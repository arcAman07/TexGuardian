"""Integration tests for compile-verify-fix visual loops.

Tests the visual verification loop integration in:
- /figures fix  (Step 3: visual verification)
- /tables fix   (Step 3: visual verification)
- /review       (Step 6: visual verification of fixes, 7-step pipeline)
- generate_and_apply_figure_fixes(visual_verify=True)
- generate_and_apply_table_fixes(visual_verify=True)
- generate_and_apply_citation_fixes(visual_verify=True)
"""

import re
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from rich.console import Console
from texguardian.config.settings import ProjectConfig, TexGuardianConfig
from texguardian.core.session import SessionState

# The VisualVerifier is imported lazily inside methods, so we patch it at
# its source module.  All three command files do:
#   from texguardian.visual.verifier import VisualVerifier
# The correct patch target is therefore "texguardian.visual.verifier.VisualVerifier".
VERIFIER_PATCH = "texguardian.visual.verifier.VisualVerifier"

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    return _ANSI_RE.sub("", text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_TEX = r"""\documentclass{article}
\usepackage{graphicx}
\usepackage{booktabs}
\begin{document}

\begin{figure}[t]
\centering
\includegraphics[width=\columnwidth]{fig1.pdf}
\caption{A test figure showing detailed experimental results for our approach.}
\label{fig:test}
\end{figure}

We refer to Figure~\ref{fig:test}.

\begin{table}[t]
\caption{Test results across methods.}
\label{tab:results}
\centering
\begin{tabular}{lcc}
\toprule
Method & Accuracy & Speed \\
\midrule
Ours & 95.1 & 1.2s \\
\bottomrule
\end{tabular}
\end{table}

We refer to Table~\ref{tab:results}.

\end{document}
"""


@pytest.fixture
def project_dir(tmp_path):
    """Create a minimal LaTeX project."""
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(MINIMAL_TEX)
    guardian_dir = tmp_path / ".texguardian"
    guardian_dir.mkdir()
    return tmp_path


@pytest.fixture
def session(project_dir):
    """Create a session with mocked LLM client."""
    config = TexGuardianConfig(
        project=ProjectConfig(main_tex="main.tex", output_dir="build"),
    )
    sess = SessionState(
        config=config,
        project_root=project_dir,
        config_path=project_dir / "texguardian.yaml",
    )
    sess.llm_client = _mock_llm_client()
    return sess


@pytest.fixture
def console():
    """Create a console that captures output."""
    output = StringIO()
    return Console(file=output, force_terminal=True, width=150)


def _mock_llm_client():
    client = AsyncMock()
    client.complete.return_value = MagicMock(
        content='{"quality_score": 85, "issues": [], "summary": "Looks good"}'
    )
    client.complete_with_vision.return_value = MagicMock(
        content='{"quality_score": 90, "issues": [], "summary": "All clear"}'
    )
    return client


def _mock_visual_result(rounds=1, quality_score=90, patches_applied=0, stopped_reason="No issues"):
    """Create a mock VisualVerificationResult."""
    from texguardian.visual.verifier import VisualVerificationResult

    return VisualVerificationResult(
        rounds=rounds,
        quality_score=quality_score,
        patches_applied=patches_applied,
        remaining_issues=[],
        stopped_reason=stopped_reason,
    )


# ---------------------------------------------------------------------------
# Test: FiguresCommand._visual_verify_figures uses VisualVerifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_figures_visual_verify_calls_verifier(session, console):
    """_visual_verify_figures should instantiate VisualVerifier and call run_loop."""
    from texguardian.cli.commands.figures import FiguresCommand

    cmd = FiguresCommand()

    mock_result = _mock_visual_result()

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = mock_result
        mock_verifier_cls.return_value = mock_instance

        await cmd._visual_verify_figures(session, console)

        mock_verifier_cls.assert_called_once_with(session)
        mock_instance.run_loop.assert_called_once()
        call_kwargs = mock_instance.run_loop.call_args
        assert call_kwargs.kwargs["max_rounds"] == session.config.safety.max_visual_rounds
        assert call_kwargs.kwargs["console"] is console
        assert "figures" in call_kwargs.kwargs["focus_areas"]
        assert "figure placement" in call_kwargs.kwargs["focus_areas"]


@pytest.mark.asyncio
async def test_figures_visual_verify_handles_error(session, console):
    """_visual_verify_figures should catch exceptions gracefully."""
    from texguardian.cli.commands.figures import FiguresCommand

    cmd = FiguresCommand()

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.side_effect = RuntimeError("Vision model unavailable")
        mock_verifier_cls.return_value = mock_instance

        # Should not raise
        await cmd._visual_verify_figures(session, console)

    output = console.file.getvalue()
    assert "Error in visual verification" in output


# ---------------------------------------------------------------------------
# Test: TablesCommand._visual_verify_tables uses VisualVerifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tables_visual_verify_calls_verifier(session, console):
    """_visual_verify_tables should instantiate VisualVerifier and call run_loop."""
    from texguardian.cli.commands.tables import TablesCommand

    cmd = TablesCommand()

    mock_result = _mock_visual_result()

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = mock_result
        mock_verifier_cls.return_value = mock_instance

        await cmd._visual_verify_tables(session, console)

        mock_verifier_cls.assert_called_once_with(session)
        mock_instance.run_loop.assert_called_once()
        call_kwargs = mock_instance.run_loop.call_args
        assert "tables" in call_kwargs.kwargs["focus_areas"]
        assert "booktabs" in call_kwargs.kwargs["focus_areas"]


@pytest.mark.asyncio
async def test_tables_visual_verify_handles_error(session, console):
    """_visual_verify_tables should catch exceptions gracefully."""
    from texguardian.cli.commands.tables import TablesCommand

    cmd = TablesCommand()

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.side_effect = RuntimeError("Render failed")
        mock_verifier_cls.return_value = mock_instance

        await cmd._visual_verify_tables(session, console)

    output = console.file.getvalue()
    assert "Error in visual verification" in output


# ---------------------------------------------------------------------------
# Test: /tables fix execute() wires visual step
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tables_fix_runs_visual_step(session, console):
    """TablesCommand.execute(fix) should call _visual_verify_tables after fixing."""
    from texguardian.cli.commands.tables import TablesCommand

    cmd = TablesCommand()

    # Make _fix_tables and _visual_verify_tables into mocks
    cmd._fix_tables = AsyncMock()
    cmd._visual_verify_tables = AsyncMock()
    cmd._analyze_tables = AsyncMock()

    # Need issues to trigger fix mode — create a tex file missing labels
    tex_no_label = MINIMAL_TEX.replace(r"\label{tab:results}", "")
    session.main_tex_path.write_text(tex_no_label)

    await cmd.execute(session, "fix", console)

    cmd._fix_tables.assert_called_once()
    cmd._visual_verify_tables.assert_called_once_with(session, console)


# ---------------------------------------------------------------------------
# Test: /figures fix execute() wires visual step (already existed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_figures_fix_runs_visual_step(session, console):
    """FiguresCommand.execute(fix) should call _visual_verify_figures after fixing."""
    from texguardian.cli.commands.figures import FiguresCommand

    cmd = FiguresCommand()

    # Make methods into mocks
    cmd._fix_figures = AsyncMock()
    cmd._visual_verify_figures = AsyncMock()
    cmd._analyze_figures = AsyncMock()

    # Need issues to trigger fix mode — remove label
    tex_no_label = MINIMAL_TEX.replace(r"\label{fig:test}", "")
    session.main_tex_path.write_text(tex_no_label)

    await cmd.execute(session, "fix", console)

    cmd._fix_figures.assert_called_once()
    cmd._visual_verify_figures.assert_called_once_with(session, console)


# ---------------------------------------------------------------------------
# Test: generate_and_apply_figure_fixes with visual_verify=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_figure_fixes_visual_verify(session, console):
    """visual_verify=True should trigger VisualVerifier after patches applied."""
    from texguardian.cli.commands.figures import generate_and_apply_figure_fixes

    # Remove label to create an issue
    tex_no_label = MINIMAL_TEX.replace(r"\label{fig:test}", "")
    session.main_tex_path.write_text(tex_no_label)

    # Mock LLM to return a patch
    mock_patch_response = (
        "Here is the fix:\n"
        "```diff\n"
        "--- a/main.tex\n"
        "+++ b/main.tex\n"
        "@@ -8,0 +9,1 @@\n"
        "+\\label{fig:test}\n"
        "```"
    )

    async def fake_stream(*args, **kwargs):
        return mock_patch_response

    with (
        patch("texguardian.llm.streaming.stream_llm", side_effect=fake_stream),
        patch("texguardian.cli.approval.interactive_approval", new_callable=AsyncMock, return_value=1),
        patch(VERIFIER_PATCH) as mock_verifier_cls,
    ):
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = _mock_visual_result(patches_applied=2)
        mock_verifier_cls.return_value = mock_instance

        applied = await generate_and_apply_figure_fixes(
            session, console, auto_approve=True, visual_verify=True,
        )

        # 1 structural + 2 visual
        assert applied == 3
        mock_instance.run_loop.assert_called_once()
        assert "figures" in mock_instance.run_loop.call_args.kwargs["focus_areas"]


@pytest.mark.asyncio
async def test_generate_figure_fixes_visual_verify_skipped_no_patches(session, console):
    """visual_verify=True should NOT run if no structural issues found."""
    from texguardian.cli.commands.figures import generate_and_apply_figure_fixes

    # No issues — all labels and captions present (MINIMAL_TEX is clean)
    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        applied = await generate_and_apply_figure_fixes(
            session, console, auto_approve=True, visual_verify=True,
        )

        assert applied == 0
        mock_verifier_cls.assert_not_called()


# ---------------------------------------------------------------------------
# Test: generate_and_apply_table_fixes with visual_verify=True
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_table_fixes_visual_verify(session, console):
    """visual_verify=True should trigger VisualVerifier after patches applied."""
    from texguardian.cli.commands.tables import generate_and_apply_table_fixes

    # Remove label to create an issue
    tex_no_label = MINIMAL_TEX.replace(r"\label{tab:results}", "")
    session.main_tex_path.write_text(tex_no_label)

    mock_patch_response = (
        "```diff\n"
        "--- a/main.tex\n"
        "+++ b/main.tex\n"
        "@@ -17,0 +18,1 @@\n"
        "+\\label{tab:results}\n"
        "```"
    )

    async def fake_stream(*args, **kwargs):
        return mock_patch_response

    with (
        patch("texguardian.llm.streaming.stream_llm", side_effect=fake_stream),
        patch("texguardian.cli.approval.interactive_approval", new_callable=AsyncMock, return_value=1),
        patch(VERIFIER_PATCH) as mock_verifier_cls,
    ):
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = _mock_visual_result(patches_applied=1)
        mock_verifier_cls.return_value = mock_instance

        applied = await generate_and_apply_table_fixes(
            session, console, auto_approve=True, visual_verify=True,
        )

        assert applied == 2  # 1 structural + 1 visual
        mock_instance.run_loop.assert_called_once()
        assert "tables" in mock_instance.run_loop.call_args.kwargs["focus_areas"]


# ---------------------------------------------------------------------------
# Test: ReviewCommand 7-step pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_review_has_eight_steps(session, console):
    """Review pipeline should show 8 steps in output."""
    from texguardian.cli.commands.review import ReviewCommand

    cmd = ReviewCommand()

    # Mock all steps to avoid real compilation / LLM calls.
    # _step_fix_verification_issues simulates applying a patch so that
    # visual steps are triggered.
    cmd._step_compile = AsyncMock(return_value=True)
    cmd._step_verify = AsyncMock()

    async def fake_fix_verify(_session, _console, result):
        result.patches_applied += 1

    cmd._step_fix_verification_issues = AsyncMock(side_effect=fake_fix_verify)
    cmd._step_citations = AsyncMock()
    cmd._step_figures = AsyncMock()
    cmd._step_tables = AsyncMock()
    cmd._step_visual_verify_fixes = AsyncMock()
    cmd._step_visual = AsyncMock()

    # Make feedback set score >= threshold to stop after 1 round
    async def fake_feedback(_session, _console, result):
        result.overall_score = 95

    cmd._step_feedback = AsyncMock(side_effect=fake_feedback)

    await cmd.execute(session, "full", console)

    output = _strip_ansi(console.file.getvalue())
    assert "Step 1/8" in output
    assert "Step 2/8" in output
    assert "Step 3/8" in output
    assert "Step 4/8" in output
    assert "Step 5/8" in output
    assert "Step 6/8" in output
    assert "Step 7/8" in output
    assert "Step 8/8" in output


@pytest.mark.asyncio
async def test_review_step7_visual_verify_called(session, console):
    """Step 7 should call _step_visual_verify_fixes when patches were applied."""
    from texguardian.cli.commands.review import ReviewCommand

    cmd = ReviewCommand()

    cmd._step_compile = AsyncMock(return_value=True)
    cmd._step_verify = AsyncMock()

    # Simulate a patch being applied so visual steps trigger
    async def fake_fix_verify(_session, _console, result):
        result.patches_applied += 1

    cmd._step_fix_verification_issues = AsyncMock(side_effect=fake_fix_verify)
    cmd._step_citations = AsyncMock()
    cmd._step_figures = AsyncMock()
    cmd._step_tables = AsyncMock()
    cmd._step_visual_verify_fixes = AsyncMock()
    cmd._step_visual = AsyncMock()

    async def fake_feedback(_session, _console, result):
        result.overall_score = 95

    cmd._step_feedback = AsyncMock(side_effect=fake_feedback)

    await cmd.execute(session, "full", console)

    cmd._step_visual_verify_fixes.assert_called_once()


@pytest.mark.asyncio
async def test_review_quick_skips_visual_polish(session, console):
    """Quick mode should skip Step 8 (visual polish) but still run Step 7."""
    from texguardian.cli.commands.review import ReviewCommand

    cmd = ReviewCommand()

    cmd._step_compile = AsyncMock(return_value=True)
    cmd._step_verify = AsyncMock()

    # Simulate a patch being applied so Step 7 (visual verify) triggers
    async def fake_fix_verify(_session, _console, result):
        result.patches_applied += 1

    cmd._step_fix_verification_issues = AsyncMock(side_effect=fake_fix_verify)
    cmd._step_citations = AsyncMock()
    cmd._step_figures = AsyncMock()
    cmd._step_tables = AsyncMock()
    cmd._step_visual_verify_fixes = AsyncMock()
    cmd._step_visual = AsyncMock()

    async def fake_feedback(_session, _console, result):
        result.overall_score = 95

    cmd._step_feedback = AsyncMock(side_effect=fake_feedback)

    await cmd.execute(session, "quick", console)

    # Step 7 (visual verify) should still run when patches were applied
    cmd._step_visual_verify_fixes.assert_called_once()
    # Step 8 (visual polish) should be skipped in quick mode
    cmd._step_visual.assert_not_called()
    output = console.file.getvalue()
    assert "Skipped" in output


# ---------------------------------------------------------------------------
# Test: _step_visual_verify_fixes behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_step_visual_verify_skips_if_no_patches(session, console):
    """Step 6 should skip if no patches were applied in earlier steps."""
    from texguardian.cli.commands.review import ReviewCommand, ReviewResult

    cmd = ReviewCommand()
    result = ReviewResult()
    result.patches_applied = 0

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        await cmd._step_visual_verify_fixes(session, console, result)
        mock_verifier_cls.assert_not_called()

    output = console.file.getvalue()
    assert "skipping" in output.lower()


@pytest.mark.asyncio
async def test_step_visual_verify_runs_if_patches_applied(session, console):
    """Step 6 should run VisualVerifier if patches were applied."""
    from texguardian.cli.commands.review import ReviewCommand, ReviewResult

    cmd = ReviewCommand()
    result = ReviewResult()
    result.patches_applied = 3

    mock_vresult = _mock_visual_result(rounds=2, quality_score=88, patches_applied=1)

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = mock_vresult
        mock_verifier_cls.return_value = mock_instance

        await cmd._step_visual_verify_fixes(session, console, result, patches_this_round=3)

        mock_instance.run_loop.assert_called_once()
        call_kwargs = mock_instance.run_loop.call_args.kwargs
        # max_rounds should be min(3, max_visual_rounds)
        assert call_kwargs["max_rounds"] == min(3, session.config.safety.max_visual_rounds)
        assert "figures" in call_kwargs["focus_areas"]
        assert "tables" in call_kwargs["focus_areas"]

    # Patches from visual verification should be added to total
    assert result.patches_applied == 4  # 3 original + 1 visual


@pytest.mark.asyncio
async def test_step_visual_verify_handles_error(session, console):
    """Step 6 should handle errors gracefully."""
    from texguardian.cli.commands.review import ReviewCommand, ReviewResult

    cmd = ReviewCommand()
    result = ReviewResult()
    result.patches_applied = 2

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.side_effect = RuntimeError("Vision API down")
        mock_verifier_cls.return_value = mock_instance

        # Should not raise
        await cmd._step_visual_verify_fixes(session, console, result, patches_this_round=2)

    output = console.file.getvalue()
    assert "Error in visual verification" in output
    # Patches count should not change on error
    assert result.patches_applied == 2


# ---------------------------------------------------------------------------
# Test: Focus areas are correct for each command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_figure_focus_areas(session, console):
    """Figure visual verification should use figure-specific focus areas."""
    from texguardian.cli.commands.figures import FiguresCommand

    cmd = FiguresCommand()

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = _mock_visual_result()
        mock_verifier_cls.return_value = mock_instance

        await cmd._visual_verify_figures(session, console)

        focus = mock_instance.run_loop.call_args.kwargs["focus_areas"]
        assert set(focus) == {"figures", "figure placement", "figure captions", "figure labels"}


@pytest.mark.asyncio
async def test_table_focus_areas(session, console):
    """Table visual verification should use table-specific focus areas."""
    from texguardian.cli.commands.tables import TablesCommand

    cmd = TablesCommand()

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = _mock_visual_result()
        mock_verifier_cls.return_value = mock_instance

        await cmd._visual_verify_tables(session, console)

        focus = mock_instance.run_loop.call_args.kwargs["focus_areas"]
        assert set(focus) == {"tables", "table alignment", "table formatting", "booktabs"}


@pytest.mark.asyncio
async def test_review_step6_focus_areas(session, console):
    """Review Step 6 should use combined figure+table focus areas."""
    from texguardian.cli.commands.review import ReviewCommand, ReviewResult

    cmd = ReviewCommand()
    result = ReviewResult()
    result.patches_applied = 1

    with patch(VERIFIER_PATCH) as mock_verifier_cls:
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = _mock_visual_result()
        mock_verifier_cls.return_value = mock_instance

        await cmd._step_visual_verify_fixes(session, console, result, patches_this_round=1)

        focus = mock_instance.run_loop.call_args.kwargs["focus_areas"]
        assert set(focus) == {"figures", "tables", "captions", "labels"}


# ---------------------------------------------------------------------------
# Fixtures for citation tests
# ---------------------------------------------------------------------------

MINIMAL_BIB = r"""@article{smith2024real,
  title = {A Real Paper That Exists},
  author = {Smith, John},
  year = {2024},
  journal = {Nature},
}

@article{fake2024hallucinated,
  title = {A Completely Fabricated Paper Title That Does Not Exist},
  author = {Fakerson, Fakey},
  year = {2024},
  journal = {Journal of Nonexistent Research},
}
"""

MINIMAL_TEX_WITH_CITATIONS = r"""\documentclass{article}
\usepackage{natbib}
\begin{document}

This result was shown by \cite{smith2024real} and also \cite{fake2024hallucinated}.

\bibliographystyle{plainnat}
\bibliography{refs}

\end{document}
"""


@pytest.fixture
def citation_session(tmp_path):
    """Session with a .bib file and citations in the tex."""
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(MINIMAL_TEX_WITH_CITATIONS)
    bib_file = tmp_path / "refs.bib"
    bib_file.write_text(MINIMAL_BIB)
    guardian_dir = tmp_path / ".texguardian"
    guardian_dir.mkdir()

    config = TexGuardianConfig(
        project=ProjectConfig(main_tex="main.tex", output_dir="build"),
    )
    sess = SessionState(
        config=config,
        project_root=tmp_path,
        config_path=tmp_path / "texguardian.yaml",
    )
    sess.llm_client = _mock_llm_client()
    return sess


# ---------------------------------------------------------------------------
# Test: generate_and_apply_citation_fixes
# ---------------------------------------------------------------------------


def _mock_validation_results():
    """Create mock validation results with one hallucinated citation."""
    from texguardian.citations.validator import BibEntry, ValidationResult

    valid = ValidationResult(
        key="smith2024real",
        status="valid",
        confidence=1.0,
        original=BibEntry(
            key="smith2024real",
            entry_type="article",
            title="A Real Paper That Exists",
            author="Smith, John",
            year="2024",
        ),
        message="Found in CrossRef",
    )
    hallucinated = ValidationResult(
        key="fake2024hallucinated",
        status="likely_hallucinated",
        confidence=0.8,
        original=BibEntry(
            key="fake2024hallucinated",
            entry_type="article",
            title="A Completely Fabricated Paper Title That Does Not Exist",
            author="Fakerson, Fakey",
            year="2024",
        ),
        message="No matching papers found",
        search_results=[{
            "title": "An Actual Similar Paper",
            "doi": "10.1234/similar",
            "authors": "Real, Author",
            "year": "2023",
            "source": "crossref",
        }],
    )
    return [valid, hallucinated]


@pytest.mark.asyncio
async def test_generate_citation_fixes_applies_patches(citation_session, console):
    """generate_and_apply_citation_fixes should apply patches for hallucinated cites."""
    from texguardian.cli.commands.citations import generate_and_apply_citation_fixes

    mock_patch_response = (
        "```diff\n"
        "--- a/refs.bib\n"
        "+++ b/refs.bib\n"
        "@@ -6,5 +6,5 @@\n"
        "-@article{fake2024hallucinated,\n"
        "-  title = {A Completely Fabricated Paper Title That Does Not Exist},\n"
        "-  author = {Fakerson, Fakey},\n"
        "+@article{fake2024hallucinated,\n"
        "+  title = {An Actual Similar Paper},\n"
        "+  author = {Real, Author},\n"
        "```"
    )

    async def fake_stream(*args, **kwargs):
        return mock_patch_response

    validation_results = _mock_validation_results()

    with (
        patch("texguardian.llm.streaming.stream_llm", side_effect=fake_stream),
        patch("texguardian.cli.approval.interactive_approval", new_callable=AsyncMock, return_value=1),
    ):
        applied = await generate_and_apply_citation_fixes(
            citation_session, console,
            auto_approve=True,
            validation_results=validation_results,
        )

        assert applied == 1


@pytest.mark.asyncio
async def test_generate_citation_fixes_skips_validation_when_results_passed(citation_session, console):
    """When validation_results is passed, no API calls should be made."""
    from texguardian.cli.commands.citations import generate_and_apply_citation_fixes

    async def fake_stream(*args, **kwargs):
        return "No patches needed."

    validation_results = _mock_validation_results()

    with (
        patch("texguardian.llm.streaming.stream_llm", side_effect=fake_stream),
        patch("texguardian.cli.approval.interactive_approval", new_callable=AsyncMock, return_value=0),
        patch("texguardian.citations.validator.CitationValidator.validate_bib_file") as mock_validate,
    ):
        await generate_and_apply_citation_fixes(
            citation_session, console,
            auto_approve=True,
            validation_results=validation_results,
        )

        # Validator should NOT have been called since we passed results
        mock_validate.assert_not_called()


@pytest.mark.asyncio
async def test_generate_citation_fixes_calls_validator_when_no_results(citation_session, console):
    """When validation_results is None, the validator should be called."""
    from texguardian.cli.commands.citations import generate_and_apply_citation_fixes

    mock_results = _mock_validation_results()

    async def fake_stream(*args, **kwargs):
        return "No patches."

    with (
        patch("texguardian.llm.streaming.stream_llm", side_effect=fake_stream),
        patch("texguardian.cli.approval.interactive_approval", new_callable=AsyncMock, return_value=0),
        patch(
            "texguardian.citations.validator.CitationValidator.validate_bib_file",
            new_callable=AsyncMock,
            return_value=mock_results,
        ) as mock_validate,
    ):
        await generate_and_apply_citation_fixes(
            citation_session, console, auto_approve=True,
        )

        mock_validate.assert_called_once()


@pytest.mark.asyncio
async def test_generate_citation_fixes_visual_verify(citation_session, console):
    """visual_verify=True should trigger VisualVerifier after patches applied."""
    from texguardian.cli.commands.citations import generate_and_apply_citation_fixes

    mock_patch_response = (
        "```diff\n"
        "--- a/refs.bib\n"
        "+++ b/refs.bib\n"
        "@@ -6,3 +6,3 @@\n"
        "-  title = {Fake},\n"
        "+  title = {Real},\n"
        "```"
    )

    async def fake_stream(*args, **kwargs):
        return mock_patch_response

    validation_results = _mock_validation_results()

    with (
        patch("texguardian.llm.streaming.stream_llm", side_effect=fake_stream),
        patch("texguardian.cli.approval.interactive_approval", new_callable=AsyncMock, return_value=1),
        patch(VERIFIER_PATCH) as mock_verifier_cls,
    ):
        mock_instance = AsyncMock()
        mock_instance.run_loop.return_value = _mock_visual_result(patches_applied=1)
        mock_verifier_cls.return_value = mock_instance

        applied = await generate_and_apply_citation_fixes(
            citation_session, console,
            auto_approve=True,
            visual_verify=True,
            validation_results=validation_results,
        )

        # 1 structural + 1 visual
        assert applied == 2
        mock_instance.run_loop.assert_called_once()
        assert "citations" in mock_instance.run_loop.call_args.kwargs["focus_areas"]


@pytest.mark.asyncio
async def test_generate_citation_fixes_no_issues_returns_zero(citation_session, console):
    """When no issues exist, function should return 0 without calling LLM."""
    from texguardian.cli.commands.citations import generate_and_apply_citation_fixes
    from texguardian.citations.validator import BibEntry, ValidationResult

    # All citations valid
    all_valid = [
        ValidationResult(
            key="smith2024real",
            status="valid",
            confidence=1.0,
            original=BibEntry(key="smith2024real", entry_type="article", title="A Real Paper"),
        ),
        ValidationResult(
            key="fake2024hallucinated",
            status="valid",
            confidence=1.0,
            original=BibEntry(key="fake2024hallucinated", entry_type="article", title="Also Real"),
        ),
    ]

    # Remove \cite usage to eliminate format_issues (uses natbib \cite which
    # the parser counts as style="cite")
    tex_no_cite = MINIMAL_TEX_WITH_CITATIONS.replace(r"\cite{", r"\citep{")
    citation_session.main_tex_path.write_text(tex_no_cite)

    with patch("texguardian.llm.streaming.stream_llm") as mock_llm:
        applied = await generate_and_apply_citation_fixes(
            citation_session, console,
            auto_approve=True,
            validation_results=all_valid,
        )

        assert applied == 0
        mock_llm.assert_not_called()

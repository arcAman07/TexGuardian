"""Integration tests for compile-verify-fix visual loops.

Tests the visual verification loop integration in:
- /figures fix  (Step 3: visual verification)
- /tables fix   (Step 3: visual verification)
- /review       (Step 6: visual verification of fixes, 7-step pipeline)
- generate_and_apply_figure_fixes(visual_verify=True)
- generate_and_apply_table_fixes(visual_verify=True)
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
async def test_review_has_seven_steps(session, console):
    """Review pipeline should show 7 steps in output."""
    from texguardian.cli.commands.review import ReviewCommand

    cmd = ReviewCommand()

    # Mock all steps to avoid real compilation / LLM calls
    cmd._step_compile = AsyncMock(return_value=True)
    cmd._step_verify = AsyncMock()
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
    assert "Step 1/7" in output
    assert "Step 2/7" in output
    assert "Step 3/7" in output
    assert "Step 4/7" in output
    assert "Step 5/7" in output
    assert "Step 6/7" in output
    assert "Step 7/7" in output


@pytest.mark.asyncio
async def test_review_step6_visual_verify_called(session, console):
    """Step 6 should call _step_visual_verify_fixes."""
    from texguardian.cli.commands.review import ReviewCommand

    cmd = ReviewCommand()

    cmd._step_compile = AsyncMock(return_value=True)
    cmd._step_verify = AsyncMock()
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
    """Quick mode should skip Step 7 (visual polish) but still run Step 6."""
    from texguardian.cli.commands.review import ReviewCommand

    cmd = ReviewCommand()

    cmd._step_compile = AsyncMock(return_value=True)
    cmd._step_verify = AsyncMock()
    cmd._step_citations = AsyncMock()
    cmd._step_figures = AsyncMock()
    cmd._step_tables = AsyncMock()
    cmd._step_visual_verify_fixes = AsyncMock()
    cmd._step_visual = AsyncMock()

    async def fake_feedback(_session, _console, result):
        result.overall_score = 95

    cmd._step_feedback = AsyncMock(side_effect=fake_feedback)

    await cmd.execute(session, "quick", console)

    # Step 6 should still run
    cmd._step_visual_verify_fixes.assert_called_once()
    # Step 7 should be skipped
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

        await cmd._step_visual_verify_fixes(session, console, result)

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
        await cmd._step_visual_verify_fixes(session, console, result)

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

        await cmd._step_visual_verify_fixes(session, console, result)

        focus = mock_instance.run_loop.call_args.kwargs["focus_areas"]
        assert set(focus) == {"figures", "tables", "captions", "labels"}

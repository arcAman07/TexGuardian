"""Tests for the camera-ready command."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from texguardian.cli.commands.camera_ready import (
    CAMERA_READY_PROMPT,
    VENUE_TEMPLATES,
    CameraReadyAnalysis,
    CameraReadyCommand,
    VenueInfo,
    _build_venue_info,
    _extract_preamble,
    _resolve_full_content,
    _venue_from_preamble,
    _venue_from_spec,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

NEURIPS_PREAMBLE = r"""
\documentclass{article}
\usepackage{neurips_2026}
\title{My Cool Paper}
"""

NEURIPS_PAPER = (
    NEURIPS_PREAMBLE
    + r"""
\begin{document}
\maketitle
\author{Anonymous}
\section{Introduction}
In the final analysis, we show ...
% TODO: fix this paragraph
\section*{Acknowledgments}
We thank the reviewers.
\end{document}
"""
)

NEURIPS_FINAL_PAPER = r"""
\documentclass{article}
\usepackage[final]{neurips_2026}
\title{My Cool Paper}
\begin{document}
\maketitle
\author{John Doe}
\section{Introduction}
We show something interesting.
\section*{Acknowledgments}
We thank the reviewers.
\end{document}
"""

CVPR_PAPER_WITH_BIB = r"""
\documentclass[10pt,twocolumn,letterpaper]{article}
\usepackage[review]{cvpr}
\title{CVPR Paper}
\begin{document}
\maketitle
\section{Introduction}
Some content.
\bibliography{cvpr_paper}
\end{document}
"""


def _make_paper_spec(venue: str = "Unknown") -> Any:
    """Create a minimal mock PaperSpec."""
    spec = MagicMock()
    spec.venue = venue
    spec.title = "Test Paper"
    spec.thresholds.max_pages = 9
    return spec


MOCK_VENUE_CHECKLIST = """\
1. Include a reproducibility statement
2. Add supplementary material description
3. Ensure camera-ready formatting compliance
"""


def _make_streaming_llm(
    response_text: str,
    checklist_response: str = "",
) -> AsyncMock:
    """Create an LLM mock that supports both stream() and complete().

    ``response_text`` is returned by ``stream()`` (patch generation).
    ``checklist_response`` is returned by ``complete()`` (venue checklist
    fetch).  Falls back to ``response_text`` if not provided.
    """
    llm = AsyncMock()

    # stream() yields chunks
    async def _fake_stream(**kwargs):
        chunk = MagicMock()
        chunk.content = response_text
        yield chunk

    llm.stream = _fake_stream

    # complete() — used by _fetch_venue_checklist
    resp = MagicMock()
    resp.content = checklist_response or response_text
    llm.complete = AsyncMock(return_value=resp)

    return llm


def _make_session(
    content: str,
    *,
    venue: str = "Unknown",
    llm_response: str = "",
    checklist_response: str = "",
    tmp_path: Path | None = None,
) -> Any:
    """Create a minimal mock SessionState."""
    root = tmp_path or Path("/tmp/test_project")
    main_tex = root / "main.tex"

    session = MagicMock()
    session.project_root = root
    session.main_tex_path = main_tex
    session.guardian_dir = root / ".texguardian"
    session.output_dir = root / "build"
    session.paper_spec = _make_paper_spec(venue)
    session.config.safety = MagicMock()

    # Context mock
    context = MagicMock()
    context.add_assistant_message = MagicMock()
    context.get_last_assistant_message = MagicMock(return_value=llm_response)
    session.context = context

    # LLM client mock
    if llm_response:
        session.llm_client = _make_streaming_llm(llm_response, checklist_response)
    else:
        session.llm_client = None

    session.checkpoint_manager = None
    session.last_compilation = None

    return session


# ---------------------------------------------------------------------------
# Tests: _extract_preamble
# ---------------------------------------------------------------------------

class TestExtractPreamble:
    def test_extracts_before_begin_document(self):
        content = r"\documentclass{article}" + "\n" + r"\begin{document}" + "\nBody"
        assert _extract_preamble(content) == r"\documentclass{article}" + "\n"

    def test_returns_whole_content_if_no_begin_document(self):
        content = r"\documentclass{article}"
        assert _extract_preamble(content) == content


# ---------------------------------------------------------------------------
# Tests: _resolve_full_content
# ---------------------------------------------------------------------------

class TestResolveFullContent:
    def test_inlines_input(self, tmp_path: Path):
        """\\input{intro} should be expanded inline."""
        intro = tmp_path / "intro.tex"
        intro.write_text("Hello from intro.\n% TODO: fix intro")

        main = tmp_path / "main.tex"
        main.write_text(
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\input{intro}\n"
            "\\end{document}\n"
        )

        full = _resolve_full_content(main)
        assert "Hello from intro." in full
        assert "TODO: fix intro" in full
        # The \input line itself is also preserved
        assert "\\input{intro}" in full

    def test_inlines_include(self, tmp_path: Path):
        """\\include{ack} should be expanded inline."""
        ack = tmp_path / "ack.tex"
        ack.write_text("\\section*{Acknowledgments}\nWe thank NSF.")

        main = tmp_path / "main.tex"
        main.write_text(
            "\\documentclass{article}\n"
            "\\begin{document}\n"
            "\\include{ack}\n"
            "\\end{document}\n"
        )

        full = _resolve_full_content(main)
        assert "Acknowledgments" in full
        assert "NSF" in full

    def test_adds_tex_extension(self, tmp_path: Path):
        """\\input{foo} → foo.tex"""
        foo = tmp_path / "foo.tex"
        foo.write_text("Foo content.")

        main = tmp_path / "main.tex"
        main.write_text("\\input{foo}\n")

        full = _resolve_full_content(main)
        assert "Foo content." in full

    def test_no_infinite_loop(self, tmp_path: Path):
        """Circular \\input should not loop."""
        a = tmp_path / "a.tex"
        b = tmp_path / "b.tex"
        a.write_text("A content.\n\\input{b}\n")
        b.write_text("B content.\n\\input{a}\n")

        full = _resolve_full_content(a)
        assert "A content." in full
        assert "B content." in full

    def test_missing_include_ignored(self, tmp_path: Path):
        """\\input{missing} with no file is silently skipped."""
        main = tmp_path / "main.tex"
        main.write_text("Before.\n\\input{missing}\nAfter.\n")

        full = _resolve_full_content(main)
        assert "Before." in full
        assert "After." in full

    def test_returns_plain_content_when_no_inputs(self, tmp_path: Path):
        main = tmp_path / "main.tex"
        main.write_text("Just a simple file.\n")
        full = _resolve_full_content(main)
        assert "Just a simple file." in full


# ---------------------------------------------------------------------------
# Tests: Venue resolution
# ---------------------------------------------------------------------------

class TestResolveVenueFromPaperSpec:
    def test_neurips_from_spec(self):
        preamble = r"\usepackage{neurips_2026}"
        info = _venue_from_spec("NeurIPS 2026", preamble)
        assert info is not None
        assert info.name == "neurips"
        assert info.display_name == "NeurIPS 2026"
        assert info.style_package == "neurips_2026"
        assert info.page_limit == 9

    def test_icml_from_spec(self):
        preamble = r"\usepackage{icml2025}"
        info = _venue_from_spec("ICML 2025", preamble)
        assert info is not None
        assert info.name == "icml"

    def test_unknown_venue_returns_none(self):
        info = _venue_from_spec("Some Workshop", r"\documentclass{article}")
        assert info is None


class TestResolveVenueFromPreamble:
    def test_detects_neurips_2026(self):
        preamble = r"\usepackage{neurips_2026}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert info.name == "neurips"
        assert "neurips_2026" in info.style_package

    def test_detects_neurips_2024(self):
        preamble = r"\usepackage{neurips_2024}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert info.name == "neurips"

    def test_detects_neurips_2030(self):
        preamble = r"\usepackage{neurips2030}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert info.name == "neurips"

    def test_detects_icml(self):
        preamble = r"\usepackage{icml2025}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert info.name == "icml"

    def test_detects_iclr(self):
        preamble = r"\usepackage{iclr2026_conference}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert info.name == "iclr"

    def test_preamble_only_no_match_in_body(self):
        """\\bibliography{neurips_stuff} in the body must NOT trigger detection."""
        preamble_only = r"\documentclass{article}" + "\n"
        info = _venue_from_preamble(preamble_only)
        assert info is None

    def test_cvpr_detected_in_preamble(self):
        preamble = r"\usepackage[review]{cvpr}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert info.name == "cvpr"


class TestVenueYearAgnostic:
    """Verify that VENUE_TEMPLATES patterns match multiple years."""

    @pytest.mark.parametrize("pkg", ["neurips_2024", "neurips_2026", "neurips_2030", "neurips2025"])
    def test_neurips_years(self, pkg: str):
        import re
        pattern = VENUE_TEMPLATES["neurips"]["pattern"]
        assert re.search(pattern, pkg, re.IGNORECASE)

    @pytest.mark.parametrize("pkg", ["icml2024", "icml2025", "icml2030"])
    def test_icml_years(self, pkg: str):
        import re
        pattern = VENUE_TEMPLATES["icml"]["pattern"]
        assert re.search(pattern, pkg, re.IGNORECASE)

    @pytest.mark.parametrize("pkg", ["iclr2024", "iclr2025", "iclr2030"])
    def test_iclr_years(self, pkg: str):
        import re
        pattern = VENUE_TEMPLATES["iclr"]["pattern"]
        assert re.search(pattern, pkg, re.IGNORECASE)


# ---------------------------------------------------------------------------
# Tests: Analysis
# ---------------------------------------------------------------------------

class TestAnalyzeSubmission:
    def setup_method(self):
        self.cmd = CameraReadyCommand()

    def test_already_camera_ready(self):
        """Paper with [final] in preamble is detected as camera-ready."""
        analysis = self.cmd._analyze_submission(
            NEURIPS_FINAL_PAPER, NEURIPS_FINAL_PAPER, venue=None,
        )
        assert analysis.is_camera_ready is True
        assert analysis.has_final_option is True

    def test_needs_conversion(self):
        """Paper without [final] has issues populated."""
        analysis = self.cmd._analyze_submission(
            NEURIPS_PAPER, NEURIPS_PAPER, venue=None,
        )
        assert analysis.is_camera_ready is False
        assert any("camera-ready" in i.lower() for i in analysis.issues)

    def test_greedy_final_fixed(self):
        """'In the final analysis' in body does NOT trigger has_final_option."""
        paper = r"""
\documentclass{article}
\usepackage{neurips_2026}
\begin{document}
In the final analysis, we conclude that ...
\end{document}
"""
        analysis = self.cmd._analyze_submission(paper, paper, venue=None)
        assert analysis.has_final_option is False
        assert analysis.is_camera_ready is False

    def test_detects_todo_markers(self):
        analysis = self.cmd._analyze_submission(
            NEURIPS_PAPER, NEURIPS_PAPER, venue=None,
        )
        assert analysis.has_todo_markers is True

    def test_detects_acknowledgments(self):
        analysis = self.cmd._analyze_submission(
            NEURIPS_PAPER, NEURIPS_PAPER, venue=None,
        )
        assert analysis.has_acknowledgments is True

    def test_detects_ack_in_included_file(self):
        """Acknowledgments in an \\input'd file should still be detected.

        full_content contains the expanded text even though content (main.tex)
        doesn't have it directly.
        """
        main_content = r"""
\documentclass{article}
\usepackage{neurips_2026}
\begin{document}
\input{ack}
\end{document}
"""
        full_content = r"""
\documentclass{article}
\usepackage{neurips_2026}
\begin{document}
\input{ack}
\section*{Acknowledgments}
We thank NSF.
\end{document}
"""
        analysis = self.cmd._analyze_submission(
            main_content, full_content, venue=None,
        )
        assert analysis.has_acknowledgments is True

    def test_detects_todo_in_included_file(self):
        """TODOs in an \\input'd file should still be detected."""
        main_content = r"""
\documentclass{article}
\begin{document}
\input{sections/intro}
\end{document}
"""
        full_content = main_content + "\n% TODO: rewrite the introduction\n"
        analysis = self.cmd._analyze_submission(
            main_content, full_content, venue=None,
        )
        assert analysis.has_todo_markers is True

    def test_accepted_option_detected(self):
        paper = r"""
\documentclass{article}
\usepackage[accepted]{icml2025}
\begin{document}
Content
\end{document}
"""
        analysis = self.cmd._analyze_submission(paper, paper, venue=None)
        assert analysis.has_accepted_option is True
        assert analysis.is_camera_ready is True

    def test_cvpr_review_flagged(self):
        """[review] option in CVPR preamble should be flagged as an issue."""
        venue = VenueInfo(
            name="cvpr",
            display_name="CVPR 2026",
            style_package="cvpr",
            camera_ready_option=r"\usepackage{cvpr}",
            anonymous_option=r"\usepackage[review]{cvpr}",
            page_limit=8,
            checklist=[],
        )
        analysis = self.cmd._analyze_submission(
            CVPR_PAPER_WITH_BIB, CVPR_PAPER_WITH_BIB, venue=venue,
        )
        assert any("[review]" in i for i in analysis.issues)


# ---------------------------------------------------------------------------
# Tests: Greedy venue detection bug (bug #1)
# ---------------------------------------------------------------------------

class TestGreedyVenueDetectionFixed:
    def test_bibliography_cvpr_not_matched(self):
        """\\bibliography{cvpr_paper} in body must NOT match CVPR venue."""
        content = r"""
\documentclass{article}
\begin{document}
\bibliography{cvpr_paper}
\end{document}
"""
        preamble = _extract_preamble(content)
        info = _venue_from_preamble(preamble)
        assert info is None

    def test_bibliography_neurips_not_matched(self):
        """\\bibliography{neurips_stuff} in body must NOT match NeurIPS."""
        content = r"""
\documentclass{article}
\begin{document}
\bibliography{neurips_stuff}
\end{document}
"""
        preamble = _extract_preamble(content)
        info = _venue_from_preamble(preamble)
        assert info is None


# ---------------------------------------------------------------------------
# Tests: Targeted content builder
# ---------------------------------------------------------------------------

class TestBuildTargetedContent:
    def test_includes_preamble(self):
        cmd = CameraReadyCommand()
        analysis = cmd._analyze_submission(NEURIPS_PAPER, NEURIPS_PAPER, venue=None)
        targeted = cmd._build_targeted_content(NEURIPS_PAPER, NEURIPS_PAPER, analysis)
        assert "%%% PREAMBLE %%%" in targeted
        assert r"\usepackage{neurips_2026}" in targeted

    def test_includes_todo_lines(self):
        cmd = CameraReadyCommand()
        analysis = cmd._analyze_submission(NEURIPS_PAPER, NEURIPS_PAPER, venue=None)
        targeted = cmd._build_targeted_content(NEURIPS_PAPER, NEURIPS_PAPER, analysis)
        assert "%%% TODO/FIXME LINES %%%" in targeted
        assert "TODO" in targeted

    def test_includes_acknowledgments(self):
        cmd = CameraReadyCommand()
        analysis = cmd._analyze_submission(NEURIPS_PAPER, NEURIPS_PAPER, venue=None)
        targeted = cmd._build_targeted_content(NEURIPS_PAPER, NEURIPS_PAPER, analysis)
        assert "%%% ACKNOWLEDGMENTS REGION %%%" in targeted

    def test_includes_end_of_document(self):
        cmd = CameraReadyCommand()
        analysis = cmd._analyze_submission(NEURIPS_PAPER, NEURIPS_PAPER, venue=None)
        targeted = cmd._build_targeted_content(NEURIPS_PAPER, NEURIPS_PAPER, analysis)
        assert "%%% END OF DOCUMENT" in targeted

    def test_finds_ack_in_full_content(self):
        """Acknowledgments in included file should appear in targeted content."""
        main = r"""
\documentclass{article}
\begin{document}
\input{ack}
\end{document}
"""
        full = r"""
\documentclass{article}
\begin{document}
\input{ack}
\section*{Acknowledgments}
We thank the reviewers.
\end{document}
"""
        cmd = CameraReadyCommand()
        analysis = cmd._analyze_submission(main, full, venue=None)
        targeted = cmd._build_targeted_content(main, full, analysis)
        assert "%%% ACKNOWLEDGMENTS REGION %%%" in targeted
        assert "We thank the reviewers" in targeted


# ---------------------------------------------------------------------------
# Tests: Execute saves to context (bug #4)
# ---------------------------------------------------------------------------

class TestExecuteSavesToContext:
    @pytest.mark.asyncio
    async def test_llm_response_saved_to_context(self, tmp_path: Path):
        """Verify session.context.add_assistant_message() is called."""
        llm_response = """Here's the patch:

```diff
--- a/main.tex
+++ b/main.tex
@@ -2,1 +2,1 @@
-\\usepackage{neurips_2026}
+\\usepackage[final]{neurips_2026}
```
"""
        main_tex = tmp_path / "main.tex"
        main_tex.write_text(NEURIPS_PAPER)

        session = _make_session(
            NEURIPS_PAPER, venue="NeurIPS 2026",
            llm_response=llm_response, tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()

        cmd = CameraReadyCommand()

        # Patch interactive_approval at its source
        with patch(
            "texguardian.cli.approval.interactive_approval",
            new_callable=AsyncMock,
            return_value=0,
        ):
            await cmd.execute(session, "", console)

        # The key assertion: LLM response was saved to context
        session.context.add_assistant_message.assert_called_once_with(llm_response)


# ---------------------------------------------------------------------------
# Tests: Next steps shown after changes
# ---------------------------------------------------------------------------

NEURIPS_FULLY_READY_PAPER = r"""
\documentclass{article}
\usepackage[final]{neurips_2026}
\title{My Cool Paper}
\begin{document}
\maketitle
\author{John Doe}
\section{Introduction}
We show something interesting.
\section*{Acknowledgments}
We thank the reviewers.
\section*{Paper Checklist}
\begin{checklist}
\item Yes
\end{checklist}
\section*{Broader Impact}
Our work has positive societal impact.
\section*{Reproducibility}
Code is available at example.com.
\end{document}
"""


class TestNextStepsShown:
    @pytest.mark.asyncio
    async def test_already_camera_ready_shows_next_steps(self, tmp_path: Path):
        """When paper is fully camera-ready (including required sections), next steps shown."""
        main_tex = tmp_path / "main.tex"
        main_tex.write_text(NEURIPS_FULLY_READY_PAPER)

        session = _make_session(
            NEURIPS_FULLY_READY_PAPER, venue="NeurIPS 2026", tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = CameraReadyCommand()

        await cmd.execute(session, "", console)

        all_calls = " ".join(
            str(call) for call in console.print.call_args_list
        )
        assert "/review" in all_calls
        assert "/visual_polish" in all_calls or "/anonymize" in all_calls

    @pytest.mark.asyncio
    async def test_next_steps_after_patches_applied(self, tmp_path: Path):
        """When patches are applied, next steps are shown."""
        llm_response = """```diff
--- a/main.tex
+++ b/main.tex
@@ -2,1 +2,1 @@
-\\usepackage{neurips_2026}
+\\usepackage[final]{neurips_2026}
```
"""
        main_tex = tmp_path / "main.tex"
        main_tex.write_text(NEURIPS_PAPER)

        session = _make_session(
            NEURIPS_PAPER, venue="NeurIPS 2026",
            llm_response=llm_response, tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = CameraReadyCommand()

        # Mock approval to say 1 patch applied
        with patch(
            "texguardian.cli.approval.interactive_approval",
            new_callable=AsyncMock,
            return_value=1,
        ):
            await cmd.execute(session, "", console)

        all_calls = " ".join(
            str(call) for call in console.print.call_args_list
        )
        assert "/review" in all_calls

    @pytest.mark.asyncio
    async def test_no_changes_message_when_nothing_applied(self, tmp_path: Path):
        """When no patches are applied, user is told to fix manually."""
        llm_response = """```diff
--- a/main.tex
+++ b/main.tex
@@ -2,1 +2,1 @@
-\\usepackage{neurips_2026}
+\\usepackage[final]{neurips_2026}
```
"""
        main_tex = tmp_path / "main.tex"
        main_tex.write_text(NEURIPS_PAPER)

        session = _make_session(
            NEURIPS_PAPER, venue="NeurIPS 2026",
            llm_response=llm_response, tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = CameraReadyCommand()

        # Mock approval to say 0 patches applied (user skipped)
        with patch(
            "texguardian.cli.approval.interactive_approval",
            new_callable=AsyncMock,
            return_value=0,
        ):
            await cmd.execute(session, "", console)

        all_calls = " ".join(
            str(call) for call in console.print.call_args_list
        )
        assert "No changes applied" in all_calls


# ---------------------------------------------------------------------------
# Tests: Venue checklist end-to-end
# ---------------------------------------------------------------------------

# Sample papers for each venue
ICML_PAPER = r"""
\documentclass{article}
\usepackage{icml2025}
\title{ICML Paper}
\begin{document}
\maketitle
\section{Introduction}
Content.
\end{document}
"""

ICLR_PAPER = r"""
\documentclass{article}
\usepackage{iclr2026_conference}
\title{ICLR Paper}
\begin{document}
\maketitle
\section{Introduction}
Content.
\end{document}
"""

CVPR_PAPER = r"""
\documentclass[10pt,twocolumn,letterpaper]{article}
\usepackage[review]{cvpr}
\title{CVPR Paper}
\begin{document}
\maketitle
\section{Introduction}
Content.
\end{document}
"""

AAAI_PAPER = r"""
\documentclass{article}
\usepackage{aaai25}
\title{AAAI Paper}
\begin{document}
\maketitle
\section{Introduction}
Content.
\end{document}
"""


# ---------------------------------------------------------------------------
# Tests: _fetch_venue_checklist (LLM-based, replaces hardcoded sections)
# ---------------------------------------------------------------------------

class TestFetchVenueChecklist:
    """Verify that _fetch_venue_checklist() parses LLM responses correctly."""

    @pytest.mark.asyncio
    async def test_parses_numbered_list(self):
        """Numbered list from LLM is parsed into individual items."""
        llm_text = (
            "1. Include a reproducibility statement\n"
            "2. Add supplementary material description\n"
            "3. Ensure camera-ready formatting compliance\n"
        )
        llm = AsyncMock()
        resp = MagicMock()
        resp.content = llm_text
        llm.complete = AsyncMock(return_value=resp)

        session = MagicMock()
        session.llm_client = llm
        console = MagicMock()

        venue = VenueInfo(
            name="neurips", display_name="NeurIPS 2026",
            style_package="neurips_2026",
            camera_ready_option=r"\usepackage[final]{neurips_2026}",
            anonymous_option=r"\usepackage{neurips_2026}",
            page_limit=9, checklist=[],
        )

        cmd = CameraReadyCommand()
        items = await cmd._fetch_venue_checklist(venue, session, console)

        assert len(items) == 3
        assert "reproducibility statement" in items[0].lower()
        assert "supplementary" in items[1].lower()

    @pytest.mark.asyncio
    async def test_parses_dash_list(self):
        """Dash-prefixed list is also parsed."""
        llm_text = (
            "- Include ethics statement\n"
            "- Add broader impact section\n"
        )
        llm = AsyncMock()
        resp = MagicMock()
        resp.content = llm_text
        llm.complete = AsyncMock(return_value=resp)

        session = MagicMock()
        session.llm_client = llm
        console = MagicMock()

        venue = VenueInfo(
            name="iclr", display_name="ICLR 2026",
            style_package="iclr2026_conference",
            camera_ready_option=r"\iclrfinalcopy",
            anonymous_option=r"\usepackage{iclr2026_conference}",
            page_limit=None, checklist=[],
        )

        cmd = CameraReadyCommand()
        items = await cmd._fetch_venue_checklist(venue, session, console)

        assert len(items) == 2
        assert "ethics" in items[0].lower()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_venue(self):
        """No venue → skip LLM call, return []."""
        session = MagicMock()
        session.llm_client = AsyncMock()
        console = MagicMock()

        cmd = CameraReadyCommand()
        items = await cmd._fetch_venue_checklist(None, session, console)

        assert items == []
        session.llm_client.complete.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_llm(self):
        """No LLM client → return []."""
        session = MagicMock()
        session.llm_client = None
        console = MagicMock()

        venue = VenueInfo(
            name="neurips", display_name="NeurIPS 2026",
            style_package="neurips_2026",
            camera_ready_option=r"\usepackage[final]{neurips_2026}",
            anonymous_option=r"\usepackage{neurips_2026}",
            page_limit=9, checklist=[],
        )

        cmd = CameraReadyCommand()
        items = await cmd._fetch_venue_checklist(venue, session, console)

        assert items == []

    @pytest.mark.asyncio
    async def test_filters_short_lines(self):
        """Lines ≤ 5 chars are filtered out."""
        llm_text = "1. OK\n2. Include a proper reproducibility statement\n3. Hi\n"
        llm = AsyncMock()
        resp = MagicMock()
        resp.content = llm_text
        llm.complete = AsyncMock(return_value=resp)

        session = MagicMock()
        session.llm_client = llm
        console = MagicMock()

        venue = VenueInfo(
            name="neurips", display_name="NeurIPS 2026",
            style_package="neurips_2026",
            camera_ready_option=r"\usepackage[final]{neurips_2026}",
            anonymous_option=r"\usepackage{neurips_2026}",
            page_limit=9, checklist=[],
        )

        cmd = CameraReadyCommand()
        items = await cmd._fetch_venue_checklist(venue, session, console)

        assert len(items) == 1
        assert "reproducibility" in items[0].lower()

    @pytest.mark.asyncio
    async def test_handles_llm_error(self):
        """LLM exception → return [] gracefully."""
        llm = AsyncMock()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

        session = MagicMock()
        session.llm_client = llm
        console = MagicMock()

        venue = VenueInfo(
            name="neurips", display_name="NeurIPS 2026",
            style_package="neurips_2026",
            camera_ready_option=r"\usepackage[final]{neurips_2026}",
            anonymous_option=r"\usepackage{neurips_2026}",
            page_limit=9, checklist=[],
        )

        cmd = CameraReadyCommand()
        items = await cmd._fetch_venue_checklist(venue, session, console)

        assert items == []
        # Should have printed the error
        all_printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "LLM down" in all_printed


class TestVenueChecklistPopulation:
    """Verify that VenueInfo.checklist is populated from VENUE_TEMPLATES."""

    @pytest.mark.parametrize("venue_key", list(VENUE_TEMPLATES.keys()))
    def test_every_venue_has_checklist(self, venue_key: str):
        tmpl = VENUE_TEMPLATES[venue_key]
        assert "checklist" in tmpl
        assert len(tmpl["checklist"]) > 0, f"{venue_key} has empty checklist"

    def test_neurips_checklist_on_venue_info(self):
        preamble = r"\usepackage{neurips_2026}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert len(info.checklist) == 3
        assert any("[final]" in item for item in info.checklist)
        assert any("9-page" in item for item in info.checklist)

    def test_icml_checklist_on_venue_info(self):
        preamble = r"\usepackage{icml2025}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert len(info.checklist) == 3
        assert any("[accepted]" in item for item in info.checklist)

    def test_iclr_checklist_on_venue_info(self):
        preamble = r"\usepackage{iclr2026_conference}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert any("iclrfinalcopy" in item for item in info.checklist)

    def test_cvpr_checklist_on_venue_info(self):
        preamble = r"\usepackage[review]{cvpr}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert any("[review]" in item for item in info.checklist)

    def test_aaai_checklist_on_venue_info(self):
        preamble = r"\usepackage{aaai25}"
        info = _venue_from_preamble(preamble)
        assert info is not None
        assert any("copyright" in item.lower() for item in info.checklist)


class TestVenueChecklistShownToUser:
    """Verify that _show_checklist prints venue-specific items."""

    def _get_printed_text(self, analysis: CameraReadyAnalysis) -> str:
        console = MagicMock()
        cmd = CameraReadyCommand()
        cmd._show_checklist(analysis, console)
        return " ".join(str(call) for call in console.print.call_args_list)

    def test_neurips_checklist_shown(self):
        venue = _venue_from_preamble(r"\usepackage{neurips_2026}")
        analysis = CameraReadyAnalysis(
            venue=venue, is_camera_ready=False, has_final_option=False,
            has_accepted_option=False, has_acknowledgments=False,
            has_todo_markers=False, preamble="", issues=[],
        )
        text = self._get_printed_text(analysis)
        assert "[final]" in text
        assert "9-page" in text

    def test_icml_checklist_shown(self):
        venue = _venue_from_preamble(r"\usepackage{icml2025}")
        analysis = CameraReadyAnalysis(
            venue=venue, is_camera_ready=False, has_final_option=False,
            has_accepted_option=False, has_acknowledgments=False,
            has_todo_markers=False, preamble="", issues=[],
        )
        text = self._get_printed_text(analysis)
        assert "[accepted]" in text
        assert "8-page" in text

    def test_cvpr_checklist_shown(self):
        venue = _venue_from_preamble(r"\usepackage[review]{cvpr}")
        analysis = CameraReadyAnalysis(
            venue=venue, is_camera_ready=False, has_final_option=False,
            has_accepted_option=False, has_acknowledgments=False,
            has_todo_markers=False, preamble="", issues=[],
        )
        text = self._get_printed_text(analysis)
        assert "[review]" in text
        assert "paper ID" in text

    def test_no_venue_still_shows_generic(self):
        analysis = CameraReadyAnalysis(
            venue=None, is_camera_ready=False, has_final_option=False,
            has_accepted_option=False, has_acknowledgments=False,
            has_todo_markers=False, preamble="", issues=[],
        )
        text = self._get_printed_text(analysis)
        assert "page limit" in text.lower()
        assert "figures" in text.lower()


class TestVenueChecklistInLLMPrompt:
    """Verify that the venue checklist reaches the LLM prompt."""

    @pytest.mark.asyncio
    async def test_neurips_structural_checklist_in_prompt(self, tmp_path: Path):
        """NeurIPS structural items must appear in the prompt sent to the LLM."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches needed."
            yield chunk

        main_tex = tmp_path / "main.tex"
        main_tex.write_text(NEURIPS_PAPER)

        session = _make_session(
            NEURIPS_PAPER, venue="NeurIPS 2026",
            llm_response="dummy",
            checklist_response="1. Short\n",  # filtered out (≤5 chars)
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        # Venue name in prompt
        assert "NeurIPS 2026" in prompt
        # NeurIPS structural checklist items in prompt
        assert "[final]" in prompt
        assert "9-page" in prompt

    @pytest.mark.asyncio
    async def test_llm_venue_checklist_items_in_prompt(self, tmp_path: Path):
        """LLM-fetched venue checklist items must appear in the patch prompt."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches needed."
            yield chunk

        main_tex = tmp_path / "main.tex"
        main_tex.write_text(NEURIPS_PAPER)

        session = _make_session(
            NEURIPS_PAPER, venue="NeurIPS 2026",
            llm_response="dummy",
            checklist_response=MOCK_VENUE_CHECKLIST,
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        # LLM-fetched items should be in the patch generation prompt
        assert "reproducibility statement" in prompt.lower()
        assert "supplementary" in prompt.lower()

    @pytest.mark.asyncio
    async def test_icml_checklist_in_prompt(self, tmp_path: Path):
        """ICML-specific items must appear in the prompt sent to the LLM."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches needed."
            yield chunk

        main_tex = tmp_path / "main.tex"
        main_tex.write_text(ICML_PAPER)

        session = _make_session(
            ICML_PAPER, venue="ICML 2025",
            llm_response="dummy",
            checklist_response="1. Short\n",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        assert "ICML 2025" in prompt
        assert "[accepted]" in prompt
        assert "8-page" in prompt

    @pytest.mark.asyncio
    async def test_cvpr_checklist_in_prompt(self, tmp_path: Path):
        """CVPR-specific items must appear in the prompt sent to the LLM."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches needed."
            yield chunk

        main_tex = tmp_path / "main.tex"
        main_tex.write_text(CVPR_PAPER)

        session = _make_session(
            CVPR_PAPER, venue="CVPR 2026",
            llm_response="dummy",
            checklist_response="1. Short\n",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        assert "CVPR 2026" in prompt
        assert "[review]" in prompt
        assert "paper ID" in prompt

    @pytest.mark.asyncio
    async def test_unknown_venue_gets_generic_prompt(self, tmp_path: Path):
        """When venue is unknown, prompt uses 'Unknown venue' with generic checklist."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches needed."
            yield chunk

        generic_paper = r"""
\documentclass{article}
\begin{document}
\section{Introduction}
Content.
\end{document}
"""
        main_tex = tmp_path / "main.tex"
        main_tex.write_text(generic_paper)

        session = _make_session(
            generic_paper, venue="Unknown",
            llm_response="dummy", tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        assert "Unknown venue" in prompt


class TestVenueChecklistEndToEnd:
    """Full end-to-end: venue detected → checklist fetched → shown → in prompt."""

    @pytest.mark.asyncio
    async def test_neurips_full_flow(self, tmp_path: Path):
        """For a NeurIPS paper: detect venue, fetch checklist, show, send to LLM."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches."
            yield chunk

        main_tex = tmp_path / "main.tex"
        main_tex.write_text(NEURIPS_PAPER)

        # Use "Unknown" venue so it falls through to preamble detection
        session = _make_session(
            NEURIPS_PAPER, venue="Unknown",
            llm_response="dummy",
            checklist_response=MOCK_VENUE_CHECKLIST,
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        all_printed = " ".join(str(c) for c in console.print.call_args_list)

        # 1. Venue was auto-detected
        assert "Auto-detected venue" in all_printed
        assert "NEURIPS" in all_printed

        # 2. Structural checklist was shown to user
        assert "[final]" in all_printed
        assert "9-page" in all_printed

        # 3. LLM-fetched checklist items were shown
        assert "reproducibility" in all_printed.lower()
        assert "supplementary" in all_printed.lower()

        # 4. Prompt was sent to LLM with venue-specific items
        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        assert "NEURIPS" in prompt
        assert "[final]" in prompt
        # LLM-fetched items also in the patch prompt
        assert "reproducibility" in prompt.lower()

    @pytest.mark.asyncio
    async def test_aaai_full_flow(self, tmp_path: Path):
        """For an AAAI paper: detect venue, show AAAI-specific checklist."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches."
            yield chunk

        main_tex = tmp_path / "main.tex"
        main_tex.write_text(AAAI_PAPER)

        session = _make_session(
            AAAI_PAPER, venue="Unknown",
            llm_response="dummy",
            checklist_response="1. Include AAAI copyright notice on first page\n",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        all_printed = " ".join(str(c) for c in console.print.call_args_list)

        # Venue detected
        assert "AAAI" in all_printed

        # AAAI-specific structural checklist shown
        assert "copyright" in all_printed.lower()
        assert "7-page" in all_printed

        # Prompt has AAAI items
        assert len(captured_prompt) == 1
        assert "copyright" in captured_prompt[0].lower()
        assert "7-page" in captured_prompt[0]


# ---------------------------------------------------------------------------
# Tests: Real-world paper simulations (esolang / position paper)
# ---------------------------------------------------------------------------

# Realistic ICML paper structure (mirrors examples/esolang_paper)
ICML_REALISTIC_PAPER = r"""
\documentclass{article}
\usepackage{microtype}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\newcommand{\theHalgorithm}{\arabic{algorithm}}
\usepackage{icml2026}
\usepackage{amsmath}
\usepackage[capitalize,noabbrev]{cleveref}
\icmltitlerunning{EsoLang-Bench: Evaluating LLMs via Esoteric Languages}
\begin{document}
\twocolumn[
  \icmltitle{EsoLang-Bench: Evaluating Genuine Reasoning in Large Language Models \\ via Esoteric Programming Languages}
  \icmlsetsymbol{equal}{*}
  \begin{icmlauthorlist}
    \icmlauthor{Anonymous Author(s)}{anon}
  \end{icmlauthorlist}
  \icmlaffiliation{anon}{Anonymous Institution}
  \icmlcorrespondingauthor{Anonymous Author(s)}{anonymous@example.com}
  \icmlkeywords{LLMs, Benchmarks, Esoteric Languages}
  \vskip 0.3in
]
\printAffiliationsAndNotice{}
\begin{abstract}
We introduce EsoLang-Bench, a benchmark using esoteric programming
languages to evaluate genuine reasoning in LLMs.
\end{abstract}
\section{Introduction}
Large language models achieve impressive performance.
\section{Method}
Our method involves five esoteric languages.
\section{Results}
Models score 0-11\% on esoteric tasks.
\section{Limitations}
Our evaluation is limited to five languages.
\section*{Reproducibility Statement}
We will open-source our code and data.
\bibliography{esolang_bench}
\end{document}
"""


class TestRealWorldICMLPaper:
    """Tests simulating the real esolang and position papers from examples/."""

    def setup_method(self):
        self.cmd = CameraReadyCommand()

    # -- Venue resolution --

    def test_icml_venue_from_paper_spec(self):
        """paper_spec.venue = 'ICML 2026' resolves correctly."""
        preamble = _extract_preamble(ICML_REALISTIC_PAPER)
        info = _venue_from_spec("ICML 2026", preamble)
        assert info is not None
        assert info.name == "icml"
        assert info.display_name == "ICML 2026"
        assert info.style_package == "icml2026"
        assert info.camera_ready_option == r"\usepackage[accepted]{icml2026}"
        assert info.page_limit == 8

    # -- Analysis --

    def test_analysis_detects_missing_accepted(self):
        """Paper with \\usepackage{icml2026} (no [accepted]) is not camera-ready."""
        venue = _venue_from_spec(
            "ICML 2026", _extract_preamble(ICML_REALISTIC_PAPER),
        )
        analysis = self.cmd._analyze_submission(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, venue,
        )
        assert analysis.is_camera_ready is False
        assert analysis.has_accepted_option is False
        assert any("camera-ready" in i.lower() for i in analysis.issues)

    def test_analysis_no_acknowledgments(self):
        """Realistic ICML paper has no acknowledgments section."""
        analysis = self.cmd._analyze_submission(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, venue=None,
        )
        assert analysis.has_acknowledgments is False
        assert any("acknowledgments" in i.lower() for i in analysis.issues)

    def test_analysis_no_false_positive_on_prose_final(self):
        """'In the final analysis' in body doesn't trigger camera-ready detection."""
        paper = ICML_REALISTIC_PAPER.replace(
            r"Models score 0-11\% on esoteric tasks.",
            r"In the final analysis, models score only 0-11\%.",
        )
        analysis = self.cmd._analyze_submission(paper, paper, venue=None)
        assert analysis.has_final_option is False
        assert analysis.is_camera_ready is False

    def test_analysis_with_accepted_option(self):
        """Paper with [accepted] is detected as camera-ready."""
        paper = ICML_REALISTIC_PAPER.replace(
            r"\usepackage{icml2026}",
            r"\usepackage[accepted]{icml2026}",
        )
        analysis = self.cmd._analyze_submission(paper, paper, venue=None)
        assert analysis.has_accepted_option is True
        assert analysis.is_camera_ready is True

    # -- Targeted content --

    def test_targeted_content_includes_title(self):
        """Targeted content must include the paper title."""
        analysis = self.cmd._analyze_submission(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, analysis,
        )
        assert "EsoLang-Bench" in targeted

    def test_targeted_content_includes_abstract(self):
        """Targeted content must include the abstract."""
        analysis = self.cmd._analyze_submission(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, analysis,
        )
        assert "%%% ABSTRACT %%%" in targeted
        assert "esoteric programming" in targeted.lower()

    def test_targeted_content_includes_author_block(self):
        """Targeted content captures icmlauthor and icmlaffiliation."""
        analysis = self.cmd._analyze_submission(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, analysis,
        )
        assert "icmlauthor" in targeted
        assert "icmlaffiliation" in targeted

    def test_targeted_content_includes_end_of_document(self):
        """Last 50 lines before \\end{document} are captured."""
        analysis = self.cmd._analyze_submission(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, analysis,
        )
        assert "%%% END OF DOCUMENT" in targeted

    def test_targeted_content_includes_section_headings(self):
        """Section headings index prevents duplicate stub generation."""
        analysis = self.cmd._analyze_submission(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            ICML_REALISTIC_PAPER, ICML_REALISTIC_PAPER, analysis,
        )
        assert "%%% SECTION HEADINGS" in targeted
        assert "Reproducibility" in targeted
        assert "Limitations" in targeted
        assert "Introduction" in targeted

    # -- Prompt includes filename --

    @pytest.mark.asyncio
    async def test_prompt_includes_actual_filename(self, tmp_path: Path):
        """The LLM prompt must include the actual tex filename, not 'main.tex'."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches."
            yield chunk

        main_tex = tmp_path / "esolang_bench_paper.tex"
        main_tex.write_text(ICML_REALISTIC_PAPER)

        session = _make_session(
            ICML_REALISTIC_PAPER, venue="ICML 2026",
            llm_response="dummy",
            checklist_response="1. Short\n",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        # Must contain the real filename
        assert "esolang_bench_paper.tex" in prompt
        # Must NOT say "main.tex" (unless the file is actually named that)
        assert "main.tex" not in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_diff_format_example(self, tmp_path: Path):
        """The LLM prompt must include a diff format example with correct filename."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches."
            yield chunk

        main_tex = tmp_path / "position_paper.tex"
        main_tex.write_text(ICML_REALISTIC_PAPER)

        session = _make_session(
            ICML_REALISTIC_PAPER, venue="ICML 2026",
            llm_response="dummy",
            checklist_response="1. Short\n",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        prompt = captured_prompt[0]
        assert "--- a/position_paper.tex" in prompt
        assert "+++ b/position_paper.tex" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_camera_ready_option(self, tmp_path: Path):
        """The prompt must include the specific camera-ready option for the venue."""
        captured_prompt = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches."
            yield chunk

        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_REALISTIC_PAPER)

        session = _make_session(
            ICML_REALISTIC_PAPER, venue="ICML 2026",
            llm_response="dummy",
            checklist_response="1. Short\n",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = CameraReadyCommand()
        await cmd.execute(session, "", console)

        prompt = captured_prompt[0]
        # Must include the specific option, not generic "[final], [accepted]"
        assert r"\usepackage[accepted]{icml2026}" in prompt

    # -- Venue detection: bibliography false positive --

    def test_bibliography_icml_not_matched(self):
        """\\bibliography{icml_refs} in body must NOT match ICML venue."""
        content = r"""
\documentclass{article}
\begin{document}
\section{Intro}
Content.
\bibliography{icml_refs}
\end{document}
"""
        preamble = _extract_preamble(content)
        info = _venue_from_preamble(preamble)
        assert info is None

    # -- Patch filename matching --

    @pytest.mark.asyncio
    async def test_patches_use_correct_filename(self, tmp_path: Path):
        """Patches generated by the LLM must reference the actual filename."""
        # Simulate LLM generating a patch with the correct filename
        llm_patch = r"""```diff
--- a/esolang_bench_paper.tex
+++ b/esolang_bench_paper.tex
@@ -7,1 +7,1 @@
-\usepackage{icml2026}
+\usepackage[accepted]{icml2026}
```
"""
        main_tex = tmp_path / "esolang_bench_paper.tex"
        main_tex.write_text(ICML_REALISTIC_PAPER)

        session = _make_session(
            ICML_REALISTIC_PAPER, venue="ICML 2026",
            llm_response=llm_patch,
            checklist_response="1. Short\n",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = CameraReadyCommand()

        with patch(
            "texguardian.cli.approval.interactive_approval",
            new_callable=AsyncMock,
            return_value=1,
        ) as mock_approval:
            await cmd.execute(session, "", console)

        # Verify interactive_approval was called with patches
        assert mock_approval.called
        patches = mock_approval.call_args[0][0]
        assert len(patches) == 1
        assert patches[0].file_path == "esolang_bench_paper.tex"

    @pytest.mark.asyncio
    async def test_wrong_filename_still_extracts_patch(self, tmp_path: Path):
        """If LLM uses wrong filename, patch still parses but will target wrong file."""
        # This tests the failure mode: LLM guesses "main.tex"
        llm_patch = r"""```diff
--- a/main.tex
+++ b/main.tex
@@ -7,1 +7,1 @@
-\usepackage{icml2026}
+\usepackage[accepted]{icml2026}
```
"""
        main_tex = tmp_path / "esolang_bench_paper.tex"
        main_tex.write_text(ICML_REALISTIC_PAPER)

        session = _make_session(
            ICML_REALISTIC_PAPER, venue="ICML 2026",
            llm_response=llm_patch,
            checklist_response="1. Short\n",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = CameraReadyCommand()

        with patch(
            "texguardian.cli.approval.interactive_approval",
            new_callable=AsyncMock,
            return_value=0,
        ) as mock_approval:
            await cmd.execute(session, "", console)

        # Patch parsed but with wrong filename
        patches = mock_approval.call_args[0][0]
        assert len(patches) == 1
        # This would be "main.tex", not the actual file — our prompt fix
        # should prevent this by telling the LLM the correct filename
        assert patches[0].file_path == "main.tex"


# ---------------------------------------------------------------------------
# Tests: Live paper from examples/ directory (reads files from disk)
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
ESOLANG_TEX = EXAMPLES_DIR / "esolang_paper" / "esolang_bench_paper.tex"
POSITION_TEX = EXAMPLES_DIR / "position_paper" / "position_paper.tex"


@pytest.mark.skipif(
    not ESOLANG_TEX.exists(),
    reason="examples/esolang_paper not present",
)
class TestLiveEsolangPaper:
    """Run analysis on the actual 1310-line esolang paper from examples/."""

    def setup_method(self):
        self.cmd = CameraReadyCommand()
        self.content = ESOLANG_TEX.read_text()
        self.full_content = _resolve_full_content(ESOLANG_TEX)
        self.preamble = _extract_preamble(self.content)

    def test_venue_detected_from_preamble(self):
        info = _venue_from_preamble(self.preamble)
        assert info is not None
        assert info.name == "icml"
        assert info.style_package == "icml2026"

    def test_venue_detected_from_spec(self):
        info = _venue_from_spec("ICML 2026", self.preamble)
        assert info is not None
        assert info.camera_ready_option == r"\usepackage[accepted]{icml2026}"

    def test_not_camera_ready(self):
        """The example paper uses \\usepackage{icml2026} (no [accepted])."""
        venue = _venue_from_preamble(self.preamble)
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue,
        )
        assert analysis.is_camera_ready is False
        assert analysis.has_final_option is False
        assert analysis.has_accepted_option is False

    def test_has_no_acknowledgments(self):
        """Esolang paper has no acknowledgments section."""
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        assert analysis.has_acknowledgments is False

    def test_has_no_todo_markers(self):
        """Esolang paper should not have TODO markers."""
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        assert analysis.has_todo_markers is False

    def test_targeted_content_has_title(self):
        """Title 'EsoLang-Bench' must appear in targeted content."""
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            self.content, self.full_content, analysis,
        )
        assert "EsoLang-Bench" in targeted

    def test_targeted_content_has_abstract(self):
        """Abstract mentioning 'esoteric programming languages' must appear."""
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            self.content, self.full_content, analysis,
        )
        assert "%%% ABSTRACT %%%" in targeted
        assert "esoteric programming languages" in targeted.lower()

    def test_targeted_content_has_reproducibility_in_headings(self):
        """Reproducibility Statement must appear in section headings index."""
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            self.content, self.full_content, analysis,
        )
        assert "%%% SECTION HEADINGS" in targeted
        assert "Reproducibility" in targeted

    def test_targeted_content_not_full_paper(self):
        """Targeted content should be significantly shorter than the full paper."""
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            self.content, self.full_content, analysis,
        )
        # A 1310-line paper should produce targeted content that is
        # substantially smaller (preamble + title + abstract + last 50 lines)
        assert len(targeted) < len(self.content) * 0.5

    def test_preamble_only_detection(self):
        """\\bibliography{esolang_bench} in body must NOT trigger venue detection."""
        # The real paper has \\bibliography{esolang_bench} — verify it's in the body
        assert r"\bibliography{esolang_bench}" in self.content
        # Preamble detection should still work via the \\usepackage
        info = _venue_from_preamble(self.preamble)
        assert info is not None
        assert info.name == "icml"


@pytest.mark.skipif(
    not POSITION_TEX.exists(),
    reason="examples/position_paper not present",
)
class TestLivePositionPaper:
    """Run analysis on the actual position paper from examples/."""

    def setup_method(self):
        self.cmd = CameraReadyCommand()
        self.content = POSITION_TEX.read_text()
        self.full_content = _resolve_full_content(POSITION_TEX)
        self.preamble = _extract_preamble(self.content)

    def test_venue_detected(self):
        info = _venue_from_preamble(self.preamble)
        assert info is not None
        assert info.name == "icml"

    def test_not_camera_ready(self):
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        assert analysis.is_camera_ready is False

    def test_targeted_content_has_title(self):
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            self.content, self.full_content, analysis,
        )
        # Position paper title contains "Benchmark Gaming"
        assert "Benchmark Gaming" in targeted or "Position" in targeted

    def test_targeted_content_has_abstract(self):
        analysis = self.cmd._analyze_submission(
            self.content, self.full_content, venue=None,
        )
        targeted = self.cmd._build_targeted_content(
            self.content, self.full_content, analysis,
        )
        assert "%%% ABSTRACT %%%" in targeted

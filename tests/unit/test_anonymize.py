"""Tests for the /anonymize command."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from texguardian.cli.commands.anonymize import (
    ANONYMIZE_PROMPT,
    IDENTIFYING_PATTERNS,
    VENUE_ANONYMOUS,
    AnonymizeCommand,
)


# ---------------------------------------------------------------------------
# Test fixtures — realistic paper content
# ---------------------------------------------------------------------------

ICML_PAPER_WITH_AUTHORS = r"""
\documentclass{article}
\usepackage{icml2026}
\begin{document}
\twocolumn[
  \icmltitle{My Great Paper}
  \begin{icmlauthorlist}
    \icmlauthor{John Doe}{mit}
    \icmlauthor{Jane Smith}{stanford}
  \end{icmlauthorlist}
  \icmlaffiliation{mit}{MIT, Cambridge, MA}
  \icmlaffiliation{stanford}{Stanford University}
  \icmlcorrespondingauthor{John Doe}{john@mit.edu}
]
\begin{abstract}
This is our paper about great things.
\end{abstract}
\section{Introduction}
In our previous work \cite{doe2024}, we showed that...
\section*{Acknowledgments}
We thank the NSF for funding (grant \#1234567).
We also thank Prof. Alice for helpful discussions.
\bibliography{refs}
\end{document}
"""

ICML_PAPER_ANONYMOUS = r"""
\documentclass{article}
\usepackage{icml2026}
\begin{document}
\twocolumn[
  \icmltitle{My Great Paper}
  \begin{icmlauthorlist}
    \icmlauthor{Anonymous Author(s)}{anon}
  \end{icmlauthorlist}
  \icmlaffiliation{anon}{Anonymous Institution}
]
\begin{abstract}
This paper presents results.
\end{abstract}
\section{Introduction}
Content here.
\end{document}
"""

NEURIPS_PAPER_WITH_AUTHORS = r"""
\documentclass{article}
\usepackage[final]{neurips_2026}
\begin{document}
\title{Neural Network Study}
\author{Alice Bob \\ MIT \\ alice@mit.edu}
\maketitle
\begin{abstract}
A study on neural networks.
\end{abstract}
\section{Introduction}
As we showed in \cite{bob2023}, the results are...
\section*{Acknowledgments}
This work was supported by Google Research.
\end{document}
"""

STANDARD_PAPER = r"""
\documentclass{article}
\begin{document}
\title{Generic Paper}
\author{Bob Jones \\ Harvard}
\maketitle
\section{Introduction}
Results here.
\email{bob@harvard.edu}
\end{document}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_streaming_llm(
    stream_response: str,
) -> AsyncMock:
    """Create a mock LLM that supports both stream() and complete()."""
    llm = AsyncMock()

    async def _fake_stream(**kwargs):
        chunk = MagicMock()
        chunk.content = stream_response
        yield chunk

    llm.stream = _fake_stream

    resp = MagicMock()
    resp.content = stream_response
    llm.complete = AsyncMock(return_value=resp)

    return llm


def _make_session(
    content: str,
    *,
    llm_response: str = "",
    tmp_path: Path | None = None,
) -> Any:
    """Create a mock session for testing."""
    session = MagicMock()

    if tmp_path:
        main_tex = tmp_path / "main.tex"
        main_tex.write_text(content)
        session.main_tex_path = main_tex
        session.project_root = tmp_path
        session.guardian_dir = tmp_path / ".texguardian"
    else:
        session.main_tex_path = MagicMock()
        session.main_tex_path.exists.return_value = True
        session.main_tex_path.read_text.return_value = content
        session.main_tex_path.name = "main.tex"
        session.project_root = Path("/fake")

    session.paper_spec = MagicMock()
    session.paper_spec.venue = "Unknown"

    session.context = MagicMock()
    session.config = MagicMock()
    session.config.safety = MagicMock()

    if llm_response:
        session.llm_client = _make_streaming_llm(llm_response)
    else:
        session.llm_client = None

    return session


# ---------------------------------------------------------------------------
# Tests: Identifying patterns
# ---------------------------------------------------------------------------


class TestIdentifyingPatterns:
    """Verify IDENTIFYING_PATTERNS detect various author/affiliation formats."""

    def setup_method(self):
        self.cmd = AnonymizeCommand()

    def test_detects_standard_author(self):
        content = r"\author{John Doe}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is False
        assert any(f["type"] == "author" for f in analysis["findings"])

    def test_detects_icml_author(self):
        """\\icmlauthor must be detected (was missing before fix)."""
        content = r"\icmlauthor{John Doe}{mit}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is False
        assert any(f["type"] == "author" for f in analysis["findings"])

    def test_detects_icml_corresponding_author(self):
        content = r"\icmlcorrespondingauthor{John Doe}{john@mit.edu}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is False
        assert any(f["type"] == "author" for f in analysis["findings"])

    def test_detects_icml_affiliation(self):
        content = r"\icmlaffiliation{mit}{MIT, Cambridge, MA}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is False
        assert any(f["type"] == "affiliation" for f in analysis["findings"])

    def test_anonymous_author_not_flagged(self):
        content = r"\author{Anonymous}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is True

    def test_anonymous_icml_author_not_flagged(self):
        content = r"\icmlauthor{Anonymous Author(s)}{anon}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is True

    def test_anonymous_icml_affiliation_not_flagged(self):
        content = r"\icmlaffiliation{anon}{Anonymous Institution}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is True

    def test_detects_email(self):
        content = r"\email{john@example.com}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is False
        assert any(f["type"] == "email" for f in analysis["findings"])

    def test_detects_orcid(self):
        content = r"\orcid{0000-0001-2345-6789}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is False

    def test_detects_thanks(self):
        content = r"\thanks{Funded by NSF grant 1234567}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["is_anonymous"] is False

    def test_detects_acknowledgments(self):
        content = r"\section*{Acknowledgments}" + "\nWe thank everyone.\n" + r"\section{References}"
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["has_acknowledgments"] is True
        assert analysis["is_anonymous"] is False

    def test_commented_acknowledgments_not_flagged(self):
        content = r"% \section*{Acknowledgments}" + "\n% We thank everyone."
        analysis = self.cmd._analyze_identifying_info(content)
        assert analysis["has_acknowledgments"] is False

    def test_detects_self_citations(self):
        content = "In our previous work, we showed that..."
        analysis = self.cmd._analyze_identifying_info(content)
        assert len(analysis["self_citations"]) > 0
        assert analysis["is_anonymous"] is False

    def test_full_icml_paper_with_authors_detected(self):
        """Full ICML paper with real names must be flagged as non-anonymous."""
        analysis = self.cmd._analyze_identifying_info(ICML_PAPER_WITH_AUTHORS)
        assert analysis["is_anonymous"] is False
        types = [f["type"] for f in analysis["findings"]]
        assert "author" in types
        assert "affiliation" in types
        assert analysis["has_acknowledgments"] is True
        assert len(analysis["self_citations"]) > 0

    def test_full_icml_anonymous_paper_passes(self):
        """ICML paper with Anonymous authors should pass."""
        analysis = self.cmd._analyze_identifying_info(ICML_PAPER_ANONYMOUS)
        assert analysis["is_anonymous"] is True


# ---------------------------------------------------------------------------
# Tests: Venue detection
# ---------------------------------------------------------------------------


class TestVenueDetection:

    def test_detects_icml(self):
        assert AnonymizeCommand._detect_venue(ICML_PAPER_WITH_AUTHORS) == "icml"

    def test_detects_neurips(self):
        assert AnonymizeCommand._detect_venue(NEURIPS_PAPER_WITH_AUTHORS) == "neurips"

    def test_preamble_only(self):
        """\\bibliography{icml_stuff} in body must NOT trigger icml detection."""
        content = r"""
\documentclass{article}
\begin{document}
\bibliography{icml_refs}
\end{document}
"""
        assert AnonymizeCommand._detect_venue(content) is None

    def test_no_venue(self):
        assert AnonymizeCommand._detect_venue(STANDARD_PAPER) is None

    def test_cvpr_detected(self):
        content = r"""
\documentclass{article}
\usepackage[review]{cvpr}
\begin{document}
\end{document}
"""
        assert AnonymizeCommand._detect_venue(content) == "cvpr"


# ---------------------------------------------------------------------------
# Tests: Targeted content
# ---------------------------------------------------------------------------


class TestBuildTargetedContent:

    def test_includes_preamble(self):
        targeted = AnonymizeCommand._build_targeted_content(
            ICML_PAPER_WITH_AUTHORS, ICML_PAPER_WITH_AUTHORS,
        )
        assert "%%% PREAMBLE %%%" in targeted
        assert r"\usepackage{icml2026}" in targeted

    def test_includes_author_block(self):
        targeted = AnonymizeCommand._build_targeted_content(
            ICML_PAPER_WITH_AUTHORS, ICML_PAPER_WITH_AUTHORS,
        )
        assert "%%% AUTHOR / AFFILIATION REGION %%%" in targeted
        assert "icmlauthor" in targeted

    def test_includes_acknowledgments(self):
        targeted = AnonymizeCommand._build_targeted_content(
            ICML_PAPER_WITH_AUTHORS, ICML_PAPER_WITH_AUTHORS,
        )
        assert "%%% ACKNOWLEDGMENTS REGION %%%" in targeted
        assert "NSF" in targeted

    def test_includes_section_headings(self):
        targeted = AnonymizeCommand._build_targeted_content(
            ICML_PAPER_WITH_AUTHORS, ICML_PAPER_WITH_AUTHORS,
        )
        assert "%%% SECTION HEADINGS" in targeted
        assert "Introduction" in targeted

    def test_includes_end_of_document(self):
        targeted = AnonymizeCommand._build_targeted_content(
            ICML_PAPER_WITH_AUTHORS, ICML_PAPER_WITH_AUTHORS,
        )
        assert "%%% END OF DOCUMENT" in targeted

    def test_includes_email_lines(self):
        """Lines with email addresses should be captured for anonymization."""
        content = r"""
\documentclass{article}
\begin{document}
\author{John Doe}
Some content.
Contact: john@mit.edu for details.
\end{document}
"""
        targeted = AnonymizeCommand._build_targeted_content(content, content)
        assert "%%% LINES WITH URLS/EMAILS %%%" in targeted
        assert "john@mit.edu" in targeted

    def test_includes_github_urls(self):
        content = r"""
\documentclass{article}
\begin{document}
Code at \url{https://github.com/johndoe/myproject}
\end{document}
"""
        targeted = AnonymizeCommand._build_targeted_content(content, content)
        assert "%%% LINES WITH URLS/EMAILS %%%" in targeted
        assert "github.com" in targeted

    def test_ack_detected_in_full_content(self):
        """Acknowledgments in \\input'd file must be found via full_content."""
        main = r"""
\documentclass{article}
\begin{document}
\section{Intro}
\input{ack}
\end{document}
"""
        full = r"""
\documentclass{article}
\begin{document}
\section{Intro}
\input{ack}
\section*{Acknowledgments}
We thank NSF.
\end{document}
"""
        targeted = AnonymizeCommand._build_targeted_content(main, full)
        assert "%%% ACKNOWLEDGMENTS REGION %%%" in targeted
        assert "NSF" in targeted


# ---------------------------------------------------------------------------
# Tests: Prompt quality
# ---------------------------------------------------------------------------


class TestPromptQuality:

    @pytest.mark.asyncio
    async def test_prompt_includes_filename(self, tmp_path: Path):
        """Prompt must include the actual filename."""
        captured_prompt: list[str] = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches needed."
            yield chunk

        main_tex = tmp_path / "esolang_bench_paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            llm_response="dummy",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        assert len(captured_prompt) == 1
        prompt = captured_prompt[0]
        assert "esolang_bench_paper.tex" in prompt
        assert "--- a/esolang_bench_paper.tex" in prompt
        assert "+++ b/esolang_bench_paper.tex" in prompt

    @pytest.mark.asyncio
    async def test_prompt_includes_venue_instructions(self, tmp_path: Path):
        """ICML venue instructions must include author template."""
        captured_prompt: list[str] = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches needed."
            yield chunk

        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            llm_response="dummy",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        prompt = captured_prompt[0]
        assert "ICML" in prompt
        assert r"\icmlauthor{Anonymous}{anon}" in prompt

    @pytest.mark.asyncio
    async def test_prompt_has_diff_format_example(self, tmp_path: Path):
        """Prompt must show the expected diff format."""
        captured_prompt: list[str] = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches needed."
            yield chunk

        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            llm_response="dummy",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        prompt = captured_prompt[0]
        assert "```diff" in prompt
        assert "--- a/paper.tex" in prompt


# ---------------------------------------------------------------------------
# Tests: Execute flow
# ---------------------------------------------------------------------------


class TestExecuteFlow:

    @pytest.mark.asyncio
    async def test_already_anonymous_skips_llm(self, tmp_path: Path):
        """If paper is already anonymous, should not call LLM."""
        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_ANONYMOUS)

        session = _make_session(
            ICML_PAPER_ANONYMOUS,
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client = None  # No LLM needed

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        all_printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "already be anonymous" in all_printed

    @pytest.mark.asyncio
    async def test_no_llm_shows_error(self, tmp_path: Path):
        """Non-anonymous paper + no LLM → show error message."""
        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client = None

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        all_printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "LLM client not available" in all_printed

    @pytest.mark.asyncio
    async def test_saves_response_to_context(self, tmp_path: Path):
        """LLM response must be saved to context for /approve."""
        llm_response = "No patches."

        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            llm_response=llm_response,
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        session.context.add_assistant_message.assert_called_once_with(
            llm_response,
        )

    @pytest.mark.asyncio
    async def test_patches_go_through_interactive_approval(self, tmp_path: Path):
        """When LLM produces patches, interactive_approval must be called."""
        llm_response = r"""```diff
--- a/paper.tex
+++ b/paper.tex
@@ -7,2 +7,2 @@
-    \icmlauthor{John Doe}{mit}
+    \icmlauthor{Anonymous}{anon}
```
"""
        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            llm_response=llm_response,
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = AnonymizeCommand()

        with patch(
            "texguardian.cli.approval.interactive_approval",
            new_callable=AsyncMock,
            return_value=1,
        ) as mock_approval:
            await cmd.execute(session, "", console)

        assert mock_approval.called
        patches = mock_approval.call_args[0][0]
        assert len(patches) == 1
        assert patches[0].file_path == "paper.tex"

    @pytest.mark.asyncio
    async def test_single_step_no_args_needed(self, tmp_path: Path):
        """Command runs full flow without needing 'apply' argument."""
        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            llm_response="No patches.",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = AnonymizeCommand()

        # args="" (no argument) — should still generate patches
        await cmd.execute(session, "", console)

        all_printed = " ".join(str(c) for c in console.print.call_args_list)
        # Should NOT say "Run '/anonymize apply'"
        assert "anonymize apply" not in all_printed
        # Should show generating message
        assert "Generating" in all_printed

    @pytest.mark.asyncio
    async def test_venue_detected_and_shown(self, tmp_path: Path):
        """Venue should be detected and displayed to user."""
        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            llm_response="No patches.",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        all_printed = " ".join(str(c) for c in console.print.call_args_list)
        assert "ICML" in all_printed


# ---------------------------------------------------------------------------
# Tests: Live papers from examples/ directory
# ---------------------------------------------------------------------------

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
ESOLANG_TEX = EXAMPLES_DIR / "esolang_paper" / "esolang_bench_paper.tex"
POSITION_TEX = EXAMPLES_DIR / "position_paper" / "position_paper.tex"


@pytest.mark.skipif(
    not ESOLANG_TEX.exists(),
    reason="examples/esolang_paper not present",
)
class TestLiveEsolangPaper:
    """Run anonymize analysis against the real esolang paper."""

    def setup_method(self):
        self.cmd = AnonymizeCommand()
        self.content = ESOLANG_TEX.read_text()

    def test_already_anonymous(self):
        """Esolang paper has Anonymous Author(s) — should be anonymous."""
        analysis = self.cmd._analyze_identifying_info(self.content)
        # The paper uses Anonymous Author(s) for icmlauthor/affiliation
        assert analysis["is_anonymous"] is True

    def test_venue_is_icml(self):
        assert AnonymizeCommand._detect_venue(self.content) == "icml"

    def test_targeted_content_has_author_block(self):
        targeted = AnonymizeCommand._build_targeted_content(
            self.content, self.content,
        )
        assert "icmlauthor" in targeted

    def test_targeted_content_has_section_headings(self):
        targeted = AnonymizeCommand._build_targeted_content(
            self.content, self.content,
        )
        assert "%%% SECTION HEADINGS" in targeted


@pytest.mark.skipif(
    not POSITION_TEX.exists(),
    reason="examples/position_paper not present",
)
class TestLivePositionPaper:

    def setup_method(self):
        self.cmd = AnonymizeCommand()
        self.content = POSITION_TEX.read_text()

    def test_already_anonymous(self):
        """Position paper has Anonymous Author(s) — should be anonymous."""
        analysis = self.cmd._analyze_identifying_info(self.content)
        assert analysis["is_anonymous"] is True

    def test_venue_is_icml(self):
        assert AnonymizeCommand._detect_venue(self.content) == "icml"


# ---------------------------------------------------------------------------
# Tests: VENUE_ANONYMOUS is actually used
# ---------------------------------------------------------------------------


class TestVenueAnonymousUsed:
    """Verify VENUE_ANONYMOUS entries appear in the prompt."""

    def test_all_venues_have_required_keys(self):
        for venue, info in VENUE_ANONYMOUS.items():
            assert "camera_ready_pattern" in info, f"{venue} missing camera_ready_pattern"
            assert "anonymous_replacement" in info, f"{venue} missing anonymous_replacement"
            assert "author_template" in info, f"{venue} missing author_template"

    @pytest.mark.asyncio
    async def test_icml_venue_info_in_prompt(self, tmp_path: Path):
        captured_prompt: list[str] = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches."
            yield chunk

        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(ICML_PAPER_WITH_AUTHORS)

        session = _make_session(
            ICML_PAPER_WITH_AUTHORS,
            llm_response="dummy",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        prompt = captured_prompt[0]
        # VENUE_ANONYMOUS["icml"] info must appear
        assert r"\icmlauthor{Anonymous}{anon}" in prompt
        assert "accepted" in prompt.lower()

    @pytest.mark.asyncio
    async def test_unknown_venue_gets_generic(self, tmp_path: Path):
        captured_prompt: list[str] = []

        async def _capture_stream(**kwargs):
            captured_prompt.append(kwargs["messages"][0]["content"])
            chunk = MagicMock()
            chunk.content = "No patches."
            yield chunk

        main_tex = tmp_path / "paper.tex"
        main_tex.write_text(STANDARD_PAPER)

        session = _make_session(
            STANDARD_PAPER,
            llm_response="dummy",
            tmp_path=tmp_path,
        )
        session.main_tex_path = main_tex
        session.llm_client.stream = _capture_stream

        console = MagicMock()
        cmd = AnonymizeCommand()
        await cmd.execute(session, "", console)

        prompt = captured_prompt[0]
        assert "No venue-specific instructions" in prompt
        assert r"\author{Anonymous}" in prompt

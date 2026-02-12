"""Camera-ready conversion command.

Single end-to-end flow: detect venue → ask LLM for venue checklist →
analyse submission → show merged checklist → generate patches via LLM →
interactive approval → apply.

De-anonymization is out of scope — handled separately via /anonymize.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from rich.table import Table

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class VenueInfo:
    """Resolved venue information."""

    name: str                    # e.g. "neurips"
    display_name: str            # e.g. "NeurIPS 2026"
    style_package: str           # e.g. "neurips_2026"
    camera_ready_option: str     # e.g. "\\usepackage[final]{neurips_2026}"
    anonymous_option: str        # e.g. "\\usepackage{neurips_2026}"
    page_limit: int | None       # e.g. 9
    checklist: list[str]         # structural items from VENUE_TEMPLATES


@dataclass
class CameraReadyAnalysis:
    """Result of analysing a submission for camera-ready readiness."""

    venue: VenueInfo | None
    is_camera_ready: bool        # already in final mode?
    has_final_option: bool       # \usepackage[final]{…} present in preamble?
    has_accepted_option: bool    # \usepackage[accepted]{…} present in preamble?
    has_acknowledgments: bool
    has_todo_markers: bool
    preamble: str                # content before \begin{document}
    issues: list[str] = field(default_factory=list)
    # LLM-generated venue checklist (fetched at runtime, not hardcoded)
    venue_checklist: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Venue templates — structural items only (year-agnostic)
#
# These cover things we can detect programmatically: package options, page
# limits, etc.  Content requirements (ethics statement, impact statement,
# reproducibility, paper checklist) are NOT hardcoded here — they are
# fetched from the LLM at runtime via _fetch_venue_checklist() because
# they change year-to-year.
# ---------------------------------------------------------------------------

VENUE_TEMPLATES: dict[str, dict] = {
    "neurips": {
        "pattern": r"neurips_?\d{4}",
        "camera_ready": "[final]",
        "page_limit": 9,
        "checklist": [
            "Add [final] option to \\usepackage{neurips_YYYY}",
            "Ensure paper is within 9-page limit (excluding references)",
            "Uncomment acknowledgments section",
        ],
    },
    "iclr": {
        "pattern": r"iclr\d{4}",
        "camera_ready": "\\iclrfinalcopy",
        "page_limit": None,
        "checklist": [
            "Add \\iclrfinalcopy before \\usepackage{iclrYYYY_conference}",
            "Uncomment acknowledgments section",
        ],
    },
    "icml": {
        "pattern": r"icml\d{4}",
        "camera_ready": "[accepted]",
        "page_limit": 8,
        "checklist": [
            "Change to \\usepackage[accepted]{icmlYYYY}",
            "Uncomment acknowledgments",
            "Verify paper is within 8-page limit (excluding references)",
        ],
    },
    "cvpr": {
        "pattern": r"\\usepackage(?:\[[^\]]*\])?\{cvpr\}",
        "camera_ready": "",
        "page_limit": 8,
        "checklist": [
            "Remove [review] option from \\usepackage{cvpr}",
            "Add paper ID in camera-ready",
            "Verify paper is within 8-page limit (excluding references)",
        ],
    },
    "iccv": {
        "pattern": r"\\usepackage(?:\[[^\]]*\])?\{iccv\}",
        "camera_ready": "",
        "page_limit": 8,
        "checklist": [
            "Remove [review] option from \\usepackage{iccv}",
            "Add paper ID in camera-ready",
            "Verify paper is within 8-page limit (excluding references)",
        ],
    },
    "eccv": {
        "pattern": r"\\usepackage(?:\[[^\]]*\])?\{eccv\}",
        "camera_ready": "",
        "page_limit": 14,
        "checklist": [
            "Remove [review] option from \\usepackage{eccv}",
            "Add paper ID in camera-ready",
            "Verify paper is within 14-page limit (excluding references)",
        ],
    },
    "acl": {
        "pattern": r"acl\d{4}|acl_[a-z]|\\usepackage[^}]*\bacl\b",
        "camera_ready": "\\aclfinalcopy",
        "page_limit": 8,
        "checklist": [
            "Add \\aclfinalcopy command",
            "Include acknowledgments section",
            "Verify paper is within 8-page limit (excluding references and appendices)",
        ],
    },
    "aaai": {
        "pattern": r"aaai\d{2,4}",
        "camera_ready": "",
        "page_limit": 7,
        "checklist": [
            "Ensure AAAI copyright block is present",
            "Verify paper is within 7-page limit (excluding references)",
        ],
    },
}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

VENUE_CHECKLIST_PROMPT = """\
You are an expert on academic conference submission requirements.

The user is preparing a camera-ready version of a paper for **{venue}**.

List the **camera-ready specific requirements** for this venue.  Focus on:
- Required sections (ethics statement, broader impact, reproducibility, \
limitations, paper checklist, etc.)
- Formatting rules specific to the camera-ready version
- Any mandatory statements or environments the venue requires
- Supplementary material requirements

Do NOT include generic advice like "proofread" or "check spelling".
Do NOT include de-anonymization — the user handles that separately.
Do NOT include style option changes (\\usepackage[final]) — we handle that.

Return ONLY a numbered list, one requirement per line. No preamble, no \
explanation — just the list.
"""

CAMERA_READY_PROMPT = """\
You are a LaTeX expert preparing a paper for camera-ready submission to {venue}.

## Target File
`{filename}`

## Venue Requirements (from checklist)
{checklist}

## Current State
{analysis_summary}

## Paper Content (targeted sections)
```latex
{targeted_content}
```

## Task
Generate unified diff patches to convert this paper to camera-ready format.

Focus on:
1. Style option: change to `{camera_ready_option}` in the preamble
2. Remove any TODO/FIXME/XXX markers
3. Ensure proper formatting for the {venue} template
4. For any missing venue-required sections from the checklist above, add a \
stub section with a brief placeholder (e.g., \
`\\section*{{Ethics Statement}}\\nTo be completed.`) — do NOT fabricate \
content the authors haven't written

Do NOT modify author names or affiliations — the user handles \
de-anonymization separately.

Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename `{filename}` in the --- and +++ headers. \
Example format:

```diff
--- a/{filename}
+++ b/{filename}
@@ -16,1 +16,1 @@
-\\usepackage{{icml2026}}
+\\usepackage[accepted]{{icml2026}}
```
"""


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------

class CameraReadyCommand(Command):
    """Single end-to-end camera-ready conversion."""

    name = "camera_ready"
    description = "Convert draft to camera-ready version (style options, TODOs, acknowledgments — not de-anonymization)"
    aliases = ["cr", "final"]
    usage = "/camera_ready - Analyse and convert to camera-ready format in one step"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute camera-ready conversion."""
        console.print("[bold cyan]Camera-Ready Conversion[/bold cyan]\n")

        # Read main tex file
        main_tex = session.main_tex_path
        if not main_tex.exists():
            console.print(f"[red]Main tex file not found: {main_tex}[/red]")
            return

        content = main_tex.read_text()

        # Resolve \input/\include to get the full document for analysis.
        full_content = _resolve_full_content(main_tex)

        # 1. Resolve venue
        venue = self._resolve_venue(content, session, console)

        # 2. Ask LLM for venue-specific checklist (the part we can't hardcode)
        venue_checklist = await self._fetch_venue_checklist(venue, session, console)

        # 3. Analyse submission (structural checks only — uses full_content)
        analysis = self._analyze_submission(content, full_content, venue)
        analysis.venue_checklist = venue_checklist

        # 4. Show status table + merged checklist
        self._show_status(analysis, console)
        self._show_checklist(analysis, console)

        # 5. If already camera-ready and LLM found no extra requirements
        if analysis.is_camera_ready and not analysis.issues and not venue_checklist:
            console.print("\n[green]Paper appears camera-ready already.[/green]")
            self._show_next_steps(console)
            return

        # 6. Generate patches via LLM, approve inline, apply
        applied = await self._generate_and_apply_patches(
            content, full_content, analysis, session, console,
        )

        # 7. Show what to do next
        if applied:
            self._show_next_steps(console)
        else:
            console.print(
                "\n[dim]No changes applied. "
                "Fix issues manually or re-run /camera_ready.[/dim]"
            )

    # ------------------------------------------------------------------
    # Venue resolution
    # ------------------------------------------------------------------

    def _resolve_venue(
        self,
        content: str,
        session: SessionState,
        console: Console,
    ) -> VenueInfo | None:
        """Resolve venue from paper_spec or preamble detection.

        Sources checked in priority order:
        1. ``session.paper_spec.venue`` (set via ``/venue``, paper_spec.md
           frontmatter, or edited by the user in chat).
        2. Re-read ``paper_spec.md`` from disk — catches manual edits or
           cases where the in-memory copy is stale.
        3. Preamble regex detection (year-agnostic).
        """
        preamble = _extract_preamble(content)

        # 1. In-memory paper_spec.venue (fastest, usually up-to-date)
        if session.paper_spec and session.paper_spec.venue not in (None, "", "Unknown"):
            venue_info = _venue_from_spec(session.paper_spec.venue, preamble)
            if venue_info:
                console.print(
                    f"[green]✓[/green] Venue from paper_spec: "
                    f"[bold]{venue_info.display_name}[/bold]\n"
                )
                return venue_info

        # 2. Re-read paper_spec.md from disk (catches manual edits / stale memory)
        venue_info = self._venue_from_disk(session, preamble)
        if venue_info:
            console.print(
                f"[green]✓[/green] Venue from paper_spec.md: "
                f"[bold]{venue_info.display_name}[/bold]\n"
            )
            return venue_info

        # 3. Fall back to preamble regex detection
        venue_info = _venue_from_preamble(preamble)
        if venue_info:
            console.print(
                f"[green]✓[/green] Auto-detected venue: "
                f"[bold]{venue_info.display_name}[/bold]\n"
            )
            return venue_info

        console.print("[yellow]Could not auto-detect venue style[/yellow]")
        console.print("[dim]Tip: set venue with /venue <name> <year> or in paper_spec.md[/dim]\n")
        return None

    @staticmethod
    def _venue_from_disk(session: SessionState, preamble: str) -> VenueInfo | None:
        """Re-read paper_spec.md from disk and try to resolve venue."""
        from texguardian.config.paper_spec import PaperSpec
        from texguardian.config.settings import SPEC_FILENAME

        spec_path = session.project_root / SPEC_FILENAME
        if not spec_path.exists():
            return None

        fresh_spec = PaperSpec.load(spec_path)
        if fresh_spec.venue in (None, "", "Unknown"):
            return None

        if session.paper_spec:
            session.paper_spec.venue = fresh_spec.venue

        return _venue_from_spec(fresh_spec.venue, preamble)

    # ------------------------------------------------------------------
    # LLM venue checklist (the part we can't hardcode)
    # ------------------------------------------------------------------

    @staticmethod
    async def _fetch_venue_checklist(
        venue: VenueInfo | None,
        session: SessionState,
        console: Console,
    ) -> list[str]:
        """Ask the LLM for venue-specific camera-ready requirements.

        Returns a list of checklist items. Empty list if no LLM or no venue.
        """
        if not venue or not session.llm_client:
            return []

        console.print(
            f"[cyan]Fetching {venue.display_name} camera-ready requirements...[/cyan]"
        )

        prompt = VENUE_CHECKLIST_PROMPT.format(venue=venue.display_name)

        try:
            response = await session.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1000,
                temperature=0.2,
            )
        except Exception as e:
            console.print(f"[yellow]Could not fetch venue checklist: {e}[/yellow]")
            return []

        # Parse the numbered list from the response
        items: list[str] = []
        for line in response.content.strip().split("\n"):
            line = line.strip()
            # Strip leading number + dot/paren: "1. ...", "1) ...", "- ..."
            cleaned = re.sub(r"^\d+[.)]\s*", "", line)
            cleaned = re.sub(r"^[-*]\s*", "", cleaned)
            cleaned = cleaned.strip()
            if cleaned and len(cleaned) > 5:  # skip empty / too-short lines
                items.append(cleaned)

        if items:
            console.print(
                f"[green]✓[/green] Found {len(items)} venue-specific requirement(s)\n"
            )
        else:
            console.print("[dim]No additional venue-specific requirements found[/dim]\n")

        return items

    # ------------------------------------------------------------------
    # Analysis (structural checks only)
    # ------------------------------------------------------------------

    def _analyze_submission(
        self,
        content: str,
        full_content: str,
        venue: VenueInfo | None,
    ) -> CameraReadyAnalysis:
        """Analyse the submission for camera-ready readiness.

        *Preamble*-only checks use ``content`` (main.tex) to avoid greedy
        matching.  Body-level checks (acknowledgments, TODOs) use
        ``full_content`` which includes \\input/\\include'd files.
        """
        preamble = _extract_preamble(content)

        has_final = bool(re.search(
            r"\\usepackage\s*\[\s*final\s*\]", preamble,
        ))
        has_accepted = bool(re.search(
            r"\\usepackage\s*\[\s*accepted\s*\]", preamble,
        ))
        has_iclr_final = bool(re.search(r"\\iclrfinalcopy", preamble))
        has_acl_final = bool(re.search(r"\\aclfinalcopy", preamble))

        is_camera_ready = has_final or has_accepted or has_iclr_final or has_acl_final

        has_ack = bool(re.search(
            r"(?<!%)\\section\*?\{[Aa]cknowledg", full_content,
        ))

        has_todo = bool(re.search(
            r"(?i)\\?%?\s*(?:TODO|FIXME|XXX|HACK)\b", full_content,
        ))

        issues: list[str] = []

        if not is_camera_ready:
            issues.append("Paper is not in camera-ready mode (missing [final]/[accepted]/finalcopy)")

        if not has_ack:
            issues.append("Acknowledgments section missing or commented out")

        if has_todo:
            issues.append("TODO/FIXME markers found in document")

        if venue:
            if venue.name in ("cvpr", "iccv", "eccv"):
                if re.search(r"\\usepackage\s*\[\s*review\s*\]", preamble):
                    issues.append(
                        f"[review] option still present — remove for "
                        f"{venue.display_name} camera-ready"
                    )

        return CameraReadyAnalysis(
            venue=venue,
            is_camera_ready=is_camera_ready,
            has_final_option=has_final,
            has_accepted_option=has_accepted,
            has_acknowledgments=has_ack,
            has_todo_markers=has_todo,
            preamble=preamble,
            issues=issues,
        )

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def _show_status(self, analysis: CameraReadyAnalysis, console: Console) -> None:
        """Show current submission status table."""
        table = Table(title="Submission Status")
        table.add_column("Check", style="cyan")
        table.add_column("Status")
        table.add_column("Action Needed")

        if analysis.is_camera_ready:
            table.add_row("Style Option", "[green]Camera-ready[/green]", "-")
        else:
            table.add_row("Style Option", "[yellow]Draft/Review[/yellow]", "Update to final/accepted")

        if analysis.has_acknowledgments:
            table.add_row("Acknowledgments", "[green]Present[/green]", "-")
        else:
            table.add_row("Acknowledgments", "[yellow]Missing[/yellow]", "Add/uncomment acknowledgments")

        if analysis.has_todo_markers:
            table.add_row("TODO/FIXME", "[yellow]Found[/yellow]", "Remove markers")
        else:
            table.add_row("TODO/FIXME", "[green]None[/green]", "-")

        console.print(table)

    def _show_checklist(self, analysis: CameraReadyAnalysis, console: Console) -> None:
        """Show camera-ready checklist (merged, no duplicates)."""
        console.print("\n[bold]Camera-Ready Checklist:[/bold]\n")

        seen: set[str] = set()
        checklist: list[tuple[str, str]] = []  # (item, priority)

        def _add(item: str, priority: str) -> None:
            key = item.lower()
            if key not in seen:
                seen.add(key)
                checklist.append((item, priority))

        # Detected issues (structural)
        for issue in analysis.issues:
            _add(issue, "required")

        # LLM-generated venue requirements
        for item in analysis.venue_checklist:
            _add(item, "venue")

        # Structural items from template
        if analysis.venue:
            for item in analysis.venue.checklist:
                _add(item, "structural")

        # Generic fallbacks
        _add("Remove any TODO/FIXME markers", "required")
        _add("Check page limit compliance", "required")
        _add("Verify all figures are high resolution", "recommended")

        for item, priority in checklist:
            if priority == "required":
                icon = "[red]☐[/red]"
            elif priority == "venue":
                icon = "[cyan]☐[/cyan]"
            elif priority == "recommended":
                icon = "[yellow]☐[/yellow]"
            else:
                icon = "[dim]☐[/dim]"
            console.print(f"  {icon} {item}")

    # ------------------------------------------------------------------
    # Targeted content extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_targeted_content(
        content: str,
        full_content: str,
        analysis: CameraReadyAnalysis,
    ) -> str:
        """Build a targeted excerpt of the paper for the LLM.

        Sends preamble (full), title/abstract, author block region,
        acknowledgments region, last 50 lines before \\end{document},
        and any TODO/FIXME lines.
        """
        sections: list[str] = []

        # Full preamble
        sections.append("%%% PREAMBLE %%%")
        sections.append(analysis.preamble)

        lines = content.split("\n")

        # Title + author block region — look for the first author/title
        # command after \begin{document} and grab generous context around
        # it so the LLM sees \icmltitle, \twocolumn[, \author, etc.
        title_author_added = False
        for i, line in enumerate(lines):
            if re.search(
                r"\\(?:author|icmlauthor|icmlaffiliation|maketitle"
                r"|icmltitle|title)\b",
                line,
            ):
                start = max(0, i - 10)
                end = min(len(lines), i + 20)
                sections.append("%%% TITLE / AUTHOR BLOCK REGION %%%")
                sections.append("\n".join(lines[start:end]))
                title_author_added = True
                break

        # Abstract — search for \begin{abstract}...\end{abstract}
        abstract_pattern = re.compile(
            r"\\begin\{abstract\}.*?\\end\{abstract\}",
            re.DOTALL,
        )
        abstract_match = abstract_pattern.search(content)
        if abstract_match:
            sections.append("%%% ABSTRACT %%%")
            sections.append(abstract_match.group(0))

        # If we didn't find a title/author block, try to get the first
        # 30 lines after \begin{document} as context
        if not title_author_added:
            for i, line in enumerate(lines):
                if r"\begin{document}" in line:
                    end = min(len(lines), i + 30)
                    sections.append("%%% DOCUMENT START %%%")
                    sections.append("\n".join(lines[i:end]))
                    break

        # Acknowledgments region — search full_content
        full_lines = full_content.split("\n")
        for i, line in enumerate(full_lines):
            if re.search(r"(?:^%\s*)?\\(?:section\*?\{[Aa]cknowledg|begin\{ack\})", line):
                start = max(0, i - 1)
                end = min(len(full_lines), i + 20)
                sections.append("%%% ACKNOWLEDGMENTS REGION %%%")
                sections.append("\n".join(full_lines[start:end]))
                break

        # Section headings index — lets the LLM know which sections exist
        # without including their full content. Prevents duplicate stubs.
        section_headings: list[str] = []
        for i, line in enumerate(full_lines):
            heading_match = re.search(
                r"\\(?:section|subsection|paragraph)\*?\{([^}]+)\}",
                line,
            )
            if heading_match:
                section_headings.append(
                    f"  Line {i + 1}: {heading_match.group(0)}"
                )
        if section_headings:
            sections.append("%%% SECTION HEADINGS (all found in document) %%%")
            sections.append("\n".join(section_headings))

        # Last 50 lines before \end{document}
        for i in range(len(lines) - 1, -1, -1):
            if r"\end{document}" in lines[i]:
                start = max(0, i - 50)
                sections.append("%%% END OF DOCUMENT (last 50 lines) %%%")
                sections.append("\n".join(lines[start:i + 1]))
                break

        # TODO/FIXME lines with context
        todo_lines: list[str] = []
        for i, line in enumerate(full_lines):
            if re.search(r"(?i)\b(?:TODO|FIXME|XXX|HACK)\b", line):
                ctx_start = max(0, i - 1)
                ctx_end = min(len(full_lines), i + 2)
                todo_lines.append(f"% Line {i + 1}:")
                todo_lines.extend(full_lines[ctx_start:ctx_end])
        if todo_lines:
            sections.append("%%% TODO/FIXME LINES %%%")
            sections.append("\n".join(todo_lines))

        return "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Patch generation, approval, application
    # ------------------------------------------------------------------

    async def _generate_and_apply_patches(
        self,
        content: str,
        full_content: str,
        analysis: CameraReadyAnalysis,
        session: SessionState,
        console: Console,
    ) -> int:
        """Generate patches via LLM, show for approval, apply with checkpoint.

        Returns the number of patches applied (0 if none).
        """
        if not session.llm_client:
            console.print("[red]LLM client not available — cannot generate patches[/red]")
            console.print("[dim]Fix the issues listed above manually, then run /review quick[/dim]")
            return 0

        console.print("\n[cyan]Generating camera-ready conversion patches...[/cyan]\n")

        # Build analysis summary
        analysis_summary_parts = [
            f"Camera-ready mode: {'Yes' if analysis.is_camera_ready else 'No'}",
            f"Has [final] option: {'Yes' if analysis.has_final_option else 'No'}",
            f"Has [accepted] option: {'Yes' if analysis.has_accepted_option else 'No'}",
            f"Has acknowledgments: {'Yes' if analysis.has_acknowledgments else 'No'}",
            f"Has TODO markers: {'Yes' if analysis.has_todo_markers else 'No'}",
        ]
        if analysis.issues:
            analysis_summary_parts.append("Issues:")
            for issue in analysis.issues:
                analysis_summary_parts.append(f"  - {issue}")

        # Merge all checklist items for the prompt:
        # structural issues + LLM venue checklist + template checklist
        checklist_items: list[str] = list(analysis.issues)
        checklist_items.extend(analysis.venue_checklist)
        if analysis.venue:
            checklist_items.extend(analysis.venue.checklist)

        # Build targeted content
        targeted_content = self._build_targeted_content(
            content, full_content, analysis,
        )

        venue_display = analysis.venue.display_name if analysis.venue else "Unknown venue"
        filename = session.main_tex_path.name
        if analysis.venue:
            camera_ready_opt = analysis.venue.camera_ready_option
        else:
            camera_ready_opt = "\\usepackage[final]{<style>}"

        prompt = CAMERA_READY_PROMPT.format(
            venue=venue_display,
            filename=filename,
            camera_ready_option=camera_ready_opt,
            checklist="\n".join(f"- {item}" for item in checklist_items) if checklist_items else "Standard camera-ready requirements",
            analysis_summary="\n".join(analysis_summary_parts),
            targeted_content=targeted_content,
        )

        # Stream the LLM response
        full_response: list[str] = []
        try:
            async for chunk in session.llm_client.stream(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.3,
            ):
                if chunk.content:
                    console.print(chunk.content, end="")
                    full_response.append(chunk.content)
            console.print("\n")
        except Exception as e:
            console.print(f"\n[red]Error during LLM streaming: {e}[/red]")
            response = await session.llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.3,
            )
            full_response = [response.content]

        response_text = "".join(full_response)

        # Save response to context so /approve can find patches
        if session.context:
            session.context.add_assistant_message(response_text)

        # Extract patches
        from texguardian.patch.parser import extract_patches

        patches = extract_patches(response_text)

        if not patches:
            console.print("[yellow]No unified diff patches found in LLM response.[/yellow]")
            return 0

        # Use the same interactive approval flow as the REPL chat
        from texguardian.cli.approval import interactive_approval

        return await interactive_approval(patches, session, console)

    # ------------------------------------------------------------------
    # Next steps
    # ------------------------------------------------------------------

    @staticmethod
    def _show_next_steps(console: Console) -> None:
        """Show what the user should do after camera-ready changes."""
        console.print("\n[bold]Next steps:[/bold]")
        console.print("  [cyan]/review quick[/cyan]  — compile and check page limits, figures, tables")
        console.print("  [cyan]/visual_polish[/cyan] — inspect PDF snapshots for spacing/overflow issues")
        console.print("  [cyan]/anonymize[/cyan]     — de-anonymize author names and affiliations")
        console.print("  [cyan]/watch[/cyan]         — auto-compile on save and run checks in a loop")
        console.print()

    def get_completions(self, partial: str) -> list[str]:
        """No sub-commands — single-flow now."""
        return []


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _resolve_full_content(main_tex: Path, *, _seen: set[Path] | None = None) -> str:
    """Read main.tex and recursively inline \\input/\\include'd files."""
    if _seen is None:
        _seen = set()

    real = main_tex.resolve()
    if real in _seen:
        return ""
    _seen.add(real)

    if not main_tex.exists():
        return ""

    content = main_tex.read_text(errors="ignore")
    result_lines: list[str] = []

    for line in content.split("\n"):
        input_match = re.search(r"\\(?:input|include)\{([^}]+)\}", line)
        if input_match:
            included_path = input_match.group(1)
            if not included_path.endswith(".tex"):
                included_path += ".tex"
            included_file = main_tex.parent / included_path
            if included_file.exists():
                result_lines.append(line)
                result_lines.append(
                    _resolve_full_content(included_file, _seen=_seen)
                )
                continue
        result_lines.append(line)

    return "\n".join(result_lines)


def _extract_preamble(content: str) -> str:
    """Return everything before \\begin{document} (the preamble)."""
    match = re.search(r"\\begin\{document\}", content)
    if match:
        return content[:match.start()]
    return content


def _venue_from_spec(spec_venue: str, preamble: str) -> VenueInfo | None:
    """Build VenueInfo from a paper_spec.venue string like 'NeurIPS 2026'."""
    spec_lower = spec_venue.lower()

    for key, tmpl in VENUE_TEMPLATES.items():
        if key in spec_lower:
            return _build_venue_info(key, tmpl, preamble, spec_venue)

    return None


def _venue_from_preamble(preamble: str) -> VenueInfo | None:
    """Detect venue from the preamble only (fixes greedy detection bug)."""
    preamble_lower = preamble.lower()

    for key, tmpl in VENUE_TEMPLATES.items():
        if re.search(tmpl["pattern"], preamble_lower):
            return _build_venue_info(key, tmpl, preamble)

    return None


def _build_venue_info(
    key: str,
    tmpl: dict,
    preamble: str,
    display_override: str | None = None,
) -> VenueInfo:
    """Construct a VenueInfo from a template + detected preamble info."""
    match = re.search(tmpl["pattern"], preamble, re.IGNORECASE)
    style_pkg = match.group(0) if match else key

    if display_override:
        display_name = display_override
    else:
        year_match = re.search(r"\d{4}", style_pkg)
        year = year_match.group(0) if year_match else ""
        display_name = f"{key.upper()} {year}".strip()

    cr_opt = tmpl["camera_ready"]
    if cr_opt.startswith("["):
        camera_ready_option = f"\\usepackage{cr_opt}{{{style_pkg}}}"
    elif cr_opt.startswith("\\"):
        camera_ready_option = cr_opt
    else:
        camera_ready_option = f"\\usepackage{{{style_pkg}}}"

    anonymous_option = f"\\usepackage{{{style_pkg}}}"

    return VenueInfo(
        name=key,
        display_name=display_name,
        style_package=style_pkg,
        camera_ready_option=camera_ready_option,
        anonymous_option=anonymous_option,
        page_limit=tmpl["page_limit"],
        checklist=list(tmpl["checklist"]),
    )

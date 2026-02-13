"""Anonymize command - make paper anonymous for submission.

Reverse of camera_ready:
- Remove/hide author names and affiliations
- Comment out acknowledgments
- Remove identifying information
- Update style options for anonymous mode
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.table import Table

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console

    from texguardian.core.session import SessionState


def _numbered_content(path: Path) -> str:
    """Return file content with line numbers for accurate LLM patch generation."""
    content = path.read_text()
    lines = content.splitlines()
    return "\n".join(f"{i+1:4d}| {line}" for i, line in enumerate(lines))


# ---------------------------------------------------------------------------
# Patterns to detect identifying information
# ---------------------------------------------------------------------------

IDENTIFYING_PATTERNS = [
    # Standard LaTeX author commands
    (r'\\author\{[^}]+\}', 'author', 'Author names'),
    # ICML-specific author commands
    (r'\\icmlauthor\{[^}]+\}\{[^}]+\}', 'author', 'Author names (ICML)'),
    (r'\\icmlcorrespondingauthor\{[^}]+\}\{[^}]+\}', 'author',
     'Corresponding author (ICML)'),
    # Affiliations (standard + ICML)
    (r'\\affiliation\{[^}]+\}', 'affiliation', 'Affiliations'),
    (r'\\icmlaffiliation\{[^}]+\}\{[^}]+\}', 'affiliation',
     'Affiliations (ICML)'),
    (r'\\institute\{[^}]+\}', 'institute', 'Institute info'),
    # Contact / identity
    (r'\\address\{[^}]+\}', 'address', 'Addresses'),
    (r'\\email\{[^}]+\}', 'email', 'Email addresses'),
    (r'\\thanks\{[^}]+\}', 'thanks', 'Thanks/footnotes'),
    (r'\\orcid\{[^}]+\}', 'orcid', 'ORCID IDs'),
    # Acknowledgments (section-level)
    (r'\\section\*?\{[Aa]cknowledg[^}]*\}.*?(?=\\section|\\end\{document\})',
     'ack', 'Acknowledgments'),
    (r'\\paragraph\{[Aa]cknowledg[^}]*\}.*?(?=\\paragraph|\\section|'
     r'\\end\{document\})', 'ack', 'Acknowledgments'),
]

# Venue-specific anonymous options — used in the LLM prompt so the model
# knows exactly how to switch from camera-ready → anonymous mode.
VENUE_ANONYMOUS = {
    "iclr": {
        "camera_ready_pattern": r"\\iclrfinalcopy",
        "anonymous_replacement": "% \\iclrfinalcopy  % Commented for anonymous submission",
        "author_template": "\\author{Anonymous}",
    },
    "icml": {
        "camera_ready_pattern": r"\\usepackage\[accepted\]\{icml\d{4}\}",
        "anonymous_replacement": "\\usepackage{icml<YEAR>}",
        "author_template": "\\icmlauthor{Anonymous}{anon}",
    },
    "neurips": {
        "camera_ready_pattern": r"\\usepackage\[final\]\{neurips_?\d{4}\}",
        "anonymous_replacement": "\\usepackage{neurips_<YEAR>}",
        "author_template": "\\author{Anonymous}",
    },
    "cvpr": {
        "camera_ready_pattern": r"\\usepackage\{cvpr\}",
        "anonymous_replacement": "\\usepackage[review]{cvpr}",
        "author_template": "\\author{Anonymous CVPR submission}",
    },
    "acl": {
        "camera_ready_pattern": r"\\aclfinalcopy",
        "anonymous_replacement": "% \\aclfinalcopy",
        "author_template": "\\author{Anonymous}",
    },
}


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

ANONYMIZE_PROMPT = """\
You are a LaTeX expert helping anonymize a paper for double-blind review.

## Target File
`{filename}`

## Detected Venue
{venue}

## Venue-Specific Anonymous Mode
{venue_instructions}

## Current Paper Analysis
{analysis}

## Full File Content (with line numbers)
{numbered_content}

## Task
Generate unified diff patches to anonymize this paper:

1. **Author Block**: Replace with "Anonymous" or venue-specific anonymous \
author template shown above
2. **Affiliations**: Replace with anonymous placeholder
3. **Acknowledgments**: Comment out the entire section (wrap in \
`% BEGIN ACKNOWLEDGMENTS (commented for review)` ... \
`% END ACKNOWLEDGMENTS`)
4. **Self-citations**: Flag obvious self-citations (e.g., "In our previous \
work [1]...") with a `% SELF-CITE:` comment
5. **Style Options**: Update to anonymous/review mode as shown above
6. **URLs/Links**: Comment out links to personal pages, GitHub repos with names
7. **Email addresses**: Comment out or replace with anonymous placeholder

IMPORTANT:
- Use the exact line numbers from the numbered content above in your @@ headers
- Context and removed lines MUST match the file content exactly (copy them)
- Do NOT delete content, just comment it out with % (so it can be restored \
for camera-ready)
- Use % to comment out lines in LaTeX
- Preserve the original content as comments so `/camera_ready` can reverse it

Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename `{filename}` in the --- and +++ headers. \
Example format:

```diff
--- a/{filename}
+++ b/{filename}
@@ -70,3 +70,3 @@
-\\icmlauthor{{John Doe}}{{mit}}
+\\icmlauthor{{Anonymous}}{{anon}}
```
"""


# ---------------------------------------------------------------------------
# Command
# ---------------------------------------------------------------------------


class AnonymizeCommand(Command):
    """Make paper anonymous for submission."""

    name = "anonymize"
    description = "Make paper anonymous for double-blind review submission"
    aliases = ["anon", "blind"]
    usage = "/anonymize - Analyze and anonymize paper for submission"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute anonymize command."""
        console.print("[bold cyan]Paper Anonymization[/bold cyan]\n")

        # Read main tex file
        main_tex = session.main_tex_path
        if not main_tex.exists():
            console.print(f"[red]Main tex file not found: {main_tex}[/red]")
            return

        content = main_tex.read_text()

        # Resolve \input/\include for full analysis
        from texguardian.cli.commands.camera_ready import _resolve_full_content

        full_content = _resolve_full_content(main_tex)

        # Detect venue from preamble
        venue = self._detect_venue(content)
        if venue:
            console.print(
                f"[green]✓[/green] Detected venue: "
                f"[bold]{venue.upper()}[/bold]\n"
            )

        # Analyze for identifying information (use full_content for
        # thorough detection across \input'd files)
        analysis = self._analyze_identifying_info(full_content)

        # Show what was found
        self._show_findings(analysis, console)

        # Check if already anonymous
        if analysis["is_anonymous"]:
            console.print(
                "\n[green]Paper appears to already be anonymous![/green]"
            )
            return

        # Generate and apply anonymization patches (single-step)
        await self._generate_and_apply_patches(
            content, full_content, venue, analysis, session, console,
        )

    def _analyze_identifying_info(self, content: str) -> dict:
        """Analyze paper for identifying information."""
        analysis: dict = {
            "is_anonymous": True,
            "findings": [],
            "author_info": None,
            "has_acknowledgments": False,
            "self_citations": [],
        }

        for pattern, info_type, description in IDENTIFYING_PATTERNS:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            if matches:
                # Check if it's just "Anonymous"
                for match in matches:
                    if "anonymous" not in match.lower():
                        analysis["is_anonymous"] = False
                        analysis["findings"].append({
                            "type": info_type,
                            "description": description,
                            "count": len(matches),
                            "sample": matches[0][:100] if matches else "",
                        })
                        break

        # Check for self-citations
        self_cite_patterns = [
            r'[Oo]ur previous work',
            r'[Ww]e previously',
            r'[Ii]n \[[^\]]+\],? we',
            r'[Oo]ur earlier',
            r'[Aa]s we showed in',
        ]
        for pattern in self_cite_patterns:
            matches = re.findall(pattern, content)
            if matches:
                analysis["self_citations"].extend(matches)
                analysis["is_anonymous"] = False

        # Check for acknowledgments section (skip commented lines)
        for line in content.split("\n"):
            if line.lstrip().startswith("%"):
                continue
            if re.search(r"\\section\*?\{[Aa]cknowledg", line):
                analysis["has_acknowledgments"] = True
                analysis["is_anonymous"] = False
                break

        return analysis

    @staticmethod
    def _detect_venue(content: str) -> str | None:
        """Detect venue from preamble style packages only.

        Searches only before \\begin{document} to avoid matching filenames
        like \\bibliography{cvpr_paper}.
        """
        begin_doc = re.search(r"\\begin\{document\}", content)
        preamble = content[:begin_doc.start()] if begin_doc else content
        preamble_lower = preamble.lower()

        # Year-agnostic patterns — must match in preamble only
        venue_patterns: list[tuple[str, str]] = [
            ("iclr", r"iclr\d{4}"),
            ("icml", r"icml\d{4}"),
            ("neurips", r"neurips_?\d{4}"),
            ("aaai", r"aaai\d{2,4}"),
            ("acl", r"acl\d{4}|acl_[a-z]|\\usepackage[^}]*\bacl\b"),
            ("cvpr", r"\\usepackage(?:\[[^\]]*\])?\{cvpr\}"),
            ("iccv", r"\\usepackage(?:\[[^\]]*\])?\{iccv\}"),
            ("eccv", r"\\usepackage(?:\[[^\]]*\])?\{eccv\}"),
        ]

        for venue, pattern in venue_patterns:
            if re.search(pattern, preamble_lower):
                return venue

        return None

    def _show_findings(self, analysis: dict, console: Console) -> None:
        """Show identified information."""
        if analysis["is_anonymous"]:
            console.print("[green]✓ No identifying information found[/green]")
            return

        table = Table(title="Identifying Information Found")
        table.add_column("Type", style="cyan")
        table.add_column("Description")
        table.add_column("Action")

        for finding in analysis["findings"]:
            table.add_row(
                finding["type"],
                finding["description"],
                "[red]Remove/Replace[/red]"
            )

        if analysis["has_acknowledgments"]:
            table.add_row(
                "acknowledgments",
                "Acknowledgments section found",
                "[red]Comment out[/red]"
            )

        if analysis["self_citations"]:
            table.add_row(
                "self-citations",
                f"{len(analysis['self_citations'])} potential self-citations",
                "[yellow]Review manually[/yellow]"
            )

        console.print(table)

        # Show self-citation examples
        if analysis["self_citations"]:
            console.print("\n[yellow]Potential self-citations:[/yellow]")
            for cite in analysis["self_citations"][:5]:
                console.print(f"  [yellow]•[/yellow] \"{cite}...\"")

    # ------------------------------------------------------------------
    # Patch generation and approval
    # ------------------------------------------------------------------

    async def _generate_and_apply_patches(
        self,
        content: str,
        full_content: str,
        venue: str | None,
        analysis: dict,
        session: SessionState,
        console: Console,
    ) -> int:
        """Generate patches via LLM, approve interactively, apply.

        Returns the number of patches applied (0 if none).
        """
        if not session.llm_client:
            console.print("[red]LLM client not available[/red]")
            console.print(
                "[dim]Fix the issues listed above manually[/dim]"
            )
            return 0

        console.print("\n[cyan]Generating anonymization patches...[/cyan]\n")

        # Build analysis text for the prompt
        analysis_text: list[str] = []
        for finding in analysis["findings"]:
            analysis_text.append(
                f"- {finding['description']}: {finding['count']} found"
            )
            if finding["sample"]:
                analysis_text.append(
                    f"  Sample: {finding['sample'][:80]}..."
                )

        if analysis["self_citations"]:
            analysis_text.append(
                f"- Potential self-citations: "
                f"{len(analysis['self_citations'])}"
            )

        if analysis["has_acknowledgments"]:
            analysis_text.append(
                "- Acknowledgments section present (needs commenting)"
            )

        # Venue-specific instructions
        venue_info = VENUE_ANONYMOUS.get(venue or "", {})
        if venue_info:
            venue_instructions = (
                f"Camera-ready pattern: `{venue_info['camera_ready_pattern']}`\n"
                f"Anonymous replacement: `{venue_info['anonymous_replacement']}`\n"
                f"Author template: `{venue_info['author_template']}`"
            )
        else:
            venue_instructions = (
                "No venue-specific instructions. Use generic anonymous mode:\n"
                "- Comment out \\iclrfinalcopy, \\aclfinalcopy, or "
                "remove [final]/[accepted] options\n"
                "- Replace author names with \\author{Anonymous}"
            )

        filename = session.main_tex_path.name
        numbered = _numbered_content(session.main_tex_path)

        prompt = ANONYMIZE_PROMPT.format(
            filename=filename,
            analysis=("\n".join(analysis_text)
                      if analysis_text
                      else "No specific issues found"),
            venue=venue.upper() if venue else "Unknown",
            venue_instructions=venue_instructions,
            numbered_content=numbered,
        )

        from texguardian.llm.prompts.system import COMMAND_SYSTEM_PROMPT
        from texguardian.llm.streaming import stream_llm

        response_text = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
            system=COMMAND_SYSTEM_PROMPT,
            max_tokens=4000,
            temperature=0.3,
        )
        console.print()  # newline after streaming

        # Save response to context so /approve can also find patches
        if session.context:
            session.context.add_assistant_message(response_text)

        # Extract and apply patches via interactive approval
        from texguardian.cli.approval import interactive_approval
        from texguardian.patch.parser import extract_patches

        patches = extract_patches(response_text)

        if not patches:
            console.print(
                "\n[yellow]No diff patches found in LLM response.[/yellow]"
            )
            console.print(
                "[dim]You can manually fix the issues or try again[/dim]"
            )
            return 0

        applied = await interactive_approval(patches, session, console)

        if applied > 0:
            console.print(
                f"\n[green]✓ Applied {applied} anonymization patch(es)[/green]"
            )
            console.print(
                "[yellow]Remember to manually review for subtle "
                "self-identifying info![/yellow]"
            )
        else:
            console.print(
                "\n[dim]No changes applied. "
                "Fix issues manually if needed.[/dim]"
            )

        return applied

    # ------------------------------------------------------------------
    # Targeted content extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _build_targeted_content(content: str, full_content: str) -> str:
        """Build targeted excerpt for the LLM (avoids blind truncation).

        Includes: preamble, author/affiliation block, acknowledgments
        region, section headings index, last 50 lines, and lines with
        self-identifying markers.
        """
        sections: list[str] = []

        # Preamble
        begin_doc = re.search(r"\\begin\{document\}", content)
        preamble = content[:begin_doc.start()] if begin_doc else content
        sections.append("%%% PREAMBLE %%%")
        sections.append(preamble)

        lines = content.split("\n")
        full_lines = full_content.split("\n")

        # Title + author / affiliation block region
        for i, line in enumerate(lines):
            if re.search(
                r"\\(?:author|icmlauthor|icmlaffiliation|affiliation"
                r"|institute|icmltitle|title|maketitle)\b",
                line,
            ):
                start = max(0, i - 10)
                end = min(len(lines), i + 20)
                sections.append("%%% AUTHOR / AFFILIATION REGION %%%")
                sections.append("\n".join(lines[start:end]))
                break

        # Acknowledgments region — search full_content for included files
        for i, line in enumerate(full_lines):
            if re.search(
                r"(?:^%\s*)?\\(?:section\*?\{[Aa]cknowledg|begin\{ack\})",
                line,
            ):
                start = max(0, i - 1)
                end = min(len(full_lines), i + 25)
                sections.append("%%% ACKNOWLEDGMENTS REGION %%%")
                sections.append("\n".join(full_lines[start:end]))
                break

        # Section headings index — lets the LLM know what sections exist
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
            sections.append(
                "%%% SECTION HEADINGS (all found in document) %%%"
            )
            sections.append("\n".join(section_headings))

        # Last 50 lines before \end{document}
        for i in range(len(lines) - 1, -1, -1):
            if r"\end{document}" in lines[i]:
                start = max(0, i - 50)
                sections.append("%%% END OF DOCUMENT (last 50 lines) %%%")
                sections.append("\n".join(lines[start:i + 1]))
                break

        # Lines with email addresses or URLs (potential identifying info)
        id_lines: list[str] = []
        for i, line in enumerate(full_lines):
            if re.search(
                r"\\url\{|\\href\{|[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\."
                r"[a-zA-Z]{2,}|github\.com/",
                line,
            ):
                ctx_start = max(0, i - 1)
                ctx_end = min(len(full_lines), i + 2)
                id_lines.append(f"% Line {i + 1}:")
                id_lines.extend(full_lines[ctx_start:ctx_end])
        if id_lines:
            sections.append("%%% LINES WITH URLS/EMAILS %%%")
            sections.append("\n".join(id_lines))

        return "\n\n".join(sections)

    def get_completions(self, partial: str) -> list[str]:
        """Get argument completions."""
        return ["apply", "fix"]

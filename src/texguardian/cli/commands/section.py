"""Section command - verify, fix, and analyze specific sections.

Unified command that:
1. Verifies section content (completeness, structure)
2. Fixes issues (writing, clarity)
3. Deep analysis (AI-powered quality assessment)
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


SECTION_FIX_PROMPT = """\
You are a LaTeX expert improving a section in an academic paper.

## Target File
`{filename}`

## Section: {section_name}
## Venue: {venue}

## Issues Found
{issues}

## Full File Content (with line numbers)
{numbered_content}

## Task
Generate unified diff patches to fix issues in the **{section_name}** section:

1. **Writing clarity**: Improve unclear sentences
2. **Structure**: Better paragraph organization
3. **Transitions**: Add transitions between paragraphs
4. **Claims**: Ensure claims have citations
5. **Technical accuracy**: Fix any technical issues

Guidelines:
- Keep the same overall structure
- Don't add new content, just improve existing
- Make minimal changes for maximum impact
- Preserve author's voice and style

IMPORTANT: Use the exact line numbers from the numbered content above in \
your @@ headers. Context and removed lines MUST match the file content exactly.

Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename `{filename}` in the --- and +++ headers. \
Example format:

```diff
--- a/{filename}
+++ b/{filename}
@@ -100,3 +100,3 @@
-Old line content
+New improved line content
```
"""


SECTION_CUSTOM_PROMPT = """\
You are a LaTeX expert editing a section in an academic paper.

## Target File
`{filename}`

## Section: {section_name}
## Venue: {venue}

## User Request
{user_instruction}

## Full File Content (with line numbers)
{numbered_content}

## Task
Generate unified diff patches to implement the user's request on the \
**{section_name}** section.

Guidelines:
- Make only the changes the user requested
- Preserve the author's voice and style
- Keep the overall structure unless the user asks for restructuring
- Make minimal, focused changes

IMPORTANT: Use the exact line numbers from the numbered content above in \
your @@ headers. Context and removed lines MUST match the file content exactly.

Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename `{filename}` in the --- and +++ headers. \
Example format:

```diff
--- a/{filename}
+++ b/{filename}
@@ -100,3 +100,3 @@
-Old line content
+New improved line content
```
"""


SECTION_ANALYSIS_PROMPT = """You are a senior reviewer for {venue} analyzing a paper section.

## Section: {section_name}

## Content
{section_content}

## Task
Provide detailed analysis and scores:

1. **Clarity** (0-100): Is the writing clear and easy to follow?
2. **Structure** (0-100): Is it well-organized with good flow?
3. **Completeness** (0-100): Does it cover what it should?
4. **Technical Depth** (0-100): Appropriate level of detail?
5. **Citations** (0-100): Are claims properly supported?

Output as JSON:
```json
{{
  "section": "{section_name}",
  "scores": {{
    "clarity": 80,
    "structure": 75,
    "completeness": 85,
    "technical_depth": 70,
    "citations": 65
  }},
  "overall": 75,
  "strengths": ["Strength 1", "Strength 2"],
  "weaknesses": ["Weakness 1", "Weakness 2"],
  "specific_suggestions": [
    {{"line": "approximate location", "issue": "what's wrong", "fix": "how to fix"}}
  ],
  "missing_elements": ["What's missing"],
  "summary": "Overall assessment"
}}
```
"""


class SectionCommand(Command):
    """Complete section verification, fixing, and analysis."""

    name = "section"
    description = "Verify, fix, and analyze a specific section"
    aliases = ["sec"]
    usage = (
        "/section <name> [fix | <instruction>]\n"
        "  /section                          - List all sections\n"
        "  /section Introduction             - Verify + analyze\n"
        "  /section Introduction fix         - Auto-fix detected issues\n"
        "  /section Introduction make it more concise  - Custom edit"
    )

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute section command.

        Supports three modes:
        - /section <name>              → verify + analyze
        - /section <name> fix          → verify + auto-fix + analyze
        - /section <name> <instruction> → custom user edit + analyze
        """
        if not args:
            await self._list_sections(session, console)
            return

        # Resolve which part of args is the section name vs instruction
        section_name, instruction = await self._parse_section_args(
            args, session,
        )

        if not section_name:
            await self._list_sections(session, console)
            return

        console.print(f"[bold cyan]Section: {section_name}[/bold cyan]\n")

        # Find the section content
        section_content = await self._find_section(section_name, session, console)
        if not section_content:
            return

        fix_mode = instruction.lower() == "fix" if instruction else False
        custom_instruction = instruction if instruction and not fix_mode else ""

        if custom_instruction:
            # Custom user instruction — skip static verify, go straight
            # to LLM with the user's request
            console.print(f"[bold]Applying: [cyan]{custom_instruction}[/cyan][/bold]\n")
            await self._custom_fix_section(
                session, console, section_name, section_content,
                custom_instruction,
            )
        else:
            # Standard flow: verify → (fix if requested) → analyze
            console.print("[bold]Step 1: Verification[/bold]")
            issues = self._verify_section(section_content, section_name, console)

            if fix_mode and issues:
                console.print("\n[bold]Step 2: Fixing Issues[/bold]")
                await self._fix_section(
                    session, console, section_name, section_content, issues,
                )
            elif issues:
                console.print(
                    f"\n[yellow]{len(issues)} potential issues found.[/yellow]"
                )
                console.print(
                    f"[dim]Run '/section {section_name} fix' to auto-fix[/dim]"
                )

            console.print("\n[bold]Deep Analysis[/bold]")
            await self._analyze_section(
                session, console, section_name, section_content,
            )

    async def _parse_section_args(
        self,
        args: str,
        session: SessionState,
    ) -> tuple[str, str]:
        """Parse section name and optional instruction from args.

        Tries to match progressively longer prefixes of *args* against
        the paper's actual section names.  Returns ``(section_name,
        instruction)`` where *instruction* is "" when the user only
        typed a section name.

        Examples:
            "Introduction"                  → ("Introduction", "")
            "Introduction fix"              → ("Introduction", "fix")
            "Related Work fix"              → ("Related Work", "fix")
            "Introduction make it shorter"  → ("Introduction", "make it shorter")
        """
        from texguardian.latex.parser import LatexParser

        parser = LatexParser(
            session.project_root, session.config.project.main_tex,
        )

        try:
            sections = parser.extract_sections()
        except Exception:
            # Fallback: first word is section name, rest is instruction
            parts = args.split(maxsplit=1)
            return parts[0], (parts[1] if len(parts) > 1 else "")

        words = args.split()
        best_n = 0  # how many leading words matched a section

        # Try 1 word, 2 words, … up to 4 words as the section name
        for n in range(1, min(len(words) + 1, 5)):
            candidate = " ".join(words[:n])
            matching = [
                s for s in sections
                if candidate.lower() in s["name"].lower()
            ]
            if matching:
                best_n = n

        if best_n == 0:
            # Nothing matched — return full args as section name so
            # _find_section() can show "not found" with suggestions.
            return args, ""

        section_name = " ".join(words[:best_n])
        instruction = " ".join(words[best_n:])
        return section_name, instruction

    async def _list_sections(
        self,
        session: SessionState,
        console: Console,
    ) -> None:
        """List all sections in the paper."""
        from texguardian.latex.parser import LatexParser

        parser = LatexParser(session.project_root, session.config.project.main_tex)

        try:
            sections = parser.extract_sections()

            if not sections:
                console.print("[yellow]No sections found[/yellow]")
                return

            console.print("[bold]Available Sections:[/bold]\n")

            for i, section in enumerate(sections, 1):
                name = section.get("name", "Unknown")
                word_count = len(section.get("content", "").split())
                console.print(f"  {i}. [cyan]{name}[/cyan] (~{word_count} words)")

            console.print("\n[dim]Usage:[/dim]")
            console.print("[dim]  /section Introduction             - Verify + analyze[/dim]")
            console.print("[dim]  /section Introduction fix         - Auto-fix issues[/dim]")
            console.print("[dim]  /section Introduction <your request> - Custom edit[/dim]")

        except Exception as e:
            console.print(f"[red]Error listing sections: {e}[/red]")

    async def _find_section(
        self,
        section_name: str,
        session: SessionState,
        console: Console,
    ) -> str | None:
        """Find a section by name."""
        from texguardian.latex.parser import LatexParser

        parser = LatexParser(session.project_root, session.config.project.main_tex)

        try:
            sections = parser.extract_sections()

            # Find matching section
            matching = [s for s in sections if section_name.lower() in s["name"].lower()]

            if not matching:
                console.print(f"[red]Section '{section_name}' not found[/red]")
                console.print("Available sections:")
                for s in sections:
                    console.print(f"  - {s['name']}")
                return None

            section = matching[0]
            console.print(f"Found: [bold]{section['name']}[/bold] (~{len(section['content'].split())} words)\n")
            return section["content"]

        except Exception as e:
            console.print(f"[red]Error finding section: {e}[/red]")
            return None

    def _verify_section(
        self,
        content: str,
        section_name: str,
        console: Console,
    ) -> list[dict]:
        """Verify section content."""
        issues = []

        # Check for common issues
        word_count = len(content.split())

        # Very short section
        if word_count < 100:
            issues.append({"type": "too_short", "desc": "Section seems very short"})

        # Very long section
        if word_count > 2000:
            issues.append({"type": "too_long", "desc": "Section may be too long"})

        # TODO markers
        if re.search(r'\bTODO\b|\bFIXME\b|\bXXX\b', content):
            issues.append({"type": "todo_marker", "desc": "Contains TODO/FIXME markers"})

        # Orphan citations (claims without citations)
        claim_patterns = [
            r'[Ii]t has been shown that',
            r'[Ss]tudies have demonstrated',
            r'[Rr]esearch indicates',
            r'[Ii]t is well known',
            r'[Pp]revious work',
        ]
        for pattern in claim_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                # Check if followed by citation within 50 chars
                idx = content.find(match)
                if idx >= 0:
                    after = content[idx:idx+100]
                    if '\\cite' not in after:
                        issues.append({"type": "missing_citation", "desc": f"Claim without citation: '{match}...'"})

        # Very long paragraphs (no blank lines for 500+ chars)
        paragraphs = content.split('\n\n')
        for i, para in enumerate(paragraphs):
            if len(para) > 2000:
                issues.append({"type": "long_paragraph", "desc": f"Paragraph {i+1} is very long"})

        # Display results
        if issues:
            table = Table(title="Verification Results")
            table.add_column("Issue", style="yellow")
            table.add_column("Description")

            for issue in issues[:10]:
                table.add_row(issue["type"], issue["desc"][:60])

            console.print(table)
        else:
            console.print("[green]✓ No obvious issues found[/green]")

        return issues

    async def _fix_section(
        self,
        session: SessionState,
        console: Console,
        section_name: str,
        section_content: str,
        issues: list[dict],
    ) -> None:
        """Fix section issues."""
        if not session.llm_client:
            console.print("[red]LLM client not available[/red]")
            return

        issues_text = "\n".join([f"- {i['type']}: {i['desc']}" for i in issues])
        filename = session.main_tex_path.name
        numbered = _numbered_content(session.main_tex_path)

        prompt = SECTION_FIX_PROMPT.format(
            filename=filename,
            section_name=section_name,
            venue=session.paper_spec.venue if session.paper_spec else "Unknown",
            issues=issues_text,
            numbered_content=numbered,
        )

        console.print("[cyan]Generating fixes...[/cyan]\n")

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

        # Save response to context so /approve can find patches
        if session.context:
            session.context.add_assistant_message(response_text)

        # Extract and apply patches via interactive approval
        from texguardian.cli.approval import interactive_approval
        from texguardian.patch.parser import extract_patches

        patches = extract_patches(response_text)

        if patches:
            applied = await interactive_approval(patches, session, console)
            if applied > 0:
                console.print(
                    f"\n[green]Applied {applied} section fix(es)[/green]"
                )
        else:
            console.print(
                "\n[yellow]No diff patches found in response.[/yellow]"
            )

    async def _custom_fix_section(
        self,
        session: SessionState,
        console: Console,
        section_name: str,
        section_content: str,
        user_instruction: str,
    ) -> None:
        """Apply a free-form user instruction to a section via LLM."""
        if not session.llm_client:
            console.print("[red]LLM client not available[/red]")
            return

        filename = session.main_tex_path.name
        numbered = _numbered_content(session.main_tex_path)

        prompt = SECTION_CUSTOM_PROMPT.format(
            filename=filename,
            section_name=section_name,
            venue=session.paper_spec.venue if session.paper_spec else "Unknown",
            user_instruction=user_instruction,
            numbered_content=numbered,
        )

        console.print("[cyan]Generating edits...[/cyan]\n")

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

        # Save response to context so /approve can find patches
        if session.context:
            session.context.add_assistant_message(response_text)

        # Extract and apply patches via interactive approval
        from texguardian.cli.approval import interactive_approval
        from texguardian.patch.parser import extract_patches

        patches = extract_patches(response_text)

        if patches:
            applied = await interactive_approval(patches, session, console)
            if applied > 0:
                console.print(
                    f"\n[green]Applied {applied} edit(s)[/green]"
                )
        else:
            console.print(
                "\n[yellow]No diff patches found in response.[/yellow]"
            )

    async def _analyze_section(
        self,
        session: SessionState,
        console: Console,
        section_name: str,
        section_content: str,
    ) -> None:
        """Deep AI analysis of section."""
        if not session.llm_client:
            console.print("[dim]LLM not available for analysis[/dim]")
            return

        prompt = SECTION_ANALYSIS_PROMPT.format(
            section_name=section_name,
            venue=session.paper_spec.venue if session.paper_spec else "Top ML venue",
            section_content=section_content,
        )

        console.print("[dim]Analyzing section quality...[/dim]\n")

        from texguardian.llm.prompts.system import COMMAND_SYSTEM_PROMPT
        from texguardian.llm.streaming import stream_llm

        content = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
            system=COMMAND_SYSTEM_PROMPT,
            max_tokens=3000,
            temperature=0.3,
        )
        console.print()  # newline after streaming

        # Try to parse JSON and display structured analysis
        import json
        json_start = content.find("{")
        json_end = content.rfind("}") + 1

        if json_start >= 0 and json_end > json_start:
            try:
                data = json.loads(content[json_start:json_end])
                self._display_analysis(data, console)
            except json.JSONDecodeError:
                console.print("\n[dim]Note: Could not parse structured analysis.[/dim]")

    @staticmethod
    def _safe_int(value: object, default: int = 0) -> int:
        """Safely convert a value to int, handling strings/floats from LLM JSON."""
        if isinstance(value, int):
            return value
        try:
            return int(float(str(value)))
        except (ValueError, TypeError):
            return default

    def _display_analysis(self, data: dict, console: Console) -> None:
        """Display parsed analysis."""
        overall = self._safe_int(data.get("overall", 0))
        color = "green" if overall >= 80 else "yellow" if overall >= 60 else "red"

        console.print(f"\n[bold]Overall Score: [{color}]{overall}/100[/{color}][/bold]")

        # Scores breakdown
        scores = data.get("scores", {})
        if scores:
            table = Table(title="Score Breakdown")
            table.add_column("Aspect", style="cyan")
            table.add_column("Score", justify="center")

            for aspect, score in scores.items():
                score = self._safe_int(score)
                score_color = "green" if score >= 80 else "yellow" if score >= 60 else "red"
                table.add_row(aspect.replace("_", " ").title(), f"[{score_color}]{score}[/{score_color}]")

            console.print(table)

        # Strengths
        strengths = data.get("strengths", [])
        if strengths:
            console.print("\n[green]Strengths:[/green]")
            for s in strengths[:3]:
                console.print(f"  ✓ {s}")

        # Weaknesses
        weaknesses = data.get("weaknesses", [])
        if weaknesses:
            console.print("\n[yellow]Weaknesses:[/yellow]")
            for w in weaknesses[:3]:
                console.print(f"  • {w}")

        # Specific suggestions
        suggestions = data.get("specific_suggestions", [])
        if suggestions:
            console.print("\n[cyan]Specific Suggestions:[/cyan]")
            for sug in suggestions[:3]:
                if isinstance(sug, dict):
                    console.print(f"  → {sug.get('issue', '')}: {sug.get('fix', '')}")
                else:
                    console.print(f"  → {sug}")

        # Summary
        summary = data.get("summary", "")
        if summary:
            console.print(f"\n[dim]{summary}[/dim]")

    def get_completions(self, partial: str) -> list[str]:
        """Get section name completions."""
        common_sections = [
            "Introduction", "Related Work", "Method", "Methods",
            "Experiments", "Results", "Discussion", "Conclusion",
            "Abstract", "Background", "Approach", "Evaluation",
        ]
        return [s for s in common_sections if s.lower().startswith(partial.lower())]

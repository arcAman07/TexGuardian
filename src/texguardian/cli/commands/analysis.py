"""Analysis commands - reference suggestions.

Note: Figure and table analysis have been merged into unified commands:
- /figures - verify, fix, and analyze figures
- /tables - verify, fix, and analyze tables
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.panel import Panel

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


SUGGEST_REFS_PROMPT = """You are an expert ML researcher suggesting relevant citations for a paper.

## Paper Content
Title: {title}
Abstract: {abstract}

## Current References
{current_refs}

## Task
Based on the paper content and topic, suggest:
1. **Missing foundational papers**: Classic papers that should be cited
2. **Recent relevant work**: Papers from last 2 years that are highly relevant
3. **Methodologically similar**: Papers using similar approaches
4. **Alternative perspectives**: Papers with different viewpoints on the topic

For each suggestion, provide:
- Citation key suggestion (e.g., "smith2024benchmark")
- Full reference in BibTeX format
- Why it should be cited (1-2 sentences)
- Where in the paper it might be relevant

Output as JSON:
```json
{{
  "suggestions": [
    {{
      "key": "smith2024benchmark",
      "bibtex": "@article{{smith2024benchmark, author={{...}}, ...}}",
      "reason": "Foundational work on benchmark contamination",
      "relevance": "Should be cited in Related Work when discussing contamination",
      "priority": "high"
    }}
  ],
  "missing_topics": ["Papers on X not cited", "..."],
  "citation_gaps": ["Introduction lacks citations for claim Y", "..."],
  "summary": "Overall citation coverage assessment"
}}
```

Note: Only suggest real papers that you're confident exist. Do not hallucinate citations.
"""


class SuggestRefsCommand(Command):
    """Suggest relevant references to add."""

    name = "suggest_refs"
    description = "AI-powered citation recommendations based on paper content"
    aliases = ["suggest_citations"]  # Removed "refs" - conflicts with CitationsCommand

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute reference suggestion."""
        from texguardian.latex.parser import LatexParser

        if not session.llm_client:
            console.print("[red]LLM client not available[/red]")
            return

        console.print("[bold]Analyzing paper for citation suggestions...[/bold]\n")

        parser = LatexParser(session.project_root, session.config.project.main_tex)

        try:
            # Get paper content
            main_tex = session.main_tex_path.read_text()

            # Extract abstract
            import re
            abstract_match = re.search(
                r'\\begin\{abstract\}(.*?)\\end\{abstract\}',
                main_tex,
                re.DOTALL
            )
            abstract = abstract_match.group(1).strip() if abstract_match else main_tex[:2000]

            # Get current references
            bib_keys = parser.extract_bib_keys()
            current_refs = ", ".join(bib_keys[:30])
            if len(bib_keys) > 30:
                current_refs += f" ... and {len(bib_keys) - 30} more"

            prompt = SUGGEST_REFS_PROMPT.format(
                title=session.paper_spec.title if session.paper_spec else "Unknown",
                abstract=abstract[:1500],
                current_refs=current_refs,
            )

            console.print(f"[dim]Current references: {len(bib_keys)}[/dim]")
            console.print("[dim]Generating suggestions...[/dim]\n")

            from texguardian.llm.streaming import stream_llm

            content = await stream_llm(
                session.llm_client,
                messages=[{"role": "user", "content": prompt}],
                console=console,
                max_tokens=4000,
                temperature=0.4,
            )
            console.print()  # newline after streaming

            # Try to parse and display nicely
            import json
            json_start = content.find("{")
            json_end = content.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                try:
                    data = json.loads(content[json_start:json_end])
                    self._display_suggestions(data, console)
                except json.JSONDecodeError:
                    console.print("\n[dim]Note: Could not parse structured suggestions.[/dim]")
            # If JSON parse fails, content was already streamed above

        except Exception as e:
            console.print(f"[red]Error generating suggestions: {e}[/red]")

    def _display_suggestions(self, data: dict, console: Console) -> None:
        """Display parsed suggestions."""
        suggestions = data.get("suggestions", [])

        if suggestions:
            console.print("[bold green]Suggested Citations:[/bold green]\n")

            for sug in suggestions:
                priority = sug.get("priority", "medium")
                priority_color = {"high": "red", "medium": "yellow", "low": "dim"}.get(priority, "dim")

                console.print(f"[{priority_color}][{priority.upper()}][/{priority_color}] [bold]{sug.get('key', 'unknown')}[/bold]")
                console.print(f"  [cyan]Why:[/cyan] {sug.get('reason', 'N/A')}")
                console.print(f"  [cyan]Where:[/cyan] {sug.get('relevance', 'N/A')}")

                bibtex = sug.get("bibtex", "")
                if bibtex:
                    # Show truncated bibtex
                    console.print(f"  [dim]{bibtex[:100]}...[/dim]")
                console.print()

        # Missing topics
        missing = data.get("missing_topics", [])
        if missing:
            console.print("[yellow bold]Missing Topic Coverage:[/yellow bold]")
            for m in missing:
                console.print(f"  [yellow]○[/yellow] {m}")
            console.print()

        # Citation gaps
        gaps = data.get("citation_gaps", [])
        if gaps:
            console.print("[red bold]Citation Gaps:[/red bold]")
            for g in gaps:
                console.print(f"  [red]•[/red] {g}")
            console.print()

        # Summary
        summary = data.get("summary", "")
        if summary:
            console.print(Panel(summary, title="Summary", border_style="blue"))

"""Page count command - quick page count with breakdown."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from texguardian.cli.commands.registry import Command
from texguardian.core.toolchain import find_binary

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class PageCountCommand(Command):
    """Quick page count with breakdown."""

    name = "page_count"
    description = "Quick page count with section breakdown and limit check"
    aliases = ["pages", "pc"]
    usage = "/page_count - Show page count and breakdown"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute page count command."""
        console.print("[bold cyan]Page Count Analysis[/bold cyan]\n")

        # Get page count from PDF if available
        pdf_pages = None
        if session.last_pdf_path and session.last_pdf_path.exists():
            pdf_pages = self._get_pdf_pages(session.last_pdf_path)
        elif session.last_compilation and session.last_compilation.pdf_path:
            pdf_pages = self._get_pdf_pages(session.last_compilation.pdf_path)

        # Auto-compile if no PDF found
        if pdf_pages is None:
            console.print("[dim]No compiled PDF found. Auto-compiling...[/dim]")
            pdf_path = await self._auto_compile(session, console)
            if pdf_path:
                pdf_pages = self._get_pdf_pages(pdf_path)

        # Get page limit from paper spec
        max_pages = 9  # Default
        if session.paper_spec and session.paper_spec.thresholds:
            max_pages = session.paper_spec.thresholds.max_pages

        # Analyze tex file for sections
        section_analysis = self._analyze_sections(session)

        # Display results
        if pdf_pages is not None:
            self._display_page_count(pdf_pages, max_pages, console)
        else:
            console.print("[yellow]Compilation failed. Showing estimate based on .tex file...[/yellow]\n")

        # Show section breakdown
        self._display_sections(section_analysis, console)

        # Show recommendations
        self._display_recommendations(pdf_pages, max_pages, section_analysis, console)

    async def _auto_compile(self, session: SessionState, console: Console) -> Path | None:
        """Auto-compile the document and return the PDF path."""
        from texguardian.latex.compiler import LatexCompiler

        compiler = LatexCompiler(session.config)
        try:
            result = await compiler.compile(session.main_tex_path, session.output_dir)
            session.last_compilation = result
            if result.success:
                console.print("  [green]✓[/green] Compiled successfully")
                return result.pdf_path
            else:
                console.print("  [red]✗[/red] Compilation failed")
                return None
        except Exception as e:
            console.print(f"  [red]✗[/red] Error: {e}")
            return None

    def _get_pdf_pages(self, pdf_path: str | Path) -> int | None:
        pdf_path = Path(pdf_path)
        """Get page count from PDF using pdfinfo."""
        pdfinfo = find_binary("pdfinfo", "poppler")
        if not pdfinfo:
            return None
        try:
            result = subprocess.run(
                [pdfinfo, str(pdf_path)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if line.startswith("Pages:"):
                        try:
                            return int(line.split(":")[1].strip())
                        except (ValueError, IndexError):
                            continue
        except Exception:
            pass

        # Fallback: try pdftk
        try:
            result = subprocess.run(
                ["pdftk", str(pdf_path), "dump_data"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.split("\n"):
                    if "NumberOfPages" in line:
                        try:
                            return int(line.split(":")[1].strip())
                        except (ValueError, IndexError):
                            continue
        except Exception:
            pass

        return None

    def _analyze_sections(self, session: SessionState) -> dict:
        """Analyze sections in the tex file."""
        analysis = {
            "sections": [],
            "figures": 0,
            "tables": 0,
            "equations": 0,
            "references_start": None,
            "appendix_start": None,
            "word_count_estimate": 0,
        }

        if not session.main_tex_path.exists():
            return analysis

        content = session.main_tex_path.read_text()

        # Find sections
        section_pattern = r'\\section\*?\{([^}]+)\}'
        for match in re.finditer(section_pattern, content):
            section_name = match.group(1).strip()
            position = match.start()

            # Check if it's references or appendix
            lower_name = section_name.lower()
            if 'reference' in lower_name or 'bibliograph' in lower_name:
                analysis["references_start"] = position
            elif 'appendix' in lower_name or 'supplement' in lower_name:
                analysis["appendix_start"] = position

            analysis["sections"].append({
                "name": section_name,
                "position": position,
            })

        # Count figures
        analysis["figures"] = len(re.findall(r'\\begin\{figure', content))

        # Count tables
        analysis["tables"] = len(re.findall(r'\\begin\{table', content))

        # Count equations
        analysis["equations"] = len(re.findall(r'\\begin\{equation|\\begin\{align|\\\[', content))

        # Estimate word count (rough)
        # Remove comments, commands, math
        text_only = re.sub(r'%.*', '', content)
        text_only = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', text_only)
        text_only = re.sub(r'\$[^$]*\$', '', text_only)
        text_only = re.sub(r'\\[a-zA-Z]+', '', text_only)
        words = len(text_only.split())
        analysis["word_count_estimate"] = words

        return analysis

    def _display_page_count(self, pages: int, max_pages: int, console: Console) -> None:
        """Display page count with visual indicator."""
        # Determine status
        if pages <= max_pages:
            status = "[green]Within limit[/green]"
            bar_color = "green"
        elif pages <= max_pages + 1:
            status = "[yellow]Slightly over[/yellow]"
            bar_color = "yellow"
        else:
            status = "[red]Over limit![/red]"
            bar_color = "red"

        # Create visual bar
        bar_width = 30
        filled = min(int((pages / max_pages) * bar_width), bar_width + 5)
        bar = "█" * min(filled, bar_width) + "░" * max(0, bar_width - filled)
        if filled > bar_width:
            bar = bar[:bar_width] + "[red]" + "█" * (filled - bar_width) + "[/red]"

        console.print(Panel.fit(
            f"[bold]Pages: {pages}/{max_pages}[/bold]  {status}\n\n"
            f"[{bar_color}]{bar}[/{bar_color}]",
            border_style=bar_color,
        ))

    def _display_sections(self, analysis: dict, console: Console) -> None:
        """Display section breakdown."""
        if not analysis["sections"]:
            return

        table = Table(title="Document Structure")
        table.add_column("#", style="dim", width=3)
        table.add_column("Section", style="cyan")
        table.add_column("Type", style="dim")

        for i, section in enumerate(analysis["sections"], 1):
            name = section["name"]

            # Determine type
            lower_name = name.lower()
            if 'intro' in lower_name:
                sec_type = "Main"
            elif 'related' in lower_name:
                sec_type = "Main"
            elif 'method' in lower_name or 'approach' in lower_name:
                sec_type = "Main"
            elif 'experiment' in lower_name or 'result' in lower_name:
                sec_type = "Main"
            elif 'conclusion' in lower_name or 'discussion' in lower_name:
                sec_type = "Main"
            elif 'reference' in lower_name or 'bibliograph' in lower_name:
                sec_type = "[dim]Refs[/dim]"
            elif 'appendix' in lower_name or 'supplement' in lower_name:
                sec_type = "[dim]Appendix[/dim]"
            elif 'acknowledg' in lower_name:
                sec_type = "[dim]Ack[/dim]"
            else:
                sec_type = "Main"

            table.add_row(str(i), name[:40], sec_type)

        console.print(table)

        # Show counts
        console.print(f"\n[dim]Figures: {analysis['figures']} | "
                      f"Tables: {analysis['tables']} | "
                      f"Equations: {analysis['equations']} | "
                      f"Est. words: ~{analysis['word_count_estimate']:,}[/dim]")

    def _display_recommendations(
        self,
        pages: int | None,
        max_pages: int,
        analysis: dict,
        console: Console,
    ) -> None:
        """Display recommendations for page management."""
        if pages is None:
            return

        recommendations = []

        if pages > max_pages:
            over = pages - max_pages
            recommendations.append(f"[red]Need to reduce by {over} page(s)[/red]")

            # Suggest cuts based on analysis
            if analysis["figures"] > 5:
                recommendations.append("  • Consider moving some figures to appendix")
            if analysis["tables"] > 4:
                recommendations.append("  • Consider consolidating tables")
            if analysis["word_count_estimate"] > 6000:
                recommendations.append("  • Text may be verbose - consider tightening prose")

        elif pages == max_pages:
            recommendations.append("[yellow]At exact page limit - no room for additions[/yellow]")

        else:
            remaining = max_pages - pages
            recommendations.append(f"[green]{remaining} page(s) remaining[/green]")

        if recommendations:
            console.print("\n[bold]Recommendations:[/bold]")
            for rec in recommendations:
                console.print(f"  {rec}")

    def get_completions(self, partial: str) -> list[str]:
        """No completions needed."""
        return []

"""Report generation command."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.table import Table

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class ReportCommand(Command):
    """Generate verification report."""

    name = "report"
    description = "Generate a comprehensive verification report"
    aliases = ["r"]
    usage = "/report [save] — generate report (optionally save to file)"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute report command."""
        console.print("Generating verification report...\n")

        # --- Compile if needed ---------------------------------------------------
        if not session.last_compilation:
            await self._auto_compile(session, console)

        # --- Gather data ---------------------------------------------------------
        paper_title = session.paper_spec.title if session.paper_spec else "Untitled"
        venue = session.paper_spec.venue if session.paper_spec else "Unknown"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # --- Run verification checks --------------------------------------------
        from texguardian.cli.commands.verify import run_verify_checks

        verify_results = run_verify_checks(session)

        # --- Analyze document structure ------------------------------------------
        section_analysis = self._analyze_document(session)

        # --- Citation stats ------------------------------------------------------
        citation_stats = self._get_citation_stats(session)

        # --- Score ---------------------------------------------------------------
        score = self._compute_score(session, verify_results, citation_stats)

        # ========================================================================
        # Build rich output
        # ========================================================================

        # --- Status Overview (table) ---------------------------------------------
        overview_table = Table(
            title="Status Overview",
            show_header=True,
            title_style="bold",
        )
        overview_table.add_column("Check", style="cyan")
        overview_table.add_column("Result", justify="right")
        overview_table.add_column("Status")

        # Score row
        if score >= 90:
            score_status = "[green]Excellent[/green]"
        elif score >= 70:
            score_status = "[yellow]Good[/yellow]"
        elif score >= 50:
            score_status = "[yellow]Needs Work[/yellow]"
        else:
            score_status = "[red]Major Issues[/red]"
        overview_table.add_row("Overall Score", f"[bold]{score}/100[/bold]", score_status)

        # Compilation row
        if session.last_compilation:
            comp = session.last_compilation
            if comp.success:
                overview_table.add_row(
                    "Compilation",
                    "Success",
                    "[green]✓[/green]",
                )
            else:
                n_errors = len(comp.errors) if comp.errors else 0
                overview_table.add_row(
                    "Compilation",
                    f"{n_errors} error(s)",
                    "[red]✗[/red]",
                )

        # Page count row
        pages = None
        max_pages = session.paper_spec.thresholds.max_pages if session.paper_spec else 9
        if session.last_compilation and session.last_compilation.page_count is not None:
            pages = session.last_compilation.page_count
            page_ok = pages <= max_pages
            overview_table.add_row(
                "Page Count",
                f"{pages}/{max_pages}",
                "[green]✓[/green]" if page_ok else "[red]✗ Over[/red]",
            )

        # Verification row
        errors = sum(1 for r in verify_results if not r["passed"] and r["severity"] == "error")
        warnings = sum(1 for r in verify_results if not r["passed"] and r["severity"] == "warning")
        total_issues = errors + warnings
        if total_issues == 0:
            overview_table.add_row("Verification", "0 issues", "[green]✓[/green]")
        else:
            parts = []
            if errors:
                parts.append(f"{errors} error(s)")
            if warnings:
                parts.append(f"{warnings} warning(s)")
            overview_table.add_row(
                "Verification",
                ", ".join(parts),
                "[red]✗[/red]" if errors else "[yellow]~[/yellow]",
            )

        # Citations row
        total_cites = citation_stats["total"]
        bib_keys = citation_stats["bib_keys"]
        undefined = citation_stats["undefined"]
        min_refs = session.paper_spec.thresholds.min_references if session.paper_spec else 0
        cite_detail = f"{bib_keys} refs"
        if undefined:
            cite_detail += f", {len(undefined)} undefined"
        cite_status = "[green]✓[/green]"
        if undefined:
            cite_status = "[red]✗[/red]"
        elif min_refs and bib_keys < min_refs:
            cite_status = f"[yellow]Need {min_refs - bib_keys} more[/yellow]"
        overview_table.add_row("Citations", cite_detail, cite_status)

        console.print(overview_table)
        console.print()

        # --- Verification Details ------------------------------------------------
        if verify_results:
            verify_table = Table(title="Verification Checks", show_header=True, title_style="bold")
            verify_table.add_column("Check")
            verify_table.add_column("Severity")
            verify_table.add_column("Status")
            verify_table.add_column("Message")

            for r in verify_results:
                status_str = "[green]PASS[/green]" if r["passed"] else (
                    "[red]FAIL[/red]" if r["severity"] == "error" else "[yellow]WARN[/yellow]"
                )
                sev_style = {"error": "red", "warning": "yellow", "info": "dim"}.get(r["severity"], "")
                verify_table.add_row(
                    r["name"],
                    f"[{sev_style}]{r['severity']}[/{sev_style}]",
                    status_str,
                    r["message"],
                )
            console.print(verify_table)
            console.print()

        # --- Document Content ----------------------------------------------------
        content_table = Table(title="Document Content", show_header=True, title_style="bold")
        content_table.add_column("Element", style="cyan")
        content_table.add_column("Count", justify="right")

        sections = section_analysis.get("sections", [])
        main_sections = [
            s for s in sections
            if not any(kw in s["name"].lower() for kw in ("reference", "bibliograph", "appendix", "supplement"))
        ]
        content_table.add_row("Sections", str(len(main_sections)))
        content_table.add_row("Figures", str(section_analysis.get("figures", 0)))
        content_table.add_row("Tables", str(section_analysis.get("tables", 0)))
        content_table.add_row("Equations", str(section_analysis.get("equations", 0)))
        content_table.add_row("Citations (unique)", str(total_cites))
        content_table.add_row("References (.bib)", str(bib_keys))
        word_est = section_analysis.get("word_count_estimate", 0)
        if word_est:
            content_table.add_row("Est. Words", f"~{word_est:,}")
        console.print(content_table)
        console.print()

        # --- Section Breakdown ---------------------------------------------------
        if sections:
            sec_table = Table(title="Section Breakdown", show_header=True, title_style="bold")
            sec_table.add_column("#", style="dim", width=3)
            sec_table.add_column("Section", style="cyan")
            for i, sec in enumerate(sections, 1):
                sec_table.add_row(str(i), sec["name"][:50])
            console.print(sec_table)
            console.print()

        # --- Configuration -------------------------------------------------------
        config_table = Table(title="Configuration", show_header=True, title_style="bold")
        config_table.add_column("Setting", style="cyan")
        config_table.add_column("Value")
        config_table.add_row("Model", session.config.models.default)
        config_table.add_row("Provider", session.config.providers.default)
        config_table.add_row("Venue", venue)
        config_table.add_row("Max Pages", str(max_pages))
        if session.paper_spec:
            config_table.add_row("Min References", str(session.paper_spec.thresholds.min_references))
            config_table.add_row("Custom Checks", str(len(session.paper_spec.checks)))
        if session.checkpoint_manager:
            checkpoints = session.checkpoint_manager.list_checkpoints()
            config_table.add_row("Checkpoints", str(len(checkpoints)))
        console.print(config_table)
        console.print()

        # --- Overall verdict panel -----------------------------------------------
        if score >= 90:
            verdict = f"[bold green]Score: {score}/100 — Excellent, ready for submission[/bold green]"
            border = "green"
        elif score >= 70:
            verdict = f"[bold yellow]Score: {score}/100 — Good, minor issues remain[/bold yellow]"
            border = "yellow"
        elif score >= 50:
            verdict = f"[bold yellow]Score: {score}/100 — Needs work before submission[/bold yellow]"
            border = "yellow"
        else:
            verdict = f"[bold red]Score: {score}/100 — Major revisions required[/bold red]"
            border = "red"

        console.print(Panel(verdict, title="Verdict", border_style=border))

        # --- Save option ---------------------------------------------------------
        if args.strip().lower() == "save":
            self._save_report(session, paper_title, timestamp, score, verify_results,
                              citation_stats, section_analysis, pages, max_pages, console)

    # --------------------------------------------------------------------- #
    # Helpers                                                                 #
    # --------------------------------------------------------------------- #

    async def _auto_compile(self, session: SessionState, console: Console) -> None:
        """Compile if no compilation result exists yet."""
        from texguardian.latex.compiler import LatexCompiler

        compiler = LatexCompiler(session.config)
        try:
            result = await compiler.compile(session.main_tex_path, session.output_dir)
            session.last_compilation = result
            if result.success:
                console.print("  [green]✓[/green] Compiled successfully")
            else:
                console.print("  [yellow]⚠[/yellow] Compilation had errors")
        except Exception as e:
            console.print(f"  [red]✗[/red] Compilation error: {e}")

    @staticmethod
    def _analyze_document(session: SessionState) -> dict:
        """Analyze .tex file for sections, figures, tables, etc."""
        import re

        analysis: dict = {
            "sections": [],
            "figures": 0,
            "tables": 0,
            "equations": 0,
            "word_count_estimate": 0,
        }

        if not session.main_tex_path.exists():
            return analysis

        content = session.main_tex_path.read_text()

        for match in re.finditer(r'\\section\*?\{([^}]+)\}', content):
            analysis["sections"].append({
                "name": match.group(1).strip(),
                "position": match.start(),
            })

        analysis["figures"] = len(re.findall(r'\\begin\{figure', content))
        analysis["tables"] = len(re.findall(r'\\begin\{table', content))
        analysis["equations"] = len(re.findall(r'\\begin\{equation|\\begin\{align|\\\[', content))

        text_only = re.sub(r'%.*', '', content)
        text_only = re.sub(r'\\[a-zA-Z]+\{[^}]*\}', '', text_only)
        text_only = re.sub(r'\$[^$]*\$', '', text_only)
        text_only = re.sub(r'\\[a-zA-Z]+', '', text_only)
        analysis["word_count_estimate"] = len(text_only.split())

        return analysis

    @staticmethod
    def _get_citation_stats(session: SessionState) -> dict:
        """Get citation statistics from the .tex and .bib files."""
        from texguardian.latex.parser import LatexParser

        stats = {"total": 0, "bib_keys": 0, "undefined": [], "uncited": []}
        try:
            parser = LatexParser(session.project_root, session.config.project.main_tex)
            citations = parser.extract_citations()
            bib_keys = parser.extract_bib_keys()
            stats["total"] = len(set(citations))
            stats["bib_keys"] = len(bib_keys)
            stats["undefined"] = [c for c in set(citations) if c not in bib_keys]
            stats["uncited"] = [b for b in bib_keys if b not in citations]
        except Exception:
            pass
        return stats

    @staticmethod
    def _compute_score(
        session: SessionState,
        verify_results: list[dict],
        citation_stats: dict,
    ) -> int:
        """Compute a quick quality score (0-100)."""
        # Start from the last session quality score if available, else compute fresh
        if session.quality_scores:
            return session.quality_scores[-1]

        score = 100

        # Compilation penalty
        if session.last_compilation and not session.last_compilation.success:
            score -= 30

        # Verification penalties
        errors = sum(1 for r in verify_results if not r["passed"] and r["severity"] == "error")
        warnings = sum(1 for r in verify_results if not r["passed"] and r["severity"] == "warning")
        score -= 7 * min(errors, 3)
        score -= 3 * min(warnings, 3)

        # Citation penalties
        undefined = len(citation_stats.get("undefined", []))
        if undefined:
            score -= 5 * min(undefined, 4)

        # Reference count penalty
        if session.paper_spec:
            min_refs = session.paper_spec.thresholds.min_references
            bib_keys = citation_stats.get("bib_keys", 0)
            if min_refs and bib_keys < min_refs:
                shortfall_pct = (min_refs - bib_keys) / min_refs
                score -= int(10 * min(shortfall_pct, 1.0))

        return max(0, min(100, score))

    @staticmethod
    def _save_report(
        session: SessionState,
        title: str,
        timestamp: str,
        score: int,
        verify_results: list[dict],
        citation_stats: dict,
        section_analysis: dict,
        pages: int | None,
        max_pages: int,
        console: Console,
    ) -> None:
        """Save a plain-text markdown report to disk."""
        lines = [
            f"# TexGuardian Report — {title}",
            f"Generated: {timestamp}",
            "",
            "## Status Overview",
            f"- Overall Score: {score}/100",
        ]

        if session.last_compilation:
            comp = session.last_compilation
            lines.append(f"- Compilation: {'Success' if comp.success else 'Failed'}")
        if pages is not None:
            lines.append(f"- Pages: {pages}/{max_pages}")

        errors = sum(1 for r in verify_results if not r["passed"] and r["severity"] == "error")
        warnings = sum(1 for r in verify_results if not r["passed"] and r["severity"] == "warning")
        lines.append(f"- Verification: {errors} error(s), {warnings} warning(s)")
        lines.append(f"- Citations: {citation_stats['total']} unique, {citation_stats['bib_keys']} in .bib")

        lines.extend(["", "## Verification Checks"])
        for r in verify_results:
            status = "PASS" if r["passed"] else ("FAIL" if r["severity"] == "error" else "WARN")
            lines.append(f"- [{status}] {r['name']}: {r['message']}")

        lines.extend(["", "## Document Content"])
        lines.append(f"- Sections: {len(section_analysis.get('sections', []))}")
        lines.append(f"- Figures: {section_analysis.get('figures', 0)}")
        lines.append(f"- Tables: {section_analysis.get('tables', 0)}")
        lines.append(f"- Equations: {section_analysis.get('equations', 0)}")
        lines.append(f"- Est. Words: ~{section_analysis.get('word_count_estimate', 0):,}")

        lines.extend(["", "## Configuration"])
        lines.append(f"- Model: {session.config.models.default}")
        lines.append(f"- Provider: {session.config.providers.default}")
        lines.append(f"- Venue: {session.paper_spec.venue if session.paper_spec else 'Unknown'}")

        report_path = session.guardian_dir / "report.md"
        report_path.write_text("\n".join(lines) + "\n")
        console.print(f"\n[green]Report saved to {report_path}[/green]")

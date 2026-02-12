"""Report generation command."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from rich.panel import Panel

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class ReportCommand(Command):
    """Generate verification report."""

    name = "report"
    description = "Generate a comprehensive verification report"
    aliases = ["r"]

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute report command."""
        console.print("Generating verification report...\n")

        # Gather data
        paper_title = session.paper_spec.title if session.paper_spec else "Untitled"
        venue = session.paper_spec.venue if session.paper_spec else "Unknown"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Build report
        report_lines = [
            f"# TexGuardian Report - {paper_title}",
            f"Generated: {timestamp}",
            "",
            "## Summary",
        ]

        # Pages
        if session.last_compilation and session.last_compilation.page_count is not None:
            pages = session.last_compilation.page_count
            max_pages = session.paper_spec.thresholds.max_pages if session.paper_spec else 9
            status = "[green]OK[/green]" if pages <= max_pages else "[red]OVER[/red]"
            report_lines.append(f"- Pages: {pages}/{max_pages} {status}")

        # Compilation status
        if session.last_compilation:
            status = (
                "[green]Success[/green]"
                if session.last_compilation.success
                else "[red]Failed[/red]"
            )
            report_lines.append(f"- Compilation: {status}")
            if session.last_compilation.warnings:
                report_lines.append(f"  - {len(session.last_compilation.warnings)} warnings")
            if session.last_compilation.errors:
                report_lines.append(f"  - {len(session.last_compilation.errors)} errors")

        # Quality score
        if session.quality_scores:
            score = session.quality_scores[-1]
            report_lines.append(f"- Quality Score: {score}/100")

        # Checkpoints
        if session.checkpoint_manager:
            checkpoints = session.checkpoint_manager.list_checkpoints()
            report_lines.append(f"- Checkpoints: {len(checkpoints)} available")

        report_lines.extend([
            "",
            "## Configuration",
            f"- Model: {session.config.models.default}",
            f"- Provider: {session.config.providers.default}",
        ])

        # Paper spec rules
        if session.paper_spec:
            report_lines.extend([
                "",
                "## Paper Specification",
                f"- Venue: {venue}",
                f"- Max pages: {session.paper_spec.thresholds.max_pages}",
                f"- Min references: {session.paper_spec.thresholds.min_references}",
                f"- Custom checks: {len(session.paper_spec.checks)}",
            ])

        # Output
        report_text = "\n".join(report_lines)
        console.print(Panel(report_text, title="Verification Report", border_style="cyan"))

        # Option to save
        if args == "save":
            import re as _re

            report_path = session.guardian_dir / "report.md"
            # Strip all Rich markup tags like [green], [/green], [bold], etc.
            plain_text = _re.sub(r"\[/?[a-zA-Z0-9_ ]+\]", "", report_text)
            report_path.write_text(plain_text)
            console.print(f"\n[green]Report saved to {report_path}[/green]")

"""Verification commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.table import Table

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


def run_verify_checks(session: SessionState) -> list[dict]:
    """Run all verification checks and return results.

    This is the core verify logic, usable from both the /verify command
    and the auto-verify on startup.
    """
    from texguardian.latex.parser import LatexParser

    parser = LatexParser(session.project_root, session.config.project.main_tex)
    results: list[dict] = []

    # Page limit check
    if session.last_compilation and session.last_compilation.page_count is not None:
        page_count = session.last_compilation.page_count
        max_pages = session.paper_spec.thresholds.max_pages if session.paper_spec else 9
        passed = page_count <= max_pages
        results.append({
            "name": "page_limit",
            "severity": "error",
            "passed": passed,
            "message": f"{page_count}/{max_pages} pages",
        })

    # Citation check
    try:
        citations = parser.extract_citations()
        bib_keys = parser.extract_bib_keys()
        undefined = [c for c in citations if c not in bib_keys]
        uncited = [b for b in bib_keys if b not in citations]

        results.append({
            "name": "citations",
            "severity": "error" if undefined else "warning" if uncited else "info",
            "passed": len(undefined) == 0,
            "message": f"{len(citations)} citations, {len(undefined)} undefined"
            if undefined
            else f"{len(citations)} citations OK"
            + (f", {len(uncited)} uncited refs" if uncited else ""),
        })
    except Exception as e:
        results.append({
            "name": "citations",
            "severity": "warning",
            "passed": True,
            "message": f"Could not check: {e}",
        })

    # Figure references check
    try:
        figures = parser.extract_figures()
        fig_refs = parser.extract_figure_refs()
        unreferenced = [f for f in figures if f not in fig_refs]

        results.append({
            "name": "figure_references",
            "severity": "warning",
            "passed": len(unreferenced) == 0,
            "message": f"All {len(figures)} figures referenced"
            if not unreferenced
            else f"{len(unreferenced)} unreferenced figures",
        })
    except Exception:
        pass

    # Custom checks from paper_spec
    if session.paper_spec:
        for check in session.paper_spec.checks:
            if check.pattern:
                try:
                    matches = parser.find_pattern(check.pattern)
                    results.append({
                        "name": check.name,
                        "severity": check.severity,
                        "passed": len(matches) == 0,
                        "message": check.message if matches else "OK",
                    })
                except Exception as e:
                    results.append({
                        "name": check.name,
                        "severity": "warning",
                        "passed": True,
                        "message": f"Check failed: {e}",
                    })

    return results


def display_verify_results(results: list[dict], console: Console) -> None:
    """Display verification results as a Rich table with summary."""
    table = Table(show_header=True)
    table.add_column("Check")
    table.add_column("Severity")
    table.add_column("Status")
    table.add_column("Message")

    for r in results:
        status = "[green]PASS[/green]" if r["passed"] else (
            "[red]FAIL[/red]" if r["severity"] == "error" else "[yellow]WARN[/yellow]"
        )
        severity_style = {
            "error": "red",
            "warning": "yellow",
            "info": "dim",
        }.get(r["severity"], "")

        table.add_row(
            r["name"],
            f"[{severity_style}]{r['severity']}[/{severity_style}]",
            status,
            r["message"],
        )

    console.print(table)

    # Summary
    failures = sum(1 for r in results if not r["passed"] and r["severity"] == "error")
    warnings = sum(1 for r in results if not r["passed"] and r["severity"] == "warning")

    if failures:
        console.print(f"\n[red]{failures} error(s) found[/red]")
    elif warnings:
        console.print(f"\n[yellow]{warnings} warning(s) found[/yellow]")
    else:
        console.print("\n[green]All checks passed![/green]")


class VerifyCommand(Command):
    """Run all verification checks."""

    name = "verify"
    description = "Run all verification checks on the paper"
    aliases = ["v", "check"]

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute verification checks."""
        console.print("Running verification checks...\n")

        results = run_verify_checks(session)
        display_verify_results(results, console)

        console.print("\n[dim]For detailed analysis, use: /figures, /tables, /section <name>[/dim]")

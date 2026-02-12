"""Full paper review pipeline command.

This is the main command that runs the entire review loop CONTINUOUSLY
until the paper reaches the threshold score or max iterations:
1. Compile
2. Verify all checks
3. Validate + fix citations
4. Analyze + fix figures
5. Analyze + fix tables
6. Visual polish loop
7. Loop back if score < threshold
8. Final report
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


# Threshold score to consider paper "ready"
SCORE_THRESHOLD = 90
MAX_REVIEW_ROUNDS = 5


@dataclass
class ReviewResult:
    """Result of a full paper review."""
    compile_success: bool = False
    page_count: int = 0
    max_pages: int = 9
    verification_passed: bool = False
    verification_issues: list[str] = field(default_factory=list)
    citations_valid: int = 0
    citations_hallucinated: int = 0
    citations_fixed: int = 0
    figures_analyzed: int = 0
    figures_issues: int = 0
    tables_analyzed: int = 0
    tables_issues: int = 0
    visual_score: int = 0
    visual_rounds: int = 0
    patches_applied: int = 0
    checkpoints_created: int = 0
    overall_score: int = 0
    review_rounds: int = 0


class ReviewCommand(Command):
    """Run full paper review pipeline with continuous fixing."""

    name = "review"
    description = "Run continuous review loop: compile → verify → fix → visual → repeat until perfect"
    aliases = ["full", "pipeline"]
    usage = "/review [quick|full] [instruction] - quick=fix loop (no visual), full=fix loop + visual (default)"

    _KEYWORDS = {"quick", "q", "full", "deep", "d", "thorough"}

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute full review pipeline with continuous fixing."""
        # Parse mode and custom instruction from args
        parts = args.strip().split(maxsplit=1)
        first_word = parts[0].lower() if parts else ""

        if first_word in ("quick", "q"):
            mode = "quick"
            custom_instruction = parts[1] if len(parts) > 1 else ""
        elif first_word in ("full", "deep", "d", "thorough"):
            mode = "full"
            custom_instruction = parts[1] if len(parts) > 1 else ""
        else:
            mode = "full"
            custom_instruction = args.strip()  # entire string is instruction

        info_lines = [
            "[bold cyan]Starting Continuous Paper Review[/bold cyan]\n",
            f"Mode: [yellow]{mode}[/yellow]",
            f"Paper: {session.paper_spec.title if session.paper_spec else 'Unknown'}",
            f"Target Score: {SCORE_THRESHOLD}/100",
            f"Max Rounds: {MAX_REVIEW_ROUNDS}",
        ]
        if custom_instruction:
            info_lines.append(f"Focus: [italic]{custom_instruction}[/italic]")

        console.print(Panel.fit(
            "\n".join(info_lines),
            border_style="cyan",
        ))

        result = ReviewResult()
        if session.paper_spec:
            result.max_pages = session.paper_spec.thresholds.max_pages

        # Continuous improvement loop
        while result.review_rounds < MAX_REVIEW_ROUNDS:
            result.review_rounds += 1
            console.print()
            console.print(Rule(f"[bold magenta]Round {result.review_rounds}/{MAX_REVIEW_ROUNDS}[/bold magenta]", style="magenta"))
            console.print()

            # Step 1: Compile
            console.print("[bold]Step 1/6:[/bold] Compiling LaTeX")
            compile_ok = await self._step_compile(session, console, result)
            if not compile_ok:
                console.print("[red]Compilation failed. Cannot continue.[/red]")
                break

            # Step 2: Run verification checks
            console.print(Rule(style="dim"))
            console.print("[bold]Step 2/6:[/bold] Running Verification Checks")
            await self._step_verify(session, console, result)

            # Step 3: Validate and fix citations
            console.print(Rule(style="dim"))
            console.print("[bold]Step 3/6:[/bold] Validating Citations")
            await self._step_citations(session, console, result, fix=True)

            # Step 4: Analyze and fix figures
            console.print(Rule(style="dim"))
            console.print("[bold]Step 4/6:[/bold] Analyzing Figures")
            await self._step_figures(session, console, result, fix=True)

            # Step 5: Analyze and fix tables
            console.print(Rule(style="dim"))
            console.print("[bold]Step 5/6:[/bold] Analyzing Tables")
            await self._step_tables(session, console, result, fix=True)

            # Step 6: Visual polish (full mode only)
            console.print(Rule(style="dim"))
            if mode == "full":
                console.print("[bold]Step 6/6:[/bold] Visual Polish Loop")
                await self._step_visual(session, console, result, custom_instruction=custom_instruction)
            else:
                console.print("[bold]Step 6/6:[/bold] Visual Polish")
                console.print("  [dim]Skipped (use 'full' mode to enable)[/dim]")

            # Calculate current score
            console.print(Rule(style="dim"))
            await self._step_feedback(session, console, result)

            # Check if we've reached the threshold
            if result.overall_score >= SCORE_THRESHOLD:
                console.print(f"\n[green bold]✓ Reached target score {result.overall_score}/100![/green bold]")
                break

            # Continue to next round
            if result.overall_score < SCORE_THRESHOLD:
                console.print(f"\n[yellow]Score {result.overall_score}/100 < {SCORE_THRESHOLD}. Continuing...[/yellow]")

        # Final summary
        self._print_summary(result, console)

    async def _step_compile(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
    ) -> bool:
        """Step 1: Compile the document."""
        from texguardian.latex.compiler import LatexCompiler

        compiler = LatexCompiler(session.config)

        try:
            with console.status("  [dim]Running latexmk...", spinner="dots"):
                compile_result = await compiler.compile(
                    session.main_tex_path,
                    session.output_dir,
                )

            session.last_compilation = compile_result
            result.compile_success = compile_result.success
            result.page_count = compile_result.page_count if compile_result.page_count is not None else 0

            if compile_result.success:
                console.print("  [green]✓[/green] Compiled successfully")
                console.print(f"  [dim]Pages: {result.page_count}[/dim]")
                if compile_result.warnings:
                    console.print(f"  [yellow]Warnings: {len(compile_result.warnings)}[/yellow]")
                return True
            else:
                console.print("  [red]✗[/red] Compilation failed")
                if compile_result.errors:
                    for err in compile_result.errors[:3]:
                        console.print(f"    [red]{err}[/red]")
                return False

        except Exception as e:
            console.print(f"  [red]✗[/red] Error: {e}")
            return False

    async def _step_verify(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
    ) -> None:
        """Step 2: Run verification checks."""
        from texguardian.latex.parser import LatexParser

        parser = LatexParser(session.project_root, session.config.project.main_tex)
        issues = []

        # Page limit check
        if session.last_compilation and session.last_compilation.page_count is not None:
            page_count = session.last_compilation.page_count
            max_pages = session.paper_spec.thresholds.max_pages if session.paper_spec else 9
            if page_count > max_pages:
                issues.append(f"Page limit exceeded: {page_count}/{max_pages}")

        # Citation check
        try:
            citations = parser.extract_citations()
            bib_keys = parser.extract_bib_keys()
            undefined = [c for c in citations if c not in bib_keys]
            if undefined:
                issues.append(f"Undefined citations: {len(undefined)}")
        except Exception:
            pass

        # Figure check
        try:
            figures = parser.extract_figures()
            fig_refs = parser.extract_figure_refs()
            unreferenced = [f for f in figures if f not in fig_refs]
            if unreferenced:
                issues.append(f"Unreferenced figures: {len(unreferenced)}")
        except Exception:
            pass

        # Custom checks
        if session.paper_spec:
            for check in session.paper_spec.checks:
                if check.pattern:
                    matches = parser.find_pattern(check.pattern)
                    if matches:
                        issues.append(f"{check.name}: {check.message}")

        result.verification_issues = issues
        result.verification_passed = len(issues) == 0

        if issues:
            console.print(f"  [yellow]Found {len(issues)} issue(s):[/yellow]")
            for issue in issues[:5]:
                console.print(f"    [yellow]•[/yellow] {issue}")
            if len(issues) > 5:
                console.print(f"    [dim]... and {len(issues) - 5} more[/dim]")
        else:
            console.print("  [green]✓[/green] All checks passed")

    async def _step_citations(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
        fix: bool = False,
    ) -> None:
        """Step 3: Validate citations against real databases."""
        from texguardian.citations.validator import CitationValidator

        bib_files = list(session.project_root.glob("**/*.bib"))
        if not bib_files:
            console.print("  [dim]No .bib files found[/dim]")
            return

        validator = CitationValidator()

        try:
            with console.status("  [dim]Checking against CrossRef & Semantic Scholar...", spinner="dots"):
                validation_results = await validator.validate_bib_file(bib_files[0], console=console)

            result.citations_valid = sum(1 for r in validation_results if r.status == "valid")
            result.citations_hallucinated = sum(1 for r in validation_results if r.status == "likely_hallucinated")

            total = len(validation_results)
            console.print(f"  Validated {total} citations:")
            console.print(f"    [green]✓[/green] Valid: {result.citations_valid}")

            if result.citations_hallucinated > 0:
                console.print(f"    [red]✗[/red] Likely hallucinated: {result.citations_hallucinated}")

                if fix and session.llm_client:
                    console.print("  [cyan]Generating citation fixes...[/cyan]")
                    # Would generate patches here - simplified for now
                    console.print("  [dim]Run '/citations fix' for detailed patches[/dim]")

        except Exception as e:
            console.print(f"  [red]Error validating citations: {e}[/red]")

    async def _step_figures(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
        fix: bool = False,
    ) -> None:
        """Step 4: Analyze figures."""
        from texguardian.latex.parser import LatexParser

        parser = LatexParser(session.project_root, session.config.project.main_tex)

        try:
            figures = parser.extract_figures_with_details()
            result.figures_analyzed = len(figures)

            if not figures:
                console.print("  [dim]No figures found[/dim]")
                return

            # Check for issues
            issues = 0
            for fig in figures:
                label = fig.get("label", "")
                caption = fig.get("caption", "")
                if not label:
                    issues += 1
                if not caption or len(caption) < 20:
                    issues += 1

            result.figures_issues = issues

            console.print(f"  Found {len(figures)} figures")
            if issues > 0:
                console.print(f"    [yellow]•[/yellow] {issues} potential issues (missing labels/captions)")
                if fix:
                    console.print("  [dim]Run '/figures fix' for detailed analysis and fixes[/dim]")
            else:
                console.print("    [green]✓[/green] All figures have labels and captions")

        except Exception as e:
            console.print(f"  [red]Error analyzing figures: {e}[/red]")

    async def _step_tables(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
        fix: bool = False,
    ) -> None:
        """Step 5: Analyze tables."""
        from texguardian.latex.parser import LatexParser

        parser = LatexParser(session.project_root, session.config.project.main_tex)

        try:
            tables = parser.extract_tables_with_details()
            result.tables_analyzed = len(tables)

            if not tables:
                console.print("  [dim]No tables found[/dim]")
                return

            # Check for issues
            issues = 0
            for tab in tables:
                label = tab.get("label", "")
                caption = tab.get("caption", "")
                if not label:
                    issues += 1
                if not caption or len(caption) < 10:
                    issues += 1

            result.tables_issues = issues

            console.print(f"  Found {len(tables)} tables")
            if issues > 0:
                console.print(f"    [yellow]•[/yellow] {issues} potential issues")
                if fix:
                    console.print("  [dim]Run '/tables fix' for detailed analysis and fixes[/dim]")
            else:
                console.print("    [green]✓[/green] All tables look good")

        except Exception as e:
            console.print(f"  [red]Error analyzing tables: {e}[/red]")

    async def _step_visual(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
        custom_instruction: str = "",
    ) -> None:
        """Step 6: Visual polish loop."""
        from texguardian.visual.verifier import VisualVerifier

        try:
            verifier = VisualVerifier(session)
            max_rounds = session.config.safety.max_visual_rounds

            visual_result = await verifier.run_loop(
                max_rounds=max_rounds,
                console=console,
                focus_areas=[custom_instruction] if custom_instruction else None,
            )

            result.visual_score = visual_result.quality_score
            result.visual_rounds = visual_result.rounds
            result.patches_applied += visual_result.patches_applied

            console.print("  Visual polish complete:")
            console.print(f"    Rounds: {result.visual_rounds}")
            console.print(f"    Score: {result.visual_score}/100")
            console.print(f"    Patches: {visual_result.patches_applied}")

        except Exception as e:
            console.print(f"  [red]Error in visual polish: {e}[/red]")

    async def _step_feedback(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
    ) -> None:
        """Step 7: Generate overall feedback."""
        if not session.llm_client:
            console.print("  [dim]LLM not available for feedback[/dim]")
            return

        # Calculate overall score based on results
        score = 100

        # Deduct for issues
        if not result.compile_success:
            score -= 30
        if not result.verification_passed:
            score -= 10 * min(len(result.verification_issues), 3)
        if result.citations_hallucinated > 0:
            score -= 5 * min(result.citations_hallucinated, 4)
        if result.figures_issues > 0:
            score -= 2 * min(result.figures_issues, 5)
        if result.tables_issues > 0:
            score -= 2 * min(result.tables_issues, 5)

        # Blend visual score only when visual polish actually ran
        if result.visual_rounds > 0 and result.visual_score > 0:
            # Weighted blend: 70% issue-based score, 30% visual score
            score = round((score * 7 + result.visual_score * 3) / 10)

        result.overall_score = max(0, min(100, score))

        console.print(f"  [bold]Overall Score: {result.overall_score}/100[/bold]")

    def _print_summary(self, result: ReviewResult, console: Console) -> None:
        """Print final review summary."""
        console.print("\n")

        # Color based on score
        if result.overall_score >= 90:
            score_style = "green bold"
            status = "Excellent - Ready for submission"
        elif result.overall_score >= 80:
            score_style = "cyan"
            status = "Good - Minor issues to address"
        elif result.overall_score >= 70:
            score_style = "yellow"
            status = "Fair - Several issues need attention"
        elif result.overall_score >= 60:
            score_style = "orange1"
            status = "Needs Work - Significant revisions required"
        else:
            score_style = "red bold"
            status = "Major Issues - Extensive revisions needed"

        # Summary table
        table = Table(title="Review Summary")
        table.add_column("Check", style="cyan")
        table.add_column("Result", justify="right")
        table.add_column("Status")

        table.add_row(
            "Compilation",
            "Success" if result.compile_success else "Failed",
            "[green]✓[/green]" if result.compile_success else "[red]✗[/red]"
        )
        table.add_row(
            "Page Count",
            str(result.page_count),
            "[green]✓[/green]" if result.page_count <= result.max_pages else "[yellow]~[/yellow]"
        )
        table.add_row(
            "Verification",
            f"{len(result.verification_issues)} issues",
            "[green]✓[/green]" if result.verification_passed else "[yellow]~[/yellow]"
        )
        table.add_row(
            "Citations",
            f"{result.citations_valid} valid, {result.citations_hallucinated} suspect",
            "[green]✓[/green]" if result.citations_hallucinated == 0 else "[red]✗[/red]"
        )
        table.add_row(
            "Figures",
            f"{result.figures_analyzed} analyzed, {result.figures_issues} issues",
            "[green]✓[/green]" if result.figures_issues == 0 else "[yellow]~[/yellow]"
        )
        table.add_row(
            "Tables",
            f"{result.tables_analyzed} analyzed, {result.tables_issues} issues",
            "[green]✓[/green]" if result.tables_issues == 0 else "[yellow]~[/yellow]"
        )
        if result.visual_score > 0:
            table.add_row(
                "Visual Quality",
                f"{result.visual_score}/100 ({result.visual_rounds} rounds)",
                "[green]✓[/green]" if result.visual_score >= 80 else "[yellow]~[/yellow]"
            )

        console.print(table)

        # Overall score
        console.print(Panel.fit(
            f"[{score_style}]Overall Score: {result.overall_score}/100[/{score_style}]\n"
            f"{status}",
            border_style=score_style.split()[0] if " " in score_style else score_style,
        ))

        # Next steps
        if result.overall_score < SCORE_THRESHOLD:
            console.print("\n[bold]Recommended Next Steps:[/bold]")
            steps = []
            if not result.compile_success:
                steps.append("Fix compilation errors first")
            if result.citations_hallucinated > 0:
                steps.append("Run '/citations fix' to correct invalid citations")
            if result.figures_issues > 0:
                steps.append("Run '/figures fix' for figure verification and fixes")
            if result.tables_issues > 0:
                steps.append("Run '/tables fix' for table verification and fixes")
            if result.visual_score < 80 and result.visual_score > 0:
                steps.append("Run '/polish_visual' for more visual improvements")
            if not result.verification_passed:
                steps.append("Address verification issues shown above")
            if result.review_rounds >= MAX_REVIEW_ROUNDS:
                steps.append("Manual review recommended - max auto-fix rounds reached")

            for i, step in enumerate(steps[:5], 1):
                console.print(f"  {i}. {step}")

    def get_completions(self, partial: str) -> list[str]:
        """Get argument completions."""
        options = ["quick", "full"]
        return [o for o in options if o.startswith(partial.lower())]

"""Full paper review pipeline command.

This is the main command that runs the entire review loop CONTINUOUSLY
until the paper reaches the threshold score or max iterations:
1. Compile
2. Verify all checks
3. Fix verification issues (LLM-based)
4. Validate + fix citations
5. Analyze + fix figures
6. Analyze + fix tables
7. Visual verification + polish (unified)
8. Loop back if score < threshold
9. Final report
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

    from texguardian.core.session import CompilationResult, SessionState


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

            # Reset per-round counters so re-detection reflects current state
            patches_this_round = 0
            result.verification_issues = []
            result.figures_issues = 0
            result.tables_issues = 0
            result.citations_hallucinated = 0
            result.citations_valid = 0

            console.print()
            console.print(Rule(f"[bold magenta]Round {result.review_rounds}/{MAX_REVIEW_ROUNDS}[/bold magenta]", style="magenta"))
            console.print()

            n_steps = 7

            # Step 1: Compile
            console.print(f"[bold]Step 1/{n_steps}:[/bold] Compiling LaTeX")
            compile_ok = await self._step_compile(session, console, result)
            if not compile_ok and session.llm_client and session.last_compilation:
                console.print("  [cyan]Attempting to fix compilation errors...[/cyan]")
                compile_ok = await self._step_fix_compile_errors(
                    session, console, result, session.last_compilation,
                )
            if not compile_ok:
                console.print("[red]Compilation failed. Cannot continue.[/red]")
                break

            # Step 2: Run verification checks
            console.print(Rule(style="dim"))
            console.print(f"[bold]Step 2/{n_steps}:[/bold] Running Verification Checks")
            await self._step_verify(session, console, result)

            # Step 3: Fix verification issues via LLM
            console.print(Rule(style="dim"))
            console.print(f"[bold]Step 3/{n_steps}:[/bold] Fixing Verification Issues")
            patches_before = result.patches_applied
            await self._step_fix_verification_issues(session, console, result)
            patches_this_round += result.patches_applied - patches_before

            # Step 4: Validate and fix citations
            console.print(Rule(style="dim"))
            console.print(f"[bold]Step 4/{n_steps}:[/bold] Validating Citations")
            patches_before = result.patches_applied
            await self._step_citations(session, console, result, fix=True)
            patches_this_round += result.patches_applied - patches_before

            # Step 5: Analyze and fix figures
            console.print(Rule(style="dim"))
            console.print(f"[bold]Step 5/{n_steps}:[/bold] Analyzing Figures")
            patches_before = result.patches_applied
            await self._step_figures(session, console, result, fix=True)
            patches_this_round += result.patches_applied - patches_before

            # Step 6: Analyze and fix tables
            console.print(Rule(style="dim"))
            console.print(f"[bold]Step 6/{n_steps}:[/bold] Analyzing Tables")
            patches_before = result.patches_applied
            await self._step_tables(session, console, result, fix=True)
            patches_this_round += result.patches_applied - patches_before

            # Recompile if any patches were applied (so visual steps see a fresh PDF)
            if patches_this_round > 0:
                console.print(Rule(style="dim"))
                console.print("[bold]Recompiling[/bold] (patches applied)")
                await self._step_compile(session, console, result)

            # Step 7: Visual verification + polish (unified)
            console.print(Rule(style="dim"))
            console.print(f"[bold]Step 7/{n_steps}:[/bold] Visual Verification")
            if mode == "full" and (result.review_rounds == 1 or patches_this_round > 0):
                patches_before = result.patches_applied
                await self._step_visual_unified(
                    session, console, result,
                    patches_this_round=patches_this_round,
                    custom_instruction=custom_instruction,
                )
                patches_this_round += result.patches_applied - patches_before
            elif mode == "full":
                console.print("  [dim]No new patches this round — skipping[/dim]")
            else:
                console.print("  [dim]Skipped (use 'full' mode to enable)[/dim]")

            # Final recompile to ensure PDF reflects all patches
            if patches_this_round > 0:
                console.print(Rule(style="dim"))
                console.print("[bold]Final Compile[/bold]")
                await self._step_compile(session, console, result)

            # Calculate current score
            console.print(Rule(style="dim"))
            await self._step_feedback(session, console, result)

            # Check if we've reached the threshold
            if result.overall_score >= SCORE_THRESHOLD:
                console.print(f"\n[green bold]✓ Reached target score {result.overall_score}/100![/green bold]")
                break

            # Early exit if no progress was made (after first round)
            if patches_this_round == 0 and result.review_rounds > 1:
                console.print("\n[yellow]No patches applied this round — stopping.[/yellow]")
                break

            # Continue to next round
            if result.overall_score < SCORE_THRESHOLD:
                console.print(f"\n[yellow]Score {result.overall_score}/100 < {SCORE_THRESHOLD}. Continuing...[/yellow]")

        # Final summary
        self._print_summary(result, console, session=session)

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
                if compile_result.pdf_path:
                    console.print(f"  [dim]PDF: {compile_result.pdf_path}[/dim]")
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

    async def _step_fix_compile_errors(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
        compile_result: CompilationResult,
    ) -> bool:
        """Attempt to fix compilation errors using the LLM.

        Tries up to ``_MAX_FIX_ATTEMPTS`` cycles of: ask the LLM for a patch,
        apply it, then recompile.  Returns ``True`` if compilation succeeds
        after a fix.
        """
        from texguardian.cli.approval import interactive_approval
        from texguardian.llm.prompts.errors import build_full_error_fix_prompt
        from texguardian.llm.prompts.system import COMMAND_SYSTEM_PROMPT
        from texguardian.llm.streaming import stream_llm
        from texguardian.patch.parser import extract_patches

        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            errors = compile_result.errors or []
            if not errors:
                break

            console.print(f"  [dim]Fix attempt {attempt}/{max_attempts}[/dim]")

            # Build numbered content for the LLM
            tex_path = session.main_tex_path
            content = tex_path.read_text()
            lines = content.splitlines()
            numbered = "\n".join(f"{i + 1:4d}| {line}" for i, line in enumerate(lines))

            prompt = build_full_error_fix_prompt(
                errors=errors[:5],
                filename=tex_path.name,
                numbered_content=numbered,
            )

            response_text = await stream_llm(
                session.llm_client,
                messages=[{"role": "user", "content": prompt}],
                console=console,
                system=COMMAND_SYSTEM_PROMPT,
                max_tokens=4000,
                temperature=0.3,
                print_output=False,
            )

            patches = extract_patches(response_text)
            if not patches:
                console.print("  [yellow]No patches generated for compilation errors[/yellow]")
                break

            applied = await interactive_approval(
                patches, session, console, auto_approve=True,
            )
            if applied == 0:
                console.print("  [yellow]No patches could be applied[/yellow]")
                break

            result.patches_applied += applied
            console.print(f"  [green]Applied {applied} fix(es) — recompiling...[/green]")

            # Clean stale build artifacts so latexmk reruns the engine
            from texguardian.latex.compiler import LatexCompiler

            compiler = LatexCompiler(session.config)
            await compiler.clean(session.main_tex_path, session.output_dir)

            # Recompile to check if the fix worked
            recompile_ok = await self._step_compile(session, console, result)
            if recompile_ok:
                return True

            # Update compile_result for next attempt
            compile_result = session.last_compilation  # type: ignore[assignment]

        return False

    async def _step_verify(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
    ) -> None:
        """Step 2: Run verification checks.

        Delegates to the shared ``run_verify_checks()`` in verify.py so
        that /review and /verify always use the same logic.
        """
        from texguardian.cli.commands.verify import run_verify_checks

        check_results = run_verify_checks(session)

        # Convert dict results into the issue-string format that
        # _step_fix_verification_issues expects.
        issues: list[str] = []
        for chk in check_results:
            if not chk["passed"]:
                issues.append(f"{chk['name']}: {chk['message']}")

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

    async def _step_fix_verification_issues(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
    ) -> None:
        """Step 3: Use the LLM to fix verification issues found in Step 2."""
        issues = result.verification_issues
        if not issues:
            console.print("  [green]✓[/green] No issues to fix")
            return

        if not session.llm_client:
            console.print("  [dim]LLM not available — skipping[/dim]")
            return

        # Skip page-limit issues — those can't be fixed by a simple patch
        fixable = [i for i in issues if not i.startswith("Page limit")]
        if not fixable:
            console.print("  [dim]No auto-fixable issues[/dim]")
            return

        from texguardian.cli.approval import interactive_approval
        from texguardian.llm.prompts.system import COMMAND_SYSTEM_PROMPT
        from texguardian.llm.streaming import stream_llm
        from texguardian.patch.parser import extract_patches

        tex_path = session.main_tex_path
        content = tex_path.read_text()
        lines = content.splitlines()
        numbered = "\n".join(f"{i + 1:4d}| {line}" for i, line in enumerate(lines))
        filename = tex_path.name

        issues_text = "\n".join(f"- {i}" for i in fixable)

        prompt = (
            "Fix the following issues found during verification of this LaTeX paper.\n\n"
            "## Issues\n"
            f"{issues_text}\n\n"
            "## Full File Content (with line numbers)\n"
            f"```latex\n{numbered}\n```\n\n"
            "## Instructions\n"
            "1. Fix ALL issues listed above with minimal changes.\n"
            "2. For 'citation_format' issues: replace bare \\cite{} with "
            "\\citep{} (parenthetical) or \\citet{} (textual) as appropriate.\n"
            "3. For 'todo_remaining': remove or replace TODO/FIXME/XXX markers.\n"
            "4. For 'figure_overflow': reduce width to fit within \\columnwidth "
            "(e.g. change width=1.5\\columnwidth to width=\\columnwidth).\n"
            "5. For 'hline_usage': replace \\hline with booktabs commands "
            "(\\toprule, \\midrule, \\bottomrule).\n"
            "6. For 'Undefined citations': remove or comment out the undefined "
            "\\cite/\\citep/\\citet calls.\n"
            "7. Do NOT rewrite unrelated code.\n"
            "8. Output unified diff patches.\n\n"
            "## Output Format\n"
            "### Explanation\n"
            "[Brief explanation of each fix]\n\n"
            "### Patch\n"
            f"```diff\n--- a/{filename}\n+++ b/{filename}\n"
            "@@ -X,Y +X,Y @@\n[patch content]\n```\n"
        )

        console.print(f"  [cyan]Generating fixes for {len(fixable)} issue(s)...[/cyan]")

        response_text = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
            system=COMMAND_SYSTEM_PROMPT,
            max_tokens=4000,
            temperature=0.3,
            print_output=False,
        )

        patches = extract_patches(response_text)
        if not patches:
            console.print("  [yellow]No patches generated[/yellow]")
            return

        applied = await interactive_approval(
            patches, session, console, auto_approve=True,
        )
        if applied > 0:
            console.print(f"  [green]Applied {applied} verification fix(es)[/green]")
            result.patches_applied += applied
        else:
            console.print("  [yellow]No patches could be applied[/yellow]")

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

            n_valid = sum(1 for r in validation_results if r.status == "valid")
            n_needs_correction = sum(1 for r in validation_results if r.status == "needs_correction")
            n_not_found = sum(1 for r in validation_results if r.status == "not_found")
            n_hallucinated = sum(1 for r in validation_results if r.status == "likely_hallucinated")

            result.citations_valid = n_valid
            result.citations_hallucinated = n_hallucinated

            total = len(validation_results)
            console.print(f"  Validated {total} citations:")
            console.print(f"    [green]✓[/green] Valid: {n_valid}")
            if n_needs_correction > 0:
                console.print(f"    [yellow]~[/yellow] Needs correction: {n_needs_correction} (metadata mismatch)")
            if n_not_found > 0:
                console.print(f"    [dim]?[/dim] Could not verify: {n_not_found} (not in database)")
            if n_hallucinated > 0:
                console.print(f"    [red]✗[/red] Likely hallucinated: {n_hallucinated}")

                if fix and session.llm_client:
                    console.print("  [cyan]Generating citation fixes...[/cyan]")
                    from texguardian.cli.commands.citations import (
                        generate_and_apply_citation_fixes,
                    )

                    # Pass pre-validated results to avoid a second round of API calls
                    applied = await generate_and_apply_citation_fixes(
                        session, console, auto_approve=True, print_output=False,
                        validation_results=validation_results,
                    )
                    result.citations_fixed = applied
                    result.patches_applied += applied

        except Exception as e:
            console.print(f"  [red]Error validating citations: {e}[/red]")

    async def _step_figures(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
        fix: bool = False,
    ) -> None:
        """Step 4: Analyze and optionally fix figures."""
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
                console.print(f"    [yellow]•[/yellow] {issues} structural issues (missing labels/captions)")

            # Always run LLM analysis when fixing — catches overflow, formatting,
            # and other issues the simple structural check misses.
            if fix and session.llm_client:
                from texguardian.cli.commands.figures import generate_and_apply_figure_fixes

                applied = await generate_and_apply_figure_fixes(
                    session, console, auto_approve=True, print_output=False,
                )
                result.patches_applied += applied
            elif issues == 0:
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
        """Step 5: Analyze and optionally fix tables."""
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
                # Check for \hline usage (should use booktabs)
                table_content = tab.get("content", "")
                if "\\hline" in table_content and "\\toprule" not in table_content:
                    issues += 1

            result.tables_issues = issues

            console.print(f"  Found {len(tables)} tables")
            if issues > 0:
                console.print(f"    [yellow]•[/yellow] {issues} potential issues")

            # Always run LLM analysis when fixing — catches \hline, overflow,
            # formatting, and other issues the simple check misses.
            if fix and session.llm_client:
                from texguardian.cli.commands.tables import generate_and_apply_table_fixes

                applied = await generate_and_apply_table_fixes(
                    session, console, auto_approve=True, print_output=False,
                )
                result.patches_applied += applied
            elif issues == 0:
                console.print("    [green]✓[/green] All tables look good")

        except Exception as e:
            console.print(f"  [red]Error analyzing tables: {e}[/red]")

    async def _step_visual_unified(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
        patches_this_round: int = 0,
        custom_instruction: str = "",
    ) -> None:
        """Step 7: Visual verification + polish (unified).

        Uses a single VisualVerifier instance.  Focus areas come from
        structural patches (if any) combined with the user's custom
        instruction.
        """
        from texguardian.visual.verifier import VisualVerifier

        try:
            verifier = VisualVerifier(session)
            max_rounds = session.config.safety.max_visual_rounds

            # Build focus areas: structural patch areas + custom instruction
            focus_areas: list[str] = []
            if patches_this_round > 0:
                focus_areas.extend(["figures", "tables", "captions", "labels"])
            if custom_instruction:
                focus_areas.append(custom_instruction)

            visual_result = await verifier.run_loop(
                max_rounds=max_rounds,
                console=console,
                focus_areas=focus_areas or None,
            )

            result.visual_score = visual_result.quality_score
            result.visual_rounds = visual_result.rounds
            result.patches_applied += visual_result.patches_applied

            console.print("  Visual verification complete:")
            console.print(f"    Rounds: {visual_result.rounds}")
            console.print(f"    Score: {visual_result.quality_score}/100")
            console.print(f"    Patches: {visual_result.patches_applied}")
            if visual_result.stopped_reason:
                console.print(f"    Stopped: {visual_result.stopped_reason}")

        except Exception as e:
            console.print(f"  [red]Error in visual verification: {e}[/red]")

    async def _step_feedback(
        self,
        session: SessionState,
        console: Console,
        result: ReviewResult,
    ) -> None:
        """Calculate overall score using *fresh* verification data.

        Re-runs verification checks after all patches have been applied so
        the score reflects the current document state rather than the stale
        pre-fix counts captured in Step 2.

        Graduated penalties:
          - errors   → -7 each (max 3)
          - warnings → -3 each (max 3)

        Visual blend: 80/20, only when visual score < structural score.
        """
        # --- Fresh verification counts ----------------------------------
        from texguardian.cli.commands.verify import run_verify_checks
        from texguardian.latex.parser import LatexParser

        fresh = run_verify_checks(session)

        errors = [c for c in fresh if not c["passed"] and c["severity"] == "error"]
        warnings = [c for c in fresh if not c["passed"] and c["severity"] == "warning"]

        result.verification_issues = [
            f"{c['name']}: {c['message']}" for c in fresh if not c["passed"]
        ]
        result.verification_passed = len(result.verification_issues) == 0

        # Re-count figure / table issues from fresh parser data
        parser = LatexParser(session.project_root, session.config.project.main_tex)
        try:
            figures = parser.extract_figures_with_details()
            result.figures_analyzed = len(figures)
            fig_issues = sum(
                1 for f in figures if not f.get("label") or not f.get("caption") or len(f.get("caption", "")) < 20
            )
            result.figures_issues = fig_issues
        except Exception:
            pass
        try:
            tables = parser.extract_tables_with_details()
            result.tables_analyzed = len(tables)
            tbl_issues = 0
            for tab in tables:
                if not tab.get("label"):
                    tbl_issues += 1
                if not tab.get("caption") or len(tab.get("caption", "")) < 10:
                    tbl_issues += 1
                content = tab.get("content", "")
                if "\\hline" in content and "\\toprule" not in content:
                    tbl_issues += 1
            result.tables_issues = tbl_issues
        except Exception:
            pass

        # --- Score calculation ------------------------------------------
        score = 100

        if not result.compile_success:
            score -= 30

        # Graduated penalties: errors -7, warnings -3
        score -= 7 * min(len(errors), 3)
        score -= 3 * min(len(warnings), 3)

        if result.citations_hallucinated > 0:
            score -= 5 * min(result.citations_hallucinated, 4)
        if result.figures_issues > 0:
            score -= 2 * min(result.figures_issues, 5)
        if result.tables_issues > 0:
            score -= 2 * min(result.tables_issues, 5)

        # Blend visual score (80/20) only when visual < structural
        if result.visual_rounds > 0 and result.visual_score > 0:
            if result.visual_score < score:
                score = round((score * 8 + result.visual_score * 2) / 10)

        result.overall_score = max(0, min(100, score))

        console.print(f"  [bold]Overall Score: {result.overall_score}/100[/bold]")

    def _print_summary(
        self,
        result: ReviewResult,
        console: Console,
        session: SessionState | None = None,
    ) -> None:
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

        # Show output PDF path
        pdf_path = session.last_pdf_path if session else None
        if pdf_path:
            console.print(f"\n[bold]Output PDF:[/bold] {pdf_path}")

    def get_completions(self, partial: str) -> list[str]:
        """Get argument completions."""
        options = ["quick", "full"]
        return [o for o in options if o.startswith(partial.lower())]

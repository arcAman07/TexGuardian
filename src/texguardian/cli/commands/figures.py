"""Figures command - complete figure verification, fixing, and analysis.

Unified command that:
1. Verifies all figures (labels, captions, references)
2. Fixes issues (missing labels, bad captions)
3. Visual verification (renders PDF, checks figure appearance)
4. Deep analysis (AI-powered quality assessment)

Runs until threshold score is met or max rounds reached.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.table import Table

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


FIGURE_FIX_PROMPT = """\
You are a LaTeX expert fixing figure issues in an academic paper.

## Target File
`{filename}`

## Figure Issues Found
{issues}

## Current Figure Code
{figure_code}

## Task
Generate unified diff patches to fix these issues:

1. **Missing labels**: Add \\label{{fig:descriptive-name}} after \\caption
2. **Missing captions**: Add descriptive caption that explains the figure
3. **Unreferenced figures**: Either add \\ref{{fig:name}} in text or mark for removal
4. **Caption quality**: Improve captions to be self-contained and informative
5. **Placement issues**: Fix [htbp] placement specifiers if needed
6. **Width overflow**: Reduce figure width to fit within \\columnwidth (e.g. change width=1.5\\columnwidth to width=\\columnwidth)
7. **Negative spacing**: Remove \\hspace{{-...}} hacks that force positioning
8. **TikZ overflow**: Ensure TikZ diagrams fit within column width by adjusting node positions and scaling

For captions, follow these guidelines:
- Start with "Overview of..." or "Illustration of..." or similar
- Include what the figure shows
- Mention key takeaways if it's a results figure
- Keep under 2-3 sentences unless complex

Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename `{filename}` in the --- and +++ headers. \
Example format:

```diff
--- a/{filename}
+++ b/{filename}
@@ -100,3 +100,4 @@
 \\begin{{figure}}[t]
 \\centering
+\\caption{{Description of the figure.}}
+\\label{{fig:example}}
```
"""


FIGURE_CUSTOM_PROMPT = """\
You are a LaTeX expert editing figures in an academic paper.

## Target File
`{filename}`

## User Request
{user_instruction}

## Current Figure Code (all figures in the paper)
{figure_code}

## Task
Generate unified diff patches to implement the user's request above.

Guidelines:
- Make only the changes the user requested
- Preserve existing labels and references
- Keep captions self-contained and informative
- Use proper LaTeX figure formatting

Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename `{filename}` in the --- and +++ headers. \
Example format:

```diff
--- a/{filename}
+++ b/{filename}
@@ -100,3 +100,3 @@
-\\includegraphics[width=0.8\\columnwidth]{{fig.pdf}}
+\\includegraphics[width=\\columnwidth]{{fig.pdf}}
```
"""


FIGURE_ANALYSIS_PROMPT = """You are an expert academic paper reviewer analyzing figures.

## Paper Information
Title: {title}
Venue: {venue}

## Figures to Analyze
{figures_content}

## Task
Provide detailed feedback for each figure:

1. **Clarity** (0-100): Is the figure easy to understand?
2. **Caption Quality** (0-100): Is the caption informative and self-contained?
3. **Necessity** (0-100): Does this figure add value?
4. **Presentation** (0-100): Resolution, colors, labels, formatting
5. **Integration** (0-100): Well-referenced in text? Text explains it?

Output as JSON:
```json
{{
  "figures": [
    {{
      "label": "fig:example",
      "scores": {{"clarity": 85, "caption": 70, "necessity": 90, "presentation": 75, "integration": 80}},
      "issues": ["Label font too small"],
      "suggestions": ["Increase axis label size"],
      "overall": 80
    }}
  ],
  "average_score": 80,
  "top_issues": ["Issue 1", "Issue 2"],
  "summary": "Overall assessment"
}}
```
"""


class FiguresCommand(Command):
    """Complete figure verification, fixing, and analysis."""

    name = "figures"
    description = "Verify, fix, and analyze all figures (combined pipeline)"
    aliases = ["figs", "fig"]
    usage = (
        "/figures [fix|analyze|<instruction>]\n"
        "  /figures                              - Verify only\n"
        "  /figures fix                          - Auto-fix detected issues\n"
        "  /figures analyze                      - AI quality analysis\n"
        "  /figures fix all spacing issues       - Custom instruction"
    )

    # Keywords that trigger built-in modes (anything else is a custom
    # instruction routed to the LLM).
    _KEYWORDS = {"fix", "analyze", "analysis"}

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute figures command.

        Modes:
        - /figures                    → verify only (shows issues)
        - /figures fix                → verify + auto-fix + compile + analysis
        - /figures analyze            → verify + AI analysis
        - /figures <free text>        → verify + custom LLM edit
        """
        console.print("[bold cyan]Figure Pipeline[/bold cyan]\n")

        # Determine mode from args
        parts = args.lower().split()
        fix_mode = "fix" in parts
        analyze_mode = "analyze" in parts or "analysis" in parts

        # Anything that isn't purely keywords is a custom instruction
        non_keywords = [w for w in args.split() if w.lower() not in self._KEYWORDS]
        custom_instruction = " ".join(non_keywords).strip() if non_keywords and not fix_mode and not analyze_mode else ""
        # Also treat "fix <extra words>" as a custom instruction
        # e.g. "/figures fix all spacing issues"
        if fix_mode and non_keywords:
            custom_instruction = args  # send the full thing as instruction

        # Step 1: Verify figures (always)
        console.print("[bold]Step 1: Verifying Figures[/bold]")
        verification_result = await self._verify_figures(session, console)

        if not verification_result["figures"]:
            console.print("[yellow]No figures found in the paper[/yellow]")
            return

        # Custom instruction mode — skip auto-fix, go straight to LLM
        if custom_instruction:
            console.print(
                f"\n[bold]Applying: [cyan]{custom_instruction}[/cyan][/bold]\n"
            )
            await self._custom_fix_figures(session, console, custom_instruction)
            return

        # Standard modes
        if fix_mode:
            if verification_result["issues"]:
                console.print("\n[bold]Step 2: Fixing Issues[/bold]")
                await self._fix_figures(session, console, verification_result)

            console.print("\n[bold]Step 3: Visual Verification[/bold]")
            await self._visual_verify_figures(session, console)
        elif verification_result["issues"] and not analyze_mode:
            console.print(f"\n[yellow]{len(verification_result['issues'])} issues found.[/yellow]")
            console.print("[dim]Run '/figures fix' to auto-fix issues[/dim]")

        if fix_mode or analyze_mode:
            console.print("\n[bold]Deep Analysis[/bold]")
            await self._analyze_figures(session, console, verification_result)

    async def _verify_figures(
        self,
        session: SessionState,
        console: Console,
    ) -> dict:
        """Verify all figures in the paper."""
        from texguardian.latex.parser import LatexParser

        parser = LatexParser(session.project_root, session.config.project.main_tex)
        result = {
            "figures": [],
            "issues": [],
            "referenced": set(),
            "defined": set(),
        }

        try:
            figures = parser.extract_figures_with_details()
            fig_refs = parser.extract_figure_refs()
            result["referenced"] = set(fig_refs)

            for fig in figures:
                label = fig.get("label", "")
                caption = fig.get("caption", "")
                ref_count = fig_refs.count(label) if label else 0

                result["figures"].append({
                    "label": label,
                    "caption": caption,
                    "ref_count": ref_count,
                    "content": fig.get("content", "")[:500],
                })

                if label:
                    result["defined"].add(label)

                # Check for issues
                if not label:
                    result["issues"].append({
                        "type": "missing_label",
                        "figure": caption[:50] if caption else "Unknown figure",
                        "severity": "error",
                    })
                elif ref_count == 0:
                    result["issues"].append({
                        "type": "unreferenced",
                        "figure": label,
                        "severity": "warning",
                    })

                if not caption or len(caption) < 20:
                    result["issues"].append({
                        "type": "poor_caption",
                        "figure": label or "Unknown",
                        "severity": "warning",
                    })

                # Check for overflow issues
                fig_content = fig.get("content", "")
                width_match = re.search(
                    r'width\s*=\s*(\d+\.?\d*)\s*\\(?:columnwidth|textwidth)',
                    fig_content,
                )
                if width_match and float(width_match.group(1)) > 1.0:
                    result["issues"].append({
                        "type": "overflow_width",
                        "figure": label or "Unknown",
                        "severity": "warning",
                    })
                if re.search(r'\\hspace\s*\{-', fig_content):
                    result["issues"].append({
                        "type": "negative_hspace",
                        "figure": label or "Unknown",
                        "severity": "warning",
                    })

            # Display results
            table = Table(title=f"Figures ({len(figures)})")
            table.add_column("Label", style="cyan")
            table.add_column("Caption", max_width=40)
            table.add_column("Refs", justify="center")
            table.add_column("Status")

            for fig in result["figures"]:
                label = fig["label"] or "[none]"
                caption = fig["caption"][:40] + "..." if len(fig["caption"]) > 40 else fig["caption"]
                refs = str(fig["ref_count"])

                # Check if this figure has overflow issues
                has_overflow = any(
                    i["type"] in ("overflow_width", "negative_hspace")
                    and i["figure"] == (fig["label"] or "Unknown")
                    for i in result["issues"]
                )

                if not fig["label"]:
                    status = "[red]No label[/red]"
                elif has_overflow:
                    status = "[yellow]Overflow[/yellow]"
                elif fig["ref_count"] == 0:
                    status = "[yellow]No refs[/yellow]"
                elif len(fig["caption"]) < 20:
                    status = "[yellow]Short caption[/yellow]"
                else:
                    status = "[green]OK[/green]"

                table.add_row(label, caption or "[no caption]", refs, status)

            console.print(table)

            # Show issue summary
            if result["issues"]:
                console.print(f"\n[yellow]Found {len(result['issues'])} issue(s)[/yellow]")

        except Exception as e:
            console.print(f"[red]Error verifying figures: {e}[/red]")

        return result

    async def _fix_figures(
        self,
        session: SessionState,
        console: Console,
        verification_result: dict,
    ) -> None:
        """Fix figure issues."""
        if not session.llm_client:
            console.print("[red]LLM client not available[/red]")
            return

        issues = verification_result["issues"]
        if not issues:
            console.print("[green]No issues to fix[/green]")
            return

        # Build issue text
        issues_text = []
        for issue in issues:
            issues_text.append(f"- {issue['type']}: {issue['figure']} ({issue['severity']})")

        # Get figure code
        content = session.main_tex_path.read_text()
        figure_pattern = r'\\begin\{figure\}.*?\\end\{figure\}'
        figures = re.findall(figure_pattern, content, re.DOTALL)
        figure_code = "\n\n".join(figures[:10])  # First 10 figures

        filename = session.main_tex_path.name
        prompt = FIGURE_FIX_PROMPT.format(
            filename=filename,
            issues="\n".join(issues_text),
            figure_code=figure_code,
        )

        console.print("[cyan]Generating fixes...[/cyan]\n")

        from texguardian.llm.streaming import stream_llm

        response_text = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
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
                    f"\n[green]Applied {applied} figure fix(es)[/green]"
                )
        else:
            console.print(
                "\n[yellow]No diff patches found in response.[/yellow]"
            )

    async def _custom_fix_figures(
        self,
        session: SessionState,
        console: Console,
        user_instruction: str,
    ) -> None:
        """Apply a free-form user instruction to figures via LLM."""
        if not session.llm_client:
            console.print("[red]LLM client not available[/red]")
            return

        # Get all figure code from main tex
        content = session.main_tex_path.read_text()
        figure_pattern = r'\\begin\{figure\}.*?\\end\{figure\}'
        figures = re.findall(figure_pattern, content, re.DOTALL)
        figure_code = "\n\n".join(figures[:10])

        if not figure_code:
            console.print("[yellow]No figure code found[/yellow]")
            return

        filename = session.main_tex_path.name
        prompt = FIGURE_CUSTOM_PROMPT.format(
            filename=filename,
            user_instruction=user_instruction,
            figure_code=figure_code,
        )

        console.print("[cyan]Generating edits...[/cyan]\n")

        from texguardian.llm.streaming import stream_llm

        response_text = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
            max_tokens=4000,
            temperature=0.3,
        )
        console.print()

        if session.context:
            session.context.add_assistant_message(response_text)

        from texguardian.cli.approval import interactive_approval
        from texguardian.patch.parser import extract_patches

        patches = extract_patches(response_text)

        if patches:
            applied = await interactive_approval(patches, session, console)
            if applied > 0:
                console.print(
                    f"\n[green]Applied {applied} figure edit(s)[/green]"
                )
        else:
            console.print(
                "\n[yellow]No diff patches found in response.[/yellow]"
            )

    async def _visual_verify_figures(
        self,
        session: SessionState,
        console: Console,
    ) -> None:
        """Visual verification of figures via compile-render-vision loop."""
        from texguardian.visual.verifier import VisualVerifier

        try:
            verifier = VisualVerifier(session)
            result = await verifier.run_loop(
                max_rounds=session.config.safety.max_visual_rounds,
                console=console,
                focus_areas=[
                    "figures",
                    "figure placement",
                    "figure captions",
                    "figure labels",
                ],
            )

            console.print("\n  Visual verification complete:")
            console.print(f"    Rounds: {result.rounds}")
            console.print(f"    Score: {result.quality_score}/100")
            console.print(f"    Patches applied: {result.patches_applied}")
            if result.stopped_reason:
                console.print(f"    Stopped: {result.stopped_reason}")

        except Exception as e:
            console.print(f"  [red]Error in visual verification: {e}[/red]")

    async def _analyze_figures(
        self,
        session: SessionState,
        console: Console,
        verification_result: dict,
    ) -> None:
        """Deep AI analysis of figures."""
        if not session.llm_client:
            console.print("[dim]LLM not available for analysis[/dim]")
            return

        figures = verification_result["figures"]
        if not figures:
            return

        # Build figure content for prompt
        figures_text = []
        for i, fig in enumerate(figures, 1):
            figures_text.append(f"Figure {i}:")
            figures_text.append(f"  Label: {fig['label'] or 'none'}")
            figures_text.append(f"  Caption: {fig['caption']}")
            figures_text.append(f"  References in text: {fig['ref_count']}")
            figures_text.append("")

        prompt = FIGURE_ANALYSIS_PROMPT.format(
            title=session.paper_spec.title if session.paper_spec else "Unknown",
            venue=session.paper_spec.venue if session.paper_spec else "Unknown",
            figures_content="\n".join(figures_text),
        )

        console.print("[dim]Analyzing figure quality...[/dim]\n")

        from texguardian.llm.streaming import stream_llm

        content = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
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
        avg_score = self._safe_int(data.get("average_score", 0))

        # Score color
        if avg_score >= 80:
            color = "green"
        elif avg_score >= 60:
            color = "yellow"
        else:
            color = "red"

        console.print(f"\n[bold]Average Figure Score: [{color}]{avg_score}/100[/{color}][/bold]")

        # Per-figure scores
        figures = data.get("figures", [])
        if figures:
            table = Table(title="Figure Scores")
            table.add_column("Figure", style="cyan")
            table.add_column("Overall", justify="center")
            table.add_column("Issues")

            for fig in figures:
                label = fig.get("label", "?")
                overall = self._safe_int(fig.get("overall", 0))
                issues = ", ".join(fig.get("issues", [])[:2])

                score_color = "green" if overall >= 80 else "yellow" if overall >= 60 else "red"
                table.add_row(label, f"[{score_color}]{overall}[/{score_color}]", issues[:40])

            console.print(table)

        # Top issues
        top_issues = data.get("top_issues", [])
        if top_issues:
            console.print("\n[yellow]Top Issues:[/yellow]")
            for issue in top_issues[:3]:
                console.print(f"  • {issue}")

        # Summary
        summary = data.get("summary", "")
        if summary:
            console.print(f"\n[dim]{summary}[/dim]")

    def get_completions(self, partial: str) -> list[str]:
        """Get argument completions."""
        return ["fix", "analyze"]


async def generate_and_apply_figure_fixes(
    session: SessionState,
    console: Console,
    *,
    auto_approve: bool = False,
    print_output: bool = True,
    visual_verify: bool = False,
) -> int:
    """Reusable figure-fix pipeline callable from ``/review``.

    Returns the number of patches applied.
    """
    from texguardian.latex.parser import LatexParser

    parser = LatexParser(session.project_root, session.config.project.main_tex)

    # Verify figures
    figures = parser.extract_figures_with_details()
    fig_refs = parser.extract_figure_refs()

    issues: list[dict] = []
    for fig in figures:
        label = fig.get("label", "")
        caption = fig.get("caption", "")
        ref_count = fig_refs.count(label) if label else 0

        if not label:
            issues.append({"type": "missing_label", "figure": caption[:50] if caption else "Unknown figure", "severity": "error"})
        elif ref_count == 0:
            issues.append({"type": "unreferenced", "figure": label, "severity": "warning"})

        if not caption or len(caption) < 20:
            issues.append({"type": "poor_caption", "figure": label or "Unknown", "severity": "warning"})

        # Check for overflow issues
        fig_content = fig.get("content", "")
        width_match = re.search(
            r'width\s*=\s*(\d+\.?\d*)\s*\\(?:columnwidth|textwidth)',
            fig_content,
        )
        if width_match and float(width_match.group(1)) > 1.0:
            issues.append({"type": "overflow_width", "figure": label or "Unknown", "severity": "warning"})
        if re.search(r'\\hspace\s*\{-', fig_content):
            issues.append({"type": "negative_hspace", "figure": label or "Unknown", "severity": "warning"})

    if not issues:
        console.print("  [green]✓[/green] No figure issues to fix")
        return 0

    if not session.llm_client:
        console.print("  [red]LLM client not available[/red]")
        return 0

    # Build prompt
    issues_text = [f"- {i['type']}: {i['figure']} ({i['severity']})" for i in issues]

    content = session.main_tex_path.read_text()
    figure_pattern = r'\\begin\{figure\}.*?\\end\{figure\}'
    figure_code = "\n\n".join(re.findall(figure_pattern, content, re.DOTALL)[:10])

    filename = session.main_tex_path.name
    prompt = FIGURE_FIX_PROMPT.format(
        filename=filename,
        issues="\n".join(issues_text),
        figure_code=figure_code,
    )

    console.print("  [cyan]Generating figure fixes...[/cyan]")

    from texguardian.llm.streaming import stream_llm

    response_text = await stream_llm(
        session.llm_client,
        messages=[{"role": "user", "content": prompt}],
        console=console,
        max_tokens=4000,
        temperature=0.3,
        print_output=print_output,
    )

    if session.context:
        session.context.add_assistant_message(response_text)

    from texguardian.cli.approval import interactive_approval
    from texguardian.patch.parser import extract_patches

    patches = extract_patches(response_text)
    if not patches:
        console.print("  [yellow]No figure patches generated[/yellow]")
        return 0

    applied = await interactive_approval(patches, session, console, auto_approve=auto_approve)
    if applied > 0:
        console.print(f"  [green]Applied {applied} figure fix(es)[/green]")

    # Phase 2: Visual verification loop
    if visual_verify and applied > 0:
        from texguardian.visual.verifier import VisualVerifier

        console.print("  [cyan]Running visual verification of figure fixes...[/cyan]")
        try:
            verifier = VisualVerifier(session)
            vresult = await verifier.run_loop(
                max_rounds=session.config.safety.max_visual_rounds,
                console=console,
                focus_areas=["figures", "figure placement", "figure captions", "figure labels"],
            )
            applied += vresult.patches_applied
        except Exception as e:
            console.print(f"  [red]Visual verification error: {e}[/red]")

    return applied

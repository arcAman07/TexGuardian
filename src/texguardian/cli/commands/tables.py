"""Tables command - complete table verification, fixing, and analysis.

Unified command that:
1. Verifies all tables (labels, captions, references)
2. Fixes issues (missing labels, formatting)
3. Deep analysis (AI-powered quality assessment)
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rich.table import Table

from texguardian.cli.commands.registry import Command


def _numbered_content(content: str) -> str:
    """Return file content with line numbers for accurate LLM patch generation."""
    lines = content.splitlines()
    return "\n".join(f"{i+1:4d}| {line}" for i, line in enumerate(lines))

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


TABLE_FIX_PROMPT = """\
You are a LaTeX expert fixing table issues in an academic paper.

## Target File
`{filename}`

## Table Issues Found
{issues}

## Full File Content (with line numbers)
{numbered_content}

## Task
Generate unified diff patches to fix these issues:

1. **Missing labels**: Add \\label{{tab:descriptive-name}} after \\caption
2. **Missing captions**: Add descriptive caption
3. **Unreferenced tables**: Add \\ref{{tab:name}} in text
4. **Formatting**: Use booktabs (\\toprule, \\midrule, \\bottomrule) instead of \\hline
5. **Alignment**: Fix column alignment, number formatting
6. **Units**: Add units to column headers if missing

For captions:
- Place ABOVE the table (standard for tables)
- Make self-contained and descriptive
- Include what the table shows and key takeaways

IMPORTANT: Use the EXACT line numbers shown above in your @@ headers. \
Context and removed lines MUST match the file content exactly (copy them). \
Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename `{filename}` in the --- and +++ headers.
"""


TABLE_CUSTOM_PROMPT = """\
You are a LaTeX expert editing tables in an academic paper.

## Target File
`{filename}`

## User Request
{user_instruction}

## Full File Content (with line numbers)
{numbered_content}

## Task
Generate unified diff patches to implement the user's request above.

Guidelines:
- Make only the changes the user requested
- Preserve existing labels and references
- Use booktabs formatting (\\toprule, \\midrule, \\bottomrule) when appropriate
- Place captions ABOVE tables (standard academic convention)
- Keep number formatting consistent within columns

IMPORTANT: Use the EXACT line numbers shown above in your @@ headers. \
Context and removed lines MUST match the file content exactly (copy them). \
Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename `{filename}` in the --- and +++ headers.
"""


TABLE_ANALYSIS_PROMPT = """You are an expert academic paper reviewer analyzing tables.

## Paper Information
Title: {title}
Venue: {venue}

## Tables to Analyze
{tables_content}

## Task
Provide detailed feedback for each table:

1. **Clarity** (0-100): Is the table easy to read?
2. **Caption Quality** (0-100): Is the caption informative?
3. **Formatting** (0-100): Proper use of booktabs, alignment, spacing
4. **Data Presentation** (0-100): Numbers formatted consistently, units shown
5. **Necessity** (0-100): Does this table add value?

Output as JSON:
```json
{{
  "tables": [
    {{
      "label": "tab:example",
      "scores": {{"clarity": 85, "caption": 70, "formatting": 80, "data": 75, "necessity": 90}},
      "issues": ["Missing units in header"],
      "suggestions": ["Add \\\\midrule after header"],
      "overall": 80
    }}
  ],
  "average_score": 80,
  "top_issues": ["Issue 1", "Issue 2"],
  "summary": "Overall assessment"
}}
```
"""


class TablesCommand(Command):
    """Complete table verification, fixing, and analysis."""

    name = "tables"
    description = "Verify, fix, and analyze all tables (combined pipeline)"
    aliases = ["tabs", "tab"]
    usage = (
        "/tables [fix|analyze|<instruction>]\n"
        "  /tables                                - Verify only\n"
        "  /tables fix                            - Auto-fix detected issues\n"
        "  /tables analyze                        - AI quality analysis\n"
        "  /tables convert all tables to booktabs - Custom instruction"
    )

    _KEYWORDS = {"fix", "analyze", "analysis"}

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute tables command.

        Modes:
        - /tables                    → verify only (shows issues)
        - /tables fix                → verify + auto-fix + AI analysis
        - /tables analyze            → verify + AI analysis
        - /tables <free text>        → verify + custom LLM edit
        """
        console.print("[bold cyan]Table Pipeline[/bold cyan]\n")

        # Determine mode from args
        parts = args.lower().split()
        fix_mode = "fix" in parts
        analyze_mode = "analyze" in parts or "analysis" in parts

        # Anything that isn't purely keywords is a custom instruction
        non_keywords = [w for w in args.split() if w.lower() not in self._KEYWORDS]
        custom_instruction = ""
        if fix_mode and non_keywords:
            custom_instruction = args
        elif non_keywords and not fix_mode and not analyze_mode:
            custom_instruction = " ".join(non_keywords).strip()

        # Step 1: Verify tables (always)
        console.print("[bold]Step 1: Verifying Tables[/bold]")
        verification_result = await self._verify_tables(session, console)

        if not verification_result["tables"]:
            console.print("[yellow]No tables found in the paper[/yellow]")
            return

        # Custom instruction mode
        if custom_instruction:
            console.print(
                f"\n[bold]Applying: [cyan]{custom_instruction}[/cyan][/bold]\n"
            )
            await self._custom_fix_tables(session, console, custom_instruction)
            return

        # Standard modes
        if fix_mode:
            if verification_result["issues"]:
                console.print("\n[bold]Step 2: Fixing Issues[/bold]")
                await self._fix_tables(session, console, verification_result)

            console.print("\n[bold]Step 3: Visual Verification[/bold]")
            await self._visual_verify_tables(session, console)
        elif verification_result["issues"] and not analyze_mode:
            console.print(f"\n[yellow]{len(verification_result['issues'])} issues found.[/yellow]")
            console.print("[dim]Run '/tables fix' to auto-fix issues[/dim]")

        if fix_mode or analyze_mode:
            console.print("\n[bold]Deep Analysis[/bold]")
            await self._analyze_tables(session, console, verification_result)

    async def _verify_tables(
        self,
        session: SessionState,
        console: Console,
    ) -> dict:
        """Verify all tables in the paper."""
        from texguardian.latex.parser import LatexParser

        parser = LatexParser(session.project_root, session.config.project.main_tex)
        result = {
            "tables": [],
            "issues": [],
        }

        try:
            tables = parser.extract_tables_with_details()

            # Get table references
            content = session.main_tex_path.read_text()
            tab_refs = re.findall(r'\\ref\{(tab:[^}]+)\}', content)

            for tab in tables:
                label = tab.get("label", "")
                caption = tab.get("caption", "")
                ref_count = tab_refs.count(label) if label else 0

                result["tables"].append({
                    "label": label,
                    "caption": caption,
                    "ref_count": ref_count,
                    "content": tab.get("content", "")[:500],
                })

                # Check for issues
                if not label:
                    result["issues"].append({
                        "type": "missing_label",
                        "table": caption[:50] if caption else "Unknown table",
                        "severity": "error",
                    })
                elif ref_count == 0:
                    result["issues"].append({
                        "type": "unreferenced",
                        "table": label,
                        "severity": "warning",
                    })

                if not caption or len(caption) < 10:
                    result["issues"].append({
                        "type": "poor_caption",
                        "table": label or "Unknown",
                        "severity": "warning",
                    })

                # Check for booktabs usage
                table_content = tab.get("content", "")
                if "\\hline" in table_content and "\\toprule" not in table_content:
                    result["issues"].append({
                        "type": "no_booktabs",
                        "table": label or "Unknown",
                        "severity": "info",
                    })

            # Display results
            table_display = Table(title=f"Tables ({len(tables)})")
            table_display.add_column("Label", style="cyan")
            table_display.add_column("Caption", max_width=40)
            table_display.add_column("Refs", justify="center")
            table_display.add_column("Status")

            for tab in result["tables"]:
                label = tab["label"] or "[none]"
                caption = tab["caption"][:40] + "..." if len(tab["caption"]) > 40 else tab["caption"]
                refs = str(tab["ref_count"])

                # Determine status from most severe issue
                has_no_booktabs = any(
                    i["type"] == "no_booktabs" and i["table"] == (tab["label"] or "Unknown")
                    for i in result["issues"]
                )

                if not tab["label"]:
                    status = "[red]No label[/red]"
                elif tab["ref_count"] == 0:
                    status = "[yellow]No refs[/yellow]"
                elif has_no_booktabs:
                    status = "[yellow]No booktabs[/yellow]"
                else:
                    status = "[green]OK[/green]"

                table_display.add_row(label, caption or "[no caption]", refs, status)

            console.print(table_display)

            if result["issues"]:
                console.print(f"\n[yellow]Found {len(result['issues'])} issue(s)[/yellow]")

        except Exception as e:
            console.print(f"[red]Error verifying tables: {e}[/red]")

        return result

    async def _fix_tables(
        self,
        session: SessionState,
        console: Console,
        verification_result: dict,
    ) -> None:
        """Fix table issues."""
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
            issues_text.append(f"- {issue['type']}: {issue['table']} ({issue['severity']})")

        # Get full file content with line numbers
        content = session.main_tex_path.read_text()
        numbered_content = _numbered_content(content)

        filename = session.main_tex_path.name
        prompt = TABLE_FIX_PROMPT.format(
            filename=filename,
            issues="\n".join(issues_text),
            numbered_content=numbered_content,
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
                    f"\n[green]Applied {applied} table fix(es)[/green]"
                )
        else:
            console.print(
                "\n[yellow]No diff patches found in response.[/yellow]"
            )

    async def _visual_verify_tables(
        self,
        session: SessionState,
        console: Console,
    ) -> None:
        """Visual verification of tables via compile-render-vision loop."""
        from texguardian.visual.verifier import VisualVerifier

        try:
            verifier = VisualVerifier(session)
            result = await verifier.run_loop(
                max_rounds=session.config.safety.max_visual_rounds,
                console=console,
                focus_areas=[
                    "tables",
                    "table alignment",
                    "table formatting",
                    "booktabs",
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

    async def _custom_fix_tables(
        self,
        session: SessionState,
        console: Console,
        user_instruction: str,
    ) -> None:
        """Apply a free-form user instruction to tables via LLM."""
        if not session.llm_client:
            console.print("[red]LLM client not available[/red]")
            return

        content = session.main_tex_path.read_text()
        if not re.search(r'\\begin\{table\}', content):
            console.print("[yellow]No table code found[/yellow]")
            return

        numbered_content = _numbered_content(content)

        filename = session.main_tex_path.name
        prompt = TABLE_CUSTOM_PROMPT.format(
            filename=filename,
            user_instruction=user_instruction,
            numbered_content=numbered_content,
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
                    f"\n[green]Applied {applied} table edit(s)[/green]"
                )
        else:
            console.print(
                "\n[yellow]No diff patches found in response.[/yellow]"
            )

    async def _analyze_tables(
        self,
        session: SessionState,
        console: Console,
        verification_result: dict,
    ) -> None:
        """Deep AI analysis of tables."""
        if not session.llm_client:
            console.print("[dim]LLM not available for analysis[/dim]")
            return

        tables = verification_result["tables"]
        if not tables:
            return

        # Build table content for prompt
        tables_text = []
        for i, tab in enumerate(tables, 1):
            tables_text.append(f"Table {i}:")
            tables_text.append(f"  Label: {tab['label'] or 'none'}")
            tables_text.append(f"  Caption: {tab['caption']}")
            tables_text.append(f"  Content preview: {tab['content'][:200]}...")
            tables_text.append("")

        prompt = TABLE_ANALYSIS_PROMPT.format(
            title=session.paper_spec.title if session.paper_spec else "Unknown",
            venue=session.paper_spec.venue if session.paper_spec else "Unknown",
            tables_content="\n".join(tables_text),
        )

        console.print("[dim]Analyzing table quality...[/dim]\n")

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
        avg_score = self._safe_int(data.get("average_score", 0))

        color = "green" if avg_score >= 80 else "yellow" if avg_score >= 60 else "red"
        console.print(f"\n[bold]Average Table Score: [{color}]{avg_score}/100[/{color}][/bold]")

        tables = data.get("tables", [])
        if tables:
            table_display = Table(title="Table Scores")
            table_display.add_column("Table", style="cyan")
            table_display.add_column("Overall", justify="center")
            table_display.add_column("Issues")

            for tab in tables:
                label = tab.get("label", "?")
                overall = self._safe_int(tab.get("overall", 0))
                issues = ", ".join(tab.get("issues", [])[:2])

                score_color = "green" if overall >= 80 else "yellow" if overall >= 60 else "red"
                table_display.add_row(label, f"[{score_color}]{overall}[/{score_color}]", issues[:40])

            console.print(table_display)

        top_issues = data.get("top_issues", [])
        if top_issues:
            console.print("\n[yellow]Top Issues:[/yellow]")
            for issue in top_issues[:3]:
                console.print(f"  • {issue}")

        summary = data.get("summary", "")
        if summary:
            console.print(f"\n[dim]{summary}[/dim]")

    def get_completions(self, partial: str) -> list[str]:
        """Get argument completions."""
        return ["fix", "analyze"]


async def generate_and_apply_table_fixes(
    session: SessionState,
    console: Console,
    *,
    auto_approve: bool = False,
    print_output: bool = True,
    visual_verify: bool = False,
) -> int:
    """Reusable table-fix pipeline callable from ``/review``.

    Returns the number of patches applied.
    """
    from texguardian.latex.parser import LatexParser

    parser = LatexParser(session.project_root, session.config.project.main_tex)

    # Verify tables
    tables = parser.extract_tables_with_details()
    content = session.main_tex_path.read_text()
    tab_refs = re.findall(r'\\ref\{(tab:[^}]+)\}', content)

    issues: list[dict] = []
    for tab in tables:
        label = tab.get("label", "")
        caption = tab.get("caption", "")
        ref_count = tab_refs.count(label) if label else 0

        if not label:
            issues.append({"type": "missing_label", "table": caption[:50] if caption else "Unknown table", "severity": "error"})
        elif ref_count == 0:
            issues.append({"type": "unreferenced", "table": label, "severity": "warning"})

        if not caption or len(caption) < 10:
            issues.append({"type": "poor_caption", "table": label or "Unknown", "severity": "warning"})

        table_content = tab.get("content", "")
        if "\\hline" in table_content and "\\toprule" not in table_content:
            issues.append({"type": "no_booktabs", "table": label or "Unknown", "severity": "info"})

    if not issues:
        console.print("  [green]✓[/green] No table issues to fix")
        return 0

    if not session.llm_client:
        console.print("  [red]LLM client not available[/red]")
        return 0

    # Build prompt
    issues_text = [f"- {i['type']}: {i['table']} ({i['severity']})" for i in issues]

    numbered_content = _numbered_content(content)

    filename = session.main_tex_path.name
    prompt = TABLE_FIX_PROMPT.format(
        filename=filename,
        issues="\n".join(issues_text),
        numbered_content=numbered_content,
    )

    console.print("  [cyan]Generating table fixes...[/cyan]")

    from texguardian.llm.prompts.system import COMMAND_SYSTEM_PROMPT
    from texguardian.llm.streaming import stream_llm

    response_text = await stream_llm(
        session.llm_client,
        messages=[{"role": "user", "content": prompt}],
        console=console,
        system=COMMAND_SYSTEM_PROMPT,
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
        console.print("  [yellow]No table patches generated[/yellow]")
        return 0

    applied = await interactive_approval(patches, session, console, auto_approve=auto_approve)
    if applied > 0:
        console.print(f"  [green]Applied {applied} table fix(es)[/green]")

    # Phase 2: Visual verification loop
    if visual_verify and applied > 0:
        from texguardian.visual.verifier import VisualVerifier

        console.print("  [cyan]Running visual verification of table fixes...[/cyan]")
        try:
            verifier = VisualVerifier(session)
            vresult = await verifier.run_loop(
                max_rounds=session.config.safety.max_visual_rounds,
                console=console,
                focus_areas=["tables", "table alignment", "table formatting", "booktabs"],
            )
            applied += vresult.patches_applied
        except Exception as e:
            console.print(f"  [red]Visual verification error: {e}[/red]")

    return applied

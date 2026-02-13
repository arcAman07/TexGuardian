"""Citations command - verify, validate, and fix citations."""

from __future__ import annotations

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


CITATION_FIX_PROMPT = """\
You are a LaTeX citation expert. Fix the following citation issues using \
the validation results and search suggestions.

## Target Files
Main paper: `{filename}`
Bibliography: `{bib_filename}`

## Issues Found
{issues}

## Validation Results (from CrossRef/Semantic Scholar API)
{validation_results}

## Bibliography File Content (with line numbers)
{numbered_bib_content}

## Paper File Content (with line numbers)
{numbered_paper_content}

## Task
For each issue, provide a unified diff patch that fixes it. Use the REAL \
paper information from validation results.

IMPORTANT:
- Use the exact line numbers from the numbered content above in your @@ headers
- Context and removed lines MUST match the file content exactly (copy them)
- For hallucinated citations: Replace with the correct paper from search \
results, or remove if no match
- For papers with wrong metadata: Update title, author, year, DOI to \
match the verified data
- For missing DOIs: Add the DOI from validation results
- For format issues: Convert \\cite{{}} to \\citep{{}} or \\citet{{}} as \
appropriate

Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename in the --- and +++ headers. Example format:

```diff
--- a/{bib_filename}
+++ b/{bib_filename}
@@ -50,3 +50,4 @@
 @article{{smith2024example,
   title = {{Old Title}},
+  doi = {{10.1234/example}},
```
"""


CITATION_CUSTOM_PROMPT = """\
You are a LaTeX citation expert editing citations in an academic paper.

## Target Files
Main paper: `{filename}`
Bibliography: `{bib_filename}`

## User Request
{user_instruction}

## Bibliography File Content (with line numbers)
{numbered_bib_content}

## Paper File Content (with line numbers)
{numbered_paper_content}

## Task
Generate unified diff patches to implement the user's request above.

Guidelines:
- Make only the changes the user requested
- Preserve existing valid citations
- Use proper BibTeX formatting
- If converting \\cite to \\citep/\\citet, use \\citep for parenthetical
  and \\citet when the author name is part of the sentence

IMPORTANT: Use the exact line numbers from the numbered content above in \
your @@ headers. Context and removed lines MUST match the file content exactly.

Output ONLY unified diff patches inside ```diff code blocks. Each patch \
must use the exact filename in the --- and +++ headers. Example format:

```diff
--- a/{filename}
+++ b/{filename}
@@ -42,1 +42,1 @@
-as shown by \\cite{{smith2024}}
+as shown by \\citet{{smith2024}}
```
"""


class CitationsCommand(Command):
    """Unified citations command - verify, validate against real databases, and fix."""

    name = "citations"
    description = "Verify citations against real paper databases and fix issues"
    aliases = ["cite", "refs"]
    usage = (
        "/citations [validate|fix|<instruction>]\n"
        "  /citations                           - Verify citations\n"
        "  /citations validate                  - Check against real databases\n"
        "  /citations fix                       - Auto-fix detected issues\n"
        "  /citations replace all cite with citep - Custom instruction"
    )

    _KEYWORDS = {"validate", "val", "fix"}

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute citations command."""
        from texguardian.latex.parser import LatexParser

        args_lower = args.lower()
        parts = args_lower.split()
        should_validate = "validate" in parts or "val" in parts
        should_fix = "fix" in parts

        # Detect custom instruction: anything that isn't purely keywords
        non_keywords = [w for w in args.split() if w.lower() not in self._KEYWORDS]
        custom_instruction = ""
        if should_fix and non_keywords:
            custom_instruction = args
        elif non_keywords and not should_validate and not should_fix:
            custom_instruction = " ".join(non_keywords).strip()

        parser = LatexParser(session.project_root, session.config.project.main_tex)

        console.print("[bold]Citation Analysis[/bold]\n")

        try:
            # Extract all citation data
            citations = parser.extract_citations_with_locations()
            bib_keys = parser.extract_bib_keys()
            bib_key_set = set(bib_keys)

            # Categorize basic issues
            undefined = []
            format_issues = []
            cited_keys = set()

            for cite in citations:
                cited_keys.add(cite["key"])
                if cite["key"] not in bib_key_set:
                    undefined.append(cite)
                if cite["style"] == "cite":
                    format_issues.append(cite)

            uncited = [k for k in bib_keys if k not in cited_keys]

            # Display summary table
            table = Table(title="Citation Summary")
            table.add_column("Metric", style="cyan")
            table.add_column("Count", justify="right")
            table.add_column("Status")

            table.add_row(
                "Total Citations",
                str(len(citations)),
                "[green]OK[/green]"
            )
            table.add_row(
                "Unique References",
                str(len(cited_keys)),
                "[green]OK[/green]"
            )
            table.add_row(
                "Undefined Citations",
                str(len(undefined)),
                "[red]ERROR[/red]" if undefined else "[green]OK[/green]"
            )
            table.add_row(
                "Uncited in .bib",
                str(len(uncited)),
                "[yellow]WARN[/yellow]" if uncited else "[green]OK[/green]"
            )
            table.add_row(
                "Format Issues",
                str(len(format_issues)),
                "[yellow]WARN[/yellow]" if format_issues else "[green]OK[/green]"
            )

            console.print(table)
            console.print()

            # Show basic details
            if undefined:
                console.print("[red bold]Undefined Citations:[/red bold]")
                for u in undefined[:10]:
                    console.print(f"  [red]✗[/red] {u['file']}:{u['line']} - \\cite{{{u['key']}}}")
                if len(undefined) > 10:
                    console.print(f"  [dim]... and {len(undefined) - 10} more[/dim]")
                console.print()

            if format_issues:
                console.print("[yellow bold]Citation Format Suggestions:[/yellow bold]")
                console.print("  Consider using [cyan]\\citep{{}}[/cyan] (parenthetical) or [cyan]\\citet{{}}[/cyan] (textual)")
                for f in format_issues[:5]:
                    console.print(f"  [yellow]→[/yellow] {f['file']}:{f['line']} - \\cite{{{f['key']}}}")
                if len(format_issues) > 5:
                    console.print(f"  [dim]... and {len(format_issues) - 5} more[/dim]")
                console.print()

            # VALIDATION MODE: Check each citation against real databases
            # Always validate when fixing or explicitly asked, including custom instructions
            validation_results = []
            if should_validate or should_fix or custom_instruction:
                validation_results = await self._validate_citations(session, console)

            # CUSTOM INSTRUCTION MODE (with validation results)
            if custom_instruction:
                console.print(
                    f"\n[bold]Applying: [cyan]{custom_instruction}[/cyan][/bold]\n"
                )
                await self._custom_fix_citations(
                    session, console, custom_instruction, validation_results,
                )
                return

            # FIX MODE: Generate patches using validation results
            if should_fix:
                await self._fix_citations(
                    session, console, undefined, format_issues,
                    uncited, validation_results
                )
            elif not should_validate:
                # Show tips
                if not undefined and not uncited and not format_issues:
                    console.print("[green bold]All citations are properly configured![/green bold]")
                else:
                    console.print("[dim]Tip: Run '/citations validate' to verify papers exist in real databases[/dim]")
                    console.print("[dim]     Run '/citations fix' to auto-generate fixes[/dim]")

        except Exception as e:
            console.print(f"[red]Error analyzing citations: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")

    async def _custom_fix_citations(
        self,
        session: SessionState,
        console: Console,
        user_instruction: str,
        validation_results: list | None = None,
    ) -> None:
        """Apply a free-form user instruction to citations via LLM."""
        if not session.llm_client:
            console.print("[red]LLM client not available[/red]")
            return

        # Get bib content with line numbers
        bib_filename = ""
        numbered_bib = "(No .bib file found)"
        bib_files = list(session.project_root.glob("**/*.bib"))
        if bib_files:
            bib_filename = bib_files[0].name
            numbered_bib = _numbered_content(bib_files[0])

        # Get paper content with line numbers
        filename = session.main_tex_path.name
        numbered_paper = _numbered_content(session.main_tex_path)

        # Build validation context if available
        validation_context = ""
        if validation_results:
            lines = []
            for r in validation_results:
                if r.status in ("likely_hallucinated", "needs_correction"):
                    lines.append(f"- {r.key}: {r.status} — {r.message}")
                    if r.search_results:
                        for sr in r.search_results[:2]:
                            lines.append(f"    Suggested: \"{sr.get('title', '')}\" ({sr.get('year', 'N/A')}) DOI:{sr.get('doi', 'N/A')}")
            if lines:
                validation_context = (
                    "\n\n## Validation Results (from CrossRef/Semantic Scholar API)\n"
                    + "\n".join(lines)
                )

        prompt = CITATION_CUSTOM_PROMPT.format(
            filename=filename,
            bib_filename=bib_filename or "references.bib",
            user_instruction=user_instruction,
            numbered_bib_content=numbered_bib,
            numbered_paper_content=numbered_paper,
        ) + validation_context

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
                    f"\n[green]Applied {applied} citation edit(s)[/green]"
                )
        else:
            console.print(
                "\n[yellow]No diff patches found in response.[/yellow]"
            )

    async def _validate_citations(
        self,
        session: SessionState,
        console: Console,
    ) -> list:
        """Validate citations against CrossRef and Semantic Scholar."""
        from texguardian.citations.validator import CitationValidator

        # Find .bib files
        bib_files = list(session.project_root.glob("**/*.bib"))
        if not bib_files:
            console.print("[yellow]No .bib files found[/yellow]")
            return []

        console.print("\n[bold cyan]Validating Citations Against Real Databases[/bold cyan]")
        console.print("[dim]Using CrossRef and Semantic Scholar APIs...[/dim]\n")

        validator = CitationValidator()
        all_results = []

        for bib_file in bib_files:
            console.print(f"[bold]Checking: {bib_file.name}[/bold]")
            results = await validator.validate_bib_file(bib_file, console)
            all_results.extend(results)

        # Summary
        console.print()
        valid_count = sum(1 for r in all_results if r.status == "valid")
        hallucinated_count = sum(1 for r in all_results if r.status == "likely_hallucinated")
        needs_correction_count = sum(1 for r in all_results if r.status == "needs_correction")
        not_found_count = sum(1 for r in all_results if r.status == "not_found")

        # Validation summary table
        val_table = Table(title="Validation Results")
        val_table.add_column("Status", style="cyan")
        val_table.add_column("Count", justify="right")

        val_table.add_row("Verified Valid", str(valid_count), style="green")
        val_table.add_row("Likely Hallucinated", str(hallucinated_count), style="red")
        val_table.add_row("Needs Correction", str(needs_correction_count), style="yellow")
        val_table.add_row("Could Not Verify", str(not_found_count), style="dim")

        console.print(val_table)
        console.print()

        # Show details for problems
        if hallucinated_count > 0:
            console.print("[red bold]⚠ Likely Hallucinated Citations:[/red bold]")
            for r in all_results:
                if r.status == "likely_hallucinated":
                    console.print(f"  [red]✗[/red] {r.key}: {r.original.title[:60]}...")
                    console.print(f"    [dim]{r.message}[/dim]")
                    if r.search_results:
                        console.print("    [cyan]Similar papers found:[/cyan]")
                        for sr in r.search_results[:2]:
                            console.print(f"      - {sr.get('title', '')[:50]}... ({sr.get('year', 'N/A')})")
            console.print()

        if needs_correction_count > 0:
            console.print("[yellow bold]Citations Needing Correction:[/yellow bold]")
            for r in all_results:
                if r.status == "needs_correction":
                    console.print(f"  [yellow]~[/yellow] {r.key}: {r.message}")
                    if r.suggested_correction:
                        sc = r.suggested_correction
                        if sc.doi:
                            console.print(f"    [green]Add DOI:[/green] {sc.doi}")
            console.print()

        return all_results

    async def _fix_citations(
        self,
        session: SessionState,
        console: Console,
        undefined: list,
        format_issues: list,
        uncited: list,
        validation_results: list,
    ) -> None:
        """Generate patches to fix citation issues."""
        if not session.llm_client:
            console.print("[red]LLM client not available for fixes[/red]")
            return

        # Check if there's anything to fix
        hallucinated = [r for r in validation_results if r.status == "likely_hallucinated"]
        needs_correction = [r for r in validation_results if r.status == "needs_correction"]

        if not undefined and not format_issues and not hallucinated and not needs_correction:
            console.print("[green]No issues to fix![/green]")
            return

        console.print("\n[cyan bold]Generating Fixes...[/cyan bold]\n")

        # Build issue list for LLM
        issues_text = []

        if undefined:
            issues_text.append("## UNDEFINED CITATIONS (not in .bib file):")
            for u in undefined[:10]:
                issues_text.append(f"  - {u['key']} at {u['file']}:{u['line']}")

        if hallucinated:
            issues_text.append("\n## LIKELY HALLUCINATED CITATIONS (not found in real databases):")
            for h in hallucinated[:10]:
                issues_text.append(f"  - {h.key}: \"{h.original.title}\"")
                issues_text.append(f"    Author: {h.original.author}")
                issues_text.append(f"    Year: {h.original.year}")
                if h.search_results:
                    issues_text.append("    Similar real papers found:")
                    for sr in h.search_results[:3]:
                        issues_text.append(f"      * \"{sr.get('title', '')}\" ({sr.get('year', 'N/A')}) - {sr.get('source', '')}")
                        if sr.get('doi'):
                            issues_text.append(f"        DOI: {sr.get('doi')}")
                        if sr.get('authors'):
                            issues_text.append(f"        Authors: {sr.get('authors')[:80]}...")

        if needs_correction:
            issues_text.append("\n## CITATIONS NEEDING CORRECTION (metadata issues):")
            for nc in needs_correction[:10]:
                issues_text.append(f"  - {nc.key}: {nc.message}")
                if nc.suggested_correction:
                    sc = nc.suggested_correction
                    issues_text.append(f"    Suggested DOI: {sc.doi}" if sc.doi else "")
                    issues_text.append(f"    Suggested title: {sc.title}" if sc.title != nc.original.title else "")

        if format_issues:
            issues_text.append("\n## FORMAT ISSUES (\\cite instead of \\citep/\\citet):")
            for f in format_issues[:10]:
                issues_text.append(f"  - {f['key']} at {f['file']}:{f['line']}")

        # Build validation results text
        validation_text = []
        for r in validation_results:
            if r.status in ("likely_hallucinated", "needs_correction"):
                validation_text.append(f"Key: {r.key}")
                validation_text.append(f"  Status: {r.status}")
                validation_text.append(f"  Original title: {r.original.title}")
                if r.search_results:
                    validation_text.append("  Suggested replacements from real databases:")
                    for sr in r.search_results[:2]:
                        validation_text.append(f"    - Title: {sr.get('title', '')}")
                        validation_text.append(f"      Authors: {sr.get('authors', '')}")
                        validation_text.append(f"      Year: {sr.get('year', '')}")
                        validation_text.append(f"      DOI: {sr.get('doi', '')}")
                        validation_text.append(f"      Source: {sr.get('source', '')}")

        # Get bib content with line numbers
        bib_filename = ""
        numbered_bib = "(No .bib file found)"
        bib_files = list(session.project_root.glob("**/*.bib"))
        if bib_files:
            bib_filename = bib_files[0].name
            numbered_bib = _numbered_content(bib_files[0])

        # Get paper content with line numbers
        filename = session.main_tex_path.name
        numbered_paper = _numbered_content(session.main_tex_path)

        prompt = CITATION_FIX_PROMPT.format(
            filename=filename,
            bib_filename=bib_filename or "references.bib",
            issues="\n".join(issues_text),
            validation_results="\n".join(validation_text) if validation_text else "No validation issues",
            numbered_bib_content=numbered_bib,
            numbered_paper_content=numbered_paper,
        )

        from texguardian.llm.prompts.system import COMMAND_SYSTEM_PROMPT
        from texguardian.llm.streaming import stream_llm

        response_text = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
            system=COMMAND_SYSTEM_PROMPT,
            max_tokens=6000,
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
                    f"\n[green]Applied {applied} citation fix(es)[/green]"
                )
        else:
            console.print(
                "\n[yellow]No diff patches found in response.[/yellow]"
            )
            console.print(
                "[dim]You can manually apply the suggestions above[/dim]"
            )

    def get_completions(self, partial: str) -> list[str]:
        """Get argument completions."""
        options = ["validate", "fix"]
        return [o for o in options if o.startswith(partial.lower())]


async def generate_and_apply_citation_fixes(
    session: SessionState,
    console: Console,
    *,
    auto_approve: bool = False,
    print_output: bool = True,
    visual_verify: bool = False,
    validation_results: list | None = None,
) -> int:
    """Reusable citation-fix pipeline callable from ``/review``.

    Parameters
    ----------
    validation_results:
        Pre-computed results from ``CitationValidator.validate_bib_file()``.
        When supplied the function skips the expensive API validation step,
        avoiding duplicate network calls when the caller already validated.

    Returns the number of patches applied.
    """
    from texguardian.latex.parser import LatexParser

    parser = LatexParser(session.project_root, session.config.project.main_tex)

    # Find .bib files
    bib_files = list(session.project_root.glob("**/*.bib"))
    if not bib_files:
        console.print("  [dim]No .bib files found[/dim]")
        return 0

    # Extract citation data
    citations = parser.extract_citations_with_locations()
    bib_keys = set(parser.extract_bib_keys())

    undefined = [c for c in citations if c["key"] not in bib_keys]
    format_issues = [c for c in citations if c["style"] == "cite"]

    # Validate against real databases (skip if caller already did this)
    if validation_results is None:
        from texguardian.citations.validator import CitationValidator

        validator = CitationValidator()
        validation_results = await validator.validate_bib_file(bib_files[0], console=console)

    hallucinated = [r for r in validation_results if r.status == "likely_hallucinated"]
    needs_correction = [r for r in validation_results if r.status == "needs_correction"]

    if not undefined and not format_issues and not hallucinated and not needs_correction:
        console.print("  [green]✓[/green] No citation issues to fix")
        return 0

    if not session.llm_client:
        console.print("  [red]LLM client not available[/red]")
        return 0

    # Build issue list (reuse same logic as _fix_citations)
    issues_text = []

    if undefined:
        issues_text.append("## UNDEFINED CITATIONS (not in .bib file):")
        for u in undefined[:10]:
            issues_text.append(f"  - {u['key']} at {u['file']}:{u['line']}")

    if hallucinated:
        issues_text.append("\n## LIKELY HALLUCINATED CITATIONS (not found in real databases):")
        for h in hallucinated[:10]:
            issues_text.append(f"  - {h.key}: \"{h.original.title}\"")
            issues_text.append(f"    Author: {h.original.author}")
            issues_text.append(f"    Year: {h.original.year}")
            if h.search_results:
                issues_text.append("    Similar real papers found:")
                for sr in h.search_results[:3]:
                    issues_text.append(f"      * \"{sr.get('title', '')}\" ({sr.get('year', 'N/A')}) - {sr.get('source', '')}")
                    if sr.get("doi"):
                        issues_text.append(f"        DOI: {sr.get('doi')}")
                    if sr.get("authors"):
                        issues_text.append(f"        Authors: {sr.get('authors')[:80]}...")

    if needs_correction:
        issues_text.append("\n## CITATIONS NEEDING CORRECTION (metadata issues):")
        for nc in needs_correction[:10]:
            issues_text.append(f"  - {nc.key}: {nc.message}")
            if nc.suggested_correction:
                sc = nc.suggested_correction
                if sc.doi:
                    issues_text.append(f"    Suggested DOI: {sc.doi}")
                if sc.title != nc.original.title:
                    issues_text.append(f"    Suggested title: {sc.title}")

    if format_issues:
        issues_text.append("\n## FORMAT ISSUES (\\cite instead of \\citep/\\citet):")
        for f in format_issues[:10]:
            issues_text.append(f"  - {f['key']} at {f['file']}:{f['line']}")

    # Build validation results text
    validation_text = []
    for r in validation_results:
        if r.status in ("likely_hallucinated", "needs_correction"):
            validation_text.append(f"Key: {r.key}")
            validation_text.append(f"  Status: {r.status}")
            validation_text.append(f"  Original title: {r.original.title}")
            if r.search_results:
                validation_text.append("  Suggested replacements from real databases:")
                for sr in r.search_results[:2]:
                    validation_text.append(f"    - Title: {sr.get('title', '')}")
                    validation_text.append(f"      Authors: {sr.get('authors', '')}")
                    validation_text.append(f"      Year: {sr.get('year', '')}")
                    validation_text.append(f"      DOI: {sr.get('doi', '')}")
                    validation_text.append(f"      Source: {sr.get('source', '')}")

    # Get file content with line numbers
    bib_filename = bib_files[0].name
    numbered_bib = _numbered_content(bib_files[0])
    filename = session.main_tex_path.name
    numbered_paper = _numbered_content(session.main_tex_path)

    prompt = CITATION_FIX_PROMPT.format(
        filename=filename,
        bib_filename=bib_filename,
        issues="\n".join(issues_text),
        validation_results="\n".join(validation_text) if validation_text else "No validation issues",
        numbered_bib_content=numbered_bib,
        numbered_paper_content=numbered_paper,
    )

    console.print("  [cyan]Generating citation fixes...[/cyan]")

    from texguardian.llm.prompts.system import COMMAND_SYSTEM_PROMPT
    from texguardian.llm.streaming import stream_llm

    response_text = await stream_llm(
        session.llm_client,
        messages=[{"role": "user", "content": prompt}],
        console=console,
        system=COMMAND_SYSTEM_PROMPT,
        max_tokens=6000,
        temperature=0.3,
        print_output=print_output,
    )

    if session.context:
        session.context.add_assistant_message(response_text)

    from texguardian.cli.approval import interactive_approval
    from texguardian.patch.parser import extract_patches

    patches = extract_patches(response_text)
    if not patches:
        console.print("  [yellow]No citation patches generated[/yellow]")
        return 0

    applied = await interactive_approval(patches, session, console, auto_approve=auto_approve)
    if applied > 0:
        console.print(f"  [green]Applied {applied} citation fix(es)[/green]")

    # Phase 2: Visual verification loop
    if visual_verify and applied > 0:
        from texguardian.visual.verifier import VisualVerifier

        console.print("  [cyan]Running visual verification of citation fixes...[/cyan]")
        try:
            verifier = VisualVerifier(session)
            vresult = await verifier.run_loop(
                max_rounds=session.config.safety.max_visual_rounds,
                console=console,
                focus_areas=["citations", "bibliography", "references", "inline citations"],
            )
            applied += vresult.patches_applied
        except Exception as e:
            console.print(f"  [red]Visual verification error: {e}[/red]")

    return applied

"""Feedback command for comprehensive paper analysis and scoring."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from texguardian.cli.commands.registry import Command
from texguardian.llm.prompts.scoring import QUALITY_SCORING_RUBRIC

if TYPE_CHECKING:
    from texguardian.core.session import SessionState


# Maximum characters of paper content to include in prompt.
# Claude models support 200k tokens (~800k chars). We keep paper content
# well under that to leave room for the prompt structure and output tokens.
# 80k chars ≈ 20k tokens, leaving ~180k for prompt overhead + output.
MAX_PAPER_CHARS = 80000

# Maximum output tokens for the LLM response.
# The JSON response contains 13 top-level keys with nested lists, detailed
# analysis text, and per-figure/table breakdowns. Typical comprehensive
# reviews run 4k-8k tokens; we set 16k to avoid truncation on large papers.
MAX_OUTPUT_TOKENS = 16000


FEEDBACK_PROMPT = """You are a senior ML researcher and expert reviewer for {venue}. Provide an extremely thorough, actionable review of the following paper.

## Scoring Rubric
{rubric}

## Paper Information
- Title: {title}
- Venue: {venue}
- Page limit: {max_pages} pages (excluding references)
- Minimum references required: {min_references}

## Paper Statistics
- Total characters: {total_chars:,}
- Estimated words: ~{word_count:,}
- Lines: {line_count:,}
- Sections: {section_count}
- Figures: {figure_count}
- Tables: {table_count}
- Equations: {equation_count}
- Citations used: {citation_count}
- Bibliography entries: {bib_entry_count}
{truncation_note}

## Paper Content
<paper>
{paper_content}
</paper>

## Your Task: Comprehensive Deep Review

Analyze this paper as if you were an Area Chair preparing detailed feedback for the authors. You must cover ALL of the following aspects thoroughly.

### 1. SCORES (integer 0-100 each, be calibrated and realistic)
- **Overall**: Publication readiness for {venue}
- **Structure**: Organization, logical flow, section completeness, appropriate length
- **Writing**: Clarity, grammar, conciseness, academic style, readability
- **Technical**: Correctness of claims, mathematical rigor, methodology soundness
- **Visual**: Figure quality, readability, captions, table formatting, layout
- **Citations**: Completeness, format consistency, relevance, coverage of related work
- **Impact**: Potential influence on the field, practical applications
- **Novelty**: Originality of contributions, differentiation from prior work

### 2. ACCEPTANCE PREDICTION (integer 0-100 probability each)
- Oral presentation probability
- Spotlight probability
- Poster probability
- Overall accept probability
- Detailed reasoning for your predictions (be specific about what helps/hurts)

### 3. FIGURE & TABLE ANALYSIS
For each figure and table in the paper:
- Name/label, whether it is necessary, clear, and well-captioned
- Any visual issues (resolution, axis labels, color choices, readability)
- Specific suggestions for improvement

### 4. ERROR DETECTION
- LaTeX errors or warnings visible in the source content
- Undefined references or broken citations
- Formatting inconsistencies (spacing, fonts, margins)
- Grammar/spelling issues (list specific examples with corrections)

### 5. QUESTIONS A REVIEWER WOULD ASK
- List 5-10 specific, pointed questions that reviewers would raise
- These should be questions the authors MUST address for acceptance

### 6. DETAILED IMPROVEMENTS
- **Critical (must fix)**: Issues that would cause rejection if not addressed
- **Important (should fix)**: Changes that would significantly improve acceptance chances
- **Minor (nice to have)**: Polish items for a stronger paper

### 7. WRITING SUGGESTIONS
- Specific sentences or paragraphs that need rewriting (quote them)
- Jargon that should be explained for the {venue} audience
- Claims that need supporting citations

### 8. MISSING ELEMENTS
- What is missing that similar accepted papers at {venue} typically include?
- What experiments, baselines, ablations, or analysis would strengthen the paper?

### 9. COMPARISON TO TOP PAPERS
- How does this compare to recent accepted papers at {venue}?
- What do top papers have that this one lacks?

## Output Format

You MUST output a single JSON object (no markdown fences, no text before or after). All scores must be integers, not strings. Use this exact structure:

{{"overall_score": 75, "category_scores": {{"structure": 80, "writing": 70, "technical": 75, "visual": 65, "citations": 80, "impact": 70, "novelty": 60}}, "acceptance_predictions": {{"oral": 5, "spotlight": 10, "poster": 35, "accept": 40, "reasoning": "..."}}, "figure_analysis": [{{"name": "Figure 1", "assessment": "...", "suggestions": "..."}}], "errors_found": ["error 1", "error 2"], "reviewer_questions": ["question 1", "question 2"], "improvements": {{"critical": ["..."], "important": ["..."], "minor": ["..."]}}, "writing_suggestions": ["suggestion 1"], "missing_elements": ["element 1"], "strengths": ["strength 1", "strength 2"], "weaknesses": ["weakness 1", "weakness 2"], "comparison_to_top_papers": "...", "summary": "2-3 sentence overall assessment", "actionable_next_steps": ["step 1", "step 2"]}}
"""


def _safe_int(value: object, default: int = 0) -> int:
    """Safely convert a value to int, handling strings and floats from LLM JSON."""
    if isinstance(value, int):
        return value
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default


def _extract_section(content: str, section_name: str) -> str | None:
    """Extract a section from LaTeX content by name.

    Returns the content from \\section{name} to the next \\section or \\end{document}.
    Returns None if not found.
    """
    # Match \section{Name} or \section*{Name}, case-insensitive
    pattern = re.compile(
        r"\\section\*?\{" + re.escape(section_name) + r"\}",
        re.IGNORECASE,
    )
    match = pattern.search(content)
    if not match:
        return None

    start = match.start()
    # Find the next \section or \end{document}
    next_section = re.search(r"\\(?:section\*?\{|end\{document\})", content[match.end():])
    if next_section:
        end = match.end() + next_section.start()
    else:
        end = len(content)

    return content[start:end]


def _count_paper_stats(content: str) -> dict:
    """Count paper statistics from LaTeX content."""
    lines = content.split("\n")
    # Rough word estimate: strip commands, math, comments
    text_only = re.sub(r"%.*", "", content)
    text_only = re.sub(r"\\[a-zA-Z]+\{[^}]*\}", "", text_only)
    text_only = re.sub(r"\$[^$]*\$", "", text_only)
    text_only = re.sub(r"\\[a-zA-Z]+", "", text_only)
    word_count = len(text_only.split())

    sections = len(re.findall(r"\\section\*?\{", content))
    figures = len(re.findall(r"\\begin\{figure", content))
    tables = len(re.findall(r"\\begin\{table", content))
    equations = len(re.findall(r"\\begin\{equation|\\begin\{align|\\\[", content))

    # Citation keys used in \cite{}, \citep{}, \citet{}
    cite_matches = re.findall(r"\\cite[pt]?\{([^}]+)\}", content)
    citation_keys = set()
    for match in cite_matches:
        for key in match.split(","):
            citation_keys.add(key.strip())

    return {
        "total_chars": len(content),
        "word_count": word_count,
        "line_count": len(lines),
        "section_count": sections,
        "figure_count": figures,
        "table_count": tables,
        "equation_count": equations,
        "citation_count": len(citation_keys),
    }


def _count_bib_entries(project_root) -> int:
    """Count bibliography entries from .bib files."""
    count = 0
    for bib_file in project_root.rglob("*.bib"):
        content = bib_file.read_text(errors="ignore")
        count += len(re.findall(r"@\w+\{", content))
    return count


class FeedbackCommand(Command):
    """Generate comprehensive feedback and scores for the paper."""

    name = "feedback"
    description = "Get comprehensive feedback, scores, and improvement suggestions for your paper"
    usage = "/feedback [section]  - Analyze entire paper or specific section"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute feedback analysis."""
        if not session.llm_client:
            console.print("[red]LLM client not initialized[/red]")
            return

        console.print("[cyan]Analyzing paper for feedback...[/cyan]")

        # Read the main tex file
        main_tex = session.project_root / session.config.project.main_tex
        if not main_tex.exists():
            console.print(f"[red]Main tex file not found: {main_tex}[/red]")
            return

        full_content = main_tex.read_text()

        # Compute stats on FULL content before any truncation
        stats = _count_paper_stats(full_content)
        stats["bib_entry_count"] = _count_bib_entries(session.project_root)

        # If a section is specified, extract just that section
        section_filter = args.strip() if args else None
        if section_filter:
            section_content = _extract_section(full_content, section_filter)
            if section_content:
                paper_content = section_content
                # Recompute stats for the section
                section_stats = _count_paper_stats(section_content)
                console.print(
                    f"[dim]Analyzing section: {section_filter} "
                    f"({section_stats['total_chars']:,} chars, "
                    f"~{section_stats['word_count']:,} words)[/dim]\n"
                )
            else:
                console.print(f"[yellow]Section '{section_filter}' not found, analyzing full paper[/yellow]\n")
                paper_content = full_content
        else:
            paper_content = full_content

        # Display paper stats to user
        truncated = len(paper_content) > MAX_PAPER_CHARS
        console.print(f"[dim]Paper: {stats['total_chars']:,} chars, "
                      f"~{stats['word_count']:,} words, "
                      f"{stats['line_count']:,} lines[/dim]")
        console.print(f"[dim]Content: {stats['section_count']} sections, "
                      f"{stats['figure_count']} figures, "
                      f"{stats['table_count']} tables, "
                      f"{stats['equation_count']} equations[/dim]")
        console.print(f"[dim]References: {stats['citation_count']} cited, "
                      f"{stats['bib_entry_count']} in bibliography[/dim]")

        if truncated:
            console.print(f"[yellow]Paper content truncated from {len(paper_content):,} "
                          f"to {MAX_PAPER_CHARS:,} chars for analysis[/yellow]")

        console.print(f"[dim]Max output tokens: {MAX_OUTPUT_TOKENS:,}[/dim]")
        console.print()

        # Truncate if too long
        truncation_note = ""
        if len(paper_content) > MAX_PAPER_CHARS:
            paper_content = paper_content[:MAX_PAPER_CHARS] + "\n\n[... content truncated for analysis ...]"
            truncation_note = (
                f"- NOTE: Paper content was truncated from {stats['total_chars']:,} "
                f"to {MAX_PAPER_CHARS:,} characters. Some later sections may be missing."
            )

        # Build prompt
        paper_spec = session.paper_spec
        prompt = FEEDBACK_PROMPT.format(
            title=paper_spec.title if paper_spec else "Unknown",
            venue=paper_spec.venue if paper_spec else "Unknown",
            max_pages=paper_spec.thresholds.max_pages if paper_spec else 9,
            min_references=paper_spec.thresholds.min_references if paper_spec else 30,
            paper_content=paper_content,
            rubric=QUALITY_SCORING_RUBRIC,
            total_chars=stats["total_chars"],
            word_count=stats["word_count"],
            line_count=stats["line_count"],
            section_count=stats["section_count"],
            figure_count=stats["figure_count"],
            table_count=stats["table_count"],
            equation_count=stats["equation_count"],
            citation_count=stats["citation_count"],
            bib_entry_count=stats["bib_entry_count"],
            truncation_note=truncation_note,
        )

        try:
            from texguardian.llm.streaming import stream_llm

            response_text = await stream_llm(
                session.llm_client,
                messages=[{"role": "user", "content": prompt}],
                console=console,
                max_tokens=MAX_OUTPUT_TOKENS,
                temperature=0.3,
            )
            console.print()  # newline after streaming

            # Extract JSON from response — try outermost braces
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                try:
                    feedback = json.loads(json_str)
                    self._display_feedback(feedback, console)
                except json.JSONDecodeError:
                    console.print("\n[dim]Note: Could not parse structured feedback.[/dim]")
            # If JSON parse fails, content was already streamed above

        except Exception as e:
            console.print(f"[red]Error getting feedback: {e}[/red]")

    def _display_feedback(self, feedback: dict, console: Console) -> None:
        """Display comprehensive structured feedback."""
        # Overall score with color coding
        overall = _safe_int(feedback.get("overall_score", 0))
        if overall >= 90:
            score_color = "green"
            status = "Publication Ready"
        elif overall >= 80:
            score_color = "cyan"
            status = "Minor Revisions Needed"
        elif overall >= 70:
            score_color = "yellow"
            status = "Moderate Revisions Needed"
        elif overall >= 60:
            score_color = "orange1"
            status = "Significant Revisions Needed"
        else:
            score_color = "red"
            status = "Major Revisions Required"

        # Score panel
        console.print(Panel(
            f"[bold {score_color}]{overall}/100[/bold {score_color}] - {status}",
            title="Overall Score",
            border_style=score_color,
        ))

        # Category scores table
        cat_scores = feedback.get("category_scores", {})
        if cat_scores:
            table = Table(title="Category Scores")
            table.add_column("Category", style="cyan")
            table.add_column("Score", justify="center")
            table.add_column("Status", justify="center")

            for cat, score in cat_scores.items():
                score = _safe_int(score)
                if score >= 80:
                    status_icon = "[green]\u2713 Good[/green]"
                elif score >= 70:
                    status_icon = "[yellow]\u25d0 OK[/yellow]"
                else:
                    status_icon = "[red]\u2717 Needs Work[/red]"
                table.add_row(cat.replace("_", " ").title(), f"{score}/100", status_icon)

            console.print(table)
            console.print()

        # Acceptance predictions
        predictions = feedback.get("acceptance_predictions", {})
        if predictions:
            console.print("[bold blue]Acceptance Predictions:[/bold blue]")
            pred_table = Table()
            pred_table.add_column("Outcome", style="cyan")
            pred_table.add_column("Probability", justify="center")
            for key in ["oral", "spotlight", "poster", "accept"]:
                prob = _safe_int(predictions.get(key, 0))
                if prob >= 70:
                    color = "green"
                elif prob >= 40:
                    color = "yellow"
                else:
                    color = "red"
                pred_table.add_row(key.title(), f"[{color}]{prob}%[/{color}]")
            console.print(pred_table)
            if predictions.get("reasoning"):
                console.print(f"  [dim]{predictions['reasoning']}[/dim]")
            console.print()

        # Strengths
        strengths = feedback.get("strengths", [])
        if strengths:
            console.print("[bold green]Strengths:[/bold green]")
            for s in strengths:
                console.print(f"  [green]\u2713[/green] {s}")
            console.print()

        # Weaknesses
        weaknesses = feedback.get("weaknesses", [])
        if weaknesses:
            console.print("[bold red]Weaknesses:[/bold red]")
            for w in weaknesses:
                console.print(f"  [red]\u2717[/red] {w}")
            console.print()

        # Figure/Table analysis
        figures = feedback.get("figure_analysis", [])
        if figures:
            console.print("[bold cyan]Figure & Table Analysis:[/bold cyan]")
            for fig in figures:
                if isinstance(fig, dict):
                    name = fig.get("name", "Figure")
                    assessment = fig.get("assessment", "")
                    suggestions = fig.get("suggestions", "")
                    console.print(f"  [cyan]\u2022[/cyan] [bold]{name}[/bold]: {assessment}")
                    if suggestions:
                        console.print(f"    [dim]\u2192 {suggestions}[/dim]")
                else:
                    console.print(f"  [cyan]\u2022[/cyan] {fig}")
            console.print()

        # Errors found
        errors = feedback.get("errors_found", [])
        if errors:
            console.print("[bold red]Errors Detected:[/bold red]")
            for e in errors:
                console.print(f"  [red]\u2717[/red] {e}")
            console.print()

        # Reviewer questions
        questions = feedback.get("reviewer_questions", [])
        if questions:
            console.print("[bold magenta]Questions Reviewers Will Ask:[/bold magenta]")
            for i, q in enumerate(questions, 1):
                console.print(f"  [magenta]{i}.[/magenta] {q}")
            console.print()

        # Improvements
        improvements = feedback.get("improvements", {})
        if improvements:
            console.print("[bold yellow]Suggested Improvements:[/bold yellow]")

            critical = improvements.get("critical", [])
            if critical:
                console.print("  [red bold]CRITICAL (must fix for acceptance):[/red bold]")
                for i, item in enumerate(critical, 1):
                    console.print(f"    [red]{i}.[/red] {item}")

            important = improvements.get("important", [])
            if important:
                console.print("  [yellow]Important (significantly improves chances):[/yellow]")
                for i, item in enumerate(important, 1):
                    console.print(f"    {i}. {item}")

            minor = improvements.get("minor", [])
            if minor:
                console.print("  [dim]Minor (polish):[/dim]")
                for i, item in enumerate(minor, 1):
                    console.print(f"    {i}. {item}")
            console.print()

        # Writing suggestions
        writing = feedback.get("writing_suggestions", [])
        if writing:
            console.print("[bold blue]Writing Suggestions:[/bold blue]")
            for w in writing:
                console.print(f"  [blue]\u2192[/blue] {w}")
            console.print()

        # Missing elements
        missing = feedback.get("missing_elements", [])
        if missing:
            console.print("[bold magenta]Missing Elements:[/bold magenta]")
            for m in missing:
                console.print(f"  [magenta]\u25cb[/magenta] {m}")
            console.print()

        # Comparison to top papers
        comparison = feedback.get("comparison_to_top_papers", "")
        if comparison:
            console.print(Panel(
                comparison,
                title="Comparison to Top Papers",
                border_style="cyan",
            ))

        # Actionable next steps
        steps = feedback.get("actionable_next_steps", [])
        if steps:
            console.print("[bold green]Actionable Next Steps (in order):[/bold green]")
            for i, step in enumerate(steps, 1):
                console.print(f"  [green]{i}.[/green] {step}")
            console.print()

        # Summary
        summary = feedback.get("summary", "")
        if summary:
            console.print(Panel(
                summary,
                title="Summary",
                border_style="blue",
            ))

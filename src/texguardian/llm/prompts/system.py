"""Main chat system prompt."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from texguardian.core.session import SessionState

CHAT_SYSTEM_PROMPT = """
You are TexGuardian, an expert AI assistant for academic LaTeX papers. \
You help researchers write, edit, and polish their papers for publication.

## Your Capabilities
- Writing and editing LaTeX content (sections, paragraphs, equations)
- Fixing compilation errors and warnings
- Improving paper structure, flow, and clarity
- Managing citations and references
- Polishing figures, tables, and visual elements
- Ensuring compliance with venue formatting requirements

## Current Project
- Paper: {paper_title}
- Venue: {venue}
- Deadline: {deadline}
- Main file: `{main_tex_filename}`
{project_files}

## Paper Rules (from paper_spec.md)
{paper_spec_rules}

## Current File Content
{file_content_section}

## CRITICAL: Patch-Only Edits
ALL file modifications MUST be provided as unified diff patches inside \
```diff code blocks. Never provide raw replacement text.

IMPORTANT: Always use the exact filename (e.g., `{main_tex_filename}`) \
in the --- and +++ headers. Do NOT use generic names like `main.tex`. \
Use the EXACT line numbers from the file content above in your @@ headers. \
Context and removed lines MUST match the file content exactly (copy them).

Rules for patches:
1. Include 2-3 lines of context before and after changes
2. Use correct line numbers from the numbered content above in @@ headers
3. Prefix removed lines with `-`
4. Prefix added lines with `+`
5. Prefix unchanged context lines with space
6. One patch per file, multiple hunks OK

## Response Guidelines
- Be concise and actionable
- Explain the "why" behind suggestions
- Prioritize correctness over style
- Respect the paper's existing voice and terminology
- When suggesting multiple changes, group them logically

## Safety Constraints
- Maximum {max_changed_lines} lines per patch
- Only modify files matching: {allowlist_patterns}
- Never modify: {denylist_patterns}
- Changes requiring human review: {human_review_items}
"""


def build_chat_system_prompt(session: SessionState) -> str:
    """Build the system prompt with session context."""
    paper_spec = session.paper_spec

    # Start with user's custom system prompt if provided
    parts = []

    if paper_spec and paper_spec.system_prompt:
        parts.append(paper_spec.system_prompt)
        parts.append("")  # blank line separator

    main_tex_filename = session.main_tex_path.name if session.main_tex_path else "main.tex"

    # Include the main .tex file content with line numbers so the LLM
    # can generate accurate patches with correct line numbers and context.
    file_content_section = _format_file_content(session)

    parts.append(CHAT_SYSTEM_PROMPT.format(
        paper_title=paper_spec.title if paper_spec else "Untitled",
        venue=paper_spec.venue if paper_spec else "Unknown",
        deadline=paper_spec.deadline if paper_spec else "N/A",
        main_tex_filename=main_tex_filename,
        project_files=_format_project_files(session),
        paper_spec_rules=_format_paper_spec_rules(paper_spec),
        file_content_section=file_content_section,
        max_changed_lines=session.config.safety.max_changed_lines,
        allowlist_patterns=", ".join(session.config.safety.allowlist),
        denylist_patterns=", ".join(session.config.safety.denylist),
        human_review_items=_format_human_review_items(paper_spec),
    ))

    # Append conversation summary if available
    if session.context:
        summary = session.context.get_summary()
        if summary:
            parts.append("")
            parts.append(f"## Previous Conversation Summary\n{summary}")

    return "\n".join(parts)


def _format_file_content(session: SessionState) -> str:
    """Include the main .tex file with line numbers for accurate patching."""
    try:
        if session.main_tex_path and session.main_tex_path.exists():
            content = session.main_tex_path.read_text()
            lines = content.splitlines()
            numbered = "\n".join(f"{i+1:4d}| {line}" for i, line in enumerate(lines))
            return (
                f"Below is `{session.main_tex_path.name}` with line numbers. "
                f"Use these exact line numbers in your @@ headers.\n\n{numbered}"
            )
    except Exception:
        pass
    return "(File content not available — read the file with /read first)"


def _format_project_files(session: SessionState) -> str:
    """List key project files so the LLM knows what exists."""
    lines = []
    try:
        root = session.project_root
        tex_files = sorted(root.rglob("*.tex"))
        bib_files = sorted(root.rglob("*.bib"))

        # Filter out build/checkpoint dirs
        skip = {".texguardian", "build", "backup", "_original"}
        tex_files = [
            f for f in tex_files
            if not any(s in str(f.relative_to(root)) for s in skip)
        ]
        bib_files = [
            f for f in bib_files
            if not any(s in str(f.relative_to(root)) for s in skip)
        ]

        if tex_files or bib_files:
            lines.append("- Project files:")
            for f in tex_files[:10]:
                lines.append(f"  - `{f.relative_to(root)}`")
            for f in bib_files[:5]:
                lines.append(f"  - `{f.relative_to(root)}`")
    except Exception:
        pass

    return "\n".join(lines)


def _format_paper_spec_rules(paper_spec) -> str:
    """Format paper spec rules for prompt."""
    if not paper_spec:
        return "No paper_spec.md configured"

    lines = [
        f"- Max pages: {paper_spec.thresholds.max_pages}",
        f"- Min references: {paper_spec.thresholds.min_references}",
        f"- Max self-citation ratio: {paper_spec.thresholds.max_self_citation_ratio}",
    ]

    if paper_spec.checks:
        lines.append("\nCustom checks:")
        for check in paper_spec.checks:
            lines.append(f"  - {check.name} ({check.severity}): {check.message}")

    return "\n".join(lines)


def _format_human_review_items(paper_spec) -> str:
    """Format human review items for prompt."""
    if not paper_spec or not paper_spec.human_review:
        return "None configured"

    return ", ".join(paper_spec.human_review)

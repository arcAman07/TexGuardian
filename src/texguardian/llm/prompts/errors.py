"""LaTeX error fixing prompts."""

LATEX_ERROR_FIX_PROMPT = """
Fix the following LaTeX compilation error.

## Error Details
```
{error_message}
```

## Error Location
- File: {file_path}
- Line: {line_number}
- Context:
```latex
{surrounding_context}
```

## Common Causes for This Error Type
{common_causes}

## Instructions
1. Identify the root cause of the error
2. Provide a minimal fix that resolves the issue
3. Output as a unified diff patch
4. Explain why the error occurred

## Output Format
### Explanation
[Brief explanation of the error cause]

### Patch
```diff
--- a/{file_path}
+++ b/{file_path}
@@ -X,Y +X,Y @@
[patch content]
```
"""

LATEX_ERROR_PATTERNS: dict[str, dict] = {
    "Undefined control sequence": {
        "causes": [
            "Missing \\usepackage{} for the command",
            "Typo in command name",
            "Command defined after use",
        ],
        "common_fixes": [
            "Add appropriate \\usepackage{} in preamble",
            "Fix spelling of command",
            "Move definition before first use",
        ],
    },
    "Missing $ inserted": {
        "causes": [
            "Math symbol used outside math mode",
            "Underscore or caret used in text mode",
        ],
        "common_fixes": [
            "Wrap in $...$ for inline math",
            "Use \\_ for literal underscore in text",
        ],
    },
    "File not found": {
        "causes": [
            "Wrong file path",
            "File extension mismatch",
            "File doesn't exist",
        ],
        "common_fixes": [
            "Check relative path from main.tex location",
            "Verify file exists and has correct extension",
        ],
    },
    "Missing } inserted": {
        "causes": [
            "Unclosed brace in command",
            "Mismatched braces in math mode",
        ],
        "common_fixes": [
            "Count and balance all { and } characters",
            "Check for nested braces in equations",
        ],
    },
    "Too many }'s": {
        "causes": [
            "Extra closing brace",
            "Missing opening brace",
        ],
        "common_fixes": [
            "Remove extra } or add missing {",
        ],
    },
}


LATEX_ERROR_FIX_FULL_PROMPT = """\
Fix the following LaTeX compilation errors.

## Errors
{errors_text}

## Full File Content (with line numbers)
```latex
{numbered_content}
```

## Common Causes
{common_causes}

## Instructions
1. Fix ALL errors listed above.
2. Provide minimal changes — do not rewrite unrelated code.
3. Output unified diff patches against the file shown above.
4. Use the exact filename shown in the header.

## Output Format
### Explanation
[Brief explanation of each error and fix]

### Patch
```diff
--- a/{filename}
+++ b/{filename}
@@ -X,Y +X,Y @@
[patch content]
```
"""


def _collect_common_causes(error_messages: list[str]) -> str:
    """Collect common causes for a list of error messages."""
    seen: set[str] = set()
    sections: list[str] = []
    for error_msg in error_messages:
        for pattern, info in LATEX_ERROR_PATTERNS.items():
            if pattern.lower() in error_msg.lower() and pattern not in seen:
                seen.add(pattern)
                causes = "\n".join(f"- {c}" for c in info["causes"])
                fixes = "\n".join(f"- {f}" for f in info["common_fixes"])
                sections.append(f"**{pattern}**\nCauses:\n{causes}\n\nCommon fixes:\n{fixes}")
                break
    return "\n\n".join(sections) if sections else "Unknown error type"


def build_error_fix_prompt(
    error_message: str,
    file_path: str,
    line_number: int,
    surrounding_context: str,
) -> str:
    """Build prompt for fixing a LaTeX error."""
    # Find matching error pattern
    common_causes = "Unknown error type"
    for pattern, info in LATEX_ERROR_PATTERNS.items():
        if pattern.lower() in error_message.lower():
            causes = "\n".join(f"- {c}" for c in info["causes"])
            fixes = "\n".join(f"- {f}" for f in info["common_fixes"])
            common_causes = f"Causes:\n{causes}\n\nCommon fixes:\n{fixes}"
            break

    return LATEX_ERROR_FIX_PROMPT.format(
        error_message=error_message,
        file_path=file_path,
        line_number=line_number,
        surrounding_context=surrounding_context,
        common_causes=common_causes,
    )


def build_full_error_fix_prompt(
    errors: list[str],
    filename: str,
    numbered_content: str,
) -> str:
    """Build prompt for fixing multiple LaTeX errors with full file context."""
    errors_text = "\n".join(f"- {e}" for e in errors)
    common_causes = _collect_common_causes(errors)

    return LATEX_ERROR_FIX_FULL_PROMPT.format(
        errors_text=errors_text,
        numbered_content=numbered_content,
        common_causes=common_causes,
        filename=filename,
    )

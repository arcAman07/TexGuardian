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

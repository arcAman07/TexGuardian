"""Patch generation and extraction prompts."""

PATCH_GENERATION_PROMPT = """
Generate a unified diff patch to fix the following issue in the LaTeX document.

## Issue Details
- File: {file_path}
- Line(s): {line_numbers}
- Problem: {problem_description}
- Desired outcome: {desired_outcome}

## Current Content (with line numbers)
```latex
{context_with_line_numbers}
```

## Requirements
1. Output ONLY a valid unified diff patch
2. Include exactly 3 lines of context before and after changes
3. Minimize the number of changed lines
4. Preserve existing formatting and indentation
5. Do not introduce new issues

## Output Format
```diff
--- a/{file_path}
+++ b/{file_path}
@@ -{old_start},{old_count} +{new_start},{new_count} @@
 context line 1
 context line 2
 context line 3
-line to remove
+line to add
 context line 4
 context line 5
 context line 6
```
"""

PATCH_EXTRACTION_PROMPT = """
Extract any unified diff patches from the following assistant response.

Response:
{response_text}

If patches are found, output them in this JSON format:
```json
{{
  "patches_found": true,
  "patches": [
    {{
      "file_path": "path/to/file.tex",
      "diff_text": "--- a/path/to/file.tex\\n+++ b/path/to/file.tex\\n..."
    }}
  ]
}}
```

If no patches are found, output:
```json
{{
  "patches_found": false,
  "patches": []
}}
```
"""


def build_patch_generation_prompt(
    file_path: str,
    line_numbers: str,
    problem_description: str,
    desired_outcome: str,
    context_with_line_numbers: str,
) -> str:
    """Build prompt for patch generation."""
    return PATCH_GENERATION_PROMPT.format(
        file_path=file_path,
        line_numbers=line_numbers,
        problem_description=problem_description,
        desired_outcome=desired_outcome,
        context_with_line_numbers=context_with_line_numbers,
    )

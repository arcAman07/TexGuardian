"""Citation verification prompts."""

CITATION_ANALYSIS_PROMPT = """
Analyze the citations in this LaTeX document for correctness and consistency.

## Bibliography Entries (from .bib file)
```bibtex
{bib_content}
```

## Citation Usage (extracted from .tex files)
{citation_usages}

## Check for:
1. **Undefined citations**: Keys used in \\cite{{}} but not in .bib
2. **Uncited references**: Keys in .bib but never cited
3. **Format consistency**: Mix of \\cite{{}}, \\citep{{}}, \\citet{{}}
4. **Self-citations**: Ratio of self-citations to total
5. **Missing fields**: Required fields (author, title, year) not present
6. **Duplicate keys**: Same key defined multiple times

## Venue Requirements
- Minimum references: {min_references}
- Maximum self-citation ratio: {max_self_citation_ratio}
- Required citation style: {citation_style}

## Output Format
```json
{{
  "total_citations": 32,
  "unique_references": 28,
  "self_citations": 4,
  "self_citation_ratio": 0.125,
  "issues": [
    {{
      "type": "undefined_citation",
      "severity": "error",
      "key": "smith2024",
      "location": "intro.tex:45",
      "message": "Citation key 'smith2024' not found in bibliography"
    }},
    {{
      "type": "format_inconsistency",
      "severity": "warning",
      "location": "method.tex:67",
      "message": "Using \\cite{{}} instead of \\citep{{}} for parenthetical citation",
      "suggestion": "Replace \\cite{{jones2023}} with \\citep{{jones2023}}"
    }}
  ],
  "summary": "28 valid citations, 2 issues found"
}}
```
"""


def build_citation_analysis_prompt(
    bib_content: str,
    citation_usages: list[dict],
    min_references: int = 30,
    max_self_citation_ratio: float = 0.2,
    citation_style: str = "natbib",
) -> str:
    """Build prompt for citation analysis."""
    usages_text = "\n".join(
        f"- {u['file']}:{u['line']}: {u['citation']}" for u in citation_usages
    )

    return CITATION_ANALYSIS_PROMPT.format(
        bib_content=bib_content,
        citation_usages=usages_text,
        min_references=min_references,
        max_self_citation_ratio=max_self_citation_ratio,
        citation_style=citation_style,
    )

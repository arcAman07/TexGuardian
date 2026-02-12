"""Section verification prompts."""

SECTION_VERIFY_PROMPT = """
Verify the content and structure of the "{section_name}" section.

## Section Content
```latex
{section_content}
```

## Venue Guidelines for {section_name}
{venue_guidelines}

## Paper Spec Rules
{relevant_checks}

## Check for:
1. **Completeness**: Does it cover all required elements?
2. **Length**: Is it within expected word/paragraph count?
3. **Flow**: Does it transition smoothly from previous section?
4. **Claims**: Are all claims supported or cited?
5. **Terminology**: Is terminology consistent with rest of paper?

## Context
- Previous section: {previous_section_summary}
- Next section: {next_section_summary}
- Key terms defined earlier: {defined_terms}

## Output Format
```json
{{
  "section": "{section_name}",
  "word_count": 450,
  "paragraph_count": 4,
  "issues": [
    {{
      "severity": "warning",
      "type": "missing_element",
      "description": "Introduction typically states contributions but none found",
      "suggestion": "Add a paragraph listing main contributions",
      "line_range": [15, 20]
    }}
  ],
  "strengths": [
    "Clear problem statement",
    "Good motivation"
  ],
  "summary": "Section is mostly complete but missing explicit contribution list"
}}
```
"""

VENUE_GUIDELINES: dict[str, dict[str, str]] = {
    "NeurIPS": {
        "Introduction": "Clear problem statement, motivation, and contributions list",
        "Related Work": "Comprehensive coverage, clear positioning",
        "Method": "Detailed algorithm description, theoretical grounding",
        "Experiments": "Multiple baselines, ablations, statistical significance",
        "Conclusion": "Summary, limitations, broader impact",
    },
    "ICML": {
        "Introduction": "Problem importance, contributions, paper outline",
        "Related Work": "Prior work comparison, clear novelty",
        "Method": "Formal problem setup, algorithm details",
        "Experiments": "Reproducibility details, comprehensive evaluation",
    },
    "ACL": {
        "Introduction": "Task definition, motivation, contributions",
        "Related Work": "NLP-specific prior work",
        "Method": "Model architecture, training details",
        "Experiments": "Standard benchmarks, error analysis",
    },
}


def build_section_verify_prompt(
    section_name: str,
    section_content: str,
    venue: str = "Unknown",
    previous_section: str = "N/A",
    next_section: str = "N/A",
    defined_terms: list[str] | None = None,
    relevant_checks: str = "None",
) -> str:
    """Build prompt for section verification."""
    guidelines = VENUE_GUIDELINES.get(venue, {})
    venue_guidelines = guidelines.get(section_name, "No specific guidelines")

    return SECTION_VERIFY_PROMPT.format(
        section_name=section_name,
        section_content=section_content,
        venue_guidelines=venue_guidelines,
        relevant_checks=relevant_checks,
        previous_section_summary=previous_section,
        next_section_summary=next_section,
        defined_terms=", ".join(defined_terms) if defined_terms else "None defined",
    )

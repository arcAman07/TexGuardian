"""Quality scoring rubric."""

QUALITY_SCORING_RUBRIC = """
## Quality Score Calculation (0-100)

### Category Weights
- Structure (20%): Section organization, flow, completeness
- Writing (25%): Clarity, grammar, conciseness
- Technical (25%): Correctness of claims, math, algorithms
- Visual (15%): Figures, tables, formatting
- Citations (15%): Proper references, no missing citations

### Scoring Guide

**90-100 (Excellent)**: Publication-ready
- No errors
- Only minor stylistic suggestions
- All venue requirements met

**80-89 (Good)**: Minor revisions needed
- No critical errors
- Some warnings to address
- Meets most requirements

**70-79 (Acceptable)**: Moderate revisions needed
- Few errors, several warnings
- Some missing elements
- May exceed page limit

**60-69 (Needs Work)**: Significant revisions needed
- Multiple errors
- Missing required sections
- Major formatting issues

**Below 60 (Major Issues)**: Substantial rewrite needed
- Critical errors throughout
- Missing core content
- Does not meet venue requirements

### Deductions
- Critical error (cut-off content, broken figure): -10 per instance
- Missing required section: -15 per section
- Undefined citation: -5 per citation
- Exceeded page limit: -5 per page over
- Inconsistent formatting: -3 per instance
"""


def calculate_quality_score(
    error_count: int = 0,
    warning_count: int = 0,
    info_count: int = 0,
    pages_over_limit: int = 0,
    missing_sections: int = 0,
    undefined_citations: int = 0,
) -> int:
    """Calculate quality score based on issues found."""
    score = 100

    # Deductions
    score -= error_count * 10
    score -= warning_count * 3
    score -= info_count * 1
    score -= pages_over_limit * 5
    score -= missing_sections * 15
    score -= undefined_citations * 5

    return max(0, min(100, score))

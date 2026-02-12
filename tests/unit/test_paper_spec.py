"""Tests for paper_spec.md parsing."""

import pytest

from texguardian.config.paper_spec import PaperSpec


def test_parse_frontmatter():
    """Test parsing YAML frontmatter."""
    content = """---
title: "Test Paper"
venue: "NeurIPS 2026"
thresholds:
  max_pages: 8
  min_references: 25
---

# Content
"""

    spec = PaperSpec.parse(content)

    assert spec.title == "Test Paper"
    assert spec.venue == "NeurIPS 2026"
    assert spec.thresholds.max_pages == 8
    assert spec.thresholds.min_references == 25


def test_parse_check_blocks():
    """Test parsing check blocks."""
    content = """---
title: "Test"
---

# Checks

```check
name: todo_check
severity: error
pattern: "TODO"
message: "Remove TODOs"
```

```check
name: citation_check
severity: warning
pattern: "\\\\cite\\\\{"
message: "Use citep/citet"
```
"""

    spec = PaperSpec.parse(content)

    assert len(spec.checks) == 2
    assert spec.checks[0].name == "todo_check"
    assert spec.checks[0].severity == "error"
    assert spec.checks[1].name == "citation_check"
    assert spec.checks[1].severity == "warning"


def test_parse_human_review():
    """Test parsing human review triggers."""
    content = """---
title: "Test"
human_review:
  - "Changes to abstract"
  - "Large deletions"
---
"""

    spec = PaperSpec.parse(content)

    assert len(spec.human_review) == 2
    assert "Changes to abstract" in spec.human_review


def test_default_values():
    """Test default values for missing fields."""
    content = "# Just markdown"

    spec = PaperSpec.parse(content)

    assert spec.title == "Untitled Paper"
    assert spec.venue == "Unknown"
    assert spec.thresholds.max_pages == 9

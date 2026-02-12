---
title: "Beyond Benchmark Maxxing: Position Paper"
venue: "ICML 2026"
deadline: "2026-01-30"
thresholds:
  max_pages: 9
  min_references: 30
  max_self_citation_ratio: 0.2
human_review:
  - "Changes to abstract"
  - "Deletion of more than 10 lines"
  - "Modifications to figures"
---

# Paper Specification - Position Paper

This paper is a position paper for ICML 2026 about esoteric programming languages as benchmarks.

## Custom Checks

```check
name: figure_overflow
severity: error
pattern: "width=1\\.[2-9]\\\\columnwidth|width=[2-9]\\.\\d*\\\\columnwidth"
message: "Figure width exceeds column width - will cause overflow"
```

```check
name: table_overflow
severity: warning
pattern: "begin\\{tabular\\}\\{[^}]{10,}\\}"
message: "Table may have too many columns - check for overflow"
```

```check
name: citation_format
severity: warning
pattern: "\\\\cite\\{(?!p|t)"
message: "Use \\citep{} or \\citet{} instead of \\cite{}"
```

```check
name: todo_remaining
severity: error
pattern: "TODO|FIXME|XXX"
message: "Remove TODO/FIXME markers before submission"
```

## Known Issues to Fix

This example paper has been modified to introduce overflow issues:
1. Figure at line ~125 has width=1.35\columnwidth (should be 1.0 or less)
2. Table at line ~274 has too many wide columns

These should be detected by /verify and fixed by the LLM.

## Notes

- ICML 2026 page limit: 9 pages (excluding references)
- Use natbib citation style

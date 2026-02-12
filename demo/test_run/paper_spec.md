---
title: "Scaling Sparse Mixture-of-Experts for Long-Context Document Understanding"
venue: "NeurIPS 2026"
deadline: "2026-05-15"
thresholds:
  max_pages: 9
  min_references: 20
  max_self_citation_ratio: 0.2
human_review:
  - "Changes to abstract"
  - "Deletion of more than 10 lines"
---

# Paper Specification

```system-prompt
You are an expert ML researcher and LaTeX editor specializing in NeurIPS papers.
Write in formal academic English. Use \citep{} for parenthetical citations and
\citet{} for textual citations. Use booktabs for tables — never \hline.
All figures must fit within \columnwidth.
```

## Custom Checks

```check
name: citation_format
severity: warning
pattern: \\cite{(?!p|t)
message: Use \citep{} or \citet{} instead of \cite{}
```

```check
name: todo_remaining
severity: error
pattern: TODO|FIXME|XXX
message: Remove TODO/FIXME markers before submission
```

```check
name: figure_overflow
severity: error
pattern: width\s*=\s*1\.[2-9]
message: Figure width exceeds column width — will cause overflow
```

```check
name: hline_usage
severity: warning
pattern: \\hline
message: Use booktabs (\toprule, \midrule, \bottomrule) instead of \hline
```

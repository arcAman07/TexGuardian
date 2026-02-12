# Test Run — TexGuardian Demo

This directory contains a LaTeX paper with **17 deliberate issues** for testing TexGuardian.

## Quick Start

```bash
cd demo/test_run
texguardian init
# Edit texguardian.yaml: change main_tex from "main.tex" to "demo_paper.tex"
texguardian chat
```

Then inside the REPL:

```
/verify              # See all 17 issues
/figures fix         # Fix overflowing figures
/tables fix          # Fix bad tables
/citations fix       # Fix citation problems
/feedback            # Get overall score
```

## Deliberate Issues

### Overflowing Figures (3)
| Line | Width | Issue |
|------|-------|-------|
| ~107 | `width=1.4\columnwidth` | 40% overflow |
| ~125 | `width=1.8\textwidth` | Massive overflow |
| ~160 | `width=2.0\columnwidth` | 2x overflow |

### Bad Tables (2)
| Line | Issue |
|------|-------|
| ~140 | 9 columns, uses `\hline` instead of booktabs, too wide |
| ~180 | Uses `\hline` instead of `\toprule/\midrule/\bottomrule` |

### Undefined Citations (4)
| Key | Issue |
|-----|-------|
| `nonexistent_paper_2024` | Cited but not in .bib |
| `hallucinated_reference_2023` | Cited but not in .bib |
| `also_fake_citation_2025` | Cited but not in .bib |
| `another_missing_ref` | Cited but not in .bib |

### Uncited References (3)
| Key | Issue |
|-----|-------|
| `unused_reference_2024` | In .bib but never cited |
| `another_unused_ref` | In .bib but never cited |
| `stale_draft_reference` | In .bib but never cited |

### Wrong Citation Style (2)
| Line | Issue |
|------|-------|
| ~42 | `\cite{devlin2019bert}` should be `\citep{}` or `\citet{}` |
| ~43 | `\cite{vaswani2017attention}` should be `\citep{}` or `\citet{}` |

### TODO/FIXME/XXX Markers (5)
| Line | Marker |
|------|--------|
| ~29 | `TODO: Rewrite this abstract` |
| ~50 | `FIXME: Need to strengthen this motivation` |
| ~96 | `XXX: Should we add a paragraph` |
| ~133 | `TODO: Add the load balancing loss equation` |
| ~196 | `TODO: Add qualitative examples` |

### Undefined Figure Reference (1)
| Line | Issue |
|------|-------|
| ~72 | `\ref{fig:nonexistent_figure}` — label doesn't exist |

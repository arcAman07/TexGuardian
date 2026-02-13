# Test Run — TexGuardian Demo

Live demo of TexGuardian's review pipeline. Start with a broken paper, run the
tool, and compare the fixed output against `error_paper.pdf`.

## Files

| File | Description |
|------|-------------|
| `demo_paper.tex` | LaTeX paper with 6 intentional formatting issues |
| `demo_refs.bib` | Bibliography (11 references) |
| `error_paper.pdf` | Pre-compiled snapshot showing all issues (the "before") |
| `paper_spec.md` | Paper specification (ICLR 2026, custom checks) |
| `texguardian.yaml` | TexGuardian configuration |
| `build/` | Output directory (fixed PDF appears here after review) |

## Intentional Issues in demo_paper.tex

| # | Issue | What You See |
|---|-------|-------------|
| 1 | Table 1 overflows (11 columns) | Last 4 columns cut off at right margin |
| 2 | Figure 2 overflows (`width=1.8\columnwidth`) | Bar chart extends past page edge |
| 3 | Table 2 overflows (10 columns) | Last 3 columns cut off at right margin |
| 4 | Table 3 uses `\hline` with `\|` separators | Ugly borders instead of booktabs rules |
| 5 | Bare `\cite{devlin2019bert}` | Should be `\citep{}` or `\citet{}` |
| 6 | Duplicate `\usepackage{natbib}` | Lines 8 and 15 |

## Running the Demo

```bash
cd demo/test_run
texguardian chat
```

Inside the chat session:

```
/venue iclr 2026
/review full
```

1. `/venue iclr 2026` — fetch ICLR 2026 style files and update document class
2. `/review full` — runs the full 7-step fix pipeline until score >= 90

After `/review full` completes, the fixed PDF is at `build/demo_paper.pdf`.
Compare it side-by-side with `error_paper.pdf` to see all issues resolved.

## Pipeline Steps (7-step review)

`/review full` loops until score reaches 90+:

1. **Compile** — Build PDF with latexmk
2. **Verify** — Run all checks (page limit, citations, figures, custom rules)
3. **Fix Issues** — LLM generates patches for verification failures
4. **Citations** — Validate against CrossRef / Semantic Scholar
5. **Figures** — Detect overflow, missing labels/captions
6. **Tables** — Detect `\hline`, overflow, formatting issues
7. **Visual Polish** — Vision model inspects rendered PDF, patches layout

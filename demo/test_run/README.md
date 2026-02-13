# Test Run — TexGuardian Demo

This directory contains a realistic ML research paper (`demo_paper.tex`) with intentional formatting issues for demonstrating TexGuardian's capabilities.

## Quick Start

```bash
cd demo/test_run
texguardian chat
```

## Known Issues in demo_paper.tex

| Issue | Location | Description |
|-------|----------|-------------|
| Figure overflow | Line ~137 | `width=1.5\columnwidth` exceeds column width |
| Wide table | Line ~51 | 10-column table overflows margins |
| Wide table | Line ~171 | 9-column table overflows margins |
| Duplicate `\usepackage{natbib}` | Lines 8,15 | natbib loaded twice |

## Screen Recording Commands

Run these commands inside `texguardian chat` to demo all features.
Each section is designed to flow naturally for a screen recording.

### 1. Orientation (Non-LLM)
```
/help
/compile --clean
/page_count
/verify
/report
```

### 2. Deep Analysis (LLM)
```
/feedback
/section
/section Introduction
```

### 3. Citations
```
/citations
/citations fix
/suggest_refs
```

### 4. Figures
```
/figures
/figures fix
/figures analyze
```

### 5. Tables
```
/tables
/tables fix
/tables analyze
```

### 6. Section Editing
```
/section Introduction fix
/section Method
```

### 7. Submission Workflow
```
/venue
/venue list
/anonymize
/camera_ready
```

### 8. Visual Polish
```
/compile
/polish_visual
```

### 9. Full Pipeline
```
/review quick
```

### 10. Utilities
```
/model
/model list
/read demo_paper.tex
/grep citep
/bash ls *.tex
/diff
/revert
/watch on
/watch off
```

## Files

| File | Description |
|------|-------------|
| `demo_paper.tex` | Main LaTeX paper (Sparse-MoE-Doc) with intentional issues |
| `demo_refs.bib` | Bibliography with 11 references |
| `texguardian.yaml` | TexGuardian configuration |
| `paper_spec.md` | Paper specification (ICLR 2026, custom checks) |
| `error_paper.pdf` | Pre-compiled PDF showing issues before fixes |
| `demo_paper.pdf` | Latest compiled PDF |
| `iclr2026_conference.sty` | ICLR 2026 style file |
| `iclr2026_conference.bst` | ICLR 2026 bibliography style |

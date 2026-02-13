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

## Commands to Test (Screen Recording Guide)

Run these commands inside `texguardian chat` to demonstrate all features:

### Core Commands
```
/help                    # Show all available commands
/compile                 # Compile the LaTeX document
/compile --clean         # Clean build artifacts and recompile
/verify                  # Run all verification checks
/page_count              # Show page count and section breakdown
/report                  # Generate comprehensive verification report
/model                   # Show current LLM model
/model list              # List available models
```

### Content Analysis & Fixing
```
/figures                 # Verify all figures
/figures fix             # Auto-fix figure issues (overflow)
/figures analyze         # Deep AI analysis of figures
/tables                  # Verify all tables
/tables fix              # Auto-fix table issues
/tables analyze          # Deep AI analysis of tables
/citations               # Verify citations
/citations fix           # Auto-fix citation issues
/suggest_refs            # AI-powered citation recommendations
/section                 # List all sections
/section Introduction    # Analyze Introduction section
/section Introduction fix # Auto-fix Introduction issues
/feedback                # Get comprehensive paper feedback with scores
```

### Submission Workflow
```
/venue                   # List supported conference venues
/venue iclr 2026         # Download ICLR 2026 style files
/camera_ready            # Convert to camera-ready format
/anonymize               # Make paper anonymous for review
```

### Visual Verification
```
/polish_visual           # Run visual verification loop with vision model
```

### Full Pipeline
```
/review quick            # Run full review pipeline (without visual polish)
/review full             # Run full review pipeline (with visual polish)
```

### File Operations
```
/read demo_paper.tex     # Display file with line numbers
/grep citep              # Search for pattern in files
/bash ls *.tex           # Run shell command
```

### Version Control
```
/diff                    # Show changes since last checkpoint
/revert                  # List/revert to previous checkpoint
```

## Files

| File | Description |
|------|-------------|
| `demo_paper.tex` | Main LaTeX paper (Sparse-MoE-Doc) |
| `demo_refs.bib` | Bibliography with 11 references |
| `texguardian.yaml` | TexGuardian configuration |
| `paper_spec.md` | Paper specification (ICLR 2026, custom checks) |
| `error_paper.pdf` | Pre-compiled PDF showing issues before fixes |
| `demo_paper.pdf` | Latest compiled PDF |

# Changelog

All notable changes to TexGuardian will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.2] - 2025-02-13

### Changed

- **TinyTeX is now the default** — search path priority, install hints (`texguardian doctor`), README, and docs all recommend TinyTeX first; MacTeX/TeX Live remain as fallbacks
- **Patch applier whitespace-tolerant** — context and removed lines are now compared with normalized whitespace (collapsed spaces, stripped trailing), fixing LLM-generated patches that failed due to minor whitespace differences
- **Patch search window widened** — context search increased from ±10 to ±30 lines for better match rates on shifted hunks

### Fixed

- **Demo paper compilation** — added `\usepackage{amsmath}` and `\usepackage{amssymb}` so `\checkmark` and `\text{}` compile without errors
- **Hardcoded path removed** — `examples/position_paper/texguardian.yaml` had an absolute path to latexmk; now uses `"latexmk"` with PATH discovery

## [0.2.1] - 2025-02-13

### Fixed

- **`__version__` synced** — `__init__.py` was stuck at 0.1.0, now matches pyproject.toml
- **README command aliases corrected** — `/tables` aliases fixed to `/tabs`, `/tab`; `/venue` to `/template`, `/conf`; `/feedback` has no aliases
- **docs/INSTALL.md** — updated wheel filename references to current version

## [0.2.0] - 2025-02-13

### Fixed

- **Figure overflow detection** — `/figures fix`, `/review full`, and `generate_and_apply_figure_fixes()` now detect `width > \columnwidth` and `\hspace{-...}` overflow issues, not just missing labels/captions
- **Review pipeline always runs LLM analysis** — Steps 4 (figures) and 5 (tables) no longer skip LLM fix when only overflow or `\hline` issues exist; the LLM always analyzes all elements when in fix mode
- **Review pipeline table `\hline` detection** — `_step_tables()` now detects `\hline` usage (matching the standalone `/tables fix` command)
- **Standalone fix commands always run visual verify** — `/figures fix` and `/tables fix` now run the compile→render→vision loop even when no structural issues are found, catching visual-only problems like overflow
- **Final recompile after review** — `/review full` adds a final compile after Step 7 to guarantee the PDF in `build/` reflects all patches

### Removed

- **ICLR template files from demo folder** — `/venue` downloads templates live at runtime instead of bundling them

## [0.1.9] - 2025-02-13

### Added

- **TinyTeX documentation** in README and docs/INSTALL.md — lightweight (~250 MB) alternative to full TeX Live (~4 GB), with install commands, PATH setup, and `tlmgr` package management
- **Recording tool explanations** in DEMO_SCRIPT.md — detailed how-it-works descriptions for macOS screen recording, VHS automated terminal recording, and asciinema interactive recording

### Changed

- **Demo paper cleaned up** — title, abstract, citations, and TODO markers fixed so the demo focuses on figure/table issues for the review pipeline to find
- Updated demo scripts (`DEMO_SCRIPT.md`, `demo.tape`) to showcase the 7-step `/review full` pipeline as the centerpiece
- Recompiled `error_paper.pdf` with TinyTeX from cleaned sources

## [0.1.8] - 2025-02-13

### Added

- **Compile-verify-fix loops** for `/figures fix`, `/tables fix`, and `/review`:
  - After structural patches (missing labels, bad captions, etc.), the pipeline now recompiles the paper, renders the PDF, sends pages to the vision model, and loops to catch residual issues
  - `/figures fix` now runs a visual verification loop (Step 3) using `VisualVerifier.run_loop()` with figure-focused analysis
  - `/tables fix` now runs a visual verification loop (Step 3) using `VisualVerifier.run_loop()` with table-focused analysis
  - `/review` pipeline expanded from 6 to 7 steps: new Step 6 verifies structural fixes visually before the general visual polish in Step 7
- **`visual_verify` parameter** on `generate_and_apply_figure_fixes()` and `generate_and_apply_table_fixes()` — when `True`, triggers a post-fix visual verification loop
- **Focused visual analysis** — visual verification in figures/tables commands uses targeted `focus_areas` (e.g., "figure placement", "table alignment", "booktabs") to steer the vision model

### Changed

- `/review` pipeline renumbered from 6 steps to 7 steps (Steps 1–5 unchanged, Step 6 = visual verification of fixes, Step 7 = general visual polish)
- `_visual_verify_figures()` in `FiguresCommand` replaced stub implementation with full `VisualVerifier.run_loop()` integration

## [0.1.0] - 2025-02-12

### Added

- **Interactive REPL** with prompt-toolkit completion, history, and auto-suggest
- **26 slash commands** covering the full paper lifecycle:
  - **Analysis**: `/verify`, `/figures`, `/tables`, `/citations`, `/section`, `/page_count`, `/feedback`, `/suggest_refs`
  - **Preparation**: `/anonymize`, `/camera_ready`, `/venue`, `/compile`, `/review`, `/polish_visual`
  - **Configuration**: `/model` (list, set, search, natural language)
  - **File Operations**: `/read`, `/grep`, `/search`, `/bash`, `/write`
  - **Version Control**: `/diff`, `/revert`, `/approve`, `/watch`
  - **Other**: `/help`, `/report`
- **LLM integration** with two providers:
  - AWS Bedrock (Claude Opus 4.5, Opus 4, Sonnet 4, Sonnet 3.7)
  - OpenRouter (any model from openrouter.ai/models)
- **Natural language mode** — type plain English, the LLM understands context
- **LLM-powered natural language** for `/venue` and `/model` commands
- **Unified diff patch system** — LLM generates patches, user reviews before applying
- **Checkpoint and rollback** — automatic checkpoints before every edit
- **Paper specification** (`paper_spec.md`) with YAML frontmatter, custom checks, and system prompt
- **Configuration** (`texguardian.yaml`) for provider, model, safety limits, LaTeX settings
- **Safety system** — allowlist/denylist, max changed lines, max rounds, human review triggers
- **Visual verification pipeline** — PDF rendering, vision model analysis, pixel diffing
- **Conversation context management** with token-aware compaction and LLM-based summarization
- **LaTeX compilation** via latexmk with configurable engine and timeout
- **Citation validation** with CrossRef and Semantic Scholar lookups
- **Tab completion** for commands and arguments
- **File history** persisted across sessions
- **`texguardian init`** command for project setup
- **`texguardian doctor`** command for toolchain verification
- **Example papers** — esolang_paper and position_paper for testing
- **Demo folder** with sample paper and recording script

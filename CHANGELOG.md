# Changelog

All notable changes to TexGuardian will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

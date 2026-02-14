<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/arcAman07/TexGuardian/main/docs/assets/logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/arcAman07/TexGuardian/main/docs/assets/logo-light.svg">
    <img alt="TexGuardian" src="https://raw.githubusercontent.com/arcAman07/TexGuardian/main/docs/assets/logo-light.svg" width="480">
  </picture>
</p>

<p align="center">
  <strong>AI-powered terminal assistant for LaTeX academic papers</strong>
</p>

<p align="center">
  <a href="#installation">Installation</a> &middot;
  <a href="#quick-start">Quick Start</a> &middot;
  <a href="#commands">Commands</a> &middot;
  <a href="#configuration">Configuration</a> &middot;
  <a href="docs/GUIDE.md">Guide</a>
</p>

<p align="center">
  <a href="https://pypi.org/project/texguardian/"><img src="https://img.shields.io/pypi/v/texguardian.svg" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-MIT-green.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/LLM-Claude%20Opus%204.5-orange.svg" alt="Claude Opus 4.5">
  <img src="https://img.shields.io/badge/providers-Bedrock%20%7C%20OpenRouter-purple.svg" alt="Bedrock | OpenRouter">
</p>

---

TexGuardian is a **researcher-focused** interactive CLI tool that helps you write, verify, and polish LaTeX academic papers for conference submission. Think of it as **Claude Code, but for LaTeX** — it reads your paper, understands venue requirements, and fixes issues through reviewable diff patches with checkpoint safety.

Whether you're preparing a NeurIPS submission, fixing figure overflows, anonymizing for double-blind review, or validating citations against real databases — TexGuardian handles the tedious parts so you can focus on the research.

## Highlights

- **Styled REPL** — bordered welcome panel with paper stats, colored `❯` prompt
- **26 slash commands** for every stage of paper preparation
- **LLM-powered fixes** — figures, tables, citations, sections, anonymization, camera-ready
- **Instant verification** — regex-based checks run directly on `.tex` files, no compilation needed
- **Unified diff patches** — every edit is reviewable, with checkpoints and rollback
- **Visual polish loop** — renders PDF, sends pages to vision model, fixes layout issues
- **Natural language** — ask for anything in plain English, the LLM figures out the rest
- **Two providers** — AWS Bedrock or OpenRouter, switch with one command

## Installation

### From PyPI (recommended)

```bash
pip install texguardian
```

### From source

```bash
git clone https://github.com/arcAman07/TexGuardian.git
cd TexGuardian
pip install -e ".[dev]"
```

### External tools

TexGuardian needs LaTeX and Poppler installed on your system for compilation and visual checks:

| Tool | Purpose | Install |
|------|---------|---------|
| Python 3.11+ | Runtime | [python.org](https://python.org) |
| LaTeX (latexmk) | Compilation | See below |
| Poppler | PDF rendering for visual checks | `brew install poppler` (macOS) / `apt install poppler-utils` (Ubuntu) |

#### LaTeX installation

**Option A: TinyTeX (~250 MB) — recommended:**

```bash
# macOS / Linux
curl -sL "https://yihui.org/tinytex/install-bin-unix.sh" | sh

# Add to PATH (add to your ~/.zshrc or ~/.bashrc):
export PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$PATH"  # macOS
export PATH="$HOME/.TinyTeX/bin/x86_64-linux:$PATH"             # Linux

# Install common academic packages:
tlmgr install booktabs natbib hyperref pgfplots xcolor float geometry \
              amsmath amssymb graphicx tikz caption subcaption
```

TinyTeX is a minimal, portable TeX Live distribution. Missing packages are auto-installed on first compile, or install manually with `tlmgr install <pkg>`. See [yihui.org/tinytex](https://yihui.org/tinytex/) for details.

**Option B: Full TeX Live (~4 GB)** — includes every package, no missing-package issues:

```bash
# macOS
brew install --cask mactex-no-gui

# Ubuntu/Debian
sudo apt install texlive-full
```

### Verify installation

```bash
texguardian doctor
```

```
TexGuardian Doctor

Checking external tools...

  ✓ latexmk      ~/Library/TinyTeX/bin/universal-darwin/latexmk
  ✓ pdflatex     ~/Library/TinyTeX/bin/universal-darwin/pdflatex
  ✓ pdfinfo      /opt/homebrew/bin/pdfinfo
  ✓ pdftoppm     /opt/homebrew/bin/pdftoppm

All tools found. You're good to go!
```

## Quick Start

### 1. Initialize your project

```bash
cd /path/to/your/latex/paper
texguardian init
```

This creates three files:

| File | Purpose |
|------|---------|
| `texguardian.yaml` | LLM provider, model, safety limits, LaTeX settings |
| `paper_spec.md` | Venue, deadline, thresholds, custom checks, system prompt |
| `.texguardian/` | Runtime data (checkpoints, history) |

### 2. Configure credentials

**AWS Bedrock** (recommended):

```bash
# Create a .env file in your project root:
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

**OpenRouter**:

```yaml
# In texguardian.yaml:
providers:
  default: "openrouter"
  openrouter:
    api_key: "sk-or-..."  # Get from https://openrouter.ai/keys
```

### 3. Start chatting

```bash
texguardian chat
```

On startup you'll see a styled welcome panel with paper stats:

```
╭──────────────────────────────────────────────────────────╮
│  TexGuardian                                             │
│                                                          │
│  Paper  Scaling Sparse MoE for Long-Context Doc...       │
│  Venue  NeurIPS 2026          Deadline  2026-05-15       │
│  Model  claude opus 4.5       Provider  bedrock          │
│  File   demo_paper.tex        Figures 4 · Tables 3       │
│                                                          │
│  Type /help for commands or ask a question.              │
╰──────────────────────────────────────────────────────────╯

❯ _
```

Then interact with commands or plain English:

```
❯ /figures fix
Figure Pipeline

Step 1: Verifying Figures
  Found 4 figures, 3 issues detected

Step 2: LLM Fix
  Analyzing figure issues...

  ✓ Generated 3 patches:
    1. demo_paper.tex (+1/-1) — width=1.3\columnwidth → width=\columnwidth
    2. demo_paper.tex (+1/-1) — width=1.8\textwidth → width=\columnwidth
    3. demo_paper.tex (+1/-1) — width=2.0\columnwidth → width=\columnwidth

  [A]pply all | [R]eview | [N]o: a
  ✓ Checkpoint created
  ✓ All patches applied

❯ The tables use \hline — please fix them to use booktabs
```

## Commands

### Paper Analysis

| Command | Aliases | Description |
|---------|---------|-------------|
| `/verify` | `/v`, `/check` | Run all verification checks (figures, citations, custom rules) |
| `/figures [verify\|fix]` | `/figs`, `/fig` | Verify and fix all figures |
| `/tables [verify\|fix]` | `/tabs`, `/tab` | Verify and fix all tables |
| `/citations [verify\|fix]` | `/cite`, `/refs` | Verify, validate (CrossRef/S2), and fix citations |
| `/section <name> [fix]` | `/sec` | Deep analysis of a specific section |
| `/page_count` | `/pages`, `/pc` | Page count with section breakdown and limit check |
| `/feedback` | — | Comprehensive paper review with scoring |
| `/suggest_refs` | `/suggest_citations` | AI-powered citation recommendations |

### Paper Preparation

| Command | Aliases | Description |
|---------|---------|-------------|
| `/anonymize` | `/anon`, `/blind` | Make paper anonymous for double-blind review |
| `/camera_ready` | `/cr`, `/final` | Convert draft to camera-ready version |
| `/venue <name> [year]` | `/template`, `/conf` | Download conference LaTeX templates |
| `/compile` | `/c`, `/build` | Compile LaTeX document with latexmk |
| `/review` | `/full`, `/pipeline` | Full pipeline: compile -> verify -> fix -> repeat |
| `/polish_visual` | `/pv`, `/visual` | Visual verification with vision model |

### Configuration

| Command | Aliases | Description |
|---------|---------|-------------|
| `/model` | `/m` | Show current model configuration |
| `/model list` | | List all available models |
| `/model set <name>` | | Change the LLM model |
| `/model search <query>` | | Search for models by name |

### File Operations

| Command | Aliases | Description |
|---------|---------|-------------|
| `/read <file>` | `/cat` | Display file contents |
| `/write <file>` | — | Write content to a file |
| `/grep <pattern>` | `/g` | Search for pattern in files |
| `/search <pattern>` | `/find`, `/ls` | Find files by name |
| `/bash <cmd>` | `/sh`, `/!` | Run a shell command |

### Version Control

| Command | Aliases | Description |
|---------|---------|-------------|
| `/diff` | `/d` | Show changes since last checkpoint |
| `/revert` | `/undo`, `/rollback` | Revert to a previous checkpoint |
| `/approve` | `/apply`, `/a` | Apply pending patches |
| `/watch` | `/w` | Toggle auto-recompile on file changes |

### Other

| Command | Aliases | Description |
|---------|---------|-------------|
| `/help` | `/h`, `/?` | Show all available commands |
| `/report` | `/r` | Generate a comprehensive verification report |

### Natural Language

You can also just type in plain English. TexGuardian will understand:

```
❯ The figure on line 44 has width=1.3\columnwidth which causes overflow. Please fix it.
❯ Please make this paper anonymous for double-blind review
❯ Can you suggest more citations for the related work section?
```

The `/venue` and `/model` commands also accept natural language:

```
❯ /venue please download the neurips 2026 style files
❯ /model we need to switch to claude sonnet 4 on bedrock
```

## Configuration

### texguardian.yaml

```yaml
project:
  main_tex: "main.tex"          # Your main .tex file
  output_dir: "build"           # Output directory for PDF

providers:
  default: "bedrock"            # "bedrock" or "openrouter"
  bedrock:
    region: "us-east-1"
    # Credentials loaded from .env automatically
  openrouter:
    api_key: "sk-or-..."
    base_url: "https://openrouter.ai/api/v1"

models:
  default: "claude opus 4.5"    # Main model for analysis and fixes
  vision: "claude opus 4.5"     # Vision model for visual polish

safety:
  max_changed_lines: 50         # Max lines per patch
  max_rounds: 10                # Max auto-fix iterations
  max_visual_rounds: 5          # Max visual verification loops
  allowlist:                    # Files the LLM can modify
    - "*.tex"
    - "*.bib"
    - "*.sty"
    - "*.cls"
  denylist:                     # Files the LLM cannot touch
    - ".git/**"
    - "*.pdf"
    - "build/**"

latex:
  compiler: "latexmk"           # Build tool
  engine: "pdflatex"            # TeX engine
  shell_escape: false           # Enable --shell-escape
  timeout: 240                  # Compilation timeout (seconds)

visual:
  dpi: 150                      # PDF render resolution
  diff_threshold: 5.0           # Convergence threshold (%)
  pixel_threshold: 15           # Per-pixel diff threshold (0-255)
  max_pages_to_analyze: 0       # 0 = all pages
```

### paper_spec.md

The paper spec defines venue-specific rules, custom checks, and your system prompt:

````markdown
---
title: "Your Paper Title"
venue: "NeurIPS 2026"
deadline: "2026-05-15"
thresholds:
  max_pages: 9
  min_references: 30
  max_self_citation_ratio: 0.2
human_review:
  - "Changes to abstract"
  - "Deletion of more than 10 lines"
---

## Custom Checks

```check
name: citation_format
severity: warning
pattern: "\\cite\\{(?!p|t)"
message: "Use \\citep{} or \\citet{} instead of \\cite{}"
```

```check
name: todo_remaining
severity: error
pattern: "TODO|FIXME|XXX"
message: "Remove TODO/FIXME markers before submission"
```

## System Prompt

```system-prompt
You are an expert academic writing assistant specializing in machine learning.
Use formal academic English. Every claim must be backed by evidence.
```
````

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_ACCESS_KEY_ID` | — | AWS access key for Bedrock |
| `AWS_SECRET_ACCESS_KEY` | — | AWS secret key for Bedrock |
| `AWS_REGION` | `us-east-1` | AWS region |
| `TEXGUARDIAN_MAX_CONTEXT_TOKENS` | `100000` | Max conversation context tokens |
| `TEXGUARDIAN_SUMMARY_THRESHOLD` | `80000` | Token threshold for auto-compaction |
| `TEXGUARDIAN_MAX_OUTPUT_TOKENS` | `32000` | Max LLM output tokens |
| `TEXGUARDIAN_MAX_THINKING_TOKENS` | `16000` | Max thinking/reasoning tokens |

## Available Models

### AWS Bedrock

| Friendly Name | Model ID |
|---------------|----------|
| `claude opus 4.5` | `us.anthropic.claude-opus-4-5-20251101-v1:0` |
| `claude opus 4` | `us.anthropic.claude-opus-4-20250514-v1:0` |
| `claude sonnet 4` | `us.anthropic.claude-sonnet-4-20250514-v1:0` |
| `claude-3.7-sonnet` | `us.anthropic.claude-3-7-sonnet-20250219-v1:0` |

### OpenRouter

| Friendly Name | Model ID |
|---------------|----------|
| `claude opus 4.5` | `anthropic/claude-opus-4.5` |
| `claude opus 4` | `anthropic/claude-opus-4` |
| `claude sonnet 4` | `anthropic/claude-sonnet-4` |
| `gpt-4o` | `openai/gpt-4o` |

Plus any model from [openrouter.ai/models](https://openrouter.ai/models).

## Development

```bash
# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=texguardian --cov-report=term-missing

# Lint
ruff check src/

# Type check
mypy src/texguardian
```

See [docs/GUIDE.md](docs/GUIDE.md) for the full architecture and project layout.

## License

MIT License. See [LICENSE](LICENSE) for details.

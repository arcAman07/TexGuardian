# TexGuardian Developer & User Guide

> Comprehensive reference for all commands, features, architecture, and internals.

---

## Table of Contents

1. [Overview](#overview)
2. [Installation](#installation)
3. [Getting Started](#getting-started)
4. [CLI Commands](#cli-commands)
5. [The REPL](#the-repl)
6. [Configuration](#configuration)
7. [Paper Specification](#paper-specification)
8. [LLM Integration](#llm-integration)
9. [Patch System](#patch-system)
10. [Checkpoint & Rollback](#checkpoint--rollback)
11. [Safety System](#safety-system)
12. [Visual Verification](#visual-verification)
13. [Conversation Context](#conversation-context)
14. [Architecture](#architecture)
15. [Adding a New Command](#adding-a-new-command)
16. [Testing](#testing)
17. [Troubleshooting](#troubleshooting)

---

## Overview

TexGuardian is an interactive CLI tool for researchers preparing LaTeX papers for conference submission. It provides 26 slash commands for verification, fixing, analysis, compilation, and submission preparation — all powered by LLMs (Claude via AWS Bedrock or OpenRouter).

**Core philosophy**: Every edit the LLM proposes is shown as a unified diff patch for human review before applying. Checkpoints are created before every modification so you can always roll back.

---

## Installation

### Prerequisites

| Tool | Required | Purpose |
|------|----------|---------|
| Python 3.11+ | Yes | Runtime |
| latexmk | Yes | LaTeX compilation |
| pdflatex/xelatex/lualatex | Yes | TeX engine |
| bibtex/biber | Yes | Bibliography processing |
| pdftoppm (Poppler) | Optional | PDF rendering for `/polish_visual` |

### Install from source

```bash
git clone https://github.com/texguardian/texguardian.git
cd texguardian
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Install from PyPI (when published)

```bash
pip install texguardian
```

### Verify installation

```bash
texguardian doctor
```

This checks that `latexmk`, `pdflatex`, `bibtex`, and `pdftoppm` are found on PATH.

---

## Getting Started

### 1. Initialize a project

```bash
cd /path/to/your/latex/paper
texguardian init
```

This creates three items:

| File | Purpose |
|------|---------|
| `texguardian.yaml` | LLM provider, model, safety limits, LaTeX settings |
| `paper_spec.md` | Venue, deadline, thresholds, custom checks, system prompt |
| `.texguardian/` | Runtime directory (checkpoints, command history) |

### 2. Configure credentials

**AWS Bedrock:**
```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

**OpenRouter:**
Set `providers.openrouter.api_key` in `texguardian.yaml` or:
```bash
export OPENROUTER_API_KEY="sk-or-..."
```

### 3. Start the REPL

```bash
texguardian chat
```

You can also specify a directory or override the model:
```bash
texguardian chat --directory /path/to/paper --model "claude sonnet 4"
```

---

## CLI Commands

TexGuardian has three top-level CLI commands:

| Command | Description |
|---------|-------------|
| `texguardian init` | Initialize a project (creates config files) |
| `texguardian chat` | Start the interactive REPL |
| `texguardian doctor` | Check external tool availability |

All other functionality is accessed through slash commands inside the REPL.

### Paper Analysis Commands

#### `/verify` (aliases: `/v`, `/check`)

Runs all verification checks defined in `paper_spec.md` plus built-in checks (figures, citations).

```
>>> /verify
┌───────────────────┬──────────┬────────┬──────────────────────────────┐
│ Check             │ Severity │ Status │ Message                      │
├───────────────────┼──────────┼────────┼──────────────────────────────┤
│ citations         │ warning  │ PASS   │ 54 citations OK              │
│ figure_overflow   │ error    │ FAIL   │ Figure width exceeds column  │
│ todo_remaining    │ error    │ FAIL   │ Remove TODO/FIXME markers    │
└───────────────────┴──────────┴────────┴──────────────────────────────┘
```

#### `/figures` (aliases: `/figs`, `/fig`)

Unified figure pipeline: verify, fix, analyze.

| Usage | Behavior |
|-------|----------|
| `/figures` | Verify only — list all figures with labels, refs, status |
| `/figures fix` | Verify + auto-fix issues + compile + analyze |
| `/figures analyze` | Verify + AI quality analysis (scoring) |
| `/figures fix all spacing issues` | Custom instruction sent to LLM |
| `/figures reduce width on fig:overview` | Custom instruction |

**Verify step**: Parses all `\begin{figure}...\end{figure}` blocks, checks for:
- Missing `\label{}`
- Missing or short captions
- Unreferenced figures (label defined but never `\ref{}`'d)

**Fix step**: Sends issues + figure code to LLM. LLM generates unified diff patches. You approve via the standard Apply/Review/No flow.

**Analyze step**: LLM scores each figure on clarity, caption quality, necessity, presentation, integration (0-100 each).

#### `/tables` (aliases: `/t`)

Same pipeline as `/figures` but for `\begin{table}...\end{table}` blocks.

| Usage | Behavior |
|-------|----------|
| `/tables` | Verify only |
| `/tables fix` | Auto-fix issues |
| `/tables analyze` | AI quality analysis |
| `/tables fix formatting` | Custom instruction |

#### `/citations` (aliases: `/cite`, `/refs`)

Citation verification and fixing.

| Usage | Behavior |
|-------|----------|
| `/citations` | Verify — finds undefined refs, unused bib entries, format issues |
| `/citations fix` | Auto-fix citation issues |
| `/citations validate` | Validate against CrossRef and Semantic Scholar APIs |

**Checks performed**:
- Undefined `\cite{key}` references (key not in .bib)
- Unused .bib entries (defined but never cited)
- Citation format issues (e.g., `\cite{}` vs `\citep{}`/`\citet{}`)
- Duplicate bib entries

#### `/section <name>` (aliases: `/sec`)

Deep analysis of a specific section.

```
>>> /section introduction
>>> /section related work fix
>>> /section method improve the notation consistency
```

| Usage | Behavior |
|-------|----------|
| `/section <name>` | Analyze section content, structure, writing quality |
| `/section <name> fix` | Auto-fix issues in the section |
| `/section <name> <instruction>` | Custom instruction for the section |

#### `/page_count` (aliases: `/pages`, `/pc`)

Counts pages and shows a section breakdown. Compares against `max_pages` threshold from `paper_spec.md`.

```
>>> /page_count
Total pages: 11 (limit: 9)
  Introduction: ~1.5 pages
  Related Work: ~2.0 pages
  Method: ~3.0 pages
  ...
```

#### `/feedback` (aliases: `/review_full`)

Comprehensive paper review with scoring. The LLM reads your full paper and provides:
- Overall score (0-100)
- Category scores: Structure, Writing, Technical, Citations, Formatting
- Acceptance predictions for the target venue
- Top strengths and weaknesses
- Detailed suggestions

#### `/suggest_refs` (aliases: `/suggest_citations`)

AI-powered citation recommendations. The LLM reads your paper and suggests missing references that would strengthen specific sections.

### Paper Preparation Commands

#### `/anonymize` (aliases: `/anon`, `/blind`)

Makes the paper anonymous for double-blind review.

```
>>> /anonymize
```

Detects and removes:
- Author names, affiliations, emails
- `\thanks{}` acknowledgments
- Self-citations that reveal identity
- Identifying information in headers/footers

Generates patches for review before applying.

#### `/camera_ready` (aliases: `/cr`, `/final`)

Converts a draft to camera-ready format.

```
>>> /camera_ready
```

- Removes anonymization
- Adds proper author block
- Updates formatting for final submission
- Checks page limit compliance

#### `/venue <name> [year]` (aliases: `/templates`, `/style`)

Downloads conference LaTeX template files.

| Usage | Behavior |
|-------|----------|
| `/venue list` | List known venues |
| `/venue neurips 2025` | Direct download (fast path) |
| `/venue please download neurips 2026 style files` | Natural language (LLM path) |

**Known venues**: neurips, icml, iclr, aaai, cvpr, eccv, emnlp, acl, naacl, chi, kdd, www, sigir, uist, ijcai.

When the input is more than 2 simple tokens, the command sends your request to the LLM, which identifies the venue and year, streams an explanation, and proposes a download action with an approval panel.

**Persistence**: Updates `paper_spec.md` venue field after successful download.

#### `/compile` (aliases: `/c`, `/build`)

Compiles the LaTeX document using latexmk.

```
>>> /compile
Compiling demo_paper.tex...
✓ Compilation successful (12 pages)
```

Uses the engine and timeout from `texguardian.yaml`. Stores result in `session.last_compilation`.

#### `/review` (aliases: `/full`, `/pipeline`)

Full pipeline: compile → verify → fix → repeat until clean or max rounds reached.

```
>>> /review
Round 1: Compiling... ✓
Round 1: Verifying... 3 issues
Round 1: Fixing... 2 patches applied
Round 2: Compiling... ✓
Round 2: Verifying... 1 issue
Round 2: Fixing... 1 patch applied
Round 3: Compiling... ✓
Round 3: Verifying... 0 issues
✓ All checks pass
```

Respects `safety.max_rounds` limit and stops on consecutive quality regressions.

#### `/polish_visual` (aliases: `/pv`, `/visual`)

Visual verification loop using a vision model.

```
>>> /polish_visual
```

Pipeline:
1. Compile `.tex` → `.pdf`
2. Render pages to PNG using `pdftoppm`
3. Send page images to vision model (Claude Opus 4.5)
4. Vision model identifies layout issues (overlapping figures, bad spacing, etc.)
5. Generate patches to fix issues
6. Apply patches (with approval)
7. Re-compile and compare pixel diff
8. Repeat until converged or max visual rounds reached

Configuration in `texguardian.yaml`:
```yaml
visual:
  dpi: 150              # Render resolution
  diff_threshold: 5.0   # Convergence threshold (% pixel change)
  pixel_threshold: 15   # Per-pixel intensity threshold (0-255)
  max_pages_to_analyze: 0  # 0 = all pages
```

### Configuration Commands

#### `/model` (aliases: `/m`)

| Usage | Behavior |
|-------|----------|
| `/model` | Show current model and provider |
| `/model list` | List all available models |
| `/model set claude opus 4.5` | Set the model |
| `/model set claude sonnet 4 on bedrock` | Set model and provider |
| `/model search sonnet` | Search models by keyword |
| `/model we need to use claude opus 4.5 on bedrock` | Natural language (LLM path) |

**Persistence**: Saves to `texguardian.yaml` immediately.

**Model resolution**: Friendly names like "claude opus 4.5" are resolved to provider-specific IDs:
- Bedrock: `us.anthropic.claude-opus-4-5-20251101-v1:0`
- OpenRouter: `anthropic/claude-opus-4.5`

### File Operations Commands

#### `/read <file>` (aliases: `/cat`)

Display file contents with syntax highlighting.

```
>>> /read main.tex
>>> /read references.bib
```

#### `/grep <pattern>` (aliases: `/g`)

Search for a regex pattern across project files.

```
>>> /grep \\begin{figure}
>>> /grep TODO|FIXME
```

Respects the allowlist — only searches in `.tex`, `.bib`, `.sty`, `.cls` files.

#### `/search <pattern>` (aliases: `/find`, `/ls`)

Find files by name pattern.

```
>>> /search *.bib
>>> /search figures
```

#### `/bash <cmd>` (aliases: `/sh`, `/!`)

Run an arbitrary shell command.

```
>>> /bash ls -la
>>> /bash wc -l main.tex
```

#### `/write <file>`

Write content to a file (used internally, also available as a command).

### Version Control Commands

#### `/diff` (aliases: `/d`)

Show changes since the last checkpoint.

```
>>> /diff
--- a/main.tex
+++ b/main.tex
@@ -71,1 +71,1 @@
-\includegraphics[width=1.4\columnwidth]{fig.pdf}
+\includegraphics[width=\columnwidth]{fig.pdf}
```

#### `/revert` (aliases: `/undo`, `/rollback`)

Revert to a previous checkpoint.

```
>>> /revert
Checkpoints:
  1. [2025-02-12 14:30] Before patch: main.tex
  2. [2025-02-12 14:25] Before patch: main.tex

Revert to checkpoint [1-2]: 1
✓ Reverted to checkpoint 1
```

#### `/approve` (aliases: `/apply`, `/a`)

Apply pending patches from the most recent LLM response (if patches weren't applied during the response).

#### `/watch` (aliases: `/w`)

Toggle auto-recompilation on file changes. Uses `watchdog` to monitor `.tex` and `.bib` files in the project directory.

```
>>> /watch
Watching for changes... (press Ctrl+C to stop)
  [14:30:12] Detected change: main.tex
  [14:30:12] Compiling...
  [14:30:18] ✓ Compilation successful (9 pages)
  [14:31:05] Detected change: references.bib
  [14:31:05] Compiling...
  [14:31:14] ✓ Compilation successful (9 pages)
```

**Behavior**:
- Watches all `.tex` and `.bib` files in the project root recursively
- Debounces rapid changes (ignores saves within 1 second of each other)
- Runs `latexmk` with the same engine/timeout from `texguardian.yaml`
- Toggle off by running `/watch` again or pressing Ctrl+C

### Other Commands

#### `/help` (aliases: `/h`, `/?`)

Lists all available commands organized by category. Use `/help <command>` for detailed usage of a specific command.

#### `/report` (aliases: `/r`)

Generates a comprehensive Markdown verification report and saves it to `report.md` in the project root.

```
>>> /report
Generating report...

Report contents:
  - Paper metadata (title, venue, deadline)
  - Figure analysis (11 figures, 2 issues)
  - Table analysis (4 tables, 0 issues)
  - Citation analysis (54 citations, 1 uncited)
  - Custom check results (3 checks, 2 failing)
  - Recommendations

✓ Report saved to report.md
```

The report includes all verification results in a format suitable for sharing with co-authors.

### Natural Language

Any input that doesn't start with `/` is sent to the LLM as a chat message. The LLM receives:
- Your message
- The full conversation history (with automatic compaction when it gets large)
- A system prompt built from `paper_spec.md` (including your custom `system-prompt` block)
- Context about your project (main .tex file path, venue, deadline)

If the LLM response contains ` ```diff ` blocks, TexGuardian automatically offers to apply them as patches through the standard Apply/Review/No approval flow.

**Example interactions:**

```
>>> The figure on line 303 causes overflow. Please fix it.
Thinking...
I see the issue — the figure width is set to 1.4\columnwidth which exceeds...

Found 1 patch(es):
  1. main.tex (+1/-1)
[A]pply all | [R]eview | [N]o:

>>> Can you suggest more citations for the related work section?
Based on your related work on efficient transformers, I'd recommend:
1. Kitaev et al. (2020) — Reformer: The Efficient Transformer
2. Zaheer et al. (2020) — BigBird: Transformers for Longer Sequences
...

>>> Please rewrite the abstract to be more concise.
>>> What's our current page count vs the limit?
>>> The notation in Section 3 is inconsistent — can you fix $Q,K,V$ usage?
```

**System prompt construction**: The system prompt is built from:
1. A base prompt identifying TexGuardian as a LaTeX expert
2. Your `paper_spec.md` `system-prompt` block (writing style, domain expertise)
3. Project metadata (venue, paper title, deadline)

---

## The REPL

The interactive REPL (`src/texguardian/cli/repl.py`) provides:

- **prompt-toolkit** integration with readline-style editing
- **Tab completion** for commands and arguments (`TexGuardianCompleter`)
- **Auto-suggest** from command history
- **Persistent history** saved to `.texguardian/history`
- **Special commands**: `exit`/`quit`/`/exit`/`/quit` to leave, `/clear` to clear screen

### REPL Loop

```
User Input
    │
    ├─ /command args ──> CommandRegistry.get_command() → Command.execute()
    │
    └─ natural language ──> _handle_chat()
                                │
                           ConversationContext.add_user_message()
                                │
                           build_chat_system_prompt()
                                │
                           llm_client.stream() → print chunks live
                                │
                           ConversationContext.add_assistant_message()
                                │
                           If "```diff" in response → offer patch application
```

---

## Configuration

### texguardian.yaml

The main configuration file. Created by `texguardian init`.

```yaml
project:
  main_tex: "main.tex"       # Main .tex file to process
  output_dir: "build"        # Output directory for compiled PDF

providers:
  default: "bedrock"         # Active provider: "bedrock" or "openrouter"
  bedrock:
    region: "us-east-1"
    access_key_id: "..."     # Or use AWS_ACCESS_KEY_ID env var
    secret_access_key: "..." # Or use AWS_SECRET_ACCESS_KEY env var
    # profile: "default"     # Alternative: use AWS profile
  openrouter:
    api_key: "sk-or-..."     # Or use OPENROUTER_API_KEY env var
    base_url: "https://openrouter.ai/api/v1"

models:
  default: "claude opus 4.5" # Model for text analysis and fixes
  vision: "claude opus 4.5"  # Model for visual verification

safety:
  max_changed_lines: 50      # Max lines per single patch
  max_rounds: 10             # Max auto-fix iterations (/review)
  max_visual_rounds: 5       # Max visual verification loops
  allowlist:                  # Files the LLM can modify
    - "*.tex"
    - "*.bib"
    - "*.sty"
    - "*.cls"
  denylist:                   # Files the LLM cannot touch
    - ".git/**"
    - "*.pdf"
    - "build/**"

latex:
  compiler: "latexmk"        # Build tool
  engine: "pdflatex"         # TeX engine (pdflatex/xelatex/lualatex)
  shell_escape: false         # Enable --shell-escape
  timeout: 240                # Compilation timeout in seconds

visual:
  dpi: 150                    # PDF render resolution
  diff_threshold: 5.0         # Convergence threshold (%)
  pixel_threshold: 15         # Per-pixel diff threshold (0-255)
  max_pages_to_analyze: 0     # 0 = all pages
```

**Loading**: `TexGuardianConfig.load(path)` in `src/texguardian/config/settings.py`. Uses Pydantic models for validation.

**Finding config**: `find_config_path()` walks up from CWD looking for `texguardian.yaml`.

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AWS_ACCESS_KEY_ID` | — | Bedrock credentials |
| `AWS_SECRET_ACCESS_KEY` | — | Bedrock credentials |
| `AWS_REGION` | `us-east-1` | Bedrock region |
| `OPENROUTER_API_KEY` | — | OpenRouter API key |
| `TEXGUARDIAN_MAX_CONTEXT_TOKENS` | `100000` | Max conversation context tokens |
| `TEXGUARDIAN_SUMMARY_THRESHOLD` | `80000` | Token threshold for auto-compaction |
| `TEXGUARDIAN_MAX_OUTPUT_TOKENS` | `32000` | Max LLM output tokens |
| `TEXGUARDIAN_MAX_THINKING_TOKENS` | `16000` | Max thinking/reasoning tokens |

---

## Paper Specification

### paper_spec.md

Defines venue-specific rules, custom checks, and the system prompt.

```markdown
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

# Paper Specification

```system-prompt
You are an expert ML researcher and LaTeX editor.
Write in formal academic English.
Use \citep{} for parenthetical and \citet{} for textual citations.
```

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
```

### YAML Frontmatter Fields

| Field | Type | Purpose |
|-------|------|---------|
| `title` | string | Paper title (shown in REPL welcome) |
| `venue` | string | Target venue (used in prompts, `/page_count`) |
| `deadline` | string | Submission deadline |
| `thresholds.max_pages` | int | Page limit for `/page_count` |
| `thresholds.min_references` | int | Minimum reference count for `/citations` |
| `thresholds.max_self_citation_ratio` | float | Self-citation limit |
| `human_review` | list[string] | Triggers that require human approval |

### Custom Checks

Defined in ` ```check ` fenced code blocks. Each check has:

| Field | Required | Purpose |
|-------|----------|---------|
| `name` | Yes | Unique identifier |
| `severity` | Yes | `error`, `warning`, or `info` |
| `pattern` | Yes | Regex pattern to search for in .tex files |
| `message` | Yes | Message shown when pattern matches |

Checks are run by `/verify` and `/review`.

### System Prompt

Defined in a ` ```system-prompt ``` ` fenced code block. This prompt is prepended to every LLM interaction in chat mode. Use it to set writing style, domain expertise, LaTeX conventions, etc.

**Parsing**: `PaperSpec.load(path)` in `src/texguardian/config/paper_spec.py`.

---

## LLM Integration

### Provider Architecture

```
src/texguardian/llm/
├── base.py         # LLMClient ABC, CompletionResponse, StreamChunk, ImageContent
├── factory.py      # create_llm_client(config) → LLMClient
├── bedrock.py      # BedrockClient — AWS Bedrock (boto3)
├── openrouter.py   # OpenRouterClient — OpenRouter (httpx)
├── streaming.py    # stream_llm() — shared streaming helper
├── retry.py        # Retry logic with exponential backoff
└── prompts/        # System prompts for each command
    ├── system.py   # build_chat_system_prompt()
    ├── citations.py
    ├── errors.py
    ├── patch.py
    ├── scoring.py
    ├── sections.py
    └── visual.py
```

### LLMClient Interface

Every provider implements this abstract class (`src/texguardian/llm/base.py`):

```python
class LLMClient(ABC):
    max_output_tokens: int = 32000

    async def complete(messages, system, max_tokens, temperature) -> CompletionResponse
    async def stream(messages, system, max_tokens, temperature) -> AsyncIterator[StreamChunk]
    async def complete_with_vision(messages, images, system, ...) -> CompletionResponse
    def supports_vision() -> bool
    async def close() -> None
```

### stream_llm() Helper

All commands use `stream_llm()` from `src/texguardian/llm/streaming.py` instead of calling `client.stream()` directly. This provides:

- Automatic "Thinking..." spinner until first token arrives
- Live printing of tokens to console
- Fallback to `complete()` for clients that don't support streaming
- Consistent return value (full response text)

```python
response_text = await stream_llm(
    session.llm_client,
    messages=[{"role": "user", "content": prompt}],
    console=console,
    system="optional system prompt",
    max_tokens=4000,
    temperature=0.3,
)
```

### Model Resolution

Friendly names → provider-specific model IDs:

| Friendly Name | Bedrock ID | OpenRouter ID |
|---------------|-----------|---------------|
| `claude opus 4.5` | `us.anthropic.claude-opus-4-5-20251101-v1:0` | `anthropic/claude-opus-4.5` |
| `claude opus 4` | `us.anthropic.claude-opus-4-20250514-v1:0` | `anthropic/claude-opus-4` |
| `claude sonnet 4` | `us.anthropic.claude-sonnet-4-20250514-v1:0` | `anthropic/claude-sonnet-4` |
| `claude sonnet 4.5` | `us.anthropic.claude-sonnet-4-5-20250514-v1:0` | `anthropic/claude-sonnet-4.5` |

For OpenRouter, any model ID from openrouter.ai/models can be used directly.

### Retry Logic

`src/texguardian/llm/retry.py` provides exponential backoff with jitter for transient API errors (throttling, network timeouts).

---

## Patch System

### Overview

All LLM-generated edits flow through a unified diff patch system:

```
LLM Response (text) → extract_patches() → list[Patch] → interactive_approval()
                                                              │
                                                    ┌─────────┴──────────┐
                                                    │                    │
                                              [A]pply all         [R]eview
                                                    │                    │
                                              PatchValidator     Show diff
                                              PatchApplier       Per-patch approve
                                              Checkpoint
```

### Patch Parser (`src/texguardian/patch/parser.py`)

**`extract_patches(text)`**: Finds all ` ```diff ``` ` code blocks in LLM output and parses them into `Patch` objects.

**`Patch` dataclass**:
```python
@dataclass
class Patch:
    file_path: str        # Target file (from --- a/filename header)
    hunks: list[Hunk]     # Individual change hunks
    raw_diff: str         # Original diff text

    @property
    def additions(self) -> int    # Lines added
    @property
    def deletions(self) -> int    # Lines removed
    @property
    def lines_changed(self) -> int  # Total changed
```

**`Hunk` dataclass**:
```python
@dataclass
class Hunk:
    old_start: int    # Starting line in original file
    old_count: int    # Number of lines from original
    new_start: int    # Starting line in new file
    new_count: int    # Number of lines in new version
    lines: list[str]  # Lines (prefixed with ' ', '+', or '-')
```

### Patch Validator (`src/texguardian/patch/validator.py`)

Checks before applying:
- Target file exists and is within project root
- File matches allowlist and doesn't match denylist
- Total changed lines ≤ `safety.max_changed_lines`

### Patch Applier (`src/texguardian/patch/applier.py`)

Applies unified diff hunks to the target file. Uses line-number matching with fuzzy offset tolerance.

### Interactive Approval (`src/texguardian/cli/approval.py`)

Two approval flows:

**`interactive_approval(patches, session, console)`** — for diff patches:
- Shows patch summary (file, +/- lines)
- Three options: [A]pply all, [R]eview, [N]o
- Review mode shows syntax-highlighted diff for each patch
- Creates checkpoint before each application

**`action_approval(action_title, details, console)`** — for non-patch actions (downloads, config changes):
- Shows a panel with title and details
- Two options: [A]pprove, [N]o

---

## Checkpoint & Rollback

### CheckpointManager (`src/texguardian/checkpoint/manager.py`)

Stores file snapshots before every edit so you can revert.

**Storage**: `.texguardian/checkpoints/<id>/`
- `metadata.json` — checkpoint ID, description, timestamp, file manifest
- Copies of backed-up files

**Index**: `.texguardian/checkpoints/index.json` — ordered list of all checkpoints.

**API**:
```python
manager = CheckpointManager(guardian_dir)
checkpoint_id = await manager.create("Before patch: main.tex", [Path("main.tex")])
await manager.restore(checkpoint_id)  # Revert
diffs = await manager.diff(checkpoint_id)  # Show what changed
manager.list_checkpoints()  # List recent 20
manager.delete(checkpoint_id)  # Remove checkpoint
```

---

## Safety System

### Allowlist / Denylist (`src/texguardian/safety/allowlist.py`)

File-level access control using glob patterns:
- **Allowlist** (default: `*.tex`, `*.bib`, `*.sty`, `*.cls`): Only these files can be modified
- **Denylist** (default: `.git/**`, `*.pdf`, `build/**`): These files are never modified

### Safety Guards (`src/texguardian/safety/guards.py`)

Runtime checks during auto-fix operations:

| Guard | Purpose |
|-------|---------|
| `check_max_rounds(n)` | Stop after `safety.max_rounds` iterations |
| `check_quality_regression()` | Stop after 2 consecutive quality regressions |
| `check_human_review_required(desc)` | Flag changes matching `human_review` triggers |
| `check_deletion_size(lines)` | Flag large deletions matching triggers |
| `check_all(...)` | Run all guards, aggregate results |

**`SafetyCheckResult`**:
```python
@dataclass
class SafetyCheckResult:
    allowed: bool             # False = hard stop
    reason: str               # Why blocked/flagged
    requires_approval: bool   # True = needs explicit human OK
```

### Max Changed Lines

`PatchValidator` rejects any single patch exceeding `safety.max_changed_lines` (default: 50). This prevents the LLM from rewriting entire files.

---

## Visual Verification

### Pipeline (`src/texguardian/visual/`)

```
.tex → latexmk → .pdf → pdftoppm → .png → Vision LLM → patches
                                      │
                             Pixel diff with previous → converged?
                                      │
                             Loop until stable
```

### Components

| File | Purpose |
|------|---------|
| `renderer.py` | PDF → PNG conversion via `pdftoppm` |
| `verifier.py` | Orchestrates the verify-fix loop |
| `differ.py` | Pixel-level comparison between page renders |

### Pixel Diffing

Compares before/after page renders pixel by pixel:
- `pixel_threshold`: minimum intensity difference to count as changed (0-255)
- `diff_threshold`: percentage of changed pixels to consider pages different
- Convergence: loop stops when diff < threshold

---

## Conversation Context

### ConversationContext (`src/texguardian/core/context.py`)

Manages conversation history with token-aware compaction.

**Token estimation**: ~4 characters per token (rough approximation).

**Compaction strategies**:

1. **Count-based** (synchronous): When `len(messages) > max_messages` (100), drops oldest half and extracts topic keywords as a summary.

2. **Token-based** (synchronous): When total tokens exceed `summary_threshold`, removes oldest messages to reach target.

3. **LLM-based** (async): `summarize_with_llm(client)` — sends oldest messages to the LLM for a proper summary. Higher quality but costs API tokens.

4. **Smart compaction**: `smart_compact(llm_client)` — called automatically when context reaches 70% capacity. Uses LLM if available, falls back to topic extraction.

**Stats**:
```python
stats = context.get_context_stats()
# {message_count, total_tokens, max_tokens, summary_threshold,
#  has_summary, summary_preview, usage_percent}
```

---

## Architecture

### Module Layout

```
src/texguardian/
├── __init__.py
├── __main__.py           # python -m texguardian
├── cli/
│   ├── main.py           # Typer app: init, chat, doctor
│   ├── repl.py           # REPL loop, command dispatch, chat handling
│   ├── approval.py       # Patch approval + action approval
│   ├── completers.py     # Tab completion
│   └── commands/
│       ├── registry.py   # Command ABC + CommandRegistry
│       ├── figures.py    # /figures
│       ├── tables.py     # /tables
│       ├── citations.py  # /citations
│       ├── section.py    # /section
│       ├── venue.py      # /venue
│       ├── model.py      # /model
│       ├── feedback.py   # /feedback
│       ├── anonymize.py  # /anonymize
│       ├── camera_ready.py  # /camera_ready
│       ├── compile.py    # /compile
│       ├── verify.py     # /verify
│       ├── review.py     # /review
│       ├── visual.py     # /polish_visual
│       ├── analysis.py   # /suggest_refs
│       ├── page_count.py # /page_count
│       ├── report.py     # /report
│       ├── file_ops.py   # /read, /grep, /search, /bash, /write
│       ├── diff.py       # /diff
│       ├── revert.py     # /revert
│       ├── approve.py    # /approve
│       ├── watch.py      # /watch
│       └── help.py       # /help
├── config/
│   ├── settings.py       # TexGuardianConfig (Pydantic)
│   └── paper_spec.py     # PaperSpec parser
├── core/
│   ├── session.py        # SessionState dataclass
│   ├── context.py        # ConversationContext
│   └── toolchain.py      # External tool detection, PATH setup
├── llm/
│   ├── base.py           # LLMClient ABC
│   ├── factory.py        # create_llm_client()
│   ├── bedrock.py        # BedrockClient (boto3)
│   ├── openrouter.py     # OpenRouterClient (httpx)
│   ├── streaming.py      # stream_llm()
│   ├── retry.py          # Exponential backoff
│   └── prompts/          # System/command prompts
├── patch/
│   ├── parser.py         # Unified diff parser
│   ├── applier.py        # Patch application
│   └── validator.py      # Safety validation
├── checkpoint/
│   └── manager.py        # Checkpoint CRUD
├── safety/
│   ├── allowlist.py      # File access control
│   └── guards.py         # Runtime safety checks
├── latex/
│   ├── compiler.py       # latexmk wrapper
│   ├── parser.py         # LaTeX document parser
│   └── watcher.py        # File change monitoring
├── citations/
│   └── validator.py      # CrossRef/S2 validation
└── visual/
    ├── renderer.py       # PDF → PNG
    ├── verifier.py       # Visual verification loop
    └── differ.py         # Pixel comparison
```

### Data Flow

```
texguardian chat
    │
    ├── Load texguardian.yaml → TexGuardianConfig
    ├── Load paper_spec.md → PaperSpec
    ├── Create SessionState (project_root, config, paper_spec, context)
    ├── create_llm_client(config) → LLMClient
    ├── CommandRegistry.register_all() → 26 commands
    └── run_repl(session, console)
            │
            ├── User types /command args
            │       → registry.get_command(cmd_name)
            │       → command.execute(session, args, console)
            │
            └── User types natural language
                    → context.add_user_message(text)
                    → build_chat_system_prompt(session)
                    → llm_client.stream(messages, system)
                    → context.add_assistant_message(response)
                    → if ```diff in response: offer patch application
```

### SessionState

Central state object passed to every command:

```python
@dataclass
class SessionState:
    project_root: Path
    config_path: Path
    config: TexGuardianConfig
    paper_spec: PaperSpec | None
    llm_client: LLMClient | None
    context: ConversationContext | None
    checkpoint_manager: CheckpointManager | None
    last_compilation: CompilationResult | None
    watch_enabled: bool
    quality_scores: list[int]
    consecutive_regressions: int

    @property
    def main_tex_path(self) -> Path
    @property
    def output_dir(self) -> Path
    @property
    def guardian_dir(self) -> Path
```

---

## Adding a New Command

1. **Create a file** in `src/texguardian/cli/commands/`:

```python
# src/texguardian/cli/commands/mycommand.py
from texguardian.cli.commands.registry import Command

class MyCommand(Command):
    name = "mycommand"
    description = "Short description for /help"
    aliases = ["mc"]

    async def execute(self, session, args, console):
        console.print("[bold]My Command[/bold]")

        # Parse args
        if args.strip() == "fix":
            await self._fix(session, console)
        else:
            await self._verify(session, console)

    async def _verify(self, session, console):
        # Read paper
        content = session.main_tex_path.read_text()
        # ... do verification ...
        console.print("[green]All good[/green]")

    async def _fix(self, session, console):
        if not session.llm_client:
            console.print("[red]LLM not available[/red]")
            return

        # Build prompt
        prompt = f"Fix issues in {session.main_tex_path.name}..."

        # Stream LLM response
        from texguardian.llm.streaming import stream_llm
        response = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
        )

        # Extract and apply patches
        from texguardian.patch.parser import extract_patches
        from texguardian.cli.approval import interactive_approval
        patches = extract_patches(response)
        if patches:
            await interactive_approval(patches, session, console)

    def get_completions(self, partial):
        return ["fix", "verify"]
```

2. **Register in `registry.py`**:

```python
from texguardian.cli.commands.mycommand import MyCommand
self.register(MyCommand())
```

3. **Add tests** in `tests/unit/test_mycommand.py` or `tests/integration/`.

---

## Testing

### Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Coverage
pytest tests/ --cov=texguardian --cov-report=term-missing

# Skip comprehensive integration tests (slow)
pytest tests/ --ignore=tests/integration/test_all_commands_comprehensive.py -v
```

### Test Structure

```
tests/
├── unit/
│   ├── test_anonymize.py
│   ├── test_camera_ready.py
│   ├── test_citation_validator.py
│   ├── test_config.py
│   ├── test_file_ops.py
│   ├── test_latex_parser.py
│   ├── test_paper_spec.py
│   ├── test_patch_parser.py
│   ├── test_retry.py
│   └── test_safety.py
└── integration/
    ├── test_cli.py
    ├── test_commands_with_errors.py
    └── test_all_commands_comprehensive.py
```

### Writing Tests

Tests use `pytest-asyncio` for async test support. Most commands can be tested with a mock LLM client:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from texguardian.core.session import SessionState
from texguardian.config.settings import TexGuardianConfig

@pytest.fixture
def session(tmp_path):
    config = TexGuardianConfig.load_defaults()
    (tmp_path / "main.tex").write_text("\\documentclass{article}...")
    return SessionState(
        project_root=tmp_path,
        config_path=tmp_path / "texguardian.yaml",
        config=config,
        llm_client=mock_llm_client(),
    )

def mock_llm_client():
    client = AsyncMock()
    client.complete.return_value = MagicMock(content="Response text")
    return client
```

---

## Troubleshooting

### "No texguardian.yaml found"

Run `texguardian init` in your paper directory, or use `texguardian chat -d /path/to/paper`.

### "LLM client not initialized"

Check your credentials:
- **Bedrock**: Verify `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` are set
- **OpenRouter**: Verify `api_key` in `texguardian.yaml` or `OPENROUTER_API_KEY` env var

### "ProfileNotFound" error with Bedrock

This happens when `AWS_PROFILE` env var conflicts with explicit credentials. TexGuardian automatically handles this by unsetting `AWS_PROFILE` when explicit keys are provided. If the issue persists:
```bash
unset AWS_PROFILE
```

### Compilation fails

Run `texguardian doctor` to check if `latexmk` and `pdflatex` are on PATH. For TinyTeX:
```bash
export PATH="$PATH:$HOME/Library/TinyTeX/bin/universal-darwin"
```

### "Max changed lines exceeded"

Increase `safety.max_changed_lines` in `texguardian.yaml` (default: 50).

### Context getting large

TexGuardian automatically compacts conversation context when it reaches 70% capacity. You can also start a fresh session by exiting and re-entering `texguardian chat`.

### Visual verification fails

Ensure `pdftoppm` (part of Poppler) is installed:
```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt install poppler-utils
```

### Patch fails to apply

This usually means the LLM generated line numbers that don't match the current file. Common causes:
- File was modified between the LLM's response and patch application
- LLM hallucinated line numbers (rare with context lines)

**Solutions**:
1. Re-run the command — the LLM will see the current file
2. Use `/read <file>` to show the LLM the current contents, then ask again
3. For persistent issues, try `/section <name> fix` on a specific section rather than the whole file

### Citations show "validate" errors

If `/citations validate` returns HTTP errors, this is usually a rate limit from CrossRef or Semantic Scholar.
- Wait a few seconds and retry
- CrossRef has a polite pool limit of ~50 requests/second
- Semantic Scholar is more restrictive — ~10 requests/second

If you get `ConnectionError`, check your internet connection.

### Checkpoints filling up disk

Checkpoints are stored in `.texguardian/checkpoints/`. Each checkpoint stores copies of modified files. To clean up:
```
>>> /revert
```
Review the list and delete old ones. Or remove the directory entirely:
```bash
rm -rf .texguardian/checkpoints/
```

### Command not found or unrecognized

Ensure you're using the `/` prefix. Common mistakes:
- `verify` (missing slash) — this gets sent to the LLM as a chat message
- `/Verify` (wrong case) — commands are case-sensitive, use lowercase
- `/figs` works (it's an alias) — run `/help` to see all aliases

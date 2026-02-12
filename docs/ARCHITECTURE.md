# TexGuardian Architecture

## Overview

TexGuardian is a terminal-based AI assistant for LaTeX academic papers. It combines a styled REPL interface, an LLM abstraction layer supporting multiple providers, a unified diff patch system with checkpoint safety, and a visual verification pipeline that uses vision models to catch layout issues.

```
src/texguardian/
├── cli/              # REPL, command dispatch, approval workflows
│   └── commands/     # 26 slash command implementations
├── config/           # YAML settings, paper spec parser
├── core/             # Session state, conversation context, toolchain
├── latex/            # LaTeX parser, compiler, file watcher
├── llm/              # LLM client abstraction, providers, streaming
│   └── prompts/      # Domain-specific prompt templates
├── patch/            # Unified diff parser, applier, validator
├── checkpoint/       # Snapshot manager for rollback
├── safety/           # Guards, allowlists, human review triggers
└── visual/           # PDF renderer, pixel differ, verification loop
```

---

## High-Level Flow

```
User Input
    │
    ├─ /command args ──────> CommandRegistry.get_command()
    │                              │
    │                         Command.execute()
    │                              │
    │                    ┌─────────┴──────────┐
    │                    │                    │
    │               Verify Only          LLM Pipeline
    │               (parse .tex,         (build prompt →
    │                run checks)          stream_llm() →
    │                    │                extract patches →
    │                    │                interactive_approval())
    │                    │                    │
    │                    └─────────┬──────────┘
    │                              │
    │                    Show results / Apply patches
    │                    Create checkpoint
    │
    └─ natural language ──> ConversationContext
                                   │
                              build_chat_system_prompt()
                                   │
                              stream_llm()
                                   │
                              Extract patches if any
                              Offer to apply
```

---

## CLI Layer

### Entry Point (`cli/main.py`)

Three top-level Typer commands:

| Command | Purpose |
|---------|---------|
| `texguardian init [dir]` | Create `texguardian.yaml` and `paper_spec.md` from templates |
| `texguardian chat [-d dir] [-m model]` | Start the interactive REPL |
| `texguardian doctor` | Check that `latexmk`, `pdflatex`, `pdfinfo`, `pdftoppm` are installed |

`chat` walks up the directory tree to find `texguardian.yaml`, loads config and paper spec, creates a `SessionState`, and hands off to the REPL.

### REPL (`cli/repl.py`)

Built on `prompt_toolkit` (history, auto-suggest, tab completion) and `rich` (panels, tables, spinners, markup).

```
┌─────────────────────────────────────────────┐
│ Startup                                     │
│   1. create_llm_client(config)              │
│   2. CommandRegistry.register_all()         │
│   3. _print_welcome() with paper stats      │
├─────────────────────────────────────────────┤
│ Main Loop                                   │
│   prompt_session.prompt("❯ ")               │
│       │                                     │
│       ├─ /command → _handle_command()        │
│       │    → registry.get_command(name)      │
│       │    → command.execute(session, args)  │
│       │                                     │
│       └─ text → _handle_chat()              │
│            → context.add_user_message()     │
│            → build_chat_system_prompt()     │
│            → llm_client.stream()            │
│            → context.add_assistant_message() │
│            → _offer_patch_application()     │
├─────────────────────────────────────────────┤
│ Cleanup                                     │
│   llm_client.close()                        │
└─────────────────────────────────────────────┘
```

LLM responses stream token-by-token with a dim `│` left-border prefix on each line, giving a visual container without blocking on the full response.

### Command Registry (`cli/commands/registry.py`)

Abstract base class pattern. Every command subclasses `Command`:

```python
class Command(ABC):
    name: str
    description: str
    aliases: list[str]

    async def execute(self, session: SessionState, args: str, console: Console) -> None: ...
```

`CommandRegistry` maps names and aliases to instances. `register_all()` instantiates all built-in commands. The REPL calls `registry.get_command(name)` to dispatch.

**Registered commands (26):**

| Category | Commands |
|----------|----------|
| Analysis | `verify`, `figures`, `tables`, `citations`, `section`, `page_count`, `feedback`, `suggest_refs` |
| Preparation | `anonymize`, `camera_ready`, `venue`, `compile`, `review`, `polish_visual` |
| Configuration | `model` (show/list/set/search) |
| File operations | `read`, `write`, `grep`, `search`, `bash` |
| Version control | `diff`, `revert`, `approve`, `watch` |
| Other | `help`, `report` |

---

## LLM Abstraction Layer

### Base Client (`llm/base.py`)

```python
class LLMClient(ABC):
    async def complete(messages, system, max_tokens, temperature) -> CompletionResponse
    async def stream(messages, system, max_tokens, temperature) -> AsyncIterator[StreamChunk]
    async def complete_with_vision(messages, images, system, ...) -> CompletionResponse
    def supports_vision() -> bool
    async def close() -> None
```

**Data types:**

| Type | Fields |
|------|--------|
| `CompletionResponse` | content, model, finish_reason, usage |
| `StreamChunk` | content, is_final, finish_reason |
| `ImageContent` | data (bytes), media_type |

### Factory (`llm/factory.py`)

```
User string (e.g. "opus 4.5")
    │
    ├─ resolve_model(input, provider)
    │    → fuzzy match against known model table
    │    → returns ResolvedModel(friendly_name, provider_model_id)
    │
    └─ create_llm_client(config, model_override?)
         → selects provider (bedrock | openrouter)
         → resolves credentials
         → returns LLMClient instance
```

Raw provider IDs (e.g. `us.anthropic.claude-opus-4-5-20251101-v1:0`) pass through without matching.

### Providers

**AWS Bedrock (`llm/bedrock.py`)**
- Uses `boto3` bedrock-runtime
- Cross-region inference for Opus 4/4.5 models
- Configurable `max_output_tokens` (default 32k), `max_thinking_tokens` (16k)
- Credential priority: explicit config keys → AWS profile → environment variables
- 15-minute timeout for vision requests with many pages

**OpenRouter (`llm/openrouter.py`)**
- HTTP client using `httpx`
- Supports Claude, GPT-4o, and any model from openrouter.ai
- In-memory model cache with 5-minute TTL
- Custom headers (referer, title) for analytics

### Streaming Helper (`llm/streaming.py`)

`stream_llm()` — unified helper used by all commands:
1. Calls `client.stream()` with spinner
2. Falls back to `client.complete()` if streaming unsupported
3. Returns the full accumulated content string

### Retry Logic (`llm/retry.py`)

Exponential backoff with jitter:
- Retryable: HTTP 429, 5xx, timeouts, throttling, connection errors
- Default: 3 retries, `2^n` base delay
- Non-retryable exceptions propagate immediately

### Prompt Templates (`llm/prompts/`)

| Module | Purpose |
|--------|---------|
| `system.py` | Build chat system prompt with paper context, venue rules, custom instructions |
| `citations.py` | Citation analysis and validation prompts |
| `errors.py` | LaTeX compilation error parsing |
| `patch.py` | Patch generation instructions |
| `scoring.py` | Paper quality scoring rubric (13 categories) |
| `sections.py` | Section-level analysis |
| `visual.py` | Visual verification prompts for vision models |

---

## LaTeX Processing

### Parser (`latex/parser.py`)

`LatexParser(project_root, main_tex)` — regex-based extraction from `.tex` and `.bib` files.

**Extraction methods:**

| Method | Returns |
|--------|---------|
| `extract_citations()` | Citation keys from `\cite{key}` calls |
| `extract_citations_with_locations()` | Keys with file and line number |
| `extract_bib_keys()` | Keys defined in `.bib` files |
| `extract_figures()` | Figure labels (`fig:*`) |
| `extract_figures_with_details()` | Label, caption, image file, width, source location |
| `extract_tables_with_details()` | Label, caption, content preview, row/column count |
| `extract_figure_refs()` / `extract_table_refs()` | `\ref{fig:*}` / `\ref{tab:*}` references |
| `extract_sections()` | Section names with content (follows `\input`/`\include`) |
| `parse_bibliography()` | Full BibTeX entries as key → fields dict |
| `find_pattern(regex)` | Custom regex matches with file/line/content |

Tracks processed files to avoid infinite recursion on includes. Skips backup files, `.texguardian/`, and build directories.

### Compiler (`latex/compiler.py`)

`LatexCompiler` wraps `latexmk`:

```
latexmk -pdf -pdflatex="pdflatex -interaction=nonstopmode"
        -output-directory=build
        -halt-on-error
        main.tex
```

Returns `CompilationResult` with success flag, PDF path, log output, parsed errors/warnings, and page count (via `pdfinfo`).

### Watcher (`latex/watcher.py`)

Uses `watchdog` to monitor `.tex`/`.bib`/`.sty`/`.cls` files for changes. Triggers recompilation when `watch_enabled` is set on the session.

---

## Patch System

### Parser (`patch/parser.py`)

```
LLM response text
    │
    └─ extract_patches(text) ─────> list[Patch]
         │
         ├─ Search for ```diff code blocks
         ├─ Fall back to raw diff patterns
         └─ De-duplicate normalized diffs
```

**Data types:**

```python
@dataclass
class Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]     # prefixed with ' ', '+', '-'

@dataclass
class Patch:
    file_path: str
    hunks: list[Hunk]
    raw_diff: str

    @property
    def lines_changed(self) -> int    # additions + deletions
    @property
    def additions(self) -> int
    @property
    def deletions(self) -> int
```

### Applier (`patch/applier.py`)

`PatchApplier(project_root)`:

1. **New files**: extracts `+` lines, creates file at target path
2. **Existing files**: applies hunks sequentially with offset tracking
3. **Context verification**: fuzzy matching with a 10-line search window to handle slight line shifts
4. **Line ending normalization**: ensures consistent newlines

### Validator (`patch/validator.py`)

`PatchValidator(safety_config)` enforces safety rules before application:

```
Patch
  │
  ├─ Check allowlist (*.tex, *.bib, *.sty, *.cls)
  ├─ Check denylist (.git/**, *.pdf, build/**)
  ├─ Enforce max_changed_lines limit
  └─ Detect human review triggers:
       • Large deletions (>10 lines)
       • Sensitive patterns (abstract, title, author, maketitle)
```

Returns `ValidationResult` with pass/fail, reason, and whether human review is required.

---

## Checkpoint System (`checkpoint/manager.py`)

`CheckpointManager(guardian_dir)` manages snapshots in `.texguardian/checkpoints/`.

```
Before patch application:
    checkpoint_manager.create(description, files)
        │
        ├─ Copy target files to checkpoints/{id}/
        ├─ Save metadata.json with file manifest
        └─ Update index.json with timestamp + description

On /revert:
    checkpoint_manager.restore(checkpoint_id)
        │
        └─ Copy backup files back to original paths

On /diff:
    checkpoint_manager.diff(checkpoint_id)
        │
        └─ difflib.unified_diff against current files
```

Checkpoint IDs are SHA256 hashes (first 16 chars). Keeps the 20 most recent checkpoints.

---

## Visual Verification Pipeline

The `/polish_visual` command runs an iterative loop that renders the PDF, sends pages to a vision model, and applies fixes until the layout converges.

### Pipeline

```
                          ┌──────────────────────────────┐
                          │     VisualVerifier.run_loop() │
                          └──────────┬───────────────────┘
                                     │
                    ┌────────────────┼────────────────────┐
                    ▼                                     │
            ┌──────────────┐                              │
            │   Compile    │  latexmk → .pdf              │
            │   (LaTeX)    │                              │
            └──────┬───────┘                              │
                   ▼                                      │
            ┌──────────────┐                              │
            │   Render     │  pdftoppm → page-01.png,     │
            │   (Poppler)  │  page-02.png, ...            │
            └──────┬───────┘                              │
                   ▼                                      │
            ┌──────────────┐                              │
            │   Diff       │  Pixel comparison with       │
            │   (NumPy)    │  previous round's images     │
            │              │  → diff_percentage            │
            └──────┬───────┘                              │
                   │                                      │
                   │  diff% < threshold? ──── YES ──> STOP (converged)
                   │                                      │
                   ▼  NO                                  │
            ┌──────────────┐                              │
            │   Analyze    │  Send PNGs to vision model   │
            │   (Vision)   │  → quality_score + issues[]  │
            └──────┬───────┘                              │
                   │                                      │
                   │  No issues? ──────── YES ──────> STOP
                   │                                      │
                   ▼  Has issues                          │
            ┌──────────────┐                              │
            │   Patch      │  Generate & apply fixes      │
            │   (LLM)      │  with checkpoint safety      │
            └──────┬───────┘                              │
                   │                                      │
                   └──── quality regressed 2x? ─── YES ──> STOP
                         │                                │
                         NO                               │
                         └── next round ─────────────────┘
```

### Components

**PDFRenderer (`visual/renderer.py`)**

Wraps `pdftoppm` from Poppler:

```python
renderer = PDFRenderer(dpi=150)
pages = renderer.render(pdf_path, output_dir)
# Returns: [output_dir/page-01.png, output_dir/page-02.png, ...]

count = get_pdf_page_count(pdf_path)
# Uses pdfinfo, parses "Pages:" line
```

**ImageDiffer (`visual/differ.py`)**

Pixel-level comparison using NumPy:

```python
differ = ImageDiffer(threshold=5.0, pixel_threshold=15)
result = differ.compare(img1_path, img2_path, output_path)
# Returns: DiffResult(diff_percentage, diff_image_path, changed_regions)
```

1. Load images, convert to RGB, resize to match
2. Compute per-pixel absolute difference
3. Count pixels where any channel differs by more than `pixel_threshold` (0-255)
4. Calculate `diff_percentage` = changed pixels / total pixels * 100
5. Find bounding boxes of changed regions (scipy.ndimage.label if available)
6. Generate red overlay image for visual inspection

**VisualVerifier (`visual/verifier.py`)**

Orchestrates the full loop:

```python
verifier = VisualVerifier(session)
result = await verifier.run_loop(max_rounds=5, console=console)
# Returns: VisualVerificationResult
#   rounds, quality_score, patches_applied, remaining_issues, stopped_reason
```

**Stop conditions:**
1. Converged — `diff_percentage < diff_threshold` (default 5.0%)
2. No substantive issues found by vision model
3. Quality regressed 2 consecutive rounds
4. Max rounds reached (default 5)

**Image analysis** sends rendered PNGs to the vision model with a structured prompt requesting JSON:

```json
{
  "quality_score": 85,
  "issues": [
    {
      "page": 1,
      "location": "Figure 3",
      "severity": "error",
      "category": "overflow",
      "description": "Figure extends beyond column margin",
      "suggested_fix": "Reduce width to \\columnwidth",
      "patch": "--- a/main.tex\n+++ b/main.tex\n..."
    }
  ]
}
```

This catches layout problems that text-only analysis misses: overlapping figures, bad spacing, misaligned columns, orphaned headers, font size inconsistencies.

---

## Safety Layer

### Guards (`safety/guards.py`)

`SafetyGuards(session)` provides runtime safety checks:

| Check | Behavior |
|-------|----------|
| `check_max_rounds(n)` | Stops auto-fix loops after `safety.max_rounds` iterations |
| `check_quality_regression()` | Stops if quality score drops 2 consecutive rounds |
| `check_human_review_required(desc)` | Flags changes matching `paper_spec.human_review` patterns |
| `check_deletion_size(n)` | Flags deletions exceeding threshold |

### Allowlist (`safety/allowlist.py`)

File-level access control defined in `texguardian.yaml`:

```yaml
safety:
  allowlist: ["*.tex", "*.bib", "*.sty", "*.cls"]
  denylist: [".git/**", "*.pdf", "build/**"]
  max_changed_lines: 50
```

Every patch is validated against these rules before application.

---

## Configuration

### `texguardian.yaml` (`config/settings.py`)

Pydantic models with YAML loading and `${ENV_VAR}` expansion:

```
TexGuardianConfig
├── project: ProjectConfig
│     main_tex, output_dir
├── providers: ProvidersConfig
│     default, bedrock: BedrockConfig, openrouter: OpenRouterConfig
├── models: ModelsConfig
│     default, vision
├── safety: SafetyConfig
│     max_changed_lines, max_rounds, max_visual_rounds, allowlist, denylist
├── latex: LatexConfig
│     compiler, engine, shell_escape, timeout
└── visual: VisualConfig
      dpi, diff_threshold, pixel_threshold, max_pages_to_analyze
```

### `paper_spec.md` (`config/paper_spec.py`)

Markdown file with YAML frontmatter and fenced code blocks:

```
PaperSpec
├── title, venue, deadline         (from YAML frontmatter)
├── thresholds: Thresholds
│     max_pages, min_references, max_self_citation_ratio
├── human_review: list[str]        (change descriptions requiring approval)
├── checks: list[Check]            (from ```check blocks)
│     name, severity, pattern (regex), message
└── system_prompt: str             (from ```system-prompt block)
```

---

## Conversation Context (`core/context.py`)

Token-aware conversation history with automatic compaction:

```
Messages: [user, assistant, user, assistant, ...]
    │
    ├─ Token estimation: ~4 chars per token
    ├─ Hard limit: 100 messages
    ├─ Soft limit: summary_threshold (default 80k tokens)
    │
    └─ Compaction strategies:
         ├─ By count: keep newest 50%, summarize old via topic extraction
         ├─ By tokens: LLM-powered summarization of oldest messages
         └─ smart_compact(): uses LLM if available, falls back to topics
```

Summaries are injected into the system prompt so the LLM retains awareness of earlier conversation.

---

## Session State (`core/session.py`)

`SessionState` is the single dataclass holding all runtime state, passed to every command:

```python
@dataclass
class SessionState:
    # Paths
    project_root: Path
    config_path: Path

    # Configuration
    config: TexGuardianConfig
    paper_spec: PaperSpec | None

    # Runtime
    llm_client: LLMClient | None
    context: ConversationContext | None
    checkpoint_manager: CheckpointManager | None

    # Compilation
    last_compilation: CompilationResult | None

    # Monitoring
    watch_enabled: bool
    quality_scores: list[int]
    consecutive_regressions: int
```

**Properties:** `last_pdf_path`, `main_tex_path`, `output_dir`, `guardian_dir`

**Quality tracking:** `track_quality(score)` appends and detects regressions. `should_stop_auto_fix()` returns `True` after 2 consecutive drops.

---

## Toolchain Discovery (`core/toolchain.py`)

Finds external binaries across platform-specific paths:

| Category | Search paths |
|----------|-------------|
| LaTeX | MacTeX symlinks, TeX Live year-versioned dirs, TinyTeX, system `$PATH` |
| Poppler | Homebrew (`/opt/homebrew`, `/usr/local`), system `$PATH` |

`ensure_latex_on_path()` adds discovered paths to `$PATH` at startup so `latexmk` and `pdflatex` work from the REPL.

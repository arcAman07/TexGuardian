# Project Structure

```
src/texguardian/
├── cli/
│   ├── main.py              # CLI entry point (init, chat, doctor)
│   ├── repl.py              # Interactive REPL with styled prompt, auto-verify
│   ├── approval.py          # Patch and action approval UI
│   ├── completers.py        # Tab completion for commands
│   └── commands/
│       ├── registry.py      # Command base class and registry
│       ├── verify.py         # /verify — run all checks + reusable verify logic
│       ├── figures.py        # /figures — verify and fix figures
│       ├── tables.py         # /tables — verify and fix tables
│       ├── citations.py      # /citations — verify and fix citations
│       ├── section.py        # /section — section analysis
│       ├── venue.py          # /venue — conference templates
│       ├── model.py          # /model — model configuration
│       ├── feedback.py       # /feedback — paper review scoring
│       ├── anonymize.py      # /anonymize — double-blind prep
│       ├── camera_ready.py   # /camera_ready — final submission prep
│       ├── compile.py        # /compile — LaTeX compilation
│       ├── review.py         # /review — full fix pipeline
│       ├── visual.py         # /polish_visual — vision-based fixes
│       ├── analysis.py       # /suggest_refs — citation suggestions
│       ├── page_count.py     # /page_count — page analysis
│       ├── report.py         # /report — verification report
│       ├── file_ops.py       # /read, /write, /grep, /search, /bash
│       ├── diff.py           # /diff — show changes
│       ├── revert.py         # /revert — rollback
│       ├── approve.py        # /approve — apply patches
│       ├── watch.py          # /watch — auto-recompile
│       └── help.py           # /help — command listing
├── config/
│   ├── settings.py           # YAML config loading (texguardian.yaml)
│   └── paper_spec.py         # Paper spec parsing (paper_spec.md)
├── core/
│   ├── session.py            # Session state management
│   ├── context.py            # Conversation context with LLM compaction
│   └── toolchain.py          # External tool detection (latexmk, poppler)
├── latex/
│   ├── parser.py             # LaTeX document parser (citations, figures, tables)
│   ├── compiler.py           # LaTeX compilation with latexmk
│   └── watcher.py            # File watcher for auto-recompile
├── llm/
│   ├── base.py               # Abstract LLM client interface
│   ├── factory.py            # Client factory with model resolution
│   ├── bedrock.py            # AWS Bedrock client (Claude)
│   ├── openrouter.py         # OpenRouter client (multi-provider)
│   ├── streaming.py          # Streaming output handler
│   ├── retry.py              # Retry logic with exponential backoff
│   └── prompts/
│       ├── system.py         # System prompt builder
│       ├── citations.py      # Citation fix prompts
│       ├── errors.py         # Error resolution prompts
│       ├── patch.py          # Patch generation prompts
│       ├── scoring.py        # Quality scoring prompts
│       ├── sections.py       # Section analysis prompts
│       └── visual.py         # Visual verification prompts
├── patch/
│   ├── parser.py             # Unified diff parser
│   ├── applier.py            # Patch application engine
│   └── validator.py          # Safety validation
├── citations/
│   └── validator.py          # CrossRef/Semantic Scholar validation
├── checkpoint/
│   └── manager.py            # Checkpoint creation and restore
├── safety/
│   ├── allowlist.py          # File allowlist/denylist matching
│   └── guards.py             # Safety guard orchestration
└── visual/
    ├── renderer.py           # PDF to PNG rendering (pdftoppm)
    ├── differ.py             # Pixel-level page diffing
    └── verifier.py           # Visual verification loop
```

## Test Structure

```
tests/
├── unit/
│   ├── test_anonymize.py           # Anonymization command tests
│   ├── test_camera_ready.py        # Camera-ready conversion tests
│   ├── test_citation_validator.py  # Citation validation tests
│   ├── test_config.py              # Config loading tests
│   ├── test_file_ops.py            # File operation command tests
│   ├── test_latex_parser.py        # LaTeX parser tests
│   ├── test_paper_spec.py          # Paper spec parsing tests
│   ├── test_patch_parser.py        # Diff patch parser tests
│   ├── test_retry.py               # Retry logic tests
│   └── test_safety.py              # Safety guard tests
└── integration/
    ├── test_cli.py                 # CLI init/chat/doctor tests
    └── test_commands_with_errors.py # End-to-end command tests with error papers
```

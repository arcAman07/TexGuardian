# Contributing to TexGuardian

Thank you for your interest in contributing to TexGuardian.

## Development Setup

```bash
git clone https://github.com/texguardian/texguardian.git
cd texguardian
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
# All tests
pytest tests/ -v

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v

# With coverage
pytest tests/ --cov=texguardian --cov-report=term-missing
```

## Code Quality

```bash
# Lint
ruff check src/

# Auto-fix lint issues
ruff check src/ --fix

# Type check
mypy src/texguardian
```

## Project Structure

```
src/texguardian/
├── cli/              # CLI entry point, REPL, commands
│   ├── main.py       # Typer app (init, chat, doctor)
│   ├── repl.py       # Interactive REPL loop
│   ├── approval.py   # Patch and action approval UI
│   └── commands/     # 24 command files
├── config/           # YAML config and paper spec parsing
├── core/             # Session state, conversation context, toolchain
├── llm/              # LLM clients (Bedrock, OpenRouter), streaming, prompts
├── patch/            # Unified diff parser, applier, validator
├── checkpoint/       # Checkpoint creation and rollback
├── safety/           # Allowlist, guards, deletion limits
├── latex/            # LaTeX compilation, parsing, file watching
├── citations/        # Citation validation (CrossRef, Semantic Scholar)
└── visual/           # PDF rendering, pixel diffing, visual verification
```

## Adding a New Command

1. Create a file in `src/texguardian/cli/commands/` (e.g., `mycommand.py`)
2. Define a class extending `Command`:

```python
from texguardian.cli.commands.registry import Command

class MyCommand(Command):
    name = "mycommand"
    description = "Short description shown in /help"
    aliases = ["mc", "my"]

    async def execute(self, session, args, console):
        # Implementation here
        pass
```

3. Register it in `registry.py`:

```python
from texguardian.cli.commands.mycommand import MyCommand
self.register(MyCommand())
```

## Commit Messages

Use conventional-style messages:

- `feat: add new /mycommand for X`
- `fix: handle edge case in patch parser`
- `docs: update README installation section`
- `test: add unit tests for citation validator`

## Pull Requests

1. Create a feature branch from `main`
2. Make focused, small changes
3. Add tests for new functionality
4. Ensure `pytest tests/ -v` passes
5. Ensure `ruff check src/` has no errors
6. Open a PR with a clear description

## Reporting Issues

Open an issue on GitHub with:

- Steps to reproduce
- Expected behavior
- Actual behavior
- Python version, OS, and TexGuardian version (`texguardian --version`)

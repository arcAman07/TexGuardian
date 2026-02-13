# Local Testing Guide

How to install, test, and run TexGuardian locally.

## Quick Setup

```bash
# Clone and install
git clone https://github.com/texguardian/texguardian.git
cd texguardian
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Verify installation
texguardian doctor
```

## Prerequisites

| Tool | Purpose | Install (macOS) | Install (Ubuntu) |
|------|---------|-----------------|------------------|
| Python 3.11+ | Runtime | `brew install python@3.11` | `apt install python3.11` |
| latexmk + pdflatex | LaTeX compilation | See LaTeX options below | See LaTeX options below |
| pdftoppm (poppler) | PDF rendering for `/polish_visual` | `brew install poppler` | `apt install poppler-utils` |

### LaTeX Installation Options

#### Option A: TinyTeX (~250 MB) — recommended

[TinyTeX](https://yihui.org/tinytex/) is a minimal, portable TeX Live distribution. It includes `latexmk`, `pdflatex`, and a small set of core packages. Missing packages are auto-installed on first compile, or you can install them manually with `tlmgr`. TexGuardian discovers TinyTeX automatically.

```bash
# Install TinyTeX (macOS / Linux)
curl -sL "https://yihui.org/tinytex/install-bin-unix.sh" | sh

# Add to PATH — put this in your ~/.zshrc or ~/.bashrc:
export PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$PATH"  # macOS
export PATH="$HOME/.TinyTeX/bin/x86_64-linux:$PATH"             # Linux

# Verify
latexmk --version
pdflatex --version

# Install common packages used by academic papers:
tlmgr install booktabs natbib hyperref pgfplots xcolor float geometry \
              amsmath amssymb graphicx tikz caption subcaption

# Update all packages:
tlmgr update --all
```

TinyTeX is a good choice for:
- CI/CD pipelines (fast install, small footprint)
- Machines where you don't want a 4 GB TeX Live install
- Docker containers
- Quick setup on a new machine

If you hit a "missing .sty" error during compilation, install the package:

```bash
tlmgr install <package-name>
# Example: tlmgr install algorithm2e
```

#### Option B: Full TeX Live (~4 GB)

The full distribution includes every LaTeX package. You'll never hit a missing-package error.

```bash
# macOS
brew install --cask mactex-no-gui

# Ubuntu/Debian
sudo apt install texlive-full

# Verify
latexmk --version
pdflatex --version
```

## Configure Credentials

### AWS Bedrock (recommended)

```bash
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

Or create a `.env` file in your paper directory:

```
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

### OpenRouter

```bash
# In texguardian.yaml:
providers:
  default: "openrouter"
  openrouter:
    api_key: "sk-or-..."  # Get from https://openrouter.ai/keys
```

## Test with Example Papers

```bash
# Use the included example paper
cd examples/esolang_paper
texguardian chat

# Try these commands:
>>> /verify
>>> /figures verify
>>> /citations verify
>>> /feedback
>>> /page_count
```

## Run the Test Suite

```bash
# All tests (unit + integration)
pytest tests/ -v --ignore=tests/integration/test_all_commands_comprehensive.py

# Unit tests only
pytest tests/unit/ -v

# Integration tests only
pytest tests/integration/ -v --ignore=tests/integration/test_all_commands_comprehensive.py

# With coverage
pytest tests/ --cov=texguardian --cov-report=term-missing

# Lint
ruff check src/

# Type check
mypy src/texguardian --ignore-missing-imports
```

## View the Website Locally

```bash
# Option 1: Python built-in server
cd docs/
python -m http.server 8000
# Open http://localhost:8000

# Option 2: Just open the file
open docs/index.html        # macOS
xdg-open docs/index.html    # Linux
```

## Build the Package

```bash
# Install build tool
pip install build

# Build sdist and wheel
python -m build

# Check what's in the wheel
unzip -l dist/texguardian-0.2.1-py3-none-any.whl | head -30

# Test install from wheel in a clean venv
python -m venv /tmp/test-install
source /tmp/test-install/bin/activate
pip install dist/texguardian-0.2.1-py3-none-any.whl
texguardian --help
texguardian doctor
deactivate
rm -rf /tmp/test-install
```

## Initialize Your Own Paper

```bash
cd /path/to/your/latex/paper
texguardian init

# This creates:
#   texguardian.yaml   - LLM provider, model, safety limits
#   paper_spec.md      - Venue rules, custom checks, system prompt
#   .texguardian/      - Runtime data (checkpoints, history)

# Edit texguardian.yaml:
#   1. Set main_tex to your .tex file name
#   2. Configure your provider credentials

# Edit paper_spec.md:
#   1. Set title, venue, deadline
#   2. Customize the system prompt for your domain
#   3. Add custom checks (regex patterns)

texguardian chat
```

## End-to-End Workflow

Here's a typical session:

```bash
cd /path/to/your/paper
texguardian chat

>>> /verify                    # Run all checks
>>> /figures fix               # Fix figure issues
>>> /citations validate        # Validate against CrossRef/S2
>>> /citations fix             # Fix citation issues
>>> /section Introduction fix  # Improve introduction
>>> /compile                   # Build PDF
>>> /polish_visual             # Visual quality check
>>> /feedback                  # Get overall score
>>> /anonymize                 # Prepare for double-blind
>>> /camera_ready              # Final submission prep
```

## Troubleshooting

### `texguardian: command not found`

```bash
# Make sure your venv is activated
source .venv/bin/activate
# Or install globally
pip install -e .
```

### `latexmk not found`

```bash
# macOS
brew install --cask mactex-no-gui
# Or use TinyTeX (see above)

# Check
texguardian doctor
```

### `LLM client not initialized`

Check your credentials:

```bash
# Bedrock
echo $AWS_ACCESS_KEY_ID
echo $AWS_SECRET_ACCESS_KEY

# OpenRouter: check api_key in texguardian.yaml
```

### `Compilation failed`

```bash
# Try compiling manually first
latexmk -pdf -interaction=nonstopmode your_paper.tex

# Check the log
cat build/your_paper.log | tail -50
```

### Tests failing

```bash
# Make sure dev dependencies are installed
pip install -e ".[dev]"

# Run with verbose output
pytest tests/unit/ -v --tb=long
```

"""Main CLI entry point using Typer."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import typer
from rich.console import Console


def _load_env():
    """Load environment variables from .env file and fix PATH for LaTeX."""
    # Try to find .env in current directory or parent directories
    env_paths = [
        Path.cwd() / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",  # TeXGuardian root
    ]

    loaded_keys = set()
    for env_path in env_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        os.environ[key] = value
                        loaded_keys.add(key)
            break

    # Unset AWS_PROFILE if explicit credentials provided (prevents boto3 conflicts)
    if "AWS_ACCESS_KEY_ID" in os.environ and "AWS_SECRET_ACCESS_KEY" in os.environ:
        os.environ.pop("AWS_PROFILE", None)

    # Add discovered LaTeX directories to PATH
    from texguardian.core.toolchain import ensure_latex_on_path
    ensure_latex_on_path()


# Load .env at import time
_load_env()

from texguardian.config.paper_spec import PaperSpec
from texguardian.config.settings import (
    CONFIG_FILENAME,
    GUARDIAN_DIR,
    SPEC_FILENAME,
    TexGuardianConfig,
    find_config_path,
    get_project_root,
)
from texguardian.core.context import ConversationContext
from texguardian.core.session import SessionState

app = typer.Typer(
    name="texguardian",
    help="Claude Code-style terminal chat for LaTeX papers",
    no_args_is_help=True,
)
console = Console(highlight=False)


@app.command()
def init(
    directory: Path = typer.Argument(
        Path("."),
        help="Directory to initialize (default: current directory)",
    ),
    provider: str = typer.Option(
        None,
        "--provider",
        "-p",
        help="LLM provider: 'bedrock' (AWS) or 'openrouter'",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing config files",
    ),
) -> None:
    """Initialize TexGuardian in a LaTeX project directory."""
    directory = directory.resolve()

    if not directory.exists():
        console.print(f"[red]Directory does not exist: {directory}[/red]")
        raise typer.Exit(1)

    # Resolve provider choice
    if provider is None:
        provider = _prompt_provider()
    else:
        provider = provider.lower().strip()
        if provider not in ("bedrock", "openrouter"):
            console.print(f"[red]Unknown provider: {provider}. Use 'bedrock' or 'openrouter'.[/red]")
            raise typer.Exit(1)

    # Create config file
    config_path = directory / CONFIG_FILENAME
    config_created = False
    if config_path.exists() and not force:
        console.print(f"[yellow]{CONFIG_FILENAME} already exists. Use --force to overwrite.[/yellow]")
    else:
        _create_config_template(config_path, provider)
        config_created = True

    # Create paper spec
    spec_path = directory / SPEC_FILENAME
    spec_created = False
    if spec_path.exists() and not force:
        console.print(f"[yellow]{SPEC_FILENAME} already exists. Use --force to overwrite.[/yellow]")
    else:
        _create_spec_template(spec_path)
        spec_created = True

    # Create .texguardian directory
    guardian_dir = directory / GUARDIAN_DIR
    guardian_created = False
    if not guardian_dir.exists():
        guardian_dir.mkdir()
        guardian_created = True

    # Print summary of created files
    console.print("\n[bold]Files created:[/bold]")
    if config_created:
        console.print(f"  [green]+[/green] {CONFIG_FILENAME}        — LLM provider, model, safety, and LaTeX settings")
    if spec_created:
        console.print(f"  [green]+[/green] {SPEC_FILENAME}          — paper rules, custom checks, and your system prompt")
    if guardian_created:
        console.print(f"  [green]+[/green] {GUARDIAN_DIR}/           — runtime data (checkpoints, history)")
    if not (config_created or spec_created or guardian_created):
        console.print("  [dim]No new files created (all exist already)[/dim]")

    # Print setup instructions
    console.print("\n[bold]Setup:[/bold]")

    step = 1
    console.print(f"  {step}. [cyan]{CONFIG_FILENAME}[/cyan] — set [bold]main_tex[/bold] to your .tex file")
    step += 1

    if provider == "bedrock":
        console.print(f"  {step}. [cyan]{CONFIG_FILENAME}[/cyan] — verify your AWS credentials under [bold]providers.bedrock[/bold]")
    else:
        console.print(f"  {step}. [cyan]{CONFIG_FILENAME}[/cyan] — add your OpenRouter API key under [bold]providers.openrouter.api_key[/bold]")
        console.print("     Get your key at: [link]https://openrouter.ai/keys[/link]")
    step += 1

    console.print(f"  {step}. [cyan]{SPEC_FILENAME}[/cyan] — set your [bold]title[/bold], [bold]venue[/bold], and [bold]deadline[/bold]")
    step += 1

    console.print(f"  {step}. [cyan]{SPEC_FILENAME}[/cyan] — paste your custom [bold]system prompt[/bold] in the ```system-prompt``` block")
    console.print("     This tells the AI how you want it to help with your paper")
    step += 1

    console.print(f"\n  [bold green]{step}. Run [cyan]texguardian chat[/cyan] to start[/bold green]")

    # Check toolchain
    from texguardian.core.toolchain import check_toolchain, get_install_hint
    tc = check_toolchain()
    if tc.missing:
        console.print("\n[yellow]Warning: some external tools are missing:[/yellow]")
        for tool in tc.missing:
            console.print(f"  [red]✗[/red] {tool.name} — {get_install_hint(tool.name)}")
        console.print("\n  Run [cyan]texguardian doctor[/cyan] for full status.")


@app.command()
def chat(
    directory: Path = typer.Option(
        None,
        "--directory",
        "-d",
        help="Project directory (default: find texguardian.yaml in parent directories)",
    ),
    model: str = typer.Option(
        None,
        "--model",
        "-m",
        help="Override default model",
    ),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        "-q",
        help="Suppress LLM streaming output, show only final results",
    ),
) -> None:
    """Start interactive chat session for your LaTeX paper."""
    # Find config
    if directory:
        config_path = directory.resolve() / CONFIG_FILENAME
        if not config_path.exists():
            console.print(f"[red]No {CONFIG_FILENAME} found in {directory}[/red]")
            console.print("Run [cyan]texguardian init[/cyan] first")
            raise typer.Exit(1)
    else:
        config_path = find_config_path()
        if not config_path:
            console.print(f"[red]No {CONFIG_FILENAME} found in current or parent directories[/red]")
            console.print("Run [cyan]texguardian init[/cyan] first")
            raise typer.Exit(1)

    # Load config
    config = TexGuardianConfig.load(config_path)
    project_root = get_project_root(config_path)

    # Override model if specified
    if model:
        config.models.default = model

    # Load paper spec
    spec_path = project_root / SPEC_FILENAME
    paper_spec = PaperSpec.load(spec_path) if spec_path.exists() else None

    # Create session
    session = SessionState(
        project_root=project_root,
        config_path=config_path,
        config=config,
        paper_spec=paper_spec,
        context=ConversationContext(),
        quiet=quiet,
    )

    # Warn about missing external tools before entering the REPL
    from texguardian.core.toolchain import check_toolchain, get_install_hint
    tc = check_toolchain()
    if tc.missing:
        console.print("[yellow]Warning: some external tools are missing:[/yellow]")
        for tool in tc.missing:
            console.print(f"  [red]✗[/red] {tool.name} — {get_install_hint(tool.name)}")
        console.print("  Run [cyan]texguardian doctor[/cyan] for details.\n")

    # Start REPL
    from texguardian.cli.repl import run_repl

    asyncio.run(run_repl(session, console))


@app.command()
def doctor() -> None:
    """Check external tool availability and display status."""
    from texguardian.core.toolchain import check_toolchain, get_install_hint

    console.print("[bold]TexGuardian Doctor[/bold]\n")
    console.print("Checking external tools...\n")

    tc = check_toolchain()

    for tool in tc.tools:
        if tool.found:
            console.print(f"  [green]✓[/green] {tool.name:12s} {tool.path}")
        else:
            console.print(f"  [red]✗[/red] {tool.name:12s} not found")

    console.print()

    if tc.all_found:
        console.print("[green]All tools found. You're good to go![/green]")
    else:
        console.print("[yellow]Missing tools:[/yellow]")
        for tool in tc.missing:
            console.print(f"  • {get_install_hint(tool.name)}")


def _prompt_provider() -> str:
    """Interactively ask the user which provider to use."""
    console.print("\n[bold]Choose your LLM provider:[/bold]")
    console.print("  [cyan]1[/cyan]. AWS Bedrock (uses AWS credentials)")
    console.print("  [cyan]2[/cyan]. OpenRouter (uses API key)")
    console.print()
    try:
        import sys
        sys.stdout.flush()
        choice = input("Provider [1/2]: ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Defaulting to bedrock[/dim]")
        return "bedrock"

    if choice in ("2", "openrouter"):
        return "openrouter"
    return "bedrock"


def _create_config_template(path: Path, provider: str = "bedrock") -> None:
    """Create texguardian.yaml template based on provider choice."""
    aws_key = os.environ.get("AWS_ACCESS_KEY_ID", "YOUR_AWS_ACCESS_KEY_ID")
    aws_secret = os.environ.get("AWS_SECRET_ACCESS_KEY", "YOUR_AWS_SECRET_ACCESS_KEY")

    if provider == "openrouter":
        provider_block = """\
providers:
  default: "openrouter"
  openrouter:
    api_key: "YOUR_OPENROUTER_API_KEY"  # Get from https://openrouter.ai/keys
    base_url: "https://openrouter.ai/api/v1"
"""
    else:
        provider_block = f"""\
providers:
  default: "bedrock"
  bedrock:
    region: "us-east-1"
    access_key_id: "{aws_key}"
    secret_access_key: "{aws_secret}"
    # profile: "default"  # Alternative: use AWS profile from ~/.aws/credentials
"""

    template = f"""\
# TexGuardian Configuration

project:
  main_tex: "main.tex"  # Change this to your main .tex file
  output_dir: "build"

{provider_block}
models:
  default: "claude opus 4.5"
  vision: "claude opus 4.5"

safety:
  max_changed_lines: 50
  max_rounds: 10
  max_visual_rounds: 5
  allowlist:
    - "*.tex"
    - "*.bib"
    - "*.sty"
    - "*.cls"
  denylist:
    - ".git/**"
    - "*.pdf"
    - "build/**"

latex:
  compiler: "latexmk"
  engine: "pdflatex"
  # shell_escape: true  # Enable --shell-escape for minted, svg, etc.
  # timeout: 240        # Compilation timeout in seconds

visual:
  dpi: 150
  diff_threshold: 5.0
  pixel_threshold: 15       # Per-pixel intensity difference (0-255)
  max_pages_to_analyze: 0   # 0 = analyze all pages
"""
    path.write_text(template)


def _create_spec_template(path: Path) -> None:
    """Create paper_spec.md template."""
    template = """\
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

This file defines custom checks and rules for your paper.

## System Prompt

This prompt is prepended to every chat interaction. Customize it to match your
paper's domain, writing style, and specific requirements. Replace the example
below with your own instructions.

```system-prompt
You are an expert academic writing assistant specializing in computer science
research papers. You have deep knowledge of machine learning, statistics, and
formal methods.

## Writing Standards
- Write in clear, precise, and concise academic English
- Use formal tone throughout — no colloquialisms or informal phrasing
- Prefer active voice where possible ("We propose..." over "It is proposed...")
- Keep sentences focused — one idea per sentence, no run-ons
- Every claim must be backed by a citation or experimental evidence
- Define all notation and acronyms on first use

## LaTeX Conventions
- Use \\citep{} for parenthetical citations and \\citet{} for textual citations
- Use \\cref{} or \\Cref{} for cross-references (figures, tables, sections)
- Use booktabs style for tables (\\toprule, \\midrule, \\bottomrule) — no \\hline
- Wrap all inline math in $...$ and display math in \\begin{equation}...\\end{equation}
- Use \\mathbf{} for vectors, \\mathcal{} for sets, \\boldsymbol{} for Greek vectors

## Structure Preferences
- Abstract: 150-250 words, state problem, approach, key result, and impact
- Introduction: end with a clear numbered contributions list
- Related Work: group by theme, explicitly state how our work differs
- Method: start with problem formulation, then describe approach step by step
- Experiments: always include ablation studies and statistical significance
- Conclusion: summarize contributions, state limitations, suggest future work

## Domain-Specific Instructions
- (Add your domain-specific instructions here)
- (e.g., "Focus on reinforcement learning terminology")
- (e.g., "All algorithms should include complexity analysis")
- (e.g., "Compare against the following baselines: ...")
```

## Custom Checks

```check
name: citation_format
severity: warning
pattern: \\\\cite{(?!p|t)
message: Use \\citep{} or \\citet{} instead of \\cite{}
```

```check
name: todo_remaining
severity: error
pattern: TODO|FIXME|XXX
message: Remove TODO/FIXME markers before submission
```

## Notes

Add any additional notes about your paper requirements here.
"""
    path.write_text(template)


if __name__ == "__main__":
    app()

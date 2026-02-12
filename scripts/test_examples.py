#!/usr/bin/env python
"""Script to test TexGuardian examples without the interactive REPL."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from rich.console import Console

from texguardian.config.paper_spec import PaperSpec
from texguardian.config.settings import TexGuardianConfig
from texguardian.core.context import ConversationContext
from texguardian.core.session import SessionState
from texguardian.latex.parser import LatexParser


console = Console()


def test_example(example_name: str, example_dir: Path):
    """Test a single example directory."""
    console.print(f"\n[bold cyan]Testing: {example_name}[/bold cyan]")
    console.print(f"Directory: {example_dir}")

    # Load config
    config_path = example_dir / "texguardian.yaml"
    if not config_path.exists():
        console.print("[red]No texguardian.yaml found[/red]")
        return False

    config = TexGuardianConfig.load(config_path)
    console.print(f"Main tex: {config.project.main_tex}")

    # Load paper spec
    spec_path = example_dir / "paper_spec.md"
    paper_spec = PaperSpec.load(spec_path) if spec_path.exists() else None
    if paper_spec:
        console.print(f"Paper: {paper_spec.title}")
        console.print(f"Venue: {paper_spec.venue}")
        console.print(f"Custom checks: {len(paper_spec.checks)}")

    # Test LaTeX parser
    console.print("\n[bold]Running LaTeX Parser Tests:[/bold]")
    parser = LatexParser(example_dir)

    # Extract citations
    citations = parser.extract_citations()
    console.print(f"  Citations found: {len(citations)}")

    # Extract figures
    figures = parser.extract_figures()
    console.print(f"  Figures found: {len(figures)}")

    # Run custom checks from paper_spec
    if paper_spec and paper_spec.checks:
        console.print("\n[bold]Running Custom Checks:[/bold]")
        for check in paper_spec.checks:
            if check.pattern:
                matches = parser.find_pattern(check.pattern)
                status = "[red]FAIL[/red]" if matches else "[green]PASS[/green]"
                console.print(f"  {check.name}: {status}")
                if matches:
                    for m in matches[:3]:
                        console.print(f"    - {m['file']}:{m['line']}")

    # Check for overflow patterns (manual check)
    console.print("\n[bold]Checking for Overflow Issues:[/bold]")

    # Check figure widths
    overflow_figures = parser.find_pattern(r"width=1\.[2-9]")
    if overflow_figures:
        console.print(f"  [red]Found {len(overflow_figures)} figure(s) with width > 1.0\\columnwidth[/red]")
        for m in overflow_figures:
            console.print(f"    - {m['file']}:{m['line']}: {m['content'][:60]}...")
    else:
        console.print("  [green]No figure overflow issues[/green]")

    # Check wide tables
    wide_tables = parser.find_pattern(r"begin\{tabular\}\{[^}]{15,}\}")
    if wide_tables:
        console.print(f"  [yellow]Found {len(wide_tables)} potentially wide table(s)[/yellow]")
        for m in wide_tables:
            console.print(f"    - {m['file']}:{m['line']}")
    else:
        console.print("  [green]No obvious table overflow issues[/green]")

    return True


def main():
    """Run tests on all examples."""
    console.print("[bold]TexGuardian Example Tests[/bold]")
    console.print("=" * 50)

    examples_dir = project_root / "examples"

    if not examples_dir.exists():
        console.print("[red]No examples directory found[/red]")
        return

    # Test each example
    examples = [d for d in examples_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]

    for example_dir in sorted(examples):
        test_example(example_dir.name, example_dir)

    console.print("\n" + "=" * 50)
    console.print("[bold green]Testing complete![/bold green]")
    console.print("\nTo interactively test with the REPL:")
    console.print("  source scripts/setup_env.sh")
    console.print("  cd examples/position_paper")
    console.print("  texguardian chat")


if __name__ == "__main__":
    main()

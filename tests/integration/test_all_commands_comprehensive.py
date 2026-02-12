"""Comprehensive test of ALL 24 commands on BOTH example papers."""

import asyncio
import sys
import traceback
from pathlib import Path
from io import StringIO
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, AsyncMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Paper directories
PAPERS = {
    "position_paper": Path("/Users/arcaman07/Documents/Projects/TeXGuardian/examples/position_paper"),
    "esolang_paper": Path("/Users/arcaman07/Documents/Projects/TeXGuardian/examples/esolang_paper"),
}

# Main tex files for each paper
MAIN_TEX = {
    "position_paper": "position_paper.tex",
    "esolang_paper": "esolang_bench_paper.tex",
}


@dataclass
class TestResult:
    """Result of a single command test."""
    command: str
    paper: str
    status: str  # "PASS", "FAIL", "ERROR", "SKIP"
    output: str = ""
    error: str = ""
    issues_found: list[str] = field(default_factory=list)
    notes: str = ""


class MockLLMClient:
    """Mock LLM client for testing."""

    async def complete(self, messages, max_tokens=2000, temperature=0.3):
        response = MagicMock()
        response.content = '{"quality_score": 85, "issues": [], "suggestions": [], "summary": "Mock analysis"}'
        return response

    async def complete_with_vision(self, messages, images, max_tokens=2000, temperature=0.3):
        response = MagicMock()
        response.content = '{"quality_score": 85, "issues": [], "patches": [], "summary": "Mock visual analysis"}'
        return response


def create_session(paper_name: str):
    """Create a session for testing."""
    from texguardian.core.session import SessionState
    from texguardian.config.settings import TexGuardianConfig, ProjectConfig

    project_root = PAPERS[paper_name]
    main_tex = MAIN_TEX[paper_name]

    config = TexGuardianConfig(
        project=ProjectConfig(
            main_tex=main_tex,
            output_dir="build",
        ),
    )

    session = SessionState(
        config=config,
        project_root=project_root,
        config_path=project_root / "texguardian.yaml",
    )
    session.llm_client = MockLLMClient()

    return session


def create_console():
    """Create a console that captures output."""
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=150, record=True)
    return console, output


async def run_command_test(command_class, session, args: str = "", command_name: str = "", paper_name: str = "") -> TestResult:
    """Test a single command."""
    console, output = create_console()
    result = TestResult(command=command_name, paper=paper_name, status="PASS")

    try:
        cmd = command_class
        await cmd.execute(session, args, console)
        result.output = output.getvalue()

        # Check for error indicators in output (but not grep results)
        output_lower = result.output.lower()
        if command_name not in ("grep", "read", "search", "bash"):
            if "traceback" in output_lower or "exception" in output_lower:
                result.status = "ERROR"
                result.error = "Error detected in output"

        # Extract issues found
        if "issue" in output_lower or "warning" in output_lower or "fail" in output_lower:
            result.issues_found.append("Issues detected in output")

    except Exception as e:
        result.status = "ERROR"
        result.error = f"{type(e).__name__}: {str(e)}"
        result.output = traceback.format_exc()

    return result


async def run_all_tests():
    """Run all command tests on all papers."""
    from texguardian.cli.commands.registry import CommandRegistry

    # Get all commands from registry
    registry = CommandRegistry()
    registry.register_all()

    all_results: list[TestResult] = []

    print("=" * 80)
    print("COMPREHENSIVE TEST OF ALL 24 COMMANDS ON BOTH EXAMPLE PAPERS")
    print("=" * 80)

    for paper_name in PAPERS.keys():
        print(f"\n{'=' * 80}")
        print(f"TESTING PAPER: {paper_name}")
        print(f"{'=' * 80}")

        session = create_session(paper_name)

        # Test each command
        commands_to_test = [
            # Core commands
            ("help", ""),
            ("compile", ""),
            ("model", ""),
            ("feedback", ""),
            # Full pipeline
            ("review", "quick"),  # Use quick mode to avoid long runs
            ("report", ""),
            # Content commands
            ("figures", ""),
            ("tables", ""),
            ("section", "Introduction"),
            ("citations", ""),
            ("suggest_refs", ""),
            # Submission workflow
            ("venue", "icml"),  # Just check, don't download
            ("anonymize", ""),
            ("camera_ready", ""),
            ("page_count", ""),
            # General verification
            ("verify", ""),
            # File operations
            ("read", session.main_tex_path.name),
            ("grep", "section"),
            ("search", "*.tex"),
            ("bash", "echo test"),
            # Version control (v1)
            ("diff", ""),
            ("revert", ""),
            ("approve", ""),
            ("watch", ""),
            # Visual (v2)
            ("polish_visual", ""),
        ]

        for cmd_name, args in commands_to_test:
            print(f"\n--- Testing /{cmd_name} {args} ---")

            cmd = registry.get_command(cmd_name)
            if not cmd:
                result = TestResult(
                    command=cmd_name,
                    paper=paper_name,
                    status="SKIP",
                    error=f"Command '{cmd_name}' not found in registry"
                )
                all_results.append(result)
                print(f"  [SKIP] Command not found")
                continue

            # Special handling for certain commands
            if cmd_name == "compile":
                # Skip actual compilation, just test the command loads
                result = TestResult(
                    command=cmd_name,
                    paper=paper_name,
                    status="SKIP",
                    notes="Skipped actual compilation (requires LaTeX)"
                )
                all_results.append(result)
                print(f"  [SKIP] Requires LaTeX installation")
                continue

            if cmd_name == "polish_visual":
                # Skip visual polish (requires compilation + vision model)
                result = TestResult(
                    command=cmd_name,
                    paper=paper_name,
                    status="SKIP",
                    notes="Skipped (requires compilation + vision model)"
                )
                all_results.append(result)
                print(f"  [SKIP] Requires compilation + vision model")
                continue

            if cmd_name == "venue":
                # Don't actually download, just test detection
                result = TestResult(
                    command=cmd_name,
                    paper=paper_name,
                    status="SKIP",
                    notes="Skipped download (would modify filesystem)"
                )
                all_results.append(result)
                print(f"  [SKIP] Would modify filesystem")
                continue

            if cmd_name == "write":
                # Skip write to avoid modifying files
                result = TestResult(
                    command=cmd_name,
                    paper=paper_name,
                    status="SKIP",
                    notes="Skipped (would modify filesystem)"
                )
                all_results.append(result)
                print(f"  [SKIP] Would modify filesystem")
                continue

            if cmd_name == "review":
                # Use quick mode and catch any issues
                args = "quick"

            try:
                result = await run_command_test(cmd, session, args, cmd_name, paper_name)
                all_results.append(result)

                if result.status == "PASS":
                    print(f"  [PASS]")
                    # Show brief output summary
                    lines = result.output.strip().split('\n')
                    if lines:
                        print(f"    Output: {len(lines)} lines")
                        # Show first few lines
                        for line in lines[:3]:
                            clean_line = line.strip()
                            if clean_line:
                                print(f"      {clean_line[:80]}...")
                elif result.status == "ERROR":
                    print(f"  [ERROR] {result.error}")
                else:
                    print(f"  [{result.status}] {result.notes}")

            except Exception as e:
                result = TestResult(
                    command=cmd_name,
                    paper=paper_name,
                    status="ERROR",
                    error=f"Test runner error: {type(e).__name__}: {str(e)}"
                )
                all_results.append(result)
                print(f"  [ERROR] {result.error}")

    return all_results


def generate_report(results: list[TestResult]):
    """Generate a comprehensive test report."""
    console = Console()

    print("\n" + "=" * 80)
    print("COMPREHENSIVE TEST REPORT")
    print("=" * 80)

    # Summary statistics
    total = len(results)
    passed = len([r for r in results if r.status == "PASS"])
    failed = len([r for r in results if r.status == "FAIL"])
    errors = len([r for r in results if r.status == "ERROR"])
    skipped = len([r for r in results if r.status == "SKIP"])

    print(f"\nSUMMARY:")
    print(f"  Total Tests: {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Errors: {errors}")
    print(f"  Skipped: {skipped}")
    print(f"  Success Rate: {(passed / (total - skipped) * 100) if (total - skipped) > 0 else 0:.1f}%")

    # Results by paper
    for paper in PAPERS.keys():
        paper_results = [r for r in results if r.paper == paper]
        print(f"\n{'=' * 80}")
        print(f"PAPER: {paper}")
        print(f"{'=' * 80}")

        print(f"\n{'Command':<20} {'Status':<10} {'Notes'}")
        print("-" * 80)

        for r in paper_results:
            status_color = {
                "PASS": "\033[92m",  # Green
                "FAIL": "\033[91m",  # Red
                "ERROR": "\033[91m",  # Red
                "SKIP": "\033[93m",  # Yellow
            }.get(r.status, "")
            reset = "\033[0m"

            notes = r.error[:50] if r.error else r.notes[:50] if r.notes else ""
            print(f"/{r.command:<19} {status_color}{r.status:<10}{reset} {notes}")

    # Detailed errors
    error_results = [r for r in results if r.status == "ERROR"]
    if error_results:
        print(f"\n{'=' * 80}")
        print("DETAILED ERRORS")
        print(f"{'=' * 80}")

        for r in error_results:
            print(f"\n--- /{r.command} on {r.paper} ---")
            print(f"Error: {r.error}")
            if r.output:
                print(f"Output (last 500 chars):")
                print(r.output[-500:])

    # Command-by-command analysis
    print(f"\n{'=' * 80}")
    print("COMMAND-BY-COMMAND ANALYSIS")
    print(f"{'=' * 80}")

    commands_tested = set(r.command for r in results)
    for cmd in sorted(commands_tested):
        cmd_results = [r for r in results if r.command == cmd]
        pass_count = len([r for r in cmd_results if r.status == "PASS"])
        total_count = len(cmd_results)
        skip_count = len([r for r in cmd_results if r.status == "SKIP"])

        if skip_count == total_count:
            status = "SKIPPED"
        elif pass_count == total_count - skip_count:
            status = "WORKING"
        else:
            status = "ISSUES"

        print(f"  /{cmd:<18} {status}")

    return results


async def main():
    """Main entry point."""
    results = await run_all_tests()
    generate_report(results)

    # Return exit code
    errors = len([r for r in results if r.status in ("ERROR", "FAIL")])
    return 1 if errors > 0 else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

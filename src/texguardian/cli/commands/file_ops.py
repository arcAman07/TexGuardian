"""File operation commands."""

from __future__ import annotations

import asyncio
import fnmatch
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState

# Maximum file size (in bytes) that /read will display without confirmation
_MAX_READ_SIZE = 256 * 1024  # 256 KB

# Maximum number of lines /read will display
_MAX_READ_LINES = 2000

# Maximum grep matches before truncating
_MAX_GREP_MATCHES = 200


def _resolve_safe_path(args: str, session: SessionState) -> Path | None:
    """Resolve *args* to an absolute path within the project root.

    Returns ``None`` if the resolved path escapes the project directory.
    """
    raw = (session.project_root / args.strip()).resolve()
    try:
        raw.relative_to(session.project_root.resolve())
    except ValueError:
        return None
    return raw


def _is_binary(path: Path) -> bool:
    """Quick heuristic: read first 8 KB and check for null bytes."""
    try:
        chunk = path.read_bytes()[:8192]
        return b"\x00" in chunk
    except Exception:
        return False


class ReadCommand(Command):
    """Read a file."""

    name = "read"
    description = "Display contents of a file"
    aliases = ["cat"]
    usage = "/read <file_path> — display file contents with line numbers"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute read command."""
        if not args:
            console.print("[red]Usage: /read <file_path>[/red]")
            return

        file_path = _resolve_safe_path(args, session)
        if file_path is None:
            console.print("[red]Access denied: path is outside the project directory[/red]")
            return

        if not file_path.exists():
            console.print(f"[red]File not found: {args}[/red]")
            return

        if not file_path.is_file():
            console.print(f"[red]Not a file: {args}[/red]")
            return

        # Check denylist
        if _is_denied(file_path, session):
            console.print(f"[red]Access denied: {args} is in denylist[/red]")
            return

        # Guard against binary files
        if _is_binary(file_path):
            console.print(f"[yellow]{args} appears to be a binary file — skipping[/yellow]")
            return

        # Guard against very large files
        size = file_path.stat().st_size
        if size > _MAX_READ_SIZE:
            console.print(
                f"[yellow]{args} is {size / 1024:.0f} KB — showing first "
                f"{_MAX_READ_LINES} lines[/yellow]"
            )

        try:
            content = file_path.read_text()
            lines = content.split("\n")

            display_lines = lines[:_MAX_READ_LINES]
            for i, line in enumerate(display_lines, 1):
                console.print(f"[dim]{i:4}[/dim] {line}")

            if len(lines) > _MAX_READ_LINES:
                console.print(
                    f"\n[dim]... {len(lines) - _MAX_READ_LINES} more lines "
                    f"(total {len(lines)})[/dim]"
                )

        except UnicodeDecodeError:
            console.print(f"[yellow]{args} is not a text file — cannot display[/yellow]")
        except Exception as e:
            console.print(f"[red]Error reading file: {e}[/red]")

    def get_completions(self, partial: str) -> list[str]:
        """Get file completions."""
        return []  # TODO: implement file completion


class WriteCommand(Command):
    """Write to a file."""

    name = "write"
    description = "Write content to a file (requires v1+)"
    aliases = []
    usage = "/write <file_path> — enter content interactively, end with Ctrl+D"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute write command."""
        if not args:
            console.print("[red]Usage: /write <file_path>[/red]")
            console.print("Then enter content, end with EOF (Ctrl+D)")
            return

        file_path = _resolve_safe_path(args, session)
        if file_path is None:
            console.print("[red]Access denied: path is outside the project directory[/red]")
            return

        # Check allowlist/denylist
        if not _is_allowed(file_path, session):
            console.print(f"[red]Access denied: {args} is not in allowlist[/red]")
            return

        if _is_denied(file_path, session):
            console.print(f"[red]Access denied: {args} is in denylist[/red]")
            return

        console.print("Enter content (Ctrl+D to save, Ctrl+C to cancel):")

        try:
            lines = []
            while True:
                try:
                    line = await asyncio.to_thread(input)
                    lines.append(line)
                except EOFError:
                    break

            content = "\n".join(lines)

            # Create checkpoint before write
            if session.checkpoint_manager:
                await session.checkpoint_manager.create(
                    f"Before write to {args}",
                    [file_path],
                )

            try:
                file_path.parent.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                console.print(f"[red]Permission denied: cannot create directory {file_path.parent}[/red]")
                return
            file_path.write_text(content)
            console.print(f"[green]Wrote {len(content)} bytes to {args}[/green]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled[/yellow]")


class GrepCommand(Command):
    """Search for pattern in files."""

    name = "grep"
    description = "Search for pattern in files"
    aliases = ["g"]
    usage = "/grep <pattern> [file_glob] — search for regex pattern (default: *.tex)"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute grep command."""
        if not args:
            console.print("[red]Usage: /grep <pattern> [file_glob][/red]")
            console.print("Example: /grep 'TODO' '*.tex'")
            return

        parts = args.split(maxsplit=1)
        pattern = parts[0].strip("'\"")
        file_glob = parts[1].strip("'\"") if len(parts) > 1 else "*.tex"

        import re

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            console.print(f"[red]Invalid pattern: {e}[/red]")
            return

        # Find matching files
        matches_found = 0
        for file_path in sorted(session.project_root.rglob(file_glob)):
            if _is_denied(file_path, session):
                continue
            if not file_path.is_file():
                continue
            if _is_binary(file_path):
                continue

            try:
                content = file_path.read_text()
                rel_path = file_path.relative_to(session.project_root)

                for i, line in enumerate(content.split("\n"), 1):
                    if regex.search(line):
                        console.print(
                            f"[cyan]{rel_path}[/cyan]:[yellow]{i}[/yellow]: "
                            f"{line.strip()}"
                        )
                        matches_found += 1
                        if matches_found >= _MAX_GREP_MATCHES:
                            console.print(
                                f"\n[yellow]Showing first {_MAX_GREP_MATCHES} "
                                f"matches — refine your pattern or glob[/yellow]"
                            )
                            return

            except (UnicodeDecodeError, PermissionError):
                continue
            except Exception:
                continue

        if matches_found == 0:
            console.print("[dim]No matches found[/dim]")
        else:
            console.print(f"\n[dim]{matches_found} match(es)[/dim]")


class SearchCommand(Command):
    """Search for files."""

    name = "search"
    description = "Search for files by name pattern"
    aliases = ["find", "ls"]
    usage = "/search [pattern] — list files matching glob pattern (default: *)"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute search command."""
        pattern = args.strip() if args else "*"

        console.print(f"Searching for: {pattern}\n")

        found = []
        for file_path in sorted(session.project_root.rglob(pattern)):
            if _is_denied(file_path, session):
                continue
            if file_path.is_file():
                rel_path = file_path.relative_to(session.project_root)
                found.append(rel_path)

        if found:
            for f in found[:50]:
                size = (session.project_root / f).stat().st_size
                if size >= 1024 * 1024:
                    size_str = f"{size / (1024 * 1024):.1f} MB"
                elif size >= 1024:
                    size_str = f"{size / 1024:.0f} KB"
                else:
                    size_str = f"{size} B"
                console.print(f"  [dim]{size_str:>8}[/dim]  {f}")
            if len(found) > 50:
                console.print(f"\n  [dim]... and {len(found) - 50} more[/dim]")
            console.print(f"\n[dim]{len(found)} file(s) found[/dim]")
        else:
            console.print("[dim]No files found[/dim]")


class BashCommand(Command):
    """Run a shell command."""

    name = "bash"
    description = "Run a shell command"
    aliases = ["sh", "!"]
    usage = "/bash <command> — run a shell command in the project directory"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute bash command."""
        if not args:
            console.print("[red]Usage: /bash <command>[/red]")
            return

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                args,
                shell=True,
                capture_output=True,
                text=True,
                cwd=session.project_root,
                timeout=60,
            )

            if result.stdout:
                console.print(result.stdout.rstrip())
            if result.stderr:
                console.print(f"[yellow]{result.stderr.rstrip()}[/yellow]")
            if result.returncode != 0:
                console.print(f"[dim]Exit code: {result.returncode}[/dim]")

        except subprocess.TimeoutExpired:
            console.print("[red]Command timed out after 60 seconds[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def _is_allowed(path: Path, session: SessionState) -> bool:
    """Check if path is in allowlist."""
    try:
        rel_path = str(path.relative_to(session.project_root.resolve()))
    except ValueError:
        return False
    for pattern in session.config.safety.allowlist:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False


def _is_denied(path: Path, session: SessionState) -> bool:
    """Check if path is in denylist."""
    try:
        rel_path = str(path.relative_to(session.project_root.resolve()))
    except ValueError:
        return True  # Deny paths outside project

    for pattern in session.config.safety.denylist:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
    return False

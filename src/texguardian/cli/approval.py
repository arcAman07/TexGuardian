"""Claude Code-style approval flow for patches and edits.

Simple 3-option flow:
- [A]pply all - Apply all patches (default, most common)
- [R]eview - Review each patch individually
- [N]o - Skip all patches
"""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState
    from texguardian.patch.parser import Patch


def _flush_and_input() -> str:
    """Flush stdout/stderr then read a line of input.

    Rich buffers output internally; flushing before a blocking
    ``input()`` call ensures the prompt text is visible.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    return input()


async def interactive_approval(
    patches: list[Patch],
    session: SessionState,
    console: Console,
    *,
    auto_approve: bool = False,
) -> int:
    """
    Simple 3-option approval for patches.

    Returns number of patches applied.

    When *auto_approve* is True the interactive prompt is skipped and all
    patches are applied immediately (used by ``/review`` auto-fix).
    """
    if not patches:
        return 0

    if auto_approve:
        return await _apply_all_patches(patches, session, console)

    console.print(f"\n[bold yellow]Found {len(patches)} patch(es):[/bold yellow]\n")

    for i, patch in enumerate(patches, 1):
        console.print(
            f"  {i}. [cyan]{escape(str(patch.file_path))}[/cyan]"
            f" (+{patch.additions}/-{patch.deletions})"
        )

    console.print()

    # Simple 3 options
    console.print("[bold]What would you like to do?[/bold]")
    console.print("  [green][A]pply all[/green] - Apply all patches (recommended)")
    console.print("  [cyan][R]eview[/cyan]    - Review each patch before applying")
    console.print("  [yellow][N]o[/yellow]        - Skip all patches")
    console.print()
    console.print("Choice [A/r/n]: ", end="")

    try:
        choice = await asyncio.to_thread(_flush_and_input)
        choice = choice.strip().lower()

        if choice in ("", "a", "apply", "y", "yes"):
            return await _apply_all_patches(patches, session, console)

        elif choice in ("r", "review"):
            return await _review_patches(patches, session, console)

        elif choice in ("n", "no", "skip", "s"):
            console.print("[dim]Skipped all patches[/dim]")
            return 0

        else:
            console.print(f"[dim]Unknown option '{escape(choice)}', skipping[/dim]")
            return 0

    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Cancelled[/dim]")
        return 0


async def _apply_all_patches(
    patches: list[Patch],
    session: SessionState,
    console: Console,
) -> int:
    """Apply all patches without review."""
    console.print("\n[cyan]Applying all patches...[/cyan]")

    applied = 0
    for patch in patches:
        success = await _apply_single_patch(patch, session, console, verbose=False)
        if success:
            applied += 1
            console.print(f"  [green]✓[/green] {escape(str(patch.file_path))}")
        else:
            console.print(f"  [red]✗[/red] {escape(str(patch.file_path))}")

    console.print(f"\n[bold]Applied {applied}/{len(patches)} patch(es)[/bold]")
    return applied


async def _review_patches(
    patches: list[Patch],
    session: SessionState,
    console: Console,
) -> int:
    """Review and apply patches one by one."""
    applied = 0

    for i, patch in enumerate(patches):
        console.print(
            f"\n[bold]Patch {i+1}/{len(patches)}:"
            f" {escape(str(patch.file_path))}[/bold]"
        )

        # Show diff
        _show_patch_diff(patch, console)

        # Ask for this patch
        console.print("[A]pply / [S]kip: ", end="")

        try:
            choice = await asyncio.to_thread(_flush_and_input)
            choice = choice.strip().lower()

            if choice in ("", "a", "apply", "y", "yes"):
                success = await _apply_single_patch(patch, session, console, verbose=True)
                if success:
                    applied += 1
            else:
                console.print("[dim]Skipped[/dim]")

        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Cancelled remaining patches[/dim]")
            break

    console.print(f"\n[bold]Applied {applied}/{len(patches)} patch(es)[/bold]")
    return applied


def _show_patch_diff(patch: Patch, console: Console) -> None:
    """Show diff with syntax highlighting."""
    diff_text = patch.raw_diff if patch.raw_diff else str(patch)

    syntax = Syntax(
        diff_text,
        "diff",
        theme="monokai",
        line_numbers=True,
        word_wrap=True,
    )

    console.print(Panel(
        syntax,
        title=f"+{patch.additions}/-{patch.deletions} lines",
        border_style="cyan",
    ))


async def action_approval(
    action_title: str,
    details: list[str],
    console: Console,
) -> bool:
    """Approve/reject a proposed action (non-patch).

    Shows a Panel with the action title and details, then asks [A]pprove / [N]o.
    Returns True if approved.
    """
    body = "\n".join(details)
    console.print(Panel.fit(
        f"[bold]{action_title}[/bold]\n\n{body}",
        border_style="yellow",
        title="Proposed Action",
    ))
    console.print("[A]pprove / [N]o: ", end="")

    try:
        choice = await asyncio.to_thread(_flush_and_input)
        return choice.strip().lower() in ("", "a", "approve", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        console.print("\n[dim]Cancelled[/dim]")
        return False


async def _apply_single_patch(
    patch: Patch,
    session: SessionState,
    console: Console,
    verbose: bool = True,
) -> bool:
    """Apply a single patch with checkpointing."""
    from texguardian.checkpoint.manager import CheckpointManager
    from texguardian.patch.applier import PatchApplier
    from texguardian.patch.validator import PatchValidator

    # Initialize managers
    if not session.checkpoint_manager:
        session.checkpoint_manager = CheckpointManager(session.guardian_dir)

    validator = PatchValidator(session.config.safety)
    applier = PatchApplier(session.project_root)

    # Correct filename if the LLM used a generic name that doesn't exist
    target_path = session.project_root / patch.file_path
    if not target_path.exists() and patch.file_path.endswith(".tex"):
        # First try the configured main_tex
        main_tex_name = session.config.project.main_tex
        corrected = session.project_root / main_tex_name
        if corrected.exists():
            patch.file_path = main_tex_name
            target_path = corrected
        else:
            # Fallback: auto-detect the main .tex file
            from texguardian.config.settings import detect_main_tex

            detected = detect_main_tex(session.project_root)
            if detected:
                patch.file_path = detected
                target_path = session.project_root / detected

    # Validate
    result = validator.validate(patch, target_path)
    if not result.valid:
        console.print(f"[red]Validation failed: {result.reason}[/red]")
        return False

    # Create checkpoint
    try:
        await session.checkpoint_manager.create(
            f"Before patch: {patch.file_path}",
            [target_path],
        )
    except Exception as exc:
        console.print(f"[dim]Checkpoint skipped: {exc}[/dim]")

    # Apply patch
    try:
        success = applier.apply(patch)
        if not success:
            console.print(
                f"[red]Patch failed: context not found in"
                f" {escape(str(patch.file_path))}[/red]"
            )
        return success
    except Exception as e:
        console.print(f"[red]Error applying patch: {e}[/red]")
        return False

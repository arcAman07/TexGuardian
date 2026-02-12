"""Approve command for applying pending patches."""

from __future__ import annotations

from typing import TYPE_CHECKING

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState
    from texguardian.patch.parser import Patch


class ApproveCommand(Command):
    """Approve and apply pending patches."""

    name = "approve"
    description = "Approve and apply pending patches"
    aliases = ["apply", "a"]

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute approve command."""
        # Get patches from last assistant message
        if not session.context:
            console.print("[dim]No conversation context - no patches to approve[/dim]")
            return

        last_response = session.context.get_last_assistant_message()
        if not last_response:
            console.print("[dim]No patches to approve[/dim]")
            return

        from texguardian.patch.parser import extract_patches

        patches = extract_patches(last_response)

        if not patches:
            console.print("[dim]No patches found in last response[/dim]")
            return

        console.print(f"Found {len(patches)} patch(es):\n")

        for i, patch in enumerate(patches, 1):
            console.print(f"[bold]{i}. {patch.file_path}[/bold]")
            console.print(f"   Lines changed: {patch.lines_changed}")

        console.print("\nApply all patches? [y/N] ", end="")

        import asyncio

        try:
            response = await asyncio.to_thread(input)
            if response.lower() not in ("y", "yes"):
                console.print("[dim]Cancelled[/dim]")
                return
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Cancelled[/dim]")
            return

        await apply_patches(patches, session, console)


async def apply_patches(
    patches: list[Patch],
    session: SessionState,
    console: Console,
) -> None:
    """Apply a list of patches with checkpointing."""
    from texguardian.checkpoint.manager import CheckpointManager
    from texguardian.patch.applier import PatchApplier
    from texguardian.patch.validator import PatchValidator

    # Initialize managers
    if not session.checkpoint_manager:
        session.checkpoint_manager = CheckpointManager(session.guardian_dir)

    validator = PatchValidator(session.config.safety)
    applier = PatchApplier(session.project_root)

    # Get files to checkpoint
    files_to_checkpoint = [
        session.project_root / p.file_path for p in patches
    ]

    # Create checkpoint
    await session.checkpoint_manager.create(
        "Before patch application",
        files_to_checkpoint,
    )
    console.print("[dim]Checkpoint created[/dim]")

    # Validate and apply patches
    applied = 0
    for patch in patches:
        target_path = session.project_root / patch.file_path

        # Validate
        result = validator.validate(patch, target_path)
        if not result.valid:
            console.print(f"[red]Rejected {patch.file_path}: {result.reason}[/red]")
            continue

        # Check human review
        if result.requires_human_review:
            console.print(f"[yellow]{patch.file_path} requires human review:[/yellow]")
            for reason in result.review_reasons:
                console.print(f"  - {reason}")
            console.print("Apply anyway? [y/N] ", end="")

            import asyncio

            try:
                response = await asyncio.to_thread(input)
                if response.lower() not in ("y", "yes"):
                    console.print("[dim]Skipped[/dim]")
                    continue
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Skipped[/dim]")
                continue

        # Apply patch
        try:
            success = applier.apply(patch)
            if success:
                console.print(f"[green]Applied: {patch.file_path}[/green]")
                applied += 1
            else:
                console.print(f"[red]Failed to apply: {patch.file_path}[/red]")
        except Exception as e:
            console.print(f"[red]Error applying {patch.file_path}: {e}[/red]")

    console.print(f"\n[bold]Applied {applied}/{len(patches)} patch(es)[/bold]")

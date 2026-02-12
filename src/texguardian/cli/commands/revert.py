"""Revert command for restoring checkpoints."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from rich.table import Table

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class RevertCommand(Command):
    """Revert to a previous checkpoint."""

    name = "revert"
    description = "Revert to a previous checkpoint"
    aliases = ["undo", "rollback"]

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute revert command."""
        # Initialize checkpoint manager if needed
        if not session.checkpoint_manager:
            from texguardian.checkpoint.manager import CheckpointManager

            session.checkpoint_manager = CheckpointManager(session.guardian_dir)

        checkpoint_id = args.strip() if args else None

        # List checkpoints if none specified
        checkpoints = session.checkpoint_manager.list_checkpoints()

        if not checkpoints:
            console.print("[dim]No checkpoints available[/dim]")
            return

        if not checkpoint_id:
            console.print("Available checkpoints:\n")
            table = Table(show_header=True)
            table.add_column("ID")
            table.add_column("Description")
            table.add_column("Time")
            table.add_column("Files")

            for cp in checkpoints[:10]:
                table.add_row(
                    cp["id"][:12],
                    cp["description"][:40],
                    cp["timestamp"],
                    str(cp["file_count"]),
                )

            console.print(table)
            console.print("\n[dim]Use /revert <id> to restore a checkpoint[/dim]")
            return

        # Find matching checkpoint
        matching = [cp for cp in checkpoints if cp["id"].startswith(checkpoint_id)]

        if not matching:
            console.print(f"[red]Checkpoint not found: {checkpoint_id}[/red]")
            return

        if len(matching) > 1:
            console.print("[yellow]Multiple matches, using most recent[/yellow]")

        target = matching[0]
        console.print(f"Revert to checkpoint: [cyan]{target['id'][:12]}[/cyan]")
        console.print(f"Description: {target['description']}")
        console.print(f"Files: {target['file_count']}")
        console.print("\nRevert? [y/N] ", end="")

        try:
            response = await asyncio.to_thread(input)
            if response.lower() not in ("y", "yes"):
                console.print("[dim]Cancelled[/dim]")
                return
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Cancelled[/dim]")
            return

        # Perform revert
        try:
            success = await session.checkpoint_manager.restore(target["id"])
            if success:
                console.print(f"[green]Reverted to checkpoint {target['id'][:12]}[/green]")
            else:
                console.print("[red]Revert failed[/red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

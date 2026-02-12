"""Diff command for showing changes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class DiffCommand(Command):
    """Show changes since last checkpoint."""

    name = "diff"
    description = "Show changes since last checkpoint"
    aliases = ["d"]

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute diff command."""
        # Initialize checkpoint manager if needed
        if not session.checkpoint_manager:
            from texguardian.checkpoint.manager import CheckpointManager

            session.checkpoint_manager = CheckpointManager(session.guardian_dir)

        # Get checkpoint ID from args or use latest
        checkpoint_id = args.strip() if args else None

        if not checkpoint_id:
            checkpoints = session.checkpoint_manager.list_checkpoints()
            if not checkpoints:
                console.print("[dim]No checkpoints available[/dim]")
                return
            checkpoint_id = checkpoints[0]["id"]

        console.print(f"Changes since checkpoint: [cyan]{checkpoint_id}[/cyan]\n")

        try:
            diff_data = await session.checkpoint_manager.diff(checkpoint_id)

            if not diff_data:
                console.print("[green]No changes[/green]")
                return

            for file_path, diff_text in diff_data.items():
                console.print(f"[bold]{file_path}[/bold]")
                _print_diff(diff_text, console)
                console.print()

        except Exception as e:
            console.print(f"[red]Error generating diff: {e}[/red]")


def _print_diff(diff_text: str, console: Console) -> None:
    """Print colored diff output."""
    for line in diff_text.split("\n"):
        if line.startswith("+") and not line.startswith("+++"):
            console.print(f"[green]{line}[/green]")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(f"[red]{line}[/red]")
        elif line.startswith("@@"):
            console.print(f"[cyan]{line}[/cyan]")
        else:
            console.print(line)

"""Help command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.table import Table

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.cli.commands.registry import CommandRegistry
    from texguardian.core.session import SessionState


class HelpCommand(Command):
    """Show available commands."""

    name = "help"
    description = "Show available commands"
    aliases = ["h", "?"]

    def __init__(self, registry: CommandRegistry):
        self.registry = registry

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute the help command."""
        if args:
            # Show help for specific command
            cmd = self.registry.get_command(args)
            if cmd:
                from rich.panel import Panel
                lines = [f"[bold cyan]/{cmd.name}[/bold cyan]"]
                lines.append(cmd.description or "No description")
                if cmd.aliases:
                    lines.append(f"[dim]Aliases: {', '.join('/' + a for a in cmd.aliases)}[/dim]")
                if hasattr(cmd, "usage") and cmd.usage:
                    lines.append(f"\n[bold]Usage:[/bold]\n{cmd.usage}")
                console.print(Panel.fit("\n".join(lines), border_style="cyan"))
            else:
                console.print(f"[red]Unknown command: {args}[/red]")
            return

        from rich.rule import Rule

        # Show all commands grouped by category
        categories = {
            "Core": ["help", "compile", "model", "feedback"],
            "Full Pipeline": ["review", "report"],
            "Content": ["figures", "tables", "section", "citations", "suggest_refs"],
            "Submission": ["venue", "anonymize", "camera_ready", "page_count"],
            "Verification": ["verify"],
            "Files": ["read", "write", "grep", "search", "bash"],
            "Version Control": ["diff", "revert", "approve", "watch"],
            "Visual": ["polish_visual"],
        }

        commands = self.registry.list_commands()
        cmd_dict = {name: desc for name, desc in commands}

        console.print(Rule("[bold cyan]TexGuardian Commands[/bold cyan]", style="cyan"))
        console.print()

        for category, cmd_names in categories.items():
            table = Table(
                show_header=False,
                box=None,
                padding=(0, 2),
                title=f"[bold]{category}[/bold]",
                title_justify="left",
                title_style="",
            )
            table.add_column("Command", style="cyan", min_width=20)
            table.add_column("Description", style="dim")
            for name in cmd_names:
                if name in cmd_dict:
                    table.add_row(f"/{name}", cmd_dict[name])
            console.print(table)
            console.print()

        console.print("[dim]Type [cyan]/help <command>[/cyan] for detailed usage  |  Type anything without / to chat with the LLM[/dim]")

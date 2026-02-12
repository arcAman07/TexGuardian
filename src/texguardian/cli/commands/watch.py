"""Watch mode command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class WatchCommand(Command):
    """Toggle watch mode for auto-recompilation."""

    name = "watch"
    description = "Toggle watch mode for auto-recompilation"
    aliases = ["w"]

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute watch command."""
        arg = args.strip().lower()

        if arg in ("on", "start", "enable"):
            await self._start_watch(session, console)
        elif arg in ("off", "stop", "disable"):
            await self._stop_watch(session, console)
        else:
            # Toggle
            if session.watch_enabled:
                await self._stop_watch(session, console)
            else:
                await self._start_watch(session, console)

    async def _start_watch(
        self,
        session: SessionState,
        console: Console,
    ) -> None:
        """Start watch mode."""
        if session.watch_enabled:
            console.print("[yellow]Watch mode already enabled[/yellow]")
            return

        from texguardian.latex.watcher import LatexWatcher

        console.print("Starting watch mode...")

        try:
            watcher = LatexWatcher(session)
            watcher.start()
            # Store watcher on session for later stop
            session._watcher = watcher
            session.watch_enabled = True
            console.print("[green]Watch mode enabled[/green]")
            console.print("[dim]Files will auto-recompile on save[/dim]")
        except Exception as e:
            console.print(f"[red]Failed to start watch: {e}[/red]")

    async def _stop_watch(
        self,
        session: SessionState,
        console: Console,
    ) -> None:
        """Stop watch mode."""
        if not session.watch_enabled:
            console.print("[dim]Watch mode not active[/dim]")
            return

        # Stop the watcher if stored
        watcher = getattr(session, '_watcher', None)
        if watcher:
            try:
                watcher.stop()
            except Exception as e:
                console.print(f"[yellow]Warning stopping watcher: {e}[/yellow]")
            session._watcher = None

        session.watch_enabled = False
        console.print("[green]Watch mode disabled[/green]")

    def get_completions(self, partial: str) -> list[str]:
        """Get argument completions."""
        options = ["on", "off"]
        return [o for o in options if o.startswith(partial.lower())]

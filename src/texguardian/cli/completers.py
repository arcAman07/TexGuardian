"""Tab completion for the REPL."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document

if TYPE_CHECKING:
    from texguardian.cli.commands.registry import CommandRegistry


class TexGuardianCompleter(Completer):
    """Completer for TexGuardian REPL commands."""

    def __init__(self, registry: CommandRegistry):
        self.registry = registry

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        """Get completions for current input."""
        try:
            yield from self._get_completions_inner(document)
        except Exception:
            # Never let a completer crash take down the REPL.
            return

    def _get_completions_inner(
        self, document: Document
    ) -> Iterable[Completion]:
        text = document.text_before_cursor.lstrip()

        # Only complete if starting with /
        if not text.startswith("/"):
            return

        # Get the partial command name
        partial = text[1:]  # Remove leading /

        # If there's a space, we're completing arguments
        if " " in partial:
            cmd_name, arg_partial = partial.split(" ", 1)
            yield from self._complete_args(cmd_name, arg_partial, document)
        else:
            # Complete command names
            yield from self._complete_commands(partial, document)

    def _complete_commands(
        self, partial: str, document: Document
    ) -> Iterable[Completion]:
        """Complete command names."""
        for name, cmd in self.registry.commands.items():
            if name.startswith(partial.lower()):
                yield Completion(
                    text=name,
                    start_position=-len(partial),
                    display=f"/{name}",
                    display_meta=cmd.description[:40] if cmd.description else "",
                )

    def _complete_args(
        self, cmd_name: str, arg_partial: str, document: Document
    ) -> Iterable[Completion]:
        """Complete command arguments."""
        command = self.registry.get_command(cmd_name)
        if not command:
            return

        # Get argument completions from command
        completions = command.get_completions(arg_partial)
        for comp in completions:
            yield Completion(
                text=comp,
                start_position=-len(arg_partial),
            )

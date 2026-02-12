"""Command registration and dispatch."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class Command(ABC):
    """Base class for slash commands."""

    name: str
    description: str = ""
    aliases: list[str] = []

    @abstractmethod
    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute the command."""
        ...

    def get_completions(self, partial: str) -> list[str]:
        """Get argument completions. Override in subclasses."""
        return []


class CommandRegistry:
    """Registry of available commands."""

    def __init__(self):
        self.commands: dict[str, Command] = {}

    def register(self, command: Command) -> None:
        """Register a command."""
        self.commands[command.name.lower()] = command
        for alias in command.aliases:
            self.commands[alias.lower()] = command

    def get_command(self, name: str) -> Command | None:
        """Get command by name or alias."""
        return self.commands.get(name.lower())

    def register_all(self) -> None:
        """Register all built-in commands."""
        from texguardian.cli.commands.analysis import SuggestRefsCommand
        from texguardian.cli.commands.anonymize import AnonymizeCommand
        from texguardian.cli.commands.approve import ApproveCommand
        from texguardian.cli.commands.camera_ready import CameraReadyCommand
        from texguardian.cli.commands.citations import CitationsCommand
        from texguardian.cli.commands.compile import CompileCommand
        from texguardian.cli.commands.diff import DiffCommand
        from texguardian.cli.commands.feedback import FeedbackCommand
        from texguardian.cli.commands.figures import FiguresCommand
        from texguardian.cli.commands.file_ops import (
            BashCommand,
            GrepCommand,
            ReadCommand,
            SearchCommand,
            WriteCommand,
        )
        from texguardian.cli.commands.help import HelpCommand
        from texguardian.cli.commands.model import ModelCommand
        from texguardian.cli.commands.page_count import PageCountCommand
        from texguardian.cli.commands.report import ReportCommand
        from texguardian.cli.commands.revert import RevertCommand
        from texguardian.cli.commands.review import ReviewCommand
        from texguardian.cli.commands.section import SectionCommand
        from texguardian.cli.commands.tables import TablesCommand
        from texguardian.cli.commands.venue import VenueCommand
        from texguardian.cli.commands.verify import VerifyCommand
        from texguardian.cli.commands.visual import PolishVisualCommand
        from texguardian.cli.commands.watch import WatchCommand

        # Core commands
        self.register(HelpCommand(self))
        self.register(CompileCommand())
        self.register(ReportCommand())
        self.register(ModelCommand())
        self.register(FeedbackCommand())

        # Verification commands
        self.register(VerifyCommand())

        # Citation & Reference commands
        self.register(CitationsCommand())
        self.register(SuggestRefsCommand())

        # Unified verify+fix+analyze commands
        self.register(FiguresCommand())   # Merged: verify_figures + analyze_figures
        self.register(TablesCommand())    # Merged: verify + analyze_tables
        self.register(SectionCommand())   # Merged: verify_section + analysis

        # File operation commands
        self.register(ReadCommand())
        self.register(WriteCommand())
        self.register(GrepCommand())
        self.register(SearchCommand())
        self.register(BashCommand())

        # Version control commands
        self.register(DiffCommand())
        self.register(RevertCommand())
        self.register(ApproveCommand())
        self.register(WatchCommand())

        # Visual verification
        self.register(PolishVisualCommand())

        # Full pipeline command
        self.register(ReviewCommand())

        # Submission workflow commands
        self.register(VenueCommand())
        self.register(CameraReadyCommand())
        self.register(AnonymizeCommand())
        self.register(PageCountCommand())

    def list_commands(self) -> list[tuple[str, str]]:
        """Get list of unique commands with descriptions."""
        seen = set()
        result = []
        for name, cmd in self.commands.items():
            if cmd.name not in seen:
                result.append((cmd.name, cmd.description))
                seen.add(cmd.name)
        return sorted(result)

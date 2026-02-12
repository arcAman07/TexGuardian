"""Visual polish command."""

from __future__ import annotations

from typing import TYPE_CHECKING

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


class PolishVisualCommand(Command):
    """Run visual polish loop."""

    name = "polish_visual"
    description = "Run visual verification loop with vision model"
    aliases = ["pv", "visual"]

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute visual polish command."""
        from texguardian.visual.verifier import VisualVerifier

        focus_text = args.strip()
        if focus_text:
            console.print(f"Starting visual verification loop (focus: [italic]{focus_text}[/italic])...\n")
        else:
            console.print("Starting visual verification loop...\n")

        verifier = VisualVerifier(session)
        max_rounds = session.config.safety.max_visual_rounds

        try:
            result = await verifier.run_loop(
                max_rounds=max_rounds,
                console=console,
                focus_areas=[focus_text] if focus_text else None,
            )

            # Print summary
            console.print("\n[bold]Visual Polish Complete[/bold]")
            console.print(f"  Rounds: {result.rounds}")
            console.print(f"  Final Score: {result.quality_score}/100")
            console.print(f"  Patches Applied: {result.patches_applied}")

            if result.remaining_issues:
                console.print(f"  Remaining Issues: {len(result.remaining_issues)}")
                for issue in result.remaining_issues[:3]:
                    console.print(f"    - {issue}")

        except Exception as e:
            console.print(f"[red]Visual verification failed: {e}[/red]")

"""Interactive REPL using prompt_toolkit."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel

from texguardian.cli.commands.registry import CommandRegistry
from texguardian.cli.completers import TexGuardianCompleter
from texguardian.llm.factory import create_llm_client
from texguardian.llm.prompts.system import build_chat_system_prompt

if TYPE_CHECKING:
    from texguardian.core.session import SessionState


async def run_repl(session: SessionState, console: Console) -> None:
    """Run the interactive REPL loop."""
    # Initialize LLM client
    try:
        session.llm_client = create_llm_client(session.config)
    except ValueError as e:
        console.print(f"[red]Error initializing LLM client: {e}[/red]")
        console.print("[dim]Check your texguardian.yaml provider settings and credentials[/dim]")
        return

    # Initialize command registry
    registry = CommandRegistry()
    registry.register_all()

    # Setup prompt session with history and proper paste handling
    history_file = session.guardian_dir / "history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    prompt_session: PromptSession = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=TexGuardianCompleter(registry),
        enable_history_search=True,
        multiline=False,
    )

    # Print welcome message
    _print_welcome(session, console)
    console.print()  # Breathing room after welcome panel

    # Main REPL loop
    while True:
        try:
            # Get user input — use patch_stdout so Rich output
            # doesn't interfere with prompt_toolkit's rendering.
            with patch_stdout():
                user_input = await asyncio.to_thread(
                    prompt_session.prompt,
                    HTML('<style fg="ansibrightcyan" bold="true">\u276f </style>'),
                )

            user_input = user_input.strip()
            if not user_input:
                continue

            # Echo slash commands so they're visible in scrollback;
            # natural language input is already visible at the prompt.
            if user_input.startswith("/"):
                console.print(f"\n[bold cyan]{escape(user_input)}[/bold cyan]")

            # Handle special commands
            if user_input.lower() in ("exit", "quit", "/exit", "/quit"):
                console.print("\n[dim]Goodbye![/dim]")
                break

            if user_input == "/clear":
                # Print enough newlines to visually clear without
                # destroying scrollback history (avoids screen flash).
                console.print("\n" * console.height)
                continue

            # Check if it's a slash command
            if user_input.startswith("/"):
                await _handle_command(user_input, session, registry, console)
                console.print()  # Post-command spacing
            else:
                # Send to LLM
                await _handle_chat(user_input, session, console)

        except KeyboardInterrupt:
            console.print("\n[dim]Use /exit to quit[/dim]")
            continue
        except EOFError:
            break

    # Cleanup
    if session.llm_client:
        await session.llm_client.close()


def _print_welcome(session: SessionState, console: Console) -> None:
    """Print welcome message with paper stats."""
    from texguardian.latex.parser import LatexParser

    title = session.paper_spec.title if session.paper_spec else "No paper"
    venue = session.paper_spec.venue if session.paper_spec else "Unknown"
    deadline = session.paper_spec.deadline if session.paper_spec else None
    provider = session.config.providers.default
    main_tex = session.config.project.main_tex

    # Truncate long titles
    max_title_len = 48
    display_title = title if len(title) <= max_title_len else title[:max_title_len - 3] + "..."

    # Gather file stats
    fig_count = 0
    table_count = 0
    try:
        parser = LatexParser(session.project_root, main_tex)
        fig_count = len(parser.extract_figures_with_details())
        table_count = len(parser.extract_tables_with_details())
    except Exception:
        pass

    # Build the panel content
    lines = [
        "[bold cyan]TexGuardian[/bold cyan]",
        "",
        f"  Paper  [bold]{escape(display_title)}[/bold]",
    ]

    # Venue + deadline on same line
    venue_line = f"  Venue  {escape(venue)}"
    if deadline:
        venue_line += f"          Deadline  {escape(deadline)}"
    lines.append(venue_line)

    # Model + provider on same line
    model_line = f"  Model  {escape(session.config.models.default)}"
    model_line += f"       Provider  {escape(provider)}"
    lines.append(model_line)

    # File + figures/tables on same line
    file_line = f"  File   {escape(main_tex)}"
    stats_parts = []
    if fig_count:
        stats_parts.append(f"Figures {fig_count}")
    if table_count:
        stats_parts.append(f"Tables {table_count}")
    if stats_parts:
        sep = " \u00b7 "
        file_line += f"        {sep.join(stats_parts)}"
    lines.append(file_line)

    lines.append("")
    lines.append("  Type [cyan]/help[/cyan] for commands or ask a question.")

    console.print(Panel.fit(
        "\n".join(lines),
        border_style="cyan",
    ))


async def _handle_command(
    user_input: str,
    session: SessionState,
    registry: CommandRegistry,
    console: Console,
) -> None:
    """Handle a slash command."""
    # Parse command and args
    parts = user_input[1:].split(maxsplit=1)
    cmd_name = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # Look up command
    command = registry.get_command(cmd_name)
    if not command:
        console.print(f"[red]Unknown command: /{escape(cmd_name)}[/red]")
        console.print("Type [cyan]/help[/cyan] for available commands")
        return

    # Execute command
    try:
        await command.execute(session, args, console)
    except Exception as e:
        console.print(f"[red]Error executing /{escape(cmd_name)}: {e}[/red]")


async def _handle_chat(
    user_input: str,
    session: SessionState,
    console: Console,
) -> None:
    """Handle natural language chat input."""
    if not session.llm_client:
        console.print("[red]LLM client not initialized[/red]")
        console.print("[dim]Check your texguardian.yaml provider and credentials, then restart[/dim]")
        return

    # Add user message to context
    session.context.add_user_message(user_input)

    # Build system prompt
    system_prompt = build_chat_system_prompt(session)

    # Get messages for LLM
    messages = session.context.get_messages_for_llm()

    # Stream response inside a bordered panel using Rich Live display
    from rich.live import Live
    from rich.markdown import Markdown

    console.print()
    full_response: list[str] = []
    error_occurred = False

    max_tokens = session.llm_client.max_output_tokens

    if session.quiet:
        # Quiet mode: collect LLM output without streaming to the console
        with console.status("[dim]Generating response...[/dim]", spinner="dots"):
            try:
                async for chunk in session.llm_client.stream(
                    messages=messages,
                    system=system_prompt,
                    max_tokens=max_tokens,
                    temperature=0.7,
                ):
                    if chunk.content:
                        full_response.append(chunk.content)
            except Exception as e:
                error_occurred = True
                console.print(f"[red]Error: {e}[/red]")

        response_text = "".join(full_response)
        if response_text and not error_occurred:
            console.print(Panel(
                Markdown(response_text),
                border_style="dim",
                padding=(1, 2),
            ))
        console.print()
    else:
        # Normal mode: live-stream into a Rich panel
        live = Live(
            Panel(
                "[dim]Thinking...[/dim]",
                border_style="dim",
                padding=(0, 2),
            ),
            console=console,
            refresh_per_second=8,
            vertical_overflow="visible",
        )
        live.start()

        try:
            async for chunk in session.llm_client.stream(
                messages=messages,
                system=system_prompt,
                max_tokens=max_tokens,
                temperature=0.7,
            ):
                if chunk.content:
                    full_response.append(chunk.content)
                    text = "".join(full_response)
                    live.update(Panel(
                        text,
                        border_style="dim",
                        padding=(0, 2),
                    ))

        except Exception as e:
            error_occurred = True
            live.update(Panel(
                f"[red]Error: {e}[/red]\n"
                "[dim]This may be a network issue or API rate limit. Try again.[/dim]",
                border_style="red",
                padding=(0, 2),
            ))
        finally:
            # Final render with Markdown formatting for a polished look
            response_text = "".join(full_response)
            if response_text and not error_occurred:
                try:
                    live.update(Panel(
                        Markdown(response_text),
                        border_style="dim",
                        padding=(1, 2),
                    ))
                except Exception:
                    pass  # Keep the plain text panel if Markdown fails
            live.stop()

        # Breathing room after response panel
        console.print()
        console.print()

    # Add assistant response to context
    if response_text:
        session.context.add_assistant_message(response_text)

    # Smart context compaction - uses LLM when context gets large
    stats = session.context.get_context_stats()
    if stats["usage_percent"] > 70:
        console.print(f"[dim]Context: {stats['usage_percent']}% used, compacting...[/dim]")
        try:
            await session.context.smart_compact(session.llm_client)
        except Exception as e:
            console.print(f"[yellow]Context compaction failed: {e}[/yellow]")

    # Check for patches in response
    if response_text and "```diff" in response_text:
        await _offer_patch_application(response_text, session, console)


async def _offer_patch_application(
    response_text: str,
    session: SessionState,
    console: Console,
) -> None:
    """Offer to apply patches found in response with Claude Code-style approval."""
    from texguardian.patch.parser import extract_patches

    patches = extract_patches(response_text)
    if not patches:
        return

    from texguardian.cli.approval import interactive_approval
    await interactive_approval(patches, session, console)

"""Model configuration command."""

from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING

from texguardian.cli.commands.registry import Command
from texguardian.llm.factory import (
    create_llm_client,
    resolve_model,
    search_known_models,
)

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


MODEL_ACTION_PROMPT = """\
You are a model configuration assistant for TexGuardian.

The user wants to configure which LLM model to use. Based on their request, \
determine the model name and provider.

## Available Models

### OpenRouter
- claude opus 4.5 → anthropic/claude-opus-4.5
- claude opus 4 → anthropic/claude-opus-4
- claude sonnet 4.5 → anthropic/claude-sonnet-4.5
- claude sonnet 4 → anthropic/claude-sonnet-4
- gpt-4o → openai/gpt-4o
- Any model ID from openrouter.ai/models

### AWS Bedrock
- claude opus 4.5 → us.anthropic.claude-opus-4-5-*
- claude opus 4 → us.anthropic.claude-opus-4-*
- claude sonnet 4 → us.anthropic.claude-sonnet-4-*

## Current Configuration
- Model: {current_model}
- Vision model: {current_vision}
- Provider: {current_provider}

## User Request
{user_instruction}

## Task
1. Identify which model and provider the user wants.
2. Provide a brief explanation of your recommendation.
3. Include a JSON action block:

```json
{{"action": "set_model", "model": "<friendly model name>", "provider": "<bedrock|openrouter|null>"}}
```

Use `null` for provider if the user doesn't specify one (keep current).
If the request is unclear, explain what you need and do NOT include a JSON block.
"""


class ModelCommand(Command):
    """View or change the current model."""

    name = "model"
    description = "View or change the current LLM model"
    aliases = ["m"]

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute model command."""
        if not args:
            # Show current model
            console.print(f"Current model: [cyan]{session.config.models.default}[/cyan]")
            console.print(f"Vision model: [cyan]{session.config.models.vision}[/cyan]")
            console.print(f"Provider: [cyan]{session.config.providers.default}[/cyan]")
            console.print("\n[dim]Use /model set <model_name> to change[/dim]")
            console.print("[dim]Use /model search <query> to find models[/dim]")
            return

        parts = args.split(maxsplit=1)
        subcommand = parts[0].lower()

        if subcommand == "set":
            if len(parts) < 2:
                console.print("[red]Usage: /model set <model_name>[/red]")
                self._show_available_models(console)
                return

            new_model = parts[1].strip()
            await self._set_model(new_model, session, console)

        elif subcommand == "list":
            self._show_available_models(console)

        elif subcommand == "search":
            if len(parts) < 2:
                console.print("[red]Usage: /model search <query>[/red]")
                return
            await self._search_models(parts[1].strip(), session, console)

        else:
            # Natural language → LLM
            await self._handle_llm_request(args, session, console)

    async def _set_model(
        self,
        model_name: str,
        session: SessionState,
        console: Console,
    ) -> None:
        """Set a new model with resolution feedback.

        Supports provider switching via "on bedrock" / "on openrouter" suffix:
            /model set claude opus 4.5 on bedrock
            /model set gpt-4o on openrouter
        """
        # Extract "on <provider>" suffix if present
        provider_match = re.search(r'\s+on\s+(bedrock|openrouter)\s*$', model_name, re.IGNORECASE)
        provider_override = None
        if provider_match:
            provider_override = provider_match.group(1).lower()
            model_name = model_name[:provider_match.start()].strip()

        provider = provider_override or session.config.providers.default
        resolved = resolve_model(model_name, provider)

        old_model = session.config.models.default
        old_provider = session.config.providers.default

        # Store canonical name so /model shows the resolved name, not raw input
        canonical = resolved.friendly_name or model_name
        session.config.models.default = canonical
        if provider_override:
            session.config.providers.default = provider_override

        try:
            # Close old client
            if session.llm_client:
                await session.llm_client.close()

            # Create new client (will re-resolve canonical name → exact match)
            session.llm_client = create_llm_client(session.config)
            console.print(f"[green]Model set: {resolved.display}[/green]")
            if provider_override:
                console.print(f"[green]Provider: {provider_override}[/green]")

            # Persist to YAML config
            session.config.save(session.config_path)
            console.print("[dim]Saved to texguardian.yaml[/dim]")

        except Exception as e:
            # Revert on error
            session.config.models.default = old_model
            session.config.providers.default = old_provider
            console.print(f"[red]Error setting model: {e}[/red]")

    async def _search_models(
        self,
        query: str,
        session: SessionState,
        console: Console,
    ) -> None:
        """Search for models matching a query."""
        provider = session.config.providers.default

        # Search known models
        results = search_known_models(query, provider)

        if results:
            console.print(f"\n[bold]Known models matching '{query}':[/bold]")
            for friendly_name, provider_id, prov in results:
                console.print(f"  [cyan]{friendly_name}[/cyan] -> {provider_id} [dim]({prov})[/dim]")
        else:
            console.print(f"\n[dim]No known models matching '{query}'[/dim]")

        # Search OpenRouter API models if available
        if provider == "openrouter":
            api_key = (
                session.config.providers.openrouter.api_key
                or os.environ.get("OPENROUTER_API_KEY", "")
            )
            if api_key:
                from texguardian.llm.openrouter import fetch_available_models

                api_models = await fetch_available_models(
                    api_key=api_key,
                    base_url=session.config.providers.openrouter.base_url,
                )
                query_lower = query.lower()
                matches = [
                    m for m in api_models
                    if query_lower in m["id"].lower() or query_lower in m["name"].lower()
                ]
                if matches:
                    console.print(f"\n[bold]OpenRouter API models matching '{query}':[/bold]")
                    for m in matches[:20]:  # Limit output
                        console.print(f"  [cyan]{m['id']}[/cyan] - {m['name']}")
                    if len(matches) > 20:
                        console.print(f"  [dim]... and {len(matches) - 20} more[/dim]")

        if not results:
            console.print("\n[dim]Tip: You can use any model ID directly with /model set[/dim]")

    async def _handle_llm_request(
        self,
        user_input: str,
        session: SessionState,
        console: Console,
    ) -> None:
        """Use the LLM to interpret a natural-language model request."""
        if not session.llm_client:
            console.print("[red]LLM not initialized. Use: /model set <model_name>[/red]")
            return

        from texguardian.llm.streaming import stream_llm

        prompt = MODEL_ACTION_PROMPT.format(
            current_model=session.config.models.default,
            current_vision=session.config.models.vision,
            current_provider=session.config.providers.default,
            user_instruction=user_input,
        )

        response_text = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
            max_tokens=1500,
            temperature=0.3,
        )
        console.print()

        if session.context:
            session.context.add_assistant_message(response_text)

        action = self._extract_json_action(response_text)
        if not action or action.get("action") != "set_model":
            return

        model = action["model"]
        provider = action.get("provider")
        if provider == "null" or provider is None:
            provider = None

        # Approval
        from texguardian.cli.approval import action_approval

        details = [f"Model: [cyan]{model}[/cyan]"]
        if provider:
            details.append(f"Provider: [cyan]{provider}[/cyan]")
        else:
            details.append(
                f"Provider: [cyan]{session.config.providers.default}[/cyan] (unchanged)"
            )

        approved = await action_approval(
            f"Set Model to {model}" + (f" on {provider}" if provider else ""),
            details,
            console,
        )
        if not approved:
            console.print("[dim]Skipped[/dim]")
            return

        # Build the model string with provider suffix for _set_model
        model_str = model
        if provider:
            model_str = f"{model} on {provider}"
        await self._set_model(model_str, session, console)

    def _extract_json_action(self, text: str) -> dict | None:
        """Extract JSON action block from LLM response."""
        # Try ```json blocks first
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        # Fallback: outermost braces
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return None

    def _show_available_models(self, console: Console) -> None:
        """Show available models."""
        console.print("\nAvailable models:")
        console.print("\n[bold]OpenRouter:[/bold]")
        console.print("  claude opus 4.5     - anthropic/claude-opus-4.5")
        console.print("  claude opus 4       - anthropic/claude-opus-4")
        console.print("  claude sonnet 4.5   - anthropic/claude-sonnet-4.5")
        console.print("  claude sonnet 4     - anthropic/claude-sonnet-4")
        console.print("  claude-3.5-sonnet   - anthropic/claude-3.5-sonnet")
        console.print("  gpt-4o              - openai/gpt-4o")
        console.print("  [dim]Any model ID from openrouter.ai/models works directly[/dim]")

        console.print("\n[bold]Bedrock:[/bold]")
        console.print("  claude opus 4.5     - us.anthropic.claude-opus-4-5-*")
        console.print("  claude opus 4       - us.anthropic.claude-opus-4-*")
        console.print("  claude sonnet 4     - us.anthropic.claude-sonnet-4-*")
        console.print("  claude-3.5-sonnet   - us.anthropic.claude-3-5-sonnet-*")

        console.print("\n[dim]Fuzzy matching: 'opus 4.5', 'claude-sonnet-4' also work[/dim]")
        console.print("[dim]Provider switching: /model set claude opus 4.5 on bedrock[/dim]")
        console.print("[dim]Use /model search <query> to find models[/dim]")

    def get_completions(self, partial: str) -> list[str]:
        """Get model name completions."""
        models = [
            "claude opus 4.5",
            "claude opus 4",
            "claude sonnet 4.5",
            "claude sonnet 4",
            "claude-3.5-sonnet",
            "gpt-4o",
        ]

        if partial.startswith("set "):
            prefix = partial[4:]
            return [m for m in models if m.startswith(prefix.lower())]

        if partial.startswith("search "):
            return []

        return ["set", "list", "search"]

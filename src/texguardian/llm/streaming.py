"""Shared streaming helper for LLM commands.

Provides a single ``stream_llm`` coroutine that all CLI commands use
so the streaming-vs-fallback logic lives in one place.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.llm.base import LLMClient


async def stream_llm(
    client: LLMClient,
    messages: list[dict[str, str]],
    console: Console,
    *,
    system: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    print_output: bool = True,
) -> str:
    """Stream an LLM response, printing chunks live to *console*.

    Falls back to a single ``complete()`` call only when the client
    genuinely lacks a ``stream`` method (e.g. a lightweight mock).
    Real errors during streaming (network, API, etc.) are **not**
    swallowed — they propagate to the caller.

    Parameters
    ----------
    client:
        An ``LLMClient`` (or duck-typed equivalent).
    messages:
        The chat messages list.
    console:
        Rich console for live output.
    system:
        Optional system prompt.
    max_tokens:
        Max output tokens.
    temperature:
        Sampling temperature.
    print_output:
        Whether to print chunks to *console* as they arrive.

    Returns
    -------
    str
        The complete response text.
    """
    parts: list[str] = []

    # Build kwargs, omitting system when None to support simpler clients
    kwargs: dict = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system is not None:
        kwargs["system"] = system

    if hasattr(client, "stream"):
        first_token = True
        # Show a thinking indicator until first token arrives
        status = console.status("[dim]Thinking...", spinner="dots") if print_output else None
        if status:
            status.start()
        try:
            async for chunk in client.stream(**kwargs):
                if chunk.content:
                    if first_token:
                        if status:
                            status.stop()
                        first_token = False
                    if print_output:
                        console.print(chunk.content, end="", highlight=False)
                    parts.append(chunk.content)
        finally:
            # Always clean up spinner — covers both normal exit (no tokens)
            # and exception exit (mid-stream failure).
            if status:
                try:
                    status.stop()
                except Exception:
                    pass
    else:
        # Fallback for clients that only implement complete()
        with console.status("[dim]Generating...", spinner="dots"):
            response = await client.complete(**kwargs)
        parts.append(response.content)
        if print_output:
            console.print(response.content, highlight=False)

    return "".join(parts)

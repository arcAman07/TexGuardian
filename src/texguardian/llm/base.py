"""Base LLM client protocol and types."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class CompletionResponse:
    """Response from LLM completion."""

    content: str
    model: str
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class StreamChunk:
    """A single chunk from streaming response."""

    content: str
    is_final: bool = False
    finish_reason: str | None = None


@dataclass
class ImageContent:
    """Image content for vision models."""

    data: bytes
    media_type: str = "image/png"


@dataclass
class MessageContent:
    """Message content that can include text and images."""

    text: str | None = None
    images: list[ImageContent] = field(default_factory=list)


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    max_output_tokens: int = 32000

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResponse:
        """Send completion request to LLM."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion from LLM."""
        ...

    @abstractmethod
    async def complete_with_vision(
        self,
        messages: list[dict],
        images: list[ImageContent],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResponse:
        """Send completion request with images to vision model."""
        ...

    @abstractmethod
    def supports_vision(self) -> bool:
        """Check if this client supports vision capabilities."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close any open connections."""
        ...

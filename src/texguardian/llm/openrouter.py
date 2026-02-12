"""OpenRouter LLM client implementation."""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import AsyncIterator

import httpx

from texguardian.llm.base import (
    CompletionResponse,
    ImageContent,
    LLMClient,
    StreamChunk,
)
from texguardian.llm.retry import RetryConfig, retry_async

logger = logging.getLogger(__name__)

# In-memory cache for available models
_models_cache: list[dict[str, str]] | None = None
_models_cache_time: float = 0
_CACHE_TTL = 300  # 5 minutes


async def fetch_available_models(
    api_key: str,
    base_url: str = "https://openrouter.ai/api/v1",
) -> list[dict[str, str]]:
    """Fetch available models from OpenRouter API.

    Returns a list of dicts with 'id' and 'name' keys.
    Results are cached in memory for 5 minutes.
    """
    global _models_cache, _models_cache_time

    if _models_cache is not None and (time.time() - _models_cache_time) < _CACHE_TTL:
        return _models_cache

    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {api_key}",
            },
            timeout=30.0,
        ) as client:
            response = await client.get("/models")
            response.raise_for_status()
            data = response.json()

        models = [
            {"id": m["id"], "name": m.get("name", m["id"])}
            for m in data.get("data", [])
        ]
        _models_cache = models
        _models_cache_time = time.time()
        return models

    except Exception:
        logger.warning("Failed to fetch OpenRouter models list")
        return _models_cache or []


class OpenRouterClient(LLMClient):
    """OpenRouter API client."""

    def __init__(
        self,
        api_key: str,
        model: str = "anthropic/claude-sonnet-4",
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/texguardian/texguardian",
                "X-Title": "TexGuardian",
            },
            timeout=120.0,
        )

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResponse:
        """Send completion request to OpenRouter with retry logic."""
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async def _call() -> CompletionResponse:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            return CompletionResponse(
                content=data["choices"][0]["message"]["content"],
                model=data.get("model", self.model),
                finish_reason=data["choices"][0].get("finish_reason", "stop"),
                usage=data.get("usage", {}),
            )

        retry_config = RetryConfig(max_retries=3, base_delay=1.0)
        return await retry_async(_call, config=retry_config)

    async def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion from OpenRouter."""
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages, system),
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }

        async with self._client.stream(
            "POST", "/chat/completions", json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        yield StreamChunk(content="", is_final=True)
                        break

                    import json

                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        finish_reason = data["choices"][0].get("finish_reason")

                        yield StreamChunk(
                            content=content,
                            is_final=finish_reason is not None,
                            finish_reason=finish_reason,
                        )
                    except json.JSONDecodeError:
                        continue

    async def complete_with_vision(
        self,
        messages: list[dict],
        images: list[ImageContent],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResponse:
        """Send completion request with images with retry logic."""
        # Build messages with images
        vision_messages = []

        if system:
            vision_messages.append({"role": "system", "content": system})

        images_copy = list(images)  # Copy to avoid mutation issues with retry
        for msg in messages:
            if msg["role"] == "user" and images_copy:
                # Add images to user message
                content = [{"type": "text", "text": msg["content"]}]
                for img in images_copy:
                    b64_data = base64.b64encode(img.data).decode("utf-8")
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{img.media_type};base64,{b64_data}"
                            },
                        }
                    )
                vision_messages.append({"role": "user", "content": content})
                images_copy = []  # Clear after first use
            else:
                vision_messages.append(msg)

        payload = {
            "model": self.model,
            "messages": vision_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        async def _call() -> CompletionResponse:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            return CompletionResponse(
                content=data["choices"][0]["message"]["content"],
                model=data.get("model", self.model),
                finish_reason=data["choices"][0].get("finish_reason", "stop"),
                usage=data.get("usage", {}),
            )

        retry_config = RetryConfig(max_retries=3, base_delay=2.0)
        return await retry_async(_call, config=retry_config)

    def supports_vision(self) -> bool:
        """OpenRouter supports vision for compatible models."""
        # Claude models support vision
        vision_models = ["claude", "gpt-4", "gemini"]
        return any(m in self.model.lower() for m in vision_models)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    def _build_messages(
        self, messages: list[dict[str, str]], system: str | None
    ) -> list[dict[str, str]]:
        """Build messages list with optional system prompt."""
        result = []
        if system:
            result.append({"role": "system", "content": system})
        result.extend(messages)
        return result

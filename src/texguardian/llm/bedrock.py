"""AWS Bedrock LLM client implementation."""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import AsyncIterator

from texguardian.llm.base import (
    CompletionResponse,
    ImageContent,
    LLMClient,
    StreamChunk,
)
from texguardian.llm.retry import RetryConfig, retry_async

logger = logging.getLogger(__name__)

# Model ID mapping - supports both regional and cross-region inference
# Note: Claude 4.x models require cross-region inference profile IDs (us. prefix)
MODEL_MAPPING = {
    # Claude Opus 4.5 - latest (requires cross-region inference profile)
    "claude opus 4.5": "us.anthropic.claude-opus-4-5-20251101-v1:0",
    # Claude Opus 4 (requires cross-region inference profile)
    "claude opus 4": "us.anthropic.claude-opus-4-20250514-v1:0",
    # Claude Sonnet 4 (requires cross-region inference profile)
    "claude sonnet 4": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    # Claude 3.7 Sonnet
    "claude-3.7-sonnet": "us.anthropic.claude-3-7-sonnet-20250219-v1:0",
    # Claude 3.5 Sonnet v2
    "claude-3.5-sonnet-v2": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    # Claude 3.5 Sonnet v1
    "claude-3.5-sonnet": "anthropic.claude-3-5-sonnet-20240620-v1:0",
    # Claude 3.x models (legacy, direct model IDs still work)
    "claude-3-opus": "anthropic.claude-3-opus-20240229-v1:0",
    "claude-3-sonnet": "anthropic.claude-3-sonnet-20240229-v1:0",
    "claude-3-haiku": "anthropic.claude-3-haiku-20240307-v1:0",
}

# Default token limits
DEFAULT_MAX_OUTPUT_TOKENS = int(os.environ.get("TEXGUARDIAN_MAX_OUTPUT_TOKENS", "32000"))
DEFAULT_MAX_THINKING_TOKENS = int(os.environ.get("TEXGUARDIAN_MAX_THINKING_TOKENS", "16000"))


class BedrockClient(LLMClient):
    """AWS Bedrock client for Claude models with extended token support."""

    def __init__(
        self,
        model: str = "us.anthropic.claude-opus-4-5-20251101-v1:0",
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        profile: str | None = None,
        max_output_tokens: int | None = None,
        max_thinking_tokens: int | None = None,
    ):
        import boto3

        self.model_name = model
        self.model_id = model  # Factory resolves model name before passing here
        self.max_output_tokens = max_output_tokens or DEFAULT_MAX_OUTPUT_TOKENS
        self.max_thinking_tokens = max_thinking_tokens or DEFAULT_MAX_THINKING_TOKENS

        # Configure longer timeout for large model calls (vision, long analysis)
        from botocore.config import Config
        bedrock_config = Config(
            read_timeout=900,  # 15 minutes for large requests (vision with many pages)
            connect_timeout=120,
            retries={'max_attempts': 3}
        )

        # Create boto3 session with explicit credentials
        # When credentials are provided, we need to bypass boto3's default credential chain
        # which picks up AWS_PROFILE from environment
        if access_key_id and secret_access_key:
            # Temporarily unset AWS_PROFILE to prevent boto3 from using it
            # during both session AND client creation (boto3 reads env in both)
            old_profile = os.environ.pop("AWS_PROFILE", None)
            try:
                session = boto3.Session(
                    aws_access_key_id=access_key_id,
                    aws_secret_access_key=secret_access_key,
                    region_name=region,
                )
                self._client = session.client(
                    "bedrock-runtime",
                    region_name=region,
                    config=bedrock_config,
                )
            finally:
                if old_profile:
                    os.environ["AWS_PROFILE"] = old_profile
        elif profile:
            session = boto3.Session(profile_name=profile)
            self._client = session.client(
                "bedrock-runtime",
                region_name=region,
                config=bedrock_config,
            )
        else:
            session = boto3.Session()
            self._client = session.client(
                "bedrock-runtime",
                region_name=region,
                config=bedrock_config,
            )

    async def complete(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResponse:
        """Send completion request to Bedrock with retry logic."""
        import asyncio

        async def _call() -> CompletionResponse:
            return await asyncio.to_thread(
                self._complete_sync, messages, system, max_tokens, temperature
            )

        # Use retry with exponential backoff
        retry_config = RetryConfig(max_retries=3, base_delay=1.0)
        return await retry_async(_call, config=retry_config)

    def _complete_sync(
        self,
        messages: list[dict[str, str]],
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> CompletionResponse:
        """Synchronous completion for Bedrock."""
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._convert_messages(messages),
        }

        if system:
            body["system"] = system

        response = self._client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())

        return CompletionResponse(
            content=result["content"][0]["text"],
            model=self.model_id,
            finish_reason=result.get("stop_reason", "end_turn"),
            usage={
                "input_tokens": result.get("usage", {}).get("input_tokens", 0),
                "output_tokens": result.get("usage", {}).get("output_tokens", 0),
            },
        )

    async def stream(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> AsyncIterator[StreamChunk]:
        """Stream completion from Bedrock."""
        import asyncio

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": self._convert_messages(messages),
        }

        if system:
            body["system"] = system

        # Run streaming in thread
        response = await asyncio.to_thread(
            self._client.invoke_model_with_response_stream,
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        for event in response["body"]:
            chunk = json.loads(event["chunk"]["bytes"])

            if chunk["type"] == "content_block_delta":
                delta = chunk.get("delta", {})
                text = delta.get("text", "")
                yield StreamChunk(content=text)

            elif chunk["type"] == "message_stop":
                yield StreamChunk(content="", is_final=True, finish_reason="end_turn")

    async def complete_with_vision(
        self,
        messages: list[dict],
        images: list[ImageContent],
        system: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> CompletionResponse:
        """Send completion request with images to Bedrock with retry logic."""
        import asyncio

        async def _call() -> CompletionResponse:
            return await asyncio.to_thread(
                self._complete_vision_sync, messages, images, system, max_tokens, temperature
            )

        # Use retry with exponential backoff (longer delays for vision)
        retry_config = RetryConfig(max_retries=3, base_delay=2.0)
        return await retry_async(_call, config=retry_config)

    def _complete_vision_sync(
        self,
        messages: list[dict],
        images: list[ImageContent],
        system: str | None,
        max_tokens: int,
        temperature: float,
    ) -> CompletionResponse:
        """Synchronous vision completion."""
        # Convert messages and add images
        converted = []

        for msg in messages:
            if msg["role"] == "user" and images:
                # Build content with images
                content = []
                for img in images:
                    b64_data = base64.b64encode(img.data).decode("utf-8")
                    content.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": img.media_type,
                                "data": b64_data,
                            },
                        }
                    )
                content.append({"type": "text", "text": msg["content"]})
                converted.append({"role": "user", "content": content})
                images = []  # Clear after first use
            else:
                converted.append(self._convert_message(msg))

        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": converted,
        }

        if system:
            body["system"] = system

        response = self._client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )

        result = json.loads(response["body"].read())

        return CompletionResponse(
            content=result["content"][0]["text"],
            model=self.model_id,
            finish_reason=result.get("stop_reason", "end_turn"),
            usage={
                "input_tokens": result.get("usage", {}).get("input_tokens", 0),
                "output_tokens": result.get("usage", {}).get("output_tokens", 0),
            },
        )

    def supports_vision(self) -> bool:
        """Bedrock Claude models support vision."""
        return True

    async def close(self) -> None:
        """Close client (no-op for boto3)."""
        pass

    def _convert_messages(self, messages: list[dict[str, str]]) -> list[dict]:
        """Convert messages to Bedrock format."""
        return [self._convert_message(m) for m in messages]

    def _convert_message(self, msg: dict[str, str]) -> dict:
        """Convert a single message to Bedrock format."""
        return {
            "role": msg["role"],
            "content": [{"type": "text", "text": msg["content"]}],
        }

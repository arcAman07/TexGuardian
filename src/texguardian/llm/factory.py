"""LLM client factory with smart model resolution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from texguardian.config.settings import TexGuardianConfig
from texguardian.llm.base import LLMClient
from texguardian.llm.bedrock import MODEL_MAPPING as BEDROCK_MODELS
from texguardian.llm.bedrock import BedrockClient
from texguardian.llm.openrouter import OpenRouterClient

# Friendly name -> provider-specific model ID
OPENROUTER_MODELS: dict[str, str] = {
    # Claude 4.x
    "claude opus 4.5": "anthropic/claude-opus-4.5",
    "claude opus 4": "anthropic/claude-opus-4",
    "claude sonnet 4.5": "anthropic/claude-sonnet-4.5",
    "claude sonnet 4": "anthropic/claude-sonnet-4",
    # Claude 3.x
    "claude-3.5-sonnet": "anthropic/claude-3.5-sonnet",
    "claude-3-opus": "anthropic/claude-3-opus",
    "claude-3-sonnet": "anthropic/claude-3-sonnet",
    "claude-3-haiku": "anthropic/claude-3-haiku",
    # OpenAI
    "gpt-4o": "openai/gpt-4o",
    "gpt-4-turbo": "openai/gpt-4-turbo",
}


def _normalize(s: str) -> str:
    """Normalize for fuzzy comparison: strip separators but keep version dots.

    Dots between two digits (e.g. 4.5) are preserved so that
    "claude opus 4.5" and "claude opus 45" remain distinguishable.
    All other separators (spaces, dashes, non-version dots) are removed.
    """
    s = s.lower()
    # Protect dots between digits (version numbers like 3.5, 4.5)
    s = re.sub(r"(?<=\d)\.(?=\d)", "\x00", s)
    # Strip all remaining separators
    s = re.sub(r"[\s\-\.]+", "", s)
    # Restore protected version dots
    return s.replace("\x00", ".")


@dataclass
class ResolvedModel:
    """Result of model resolution."""

    friendly_name: str | None  # The known friendly name, or None for raw IDs
    provider_id: str  # The provider-specific model ID
    raw_input: str  # What the user originally typed

    @property
    def display(self) -> str:
        """Human-readable display string."""
        if self.friendly_name and self.friendly_name.lower() != self.raw_input.lower():
            return f"{self.raw_input} -> {self.friendly_name} ({self.provider_id})"
        elif self.friendly_name:
            return f"{self.friendly_name} ({self.provider_id})"
        else:
            return self.provider_id


def resolve_model(model: str, provider: str) -> ResolvedModel:
    """Resolve a user-typed model name to a provider-specific model ID.

    Resolution order:
    1. Exact match against known mappings (case-insensitive)
    2. Normalized fuzzy match (strip spaces/dashes/dots, lowercase)
    3. Raw provider ID pass-through (contains '/' or provider prefix)
    4. Fallback: return as-is (provider API will validate)
    """
    mappings = _get_mappings(provider)
    model_stripped = model.strip()
    model_lower = model_stripped.lower()

    # 1. Exact match (case-insensitive)
    if model_lower in mappings:
        return ResolvedModel(
            friendly_name=model_lower,
            provider_id=mappings[model_lower],
            raw_input=model_stripped,
        )

    # 2. Normalized fuzzy match (exact normalized string comparison)
    normalized_input = _normalize(model_stripped)
    for friendly_name, provider_id in mappings.items():
        if _normalize(friendly_name) == normalized_input:
            return ResolvedModel(
                friendly_name=friendly_name,
                provider_id=provider_id,
                raw_input=model_stripped,
            )

    # 2b. Substring/suffix match — e.g. "opus 4.5" matches "claude opus 4.5"
    if len(normalized_input) >= 5:  # Avoid overly short/ambiguous matches
        candidates = [
            (fn, pid)
            for fn, pid in mappings.items()
            if normalized_input in _normalize(fn)
        ]
        if len(candidates) == 1:
            fn, pid = candidates[0]
            return ResolvedModel(
                friendly_name=fn, provider_id=pid, raw_input=model_stripped,
            )
        elif len(candidates) > 1:
            # Prefer suffix match to disambiguate
            suffix = [
                (fn, pid)
                for fn, pid in candidates
                if _normalize(fn).endswith(normalized_input)
            ]
            if len(suffix) == 1:
                fn, pid = suffix[0]
                return ResolvedModel(
                    friendly_name=fn, provider_id=pid, raw_input=model_stripped,
                )

    # 3. Raw provider ID pass-through
    if _is_raw_provider_id(model_stripped, provider):
        return ResolvedModel(
            friendly_name=None,
            provider_id=model_stripped,
            raw_input=model_stripped,
        )

    # 4. Fallback — return as-is
    return ResolvedModel(
        friendly_name=None,
        provider_id=model_stripped,
        raw_input=model_stripped,
    )


def _get_mappings(provider: str) -> dict[str, str]:
    """Get the model name mappings for a provider."""
    if provider == "openrouter":
        return OPENROUTER_MODELS
    elif provider == "bedrock":
        return BEDROCK_MODELS
    return {}


def _is_raw_provider_id(model: str, provider: str) -> bool:
    """Check if the input looks like a raw provider model ID."""
    # OpenRouter format: "org/model-name"
    if "/" in model:
        return True
    # Bedrock format: "anthropic.claude-*" or "us.anthropic.claude-*"
    if provider == "bedrock" and (
        model.startswith("anthropic.") or model.startswith("us.")
    ):
        return True
    return False


def search_known_models(query: str, provider: str | None = None) -> list[tuple[str, str, str]]:
    """Search known models by query string.

    Returns list of (friendly_name, provider_id, provider) tuples.
    """
    results: list[tuple[str, str, str]] = []
    query_norm = _normalize(query)

    providers_to_search: list[tuple[str, dict[str, str]]] = []
    if provider is None or provider == "openrouter":
        providers_to_search.append(("openrouter", OPENROUTER_MODELS))
    if provider is None or provider == "bedrock":
        providers_to_search.append(("bedrock", BEDROCK_MODELS))

    for prov_name, mappings in providers_to_search:
        for friendly_name, provider_id in mappings.items():
            if (
                query_norm in _normalize(friendly_name)
                or query_norm in _normalize(provider_id)
            ):
                results.append((friendly_name, provider_id, prov_name))

    return results


def create_llm_client(
    config: TexGuardianConfig,
    model_override: str | None = None,
) -> LLMClient:
    """Create LLM client based on configuration.

    Credentials can come from:
    1. texguardian.yaml config
    2. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, etc.)
    3. AWS profile (~/.aws/credentials)
    """
    provider = config.providers.default
    model = model_override or config.models.default

    # Resolve model name for all providers
    resolved = resolve_model(model, provider)

    if provider == "openrouter":
        # Get API key from config or environment
        api_key = config.providers.openrouter.api_key or os.environ.get("OPENROUTER_API_KEY", "")

        if not api_key:
            raise ValueError(
                "OpenRouter API key not configured. "
                "Set OPENROUTER_API_KEY environment variable or add to texguardian.yaml"
            )

        return OpenRouterClient(
            api_key=api_key,
            model=resolved.provider_id,
            base_url=config.providers.openrouter.base_url,
        )

    elif provider == "bedrock":
        bedrock_config = config.providers.bedrock

        # Get credentials from config or environment
        access_key_id = (
            bedrock_config.access_key_id
            or os.environ.get("AWS_ACCESS_KEY_ID")
        )
        secret_access_key = (
            bedrock_config.secret_access_key
            or os.environ.get("AWS_SECRET_ACCESS_KEY")
        )
        region = (
            bedrock_config.region
            or os.environ.get("AWS_REGION", "us-east-1")
        )

        # Only use profile if explicit credentials not provided
        # This prevents AWS_PROFILE env var from overriding our credentials
        profile = None
        if not (access_key_id and secret_access_key):
            profile = (
                bedrock_config.profile
                or os.environ.get("AWS_PROFILE")
            )

        # Get token limits from environment
        max_output_tokens = int(os.environ.get("TEXGUARDIAN_MAX_OUTPUT_TOKENS", "32000"))
        max_thinking_tokens = int(os.environ.get("TEXGUARDIAN_MAX_THINKING_TOKENS", "16000"))

        return BedrockClient(
            model=resolved.provider_id,
            region=region,
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            profile=profile,
            max_output_tokens=max_output_tokens,
            max_thinking_tokens=max_thinking_tokens,
        )

    else:
        raise ValueError(f"Unknown provider: {provider}")


def create_vision_client(config: TexGuardianConfig) -> LLMClient:
    """Create LLM client specifically for vision tasks."""
    return create_llm_client(config, model_override=config.models.vision)

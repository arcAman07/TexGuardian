"""Conversation context management with token-aware compaction."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from texguardian.llm.base import LLMClient


class MessageRole(StrEnum):
    """Message role in conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Message:
    """A single message in the conversation."""

    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    token_count: int = 0  # Estimated token count

    def to_dict(self) -> dict[str, str]:
        """Convert to dict for LLM API."""
        return {"role": self.role.value, "content": self.content}

    def estimate_tokens(self) -> int:
        """Estimate token count (rough: ~4 chars per token)."""
        if self.token_count > 0:
            return self.token_count
        self.token_count = len(self.content) // 4 + 1
        return self.token_count


# Default context limits
DEFAULT_MAX_CONTEXT_TOKENS = int(os.environ.get("TEXGUARDIAN_MAX_CONTEXT_TOKENS", "100000"))
DEFAULT_SUMMARY_THRESHOLD = int(os.environ.get("TEXGUARDIAN_SUMMARY_THRESHOLD", "80000"))


@dataclass
class ConversationContext:
    """Manages conversation history with token-aware compaction.

    Features:
    - Token counting to prevent context overflow
    - Automatic summarization when context gets large
    - Preserves recent messages while compacting old ones
    """

    messages: list[Message] = field(default_factory=list)
    max_context_tokens: int = DEFAULT_MAX_CONTEXT_TOKENS
    summary_threshold: int = DEFAULT_SUMMARY_THRESHOLD
    max_messages: int = 100  # Hard limit on message count
    _summary: str | None = None  # Summarized old context
    _total_tokens: int = 0

    def add_user_message(self, content: str, **metadata: Any) -> None:
        """Add a user message."""
        msg = Message(role=MessageRole.USER, content=content, metadata=metadata)
        msg.estimate_tokens()
        self.messages.append(msg)
        self._total_tokens += msg.token_count
        self._check_compaction()

    def add_assistant_message(self, content: str, **metadata: Any) -> None:
        """Add an assistant message."""
        msg = Message(role=MessageRole.ASSISTANT, content=content, metadata=metadata)
        msg.estimate_tokens()
        self.messages.append(msg)
        self._total_tokens += msg.token_count
        self._check_compaction()

    def add_system_message(self, content: str, **metadata: Any) -> None:
        """Add a system message."""
        msg = Message(role=MessageRole.SYSTEM, content=content, metadata=metadata)
        msg.estimate_tokens()
        self.messages.append(msg)
        self._total_tokens += msg.token_count
        self._check_compaction()

    def get_messages_for_llm(self) -> list[dict[str, str]]:
        """Get messages formatted for LLM API."""
        return [msg.to_dict() for msg in self.messages]

    def get_summary(self) -> str | None:
        """Get the conversation summary for inclusion in system prompt."""
        return self._summary

    def get_total_tokens(self) -> int:
        """Get estimated total token count."""
        return self._total_tokens + (len(self._summary) // 4 if self._summary else 0)

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        self._summary = None
        self._total_tokens = 0

    def _check_compaction(self) -> None:
        """Check if context needs compaction and perform it if needed.

        Only performs count-based compaction synchronously.
        Token-based compaction is handled by smart_compact() which uses
        LLM summarization for higher quality results.
        """
        if len(self.messages) > self.max_messages:
            self._compact_by_count()

    def _compact_by_count(self) -> None:
        """Compact by removing oldest messages."""
        # Keep the most recent half
        keep_count = self.max_messages // 2
        removed = self.messages[:-keep_count]
        self.messages = self.messages[-keep_count:]

        # Update token count
        removed_tokens = sum(m.estimate_tokens() for m in removed)
        self._total_tokens -= removed_tokens

        # Create simple summary of removed messages
        if removed:
            topics = self._extract_topics(removed)
            if topics:
                self._summary = f"Earlier discussion covered: {', '.join(topics)}"

    def _compact_by_tokens(self) -> None:
        """Compact to reduce token count."""
        # Calculate how many tokens to remove
        target_tokens = self.summary_threshold // 2

        # Find split point
        running_total = 0
        split_idx = 0
        for i, msg in enumerate(self.messages):
            running_total += msg.estimate_tokens()
            if running_total > (self._total_tokens - target_tokens):
                split_idx = i
                break

        if split_idx > 0:
            # Extract messages to summarize
            to_summarize = self.messages[:split_idx]
            self.messages = self.messages[split_idx:]

            # Update token count
            removed_tokens = sum(m.estimate_tokens() for m in to_summarize)
            self._total_tokens -= removed_tokens

            # Create summary
            topics = self._extract_topics(to_summarize)
            if topics:
                new_summary = f"Earlier discussion covered: {', '.join(topics)}"
                if self._summary:
                    self._summary = f"{self._summary}; {new_summary}"
                else:
                    self._summary = new_summary

    def _extract_topics(self, messages: list[Message]) -> list[str]:
        """Extract key topics from messages for summary."""
        topics = []

        for msg in messages:
            content = msg.content.lower()

            # Extract mentioned files
            if ".tex" in content:
                topics.append("LaTeX files")
            if ".bib" in content:
                topics.append("bibliography")
            if "figure" in content:
                topics.append("figures")
            if "table" in content:
                topics.append("tables")
            if "citation" in content:
                topics.append("citations")
            if "overflow" in content:
                topics.append("overflow issues")
            if "compile" in content:
                topics.append("compilation")
            if "error" in content:
                topics.append("errors")

        # Deduplicate while preserving order
        seen = set()
        unique_topics = []
        for t in topics:
            if t not in seen:
                seen.add(t)
                unique_topics.append(t)

        return unique_topics[:5]  # Limit to 5 topics

    def get_last_assistant_message(self) -> str | None:
        """Get the last assistant message content."""
        for msg in reversed(self.messages):
            if msg.role == MessageRole.ASSISTANT:
                return msg.content
        return None

    async def summarize_with_llm(self, llm_client: LLMClient) -> None:
        """Use LLM to create a proper summary of conversation history.

        This is more accurate than topic extraction but uses API tokens.
        Called automatically when context gets large.
        """
        if len(self.messages) < 10:
            return  # Not enough to summarize

        # Take first half of messages
        to_summarize = self.messages[:len(self.messages) // 2]

        # Build prompt
        conversation_text = "\n".join(
            f"{m.role.value}: {m.content[:500]}..."
            if len(m.content) > 500 else f"{m.role.value}: {m.content}"
            for m in to_summarize
        )

        prompt = f"""Summarize this conversation in 2-3 sentences, focusing on:
- What LaTeX issues were discussed
- What files were mentioned
- What was resolved or still pending

Conversation:
{conversation_text}

Summary:"""

        try:
            response = await llm_client.complete(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )

            # Update summary and remove summarized messages
            self._summary = response.content.strip()
            removed_tokens = sum(m.estimate_tokens() for m in to_summarize)
            self.messages = self.messages[len(to_summarize):]
            self._total_tokens -= removed_tokens

        except Exception:
            # Fall back to topic extraction
            self._compact_by_tokens()

    async def smart_compact(self, llm_client: LLMClient | None = None) -> None:
        """Smart context compaction - uses LLM if available, otherwise topic extraction.

        This provides Claude Code-like context management:
        1. Tracks total tokens in conversation
        2. When threshold reached, summarizes old messages
        3. Preserves recent context while compacting history
        """
        if self._total_tokens < self.summary_threshold:
            return  # No compaction needed

        if llm_client:
            # Use LLM for higher quality summarization
            await self.summarize_with_llm(llm_client)
        else:
            # Fall back to topic extraction
            self._compact_by_tokens()

    def get_context_stats(self) -> dict:
        """Get statistics about the current context state."""
        return {
            "message_count": len(self.messages),
            "total_tokens": self._total_tokens,
            "max_tokens": self.max_context_tokens,
            "summary_threshold": self.summary_threshold,
            "has_summary": self._summary is not None,
            "summary_preview": self._summary[:100] + "..." if self._summary and len(self._summary) > 100 else self._summary,
            "usage_percent": round(self._total_tokens / self.max_context_tokens * 100, 1),
        }

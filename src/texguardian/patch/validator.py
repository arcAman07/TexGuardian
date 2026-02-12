"""Patch validation with safety checks."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from texguardian.config.settings import SafetyConfig
    from texguardian.patch.parser import Patch


@dataclass
class ValidationResult:
    """Result of patch validation."""

    valid: bool
    reason: str = ""
    requires_human_review: bool = False
    review_reasons: list[str] = field(default_factory=list)


class PatchValidator:
    """Validates patches against safety rules."""

    def __init__(self, safety_config: SafetyConfig):
        self.config = safety_config

    def validate(self, patch: Patch, target_path: Path) -> ValidationResult:
        """Validate a patch against safety rules."""
        # Check file path against allowlist
        if not self._is_allowed(patch.file_path):
            return ValidationResult(
                valid=False,
                reason=f"File not in allowlist: {patch.file_path}",
            )

        # Check file path against denylist
        if self._is_denied(patch.file_path):
            return ValidationResult(
                valid=False,
                reason=f"File in denylist: {patch.file_path}",
            )

        # Check max changed lines
        if patch.lines_changed > self.config.max_changed_lines:
            return ValidationResult(
                valid=False,
                reason=f"Too many lines changed ({patch.lines_changed} > {self.config.max_changed_lines})",
            )

        # Check for human review triggers
        review_reasons = self._check_human_review_triggers(patch, target_path)

        return ValidationResult(
            valid=True,
            requires_human_review=bool(review_reasons),
            review_reasons=review_reasons,
        )

    def _is_allowed(self, file_path: str) -> bool:
        """Check if file matches allowlist."""
        for pattern in self.config.allowlist:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False

    def _is_denied(self, file_path: str) -> bool:
        """Check if file matches denylist."""
        for pattern in self.config.denylist:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        return False

    def _check_human_review_triggers(
        self,
        patch: Patch,
        target_path: Path,
    ) -> list[str]:
        """Check if patch triggers human review."""
        reasons = []

        # Count deletions
        deletion_count = sum(
            1
            for hunk in patch.hunks
            for line in hunk.lines
            if line.startswith("-")
        )

        if deletion_count > 10:
            reasons.append(f"Large deletion ({deletion_count} lines)")

        # Check for sensitive patterns
        sensitive_patterns = [
            "abstract",
            "\\title",
            "\\author",
            "\\maketitle",
        ]

        raw_lower = patch.raw_diff.lower()
        for pattern in sensitive_patterns:
            if pattern.lower() in raw_lower:
                reasons.append(f"Modifies sensitive content: {pattern}")

        return reasons

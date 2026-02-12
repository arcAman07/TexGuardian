"""Safety guard implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from texguardian.core.session import SessionState


@dataclass
class SafetyCheckResult:
    """Result of a safety check."""

    allowed: bool
    reason: str = ""
    requires_approval: bool = False


class SafetyGuards:
    """Collection of safety checks for auto-fix operations."""

    def __init__(self, session: SessionState):
        self.session = session

    def check_max_rounds(self, current_round: int) -> SafetyCheckResult:
        """Check if max rounds limit reached."""
        max_rounds = self.session.config.safety.max_rounds

        if current_round >= max_rounds:
            return SafetyCheckResult(
                allowed=False,
                reason=f"Max rounds ({max_rounds}) reached",
            )

        return SafetyCheckResult(allowed=True)

    def check_quality_regression(self) -> SafetyCheckResult:
        """Check for consecutive quality regressions."""
        if self.session.should_stop_auto_fix():
            return SafetyCheckResult(
                allowed=False,
                reason="Quality regressed twice consecutively",
            )

        return SafetyCheckResult(allowed=True)

    def check_human_review_required(
        self,
        change_description: str,
    ) -> SafetyCheckResult:
        """Check if change requires human review."""
        paper_spec = self.session.paper_spec

        if not paper_spec or not paper_spec.human_review:
            return SafetyCheckResult(allowed=True)

        description_lower = change_description.lower()

        for trigger in paper_spec.human_review:
            trigger_lower = trigger.lower()

            if trigger_lower in description_lower:
                return SafetyCheckResult(
                    allowed=True,
                    requires_approval=True,
                    reason=f"Matches human review trigger: {trigger}",
                )

        return SafetyCheckResult(allowed=True)

    def check_deletion_size(self, lines_deleted: int) -> SafetyCheckResult:
        """Check if deletion is within limits."""
        # From paper_spec human_review triggers
        paper_spec = self.session.paper_spec

        if paper_spec and paper_spec.human_review:
            for trigger in paper_spec.human_review:
                if "deletion" in trigger.lower():
                    # Try to extract number
                    import re

                    match = re.search(r"(\d+)", trigger)
                    if match:
                        max_delete = int(match.group(1))
                        if lines_deleted > max_delete:
                            return SafetyCheckResult(
                                allowed=True,
                                requires_approval=True,
                                reason=f"Large deletion ({lines_deleted} lines)",
                            )

        return SafetyCheckResult(allowed=True)

    def check_all(
        self,
        current_round: int = 0,
        change_description: str = "",
        lines_deleted: int = 0,
    ) -> SafetyCheckResult:
        """Run all safety checks."""
        checks = [
            self.check_max_rounds(current_round),
            self.check_quality_regression(),
            self.check_human_review_required(change_description),
            self.check_deletion_size(lines_deleted),
        ]

        for check in checks:
            if not check.allowed:
                return check

        # Aggregate requires_approval
        requires_approval = any(c.requires_approval for c in checks)
        approval_reasons = [c.reason for c in checks if c.requires_approval]

        return SafetyCheckResult(
            allowed=True,
            requires_approval=requires_approval,
            reason="; ".join(approval_reasons) if approval_reasons else "",
        )

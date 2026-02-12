"""Session state management."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from texguardian.config.paper_spec import PaperSpec
from texguardian.config.settings import TexGuardianConfig

if TYPE_CHECKING:
    from texguardian.checkpoint.manager import CheckpointManager
    from texguardian.core.context import ConversationContext
    from texguardian.llm.base import LLMClient


@dataclass
class CompilationResult:
    """Result of a LaTeX compilation."""

    success: bool
    pdf_path: Path | None = None
    log_output: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_count: int | None = None  # None = unknown, 0 = genuinely zero pages


@dataclass
class VerificationResult:
    """Result of a verification check."""

    name: str
    passed: bool
    severity: str  # error, warning, info
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class SessionState:
    """Holds all state for a TexGuardian session."""

    # Paths
    project_root: Path
    config_path: Path

    # Configuration
    config: TexGuardianConfig
    paper_spec: PaperSpec | None = None

    # Runtime state
    llm_client: LLMClient | None = None
    context: ConversationContext | None = None
    checkpoint_manager: CheckpointManager | None = None

    # Compilation state
    last_compilation: CompilationResult | None = None

    # Watch mode
    watch_enabled: bool = False

    # Quality tracking for auto-fix
    quality_scores: list[int] = field(default_factory=list)
    consecutive_regressions: int = 0

    @property
    def last_pdf_path(self) -> Path | None:
        """Get the PDF path from the last successful compilation."""
        if self.last_compilation and self.last_compilation.pdf_path:
            return self.last_compilation.pdf_path
        return None

    @property
    def main_tex_path(self) -> Path:
        """Get full path to main .tex file."""
        return self.project_root / self.config.project.main_tex

    @property
    def output_dir(self) -> Path:
        """Get full path to output directory."""
        return self.project_root / self.config.project.output_dir

    @property
    def guardian_dir(self) -> Path:
        """Get .texguardian directory path."""
        return self.project_root / ".texguardian"

    def track_quality(self, score: int) -> None:
        """Track quality score and detect regressions."""
        if self.quality_scores and score < self.quality_scores[-1]:
            self.consecutive_regressions += 1
        else:
            self.consecutive_regressions = 0
        self.quality_scores.append(score)

    def should_stop_auto_fix(self) -> bool:
        """Check if auto-fix should stop due to regressions."""
        return self.consecutive_regressions >= 2

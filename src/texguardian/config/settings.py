"""Configuration settings and texguardian.yaml loader."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class OpenRouterConfig(BaseModel):
    """OpenRouter provider configuration."""

    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"


class BedrockConfig(BaseModel):
    """AWS Bedrock provider configuration."""

    region: str = "us-east-1"
    access_key_id: str = ""
    secret_access_key: str = ""
    profile: str | None = None


class ProvidersConfig(BaseModel):
    """LLM provider configurations."""

    default: str = "bedrock"  # Default to bedrock (AWS)
    openrouter: OpenRouterConfig = Field(default_factory=OpenRouterConfig)
    bedrock: BedrockConfig = Field(default_factory=BedrockConfig)


class ModelsConfig(BaseModel):
    """Model selection configuration."""

    default: str = "claude opus 4.5"
    vision: str = "claude opus 4.5"


class SafetyConfig(BaseModel):
    """Safety guard configuration."""

    max_changed_lines: int = 50
    max_rounds: int = 10
    max_visual_rounds: int = 5
    allowlist: list[str] = Field(default_factory=lambda: ["*.tex", "*.bib", "*.sty", "*.cls"])
    denylist: list[str] = Field(default_factory=lambda: [".git/**", "*.pdf", "build/**"])


class LatexConfig(BaseModel):
    """LaTeX compilation configuration."""

    compiler: str = "latexmk"
    engine: str = "pdflatex"
    shell_escape: bool = False
    timeout: int = 240  # seconds


class VisualConfig(BaseModel):
    """Visual verification configuration."""

    dpi: int = 150
    diff_threshold: float = 5.0  # Percentage for convergence
    pixel_threshold: int = 15  # Per-pixel intensity difference (0-255)
    max_pages_to_analyze: int = 0  # 0 = analyze all pages


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    main_tex: str = "main.tex"
    output_dir: str = "build"


class TexGuardianConfig(BaseModel):
    """Root configuration model for texguardian.yaml."""

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    latex: LatexConfig = Field(default_factory=LatexConfig)
    visual: VisualConfig = Field(default_factory=VisualConfig)

    @classmethod
    def load(cls, path: Path) -> TexGuardianConfig:
        """Load configuration from YAML file."""
        if not path.exists():
            return cls()

        with open(path) as f:
            data = yaml.safe_load(f) or {}

        # Expand environment variables in the config
        data = _expand_env_vars(data)
        return cls.model_validate(data)

    def save(self, path: Path) -> None:
        """Save configuration to YAML file."""
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False, sort_keys=False)


def _expand_env_vars(obj: Any) -> Any:
    """Recursively expand ${VAR} patterns in strings."""
    if isinstance(obj, str):
        # Match ${VAR} or $VAR patterns
        pattern = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)")

        def replace(match: re.Match[str]) -> str:
            var_name = match.group(1) or match.group(2)
            return os.environ.get(var_name, match.group(0))

        return pattern.sub(replace, obj)
    elif isinstance(obj, dict):
        return {k: _expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_expand_env_vars(item) for item in obj]
    return obj


CONFIG_FILENAME = "texguardian.yaml"
SPEC_FILENAME = "paper_spec.md"
GUARDIAN_DIR = ".texguardian"


def find_config_path(start_dir: Path | None = None) -> Path | None:
    """Find texguardian.yaml by walking up directory tree."""
    current = start_dir or Path.cwd()

    while current != current.parent:
        config_path = current / CONFIG_FILENAME
        if config_path.exists():
            return config_path
        current = current.parent

    return None


def get_project_root(config_path: Path) -> Path:
    """Get project root directory from config path."""
    return config_path.parent

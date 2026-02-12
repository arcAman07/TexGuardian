"""Paper specification parser for paper_spec.md."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Check:
    """A verification check from paper_spec.md."""

    name: str
    severity: str = "warning"  # error, warning, info
    pattern: str | None = None
    message: str = ""


@dataclass
class Thresholds:
    """Paper thresholds from paper_spec.md."""

    max_pages: int = 9
    min_references: int = 30
    max_self_citation_ratio: float = 0.2


@dataclass
class PaperSpec:
    """Parsed paper specification."""

    title: str = "Untitled Paper"
    venue: str = "Unknown"
    deadline: str | None = None
    thresholds: Thresholds = field(default_factory=Thresholds)
    human_review: list[str] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    system_prompt: str | None = None

    @classmethod
    def load(cls, path: Path) -> PaperSpec:
        """Load and parse paper_spec.md file."""
        if not path.exists():
            return cls()

        content = path.read_text()
        return cls.parse(content)

    @classmethod
    def parse(cls, content: str) -> PaperSpec:
        """Parse paper_spec.md content."""
        spec = cls()

        # Parse YAML frontmatter
        frontmatter = _extract_frontmatter(content)
        if frontmatter:
            spec.title = frontmatter.get("title", spec.title)
            spec.venue = frontmatter.get("venue", spec.venue)
            spec.deadline = frontmatter.get("deadline")

            if "thresholds" in frontmatter:
                t = frontmatter["thresholds"]
                spec.thresholds = Thresholds(
                    max_pages=t.get("max_pages", spec.thresholds.max_pages),
                    min_references=t.get("min_references", spec.thresholds.min_references),
                    max_self_citation_ratio=t.get(
                        "max_self_citation_ratio", spec.thresholds.max_self_citation_ratio
                    ),
                )

            if "human_review" in frontmatter:
                spec.human_review = frontmatter["human_review"]

        # Parse check blocks
        spec.checks = _extract_checks(content)

        # Parse system prompt block
        spec.system_prompt = _extract_system_prompt(content)

        return spec


def _extract_frontmatter(content: str) -> dict[str, Any] | None:
    """Extract YAML frontmatter from markdown content."""
    import yaml

    # Match content between --- markers at the start
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, content, re.DOTALL)

    if match:
        try:
            return yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            return None
    return None


def _extract_checks(content: str) -> list[Check]:
    """Extract check blocks from markdown content."""
    checks = []

    # Match ```check ... ``` blocks
    pattern = r"```check\s*\n(.*?)\n```"
    matches = re.finditer(pattern, content, re.DOTALL)

    for match in matches:
        check_content = match.group(1)
        check = _parse_check_block(check_content)
        if check:
            checks.append(check)

    return checks


def _unescape_quoted(s: str) -> str:
    """Unescape a quoted string value from paper_spec.md.

    Patterns in paper_spec.md are written inside double quotes using
    backslash escaping: ``\\\\`` represents a literal backslash,
    ``\\\\.`` represents ``\\.`` (regex literal dot), etc.
    This removes one escaping level so the string can be used as a regex.
    """
    # Replace every pair of backslashes with a single backslash.
    # E.g. file \\. → regex \.  (literal dot)
    #      file \\\\\\\\ → regex \\  (literal backslash)
    return s.replace("\\\\", "\\")


def _parse_check_block(content: str) -> Check | None:
    """Parse a single check block."""
    lines = content.strip().split("\n")
    data: dict[str, str] = {}

    for line in lines:
        if ":" in line:
            key, value = line.split(":", 1)
            raw = value.strip()
            if raw.startswith('"') and raw.endswith('"'):
                data[key.strip()] = _unescape_quoted(raw[1:-1])
            else:
                data[key.strip()] = raw

    if "name" not in data:
        return None

    return Check(
        name=data["name"],
        severity=data.get("severity", "warning"),
        pattern=data.get("pattern"),
        message=data.get("message", ""),
    )


def _extract_system_prompt(content: str) -> str | None:
    """Extract system prompt from ```system-prompt fenced block."""
    pattern = r"```system-prompt\s*\n(.*?)\n```"
    match = re.search(pattern, content, re.DOTALL)

    if match:
        prompt = match.group(1).strip()
        return prompt if prompt else None
    return None

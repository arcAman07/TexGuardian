"""Unified diff patch parser."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Hunk:
    """A single hunk within a patch."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)


@dataclass
class Patch:
    """A parsed unified diff patch."""

    file_path: str
    hunks: list[Hunk] = field(default_factory=list)
    raw_diff: str = ""

    @property
    def lines_changed(self) -> int:
        """Count of lines added or removed."""
        return self.additions + self.deletions

    @property
    def additions(self) -> int:
        """Count of lines added."""
        count = 0
        for hunk in self.hunks:
            for line in hunk.lines:
                if line.startswith("+") and not line.startswith("+++"):
                    count += 1
        return count

    @property
    def deletions(self) -> int:
        """Count of lines removed."""
        count = 0
        for hunk in self.hunks:
            for line in hunk.lines:
                if line.startswith("-") and not line.startswith("---"):
                    count += 1
        return count


def extract_patches(text: str) -> list[Patch]:
    """Extract unified diff patches from text."""
    patches = []
    seen_diffs = set()

    # Find diff blocks in markdown code blocks
    diff_pattern = r"```diff\s*\n(.*?)\n```"
    matches = re.finditer(diff_pattern, text, re.DOTALL)

    for match in matches:
        diff_text = match.group(1)
        # Normalize for deduplication
        normalized = diff_text.strip()
        if normalized in seen_diffs:
            continue
        seen_diffs.add(normalized)

        patch = parse_patch(diff_text)
        if patch:
            patches.append(patch)

    # Also try to find raw diffs (not in code blocks) - skip if we already found patches
    # This prevents duplicates when the same diff appears both in and outside code blocks
    if not patches:
        raw_diff_pattern = r"^---\s+a/(.+)\n\+\+\+\s+b/(.+)\n((?:@@.*@@.*\n(?:[ +-].*\n)*)+)"
        for match in re.finditer(raw_diff_pattern, text, re.MULTILINE):
            diff_text = match.group(0)
            patch = parse_patch(diff_text)
            if patch:
                patches.append(patch)

    return patches


def parse_patch(diff_text: str) -> Patch | None:
    """Parse a single unified diff into a Patch."""
    lines = diff_text.strip().split("\n")

    if len(lines) < 3:
        return None

    # Find file paths
    file_path = None
    for line in lines[:4]:
        if line.startswith("---"):
            # Extract path from --- a/path or --- path
            match = re.match(r"---\s+(?:a/)?(.+)", line)
            if match:
                file_path = match.group(1).strip()
        elif line.startswith("+++"):
            # Prefer +++ path if --- didn't give us one
            if not file_path:
                match = re.match(r"\+\+\+\s+(?:b/)?(.+)", line)
                if match:
                    file_path = match.group(1).strip()

    if not file_path:
        return None

    patch = Patch(file_path=file_path, raw_diff=diff_text)

    # Parse hunks
    current_hunk = None
    hunk_header_pattern = r"@@\s*-(\d+)(?:,(\d+))?\s*\+(\d+)(?:,(\d+))?\s*@@"

    for line in lines:
        # Check for hunk header
        match = re.match(hunk_header_pattern, line)
        if match:
            if current_hunk:
                patch.hunks.append(current_hunk)

            current_hunk = Hunk(
                old_start=int(match.group(1)),
                old_count=int(match.group(2) or 1),
                new_start=int(match.group(3)),
                new_count=int(match.group(4) or 1),
            )
        elif current_hunk is not None:
            # Add line to current hunk
            if line.startswith((" ", "+", "-")):
                current_hunk.lines.append(line)

    if current_hunk:
        patch.hunks.append(current_hunk)

    return patch if patch.hunks else None

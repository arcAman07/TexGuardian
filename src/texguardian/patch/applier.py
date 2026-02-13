"""Patch application."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from texguardian.patch.parser import Patch

logger = logging.getLogger(__name__)


class PatchApplier:
    """Applies unified diff patches to files."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    def apply(self, patch: Patch) -> bool:
        """Apply a patch to its target file."""
        target_path = self.project_root / patch.file_path

        if not target_path.exists():
            # Create new file
            return self._apply_to_new_file(patch, target_path)

        # Read current content
        current_lines = target_path.read_text().splitlines(keepends=True)

        # Apply each hunk
        offset = 0
        for i, hunk in enumerate(patch.hunks):
            result = self._apply_hunk(current_lines, hunk, offset)
            if result is None:
                logger.warning(
                    "Hunk %d failed for %s (old_start=%d, old_count=%d, lines=%d)",
                    i, patch.file_path, hunk.old_start, hunk.old_count, len(hunk.lines),
                )
                return False
            current_lines, offset = result

        # Write result
        target_path.write_text("".join(current_lines))
        return True

    def _apply_hunk(
        self,
        lines: list[str],
        hunk,
        offset: int,
    ) -> tuple[list[str], int] | None:
        """Apply a single hunk to lines."""
        # Calculate actual position with offset
        pos = hunk.old_start - 1 + offset

        # Build the new content from hunk lines
        new_lines = []
        old_lines_count = 0  # context + removed = lines consumed from original
        new_lines_added = 0
        old_lines_removed = 0

        for line in hunk.lines:
            if line.startswith(" "):
                # Context line - keep as is
                new_lines.append(line[1:] + "\n" if not line[1:].endswith("\n") else line[1:])
                old_lines_count += 1
            elif line.startswith("-"):
                # Removed line - don't add to new content
                old_lines_count += 1
                old_lines_removed += 1
            elif line.startswith("+"):
                # Added line
                content = line[1:]
                if not content.endswith("\n"):
                    content += "\n"
                new_lines.append(content)
                new_lines_added += 1

        # Try to find the right position using multiple strategies
        found_pos = self._find_hunk_position(lines, hunk, pos)
        if found_pos is not None:
            pos = found_pos
        else:
            return None

        # Use actual line count from hunk content (not the header)
        end_pos = pos + old_lines_count
        if end_pos > len(lines):
            end_pos = len(lines)

        result = lines[:pos] + new_lines + lines[end_pos:]

        # Update offset
        new_offset = offset + (new_lines_added - old_lines_removed)

        return result, new_offset

    @staticmethod
    def _normalize(s: str) -> str:
        """Normalize a line for comparison.

        Strips trailing whitespace, collapses internal runs, and removes
        line-number prefixes (``  39| ``) that LLMs sometimes copy from
        numbered content.
        """
        # Strip line-number prefix if present (e.g. "  39| content")
        s = re.sub(r"^\s*\d+\|\s?", "", s)
        return " ".join(s.split())

    def _find_hunk_position(self, lines: list[str], hunk, expected_pos: int) -> int | None:
        """Find the correct position for a hunk using multiple strategies.

        Strategy 1: Exact position with context verification
        Strategy 2: Nearby search (±30 lines) with context verification
        Strategy 3: Search entire file for the removed lines (content-based)
        """
        # Strategy 1: Try the expected position
        if self._verify_context(lines, expected_pos, hunk):
            return expected_pos

        # Strategy 2: Search nearby
        window = 30
        for delta in range(-window, window + 1):
            pos = expected_pos + delta
            if pos < 0 or delta == 0:
                continue
            if self._verify_context(lines, pos, hunk):
                return pos

        # Strategy 3: Find removed/context lines anywhere in the file
        match_pos = self._find_by_content(lines, hunk)
        if match_pos is not None:
            return match_pos

        return None

    def _verify_context(self, lines: list[str], pos: int, hunk) -> bool:
        """Verify that context and removed lines match (whitespace-tolerant)."""
        if pos < 0:
            return False
        line_idx = pos

        for hunk_line in hunk.lines:
            if hunk_line.startswith(" "):
                # Context line should match
                if line_idx >= len(lines):
                    return False
                expected = self._normalize(hunk_line[1:])
                actual = self._normalize(lines[line_idx])
                if expected != actual:
                    return False
                line_idx += 1
            elif hunk_line.startswith("-"):
                # Removed line should be present
                if line_idx >= len(lines):
                    return False
                expected = self._normalize(hunk_line[1:])
                actual = self._normalize(lines[line_idx])
                if expected != actual:
                    return False
                line_idx += 1

        return True

    def _find_by_content(self, lines: list[str], hunk) -> int | None:
        """Search the entire file for the sequence of context+removed lines.

        This is the fallback when the line numbers from the LLM are wrong.
        We extract all non-'+' lines from the hunk and search for them
        sequentially in the file.
        """
        # Build the sequence of lines we expect to find (context + removed)
        expected_sequence: list[str] = []
        for hunk_line in hunk.lines:
            if hunk_line.startswith(" ") or hunk_line.startswith("-"):
                expected_sequence.append(self._normalize(hunk_line[1:]))

        if not expected_sequence:
            return None

        # Search for this sequence anywhere in the file
        file_len = len(lines)
        seq_len = len(expected_sequence)

        for start in range(file_len - seq_len + 1):
            match = True
            for j, expected in enumerate(expected_sequence):
                actual = self._normalize(lines[start + j])
                if expected != actual:
                    match = False
                    break
            if match:
                return start

        # Last resort: try matching with just the first removed line
        removed_lines = [
            self._normalize(hl[1:])
            for hl in hunk.lines
            if hl.startswith("-")
        ]
        if removed_lines:
            target = removed_lines[0]
            for i, line in enumerate(lines):
                if self._normalize(line) == target:
                    # Found the first removed line — walk back to find
                    # where context lines before it start
                    context_before = []
                    for hl in hunk.lines:
                        if hl.startswith(" "):
                            context_before.append(self._normalize(hl[1:]))
                        else:
                            break
                    candidate = i - len(context_before)
                    if candidate >= 0 and self._verify_context(lines, candidate, hunk):
                        return candidate
                    # If no context before, just use this position
                    if not context_before:
                        return i

        return None

    def _apply_to_new_file(self, patch: Patch, target_path: Path) -> bool:
        """Apply patch to create a new file."""
        new_lines = []

        for hunk in patch.hunks:
            for line in hunk.lines:
                if line.startswith("+"):
                    content = line[1:]
                    if not content.endswith("\n"):
                        content += "\n"
                    new_lines.append(content)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("".join(new_lines))
        return True

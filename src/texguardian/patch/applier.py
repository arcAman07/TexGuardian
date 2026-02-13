"""Patch application."""

from __future__ import annotations

from pathlib import Path

from texguardian.patch.parser import Patch


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
        for hunk in patch.hunks:
            result = self._apply_hunk(current_lines, hunk, offset)
            if result is None:
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

        # Build the new content
        new_lines = []
        old_lines_removed = 0
        new_lines_added = 0

        for line in hunk.lines:
            if line.startswith(" "):
                # Context line - keep as is
                new_lines.append(line[1:] + "\n" if not line[1:].endswith("\n") else line[1:])
            elif line.startswith("-"):
                # Removed line - don't add to new content
                old_lines_removed += 1
            elif line.startswith("+"):
                # Added line
                content = line[1:]
                if not content.endswith("\n"):
                    content += "\n"
                new_lines.append(content)
                new_lines_added += 1

        # Replace the old content with new
        # First, verify context matches (fuzzy)
        if not self._verify_context(lines, pos, hunk):
            # Try to find matching context nearby
            new_pos = self._find_context(lines, hunk, pos)
            if new_pos is not None:
                pos = new_pos
            else:
                return None

        # Remove old lines and insert new
        end_pos = pos + hunk.old_count
        result = lines[:pos] + new_lines + lines[end_pos:]

        # Update offset
        new_offset = offset + (new_lines_added - old_lines_removed)

        return result, new_offset

    @staticmethod
    def _normalize(s: str) -> str:
        """Normalize a line for comparison: strip trailing whitespace, collapse internal runs."""
        return " ".join(s.split())

    def _verify_context(self, lines: list[str], pos: int, hunk) -> bool:
        """Verify that context lines match (whitespace-tolerant)."""
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

    def _find_context(self, lines: list[str], hunk, start_pos: int) -> int | None:
        """Try to find matching context nearby."""
        # Look within a window around expected position
        window = 30

        for offset in range(-window, window + 1):
            pos = start_pos + offset
            if pos < 0:
                continue
            if self._verify_context(lines, pos, hunk):
                return pos

        return None

    def _apply_to_new_file(self, patch: Patch, target_path: Path) -> bool:
        """Apply patch to create a new file."""
        lines = []

        for hunk in patch.hunks:
            for line in hunk.lines:
                if line.startswith("+"):
                    content = line[1:]
                    if not content.endswith("\n"):
                        content += "\n"
                    lines.append(content)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("".join(lines))
        return True

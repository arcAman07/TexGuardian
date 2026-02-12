"""File allowlist and denylist management."""

from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from texguardian.config.settings import SafetyConfig


class FileAccessControl:
    """Controls file access based on allowlist/denylist."""

    def __init__(self, safety_config: SafetyConfig, project_root: Path):
        self.config = safety_config
        self.project_root = project_root

    def can_read(self, path: Path) -> bool:
        """Check if file can be read."""
        # Allow reading if not explicitly denied
        return not self._is_denied(path)

    def can_write(self, path: Path) -> bool:
        """Check if file can be written."""
        # Must be in allowlist and not in denylist
        return self._is_allowed(path) and not self._is_denied(path)

    def can_modify(self, path: Path) -> bool:
        """Check if file can be modified (same as write)."""
        return self.can_write(path)

    def _is_allowed(self, path: Path) -> bool:
        """Check if path matches any allowlist pattern."""
        try:
            rel_path = str(path.relative_to(self.project_root))
        except ValueError:
            # Path is outside project root
            return False

        for pattern in self.config.allowlist:
            if fnmatch.fnmatch(rel_path, pattern):
                return True
            # Also check just the filename
            if fnmatch.fnmatch(path.name, pattern):
                return True

        return False

    def _is_denied(self, path: Path) -> bool:
        """Check if path matches any denylist pattern."""
        try:
            rel_path = str(path.relative_to(self.project_root))
        except ValueError:
            # Path is outside project root - deny by default
            return True

        for pattern in self.config.denylist:
            # Handle ** patterns (recursive match)
            if "**" in pattern:
                # Convert ** to work with fnmatch
                base_pattern = pattern.replace("/**", "").replace("**", "")
                if rel_path.startswith(base_pattern) or f"/{rel_path}".startswith(f"/{base_pattern}"):
                    return True
            elif fnmatch.fnmatch(rel_path, pattern):
                return True
            # Also check just the filename
            elif fnmatch.fnmatch(path.name, pattern):
                return True

        return False

    def filter_paths(self, paths: list[Path], mode: str = "read") -> list[Path]:
        """Filter paths to only those accessible in given mode."""
        check_fn = {
            "read": self.can_read,
            "write": self.can_write,
            "modify": self.can_modify,
        }.get(mode, self.can_read)

        return [p for p in paths if check_fn(p)]

    def get_allowed_extensions(self) -> list[str]:
        """Get list of allowed file extensions from allowlist."""
        extensions = []

        for pattern in self.config.allowlist:
            if pattern.startswith("*."):
                extensions.append(pattern[1:])  # Remove *

        return extensions

    def get_denied_directories(self) -> list[str]:
        """Get list of denied directory patterns."""
        dirs = []

        for pattern in self.config.denylist:
            if pattern.endswith("/**"):
                dirs.append(pattern[:-3])  # Remove /**

        return dirs

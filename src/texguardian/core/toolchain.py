"""Centralized tool discovery for LaTeX and Poppler binaries.

Replaces scattered path lists in compiler.py, renderer.py, main.py,
and page_count.py with a single discovery mechanism.
"""

from __future__ import annotations

import glob
import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Search-path helpers
# ---------------------------------------------------------------------------

def _latex_search_paths() -> list[str]:
    """Build list of directories that may contain LaTeX binaries.

    Uses ``glob`` for TeX Live year directories so new releases are found
    automatically (newest first).
    """
    paths: list[str] = []

    # Honour explicit env-var override first
    env_path = os.environ.get("LATEX_PATH", "")
    if env_path:
        paths.append(env_path)

    # MacTeX stable symlink
    paths.append("/Library/TeX/texbin")
    paths.append("/usr/texbin")

    # TeX Live year-versioned installs — glob and sort newest-first
    system = platform.system()
    machine = platform.machine()

    if system == "Darwin":
        arch_suffix = "universal-darwin"
        tl_glob = f"/usr/local/texlive/*/bin/{arch_suffix}"
    elif system == "Linux":
        arch_suffix = f"{machine}-linux" if machine else "x86_64-linux"
        tl_glob = f"/usr/local/texlive/*/bin/{arch_suffix}"
    else:
        tl_glob = ""

    if tl_glob:
        # sorted() descending so e.g. 2025 comes before 2024
        paths.extend(sorted(glob.glob(tl_glob), reverse=True))

    # TinyTeX
    if system == "Darwin":
        paths.append(str(Path.home() / "Library/TinyTeX/bin/universal-darwin"))
    else:
        paths.append(str(Path.home() / ".TinyTeX/bin/x86_64-linux"))

    # System paths
    paths.extend(["/usr/bin", "/usr/local/bin"])

    return paths


def _poppler_search_paths() -> list[str]:
    """Build list of directories that may contain Poppler binaries."""
    paths: list[str] = []

    system = platform.system()
    machine = platform.machine()

    # Homebrew — only /opt/homebrew on ARM Mac
    if system == "Darwin":
        if machine == "arm64":
            paths.append("/opt/homebrew/bin")
        paths.append("/usr/local/bin")
    else:
        paths.extend(["/usr/bin", "/usr/local/bin"])

    return paths


# ---------------------------------------------------------------------------
# Binary discovery
# ---------------------------------------------------------------------------

def find_binary(name: str, category: str = "latex") -> str | None:
    """Find a binary by *name* in the standard ``$PATH`` then in
    category-specific search directories.

    Parameters
    ----------
    name:
        Executable name, e.g. ``"latexmk"``, ``"pdfinfo"``.
    category:
        ``"latex"`` or ``"poppler"`` — selects which extra directories to
        search.

    Returns
    -------
    Absolute path to the binary, or ``None`` if not found.
    """
    # Fast path — already on $PATH
    found = shutil.which(name)
    if found:
        return found

    # Category-specific directories
    if category == "latex":
        search_dirs = _latex_search_paths()
    elif category == "poppler":
        search_dirs = _poppler_search_paths()
    else:
        search_dirs = []

    for directory in search_dirs:
        binary = Path(directory) / name
        if binary.exists():
            return str(binary)

    return None


# ---------------------------------------------------------------------------
# Install hints
# ---------------------------------------------------------------------------

def get_install_hint(tool_name: str) -> str:
    """Return platform-specific install instructions for *tool_name*."""
    system = platform.system()

    hints: dict[str, dict[str, str]] = {
        "latexmk": {
            "Darwin": "brew install --cask mactex-no-gui   # or: brew install --cask mactex",
            "Linux": "sudo apt install texlive-full   # or: sudo dnf install texlive-scheme-full",
        },
        "pdflatex": {
            "Darwin": "brew install --cask mactex-no-gui",
            "Linux": "sudo apt install texlive-latex-base",
        },
        "pdfinfo": {
            "Darwin": "brew install poppler",
            "Linux": "sudo apt install poppler-utils",
        },
        "pdftoppm": {
            "Darwin": "brew install poppler",
            "Linux": "sudo apt install poppler-utils",
        },
    }

    tool_hints = hints.get(tool_name, {})
    hint = tool_hints.get(system, tool_hints.get("Linux", ""))

    if hint:
        return f"Install {tool_name}: {hint}"
    return f"{tool_name} not found. Please install it and ensure it is on your PATH."


# ---------------------------------------------------------------------------
# Toolchain status
# ---------------------------------------------------------------------------

@dataclass
class ToolStatus:
    """Status of a single external tool."""

    name: str
    category: str
    path: str | None
    found: bool


@dataclass
class ToolchainStatus:
    """Aggregated status of all required external tools."""

    tools: list[ToolStatus] = field(default_factory=list)

    @property
    def all_found(self) -> bool:
        return all(t.found for t in self.tools)

    @property
    def missing(self) -> list[ToolStatus]:
        return [t for t in self.tools if not t.found]


def check_tool(name: str, category: str = "latex") -> ToolStatus:
    """Check whether *name* is available."""
    path = find_binary(name, category)
    return ToolStatus(name=name, category=category, path=path, found=path is not None)


_REQUIRED_TOOLS: list[tuple[str, str]] = [
    ("latexmk", "latex"),
    ("pdflatex", "latex"),
    ("pdfinfo", "poppler"),
    ("pdftoppm", "poppler"),
]


def check_toolchain() -> ToolchainStatus:
    """Check all required external tools and return their status."""
    status = ToolchainStatus()
    for name, category in _REQUIRED_TOOLS:
        status.tools.append(check_tool(name, category))
    return status


# ---------------------------------------------------------------------------
# PATH manipulation
# ---------------------------------------------------------------------------

def ensure_latex_on_path() -> None:
    """Add discovered LaTeX directories to ``$PATH`` if not already present.

    Intended to be called once at startup (replaces the hard-coded list
    formerly in ``main.py:_load_env()``).
    """
    current_path = os.environ.get("PATH", "")
    added: list[str] = []

    for directory in _latex_search_paths():
        if directory and directory not in current_path and Path(directory).exists():
            added.append(directory)

    if added:
        os.environ["PATH"] = os.pathsep.join(added) + os.pathsep + current_path

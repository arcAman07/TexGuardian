"""LaTeX compiler wrapper."""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from texguardian.core.toolchain import find_binary, get_install_hint

if TYPE_CHECKING:
    from texguardian.config.settings import TexGuardianConfig
    from texguardian.core.session import CompilationResult

# TeX wraps .log lines at this column width.  We use it to unwrap before
# running regex patterns against the log.
_TEX_LOG_LINE_WIDTH = 79


def _unwrap_log_lines(log: str) -> str:
    """Rejoin lines that TeX broke at the 79-column boundary.

    TeX hard-wraps its ``.log`` output at 79 characters.  A long warning like
    ``LaTeX Warning: Reference `fig:very-long-name' ...`` may be split across
    two (or more) lines.  We detect lines that are *exactly* 79 characters
    (before the newline) and concatenate them with the following line.
    """
    lines = log.split("\n")
    merged: list[str] = []
    i = 0
    while i < len(lines):
        current = lines[i]
        # Keep appending while the line is exactly 79 chars (TeX wrap point)
        while len(current) >= _TEX_LOG_LINE_WIDTH and i + 1 < len(lines):
            i += 1
            current += lines[i]
        merged.append(current)
        i += 1
    return "\n".join(merged)


class LatexCompiler:
    """Wrapper for latexmk compilation."""

    def __init__(self, config: TexGuardianConfig):
        self.config = config

    async def clean(self, main_tex: Path, output_dir: Path) -> None:
        """Run ``latexmk -C`` to remove build artifacts."""
        compiler = find_binary(self.config.latex.compiler, "latex")
        if not compiler:
            return
        cmd = [
            compiler,
            "-C",
            f"-output-directory={output_dir}",
            main_tex.name,
        ]
        try:
            await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                cwd=main_tex.parent,
                timeout=30,
            )
        except Exception:
            pass

    async def compile(
        self,
        main_tex: Path,
        output_dir: Path,
    ) -> CompilationResult:
        """Compile LaTeX document."""
        from texguardian.core.session import CompilationResult

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)

        # Find compiler binary
        compiler = find_binary(self.config.latex.compiler, "latex")
        if not compiler:
            hint = get_install_hint(self.config.latex.compiler)
            return CompilationResult(
                success=False,
                log_output="Compiler not found",
                errors=[f"Compiler '{self.config.latex.compiler}' not found. {hint}"],
            )

        # Build command
        engine_flag = {
            "pdflatex": "-pdf",
            "xelatex": "-xelatex",
            "lualatex": "-lualatex",
        }.get(self.config.latex.engine, "-pdf")

        # Use relative paths for latexmk (cwd will be main_tex.parent)
        relative_output = output_dir.relative_to(main_tex.parent) if output_dir.is_relative_to(main_tex.parent) else output_dir

        cmd = [
            compiler,
            engine_flag,
            "-interaction=nonstopmode",
            "-halt-on-error",
            f"-output-directory={relative_output}",
        ]

        # Add --shell-escape if configured
        if getattr(self.config.latex, "shell_escape", False):
            cmd.append("--shell-escape")

        cmd.append(main_tex.name)  # Just the filename since cwd is set

        # Set up environment with LaTeX paths
        env = os.environ.copy()
        latex_bin_dir = str(Path(compiler).parent)
        if latex_bin_dir not in env.get("PATH", ""):
            env["PATH"] = f"{latex_bin_dir}{os.pathsep}{env.get('PATH', '')}"

        # Read configurable timeout
        timeout = getattr(self.config.latex, "timeout", 120)

        # Run compilation
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                cwd=main_tex.parent,
                env=env,
                timeout=timeout,
            )

            log_output = result.stdout + result.stderr

            # Detect stale latexmk state: "error in previous invocation"
            # means latexmk refused to re-run the engine.  Clean and retry.
            if (
                result.returncode != 0
                and "error in previous invocation" in log_output
            ):
                await self.clean(main_tex, output_dir)
                result = await asyncio.to_thread(
                    subprocess.run,
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=main_tex.parent,
                    env=env,
                    timeout=timeout,
                )
                log_output = result.stdout + result.stderr

            errors = self._extract_errors(log_output)
            warnings = self._extract_warnings(log_output)

            # Fallback: if stdout/stderr had no parseable errors but the
            # compilation failed, read the .log file directly — it always
            # contains the full pdflatex output.
            if not errors and result.returncode != 0:
                log_file = output_dir / (main_tex.stem + ".log")
                if log_file.exists():
                    log_text = log_file.read_text(errors="replace")
                    errors = self._extract_errors(log_text)
                    if not warnings:
                        warnings = self._extract_warnings(log_text)

            # Last resort: if we still have no parseable errors but the
            # process returned non-zero, synthesize an error from the raw
            # output so the user is never shown "compilation failed" with
            # an empty error list.
            if not errors and result.returncode != 0:
                errors = self._fallback_errors(log_output, result.returncode)

            # Check for PDF
            pdf_name = main_tex.stem + ".pdf"
            pdf_path = output_dir / pdf_name

            success = result.returncode == 0 and pdf_path.exists()

            # Get page count
            page_count: int | None = None
            if success and pdf_path.exists():
                page_count = await self._get_page_count(pdf_path)

            return CompilationResult(
                success=success,
                pdf_path=pdf_path if success else None,
                log_output=log_output,
                errors=errors,
                warnings=warnings,
                page_count=page_count,
            )

        except subprocess.TimeoutExpired:
            return CompilationResult(
                success=False,
                log_output="Compilation timed out",
                errors=[f"Compilation timed out after {timeout} seconds"],
            )
        except Exception as e:
            return CompilationResult(
                success=False,
                log_output=str(e),
                errors=[str(e)],
            )

    def _extract_errors(self, log: str) -> list[str]:
        """Extract error messages from log.

        Pairs ``! Error text`` lines with their following ``l.NNN`` location
        line into a single error entry so the user sees both the error
        description and the source location together.
        """
        unwrapped = _unwrap_log_lines(log)
        lines = unwrapped.split("\n")
        errors: list[str] = []

        i = 0
        while i < len(lines):
            line = lines[i]

            # "! ..." errors — look ahead for the "l.NNN" location line
            if re.match(r"^! (.+)$", line):
                entry = line.strip()
                # Scan ahead (up to 5 lines) for the location
                for j in range(i + 1, min(i + 6, len(lines))):
                    loc_match = re.match(r"^l\.(\d+) (.*)$", lines[j])
                    if loc_match:
                        entry = f"{entry}  [l.{loc_match.group(1)}]"
                        i = j  # skip past the location line
                        break
                errors.append(entry)
            elif re.match(r"^LaTeX Error: (.+)$", line):
                errors.append(line.strip())
            elif re.match(r"^Package (\w+) Error: (.+)$", line):
                errors.append(line.strip())
            i += 1

        return errors[:20]  # Limit to first 20

    @staticmethod
    def _fallback_errors(log_output: str, returncode: int) -> list[str]:
        """Synthesize error messages when ``_extract_errors`` finds nothing.

        Scans the raw log output for lines that look like errors (containing
        keywords like "error", "fatal", "not found", "missing") and returns
        up to 10 of them.  If even that yields nothing, returns a generic
        message with the exit code.
        """
        error_keywords = re.compile(
            r"(?:error|fatal|not found|missing|undefined|"
            r"emergency stop|no such file|cannot \\(read|open))",
            re.IGNORECASE,
        )
        fallback: list[str] = []
        for line in log_output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if error_keywords.search(stripped):
                # Skip noisy "see the transcript" / "output written" lines
                if "see the transcript" in stripped.lower():
                    continue
                fallback.append(stripped)
                if len(fallback) >= 10:
                    break

        if fallback:
            return fallback

        # Absolute last resort — show the last 5 non-empty lines
        tail = [
            ln.strip()
            for ln in log_output.splitlines()
            if ln.strip()
        ][-5:]
        if tail:
            return [
                f"Compilation failed (exit code {returncode}). Last output lines:",
                *tail,
            ]

        return [f"Compilation failed with exit code {returncode} (no log output captured)"]

    def _extract_warnings(self, log: str) -> list[str]:
        """Extract warning messages from log.

        Returns important warnings (LaTeX/Package) first, followed by box
        warnings, so the 20-item cap doesn't let box noise drown out real
        issues.
        """
        unwrapped = _unwrap_log_lines(log)

        important: list[str] = []
        box_warnings: list[str] = []

        important_patterns = [
            r"^LaTeX Warning: (.+)$",
            r"^Package (\w+) Warning: (.+)$",
        ]
        box_patterns = [
            r"^Overfull \\hbox",
            r"^Underfull \\hbox",
            r"^Overfull \\vbox",
            r"^Underfull \\vbox",
        ]

        for line in unwrapped.split("\n"):
            for pattern in important_patterns:
                if re.match(pattern, line):
                    important.append(line.strip())
                    break
            else:
                for pattern in box_patterns:
                    if re.match(pattern, line):
                        box_warnings.append(line.strip())
                        break

        # Important first, then box warnings, capped at 20 total
        return (important + box_warnings)[:20]

    async def _get_page_count(self, pdf_path: Path) -> int | None:
        """Get page count from PDF.  Returns ``None`` if pdfinfo is
        unavailable or fails, so callers can distinguish "unknown" from
        "zero pages".
        """
        pdfinfo = find_binary("pdfinfo", "poppler")
        if not pdfinfo:
            return None
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [pdfinfo, str(pdf_path)],
                capture_output=True,
                text=True,
            )

            for line in result.stdout.split("\n"):
                if line.startswith("Pages:"):
                    return int(line.split(":")[1].strip())

        except Exception:
            pass

        return None

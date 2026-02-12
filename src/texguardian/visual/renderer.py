"""PDF to PNG rendering using pdftoppm."""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path

from texguardian.core.toolchain import find_binary, get_install_hint


class PDFRenderer:
    """Renders PDF pages to PNG images."""

    def __init__(self, dpi: int = 150):
        self.dpi = dpi

    async def render(
        self,
        pdf_path: Path,
        output_dir: Path,
        pages: list[int] | None = None,
    ) -> list[Path]:
        """Render PDF pages to PNG images.

        Args:
            pdf_path: Path to PDF file
            output_dir: Directory for output PNG files
            pages: Specific pages to render (1-indexed), or None for all

        Returns:
            List of paths to generated PNG files
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Find pdftoppm binary
        pdftoppm = find_binary("pdftoppm", "poppler")
        if not pdftoppm:
            raise RuntimeError(
                f"pdftoppm not found. {get_install_hint('pdftoppm')}"
            )

        cmd = [
            pdftoppm,
            "-png",
            "-r", str(self.dpi),
        ]

        if pages:
            # Render specific pages
            cmd.extend(["-f", str(min(pages)), "-l", str(max(pages))])

        output_prefix = output_dir / "page"
        cmd.extend([str(pdf_path), str(output_prefix)])

        # Run pdftoppm
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                raise RuntimeError(f"pdftoppm failed: {result.stderr}")

        except FileNotFoundError:
            raise RuntimeError(
                "pdftoppm not found. Install poppler-utils: "
                "brew install poppler (macOS) or apt install poppler-utils (Linux)"
            )

        # Collect output files
        png_files = sorted(output_dir.glob("page-*.png"))

        # Filter to requested pages if specified
        if pages:
            png_files = [
                f for f in png_files
                if self._get_page_number(f) in pages
            ]

        return png_files

    async def render_single_page(
        self,
        pdf_path: Path,
        page_number: int,
        output_path: Path,
    ) -> Path:
        """Render a single page to a specific path."""
        output_dir = output_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)

        pdftoppm = find_binary("pdftoppm", "poppler")
        if not pdftoppm:
            raise RuntimeError(
                f"pdftoppm not found. {get_install_hint('pdftoppm')}"
            )
        cmd = [
            pdftoppm,
            "-png",
            "-r", str(self.dpi),
            "-f", str(page_number),
            "-l", str(page_number),
            "-singlefile",
            str(pdf_path),
            str(output_path.with_suffix("")),
        ]

        try:
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise RuntimeError(f"pdftoppm failed: {result.stderr}")

        except FileNotFoundError:
            raise RuntimeError("pdftoppm not found")

        # pdftoppm adds .png suffix
        actual_path = output_path.with_suffix(".png")
        if not actual_path.exists():
            actual_path = output_path
        if not actual_path.exists():
            raise RuntimeError(f"Expected output not created: {output_path}")

        return actual_path

    def _get_page_number(self, png_path: Path) -> int:
        """Extract page number from PNG filename."""
        # Format: page-01.png, page-02.png, etc.
        name = png_path.stem
        try:
            return int(name.split("-")[-1])
        except ValueError:
            return 0


async def get_pdf_page_count(pdf_path: Path) -> int:
    """Get the number of pages in a PDF."""
    pdfinfo = find_binary("pdfinfo", "poppler")
    if not pdfinfo:
        return 0
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

    return 0

"""Image differencing using Pillow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass
class DiffResult:
    """Result of image comparison."""

    diff_percentage: float
    diff_image_path: Path | None = None
    changed_regions: list[tuple[int, int, int, int]] | None = None  # Bounding boxes


class ImageDiffer:
    """Compares images and generates diff overlays."""

    def __init__(self, threshold: float = 5.0, pixel_threshold: int = 15):
        """
        Args:
            threshold: Percentage threshold for "significant" change (convergence)
            pixel_threshold: Per-pixel intensity difference to count as changed (0-255)
        """
        self.threshold = threshold
        self.pixel_threshold = pixel_threshold

    def compare(
        self,
        image1_path: Path | str,
        image2_path: Path | str,
        output_path: Path | str | None = None,
    ) -> DiffResult:
        """Compare two images and optionally generate diff overlay.

        Args:
            image1_path: Path to first (before) image
            image2_path: Path to second (after) image
            output_path: Path for diff overlay image (optional)

        Returns:
            DiffResult with percentage difference and optional overlay path
        """
        # Convert string paths to Path objects
        image1_path = Path(image1_path) if isinstance(image1_path, str) else image1_path
        image2_path = Path(image2_path) if isinstance(image2_path, str) else image2_path

        # Load images
        img1 = Image.open(image1_path).convert("RGB")
        img2 = Image.open(image2_path).convert("RGB")

        # Ensure same size
        if img1.size != img2.size:
            # Resize img2 to match img1
            img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)

        # Convert to numpy arrays
        arr1 = np.array(img1, dtype=np.float32)
        arr2 = np.array(img2, dtype=np.float32)

        # Calculate pixel-wise difference
        diff = np.abs(arr1 - arr2)

        # Calculate percentage of significantly different pixels
        # A pixel is "different" if any channel differs by more than pixel_threshold
        significant_diff = np.max(diff, axis=2) > self.pixel_threshold
        diff_percentage = (np.sum(significant_diff) / significant_diff.size) * 100

        # Find regions with changes (with fallback if scipy unavailable)
        regions = self._find_change_regions(significant_diff)

        # Generate diff overlay if requested
        diff_image_path = None
        if output_path:
            diff_image_path = self._generate_overlay(img2, significant_diff, output_path)

        return DiffResult(
            diff_percentage=diff_percentage,
            diff_image_path=diff_image_path,
            changed_regions=regions,
        )

    def _find_change_regions(
        self,
        diff_mask: np.ndarray,
    ) -> list[tuple[int, int, int, int]]:
        """Find bounding boxes of changed regions.

        Falls back to simple bounding box if scipy unavailable.
        """
        try:
            from scipy import ndimage

            # Label connected components
            labeled, num_features = ndimage.label(diff_mask)

            regions = []
            for i in range(1, num_features + 1):
                component = labeled == i
                rows = np.any(component, axis=1)
                cols = np.any(component, axis=0)

                if np.any(rows) and np.any(cols):
                    rmin, rmax = np.where(rows)[0][[0, -1]]
                    cmin, cmax = np.where(cols)[0][[0, -1]]
                    regions.append((cmin, rmin, cmax, rmax))

            return regions
        except (ImportError, AttributeError):
            # Fallback: return single bounding box of all changes
            if not np.any(diff_mask):
                return []
            rows = np.any(diff_mask, axis=1)
            cols = np.any(diff_mask, axis=0)
            if np.any(rows) and np.any(cols):
                rmin, rmax = np.where(rows)[0][[0, -1]]
                cmin, cmax = np.where(cols)[0][[0, -1]]
                return [(cmin, rmin, cmax, rmax)]
            return []

    def _generate_overlay(
        self,
        base_image: Image.Image,
        diff_mask: np.ndarray,
        output_path: Path | str,
    ) -> Path:
        """Generate diff overlay image highlighting changes in red."""
        # Convert to Path if string
        output_path = Path(output_path) if isinstance(output_path, str) else output_path

        # Create a copy of the base image
        overlay = base_image.copy()
        overlay_arr = np.array(overlay)

        # Create red highlight
        highlight = np.zeros_like(overlay_arr)
        highlight[diff_mask] = [255, 0, 0]  # Red

        # Blend: 70% original, 30% red where different
        alpha = 0.3
        result = overlay_arr.copy()
        result[diff_mask] = (
            (1 - alpha) * overlay_arr[diff_mask] + alpha * highlight[diff_mask]
        ).astype(np.uint8)

        # Save result
        output_path.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(result).save(output_path)

        return output_path


def compute_structural_similarity(
    image1_path: Path,
    image2_path: Path,
) -> float:
    """Compute structural similarity index between two images.

    Returns:
        SSIM value between 0 and 1 (1 = identical)
    """
    img1 = Image.open(image1_path).convert("L")  # Grayscale
    img2 = Image.open(image2_path).convert("L")

    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.Resampling.LANCZOS)

    arr1 = np.array(img1, dtype=np.float64)
    arr2 = np.array(img2, dtype=np.float64)

    # Simple MSE-based similarity (not true SSIM but faster)
    mse = np.mean((arr1 - arr2) ** 2)
    if mse == 0:
        return 1.0

    max_val = 255.0
    psnr = 10 * np.log10((max_val ** 2) / mse)

    # Convert PSNR to 0-1 scale (rough approximation)
    # PSNR > 40 dB is generally considered excellent
    similarity = min(1.0, psnr / 50.0)

    return similarity

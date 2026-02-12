"""Visual verification loop."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


@dataclass
class VisualVerificationResult:
    """Result of visual verification loop."""

    rounds: int
    quality_score: int
    patches_applied: int
    remaining_issues: list[str] = field(default_factory=list)
    stopped_reason: str = ""


@dataclass
class VisualIssue:
    """A visual issue identified by the vision model."""

    page: int
    location: str
    severity: str
    category: str
    description: str
    suggested_fix: str
    patch: str | None = None


class VisualVerifier:
    """Runs the visual verification loop."""

    def __init__(self, session: SessionState):
        self.session = session

    async def run_loop(
        self,
        max_rounds: int = 5,
        console: Console | None = None,
        focus_areas: list[str] | None = None,
    ) -> VisualVerificationResult:
        """Run the visual verification loop.

        1. Compile LaTeX -> PDF
        2. Render PDF pages to PNG
        3. Send images to vision model
        4. If issues found:
           a. Generate/apply patches
           b. Re-render, compute diff
           c. Check if converged
        5. Repeat until converged or max rounds
        """
        from texguardian.latex.compiler import LatexCompiler
        from texguardian.llm.factory import create_vision_client
        from texguardian.visual.renderer import PDFRenderer

        compiler = LatexCompiler(self.session.config)
        renderer = PDFRenderer(dpi=self.session.config.visual.dpi)
        vision_client = create_vision_client(self.session.config)

        # Reset quality tracking so previous runs don't contaminate regression detection
        self.session.quality_scores.clear()
        self.session.consecutive_regressions = 0

        patches_applied = 0
        quality_score = 0
        previous_images: list[Path] = []
        previous_issues: list[str] = []

        for round_num in range(1, max_rounds + 1):
            if console:
                console.print(f"\n[bold]Round {round_num}/{max_rounds}[/bold]")

            # Step 1: Compile
            if console:
                console.print("  Compiling...", end=" ")
            result = await compiler.compile(
                self.session.main_tex_path,
                self.session.output_dir,
            )

            if not result.success:
                if console:
                    console.print("[red]Failed[/red]")
                return VisualVerificationResult(
                    rounds=round_num,
                    quality_score=0,
                    patches_applied=patches_applied,
                    stopped_reason="Compilation failed",
                )
            if console:
                console.print("[green]OK[/green]")

            # Step 2: Render pages
            if console:
                console.print("  Rendering pages...", end=" ")

            render_dir = self.session.guardian_dir / "renders" / f"round_{round_num}"
            current_images = await renderer.render(result.pdf_path, render_dir)

            if console:
                console.print(f"[green]{len(current_images)} pages[/green]")

            # Step 3: Compute diff if we have previous images
            diff_percentage = 100.0
            if previous_images:
                if len(previous_images) == len(current_images):
                    diff_percentage = await self._compute_diff(
                        previous_images, current_images, render_dir / "diffs"
                    )
                    if console:
                        console.print(f"  Visual diff: {diff_percentage:.1f}%")

                    if diff_percentage < self.session.config.visual.diff_threshold:
                        if console:
                            console.print("  [green]Converged![/green]")
                        return VisualVerificationResult(
                            rounds=round_num,
                            quality_score=quality_score,
                            patches_applied=patches_applied,
                            stopped_reason="Converged",
                        )
                else:
                    if console:
                        console.print(f"  [yellow]Page count changed ({len(previous_images)} → {len(current_images)}), skipping diff[/yellow]")

            # Step 4: Send to vision model
            if console:
                console.print("  Analyzing with vision model...")

            analysis = await self._analyze_images(
                current_images,
                vision_client,
                previous_issues,
                focus_areas=focus_areas,
            )

            quality_score = analysis.get("quality_score", 0)
            issues = analysis.get("issues", [])

            if console:
                console.print(f"  Quality: {quality_score}/100")
                console.print(f"  Issues found: {len(issues)}")

            # Check quality regression
            self.session.track_quality(quality_score)
            if self.session.should_stop_auto_fix():
                if console:
                    console.print("  [yellow]Quality regressed twice, stopping[/yellow]")
                return VisualVerificationResult(
                    rounds=round_num,
                    quality_score=quality_score,
                    patches_applied=patches_applied,
                    remaining_issues=[i.get("description", "") for i in issues],
                    stopped_reason="Quality regression",
                )

            # Step 5: Apply patches if any
            substantive_issues = [
                i for i in issues if i.get("severity") in ("error", "warning")
            ]

            if not substantive_issues:
                if console:
                    console.print("  [green]No substantive issues[/green]")
                return VisualVerificationResult(
                    rounds=round_num,
                    quality_score=quality_score,
                    patches_applied=patches_applied,
                    stopped_reason="No issues",
                )

            # Apply patches
            applied = await self._apply_visual_patches(substantive_issues, console)
            patches_applied += applied

            # Store for next round
            previous_images = current_images
            previous_issues = [i.get("description", "") for i in issues]

        return VisualVerificationResult(
            rounds=max_rounds,
            quality_score=quality_score,
            patches_applied=patches_applied,
            remaining_issues=previous_issues,
            stopped_reason="Max rounds reached",
        )

    async def _compute_diff(
        self,
        old_images: list[Path],
        new_images: list[Path],
        diff_dir: Path,
    ) -> float:
        """Compute visual diff between image sets."""
        from texguardian.visual.differ import ImageDiffer

        differ = ImageDiffer(
            threshold=self.session.config.visual.diff_threshold,
            pixel_threshold=self.session.config.visual.pixel_threshold,
        )

        total_diff = 0.0
        diff_dir.mkdir(parents=True, exist_ok=True)

        for old_img, new_img in zip(old_images, new_images):
            result = differ.compare(
                old_img,
                new_img,
                diff_dir / f"diff_{old_img.stem}.png",
            )
            total_diff += result.diff_percentage

        return total_diff / len(old_images) if old_images else 0.0

    async def _analyze_images(
        self,
        images: list[Path],
        vision_client,
        previous_issues: list[str],
        focus_areas: list[str] | None = None,
    ) -> dict:
        """Send images to vision model for analysis."""
        from texguardian.llm.base import ImageContent
        from texguardian.llm.prompts.visual import (
            VISUAL_VERIFIER_SYSTEM_PROMPT,
            build_visual_user_prompt,
        )

        # Load images - analyze all pages or up to configured limit
        # Default to all pages (0 = no limit), but can be limited via config
        max_pages = getattr(self.session.config.visual, 'max_pages_to_analyze', 0)
        if max_pages <= 0:
            max_pages = len(images)  # Analyze all pages

        image_contents = []
        for img_path in images[:max_pages]:
            image_data = img_path.read_bytes()
            image_contents.append(ImageContent(data=image_data, media_type="image/png"))

        # Build prompt
        paper_spec = self.session.paper_spec
        user_prompt = build_visual_user_prompt(
            paper_title=paper_spec.title if paper_spec else "Paper",
            venue=paper_spec.venue if paper_spec else "Unknown",
            max_pages=paper_spec.thresholds.max_pages if paper_spec else 9,
            page_numbers=list(range(1, len(images) + 1)),
            focus_areas=focus_areas,
            previous_issues=previous_issues,
        )

        # Send to vision model
        try:
            response = await vision_client.complete_with_vision(
                messages=[{"role": "user", "content": user_prompt}],
                images=image_contents,
                system=VISUAL_VERIFIER_SYSTEM_PROMPT,
                max_tokens=4000,
                temperature=0.3,
            )

            # Parse JSON response
            content = response.content

            # Extract JSON from response — use find/rfind to avoid greedy regex
            json_start = content.find("{")
            json_end = content.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                return json.loads(content[json_start:json_end])

        except Exception as e:
            return {"quality_score": 0, "issues": [], "error": str(e)}

        return {"quality_score": 50, "issues": []}

    async def _apply_visual_patches(
        self,
        issues: list[dict],
        console: Console | None,
    ) -> int:
        """Apply patches from visual issues."""
        from texguardian.cli.commands.approve import apply_patches
        from texguardian.patch.parser import extract_patches

        applied = 0

        for issue in issues:
            patch_text = issue.get("patch")
            if not patch_text:
                continue

            # Wrap in diff block for parser
            if not patch_text.startswith("```"):
                patch_text = f"```diff\n{patch_text}\n```"

            patches = extract_patches(patch_text)

            if patches:
                try:
                    await apply_patches(patches, self.session, console)
                    applied += len(patches)
                except Exception as e:
                    if console:
                        console.print(f"  [red]Failed to apply patch: {e}[/red]")

        return applied

"""TexGuardian release animation — 15-second GIF.

Storyboard:
  Phase 1 (0-2.5s)   — Logo entrance: shield fades in, title types out, tagline
  Phase 2 (2.5-4.5s) — Logo slides up, terminal window appears
  Phase 3 (4.5-9s)   — Terminal demo: /review full pipeline with steps ticking off
  Phase 4 (9-12s)    — Feature badges fly in as a 2x3 grid
  Phase 5 (12-15s)   — CTA: pip install texguardian + GitHub URL

Render:
  manim -ql release_animation.py TexGuardianRelease   # low quality (fast)
  manim -qm release_animation.py TexGuardianRelease   # medium quality
  manim -qh release_animation.py TexGuardianRelease   # high quality (1080p)

Convert to GIF:
  ffmpeg -i media/videos/release_animation/720p30/TexGuardianRelease.mp4 \
         -vf "fps=12,scale=960:-1:flags=lanczos" -loop 0 release_animation.gif
"""

from manim import *


# ── Brand palette ────────────────────────────────────────────────────────────
BRAND_BLUE = "#2563EB"
BRAND_BLUE_DARK = "#1D4ED8"
BRAND_GREEN = "#16A34A"
BRAND_GRAY = "#64748B"
BRAND_LIGHT = "#C9D1D9"
BRAND_DARK = "#0F172A"
BRAND_RED = "#EF4444"
BRAND_ORANGE = "#F59E0B"
BRAND_PURPLE = "#D2A8FF"
BRAND_CYAN = "#06B6D4"
BRAND_PINK = "#EC4899"
BRAND_VIOLET = "#8B5CF6"


class TexGuardianRelease(Scene):
    def construct(self):
        self.camera.background_color = BRAND_DARK

        # ── Phase 1: Logo entrance (0 – 2.5s) ───────────────────────
        shield = self._build_shield()
        shield.scale(1.2).move_to(ORIGIN)

        title = Text("TexGuardian", font="Helvetica Neue", weight=BOLD, font_size=56)
        title[:3].set_color(WHITE)
        title[3:].set_color(BRAND_BLUE)
        title.next_to(shield, RIGHT, buff=0.5)

        logo_group = VGroup(shield, title).move_to(ORIGIN)

        self.play(FadeIn(shield, scale=0.3), run_time=0.6)
        self.play(Write(title), run_time=0.8)

        tagline = Text(
            "AI-powered LaTeX paper assistant",
            font="Helvetica Neue", font_size=22, color=BRAND_GRAY,
        )
        tagline.next_to(logo_group, DOWN, buff=0.4)
        self.play(FadeIn(tagline, shift=UP * 0.2), run_time=0.5)
        self.wait(0.8)

        # ── Phase 2: Slide logo up, show terminal (2.5 – 4.5s) ──────
        self.play(
            logo_group.animate.scale(0.55).to_edge(UP, buff=0.3),
            FadeOut(tagline),
            run_time=0.6,
        )

        terminal = self._build_terminal()
        terminal.scale(0.75).move_to(DOWN * 0.3)

        self.play(FadeIn(terminal, shift=UP * 0.3), run_time=0.5)
        self.wait(0.2)

        # ── Phase 3: Terminal demo — the pipeline (4.5 – 9s) ────────
        lines = [
            ("❯ ", BRAND_BLUE, "/review full", BRAND_PURPLE),
            ("  ① Compile      ", BRAND_LIGHT, "✓ built PDF", BRAND_GREEN),
            ("  ② Verify       ", BRAND_LIGHT, "6 issues found", BRAND_ORANGE),
            ("  ③ Fix          ", BRAND_LIGHT, "6 patches applied ✓", BRAND_GREEN),
            ("  ④ Citations    ", BRAND_LIGHT, "9 verified ✓", BRAND_GREEN),
            ("  ⑤ Figures      ", BRAND_LIGHT, "fixed overflow ✓", BRAND_GREEN),
            ("  ⑥ Tables       ", BRAND_LIGHT, "booktabs applied ✓", BRAND_GREEN),
            ("  ⑦ Visual       ", BRAND_LIGHT, "layout confirmed ✓", BRAND_GREEN),
            ("  Score: ", WHITE, "97 / 100", BRAND_GREEN),
        ]

        body_anchor = terminal[1].get_corner(UL) + RIGHT * 0.25 + DOWN * 0.22
        rendered_lines = VGroup()

        for i, (prefix, pcol, content, ccol) in enumerate(lines):
            p = Text(prefix, font="Courier New", font_size=14, color=pcol)
            c = Text(content, font="Courier New", font_size=14, color=ccol)
            row = VGroup(p, c).arrange(RIGHT, buff=0.05)
            row.move_to(body_anchor + DOWN * i * 0.28, aligned_edge=LEFT)
            rendered_lines.add(row)

            # First line (command) types slower; steps appear faster
            if i == 0:
                self.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.4)
                self.wait(0.15)
            elif i == len(lines) - 1:
                # Score line — slight pause before, then emphasize
                self.wait(0.15)
                self.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.35)
            else:
                self.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.25)

        self.wait(0.8)

        # ── Phase 4: Feature badges (9 – 12s) ───────────────────────
        self.play(FadeOut(terminal), FadeOut(rendered_lines), run_time=0.4)

        features = [
            ("26 Commands", BRAND_BLUE),
            ("Visual Polish", BRAND_VIOLET),
            ("Citation Check", BRAND_GREEN),
            ("Diff Patches", BRAND_ORANGE),
            ("14 Venues", BRAND_PINK),
            ("Checkpoint Safety", BRAND_CYAN),
        ]

        badges = VGroup()
        for label, color in features:
            badges.add(self._build_badge(label, color))

        badges.arrange_in_grid(rows=2, cols=3, buff=(0.3, 0.25))
        badges.move_to(DOWN * 0.3)

        self.play(
            LaggedStart(
                *[FadeIn(b, scale=0.5) for b in badges],
                lag_ratio=0.1,
            ),
            run_time=1.2,
        )
        self.wait(1.0)

        # ── Phase 5: CTA — pip install + GitHub (12 – 15s) ──────────
        self.play(FadeOut(badges), run_time=0.3)

        # Install command box
        install_cmd = Text(
            "pip install texguardian",
            font="Courier New", font_size=28, color=WHITE,
        )
        install_bg = RoundedRectangle(
            corner_radius=0.15,
            width=install_cmd.width + 0.7,
            height=install_cmd.height + 0.4,
            fill_color="#1E293B", fill_opacity=1,
            stroke_color=BRAND_BLUE, stroke_width=2,
        )
        install_group = VGroup(install_bg, install_cmd).move_to(UP * 0.15)

        # GitHub link
        gh_text = Text(
            "github.com/arcAman07/TexGuardian",
            font="Courier New", font_size=18, color=BRAND_GRAY,
        )
        gh_text.next_to(install_group, DOWN, buff=0.45)

        # Open-source badge
        oss_badge = Text("MIT Licensed · Free & Open Source", font="Helvetica Neue", font_size=16, color=BRAND_GRAY)
        oss_badge.next_to(gh_text, DOWN, buff=0.3)

        self.play(FadeIn(install_group, scale=0.8), run_time=0.5)
        self.play(FadeIn(gh_text, shift=UP * 0.15), run_time=0.4)
        self.play(FadeIn(oss_badge, shift=UP * 0.1), run_time=0.3)
        self.wait(3.2)

    # ── Helper builders ──────────────────────────────────────────────────────

    def _build_shield(self):
        """Shield logo with T and checkmark."""
        # Shield body
        shield = RoundedRectangle(
            corner_radius=0.15, width=1.0, height=1.3,
            fill_color=BRAND_BLUE, fill_opacity=0.15,
            stroke_color=BRAND_BLUE, stroke_width=3,
        )
        # Pointed bottom
        point = Polygon(
            shield.get_corner(DL) + RIGHT * 0.05,
            shield.get_bottom() + DOWN * 0.3,
            shield.get_corner(DR) + LEFT * 0.05,
            fill_color=BRAND_BLUE, fill_opacity=0.15,
            stroke_color=BRAND_BLUE, stroke_width=3,
        )
        shape = VGroup(shield, point)

        # Italic "T"
        t_letter = Text(
            "T", font="Georgia", font_size=40,
            color=BRAND_BLUE, weight=BOLD, slant=ITALIC,
        )
        t_letter.move_to(shape.get_center() + UP * 0.05)

        # Checkmark
        check = VMobject(color=BRAND_GREEN, stroke_width=4)
        check.set_points_as_corners([
            shape.get_center() + LEFT * 0.2 + DOWN * 0.1,
            shape.get_center() + DOWN * 0.25,
            shape.get_center() + RIGHT * 0.3 + UP * 0.2,
        ])

        return VGroup(shape, t_letter, check)

    def _build_terminal(self):
        """macOS-style terminal window."""
        bg = RoundedRectangle(
            corner_radius=0.15, width=9.5, height=4.5,
            fill_color="#0D1117", fill_opacity=1,
            stroke_color="#30363D", stroke_width=1.5,
        )

        bar = Rectangle(
            width=9.5, height=0.4,
            fill_color="#161B22", fill_opacity=1, stroke_width=0,
        )
        bar.next_to(bg, UP, buff=0).shift(DOWN * 0.2)

        dots = VGroup(
            Dot(radius=0.06, color="#FF5F57"),
            Dot(radius=0.06, color="#FEBC2E"),
            Dot(radius=0.06, color="#28C840"),
        ).arrange(RIGHT, buff=0.12)
        dots.move_to(bar.get_left() + RIGHT * 0.5)

        bar_title = Text(
            "texguardian chat", font="Courier New",
            font_size=13, color=BRAND_GRAY,
        )
        bar_title.move_to(bar)

        return VGroup(VGroup(bg, bar, dots, bar_title), bg)

    def _build_badge(self, label, color):
        """Rounded pill badge with colored background."""
        txt = Text(label, font="Helvetica Neue", font_size=20, color=WHITE, weight=BOLD)
        bg = RoundedRectangle(
            corner_radius=0.12,
            width=txt.width + 0.5,
            height=txt.height + 0.35,
            fill_color=color, fill_opacity=0.9,
            stroke_width=0,
        )
        return VGroup(bg, txt)

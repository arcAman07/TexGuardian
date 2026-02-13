"""TexGuardian v0.3.3 release animation — 15-second GIF."""

from manim import *


# Brand colors
BRAND_BLUE = "#2563EB"
BRAND_BLUE_DARK = "#1D4ED8"
BRAND_GREEN = "#16A34A"
BRAND_GRAY = "#64748B"
BRAND_DARK = "#0F172A"
BRAND_RED = "#EF4444"
BRAND_ORANGE = "#F59E0B"


class TexGuardianRelease(Scene):
    def construct(self):
        self.camera.background_color = BRAND_DARK

        # ── Phase 1: Logo entrance (0-3s) ──────────────────────────
        shield = self._build_shield()
        shield.scale(1.2).move_to(ORIGIN)

        title = Text("TexGuardian", font="Inter", weight=BOLD, font_size=56)
        title[:3].set_color(WHITE)
        title[3:].set_color(BRAND_BLUE)
        title.next_to(shield, RIGHT, buff=0.5)

        logo_group = VGroup(shield, title).move_to(ORIGIN)

        self.play(
            FadeIn(shield, scale=0.3),
            run_time=0.6,
        )
        self.play(Write(title), run_time=0.8)

        tagline = Text(
            "AI-powered LaTeX paper assistant",
            font="Inter",
            font_size=22,
            color=BRAND_GRAY,
        )
        tagline.next_to(logo_group, DOWN, buff=0.4)
        self.play(FadeIn(tagline, shift=UP * 0.2), run_time=0.5)
        self.wait(0.5)

        # ── Phase 2: Slide logo up, show terminal demo (3-9s) ─────
        self.play(
            logo_group.animate.scale(0.55).to_edge(UP, buff=0.3),
            FadeOut(tagline),
            run_time=0.6,
        )

        terminal = self._build_terminal()
        terminal.scale(0.75).move_to(DOWN * 0.4)

        self.play(FadeIn(terminal, shift=UP * 0.3), run_time=0.5)
        self.wait(0.3)

        # Typewriter lines inside terminal body
        lines = [
            ("❯ ", BRAND_BLUE, "/venue iclr 2026", "#D2A8FF"),
            ("  ✓ ", BRAND_GREEN, "Downloaded ICLR 2026 template", "#C9D1D9"),
            ("❯ ", BRAND_BLUE, "/review full", "#D2A8FF"),
            ("  Step 2/7: ", "#C9D1D9", "Found 6 issues", BRAND_ORANGE),
            ("  Step 3/7: ", "#C9D1D9", "Applied 6 patches ✓", BRAND_GREEN),
            ("  Score: ", "#C9D1D9", "97/100", BRAND_GREEN),
        ]

        body_anchor = terminal[1].get_corner(UL) + RIGHT * 0.25 + DOWN * 0.25
        rendered = []
        for i, (prefix, pcol, content, ccol) in enumerate(lines):
            p = Text(prefix, font="Courier New", font_size=16, color=pcol)
            c = Text(content, font="Courier New", font_size=16, color=ccol)
            row = VGroup(p, c).arrange(RIGHT, buff=0.05)
            row.move_to(body_anchor + DOWN * i * 0.32, aligned_edge=LEFT)
            rendered.append(row)

            if i < 3:
                self.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.35)
            else:
                self.play(FadeIn(row, shift=RIGHT * 0.15), run_time=0.3)
        self.wait(0.4)

        # ── Phase 3: Feature badges fly in (9-12s) ────────────────
        self.play(FadeOut(terminal), run_time=0.4)

        features = [
            ("26 Commands", BRAND_BLUE),
            ("Visual Polish", "#8B5CF6"),
            ("Citation Check", BRAND_GREEN),
            ("Diff Patches", BRAND_ORANGE),
            ("14 Venues", "#EC4899"),
            ("Checkpoint Safety", "#06B6D4"),
        ]

        badges = VGroup()
        for label, color in features:
            badge = self._build_badge(label, color)
            badges.add(badge)

        badges.arrange_in_grid(rows=2, cols=3, buff=(0.3, 0.25))
        badges.move_to(DOWN * 0.3)

        self.play(
            LaggedStart(
                *[FadeIn(b, scale=0.5) for b in badges],
                lag_ratio=0.1,
            ),
            run_time=1.2,
        )
        self.wait(0.8)

        # ── Phase 4: Version + CTA (12-15s) ───────────────────────
        self.play(FadeOut(badges), run_time=0.3)

        version = Text("v0.3.3", font="Inter", weight=BOLD, font_size=48, color=BRAND_BLUE)
        version.move_to(DOWN * 0.1)

        install_cmd = Text(
            "pip install texguardian",
            font="Courier New",
            font_size=26,
            color=WHITE,
        )
        install_bg = RoundedRectangle(
            corner_radius=0.15,
            width=install_cmd.width + 0.6,
            height=install_cmd.height + 0.35,
            fill_color="#1E293B",
            fill_opacity=1,
            stroke_color=BRAND_BLUE,
            stroke_width=2,
        )
        install_group = VGroup(install_bg, install_cmd).move_to(DOWN * 0.9)

        self.play(
            FadeIn(version, scale=0.6),
            run_time=0.5,
        )
        self.play(FadeIn(install_group, shift=UP * 0.2), run_time=0.5)
        self.wait(1.5)

    # ── Helpers ────────────────────────────────────────────────────

    def _build_shield(self):
        """Shield icon matching the SVG logo."""
        shield_path = SVGMobject(
            "shield_path.svg",
        ) if False else self._shield_from_points()
        return shield_path

    def _shield_from_points(self):
        """Manually build the shield + checkmark."""
        # Shield outline
        shield = RoundedRectangle(
            corner_radius=0.15,
            width=1.0,
            height=1.3,
            fill_color=BRAND_BLUE,
            fill_opacity=0.15,
            stroke_color=BRAND_BLUE,
            stroke_width=3,
        )
        # Pointed bottom
        point = Polygon(
            shield.get_corner(DL) + RIGHT * 0.05,
            shield.get_bottom() + DOWN * 0.3,
            shield.get_corner(DR) + LEFT * 0.05,
            fill_color=BRAND_BLUE,
            fill_opacity=0.15,
            stroke_color=BRAND_BLUE,
            stroke_width=3,
        )
        shield_shape = VGroup(shield, point)

        # "T" letter
        t_letter = Text(
            "T", font="Georgia", font_size=40,
            color=BRAND_BLUE, weight=BOLD, slant=ITALIC,
        )
        t_letter.move_to(shield_shape.get_center() + UP * 0.05)

        # Checkmark
        check = VMobject(color=BRAND_GREEN, stroke_width=4)
        check.set_points_as_corners([
            shield_shape.get_center() + LEFT * 0.2 + DOWN * 0.1,
            shield_shape.get_center() + DOWN * 0.25,
            shield_shape.get_center() + RIGHT * 0.3 + UP * 0.2,
        ])

        return VGroup(shield_shape, t_letter, check)

    def _build_terminal(self):
        """Terminal window chrome."""
        bg = RoundedRectangle(
            corner_radius=0.15,
            width=9,
            height=4.0,
            fill_color="#0D1117",
            fill_opacity=1,
            stroke_color="#30363D",
            stroke_width=1.5,
        )

        # Title bar
        bar = Rectangle(
            width=9, height=0.4,
            fill_color="#161B22",
            fill_opacity=1,
            stroke_width=0,
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
        """Rounded feature badge."""
        txt = Text(label, font="Inter", font_size=20, color=WHITE, weight=BOLD)
        bg = RoundedRectangle(
            corner_radius=0.12,
            width=txt.width + 0.5,
            height=txt.height + 0.35,
            fill_color=color,
            fill_opacity=0.9,
            stroke_width=0,
        )
        return VGroup(bg, txt)

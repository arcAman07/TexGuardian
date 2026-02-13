"""TexGuardian release animation — ~50s demo GIF based on actual CLI output.

Render:
  manim -qm release_animation.py TexGuardianRelease

Convert to GIF:
  ffmpeg -y -i <mp4> -vf "fps=12,scale=960:-1:flags=lanczos,split[s0][s1]; \
    [s0]palettegen=max_colors=128:stats_mode=diff[p]; \
    [s1][p]paletteuse=dither=floyd_steinberg" -loop 0 release_animation.gif
"""

from manim import *

# ── Brand palette ──
BLUE = "#2563EB"
GREEN = "#16A34A"
GRAY = "#64748B"
LIGHT = "#C9D1D9"
DARK = "#0F172A"
ORANGE = "#F59E0B"
PURPLE = "#D2A8FF"
CYAN = "#06B6D4"
PINK = "#EC4899"
VIOLET = "#8B5CF6"
WHITE_T = "#E6EDF3"
TERM_BG = "#0D1117"
TERM_BORDER = "#30363D"
TERM_BAR_BG = "#161B22"

MONO = "Courier New"
SANS = "Helvetica Neue"
FS = 12
LH = 0.22


class TexGuardianRelease(Scene):
    def construct(self):
        self.camera.background_color = DARK

        # ────────────────────────────────────────────────────
        # Phase 1 — Logo entrance (0–3s)
        # ────────────────────────────────────────────────────
        shield = self._shield().scale(1.2).move_to(ORIGIN)
        title = Text("TexGuardian", font=SANS, weight=BOLD, font_size=56)
        title[:3].set_color(WHITE)
        title[3:].set_color(BLUE)
        title.next_to(shield, RIGHT, buff=0.5)
        logo = VGroup(shield, title).move_to(ORIGIN)

        self.play(FadeIn(shield, scale=0.3), run_time=0.6)
        self.play(Write(title), run_time=0.8)

        tagline = Text(
            "AI-powered LaTeX paper assistant",
            font=SANS, font_size=22, color=GRAY,
        )
        tagline.next_to(logo, DOWN, buff=0.4)
        self.play(FadeIn(tagline, shift=UP * 0.2), run_time=0.5)
        self.wait(1.0)

        # ────────────────────────────────────────────────────
        # Phase 2 — Terminal + welcome panel (3–7.5s)
        # ────────────────────────────────────────────────────
        self.play(
            logo.animate.scale(0.5).to_edge(UP, buff=0.25),
            FadeOut(tagline),
            run_time=0.5,
        )

        # Terminal chrome
        term_bg = RoundedRectangle(
            corner_radius=0.15, width=11.5, height=5.8,
            fill_color=TERM_BG, fill_opacity=1,
            stroke_color=TERM_BORDER, stroke_width=1.5,
        )
        term_bar = Rectangle(
            width=11.5, height=0.35,
            fill_color=TERM_BAR_BG, fill_opacity=1, stroke_width=0,
        )
        term_bar.next_to(term_bg, UP, buff=0).shift(DOWN * 0.175)
        dots = VGroup(
            Dot(radius=0.05, color="#FF5F57"),
            Dot(radius=0.05, color="#FEBC2E"),
            Dot(radius=0.05, color="#28C840"),
        ).arrange(RIGHT, buff=0.1)
        dots.move_to(term_bar.get_left() + RIGHT * 0.4)
        bar_title = Text("texguardian chat", font=MONO, font_size=10, color=GRAY)
        bar_title.move_to(term_bar)

        terminal = VGroup(term_bg, term_bar, dots, bar_title)
        terminal.move_to(DOWN * 0.4)
        self.play(FadeIn(terminal, shift=UP * 0.3), run_time=0.5)

        anchor = term_bg.get_corner(UL) + RIGHT * 0.35 + DOWN * 0.5

        # Welcome panel
        wp = self._panel([
            [("TexGuardian", WHITE_T, True)],
            None,
            [("  Paper  ", GRAY), ("Scaling Sparse MoE for Long-Context...", LIGHT)],
            [("  Venue  ", GRAY), ("ICLR 2026", BLUE),
             ("        Deadline  ", GRAY), ("2026-01-23", LIGHT)],
            [("  Model  ", GRAY), ("claude opus 4.5", LIGHT),
             ("     Provider  ", GRAY), ("bedrock", LIGHT)],
            [("  File   ", GRAY), ("demo_paper.tex", LIGHT),
             ("      Figures ", GRAY), ("2", LIGHT),
             (" · Tables ", GRAY), ("3", LIGHT)],
            None,
            [("  Type /help for commands or ask a question.", GRAY)],
        ])
        wp.move_to(term_bg.get_center())
        self.play(FadeIn(wp, scale=0.95), run_time=0.5)
        self.wait(3.0)

        # ────────────────────────────────────────────────────
        # Phase 3 — /review full command + header (7.5–10.5s)
        # ────────────────────────────────────────────────────
        self.play(FadeOut(wp), run_time=0.3)

        prompt = self._row([
            ("❯ ", BLUE), ("/review full", PURPLE),
            (" the entire paper", GRAY),
        ])
        prompt.move_to(anchor, aligned_edge=LEFT)
        self.play(FadeIn(prompt), run_time=0.3)
        self.wait(0.3)

        rh = self._panel([
            [("Starting Continuous Paper Review", WHITE_T, True)],
            None,
            [("Mode: ", GRAY), ("full", LIGHT)],
            [("Paper: ", GRAY), ("Scaling Sparse MoE for Long-Context...", LIGHT)],
            [("Target Score: ", GRAY), ("90/100", GREEN)],
            [("Max Rounds: ", GRAY), ("5", LIGHT)],
        ])
        rh.next_to(prompt, DOWN, buff=0.3, aligned_edge=LEFT)
        self.play(FadeIn(rh, shift=UP * 0.1), run_time=0.4)
        self.wait(1.5)

        # ────────────────────────────────────────────────────
        # Phase 4 — Steps 1–7 ticking off (10.5–28s)
        # ────────────────────────────────────────────────────
        self.play(FadeOut(prompt), FadeOut(rh), run_time=0.3)

        round_hdr = Text(
            "── Round 1/5 " + "─" * 38,
            font=MONO, font_size=FS - 1, color=GRAY,
        )
        round_hdr.move_to(anchor, aligned_edge=LEFT)
        self.play(FadeIn(round_hdr), run_time=0.2)

        y = anchor[1] - LH * 1.5
        phase4 = VGroup(round_hdr)

        steps = [
            ("Step 1/7: Compiling LaTeX",
             "  ✓ Compiled successfully · Pages: 4", GREEN, 1.0),
            ("Step 2/7: Running Verification Checks",
             "  Found 3 issue(s): citation, overflow, hline", ORANGE, 1.3),
            ("Step 3/7: Fixing Verification Issues",
             "  ✓ Applied 1 patch to demo_paper.tex", GREEN, 1.0),
            ("Step 4/7: Validating Citations",
             "  ✓ Valid: 7   ~ Needs correction: 4", GREEN, 1.3),
            ("Step 5/7: Analyzing Figures",
             "  ✓ Applied 1 figure fix", GREEN, 1.0),
            ("Step 6/7: Analyzing Tables",
             "  ✓ No table issues", GREEN, 0.8),
            ("Step 7/7: Visual Verification",
             "  3 rounds · Quality: 88/100 · Converged!", GREEN, 1.5),
        ]

        for name, result, color, pause in steps:
            sep = Line(
                [anchor[0], y + 0.05, 0],
                [anchor[0] + 10.5, y + 0.05, 0],
                color=TERM_BORDER, stroke_width=0.5,
            )
            y -= 0.05

            hdr = Text(name, font=MONO, font_size=FS, color=WHITE_T, weight=BOLD)
            hdr.move_to([anchor[0], y, 0], aligned_edge=LEFT)
            y -= LH

            self.play(FadeIn(sep), FadeIn(hdr), run_time=0.2)
            self.wait(0.15)

            res = Text(result, font=MONO, font_size=FS, color=color)
            res.move_to([anchor[0], y, 0], aligned_edge=LEFT)
            y -= LH * 1.3

            self.play(FadeIn(res, shift=RIGHT * 0.08), run_time=0.2)
            phase4.add(sep, hdr, res)
            self.wait(pause)

        # Score reveal
        sep_f = Line(
            [anchor[0], y + 0.05, 0],
            [anchor[0] + 10.5, y + 0.05, 0],
            color=TERM_BORDER, stroke_width=0.5,
        )
        y -= LH * 0.5

        score = self._row([("  Overall Score: ", WHITE_T), ("98/100", GREEN)])
        score.move_to([anchor[0], y, 0], aligned_edge=LEFT)
        y -= LH * 1.2

        ready = Text(
            "  ✓ Reached target score — Ready for submission!",
            font=MONO, font_size=FS, color=GREEN, weight=BOLD,
        )
        ready.move_to([anchor[0], y, 0], aligned_edge=LEFT)

        self.play(FadeIn(sep_f), run_time=0.1)
        self.wait(0.2)
        self.play(FadeIn(score, scale=0.9), run_time=0.4)
        self.wait(0.4)
        self.play(FadeIn(ready, shift=UP * 0.08), run_time=0.3)
        phase4.add(sep_f, score, ready)
        self.wait(2.0)

        # ────────────────────────────────────────────────────
        # Phase 5 — Summary table (28–35s)
        # ────────────────────────────────────────────────────
        self.play(FadeOut(phase4), run_time=0.4)

        summary = self._summary_table()
        summary.move_to(term_bg.get_center())
        self.play(FadeIn(summary, scale=0.95), run_time=0.5)
        self.wait(5.0)

        # ────────────────────────────────────────────────────
        # Phase 6 — Feature badges (35–40s)
        # ────────────────────────────────────────────────────
        self.play(FadeOut(summary), FadeOut(terminal), run_time=0.4)

        features = [
            ("26 Commands", BLUE), ("Visual Polish", VIOLET),
            ("Citation Check", GREEN), ("Diff Patches", ORANGE),
            ("14 Venues", PINK), ("Checkpoint Safety", CYAN),
        ]
        badges = VGroup(*[self._badge(l, c) for l, c in features])
        badges.arrange_in_grid(rows=2, cols=3, buff=(0.3, 0.25))
        badges.move_to(DOWN * 0.3)

        self.play(
            LaggedStart(
                *[FadeIn(b, scale=0.5) for b in badges],
                lag_ratio=0.1,
            ),
            run_time=1.2,
        )
        self.wait(2.5)

        # ────────────────────────────────────────────────────
        # Phase 7 — CTA: pip install + GitHub (40–50s)
        # ────────────────────────────────────────────────────
        self.play(FadeOut(badges), run_time=0.3)

        cmd = Text("pip install texguardian", font=MONO, font_size=28, color=WHITE)
        cmd_bg = RoundedRectangle(
            corner_radius=0.15,
            width=cmd.width + 0.7, height=cmd.height + 0.4,
            fill_color="#1E293B", fill_opacity=1,
            stroke_color=BLUE, stroke_width=2,
        )
        install = VGroup(cmd_bg, cmd).move_to(UP * 0.15)

        gh = Text(
            "github.com/arcAman07/TexGuardian",
            font=MONO, font_size=18, color=GRAY,
        )
        gh.next_to(install, DOWN, buff=0.45)

        oss = Text(
            "MIT Licensed · Free & Open Source",
            font=SANS, font_size=16, color=GRAY,
        )
        oss.next_to(gh, DOWN, buff=0.3)

        self.play(FadeIn(install, scale=0.8), run_time=0.5)
        self.play(FadeIn(gh, shift=UP * 0.15), run_time=0.4)
        self.play(FadeIn(oss, shift=UP * 0.1), run_time=0.3)
        self.wait(5.0)

    # ── Helpers ─────────────────────────────────────────────

    def _row(self, parts):
        """Colored text row. parts: list of (text, color) tuples."""
        texts = [Text(t, font=MONO, font_size=FS, color=c) for t, c in parts]
        return VGroup(*texts).arrange(RIGHT, buff=0.04)

    def _tbl_row(self, col1, col2, col3, text_color, status_color):
        """Fixed-width table row with proper column spacing."""
        c1 = Text(f"{col1:<17}", font=MONO, font_size=FS, color=text_color)
        c2 = Text(f"{col2:>22}", font=MONO, font_size=FS, color=text_color)
        c3 = Text(f"  {col3:>6}", font=MONO, font_size=FS, color=status_color)
        return VGroup(c1, c2, c3).arrange(RIGHT, buff=0.15)

    def _panel(self, lines_data, border_color=GRAY):
        """Rich-style bordered panel. None = empty line."""
        rows = VGroup()
        for line in lines_data:
            if line is None:
                rows.add(Text(" ", font=MONO, font_size=4))
                continue
            parts = []
            for item in line:
                if len(item) == 3:
                    txt, col, bold = item
                    parts.append(Text(
                        txt, font=MONO, font_size=FS - 1, color=col,
                        weight=BOLD if bold else NORMAL,
                    ))
                else:
                    txt, col = item
                    parts.append(Text(txt, font=MONO, font_size=FS - 1, color=col))
            rows.add(VGroup(*parts).arrange(RIGHT, buff=0.12))
        rows.arrange(DOWN, buff=0.08, aligned_edge=LEFT)

        border = RoundedRectangle(
            corner_radius=0.1,
            width=rows.width + 0.6, height=rows.height + 0.5,
            stroke_color=border_color, stroke_width=1,
            fill_opacity=0,
        )
        border.move_to(rows)
        return VGroup(border, rows)

    def _summary_table(self):
        """Review summary table + score box."""
        title = Text(
            "Review Summary", font=MONO, font_size=FS + 2,
            color=WHITE_T, weight=BOLD,
        )

        data = [
            ("Compilation", "Success", GREEN),
            ("Page Count", "4", GREEN),
            ("Verification", "0 issues", GREEN),
            ("Citations", "7 valid, 0 suspect", GREEN),
            ("Figures", "2 analyzed, 0 issues", GREEN),
            ("Tables", "3 analyzed, 0 issues", GREEN),
            ("Visual Quality", "88/100 (3 rounds)", GREEN),
        ]

        tbl = VGroup()
        # Header
        tbl.add(self._tbl_row("Check", "Result", "Status", GRAY, GRAY))
        tbl.add(Text("─" * 48, font=MONO, font_size=FS - 2, color=TERM_BORDER))

        for check, result, color in data:
            tbl.add(self._tbl_row(check, result, "✓", LIGHT, color))

        tbl.add(Text("─" * 48, font=MONO, font_size=FS - 2, color=TERM_BORDER))
        tbl.arrange(DOWN, buff=0.06, aligned_edge=LEFT)

        # Score box
        sc = self._row([("Overall Score: ", WHITE_T), ("98/100", GREEN)])
        sl = Text(
            "Excellent - Ready for submission",
            font=MONO, font_size=FS - 1, color=GREEN,
        )
        sc_content = VGroup(sc, sl).arrange(DOWN, buff=0.12)
        sc_border = RoundedRectangle(
            corner_radius=0.1,
            width=sc_content.width + 0.5, height=sc_content.height + 0.3,
            stroke_color=GREEN, stroke_width=1.5, fill_opacity=0,
        )
        sc_border.move_to(sc_content)
        sc_box = VGroup(sc_border, sc_content)

        return VGroup(title, tbl, sc_box).arrange(DOWN, buff=0.3)

    def _shield(self):
        """Shield logo with T and checkmark."""
        body = RoundedRectangle(
            corner_radius=0.15, width=1.0, height=1.3,
            fill_color=BLUE, fill_opacity=0.15,
            stroke_color=BLUE, stroke_width=3,
        )
        point = Polygon(
            body.get_corner(DL) + RIGHT * 0.05,
            body.get_bottom() + DOWN * 0.3,
            body.get_corner(DR) + LEFT * 0.05,
            fill_color=BLUE, fill_opacity=0.15,
            stroke_color=BLUE, stroke_width=3,
        )
        shape = VGroup(body, point)
        t = Text("T", font="Georgia", font_size=40,
                 color=BLUE, weight=BOLD, slant=ITALIC)
        t.move_to(shape.get_center() + UP * 0.05)
        chk = VMobject(color=GREEN, stroke_width=4)
        chk.set_points_as_corners([
            shape.get_center() + LEFT * 0.2 + DOWN * 0.1,
            shape.get_center() + DOWN * 0.25,
            shape.get_center() + RIGHT * 0.3 + UP * 0.2,
        ])
        return VGroup(shape, t, chk)

    def _badge(self, label, color):
        """Rounded pill badge."""
        txt = Text(label, font=SANS, font_size=20, color=WHITE, weight=BOLD)
        bg = RoundedRectangle(
            corner_radius=0.12,
            width=txt.width + 0.5, height=txt.height + 0.35,
            fill_color=color, fill_opacity=0.9, stroke_width=0,
        )
        return VGroup(bg, txt)

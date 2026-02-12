# TexGuardian Demo Recording Script

## Pre-recording Setup

```bash
# Terminal: 120 cols x 36 rows minimum, dark theme, 14-16pt monospace font
# Working directory:
cd demo/test_run

# Ensure TinyTeX is on PATH:
export PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$PATH"

# Ensure credentials are set:
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

## Current Demo Paper State

The `demo_paper.tex` has these **remaining issues** (everything else is clean):

| Category | Issue | Location |
|----------|-------|----------|
| Figure overflow | Architecture diagram nodes at x=-6..6, `\hspace{-1cm}` | Fig 1 |
| Figure overflow | Expert chart `width=1.5\columnwidth` | Fig 2 |
| Table overflow | 9-column comparison table, `\hline` | Tab 1 |
| Table overflow | 8-column results table, `\hline` | Tab 2 |
| Table formatting | Ablation table uses `\hline` not booktabs | Tab 3 |

Title, abstract, citations, and TODO markers are all clean.

---

## Recording Options

### Option A: macOS screen recording (simplest)

Built into macOS, no install needed. Records your screen as a `.mov` video file.

**How it works**: macOS Screenshot toolbar lets you record the whole screen or a
selected window. The recording is saved to your Desktop as a `.mov` file which
you can then trim in QuickTime or convert to MP4/GIF with ffmpeg.

```
1. Press Cmd+Shift+5          — opens the Screenshot toolbar at bottom of screen
2. Click "Record Selected Portion" or "Record Entire Screen"
3. Select your terminal window
4. Click "Record"
5. Run the demo commands
6. Click the Stop button in the menu bar (or Cmd+Shift+5 again)
7. Recording saves to ~/Desktop/Screen Recording YYYY-MM-DD.mov
```

To convert to MP4 or GIF afterward:

```bash
# Convert .mov to .mp4
ffmpeg -i ~/Desktop/"Screen Recording 2026-02-13.mov" demo.mp4

# Convert to GIF (for README embeds)
ffmpeg -i demo.mp4 -vf "fps=10,scale=800:-1" -loop 0 demo.gif
```

### Option B: VHS (automated terminal GIF/MP4)

[VHS](https://github.com/charmbracelet/vhs) is a tool by Charm that reads a
`.tape` script file and produces a terminal recording automatically. It types
commands, waits for output, and renders the result as a GIF or MP4. No manual
interaction needed — the recording is fully scripted and reproducible.

**How it works**: You write a `.tape` file with commands like `Type`, `Enter`,
`Sleep`. VHS launches a headless terminal, replays those commands, captures each
frame, and encodes them into a GIF/MP4. This means every recording is identical
and can be re-generated from the script.

```bash
# Install VHS (requires Go and ffmpeg)
brew install vhs

# Run the demo tape — produces demo.gif and demo.mp4
cd demo/
vhs demo.tape
```

The `demo.tape` file in this repo is pre-configured with the full demo flow,
terminal theme (Catppuccin Mocha), font size, and timing. Edit it to adjust
sleep durations or commands.

### Option C: asciinema (interactive terminal recording)

[asciinema](https://asciinema.org) records your terminal session as a lightweight
`.cast` file (just text + timestamps, not pixels). You can replay it in the
browser, embed it on a website, or convert it to a GIF. The recording captures
exactly what you see in the terminal, including colors and cursor movement.

**How it works**: asciinema hooks into your shell's PTY (pseudo-terminal) and
records every byte of output along with precise timestamps. The `.cast` file is
a plain-text format (JSON lines) that can be replayed at any speed, paused, and
even copied from. You can share recordings on asciinema.org or self-host.

```bash
# Install
brew install asciinema              # macOS
sudo apt install asciinema          # Ubuntu

# Record — launches texguardian chat and records everything
cd demo/test_run
asciinema rec ../demo.cast -c "texguardian chat"
# Run your demo commands interactively...
# Press Ctrl+D or type /exit to stop recording

# Replay locally
asciinema play ../demo.cast

# Upload to asciinema.org (creates a shareable URL)
asciinema upload ../demo.cast

# Convert to GIF (requires agg, the asciinema GIF generator)
brew install agg
agg ../demo.cast ../demo.gif
```

**Pros over screen recording**: tiny file size (~50 KB vs 50 MB), text is
selectable/searchable in playback, resolution-independent, can speed up/slow
down playback. **Cons**: only captures terminal output (no GUI windows like
PDF Preview).

---

## Demo Flow: Review Pipeline (~2 minutes)

Run these in order inside `demo/test_run/`.

### 1. Start chat session

```bash
texguardian chat
```

Welcome panel appears with paper stats (title, venue, model, figures, tables).

### 2. Run the full review pipeline

```
/review full
```

This is the centerpiece. The 7-step pipeline runs:

1. **Step 1/7: Compile** -- builds the PDF
2. **Step 2/7: Verify** -- finds `\hline` usage, figure overflow warnings
3. **Step 3/7: Citations** -- validates all references (should be clean)
4. **Step 4/7: Figures** -- detects overflow, generates patches to fix widths and positioning
5. **Step 5/7: Tables** -- detects `\hline`, generates patches to convert to booktabs
6. **Step 6/7: Visual verification** -- recompiles, renders PDF, vision model confirms fixes look correct
7. **Step 7/7: Visual polish** -- full vision loop for any remaining layout issues

When prompted for patches: type **`a`** to apply all.

The pipeline loops until score >= 90 or max rounds reached.

### 3. Open the fixed PDF

```
/bash open build/demo_paper.pdf
```

Opens the compiled PDF in Preview -- audience sees the polished result.

### 4. Exit

```
/exit
```

---

## Quick Demo: Individual Commands (~1 minute)

If you prefer showing commands one by one:

### 1. Start chat

```bash
texguardian chat
```

### 2. Fix figures

```
/figures fix
```

LLM analyzes figures, generates patches:
- `width=1.5\columnwidth` -> `width=\columnwidth`
- Fixes TikZ node overflow, removes `\hspace{-1cm}`

When prompted: type **`a`** to apply all patches.
Step 3 (visual verification) then recompiles and vision-checks the fixes.

### 3. Fix tables

```
/tables fix
```

LLM replaces `\hline` with booktabs (`\toprule`, `\midrule`, `\bottomrule`).
Reduces wide tables, fixes column separators (`|` -> spacing).

When prompted: type **`a`** to apply.
Step 3 (visual verification) confirms tables render correctly.

### 4. Compile and view

```
/compile
/bash open build/demo_paper.pdf
```

### 5. Exit

```
/exit
```

---

## Extended Demo: Natural Language + Review (~3 minutes)

```
texguardian chat

# Show the verify check first
/verify

# Fix figures with natural language
Fix all overflowing figures — scale them to fit within column width
# approve with 'a'

# Fix tables
/tables fix
# approve with 'a'

# Run full review to verify everything
/review quick

# Show final result
/compile
/bash open build/demo_paper.pdf
/exit
```

---

## Key Points to Highlight

1. **7-step review pipeline** -- compile -> verify -> citations -> figures -> tables -> visual verify -> visual polish
2. **Compile-verify-fix loop** -- after fixing, it recompiles and vision-checks the result
3. **Diff patches before apply** -- `[A]pply all | [R]eview | [N]o` prompt
4. **Checkpoints** -- created automatically before every patch
5. **Natural language** -- type plain English instructions alongside slash commands
6. **Everything in the terminal** -- no GUI, no browser

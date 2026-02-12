# TexGuardian Demo Recording Script

## Pre-recording Setup

```bash
# Terminal: 120 cols x 36 rows minimum, dark theme, 14-16pt monospace font
# Working directory:
cd demo/test_run

# Ensure credentials are set:
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

---

## Recording Options

### Option A: VHS (automated terminal GIF/MP4) — recommended

```bash
cd demo/
vhs demo.tape
# Produces demo.gif and demo.mp4
```

### Option B: macOS screen recording

```
Cmd+Shift+5 → select terminal window → Start Recording
```

### Option C: asciinema

```bash
brew install asciinema
cd demo/test_run
asciinema rec ../demo.cast -c "texguardian chat"
# Ctrl+D to stop

# Convert to GIF:
# agg ../demo.cast ../demo.gif --theme monokai
```

---

## Demo Commands

Run these in order inside `demo/test_run/`.

### 1. Doctor check (optional, quick)

```bash
texguardian doctor
```

Shows all 4 external tools found. Confirms installation works.

### 2. Start chat

```bash
texguardian chat
```

Welcome panel appears with:
- Paper: "Scaling Sparse Mixture-of-Experts for Long-Context..."
- Venue: ICLR 2026, Deadline: 2026-01-23
- Model: claude opus 4.5, Provider: bedrock
- File: demo_paper.tex, Figures 2, Tables 3

### 3. Verify — show all issues

```
/verify
```

Outputs a table with 6 checks:

| Check | Status | Issue |
|-------|--------|-------|
| citations | FAIL | 15 citations, 4 undefined |
| figure_references | WARN | 2 unreferenced figures |
| citation_format | WARN | Uses \cite{} instead of \citep{} |
| todo_remaining | FAIL | TODO/FIXME/XXX markers found |
| figure_overflow | FAIL | width=1.5\columnwidth overflows |
| hline_usage | WARN | \hline instead of booktabs |

### 4. Fix figures

```
/figures fix
```

LLM analyzes figures, generates patches:
- `width=1.5\columnwidth` → `width=\columnwidth`
- Fixes `\hspace{-1cm}` architecture diagram overflow

When prompted: type **`a`** to apply all patches.

### 5. Fix tables

```
/tables fix
```

LLM replaces all `\hline` with booktabs (`\toprule`, `\midrule`, `\bottomrule`), fixes overflowing column layouts.

When prompted: type **`a`** to apply.

### 6. Natural language — remove TODOs

```
Please remove all TODO, FIXME, and XXX comments from the paper
```

LLM generates diff patches removing the 3 comment markers.

When prompted: type **`a`** to apply.

### 7. Re-verify — show fixes

```
/verify
```

Shows reduced errors — figures fixed, tables fixed, TODOs removed.

### 8. Feedback — full paper review

```
/feedback
```

Comprehensive AI review with:
- Overall score (out of 100)
- 13 category scores (novelty, clarity, experiments, etc.)
- Acceptance prediction
- Top strengths and weaknesses

### 9. Exit

```
/exit
```

---

## Short Demo (3 minutes)

If time is limited, just run:

```
texguardian chat
/verify                    # show all 6 issues
/figures fix               # approve with 'a'
/tables fix                # approve with 'a'
/verify                    # show issues reduced
/exit
```

---

## Key Points to Highlight

1. **Welcome panel** — paper metadata at a glance, no setup needed
2. **`/verify` runs instantly** — regex-based, no compilation step
3. **Diff patches before apply** — `[A]pply all | [R]eview | [N]o` prompt
4. **Checkpoints** — created automatically before every patch
5. **Natural language** — "remove TODOs", "fix the abstract", etc.
6. **26 slash commands** — covers the entire paper lifecycle
7. **`/feedback`** — venue-aware comprehensive review with scoring
8. **Everything in the terminal** — no GUI, no browser

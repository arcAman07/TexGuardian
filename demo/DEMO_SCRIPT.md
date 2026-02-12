# TexGuardian Demo Recording Script (~1 minute)

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

### Option A: macOS screen recording (recommended for 1-min demo)

```
Cmd+Shift+5 → select terminal window → Start Recording
```

### Option B: VHS (automated terminal GIF/MP4)

```bash
cd demo/
vhs demo.tape
# Produces demo.gif and demo.mp4
```

### Option C: asciinema

```bash
brew install asciinema
cd demo/test_run
asciinema rec ../demo.cast -c "texguardian chat"
# Ctrl+D to stop
```

---

## 1-Minute Demo Commands

Run these in order inside `demo/test_run/`.

### 1. Start chat

```bash
texguardian chat
```

Welcome panel appears with paper stats (title, venue, model, figures, tables).

### 2. Set venue — download ICLR 2025 style files

```
/venue ICLR 2025
```

Downloads `iclr2025_conference.sty` and related files to the project directory.

### 3. Fix figures

```
/figures fix
```

LLM analyzes figures, generates patches:
- `width=1.5\columnwidth` → `width=\columnwidth`
- Fixes overflow issues

When prompted: type **`a`** to apply all patches.

### 4. Fix tables

```
/tables fix
```

LLM replaces `\hline` with booktabs (`\toprule`, `\midrule`, `\bottomrule`).

When prompted: type **`a`** to apply.

### 5. Compile — build the final PDF

```
/compile
```

Runs `latexmk -pdf` to produce the fixed `demo_paper.pdf`.

### 6. Open the PDF

```
/bash open build/demo_paper.pdf
```

Opens the compiled PDF in Preview — the audience sees the polished result.

### 7. Exit

```
/exit
```

---

## Extended Demo (3 minutes)

If you have more time, add these after step 4:

```
/verify                                          # show all issues
Please remove all TODO, FIXME, and XXX comments  # natural language
# approve with 'a'
/feedback                                        # full AI review with scores
/compile                                         # build final PDF
/bash open build/demo_paper.pdf                  # show result
/exit
```

---

## Key Points to Highlight

1. **Welcome panel** — paper metadata at a glance, no setup needed
2. **`/venue`** — downloads conference style files in one command
3. **Diff patches before apply** — `[A]pply all | [R]eview | [N]o` prompt
4. **Checkpoints** — created automatically before every patch
5. **`/compile`** — builds the PDF, then you show the final result
6. **Everything in the terminal** — no GUI, no browser

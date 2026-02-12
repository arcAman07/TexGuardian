# TexGuardian Demo Recording Script

**Duration**: ~60 seconds
**Setup**: Use the `demo/sample_paper/` directory which has deliberate issues for the demo.

## Pre-recording Setup

```bash
cd demo/sample_paper
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_REGION="us-east-1"
```

**Terminal settings**: 120 columns wide, dark theme, large font (18pt).

**Recording tool**: [asciinema](https://asciinema.org/) or screen recording with terminal.

```bash
# Optional: record with asciinema
asciinema rec demo.cast -c "texguardian chat"
```

---

## Demo Script (60 seconds)

### 1. Start TexGuardian (5s)

```
texguardian chat
```

Wait for the welcome message to appear.

### 2. Run Verification (10s)

```
/verify
```

**Show**: The table output with PASS/FAIL/WARN for each check. Point out:
- `figure_overflow` → FAIL (width=1.4\columnwidth)
- `citation_format` → WARN (uses \cite{} instead of \citep{})
- `todo_remaining` → FAIL

### 3. Fix Figures (15s)

```
/figures fix
```

**Show**:
- Figure table listing all figures with labels, refs, status
- LLM streaming its analysis
- Patch generated: `width=1.4\columnwidth → width=\columnwidth`
- Type `a` to apply
- Checkpoint created, patch applied

### 4. Get Feedback (15s)

```
/feedback
```

**Show**:
- LLM streaming comprehensive review
- Overall score (e.g., 72/100)
- Category scores with color coding
- Acceptance predictions
- Top strengths and weaknesses

### 5. Natural Language (10s)

```
Can you suggest some missing citations for the related work section?
```

**Show**: LLM streams citation suggestions with BibTeX entries.

### 6. Venue Templates (5s)

```
/venue please download neurips 2026 style files
```

**Show**: LLM explains what will be downloaded, approval panel appears.
Type `n` to skip (just showing the flow).

---

## Key Points to Highlight

1. **Interactive terminal** — like Claude Code but for LaTeX
2. **Rich output** — tables, colors, progress spinners
3. **Reviewable patches** — every change shown as a diff before applying
4. **Safety** — checkpoints, rollback, allowlists
5. **26 commands** — covers the entire paper lifecycle
6. **Natural language** — just type what you need

## After Recording

```bash
# Convert asciinema to GIF (if using asciinema)
agg demo.cast demo.gif --theme monokai

# Or convert to SVG
svg-term --in demo.cast --out demo.svg --window
```

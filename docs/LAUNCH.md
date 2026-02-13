# TexGuardian v0.1.0 — Launch Playbook

Everything you need: 60-second demo plan, GitHub push, PyPI upload, and platform-by-platform launch content.

---

## 1. Record the 60-Second Demo GIF

### Demo Script (timed to 60 seconds)

| Time | Action | What it shows |
|------|--------|---------------|
| 0-5s | `texguardian chat` | Welcome panel with paper title, venue, model |
| 5-15s | `>>> /verify` | Rich verification table (PASS/FAIL/WARN) |
| 15-30s | `>>> /figures fix` | LLM streams patch, `[A]pply / [R]eview / [N]o`, press `a`, checkpoint + applied |
| 30-40s | `>>> /citations validate` | Real CrossRef/S2 validation, shows valid/suspect counts |
| 40-50s | `>>> Can you make the introduction more concise?` | Natural language, LLM streams, patch offered |
| 50-60s | `>>> /feedback` | Overall score 72/100 with breakdown |

### Recording with VHS (best for GIF — scripted, reproducible)

```bash
# Install VHS
brew install charmbracelet/tap/vhs

# Create demo.tape
cat > demo.tape << 'TAPE'
Output demo.gif
Set FontSize 15
Set Width 1200
Set Height 700
Set Theme "Catppuccin Mocha"
Set TypingSpeed 40ms
Set Shell "bash"

Type "cd examples/esolang_paper && texguardian chat"
Enter
Sleep 3s

Type "/verify"
Enter
Sleep 4s

Type "/figures fix"
Enter
Sleep 6s
Type "a"
Enter
Sleep 3s

Type "/citations validate"
Enter
Sleep 5s

Type "Can you make the introduction more concise?"
Enter
Sleep 8s

Type "/feedback"
Enter
Sleep 5s

Type "/exit"
Enter
TAPE

# Record
vhs demo.tape
# Output: demo.gif
```

### Alternative: asciinema (for embeddable player)

```bash
brew install asciinema
cd examples/esolang_paper
asciinema rec demo.cast
# Run the demo script manually, Ctrl+D to stop
asciinema upload demo.cast
# Gets you a shareable URL like: https://asciinema.org/a/xxxxx
```

### Alternative: Screen recording (for Twitter/LinkedIn video)

```bash
# Terminal setup:
#   Font: JetBrains Mono or SF Mono, 16pt
#   Window: 120 cols x 35 rows
#   Theme: dark (matches brand)

# macOS: Cmd+Shift+5 → Record Selected Portion
# Convert to GIF: ffmpeg -i demo.mov -vf "fps=15,scale=800:-1" demo.gif
```

### After recording

1. Add the GIF to `docs/assets/demo.gif`
2. Add to README.md under the hero section:
   ```markdown
   <p align="center">
     <img src="docs/assets/demo.gif" alt="TexGuardian demo" width="800">
   </p>
   ```

---

## 2. Push to GitHub

```bash
cd path/to/TexGuardian

# Initialize git
git init
git add .
git commit -m "v0.1.0: Initial release of TexGuardian

AI-powered terminal assistant for LaTeX academic papers.
26 slash commands, LLM-powered fixes, citation validation,
visual polish, checkpoint safety."

# Create the repo on GitHub first, then:
git remote add origin https://github.com/texguardian/texguardian.git
git branch -M main
git push -u origin main

# Create the release tag
git tag -a v0.1.0 -m "v0.1.0: Initial release"
git push origin v0.1.0
```

### Create a GitHub Release

```bash
gh release create v0.1.0 \
  --title "v0.1.0 — Initial Release" \
  --notes "$(cat << 'EOF'
# TexGuardian v0.1.0

**Claude Code, but for LaTeX academic papers.**

## Highlights
- 26 slash commands for every stage of paper preparation
- LLM-powered fixes via Claude (AWS Bedrock or OpenRouter)
- Citation validation against CrossRef and Semantic Scholar
- Visual polish using vision model on rendered PDF pages
- Checkpoint safety with instant rollback
- Natural language — just describe what you want

## Install
```bash
git clone https://github.com/texguardian/texguardian.git
cd texguardian && pip install -e .
texguardian doctor
```

See [GUIDE.md](docs/GUIDE.md) for full documentation.
EOF
)"
```

### Enable GitHub Pages (for the website)

1. Go to repo Settings > Pages
2. Source: Deploy from a branch
3. Branch: `main`, folder: `/docs`
4. Save — site will be at `https://texguardian.github.io/texguardian`

---

## 3. Upload to PyPI (Python Package Index)

This lets anyone install TexGuardian with `pip install texguardian`.

### One-time setup

```bash
# Install build + upload tools
pip install build twine

# Create a PyPI account at https://pypi.org/account/register/
# Create an API token at https://pypi.org/manage/account/token/
#   Scope: "Entire account" for first upload, then restrict to project

# Save token (choose one method):

# Method A: ~/.pypirc file
cat > ~/.pypirc << 'EOF'
[pypi]
username = __token__
password = pypi-YOUR_TOKEN_HERE
EOF
chmod 600 ~/.pypirc

# Method B: Environment variable
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=pypi-YOUR_TOKEN_HERE
```

### Build and upload

```bash
cd path/to/TexGuardian

# Clean previous builds
rm -rf dist/ build/ *.egg-info src/*.egg-info

# Build sdist and wheel
python -m build

# Verify the package looks correct
twine check dist/*

# Upload to Test PyPI first (optional but recommended)
twine upload --repository testpypi dist/*
# Test install: pip install -i https://test.pypi.org/simple/ texguardian

# Upload to real PyPI
twine upload dist/*
```

### Verify it works

```bash
# In a clean environment
python -m venv /tmp/pypi-test
source /tmp/pypi-test/bin/activate
pip install texguardian
texguardian --help
texguardian doctor
deactivate
rm -rf /tmp/pypi-test
```

### After PyPI upload

Update README badge:
```markdown
<img src="https://img.shields.io/pypi/v/texguardian.svg" alt="PyPI">
```

Update install instructions in README and website:
```bash
# Before (from source):
git clone ... && pip install -e .

# After (from PyPI):
pip install texguardian
```

---

## 4. Platform Launch Content

### Twitter/X — Thread (6 tweets)

**Tweet 1 (main — attach demo GIF):**
```
Introducing TexGuardian — Claude Code, but for LaTeX papers.

An open-source CLI that reads your paper, understands venue requirements, and fixes issues through reviewable diff patches.

26 commands. Checkpoint safety. Real citation validation.

github.com/texguardian/texguardian
```

**Tweet 2:**
```
/verify scans your paper for figure overflows, undefined citations, TODO markers, and custom checks you define in paper_spec.md.

A pre-reviewer that catches issues before the real reviewers do.
```

**Tweet 3:**
```
/figures fix and /citations fix use Claude to generate targeted diff patches.

Every edit is shown as a reviewable diff before applying. Checkpoints let you rollback instantly.
```

**Tweet 4:**
```
/citations validate checks your bibliography against CrossRef and Semantic Scholar.

Finds hallucinated references, outdated entries, and missing citations.
```

**Tweet 5:**
```
/polish_visual renders your PDF and sends pages to a vision model.

Catches layout issues text-only analysis misses: overlapping figures, bad spacing, misaligned columns.
```

**Tweet 6:**
```
Or just type in plain English:

"Fix the figure overflow on line 303"
"Make this anonymous for double-blind review"
"Suggest more citations for related work"

pip install texguardian
github.com/texguardian/texguardian
```

**Hashtags (add to tweet 1):** `#LaTeX #AcademicWriting #OpenSource #NeurIPS #ICML #ResearchTools #AI`

---

### Reddit

**Where to post:**

| Subreddit | Title | Angle |
|-----------|-------|-------|
| r/MachineLearning | `[P] TexGuardian — Open-source CLI that uses Claude to verify and fix LaTeX papers` | Technical, show /verify output |
| r/LaTeX | `TexGuardian — AI-powered CLI for verifying and fixing LaTeX papers` | Figure fixes, compilation, visual polish |
| r/PhD | `Built a tool that automates the tedious parts of paper submission prep` | Personal story, time saved |
| r/Python | `TexGuardian — A Claude Code-style REPL for LaTeX papers (Python, 26 commands)` | Architecture, CLI design |
| r/ClaudeAI | `Built a "Claude Code for LaTeX" — open source CLI for academic papers` | Claude integration angle |
| r/CommandLine | `Show r/CommandLine: TexGuardian — interactive REPL for LaTeX papers with 26 slash commands` | REPL, diff patches, CLI design |
| r/AcademicPapers | `Tool for automating paper submission checks (citations, figures, anonymization)` | Quality/verification angle |

**r/MachineLearning post body:**

```
I built an open-source tool that helps researchers prepare LaTeX papers for
conference submission. Think of it as Claude Code, but specifically for LaTeX.

**What it does:**
- `/verify` — automated checks for citations, figures, tables, page limits, custom rules
- `/figures fix` and `/citations fix` — LLM generates reviewable diff patches
- `/citations validate` — checks .bib against CrossRef and Semantic Scholar
- `/polish_visual` — renders PDF, sends to vision model, catches layout issues
- `/anonymize` and `/camera_ready` — submission prep
- Natural language: "fix the figure overflow on line 303"

**Key design decisions:**
- Every edit is a reviewable unified diff — you approve before anything changes
- Checkpoints before every modification, instant rollback with `/revert`
- Custom checks in `paper_spec.md` (regex patterns with severity levels)
- Works with any LaTeX paper, 12+ conference templates built in

Built with Python. Uses AWS Bedrock or OpenRouter for LLM calls (Claude Opus 4.5).

`pip install texguardian` or GitHub: github.com/texguardian/texguardian

Happy to answer questions or take feature requests.
```

---

### Hacker News

**Title:** `Show HN: TexGuardian – Claude Code, but for LaTeX academic papers`

**Body:**
```
TexGuardian is a researcher-focused CLI tool that helps you write, verify, and
polish LaTeX papers for conference submission.

It reads your paper, understands venue requirements (NeurIPS, ICML, ICLR, etc.),
and fixes issues through reviewable diff patches with checkpoint safety.

26 slash commands covering the full paper lifecycle:
- Verification (citations, figures, tables, custom checks)
- LLM-powered fixes with interactive approval
- Citation validation against CrossRef and Semantic Scholar
- Visual polish using a vision model on rendered PDF pages
- Anonymization and camera-ready preparation

Every edit is a reviewable diff. Checkpoints before every change. Instant rollback.

Built with Python, MIT license. Uses AWS Bedrock or OpenRouter for LLM access.

pip install texguardian
GitHub: https://github.com/texguardian/texguardian
```

---

### LinkedIn

```
Sharing TexGuardian — an open-source CLI tool I built for researchers preparing
LaTeX papers for conference submission.

The problem: Getting a paper submission-ready involves dozens of tedious checks.
Figure overflows, undefined citations, TODO markers, anonymization, page limits.
It's error-prone and time-consuming.

The solution: TexGuardian acts as an AI-powered pre-reviewer. It reads your
paper, runs automated checks, validates citations against real databases
(CrossRef, Semantic Scholar), and generates targeted fixes as reviewable
diff patches.

Key features:
- 26 slash commands for every stage of paper preparation
- LLM-powered analysis and fixes (Claude via AWS Bedrock or OpenRouter)
- Citation validation against real academic databases
- Visual polish using a vision model on rendered PDF pages
- Checkpoint safety with instant rollback
- Natural language — just describe what you want

Every edit is shown as a diff before applying. Your paper is always safe.

pip install texguardian
github.com/texguardian/texguardian

#OpenSource #Research #LaTeX #AcademicWriting #AI #MachineLearning #NeurIPS #ICML
```

---

### Discord

**Servers:**

| Server | Channel |
|--------|---------|
| MLOps Community | #tools |
| Weights & Biases | #show-and-tell |
| Hugging Face | #cool-projects |
| Anthropic/Claude | #projects |
| Python Discord | #show-your-projects |
| EleutherAI | #general |
| LaTeX Discord | #showcase |

**Message:**

```
**TexGuardian** — Claude Code, but for LaTeX papers

Open-source CLI that helps researchers prepare LaTeX papers for submission.

- 26 slash commands (verify, figures, citations, anonymize, camera-ready...)
- LLM-powered fixes as reviewable diff patches
- Citation validation against CrossRef & Semantic Scholar
- Visual polish with vision model
- Checkpoint safety + instant rollback

Works with any LaTeX paper. Supports NeurIPS, ICML, ICLR, and 10+ venues.

`pip install texguardian`
GitHub: <https://github.com/texguardian/texguardian>
```

---

## 5. Next Steps — Ordered Checklist

### Day 0: Prepare

- [ ] Record the 60-second demo GIF using VHS or asciinema
- [ ] Add `demo.gif` to `docs/assets/` and embed in README
- [ ] Push code to GitHub
- [ ] Create GitHub release `v0.1.0`
- [ ] Enable GitHub Pages (Settings > Pages > main branch, /docs folder)
- [ ] Upload to PyPI (`python -m build && twine upload dist/*`)
- [ ] Verify `pip install texguardian` works in a clean venv

### Day 1: Launch (Tuesday-Thursday, 8-10 AM ET)

- [ ] Post Twitter/X thread with demo GIF attached to tweet 1
- [ ] Submit to Hacker News (Show HN)
- [ ] Post to r/MachineLearning

### Day 2: Expand

- [ ] Post to r/LaTeX
- [ ] Post to r/PhD
- [ ] Post to r/Python
- [ ] Share in Discord servers (Anthropic, HF, W&B, Python)

### Day 3: Professional

- [ ] Post LinkedIn article
- [ ] Post to r/ClaudeAI and r/CommandLine
- [ ] Submit PR to awesome-python, awesome-cli-apps

### Week 2: Follow-up

- [ ] Respond to all GitHub issues and comments
- [ ] Write a blog post about the architecture (optional)
- [ ] Submit to Product Hunt (optional)
- [ ] Record a longer 5-min tutorial video (optional)

---

## 6. Launch Timing

| Platform | Best day | Best time (ET) | Notes |
|----------|----------|----------------|-------|
| Hacker News | Tue-Thu | 8-10 AM | Peak US morning reading |
| Twitter/X | Tue-Thu | 8-10 AM or 12-2 PM | Two engagement peaks |
| r/MachineLearning | Tue-Wed | 9-11 AM | Research crowd online |
| r/LaTeX | Any weekday | 10 AM - 2 PM | Smaller sub, less timing-sensitive |
| LinkedIn | Tue-Thu | 7-9 AM | Professional morning scroll |
| Discord | Tue-Thu | 11 AM - 3 PM | US+EU overlap |

**Rule:** Don't post everywhere at once. Stagger over 3 days so you can engage with comments on each platform.

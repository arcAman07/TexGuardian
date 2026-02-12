# TexGuardian v0.1.0 — Release Playbook

## 1. Record the 60-Second Demo GIF

### Script (6 commands, 60 seconds)

```
0:00  texguardian chat              → Welcome panel (paper, venue, model)
0:05  >>> /verify                   → Rich table: PASS/FAIL/WARN checks
0:15  >>> /figures fix              → LLM streams fix, [A]pply/[R]eview/[N]o, press 'a'
0:30  >>> /citations validate       → Live CrossRef/S2 API validation
0:40  >>> Can you tighten the intro? → Natural language, LLM streams response
0:50  >>> /feedback                 → Overall score 72/100 with breakdown
1:00  done
```

### Record with VHS (produces GIF automatically)

```bash
brew install charmbracelet/tap/vhs

cat > demo.tape << 'TAPE'
Output docs/assets/demo.gif
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

Type "Can you tighten the introduction?"
Enter
Sleep 8s

Type "/feedback"
Enter
Sleep 5s

Type "/exit"
Enter
TAPE

vhs demo.tape
```

### Or record manually with asciinema

```bash
brew install asciinema
cd examples/esolang_paper
asciinema rec demo.cast    # run the commands, Ctrl+D to stop
asciinema upload demo.cast # get shareable link
```

### Or screen-record for video (Twitter/LinkedIn)

```bash
# Terminal: JetBrains Mono 16pt, 120x35, dark theme
# macOS: Cmd+Shift+5
# Convert: ffmpeg -i demo.mov -vf "fps=15,scale=800:-1" demo.gif
```

### After recording, add to README

```markdown
<p align="center">
  <img src="docs/assets/demo.gif" alt="TexGuardian demo" width="800">
</p>
```

---

## 2. Push to GitHub

```bash
cd /path/to/TeXGuardian
git init
git add .
git commit -m "v0.1.0: Initial release — AI-powered LaTeX paper assistant"
git remote add origin https://github.com/texguardian/texguardian.git
git branch -M main
git push -u origin main

git tag -a v0.1.0 -m "v0.1.0: Initial release"
git push origin v0.1.0
```

### Create GitHub Release

```bash
gh release create v0.1.0 \
  --title "v0.1.0 — Initial Release" \
  --notes "Claude Code, but for LaTeX. 26 commands, checkpoint safety, citation validation."
```

### Enable GitHub Pages (website)

Settings → Pages → Branch: main, Folder: /docs → Save
Site: https://texguardian.github.io/texguardian

---

## 3. Upload to PyPI

```bash
# One-time: create account at pypi.org, get API token
pip install build twine

# Save token
cat > ~/.pypirc << 'EOF'
[pypi]
username = __token__
password = pypi-YOUR_TOKEN_HERE
EOF
chmod 600 ~/.pypirc

# Build and upload
rm -rf dist/ build/
python -m build
twine check dist/*
twine upload dist/*

# Verify
python -m venv /tmp/test && source /tmp/test/bin/activate
pip install texguardian
texguardian --help && texguardian doctor
deactivate && rm -rf /tmp/test
```

---

## 4. Post Content (copy-paste ready)

### TWITTER/X — Thread (attach demo GIF to tweet 1)

**Tweet 1:**

```
Introducing TexGuardian — Claude Code, but for LaTeX papers.

Open-source CLI that reads your paper, understands venue requirements, and fixes issues through reviewable diff patches.

26 commands. Checkpoint safety. Real citation validation against CrossRef & Semantic Scholar.

Built for researchers, by researchers.

pip install texguardian
github.com/texguardian/texguardian

#LaTeX #AcademicWriting #OpenSource #NeurIPS #ICML #AI #ResearchTools
```

**Tweet 2:**

```
/verify scans your entire paper in seconds:

→ Figure overflows
→ Undefined citations
→ TODO/FIXME markers
→ Custom checks you define in paper_spec.md

Think of it as a pre-reviewer that catches issues before the real reviewers do.
```

**Tweet 3:**

```
/figures fix and /citations fix use Claude to generate targeted diff patches.

Every edit is shown as a reviewable diff before applying.

Checkpoints before every change. /revert rolls back instantly.

Your paper is always safe.
```

**Tweet 4:**

```
/citations validate checks your .bib against CrossRef and Semantic Scholar.

Finds:
→ Hallucinated references
→ Outdated entries
→ Missing DOIs
→ Suggested corrections

No more "citation not found" from reviewers.
```

**Tweet 5:**

```
/polish_visual renders your PDF and sends pages to a vision model.

Catches layout issues that text-only analysis misses:
→ Overlapping figures
→ Bad column spacing
→ Misaligned tables
→ Orphaned section headers
```

**Tweet 6:**

```
Or just type in plain English:

"Fix the figure overflow on line 303"
"Make this anonymous for double-blind review"
"Suggest more citations for the related work section"

The LLM reads your paper, understands context, and generates fixes.

Try it: pip install texguardian
github.com/texguardian/texguardian
```

---

### REDDIT — r/MachineLearning

**Title:** `[P] TexGuardian — Open-source CLI that uses Claude to verify and fix LaTeX papers`

**Body:**

```
I built an open-source tool that helps researchers prepare LaTeX papers for conference submission. Think of it as Claude Code, but specifically for LaTeX.

**What it does:**

- `/verify` — automated checks for citations, figures, tables, page limits, and custom regex rules
- `/figures fix` and `/citations fix` — Claude generates reviewable diff patches for issues it finds
- `/citations validate` — checks your .bib against CrossRef and Semantic Scholar APIs (finds hallucinated references)
- `/polish_visual` — renders your PDF and sends pages to a vision model to catch layout issues
- `/anonymize` — strips author info for double-blind review
- `/camera_ready` — converts draft to final submission format
- `/feedback` — gives your paper an overall score with category breakdown
- Or just type in plain English: "fix the figure overflow on line 303"

**Design philosophy:**

- Every edit is a reviewable unified diff — you approve before anything changes
- Checkpoints created before every modification, instant rollback with `/revert`
- Custom checks defined in `paper_spec.md` (regex patterns with severity levels)
- 26 slash commands covering the full paper lifecycle
- Works with any LaTeX paper, built-in template support for NeurIPS, ICML, ICLR, AAAI, CVPR, ACL, and 6 more

Built with Python 3.11+. Uses AWS Bedrock or OpenRouter for LLM calls (Claude Opus 4.5 by default). MIT license.

`pip install texguardian`

GitHub: https://github.com/texguardian/texguardian

Demo in the video above. Happy to answer questions about the architecture or take feature requests.
```

---

### REDDIT — r/LaTeX

**Title:** `TexGuardian — AI-powered CLI for verifying and fixing LaTeX papers`

**Body:**

```
Built an open-source CLI that acts as an AI pre-reviewer for your LaTeX papers.

LaTeX-specific features:

- `/verify` — checks figure overflows (e.g. `width=1.4\columnwidth`), undefined `\ref{}`, citation issues, custom regex rules
- `/figures fix` — detects width/placement issues and generates diff patches to fix them
- `/tables fix` — checks booktabs usage, column overflow, missing captions
- `/compile` — runs latexmk with proper error reporting
- `/polish_visual` — renders your PDF to images, sends to a vision model, catches overlapping figures, bad spacing, misaligned columns
- `/venue neurips 2026` — downloads conference style files from GitHub
- `/page_count` — section breakdown with page limit check

Every edit is shown as a unified diff you review before applying. Checkpoints before every change, instant rollback.

Works with pdflatex, xelatex, lualatex. Supports NeurIPS, ICML, ICLR, AAAI, CVPR, ECCV, ACL, EMNLP, and more.

`pip install texguardian`

GitHub: https://github.com/texguardian/texguardian
```

---

### REDDIT — r/PhD

**Title:** `Built a tool that automates the tedious parts of paper submission prep`

**Body:**

```
If you've ever spent hours before a deadline fixing figure overflows, hunting down undefined citations, removing TODO markers, and making sure your paper is anonymized — I built a tool for that.

TexGuardian is an open-source CLI that reads your LaTeX paper and helps you fix issues through an interactive chat. You can use slash commands or just describe what you want in plain English.

What saved me the most time:

- `/verify` catches figure overflows, citation issues, TODOs, and page limit violations in one scan
- `/citations validate` checks your bibliography against CrossRef and Semantic Scholar — finds fake or outdated references before reviewers do
- `/anonymize` strips author names, affiliations, acknowledgments for double-blind review
- `/camera_ready` converts your anonymous draft to camera-ready format
- `/feedback` gives you an overall score with breakdown (structure, writing, technical depth, citations)

Everything is a reviewable diff. Checkpoints mean you can always roll back. No surprises.

Free and open source (MIT license). You just need Python and your own LLM API key (AWS Bedrock or OpenRouter).

`pip install texguardian`

GitHub: https://github.com/texguardian/texguardian
```

---

### REDDIT — r/Python

**Title:** `TexGuardian — Claude Code-style REPL for LaTeX papers (Python 3.11+, 26 commands, 256 tests)`

**Body:**

```
Built a research-focused CLI tool in Python that helps researchers prepare LaTeX papers for conference submission.

**Architecture highlights:**

- Typer CLI with `init`, `chat`, `doctor` subcommands
- prompt_toolkit REPL with tab completion, history search, paste handling via `patch_stdout`
- Rich for all terminal output — tables, panels, syntax-highlighted diffs, spinners
- Fully async — streaming LLM responses, concurrent citation validation with semaphore
- Unified diff patch system: `extract_patches()` → `PatchValidator` → `PatchApplier` with checkpoints
- Pluggable LLM backends: AWS Bedrock (boto3) and OpenRouter (httpx)
- 256 tests (unit + integration), CI with GitHub Actions

**Interesting design choices:**

- Every LLM edit produces a unified diff patch, never direct file writes
- `paper_spec.md` defines custom checks as regex patterns with severity levels
- Citation validator hits CrossRef and Semantic Scholar APIs concurrently
- Visual polish pipeline: .tex → latexmk → .pdf → pdftoppm → .png → vision LLM → patches → pixel diff for convergence
- Rich markup escaping on all dynamic strings to prevent injection from file paths

Python 3.11+, MIT license, hatchling build.

`pip install texguardian`

GitHub: https://github.com/texguardian/texguardian
```

---

### REDDIT — r/ClaudeAI

**Title:** `Built "Claude Code for LaTeX" — open-source CLI for academic papers`

**Body:**

```
I built TexGuardian — an open-source CLI that uses Claude to help researchers prepare LaTeX papers for conference submission.

It connects to Claude via AWS Bedrock or OpenRouter and uses it to:

- Analyze your entire paper and generate targeted diff patches for any issues
- Validate citations against CrossRef and Semantic Scholar (catches hallucinated or outdated refs)
- Send rendered PDF pages to Claude's vision model for layout quality checks
- Understand natural language requests: "make this anonymous" or "fix the figure on line 303"

The key difference from just pasting into Claude: TexGuardian reads your full .tex and .bib files, understands LaTeX structure, generates proper unified diffs, and has checkpoint safety so you can always roll back.

26 slash commands covering verification, LLM-powered fixes, anonymization, camera-ready prep, and more.

`pip install texguardian`

GitHub: https://github.com/texguardian/texguardian
```

---

### HACKER NEWS

**Title:** `Show HN: TexGuardian – Claude Code, but for LaTeX academic papers`

**Body:**

```
TexGuardian is a researcher-focused CLI that helps you write, verify, and polish LaTeX papers for conference submission.

It reads your paper, understands venue requirements (NeurIPS, ICML, ICLR, etc.), and fixes issues through reviewable diff patches with checkpoint safety.

26 slash commands covering the full paper lifecycle:

- Verification: citations, figures, tables, page limits, custom regex checks
- LLM-powered fixes with interactive [A]pply/[R]eview/[N]o approval
- Citation validation against CrossRef and Semantic Scholar APIs
- Visual polish: renders PDF, sends to vision model, catches layout issues
- Anonymization and camera-ready preparation
- Natural language: just describe what you want

Every edit is a reviewable diff. Checkpoints before every change. Instant rollback with /revert.

Built with Python 3.11+, MIT license. Uses AWS Bedrock or OpenRouter for LLM access.

pip install texguardian

https://github.com/texguardian/texguardian
```

---

### LINKEDIN

```
Sharing TexGuardian — an open-source CLI tool I built for researchers preparing LaTeX papers for conference submission.

The problem: Getting a paper submission-ready involves dozens of tedious, error-prone checks. Figure overflows, undefined citations, TODO markers left in, anonymization mistakes, page limit violations, formatting inconsistencies. Every researcher has been burned by at least one of these.

The solution: TexGuardian acts as an AI-powered pre-reviewer. It reads your full paper, runs 26 different checks, validates citations against real academic databases (CrossRef, Semantic Scholar), and generates targeted fixes as reviewable diff patches.

What makes it different:

→ Every edit is shown as a unified diff before applying — you approve or skip
→ Checkpoints created before every modification — instant rollback with /revert
→ Citation validation catches hallucinated and outdated references before reviewers do
→ Visual polish renders your PDF and uses a vision model to catch layout issues
→ Natural language: "fix the figure overflow on line 303" just works
→ 12+ conference templates built in (NeurIPS, ICML, ICLR, AAAI, CVPR, ACL...)

Built for researchers who want to focus on the research, not the formatting.

Open source (MIT): pip install texguardian
https://github.com/texguardian/texguardian

#OpenSource #Research #LaTeX #AcademicWriting #AI #MachineLearning #NeurIPS #ICML #PhD
```

---

### DISCORD (all servers)

```
**TexGuardian** — Claude Code, but for LaTeX papers

Open-source CLI that helps researchers prepare LaTeX papers for conference submission.

→ 26 slash commands: /verify, /figures fix, /citations validate, /anonymize, /camera_ready, /feedback...
→ LLM-powered fixes as reviewable diff patches (Claude via Bedrock or OpenRouter)
→ Citation validation against CrossRef & Semantic Scholar
→ Visual polish with vision model on rendered PDF pages
→ Checkpoint safety + instant rollback
→ Natural language: just describe what you want

Works with any LaTeX paper. Built-in support for NeurIPS, ICML, ICLR, and 10+ venues.

`pip install texguardian`
<https://github.com/texguardian/texguardian>
```

**Post in:** MLOps Community (#tools), Weights & Biases (#show-and-tell), Hugging Face (#cool-projects), Anthropic/Claude (#projects), Python Discord (#show-your-projects), EleutherAI (#general), LaTeX Discord (#showcase)

---

## 5. Launch Schedule

| Day | Platform | Time (ET) |
|-----|----------|-----------|
| Day 1 | Twitter/X thread + demo GIF | 8-10 AM |
| Day 1 | Hacker News (Show HN) | 8-10 AM |
| Day 1 | r/MachineLearning | 9-11 AM |
| Day 2 | r/LaTeX | 10 AM |
| Day 2 | r/PhD | 11 AM |
| Day 2 | r/Python | 12 PM |
| Day 2 | Discord (all 7 servers) | 1 PM |
| Day 3 | LinkedIn | 7-9 AM |
| Day 3 | r/ClaudeAI | 10 AM |
| Day 3 | r/CommandLine | 11 AM |

**Pick a Tuesday, Wednesday, or Thursday.** Stagger over 3 days so you can engage with comments.

---

## 6. Checklist

### Day 0: Prepare
- [ ] Record 60-second demo GIF
- [ ] Add demo.gif to docs/assets/ and embed in README
- [ ] Push code to GitHub
- [ ] Create GitHub release v0.1.0
- [ ] Enable GitHub Pages
- [ ] Upload to PyPI
- [ ] Verify `pip install texguardian` works in clean venv

### Day 1-3: Launch
- [ ] Post Twitter/X thread with demo GIF on tweet 1
- [ ] Submit to Hacker News
- [ ] Post to r/MachineLearning, r/LaTeX, r/PhD, r/Python, r/ClaudeAI
- [ ] Share in Discord servers
- [ ] Post on LinkedIn

### Week 2: Follow-up
- [ ] Respond to all GitHub issues
- [ ] Submit PRs to awesome-python, awesome-cli-apps
- [ ] Write architecture blog post (optional)
- [ ] Product Hunt submission (optional)

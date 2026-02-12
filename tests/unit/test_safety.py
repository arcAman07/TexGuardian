"""Tests for safety guards and validation."""

import tempfile
from pathlib import Path

import pytest

from texguardian.config.settings import SafetyConfig
from texguardian.patch.parser import parse_patch
from texguardian.patch.validator import PatchValidator
from texguardian.safety.allowlist import FileAccessControl


@pytest.fixture
def safety_config():
    """Create a test safety config."""
    return SafetyConfig(
        max_changed_lines=50,
        allowlist=["*.tex", "*.bib"],
        denylist=[".git/**", "*.pdf", "build/**"],
    )


@pytest.fixture
def temp_project():
    """Create temporary project directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.tex").write_text("content")
        (root / "refs.bib").write_text("@article{}")
        (root / "output.pdf").write_text("")
        (root / ".git").mkdir()
        yield root


def test_allowlist_check(safety_config):
    """Test allowlist pattern matching."""
    validator = PatchValidator(safety_config)

    # Create patches
    tex_patch = parse_patch("""--- a/main.tex
+++ b/main.tex
@@ -1,1 +1,1 @@
-old
+new
""")

    pdf_patch = parse_patch("""--- a/output.pdf
+++ b/output.pdf
@@ -1,1 +1,1 @@
-old
+new
""")

    # .tex is allowed
    result = validator.validate(tex_patch, Path("main.tex"))
    assert result.valid

    # .pdf is not in allowlist
    result = validator.validate(pdf_patch, Path("output.pdf"))
    assert not result.valid


def test_denylist_check(safety_config):
    """Test denylist pattern matching."""
    validator = PatchValidator(safety_config)

    patch = parse_patch("""--- a/.git/config
+++ b/.git/config
@@ -1,1 +1,1 @@
-old
+new
""")

    result = validator.validate(patch, Path(".git/config"))
    assert not result.valid


def test_max_lines_check(safety_config):
    """Test max changed lines limit."""
    safety_config.max_changed_lines = 5
    validator = PatchValidator(safety_config)

    # Patch with too many changes
    large_diff = "--- a/main.tex\n+++ b/main.tex\n@@ -1,10 +1,10 @@\n"
    for i in range(10):
        large_diff += f"-line{i}\n+newline{i}\n"

    patch = parse_patch(large_diff)
    result = validator.validate(patch, Path("main.tex"))

    assert not result.valid
    assert "Too many lines" in result.reason


def test_file_access_control(safety_config, temp_project):
    """Test file access control."""
    access = FileAccessControl(safety_config, temp_project)

    # Can read/write .tex (in allowlist, not in denylist)
    assert access.can_read(temp_project / "main.tex")
    assert access.can_write(temp_project / "main.tex")

    # Can read/write .bib (in allowlist, not in denylist)
    (temp_project / "refs.bib").write_text("@article{test}")
    assert access.can_read(temp_project / "refs.bib")
    assert access.can_write(temp_project / "refs.bib")

    # Cannot read .pdf (in denylist via *.pdf pattern)
    assert not access.can_read(temp_project / "output.pdf")
    assert not access.can_write(temp_project / "output.pdf")

    # Cannot read from .git (in denylist via .git/** pattern)
    assert not access.can_read(temp_project / ".git" / "config")


def test_human_review_trigger():
    """Test human review triggers in validation."""
    safety_config = SafetyConfig(
        max_changed_lines=100,
        allowlist=["*.tex"],
        denylist=[],
    )
    validator = PatchValidator(safety_config)

    # Patch that touches abstract
    patch = parse_patch("""--- a/main.tex
+++ b/main.tex
@@ -1,3 +1,3 @@
 \\begin{abstract}
-Old abstract text
+New abstract text
 \\end{abstract}
""")

    result = validator.validate(patch, Path("main.tex"))

    assert result.valid
    assert result.requires_human_review
    assert any("abstract" in r.lower() for r in result.review_reasons)

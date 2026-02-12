"""Tests for patch parsing."""

import pytest

from texguardian.patch.parser import Patch, extract_patches, parse_patch


def test_parse_simple_patch():
    """Test parsing a simple unified diff."""
    diff_text = """--- a/main.tex
+++ b/main.tex
@@ -10,3 +10,4 @@
 context before
-old line
+new line
+added line
 context after
"""

    patch = parse_patch(diff_text)

    assert patch is not None
    assert patch.file_path == "main.tex"
    assert len(patch.hunks) == 1
    assert patch.hunks[0].old_start == 10
    assert patch.hunks[0].old_count == 3
    assert patch.hunks[0].new_start == 10
    assert patch.hunks[0].new_count == 4


def test_extract_patches_from_markdown():
    """Test extracting patches from markdown code blocks."""
    text = """
Here's the fix:

```diff
--- a/intro.tex
+++ b/intro.tex
@@ -5,1 +5,1 @@
-old text
+new text
```

That should work.
"""

    patches = extract_patches(text)

    assert len(patches) == 1
    assert patches[0].file_path == "intro.tex"


def test_multiple_patches():
    """Test extracting multiple patches."""
    text = """
```diff
--- a/file1.tex
+++ b/file1.tex
@@ -1,1 +1,1 @@
-a
+b
```

```diff
--- a/file2.tex
+++ b/file2.tex
@@ -1,1 +1,1 @@
-c
+d
```
"""

    patches = extract_patches(text)

    assert len(patches) == 2
    assert patches[0].file_path == "file1.tex"
    assert patches[1].file_path == "file2.tex"


def test_lines_changed():
    """Test counting changed lines."""
    diff_text = """--- a/test.tex
+++ b/test.tex
@@ -1,5 +1,6 @@
 line1
-removed1
-removed2
+added1
+added2
+added3
 line5
"""

    patch = parse_patch(diff_text)

    # 2 removed + 3 added = 5 changed lines
    assert patch.lines_changed == 5


def test_multiple_hunks():
    """Test parsing multiple hunks."""
    diff_text = """--- a/test.tex
+++ b/test.tex
@@ -1,3 +1,3 @@
 context
-old1
+new1
 context
@@ -10,3 +10,3 @@
 context
-old2
+new2
 context
"""

    patch = parse_patch(diff_text)

    assert len(patch.hunks) == 2
    assert patch.hunks[0].old_start == 1
    assert patch.hunks[1].old_start == 10

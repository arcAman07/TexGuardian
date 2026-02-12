"""Tests for file operation commands: read, write, grep, search, bash."""

from __future__ import annotations

import asyncio
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from rich.console import Console

from texguardian.cli.commands.file_ops import (
    BashCommand,
    GrepCommand,
    ReadCommand,
    SearchCommand,
    WriteCommand,
    _is_binary,
    _is_denied,
    _is_allowed,
    _resolve_safe_path,
)
from texguardian.config.settings import TexGuardianConfig
from texguardian.core.context import ConversationContext
from texguardian.core.session import SessionState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(tmpdir: Path) -> SessionState:
    """Create a minimal session rooted at *tmpdir*."""
    config_path = tmpdir / "texguardian.yaml"
    config_path.write_text("")
    return SessionState(
        project_root=tmpdir,
        config_path=config_path,
        config=TexGuardianConfig(),
        context=ConversationContext(),
    )


def _capture_console() -> tuple[Console, StringIO]:
    """Return a Console that writes to a StringIO buffer."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=False, width=200)
    return console, buf


# ---------------------------------------------------------------------------
# _resolve_safe_path
# ---------------------------------------------------------------------------


class TestResolveSafePath:
    def test_normal_path(self, tmp_path):
        session = _make_session(tmp_path)
        result = _resolve_safe_path("main.tex", session)
        assert result is not None
        assert result == (tmp_path / "main.tex").resolve()

    def test_subdir_path(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "sections").mkdir()
        result = _resolve_safe_path("sections/intro.tex", session)
        assert result is not None

    def test_traversal_blocked(self, tmp_path):
        session = _make_session(tmp_path)
        result = _resolve_safe_path("../../../etc/passwd", session)
        assert result is None

    def test_absolute_outside_blocked(self, tmp_path):
        session = _make_session(tmp_path)
        result = _resolve_safe_path("/etc/passwd", session)
        # /etc/passwd is not under tmp_path, should be None
        assert result is None


# ---------------------------------------------------------------------------
# _is_binary
# ---------------------------------------------------------------------------


class TestIsBinary:
    def test_text_file(self, tmp_path):
        f = tmp_path / "test.tex"
        f.write_text("Hello world")
        assert _is_binary(f) is False

    def test_binary_file(self, tmp_path):
        f = tmp_path / "test.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        assert _is_binary(f) is True

    def test_nonexistent_file(self, tmp_path):
        f = tmp_path / "nope"
        assert _is_binary(f) is False


# ---------------------------------------------------------------------------
# _is_denied / _is_allowed
# ---------------------------------------------------------------------------


class TestDenyAllowList:
    def test_denied_in_denylist(self, tmp_path):
        session = _make_session(tmp_path)
        pdf = (tmp_path / "paper.pdf").resolve()
        pdf.write_bytes(b"fake")
        assert _is_denied(pdf, session) is True

    def test_denied_outside_project(self, tmp_path):
        session = _make_session(tmp_path)
        assert _is_denied(Path("/etc/passwd"), session) is True

    def test_not_denied_tex(self, tmp_path):
        session = _make_session(tmp_path)
        tex = (tmp_path / "main.tex").resolve()
        tex.write_text("hello")
        assert _is_denied(tex, session) is False

    def test_allowed_tex(self, tmp_path):
        session = _make_session(tmp_path)
        tex = (tmp_path / "main.tex").resolve()
        tex.write_text("hello")
        assert _is_allowed(tex, session) is True

    def test_not_allowed_py(self, tmp_path):
        session = _make_session(tmp_path)
        py = (tmp_path / "script.py").resolve()
        py.write_text("pass")
        assert _is_allowed(py, session) is False


# ---------------------------------------------------------------------------
# /read
# ---------------------------------------------------------------------------


class TestReadCommand:
    def test_read_normal_file(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "main.tex").write_text("line1\nline2\nline3")
        console, buf = _capture_console()
        cmd = ReadCommand()
        asyncio.run(cmd.execute(session, "main.tex", console))
        output = buf.getvalue()
        assert "line1" in output
        assert "line2" in output
        assert "line3" in output

    def test_read_no_args(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = ReadCommand()
        asyncio.run(cmd.execute(session, "", console))
        assert "Usage" in buf.getvalue()

    def test_read_missing_file(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = ReadCommand()
        asyncio.run(cmd.execute(session, "nope.tex", console))
        assert "not found" in buf.getvalue()

    def test_read_denied_file(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "secret.pdf").write_bytes(b"%PDF")
        console, buf = _capture_console()
        cmd = ReadCommand()
        asyncio.run(cmd.execute(session, "secret.pdf", console))
        # Should be denied (*.pdf in denylist) or detected as binary
        output = buf.getvalue()
        assert "denied" in output.lower() or "binary" in output.lower()

    def test_read_path_traversal(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = ReadCommand()
        asyncio.run(cmd.execute(session, "../../../etc/passwd", console))
        assert "outside" in buf.getvalue().lower()

    def test_read_binary_file(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "image.tex").write_bytes(b"\x00\x89PNG")
        console, buf = _capture_console()
        cmd = ReadCommand()
        asyncio.run(cmd.execute(session, "image.tex", console))
        assert "binary" in buf.getvalue().lower()

    def test_read_large_file_truncated(self, tmp_path):
        session = _make_session(tmp_path)
        # Write a file with 3000 lines
        content = "\n".join(f"line {i}" for i in range(3000))
        (tmp_path / "big.tex").write_text(content)
        console, buf = _capture_console()
        cmd = ReadCommand()
        asyncio.run(cmd.execute(session, "big.tex", console))
        output = buf.getvalue()
        assert "more lines" in output

    def test_read_directory(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "subdir").mkdir()
        console, buf = _capture_console()
        cmd = ReadCommand()
        asyncio.run(cmd.execute(session, "subdir", console))
        assert "Not a file" in buf.getvalue()


# ---------------------------------------------------------------------------
# /write
# ---------------------------------------------------------------------------


class TestWriteCommand:
    def test_write_no_args(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = WriteCommand()
        asyncio.run(cmd.execute(session, "", console))
        assert "Usage" in buf.getvalue()

    def test_write_denied_extension(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = WriteCommand()
        # .py is not in allowlist
        asyncio.run(cmd.execute(session, "script.py", console))
        assert "not in allowlist" in buf.getvalue()

    def test_write_path_traversal(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = WriteCommand()
        asyncio.run(cmd.execute(session, "../../evil.tex", console))
        assert "outside" in buf.getvalue().lower()

    def test_write_pdf_denied(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = WriteCommand()
        asyncio.run(cmd.execute(session, "output.pdf", console))
        output = buf.getvalue()
        # *.pdf matches denylist
        assert "denied" in output.lower() or "allowlist" in output.lower()


# ---------------------------------------------------------------------------
# /grep
# ---------------------------------------------------------------------------


class TestGrepCommand:
    def test_grep_finds_pattern(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "main.tex").write_text("line one\nTODO: fix this\nline three")
        console, buf = _capture_console()
        cmd = GrepCommand()
        asyncio.run(cmd.execute(session, "TODO", console))
        output = buf.getvalue()
        assert "TODO" in output
        assert "main.tex" in output
        assert "1 match" in output

    def test_grep_no_matches(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "main.tex").write_text("nothing interesting here")
        console, buf = _capture_console()
        cmd = GrepCommand()
        asyncio.run(cmd.execute(session, "FOOBAR", console))
        assert "No matches" in buf.getvalue()

    def test_grep_no_args(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = GrepCommand()
        asyncio.run(cmd.execute(session, "", console))
        assert "Usage" in buf.getvalue()

    def test_grep_invalid_regex(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = GrepCommand()
        asyncio.run(cmd.execute(session, "[invalid", console))
        assert "Invalid pattern" in buf.getvalue()

    def test_grep_custom_glob(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "main.tex").write_text("hello")
        (tmp_path / "refs.bib").write_text("hello bib")
        console, buf = _capture_console()
        cmd = GrepCommand()
        asyncio.run(cmd.execute(session, "hello *.bib", console))
        output = buf.getvalue()
        assert "refs.bib" in output
        # Should NOT find main.tex since glob is *.bib
        assert "main.tex" not in output

    def test_grep_skips_binary(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "data.tex").write_bytes(b"\x00binary data with TODO")
        (tmp_path / "main.tex").write_text("TODO here")
        console, buf = _capture_console()
        cmd = GrepCommand()
        asyncio.run(cmd.execute(session, "TODO *.tex", console))
        output = buf.getvalue()
        assert "main.tex" in output
        # data.tex should be skipped (binary)
        assert "data.tex" not in output

    def test_grep_skips_denied_files(self, tmp_path):
        session = _make_session(tmp_path)
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "output.tex").write_text("TODO: build artifact")
        (tmp_path / "main.tex").write_text("TODO: real match")
        console, buf = _capture_console()
        cmd = GrepCommand()
        asyncio.run(cmd.execute(session, "TODO *.tex", console))
        output = buf.getvalue()
        assert "main.tex" in output
        # build/** is in denylist
        assert "build" not in output.split("main.tex")[0]  # no build/ match before


# ---------------------------------------------------------------------------
# /search
# ---------------------------------------------------------------------------


class TestSearchCommand:
    def test_search_finds_files(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "main.tex").write_text("content")
        (tmp_path / "refs.bib").write_text("bib")
        console, buf = _capture_console()
        cmd = SearchCommand()
        asyncio.run(cmd.execute(session, "*.tex", console))
        output = buf.getvalue()
        assert "main.tex" in output
        assert "refs.bib" not in output

    def test_search_no_pattern_lists_all(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "a.tex").write_text("a")
        (tmp_path / "b.bib").write_text("b")
        console, buf = _capture_console()
        cmd = SearchCommand()
        asyncio.run(cmd.execute(session, "", console))
        output = buf.getvalue()
        assert "a.tex" in output
        assert "b.bib" in output

    def test_search_skips_denied(self, tmp_path):
        session = _make_session(tmp_path)
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")
        (tmp_path / "main.tex").write_text("tex")
        console, buf = _capture_console()
        cmd = SearchCommand()
        asyncio.run(cmd.execute(session, "", console))
        output = buf.getvalue()
        assert "main.tex" in output
        assert ".git" not in output or "config" not in output

    def test_search_shows_sizes(self, tmp_path):
        session = _make_session(tmp_path)
        (tmp_path / "small.tex").write_text("x")
        console, buf = _capture_console()
        cmd = SearchCommand()
        asyncio.run(cmd.execute(session, "*.tex", console))
        output = buf.getvalue()
        # Should show a size like "1 B" or similar
        assert "B" in output

    def test_search_no_results(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = SearchCommand()
        asyncio.run(cmd.execute(session, "*.xyz", console))
        assert "No files found" in buf.getvalue()


# ---------------------------------------------------------------------------
# /bash
# ---------------------------------------------------------------------------


class TestBashCommand:
    def test_bash_echo(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = BashCommand()
        asyncio.run(cmd.execute(session, "echo hello", console))
        assert "hello" in buf.getvalue()

    def test_bash_no_args(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = BashCommand()
        asyncio.run(cmd.execute(session, "", console))
        assert "Usage" in buf.getvalue()

    def test_bash_nonzero_exit(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = BashCommand()
        asyncio.run(cmd.execute(session, "false", console))
        assert "Exit code" in buf.getvalue()

    def test_bash_stderr(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = BashCommand()
        asyncio.run(cmd.execute(session, "echo oops >&2", console))
        assert "oops" in buf.getvalue()

    def test_bash_cwd_is_project_root(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = BashCommand()
        asyncio.run(cmd.execute(session, "pwd", console))
        # The output should contain the project root path
        output = buf.getvalue()
        assert str(tmp_path) in output or str(tmp_path.resolve()) in output

    def test_bash_invalid_command(self, tmp_path):
        session = _make_session(tmp_path)
        console, buf = _capture_console()
        cmd = BashCommand()
        asyncio.run(cmd.execute(session, "nonexistent_command_xyz_123", console))
        output = buf.getvalue()
        assert "not found" in output.lower() or "Exit code" in output

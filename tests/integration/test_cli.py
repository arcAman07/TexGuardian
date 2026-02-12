"""Integration tests for CLI commands."""

import tempfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from texguardian.cli.main import app

runner = CliRunner()


def test_init_creates_files():
    """Test that init creates config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(app, ["init", tmpdir])

        assert result.exit_code == 0
        assert (Path(tmpdir) / "texguardian.yaml").exists()
        assert (Path(tmpdir) / "paper_spec.md").exists()
        assert (Path(tmpdir) / ".texguardian").is_dir()


def test_init_force_overwrites():
    """Test that init --force overwrites existing files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # First init
        runner.invoke(app, ["init", tmpdir])

        # Write custom content
        config_path = Path(tmpdir) / "texguardian.yaml"
        config_path.write_text("custom: true")

        # Second init without force - should not overwrite
        result = runner.invoke(app, ["init", tmpdir])
        assert "already exists" in result.stdout

        # Verify custom content still there
        assert "custom: true" in config_path.read_text()

        # Init with force - should overwrite
        result = runner.invoke(app, ["init", tmpdir, "--force"])
        assert result.exit_code == 0
        assert "custom: true" not in config_path.read_text()


def test_chat_requires_config():
    """Test that chat requires texguardian.yaml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(app, ["chat", "-d", tmpdir])

        assert result.exit_code == 1
        assert "No texguardian.yaml" in result.stdout


def test_help_shows_commands():
    """Test that help shows available commands."""
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "init" in result.stdout
    assert "chat" in result.stdout

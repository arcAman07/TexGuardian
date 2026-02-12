"""Tests for configuration loading."""

import os
import tempfile
from pathlib import Path

import pytest

from texguardian.config.settings import TexGuardianConfig


def test_default_config():
    """Test default configuration values."""
    config = TexGuardianConfig()

    assert config.project.main_tex == "main.tex"
    assert config.project.output_dir == "build"
    assert config.safety.max_changed_lines == 50


def test_load_config_from_yaml():
    """Test loading configuration from YAML file."""
    yaml_content = """
project:
  main_tex: "paper.tex"
  output_dir: "output"

safety:
  max_changed_lines: 100
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()

        config = TexGuardianConfig.load(Path(f.name))

        assert config.project.main_tex == "paper.tex"
        assert config.project.output_dir == "output"
        assert config.safety.max_changed_lines == 100

    os.unlink(f.name)


def test_env_var_expansion():
    """Test environment variable expansion."""
    os.environ["TEST_API_KEY"] = "test-key-123"

    yaml_content = """
providers:
  openrouter:
    api_key: "${TEST_API_KEY}"
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        f.flush()

        config = TexGuardianConfig.load(Path(f.name))

        assert config.providers.openrouter.api_key == "test-key-123"

    os.unlink(f.name)
    del os.environ["TEST_API_KEY"]


def test_missing_config_file():
    """Test that missing config returns defaults."""
    config = TexGuardianConfig.load(Path("/nonexistent/path.yaml"))

    assert config.project.main_tex == "main.tex"

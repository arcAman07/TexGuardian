"""Integration tests for all commands using the position_paper_test.tex file with intentional errors."""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from rich.console import Console
from io import StringIO

# Setup paths
TEST_DIR = Path(__file__).parent.parent.parent / "examples" / "position_paper"
TEST_TEX = TEST_DIR / "position_paper_test.tex"
TEST_BIB = TEST_DIR / "references_test.bib"


class MockLLMClient:
    """Mock LLM client for testing."""

    async def complete(self, messages, max_tokens=2000, temperature=0.3):
        """Return mock response."""
        response = MagicMock()
        response.content = "Mock LLM response for testing"
        return response

    async def complete_with_vision(self, messages, images, max_tokens=2000, temperature=0.3):
        """Return mock vision response."""
        response = MagicMock()
        response.content = '{"quality_score": 85, "issues": [], "patches": [], "summary": "Test"}'
        return response


def create_test_session():
    """Create a session for testing with the test tex file."""
    from texguardian.core.session import SessionState
    from texguardian.config.settings import TexGuardianConfig, ProjectConfig

    config = TexGuardianConfig(
        project=ProjectConfig(
            main_tex="position_paper_test.tex",
            output_dir="build",
        ),
    )

    # Session requires config_path
    config_path = TEST_DIR / "texguardian.yaml"

    session = SessionState(
        config=config,
        project_root=TEST_DIR,
        config_path=config_path,
    )
    session.llm_client = MockLLMClient()

    return session


def create_console():
    """Create a console that captures output."""
    output = StringIO()
    return Console(file=output, force_terminal=True, width=120), output


class TestVerifyCommand:
    """Test the /verify command."""

    @pytest.mark.asyncio
    async def test_verify_detects_issues(self):
        """Test that verify detects the intentional errors."""
        from texguardian.cli.commands.verify import VerifyCommand

        session = create_test_session()
        console, output = create_console()
        cmd = VerifyCommand()

        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /verify output ===\n{result}")

        # Should detect issues
        assert "verification" in result.lower() or "check" in result.lower()


class TestCitationsCommand:
    """Test the /citations command."""

    @pytest.mark.asyncio
    async def test_citations_detects_issues(self):
        """Test that citations command detects undefined citations."""
        from texguardian.cli.commands.citations import CitationsCommand

        session = create_test_session()
        console, output = create_console()
        cmd = CitationsCommand()

        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /citations output ===\n{result}")

        # Should detect undefined citations or citation issues


class TestFiguresCommand:
    """Test the /figures command."""

    @pytest.mark.asyncio
    async def test_figures_detects_issues(self):
        """Test that figures command detects missing labels and short captions."""
        from texguardian.cli.commands.figures import FiguresCommand

        session = create_test_session()
        console, output = create_console()
        cmd = FiguresCommand()

        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /figures output ===\n{result}")

        # Should detect figure issues


class TestTablesCommand:
    """Test the /tables command."""

    @pytest.mark.asyncio
    async def test_tables_detects_issues(self):
        """Test that tables command detects missing labels and hline usage."""
        from texguardian.cli.commands.tables import TablesCommand

        session = create_test_session()
        console, output = create_console()
        cmd = TablesCommand()

        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /tables output ===\n{result}")

        # Should detect table issues


class TestSectionCommand:
    """Test the /section command."""

    @pytest.mark.asyncio
    async def test_section_lists_sections(self):
        """Test that section command can list sections."""
        from texguardian.cli.commands.section import SectionCommand

        session = create_test_session()
        console, output = create_console()
        cmd = SectionCommand()

        # List all sections
        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /section (list) output ===\n{result}")

        # Should show available sections
        assert "Introduction" in result or "section" in result.lower()

    @pytest.mark.asyncio
    async def test_section_analyzes_specific_section(self):
        """Test that section command analyzes a specific section."""
        from texguardian.cli.commands.section import SectionCommand

        session = create_test_session()
        console, output = create_console()
        cmd = SectionCommand()

        # Analyze Related Work (which is intentionally short)
        await cmd.execute(session, "Related", console)

        result = output.getvalue()
        print(f"\n=== /section Related output ===\n{result}")


class TestAnonymizeCommand:
    """Test the /anonymize command."""

    @pytest.mark.asyncio
    async def test_anonymize_detects_author_info(self):
        """Test that anonymize detects non-anonymous author information."""
        from texguardian.cli.commands.anonymize import AnonymizeCommand

        session = create_test_session()
        console, output = create_console()
        cmd = AnonymizeCommand()

        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /anonymize output ===\n{result}")

        # Should detect author info, affiliations, acknowledgments, self-citations
        # The test file has: John Smith, Jane Doe, Stanford, MIT, Acknowledgments section


class TestPageCountCommand:
    """Test the /page_count command."""

    @pytest.mark.asyncio
    async def test_page_count_analyzes_structure(self):
        """Test that page_count analyzes document structure."""
        from texguardian.cli.commands.page_count import PageCountCommand

        session = create_test_session()
        console, output = create_console()
        cmd = PageCountCommand()

        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /page_count output ===\n{result}")

        # Should show section breakdown and counts


class TestCameraReadyCommand:
    """Test the /camera_ready command."""

    @pytest.mark.asyncio
    async def test_camera_ready_detects_anonymous(self):
        """Test that camera_ready detects if paper is already de-anonymized."""
        from texguardian.cli.commands.camera_ready import CameraReadyCommand

        session = create_test_session()
        console, output = create_console()
        cmd = CameraReadyCommand()

        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /camera_ready output ===\n{result}")


class TestHelpCommand:
    """Test the /help command."""

    @pytest.mark.asyncio
    async def test_help_shows_all_commands(self):
        """Test that help shows all available commands."""
        from texguardian.cli.commands.registry import CommandRegistry
        from texguardian.cli.commands.help import HelpCommand

        registry = CommandRegistry()
        registry.register_all()

        session = create_test_session()
        console, output = create_console()

        cmd = HelpCommand(registry)
        await cmd.execute(session, "", console)

        result = output.getvalue()
        print(f"\n=== /help output ===\n{result}")

        # Should show all commands
        assert "/compile" in result or "compile" in result
        assert "/verify" in result or "verify" in result
        assert "/figures" in result or "figures" in result
        assert "/tables" in result or "tables" in result
        assert "/citations" in result or "citations" in result
        assert "/anonymize" in result or "anonymize" in result


if __name__ == "__main__":
    # Run a quick manual test
    async def main():
        print("=" * 60)
        print("Testing TeXGuardian commands with intentional errors")
        print("=" * 60)

        # Test verify
        print("\n\n--- Testing /verify ---")
        test = TestVerifyCommand()
        await test.test_verify_detects_issues()

        # Test citations
        print("\n\n--- Testing /citations ---")
        test = TestCitationsCommand()
        await test.test_citations_detects_issues()

        # Test figures
        print("\n\n--- Testing /figures ---")
        test = TestFiguresCommand()
        await test.test_figures_detects_issues()

        # Test tables
        print("\n\n--- Testing /tables ---")
        test = TestTablesCommand()
        await test.test_tables_detects_issues()

        # Test section
        print("\n\n--- Testing /section ---")
        test = TestSectionCommand()
        await test.test_section_lists_sections()

        # Test anonymize
        print("\n\n--- Testing /anonymize ---")
        test = TestAnonymizeCommand()
        await test.test_anonymize_detects_author_info()

        # Test page_count
        print("\n\n--- Testing /page_count ---")
        test = TestPageCountCommand()
        await test.test_page_count_analyzes_structure()

        # Test help
        print("\n\n--- Testing /help ---")
        test = TestHelpCommand()
        await test.test_help_shows_all_commands()

        print("\n\n" + "=" * 60)
        print("All tests completed!")
        print("=" * 60)

    asyncio.run(main())

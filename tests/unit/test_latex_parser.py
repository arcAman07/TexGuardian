"""Tests for LaTeX parsing."""

import tempfile
from pathlib import Path

import pytest

from texguardian.latex.parser import LatexParser


@pytest.fixture
def temp_project():
    """Create a temporary project directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create main.tex
        (root / "main.tex").write_text(r"""
\documentclass{article}
\begin{document}
\section{Introduction}
As shown by \citet{smith2024}, the problem is hard.
We build on prior work \citep{jones2023,williams2022}.

\section{Method}
See Figure \ref{fig:overview} for details.

\begin{figure}
\includegraphics{overview.pdf}
\caption{System overview}
\label{fig:overview}
\end{figure}

\end{document}
""")

        # Create refs.bib
        (root / "refs.bib").write_text(r"""
@article{smith2024,
    author = {Smith, John},
    title = {A Paper},
    year = {2024}
}
@article{jones2023,
    author = {Jones, Jane},
    title = {Another Paper},
    year = {2023}
}
@article{williams2022,
    author = {Williams, Bob},
    title = {Old Paper},
    year = {2022}
}
@article{unused2021,
    author = {Unused, Author},
    title = {Never Cited},
    year = {2021}
}
""")

        yield root


def test_extract_citations(temp_project):
    """Test extracting citation keys."""
    parser = LatexParser(temp_project)
    citations = parser.extract_citations()

    assert "smith2024" in citations
    assert "jones2023" in citations
    assert "williams2022" in citations


def test_extract_bib_keys(temp_project):
    """Test extracting bibliography keys."""
    parser = LatexParser(temp_project)
    keys = parser.extract_bib_keys()

    assert "smith2024" in keys
    assert "unused2021" in keys
    assert len(keys) == 4


def test_extract_citations_with_locations(temp_project):
    """Test extracting citations with file/line info."""
    parser = LatexParser(temp_project)
    citations = parser.extract_citations_with_locations()

    # Check we got location info
    assert any(c["key"] == "smith2024" and c["style"] == "citet" for c in citations)
    assert any(c["key"] == "jones2023" and c["style"] == "citep" for c in citations)


def test_extract_figures(temp_project):
    """Test extracting figure labels."""
    parser = LatexParser(temp_project)
    figures = parser.extract_figures()

    assert "fig:overview" in figures


def test_extract_figure_refs(temp_project):
    """Test extracting figure references."""
    parser = LatexParser(temp_project)
    refs = parser.extract_figure_refs()

    assert "fig:overview" in refs


def test_find_pattern(temp_project):
    """Test finding patterns in files."""
    parser = LatexParser(temp_project)

    # Find TODO markers (none in this project)
    matches = parser.find_pattern(r"TODO")
    assert len(matches) == 0

    # Find citation commands
    matches = parser.find_pattern(r"\\cite")
    assert len(matches) >= 2

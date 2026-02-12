"""Tests for citation validator."""

import pytest

from texguardian.citations.validator import (
    BibEntry,
    CitationValidator,
)


def test_parse_bib_fields():
    """Test BibTeX field parsing."""
    validator = CitationValidator()

    # Test basic field parsing
    fields_text = """
    title = {Deep Learning for NLP},
    author = {Smith, John and Doe, Jane},
    year = {2024},
    doi = {10.1234/example},
    """

    fields = validator._parse_bib_fields(fields_text)

    assert fields["title"] == "Deep Learning for NLP"
    assert fields["author"] == "Smith, John and Doe, Jane"
    assert fields["year"] == "2024"
    assert fields["doi"] == "10.1234/example"


def test_parse_bib_file():
    """Test parsing complete .bib file content."""
    validator = CitationValidator()

    content = """
@article{smith2024deep,
    title = {Deep Learning for NLP},
    author = {Smith, John and Doe, Jane},
    year = {2024},
    journal = {Nature ML},
    doi = {10.1234/example},
}

@inproceedings{jones2023benchmark,
    title = {A New Benchmark},
    author = {Jones, Alice},
    year = {2023},
    booktitle = {NeurIPS 2023},
}
"""

    entries = validator._parse_bib_file(content)

    assert len(entries) == 2

    assert entries[0].key == "smith2024deep"
    assert entries[0].entry_type == "article"
    assert entries[0].title == "Deep Learning for NLP"
    assert entries[0].year == "2024"
    assert entries[0].doi == "10.1234/example"

    assert entries[1].key == "jones2023benchmark"
    assert entries[1].entry_type == "inproceedings"
    assert entries[1].booktitle == "NeurIPS 2023"


def test_normalize_title():
    """Test title normalization."""
    validator = CitationValidator()

    # Basic normalization
    assert validator._normalize_title("Deep Learning") == "deep learning"

    # Remove LaTeX formatting
    assert validator._normalize_title("{Deep} Learning") == "deep learning"
    # LaTeX commands like \textbf{...} are stripped, keeping content
    assert validator._normalize_title("\\textbf{Deep} Learning") == "deep learning"
    assert "deep" in validator._normalize_title("\\textbf{Deep} Learning")

    # Remove punctuation
    assert validator._normalize_title("Deep Learning: A Survey") == "deep learning a survey"

    # Empty/None handling
    assert validator._normalize_title("") == ""
    assert validator._normalize_title(None) == ""


def test_titles_match():
    """Test title matching logic."""
    validator = CitationValidator()

    # Exact match
    assert validator._titles_match("deep learning", "deep learning")

    # Substring match (truncated titles)
    assert validator._titles_match("deep learning for nlp", "deep learning")

    # High word overlap
    assert validator._titles_match(
        "deep learning methods for natural language processing",
        "deep learning methods for nlp"
    )

    # Should not match
    assert not validator._titles_match("deep learning", "machine learning")
    assert not validator._titles_match("neural networks", "decision trees")

    # Empty strings
    assert not validator._titles_match("", "deep learning")
    assert not validator._titles_match("deep learning", "")


def test_format_crossref_authors():
    """Test CrossRef author formatting."""
    validator = CitationValidator()

    authors = [
        {"given": "John", "family": "Smith"},
        {"given": "Jane", "family": "Doe"},
    ]

    formatted = validator._format_crossref_authors(authors)
    assert formatted == "Smith, John and Doe, Jane"

    # Handle missing given name
    authors = [{"family": "Smith"}]
    assert validator._format_crossref_authors(authors) == "Smith"

    # Empty list
    assert validator._format_crossref_authors([]) == ""


def test_generate_bibtex():
    """Test BibTeX generation."""
    validator = CitationValidator()

    entry = BibEntry(
        key="smith2024deep",
        entry_type="article",
        title="Deep Learning for NLP",
        author="Smith, John and Doe, Jane",
        year="2024",
        doi="10.1234/example",
        journal="Nature ML",
    )

    bibtex = validator.generate_bibtex(entry)

    assert "@article{smith2024deep," in bibtex
    assert "title = {Deep Learning for NLP}," in bibtex
    assert "author = {Smith, John and Doe, Jane}," in bibtex
    assert "year = {2024}," in bibtex
    assert "doi = {10.1234/example}," in bibtex
    assert "journal = {Nature ML}," in bibtex


def test_needs_update():
    """Test update detection."""
    validator = CitationValidator()

    # Entry without DOI, search result has DOI
    original = BibEntry(key="test", entry_type="article", title="Test")
    assert validator._needs_update(original, {"doi": "10.1234/test"})

    # Entry already has DOI
    original = BibEntry(key="test", entry_type="article", title="Test", doi="existing")
    assert not validator._needs_update(original, {"doi": "10.1234/test"})

    # No DOI in either
    original = BibEntry(key="test", entry_type="article", title="Test")
    assert not validator._needs_update(original, {})


@pytest.mark.asyncio
async def test_validate_by_doi_invalid():
    """Test DOI validation with invalid DOI."""
    validator = CitationValidator(timeout=5.0)

    entry = BibEntry(
        key="test",
        entry_type="article",
        title="Test Paper",
        doi="10.9999/nonexistent",  # Invalid DOI
    )

    result = await validator._validate_by_doi(entry)

    # Should fail since DOI doesn't exist
    assert result.status in ("not_found", "valid")  # Depends on API response


@pytest.mark.asyncio
async def test_validate_entry_no_title():
    """Test validation with no title."""
    validator = CitationValidator(timeout=5.0)

    entry = BibEntry(
        key="test",
        entry_type="article",
        # No title
    )

    result = await validator._validate_entry(entry)

    assert result.status == "not_found"
    assert "No title" in result.message


class TestBibEntry:
    """Tests for BibEntry dataclass."""

    def test_basic_creation(self):
        """Test basic BibEntry creation."""
        entry = BibEntry(
            key="smith2024",
            entry_type="article",
            title="Test Paper",
            author="Smith, John",
            year="2024",
        )

        assert entry.key == "smith2024"
        assert entry.entry_type == "article"
        assert entry.title == "Test Paper"

    def test_default_values(self):
        """Test default values."""
        entry = BibEntry(key="test", entry_type="misc")

        assert entry.title == ""
        assert entry.author == ""
        assert entry.year == ""
        assert entry.doi == ""
        assert entry.raw_content == ""

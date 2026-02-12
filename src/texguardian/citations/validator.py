"""Citation validator using CrossRef and Semantic Scholar APIs.

Validates that citations in .bib files refer to real papers,
and can suggest corrections for hallucinated/incorrect citations.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from pathlib import Path

    from rich.console import Console


@dataclass
class BibEntry:
    """Parsed bibliography entry."""
    key: str
    entry_type: str  # article, inproceedings, book, etc.
    title: str = ""
    author: str = ""
    year: str = ""
    doi: str = ""
    url: str = ""
    journal: str = ""
    booktitle: str = ""
    arxiv_id: str = ""
    raw_content: str = ""


@dataclass
class ValidationResult:
    """Result of validating a single citation."""
    key: str
    status: str  # "valid", "not_found", "likely_hallucinated", "needs_correction"
    confidence: float  # 0.0 to 1.0
    original: BibEntry
    suggested_correction: BibEntry | None = None
    search_results: list[dict] = field(default_factory=list)
    message: str = ""


class CitationValidator:
    """Validates citations against real academic databases."""

    CROSSREF_API = "https://api.crossref.org/works"
    SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1/paper/search"
    _HEADERS = {"User-Agent": "texguardian/1.0 (https://github.com/texguardian; mailto:texguardian@users.noreply.github.com)"}

    def __init__(self, timeout: float = 10.0, max_concurrent: int = 5):
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def validate_bib_file(
        self,
        bib_path: Path,
        console: Console | None = None,
    ) -> list[ValidationResult]:
        """Validate all entries in a .bib file."""
        content = bib_path.read_text()
        entries = self._parse_bib_file(content)

        if console:
            console.print(f"[dim]Found {len(entries)} bibliography entries[/dim]")

        results = []
        for i, entry in enumerate(entries):
            if console:
                console.print(f"  [{i+1}/{len(entries)}] Validating: {entry.key}...", end="")

            result = await self._validate_entry(entry)
            results.append(result)

            if console:
                status_icon = {
                    "valid": "[green]✓[/green]",
                    "not_found": "[red]✗[/red]",
                    "likely_hallucinated": "[red]⚠[/red]",
                    "needs_correction": "[yellow]~[/yellow]",
                }.get(result.status, "?")
                console.print(f" {status_icon}")

        return results

    async def validate_entries(
        self,
        entries: list[BibEntry],
        console: Console | None = None,
    ) -> list[ValidationResult]:
        """Validate a list of BibEntry objects."""
        tasks = [self._validate_entry(entry) for entry in entries]
        return await asyncio.gather(*tasks)

    async def _validate_entry(self, entry: BibEntry) -> ValidationResult:
        """Validate a single bibliography entry."""
        async with self._semaphore:
            # Try DOI first if available (most reliable)
            if entry.doi:
                doi_result = await self._validate_by_doi(entry)
                if doi_result.status == "valid":
                    return doi_result

            # Try arXiv ID if available
            if entry.arxiv_id:
                arxiv_result = await self._validate_by_arxiv(entry)
                if arxiv_result.status == "valid":
                    return arxiv_result

            # Search by title + author
            if entry.title:
                search_result = await self._validate_by_search(entry)
                return search_result

            # Can't validate without title
            return ValidationResult(
                key=entry.key,
                status="not_found",
                confidence=0.0,
                original=entry,
                message="No title available for validation",
            )

    async def _validate_by_doi(self, entry: BibEntry) -> ValidationResult:
        """Validate by DOI lookup."""
        doi = entry.doi.strip()
        # Clean DOI format
        doi = re.sub(r'^https?://(dx\.)?doi\.org/', '', doi)

        url = f"{self.CROSSREF_API}/{doi}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._HEADERS) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    data = response.json()
                    work = data.get("message", {})

                    # Compare titles
                    api_title = self._normalize_title(
                        work.get("title", [""])[0] if work.get("title") else ""
                    )
                    entry_title = self._normalize_title(entry.title)

                    if self._titles_match(api_title, entry_title):
                        return ValidationResult(
                            key=entry.key,
                            status="valid",
                            confidence=1.0,
                            original=entry,
                            message=f"DOI verified: {doi}",
                        )
                    else:
                        # DOI exists but title doesn't match - wrong DOI?
                        suggested = self._create_correction_from_crossref(entry, work)
                        return ValidationResult(
                            key=entry.key,
                            status="needs_correction",
                            confidence=0.7,
                            original=entry,
                            suggested_correction=suggested,
                            message=f"DOI exists but title mismatch. API title: '{api_title[:50]}...'",
                        )

        except Exception:
            pass  # Fall through to other methods

        return ValidationResult(
            key=entry.key,
            status="not_found",
            confidence=0.0,
            original=entry,
            message=f"DOI lookup failed: {doi}",
        )

    async def _validate_by_arxiv(self, entry: BibEntry) -> ValidationResult:
        """Validate by arXiv ID."""
        arxiv_id = entry.arxiv_id.strip()
        # Clean arxiv ID format
        arxiv_id = re.sub(r'^(https?://)?arxiv\.org/abs/', '', arxiv_id)
        arxiv_id = re.sub(r'^arXiv:', '', arxiv_id, flags=re.IGNORECASE)

        url = f"https://export.arxiv.org/api/query?id_list={arxiv_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._HEADERS) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    # Parse XML response (simple approach)
                    content = response.text
                    if "<title>" in content and "Error" not in content:
                        # Extract title from XML
                        title_match = re.search(r'<title>([^<]+)</title>', content)
                        if title_match:
                            api_title = self._normalize_title(title_match.group(1))
                            entry_title = self._normalize_title(entry.title)

                            if self._titles_match(api_title, entry_title):
                                return ValidationResult(
                                    key=entry.key,
                                    status="valid",
                                    confidence=1.0,
                                    original=entry,
                                    message=f"arXiv verified: {arxiv_id}",
                                )
        except Exception:
            pass

        return ValidationResult(
            key=entry.key,
            status="not_found",
            confidence=0.0,
            original=entry,
            message=f"arXiv lookup failed: {arxiv_id}",
        )

    async def _validate_by_search(self, entry: BibEntry) -> ValidationResult:
        """Validate by searching CrossRef and Semantic Scholar."""
        # Try CrossRef first
        crossref_result = await self._search_crossref(entry)
        if crossref_result.status == "valid":
            return crossref_result

        # Try Semantic Scholar
        ss_result = await self._search_semantic_scholar(entry)
        if ss_result.status == "valid":
            return ss_result

        # If both failed but we got search results, it might be hallucinated
        all_results = crossref_result.search_results + ss_result.search_results

        if not all_results:
            return ValidationResult(
                key=entry.key,
                status="likely_hallucinated",
                confidence=0.8,
                original=entry,
                message="No matching papers found in CrossRef or Semantic Scholar. Citation may be hallucinated.",
            )

        # We found similar papers but not exact match
        return ValidationResult(
            key=entry.key,
            status="needs_correction",
            confidence=0.5,
            original=entry,
            search_results=all_results[:5],
            message=f"Found {len(all_results)} similar papers but no exact match. See search_results for alternatives.",
        )

    async def _search_crossref(self, entry: BibEntry) -> ValidationResult:
        """Search CrossRef by title."""
        # Build query
        query_parts = []
        if entry.title:
            query_parts.append(entry.title)

        if not query_parts:
            return ValidationResult(
                key=entry.key,
                status="not_found",
                confidence=0.0,
                original=entry,
            )

        query = " ".join(query_parts)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._HEADERS) as client:
                params = {
                    "query": query,
                    "rows": 5,
                    "select": "DOI,title,author,published-print,container-title",
                }

                response = await client.get(self.CROSSREF_API, params=params)

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("message", {}).get("items", [])

                    search_results = []
                    for item in items:
                        api_title = item.get("title", [""])[0] if item.get("title") else ""
                        entry_title = self._normalize_title(entry.title)

                        result = {
                            "title": api_title,
                            "doi": item.get("DOI", ""),
                            "authors": self._format_crossref_authors(item.get("author", [])),
                            "year": self._extract_year_from_crossref(item),
                            "journal": item.get("container-title", [""])[0] if item.get("container-title") else "",
                            "source": "crossref",
                        }
                        search_results.append(result)

                        # Check for match
                        if self._titles_match(self._normalize_title(api_title), entry_title):
                            # Found a match!
                            suggested = self._create_correction_from_dict(entry, result)
                            return ValidationResult(
                                key=entry.key,
                                status="valid",
                                confidence=0.9,
                                original=entry,
                                suggested_correction=suggested if self._needs_update(entry, result) else None,
                                search_results=search_results,
                                message="Found in CrossRef",
                            )

                    return ValidationResult(
                        key=entry.key,
                        status="not_found",
                        confidence=0.0,
                        original=entry,
                        search_results=search_results,
                    )

        except Exception:
            pass

        return ValidationResult(
            key=entry.key,
            status="not_found",
            confidence=0.0,
            original=entry,
        )

    async def _search_semantic_scholar(self, entry: BibEntry) -> ValidationResult:
        """Search Semantic Scholar by title."""
        if not entry.title:
            return ValidationResult(
                key=entry.key,
                status="not_found",
                confidence=0.0,
                original=entry,
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self._HEADERS) as client:
                params = {
                    "query": entry.title,
                    "limit": 5,
                    "fields": "title,authors,year,externalIds,venue",
                }

                response = await client.get(self.SEMANTIC_SCHOLAR_API, params=params)

                if response.status_code == 200:
                    data = response.json()
                    papers = data.get("data", [])

                    search_results = []
                    for paper in papers:
                        api_title = paper.get("title", "")
                        entry_title = self._normalize_title(entry.title)

                        external_ids = paper.get("externalIds", {}) or {}

                        result = {
                            "title": api_title,
                            "doi": external_ids.get("DOI", ""),
                            "arxiv": external_ids.get("ArXiv", ""),
                            "authors": ", ".join(
                                a.get("name", "") for a in paper.get("authors", [])
                            ),
                            "year": str(paper.get("year", "")),
                            "venue": paper.get("venue", ""),
                            "source": "semantic_scholar",
                        }
                        search_results.append(result)

                        # Check for match
                        if self._titles_match(self._normalize_title(api_title), entry_title):
                            suggested = self._create_correction_from_dict(entry, result)
                            return ValidationResult(
                                key=entry.key,
                                status="valid",
                                confidence=0.9,
                                original=entry,
                                suggested_correction=suggested if self._needs_update(entry, result) else None,
                                search_results=search_results,
                                message="Found in Semantic Scholar",
                            )

                    return ValidationResult(
                        key=entry.key,
                        status="not_found",
                        confidence=0.0,
                        original=entry,
                        search_results=search_results,
                    )

        except Exception:
            pass

        return ValidationResult(
            key=entry.key,
            status="not_found",
            confidence=0.0,
            original=entry,
        )

    def _parse_bib_file(self, content: str) -> list[BibEntry]:
        """Parse a .bib file into BibEntry objects."""
        entries = []

        # Match @type{key, ... }
        pattern = r'@(\w+)\s*\{\s*([^,]+)\s*,([^@]*?)(?=\n@|\Z)'

        for match in re.finditer(pattern, content, re.DOTALL):
            entry_type = match.group(1).lower()
            key = match.group(2).strip()
            fields_text = match.group(3)

            entry = BibEntry(
                key=key,
                entry_type=entry_type,
                raw_content=match.group(0),
            )

            # Parse fields
            fields = self._parse_bib_fields(fields_text)
            entry.title = fields.get("title", "")
            entry.author = fields.get("author", "")
            entry.year = fields.get("year", "")
            entry.doi = fields.get("doi", "")
            entry.url = fields.get("url", "")
            entry.journal = fields.get("journal", "")
            entry.booktitle = fields.get("booktitle", "")

            # Extract arXiv ID from various fields
            if "eprint" in fields:
                entry.arxiv_id = fields["eprint"]
            elif "arxiv" in entry.url.lower():
                # Extract just the ID from URLs like https://arxiv.org/abs/2301.12345
                arxiv_match = re.search(r'(\d{4}\.\d{4,5}(?:v\d+)?)', entry.url)
                entry.arxiv_id = arxiv_match.group(1) if arxiv_match else ""

            entries.append(entry)

        return entries

    def _parse_bib_fields(self, fields_text: str) -> dict[str, str]:
        """Parse BibTeX fields from text."""
        fields = {}

        # Match field = {value} or field = "value" or field = value
        pattern = r'(\w+)\s*=\s*(?:\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}|"([^"]*)"|(\S+))'

        for match in re.finditer(pattern, fields_text):
            field_name = match.group(1).lower()
            value = match.group(2) or match.group(3) or match.group(4) or ""
            # Clean up LaTeX formatting
            value = re.sub(r'[\{\}]', '', value)
            value = value.strip()
            fields[field_name] = value

        return fields

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        if not title:
            return ""
        # Remove LaTeX commands like \textbf{...} → keep content inside braces
        title = re.sub(r'\\[a-zA-Z]+\{([^}]*)\}', r'\1', title)
        # Remove remaining LaTeX control sequences and braces
        title = re.sub(r'\\[a-zA-Z]+', '', title)
        title = re.sub(r'[{}]', '', title)
        # Remove punctuation, collapse whitespace
        title = re.sub(r'[^\w\s]', ' ', title)
        title = re.sub(r'\s+', ' ', title)
        return title.lower().strip()

    def _titles_match(self, title1: str, title2: str) -> bool:
        """Check if two normalized titles match."""
        if not title1 or not title2:
            return False

        # Exact match
        if title1 == title2:
            return True

        # One contains the other (handles truncated titles)
        if title1 in title2 or title2 in title1:
            return True

        # Calculate similarity (simple word overlap)
        words1 = set(title1.split())
        words2 = set(title2.split())

        if not words1 or not words2:
            return False

        overlap = len(words1 & words2)
        min_len = min(len(words1), len(words2))

        # At least 80% word overlap
        return overlap / min_len >= 0.8

    def _format_crossref_authors(self, authors: list[dict]) -> str:
        """Format CrossRef author list."""
        names = []
        for author in authors:
            given = author.get("given", "")
            family = author.get("family", "")
            if family:
                names.append(f"{family}, {given}" if given else family)
        return " and ".join(names)

    def _extract_year_from_crossref(self, item: dict) -> str:
        """Extract year from CrossRef response."""
        published = item.get("published-print") or item.get("published-online") or {}
        date_parts = published.get("date-parts", [[]])
        if date_parts and date_parts[0]:
            return str(date_parts[0][0])
        return ""

    def _create_correction_from_crossref(self, original: BibEntry, work: dict) -> BibEntry:
        """Create a corrected BibEntry from CrossRef data."""
        return BibEntry(
            key=original.key,
            entry_type=original.entry_type,
            title=work.get("title", [""])[0] if work.get("title") else original.title,
            author=self._format_crossref_authors(work.get("author", [])) or original.author,
            year=self._extract_year_from_crossref(work) or original.year,
            doi=work.get("DOI", "") or original.doi,
            journal=work.get("container-title", [""])[0] if work.get("container-title") else original.journal,
        )

    def _create_correction_from_dict(self, original: BibEntry, data: dict) -> BibEntry:
        """Create a corrected BibEntry from search result dict."""
        return BibEntry(
            key=original.key,
            entry_type=original.entry_type,
            title=data.get("title", "") or original.title,
            author=data.get("authors", "") or original.author,
            year=data.get("year", "") or original.year,
            doi=data.get("doi", "") or original.doi,
            arxiv_id=data.get("arxiv", "") or original.arxiv_id,
            journal=data.get("journal", "") or data.get("venue", "") or original.journal,
        )

    def _needs_update(self, original: BibEntry, data: dict) -> bool:
        """Check if original entry needs updating based on found data."""
        # Has DOI in search result but not in original
        if data.get("doi") and not original.doi:
            return True
        # Has arXiv in search result but not in original
        if data.get("arxiv") and not original.arxiv_id:
            return True
        return False

    def generate_bibtex(self, entry: BibEntry) -> str:
        """Generate BibTeX string from BibEntry."""
        lines = [f"@{entry.entry_type}{{{entry.key},"]

        if entry.title:
            lines.append(f"  title = {{{entry.title}}},")
        if entry.author:
            lines.append(f"  author = {{{entry.author}}},")
        if entry.year:
            lines.append(f"  year = {{{entry.year}}},")
        if entry.doi:
            lines.append(f"  doi = {{{entry.doi}}},")
        if entry.journal:
            lines.append(f"  journal = {{{entry.journal}}},")
        if entry.booktitle:
            lines.append(f"  booktitle = {{{entry.booktitle}}},")
        if entry.arxiv_id:
            lines.append(f"  eprint = {{{entry.arxiv_id}}},")
            lines.append("  archiveprefix = {arXiv},")
        if entry.url:
            lines.append(f"  url = {{{entry.url}}},")

        lines.append("}")
        return "\n".join(lines)

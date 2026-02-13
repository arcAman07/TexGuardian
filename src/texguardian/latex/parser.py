"""LaTeX document parser."""

from __future__ import annotations

import re
from pathlib import Path


class LatexParser:
    """Parser for LaTeX documents."""

    _SKIP_DIRS = {'_original', '.texguardian', 'build', 'backup', '.git', '__pycache__'}

    def __init__(self, project_root: Path, main_tex: Path | str | None = None):
        self.project_root = project_root
        # If main_tex is specified, use it; otherwise will search for \documentclass
        if main_tex:
            if isinstance(main_tex, str):
                self.main_tex = project_root / main_tex
            else:
                self.main_tex = main_tex
        else:
            self.main_tex = None

    def _iter_tex_files(self) -> list[Path]:
        """Iterate .tex files, filtering out build/backup dirs."""
        result = []
        for f in self.project_root.rglob("*.tex"):
            rel = str(f.relative_to(self.project_root))
            if not any(skip in rel for skip in self._SKIP_DIRS):
                result.append(f)
        return result

    def _iter_bib_files(self) -> list[Path]:
        """Iterate .bib files, filtering out build/backup dirs."""
        result = []
        for f in self.project_root.rglob("*.bib"):
            rel = str(f.relative_to(self.project_root))
            if not any(skip in rel for skip in self._SKIP_DIRS):
                result.append(f)
        return result

    def extract_citations(self) -> list[str]:
        """Extract all citation keys from .tex files."""
        keys = []
        pattern = r"\\cite[pt]?\{([^}]+)\}"

        for tex_file in self._iter_tex_files():
            content = tex_file.read_text(errors="ignore")
            matches = re.findall(pattern, content)
            for match in matches:
                # Handle multiple keys in one cite
                keys.extend(k.strip() for k in match.split(","))

        return list(set(keys))

    def extract_citations_with_locations(self) -> list[dict]:
        """Extract citations with file and line information."""
        citations = []
        pattern = r"\\(cite[pt]?)\{([^}]+)\}"

        for tex_file in self._iter_tex_files():
            content = tex_file.read_text(errors="ignore")
            rel_path = tex_file.relative_to(self.project_root)

            for i, line in enumerate(content.split("\n"), 1):
                for match in re.finditer(pattern, line):
                    style = match.group(1)
                    keys = match.group(2)
                    for key in keys.split(","):
                        citations.append({
                            "key": key.strip(),
                            "style": style,
                            "file": str(rel_path),
                            "line": i,
                        })

        return citations

    def extract_bib_keys(self) -> list[str]:
        """Extract all keys from .bib files."""
        keys = []
        pattern = r"@\w+\{([^,]+),"

        for bib_file in self._iter_bib_files():
            content = bib_file.read_text(errors="ignore")
            matches = re.findall(pattern, content)
            keys.extend(k.strip() for k in matches)

        return keys

    def extract_figures(self) -> list[str]:
        """Extract figure labels."""
        labels = []
        # Match \label{fig:...} inside figure environments
        pattern = r"\\label\{(fig:[^}]+)\}"

        for tex_file in self._iter_tex_files():
            content = tex_file.read_text(errors="ignore")
            matches = re.findall(pattern, content)
            labels.extend(matches)

        return labels

    def extract_figures_with_details(self) -> list[dict]:
        """Extract figures with details."""
        figures = []
        seen_labels: set[str] = set()
        # Simple pattern for figure environments
        fig_pattern = r"\\begin\{figure\}.*?\\end\{figure\}"

        for tex_file in self.project_root.rglob("*.tex"):
            # Skip backup files, checkpoints, and build directories
            rel_path = tex_file.relative_to(self.project_root)
            path_str = str(rel_path)
            if any(skip in path_str for skip in ['_original', '.texguardian', 'build', 'backup']):
                continue

            content = tex_file.read_text(errors="ignore")

            for match in re.finditer(fig_pattern, content, re.DOTALL):
                fig_content = match.group(0)

                # Extract label
                label_match = re.search(r"\\label\{([^}]+)\}", fig_content)
                label = label_match.group(1) if label_match else ""

                # Skip duplicate labels
                if label and label in seen_labels:
                    continue
                if label:
                    seen_labels.add(label)

                # Extract caption
                caption_match = re.search(r"\\caption\{([^}]+)\}", fig_content)
                caption = caption_match.group(1) if caption_match else ""

                # Extract includegraphics
                include_match = re.search(r"\\includegraphics.*?\{([^}]+)\}", fig_content)
                image_file = include_match.group(1) if include_match else ""

                figures.append({
                    "label": label,
                    "caption": caption,
                    "file": image_file,
                    "source": str(rel_path),
                    "content": fig_content[:500],
                })

        return figures

    def extract_figure_refs(self) -> list[str]:
        """Extract all figure references."""
        refs = []
        pattern = r"\\ref\{(fig:[^}]+)\}"

        for tex_file in self._iter_tex_files():
            content = tex_file.read_text(errors="ignore")
            matches = re.findall(pattern, content)
            refs.extend(matches)

        return refs

    def extract_tables_with_details(self) -> list[dict]:
        """Extract tables with details."""
        tables = []
        seen_labels = set()  # Track seen labels to avoid duplicates
        # Pattern for table environments
        table_pattern = r"\\begin\{table\}.*?\\end\{table\}"

        for tex_file in self._iter_tex_files():
            rel_path = tex_file.relative_to(self.project_root)
            content = tex_file.read_text(errors="ignore")

            for match in re.finditer(table_pattern, content, re.DOTALL):
                table_content = match.group(0)

                # Extract label
                label_match = re.search(r"\\label\{([^}]+)\}", table_content)
                label = label_match.group(1) if label_match else ""

                # Extract caption
                caption_match = re.search(r"\\caption\{([^}]+)\}", table_content)
                caption = caption_match.group(1) if caption_match else ""

                # Extract tabular content
                tabular_match = re.search(
                    r"\\begin\{tabular\}.*?\\end\{tabular\}",
                    table_content,
                    re.DOTALL
                )
                tabular_content = tabular_match.group(0) if tabular_match else ""

                # Count rows and columns (rough estimate)
                rows = tabular_content.count(r"\\") if tabular_content else 0
                col_match = re.search(r"\\begin\{tabular\}\{([^}]+)\}", tabular_content)
                cols = len(col_match.group(1).replace("|", "").replace("@", "").replace("{", "").replace("}", "")) if col_match else 0

                # Skip duplicate labels
                if label and label in seen_labels:
                    continue
                if label:
                    seen_labels.add(label)

                tables.append({
                    "label": label,
                    "caption": caption,
                    "content": tabular_content[:500],  # Preview
                    "source": str(rel_path),
                    "rows": rows,
                    "columns": cols,
                })

        return tables

    def extract_table_refs(self) -> list[str]:
        """Extract all table references."""
        refs = []
        pattern = r"\\ref\{(tab:[^}]+)\}"

        for tex_file in self._iter_tex_files():
            content = tex_file.read_text(errors="ignore")
            matches = re.findall(pattern, content)
            refs.extend(matches)

        return refs

    def parse_bibliography(self) -> dict[str, dict]:
        """Parse bibliography files into a dictionary."""
        entries = {}

        for bib_file in self._iter_bib_files():
            content = bib_file.read_text(errors="ignore")

            # Match @type{key, ...}
            entry_pattern = r"@(\w+)\{([^,]+),([^@]*)"
            for match in re.finditer(entry_pattern, content, re.DOTALL):
                entry_type = match.group(1).lower()
                key = match.group(2).strip()
                fields_str = match.group(3)

                # Parse fields
                fields = {"type": entry_type}
                field_pattern = r"(\w+)\s*=\s*[{\"]([^}\"]*)[}\"]"
                for field_match in re.finditer(field_pattern, fields_str):
                    fields[field_match.group(1).lower()] = field_match.group(2)

                entries[key] = fields

        return entries

    def extract_sections(self) -> list[dict]:
        """Extract sections with content."""
        sections = []

        # Use specified main_tex or find it
        main_tex = self.main_tex
        if not main_tex or not main_tex.exists():
            # Find main tex file by looking for \documentclass
            for tex_file in self.project_root.rglob("*.tex"):
                content = tex_file.read_text(errors="ignore")
                if r"\documentclass" in content:
                    main_tex = tex_file
                    break

        if not main_tex or not main_tex.exists():
            return sections

        # Recursively process files
        processed = set()
        self._process_tex_file(main_tex, sections, processed)

        return sections

    def _process_tex_file(
        self,
        tex_file: Path,
        sections: list[dict],
        processed: set,
    ) -> None:
        """Process a .tex file for sections."""
        if tex_file in processed:
            return
        processed.add(tex_file)

        content = tex_file.read_text(errors="ignore")

        # Find sections
        section_pattern = r"\\(section|subsection|subsubsection)\{([^}]+)\}"
        current_section = None
        current_content = []

        for line in content.split("\n"):
            # Check for section header
            match = re.match(section_pattern, line)
            if match:
                # Save previous section
                if current_section:
                    sections.append({
                        "name": current_section,
                        "content": "\n".join(current_content),
                    })
                current_section = match.group(2)
                current_content = []
            elif current_section:
                current_content.append(line)

            # Check for input/include
            input_match = re.search(r"\\(?:input|include)\{([^}]+)\}", line)
            if input_match:
                included_path = input_match.group(1)
                if not included_path.endswith(".tex"):
                    included_path += ".tex"
                included_file = tex_file.parent / included_path
                if included_file.exists():
                    self._process_tex_file(included_file, sections, processed)

        # Save last section
        if current_section:
            sections.append({
                "name": current_section,
                "content": "\n".join(current_content),
            })

    def find_pattern(self, pattern: str) -> list[dict]:
        """Find pattern matches in all .tex files."""
        matches = []

        try:
            regex = re.compile(pattern)
        except re.error:
            return matches

        for tex_file in self._iter_tex_files():
            content = tex_file.read_text(errors="ignore")
            rel_path = tex_file.relative_to(self.project_root)

            for i, line in enumerate(content.split("\n"), 1):
                if regex.search(line):
                    matches.append({
                        "file": str(rel_path),
                        "line": i,
                        "content": line.strip(),
                    })

        return matches

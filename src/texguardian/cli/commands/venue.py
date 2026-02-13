"""Venue command - fetch conference LaTeX templates.

Downloads style files directly to project directory for easy use with main.tex.
Searches GitHub, official conference sites, and CTAN for any venue/year.
"""

from __future__ import annotations

import asyncio
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from texguardian.cli.commands.registry import Command

if TYPE_CHECKING:
    from rich.console import Console

    from texguardian.core.session import SessionState


VENUE_ACTION_PROMPT = """\
You are a LaTeX conference template assistant for TexGuardian.

The user wants to download or configure conference style files. Based on their \
request, determine which conference venue and year they need.

## Available Known Venues
{venues_list}

## Current Project
- Paper venue: {current_venue}
- Project root: {project_root}

## User Request
{user_instruction}

## Task
1. Identify the conference venue and year from the user's request.
2. Provide a brief, helpful explanation about the venue and what will be downloaded.
3. Include a JSON action block in your response with this exact format:

```json
{{"action": "download_template", "venue": "<venue_key>", "year": "<4-digit-year>"}}
```

If the venue is not in the known list, still provide the venue key (lowercase, \
no spaces) and we'll search GitHub and CTAN for it.
If the user's request is unclear or you can't determine a venue, explain what \
you need and do NOT include a JSON block.
"""


# Known conference template sources
KNOWN_VENUES = {
    "iclr": {
        "name": "ICLR",
        "github": "ICLR/Master-Template",
        "pattern": r"iclr\d{4}",
        "files": [".sty", ".bst"],
    },
    "icml": {
        "name": "ICML",
        "url_pattern": "https://media.icml.cc/Conferences/ICML{year}/Styles/icml{year}.zip",
        "pattern": r"icml\d{4}",
        "files": [".sty", ".bst"],
    },
    "neurips": {
        "name": "NeurIPS",
        "url_pattern": "https://media.neurips.cc/Conferences/NeurIPS{year}/Styles/neurips_{year}.zip",
        "pattern": r"neurips_?\d{4}",
        "files": [".sty", ".bst"],
    },
    "aaai": {
        "name": "AAAI",
        "pattern": r"aaai\d{2,4}",
        "files": [".sty", ".bst", ".cls"],
    },
    "acl": {
        "name": "ACL",
        "github": "acl-org/acl-style-files",
        "pattern": r"acl",
        "files": [".sty", ".bst"],
    },
    "cvpr": {
        "name": "CVPR",
        "pattern": r"cvpr\d{0,4}",
        "files": [".sty", ".cls"],
    },
    "iccv": {
        "name": "ICCV",
        "pattern": r"iccv\d{0,4}",
        "files": [".sty", ".cls"],
    },
    "eccv": {
        "name": "ECCV",
        "pattern": r"eccv\d{0,4}",
        "files": [".sty", ".cls"],
    },
    "naacl": {
        "name": "NAACL",
        "github": "acl-org/acl-style-files",
        "pattern": r"naacl",
        "files": [".sty", ".bst"],
    },
    "emnlp": {
        "name": "EMNLP",
        "github": "acl-org/acl-style-files",
        "pattern": r"emnlp",
        "files": [".sty", ".bst"],
    },
    "coling": {
        "name": "COLING",
        "pattern": r"coling",
        "files": [".sty", ".cls"],
    },
}


class VenueCommand(Command):
    """Fetch conference LaTeX templates."""

    name = "venue"
    description = "Fetch conference LaTeX templates (ICLR, ICML, NeurIPS, ACL, etc.)"
    aliases = ["template", "conf"]
    usage = "/venue <name> [year] or natural language (e.g., /venue iclr 2025 or /venue pls fetch neurips 2026 style files)"

    async def execute(
        self,
        session: SessionState,
        args: str,
        console: Console,
    ) -> None:
        """Execute venue command."""
        args = args.strip().lower()

        if not args or args == "list":
            self._list_venues(console)
            return

        # Simple pattern: 1-2 tokens, first is venue-like
        venue_name, year = self._try_simple_parse(args)
        if venue_name:
            await self._download_and_persist(venue_name, year, session, console)
            return

        # Natural language → LLM
        await self._handle_llm_request(args, session, console)

    def _try_simple_parse(self, args: str) -> tuple[str | None, str]:
        """Try to parse as simple '<venue> [year]'. Returns (None, _) if not simple."""
        parts = args.split()
        if len(parts) > 2:
            return None, ""
        venue = parts[0]
        year = parts[1] if len(parts) == 2 else "2025"
        # Normalize 2-digit year
        if re.match(r'^\d{2}$', year):
            year = "20" + year
        if not re.match(r'^20\d{2}$', year) and len(parts) == 2:
            return None, ""  # Second word isn't a year → not simple
        return venue, year

    async def _handle_llm_request(
        self,
        user_input: str,
        session: SessionState,
        console: Console,
    ) -> None:
        """Use the LLM to interpret a natural-language venue request."""
        if not session.llm_client:
            console.print("[red]LLM client not initialized. Use simple syntax: /venue <name> [year][/red]")
            return

        from texguardian.llm.prompts.system import COMMAND_SYSTEM_PROMPT
        from texguardian.llm.streaming import stream_llm

        # Build prompt
        venues_list = "\n".join(f"- {k}: {v['name']}" for k, v in KNOWN_VENUES.items())
        current_venue = session.paper_spec.venue if session.paper_spec else "Not set"

        prompt = VENUE_ACTION_PROMPT.format(
            venues_list=venues_list,
            current_venue=current_venue,
            project_root=str(session.project_root),
            user_instruction=user_input,
        )

        # Stream LLM response
        response_text = await stream_llm(
            session.llm_client,
            messages=[{"role": "user", "content": prompt}],
            console=console,
            system=COMMAND_SYSTEM_PROMPT,
            max_tokens=1500,
            temperature=0.3,
        )
        console.print()

        # Save to context
        if session.context:
            session.context.add_assistant_message(response_text)

        # Extract JSON action
        action = self._extract_json_action(response_text)
        if not action or action.get("action") != "download_template":
            return  # LLM already explained the issue

        venue_name = action["venue"]
        year = action["year"]

        # Approval
        from texguardian.cli.approval import action_approval

        approved = await action_approval(
            f"Download {venue_name.upper()} {year} Template",
            [
                f"Venue: [cyan]{venue_name.upper()}[/cyan]",
                f"Year: [cyan]{year}[/cyan]",
                f"Target: {session.project_root}",
            ],
            console,
        )
        if not approved:
            console.print("[dim]Skipped[/dim]")
            return

        await self._download_and_persist(venue_name, year, session, console)

    def _extract_json_action(self, text: str) -> dict | None:
        """Extract JSON action block from LLM response."""
        # Try ```json blocks first
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        # Fallback: outermost braces
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass
        return None

    async def _download_and_persist(
        self,
        venue_name: str,
        year: str,
        session: SessionState,
        console: Console,
    ) -> None:
        """Download template and offer to update paper_spec."""
        console.print(f"[bold cyan]Searching for {venue_name.upper()} {year} template...[/bold cyan]\n")

        # Snapshot .sty/.cls files before download
        style_exts = {".sty", ".cls"}
        before = {
            p.name for p in session.project_root.iterdir()
            if p.suffix in style_exts
        }

        success = await self._find_and_download(venue_name, year, session, console)

        if success:
            console.print("\n[green]✓ Template files downloaded to project directory![/green]")

            # Determine which .sty/.cls files are new
            after = {
                p.name for p in session.project_root.iterdir()
                if p.suffix in style_exts
            }
            new_files = sorted(after - before)

            # Auto-update the main .tex file
            if new_files:
                self._update_tex_for_style_files(
                    new_files, session, venue_name, console,
                )

            # Offer to update paper_spec
            await self._offer_update_spec(venue_name, year, session, console)
        else:
            console.print("\n[yellow]Could not auto-download template.[/yellow]")
            console.print("[dim]Try searching manually:[/dim]")
            console.print(f"  - GitHub: https://github.com/search?q={venue_name}+{year}+latex+template")
            console.print(f"  - CTAN: https://ctan.org/search?phrase={venue_name}")

    def _update_tex_for_style_files(
        self,
        downloaded_files: list[str],
        session: SessionState,
        venue: str,
        console: Console,
    ) -> None:
        """Auto-update the main .tex file to use downloaded style files."""
        tex_path = session.main_tex_path
        if not tex_path.exists():
            return

        content = tex_path.read_text()

        # Split at \begin{document} to only modify the preamble
        doc_marker = r"\begin{document}"
        marker_pos = content.find(doc_marker)
        if marker_pos == -1:
            return  # Not a standard LaTeX file
        preamble = content[:marker_pos]
        body = content[marker_pos:]

        venue_info = KNOWN_VENUES.get(venue, {})
        venue_pattern = venue_info.get("pattern", re.escape(venue))
        changes: list[str] = []

        for filename in downloaded_files:
            name_no_ext = Path(filename).stem
            ext = Path(filename).suffix

            if ext == ".sty":
                # Look for an existing \usepackage{<venue_pattern>...} to replace
                pkg_re = re.compile(
                    r"(\\usepackage\s*(?:\[[^\]]*\])?\s*\{)"
                    + r"(" + venue_pattern + r"[^}]*)"
                    + r"(\})",
                )
                match = pkg_re.search(preamble)
                if match and match.group(2) != name_no_ext:
                    old_pkg = match.group(2)
                    preamble = preamble[:match.start(2)] + name_no_ext + preamble[match.end(2):]
                    changes.append(
                        f"Replaced \\usepackage{{{old_pkg}}} "
                        f"with \\usepackage{{{name_no_ext}}}"
                    )
                elif not match:
                    # No existing venue package — insert after last \usepackage
                    last_pkg = None
                    for m in re.finditer(r"\\usepackage\s*(?:\[[^\]]*\])?\s*\{[^}]*\}", preamble):
                        last_pkg = m
                    if last_pkg:
                        insert_pos = last_pkg.end()
                        insert_line = f"\n\\usepackage{{{name_no_ext}}}"
                        preamble = preamble[:insert_pos] + insert_line + preamble[insert_pos:]
                        changes.append(f"Added \\usepackage{{{name_no_ext}}}")

            elif ext == ".cls":
                # Replace \documentclass{<venue_pattern>...}
                cls_re = re.compile(
                    r"(\\documentclass\s*(?:\[[^\]]*\])?\s*\{)"
                    + r"(" + venue_pattern + r"[^}]*)"
                    + r"(\})",
                )
                match = cls_re.search(preamble)
                if match and match.group(2) != name_no_ext:
                    old_cls = match.group(2)
                    preamble = preamble[:match.start(2)] + name_no_ext + preamble[match.end(2):]
                    changes.append(
                        f"Replaced \\documentclass{{{old_cls}}} "
                        f"with \\documentclass{{{name_no_ext}}}"
                    )

        if changes:
            tex_path.write_text(preamble + body)
            console.print("\n[bold]Auto-updated main .tex file:[/bold]")
            for change in changes:
                console.print(f"  [green]✓[/green] {change}")
        else:
            # No auto-update was possible — show manual hint
            pkg_names = [
                Path(f).stem for f in downloaded_files
                if f.endswith(".sty") or f.endswith(".cls")
            ]
            if pkg_names:
                console.print("\n[bold]Downloaded style files:[/bold]")
                for pkg in pkg_names:
                    console.print(f"  [cyan]{pkg}[/cyan]")

    def _list_venues(self, console: Console) -> None:
        """List known venues."""
        from rich.table import Table

        table = Table(title="Supported Conferences")
        table.add_column("Venue", style="cyan")
        table.add_column("Full Name")
        table.add_column("Source")

        for key, info in sorted(KNOWN_VENUES.items()):
            source = "GitHub" if info.get("github") else "Official"
            table.add_row(key, info["name"], source)

        console.print(table)
        console.print("\n[dim]Usage: /venue <name> [year][/dim]")
        console.print("[dim]Example: /venue iclr 2025  or  /venue neurips 2024[/dim]")
        console.print("\n[dim]Can also search for unlisted venues - will search GitHub/CTAN[/dim]")

    async def _find_and_download(
        self,
        venue: str,
        year: str,
        session: SessionState,
        console: Console,
    ) -> bool:
        """Try multiple sources to find and download template."""
        venue_info = KNOWN_VENUES.get(venue, {})

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # 1. Try direct URL pattern if known
            if "url_pattern" in venue_info:
                url = venue_info["url_pattern"].format(year=year)
                console.print("  Trying official source...")
                if await self._download_from_url(url, session.project_root, console):
                    return True

            # 2. Try GitHub repo if known
            if "github" in venue_info:
                console.print(f"  Searching GitHub repo: {venue_info['github']}...")
                if await self._download_from_github(
                    venue_info["github"], venue, year, session.project_root, client, console
                ):
                    return True

            # 3. Search GitHub for any venue
            console.print(f"  Searching GitHub for {venue} {year}...")
            if await self._search_github(venue, year, session.project_root, client, console):
                return True

            # 4. Try CTAN
            console.print("  Searching CTAN...")
            if await self._search_ctan(venue, year, session.project_root, client, console):
                return True

        return False

    async def _download_from_url(
        self,
        url: str,
        target_dir: Path,
        console: Console,
    ) -> bool:
        """Download from direct URL."""
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(url)

                if response.status_code == 200:
                    if url.endswith(".zip"):
                        return self._extract_zip(response.content, target_dir, console)
                    else:
                        # Direct file
                        filename = url.split("/")[-1]
                        (target_dir / filename).write_bytes(response.content)
                        console.print(f"    [green]✓[/green] Downloaded: {filename}")
                        return True
        except Exception as e:
            console.print(f"    [dim]Failed: {e}[/dim]")

        return False

    async def _download_from_github(
        self,
        repo: str,
        venue: str,
        year: str,
        target_dir: Path,
        client: httpx.AsyncClient,
        console: Console,
    ) -> bool:
        """Download from GitHub repo.

        Strategy (in order):
        1. Check for a year-named subdirectory (e.g. ``iclr2026/``)
        2. Check for a year-named zip file (e.g. ``iclr2026.zip``)
        3. Look for year-matched style files at the repo root
        Do NOT fall back to wrong-year files — return False so the
        caller can try the next search strategy.
        """
        api_url = f"https://api.github.com/repos/{repo}/contents"

        try:
            response = await client.get(api_url)
            if response.status_code != 200:
                return False

            root_items = response.json()

            # --- 1. Year-named subdirectory (e.g. "iclr2026") ---------
            year_dirs = [
                item for item in root_items
                if item.get("type") == "dir"
                and venue in item.get("name", "").lower()
                and year in item.get("name", "")
            ]
            for dir_item in year_dirs:
                dir_name = dir_item["name"]
                console.print(f"    Found subdirectory: {dir_name}/")
                sub_url = f"{api_url}/{dir_name}"
                sub_resp = await client.get(sub_url)
                if sub_resp.status_code != 200:
                    continue
                sub_files = sub_resp.json()
                downloaded = await self._download_style_files_from_listing(
                    sub_files, target_dir, client, console,
                )
                if downloaded:
                    return True

            # --- 2. Year-named zip (e.g. "iclr2026.zip") --------------
            year_zips = [
                item for item in root_items
                if item.get("name", "").endswith(".zip")
                and venue in item.get("name", "").lower()
                and year in item.get("name", "")
            ]
            for zip_item in year_zips:
                zip_name = zip_item["name"]
                download_url = zip_item.get("download_url")
                if not download_url:
                    continue
                console.print(f"    Found archive: {zip_name}")
                zip_resp = await client.get(download_url)
                if zip_resp.status_code == 200:
                    if self._extract_zip(zip_resp.content, target_dir, console):
                        return True

            # --- 3. Year-matched style files at root -------------------
            year_matched = [
                item for item in root_items
                if any(item.get("name", "").endswith(ext) for ext in [".sty", ".bst", ".cls"])
                and venue in item.get("name", "").lower()
                and year in item.get("name", "")
            ]
            if year_matched:
                downloaded = await self._download_style_files_from_listing(
                    year_matched, target_dir, client, console,
                )
                if downloaded:
                    return True

            # Do NOT fall back to wrong-year files
            console.print(f"    [yellow]No {year} files found in {repo}[/yellow]")
            return False

        except Exception as e:
            console.print(f"    [dim]GitHub error: {e}[/dim]")
            return False

    async def _download_style_files_from_listing(
        self,
        file_listing: list[dict],
        target_dir: Path,
        client: httpx.AsyncClient,
        console: Console,
    ) -> list[str]:
        """Download .sty/.bst/.cls files from a GitHub API file listing.

        Returns the list of filenames that were successfully downloaded.
        """
        style_exts = (".sty", ".bst", ".cls")
        downloaded: list[str] = []
        for file_info in file_listing:
            if not isinstance(file_info, dict):
                continue
            name = file_info.get("name", "")
            if not any(name.endswith(ext) for ext in style_exts):
                continue
            download_url = file_info.get("download_url")
            if not download_url:
                continue
            file_response = await client.get(download_url)
            if file_response.status_code == 200:
                (target_dir / name).write_bytes(file_response.content)
                downloaded.append(name)
                console.print(f"    [green]✓[/green] Downloaded: {name}")
        return downloaded

    async def _search_github(
        self,
        venue: str,
        year: str,
        target_dir: Path,
        client: httpx.AsyncClient,
        console: Console,
    ) -> bool:
        """Search GitHub for template files.

        Uses the GitHub code search API to find .sty files matching the
        venue+year, then falls back to repository search with subdirectory
        traversal.
        """
        # --- Strategy A: GitHub code search for the exact .sty file ---
        code_query = f"{venue}{year} extension:sty"
        code_url = f"https://api.github.com/search/code?q={code_query}&per_page=5"
        try:
            code_resp = await client.get(code_url)
            if code_resp.status_code == 200:
                code_items = code_resp.json().get("items", [])
                for item in code_items:
                    name = item.get("name", "")
                    repo_info = item.get("repository", {})
                    repo_full = repo_info.get("full_name", "")
                    if not name.endswith(".sty"):
                        continue
                    if venue not in name.lower() or year not in name:
                        continue
                    # Get the raw download URL for this file
                    file_api = item.get("url")
                    if not file_api:
                        continue
                    console.print(f"    Found {name} in {repo_full}")
                    file_meta = await client.get(file_api)
                    if file_meta.status_code != 200:
                        continue
                    download_url = file_meta.json().get("download_url")
                    if not download_url:
                        continue
                    # Download this file and its siblings (.bst, .cls, etc.)
                    # by listing the containing directory
                    file_path = item.get("path", "")
                    dir_path = "/".join(file_path.split("/")[:-1]) if "/" in file_path else ""
                    dir_api = f"https://api.github.com/repos/{repo_full}/contents"
                    if dir_path:
                        dir_api += f"/{dir_path}"
                    dir_resp = await client.get(dir_api)
                    if dir_resp.status_code == 200:
                        downloaded = await self._download_style_files_from_listing(
                            dir_resp.json(), target_dir, client, console,
                        )
                        if downloaded:
                            return True
        except Exception:
            pass  # Fall through to repo search

        # --- Strategy B: Repo search with subdirectory traversal -------
        query = f"{venue} {year} latex template"
        search_url = f"https://api.github.com/search/repositories?q={query}&sort=stars&per_page=5"

        try:
            response = await client.get(search_url)
            if response.status_code != 200:
                return False

            results = response.json().get("items", [])

            for repo in results[:3]:
                repo_name = repo.get("full_name")
                console.print(f"    Checking: {repo_name}...")

                contents_url = f"https://api.github.com/repos/{repo_name}/contents"
                contents_response = await client.get(contents_url)

                if contents_response.status_code != 200:
                    continue

                root_items = contents_response.json()

                # Check year-named subdirectories first
                for item in root_items:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") == "dir" and year in item.get("name", ""):
                        sub_url = f"{contents_url}/{item['name']}"
                        sub_resp = await client.get(sub_url)
                        if sub_resp.status_code == 200:
                            downloaded = await self._download_style_files_from_listing(
                                sub_resp.json(), target_dir, client, console,
                            )
                            if downloaded:
                                return True

                # Check root-level style files
                downloaded = await self._download_style_files_from_listing(
                    root_items, target_dir, client, console,
                )
                if downloaded:
                    return True

        except Exception as e:
            console.print(f"    [dim]Search error: {e}[/dim]")

        return False

    async def _search_ctan(
        self,
        venue: str,
        year: str,
        target_dir: Path,
        client: httpx.AsyncClient,
        console: Console,
    ) -> bool:
        """Search CTAN for package."""
        # CTAN doesn't have a great API, but we can try direct package names
        package_names = [
            f"{venue}{year}",
            f"{venue}_{year}",
            f"{venue}-{year}",
            venue,
        ]

        for pkg in package_names:
            url = f"https://mirrors.ctan.org/macros/latex/contrib/{pkg}.zip"
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    if self._extract_zip(response.content, target_dir, console):
                        return True
            except Exception:
                pass

        return False

    def _extract_zip(
        self,
        content: bytes,
        target_dir: Path,
        console: Console,
    ) -> bool:
        """Extract style files from ZIP."""
        try:
            with zipfile.ZipFile(BytesIO(content)) as zf:
                extracted = []

                for name in zf.namelist():
                    filename = Path(name).name
                    if any(filename.endswith(ext) for ext in [".sty", ".bst", ".cls", ".tex"]):
                        # Skip example/sample files
                        if "example" in filename.lower() or "sample" in filename.lower():
                            continue
                        target = target_dir / filename
                        target.write_bytes(zf.read(name))
                        extracted.append(filename)
                        console.print(f"    [green]✓[/green] Extracted: {filename}")

                return len(extracted) > 0

        except Exception as e:
            console.print(f"    [dim]Extract error: {e}[/dim]")
            return False

    async def _offer_update_spec(
        self,
        venue: str,
        year: str,
        session: SessionState,
        console: Console,
    ) -> None:
        """Offer to update paper_spec.md."""
        console.print("\n[cyan]Update paper_spec.md with venue?[/cyan] [y/N] ", end="")

        try:
            response = await asyncio.to_thread(input)
            if response.lower() in ("y", "yes"):
                spec_path = session.project_root / "paper_spec.md"
                venue_name = KNOWN_VENUES.get(venue, {}).get("name", venue.upper())
                full_name = f"{venue_name} {year}"

                if spec_path.exists():
                    content = spec_path.read_text()
                    if 'venue:' in content:
                        content = re.sub(
                            r'venue:\s*"[^"]*"',
                            f'venue: "{full_name}"',
                            content
                        )
                    spec_path.write_text(content)

                    # Keep in-memory paper_spec in sync so later
                    # commands (e.g. /camera_ready) see the update
                    # without requiring a session restart.
                    if session.paper_spec:
                        session.paper_spec.venue = full_name

                    console.print(f"[green]✓ Updated venue to: {full_name}[/green]")

        except (EOFError, KeyboardInterrupt):
            pass

    def get_completions(self, partial: str) -> list[str]:
        """Get venue completions."""
        venues = list(KNOWN_VENUES.keys())
        years = ["2025", "2024", "2023"]

        if " " in partial:
            # Already have venue, suggest years
            return years
        return [v for v in venues if v.startswith(partial.lower())]

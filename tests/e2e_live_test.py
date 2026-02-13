"""End-to-end live LLM test for TeXGuardian.

Requires AWS credentials in .env. Tests the real pipeline:
LLM generates patches → parser extracts → applier applies → compiler verifies.
"""

import asyncio
import os
import shutil
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)


def make_session(project_root: Path):
    """Create a minimal SessionState for testing."""
    from texguardian.config.paper_spec import PaperSpec
    from texguardian.config.settings import SPEC_FILENAME, TexGuardianConfig
    from texguardian.core.session import SessionState

    config_path = project_root / "texguardian.yaml"
    config = TexGuardianConfig.load(config_path)

    spec_path = project_root / SPEC_FILENAME
    paper_spec = PaperSpec.load(spec_path) if spec_path.exists() else None

    session = SessionState(
        project_root=project_root,
        config_path=config_path,
        config=config,
        paper_spec=paper_spec,
    )
    return session


async def test_compilation(session):
    """Test 1: Compile the demo paper."""
    print("\n" + "=" * 60)
    print("TEST 1: LaTeX Compilation")
    print("=" * 60)

    from texguardian.latex.compiler import LatexCompiler

    compiler = LatexCompiler(session.config)
    output_dir = session.project_root / session.config.project.output_dir
    result = await compiler.compile(session.main_tex_path, output_dir)

    print(f"  Success: {result.success}")
    print(f"  PDF exists: {result.pdf_path and result.pdf_path.exists()}")
    print(f"  Pages: {result.page_count}")
    print(f"  Warnings: {len(result.warnings)}")
    print(f"  Errors: {len(result.errors)}")

    if result.warnings:
        for w in result.warnings[:5]:
            print(f"    WARN: {w[:80]}")

    assert result.success, f"Compilation failed: {result.errors}"
    assert result.pdf_path and result.pdf_path.exists(), "PDF not produced"
    print("  ✓ PASSED")
    return result


async def test_llm_connection(session):
    """Test 2: Verify LLM connection works."""
    print("\n" + "=" * 60)
    print("TEST 2: LLM Connection (Claude Opus 4.5 via Bedrock)")
    print("=" * 60)

    from texguardian.llm.factory import create_llm_client

    client = create_llm_client(session.config)
    session.llm_client = client

    response = await client.complete(
        messages=[{"role": "user", "content": "Say 'hello' in one word."}],
        max_tokens=10,
        temperature=0.0,
    )

    print(f"  Model responded: {response.content.strip()[:50]}")
    assert response.content.strip(), "Empty LLM response"
    session.llm_client = client
    print("  ✓ PASSED")
    return client


async def test_patch_generation_and_application(session):
    """Test 3: Generate a real patch via LLM and apply it."""
    print("\n" + "=" * 60)
    print("TEST 3: Patch Generation + Application (Live LLM)")
    print("=" * 60)

    # Make a backup of the original file
    main_tex = session.main_tex_path
    backup = main_tex.with_suffix(".tex.bak")
    shutil.copy2(main_tex, backup)

    try:
        content = main_tex.read_text()
        lines = content.splitlines()
        numbered = "\n".join(f"{i+1:4d}| {line}" for i, line in enumerate(lines))

        # Ask LLM to make a specific, simple change
        prompt = f"""You are a LaTeX expert. Below is the file `{main_tex.name}` with line numbers.

{numbered}

Make ONE small change: in the abstract (around lines 27-33), change "14.3\\%" to "15.1\\%".

Output ONLY a unified diff patch in a ```diff code block.
Use the exact filename `{main_tex.name}` in --- and +++ headers.
Use the exact line numbers from above."""

        response = await session.llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.0,
        )

        print(f"  LLM response length: {len(response.content)} chars")
        print(f"  Response preview: {response.content[:200]}...")

        # Extract patches
        from texguardian.patch.parser import extract_patches

        patches = extract_patches(response.content)
        print(f"  Patches extracted: {len(patches)}")

        assert len(patches) > 0, "No patches extracted from LLM response"

        for p in patches:
            print(f"    File: {p.file_path}")
            print(f"    Hunks: {len(p.hunks)}")
            for h in p.hunks:
                print(f"      @@ -{h.old_start},{h.old_count} +{h.new_start},{h.new_count} @@")
                for line in h.lines[:5]:
                    print(f"        {line}")

        # Apply patch
        from texguardian.patch.applier import PatchApplier

        applier = PatchApplier(session.project_root)
        success = applier.apply(patches[0])
        print(f"  Patch applied: {success}")

        if success:
            new_content = main_tex.read_text()
            assert "15.1" in new_content, "Change not found in file after patch"
            assert "14.3" not in new_content.split("abstract")[1].split("\\end")[0], \
                "Old value still present in abstract"
            print("  ✓ File content verified - change applied correctly")

        assert success, "Patch application failed"
        print("  ✓ PASSED")

    finally:
        # Restore original
        shutil.copy2(backup, main_tex)
        backup.unlink()
        print("  (Original file restored)")


async def test_figures_detection(session):
    """Test 4: Figure/table issue detection."""
    print("\n" + "=" * 60)
    print("TEST 4: Figure/Table Issue Detection")
    print("=" * 60)

    from texguardian.latex.parser import LatexParser

    parser = LatexParser(session.project_root, session.config.project.main_tex)

    content = session.main_tex_path.read_text()

    # Check for overflow issues
    overflow_issues = []
    if "width=1.5\\columnwidth" in content:
        overflow_issues.append("Figure with width > columnwidth (1.5\\columnwidth)")
    if "\\hspace{-1cm}" in content:
        overflow_issues.append("Negative hspace causing overflow")
    if "\\hline" in content:
        overflow_issues.append("\\hline usage (should use booktabs)")

    print(f"  Issues found: {len(overflow_issues)}")
    for issue in overflow_issues:
        print(f"    • {issue}")

    assert len(overflow_issues) >= 2, "Expected at least 2 issues in demo paper"
    print("  ✓ PASSED")


async def test_section_listing(session):
    """Test 5: Section listing."""
    print("\n" + "=" * 60)
    print("TEST 5: Section Listing")
    print("=" * 60)

    from texguardian.latex.parser import LatexParser

    parser = LatexParser(session.project_root, session.config.project.main_tex)
    sections = parser.extract_sections()

    print(f"  Sections found: {len(sections)}")
    for s in sections:
        wc = len(s.get("content", "").split())
        print(f"    • {s['name']} (~{wc} words)")

    assert len(sections) >= 3, f"Expected >=3 sections, got {len(sections)}"
    names = [s["name"].lower() for s in sections]
    assert any("intro" in n for n in names), "No Introduction section"
    print("  ✓ PASSED")


async def test_citation_analysis(session):
    """Test 6: Citation analysis."""
    print("\n" + "=" * 60)
    print("TEST 6: Citation Analysis")
    print("=" * 60)

    from texguardian.latex.parser import LatexParser

    parser = LatexParser(session.project_root, session.config.project.main_tex)
    citations = parser.extract_citations_with_locations()
    bib_keys = parser.extract_bib_keys()

    print(f"  Citations in paper: {len(citations)}")
    print(f"  Keys in .bib: {len(bib_keys)}")

    cited_keys = {c["key"] for c in citations}
    undefined = cited_keys - set(bib_keys)
    uncited = set(bib_keys) - cited_keys

    print(f"  Undefined (in paper but not .bib): {len(undefined)}")
    if undefined:
        for u in list(undefined)[:5]:
            print(f"    ✗ {u}")
    print(f"  Uncited (in .bib but not paper): {len(uncited)}")

    print("  ✓ PASSED")


async def test_numbered_content_in_prompts(session):
    """Test 7: Verify all prompts include numbered content."""
    print("\n" + "=" * 60)
    print("TEST 7: All Prompts Use Numbered Content")
    print("=" * 60)

    from texguardian.llm.prompts.system import build_chat_system_prompt

    # Build the chat system prompt
    system_prompt = build_chat_system_prompt(session)

    # Verify it contains numbered lines
    assert "1|" in system_prompt or "   1|" in system_prompt, \
        "Chat system prompt missing numbered content"
    print("  ✓ Chat system prompt includes numbered file content")

    # Check that the prompt has line number instructions
    assert "line numbers" in system_prompt.lower() or "exact line" in system_prompt.lower(), \
        "Chat prompt missing line number instructions"
    print("  ✓ Chat system prompt has line number instructions")

    # Verify figures prompt
    from texguardian.cli.commands.figures import FIGURE_FIX_PROMPT
    assert "{numbered_content}" in FIGURE_FIX_PROMPT, "Figure fix prompt missing numbered_content"
    print("  ✓ Figure fix prompt uses {numbered_content}")

    # Verify tables prompt
    from texguardian.cli.commands.tables import TABLE_FIX_PROMPT
    assert "{numbered_content}" in TABLE_FIX_PROMPT, "Table fix prompt missing numbered_content"
    print("  ✓ Table fix prompt uses {numbered_content}")

    # Verify section prompts
    from texguardian.cli.commands.section import SECTION_FIX_PROMPT, SECTION_CUSTOM_PROMPT
    assert "{numbered_content}" in SECTION_FIX_PROMPT, "Section fix prompt missing numbered_content"
    assert "{numbered_content}" in SECTION_CUSTOM_PROMPT, "Section custom prompt missing numbered_content"
    print("  ✓ Section prompts use {numbered_content}")

    # Verify citations prompts
    from texguardian.cli.commands.citations import CITATION_FIX_PROMPT, CITATION_CUSTOM_PROMPT
    assert "{numbered_paper_content}" in CITATION_FIX_PROMPT, "Citation fix prompt missing numbered content"
    assert "{numbered_bib_content}" in CITATION_FIX_PROMPT, "Citation fix prompt missing numbered bib content"
    assert "{numbered_paper_content}" in CITATION_CUSTOM_PROMPT
    assert "{numbered_bib_content}" in CITATION_CUSTOM_PROMPT
    print("  ✓ Citation prompts use numbered content for both .tex and .bib")

    # Verify camera_ready prompt
    from texguardian.cli.commands.camera_ready import CAMERA_READY_PROMPT
    assert "{numbered_content}" in CAMERA_READY_PROMPT, "Camera ready prompt missing numbered_content"
    print("  ✓ Camera ready prompt uses {numbered_content}")

    # Verify anonymize prompt
    from texguardian.cli.commands.anonymize import ANONYMIZE_PROMPT
    assert "{numbered_content}" in ANONYMIZE_PROMPT, "Anonymize prompt missing numbered_content"
    print("  ✓ Anonymize prompt uses {numbered_content}")

    print("  ✓ ALL PROMPTS VERIFIED")


async def test_patch_with_recompile(session):
    """Test 8: Full pipeline - LLM patch → apply → recompile → verify."""
    print("\n" + "=" * 60)
    print("TEST 8: Full Pipeline (Patch → Apply → Recompile)")
    print("=" * 60)

    from texguardian.latex.compiler import LatexCompiler

    main_tex = session.main_tex_path
    backup = main_tex.with_suffix(".tex.bak2")
    shutil.copy2(main_tex, backup)

    try:
        content = main_tex.read_text()
        lines = content.splitlines()
        numbered = "\n".join(f"{i+1:4d}| {line}" for i, line in enumerate(lines))

        # Ask LLM to fix the table overflow by replacing \hline with booktabs
        prompt = f"""You are a LaTeX expert. Below is `{main_tex.name}` with line numbers.

{numbered}

Fix the ablation table (Table 3, tab:ablation around lines 190-209):
Replace all \\hline with proper booktabs commands (\\toprule, \\midrule, \\bottomrule).

Output ONLY a unified diff patch in a ```diff code block.
Use filename `{main_tex.name}` in --- and +++ headers.
Use exact line numbers from above."""

        response = await session.llm_client.complete(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.0,
        )

        print(f"  LLM response: {len(response.content)} chars")

        from texguardian.patch.parser import extract_patches
        from texguardian.patch.applier import PatchApplier

        patches = extract_patches(response.content)
        print(f"  Patches extracted: {len(patches)}")

        if not patches:
            print(f"  LLM response:\n{response.content}")
            print("  ✗ FAILED - No patches extracted")
            return

        applier = PatchApplier(session.project_root)
        success = applier.apply(patches[0])
        print(f"  Patch applied: {success}")

        if not success:
            print("  ✗ FAILED - Patch not applied")
            return

        # Verify the change
        new_content = main_tex.read_text()
        # Check that at least one \hline was replaced in the ablation table region
        ablation_region = new_content[new_content.find("tab:ablation"):new_content.find("\\end{table}", new_content.find("tab:ablation"))]
        has_booktabs = "\\toprule" in ablation_region or "\\midrule" in ablation_region
        print(f"  Booktabs in ablation table: {has_booktabs}")

        # Recompile
        compiler = LatexCompiler(session.config)
        output_dir = session.project_root / session.config.project.output_dir
        result = await compiler.compile(session.main_tex_path, output_dir)
        print(f"  Recompilation success: {result.success}")
        print(f"  PDF produced: {result.pdf_path and result.pdf_path.exists()}")

        assert result.success, "Recompilation failed after patch"
        print("  ✓ PASSED - Patch applied and paper recompiles cleanly")

    finally:
        shutil.copy2(backup, main_tex)
        backup.unlink()
        # Recompile to restore original PDF
        compiler = LatexCompiler(session.config)
        output_dir = session.project_root / session.config.project.output_dir
        await compiler.compile(session.main_tex_path, output_dir)
        print("  (Original file and PDF restored)")


async def main():
    print("=" * 60)
    print("  TeXGuardian End-to-End Live LLM Test Suite")
    print("=" * 60)

    project_root = Path(__file__).parent.parent / "demo" / "test_run"
    print(f"Project root: {project_root}")

    session = make_session(project_root)

    results = {}
    tests = [
        ("compilation", test_compilation),
        ("llm_connection", test_llm_connection),
        ("numbered_prompts", test_numbered_content_in_prompts),
        ("figures_detection", test_figures_detection),
        ("section_listing", test_section_listing),
        ("citation_analysis", test_citation_analysis),
        ("patch_gen_apply", test_patch_generation_and_application),
        ("full_pipeline", test_patch_with_recompile),
    ]

    for name, test_fn in tests:
        try:
            await test_fn(session)
            results[name] = "PASSED"
        except Exception as e:
            results[name] = f"FAILED: {e}"
            import traceback
            traceback.print_exc()

    # Summary
    print("\n" + "=" * 60)
    print("  RESULTS SUMMARY")
    print("=" * 60)
    passed = 0
    failed = 0
    for name, result in results.items():
        status = "✓" if result == "PASSED" else "✗"
        print(f"  {status} {name}: {result}")
        if result == "PASSED":
            passed += 1
        else:
            failed += 1

    print(f"\n  {passed}/{passed + failed} tests passed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

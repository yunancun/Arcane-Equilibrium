from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS_README = ROOT / "docs" / "README.md"


def test_docs_agents_section_and_files_are_indexed() -> None:
    source = DOCS_README.read_text()
    assert "### docs/agents/" in source
    for rel in (
        "agents/domain.md",
        "agents/issue-tracker.md",
        "agents/triage-labels.md",
    ):
        assert rel in source
        assert (ROOT / "docs" / rel).exists()


def test_helper_script_index_is_linked_from_docs_readme() -> None:
    source = DOCS_README.read_text()
    assert "../helper_scripts/SCRIPT_INDEX.md" in source
    assert (ROOT / "helper_scripts" / "SCRIPT_INDEX.md").exists()


def test_archive_top_level_files_are_all_indexed() -> None:
    source = DOCS_README.read_text()
    for path in sorted((ROOT / "docs" / "archive").glob("*.md")):
        assert path.name in source


def test_ccagent_workspace_count_and_mit_bb_rows_are_indexed() -> None:
    source = DOCS_README.read_text()
    assert "19 個 Agent" in source
    assert "`CCAgentWorkSpace/MIT/`" in source
    assert "`CCAgentWorkSpace/BB/`" in source


def test_mit_bb_workspace_readmes_exist_at_workspace_level() -> None:
    for rel in (
        "docs/CCAgentWorkSpace/MIT/workspace/README.md",
        "docs/CCAgentWorkSpace/BB/workspace/README.md",
    ):
        assert (ROOT / rel).exists()

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS_README = ROOT / "docs" / "README.md"
IBKR_STOCK_ETF_PLAN = (
    ROOT
    / "docs"
    / "execution_plan"
    / "2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md"
)
IBKR_STOCK_ETF_OPERATOR = (
    ROOT
    / "docs"
    / "CCAgentWorkSpace"
    / "Operator"
    / "2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md"
)
IBKR_STOCK_ETF_CHECKPOINT_TITLE_RE = re.compile(
    r"^## \d+\. 2026-\d{2}-\d{2} PM session .*?：(.+)$",
    re.MULTILINE,
)


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


def test_ccagent_workspace_count_and_broker_ops_rows_are_indexed() -> None:
    source = DOCS_README.read_text()
    registry = json.loads((ROOT / ".codex/agent_registry_v1.json").read_text())
    assert f"{len(registry['roles'])} 個 generated development role presets" in source
    for role in ("MIT", "BB", "IB", "OPS"):
        assert f"`CCAgentWorkSpace/{role}/`" in source


def test_mit_bb_workspace_readmes_exist_at_workspace_level() -> None:
    for rel in (
        "docs/CCAgentWorkSpace/MIT/workspace/README.md",
        "docs/CCAgentWorkSpace/BB/workspace/README.md",
    ):
        assert (ROOT / rel).exists()


def test_ibkr_stock_etf_pm_checkpoint_numbers_are_linear() -> None:
    source = IBKR_STOCK_ETF_PLAN.read_text()
    checkpoint_numbers = [
        int(match.group(1))
        for match in re.finditer(
            r"^## (\d+)\. 2026-\d{2}-\d{2} PM session .*checkpoint",
            source,
            re.MULTILINE,
        )
    ]

    assert checkpoint_numbers
    expected = list(range(checkpoint_numbers[0], checkpoint_numbers[-1] + 1))
    assert checkpoint_numbers == expected


def test_ibkr_stock_etf_plan_and_operator_cover_pm_memory_trace_titles() -> None:
    plan_source = IBKR_STOCK_ETF_PLAN.read_text()
    operator_source = IBKR_STOCK_ETF_OPERATOR.read_text()
    required_titles = IBKR_STOCK_ETF_CHECKPOINT_TITLE_RE.findall(plan_source)

    assert "Stock/ETF Index Reference Integrity Static Guard" in required_titles
    assert len(required_titles) >= 120

    for title in required_titles:
        assert title in plan_source
        assert title in operator_source

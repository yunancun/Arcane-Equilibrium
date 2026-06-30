from __future__ import annotations

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
    required_titles = (
        "Source Posture Header Catch-up",
        "Rust Connector Skeleton Readiness Source",
        "Read-Only Probe Request Contract",
        "Read-Only Probe Readiness Gate",
        "Python Connector Network Static Guard",
        "GUI Endpoint Template Consistency Guard",
        "GUI Static Endpoint Template Consistency Guard",
        "FastAPI Route Auth Coverage Guard",
        "FastAPI Route Cache Header Coverage Guard",
        "FastAPI IPC Empty Params Guard",
        "FastAPI Handler Client-State Guard",
        "FastAPI IPC Method Allowlist Guard",
        "Python Persistence Static Guard",
        "OpenAPI Client Input Surface Guard",
        "Rust Status IPC Untrusted Params Guard",
        "Rust Dispatch Registry Routing Guard",
        "GUI Data/Policy Fallback Split Guard",
        "Rust IPC Test Split Guard",
        "Rust IPC Handler Split Guard",
        "Route Fixture Split Guard",
        "Rust IPC Request Contract Test Split Guard",
        "Rust IPC Handler Request Summary Split Guard",
        "FastAPI Route IPC Query Helper Guard",
        "GUI Fallback Payload Split Guard",
        "GUI Data/Policy Renderer Split Guard",
        "GUI Authorization/Account Renderer Split Guard",
        "GUI Evidence/Paper Renderer Split Guard",
        "GUI Scorecard/Launch Renderer Split Guard",
        "GUI Readiness Renderer Split Guard",
    )
    plan_source = IBKR_STOCK_ETF_PLAN.read_text()
    operator_source = IBKR_STOCK_ETF_OPERATOR.read_text()

    for title in required_titles:
        assert title in plan_source
        assert title in operator_source

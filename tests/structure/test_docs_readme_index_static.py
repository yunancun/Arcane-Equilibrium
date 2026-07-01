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
        "Python Secret/Env Access Static Guard",
        "Rust IPC Secret/Env Material Static Guard",
        "Rust Feature Flag Env Allowlist Guard",
        "IBKR Connector Preview Payload Guard",
        "IBKR Connector Bybit Import Separation Guard",
        "FastAPI IBKR Connector Runtime Wiring Guard",
        "Rust IPC Bybit Runtime Separation Guard",
        "IBKR Connector Public API Freeze Guard",
        "Python Runtime Side-Effect Static Guard",
        "Rust IPC Runtime Side-Effect Static Guard",
        "GUI Background Work Static Guard",
        "GUI One-Shot Fanout Budget Guard",
        "Collector Run Contract",
        "DQ Manifest Contract",
        "Evidence Clock Lineage Guard",
        "Phase3 Evidence Module Split Guard",
        "Connector Attestation Preview Guard",
        "Session Attestation Data-Tier Lineage Guard",
        "Read-Only Probe Result Import Request Contract",
        "Phase0 Result-Import Display Lineage Guard",
        "Readiness Result-Import Request Guard",
        "Connector Result-Import Preview Guard",
        "Scorecard Input Result-Import Lineage Guard",
        "Scorecard Fallback Input Lineage Guard",
        "Scorecard Status Module Split Guard",
        "Python No-Write Static Guard Split Guard",
        "Scorecard Input Module Split Guard",
        "Rust IPC Parent Module Split Guard",
        "Paper Order Request Module Split Guard",
        "Connector Risky Config Blocker Guard",
        "Phase2 Policy Source Static Guard",
        "Lane-Scoped IPC Source Static Guard",
        "Stock/ETF Lane Source Static Guard",
        "IBKR Phase2 Gate Source Static Guard",
        "IBKR Phase2 Runtime Source Static Guard",
        "IBKR Phase2 Artifact Source Static Guard",
        "IBKR Feature Flag Secret Auth Source Static Guard",
        "IBKR Non-Bybit API Allowlist Source Static Guard",
        "Stock/ETF Broker Capability Registry Source Static Guard",
        "Stock/ETF Risk Policy Source Static Guard",
        "Stock/ETF Paper Order Request Source Static Guard",
        "IBKR Paper Lifecycle Source Static Guard",
        "Stock/ETF Paper Fill Import Request Source Static Guard",
        "Stock/ETF Paper Shadow Reconciliation Source Static Guard",
        "Stock/ETF Shadow Signal Request Source Static Guard",
        "Stock/ETF Scorecard Inputs Source Static Guard",
        "Stock/ETF Scorecard Derivation Source Static Guard",
        "Stock/ETF Scorecard Verdict Source Static Guard",
        "Stock/ETF Tiny-Live Eligibility Source Static Guard",
        "Stock/ETF Release Packet Source Static Guard",
        "Stock/ETF Phase0 Manifest Source Static Guard",
        "Stock/ETF Asset-Lane Audit Events Source Static Guard",
        "Stock/ETF DB Evidence DDL Source Static Guard",
        "Stock/ETF Disable Cleanup Runbook Source Static Guard",
        "Stock/ETF GUI Lane Contract Source Static Guard",
    )
    plan_source = IBKR_STOCK_ETF_PLAN.read_text()
    operator_source = IBKR_STOCK_ETF_OPERATOR.read_text()

    for title in required_titles:
        assert title in plan_source
        assert title in operator_source

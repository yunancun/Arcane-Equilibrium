from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
SPECS_ROOT = ROOT / "docs/execution_plan/specs"
MIGRATIONS_ROOT = ROOT / "sql/migrations"
IBKR_STOCK_ETF_PLAN = (
    ROOT
    / "docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md"
)
IBKR_STOCK_ETF_OPERATOR = (
    ROOT
    / "docs/CCAgentWorkSpace/Operator"
    / "2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md"
)
EXPECTED_SPEC_ARTIFACTS = (
    "2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json",
    "2026-06-29--stock_etf_cash_phase0_named_contract_packet.md",
    "2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql",
)
TEST_REFERENCE_PATTERNS = (
    "tests/structure/**/*.py",
    "rust/openclaw_types/tests/**/*.rs",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/tests/**/*.py",
)
TRACE_DOCS = (
    IBKR_STOCK_ETF_PLAN,
    IBKR_STOCK_ETF_OPERATOR,
)
REQUIRED_GLOBAL_DENIALS = (
    "ibkr_live",
    "tiny_live",
    "margin",
    "short",
    "options",
    "cfd",
    "transfer",
    "account_management_writes",
    "python_broker_write_authority",
    "gui_lane_authority",
    "automatic_promotion",
)


def _stock_etf_ibkr_spec_artifacts() -> list[Path]:
    return sorted(
        path
        for path in SPECS_ROOT.iterdir()
        if path.is_file() and ("stock_etf" in path.name or "ibkr" in path.name)
    )


def _reference_text() -> str:
    chunks = []
    for pattern in TEST_REFERENCE_PATTERNS:
        for path in ROOT.glob(pattern):
            if path.resolve() == THIS_FILE:
                continue
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def test_stock_etf_phase0_spec_artifact_scan_scope_is_exact() -> None:
    names = tuple(path.name for path in _stock_etf_ibkr_spec_artifacts())

    assert names == EXPECTED_SPEC_ARTIFACTS
    assert "2026-05-29--basis-panel-infra-spec.md" not in names
    assert "2026-05-26--p0-ops-4-first-day-live-runbook.md" not in names


def test_stock_etf_phase0_spec_artifacts_are_directly_referenced_by_tests() -> None:
    source = _reference_text()
    uncovered = []

    for path in _stock_etf_ibkr_spec_artifacts():
        rel = path.relative_to(ROOT).as_posix()
        if rel not in source and path.name not in source:
            uncovered.append(rel)

    assert uncovered == []


def test_stock_etf_phase0_spec_artifacts_are_listed_in_launch_trace_docs() -> None:
    for trace_doc in TRACE_DOCS:
        source = trace_doc.read_text(encoding="utf-8")
        missing = []
        for path in _stock_etf_ibkr_spec_artifacts():
            rel = path.relative_to(ROOT).as_posix()
            if rel not in source and path.name not in source:
                missing.append(rel)

        assert missing == [], trace_doc.relative_to(ROOT).as_posix()


def test_stock_etf_phase0_manifest_json_keeps_fail_closed_authority() -> None:
    raw = (
        SPECS_ROOT
        / "2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json"
    ).read_text(encoding="utf-8")
    manifest = json.loads(raw)

    assert manifest["schema"] == "stock_etf_phase0_contract_packet_manifest_v1"
    assert manifest["status"] == "ACCEPTED_PHASE0_CONTRACT_NO_RUNTIME_AUTHORITY"
    assert manifest["asset_lane"] == "stock_etf_cash"
    assert manifest["broker"] == "ibkr"
    assert manifest["scope"] == "paper_shadow_only"
    assert (
        manifest["authority"]["contract_packet"]
        == "docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md"
    )
    assert manifest["api_baseline"]["selected"] == "ib_gateway_tws_api"
    assert manifest["api_baseline"]["host_policy"] == "loopback_only"
    assert manifest["api_baseline"]["paper_port_default_candidate"] == 4002
    assert manifest["api_baseline"]["live_ports_denied"] is True
    assert manifest["api_baseline"]["ibkr_call_performed"] is False

    for denial in REQUIRED_GLOBAL_DENIALS:
        assert manifest["global_denials"][denial] is True

    assert (
        manifest["phase_unlock"]["phase2_ibkr_external_contact"]
        == "BLOCKED_UNTIL_PHASE2_EXTERNAL_SURFACE_GATE_PASS"
    )
    assert (
        manifest["phase_unlock"]["phase5_paper_shadow_online"]
        == "BLOCKED_UNTIL_RELEASE_PACKET_AND_SHAKEDOWN_PASS"
    )
    assert manifest["phase_unlock"]["tiny_live_or_live"] == "BLOCKED_REQUIRES_FUTURE_ADR"


def test_stock_etf_phase0_contract_packet_keeps_no_runtime_authority_boundary() -> None:
    source = (
        SPECS_ROOT / "2026-06-29--stock_etf_cash_phase0_named_contract_packet.md"
    ).read_text(encoding="utf-8")

    for token in (
        "Status: **Accepted Phase 0 contract packet - no runtime authority**",
        "It does not authorize:",
        "- IBKR API calls",
        "- IBKR process startup",
        "- secret-slot creation",
        "- broker-paper order submission",
        "- GUI runtime stock/ETF activation",
        "- DB migration apply",
        "- evidence clock start",
        "- tiny-live or live",
        "Rust authority",
        "Python boundary",
        "Evidence boundary",
    ):
        assert token in source


def test_stock_etf_db_evidence_source_sql_stays_source_only_and_out_of_migrations() -> None:
    source = (
        SPECS_ROOT / "2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql"
    ).read_text(encoding="utf-8")

    for token in (
        "SOURCE-ONLY DDL DRAFT",
        "Do not copy into sql/migrations/ or apply",
        "Linux Postgres dry-run",
        "idempotency double-apply proof",
        "PM/Operator migration apply authorization",
        "CREATE SCHEMA IF NOT EXISTS broker",
        "CREATE SCHEMA IF NOT EXISTS research",
        "CREATE SCHEMA IF NOT EXISTS audit",
        "CHECK (asset_lane = 'stock_etf_cash')",
        "CHECK (broker = 'ibkr')",
    ):
        assert token in source

    migration_copies = []
    if MIGRATIONS_ROOT.exists():
        migration_copies = [
            path.relative_to(ROOT).as_posix()
            for path in MIGRATIONS_ROOT.rglob("*stock_etf_db_evidence_ddl_v1*")
            if path.is_file()
        ]

    assert migration_copies == []

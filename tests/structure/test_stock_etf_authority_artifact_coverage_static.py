from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()
ADR_ROOT = ROOT / "docs/adr"
AMD_ROOT = ROOT / "docs/governance_dev/amendments"
IBKR_STOCK_ETF_PLAN = (
    ROOT
    / "docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md"
)
IBKR_STOCK_ETF_OPERATOR = (
    ROOT
    / "docs/CCAgentWorkSpace/Operator"
    / "2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md"
)
EXPECTED_AUTHORITY_ARTIFACTS = (
    "docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md",
    "docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md",
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


def _stock_etf_authority_artifacts() -> list[Path]:
    artifacts = []
    artifacts.extend(
        path
        for path in ADR_ROOT.iterdir()
        if path.is_file() and "ibkr-stock-etf" in path.name
    )
    artifacts.extend(
        path
        for path in AMD_ROOT.iterdir()
        if path.is_file() and "ibkr-stock-etf" in path.name
    )
    return sorted(artifacts)


def _reference_text() -> str:
    chunks = []
    for pattern in TEST_REFERENCE_PATTERNS:
        for path in ROOT.glob(pattern):
            if path.resolve() == THIS_FILE:
                continue
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def test_stock_etf_authority_artifact_scan_scope_is_exact() -> None:
    rels = tuple(path.relative_to(ROOT).as_posix() for path in _stock_etf_authority_artifacts())

    assert rels == EXPECTED_AUTHORITY_ARTIFACTS
    assert "docs/adr/0006-bybit-only-exchange.md" not in rels
    assert "docs/adr/0040-multi-venue-gate-spec.md" not in rels


def test_stock_etf_authority_artifacts_are_directly_referenced_by_tests() -> None:
    source = _reference_text()
    uncovered = []

    for path in _stock_etf_authority_artifacts():
        rel = path.relative_to(ROOT).as_posix()
        if rel not in source and path.name not in source:
            uncovered.append(rel)

    assert uncovered == []


def test_stock_etf_authority_artifacts_are_listed_in_launch_trace_docs() -> None:
    for trace_doc in TRACE_DOCS:
        source = trace_doc.read_text(encoding="utf-8")
        missing = []
        for path in _stock_etf_authority_artifacts():
            rel = path.relative_to(ROOT).as_posix()
            if rel not in source and path.name not in source:
                missing.append(rel)

        assert missing == [], trace_doc.relative_to(ROOT).as_posix()


def test_adr_0048_keeps_stock_etf_paper_shadow_only_authority() -> None:
    source = (ROOT / EXPECTED_AUTHORITY_ARTIFACTS[0]).read_text(encoding="utf-8")

    for token in (
        "status: accepted",
        "scope: stock_etf_cash paper/shadow research only",
        "Status: **Accepted - paper/shadow governance scope only**",
        "Bybit remains the only active live execution venue.",
        "IBKR live, tiny-live, margin, short, options, CFD, transfers",
        "`asset_lane = stock_etf_cash`",
        "`broker = ibkr`",
        "`environment in {readonly, paper, shadow}`",
        "`live`, `tiny_live`, `margin`, `short`, `options`, `cfd`, `transfer`",
        "Denied; positive paper/shadow may only open a new ADR discussion",
        "No `Other(String)`, catch-all broker, catch-all lane",
    ):
        assert token in source


def test_adr_0048_keeps_denied_paths_and_runtime_boundaries() -> None:
    source = (ROOT / EXPECTED_AUTHORITY_ARTIFACTS[0]).read_text(encoding="utf-8")

    for token in (
        "Functional `OPENCLAW_IBKR_LIVE_ENABLED`.",
        "Creating `$OPENCLAW_SECRETS_DIR/external/ibkr/live/`.",
        "Reusing Bybit paper `submit_paper_order` IPC",
        "Python broker write authority or Python retrying broker writes.",
        "Treating GUI lane selection, localStorage, query params, or hidden form fields as authorization.",
        "Treating IBKR paper fills as live fills.",
        "Treating 6-8 weeks of paper/shadow evidence as durable alpha proof by itself.",
        "It may expose blocked readiness/previews and secret-free fixtures only",
        "it must not import IBKR SDKs, open sockets or HTTP sessions, read secrets",
    ):
        assert token in source


def test_amd_20260629_keeps_bybit_live_and_ibkr_research_boundary() -> None:
    source = (ROOT / EXPECTED_AUTHORITY_ARTIFACTS[1]).read_text(encoding="utf-8")

    for token in (
        "Status: **Active - paper/shadow research amendment**",
        "Scope: `stock_etf_cash` paper/shadow research lane only.",
        "Bybit remains the only active live execution venue.",
        "The first accepted non-Bybit broker-paper exception is `stock_etf_cash`",
        "This amendment does not approve any IBKR live, tiny-live, margin, short, options, CFD, transfer, or account-management write surface.",
        "`docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md`",
        "`docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md`",
        "`docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json`",
    ):
        assert token in source


def test_amd_20260629_keeps_secret_runtime_and_evidence_denials() -> None:
    source = (ROOT / EXPECTED_AUTHORITY_ARTIFACTS[1]).read_text(encoding="utf-8")

    for token in (
        "$OPENCLAW_SECRETS_DIR/external/ibkr/readonly/",
        "$OPENCLAW_SECRETS_DIR/external/ibkr/paper/",
        "$OPENCLAW_SECRETS_DIR/external/ibkr/live/",
        "Environment-variable fallback is not allowed.",
        "Rust remains the trading, risk, strategy-config, and execution authority.",
        "Python must not own broker order truth",
        "The current `program_code/broker_connectors/ibkr_connector/` package is an inert source-only skeleton.",
        "it must not import IBKR SDKs, open sockets or HTTP sessions, read secrets",
        "Positive paper/shadow evidence may only trigger a new `tiny_live_adr_eligibility_v1` discussion.",
        "cannot authorize connector runtime, tiny-live, live, account-management writes, or secret creation.",
    ):
        assert token in source

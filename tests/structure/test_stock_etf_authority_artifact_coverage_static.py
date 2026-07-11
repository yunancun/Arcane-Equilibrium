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
AMD_20260708 = ROOT / "docs/governance_dev/amendments/2026-07-08--AMD-2026-07-08-01-ibkr-phase2-external-contact-readonly.md"
AMD_20260709 = ROOT / "docs/governance_dev/amendments/2026-07-09--AMD-2026-07-09-01-ibkr-credential-provisioning-write-path.md"
EXPECTED_AUTHORITY_ARTIFACTS = (
    "docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md",
    "docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md",
    "docs/governance_dev/amendments/2026-07-11--AMD-2026-07-11-01-ibkr-stock-etf-full-live-capability-development.md",
)
TEST_REFERENCE_PATTERNS = (
    "tests/structure/**/*.py",
    "rust/openclaw_types/tests/**/*.rs",
    "program_code/exchange_connectors/bybit_connector/control_api_v1/tests/**/*.py",
)
TRACE_DOCS = (ROOT / "docs/_indexes/document_index.md",)


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


def test_adr_0048_records_the_accepted_capability_supersession() -> None:
    source = (ROOT / EXPECTED_AUTHORITY_ARTIFACTS[0]).read_text(encoding="utf-8")

    for token in (
        "status: accepted_amended_in_part",
        "AMD-2026-07-11-01",
        "production-wired capability development",
        "ibkr_activation_envelope_v1",
        "credentials or session never",
        "Margin, short, options, CFD, transfer, account-management",
        "No `Other(String)`, catch-all broker, catch-all lane",
    ):
        assert token in source


def test_adr_0048_keeps_non_product_and_python_denials() -> None:
    source = (ROOT / EXPECTED_AUTHORITY_ARTIFACTS[0]).read_text(encoding="utf-8")

    for token in (
        "Reusing Bybit paper `submit_paper_order` IPC",
        "Python broker write authority or Python retrying broker writes.",
        "Treating GUI lane selection, localStorage, query params, or hidden form fields as authorization.",
        "Treating IBKR paper fills as live fills.",
        "Treating 6-8 weeks of paper/shadow evidence as durable alpha proof by itself.",
        "Treating GUI lane selection, localStorage, query params, or hidden form fields as authorization.",
    ):
        assert token in source


def test_amd_20260629_is_explicitly_superseded_in_part() -> None:
    source = (ROOT / EXPECTED_AUTHORITY_ARTIFACTS[1]).read_text(encoding="utf-8")

    for token in (
        "Status: **Superseded in part by AMD-2026-07-11-01",
        "AMD-2026-07-11-01 supersedes this",
        "Credentials/session never auto-activate.",
        "Rust authority",
        "margin/short/options/CFD/transfer/",
    ):
        assert token in source


def test_amd_20260711_binds_development_to_explicit_activation() -> None:
    source = (ROOT / EXPECTED_AUTHORITY_ARTIFACTS[2]).read_text(encoding="utf-8")

    for token in (
        "This is a development authorization, not broker activation.",
        "ibkr_activation_envelope_v1",
        "Credentials/session never auto-activate.",
        "Rust is the sole order, execution, risk, and activation authority",
        "global Cost Gate must not be reduced",
        "margin`, `short`, `options`, `cfd`, `transfer`",
        "Rust-owned, authenticated Operator activation record",
        "Rust atomically consumes the nonce",
        "Python, FastAPI, and the GUI may request or display",
        "Phase 2 owner-only read-only seal and its approval are not an",
        "activation authority and cannot be substituted for this record.",
        "Credential custody boundary",
        "variable credential fallback.",
        "This requirement applies to every real-contact mode, including readonly and",
    ):
        assert token in source


def test_superseded_phase2_and_credential_amendments_point_to_current_policy() -> None:
    phase2 = AMD_20260708.read_text(encoding="utf-8")
    credential_draft = AMD_20260709.read_text(encoding="utf-8")

    for token in (
        "Status: **Superseded in part by AMD-2026-07-11-01",
        "AMD-2026-07-11-01 replaces this",
        "ibkr_activation_envelope_v1",
        "Credentials/session never auto-activate.",
    ):
        assert token in phase2

    for token in (
        "Status: **Superseded before acceptance by AMD-2026-07-11-01",
        "This draft was never accepted",
        "no credential-write authority.",
        "credential/session presence never activates",
        "ibkr_activation_envelope_v1",
    ):
        assert token in credential_draft

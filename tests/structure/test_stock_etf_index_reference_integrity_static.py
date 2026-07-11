from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INDEX_DOCS = (
    ROOT / "docs/_indexes/document_index.md",
    ROOT / "docs/_indexes/initiative_index.md",
)
PATH_PREFIXES = (
    "docs/",
    "settings/",
    "adr/",
    "governance_dev/",
    "execution_plan/",
    "CCAgentWorkSpace/",
)
REQUIRED_INDEX_REFERENCES = (
    "docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md",
    "docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md",
    "docs/governance_dev/amendments/2026-07-11--AMD-2026-07-11-01-ibkr-stock-etf-full-live-capability-development.md",
    "docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md",
    "docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json",
    "docs/execution_plan/specs/2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql",
    "docs/execution_plan/2026-06-29--ibkr_stock_etf_paper_shadow_development_arrangement.md",
    "docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md",
    "docs/CCAgentWorkSpace/Operator/2026-06-29--ibkr_stock_etf_plan_round3_pm_launch_certification.md",
)
EXPECTED_NON_PATH_CODE_SPANS = {
    "/api/v1/stock-etf/readiness",
    "first_ibkr_contact_allowed=false",
    "stock_etf.*",
}


def _ibkr_stock_etf_code_spans() -> list[str]:
    spans = []
    for index_doc in INDEX_DOCS:
        source = index_doc.read_text(encoding="utf-8")
        spans.extend(
            match.group(1)
            for match in re.finditer(r"`([^`]+)`", source)
            if re.search(r"ibkr|stock[_-]etf|ADR-0048|AMD-2026-06-29-01", match.group(1), re.I)
        )
    return sorted(set(spans))


def _is_path_like(span: str) -> bool:
    if span in EXPECTED_NON_PATH_CODE_SPANS:
        return False
    if span.startswith("/"):
        return False
    return "/" in span and span.startswith(PATH_PREFIXES)


def _resolve_index_path(span: str) -> Path:
    if span.startswith(("docs/", "settings/")):
        return ROOT / span
    return ROOT / "docs" / span


def _normalized_index_path_spans() -> list[str]:
    normalized = []
    for span in _ibkr_stock_etf_code_spans():
        if _is_path_like(span):
            normalized.append(_resolve_index_path(span).relative_to(ROOT).as_posix())
    return sorted(set(normalized))


def test_stock_etf_index_reference_integrity_scope_includes_router_files() -> None:
    for index_doc in INDEX_DOCS:
        assert index_doc.exists()

    spans = _ibkr_stock_etf_code_spans()
    assert "docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md" in spans
    assert "docs/execution_plan/specs/2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql" in spans
    assert "/api/v1/stock-etf/readiness" in spans
    assert "first_ibkr_contact_allowed=false" in spans


def test_stock_etf_index_path_references_all_exist() -> None:
    missing = {}
    for span in _ibkr_stock_etf_code_spans():
        if not _is_path_like(span):
            continue
        resolved = _resolve_index_path(span)
        if not resolved.exists():
            missing[span] = resolved.relative_to(ROOT).as_posix()

    assert missing == {}


def test_stock_etf_index_keeps_required_launch_trace_references() -> None:
    joined_spans = "\n".join(_normalized_index_path_spans())
    missing = [reference for reference in REQUIRED_INDEX_REFERENCES if reference not in joined_spans]

    assert missing == []

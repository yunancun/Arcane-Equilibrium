from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STABLE_BOUNDARY_DOCS = {
    "CLAUDE.md": ROOT / "CLAUDE.md",
    ".codex/MEMORY.md": ROOT / ".codex/MEMORY.md",
    "README.md": ROOT / "README.md",
    "docs/_indexes/document_index.md": ROOT / "docs/_indexes/document_index.md",
    "docs/_indexes/initiative_index.md": ROOT / "docs/_indexes/initiative_index.md",
    "docs/governance_dev/SPECIFICATION_REGISTER.md": (
        ROOT / "docs/governance_dev/SPECIFICATION_REGISTER.md"
    ),
}
REQUIRED_STABLE_TOKENS = {
    "CLAUDE.md": (
        "Bybit remains the only active live execution exchange.",
        "IBKR `stock_etf_cash` read-only/paper/shadow research per",
        "ADR-0048 + AMD-2026-06-29-01. IBKR live/tiny-live remains denied.",
        "separate research/evidence lane and",
        "still cannot auto-promote to tiny-live, live, or durable-alpha proof.",
    ),
    ".codex/MEMORY.md": (
        "Bybit remains the only active live execution exchange target.",
        "IBKR `stock_etf_cash` read-only/paper/shadow research per",
        "ADR-0048 + AMD-2026-06-29-01. IBKR live/tiny-live remains denied.",
        "paper/shadow lane is separate research evidence and cannot auto-promote to",
        "tiny-live, live, or durable-alpha proof.",
    ),
    "README.md": (
        "**Bybit** 仍是唯一 active live execution",
        "IBKR `stock_etf_cash` read-only / paper / shadow research lane",
        "IBKR live / tiny-live / margin / short / options / CFD / transfer 仍禁止",
        "不是 live/tiny-live 或 durable-alpha promotion lane",
    ),
    "docs/_indexes/document_index.md": (
        "2026-06-29 IBKR Stock/ETF paper + shadow feasibility lane",
        "`adr/0048-ibkr-stock-etf-paper-shadow-lane.md`",
        "`governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md`",
        "live/non-Bybit execution 仍禁止",
        "不授權 runtime/API/secret/order",
    ),
    "docs/_indexes/initiative_index.md": (
        "| IBKR Stock/ETF paper + shadow lane |",
        "Phase 0 ADR/AMD + named contract packet 已落地",
        "下一步仍需 real secret/topology evidence + immutable Phase 2 PASS artifact",
        "不允許 IBKR API/secret-content read/connector/runtime/evidence clock/GUI lane authority/tiny-live/live",
    ),
    "docs/governance_dev/SPECIFICATION_REGISTER.md": (
        "AMD-2026-06-29-01",
        "IBKR `stock_etf_cash` paper/shadow research lane boundary",
        "Bybit remains the only active live execution exchange",
        "IBKR is limited to read-only / paper / shadow",
        "Denies IBKR live/tiny-live/margin/short/options/CFD/transfer/account-management writes",
        "| ADR-0048 | IBKR Stock/ETF Paper + Shadow Lane |",
        "IBKR contact still requires real secret/topology evidence plus immutable PASS artifact",
    ),
}
FORBIDDEN_STABLE_CLAIMS = (
    "ibkr live is approved",
    "ibkr live is allowed",
    "ibkr live authorized",
    "ibkr tiny-live authorized",
    "ibkr runtime approved",
    "ibkr connector runtime approved",
    "ibkr paper order route approved",
    "first ibkr contact allowed=true",
    "stock_etf_cash live enabled",
)


def test_stock_etf_stable_boundary_docs_exist() -> None:
    missing = [rel for rel, path in STABLE_BOUNDARY_DOCS.items() if not path.exists()]

    assert missing == []


def test_stock_etf_stable_boundary_docs_keep_required_ibkr_bybit_tokens() -> None:
    missing = {}
    for rel, required_tokens in REQUIRED_STABLE_TOKENS.items():
        source = STABLE_BOUNDARY_DOCS[rel].read_text(encoding="utf-8")
        absent = [token for token in required_tokens if token not in source]
        if absent:
            missing[rel] = absent

    assert missing == {}


def test_stock_etf_stable_boundary_docs_do_not_claim_ibkr_runtime_authority() -> None:
    violations = {}
    for rel, path in STABLE_BOUNDARY_DOCS.items():
        source = path.read_text(encoding="utf-8").lower()
        hits = [claim for claim in FORBIDDEN_STABLE_CLAIMS if claim in source]
        if hits:
            violations[rel] = hits

    assert violations == {}

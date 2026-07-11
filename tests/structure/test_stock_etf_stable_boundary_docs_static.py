from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STABLE_BOUNDARY_DOCS = {
    "AGENTS.md": ROOT / "AGENTS.md",
    ".codex/agent_registry_v1.json": ROOT / ".codex/agent_registry_v1.json",
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
    "AGENTS.md": (
        "AMD-2026-07-11-01",
        "permits IBKR `stock_etf_cash`",
        "ibkr_activation_envelope_v1",
        "credentials/session never auto-activate",
    ),
    ".codex/agent_registry_v1.json": (
        "capability-vs-activation separation",
        "Capability development is allowed under AMD-2026-07-11-01",
        "Tiny-live/live effects require explicit time-bounded",
        "credentials/session never auto-activate",
    ),
    "CLAUDE.md": (
        "AMD-2026-07-11-01 authorizes development",
        "ibkr_activation_envelope_v1",
        "IBKR is inactive and `EXTERNAL_VERIFICATION_PENDING`",
        "Credentials and sessions never",
        "global Cost Gate",
        "authenticated Operator activation record.",
        "Rust atomically consumes its nonce",
        "Credential custody remains",
    ),
    ".codex/MEMORY.md": (
        "AMD-2026-07-11-01 permits `stock_etf_cash`",
        "EXTERNAL_VERIFICATION_PENDING",
        "ibkr_activation_envelope_v1",
        "credentials/session never auto-activate",
        "Python order/risk/activation authority remain denied",
    ),
    "README.md": (
        "AMD-2026-07-11-01 已授权开发 IBKR `stock_etf_cash`",
        "默认 inactive",
        "ibkr_activation_envelope_v1",
        "credential/session 本身永不 auto-activate",
        "Python authority 仍禁止",
        "commit/account/session-bound",
    ),
    "docs/_indexes/document_index.md": (
        "2026-07-11 IBKR Stock/ETF full live-capability development",
        "ibkr-stock-etf-full-live-capability-development.md",
        "Current W1–W11 dispatch queue",
        "credentials/session never auto-activate",
    ),
    "docs/_indexes/initiative_index.md": (
        "IBKR Stock/ETF full live-capability development",
        "AMD-2026-07-11-01 已 Accepted",
        "ibkr_activation_envelope_v1",
        "EXTERNAL_VERIFICATION_PENDING",
        "Python authority 仍禁止",
    ),
    "docs/governance_dev/SPECIFICATION_REGISTER.md": (
        "AMD-2026-07-11-01",
        "complete no-contact `stock_etf_cash`",
        "EXTERNAL_VERIFICATION_PENDING",
        "commit/account/session-bound `ibkr_activation_envelope_v1`",
        "Credentials/session never auto-activate",
    ),
}
FORBIDDEN_STABLE_CLAIMS = (
    "capability development authorizes broker contact",
    "credential/session auto-activates ibkr",
    "ibkr live automatically enabled",
    "first ibkr contact allowed=true",
    "python ibkr order authority",
    "python ibkr risk authority",
    "python ibkr activation authority",
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

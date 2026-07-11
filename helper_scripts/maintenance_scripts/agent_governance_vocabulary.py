"""Shared closed vocabularies for Development-Agent task and Context contracts.

This module deliberately has no Registry, routing, or Context imports. Both
producers can validate the same terms without circular imports or drift.
"""

KNOWN_SURFACES = frozenset({
    "acceptance", "accessibility", "agent_workflow", "ai", "alpha", "architecture",
    "auth", "authority", "broker_session", "bybit", "closure", "comments",
    "compliance", "consumption", "cron", "cross_interface", "data", "deploy",
    "docs", "evidence_methodology", "ffi", "full_audit", "functional", "governance",
    "gui", "hard_boundary", "ibkr", "implementation", "incident_rca", "index",
    "ipc", "large_file", "live", "llm", "ml", "ml_data", "model_routing",
    "multi_agent", "operations", "performance", "pg", "policy", "portfolio",
    "private_external_contact", "profit_diagnosis", "profitability", "public_web_read",
    "python", "quant", "registry", "risk", "risk_model", "routing", "runtime",
    "runtime_effect", "rust", "schema", "secret", "security", "service",
    "simplification", "spec", "stock_etf_cash", "strategy", "tws", "ux", "visual",
})

CLAIM_FLAGS = frozenset({"runtime_claim", "end_to_end_claim"})
UNCERTAINTY_LEVELS = frozenset({"low", "medium", "high", "unknown"})

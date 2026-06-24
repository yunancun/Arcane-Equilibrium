"""Proof-exclusion rules for bounded demo-probe evidence rows.

These helpers are intentionally source-only and artifact-local. They do not
query PG, call Bybit, grant authority, or mutate runtime state.
"""

from __future__ import annotations

from typing import Any


UNATTRIBUTED_STRATEGY_PREFIX = "unattributed:"

_FILL_LINEAGE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "candidate_lineage_missing",
        ("side_cell_key", "candidate_id", "candidate_key", "candidate_summary"),
    ),
    (
        "openclaw_order_linkage_missing",
        ("order_link_id", "orderLinkId", "openclaw_order_link_id"),
    ),
    (
        "exchange_order_mapping_missing",
        ("exchange_order_id", "bybit_order_id", "order_id"),
    ),
    (
        "fill_execution_mapping_missing",
        ("exec_id", "execution_id", "fill_id"),
    ),
    (
        "intent_lineage_missing",
        ("intent_id", "order_intent_id", "source_intent_id", "attempt_id"),
    ),
    (
        "risk_verdict_missing",
        (
            "risk_verdict",
            "risk_decision",
            "risk_gate_verdict",
            "risk_gate_decision",
            "source_admission_decision",
        ),
    ),
    (
        "fee_evidence_missing",
        ("fee_bps", "fee_rate", "maker_fee_bps", "taker_fee_bps", "exec_fee", "cost_bps"),
    ),
    (
        "slippage_evidence_missing",
        ("slippage_bps", "price_slippage_bps", "execution_slippage_bps"),
    ),
    (
        "close_state_missing",
        ("close_state", "position_closed", "exit_order_id", "exit_exec_id", "exit_price", "exit_ts_ms"),
    ),
    (
        "source_artifact_linkage_missing",
        ("outcome_source", "source_artifact", "source_artifact_path", "source_ledger_record_id", "boundary"),
    ),
)

_FILL_IDENTITY_KEYS = (
    "fill_id",
    "exec_id",
    "execution_id",
    "order_id",
    "exchange_order_id",
    "bybit_order_id",
    "order_link_id",
    "orderLinkId",
    "openclaw_order_link_id",
)


def _str(value: Any) -> str:
    return str(value or "").strip()


def _present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _has_any(row: dict[str, Any], keys: tuple[str, ...]) -> bool:
    return any(_present(row.get(key)) for key in keys)


def strategy_is_unattributed(row: dict[str, Any]) -> bool:
    """Return True when a row is explicitly marked as unattributed."""
    return _str(row.get("strategy_name")).lower().startswith(UNATTRIBUTED_STRATEGY_PREFIX)


def is_fill_backed_or_unattributed(row: dict[str, Any]) -> bool:
    """Return True for rows that purport to carry real fill/execution evidence."""
    if strategy_is_unattributed(row):
        return True
    if _has_any(row, _FILL_IDENTITY_KEYS):
        return True
    source = _str(row.get("outcome_source")).lower()
    return "fill" in source and "proxy" not in source


def proof_exclusion_reasons(row: dict[str, Any]) -> list[str]:
    """Return reasons a row must not count toward proof-grade outcomes.

    Markout/proxy rows are not treated as fill-backed evidence here, so legacy
    review artifacts remain readable. Real fill-backed rows and explicitly
    unattributed rows must clear the lineage checks before they can be counted.
    """
    reasons: list[str] = []
    if strategy_is_unattributed(row):
        reasons.append("unattributed_strategy_name")
    if is_fill_backed_or_unattributed(row):
        for reason, keys in _FILL_LINEAGE_GROUPS:
            if not _has_any(row, keys):
                reasons.append(reason)
    return reasons


def proof_exclusion_reason(row: dict[str, Any]) -> str | None:
    reasons = proof_exclusion_reasons(row)
    return ",".join(reasons) if reasons else None

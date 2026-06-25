"""Proof-exclusion rules for bounded demo-probe evidence rows.

These helpers are intentionally source-only and artifact-local. They do not
query PG, call Bybit, grant authority, or mutate runtime state.
"""

from __future__ import annotations

from typing import Any


UNATTRIBUTED_STRATEGY_PREFIX = "unattributed:"
ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE = "bounded_probe_active_near_touch"
ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ = 2_176_782_335
ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_MOD = 101_559_956_668_416
ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_LEN = 9

_ACTIVE_BOUNDED_PROBE_PROOF_KEY_FIELDS = (
    "side_cell_key",
    "engine_mode",
    "signal_ts_ms",
    "context_id",
    "signal_id",
    "order_link_id",
    "decision_lease_id",
    "reference_source",
)

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


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _raw_str(value: Any) -> str:
    return str(value or "")


def _stable_component(value: Any) -> bool:
    raw = _raw_str(value)
    return bool(raw) and raw.strip() == raw


def _parse_positive_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _to_base36(value: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    out = ""
    while value > 0:
        value, idx = divmod(value, 36)
        out = digits[idx] + out
    return out


def _parse_base36(value: Any) -> int | None:
    raw = _raw_str(value)
    if not raw or len(raw) > 6:
        return None
    out = 0
    for char in raw:
        if "0" <= char <= "9":
            digit = ord(char) - ord("0")
        elif "a" <= char <= "z":
            digit = 10 + ord(char) - ord("a")
        else:
            return None
        out = out * 36 + digit
    return out


def _candidate_lineage_hash_tag(
    side_cell_key: str,
    context_id: str,
    signal_id: str,
) -> str | None:
    if not all(_stable_component(value) for value in (side_cell_key, context_id, signal_id)):
        return None
    hash_value = 0xCBF2_9CE4_8422_2325
    for byte in (
        side_cell_key.encode()
        + bytes([0x1E])
        + context_id.encode()
        + bytes([0x1F])
        + signal_id.encode()
    ):
        hash_value ^= byte
        hash_value = (hash_value * 0x0000_0100_0000_01B3) & 0xFFFF_FFFF_FFFF_FFFF
    tag = _to_base36(hash_value % ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_MOD)
    return tag.rjust(ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_LEN, "0")


def _candidate_bound_active_order_link_id_is_valid(
    order_link_id: str,
    engine_mode: str,
    signal_ts_ms: int,
    side_cell_key: str,
    context_id: str,
    signal_id: str,
) -> bool:
    mode_tag = {"demo": "dm", "live_demo": "ld"}.get(engine_mode)
    expected_hash = _candidate_lineage_hash_tag(side_cell_key, context_id, signal_id)
    if mode_tag is None or expected_hash is None:
        return False
    parts = order_link_id.split("_")
    if len(parts) != 5:
        return False
    prefix, observed_mode_tag, ts_part, seq_part, hash_part = parts
    seq = _parse_base36(seq_part)
    return (
        prefix == "oc"
        and observed_mode_tag == mode_tag
        and ts_part == str(signal_ts_ms)
        and seq is not None
        and 1 <= seq <= ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ
        and seq_part == _to_base36(seq)
        and hash_part == expected_hash
    )


def _active_bounded_probe_reference_source_is_present(row: dict[str, Any]) -> bool:
    details = _dict(row.get("details"))
    return (
        _str(row.get("reference_source")) == ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE
        or _str(details.get("reference_source")) == ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE
    )


def _active_bounded_probe_proof_key(row: dict[str, Any]) -> dict[str, Any]:
    details = _dict(row.get("details"))
    return _dict(
        row.get("active_bounded_probe_proof_key")
        or details.get("active_bounded_probe_proof_key")
    )


def _active_bounded_probe_proof_key_is_valid(row: dict[str, Any]) -> bool:
    proof_key = _active_bounded_probe_proof_key(row)
    if not proof_key:
        return False
    if any(not _present(proof_key.get(key)) for key in _ACTIVE_BOUNDED_PROBE_PROOF_KEY_FIELDS):
        return False
    if _str(proof_key.get("reference_source")) != ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE:
        return False
    engine_mode = _raw_str(proof_key.get("engine_mode"))
    if engine_mode not in {"demo", "live_demo"}:
        return False
    signal_ts_ms = _parse_positive_int(proof_key.get("signal_ts_ms"))
    if signal_ts_ms is None:
        return False
    side_cell_key = _str(row.get("side_cell_key"))
    if side_cell_key and _str(proof_key.get("side_cell_key")) != side_cell_key:
        return False
    proof_side_cell_key = _raw_str(proof_key.get("side_cell_key"))
    context_id = _raw_str(proof_key.get("context_id"))
    signal_id = _raw_str(proof_key.get("signal_id"))
    decision_lease_id = _raw_str(proof_key.get("decision_lease_id"))
    proof_order_link_id = _raw_str(proof_key.get("order_link_id"))
    if not all(
        _stable_component(value)
        for value in (
            proof_side_cell_key,
            context_id,
            signal_id,
            decision_lease_id,
            proof_order_link_id,
        )
    ):
        return False
    order_link_id = _str(
        row.get("order_link_id")
        or row.get("orderLinkId")
        or row.get("openclaw_order_link_id")
    )
    if order_link_id and _str(proof_key.get("order_link_id")) != order_link_id:
        return False
    if not _candidate_bound_active_order_link_id_is_valid(
        proof_order_link_id,
        engine_mode,
        signal_ts_ms,
        proof_side_cell_key,
        context_id,
        signal_id,
    ):
        return False
    return True


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
    if _active_bounded_probe_reference_source_is_present(
        row
    ) and not _active_bounded_probe_proof_key_is_valid(row):
        reasons.append("active_bounded_probe_proof_key_missing_or_invalid")
    return reasons


def proof_exclusion_reason(row: dict[str, Any]) -> str | None:
    reasons = proof_exclusion_reasons(row)
    return ",".join(reasons) if reasons else None

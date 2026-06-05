"""AEG execution-realism 純函數核心。"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Optional

from . import (
    EMPIRICAL_EVIDENCE_SOURCE_TIERS,
    EXECUTION_REALISM_SCHEMA_VERSION,
    MAX_ADVERSE_SELECTION_BPS_P95,
    MAX_LATENCY_MS_P95,
    MAX_PARTICIPATION_RATE_P95,
    MIN_MAKER_FILL_RATE,
    MIN_SAMPLE_COUNT,
    ORDER_STYLES,
    RUNNER_VERSION,
)


def load_input(path: Path) -> dict[str, Any]:
    """讀原始 execution realism 輸入 JSON。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        f = float(value)
    else:
        s = str(value).strip()
        if not s:
            return None
        try:
            f = float(s)
        except ValueError:
            return None
    if not math.isfinite(f):
        return None
    return f


def _int_or_none(value: Any) -> Optional[int]:
    f = _float_or_none(value)
    if f is None:
        return None
    return int(f)


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _bool_pass(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in {"pass", "passed", "ok", "true", "available", "continuous"}:
        return True
    if s in {"fail", "failed", "false", "unavailable", "blocked", "missing"}:
        return False
    return None


def _normalize_source(payload: dict[str, Any]) -> str:
    source = _first_present(
        payload,
        "evidence_source_tier",
        "source_tier",
        "execution_evidence_source",
        "evidence_source",
    )
    return str(source or "missing").strip().lower()


def _normalize_order_style(payload: dict[str, Any]) -> str:
    style = _first_present(payload, "order_style", "expected_order_style", "execution_order_style")
    return str(style or "missing").strip().lower()


def _effective_fee_bps(
    *,
    order_style: str,
    maker_fee_bps: Optional[float],
    taker_fee_bps: Optional[float],
    maker_fill_rate: Optional[float],
) -> Optional[float]:
    if maker_fee_bps is None or taker_fee_bps is None:
        return None
    if order_style == "maker":
        return maker_fee_bps
    if order_style == "taker":
        return taker_fee_bps
    if order_style == "mixed":
        if maker_fill_rate is None:
            return None
        fill = min(max(maker_fill_rate, 0.0), 1.0)
        return fill * maker_fee_bps + (1.0 - fill) * taker_fee_bps
    return None


def evaluate(payload: dict[str, Any]) -> dict[str, Any]:
    """把原始輸入正規化成 robustness matrix 可讀的 execution_realism payload。

    輸入 payload 的 ``status`` 只保留在 ``input_status``，不參與信任；本函數
    用固定 gate 重算 ``status`` 與 ``reject_reasons``。
    """
    evidence_source_tier = _normalize_source(payload)
    order_style = _normalize_order_style(payload)
    maker_fee_bps = _float_or_none(_first_present(payload, "maker_fee_bps", "maker_fee_rate_bps"))
    taker_fee_bps = _float_or_none(_first_present(payload, "taker_fee_bps", "taker_fee_rate_bps"))
    slippage_bps_p95 = _float_or_none(_first_present(payload, "slippage_bps_p95", "slippage_p95_bps"))
    maker_fill_rate = _float_or_none(_first_present(payload, "maker_fill_rate", "fill_rate"))
    adverse_selection_bps_p95 = _float_or_none(
        _first_present(payload, "adverse_selection_bps_p95", "adverse_selection_p95_bps")
    )
    latency_ms_p95 = _float_or_none(_first_present(payload, "latency_ms_p95", "latency_p95_ms"))
    participation_rate_p95 = _float_or_none(
        _first_present(payload, "participation_rate_p95", "participation_p95")
    )
    sample_count = _int_or_none(_first_present(payload, "sample_count", "n_fills", "fill_sample_count"))
    capacity_notional_usdt = _float_or_none(
        _first_present(payload, "capacity_notional_usdt", "capacity_notional_usd")
    )
    order_availability = _bool_pass(
        _first_present(payload, "order_availability_status", "order_available", "order_availability")
    )

    reasons: list[str] = []
    if evidence_source_tier == "missing":
        reasons.append("missing_evidence_source_tier")
    elif evidence_source_tier not in EMPIRICAL_EVIDENCE_SOURCE_TIERS:
        reasons.append("execution_realism_not_empirical")

    if order_style not in ORDER_STYLES:
        reasons.append("invalid_or_missing_order_style")

    numeric_requirements = {
        "maker_fee_bps": maker_fee_bps,
        "taker_fee_bps": taker_fee_bps,
        "slippage_bps_p95": slippage_bps_p95,
        "latency_ms_p95": latency_ms_p95,
        "participation_rate_p95": participation_rate_p95,
        "sample_count": sample_count,
        "capacity_notional_usdt": capacity_notional_usdt,
    }
    for key, value in numeric_requirements.items():
        if value is None:
            reasons.append(f"missing_{key}")

    if maker_fee_bps is not None and maker_fee_bps < 0:
        reasons.append("negative_maker_fee_rebate_not_allowed")
    if taker_fee_bps is not None and taker_fee_bps < 0:
        reasons.append("negative_taker_fee_not_allowed")
    if (
        maker_fee_bps is not None
        and taker_fee_bps is not None
        and taker_fee_bps < maker_fee_bps
    ):
        reasons.append("taker_fee_below_maker_fee_unexpected")

    if sample_count is not None and sample_count < MIN_SAMPLE_COUNT:
        reasons.append("sample_count_below_30")
    if latency_ms_p95 is not None and latency_ms_p95 > MAX_LATENCY_MS_P95:
        reasons.append("latency_ms_p95_above_2000")
    if participation_rate_p95 is not None and participation_rate_p95 > MAX_PARTICIPATION_RATE_P95:
        reasons.append("participation_rate_p95_above_0_05")
    if capacity_notional_usdt is not None and capacity_notional_usdt <= 0:
        reasons.append("capacity_notional_missing_or_non_positive")

    needs_maker_quality = order_style in {"maker", "mixed"}
    if needs_maker_quality:
        if maker_fill_rate is None:
            reasons.append("missing_maker_fill_rate")
        elif maker_fill_rate < MIN_MAKER_FILL_RATE:
            reasons.append("maker_fill_rate_below_0_60")
        if adverse_selection_bps_p95 is None:
            reasons.append("missing_adverse_selection_bps_p95")
        elif adverse_selection_bps_p95 > MAX_ADVERSE_SELECTION_BPS_P95:
            reasons.append("adverse_selection_bps_p95_above_3_50")

    if order_availability is None:
        reasons.append("missing_order_availability_status")
    elif order_availability is False:
        reasons.append("order_availability_not_pass")

    effective_fee_bps = _effective_fee_bps(
        order_style=order_style,
        maker_fee_bps=maker_fee_bps,
        taker_fee_bps=taker_fee_bps,
        maker_fill_rate=maker_fill_rate,
    )
    cost_bps_round_trip_p95 = None
    if effective_fee_bps is not None and slippage_bps_p95 is not None:
        adverse_drag = adverse_selection_bps_p95 if needs_maker_quality else 0.0
        if adverse_drag is not None:
            cost_bps_round_trip_p95 = 2.0 * (effective_fee_bps + slippage_bps_p95) + adverse_drag

    status = "PASS" if not reasons else "FAIL"
    mode = (
        f"calibrated_{evidence_source_tier}_{order_style}"
        if status == "PASS"
        else f"unverified_{evidence_source_tier}_{order_style}"
    )
    thresholds = {
        "min_sample_count": MIN_SAMPLE_COUNT,
        "min_maker_fill_rate": MIN_MAKER_FILL_RATE,
        "max_latency_ms_p95": MAX_LATENCY_MS_P95,
        "max_participation_rate_p95": MAX_PARTICIPATION_RATE_P95,
        "max_adverse_selection_bps_p95": MAX_ADVERSE_SELECTION_BPS_P95,
        "empirical_evidence_source_tiers": sorted(EMPIRICAL_EVIDENCE_SOURCE_TIERS),
    }
    return {
        "schema_version": EXECUTION_REALISM_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "candidate_id": payload.get("candidate_id"),
        "strategy_family": payload.get("strategy_family"),
        "parameter_cell_id": payload.get("parameter_cell_id"),
        "input_status": payload.get("status"),
        "status": status,
        "reject_reason": reasons[0] if reasons else None,
        "reject_reasons": list(dict.fromkeys(reasons)),
        "execution_realism_mode": mode,
        "evidence_source_tier": evidence_source_tier,
        "order_style": order_style,
        "maker_fee_bps": maker_fee_bps,
        "taker_fee_bps": taker_fee_bps,
        "effective_fee_bps_per_side": effective_fee_bps,
        "slippage_bps_p95": slippage_bps_p95,
        "maker_fill_rate": maker_fill_rate,
        "adverse_selection_bps_p95": adverse_selection_bps_p95,
        "latency_ms_p95": latency_ms_p95,
        "participation_rate_p95": participation_rate_p95,
        "sample_count": sample_count,
        "capacity_notional_usdt": capacity_notional_usdt,
        "order_availability_status": "PASS" if order_availability is True else (
            "FAIL" if order_availability is False else "MISSING"
        ),
        "cost_bps_round_trip_p95": cost_bps_round_trip_p95,
        "thresholds": thresholds,
        "notes": payload.get("notes"),
    }

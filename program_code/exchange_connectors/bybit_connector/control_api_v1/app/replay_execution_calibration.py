"""Replay execution calibration helpers for REF-21 full-chain replay.

This module reads recent real demo/live_demo fill attribution as an as-of
calibration source for replay-only execution assumptions. It never writes to
engine settings and never mutates live/demo runtime config; callers receive a
copied risk override blob suitable only for replay manifests.
"""

from __future__ import annotations

import copy
import logging
import math
from typing import Any, Callable


logger = logging.getLogger(__name__)

CALIBRATION_ENGINE_MODES = ("demo", "live_demo")
CALIBRATION_LOOKBACK_DAYS = 30
CALIBRATION_STATEMENT_TIMEOUT_MS = 3_000
MIN_LIMITED_SLIPPAGE_SAMPLES = 30
MIN_CALIBRATED_SLIPPAGE_SAMPLES = 200
FALLBACK_TAKER_SLIPPAGE_BPS = 50.0
MIN_TAKER_SLIPPAGE_BPS = 5.0
MAX_TAKER_SLIPPAGE_BPS = 100.0

DEFAULT_SLIPPAGE_TIERS = (
    {"min_turnover_usd": 1_000_000_000.0, "rate": 0.0001},
    {"min_turnover_usd": 100_000_000.0, "rate": 0.0002},
    {"min_turnover_usd": 10_000_000.0, "rate": 0.0005},
    {"min_turnover_usd": 1_000_000.0, "rate": 0.0015},
    {"min_turnover_usd": 0.0, "rate": 0.0030},
)


def fetch_execution_calibration_sync(
    *,
    get_pg_conn_fn: Callable[[], Any],
    symbols: list[str],
    strategies: list[str],
    asof_ms: int,
) -> dict[str, Any]:
    """Fetch as-of execution calibration from `trading.fills`.

    Fail-soft by design: replay remains usable when PG or attribution columns
    are unavailable, but the returned summary drives conservative S2 bounds.
    """
    base = _base_summary(asof_ms=asof_ms)
    clean_symbols = _clean_unique(symbols)
    clean_strategies = _clean_unique(strategies)
    if not clean_symbols or not clean_strategies:
        return {**base, "status": "unavailable", "reason": "empty_scope"}

    try:
        conn_ctx = get_pg_conn_fn()
        if conn_ctx is None:
            return {**base, "status": "unavailable", "reason": "pg_unavailable"}
        with conn_ctx as conn:
            if conn is None:
                return {**base, "status": "unavailable", "reason": "pg_unavailable"}
            with conn.cursor() as cur:
                cur.execute(
                    "SET LOCAL statement_timeout = %s;",
                    (CALIBRATION_STATEMENT_TIMEOUT_MS,),
                )
                cur.execute("SELECT to_regclass('trading.fills') IS NOT NULL;")
                exists_row = cur.fetchone()
                if not exists_row or not bool(exists_row[0]):
                    return {
                        **base,
                        "status": "unavailable",
                        "reason": "trading_fills_missing",
                    }

                cur.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'trading'
                      AND table_name = 'fills';
                    """
                )
                columns = {str(row[0]) for row in cur.fetchall()}
                required = {"ts", "strategy_name", "symbol", "engine_mode"}
                missing = sorted(required - columns)
                if missing:
                    return {
                        **base,
                        "status": "unavailable",
                        "reason": "trading_fills_missing_columns:" + ",".join(missing),
                    }

                role_expr = (
                    "liquidity_role"
                    if "liquidity_role" in columns
                    else "NULL::text AS liquidity_role"
                )
                slip_expr = (
                    "slippage_bps"
                    if "slippage_bps" in columns
                    else "NULL::double precision AS slippage_bps"
                )
                fee_expr = (
                    "fee_rate"
                    if "fee_rate" in columns
                    else "NULL::double precision AS fee_rate"
                )
                reject_filter = (
                    "AND NOT (symbol = 'BUSDT' AND reject_code = '110017')"
                    if "reject_code" in columns
                    else ""
                )
                cur.execute(
                    f"""
                    SELECT strategy_name, symbol, ts,
                           {role_expr}, {slip_expr}, {fee_expr}
                    FROM trading.fills
                    WHERE strategy_name = ANY(%s)
                      AND symbol = ANY(%s)
                      AND engine_mode = ANY(%s)
                      AND ts >= to_timestamp(%s / 1000.0)
                      AND ts < to_timestamp(%s / 1000.0)
                      {reject_filter}
                    ORDER BY ts ASC;
                    """,
                    (
                        clean_strategies,
                        clean_symbols,
                        list(CALIBRATION_ENGINE_MODES),
                        asof_ms - CALIBRATION_LOOKBACK_DAYS * 86_400_000,
                        asof_ms,
                    ),
                )
                rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 - advisory calibration only
        logger.warning("replay execution calibration unavailable: %s", exc)
        return {
            **base,
            "status": "unavailable",
            "reason": type(exc).__name__,
        }

    records = [
        {
            "strategy": row[0],
            "symbol": row[1],
            "ts": row[2],
            "liquidity_role": row[3],
            "slippage_bps": row[4],
            "fee_rate": row[5],
        }
        for row in rows
    ]
    return build_execution_calibration_summary(
        records,
        asof_ms=asof_ms,
        source="trading.fills",
    )


def build_execution_calibration_summary(
    records: list[dict[str, Any]],
    *,
    asof_ms: int,
    source: str,
) -> dict[str, Any]:
    """Build execution calibration summary from fill records."""
    summary = _base_summary(asof_ms=asof_ms)
    roles = [str(item.get("liquidity_role") or "unknown").lower() for item in records]
    sample_count = len(records)
    maker_count = sum(1 for role in roles if role == "maker")
    taker_count = sum(1 for role in roles if role == "taker")
    unknown_count = sample_count - maker_count - taker_count

    slippage = [
        max(0.0, value)
        for value in (_finite_float(item.get("slippage_bps")) for item in records)
        if value is not None
    ]
    fee_bps = [
        value * 10_000.0
        for value in (_finite_float(item.get("fee_rate")) for item in records)
        if value is not None
    ]

    q10 = _percentile(slippage, 0.10)
    q50 = _percentile(slippage, 0.50)
    q90 = _percentile(slippage, 0.90)
    fee_q50 = _percentile(fee_bps, 0.50)
    latest_ts_ms = max((_to_epoch_ms(item.get("ts")) or 0 for item in records), default=0)
    latest_age_days = (
        max(0.0, (asof_ms - latest_ts_ms) / 86_400_000.0)
        if latest_ts_ms > 0
        else None
    )

    slippage_n = len(slippage)
    if (
        slippage_n >= MIN_CALIBRATED_SLIPPAGE_SAMPLES
        and (latest_age_days or 999.0) <= 7.0
    ):
        status = "calibrated"
        confidence = "S1_CALIBRATED"
        recommended, recommended_clamped = _bounded_taker_slippage_bps(q90 or 0.0)
        reason = None
    elif (
        slippage_n >= MIN_LIMITED_SLIPPAGE_SAMPLES
        and (latest_age_days or 999.0) <= 30.0
    ):
        status = "limited"
        confidence = "S1_LIMITED"
        recommended, recommended_clamped = _bounded_taker_slippage_bps(q90 or 0.0)
        reason = None
    else:
        status = "insufficient_samples"
        confidence = "S2_CONSERVATIVE_BOUND"
        recommended = FALLBACK_TAKER_SLIPPAGE_BPS
        recommended_clamped = False
        reason = f"slippage_samples:{slippage_n}<required:{MIN_LIMITED_SLIPPAGE_SAMPLES}"

    return {
        **summary,
        "status": status,
        "reason": reason,
        "source": source,
        "sample_count": sample_count,
        "slippage_sample_count": slippage_n,
        "latest_fill_age_days": latest_age_days,
        "maker_role_share": (maker_count / sample_count) if sample_count else 0.0,
        "taker_role_share": (taker_count / sample_count) if sample_count else 0.0,
        "unknown_role_share": (unknown_count / sample_count) if sample_count else 0.0,
        "adverse_slippage_bps": {"q10": q10, "q50": q50, "q90": q90},
        "fee_rate_bps": {"q50": fee_q50},
        "recommended_taker_slippage_bps": recommended,
        "recommended_taker_slippage_clamped": recommended_clamped,
        "execution_confidence": confidence,
        "maker_fill_probability_status": "unavailable_without_order_outcomes",
    }


def apply_execution_calibration_to_risk_overrides(
    risk_overrides: dict[str, Any] | None,
    execution_calibration: dict[str, Any],
) -> dict[str, Any]:
    """Return replay-only risk overrides with calibrated slippage floor applied."""
    calibrated = copy.deepcopy(risk_overrides) if isinstance(risk_overrides, dict) else {}
    floor_bps = _finite_float(execution_calibration.get("recommended_taker_slippage_bps"))
    if floor_bps is None or floor_bps <= 0.0:
        floor_bps = FALLBACK_TAKER_SLIPPAGE_BPS
    floor_bps = min(max(floor_bps, MIN_TAKER_SLIPPAGE_BPS), MAX_TAKER_SLIPPAGE_BPS)
    floor_rate = floor_bps / 10_000.0

    slippage = calibrated.get("slippage")
    if not isinstance(slippage, dict):
        slippage = {}
    default_rate = _finite_float(slippage.get("default_rate")) or 0.0
    slippage["default_rate"] = max(default_rate, floor_rate)

    raw_tiers = slippage.get("tiers")
    tiers = raw_tiers if isinstance(raw_tiers, list) and raw_tiers else list(DEFAULT_SLIPPAGE_TIERS)
    floored_tiers: list[dict[str, float]] = []
    for item in tiers:
        if not isinstance(item, dict):
            continue
        min_turnover = _finite_float(item.get("min_turnover_usd"))
        rate = _finite_float(item.get("rate"))
        if min_turnover is None or rate is None:
            continue
        floored_tiers.append({
            "min_turnover_usd": min_turnover,
            "rate": max(rate, floor_rate),
        })
    slippage["tiers"] = floored_tiers or [
        {
            "min_turnover_usd": item["min_turnover_usd"],
            "rate": max(item["rate"], floor_rate),
        }
        for item in DEFAULT_SLIPPAGE_TIERS
    ]
    calibrated["slippage"] = slippage

    overlay = dict(execution_calibration.get("risk_overlay") or {})
    overlay.update({
        "applied": True,
        "slippage_floor_bps": floor_bps,
        "scope": "replay_only_risk_overrides",
    })
    execution_calibration["risk_overlay"] = overlay
    return calibrated


def _base_summary(*, asof_ms: int) -> dict[str, Any]:
    return {
        "status": "unavailable",
        "source": "trading.fills",
        "engine_modes": list(CALIBRATION_ENGINE_MODES),
        "lookback_days": CALIBRATION_LOOKBACK_DAYS,
        "asof_ms": int(asof_ms),
        "sample_count": 0,
        "slippage_sample_count": 0,
        "recommended_taker_slippage_bps": FALLBACK_TAKER_SLIPPAGE_BPS,
        "recommended_taker_slippage_clamped": False,
        "execution_confidence": "S2_CONSERVATIVE_BOUND",
        "risk_overlay": {"applied": False},
    }


def _clean_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(ordered[int(pos)])
    weight = pos - lo
    return float(ordered[lo] * (1.0 - weight) + ordered[hi] * weight)


def _bounded_taker_slippage_bps(value: float) -> tuple[float, bool]:
    bounded = min(max(value, MIN_TAKER_SLIPPAGE_BPS), MAX_TAKER_SLIPPAGE_BPS)
    return bounded, bounded != value


def _to_epoch_ms(value: Any) -> int | None:
    if value is None:
        return None
    if hasattr(value, "timestamp"):
        return int(value.timestamp() * 1000)
    parsed = _finite_float(value)
    if parsed is None:
        return None
    return int(parsed)

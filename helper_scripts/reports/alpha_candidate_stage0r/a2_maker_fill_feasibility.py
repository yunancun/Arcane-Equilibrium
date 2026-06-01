#!/usr/bin/env python3
"""A2 liquidation cascade maker-fill feasibility diagnostic.

MODULE_NOTE
This script answers one narrow QC question for A2 liquidation_cascade_fade:
after a qualifying liquidation-cascade trigger, would a passive PostOnly entry
price plausibly be touched within 60 seconds by observed BBO snapshots?

Hard boundaries:
  - Read-only SELECT from market.liquidations and market.market_tickers.
  - No order placement, no fill insertion, no TOML mutation, no IPC/lease call.
  - Output is diagnostic only: reject / draft_only / observe_more.
  - BBO touch is a conservative proxy. It does not model queue priority.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

# 共享統計公式（E5 finding #3 整併）。本檔原有同邏輯的 local ``_safe_float``，
# 改 re-export canonical。三段 fallback 理由同 8b/8c：既被 ``python -m`` 從 repo
# root 跑，也被 smoke 以「script 目錄在 sys.path」直跑模式匯入。
try:
    from helper_scripts.lib import stats_common as _sc
except ImportError:  # 直跑（非 -m）：補 repo root 後重試
    _REPO_ROOT = Path(__file__).resolve().parents[3]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from helper_scripts.lib import stats_common as _sc


A2_ALPHA_SOURCE_ID = "liquidation_cascade_fade"
RUNNER_VERSION = "a2_maker_fill_feasibility.v1"
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
DEFAULT_PER_SYMBOL_THRESHOLD = {
    "BTCUSDT": 500_000.0,
    "ETHUSDT": 300_000.0,
}
DEFAULT_OFFSET_BPS_LIST = (0.0, 1.0, 2.0, 5.0)


@dataclass(frozen=True)
class A2MakerFillConfig:
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    per_symbol_threshold: Mapping[str, float] = field(
        default_factory=lambda: dict(DEFAULT_PER_SYMBOL_THRESHOLD)
    )
    min_events: int = 3
    dominance_share: float = 0.60
    timeout_sec: int = 60
    entry_bbo_grace_sec: int = 10
    spread_guard_bps: float = 50.0
    offset_bps_list: tuple[float, ...] = DEFAULT_OFFSET_BPS_LIST
    primary_offset_bps: float = 1.0
    min_attempts: int = 30
    min_fill_rate: float = 0.50


@dataclass(frozen=True)
class CascadeTriggerEvent:
    trigger_id: str
    symbol: str
    bucket_start_ts: Any
    bucket_end_ts: Any
    dominant_side: str
    event_count_5m: int
    dominant_event_count: int
    cluster_notional_5m: float
    long_liq_notional: float
    short_liq_notional: float
    entry_bbo_ts: Any = None
    entry_best_bid: float | None = None
    entry_best_ask: float | None = None
    entry_spread_bps: float | None = None


@dataclass(frozen=True)
class BboSnapshot:
    ts: Any
    best_bid: float
    best_ask: float
    spread_bps: float | None = None


def build_maker_fill_query(
    *,
    cfg: A2MakerFillConfig,
    lookback_days: int,
) -> tuple[str, dict[str, Any]]:
    """Build the read-only liquidation trigger + BBO window query."""
    _validate_config(cfg)
    if lookback_days <= 0:
        raise ValueError("lookback_days must be positive")
    thresholds = _threshold_params(cfg)
    sql = """
WITH buckets AS (
    SELECT
        l.symbol,
        to_timestamp(floor(extract(epoch FROM l.ts) / 300) * 300) AS bucket_start_ts,
        max(l.ts) AS bucket_end_ts,
        count(*)::int AS event_count_5m,
        count(*) FILTER (WHERE l.side = 'Buy')::int AS long_liq_count,
        count(*) FILTER (WHERE l.side = 'Sell')::int AS short_liq_count,
        sum(abs(l.qty * l.price))::double precision AS cluster_notional_5m,
        sum(CASE WHEN l.side = 'Buy' THEN abs(l.qty * l.price) ELSE 0 END)::double precision
            AS long_liq_notional,
        sum(CASE WHEN l.side = 'Sell' THEN abs(l.qty * l.price) ELSE 0 END)::double precision
            AS short_liq_notional
    FROM market.liquidations l
    WHERE l.symbol = ANY(%(symbols)s::text[])
      AND l.ts >= now() - %(lookback)s::interval
      AND l.side IN ('Buy', 'Sell')
      AND l.qty IS NOT NULL
      AND l.price IS NOT NULL
      AND l.qty > 0
      AND l.price > 0
    GROUP BY l.symbol, to_timestamp(floor(extract(epoch FROM l.ts) / 300) * 300)
),
triggers AS (
    SELECT
        b.*,
        CASE
            WHEN b.cluster_notional_5m > 0
             AND b.long_liq_notional >= b.cluster_notional_5m * %(dominance_share)s
             AND b.long_liq_notional >= b.short_liq_notional
                THEN 'long_liquidated'
            WHEN b.cluster_notional_5m > 0
             AND b.short_liq_notional >= b.cluster_notional_5m * %(dominance_share)s
             AND b.short_liq_notional > b.long_liq_notional
                THEN 'short_liquidated'
            ELSE 'mixed'
        END AS dominant_side,
        CASE
            WHEN b.long_liq_notional >= b.short_liq_notional THEN b.long_liq_count
            ELSE b.short_liq_count
        END AS dominant_event_count
    FROM buckets b
    WHERE b.event_count_5m >= %(min_events)s
),
eligible AS (
    SELECT *
    FROM triggers t
    WHERE t.dominant_side IN ('long_liquidated', 'short_liquidated')
      AND t.cluster_notional_5m >= CASE
          WHEN t.symbol = 'BTCUSDT' THEN %(threshold_btcusdt)s
          WHEN t.symbol = 'ETHUSDT' THEN %(threshold_ethusdt)s
          ELSE %(threshold_other)s
      END
),
entry_bbo AS (
    SELECT
        e.*,
        eb.ts AS entry_bbo_ts,
        eb.best_bid AS entry_best_bid,
        eb.best_ask AS entry_best_ask,
        eb.spread_bps AS entry_spread_bps
    FROM eligible e
    LEFT JOIN LATERAL (
        SELECT mt.ts, mt.best_bid, mt.best_ask, mt.spread_bps
        FROM market.market_tickers mt
        WHERE mt.symbol = e.symbol
          AND mt.ts >= e.bucket_end_ts
          AND mt.ts <= e.bucket_end_ts + (%(entry_bbo_grace_sec)s::int * interval '1 second')
          AND mt.best_bid IS NOT NULL
          AND mt.best_ask IS NOT NULL
          AND mt.best_bid > 0
          AND mt.best_ask > 0
        ORDER BY mt.ts ASC
        LIMIT 1
    ) eb ON TRUE
)
SELECT
    e.symbol || '|' || extract(epoch FROM e.bucket_start_ts)::bigint || '|'
        || e.dominant_side AS trigger_id,
    e.symbol,
    e.bucket_start_ts,
    e.bucket_end_ts,
    e.event_count_5m,
    e.long_liq_count,
    e.short_liq_count,
    e.dominant_event_count,
    e.cluster_notional_5m,
    e.long_liq_notional,
    e.short_liq_notional,
    e.dominant_side,
    e.entry_bbo_ts,
    e.entry_best_bid,
    e.entry_best_ask,
    e.entry_spread_bps,
    tw.ts AS tick_ts,
    tw.best_bid AS tick_best_bid,
    tw.best_ask AS tick_best_ask,
    tw.spread_bps AS tick_spread_bps
FROM entry_bbo e
LEFT JOIN LATERAL (
    SELECT mt.ts, mt.best_bid, mt.best_ask, mt.spread_bps
    FROM market.market_tickers mt
    WHERE mt.symbol = e.symbol
      AND mt.ts >= e.bucket_end_ts
      AND mt.ts <= e.bucket_end_ts + (%(timeout_sec)s::int * interval '1 second')
      AND mt.best_bid IS NOT NULL
      AND mt.best_ask IS NOT NULL
      AND mt.best_bid > 0
      AND mt.best_ask > 0
    ORDER BY mt.ts ASC
) tw ON TRUE
ORDER BY e.bucket_end_ts ASC, e.symbol ASC, tw.ts ASC
"""
    params: dict[str, Any] = {
        "symbols": list(cfg.symbols),
        "lookback": f"{lookback_days} days",
        "min_events": int(cfg.min_events),
        "dominance_share": float(cfg.dominance_share),
        "entry_bbo_grace_sec": int(cfg.entry_bbo_grace_sec),
        "timeout_sec": int(cfg.timeout_sec),
        **thresholds,
    }
    return sql, params


def fetch_maker_fill_query_rows(
    conn: Any,
    *,
    cfg: A2MakerFillConfig,
    lookback_days: int,
) -> list[dict[str, Any]]:
    sql, params = build_maker_fill_query(cfg=cfg, lookback_days=lookback_days)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        if not rows:
            return []
        if isinstance(rows[0], Mapping):
            return [dict(row) for row in rows]
        columns = [desc[0] for desc in cur.description]
        return [dict(zip(columns, row)) for row in rows]


def query_rows_to_events(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[list[CascadeTriggerEvent], dict[str, list[BboSnapshot]]]:
    events_by_id: dict[str, CascadeTriggerEvent] = {}
    snapshots: dict[str, list[BboSnapshot]] = {}
    for row in rows:
        trigger_id = str(row.get("trigger_id") or "")
        if not trigger_id:
            continue
        if trigger_id not in events_by_id:
            events_by_id[trigger_id] = CascadeTriggerEvent(
                trigger_id=trigger_id,
                symbol=str(row.get("symbol") or ""),
                bucket_start_ts=row.get("bucket_start_ts"),
                bucket_end_ts=row.get("bucket_end_ts"),
                dominant_side=str(row.get("dominant_side") or ""),
                event_count_5m=int(_safe_float(row.get("event_count_5m")) or 0),
                dominant_event_count=int(_safe_float(row.get("dominant_event_count")) or 0),
                cluster_notional_5m=float(_safe_float(row.get("cluster_notional_5m")) or 0.0),
                long_liq_notional=float(_safe_float(row.get("long_liq_notional")) or 0.0),
                short_liq_notional=float(_safe_float(row.get("short_liq_notional")) or 0.0),
                entry_bbo_ts=row.get("entry_bbo_ts"),
                entry_best_bid=_safe_float(row.get("entry_best_bid")),
                entry_best_ask=_safe_float(row.get("entry_best_ask")),
                entry_spread_bps=_safe_float(row.get("entry_spread_bps")),
            )
        tick_ts = row.get("tick_ts")
        tick_bid = _safe_float(row.get("tick_best_bid"))
        tick_ask = _safe_float(row.get("tick_best_ask"))
        if tick_ts is not None and tick_bid is not None and tick_ask is not None:
            snapshots.setdefault(trigger_id, []).append(
                BboSnapshot(
                    ts=tick_ts,
                    best_bid=tick_bid,
                    best_ask=tick_ask,
                    spread_bps=_safe_float(row.get("tick_spread_bps")),
                )
            )
    events = sorted(events_by_id.values(), key=lambda item: (_ts_sort_key(item.bucket_end_ts), item.symbol))
    for trigger_id, items in snapshots.items():
        snapshots[trigger_id] = sorted(items, key=lambda item: _ts_sort_key(item.ts))
    return events, snapshots


def analyze_maker_fill_feasibility(
    events: Sequence[CascadeTriggerEvent | Mapping[str, Any]],
    snapshots_by_trigger_id: Mapping[str, Sequence[BboSnapshot | Mapping[str, Any]]],
    *,
    cfg: A2MakerFillConfig | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    config = cfg or A2MakerFillConfig()
    _validate_config(config)
    normalized_events = _normalize_events(events)
    normalized_snapshots = _normalize_snapshot_map(snapshots_by_trigger_id)
    generated = generated_at or datetime.now(timezone.utc)

    by_offset: list[dict[str, Any]] = []
    by_offset_index: dict[float, dict[str, Any]] = {}
    event_examples: list[dict[str, Any]] = []
    for offset_bps in config.offset_bps_list:
        attempts = [
            _simulate_event_offset(event, normalized_snapshots.get(event.trigger_id, []), offset_bps, config)
            for event in normalized_events
        ]
        summary = _summarize_attempts(attempts, offset_bps=offset_bps)
        by_offset.append(summary)
        by_offset_index[_offset_key(offset_bps)] = summary
        if len(event_examples) < 12:
            event_examples.extend(_attempt_examples(attempts, limit=12 - len(event_examples)))

    primary_key = _offset_key(config.primary_offset_bps)
    primary = by_offset_index.get(primary_key)
    if primary is None and by_offset:
        primary = by_offset[0]
    verdict, ready, reasons, basis, recommendation = _verdict(primary, config)

    packet = {
        "runner_version": RUNNER_VERSION,
        "alpha_source_id": A2_ALPHA_SOURCE_ID,
        "diagnostic": "maker_fill_feasibility",
        "generated_at_utc": generated.isoformat(),
        "lane": "execution_feasibility_diagnostic",
        "verdict": verdict,
        "precheck_ready_for_qc_reassessment": ready,
        "eligible_for_demo_canary": False,
        "promotion_recommendation": recommendation,
        "verdict_basis": basis,
        "fail_reasons": reasons,
        "governance_attest": {
            "read_only": True,
            "source_tables": ["market.liquidations", "market.market_tickers"],
            "no_order_or_fill": True,
            "no_toml_mutation": True,
            "no_ipc_or_lease_call": True,
            "no_auto_promote": True,
        },
        "config": _config_summary(config),
        "data_window": _data_window(normalized_events),
        "primary_offset_bps": primary.get("offset_bps") if primary else config.primary_offset_bps,
        "primary_summary": primary,
        "by_offset": by_offset,
        "by_symbol_side": _summarize_by_symbol_side(normalized_events, normalized_snapshots, config),
        "event_examples": event_examples,
        "limitations": [
            "BBO touch does not prove queue fill priority.",
            "Ticker snapshots can miss intra-snapshot trade-through.",
            "This diagnostic does not retest A2 alpha edge or exit model.",
        ],
    }
    return _clean_json(packet)


def _simulate_event_offset(
    event: CascadeTriggerEvent,
    snapshots: Sequence[BboSnapshot],
    offset_bps: float,
    cfg: A2MakerFillConfig,
) -> dict[str, Any]:
    entry_bid = event.entry_best_bid
    entry_ask = event.entry_best_ask
    if entry_bid is None or entry_ask is None or entry_bid <= 0.0 or entry_ask <= 0.0:
        return _attempt_packet(event, offset_bps, "missing_entry_bbo")
    if entry_bid >= entry_ask:
        return _attempt_packet(event, offset_bps, "crossed_entry_bbo")

    entry_spread = event.entry_spread_bps
    if entry_spread is None:
        entry_spread = _spread_bps(entry_bid, entry_ask)
    if entry_spread is None:
        return _attempt_packet(event, offset_bps, "invalid_entry_spread")
    if entry_spread > cfg.spread_guard_bps:
        return _attempt_packet(
            event,
            offset_bps,
            "spread_guard",
            entry_spread_bps=entry_spread,
        )

    side = _entry_side(event.dominant_side)
    if side is None:
        return _attempt_packet(event, offset_bps, "unsupported_dominant_side")

    if side == "buy":
        limit_price = entry_bid * (1.0 - offset_bps / 10_000.0)
        postonly_reject = limit_price >= entry_ask
    else:
        limit_price = entry_ask * (1.0 + offset_bps / 10_000.0)
        postonly_reject = limit_price <= entry_bid
    if postonly_reject:
        return _attempt_packet(
            event,
            offset_bps,
            "postonly_reject",
            entry_side=side,
            limit_price=limit_price,
            entry_spread_bps=entry_spread,
        )

    fill_snapshot = None
    for snapshot in snapshots:
        if snapshot.best_bid <= 0.0 or snapshot.best_ask <= 0.0 or snapshot.best_bid >= snapshot.best_ask:
            continue
        if side == "buy" and snapshot.best_ask <= limit_price:
            fill_snapshot = snapshot
            break
        if side == "sell" and snapshot.best_bid >= limit_price:
            fill_snapshot = snapshot
            break

    if fill_snapshot is None:
        return _attempt_packet(
            event,
            offset_bps,
            "no_touch",
            eligible=True,
            entry_side=side,
            limit_price=limit_price,
            entry_spread_bps=entry_spread,
            n_bbo_snapshots=len(snapshots),
        )

    return _attempt_packet(
        event,
        offset_bps,
        "filled",
        eligible=True,
        filled=True,
        entry_side=side,
        limit_price=limit_price,
        fill_ts=fill_snapshot.ts,
        seconds_to_fill=_seconds_between(event.bucket_end_ts, fill_snapshot.ts),
        entry_spread_bps=entry_spread,
        n_bbo_snapshots=len(snapshots),
    )


def _attempt_packet(
    event: CascadeTriggerEvent,
    offset_bps: float,
    reason: str,
    *,
    eligible: bool = False,
    filled: bool = False,
    entry_side: str | None = None,
    limit_price: float | None = None,
    fill_ts: Any = None,
    seconds_to_fill: float | None = None,
    entry_spread_bps: float | None = None,
    n_bbo_snapshots: int = 0,
) -> dict[str, Any]:
    return {
        "trigger_id": event.trigger_id,
        "symbol": event.symbol,
        "bucket_end_ts": _iso_ts(event.bucket_end_ts),
        "dominant_side": event.dominant_side,
        "entry_side": entry_side,
        "offset_bps": offset_bps,
        "eligible": eligible,
        "filled": filled,
        "reason": reason,
        "limit_price": limit_price,
        "fill_ts": _iso_ts(fill_ts),
        "seconds_to_fill": seconds_to_fill,
        "entry_spread_bps": entry_spread_bps,
        "n_bbo_snapshots": n_bbo_snapshots,
        "cluster_notional_5m": event.cluster_notional_5m,
        "event_count_5m": event.event_count_5m,
    }


def _summarize_attempts(attempts: Sequence[Mapping[str, Any]], *, offset_bps: float) -> dict[str, Any]:
    total = len(attempts)
    eligible = [item for item in attempts if item.get("eligible") is True]
    fills = [item for item in eligible if item.get("filled") is True]
    skipped = [item for item in attempts if item.get("eligible") is not True]
    fill_rate = len(fills) / len(eligible) if eligible else None
    ci_low, ci_high = _wilson_interval(len(fills), len(eligible))
    seconds = [
        float(item["seconds_to_fill"])
        for item in fills
        if item.get("seconds_to_fill") is not None
    ]
    return {
        "offset_bps": offset_bps,
        "total_triggers": total,
        "eligible_attempts": len(eligible),
        "eligible_attempt_rate": len(eligible) / total if total else None,
        "simulated_fills": len(fills),
        "maker_touch_fill_rate": fill_rate,
        "wilson_95_low": ci_low,
        "wilson_95_high": ci_high,
        "skip_counts": _count_by_reason(skipped),
        "no_touch_count": sum(1 for item in eligible if item.get("reason") == "no_touch"),
        "avg_seconds_to_fill": sum(seconds) / len(seconds) if seconds else None,
        "median_seconds_to_fill": _median(seconds),
        "denominator_note": "eligible_attempts exclude missing/crossed/spread-guard BBO rows",
    }


def _summarize_by_symbol_side(
    events: Sequence[CascadeTriggerEvent],
    snapshots_by_trigger_id: Mapping[str, Sequence[BboSnapshot]],
    cfg: A2MakerFillConfig,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for offset_bps in cfg.offset_bps_list:
        attempts = [
            _simulate_event_offset(event, snapshots_by_trigger_id.get(event.trigger_id, []), offset_bps, cfg)
            for event in events
        ]
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for attempt in attempts:
            key = (str(attempt.get("symbol") or ""), str(attempt.get("dominant_side") or ""))
            groups.setdefault(key, []).append(attempt)
        for (symbol, dominant_side), group in sorted(groups.items()):
            summary = _summarize_attempts(group, offset_bps=offset_bps)
            summary["symbol"] = symbol
            summary["dominant_side"] = dominant_side
            rows.append(summary)
    return rows


def _verdict(
    primary: Mapping[str, Any] | None,
    cfg: A2MakerFillConfig,
) -> tuple[str, bool, list[str], str, str]:
    if not primary:
        return (
            "observe_more",
            False,
            ["no_qualifying_triggers"],
            "no qualifying A2 cascade triggers found in the selected window",
            "do_not_demo",
        )
    eligible = int(primary.get("eligible_attempts") or 0)
    fill_rate = primary.get("maker_touch_fill_rate")
    if eligible < cfg.min_attempts:
        return (
            "observe_more",
            False,
            [f"eligible_attempts {eligible} < min_attempts {cfg.min_attempts}"],
            "insufficient maker-fill sample for execution feasibility decision",
            "do_not_demo",
        )
    if fill_rate is None or float(fill_rate) < cfg.min_fill_rate:
        return (
            "reject",
            False,
            [f"maker_touch_fill_rate {fill_rate} < min_fill_rate {cfg.min_fill_rate}"],
            "A2 PostOnly entry layer fails the 60s BBO-touch feasibility gate",
            "do_not_demo",
        )
    return (
        "draft_only",
        True,
        ["maker_touch_fill_rate_meets_feasibility_gate"],
        "execution touch feasibility passed; A2 still requires edge and exit-model reassessment",
        "qc_reassess_only_no_demo_activation",
    )


def _normalize_events(events: Sequence[CascadeTriggerEvent | Mapping[str, Any]]) -> list[CascadeTriggerEvent]:
    out: list[CascadeTriggerEvent] = []
    for row in events:
        if isinstance(row, CascadeTriggerEvent):
            event = row
        else:
            event = CascadeTriggerEvent(
                trigger_id=str(row.get("trigger_id") or ""),
                symbol=str(row.get("symbol") or ""),
                bucket_start_ts=row.get("bucket_start_ts"),
                bucket_end_ts=row.get("bucket_end_ts"),
                dominant_side=str(row.get("dominant_side") or ""),
                event_count_5m=int(_safe_float(row.get("event_count_5m")) or 0),
                dominant_event_count=int(_safe_float(row.get("dominant_event_count")) or 0),
                cluster_notional_5m=float(_safe_float(row.get("cluster_notional_5m")) or 0.0),
                long_liq_notional=float(_safe_float(row.get("long_liq_notional")) or 0.0),
                short_liq_notional=float(_safe_float(row.get("short_liq_notional")) or 0.0),
                entry_bbo_ts=row.get("entry_bbo_ts"),
                entry_best_bid=_safe_float(row.get("entry_best_bid")),
                entry_best_ask=_safe_float(row.get("entry_best_ask")),
                entry_spread_bps=_safe_float(row.get("entry_spread_bps")),
            )
        if event.trigger_id and event.symbol:
            out.append(event)
    return sorted(out, key=lambda item: (_ts_sort_key(item.bucket_end_ts), item.symbol))


def _normalize_snapshot_map(
    snapshots_by_trigger_id: Mapping[str, Sequence[BboSnapshot | Mapping[str, Any]]],
) -> dict[str, list[BboSnapshot]]:
    out: dict[str, list[BboSnapshot]] = {}
    for trigger_id, rows in snapshots_by_trigger_id.items():
        snapshots: list[BboSnapshot] = []
        for row in rows:
            if isinstance(row, BboSnapshot):
                snapshot = row
            else:
                bid = _safe_float(row.get("best_bid"))
                ask = _safe_float(row.get("best_ask"))
                if bid is None or ask is None:
                    continue
                snapshot = BboSnapshot(
                    ts=row.get("ts"),
                    best_bid=bid,
                    best_ask=ask,
                    spread_bps=_safe_float(row.get("spread_bps")),
                )
            snapshots.append(snapshot)
        out[str(trigger_id)] = sorted(snapshots, key=lambda item: _ts_sort_key(item.ts))
    return out


def _config_summary(cfg: A2MakerFillConfig) -> dict[str, Any]:
    return {
        "symbols": list(cfg.symbols),
        "per_symbol_threshold": dict(cfg.per_symbol_threshold),
        "min_events": cfg.min_events,
        "dominance_share": cfg.dominance_share,
        "timeout_sec": cfg.timeout_sec,
        "entry_bbo_grace_sec": cfg.entry_bbo_grace_sec,
        "spread_guard_bps": cfg.spread_guard_bps,
        "offset_bps_list": list(cfg.offset_bps_list),
        "primary_offset_bps": cfg.primary_offset_bps,
        "min_attempts": cfg.min_attempts,
        "min_fill_rate": cfg.min_fill_rate,
        "entry_price_proxy": {
            "long_liquidated": "passive buy at entry_best_bid * (1 - offset_bps/10000)",
            "short_liquidated": "passive sell at entry_best_ask * (1 + offset_bps/10000)",
        },
        "fill_proxy": {
            "buy": "filled when future best_ask <= limit_price",
            "sell": "filled when future best_bid >= limit_price",
        },
    }


def _data_window(events: Sequence[CascadeTriggerEvent]) -> dict[str, Any]:
    return {
        "n_qualifying_triggers": len(events),
        "start_ts": _iso_ts(events[0].bucket_end_ts) if events else None,
        "end_ts": _iso_ts(events[-1].bucket_end_ts) if events else None,
        "source_tables": ["market.liquidations", "market.market_tickers"],
    }


def _attempt_examples(attempts: Sequence[Mapping[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in attempts:
        if len(out) >= limit:
            break
        if item.get("filled") is True or item.get("reason") in {"no_touch", "spread_guard", "missing_entry_bbo"}:
            out.append(
                {
                    "trigger_id": item.get("trigger_id"),
                    "symbol": item.get("symbol"),
                    "bucket_end_ts": item.get("bucket_end_ts"),
                    "dominant_side": item.get("dominant_side"),
                    "offset_bps": item.get("offset_bps"),
                    "entry_side": item.get("entry_side"),
                    "reason": item.get("reason"),
                    "filled": item.get("filled"),
                    "limit_price": item.get("limit_price"),
                    "fill_ts": item.get("fill_ts"),
                    "seconds_to_fill": item.get("seconds_to_fill"),
                    "entry_spread_bps": item.get("entry_spread_bps"),
                    "n_bbo_snapshots": item.get("n_bbo_snapshots"),
                }
            )
    return out


def _validate_config(cfg: A2MakerFillConfig) -> None:
    if not cfg.symbols:
        raise ValueError("symbols must not be empty")
    unsupported = [symbol for symbol in cfg.symbols if symbol not in DEFAULT_PER_SYMBOL_THRESHOLD]
    if unsupported:
        raise ValueError("A2 diagnostic supports BTCUSDT/ETHUSDT only; unsupported=" + ",".join(unsupported))
    for symbol in cfg.symbols:
        threshold = cfg.per_symbol_threshold.get(symbol)
        if threshold is None or float(threshold) <= 0.0:
            raise ValueError(f"missing positive threshold for {symbol}")
    if cfg.min_events <= 0:
        raise ValueError("min_events must be positive")
    if not (0.5 <= cfg.dominance_share <= 1.0):
        raise ValueError("dominance_share must be in [0.5, 1.0]")
    if cfg.timeout_sec <= 0 or cfg.entry_bbo_grace_sec < 0:
        raise ValueError("timeout_sec must be positive and entry_bbo_grace_sec non-negative")
    if cfg.spread_guard_bps <= 0.0:
        raise ValueError("spread_guard_bps must be positive")
    if not cfg.offset_bps_list:
        raise ValueError("offset_bps_list must not be empty")
    for offset in cfg.offset_bps_list:
        if offset < 0.0 or not math.isfinite(offset):
            raise ValueError("offset_bps values must be finite and non-negative")
    if cfg.primary_offset_bps not in cfg.offset_bps_list:
        raise ValueError("primary_offset_bps must be included in offset_bps_list")
    if cfg.min_attempts <= 0:
        raise ValueError("min_attempts must be positive")
    if not (0.0 < cfg.min_fill_rate <= 1.0):
        raise ValueError("min_fill_rate must be in (0, 1]")


def _threshold_params(cfg: A2MakerFillConfig) -> dict[str, float]:
    return {
        "threshold_btcusdt": float(cfg.per_symbol_threshold.get("BTCUSDT", math.inf)),
        "threshold_ethusdt": float(cfg.per_symbol_threshold.get("ETHUSDT", math.inf)),
        "threshold_other": 1.0e100,
    }


def _entry_side(dominant_side: str) -> str | None:
    if dominant_side == "long_liquidated":
        return "buy"
    if dominant_side == "short_liquidated":
        return "sell"
    return None


def _spread_bps(best_bid: float, best_ask: float) -> float | None:
    midpoint = (best_bid + best_ask) / 2.0
    if midpoint <= 0.0 or best_ask < best_bid:
        return None
    return (best_ask - best_bid) / midpoint * 10_000.0


def _seconds_between(start: Any, end: Any) -> float | None:
    if isinstance(start, datetime) and isinstance(end, datetime):
        return max(0.0, (end - start).total_seconds())
    start_ts = _ts_sort_key(start)
    end_ts = _ts_sort_key(end)
    if start_ts > 0.0 and end_ts > 0.0:
        return max(0.0, end_ts - start_ts)
    return None


def _count_by_reason(attempts: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in attempts:
        reason = str(item.get("reason") or "unknown")
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float | None, float | None]:
    if n <= 0:
        return None, None
    phat = successes / n
    denom = 1.0 + z * z / n
    center = (phat + z * z / (2.0 * n)) / denom
    margin = z * math.sqrt((phat * (1.0 - phat) + z * z / (4.0 * n)) / n) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[midpoint]
    return (ordered[midpoint - 1] + ordered[midpoint]) / 2.0


# _safe_float 整併至 helper_scripts.lib.stats_common（與原 local 實作 byte-equiv：
# float() 轉換失敗或非 finite → None）。re-export 保留本檔內既有 _safe_float 呼叫點。
_safe_float = _sc._safe_float


def _ts_sort_key(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    timestamp = getattr(value, "timestamp", None)
    if callable(timestamp):
        return float(timestamp())
    return 0.0


def _iso_ts(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _offset_key(value: float) -> float:
    return round(float(value), 8)


def _clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean_json(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        return value
    return value


def parse_offset_bps_list(value: str) -> tuple[float, ...]:
    offsets: list[float] = []
    for item in value.split(","):
        text = item.strip()
        if not text:
            continue
        offset = float(text)
        if offset < 0.0 or not math.isfinite(offset):
            raise ValueError("offsets must be finite and non-negative")
        if offset not in offsets:
            offsets.append(offset)
    if not offsets:
        raise ValueError("at least one offset is required")
    return tuple(offsets)


def _parse_symbols(value: str) -> tuple[str, ...]:
    symbols = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    if not symbols:
        raise ValueError("at least one symbol is required")
    return symbols


def _load_runtime_pg_env() -> None:
    """Load canonical Linux runtime PG env when explicit env is absent."""
    if os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL"):
        return
    if os.environ.get("POSTGRES_USER") and os.environ.get("POSTGRES_DB"):
        return
    secrets_root = Path(
        os.environ.get("OPENCLAW_SECRETS_ROOT")
        or Path.home() / "BybitOpenClaw" / "secrets"
    )
    env_path = secrets_root / "environment_files" / "basic_system_services.env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#") or "=" not in item:
            continue
        if item.startswith("export "):
            item = item[len("export "):]
        key, value = item.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def _get_conn() -> Any:
    import psycopg2  # type: ignore

    _load_runtime_pg_env()
    dsn = os.environ.get("OPENCLAW_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if dsn:
        return psycopg2.connect(dsn, application_name="openclaw_a2_maker_fill_feasibility")
    required = {
        "host": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "port": os.environ.get("POSTGRES_PORT", "5432"),
        "dbname": os.environ.get("POSTGRES_DB"),
        "user": os.environ.get("POSTGRES_USER"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError("missing PG connection env: " + ", ".join(missing))
    password = os.environ.get("POSTGRES_PASSWORD")
    if password:
        required["password"] = password
    return psycopg2.connect(**required, application_name="openclaw_a2_maker_fill_feasibility")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="A2 maker-fill feasibility diagnostic")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--btc-threshold-usd", type=float, default=DEFAULT_PER_SYMBOL_THRESHOLD["BTCUSDT"])
    parser.add_argument("--eth-threshold-usd", type=float, default=DEFAULT_PER_SYMBOL_THRESHOLD["ETHUSDT"])
    parser.add_argument("--min-events", type=int, default=3)
    parser.add_argument("--dominance-share", type=float, default=0.60)
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--entry-bbo-grace-sec", type=int, default=10)
    parser.add_argument("--spread-guard-bps", type=float, default=50.0)
    parser.add_argument("--offset-bps-list", default="0,1,2,5")
    parser.add_argument("--primary-offset-bps", type=float, default=1.0)
    parser.add_argument("--min-attempts", type=int, default=30)
    parser.add_argument("--min-fill-rate", type=float, default=0.50)
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    try:
        symbols = _parse_symbols(args.symbols)
        offsets = parse_offset_bps_list(args.offset_bps_list)
        cfg = A2MakerFillConfig(
            symbols=symbols,
            per_symbol_threshold={
                "BTCUSDT": args.btc_threshold_usd,
                "ETHUSDT": args.eth_threshold_usd,
            },
            min_events=args.min_events,
            dominance_share=args.dominance_share,
            timeout_sec=args.timeout_sec,
            entry_bbo_grace_sec=args.entry_bbo_grace_sec,
            spread_guard_bps=args.spread_guard_bps,
            offset_bps_list=offsets,
            primary_offset_bps=args.primary_offset_bps,
            min_attempts=args.min_attempts,
            min_fill_rate=args.min_fill_rate,
        )
        _validate_config(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] invalid config: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    try:
        conn = _get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] PG connection failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    try:
        rows = fetch_maker_fill_query_rows(conn, cfg=cfg, lookback_days=args.lookback_days)
    except Exception as exc:  # noqa: BLE001
        print(f"[FATAL] A2 maker-fill query failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    events, snapshots = query_rows_to_events(rows)
    packet = analyze_maker_fill_feasibility(events, snapshots, cfg=cfg)
    text = json.dumps(_clean_json(packet), ensure_ascii=False, indent=2, sort_keys=False)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[OK] packet written: {args.out}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

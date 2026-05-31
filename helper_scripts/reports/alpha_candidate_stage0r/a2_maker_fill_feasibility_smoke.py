#!/usr/bin/env python3
"""Smoke tests for A2 maker-fill feasibility diagnostic.

Synthetic only. No PG connection. The tests cover passive buy/sell BBO touch,
no-touch rejection, spread-guard skips, insufficient samples, SQL read-only
shape, and forbidden-output discipline.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from a2_maker_fill_feasibility import (  # noqa: E402
    A2_ALPHA_SOURCE_ID,
    A2MakerFillConfig,
    BboSnapshot,
    CascadeTriggerEvent,
    analyze_maker_fill_feasibility,
    build_maker_fill_query,
    parse_offset_bps_list,
    query_rows_to_events,
)


_BASE = datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc)


def _cfg(**overrides: Any) -> A2MakerFillConfig:
    data = {
        "symbols": ("BTCUSDT", "ETHUSDT"),
        "min_attempts": 3,
        "offset_bps_list": (1.0,),
        "primary_offset_bps": 1.0,
        "spread_guard_bps": 50.0,
    }
    data.update(overrides)
    return A2MakerFillConfig(**data)


def _event(
    idx: int,
    *,
    symbol: str = "BTCUSDT",
    dominant_side: str = "long_liquidated",
    bid: float = 100.0,
    ask: float = 100.02,
    spread_bps: float | None = None,
) -> CascadeTriggerEvent:
    ts = _BASE + timedelta(minutes=5 * idx)
    return CascadeTriggerEvent(
        trigger_id=f"{symbol}|{idx}|{dominant_side}",
        symbol=symbol,
        bucket_start_ts=ts - timedelta(minutes=5),
        bucket_end_ts=ts,
        dominant_side=dominant_side,
        event_count_5m=3,
        dominant_event_count=3,
        cluster_notional_5m=600_000.0 if symbol == "BTCUSDT" else 350_000.0,
        long_liq_notional=600_000.0 if dominant_side == "long_liquidated" else 0.0,
        short_liq_notional=600_000.0 if dominant_side == "short_liquidated" else 0.0,
        entry_bbo_ts=ts,
        entry_best_bid=bid,
        entry_best_ask=ask,
        entry_spread_bps=spread_bps,
    )


def _snap(base_ts: datetime, seconds: int, bid: float, ask: float) -> BboSnapshot:
    return BboSnapshot(ts=base_ts + timedelta(seconds=seconds), best_bid=bid, best_ask=ask)


def _check_pass_fill_gate(failures: list[str]) -> None:
    events = [
        _event(0, dominant_side="long_liquidated", bid=100.0, ask=100.02),
        _event(1, dominant_side="short_liquidated", bid=100.0, ask=100.02),
        _event(2, dominant_side="long_liquidated", bid=100.0, ask=100.02),
    ]
    snapshots = {
        events[0].trigger_id: [
            _snap(events[0].bucket_end_ts, 5, bid=99.95, ask=99.98),
        ],
        events[1].trigger_id: [
            _snap(events[1].bucket_end_ts, 7, bid=100.04, ask=100.06),
        ],
        events[2].trigger_id: [
            _snap(events[2].bucket_end_ts, 9, bid=99.99, ask=100.01),
        ],
    }
    packet = analyze_maker_fill_feasibility(events, snapshots, cfg=_cfg())
    if packet.get("alpha_source_id") != A2_ALPHA_SOURCE_ID:
        failures.append("alpha_source_id mismatch")
    if packet.get("verdict") != "draft_only":
        failures.append(f"2/3 fill rate should pass as draft_only, got {packet.get('verdict')}")
    primary = packet.get("primary_summary") or {}
    if primary.get("eligible_attempts") != 3 or primary.get("simulated_fills") != 2:
        failures.append(f"unexpected primary summary: {primary}")
    if abs(float(primary.get("maker_touch_fill_rate") or 0.0) - (2.0 / 3.0)) > 1e-9:
        failures.append(f"unexpected fill rate: {primary}")
    examples = packet.get("event_examples") or []
    if not any(item.get("entry_side") == "buy" and item.get("filled") is True for item in examples):
        failures.append("missing filled passive buy example")
    if not any(item.get("entry_side") == "sell" and item.get("filled") is True for item in examples):
        failures.append("missing filled passive sell example")
    if packet.get("eligible_for_demo_canary") is not False:
        failures.append("diagnostic must not enable demo canary")


def _check_reject_fill_gate(failures: list[str]) -> None:
    events = [_event(i, dominant_side="long_liquidated") for i in range(3)]
    snapshots = {
        events[0].trigger_id: [_snap(events[0].bucket_end_ts, 5, bid=99.98, ask=99.99)],
        events[1].trigger_id: [_snap(events[1].bucket_end_ts, 5, bid=100.0, ask=100.02)],
        events[2].trigger_id: [_snap(events[2].bucket_end_ts, 5, bid=100.0, ask=100.02)],
    }
    packet = analyze_maker_fill_feasibility(events, snapshots, cfg=_cfg())
    if packet.get("verdict") != "reject":
        failures.append(f"1/3 fill rate should reject, got {packet.get('verdict')}")
    if "maker_touch_fill_rate" not in " ".join(packet.get("fail_reasons") or []):
        failures.append(f"reject reason should mention fill rate, got {packet.get('fail_reasons')}")


def _check_spread_guard_and_insufficient(failures: list[str]) -> None:
    wide = _event(0, bid=100.0, ask=101.0, spread_bps=99.5)
    good = _event(1, bid=100.0, ask=100.02)
    packet = analyze_maker_fill_feasibility(
        [wide, good],
        {
            wide.trigger_id: [_snap(wide.bucket_end_ts, 5, bid=99.0, ask=99.1)],
            good.trigger_id: [_snap(good.bucket_end_ts, 5, bid=99.95, ask=99.98)],
        },
        cfg=_cfg(min_attempts=2),
    )
    primary = packet.get("primary_summary") or {}
    if primary.get("eligible_attempts") != 1:
        failures.append(f"wide spread event should be skipped, got {primary}")
    if (primary.get("skip_counts") or {}).get("spread_guard") != 1:
        failures.append(f"spread_guard skip missing, got {primary}")
    if packet.get("verdict") != "observe_more":
        failures.append(f"1 eligible attempt with min=2 should observe_more, got {packet.get('verdict')}")


def _check_query_read_only(failures: list[str]) -> None:
    sql, params = build_maker_fill_query(cfg=_cfg(), lookback_days=30)
    lowered = sql.lower()
    for token in ("insert", "update", "delete", "alter", "drop", "create", "truncate"):
        if re.search(rf"\b{token}\b", lowered):
            failures.append(f"query should be read-only, found {token}")
    if "market.liquidations" not in sql or "market.market_tickers" not in sql:
        failures.append("query should read liquidations and market_tickers")
    if params.get("min_events") != 3 or params.get("timeout_sec") != 60:
        failures.append(f"query params mismatch: {params}")


def _check_query_rows_to_events(failures: list[str]) -> None:
    row = {
        "trigger_id": "BTCUSDT|1|long_liquidated",
        "symbol": "BTCUSDT",
        "bucket_start_ts": _BASE,
        "bucket_end_ts": _BASE + timedelta(minutes=5),
        "event_count_5m": 3,
        "dominant_event_count": 3,
        "cluster_notional_5m": 700_000.0,
        "long_liq_notional": 700_000.0,
        "short_liq_notional": 0.0,
        "dominant_side": "long_liquidated",
        "entry_bbo_ts": _BASE + timedelta(minutes=5),
        "entry_best_bid": 100.0,
        "entry_best_ask": 100.02,
        "entry_spread_bps": 2.0,
        "tick_ts": _BASE + timedelta(minutes=5, seconds=5),
        "tick_best_bid": 99.95,
        "tick_best_ask": 99.98,
        "tick_spread_bps": 3.0,
    }
    events, snapshots = query_rows_to_events([row])
    if len(events) != 1 or len(snapshots.get(row["trigger_id"], [])) != 1:
        failures.append(f"query row grouping failed: events={events} snapshots={snapshots}")


def _check_offset_parser_and_forbidden_output(failures: list[str]) -> None:
    if parse_offset_bps_list("0,1,1,2") != (0.0, 1.0, 2.0):
        failures.append("offset parser should de-duplicate preserving order")
    packet = analyze_maker_fill_feasibility(
        [_event(i) for i in range(3)],
        {},
        cfg=_cfg(),
    )
    scrubbed = dict(packet)
    scrubbed.pop("governance_attest", None)
    blob = json.dumps(scrubbed, ensure_ascii=False)
    for token in (
        "Stage 1 PASS",
        "stage_1_pass",
        "auto_promote",
        "to_stage",
        "live_reserved",
        "OPENCLAW_ALLOW_MAINNET",
        "authorization.json",
        "decision_lease_emitted",
    ):
        if token in blob:
            failures.append(f"forbidden token present: {token}")


def main() -> int:
    failures: list[str] = []
    _check_pass_fill_gate(failures)
    _check_reject_fill_gate(failures)
    _check_spread_guard_and_insufficient(failures)
    _check_query_read_only(failures)
    _check_query_rows_to_events(failures)
    _check_offset_parser_and_forbidden_output(failures)
    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("PASS a2_maker_fill_feasibility smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

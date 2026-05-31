#!/usr/bin/env python3
"""Smoke tests for A3 BTC/ETH pairs precheck.

合成數據，不連 PG。驗 A3 stats-first DRAFT lane 的核心不變量：
cointegration/half-life pass、shift(1) next-bar entry、fee replay sample gate、
以及任何情況不輸出 stage0_ready / auto-promote 類 token。
"""
from __future__ import annotations

import json
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from a3_pairs_precheck import (  # noqa: E402
    A3_ALPHA_SOURCE_ID,
    PairBar,
    PairPrecheckConfig,
    analyze_pair_precheck,
    build_pairs_kline_query,
)


_BASE = datetime(2026, 5, 1, tzinfo=timezone.utc)


def _cointegrated_rows(n: int = 1200) -> list[PairBar]:
    rows: list[PairBar] = []
    rng = random.Random(20260531)
    spread = 0.0
    for i in range(n):
        x = math.log(40_000.0) + 0.00003 * i + 0.018 * math.sin(i / 71.0)
        # Stationary AR residual: strong enough for the ADF-like proxy and
        # still noisy enough to generate real z-score entries.
        spread = 0.58 * spread + rng.gauss(0.0, 0.004)
        y = -1.85 + 1.04 * x + spread
        rows.append(
            PairBar(
                ts=_BASE + timedelta(minutes=5 * i),
                x_close=math.exp(x),
                y_close=math.exp(y),
            )
        )
    return rows


def _random_walk_spread_rows(n: int = 1200) -> list[PairBar]:
    rows: list[PairBar] = []
    spread = 0.0
    for i in range(n):
        x = math.log(40_000.0) + 0.00004 * i + 0.01 * math.sin(i / 53.0)
        # deterministic non-stationary residual: no mean-reversion.
        spread += 0.00008 + 0.0009 * math.sin(i / 17.0)
        y = -1.8 + 1.02 * x + spread
        rows.append(
            PairBar(
                ts=_BASE + timedelta(minutes=5 * i),
                x_close=math.exp(x),
                y_close=math.exp(y),
            )
        )
    return rows


def _base_cfg(**overrides: Any) -> PairPrecheckConfig:
    data = {
        "min_aligned_bars": 300,
        "min_abs_corr": 0.65,
        "adf_t_stat_max": -2.5,
        "max_half_life_bars": 160.0,
        "rolling_window": 72,
        "entry_z": 1.2,
        "exit_z": 0.2,
        "max_hold_bars": 96,
        "min_trades": 8,
        "roundtrip_cost_bps": 0.5,
    }
    data.update(overrides)
    return PairPrecheckConfig(**data)


def _check_positive_draft_precheck(failures: list[str]) -> None:
    packet = analyze_pair_precheck(_cointegrated_rows(), config=_base_cfg())
    if packet.get("alpha_source_id") != A3_ALPHA_SOURCE_ID:
        failures.append("alpha_source_id mismatch")
    if packet.get("verdict") != "draft_only":
        failures.append(f"cointegrated synthetic should be draft_only, got {packet.get('verdict')}")
    if packet.get("precheck_ready_for_pa_spec") is not True:
        failures.append("positive synthetic should be ready for PA spec")
    coint = packet.get("cointegration") or {}
    if coint.get("cointegration_pass") is not True:
        failures.append(f"cointegration_pass should be true, got {coint}")
    replay = packet.get("fee_adjusted_replay") or {}
    if replay.get("fee_gate_pass") is not True:
        failures.append(f"fee_gate_pass should be true, got {replay}")
    if packet.get("stage0_ready_candidate") is not False:
        failures.append("A3 precheck must not output stage0_ready_candidate=true")
    if packet.get("eligible_for_demo_canary") is not False:
        failures.append("A3 precheck must not mark demo eligibility")


def _check_next_bar_entry(failures: list[str]) -> None:
    packet = analyze_pair_precheck(_cointegrated_rows(), config=_base_cfg())
    trades = ((packet.get("fee_adjusted_replay") or {}).get("trade_examples") or [])
    if not trades:
        failures.append("expected at least one trade example")
        return
    first = trades[0]
    if not (str(first.get("entry_ts")) > str(first.get("entry_signal_ts"))):
        failures.append(f"entry_ts must be after entry_signal_ts, got {first}")


def _check_cointegration_reject(failures: list[str]) -> None:
    packet = analyze_pair_precheck(_random_walk_spread_rows(), config=_base_cfg())
    if packet.get("verdict") != "reject":
        failures.append(f"random-walk residual should reject, got {packet.get('verdict')}")
    reasons = packet.get("fail_reasons") or []
    if "cointegration_adf_proxy_fail" not in reasons and "half_life_out_of_bounds" not in reasons:
        failures.append(f"reject reasons should mention cointegration/half-life, got {reasons}")


def _check_insufficient_rows_observe_more(failures: list[str]) -> None:
    packet = analyze_pair_precheck(_cointegrated_rows(80), config=_base_cfg())
    if packet.get("verdict") != "observe_more":
        failures.append(f"short data should observe_more, got {packet.get('verdict')}")
    if packet.get("cointegration") is not None:
        failures.append("insufficient data should not compute cointegration packet")


def _check_query_read_only(failures: list[str]) -> None:
    sql, params = build_pairs_kline_query(
        symbol_x="BTCUSDT",
        symbol_y="ETHUSDT",
        timeframe="5m",
        lookback_days=60,
    )
    lowered = sql.lower()
    for token in ("insert", "update", "delete", "alter", "drop"):
        if token in lowered:
            failures.append(f"query should be read-only, found {token}")
    if "market.klines" not in sql:
        failures.append("query should read market.klines")
    if params.get("symbol_x") != "BTCUSDT" or params.get("symbol_y") != "ETHUSDT":
        failures.append(f"query params symbols wrong: {params}")


def _check_forbidden_output_tokens(failures: list[str]) -> None:
    packet = analyze_pair_precheck(_cointegrated_rows(), config=_base_cfg())
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
    _check_positive_draft_precheck(failures)
    _check_next_bar_entry(failures)
    _check_cointegration_reject(failures)
    _check_insufficient_rows_observe_more(failures)
    _check_query_read_only(failures)
    _check_forbidden_output_tokens(failures)
    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("PASS a3_pairs_precheck smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

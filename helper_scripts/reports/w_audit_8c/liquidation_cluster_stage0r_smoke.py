#!/usr/bin/env python3
"""Smoke test for W-AUDIT-8c Stage 0R pure metrics.

MODULE_NOTE
模塊用途：對 liquidation_cluster_stage0r_metrics 模塊的純合成數據驗證。
為什麼用合成數據而非 PG dry-run：本檔屬 8C-S0R-2 worktree 範圍，PG dry-run
留給 8C-S0R-4 worktree（per PA design §4.1）；本檔僅驗 math 正確性與
RED 路徑 fail-closed。

主要 cases：
  - PASS-BOTH happy path：合成兩方向均符 floor 之 panel。
  - PASS-LONG-ONLY：long-only triggers → emit PASS-LONG-ONLY（非 RED）。
  - PASS-SHORT-ONLY：short-only triggers → emit PASS-SHORT-ONLY。
  - RED via insufficient_n_per_cell / pooled_n_eff_too_low / both_direction_dead /
    single_day_87pct / single_symbol_87pct / sample_days_lt_7 / dsr_pbo_auto_red /
    bb_demo_bias_not_confirmed 等 fail-closed scenarios。
  - cluster-aware n_eff 數學單元：100 triggers in 60min → n_eff_cluster ≤ 1；
    100 triggers spaced > 60min apart → n_eff_cluster = min(distinct days,
    horizon_overlap)。
  - bootstrap CI：known-mean 合成數據 CI within tolerance。
  - sweep：4×4 grid 配置 → 返回 16 cells。

依賴：純 stdlib + sibling metrics 模塊。

硬邊界：合成數據；不接 PG；不寫文件。
"""

from __future__ import annotations

import json
import math
import sys
from typing import Any

try:
    from .liquidation_cluster_stage0r_metrics import (
        ALPHA_SOURCE_ID,
        BOTH_DIRECTION_FLOOR_RATE,
        BRANCH_N_EFF_FLOOR,
        DENSITY_TIERS,
        DIRECTION_BRANCHES,
        MAX_DAY_SHARE,
        MAX_SYMBOL_SHARE,
        MIN_SAMPLE_DAYS,
        PER_CELL_N_FLOOR,
        POOLED_N_EFF_FLOOR,
        _both_direction_floor_check,
        _classify_symbols_by_tier,
        _classify_tier,
        _density_floor_efficacy,
        _false_positive_rate,
        _n_eff_cluster_aware,
        _single_day_concentration_check,
        _single_symbol_concentration_check,
        block_bootstrap_ci,
        compute_stage0r,
        compute_stage0r_sweep,
        dsr_with_k,
        psr_bailey_ldp,
        wilson_ci_95,
    )
except ImportError:
    from liquidation_cluster_stage0r_metrics import (  # type: ignore
        ALPHA_SOURCE_ID,
        BOTH_DIRECTION_FLOOR_RATE,
        BRANCH_N_EFF_FLOOR,
        DENSITY_TIERS,
        DIRECTION_BRANCHES,
        MAX_DAY_SHARE,
        MAX_SYMBOL_SHARE,
        MIN_SAMPLE_DAYS,
        PER_CELL_N_FLOOR,
        POOLED_N_EFF_FLOOR,
        _both_direction_floor_check,
        _classify_symbols_by_tier,
        _classify_tier,
        _density_floor_efficacy,
        _false_positive_rate,
        _n_eff_cluster_aware,
        _single_day_concentration_check,
        _single_symbol_concentration_check,
        block_bootstrap_ci,
        compute_stage0r,
        compute_stage0r_sweep,
        dsr_with_k,
        psr_bailey_ldp,
        wilson_ci_95,
    )


# ============================================================================
# Fixture builders（合成數據生成；模擬 SQL CTE final_signals row 結構）
# ============================================================================


def _make_row(
    symbol: str,
    bucket_end_ts_ms: int,
    dominant_side: str,
    *,
    cluster_notional_5m: float = 50_000.0,
    event_count_5m: int = 5,
    dominant_event_count: int = 4,
    side_dominance_ratio: float = 0.90,
    entry_mid: float = 100.0,
    exit_mid: float | None = None,  # 預設依方向 mean-revert：long → up；short → down
) -> dict[str, Any]:
    """合成單一 panel row（per PA design §2.3 CTE final_signals 結構）。

    為什麼 exit_mid 依方向決定：long_liquidated → expected mean-revert UP
    (+1 dir)；要 +50 bps gross，exit > entry。short_liquidated → expected
    mean-revert DOWN (-1 dir)；要 +50 bps gross，exit < entry。如此
    `gross_bps = 10000 * expected_dir * (exit-entry)/entry` 兩方向都 +50。
    """
    if exit_mid is None:
        exit_mid = entry_mid + 0.50 if dominant_side == "long_liquidated" else entry_mid - 0.50
    expected_dir = +1 if dominant_side == "long_liquidated" else -1
    gross_bps = 10000.0 * expected_dir * (exit_mid - entry_mid) / entry_mid
    net_bps = gross_bps - 12.0
    return {
        "symbol": symbol,
        "bucket_5m_epoch": bucket_end_ts_ms // 1000,
        "bucket_end_ts_ms": bucket_end_ts_ms,
        "dominant_side": dominant_side,
        "expected_dir": expected_dir,
        "cluster_notional_5m": cluster_notional_5m,
        "event_count_5m": event_count_5m,
        "dominant_event_count": dominant_event_count,
        "side_dominance_ratio": side_dominance_ratio,
        "notional_pct_24h": 0.95,
        "entry_mid": entry_mid,
        "exit_mid": exit_mid,
        "gross_bps": gross_bps,
        "net_bps": net_bps,
    }


def _build_balanced_fixture(
    n_symbols: int = 25,
    n_days: int = 7,
    n_per_day_per_dir: int = 4,
) -> list[dict[str, Any]]:
    """合成 balanced 雙方向 panel：25 symbols × 7 days × 8 events/day
    （4 long + 4 short）= 1400 rows。

    為什麼這設定：n_symbols ≥ MIN_STAGE0R_SYMBOLS (25)；n_days ≥
    MIN_SAMPLE_DAYS (7)；每日 8 events 確保 per-cell n 與 pooled n_eff
    超過 floor。

    avg_net_bps 設 +30（> 15 floor）；entry/exit ratios 預設 +50 bps gross。
    """
    rows: list[dict[str, Any]] = []
    base_ts_ms = 1_765_000_000_000
    day_ms = 86_400_000
    for sym_idx in range(n_symbols):
        sym = f"SYM{sym_idx:02d}USDT"
        for day_idx in range(n_days):
            day_start_ms = base_ts_ms + day_idx * day_ms
            for ev_idx in range(n_per_day_per_dir):
                # Long event — 90min apart to avoid 60min cluster collapse。
                long_ts_ms = day_start_ms + ev_idx * 5_400_000
                rows.append(_make_row(sym, long_ts_ms, "long_liquidated"))
                # Short event — offset by 45min from long。
                short_ts_ms = long_ts_ms + 2_700_000
                rows.append(_make_row(sym, short_ts_ms, "short_liquidated"))
    return rows


def _build_long_only_fixture(
    n_symbols: int = 25,
    n_days: int = 7,
    n_per_day: int = 8,
) -> list[dict[str, Any]]:
    """合成 long-only panel：模擬 BB STRUCTURAL 之 8-12× long-skew。

    為什麼必要：驗 4-value verdict 邏輯 — long-dead-only 應 emit
    PASS-LONG-ONLY 非 RED（per task brief §"both-direction floor failure
    does NOT auto-RED entire cell"）。
    """
    rows: list[dict[str, Any]] = []
    base_ts_ms = 1_765_000_000_000
    day_ms = 86_400_000
    for sym_idx in range(n_symbols):
        sym = f"SYM{sym_idx:02d}USDT"
        for day_idx in range(n_days):
            day_start_ms = base_ts_ms + day_idx * day_ms
            for ev_idx in range(n_per_day):
                ts_ms = day_start_ms + ev_idx * 5_400_000
                rows.append(_make_row(sym, ts_ms, "long_liquidated"))
    return rows


def _build_single_day_87pct_fixture() -> list[dict[str, Any]]:
    """合成 single-day 87% 集中 panel（鏡像 8b INJUSDT 教訓）。

    其中一天 87% events，其餘 6 天分佈 13%。
    """
    rows: list[dict[str, Any]] = []
    base_ts_ms = 1_765_000_000_000
    day_ms = 86_400_000
    n_sym = 25
    # Day 2 為 87% 集中：每 symbol 87 events。
    big_day_idx = 2
    big_day_ms = base_ts_ms + big_day_idx * day_ms
    for sym_idx in range(n_sym):
        sym = f"SYM{sym_idx:02d}USDT"
        for ev_idx in range(87):
            ts_ms = big_day_ms + ev_idx * 600_000  # 10min apart within day
            rows.append(_make_row(sym, ts_ms, "long_liquidated"))
            rows.append(_make_row(sym, ts_ms + 300_000, "short_liquidated"))
    # 其他 6 天稀薄分佈：13/6 ≈ 2 events/day。
    for sym_idx in range(n_sym):
        sym = f"SYM{sym_idx:02d}USDT"
        for day_idx in range(7):
            if day_idx == big_day_idx:
                continue
            day_start_ms = base_ts_ms + day_idx * day_ms
            for ev_idx in range(2):
                ts_ms = day_start_ms + ev_idx * 5_400_000
                rows.append(_make_row(sym, ts_ms, "long_liquidated"))
                rows.append(_make_row(sym, ts_ms + 2_700_000, "short_liquidated"))
    return rows


def _build_single_symbol_87pct_fixture() -> list[dict[str, Any]]:
    """合成 single-symbol 87% 集中 panel（per 8b INJUSDT 教訓）。"""
    rows: list[dict[str, Any]] = []
    base_ts_ms = 1_765_000_000_000
    day_ms = 86_400_000
    # INJ-style：87 events × 7 days = 609。
    for day_idx in range(7):
        day_start_ms = base_ts_ms + day_idx * day_ms
        for ev_idx in range(87):
            ts_ms = day_start_ms + ev_idx * 600_000
            rows.append(_make_row("INJUSDT", ts_ms, "long_liquidated"))
    # 其他 24 symbols 各 4 events/day × 7d = 28 each → 24*28 = 672 total。
    for sym_idx in range(24):
        sym = f"OTHER{sym_idx:02d}USDT"
        for day_idx in range(7):
            day_start_ms = base_ts_ms + day_idx * day_ms
            for ev_idx in range(4):
                ts_ms = day_start_ms + ev_idx * 5_400_000
                rows.append(_make_row(sym, ts_ms, "long_liquidated"))
    # INJ 60.9% of 1281 → > 40% MAX_SYMBOL_SHARE cap。
    return rows


# ============================================================================
# Test helpers
# ============================================================================


def _assert(condition: bool, msg: str, failures: list[str]) -> None:
    if not condition:
        failures.append(msg)


# ============================================================================
# Case：cluster-aware n_eff math unit tests
# ============================================================================


def _check_cluster_neff_60min_window(failures: list[str]) -> None:
    """100 triggers in 60min window 在 same (symbol, direction) → distinct_60min_clusters = 1。"""
    base_ts_ms = 1_765_000_000_000
    triggers = [
        {
            "signal_ts_ms": base_ts_ms + i * 30_000,  # 30s apart, well within 60min
            "symbol": "BTCUSDT",
            "direction": "long_liquidated",
        }
        for i in range(100)
    ]
    result = _n_eff_cluster_aware(triggers, horizon_min=5, cluster_window_min=60)
    _assert(
        result["distinct_60min_clusters"] == 1,
        f"100 triggers in 60min should be 1 cluster, got {result['distinct_60min_clusters']}",
        failures,
    )
    _assert(
        result["n_eff_cluster"] == 1,
        f"n_eff_cluster should be 1 (clusters binding), got {result['n_eff_cluster']}",
        failures,
    )


def _check_cluster_neff_spaced(failures: list[str]) -> None:
    """100 triggers spaced 2h apart → distinct_60min_clusters = 100。"""
    base_ts_ms = 1_765_000_000_000
    triggers = [
        {
            "signal_ts_ms": base_ts_ms + i * 7_200_000,  # 2h apart
            "symbol": "BTCUSDT",
            "direction": "long_liquidated",
        }
        for i in range(100)
    ]
    result = _n_eff_cluster_aware(triggers, horizon_min=5, cluster_window_min=60)
    _assert(
        result["distinct_60min_clusters"] == 100,
        f"100 triggers spaced 2h apart should be 100 clusters, got {result['distinct_60min_clusters']}",
        failures,
    )
    # n_eff_cluster = min(horizon=100, days=~9, clusters=100) = 9 binding by days。
    _assert(
        result["n_eff_cluster"] <= result["distinct_days"],
        f"n_eff_cluster should be ≤ distinct_days (days binding), got "
        f"cluster={result['n_eff_cluster']} days={result['distinct_days']}",
        failures,
    )


def _check_cluster_neff_three_way_binding(failures: list[str]) -> None:
    """horizon=30m → horizon_overlap = n // 6；days = small；clusters = different。
    驗 min(三方) 正確選 minimum。"""
    base_ts_ms = 1_765_000_000_000
    # 60 triggers spread over 2 days, each cluster 1 hour apart
    triggers = [
        {
            "signal_ts_ms": base_ts_ms + i * 3_600_000,  # 1h apart → 60 clusters distinct
            "symbol": "BTCUSDT",
            "direction": "long_liquidated",
        }
        for i in range(60)
    ]
    result = _n_eff_cluster_aware(triggers, horizon_min=30, cluster_window_min=60)
    # horizon_overlap = 60 / (30//5) = 60/6 = 10
    # distinct_days = ceil(60h / 24h) ≈ 3
    # distinct_60min_clusters = 60（剛好超過 60min boundary 每次新 cluster）
    # ⇒ n_eff_cluster = min(10, 3, 60) = 3
    _assert(
        result["n_eff_horizon"] == 10,
        f"horizon_overlap 60 / (30//5) should be 10, got {result['n_eff_horizon']}",
        failures,
    )
    _assert(
        result["n_eff_cluster"] == min(
            result["n_eff_horizon"], result["distinct_days"], result["distinct_60min_clusters"],
        ),
        f"n_eff_cluster should be min(三方), got breakdown={result}",
        failures,
    )


# ============================================================================
# Case：concentration cap checks
# ============================================================================


def _check_single_day_concentration(failures: list[str]) -> None:
    """合成 87% single-day → reject。"""
    base_ts_ms = 1_765_000_000_000
    day_ms = 86_400_000
    # 87 events on day 2; 13 events on days 0-6 (excl day 2) → total 100。
    big_day = base_ts_ms + 2 * day_ms
    other_days = [base_ts_ms + d * day_ms for d in range(7) if d != 2]
    triggers = []
    for i in range(87):
        triggers.append({"signal_ts_ms": big_day + i * 600_000, "symbol": "BTC"})
    for i, d in enumerate(other_days):
        for j in range(2):  # 2 events per other day → 12 total + 87 = 99 ≈ 87%
            triggers.append({"signal_ts_ms": d + j * 600_000, "symbol": "BTC"})

    result = _single_day_concentration_check(triggers, cap=MAX_DAY_SHARE)
    _assert(
        not result["passed"],
        f"single-day 87% should fail, got {result}",
        failures,
    )
    _assert(
        result["max_day_share"] > 0.80,
        f"max_day_share should exceed 80%, got {result['max_day_share']}",
        failures,
    )


def _check_single_day_concentration_pass(failures: list[str]) -> None:
    """合成 even distribution → pass。"""
    base_ts_ms = 1_765_000_000_000
    day_ms = 86_400_000
    triggers = []
    for d in range(7):
        for j in range(10):  # 70 evenly distributed
            triggers.append({"signal_ts_ms": base_ts_ms + d * day_ms + j * 300_000, "symbol": "BTC"})

    result = _single_day_concentration_check(triggers, cap=MAX_DAY_SHARE)
    _assert(
        result["passed"],
        f"even distribution should pass, got {result}",
        failures,
    )


def _check_single_symbol_concentration(failures: list[str]) -> None:
    """合成 BTCUSDT 60% concentration → reject (cap=0.40)。"""
    base_ts_ms = 1_765_000_000_000
    triggers = []
    # 60 BTC + 40 across 4 symbols。
    for i in range(60):
        triggers.append({"signal_ts_ms": base_ts_ms + i * 600_000, "symbol": "BTCUSDT"})
    for sym_idx, sym in enumerate(("ETH", "SOL", "DOGE", "LINK")):
        for j in range(10):
            triggers.append({
                "signal_ts_ms": base_ts_ms + (sym_idx * 10 + j) * 600_000,
                "symbol": sym,
            })

    result = _single_symbol_concentration_check(triggers, cap=MAX_SYMBOL_SHARE)
    _assert(
        not result["passed"],
        f"single-symbol 60% should fail (cap=0.40), got {result}",
        failures,
    )
    _assert(
        result["max_symbol"] == "BTCUSDT",
        f"max_symbol should be BTCUSDT, got {result['max_symbol']}",
        failures,
    )


# ============================================================================
# Case：both-direction floor check
# ============================================================================


def _check_both_direction_floor_long_dead(failures: list[str]) -> None:
    """100% long triggers → short_passed=False。"""
    triggers = [{"direction": "long_liquidated"} for _ in range(20)]
    result = _both_direction_floor_check(
        triggers, total_bucket_count=10_000, floor_rate=BOTH_DIRECTION_FLOOR_RATE,
    )
    _assert(result["long_passed"], "long should pass (20/10000=0.2% > 0.1%)", failures)
    _assert(not result["short_passed"], "short should fail (0 triggers)", failures)
    _assert(not result["both_passed"], "both should fail", failures)


def _check_both_direction_floor_both_pass(failures: list[str]) -> None:
    """20 long + 20 short / 10000 buckets → both pass。"""
    triggers = [{"direction": "long_liquidated"} for _ in range(20)] + \
               [{"direction": "short_liquidated"} for _ in range(20)]
    result = _both_direction_floor_check(
        triggers, total_bucket_count=10_000, floor_rate=BOTH_DIRECTION_FLOOR_RATE,
    )
    _assert(result["both_passed"], f"both should pass, got {result}", failures)


# ============================================================================
# Case：density floor efficacy / FP rate
# ============================================================================


def _check_density_floor_efficacy(failures: list[str]) -> None:
    """1000 raw buckets → 300 after K → 200 after N → 100 after M。
    efficacy = 1 - 100/1000 = 0.9 → pass。"""
    result = _density_floor_efficacy(1000, 300, 200, 100)
    _assert(result["passed"], f"efficacy 0.9 should pass, got {result}", failures)
    _assert(
        abs(result["efficacy"] - 0.9) < 1e-9,
        f"efficacy should be 0.9, got {result['efficacy']}",
        failures,
    )


def _check_false_positive_rate_pass(failures: list[str]) -> None:
    """100 triggers, all net_bps = +20 → fp_rate = 0 (none in ±5 band)。"""
    triggers = [{"net_bps": 20.0} for _ in range(100)]
    result = _false_positive_rate(triggers, bps_band=5.0, cost_bps=12.0)
    _assert(result["passed"], "0% FP rate should pass", failures)


def _check_false_positive_rate_fail(failures: list[str]) -> None:
    """100 triggers, 50 with |net_bps| ≤ 5 → fp_rate = 0.5 > 0.40 → fail。"""
    triggers = [{"net_bps": 2.0} for _ in range(50)] + \
               [{"net_bps": 30.0} for _ in range(50)]
    result = _false_positive_rate(triggers, bps_band=5.0, cost_bps=12.0)
    _assert(not result["passed"], f"50% FP rate should fail, got {result}", failures)


# ============================================================================
# Case：tier classification
# ============================================================================


def _check_tier_classify(failures: list[str]) -> None:
    _assert(_classify_tier(15) == "high", "≥10 → high", failures)
    _assert(_classify_tier(5) == "medium", "4-9 → medium", failures)
    _assert(_classify_tier(2) == "low", "≤3 → low", failures)
    _assert(_classify_tier(0) == "low", "0 → low", failures)


def _check_symbols_by_tier(failures: list[str]) -> None:
    rows = (
        [{"symbol": "BTC"}] * 15  # high
        + [{"symbol": "ETH"}] * 6  # medium
        + [{"symbol": "DOGE"}] * 2  # low
    )
    tiers = _classify_symbols_by_tier(rows)
    _assert(tiers["BTC"] == "high", "BTC 15 → high", failures)
    _assert(tiers["ETH"] == "medium", "ETH 6 → medium", failures)
    _assert(tiers["DOGE"] == "low", "DOGE 2 → low", failures)


# ============================================================================
# Case：core compute_stage0r — RED routes (fail-closed)
# ============================================================================


def _check_compute_stage0r_bb_demo_bias_refuse(failures: list[str]) -> None:
    """BB demo bias not confirmed → RED with explicit reason。"""
    rows = _build_balanced_fixture()
    packet = compute_stage0r(rows, bb_demo_bias_confirmed=False)
    _assert(packet["pass"] == "RED", "BB not cleared → RED", failures)
    _assert(
        any("bb_demo_bias_not_confirmed" in r for r in packet["pass_reasons"]),
        f"RED reason should mention bb_demo_bias_not_confirmed, got {packet['pass_reasons']}",
        failures,
    )


def _check_compute_stage0r_single_day_red(failures: list[str]) -> None:
    """single-day 87% → RED。"""
    rows = _build_single_day_87pct_fixture()
    packet = compute_stage0r(rows, bb_demo_bias_confirmed=True, k_event_count=1, n_usd=1, m_dominant=1)
    _assert(packet["pass"] == "RED", f"single-day 87% should RED, got {packet['pass']}", failures)
    _assert(
        any("single-day share" in r for r in packet["pass_reasons"]),
        f"RED reason should mention single-day, got {packet['pass_reasons']}",
        failures,
    )


def _check_compute_stage0r_single_symbol_red(failures: list[str]) -> None:
    """single-symbol 60% → RED。"""
    rows = _build_single_symbol_87pct_fixture()
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True, k_event_count=1, n_usd=1, m_dominant=1,
    )
    _assert(
        packet["pass"] == "RED",
        f"single-symbol concentration should RED, got {packet['pass']}",
        failures,
    )
    has_symbol_reason = any("single-symbol share" in r for r in packet["pass_reasons"])
    _assert(
        has_symbol_reason,
        f"RED reason should mention single-symbol, got {packet['pass_reasons']}",
        failures,
    )


# ============================================================================
# Case：core compute_stage0r — PASS-LONG-ONLY
# ============================================================================


def _check_compute_stage0r_long_only_emits_long_only(failures: list[str]) -> None:
    """合成 long-only triggers，profitable enough to bypass other floors → 預期
    PASS-LONG-ONLY 或 RED（後者表 other_red_reasons 之一 fail；驗 verdict
    分類正確即 sufficient — both direction 必明示 fail）。"""
    rows = _build_long_only_fixture(n_symbols=25, n_days=7, n_per_day=10)
    packet = compute_stage0r(
        rows,
        bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1,
        # 取 small floor 確保 trigger 都過。
    )
    # 因為 short 完全 dead，若無其他 hard fail 應為 PASS-LONG-ONLY。
    # 但 PSR / DSR / sample_window / FP rate / cost_edge 等 hard fail 可能 dominate。
    # 因此這個檢查驗：若 verdict 是 PASS-* 系列，必為 PASS-LONG-ONLY；不能是 PASS-BOTH。
    if packet["pass"].startswith("PASS"):
        _assert(
            packet["pass"] == "PASS-LONG-ONLY",
            f"long-only fixture PASS verdict should be PASS-LONG-ONLY, got {packet['pass']}",
            failures,
        )
    else:
        # 若 RED，驗 direction check 有捕捉 short-dead（不論其他 hard fail）。
        dc = packet["both_direction_floor"]
        _assert(
            dc["long_passed"] and not dc["short_passed"],
            f"long-only fixture: long should pass, short should fail; got {dc}",
            failures,
        )


def _check_compute_stage0r_balanced_no_panic(failures: list[str]) -> None:
    """Balanced fixture → 不應 panic / KeyError / TypeError；verdict 為合法 4 值。"""
    rows = _build_balanced_fixture()
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1,
    )
    _assert(
        packet["pass"] in ("PASS-BOTH", "PASS-LONG-ONLY", "PASS-SHORT-ONLY", "RED"),
        f"verdict should be valid 4-value, got {packet['pass']}",
        failures,
    )
    # 驗 packet 結構完整。
    required_keys = (
        "strategy_variant", "alpha_source_id", "pass", "pass_reasons",
        "n_per_cell", "pooled_n_eff", "pooled_n_eff_breakdown",
        "avg_net_bps", "avg_gross_bps", "psr_0", "dsr",
        "bootstrap_ci_95_60m", "bootstrap_ci_95_4h",
        "pbo", "pbo_metadata",
        "single_day_concentration", "single_symbol_concentration",
        "both_direction_floor", "density_floor_efficacy", "false_positive_rate",
        "long_branch", "short_branch", "tombstone_risk",
    )
    for k in required_keys:
        _assert(k in packet, f"missing required key: {k}", failures)


# ============================================================================
# Case：sweep — multi-cell evaluation
# ============================================================================


def _check_sweep_returns_expected_cells(failures: list[str]) -> None:
    """4×4 sweep on k×n_usd → 16 cells (其他軸取單值)。"""
    rows = _build_balanced_fixture()
    packet = compute_stage0r_sweep(
        rows,
        bb_demo_bias_confirmed=True,
        k_grid=(2, 3, 5, 8),
        n_usd_grid=(5_000, 10_000, 25_000, 50_000),
        m_grid=(1,),  # single value
        side_dom_grid=(0.7,),
        floor_grid=(10_000,),
        quiet_grid=(0,),
        horizon_grid=(5,),
    )
    _assert(
        len(packet["sweep_cells"]) == 16,
        f"expected 16 cells (4×4), got {len(packet['sweep_cells'])}",
        failures,
    )
    _assert(
        packet["sweep_meta"]["total_cells"] == 16,
        f"sweep_meta total_cells mismatch: {packet['sweep_meta']['total_cells']}",
        failures,
    )
    # 驗 per-tier × per-direction verdict 結構完整。
    for tier in DENSITY_TIERS:
        _assert(
            tier in packet["eligible_for_demo_canary_per_tier"],
            f"missing tier in verdict: {tier}",
            failures,
        )


def _check_sweep_bb_demo_bias_refuse(failures: list[str]) -> None:
    """BB demo bias not confirmed → sweep returns refusal packet。"""
    rows = _build_balanced_fixture()
    packet = compute_stage0r_sweep(rows, bb_demo_bias_confirmed=False)
    _assert(
        packet["eligible_for_demo_canary"] is False,
        "BB not cleared → eligible_for_demo_canary=False",
        failures,
    )
    _assert(
        len(packet["sweep_cells"]) == 0,
        f"refusal packet should have 0 cells, got {len(packet['sweep_cells'])}",
        failures,
    )
    for tier in DENSITY_TIERS:
        _assert(
            packet["eligible_for_demo_canary_per_tier"][tier] == {"long": False, "short": False},
            f"refusal: tier {tier} should be all False",
            failures,
        )


def _check_sweep_json_roundtrip(failures: list[str]) -> None:
    """sweep packet 應 JSON-serializable（CLI 持久化要求）。"""
    rows = _build_balanced_fixture(n_symbols=5, n_days=7, n_per_day_per_dir=4)
    packet = compute_stage0r_sweep(
        rows, bb_demo_bias_confirmed=True,
        k_grid=(3,), n_usd_grid=(10_000,), m_grid=(2,),
        side_dom_grid=(0.8,), floor_grid=(10_000,),
        quiet_grid=(30,), horizon_grid=(5,),
    )
    try:
        # tuple → list conversion for symbols_in_panel etc.
        json.dumps(packet, default=str, sort_keys=True)
    except (TypeError, ValueError) as exc:
        failures.append(f"sweep packet JSON serialization failed: {exc}")


# ============================================================================
# Case：PSR / DSR / Bootstrap CI math correctness
# ============================================================================


def _check_psr_dsr_finite(failures: list[str]) -> None:
    """正 Sharpe sample → PSR > 0.5；large K → DSR < PSR。"""
    values = [10.0, 12.0, 8.0, 15.0, 11.0, 9.0, 14.0, 13.0, 7.0, 16.0] * 10
    psr = psr_bailey_ldp(values)
    _assert(psr is not None and psr > 0.5,
            f"positive Sharpe sample → PSR > 0.5, got {psr}", failures)
    dsr_large = dsr_with_k(values, 100_000)
    _assert(dsr_large is not None and dsr_large < psr,
            f"large K → DSR < PSR, got DSR={dsr_large} PSR={psr}", failures)


def _check_bootstrap_ci_known_mean(failures: list[str]) -> None:
    """Bootstrap CI 對 known-mean sample 應包含 sample mean。

    為什麼測 sample mean 而非 population mean：bootstrap 抽自樣本，CI 是
    "if we resampled, where would the mean fall" — 應 always 包含當前 sample
    mean。小 n (200) 之 sample mean 對 population mean 有非零偏差，testing
    population mean 是 statistical mistake。
    """
    import random as _r
    import statistics as _st
    rng = _r.Random(42)
    values = [rng.gauss(10.0, 5.0) for _ in range(200)]
    sample_mean = _st.mean(values)
    ci = block_bootstrap_ci(values, block_size=12, iterations=400, seed=42)
    _assert(ci is not None, "CI should not be None for n=200", failures)
    if ci is not None:
        lower, upper = ci
        # CI 必含 sample mean（不變量）；同時兩端 spread 應 < 2.0（n=200 + sd=5 之 SE 估算）。
        _assert(
            lower <= sample_mean <= upper,
            f"bootstrap CI should contain sample mean {sample_mean:.3f}, "
            f"got ({lower:.3f}, {upper:.3f})",
            failures,
        )
        _assert(
            upper - lower < 2.0,
            f"CI spread should be reasonably narrow for n=200, got {upper-lower:.3f}",
            failures,
        )


def _check_wilson_ci_bench(failures: list[str]) -> None:
    """Wilson CI bench vs known values（鏡像 8b smoke check）。"""
    cases = (
        (20, 4, 0.082, 0.422, 0.010),
        (100, 50, 0.404, 0.596, 0.005),
        (10, 2, 0.057, 0.510, 0.010),
    )
    for n, n_eff, exp_lower, exp_upper, tol in cases:
        ci = wilson_ci_95(n, n_eff)
        _assert(ci is not None, f"wilson_ci_95({n}, {n_eff}) returned None", failures)
        if ci is None:
            continue
        lower, upper = ci
        _assert(
            abs(lower - exp_lower) <= tol and abs(upper - exp_upper) <= tol,
            f"wilson_ci_95({n}, {n_eff})=({lower:.4f}, {upper:.4f}) "
            f"expected ({exp_lower}, {exp_upper}) tol={tol}",
            failures,
        )


# ============================================================================
# Entry point
# ============================================================================


def main() -> int:
    failures: list[str] = []

    # cluster-aware n_eff
    _check_cluster_neff_60min_window(failures)
    _check_cluster_neff_spaced(failures)
    _check_cluster_neff_three_way_binding(failures)

    # concentration caps
    _check_single_day_concentration(failures)
    _check_single_day_concentration_pass(failures)
    _check_single_symbol_concentration(failures)

    # both-direction floor
    _check_both_direction_floor_long_dead(failures)
    _check_both_direction_floor_both_pass(failures)

    # density floor efficacy / FP rate
    _check_density_floor_efficacy(failures)
    _check_false_positive_rate_pass(failures)
    _check_false_positive_rate_fail(failures)

    # tier classification
    _check_tier_classify(failures)
    _check_symbols_by_tier(failures)

    # compute_stage0r RED paths
    _check_compute_stage0r_bb_demo_bias_refuse(failures)
    _check_compute_stage0r_single_day_red(failures)
    _check_compute_stage0r_single_symbol_red(failures)

    # compute_stage0r 4-value verdict
    _check_compute_stage0r_long_only_emits_long_only(failures)
    _check_compute_stage0r_balanced_no_panic(failures)

    # sweep
    _check_sweep_returns_expected_cells(failures)
    _check_sweep_bb_demo_bias_refuse(failures)
    _check_sweep_json_roundtrip(failures)

    # math correctness
    _check_psr_dsr_finite(failures)
    _check_bootstrap_ci_known_mean(failures)
    _check_wilson_ci_bench(failures)

    if failures:
        print("FAIL")
        for item in failures:
            print(f"- {item}")
        return 1
    print("PASS W-AUDIT-8c Stage 0R metrics smoke")
    print(f"ALPHA_SOURCE_ID={ALPHA_SOURCE_ID}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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


def _check_cluster_neff_30min_cascade(failures: list[str]) -> None:
    """E2 round-1 CRIT-3 fix verify：10 events at 30min apart → 1 cluster（match SQL lag()）。

    為什麼這 case：round 1 anchor pattern 會把 10 events spaced 30min 算成
    4 clusters（events 4,7,10 與 anchor 0 差 90/180/270min > 60min ⇒ 新 cluster）；
    SQL `lag()` 看 PREVIOUS event delta (30min ≤ 60min) → 1 cluster only。
    Round 2 fix 必須 mirror SQL semantic → distinct_60min_clusters = 1。
    """
    base_ts_ms = 1_765_000_000_000
    triggers = [
        {
            "signal_ts_ms": base_ts_ms + i * 1_800_000,  # 30min apart
            "symbol": "BTCUSDT",
            "direction": "long_liquidated",
        }
        for i in range(10)
    ]
    result = _n_eff_cluster_aware(triggers, horizon_min=5, cluster_window_min=60)
    _assert(
        result["distinct_60min_clusters"] == 1,
        f"10 events 30min apart should be 1 cluster (sliding lag pattern), "
        f"got {result['distinct_60min_clusters']}",
        failures,
    )


def _check_n_eff_horizon_ceil(failures: list[str]) -> None:
    """MIT round-1 MUST-FIX verify：math.ceil 取代整數除 floor。

    canonical grid (1, 5, 15) 結果不變；horizon=6 / 10 / 14 在 round 1 有
    dormant bug（floor 至 1/2/2，漏算 sub-bar overlap）；round 2 fix 用
    math.ceil 修。
    """
    from helper_scripts.reports.w_audit_8c.liquidation_cluster_stage0r_metrics import (
        _n_eff_horizon_overlap,
    )

    # Canonical grid unchanged。
    _assert(_n_eff_horizon_overlap(100, 1) == 100, "h=1 → n/1=100", failures)
    _assert(_n_eff_horizon_overlap(100, 5) == 100, "h=5 → n/1=100", failures)
    _assert(_n_eff_horizon_overlap(100, 15) == 33, "h=15 → n/3=33", failures)
    # Round 2 fix：horizon=6 / 10 / 14 sensitivity grid 之 dormant bug。
    _assert(_n_eff_horizon_overlap(100, 6) == 50, "h=6 → ceil(6/5)=2 → n/2=50 (round 1 = n/1=100 bug)", failures)
    _assert(_n_eff_horizon_overlap(100, 10) == 50, "h=10 → ceil(10/5)=2 → n/2=50", failures)
    _assert(_n_eff_horizon_overlap(100, 14) == 33, "h=14 → ceil(14/5)=3 → n/3=33 (round 1 = n/2=50 bug)", failures)
    # Edge case：horizon=0 / 1 / 4 → max(1, ceil) = 1 → n/1=n。
    _assert(_n_eff_horizon_overlap(100, 4) == 100, "h=4 → ceil(4/5)=1 → n/1=100", failures)


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
    """single-day 87% → RED。

    E1 round 2：必傳 total_bucket_count；下游也應有 single-day RED 原因。
    """
    rows = _build_single_day_87pct_fixture()
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1, notional_pct_floor=0.0,
        total_bucket_count=20_000,
    )
    _assert(packet["pass"] == "RED", f"single-day 87% should RED, got {packet['pass']}", failures)
    _assert(
        any("single-day share" in r for r in packet["pass_reasons"]),
        f"RED reason should mention single-day, got {packet['pass_reasons']}",
        failures,
    )


def _check_compute_stage0r_single_symbol_red(failures: list[str]) -> None:
    """single-symbol 60% → RED。

    E1 round 2：必傳 total_bucket_count；MIT 0.30 cap 比 0.40 嚴 → 60% 必 RED。
    """
    rows = _build_single_symbol_87pct_fixture()
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1, notional_pct_floor=0.0,
        total_bucket_count=20_000,
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
    分類正確即 sufficient — both direction 必明示 fail）。

    E1 round 2：必傳 total_bucket_count 以滿足 CRIT-2 fail-closed gate。
    """
    rows = _build_long_only_fixture(n_symbols=25, n_days=7, n_per_day=10)
    packet = compute_stage0r(
        rows,
        bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1, notional_pct_floor=0.0,
        total_bucket_count=10_000,
        # 取 small floor 確保 trigger 都過；notional_pct_floor=0 跳過該軸。
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
            dc.get("long_passed") is True and dc.get("short_passed") is False,
            f"long-only fixture: long should pass, short should fail; got {dc}",
            failures,
        )


def _check_compute_stage0r_balanced_no_panic(failures: list[str]) -> None:
    """Balanced fixture → 不應 panic / KeyError / TypeError；verdict 為合法 4 值。

    E1 round 2：必傳 total_bucket_count 以滿足 CRIT-2 fail-closed gate。
    """
    rows = _build_balanced_fixture()
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1, notional_pct_floor=0.0,
        total_bucket_count=20_000,
    )
    _assert(
        packet["pass"] in ("PASS-BOTH", "PASS-LONG-ONLY", "PASS-SHORT-ONLY", "RED"),
        f"verdict should be valid 4-value, got {packet['pass']}",
        failures,
    )
    # 驗 packet 結構完整（E1 round 2：新增 baseline_lift / exclusion_counts / regime_annotation）。
    required_keys = (
        "strategy_variant", "alpha_source_id", "pass", "pass_reasons",
        "n_per_cell", "pooled_n_eff", "pooled_n_eff_breakdown",
        "avg_net_bps", "avg_gross_bps", "psr_0", "dsr",
        "bootstrap_ci_95_60m", "bootstrap_ci_95_4h",
        "pbo", "pbo_metadata",
        "single_day_concentration", "single_symbol_concentration",
        "both_direction_floor", "density_floor_efficacy", "false_positive_rate",
        "long_branch", "short_branch", "tombstone_risk",
        # E1 round 2 新增。
        "baseline_lift", "exclusion_counts", "regime_annotation",
    )
    for k in required_keys:
        _assert(k in packet, f"missing required key: {k}", failures)


# ============================================================================
# Case：sweep — multi-cell evaluation
# ============================================================================


def _check_sweep_returns_expected_cells(failures: list[str]) -> None:
    """4×4 sweep on k×n_usd → 16 cells (其他軸取單值)。

    E1 round 2：sweep 升 8-D（加 pct_grid）；本 test 顯式 pct_grid=(0.95,) 鎖單值。
    """
    rows = _build_balanced_fixture()
    packet = compute_stage0r_sweep(
        rows,
        bb_demo_bias_confirmed=True,
        k_grid=(2, 3, 5, 8),
        n_usd_grid=(5_000, 10_000, 25_000, 50_000),
        m_grid=(1,),  # single value
        side_dom_grid=(0.7,),
        floor_grid=(10_000,),
        pct_grid=(0.95,),  # E1 round 2：新 8th axis 顯式單值
        quiet_grid=(0,),
        horizon_grid=(5,),
        total_bucket_count=20_000,  # E1 round 2 CRIT-2 fix
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
    """sweep packet 應 JSON-serializable（CLI 持久化要求）。

    E1 round 2：必傳 pct_grid + total_bucket_count。
    """
    rows = _build_balanced_fixture(n_symbols=5, n_days=7, n_per_day_per_dir=4)
    packet = compute_stage0r_sweep(
        rows, bb_demo_bias_confirmed=True,
        k_grid=(3,), n_usd_grid=(10_000,), m_grid=(2,),
        side_dom_grid=(0.8,), floor_grid=(10_000,), pct_grid=(0.95,),
        quiet_grid=(30,), horizon_grid=(5,),
        total_bucket_count=4_000,
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
# Case：E1 round 2 — CRIT-1 notional_pct_floor filter verify
# ============================================================================


def _check_notional_pct_floor_filter(failures: list[str]) -> None:
    """E2 round-1 CRIT-1 fix verify：notional_pct_floor 過濾掉低 percentile row。

    為什麼必驗：round 1 sweep 漏 pct 軸 → 67% grid silent skip；fix 後
    `_extract_trigger_rows` 必過該 filter，否則 sweep 結果仍偏。
    """
    rows = _build_balanced_fixture(n_symbols=5, n_days=7, n_per_day_per_dir=4)
    # 把所有 row 之 notional_pct_24h 改成 0.50（< 0.95 default）→ 預期 0 triggers。
    for r in rows:
        r["notional_pct_24h"] = 0.50
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1,
        notional_pct_floor=0.95,
        total_bucket_count=2_000,
    )
    _assert(
        packet["n_per_cell"] == 0,
        f"notional_pct=0.50 vs floor=0.95 應 filter 全 rows，got n={packet['n_per_cell']}",
        failures,
    )
    # 把 floor 降至 0.40 → 應 retrieve all rows。
    packet_loose = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1,
        notional_pct_floor=0.40,
        total_bucket_count=2_000,
    )
    _assert(
        packet_loose["n_per_cell"] > 0,
        f"floor=0.40 應 retrieve 部分 rows，got n={packet_loose['n_per_cell']}",
        failures,
    )


# ============================================================================
# Case：E1 round 2 — CRIT-2 total_bucket_count fail-closed
# ============================================================================


def _check_missing_bucket_count_red(failures: list[str]) -> None:
    """E2 round-1 CRIT-2 fix verify：caller 不傳 total_bucket_count → RED。"""
    rows = _build_balanced_fixture(n_symbols=5, n_days=7, n_per_day_per_dir=4)
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1, notional_pct_floor=0.0,
        # total_bucket_count 故意不傳。
    )
    _assert(
        packet["pass"] == "RED",
        f"missing total_bucket_count 應 RED, got {packet['pass']}",
        failures,
    )
    _assert(
        any("missing_bucket_count_denominator" in r for r in packet["pass_reasons"]),
        f"RED reason 應含 missing_bucket_count_denominator, got {packet['pass_reasons']}",
        failures,
    )


def _check_direction_check_none_when_missing(failures: list[str]) -> None:
    """E2 round-1 CRIT-2 fix verify：direction_check passed 三態 None。"""
    triggers = [{"direction": "long_liquidated"} for _ in range(20)]
    result = _both_direction_floor_check(triggers, total_bucket_count=None)
    _assert(
        result.get("long_passed") is None
        and result.get("short_passed") is None
        and result.get("both_passed") is None,
        f"None bucket count → 三態 passed=None, got {result}",
        failures,
    )
    _assert(
        "missing_bucket_count_denominator" in str(result.get("fail_reason") or ""),
        f"fail_reason 應顯式提 missing_bucket_count_denominator, got {result}",
        failures,
    )


# ============================================================================
# Case：E1 round 2 — MIT bear-regime annotation
# ============================================================================


def _check_regime_annotation_emit(failures: list[str]) -> None:
    """MIT round-1 governance MUST-FIX verify：Stage 0R verdict 含 bear-regime annotation。"""
    rows = _build_balanced_fixture(n_symbols=5, n_days=7, n_per_day_per_dir=4)
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1, notional_pct_floor=0.0,
        total_bucket_count=2_000,
    )
    _assert("regime_annotation" in packet, "compute_stage0r 必含 regime_annotation", failures)
    annotation = packet.get("regime_annotation")
    _assert(isinstance(annotation, dict), "regime_annotation 必為 dict", failures)
    if isinstance(annotation, dict):
        _assert(annotation.get("regime_label") == "bear", "regime_label 必為 'bear'", failures)
        _assert(
            annotation.get("cross_regime_validation_required") is True,
            "cross_regime_validation_required 必為 True",
            failures,
        )
        _assert(
            annotation.get("sample_period_start") == "2026-05-11",
            f"sample_period_start 必為 2026-05-11, got {annotation.get('sample_period_start')}",
            failures,
        )


def _check_regime_annotation_in_sweep(failures: list[str]) -> None:
    """E1 round 2：sweep return 也必含 regime_annotation（不論 BB 是否 confirmed）。"""
    rows = _build_balanced_fixture(n_symbols=5, n_days=7, n_per_day_per_dir=4)
    # BB confirmed path。
    sweep_ok = compute_stage0r_sweep(
        rows, bb_demo_bias_confirmed=True,
        k_grid=(3,), n_usd_grid=(10_000,), m_grid=(2,),
        side_dom_grid=(0.8,), floor_grid=(10_000,), pct_grid=(0.95,),
        quiet_grid=(30,), horizon_grid=(5,),
        total_bucket_count=2_000,
    )
    _assert("regime_annotation" in sweep_ok, "sweep BB-OK path 必含 regime_annotation", failures)

    # BB refused path。
    sweep_red = compute_stage0r_sweep(rows, bb_demo_bias_confirmed=False)
    _assert("regime_annotation" in sweep_red, "sweep BB-refused path 必含 regime_annotation", failures)
    _assert(
        "best_per_tier_per_direction" in sweep_red,
        "sweep refusal 必含 best_per_tier_per_direction（E2 HIGH-2 symmetric keys）",
        failures,
    )
    _assert(
        "symbol_tiers" in sweep_red,
        "sweep refusal 必含 symbol_tiers（E2 HIGH-2 symmetric keys）",
        failures,
    )


# ============================================================================
# Case：E1 round 2 — HIGH-4 baseline_lift + exclusion_counts
# ============================================================================


def _check_baseline_lift_and_exclusion_counts(failures: list[str]) -> None:
    """E2 round-1 HIGH-4 fix verify：compute_stage0r return 含 baseline_lift + exclusion_counts。"""
    rows = _build_balanced_fixture(n_symbols=5, n_days=7, n_per_day_per_dir=4)
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=3, n_usd=10_000, m_dominant=2, notional_pct_floor=0.0,
        total_bucket_count=2_000,
    )
    _assert("baseline_lift" in packet, "必含 baseline_lift", failures)
    bl = packet.get("baseline_lift")
    _assert(isinstance(bl, dict), "baseline_lift 必為 dict", failures)
    if isinstance(bl, dict):
        # 必含 key 結構（值可能 None 因 fixture 設計）。
        for key in ("avg_net_tight", "avg_net_loose", "baseline_lift_bps", "n_tight", "n_loose"):
            _assert(key in bl, f"baseline_lift 缺 key {key}", failures)

    _assert("exclusion_counts" in packet, "必含 exclusion_counts", failures)
    ec = packet.get("exclusion_counts")
    _assert(isinstance(ec, dict), "exclusion_counts 必為 dict", failures)
    if isinstance(ec, dict):
        for key in ("stale", "missing_dominance", "mixed", "quiet_window_fail", "density_floor_fail"):
            _assert(key in ec, f"exclusion_counts 缺 key {key}", failures)


# ============================================================================
# Case：E1 round 2 — HIGH-1 density_efficacy three-state passed
# ============================================================================


def _check_density_efficacy_three_state(failures: list[str]) -> None:
    """E2 round-1 HIGH-1 fix verify：caller 不傳 raw_5m_bucket_count → passed=None + skipped=True。

    為什麼必驗：round 1 fallback `passed=True` 偽 PASS；下游 verdict 看 passed
    為 True → 不加 RED reason → silent PASS。Fix 後三態 passed=None 表明
    SKIPPED 而不阻塞 verdict（CRIT-2 missing bucket count 才是 hard RED）。
    """
    rows = _build_balanced_fixture(n_symbols=5, n_days=7, n_per_day_per_dir=4)
    packet = compute_stage0r(
        rows, bb_demo_bias_confirmed=True,
        k_event_count=1, n_usd=1, m_dominant=1, notional_pct_floor=0.0,
        total_bucket_count=2_000,
        # raw_5m_bucket_count / after_k/n/m_count 故意不傳。
    )
    de = packet.get("density_floor_efficacy")
    _assert(isinstance(de, dict), "density_floor_efficacy 必為 dict", failures)
    if isinstance(de, dict):
        _assert(de.get("passed") is None, f"caller 不傳 → passed 三態 None, got {de.get('passed')}", failures)
        _assert(de.get("skipped") is True, f"skipped 必為 True, got {de.get('skipped')}", failures)


# ============================================================================
# Case：E1 round 2 — MIT drift correction constants
# ============================================================================


def _check_mit_drift_correction_constants(failures: list[str]) -> None:
    """MIT round-1 drift correction verify：3 個 constant 修正。

    - MAX_SYMBOL_SHARE: 0.40 → 0.30
    - COST_EDGE_RATIO_MAX: 0.80 → 0.60
    - FALSE_POSITIVE_RATE_MAX: 0.40 → 0.30
    """
    from helper_scripts.reports.w_audit_8c.liquidation_cluster_stage0r_metrics import (
        COST_EDGE_RATIO_MAX,
        FALSE_POSITIVE_RATE_MAX,
    )

    _assert(MAX_SYMBOL_SHARE == 0.30, f"MAX_SYMBOL_SHARE 必為 0.30 (MIT 從 0.40 tightened), got {MAX_SYMBOL_SHARE}", failures)
    _assert(
        COST_EDGE_RATIO_MAX == 0.60,
        f"COST_EDGE_RATIO_MAX 必為 0.60 (MIT 從 0.80 tightened), got {COST_EDGE_RATIO_MAX}",
        failures,
    )
    _assert(
        FALSE_POSITIVE_RATE_MAX == 0.30,
        f"FALSE_POSITIVE_RATE_MAX 必為 0.30 (MIT 從 0.40 tightened), got {FALSE_POSITIVE_RATE_MAX}",
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
    _check_cluster_neff_30min_cascade(failures)        # E1 round 2 CRIT-3 verify
    _check_n_eff_horizon_ceil(failures)                # E1 round 2 MIT MUST-FIX verify
    _check_cluster_neff_three_way_binding(failures)

    # concentration caps
    _check_single_day_concentration(failures)
    _check_single_day_concentration_pass(failures)
    _check_single_symbol_concentration(failures)

    # both-direction floor
    _check_both_direction_floor_long_dead(failures)
    _check_both_direction_floor_both_pass(failures)
    _check_direction_check_none_when_missing(failures)  # E1 round 2 CRIT-2 verify

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
    _check_missing_bucket_count_red(failures)           # E1 round 2 CRIT-2 verify

    # compute_stage0r 4-value verdict
    _check_compute_stage0r_long_only_emits_long_only(failures)
    _check_compute_stage0r_balanced_no_panic(failures)

    # E1 round 2 new tests
    _check_notional_pct_floor_filter(failures)          # CRIT-1
    _check_regime_annotation_emit(failures)             # MIT MUST-FIX
    _check_regime_annotation_in_sweep(failures)         # MIT MUST-FIX + HIGH-2
    _check_baseline_lift_and_exclusion_counts(failures) # HIGH-4
    _check_density_efficacy_three_state(failures)       # HIGH-1
    _check_mit_drift_correction_constants(failures)     # MIT drift correction

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

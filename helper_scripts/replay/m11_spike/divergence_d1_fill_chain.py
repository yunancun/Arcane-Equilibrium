"""
MODULE_NOTE
模塊用途：Sprint 1A-ζ Track C D1 fill_chain divergence detector (skeleton)
  - 7 種 divergence type (D1-D7) 之 D1 fill_chain
  - per M11 design spec §4.2 D1 + V107 spec §4.2 column 行為
  - spike scope 限 1 種 divergence type (per spike spec §2.3 C4)
  - 與 spike_trigger.py 共用 detect_d1_fill_chain;此 module 提供 detector API
    + 統計 baseline + leak-free shift(1) 對比 (per AC-7 mandate)
主要函數:
  - compute_5d_baseline(): 5d empirical mean / sigma per (strategy, symbol)
  - detect_with_baseline(): 用 5d baseline 評估 severity (NOISE/WARN/CRITICAL)
  - leak_free_shift1_replay(): 反向重算 fill chain (排除 current bar)
  - inject_synthetic_fixture(): 注入 synthetic divergence (spike 用)
依賴: psycopg2 (連線由 caller 注;detector module 純運算)
硬邊界:
  - D1 only;D2-D7 不在 spike scope (per spike spec §2.3 C4)
  - 5d baseline cold-start 時 fallback cohort median proxy (per
    m11_threshold_..._rename §2.5 + ADR-0038 Decision 3 cold start)
  - leak-free shift(1) 對齊 feedback_indicator_lookahead_bias mandate (per AC-7)
  - 不寫 PG (detector 純運算;writer 由 spike_trigger.py 負責)
治理對照: ADR-0038 Decision 3 + M11 design spec §4.2 D1 + AC-7 leak-free
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass
from typing import Any

LOG = logging.getLogger("m11_spike_d1_detector")


# 為什麼採 dataclass:統計 baseline 結構化 + audit-friendly
@dataclass(frozen=True)
class DivergenceBaseline:
    """5d empirical baseline for D1 fill_chain detector"""

    mean: float  # μ
    sigma: float  # σ
    noise_floor: float  # μ + 0.5σ (per ADR-0038 Decision 3)
    warn_threshold: float  # μ + 2.5σ
    critical_threshold: float  # μ + 3σ
    sample_size: int  # 樣本數
    cold_start: bool  # 樣本不足 (< 5d) 標記


def compute_5d_baseline(
    historical_fill_counts: list[int],
) -> DivergenceBaseline:
    """
    5d empirical baseline 計算 (per ADR-0038 Decision 3 + spec §2.1)

    為什麼採 5d window:
        sample reliability (≥ 5 sample for σ stable) vs regime
        responsiveness (≤ 7d for crypto regime shift) best 折衷;
        per m11_threshold_..._rename §2.4

    cold start handling:
        若樣本 < 5 → cold_start=True;threshold 用 cohort median proxy
        (此 skeleton 用簡化版:無歷史時 mean=0 sigma=1 寬鬆放行)
    """
    n = len(historical_fill_counts)
    cold_start = n < 5

    if n == 0:
        # 完全無 history;極端 cold start
        LOG.warning("0 historical sample;cold_start with relaxed thresholds")
        return DivergenceBaseline(
            mean=0.0,
            sigma=1.0,
            noise_floor=0.5,
            warn_threshold=2.5,
            critical_threshold=3.0,
            sample_size=0,
            cold_start=True,
        )

    mu = statistics.mean(historical_fill_counts)
    if n >= 2:
        sigma = statistics.stdev(historical_fill_counts)
    else:
        # 樣本 < 2 無法算 σ;放寬
        sigma = max(1.0, abs(mu) * 0.5)

    return DivergenceBaseline(
        mean=mu,
        sigma=sigma,
        noise_floor=mu + 0.5 * sigma,
        warn_threshold=mu + 2.5 * sigma,
        critical_threshold=mu + 3.0 * sigma,
        sample_size=n,
        cold_start=cold_start,
    )


def detect_with_baseline(
    live_count: int,
    replay_count: int,
    baseline: DivergenceBaseline,
) -> dict[str, Any]:
    """
    用 5d baseline 評估 severity (per V107 spec §4.3 D1 threshold)

    threshold (per spec §4.3 D1 absolute count):
        NOISE < ±2 fills
        WARN ±3-5 fills
        CRITICAL ≥ ±5 fills

    本 detector 同時提供:
        - absolute count threshold (per spec §4.3 D1)
        - σ-based threshold (per ADR-0038 Decision 3 + baseline)
    取兩者 max severity (保守 fail-closed per CLAUDE.md §二 原則 6)
    """
    divergence = replay_count - live_count
    abs_div = abs(divergence)

    # absolute count threshold (per spec §4.3 D1)
    if abs_div < 2:
        abs_severity = "NOISE"
    elif abs_div < 5:
        abs_severity = "WARN"
    else:
        abs_severity = "CRITICAL"

    # σ-based threshold (per ADR-0038 Decision 3)
    z_score = (
        (divergence - baseline.mean) / baseline.sigma if baseline.sigma > 0 else 0.0
    )
    abs_z = abs(z_score)
    if abs_z < 0.5:
        sigma_severity = "NOISE"
    elif abs_z < 2.5:
        sigma_severity = "NOISE"  # σ-based 中間階段歸 NOISE band
    elif abs_z < 3.0:
        sigma_severity = "WARN"
    else:
        sigma_severity = "CRITICAL"

    # 取兩者 max (per fail-closed 紀律)
    severity_rank = {"NOISE": 0, "WARN": 1, "CRITICAL": 2}
    if severity_rank[abs_severity] >= severity_rank[sigma_severity]:
        final_severity = abs_severity
    else:
        final_severity = sigma_severity

    # cold_start downgrade:per m11_threshold_..._rename §2.5
    # CRITICAL → WARN (baseline 不可信時不升 CRITICAL)
    if baseline.cold_start and final_severity == "CRITICAL":
        LOG.warning(
            "cold_start=true (sample=%s);downgrading CRITICAL to WARN per spec §2.5",
            baseline.sample_size,
        )
        final_severity = "WARN"

    return {
        "live_count": live_count,
        "replay_count": replay_count,
        "divergence_count": divergence,
        "abs_divergence": abs_div,
        "z_score": z_score,
        "severity": final_severity,
        "baseline_mean": baseline.mean,
        "baseline_sigma": baseline.sigma,
        "noise_floor_threshold": baseline.noise_floor,
        "warn_threshold": baseline.warn_threshold,
        "critical_threshold": baseline.critical_threshold,
        "cold_start": baseline.cold_start,
        "severity_origin": {
            "abs_count_based": abs_severity,
            "sigma_based": sigma_severity,
        },
    }


def leak_free_shift1_replay(
    fills: list[dict],
) -> int:
    """
    leak-free shift(1) baseline (per AC-7 + feedback_indicator_lookahead_bias mandate)

    為什麼必須:
        per feedback_indicator_lookahead_bias 2026-04-24 memory:
            rolling(N).max() 含 current bar → breach signal 必 mean-revert (artifact);
            任何 sweep/研究必並列 leak-free shift(1) 對比

    本 detector 用 shift(1) baseline:
        replay 重算只用「上一個 bar 之前」的 history;不引用 current bar;
        對 fill_chain count delta 用 N-1 samples (排除 latest fill);
        若 latest fill 是 spike → leak-free baseline 不被 spike 污染

    return: leak-free fill count baseline (N-1 sample;排除 latest fill)
    """
    if not fills:
        return 0
    # shift(1) 對 fill_chain count:排除最後一個 fill (current bar)
    return len(fills) - 1


def inject_synthetic_fixture(
    base_count: int,
    delta: int = 5,
) -> int:
    """
    spike 用:注入 synthetic divergence (per packet Task 2 step 3.D)

    delta=5 對應 CRITICAL threshold (≥ ±5 fills per spec §4.3 D1);
    走完 m7_decay_candidate routing path 是 dedup contract empirical 驗證
    所需的 evidence row
    """
    return base_count + delta

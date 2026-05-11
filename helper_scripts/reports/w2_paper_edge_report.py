#!/usr/bin/env python3
"""W2 A4-C BTC→Alt Lead-Lag — D+12 paper edge report 工具鏈。

MODULE_NOTE:
    Sprint N+1 W2 IMPL sub-task 4。對 D+12 paper engine 跑滿 7d 後的
    panel.btc_lead_lag_panel + trading.fills + trading.klines 三方資料，
    跑 spec §7.2 counterfactual SQL（``sql/queries/w2_btc_alt_lead_lag_counterfactual.sql``）
    再算 spec v1.2 §7.1 mandatory 6 metric + dual-layer σ + PSR(0)
    Bailey-López de Prado 2012 skew/kurt-aware formula + spec §8.1
    +15 / +5~15 / <+5 三檔 step gate verdict，輸出 markdown 報告。

    對齊：
      - spec v1.2 §7.1 mandatory metric set 6 條（pooled+per-symbol breakdown
        / DSR K=95 deflate / PSR(0) skew/kurt formula / alpha decay R²(N) /
        block-bootstrap 95% CI / per-cohort counterfactual delta）
      - spec v1.2 §7.1 acceptance prerequisite dual-layer σ：raw market σ_60=
        4.54 / σ_120=6.28 / σ_300=10.08 bps + net edge σ=50-80 bps EDGE-DIAG-1
        baseline；強制：power calculation 用 net edge σ，禁用 raw market σ
      - spec v1.2 §8.1 三檔 gate：+15 promote N+2 / +5~+15 extend 14d /
        <+5 revise spec or archive
      - spec §9 condition #5：regime_tag='extreme' 排除（FILTER WHERE
        regime_tag='normal'），不計入 7d edge avg

    純 READ-ONLY：無寫操作；輸出 markdown 到 docs/CCAgentWorkSpace/PA/workspace/
    reports/YYYY-MM-DD--w2_paper_edge_report.md（D+12 land）。psycopg2
    lazy-import 進 main()（避 --smoke-test 需要真連 PG，per CLAUDE.md §七）。

    PSR(0) 強制公式（per spec v1.2 §7.1 metric (3) + MIT C-3 verify）：
        PSR(0) = Φ((SR - 0) × √(n - 1) /
                   √(1 - skew·SR + ((kurt - 1) / 4)·SR²))
        - Φ = standard normal CDF
        - SR = annualized Sharpe（per-symbol 算）
        - n = sample size
        - skew + kurt = 7d empirical estimate
        - threshold ≥ 0.95
        - 禁用 normal SR z-test
      Reference: Bailey, D. H., & López de Prado, M. (2012).
                 "The Sharpe Ratio Efficient Frontier"。
                 Journal of Risk, 15(2), 13-44.

    DSR with K=95 deflate（per spec §7.1 metric (2) + v1.1 condition #1）：
        mu_0 = √(2 ln K)，K = 95（active strategy×symbol cell 總數）
        DSR = Φ((SR - mu_0) × √(n - 1) /
                √(1 - skew·SR + ((kurt - 1) / 4)·SR²))
        threshold ≥ 0.95（PASS）
      Reference: Bailey, D. H., & López de Prado, M. (2014).
                 "The Deflated Sharpe Ratio"。 §4.2 DSR with multiple trial。

Usage / 用法：

    # Default — 預設 read live PG，寫 docs/CCAgentWorkSpace/PA/workspace/reports/
    python3 helper_scripts/reports/w2_paper_edge_report.py

    # Dry-run（不寫檔，stdout only）
    python3 helper_scripts/reports/w2_paper_edge_report.py --dry-run

    # Smoke test（不連 PG，跑內建 mock fixture 驗 metric 公式 + gate verdict）
    python3 helper_scripts/reports/w2_paper_edge_report.py --smoke-test

    # 自訂 window / cohort
    python3 helper_scripts/reports/w2_paper_edge_report.py \\
        --window-days 14 \\
        --cohort ETHUSDT,SOLUSDT,XRPUSDT

    # 自訂輸出
    python3 helper_scripts/reports/w2_paper_edge_report.py --out /tmp/w2.md
"""

from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

# ============================================================
# 常數（per spec v1.2）
# ============================================================

# DSR multiple trial K（per spec §7.1 metric (2) + v1.1 condition #1）。
# K = active strategy×symbol cell 總數（per Bailey-López de Prado 2014 §4.2）。
DSR_K_MULTIPLE_TRIAL = 95

# Dual-layer σ acceptance（per spec v1.2 §7.1 prerequisite + MIT C-3 verify）。
# Raw market σ — 用於 alpha decay R²(N) baseline + price horizon scaling。
RAW_MARKET_SIGMA_60S_BPS = 4.54
RAW_MARKET_SIGMA_120S_BPS = 6.28
RAW_MARKET_SIGMA_300S_BPS = 10.08
# Net edge σ — 用於 paper edge gate power calculation + PSR(0) deflation。
NET_EDGE_SIGMA_LOWER_BPS = 50.0
NET_EDGE_SIGMA_UPPER_BPS = 80.0
NET_EDGE_SIGMA_MID_BPS = 65.0  # 中位點 hint（per cross_asset/mod.rs 對齊）

# Spec §8.1 三檔 gate（per v1.1 condition #5 + v1.2 power verification）。
GATE_PLUS_15_BPS = 15.0  # promote N+2 demo IMPL
GATE_PLUS_5_BPS = 5.0    # extend paper window 14d 邊界（≥ +5 < +15）

# Per-symbol gate（per spec §7.1 metric (1) + v1.1 condition #4 (1)）。
PER_SYMBOL_N_MIN = 100     # per-symbol sample n ≥ 100 fills
PER_SYMBOL_T_MIN = 2.0     # per-symbol t-stat > 2.0

# Block-bootstrap config（per spec §7.1 metric (5) + QC 5 conditions #4(e)）。
BOOTSTRAP_BLOCK_SIZE_MINUTES = 60     # block_size = 60min（對齊 BTC autocorr scale）
BOOTSTRAP_ITERATIONS = 1000           # 1000 iter

# DSR / PSR threshold（per spec §7.1 metric (2) + (3)）。
PSR_THRESHOLD = 0.95
DSR_THRESHOLD = 0.95

# Smoke-test 預設 cohort（per spec §2.2 7-symbol cohort）。
DEFAULT_COHORT = (
    "ETHUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT",
)
DEFAULT_WINDOW_DAYS = 7


# ============================================================
# DB connection helper（mirror passive_wait_healthcheck pattern）
# ============================================================


def _get_conn():
    """建 psycopg2 connection（優先 OPENCLAW_DATABASE_URL，否則 POSTGRES_* 五件組）。"""
    import psycopg2  # type: ignore

    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


def _read_counterfactual_sql() -> str:
    """讀 sql/queries/w2_btc_alt_lead_lag_counterfactual.sql。

    路徑解析：OPENCLAW_BASE_DIR → repo root；fallback 到 __file__ parent.parent.parent
    """
    base = os.environ.get("OPENCLAW_BASE_DIR")
    if not base:
        # __file__ 在 helper_scripts/reports/，往上三層到 srv/
        base = str(Path(__file__).resolve().parent.parent.parent)
    sql_path = Path(base) / "sql" / "queries" / "w2_btc_alt_lead_lag_counterfactual.sql"
    if not sql_path.exists():
        raise FileNotFoundError(
            f"counterfactual SQL not found at {sql_path}; "
            "expected sql/queries/w2_btc_alt_lead_lag_counterfactual.sql"
        )
    return sql_path.read_text(encoding="utf-8")


# ============================================================
# 統計 helper — pure Python (no numpy/scipy dependency, MUST cross-platform)
# ============================================================


def _normal_cdf(x: float) -> float:
    """Standard normal CDF Φ(x)。

    用 math.erf 實作；無 scipy.stats 依賴（cross-platform Mac+Linux）。
    Φ(x) = 0.5 * (1 + erf(x / √2))
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _safe_mean(values: Sequence[float]) -> Optional[float]:
    """Safe mean，過濾 None/NaN/inf；空集回 None。"""
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if not clean:
        return None
    return statistics.mean(clean)


def _safe_stdev(values: Sequence[float]) -> Optional[float]:
    """Safe sample stdev，n≥2 才回；過濾 None/NaN/inf。"""
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if len(clean) < 2:
        return None
    return statistics.stdev(clean)


def _skewness(values: Sequence[float]) -> Optional[float]:
    """7d empirical skewness（biased moment estimator）。

    skew = (1/n) Σ ((x_i - μ) / σ)³
    若 n<3 或 σ=0 → None
    """
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < 3:
        return None
    mu = statistics.mean(clean)
    var = sum((v - mu) ** 2 for v in clean) / n
    if var <= 0:
        return None
    sigma = math.sqrt(var)
    skew = sum(((v - mu) / sigma) ** 3 for v in clean) / n
    return skew


def _kurtosis(values: Sequence[float]) -> Optional[float]:
    """7d empirical kurtosis (raw, not excess kurtosis)。

    kurt = (1/n) Σ ((x_i - μ) / σ)⁴
    若 n<4 或 σ=0 → None
    注意：PSR formula 用 raw kurtosis（不是 excess kurtosis = kurt − 3）
    spec v1.2 §7.1 metric (3) formula 中的 "(kurt - 1) / 4" 用 raw kurt。
    """
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < 4:
        return None
    mu = statistics.mean(clean)
    var = sum((v - mu) ** 2 for v in clean) / n
    if var <= 0:
        return None
    sigma = math.sqrt(var)
    kurt = sum(((v - mu) / sigma) ** 4 for v in clean) / n
    return kurt


def compute_t_stat(values: Sequence[float], h0_mu: float = 0.0) -> Optional[float]:
    """one-sample t-statistic against H0: μ = h0_mu。

    t = (mean - h0_mu) / (stdev / √n)
    若 n<2 或 stdev=0 → None
    """
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < 2:
        return None
    mean = statistics.mean(clean)
    sd = statistics.stdev(clean)
    if sd == 0:
        return None
    return (mean - h0_mu) / (sd / math.sqrt(n))


def compute_psr_bailey_lopez_de_prado_2012(
    values: Sequence[float],
    sr_benchmark: float = 0.0,
) -> Optional[float]:
    """PSR(SR*) — Bailey & López de Prado 2012 skew/kurt-aware formula。

    PSR(SR*) = Φ((SR_hat - SR*) × √(n - 1) /
                 √(1 - skew·SR_hat + ((kurt - 1) / 4)·SR_hat²))

    Args:
        values: per-tick / per-fill net_edge bps samples
        sr_benchmark: H0 benchmark Sharpe（spec §7.1 metric (3) PSR(0) → 0.0；
                       DSR 走 mu_0 = √(2 ln K)）

    Returns:
        Φ-CDF probability ∈ [0, 1]；若資料不足或 σ=0 → None

    強制：禁用 normal SR z-test（per spec v1.2 §7.1 metric (3) per MIT C-3 verify）
    Reference:
        Bailey, D. H., & López de Prado, M. (2012). "The Sharpe Ratio
        Efficient Frontier"。 Journal of Risk, 15(2), 13-44.

    注意（per spec §7.1 v1.2 公式）：本端 SR_hat 為 sample non-annualized SR
        = mean(values) / stdev(values)；caller 若需 annualized SR 自行 × √T。
        D+12 paper edge report 走 per-sample bps net_edge → sample-SR 對齊
        spec power calculation 公式，不再 × annualize factor。
    """
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < 4:  # 需 n≥4 算 skew + kurt
        return None
    mean = statistics.mean(clean)
    sd = statistics.stdev(clean)
    if sd == 0:
        return None
    sr_hat = mean / sd
    skew = _skewness(clean)
    kurt = _kurtosis(clean)
    if skew is None or kurt is None:
        return None
    # PSR denominator: √(1 - skew·SR_hat + ((kurt - 1) / 4)·SR_hat²)
    denom_sq = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * (sr_hat ** 2)
    if denom_sq <= 0:
        # denominator 不正（極端 skew + 高 SR 組合），spec acceptance 視為 fail
        return None
    denom = math.sqrt(denom_sq)
    # numerator
    z = (sr_hat - sr_benchmark) * math.sqrt(n - 1) / denom
    return _normal_cdf(z)


def compute_dsr_with_k_deflate(
    values: Sequence[float],
    k_trials: int = DSR_K_MULTIPLE_TRIAL,
) -> Optional[float]:
    """DSR — Deflated Sharpe Ratio with K trials deflation。

    mu_0 = √(2 ln K)；DSR = PSR(mu_0)。
    K = 95 per spec v1.1 condition #1（active strategy×symbol cell 總數，per
    Bailey-López de Prado 2014 §4.2 DSR with multiple trial）。

    Args:
        values: per-tick / per-fill net_edge bps samples
        k_trials: 多重 trial 修正參數，default = 95

    Returns:
        Φ-CDF probability ∈ [0, 1]；若資料不足 → None
    """
    if k_trials <= 1:
        return None
    mu_0 = math.sqrt(2.0 * math.log(k_trials))
    return compute_psr_bailey_lopez_de_prado_2012(values, sr_benchmark=mu_0)


def compute_block_bootstrap_ci(
    values: Sequence[float],
    block_size: int = BOOTSTRAP_BLOCK_SIZE_MINUTES,
    iterations: int = BOOTSTRAP_ITERATIONS,
    confidence: float = 0.95,
    seed: int = 20260512,  # deterministic seed for reproducibility
) -> Optional[tuple[float, float]]:
    """Block-bootstrap 95% CI for mean(values)。

    per spec §7.1 metric (5) + QC 5 conditions #4(e)：
      - block_size = 60min（對齊 BTC autocorr scale）
      - iterations = 1000
      - 95% CI

    Args:
        values: per-tick / per-fill net_edge bps samples（時間排序）
        block_size: block 長度（樣本單位；1m grain 下 60min = 60 sample）
        iterations: bootstrap iteration 次數
        confidence: CI 信心水準
        seed: deterministic random seed（spec 重現性）

    Returns:
        (ci_lower, ci_upper)；若資料不足 → None

    注意：本端為 moving-block bootstrap（per Künsch 1989）；對 stationary
    bootstrap 偏好可用 random block length，但 spec §7.1 metric (5)
    明定 block_size=60min fixed，固跑 moving-block。
    """
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < block_size:
        return None  # 樣本不足一個 block
    rng = random.Random(seed)
    n_blocks_per_iter = max(1, n // block_size)
    boot_means: list[float] = []
    for _ in range(iterations):
        # 抽 n_blocks_per_iter 個 block，每個 block 起點 ∈ [0, n - block_size]
        sample: list[float] = []
        for _b in range(n_blocks_per_iter):
            start = rng.randint(0, n - block_size)
            sample.extend(clean[start:start + block_size])
        # truncate 到 n 長度（避免 overshoot 影響 mean weight）
        boot_means.append(statistics.mean(sample[:n]))
    boot_means.sort()
    lower_idx = int((1.0 - confidence) / 2.0 * iterations)
    upper_idx = int((1.0 + confidence) / 2.0 * iterations) - 1
    lower_idx = max(0, min(iterations - 1, lower_idx))
    upper_idx = max(0, min(iterations - 1, upper_idx))
    return (boot_means[lower_idx], boot_means[upper_idx])


def compute_alpha_decay_r_squared(
    btc_returns: Sequence[float],
    alt_forward_returns: Sequence[float],
) -> Optional[float]:
    """alpha decay R²(N) — BTC lead return → alt forward return 的 OLS R²。

    對齊 spec §7.1 metric (4)：R²(N=60/120/300) 三檔 decay curve
    本 helper 算單一檔 N 的 R²；caller 三次呼叫覆 60/120/300。

    R² = 1 - SS_res / SS_tot
    SS_res = Σ (y_i - ŷ_i)²
    SS_tot = Σ (y_i - ȳ)²
    ŷ = β₀ + β₁ × x
    β₁ = Cov(x, y) / Var(x)
    β₀ = ȳ - β₁ × x̄

    Args:
        btc_returns: BTC lead return bps sample
        alt_forward_returns: 對齊 alt forward return bps sample

    Returns:
        R² ∈ [0, 1]；若資料不足 / Var(x)=0 → None
    """
    pairs = [
        (x, y) for x, y in zip(btc_returns, alt_forward_returns)
        if x is not None and y is not None
        and math.isfinite(x) and math.isfinite(y)
    ]
    if len(pairs) < 4:
        return None
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    x_mean = statistics.mean(xs)
    y_mean = statistics.mean(ys)
    var_x = sum((x - x_mean) ** 2 for x in xs)
    if var_x == 0:
        return None
    cov_xy = sum((x - x_mean) * (y - y_mean) for x, y in pairs)
    beta_1 = cov_xy / var_x
    beta_0 = y_mean - beta_1 * x_mean
    ss_res = sum((y - (beta_0 + beta_1 * x)) ** 2 for x, y in pairs)
    ss_tot = sum((y - y_mean) ** 2 for y in ys)
    if ss_tot == 0:
        return None
    return max(0.0, 1.0 - ss_res / ss_tot)


# ============================================================
# Step gate verdict（per spec v1.2 §8.1 三檔）
# ============================================================


def step_gate_verdict(
    avg_net_bps: Optional[float],
    t_stat: Optional[float],
    sample_n: int,
) -> dict:
    """三檔 gate verdict（per spec v1.2 §8.1）。

    決策層級：
      - ≥ +15 bps + t > 2.0 + n ≥ 100 → "plus15"（promote N+2 demo IMPL）
      - +5 ≤ avg < +15 → "plus5_15"（extend paper window 14d 重評）
      - < +5 bps → "minus5"（revise spec 或 archive）
      - 無樣本 / underpowered → "no_signal"
    """
    if avg_net_bps is None or t_stat is None:
        return {
            "label": "no_signal",
            "reason": "insufficient sample / undefined t-stat",
            "promote_n2": False,
        }
    # promote 路徑：spec §7.1 metric (1) per-symbol gate（n ≥ 100 + t > 2.0）
    underpowered = (sample_n < PER_SYMBOL_N_MIN or t_stat <= PER_SYMBOL_T_MIN)
    if avg_net_bps >= GATE_PLUS_15_BPS:
        if underpowered:
            return {
                "label": "plus15",
                "reason": (
                    f"avg_net ≥ +15 bps but underpowered "
                    f"(n={sample_n}<{PER_SYMBOL_N_MIN} or t={t_stat:.3f}≤{PER_SYMBOL_T_MIN})"
                    " → cannot promote without n + t gate"
                ),
                "promote_n2": False,
            }
        return {
            "label": "plus15",
            "reason": (
                f"avg_net = {avg_net_bps:.2f} bps ≥ +15 + n={sample_n}≥100 "
                f"+ t={t_stat:.3f}>2.0 → promote N+2 demo IMPL"
            ),
            "promote_n2": True,
        }
    if avg_net_bps >= GATE_PLUS_5_BPS:
        return {
            "label": "plus5_15",
            "reason": (
                f"avg_net = {avg_net_bps:.2f} bps ∈ [+5, +15) → extend paper "
                f"window 14d 重評 (n={sample_n}, t={t_stat:.3f})"
            ),
            "promote_n2": False,
        }
    return {
        "label": "minus5",
        "reason": (
            f"avg_net = {avg_net_bps:.2f} bps < +5 → revise spec 或 archive"
            f" (n={sample_n}, t={t_stat:.3f})"
        ),
        "promote_n2": False,
    }


# ============================================================
# Per-symbol + pooled metric 計算（per spec §7.1 mandatory 6 條）
# ============================================================


def _select_forward_window_field(
    row: dict,
    window_secs: int,
) -> Optional[float]:
    """根據 lead_window_secs (60/120/300) 取對應的 cf_net_edge / alt_forward_return。"""
    if window_secs == 60:
        return row.get("cf_net_edge_60s_bps")
    if window_secs == 120:
        return row.get("cf_net_edge_120s_bps")
    if window_secs == 300:
        return row.get("cf_net_edge_300s_bps")
    return None


def _alt_forward_return_field(
    row: dict,
    window_secs: int,
) -> Optional[float]:
    """根據 N (60/120/300) 取 alt_forward_return_*_bps。"""
    if window_secs == 60:
        return row.get("alt_forward_return_60s_bps")
    if window_secs == 120:
        return row.get("alt_forward_return_120s_bps")
    if window_secs == 300:
        return row.get("alt_forward_return_300s_bps")
    return None


def _btc_lead_return_field(row: dict, window_secs: int) -> Optional[float]:
    """根據 N (60/120/300) 取 btc_lead_return_pct_*。"""
    if window_secs == 60:
        return row.get("btc_lead_return_pct_60s")
    if window_secs == 120:
        return row.get("btc_lead_return_pct")
    if window_secs == 300:
        return row.get("btc_lead_return_pct_300s")
    return None


def compute_per_symbol_metrics(
    rows: list[dict],
    primary_window_secs: int = 120,
) -> dict[str, dict]:
    """spec §7.1 metric (1)：per-symbol breakdown。

    per spec：per-symbol n ≥ 100 + per-symbol t > 2.0 才允許單 symbol promote。
    本端對 cohort 內每 symbol 算 avg_net_bps / stdev / sample n / t-stat /
    PSR(0) / DSR / block-bootstrap 95% CI / counterfactual delta。

    regime filter：FILTER (regime_tag = 'normal')（per spec §7.2 + §9 condition #5）。

    Args:
        rows: counterfactual SQL 回傳的 dict rows
        primary_window_secs: 主信號 N（default 120）

    Returns:
        dict[symbol -> metrics_dict]
    """
    out: dict[str, dict] = {}
    # group by symbol
    by_symbol: dict[str, list[dict]] = {}
    for r in rows:
        sym = r.get("symbol")
        if sym is None:
            continue
        by_symbol.setdefault(sym, []).append(r)

    for sym, sym_rows in by_symbol.items():
        # filter normal regime（per spec §9 condition #5）
        normal_rows = [r for r in sym_rows if r.get("regime_tag") == "normal"]
        extreme_n = sum(1 for r in sym_rows if r.get("regime_tag") == "extreme")
        cf_values_primary = [
            v for v in (_select_forward_window_field(r, primary_window_secs)
                        for r in normal_rows)
            if v is not None
        ]
        sample_n = len(cf_values_primary)
        avg_net = _safe_mean(cf_values_primary)
        std_net = _safe_stdev(cf_values_primary)
        t_stat = compute_t_stat(cf_values_primary)
        psr_0 = compute_psr_bailey_lopez_de_prado_2012(cf_values_primary, sr_benchmark=0.0)
        dsr = compute_dsr_with_k_deflate(cf_values_primary, k_trials=DSR_K_MULTIPLE_TRIAL)
        ci = compute_block_bootstrap_ci(
            cf_values_primary,
            block_size=BOOTSTRAP_BLOCK_SIZE_MINUTES,
            iterations=BOOTSTRAP_ITERATIONS,
        )
        # spec §7.1 metric (6): per-cohort-symbol counterfactual delta
        # cf_long_avg = E[forward_return | expected_dir=+1]（spec §7.2）
        long_rows = [r for r in normal_rows if r.get("expected_dir") == 1]
        short_rows = [r for r in normal_rows if r.get("expected_dir") == -1]
        no_sig_rows = [r for r in normal_rows if r.get("expected_dir") == 0]
        cf_long_avg = _safe_mean([
            v for v in (_alt_forward_return_field(r, primary_window_secs) for r in long_rows)
            if v is not None
        ])
        cf_short_avg = _safe_mean([
            v for v in (_alt_forward_return_field(r, primary_window_secs) for r in short_rows)
            if v is not None
        ])
        cf_no_sig_baseline = _safe_mean([
            v for v in (_alt_forward_return_field(r, primary_window_secs) for r in no_sig_rows)
            if v is not None
        ])
        # spec §7.1 metric (4): alpha decay R²(N=60/120/300)
        r_sq_decay: dict[int, Optional[float]] = {}
        for ws in (60, 120, 300):
            btc_rets = [_btc_lead_return_field(r, ws) for r in normal_rows]
            alt_rets = [_alt_forward_return_field(r, ws) for r in normal_rows]
            r_sq_decay[ws] = compute_alpha_decay_r_squared(btc_rets, alt_rets)
        verdict = step_gate_verdict(avg_net, t_stat, sample_n)

        out[sym] = {
            "symbol": sym,
            "sample_n": sample_n,
            "raw_rows_n": len(sym_rows),
            "extreme_regime_n": extreme_n,
            "long_n": len(long_rows),
            "short_n": len(short_rows),
            "no_signal_n": len(no_sig_rows),
            "avg_net_bps": avg_net,
            "stdev_bps": std_net,
            "t_stat": t_stat,
            "psr_0": psr_0,
            "dsr_k95": dsr,
            "ci_95_low": ci[0] if ci else None,
            "ci_95_high": ci[1] if ci else None,
            "cf_long_avg_bps": cf_long_avg,
            "cf_short_avg_bps": cf_short_avg,
            "cf_no_signal_baseline_bps": cf_no_sig_baseline,
            "r_squared_60s": r_sq_decay[60],
            "r_squared_120s": r_sq_decay[120],
            "r_squared_300s": r_sq_decay[300],
            "verdict": verdict,
        }
    return out


def compute_pooled_metrics(
    rows: list[dict],
    primary_window_secs: int = 120,
) -> dict:
    """spec §7.1 metric (1)：pooled across all cohort symbols。

    用 normal regime row（per §9 condition #5）。
    """
    normal_rows = [r for r in rows if r.get("regime_tag") == "normal"]
    extreme_n = sum(1 for r in rows if r.get("regime_tag") == "extreme")
    cf_values = [
        v for v in (_select_forward_window_field(r, primary_window_secs) for r in normal_rows)
        if v is not None
    ]
    sample_n = len(cf_values)
    avg_net = _safe_mean(cf_values)
    std_net = _safe_stdev(cf_values)
    t_stat = compute_t_stat(cf_values)
    psr_0 = compute_psr_bailey_lopez_de_prado_2012(cf_values, sr_benchmark=0.0)
    dsr = compute_dsr_with_k_deflate(cf_values, k_trials=DSR_K_MULTIPLE_TRIAL)
    ci = compute_block_bootstrap_ci(
        cf_values,
        block_size=BOOTSTRAP_BLOCK_SIZE_MINUTES,
        iterations=BOOTSTRAP_ITERATIONS,
    )
    # alpha decay R²(N)
    r_sq_decay: dict[int, Optional[float]] = {}
    for ws in (60, 120, 300):
        btc_rets = [_btc_lead_return_field(r, ws) for r in normal_rows]
        alt_rets = [_alt_forward_return_field(r, ws) for r in normal_rows]
        r_sq_decay[ws] = compute_alpha_decay_r_squared(btc_rets, alt_rets)
    verdict = step_gate_verdict(avg_net, t_stat, sample_n)
    return {
        "sample_n": sample_n,
        "raw_rows_n": len(rows),
        "extreme_regime_n": extreme_n,
        "avg_net_bps": avg_net,
        "stdev_bps": std_net,
        "t_stat": t_stat,
        "psr_0": psr_0,
        "dsr_k95": dsr,
        "ci_95_low": ci[0] if ci else None,
        "ci_95_high": ci[1] if ci else None,
        "r_squared_60s": r_sq_decay[60],
        "r_squared_120s": r_sq_decay[120],
        "r_squared_300s": r_sq_decay[300],
        "verdict": verdict,
    }


# ============================================================
# Markdown render
# ============================================================


def _fmt(value: Any, fmt: str = ".4f") -> str:
    """Safe format - 把 None / NaN / inf 渲染為 '-'。"""
    if value is None:
        return "-"
    if isinstance(value, float) and not math.isfinite(value):
        return "-"
    try:
        return format(value, fmt)
    except (TypeError, ValueError):
        return str(value)


def render_markdown(
    pooled: dict,
    per_symbol: dict[str, dict],
    window_days: int,
    cohort: Sequence[str],
    timestamp: datetime,
) -> str:
    """渲染 D+12 paper edge report markdown。

    對應 spec v1.2 §7.1 mandatory metric 6 條全 land + dual-layer σ acceptance
    + PSR(0) skew/kurt formula + +15 bps gate power verification σ_net=50/80。
    """
    lines: list[str] = []
    lines.append("# W2 A4-C BTC→Alt Lead-Lag — D+12 Paper Edge Report")
    lines.append("")
    lines.append(
        f"**生成時間**: {timestamp.isoformat()}  "
        f"**Window**: {window_days} days  "
        f"**Cohort size**: {len(cohort)}"
    )
    lines.append(
        f"**Cohort symbols**: {', '.join(cohort)}"
    )
    lines.append("")
    lines.append("**Spec reference**:")
    lines.append("- v1.2 §7.1 mandatory metric 6 條（pooled + per-symbol / DSR K=95 / "
                 "PSR(0) skew/kurt / R²(N) decay / block-bootstrap 95% CI / counterfactual delta）")
    lines.append("- v1.2 §7.1 dual-layer σ：raw market σ_60=4.54/σ_120=6.28/σ_300=10.08 bps "
                 f"+ net edge σ={NET_EDGE_SIGMA_LOWER_BPS:.0f}-{NET_EDGE_SIGMA_UPPER_BPS:.0f} bps")
    lines.append("- v1.2 §8.1 三檔 gate：+15 promote N+2 / +5~+15 extend 14d / <+5 revise/archive")
    lines.append("- v1.2 §7.1 metric (3) PSR(0)：Bailey-López de Prado 2012 skew/kurt-aware "
                 "formula 強制（禁 normal SR z-test）")
    lines.append("")
    lines.append(
        "**PSR(0) 公式**：`PSR(0) = Φ((SR_hat - 0) × √(n-1) / "
        "√(1 - skew·SR_hat + ((kurt-1)/4)·SR_hat²))`"
    )
    lines.append("")

    # ============================================================
    # §1 Pooled metrics
    # ============================================================
    lines.append("## §1 Pooled metrics（cross-symbol aggregate）")
    lines.append("")
    lines.append("| Metric | Value | 解讀 |")
    lines.append("|---|---|---|")
    lines.append(
        f"| Sample n (normal regime) | {pooled['sample_n']} | "
        f"raw rows = {pooled['raw_rows_n']}, extreme = {pooled['extreme_regime_n']} |"
    )
    lines.append(f"| avg_net_bps | {_fmt(pooled['avg_net_bps'], '.4f')} | 平均反事實 net edge bps |")
    lines.append(f"| stdev (bps) | {_fmt(pooled['stdev_bps'], '.4f')} | "
                 f"net edge σ（對齊 dual-layer σ 範圍 [50, 80]）|")
    lines.append(f"| t-stat | {_fmt(pooled['t_stat'], '.4f')} | H0: μ=0；t>2.0 為信號顯著 |")
    lines.append(f"| PSR(0) | {_fmt(pooled['psr_0'], '.4f')} | "
                 f"Bailey-LdP 2012 skew/kurt-aware；threshold ≥ 0.95 → "
                 f"{'PASS' if pooled.get('psr_0') is not None and pooled['psr_0'] >= PSR_THRESHOLD else 'FAIL'} |")
    lines.append(f"| DSR (K=95) | {_fmt(pooled['dsr_k95'], '.4f')} | "
                 f"mu_0=√(2 ln 95)=3.018；threshold ≥ 0.95 → "
                 f"{'PASS' if pooled.get('dsr_k95') is not None and pooled['dsr_k95'] >= DSR_THRESHOLD else 'FAIL'} |")
    lines.append(
        f"| 95% block-bootstrap CI | "
        f"[{_fmt(pooled['ci_95_low'], '.4f')}, {_fmt(pooled['ci_95_high'], '.4f')}] | "
        f"block_size={BOOTSTRAP_BLOCK_SIZE_MINUTES}min, "
        f"{BOOTSTRAP_ITERATIONS} iter |"
    )
    lines.append("")
    lines.append("### Alpha decay R²(N=60/120/300) — pooled")
    lines.append("")
    lines.append("| N (secs) | R²(N) | raw market σ baseline (bps) |")
    lines.append("|---|---|---|")
    lines.append(
        f"| 60 | {_fmt(pooled['r_squared_60s'], '.4f')} | "
        f"{RAW_MARKET_SIGMA_60S_BPS:.2f} |"
    )
    lines.append(
        f"| 120 (主信號) | {_fmt(pooled['r_squared_120s'], '.4f')} | "
        f"{RAW_MARKET_SIGMA_120S_BPS:.2f} |"
    )
    lines.append(
        f"| 300 | {_fmt(pooled['r_squared_300s'], '.4f')} | "
        f"{RAW_MARKET_SIGMA_300S_BPS:.2f} |"
    )
    lines.append("")
    # alpha decay regime test verdict
    r60 = pooled.get("r_squared_60s")
    r120 = pooled.get("r_squared_120s")
    r300 = pooled.get("r_squared_300s")
    decay_notes = []
    if r120 is not None and r120 < 0.04:
        decay_notes.append("- **WARN**：N=120 主信號 R² < 0.04 → spec §3.1.1 半衰期 < 60s 風險，需 revise")
    if r60 is not None and r300 is not None and r300 > r60:
        decay_notes.append(
            "- **WARN**：R²(300) > R²(60) → trend-continuation 未被 arbitrage 完全消化，"
            "需重評 N 選擇"
        )
    if not decay_notes:
        decay_notes.append("- alpha decay regime test：OK（N=120 主信號 R² ≥ 0.04 + decay 單調）")
    lines.extend(decay_notes)
    lines.append("")
    lines.append(f"### Step gate verdict — pooled: **{pooled['verdict']['label']}**")
    lines.append("")
    lines.append(f"> {pooled['verdict']['reason']}")
    lines.append("")

    # ============================================================
    # §2 Per-symbol breakdown
    # ============================================================
    lines.append("## §2 Per-symbol breakdown（spec §7.1 metric (1)：n ≥ 100 + t > 2.0 gate）")
    lines.append("")
    lines.append("| Symbol | n | avg_net (bps) | t-stat | PSR(0) | DSR | "
                 "CI 95% | Verdict | promote N+2 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for sym in cohort:
        m = per_symbol.get(sym)
        if m is None:
            lines.append(f"| {sym} | 0 | - | - | - | - | - | no_signal | ❌ |")
            continue
        ci_str = (
            f"[{_fmt(m['ci_95_low'], '.2f')}, {_fmt(m['ci_95_high'], '.2f')}]"
            if m.get("ci_95_low") is not None and m.get("ci_95_high") is not None
            else "-"
        )
        promote_icon = "✅" if m["verdict"]["promote_n2"] else "❌"
        lines.append(
            f"| {sym} | {m['sample_n']} | {_fmt(m['avg_net_bps'], '.2f')} | "
            f"{_fmt(m['t_stat'], '.3f')} | {_fmt(m['psr_0'], '.3f')} | "
            f"{_fmt(m['dsr_k95'], '.3f')} | {ci_str} | "
            f"{m['verdict']['label']} | {promote_icon} |"
        )
    lines.append("")

    # ============================================================
    # §3 Counterfactual delta（spec §7.1 metric (6)）
    # ============================================================
    lines.append("## §3 Per-cohort counterfactual delta（expected_dir 三方向）")
    lines.append("")
    lines.append("| Symbol | LONG n / avg (bps) | SHORT n / avg (bps) | "
                 "No-signal n / baseline (bps) | extreme regime n |")
    lines.append("|---|---|---|---|---|")
    for sym in cohort:
        m = per_symbol.get(sym)
        if m is None:
            lines.append(f"| {sym} | 0 / - | 0 / - | 0 / - | 0 |")
            continue
        lines.append(
            f"| {sym} | {m['long_n']} / {_fmt(m['cf_long_avg_bps'], '.2f')} | "
            f"{m['short_n']} / {_fmt(m['cf_short_avg_bps'], '.2f')} | "
            f"{m['no_signal_n']} / {_fmt(m['cf_no_signal_baseline_bps'], '.2f')} | "
            f"{m['extreme_regime_n']} |"
        )
    lines.append("")

    # ============================================================
    # §4 Alpha decay R²(N) — per symbol
    # ============================================================
    lines.append("## §4 Alpha decay R²(N=60/120/300) per-symbol（spec §7.1 metric (4)）")
    lines.append("")
    lines.append("| Symbol | R²(60) | R²(120 主信號) | R²(300) | decay verdict |")
    lines.append("|---|---|---|---|---|")
    for sym in cohort:
        m = per_symbol.get(sym)
        if m is None:
            lines.append(f"| {sym} | - | - | - | no_data |")
            continue
        r60_s = m.get("r_squared_60s")
        r120_s = m.get("r_squared_120s")
        r300_s = m.get("r_squared_300s")
        # decay verdict per spec §3.1.1
        verdict_d = "OK"
        if r120_s is not None and r120_s < 0.04:
            verdict_d = "FAIL: R²(120)<0.04"
        elif r60_s is not None and r300_s is not None and r300_s > r60_s:
            verdict_d = "WARN: R²(300)>R²(60)"
        lines.append(
            f"| {sym} | {_fmt(r60_s, '.4f')} | {_fmt(r120_s, '.4f')} | "
            f"{_fmt(r300_s, '.4f')} | {verdict_d} |"
        )
    lines.append("")

    # ============================================================
    # §5 Acceptance summary
    # ============================================================
    lines.append("## §5 Acceptance summary（spec v1.2 §8.3 sign-off path）")
    lines.append("")
    p = pooled
    psr_pass = p.get("psr_0") is not None and p["psr_0"] >= PSR_THRESHOLD
    dsr_pass = p.get("dsr_k95") is not None and p["dsr_k95"] >= DSR_THRESHOLD
    pooled_promote = p["verdict"].get("promote_n2", False)
    any_symbol_promote = any(
        m["verdict"].get("promote_n2", False)
        for m in per_symbol.values()
    )
    lines.append(f"- Pooled PSR(0) ≥ 0.95（B-LdP 2012）: "
                 f"{'✅ PASS' if psr_pass else '❌ FAIL'} (`{_fmt(p.get('psr_0'), '.4f')}`)")
    lines.append(f"- Pooled DSR ≥ 0.95（K=95, mu_0=3.018）: "
                 f"{'✅ PASS' if dsr_pass else '❌ FAIL'} (`{_fmt(p.get('dsr_k95'), '.4f')}`)")
    lines.append(f"- Pooled verdict: `{p['verdict']['label']}` → promote N+2: "
                 f"{'✅' if pooled_promote else '❌'}")
    lines.append(f"- Any per-symbol promote N+2 PASS: "
                 f"{'✅' if any_symbol_promote else '❌'}")
    lines.append("")
    lines.append("**Acceptance verdict**：")
    final_verdict = "ARCHIVE / REVISE"
    if pooled_promote and any_symbol_promote and psr_pass and dsr_pass:
        final_verdict = "PROMOTE N+2 DEMO IMPL"
    elif p["verdict"]["label"] == "plus5_15":
        final_verdict = "EXTEND PAPER WINDOW 14d"
    elif p["verdict"]["label"] == "plus15" and (not psr_pass or not dsr_pass):
        final_verdict = "PROMOTE PENDING (PSR/DSR fail) — EXTEND 14d"
    lines.append(f"> **{final_verdict}**")
    lines.append("")
    lines.append(
        "（PA + QC + MIT 三角 sign-off 才正式決定 N+2 dispatch；本報告是 evidence 基礎。）"
    )
    lines.append("")
    return "\n".join(lines)


# ============================================================
# Smoke-test mock fixture（per dispatch §3.4 E4 regression：3 mock case）
# ============================================================


def _make_mock_row(
    symbol: str,
    ts_bucket: int,
    expected_dir: int,
    btc_lead: float,
    btc_lead_60s: float,
    btc_lead_300s: float,
    xcorr: float,
    regime: str,
    alt_fwd_60s: float,
    alt_fwd_120s: float,
    alt_fwd_300s: float,
    has_fill: bool = False,
) -> dict:
    """構造一個 mock SQL row（對齊 sql/queries/w2_btc_alt_lead_lag_counterfactual.sql output schema）。"""
    cf_60 = expected_dir * alt_fwd_60s if expected_dir != 0 else None
    cf_120 = expected_dir * alt_fwd_120s if expected_dir != 0 else None
    cf_300 = expected_dir * alt_fwd_300s if expected_dir != 0 else None
    return {
        "symbol": symbol,
        "snapshot_ts_ms": ts_bucket,
        "lead_window_secs": 120,
        "btc_lead_return_pct": btc_lead,
        "btc_lead_return_pct_60s": btc_lead_60s,
        "btc_lead_return_pct_300s": btc_lead_300s,
        "btc_volume_z": 0.5,
        "btc_book_imbalance": 0.1,
        "xcorr": xcorr,
        "expected_dir": expected_dir,
        "regime_tag": regime,
        "alt_forward_return_60s_bps": alt_fwd_60s,
        "alt_forward_return_120s_bps": alt_fwd_120s,
        "alt_forward_return_300s_bps": alt_fwd_300s,
        "cf_net_edge_60s_bps": cf_60,
        "cf_net_edge_120s_bps": cf_120,
        "cf_net_edge_300s_bps": cf_300,
        "has_actual_fill": has_fill,
        "actual_fill_count": 1 if has_fill else 0,
    }


def make_smoke_fixture_plus15() -> list[dict]:
    """Mock case 1：plus15 — gross +20 bps mean → step_gate=plus15 promote。

    為了通過 t-stat > 2.0 gate，本 fixture 構造低 σ 配合高 mean：
    fluctuation ~±5 bps（low σ），中位 +20 bps → t-stat very large。
    BTC lead 加 jitter 讓 R²(N) 可計算（var_x > 0）。
    """
    rng = random.Random(20260512)
    rows = []
    ts0 = 1_730_000_000_000
    for i in range(150):  # n ≥ 100 才能 promote
        # alt forward return ≈ +20 bps + noise ±5 bps（per-symbol σ ~ 5 bps low）
        alt = 20.0 + rng.uniform(-5.0, 5.0)
        # BTC lead 加 jitter 確保 var_x > 0（R²(N) 可算）；
        # 主信號 N=120 alt 與 BTC lead correlation ~ moderate（OLS regression demo）
        btc_jitter = rng.uniform(-3.0, 3.0)
        rows.append(_make_mock_row(
            symbol="ETHUSDT",
            ts_bucket=ts0 + i * 60_000,
            expected_dir=1,
            btc_lead=12.0 + btc_jitter,
            btc_lead_60s=8.0 + btc_jitter * 0.6,
            btc_lead_300s=18.0 + btc_jitter * 1.4,
            xcorr=0.65,
            regime="normal",
            alt_fwd_60s=alt * 0.5,
            alt_fwd_120s=alt,
            alt_fwd_300s=alt * 1.5,
            has_fill=True,
        ))
    return rows


def make_smoke_fixture_plus5_15() -> list[dict]:
    """Mock case 2：plus5_15 — gross +8 bps → step_gate=plus5_15 extend。"""
    rng = random.Random(20260513)
    rows = []
    ts0 = 1_730_000_000_000
    for i in range(150):
        alt = 8.0 + rng.uniform(-5.0, 5.0)
        btc_jitter = rng.uniform(-3.0, 3.0)
        rows.append(_make_mock_row(
            symbol="ETHUSDT",
            ts_bucket=ts0 + i * 60_000,
            expected_dir=1,
            btc_lead=12.0 + btc_jitter,
            btc_lead_60s=8.0 + btc_jitter * 0.6,
            btc_lead_300s=18.0 + btc_jitter * 1.4,
            xcorr=0.55,
            regime="normal",
            alt_fwd_60s=alt * 0.5,
            alt_fwd_120s=alt,
            alt_fwd_300s=alt * 1.5,
            has_fill=False,
        ))
    return rows


def make_smoke_fixture_minus5() -> list[dict]:
    """Mock case 3：minus5 — gross -3 bps → step_gate=minus5 archive/revise。"""
    rng = random.Random(20260514)
    rows = []
    ts0 = 1_730_000_000_000
    for i in range(150):
        alt = -3.0 + rng.uniform(-5.0, 5.0)
        btc_jitter = rng.uniform(-3.0, 3.0)
        rows.append(_make_mock_row(
            symbol="ETHUSDT",
            ts_bucket=ts0 + i * 60_000,
            expected_dir=1,
            btc_lead=11.0 + btc_jitter,
            btc_lead_60s=7.0 + btc_jitter * 0.6,
            btc_lead_300s=17.0 + btc_jitter * 1.4,
            xcorr=0.45,
            regime="normal",
            alt_fwd_60s=alt * 0.5,
            alt_fwd_120s=alt,
            alt_fwd_300s=alt * 1.5,
            has_fill=False,
        ))
    return rows


def run_smoke_test() -> int:
    """跑 3 mock case，驗 step_gate verdict + 6 mandatory metric 公式正確。

    退出碼：0 = ALL PASS；1 = ANY FAIL（E4 regression gate）
    """
    print("=== W2 paper edge report smoke test ===")
    print("(per dispatch §3.4 E4 regression：plus15 / plus5_15 / minus5)")
    print()

    failures: list[str] = []

    # Case 1: plus15
    print("Case 1: plus15 (gross +20 bps, n=150, expected promote N+2)")
    rows1 = make_smoke_fixture_plus15()
    per_sym_1 = compute_per_symbol_metrics(rows1, primary_window_secs=120)
    pooled_1 = compute_pooled_metrics(rows1, primary_window_secs=120)
    m1 = per_sym_1.get("ETHUSDT", {})
    print(f"  ETHUSDT: n={m1.get('sample_n')} avg_net={_fmt(m1.get('avg_net_bps'), '.2f')} "
          f"t={_fmt(m1.get('t_stat'), '.3f')} verdict={m1.get('verdict', {}).get('label')}")
    print(f"  pooled: avg_net={_fmt(pooled_1.get('avg_net_bps'), '.2f')} "
          f"verdict={pooled_1.get('verdict', {}).get('label')}")
    if m1.get("verdict", {}).get("label") != "plus15":
        failures.append(f"Case 1 ETHUSDT verdict expected plus15 got {m1.get('verdict', {}).get('label')}")
    if not m1.get("verdict", {}).get("promote_n2"):
        failures.append("Case 1 ETHUSDT promote_n2 expected True")
    print()

    # Case 2: plus5_15
    print("Case 2: plus5_15 (gross +8 bps, n=150, expected extend 14d)")
    rows2 = make_smoke_fixture_plus5_15()
    per_sym_2 = compute_per_symbol_metrics(rows2, primary_window_secs=120)
    pooled_2 = compute_pooled_metrics(rows2, primary_window_secs=120)
    m2 = per_sym_2.get("ETHUSDT", {})
    print(f"  ETHUSDT: n={m2.get('sample_n')} avg_net={_fmt(m2.get('avg_net_bps'), '.2f')} "
          f"t={_fmt(m2.get('t_stat'), '.3f')} verdict={m2.get('verdict', {}).get('label')}")
    print(f"  pooled: avg_net={_fmt(pooled_2.get('avg_net_bps'), '.2f')} "
          f"verdict={pooled_2.get('verdict', {}).get('label')}")
    if m2.get("verdict", {}).get("label") != "plus5_15":
        failures.append(f"Case 2 ETHUSDT verdict expected plus5_15 got {m2.get('verdict', {}).get('label')}")
    if m2.get("verdict", {}).get("promote_n2"):
        failures.append("Case 2 ETHUSDT promote_n2 expected False")
    print()

    # Case 3: minus5
    print("Case 3: minus5 (gross -3 bps, n=150, expected revise/archive)")
    rows3 = make_smoke_fixture_minus5()
    per_sym_3 = compute_per_symbol_metrics(rows3, primary_window_secs=120)
    pooled_3 = compute_pooled_metrics(rows3, primary_window_secs=120)
    m3 = per_sym_3.get("ETHUSDT", {})
    print(f"  ETHUSDT: n={m3.get('sample_n')} avg_net={_fmt(m3.get('avg_net_bps'), '.2f')} "
          f"t={_fmt(m3.get('t_stat'), '.3f')} verdict={m3.get('verdict', {}).get('label')}")
    print(f"  pooled: avg_net={_fmt(pooled_3.get('avg_net_bps'), '.2f')} "
          f"verdict={pooled_3.get('verdict', {}).get('label')}")
    if m3.get("verdict", {}).get("label") != "minus5":
        failures.append(f"Case 3 ETHUSDT verdict expected minus5 got {m3.get('verdict', {}).get('label')}")
    if m3.get("verdict", {}).get("promote_n2"):
        failures.append("Case 3 ETHUSDT promote_n2 expected False")
    print()

    # 額外驗 PSR(0) 用 Bailey-LdP formula 而非 normal z-test
    # 用 case 1 對比：σ_net=5 + μ=20 → SR_hat=4.0；normal z-test = SR×√n=49 → Φ≈1.0
    # B-LdP formula 對 skew/kurt 修正後應該也 ≈ 0.99+（高度 PASS）
    psr_case1 = m1.get("psr_0")
    if psr_case1 is None or psr_case1 < 0.95:
        failures.append(f"Case 1 PSR(0) expected ≥0.95, got {psr_case1}")
    else:
        print(f"  PSR(0) case 1 = {_fmt(psr_case1, '.4f')} ≥ 0.95 ✅ (Bailey-LdP 2012 formula)")

    # 驗 DSR with K=95 deflate
    dsr_case1 = m1.get("dsr_k95")
    if dsr_case1 is None:
        failures.append("Case 1 DSR K=95 None - formula error")
    else:
        print(f"  DSR(K=95) case 1 = {_fmt(dsr_case1, '.4f')} (mu_0=√(2 ln 95)=3.018)")
    print()

    # 驗 block-bootstrap CI 為合理 range
    ci_case1 = (m1.get("ci_95_low"), m1.get("ci_95_high"))
    if ci_case1[0] is None or ci_case1[1] is None:
        failures.append("Case 1 block-bootstrap CI None")
    else:
        print(f"  Case 1 95% CI = [{_fmt(ci_case1[0], '.3f')}, {_fmt(ci_case1[1], '.3f')}] "
              f"(block_size=60, 1000 iter)")
    print()

    # 驗 alpha decay R²(N)
    r60 = m1.get("r_squared_60s")
    r120 = m1.get("r_squared_120s")
    r300 = m1.get("r_squared_300s")
    print(f"  Alpha decay R²(60/120/300) case 1: "
          f"{_fmt(r60, '.4f')} / {_fmt(r120, '.4f')} / {_fmt(r300, '.4f')}")
    if r60 is None or r120 is None or r300 is None:
        failures.append("Case 1 R²(N) None - decay formula error")

    print()
    print("=" * 50)
    if failures:
        print(f"FAILURES ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ALL PASS — 3 mock case + PSR(0) + DSR + CI + R²(N) 公式驗證通過")
    return 0


# ============================================================
# Main entry
# ============================================================


def _parse_cohort(arg: Optional[str]) -> tuple[str, ...]:
    """parse --cohort arg：comma-separated symbol list；空則用 DEFAULT_COHORT。"""
    if not arg:
        return DEFAULT_COHORT
    return tuple(s.strip().upper() for s in arg.split(",") if s.strip())


def fetch_rows_from_pg(
    conn,
    window_days: int,
    cohort: Sequence[str],
) -> list[dict]:
    """跑 counterfactual SQL，回傳 dict rows（column_name → value）。"""
    sql_text = _read_counterfactual_sql()
    with conn.cursor() as cur:
        cur.execute(
            sql_text,
            {
                "window_days": window_days,
                "cohort_symbols": list(cohort),
            },
        )
        col_names = [d[0] for d in cur.description]
        return [dict(zip(col_names, row)) for row in cur.fetchall()]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="W2 A4-C BTC→Alt Lead-Lag — D+12 paper edge report generator"
    )
    parser.add_argument(
        "--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
        help=f"paper engine edge collection window (default {DEFAULT_WINDOW_DAYS})",
    )
    parser.add_argument(
        "--cohort", type=str, default=None,
        help="comma-separated cohort symbols (default 7-symbol cohort per spec §2.2)",
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="output markdown path (default docs/CCAgentWorkSpace/PA/workspace/reports/<today>--w2_paper_edge_report.md)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print to stdout only, do not write file",
    )
    parser.add_argument(
        "--smoke-test", action="store_true",
        help="run smoke test (3 mock case, no PG), exit 0 PASS / 1 FAIL",
    )
    args = parser.parse_args()

    # smoke-test 不連 PG，跑 mock fixture 驗 metric 公式 + step_gate verdict
    if args.smoke_test:
        return run_smoke_test()

    cohort = _parse_cohort(args.cohort)
    window_days = max(1, args.window_days)

    try:
        conn = _get_conn()
    except Exception as e:  # noqa: BLE001
        print(f"[FATAL] DB connect failed: {e}", file=sys.stderr)
        return 2

    try:
        rows = fetch_rows_from_pg(conn, window_days, cohort)
    finally:
        conn.close()

    print(f"[INFO] fetched {len(rows)} counterfactual rows over {window_days}d "
          f"for {len(cohort)} cohort symbols", file=sys.stderr)

    pooled = compute_pooled_metrics(rows, primary_window_secs=120)
    per_symbol = compute_per_symbol_metrics(rows, primary_window_secs=120)

    md = render_markdown(
        pooled=pooled,
        per_symbol=per_symbol,
        window_days=window_days,
        cohort=cohort,
        timestamp=datetime.now(timezone.utc),
    )

    if args.dry_run:
        print(md)
        return 0

    base = os.environ.get("OPENCLAW_BASE_DIR") or os.environ.get("OPENCLAW_SRV_ROOT")
    if not base:
        base = str(Path(__file__).resolve().parent.parent.parent)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = (
        Path(args.out)
        if args.out
        else Path(base) / "docs" / "CCAgentWorkSpace" / "PA" / "workspace"
            / "reports" / f"{today}--w2_paper_edge_report.md"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

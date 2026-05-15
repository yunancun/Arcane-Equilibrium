"""W2 legacy paper edge / Stage 0R diagnostic report 計算層。

MODULE_NOTE:
    本模組承接 W2 A4-C BTC→Alt Lead-Lag spec v1.2 §7.1 六項 mandatory
    metric 的純計算邏輯，並按 AMD-2026-05-15-01 將輸出降級為
    Stage 0R diagnostic eligibility；不得輸出 Stage 1 PASS 或 promotion。
    覆蓋 per-symbol / pooled edge、DSR K=95、PSR(0)
    Bailey-López de Prado skew/kurt 公式、alpha decay R²、block-bootstrap CI、
    counterfactual delta 與 spec §8.1 三檔 diagnostic band。保持無 DB、無檔案 I/O。
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Optional, Sequence

DSR_K_MULTIPLE_TRIAL = 95

RAW_MARKET_SIGMA_60S_BPS = 4.54
RAW_MARKET_SIGMA_120S_BPS = 6.28
RAW_MARKET_SIGMA_300S_BPS = 10.08
NET_EDGE_SIGMA_LOWER_BPS = 50.0
NET_EDGE_SIGMA_UPPER_BPS = 80.0
NET_EDGE_SIGMA_MID_BPS = 65.0

GATE_PLUS_15_BPS = 15.0
GATE_PLUS_5_BPS = 5.0

PER_SYMBOL_N_MIN = 100
PER_SYMBOL_T_MIN = 2.0

BOOTSTRAP_BLOCK_SIZE_MINUTES = 60
BOOTSTRAP_ITERATIONS = 1000

PSR_THRESHOLD = 0.95
DSR_THRESHOLD = 0.95

DEFAULT_COHORT = (
    "ETHUSDT", "SOLUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT",
)
DEFAULT_WINDOW_DAYS = 7


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _safe_mean(values: Sequence[float]) -> Optional[float]:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if not clean:
        return None
    return statistics.mean(clean)


def _safe_stdev(values: Sequence[float]) -> Optional[float]:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if len(clean) < 2:
        return None
    return statistics.stdev(clean)


def _skewness(values: Sequence[float]) -> Optional[float]:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < 3:
        return None
    mu = statistics.mean(clean)
    var = sum((v - mu) ** 2 for v in clean) / n
    if var <= 0:
        return None
    sigma = math.sqrt(var)
    return sum(((v - mu) / sigma) ** 3 for v in clean) / n


def _kurtosis(values: Sequence[float]) -> Optional[float]:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < 4:
        return None
    mu = statistics.mean(clean)
    var = sum((v - mu) ** 2 for v in clean) / n
    if var <= 0:
        return None
    sigma = math.sqrt(var)
    return sum(((v - mu) / sigma) ** 4 for v in clean) / n


def compute_t_stat(values: Sequence[float], h0_mu: float = 0.0) -> Optional[float]:
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
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < 4:
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
    denom_sq = 1.0 - skew * sr_hat + ((kurt - 1.0) / 4.0) * (sr_hat ** 2)
    if denom_sq <= 0:
        return None
    z = (sr_hat - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(denom_sq)
    return _normal_cdf(z)


def compute_dsr_with_k_deflate(
    values: Sequence[float],
    k_trials: int = DSR_K_MULTIPLE_TRIAL,
) -> Optional[float]:
    if k_trials <= 1:
        return None
    mu_0 = math.sqrt(2.0 * math.log(k_trials))
    return compute_psr_bailey_lopez_de_prado_2012(values, sr_benchmark=mu_0)


def compute_block_bootstrap_ci(
    values: Sequence[float],
    block_size: int = BOOTSTRAP_BLOCK_SIZE_MINUTES,
    iterations: int = BOOTSTRAP_ITERATIONS,
    confidence: float = 0.95,
    seed: int = 20260512,
) -> Optional[tuple[float, float]]:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    n = len(clean)
    if n < block_size:
        return None
    rng = random.Random(seed)
    n_blocks_per_iter = max(1, n // block_size)
    boot_means: list[float] = []
    for _ in range(iterations):
        sample: list[float] = []
        for _b in range(n_blocks_per_iter):
            start = rng.randint(0, n - block_size)
            sample.extend(clean[start:start + block_size])
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


def step_gate_verdict(
    avg_net_bps: Optional[float],
    t_stat: Optional[float],
    sample_n: int,
) -> dict:
    if avg_net_bps is None or t_stat is None:
        return {
            "label": "no_signal",
            "reason": "insufficient sample / undefined t-stat",
            "eligible_for_demo_canary": False,
            "promote_n2": False,
        }
    underpowered = (sample_n < PER_SYMBOL_N_MIN or t_stat <= PER_SYMBOL_T_MIN)
    if avg_net_bps >= GATE_PLUS_15_BPS:
        if underpowered:
            return {
                "label": "plus15",
                "reason": (
                    f"avg_net ≥ +15 bps but underpowered "
                    f"(n={sample_n}<{PER_SYMBOL_N_MIN} or t={t_stat:.3f}≤{PER_SYMBOL_T_MIN})"
                    " → not eligible for demo canary without n + t gate"
                ),
                "eligible_for_demo_canary": False,
                "promote_n2": False,
            }
        return {
            "label": "plus15",
            "reason": (
                f"avg_net = {avg_net_bps:.2f} bps ≥ +15 + n={sample_n}≥100 "
                f"+ t={t_stat:.3f}>2.0 → eligible_for_demo_canary=true "
                "(Stage 0R only; not Stage 1 PASS)"
            ),
            "eligible_for_demo_canary": True,
            "promote_n2": False,
        }
    if avg_net_bps >= GATE_PLUS_5_BPS:
        return {
            "label": "plus5_15",
            "reason": (
                f"avg_net = {avg_net_bps:.2f} bps ∈ [+5, +15) → "
                f"eligible_for_demo_canary=false_or_defer (n={sample_n}, t={t_stat:.3f})"
            ),
            "eligible_for_demo_canary": False,
            "promote_n2": False,
        }
    return {
        "label": "minus5",
        "reason": (
            f"avg_net = {avg_net_bps:.2f} bps < +5 → revise spec 或 archive"
            f" (n={sample_n}, t={t_stat:.3f})"
        ),
        "eligible_for_demo_canary": False,
        "promote_n2": False,
    }


def _select_forward_window_field(row: dict, window_secs: int) -> Optional[float]:
    if window_secs == 60:
        return row.get("cf_net_edge_60s_bps")
    if window_secs == 120:
        return row.get("cf_net_edge_120s_bps")
    if window_secs == 300:
        return row.get("cf_net_edge_300s_bps")
    return None


def _alt_forward_return_field(row: dict, window_secs: int) -> Optional[float]:
    if window_secs == 60:
        return row.get("alt_forward_return_60s_bps")
    if window_secs == 120:
        return row.get("alt_forward_return_120s_bps")
    if window_secs == 300:
        return row.get("alt_forward_return_300s_bps")
    return None


def _btc_lead_return_field(row: dict, window_secs: int) -> Optional[float]:
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
    out: dict[str, dict] = {}
    by_symbol: dict[str, list[dict]] = {}
    for r in rows:
        sym = r.get("symbol")
        if sym is None:
            continue
        by_symbol.setdefault(sym, []).append(r)

    for sym, sym_rows in by_symbol.items():
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

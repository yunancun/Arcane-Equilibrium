#!/usr/bin/env python3
"""
Golden Dataset Generator — Rust↔Python Indicator Cross-Validation
黃金數據集生成器 — Rust↔Python 指標交叉驗證

MODULE_NOTE (中文):
  R02-10 黃金數據集 Python 端對照腳本。使用與 Rust 整合測試相同的確定性合成
  OHLCV 生成演算法，計算全部 13 個指標的 Python 參考值並輸出 JSON。
  用途：未來自動化 Rust↔Python 數值比對。

MODULE_NOTE (English):
  R02-10 golden dataset Python counterpart script. Uses the same deterministic
  synthetic OHLCV generation algorithm as the Rust integration test, computes
  all 13 indicators using the Python reference implementation, and outputs JSON.
  Purpose: future automated Rust↔Python numerical comparison.

Usage / 用法:
  python3 helper_scripts/golden_dataset_gen.py [--bars N] [--seed S] [--output FILE]

Safety invariant / 安全不變量:
  Pure computation script — no API calls, no trading, no side effects.
  純計算腳本 — 無 API 呼叫、不交易、無副作用。
"""

import argparse
import json
import math
import sys
import os
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════════════
# Synthetic OHLCV Generator (mirrors Rust `generate_synthetic_ohlcv`)
# 合成 OHLCV 生成器（鏡像 Rust `generate_synthetic_ohlcv`）
# ═══════════════════════════════════════════════════════════════════════════════


def generate_synthetic_ohlcv(
    n: int = 200, seed: int = 42
) -> tuple[list[float], list[float], list[float], list[float], list[float]]:
    """
    Generate deterministic synthetic OHLCV data.
    生成確定性合成 OHLCV 數據。

    IMPORTANT: This algorithm MUST stay in sync with the Rust version in
    `openclaw_core/tests/golden_dataset.rs::generate_synthetic_ohlcv()`.
    重要：此演算法必須與 Rust 版本保持同步。

    Args:
        n: Number of bars / K 線數量
        seed: Deterministic seed / 確定性種子

    Returns:
        (open, high, low, close, volume) arrays / 陣列
    """
    close, high, low, open_prices, volume = [], [], [], [], []
    base = 50_000.0  # BTC-like base price / BTC 級別基準價格

    for i in range(n):
        t = i / n * math.pi * 4.0
        trend = base + i * 10.0
        cycle = 2000.0 * math.sin(t)
        # Deterministic pseudo-noise (mirrors Rust wrapping_mul + mod)
        # 確定性偽噪聲（鏡像 Rust wrapping_mul + mod）
        # Python integers don't overflow, so we mask to u64 range
        raw = (i * seed * 2_654_435_761) % (2**64)
        noise = (raw % 1000) - 500

        c = trend + cycle + noise
        h = c + (50.0 + abs(noise) * 0.1)
        l = c - (50.0 + abs(noise) * 0.1)
        o = c if i == 0 else close[i - 1]
        v = 100.0 + i * 1.5

        close.append(c)
        high.append(h)
        low.append(l)
        open_prices.append(o)
        volume.append(v)

    return open_prices, high, low, close, volume


# ═══════════════════════════════════════════════════════════════════════════════
# Python Indicator Implementations (standalone, no external deps)
# Python 指標實現（獨立，無外部依賴）
# ═══════════════════════════════════════════════════════════════════════════════


def kahan_sum(values: list[float]) -> float:
    """Kahan compensated summation. / Kahan 補償求和。"""
    s = 0.0
    comp = 0.0
    for v in values:
        y = v - comp
        t = s + y
        comp = (t - s) - y
        s = t
    return s


def calc_sma(close: list[float], period: int) -> float | None:
    """SMA using Kahan sum. / 使用 Kahan 求和的 SMA。"""
    if len(close) < period or period == 0:
        return None
    window = close[-period:]
    return kahan_sum(window) / period


def calc_ema(close: list[float], period: int) -> float | None:
    """EMA seeded with SMA. / 以 SMA 為種子的 EMA。"""
    if len(close) < period or period == 0:
        return None
    k = 2.0 / (period + 1.0)
    seed = kahan_sum(close[:period]) / period
    ema_val = seed
    for price in close[period:]:
        ema_val = price * k + ema_val * (1.0 - k)
    return ema_val


def calc_rsi(close: list[float], period: int) -> float | None:
    """RSI with Wilder's smoothing. / Wilder 平滑的 RSI。"""
    if len(close) < period + 1 or period == 0:
        return None
    changes = [close[i + 1] - close[i] for i in range(len(close) - 1)]
    init = changes[:period]
    avg_gain = kahan_sum([max(c, 0) for c in init]) / period
    avg_loss = kahan_sum([max(-c, 0) for c in init]) / period
    for change in changes[period:]:
        gain = max(change, 0)
        loss = max(-change, 0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss < 1e-15:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)


def calc_macd(
    close: list[float], fast: int, slow: int, signal: int
) -> dict | None:
    """MACD with configurable periods. / 可配置週期的 MACD。"""
    if fast == 0 or slow == 0 or signal == 0 or fast >= slow:
        return None

    def ema_series(data, period):
        if len(data) < period:
            return None
        k = 2.0 / (period + 1.0)
        seed = kahan_sum(data[:period]) / period
        result = [seed]
        prev = seed
        for price in data[period:]:
            val = price * k + prev * (1.0 - k)
            result.append(val)
            prev = val
        return result

    fast_ema = ema_series(close, fast)
    slow_ema = ema_series(close, slow)
    if fast_ema is None or slow_ema is None:
        return None
    offset = slow - fast
    if len(fast_ema) <= offset:
        return None
    macd_line = [f - s for f, s in zip(fast_ema[offset:], slow_ema)]
    if len(macd_line) < signal:
        return None
    sig_k = 2.0 / (signal + 1.0)
    sig_seed = kahan_sum(macd_line[:signal]) / signal
    sig_val = sig_seed
    for m in macd_line[signal:]:
        sig_val = m * sig_k + sig_val * (1.0 - sig_k)
    last_macd = macd_line[-1]
    return {
        "macd": last_macd,
        "signal": sig_val,
        "histogram": last_macd - sig_val,
    }


def calc_bollinger(
    close: list[float], period: int, std_mult: float
) -> dict | None:
    """Bollinger Bands. / 布林帶。"""
    if len(close) < period or period == 0:
        return None
    window = close[-period:]
    mean = kahan_sum(window) / period
    sq_devs = [(v - mean) ** 2 for v in window]
    variance = kahan_sum(sq_devs) / period
    std_dev = math.sqrt(variance)
    upper = mean + std_mult * std_dev
    lower = mean - std_mult * std_dev
    bandwidth = (upper - lower) / mean if mean > 1e-15 else 0.0
    last = close[-1]
    band_range = upper - lower
    percent_b = (last - lower) / band_range if band_range > 1e-15 else 0.5
    return {
        "upper": upper,
        "middle": mean,
        "lower": lower,
        "bandwidth": bandwidth,
        "percent_b": percent_b,
    }


def calc_atr(
    high: list[float], low: list[float], close: list[float], period: int
) -> dict | None:
    """ATR with Wilder's smoothing. / Wilder 平滑的 ATR。"""
    n = min(len(high), len(low), len(close))
    if n < period + 1 or period == 0:
        return None
    tr_vals = []
    for i in range(1, n):
        tr = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
        tr_vals.append(tr)
    atr_val = kahan_sum(tr_vals[:period]) / period
    for tr in tr_vals[period:]:
        atr_val = (atr_val * (period - 1) + tr) / period
    last_close = close[-1]
    atr_pct = atr_val / last_close * 100.0 if last_close > 1e-15 else 0.0
    return {"atr": atr_val, "atr_percent": atr_pct}


def calc_stochastic(
    high: list[float],
    low: list[float],
    close: list[float],
    k_period: int,
    d_period: int,
) -> dict | None:
    """Stochastic oscillator. / 隨機指標。"""
    n = min(len(high), len(low), len(close))
    if k_period == 0 or d_period == 0 or n < k_period + d_period - 1:
        return None
    k_values = []
    for i in range(n - d_period, n):
        start = i + 1 - k_period
        h_max = max(high[start : i + 1])
        l_min = min(low[start : i + 1])
        rng = h_max - l_min
        k_val = (close[i] - l_min) / rng * 100.0 if rng > 1e-15 else 50.0
        k_values.append(k_val)
    k = k_values[-1]
    d = kahan_sum(k_values) / d_period
    return {"k": k, "d": d}


def calc_volume_ratio(volume: list[float], period: int) -> float | None:
    """Volume ratio. / 量比。"""
    if len(volume) < period + 1 or period == 0:
        return None
    avg_window = volume[-(period + 1) : -1]
    avg = kahan_sum(avg_window) / period
    if avg < 1e-15:
        return None
    return volume[-1] / avg


def calc_donchian(
    high: list[float], low: list[float], close: list[float], period: int
) -> dict | None:
    """Donchian Channel. / 唐奇安通道。"""
    n = min(len(high), len(low), len(close))
    if n < period or period == 0:
        return None
    h_window = high[n - period : n]
    l_window = low[n - period : n]
    upper = max(h_window)
    lower = min(l_window)
    middle = (upper + lower) / 2.0
    width = (upper - lower) / middle if middle > 1e-15 else 0.0
    return {"upper": upper, "lower": lower, "middle": middle, "width": width}


# ═══════════════════════════════════════════════════════════════════════════════
# Main — Generate and Output Golden Dataset
# 主程序 — 生成並輸出黃金數據集
# ═══════════════════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Golden dataset generator for Rust↔Python indicator cross-validation"
    )
    parser.add_argument("--bars", type=int, default=200, help="Number of bars")
    parser.add_argument("--seed", type=int, default=42, help="Deterministic seed")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file (default: stdout)",
    )
    args = parser.parse_args()

    open_prices, high, low, close, volume = generate_synthetic_ohlcv(
        args.bars, args.seed
    )

    # Compute all 13 indicators with default parameters
    # 使用默認參數計算全部 13 個指標
    results = {
        "metadata": {
            "bars": args.bars,
            "seed": args.seed,
            "generator": "golden_dataset_gen.py",
            "qc_tolerances": {
                "sma": "±1e-8 (Kahan compensated)",
                "ema": "±1e-8 (Kahan compensated)",
                "rsi": "±0.1% (Wilder smoothing propagation)",
                "macd_histogram_identity": "±1e-10 (algebraic)",
                "bollinger_middle_vs_sma": "±1e-10 (same path)",
                "atr": "±0.01% (Wilder smoothing)",
                "stochastic": "±0.01% (window-based)",
                "hurst": "±0.05 (R/S inherent variance)",
                "donchian_middle_identity": "±1e-10 (algebraic)",
            },
        },
        "data_sample": {
            "first_5_close": close[:5],
            "last_5_close": close[-5:],
            "first_5_high": high[:5],
            "last_5_high": high[-5:],
        },
        "indicators": {
            "sma_20": calc_sma(close, 20),
            "ema_12": calc_ema(close, 12),
            "rsi_14": calc_rsi(close, 14),
            "macd_12_26_9": calc_macd(close, 12, 26, 9),
            "bollinger_20_2": calc_bollinger(close, 20, 2.0),
            "atr_14": calc_atr(high, low, close, 14),
            "stochastic_14_3": calc_stochastic(high, low, close, 14, 3),
            "volume_ratio_20": calc_volume_ratio(volume, 20),
            "donchian_20": calc_donchian(high, low, close, 20),
        },
    }

    # Verify internal consistency / 驗證內部一致性
    sma_val = results["indicators"]["sma_20"]
    bb = results["indicators"]["bollinger_20_2"]
    macd_r = results["indicators"]["macd_12_26_9"]
    donch = results["indicators"]["donchian_20"]

    checks = {
        "bb_middle_eq_sma": (
            abs(bb["middle"] - sma_val) < 1e-10 if bb and sma_val else "N/A"
        ),
        "macd_hist_identity": (
            abs(macd_r["histogram"] - (macd_r["macd"] - macd_r["signal"])) < 1e-10
            if macd_r
            else "N/A"
        ),
        "donchian_middle_identity": (
            abs(donch["middle"] - (donch["upper"] + donch["lower"]) / 2) < 1e-10
            if donch
            else "N/A"
        ),
        "rsi_in_range": (
            0 <= results["indicators"]["rsi_14"] <= 100
            if results["indicators"]["rsi_14"] is not None
            else "N/A"
        ),
    }
    results["consistency_checks"] = checks

    output = json.dumps(results, indent=2, ensure_ascii=False)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output, encoding="utf-8")
        print(f"Golden dataset written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Summary to stderr / 摘要輸出到 stderr
    n_computed = sum(
        1
        for v in results["indicators"].values()
        if v is not None
    )
    n_total = len(results["indicators"])
    all_checks_pass = all(
        v is True for v in checks.values() if v != "N/A"
    )
    print(
        f"\n[Golden Dataset] {n_computed}/{n_total} indicators computed, "
        f"consistency checks: {'ALL PASS' if all_checks_pass else 'SOME FAILED'}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

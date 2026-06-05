"""AEG regime classifier pure functions.

MODULE_NOTE:
  模塊用途：純函數分類核心。輸入 per-symbol daily close 序列，計算 AEG-S0 §2.6
    10 個 frozen feature，按 §2.7 產 main_regime，再補 BTCUSDT market anchor 與
    transition rows。全層 0 DB / 0 IO，方便 synthetic bite tests。
"""

from __future__ import annotations

import datetime as dt
import math
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from . import (
    BAR_MS_1D,
    CLASSIFIER_VERSION,
    EPSILON,
    FEATURE_NAMES,
    OVERLAY_FLAG_NAMES,
    VALID_MAIN_REGIMES,
    feature_rules_digest,
)


def _utc(ts: dt.datetime) -> dt.datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    return ts.astimezone(dt.timezone.utc)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def _none_if_nan(value: float | None) -> float | None:
    if value is None:
        return None
    return float(value) if math.isfinite(float(value)) else None


def _ret(closes: np.ndarray, bars: int) -> float | None:
    if len(closes) < bars + 1 or np.any(~np.isfinite(closes[-(bars + 1):])):
        return None
    if closes[-1] <= 0 or closes[-(bars + 1)] <= 0:
        return None
    return float(math.log(closes[-1] / closes[-(bars + 1)]))


def _rv(closes: np.ndarray, bars: int) -> float | None:
    if len(closes) < bars + 1 or np.any(~np.isfinite(closes[-(bars + 1):])):
        return None
    seg = closes[-(bars + 1):]
    if np.any(seg <= 0):
        return None
    rets = np.diff(np.log(seg))
    if len(rets) < 2:
        return None
    return float(np.std(rets, ddof=1))


def _sma(closes: np.ndarray, bars: int) -> float | None:
    if len(closes) < bars or np.any(~np.isfinite(closes[-bars:])):
        return None
    return float(np.mean(closes[-bars:]))


def _efficiency_30(closes: np.ndarray) -> float | None:
    if len(closes) < 31 or np.any(~np.isfinite(closes[-31:])):
        return None
    seg = closes[-31:]
    denom = float(np.sum(np.abs(np.diff(seg))))
    if denom <= EPSILON:
        return None
    return float(abs(seg[-1] - seg[0]) / denom)


def _direction_flip_30(closes: np.ndarray) -> float | None:
    if len(closes) < 31 or np.any(~np.isfinite(closes[-31:])):
        return None
    seg = closes[-31:]
    if np.any(seg <= 0):
        return None
    signs = np.sign(np.diff(np.log(seg)))
    valid_pairs = []
    for a, b in zip(signs[:-1], signs[1:]):
        if a == 0 or b == 0:
            continue
        valid_pairs.append((a, b))
    if len(valid_pairs) < 10:
        return None
    flips = sum(1 for a, b in valid_pairs if a != b)
    return float(flips / len(valid_pairs))


def _prior_percentile(value: float | None, prior: Sequence[float], *, min_n: int = 30) -> float | None:
    if value is None or not _finite(value):
        return None
    finite = [float(v) for v in prior if _finite(v)]
    if len(finite) < min_n:
        return None
    return float(sum(1 for v in finite if v <= float(value)) / len(finite))


def compute_feature_rows_for_symbol(
    symbol: str,
    closes: Sequence[tuple[dt.datetime, float]],
    *,
    run_id: str,
    timeframe: str = "1d",
) -> list[dict[str, Any]]:
    """計算單一 symbol 的 PIT feature rows。

    第 i 個 signal_ts 只能看 ``closes[:i]``；因此在尾部追加未來資料，不會改變早期
    signal 的 feature 或 label。
    """
    ordered = sorted((_utc(ts), float(close)) for ts, close in closes)
    ts_arr = [ts for ts, _close in ordered]
    close_arr = np.array([close for _ts, close in ordered], dtype=float)
    rv30_so_far: list[float | None] = []
    rows: list[dict[str, Any]] = []
    digest = feature_rules_digest()

    for i, signal_ts in enumerate(ts_arr):
        prior = close_arr[:i]
        feature_ts = ts_arr[i - 1] if i > 0 else None
        close_prior = float(prior[-1]) if len(prior) and _finite(prior[-1]) else None
        ret_30 = _ret(prior, 30)
        ret_90 = _ret(prior, 90)
        rv_30 = _rv(prior, 30)
        rv_90 = _rv(prior, 90)
        trend_z_30 = (
            float(ret_30 / max(rv_30, EPSILON))
            if ret_30 is not None and rv_30 is not None
            else None
        )
        ma_50 = _sma(prior, 50)
        ma_200 = _sma(prior, 200)
        efficiency_30 = _efficiency_30(prior)
        direction_flip_30 = _direction_flip_30(prior)
        rv_30d_percentile_365 = _prior_percentile(
            rv_30,
            [v for v in rv30_so_far[-365:] if v is not None],
        )
        rv30_so_far.append(rv_30)

        rows.append(
            {
                "classifier_version": CLASSIFIER_VERSION,
                "run_id": run_id,
                "signal_ts": signal_ts,
                "symbol": symbol,
                "timeframe": timeframe,
                "feature_ts": feature_ts,
                "feature_bar_ms": BAR_MS_1D,
                "source_table": "market.klines",
                "source_endpoint": "stored_daily_kline",
                "close_prior": close_prior,
                "ret_30d": _none_if_nan(ret_30),
                "ret_90d": _none_if_nan(ret_90),
                "rv_30d": _none_if_nan(rv_30),
                "rv_90d": _none_if_nan(rv_90),
                "trend_z_30": _none_if_nan(trend_z_30),
                "ma_50": _none_if_nan(ma_50),
                "ma_200": _none_if_nan(ma_200),
                "efficiency_30": _none_if_nan(efficiency_30),
                "direction_flip_30": _none_if_nan(direction_flip_30),
                "rv_30d_percentile_365": _none_if_nan(rv_30d_percentile_365),
                "context_bars": int(len(prior)),
                "feature_rules_digest": digest,
            }
        )
    return rows


def high_vol_trigger(row: Mapping[str, Any]) -> bool:
    pct = row.get("rv_30d_percentile_365")
    if pct is not None and _finite(pct):
        return float(pct) >= 0.80
    rv30 = row.get("rv_30d")
    rv90 = row.get("rv_90d")
    return bool(
        rv30 is not None
        and rv90 is not None
        and _finite(rv30)
        and _finite(rv90)
        and float(rv90) > 0
        and float(rv30) >= 1.5 * float(rv90)
    )


def classify_feature_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """把 feature row 分類成 V127 label row。"""
    context_bars = int(row.get("context_bars") or 0)
    insufficient = context_bars < 90
    close_prior = row.get("close_prior")
    ma50 = row.get("ma_50")
    ma200 = row.get("ma_200")
    ret90 = row.get("ret_90d")
    trend = row.get("trend_z_30")
    high_vol = high_vol_trigger(row)

    main = "insufficient_context"
    if not insufficient and all(_finite(v) for v in (close_prior, ma50, ret90, trend)):
        bull = (
            float(ret90) >= 0.15
            and float(trend) >= 0.8
            and float(close_prior) > float(ma50)
            and (ma200 is None or float(ma50) >= float(ma200))
        )
        bear = (
            float(ret90) <= -0.15
            and float(trend) <= -0.8
            and float(close_prior) < float(ma50)
            and (ma200 is None or float(ma50) <= float(ma200))
        )
        if bull:
            main = "bull"
        elif bear:
            main = "bear"
        elif high_vol:
            main = "high-vol"
        elif (
            row.get("efficiency_30") is not None
            and row.get("direction_flip_30") is not None
            and float(row["efficiency_30"]) < 0.25
            and float(row["direction_flip_30"]) >= 0.45
        ):
            main = "chop"
        else:
            main = "range"

    flags = {name: False for name in OVERLAY_FLAG_NAMES}
    flags["high_vol_overlay"] = bool(high_vol)
    flags["insufficient_context"] = bool(insufficient)
    return {
        **{k: row.get(k) for k in row.keys()},
        "main_regime": main,
        "market_anchor_regime": None,
        "high_vol_overlay": bool(high_vol),
        "overlay_flags": flags,
        "insufficient_context": bool(insufficient),
    }


def attach_market_anchor(
    label_rows: Sequence[Mapping[str, Any]],
    *,
    anchor_symbol: str = "BTCUSDT",
) -> list[dict[str, Any]]:
    """把 BTCUSDT 同 signal_ts 的 main_regime denormalize 到所有 row。"""
    anchor = {
        (r.get("timeframe"), r.get("signal_ts")): r.get("main_regime")
        for r in label_rows
        if r.get("symbol") == anchor_symbol
    }
    out = []
    for row in label_rows:
        r = dict(row)
        r["market_anchor_regime"] = anchor.get((r.get("timeframe"), r.get("signal_ts")))
        out.append(r)
    return out


def validate_label_row(row: Mapping[str, Any]) -> None:
    """V127 row 最小 vocabulary 檢查；防 V002 詞表混入。"""
    main = str(row.get("main_regime") or "")
    if main not in VALID_MAIN_REGIMES:
        raise ValueError(f"invalid_aeg_regime:{main}")
    anchor = row.get("market_anchor_regime")
    if anchor is not None and str(anchor) not in VALID_MAIN_REGIMES:
        raise ValueError(f"invalid_aeg_anchor_regime:{anchor}")


def build_transition_rows(label_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """由 label rows 產 regime transition rows。"""
    out: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for row in label_rows:
        by_key.setdefault((str(row.get("symbol")), str(row.get("timeframe"))), []).append(row)
    for (symbol, timeframe), rows in by_key.items():
        prev: Optional[Mapping[str, Any]] = None
        for row in sorted(rows, key=lambda r: r["signal_ts"]):
            if prev is not None and prev.get("main_regime") != row.get("main_regime"):
                out.append(
                    {
                        "classifier_version": CLASSIFIER_VERSION,
                        "run_id": row.get("run_id"),
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "transition_ts": row.get("signal_ts"),
                        "from_regime": prev.get("main_regime"),
                        "to_regime": row.get("main_regime"),
                        "trigger_feature": {
                            name: row.get(name)
                            for name in FEATURE_NAMES
                            if row.get(name) is not None
                        },
                    }
                )
            prev = row
    return out


def build_label_rows(
    closes_by_symbol: Mapping[str, Sequence[tuple[dt.datetime, float]]],
    *,
    run_id: str,
    window_start: dt.datetime | None = None,
    window_end: dt.datetime | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """closes panel → V127 label rows + transition rows。"""
    rows: list[dict[str, Any]] = []
    for symbol, closes in sorted(closes_by_symbol.items()):
        features = compute_feature_rows_for_symbol(symbol, closes, run_id=run_id)
        rows.extend(classify_feature_row(r) for r in features)
    rows = attach_market_anchor(rows)
    if window_start is not None:
        ws = _utc(window_start)
        rows = [r for r in rows if r["signal_ts"] >= ws]
    if window_end is not None:
        we = _utc(window_end)
        rows = [r for r in rows if r["signal_ts"] <= we]
    for row in rows:
        validate_label_row(row)
    return rows, build_transition_rows(rows)

"""AEG regime feature lineage helpers.

MODULE_NOTE:
  模塊用途：產生並驗證 AEG-S0 §2.5 feature_lineage rows。這是防 leakage 的
    load-bearing gate：每個 scoring feature 的 source/bar timestamp 必須至少落後
    signal_ts 一根完整 source bar。
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Mapping, Sequence

from . import BAR_MS_1D, CLASSIFIER_VERSION, FEATURE_NAMES


def _iso(ts: Any) -> str | None:
    if ts is None:
        return None
    if isinstance(ts, dt.datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=dt.timezone.utc)
        return ts.astimezone(dt.timezone.utc).isoformat()
    return str(ts)


def _lag_ms(signal_ts: dt.datetime, source_ts: dt.datetime | None) -> int | None:
    if source_ts is None:
        return None
    if signal_ts.tzinfo is None:
        signal_ts = signal_ts.replace(tzinfo=dt.timezone.utc)
    if source_ts.tzinfo is None:
        source_ts = source_ts.replace(tzinfo=dt.timezone.utc)
    return int((signal_ts.astimezone(dt.timezone.utc) - source_ts.astimezone(dt.timezone.utc)).total_seconds() * 1000)


def build_feature_lineage_rows(label_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """V127 label rows → feature_lineage artifact rows。"""
    out: list[dict[str, Any]] = []
    for row in label_rows:
        signal_ts = row["signal_ts"]
        feature_ts = row.get("feature_ts")
        lag = _lag_ms(signal_ts, feature_ts)
        for feature_name in FEATURE_NAMES:
            # insufficient_context row 也保留 lineage；feature_ts=None 時明確 violation。
            violation = 1 if lag is None or lag < BAR_MS_1D else 0
            out.append(
                {
                    "run_id": row.get("run_id"),
                    "classifier_version": CLASSIFIER_VERSION,
                    "signal_ts_utc": _iso(signal_ts),
                    "symbol": row.get("symbol"),
                    "feature_name": feature_name,
                    "source_table": row.get("source_table") or "market.klines",
                    "source_endpoint": row.get("source_endpoint") or "stored_daily_kline",
                    "source_ts_utc": _iso(feature_ts),
                    "bar_close_ts_utc": _iso(feature_ts),
                    "feature_bar_ms": int(row.get("feature_bar_ms") or BAR_MS_1D),
                    "lookback_bars": _lookback_for_feature(feature_name),
                    "join_rule_version": "aeg_regime_lineage_shift1.v0.1",
                    "lag_ms": lag,
                    "leak_violation_count": violation,
                }
            )
    return out


def validate_feature_lineage(
    lineage_rows: Sequence[Mapping[str, Any]],
    *,
    allow_insufficient_context: bool = False,
) -> tuple[bool, str]:
    """驗 lineage 是否全數滿足 ``lag_ms >= feature_bar_ms`` 且 violation=0。"""
    bad = []
    for row in lineage_rows:
        lag = row.get("lag_ms")
        bar = int(row.get("feature_bar_ms") or BAR_MS_1D)
        vio = int(row.get("leak_violation_count") or 0)
        if lag is None and allow_insufficient_context:
            continue
        if lag is None or int(lag) < bar or vio != 0:
            bad.append(row)
    if bad:
        first = bad[0]
        return (
            False,
            "feature_lineage_leak:"
            f"{first.get('symbol')}:{first.get('feature_name')}:"
            f"lag_ms={first.get('lag_ms')}:bar_ms={first.get('feature_bar_ms')}",
        )
    return True, "pass"


def _lookback_for_feature(feature_name: str) -> int:
    return {
        "ret_30d": 30,
        "ret_90d": 90,
        "rv_30d": 30,
        "rv_90d": 90,
        "trend_z_30": 30,
        "ma_50": 50,
        "ma_200": 200,
        "efficiency_30": 30,
        "direction_flip_30": 30,
        "rv_30d_percentile_365": 365,
    }.get(feature_name, 0)

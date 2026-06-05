"""AEG-S2 component (a) regime label runner.

MODULE_NOTE:
  模塊用途：把 AEG-S0 凍結的 ``aeg_regime_v0.1.0`` 分類器落成 batch research
    runner。輸入為已持久化 daily kline，輸出 ``research.aeg_regime_labels`` 對齊
    row、``feature_lineage`` artifact、transition artifact；默認只寫本地 artifact，
    只有 CLI 顯式 ``--write-db`` 才寫 V127 research 表。
  硬邊界：
    - 不重用 V002 ``market.regime_snapshots``；V002 是 intraday/dormant/vocab 不同。
    - 所有 feature 對 signal timestamp 都用前一根 complete daily bar，不看 current
      bar、不看未來分布。
    - 這是 research evidence builder，不碰 order / auth / lease / IPC / runtime 交易面。
"""

from __future__ import annotations

import hashlib
import json


CLASSIFIER_VERSION = "aeg_regime_v0.1.0"
RUNNER_VERSION = "aeg_regime_runner.v0.1"
LABEL_SCHEMA_VERSION = "aeg.regime_label.v0.1"
TRANSITION_SCHEMA_VERSION = "aeg.regime_transition.v0.1"
LINEAGE_SCHEMA_VERSION = "aeg.feature_lineage.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

BAR_MS_1D = 86_400_000
EPSILON = 1e-12

FEATURE_NAMES = (
    "ret_30d",
    "ret_90d",
    "rv_30d",
    "rv_90d",
    "trend_z_30",
    "ma_50",
    "ma_200",
    "efficiency_30",
    "direction_flip_30",
    "rv_30d_percentile_365",
)

VALID_MAIN_REGIMES = (
    "bull",
    "bear",
    "high-vol",
    "chop",
    "range",
    "insufficient_context",
)

OVERLAY_FLAG_NAMES = (
    "bull_heavy",
    "bear_heavy",
    "range_or_chop_heavy",
    "high_vol_overlay",
    "high_vol_heavy",
    "2024_dominated",
    "stale_year_dominated",
    "recent_window_weak",
    "low_breadth",
    "insufficient_context",
    "funding_extreme",
    "oi_expansion",
)

FEATURE_RULES = {
    "classifier_version": CLASSIFIER_VERSION,
    "epsilon": EPSILON,
    "pit_rule": "all_features_use_previous_complete_daily_bar",
    "minimum_context": {"full": 200, "reduced": 90},
    "rules": {
        "bull": ["ret_90d>=0.15", "trend_z_30>=0.8", "close_prior>ma_50"],
        "bear": ["ret_90d<=-0.15", "trend_z_30<=-0.8", "close_prior<ma_50"],
        "high-vol": ["rv_30d_percentile_365>=0.80", "rv_30d>=1.5*rv_90d"],
        "chop": ["efficiency_30<0.25", "direction_flip_30>=0.45"],
    },
    "percentile": "prior_window_only_excluding_current",
}


def feature_rules_digest() -> str:
    """凍結 feature/threshold 定義的 canonical SHA-256。"""
    payload = json.dumps(
        FEATURE_RULES,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "BAR_MS_1D",
    "CLASSIFIER_VERSION",
    "EPSILON",
    "FEATURE_NAMES",
    "LABEL_SCHEMA_VERSION",
    "LINEAGE_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "OVERLAY_FLAG_NAMES",
    "RUNNER_VERSION",
    "TRANSITION_SCHEMA_VERSION",
    "VALID_MAIN_REGIMES",
    "feature_rules_digest",
]

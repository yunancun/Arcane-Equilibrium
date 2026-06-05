"""AEG execution-realism artifact builder.

MODULE_NOTE:
  模塊用途：把候選的費率、滑點、maker fill、容量、延遲與訂單可用性證據
    正規化成 ``execution_realism.json``，供 AEG robustness matrix 消費。
  硬邊界：artifact-only；不連 DB、不碰 runtime、不讀交易授權、不下單。輸入
    的 ``status`` 不被信任，PASS/FAIL 一律由本 package 重新計算。
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_execution_realism.v0.1"
EXECUTION_REALISM_SCHEMA_VERSION = "aeg.execution_realism.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

EMPIRICAL_EVIDENCE_SOURCE_TIERS = frozenset({
    "calibrated_replay",
    "demo_fills",
    "live_demo_fills",
    "live_fills",
})

ORDER_STYLES = frozenset({"maker", "taker", "mixed"})

MIN_SAMPLE_COUNT = 30
MIN_MAKER_FILL_RATE = 0.60
MAX_LATENCY_MS_P95 = 2_000.0
MAX_PARTICIPATION_RATE_P95 = 0.05
MAX_ADVERSE_SELECTION_BPS_P95 = 3.50

__all__ = [
    "EMPIRICAL_EVIDENCE_SOURCE_TIERS",
    "EXECUTION_REALISM_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "MAX_ADVERSE_SELECTION_BPS_P95",
    "MAX_LATENCY_MS_P95",
    "MAX_PARTICIPATION_RATE_P95",
    "MIN_MAKER_FILL_RATE",
    "MIN_SAMPLE_COUNT",
    "ORDER_STYLES",
    "RUNNER_VERSION",
]

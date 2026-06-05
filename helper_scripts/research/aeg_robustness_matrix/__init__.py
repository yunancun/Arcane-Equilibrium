"""AEG-S2 component (c) robustness matrix builder.

MODULE_NOTE:
  模塊用途：消費 AEG regime runner + breadth ladder artifact，產出 S0 §2.9
    ``verdict_matrix.csv/.parquet``。這是五軸 promotion gate 的 artifact-only
    builder，不寫 DB、不碰交易路徑。
  重要邊界：第一版只使用上游 artifact 已明確提供的證據；若缺 per-regime PnL、
    freshness 或 execution-realism，就在矩陣中 fail-closed 標成
    ``insufficient evidence``，不把 aggregate breadth 結果冒充成 regime-sliced alpha。
"""

from __future__ import annotations

VERDICT_GATE_VERSION = "aeg_verdict_gate_v0.1.0"
RUNNER_VERSION = "aeg_robustness_matrix.v0.1"
MATRIX_SCHEMA_VERSION = "aeg.verdict_matrix.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

FINAL_LABELS = (
    "durable-alpha candidate",
    "regime-bet / learning-only",
    "stale-data artifact",
    "breadth-limited",
    "insufficient evidence",
    "kill",
)

MATRIX_COLUMNS = (
    "run_id",
    "candidate_id",
    "strategy_family",
    "parameter_cell_id",
    "symbol",
    "cohort_id",
    "regime",
    "market_anchor_regime",
    "overlay_flags",
    "breadth_cohort",
    "freshness_bucket",
    "survivorship_mode",
    "execution_realism_mode",
    "coverage_gate_status",
    "feature_lineage_status",
    "gross_bps",
    "cost_bps",
    "net_bps",
    "net_to_cost_ratio",
    "is_sharpe",
    "oos_sharpe",
    "psr_0",
    "dsr_k",
    "pbo",
    "multiple_test_family",
    "k_trials",
    "n_independent",
    "sample_unit",
    "recent_90d_net_bps",
    "recent_180d_net_bps",
    "non_bull_independent_pass",
    "final_label",
    "reject_reasons",
)

NON_BULL_REGIMES = frozenset({"bear", "range", "chop", "high-vol"})

__all__ = [
    "FINAL_LABELS",
    "MANIFEST_SCHEMA_VERSION",
    "MATRIX_COLUMNS",
    "MATRIX_SCHEMA_VERSION",
    "NON_BULL_REGIMES",
    "RUNNER_VERSION",
    "VERDICT_GATE_VERSION",
]

"""AEG candidate metrics adapter.

MODULE_NOTE:
  模塊用途：把候選診斷報告中的 selected variant / per-regime PnL 指標正規化成
    artifact rows，作為 robustness matrix 後續接入的候選級 metrics contract。
  邊界：不把 mean_daily_bps 冒充為 matrix net_bps，也不把 n_days 冒充為
    n_independent；缺 matrix-critical 欄位時 fail-closed 標記。artifact-only，
    0 DB / 0 runtime / 0 trading path。
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_candidate_metrics.v0.2"
REGIME_METRICS_SCHEMA_VERSION = "aeg.candidate_regime_metrics.v0.2"
SUMMARY_SCHEMA_VERSION = "aeg.candidate_metrics_summary.v0.2"
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

REGIME_METRIC_COLUMNS = (
    "run_id",
    "candidate_id",
    "strategy_family",
    "parameter_cell_id",
    "source_report_type",
    "selected_variant",
    "regime",
    "n_days",
    "gross_bps",
    "cost_bps",
    "net_bps",
    "net_to_cost_ratio",
    "mean_daily_bps",
    "annualized_net_sharpe",
    "oos_sharpe",
    "psr_0",
    "dsr_k",
    "pbo",
    "k_trials",
    "n_independent",
    "sample_unit",
    "recent_90d_net_bps",
    "recent_180d_net_bps",
    "freshness_bucket",
    "metric_status",
    "reject_reasons",
)

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "REGIME_METRIC_COLUMNS",
    "REGIME_METRICS_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SUMMARY_SCHEMA_VERSION",
]

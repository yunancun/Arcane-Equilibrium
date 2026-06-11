"""AEG-S3 candidate direct rows builder.

MODULE_NOTE:
  模塊用途：把候選擁有的 leak-free 獨立樣本 returns 轉成
    `aeg_candidate_metrics` 已支援的 direct `candidate_regime_metrics` report。
  邊界：artifact-only；不連 DB、不打 Bybit、不匯入 control_api runtime；不把
    mean_daily_bps 合成 net_bps，也不把 row count 冒充 n_independent。
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_candidate_rows.v0.1"
DIRECT_REPORT_SCHEMA_VERSION = "aeg.s3_candidate_direct_report.v0.1"
SAMPLE_RETURNS_SCHEMA_VERSION = "aeg.s3_candidate_sample_returns.v0.1"
DAILY_RETURNS_SCHEMA_VERSION = "aeg.s3_candidate_daily_returns.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.s3_candidate_rows_manifest.v0.1"

SAMPLE_COLUMNS = (
    "sample_id",
    "sample_ts_utc",
    "sample_date",
    "regime",
    "independence_bucket",
    "gross_bps",
    "cost_bps",
    "net_bps",
    "is_oos",
)

__all__ = [
    "DAILY_RETURNS_SCHEMA_VERSION",
    "DIRECT_REPORT_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SAMPLE_COLUMNS",
    "SAMPLE_RETURNS_SCHEMA_VERSION",
]

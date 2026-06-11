"""AEG-S3 OI delta evidence producer.

MODULE_NOTE:
  模塊用途：把離線 OI/price panel export 轉成 `aeg_s3_candidate_rows`
    可消費的 candidate evidence JSON。
  邊界：artifact-only；不連資料庫、不打 Bybit、不匯入 runtime；保留 OI delta
    standalone 成本牆，不把低毛利樣本改寫成可晉升證據。
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_oi_delta.v0.1"
EVIDENCE_SCHEMA_VERSION = "aeg.s3_oi_delta_evidence.v0.1"
SUMMARY_SCHEMA_VERSION = "aeg.s3_oi_delta_summary.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.s3_oi_delta_manifest.v0.1"

SAMPLE_UNIT = "oi_delta_rebalance_window"
STRATEGY_FAMILY = "oi_delta"

__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SAMPLE_UNIT",
    "STRATEGY_FAMILY",
    "SUMMARY_SCHEMA_VERSION",
]

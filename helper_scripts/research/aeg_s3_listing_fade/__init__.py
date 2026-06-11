"""AEG-S3 listing fade evidence producer.

MODULE_NOTE:
  模塊用途：把 Gate-B/listing capture 離線 artifact 轉成
    `aeg_s3_candidate_rows` 可消費的 candidate evidence JSON。
  邊界：artifact-only；不連 DB、不打 Bybit、不匯入 runtime；不把 connection-only
    Gate-B 結果或 missing/slow capture 冒充真樣本。
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_listing_fade.v0.1"
EVIDENCE_SCHEMA_VERSION = "aeg.s3_listing_fade_evidence.v0.1"
SUMMARY_SCHEMA_VERSION = "aeg.s3_listing_fade_summary.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.s3_listing_fade_manifest.v0.1"

SAMPLE_UNIT = "listing_event_window"
STRATEGY_FAMILY = "listing_fade"

__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SAMPLE_UNIT",
    "STRATEGY_FAMILY",
    "SUMMARY_SCHEMA_VERSION",
]

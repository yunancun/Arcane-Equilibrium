"""AEG-S3 funding revive evidence producer.

MODULE_NOTE:
  Purpose: convert an offline funding/price panel export into candidate
    evidence JSON consumable by `aeg_s3_candidate_rows`.
  Boundary: artifact-only; does not connect to runtime services, exchanges, or
    databases; does not reopen the closed cross-sectional funding tilt thesis.
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_funding_revive.v0.1"
EVIDENCE_SCHEMA_VERSION = "aeg.s3_funding_revive_evidence.v0.1"
SUMMARY_SCHEMA_VERSION = "aeg.s3_funding_revive_summary.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.s3_funding_revive_manifest.v0.1"

SAMPLE_UNIT = "funding_revive_event_window"
STRATEGY_FAMILY = "funding_revive"

__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SAMPLE_UNIT",
    "STRATEGY_FAMILY",
    "SUMMARY_SCHEMA_VERSION",
]

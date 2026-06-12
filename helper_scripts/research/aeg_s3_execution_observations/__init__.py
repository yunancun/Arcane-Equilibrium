"""AEG-S3 execution-observation producers.

This package converts event-capture artifacts into the JSONL observation format
consumed by ``aeg_s3_event_execution_realism``.
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_execution_observations.v0.1"
OBSERVATION_SCHEMA_VERSION = "aeg.s3_execution_observation.v0.1"
SUMMARY_SCHEMA_VERSION = "aeg.s3_execution_observations_summary.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "OBSERVATION_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SUMMARY_SCHEMA_VERSION",
]


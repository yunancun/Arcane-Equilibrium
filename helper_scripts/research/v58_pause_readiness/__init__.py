"""V5.8 pause readiness checker.

This package inspects repository-local V5.8/AEG handoff state. It is
artifact-only: no DB connection, no exchange call, no runtime mutation.
"""

from __future__ import annotations

RUNNER_VERSION = "v58_pause_readiness.v0.1"
SUMMARY_SCHEMA_VERSION = "v58.pause_readiness_summary.v0.1"
MANIFEST_SCHEMA_VERSION = "v58.pause_readiness_manifest.v0.1"

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SUMMARY_SCHEMA_VERSION",
]

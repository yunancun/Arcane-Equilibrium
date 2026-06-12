"""AEG-S3 Gate-B preflight and artifact locator.

The package inspects local artifacts and builds the recommended full-chain
Gate-B command. It does not collect market data, call Bybit, write DB rows, or
touch runtime state.
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_gate_b_preflight.v0.3"
SUMMARY_SCHEMA_VERSION = "aeg.s3_gate_b_preflight_summary.v0.3"
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SUMMARY_SCHEMA_VERSION",
]

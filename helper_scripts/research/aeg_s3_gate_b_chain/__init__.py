"""AEG-S3 Gate-B evidence-chain orchestrator.

This package wires existing artifact-only AEG-S3 producers into a repeatable
Gate-B listing_fade chain. It does not collect data, call Bybit, write DB rows,
or trigger runtime actions.
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_gate_b_chain.v0.1"
SUMMARY_SCHEMA_VERSION = "aeg.s3_gate_b_chain_summary.v0.1"
MANIFEST_SCHEMA_VERSION = "aeg.alpha_history_run_manifest.v0.1"

__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "RUNNER_VERSION",
    "SUMMARY_SCHEMA_VERSION",
]


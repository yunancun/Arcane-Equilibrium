"""AEG-S3 event-candidate breadth adapter.

This package converts single-symbol AEG-S3 candidate evidence into the existing
AEG-S2 breadth ladder artifact format by evaluating the evidence against FND-2
point-in-time universe tiers.
"""

from __future__ import annotations

RUNNER_VERSION = "aeg_s3_event_breadth.v0.1"
SUMMARY_SCHEMA_VERSION = "aeg.s3_event_breadth_summary.v0.1"

SUPPORTED_CANDIDATE_SYMBOL_FIELDS = {
    "funding_revive": ("symbol",),
    "listing_fade": ("source_symbol", "symbol"),
}

__all__ = [
    "RUNNER_VERSION",
    "SUMMARY_SCHEMA_VERSION",
    "SUPPORTED_CANDIDATE_SYMBOL_FIELDS",
]

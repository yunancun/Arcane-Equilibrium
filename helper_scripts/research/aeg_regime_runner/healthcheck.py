"""AEG regime runner healthchecks."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import CLASSIFIER_VERSION


def check_regime_run_summary(summary: Mapping[str, Any]) -> tuple[str, str]:
    """最小 freshness/lineage healthcheck；給 harness 與排程外掛復用。"""
    if summary.get("classifier_version") != CLASSIFIER_VERSION:
        return "FAIL", "classifier_version_mismatch"
    if summary.get("lineage_status") != "pass":
        return "FAIL", f"lineage_status={summary.get('lineage_status')}"
    if int(summary.get("label_count") or 0) <= 0:
        return "FAIL", "no_regime_labels"
    if int(summary.get("anchor_label_count") or 0) <= 0:
        return "WARN", "btc_anchor_missing"
    return "PASS", "ok"


def regime_counts(labels: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in labels:
        key = str(row.get("main_regime") or "missing")
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))

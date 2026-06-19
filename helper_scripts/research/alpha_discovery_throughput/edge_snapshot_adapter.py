"""AEG verdict matrix -> Rust edge_estimates snapshot adapter."""

from __future__ import annotations

import datetime as dt
import json
import math
from statistics import mean
from typing import Any

from . import EDGE_SNAPSHOT_ADAPTER_SCHEMA_VERSION, RUNNER_VERSION

NON_BULL_REGIMES = {"bear", "chop", "crash", "high_vol", "mean_reverting", "sideways"}


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _int(value: Any) -> int | None:
    out = _float(value)
    return int(out) if out is not None else None


def _rejects(row: dict[str, Any]) -> list[str]:
    raw = row.get("reject_reasons")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, list):
                return [str(item) for item in loaded]
        except json.JSONDecodeError:
            return [raw]
    return []


def row_is_live_grade(row: dict[str, Any]) -> bool:
    """只有 durable, concrete, non-bull regime row 能轉正 edge cell。"""
    if str(row.get("final_label")) != "durable-alpha candidate":
        return False
    symbol = str(row.get("symbol") or "").strip()
    if not symbol or symbol == "__AGGREGATE__":
        return False
    regime = str(row.get("regime") or "").strip()
    if regime == "all_regimes" or regime not in NON_BULL_REGIMES:
        return False
    net = _float(row.get("net_bps"))
    n_ind = _int(row.get("n_independent"))
    psr = _float(row.get("psr_0"))
    dsr = _float(row.get("dsr_k"))
    pbo = _float(row.get("pbo"))
    return (
        net is not None and net > 0
        and n_ind is not None and n_ind >= 30
        and psr is not None and psr >= 0.95
        and dsr is not None and dsr >= 0.95
        and pbo is not None and pbo < 0.5
        and not _rejects(row)
    )


def _cell_key(row: dict[str, Any]) -> str:
    return f"{row.get('strategy_family')}::{row.get('symbol')}"


def build_edge_snapshot(
    rows: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    include_rejected_zero_cells: bool = False,
) -> dict[str, Any]:
    """產生 Rust `EdgeEstimates` 可讀 snapshot。"""
    now = now_utc or dt.datetime.now(dt.timezone.utc)
    snapshot: dict[str, Any] = {
        "_meta": {
            "schema_version": EDGE_SNAPSHOT_ADAPTER_SCHEMA_VERSION,
            "runner_version": RUNNER_VERSION,
            "source": "aeg_robustness_matrix",
            "updated_at": now.astimezone(dt.timezone.utc).isoformat(),
            "n_cells": 0,
            "grand_mean_bps": 0.0,
            "policy": "only_live_grade_durable_non_bull_concrete_rows_get_positive_runtime_bps",
        }
    }
    positives: list[float] = []
    for row in rows:
        key = _cell_key(row)
        if "None::" in key or key.endswith("::") or key.startswith("None::"):
            continue
        net = _float(row.get("net_bps")) or 0.0
        n_ind = _int(row.get("n_independent")) or 0
        if row_is_live_grade(row):
            runtime_bps = net
            validation_passed = True
            validation_reason = "aeg_durable_alpha_candidate"
            positives.append(runtime_bps)
        elif include_rejected_zero_cells:
            runtime_bps = 0.0
            validation_passed = False
            validation_reason = ",".join(_rejects(row)) or "not_live_grade_aeg_row"
        else:
            continue
        snapshot[key] = {
            "runtime_bps": round(runtime_bps, 8),
            "shrunk_bps": round(runtime_bps, 8),
            "validation_passed": validation_passed,
            "validation_reason": validation_reason,
            "n": n_ind,
            "win_rate": 0.5,
            "std_bps": abs(net),
            "source_regime": row.get("regime"),
            "parameter_cell_id": row.get("parameter_cell_id"),
        }
    snapshot["_meta"]["n_cells"] = len(snapshot) - 1
    snapshot["_meta"]["grand_mean_bps"] = round(mean(positives), 8) if positives else 0.0
    return snapshot


__all__ = ["build_edge_snapshot", "row_is_live_grade"]

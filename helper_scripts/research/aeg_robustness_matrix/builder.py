"""AEG robustness matrix 純函數核心。

MODULE_NOTE:
  模塊用途：讀 regime/breadth artifact payload，生成 S0 §2.9 最小欄位的
    ``verdict_matrix`` rows + summary。此層只做 deterministic gate 合成，0 DB / 0 IO
    寫入；artifact 寫入在 ``artifact.py``。
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Optional

from . import MATRIX_COLUMNS, NON_BULL_REGIMES, VERDICT_GATE_VERSION


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _json_cell(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _int_or_none(value: Any) -> Optional[int]:
    f = _float_or_none(value)
    if f is None:
        return None
    return int(f)


def _status_is_pass(payload: dict[str, Any]) -> bool:
    status = payload.get("status")
    return str(status).upper() == "PASS"


def load_regime_artifact(run_dir: Path) -> dict[str, Any]:
    """讀 regime artifact（CSV + summary）。"""
    run_dir = Path(run_dir)
    labels = _read_csv(run_dir / "regime_labels.csv")
    summary = _read_json(run_dir / "regime_summary.json")
    return {"run_dir": run_dir, "labels": labels, "summary": summary}


def load_breadth_artifact(run_dir: Path) -> dict[str, Any]:
    """讀 breadth artifact（CSV + summary）。"""
    run_dir = Path(run_dir)
    rows = _read_csv(run_dir / "breadth_ladder.csv")
    summary = _read_json(run_dir / "breadth_ladder_summary.json")
    return {"run_dir": run_dir, "rows": rows, "summary": summary}


def load_execution_realism(path: Optional[Path]) -> dict[str, Any]:
    """讀 execution_realism.json；缺失時回 fail-closed payload。"""
    if path is None:
        return {
            "execution_realism_mode": "missing",
            "status": "FAIL",
            "reject_reason": "missing_execution_realism",
        }
    payload = _read_json(Path(path))
    mode = (
        payload.get("execution_realism_mode")
        or payload.get("mode")
        or payload.get("assumption_mode")
        or "provided_unspecified"
    )
    return {
        **payload,
        "execution_realism_mode": mode,
        "status": payload.get("status", "PASS"),
    }


def regime_slices(regime: dict[str, Any]) -> list[dict[str, Any]]:
    """從 regime labels 建 axis slices；加入 all_regimes 診斷聚合列。"""
    labels = regime["labels"]
    counts = Counter((row.get("main_regime") or "unknown").strip() for row in labels)
    counts = Counter({k: v for k, v in counts.items() if k})
    slices = [
        {
            "regime": "all_regimes",
            "market_anchor_regime": "mixed",
            "overlay_flags": {"aggregate": True, "slice_label_count": sum(counts.values())},
            "is_aggregate": True,
        }
    ]
    for name in sorted(counts):
        slices.append(
            {
                "regime": name,
                "market_anchor_regime": _dominant_anchor(labels, name),
                "overlay_flags": {"slice_label_count": counts[name]},
                "is_aggregate": False,
            }
        )
    return slices


def _dominant_anchor(labels: list[dict[str, str]], regime: str) -> str:
    anchors = Counter(
        (row.get("market_anchor_regime") or "unknown").strip()
        for row in labels
        if (row.get("main_regime") or "unknown").strip() == regime
    )
    if not anchors:
        return "unknown"
    return anchors.most_common(1)[0][0]


def _coverage_status(regime_summary: dict[str, Any], breadth_summary: dict[str, Any]) -> str:
    regime_hc = regime_summary.get("healthcheck") or {}
    breadth_hc = breadth_summary.get("survivorship_healthcheck") or {}
    if regime_hc and not _status_is_pass(regime_hc):
        return "FAIL"
    if breadth_hc and not _status_is_pass(breadth_hc):
        return "FAIL"
    if not regime_summary.get("label_count"):
        return "FAIL"
    return "PASS"


def _feature_lineage_status(regime_summary: dict[str, Any]) -> str:
    status = str(regime_summary.get("lineage_status") or "").upper()
    if status == "PASS":
        return "PASS"
    health = regime_summary.get("healthcheck") or {}
    lineage = health.get("lineage_status")
    if str(lineage).upper() == "PASS":
        return "PASS"
    return "FAIL"


def _survivorship_mode(breadth_summary: dict[str, Any]) -> str:
    hc = breadth_summary.get("survivorship_healthcheck") or {}
    inherited = breadth_summary.get("survivorship_inherited_from_fnd2")
    delisted_total = _int_or_none(breadth_summary.get("delisted_proof_total")) or 0
    if _status_is_pass(hc) and inherited is True and delisted_total >= 1:
        return "pit_fnd2_delisted_proof"
    if _status_is_pass(hc) and inherited is True:
        return "pit_fnd2_proven_none"
    return "current_survivor_or_unverified"


def _reject_reasons(
    *,
    breadth_row: dict[str, str],
    slice_row: dict[str, Any],
    coverage_gate_status: str,
    feature_lineage_status: str,
    survivorship_mode: str,
    execution_realism: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if coverage_gate_status != "PASS":
        reasons.append("coverage_gate_not_pass")
    if feature_lineage_status != "PASS":
        reasons.append("feature_lineage_not_pass")
    if slice_row["is_aggregate"]:
        reasons.append("aggregate_not_regime_slice")
    else:
        # breadth runner 目前沒有 per-regime candidate PnL；不能把 aggregate edge 塞進 regime slice。
        reasons.append("missing_regime_slice_metrics")

    net_bps = _float_or_none(breadth_row.get("net_bps")) if slice_row["is_aggregate"] else None
    net_to_cost = (
        _float_or_none(breadth_row.get("net_to_cost_ratio"))
        if slice_row["is_aggregate"]
        else None
    )
    n_independent = (
        _int_or_none(breadth_row.get("n_independent"))
        if slice_row["is_aggregate"]
        else None
    )

    if net_bps is None:
        reasons.append("missing_net_bps")
    elif net_bps <= 0:
        reasons.append("net_bps_non_positive")
    if net_to_cost is None:
        reasons.append("missing_net_to_cost_ratio")
    elif net_to_cost < 2.0:
        reasons.append("net_to_cost_ratio_below_2")
    if n_independent is None:
        reasons.append("missing_n_independent")
    elif n_independent < 30:
        reasons.append("n_independent_below_30")

    for metric in ("psr_0", "dsr_k", "pbo", "is_sharpe", "oos_sharpe"):
        if _float_or_none(breadth_row.get(metric)) is None:
            reasons.append(f"missing_{metric}")

    reasons.append("missing_recent_90d_net_bps")
    reasons.append("missing_recent_180d_net_bps")

    if survivorship_mode == "current_survivor_or_unverified":
        reasons.append("survivorship_not_pit_verified")
    if str(execution_realism.get("status", "")).upper() != "PASS":
        reasons.append(execution_realism.get("reject_reason") or "execution_realism_not_pass")
    if breadth_row.get("excluded_from_promotion") == "true":
        reasons.append("breadth_row_excluded_from_promotion")
    return list(dict.fromkeys(reasons))


def _final_label(reasons: list[str], breadth_summary: dict[str, Any]) -> str:
    if not reasons:
        return "durable-alpha candidate"
    if "net_bps_non_positive" in reasons:
        return "kill"
    if breadth_summary.get("verdict_hint") == "breadth-limited":
        return "breadth-limited"
    if (
        "missing_recent_90d_net_bps" in reasons
        and "missing_regime_slice_metrics" not in reasons
        and "aggregate_not_regime_slice" not in reasons
    ):
        return "stale-data artifact"
    return "insufficient evidence"


def build_matrix(
    *,
    run_id: str,
    regime_artifact: dict[str, Any],
    breadth_artifact: dict[str, Any],
    execution_realism: dict[str, Any],
    strategy_family: str,
    parameter_cell_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """生成 verdict matrix rows + summary。"""
    regime_summary = regime_artifact["summary"]
    breadth_summary = breadth_artifact["summary"]
    coverage = _coverage_status(regime_summary, breadth_summary)
    lineage = _feature_lineage_status(regime_summary)
    survivorship = _survivorship_mode(breadth_summary)

    rows: list[dict[str, Any]] = []
    for breadth_row in breadth_artifact["rows"]:
        for slice_row in regime_slices(regime_artifact):
            reasons = _reject_reasons(
                breadth_row=breadth_row,
                slice_row=slice_row,
                coverage_gate_status=coverage,
                feature_lineage_status=lineage,
                survivorship_mode=survivorship,
                execution_realism=execution_realism,
            )
            aggregate = slice_row["is_aggregate"]
            row = {
                "run_id": run_id,
                "candidate_id": breadth_summary.get("candidate_id") or breadth_row.get("candidate_id"),
                "strategy_family": strategy_family,
                "parameter_cell_id": parameter_cell_id,
                "symbol": "__AGGREGATE__",
                "cohort_id": breadth_row.get("breadth_cohort"),
                "regime": slice_row["regime"],
                "market_anchor_regime": slice_row["market_anchor_regime"],
                "overlay_flags": _json_cell(slice_row["overlay_flags"]),
                "breadth_cohort": breadth_row.get("breadth_cohort"),
                "freshness_bucket": "unmeasured",
                "survivorship_mode": survivorship,
                "execution_realism_mode": execution_realism.get("execution_realism_mode"),
                "coverage_gate_status": coverage,
                "feature_lineage_status": lineage,
                "gross_bps": breadth_row.get("gross_bps") if aggregate else None,
                "cost_bps": breadth_row.get("cost_bps") if aggregate else None,
                "net_bps": breadth_row.get("net_bps") if aggregate else None,
                "net_to_cost_ratio": breadth_row.get("net_to_cost_ratio") if aggregate else None,
                "is_sharpe": breadth_row.get("is_sharpe") if aggregate else None,
                "oos_sharpe": breadth_row.get("oos_sharpe") if aggregate else None,
                "psr_0": breadth_row.get("psr_0") if aggregate else None,
                "dsr_k": breadth_row.get("dsr_k") if aggregate else None,
                "pbo": breadth_row.get("pbo") if aggregate else None,
                "multiple_test_family": breadth_summary.get("candidate_id"),
                "k_trials": breadth_row.get("k_trials") if aggregate else None,
                "n_independent": breadth_row.get("n_independent") if aggregate else None,
                "sample_unit": breadth_row.get("sample_unit") if aggregate else None,
                "recent_90d_net_bps": None,
                "recent_180d_net_bps": None,
                "non_bull_independent_pass": False,
                "final_label": _final_label(reasons, breadth_summary),
                "reject_reasons": _json_cell(reasons),
            }
            rows.append({col: row.get(col) for col in MATRIX_COLUMNS})

    final_counts = Counter(row["final_label"] for row in rows)
    summary = {
        "run_id": run_id,
        "candidate_id": breadth_summary.get("candidate_id"),
        "verdict_gate_version": VERDICT_GATE_VERSION,
        "row_count": len(rows),
        "regime_slice_count": len(regime_slices(regime_artifact)),
        "breadth_row_count": len(breadth_artifact["rows"]),
        "final_label_counts": dict(sorted(final_counts.items())),
        "coverage_gate_status": coverage,
        "feature_lineage_status": lineage,
        "survivorship_mode": survivorship,
        "execution_realism_mode": execution_realism.get("execution_realism_mode"),
        "non_bull_independent_pass": any(
            row["final_label"] == "durable-alpha candidate" and row["regime"] in NON_BULL_REGIMES
            for row in rows
        ),
        "upstream": {
            "regime_run_id": regime_summary.get("run_id"),
            "breadth_run_id": breadth_summary.get("run_id"),
            "fnd2_run_id": breadth_summary.get("fnd2_run_id") or regime_summary.get("fnd2_run_id"),
            "fnd2_universe_id": (
                breadth_summary.get("fnd2_universe_id") or regime_summary.get("fnd2_universe_id")
            ),
        },
    }
    return rows, summary

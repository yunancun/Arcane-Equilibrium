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


def load_candidate_metrics_artifact(run_dir: Optional[Path]) -> dict[str, Any]:
    """讀 candidate metrics artifact；缺失時回空 payload。"""
    if run_dir is None:
        return {"run_dir": None, "rows": [], "summary": {}}
    run_dir = Path(run_dir)
    rows = _read_csv(run_dir / "candidate_regime_metrics.csv")
    summary = _read_json(run_dir / "candidate_metrics_summary.json")
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


def _candidate_metric_index(candidate_metrics: dict[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in candidate_metrics.get("rows") or []:
        regime = (row.get("regime") or "").strip()
        if regime:
            out[regime] = row
    return out


def _cell_metrics(
    *,
    breadth_row: dict[str, str],
    slice_row: dict[str, Any],
    candidate_metric: Optional[dict[str, str]],
) -> dict[str, Any]:
    if slice_row["is_aggregate"]:
        return {
            "gross_bps": breadth_row.get("gross_bps"),
            "cost_bps": breadth_row.get("cost_bps"),
            "net_bps": breadth_row.get("net_bps"),
            "net_to_cost_ratio": breadth_row.get("net_to_cost_ratio"),
            "is_sharpe": breadth_row.get("is_sharpe"),
            "oos_sharpe": breadth_row.get("oos_sharpe"),
            "psr_0": breadth_row.get("psr_0"),
            "dsr_k": breadth_row.get("dsr_k"),
            "pbo": breadth_row.get("pbo"),
            "k_trials": breadth_row.get("k_trials"),
            "n_independent": breadth_row.get("n_independent"),
            "sample_unit": breadth_row.get("sample_unit"),
            "excluded_from_promotion": breadth_row.get("excluded_from_promotion"),
            "freshness_bucket": "unmeasured",
            "recent_90d_net_bps": None,
            "recent_180d_net_bps": None,
        }
    if not candidate_metric:
        return {
            "freshness_bucket": "unmeasured",
            "recent_90d_net_bps": None,
            "recent_180d_net_bps": None,
        }
    return {
        "gross_bps": candidate_metric.get("gross_bps"),
        "cost_bps": candidate_metric.get("cost_bps"),
        "net_bps": candidate_metric.get("net_bps"),
        "net_to_cost_ratio": candidate_metric.get("net_to_cost_ratio"),
        "is_sharpe": candidate_metric.get("annualized_net_sharpe"),
        "oos_sharpe": candidate_metric.get("oos_sharpe"),
        "psr_0": candidate_metric.get("psr_0"),
        "dsr_k": candidate_metric.get("dsr_k"),
        "pbo": candidate_metric.get("pbo"),
        "k_trials": candidate_metric.get("k_trials"),
        # 不把 n_days 冒充為 n_independent；若候選真的有 cluster-adjusted N，必須顯式給。
        "n_independent": candidate_metric.get("n_independent"),
        "sample_unit": candidate_metric.get("sample_unit"),
        "freshness_bucket": candidate_metric.get("freshness_bucket") or "unmeasured",
        "recent_90d_net_bps": candidate_metric.get("recent_90d_net_bps"),
        "recent_180d_net_bps": candidate_metric.get("recent_180d_net_bps"),
    }


def _reject_reasons(
    *,
    slice_row: dict[str, Any],
    cell_metrics: dict[str, Any],
    candidate_metric: Optional[dict[str, str]],
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
        if candidate_metric is None:
            reasons.append("missing_regime_slice_metrics")
        elif str(candidate_metric.get("metric_status", "")).upper() != "PASS":
            reasons.append("candidate_metric_not_pass")

    net_bps = _float_or_none(cell_metrics.get("net_bps"))
    net_to_cost = _float_or_none(cell_metrics.get("net_to_cost_ratio"))
    n_independent = _int_or_none(cell_metrics.get("n_independent"))
    is_sharpe = _float_or_none(cell_metrics.get("is_sharpe"))
    oos_sharpe = _float_or_none(cell_metrics.get("oos_sharpe"))
    psr_0 = _float_or_none(cell_metrics.get("psr_0"))
    dsr_k = _float_or_none(cell_metrics.get("dsr_k"))
    pbo = _float_or_none(cell_metrics.get("pbo"))

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

    if is_sharpe is None:
        reasons.append("missing_is_sharpe")
    elif is_sharpe <= 0:
        reasons.append("is_sharpe_non_positive")
    if oos_sharpe is None:
        reasons.append("missing_oos_sharpe")
    elif oos_sharpe <= 0:
        reasons.append("oos_sharpe_non_positive")
    if psr_0 is None:
        reasons.append("missing_psr_0")
    elif psr_0 < 0.95:
        reasons.append("psr_0_below_0_95")
    if dsr_k is None:
        reasons.append("missing_dsr_k")
    elif dsr_k < 0.95:
        reasons.append("dsr_k_below_0_95")
    if pbo is None:
        reasons.append("missing_pbo")
    elif pbo >= 0.5:
        reasons.append("pbo_at_or_above_0_5")

    if _float_or_none(cell_metrics.get("recent_90d_net_bps")) is None:
        reasons.append("missing_recent_90d_net_bps")
    if _float_or_none(cell_metrics.get("recent_180d_net_bps")) is None:
        reasons.append("missing_recent_180d_net_bps")

    if survivorship_mode == "current_survivor_or_unverified":
        reasons.append("survivorship_not_pit_verified")
    if str(execution_realism.get("status", "")).upper() != "PASS":
        reasons.append(execution_realism.get("reject_reason") or "execution_realism_not_pass")
    if str(cell_metrics.get("excluded_from_promotion") or "").lower() == "true":
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
    candidate_metrics: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """生成 verdict matrix rows + summary。"""
    regime_summary = regime_artifact["summary"]
    breadth_summary = breadth_artifact["summary"]
    coverage = _coverage_status(regime_summary, breadth_summary)
    lineage = _feature_lineage_status(regime_summary)
    survivorship = _survivorship_mode(breadth_summary)
    candidate_metrics = candidate_metrics or {"rows": [], "summary": {}}
    candidate_by_regime = _candidate_metric_index(candidate_metrics)

    rows: list[dict[str, Any]] = []
    for breadth_row in breadth_artifact["rows"]:
        for slice_row in regime_slices(regime_artifact):
            candidate_metric = None if slice_row["is_aggregate"] else candidate_by_regime.get(slice_row["regime"])
            cell_metrics = _cell_metrics(
                breadth_row=breadth_row,
                slice_row=slice_row,
                candidate_metric=candidate_metric,
            )
            reasons = _reject_reasons(
                slice_row=slice_row,
                cell_metrics=cell_metrics,
                candidate_metric=candidate_metric,
                coverage_gate_status=coverage,
                feature_lineage_status=lineage,
                survivorship_mode=survivorship,
                execution_realism=execution_realism,
            )
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
                "freshness_bucket": cell_metrics.get("freshness_bucket") or "unmeasured",
                "survivorship_mode": survivorship,
                "execution_realism_mode": execution_realism.get("execution_realism_mode"),
                "coverage_gate_status": coverage,
                "feature_lineage_status": lineage,
                "gross_bps": cell_metrics.get("gross_bps"),
                "cost_bps": cell_metrics.get("cost_bps"),
                "net_bps": cell_metrics.get("net_bps"),
                "net_to_cost_ratio": cell_metrics.get("net_to_cost_ratio"),
                "is_sharpe": cell_metrics.get("is_sharpe"),
                "oos_sharpe": cell_metrics.get("oos_sharpe"),
                "psr_0": cell_metrics.get("psr_0"),
                "dsr_k": cell_metrics.get("dsr_k"),
                "pbo": cell_metrics.get("pbo"),
                "multiple_test_family": breadth_summary.get("candidate_id"),
                "k_trials": cell_metrics.get("k_trials"),
                "n_independent": cell_metrics.get("n_independent"),
                "sample_unit": cell_metrics.get("sample_unit"),
                "recent_90d_net_bps": cell_metrics.get("recent_90d_net_bps"),
                "recent_180d_net_bps": cell_metrics.get("recent_180d_net_bps"),
                "non_bull_independent_pass": False,
                "final_label": _final_label(reasons, breadth_summary),
                "reject_reasons": _json_cell(reasons),
            }
            rows.append({col: row.get(col) for col in MATRIX_COLUMNS})

    final_counts = Counter(row["final_label"] for row in rows)
    candidate_summary = candidate_metrics.get("summary") or {}
    summary = {
        "run_id": run_id,
        "candidate_id": breadth_summary.get("candidate_id"),
        "candidate_key": candidate_summary.get("candidate_key"),
        "candidate_metrics_source_report_type": candidate_summary.get("source_report_type"),
        "candidate_metrics_selected_variant": candidate_summary.get("selected_variant"),
        "verdict_gate_version": VERDICT_GATE_VERSION,
        "row_count": len(rows),
        "regime_slice_count": len(regime_slices(regime_artifact)),
        "breadth_row_count": len(breadth_artifact["rows"]),
        "final_label_counts": dict(sorted(final_counts.items())),
        "coverage_gate_status": coverage,
        "feature_lineage_status": lineage,
        "survivorship_mode": survivorship,
        "execution_realism_mode": execution_realism.get("execution_realism_mode"),
        "candidate_metrics_status_counts": dict(sorted(
            Counter(
                str(row.get("metric_status") or "UNKNOWN").upper()
                for row in candidate_metrics.get("rows") or []
            ).items()
        )),
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
            "candidate_metrics_run_id": candidate_summary.get("run_id"),
        },
    }
    return rows, summary

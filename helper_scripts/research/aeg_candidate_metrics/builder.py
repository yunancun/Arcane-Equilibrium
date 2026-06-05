"""AEG candidate metrics adapter 純函數核心。"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Optional


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _float_or_none(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        f = float(value)
    else:
        s = str(value).strip()
        if not s:
            return None
        try:
            f = float(s)
        except ValueError:
            return None
    return f if math.isfinite(f) else None


def _int_or_none(value: Any) -> Optional[int]:
    f = _float_or_none(value)
    if f is None:
        return None
    return int(f)


def detect_report_type(report: dict[str, Any]) -> str:
    if report.get("diagnostic") == "funding_tilt_carry":
        return "funding_tilt_diagnostic"
    if report.get("phase") == "phase_1_fail_fast_early_gates":
        return "multiday_trend_diagnostic"
    return "unknown"


def _select_variant(report: dict[str, Any]) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    evaluations = report.get("signal_evaluation") or {}
    preferred = (report.get("decision_tree") or {}).get("best_variant")
    if preferred and isinstance(evaluations.get(preferred), dict):
        return preferred, evaluations[preferred]

    best_key = None
    best_ev = None
    for key, ev in evaluations.items():
        if not isinstance(ev, dict):
            continue
        sharpe = _float_or_none(ev.get("annualized_net_sharpe_leakfree"))
        if sharpe is None:
            continue
        if best_ev is None or sharpe > _float_or_none(best_ev.get("annualized_net_sharpe_leakfree")):
            best_key = key
            best_ev = ev
    return best_key, best_ev


def _freshness_value(ev: dict[str, Any], report: dict[str, Any], key: str) -> Optional[float]:
    freshness = report.get("freshness") or {}
    return _float_or_none(ev.get(key) if key in ev else freshness.get(key))


def _freshness_bucket(recent_90d: Optional[float], recent_180d: Optional[float]) -> str:
    if recent_90d is not None and recent_180d is not None:
        return "recent_90_180_measured"
    if recent_90d is not None:
        return "recent_90_measured_180_missing"
    if recent_180d is not None:
        return "recent_180_measured_90_missing"
    return "unmeasured"


def _reject_reasons(
    *,
    n_days: Optional[int],
    net_bps: Optional[float],
    mean_daily_bps: Optional[float],
    annualized_net_sharpe: Optional[float],
    recent_90d: Optional[float],
    recent_180d: Optional[float],
) -> list[str]:
    reasons: list[str] = []
    if n_days is None:
        reasons.append("missing_n_days")
    elif n_days < 30:
        reasons.append("n_days_below_30")
    if net_bps is None:
        reasons.append("missing_net_bps")
    if mean_daily_bps is None:
        reasons.append("missing_mean_daily_bps")
    if annualized_net_sharpe is None:
        reasons.append("missing_annualized_net_sharpe")
    if recent_90d is None:
        reasons.append("missing_recent_90d_net_bps")
    if recent_180d is None:
        reasons.append("missing_recent_180d_net_bps")
    return reasons


def build_candidate_metrics(
    report: dict[str, Any],
    *,
    run_id: str,
    candidate_id: str,
    strategy_family: str,
    parameter_cell_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """從 diagnostic report 正規化 per-regime metrics rows + summary。"""
    report_type = detect_report_type(report)
    selected_variant, ev = _select_variant(report)
    rows: list[dict[str, Any]] = []
    if ev is not None:
        per_regime = ev.get("per_regime_net") or {}
        for regime in sorted(per_regime):
            src = per_regime.get(regime) or {}
            n_days = _int_or_none(src.get("n_days"))
            net_bps = _float_or_none(src.get("net_bps"))
            mean_daily_bps = _float_or_none(src.get("mean_daily_bps"))
            sharpe = _float_or_none(src.get("annualized_net_sharpe"))
            recent_90d = _freshness_value(ev, report, "recent_90d_net_bps")
            recent_180d = _freshness_value(ev, report, "recent_180d_net_bps")
            reasons = _reject_reasons(
                n_days=n_days,
                net_bps=net_bps,
                mean_daily_bps=mean_daily_bps,
                annualized_net_sharpe=sharpe,
                recent_90d=recent_90d,
                recent_180d=recent_180d,
            )
            rows.append({
                "run_id": run_id,
                "candidate_id": candidate_id,
                "strategy_family": strategy_family,
                "parameter_cell_id": parameter_cell_id,
                "source_report_type": report_type,
                "selected_variant": selected_variant,
                "regime": regime,
                "n_days": n_days,
                "net_bps": net_bps,
                "mean_daily_bps": mean_daily_bps,
                "annualized_net_sharpe": sharpe,
                "recent_90d_net_bps": recent_90d,
                "recent_180d_net_bps": recent_180d,
                "freshness_bucket": _freshness_bucket(recent_90d, recent_180d),
                "metric_status": "PASS" if not reasons else "FAIL",
                "reject_reasons": json.dumps(
                    list(dict.fromkeys(reasons)),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            })

    counts = Counter(row["metric_status"] for row in rows)
    summary = {
        "run_id": run_id,
        "candidate_id": candidate_id,
        "strategy_family": strategy_family,
        "parameter_cell_id": parameter_cell_id,
        "source_report_type": report_type,
        "selected_variant": selected_variant,
        "row_count": len(rows),
        "metric_status_counts": dict(sorted(counts.items())),
        "freshness_buckets": dict(sorted(Counter(row["freshness_bucket"] for row in rows).items())),
        "date_span": report.get("date_span"),
        "diagnostic_verdict": (report.get("decision_tree") or {}).get("verdict"),
        "notes": [
            "mean_daily_bps 不等於 matrix net_bps；缺 net_bps 時必 fail-closed",
            "recent_90d_net_bps / recent_180d_net_bps 缺失時 freshness 仍未量測",
        ],
    }
    if ev is None:
        summary["reject_reason"] = "no_selected_or_evaluable_variant"
    return rows, summary

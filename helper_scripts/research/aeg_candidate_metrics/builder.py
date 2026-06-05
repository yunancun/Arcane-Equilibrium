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


def _metric_source_value(
    src: dict[str, Any],
    ev: dict[str, Any],
    report: dict[str, Any],
    key: str,
) -> Optional[float]:
    """讀明確 metric 欄位；不做單位/樣本替換。"""
    if key in src:
        return _float_or_none(src.get(key))
    defaults = ev.get("regime_metric_defaults") or {}
    if key in defaults:
        return _float_or_none(defaults.get(key))
    if key in ev:
        return _float_or_none(ev.get(key))
    report_defaults = report.get("candidate_metric_defaults") or {}
    if key in report_defaults:
        return _float_or_none(report_defaults.get(key))
    return None


def _pbo_value(value: Any) -> Optional[float]:
    if isinstance(value, dict):
        return _float_or_none(value.get("value"))
    return _float_or_none(value)


def _psr_value(src: dict[str, Any], ev: dict[str, Any], report: dict[str, Any]) -> Optional[float]:
    val = _metric_source_value(src, ev, report, "psr_0")
    if val is not None:
        return val
    return _float_or_none((report.get("overfitting") or {}).get("psr_0"))


def _dsr_value(src: dict[str, Any], ev: dict[str, Any], report: dict[str, Any]) -> Optional[float]:
    # funding_tilt 的 overfitting.dsr_k 是 K budget，不是 DSR 分數；只用 overfitting.dsr。
    for key in ("dsr_k", "dsr"):
        val = _metric_source_value(src, ev, report, key)
        if val is not None:
            return val
    return _float_or_none((report.get("overfitting") or {}).get("dsr"))


def _pbo_metric_value(src: dict[str, Any], ev: dict[str, Any], report: dict[str, Any]) -> Optional[float]:
    for container in (src, ev, report.get("candidate_metric_defaults") or {}):
        if "pbo" in container:
            val = _pbo_value(container.get("pbo"))
            if val is not None:
                return val
    return _pbo_value((report.get("overfitting") or {}).get("pbo"))


def _k_trials_value(src: dict[str, Any], ev: dict[str, Any], report: dict[str, Any]) -> Optional[int]:
    for key in ("k_trials", "trial_budget_K"):
        if key in src:
            return _int_or_none(src.get(key))
        if key in ev:
            return _int_or_none(ev.get(key))
    return _int_or_none(report.get("trial_budget_K"))


def _sample_unit_value(src: dict[str, Any], ev: dict[str, Any]) -> Optional[str]:
    for container in (src, ev.get("regime_metric_defaults") or {}, ev):
        value = container.get("sample_unit")
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _net_to_cost_ratio(
    src: dict[str, Any],
    ev: dict[str, Any],
    report: dict[str, Any],
    *,
    net_bps: Optional[float],
    cost_bps: Optional[float],
) -> Optional[float]:
    explicit = _metric_source_value(src, ev, report, "net_to_cost_ratio")
    if explicit is not None:
        return explicit
    if net_bps is not None and cost_bps is not None and cost_bps > 0:
        return net_bps / cost_bps
    return None


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
    gross_bps: Optional[float],
    cost_bps: Optional[float],
    net_bps: Optional[float],
    net_to_cost_ratio: Optional[float],
    mean_daily_bps: Optional[float],
    annualized_net_sharpe: Optional[float],
    oos_sharpe: Optional[float],
    psr_0: Optional[float],
    dsr_k: Optional[float],
    pbo: Optional[float],
    k_trials: Optional[int],
    n_independent: Optional[int],
    sample_unit: Optional[str],
    recent_90d: Optional[float],
    recent_180d: Optional[float],
) -> list[str]:
    reasons: list[str] = []
    if n_days is None:
        reasons.append("missing_n_days")
    elif n_days < 30:
        reasons.append("n_days_below_30")
    if gross_bps is None:
        reasons.append("missing_gross_bps")
    if cost_bps is None:
        reasons.append("missing_cost_bps")
    if net_bps is None:
        reasons.append("missing_net_bps")
    if net_to_cost_ratio is None:
        reasons.append("missing_net_to_cost_ratio")
    if mean_daily_bps is None:
        reasons.append("missing_mean_daily_bps")
    if annualized_net_sharpe is None:
        reasons.append("missing_annualized_net_sharpe")
    if oos_sharpe is None:
        reasons.append("missing_oos_sharpe")
    if psr_0 is None:
        reasons.append("missing_psr_0")
    if dsr_k is None:
        reasons.append("missing_dsr_k")
    if pbo is None:
        reasons.append("missing_pbo")
    if k_trials is None:
        reasons.append("missing_k_trials")
    if n_independent is None:
        reasons.append("missing_n_independent")
    elif n_independent < 30:
        reasons.append("n_independent_below_30")
    if not sample_unit:
        reasons.append("missing_sample_unit")
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
            gross_bps = _metric_source_value(src, ev, report, "gross_bps")
            cost_bps = _metric_source_value(src, ev, report, "cost_bps")
            net_bps = _float_or_none(src.get("net_bps"))
            net_to_cost = _net_to_cost_ratio(
                src,
                ev,
                report,
                net_bps=net_bps,
                cost_bps=cost_bps,
            )
            mean_daily_bps = _float_or_none(src.get("mean_daily_bps"))
            sharpe = _float_or_none(src.get("annualized_net_sharpe"))
            oos_sharpe = _metric_source_value(src, ev, report, "oos_sharpe")
            psr_0 = _psr_value(src, ev, report)
            dsr_k = _dsr_value(src, ev, report)
            pbo = _pbo_metric_value(src, ev, report)
            k_trials = _k_trials_value(src, ev, report)
            # 不把 n_days 冒充為 n_independent；候選必須顯式提供 cluster-adjusted N。
            n_independent = _int_or_none(src.get("n_independent"))
            sample_unit = _sample_unit_value(src, ev)
            recent_90d = _float_or_none(src.get("recent_90d_net_bps"))
            if recent_90d is None:
                recent_90d = _freshness_value(ev, report, "recent_90d_net_bps")
            recent_180d = _float_or_none(src.get("recent_180d_net_bps"))
            if recent_180d is None:
                recent_180d = _freshness_value(ev, report, "recent_180d_net_bps")
            reasons = _reject_reasons(
                n_days=n_days,
                gross_bps=gross_bps,
                cost_bps=cost_bps,
                net_bps=net_bps,
                net_to_cost_ratio=net_to_cost,
                mean_daily_bps=mean_daily_bps,
                annualized_net_sharpe=sharpe,
                oos_sharpe=oos_sharpe,
                psr_0=psr_0,
                dsr_k=dsr_k,
                pbo=pbo,
                k_trials=k_trials,
                n_independent=n_independent,
                sample_unit=sample_unit,
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
                "gross_bps": gross_bps,
                "cost_bps": cost_bps,
                "net_bps": net_bps,
                "net_to_cost_ratio": net_to_cost,
                "mean_daily_bps": mean_daily_bps,
                "annualized_net_sharpe": sharpe,
                "oos_sharpe": oos_sharpe,
                "psr_0": psr_0,
                "dsr_k": dsr_k,
                "pbo": pbo,
                "k_trials": k_trials,
                "n_independent": n_independent,
                "sample_unit": sample_unit,
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
            "n_days 不等於 n_independent；cluster-adjusted N 必須顯式提供",
            "recent_90d_net_bps / recent_180d_net_bps 缺失時 freshness 仍未量測",
        ],
    }
    if ev is None:
        summary["reject_reason"] = "no_selected_or_evaluable_variant"
    return rows, summary

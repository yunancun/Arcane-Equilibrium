"""AEG-S3 candidate-specific matrix input builders."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from aeg_breadth_ladder import BREADTH_LADDER_VERSION
from aeg_breadth_ladder.ladder import LADDER_COLUMNS
from aeg_execution_realism import builder as execution_builder

from . import RUNNER_VERSION, SUMMARY_SCHEMA_VERSION

_PLACEHOLDER_PROVENANCE = "candidate_metrics_only_not_evaluated"
_BREADTH_COHORT = "candidate_metrics_only"
_BREADTH_EXCLUSION_REASON = "candidate_specific_breadth_not_evaluated"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_candidate_metrics(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    return {
        "run_dir": run_dir,
        "rows": _read_csv(run_dir / "candidate_regime_metrics.csv"),
        "summary": _read_json(run_dir / "candidate_metrics_summary.json"),
    }


def load_breadth_artifact(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    return {
        "run_dir": run_dir,
        "rows": _read_csv(run_dir / "breadth_ladder.csv"),
        "summary": _read_json(run_dir / "breadth_ladder_summary.json"),
    }


def load_execution_realism(path: Path) -> dict[str, Any]:
    payload = _read_json(Path(path))
    mode = (
        payload.get("execution_realism_mode")
        or payload.get("mode")
        or payload.get("assumption_mode")
        or "provided_unspecified"
    )
    return {**payload, "execution_realism_mode": mode}


def _date_to_utc(value: Any, *, end_of_day: bool = False) -> str:
    if value is None or str(value).strip() == "":
        return "1970-01-01T00:00:00+00:00"
    raw = str(value).strip()
    if "T" in raw:
        s = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
        parsed = dt.datetime.fromisoformat(s)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat()
    d = dt.date.fromisoformat(raw[:10])
    t = dt.time.max if end_of_day else dt.time.min
    return dt.datetime.combine(d, t, tzinfo=dt.timezone.utc).isoformat()


def _window_from_summary(summary: dict[str, Any]) -> tuple[str, str, str]:
    span = summary.get("date_span")
    start = span[0] if isinstance(span, list) and len(span) >= 1 else None
    end = span[1] if isinstance(span, list) and len(span) >= 2 else None
    window_start = _date_to_utc(start)
    window_end = _date_to_utc(end, end_of_day=True)
    return window_end, window_start, window_end


def _stable_ladder_id(*, run_id: str, candidate_id: str, parameter_cell_id: str) -> str:
    payload = "|".join([
        RUNNER_VERSION,
        run_id,
        candidate_id,
        parameter_cell_id,
        _BREADTH_COHORT,
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _summary_value(summary: dict[str, Any], key: str) -> str:
    value = summary.get(key)
    return str(value).strip() if value is not None and str(value).strip() else "unknown"


def _required_summary_value(summary: dict[str, Any], key: str) -> str:
    value = _summary_value(summary, key)
    if value == "unknown":
        raise ValueError(f"candidate_metrics_{key}_missing")
    return value


def _artifact_value(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return str(value).strip() if value is not None and str(value).strip() else ""


def _require_match(*, kind: str, field: str, expected: str, actual: str) -> None:
    if not actual:
        raise ValueError(f"{kind}_{field}_missing")
    if expected != "unknown" and actual != expected:
        raise ValueError(f"{kind}_{field}_mismatch:expected={expected},actual={actual}")


def _validate_breadth_artifact(candidate_metrics: dict[str, Any], breadth_artifact: dict[str, Any]) -> None:
    expected_candidate_id = _required_summary_value(candidate_metrics["summary"], "candidate_id")
    summary = breadth_artifact["summary"]
    rows = breadth_artifact.get("rows") or []
    actual_candidate_id = _artifact_value(summary, "candidate_id")
    if not actual_candidate_id and rows:
        actual_candidate_id = _artifact_value(rows[0], "candidate_id")
    _require_match(
        kind="breadth",
        field="candidate_id",
        expected=expected_candidate_id,
        actual=actual_candidate_id,
    )
    for idx, row in enumerate(rows):
        row_candidate_id = _artifact_value(row, "candidate_id")
        if row_candidate_id and row_candidate_id != expected_candidate_id:
            raise ValueError(
                "breadth_candidate_id_mismatch:"
                f"row={idx},expected={expected_candidate_id},actual={row_candidate_id}"
            )


def _validate_execution_realism(candidate_metrics: dict[str, Any], payload: dict[str, Any]) -> None:
    summary = candidate_metrics["summary"]
    for field in ("candidate_id", "strategy_family", "parameter_cell_id"):
        _require_match(
            kind="execution",
            field=field,
            expected=_required_summary_value(summary, field),
            actual=_artifact_value(payload, field),
        )
    if "status" not in payload:
        raise ValueError("execution_status_missing")
    if not _artifact_value(payload, "execution_realism_mode"):
        raise ValueError("execution_realism_mode_missing")


def _breadth_policy(breadth_summary: dict[str, Any]) -> str:
    adapter = breadth_summary.get("event_breadth_adapter")
    if isinstance(adapter, dict) and adapter.get("policy"):
        return str(adapter["policy"])
    return str(breadth_summary.get("policy") or "provided_breadth_artifact")


def _execution_reject_reasons(payload: dict[str, Any]) -> list[str]:
    reasons = payload.get("reject_reasons")
    if isinstance(reasons, list):
        return [str(item) for item in reasons]
    reason = payload.get("reject_reason")
    return [str(reason)] if reason else []


def build_breadth_placeholder(
    candidate_metrics: dict[str, Any],
    *,
    run_id: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build candidate-specific breadth artifact rows that fail closed.

    This artifact intentionally does not claim breadth evidence. It only carries
    the candidate_id lineage into robustness_matrix without borrowing an
    unrelated smoke breadth run.
    """
    summary = candidate_metrics["summary"]
    candidate_id = _summary_value(summary, "candidate_id")
    strategy_family = _summary_value(summary, "strategy_family")
    parameter_cell_id = _summary_value(summary, "parameter_cell_id")
    asof_utc, window_start_utc, window_end_utc = _window_from_summary(summary)
    ladder_id = _stable_ladder_id(
        run_id=run_id,
        candidate_id=candidate_id,
        parameter_cell_id=parameter_cell_id,
    )
    row = {
        "run_id": run_id,
        "ladder_id": ladder_id,
        "candidate_id": candidate_id,
        "breadth_ladder_version": BREADTH_LADDER_VERSION,
        "asof_utc": asof_utc,
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "fnd2_universe_id": _PLACEHOLDER_PROVENANCE,
        "fnd2_run_id": _PLACEHOLDER_PROVENANCE,
        "breadth_cohort": _BREADTH_COHORT,
        "breadth_symbol_count": "",
        "seen_delisted_count": 0,
        "tier_quality": "candidate_metrics_only",
        "tier_rank_pit_mode": "n/a",
        "gross_bps": "",
        "cost_bps": "",
        "net_bps": "",
        "net_to_cost_ratio": "",
        "is_sharpe": "",
        "oos_sharpe": "",
        "n_independent": "",
        "sample_unit": "candidate_regime_metric_rows",
        "t_stat_hac": "",
        "psr_0": "",
        "dsr_k": "",
        "pbo": "",
        "k_trials": "",
        "long_leg_net_bps": "",
        "short_leg_net_bps": "",
        "pit_mask_source": "not_evaluated_candidate_metrics_only",
        "leak_free_signal": "false",
        "monotonicity_rank": "",
        "excluded_from_promotion": "true",
        "exclusion_reason": _BREADTH_EXCLUSION_REASON,
    }
    rows = [{col: row.get(col, "") for col in LADDER_COLUMNS}]
    breadth_summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "ladder_id": ladder_id,
        "candidate_id": candidate_id,
        "strategy_family": strategy_family,
        "parameter_cell_id": parameter_cell_id,
        "breadth_ladder_version": BREADTH_LADDER_VERSION,
        "fnd2_universe_id": _PLACEHOLDER_PROVENANCE,
        "fnd2_run_id": _PLACEHOLDER_PROVENANCE,
        "asof_utc": asof_utc,
        "window_start_utc": window_start_utc,
        "window_end_utc": window_end_utc,
        "tiers_evaluated": [_BREADTH_COHORT],
        "per_tier_net_bps": {_BREADTH_COHORT: None},
        "per_tier_n_independent": {_BREADTH_COHORT: None},
        "per_tier_breadth": {_BREADTH_COHORT: None},
        "monotonicity": {
            "net_bps_monotonic_in_breadth": False,
            "net_bps_trend": "not_evaluated",
            "narrow_only_edge": False,
            "n_independent_invariant_to_breadth": False,
            "binding_ceiling": "candidate_specific_breadth_missing",
            "per_tier_net_bps": {_BREADTH_COHORT: None},
            "per_tier_n_independent": {_BREADTH_COHORT: None},
            "verdict_hint": "candidate_metrics_only_no_breadth",
            "reason": _BREADTH_EXCLUSION_REASON,
        },
        "delisted_proof_total": 0,
        "survivorship_inherited_from_fnd2": False,
        "survivorship_healthcheck": {
            "status": "FAIL",
            "message": (
                "candidate-specific breadth ladder was not evaluated; artifact "
                "exists only to carry candidate_id lineage into robustness_matrix"
            ),
        },
        "verdict_hint": "candidate_metrics_only_no_breadth",
        "source_candidate_metrics_run_id": summary.get("run_id"),
        "candidate_metrics_status_counts": summary.get("metric_status_counts") or {},
        "policy": "fail_closed_candidate_metrics_only_no_breadth_claim",
    }
    return rows, breadth_summary


def build_unverified_execution_realism(
    candidate_metrics: dict[str, Any],
) -> dict[str, Any]:
    summary = candidate_metrics["summary"]
    raw = {
        "candidate_id": summary.get("candidate_id"),
        "strategy_family": summary.get("strategy_family"),
        "parameter_cell_id": summary.get("parameter_cell_id"),
        "status": "FAIL",
        "evidence_source_tier": "missing",
        "order_style": "missing",
        "notes": [
            "AEG-S3 candidate-specific execution realism has not been measured",
            "this fail-closed payload exists only to make matrix lineage explicit",
        ],
    }
    return execution_builder.evaluate(raw)


def build_inputs(
    candidate_metrics: dict[str, Any],
    *,
    run_id: str,
    breadth_artifact: Optional[dict[str, Any]] = None,
    execution_realism: Optional[dict[str, Any]] = None,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if breadth_artifact is None:
        rows, breadth_summary = build_breadth_placeholder(candidate_metrics, run_id=run_id)
        breadth_input_mode = "generated_placeholder"
    else:
        _validate_breadth_artifact(candidate_metrics, breadth_artifact)
        rows = breadth_artifact["rows"]
        breadth_summary = breadth_artifact["summary"]
        breadth_input_mode = "provided_breadth_artifact"

    if execution_realism is None:
        execution_payload = build_unverified_execution_realism(candidate_metrics)
        execution_input_mode = "unverified_placeholder"
    else:
        _validate_execution_realism(candidate_metrics, execution_realism)
        execution_payload = execution_realism
        execution_input_mode = "provided_execution_realism_artifact"

    candidate_summary = candidate_metrics["summary"]
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "run_id": run_id,
        "candidate_id": breadth_summary["candidate_id"],
        "strategy_family": _summary_value(candidate_summary, "strategy_family"),
        "parameter_cell_id": _summary_value(candidate_summary, "parameter_cell_id"),
        "source_candidate_metrics_run_id": candidate_summary.get("run_id"),
        "breadth_input_mode": breadth_input_mode,
        "breadth_policy": _breadth_policy(breadth_summary),
        "breadth_artifact_run_id": breadth_summary.get("run_id"),
        "breadth_artifact_adapter": (
            "event_breadth"
            if isinstance(breadth_summary.get("event_breadth_adapter"), dict)
            else "generic_breadth_ladder"
        ),
        "execution_input_mode": execution_input_mode,
        "execution_realism_status": execution_payload.get("status"),
        "execution_realism_mode": execution_payload.get("execution_realism_mode"),
        "execution_realism_reject_reasons": _execution_reject_reasons(execution_payload),
        "notes": [
            "outputs are candidate-specific matrix inputs",
            "missing sidecar artifacts intentionally fail closed until measured",
        ],
    }
    return rows, breadth_summary, execution_payload, summary

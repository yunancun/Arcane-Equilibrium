#!/usr/bin/env python3
"""Build artifact-only learning evidence for a sealed horizon candidate.

This wrapper ties the existing fail-closed learning-lane pieces together for one
preselected sealed horizon side-cell:

1. read mature cost-gate rejects from a read-only source,
2. materialize them into scratch admission-ledger rows,
3. build blocked-signal markouts at the candidate horizon,
4. summarize the review gate in a compact evidence packet.

It never writes PG, calls Bybit, submits orders, lowers the main Cost Gate, or
mutates runtime config.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.outcome_refresh import (  # noqa: E402
    OutcomeRefreshSelection,
    append_refresh_outcomes_to_ledger,
    build_cost_gate_outcome_refresh_batch,
    build_price_rows_from_pg_for_refresh,
)
from cost_gate_learning_lane.outcome_review import (  # noqa: E402
    BlockedOutcomeReviewConfig,
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.outcome_writer import ProbeOutcomeConfig  # noqa: E402
from cost_gate_learning_lane.price_observations import (  # noqa: E402
    read_source_price_rows,
    validate_pg_timeframe,
)
from cost_gate_learning_lane.reject_materializer import (  # noqa: E402
    VALID_ENGINE_MODES,
    append_materialized_records_to_ledger,
    build_materialized_reject_ledger_batch,
    connect_readonly_reject_materializer_pg,
)
from cost_gate_learning_lane.runtime_adapter import (  # noqa: E402
    RuntimeAdmissionConfig,
    read_jsonl_ledger,
)


SEALED_HORIZON_LEARNING_EVIDENCE_SCHEMA_VERSION = (
    "sealed_horizon_learning_evidence_v1"
)


@dataclass(frozen=True)
class SealedHorizonLearningEvidenceConfig:
    """Controls one sealed-horizon learning evidence run."""

    engine_modes: tuple[str, ...] = ("demo", "live_demo")
    lookback_hours: int = 72
    limit: int = 50_000
    maturity_buffer_minutes: int = 0
    pg_timeframe: str = "1m"
    default_horizon_minutes: int = 60
    outcome_cost_bps: float = 4.0
    max_entry_delay_ms: int = 5 * 60_000
    max_plan_age_hours: int = 48
    # P2-7:禁用規則 UCB-futility 化,n≥8 才觸發(n=2 誤殺率 ~42% 為負淨貢獻)。與
    # RuntimeAdmissionConfig / Rust AdmissionConfig::default() 同步。
    min_failed_outcomes_to_disable: int = 8
    min_outcome_net_positive_pct: float = 50.0
    min_avg_net_bps: float = 0.0
    min_review_outcomes_per_side_cell: int = 100
    # F1:distinct-entry n_eff 候選門檻 pass-through(默認 30 = QC 預註冊
    # docs/research/2026-07-10--counterfactual_rerun_preregistration.md §3 E1)。
    min_review_effective_entries_per_side_cell: int = 30
    # 預註冊 §3 E2/E3 pass-through(distinct UTC days ≥5;top-day share ≤50%)。
    min_review_distinct_entry_utc_days: int = 5
    max_review_top_entry_day_share_pct: float = 50.0
    min_review_avg_net_bps: float = 0.0
    min_review_net_positive_pct: float = 60.0
    statement_timeout_ms: int = 180_000


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _read_json_or_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSONL row at {path}:{line_no}") from exc
            if isinstance(payload, dict):
                rows.append(payload)
        return rows
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("features") or payload.get("data")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    raise ValueError(f"{path} did not contain rows")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )


def _sha256_file(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_sealed_horizon_evidence_config(
    cfg: SealedHorizonLearningEvidenceConfig,
) -> None:
    if not cfg.engine_modes:
        raise ValueError("at least one engine mode is required")
    bad_modes = [mode for mode in cfg.engine_modes if mode not in VALID_ENGINE_MODES]
    if bad_modes:
        raise ValueError(f"invalid engine mode(s): {bad_modes}")
    if cfg.lookback_hours < 1 or cfg.lookback_hours > 24 * 30:
        raise ValueError("--lookback-hours must be in [1, 720]")
    if cfg.limit < 1 or cfg.limit > 500_000:
        raise ValueError("--limit must be in [1, 500000]")
    if cfg.maturity_buffer_minutes < 0 or cfg.maturity_buffer_minutes > 24 * 60:
        raise ValueError("--maturity-buffer-minutes must be in [0, 1440]")
    if cfg.default_horizon_minutes < 1 or cfg.default_horizon_minutes > 24 * 60:
        raise ValueError("--horizon-minutes must be in [1, 1440]")
    if cfg.max_entry_delay_ms < 0 or cfg.max_entry_delay_ms > 24 * 60 * 60_000:
        raise ValueError("--max-entry-delay-ms must be in [0, 86400000]")
    if cfg.max_plan_age_hours < 1 or cfg.max_plan_age_hours > 24 * 30:
        raise ValueError("--max-plan-age-hours must be in [1, 720]")
    if cfg.statement_timeout_ms < 1_000 or cfg.statement_timeout_ms > 900_000:
        raise ValueError("--pg-statement-timeout-ms must be in [1000, 900000]")
    validate_pg_timeframe(cfg.pg_timeframe)


def _candidate_horizon_minutes(
    candidate: dict[str, Any],
    default_horizon_minutes: int,
) -> int:
    proposal = _dict(candidate.get("probe_proposal"))
    for value in (
        proposal.get("outcome_horizon_minutes"),
        proposal.get("learning_outcome_horizon_minutes"),
        candidate.get("outcome_horizon_minutes"),
        candidate.get("learning_outcome_horizon_minutes"),
    ):
        parsed = _int(value)
        if 1 <= parsed <= 24 * 60:
            return parsed
    return default_horizon_minutes


def _validate_sealed_horizon_candidate(
    candidate: dict[str, Any],
    *,
    default_horizon_minutes: int,
) -> dict[str, Any]:
    side_cell_key = _str(candidate.get("side_cell_key"))
    if not side_cell_key:
        raise ValueError("sealed horizon candidate is missing side_cell_key")
    if candidate.get("source_kind") != "horizon_specific_sealed_replay":
        raise ValueError(f"{side_cell_key} is not a sealed horizon replay candidate")
    if not _dict(candidate.get("sealed_horizon_replay")):
        raise ValueError(f"{side_cell_key} is missing sealed_horizon_replay evidence")
    if _candidate_horizon_minutes(candidate, default_horizon_minutes) <= 0:
        raise ValueError(f"{side_cell_key} is missing a candidate outcome horizon")
    for field in ("strategy_name", "symbol", "side", "reject_reason_code"):
        if not _str(candidate.get(field)):
            raise ValueError(f"{side_cell_key} is missing {field}")
    return candidate


def find_sealed_horizon_candidate(
    plan: dict[str, Any],
    side_cell_key: str,
    *,
    default_horizon_minutes: int = 60,
) -> dict[str, Any]:
    """Return a fail-closed sealed horizon candidate from a learning plan."""
    for candidate in plan.get("probe_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        if _str(candidate.get("side_cell_key")) != side_cell_key:
            continue
        return _validate_sealed_horizon_candidate(
            candidate,
            default_horizon_minutes=default_horizon_minutes,
        )
    raise ValueError(f"sealed horizon candidate not found: {side_cell_key}")


def select_default_sealed_horizon_candidate(
    plan: dict[str, Any],
    *,
    default_horizon_minutes: int = 60,
) -> dict[str, Any]:
    """Return the first sealed replay candidate selected by the learning plan."""
    for candidate in plan.get("probe_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        if candidate.get("source_kind") != "horizon_specific_sealed_replay":
            continue
        return _validate_sealed_horizon_candidate(
            candidate,
            default_horizon_minutes=default_horizon_minutes,
        )
    raise ValueError("sealed horizon candidate not found")


def _side_to_int(side: Any) -> int:
    lowered = _str(side).lower()
    if lowered in {"buy", "long", "1", "1.0"}:
        return 1
    if lowered in {"sell", "short", "-1", "-1.0"}:
        return -1
    raise ValueError(f"unsupported side: {side!r}")


def build_sealed_horizon_reject_feature_sql(
    candidate: dict[str, Any],
    cfg: SealedHorizonLearningEvidenceConfig,
) -> tuple[str, list[Any]]:
    """Return read-only SQL for mature rejects matching one sealed candidate."""
    validate_sealed_horizon_evidence_config(cfg)
    horizon_minutes = _candidate_horizon_minutes(candidate, cfg.default_horizon_minutes)
    mature_age_minutes = horizon_minutes + cfg.maturity_buffer_minutes
    params: list[Any] = [
        list(cfg.engine_modes),
        cfg.lookback_hours,
        mature_age_minutes,
        _str(candidate.get("reject_reason_code")),
        _str(candidate.get("strategy_name")),
        _str(candidate.get("symbol")).upper(),
        _side_to_int(candidate.get("side")),
        cfg.limit,
    ]
    sql = """
SELECT
    f.ts,
    (EXTRACT(EPOCH FROM f.ts) * 1000)::bigint AS ts_ms,
    f.context_id,
    f.engine_mode,
    f.strategy_name,
    f.symbol,
    CASE WHEN f.side = 1 THEN 'Buy' ELSE 'Sell' END AS side,
    f.reject_reason_code,
    d.last_price::float8 AS last_price
FROM learning.decision_features f
LEFT JOIN trading.decision_context_snapshots d
  ON d.context_id = f.context_id
WHERE f.engine_mode = ANY(%s)
  AND f.ts >= now() - (%s::int * interval '1 hour')
  AND f.ts <= now() - (%s::int * interval '1 minute')
  AND f.reject_reason_code = %s
  AND f.strategy_name = %s
  AND f.symbol = %s
  AND f.side = %s
ORDER BY f.ts DESC
LIMIT %s
"""
    return sql, params


def _cursor_rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    rows = cur.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], Mapping):
        return [dict(row) for row in rows]
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in rows]


def fetch_sealed_horizon_reject_feature_rows(
    conn: Any,
    candidate: dict[str, Any],
    cfg: SealedHorizonLearningEvidenceConfig,
) -> list[dict[str, Any]]:
    """Fetch mature cost-gate rejects for one sealed horizon candidate."""
    sql, params = build_sealed_horizon_reject_feature_sql(candidate, cfg)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return _cursor_rows_to_dicts(cur)


def _decision_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in rows:
        decision = _str(row.get("decision")) or "UNKNOWN"
        out[decision] = out.get(decision, 0) + 1
    return out


def _net_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [_float(row.get("realized_net_bps")) for row in rows]
    net_values = [value for value in nets if value is not None]
    gross = [_float(row.get("gross_bps")) for row in rows]
    gross_values = [value for value in gross if value is not None]
    positive = sum(1 for value in net_values if value > 0.0)
    gross_positive = sum(1 for value in gross_values if value > 0.0)
    return {
        "outcome_count": len(net_values),
        "avg_net_bps": (sum(net_values) / len(net_values)) if net_values else None,
        "avg_gross_bps": (sum(gross_values) / len(gross_values)) if gross_values else None,
        "net_positive_pct": (positive / len(net_values) * 100.0) if net_values else None,
        "gross_positive_pct": (
            gross_positive / len(gross_values) * 100.0 if gross_values else None
        ),
        "min_net_bps": min(net_values) if net_values else None,
        "max_net_bps": max(net_values) if net_values else None,
    }


def build_sealed_horizon_learning_evidence_packet(
    *,
    plan: dict[str, Any],
    candidate: dict[str, Any],
    feature_row_count: int,
    materializer_batch: dict[str, Any],
    outcome_batch: dict[str, Any],
    review: dict[str, Any],
    ledger_path: Path,
    plan_path: Path | None = None,
    output_path: Path | None = None,
    source_rows_path: Path | None = None,
    review_path: Path | None = None,
    generated_at_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a compact packet from full materializer/outcome/review artifacts."""
    generated_at = (generated_at_utc or _utc_now()).astimezone(dt.timezone.utc)
    records = [
        row for row in materializer_batch.get("records", []) if isinstance(row, dict)
    ]
    blocked_outcomes = [
        row for row in outcome_batch.get("blocked_signal_outcomes", [])
        if isinstance(row, dict)
    ]
    raw_outcome_summary = _net_summary(blocked_outcomes)
    candidate_side_cell_key = _str(candidate.get("side_cell_key"))
    strict_side_cell_reviews = _dict(
        review.get("strict_side_cell_reviews_by_key")
    )
    selected_review_cell = _dict(
        strict_side_cell_reviews.get(candidate_side_cell_key)
    )
    if not selected_review_cell:
        # Backward-compatible read of already-produced strict v6 artifacts.
        # Current production reviews always carry the full keyed surface.
        selected_review_cell = next(
            (
                row
                for row in review.get("top_side_cells") or []
                if isinstance(row, dict)
                and _str(row.get("side_cell_key")) == candidate_side_cell_key
            ),
            {},
        )
    candidate_board = _dict(review.get("learning_candidate_board"))
    selected_lineage_cell = next(
        (
            row
            for row in candidate_board.get("candidate_rows") or []
            if isinstance(row, dict)
            and _str(row.get("side_cell_key")) == candidate_side_cell_key
        ),
        {},
    )
    qualified_outcome_count = int(
        selected_review_cell.get("outcome_count") or 0
    )
    selected_qualified_input_count = int(
        selected_lineage_cell.get("qualified_evaluator_input_count") or 0
    )
    selected_materializer_records = [
        row
        for row in records
        if _str(row.get("side_cell_key")) == candidate_side_cell_key
    ]
    qualified_materialization_count = min(
        selected_qualified_input_count,
        feature_row_count,
        len(selected_materializer_records),
    )
    selected_materializer_decision_counts = _decision_counts(
        selected_materializer_records
    )
    selected_materializer_all_order_authority_not_granted = bool(
        selected_materializer_records
    ) and selected_materializer_decision_counts == {
        "ORDER_AUTHORITY_NOT_GRANTED": len(selected_materializer_records)
    }
    raw_materialized_record_count = int(
        materializer_batch.get("materialized_record_count") or 0
    )
    raw_appended_record_count = int(
        materializer_batch.get("appended_record_count") or 0
    )
    qualified_appended_record_count = (
        qualified_materialization_count
        if raw_materialized_record_count == len(records)
        and raw_appended_record_count == raw_materialized_record_count
        else 0
    )
    review_candidate = bool(selected_review_cell.get("review_candidate"))
    horizon_minutes = _candidate_horizon_minutes(candidate, 60)

    return {
        "schema_version": SEALED_HORIZON_LEARNING_EVIDENCE_SCHEMA_VERSION,
        "generated_at_utc": generated_at.isoformat(),
        "status": review.get("status"),
        "reason": review.get("reason"),
        "next_trigger": review.get("next_trigger"),
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "reject_reason_code": candidate.get("reject_reason_code"),
        "source_kind": candidate.get("source_kind"),
        "outcome_horizon_minutes": horizon_minutes,
        "default_horizon_minutes": outcome_batch.get("horizon_minutes"),
        "candidate": {
            "learning_lane_action": candidate.get("learning_lane_action"),
            "learning_lane_reason": candidate.get("learning_lane_reason"),
            "sealed_horizon_replay": candidate.get("sealed_horizon_replay"),
            "horizon_stability": candidate.get("horizon_stability"),
            "guardrails": candidate.get("guardrails"),
            "probe_proposal": candidate.get("probe_proposal"),
        },
        "materialization": {
            # Legacy consumer keys are authority-bearing and therefore derive
            # only from strict review aggregation input.  Full producer totals
            # remain available below under raw_* for audit/diagnostics.
            "input_feature_row_count": qualified_materialization_count,
            "materialized_record_count": qualified_materialization_count,
            "appended_record_count": qualified_appended_record_count,
            "decision_counts": (
                {
                    "ORDER_AUTHORITY_NOT_GRANTED": (
                        qualified_materialization_count
                    )
                }
                if qualified_materialization_count
                and selected_materializer_all_order_authority_not_granted
                else {}
            ),
            "all_order_authority_not_granted": (
                qualified_materialization_count > 0
                and selected_materializer_all_order_authority_not_granted
            ),
            "raw_input_feature_row_count": feature_row_count,
            "raw_materialized_record_count": raw_materialized_record_count,
            "raw_appended_record_count": raw_appended_record_count,
            "raw_decision_counts": _decision_counts(records),
            "raw_all_order_authority_not_granted": (
                bool(records)
                and _decision_counts(records) == {"ORDER_AUTHORITY_NOT_GRANTED": len(records)}
            ),
            "qualified_outcome_row_count": int(
                selected_qualified_input_count
            ),
        },
        "outcomes": {
            "raw_window_count": outcome_batch.get("window_count"),
            "raw_price_observation_count": outcome_batch.get(
                "price_observation_count"
            ),
            "raw_blocked_signal_outcome_count": outcome_batch.get(
                "blocked_signal_outcome_count"
            ),
            "raw_appended_outcome_count": outcome_batch.get(
                "appended_outcome_count"
            ),
            **{f"raw_{key}": value for key, value in raw_outcome_summary.items()},
            "blocked_signal_outcome_count": qualified_outcome_count,
            "outcome_count": qualified_outcome_count,
            "avg_net_bps": selected_review_cell.get("avg_net_bps"),
            "avg_gross_bps": selected_review_cell.get("avg_gross_bps"),
            "net_positive_pct": selected_review_cell.get("net_positive_pct"),
            "gross_positive_pct": selected_review_cell.get("gross_positive_pct"),
            "min_net_bps": selected_review_cell.get("min_net_bps"),
            "max_net_bps": selected_review_cell.get("max_net_bps"),
        },
        "review": {
            "status": review.get("status"),
            "reason": review.get("reason"),
            "review_candidate_side_cell_count": int(review_candidate),
            "blocked_signal_outcome_count": qualified_outcome_count,
            "avg_blocked_signal_outcome_net_bps": selected_review_cell.get(
                "avg_net_bps"
            ),
            "blocked_signal_net_positive_pct": selected_review_cell.get(
                "net_positive_pct"
            ),
            "top_side_cell_key": selected_review_cell.get("side_cell_key"),
            "top_side_cell_status": selected_review_cell.get("status"),
            "top_side_cell_wrongful_block_score": selected_review_cell.get(
                "wrongful_block_score"
            ),
            "top_side_cell": selected_review_cell,
            "thresholds": review.get("thresholds"),
        },
        "answers": {
            "sealed_candidate_materialized": qualified_materialization_count > 0,
            "blocked_signal_outcomes_recorded": qualified_outcome_count > 0,
            "candidate_clears_operator_review_gate": review_candidate,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "artifacts": {
            "plan": {
                "path": str(plan_path) if plan_path else None,
                "sha256": _sha256_file(plan_path),
                "schema_version": plan.get("schema_version"),
                "status": plan.get("status"),
                "gate_status": plan.get("gate_status"),
            },
            "source_rows": {
                "path": str(source_rows_path) if source_rows_path else None,
                "sha256": _sha256_file(source_rows_path),
            },
            "ledger": {
                "path": str(ledger_path),
                "sha256": _sha256_file(ledger_path),
            },
            "review": {
                "path": str(review_path) if review_path else None,
                "sha256": _sha256_file(review_path),
            },
            "packet": {
                "path": str(output_path) if output_path else None,
            },
        },
        "boundary": (
            "sealed horizon learning evidence artifact only; PG sources are "
            "read-only SELECT-only; no PG write/schema migration, Bybit call, "
            "order, config, risk, auth, runtime mutation, main Cost Gate "
            "lowering, probe authority, order authority, or promotion proof"
        ),
    }


def build_sealed_horizon_learning_evidence_from_rows(
    *,
    plan: dict[str, Any],
    side_cell_key: str,
    feature_rows: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
    ledger_path: Path,
    cfg: SealedHorizonLearningEvidenceConfig | None = None,
    append_ledger: bool = False,
    now_utc: dt.datetime | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build the full evidence chain from in-memory rows."""
    cfg = cfg or SealedHorizonLearningEvidenceConfig()
    validate_sealed_horizon_evidence_config(cfg)
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    candidate = find_sealed_horizon_candidate(
        plan,
        side_cell_key,
        default_horizon_minutes=cfg.default_horizon_minutes,
    )
    existing_rows = read_jsonl_ledger(ledger_path)
    admission_cfg = RuntimeAdmissionConfig(
        max_plan_age_hours=cfg.max_plan_age_hours,
        min_failed_outcomes_to_disable=cfg.min_failed_outcomes_to_disable,
        min_outcome_net_positive_pct=cfg.min_outcome_net_positive_pct,
        min_avg_net_bps=cfg.min_avg_net_bps,
    )
    materializer_batch = build_materialized_reject_ledger_batch(
        plan,
        feature_rows,
        existing_ledger_rows=existing_rows,
        admission_cfg=admission_cfg,
        now_utc=now,
    )
    if append_ledger:
        append_materialized_records_to_ledger(ledger_path, materializer_batch)
    materialized_rows = [
        row for row in materializer_batch.get("records", []) if isinstance(row, dict)
    ]
    ledger_for_outcomes = existing_rows + materialized_rows
    selection = OutcomeRefreshSelection(record_blocked_outcomes=True)
    outcome_cfg = ProbeOutcomeConfig(
        horizon_minutes=cfg.default_horizon_minutes,
        cost_bps=cfg.outcome_cost_bps,
        max_entry_delay_ms=cfg.max_entry_delay_ms,
    )
    outcome_batch = build_cost_gate_outcome_refresh_batch(
        ledger_for_outcomes,
        price_rows,
        now_utc=now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source="local_price_rows",
    )
    if append_ledger:
        append_refresh_outcomes_to_ledger(ledger_path, outcome_batch)
    outcome_rows = [
        row for row in outcome_batch.get("outcomes", []) if isinstance(row, dict)
    ]
    review_cfg = BlockedOutcomeReviewConfig(
        min_outcomes_per_side_cell=cfg.min_review_outcomes_per_side_cell,
        min_effective_entries_per_side_cell=(
            cfg.min_review_effective_entries_per_side_cell
        ),
        min_distinct_entry_utc_days=cfg.min_review_distinct_entry_utc_days,
        max_top_entry_day_share_pct=cfg.max_review_top_entry_day_share_pct,
        min_avg_net_bps=cfg.min_review_avg_net_bps,
        min_net_positive_pct=cfg.min_review_net_positive_pct,
    )
    review = build_blocked_signal_outcome_review(
        ledger_for_outcomes + outcome_rows,
        now_utc=now,
        cfg=review_cfg,
    )
    packet = build_sealed_horizon_learning_evidence_packet(
        plan=plan,
        candidate=candidate,
        feature_row_count=len(feature_rows),
        materializer_batch=materializer_batch,
        outcome_batch=outcome_batch,
        review=review,
        ledger_path=ledger_path,
        generated_at_utc=now,
    )
    return packet, materializer_batch, outcome_batch, review


def _run_from_args(args: argparse.Namespace) -> dict[str, Any]:
    cfg = SealedHorizonLearningEvidenceConfig(
        engine_modes=tuple(args.engine_modes or ("demo", "live_demo")),
        lookback_hours=args.lookback_hours,
        limit=args.limit,
        maturity_buffer_minutes=args.maturity_buffer_minutes,
        pg_timeframe=args.pg_timeframe,
        default_horizon_minutes=args.horizon_minutes,
        outcome_cost_bps=args.outcome_cost_bps,
        max_entry_delay_ms=args.max_entry_delay_ms,
        max_plan_age_hours=args.max_plan_age_hours,
        min_failed_outcomes_to_disable=args.min_failed_outcomes_to_disable,
        min_outcome_net_positive_pct=args.min_outcome_net_positive_pct,
        min_avg_net_bps=args.min_avg_net_bps,
        min_review_outcomes_per_side_cell=args.min_review_outcomes_per_side_cell,
        min_review_effective_entries_per_side_cell=(
            args.min_review_effective_entries_per_side_cell
        ),
        min_review_distinct_entry_utc_days=args.min_review_distinct_entry_utc_days,
        max_review_top_entry_day_share_pct=(
            args.max_review_top_entry_day_share_pct
        ),
        min_review_avg_net_bps=args.min_review_avg_net_bps,
        min_review_net_positive_pct=args.min_review_net_positive_pct,
        statement_timeout_ms=args.pg_statement_timeout_ms,
    )
    validate_sealed_horizon_evidence_config(cfg)
    plan = _read_json(args.plan)
    if args.side_cell_key:
        candidate = find_sealed_horizon_candidate(
            plan,
            args.side_cell_key,
            default_horizon_minutes=cfg.default_horizon_minutes,
        )
    else:
        candidate = select_default_sealed_horizon_candidate(
            plan,
            default_horizon_minutes=cfg.default_horizon_minutes,
        )

    if args.source_rows:
        feature_rows = _read_json_or_jsonl_rows(args.source_rows)
    else:
        conn = connect_readonly_reject_materializer_pg(
            statement_timeout_ms_default=cfg.statement_timeout_ms,
        )
        try:
            feature_rows = fetch_sealed_horizon_reject_feature_rows(conn, candidate, cfg)
        finally:
            close = getattr(conn, "close", None)
            if callable(close):
                close()
    if args.source_rows_output:
        _write_jsonl(args.source_rows_output, feature_rows)

    existing_rows = read_jsonl_ledger(args.ledger)
    admission_cfg = RuntimeAdmissionConfig(
        max_plan_age_hours=cfg.max_plan_age_hours,
        min_failed_outcomes_to_disable=cfg.min_failed_outcomes_to_disable,
        min_outcome_net_positive_pct=cfg.min_outcome_net_positive_pct,
        min_avg_net_bps=cfg.min_avg_net_bps,
    )
    materializer_batch = build_materialized_reject_ledger_batch(
        plan,
        feature_rows,
        existing_ledger_rows=existing_rows,
        admission_cfg=admission_cfg,
    )
    if args.append_ledger:
        append_materialized_records_to_ledger(args.ledger, materializer_batch)
    materialized_rows = [
        row for row in materializer_batch.get("records", []) if isinstance(row, dict)
    ]
    ledger_for_outcomes = existing_rows + materialized_rows
    selection = OutcomeRefreshSelection(record_blocked_outcomes=True)
    outcome_cfg = ProbeOutcomeConfig(
        horizon_minutes=cfg.default_horizon_minutes,
        cost_bps=cfg.outcome_cost_bps,
        max_entry_delay_ms=cfg.max_entry_delay_ms,
    )
    if args.price_source_pg:
        price_rows = build_price_rows_from_pg_for_refresh(
            ledger_for_outcomes,
            selection=selection,
            outcome_cfg=outcome_cfg,
            timeframe=cfg.pg_timeframe,
            statement_timeout_ms=cfg.statement_timeout_ms,
        )
        price_source = "pg_market_klines"
    else:
        if args.source_prices is None:
            raise ValueError("--source-prices is required unless --price-source-pg is used")
        price_rows = read_source_price_rows(args.source_prices)
        price_source = "local_price_file"

    outcome_batch = build_cost_gate_outcome_refresh_batch(
        ledger_for_outcomes,
        price_rows,
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source=price_source,
    )
    if args.price_source_pg:
        outcome_batch["pg_timeframe"] = cfg.pg_timeframe
    if args.append_ledger:
        append_refresh_outcomes_to_ledger(args.ledger, outcome_batch)
    outcome_rows = [
        row for row in outcome_batch.get("outcomes", []) if isinstance(row, dict)
    ]
    review_cfg = BlockedOutcomeReviewConfig(
        min_outcomes_per_side_cell=cfg.min_review_outcomes_per_side_cell,
        min_effective_entries_per_side_cell=(
            cfg.min_review_effective_entries_per_side_cell
        ),
        min_distinct_entry_utc_days=cfg.min_review_distinct_entry_utc_days,
        max_top_entry_day_share_pct=cfg.max_review_top_entry_day_share_pct,
        min_avg_net_bps=cfg.min_review_avg_net_bps,
        min_net_positive_pct=cfg.min_review_net_positive_pct,
    )
    review = build_blocked_signal_outcome_review(
        ledger_for_outcomes + outcome_rows,
        cfg=review_cfg,
    )
    if args.review_output:
        _write_json(args.review_output, review)
    packet = build_sealed_horizon_learning_evidence_packet(
        plan=plan,
        candidate=candidate,
        feature_row_count=len(feature_rows),
        materializer_batch=materializer_batch,
        outcome_batch=outcome_batch,
        review=review,
        ledger_path=args.ledger,
        plan_path=args.plan,
        output_path=args.output,
        source_rows_path=args.source_rows_output or args.source_rows,
        review_path=args.review_output,
    )
    if args.output:
        _write_json(args.output, packet)
    return packet


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--side-cell-key")
    parser.add_argument("--ledger", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-pg", action="store_true")
    source.add_argument("--source-rows", type=Path)
    price_source = parser.add_mutually_exclusive_group(required=True)
    price_source.add_argument("--price-source-pg", action="store_true")
    price_source.add_argument("--source-prices", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--review-output", type=Path)
    parser.add_argument("--source-rows-output", type=Path)
    parser.add_argument("--append-ledger", action="store_true")
    parser.add_argument("--engine-mode", action="append", dest="engine_modes")
    parser.add_argument("--lookback-hours", type=int, default=72)
    parser.add_argument("--limit", type=int, default=50_000)
    parser.add_argument("--maturity-buffer-minutes", type=int, default=0)
    parser.add_argument("--horizon-minutes", type=int, default=60)
    parser.add_argument("--outcome-cost-bps", type=float, default=4.0)
    parser.add_argument("--max-entry-delay-ms", type=int, default=5 * 60_000)
    parser.add_argument("--pg-timeframe", default="1m")
    parser.add_argument("--pg-statement-timeout-ms", type=int, default=180_000)
    parser.add_argument("--max-plan-age-hours", type=int, default=48)
    # P2-7:CLI 默認與 SealedHorizonEvidenceConfig / RuntimeAdmissionConfig 同步(n≥8)。
    parser.add_argument("--min-failed-outcomes-to-disable", type=int, default=8)
    parser.add_argument("--min-outcome-net-positive-pct", type=float, default=50.0)
    parser.add_argument("--min-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--min-review-outcomes-per-side-cell", type=int, default=100)
    # F1:distinct-entry n_eff 候選門檻(默認 30 = QC 預註冊 §3 E1 凍結值)。
    parser.add_argument(
        "--min-review-effective-entries-per-side-cell", type=int, default=30
    )
    # 預註冊 §3 E2/E3 凍結值(distinct UTC days ≥5;top-day share ≤50%)。
    parser.add_argument("--min-review-distinct-entry-utc-days", type=int, default=5)
    parser.add_argument(
        "--max-review-top-entry-day-share-pct", type=float, default=50.0
    )
    parser.add_argument("--min-review-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--min-review-net-positive-pct", type=float, default=60.0)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = _run_from_args(args)
    if args.print_json or not args.output:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

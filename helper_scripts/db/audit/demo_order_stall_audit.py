#!/usr/bin/env python3
"""Read-only audit for demo/live_demo order-flow stalls.

This script answers a narrow operational question: when demo has not placed
orders recently, where did the pipeline stop?

It deliberately separates observation/candidate data from actual order flow:

    decision_context_snapshots / decision_features_evaluations
      -> risk_verdicts
      -> intents
      -> orders
      -> fills

No PG writes, no Bybit calls, no order placement, no risk/config mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper_scripts.lib.pg_connect import connect_report_pg  # noqa: E402


VALID_ENGINE_MODES = {"paper", "demo", "live_demo", "live", "live_testnet", "replay"}


@dataclass(frozen=True)
class AuditConfig:
    engine_modes: tuple[str, ...]
    lookback_hours: int
    top_limit: int = 20


def validate_config(cfg: AuditConfig) -> None:
    if not cfg.engine_modes:
        raise ValueError("at least one engine mode is required")
    bad = [m for m in cfg.engine_modes if m not in VALID_ENGINE_MODES]
    if bad:
        raise ValueError(f"invalid engine mode(s): {bad}")
    if cfg.lookback_hours < 1 or cfg.lookback_hours > 24 * 30:
        raise ValueError("--lookback-hours must be in [1, 720]")
    if cfg.top_limit < 1 or cfg.top_limit > 200:
        raise ValueError("--top-limit must be in [1, 200]")


def build_pipeline_counts_sql() -> str:
    return """
WITH params AS (
    SELECT %s::text[] AS engine_modes, %s::int AS lookback_hours
),
dcs AS (
    SELECT d.*
    FROM trading.decision_context_snapshots d, params p
    WHERE d.engine_mode = ANY(p.engine_modes)
      AND d.ts >= now() - (p.lookback_hours * interval '1 hour')
),
evals AS (
    SELECT e.*
    FROM learning.decision_features_evaluations e, params p
    WHERE e.engine_mode = ANY(p.engine_modes)
      AND e.ts >= now() - (p.lookback_hours * interval '1 hour')
),
features AS (
    SELECT f.*
    FROM learning.decision_features f, params p
    WHERE f.engine_mode = ANY(p.engine_modes)
      AND f.ts >= now() - (p.lookback_hours * interval '1 hour')
),
rv AS (
    SELECT r.*
    FROM trading.risk_verdicts r, params p
    WHERE r.engine_mode = ANY(p.engine_modes)
      AND r.ts >= now() - (p.lookback_hours * interval '1 hour')
),
intents AS (
    SELECT i.*
    FROM trading.intents i, params p
    WHERE i.engine_mode = ANY(p.engine_modes)
      AND i.ts >= now() - (p.lookback_hours * interval '1 hour')
),
orders AS (
    SELECT o.*
    FROM trading.orders o, params p
    WHERE o.engine_mode = ANY(p.engine_modes)
      AND o.ts >= now() - (p.lookback_hours * interval '1 hour')
),
order_states AS (
    SELECT
        o.order_id,
        bool_or(lower(coalesce(osc.to_status, '')) IN (
            'filled',
            'partiallyfilled',
            'partially_filled'
        )) AS any_fill_state,
        bool_or(lower(coalesce(osc.to_status, '')) = 'rejected') AS any_rejected_state,
        bool_or(lower(coalesce(osc.to_status, '')) IN (
            'cancelled',
            'canceled',
            'deactivated'
        )) AS any_cancelled_state,
        bool_or(
            coalesce(osc.reason, '') ILIKE '%post_only_cross%'
            OR coalesce(osc.reason, '') ILIKE '%postonlywilltakeliquidity%'
            OR coalesce(osc.reason, '') ILIKE '%post only will take liquidity%'
            OR coalesce(osc.reason, '') ILIKE '%ec_postonlywilltakeliquidity%'
        ) AS any_post_only_cross
    FROM orders o
    LEFT JOIN trading.order_state_changes osc
      ON osc.order_id = o.order_id
     AND osc.ts >= o.ts
    GROUP BY o.order_id
),
fills AS (
    SELECT f.*
    FROM trading.fills f, params p
    WHERE f.engine_mode = ANY(p.engine_modes)
      AND f.ts >= now() - (p.lookback_hours * interval '1 hour')
)
SELECT
    (SELECT count(*)::bigint FROM dcs) AS decision_context_snapshots,
    (SELECT max(ts) FROM dcs) AS latest_decision_context_ts,
    (SELECT count(*)::bigint FROM evals) AS candidate_evaluations,
    (SELECT max(ts) FROM evals) AS latest_candidate_evaluation_ts,
    (SELECT count(*)::bigint FROM features) AS decision_features,
    (SELECT max(ts) FROM features) AS latest_decision_feature_ts,
    (SELECT count(*)::bigint FROM features WHERE reject_reason_code IS NOT NULL)
        AS rejected_decision_features,
    (SELECT count(*)::bigint FROM rv) AS risk_verdicts,
    (SELECT max(ts) FROM rv) AS latest_risk_verdict_ts,
    (SELECT count(*)::bigint FROM rv WHERE lower(verdict) = 'approved')
        AS approved_risk_verdicts,
    (SELECT count(*)::bigint FROM rv WHERE lower(verdict) = 'rejected')
        AS rejected_risk_verdicts,
    (SELECT count(*)::bigint FROM intents) AS intents,
    (SELECT max(ts) FROM intents) AS latest_intent_ts,
    (SELECT count(*)::bigint FROM orders) AS orders,
    (SELECT max(ts) FROM orders) AS latest_order_ts,
    (
        SELECT count(*)::bigint
        FROM orders
        WHERE lower(coalesce(order_type, '')) = 'limit'
          AND lower(replace(coalesce(time_in_force, ''), '_', '')) = 'postonly'
    ) AS post_only_orders,
    (SELECT count(*)::bigint FROM order_states WHERE coalesce(any_fill_state, false))
        AS orders_with_fill_state,
    (SELECT count(*)::bigint FROM order_states WHERE coalesce(any_rejected_state, false))
        AS orders_with_rejected_state,
    (SELECT count(*)::bigint FROM order_states WHERE coalesce(any_cancelled_state, false))
        AS orders_with_cancelled_state,
    (SELECT count(*)::bigint FROM order_states WHERE coalesce(any_post_only_cross, false))
        AS post_only_cross_orders,
    (SELECT count(*)::bigint FROM fills) AS fills,
    (SELECT max(ts) FROM fills) AS latest_fill_ts,
    (
        SELECT round(
            coalesce(sum(coalesce(realized_pnl, 0) - abs(coalesce(fee, 0))), 0)::numeric,
            4
        )
        FROM fills
    ) AS net_pnl_usdt
"""


def build_risk_reason_sql() -> str:
    return """
WITH params AS (
    SELECT %s::text[] AS engine_modes, %s::int AS lookback_hours
),
rv AS (
    SELECT r.*
    FROM trading.risk_verdicts r, params p
    WHERE r.engine_mode = ANY(p.engine_modes)
      AND r.ts >= now() - (p.lookback_hours * interval '1 hour')
)
SELECT
    coalesce(nullif(reason, ''), '<empty>') AS reason,
    count(*)::bigint AS n,
    max(ts) AS latest_ts,
    count(*) FILTER (WHERE lower(verdict) = 'approved')::bigint AS approved_n,
    count(*) FILTER (WHERE lower(verdict) = 'rejected')::bigint AS rejected_n
FROM rv
GROUP BY 1
ORDER BY n DESC, reason
LIMIT %s
"""


def build_evaluation_outcome_sql() -> str:
    return """
WITH params AS (
    SELECT %s::text[] AS engine_modes, %s::int AS lookback_hours
),
evals AS (
    SELECT e.*
    FROM learning.decision_features_evaluations e, params p
    WHERE e.engine_mode = ANY(p.engine_modes)
      AND e.ts >= now() - (p.lookback_hours * interval '1 hour')
)
SELECT
    evaluation_outcome,
    evidence_source_tier,
    count(*)::bigint AS n,
    max(ts) AS latest_ts,
    count(DISTINCT symbol)::bigint AS symbols
FROM evals
GROUP BY evaluation_outcome, evidence_source_tier
ORDER BY n DESC, evaluation_outcome, evidence_source_tier
LIMIT %s
"""


def build_intent_order_lineage_sql() -> str:
    return """
WITH params AS (
    SELECT %s::text[] AS engine_modes, %s::int AS lookback_hours
),
recent_intents AS (
    SELECT i.*
    FROM trading.intents i, params p
    WHERE i.engine_mode = ANY(p.engine_modes)
      AND i.ts >= now() - (p.lookback_hours * interval '1 hour')
),
recent_orders AS (
    SELECT o.*
    FROM trading.orders o, params p
    WHERE o.engine_mode = ANY(p.engine_modes)
      AND o.ts >= now() - (p.lookback_hours * interval '1 hour')
),
per_intent AS (
    SELECT
        i.intent_id,
        i.engine_mode,
        i.ts,
        count(o.order_id)::bigint AS joined_orders
    FROM recent_intents i
    LEFT JOIN recent_orders o
      ON o.intent_id = i.intent_id
     AND o.engine_mode = i.engine_mode
    GROUP BY i.intent_id, i.engine_mode, i.ts
)
SELECT
    count(*)::bigint AS intents,
    count(*) FILTER (WHERE joined_orders > 0)::bigint AS intents_with_orders,
    count(*) FILTER (WHERE joined_orders = 0)::bigint AS intents_without_orders,
    coalesce(sum(joined_orders), 0)::bigint AS joined_orders,
    round(
        100.0 * count(*) FILTER (WHERE joined_orders = 0) / nullif(count(*), 0),
        4
    ) AS intent_without_order_pct,
    max(ts) AS latest_intent_ts
FROM per_intent
"""


def fetch_one(conn: Any, sql: str, params: list[Any]) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [desc[0] for desc in cur.description]
        row = cur.fetchone()
    return dict(zip(cols, row)) if row else {}


def fetch_rows(conn: Any, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_audit(conn: Any, cfg: AuditConfig) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    validate_config(cfg)
    base = [list(cfg.engine_modes), cfg.lookback_hours]
    counts = fetch_one(conn, build_pipeline_counts_sql(), base)
    risk_reasons = fetch_rows(conn, build_risk_reason_sql(), [*base, cfg.top_limit])
    eval_outcomes = fetch_rows(conn, build_evaluation_outcome_sql(), [*base, cfg.top_limit])
    lineage = fetch_one(conn, build_intent_order_lineage_sql(), base)
    return counts, risk_reasons, eval_outcomes, lineage


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def reason_category(reason: str) -> str:
    value = reason.lower()
    if "cost_gate" in value:
        return "cost_gate"
    if "predictor" in value or "edge_predictor" in value:
        return "predictor_gate"
    if "blocked_symbols" in value or "blocked by per_strategy" in value:
        return "strategy_blocklist"
    if "exposure" in value or "position" in value or "drawdown" in value:
        return "risk_envelope"
    if "auth" in value or "lease" in value:
        return "governance_auth"
    return "other"


def dominant_risk_category(
    risk_reasons: list[dict[str, Any]],
    total_risk_verdicts: int,
) -> dict[str, Any]:
    if total_risk_verdicts <= 0 or not risk_reasons:
        return {"category": None, "n": 0, "pct": 0.0, "top_reason": None}
    counts: dict[str, int] = {}
    top_reason = str(risk_reasons[0].get("reason") or "")
    for row in risk_reasons:
        category = reason_category(str(row.get("reason") or ""))
        counts[category] = counts.get(category, 0) + _as_int(row.get("n"))
    category, n = max(counts.items(), key=lambda item: item[1])
    return {
        "category": category,
        "n": n,
        "pct": round((n / total_risk_verdicts) * 100.0, 4),
        "top_reason": top_reason,
    }


def classify_order_stall(
    counts: dict[str, Any],
    risk_reasons: list[dict[str, Any]],
    lineage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dcs = _as_int(counts.get("decision_context_snapshots"))
    evaluations = _as_int(counts.get("candidate_evaluations"))
    features = _as_int(counts.get("decision_features"))
    rejected_features = _as_int(counts.get("rejected_decision_features"))
    risk = _as_int(counts.get("risk_verdicts"))
    approved = _as_int(counts.get("approved_risk_verdicts"))
    intents = _as_int(counts.get("intents"))
    orders = _as_int(counts.get("orders"))
    fills = _as_int(counts.get("fills"))
    rejected_orders = _as_int(counts.get("orders_with_rejected_state"))
    cancelled_orders = _as_int(counts.get("orders_with_cancelled_state"))
    post_only_cross = _as_int(counts.get("post_only_cross_orders"))
    risk_category = dominant_risk_category(risk_reasons, risk)
    warnings: list[str] = []

    if evaluations > 0 and features == 0:
        warnings.append("candidate_evaluations_accumulating_but_no_intent_training_rows")
    if risk > 0 and rejected_features == 0:
        warnings.append("risk_verdicts_present_without_rejected_decision_features")
    if risk_category["category"] == "cost_gate":
        warnings.append("cost_gate_dominates_recent_risk_verdicts")
    if lineage and _as_float(lineage.get("intent_without_order_pct")) is not None:
        orphan_pct = _as_float(lineage.get("intent_without_order_pct")) or 0.0
        if _as_int(lineage.get("intents")) > 0 and orphan_pct > 50.0:
            warnings.append("intent_order_lineage_orphan_high")

    observed = dcs + evaluations + features + risk + intents + orders + fills
    if observed == 0:
        status = "NO_RECENT_PIPELINE_DATA"
        stage = "observation"
        reason = "no recent signal, candidate, verdict, intent, order, or fill rows"
    elif fills > 0:
        status = "RECENT_FILL_FLOW_PRESENT"
        stage = "fills"
        reason = "recent fills exist; demo did order/fill inside lookback"
    elif orders > 0:
        if rejected_orders > 0 or cancelled_orders > 0 or post_only_cross > 0:
            status = "ORDER_REJECT_OR_POST_ONLY_GAP"
            reason = "orders exist but state changes show rejects/cancels/post-only crosses"
        else:
            status = "ORDER_TO_FILL_GAP"
            reason = "orders exist but no fills landed inside lookback"
        stage = "orders_to_fills"
    elif intents > 0:
        status = "INTENT_TO_ORDER_GAP"
        stage = "intents_to_orders"
        reason = "intents exist but no exchange-confirmed orders landed"
    elif risk > 0:
        stage = "risk_to_intents"
        if approved > 0:
            status = "APPROVED_VERDICT_INTENT_PERSISTENCE_GAP"
            reason = "approved risk verdicts exist but no intents landed"
        elif risk_category["category"] == "cost_gate":
            status = "COST_GATE_REJECTING_ALL_RECENT_ATTEMPTS"
            reason = "risk verdicts are present and dominated by cost-gate rejection"
        else:
            status = "RISK_GATE_REJECTING_ALL_RECENT_ATTEMPTS"
            reason = "risk verdicts are present but no approved intent landed"
    elif evaluations > 0:
        status = "PREDICTOR_OR_STRATEGY_PRE_RISK_GATE"
        stage = "candidate_to_risk"
        reason = "candidate evaluations exist but no risk verdicts or intents landed"
    elif dcs > 0:
        status = "SIGNAL_OBSERVATION_ONLY_PRE_GATE"
        stage = "signal_to_candidate"
        reason = "decision context snapshots exist but no candidate/risk/order rows landed"
    else:
        status = "DECISION_FEATURES_ONLY"
        stage = "feature_writer"
        reason = "decision feature rows exist without later order-flow rows"

    if status == "NO_RECENT_PIPELINE_DATA":
        data_status = "NOT_ACCUMULATING_RECENT_DATA"
    elif evaluations > 0 or risk > 0 or rejected_features > 0:
        data_status = "REJECT_OR_CANDIDATE_DATA_ACCUMULATING"
    else:
        data_status = "OBSERVATION_OR_ORDER_DATA_ACCUMULATING"

    return {
        "status": status,
        "primary_blocker_stage": stage,
        "primary_blocker_reason": reason,
        "data_accumulation_status": data_status,
        "dominant_risk_category": risk_category,
        "warnings": warnings,
        "answers": {
            "recent_orders_or_fills_present": orders > 0 or fills > 0,
            "candidate_or_reject_data_accumulating": evaluations > 0
            or risk > 0
            or rejected_features > 0,
            "rejected_signals_recorded": risk > 0 or rejected_features > 0,
            "silent_drop_risk": dcs > 0 and evaluations == 0 and risk == 0 and intents == 0,
            "cost_gate_dominant": risk_category["category"] == "cost_gate",
            "global_cost_gate_lowering_recommended": False,
            "bounded_demo_learning_lane_recommended": risk_category["category"] == "cost_gate"
            and intents == 0,
        },
    }


def build_scorecard(
    cfg: AuditConfig,
    counts: dict[str, Any],
    risk_reasons: list[dict[str, Any]],
    eval_outcomes: list[dict[str, Any]],
    lineage: dict[str, Any],
) -> dict[str, Any]:
    classification = classify_order_stall(counts, risk_reasons, lineage)
    return {
        "schema_version": "demo_order_stall_audit_v1",
        "engine_modes": list(cfg.engine_modes),
        "lookback_hours": cfg.lookback_hours,
        "classification": classification,
        "counts": counts,
        "risk_reason_top": risk_reasons,
        "evaluation_outcome_top": eval_outcomes,
        "intent_order_lineage": lineage,
        "boundary": "read-only PG SELECT; no Bybit call, order, config, risk, auth, runtime, or schema mutation",
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def build_json_payload(
    cfg: AuditConfig,
    counts: dict[str, Any],
    risk_reasons: list[dict[str, Any]],
    eval_outcomes: list[dict[str, Any]],
    lineage: dict[str, Any],
    *,
    generated: str | None = None,
) -> dict[str, Any]:
    generated = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    return {
        "generated_at_utc": generated,
        **build_scorecard(cfg, counts, risk_reasons, eval_outcomes, lineage),
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, Decimal):
        return f"{float(value):.4f}"
    return str(value)


def render_markdown(
    cfg: AuditConfig,
    counts: dict[str, Any],
    risk_reasons: list[dict[str, Any]],
    eval_outcomes: list[dict[str, Any]],
    lineage: dict[str, Any],
    *,
    generated: str | None = None,
) -> str:
    generated = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    scorecard = build_scorecard(cfg, counts, risk_reasons, eval_outcomes, lineage)
    cls = scorecard["classification"]
    answers = cls["answers"]
    lines = [
        "# Demo Order Stall Audit",
        "",
        f"- Generated: `{generated}`",
        f"- Engine modes: `{','.join(cfg.engine_modes)}`",
        f"- Lookback: `{cfg.lookback_hours}` hours",
        "- Boundary: read-only PG SELECT; no Bybit call, order, config, risk, auth, runtime, or schema mutation.",
        "",
        "## Classification",
        "",
        f"- Status: `{cls['status']}`",
        f"- Primary stage: `{cls['primary_blocker_stage']}`",
        f"- Reason: {cls['primary_blocker_reason']}",
        f"- Data accumulation: `{cls['data_accumulation_status']}`",
        f"- Dominant risk category: `{_fmt(cls['dominant_risk_category'].get('category'))}` "
        f"({_fmt(cls['dominant_risk_category'].get('pct'))}%)",
        f"- Global cost-gate lowering recommended: `{answers['global_cost_gate_lowering_recommended']}`",
        f"- Bounded demo-learning lane recommended: `{answers['bounded_demo_learning_lane_recommended']}`",
        "",
        "## Pipeline Counts",
        "",
        "| stage | count | latest |",
        "|---|---:|---|",
    ]
    for label, count_key, ts_key in [
        ("decision_context_snapshots", "decision_context_snapshots", "latest_decision_context_ts"),
        ("candidate_evaluations", "candidate_evaluations", "latest_candidate_evaluation_ts"),
        ("decision_features", "decision_features", "latest_decision_feature_ts"),
        ("risk_verdicts", "risk_verdicts", "latest_risk_verdict_ts"),
        ("intents", "intents", "latest_intent_ts"),
        ("orders", "orders", "latest_order_ts"),
        ("fills", "fills", "latest_fill_ts"),
    ]:
        lines.append(f"| {label} | {_fmt(counts.get(count_key))} | {_fmt(counts.get(ts_key))} |")

    lines.extend(
        [
            "",
            "## Gate And Order Details",
            "",
            "| metric | value |",
            "|---|---:|",
        ]
    )
    for key in [
        "rejected_decision_features",
        "approved_risk_verdicts",
        "rejected_risk_verdicts",
        "post_only_orders",
        "orders_with_fill_state",
        "orders_with_rejected_state",
        "orders_with_cancelled_state",
        "post_only_cross_orders",
        "net_pnl_usdt",
    ]:
        lines.append(f"| {key} | {_fmt(counts.get(key))} |")
    for key in [
        "intents",
        "intents_with_orders",
        "intents_without_orders",
        "joined_orders",
        "intent_without_order_pct",
    ]:
        lines.append(f"| lineage_{key} | {_fmt(lineage.get(key))} |")

    lines.extend(
        [
            "",
            "## Risk Reasons",
            "",
            "| reason | category | n | approved | rejected | latest |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for row in risk_reasons:
        reason = str(row.get("reason") or "")
        lines.append(
            f"| {reason} | {reason_category(reason)} | {_fmt(row.get('n'))} | "
            f"{_fmt(row.get('approved_n'))} | {_fmt(row.get('rejected_n'))} | "
            f"{_fmt(row.get('latest_ts'))} |"
        )

    lines.extend(
        [
            "",
            "## Candidate Evaluation Outcomes",
            "",
            "| outcome | tier | n | symbols | latest |",
            "|---|---|---:|---:|---|",
        ]
    )
    for row in eval_outcomes:
        lines.append(
            f"| {_fmt(row.get('evaluation_outcome'))} | {_fmt(row.get('evidence_source_tier'))} | "
            f"{_fmt(row.get('n'))} | {_fmt(row.get('symbols'))} | {_fmt(row.get('latest_ts'))} |"
        )

    if cls["warnings"]:
        lines.extend(["", "## Warnings", ""])
        for warning in cls["warnings"]:
            lines.append(f"- `{warning}`")
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-mode", action="append", dest="engine_modes")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--top-limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = AuditConfig(
        engine_modes=tuple(args.engine_modes or ["demo", "live_demo"]),
        lookback_hours=args.lookback_hours,
        top_limit=args.top_limit,
    )
    validate_config(cfg)
    conn = connect_report_pg(
        "demo_order_stall_audit",
        statement_timeout_ms_default=180_000,
    )
    try:
        conn.rollback()
        conn.set_session(readonly=True, autocommit=True)
        counts, risk_reasons, eval_outcomes, lineage = fetch_audit(conn, cfg)
    finally:
        conn.close()

    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = render_markdown(
        cfg,
        counts,
        risk_reasons,
        eval_outcomes,
        lineage,
        generated=generated,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    if args.json_output:
        payload = build_json_payload(
            cfg,
            counts,
            risk_reasons,
            eval_outcomes,
            lineage,
            generated=generated,
        )
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

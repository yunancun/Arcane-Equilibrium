#!/usr/bin/env python3
"""Read-only counterfactual audit for cost-gate rejections.

The normal outcome path is:

    decision_context_snapshots -> decision_outcomes

That path is useful when labels are caught up, but it can lag large signal
bursts. This audit measures rejected cost-gate decisions directly from
``learning.decision_features`` and future ``market.klines`` prices, so the
operator can see whether blocked signals later moved in the blocked direction.

No PG writes, no order placement, no risk/config mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper_scripts.lib.pg_connect import connect_report_pg  # noqa: E402


VALID_ENGINE_MODES = {"paper", "demo", "live_demo", "live"}


@dataclass(frozen=True)
class AuditConfig:
    engine_modes: tuple[str, ...]
    lookback_hours: int
    horizon_minutes: int
    limit: int
    friction_bps: float
    strategy: str | None = None
    symbol: str | None = None
    side: int | None = None
    min_probe_sample: int = 100
    min_probe_avg_net_bps: float = 0.0
    min_probe_net_positive_pct: float = 55.0
    max_block_net_positive_pct: float = 40.0


def side_to_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in {"buy", "long", "1"}:
        return 1
    if value in {"sell", "short", "-1"}:
        return -1
    raise ValueError("--side must be Buy/Long/1 or Sell/Short/-1")


def validate_config(cfg: AuditConfig) -> None:
    if not cfg.engine_modes:
        raise ValueError("at least one engine mode is required")
    bad = [m for m in cfg.engine_modes if m not in VALID_ENGINE_MODES]
    if bad:
        raise ValueError(f"invalid engine mode(s): {bad}")
    if cfg.lookback_hours < 1 or cfg.lookback_hours > 24 * 30:
        raise ValueError("--lookback-hours must be in [1, 720]")
    if cfg.horizon_minutes < 1 or cfg.horizon_minutes > 24 * 60:
        raise ValueError("--horizon-minutes must be in [1, 1440]")
    if cfg.limit < 1 or cfg.limit > 500_000:
        raise ValueError("--limit must be in [1, 500000]")
    if cfg.friction_bps < 0 or cfg.friction_bps > 200:
        raise ValueError("--friction-bps must be in [0, 200]")
    if cfg.min_probe_sample < 1 or cfg.min_probe_sample > cfg.limit:
        raise ValueError("--min-probe-sample must be in [1, --limit]")
    if cfg.min_probe_net_positive_pct < 0 or cfg.min_probe_net_positive_pct > 100:
        raise ValueError("--min-probe-net-positive-pct must be in [0, 100]")
    if cfg.max_block_net_positive_pct < 0 or cfg.max_block_net_positive_pct > 100:
        raise ValueError("--max-block-net-positive-pct must be in [0, 100]")


def build_coverage_sql() -> str:
    return """
WITH rv AS (
    SELECT rv.*
    FROM trading.risk_verdicts rv
    WHERE rv.engine_mode = ANY(%s)
      AND rv.ts >= now() - (%s::int * interval '1 hour')
      AND rv.reason LIKE 'cost_gate%%'
),
features AS (
    SELECT f.*
    FROM learning.decision_features f
    WHERE f.engine_mode = ANY(%s)
      AND f.ts >= now() - (%s::int * interval '1 hour')
      AND f.reject_reason_code LIKE 'cost_gate%%'
)
SELECT
    (SELECT count(*)::bigint FROM rv) AS risk_verdicts,
    (SELECT max(ts) FROM rv) AS latest_risk_verdict_ts,
    (
      SELECT count(*)::bigint
      FROM rv
      JOIN trading.intents i
        ON i.intent_id = rv.intent_id
       AND i.engine_mode = rv.engine_mode
    ) AS risk_verdicts_joined_intents,
    (SELECT count(*)::bigint FROM features) AS decision_features,
    (
      SELECT count(*)::bigint
      FROM features f
      JOIN trading.decision_context_snapshots d
        ON d.context_id = f.context_id
    ) AS features_joined_contexts,
    (
      SELECT count(*)::bigint
      FROM features f
      JOIN trading.decision_outcomes o
        ON o.context_id = f.context_id
    ) AS features_joined_outcomes,
    (
      SELECT count(*)::bigint
      FROM trading.decision_context_snapshots d
      WHERE d.outcome_backfilled = false
        AND d.ts < now() - interval '25 hours'
    ) AS decision_context_old_pending
"""


def build_counterfactual_sql(cfg: AuditConfig) -> tuple[str, list[Any]]:
    validate_config(cfg)
    where = [
        "f.engine_mode = ANY(%s)",
        "f.ts >= now() - (%s::int * interval '1 hour')",
        "f.ts < now() - (%s::int * interval '1 minute')",
        "f.reject_reason_code LIKE 'cost_gate%%'",
    ]
    params: list[Any] = [list(cfg.engine_modes), cfg.lookback_hours, cfg.horizon_minutes]
    if cfg.strategy:
        where.append("f.strategy_name = %s")
        params.append(cfg.strategy)
    if cfg.symbol:
        where.append("f.symbol = %s")
        params.append(cfg.symbol)
    if cfg.side is not None:
        where.append("f.side = %s")
        params.append(cfg.side)
    params.extend([cfg.limit, cfg.horizon_minutes, cfg.friction_bps, cfg.friction_bps])

    sql = f"""
WITH base AS (
    SELECT f.ts, f.context_id, f.engine_mode, f.strategy_name, f.symbol,
           f.side, f.reject_reason_code
    FROM learning.decision_features f
    WHERE {' AND '.join(where)}
    ORDER BY f.ts DESC
    LIMIT %s
),
priced AS (
    SELECT b.*,
           COALESCE(d.last_price::float8, k0.close::float8) AS entry_px,
           kh.close::float8 AS future_px,
           (d.context_id IS NOT NULL) AS has_context
    FROM base b
    LEFT JOIN trading.decision_context_snapshots d
      ON d.context_id = b.context_id
    LEFT JOIN LATERAL (
        SELECT k.close
        FROM market.klines k
        WHERE k.symbol = b.symbol
          AND k.timeframe = '1m'
          AND k.ts <= b.ts
        ORDER BY k.ts DESC
        LIMIT 1
    ) k0 ON TRUE
    LEFT JOIN LATERAL (
        SELECT k.close
        FROM market.klines k
        WHERE k.symbol = b.symbol
          AND k.timeframe = '1m'
          AND k.ts >= b.ts + (%s::int * interval '1 minute')
        ORDER BY k.ts ASC
        LIMIT 1
    ) kh ON TRUE
),
scored AS (
    SELECT *,
           ((future_px - entry_px) / NULLIF(entry_px, 0)) * 10000.0 * side
             AS directional_gross_bps
    FROM priced
    WHERE entry_px > 0
      AND future_px > 0
)
SELECT
    strategy_name,
    symbol,
    CASE WHEN side = 1 THEN 'Buy' ELSE 'Sell' END AS side,
    reject_reason_code,
    count(*)::bigint AS n,
    count(*) FILTER (WHERE has_context)::bigint AS joined_contexts,
    min(ts) AS min_ts,
    max(ts) AS max_ts,
    round(avg(directional_gross_bps)::numeric, 4) AS avg_gross_bps,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY directional_gross_bps)::numeric, 4)
      AS p50_gross_bps,
    round(percentile_cont(0.9) WITHIN GROUP (ORDER BY directional_gross_bps)::numeric, 4)
      AS p90_gross_bps,
    round(avg(directional_gross_bps - %s)::numeric, 4) AS avg_net_bps,
    round((avg((directional_gross_bps > 0)::int) * 100)::numeric, 2)
      AS gross_positive_pct,
    round((avg((directional_gross_bps > %s)::int) * 100)::numeric, 2)
      AS net_positive_pct
FROM scored
GROUP BY strategy_name, symbol, side, reject_reason_code
ORDER BY n DESC, strategy_name, symbol, side
"""
    return sql, params


def fetch_coverage(conn: Any, cfg: AuditConfig) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            build_coverage_sql(),
            [list(cfg.engine_modes), cfg.lookback_hours, list(cfg.engine_modes), cfg.lookback_hours],
        )
        cols = [desc[0] for desc in cur.description]
        row = cur.fetchone()
    return dict(zip(cols, row)) if row else {}


def fetch_counterfactual_rows(conn: Any, cfg: AuditConfig) -> list[dict[str, Any]]:
    sql, params = build_counterfactual_sql(cfg)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cols = [desc[0] for desc in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, Decimal):
        return f"{float(value):.4f}"
    return str(value)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def classify_learning_lane_row(cfg: AuditConfig, row: dict[str, Any]) -> tuple[str, str]:
    reject_reason = str(row.get("reject_reason_code") or "").lower()
    if "unavailable" in reject_reason or "missing" in reject_reason:
        return "DATA_COVERAGE_BLOCKER", "reject_reason_requires_data_fix_not_probe"
    if "negative_edge" not in reject_reason:
        return "NON_EDGE_REJECT_REASON", "reject_reason_not_negative_edge"
    n = int(row.get("n") or 0)
    avg_net = _as_float(row.get("avg_net_bps"))
    p50_gross = _as_float(row.get("p50_gross_bps"))
    p90_gross = _as_float(row.get("p90_gross_bps"))
    net_positive_pct = _as_float(row.get("net_positive_pct"))
    if n < cfg.min_probe_sample:
        return "INSUFFICIENT_SAMPLE", f"n<{cfg.min_probe_sample}"
    if avg_net is None or p50_gross is None or p90_gross is None or net_positive_pct is None:
        return "UNSCORABLE", "missing_counterfactual_metrics"
    if (
        avg_net > cfg.min_probe_avg_net_bps
        and p50_gross > cfg.friction_bps
        and net_positive_pct >= cfg.min_probe_net_positive_pct
    ):
        return (
            "LEARNING_PROBE_CANDIDATE",
            "avg_net_positive_and_median_gross_clears_friction",
        )
    if avg_net <= 0 and net_positive_pct <= cfg.max_block_net_positive_pct:
        return "BLOCK_CONFIRMED", "avg_net_nonpositive_and_low_net_positive_rate"
    if avg_net > cfg.min_probe_avg_net_bps and p90_gross > cfg.friction_bps:
        return "TAIL_ONLY_WATCH", "positive_average_but_median_or_hit_rate_not_ready"
    return "NO_PROBE", "does_not_clear_learning_probe_thresholds"


def annotate_learning_lane_rows(
    cfg: AuditConfig,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for row in rows:
        action, reason = classify_learning_lane_row(cfg, row)
        enriched = dict(row)
        enriched["learning_lane_action"] = action
        enriched["learning_lane_reason"] = reason
        annotated.append(enriched)
    return annotated


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sort_float(value: Any) -> float:
    parsed = _as_float(value)
    return parsed if parsed is not None else float("-inf")


def _side_cell_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            str(row.get("strategy_name") or "unknown_strategy"),
            str(row.get("symbol") or "unknown_symbol"),
            str(row.get("side") or "unknown_side"),
        ]
    )


def _bounded_score(value: float, scale: float, weight: float) -> float:
    if scale <= 0:
        return 0.0
    return min(max(value, 0.0) / scale, 1.0) * weight


def _profit_priority_components(cfg: AuditConfig, row: dict[str, Any]) -> dict[str, float]:
    n = max(_as_int(row.get("n")), 0)
    avg_net = _as_float(row.get("avg_net_bps")) or 0.0
    p50_gross = _as_float(row.get("p50_gross_bps")) or 0.0
    net_positive_pct = _as_float(row.get("net_positive_pct")) or 0.0
    return {
        "sample_score": min(math.log10(n + 1) / 4.0, 1.0) * 25.0,
        "avg_net_score": _bounded_score(avg_net - cfg.min_probe_avg_net_bps, 100.0, 25.0),
        "median_margin_score": _bounded_score(p50_gross - cfg.friction_bps, 50.0, 25.0),
        "hit_rate_score": _bounded_score(net_positive_pct - 50.0, 50.0, 25.0),
    }


def _profit_priority_tier(action: str, score: float) -> str:
    if action == "LEARNING_PROBE_CANDIDATE":
        if score >= 70.0:
            return "HIGH_PRIORITY_BOUNDED_DEMO_LEARNING"
        if score >= 60.0:
            return "MEDIUM_PRIORITY_BOUNDED_DEMO_LEARNING"
        return "LOW_PRIORITY_BOUNDED_DEMO_LEARNING"
    if action == "BLOCK_CONFIRMED":
        return "KEEP_BLOCKED_CONFIRMED"
    if action == "DATA_COVERAGE_BLOCKER":
        return "DATA_FIX_BEFORE_PROFIT_JUDGMENT"
    if action == "INSUFFICIENT_SAMPLE":
        return "COLLECT_MORE_SAMPLE"
    if action == "TAIL_ONLY_WATCH":
        return "TAIL_ONLY_WATCH_NO_PROBE"
    return "NO_PROBE"


def _profit_next_action(action: str) -> str:
    if action == "LEARNING_PROBE_CANDIDATE":
        return "operator_review_ranked_side_cell_for_bounded_demo_learning_lane"
    if action == "BLOCK_CONFIRMED":
        return "keep_main_cost_gate_block_for_side_cell"
    if action == "DATA_COVERAGE_BLOCKER":
        return "fix_data_coverage_before_profit_judgment"
    if action == "INSUFFICIENT_SAMPLE":
        return "continue_collecting_reject_counterfactual_samples"
    if action == "TAIL_ONLY_WATCH":
        return "continue_watch_without_probe_authority"
    return "do_not_probe_side_cell"


def build_profit_opportunity_ranking(
    cfg: AuditConfig,
    annotated_rows: list[dict[str, Any]],
    action_counts: dict[str, int],
) -> dict[str, Any]:
    """Rank blocked side-cells by learning value without granting authority."""

    ranked_rows: list[dict[str, Any]] = []
    for row in annotated_rows:
        action = str(row.get("learning_lane_action") or "UNSCORABLE")
        components = _profit_priority_components(cfg, row)
        score = round(sum(components.values()), 4)
        n = _as_int(row.get("n"))
        joined_contexts = _as_int(row.get("joined_contexts"))
        context_join_coverage_pct = round((joined_contexts / n * 100.0), 4) if n else 0.0
        avg_net = _as_float(row.get("avg_net_bps"))
        p50_gross = _as_float(row.get("p50_gross_bps"))
        net_positive_pct = _as_float(row.get("net_positive_pct"))
        ranked_rows.append(
            {
                "side_cell_key": _side_cell_key(row),
                "strategy_name": row.get("strategy_name"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "reject_reason_code": row.get("reject_reason_code"),
                "learning_lane_action": action,
                "learning_lane_reason": row.get("learning_lane_reason"),
                "priority_tier": _profit_priority_tier(action, score),
                "priority_score": score,
                "priority_components": {key: round(value, 4) for key, value in components.items()},
                "n": n,
                "joined_contexts": joined_contexts,
                "context_join_coverage_pct": context_join_coverage_pct,
                "avg_net_bps": avg_net,
                "p50_gross_bps": p50_gross,
                "p90_gross_bps": _as_float(row.get("p90_gross_bps")),
                "net_positive_pct": net_positive_pct,
                "net_margin_bps": (
                    round(avg_net - cfg.min_probe_avg_net_bps, 4)
                    if avg_net is not None
                    else None
                ),
                "median_margin_bps": (
                    round(p50_gross - cfg.friction_bps, 4)
                    if p50_gross is not None
                    else None
                ),
                "hit_rate_margin_pct": (
                    round(net_positive_pct - cfg.min_probe_net_positive_pct, 4)
                    if net_positive_pct is not None
                    else None
                ),
                "next_action": _profit_next_action(action),
                "order_authority": "NOT_GRANTED",
                "main_cost_gate_adjustment": "NONE",
                "promotion_evidence": False,
            }
        )

    action_order = {
        "LEARNING_PROBE_CANDIDATE": 0,
        "TAIL_ONLY_WATCH": 1,
        "INSUFFICIENT_SAMPLE": 2,
        "DATA_COVERAGE_BLOCKER": 3,
        "NO_PROBE": 4,
        "UNSCORABLE": 5,
        "BLOCK_CONFIRMED": 6,
    }
    ranked_rows.sort(
        key=lambda row: (
            action_order.get(str(row.get("learning_lane_action")), 9),
            -(float(row.get("priority_score") or 0.0)),
            -_sort_float(row.get("avg_net_bps")),
            -_as_int(row.get("n")),
        )
    )
    candidate_count = int(action_counts.get("LEARNING_PROBE_CANDIDATE") or 0)
    data_blocker_count = int(action_counts.get("DATA_COVERAGE_BLOCKER") or 0)
    sample_gap_count = int(action_counts.get("INSUFFICIENT_SAMPLE") or 0)
    tail_watch_count = int(action_counts.get("TAIL_ONLY_WATCH") or 0)
    if candidate_count:
        status = "PROFIT_LEARNING_CANDIDATES_PRESENT"
        next_trigger = "operator_review_top_ranked_side_cells_for_bounded_demo_learning_lane"
    elif data_blocker_count:
        status = "DATA_COVERAGE_BLOCKS_PROFIT_JUDGMENT"
        next_trigger = "fix_data_coverage_before_probe_or_gate_change"
    elif sample_gap_count or tail_watch_count:
        status = "NO_READY_CANDIDATE_COLLECT_MORE_EVIDENCE"
        next_trigger = "continue_collecting_cost_gate_reject_counterfactuals"
    else:
        status = "NO_PROFIT_LEARNING_CANDIDATE"
        next_trigger = "keep_cost_gate_and_continue_research"

    return {
        "schema_version": "cost_gate_profit_opportunity_ranking_v1",
        "status": status,
        "next_trigger": next_trigger,
        "candidate_count": candidate_count,
        "data_blocker_count": data_blocker_count,
        "confirmed_block_count": int(action_counts.get("BLOCK_CONFIRMED") or 0),
        "sample_gap_count": sample_gap_count,
        "tail_watch_count": tail_watch_count,
        "scoring": {
            "sample_score": "min(log10(n+1)/4,1)*25",
            "avg_net_score": "clamp((avg_net_bps-min_probe_avg_net_bps)/100,0,1)*25",
            "median_margin_score": "clamp((p50_gross_bps-friction_bps)/50,0,1)*25",
            "hit_rate_score": "clamp((net_positive_pct-50)/50,0,1)*25",
        },
        "top_side_cells": ranked_rows[:20],
        "boundary": {
            "order_authority": "NOT_GRANTED",
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
            "runtime_mutation": "NONE",
        },
    }


def build_learning_lane_scorecard(
    cfg: AuditConfig,
    coverage: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    annotated = annotate_learning_lane_rows(cfg, rows)
    action_counts: dict[str, int] = {}
    for row in annotated:
        action = str(row["learning_lane_action"])
        action_counts[action] = action_counts.get(action, 0) + 1

    def ranked(source: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            source,
            key=lambda item: (
                _as_float(item.get("avg_net_bps")) or float("-inf"),
                int(item.get("n") or 0),
            ),
            reverse=True,
        )

    probe_candidates = ranked(
        [row for row in annotated if row["learning_lane_action"] == "LEARNING_PROBE_CANDIDATE"]
    )
    block_confirmed = ranked(
        [row for row in annotated if row["learning_lane_action"] == "BLOCK_CONFIRMED"]
    )
    features = int(coverage.get("decision_features") or 0)
    outcomes = int(coverage.get("features_joined_outcomes") or 0)
    contexts = int(coverage.get("features_joined_contexts") or 0)
    context_coverage_pct = (contexts / features * 100.0) if features else 0.0
    outcome_path_status = (
        "OUTCOME_PATH_STALLED_FOR_FEATURE_REJECTS"
        if features > 0 and outcomes == 0
        else "OUTCOME_PATH_HAS_REJECT_COVERAGE_OR_NO_FEATURES"
    )
    status = (
        "LEARNING_LANE_PROBE_CANDIDATES_PRESENT"
        if probe_candidates
        else "NO_LEARNING_LANE_PROBE_CANDIDATES"
    )
    profit_opportunity_ranking = build_profit_opportunity_ranking(
        cfg,
        annotated,
        action_counts,
    )
    return {
        "schema_version": "cost_gate_reject_counterfactual_v2",
        "status": status,
        "outcome_path_status": outcome_path_status,
        "action_counts": action_counts,
        "context_coverage_pct": round(context_coverage_pct, 4),
        "thresholds": {
            "min_probe_sample": cfg.min_probe_sample,
            "min_probe_avg_net_bps": cfg.min_probe_avg_net_bps,
            "min_probe_net_positive_pct": cfg.min_probe_net_positive_pct,
            "max_block_net_positive_pct": cfg.max_block_net_positive_pct,
            "friction_bps": cfg.friction_bps,
        },
        "probe_candidates": probe_candidates[:20],
        "block_confirmed": block_confirmed[:20],
        "profit_opportunity_ranking": profit_opportunity_ranking,
        "rows": annotated,
    }


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def build_json_payload(
    cfg: AuditConfig,
    coverage: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    generated: str | None = None,
) -> dict[str, Any]:
    generated = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    scorecard = build_learning_lane_scorecard(cfg, coverage, rows)
    return {
        "generated_at_utc": generated,
        "engine_modes": list(cfg.engine_modes),
        "lookback_hours": cfg.lookback_hours,
        "horizon_minutes": cfg.horizon_minutes,
        "limit": cfg.limit,
        "friction_bps": cfg.friction_bps,
        "filters": {
            "strategy": cfg.strategy,
            "symbol": cfg.symbol,
            "side": cfg.side,
        },
        "boundary": "read-only PG SELECT; no order/config/risk/auth/runtime mutation",
        "coverage": coverage,
        "learning_lane_scorecard": scorecard,
    }


def render_markdown(
    cfg: AuditConfig,
    coverage: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    generated: str | None = None,
) -> str:
    generated = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    scorecard = build_learning_lane_scorecard(cfg, coverage, rows)
    lines = [
        "# Cost Gate Reject Counterfactual Audit",
        "",
        f"- Generated: `{generated}`",
        f"- Engine modes: `{','.join(cfg.engine_modes)}`",
        f"- Lookback: `{cfg.lookback_hours}` hours",
        f"- Horizon: `{cfg.horizon_minutes}` minutes",
        f"- Friction: `{cfg.friction_bps:.2f}` bps",
        f"- Limit: `{cfg.limit}` latest rejected feature rows before grouping",
        "- Boundary: read-only PG SELECT; no order, config, risk, auth, or runtime mutation.",
        "- Interpretation: kline counterfactual uses future market close, not actual queue fill.",
        "",
        "## Coverage",
        "",
        "| metric | value |",
        "|---|---:|",
    ]
    for key in [
        "risk_verdicts",
        "latest_risk_verdict_ts",
        "risk_verdicts_joined_intents",
        "decision_features",
        "features_joined_contexts",
        "features_joined_outcomes",
        "decision_context_old_pending",
    ]:
        lines.append(f"| {key} | {_fmt(coverage.get(key))} |")

    lines.extend(
        [
            "",
            "## Learning Lane Scorecard",
            "",
            f"- Status: `{scorecard['status']}`",
            f"- Outcome path: `{scorecard['outcome_path_status']}`",
            f"- Context coverage: `{scorecard['context_coverage_pct']:.4f}%`",
            "",
            "| action | count |",
            "|---|---:|",
        ]
    )
    for action, count in sorted(scorecard["action_counts"].items()):
        lines.append(f"| {action} | {count} |")
    ranking = scorecard["profit_opportunity_ranking"]
    lines.extend(
        [
            "",
            "### Profit Opportunity Ranking",
            "",
            f"- Status: `{ranking['status']}`",
            f"- Next trigger: `{ranking['next_trigger']}`",
            "- Boundary: ranking only; `order_authority=NOT_GRANTED`, `main_cost_gate_adjustment=NONE`.",
            "",
            "| rank | side_cell | action | tier | score | n | avg_net | p50 | net+% | next_action |",
            "|---:|---|---|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for idx, row in enumerate(ranking["top_side_cells"][:10], start=1):
        lines.append(
            "| "
            f"{idx} | {row['side_cell_key']} | {row['learning_lane_action']} | "
            f"{row['priority_tier']} | {_fmt(row['priority_score'])} | {row['n']} | "
            f"{_fmt(row['avg_net_bps'])} | {_fmt(row['p50_gross_bps'])} | "
            f"{_fmt(row['net_positive_pct'])} | {row['next_action']} |"
        )
    lines.extend(
        [
            "",
            "### Probe Candidates",
            "",
            "| strategy | symbol | side | n | avg_net | p50 | net+% | reason |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in scorecard["probe_candidates"][:10]:
        lines.append(
            "| "
            f"{row['strategy_name']} | {row['symbol']} | {row['side']} | "
            f"{row['n']} | {_fmt(row['avg_net_bps'])} | {_fmt(row['p50_gross_bps'])} | "
            f"{_fmt(row['net_positive_pct'])} | {row['learning_lane_reason']} |"
        )

    lines.extend(
        [
            "",
            "## Counterfactual",
            "",
            "| strategy | symbol | side | action | reason | n | ctx | avg_gross | p50 | p90 | avg_net | gross+% | net+% | max_ts |",
            "|---|---:|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in scorecard["rows"]:
        lines.append(
            "| "
            f"{row['strategy_name']} | {row['symbol']} | {row['side']} | "
            f"{row['learning_lane_action']} | "
            f"{row['reject_reason_code']} | {row['n']} | {row['joined_contexts']} | "
            f"{_fmt(row['avg_gross_bps'])} | {_fmt(row['p50_gross_bps'])} | "
            f"{_fmt(row['p90_gross_bps'])} | {_fmt(row['avg_net_bps'])} | "
            f"{_fmt(row['gross_positive_pct'])} | {_fmt(row['net_positive_pct'])} | "
            f"{_fmt(row['max_ts'])} |"
        )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-mode", action="append", default=["demo", "live_demo"])
    parser.add_argument("--lookback-hours", type=int, default=168)
    parser.add_argument("--horizon-minutes", type=int, default=60)
    parser.add_argument("--limit", type=int, default=50_000)
    parser.add_argument("--friction-bps", type=float, default=4.0)
    parser.add_argument("--strategy")
    parser.add_argument("--symbol")
    parser.add_argument("--side")
    parser.add_argument("--min-probe-sample", type=int, default=100)
    parser.add_argument("--min-probe-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--min-probe-net-positive-pct", type=float, default=55.0)
    parser.add_argument("--max-block-net-positive-pct", type=float, default=40.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cfg = AuditConfig(
        engine_modes=tuple(args.engine_mode),
        lookback_hours=args.lookback_hours,
        horizon_minutes=args.horizon_minutes,
        limit=args.limit,
        friction_bps=args.friction_bps,
        strategy=args.strategy,
        symbol=args.symbol,
        side=side_to_int(args.side),
        min_probe_sample=args.min_probe_sample,
        min_probe_avg_net_bps=args.min_probe_avg_net_bps,
        min_probe_net_positive_pct=args.min_probe_net_positive_pct,
        max_block_net_positive_pct=args.max_block_net_positive_pct,
    )
    validate_config(cfg)
    conn = connect_report_pg(
        "cost_gate_reject_counterfactual",
        statement_timeout_ms_default=180_000,
    )
    try:
        # connect_report_pg sets statement_timeout with a normal SET, which
        # opens a psycopg2 transaction. End that setup transaction before
        # switching the session into read-only autocommit mode.
        conn.rollback()
        conn.set_session(readonly=True, autocommit=True)
        coverage = fetch_coverage(conn, cfg)
        rows = fetch_counterfactual_rows(conn, cfg)
    finally:
        conn.close()
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = render_markdown(cfg, coverage, rows, generated=generated)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    if args.json_output:
        payload = build_json_payload(cfg, coverage, rows, generated=generated)
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

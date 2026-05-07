# MAG-070 AnalystInsight L1/L2/L3 Schema

Date: 2026-05-07
Status: implemented as Python contract schema

## Purpose

MAG-070 defines the typed AnalystInsight schema boundary for the Analyst
Learning Loop. This task does not wire runtime Analyst emission, proposal
approval, cloud calls, or Strategist/Guardian consumption changes.

## Common Fields

All AnalystInsight rows use `agent_spine.analyst_insight.v1` and carry:

- `analyst_tier`: one of `l1`, `l2`, `l3`.
- `insight_type`: tier-specific insight category.
- `insight_level`: one of `fact`, `inference`, `hypothesis`.
- `evidence_refs`: object IDs, fill IDs, report IDs, or prior insight IDs.
- `claims`: typed claim dictionaries for downstream Strategist/Guardian use.
- `confidence`: optional bounded score from `0.0` to `1.0`.
- `recommendation`: optional non-authoritative recommendation text.
- `severity`: optional `info`, `low`, `medium`, `high`, or `critical`.

## Tier Boundaries

### L1

Purpose: post-trade and execution-quality review.

Allowed `insight_type` values:

- `post_trade_review`
- `execution_quality`
- `strategy_metric`

### L2

Purpose: pattern discovery over round trips, strategy performance, risk, regime,
or cost behavior.

Allowed `insight_type` values:

- `strategy_pattern`
- `risk_pattern`
- `regime_pattern`
- `cost_pattern`

### L3

Purpose: hypothesis and experiment lifecycle evidence.

Allowed `insight_type` values:

- `hypothesis`
- `experiment_design`
- `experiment_result`

## Authority Boundary

AnalystInsight is evidence only. It can feed later Strategist weighting or
Guardian risk-pattern consumption, but it does not choose symbol/direction,
modify Guardian verdict authority, submit orders, or acquire/release leases.

# Operator Note: Profitability Path Scorecard Alpha-Cron Ingestion

Date: 2026-06-23

## What Changed

The alpha discovery cron now refreshes a canonical profitability path scorecard before each killboard run:

- `/tmp/openclaw/alpha_discovery_throughput/profitability_path_scorecard_latest.json`
- `/tmp/openclaw/alpha_discovery_throughput/profitability_path_scorecard_latest.md`

The killboard mirrors the scorecard's closure status, leading path, leading candidate, remaining proof gates, and no-authority answers.

## Current Runtime Read

Latest canonical smoke:

- Scorecard status: `PROFITABILITY_PATHS_PRESENT_BUT_EXECUTION_EVIDENCE_MISSING`
- Closure: `COST_GATE_ESCAPE_PREFLIGHT_BLOCKED_BY_OPERATOR_REVIEW`
- Leading path: `horizon_edge_amplification:ma_crossover|BTCUSDT|Sell`
- Leading candidate: `ma_crossover|BTCUSDT|Sell`
- Remaining proof gate count: `1`
- Current gate: operator sealed-horizon review without granting order/probe authority

The scorecard says the system has cost-gate-crossing candidates, but does not yet have execution evidence.

## Boundary

This is artifact-only. It does not:

- lower the global Cost Gate
- grant order authority
- grant probe authority
- submit or cancel orders
- mutate env/auth/risk/order/strategy/runtime state
- prove promotion readiness

## Next Operator Gate

The next human/operator gate remains sealed-horizon review. Only after that should the system move toward a separately authorized, bounded, side-cell-specific Demo probe, followed by candidate-matched fill/fee/slippage evidence, matched blocked controls, and execution-realism review.

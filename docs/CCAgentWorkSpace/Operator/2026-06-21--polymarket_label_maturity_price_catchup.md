# Polymarket label maturity / price catch-up routing

Date: 2026-06-21

## Operator read

Polymarket alpha discovery still has no tradable signal. The improvement is diagnostic: the killboard now explains why lead-lag has zero joined IC rows.

Current state:

- Alpha scorecard: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`.
- Polymarket primary blocker: `price_data_not_caught_up_to_label_target`.
- Snapshot rows: `3555`.
- Feature points: `39`.
- Joined rows: `0`.
- Latest Polymarket feature: `2026-06-20T22:07:01.434000+00:00`.
- Latest PG 1m price bars for tracked symbols: `2026-06-20T22:06:00+00:00`.

## Action

No operator action, no strategy change, no probe, no order.

Let price data catch up, then rerun Polymarket lead-lag and alpha discovery. Only escalate if normal replay/history/execution-realism gates later produce durable evidence.

## Boundary

Artifact-only research routing. No PG write, Bybit private/signed/trading call, engine/API rebuild/restart, credential/auth/risk/order mutation, or promotion proof.

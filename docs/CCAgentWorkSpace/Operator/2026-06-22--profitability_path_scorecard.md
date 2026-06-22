# Profitability Path Scorecard

Date: 2026-06-22

## Summary

I added a reusable scorecard for the question "how can we become profitable?" It ranks paths instead of repeating manual audits:

- bounded Cost Gate demo-learning candidates
- horizon retiming / side-cell filters
- low-friction MM alpha search
- fee / rebate / scale path
- Polymarket lead-lag
- Gate-B listing-fade event wait

It also fixes the SQL bug that made the demo data-flow monitor fail on psycopg literal `%` patterns.

## Key Point

The recommended direction is not global Cost Gate lowering. The scorecard keeps that false and instead requires proof through data-flow, ledger/outcome accumulation, bounded demo probe review, and execution realism.

## Verified

- py_compile passed
- focused SQL/scorecard tests = `20 passed`
- broader related tests = `73 passed`
- `git diff --check` passed

## Boundary

No Cost Gate lowering, no probe/order authority, no PG write, no Bybit call, no deploy/restart, and no promotion proof.

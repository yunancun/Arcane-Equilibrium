# 2026-06-21 -- Cost gate reject counterfactual learning loop

## Decision

Demo should not be treated as a small live account whose goal is simply to avoid orders. Its purpose is autonomous learning: generate bounded, labeled evidence that can improve edge estimates and strategy selection.

The current cost-gate path was inspected because demo had not placed new orders for a long time. The key finding is that cost-gate rejections are partially recorded, but the learning loop is incomplete:

- `trading.risk_verdicts` and `learning.decision_features` receive cost-gate rejects.
- `trading.intents` does not receive exchange cost-gate rejects.
- `trading.decision_context_snapshots` coverage is sparse for those rejects.
- `trading.decision_outcomes` is not usable for recent rejects because the backfill backlog is large.

To make this measurable, this pass added `helper_scripts/db/audit/cost_gate_reject_counterfactual.py`, a read-only audit that computes post-rejection market outcomes directly from `learning.decision_features` and future `market.klines`, without relying on the lagged `decision_outcomes` table.

## Runtime Evidence

Generated artifact:

- path: `/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.md`
- sha256: `9acc5a3c54bd77c644d0a8d9ce2aeab3cd36a7b6075c1a8212122130a69bcac0`
- generated: `2026-06-21T10:16:11+00:00`
- scope: demo/live_demo, 168h lookback, 60m horizon, 50,000 latest rejected feature rows, 4bp friction

Coverage:

- cost-gate risk verdicts: `182,058`
- latest risk verdict: `2026-06-21 11:48:59.990000+02:00`
- risk verdicts joined to intents: `0`
- decision features: `182,058`
- features joined to decision contexts: `353`
- features joined to decision outcomes: `0`
- old decision-context pending backlog: `6,826,552`

Selected 60m counterfactual rows:

- `ma_crossover BTCUSDT Buy`: n=`24,437`, avg gross `-31.7434bp`, p50 `-29.6769bp`, net-positive after 4bp `0.00%`.
- `ma_crossover ETHUSDT Sell`: n=`13,487`, avg gross `101.9788bp`, p50 `17.9914bp`, net-positive after 4bp `86.01%`.
- `ma_crossover NEARUSDT Sell`: n=`2,125`, avg gross `20.2197bp`, p50 `21.5106bp`, net-positive after 4bp `99.95%`.

## PM Read

This is not a case for globally lowering the main cost gate. The BTC Buy rejects are correctly blocked by the 60m market counterfactual. But it is also not acceptable to let demo become inert: ETH/NEAR Sell examples show side-specific blocked signals can contain learnable right-tail or regime evidence.

The correct design direction is:

- Main gate protects normal trading budget.
- Demo-learning gate allocates small, explicit exploration budget by side cell.
- Every blocked and explored signal must produce durable feature + market outcome evidence.
- Edge estimates should be updated from actual post-signal outcomes, not just realized fills.

In short: guardrail plus learning flywheel, not guardrail plus stagnation.

## Verification

- Mac: `python3 -m pytest -q helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py` -> `4 passed`
- Mac: `python3 -m py_compile helper_scripts/db/audit/cost_gate_reject_counterfactual.py`
- Linux: same test -> `4 passed`
- Linux: same py_compile passed
- Linux: read-only report generation passed with PG `default_transaction_read_only=on`

## Boundary

Read-only audit/source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact write. No PG table write or schema migration. No Bybit private/signed/trading call. No engine/API rebuild or restart. No credential, auth, risk, order, strategy, or runtime config mutation. This is learning-loop evidence, not permission to trade.

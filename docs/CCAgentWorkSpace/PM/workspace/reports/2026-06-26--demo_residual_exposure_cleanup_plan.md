# Demo Residual Exposure Cleanup / Reconciler Plan

Timestamp: 2026-06-26T01:46Z

## Blocker

`P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-PLAN-E3-BB-REVIEW`

## Decision

`DONE_WITH_CONCERNS`.

The residual exposure checkpoint is classified, but not cleaned. Candidate
selection remains blocked. The next action must be a separate E3/BB-reviewed
exchange cleanup action plan; this report grants no cancel/modify/close/order
authority.

## Session State

- `/tmp/openclaw/session_loop_state_20260626T013402Z_demo_residual_exposure_cleanup_plan.json`
- `/tmp/openclaw/session_loop_state_packet_20260626T013402Z_demo_residual_exposure_cleanup_plan.json`
- Anti-repeat decision: `new_evidence_delta_allows_active_blocker_progress`

## Review Chain

E3: `DONE_WITH_CONCERNS`.

- Allowed exactly one fresh demo private GET-only inventory because the
  2026-06-26T01:34Z PG delta made the prior 01:17Z exchange snapshot stale.
- Allowed source/read-only cleanup/reconciler plan/report.
- Hard stops: POST, create/cancel/modify/close order, clean restart/flatten,
  PG write, source sync, service restart, crontab/env mutation, adapter/Rust
  writer, Cost Gate change, authority grant, proof claim.

BB: `DONE_WITH_CONCERNS`.

- Completed one fresh demo private read-only inventory during review.
- Artifact on `trade-core`:
  `/tmp/openclaw/audit/bybit_demo_exchange_inventory_bb_review/20260626T014016Z_bb_inventory.json`
- Endpoints used:
  - `GET /v5/order/realtime`, `category=linear`, `settleCoin=USDT`,
    `openOnly=0`, `limit=50`, cursor loop
  - `GET /v5/position/list`, `category=linear`, `settleCoin=USDT`,
    `limit=200`, cursor loop
- No POST, order history, cancel/modify/close, PG write, runtime source sync,
  restart, Cost Gate/probe/order/live authority.

## Fresh Evidence

Bybit demo open orders:

| Class | Count | Symbols | Interpretation |
|---|---:|---|---|
| linked New PostOnly limit entries | 2 | `ETCUSDT`, `INJUSDT` | Current active maker entry exposure. These are not cleanup/protective orders. |
| unlinked reduce-only conditional StopLoss orders | 3 | `NEARUSDT`, `FILUSDT`, `ICPUSDT` | Position-protection stops for existing residual positions. Do not cancel alone while positions remain. |

Bybit demo positions:

| Symbol | Side | Size | Position value | Unrealised PnL | Matching protective order |
|---|---|---:|---:|---:|---|
| `NEARUSDT` | Buy | `0.1` | `0.18301` | `-0.00246` | Sell reduce-only StopLoss |
| `ICPUSDT` | Buy | `45.3` | `100.2942` | `-3.2163` | Sell reduce-only StopLoss |
| `FILUSDT` | Sell | `481.6` | `334.66384` | `-14.39984` | Buy reduce-only StopLoss |

Aggregate:

- open orders: `5`
- estimated open notional: `486.24260000 USDT`
- nonzero positions: `3`
- position value: `435.14105000 USDT`
- unrealised PnL: `-17.61860000 USDT`
- unlinked conditionals match nonzero position symbols: `true`

Read-only PG:

- 2026-06-26T01:34Z: 72h demo fills `82`; missing order/context/strategy
  attribution all `0`.
- 24h effective Working using latest `trading.order_state_changes`: exactly
  the 2 linked maker entry orders:
  - `oc_dm_1782437036355_109` `INJUSDT` Buy Limit PostOnly
  - `oc_dm_1782438000052_112` `ETCUSDT` Buy Limit PostOnly

Healthcheck [68]:

- Still `FAIL`.
- demo `working_n=2`
- resting about `487 USDT` (`L487/S0`)
- filled exposure in local snapshot: `0`
- divergence critical.

## Classification

1. Current exchange exposure is not a stale deep-open-order overhang.
   The active entry side is two linked maker orders on `ETCUSDT` and `INJUSDT`.

2. The three unlinked orders are protective StopLoss conditionals for three
   residual positions. They should be treated as position-protection orders,
   not candidate-matched entries, and not profitability evidence.

3. Canceling protective conditionals alone would remove downside protection
   while leaving positions open. Any cleanup action must sequence position
   close/replacement-protection/cancel logic explicitly.

4. Healthcheck [68] remains correctly blocking candidate selection. It now
   flags current maker entry resting exposure against zero filled exposure in
   the local snapshot; it does not prove clean exchange state.

5. Fill attribution is clean in the 72h window. The current blocker is residual
   exposure and reconciler state, not unattributed fills.

## Max Safe Next Action

Open a separate runtime/exchange checkpoint:

`P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW`

Required review content:

- Exact exchange/action envelope for a demo-only cleanup.
- Position-aware sequence for:
  - the 2 linked maker entry orders (`ETCUSDT`, `INJUSDT`)
  - the 3 residual positions (`NEARUSDT`, `ICPUSDT`, `FILUSDT`)
  - their 3 protective reduce-only StopLoss orders
- Preconditions:
  - fresh demo private GET inventory immediately before action
  - fail closed on non-demo base URL, missing creds, retCode != 0, timeout, or
    cursor/malformed response
  - no live/mainnet
  - no global Cost Gate change
  - no probe/order/live promotion authority
- Postconditions:
  - fresh read-only Bybit inventory proves zero unwanted open orders/positions,
    or explicitly documents accepted residual protection
  - healthcheck [68] re-run and recorded
  - PG/fill attribution rechecked

Forbidden until that separate review:

- Canceling the 3 protective conditionals alone
- Closing positions without explicit stop/cancel sequencing
- Restart/flatten scripts
- PG writes/backfills
- Runtime source sync/restart
- Adapter/Rust writer enablement
- Candidate selection or bounded probe authorization

## Proof Exclusions

- Fresh inventory and cleanup planning are risk/exchange-truth evidence only.
- The `ETCUSDT`/`INJUSDT` maker entries are not bounded-probe proof.
- The `NEARUSDT`/`ICPUSDT`/`FILUSDT` protective stops and positions are not
  profitability proof.
- No `flash_dip_buy`, risk-close, cleanup, or unattributed fill may count
  toward Cost Gate proof, bounded-probe proof, promotion, or risk-adjusted net
  PnL.

## Aggressive Profit Hypotheses

1. Clean-book unlock for exactly one bounded Demo candidate
   - Why it might make money: removing residual exposure and stale resting
     ambiguity lets candidate selection use clean candidate-matched controls.
   - Fastest safe test: execute reviewed demo cleanup, then select one
     false-negative / MM / sealed-horizon candidate.
   - Required data: post-clean Bybit inventory, healthcheck [68], candidate
     scorecard, fee/slippage model.
   - Failure condition: positions or unlinked protective orders remain
     unexplained.
   - Authority required: separate E3/BB exchange cleanup review first.
   - Max safe next action: cleanup action review, no mutation in this report.
   - Scores: upside `5/5`, evidence `4/5`, execution realism `3/5`, cost `3/5`,
     time `3/5`, account risk `3/5`, governance risk `1/5`, autonomy `5/5`.

2. Protective-stop-aware reconciler hygiene
   - Why it might make money: separating protective stops from entry exposure
     prevents false blocks and avoids removing protection while positions are
     open.
   - Fastest safe test: after cleanup, add/verify a source-only classifier that
     distinguishes entry maker orders from reduce-only position protection.
   - Required data: Bybit order rows, position rows, PG state changes.
   - Failure condition: classifier cannot reconstruct order/position pairing.
   - Authority required: source/test review only for classifier; E3/BB for any
     runtime/exchange adoption.
   - Max safe next action: cleanup action review before source adoption.
   - Scores: upside `3/5`, evidence `5/5`, execution realism `4/5`, cost `4/5`,
     time `4/5`, account risk `2/5`, governance risk `1/5`, autonomy `5/5`.

3. Maker-ratio candidate after entry-order cleanup
   - Why it might make money: current linked PostOnly entry orders show maker
     placement works; a clean book allows a fee-aware maker candidate to be
     tested without exposure contamination.
   - Fastest safe test: post-clean candidate packet with maker ratio and
     adverse-selection controls.
   - Required data: clean exchange inventory, BBO freshness, matched fills,
     maker/taker fee assumptions.
   - Failure condition: maker entries fill without candidate attribution or
     controls.
   - Authority required: bounded Demo review only after P0 evidence quality.
   - Max safe next action: keep candidate selection blocked.
   - Scores: upside `4/5`, evidence `3/5`, execution realism `3/5`, cost `4/5`,
     time `2/5`, account risk `2/5`, governance risk `1/5`, autonomy `4/5`.

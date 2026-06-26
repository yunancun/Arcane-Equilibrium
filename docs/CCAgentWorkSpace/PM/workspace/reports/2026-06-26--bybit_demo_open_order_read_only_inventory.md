# Bybit Demo Open-Order Read-Only Inventory

Timestamp: 2026-06-26T01:18Z

## Blocker

`P0-PROFIT-EVIDENCE-QUALITY-BYBIT-DEMO-OPEN-ORDER-READ-ONLY-INVENTORY-E3-BB-REVIEW`

## Decision

`DONE_WITH_CONCERNS`.

Bybit demo exchange-truth inventory was completed with cursor-aware private
GET-only reads. No order/cancel/modify/close action was taken. No PG write,
runtime source sync, service restart, crontab/env mutation, adapter/Rust writer
enablement, Cost Gate change, probe/order/live authority, or promotion proof
occurred.

This closes the read-only inventory checkpoint only. It does not authorize
candidate selection or bounded probe execution because demo still has residual
exchange exposure and healthcheck [68] is still FAIL.

## Session State

- `/tmp/openclaw/session_loop_state_20260626T010537Z_bybit_demo_open_order_read_only_inventory.json`
- `/tmp/openclaw/session_loop_state_packet_20260626T010537Z_bybit_demo_open_order_read_only_inventory.json`
- Anti-repeat decision: `new_evidence_delta_allows_active_blocker_progress`

## E3 / BB Review

E3: `DONE_WITH_CONCERNS`.

- Allowed exactly bounded read-only evidence collection.
- Forbidden: POST, place/cancel/modify/close order, clean restart flattening,
  PG write, restart/rebuild, env/crontab mutation, adapter/Rust writer,
  Cost Gate change, authority grant, and proof claim.

BB: `DONE_WITH_CONCERNS`.

- One-call `/v5/order/realtime` was not enough.
- Required cursor-aware `GET /v5/order/realtime` with `category=linear`,
  `settleCoin=USDT`, `openOnly=0`, `limit=50`, and `nextPageCursor` loop.
- Required cursor-aware `/v5/position/list` with `category=linear`,
  `settleCoin=USDT`, `limit=200`, and cursor loop.
- Stop if cleanup is needed; cleanup/cancel/modify needs a separate E3/BB plan.

## Source Change

Added source-controlled full-scan support so future inventory does not rely on
ad hoc paging code:

- `BybitClient.get_active_orders_full_scan(...)`
- `BybitClient.get_positions_full_scan(...)`
- shared fail-closed pagination helper for malformed result, non-list rows,
  missing/malformed `list` or `nextPageCursor`, non-object rows,
  repeated/non-advancing cursor, and page-cap overflow
- `helper_scripts/bybit/demo_exchange_inventory_readonly.py`
- local Bybit reference update for `/v5/order/realtime` full-scan
  `settleCoin/openOnly/limit/cursor` and strict cursor fail-closed semantics

Backward compatibility note: existing `get_active_orders()` and
`get_positions()` behavior was left unchanged.

Verification:

- `PYTHONPATH=program_code/exchange_connectors/bybit_connector/control_api_v1 python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_bybit_rest_client.py -q`
  - `61 passed`
- `PYTHONPATH=helper_scripts/bybit python3 -m pytest helper_scripts/bybit/test_demo_exchange_inventory_readonly.py -q`
  - `5 passed`
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py helper_scripts/bybit/demo_exchange_inventory_readonly.py`
- `python3 helper_scripts/bybit/demo_exchange_inventory_readonly.py --help`
- `git diff --check`

E4 review findings addressed:

- P1 false-clean risk from `result=None` / missing `list` /
  malformed `nextPageCursor` fixed with strict fail-closed parsing and
  regression coverage.
- E2 medium false-clean risk from non-object `result.list` rows fixed with
  strict fail-closed parsing and regression coverage.
- E2 low conditional summary overcount fixed so `UNKNOWN` / `0.00` normal
  orders do not count as conditional; `Untriggered`, meaningful
  `stopOrderType`, or nonzero trigger price still do.
- CLI demo-only/base-URL/failure/success-helper-call boundaries covered by
  new fake-client tests.
- Local Bybit reference SSOT updated to match the current official Bybit V5
  open-order and position pagination contracts.

## Runtime / Exchange Evidence

Local Mac had no demo private credentials, so the reviewed GET-only inventory
was executed on `trade-core` without syncing runtime source and without writing
repo files. Output artifact:

- JSON: `/tmp/openclaw/audit/bybit_demo_exchange_inventory/20260626T011756Z_inventory.json`
- Markdown: `/tmp/openclaw/audit/bybit_demo_exchange_inventory/20260626T011756Z_inventory.md`

Bybit demo exchange open orders:

- Total: `5`
- Estimated open notional: `400.97259600 USDT`
- Status counts: `New=2`, `Untriggered=3`
- Type counts: `Limit=2`, `Market=3`
- Symbols: `ARBUSDT`, `FILUSDT`, `ICPUSDT`, `LINKUSDT`, `NEARUSDT`
- Two linked OpenClaw PostOnly limit orders:
  - `LINKUSDT` Buy Limit, orderLinkId `oc_dm_1782435475929_100`
  - `ARBUSDT` Buy Limit, orderLinkId `oc_dm_1782436030189_103`
- Three unlinked exchange reduce-only conditional market orders with empty
  orderLinkId:
  - `NEARUSDT` Sell Market reduce-only, qty `0.1`
  - `FILUSDT` Buy Market reduce-only, qty `481.6`
  - `ICPUSDT` Sell Market reduce-only, qty `45.3`

Bybit demo positions:

- Nonzero positions: `3`
- Symbols: `FILUSDT`, `ICPUSDT`, `NEARUSDT`
- Position value: `435.14105000 USDT`
- Unrealised PnL: `-21.44009000 USDT`

## PG / Healthcheck Reconciliation

Important SQL distinction:

- `trading.orders.status='Working'` alone is stale and overcounts.
- Effective order state must use `trading.order_state_changes` latest
  `to_status` when present.

Read-only PG evidence:

- 72h demo fills: `79`
- Missing order attribution: `0`
- Missing context attribution: `0`
- Missing strategy attribution: `0`
- Therefore unattributed fills remain proof-excluded, but they are not the
  current root cause.

72h effective working view:

| Classification | Count | Notional |
|---|---:|---:|
| exchange-open linked | 2 | `400.959000` |
| effective Working `flash_dip_buy` not exchange-open | 27 | `6781.290000` |
| effective Working `risk_close` not exchange-open | 2 | `0.000000` |

24h effective working view:

| Classification | Count | Notional |
|---|---:|---:|
| exchange-open linked | 2 | `400.959000` |
| effective Working `risk_close` not exchange-open | 2 | `0.000000` |

Passive healthcheck [68] after exchange inventory:

- `FAIL`
- demo `working_n=5`
- resting about `408 USDT` (`L401/S7`)
- divergence critical

Interpretation:

- The prior large PG `Working` overhang is mostly stale local state, not live
  exchange open-order exposure.
- Exchange truth still has 5 open orders: 2 linked PostOnly maker orders and 3
  unlinked reduce-only conditional orders tied to residual positions.
- Candidate selection should remain blocked until a separate exposure /
  cleanup / reconciler plan decides how to handle the unlinked reduce-only
  orders and nonzero positions.

## Proof Exclusions

- This inventory is exchange-truth / risk evidence only.
- It is not Cost Gate proof, bounded-probe proof, promotion evidence, or
  risk-adjusted net PnL evidence.
- `flash_dip_buy` rows/fills and cleanup/risk-close rows remain ineligible for
  bounded Cost Gate proof.
- Unattributed fills must never count toward proof; current 72h unattributed
  fill counts are zero.

## Aggressive Profit Hypotheses

1. Candidate-scoped maker re-entry after exposure cleanup
   - Why it might make money: the two current linked PostOnly orders show the
     active path can still place maker liquidity without broad exchange
     overhang.
   - Fastest safe test: after exposure cleanup plan, run candidate selection
     only from clean attributed fills and current-fee false-negative candidates.
   - Required data: clean exchange inventory, candidate-matched fills, BBO
     freshness, fee/slippage model.
   - Failure condition: any unlinked exchange exposure remains or healthcheck
     [68] stays FAIL.
   - Authority required: research/proposal only now; later E3/BB/operator for
     bounded demo.
   - Max safe next action: separate read-only cleanup/reconciler plan.
   - Scores: upside `4/5`, evidence `2/5`, execution realism `3/5`, cost `3/5`,
     time `3/5`, account risk `3/5`, governance risk `1/5`, autonomy `4/5`.

2. Reduce-only conditional order hygiene as profit enabler
   - Why it might make money: removing residual exposure ambiguity prevents
     false risk blocks and frees the system to select high-upside candidates.
   - Fastest safe test: classify the three unlinked reduce-only orders against
     positions/fills and design a no-surprise close/cancel policy for review.
   - Required data: Bybit order details, position rows, recent fills and state
     changes.
   - Failure condition: cannot reconstruct origin/intent for the unlinked
     reduce-only orders.
   - Authority required: E3/BB for any cancel/modify/close; none granted here.
   - Max safe next action: source/read-only reconciliation packet.
   - Scores: upside `3/5`, evidence `4/5`, execution realism `4/5`, cost `4/5`,
     time `4/5`, account risk `2/5`, governance risk `1/5`, autonomy `5/5`.

3. Regime-specific false-negative subset after clean book
   - Why it might make money: broad strategies may be structurally sub-fee,
     while narrow false-negative regimes can still clear fees after slippage.
   - Fastest safe test: choose exactly one candidate from false-negative /
     sealed-horizon / current-fee MM evidence after exchange exposure is clean.
   - Required data: clean inventory, candidate scorecard, matched controls, fee
     and maker-ratio assumptions.
   - Failure condition: candidate cannot produce candidate-matched fills or
     execution-realism controls.
   - Authority required: operator review for bounded demo design only.
   - Max safe next action: no-order candidate packet after cleanup blocker.
   - Scores: upside `5/5`, evidence `3/5`, execution realism `2/5`, cost `3/5`,
     time `2/5`, account risk `2/5`, governance risk `1/5`, autonomy `5/5`.

## Next Blocker

`P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-PLAN-E3-BB-REVIEW`

Goal: produce a separate reviewed plan for the 3 unlinked reduce-only
conditional orders and 3 nonzero positions. The next checkpoint may be
source/read-only reconciliation only. Any cancel/modify/close/order-affecting
action remains outside this report and requires its own E3/BB runtime/exchange
plan.

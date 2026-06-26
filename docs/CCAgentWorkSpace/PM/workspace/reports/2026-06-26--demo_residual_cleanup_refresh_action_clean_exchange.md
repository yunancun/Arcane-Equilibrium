# Demo Residual Cleanup Refresh Action - Clean Exchange Book

Timestamp: 2026-06-26T03:18Z

## Blocker

`P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB`

## Decision

`DONE_WITH_CONCERNS`.

The refreshed cleanup envelope completed successfully through the reviewed
control-plane route. Independent post-action Bybit demo full-scan inventory
shows no open orders and no nonzero positions.

Concern: passive healthcheck [68] still fails from local
`trading.order_state_changes` stale `Working` rows even though exchange truth is
clean. Those local rows, plus cleanup/risk-close/unattributed fills, remain
proof-excluded.

## Session State

- `/tmp/openclaw/session_loop_state_20260626T030115Z_demo_residual_cleanup_refresh.json`
- Anti-repeat decision: `PROCEED_NEW_EVIDENCE_DELTA`
- Evidence delta:
  - runtime-local auth proof succeeded in the prior blocker
  - 72h demo fills changed to `101` before action and `106` after action
  - health [68] still showed demo exposure divergence before action
  - runtime lacked the v535 inventory helper, so E3/BB approved a one-time inline
    GET-only full-scan inventory path

## Review Chain

E3 verdict: `DONE_WITH_CONCERNS`.

- Rejected the original helper-based envelope because the inventory helper was
  not present on runtime `d2cd70d0`.
- Approved either a separate runtime source-sync review or a one-time
  runtime-local inline Python pre-inventory script.
- Approved the control API POST shape only with runtime-local token source,
  0600 curl config, matching CSRF cookie/header, and one-shot hard stops.

BB verdict: `DONE_WITH_CONCERNS`.

- Rejected using the missing runtime helper.
- Approved the one-time inline private signed GET-only inventory replacement.
- Approved caps:
  - open orders `<=20`
  - nonzero positions `<=20`
  - open-order notional `<=1500 USDT`
  - nonzero position value `<=1500 USDT`
- Required independent post-action full-scan inventory; route `closed_all=true`
  alone was not enough.

## Fresh Pre-Inventory

Artifact:

- `/tmp/openclaw/audit/bybit_demo_cleanup_refresh_pre_inventory/20260626T030910Z_pre_inventory.json`

Scope:

- `GET /v5/order/realtime`
  `category=linear`, `settleCoin=USDT`, `openOnly=0`, `limit=50`
- `GET /v5/position/list`
  `category=linear`, `settleCoin=USDT`, `limit=200`
- base URL `https://api-demo.bybit.com`
- cursor-aware, max pages `50`
- no Bybit POST/PUT/DELETE

Result:

- open orders: `5`
- order class: all `reduceOnly=true`, `Untriggered`, `Market`
- symbols: `ETCUSDT`, `FILUSDT`, `ICPUSDT`, `NEARUSDT`, `TRXUSDT`
- estimated open-order notional: `0.00000000 USDT`
- nonzero positions: `5`
- nonzero position value: `440.14150000 USDT`
- unrealised PnL: `-7.83110000 USDT`
- parse errors: `0`
- within review caps: `true`
- `should_post_cleanup=true`

This inventory is risk/evidence hygiene only and not PnL/profit proof.

## Cleanup Action

Artifact:

- response:
  `/tmp/openclaw/audit/demo_residual_cleanup_refresh_action/20260626T030949Z_session_stop_response.json`
- meta:
  `/tmp/openclaw/audit/demo_residual_cleanup_refresh_action/20260626T030949Z_session_stop_meta.json`

Path:

- `POST /api/v1/strategy/demo/session/stop`
- API base: `http://100.91.109.86:8000`
- auth: runtime-local token file, not Mac token file
- CSRF: double-submit cookie/header via 0600 curl config

Result:

- HTTP status: `200`
- curl exit code: `0`
- route executed: `true`
- `closed_all=true`
- `partial_failure=false`
- `cancel_orders.found=5`
- `cancel_orders.cancelled=5`
- `orphan_sweep.found=4`
- `orphan_sweep.swept=4`
- `verify.clean=true`
- `verify.attempts=2`
- no retry performed

## Post-Action Inventory

Artifact:

- `/tmp/openclaw/audit/bybit_demo_cleanup_refresh_post_inventory/20260626T031031Z_post_inventory.json`

Result:

- open orders: `0`
- nonzero positions: `0`
- parse errors: `0`
- clean: `true`

This is the acceptance evidence for exchange-book cleanup.

## PG And Health Evidence

Read-only PG after action at `2026-06-26 05:10:50+02`:

- 72h demo fills: `106`
- missing order/context/blank strategy: `0/0/0`
- `flash_dip_buy=88`
- `ma_crossover=8`
- `risk_close:ipc_close_symbol=6`
- `unattributed:bybit_auto=4`

Passive healthcheck at `2026-06-26T03:10:50Z` remains `FAIL`. [68] reports
demo `working_n=4`, `resting=398`, `filled=0`, and divergence critical.

The latest local `Working` rows are:

- `oc_close_mf_fb_dm_1782442166742_135`
- `oc_risk_dm_1782442146668_133`
- `oc_risk_dm_1782440967557_121`
- `oc_close_mf_fb_dm_1782440965566_120`

All have NULL details in the inspected rows. Since independent Bybit full scan
is clean, this is classified as a local lineage/healthcheck hygiene residual,
not exchange open exposure.

## Boundaries Preserved

This checkpoint did not:

- issue a direct Bybit POST from PM
- run more than one cleanup POST
- write PG or change schema
- sync source to runtime
- restart/rebuild services
- edit crontab or runtime env
- enable Rust writer or adapter
- lower global Cost Gate
- grant probe/order/live authority
- claim profitability, bounded-probe proof, or promotion proof

The only mutation was the reviewed demo control-plane cleanup route. All
post-action fills/cancels/closes are risk hygiene only.

## State Transition

- `active_blocker_id`:
  `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB`
- `status`: `DONE_WITH_CONCERNS`
- `next_blocker_id`: `P0-PROFIT-CANDIDATE-SELECTION`

`why_not_repeating_current_blocker`: cleanup already executed exactly once and
post-action exchange full scan is clean. Repeating cleanup would violate the
one-shot envelope and add no new evidence.

## Max Safe Next Action

Build a candidate-selection packet:

- select exactly one bounded Demo candidate
- use only candidate-matched, attributed, fee/slippage-aware evidence
- exclude `flash_dip_buy`, cleanup/risk-close rows, `unattributed:bybit_auto`,
  and local stale `Working` rows
- output operator review packet only
- do not grant probe/order/live authority

## Aggressive Profit Hypotheses

1. `false_negative_high_edge_subset_after_clean_exchange_book`
   - Why it might make money: the exchange book is now clean, so false-negative
     Cost Gate candidates can be ranked without residual exposure contamination.
   - Fastest safe test: rank candidates by current-fee net edge, sealed horizon,
     attribution quality, touchability friction, and controls; select exactly
     one review packet.
   - Required data: false-negative ledger, current fee/slippage model,
     attributed fills, post-clean exchange inventory.
   - Failure condition: no candidate survives fees, controls, OOS/repeat, or
     execution realism.
   - Authority required: proposal only; bounded-probe authorization later.
   - Max safe next action: source/read-only candidate packet.

2. `maker_path_after_cleanup`
   - Why it might make money: maker placement can reduce fee and spread cost,
     but evidence must be candidate-matched and not contaminated by cleanup.
   - Fastest safe test: build a maker-ratio packet with adverse-selection
     controls and current fee tier.
   - Required data: clean attributed fills, maker/taker labels, BBO touchability,
     fee tier.
   - Failure condition: maker edge disappears after fees/slippage or low sample.
   - Authority required: research/proposal only.
   - Max safe next action: include as candidate-ranking feature.

3. `local_lineage_68_repair`
   - Why it might make money: reducing false blocker noise lets autonomous
     selection advance faster without weakening exchange/risk gates.
   - Fastest safe test: source-only healthcheck/reconciler patch that treats
     exchange-clean close/risk stale Working rows as local lineage residuals.
   - Required data: order_state_changes rows, exchange clean inventory, route
     response.
   - Failure condition: any exchange residual exists or the rule would hide real
     open exposure.
   - Authority required: source-only review; no runtime mutation by default.
   - Max safe next action: defer until after candidate packet unless [68] blocks it.

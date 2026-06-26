# Demo Residual Cleanup Action - Unauthenticated Block

Timestamp: 2026-06-26T02:45Z

## Blocker

`P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW`

## Decision

`BLOCKED_BY_RUNTIME_AUTHORIZATION`.

The CSRF delivery blocker was fixed in source, and E3/BB conditionally approved
one demo-only cleanup POST through the reviewed helper. PM executed exactly one
real control API POST to `/api/v1/strategy/demo/session/stop`. It failed at
HTTP `401` with `reason_codes=["unauthenticated"]` before the route executed.
No exchange mutation occurred.

Per E3/BB stop conditions, PM did not retry, did not use a direct Bybit POST
shortcut, and did not attempt an alternate cleanup path.

## Session State

- `/tmp/openclaw/session_loop_state_20260626T022556Z_demo_residual_cleanup_action_refresh.json`
- `/tmp/openclaw/session_loop_state_packet_20260626T022556Z_demo_residual_cleanup_action_refresh.json`
- Anti-repeat decision: `new_evidence_delta_allows_active_blocker_progress`

## Review Chain

Initial refreshed review:

- E3: `DONE_WITH_CONCERNS`; approved exactly one helper-mediated POST if fresh
  inventory remained inside the reviewed demo cleanup scope.
- BB: `DONE_WITH_CONCERNS`; approved the control-plane stop route as safer than
  ad hoc direct Bybit cancel/close, with mandatory fresh cursor-aware
  post-inventory.

Fresh inventory changed the exact symbol set, so PM stopped before POST and
requested delta review.

Delta review:

- E3: `DONE_WITH_CONCERNS`; approved expanding the one-shot cleanup envelope to
  the fresh all-demo USDT-linear residual/current exposure because the action
  class was unchanged.
- BB: `DONE_WITH_CONCERNS`; approved the refreshed scope conditionally, with
  explicit stop conditions and independent post-action inventory requirement.

## Fresh Pre-Action Inventory

PM collected cursor-aware private GET-only demo inventory immediately before
the action:

- Artifact:
  `/tmp/openclaw/audit/bybit_demo_cleanup_action_pre_inventory/20260626T024042Z_pre_inventory.json`
- Generated: `2026-06-26T02:40:42Z`
- Endpoints:
  - `GET /v5/order/realtime`, `category=linear`, `settleCoin=USDT`,
    `openOnly=0`, `limit=50`, cursor loop
  - `GET /v5/position/list`, `category=linear`, `settleCoin=USDT`,
    `limit=200`, cursor loop
- Open orders: `6`
- Open-order symbols: `ETCUSDT`, `FILUSDT`, `ICPUSDT`, `NEARUSDT`, `TRXUSDT`
- Estimated open notional: `200.61774000 USDT`
- Order classes:
  - `1` linked non-reduce-only `FILUSDT` Buy Limit,
    `orderLinkId=oc_dm_1782441298169_128`
  - `5` reduce-only `StopLoss` conditionals
- Nonzero positions: `5`
- Position symbols: `ETCUSDT`, `FILUSDT`, `ICPUSDT`, `NEARUSDT`, `TRXUSDT`
- Position value: `636.52024000 USDT`
- Unrealised PnL: `-12.86180000 USDT`

This inventory is exchange-truth risk evidence only. It is not Cost Gate,
bounded-probe, promotion, or risk-adjusted PnL proof.

## Action Attempt

Attempted exactly one reviewed helper-mediated POST:

- Path: `/api/v1/strategy/demo/session/stop`
- API base: `http://100.91.109.86:8000`
- Reviewed change id: `pm-e3-bb-demo-cleanup-20260626T024042Z`
- Helper: `helper_scripts/operator/control_api_csrf_post.py`
- Response artifact:
  `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T024042Z_session_stop_response.json`
- Meta artifact:
  `/tmp/openclaw/audit/demo_residual_cleanup_action/20260626T024042Z_session_stop_meta.json`

Result:

- helper `ok=false`
- curl return code `0`
- HTTP status `401`
- reason codes: `["unauthenticated"]`
- route executed: `false`
- exchange mutation occurred: `false`
- retry in same envelope: `false`

The local helper used the source checkout token file
`program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token`,
whose mtime is `2026-04-20T22:59:09Z` on Mac. Read-only runtime inspection
showed no `OPENCLAW_API_TOKEN` or `OPENCLAW_API_TOKEN_FILE` in the non-login SSH
environment, and the runtime checkout token file mtime is
`2026-03-26 21:27:31 +0100`. Source inspection confirms `current_actor`
compares the Bearer token against the runtime process `settings.api_token`.

Inference: the failed POST is now blocked by authenticated token-source
alignment, not CSRF cookie delivery.

## Boundaries Preserved

This checkpoint did not:

- Execute the demo stop route.
- Cancel, modify, create, or close any Bybit order/position.
- Use direct Bybit POST from PM.
- Write PG or change schema.
- Sync source to runtime.
- Restart/rebuild services.
- Edit crontab or runtime env.
- Enable Rust writer or adapter.
- Lower global Cost Gate.
- Grant probe/order/live authority.
- Claim profitability or bounded-probe proof.

## State Transition

- `active_blocker_id`:
  `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-EXPOSURE-CLEANUP-ACTION-E3-BB-REVIEW`
- `status`: `BLOCKED_BY_RUNTIME_AUTHORIZATION`
- `next_blocker_id`:
  `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH`

`why_not_repeating_current_blocker`: E3/BB approved one attempt and PM used it.
The attempt failed at authentication before route execution. A second cleanup
POST under the same envelope would violate the explicit stop condition.

## Max Safe Next Action

Open a narrow auth-token path checkpoint:

- identify the runtime API token source without printing or exfiltrating token
  material
- decide whether the next reviewed cleanup should run from the runtime host
  using the runtime token source, or via a separately reviewed same-origin
  authenticated GUI/session path
- do not retry cleanup until a new E3/BB envelope and fresh pre-action inventory
  exist

Candidate selection remains blocked.

## Aggressive Profit Hypotheses

1. `runtime-local_authenticated_cleanup_invocation`
   - Why it might make money: removes residual/current demo exposure so
     candidate selection can use clean attributed evidence.
   - Fastest safe test: source/read-only auth-token path review, then a fresh
     E3/BB cleanup envelope that runs the helper or equivalent 0600 curl config
     from the runtime token source.
   - Required data: runtime token-source path, fresh pre-inventory,
     response/meta, post-inventory, PG/healthcheck read-only.
   - Failure condition: token path cannot be proven without secret leakage or
     route still fails auth/CSRF.
   - Authority required: E3/BB for the next cleanup attempt.
   - Scores: upside `5/5`, evidence `4/5`, execution realism `4/5`,
     cost `4/5`, time `3/5`, account risk `2/5`, governance risk `2/5`,
     autonomy `5/5`.
2. `clean_book_false_negative_candidate`
   - Why it might make money: false-negative candidates cannot be fairly ranked
     while demo exposure is drifting.
   - Fastest safe test: after authenticated cleanup and clean post-inventory,
     select exactly one attributed false-negative candidate packet.
   - Required data: post-clean inventory, fee/slippage scorecard,
     candidate-matched fills and controls.
   - Failure condition: residual orders/positions remain or fills are cleanup
     / unattributed.
   - Authority required: proposal only until bounded-probe review.
   - Scores: upside `4/5`, evidence `3/5`, execution realism `3/5`,
     cost `4/5`, time `2/5`, account risk `2/5`, governance risk `1/5`,
     autonomy `5/5`.
3. `maker_ratio_reset_after_demo_stop`
   - Why it might make money: current linked maker order flow shows placement
     is active, but cleanup is needed before maker-ratio evidence is usable.
   - Fastest safe test: post-clean maker-ratio candidate review with
     adverse-selection controls.
   - Required data: clean exchange book, BBO freshness, maker/taker fee tier,
     candidate attribution.
   - Failure condition: maker fills remain non-candidate or sub-fee after
     controls.
   - Authority required: candidate review only; bounded probe later.
   - Scores: upside `4/5`, evidence `2/5`, execution realism `3/5`,
     cost `4/5`, time `3/5`, account risk `2/5`, governance risk `1/5`,
     autonomy `4/5`.

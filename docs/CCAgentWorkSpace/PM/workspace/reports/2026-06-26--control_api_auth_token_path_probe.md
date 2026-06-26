# Control API Auth Token Path Probe

Timestamp: 2026-06-26T02:56Z

## Blocker

`P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH`

## Decision

`DONE_WITH_CONCERNS`.

The prior cleanup action failed at HTTP `401 unauthenticated` before route
execution. This checkpoint proved that the runtime host's own control API token
file can authenticate a safe read-only route when used locally on `trade-core`.

This does not authorize cleanup, cancel, modify, close, order placement, probe
authority, live authority, PG writes, service restarts, source sync, or Cost
Gate mutation.

## Session State

- `/tmp/openclaw/session_loop_state_20260626T024946Z_control_api_auth_token_path.json`
- Anti-repeat decision: `PROCEED_NEW_EVIDENCE_DELTA`
- Evidence delta: previous cleanup POST failed `401`; runtime token-file mtime
  differs from the Mac checkout token-file mtime; a runtime-local auth proof was
  required before any fresh cleanup envelope.

## Review Chain

E3 reviewed the route and probe shape and returned `APPROVE` with constraints:

- exactly one `GET /api/v1/backtest/status`
- no POST, cleanup retry, Bybit call, PG write, service restart, source/env/
  crontab mutation
- no token material in stdout, stderr, argv, artifacts, hashes, prefixes, or
  copied transcript
- use a `0600` temporary curl config and remove it by trap
- if HTTP is `401` or non-2xx, stop without alternate token or login flow

Source basis:

- `GET /api/v1/backtest/status` depends on `_get_auth_actor` but requires no
  Operator role.
- `_get_auth_actor` accepts `Authorization: Bearer ...` and compares it with
  `base.settings.api_token`.
- `settings.api_token` resolves from `OPENCLAW_API_TOKEN`, then
  `OPENCLAW_API_TOKEN_FILE`, then default `.secrets/api_token`.
- `BacktestEngine.get_status()` returns in-memory stub status only.
- CSRF does not apply to GET.

## Runtime Probe

Runtime host: `trade-core`

Command class:

- SSH to runtime
- read token from
  `program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token`
  into a shell variable
- write `Authorization: Bearer ...` only into a chmod `600` temporary curl
  config
- curl exactly one GET:
  `http://100.91.109.86:8000/api/v1/backtest/status`
- write response and sanitized meta under `/tmp/openclaw/audit`
- remove the temporary curl config

Artifacts:

- Meta:
  `/tmp/openclaw/audit/control_api_auth_token_path/20260626T025405Z_auth_probe_meta.json`
- Response:
  `/tmp/openclaw/audit/control_api_auth_token_path/20260626T025405Z_auth_probe_response.json`

Result:

- HTTP status: `200`
- curl exit code: `0`
- JSON valid: `true`
- top-level keys: `last_result_available`, `source`, `stub`
- response:
  - `last_result_available=false`
  - `source=rust_engine_primary`
  - `stub=true`

No token material was printed or written to the sanitized meta.

## Inference

The runtime-local default token file is accepted by the running control API for
authenticated read-only requests. The prior HTTP `401` cleanup failure was a
token-source alignment issue in the Mac-side helper invocation, not evidence
that the runtime API cannot authenticate programmatic requests.

The successful GET does not execute or validate the cleanup route. A cleanup
retry still needs a fresh E3/BB envelope, fresh cursor-aware demo pre-inventory,
and the exact one-shot stop conditions.

## Boundaries Preserved

This checkpoint did not:

- retry `/api/v1/strategy/demo/session/stop`
- call Bybit or any exchange endpoint
- cancel, modify, create, or close any order/position
- write PG or change schema
- sync source to runtime
- restart/rebuild services
- edit crontab or runtime env
- enable Rust writer or adapter
- lower global Cost Gate
- grant probe/order/live authority
- claim profitability or bounded-probe proof

## State Transition

- `active_blocker_id`:
  `P1-RUNTIME-HEALTH-HYGIENE-CONTROL-API-AUTH-TOKEN-PATH`
- `status`: `DONE_WITH_CONCERNS`
- `next_blocker_id`:
  `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESIDUAL-CLEANUP-ACTION-REFRESH-E3-BB`

`why_not_repeating_current_blocker`: the auth-token path has now produced the
needed runtime-local proof. Repeating it would not add evidence unless a later
cleanup action produces a new auth failure.

## Max Safe Next Action

Build a fresh `PM -> E3 -> BB -> PM` cleanup envelope:

- use this auth proof as input
- collect a fresh cursor-aware demo private GET pre-inventory immediately before
  any proposed cleanup action
- allow at most one reviewed cleanup POST through the runtime-local
  authenticated control-plane path
- stop on any auth, CSRF, runtime, or exchange failure

Candidate selection remains blocked until cleanup succeeds or residual exposure
is explicitly accepted.

## Aggressive Profit Hypotheses

1. `runtime_local_authenticated_cleanup_path`
   - Why it might make money: removes residual/current demo exposure so future
     PnL selection is not contaminated by uncontrolled positions or stale
     orders.
   - Fastest safe test: fresh E3/BB cleanup packet plus fresh inventory, then
     one reviewed runtime-local cleanup POST only if approved.
   - Required data: current open orders, positions, route response, post-action
     inventory if route executes.
   - Failure condition: auth/CSRF/runtime/exchange failure, unexpected symbol
     scope, or unresolved residual exposure.
   - Authority required: E3/BB exchange-facing review; no live authority.
   - Max safe next action: prepare refreshed review packet only.

2. `maker_path_after_clean_exposure`
   - Why it might make money: maker-ratio improvements can reduce fees and
     adverse spread cost after exposure noise is removed.
   - Fastest safe test: post-clean candidate packet using attributed demo fills,
     maker ratio, adverse-selection controls, and current fee tier.
   - Required data: clean attributed fills, current fee assumptions, BBO/touch
     realism.
   - Failure condition: net edge disappears after fees/slippage or attribution
     is incomplete.
   - Authority required: research/proposal only until bounded-probe approval.
   - Max safe next action: define ranking columns for candidate packet.

3. `false_negative_high_edge_subset`
   - Why it might make money: Cost Gate false negatives may hide regime-specific
     high-edge cells that are filtered by broad aggregate thresholds.
   - Fastest safe test: after cleanup, rank false negatives by current-fee net
     edge, sealed horizon, attribution quality, and touchability friction.
   - Required data: false-negative ledger, fee/slippage model, attributed fills,
     controls.
   - Failure condition: no candidate survives fees, OOS controls, and execution
     realism.
   - Authority required: candidate review only.
   - Max safe next action: source-only scoring spec after P0 cleanup.

# Standing Auth Readiness Cycle Source Fix

- Date: 2026-07-01
- Active blocker: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`
- State transition: `DONE_WITH_CONCERNS`
- Next blocker: `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-RUNTIME-REFRESH-E3-SCOPE-CURRENT-HEAD`
- Candidate: `grid_trading|ETHUSDT|Buy`

PM resumed the expired standing Demo loss-control envelope blocker at parent fetched source `c73275f549d0022ea72c677196bce9230bc59f91`. Runtime read-only evidence still showed `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json` sha `8c891b4e675821118d79921631ccd07c29907130e24ee4dde1483f0be20cfe4f`, candidate `grid_trading|ETHUSDT|Buy`, cap `954.18759458`, max probe orders `2`, mode `0600`, expired at `2026-07-01T17:16:05.473618+00:00`.

The source blocker was a refresh cycle: `standing_demo_authorization_refresh_guardrail.py` required `bounded_demo_runtime_readiness_v1` status `BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES`, while bounded readiness correctly blocks on the same expired standing auth that the guardrail is supposed to refresh.

Source change:

- Added explicit `--allow-expired-standing-auth-readiness-only`.
- Default remains fail-closed and still requires readiness READY.
- The explicit flag only accepts readiness status `BOUNDED_DEMO_RUNTIME_BLOCKED_BY_AUTH_OR_PLAN` when the combined top-level and nested blocker set is exactly `standing_authorization:standing_auth_expired`.
- Credential, connector, plan, engine env, candidate, authority, and any extra readiness blocker still fail closed.
- Output now records `runtime_readiness_resolution`, `expired_standing_auth_readiness_exception_applied`, and `runtime_readiness_other_blockers_accepted=false`.

E2 initially found a real fail-open risk: inconsistent readiness packets with top-level `standing_authorization:standing_auth_expired` but nested plan blockers could be accepted. PM fixed this by unioning top-level `blocking_reasons` and nested `checks.*.blocking_reasons`, then added a regression for nested blocker disagreement.

Verification:

- PM focused: `10 passed`.
- PM adjacent: `66 passed`.
- `py_compile` passed.
- `git diff --check` passed.
- E2 verdict: `DONE`; replayed inconsistent packet returns `STANDING_DEMO_AUTHORIZATION_REFRESH_NOT_READY` and no preview.
- E4 verdict: `DONE`; focused `10 passed`, adjacent `66 passed`, py_compile and diff-check passed.

Boundary result: source/test/docs only. No Control API GET, public quote, active Decision Lease, private/order endpoint, order/cancel/modify, PG write, service/env/risk mutation, runtime standing-envelope materialization, Cost Gate lowering, live/mainnet authority, fill/PnL, promotion, or profit proof occurred.

Next PM action: request E3 for exact runtime refresh scope: read-only bounded readiness, one runtime-local authenticated Control API fast-balance GET, source-only guardrail with `--allow-expired-standing-auth-readiness-only`, exact preview materialization only if READY and no authority/cap/probe-order expansion, post-refresh standing validator and readiness. BB is not required unless the next scope becomes exchange-facing.

# Standing Auth Explicit AVAX Bounded Auth Object Review

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0348Z_standing_auth_explicit_avax_bounded_auth_object_review.json` |
| `session_loop_state_sha256` | `c55a59824b3125f2a1732fc77e3dc6576f7232bfdae8016f3edf684f52219ec6` |
| `source_commit` | `523bffa2c47e899682a67497eef7dd6d70364a39` |
| `runtime_review_dir` | `/tmp/openclaw/standing_auth_explicit_avax_review_after_sync_20260627T0348Z/` |

## Decision

The operator correction is now enforced through source, runtime sync, and timestamped no-order evidence:

- GUI/Rust RiskConfig is the risk source of truth.
- GUI `P1 Risk/Trade=10.0%` maps to `per_trade_risk_pct=0.1`.
- The resolved per-order cap is `955.24342626 USDT` from accepted Demo equity `9552.43426257`.
- The old bounded local `10 USDT` diagnostic cap is not authorization-grade risk authority.

Source `523bffa2` fixes `false_negative_operator_review.py` so explicit `decision=approve-preflight` can consume a valid standing Demo authorization when no typed-confirm is supplied. Wrong typed-confirm still fails closed.

## Verification

Local source verification:

- Reproduced the regression with two failing focused tests before the fix.
- Focused false-negative operator review tests after fix: `11 passed`.
- Adjacent GUI-cap/standing/preflight/auth suites: `192 passed`.
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/false_negative_operator_review.py`: pass.
- `git diff --check`: pass.

Runtime sync:

- Runtime source fast-forwarded `22a5c0c5 -> 523bffa2`.
- Crontab expected-head pins replaced from `22a5c0c5` to `523bffa2` (`11` replacements; `70` lines preserved).
- Runtime focused false-negative tests: `11 passed`.
- Correct API unit is `openclaw-trading-api.service`, active/running PID `2218842`; `openclaw-api.service` is a stale pointer.
- Watchdog active/running PID `1538268`.
- No service restart, cron run, writer enablement, plan mutation, or order.

## Outputs

Timestamped AVAX chain:

- False-negative review: sha `497064af8f08c29b657fe194ee84e3e345c8b4336f610c2d94f13f22b98064b2`, status `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`, decision `approve-preflight`.
- Preflight: sha `32dbe04c570032004b5502aa442165da6f0bbc5395ca2ca3229db71570fd3013`, status `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`.
- Touchability: sha `afcaab2d62f09d6d5b5095c855b4766041b6e48e1d70b0d24eb80951fea70bcb`, status `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED`.
- Placement: sha `b79b63f68b71987392df6afdedbae8af45f6111e07c152e01068a788f3ecd81d`, status `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`.
- Readiness: sha `11404e43339fee59c607526bc98c36617bfe42c179e5cf23a74e874e4e4aa76c`, status `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`.
- Bounded auth: sha `8bbd865688de2fa7c067927383e584a4ca24dddca797a1ebbc45da15a7cd3cea`, status `BOUNDED_DEMO_PROBE_AUTHORIZED`, decision `authorize`, `blocking_gates=[]`.
- Manifest: sha `2d981fcf19746d0dcb82e09a78d5adf3c1e95319a66241641d655593378bdf3b`.

Bounded auth object:

- `authorization_id=standing-demo-9309f8073f60d3db`
- `side_cell_key=grid_trading|AVAXUSDT|Sell`
- `max_authorized_probe_orders=2`
- `expires_at_utc=2026-06-27T14:51:58.043996+00:00`
- `authorization_confirmation_source=standing_demo_authorization`

GUI risk gate in bounded auth:

- `expected_cap_usdt=955.24342626`
- `preflight_cap_usdt=955.24342626`
- `placement_cap_usdt=955.24342626`
- `standing_cap_usdt=955.24342626`
- `risk_source_of_truth=GUI-backed Rust RiskConfig`
- `preflight_local_10_usdt_cap_is_global_risk_authority=false`
- `placement_local_10_usdt_cap_is_global_risk_authority=false`

## Boundary

This was source/test work, runtime source/crontab pin sync, and timestamped no-order artifact generation only. It did not overwrite canonical `_latest`, include the auth object in a plan, enable writer/adapter, submit an order, call Bybit private/order APIs, mutate Cost Gate, grant live/mainnet authority, or claim profit proof.

The auth object is review evidence. Active runtime probe/order authority remains false in the artifact answers.

## Next

Run a no-order current-candidate bounded Demo admission envelope review consuming this timestamped auth object. Required blockers before any order-capable action remain:

- Decision Lease
- Guardian risk gate
- Rust authority runtime admission
- fresh BBO at actual admission
- auditability and reconstructability
- no Cost Gate lowering
- no risk expansion

If candidate identity, standing envelope expiry, GUI cap/equity, or source/runtime head drifts before admission review, record `ROTATED` or `BLOCKED_BY_LOSS_CONTROL` instead of executing.

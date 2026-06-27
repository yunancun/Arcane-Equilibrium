# Current Candidate Bounded Demo Admission After Auth Object

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `BLOCKED_BY_LOSS_CONTROL` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0400Z_current_candidate_admission_after_auth_object.json` |
| `session_loop_state_sha256` | `f74967414a1e0b5d11ab16ac93423831aa66bc12457698a6aaf1757da3fc32ae` |
| `output_dir` | `/tmp/openclaw/current_candidate_bounded_demo_admission_after_auth_object_20260627T0400Z/` |
| `review_sha256` | `7f21a507e41b01de7e767b7bd02723e8b3e18b09f9d647e075b7195f0c3c8303` |
| `manifest_sha256` | `51dea969287e262d38d3a25e4145f1f399af1adff56a9e492a90133d7f0a1c3a` |

## Decision

The no-order admission review consumed the timestamped AVAX bounded auth object and removed the previous `bounded_demo_authorization_object_valid` blocker.

Result:

- status: `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`
- candidate: `grid_trading|AVAXUSDT|Sell`
- bounded auth valid: `true`
- source blockers: `[]`
- authority contamination: `[]`
- runtime admission ready: `false`
- order admission ready: `false`

Remaining blockers:

- `decision_lease_valid`
- `guardian_risk_gate_valid`
- `rust_authority_path_valid`
- `fresh_bbo_refresh_at_actual_admission`

## Inputs

- Current no-order envelope: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/current_candidate_no_order_refresh_envelope.json`, sha `993ff2ca0c027281d81d8fb80a2357b3063c41ecbb9261b8740b7ebc02fef9eb`.
- Runtime admission handoff: `/tmp/openclaw/current_candidate_runtime_admission_handoff_review_20260627T022444Z/current_candidate_runtime_admission_handoff_review.json`, sha `8e8f9387fd66d895a22f8238fe48e10366a405cccd0b079ce7d02a5360481f9a`.
- Standing Demo authorization snapshot: sha `42fca4b3e4bd1143dd8550bb4f36ff85774eed7a3b8acbf3ae99243d2a49d520`.
- Runtime bounded auth object snapshot: sha `8bbd865688de2fa7c067927383e584a4ca24dddca797a1ebbc45da15a7cd3cea`.

## Risk Semantics

GUI/Rust RiskConfig remains the risk source of truth:

- GUI `P1 Risk/Trade=10.0%`
- `per_trade_risk_pct_fraction=0.1`
- accepted Demo equity `9552.43426257`
- resolved cap `955.24342626 USDT`
- rounded candidate notional `954.6264 USDT`
- `local_10_usdt_cap_is_global_risk_authority=false`

## Verification

- Generated review: `/tmp/openclaw/current_candidate_bounded_demo_admission_after_auth_object_20260627T0400Z/current_candidate_bounded_demo_admission_envelope_review_after_auth_object.json`
- Manifest invariant checks passed:
  - bounded auth gate passed
  - bounded auth removed from blockers
  - Decision Lease / Guardian / Rust authority / fresh BBO remain blockers
  - runtime/order admission remain false
  - source blockers empty
  - authority contamination empty
  - GUI cap is `955.24342626`
  - local `10 USDT` authority false
- Focused helper tests: `6 passed`.
- `py_compile` for admission helper: pass.

## Boundary

This was a timestamped no-order review only. No canonical `_latest` overwrite, plan mutation, writer/adapter enablement, Bybit call, order/cancel/modify, PG write, runtime/service/env/crontab mutation, Cost Gate change, risk expansion, live/mainnet authority, or profit proof occurred.

## Next

Implement or generate no-order machine-checkable evidence for:

- current-candidate Decision Lease
- Guardian risk gate under the GUI-resolved cap
- Rust authority path/runtime admission review
- fresh actual-admission BBO inside a reviewed runtime-admission envelope

Do not execute until every admission gate passes and auditability/reconstructability remain intact.

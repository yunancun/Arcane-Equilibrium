# Current Candidate Bounded Demo Admission Envelope Review

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `BLOCKED_BY_LOSS_CONTROL` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0239Z_current_candidate_bounded_demo_admission_envelope_review.json` |
| `session_loop_state_sha256` | `b6e2a84b753998b1f26091420dacb883512d36e04939c066186f1b038d086b5a` |
| `source_head` | `92e9172d9fdc410c7dc1d47f3334c05b04258297` |
| `runtime_head` | `665b2eef615cd1d93f0691a757f9ab4c3ade83ed` |

## Decision

本輪新增並執行 current-candidate bounded Demo admission envelope review。結果是 `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`。

這個結果確認 operator correction：GUI `P1 Risk/Trade = 10.0%` 是 `per_trade_risk_pct=0.1`，不是 `10 USDT` 單筆下單上限。Current admission review 的 per-order cap 固定來自 `current_candidate_envelope.cap_resolution.resolved_cap_usdt`，目前是 `955.24342626 USDT`。Local/bounded `10 USDT` 只能是歷史 diagnostic envelope，不可作 runtime admission cap。

Review contract 本身已 ready，但 runtime/order admission 仍 fail-closed，因為 order-capable action 還缺 current-candidate-scoped loss-control authority chain。

## Source/Test

新增：

- `helper_scripts/research/cost_gate_learning_lane/current_candidate_bounded_demo_admission_envelope_review.py`
- `helper_scripts/research/tests/test_current_candidate_bounded_demo_admission_envelope_review.py`

補：

- `helper_scripts/SCRIPT_INDEX.md`

驗證：

- focused pytest: `6 passed`
- adjacent pytest: `66 passed`
- `py_compile`: pass
- `git diff --check`: pass before source commit

Source/test commit pushed:

- `92e9172d9fdc410c7dc1d47f3334c05b04258297`

## Review Artifact

Input:

- handoff: `/tmp/openclaw/current_candidate_runtime_admission_handoff_review_20260627T022444Z/current_candidate_runtime_admission_handoff_review.json`, sha `8e8f9387fd66d895a22f8238fe48e10366a405cccd0b079ce7d02a5360481f9a`
- current envelope: `/tmp/openclaw/current_candidate_public_quote_construction_refresh_20260627T021157Z/current_candidate_no_order_refresh_envelope.json`, sha `993ff2ca0c027281d81d8fb80a2357b3063c41ecbb9261b8740b7ebc02fef9eb`
- runtime standing Demo authorization snapshot: sha `b805df18d1bc3bfed0bbf15b8ec6d120e96695eca04702fb68bc7e472a80b66d`

Output:

- path: `/tmp/openclaw/current_candidate_bounded_demo_admission_envelope_review_20260627T023903Z/current_candidate_bounded_demo_admission_envelope_review.json`
- sha: `34cd80461706cde2dad8bb5bff9b2d72224230452a2b6d989ee9ae1b6f4b224c`
- status: `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`
- candidate: `grid_trading|AVAXUSDT|Sell`

Risk semantics:

- GUI/Rust RiskConfig source of truth: true
- GUI P1 risk/trade: `10.0%`
- `per_trade_risk_pct_fraction`: `0.1`
- max single position: `25.0%`
- accepted Demo equity: `9552.43426257`
- resolved cap: `955.24342626 USDT`
- constructed notional: `954.6264 USDT`
- local `10 USDT` as global risk authority: false

Loss-control blockers:

- `standing_demo_authorization_valid_if_supplied`: runtime standing envelope is still `grid_trading|ETHUSDT|Buy`, not current `grid_trading|AVAXUSDT|Sell`
- `bounded_demo_authorization_object_valid`: no current AVAX bounded auth object exists
- `decision_lease_valid`: no current-candidate Decision Lease exists
- `guardian_risk_gate_valid`: no current-candidate Guardian/risk gate pass exists
- `rust_authority_path_valid`: no current-candidate Rust authority-path artifact was supplied to this review
- `fresh_bbo_refresh_at_actual_admission`: prior BBO is construction evidence only; actual admission must refresh BBO

Still false:

- `runtime_admission_ready=false`
- `order_admission_ready=false`
- `operator_authorization_object_emitted=false`
- `bounded_demo_probe_authorized=false`
- `order_submission_performed=false`
- `runtime_mutation_performed=false`
- `global_cost_gate_lowering_recommended=false`

## Boundary

No Bybit call, no private endpoint, no order/cancel/modify, no Control API POST, no PG query/write, no runtime mutation, no service restart, no crontab/env mutation, no Cost Gate lowering, no risk expansion, no bounded auth/probe/order/live authority, and no profit proof.

## Next

Do not repeat the quote/construction or handoff review unless candidate/cap/evidence changes. Next safe work is to reissue or materialize current-candidate-scoped Demo loss-control / bounded authorization review artifacts for `grid_trading|AVAXUSDT|Sell`, then rerun this no-order admission review. Any order-capable step still requires Decision Lease, Guardian risk gate, Rust authority path, and fresh BBO at actual admission.

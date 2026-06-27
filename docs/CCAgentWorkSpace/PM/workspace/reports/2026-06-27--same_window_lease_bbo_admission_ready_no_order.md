# Same-Window Lease/BBO Admission Ready No-Order

| Field | Value |
|---|---|
| `blocker_id` | `P0-CURRENT-CANDIDATE-SAME-WINDOW-LEASE-BBO-ADMISSION-REVALIDATION` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T163540Z_same_window_lease_bbo_admission/session_loop_state.json` |
| `session_loop_state_sha256` | `94c17cad206c573cd7f87ef4c334f16125128e6aad04d176e3f48b7f1e451ae4` |
| `round_manifest` | `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/same_window_lease_bbo_admission_manifest.json` |
| `round_manifest_sha256` | `1ab1e279333708cb3c0090ac207f70fe7006662b5860fc03abb3cf7a45f2e399` |
| `source_head_at_review` | `6b75c5039eb1dab2dd38d0cf4a14897f4d4a6af5` |
| `runtime_source_head_at_review` | `451be917c058a9813a5b648d3b00cadd15eef237` |

## Decision

The same-window no-order admission revalidation is ready.

The first dry-run failed closed on stale current-candidate envelope evidence. This round refreshed the Demo fast-balance equity artifact through the fixed local Control API fast-balance GET, regenerated the current-candidate no-order envelope from GUI-backed Rust RiskConfig, and then reran the same-window helper.

GUI/Rust RiskConfig remains the risk source of truth:

- GUI P1 risk/trade: `10.0%`
- `per_trade_risk_pct_fraction`: `0.1`
- accepted Demo equity: `9549.38926928`
- resolved per-trade/effective cap: `954.93892693 USDT`
- GUI max-single-position: `25.0%`
- single-position budget: `2387.34731732 USDT`
- local `10 USDT` authority: `false`

## Evidence

- initial dry-run: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/dry_run_current_candidate_actual_admission_bbo_lease_window.json`
- initial dry-run sha: `111e7bb40dc87d1015b2da71fe3ff111a3173dc95ef96428fa259c8b616e64b5`
- initial dry-run status: `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_SOURCE_NOT_READY`
- blocker: `current_candidate_envelope_stale`

- accepted fresh equity: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/inputs/demo_account_equity_artifact_fresh_ready.json`
- accepted fresh equity sha: `6ed7e6854321bb0dd2a0913405736ac26806478fd0f61c2bafd9f5eb7db2e19a`
- accepted fresh equity status: `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`

- refreshed envelope: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/inputs/current_candidate_envelope_fresh_v656.json`
- refreshed envelope sha: `37d7c44d15ebd85f808ef4e29d879b002f1b310b60ded681c65ee2d5c344e4f4`
- refreshed envelope status: `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`

- ready dry-run: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/dry_run_current_candidate_actual_admission_bbo_lease_window_after_envelope_refresh.json`
- ready dry-run sha: `a118a6f696bcfeb7a861cfea01ab41e7e3d1af9cf6ce38bbb09c1b0e07f23510`
- ready dry-run status: `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DRY_RUN_READY`

- same-window active lease/BBO/gate artifact: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/current_candidate_actual_admission_bbo_lease_window.json`
- same-window active lease/BBO/gate sha: `b82bfc700d522ac5db94c7a4f07e41bb23394ab97be729151c9f79118fbf4083`
- same-window active lease/BBO/gate status: `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER`
- active lease id: `lease:2ef803bcb5e9`
- lease acquire/release: `true/true`
- lease released before artifact: `true`
- source/runtime/loss-control/authority blockers: `[]/[]/[]/[]`

- public quote/construction: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/actual_quote/current_candidate_public_quote_construction_refresh.json`
- public quote/construction sha: `0c54dfaec07de43697aaa34b1e26230b3ef718e5d3ca18436987539d5bdb5195`
- BBO age: `832.241ms`
- actual rounded qty/notional: `144.1 / 954.6625 USDT`
- actual order shape under GUI cap: `true`

- active gate evidence: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/active_window/current_candidate_decision_lease_guardian_gate_evidence.json`
- active gate evidence sha: `d92e37cbdd76046a00c65d81949b5f58bc96801c30c2879cf3996f87cc6228af`
- active gate status: `CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER`

- post-run governance snapshot: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/post_run_runtime_governance_snapshot.json`
- post-run governance snapshot sha: `c3f7d4fc27117f11e0c07aa87197c89792179cb07692cc2f27d93abc5d593e59`
- post-run live lease count: `0`
- post-run lease list: `[]`

- final admission review: `/tmp/openclaw/same_window_lease_bbo_admission_20260627T163540Z/admission_review/current_candidate_bounded_demo_admission_envelope_review_after_same_window.json`
- final admission review sha: `09379324a8f28d287c4b17407f252142902ec6d93d461013964ca1c77f9fd003`
- final admission review status: `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_ENVELOPE_READY_NO_ORDER`
- final admission source blockers: `[]`
- final admission runtime blockers: `[]`
- final admission authority contamination reasons: `[]`

## Boundary

This round performed one fixed Control API fast-balance GET, one short Demo `TRADE_ENTRY` Decision Lease acquire/release, Bybit Demo public market-data GETs, read-only governance IPC snapshots, and no-order admission review generation.

It did not promote `_latest`, enable writer/adapter paths, submit/cancel/modify orders, call Bybit private/order APIs, write PG, mutate runtime config/env/service/crontab, lower Cost Gate, use live/mainnet, grant runtime/order authority, create fills/PnL, or claim profit proof.

## Concern

The final review is `READY_NO_ORDER` only. The active lease was released before artifact consumption, and the post-run governance snapshot confirms no live lease remains. Any future order-capable Demo invocation still needs a fresh final active lease/BBO/order-shape window and explicit review at that time.

Per operator request, stop after this round and do not continue dispatching the loop.

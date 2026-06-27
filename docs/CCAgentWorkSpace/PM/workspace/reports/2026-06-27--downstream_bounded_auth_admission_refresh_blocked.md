# Downstream Bounded Auth / Admission Refresh Blocked

| Field | Value |
|---|---|
| `blocker_id` | `P0-CURRENT-CANDIDATE-DOWNSTREAM-BOUNDED-AUTH-ADMISSION-REFRESH` |
| `state_transition` | `BLOCKED_BY_LOSS_CONTROL` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T_downstream_bounded_auth_admission_refresh/session_loop_state.json` |
| `session_loop_state_sha256` | `71d511c0258112be3fd57f9fc7f3b13d2af4b6eed7aaa41033217dc619652d4e` |
| `round_manifest` | `/tmp/openclaw/downstream_bounded_auth_admission_refresh_20260627T160841Z/downstream_bounded_auth_admission_refresh_manifest.json` |
| `round_manifest_sha256` | `46959d5a6501c73bcd5c809b06f212316c061ab997ef5f4fc902b158dcee6007` |
| `source_head_at_review` | `a0a31ccceb35b64f9caf9455ab252e49c09f06aa` |
| `runtime_source_head_at_review` | `451be917c058a9813a5b648d3b00cadd15eef237` |

## Decision

The downstream bounded auth/admission refresh is blocked by loss-control, not by a runtime crash.

The bounded authorization review failed closed because the fresh standing Demo envelope and the downstream preflight/placement artifacts do not share the same GUI/Rust RiskConfig cap lineage:

- standing auth sha: `47757625ef41e845ecfb4818f35aa20a225bc40e7bed86ca2ebdd4f8ab7d0eb6`
- standing GUI P1 risk/trade: `10.0%`
- standing `per_trade_risk_pct_fraction`: `0.1`
- standing resolved cap: `954.93892693 USDT`
- standing max-single-position budget: `2387.34731732 USDT`
- downstream preflight sha: `128632b67dbf3bf43e89a00ce61f2bf275b0111e70d09ec08ac8c35e4bef453f`
- downstream placement sha: `aeb93222f9e978cf78121b1152b9f6f46ebd109f2f5e0fad77a24e24e7cdf9be`
- downstream preflight/placement cap: `955.1369426 USDT`
- local `10 USDT` authority: `false`

Both caps are GUI-derived percentages, but they come from different accepted equity/cap snapshots. The helper correctly refused to manufacture a bounded authorization object across that mismatch.

## Auth Review

- path: `/tmp/openclaw/downstream_bounded_auth_admission_refresh_20260627T160841Z/bounded_authorization/bounded_probe_operator_authorization_authorize.json`
- sha: `7cc2faaf50f7eb30b4acb7c2cc7dd0a96f862c52da1ab27a489d96fb61c264d5`
- status: `GUI_RISK_CAP_INPUT_REQUIRED_FOR_AUTHORIZATION_REVIEW`
- decision requested: `authorize`
- blocking gates: `gui_risk_notional_limit_valid`, `authorization_id_present`, `standing_demo_operator_matches`, `probe_budget_valid`, `authorization_expiry_valid`, `typed_confirm_matches`
- `operator_authorization_object_emitted=false`
- `bounded_demo_probe_authorized=false`
- active runtime probe/order authority: `false`

## Admission Review

- path: `/tmp/openclaw/downstream_bounded_auth_admission_refresh_20260627T160841Z/admission_review/current_candidate_bounded_demo_admission_envelope_review.json`
- sha: `2876f159f62e856e3013fc054351cd8eca974534bad2d1cc671a002031a0d1a9`
- status: `CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL`
- blocking gates: `bounded_demo_authorization_object_valid`, `decision_lease_valid`, `fresh_bbo_refresh_at_actual_admission`
- source blockers: `[]`
- authority contamination reasons: `[]`
- `order_admission_ready=false`
- `runtime_admission_ready=false`
- `order_submission_performed=false`

## Boundary

This round copied runtime `_latest` artifacts into a timestamped local evidence directory and generated timestamped no-order review packets only. It did not promote `_latest`, mutate runtime configuration, acquire or release a Decision Lease, refresh actual-admission BBO, call Bybit private/order APIs, submit/cancel/modify orders, enable writer/adapter paths, lower Cost Gate, use live/mainnet, produce fills/PnL, or claim profit proof.

## Next

Rebuild `false_negative_bounded_probe_preflight` and `bounded_probe_placement_repair_plan` from the same current GUI/Rust RiskConfig plus accepted Demo equity lineage as the standing authorization, then rerun bounded operator authorization. Only after the bounded auth object is machine-valid should the system rerun same-window Decision Lease, Guardian, Rust authority, actual BBO, GUI cap, book-clean, auditability, and reconstructability gates before any order-capable Demo invocation.

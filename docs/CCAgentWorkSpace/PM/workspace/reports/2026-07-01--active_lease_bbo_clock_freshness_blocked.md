# Active Lease BBO Clock Freshness Blocked

## Summary

- Active blocker: `P0-CURRENT-CANDIDATE-ACTIVE-LEASE-BBO-WINDOW-E3-BB-REVIEW`
- State transition: `BLOCKED_BY_LOSS_CONTROL`
- Next blocker: `P0-CURRENT-CANDIDATE-ACTIVE-BBO-CLOCK-FRESHNESS-GATE-DIAGNOSIS`
- Candidate: `grid_trading|ETHUSDT|Buy`
- Runtime base: `/tmp/openclaw/fresh_source_envelope_refresh_20260701T014200Z_snapshot_noauth/`
- Source metadata: `9c36bf82c166984b0aa392ee625d361325793956`
- Runtime head: `461dfbe210a46b3cd9c23a1424085124adf5b9ee`

## Session State

- Session loop state: `/tmp/openclaw/session_loop_state_20260701T_active_lease_bbo_freshness_precheck/session_loop_state.json`
- Session loop state sha: `0d5fc08947269c4d1ac8e482d07de6f8abf1ff09dab0e0521a6b8651d071ce83`
- New evidence delta: v693 artifacts were stale for the 900s active-window helper limits, so PM refreshed source inputs before requesting E3/BB review.

## Review Chain

- PM no-authority equity artifact: `equity/demo_account_equity_artifact.json`
  - sha `74e1ec42070342348642ef2720e22350cc122ea670740f43d0dbcf495cfd0e8e`
  - status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`
- PM no-authority envelope: `envelope/current_candidate_no_order_refresh_envelope_noauth_ready.json`
  - sha `7e0227eaa747e8d1e46c1bf618bda79c6dfd0d9299bca62f0f5da708fcf017fc`
  - status `CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY`
- E3/BB request: `e3_bb_active_lease_bbo_refresh_review_request.json`
  - sha `06df6cfa8594c64ff56184fc18cc2c7d065194b04e9e623aeb61dfc349faa09f`
- E3 and BB both returned `DONE_WITH_CONCERNS` / `APPROVE_WITH_CONDITIONS`.

## Phase A

- Scope: exactly three unauthenticated Demo public Market Data GETs against `https://api-demo.bybit.com`, followed by no-order handoff/admission/governance/sizing/gate/dry-run artifacts.
- Quote refresh: `quote/current_candidate_public_quote_construction_refresh.json`
  - sha `7de4b399f53dbd8d198645c3c9c858b2083accac8f47f548f6f210b6e1608b4a`
  - status `CURRENT_CANDIDATE_PUBLIC_QUOTE_CONSTRUCTION_REFRESH_READY_NO_ORDER`
  - request count `3`
- Handoff: sha `3968029febe7fe7382b054bbe5863ab65638ef869e00cdc9bc60c29e7753fb7f`
- Admission: sha `7b495508fa248d7e89ef0a87ab5bdc1687fe4b6ff6c606e129159029638dc1b2`
- Governance: sha `c9a66f4e1f350a68e20bc0a13679367bf5c578bc280826b05936a0075500124c`
- Sizing: sha `028ee983da4d41540451ef2026d5616e89cc21c4e07b1a411ee0ecc1686579bb`
- Sizing-aware gate: sha `c866468b9948cd28fb2b8caf6565f314576649a2ab26430fd483d21b5f78a866`
- Dry-run: sha `b39d98666454687b8e753aed0d2cbb6a5e2cf916fa0f2b7acd5a3ac181aa20bf`
  - status `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DRY_RUN_READY`
  - source blockers `[]`
  - runtime blockers `[]`
  - authority contamination `[]`

## Phase B

- Scope: one conditional no-order active Decision Lease window with explicit `OPENCLAW_CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW=1`, `--run --yes`, `--lease-ttl-seconds 5`, and explicit `--base-url https://api-demo.bybit.com`.
- Active-window artifact: `active_lease_bbo_window/current_candidate_actual_admission_bbo_lease_window_run.json`
  - sha `af480e677980548364245cad5565573e1339f184fe638465d4938bad04412839`
  - status `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_BLOCKED_BY_LOSS_CONTROL`
  - reason `actual_admission_bbo_refresh_not_ready`
  - blockers `actual_admission_bbo_refresh_not_ready`, `ticker_time_future_or_clock_ambiguous`
- Lease: `lease:ad56ce37029f`
  - acquire ok `true`
  - release ok `true`
  - released before artifact `true`
- Active quote:
  - request count `3`
  - active gate status `CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER`
  - `raw_bbo_age_ms=-4`
  - `effective_bbo_age_ms=441.275`
- Post-run governance: `post_active_governance/runtime_governance_snapshot_after_active_lease_bbo_run.json`
  - sha `3814f643026cc375632fe39b21fe7b37526bfe8dc082be0ab7926d0ff7023072`
  - status `RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY`
  - `lease_live_count=0`
  - `lease_count=0`
- Execution summary: `phase_a_b_execution_summary.json`
  - sha `0d353fa268e1e0666a7539a21a98d2ff40da20df0a6fdfc097c87f35111f122e`

## Boundary

No order, cancel, modify, private endpoint, PG write, service/env/risk mutation, Cost Gate lowering, live/mainnet action, fill, PnL, or proof occurred. The acquired/released lease is not persistent authority and must not be reused as runtime admission or order authority.

## Next

Diagnose the BBO freshness gate before any renewed E3/BB active-window review. The immediate source question is whether `ticker_time_future_or_clock_ambiguous` should fail closed for a small negative `raw_bbo_age_ms` when `effective_bbo_age_ms` remains positive and well under the freshness gate, or whether this exposes a runtime/Bybit clock ambiguity that should remain a blocker.

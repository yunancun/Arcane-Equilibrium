# Final-Window Guardian CAUTIOUS Blocked

Date: 2026-06-27

## Status

`BLOCKED_BY_LOSS_CONTROL`

The final-window current-candidate AVAX Sell chain was refreshed under GUI/Rust RiskConfig cap semantics, but runtime admission remains blocked because Guardian is `CAUTIOUS` after a fresh `reconciler_drift` following recovery. No active Decision Lease was acquired because the Guardian gate is invalid.

## Source / Runtime

- Source/runtime commit: `9d9c575b2bfbe0cfab24ec001b866c90c016059c`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_readonly_snapshot_helper_20260627T080352Z/runtime_sync_manifest.json`
- Manifest sha256: `22b69cd574c2f1b54a64b7746e805cf7483f0cd926bd3f72c00d01758e99a482`
- Crontab pins: `9d9c575b=5`, old `9040c75e=0`, line count `70`
- Verification: local/runtime focused suite `19 passed`; py_compile and `git diff --check` passed
- No service restart, no engine rebuild, no order path

## Evidence

- Equity: `/tmp/openclaw/current_candidate_final_window_fresh_equity_20260627T075301Z/demo_account_equity_artifact.json`
  - sha256 `72e3cd04b33105ce4df4c216c777d25595f2cfe8751c44eafd1cc4797c65991d`
  - equity `9551.58809495`
- No-order envelope: `/tmp/openclaw/current_candidate_final_window_no_order_envelope_20260627T075322Z/current_candidate_no_order_refresh_envelope.json`
  - sha256 `bda743baa3aa40aefdc80b13a90f35bbe14f1a9da78fd5909b140f49a6ea29e9`
  - GUI cap `955.1588095 USDT`; max-single-position budget `2387.89702374 USDT`
- Public quote/construction: `/tmp/openclaw/current_candidate_final_window_public_quote_construction_20260627T075436Z/current_candidate_public_quote_construction_refresh.json`
  - sha256 `8606a213ad3d2e3a78d2488e1d411189c18e76659699dd1a2676c041660a9804`
  - BBO age `478.308ms`; original construction `145.5 AVAX / 954.9165 USDT`
- Admission review: `/tmp/openclaw/current_candidate_final_window_admission_review_20260627T075634Z/current_candidate_bounded_demo_admission_envelope_review.json`
  - sha256 `5ccd9a239bf9f095dc00ec1c613a01966e333de0eff5830b93bdf02388bb4170`
  - bounded auth and Rust authority path valid; Decision Lease, Guardian gate, and actual-admission BBO remain blocked
- Governance snapshot: `/tmp/openclaw/current_candidate_final_window_governance_snapshot_20260627T080216Z/runtime_governance_snapshot.json`
  - sha256 `4bf3d10b17dd865953398936e6e1048d5013a1ff33d220457c868df394e1d669`
  - Guardian `CAUTIOUS`, multiplier `0.7`, `lease_live_count=0`, latest tail `reconciler_drift`
- Guardian-adjusted sizing: `/tmp/openclaw/current_candidate_final_window_guardian_adjusted_sizing_20260627T080248Z/current_candidate_guardian_adjusted_sizing_proposal.json`
  - sha256 `33e0e97e848f1827e5da535982429a8279f34f5291cbb1c9c08ca9fd949ba412`
  - proposed `101.8 AVAX / 668.1134 USDT`, under Guardian-adjusted cap `668.61116665 USDT`
- Final gate: `/tmp/openclaw/current_candidate_final_window_gate_with_sizing_20260627T080300Z/current_candidate_decision_lease_guardian_gate_evidence.json`
  - sha256 `c8990418f35621918071f5d0d1b61bd861fd909ad2f0a1bb08e9e5d7d01aa8bd`
  - blockers: `decision_lease_valid`, `guardian_risk_gate_valid`
- Diagnosis: `/tmp/openclaw/current_candidate_final_window_guardian_reconciler_diagnosis_20260627T080325Z/current_candidate_guardian_reconciler_drift_diagnosis.json`
  - sha256 `edaa2fd9c0d0910d99eab8f014640a3602fdbd12e8630b28f9573b5f8ebb424f`
  - blockers include `guardian_risk_state_not_normal`, `position_size_multiplier_below_one`, `reconciler_drift_after_recovery`, and missing active lease
- Session state: `/tmp/openclaw/session_loop_state_20260627T0804Z_final_window_guardian_cautious_blocked/session_loop_state.json`
  - sha256 `a0440bfbac73e2da703c042c9326f056b593d8929dfcecfa5426d6358e64a84f`

## Boundary

No Decision Lease acquire/release, no actual-admission BBO refresh after the Guardian blocker, no order/cancel/modify, no Bybit private/order call, no PG write, no service restart, no Cost Gate lowering, no risk expansion, no writer/adapter enablement, no live/mainnet authority, no execution, and no profit proof.

## Next

Take a fresh read-only runtime governance snapshot. Proceed only if Guardian is `NORMAL` and the active reconciler drift tail is gone; then acquire a fresh bounded Demo Decision Lease and rerun gate evidence before refreshing actual-admission BBO. Do not execute.

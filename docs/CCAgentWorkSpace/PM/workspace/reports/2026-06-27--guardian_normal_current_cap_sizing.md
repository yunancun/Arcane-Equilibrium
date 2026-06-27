# Guardian NORMAL Current-Cap Sizing

Date: 2026-06-27

## Status

`DONE_WITH_CONCERNS`

Guardian recovered to `NORMAL`, so current-candidate sizing was refreshed back to GUI/Rust current cap semantics. Runtime admission is still not cleared because there is no active current-candidate Decision Lease and no fresh actual-admission BBO.

## Source / Runtime

- Source/runtime commit: `9040c75e92c7b363087c4599ad42059450af9112`
- Runtime sync manifest: `/tmp/openclaw/runtime_source_sync_guardian_normal_sizing_20260627T074057Z/runtime_sync_manifest.json`
- Manifest sha256: `3d72b8ea7281aa9f0746b02399de5f91482b59ede0ec2eb60db16c8688725c99`
- Crontab pins: `9040c75e=11`, old `e4fb5c7f=0`
- No service restart, no engine rebuild, no cron invocation, no order path

## Evidence

- Read-only governance snapshot: `/tmp/openclaw/runtime_guardian_normal_snapshot_20260627T074300Z_contract/runtime_governance_snapshot.json`
  - sha256 `034132e387c44e5926989a83f41bf122f72668c500548a0ab774e5ffcb289943`
  - Guardian `NORMAL`, multiplier `1.0`, `lease_live_count=0`, `list_leases=[]`
- Current-cap sizing proposal: `/tmp/openclaw/runtime_guardian_normal_current_cap_evidence_20260627T074329Z/current_cap_sizing/current_candidate_guardian_adjusted_sizing_proposal.json`
  - sha256 `59d8e8b75d810d8c5f78a537ca4c36c56c39a9556ea3bb0e97b108e5b2211229`
  - status `CURRENT_CANDIDATE_GUARDIAN_ADJUSTED_SIZING_PROPOSAL_READY_NO_ORDER`
  - effective cap `955.24342626 USDT`
  - proposed `145.7 AVAX / 954.6264 USDT`
  - `requires_fresh_bbo_before_admission=true`
- Final no-order gate: `/tmp/openclaw/runtime_guardian_normal_current_cap_evidence_20260627T074329Z/gate_with_current_cap_sizing/current_candidate_decision_lease_guardian_gate_evidence.json`
  - sha256 `b9e730a3bc1ebc79c632eed7b2e5ec4b5669d2b775ca5e655651a8e9ed6a586b`
  - Guardian gate passes
  - remaining runtime blocker: `decision_lease_valid`
- Session state: `/tmp/openclaw/session_loop_state_20260627T0745Z_guardian_normal_current_cap_sizing/session_loop_state.json`
  - sha256 `e6e5bbf668574b1f5f593c3f2d2d267feeee122d16f8e3da364cf179ccacddb8`

## Verification

- Local focused/related tests: `36 passed`
- Runtime focused/related tests: `36 passed`
- Local/runtime `py_compile`: passed
- Local/runtime `git diff --check`: passed

## Boundary

No Decision Lease acquire/release, no fresh actual-admission BBO, no order/cancel/modify, no Bybit private/order call, no PG write, no service restart, no Cost Gate lowering, no risk expansion, no writer/adapter enablement, no live/mainnet authority, no execution, and no profit proof.

## Next

Recompute fresh current-candidate envelope/BBO inside the final no-order admission window, then acquire a fresh bounded Demo Decision Lease and rerun gate evidence inside that same window. Do not execute until all gates clear.

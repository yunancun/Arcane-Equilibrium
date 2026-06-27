State transition: `BLOCKED_BY_LOSS_CONTROL`.

GUI/Rust risk settings remain authoritative. Fresh equity is `9551.58809495`, so GUI `10.0%` resolves to `955.1588095 USDT`, not `10 USDT`; GUI max-single-position `25%` resolves to `2387.89702374 USDT`.

Fresh AVAX Sell public quote/construction succeeded with BBO age `478.308ms`. Sizing was reduced to `101.8 AVAX / 668.1134 USDT` under Guardian-adjusted cap `668.61116665 USDT`, but the final gate still blocks because Guardian is `CAUTIOUS` after reconciler drift and there is no active current-candidate Decision Lease.

Key artifacts:

- Governance snapshot: `/tmp/openclaw/current_candidate_final_window_governance_snapshot_20260627T080216Z/runtime_governance_snapshot.json`
- Final gate: `/tmp/openclaw/current_candidate_final_window_gate_with_sizing_20260627T080300Z/current_candidate_decision_lease_guardian_gate_evidence.json`
- Diagnosis: `/tmp/openclaw/current_candidate_final_window_guardian_reconciler_diagnosis_20260627T080325Z/current_candidate_guardian_reconciler_drift_diagnosis.json`
- Session state: `/tmp/openclaw/session_loop_state_20260627T0804Z_final_window_guardian_cautious_blocked/session_loop_state.json`

Boundary: no Decision Lease acquire/release, no order, no private Bybit/order call, no PG write, no Cost Gate lowering, no risk expansion, no live/mainnet authority, and no profit proof.

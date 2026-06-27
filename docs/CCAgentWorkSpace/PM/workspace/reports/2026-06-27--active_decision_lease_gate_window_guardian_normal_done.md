# Active Decision Lease Gate Window Guardian NORMAL Done

Generated: 2026-06-27

## Result

State transition: `DONE_WITH_CONCERNS`.

The operator correction is binding: GUI/Rust RiskConfig is source of truth. GUI `P1 Risk/Trade=10.0%` is Rust `per_trade_risk_pct=0.1`, not a fixed `10 USDT` order cap. GUI `Max Single Position=25%` is `position_size_max_pct=25.0`. With accepted Demo equity `9551.58809495`, the current GUI per-trade cap is `955.1588095 USDT` and the max-single-position budget is `2387.89702374 USDT`.

## Evidence

- Fresh governance snapshot: `/tmp/openclaw/current_candidate_followup_governance_snapshot_20260627T081842Z/runtime_governance_snapshot.json`, sha `7ac2439134f73e406fe261a1a2a6c250078c2924c6b85cb4b4d98ddcc6aa8139`, Guardian `NORMAL`, multiplier `1.0`, `lease_live_count=0`.
- Gate without sizing: `/tmp/openclaw/current_candidate_followup_gate_without_sizing_20260627T081842Z/current_candidate_decision_lease_guardian_gate_evidence.json`, sha `58ec18b1ec373de2efb6693f206aa1585752e455f2482d973ef634a8a3a8e78e`, Guardian pass, blocked only by missing Decision Lease.
- Normal sizing: `/tmp/openclaw/current_candidate_followup_guardian_normal_sizing_20260627T081842Z/current_candidate_guardian_adjusted_sizing_proposal.json`, sha `3011fb95827d6c038b5230a58e56977e76ae0b4815fb21b6de0cac5d0861a06b`, proposed `145.5 AVAX / 954.9165 USDT`, effective cap `955.1588095 USDT`.
- Gate with sizing: `/tmp/openclaw/current_candidate_followup_gate_with_normal_sizing_20260627T081842Z/current_candidate_decision_lease_guardian_gate_evidence.json`, sha `07ba7560ec0d8831a45fd081177cd7dfafd79608a72b05bf725ae61bc249d174`, Guardian pass, blocked only by missing Decision Lease.
- Active lease window: `/tmp/openclaw/current_candidate_followup_active_lease_gate_window_20260627T081842Z/current_candidate_active_decision_lease_gate_window.json`, sha `c562665f41db188d1da3c58b71684dc5aaa45310c61ba7ca95ef6746e4061188`, status `CURRENT_CANDIDATE_ACTIVE_DECISION_LEASE_GATE_WINDOW_DONE_NO_ORDER`.
- Nested active gate evidence: `/tmp/openclaw/current_candidate_followup_active_lease_gate_window_20260627T081842Z/active_current_candidate_decision_lease_guardian_gate_evidence.json`, sha `a67e25c3f61d8bc2ce7a23ed8357a35328aeac66ddaddd5c8570550b34609d8e`, status `CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER`.
- Post-window governance snapshot: `/tmp/openclaw/current_candidate_followup_post_active_governance_snapshot_20260627T081843Z/runtime_governance_snapshot.json`, sha `71175768a9d400a59ccc680434b5ce92421fcfee3044dc519a276224b1bb5749`, Guardian `NORMAL`, `lease_live_count=0`.
- Session state: `/tmp/openclaw/session_loop_state_20260627T0819Z_active_decision_lease_gate_window_done/session_loop_state.json`, sha `f50cfafdd776bb28b212034fdafe5e7dd6ce1d0f3d6500c2d17e2723e201df26`, state `DONE_WITH_CONCERNS`.

## Boundary

No order, Bybit private/order call, PG write, service restart, Cost Gate lowering, risk expansion, live/mainnet authority, execution, or profit proof occurred. The only runtime mutation was the bounded short Demo governance lease acquire/release required to validate the active-window gate; post-window evidence shows no live lease remains.

## Next

Do not treat this as persistent runtime admission. The next no-order blocker is fresh actual-admission BBO/instrument refresh inside a fresh current-candidate Demo Decision Lease window, followed by admission/gate evidence in that same window.

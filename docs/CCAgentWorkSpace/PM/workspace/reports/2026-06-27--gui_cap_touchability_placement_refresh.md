# GUI Cap Touchability / Placement Refresh

| Field | Value |
|---|---|
| `blocker_id` | `P0-GUI-RISK-CAP-RESOLVER-CURRENT-CANDIDATE-DRIFT-RECONCILE` |
| `state_transition` | `DONE_WITH_CONCERNS` |
| `session_loop_state` | `/tmp/openclaw/session_loop_state_20260627T0324Z_gui_cap_touchability_placement_refresh.json` |
| `session_loop_state_sha256` | `63a972bb8b139dd6749716bfcedf8ff58752cc09355f615af4164ff4c0a41556` |
| `output_dir` | `/tmp/openclaw/gui_cap_touchability_placement_refresh_20260627T0324Z/` |

## Decision

The stale placement cap `10.0` has been replaced in the timestamped review chain. Placement now carries GUI/Rust RiskConfig lineage:

- `max_demo_notional_usdt_per_order=955.24342626`
- `cap_source=current_candidate_envelope.cap_resolution.resolved_cap_usdt`
- `risk_source_of_truth=GUI-backed Rust RiskConfig`
- `per_trade_risk_pct_fraction=0.1`
- `per_trade_risk_pct_display=10.0`
- `local_10_usdt_cap_is_global_risk_authority=false`

The bounded authorization packet is review-ready but still `decision=defer`. No bounded auth object, active probe authority, active order authority, plan inclusion, writer enablement, order, Cost Gate lowering, live authority, or profit proof was created.

## Inputs

- GUI-cap preflight: `/tmp/openclaw/current_candidate_standing_materialization_verification_20260627T025617Z/false_negative_bounded_probe_preflight_after_standing_materialization.json`, sha `ff69e4b591a3edd268152c10efd2c0804d80881e207297a061d837bf4f06c532`.
- Runtime order-to-fill gap snapshot copied from `trade-core:/tmp/openclaw/demo_order_to_fill_gap/demo_order_to_fill_gap_latest.json`, sha `e623250009110e82c4c558e36461e6f699f1a0c305083b8294a640b4926dd99e`.
- Runtime standing envelope snapshot copied from `trade-core:/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`, sha `42fca4b3e4bd1143dd8550bb4f36ff85774eed7a3b8acbf3ae99243d2a49d520`.

## Outputs

- Touchability: `bounded_probe_touchability_preflight_gui_cap.json`, sha `984334b6a249e4308ce96c9e7c1cfd1e30af13492804d1ae0397936ebfa340fc`, status `FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED`.
- Placement: `bounded_probe_placement_repair_plan_gui_cap.json`, sha `ad9de43c963b9f74e32974b9508b2bcb1e38b0f3884b1f35e74cdbe7b5c9d639`, status `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`.
- Readiness: `bounded_probe_authority_patch_readiness_gui_cap.json`, sha `8d280c7f976254686a684910fb788c8db09c2817f1f8239edc6e0e91134944d5`, status `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`.
- Bounded auth defer: `bounded_probe_operator_authorization_defer_gui_cap.json`, sha `0a7a416450c72b878c8245f4b440f42def7d3da6a9d8e7aa30d457ea8f75e6e3`, status `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, decision `defer`, `blocking_gates=[]`.

## Verification

- Artifact invariant checks: pass.
- Focused Python suite: `89 passed`.
- GUI risk gate in bounded auth: `gui_risk_notional_limit_valid=true`; expected, preflight, placement, and standing caps all equal `955.24342626 USDT`.

## Boundary

This was a no-order artifact refresh. Linux canonical `_latest` artifacts were not overwritten. No Bybit private call, PG write, runtime mutation, env/crontab change, service restart, adapter/writer enablement, bounded auth object, Decision Lease, Guardian/Rust admission, order, Cost Gate change, live/mainnet authority, or profit proof occurred.

## Next

Open a separate PM -> E3 -> BB review for whether to emit a scoped bounded auth object from the valid current AVAX standing Demo authorization. Even if that object is emitted, execution remains blocked until Decision Lease, Guardian risk gate, Rust authority runtime admission, fresh BBO at actual admission, auditability, reconstructability, and no Cost Gate/risk expansion all pass.

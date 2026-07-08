# Cost Gate False-Negative Bounded Demo Probe Preflight

- Generated: `2026-07-08T12:15:09.634991+00:00`
- Status: `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`
- Side-cell: `ma_crossover|NEARUSDT|Buy`
- Symbol: `NEARUSDT`
- Side: `Buy`
- Horizon minutes: `60`
- Ready for bounded authorization review: `True`
- Probe authority granted: `False`
- Order authority granted: `False`
- Boundary: artifact-only false-negative bounded Demo probe preflight; no PG query/write, Bybit call, order, config, risk, auth, runtime mutation, global Cost Gate lowering, probe authority, order authority, or promotion proof.

## Gates

| gate | passed | status | reason |
|---|---:|---|---|
| authority_boundary_preserved | `True` | `PRESERVED` | inputs must not grant Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof |
| standing_demo_authorization_valid_for_preflight | `True` | `VALID` | standing-sourced false-negative preflight approval must carry the same fresh Demo-only scoped loss-control envelope |
| gui_risk_cap_lineage_valid_for_preflight | `True` | `VALID` | approved bounded Demo probe preflight must source per-order notional from GUI-backed Rust RiskConfig, not a local 10 USDT diagnostic cap |
| autonomous_parameter_proposal_ready | `True` | `REVIEWABLE_PARAMETER_PROPOSAL_READY` | proposal must be an inactive no-authority review packet |
| false_negative_operator_review_present | `True` | `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT` | false-negative review artifact must be fresh and no-authority |
| candidate_alignment | `True` | `ALIGNED` | proposal and false-negative operator review must name the same side-cell/horizon |
| false_negative_operator_review_approved_for_preflight | `True` | `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT` | operator review must approve candidate preflight without granting runtime authority |

## Next Actions

- `run_candidate_matched_touchability_preflight`
- `build_or_refresh_near_touch_or_skip_placement_review`
- `then_operator_may_authorize_bounded_demo_probe_with_exact_typed_confirm`

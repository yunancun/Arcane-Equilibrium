# Bounded Demo Probe Operator Authorization

- Generated: `2026-07-08T10:11:24.709497+00:00`
- Status: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`
- Decision: `defer`
- Operator: `profit-first-fast-demo-loop`
- Authorization id: `None`
- Confirmation source: `None`
- Side-cell: `ma_crossover|NEARUSDT|Buy`
- Max authorized probe orders: `None`
- Expires at: `None`
- Boundary: artifact-only bounded Demo probe operator authorization review; no plan mutation, writer enablement, PG query/write, Bybit call, order, config, risk, runtime mutation, main Cost Gate lowering, or promotion proof

## Authorization Phrase

`NOT_AVAILABLE_UNTIL_AUTHORIZATION_FIELDS_AND_PREFLIGHT_READY`

- Template: `authorize_bounded_demo_probe:ma_crossover|NEARUSDT|Buy:<max_authorized_probe_orders<=2>:<authorization_id>`
- Readiness: `MISSING_AUTHORIZATION_FIELDS`

## Standing Demo Authorization

- Present: `True`
- Valid: `True`
- Standing authorization id: `standing-demo-loss-control-20260708T100636Z-6adb99b5d0fb`
- Demo only: `True`
- Candidate scoping required: `True`

## Gates

| gate | passed | status | reason |
|---|---:|---|---|
| authority_boundary_preserved | `True` | `PRESERVED` | inputs must not already grant Cost Gate lowering, probe/order authority, or promotion proof |
| false_negative_preflight_ready | `True` | `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION` | false-negative preflight must reach READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION after operator review |
| standing_demo_authorization_safe | `True` | `SAFE` | standing Demo authorization input must not carry live, runtime, Cost Gate, or promotion authority |
| standing_demo_authorization_valid_for_candidate_scope | `True` | `VALID` | supplied standing Demo authorization must be valid for the candidate-scoped bounded authorization review |
| gui_risk_notional_limit_valid | `True` | `VALID` | preflight and placement per-order notional caps must match GUI-backed Rust RiskConfig cap lineage; a local 10 USDT diagnostic cap is not authorization-grade risk control |
| placement_repair_plan_ready | `True` | `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW` | placement repair plan must be fresh and near-touch-or-skip ready |
| authority_path_patch_readiness_ready | `True` | `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW` | source readiness must confirm near-touch Adapter and authority-path wiring |
| candidate_alignment | `True` | `ALIGNED` | preflight, placement plan, and source readiness must name the same side-cell/horizon |
| authorization_id_present | `True` | `MISSING` | authorization requires a durable authorization id |
| operator_id_present | `True` | `PRESENT` | authorization requires a non-empty operator id |
| standing_demo_operator_matches | `True` | `MATCH` | explicit operator id must match the standing Demo authorization operator id |
| probe_budget_valid | `True` | `MISSING_OR_EXCEEDS_SOURCE_LIMIT` | authorized probe orders must be positive and no larger than the source plan budget |
| authorization_expiry_valid | `True` | `MISSING_OR_INVALID` | authorization expiry must be future-dated and within the allowed TTL cap |
| typed_confirm_matches | `True` | `MISSING_OR_MISMATCH` | authorization requires either the exact typed confirmation phrase or a fresh standing Demo-only authorization that still scopes the emitted object to one candidate |

## Next Actions

- `operator_may_authorize_bounded_demo_probe_with_exact_typed_confirm`
- `do_not_edit_plan_or_enable_writer_until_authorization_artifact_is_reviewed`

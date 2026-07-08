# Bounded Probe Operator Authorization Readiness

Status: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`
Decision: `defer`
Reason: `defer`

## Candidate

```json
{
  "outcome_horizon_minutes": 60,
  "side": "Buy",
  "side_cell_key": "ma_crossover|NEARUSDT|Buy",
  "strategy_name": "ma_crossover",
  "symbol": "NEARUSDT"
}
```

## No-Authority Answers

- `active_runtime_order_authority`: `False`
- `active_runtime_probe_authority`: `False`
- `authorization_confirmation_source`: `None`
- `bounded_demo_probe_authorized`: `False`
- `global_cost_gate_lowering_recommended`: `False`
- `main_cost_gate_adjustment`: `NONE`
- `operator_authorization_object_emitted`: `False`
- `order_authority_granted_in_authorization_object`: `False`
- `order_submission_performed`: `False`
- `plan_mutation_performed`: `False`
- `probe_authority_granted_in_authorization_object`: `False`
- `promotion_evidence`: `False`
- `ready_for_operator_authorization_review`: `True`
- `runtime_mutation_performed`: `False`
- `standing_demo_authorization_present`: `True`
- `standing_demo_authorization_valid`: `False`
- `writer_enabled`: `False`

## Blocking Gates

```json
[]
```

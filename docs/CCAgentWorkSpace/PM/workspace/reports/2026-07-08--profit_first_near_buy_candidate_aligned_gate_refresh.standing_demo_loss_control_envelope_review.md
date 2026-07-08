# Standing Demo Loss-Control Envelope Review

- Generated: `2026-07-08T10:06:36.797731+00:00`
- Status: `STANDING_DEMO_LOSS_CONTROL_ENVELOPE_REVIEW_READY_NO_RUNTIME_MUTATION`
- Reason: `standing_demo_loss_control_envelope_review_ready`
- Side-cell: `ma_crossover|NEARUSDT|Buy`
- Runtime envelope path: `/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json`
- Env var: `OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON`
- Boundary: source-only standing Demo loss-control envelope materialization review; no runtime file write, env or crontab mutation, PG query/write, Bybit call, order, cancel, service restart, risk mutation, Cost Gate lowering, probe authority, order authority, live authority, promotion proof, or profit proof.

## Gates

| gate | passed | status | reason |
|---|---:|---|---|
| authority_boundary_preserved | `True` | `PRESERVED` | source packet and candidate rows must not contain runtime/order/live authority, Cost Gate lowering, env/crontab/runtime mutation, or proof |
| materialization_path_valid | `True` | `VALID` | materialization_path_valid |
| materialization_env_var_valid | `True` | `VALID` | standing_authorization_env_var_valid |
| loss_control_limits_valid | `True` | `VALID` | loss_control_limits_valid |
| operator_id_present | `True` | `PRESENT` | standing Demo envelope preview requires auditable operator id |
| false_negative_candidate_packet_ready | `True` | `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW` | candidate packet must be fresh, schema-valid, ready for operator review, and no-authority |
| candidate_selected | `True` | `SELECTED` | review must bind to exactly one ranked false-negative side-cell |
| candidate_reviewable | `True` | `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE` | selected candidate must remain false_negative_after_cost and no-authority |
| candidate_scope_complete | `True` | `COMPLETE` | standing envelope must be candidate-scoped by side-cell, strategy, symbol, side, and horizon |
| gui_risk_cap_lineage_valid | `True` | `VALID` | standing envelope preview must carry GUI-backed Rust RiskConfig cap lineage; local 10 USDT diagnostics cannot define per-order risk |
| standing_demo_authorization_preview_valid | `True` | `VALID` | generated preview must pass standing_demo_operator_authorization_v1 validator for the selected candidate |

## Materialization Plan

```json
{
  "candidate_scope_policy": {
    "candidate_scope": {
      "outcome_horizon_minutes": 60,
      "side": "Buy",
      "side_cell_key": "ma_crossover|NEARUSDT|Buy",
      "strategy_name": "ma_crossover",
      "symbol": "NEARUSDT"
    },
    "candidate_scope_mismatch_policy": "fail_closed_no_review_approval",
    "candidate_scoping_required": true,
    "cross_candidate_reuse_allowed": false
  },
  "future_apply_steps_require_e3_review": [
    "write the reviewed standing_demo_operator_authorization_v1 JSON atomically with mode 0600 at proposed_runtime_envelope_path",
    "add only the proposed_env_assignment to the cost_gate_learning_lane_cron crontab line or reviewed runtime env wrapper",
    "do not set OPENCLAW_COST_GATE_BOUNDED_PROBE_OPERATOR_AUTHORIZATION_DECISION=authorize",
    "refresh false_negative_operator_review and false_negative_bounded_probe_preflight artifacts and verify no probe/order authority is emitted"
  ],
  "loss_control_envelope": {
    "authorization_ttl_hours": 12,
    "demo_only": true,
    "hard_max_authorized_probe_orders_per_candidate": 3,
    "max_authorization_ttl_hours": 24,
    "max_authorized_probe_orders_per_candidate": 2,
    "scheduled_bounded_probe_operator_authorization_decision_must_remain": "defer"
  },
  "proposed_env_assignment": "OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON=/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json",
  "proposed_env_scope": "cost_gate_learning_lane_cron_only; alpha_discovery_throughput_cron will observe this same path only through its documented fallback when OPENCLAW_ALPHA_STANDING_DEMO_AUTHORIZATION_JSON is unset",
  "proposed_env_var": "OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON",
  "proposed_runtime_envelope_path": "/tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json",
  "rollback_plan": [
    "remove OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON from the cost_gate_learning_lane_cron crontab/env wiring",
    "move or delete /tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json after recording sha256 and review id",
    "verify crontab/env no longer contains OPENCLAW_COST_GATE_STANDING_DEMO_AUTHORIZATION_JSON",
    "refresh natural scheduled artifacts with default defer and confirm they fail closed or remain no-authority"
  ],
  "rollback_verification_expected": {
    "active_runtime_order_authority": false,
    "active_runtime_probe_authority": false,
    "bounded_demo_probe_authorized": false,
    "operator_authorization_object_emitted": false,
    "order_submission_performed": false,
    "standing_env_configured": false
  },
  "runtime_mutation_performed_by_this_helper": false,
  "source_only_review": true,
  "standing_envelope_materialized_by_this_helper": false,
  "validation_commands": [
    "PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.false_negative_operator_review --false-negative-candidate-packet-json /tmp/openclaw/cost_gate_learning_lane/false_negative_candidate_packet_latest.json --standing-demo-authorization-json /tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json --selected-side-cell-key 'ma_crossover|NEARUSDT|Buy' --decision defer --max-authorization-ttl-hours 24 --print-json",
    "PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.false_negative_bounded_probe_preflight --autonomous-parameter-proposal-json /tmp/openclaw/cost_gate_learning_lane/autonomous_parameter_proposal_latest.json --false-negative-operator-review-json /tmp/openclaw/cost_gate_learning_lane/false_negative_operator_review_latest.json --standing-demo-authorization-json /tmp/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json --print-json"
  ]
}
```

## Envelope Preview

```json
{
  "answers": {
    "active_runtime_order_authority": false,
    "active_runtime_probe_authority": false,
    "bounded_demo_probe_authorized": false,
    "candidate_scoping_required": true,
    "crontab_mutation_performed": false,
    "demo_only": true,
    "env_mutation_performed": false,
    "global_cost_gate_lowering_recommended": false,
    "live_authority_granted": false,
    "main_cost_gate_adjustment": "NONE",
    "operator_authorization_object_emitted": false,
    "order_authority_granted": false,
    "order_submission_performed": false,
    "probe_authority_granted": false,
    "promotion_evidence": false,
    "promotion_proof": false,
    "runtime_mutation_performed": false
  },
  "candidate": {
    "outcome_horizon_minutes": 60,
    "side": "Buy",
    "side_cell_key": "ma_crossover|NEARUSDT|Buy",
    "strategy_name": "ma_crossover",
    "symbol": "NEARUSDT"
  },
  "candidate_scoping_required": true,
  "demo_only": true,
  "environment": "demo",
  "expires_at_utc": "2026-07-08T22:06:36.797731+00:00",
  "generated_at_utc": "2026-07-08T10:06:36.797731+00:00",
  "max_authorized_probe_orders_per_candidate": 2,
  "operator_id": "profit-first-fast-demo-loop",
  "risk_cap_lineage": {
    "account_equity_usdt": 9544.67467679,
    "bounded_probe_local_cap_usdt_is_authority": false,
    "cap_source": "standing_demo_loss_control_envelope_review.gui_risk_config_plus_demo_equity",
    "local_10_usdt_cap_is_global_risk_authority": false,
    "per_trade_risk_pct_display": 10.0,
    "per_trade_risk_pct_fraction": 0.1,
    "position_size_max_pct": 25.0,
    "resolved_cap_usdt": 954.46746768,
    "risk_source_of_truth": "GUI-backed Rust RiskConfig",
    "rounded_notional_usdt": null,
    "single_position_budget_usdt": 2386.1686692,
    "valid": true
  },
  "schema_version": "standing_demo_operator_authorization_v1",
  "scope": "demo_api_only_bounded_probe",
  "standing_authorization_id": "standing-demo-loss-control-20260708T100636Z-6adb99b5d0fb",
  "status": "STANDING_DEMO_AUTHORIZATION_ACTIVE"
}
```

## No-Authority Answers

- `source_only_research_artifact`: `True`
- `review_ready_no_runtime_mutation`: `True`
- `runtime_mutation_performed`: `False`
- `env_mutation_performed`: `False`
- `crontab_mutation_performed`: `False`
- `standing_envelope_materialized`: `False`
- `standing_demo_authorization_valid`: `True`
- `standing_demo_authorization_consumed`: `False`
- `operator_authorization_object_emitted`: `False`
- `bounded_demo_probe_authorized`: `False`
- `active_runtime_probe_authority`: `False`
- `active_runtime_order_authority`: `False`
- `review_grants_runtime_authority`: `False`
- `global_cost_gate_lowering_recommended`: `False`
- `main_cost_gate_adjustment`: `NONE`
- `probe_authority_granted`: `False`
- `order_authority_granted`: `False`
- `live_authority_granted`: `False`
- `mainnet_authority_granted`: `False`
- `order_submission_performed`: `False`
- `pg_query_performed`: `False`
- `pg_write_performed`: `False`
- `bybit_call_performed`: `False`
- `promotion_evidence`: `False`
- `promotion_proof`: `False`
- `profit_proof`: `False`

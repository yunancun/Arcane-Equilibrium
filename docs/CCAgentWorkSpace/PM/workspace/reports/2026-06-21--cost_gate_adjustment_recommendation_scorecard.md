# Cost Gate Adjustment Recommendation Scorecard

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime still unsynced

## Finding

We had enough pieces to see the situation:

- fresh Cost Gate rejects can be present
- demo orders/fills can still be absent
- blocked-outcome review can eventually justify operator review

But the composite evidence did not directly answer the operator question:

```text
Should we lower Cost Gate?
```

That left the answer implicit in counts and blocker names.

## Change

`demo_learning_evidence_audit.py` now emits a
`cost_gate_adjustment_recommendation` object.

The recommendation always keeps:

```text
main_cost_gate_adjustment = NONE
global_cost_gate_lowering_recommended = false
order_authority = NOT_GRANTED
```

It separates bounded alternatives:

- `BOUNDED_LEARNING_LANE_ACTIVATION_RECOMMENDED`
- `BOUNDED_DEMO_PROBE_AUTHORITY_REVIEW_READY`
- `ORDER_TO_FILL_DIAGNOSIS_BEFORE_COST_GATE_CHANGE`
- `RESTORE_DATA_FLOW_BEFORE_ANY_COST_GATE_CHANGE`
- `CONTINUE_BOUNDED_LEARNING_NO_COST_GATE_CHANGE`
- `NO_COST_GATE_ADJUSTMENT_RECOMMENDED`

Alpha-discovery now carries the recommendation fields into cost-gate blocker
rows, including the proposed `learning_gate_adjustment`.

## Verification

- `python3 -m pytest helper_scripts/db/audit/test_demo_learning_evidence_audit.py -q` -> `8 passed`
- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `43 passed`
- `python3 -m py_compile helper_scripts/db/audit/demo_learning_evidence_audit.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`

## Boundary

No runtime source sync, artifact refresh, crontab edit/install, env edit,
deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading
call, credential/auth/risk/order/strategy mutation, order authority, Cost Gate
lowering, execution proof, or promotion proof.

## PM Read

This is the current disciplined answer to the Cost Gate question:

- do **not** globally lower the main Cost Gate from source evidence alone
- do make the bounded learning path explicit
- require operator review before any bounded demo probe authority
- keep every recommendation machine-checkable and reversible

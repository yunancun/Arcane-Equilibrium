# Cost Gate Recommendation Runtime Preflight Gate

Date: 2026-06-21
Role: PM local implementation checkpoint
Status: source/test/docs complete; runtime still unsynced

## Finding

v354 answered the operator's Cost Gate question, but one trust gap remained:
bounded learning/probe recommendations could be shown without carrying the
runtime source/writer readiness gate as part of the same recommendation object.

That is dangerous because the current runtime blocker is still source trust:
`trade-core` is behind/dirty and current runtime alpha artifacts are old-schema
until source is synced and alpha-discovery reruns.

## Change

`demo_learning_evidence_audit.py` now derives runtime readiness from
`cost_gate_learning_preflight` before recommending any bounded path.

Hard blockers now produce explicit statuses:

- `RUNTIME_SOURCE_SYNC_REQUIRED_BEFORE_COST_GATE_CHANGE`
- `RUNTIME_WRITER_ENABLEMENT_REQUIRED_BEFORE_BOUNDED_LEARNING_LANE`
- `RUNNING_ENGINE_WRITER_ENABLEMENT_REQUIRED_BEFORE_BOUNDED_LEARNING_LANE`
- `RUNTIME_PREFLIGHT_REQUIRED_BEFORE_BOUNDED_LEARNING_LANE`

Composite classification follows these blockers as:

```text
RUNTIME_PREFLIGHT_BLOCKS_COST_GATE_LEARNING_ADJUSTMENT
```

The invariant remains unchanged:

```text
main_cost_gate_adjustment = NONE
global_cost_gate_lowering_recommended = false
order_authority = NOT_GRANTED
```

Alpha-discovery now carries runtime preflight/source/writer fields into the
cost-gate blocker rows, so the next trigger can be source sync or writer
enablement rather than Cost Gate relaxation.

## Verification

- `python3 -m py_compile helper_scripts/db/audit/demo_learning_evidence_audit.py helper_scripts/db/audit/test_demo_learning_evidence_audit.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`
- `python3 -m pytest helper_scripts/db/audit/test_demo_order_stall_audit.py helper_scripts/db/audit/test_demo_learning_evidence_audit.py helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `66 passed`

`python3 -m black ...` was attempted but local `black` is not installed.

## Boundary

No runtime source sync, artifact refresh, crontab edit/install, env edit,
deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading
call, credential/auth/risk/order/strategy mutation, order authority, Cost Gate
lowering, execution proof, or promotion proof.

## PM Read

This closes the immediate "do not misread recommendation as permission" gap.
The next real engineering step is still runtime source reconcile/sync and then
bounded learning-lane activation preflight, not global Cost Gate lowering.

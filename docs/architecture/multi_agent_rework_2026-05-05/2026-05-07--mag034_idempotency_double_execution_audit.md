# MAG-034 Idempotency and Double-Execution Audit

Date: 2026-05-07
Status: DONE
Scope: AgentTodo M3 Agent Decision Spine Shadow

## Verdict

APPROVED for shadow integration.

Every execution candidate in the current Agent Spine surface carries both
lineage and duplicate-submit identifiers:

- `decision_id`
- `order_plan_id`
- `idempotency_key`
- `engine_mode`

The durable store, Rust event surface, and Python client now have explicit
source-level checks that reserve an execution key before a plan can be treated
as the execution candidate for downstream integration.

## Audited Surfaces

| Surface | Evidence | Result |
|---|---|---|
| DB V064 | `agent.execution_idempotency_keys` primary key on `idempotency_key`; unique `(order_plan_id, engine_mode)`; unique `(decision_id, order_plan_id, engine_mode)` | Duplicate plan/decision reservations are rejected by schema. |
| DB V064 | `agent.decision_objects` unique execution plan index on `order_plan_id` | A plan object cannot be duplicated under a different object id. |
| Rust contracts | `ExecutionPlan` requires `order_plan_id`, `decision_id`, and `idempotency_key` | Rust execution candidates have stable lineage and dedupe ids. |
| Rust events | `ExecutionIdempotencyKey::reserved(&ExecutionPlan, ts)` copies plan idempotency, plan id, decision id, and mode | Reservation rows cannot silently detach from the plan they guard. |
| Rust writer | `flush_execution_idempotency_keys` inserts the reservation with `ON CONFLICT (idempotency_key) DO NOTHING` | Duplicate key writes are idempotent in the fail-soft writer. |
| Python contracts | `ExecutionPlan` and `ExecutionReport` reject missing lineage ids | Python-side agents cannot publish untraceable execution candidates through the typed models. |
| Python client | `publish_execution_plan(..., reserve_idempotency=True)` writes object, edge, then `execution_idempotency_keys` reservation | Shadow integration has a default idempotency reservation path. |

## Double-Execution Boundary

MAG-034 does not claim live duplicate-submit enforcement is active. The Agent
Spine writer remains default-disabled and is not wired into engine startup.
Current protection is source-level and schema-level:

1. a plan has exactly one `order_plan_id`;
2. the execution reservation has exactly one `idempotency_key`;
3. the same `order_plan_id` cannot be reserved twice for the same mode;
4. the same `decision_id` + `order_plan_id` cannot be reserved twice for the
   same mode;
5. reports must carry the same `decision_id` and `order_plan_id` lineage.

MAG-035 shadow integration must preserve `reserve_idempotency=True`. Any future
primary/canary path must fail closed if an `ExecutionPlan` lacks `decision_id`,
`order_plan_id`, or `idempotency_key`.

## Residual Risk

- No production migration apply was performed.
- No DB runtime write was performed.
- No engine rebuild, restart, deploy, flag flip, or trading authority change was
  performed.
- Live duplicate-submit prevention still depends on later wiring and Decision
  Lease enforcement; MAG-034 only closes the shadow spine audit gate.

## Verification Additions

- Python test now rejects missing execution lineage/deduplication identifiers.
- Rust test now asserts idempotency reservation fields are copied from
  `ExecutionPlan`.
- Static V064 migration test now checks non-null idempotency columns and unique
  constraints.

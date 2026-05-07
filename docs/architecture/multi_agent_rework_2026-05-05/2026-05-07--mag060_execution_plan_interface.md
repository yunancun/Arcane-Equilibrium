# MAG-060 ExecutionPlan Interface and Order Styles

Date: 2026-05-07
Status: DONE contract + shadow-client guard
Scope: AgentTodo M6 Executor Planner
Owner: PA / PM local synthesis

## Verdict

APPROVED as the implementation contract for MAG-061 through MAG-064.

Executor may optimize execution quality, but it must not choose the tactical
trade. `ExecutionPlan.symbol`, `ExecutionPlan.direction`, `strategy`, and
`engine_mode` must match a durable `StrategistDecision` and a matching
approved or modified `GuardianVerdict` before the plan can be published.

## Authority Boundary

Executor may:

- choose an execution style inside the approved decision/verdict scope;
- set urgency, max slippage, maker preference, local stop handoff, and
  anti-hunt stop policy;
- request a Decision Lease scope and TTL;
- reserve execution idempotency before submit.

Executor may not:

- choose a new symbol, direction, strategy, or thesis;
- turn `hold` / `no_action` into an execution plan;
- turn scanner decay into a direct close without a PositionReview-derived
  tactical decision and Guardian verdict;
- submit a real order without Decision Lease binding;
- bypass Rust execution authority.

## ExecutionPlan Fields

Python and Rust contracts now expose the MAG-060 interface:

| Field | Meaning |
|---|---|
| `order_plan_id` | durable plan id and idempotency parent |
| `decision_id` | required StrategistDecision parent |
| `verdict_id` / `verdict_version` | exact GuardianVerdict parent |
| `symbol` / `direction` | copied from StrategistDecision, not chosen by Executor |
| `symbol_source` / `direction_source` | must be `strategist_decision` |
| `qty` | execution quantity after Guardian P2 modifications |
| `reduce_only` | true only for `close_long` / `close_short` directions |
| `order_style` | high-level execution style |
| `urgency` | `low`, `normal`, `high`, or `urgent` |
| `max_slippage_bps` | execution-quality tolerance, not risk approval |
| `maker_preference` | `none`, `prefer_maker`, `maker_only`, or `allow_taker` |
| `order_type` / `limit_price` / `time_in_force` | current Rust/Bybit-compatible order shape |
| `order_style_params` | schedule or split parameters for future TWAP/split |
| `local_stop_policy` | local stop handoff payload |
| `anti_hunt_stop_policy` | anti-hunt stop handoff payload |
| `lease_scope` / `lease_ttl_ms` | requested Decision Lease binding |
| `lease_id` | populated after MAG-062 lease acquisition |
| `idempotency_key` | duplicate-submit guard |

## Allowed Order Styles

`order_style` is the semantic contract. `order_type` and `time_in_force` remain
the compatibility bridge to existing Rust/Bybit execution code.

| Style | Required shape | Notes |
|---|---|---|
| `market` | `order_type=market`, no `limit_price`, no `time_in_force` | taker path; slippage cap must be enforced before real submit in MAG-061/062 |
| `limit` | `order_type=limit`, positive `limit_price`, no `PostOnly` TIF | ordinary limit order; may allow taker if exchange crosses |
| `post_only` | `order_type=limit`, positive `limit_price`, `time_in_force=PostOnly` | maker-only path; `maker_preference=allow_taker` is invalid |
| `twap` | `order_type=market` or `limit`; limit TWAP needs positive `limit_price` | interface only in MAG-060; no scheduler is enabled yet |
| `split` | `order_type=market` or `limit`; limit split needs positive `limit_price` | interface only in MAG-060; no submit fanout is enabled yet |

Additional constraints:

- `maker_preference=maker_only` requires `order_style=post_only`.
- `reduce_only=true` requires `direction` to be `close_long` or `close_short`.
- `close_long` / `close_short` requires `reduce_only=true`.
- `qty` and `limit_price` must be positive when present.

## Publish Gate

`AgentSpineClient.publish_execution_plan()` now performs a fail-soft lineage
check before writing a plan object:

1. A matching `StrategistDecision` must exist in the client cache or durable
   spine store.
2. Plan symbol, direction, strategy, and engine mode must match that decision.
3. A matching approved or modified `GuardianVerdict` must exist.
4. Plan decision id, symbol, strategy, engine mode, and verdict version must
   match that verdict.
5. `hold` / `no_action` decisions cannot produce an execution plan.

In shadow mode, failed publish attempts increment client failure stats and do
not write `execution_plan` rows.

## Downstream Requirements

MAG-061 must build ExecutionPlan objects from approved/modified
StrategistDecision + GuardianVerdict lineage and apply Guardian P2 size/risk
modifications.

MAG-062 must bind the plan to Decision Lease before any real submit. Missing
lease on a real submit remains fail-closed.

MAG-063 must emit ExecutionReport quality metrics for Analyst.

MAG-064 must add regression coverage that Executor cannot change symbol or
direction relative to the approved decision.

## Boundary

No runtime wiring, order submit path, rebuild, restart, DB migration apply, DB
write, feature-flag flip, live auth mutation, trading mode change, or
strategy/risk runtime config change was performed.

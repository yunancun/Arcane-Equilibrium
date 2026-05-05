# MAG-002 Architecture Review - AgentTodo M0

Date: 2026-05-06
Role: FA(default)
Scope: Agent Decision Spine object lifecycle and persistence order
Repo root: `/Users/ncyu/Projects/TradeBot/srv`
Observed HEAD: `6b667daf`
Verdict: **CONDITIONAL**

## Executive Verdict

MAG-002 is **conditionally approved as an M0 architecture review**, not yet as an implementation-ready E1 contract.

The target canonical order is coherent and can be signed off as the required trading decision order:

`Scout/Scanner/StrategySignal evidence -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease -> Rust execution -> ExecutionReport -> AnalystInsight`

This sign-off is conditional because the current plan defines the correct object names and broad order, but does not yet define enough lifecycle, ownership, persistence, idempotency, scanner decay, and fail-closed behavior for implementation. E1 must not begin until the acceptance criteria in this report are folded into MAG-003/RFC/contracts.

H0 remains a hard factual precondition and protective interrupt around this chain. H0 may reject/pass or force protective risk handling; it must not generate trade ideas. Scanner output remains evidence/advisory only. Strategist owns open/hold/reduce/close/no_action trading intent. Guardian owns non-bypassable reject/modify/circuit authority. Rust remains the execution and enforcement engine, not a hidden decision authority.

## Current Implementation Findings

The plan is directionally aligned with the governance documents, but current implementation paths are not yet aligned with the proposed spine:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py` keeps `MessageBus` messages in memory with optional audit callback only. This does not satisfy durable `agent.messages` persistence.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/base_agent.py` records state/audit/LLM activity through local callbacks and cost tracking, but does not write authoritative `agent.state_changes` or `agent.ai_invocations` rows.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py` wires agent audit into GovernanceHub change audit, not into the agent event schema.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_edge_eval.py` currently produces `TradeIntent`, not a formal `StrategistDecision` with open/hold/reduce/close/no_action lifecycle.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/guardian_agent.py` emits approved intents over the bus and contains a TODO for intent_id dedup before production flow use.
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py` has only in-memory intent deduplication, no `ExecutionPlan`/`order_plan_id` lineage, and the Python Decision Lease path can fail open when GovernanceHub is missing.
- `sql/migrations/V003__trading_agent_tables.sql` defines `agent.messages`, `agent.ai_invocations`, and `agent.state_changes`, but production inserts are not present in the targeted paths.
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` still applies scanner/route gates directly before normal dispatch and can execute Rust-side strategy actions without the proposed Agent Decision Spine.
- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` also treats strategy closes as risk-reducing and skips Guardian/cost/Kelly/P1 review, which must be split into protective close versus tactical Strategist close/reduce.
- `rust/openclaw_engine/src/scanner/runner.rs` and `rust/openclaw_engine/src/scanner/registry.rs` retain active positions in scanner subscriptions, but do not produce a formal `OpportunityDecay` or `PositionReview` lifecycle event.

## Canonical Lifecycle Sign-Off

Conditional sign-off is granted for the following canonical lifecycle only:

1. Evidence is created by Scout, Scanner, or StrategySignal producers and persisted before Strategist consumption.
2. Strategist creates a persisted `StrategistDecision` for `open`, `hold`, `reduce`, `close`, or `no_action`.
3. Guardian reviews the persisted decision and creates a persisted `GuardianVerdict` of `approved`, `modified`, `rejected`, or `circuit_break`.
4. Executor creates an `ExecutionPlan` only from an approved or modified Guardian verdict.
5. Decision Lease is acquired against the approved plan before any real submit path.
6. Rust executes only the leased plan, validates the plan against H0/P0/P1/Guardian constraints, and records execution outcome.
7. `ExecutionReport` is persisted and linked back to the plan, lease, verdict, decision, and evidence.
8. Analyst consumes execution reports and persisted evidence to create labeled `AnalystInsight` records.

This lifecycle is not signed off if any real new-open path can bypass StrategistDecision, GuardianVerdict, ExecutionPlan, or Decision Lease. A protective H0/P0/P1 risk close may bypass Strategist tactical approval only if it is explicitly recorded as a protective decision edge and cannot open or increase exposure.

## Blocking Contract Gaps Before E1

These are not blockers to completing MAG-002 as a review, but they are blockers to E1 implementation.

### 1. Object State Transitions Are Missing

The plan must define allowed states, transitions, terminal states, parent IDs, and versioning for each spine object.

Minimum required state model:

- Evidence / StrategySignal: `observed`, `stale`, `superseded`, `invalidated`.
- StrategistDecision: `proposed`, `superseded`, `withdrawn`, `rejected_by_guardian`, `approved_by_guardian`, `planned`, `leased`, `executing`, `executed`, `failed`, `expired`, `cancelled`, `closed`, `analyzed`.
- GuardianVerdict: `approved`, `modified`, `rejected`, `circuit_break`, with verdict version and parent `decision_id`.
- ExecutionPlan: `drafted`, `lease_pending`, `lease_denied`, `leased`, `submitted`, `acknowledged`, `partially_filled`, `filled`, `rejected`, `cancelled`, `expired`.
- Decision Lease: `acquired`, `released_cancelled`, `released_consumed`, `expired`, `revoked`.
- ExecutionReport: `received`, `linked`, `quality_scored`.
- AnalystInsight: `proposed`, `consumed_by_strategist`, `consumed_by_guardian`, `archived`, `rejected`.

### 2. Store Ownership Is Ambiguous

AgentTodo still leaves storage authority unresolved: Rust-only authoritative with Python adapters, or DB-authoritative with Rust enforcement.

FA acceptance requires an explicit ownership table. The minimum coherent model is:

- DB is the durable audit and lineage ledger.
- Python agents own reasoning object production through adapter boundaries.
- Rust owns final execution enforcement and cannot treat unpersisted Python objects as authoritative.
- No object may advance to a side-effecting state unless the previous authoritative object is durably persisted and linked.
- Each table/state transition must have exactly one writer class and explicit updater permissions.

### 3. Idempotency And Double Execution Rules Are Insufficient

The plan mentions dedupe, but does not yet define durable idempotency keys or replay behavior across MessageBus, Python agent restart, Rust tick replay, and legacy command paths.

E1 must define:

- Deterministic or durable unique IDs for evidence/signal, `decision_id`, verdict version, `order_plan_id`, lease binding, and execution candidate.
- A unique rule allowing at most one real submitted order per `order_plan_id` per engine mode unless an explicit cancel/replace version exists.
- Guardian duplicate handling before bus production.
- Executor duplicate handling in durable storage, not only in-memory intent windows.
- Rust and Python paths using the same idempotency keys.

### 4. Persistence Order Is Not Explicit Enough

All authoritative spine objects must persist before downstream side effects:

- Evidence/signal before Strategist consumption.
- StrategistDecision before Guardian review.
- GuardianVerdict before ExecutionPlan creation.
- ExecutionPlan before lease acquisition.
- Lease ID and lease state before Rust submit.
- ExecutionReport before Analyst consumption.
- AnalystInsight before Strategist or Guardian can consume it as learning input.
- AI invocation row for every L1/L1.5/L2 call before or atomically with decision object finalization, including prompt hash, output hash, model/provider, latency, cost, success/failure, and linked object ID.

Failure to persist an authoritative object must fail closed or degrade to non-trading shadow behavior. Non-authoritative logging may fail soft only if healthchecks expose the gap.

### 5. Scanner Decay And Open-Position Review Lifecycle Are Under-Specified

Scanner lifecycle must be defined so scanner rank, churn, and route status cannot become hidden trading authority.

Required behavior:

- Scanner candidate removal, rank degradation, route degradation, or stale snapshot produces `OpportunityDecay` evidence.
- Open positions remain subscribed/reviewed independent of rank.
- If open-position discovery fails, scanner must fail visible and must not silently unsubscribe unknown open positions.
- `OpportunityDecay` may trigger Strategist `hold/reduce/close/no_action` review, but must not auto-close or directly block opens.
- Only hard facts such as delisting, impossible instrument state, missing market eligibility, or exchange hard invalidity may enter H0/Guardian hard rejection paths.

### 6. Fail-Closed Behavior And Healthcheck Visibility Are Incomplete

E1 must define healthchecks and failure gates for:

- Complete-chain ratio for every real order: evidence/signal, decision, verdict, plan, lease, execution report.
- Freshness and nonzero row counts for `agent.messages`, `agent.state_changes`, `agent.ai_invocations`, and decision/edge/insight tables.
- Orphan `StrategistDecision` without GuardianVerdict.
- Approved/modified GuardianVerdict without ExecutionPlan.
- ExecutionPlan stuck in lease pending/denied/submitted states.
- Any real submit when lease gate is disabled or lease ID is missing.
- Scanner decay events with no resulting review event.
- AI-backed decisions missing AI invocation records.
- Duplicate decision/order_plan replay attempts.

Existing fail-open audit bridge behavior is acceptable only for non-authoritative observability logs, not for spine object persistence.

### 7. Close/Reduce Semantics Need A Hard Split

The Rust pipeline currently treats strategy close as risk-reducing and bypasses Guardian/cost/Kelly/P1 checks. That is too broad for the target governance model.

E1 must distinguish:

- Protective H0/P0/P1/risk close: may bypass Strategist tactical approval, must be reduce-only, and must create protective decision/report lineage.
- Tactical Strategist reduce/close/hold: must pass StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease.

Without this split, Rust retains hidden close authority after cutover.

### 8. ExecutionPlan Authority Boundary Is Not Formalized

ExecutionPlan must be derived from the approved or modified GuardianVerdict. Executor may choose execution mechanics only, not symbol, direction, thesis, risk posture, or exposure increase.

Plan validation must reject any plan whose symbol, side, size, reduce-only flag, leverage, stop/take-profit envelope, or max slippage exceeds the Guardian-modified decision.

### 9. AnalystInsight Contract Needs Labels And Consumption State

Current analyst pattern records do not provide enough lineage for learning control.

E1 must require `AnalystInsight` to label each claim as fact, inference, hypothesis, or recommendation, link to source execution/evidence, and record whether Strategist or Guardian consumed it. Insight consumption must not become an untracked implicit strategy mutation.

### 10. Legacy And Fallback Paths Must Be Constrained

Any legacy Rust fallback after cutover must be either:

- Wrapped in the full Agent Decision Spine, or
- Protective/reduce-only with explicit protective lineage.

Fallback must never restore raw Rust new-open authority or scanner-driven trade authority.

## Required Acceptance Criteria Before E1 Implementation

E1 implementation may start only after these criteria are satisfied in MAG-003/RFC/contracts:

1. The canonical order is documented with hard preconditions, producer/consumer ownership, and permitted bypasses limited to protective reduce-only handling.
2. A contract table exists for every spine object: object ID, parent ID, allowed states, transitions, terminal states, persistence timing, writer, updater, and failure behavior.
3. DB schema/RFC defines durable lineage through `decision_edges` or equivalent: evidence/signal -> StrategistDecision -> GuardianVerdict -> ExecutionPlan -> Decision Lease -> ExecutionReport -> AnalystInsight.
4. Persistence-before-side-effect rule is explicit for all authoritative objects, with fail-closed behavior for write failures.
5. Durable idempotency keys and unique constraints are defined for decision, verdict version, order plan, lease binding, and execution submit.
6. Replay tests are specified for duplicate bus delivery, agent restart, Rust tick replay, and legacy command submission.
7. Scanner lifecycle is accepted: `OpportunityCandidate`, `OpportunityDecay`, `PositionReview`, no auto-close, no hidden scanner open gate, and conservative open-position subscription behavior.
8. H0/Guardian/protective close semantics are split and documented.
9. Healthcheck queries are specified for complete-chain ratio, orphan objects, zero-row agent tables, missing AI invocation links, missing lease IDs, scanner decay without review, and duplicate submit attempts.
10. Feature flag semantics are documented: scanner advisory mode means advisory-only enforcement, and any primary Agent Spine mode must fail closed on missing decision/verdict/plan/lease.
11. Executor contract states that it cannot choose symbol, direction, thesis, or exposure-increasing size, and must reject plans that exceed Guardian constraints.
12. AnalystInsight contract includes fact/inference/hypothesis/recommendation labels, source links, and consumption state.
13. Cutover/fallback behavior states that legacy raw Rust new-open authority is disabled after primary Agent Spine cutover.

## MAG-002 Acceptance Statement

FA accepts MAG-002 with **CONDITIONAL** verdict: the proposed Agent Decision Spine ordering is coherent and governance-compatible as the canonical target lifecycle, but E1 implementation is blocked until the above lifecycle, persistence, ownership, idempotency, scanner decay, protective-close, and fail-closed healthcheck criteria are made explicit in the next contracts/RFC step.

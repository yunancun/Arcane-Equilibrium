# MAG-030 Agent Spine Rust Module Design RFC

Date: 2026-05-07
Status: MAG-030 design checkpoint
Owner: PA
Scope: M3 Agent Decision Spine Shadow

## Decision

M3 adds a Rust-first `agent_spine` module as the narrow typed seam for
trade-relevant lineage. The first implementation wave is shadow-only: it
persists StrategySignal and downstream decision-chain objects for audit and
comparison while legacy Rust execution behavior remains unchanged.

The module must not promote `MessageBus` to authority. `MessageBus` remains a
legacy/advisory trace. The authoritative chain is typed objects plus durable
edges:

```text
OpportunityCandidate / ScoutIntel / StrategySignal
  -> StrategistDecision
  -> GuardianVerdict
  -> ExecutionPlan
  -> Decision Lease
  -> order dispatch
  -> ExecutionReport
  -> AnalystInsight
```

## Non-Goals

- No runtime deploy, rebuild, restart, or feature-flag flip in MAG-030.
- No live, live-demo, or demo behavior change.
- No Python agent rewrite in MAG-030.
- No new execution authority for scanner, Executor, or OpenClaw Gateway.
- No direct cloud-agent call path.

## Authority Rules

Facts from M0/M2:

- Rust remains the execution engine and final hot-path enforcement layer.
- Python agents may reason and produce typed objects through adapters.
- Scanner is advisory evidence only after M2; scanner decay cannot close,
  reduce, or directly decide tactical opens.
- GuardianVerdict is mandatory before any ExecutionPlan that can reach real
  submit.
- Decision Lease remains independent and is still required before execution.

Inference for M3:

- Rust must be able to reject or shadow-flag execution candidates whose typed
  lineage is incomplete.
- Postgres needs durable lineage joins, not only free-text messages.
- Idempotency must be keyed by decision lineage IDs, not symbol/side/time alone.

Assumption for MAG-031..035:

- M3 starts with `disabled` or `shadow` mode only. `canary` and `primary` are
  reserved for later acceptance after MAG-034 and MAG-035.

## Rust Module Files

| File | Responsibility | First MAG |
|---|---|---:|
| `rust/openclaw_engine/src/agent_spine/mod.rs` | Module exports, top-level `AgentSpine` facade, no business logic. | MAG-031 |
| `rust/openclaw_engine/src/agent_spine/config.rs` | `AgentSpineMode` parsing and fail-open/fail-closed policy by mode. | MAG-031 |
| `rust/openclaw_engine/src/agent_spine/contracts.rs` | Serde contracts for `StrategySignal`, `StrategistDecisionRef`, `GuardianVerdictRef`, `ExecutionPlan`, `ExecutionReportRef`, `AnalystInsightRef`. | MAG-031/032 |
| `rust/openclaw_engine/src/agent_spine/ids.rs` | Deterministic idempotency-key builders and payload hash helpers. | MAG-031/032 |
| `rust/openclaw_engine/src/agent_spine/events.rs` | `SpineObjectEnvelope`, `SpineEdge`, `SpineStateTransition`, edge/state enums. | MAG-032 |
| `rust/openclaw_engine/src/agent_spine/store.rs` | Store trait plus fail-soft channel producer for DB writes. | MAG-032 |
| `rust/openclaw_engine/src/agent_spine/signal_adapter.rs` | Converts Rust strategy output metadata into `StrategySignal`. | MAG-031 |
| `rust/openclaw_engine/src/agent_spine/router.rs` | Shadow/canary gate that validates complete lineage before an `ExecutionPlan` can become an order candidate. | MAG-034/035 |
| `rust/openclaw_engine/src/agent_spine/tests.rs` | Contract, hash, idempotency, and shadow-gate unit tests. | MAG-031..035 |
| `rust/openclaw_engine/src/database/agent_spine_writer.rs` | Async DB writer, matching existing database writer conventions. | MAG-032 |

Module registration:

- Add `pub mod agent_spine;` to `rust/openclaw_engine/src/lib.rs`.
- Add `pub mod agent_spine_writer;` to `rust/openclaw_engine/src/database/mod.rs`
  only when MAG-032 lands the writer.

## Rust Interfaces

### Mode

```rust
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AgentSpineMode {
    Disabled,
    Shadow,
    Canary,
    Primary,
}

impl AgentSpineMode {
    pub fn writes_enabled(self) -> bool;
    pub fn enforces_new_exposure(self) -> bool;
    pub fn store_error_blocks_new_exposure(self) -> bool;
}
```

Mode semantics:

| Mode | Writes | New-open enforcement | Store error behavior |
|---|---:|---:|---|
| `disabled` | No | No | No behavior change |
| `shadow` | Yes | No | Warn and continue legacy behavior |
| `canary` | Yes | Shadow verdict compares against legacy | Block only if an explicit canary test path requests it |
| `primary` | Yes | Yes for new exposure | Fail closed for new/increase exposure |

Protective H0/P0/P1 reduce-only paths are outside tactical Strategist
approval, but must still write explicit protective lineage before they are
treated as accepted M3 behavior.

### Object Contracts

`contracts.rs` owns Rust-side contracts that are persisted as JSONB payloads
and shared with Python via mirrored Pydantic/TypedDict models in MAG-033.

Required contracts:

- `StrategySignal`
- `StrategistDecisionRef`
- `GuardianVerdictRef`
- `ExecutionPlan`
- `ExecutionReportRef`
- `AnalystInsightRef`
- `DecisionObjectType`
- `DecisionAction`
- `GuardianVerdictStatus`
- `ExecutionPlanStatus`
- `ExecutionReportStatus`

Minimum `StrategySignal` fields:

```rust
pub struct StrategySignal {
    pub signal_id: String,
    pub ts_ms: u64,
    pub engine_mode: String,
    pub symbol: String,
    pub strategy: String,
    pub direction: SignalDirection,
    pub raw_signal_strength: f64,
    pub expected_edge_bps: Option<f64>,
    pub expected_cost_bps: Option<f64>,
    pub confidence: f64,
    pub regime: Option<String>,
    pub scanner_candidate_id: Option<String>,
    pub scanner_decay_id: Option<String>,
    pub context_id: Option<String>,
    pub evidence_refs: Vec<String>,
    pub invalidation: Option<String>,
}
```

Rust only stores refs for Python-created reasoning objects until those objects
are fully implemented:

```rust
pub struct StrategistDecisionRef {
    pub decision_id: String,
    pub signal_id: Option<String>,
    pub action: DecisionAction,
    pub symbol: String,
    pub strategy: Option<String>,
    pub payload_hash: String,
}

pub struct GuardianVerdictRef {
    pub verdict_id: String,
    pub decision_id: String,
    pub verdict_version: i32,
    pub status: GuardianVerdictStatus,
    pub payload_hash: String,
}
```

`ExecutionPlan` must never encode independent tactical authority. Its symbol,
side, reduce-only state, and max exposure must be derived from an approved or
modified GuardianVerdict:

```rust
pub struct ExecutionPlan {
    pub order_plan_id: String,
    pub decision_id: String,
    pub verdict_id: String,
    pub verdict_version: i32,
    pub engine_mode: String,
    pub symbol: String,
    pub side: String,
    pub qty: f64,
    pub reduce_only: bool,
    pub order_style: OrderStyle,
    pub urgency: ExecutionUrgency,
    pub max_slippage_bps: Option<f64>,
    pub maker_preference: Option<String>,
    pub lease_scope: Option<String>,
    pub lease_ttl_ms: Option<u64>,
    pub idempotency_key: String,
}
```

### Store Trait

`store.rs` defines a narrow interface. Implementations may use an in-memory
test store, a channel-backed DB writer, or a disabled store.

```rust
pub trait AgentSpineStore {
    fn put_object(&self, object: SpineObjectEnvelope) -> Result<StoreAck, SpineError>;
    fn put_edge(&self, edge: SpineEdge) -> Result<StoreAck, SpineError>;
    fn put_transition(&self, transition: SpineStateTransition) -> Result<StoreAck, SpineError>;
    fn reserve_execution_key(&self, key: ExecutionIdempotencyKey) -> Result<StoreAck, SpineError>;
}
```

The hot path must not await Postgres directly in shadow mode. Use the existing
database writer pattern: bounded channel, async batch insert, fail-soft warning
in `shadow`, fail-closed only when `primary` is intentionally enabled for
new/increase exposure.

### Router Gate

`router.rs` validates lineage before an execution candidate is considered
eligible:

```rust
pub enum SpineGateDecision {
    AllowShadow { reasons: Vec<String> },
    AllowPrimary { lineage_hash: String },
    Reject { reason: String },
}
```

Required rejection reasons:

- `missing_decision_id`
- `missing_guardian_verdict`
- `guardian_rejected`
- `missing_execution_plan`
- `missing_order_plan_id`
- `duplicate_order_plan_id`
- `missing_required_lease`
- `execution_authority_mismatch`
- `store_unavailable_primary`

## Store Design

MAG-032 should add a migration after the current migration head. The exact
migration number must be selected at implementation time.

### `agent.decision_objects`

Canonical identity table. Use a regular table, not a hypertable, so durable
unique constraints can key on object IDs and idempotency keys without Timescale
time-column restrictions.

Required columns:

- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `object_id TEXT PRIMARY KEY`
- `object_type TEXT NOT NULL`
- `object_version INT NOT NULL DEFAULT 1`
- `engine_mode TEXT NOT NULL`
- `symbol TEXT`
- `strategy TEXT`
- `decision_id TEXT`
- `verdict_id TEXT`
- `verdict_version INT`
- `order_plan_id TEXT`
- `lease_id TEXT`
- `state TEXT NOT NULL`
- `source_agent TEXT NOT NULL`
- `authority_mode TEXT NOT NULL`
- `idempotency_key TEXT NOT NULL`
- `payload_hash TEXT NOT NULL`
- `payload JSONB NOT NULL`

Required unique constraints:

- `UNIQUE (object_type, idempotency_key)`
- partial unique `decision_id` for `object_type='strategist_decision'`
- partial unique `(decision_id, verdict_version)` for `object_type='guardian_verdict'`
- partial unique `order_plan_id` for `object_type='execution_plan'`

### `agent.decision_edges`

Durable lineage edges:

- `edge_id TEXT PRIMARY KEY`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `from_object_id TEXT NOT NULL`
- `to_object_id TEXT NOT NULL`
- `edge_type TEXT NOT NULL`
- `engine_mode TEXT NOT NULL`
- `decision_id TEXT`
- `payload_hash TEXT NOT NULL`
- `details JSONB NOT NULL DEFAULT '{}'::jsonb`

Required unique constraint:

- `UNIQUE (from_object_id, to_object_id, edge_type)`

Allowed edge types:

- `evidence_for`
- `signal_for`
- `reviewed_by`
- `modified_by`
- `planned_by`
- `leased_by`
- `executed_by`
- `analyzed_by`
- `protective_bypass_for`

### `agent.decision_state_changes`

Append-only transition log. This can be a hypertable because state history is
time-series and does not need global unique business-key enforcement beyond
`transition_id`.

Required columns:

- `ts TIMESTAMPTZ NOT NULL`
- `transition_id TEXT NOT NULL`
- `object_id TEXT NOT NULL`
- `object_type TEXT NOT NULL`
- `from_state TEXT`
- `to_state TEXT NOT NULL`
- `engine_mode TEXT NOT NULL`
- `trigger TEXT NOT NULL`
- `details JSONB NOT NULL DEFAULT '{}'::jsonb`
- `PRIMARY KEY (transition_id, ts)`

### `agent.execution_idempotency_keys`

Regular table for execution dedupe:

- `idempotency_key TEXT PRIMARY KEY`
- `order_plan_id TEXT NOT NULL`
- `decision_id TEXT NOT NULL`
- `engine_mode TEXT NOT NULL`
- `first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()`
- `status TEXT NOT NULL`
- `details JSONB NOT NULL DEFAULT '{}'::jsonb`

Required unique constraints:

- `UNIQUE (order_plan_id, engine_mode)`
- `UNIQUE (decision_id, order_plan_id, engine_mode)`

## Integration Points

### MAG-031 StrategySignal Adapter

Insertion point:

- `rust/openclaw_engine/src/tick_pipeline/on_tick/step_3_signals.rs`

Behavior:

- Build `StrategySignal` from existing Rust signal/strategy metadata.
- Persist it in `shadow` mode before strategy dispatch.
- Attach `signal_id` / `spine_signal_id` to existing intent metadata where
  available.
- Do not suppress, allow, or modify strategy action behavior.

### MAG-032 Spine Store

Insertion points:

- `rust/openclaw_engine/src/agent_spine/store.rs`
- `rust/openclaw_engine/src/database/agent_spine_writer.rs`
- new migration under `sql/migrations/`

Behavior:

- Persist object, edge, state-change, and execution-idempotency rows.
- Provide joinable row proof:

```sql
SELECT s.object_id AS signal_id,
       d.decision_id,
       v.verdict_id,
       p.order_plan_id
FROM agent.decision_objects s
JOIN agent.decision_edges e1 ON e1.from_object_id = s.object_id
JOIN agent.decision_objects d ON d.object_id = e1.to_object_id
JOIN agent.decision_edges e2 ON e2.from_object_id = d.object_id
JOIN agent.decision_objects v ON v.object_id = e2.to_object_id
JOIN agent.decision_edges e3 ON e3.from_object_id = v.object_id
JOIN agent.decision_objects p ON p.object_id = e3.to_object_id
WHERE s.object_type = 'strategy_signal'
  AND d.object_type = 'strategist_decision'
  AND v.object_type = 'guardian_verdict'
  AND p.object_type = 'execution_plan';
```

### MAG-033 Python Client

Insertion points:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_contracts.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/agent_spine_client.py`

Behavior:

- Mirror the Rust contracts.
- Publish StrategistDecision, GuardianVerdict, ExecutionPlan, ExecutionReport,
  and AnalystInsight objects plus edges.
- Enforce bounded payloads and hashes; no raw prompts, raw LLM responses,
  secrets, API keys, or unbounded free text.

### MAG-034 Idempotency Audit

Required audit:

- `decision_id` uniqueness.
- Guardian verdict version uniqueness per decision.
- `order_plan_id` uniqueness.
- One submit attempt per `(decision_id, order_plan_id, engine_mode)` unless a
  later cancel/replace version is explicitly introduced.
- Missing lineage cannot be treated as approval.

### MAG-035 Shadow Integration

Required proof:

- Legacy behavior remains unchanged in `shadow`.
- Complete shadow chain is persisted for at least one strategy open candidate.
- Guardian rejection and missing-plan paths are visible in shadow verdicts.
- No order reaches a new primary path from the spine until `primary` mode is
  explicitly enabled in a later milestone.

## State Model

`StrategySignal`:

- `observed`
- `stale`
- `superseded`
- `invalidated`

`StrategistDecision`:

- `proposed`
- `superseded`
- `withdrawn`
- `rejected_by_guardian`
- `approved_by_guardian`
- `planned`
- `leased`
- `executing`
- `executed`
- `failed`
- `expired`
- `cancelled`
- `analyzed`

`GuardianVerdict`:

- `approved`
- `modified`
- `rejected`
- `circuit_break`

`ExecutionPlan`:

- `drafted`
- `lease_pending`
- `lease_denied`
- `leased`
- `submitted`
- `acknowledged`
- `partially_filled`
- `filled`
- `rejected`
- `cancelled`
- `expired`

`ExecutionReport`:

- `received`
- `linked`
- `quality_scored`

## Feature Flags

Primary config surface:

```toml
[agent_spine]
mode = "disabled" # disabled | shadow | canary | primary
store_channel_capacity = 1024
payload_max_bytes = 65536
```

Environment override:

- `OPENCLAW_AGENT_SPINE_MODE`

Rules:

- Default must remain `disabled`.
- `shadow` may write rows but must not alter trading behavior.
- `canary` may calculate allow/reject comparison but must not become primary
  execution authority.
- `primary` requires MAG-034 + MAG-035 acceptance and a separate operator
  cutover decision.
- Store failures in `shadow` are warn-only.
- Store failures in `primary` fail closed for new or exposure-increasing orders.

## Acceptance Checklist for MAG-030

- [x] Lists Rust module files and ownership.
- [x] Defines Rust interfaces for modes, contracts, store, and router gate.
- [x] Defines store tables, keys, edges, and idempotency constraints.
- [x] Defines feature flags and default-disabled rollout semantics.
- [x] Maps MAG-031..035 to exact implementation seams.
- [x] Preserves M2 scanner advisory boundary and Decision Lease independence.
- [x] Makes no runtime behavior change.

## Next Work

MAG-031 can start with `StrategySignal` adapter scaffolding in shadow-only mode.
It should not add `ExecutionPlan` submission or Guardian enforcement. MAG-032
must land the durable store before Python agents publish authoritative chain
objects in MAG-033.

# MAG-015 Sprint A Contract Addendum

Date: 2026-05-06
Status: APPROVED contract input for MAG-010..MAG-019
Owner: PA
Parent backlog: `AgentTodo.md`

## 1. Purpose

MAG-015 freezes the first Sprint A contracts before any implementation starts.

This addendum resolves the M0 conditional gaps from MAG-002 and MAG-003 for
the read-only / event-store foundation:

- local agent observations,
- OpenClaw backend view models,
- supervisor escalation packets,
- proposal / approval / channel schemas,
- OpenClaw endpoint allowlist,
- cloud budget policy,
- store ownership,
- state transitions and failure behavior.

This is not the full Agent Decision Spine. MAG-010..MAG-014 close the current
`agent.messages`, `agent.state_changes`, and `agent.ai_invocations` zero-row
blocker first. MAG-016..MAG-019 may only build read-only OpenClaw / Agent
Control surfaces on top of those durable rows.

## 2. Hard Boundaries

These boundaries are part of the contract and must be tested in MAG-013,
MAG-014, MAG-016, MAG-017, MAG-018, and MAG-019.

| Boundary | Contract |
|---|---|
| OpenClaw Gateway authority | Gateway may read, brief, diagnose, create proposals, and relay approval intent through TradeBot APIs. It must never order, mutate live/demo risk config directly, read secrets, or bypass GovernanceHub / Decision Lease / Rust enforcement. |
| Local 5-Agent runtime | Scout / Strategist / Guardian / Analyst / Executor stay inside TradeBot. They emit observations and decisions through TradeBot storage and governance seams. |
| MessageBus | Legacy/advisory transport trace only. `agent.messages` persistence does not promote MessageBus into the Agent Decision Spine. |
| Cloud L2 | No local agent calls cloud independently. One supervisor compresses observations into one bounded packet, budget-checks it, records `agent.ai_invocations`, then may call cloud only if enabled. |
| GUI | Existing FastAPI console is the only canonical GUI. Agent Control is read-only until proposal/approval backend contracts are separately implemented. |
| Trading side effects | Any side-effecting proposal must be persisted before approval and still enter existing governance paths. Proposal creation is not execution authorization. |
| Runtime dependency | OpenClaw Gateway outage must not stop Rust trading runtime. It must render as degraded status. |

## 3. Contract Vocabulary

### 3.1 LocalObservation

`LocalObservation` is the normalized output shape for local agents before
supervisor escalation or OpenClaw view aggregation.

Authority: none. It is evidence, diagnosis input, or brief input.

Minimum fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `observation_id` | string | yes | Stable UUID or deterministic event id. |
| `ts_ms` | integer | yes | Producer wall-clock milliseconds. |
| `agent_role` | enum | yes | `scout`, `strategist`, `guardian`, `analyst`, `executor`, `conductor`, `supervisor`. |
| `engine_mode` | string/null | no | `paper`, `demo`, `live`, or null for control-plane observations. |
| `observation_type` | enum | yes | `runtime_health`, `market_evidence`, `strategy_evidence`, `risk_evidence`, `execution_quality`, `learning_signal`, `governance_gap`, `operator_context`, `gateway_status`. |
| `severity` | enum | yes | `info`, `warn`, `fail`, `critical`. |
| `confidence` | number/null | no | 0..1 if known. |
| `claim_type` | enum | yes | `fact`, `inference`, `hypothesis`, `recommendation`. |
| `summary` | string | yes | Safe short text, no raw prompt or secrets. |
| `evidence_refs` | array | yes | Links to DB rows, healthchecks, reports, or route names. |
| `context_id` | string/null | no | Shared chain id when available. |
| `related_object_ids` | array | no | Future decision object / proposal / escalation ids. |
| `recommended_next_action` | enum/null | no | `none`, `observe`, `diagnose`, `escalate`, `create_readonly_proposal`, `create_approval_required_proposal`. |
| `payload` | object | yes | Redacted bounded details. |

Redaction requirements:

- no Bybit keys, secret paths, auth tokens, session cookies, raw prompts, raw
  model responses, stack traces, or unrestricted DB dumps;
- payload must be size-capped by
  `OPENCLAW_AGENT_EVENT_STORE_MAX_PAYLOAD_BYTES`;
- truncated fields must be marked with `payload_truncated=true`.

Persistence mapping for MAG-010..MAG-014:

- first wave: store `LocalObservation` as redacted `agent.messages.payload`
  or `agent.ai_invocations.details` references when tied to a model call;
- later M2/M3: the same fields can be promoted into typed
  `agent.decision_objects` / `agent.insights` without changing meaning.

### 3.2 EvidenceRef

All view models, diagnoses, escalation packets, and proposals use the same
evidence reference shape.

| Field | Type | Required | Notes |
|---|---|---:|---|
| `ref_type` | enum | yes | `db_row`, `healthcheck`, `report`, `api_route`, `log_excerpt`, `config_key`, `commit`, `runtime_probe`. |
| `ref_id` | string | yes | Row id, healthcheck id, path, route, commit sha, or probe id. |
| `label` | string | yes | Human-safe label. |
| `freshness_ts_ms` | integer/null | no | Timestamp of observed source. |
| `engine_mode` | string/null | no | Mode when relevant. |
| `safe_url` | string/null | no | Internal route/report path only; no secret URLs. |

## 4. OpenClaw Backend View Models

Backend view models are the only source for Agent Control GUI and Gateway
read-only responses. Frontend JavaScript must not reconstruct state by joining
raw tables.

Every OpenClaw API response uses this envelope:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `ok` | boolean | yes | False when the endpoint itself is degraded. |
| `status` | enum | yes | `pass`, `warn`, `fail`, `degraded`, `disabled`. |
| `generated_at_ms` | integer | yes | Backend generation time. |
| `freshness_ms` | integer/null | no | Age of oldest critical source. |
| `degraded` | boolean | yes | True when any backing source is unavailable or stale. |
| `degraded_reasons` | array | yes | Safe strings, no exception internals. |
| `evidence_refs` | array | yes | `EvidenceRef[]`. |
| `data` | object | yes | Endpoint-specific model. |

### 4.1 SelfStateSnapshot

Endpoint: `GET /api/v1/openclaw/self-state`

Authority: none. Read-only snapshot.

Minimum fields:

| Field | Type | Notes |
|---|---|---|
| `snapshot_id` | string | Stable id for this snapshot. |
| `runtime` | object | Engine alive flags, snapshot age, paper/demo/live posture. |
| `agents` | array | Five local agents plus conductor/supervisor state. |
| `agent_event_store` | object | Recent row counts and zero-row blocker status for `agent.messages`, `agent.state_changes`, `agent.ai_invocations`. |
| `governance` | object | Decision Lease flag posture, live auth posture, known live blockers. |
| `edge` | object | Read-only [33]/[38]/[40]/[51] summary. |
| `model_budget` | object | Local/cloud availability, daily/monthly budget status, disabled reason. |
| `open_blockers` | array | Active P0/P1 blockers with evidence refs. |
| `latest_diagnoses` | array | Recent `Diagnosis` summaries. |

Status rules:

- `pass`: runtime fresh and no P0/P1 blocker in queried scope;
- `warn`: known blockers or missing optional Gateway/channel data;
- `fail`: event-store required but zero rows, runtime stale, or governance
  hard-boundary violation;
- `degraded`: backing source unavailable, but safe read envelope still returned;
- `disabled`: feature flag disabled by design.

### 4.2 Diagnosis

Endpoint: `GET /api/v1/openclaw/diagnostics`

Authority: none. A diagnosis may lead to a proposal but is not a proposal.

Minimum fields:

| Field | Type | Notes |
|---|---|---|
| `diagnosis_id` | string | Stable id. |
| `ts_ms` | integer | Creation timestamp. |
| `severity` | enum | `info`, `warn`, `fail`, `critical`. |
| `domain` | enum | `runtime`, `edge`, `governance`, `data`, `security`, `gateway`, `ai_cost`, `operator`. |
| `status` | enum | See state table below. |
| `facts` | array | Fact claims only. |
| `inferences` | array | Inference claims only. |
| `hypotheses` | array | Hypotheses or candidate root causes. |
| `recommended_action` | string/null | Safe summary. |
| `evidence_refs` | array | Required. |
| `linked_escalation_id` | string/null | If cloud escalation was made. |
| `linked_proposal_id` | string/null | If a proposal was created. |

## 5. Supervisor Escalation Contract

### 5.1 EscalationPacket

Endpoint family: `GET /api/v1/openclaw/escalations` for read-only listing.
Creation can be internal first; external creation waits until proposal/channel
work is explicitly enabled.

Authority: none. Cloud response may produce a diagnosis or proposal, not an
action.

Minimum fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `escalation_id` | string | yes | Stable id. |
| `created_at_ms` | integer | yes | Creation timestamp. |
| `trigger_type` | enum | yes | `healthcheck_fail`, `edge_regression`, `execution_quality_shock`, `strategy_anomaly`, `governance_contradiction`, `operator_requested`, `daily_brief_low_confidence`. |
| `source_observation_ids` | array | yes | Local observations compressed into this packet. |
| `budget_decision` | object | yes | Budget result before any cloud call. |
| `prompt_hash` | string/null | no | Required if sent to model. |
| `input_summary` | string | yes | Safe compressed packet summary. |
| `model_request` | object/null | no | Provider, model, tier. |
| `ai_invocation_id` | string/null | no | Must link to `agent.ai_invocations` when model is called. |
| `response_summary` | string/null | no | Safe summary only. |
| `result_diagnosis_ids` | array | no | Diagnoses created from response. |
| `result_proposal_ids` | array | no | Proposals created from response. |
| `status` | enum | yes | See state table below. |

### 5.2 Cloud Budget Policy

Default flags:

| Flag | Default | Contract |
|---|---|---|
| `OPENCLAW_SUPERVISOR_CLOUD_ENABLED` | `0` | No cloud call unless explicitly enabled. |
| `OPENCLAW_SUPERVISOR_CLOUD_REQUIRE_BUDGET` | `1` | Missing budget config blocks cloud calls. |
| `OPENCLAW_SUPERVISOR_CLOUD_DAILY_USD_CAP` | unset | Required before enable; unset means budget denied. |
| `OPENCLAW_SUPERVISOR_CLOUD_MONTHLY_USD_CAP` | unset | Required before enable; unset means budget denied. |
| `OPENCLAW_SUPERVISOR_CLOUD_MAX_PACKET_BYTES` | `32768` | Escalation packet hard cap before prompt hash. |

Budget behavior:

1. Build local observations first.
2. Supervisor compresses and redacts.
3. Budget decision is persisted in packet payload.
4. If denied, no cloud call is made and a local `Diagnosis` records
   `cloud_budget_denied`.
5. If allowed, `agent.ai_invocations` must be written before or atomically
   with finalizing the escalation result.
6. A missing or failed `agent.ai_invocations` row makes the escalation
   `failed` or `degraded`; it must not silently succeed.

For control-plane supervisor calls with no trading mode, set
`agent.ai_invocations.engine_mode = NULL` and include
`details.control_plane=true`.

## 6. Proposal, Approval, and Channel Contracts

These schemas are frozen now so MAG-017/MAG-018 can render read-only empty or
disabled states. Write endpoints remain deferred until event-store row proof
and authority lockdown pass.

### 6.1 Proposal

Endpoint family:

- deferred read/write: `GET /api/v1/openclaw/proposals`,
  `POST /api/v1/openclaw/proposals`
- no proposal creation in MAG-016/MAG-017 unless PM explicitly opens OC-GW-5.

Authority: none until approved and delegated to existing governance path.

Minimum fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `proposal_id` | string | yes | Stable id. |
| `request_id` | string | yes | OpenClaw-origin idempotency key. |
| `created_at_ms` | integer | yes | Creation timestamp. |
| `created_by` | object | yes | Source/channel/sender/auth profile. |
| `proposal_type` | enum | yes | `read_only_report`, `diagnosis_followup`, `offline_replay`, `config_change`, `risk_change`, `live_authorization`, `deploy`, `trade_affecting`. |
| `risk_class` | enum | yes | `read_only`, `offline`, `demo_only`, `live_affecting`, `mainnet_affecting`. |
| `status` | enum | yes | See state table below. |
| `summary` | string | yes | Safe short text. |
| `evidence_refs` | array | yes | Required. |
| `required_approval_class` | enum | yes | `none`, `operator`, `governance`, `live_reserved`, `deploy_operator`. |
| `operator_action_required` | boolean | yes | Backend controls GUI buttons. |
| `expires_at_ms` | integer/null | no | Required for approval-required proposals. |
| `linked_diagnosis_id` | string/null | no | If derived from diagnosis. |
| `linked_escalation_id` | string/null | no | If derived from cloud/local supervisor. |
| `side_effect_route` | string/null | no | Existing TradeBot governance route to call after approval, never an order route directly. |
| `payload` | object | yes | Redacted bounded details. |

Rules:

- proposal persistence must happen before it appears in GUI/mobile;
- approval-required proposals must expire;
- creation must be idempotent by `(source, channel, request_id)`;
- approval does not call order endpoints directly;
- live-affecting proposals must use existing operator auth and governance
  paths.

### 6.2 ApprovalDecision

Endpoint family:

- deferred: `POST /api/v1/openclaw/proposals/{proposal_id}/approve`
- deferred: `POST /api/v1/openclaw/proposals/{proposal_id}/reject`

Authority: records operator decision and delegates to existing governance path
when applicable.

Minimum fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `approval_id` | string | yes | Stable id. |
| `proposal_id` | string | yes | Parent proposal. |
| `request_id` | string | yes | Channel/operator idempotency key. |
| `decision` | enum | yes | `approved`, `rejected`, `expired`, `denied`, `cancelled`. |
| `decided_at_ms` | integer | yes | Timestamp. |
| `actor` | object | yes | Authenticated operator identity/profile. |
| `auth_result` | enum | yes | `authenticated`, `unauthorized`, `expired`, `insufficient_scope`. |
| `reason` | string/null | no | Safe reason. |
| `delegated_route` | string/null | no | Existing TradeBot route if side effect proceeds. |
| `governance_result_ref` | object/null | no | Decision Lease/GovernanceHub refs after delegation. |

Rules:

- expired proposals cannot be approved;
- unauthorized channel approvals fail closed;
- approval replay with same request id must be idempotent;
- rejection is terminal unless a new proposal is created.

### 6.3 ChannelEvent

Endpoint family: read-only surfaced through `/api/v1/openclaw/status` and later
`/api/v1/openclaw/brief/latest` / `/proposals`.

Authority: none. Audit trace only.

Minimum fields:

| Field | Type | Required | Notes |
|---|---|---:|---|
| `channel_event_id` | string | yes | Stable id. |
| `request_id` | string | yes | Idempotency key from channel/gateway. |
| `ts_ms` | integer | yes | Event timestamp. |
| `direction` | enum | yes | `inbound`, `outbound`. |
| `channel` | enum | yes | `console`, `telegram`, `webchat`, `mobile`, `gateway_internal`. |
| `sender` | string | yes | Redacted channel sender id. |
| `auth_profile` | string | yes | `anonymous`, `read_only`, `operator`, `live_operator`, `service`. |
| `event_type` | enum | yes | `status_query`, `alert_sent`, `ack`, `proposal_created`, `approval_intent`, `brief_sent`, `diagnosis_request`. |
| `status` | enum | yes | See state table below. |
| `linked_proposal_id` | string/null | no | If applicable. |
| `linked_escalation_id` | string/null | no | If applicable. |
| `payload_summary` | string | yes | Safe summary, no raw message body if sensitive. |

## 7. Endpoint Allowlist

MAG-016 must encode this allowlist as policy plus static tests.

### 7.1 Sprint A Active Allowlist

Only these endpoints may be exposed during MAG-016/MAG-017:

```text
GET /api/v1/openclaw/status
GET /api/v1/openclaw/self-state
```

Allowed behavior:

- read backend-authored view models;
- return degraded envelopes when Gateway, DB, or event-store rows are missing;
- report configured allowlist/auth/channel posture;
- never mutate runtime, strategy/risk config, live auth, orders, or secrets.

### 7.2 Sprint A Read-Only Deferred Endpoints

These may be contracted and tested with disabled or empty responses, but should
not be treated as enabled workflow until MAG-010..MAG-014 row proof exists:

```text
GET /api/v1/openclaw/brief/latest
GET /api/v1/openclaw/diagnostics
GET /api/v1/openclaw/escalations
GET /api/v1/openclaw/proposals
```

### 7.3 Deferred Write Endpoints

These are not part of MAG-016/MAG-017 implementation:

```text
POST /api/v1/openclaw/proposals
POST /api/v1/openclaw/proposals/{proposal_id}/approve
POST /api/v1/openclaw/proposals/{proposal_id}/reject
```

They require a later PM gate after event-store row proof, proposal persistence,
operator auth, idempotency tests, and E3 security review.

### 7.4 Forbidden Endpoint Classes

OpenClaw client code, gateway code, and `/api/v1/openclaw/*` routes must not
call or proxy:

- Bybit credential or secret endpoints;
- direct order submit/cancel/close endpoints;
- live authorization renewal or live session activation endpoints;
- direct TOML, risk, leverage, strategy config mutation endpoints;
- restart, rebuild, deploy, shell, migration, or watchdog mutation endpoints;
- unrestricted raw SQL / raw table dump endpoints;
- any route that bypasses existing operator auth, GovernanceHub, Decision
  Lease, or Rust execution authority.

All OpenClaw-originated requests must carry:

- `source`,
- `channel`,
- `sender`,
- `auth_profile`,
- `request_id`.

Missing request context downgrades read requests to degraded/anonymous posture
and rejects write-like requests once they exist.

## 8. Store Ownership

| Surface | Durable store | Sole writer/updater | Reader | Failure behavior |
|---|---|---|---|---|
| `agent.messages` | Existing V003 table | `AgentEventStore.record_message()` | healthcheck, OpenClaw views, audit tools | MAG-010 fail-soft for trading, fail-visible in healthcheck. |
| `agent.state_changes` | Existing V003 table | `AgentEventStore.record_state_change()` | healthcheck, OpenClaw views | MAG-011 fail-soft for trading, fail-visible in healthcheck. |
| `agent.ai_invocations` | Existing V003/V015 table | `AgentEventStore.record_ai_invocation()` | healthcheck, OpenClaw escalation ledger | MAG-012/MAG-019 missing row makes cloud escalation degraded/failed. |
| `SelfStateSnapshot` | Backend computed view | `openclaw_routes.py` / view service | Gateway, GUI | Degraded envelope; no mutation. |
| `Diagnosis` | Later durable proposal/diagnosis table or report-backed view | OpenClaw diagnosis service | Gateway, GUI | Missing backing rows render empty/degraded. |
| `EscalationPacket` | Later durable table plus `agent.ai_invocations` link | Supervisor escalation service | GUI, Gateway | Budget denied means no cloud call. Missing AI row is WARN/FAIL. |
| `Proposal` | Later durable proposal table | TradeBot proposal service only | GUI, Gateway | Persistence failure blocks proposal visibility and approval. |
| `ApprovalDecision` | Later durable approval table + governance audit | TradeBot approval service only | GUI, Gateway | Auth/governance failure blocks side effect. |
| `ChannelEvent` | Later durable channel event table | Gateway adapter through TradeBot API | GUI, healthcheck | Failure visible; no trading effect. |
| Rust execution | Existing Rust engine/governance stores | Rust/GovernanceHub only | GUI/API | OpenClaw cannot write. |

No other module should insert directly into the three existing `agent.*` tables
after MAG-010..MAG-012. Tests should grep for direct SQL writes outside the
event-store module, allowing migrations and tests.

## 9. State Transitions

### 9.1 LocalObservation

| From | To | Trigger | Terminal |
|---|---|---|---:|
| none | `observed` | agent emits observation | no |
| `observed` | `linked` | attached to diagnosis/escalation/proposal | no |
| `observed` / `linked` | `stale` | freshness TTL exceeded | yes |
| `observed` / `linked` | `superseded` | newer observation replaces it | yes |
| any | `invalidated` | source later proved wrong | yes |

### 9.2 SelfStateSnapshot

| From | To | Trigger | Terminal |
|---|---|---|---:|
| none | `generated` | backend aggregation succeeds | no |
| none | `degraded` | one or more sources unavailable | no |
| `generated` / `degraded` | `stale` | freshness TTL exceeded | yes |
| any | `failed` | contract violation or unsafe source error | yes |

### 9.3 Diagnosis

| From | To | Trigger | Terminal |
|---|---|---|---:|
| none | `open` | diagnosis created | no |
| `open` | `acknowledged` | operator/system ack | no |
| `open` / `acknowledged` | `escalated` | supervisor packet created | no |
| `open` / `escalated` | `proposal_created` | proposal persisted | no |
| any | `resolved` | evidence shows issue closed | yes |
| any | `suppressed` | duplicate or intentionally ignored | yes |
| any | `expired` | TTL exceeded | yes |

### 9.4 EscalationPacket

| From | To | Trigger | Terminal |
|---|---|---|---:|
| none | `drafted` | supervisor builds packet | no |
| `drafted` | `budget_checked` | budget evaluated | no |
| `budget_checked` | `denied` | cloud disabled or over budget | yes |
| `budget_checked` | `invocation_recorded` | `agent.ai_invocations` row reserved/written | no |
| `invocation_recorded` | `sent` | cloud request sent | no |
| `sent` | `responded` | cloud response summarized | no |
| `responded` | `diagnosis_created` | diagnosis persisted | no |
| `responded` | `proposal_created` | proposal persisted | no |
| any | `failed` | persistence/model/contract failure | yes |
| any | `cancelled` | operator/system cancellation | yes |

### 9.5 Proposal

| From | To | Trigger | Terminal |
|---|---|---|---:|
| none | `drafted` | proposal assembled | no |
| `drafted` | `persisted` | durable row written | no |
| `persisted` | `visible` | backend exposes to GUI/Gateway | no |
| `visible` | `pending_approval` | approval required | no |
| `visible` | `completed_read_only` | read-only proposal acknowledged/completed | yes |
| `pending_approval` | `approved` | valid operator approval | no |
| `pending_approval` | `rejected` | valid rejection | yes |
| `pending_approval` | `expired` | expiry time passed | yes |
| `approved` | `delegated_to_governance` | existing governance path called | no |
| `delegated_to_governance` | `executed` | side effect completed by canonical path | yes |
| `delegated_to_governance` | `failed` | governance/path failure | yes |
| any | `cancelled` | operator/system cancellation | yes |

### 9.6 ApprovalDecision

| From | To | Trigger | Terminal |
|---|---|---|---:|
| none | `received` | channel/API request received | no |
| `received` | `authenticated` | operator auth passes | no |
| `received` | `denied` | auth fails or scope insufficient | yes |
| `authenticated` | `accepted` | proposal open and action allowed | yes |
| `authenticated` | `rejected` | operator rejects | yes |
| `authenticated` | `expired` | proposal expired | yes |
| any | `duplicate_ignored` | same request id replayed | yes |

### 9.7 ChannelEvent

| From | To | Trigger | Terminal |
|---|---|---|---:|
| none | `received` | inbound/outbound event observed | no |
| `received` | `validated` | request context passes shape checks | no |
| `received` | `rejected` | missing/invalid request context | yes |
| `validated` | `persisted` | event audit row written | no |
| `persisted` | `dispatched` | outbound message sent or inbound routed | no |
| `dispatched` | `acknowledged` | channel/operator ack | yes |
| any | `failed` | channel/persistence failure | yes |

### 9.8 AgentEventStore M1 Tables

`agent.messages`, `agent.state_changes`, and `agent.ai_invocations` are
append-only in Sprint A.

Allowed failure states:

- `write_succeeded`,
- `write_failed_redacted`,
- `serialization_failed_redacted`,
- `disabled_by_flag`,
- `sampled_out` only after PM opens sampling later; M1 default is no sampling.

Write failure must not block trading in MAG-010..MAG-014, but it must be
counted and surfaced by healthcheck. If
`OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED=1`, zero recent rows are FAIL.

## 10. MAG-010..MAG-019 Implementation Packet

### MAG-010 Message Store

E1 must implement:

- `agent_event_store.py` as sole V003 event-store writer;
- `MessageBus` sink/fanout after message validation and before subscriber
  delivery;
- payload redaction, size cap, and safe serialization;
- tests proving DB failure does not block subscriber delivery;
- tests proving MessageBus is still not the Agent Decision Spine.

### MAG-011 State Store

E1 must implement:

- `BaseAgent` lifecycle transition sink for start/pause/stop/degrade/recover
  where existing lifecycle supports it;
- no DB IO while holding agent lock;
- Conductor/five-agent coverage where instantiated;
- healthcheck recent-row visibility.

### MAG-012 AI Invocation Store

E1a must implement:

- one `agent.ai_invocations` row per local L1/L1.5/L2 request where the call
  site exists;
- prompt hash and output hash/summary, not raw prompt or raw response;
- provider/model/tier/purpose/latency/cost/success/context id;
- direct Strategist/Analyst model-call audit so paths do not bypass the store.

### MAG-013 Failure Audit

E2 must block if:

- raw prompt/response/secret data is persisted;
- event-store writes can block trading in M1;
- direct inserts into `agent.*` tables bypass `AgentEventStore`;
- zero-row conditions are hidden by disabled/degraded envelopes;
- OpenClaw route code calls forbidden endpoints.

### MAG-014 Linux Regression

E4 must prove on Linux:

- event store enabled;
- recent nonzero rows in all three existing `agent.*` tables;
- targeted tests pass under Linux Python;
- passive healthcheck reports the event-store check correctly;
- known unrelated healthcheck failures are documented separately and not
  reclassified as event-store pass.

### MAG-016 Authority Lockdown

E2/E3 must implement/review:

- explicit allowlist from Section 7;
- forbidden endpoint static scan;
- request context shape enforcement;
- degraded read envelope behavior;
- no order/config/secret/live-auth access from Gateway or OpenClaw routes.

### MAG-017 Read-Only OpenClaw APIs

E1 must implement only:

- `GET /api/v1/openclaw/status`;
- `GET /api/v1/openclaw/self-state`;
- backend-authored view models and degraded envelopes;
- no write/proposal endpoint activation.

### MAG-018 Agent Control GUI

E1a must implement:

- read-only topology and self-state panels in `tab-agents.html`;
- data from backend view models only;
- degraded/disabled/empty states;
- no manual order controls and no raw prompt text.

### MAG-019 Supervisor Cloud Ledger Policy

AI-E/PM may proceed only after MAG-012 row proof:

- default cloud disabled;
- explicit budget required;
- one supervisor packet per escalation;
- every cloud call linked to `agent.ai_invocations`;
- cloud response can create diagnosis/proposal only, not direct action.

## 11. Acceptance

MAG-015 is complete when:

1. E1/E1a can implement MAG-010..MAG-012 without guessing schemas, ownership,
   state transitions, redaction, or failure behavior.
2. E2/E3 can test MAG-013/MAG-016 against a concrete allowlist and forbidden
   endpoint list.
3. E4 can prove MAG-014 with a Linux nonzero-row acceptance query.
4. MAG-017/MAG-018 can render read-only degraded OpenClaw views without raw
   table stitching.
5. MAG-019 has a cloud budget and ledger policy that defaults to no cloud call
   and records every allowed model request.

## 12. Explicit Non-Goals

- no scanner authority-mode change;
- no Agent Decision Spine primary/canary behavior;
- no Telegram/WebChat/mobile relay enablement;
- no proposal write endpoint enablement;
- no live/demo risk or strategy mutation;
- no Decision Lease flag flip;
- no runtime rebuild, restart, deploy, DB write, or migration apply as part of
  this contract artifact.

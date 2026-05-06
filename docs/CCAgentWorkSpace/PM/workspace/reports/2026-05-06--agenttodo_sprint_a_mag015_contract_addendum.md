# AgentTodo Sprint A MAG-015 Contract Addendum

Date: 2026-05-06
Role: PM
Status: MAG-015 DONE; MAG-010..014 next

## Scope

Started AgentTodo Sprint A from MAG-015 as requested. This batch froze the
contract addendum for the durable event-store and read-only OpenClaw foundation.

Primary artifact:

- `docs/architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md`

## Result

MAG-015 now defines:

- `LocalObservation` and `EvidenceRef`;
- backend view envelope, `SelfStateSnapshot`, and `Diagnosis`;
- `EscalationPacket` and default-disabled cloud budget policy;
- `Proposal`, `ApprovalDecision`, and `ChannelEvent` schemas for later phases;
- Sprint A endpoint allowlist: active only `GET /api/v1/openclaw/status` and `GET /api/v1/openclaw/self-state`;
- deferred read endpoints and deferred write endpoints;
- forbidden endpoint classes for OpenClaw route/client code;
- store ownership for `agent.messages`, `agent.state_changes`, `agent.ai_invocations`, OpenClaw view models, proposal/approval/channel objects, and Rust execution;
- state transitions for observations, self-state snapshots, diagnoses, escalations, proposals, approvals, channel events, and event-store writes;
- concrete MAG-010..MAG-019 implementation packet.

## PM Decision

MAG-015 is accepted as the Sprint A contract input.

Next work should proceed to MAG-010 / MAG-011 / MAG-012 only as a durable
event-store wave. MAG-016 / MAG-017 may not expose write/proposal endpoints.
MAG-018 must render read-only backend-authored view models. MAG-019 cloud
supervisor work remains blocked until `agent.ai_invocations` row proof exists.

## Runtime Reality

Fact:

- Mac and Linux source were clean and aligned at `6dc4f810` before edits.
- Linux watchdog with correct repo `cd` reported `engine_alive=true`; demo/live fresh; paper inactive by design.
- Passive healthcheck returned FAIL for known runtime/data gaps including `[4]`, `[42]`, `[42b]`, `[42c]`, `[50]`, and `[Xb]`.

Inference:

- These runtime FAIL lines do not block MAG-015 because this batch is docs/meta only.
- They do block any claim that Sprint A implementation or OpenClaw runtime readiness is complete.

## Updated Files

- `CLAUDE.md`
- `TODO.md`
- `docs/CLAUDE_CHANGELOG.md`
- `docs/README.md`
- `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`
- `docs/architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md`
- `docs/CCAgentWorkSpace/PM/memory.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-06--agenttodo_sprint_a_mag015_contract_addendum.md`
- `docs/CCAgentWorkSpace/Operator/2026-05-06--agenttodo_sprint_a_mag015_contract_addendum.md`

## Boundary

No runtime, DB schema, DB write, strategy/risk config, live authorization,
Decision Lease flag flip, Gateway channel enablement, proposal write endpoint,
rebuild, restart, or deploy action was performed.

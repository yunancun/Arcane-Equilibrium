# AgentTodo Sprint A MAG-019 Supervisor Cloud Ledger Policy Report

Date: 2026-05-06
Owner: PM
Status: Complete; Mac/Linux policy contract tests passed

## Scope

- Added `openclaw_supervisor_policy.py`.
- Wired OpenClaw `model_budget` view-model output to the supervisor policy
  snapshot.
- Implemented bounded supervisor escalation packets with prompt hash,
  budget decision, model request, diagnosis IDs, proposal IDs, and status.
- Implemented pre-cloud-call `AgentEventStore.record_ai_invocation` reservation
  for allowed packets.

## Policy Boundary

- Cloud is default-disabled by `OPENCLAW_SUPERVISOR_CLOUD_ENABLED=0`.
- Explicit budget and model/provider config are required before any allowed
  cloud call.
- The policy module does not call cloud/network providers.
- Local agents do not call cloud independently through this policy; the only
  allowed path is a supervisor packet.
- A failed `agent.ai_invocations` reservation makes the packet failed/degraded
  instead of silently succeeding.

## Verification

- Mac: targeted pytest for `test_openclaw_supervisor_policy.py`,
  `test_openclaw_agent_control_static.py`, `test_openclaw_routes.py`, and
  `test_agents_routes.py` passed 45/0.
- Linux `trade-core` fast-forwarded to `65a4279f`.
- Linux: same targeted pytest passed 45/0.
- Mac/Linux `py_compile` passed for touched OpenClaw policy/route/test files.
- Mac/Linux `node --check` passed for `openclaw-agent-control.js`.
- `git diff --check` passed before commit.

## Remaining Gate

AgentTodo Sprint A is closed. No cloud provider call, write/proposal endpoint,
browser/server restart, deploy/rebuild, live auth, production continuous
event-store flag, or trading authority change was performed. Next AgentTodo
gate is M2 MAG-020..026 Scanner Advisory Conversion.

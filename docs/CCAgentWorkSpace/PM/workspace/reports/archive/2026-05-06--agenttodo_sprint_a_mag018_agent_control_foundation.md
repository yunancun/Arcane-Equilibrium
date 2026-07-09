# AgentTodo Sprint A MAG-018 Agent Control GUI Foundation Report

Date: 2026-05-06
Owner: PM
Status: Complete; Mac/Linux static contract tests passed

## Scope

- Added a read-only OpenClaw Agent Control foundation to `tab-agents.html`.
- Added `openclaw-agent-control.js`.
- The new panel consumes only:
  - `GET /api/v1/openclaw/status`
  - `GET /api/v1/openclaw/self-state`
- It renders authority lockdown, gateway/channel posture, local topology,
  event-store row proof, model-budget posture, and degraded/error state from
  backend-authored view models.

## Frontend Boundary

- No manual trading control was added.
- No proposal or approval UI was added.
- No frontend raw join over `agent.messages`, `agent.state_changes`, or
  `agent.ai_invocations` was added.
- OpenClaw request context headers are sent for console reads:
  `source`, `channel`, `sender`, `auth_profile`, and `request_id`.

## Verification

- Mac: targeted pytest for `test_openclaw_agent_control_static.py`,
  `test_openclaw_routes.py`, and `test_agents_routes.py` passed 38/0.
- Linux `trade-core` fast-forwarded to `12d3f3ff`.
- Linux: same targeted pytest passed 38/0.
- Mac/Linux `node --check` passed for `openclaw-agent-control.js`.
- Mac/Linux `py_compile` passed for touched OpenClaw route/model/main/test files.
- `git diff --check` passed before commit.

## Remaining Gate

MAG-018 is closed for source + Mac/Linux static proof. No browser/server restart
or deploy was performed. Next Sprint A work is MAG-019 supervisor cloud
escalation ledger policy.

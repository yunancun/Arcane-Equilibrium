# AgentTodo Sprint A MAG-016/017 OpenClaw Read-Only Foundation Report

Date: 2026-05-06
Owner: PM
Status: Complete; Mac/Linux route contract tests passed

## Scope

- Added `openclaw_models.py` for the MAG-015 OpenClaw envelope contract.
- Added `openclaw_routes.py` with only:
  - `GET /api/v1/openclaw/status`
  - `GET /api/v1/openclaw/self-state`
- Registered the router in `app/main.py`.
- The response payloads are backend-authored and include authority posture,
  gateway/channel posture, runtime summary, event-store recent row proof,
  governance posture, model-budget posture, open blockers, and self-state
  sections.

## Authority Boundary

- OpenClaw routes remain read-only.
- No proposal, approval, order, live auth, secret, deploy, restart, shell, or
  config-mutation endpoint was added.
- Missing OpenClaw request context downgrades read requests to degraded posture.
- PG outage returns a 200 degraded envelope; required zero recent event-store
  rows are fail-visible.

## Verification

- Mac: `python3 -m pytest test_openclaw_routes.py test_agents_routes.py -q`
  passed 33/0.
- Linux `trade-core` fast-forwarded to `cbb225b7`.
- Linux: same targeted pytest passed 33/0.
- Mac/Linux `py_compile` passed for the touched OpenClaw route/model/main/test
  files.
- Static tests prove the Sprint A allowlist is exactly two GET routes and the
  route source has no write SQL or forbidden proxy markers.

## Remaining Gate

MAG-016/017 are closed for source + Mac/Linux route contract proof. No service
restart or deploy was performed. Next Sprint A work is MAG-018 Agent Control GUI
foundation, followed by MAG-019 supervisor cloud escalation ledger policy.

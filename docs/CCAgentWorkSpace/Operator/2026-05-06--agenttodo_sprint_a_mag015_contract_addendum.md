# AgentTodo Sprint A MAG-015 Contract Addendum

Date: 2026-05-06
Role: PM
Status: MAG-015 DONE; MAG-010..014 next

## Result

AgentTodo Sprint A has started from MAG-015. The contract addendum is frozen at:

- `docs/architecture/multi_agent_rework_2026-05-05/2026-05-06--mag015_sprint_a_contract_addendum.md`

It defines the required contracts for:

- local agent observations and evidence refs;
- OpenClaw read-only backend view models;
- supervisor escalation packets and cloud budget defaults;
- proposal / approval / channel schemas for later phases;
- active/deferred OpenClaw endpoint allowlist;
- forbidden endpoint classes;
- store ownership;
- state transitions;
- MAG-010..MAG-019 implementation packet.

## Next

Next Sprint A work is MAG-010 / MAG-011 / MAG-012: durable event-store wiring
for `agent.messages`, `agent.state_changes`, and `agent.ai_invocations`.

MAG-016 / MAG-017 stay read-only. Proposal writes, approval relay,
Telegram/WebChat/mobile, and cloud supervisor calls remain blocked until the
durable agent rows exist and E2/E4 acceptance passes.

## Runtime Reality

Linux watchdog was healthy for demo/live during handoff. Passive healthcheck is
still FAIL on known runtime/data gaps, so this is not a runtime readiness sign-off.

## Boundary

Docs/meta only. No runtime, DB schema, DB write, strategy/risk config, live auth,
Decision Lease flag, Gateway channel, proposal endpoint, rebuild, restart, or
deploy action was performed.

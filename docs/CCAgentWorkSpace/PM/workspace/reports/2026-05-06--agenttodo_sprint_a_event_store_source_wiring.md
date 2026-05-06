# AgentTodo Sprint A MAG-010..014 Source Wiring Report

Date: 2026-05-06
Owner: PM
Status: Source wiring complete; Linux controlled row proof passed

## Scope

- Added default-off `AgentEventStore` as the single writer for `agent.messages`, `agent.state_changes`, and `agent.ai_invocations`.
- Wired `MessageBus` to an advisory `message_sink`; delivery remains before subscriber side effects, and sink failure does not block delivery.
- Wired `BaseAgent` lifecycle and `Conductor.set_agent_state` to state-change persistence.
- Wired Strategist, Guardian, and Analyst local Ollama call paths to AI invocation persistence with prompt hash, response hash, model, tier, latency, purpose, and redacted details.
- Added `[52] agent_event_store_rows` passive healthcheck for enabled runtime row proof.

## Boundary

`MessageBus` remains a legacy/advisory local trace and is not promoted into the Agent Decision Spine. Event-store writes are observability-only and fail-soft. Raw prompt, raw response, tokens, secrets, cookies, and stack traces are not persisted.

## Verification

- `python3 -m pytest ...` targeted new + affected tests: 215 passed.
- `python3 -m py_compile` for touched runtime and healthcheck modules: PASS.
- `git diff --check`: PASS.
- Linux `trade-core` fast-forward to `91379cd2`: targeted pytest 215 passed and
  touched-module `py_compile` passed.
- MAG-013/014 row proof: strict `[52]` first failed with
  `messages=0 state_changes=0 ai_invocations=0`; controlled smoke then wrote
  `messages=2 state_changes=11 ai_invocations=2`; strict `[52]` passed.
- State proof includes `scout`, `strategist`, `guardian`, `analyst`, `executor`,
  `conductor`, and `conductor:*` rows.

## Remaining Gate

MAG-010..014 are closed for source + controlled Linux row proof. No service restart
or production continuous flag was applied. Supervisor cloud escalation ledger remains
MAG-019, and read-only OpenClaw foundation starts at MAG-016/017.

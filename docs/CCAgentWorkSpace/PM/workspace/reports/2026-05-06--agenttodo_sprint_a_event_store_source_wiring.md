# AgentTodo Sprint A MAG-010..014 Source Wiring Report

Date: 2026-05-06
Owner: PM
Status: Source wiring complete; Linux runtime row proof pending

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

## Remaining Gate

MAG-010..012 are not marked DONE because the acceptance requires Linux runtime fresh rows. MAG-013/014 next step is to push/pull to Linux, run targeted Linux tests, and then enable/validate `[52]` row proof without changing trading authority.

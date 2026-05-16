# Agent Context Loading

Purpose: define where project context lives after the 2026-05-16 memory
slimming decision. Agent memory files should stay small and operational; stable
project context belongs in README/docs, and current work state belongs in
TODO.

## Source-of-truth map

| Need | Read |
|---|---|
| Operating personality, hard boundaries, workflow | `CLAUDE.md` and, for Codex, `.codex/MEMORY.md` |
| Stable project overview, architecture entry, GUI, scripts | `README.md` |
| Current active state, blockers, queue, schedules | `TODO.md` |
| Domain vocabulary | `CONTEXT.md` and `docs/agents/domain.md` |
| Accepted architecture decisions | relevant files under `docs/adr/` |
| Implementation plans / sign-off evidence | linked reports under `docs/CCAgentWorkSpace/*/workspace/reports/` |
| Role profile/memory structure | `docs/agents/role-profile-memory-standard.md` |
| Historical completed detail | linked files under `docs/archive/` |
| Deep old inventory / RCA | `OPENCLAW_INVENTORY_CONSOLIDATED.md`, on demand only |

## Default loading route

Every agent session starts from the local operating memory, then routes to the
right project sources:

1. Read the applicable memory file: `CLAUDE.md` for Claude agents;
   `.codex/MEMORY.md` for Codex after `AGENTS.md`.
2. Read `README.md` for stable project shape and source routing.
3. Read this file when deciding whether more context is required.
4. Read `TODO.md` by default for code, deploy, runtime, planning, sign-off,
   review, or unclear-continuity work.
5. Skip `TODO.md` only for narrow stable-context questions where current state
   cannot affect the answer.

If in doubt, read `TODO.md`. This project has live-trading boundaries and
multi-session drift risk; stale active state is more dangerous than one extra
read.

## Relocation map for slimmed memory

This table records where content formerly stored in large memory files should
live. Do not delete a memory section unless its destination below already
captures the same decision surface or the deletion is explicitly called out.

| Old memory content | Destination |
|---|---|
| Product name, OpenClaw positioning, Bybit-only target | `README.md`, `CONTEXT.md`, ADR-0013/0014 |
| 16 root principles and live hard boundaries | compact form in memory; full governance in `CLAUDE.md` plus ADR/governance docs |
| Runtime PID, env, healthcheck timestamps, active blockers | `TODO.md` latest-state sections |
| Wave / sprint progress and closed work ledgers | `TODO.md` short active markers; full detail in reports/archive |
| Architecture overview and service family map | `README.md`, `docs/architecture/*`, ADRs |
| Paths, scripts, deploy entry points | `README.md`, `helper_scripts/SCRIPT_INDEX.md`, `.codex/DEPLOYMENT.md` |
| Dispatch chains and sub-agent role binding | `CLAUDE.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md` |
| TODO maintenance rules | `docs/agents/todo-maintenance.md` |
| Agent profile/memory hygiene | `docs/agents/role-profile-memory-standard.md` |
| External tool posture | `README.md`, `docs/agents/issue-tracker.md`, compact memory reminder |
| Long historical lessons | `memory/MEMORY.md`, specific `memory/*.md`, reports/archive |

## Update rules

- When changing current state, update `TODO.md`, not README or memory.
- When changing stable architecture or project entry points, update `README.md`
  and the relevant architecture/ADR docs.
- When changing agent behavior, update memory plus the relevant agent startup
  file.
- When changing role profile or memory structure, update
  `docs/agents/role-profile-memory-standard.md`.
- When changing TODO format or lifecycle, update
  `docs/agents/todo-maintenance.md` and then the memory reminder.
- Do not mirror the same long status paragraph across memory, README, and
  TODO. Use one source of truth plus links.

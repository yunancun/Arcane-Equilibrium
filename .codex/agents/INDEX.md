# Codex Agent Index

Codex role files mirror the Claude agent roster while adapting it to Codex sub-agent types.

## Roster

| Role | Codex type | Source |
|---|---|---|
| `A3` | `default` | `.claude/agents/A3.md` |
| `AI-E` | `default` | `.claude/agents/AI-E.md` |
| `BB` | `default` | `.claude/agents/BB.md` |
| `CC` | `default` | `.claude/agents/CC.md` |
| `E1` | `worker` | `.claude/agents/E1.md` |
| `E1a` | `worker` | `.claude/agents/E1a.md` |
| `E2` | `explorer` | `.claude/agents/E2.md` |
| `E3` | `explorer` | `.claude/agents/E3.md` |
| `E4` | `worker` | `.claude/agents/E4.md` |
| `E5` | `explorer` | `.claude/agents/E5.md` |
| `FA` | `default` | `.claude/agents/FA.md` |
| `MIT` | `default` | `.claude/agents/MIT.md` |
| `PA` | `default` | `.claude/agents/PA.md` |
| `PM` | `default` | `.claude/agents/PM.md` |
| `QA` | `worker` | `.claude/agents/QA.md` |
| `QC` | `default` | `.claude/agents/QC.md` |
| `R4` | `explorer` | `.claude/agents/R4.md` |
| `TW` | `worker` | `.claude/agents/TW.md` |

## Usage

- Read the role file here first.
- Then read the linked Claude source file for full role detail.
- Then load the referenced skill files from `.claude/skills/`.
- Every Codex role also follows the universal preload below before acting.

## Universal Preload

Required for every Codex role:

- `CLAUDE.md` — shared operating memory, boundaries, workflow.
- `.codex/MEMORY.md` — Codex-specific operating memory and dispatch rules.
- `README.md` — stable project entry and current canonical surfaces.
- `docs/agents/context-loading.md` — decides when to load `TODO.md` and extra docs.
- `TODO.md` for code / deploy / runtime / planning / sign-off / review / unclear continuity.
- `.codex/AGENT_DISPATCH_PROTOCOL.md` before dispatching or receiving delegated work.
- `docs/agents/todo-maintenance.md` before editing `TODO.md`.

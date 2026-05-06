# Documentation Path Redirect Plan

Date: 2026-05-06
Status: planning index only; no paths have been moved by this file.

This file records the safe rename / relocation plan recommended by R4. It is
intentionally a redirect plan, not an executed migration, because many current
documents are referenced by agent boot rules, SQL migration comments, root docs,
and GUI/API development plans.

## Freeze First

Do not move these paths until the redirect map, front matter, and GUI consumers
are stable:

- `CLAUDE.md`
- `TODO.md`
- `CONTEXT.md`
- `AGENTS.md`
- `.codex/*`
- `memory/*`
- `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`
- `docs/CCAgentWorkSpace/*/workspace/reports/*`
- `docs/governance_dev/*`

## Target Taxonomy

| Target | Purpose |
|---|---|
| `docs/00-active/` | Curated active status, backlog, active plan pointers |
| `docs/01-architecture/` | Architecture overlays, ADRs, system boundary docs |
| `docs/02-execution-plans/` | REF, MAG, sprint, wave, and phase plans grouped by initiative |
| `docs/03-governance/` | Governance specs, amendments, registers, formal policies |
| `docs/04-audits/` | Audit and verdict reports |
| `docs/05-agent-workspace/` | Role profiles, memories, reports, and operator copies |
| `docs/06-runbooks/` | Deploy, disaster, first-day-live, and healthcheck SOPs |
| `docs/07-reference/` | Stable technical background and external references |
| `docs/08-worklogs/` | Chronological engineering logs |
| `docs/90-archive/` | Stale extracts, snapshots, superseded plans |
| `docs/_indexes/` | Machine-readable inventories, redirect maps, GUI metadata |

## Candidate Redirects

| Current path | Future canonical path | Timing |
|---|---|---|
| `docs/architecture/2026-05-06--openclaw_control_plane_repositioning.md` | `docs/01-architecture/openclaw/2026-05-06--openclaw--architecture-overlay--control-plane-repositioning.md` | after active references updated |
| `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md` | `docs/02-execution-plans/openclaw-console/2026-05-06--openclaw-console--gui-plan.md` | after GUI metadata endpoint lands |
| `docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md` | `docs/02-execution-plans/openclaw-gateway/2026-05-06--openclaw-gateway--development-plan.md` | after OpenClaw status APIs land |
| `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md` | `docs/02-execution-plans/ref21/2026-05-06--ref21--execution-plan--full-chain-replay-v1-3.md` | after REF-21 supersession metadata lands |
| `docs/execution_plan/2026-05-06--ref21_gui_ux_spec_v1_1.md` | `docs/02-execution-plans/ref21/2026-05-06--ref21--gui-spec--replay-ux-v1-1.md` | after replay GUI consumers use metadata |
| `docs/audit/*` | `docs/04-audits/legacy/*` | cold batch after redirect stubs |
| `docs/audits/*` | `docs/04-audits/*` | cold batch after redirect stubs |
| `.claude_reports/*.md` | `docs/90-archive/generated/claude-reports/*.md` | cold batch after no active references |

## Redirect Stub Template

When a file is eventually moved, keep a small stub at the old path for at least
one release cycle:

```markdown
# Moved

This document moved to:

- `<new path>`

Metadata:
- moved_at: YYYY-MM-DD
- superseded_by: `<new path>`
- redirect_owner: PM
```

## GUI Integration Priority

High-value hot interaction candidates:

- `TODO.md`
- `CLAUDE.md`
- `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md`
- `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`
- `docs/execution_plan/2026-05-06--openclaw_gateway_development_plan.md`
- `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md`
- `docs/execution_plan/2026-05-06--ref21_gui_ux_spec_v1_1.md`

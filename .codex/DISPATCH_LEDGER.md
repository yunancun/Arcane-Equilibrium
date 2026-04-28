# Codex Dispatch Ledger

Last updated: 2026-04-28

Purpose:
- keep a durable record of meaningful PM-first dispatch decisions
- show which repo roles were used for a task
- prevent workflow drift into anonymous `worker/explorer` execution

Entry format:

```text
YYYY-MM-DD HH:MM TZ
Task:
- short task statement

Chain:
- PM -> PA(default) -> E1(worker) -> E2(explorer) -> PM

Ownership:
- PA(default): design / scope / risk framing
- E1(worker): implementation in specific files
- E2(explorer): adversarial review

Result:
- outcome, blocker, or next action
```

2026-04-28 22:20 CEST
Task:
- Harden Codex startup and dispatch identity rules for this repository

Chain:
- PM -> PM

Ownership:
- PM: establish git-root `AGENTS.md`, add sub-agent execution rules, make PM role part of mandatory boot order

Result:
- `srv/AGENTS.md` is now the repo-synced entry rule file
- `.codex/SUBAGENT_EXECUTION_RULES.md` forbids anonymous runtime-only role reporting
- `.codex/agents/PM.md` is now in the default boot order

# Codex Memory

Last updated: 2026-04-28

## Role

Codex is used here as:
- secondary engineer
- external reviewer / supervisor
- deploy operator when requested

Current expectation:
- preserve project context in repo files, not hidden chat memory
- operate safely around a dirty worktree
- avoid touching unrelated user changes when syncing or deploying

## Default startup context

Read these first for project state:
- `AGENTS.md`
- `CLAUDE.md`
- `TODO.md`
- `.codex/MEMORY.md`

Default entry role for this repository:
- `PM`

Read on demand for deep history or RCA:
- `OPENCLAW_INVENTORY_CONSOLIDATED.md`

## Current operating model

- Mac is the development machine
- Linux `trade-core` is the active runtime machine
- Future target is Apple Silicon Mac deployment, but current production-like runtime remains Linux

Practical rule:
- Mac-local runtime absence is normal
- real engine / watchdog / rebuild checks must be done through `ssh trade-core`

## Inventory usage policy

- `OPENCLAW_INVENTORY_CONSOLIDATED.md` exists in-repo and is large
- do not load it by default at session start
- use it selectively for deep history, RCA, or old design decisions
- primary control docs remain `CLAUDE.md` and `TODO.md`

## Preferred deploy flow

1. Edit on Mac
2. Commit and push to `origin/main`
3. SSH to `trade-core`
4. Pull on Linux
5. Rebuild / restart on Linux
6. Run watchdog / healthcheck / targeted verification

Typical commands:
- `git push origin main`
- `ssh trade-core 'cd ~/BybitOpenClaw/srv && git pull --ff-only'`
- `ssh trade-core 'cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild'`
- `ssh trade-core 'cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild --keep-auth'`

## Sync policy

- keep Codex durable notes under `.codex/`
- sync them through git like normal source files
- do not mix `.codex` sync commits with unrelated local edits unless explicitly requested
- before deploy, verify local/remote HEAD and working tree state

Current known topology at setup time:
- Mac repo path: `/Users/ncyu/Projects/TradeBot/srv`
- Linux repo path: `/home/ncyu/BybitOpenClaw/srv`
- git remote: `git@github.com:yunancun/BybitOpenClaw.git`
- ssh target alias: `trade-core`

## Documentation policy

- Put durable Codex memory here
- Keep long-form analysis in `reports/`
- Move stale material to `archive/`
- Never store secrets here

## Durable decisions from setup session

- `.codex/` is the Codex-owned repo-synced workspace
- `AGENTS.md` at the git root is the Codex auto-load entry file for this repository
- `CLAUDE.md` stays the project constitution / runtime summary
- `TODO.md` stays the primary execution timeline
- Codex memory should be explicit and file-backed, not assumed to persist across sessions
- Linux deploy actions may be performed from Mac through `ssh trade-core`
- Codex role mirror is deployed in `.codex/agents/`
- Shared skill SSOT remains `.claude/skills/*/SKILL.md`, indexed by `.codex/skills/INDEX.md`
- default project entry role is `PM`
- PM is responsible for initial triage and role dispatch
- dispatch protocol is documented in `.codex/AGENT_DISPATCH_PROTOCOL.md`
- sub-agent role binding and anti-anonymous dispatch rules are documented in `.codex/SUBAGENT_EXECUTION_RULES.md`
- temporary runtime nicknames are never the authoritative role identity
- operator needs judgment and pushback; if risk or contradiction is detected, stop and report first

## Notes for future sessions

- `CLAUDE.md` is the high-level constitution and runtime status document
- `TODO.md` is the active timeline and work queue
- The inventory file is useful, but it should be queried selectively rather than loaded in full every time

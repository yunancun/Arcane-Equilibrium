# Cold Audit Baseline Freeze

## FACT

- Requested audit date: `2026-05-17`.
- Actual PM freeze timestamp: `2026-05-28T23:28:56Z` / `2026-05-29T01:28:56+0200`.
- Canonical repo root: `/Users/ncyu/Projects/TradeBot/srv`.
- Local branch at freeze: `main`.
- Local HEAD at freeze: `9bf71423a0c3251ef56393c7b0e137f45f3127ff`.
- Origin `main` observed by read-only `git ls-remote --heads origin main`: `b9bb6735698a15072746b014ea0ef80253ccb7e5`.
- Linux runtime source observed by read-only `ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git rev-parse HEAD && git branch --show-current && git status --porcelain=v1 -b'`:
  - branch: `main`
  - HEAD: `b9bb6735698a15072746b014ea0ef80253ccb7e5`
  - status: `## main...origin/main`
- Local dirty worktree at freeze by `git status --porcelain=v1 -b`:
  - `## main...origin/main [ahead 1]`
  - ` M docs/CCAgentWorkSpace/E1/memory.md`
  - ` M docs/CCAgentWorkSpace/E2/memory.md`
  - ` M docs/CCAgentWorkSpace/MIT/memory.md`
- A concurrent source movement was observed during boot: local `HEAD` was first observed as `b9bb6735698a15072746b014ea0ef80253ccb7e5`, then at freeze as `9bf71423a0c3251ef56393c7b0e137f45f3127ff`.
- PM used read-only remote inspection (`git ls-remote`) instead of `git fetch`; actual `git fetch` was not run because it would write `.git/FETCH_HEAD` during a read-only audit.

## Active Source Of Truth Files

- `AGENTS.md`
- `CLAUDE.md`
- `README.md`
- `TODO.md`
- `CONTEXT.md`
- `.codex/MEMORY.md`
- `.codex/agents/PM.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/INDEX.md`
- `docs/agents/context-loading.md`
- `docs/agents/todo-maintenance.md` before final `TODO.md` edits
- `docs/adr/*`
- `docs/governance_dev/SPECIFICATION_REGISTER.md`
- `helper_scripts/SCRIPT_INDEX.md`
- Existing role workspace reports under `docs/CCAgentWorkSpace/*/workspace/reports/`
- Archive references under `docs/archive/`

## Runtime Inclusion

Runtime is included for read-only evidence only.

Allowed runtime command envelope:

- `ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && git ... read-only inspection ...'`
- `ssh trade-core 'systemctl --user status/is-active ...'`
- `ssh trade-core 'pgrep/ps/readlink/sha256sum/stat/find/ls/grep/sed/head/tail read-only inspection ...'`
- `ssh trade-core 'psql ... SELECT-only reflection ...'`
- `ssh trade-core 'curl GET-only health/read endpoints ...'`

Explicitly forbidden runtime actions:

- rebuild
- restart
- deploy
- migration apply
- DB schema mutation
- auth renewal or auth file edits
- secret edits or credential rotation
- live/demo/paper trading mutation
- TOML live/risk/strategy config mutation

## Report Naming Rules

- Role reports stay in `docs/CCAgentWorkSpace/<ROLE>/workspace/reports/`.
- Required report date prefix remains `2026-05-17--` per operator request even though the actual freeze occurred on 2026-05-28/29.
- Each finding must mark `FACT`, `INFERENCE`, or `ASSUMPTION`.
- Each finding must include severity, affected path and line, evidence command or inspection method, impact, false-positive defense, suggested fix direction, fix owner role, and verification owner role.
- P0/P1 items must be locally rechecked by PA or cross-confirmed by another bound role before entering PA final plan.

## Inference

- Local Mac source is ahead of both origin and Linux runtime by one commit at freeze, so any source/runtime drift finding must distinguish local source truth from deployed/runtime truth.
- Existing uncommitted role memory edits are not part of this audit unless a later role proves they affect the requested evidence surface.

## Assumption

- Report file creation and the final PM/TODO audit tracking edits are allowed output artifacts of this read-only audit. No code, runtime, auth, schema, live/demo/paper, risk, strategy, or TOML behavior changes are allowed.

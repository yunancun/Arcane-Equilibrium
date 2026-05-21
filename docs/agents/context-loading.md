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

## PG Connection Examples (Linux runtime authoritative)

PostgreSQL empirical dry-run + reflection is mandatory before any V###
migration sign-off (per CLAUDE.md `Data, Migrations, And Validation`). Mac
sandbox uses pytest with mocked DB; Mac mock cannot catch runtime PG semantic
(PL/pgSQL constraints, schema drift, sqlx checksum mismatch).

Use these patterns on Linux `trade-core` runtime only:

### Standard psql connect (via systemd-managed PG)

```bash
ssh trade-core 'sudo -u postgres psql -d openclaw -c "SELECT current_database(), version();"'
```

### Schema reflection example (V### dry-run)

```bash
# Verify column existence before ADD COLUMN IF NOT EXISTS
ssh trade-core 'sudo -u postgres psql -d openclaw -c "
  SELECT column_name, data_type
  FROM information_schema.columns
  WHERE table_schema=$$learning$$ AND table_name=$$hypotheses$$
  ORDER BY ordinal_position;
"'

# Verify migration head (sqlx checksums)
ssh trade-core 'sudo -u postgres psql -d openclaw -c "
  SELECT version, success, checksum, execution_time
  FROM _sqlx_migrations
  ORDER BY version DESC
  LIMIT 5;
"'
```

### Idempotency double-apply test

```bash
# Apply V### twice on Linux PG; second apply must be a no-op (per Guard A/B/C)
ssh trade-core 'cd ~/openclaw && cargo sqlx migrate run --database-url $DATABASE_URL'
ssh trade-core 'cd ~/openclaw && cargo sqlx migrate run --database-url $DATABASE_URL'
```

### Engine restart empirical test (per a19797d sqlx hash drift 2026-05-02)

```bash
# After V### apply, restart engine and confirm migration head matches
ssh trade-core 'bash ~/openclaw/helper_scripts/restart_all.sh --rebuild'
ssh trade-core 'sudo -u postgres psql -d openclaw -c "SELECT version FROM _sqlx_migrations ORDER BY version DESC LIMIT 1;"'
```

### Hypertable + retention reflection (TimescaleDB)

```bash
ssh trade-core 'sudo -u postgres psql -d openclaw -c "
  SELECT hypertable_name, num_chunks, compression_enabled
  FROM timescaledb_information.hypertables
  WHERE hypertable_schema = $$learning$$;
"'
```

**Rules**:

- Always use `ssh trade-core` prefix; do not run `psql` against Mac (no PG on
  Mac per memory `project_dev_runtime_split`).
- Use `sudo -u postgres` for admin-level reflection; never embed user/password
  in command line.
- Use `$$...$$` dollar-quoted strings inside SQL to avoid bash quote escaping
  (per memory `feedback_shell_paste_safety` 2026-04-21).
- For PR sign-off, capture `_sqlx_migrations.version` head + V### checksum +
  engine restart output as evidence (per V055 5-round loop 2026-05-05 lesson).

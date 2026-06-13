# 2026-06-13 — L2 V138/V139 activation runtime

## Verdict

`PASS-APPLIED`.

Operator approved the low-risk V138/V139 activation window. PM executed the engine-only auto-migrate path and verified the result on Linux `trade-core`.

Scope remained limited to V138/V139:

- no CI
- no rebuild
- no manual `psql -f`
- no manual V140
- no agent memory seed
- no L2 memory flag-on / cron activation / embedding backfill
- no model call
- no Gate-B probe
- no auth/risk/order/trading configuration mutation

## Execution

- Runtime host: Linux `trade-core`
- Repo: `/home/ncyu/BybitOpenClaw/srv`
- Source head: `3f7e056031b04ed75c173f723fd0bc4a5bd0505f`
- Run id: `l2_v138_v139_activation_20260613T153352Z`
- Run log: `/tmp/openclaw/l2_v138_v139_activation_20260613T153352Z.log`
- Env backup: `/home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env.bak.20260613T153352Z`
- Command path: temporarily set persistent `OPENCLAW_AUTO_MIGRATE=1`, run `bash helper_scripts/restart_all.sh --engine-only --keep-auth`, trap-restore persistent `OPENCLAW_AUTO_MIGRATE=0`.

Runtime output:

- Engine stopped cleanly after `1x500ms`.
- New engine PID: `3607315`.
- `engine.sock` ready after `3x500ms`.
- `restart_all.sh` health wait: `engine_alive=true`, demo fresh, `paused=False`.
- Maintenance flag cleared by restart trap.
- Cleanup trap restored persistent `OPENCLAW_AUTO_MIGRATE=0`.

Engine startup log confirms migration execution:

- `auto_migrate: loading migrations`
- `auto_migrate: migrations parsed count=122`
- `auto_migrate: completed seeded=0 applied=2 elapsed_ms=68`
- `auto_migrate runner completed outcome=Applied(2)`

## Post-apply verification

### Migration ledger

Post-apply SQL reflection:

```text
migrations_head|139|all_success=true|count=122
migration_row|139|agent memory store|true
migration_row|138|research fdr tables|true
migration_row|137|lease ipc soak events|true
```

`repair_migration_checksum --verify`:

- `db_rows=122`
- `drift_count=0`
- `drift_versions=[]`
- V138/V139 checksum rows match.

### Objects

All expected V138/V139 objects now exist:

```text
object|research.pre_registered_hypotheses|research.pre_registered_hypotheses
object|research.alpha_wealth_ledger|research.alpha_wealth_ledger
object|research.alpha_wealth_debit_state|research.alpha_wealth_debit_state
object|agent.agent_memory|agent.agent_memory
object|agent.agent_memory_embedding_meta|agent.agent_memory_embedding_meta
```

Initial row counts are zero as expected:

```text
count|research.pre_registered_hypotheses|0
count|research.alpha_wealth_ledger|0
count|agent.agent_memory|0
count|agent.agent_memory_embedding_meta|0
```

### Passive healthchecks

Linux true DB post-check:

```bash
python3 -m helper_scripts.db.passive_wait_healthcheck.runner \
  --check 83 --check 84 --check 85 --check 86 --check 87 --check 88 --check 89
```

Result: `SUMMARY: ALL PASS`.

- `[83]`: PASS, `families=0`, bound `10`.
- `[84]`: PASS, `orphan_refunds=0`.
- `[85]`: PASS, `refund_amount_mismatches=0`.
- `[86]`: PASS, `cross_family_duplicate_specs=0`.
- `[87]`: PASS, `sealed_rows_with_post_insert_updates=0`.
- `[88]`: PASS-skip because `OPENCLAW_L2_MEMORY_PIPELINE != 1`.
- `[89]`: PASS-skip because `OPENCLAW_L2_MEMORY_EMBED_BACKFILL != 1`.

### Runtime health

- Persistent env: `OPENCLAW_AUTO_MIGRATE=0`.
- Engine process env still shows `OPENCLAW_AUTO_MIGRATE=1` because the currently running process was started for the migration window. This is expected; the migrator only runs during startup, and future restarts will read persistent env `0`.
- `OPENCLAW_ALLOW_MAINNET=0`.
- `OPENCLAW_ENABLE_PAPER=0`.
- `engine_watchdog.py --status`: `engine_alive=true`, snapshot fresh.
- `/tmp/openclaw/engine_maintenance.flag`: absent.

## Operational observations

Two non-blocking observations were present in logs:

- V138/V139 emitted `trading_ai role absent` notices. The migrations still completed successfully, ledger rows are successful, and all objects/checks are present. This is not a blocker for the current runtime DB user path.
- Shortly after restart, engine log recorded a TONUSDT structural order reject: Bybit `retCode=30228`, `No new positions during delisting`. The engine treated it as no-retry terminal failure and released the decision lease. This was not a migration failure and did not change the V138/V139 verdict, but it is worth keeping in mind if TONUSDT-related dispatch appears again.

## Remaining gates

V138/V139 activation is closed. Remaining L2 follow-ups are separate approvals:

- manual V140 pgvector apply
- `seed_agent_memory.py --dry-run` / `--apply`
- `OPENCLAW_L2_MEMORY_PIPELINE=1`
- `OPENCLAW_L2_MEMORY_CRON_APPLY=1`
- `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1`
- E2E true model call
- P2p incident sentinel credential/probe/install
- P5 feedback/quality/GUI gate

# 2026-06-13 — L2 V138/V139 activation window packet

## Verdict

`READY-FOR-OPERATOR-WINDOW / NOT EXECUTED`.

P5-SM `[82]` is no longer the blocker. The remaining requirement is an explicit operator-approved low-risk engine restart / auto-migration window. This packet is a runbook and evidence bundle only: no restart, no migration apply, no DB write, no auth/risk/order/trading mutation.

## Current read-only ground truth

Collected from Linux `trade-core` at `2026-06-13T07:44Z`.

- Source head on Linux: `de92f879d297696a34b932d9a448bc00867a69f7`, clean.
- `_sqlx_migrations`: head `137`, `all_success=true`, row count `120`.
- Recent applied rows: V137 lease ipc soak events; V136 L2 provenance columns; V135 L2 gate seam log; V134 L2 calls ledger; V133 agent lessons.
- V138/V139 target objects are absent as expected before activation:
  - `research.pre_registered_hypotheses` = `NULL`
  - `research.alpha_wealth_ledger` = `NULL`
  - `research.alpha_wealth_debit_state` = `NULL`
  - `agent.agent_memory` = `NULL`
  - `agent.agent_memory_embedding_meta` = `NULL`
- `repair_migration_checksum --verify`: `drift_count=0`, `drift_versions=[]`, V138 and V139 both `MISSING_IN_DB`.
- File SHA256 on Linux:
  - V138 `1403e9b5efcb093b8ce95a2d9e64b8dd5617f93557dc8c5d0d03452a18dc1cfd`
  - V139 `da37c52d692ad15e2e06a76f46f5fb1818879ed91b51aa79c08ec8a669db1a16`
  - manual V140 `5b53d64bbd9526a64963d7b936af454a84bd3280fb54c5024e1912d8d24307eb`
- Runtime flags: `OPENCLAW_AUTO_MIGRATE=0`; `OPENCLAW_ALPHA_WEALTH_RECONCILER`, `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT`, `OPENCLAW_L2_MEMORY_PIPELINE`, `OPENCLAW_L2_MEMORY_CRON_APPLY`, `OPENCLAW_L2_MEMORY_EMBED_BACKFILL` unset/empty.
- Safety flags checked in the same pass: `OPENCLAW_ENABLE_PAPER=0`, `OPENCLAW_ALLOW_MAINNET=0`.
- Gate-B watch latest remains unrelated wait-only: `WATCH_ONLY`, 23 candidates, 0 alertable/start/schedule.

## Pre-window healthcheck

Linux true DB narrow preflight at `2026-06-13T07:44:51Z`:

```bash
cd /home/ncyu/BybitOpenClaw/srv
set -a
source /home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env >/dev/null 2>&1
set +a
export OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv
export OPENCLAW_DATABASE_URL_FILE=/tmp/openclaw/runtime_secrets/openclaw_database_url
python3 -m helper_scripts.db.passive_wait_healthcheck.runner \
  --check 83 --check 84 --check 85 --check 86 --check 87 --check 88 --check 89
```

Result: `SUMMARY: ALL PASS`.

- `[83]-[86]`: PASS-skip because V138 tables are not deployed yet.
- `[87]`: PASS, `sealed_rows_with_post_insert_updates=0`.
- `[88]`: PASS-skip because `OPENCLAW_L2_MEMORY_PIPELINE != 1`.
- `[89]`: PASS-skip because `OPENCLAW_L2_MEMORY_EMBED_BACKFILL != 1`.

## Why this must use engine auto-migrate

The accepted path is engine startup auto-migration:

- `helper_scripts/restart_all.sh --engine-only --keep-auth` reads `OPENCLAW_AUTO_MIGRATE` from `basic_system_services.env` and passes it to the engine.
- `openclaw_engine` calls `MigrationRunner::run_if_enabled(...)` during startup.
- `MigrationRunner` only runs when `OPENCLAW_AUTO_MIGRATE=1`; otherwise it is a no-op.

Do not apply V138/V139 with raw `psql -f`. That bypasses `_sqlx_migrations`, recreates the old silent-noop class of failure, and leaves future sqlx migration state ambiguous.

## Operator-approved activation sequence

Run this only after explicit operator approval for the V138/V139 activation window. It is designed to be minimal scope: engine-only restart, keep auth, auto-restore `OPENCLAW_AUTO_MIGRATE=0` on shell exit.

```bash
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && bash -s' <<'SH'
set -euo pipefail

ENV_FILE=/home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env
BACKUP="$ENV_FILE.bak.$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$ENV_FILE" "$BACKUP"
echo "env backup: $BACKUP"

set_env_kv() {
  local key="$1" value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]
lines = path.read_text().splitlines()
out = []
seen = False
for line in lines:
    if line.startswith(key + "="):
        out.append(f"{key}={value}")
        seen = True
    else:
        out.append(line)
if not seen:
    out.append(f"{key}={value}")
path.write_text("\n".join(out) + "\n")
PY
}

cleanup() {
  set_env_kv OPENCLAW_AUTO_MIGRATE 0
  echo "OPENCLAW_AUTO_MIGRATE restored to 0"
}
trap cleanup EXIT

set_env_kv OPENCLAW_AUTO_MIGRATE 1
bash helper_scripts/restart_all.sh --engine-only --keep-auth
SH
```

Expected migration result: `_sqlx_migrations` advances from V137 to V139; V138/V139 objects exist; `OPENCLAW_AUTO_MIGRATE` is restored to `0`.

## Post-window verification

After the restart returns, run these read-only checks:

```bash
ssh trade-core 'cd /home/ncyu/BybitOpenClaw/srv && bash -s' <<'SH'
set -euo pipefail
set -a
source /home/ncyu/BybitOpenClaw/secrets/environment_files/basic_system_services.env >/dev/null 2>&1
set +a
export OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv
export OPENCLAW_DATABASE_URL_FILE=/tmp/openclaw/runtime_secrets/openclaw_database_url

rust/target/release/repair_migration_checksum --verify | tail -50

DBURL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url)
psql "$DBURL" -X -v ON_ERROR_STOP=1 -At <<'SQL'
SELECT 'migrations_head|' || max(version)::text || '|all_success=' || bool_and(success)::text || '|count=' || count(*)::text FROM _sqlx_migrations;
SELECT 'object|research.pre_registered_hypotheses|' || coalesce(to_regclass('research.pre_registered_hypotheses')::text, 'NULL');
SELECT 'object|research.alpha_wealth_ledger|' || coalesce(to_regclass('research.alpha_wealth_ledger')::text, 'NULL');
SELECT 'object|research.alpha_wealth_debit_state|' || coalesce(to_regclass('research.alpha_wealth_debit_state')::text, 'NULL');
SELECT 'object|agent.agent_memory|' || coalesce(to_regclass('agent.agent_memory')::text, 'NULL');
SELECT 'object|agent.agent_memory_embedding_meta|' || coalesce(to_regclass('agent.agent_memory_embedding_meta')::text, 'NULL');
SELECT 'v139_agent_memory_rows|' || count(*)::text FROM agent.agent_memory;
SQL

python3 -m helper_scripts.db.passive_wait_healthcheck.runner \
  --check 83 --check 84 --check 85 --check 86 --check 87 --check 88 --check 89

python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --status
SH
```

Expected post-window state:

- `_sqlx_migrations` head `139`, `all_success=true`.
- `repair_migration_checksum --verify` still `drift_count=0`; V138/V139 no longer `MISSING_IN_DB`.
- V138/V139 objects resolve to non-NULL regclasses.
- `agent.agent_memory` has 0 rows until an explicitly approved seed/apply step.
- `[83]-[87]` should remain PASS or PASS/WARN based on empty V138 data; `[88]-[89]` remain PASS-skip while memory flags stay OFF.
- Engine watchdog reports alive/fresh.

## Non-closures

- manual V140 pgvector is not part of this auto-migrate window. It requires V139 first and separate operator permission/role capability.
- `helper_scripts/memory/seed_agent_memory.py --apply` is a DB write and remains separately gated.
- `OPENCLAW_L2_MEMORY_PIPELINE=1`, `OPENCLAW_L2_MEMORY_CRON_APPLY=1`, and `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1` remain separately gated.
- E2E-1 true Ollama model call remains separately gated.
- Gate-B watch status should not block V138/V139 activation, but it also does not authorize any alpha promotion path.

## PM recommendation

When the operator approves runtime work, execute V138/V139 first as the smallest useful activation unit. Do not bundle V140, seed, memory cron, embedding backfill, E2E model call, or Gate-B actions into the same window unless separately approved; those are different blast-radius classes.

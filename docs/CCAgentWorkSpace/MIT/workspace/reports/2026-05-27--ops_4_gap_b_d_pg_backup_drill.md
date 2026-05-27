# MIT — OPS-4 GAP-B + GAP-D PG backup drill audit (2026-05-27)

**Owner**: MIT
**Spec**: `srv/docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md` §2.3 + §7.2 + §10 GAP-B / GAP-D
**Scope**: empirical Linux runtime audit (ssh trade-core) — current backup posture + restore-path proof + cron + script drafts
**Boundary**: spec-only; NO crontab modification; NO main DB mutation; sandbox dropped at end
**Draft artifacts**: `srv/docs/CCAgentWorkSpace/MIT/workspace/drafts/ops4_gap_b_d/{install_pg_dump_cron.sh,trading_ai_pg_dump_cron.sh,verify_pg_dump.sh}`

---

## §1 — GAP-B 現況 evidence

### 1.1 Backup 目錄盤點 (ssh trade-core empirical)

| Path | 狀態 | 內容 |
|---|---|---|
| `/home/ncyu/BybitOpenClaw/backups/` | 存在但空 | 0 files (2 dirs only) |
| `/home/ncyu/BybitOpenClaw/srv/backups/` | 存在 1 file | `trading_ai_pre_phase0a_20260404_180411.dump` (189KB, 53d old, custom PG format, 118 TOC entries) |
| `/home/ncyu/pg_backups/` | **不存在** | — |
| `/mnt/nas` / `/nas` | **未掛載** | NFS daemon up, 無 client mount (`project_hardware_constraints` 10GbE 40TB NAS not mounted on trade-core) |
| `helper_scripts/db/` | 無 backup tooling | 0 of `pg_dump.sh` / `restore.sh` / `dr_*.sh` |
| `helper_scripts/cron/` | 無 backup cron | 23 cron scripts, 0 PG dump |

### 1.2 Crontab pg_dump 條目 (ssh trade-core `crontab -l`)

- 46 行 total
- **0 行 active pg_dump / backup entry**
- 唯一 match 是 Ubuntu 預設 sample comment `# 0 5 * * 1 tar -zcf /var/backups/home.tgz /home/` (commented)
- **15d retention 不存在** (根本無 dump 在跑)

### 1.3 PG runtime + tooling capability

| Item | Status |
|---|---|
| PG container | `trading_postgres` (timescale/timescaledb:latest-pg16, **up 6 weeks healthy**) |
| trading_ai 大小 | **226 GB** |
| Host `pg_dump` 版本 | 16.14 — 與 container 16.13 相容 ✓ |
| 磁碟可用 | `/dev/nvme0n1p8` 1.4T total / 841G free (3.7× DB size) |

### 1.4 結論

**GAP-B 現況 = BLOCKER for first-day live**：DB backup posture 是 single 53-day-old 189KB schema-only pre-phase0a dump，不是 DR 級。RPO 對於 `trading.fills` / `trading.intents` / `learning.governance_audit_log` 等永久保留資料 = **無限**。spec §2.2 "PG 主庫毀損 → 待 backup restore（GAP B）" — empirical 確認此 gap 真實存在。

---

## §2 — GAP-B restore drill empirical 結果

### 2.1 Drill 設計

對既有 `trading_ai_pre_phase0a_20260404_180411.dump` 跑 **schema-only restore** 到 sandbox，驗證 restore path 工作。不對全 226GB 跑 full data restore（會需 ~30+ min + 226GB scratch + GAP-D land 後才有 fresh dump 可測）。

### 2.2 Drill 執行 (ssh trade-core 2026-05-27 21:02 UTC)

```
sandbox = sandbox_restore_drill_20260527_2102
CREATE DATABASE sandbox_restore_drill_20260527_2102 TEMPLATE template0;  -- 避 template1 collation warning
pg_restore --schema-only --no-owner --no-privileges -d sandbox_restore_drill_20260527_2102 <dump>
   → exit 0 silent / real 0.090s
```

### 2.3 Verify

| Item | 值 |
|---|---|
| Restored public 表數 | 14 |
| Primary keys / CHECK / FK | 14 / 2 / 0 |
| Restore exit code | 0 (clean) |

`DROP DATABASE IF EXISTS sandbox_restore_drill_20260527_2102;` OK，主庫不動。

### 2.4 觀察

- **Restore path 本身工作**：host pg_dump 16.14 → docker container PG 16.13 兼容性已驗
- dump **結構性過時**：4/4 dump 是 V001 級 schema，缺 `trading` / `learning` / `governance` / `system` / `observability` / `replay` / `market` 7 namespace + ~120+ V### tables
- GAP-B "restore drill" **不能用此 dump 當 first-day live readiness 證據**；必先 GAP-D land 拿 fresh 226GB dump 才能跑真 full restore drill

---

## §3 — GAP-D cron + script drafts

### 3.1 Crontab entry (proposed, NOT installed)

```
0 3 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
    OPENCLAW_SECRETS_ROOT=$HOME/BybitOpenClaw/secrets OPENCLAW_BACKUP_ROOT=$HOME/pg_backups \
    OPENCLAW_BACKUP_RETENTION_DAYS=15 \
    $HOME/BybitOpenClaw/srv/helper_scripts/cron/trading_ai_pg_dump_cron.sh \
    >> /tmp/openclaw/logs/trading_ai_pg_dump_cron.cron.log 2>&1
```

對齊 spec §2.3 daily 03:00 UTC + 15d retention + JSONL log。

### 3.2 `install_pg_dump_cron.sh` (74 lines)

- **Linux only** (`uname -s` gate)
- Path via env var: `OPENCLAW_BACKUP_ROOT` / `OPENCLAW_BACKUP_RETENTION_DAYS` / `OPENCLAW_BACKUP_HOUR_UTC`，**0 hardcoded `/home/ncyu`**
- pre-flight：pg_dump on PATH + secrets env file exist
- **Idempotent guard**：crontab 已有 `pg_dump` entry 即 skip
- **Default DRY-RUN**：必 `OPENCLAW_BACKUP_CRON_APPLY=1` 才實裝

### 3.3 `trading_ai_pg_dump_cron.sh` (101 lines, mirrors `outcome_backfiller_live_cron.sh` style)

- env var first：`OPENCLAW_BASE_DIR` / `OPENCLAW_DATA_DIR` / `OPENCLAW_SECRETS_ROOT` / `OPENCLAW_BACKUP_ROOT` / `OPENCLAW_BACKUP_RETENTION_DAYS`
- 讀 `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env` 拿 PG creds (與既有 cron wrapper 一致)
- Lock dir (`mkdir`) 防 concurrent
- `pg_dump -Fc` custom format (gzip compressed, parallel restorable)
- 顯式 7 schema (`trading / learning / governance / system / observability / replay / market / public`) 避 pg_temp_*
- JSONL log: `{ts, status, dump_file, size_bytes, md5, duration_sec, retention_days}`
- 寫 sentinel file `$OPENCLAW_BACKUP_ROOT/.last_pg_dump`
- 失敗 zero-byte file 自動 rm
- Retention via `find ... -mtime +${OPENCLAW_BACKUP_RETENTION_DAYS} -delete`

### 3.4 `verify_pg_dump.sh` (116 lines) — 5-check

1. backup dir exists + writable
2. **latest dump mtime < 26h** — critical (FAIL exit 2)
3. **dump size > 1 MB** sanity — critical
4. md5sum vs JSONL log match (drift)
5. retention effective (oldest ≤ 15d + 1d grace)

設計給 `passive_wait_healthcheck.sh` 加 `check_pg_dump_freshness()` consume。

### 3.5 安全保證

| 約束 | 落實方式 |
|---|---|
| 不引入硬編碼路徑 | 所有 path via env var，default `$HOME/...` |
| 不真實 install | install script default DRY-RUN，必 `OPENCLAW_BACKUP_CRON_APPLY=1` |
| 不動主 DB | dump wrapper 是 read-only (`pg_dump` not `pg_restore`) |
| 不修 secrets | 只 read `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env` |
| 跨平台 | install script `uname -s != Linux` refuse exit 2 |

---

## §4 — Spec §2.3 + §7.2 backup policy 對齊

| Spec 要求 | 本 draft 對齊狀態 |
|---|---|
| daily logical dump → NAS 異地 | ✓ daily 03:00 UTC pg_dump 7 schema；**NAS path deferred**（NAS 未掛 trade-core，spec §7.2 與 reality drift） |
| weekly `pg_basebackup` + WAL archive | ✗ **NOT in this draft**；separate spec ticket |
| 留 30d × 7 = 210 dump rotation | ✗ 本 draft 15d 對齊 spec §10 GAP-D minimum |
| restore drill quarterly | ✓ 本 audit empirical 跑過 schema-only；建議 quarterly cron sub-task |

### Push back / spec drift

1. **NAS not mounted** — spec §7.2 假設 NAS available；reality 不是。Operator 必須先掛 NAS 或接受 local-only 風險
2. **226GB DB 真實 dump 預估**：custom format gzip 通常 4-6x 壓縮 → 35-55 GB / 15-30 min；**15d × 50GB = 750GB > 841G free → 需縮 retention 至 ~10d OR 加 NAS 異地**。本 draft default 15d，operator 實裝前需驗實際 dump size
3. **`pg_basebackup` + WAL archive deferred** — spec §2.3 weekly track 不在本 GAP-D 範圍

---

## §5 — Unblock first-day live verdict

| Gap | 狀態 | unblock? |
|---|---|---|
| **GAP-B** (PG restore drill) | restore path 驗 OK（schema-only / dump 過時）；full data drill 必待 GAP-D land 後 | **PARTIAL** |
| **GAP-D** (PG dump cron) | spec + 3 script drafts ready；未 install | **NOT CLEARED** |

### 5.1 Operator hand-actions

1. **Review + approve 3 drafts** in `drafts/ops4_gap_b_d/` (291 lines total)
2. **Decide disk strategy**：(a) local-only 15d on `/home/ncyu/pg_backups/` (~600-800GB worst — 近 841G ceiling) OR (b) Mount NAS at `/mnt/nas` + rsync step (推薦) OR (c) 縮 retention 至 7d
3. **Land 3 drafts to `srv/helper_scripts/cron/`** (E1 chain or operator direct)
4. **Dry-run install**：`OPENCLAW_BACKUP_CRON_APPLY=0 install_pg_dump_cron.sh` → 確認 entry → `=1` 實裝
5. **D+1**: 03:00 UTC 第一次 dump fire 後跑 `verify_pg_dump.sh` 確認 5-check PASS
6. **D+1+**: fresh 226GB dump 跑 **full data restore drill** (估 30-60 min + ~226GB scratch)
7. **Land healthcheck wiring**：`verify_pg_dump.sh` → `passive_wait_healthcheck.sh` 第 7+ check (CLAUDE.md §七 mandate)

### 5.2 First-day live unblock verdict

**NOT CLEARED**. GAP-B + GAP-D 同時阻擋 first-day live (spec §8 sign-off MIT row 未滿足)。

最快路徑：operator land + dry-run + install (≤2 hr) → D+1 03:00 UTC fresh dump → D+1 full restore drill (~1 hr) → MIT row sign-off。**最早 unblock = T+~28 hr from operator first action**。

---

## §6 — 附錄

- Sandbox 已 drop: `sandbox_restore_drill_20260527_2102`；不動 runtime / 不 commit
- Drafts: `drafts/ops4_gap_b_d/*` 3 files 291 lines
- 與 ML pipeline maturity 正交；不重述 V104 ML audit (`2026-05-27--v104_supervised_live_audit_dry_run.md`)

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_b_d_pg_backup_drill.md

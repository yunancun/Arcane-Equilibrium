# MIT — OPS-4 GAP-B + GAP-D PG backup/restore deepening research

**Date**: 2026-05-27 (本次 21:00+, 接續 21:06 baseline audit)
**Owner**: MIT (research only; E1 / operator IMPL)
**Boundary**: research + design proposal only; **不寫 IMPL**; **不改 PG schema**; **不執行 dump**; ssh trade-core read-only
**Spec source**: `srv/docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md` §2.3 / §7.2 / §10 GAP-B / GAP-D
**Baseline audit**: `2026-05-27--ops_4_gap_b_d_pg_backup_drill.md` (21:06 today, 9.3 KB) — 含 empirical scan + 3 draft script (291 lines) + 5-check verify SOP
**Scope**: 深化 dump strategy / compression / hypertable / disk usage / restore drill / PA spec hidden risk — **不重述 baseline audit 已 cover 內容**

---

## §0 — Context delta（vs 21:06 baseline audit）

### Empirical updates (post-baseline)

| Item | Baseline (21:06) | Deepening (21:00+) | Delta |
|---|---|---|---|
| DB total | 226 GB | 226 GB | 無 |
| Top contributor identified | （未拆解） | **`learning.decision_features_evaluations` = 182 GB (81%)** | NEW |
| 該表 retention | （未驗）| **無 retention policy** + 17d window + 279.5M row → ~10.7 GB/day | NEW + RED |
| 該表 consumer | （未驗） | **grep `FROM learning.decision_features_evaluations` = 0 SQL match** → producer-only audit log | NEW |
| WAL archive | （未驗）| `archive_mode=off`, `archive_command=disabled`, `max_wal_size=1GB` | NEW |
| Compression tools | （未驗）| zstd 1.5.5 ✓ / gzip ✓ / pigz 2.8 ✓ / lz4 ✗ (not installed) / xz ✓ | NEW |
| CPU + RAM headroom | （未驗）| 32 threads / 124 GiB / 47 GiB free / 74 GiB cache | NEW |
| Network | 10GbE assumed | confirmed `eth0 speed=10000 Mbit` | NEW |

### Baseline audit 已 cover 不重述

- §1.1 backup dir empirical scan (4 path)
- §1.2 crontab pg_dump check (0 active)
- §1.3 PG container health + tool version
- §2 restore drill 53d 189KB dump schema-only sandbox (exit 0)
- §3 3 draft scripts (install_pg_dump_cron.sh / trading_ai_pg_dump_cron.sh / verify_pg_dump.sh)
- §5 7-step operator hand-actions

本 deepening 補：**dump strategy 對比表 / disk budget 細算 / restore scenario 拆細 / PA spec 3 hidden risk / Track-A Track-B 拆分提案**.

---

## §1 — A. PG Dump 策略對比（task A.1-A.4）

### 1.1 What to dump — 7 schema priority 分層

| Tier | Schema / Table | Why | Dump cadence | 復原 priority |
|---|---|---|---|---|
| **Tier-0 critical**  | `trading.fills` / `trading.intents` / `trading.orders` / `trading.position_snapshots` / `trading.decision_outcomes` | trade record SoT，永久保留無 retention | daily | **必復原** |
| **Tier-0 critical** | `learning.governance_audit_log` / `learning.lease_transitions` / `governance.*` (6 tables) | audit chain 法規重建 | daily | **必復原** |
| **Tier-0 critical** | `authorization` 衍生 (`system.*`) + `_sqlx_migrations` | schema state + auth chain | daily | **必復原** |
| **Tier-1 valuable** | `learning.decision_features` (12 GB) / `trading.decision_context_snapshots` (20 GB, 46d span) | ML training source；可由 raw klines replay 部分重建 | daily | 重要 |
| **Tier-1 valuable** | `learning.strategist_applied_params` / `learning.mlde_param_applications` / `learning.edge_estimate_snapshots` | strategy state + edge cache | daily | 重要 |
| **Tier-1 valuable** | `learning.mlde_shadow_recommendations` / `learning.strategy_trial_ledger` / `agent.decision_objects` (27 MB) | ML state | daily | 重要 |
| **Tier-2 reconstructible** | `market.*` (534 MB total) / `market.klines` (259 MB hypertable) | 可由 Bybit history API replay | weekly | 可選 |
| **Tier-3 rebuildable** | `learning.decision_features_evaluations` (**182 GB**, 17d, no retention, no consumer) | producer-only audit log; W-AUDIT-4b 評估痕跡 | **EXCLUDE 或 separate** | 不需復原 |
| **Tier-3 rebuildable** | `learning.health_observations` (112 MB hypertable) / `learning.replay_divergence_log` | runtime health snapshot；replay 可重產 | weekly | 不需 |
| **Tier-3 rebuildable** | `trading.risk_verdicts_damaged_20260414_130607` (903 MB) / `fills_damaged*` / `intents_damaged*` | 2026-04-14 incident quarantine 殘留 | **EXCLUDE 完全** | 不需 |
| **Tier-X 系統表** | `pg_catalog` / `information_schema` / `_timescaledb_internal` chunks | pg_dump 自動 reconstruct | N/A | N/A |

**MIT 強烈推薦**：**Tier-3 evaluations + damaged 表 EXCLUDE** → dump size 從 226 GB → ~44 GB（uncompressed），這是 design 的 critical choice。

**EXCLUDE 風險**：evaluations 是 ML training future source；EXCLUDE 等於放棄此 17d 資料的 disaster recovery。對應 risk decision = **operator 必須 confirm「evaluations 表是否屬 RPO 範圍」**。MIT 立場：**不屬**（未有 consumer + 17d 已 182 GB + W6 RFC 已揭露 audit purpose），加 retention policy（≤30d）+ separate weekly dump 比 daily 全 dump 划算。

### 1.2 Dump strategy 三選一對比

| 工具 | 機制 | Pros | Cons | 對 226 GB / Tier 0+1 (~44GB) 適用度 |
|---|---|---|---|---|
| **`pg_dump -Fc -j N`** logical custom | per-table COPY OUT；parallel job; restore selective per-table | (a) 可 selective schema/table EXCLUDE (Tier-3) (b) restore granular (c) 跨 PG version (16→17) safe (d) compression built-in | (a) 不能 PITR (b) 跑時 lock contention (c) 1 cohort snapshot only | **GO** for Tier 0+1 daily; primary strategy |
| **`pg_basebackup -D ... -Ft -X stream`** physical | byte-level data dir copy + WAL stream | (a) 包含 cluster level state (b) 可配合 WAL archive 做 PITR | (a) 不能 per-table restore (b) 需停或熱 backup mode (c) **WAL archive 必須先 enable** (現 archive_mode=off) (d) physical size = full DB = 226 GB no compression natively (e) PG version 必 exact match | **DEFER** to phase 2; spec §2.3 weekly schedule (現缺 WAL archive infra) |
| **`timescaledb-backup` (community)** | wraps pg_dump + handles chunk-aware DDL | (a) hypertable chunk metadata 正確處理 | (a) external dependency (b) docker container 內安裝 (c) limited maintenance | **CONDITIONAL**: 如 pg_dump 對 hypertable chunk metadata 處理有問題才用 |
| **`COPY (SELECT ... FROM tier_0) TO program 'zstd -T0 > /backup/...'`** custom | 純 SQL COPY 串 zstd | (a) 最精細控制 (b) 對特定大表 efficient | (a) 不含 DDL (b) 需單獨 dump schema (c) ad-hoc 不維護 | **REJECT**: 過度 custom 增加 ops burden |

**MIT 推薦**：**主路徑 `pg_dump -Fc -j N --exclude-schema 與 --exclude-table EXCLUDE Tier-3`**，Tier-2 可 weekly 單獨跑（market.* 可由 Bybit API replay）。

### 1.3 Hypertable 處理 — pg_dump 行為驗證

- TimescaleDB 16.13 + pg_dump 16.14 兼容 ✓ (baseline §1.3)
- `pg_dump` 對 hypertable 預設行為：**dump 每個 chunk 為 inheritance child table + parent table 為空** — 此處有歷史 trap
- **建議參數**：
  - `--no-owner --no-privileges` 跨環境兼容
  - `--no-publications --no-subscriptions` 避 logical replication 衝突
  - Sprint N+0 內驗 hypertable restore 是否需 `SELECT timescaledb_pre_restore() / timescaledb_post_restore()` 包覆（per TSDB docs）— **此為 GAP-B drill 必驗點**
- **chunk-aware 必驗 query**：
  ```sql
  -- post-restore verify
  SELECT hypertable_schema, hypertable_name, num_chunks 
  FROM timescaledb_information.hypertables 
  ORDER BY hypertable_name;
  -- 對比 dump 前 snapshot
  ```

### 1.4 Compression 對比

實測未跑（不在 scope；E1 IMPL phase 必跑 benchmark），但理論 + 軟體基線：

| Compression | Ratio (text/jsonb heavy data 預估) | CPU cost | Compatibility | trade-core 安裝 |
|---|---|---|---|---|
| **zstd -T0 (level 3 default)** | 5-8x | 低 (parallel) | ✓ ubiquitous since 2020 | ✓ 1.5.5 |
| **zstd -T0 -19** (max) | 7-10x | 高 (慢 3-5x) | ✓ | ✓ |
| **gzip (single thread)** | 3-5x | 中 | ✓ universal | ✓ |
| **pigz (parallel gzip)** | 3-5x | 中-低 | ✓ | ✓ 2.8 |
| **lz4** | 2-3x | 最低 (最快) | ✓ | ✗ **未裝** |
| **xz** | 6-9x | 最高 (慢 10x) | ✓ | ✓ |

**MIT 推薦**：**zstd -T0 level 3** 為 default
- ratio 5-8x → 44 GB Tier 0+1 → ~6-9 GB / dump
- 32-thread parallel → ~5-10 min compression 不阻 PG IO
- 比 gzip 快 3-5x + 比 pigz 略好 ratio + 比 xz 快 10x
- `pg_dump -Fc` 內建 zlib compression level 0-9（gzip-family）→ 對 jsonb 不及 zstd；**建議 `pg_dump -Fc -Z 0`（停用內建壓縮）然後 pipe 給 zstd** 或用 `pg_dump --compress=zstd:level=3` (PG 16.0+ 支援 zstd directly via `--compress=zstd:N`)

**driver decision**：`pg_dump --compress=zstd:3 -Fc -j 4 --exclude-schema='_timescaledb_internal' --exclude-table='learning.decision_features_evaluations' --exclude-table='*_damaged_*' -f tier01_$(date +%Y%m%d).dump trading_ai`

### 1.5 Disk usage 估算 — 詳細

| Component | Size 估算 | 計算 |
|---|---|---|
| Tier 0+1 raw | ~44 GB | 226 - 182 (evaluations) - 0.9 (damaged) ≈ 43 + market.* 0.5 GB |
| Tier 0+1 zstd:3 compressed | **6-9 GB** (single dump) | 5-8x ratio on jsonb-heavy + numeric |
| **15d × 6-9 GB** | **90-135 GB** | retention policy spec §10 GAP-D minimum 15d |
| **30d × 6-9 GB** | **180-270 GB** | spec §7.2 建議 30d |
| Tier 2 weekly (market.* 534 MB) | ~100-200 MB compressed | 1x dump/week × 4 = 800 MB |
| **Total budget 15d** | **~91-136 GB** | local-only `/home/ncyu/pg_backups/` |
| **Total budget 30d** | **~181-271 GB** | 需 NAS or 縮 retention |
| Disk free | **842 GB** | trade-core `/dev/nvme0n1p8` |

**結論**：
1. **15d retention 完全 fit 在 local disk** (90-135 GB << 842 GB; 占 11-16%)
2. **30d retention 可 fit local 但接近 25-32% 容量** + DB 持續增長壓力
3. **若 evaluations 表加入 dump（不 EXCLUDE）**：daily compressed ≈ +20-30 GB → 15d ≈ +300-450 GB → **超出 disk 安全 60% 紅線**
4. **NAS path 不可達**（baseline §1.1: `/mnt/nas` 未掛載；sudo 拒 exportfs verify）→ 短期建議 **local-only 15d + evaluations EXCLUDE**

### 1.6 Schedule + lock contention

| Option | Time | Rationale | Lock 風險 |
|---|---|---|---|
| **03:00 UTC daily** ✓ (baseline draft default) | crypto Asian off-hours + ML training 02:00 跑完 | aligns with `restart_all` low-touch | pg_dump COPY 是 ROW SHARE lock → 只阻 DDL，**不阻 INSERT/SELECT** |
| 02:00 UTC | ML cron 高峰時段 | 衝突 ml_training_maintenance_cron | reject |
| Hourly differential | 過頻 + WAL archive 未開 → 無 incremental 機制 | reject for now | N/A |
| Per-event WAL stream | 需 archive_mode=on → 另案 | DEFER | N/A |

**Lock 詳細**：`pg_dump` 對每個 table 取 `ACCESS SHARE`，**只阻 `DROP/TRUNCATE/ALTER`**，**不阻** `INSERT/UPDATE/DELETE/SELECT`。對 OpenClaw 03:00 UTC 場景：fills/intents/risk_verdicts INSERT 持續流入 OK，僅 V### migration 阻擋（V### 通常 dev-time apply，runtime 不會 ALTER）。

**TSDB compress_chunk policy 衝突**：retention/compression policy job 12:00:00 schedule_interval 多在 02:00-08:00 UTC firing；**03:00 UTC dump 可能與 risk_verdicts/intents compress policy 撞**。建議：
- Dump 開始前 30s 跑 `SELECT * FROM timescaledb_information.job_stats WHERE next_start < now() + interval '1 hour';` 預檢
- 若衝突 → dump 改 04:00 UTC（offset 1h）

### 1.7 Storage placement decision tree

```
disk free 842 GB + DB 226 GB ?
├─ YES → option A: local-only `/home/ncyu/pg_backups/` 15d × 6-9 GB = 90-135 GB OK
│   └─ 警告: 同物理 disk → disk failure = backup + DB 同毀
├─ NAS mount 可達 ?
│   ├─ YES → option B: local 7d hot + NAS 30d cold (rsync 10GbE)
│   │   └─ 推薦: 異地 + 雙重備援
│   └─ NO → option A only + 加 retention 緊縮 + 加 disk 監控
└─ 若 evaluations 加入 dump → 走 NAS 不可選 → option A 必崩
```

**MIT 推薦 phase plan**：
- **Phase 1（first-day live unblock）**: option A local-only 15d × EXCLUDE evaluations → ≤135 GB OK
- **Phase 2（W18-21 後）**: mount NAS + 加 rsync step → option B 異地 + 30d
- **Phase 3（GA 後）**: enable WAL archive + pg_basebackup weekly → PITR capability

---

## §2 — B. Restore Drill SOP 細化（task B.1-B.6）

### 2.1 Scenario coverage 矩陣

| Scenario | 嚴重度 | RTO target | RPO target | Test cadence |
|---|---|---|---|---|
| **S1: 完整 DB corruption** (e.g. disk fail / pg cluster 損毀) | CRITICAL | < 4 hours | ≤ 24 hours (last daily dump) | **Quarterly** + first-day live 必跑 |
| **S2: Single table accidental TRUNCATE/DROP** (e.g. operator error) | HIGH | < 1 hour | ≤ 24 hours | Annual |
| **S3: Single hypertable chunk corruption** | MEDIUM | < 30 min | ≤ 24 hours | Annual |
| **S4: Migration rollback** (e.g. V### apply 後發現 schema 設計錯) | LOW-MED | < 30 min | live (rollback to pre-migration state) | Per-event triggered |
| **S5: Single row recovery** (e.g. UPDATE 誤改 risk_config) | LOW | < 15 min | ≤ 24 hours | Per-event |

### 2.2 RTO/RPO recommended numbers — final

**RPO (Recovery Point Objective)**:
- **Tier 0 (fills / intents / governance audit)**: **≤ 24 hours**（daily dump cadence）
- **Tier 0 with WAL archive (Phase 3 後)**: ≤ 5 min（per WAL ship interval）
- **Tier 1 (decision_features / context_snapshots)**: ≤ 24 hours
- **Tier 2 (market.* replayable)**: ≤ 7 days（weekly cadence + Bybit API fallback）
- **Tier 3 (evaluations EXCLUDE)**: **不 commit RPO; producer-only audit log loss tolerable**

**RTO (Recovery Time Objective)**:
- **S1 full restore**: target **≤ 4 hours**
  - download dump from NAS / local (~6-9 GB) ≤ 5 min
  - pg_restore -j 16 parallel (44 GB raw decompress) ≈ 30-90 min on AMD 32-thread / 124 GiB
  - timescaledb_post_restore() ≈ 5-10 min
  - schema verify (10-step) ≈ 15 min
  - reconciler 對 Bybit account state ≤ 30 min
  - app restart + 6 health domain 30min PASS = 30 min
  - **Total median ≈ 2-3 hours**, **worst 4 hours**
- **S2 single table**: ≤ 30 min（pg_restore -t table_name selective）
- **S3 single chunk**: ≤ 30 min (TSDB 內建 `reorder_chunk` or `move_chunk`)
- **S4 migration rollback**: ≤ 30 min (per dev migration SOP, 不需走 dump)
- **S5 single row**: ≤ 15 min (跑 SELECT 從 dump 撈 row + INSERT)

**spec §2.1 對應**：spec PG out-of-disk 寫 < 30 min → 對應 S5 級別 ✓；spec 沒列 S1 RTO → **本 audit 推 ≤ 4h**（aggressive but achievable on 32-thread machine）

### 2.3 Restore procedure — 5 phase

| Phase | Action | Duration | Verify |
|---|---|---|---|
| 1. Snapshot | freeze writes; emit halt_session | 1 min | live engine state = paused |
| 2. Side-restore | `createdb trading_ai_restore_YYYYMMDD; pg_restore -j 16 -d ... dump` | 30-90 min | exit 0 |
| 3. Verify | per §2.4 below | 15 min | 10/10 checks PASS |
| 4. Swap | rename live → archive; rename restore → live | 5 min | PG up + sqlx_migrations max correct |
| 5. Reconcile | engine restart + Bybit position 對賬 reconciler | 30 min | 0 diff |

### 2.4 Verification queries — post-restore 10-step

```sql
-- 1. Schema count
SELECT count(*) FROM information_schema.schemata WHERE schema_name IN ('trading','learning','governance','system','observability','replay','market','agent','panel','public');
-- expect: 10

-- 2. _sqlx_migrations max + count
SELECT max(version), count(*) FROM public._sqlx_migrations;
-- expect: matches pre-dump snapshot

-- 3. Critical table row counts (relative to pre-dump baseline)
SELECT 'fills' AS t, count(*) FROM trading.fills
UNION ALL SELECT 'intents', count(*) FROM trading.intents
UNION ALL SELECT 'orders', count(*) FROM trading.orders
UNION ALL SELECT 'governance_audit_log', count(*) FROM learning.governance_audit_log
UNION ALL SELECT 'decision_outcomes', count(*) FROM trading.decision_outcomes;

-- 4. Hypertable chunk count
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables ORDER BY hypertable_name;

-- 5. Compressed chunk integrity
SELECT count(*) FROM timescaledb_information.chunks WHERE is_compressed;

-- 6. Authorization chain (governance audit append-only)
SELECT max(ts), count(*) FROM learning.governance_audit_log WHERE ts > now() - interval '7 days';

-- 7. Constraint validity
SELECT conname, conrelid::regclass, contype FROM pg_constraint WHERE NOT convalidated;
-- expect: only V083 NOT VALID intentional ones

-- 8. CHECK enum coverage (V086 reject_reason_code / close_reason_code)
SELECT count(*) FROM learning.decision_features WHERE reject_reason_code IS NULL AND label_close_tag IS NOT NULL;

-- 9. TimescaleDB extension version match
SELECT extname, extversion FROM pg_extension WHERE extname='timescaledb';

-- 10. Decision lease state machine consistency (post ADR-0008)
SELECT decision_state, count(*) FROM trading.decision_outcomes WHERE ts > now() - interval '7 days' GROUP BY decision_state;
```

### 2.5 Drill cadence

| Drill | Frequency | Trigger | Owner | Pass criteria |
|---|---|---|---|---|
| **Schema-only sandbox drill** | After every new dump file | Cron post-step | automated | exit 0 |
| **Full data drill (S1)** | Quarterly | Cron + manual | MIT + operator | 10/10 verify + RTO ≤ 4h |
| **First-day live qualifying drill** | **Once before W18-21** | spec §8 sign-off | MIT | Full S1 drill |
| **Pre-migration drill (S4)** | Per V### apply | E2 review chain | E2 | Selective table verify |
| **Single-row drill (S5)** | Annual or per-event | Manual | E1 | < 15 min |

**First-day live 必跑 drill**:
1. baseline 21:06 audit 跑了 schema-only / pre-phase0a 53d stale dump → 不能算 first-day qualifying drill
2. **必待 GAP-D land + first fresh daily dump 生成（D+1 03:00 UTC fire）→ 對該 dump 跑 full S1 restore drill**
3. Drill 需 ~3-4 hours wall-clock + ~50 GB scratch disk
4. **MIT 推薦 drill 跑在 sandbox sandbox DB on same instance**（不需 separate hardware；用 `createdb trading_ai_drill_YYYYMMDD`）

---

## §3 — C. PA spec hidden risk（MIT 視角 3 個關鍵）

PA OPS-4 runbook §10 列 GAP B/D 為 spec gap，但 spec 本身有以下 3 個 hidden risk 未列：

### 3.1 HIDDEN RISK #1: spec 假設 NAS 可達但 reality 未掛載

**證據**：
- spec §7.2 寫「daily 02:00 UTC: `pg_dump --schema=trading,learning,governance,system` → NAS」
- spec §10 GAP D 寫「PG dump cadence cron 未排」隱含 NAS infra ready
- **Reality**: baseline §1.1 empirical 證 `/mnt/nas` 未掛，`/nas` 不存在；trade-core 是 nfsd 提供者但 sudo 拒 verify export
- memory `project_hardware_constraints` 寫「40TB NAS via 10GbE」是 hardware claim 不是 mount state

**Risk impact**:
- 若 operator 接 spec 字面意思 → install cron 寫 NAS path → cron 第一次 fire 即 fail（path 不存在）→ 0 dump
- spec §8 ratification checklist MIT row 寫「PG dump cadence cron 已 land」未驗 NAS path → 假性 PASS

**MIT 建議修法**:
1. PA OPS-4 spec §7.2 改寫「local-only 15d as Phase 1; NAS optional Phase 2」
2. operator 必須在 sign-off 前 explicit 確認 storage placement（option A 或 B）
3. spec §8 MIT row 加 sub-check: `pg_dump path writable` 而非 cadence cron only

### 3.2 HIDDEN RISK #2: spec 寫 `--schema=trading,learning,governance,system` 但 evaluations 是 learning 下 182 GB 大表 → daily dump 變 ~25-35 GB 直接 explode 15d budget

**證據**:
- spec §7.2 `pg_dump --schema=trading,learning,governance,system` — `learning` schema include 即抓 evaluations
- evaluations: 182 GB / 17d / 無 retention / 無 consumer
- Daily compressed estimate: 25-35 GB（zstd 5-8x ratio on jsonb-heavy）
- 15d retention budget: **375-525 GB** << 842 GB free → 還 OK
- **但**：1 個月後 evaluations 自然成長到 ~325 GB（10.7 GB/day × 30）→ daily compressed 變 40-50 GB → 15d 600-750 GB → **接近 disk 紅線**
- **半年後**：evaluations ~1.95 TB raw → 即使無 retention 也會撞 PG 自己 disk full (`/dev/nvme0n1p8` 1.4T)

**Risk impact**:
- spec 字面 schema-level dump 是「在 OK 範圍但會自殺」設計
- Operator 不知 evaluations 表特殊（無 consumer、純 audit）→ 預設 include
- 加 retention policy on evaluations 是 separate decision，但 spec 沒 mention → 不會 propagate

**MIT 建議修法**:
1. spec §7.2 改寫顯式 EXCLUDE 該表 `--exclude-table='learning.decision_features_evaluations'`
2. **NEW MIT migration proposal V###**: `add_retention_policy('learning.decision_features_evaluations', INTERVAL '30 days')` + compress_after 7d
3. evaluations 改 hypertable（若可行）或 partitioning（per-week range partition）— architectural review separate
4. spec §10 GAP list 新增 **GAP I: `decision_features_evaluations` 無 retention + 無 consumer**（W6 audit 後延宕沒人 follow-up）

### 3.3 HIDDEN RISK #3: spec 假設 dump 是 idempotent + 重啟 engine 可吃；但 `pg_dump` checksum drift + sqlx_migrations checksum drift 雙重風險未 list

**證據**:
- memory `project_2026_05_02_p0_sqlx_hash_drift` 記載：手動 `psql -f V###.sql` apply 與 `OPENCLAW_AUTO_MIGRATE=1` sqlx migrate path 不同 checksum → engine restart with AUTO_MIGRATE=1 觸發 checksum mismatch panic
- 該事件治本 = `repair_migration_checksum` binary（commit 3681f83）
- baseline §2.1 21:06 audit empirical 揭：「V083/V084 已 manual apply 但 `_sqlx_migrations` max=79 未 register V083/V084」→ **drift 持續存在**

**Risk impact**:
- restore 流程 = `pg_restore` recreates `public._sqlx_migrations` table from dump
- dump time 點 vs restore 時點 的 sqlx_migrations max 可能不同
- 若 restore 後 engine 走 AUTO_MIGRATE=1 path → checksum mismatch panic
- 真實 incident scenario：S1 full restore 從 7d 前 dump 拿 _sqlx_migrations max=84 → 期間 V085/V086 apply 過 → restore 後 engine startup 跑 sqlx migrate → V085/V086 重新 apply 但 checksum 與當時不同（因為 V086 OR-filter audit 後 spec drift）→ panic

**MIT 建議修法**:
1. restore SOP 加 **mandatory step**: `pg_restore` 後 + engine restart 前 → 跑 `bin/repair_migration_checksum --confirm` aligning to current SQL file checksum
2. spec §10 加 **GAP J: restore-with-sqlx-checksum-drift SOP**
3. drill SOP §2.4 step 2 (_sqlx_migrations max + count) 不夠 → 加 step 11: 計算 V### file SHA256 vs `_sqlx_migrations.checksum` byte-equal 比對

---

## §4 — Acceptance criteria（research → IMPL handoff）

### 4.1 GAP-D PG dump cron IMPL acceptance

**Must-have (block first-day live)**:
1. Cron entry installed in `crontab -l`; fire daily 03:00 UTC ✓ idempotent guard
2. First D+1 fire → produces `tier01_YYYYMMDD.dump` in `/home/ncyu/pg_backups/`
3. Dump size 6-9 GB (zstd:3 compressed, Tier 0+1 only)
4. JSONL log entry written with `status=success` + md5sum + duration_sec
5. `verify_pg_dump.sh` 5-check exit 0
6. healthcheck `check_pg_dump_freshness()` integrated to `passive_wait_healthcheck.sh`（CLAUDE.md §七 mandate）
7. Retention 15d effective: D+15 oldest dump auto-removed
8. **EXCLUDE `learning.decision_features_evaluations` + `*_damaged_*` tables**

**Should-have (Phase 2 / not block first-day)**:
9. NAS mount + rsync step (option B)
10. Tier-2 market.* weekly cadence
11. Spec §7.2 amend (MIT push back #1 + #2)

**Could-have (Phase 3)**:
12. WAL archive enable + pg_basebackup weekly
13. PITR drill SOP

### 4.2 GAP-B restore drill acceptance

**Must-have**:
1. First fresh daily dump (from GAP-D) → full S1 restore drill 跑通
2. Drill duration ≤ 4 hours wall-clock
3. 10/10 verification SQL pass
4. Hypertable chunk count post-restore = pre-dump
5. sqlx_migrations checksum drift handled via `repair_migration_checksum`（MIT push back #3）
6. Drill report written to `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/YYYY-MM-DD--ops4_full_restore_drill.md`

**Should-have**:
7. Quarterly drill schedule in cron
8. S2-S5 individual drill SOPs documented

---

## §5 — E1 IMPL packet estimation

### 5.1 拆分提案 — 2 sub-agent 並行

**Sub-agent A (GAP-D dump cron land + healthcheck wiring)**:
- 工時 estimate: **3-4 hours**
- 工作：
  1. Land 3 draft scripts to `srv/helper_scripts/cron/`（已有 21:06 draft 291 lines）
  2. Amend `trading_ai_pg_dump_cron.sh` 加 `--exclude-table` + `--compress=zstd:3` (per §1.2 + §1.4)
  3. Amend `verify_pg_dump.sh` 加 sqlx checksum drift check (per §3.3)
  4. Wire `check_pg_dump_freshness()` to `passive_wait_healthcheck.sh`
  5. Dry-run install + crontab entry verify
  6. Operator confirm + `OPENCLAW_BACKUP_CRON_APPLY=1` activate
- Adversarial review: E2 + A3 (per §feedback_impl_done_adversarial_review)
- Output: commit + report `2026-05-28--ops4_gap_d_pg_dump_cron_land.md`

**Sub-agent B (GAP-B full restore drill SOP + first drill run)**:
- **依賴**：sub-agent A 完成 + D+1 03:00 UTC 第一次 dump fire (~30 hours wall-clock)
- 工時 estimate: **5-7 hours**（含 drill 跑 3-4h + verify 1h + report 1h）
- 工作：
  1. 寫 `helper_scripts/db/restore_drill.sh`（基於 baseline §2.2 schema-only drill 擴展）
  2. 包含 §2.3 5-phase + §2.4 10-step verify
  3. 第一次 跑 S1 full drill 對首份 fresh dump
  4. 寫 drill report 含 actual RTO measurement
- Output: commit + report `2026-05-29--ops4_gap_b_full_restore_drill.md`

**Total wall-clock**: ~30 hours（含 D+1 dump fire wait）+ 8-11 hours active dev
**Total active dev**: 8-11 hours
**Parallel sub-agents**: 2

### 5.2 Operator confirm needed before IMPL dispatch

| # | Decision | Default | Risk if defer |
|---|---|---|---|
| 1 | **Storage placement**: option A local-only 15d × EXCLUDE evaluations? | Yes (MIT 推薦) | option B NAS need ops effort + mount verify |
| 2 | **`evaluations` 表 EXCLUDE from dump**? | Yes (MIT 推薦) | RPO loss on 17d audit log; W6 stakeholders 應 confirm |
| 3 | **Retention 15d 或 30d**? | 15d (per spec §10 GAP-D minimum) | 30d 需 180-270 GB local disk (still fit) |
| 4 | **Tier-2 market.* weekly cadence land in Phase 1 or 2**? | Phase 2 (deferrable) | small risk; market replayable from Bybit |
| 5 | **sqlx_migrations drift handler `bin/repair_migration_checksum` 可用 ?** | Verify before drill | already shipped per memory |
| 6 | **NAS mount Phase 2 owner**? | E3 | spec §7.2 假設 NAS ready but reality 未 |

---

## §6 — 結論 + push back summary

### 6.1 結論

1. **GAP-D research COMPLETE**: pg_dump -Fc -j 4 --compress=zstd:3 + EXCLUDE evaluations + EXCLUDE damaged → 6-9 GB/day × 15d = 90-135 GB local OK
2. **GAP-B drill scenario COMPLETE**: 5-scenario matrix + RTO ≤ 4h + RPO ≤ 24h + 10-step verify
3. **3 hidden risks identified**（PA spec NAS 假設 / evaluations 表負擔 / sqlx checksum drift）
4. **E1 IMPL 8-11 hours active dev × 2 parallel sub-agent + 30h wall-clock wait first dump**

### 6.2 Push back to PA OPS-4 spec

| # | Push back | Reason | Amend target |
|---|---|---|---|
| 1 | spec §7.2 NAS path → option A local-only Phase 1 | NAS 未掛 reality | §7.2 + §10 GAP-D |
| 2 | spec §7.2 `--schema=learning` → 顯式 EXCLUDE evaluations | 182 GB 無 retention 無 consumer | §7.2 + 新 GAP-I |
| 3 | spec §10 加 GAP-J: restore + sqlx checksum drift SOP | repair_migration_checksum 流程未 list | §10 |
| 4 | spec §8 MIT row sub-check: dump path writable + size 6-9 GB sanity | cadence cron only insufficient | §8 |
| 5 | spec §2.3 RTO/RPO 加 explicit 數字（< 4h S1 / ≤ 24h Tier 0）| spec 只列 GAP D 沒 commit RTO | §2.2 + §2.3 |

### 6.3 Operator confirm needed (block IMPL dispatch)

- A. Storage placement option A vs B
- B. `evaluations` 表 EXCLUDE confirm
- C. Retention 15d vs 30d
- D. NAS mount Phase 2 owner

### 6.4 不在 scope（per task constraint）

- 不寫 IMPL (E1 + 主會話)
- 不改 PG schema
- 不執行 dump
- 不碰 GAP A/F systemd / OPS-1 HTTPS
- 不評估 alpha / 策略 / ML pipeline maturity（separate）

---

## §7 — Cross-reference

- Baseline (21:06): `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_b_d_pg_backup_drill.md`
- Drafts: `srv/docs/CCAgentWorkSpace/MIT/workspace/drafts/ops4_gap_b_d/{install_pg_dump_cron.sh, trading_ai_pg_dump_cron.sh, verify_pg_dump.sh}` (291 lines)
- PA spec: `srv/docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md` §2.3 / §7.2 / §10 GAP-B / GAP-D
- Hardware: memory `project_hardware_constraints`
- sqlx hash drift incident: memory `project_2026_05_02_p0_sqlx_hash_drift`
- WAL archive enable proposal (Phase 3): NOT yet drafted

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md

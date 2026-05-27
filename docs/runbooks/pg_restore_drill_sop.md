# PG Restore Drill — Operating SOP Runbook

**狀態：** Active（OPS-4 GAP-B baseline — Round 2 land 2026-05-27）
**版本：** v1（2026-05-27 — Mid-Sprint 4 first-day live qualifying baseline）
**Owner：** MIT (drill plan + verify) + Operator (drill 執行 + DB write)
**契約上游：**
- [PA OPS-4 spec §10.A](../execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md) — 7 scenarios + 7-step restore procedure（ratified）
- [FA business acceptance audit §B.5 + §B.2](../CCAgentWorkSpace/FA/workspace/reports/2026-05-27--ops_4_gap_bd_business_acceptance_audit.md) — 4/9 invariant re-verify + drill scenarios
- [MIT empirical research §2.3 + §2.4 + §3.3](../CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md) — 5 phase + sqlx hidden risk #3

**輔助腳本：**
- [`helper_scripts/db/post_restore_validation.sql`](../../helper_scripts/db/post_restore_validation.sql) — 9 query 業務 acceptance gate（必跑）
- `rust/openclaw_engine/src/bin/repair_migration_checksum.rs` — sqlx checksum drift 修復 binary（`cargo run --bin repair_migration_checksum --release -- --verify` / `--apply --i-understand-this-modifies-db`）

**Drill report template：** [`docs/CCAgentWorkSpace/MIT/workspace/templates/pg_restore_drill_report_template.md`](../CCAgentWorkSpace/MIT/workspace/templates/pg_restore_drill_report_template.md)

---

## 1. 用途 / Why this runbook exists

`pg_dump` (GAP-D land 後 daily 03:00 UTC fire) 是 OpenClaw 唯一 DR primary lane。`pg_restore` 成功（exit 0）**不等於** business reusable —— restored DB 必須 pass 9 query L0 business invariant + 4/9 safety invariant re-verify，才可進入 swap-to-live phase。

本 runbook 規範三類事件：

- **Initial setup**（sandbox DB + NVMe scratch + 隔離 from live runtime）
- **Scheduled drill**（per FA §C.5：monthly mandatory + per-event ad-hoc）
- **Emergency drill**（post-incident：disaster recovery 驗 + RTO 計時驗證）

涵蓋 PA §10.A.4 七大 drill scenarios：S1 Full DB corruption / S2 Single L0 schema / S3 Single L0 table TRUNCATE / S4 V### migration rollback / S5 TSDB hypertable chunk loss / S6 Disaster after Earn first stake / S7 Mid-Sprint 4 first-day live disaster。

每 drill 跑完必落 drill report（template `pg_restore_drill_report_template.md`），併入 `learning.governance_audit_log` 一行 governance row 紀錄。

> **CLAUDE.md §四 alignment**：drill 期間絕不對 live trading_ai DB 寫；任何 verify SQL 均對 sandbox DB（`trading_ai_drill_YYYYMMDD` / `trading_ai_restore_YYYYMMDD`）執行。violate = root principle #1 single controlled write entry violation。

---

## 2. 治理約束 / Governance Invariants

| Invariant | 來源 | 違反後果 |
|---|---|---|
| Drill 必對 sandbox DB 跑，永不對 live `trading_ai` 直接 restore | CLAUDE.md §四 5-gate hard boundary | live DB 被誤 overwrite = 全 fills loss + 30d audit 中斷 |
| 9 query 必 9/9 PASS 才可進入 swap phase（drill scenario 1） | FA §B.1 + post_restore_validation.sql aggregate | 任一 FAIL swap → root principle #8 every-trade-reconstructable 破 |
| 4/9 invariant re-verify (I1/I2/I7/I8) 必 4/4 PASS | FA §B.2 | I1-I8 任一 FAIL → 5-gate 不完整 → 不可 resume live |
| Restore 後 + engine restart **前**必跑 `repair_migration_checksum --verify` | memory `project_2026_05_02_p0_sqlx_hash_drift` | sqlx checksum drift → engine startup panic → unscheduled outage |
| Scenario 6（Earn first stake disaster）必補 Bybit Earn API cross-check | BB OPS-3 C-4 + FA §C.5 | 本地 `learning.earn_movement_log` row 缺 → 稅務 + monetary loss 不可重建 |
| Drill report 必落 `MIT/workspace/reports/YYYY-MM-DD--<scenario>.md` | role-profile-memory-standard | 治理空白 → 後續 drill 無 baseline |
| Drill 完成必 INSERT `learning.governance_audit_log` (event_type='pg_restore_drill_completed' / '_failed') | root principle #8 + FA §C.1 mirror | I8（不 fake audit）驗不到 PG 級證據 |
| Sandbox DB 跑完必 `DROP DATABASE` cleanup（不長存）| PG disk hygiene + §6 fail mode | 多 sandbox 累積 → /dev/nvme0n1p8 1.4T 撞 disk full |
| Monthly cadence 不可跳；跳 1 month → P0 audit finding | FA §C.5 mandate | drift detect 落後 + 真實 disaster 時 SOP 失準 |

---

## 3. Initial Setup（sandbox DB / NVMe scratch / 隔離 from live）

### 3.1 前置 / Preconditions

- [ ] `OPENCLAW_DATABASE_URL` env var 已設且指向 live PG（drill 跑同 PG instance 但不同 DB name；per MIT §2.5 推薦）
- [ ] `/home/ncyu/pg_backups/` 已存在且 GAP-D cron 已 fire ≥ 1 次（first fresh daily dump 已生成）
- [ ] `/dev/nvme0n1p8` free space ≥ 60 GB（drill DB 需 ~50 GB scratch）
- [ ] `bin/repair_migration_checksum` 已 build（`cargo build --bin repair_migration_checksum --release`）
- [ ] `helper_scripts/db/post_restore_validation.sql` 存在且 readable
- [ ] Operator 有 PG superuser credential（drill 需 `CREATE DATABASE`）
- [ ] live runtime `OPENCLAW_AUTO_MIGRATE=0`（drill 期間不允 sqlx auto-migrate 觸發）
- [ ] PG `pg_stat_activity` 連線數 < 80%（drill restore -j 16 並行不撞 max_connections）

### 3.2 Sandbox DB naming convention

| 用途 | 命名 pattern | TTL |
|---|---|---|
| Drill 跑 scenario 1-7 | `trading_ai_drill_YYYYMMDD` | 跑完 24h 內 `DROP DATABASE` |
| 真實 disaster restore 前驗 | `trading_ai_restore_YYYYMMDD` | swap 成功後保留 7d 作 archive |

兩 sandbox 不可共存超過 24h；多 sandbox 累積會撞 NVMe disk full。

### 3.3 NVMe scratch placement

drill DB 跑同 PG instance（per MIT §2.5）：

```bash
# 不需 separate hardware；用 createdb at same PG instance
psql -h $PG_HOST -U $PG_USER -d postgres -c "CREATE DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

不可放 `/mnt/nas`（per MIT HIDDEN RISK #1：NAS 未掛）；不可放 `/tmp`（ephemeral tmpfs 不夠）。

### 3.4 Isolation from live runtime

| Risk | Mitigation |
|---|---|
| Drill restore 期間 PG max_connections 撞滿 | restore 用 `-j 4` 而非 `-j 16` 留 buffer；live engine 連線優先 |
| Drill query 慢 / table scan 拖累 live | drill 避開 03:00 UTC dump fire 與 04:00 UTC retention prune；建議 06:00-10:00 UTC 跑 |
| Drill DB 誤被 sqlx auto-migrate 觸發 | restore 後 + engine restart 前先跑 `repair_migration_checksum --verify`；確定 drill DB 與 live DB engine 分離 |
| Sandbox DB 被誤 swap 成 live | 命名嚴格遵 §3.2；swap 前 operator 必 explicit confirm DB name |

---

## 4. Scheduled Drill（per FA §C.5：monthly mandatory + per-event ad-hoc）

### 4.1 觸發條件 / Trigger

- **Monthly cadence**：每月第 2 個週六 06:00-12:00 UTC fire（避開週末 trading 高峰 + 03:00 UTC dump fire window）
- **Per-event ad-hoc**：
  - V### migration land 後 24h 內 → 跑 scenario 4
  - GAP-D dump retention 改動後 → 跑 scenario 1（驗 dump 完整性）
  - Bybit Earn 大額 movement（> 10000 USDT stake / redeem）後 → 跑 scenario 6
  - 任一 P0 incident postmortem 推薦 → 跑相關 scenario

### 4.2 Drill 工作流（7 phase 對齊 PA §10.A.6）

對每 scenario 適用 PA §10.A.6 之 7-step restore procedure：

| Phase | Action | Duration (median) | Verify |
|---|---|---|---|
| 1 | **Snapshot**：freeze writes（drill 不需，僅 record 跑 baseline_snapshot.sql 紀錄 pre-disaster 狀態）| 1 min | `baseline_snapshot.sql` log 存 `/tmp/openclaw/logs/drill_baseline_<ts>.log` |
| 2 | **Side-restore**：`createdb trading_ai_drill_YYYYMMDD; pg_restore -j 4 -d ... <dump>` | 30-90 min | exit 0 + table count > 0 |
| 3 | **sqlx checksum repair**：`cargo run --bin repair_migration_checksum --release -- --verify` first；若 drift detected → `--apply --i-understand-this-modifies-db` interactive prompt | 1-2 min | drift_count = 0 OR drift 修復後 0 |
| 4 | **Verify**：跑 `helper_scripts/db/post_restore_validation.sql` 9 query + 4/9 invariant matrix（see §8） | 15 min | 9/9 query PASS + 4/4 invariant PASS（aggregate summary block 最後印） |
| 5 | **Swap**（drill **跳過**；僅在真實 disaster 才 swap live） | N/A | drill mode skip |
| 6 | **Reconcile**（drill **跳過**；僅在真實 disaster 才對 Bybit 對賬） | N/A | drill mode skip；scenario 6 例外 → 跑 Bybit Earn cross-check |
| 7 | **Operator approval resume**（drill **跳過**；僅在真實 disaster 才走） | N/A | drill report verdict PASS / CONDITIONAL / FAIL |

Drill 7 phase 完成 → cleanup phase：`DROP DATABASE trading_ai_drill_YYYYMMDD` + drill report 落 reports/。

### 4.3 7 Drill Scenarios 細化（per PA §10.A.4 + FA §B.5）

#### Scenario 1 — Full DB corruption recovery（RTO budget ≤ 4 hr）

**Use case**：disk fail / pg cluster 損毀 / accidental `DROP DATABASE trading_ai`。

**Procedure**：
```bash
# 1. baseline snapshot (skip if drill-only; ad-hoc 跑 fills 數+sqlx max 紀錄)
psql -h $PG_HOST -U $PG_USER -d trading_ai -c "\
    SELECT count(*) AS fill_count, max(ts) AS latest_fill FROM trading.fills; \
    SELECT max(version) AS sqlx_max FROM public._sqlx_migrations;"

# 2. createdb sandbox
psql -h $PG_HOST -U $PG_USER -d postgres -c "CREATE DATABASE trading_ai_drill_$(date -u +%Y%m%d);"

# 3. pg_restore from latest daily dump
pg_restore -j 4 -h $PG_HOST -U $PG_USER -d trading_ai_drill_$(date -u +%Y%m%d) \
    /home/ncyu/pg_backups/tier01_$(date -u -d 'yesterday' +%Y%m%d).dump 2>&1 | \
    tee /tmp/openclaw/logs/drill_restore_s1_$(date -u +%Y%m%dT%H%M%SZ).log

# 4. sqlx checksum verify (mandatory per §10.A.5)
cd ~/BybitOpenClaw/srv && cargo run --bin repair_migration_checksum --release -- --verify 2>&1 | \
    tee /tmp/openclaw/logs/drill_sqlx_verify_s1_$(date -u +%Y%m%dT%H%M%SZ).log

# 5. 9 query 驗
PGPASSWORD=$PG_PASS psql -X -A -t -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    -v ON_ERROR_STOP=1 \
    -f helper_scripts/db/post_restore_validation.sql 2>&1 | \
    tee /tmp/openclaw/logs/drill_9query_s1_$(date -u +%Y%m%dT%H%M%SZ).log

# 6. 4/9 invariant re-verify (manual per §8)

# 7. Drill report 落 + governance audit row INSERT (per §8)

# 8. Cleanup
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

**估時**：median 2.0 hr / worst 4.0 hr（含 pg_restore 30-90 min + verify 15 min + report 30 min + buffer 30 min）。

**Pass criteria**：9/9 query PASS + 4/4 invariant PASS + Bybit balance 對齊 pre-disaster snapshot ± 0。

---

#### Scenario 2 — Single L0 schema restore (governance only)（RTO budget ≤ 30 min）

**Use case**：`governance` schema 被誤 drop / corrupted；其他 schema OK。

**Procedure**：
```bash
# 1. createdb sandbox
psql -h $PG_HOST -U $PG_USER -d postgres -c "CREATE DATABASE trading_ai_drill_$(date -u +%Y%m%d);"

# 2. pg_restore SELECTIVE governance schema only
pg_restore --schema=governance -j 4 -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    /home/ncyu/pg_backups/tier01_$(date -u -d 'yesterday' +%Y%m%d).dump 2>&1 | \
    tee /tmp/openclaw/logs/drill_restore_s2_$(date -u +%Y%m%dT%H%M%SZ).log

# 3. 驗 governance schema 完整 + 其他 schema 為空
psql -h $PG_HOST -U $PG_USER -d trading_ai_drill_$(date -u +%Y%m%d) -c "\
    SELECT schemaname, count(*) FROM pg_tables WHERE schemaname IN ('governance','trading','learning') \
    GROUP BY schemaname;"
# expect: governance > 0; trading=0; learning=0

# 4. 跑 9 query Q9（governance.lease_lal_tiers seed integrity）必 PASS
PGPASSWORD=$PG_PASS psql -X -A -t -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    -c "SELECT tier_level, count(*) FROM governance.lease_lal_tiers GROUP BY tier_level;"
# expect: 5 rows, tier_level 0..4

# 5. cleanup
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

**估時**：median 20 min / worst 30 min。

**Pass criteria**：governance schema 5 tier seed 完整 + 其他 schema 確認為空（不破壞）。

---

#### Scenario 3 — Single L0 table TRUNCATE accident（RTO budget ≤ 30 min）

**Use case**：operator 誤跑 `TRUNCATE trading.fills`；其他 table OK。

**Procedure**：
```bash
# 1. createdb sandbox
psql -h $PG_HOST -U $PG_USER -d postgres -c "CREATE DATABASE trading_ai_drill_$(date -u +%Y%m%d);"

# 2. pg_restore SELECTIVE table trading.fills only
pg_restore -t trading.fills -j 4 -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    /home/ncyu/pg_backups/tier01_$(date -u -d 'yesterday' +%Y%m%d).dump 2>&1 | \
    tee /tmp/openclaw/logs/drill_restore_s3_$(date -u +%Y%m%dT%H%M%SZ).log

# 3. 驗 FK lineage 不破（trading.intents → trading.orders 應仍可 JOIN）
#    注意：本 scenario 僅 restore trading.fills；intents/orders 是空 → orphan 0 是 vacuous PASS
psql -h $PG_HOST -U $PG_USER -d trading_ai_drill_$(date -u +%Y%m%d) -c "\
    SELECT count(*) AS fill_count FROM trading.fills;"
# expect: > 0 (matches pre-disaster)

# 4. cleanup
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

**估時**：median 15 min / worst 30 min。

**Pass criteria**：trading.fills row count match pre-disaster baseline；FK lineage 概念性 OK（real disaster 才驗 intents/orders）。

---

#### Scenario 4 — V### migration rollback（RTO budget ≤ 30 min）

**Use case**：V### apply 後發現 schema 設計錯（e.g. V112 LAL retract）；rollback 到 V###-1。

**Procedure**：
```bash
# 1. createdb sandbox
psql -h $PG_HOST -U $PG_USER -d postgres -c "CREATE DATABASE trading_ai_drill_$(date -u +%Y%m%d);"

# 2. pg_restore from dump taken BEFORE V### apply（找 V###-1 land 後的 dump）
pg_restore -j 4 -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    /home/ncyu/pg_backups/tier01_<pre-V###-date>.dump 2>&1 | \
    tee /tmp/openclaw/logs/drill_restore_s4_$(date -u +%Y%m%dT%H%M%SZ).log

# 3. 驗 sqlx max = V###-1（V### 不在）
psql -h $PG_HOST -U $PG_USER -d trading_ai_drill_$(date -u +%Y%m%d) -c "\
    SELECT max(version) FROM public._sqlx_migrations;"
# expect: V###-1

# 4. sqlx checksum verify (MANDATORY) - 預期 drift（V###-1 之後的 V file 沒在 _sqlx_migrations）
cd ~/BybitOpenClaw/srv && cargo run --bin repair_migration_checksum --release -- --verify

# 5. 跑 9 query 驗 5 tier seed 完整（如 V112 LAL retract scenario）
PGPASSWORD=$PG_PASS psql -X -A -t -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    -v ON_ERROR_STOP=1 \
    -f helper_scripts/db/post_restore_validation.sql 2>&1 | \
    tee /tmp/openclaw/logs/drill_9query_s4_$(date -u +%Y%m%dT%H%M%SZ).log
# 注意：若 V### post-rollback 觸發 5 tier seed 缺 → Q9 FAIL（預期 + must document in drill report）

# 6. cleanup
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

**估時**：median 20 min / worst 30 min。

**Pass criteria**：sqlx max = expected V###-1；任何 expected schema state 對齊 V###-1 land 後狀態；5 tier seed 如未被 V### 改動則 Q9 PASS。

---

#### Scenario 5 — TimescaleDB hypertable chunk loss（RTO budget ≤ 30 min）

**Use case**：單 chunk corrupt（e.g. `trading.fills` 某 7d chunk file 損毀）。

**Procedure**：
```bash
# 1. createdb sandbox
psql -h $PG_HOST -U $PG_USER -d postgres -c "CREATE DATABASE trading_ai_drill_$(date -u +%Y%m%d);"

# 2. pg_restore (full) - 因 TSDB chunk 無法 selectively restore (per MIT §1.3)
pg_restore -j 4 -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    /home/ncyu/pg_backups/tier01_$(date -u -d 'yesterday' +%Y%m%d).dump 2>&1 | \
    tee /tmp/openclaw/logs/drill_restore_s5_$(date -u +%Y%m%dT%H%M%SZ).log

# 3. 驗 hypertable chunk count 對齊 pre-disaster
psql -h $PG_HOST -U $PG_USER -d trading_ai_drill_$(date -u +%Y%m%d) -c "\
    SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables \
    ORDER BY hypertable_name;"

# 4. 驗 retention policy 不重 fire (post-restore TSDB policy state)
psql -h $PG_HOST -U $PG_USER -d trading_ai_drill_$(date -u +%Y%m%d) -c "\
    SELECT * FROM timescaledb_information.policy_stats LIMIT 10;"

# 5. cleanup
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

**估時**：median 30-45 min / worst 60 min（chunk loss 通常 in-place 比較合理但 SOP scope 是驗 dump restore path）。

**Pass criteria**：hypertable chunk count match pre-disaster；retention policy 不在 restore 後立即 fire（避免 newly-restored chunk 被誤 prune）。

---

#### Scenario 6 — Disaster after Earn first stake（RTO budget ≤ 4 hr）

**Use case**：operator 首次 Bybit Earn stake 後 24h 內 disaster；本地 `learning.earn_movement_log` row 可能 inconsistent with Bybit。

**Procedure**：
```bash
# 1-3. 同 scenario 1 full restore
psql -h $PG_HOST -U $PG_USER -d postgres -c "CREATE DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
pg_restore -j 4 -h $PG_HOST -U $PG_USER -d trading_ai_drill_$(date -u +%Y%m%d) \
    /home/ncyu/pg_backups/tier01_$(date -u -d 'yesterday' +%Y%m%d).dump
cd ~/BybitOpenClaw/srv && cargo run --bin repair_migration_checksum --release -- --verify

# 4. 跑 9 query 含 Q6（learning.earn_movement_log direction 分布）
PGPASSWORD=$PG_PASS psql -X -A -t -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    -v ON_ERROR_STOP=1 \
    -f helper_scripts/db/post_restore_validation.sql 2>&1 | \
    tee /tmp/openclaw/logs/drill_9query_s6_$(date -u +%Y%m%dT%H%M%SZ).log

# 5. BYBIT EARN API CROSS-CHECK (per BB OPS-3 C-4)
#    operator 手動跑：Bybit GET /v5/earn/position 取 staked USDT 總額
#    對齊 SUM(amount_usdt) WHERE direction='stake' FROM learning.earn_movement_log
psql -h $PG_HOST -U $PG_USER -d trading_ai_drill_$(date -u +%Y%m%d) -c "\
    SELECT direction, ROUND(SUM(amount_usdt)::NUMERIC, 8) AS sum_usdt, count(*) \
    FROM learning.earn_movement_log GROUP BY direction;"
# operator: 開 Bybit GUI / API 比對 staked total

# 6. drill report Q6 verdict：local SUM vs Bybit API SUM diff < 0.01 USDT → PASS

# 7. cleanup
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

**估時**：median 2.5 hr / worst 4.0 hr（含 Bybit cross-check operator interactive 30 min）。

**Pass criteria**：9/9 query PASS + Bybit Earn position cross-check local SUM diff < 0.01 USDT（per BB OPS-3 C-4）+ Q6 verdict PASS。

---

#### Scenario 7 — Mid-Sprint 4 first-day live disaster（RTO budget ≤ 4 hr + operator approval resume）

**Use case**：first-day live launch 後 24h 內 disaster；模擬 full restore + 9 invariant re-verify + operator approval resume 全鏈路。

**Procedure**：
```bash
# 1-3. 同 scenario 1 full restore (含 sqlx checksum repair)

# 4. 跑 §8 完整 audit verification（9 query + 4/9 invariant + governance audit INSERT）

# 5. SIMULATED swap rehearsal（drill mode 不真 swap 但 walk through procedure 並 record）
#    操作員必 explicit 確認 sandbox DB 全 PASS 才模擬簽 swap
#    real disaster 才跑：psql -c "ALTER DATABASE trading_ai RENAME TO trading_ai_archive_<ts>;
#                              ALTER DATABASE trading_ai_drill_<date> RENAME TO trading_ai;"
echo "DRILL MODE - SKIPPING REAL SWAP"

# 6. SIMULATED engine restart + reconciler walk through
echo "DRILL MODE - SKIPPING REAL ENGINE RESTART"

# 7. operator approval resume rehearsal（drill report verdict）
# 操作員必 explicit confirm 9/9 + 4/4 PASS + (if applicable) Bybit reconcile
# drill report verdict: PASS = ratify SOP for real disaster

# 8. cleanup
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

**估時**：median 3.0 hr / worst 4.0 hr + operator approval 30 min（含 7 phase 全鏈路 walk through）。

**Pass criteria**：9/9 query PASS + 4/4 invariant PASS + drill report 含 operator sign-off + 模擬 swap/restart procedure walked through。

---

### 4.4 7 scenarios 估時總表

| # | Scenario | Median | Worst | Includes |
|---:|---|---:|---:|---|
| 1 | Full DB corruption | 2.0 hr | 4.0 hr | pg_restore 30-90m + verify 15m + report 30m + buffer |
| 2 | Single L0 schema (governance) | 20 min | 30 min | selective restore + Q9 only |
| 3 | Single L0 table TRUNCATE | 15 min | 30 min | -t trading.fills selective |
| 4 | V### migration rollback | 20 min | 30 min | pre-V### dump + sqlx verify |
| 5 | TSDB hypertable chunk loss | 30-45 min | 60 min | full restore + chunk count verify |
| 6 | Disaster after Earn first stake | 2.5 hr | 4.0 hr | scenario 1 + Bybit Earn cross-check 30m |
| 7 | Mid-Sprint 4 first-day live disaster | 3.0 hr | 4.0 hr + 30m approval | scenario 1 + full 7-phase walk-through |

**全 7 scenarios 連跑 wall-clock**：~14.0 hr（median）/ ~22.5 hr（worst）+ 1 hr operator approval。  
**建議分批跑**：1+6+7 連跑（~7.5 hr median）；2+3+4+5 連跑（~85 min median）。

---

## 5. Emergency Drill（post-incident）

### 5.1 Trigger

- P0 incident postmortem 推薦
- 真實 disaster 後 restore 完成 + swap live 後 7 天內必 retro drill
- engine startup panic 與 sqlx checksum 相關 → 立即 scenario 4

### 5.2 Steps（與 §4 差異標 ⚠️）

1. ⚠️ **不等 monthly cadence**：incident 後 24h 內 fire（防止 stale RCA）
2. ⚠️ **使用真實 incident dump**（如 incident-triggered pg_dump）而非 latest daily
3. ⚠️ **Drill report 標 `EMERGENCY`**：落 `MIT/workspace/reports/YYYY-MM-DD--<scenario>--emergency.md`
4. ⚠️ **同步寫 `learning.governance_audit_log` event_type='pg_restore_drill_emergency_completed'**
5. ⚠️ **24h 內 PM-led 寫 postmortem doc**：`docs/audits/<date>--<incident>_postmortem.md`
6. ⚠️ **若 drill 反映 SOP 不足**：本 runbook §3-§8 加 revision history row + commit

---

## 6. Fail Modes

| Fail mode | 偵測 | 處置 |
|---|---|---|
| **sqlx_migrations checksum drift** | `repair_migration_checksum --verify` reports drift_count > 0 | `--apply --i-understand-this-modifies-db` 互動修復（typed COMMIT 才提交）；若 drift 與 dump 同期 V### file 不對齊 → 查 V### file SHA 與 dump time 點 git log；NEVER 旁路 prompt（per binary §5-PRE TTY guard） |
| **Table corruption (post-restore SELECT errors)** | post_restore_validation.sql 某 query 報 PG error（非 0 row）| 重 pg_restore 確認 dump 完整性 → md5 對 GAP-D verify_pg_dump.sh 紀錄；若 dump 本身壞 → fall back 到前一天 dump（accept higher RPO） |
| **TSDB hypertable chunk loss post-restore** | `timescaledb_information.hypertables.num_chunks` < pre-disaster baseline | 跑 `SELECT show_chunks('learning.X')` 確認；若 dump 本身缺 chunk → re-dump from healthy time point；若 restore 不完整 → 重跑 scenario 5 並查 pg_restore stderr |
| **9 query 任一 FAIL** | post_restore_validation.sql aggregate summary 報 FAIL verdict | 對應 Q### detailed result 查 root cause；不可進 swap；落 drill report 紀錄 + Q### specific RCA |
| **4/9 invariant 任一 FAIL** | I1/I2/I7/I8 manual re-verify FAIL | I1 → autonomy_level_config seed 缺；I2 → governance_audit_log lease_grant 缺；I7 → lease_transitions producer code drift；I8 → fills count vs Bybit reconcile diff > 0；NEVER swap 直到 invariant 修復 |
| **Restore exit ≠ 0** | pg_restore log 含 ERROR | 查 stderr → 通常 disk full / connection limit；retry with -j 4 並監控 disk |
| **Sandbox DB 無法 CREATE** | `CREATE DATABASE` permission denied | 檢查 PG superuser cred + 連線；非 superuser 不能跑 drill |
| **Bybit Earn cross-check diff > 0.01 USDT** | Q6 verdict FAIL（scenario 6） | 查 GAP-D dump RPO 是否覆蓋最近 stake/redeem event；若 dump 太舊 → escalate；若 dump 新但 row 缺 → Earn writer 可能 bug |

---

## 7. Rollback / Cleanup

### 7.1 Drill 結束 cleanup（每次 drill 必跑）

```bash
# 1. 確認 sandbox DB 名（防誤刪 live trading_ai）
psql -h $PG_HOST -U $PG_USER -d postgres -c "\l" | grep -E "trading_ai_(drill|restore)_"

# 2. DROP DATABASE（per §2 invariant）
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"

# 3. 驗 free space 回收
df -h /dev/nvme0n1p8
```

### 7.2 Drill 失敗 rollback（drill 跑壞但 sandbox 已創）

```bash
# Always safe: sandbox DB never affects live；DROP 即可
psql -h $PG_HOST -U $PG_USER -d postgres -c "DROP DATABASE trading_ai_drill_$(date -u +%Y%m%d);"
```

**重要：drill rollback 不需動 live `trading_ai` DB**；sandbox isolation 是 §2 invariant。

---

## 8. Audit Verification

### 8.1 9 query 跑（必對 sandbox DB 執行）

詳細 9 query 內容見 [`helper_scripts/db/post_restore_validation.sql`](../../helper_scripts/db/post_restore_validation.sql) 330 LOC，含 aggregate summary 自動印 9 row PASS/FAIL/WARN table。

跑法：
```bash
PGPASSWORD=$PG_PASS psql -X -A -t \
    -h $PG_HOST -U $PG_USER \
    -d trading_ai_drill_$(date -u +%Y%m%d) \
    -v ON_ERROR_STOP=1 \
    -f /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/post_restore_validation.sql 2>&1 | \
    tee /tmp/openclaw/logs/post_restore_validation_$(date -u +%Y%m%dT%H%M%SZ).log
```

9 query 業務目的 + Pass criteria 摘要（detail 在 SQL file inline comment）：

| Q# | Table | Invariant 對應 | Pass criteria |
|---:|---|---|---|
| 1 | `system.autonomy_level_config` | I1 5-gate state | 1 row + id=1 + level IN (CONSERVATIVE/STANDARD) |
| 2 | `learning.governance_audit_log` | I2 signed auth | 24h ≥ 1 row event_type='lease_grant'（first-day disaster WARN tolerable）|
| 3 | `learning.lease_transitions` | I7 lease state | 24h ≥ 2 distinct to_state |
| 4 | `trading.fills` | root #8 every-trade-reconstructable | 24h count + SUM(realized_pnl) 對齊 baseline + Bybit |
| 5 | `trading.intents → orders` FK | I8 lineage | orphan_pct < 10% |
| 6 | `learning.earn_movement_log` | BB OPS-3 C-4 | direction stake/redeem 分布；scenario 6 Bybit cross-check |
| 7 | `learning.strategist_applied_params` | root #11 | 4 active strategy 各 ≥ 1 row in live/live_demo |
| 8 | `learning.hypothesis_preregistration` | M4 signed integrity | last 10 row payload_hash NOT NULL + signed_at strict DESC |
| 9 | `governance.lease_lal_assignments` + `lease_lal_tiers` | ADR-0034 LAL | 5 tier seed exact 5 row (tier_level 0..4) |

**Pass criteria summary**（aggregate）：≥ 7/9 PASS + 0 FAIL → drill verdict PASS；任 FAIL → drill report 紀錄 + 不可進 swap。

### 8.2 4/9 invariant re-verify（manual per FA §B.2）

post_restore_validation.sql 跑完，operator 額外手動 verify 4/9 mandatory invariant：

| # | Invariant | 對應 9 query | 額外手動 check |
|---|---|---|---|
| I1 | 5-gate live boundary | Q1 | drill mode 不驗 authorization.json 簽（sandbox 無 engine startup）；只驗 Q1 1 row + id=1 |
| I2 | Signed authorization 路徑 | Q2 | drill mode 不驗 Python renew/approve（無 engine）；只驗 Q2 ≥ 1 row in 24h |
| I7 | ML/Dream/Executor/Strategist 不繞 Governance | Q3 + Q9 | Q3 lease_transitions + Q9 LAL tier integrity 同時 PASS |
| I8 | 不 fake healthcheck / fills / lineage | Q2 + Q4 | Q4 fills count vs Bybit reconcile（scenario 6 / 7 必查；其他 scenario 可跳；落 report 記 N/A）|

**Drill mode caveat**：drill 跑 sandbox DB 不對應 live engine，I1-I8 invariant re-verify scope = 「PG 級可查證據」。real disaster restore 完整鏈路（engine restart + IPC + healthcheck）由 operator approval resume phase 補。

### 8.3 Governance audit row INSERT（drill 完成必跑）

```bash
# Drill PASS verdict
psql -h $PG_HOST -U $PG_USER -d trading_ai -c "
INSERT INTO learning.governance_audit_log (event_type, ts, payload, actor, engine_mode) VALUES (
    'pg_restore_drill_completed',
    NOW(),
    jsonb_build_object(
        'scenario', 'S1',
        'drill_date', '$(date -u +%Y-%m-%d)',
        'verdict', 'PASS',
        'duration_min', <填實際 wall-clock>,
        'q_pass_count', <填 0-9>,
        'q_fail_count', <填 0-9>,
        'invariant_pass_count', <填 0-4>,
        'report_path', 'docs/CCAgentWorkSpace/MIT/workspace/reports/$(date -u +%Y-%m-%d)--<scenario>.md'
    ),
    'operator_drill',
    'live'
);"

# Drill FAIL verdict（event_type 改 _failed + payload 加 fail_reason）
psql -h $PG_HOST -U $PG_USER -d trading_ai -c "
INSERT INTO learning.governance_audit_log (event_type, ts, payload, actor, engine_mode) VALUES (
    'pg_restore_drill_failed',
    NOW(),
    jsonb_build_object(
        'scenario', '<S#>',
        'verdict', 'FAIL',
        'fail_reason', '<short description>',
        'report_path', 'docs/CCAgentWorkSpace/MIT/workspace/reports/$(date -u +%Y-%m-%d)--<scenario>.md'
    ),
    'operator_drill',
    'live'
);"
```

**注意**：governance audit INSERT 對 **live `trading_ai` DB**（非 sandbox）；drill 完成後是 live operator 操作。

### 8.4 Drill report 落 reports/

每次 drill 跑完必落 `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/YYYY-MM-DD--<scenario>.md` 用 [`pg_restore_drill_report_template.md`](../CCAgentWorkSpace/MIT/workspace/templates/pg_restore_drill_report_template.md) template。

---

## 9. Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-27 | MIT (OPS-4 GAP-B Round 2) | First-day live qualifying baseline runbook：9 章節 + 7 scenarios 細化（S1-S7 含 procedure + Pass criteria + 估時）+ sqlx checksum repair MANDATORY step（per memory `project_2026_05_02_p0_sqlx_hash_drift`）+ Bybit Earn cross-check scenario 6（per BB OPS-3 C-4）+ governance audit row INSERT（per FA §C.1 mirror）+ template cross-reference |

---

## 10. Cross-References

- 上游 spec：[PA OPS-4 first-day live runbook §10.A](../execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md) — 7 scenarios + 7-step procedure 來源
- FA 業務 acceptance：[FA report §B.5 + §B.2](../CCAgentWorkSpace/FA/workspace/reports/2026-05-27--ops_4_gap_bd_business_acceptance_audit.md) — drill scenarios + 4/9 invariant
- MIT empirical research：[MIT report §2.3 + §2.4 + §3.3](../CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md) — 5 phase + 10-step verify + sqlx hidden risk
- 9 query script：[`helper_scripts/db/post_restore_validation.sql`](../../helper_scripts/db/post_restore_validation.sql) (330 LOC)
- sqlx repair binary：[`rust/openclaw_engine/src/bin/repair_migration_checksum.rs`](../../rust/openclaw_engine/src/bin/repair_migration_checksum.rs) — `--verify` 唯讀 / `--apply --i-understand-this-modifies-db` 互動 prompt
- Drill report template：[`docs/CCAgentWorkSpace/MIT/workspace/templates/pg_restore_drill_report_template.md`](../CCAgentWorkSpace/MIT/workspace/templates/pg_restore_drill_report_template.md)
- 配對 GAP-D dump cron runbook：（待 GAP-D land 後新增；當前 PA spec §10.B 為 baseline）
- Sibling runbook 風格參考：[`replay_signing_key_rotation.md`](replay_signing_key_rotation.md) — 9 章結構源頭
- 治理約束：[CLAUDE.md §四 5-gate hard boundary](../../CLAUDE.md) + §二 root principle #8 every-trade-reconstructable
- 不變量 + dry-run 邊界：[docs/agents/context-loading.md](../agents/context-loading.md) — PG Connection Examples (Linux runtime authoritative)

---
role: E1 Backend Developer
phase: Sprint 5+ Wave 1 §8.1 V101/V102 Track v3 attribution IMPL
date: 2026-05-23
status: IMPL DONE (待 E2 審查)
parent_spec:
  - srv/docs/execution_plan/specs/2026-05-23--v101-track-v3-attribution-column.md
  - srv/docs/execution_plan/specs/2026-05-23--v102-track-v3-indexes-not-null.md
parent_design:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_design.md
parent_adr:
  - ADR-0025 v3 Track-Based Strategy Attribution
  - ADR-0026 v3 Direct Exploit bypass CPCV
  - ADR-0010 Guard A/B/C migration discipline
  - ADR-0011 Linux PG empirical dry-run mandatory
files_modified:
  - sql/migrations/V101__track_v3_attribution_column.sql (新檔 281 LOC)
  - sql/migrations/V102__track_v3_indexes_not_null.sql (新檔 312 LOC)
  - docs/CCAgentWorkSpace/E1/memory.md (append)
estimated_loc_actual: V101 281 / V102 312 (vs PA spec ~250/~280)
---

# E1 — Sprint 5+ Wave 1 §8.1 V101/V102 Track v3 attribution IMPL

## §1 任務摘要

per PA dispatch + operator 拍板 2026-05-23 carry-over §8.1：

- **V101**：CREATE TYPE strategy_track ENUM (3 值) + ADD COLUMN trading.fills.track strategy_track NULL + batched backfill 100% → 'baseline' + Guard A/B/C
- **V102**：ALTER COLUMN track SET DEFAULT 'baseline' + BEFORE INSERT/UPDATE OF track trigger NOT NULL fail-closed (per V077 範式) + 2 hot-path indexes + Guard A/B/C

scope 嚴守 trading.fills only (per PA push back operator prompt 字面範圍)；其他 11 表 + 2 新表 + 4 view + governance.track_kill_events 拆 Sprint 5+ Wave 2 Phase 2 carry-over。

## §2 修改清單

| 檔案 | 行數 | 類型 | 用途 |
|---|---|---|---|
| `srv/sql/migrations/V101__track_v3_attribution_column.sql` | 281 | 新檔 | ENUM + column EXTEND + backfill |
| `srv/sql/migrations/V102__track_v3_indexes_not_null.sql` | 312 | 新檔 | DEFAULT + trigger + 2 index |
| `srv/docs/CCAgentWorkSpace/E1/memory.md` | +60 | append | 教訓 / 範式 / E2 重點記錄 |

未動：openclaw_engine lib code / 既有 V### file / 隔壁 session unstaged WIP。

## §3 關鍵 DDL 對映

### V101 7-Step chain

| Step | DDL | rationale |
|---|---|---|
| 0 | `CREATE TYPE strategy_track AS ENUM (...)` 含 `EXCEPTION WHEN duplicate_object` NOTICE skip | per V057 範式 idempotency |
| Guard A | `trading.fills` 必存 + 15 baseline column (per V003+V015+V077+V083+V094) | fail-closed 阻 V003 漏 apply |
| Guard B | track column 已存在情境下 type/udt/nullable 對齊驗 | idempotency drift detection |
| Main 1 | `ALTER TABLE trading.fills ADD COLUMN IF NOT EXISTS track strategy_track NULL` | per V094 columnstore-safe ADD nullable column |
| Main 2 | Batched UPDATE LOOP (LIMIT 10000 + pg_sleep(0.1) + FOR UPDATE SKIP LOCKED) | per V094 batched 範式；composite PK (fill_id, ts) 對齊 |
| Main 3 | 收尾 verify `COUNT(*) WHERE track IS NULL > 0` → RAISE EXCEPTION | 根原則 6 fail-closed |
| Guard C | ENUM 3 值 + column udt + nullable + 0 NULL backfill 後驗 | post-DDL invariant verify |

### V102 7-Step chain

| Step | DDL | rationale |
|---|---|---|
| Guard A | V101 prereq verify (column + ENUM + 0 NULL backfill) | fail-closed 阻 V101 漏 apply |
| Guard B | DEFAULT + trigger 已存在情境下定義對齊驗 | idempotency drift detection |
| Main 1 | `ALTER COLUMN track SET DEFAULT 'baseline'::strategy_track` | metadata-only;writer 漏填降級安全網 |
| Main 2a | `CREATE OR REPLACE FUNCTION trading.enforce_fills_track_not_null` (LANGUAGE plpgsql + USING ERRCODE='23502') | per V077 trigger function 命名 mirror |
| Main 2b | `CREATE TRIGGER trg_fills_track_not_null_v102 BEFORE INSERT OR UPDATE OF track` | columnstore-safe NOT NULL enforcement |
| Main 3 | `CREATE INDEX IF NOT EXISTS` 2 個 (idx_fills_track_ts_v102 / idx_fills_strategy_track_v102) | hot-path per ADR-0025 v3 4 P&L view query pattern |
| Guard C | 2 index pg_get_indexdef + DEFAULT + trigger count=1 後驗 | post-DDL invariant verify |

## §4 治理對照

### 4.1 V### 順序

```
V099 (autonomy) IMPL-PENDING
   ↓ (V099 不依;不阻 V101)
V100 (M4 base) LAND 2026-05-23 production
   ↓ (V100 與 trading.fills.track 無交集)
V101 (本 — Track v3 attribution column EXTEND)
   ↓
V102 (本 — Track v3 indexes + NOT NULL trigger)
   ↓ (V103 與 trading.fills.track 無交集)
V103 (M4 EXTEND 6 column)
   ↓
V106 / V107 / V112 (既有 LAND chain)
```

102 migrations parse monotonic verified；V100 → V101 → V102 → V103 sequence intact。

### 4.2 範式對齊

| 範式 | 來源 | V101/V102 採用點 |
|---|---|---|
| CREATE TYPE ENUM with EXCEPTION duplicate_object | V057 | V101 Main DDL Step 0 |
| columnstore hypertable nullable ADD COLUMN IF NOT EXISTS | V094 | V101 Main DDL Step 1 |
| Batched UPDATE LIMIT 10000 + pg_sleep + FOR UPDATE SKIP LOCKED | V094 | V101 Main DDL Step 2 |
| BEFORE INSERT/UPDATE trigger fallback for columnstore | V077 | V102 Main DDL Step 2 |
| function naming trading.enforce_fills_* | V077 | V102 trading.enforce_fills_track_not_null |
| trigger naming trg_fills_*_v### | V077 | V102 trg_fills_track_not_null_v102 |
| ALTER COLUMN SET DEFAULT 範式 | V003 (既有 fee DEFAULT 0 / fee_currency DEFAULT 'USDT') | V102 Main DDL Step 1 |
| Guard A schema reflection RAISE EXCEPTION on drift | V100 | V101+V102 Guard A |
| pg_get_indexdef Guard C verify | V094 | V102 Guard C |
| 跨平台 portable (0 /home/ncyu / /Users/ncyu / IP hard-code) | CLAUDE.md §六 | V101+V102 全 SQL 純 schema reflection |

### 4.3 硬邊界對照

- live_execution_allowed / execution_authority / system_mode / max_retries — 未碰
- trading.fills 是 columnstore hypertable — 全程 nullable ADD + trigger fallback;不走 SET NOT NULL/CHECK constraint
- ML training filter IN ('live','live_demo') — V101/V102 未影響 engine_mode column (V077 既有 trigger 不變)
- scope trading.fills only — 未擴 v3 spec 12 表 + 2 新表 + view + kill_events

## §5 不確定之處

### 5.1 cargo test --release --lib database::migrations::tests::load_migrations_real_srv_tree 無法直接跑

**狀況**：pre-existing dirty tree 13 lib test compile errors 來自 unstaged WIP (risk_envelope_probe_impl.rs / ws_client/mod.rs / metric_emitter/mod.rs)。這些是隔壁 session 改動 method signature 4→5 args 但測試端未對齊。

**E1 處理**：不在 E1 scope 改 unstaged WIP（不應動隔壁 session 改動）；改走兩個替代驗證路徑：

1. **`cargo check --release --lib` PASS 0 error**：lib 本體含 migrations.rs (其 parser 邏輯不變) compile 全 PASS（只有 2 個 unused warnings）— V101/V102 不破 lib build。

2. **Standalone parser sanity check**：寫一個 mirror `parse_flyway_filename` + `is_eligible` 規則的 standalone Rust binary，掃 `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/`。結果：

   ```
   PASS: 102 migrations parsed monotonic
   V100/V101/V102/V103 anchor sequence check:
     V100 m4_hypothesis_base_table
     V101 track_v3_attribution_column
     V102 track_v3_indexes_not_null
     V103 extend_m4_hypothesis_columns
     V106 health_observations
     V107 replay_divergence_log
   ```

**等隔壁 WIP commit 後**：建議 PM 串通 `cargo test --release --lib database::migrations::tests::load_migrations_real_srv_tree` 重跑確認；目前 standalone 結果等價（mirror parser 完全一致）。

### 5.2 V101 Main DDL Step 2 走 (fill_id, ts) IN 對齊 composite PK

**狀況**：PA spec §2.3 line 175 範本走 `WHERE fill_id IN (SELECT fill_id FROM ...)`；但 trading.fills PK = `(fill_id, ts)` (V003 line 285)。

**E1 處理**：改為 `WHERE (fill_id, ts) IN (SELECT fill_id, ts FROM ...)` 對齊 composite PK 避免 fill_id 單獨非 unique 在 hypertable 上 SELECT 跨 chunk 漂移。原 SQL 在 PG 仍能跑（fill_id IN 對任何 row 是 unique 但 trans hypertable chunk 可能 plan 退化）；composite key 更明確 + index-friendly。

### 5.3 DEFAULT 'baseline' columnstore-safe 未經 sandbox empirical 驗

**狀況**：PA spec §3.4 line 226 寫「DEFAULT is metadata-only operation; PA 預設可 PASS 但未 sandbox empirical 驗」。

**E1 處理**：採 DEFAULT。若 sandbox dry-run Round 1 RAISE feature_not_supported 在 ALTER COLUMN SET DEFAULT 上 — fallback 路徑 = drop DEFAULT 步驟 + 強化 trigger 必填規則 (writer self-discipline catch by COMMENT)。spec amend 路徑已 PA spec §9.3 line 632 記錄。

E2 審查時建議覆驗：sandbox dry-run Round 1 是否在 Step 1 RAISE。如 RAISE，E1 patch path = remove `ALTER COLUMN ... SET DEFAULT 'baseline'::strategy_track` 一行 + Guard B/C DEFAULT 檢查降為 optional。

### 5.4 V101 結尾 verify 與 writer race

**狀況**：V101 Main DDL Step 2 backfill 全 row → 'baseline'，Step 3 verify 0 NULL；但若 backfill 期間 writer 寫新 row 但漏填 track，Step 3 RAISE EXCEPTION → migration 失敗 → rollback。

**E1 處理**：保留 RAISE EXCEPTION fail-closed（per 根原則 6）。注釋已標示「V102 trigger 上線後此 race 消失」。

實際 production impact：V101 deploy 推薦走 low-IO window；若 writer race 概率高（live 24/7 demo+paper writer 持續寫），需考慮：
1. 走 sandbox empirical 驗 backfill window 內 0 new fill insert（測 wall clock ~17s-3min）
2. 若 production deploy 失敗，operator 手工 backfill + retry V101

## §6 Operator 下一步

### 6.1 E2 審查觸發

派 E2 對 `srv/sql/migrations/V101__track_v3_attribution_column.sql` + `V102__track_v3_indexes_not_null.sql` 同時審查，3 重點：

- **E2-1**：columnstore hypertable trigger fallback 對齊 V077 範式
  - function 名 `trading.enforce_fills_track_not_null`
  - trigger 名 `trg_fills_track_not_null_v102`
  - `BEFORE INSERT OR UPDATE OF track ON trading.fills FOR EACH ROW`
  - `USING ERRCODE='23502'` (not_null_violation SQLSTATE)
  - 不走 `ALTER COLUMN SET NOT NULL` (columnstore feature_not_supported per V077 lesson)

- **E2-2**：scope `trading.fills` only
  - 不擴 v3 spec 12 表 (trading.intents/signals/orders/decision_outcomes/risk_verdicts/position_snapshots 等)
  - 不重 CREATE `learning.hypotheses` (V100 已 land)
  - 不 CREATE `governance.track_kill_events` (Sprint 5+ Wave 3)
  - 不 CREATE 4 P&L view (Sprint 5+ Wave 2 Phase 2)

- **E2-3**：V101 backfill 100% verify
  - Batched UPDATE LIMIT 10000 + pg_sleep(0.1) + LOOP + FOR UPDATE SKIP LOCKED 對齊 V094 範式
  - 收尾 verify `COUNT(*) WHERE track IS NULL > 0` → RAISE EXCEPTION (fail-closed)
  - 不在 V101 內 `ALTER COLUMN SET NOT NULL` (屬 V102 trigger scope)

### 6.2 E4 regression（E2 後）

- E4 regression test 不變 (V101/V102 純 schema migration 不影響 hot path)
- 建議跑 `cargo check --release --lib` 確認 lib 本體 0 error
- 等隔壁 session unstaged WIP commit 後跑 `cargo test --release --lib database::migrations::tests::load_migrations_real_srv_tree` 重 verify

### 6.3 Phase B Sandbox dry-run（E2/E4 後）

per PA spec §4 + §5：

1. `ssh trade-core git pull --ff-only`
2. `ssh trade-core psql -d trading_ai_sandbox -f V101 Round 1 (apply + 5 reflection SQL)`
3. `ssh trade-core psql -d trading_ai_sandbox -f V101 Round 2 idempotent (0 ERROR/RAISE)`
4. `ssh trade-core psql -d trading_ai_sandbox -f V102 Round 1 (apply + 5 reflection SQL)`
5. `ssh trade-core psql -d trading_ai_sandbox -f V102 Round 2 idempotent`
6. V101 → V103 + V102 → V103 chain reapply (V103 EXTEND Guard A 不依 track；chain unaffected)

5 reflection SQL per PA V101 spec §4.1 + V102 spec §5.1 全在 spec 文件已列出。

### 6.4 Phase C Production deploy (PM 統一)

- 等 E2 sign-off + E4 regression + Phase B sandbox dry-run 全綠
- `OPENCLAW_AUTO_MIGRATE=1` restart_all.sh 或 raw psql -f 路徑 (per V100 production deploy 範式)
- expect `_sqlx_migrations` MAX 100 → 102

## §7 完成回報 (4 條)

### 1. V101 SQL LOC + 3 enum + Guard A/B/C
- LOC: 281 (vs PA spec ~250 估計)
- ENUM 3 值: `direct_exploit` / `asds_factory` / `baseline`
- Guard A: trading.fills exist + V003/V015/V077/V083/V094 baseline 15 column 完整
- Guard B: track column 已存在情境 type/udt/nullable 對齊 (idempotency)
- Guard C 後驗: strategy_track ENUM 3 值 + column udt=strategy_track + nullable=YES + 0 NULL backfill

### 2. V102 SQL LOC + 2 indexes + trigger + DEFAULT
- LOC: 312 (vs PA spec ~280 估計)
- 2 indexes: `idx_fills_track_ts_v102` (track, ts DESC) + `idx_fills_strategy_track_v102` (strategy_name, track)
- trigger: `trg_fills_track_not_null_v102` BEFORE INSERT OR UPDATE OF track FOR EACH ROW
- function: `trading.enforce_fills_track_not_null` (LANGUAGE plpgsql + USING ERRCODE='23502')
- DEFAULT: `ALTER COLUMN track SET DEFAULT 'baseline'::strategy_track`

### 3. cargo test sqlx_migrate_check 結果
- `cargo test --release --lib database::migrations::tests::load_migrations_real_srv_tree` 直接跑 fail 但 root cause = pre-existing dirty tree 13 lib test compile errors (risk_envelope_probe_impl.rs / ws_client/mod.rs unstaged WIP)，**不是 V101/V102 引起**
- `cargo check --release --lib` PASS 0 error (lib 本體含 migrations.rs compile OK)
- Standalone Rust parser mirror sanity check: PASS 102 migrations parsed monotonic + V100 → V101 → V102 → V103 → V106 → V107 → V112 sequence intact
- 等隔壁 session unstaged WIP commit 後建議跑 `cargo test ... load_migrations_real_srv_tree` 重 verify (mirror parser 邏輯等價，預期 PASS)

### 4. E2 重點 3 條
- **E2-1**: trigger fallback V077 mirror (function 名 + trigger 命名 + USING ERRCODE='23502' + 不走 ALTER COLUMN SET NOT NULL)
- **E2-2**: scope trading.fills only (不擴 v3 spec 12 表 + 2 新表 + view + kill_events)
- **E2-3**: V101 backfill 100% verify (LIMIT 10000 + pg_sleep + RAISE EXCEPTION on NULL > 0 — fail-closed 根原則 6)

---

**E1 IMPLEMENTATION DONE: 待 E2 審查 (report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_impl.md)**

---
report: E1 Sprint 1B late §4.1.1 V100 M4 hypothesis discovery base table IMPL
date: 2026-05-23
author: E1
phase: Sprint 1B late §4.1.1 P0 (Sprint 4+ first Live carry-over)
status: IMPL-DONE — E2 PENDING
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_late_v100_m4_hypothesis_base_table_design.md
files_changed: 2 added / 0 modified
loc: 663 (SQL) + 581 (spec) = 1244
cargo_test: 15/15 PASS (migrations module lib-only)
sandbox_dry_run: PENDING (Phase B operator + PA)
production_deploy: PENDING (Phase C-D operator + PA + E1)
---

# E1 Sprint 1B late §4.1.1 V100 M4 hypothesis base table IMPL Report

## §0 Executive Summary

**任務**：PA Sprint 1B late §4.1.1 P0 IMPL — V100 M4 hypothesis_discovery 3 base table migration + spec doc。解 V103 EXTEND Guard A FAIL（Sprint 4+ Phase 3c production AUTO_MIGRATE=1 attempt 觸發 V103 Guard A base table 缺問題）。Single-thread，~3 hr 實際 IMPL（PA est 6-8 hr 上界對齊）。

**核心對齊 PA verdict**：
- V099 不碰（autonomy_level_toggle SSOT 不可碰）
- V100 base table（純後加；連續 V099 → V100 → V103 sqlx chain 0 跳號）
- earn_movement_log FK target 必 patch `governance.audit_log` → `learning.governance_audit_log`（PA-DRIFT-1 lesson 繼承 V106/V107/V112 三例）
- Guard A 驗 13 base column only（不混 V103 EXTEND scope）
- 不 rename V103 → V104（避 sqlx checksum drift per 2026-05-02 incident）

**核心交付**：
1. `sql/migrations/V100__m4_hypothesis_base_table.sql` (663 LOC)
2. `docs/execution_plan/specs/2026-05-23--v100-m4-hypothesis-base-table.md` (581 LOC)

**核心驗證**：`cargo test --release -p openclaw_engine --lib database::migrations::` 15/15 PASS，含 `load_migrations_real_srv_tree`（V100 file 被 sqlx parser 接受 + sort chain V099 → V100 → V103 正確）。

**Verdict**：**IMPL-DONE — 等 E2 review**。Sandbox Round 1+2 dry-run + production AUTO_MIGRATE deploy 為 Phase B-D 後續操作（operator + PA 親手）。

---

## §1 修改清單

### 1.1 新增 files (2)

| File | LOC | 用途 |
|---|---|---|
| `sql/migrations/V100__m4_hypothesis_base_table.sql` | 663 | M4 hypothesis discovery 3 base table CREATE + Guard A/C + 4 index + 2 FK + 20 COMMENT |
| `docs/execution_plan/specs/2026-05-23--v100-m4-hypothesis-base-table.md` | 581 | V100 schema spec doc 含 13 主章節 + 4 AC + V### 範式對照表 + E2 重點 3 條 |

### 1.2 修改 files (0)

無。本 IMPL 純新增，0 既有檔案修改。對齊 profile「多實例並行同檔不重疊」紀律。

### 1.3 不在範圍

- ❌ V099 不動（autonomy_level_toggle SSOT）
- ❌ V103 EXTEND .sql 不動（EXTEND-only 路徑維持；避 sqlx checksum drift）
- ❌ Sandbox PG dry-run 不跑（Phase B operator + PA 親手執行）
- ❌ Production deploy 不執行（Phase C-D operator + PA + E1）
- ❌ commit + push（PM 主對話統一 commit 避 multi-session race）

---

## §2 V100 SQL migration 設計關鍵 diff

### 2.1 3 NEW table CREATE

**`learning.hypotheses`** (13 column;line 196-219 of V100 file)：

```sql
CREATE TABLE IF NOT EXISTS learning.hypotheses (
    hypothesis_id           BIGSERIAL PRIMARY KEY,
    strategy_name           TEXT NOT NULL,
    pre_reg_ts              TIMESTAMPTZ NOT NULL,
    pre_reg_hash            TEXT NOT NULL,
    status                  TEXT NOT NULL
                            CHECK (status IN (
                                'draft','preregistered','shadow','stage_0r',
                                'stage_1','stage_2','stage_3','stage_4',
                                'live','retired','killed'
                            )),
    expected_sharpe         REAL,
    expected_dd             REAL,
    capacity_estimate_usdt  BIGINT,
    t_stat_min              REAL,
    min_sample_size         INTEGER,
    engine_mode             TEXT NOT NULL
                            CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**`learning.hypothesis_preregistration`** (7 column；line 248-258)：

```sql
CREATE TABLE IF NOT EXISTS learning.hypothesis_preregistration (
    preregistration_id      BIGSERIAL PRIMARY KEY,
    hypothesis_id           BIGINT NOT NULL
                            REFERENCES learning.hypotheses(hypothesis_id),
    payload_json            JSONB NOT NULL,
    payload_hash            TEXT NOT NULL,
    operator_signature      TEXT NOT NULL,
    signed_at               TIMESTAMPTZ NOT NULL,
    engine_mode             TEXT NOT NULL
                            CHECK (engine_mode IN ('paper','demo','live_demo','live'))
);
```

**`learning.earn_movement_log`** (10 column + **FK schema patch**；line 285-302)：

```sql
CREATE TABLE IF NOT EXISTS learning.earn_movement_log (
    movement_id                BIGSERIAL PRIMARY KEY,
    event_ts                   TIMESTAMPTZ NOT NULL,
    direction                  TEXT NOT NULL
                               CHECK (direction IN ('stake','redeem')),
    amount_usdt                NUMERIC(18,8) NOT NULL,
    apr_at_time                REAL,
    governance_approval_id     BIGINT REFERENCES learning.governance_audit_log(id),
    -- ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    -- **核心 PA-DRIFT-1 patch:不是 governance.audit_log(id)**
    bybit_response_payload     JSONB,
    engine_mode                TEXT NOT NULL
                               CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    api_scope_used             TEXT NOT NULL,
    reconciliation_status      TEXT NOT NULL DEFAULT 'pending'
                               CHECK (reconciliation_status IN (
                                   'pending','matched','mismatch'
                               ))
);
```

### 2.2 Guard A 設計 (line 57-138)

**4 段邏輯**：
1. `learning.hypotheses` 已存在情境驗 13 base column 完整性（防 V019/Sprint 1A-α stub 路徑遺留）
2. `learning.hypothesis_preregistration` 已存在情境驗 7 column 完整性
3. `learning.earn_movement_log` 已存在情境驗 10 column 完整性
4. **`learning.governance_audit_log` 必須存在**（earn_movement_log FK target prereq；V035/V053/V098 baseline）

**RAISE 訊息**對齊 V107 line 96-101 範式：含 actual missing column array + remediation hint「Resolve schema reconciliation before V100」+ 「Reference v103_v104 base spec §2.1.1 for canonical 13-column shape」。

### 2.3 Guard C 預檢 (line 141-225)

**4 CHECK 預檢**用 `to_regclass()` safe pattern 對齊 V107 line 156-169：

```sql
v_target_oid := to_regclass('learning.hypotheses');
IF v_target_oid IS NOT NULL THEN
    -- status CHECK 11 值驗
    -- engine_mode CHECK 4 值驗
END IF;

v_target_oid := to_regclass('learning.earn_movement_log');
IF v_target_oid IS NOT NULL THEN
    -- direction CHECK 2 值驗
    -- reconciliation_status CHECK 3 值驗
END IF;
```

**首次 apply path**：to_regclass NULL → skip 全部 CHECK 驗（避 regclass cast RAISE）。
**重跑 path**：to_regclass NOT NULL → 對 actual CHECK constraint 驗 enum 字面齊全。

### 2.4 Guard C 後驗 (line 502-628)

**6 後驗點**（DDL 完成後 deterministic 驗）：
1. hypotheses.status CHECK 11 值齊全
2. hypotheses.engine_mode CHECK 4 值齊全
3. earn_movement_log.direction CHECK 2 值齊全
4. earn_movement_log.reconciliation_status CHECK 3 值齊全
5. 4 hot-path index 全到位（count = 4）
6. 2 FK 必存在（preregistration → hypotheses；earn_movement_log → learning.governance_audit_log）

**最終 RAISE NOTICE**（line 619-628）紀錄完整 PASS 訊息：

```
V100: M4 base table all guards PASS — 3 NEW table (learning.hypotheses
13 col / hypothesis_preregistration 7 col / earn_movement_log 10 col),
status CHECK 11 values, engine_mode CHECK 4 values, direction CHECK 2
values, reconciliation_status CHECK 3 values, 4 hot-path index built,
2 FK installed (preregistration.hypothesis_id → hypotheses;
earn_movement_log.governance_approval_id → learning.governance_audit_log
[schema patch per PA-DRIFT-1]). V103 EXTEND Guard A now satisfied;
sqlx chain V099 (autonomy) → V100 (M4 base) → V103 (EXTEND M4 6 col) ready.
```

### 2.5 4 hot-path index (line 421-437)

| Index | Hot-path query 設計 |
|---|---|
| `idx_hypotheses_strategy_status` | canary dashboard `WHERE strategy_name=$1 AND status IN ('shadow','stage_0r','stage_1')` |
| `idx_hypotheses_pre_reg_ts` | audit log temporal `ORDER BY pre_reg_ts DESC` |
| `idx_preregistration_hypothesis_signed` | latest signature lookup `WHERE hypothesis_id=$1 ORDER BY signed_at DESC LIMIT 1` |
| `idx_earn_movement_log_strategy_ts` | daily reconciliation cron `WHERE event_ts > now() - INTERVAL '24 hours'` |

非 CONCURRENTLY（sqlx migrate BEGIN/COMMIT 包裹下 CONCURRENTLY 會 RAISE；對齊 V103 EXTEND line 262-265 範式）。

### 2.6 COMMENT ON TABLE / COLUMN (line 441-498)

中文註釋每 column per `feedback_chinese_only_comments` 2026-05-05。對齊 V106/V107/V112 範式。

**核心 COMMENT**（PA-DRIFT-1 治理紀錄）：

```sql
COMMENT ON COLUMN learning.earn_movement_log.governance_approval_id IS
    'FK to learning.governance_audit_log(id); Decision Lease 審批 cross-ref。'
    '注意: spec doc §2.3.1 寫 governance.audit_log 為 schema 名 typo;'
    '真實 production 表名為 learning.governance_audit_log (per V035/V053/V098 baseline)。'
    'V106/V107/V112 PA-DRIFT-1 patch lesson 對齊。';
```

此 COMMENT 是治理紀錄 — E2/E4 audit 用 COMMENT cross-verify FK target 一致性；未來 V### 加新 FK 看到 COMMENT 自然繼承 lesson。

---

## §3 治理對照

### 3.1 PA design verdict 對齊（per `2026-05-23--sprint_1b_late_v100_m4_hypothesis_base_table_design.md`）

| PA verdict 點 | E1 IMPL 對齊 | 證據 |
|---|---|---|
| V099 不碰（autonomy SSOT） | ✅ 不動 V099 file | V100 file path = `V100__*.sql` |
| V100 base table（純後加） | ✅ 純新增 .sql + spec doc | 0 既有 file 修改 |
| 3 table 設計（13/7/10 column） | ✅ 嚴格對齊 v103_v104 §2.1-§2.3 | V100 SQL line 196-302 |
| **earn_movement_log FK schema 名 patch** | ✅ `learning.governance_audit_log(id)` | V100 SQL line 291 + COMMENT line 487-491 |
| Guard A 13 base column only | ✅ 不混 V103 EXTEND 6 column scope | V100 SQL line 65-76 unnest 13 column array |
| 11 status enum 齊全 | ✅ CHECK + Guard C 預檢 + 後驗三重驗 | V100 SQL line 201-211 + 162-181 + 515-535 |
| 4 engine_mode CHECK | ✅ 對齊 paper/demo/live_demo/live | V100 SQL line 213-214 + 537-559 |
| 不 rename V103 → V104 | ✅ V103 EXTEND-only 維持 | 0 V103 file 修改 |
| Linux PG dry-run mandatory | ✅ §6 5 reflection SQL 文檔化 | spec doc §6.1 |

### 3.2 ADR 對齊

- **ADR-0010 Guard A/B/C migration discipline**：✅ Guard A (3 表 column + governance_audit_log prereq) + Guard B 不適用（純 CREATE 0 ALTER 既有 column） + Guard C 預檢 + 後驗（4 CHECK + 4 index + 2 FK）
- **ADR-0011 Linux PG empirical dry-run mandatory**：✅ spec doc §6 5 reflection SQL + Phase B sandbox SOP land；Phase B operator 親手執行
- **ADR-0045 M4 hypothesis discovery governance**：✅ 3 base table land 為 M4 module DDL prerequisite
- **ADR-0026 v3 hypothesis pre-registration**：✅ 11 status enum 含 ADR-0026 v3 4-stage + Sprint 2 promotion stage_1-4

### 3.3 16 root principles 對齊

| Principle | V100 對齊 |
|---|---|
| #5 survival > profit | hypothesis registry 是 governance / pre-registration 層 不影響 live order path |
| #6 uncertainty → conservative | Guard A/C 全 fail-loud RAISE 不靜默 skip |
| #8 reconstructable | preregistration ledger append-only + payload_hash content hash + operator_signature |
| #11 portfolio risk | earn_movement_log 對 Bybit Earn stake/redeem 全 audit + reconciliation_status cron |
| #14 baseline operability | regular table 非 hypertable 0 TimescaleDB dependency |

### 3.4 CLAUDE.md §七 對齊

- ✅ 新代碼 Rust-first 範式（V100 SQL 對齊 V103/V106/V107/V112）
- ✅ 新或改注釋默認中文（17 COMMENT 中文）
- ✅ 800/2000 LOC 警戒：V100 SQL 663 + spec 581 全 < 800 安全帶
- ✅ engine_mode CHECK 4 值齊全 + training filter IN ('live','live_demo') 對齊

### 3.5 Hard Boundaries

- ✅ 不改 `max_retries=0`
- ✅ 不改 `live_execution_allowed` / `execution_authority` / `system_mode`
- ✅ V100 含 Guard A/C（per CLAUDE.md §Data Migrations）
- ✅ 不順手「優化」未要求代碼（profile 硬約束）

---

## §4 cargo test 驗證

### 4.1 結果

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust
source ~/.cargo/env
cargo test --release -p openclaw_engine --lib database::migrations::
```

```
running 15 tests
test database::migrations::tests::parse_rejects_missing_suffix ... ok
test database::migrations::tests::parse_ok_larger_version ... ok
test database::migrations::tests::parse_rejects_single_underscore ... ok
test database::migrations::tests::eligibility_accepts_valid ... ok
test database::migrations::tests::eligibility_rejects_fixtures_and_rollbacks ... ok
test database::migrations::tests::parse_ok_leading_zeroes ... ok
test database::migrations::tests::build_migrator_echoes_inputs ... ok
test database::migrations::tests::parse_rejects_missing_v ... ok
test database::migrations::tests::eligibility_rejects_wrong_prefix ... ok
test database::migrations::tests::parse_rejects_zero_version ... ok
test database::migrations::tests::parse_rejects_nonnumeric_version ... ok
test database::migrations::tests::disabled_and_enabled_no_pool ... ok
test database::migrations::tests::load_migrations_detects_duplicate_version ... ok
test database::migrations::tests::load_migrations_filters_and_sorts ... ok
test database::migrations::tests::load_migrations_real_srv_tree ... ok

test result: ok. 15 passed; 0 failed; 0 ignored; 0 measured; 3170 filtered out; finished in 0.00s
```

### 4.2 關鍵驗證點

- ✅ `load_migrations_real_srv_tree` PASS：V100 file 被 sqlx Migrator parser 接受 + sorted chain monotonic（V099 → V100 → V103 排序正確）
- ✅ `eligibility_accepts_valid` 對 V100__m4_hypothesis_base_table.sql filename pattern 接受
- ✅ `parse_ok_larger_version` 範式對 V100 number parsing 正確
- ✅ `load_migrations_filters_and_sorts` 範式驗 sort 正確
- ✅ `load_migrations_detects_duplicate_version` 確認 V100 與既有 V### chain 無 duplicate

### 4.3 pre-existing build error 與 V100 無關

Full target build (`cargo test --release -p openclaw_engine`)：
- 撞 `live_auth_watcher_tests.rs:103` `PrivateWsBindings` missing `dropout_counter` + `rtt_histogram` field
- 撞 `bybit_rest_client_tests.rs` `ApiLatencyHistogramSnapshot` missing fields

**根因**：PA-DRIFT-4 + PA-DRIFT-5 並行 sub-agent 改造後 test 端 PrivateWsBindings + ApiLatencyHistogramSnapshot struct 加 field；對應 integration test 端尚未同步補 field 初始化。**與 V100 schema migration 0 相關**。

**處理**：lib-only test path（`--lib`）跳過 integration test build → 15/15 PASS。對齊 profile「多實例並行同檔不重疊」紀律。

---

## §5 不確定之處

### 5.1 V103 EXTEND chain 真實 Sandbox 行為

**spec doc §8.1 估計**：V100 base land 後 V103 EXTEND apply Guard A 「learning.hypotheses + hypothesis_id PK 存在」驗自然 PASS。

**真實 Sandbox 行為待 Phase B empirical verify**：
- V100 → V103 chain sandbox apply order 必驗 V103 Guard A line 56-66 邏輯通過
- V103 EXTEND 6 column ADD 對 V100 base 13 column + V103 5 audit field（V094 範式）的 column count 對齊 verify
- 不混 forbidden action column 範式（V107 CR-7 反模式）

**E1 不擅自跑 Sandbox**：per dispatch §禁忌「不 deploy production」+「不執行 sandbox dry-run」；Phase B operator + PA 親手執行 §6.1 5 reflection SQL。

### 5.2 V### slot ordering 對 Sprint 1B late 整體 deploy

Per PA design report §4.1 Phase A-D：
- 預期 production `_sqlx_migrations` MAX 96 → 112 或 113
- 若 V099 autonomy 同期 land → MAX = 113
- 若 V103 + V106 已被 raw psql -f 走過導致只能走 metadata register 路徑（per 2026-05-22 decision_2 SOP step 3 alt）→ real path 待 runtime observe

**E1 IMPL 不預判 MAX**：本 IMPL 純 source-layer V100 file land；MAX 觀察由 Phase D operator verify。

### 5.3 production AUTO_MIGRATE 路徑與 sqlx checksum

per memory `project_2026_05_02_p0_sqlx_hash_drift`：
- V100 file commit 後不再 edit；如必要 edit，必跑 `cargo run --release --bin repair_migration_checksum -- --version 100`
- Phase B Sandbox dry-run 走 `psql -f` 不更新 `_sqlx_migrations` checksum metadata；待 Phase C engine restart auto-migrate 第一次正式寫入

**待 PA / operator Phase B 後確認**：Sandbox 走 raw `psql -f` 或走 engine binary `cargo run` 沿 sqlx Migrator chain；前者不寫 `_sqlx_migrations`；後者寫。本 spec §8.1 假設 `psql -f` 路徑（per V107 sandbox empirical SOP `2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md` 範式）。

---

## §6 Operator 下一步

### 6.1 等 E2 對抗性 code review（per profile + CLAUDE.md §八 chain）

E2 重點 3 條（per V100 spec §12.1-§12.3）：
1. **earn_movement_log FK target schema 名**：SQL line 291 + COMMENT line 487-491 雙重驗；不可寫 `governance.audit_log(id)`
2. **Guard A scope**：V100 驗 13 base column only；不混 V103 EXTEND 6 column；V100 Guard A 邏輯使用 `array_agg(c) ... WHERE NOT EXISTS` 範式對齊 V107
3. **status CHECK 11 值齊全**：CHECK + Guard C 預檢 + 後驗三重驗；對齊 ADR-0026 v3 + Sprint 2 promotion

### 6.2 PM 主對話統一 commit

per profile + memory `feedback_git_commit_only_for_metadoc`：
- E1 IMPL 不 commit；PM 主對話統一 commit
- 建議 commit message subject：`feat(sql): V100 M4 hypothesis discovery base table migration`
- body 含 spec doc link + 對齊 V103 EXTEND Guard A FAIL 解 + earn_movement_log FK schema 名 patch lesson

### 6.3 Phase B Sandbox dry-run（operator + PA 親手）

per V100 spec §6.1 5 reflection SQL + §8.1 Phase B 步驟 4-7：
1. ssh trade-core git pull --ff-only
2. `psql -d trading_ai_sandbox -f V100__m4_hypothesis_base_table.sql` Round 1
3. 跑 5 reflection SQL（表 column / status enum / FK schema 名 / index / engine_mode CHECK）
4. 第二次 apply Round 2 驗 idempotency（0 RAISE EXCEPTION）
5. V100 → V103 EXTEND chain sandbox apply 驗 V103 Guard A 自然 PASS

### 6.4 Phase C-D Production deploy（operator + PA + E1）

per V100 spec §8.1 Phase C-D：
1. `OPENCLAW_AUTO_MIGRATE=0 → 1`
2. `restart_all.sh`（no rebuild;auto-migrate land V97/V98/V100/V103/V106/V107/V112 chain）
3. `_sqlx_migrations` MAX 96 → 112 / 113
4. 6 target table 物理存在 verify
5. engine startup 0 panic
6. 30 min observe + AC-1b SQL 重驗

### 6.5 後續 Sprint 5+ defer item（per PA design §3）

- V101：Sprint 5+ defer（Track v3 attribution column EXTEND；v5.7 4 follow-up）
- V102：Sprint 5+ defer（Track v3 indexes / NOT NULL）
- V104：retired no-op 維持（per v103_v104 §1.3）
- 5 ADD module 剩餘 4 base table（M2 V105 / M8 V109 / M9 V108 / M10 V111）：Sprint 2 Wave 1 IMPL

---

## §7 完成回報 4 條（per dispatch §Step 5）

### 7.1 V100 spec doc 路徑 + LOC + 對齊 V103/V106/V107/V112 範式

- **路徑**：`docs/execution_plan/specs/2026-05-23--v100-m4-hypothesis-base-table.md`
- **LOC**：581
- **對齊範式**：
  - 13 主章節 + 4 AC + spec 範式對照表 + E2 重點 3 條
  - §6 Linux PG dry-run 5 reflection SQL（sandbox empirical SOP per V107）
  - §7 Round 1/2 idempotency proof
  - §8 deploy 4-phase chain（Mac IMPL → Sandbox dry-run → Production AUTO_MIGRATE → verify）
  - §9 Rollback path（V096 boundary 對齊）
  - §11 V103 EXTEND 365 / V106 545 / V107 739 / V112 391 / V099 568 範式 LOC + 結構對照

### 7.2 V100 SQL migration LOC + 3 table column count + 11 status enum + FK schema patch

- **路徑**：`sql/migrations/V100__m4_hypothesis_base_table.sql`
- **LOC**：663
- **3 table column count**：13（hypotheses）/ 7（hypothesis_preregistration）/ 10（earn_movement_log）= **30 column total**
- **11 status enum 字面**：`'draft','preregistered','shadow','stage_0r','stage_1','stage_2','stage_3','stage_4','live','retired','killed'`
- **4 engine_mode enum 字面**：`'paper','demo','live_demo','live'`
- **earn_movement_log FK schema 名 patch**：✅ `learning.governance_audit_log(id)`（不是 `governance.audit_log(id)`）— SQL line 291 + COMMENT line 487-491 雙重紀錄 PA-DRIFT-1 lesson
- **2 additional CHECK enum**：direction 2 值（stake/redeem）+ reconciliation_status 3 值（pending/matched/mismatch）
- **4 hot-path index** + **2 FK** + **20 COMMENT**（3 TABLE + 17 COLUMN）

### 7.3 cargo test sqlx_migrate_check 結果

- **命令**：`cargo test --release -p openclaw_engine --lib database::migrations::`
- **結果**：**15/15 PASS**（0 failed）
- **關鍵 test**：`load_migrations_real_srv_tree` PASS — V100 file 被 sqlx Migrator parser 接受 + sort chain monotonic（V099 → V100 → V103 排序正確）
- **pre-existing build error 與 V100 無關**：full target build 撞 PA-DRIFT-4 並行 sub-agent 改造後 live_auth_watcher_tests.rs + bybit_rest_client_tests.rs missing fields；lib-only test path 跳過

### 7.4 下游 E2 重點 3 點 + Sandbox dry-run readiness verdict

**E2 重點 3 條**（per V100 spec §12）：
1. earn_movement_log FK target schema 名（必驗 `learning.governance_audit_log`）
2. Guard A 13 base column only（不混 V103 EXTEND scope）
3. status CHECK 11 值齊全（CHECK + Guard C 預檢 + 後驗三重驗）

**Sandbox dry-run readiness**：
- ✅ V100 SQL file LAND（663 LOC）
- ✅ V100 spec doc LAND（581 LOC）
- ✅ cargo test 15/15 PASS（V100 file 被 sqlx parser 接受）
- 🟡 **PENDING**：Phase B operator + PA 親手執行 sandbox `psql -d trading_ai_sandbox -f V100` Round 1 + 5 reflection SQL + Round 2 idempotency + V100 → V103 chain 驗
- 🟡 **PENDING**：Phase C-D production deploy（OPENCLAW_AUTO_MIGRATE=1 + restart_all.sh + 6 table verify + 30 min observe）

**Verdict**：**Sandbox dry-run readiness = OPEN — 等 E2 review 通過 + PM commit + operator Phase B 親手執行**。

---

**END OF E1 V100 M4 Hypothesis Base Table IMPL Report**

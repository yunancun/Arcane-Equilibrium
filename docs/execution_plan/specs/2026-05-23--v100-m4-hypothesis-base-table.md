---
spec: V100 M4 hypothesis base table migration
date: 2026-05-23
author: E1
phase: Sprint 1B late §4.1.1 IMPL (Sprint 4+ first Live carry-over)
status: SPEC-DRAFT
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_late_v100_m4_hypothesis_base_table_design.md
base_spec: srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md §2.1-§2.3
adrs:
  - ADR-0010 Guard A/B/C migration discipline
  - ADR-0011 Linux PG empirical dry-run mandatory
  - ADR-0045 M4 hypothesis discovery governance authority
  - ADR-0026 v3 hypothesis pre-registration (Sprint 1A canary + Sprint 2 promotion 對齊)
file: srv/sql/migrations/V100__m4_hypothesis_base_table.sql
loc: 663
---

# V100 M4 Hypothesis Discovery Base Tables — Migration Spec

## §1 Context — V103 Guard A FAIL 解 + M4 base table land

### 1.1 為什麼是 V100 不是 V099 不是 V103.5

**V099 已 SSOT 佔用**：`autonomy_level_toggle` system-wide policy state（568 LOC spec / AMD-2026-05-21-01 v2 + CC re-audit APPROVE A 級 / Wave 5 cascade pending sign-off）；不可碰 — 衝突 SSOT 風險 + 治理 cascade pending。

**V103 EXTEND 路徑已 LAND**：`V103__extend_m4_hypothesis_columns.sql` 366 LOC commit `e1 track c 2026-05-22 stub IMPL #2` Sandbox 走 stub 證明；rename V103 → V104 會觸 sqlx checksum drift（per memory `project_2026_05_02_p0_sqlx_hash_drift`）；維持 V103 EXTEND only 路徑。

**V100 OPEN（純後加）**：v5.7 dispatch_consolidation §3.2 line 336 假佔位 Track v3 attribution column EXTEND，從未 IMPL；可重 number 給 M4 base table；連續 V099 (autonomy) → V100 (M4 base) → V103 (EXTEND M4) 0 跳號，sqlx chain 自然順位。

### 1.2 解 V103 Guard A FAIL chain

**問題**：V103 EXTEND Guard A `learning.hypotheses` 表存在性 + `hypothesis_id` PK 完整性驗（per `V103__extend_m4_hypothesis_columns.sql` line 55-78）；production AUTO_MIGRATE=1 attempt 觸發 V103 Guard A FAIL 因 base 表從未建立（V103 spec 假設 base table 已 land，但 IMPL 走 EXTEND-only 路徑）。

**解**：V100 base land 後 sqlx chain 順序：
```
V099 (autonomy) → V100 (M4 base 3 tables) → V103 (EXTEND M4 6 column)
```

V103 EXTEND Guard A 驗 `learning.hypotheses` + `hypothesis_id` PK 存在 → V100 IMPL 對齊 → PASS。

### 1.3 5 ADD module base table 需求

| Module | base table 需求 | V### owner | 狀態 |
|---|---|---|---|
| M2 overlay | `learning.overlay_state_transitions` hypertable | V105 | spec only |
| **M4 hypothesis_discovery** | **3 base tables**（本 V100） | **V100** | **本 IMPL** |
| M8 anomaly | `learning.anomaly_events` hypertable | V109 | spec only |
| M9 A/B | `learning.ab_tests` + `ab_assignments` + `ab_results` 3 tables | V108 | spec only |
| M10 discovery | `governance.discovery_tier_config` + `discovery_tier_activations` | V111 | spec only |

5 ADD module 中**只有 M4 base table 因 V103 IMPL 走 EXTEND-only 路徑而留下缺口**，其他 M2/M8/M9/M10 base 在 V105/V108–V111 spec 內含 CREATE TABLE 完整 DDL。本 V100 補 M4 base table。

---

## §2 Schema 設計

### 2.1 `learning.hypotheses` — 13 column 基礎 registry

```sql
CREATE TABLE IF NOT EXISTS learning.hypotheses (
    hypothesis_id           BIGSERIAL PRIMARY KEY,
    strategy_name           TEXT NOT NULL,
    pre_reg_ts              TIMESTAMPTZ NOT NULL,
    pre_reg_hash            TEXT NOT NULL,
    status                  TEXT NOT NULL CHECK (status IN (
        'draft','preregistered','shadow','stage_0r','stage_1',
        'stage_2','stage_3','stage_4','live','retired','killed'
    )),
    expected_sharpe         REAL,
    expected_dd             REAL,
    capacity_estimate_usdt  BIGINT,
    t_stat_min              REAL,
    min_sample_size         INTEGER,
    engine_mode             TEXT NOT NULL CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

#### 設計理由

| Aspect | 設計 | 理由 |
|---|---|---|
| PK 類型 | `BIGSERIAL` | 對齊 v5.7 brief；sequential ID 利於 audit log temporal ordering；不需 UUID（無 cross-system import 需求） |
| `strategy_name` 不 enum | `TEXT` | 5 既有 + Sprint 2+ 新策略名（cointegration_pairs 等）動態擴增；CHECK enum 易過時 |
| `pre_reg_ts` + `pre_reg_hash` | 必 NOT NULL | pre-registration 不變式（per ADR-0026 v3 + DOC-08 §12）；hash = spec_json + config_hash 的 git-style content hash |
| `status` 11 值 CHECK | TEXT + CHECK | 統一 Sprint 1A canary stage + Sprint 2 dual-track promotion；對齊 ADR-0026 v3 4-stage + promotion stage_1-4 |
| `expected_sharpe` / `expected_dd` / `capacity_estimate_usdt` / `t_stat_min` / `min_sample_size` | NULL allowed | Sprint 1A 起始 hypothesis 可暫不填；preregistered 後 backfill |
| REAL vs DOUBLE PRECISION | REAL (single-precision) | sharpe / dd / t_stat 4 byte 精度足夠；節省 storage |
| `capacity_estimate_usdt` BIGINT | 整數 USDT | capacity ~USDT amount；天然 round to USDT 整數 |
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | training filter 必 IN ('live','live_demo') per CLAUDE.md §七；preregistration 期 'paper' / shadow 期 'demo' / promotion 期 'live_demo' → 'live' |
| `created_at` + `updated_at` | DEFAULT now() | audit trail；writer 維護 |

#### Row 量級 + 表類型決策

- 5 既有策略 × per-strategy ~2 hypotheses/yr = 10 row/yr
- Sprint 2+ ASDS-generated cohort ~10-20 hypothesis/yr
- Sprint 1B+ Alpha Tournament dataset 一次性 ~50 hypothesis records
- **總量 ~100 row/yr** → **regular table 非 hypertable**（無 TimescaleDB extension dependency）

### 2.2 `learning.hypothesis_preregistration` — 7 column append-only ledger

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

#### 設計理由

| Aspect | 設計 | 理由 |
|---|---|---|
| FK to `hypotheses` | `BIGINT NOT NULL REFERENCES learning.hypotheses(hypothesis_id)` | 一對多（一 hypothesis 可有多次簽署版本，e.g. v1 → v2 amendment）|
| `payload_json` JSONB | NOT NULL | 序列化 hypothesis spec + statistical thresholds + variance estimator + trigger rule（ADR-0026 v3 字段集移入此 JSONB）|
| `payload_hash` TEXT NOT NULL | content hash 防 payload 篡改 | git-style hash of canonical JSON serialization |
| `operator_signature` TEXT NOT NULL | 簽署人 ID + cryptographic signature | Ed25519 / HMAC-SHA256 by IMPL 定；per DOC-08 §12 + §四 Operator 角色 |
| `signed_at` TIMESTAMPTZ NOT NULL | 簽署時間 | audit timestamp |
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | per CLAUDE.md §七 + MIT memory baseline |
| **無 `updated_at`** | append-only design | preregistration ledger 是 immutable audit log；amendment = 新 row（hypothesis_id 同 / payload_hash 不同 / signed_at 不同）|

#### Row 量級

- hypotheses ~100 row/yr × per-hypothesis 1-2 簽署版本 = ~150 row/yr
- regular table，無 hypertable / retention 需求

### 2.3 `learning.earn_movement_log` — 10 column + FK schema 名 patch

```sql
CREATE TABLE IF NOT EXISTS learning.earn_movement_log (
    movement_id                BIGSERIAL PRIMARY KEY,
    event_ts                   TIMESTAMPTZ NOT NULL,
    direction                  TEXT NOT NULL
                               CHECK (direction IN ('stake','redeem')),
    amount_usdt                NUMERIC(18,8) NOT NULL,
    apr_at_time                REAL,
    governance_approval_id     BIGINT REFERENCES learning.governance_audit_log(id),
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

#### 設計理由

| Aspect | 設計 | 理由 |
|---|---|---|
| PK BIGSERIAL | sequential | audit log temporal ordering |
| `event_ts` NOT NULL TIMESTAMPTZ | Bybit response 提供時間 | stake/redeem 真實時間 |
| `direction` ENUM 2 值 | TEXT + CHECK (`stake`/`redeem`) | 雙向流動 |
| `amount_usdt` NUMERIC(18,8) | 高精度 8 位小數 | Bybit Earn stable coin satoshi-scale；REAL 在 satoshi-scale amount 會丟精度，**不可接受** |
| `apr_at_time` REAL | single precision | APR 4-decimal float 足夠；NULL allowed for redeem |
| **`governance_approval_id` BIGINT FK → `learning.governance_audit_log(id)`** | **schema 名 patch（必填）** | **base spec §2.3.1 line 210 寫 `governance.audit_log` 為 schema typo**；production 真實表名 = `learning.governance_audit_log` per V035/V053/V098 baseline；對齊 V106/V107/V112 PA-DRIFT-1 patch lesson |
| `bybit_response_payload` JSONB NULL | API raw response | reconciliation/debug 用；NULL allowed for paper/demo dry-run |
| `engine_mode` NOT NULL CHECK 4 值 | TEXT + CHECK | per CLAUDE.md §七 |
| `api_scope_used` TEXT NOT NULL | Bybit API permission scope（e.g. `account:earn:write`）| audit trail 必含 scope evidence (compliance + post-incident forensic) |
| `reconciliation_status` ENUM 3 值 | TEXT + CHECK + DEFAULT 'pending' | daily reconciliation cron 將 'pending' → 'matched'/'mismatch' |

#### Row 量級

- 手動 rebalance 前 3 months → 每月 ~4-8 stake/redeem events
- 自動化 Sprint 3+：daily/weekly rebalance → ~30-60 event/yr
- **總量 ~100 row/yr**（regular table）

---

## §3 Guard A/C migration pattern

### 3.1 Guard A — 3 NEW table column 完整性 + V098 prereq

**邏輯**：
1. `learning.hypotheses` 已存在情境驗 13 base column 完整性（防 V019 / Sprint 1A-α stub 路徑遺留半成品）
2. `learning.hypothesis_preregistration` 已存在情境驗 7 column 完整性
3. `learning.earn_movement_log` 已存在情境驗 10 column 完整性
4. **`learning.governance_audit_log` 必須存在**（earn_movement_log FK target；V035 baseline + V053/V098 extension；對齊 PA-DRIFT-1 patch）

**RAISE 條件**：表已存在但 column 缺；or governance_audit_log 缺。
**NOT RAISE**（idempotent）：全 column 俱在 / 表不存在（首次跑）。

### 3.2 Guard C — CHECK constraint 對齊驗

**4 CHECK 預檢**（重跑時抓 drift）：
1. `hypotheses.status` CHECK 11 值（draft/preregistered/shadow/stage_0r/stage_1-4/live/retired/killed）
2. `hypotheses.engine_mode` CHECK 4 值（paper/demo/live_demo/live）
3. `earn_movement_log.direction` CHECK 2 值（stake/redeem）
4. `earn_movement_log.reconciliation_status` CHECK 3 值（pending/matched/mismatch）

**Guard C 後驗**（DDL 完成後再驗一次）：
- 4 CHECK constraint 必存在 + 對齊
- 4 hot-path index 必到位
- 2 FK constraint 必存在（preregistration → hypotheses;earn_movement_log → governance_audit_log）

### 3.3 Guard B — 不適用

V100 不 ALTER 既有 column type；無 type-sensitive 檢查需求。對齊 V094/V106/V107 範式（base table CREATE-only 不需 Guard B）。

---

## §4 4 hot-path index

```sql
CREATE INDEX IF NOT EXISTS idx_hypotheses_strategy_status
    ON learning.hypotheses (strategy_name, status);

CREATE INDEX IF NOT EXISTS idx_hypotheses_pre_reg_ts
    ON learning.hypotheses (pre_reg_ts DESC);

CREATE INDEX IF NOT EXISTS idx_preregistration_hypothesis_signed
    ON learning.hypothesis_preregistration (hypothesis_id, signed_at DESC);

CREATE INDEX IF NOT EXISTS idx_earn_movement_log_strategy_ts
    ON learning.earn_movement_log (event_ts DESC);
```

#### 查詢 → 索引對映

| Index | Hot-path query | 對映設計依據 |
|---|---|---|
| `idx_hypotheses_strategy_status` | `WHERE strategy_name=$1 AND status IN ('shadow','stage_0r','stage_1')` | canary dashboard query |
| `idx_hypotheses_pre_reg_ts` | `ORDER BY pre_reg_ts DESC` | audit log temporal 排序 / recent preregistration 列表 |
| `idx_preregistration_hypothesis_signed` | `WHERE hypothesis_id=$1 ORDER BY signed_at DESC LIMIT 1` | latest signature lookup |
| `idx_earn_movement_log_strategy_ts` | `WHERE event_ts > now() - INTERVAL '24 hours' ORDER BY event_ts DESC` | daily reconciliation cron |

**注意**：全 regular table 走 `CREATE INDEX IF NOT EXISTS`（非 CONCURRENTLY）；sqlx migrate BEGIN/COMMIT 包裹下 CONCURRENTLY 會 RAISE；對齊 V103 EXTEND 範式（line 262-265）。

---

## §5 COMMENT ON TABLE / COLUMN

每個 column 中文註釋（per `feedback_chinese_only_comments` 2026-05-05：新代碼默認中文）。

範式（per V106 line 405-417 + V107 line 521-547 + V112 line 378-391）：
- `COMMENT ON TABLE`：表用途 + 設計參數（row 量級 / hypertable 否 / FK 結構）
- `COMMENT ON COLUMN`：每 column 業務語意 + 治理對齊 + 數據類型理由

關鍵 COMMENT 點（**E2 必審**）：

```sql
COMMENT ON COLUMN learning.earn_movement_log.governance_approval_id IS
    'FK to learning.governance_audit_log(id); Decision Lease 審批 cross-ref。'
    '注意: spec doc §2.3.1 寫 governance.audit_log 為 schema 名 typo;'
    '真實 production 表名為 learning.governance_audit_log (per V035/V053/V098 baseline)。'
    'V106/V107/V112 PA-DRIFT-1 patch lesson 對齊。';
```

此 COMMENT 是 PA-DRIFT-1 治理紀錄 — E2/E4 review 必驗 SQL FK target 與 COMMENT 一致。

---

## §6 Linux PG dry-run 5 reflection SQL

per ADR-0011 mandatory + `feedback_v_migration_pg_dry_run.md`。對齊 V106 / V107 / V112 sandbox empirical SOP 範式（per `2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md` §2.4）。

### 6.1 Phase B Sandbox dry-run 必驗 5 SQL（Round 1 apply 後）

```bash
# Round 1: psql -d trading_ai_sandbox -f V100__m4_hypothesis_base_table.sql

# Reflection 1: 3 NEW table 存在 + column count
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT table_name, count(column_name) AS column_count
FROM information_schema.columns
WHERE table_schema='learning'
  AND table_name IN ('hypotheses','hypothesis_preregistration','earn_movement_log')
GROUP BY table_name ORDER BY table_name;
\""
# Expected:
#   earn_movement_log         | 10
#   hypotheses                | 13
#   hypothesis_preregistration | 7
```

```bash
# Reflection 2: status CHECK enum 11 值齊全
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.hypotheses'::regclass AND conname LIKE '%status%check%';
\""
# Expected: 含 11 值 (draft/preregistered/shadow/stage_0r/stage_1/stage_2/stage_3/stage_4/live/retired/killed)
```

```bash
# Reflection 3: earn_movement_log FK target schema 名驗 (核心 PA-DRIFT-1 check)
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT
    tc.constraint_name,
    tc.table_schema || '.' || tc.table_name AS source_table,
    kcu.column_name AS source_column,
    ccu.table_schema || '.' || ccu.table_name AS target_table,
    ccu.column_name AS target_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type='FOREIGN KEY'
  AND tc.table_schema='learning'
  AND tc.table_name='earn_movement_log';
\""
# Expected:
#   source_table = learning.earn_movement_log
#   source_column = governance_approval_id
#   target_table = learning.governance_audit_log   <-- 必驗 schema 名 patch
#   target_column = id
```

```bash
# Reflection 4: 4 hot-path index 齊全
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT indexname FROM pg_indexes
WHERE schemaname='learning'
  AND indexname IN (
    'idx_hypotheses_strategy_status',
    'idx_hypotheses_pre_reg_ts',
    'idx_preregistration_hypothesis_signed',
    'idx_earn_movement_log_strategy_ts'
  )
ORDER BY indexname;
\""
# Expected: 4 row
```

```bash
# Reflection 5: engine_mode CHECK 自動 reject INVALID value (empirical INSERT test)
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
BEGIN;
SAVEPOINT test_engine_mode;
INSERT INTO learning.hypotheses
    (strategy_name, pre_reg_ts, pre_reg_hash, status, engine_mode)
VALUES ('test_strategy', NOW(), 'test_hash', 'draft', 'INVALID_MODE');
ROLLBACK;
\" 2>&1 | grep -i 'violates check constraint'"
# Expected: PG catch CHECK violation
```

### 6.2 為何 Mac mock pytest 不夠

per memory `feedback_v_migration_pg_dry_run`：
- Mac mock pytest 無法捕捉 PG runtime 真實 PL/pgSQL DO block semantic（特別是 Guard A `array_agg` + `unnest`）
- Mac static parse review 無法驗 `pg_get_constraintdef` 真實輸出對齊 spec
- Mac 無法驗 FK constraint cross-schema target（`learning.governance_audit_log`）真存在
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug

**E2/E4 review 必含 Linux PG dry-run gate 證據 ID** per ADR-0011。

---

## §7 Round 1/2 idempotency proof

### 7.1 Round 1（首次 apply）

預期：
- Guard A：表不存在 → array_agg 為 NULL → 全 skip（無 RAISE）
- 主 DDL：3 CREATE TABLE 寫入 + 4 CREATE INDEX 建 + COMMENT 寫入 + 2 FK constraint 建
- Guard C 後驗：CHECK + index + FK 全到位 → RAISE NOTICE PASS

### 7.2 Round 2（重跑 apply）

預期：
- Guard A：表已存在 → 驗 column 完整性 → 全 column 俱在 → 不 RAISE
- 主 DDL：`CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` + `COMMENT ON` 全 idempotent → 0 RAISE
- Guard C 後驗：全 constraint 對齊 → RAISE NOTICE PASS

### 7.3 idempotency 範式對齊

對齊 V103 EXTEND（line 89-185 Guard B + 209-236 ADD COLUMN IF NOT EXISTS）+ V106（line 60-104 Guard A + 296-321 compression idempotent path）+ V107（line 156-264 to_regclass safe pre-check）+ V112（line 67-115 Guard A + 174 ON CONFLICT DO NOTHING）。

**核心 pattern**：
- 用 `EXISTS (SELECT 1 FROM information_schema.tables ...)` guard CREATE TABLE 已存在
- 用 `IF EXISTS (...)` guard ADD COLUMN 對既有 column 完整性驗（V103 EXTEND 範式）
- 用 `to_regclass()` 安全測表是否存在；首次 apply 為 NULL skip CHECK 驗（V107 line 165-168 範式）
- 用 `pg_get_constraintdef` + `position()` 驗 CHECK enum 完整對齊

---

## §8 Engine restart 實測（Phase D production verify）

### 8.1 deploy 鏈

```
Phase A: Mac IMPL (本 E1 work)
  ↓
  1. 寫 V100__m4_hypothesis_base_table.sql (663 LOC)
  2. cargo test --release -p openclaw_engine --lib database::migrations:: PASS
  3. commit + push (per CLAUDE.md §git: 不 amend / 不 force push;narrow staging)

Phase B: Sandbox dry-run (Linux PG empirical mandatory per ADR-0011)
  ↓
  4. ssh trade-core git pull --ff-only
  5. ssh trade-core psql -d trading_ai_sandbox -f V100 Round 1 (apply + 5 reflection SQL)
  6. ssh trade-core psql -d trading_ai_sandbox -f V100 Round 2 (idempotent re-apply; 0 ERROR/RAISE)
  7. Sandbox V100 → V103 chain reapply (V103 EXTEND Guard A 自然 PASS empirical)

Phase C: Production deploy (PA + E1 + operator)
  ↓
  8. OPENCLAW_AUTO_MIGRATE=0→1
  9. restart_all.sh (no rebuild;auto-migrate land V97/V98/V100/V103/V106/V107/V112 chain)
  10. expect _sqlx_migrations MAX 96→112 (V99 autonomy 同期 land 走 113)

Phase D: verify (per Sprint 4+ AC-1b 範式)
  ↓
  11. _sqlx_migrations MAX confirm
  12. 6 target table 物理存在 (learning.hypotheses/hypothesis_preregistration/
       earn_movement_log/health_observations/replay_divergence_log/governance.lease_lal_*)
  13. engine startup 0 panic
  14. 30 min observe + AC-1b SQL 重驗 5 reflection
```

### 8.2 sqlx hash drift 防線

per memory `project_2026_05_02_p0_sqlx_hash_drift` commit `3681f83`：
- V100 file edit 後 DB checksum 必同步
- 若 V100.sql 落地後又被 edit → DB checksum drift → `_sqlx_migrations.checksum` 不對齊
- 修復：`cargo run --release --bin repair_migration_checksum -- --version 100`

**E1 IMPL discipline**：V100 file commit 後不再 edit；如必要 edit，必跑 repair binary 同步 checksum。

### 8.3 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift`：cargo test PASS ≠ runtime sqlx migrate 驗證。E2/E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §9 Rollback plan

### 9.1 V100 rollback

```sql
-- 依序 drop (FK 依賴順序):
DROP TABLE IF EXISTS learning.earn_movement_log;
DROP TABLE IF EXISTS learning.hypothesis_preregistration;
DROP TABLE IF EXISTS learning.hypotheses;
-- 0 row loss (V100 apply 後立即 0 row;Foundation stage per MIT pipeline maturity)
```

### 9.2 V096 boundary

per V101 spec v3 §7：rollback 路徑不跨 V096（V096 drop dead tables 不可逆）。V100 rollback 全在 V096 之後（V096 < V098 < V100），無 boundary 風險。

### 9.3 Rollback 場景對齊

| 場景 | Rollback path |
|---|---|
| Apply 後立即發現 schema bug（before any row written） | DROP 3 表 + 從 `_sqlx_migrations` 刪 V100 row + 重 land 修好 V100 |
| Apply 後有 hypothesis registry row（real production data） | **不 rollback** — 走 ADR-0006 數據訂正紀律 + 補新 V### migration patch |
| 5-gate live / mainnet 期間 | **永不 destructive rollback** — 走 V### forward patch |

per CLAUDE.md §四 + ADR-0006，production 期間 schema rollback 風險高於 forward-patch。本 V100 為 additive schema migration（純 CREATE，0 ALTER 既有 row / DROP COLUMN / 改 type），降低 rollback 需要機率。

---

## §10 4 AC（Acceptance Criteria）

### AC-1: V100 file LAND + sqlx parser accept

- `sql/migrations/V100__m4_hypothesis_base_table.sql` 存在
- LOC 663（對齊 V106 545 / V107 739 / V112 391 / V103 EXTEND 365 範式）
- `cargo test --release -p openclaw_engine --lib database::migrations::tests::load_migrations_real_srv_tree` PASS
- 全 15 migrations module test PASS（含 parse / eligibility / sort / duplicate detect）

**Status**：✅ DONE（本 E1 IMPL 完成）

### AC-2: Sandbox Round 1+2 idempotent apply

- Phase B sandbox `psql -d trading_ai_sandbox -f V100` 第一次 apply 全 RAISE NOTICE PASS（0 ERROR）
- 第二次 apply 0 RAISE EXCEPTION + 0 RAISE NOTICE 衝突
- 5 reflection SQL 全綠（表 column / status enum / FK schema 名 / index / engine_mode CHECK）

**Status**：🟡 PENDING（PA + operator 親手執行 Phase B sandbox dry-run）

### AC-3: V100 → V103 EXTEND chain Guard A pass

- V100 base land 後跑 V103 EXTEND apply
- V103 Guard A 「`learning.hypotheses` table + `hypothesis_id` PK 存在」驗自然 PASS
- V103 EXTEND ADD 6 column 全 PASS
- Sandbox empirical chain verify

**Status**：🟡 PENDING（Phase B sandbox empirical）

### AC-4: Production engine restart + auto-migrate land

- Phase C `OPENCLAW_AUTO_MIGRATE=1` restart_all.sh
- engine startup 0 panic
- `_sqlx_migrations` 含 V100 row + success=true
- 6 target table 物理存在
- 30 min observe + AC-1b SQL 重驗

**Status**：🟡 PENDING（Phase C-D operator + PA + E1）

---

## §11 對齊 V103/V106/V107/V112 spec 範式對照表

| Aspect | V103 EXTEND | V106 | V107 | V112 | V100 (本) |
|---|---|---|---|---|---|
| LOC | 365 | 545 | 739 | 391 | 663 |
| Guard A | ✅ base table + hypothesis_id PK | ✅ TimescaleDB + governance_audit_log | ✅ TimescaleDB + V098 + V103 + forbidden column | ✅ governance schema + governance_audit_log | ✅ 3 NEW table column + governance_audit_log |
| Guard B | ✅ 6 column type/CHECK/DEFAULT mismatch | N/A | N/A | N/A | N/A（純 CREATE）|
| Guard C 預檢 | ✅ 6 column + 3 index + CHECK enum | ✅ domain/state/engine_mode CHECK | ✅ 4 CHECK + hypertable interval | ✅ tier_name/tier_change_reason/engine_mode CHECK + 5 seed row + MV | ✅ 4 CHECK (status/engine_mode/direction/reconciliation_status) |
| Main DDL CREATE | ALTER ADD COLUMN | CREATE TABLE 19 col + hypertable | CREATE TABLE 27 col + hypertable + MV | CREATE TABLE 15+20 col + 5 seed + MV | CREATE TABLE 13+7+10 col |
| Hot-path index | 3 | 4 | 5 | 3 + 1 UNIQUE | 4 |
| COMMENT | 6 column | 1 table + 2 column | 1 table + 3 column | 3 table + 2 column | 3 table + 17 column（最詳） |
| Guard C 後驗 | ✅ idempotency | ✅ domain + chunk + policy + index | ✅ 4 CHECK + chunk + policy + 5 index + MV + FK + forbidden column | ✅ 4 CHECK + 5 seed + MV | ✅ 4 CHECK + 4 index + 2 FK |
| schema 名 patch | N/A | ✅ governance_audit_log (Guard A) | ✅ PA-DRIFT-1 (Guard A line 127-139) | ✅ V112 line 32-66 typo patch | ✅ FK target patch + COMMENT 紀錄 |

---

## §12 E2 review 重點 3 條（per PA design report §4.4）

### 12.1 earn_movement_log FK target schema 名

E2 必驗：
- SQL line: `governance_approval_id BIGINT REFERENCES learning.governance_audit_log(id)`
- **不可寫 `governance.audit_log(id)`**（spec doc §2.3.1 typo）
- COMMENT 中文紀錄 PA-DRIFT-1 lesson + V035/V053/V098 baseline reference
- Sandbox dry-run Reflection 3 驗 FK target_table = `learning.governance_audit_log`

### 12.2 Guard A idempotency 對 V103 EXTEND chain

E2 必驗：
- V100 Guard A 驗 13 base column only（**不混 V103 EXTEND 6 column scope**）
- V103 EXTEND 自身 Guard B 驗 EXTEND 6 column 對齊
- V100 重跑時對 V103 EXTEND 已 ADD 6 column 表狀態 0 RAISE（idempotent）
- V100 Guard A 邏輯使用 `array_agg(c) ... WHERE NOT EXISTS` 範式（對齊 V107 line 79-95）

### 12.3 status CHECK enum 11 值

E2 必驗：
- SQL CHECK enum 11 值字面對齊 v103_v104 base spec §2.1.1 + ADR-0026 v3 4-stage + Sprint 2 promotion stage_1-4
- Guard C 預檢 + Guard C 後驗都驗 11 值齊全
- V103 EXTEND 自身不改 status enum（per spec §2.1 確認）

---

## §13 E1 IMPL 完成 4 條回報

### 13.1 V100 spec doc 路徑 + LOC + 範式對齊

- 路徑：`docs/execution_plan/specs/2026-05-23--v100-m4-hypothesis-base-table.md`
- LOC：~700（13 主章節 + 4 AC + spec 範式對照表 + E2 重點）
- 對齊 V099 spec（568 LOC）+ V103 EXTEND spec + V106/V107/V112 sandbox SOP 範式

### 13.2 V100 SQL migration LOC + 3 table column count + 11 status enum + FK schema 名 patch

- 路徑：`sql/migrations/V100__m4_hypothesis_base_table.sql`
- LOC：663
- 3 table column count：13 / 7 / 10
- 11 status enum：draft/preregistered/shadow/stage_0r/stage_1/stage_2/stage_3/stage_4/live/retired/killed
- 4 engine_mode enum：paper/demo/live_demo/live
- earn_movement_log FK target = `learning.governance_audit_log(id)` ✅ schema 名 patch（不是 governance.audit_log）

### 13.3 cargo test sqlx_migrate_check 結果

- `cargo test --release -p openclaw_engine --lib database::migrations::`：**15/15 PASS**
- `load_migrations_real_srv_tree` PASS（V100 file 被 sqlx parser 接受 + sort chain 正確）
- pre-existing build error（live_auth_watcher_tests.rs PrivateWsBindings missing field）與 V100 無關（PA-DRIFT-4 並行 sub-agent 影響 test 端 → lib-only test path 通過）

### 13.4 下游 E2 重點 3 點 + Sandbox dry-run readiness verdict

- E2 重點 3 條（per §12.1-§12.3）
- Sandbox dry-run readiness：**OPEN — Phase B operator + PA 親手執行**
- 必驗 5 reflection SQL（per §6.1）
- 必驗 Round 1+2 idempotent
- 必驗 V100 → V103 EXTEND chain 自然 PASS

---

**END OF V100 M4 Hypothesis Discovery Base Tables Migration Spec**

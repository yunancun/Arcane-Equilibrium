---
spec: V102 Track v3 indexes + NOT NULL handling — trading.fills hot-path + fail-closed
date: 2026-05-23
author: PA
phase: Sprint 5+ Wave 1 §8.1 IMPL (per Stage F PM Phase 3e §8.1 carry-over)
status: SPEC-DRAFT
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_design.md
base_spec: srv/docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md v3 §4.1-§4.2 (Track v3 indexes + NOT NULL SSOT)
prereq_spec: srv/docs/execution_plan/specs/2026-05-23--v101-track-v3-attribution-column.md (V101 must apply first)
parent_adr:
  - ADR-0025 v3 Track-Based Strategy Attribution (4 P&L view per-track query pattern)
  - ADR-0010 Guard A/B/C migration discipline
  - ADR-0011 Linux PG empirical dry-run mandatory
file: srv/sql/migrations/V102__track_v3_indexes_not_null.sql
loc: ~280 (est.)
related_lesson:
  - V077 columnstore hypertable feature_not_supported (BEFORE INSERT/UPDATE trigger fallback)
---
> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）


# V102 Track v3 Indexes + NOT NULL Handling — Migration Spec

## §1 Context — V101 配對 + columnstore hypertable NOT NULL handling 抉擇

### 1.1 V101/V102 配對 chain

V101 (本配對 prereq) 已 land 後：
- `strategy_track` ENUM (3 值) 存在
- `trading.fills.track` column 存在 + nullable + 100% backfilled 'baseline'

V102 工作：
- ADD hot-path indexes 對 (track, ts DESC) 等 query pattern 支撐
- handle NOT NULL constraint with columnstore hypertable 約束（per V077 lesson）

### 1.2 trading.fills 是 TimescaleDB columnstore hypertable — V102 設計約束

per V077 hotfix runtime（2026-05-09 PM signed `49ceeb61`）：

```
operation not supported on hypertables that have columnstore enabled
```

對 V102 IMPL 影響：

| 操作 | columnstore hypertable 支援 | V102 處理路徑 |
|---|---|---|
| **CREATE INDEX (non-CONCURRENTLY)** | ✅ Yes (per V094 + V083 + V028 + V021 + V033 + V015 既有 fills index land 範式) | 走 CREATE INDEX IF NOT EXISTS（非 CONCURRENTLY）|
| **CREATE INDEX CONCURRENTLY** | ⚠️ 不能在 sqlx migrate BEGIN/COMMIT 內（per V100 spec §4 注意）+ Timescale 對 hypertable CONCURRENTLY 也有限制 | 走 raw `CREATE INDEX IF NOT EXISTS`（非 CONCURRENTLY） |
| **ALTER COLUMN ... SET NOT NULL** | ❌ feature_not_supported (per V077 lesson) | 走 BEFORE INSERT/UPDATE trigger fallback (per V077 同表 trigger fallback 範式) |
| **ALTER COLUMN ... SET DEFAULT** | ⚠️ 未驗 / 推測 PASS（DEFAULT 是 metadata-only operation） | 走 ALTER COLUMN ... SET DEFAULT 'baseline' (low risk;但 trigger fallback 更安全) |

**V102 NOT NULL handling 抉擇**：採 Option B trigger-based fail-closed（per V077 範式），**不**走 ALTER COLUMN SET NOT NULL。

### 1.3 V### 編號驗證

per V101 spec §1.2 + Stage A-E §8.1：V101 已收口 + V102 真正 OPEN 給 Track v3 indexes/NOT NULL。

---

## §2 既有 indexes Audit + 新 indexes 設計

### 2.1 trading.fills 既有 indexes inventory

per V005 + V015 + V017 + V021 + V028 + V033 + V083 + V094 chain：

```sql
-- V005 base indexes
idx_fills_symbol_ts ON trading.fills (symbol, ts DESC)
idx_fills_order_id ON trading.fills (order_id)

-- V015 engine_mode separation
idx_fills_engine_mode_ts ON trading.fills (engine_mode, ts DESC)

-- V017 edge predictor support
idx_fills_entry_ctx ON trading.fills (entry_context_id) WHERE entry_context_id IS NOT NULL

-- V021 exit_source
idx_fills_exit_source_non_physical ON trading.fills (exit_source, ts DESC) WHERE exit_source <> 'physical_micro_profit_lock'

-- V028 execution slippage
idx_fills_execution_slippage ON trading.fills (engine_mode, symbol, ts DESC) WHERE slippage_bps IS NOT NULL

-- V033 exit_reason
idx_fills_exit_reason_prefix ON trading.fills (...) WHERE exit_reason ...

-- V083 entry_context_id
idx_fills_entry_lookup_v083 ON trading.fills (strategy_name, engine_mode, symbol, side, ts) WHERE entry_context_id IS NULL

-- V094 close_maker_audit
idx_fills_close_maker_attempt_v094 ON trading.fills (engine_mode, ts DESC) WHERE close_maker_attempt = TRUE
```

**Total ~8 既有 indexes on trading.fills**。

### 2.2 V102 新 indexes 設計（2 indexes only）

per v3 spec §4.2 line 324 line 範式 + 收緊到「2-3 indexes only (per v103_v104 §2.1.3 範式 cap)」+ ADR-0025 v3 4 P&L view query pattern：

```sql
-- Index 1: track + ts DESC for time-series per-track query (P&L view 主索引)
CREATE INDEX IF NOT EXISTS idx_fills_track_ts_v102
    ON trading.fills (track, ts DESC);

-- Index 2: strategy + track for cross-track audit query (track 對映 sanity check)
CREATE INDEX IF NOT EXISTS idx_fills_strategy_track_v102
    ON trading.fills (strategy_name, track);
```

#### 查詢 → 索引對映

| Index | Hot-path query | 對映設計依據 |
|---|---|---|
| `idx_fills_track_ts_v102` | `WHERE track = 'direct_exploit' AND ts > now() - INTERVAL '7d' ORDER BY ts DESC` | per-track time-series P&L attribution（4 P&L view in v3 spec §4.3） |
| `idx_fills_strategy_track_v102` | `WHERE strategy_name='grid_trading' GROUP BY track`（cross-track audit）| Track A/B/C 對映 strategy 一致性 verify（per ADR-0025 v3 X-AC5 cross-spec AC） |

**為什麼不走 v3 spec 12 indexes**：v3 spec §4.2 設計對應 12 表 ALTER + 4 placeholder time column；但本 V102 spec scope 收緊到 trading.fills only — 2 indexes 已覆蓋核心 query pattern。其他 indexes 屬 Sprint 5+ Wave 2 Phase 2 IMPL（per V102 §8 carry-over）。

**為什麼不走 CONCURRENTLY**：
- sqlx migrate 將 V102 包入 BEGIN/COMMIT；CREATE INDEX CONCURRENTLY 在 transaction 內 RAISE
- 對齊 V094 + V083 + V028 等既有 fills index 範式（全 CREATE INDEX IF NOT EXISTS 非 CONCURRENTLY）
- columnstore hypertable 對 CONCURRENTLY 限制未明確驗（per V077 lesson 一系列 hypertable + columnstore 操作 feature_not_supported）；保守採非 CONCURRENTLY

### 2.3 indexes 衝突風險評估

| 風險 | 評估 | 緩解 |
|---|---|---|
| Index 1 (track, ts DESC) 與 V005 idx_fills_symbol_ts 高相關 | 低 — track 是新維度；symbol 不重疊 | 0 conflict |
| Index 2 (strategy_name, track) 與 V083 idx_fills_entry_lookup_v083 (strategy_name, engine_mode, symbol, side, ts) | 低 — V083 是 partial index WHERE entry_context_id IS NULL；本 index full | 0 conflict |
| Index 1 創建期間表 lock | 中 — 非 CONCURRENTLY = AccessShareLock + ExclusiveLock | 對齊 V094 / V083 land 範式（已驗 acceptable）；deploy at low-IO window |

---

## §3 NOT NULL Handling Decision (3 Options 比對 + PA Verdict)

### 3.1 Option A — 永遠 NULL allowed (legacy fill 預留 NULL slot)

```sql
-- 不做 NOT NULL constraint;writer 規範靠 application layer
-- V102 不 ALTER COLUMN
```

| 維度 | Option A 評估 |
|---|---|
| **columnstore 兼容** | ✅ 完美 — 0 ALTER 操作 |
| **fail-closed 強度** | ❌ 弱 — writer bug 漏填 track 不 RAISE；silent corruption 風險 |
| **Sprint 5+ Track A/B writer 上線後** | 不變式無強制 — Track A/B writer 必依賴 application code self-discipline |
| **legacy fill 處理** | NULL allowed → 可保留 V101 backfill 中漏掉的 edge case row（但 V101 backfill 已 100%）|
| **rollback 風險** | 0 — schema 永遠 backward compatible |
| **per ADR-0025 v3 對齊** | 部分對齊 — v3 spec V102 採 NOT NULL + DEFAULT 'baseline' |

**評分**：fail-closed 強度太弱（per 根原則 6）

### 3.2 Option B — BEFORE INSERT/UPDATE trigger fail-closed enforce (PA 推薦)

```sql
-- ALTER COLUMN ... SET DEFAULT 'baseline' (metadata-only;預期 PASS)
ALTER TABLE trading.fills
    ALTER COLUMN track SET DEFAULT 'baseline';

-- BEFORE INSERT/UPDATE trigger fallback enforce NOT NULL (per V077 範式)
CREATE OR REPLACE FUNCTION trading.enforce_fills_track_not_null()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.track IS NULL THEN
        RAISE EXCEPTION
            'V102 trigger violation: trading.fills.track must not be NULL '
            '(per ADR-0025 v3 Track-based attribution unfair if track unset). '
            'Writer must explicitly set track to direct_exploit/asds_factory/baseline.';
    END IF;
    RETURN NEW;
END
$fn$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgrelid = 'trading.fills'::regclass
          AND tgname = 'trg_fills_track_not_null_v102'
          AND NOT tgisinternal
    ) THEN
        CREATE TRIGGER trg_fills_track_not_null_v102
            BEFORE INSERT OR UPDATE OF track ON trading.fills
            FOR EACH ROW
            EXECUTE FUNCTION trading.enforce_fills_track_not_null();
        RAISE NOTICE 'V102: trg_fills_track_not_null_v102 installed (NOT NULL enforced via trigger;columnstore-safe)';
    ELSE
        RAISE NOTICE 'V102: trg_fills_track_not_null_v102 already present;skipping';
    END IF;
END $$;
```

| 維度 | Option B 評估 |
|---|---|
| **columnstore 兼容** | ✅ 完美 — trigger fallback 對齊 V077 範式（已 verified 2026-05-09 PM signed） |
| **fail-closed 強度** | ✅ 強 — writer 漏填 RAISE EXCEPTION |
| **Sprint 5+ Track A/B writer 上線後** | 強制 — writer 必填 'direct_exploit'/'asds_factory'；漏填即 RAISE（catch early） |
| **legacy fill 處理** | V101 backfill 已 100% 'baseline'；trigger 不 backfill legacy；新 row 強制非 NULL |
| **rollback 風險** | 低 — DROP TRIGGER 可逆 |
| **per ADR-0025 v3 對齊** | 對齊 fail-closed 意圖；NOT NULL semantic 走 trigger 而非 column constraint |
| **DEFAULT 'baseline' 安全網** | ✅ 雙保險 — writer 未顯式設 track 時 INSERT 走 default = 'baseline'（writer 漏填降級行為） |

**評分**：fail-closed + columnstore 兼容 + 雙保險 — 強推

### 3.3 Option C — backfill UPDATE + ALTER COLUMN SET NOT NULL (data migration heavy)

```sql
-- 嘗試 ALTER COLUMN SET NOT NULL
ALTER TABLE trading.fills ALTER COLUMN track SET NOT NULL;
-- 預期 columnstore RAISE feature_not_supported
```

| 維度 | Option C 評估 |
|---|---|
| **columnstore 兼容** | ❌ 預期 RAISE feature_not_supported (per V077 教訓對 trading.fills CHECK constraint 失敗) |
| **fail-closed 強度** | ✅ 強（若 PASS） |
| **runtime 風險** | 高 — production 失敗 = rollback / 手動 fix；deploy window 受限 |
| **per ADR-0025 v3 對齊** | v3 spec §4.1 line 302 寫 `ALTER COLUMN track SET NOT NULL`；但 v3 spec 未考慮 trading.fills columnstore constraint |

**評分**：runtime 風險過高（per V077 教訓）— 不推

### 3.4 PA Verdict

**選 Option B**（BEFORE INSERT/UPDATE trigger + ALTER COLUMN SET DEFAULT 'baseline'）。

3 理由：
1. **columnstore-safe**：完全對齊 V077 hotfix 範式（PM signed 2026-05-09 49ceeb61），avoid feature_not_supported RAISE
2. **fail-closed 強度**：writer 漏填 RAISE EXCEPTION + DEFAULT 'baseline' 雙保險（catch early + 降級行為）
3. **per ADR-0025 v3 semantic 對齊**：NOT NULL 不變式達成（writer 必填 track），只是 enforcement mechanism 從 column constraint 改 trigger

---

## §4 Guard A/B/C 設計

### 4.1 Guard A — V101 prerequisite check

```sql
DO $$
BEGIN
    -- trading.fills.track column 必存在 (V101 已 land)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'trading' AND table_name = 'fills'
          AND column_name = 'track'
          AND udt_name = 'strategy_track'
    ) THEN
        RAISE EXCEPTION
            'V102 Guard A FAIL: trading.fills.track missing — V101 必先 apply。'
            'Re-check migration order。';
    END IF;

    -- strategy_track ENUM 必存在 (V101 已 CREATE TYPE)
    IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'strategy_track'
    ) THEN
        RAISE EXCEPTION
            'V102 Guard A FAIL: strategy_track ENUM missing — V101 必先 apply。';
    END IF;

    -- V101 backfill 100% verify (0 NULL)
    IF EXISTS (
        SELECT 1 FROM trading.fills WHERE track IS NULL LIMIT 1
    ) THEN
        RAISE EXCEPTION
            'V102 Guard A FAIL: trading.fills.track still has NULL row。'
            'V101 backfill 必先 100% 完成。';
    END IF;

    RAISE NOTICE 'V102 Guard A PASS: V101 prerequisite verified';
END $$;
```

### 4.2 Guard B — DEFAULT + trigger idempotency check

```sql
DO $$
DECLARE
    v_column_default TEXT;
    v_trigger_def TEXT;
BEGIN
    -- DEFAULT 'baseline' 存在情境驗對齊 (idempotency)
    SELECT column_default INTO v_column_default
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'track';

    IF v_column_default IS NOT NULL THEN
        IF v_column_default NOT ILIKE '%baseline%' THEN
            RAISE EXCEPTION
                'V102 Guard B FAIL: trading.fills.track DEFAULT drift。'
                'Expected ''baseline''::strategy_track, got %。', v_column_default;
        END IF;
    END IF;

    -- trigger 存在情境驗對齊 (idempotency)
    SELECT pg_get_triggerdef(t.oid)
      INTO v_trigger_def
    FROM pg_trigger t
    WHERE t.tgrelid = 'trading.fills'::regclass
      AND t.tgname = 'trg_fills_track_not_null_v102'
      AND NOT t.tgisinternal;

    IF v_trigger_def IS NOT NULL THEN
        IF v_trigger_def NOT ILIKE '%BEFORE INSERT OR UPDATE OF track%'
           OR v_trigger_def NOT ILIKE '%enforce_fills_track_not_null%' THEN
            RAISE EXCEPTION
                'V102 Guard B FAIL: trg_fills_track_not_null_v102 definition drift。'
                'Expected BEFORE INSERT OR UPDATE OF track + enforce_fills_track_not_null function, got %。',
                v_trigger_def;
        END IF;
    END IF;
END $$;
```

### 4.3 Guard C — 後驗 indexes + DEFAULT + trigger 全 land

```sql
DO $$
DECLARE
    v_idx1 TEXT;
    v_idx2 TEXT;
    v_column_default TEXT;
    v_trigger_count INT;
BEGIN
    -- Index 1 land
    SELECT pg_get_indexdef(c.oid) INTO v_idx1
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'trading'
      AND c.relname = 'idx_fills_track_ts_v102';

    IF v_idx1 IS NULL THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: idx_fills_track_ts_v102 missing after DDL。';
    END IF;
    IF position('track' IN v_idx1) = 0 OR position('ts' IN v_idx1) = 0 THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: idx_fills_track_ts_v102 definition drift。Actual: %。', v_idx1;
    END IF;

    -- Index 2 land
    SELECT pg_get_indexdef(c.oid) INTO v_idx2
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'trading'
      AND c.relname = 'idx_fills_strategy_track_v102';

    IF v_idx2 IS NULL THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: idx_fills_strategy_track_v102 missing after DDL。';
    END IF;
    IF position('strategy_name' IN v_idx2) = 0 OR position('track' IN v_idx2) = 0 THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: idx_fills_strategy_track_v102 definition drift。Actual: %。', v_idx2;
    END IF;

    -- DEFAULT 'baseline'
    SELECT column_default INTO v_column_default
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'track';

    IF v_column_default IS NULL OR v_column_default NOT ILIKE '%baseline%' THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: trading.fills.track DEFAULT not set to baseline。Actual: %。', v_column_default;
    END IF;

    -- trigger 存在
    SELECT COUNT(*) INTO v_trigger_count
    FROM pg_trigger
    WHERE tgrelid = 'trading.fills'::regclass
      AND tgname = 'trg_fills_track_not_null_v102'
      AND NOT tgisinternal;

    IF v_trigger_count <> 1 THEN
        RAISE EXCEPTION
            'V102 Guard C FAIL: trg_fills_track_not_null_v102 trigger count = %, expected 1。', v_trigger_count;
    END IF;

    RAISE NOTICE 'V102 Guard C PASS: 2 index + DEFAULT + trigger all verified';
END $$;
```

---

## §5 Linux PG Dry-run + CONCURRENTLY consideration

per ADR-0011 mandatory + V094 close_maker_audit 範式：

### 5.1 Phase B Sandbox dry-run 必驗 5 SQL（Round 1 apply 後）

```bash
# Round 1: psql -d trading_ai_sandbox -f V102__track_v3_indexes_not_null.sql

# Reflection 1: 2 index land
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT n.nspname, c.relname, pg_get_indexdef(c.oid) AS index_def
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'trading'
  AND c.relname IN ('idx_fills_track_ts_v102', 'idx_fills_strategy_track_v102')
ORDER BY c.relname;
\""
# Expected:
#   idx_fills_strategy_track_v102 | CREATE INDEX ... (strategy_name, track)
#   idx_fills_track_ts_v102       | CREATE INDEX ... (track, ts DESC)
```

```bash
# Reflection 2: DEFAULT 'baseline' set
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT column_name, column_default, is_nullable
FROM information_schema.columns
WHERE table_schema = 'trading' AND table_name = 'fills' AND column_name = 'track';
\""
# Expected: track | 'baseline'::strategy_track | YES (still nullable;由 trigger 強制)
```

```bash
# Reflection 3: trigger 存在 + 對齊
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT tgname, pg_get_triggerdef(oid) AS trigger_def
FROM pg_trigger
WHERE tgrelid = 'trading.fills'::regclass
  AND tgname = 'trg_fills_track_not_null_v102'
  AND NOT tgisinternal;
\""
# Expected:
#   trg_fills_track_not_null_v102 | CREATE TRIGGER ... BEFORE INSERT OR UPDATE OF track ON trading.fills FOR EACH ROW EXECUTE FUNCTION trading.enforce_fills_track_not_null()
```

```bash
# Reflection 4: trigger fail-closed 行為驗（dry-run 不污染 prod）
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
BEGIN;
INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, engine_mode, track)
VALUES (now(), 'dry-run-test-v102', 'dummy-order', 'BTCUSDT', 'Buy', 0.001, 50000, 'paper', NULL);
ROLLBACK;
\""
# Expected:
#   ERROR: V102 trigger violation: trading.fills.track must not be NULL ...
```

```bash
# Reflection 5: DEFAULT 'baseline' 行為驗（dry-run 不污染 prod）
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
BEGIN;
INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, engine_mode)
VALUES (now(), 'dry-run-default-v102', 'dummy-order', 'BTCUSDT', 'Buy', 0.001, 50000, 'paper');
SELECT track FROM trading.fills WHERE fill_id = 'dry-run-default-v102';
ROLLBACK;
\""
# Expected: track | baseline (DEFAULT 'baseline' 自動填)
```

### 5.2 Phase B Sandbox dry-run Round 2 idempotency 驗

```bash
# Round 2: psql -d trading_ai_sandbox -f V102 重 apply
# Expected: 0 ERROR + 0 RAISE EXCEPTION (Guard B 自然 PASS + Guard C 自然 PASS)
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -f /home/ncyu/srv/sql/migrations/V102__track_v3_indexes_not_null.sql 2>&1 | grep -E 'NOTICE|ERROR'"
# Expected NOTICE (idempotent):
#   - 'V102 Guard A PASS: V101 prerequisite verified'
#   - 'V102: trg_fills_track_not_null_v102 already present;skipping'
#   - 'V102 Guard C PASS: 2 index + DEFAULT + trigger all verified'
# Expected ERROR: 0
```

### 5.3 CONCURRENTLY consideration

per V100 spec §4 注意 + sqlx migrate BEGIN/COMMIT 約束：

**本 V102 走 CREATE INDEX IF NOT EXISTS（非 CONCURRENTLY）**：
- sqlx migrate transaction-wrapped → CONCURRENTLY 會 RAISE in transaction
- 對齊 V094 + V083 + V028 既有 trading.fills index land 範式（全 IF NOT EXISTS）
- production deploy 建議 low-IO window（per V077 columnstore hotfix runtime PM 範式：authorized low-IO restart window）
- 2 index 數量少；非 huge table index build cost；預期 wall clock ~30s-2min per index on production data volume

---

## §6 4-Phase Deploy Chain

### 6.1 Phase A — Mac IMPL

```
Phase A: Mac IMPL (E1 work)
  ↓
  1. 寫 V102__track_v3_indexes_not_null.sql (~280 LOC)
  2. cargo test --release -p openclaw_engine --lib database::migrations:: PASS
     (sqlx Migrator parser accept + sort chain V101 → V102 → V103 monotonic)
  3. commit + push (per CLAUDE.md §git: 不 amend / 不 force push;narrow staging)
```

### 6.2 Phase B — Sandbox dry-run

```
Phase B: Sandbox dry-run (per ADR-0011 mandatory)
  ↓
  4. ssh trade-core git pull --ff-only
  5. ssh trade-core psql -d trading_ai_sandbox -f V102 Round 1 (apply + 5 reflection SQL)
  6. ssh trade-core psql -d trading_ai_sandbox -f V102 Round 2 (idempotent re-apply; 0 ERROR/RAISE)
  7. sandbox V102 → V103 chain reapply (V103 EXTEND Guard A 不依 trading.fills index; chain unaffected)
```

### 6.3 Phase C — Production deploy

```
Phase C: Production deploy (PA + E1 + operator)
  ↓
  8. OPENCLAW_AUTO_MIGRATE=0→1 + low-IO window 確認 (per V077 columnstore hotfix 範式)
  9. restart_all.sh (no rebuild;auto-migrate land V102 chain)
  10. expect _sqlx_migrations MAX 101→102

  Alt path: psql -f raw apply (per V100 production deploy 範式)
   - 走 metadata register 路徑 (post-apply 手動 INSERT _sqlx_migrations row)
```

### 6.4 Phase D — Verify

```
Phase D: verify (per Sprint 4+ AC-1b 範式)
  ↓
  11. _sqlx_migrations MAX = 102 confirm
  12. 2 target index 物理存在 (idx_fills_track_ts_v102 + idx_fills_strategy_track_v102)
  13. DEFAULT 'baseline' 生效 (test INSERT 缺 track → 自動 baseline)
  14. trigger 強制 NOT NULL (test INSERT track=NULL → RAISE EXCEPTION)
  15. engine startup 0 panic
  16. 30 min observe + AC-1b SQL 重驗
```

---

## §7 V101 → V102 Sequential Apply 對齊

```
V101 (track column EXTEND + backfill 100% baseline) [must apply first]
   ↓
V102 (indexes + DEFAULT baseline + trigger NOT NULL fail-closed) [本 spec]
   ↓
V103 (EXTEND M4 hypothesis 6 column) [不依賴 V101/V102; 順序中間是 V100 → V103 chain]
   ↓
V106/V107/V112 (Sprint 1A-ζ / Sprint 2; 已 land)
```

**V102 Guard A 確認 V101 已 apply**：
- trading.fills.track column 存在 + 對齊 strategy_track ENUM
- 0 NULL row (V101 backfill 100% 完成)

如 V101 沒 apply → V102 Guard A FAIL → RAISE EXCEPTION → 0 destructive operation。

**V102 對 V103 chain 不依賴**：V103 EXTEND learning.hypotheses 與 trading.fills.track / indexes 完全無交集。

---

## §8 3 Acceptance Criteria + Sprint 5+ Wave 2 Phase 2 Carry-over

### AC-1: V102 file LAND + sqlx parser accept

- `sql/migrations/V102__track_v3_indexes_not_null.sql` 存在
- LOC ~280
- `cargo test --release -p openclaw_engine --lib database::migrations::tests::load_migrations_real_srv_tree` PASS

**Status**：🟡 PENDING（Phase A E1 IMPL）

### AC-2: Sandbox Round 1+2 idempotent + 5 reflection SQL PASS

- 2 index 物理 land
- DEFAULT 'baseline' 生效
- trigger 強制 NOT NULL fail-closed
- Round 2 idempotency 驗（0 ERROR + 0 RAISE EXCEPTION）

**Status**：🟡 PENDING（Phase B operator + PA 親手執行）

### AC-3: Production engine restart + Sprint 5+ Writer path 預留

- Phase C auto-migrate or raw psql land V102
- engine startup 0 panic
- 30 min observe + writer 走 DEFAULT 'baseline' 行為 + 0 trigger violation
- **Sprint 5+ Wave 2 Phase 2 carry-over readiness**：Track A/B Rust writer 上線後改填 'direct_exploit'/'asds_factory'，trigger 強制 catch 漏填 row

**Status**：🟡 PENDING（Phase C-D operator + PA + E1 + Sprint 5+ Wave 2 dependency）

### Sprint 5+ Wave 2 Phase 2 Carry-over (V103+)

V101/V102 只覆蓋 trading.fills；其他 11 表 + 2 新表 + 4 view + governance.track_kill_events 屬 Sprint 5+ Wave 2 Phase 2 work：

| Item | V### 預估 | 對應 v3 spec scope | 估工時 |
|---|---|---|---|
| trading.intents/orders/signals/risk_verdicts/position_snapshots/decision_outcomes ADD track | V104+ | v3 spec §3.2 + §3.4 11 表 | 8-12 hr |
| learning.lease_transitions / strategy_trial_ledger / cost_edge_advisor_log ADD track | V104+ | v3 spec §3.2 learning.* | 4-6 hr |
| agent.ai_invocations / decision_objects ADD track | V104+ | v3 spec §3.2 agent.* | 2-4 hr |
| CREATE TABLE governance.track_kill_events | V104+ | v3 spec §4.4 | 2-3 hr |
| 4 P&L view (track_direct_exploit_daily / track_asds_factory_daily / track_baseline_daily / track_summary_daily) | V104+ view | v3 spec §4.3 | 2-3 hr |
| 12 indexes + NOT NULL trigger fan-out 對 11 ALTER 表 | V104+ | v3 spec §4.1 + §4.2 | 8-12 hr |
| Rust enum + writer fan-out (5 既有策略 + Track A/B writer 上線) | Sprint 5+ Wave 2 Rust IMPL | ADR-0025 v3 Rust implementation anchors | 12-20 hr |

**total Sprint 5+ Wave 2 Phase 2 carry-over effort 估**：~40-60 hr E1 + E2 + dispatch chain。

---

## §9 E2 重點審查 3 點

### 9.1 columnstore hypertable trigger fallback path 對齊 V077 範式

**E2 必驗**：
- V102 採 trigger-based NOT NULL enforcement（**不**走 ALTER COLUMN SET NOT NULL）
- trigger 名 `trg_fills_track_not_null_v102` + function 名 `trading.enforce_fills_track_not_null` 對齊 V077 範式（`trg_fills_engine_mode_known_values` + `trading.enforce_fills_engine_mode_known_values()`）
- BEFORE INSERT OR UPDATE OF track ON trading.fills FOR EACH ROW + RAISE EXCEPTION on NULL
- Sandbox dry-run Reflection 4 驗 trigger fail-closed 行為（test INSERT track=NULL → RAISE）

**潛在 catch**：E1 IMPL 嘗試 ALTER COLUMN SET NOT NULL → production RAISE feature_not_supported → 走 rollback；E2 reject 不對齊 V077 範式版本。

### 9.2 indexes 數量 + 非 CONCURRENTLY 路徑

**E2 必驗**：
- V102 SQL 創建 2 index only（不 12 index per v3 spec）
- 均走 CREATE INDEX IF NOT EXISTS（非 CONCURRENTLY，per sqlx migrate transaction-wrapped 約束）
- index 對齊 (track, ts DESC) + (strategy_name, track) 兩 query pattern
- Sandbox dry-run Reflection 1 驗 2 index 物理 land + def 對齊

**潛在 catch**：E1 IMPL 跑 v3 spec 全 12 index = scope creep；E2 reject。

### 9.3 DEFAULT 'baseline' 雙保險語意 + Sprint 5+ Writer path 預留 COMMENT

**E2 必驗**：
- ALTER COLUMN ... SET DEFAULT 'baseline' 走得通（metadata-only operation，columnstore 兼容 — 預期 PASS；如 RAISE feature_not_supported 需 fallback 路徑）
- Writer 漏填 track → DEFAULT 'baseline'（降級行為）→ 不 trigger violation（DEFAULT 自動填非 NULL）
- COMMENT ON COLUMN trading.fills.track 描述 Sprint 5+ Writer path 預留語意（per V101 spec §2.2）
- Sandbox dry-run Reflection 5 驗 DEFAULT 行為

**潛在 catch**：若 DEFAULT 'baseline' 在 columnstore hypertable 走不通（PA 預設可 PASS 但未 sandbox empirical 驗）→ trigger 唯一防線 + Writer 必顯式填；spec amend 路徑 = drop DEFAULT 段 + 強化 trigger 必填規則。

---

## §10 spec 範式對齊與 commit log

### 10.1 spec 範式對齊 V094/V077 範式對照表

| Aspect | V077 engine_mode | V094 close_maker_audit | **V102 Track v3 indexes/NOT NULL (本)** |
|---|---|---|---|
| LOC | 159 | 229 | ~280 |
| Guard A | trading.fills + engine_mode + ts column | trading.fills + 13 column 完整 | trading.fills.track exist + ENUM + V101 backfill 100% |
| Guard B | bad engine_mode value | 2 column type/CHECK/DEFAULT mismatch | DEFAULT + trigger idempotency check |
| Main DDL — index | N/A | 1 partial index (close_maker_attempt=TRUE) | 2 index (track,ts DESC) + (strategy_name,track) |
| Main DDL — CHECK/trigger | CHECK with trigger fallback (feature_not_supported) | NOT VALID CHECK 10-value | **trigger BEFORE INSERT/UPDATE OF track NOT NULL** + **ALTER SET DEFAULT 'baseline'** |
| Guard C 後驗 | CHECK / trigger constraint def | CHECK + index def | 2 index + DEFAULT + trigger 全 verify |
| columnstore tolerance | trigger fallback | nullable ADD COLUMN safe | trigger fallback + DEFAULT (metadata-only) safe |

### 10.2 revision history

| date | author | revision |
|---|---|---|
| 2026-05-23 | PA | v1 SPEC-DRAFT — operator scope push back trading.fills only；NOT NULL handling Option B 推薦（trigger-based fail-closed per V077 範式）；indexes 2 only 對齊 hot-path query 設計；其他 11 表 + view + kill_events 拆 Sprint 5+ Wave 2 Phase 2 carry-over |

---

**END OF V102 Track v3 Indexes + NOT NULL Handling Migration Spec**

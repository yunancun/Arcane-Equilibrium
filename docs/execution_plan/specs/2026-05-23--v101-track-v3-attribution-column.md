---
spec: V101 Track v3 attribution column EXTEND — trading.fills only
date: 2026-05-23
author: PA
phase: Sprint 5+ Wave 1 §8.1 IMPL (per Stage F PM Phase 3e §8.1 carry-over)
status: SPEC-DRAFT
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_design.md
base_spec: srv/docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md v3 §3.1-§3.4 (Track v3 attribution SSOT)
parent_adr:
  - ADR-0025 v3 Track-Based Strategy Attribution (12-table verdict)
  - ADR-0026 v3 Direct Exploit bypass CPCV (preregistration + future replay match)
  - ADR-0010 Guard A/B/C migration discipline
  - ADR-0011 Linux PG empirical dry-run mandatory
file: srv/sql/migrations/V101__track_v3_attribution_column.sql
loc: ~250 (est.)
push_back_from_operator: Yes (operator prompt scope = trading.fills only, NOT v3 spec full 12-table)
---

# V101 Track v3 Attribution Column EXTEND — Migration Spec

## §1 Context — operator scope push back + v5.7 4 follow-up land

### 1.1 為什麼是 trading.fills only 不是 12 表

operator prompt 2026-05-23 拍板「Sprint 5+ Wave 1 §8.1 V101/V102 spec design — Track v3 attribution column EXTEND，3-4 hr single-thread」。

**PA push back（強制 scope 收緊）**：

`docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md` v3 SSOT spec **完整 scope** =
- CREATE TYPE strategy_track ENUM (3 值)
- ADD COLUMN track on 12 既存表
- CREATE TABLE 2 新表 (learning.hypotheses + learning.hypothesis_preregistration)
- backfill 12 既存表 全部 row → 'baseline'
- V101 結尾 assert 0 NULL row

estimated effort = **40-60 hr E1 (12 table backfill + 2 table CREATE + assert + sandbox dry-run × 2 round)** — 遠超 3-4 hr single-thread budget。

**PA verdict**：operator 「現在順手推上去」+ 3-4 hr single-thread 字面只夠做 single-table EXTEND；其他 11 表 + 2 新表 + 4 view + governance.track_kill_events 必拆 Sprint 5+ Wave 2 Phase 2 處理。

**收緊 scope 至 trading.fills only**：
- CREATE TYPE strategy_track ENUM (3 值)
- ADD COLUMN track on trading.fills (nullable)
- backfill trading.fills 全 row → 'baseline'

**衝突解析**：v3 spec §3.3.1 寫的 learning.hypotheses 已被 V100 (2026-05-23) CREATE TABLE land — 從本 V101 spec 削除（base 表概念已被 M4 hypothesis_discovery 走另一條路徑）。spec 註解 carry-over「learning.hypotheses 取消 v3 spec CHECK (track='asds_factory') constraint，Sprint 5+ Wave 2 Phase 2 處理 if needed」。

### 1.2 V### 編號驗證

per Stage A-E §8.1 + Sprint 1B late §4.1.1 PA design report (`2026-05-23--sprint_1b_late_v100_m4_hypothesis_base_table_design.md`)：

| V### | 真實佔用 | 來源 | 狀態 |
|---|---|---|---|
| V099 | autonomy_level_config (system.autonomy_level_config + _switch_audit) | `2026-05-22--v099-autonomy-level-config.md` 568 LOC | SPEC-LAND / IMPL-PENDING |
| V100 | M4 hypothesis_discovery base (learning.hypotheses + hypothesis_preregistration + earn_movement_log) | `2026-05-23--v100-m4-hypothesis-base-table.md` 663 SQL LOC | LAND 2026-05-23 production |
| **V101** | **Track v3 attribution column EXTEND on trading.fills** (本 spec) | v5.7 4 follow-up + dispatch_consolidation §3.2 line 336 | 本 IMPL |
| **V102** | **Track v3 indexes + NOT NULL handling on trading.fills** | v5.7 4 follow-up | V101 配對 |
| V103 | EXTEND M4 hypothesis columns (6 additional EXTEND) | LAND 2026-05-22 production | LAND |
| V104 | retired no-op | per v103_v104 §1.3 | retired |

**V101/V102 真正 OPEN** — Track v3 attribution column EXTEND 可立即 land。

### 1.3 為什麼 trading.fills 是 P1（不是 trading.intents / trading.signals）

| 表 | Track v3 attribution 優先級 | 理由 |
|---|---|---|
| **trading.fills** | **P1 本 V101** | Strategy P&L attribution 主要源（realized_pnl + fee + qty + price）；4 P&L view 全建在 fills 之上；MIT Track 對齊核心 |
| trading.intents | P2 Sprint 5+ Wave 2 | intent → fill 對映可走 order_id JOIN 反查；非 P&L 直接源 |
| trading.signals | P2 Sprint 5+ Wave 2 | signal → intent → order → fill chain；signal-level Track 是 second-order |
| trading.orders | P2 Sprint 5+ Wave 2 | order rate / venue mix 可走 JOIN fills 反查 |
| trading.decision_outcomes | P2 Sprint 5+ Wave 2 | ML label table；走 context_id JOIN 反查 |
| trading.risk_verdicts | P3 Sprint 5+ Wave 3 | Guardian audit；low frequency |
| trading.position_snapshots | P3 Sprint 5+ Wave 3 | position state；走 JOIN fills 反查 |

**收緊到 trading.fills only 不破 Track v3 設計意圖** — P&L attribution 4 view (per v3 spec §4.3) 可以全建在 fills.track 之上。其他 attribution surface 屬 Sprint 5+ Wave 2 Phase 2 work。

### 1.4 Critical constraint: trading.fills 是 TimescaleDB columnstore hypertable

per V077 hotfix runtime（2026-05-09 PM signed `49ceeb61`）：

```
operation not supported on hypertables that have columnstore enabled
```

**影響 V101 IMPL design**：
- ADD COLUMN nullable 走得通（per V094 close_maker_audit 2026-05-15 land 範式：`ADD COLUMN IF NOT EXISTS close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE` 在 fills hypertable PASS）
- backfill UPDATE 走得通（per V094 走 batched UPDATE 範式）
- **V101 不要 ALTER COLUMN ... SET NOT NULL**（columnstore feature_not_supported），改在 V102 處理（per V102 spec §3 NOT NULL handling decision）
- CONCURRENTLY index 不適用 sqlx migrate BEGIN/COMMIT 包裹

### 1.5 v5.7 4 follow-up 收口

dispatch_consolidation §3.2 line 336 「V099/V100 (Track v3) — v5.7 4 follow-up」假佔位 → 因 V099/V100 順走至 autonomy + M4 base，**Track v3 上移至 V101/V102**。本 V101 收口 v5.7 4 follow-up 之一（Track v3 attribution）。

---

## §2 trading.fills 既有 Column Audit + ADD COLUMN track

### 2.1 trading.fills 既有 column inventory

per V003 base + 6 ALTER chain（V008 + V021 + V028 + V033 + V077 + V083 + V094）：

```sql
-- V003 base (13 column):
ts TIMESTAMPTZ NOT NULL          -- PK partition column
fill_id TEXT NOT NULL            -- PK
order_id TEXT NOT NULL           -- logical FK → orders
symbol TEXT NOT NULL
side TEXT NOT NULL
qty REAL NOT NULL
price REAL NOT NULL
fee REAL DEFAULT 0
fee_currency TEXT DEFAULT 'USDT'
realized_pnl REAL DEFAULT 0
is_paper BOOLEAN DEFAULT FALSE
strategy_name TEXT
context_id TEXT                  -- logical FK → decision_context_snapshots
details JSONB
-- PRIMARY KEY (fill_id, ts)

-- V008 (1 column ADD): fee_rate REAL DEFAULT 0
-- V015 (1 column ADD via separate migration): engine_mode TEXT
-- V021 (1 column ADD): exit_source TEXT
-- V028 (6 column ADD): reference_price/reference_ts_ms/reference_source/slippage_bps/liquidity_role/fill_latency_ms
-- V033 (1 column ADD): exit_reason TEXT
-- V077 (no column ADD; CHECK constraint 或 trigger on engine_mode)
-- V083 (2 column ADD): entry_context_id TEXT (+ CHECK constraint for close fills)
-- V094 (2 column ADD): close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE + close_maker_fallback_reason TEXT NULL
```

**total ~26 column already on trading.fills**。

### 2.2 ADD COLUMN track 設計

```sql
-- 必先 CREATE TYPE strategy_track ENUM
DO $$ BEGIN
    CREATE TYPE strategy_track AS ENUM (
        'direct_exploit',    -- Track A: hand-coded Rust, cash flow priority
        'asds_factory',      -- Track B: schema-only N+1-N+3, LLM hypothesis
        'baseline'           -- Track C: frozen textbook 5 strategy, A/B baseline
    );
EXCEPTION
    WHEN duplicate_object THEN
        RAISE NOTICE 'V101: strategy_track ENUM already exists; skipping CREATE TYPE';
END $$;

-- ADD COLUMN track on trading.fills (nullable; per V094 範式)
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;

COMMENT ON COLUMN trading.fills.track IS
    'Strategy track attribution dimension per ADR-0025 v3。'
    '3 值 enum: direct_exploit (Track A hand-coded Rust);'
    'asds_factory (Track B schema-only LLM hypothesis);'
    'baseline (Track C frozen textbook 5 strategy A/B reference)。'
    '既有 5 textbook 策略 全 backfill baseline;'
    'Sprint 5+ Track A/B 上線後新 fill 由 writer 顯式填 direct_exploit/asds_factory。'
    'V101 此 column NULL allowed (legacy fill 補不可達 row);'
    'V102 NOT NULL handling 走 BEFORE INSERT trigger 強制 fail-closed (per columnstore feature_not_supported)。';
```

### 2.3 Backfill 設計

per V003 既有 5 textbook strategy_name 全 → 'baseline' track。

```sql
-- Round 1: batch UPDATE (per v3 spec §3.4 範式 + V094 batched UPDATE 範式)
DO $$
DECLARE
    v_updated INT;
    v_total INT := 0;
BEGIN
    LOOP
        UPDATE trading.fills
           SET track = 'baseline'
         WHERE fill_id IN (
             SELECT fill_id
               FROM trading.fills
              WHERE track IS NULL
              LIMIT 10000
              FOR UPDATE SKIP LOCKED
         );
        GET DIAGNOSTICS v_updated = ROW_COUNT;
        v_total := v_total + v_updated;
        EXIT WHEN v_updated = 0;
        PERFORM pg_sleep(0.1);  -- 100ms breath; avoid lock contention
    END LOOP;
    RAISE NOTICE 'V101 backfill: % rows updated to track=baseline', v_total;
END $$;
```

**Batch sizing rationale**：
- batch 10000 + sleep 100ms = ~6k row/sec sustained
- 估 trading.fills row volume：~100k-1M（live 8 個月 demo + paper 累計）→ 17s-3min wall clock
- per V094 close_maker_audit 2026-05-15 land 範式（同表 ADD COLUMN + index + CHECK constraint）已驗 acceptable lock impact

### 2.4 V101 結尾 backfill verify

```sql
DO $$
DECLARE
    null_count INT;
BEGIN
    SELECT COUNT(*) INTO null_count
      FROM trading.fills
     WHERE track IS NULL;

    IF null_count > 0 THEN
        RAISE EXCEPTION
            'V101 backfill incomplete: % rows still have track=NULL. '
            'Re-run backfill DO block or investigate writer race.', null_count;
    END IF;
    RAISE NOTICE 'V101: trading.fills.track 100%% backfilled (0 NULL row)';
END $$;
```

**注意**：V101 結尾 verify **不 ALTER COLUMN SET NOT NULL**（columnstore feature_not_supported）— NOT NULL handling 屬 V102 scope（per V102 spec §3）。

---

## §3 Guard A/B/C 設計

### 3.1 Guard A — trading.fills exist + baseline column 完整

```sql
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    -- trading.fills 必存在 (V003 baseline)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'trading' AND table_name = 'fills'
    ) THEN
        RAISE EXCEPTION
            'V101 Guard A FAIL: trading.fills missing — '
            'V003 trading_agent_tables.sql 必先 apply。Re-check migration order.';
    END IF;

    -- baseline + V015+V077+V083+V094 column 必齊全 (per V094 範式)
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts', 'fill_id', 'order_id', 'symbol', 'side', 'qty', 'price',
        'fee', 'strategy_name', 'context_id', 'engine_mode',
        'entry_context_id', 'exit_reason', 'close_maker_attempt',
        'details'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'trading' AND table_name = 'fills'
          AND column_name = c
    );

    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V101 Guard A FAIL: trading.fills missing baseline columns: %. '
            'Resolve V003/V015/V077/V083/V094 schema drift before V101.', v_missing;
    END IF;
END $$;
```

### 3.2 Guard B — track column type 對齊（如 EXTEND-friendly idempotency）

```sql
DO $$
DECLARE
    v_data_type TEXT;
    v_udt_name TEXT;
    v_is_nullable TEXT;
BEGIN
    SELECT data_type, udt_name, is_nullable
      INTO v_data_type, v_udt_name, v_is_nullable
    FROM information_schema.columns
    WHERE table_schema = 'trading' AND table_name = 'fills'
      AND column_name = 'track';

    IF v_data_type IS NOT NULL THEN
        -- track 已存在 → 驗 type 對齊 (重跑 idempotency safety)
        IF v_data_type IS DISTINCT FROM 'USER-DEFINED'
           OR v_udt_name IS DISTINCT FROM 'strategy_track'
           OR v_is_nullable IS DISTINCT FROM 'YES' THEN
            RAISE EXCEPTION
                'V101 Guard B FAIL: trading.fills.track type drift. '
                'Expected strategy_track ENUM NULL, got type=%, udt=%, nullable=%. '
                'Resolve schema state before V101 re-apply.',
                v_data_type, v_udt_name, v_is_nullable;
        END IF;
    END IF;
END $$;
```

### 3.3 Guard C — track column existence + ENUM 對齊 + backfill 100% verify

```sql
-- Main DDL 完成後再驗一次
DO $$
DECLARE
    v_enum_count INT;
    v_null_count INT;
BEGIN
    -- ENUM 3 值齊全
    SELECT COUNT(*) INTO v_enum_count
    FROM pg_enum
    WHERE enumtypid = 'strategy_track'::regtype;

    IF v_enum_count <> 3 THEN
        RAISE EXCEPTION
            'V101 Guard C FAIL: strategy_track ENUM 應有 3 值, 實際 %. '
            'Expected 3 values: direct_exploit, asds_factory, baseline.', v_enum_count;
    END IF;

    -- column 存在 + nullable
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'trading' AND table_name = 'fills'
          AND column_name = 'track'
          AND udt_name = 'strategy_track'
          AND is_nullable = 'YES'
    ) THEN
        RAISE EXCEPTION
            'V101 Guard C FAIL: trading.fills.track column missing or type drift.';
    END IF;

    -- backfill 100% (0 NULL)
    SELECT COUNT(*) INTO v_null_count
    FROM trading.fills WHERE track IS NULL;

    IF v_null_count > 0 THEN
        RAISE EXCEPTION
            'V101 Guard C FAIL: % rows still have track=NULL after backfill. '
            'Backfill DO block 失敗或 writer race。', v_null_count;
    END IF;
    RAISE NOTICE 'V101 Guard C PASS: 3 enum + track column + 0 NULL row verified';
END $$;
```

---

## §4 Linux PG Dry-run 5 Reflection SQL

per ADR-0011 mandatory + `feedback_v_migration_pg_dry_run.md`。對齊 V100 範式（per `2026-05-23--v100-m4-hypothesis-base-table.md` §6.1）。

### 4.1 Phase B Sandbox dry-run 必驗 5 SQL（Round 1 apply 後）

```bash
# Round 1: psql -d trading_ai_sandbox -f V101__track_v3_attribution_column.sql

# Reflection 1: strategy_track ENUM 存在 + 3 值
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT enumlabel
FROM pg_enum
WHERE enumtypid = 'strategy_track'::regtype
ORDER BY enumsortorder;
\""
# Expected:
#   direct_exploit
#   asds_factory
#   baseline
```

```bash
# Reflection 2: trading.fills.track column 存在 + nullable + ENUM 對齊
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT column_name, data_type, udt_name, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'trading' AND table_name = 'fills' AND column_name = 'track';
\""
# Expected:
#   track | USER-DEFINED | strategy_track | YES | (null)
```

```bash
# Reflection 3: backfill 100% NULL → baseline
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT track::text, COUNT(*) AS row_count
FROM trading.fills
GROUP BY track ORDER BY track;
\""
# Expected:
#   baseline | <total fill count>
#   (0 row with track=NULL)
```

```bash
# Reflection 4: trading.fills row volume (impact assessment)
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT COUNT(*) AS total_rows, MIN(ts) AS earliest, MAX(ts) AS latest
FROM trading.fills;
\""
# Expected: row count 估計 ~100k-1M (live 8 個月累計;PA dispatch 確認)
```

```bash
# Reflection 5: 既有 5 textbook strategy → baseline 對映完整
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -c \"
SELECT strategy_name, track::text, COUNT(*) AS row_count
FROM trading.fills
WHERE strategy_name IN ('grid_trading', 'bb_breakout', 'bb_reversion', 'ma_crossover', 'funding_arb')
GROUP BY strategy_name, track ORDER BY strategy_name;
\""
# Expected: 全 strategy_name → track=baseline; 0 row with track<>baseline
```

### 4.2 Phase B Sandbox dry-run Round 2 idempotency 驗

```bash
# Round 2: psql -d trading_ai_sandbox -f V101 重 apply
# Expected: 0 ERROR + 0 RAISE EXCEPTION + Guard B 自然 PASS (track ENUM 對齊驗) + Guard C 自然 PASS (3 enum + 0 NULL)
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai_sandbox -f /home/ncyu/srv/sql/migrations/V101__track_v3_attribution_column.sql 2>&1 | grep -E 'NOTICE|ERROR'"
# Expected NOTICE:
#   - 'V101: strategy_track ENUM already exists; skipping CREATE TYPE'
#   - 'V101 backfill: 0 rows updated to track=baseline' (already 100% backfilled)
#   - 'V101: trading.fills.track 100% backfilled (0 NULL row)'
#   - 'V101 Guard C PASS: 3 enum + track column + 0 NULL row verified'
# Expected ERROR: 0
```

---

## §5 Round 1+2 Idempotency Proof

### 5.1 Round 1 (first apply) 走完 chain

| Step | 預期行為 |
|---|---|
| 1. CREATE TYPE strategy_track | 0 RAISE → NOTICE 0 + ENUM 建立 |
| 2. Guard A | trading.fills exist + V094 column 全有 → PASS |
| 3. Guard B | track column 不存在 → SELECT 返 NULL → if block skip → PASS |
| 4. ALTER TABLE ADD COLUMN track strategy_track NULL | column 建立 + IF NOT EXISTS guard PASS |
| 5. Backfill DO block | 全 row 更新 track='baseline' + RAISE NOTICE total |
| 6. V101 結尾 verify | 0 NULL row → RAISE NOTICE 100% |
| 7. Guard C | 3 enum + 0 NULL + column 存在 → PASS NOTICE |

### 5.2 Round 2 (re-apply) 走完 chain

| Step | 預期行為 |
|---|---|
| 1. CREATE TYPE | duplicate_object → NOTICE skip |
| 2. Guard A | PASS（同 Round 1）|
| 3. Guard B | track column 存在 → SELECT 返 type + udt + nullable → if NOT DISTINCT block PASS |
| 4. ALTER TABLE ADD COLUMN IF NOT EXISTS | column 已存在 → skip |
| 5. Backfill DO block | WHERE track IS NULL → 0 row 匹配 → exit loop → NOTICE 0 row updated |
| 6. V101 結尾 verify | 0 NULL row → PASS NOTICE |
| 7. Guard C | PASS（同 Round 1）|

**Idempotency 不變式**：Round 1 + Round 2 結果一致；0 destructive side effect；0 row 損失。

### 5.3 Round 1 Sandbox vs Production 對照

per Sprint 1A-ζ Phase 3a 教訓（stub 路徑遺留 partial column）+ V100 production deploy lesson（Guard A FAIL with hypotheses partial column）：

V101 Round 1 production apply 預設 trading.fills schema 全齊全（per V094 land 2026-05-15）+ 0 partial state；Guard A pass。

如出現 Guard B FAIL (`track column type drift`)：人工 schema reconciliation 後重 apply。

---

## §6 4-Phase Deploy Chain

### 6.1 Phase A — Mac IMPL

```
Phase A: Mac IMPL (E1 work)
  ↓
  1. 寫 V101__track_v3_attribution_column.sql (~250 LOC)
  2. cargo test --release -p openclaw_engine --lib database::migrations:: PASS
     (sqlx Migrator parser accept + sort chain V100 → V101 → V103 monotonic)
  3. commit + push (per CLAUDE.md §git: 不 amend / 不 force push;narrow staging)
```

### 6.2 Phase B — Sandbox dry-run (Linux PG empirical mandatory)

```
Phase B: Sandbox dry-run
  ↓
  4. ssh trade-core git pull --ff-only
  5. ssh trade-core psql -d trading_ai_sandbox -f V101 Round 1 (apply + 5 reflection SQL)
  6. ssh trade-core psql -d trading_ai_sandbox -f V101 Round 2 (idempotent re-apply; 0 ERROR/RAISE)
  7. Sandbox V101 → V103 chain reapply (V103 EXTEND Guard A 不依 track column; chain unaffected)
```

### 6.3 Phase C — Production deploy

```
Phase C: Production deploy (PA + E1 + operator)
  ↓
  8. OPENCLAW_AUTO_MIGRATE=0→1 (per V100 production deploy chain;raw psql -f path 屬 alt option)
  9. restart_all.sh (no rebuild;auto-migrate land V101 chain)
  10. expect _sqlx_migrations MAX 100→101 (V100 production confirmed land 2026-05-23)

  Alt path: psql -f raw apply (per `2026-05-22--decision_2_pg_checksum_alignment_runbook.md` Step 3 alt path)
   - 走 metadata register 路徑 (post-apply 手動 INSERT _sqlx_migrations row)
   - 對齊 V100 production deploy 範式
```

### 6.4 Phase D — Verify

```
Phase D: verify (per Sprint 4+ AC-1b 範式)
  ↓
  11. _sqlx_migrations MAX = 101 confirm
  12. 1 target column 物理存在 (trading.fills.track strategy_track NULL)
  13. strategy_track ENUM 3 值 land
  14. backfill 100% (0 NULL row in trading.fills.track)
  15. engine startup 0 panic
  16. 30 min observe + AC-1b SQL 重驗 5 reflection
```

---

## §7 V99 → V100 → V101 → V103 Sequential Apply 對齊

```
V099 (autonomy_level_config)
   ↓
V100 (M4 base: hypotheses + hypothesis_preregistration + earn_movement_log)
   ↓
V101 (Track v3 attribution column EXTEND on trading.fills; 本 spec)
   ↓
V102 (Track v3 indexes + NOT NULL handling; V101 配對)
   ↓
V103 (EXTEND M4 hypothesis 6 column)
   ↓
V106 / V107 / V112 (Sprint 1A-ζ / Sprint 2 chain - already land)
```

**V101 對 V103 EXTEND chain 不依賴**：V103 Guard A 驗 `learning.hypotheses` + `hypothesis_id` PK（V100 land 後 PASS）— 與 trading.fills.track 完全無交集。V101 land 不影響 V103。

**V101 對 V099 autonomy 不依賴**：autonomy_level_config 在 system schema，與 trading 無 FK 或 ENUM 共用。V099 land 順序對 V101 無影響（per V101 Guard A 不檢 system.autonomy_level_config）。

---

## §8 4 Acceptance Criteria

### AC-1: V101 file LAND + sqlx parser accept

- `sql/migrations/V101__track_v3_attribution_column.sql` 存在
- LOC ~250 (對齊 V094 close_maker_audit 229 LOC 範式 + V057 CREATE TYPE ENUM 範式 + V100 663 簡化版)
- `cargo test --release -p openclaw_engine --lib database::migrations::tests::load_migrations_real_srv_tree` PASS
- 全 15 migrations module test PASS（含 parse / eligibility / sort / duplicate detect）

**Status**：🟡 PENDING（Phase A E1 IMPL）

### AC-2: Sandbox Round 1+2 idempotent apply

- Phase B sandbox `psql -d trading_ai_sandbox -f V101` 第一次 apply 全 RAISE NOTICE PASS（0 ERROR）
- 第二次 apply 0 RAISE EXCEPTION + skip 全部已存在 object
- 5 reflection SQL 全綠（ENUM 3 值 / column 存在 + nullable / 0 NULL backfill / row count / strategy_name backfill 對映）

**Status**：🟡 PENDING（Phase B operator + PA 親手執行）

### AC-3: V101 → V103 EXTEND chain Guard A 不互相阻塞

- V101 land 後跑 V103 EXTEND apply
- V103 Guard A 「`learning.hypotheses` table + `hypothesis_id` PK 存在」驗自然 PASS（V100 land 後）
- V103 EXTEND 自身不檢 trading.fills.track（無依賴）
- Sandbox empirical chain verify

**Status**：🟡 PENDING（Phase B sandbox empirical）

### AC-4: Production engine restart + auto-migrate land + Sprint 5+ Writer path 預留

- Phase C `OPENCLAW_AUTO_MIGRATE=1` restart_all.sh
- engine startup 0 panic
- `_sqlx_migrations` 含 V101 row + success=true
- trading.fills.track column 物理存在 + 100% backfilled baseline
- 30 min observe + AC-1b SQL 重驗
- **Sprint 5+ Writer path 預留**：Rust writer (per Sprint 5+ Wave 2 Phase 2) 必補對 track column 顯式填寫；目前 strategy 既有 5 textbook 全寫 'baseline'；Track A/B 上線後 writer 改填 'direct_exploit' / 'asds_factory'

**Status**：🟡 PENDING（Phase C-D operator + PA + E1 + Sprint 5+ Wave 2 dependency）

---

## §9 E2 重點審查 3 點

### 9.1 trading.fills 是 TimescaleDB columnstore hypertable — V101 ADD COLUMN 安全性

**E2 必驗**：
- V101 SQL 使用 `ADD COLUMN IF NOT EXISTS track strategy_track NULL`（nullable 安全）
- 不使用 `SET NOT NULL`（per columnstore feature_not_supported 過去 V077 教訓）
- 對齊 V094 close_maker_audit 同表 ADD COLUMN 範式（`ADD COLUMN IF NOT EXISTS close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE`）— V094 此範式在 columnstore hypertable PASS
- Sandbox dry-run Reflection 2 驗 column 物理建立 + type 對齊

**潛在 catch**：若 sandbox dry-run Round 1 RAISE `feature_not_supported`，則需走 trigger fallback path（per V077 範式）；但本 V101 為 nullable ADD COLUMN（low risk），預期 PASS。

### 9.2 strategy_track ENUM scope + Sprint 5+ Wave 2 Phase 2 carry-over

**E2 必驗**：
- V101 spec scope 嚴守「trading.fills only」— **不**對 trading.intents/signals/orders/decision_outcomes/risk_verdicts/position_snapshots 同時 ADD COLUMN
- 不 CREATE TABLE learning.hypotheses（V100 已 land）
- 不 CREATE TABLE learning.hypothesis_preregistration（V100 已 land）
- 不 CREATE TABLE governance.track_kill_events（Sprint 5+ Wave 3 dispatch）
- 不 CREATE VIEW track_*_daily（Sprint 5+ Wave 2 Phase 2）
- spec §1.1 push back 明文記錄 scope decision + Sprint 5+ Wave 2/3 carry-over

**潛在 drift**：E1 IMPL 自行擴 scope（如「順手加 trading.intents.track」）= 違反 PA dispatch scope；E2 reject。

### 9.3 backfill batched UPDATE + V101 結尾 verify 100% 對齊

**E2 必驗**：
- backfill DO block 用 `LIMIT 10000 + pg_sleep(0.1) + LOOP` 範式（per v3 spec §3.4 large table batch）
- V101 結尾 verify SELECT COUNT(*) WHERE track IS NULL = 0
- 失敗 RAISE EXCEPTION（per fail-closed 原則 6）
- **不**在 V101 內 ALTER COLUMN SET NOT NULL（per columnstore constraint；屬 V102 scope）

**潛在 catch**：若 backfill 中途 writer 寫新 row 但漏填 track（race condition），V101 結尾 verify FAIL；需 V102 BEFORE INSERT trigger 處理（per V102 spec §3）。

---

## §10 spec 範式對齊與 commit log

### 10.1 spec 範式對齊 V094/V100 範式對照表

| Aspect | V094 close_maker_audit | V100 M4 base | **V101 Track v3 (本)** |
|---|---|---|---|
| LOC | 229 | 663 | ~250 |
| Guard A | trading.fills exist + 13 column 完整 | 3 NEW table column 完整 + governance_audit_log | trading.fills exist + 15 baseline column |
| Guard B | 2 column type/CHECK/DEFAULT mismatch | N/A | track column type/udt/nullable 對齊 (idempotency) |
| Guard C 預檢 | N/A | 4 CHECK enum 對齊 | strategy_track ENUM 3 值 + column 存在 + 0 NULL backfill |
| Main DDL | ADD 2 column + 10-value CHECK + partial index | CREATE 3 table + 4 index + 20 COMMENT | CREATE TYPE ENUM + ADD 1 column + batch backfill |
| Backfill | N/A | N/A | batched UPDATE LOOP + 100% verify |
| COMMENT | 0 column | 3 table + 17 column | 1 column (track 詳細語意 + Sprint 5+ Writer path 預留) |
| Guard C 後驗 | CHECK constraint + index | 4 CHECK + 4 index + 2 FK | ENUM 3 值 + column + 0 NULL |
| schema 名 patch | N/A | FK target patch (PA-DRIFT-1) | N/A (純 ADD COLUMN) |

### 10.2 revision history

| date | author | revision |
|---|---|---|
| 2026-05-23 | PA | v1 SPEC-DRAFT — operator scope push back trading.fills only；剝離 v3 spec 12 表 + 2 新表 + view + kill_events 至 Sprint 5+ Wave 2/3 carry-over |

---

**END OF V101 Track v3 Attribution Column EXTEND Migration Spec**

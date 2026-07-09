---
spec: V094 — Close-Maker-First Audit Schema (hybrid: hot column + JSONB extension)
date: 2026-05-15
author: PA agent (Wave 2 Track A2)
phase: EDGE-P2-3 Phase 1b close-maker-first refactor — F-FA-1 IMPL Prereq 5 第 3 子條件
status: SPEC-FINAL（V094 SQL + trading_writer.rs writer upgrade + Linux PG dry-run protocol + healthcheck [62][63][64][65] integration + 配套 IMPL plan）
parent specs:
  - srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md (v1.2 §4.4 + §11.7 + §15)
  - srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md (v0.3 §4.1 + §10.1)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md (Wave 1 Track A4)
mirror precedent: srv/sql/migrations/V083__fills_entry_context_id_close_check.sql
scope: design / spec only — 不寫 V094.sql 實檔，不改 trading_writer.rs 實際代碼，不在 Mac 跑 V094 SQL，不動 V083 schema，不動 paper_state / resting_orders / spine writer
---

# V094 Close-Maker-First Audit Schema — Hybrid Migration Spec

## §0 TL;DR

- **V094 hybrid schema** = 2 new columns on `trading.fills` (hot path) + 3 keys in existing `trading.fills.details` JSONB (audit-only)。
- **Critical writer gap**：`trading_writer.rs:430` INSERT 列表 23 columns 不寫 `details`（empirical 24h 98 fills 0% details present 確認）— V094 IMPL 必同步升 `TradingMsg::Fill` enum + writer 寫 details payload，否則 audit 100% NULL → guard tests 全 FAIL。
- **Spec deliverables**：V094 SQL 設計 + Guard A/B/C templates + Linux PG dry-run protocol（× 2 round）+ sqlx checksum repair SOP + trading_writer.rs upgrade spec（含 13 caller site impact）+ healthcheck [62][63][64][65] integration spec + IMPL plan + Backward-compat + Rollback。
- **F-FA-1 解除條件**：本 spec PM sign-off → AMD §8 IMPL Prereq 5 第 3 子條件 `F-FA-1 V094 spec ✅ DONE`。
- **改動風險評級** = **中**（schema migration + writer hot path + 13 caller sites）；mitigated by Linux PG empirical dry-run × 2 + writer sites enumeration + backward-compat append-only。
- **16 原則合規** 16/16；**DOC-08 §12 安全不變量觸碰** 0/9（strengthens 原則 #8 交易可解釋）；**§四硬邊界觸碰** 0/5。

---

## §1 Background + Scope

### 1.1 動機

EDGE-P2-3 Phase 1b close-maker-first refactor（spec v1.2 + AMD v0.3）要求 close path execution-quality 改造：策略級 close 改走 PostOnly Limit + maker_timeout fallback to taker。為滿足 §二 #8 交易可解釋（每筆交易可重建：為什麼、何時、風控、授權、執行、結果）+ AC-6 close_maker audit 欄位 NULL ladder + healthcheck [62]/[63]/[64]/[65] dual gate，需新增 5 個 audit 欄位：

| 欄位 | 用途 |
|---|---|
| `close_maker_attempt:bool` | 此 close fill 是否嘗試 maker-first（hot-path filter）|
| `close_maker_fallback_reason:text` | maker fail / fallback 真因（hot-path enum filter）|
| `close_initial_limit_price:numeric` | maker 下單時的 limit price（audit-only）|
| `close_final_fill_price:numeric` | 最終成交價（audit-only，與 limit price 對比量化 slippage）|
| `close_maker_eligible_reason:text` | trigger_tag 鏡像（audit-only，反查白名單分類路徑）|

### 1.2 為何 hybrid schema（hot column + JSONB extension）— 性能 + audit completeness 平衡

| 設計選項 | 性能 | Schema bloat | 結論 |
|---|---|---|---|
| 全 5 欄位走 new column | 最快（columnar scan） | **+5 column** 對 trading.fills 既有 23 columns 增 22% schema 寬度；歷史 row default 占空間 | over-optimize for low-cardinality audit-only fields |
| 全 5 欄位走 JSONB | 慢（GIN index 100x slower than partial BTREE per MIT F-MIT-1 verified） | 0 | hot-path query (healthcheck [62]/[63] `GROUP BY close_maker_attempt`) 性能不可接受 |
| **Hybrid（2 column + 3 JSONB）** | 快（hot path filter）+ low cardinality audit JSON-extension | +2 column（既有 23 → 25）+ JSON keys append-only | **採用** |

具體分配：

| 欄位 | 類型 | 載體 | 設計理由 |
|---|---|---|---|
| `close_maker_attempt` | `BOOLEAN NOT NULL DEFAULT FALSE` | **new column on `trading.fills`** | high-frequency group-by query；`partial index WHERE close_maker_attempt = true` 比 JSONB GIN 高效 100x（per MIT F-MIT-1 verified）|
| `close_maker_fallback_reason` | `TEXT NULL` (CHECK enum) | **new column on `trading.fills`** | enum allowlist 約束（CHECK constraint）+ healthcheck [63] NULL ladder 計算需獨立欄位；不適合 JSONB |
| `close_initial_limit_price` | `NUMERIC` | **`trading.fills.details` JSONB key** | 單筆 audit 讀取，無 group-by；JSON-column extension append-only（FA-MF-3 backward-compat） |
| `close_final_fill_price` | `NUMERIC` | **`trading.fills.details` JSONB key** | 同上 |
| `close_maker_eligible_reason` | `TEXT` | **`trading.fills.details` JSONB key** | 鏡像 trigger_tag，僅 audit 讀取 |

### 1.3 對 close-maker-first IMPL prereq 5 解的依賴關係

V094 spec finalize 解 AMD v0.3 §8 IMPL Prereq 5 第 3 子條件：
- ✅ **F-FA-2 DONE Wave 1 Track A3** (`96995b61`) — portfolio_var SoT verify
- ✅ **F-FA-3 DONE Wave 1 Track A4** (`a5a7107c`) — W-C Caveat 2 guard tests
- 🔄 **F-FA-1 (本 spec)** — V094 hybrid schema migration spec finalize

3 子條件全 done → AMD §8 IMPL Prereq 5 解 → 與 Prereq 1/2/3/4/6 並行收口 → IMPL kickoff 派 E1 5-worktree。

### 1.4 不在本 spec 範圍

- ❌ V094.sql 實檔寫作（E1 IMPL 工作）
- ❌ trading_writer.rs 實際代碼改動（E1 IMPL 工作）
- ❌ Mac 跑 V094 SQL（必 Linux PG empirical）
- ❌ V083 schema 改動（mirror 不修改）
- ❌ paper_state / resting_orders / spine writer 任何改動
- ❌ ML training pipeline integration（permanently-banned per MIT-MF-1 + non-training surface invariant）
- ❌ 5 audit 欄位寫入 `agent.decision_objects` spine lineage（W-C Caveat 2 carve-out per F-FA-3 6 grep guard patterns）

---

## §2 Schema Changes

### 2.1 New Columns to `trading.fills`

#### 2.1.1 `close_maker_attempt`

```sql
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE;
```

**語意**：
- `TRUE` = 此 close fill 嘗試 maker-first（PostOnly Limit）路徑，無論最終是 maker fill 或 fallback to taker
- `FALSE` = 此 close fill 走 hard-coded market 路徑（風控 / safety path / negative whitelist），或 entry fill（非 close path）
- 不允許 NULL（NOT NULL DEFAULT FALSE 既保 backward-compat 又防 audit 漏寫）

**Index**：
```sql
CREATE INDEX IF NOT EXISTS idx_fills_close_maker_attempt_v094
    ON trading.fills (engine_mode, ts DESC)
    WHERE close_maker_attempt = TRUE;
```

理由：partial index 縮小體積（只索引嘗試 maker 的 close fills，預估 5-15% rows）；hot-path query `[62] close_maker_fill_rate` 高頻 SELECT WHERE close_maker_attempt = TRUE GROUP BY engine_mode。

#### 2.1.2 `close_maker_fallback_reason`

```sql
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS close_maker_fallback_reason TEXT NULL;
```

**語意**：
- close_maker_attempt = FALSE → 必 NULL（無 maker 嘗試 = 無 fallback reason）
- close_maker_attempt = TRUE → 必 ∈ enum 8 + NULL（NULL = maker fill success，無 fallback；其餘 8 值 = fallback / safety path 真因）

**enum allowlist (CHECK constraint NOT VALID)**：
```sql
ALTER TABLE trading.fills
    ADD CONSTRAINT chk_fills_close_maker_fallback_reason_v094
    CHECK (
        close_maker_fallback_reason IS NULL
        OR close_maker_fallback_reason IN (
            'timeout_taker',                    -- maker timeout fallback to market (5.5 spec §5.5 Race A)
            'postonly_reject',                  -- EC_PostOnlyWillTakeLiquidity reject
            'cancel_grace_expired',             -- 2s cancel ack grace 過期
            'ack_lost',                         -- IPC ack 遺失，best-effort fallback
            'rate_limit_pause_global',          -- TooManyPending → conditional global 5min pause（spec §5.5 BB-MF-2）
            'rate_limit_backoff_per_symbol',    -- per-symbol exp backoff 1s→60s（spec §5.5 BB-MF-2）
            'fast_escalate_safety_upgrade',     -- Race A: pending close + 新 risk trigger upgrade
            'not_attempted_safety_path',        -- 走 market 真風控（Negative whitelist；safety path enum）
            'engine_shutdown_safety',           -- cancel_token / authorization 失效（safety path enum）
            'fallback_to_taker_mandatory'       -- spec §5.5 Race E mandatory fallback policy land
        )
    ) NOT VALID;
```

**NOT VALID 理由**：
- mirror V083 precedent：不掃 historical row（pre-V094 fills 全部 close_maker_attempt = FALSE → 全 NULL → 自然 PASS constraint）
- 只對新 INSERT 生效；M2 觀察期 14d 後 PASS 可 ALTER ... VALIDATE CONSTRAINT 強化
- 避免 V094 apply 時 lock trading.fills 全表掃描（1d chunk_time_interval × 數十 chunks → 數秒 lock）

**enum 完整性 vs spec/AMD 對照**：

| enum 值 | spec/AMD 來源 | 是否 safety path |
|---|---|---|
| `timeout_taker` | spec §5.5 Race A | NO |
| `postonly_reject` | spec §5.5 Race B + AMD §4.1 | NO |
| `cancel_grace_expired` | spec §5.5 Race C + AMD §4.1 | NO |
| `ack_lost` | spec §5.5 Race D + AMD §4.1 | NO |
| `rate_limit_pause_global` | AMD §5.4 BB-MF-2 conditional global | NO |
| `rate_limit_backoff_per_symbol` | AMD §5.4 BB-MF-2 per-symbol | NO |
| `fast_escalate_safety_upgrade` | AMD §4.1 Race A escalation | YES (safety) |
| `not_attempted_safety_path` | AMD §4.1 negative whitelist | YES (safety) |
| `engine_shutdown_safety` | AMD §4.1 cancel_token/auth | YES (safety) |
| `fallback_to_taker_mandatory` | spec §5.5 Race E AC-18 (≥95% over 7d) | NO |

> **Safety path 三 enum (`fast_escalate_safety_upgrade` / `not_attempted_safety_path` / `engine_shutdown_safety`) 重要**：healthcheck [63] NULL ladder 必須 **exclude** 這三個值而非算進 NULL 比例（per Consensus-MF-3 + AC-6 + AC-16）。spec/AMD 原 enum 缺 `rate_limit_backoff_per_symbol` 細分 + `fallback_to_taker_mandatory` Race E 新增，本 spec V094 enum 是上 superset（10 值），覆蓋 AMD enum (8 值) + spec §5.5 額外 2 值。**E1 IMPL 不可縮減**。

### 2.2 JSONB Extensions to `trading.fills.details`

`trading.fills.details JSONB` 已存在於 V003 line 284（empirical re-verified Linux PG 2026-05-15）。V094 不需 ALTER details column，僅約定 IMPL 期 writer 寫入時的 JSON key contract：

```json
{
  "close_initial_limit_price": 1234.56,    // f64 numeric, optional, only set when close_maker_attempt=true
  "close_final_fill_price": 1234.50,       // f64 numeric, optional, only set when close fill confirmed
  "close_maker_eligible_reason": "grid_close_short"   // TEXT, optional, mirrors trigger_tag suffix
}
```

**JSON key contract**：
- 3 個 keys 全 optional（per backward-compat append-only）
- only `close_maker_attempt = TRUE` 的 close fill 才寫 3 個 keys（writer-side conditional）
- key 命名 prefix `close_*`（避免與 V003 既有 `contaminated`/`contamination_reason` keys 撞名）
- 不破現有 V083 / pre-V083 details usage（既有 details usage 為「fa_phantom_1 contamination tagging」per Linux PG empirical 5 歷史 sample 確認）

### 2.3 為什麼不破 V003 details usage（Backward-Compat append-only）

| 既有 details usage | 是否被 V094 影響 | 證據 |
|---|---|---|
| `{"contaminated": true, "contamination_reason": "fa_phantom_1"}` | NO | V094 只追加 `close_*` prefix keys；既有 keys 0 衝突；JSON key namespace 互斥 |
| 24h 0% details present rate（writer gap） | YES（被本 spec 修） | V094 IMPL 同步升 writer 寫 details payload；既有 NULL details rows 在 V094 apply 後仍 NULL（DEFAULT NULL，不 backfill） |
| 其他模組讀 details JSONB | 0 caller 讀 close_*（grep verify） | V094 keys 全為新增 contract；無下游期望 |

---

## §3 Guard A/B/C Templates（per CLAUDE.md §七 + V083 mirror）

V094 必含 **3 Guard blocks**（Guard A 驗 column 添加成功 / Guard B 驗 column 型別正確 / Guard C 驗 enum CHECK constraint 真存在 + INDEX 對齊）。

### 3.1 Guard A — table existence + required columns 驗證

```sql
-- ============================================================
-- Guard A: trading.fills must exist with V003/V017/V083 baseline columns
-- Guard A：trading.fills 必須存在且 V003/V017/V083 baseline 欄位俱在
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='trading' AND table_name='fills'
    ) THEN
        RAISE EXCEPTION
            'V094 Guard A FAIL: trading.fills missing — '
            'V003 must have applied first. Re-check migration order.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'ts', 'fill_id', 'symbol', 'side', 'strategy_name',
        'context_id', 'entry_context_id', 'engine_mode', 'exit_reason',
        'details'  -- V003 line 284 details JSONB (V094 IMPL 升 writer 必依賴)
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='trading' AND table_name='fills'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V094 Guard A FAIL: trading.fills missing required columns: %. '
            'Resolve V003/V017/V033/V083 schema drift before applying V094.',
            v_missing;
    END IF;
END $$;
```

### 3.2 Guard B — V094 new columns 型別正確（idempotent re-run check）

```sql
-- ============================================================
-- Guard B: V094 new columns 型別必須對齊 spec
-- Guard B: V094 new column types must match spec
-- 對齊：close_maker_attempt BOOLEAN / close_maker_fallback_reason TEXT
-- 重跑 V094 時 idempotent 檢查；shape 正確不 RAISE，drift 才 RAISE
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- close_maker_attempt 若已存在，必須 boolean
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='trading' AND table_name='fills'
      AND column_name='close_maker_attempt';
    IF v_actual IS NOT NULL AND v_actual IS DISTINCT FROM 'boolean' THEN
        RAISE EXCEPTION
            'V094 Guard B FAIL: trading.fills.close_maker_attempt type drift. '
            'Expected boolean, got %.',
            v_actual;
    END IF;

    -- close_maker_fallback_reason 若已存在，必須 text
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='trading' AND table_name='fills'
      AND column_name='close_maker_fallback_reason';
    IF v_actual IS NOT NULL AND v_actual IS DISTINCT FROM 'text' THEN
        RAISE EXCEPTION
            'V094 Guard B FAIL: trading.fills.close_maker_fallback_reason type drift. '
            'Expected text, got %.',
            v_actual;
    END IF;
END $$;
```

### 3.3 Guard C — enum CHECK constraint + partial index 對齊

```sql
-- ============================================================
-- Guard C: V094 CHECK constraint + partial index 必須與預期對齊
-- Guard C: V094 CHECK constraint + partial index must match expectation
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- CHECK constraint 若已存在，必須 enum 10 值齊全（substring match）
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='trading.fills'::regclass
      AND conname='chk_fills_close_maker_fallback_reason_v094';
    IF v_actual IS NOT NULL THEN
        IF position('timeout_taker' IN v_actual) = 0
           OR position('postonly_reject' IN v_actual) = 0
           OR position('cancel_grace_expired' IN v_actual) = 0
           OR position('ack_lost' IN v_actual) = 0
           OR position('rate_limit_pause_global' IN v_actual) = 0
           OR position('rate_limit_backoff_per_symbol' IN v_actual) = 0
           OR position('fast_escalate_safety_upgrade' IN v_actual) = 0
           OR position('not_attempted_safety_path' IN v_actual) = 0
           OR position('engine_shutdown_safety' IN v_actual) = 0
           OR position('fallback_to_taker_mandatory' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V094 Guard C FAIL: chk_fills_close_maker_fallback_reason_v094 enum mismatch. '
                'Actual: %. Expected to contain all 10 enum values.',
                v_actual;
        END IF;
    END IF;

    -- partial index 若已存在，必須 partial WHERE close_maker_attempt = TRUE
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname='trading'
      AND c.relname='idx_fills_close_maker_attempt_v094';
    IF v_actual IS NOT NULL THEN
        IF position('engine_mode' IN v_actual) = 0
           OR position('close_maker_attempt' IN v_actual) = 0
           OR position('true' IN lower(v_actual)) = 0
        THEN
            RAISE EXCEPTION
                'V094 Guard C FAIL: idx_fills_close_maker_attempt_v094 column list mismatch. '
                'Actual: %. Expected to contain (engine_mode, ts DESC) WHERE close_maker_attempt = TRUE.',
                v_actual;
        END IF;
    END IF;
END $$;
```

### 3.4 Guard 設計理念（per V083 mirror）

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件（idempotent）|
|---|---|---|---|
| A | trading.fills 不存在 / V003-V083 baseline 欄位缺 | RAISE | 全欄位俱在 |
| B | V094 column 已存在但型別錯 | RAISE | column 不存在（首次跑）/ column 存在且型別正確（重跑）|
| C | CHECK constraint 缺 enum 值 / index 缺欄位 | RAISE | constraint 不存在（首次跑）/ constraint 完整（重跑）|

**重跑 V094 第二次必不 RAISE**（idempotent verification per CLAUDE.md §七 V055/V083/V084 incident precedent）。

---

## §4 Linux PG Dry-Run Protocol（mandatory）

per CLAUDE.md §七 + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident precedent，V094 涉及 PG reflection（`information_schema.columns` for Guard B + `pg_get_indexdef` + `pg_get_constraintdef` for Guard C）+ enum CHECK constraint runtime semantic + partial index 行為，**必先 Linux PG empirical 驗證**，禁 Mac mock pytest 代替。

### 4.1 Round 1 — 真實 schema runtime semantic empirical 驗證

**目標**：在 Linux trade-core empirical 驗 V094 SQL 真實 PG 行為對齊 spec。

```bash
# ssh trade-core 執行（不在 Mac 跑）
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V094__fills_close_maker_audit.sql
"
```

**Round 1 必驗 6 項**（empirical SELECT verify after V094 apply）：

```sql
-- 1. 確認 close_maker_attempt 欄位存在 + boolean + NOT NULL DEFAULT FALSE
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='trading' AND table_name='fills'
  AND column_name='close_maker_attempt';
-- Expected: 1 row, data_type=boolean, is_nullable=NO, column_default=false

-- 2. 確認 close_maker_fallback_reason 欄位存在 + text + NULL
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema='trading' AND table_name='fills'
  AND column_name='close_maker_fallback_reason';
-- Expected: 1 row, data_type=text, is_nullable=YES, column_default=NULL

-- 3. 確認 enum CHECK constraint NOT VALID 模式 attached
SELECT conname, pg_get_constraintdef(oid), convalidated
FROM pg_constraint
WHERE conrelid='trading.fills'::regclass
  AND conname='chk_fills_close_maker_fallback_reason_v094';
-- Expected: 1 row, convalidated=false (NOT VALID), pg_get_constraintdef 含 10 enum 值

-- 4. 確認 partial index 已建立
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname='trading' AND indexname='idx_fills_close_maker_attempt_v094';
-- Expected: 1 row 含 WHERE (close_maker_attempt = true)

-- 5. enum CHECK 真 reject 非 enum 值（empirical INSERT test）
INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, engine_mode,
                            close_maker_attempt, close_maker_fallback_reason)
VALUES (NOW(), 'V094_TEST_REJECT', 'TEST_ORDER', 'BTCUSDT', 'Buy', 0.001, 100000, 'paper',
        true, 'INVALID_ENUM_VALUE');
-- Expected: ERROR: new row for relation "fills" violates check constraint
--           "chk_fills_close_maker_fallback_reason_v094"
ROLLBACK;

-- 6. enum CHECK 真允許 enum 值（empirical INSERT test）
INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, engine_mode,
                            close_maker_attempt, close_maker_fallback_reason)
VALUES (NOW(), 'V094_TEST_ACCEPT', 'TEST_ORDER', 'BTCUSDT', 'Buy', 0.001, 100000, 'paper',
        true, 'timeout_taker');
-- Expected: INSERT 0 1 (success)
ROLLBACK;
```

### 4.2 Round 2 — Idempotency 驗證

**目標**：重跑 V094.sql 第二次，必不 RAISE / 必不重複建 index / 必不 fail（per CLAUDE.md §七 idempotency mandatory）。

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V094__fills_close_maker_audit.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS;
# 0 RAISE EXCEPTION; 0 schema drift；0 row count change
```

**Round 2 後驗證**：

```sql
-- 確認 V094 不 double-add column / double-create index / double-add constraint
SELECT COUNT(*) FROM information_schema.columns
WHERE table_schema='trading' AND table_name='fills'
  AND column_name IN ('close_maker_attempt', 'close_maker_fallback_reason');
-- Expected: 2 (each column once)

SELECT COUNT(*) FROM pg_indexes
WHERE schemaname='trading' AND indexname='idx_fills_close_maker_attempt_v094';
-- Expected: 1

SELECT COUNT(*) FROM pg_constraint
WHERE conrelid='trading.fills'::regclass
  AND conname='chk_fills_close_maker_fallback_reason_v094';
-- Expected: 1
```

### 4.3 為何 Mac mock pytest 不夠（V055 5-round loop 教訓）

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift`：
- Mac mock pytest 無法捕捉 PG runtime 真實 PL/pgSQL DO block semantic
- Mac static parse review 無法驗證 `pg_get_constraintdef` 真實輸出對齊 spec
- Mac 無法驗證 enum CHECK constraint 真 reject INVALID 值
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**（per AMD §4.1 IMPL prereq）。

### 4.4 Linux runtime drift caveat（重要）

**Empirical fact (2026-05-15)**：
- Mac source files：V091/V092/V093 已存在於 git
- Linux runtime applied max：V90（per `_sqlx_migrations` table empirical query）
- V81 漏（empirical applied 列表 80→82 跳，91/92/93 source 未 apply）

**對 V094 IMPL 影響**：
- V094 deploy 時，sqlx migrate 會先按 numeric order apply V81/V91/V92/V93，再 V094
- 若 V81/V91/V92/V93 在 deploy 期 fail（schema drift / sqlx checksum mismatch）→ V094 不會 apply
- E1 IMPL kickoff 前必先驗證 V81/V91/V92/V93 在 Linux runtime 應用無 issue（直接 ssh trade-core 跑各 file 確認 apply success）

**Mitigation**：
- E1 IMPL 派工前 PA 補一輪 Linux V81/V91/V92/V93 dry-run 檢查（per CLAUDE.md §七 backlog migration application discipline）
- 或 PM 接受「V094 deploy 時 V81/V91/V92/V93 連帶 apply」accepted risk 並在 IMPL kickoff 加 1d buffer

**spec/AMD wording drift**：spec v1.2 §4.4 + AMD v0.3 §4.1 寫「current max applied V093」是 incorrect（事實 V90）。此 spec §4.4 caveat 段是 source-of-truth 修正；spec/AMD 文字無需 patch（V094 仍 next-free numeric slot；deploy semantic 不變）。

---

## §5 sqlx Checksum Repair SOP

per memory `project_2026_05_02_p0_sqlx_hash_drift`（commit `3681f83`），V094 file edit 後 DB checksum 必同步，否則 engine restart 觸發 sqlx migrate runtime panic。

### 5.1 V094 file 寫作後（IMPL 階段）

```bash
# E1 IMPL：寫 V094.sql 完成後立即跑 Linux dry-run（per §4.1）
# 若 V094.sql 落地後又被 edit（typo fix / comment 補）→ DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 94
"
# Expected: V094 checksum updated in _sqlx_migrations table to match new file SHA
```

### 5.2 Engine restart 後驗證 sqlx migrate 不 panic

```bash
# 1. 部署 V094 到 Linux 後（E1 IMPL kickoff 後 deploy 期）
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

# 2. engine.log 不出現 sqlx migrate panic
ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic'"
# Expected: 0 panic; "Applied migrations" 正常 log

# 3. _sqlx_migrations 表 V094 row success=t
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=94;'"
# Expected: 1 row, success=t, description 含 'close maker audit'
```

### 5.3 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` 教訓：cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §6 trading_writer.rs Upgrade Spec

### 6.1 Critical fix — INSERT 漏接 details payload

**Empirical 證據（PA 2026-05-15）**：
- `srv/rust/openclaw_engine/src/database/trading_writer.rs:430` INSERT INTO trading.fills 列表 23 columns（per `FILL_COLS = 23`），**不含 `details` JSONB column**
- Linux PG 24h empirical：98 fills / 0% details present（writer gap 確認）
- 歷史 details rows（5 sample）全為 manual UPDATE 寫入的 `fa_phantom_1 contamination tagging`，非 writer INSERT 寫入

**修復目標**：
1. 加 `details` 到 INSERT column list（FILL_COLS 23 → 24）
2. 升 `TradingMsg::Fill` enum 加 `details: Option<serde_json::Value>` 欄位
3. close maker path 在 `apply_confirmed_fill` / `compute_close_limit_price` 構造 details payload 含 3 個 JSONB audit keys：
   ```rust
   serde_json::json!({
       "close_initial_limit_price": initial_limit_price,
       "close_final_fill_price": final_fill_price,
       "close_maker_eligible_reason": eligible_reason  // mirror trigger_tag
   })
   ```
4. 若 close fill non-maker path（safety / negative whitelist）→ details = None（既有行為，0 改動）
5. 若 entry fill → details = None（既有行為，0 改動）

### 6.2 trading_writer.rs INSERT 列表升級

**Before (line 430)**:
```rust
let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
    "INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, fee, fee_rate, reference_price, reference_ts_ms, reference_source, slippage_bps, liquidity_role, fill_latency_ms, realized_pnl, is_paper, strategy_name, context_id, entry_context_id, engine_mode, exit_source, exit_reason) "
);
```

**After**:
```rust
let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
    "INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, fee, fee_rate, reference_price, reference_ts_ms, reference_source, slippage_bps, liquidity_role, fill_latency_ms, realized_pnl, is_paper, strategy_name, context_id, entry_context_id, engine_mode, exit_source, exit_reason, details, close_maker_attempt, close_maker_fallback_reason) "
);
```

**FILL_COLS update**:
```rust
const FILL_COLS: usize = 26; // V094 adds details JSONB + close_maker_attempt + close_maker_fallback_reason
```

**push_values 區塊新增**:
```rust
// V094 (2026-05-15): details JSONB writer-side fix + close_maker audit columns
b.push_bind(details.as_ref());  // Option<&serde_json::Value> → JSONB or NULL
b.push_bind(*close_maker_attempt);  // bool → boolean
b.push_bind(close_maker_fallback_reason.as_deref());  // Option<&str> → text or NULL
```

### 6.3 TradingMsg::Fill enum upgrade

**File**：`srv/rust/openclaw_engine/src/database/mod.rs:281-376`

**Before**：21 fields（fill_id / ts_ms / order_id / symbol / side / qty / price / fee / fee_rate / reference_price / reference_ts_ms / reference_source / slippage_bps / liquidity_role / fill_latency_ms / realized_pnl / strategy_name / context_id / entry_context_id / engine_mode / exit_source / exit_reason）

**After**：24 fields（+3 new）：
```rust
pub enum TradingMsg {
    Fill {
        // ... 既有 21 fields ...

        // V094 (2026-05-15): close-maker-first audit fields
        /// V094: close-maker audit JSON payload. None = entry fill / non-maker close.
        /// Some = close-maker-first attempted close fill (writer 寫入 trading.fills.details).
        /// V094：close-maker 路徑 audit JSON payload；None = entry fill 或 non-maker close。
        details: Option<serde_json::Value>,

        /// V094: TRUE = close fill 嘗試 maker-first；FALSE = entry / market close (default).
        /// V094：TRUE = close 嘗試 maker-first；FALSE = entry / market close（既有行為）。
        close_maker_attempt: bool,

        /// V094: maker fallback / safety path reason. NULL when maker fill success
        /// or entry fill. Constrained to enum allowlist by V094 CHECK constraint.
        /// V094：maker fallback 真因 / safety path tag；maker 成交或 entry fill 時 NULL；
        /// 受 V094 CHECK constraint enum 約束。
        close_maker_fallback_reason: Option<String>,
    },
    // ... 其他 variant 不動 ...
}
```

### 6.4 13 caller sites impact analysis

**Production callers（6 sites）— 必修**：

| Path | Line | Context |
|---|---|---|
| `event_consumer/unattributed_emit.rs` | 168 | unattributed audit fill emit |
| `tick_pipeline/pipeline_helpers.rs` | 232 | helper fill emit |
| `tick_pipeline/on_tick/step_4_5_dispatch.rs` | 1179 | dispatch step fill emit |
| `tick_pipeline/on_tick/step_4_5_dispatch.rs` | 1462 | dispatch step fill emit |
| `tick_pipeline/commands.rs` | 301 | open close cmd path fill emit |
| `tick_pipeline/commands.rs` | 618 | open close cmd path fill emit |

**Test callers（7 sites）— 必修（避免 cargo test 編譯錯）**：

| Path | Line |
|---|---|
| `database/trading_writer.rs` | 979, 1113, 1241, 1274 |
| `event_consumer/tests/pending_registration_order_type_tests.rs` | 397 |
| `event_consumer/tests/unattributed_fill_tests.rs` | 106 |

**升級 pattern (per site)**：
```rust
// Before:
TradingMsg::Fill {
    fill_id: ...,
    // ... 21 既有 fields ...
    exit_reason: ...,
}

// After:
TradingMsg::Fill {
    fill_id: ...,
    // ... 21 既有 fields ...
    exit_reason: ...,
    // V094: close-maker audit fields
    details: None,                           // entry fill / non-maker close = None
    close_maker_attempt: false,              // entry fill / market close = false
    close_maker_fallback_reason: None,       // 同上
}
```

### 6.5 Close-maker-first IMPL 階段的 details 寫入路徑

**僅 close maker path（spec §4.4 commands.rs 改造後）寫入 details + close_maker_attempt=true**：

```rust
// commands.rs:778-816 改造後（per spec §4.1）
let close_maker_attempt = self.is_close_maker_eligible(trigger_tag, &self.use_maker_close_cfg);
let (order_type, limit_price, time_in_force, maker_timeout_ms) = if close_maker_attempt {
    // ... maker path 設置 limit_price 等 ...
    (..., Some(limit_price), Some("PostOnly"), Some(timeout_ms))
} else {
    ("market", None, None, None)
};

// 於 apply_confirmed_fill / build_fill_msg 構造 TradingMsg::Fill：
let (details, fallback_reason) = if close_maker_attempt {
    let payload = serde_json::json!({
        "close_initial_limit_price": initial_limit_price,
        "close_final_fill_price": confirmed_fill_price,
        "close_maker_eligible_reason": trigger_tag.split(':').nth(1).unwrap_or(""),
    });
    let reason = if was_maker_filled {
        None  // maker 成功成交，無 fallback reason
    } else {
        Some(classify_fallback_reason(fallback_event))  // 從 enum 10 值選一
    };
    (Some(payload), reason)
} else {
    (None, None)  // safety / negative whitelist / entry fill
};

let msg = TradingMsg::Fill {
    // ... 既有 21 fields ...
    details,
    close_maker_attempt,
    close_maker_fallback_reason: fallback_reason,
};
```

### 6.6 對 SLA 影響估算（per CLAUDE.md SLA <1ms H0 / <0.3ms tick / <5ms IPC）

| 操作 | Before | After | Δ |
|---|---|---|---|
| TradingMsg::Fill 構造 | 21 fields | 24 fields | +3 fields ~80 ns |
| serde_json::json!() macro（close maker path only） | N/A | 3 keys | ~500 ns（only when close_maker_attempt=true） |
| INSERT 列表 push_bind | 23 columns | 26 columns | +120 ns |
| sqlx batch INSERT (1 fill) | ~2 ms | ~2.05 ms | +50 μs |

**結論**：對 SLA 0 風險（tick 主路徑 <0.3ms 不被觸碰；DB INSERT 不在 hot tick path；trading_writer.rs 是異步 batch flush 設計）。

### 6.7 Cross-language IPC contract（PyO3 / Python）

per CLAUDE.md §九 PYO3-ELIMINATE-1 後：
- Python 側無 PyO3 等價 TradingMsg::Fill 結構（writer 是 Rust-only）
- Python 讀 `trading.fills.details` 走 SQL JSONB query，無 schema 對等需求
- 0 Python writer 對等需要同步升

---

## §7 Healthcheck [62] [63] [64] [65] Integration

per spec §8.1 + AMD §4.1 配套 healthcheck，V094 IMPL 後新增 4 healthcheck（healthcheck 計數 51 → 55；註冊在 `helper_scripts/db/passive_wait_healthcheck/runner.py`）。

### 7.1 [62] close_maker_fill_rate（per Consensus-MF-2 + AC-1 Wilson-CI gate）

**檔位置**：`helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py`（新檔）

**Spec**：
```python
def check_close_maker_fill_rate(conn) -> dict:
    """[62] close_maker_fill_rate — Wilson 95% CI gate
    
    Query (24h, env-stratified):
        WITH attempt AS (
            SELECT engine_mode, COUNT(*) AS total
            FROM trading.fills
            WHERE close_maker_attempt = TRUE
              AND ts > NOW() - INTERVAL '24 hours'
            GROUP BY engine_mode
        ),
        filled AS (
            SELECT engine_mode, COUNT(*) AS maker_filled
            FROM trading.fills
            WHERE close_maker_attempt = TRUE
              AND close_maker_fallback_reason IS NULL  -- maker 成功 (per §2.1.2)
              AND ts > NOW() - INTERVAL '24 hours'
            GROUP BY engine_mode
        )
        SELECT a.engine_mode, a.total, COALESCE(f.maker_filled, 0) AS maker_filled
        FROM attempt a
        LEFT JOIN filled f USING (engine_mode)
    
    Wilson CI 95% lower bound vs 60% threshold:
        - PASS: lower_bound >= 0.65 (WARN @ 65% per QC-SF-3 safety margin)
        - WARN: 0.60 <= lower_bound < 0.65
        - FAIL: lower_bound < 0.60 (per AC-1)
        - NEUTRAL: total < 30 (sample size gate per AC-14 Wilson n<30)
    """
```

### 7.2 [63] close_maker_audit_lineage_integrity（per F-FA-3 dual gate）

per Wave 1 Track A4 PA report `2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md` §5：

**Spec**：
```python
def check_close_maker_audit_lineage_integrity(conn) -> dict:
    """[63] close_maker_audit_lineage_integrity — dual gate (W-C + audit completeness)
    
    Gate A (W-C Caveat 2 不變式 — close path 0 spine row):
        SELECT COUNT(*) FROM agent.decision_objects
        WHERE object_type IN ('execution_plan', 'execution_report')
          AND payload::jsonb @> '{"is_close": true}'
          AND created_at > NOW() - INTERVAL '24 hours'
        → spine_close_row_count
    
    Gate B (V094 audit completeness):
        WITH close_maker_fills AS (
            SELECT fill_id, ts, details, close_maker_attempt, close_maker_fallback_reason
            FROM trading.fills
            WHERE close_maker_attempt = TRUE
              AND ts > NOW() - INTERVAL '24 hours'
        )
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE 
                details ? 'close_initial_limit_price' AND
                details ? 'close_final_fill_price' AND
                details ? 'close_maker_eligible_reason'
            ) AS jsonb_complete,
            COUNT(*) FILTER (WHERE
                close_maker_fallback_reason IS NULL OR
                close_maker_fallback_reason NOT IN (
                    'fast_escalate_safety_upgrade',
                    'not_attempted_safety_path',
                    'engine_shutdown_safety'
                )
            ) AS not_safety_path_total,
            COUNT(*) FILTER (WHERE
                close_maker_fallback_reason IS NULL AND
                NOT (details ? 'close_initial_limit_price')
            ) AS audit_missing  -- maker 成功但缺 audit JSON
    
    PASS:
        - Gate A: spine_close_row_count = 0
        - Gate B: jsonb_complete / not_safety_path_total >= 0.999 (per AC-6 NULL ladder PASS ≤ 0.1%)
    
    WARN:
        - Gate A: 1 <= spine_close_row_count <= 5 (race condition tolerance)
        - Gate B: 0.99 <= ratio < 0.999 (per AC-6 NULL ladder WARN 0.1-1.0%)
    
    FAIL:
        - Gate A: spine_close_row_count > 5 (W-C invariant 破)
        - Gate B: ratio < 0.99 (per AC-6 NULL ladder FAIL > 1.0%)
    
    NEUTRAL:
        - close_maker fills 24h < 5 (sample size gate)
    
    safety path enum exclusion:
        - 'fast_escalate_safety_upgrade' / 'not_attempted_safety_path' / 'engine_shutdown_safety'
          不算 NULL（per Consensus-MF-3 + AC-6 + AC-16）
    """
```

### 7.3 [64] close_maker_rate_limit_pause_duration（per BB-SF-1 + spec §5.5 BB-MF-2）

**Spec**：
```python
def check_close_maker_rate_limit_pause_duration(conn) -> dict:
    """[64] close_maker_rate_limit_pause_duration — rate limit observability
    
    Query (24h, count rate_limit fallback events):
        SELECT
            COUNT(*) FILTER (WHERE close_maker_fallback_reason='rate_limit_pause_global') AS global_pause_count,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason='rate_limit_backoff_per_symbol') AS per_symbol_backoff_count
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND ts > NOW() - INTERVAL '24 hours'
    
    PASS:
        - global_pause_count = 0 (no global 5min pause triggered)
        - per_symbol_backoff_count <= 100/24h (per-symbol backoff is normal)
    
    WARN:
        - 1 <= global_pause_count <= 5 (occasional global pause acceptable)
        - 100 < per_symbol_backoff_count <= 500
    
    FAIL:
        - global_pause_count > 5 (rate limit 全域反復觸發 = Bybit 配額破壞)
        - per_symbol_backoff_count > 500
    """
```

### 7.4 [65] close_maker_reject_sample_completeness（per BB-MF-5 + AC-15）

**Spec**：
```python
def check_close_maker_reject_sample_completeness(conn) -> dict:
    """[65] close_maker_reject_sample_completeness — reject category coverage
    
    Per AC-15 (BB-MF-5)：每 env 7d 至少 ≥ 1 sample per
    EC_PostOnlyWillTakeLiquidity / EC_ReachMaxPendingOrders reject category；
    0 樣本 → upgrade Phase 2b 前必跑 mainnet probe 驗 demo endpoint silent
    degradation 不存在。
    
    Query (7d, env-stratified):
        SELECT
            engine_mode,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason='postonly_reject') AS postonly_reject,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason='rate_limit_pause_global') AS rate_limit_global,
            COUNT(*) FILTER (WHERE close_maker_fallback_reason='rate_limit_backoff_per_symbol') AS rate_limit_per_symbol
        FROM trading.fills
        WHERE close_maker_attempt = TRUE
          AND ts > NOW() - INTERVAL '7 days'
        GROUP BY engine_mode
    
    PASS:
        - per env 各 reject category sample >= 1 over 7d (per AC-15)
    
    WARN:
        - per env 某 reject category sample = 0 over 7d, but Phase 2a only
          (允許 demo silent endpoint degradation 等 mainnet probe 驗證)
    
    FAIL:
        - Phase 2b upgrade 前某 reject category sample = 0 (mainnet probe 必跑)
    
    NEUTRAL:
        - 7d close_maker fills total < 30 per env (sample size gate per AC-14 Wilson n<30)
    """
```

### 7.5 healthcheck runner 註冊

per CLAUDE.md §七，新 healthcheck 必註冊在 `helper_scripts/db/passive_wait_healthcheck/runner.py`：

```python
# IMPL prereq 解開後，E1 在 runner.py 加：
from . import checks_close_maker_audit

CHECKS = [
    # ... 51 既有 checks ...
    ("[62] close_maker_fill_rate", checks_close_maker_audit.check_close_maker_fill_rate),
    ("[63] close_maker_audit_lineage_integrity", checks_close_maker_audit.check_close_maker_audit_lineage_integrity),
    ("[64] close_maker_rate_limit_pause_duration", checks_close_maker_audit.check_close_maker_rate_limit_pause_duration),
    ("[65] close_maker_reject_sample_completeness", checks_close_maker_audit.check_close_maker_reject_sample_completeness),
]
```

CLAUDE.md §七 healthcheck 計數同步更新：51 → **55**。

---

## §8 IMPL Plan + 估工時

### 8.1 E1 工作鏈

```
PA V094 spec (本 spec PM sign-off)
  ↓
E1 IMPL (並行 2 worktree + 1 串行)：
  ├─ Worktree A: 寫 V094.sql 含 Guard A/B/C + enum CHECK + partial index + idempotency
  │  (~80 LOC SQL, 1 E1-day，含 Linux PG dry-run × 2 round)
  └─ Worktree B: 改 trading_writer.rs INSERT + TradingMsg::Fill enum + 13 caller sites
     (~30 LOC writer + ~30 LOC enum + ~15 LOC × 13 callers ≈ 235 LOC, 1.5 E1-day)
  ↓
E1 串行 Worktree C: 寫 [62][63][64][65] 4 healthcheck Python (per §7)
  (~50 LOC × 4 + runner.py 註冊 ≈ 220 LOC, 0.5 E1-day)
  ↓
E2 review (≥30min, 重點查 §8.3 三高風險點)
  ↓
E4 regression (cargo test --release + Linux pytest healthcheck × 4)
  ↓
ssh trade-core 跑 V094.sql Linux PG dry-run × 2 round
  ↓
restart_all --rebuild deploy V094 + writer + healthcheck
  ↓
engine restart verify sqlx migrate runtime PASS + healthcheck [62][63][64][65] PASS
  ↓
QA cycle (per Phase 2a Demo 14d 觀察期)
  ↓
PM sign-off
```

### 8.2 估 LOC 細化

| 項目 | LOC | 估 E1-time |
|---|---|---|
| V094.sql（SQL + Guard A/B/C + comments） | ~80 | 0.5 day |
| Linux PG dry-run × 2 round（SQL execute + 6 verify queries） | N/A | 0.5 day |
| trading_writer.rs INSERT 升級 | ~30 | 0.3 day |
| TradingMsg::Fill enum 加 3 fields + comments | ~30 | 0.2 day |
| 13 caller sites 升級（per site +6 LOC None defaults） | ~80 | 0.5 day |
| close-maker-first commands.rs 改造寫 details + close_maker_* | ~50 | 0.5 day（已含 spec §4.1 IMPL scope，本 spec 不重複） |
| 4 healthcheck Python（[62][63][64][65]） | ~200 | 0.5 day |
| healthcheck runner.py 註冊 | ~10 | 0.1 day |
| **Total** | **~480 LOC** | **~3.1 E1-day**（含 Linux PG dry-run 0.5d） |

> **Note**：本 spec scope = V094 schema + writer upgrade + healthcheck。spec §4.1 commands.rs close-maker-first 改造（~50 LOC）屬 spec v1.2 §4.1 IMPL scope，本 spec 包含估計但不重複設計。

### 8.3 PA Worktree dispatch 建議

| Worktree | Files | 並行 |
|---|---|---|
| A (V094 SQL) | `sql/migrations/V094__fills_close_maker_audit.sql` (NEW) | 並行 B |
| B (writer + enum + callers) | `database/trading_writer.rs` + `database/mod.rs` + 13 caller sites | 並行 A（互不重疊）|
| C (healthcheck) | `helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py` (NEW) + `runner.py` | 串行（依賴 A 落地後 query 可跑） |

### 8.4 IMPL 派工時點

- **Wave 4**：本 V094 spec PM sign-off → 派 E1 worktree A+B 並行
- **Wave 4.1**：A+B done → 派 E1 worktree C 串行
- **Wave 4.2**：A+B+C done → 派 E2 review + E4 regression
- **Wave 4.3**：E2+E4 PASS → ssh trade-core Linux PG dry-run × 2 + deploy + healthcheck verify
- **Wave 4.4**：Phase 2a Demo 14d 觀察 → PM sign-off

**前置依賴**：3-gate（P0-EDGE-1 / W-AUDIT-8b Stage 0R / W-AUDIT-8a C1）解除 + Wave 1+1.5+2+3 全 done + AMD prereq 5 全 done（含本 spec sign-off）。

---

## §9 Backward Compat（per AMD §10.1）

### 9.1 Append-only 設計

V094 是 **append-only schema migration**：
- 加 2 new columns on `trading.fills`（`close_maker_attempt` BOOLEAN NOT NULL DEFAULT FALSE / `close_maker_fallback_reason` TEXT NULL）
- 加 1 CHECK constraint NOT VALID（chk_fills_close_maker_fallback_reason_v094）
- 加 1 partial index（idx_fills_close_maker_attempt_v094）
- 利用既有 `trading.fills.details` JSONB（V003 line 284）寫 3 個 keys（`close_*` prefix，無 namespace 衝突）

### 9.2 不破現有 SELECT / INSERT / UPDATE

| 既有操作 | V094 影響 |
|---|---|
| `SELECT * FROM trading.fills` | new columns 出現在 result，但不破 column count（client-side decode 用 column name 不是 index） |
| `SELECT details FROM trading.fills` | 既有 details rows 0 影響；future close_maker rows 多 3 keys |
| `INSERT INTO trading.fills (..., details)` 既有 caller | 0 影響（caller 不寫 close_maker_attempt 拿 default FALSE；不寫 close_maker_fallback_reason 拿 NULL） |
| `UPDATE trading.fills SET ...` | 0 影響（ALTER COLUMN 既有 columns 完全不動） |
| 既有 healthcheck（51 個 check） | 0 影響（沒有 check 引用 V094 新欄位） |

### 9.3 對 entry / close fill NULL ladder

| Fill type | close_maker_attempt | close_maker_fallback_reason | details |
|---|---|---|---|
| entry fill | FALSE (default) | NULL | NULL（既有行為） |
| close fill — market path（safety / negative whitelist） | FALSE | NULL | NULL（既有行為） |
| close fill — maker success（無 fallback） | TRUE | NULL | JSON 含 3 keys |
| close fill — maker fallback（timeout / postonly_reject / etc.） | TRUE | enum 值 | JSON 含 3 keys |

> **AC-6 NULL ladder（per spec §11.1 + AMD §11）**：
> - PASS：`close_maker_attempt=TRUE AND fallback_reason NOT IN (safety enum 3) AND details IS NULL` ratio ≤ 0.1%
> - WARN：0.1% < ratio ≤ 1.0%
> - FAIL：ratio > 1.0%
> - safety enum 3 (`fast_escalate_safety_upgrade` / `not_attempted_safety_path` / `engine_shutdown_safety`) 不算 NULL

### 9.4 IMPL 階段不可改設計（重評風險）

per AMD §10.1：
> 如果 IMPL 階段 PA 改設計從 hybrid 變成 separate column（即 `close_initial_limit_price` 等也走 new column）→ **必重評 backward-compat 影響 + 重派 4-agent review**。

本 spec hybrid schema 是 SoT；E1 IMPL 不可在「方便」名義下改 separate column。

---

## §10 Rollback Path

### 10.1 Phase 2a Demo / Phase 2b LiveDemo / Phase 3 Live FAIL → TOML hot-reload

per AMD §10：
- TOML hot-reload `use_maker_close=false` → 1 tick 內回 market path
- V094 schema **不需要 rollback**（new columns 留著，只是後續 fills row `close_maker_attempt` 全 FALSE）
- close_maker_fallback_reason 全 NULL（與 entry fill 相同）
- 既有 details NULL rows 不被觸碰

### 10.2 IMPL 階段未 deploy → V094 schema rollback

**極端場景：V094 已 apply 到 Linux runtime 但 IMPL 後發現必須 reject spec**。

```sql
-- ⚠️ 不可在 prod 執行 DROP（會丟既有 audit 數據）
-- rollback 場景僅限 IMPL 階段未 deploy（早期 dry-run 階段）

ALTER TABLE trading.fills
    DROP COLUMN IF EXISTS close_maker_attempt;

ALTER TABLE trading.fills
    DROP COLUMN IF EXISTS close_maker_fallback_reason;
    -- DROP COLUMN 自動 cascade DROP CHECK constraint chk_fills_close_maker_fallback_reason_v094

DROP INDEX IF EXISTS trading.idx_fills_close_maker_attempt_v094;

-- _sqlx_migrations row 也需手動 DELETE 否則 sqlx 認為 V094 已 apply
DELETE FROM _sqlx_migrations WHERE version=94;

-- trading_writer.rs revert 到 23-column INSERT
-- 13 caller sites revert 到不寫 details/close_maker_* 三 fields
-- TradingMsg::Fill enum revert 到 21 fields
```

### 10.3 Post-deploy rollback path

| 場景 | 動作 | V094 schema 影響 |
|---|---|---|
| Phase 2a/2b/3 metric FAIL | TOML `use_maker_close=false` hot-reload | 不需 schema rollback |
| Phase 2a 發現 bug 必修 | TOML hot-reload + E1 修 IMPL + redeploy | 不需 schema rollback |
| 必須完全棄 V094 schema | IMPL revert + Linux PG manual DROP（per §10.2） | 需 manual DROP；只限 IMPL 階段未 deploy |
| operator 執行 emergency kill-switch | engine cancel_token shutdown + force market | 不需 schema rollback |

---

## §11 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰

### 11.1 改動風險評級 = **中**

V094 是 schema migration + writer hot-path 升級 + 13 caller sites 修改：
- **中**：schema migration 必經 Linux PG empirical dry-run × 2 + sqlx checksum repair（V055/V083/V084 incident precedent risk mitigated）
- **中**：trading_writer.rs INSERT 列表升級觸 hot-path（每 fill INSERT 走此路）；Rust 強型別保證 caller compile-time 不漏接（13 sites + tests 全 enumerated）
- **低**：healthcheck integration 純新增，無既有 test breakage 風險
- **低**：backward-compat append-only（mirror V083 NOT VALID precedent，0 ALTER existing column / 0 DROP / 0 RENAME）

### 11.2 16 根原則合規（16/16）

| 原則 | 狀態 | 證據 |
|---|---|---|
| #1 單一寫入口 | PASS | V094 不改 IntentProcessor / submit_intent 既有契約 |
| #2 讀寫分離 | PASS | healthcheck 純 SQL SELECT；writer 升級不改寫入路徑（仍走 trading_writer task） |
| #3 AI→Lease→複核→執行 | PASS | V094 不觸 lease；保護 W-C Caveat 2 close path 不寫 spine 不變式（per F-FA-3 6 grep guard patterns）|
| #4 策略不繞風控 | PASS | V094 不觸 Guardian / risk_envelope；safety path enum 3 值（fast_escalate / not_attempted / engine_shutdown）保護風控優先 |
| #5 生存 > 利潤 | PASS | V094 audit trail 服務 §二 #5（empirical 證據服務 phys_lock + risk close 路徑優先 market 不走 maker）|
| #6 失敗默認收縮 | PASS | enum allowlist + NOT NULL DEFAULT FALSE = fail-closed audit；無 enum 值落到 NULL |
| #7 學習 ≠ 改寫 Live | PASS | V094 5 audit 欄位 permanently-banned from ML training pipeline（per MIT-MF-1 + non-training surface invariant + grep guard rule）|
| #8 交易可解釋 | PASS（**strengthens**） | V094 5 audit 欄位 + 4 healthcheck dual-gate 全鏈條 audit 完整性服務原則 #8 |
| #9 災難保護 | PASS | enum 含 `engine_shutdown_safety` 顯式記錄 cancel_token / authorization 失效時的 audit row |
| #10 認知誠實 | PASS | 本 spec §4.4 顯式標記 spec/AMD wording drift（V93 vs V90 真實狀態），事實/推斷分明 |
| #11 P0/P1 內自主 | PASS | V094 不觸 cognitive_modulator |
| #12 持續進化 | PASS | V094 audit trail 是進化前提（F-FA-2 + F-FA-3 + 本 spec 三鏈完整）|
| #13 AI cost 感知 | PASS | V094 不觸 AI |
| #14 零外部成本可運行 | PASS | V094 純 PG schema + Rust writer，無外部依賴 |
| #15 多 Agent 協作 | PASS | V094 不觸 MessageBus / agent topics |
| #16 組合風險 | PASS | V094 不觸 portfolio_var（per AMD §7 #16 MAINTAIN per A3 verify finding）|

### 11.3 DOC-08 §12 9 條安全不變量觸碰（0/9）

| 不變量 | 觸碰 | 評估 |
|---|---|---|
| Pre-trade audit/replay 必開 | NO | V094 不改 pre-trade gate |
| Lease 必在執行前 acquired | NO | V094 不觸 lease |
| 執行回報必落 fills 表 | **strengthens** | V094 升 writer 寫 details 完整性，從 0% → ≥99.9%（per AC-6 NULL ladder PASS） |
| 風控降級 → engine 自動止血 | NO | V094 不觸風控 |
| Authorization 過期 → cancel_token shutdown | NO | V094 不觸 authorization |
| Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒 | NO | V094 不觸 mainnet spawn |
| Bybit retCode != 0 → fail-closed 不重試 | NO | V094 不觸 retry |
| Reconciler 對賬差異 → 自動降級 paper | NO | V094 不觸 reconciler |
| Operator 角色與 live_reserved 缺一即拒 | NO | V094 不觸 operator auth |

### 11.4 §四 5 硬邊界觸碰（0/5）

`execution_state` / `execution_authority` / `live_execution_allowed` / `decision_lease_emitted` / `max_retries=0` 全 0 觸碰。

---

## §12 E2 Review 重點 3 項

per PA 輸出物標準（profile.md §輸出物標準）：

### 12.1 Linux PG dry-run gate 證據 ID 必出現

E2 PR 審查必拒「無 Linux PG dry-run × 2 round 證據 ID」的 V094 PR。SOP per CLAUDE.md §七：
- E1 IMPL commit message 含 dry-run round 1 + round 2 commit ID 或 ssh trade-core 操作 ID
- 重跑 V094 SQL 第二次的 NOTICE 輸出 attached（idempotency 證明）

### 12.2 13 caller sites 必全部修（無一漏接）

E2 必跑 grep 驗證 `TradingMsg::Fill { ... }` 全 codebase 13 sites 已加 3 new fields：
```bash
# 每個 caller site 必含以下三行：
grep -A 25 "TradingMsg::Fill {" srv/rust/openclaw_engine/src/ -r | grep -E "details:|close_maker_attempt:|close_maker_fallback_reason:"
# Expected: 39 hits（13 sites × 3 fields）；少於 39 即 PR reject
```

### 12.3 W-C Caveat 2 不變式不破（Wave 1 Track A4 6 grep guard patterns）

E2 必跑 PA Wave 1 Track A4 report §3.1 6 grep guard patterns：
- Pattern 1a/1b: close path 不寫 spine_*_id Some(...)
- Pattern 2a/2b: emit_entry_lineage / emit_fill_completion_lineage callsite 上下文不含 close_maker_*
- Pattern 3a/3b/3c: ML training pipeline / SQL / feature engineering 不引用 close_maker_*

任一 pattern 命中 ≥ 1 → PR reject。

---

## §13 PA Verdict

**判定**：**SPEC-FINAL — F-FA-1 解除條件 (a)(b)(c) 全完成**

| F-FA-1 子條件 | 完成證據 |
|---|---|
| (a) PA spec finalize V094 `sql/migrations/V094__fills_close_maker_audit.sql` | 本 spec §2 schema + §3 Guard A/B/C + §10 rollback |
| (b) trading_writer.rs INSERT INTO trading.fills 列表升級 details JSONB 寫入路徑 spec finalize | 本 spec §6 writer upgrade + 13 caller sites + TradingMsg::Fill enum + cross-language IPC |
| (c) Linux PG empirical query 驗證 trading.fills 既有 schema 對齊 | 本 spec §1.2 hybrid schema 設計理由 + §4 Linux PG dry-run × 2 round protocol + §4.4 V93 vs V90 drift caveat 修正 |

**11.2 16 原則 16/16 + 11.3 DOC-08 §12 0/9 觸碰 + 11.4 §四 0/5 觸碰** = 0 BLOCKER。

**改動風險評級 = 中**（schema migration + writer hot-path + 13 caller sites）；mitigated by Linux PG empirical dry-run × 2 + sqlx checksum repair SOP + caller sites enumeration + backward-compat append-only。

**核心教訓**：

1. **Hybrid schema (hot column + JSONB extension) > 全 column / 全 JSONB**：5 audit 欄位中 2 個有 hot-path filter 需求（healthcheck [62]/[63] GROUP BY），3 個是低 cardinality 純 audit；hybrid 是性能與 schema bloat 的 Pareto 平衡。
2. **Writer gap 必先 empirical 驗 (V083 incident pattern revisit)**：`trading_writer.rs:430` 23-column INSERT 漏 details 是 24h 100% 確認的 systemic gap；V094 IMPL **必同步升 writer**，否則 audit 欄位 100% NULL → guard tests 全 FAIL → spec sign-off 撤回。PA 派 sub-agent 前必 empirical re-check 既有 schema + writer 對齊現實，不能基於 spec 假設設計（per F-FA-3 PA report §1.2 同 lesson）。
3. **Linux PG empirical query mandatory（V055 5-round loop + V083 + V084 + sqlx hash drift incident chain）**：V094 涉及 PG reflection（`pg_get_constraintdef` / `pg_get_indexdef` / `information_schema.columns`）+ enum CHECK constraint runtime semantic + partial index 行為，Mac mock pytest **絕對不夠**。E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID。
4. **TradingMsg::Fill enum 升級 = 13 caller sites 強制 enumeration**：Rust 強型別保證 compile-time 不漏接，但 PR review 仍需 grep verify 39 hit count（13 × 3 fields）；遺漏一個 caller 會編譯錯，遺漏一個 default value 會語意錯（close_maker_attempt: None vs false）。
5. **spec/AMD wording drift 修正（V93 → V90 真實狀態）**：spec v1.2 §4.4 + AMD v0.3 §4.1 寫 "current max applied V093" 是 incorrect。Linux runtime applied max 真實 = V90（V81/V91/V92/V93 source 在 git 但 PG 未 apply）。本 spec §4.4 顯式 caveat 段是 source-of-truth 修正；spec/AMD 文字無需 patch（V094 仍 next-free numeric slot；deploy semantic 不變）。E1 IMPL kickoff 前 PA 補一輪 Linux V81/V91/V92/V93 dry-run 檢查或 PM 接受連帶 apply accepted risk + 1d buffer。
6. **Backward-compat append-only 是 V083 mirror 範式的延伸**：mirror V083 NOT VALID CHECK + partial WHERE close_maker_attempt = TRUE + Guard A/B/C；保證重跑 V094 idempotent + 既有 fills row 0 影響 + 既有 healthcheck 0 影響 + 既有 caller 0 break。

---

## §14 後續行動（給 PM 派發）

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V094 spec | PM | Wave 2 Track A2 closure | P0 |
| Update AMD v0.3 → v0.3.1：§8 IMPL Prereq 5 第 3 子條件 marker `F-FA-1 V094 spec ✅ DONE Wave 2a (commit ...)` | PM 派 PA AMD patch | Wave 2a closure | P0 |
| Update TODO §11.5 Wave 2 Status block：A2 ✅ DONE | PM | Wave 2 closure | P0 |
| Update TODO §15 後續工作項：F-FA-1 → DONE row | PM | Wave 2 closure | P0 |
| 派 Wave 3 4-agent short re-review on AMD v0.3.1 + spec v1.2 + V094 spec | PM | Wave 3 dispatch | P1 |
| IMPL kickoff（Wave 4 / 3-gate 解除後）：派 E1 worktree A+B 並行 → C 串行 → E2/E4/Linux PG dry-run/deploy/healthcheck verify | PM | Wave 4+ dispatch | P1 |
| Pre-Wave 4 Linux V81/V91/V92/V93 backlog migration apply 檢查（per §4.4 caveat） | PA | Wave 3.5 | P1 |

### 14.1 Wave 2a Track A2 closure 標誌

本 spec PM sign-off → F-FA-1 解除條件 (a)(b)(c) 全完成 → AMD §8 IMPL Prereq 5 第 3 子條件 ✅ DONE → 與 Track A1 ✅ + Track A3 ✅ + Track A4 ✅ 並行收口 → IMPL prereq 5 全 done → 待 prereq 1/2/3/4/6 全 done + 3-gate 解 → IMPL kickoff Wave 4。

---

## §15 關鍵文件指針（後續 IMPL agent / PM / E2 / E4 必讀）

- 本 V094 spec：本檔
- F-FA-1 parent ticket spec：`srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` v1.2 §4.4 + §11.7 + §15
- AMD v0.3：`srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md` §4.1 + §10.1
- F-FA-3 W-C Caveat 2 guard tests + writer gap discovery：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md`
- V083 mirror precedent：`srv/sql/migrations/V083__fills_entry_context_id_close_check.sql`
- V003 trading.fills base schema (含 details JSONB line 284)：`srv/sql/migrations/V003__trading_agent_tables.sql`
- schema_guard_template：`srv/sql/migrations/templates/schema_guard_template.sql`
- trading_writer.rs（writer gap 對象 line 430）：`srv/rust/openclaw_engine/src/database/trading_writer.rs`
- TradingMsg::Fill enum（mod.rs line 281-376）：`srv/rust/openclaw_engine/src/database/mod.rs`
- repair binary：`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- healthcheck framework：`srv/helper_scripts/db/passive_wait_healthcheck/`
- V055 5-round loop + sqlx hash drift incident lessons：`srv/docs/CCAgentWorkSpace/PA/memory.md`（搜 `feedback_v_migration_pg_dry_run` + `project_2026_05_02_p0_sqlx_hash_drift`）
- CLAUDE.md §七 V### migration 規範：`srv/CLAUDE.md`

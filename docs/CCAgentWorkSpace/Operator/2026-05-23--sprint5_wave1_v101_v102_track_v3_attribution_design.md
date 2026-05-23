---
report: PA design — Sprint 5+ Wave 1 §8.1 V101/V102 Track v3 attribution column + indexes
date: 2026-05-23
author: PA
phase: Sprint 5+ Wave 1 (per Stage F PM Phase 3e sign-off §8.1 carry-over)
status: DESIGN-DONE
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md §8.1
spec_artifacts:
  - docs/execution_plan/specs/2026-05-23--v101-track-v3-attribution-column.md
  - docs/execution_plan/specs/2026-05-23--v102-track-v3-indexes-not-null.md
risk_grade: 中 (新 V### ADD column on hot-path table trading.fills + columnstore hypertable feature_not_supported constraint + trigger fallback path)
push_back: Yes (operator prompt scope = trading.fills only;v3 spec full 12-table + 2 new table + 4 view + kill_events 拆 Sprint 5+ Wave 2 Phase 2 carry-over)
---

# §1 Executive Summary

per Stage F PM Phase 3e §8.1 carry-over (HEAD 5a58cc96, 2026-05-23) + operator 拍板「V101/V102 現在順手推上去」+ 3-4 hr single-thread budget — PA single-thread 完成 V101/V102 spec doc + IMPL 預估設計。

**核心 push back**：v3 spec (`2026-05-20--v101_v102_track_attribution_migration_spec.md`) 完整 scope = 12 既存表 ADD COLUMN + 2 新表 CREATE + 4 view + governance.track_kill_events + ENUM + Rust enum + Guardian check 6 + 4 view P&L attribution — 估 40-60 hr E1 effort 遠超 3-4 hr single-thread budget。

**PA 收緊 scope**：V101/V102 spec 限縮至 `trading.fills` only（per operator prompt 字面）；其他 11 表 + 2 新表 + view + kill_events 拆 Sprint 5+ Wave 2 Phase 2 carry-over 處理。

**衝突解析**：v3 spec §3.3.1 寫 CREATE TABLE learning.hypotheses，但 V100 (2026-05-23) 已 land 同表 base schema — 從本 V101 spec 削除（避 conflict）。

**3 deliverable**：
1. V101 spec doc — `srv/docs/execution_plan/specs/2026-05-23--v101-track-v3-attribution-column.md` (~600 LOC spec)
2. V102 spec doc — `srv/docs/execution_plan/specs/2026-05-23--v102-track-v3-indexes-not-null.md` (~640 LOC spec)
3. 本 PA design report

**E1 IMPL est**：V101 ~3-4 hr (SQL ~250 LOC + cargo test + Mac IMPL) + V102 ~3-4 hr (SQL ~280 LOC + cargo test + Mac IMPL) = ~6-8 hr E1 single-thread；含 Sandbox dry-run + Production deploy 額外 ~2-4 hr (operator + PA execute)；total wall-clock ~8-12 hr。

---

# §2 V101 設計

## 2.1 spec 路徑 + LOC + Scope

- **路徑**：`srv/docs/execution_plan/specs/2026-05-23--v101-track-v3-attribution-column.md`
- **LOC**：~600 (spec doc) + ~250 SQL est (V101__track_v3_attribution_column.sql)
- **Scope**：
  - CREATE TYPE strategy_track ENUM (3 值: direct_exploit / asds_factory / baseline) per V057 範式（EXCEPTION WHEN duplicate_object）
  - ADD COLUMN track strategy_track NULL on trading.fills (per V094 範式)
  - Batched UPDATE backfill (10000 + 100ms sleep loop) 既有 row 全 → 'baseline'
  - V101 結尾 verify 0 NULL row

## 2.2 ADD COLUMN 設計

```sql
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

ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS track strategy_track NULL;
```

## 2.3 Guard A/B/C 設計

| Guard | 邏輯 | RAISE 條件 |
|---|---|---|
| **A** | trading.fills exist + 15 baseline column (ts/fill_id/order_id/symbol/side/qty/price/fee/strategy_name/context_id/engine_mode/entry_context_id/exit_reason/close_maker_attempt/details) 完整 | 表缺 或 baseline column 缺（V003+V015+V077+V083+V094 schema drift）|
| **B** | track column 已存在情境驗 type=USER-DEFINED + udt=strategy_track + nullable=YES | type drift（重跑時抓） |
| **C 預檢** | （首跑 skip） | — |
| **Main DDL** | CREATE TYPE + ADD COLUMN + Batched UPDATE backfill + 結尾 0 NULL verify | backfill 失敗 RAISE |
| **C 後驗** | strategy_track 3 enum 值 + column 存在 + nullable=YES + 0 NULL row | 任一檢查 FAIL RAISE |

## 2.4 4 Acceptance Criteria

| AC | 驗證 | 階段 |
|---|---|---|
| AC-1 | V101 file LAND + cargo test sqlx Migrator parser accept + sort chain V100→V101→V103 monotonic | Phase A E1 IMPL |
| AC-2 | Sandbox Round 1+2 idempotent + 5 reflection SQL PASS（ENUM 3 值 / column 對齊 / 0 NULL backfill / row count / strategy_name 對映） | Phase B operator + PA |
| AC-3 | V101 → V103 EXTEND chain Guard A 自然 PASS（V103 不依 trading.fills.track） | Phase B sandbox empirical |
| AC-4 | Production engine restart + auto-migrate land + 30 min observe + Sprint 5+ Writer path 預留 | Phase C-D operator + PA + E1 |

---

# §3 V102 設計

## 3.1 spec 路徑 + LOC + Scope

- **路徑**：`srv/docs/execution_plan/specs/2026-05-23--v102-track-v3-indexes-not-null.md`
- **LOC**：~640 (spec doc) + ~280 SQL est (V102__track_v3_indexes_not_null.sql)
- **Scope**：
  - 2 hot-path index on trading.fills (track, ts DESC) + (strategy_name, track)
  - ALTER COLUMN ... SET DEFAULT 'baseline'
  - BEFORE INSERT/UPDATE OF track trigger fail-closed (per V077 範式)

## 3.2 indexes 設計 (2 only)

```sql
CREATE INDEX IF NOT EXISTS idx_fills_track_ts_v102
    ON trading.fills (track, ts DESC);

CREATE INDEX IF NOT EXISTS idx_fills_strategy_track_v102
    ON trading.fills (strategy_name, track);
```

| Index | Hot-path query | 對映設計依據 |
|---|---|---|
| `idx_fills_track_ts_v102` | `WHERE track='direct_exploit' AND ts > now() - INTERVAL '7d' ORDER BY ts DESC` | per-track time-series P&L attribution；4 P&L view (v3 spec §4.3) 主索引 |
| `idx_fills_strategy_track_v102` | `WHERE strategy_name='grid_trading' GROUP BY track` | Track A/B/C 對映 strategy 一致性 verify（per ADR-0025 v3 X-AC5）|

**為什麼非 CONCURRENTLY**：sqlx migrate 包入 BEGIN/COMMIT transaction；CONCURRENTLY 在 transaction 內 RAISE；對齊 V094 + V083 + V028 既有 trading.fills 6 個 index land 範式（全 CREATE INDEX IF NOT EXISTS）。

## 3.3 NOT NULL handling 路徑 — 3 Options 比對 + PA Verdict

### Option A — 永遠 NULL allowed

| 維度 | 評估 |
|---|---|
| columnstore 兼容 | ✅ 完美 |
| fail-closed 強度 | ❌ 弱 — silent corruption 風險（per 根原則 6 違反）|
| Sprint 5+ Track A/B writer 強制度 | 0 — application self-discipline only |
| 評分 | NOT RECOMMENDED |

### Option B — BEFORE INSERT/UPDATE trigger + DEFAULT 'baseline' (PA 強推)

```sql
-- DEFAULT (metadata-only;預期 PASS)
ALTER TABLE trading.fills ALTER COLUMN track SET DEFAULT 'baseline';

-- trigger fail-closed (per V077 範式 PM signed 2026-05-09 49ceeb61)
CREATE OR REPLACE FUNCTION trading.enforce_fills_track_not_null()
RETURNS trigger
LANGUAGE plpgsql
AS $fn$
BEGIN
    IF NEW.track IS NULL THEN
        RAISE EXCEPTION
            'V102 trigger violation: trading.fills.track must not be NULL ...';
    END IF;
    RETURN NEW;
END
$fn$;

CREATE TRIGGER trg_fills_track_not_null_v102
    BEFORE INSERT OR UPDATE OF track ON trading.fills
    FOR EACH ROW
    EXECUTE FUNCTION trading.enforce_fills_track_not_null();
```

| 維度 | 評估 |
|---|---|
| columnstore 兼容 | ✅ trigger fallback 對齊 V077 範式（已 verified 2026-05-09）|
| fail-closed 強度 | ✅ writer 漏填 RAISE EXCEPTION |
| Sprint 5+ Track A/B writer 強制度 | ✅ catch early |
| DEFAULT 'baseline' 雙保險 | ✅ writer 漏填降級行為（不 trigger violation;走 default）|
| rollback 風險 | 低（DROP TRIGGER 可逆） |
| 評分 | **STRONGLY RECOMMENDED** |

### Option C — backfill UPDATE + ALTER COLUMN SET NOT NULL

| 維度 | 評估 |
|---|---|
| columnstore 兼容 | ❌ 預期 RAISE feature_not_supported (per V077 教訓) |
| runtime 風險 | 高 — production deploy 失敗 = rollback / 手動 fix |
| 評分 | NOT RECOMMENDED |

### PA Verdict: Option B

3 理由：
1. **columnstore-safe**：完全對齊 V077 hotfix 範式（PM signed 2026-05-09 49ceeb61），avoid feature_not_supported RAISE
2. **fail-closed 強度**：trigger RAISE + DEFAULT 'baseline' 雙保險（catch early + 降級行為）
3. **per ADR-0025 v3 semantic 對齊**：NOT NULL 不變式達成（writer 必填 track）；enforcement mechanism 從 column constraint 改 trigger

## 3.4 Guard A/B/C 設計

| Guard | 邏輯 | RAISE 條件 |
|---|---|---|
| **A** | V101 prerequisite verify — trading.fills.track column exist + strategy_track ENUM exist + 0 NULL row | V101 未 apply / V101 backfill 未 100% |
| **B** | DEFAULT 'baseline' + trigger 已存在情境 type/def drift | drift catch |
| **C 預檢** | （首跑 skip） | — |
| **Main DDL** | 2 index + ALTER COLUMN SET DEFAULT 'baseline' + CREATE OR REPLACE FUNCTION + CREATE TRIGGER | 任一 RAISE feature_not_supported = fallback path 走 trigger-only |
| **C 後驗** | 2 index def 對齊 + DEFAULT 'baseline' set + trigger count = 1 | 任一檢查 FAIL RAISE |

## 3.5 3 Acceptance Criteria

| AC | 驗證 | 階段 |
|---|---|---|
| AC-1 | V102 file LAND + cargo test sqlx Migrator parser accept | Phase A E1 IMPL |
| AC-2 | Sandbox Round 1+2 idempotent + 5 reflection SQL PASS（2 index / DEFAULT 'baseline' / trigger / fail-closed 行為 / default 行為） | Phase B operator + PA |
| AC-3 | Production engine restart + auto-migrate land + Sprint 5+ Writer path 預留 + 30 min observe + 0 trigger violation | Phase C-D operator + PA + E1 + Sprint 5+ Wave 2 dependency |

---

# §4 NOT NULL 處理路徑 (3 Options 比對) + PA Verdict

per V102 spec §3：

| Option | columnstore 兼容 | fail-closed 強度 | runtime 風險 | PA 推薦 |
|---|---|---|---|---|
| A NULL allowed | ✅ | ❌ 弱 | 0 | NOT RECOMMENDED |
| **B trigger + DEFAULT (本選)** | ✅ V077 範式 | ✅ 強 (catch early + DEFAULT 雙保險) | 低 | **STRONGLY RECOMMENDED** |
| C ALTER COLUMN SET NOT NULL | ❌ feature_not_supported (per V077) | ✅ 強 | 高 (production RAISE / rollback) | NOT RECOMMENDED |

**選 Option B 的關鍵 critical lesson 對齊**：V077 hotfix runtime (2026-05-09 PM signed 49ceeb61) 已對 trading.fills 在 columnstore-enabled hypertable 上嘗試 CHECK constraint 失敗 + 走 BEFORE INSERT/UPDATE trigger fallback path 全鏈 verified。V102 採同範式 → 0 runtime surprise。

---

# §5 4 AC + Sprint 5+ IMPL phase split + E1 IMPL est

## 5.1 4 Acceptance Criteria 合併（V101 4 + V102 3）

| AC | 驗證 | 階段 | 預估時間 |
|---|---|---|---|
| **AC-V101-1** | V101 file LAND + cargo test PASS | Phase A E1 | ~30 min |
| **AC-V101-2** | V101 Sandbox Round 1+2 idempotent + 5 reflection SQL PASS | Phase B operator + PA | ~30 min |
| **AC-V101-3** | V101 → V103 chain Guard A 不阻塞 | Phase B sandbox empirical | ~5 min |
| **AC-V101-4** | V101 Production deploy + 30 min observe | Phase C-D | ~30 min + 30 min observe |
| **AC-V102-1** | V102 file LAND + cargo test PASS | Phase A E1 | ~30 min |
| **AC-V102-2** | V102 Sandbox Round 1+2 idempotent + 5 reflection SQL PASS（含 trigger fail-closed 行為 + DEFAULT 行為） | Phase B operator + PA | ~45 min |
| **AC-V102-3** | V102 Production deploy + 30 min observe + 0 trigger violation | Phase C-D | ~30 min + 30 min observe |

## 5.2 Sprint 5+ IMPL phase split

```
Phase A: Mac IMPL (E1 single-thread)
  ├─ V101__track_v3_attribution_column.sql (~250 LOC)
  │   ├─ CREATE TYPE strategy_track ENUM (3 值)
  │   ├─ ADD COLUMN track strategy_track NULL on trading.fills
  │   ├─ Batched UPDATE backfill (10000 + 100ms sleep loop)
  │   ├─ V101 結尾 0 NULL verify
  │   └─ Guard A/B/C + COMMENT
  └─ V102__track_v3_indexes_not_null.sql (~280 LOC)
      ├─ Guard A V101 prerequisite verify
      ├─ ALTER COLUMN ... SET DEFAULT 'baseline'
      ├─ CREATE OR REPLACE FUNCTION trading.enforce_fills_track_not_null()
      ├─ CREATE TRIGGER trg_fills_track_not_null_v102 (BEFORE INSERT OR UPDATE OF track)
      ├─ CREATE INDEX idx_fills_track_ts_v102 + idx_fills_strategy_track_v102
      └─ Guard B/C + COMMENT

Phase A E1 IMPL est: ~3-4 hr (V101 ~1.5 hr + V102 ~2 hr + cargo test + 兩 .sql commit + Mac local verify)

Phase B: Sandbox dry-run (operator + PA execute on Linux trade-core)
  ├─ V101 Round 1 + 5 reflection SQL ~10 min
  ├─ V101 Round 2 idempotent ~5 min
  ├─ V102 Round 1 + 5 reflection SQL ~15 min
  ├─ V102 Round 2 idempotent ~5 min
  └─ V103 chain reapply check ~5 min

Phase B est: ~45 min Linux trade-core wall-clock

Phase C: Production deploy (operator + PA execute)
  ├─ OPENCLAW_AUTO_MIGRATE=0→1 + restart_all.sh (no rebuild)
  │   OR raw psql -f path (per V100 production deploy 範式)
  └─ _sqlx_migrations 確認 MAX 100→102

Phase C est: ~30 min

Phase D: verify
  ├─ trading.fills.track column 物理存在 + 100% backfilled baseline
  ├─ 2 index 物理 land
  ├─ DEFAULT 'baseline' 生效 (test INSERT)
  ├─ trigger 強制 NOT NULL (test INSERT track=NULL → RAISE)
  ├─ engine startup 0 panic
  └─ 30 min observe + AC-1b SQL 重驗

Phase D est: ~1 hr (含 30 min observe)
```

**total Sprint 5+ Wave 1 §8.1 V101/V102 IMPL wall-clock**：~6-8 hr E1 + ~2-3 hr operator + PA = **~8-11 hr** wall-clock，**或 ~6-10 hr** depending on Sandbox dry-run + observe parallel。

## 5.3 Sprint 5+ Wave 2 Phase 2 Carry-over

V101/V102 只覆蓋 `trading.fills`；其他 attribution surfaces 拆 Sprint 5+ Wave 2 Phase 2：

| Item | V### 預估 | scope | 估工時 |
|---|---|---|---|
| trading.intents/orders/signals/risk_verdicts/position_snapshots/decision_outcomes ADD track | V104+ | 6 表 ADD COLUMN + backfill | 8-12 hr |
| learning.lease_transitions / strategy_trial_ledger / cost_edge_advisor_log ADD track | V104+ | 3 表 ADD COLUMN | 4-6 hr |
| agent.ai_invocations / decision_objects ADD track | V104+ | 2 表 ADD COLUMN | 2-4 hr |
| CREATE TABLE governance.track_kill_events | V104+ | 1 新表 | 2-3 hr |
| 4 P&L view (track_direct_exploit_daily / track_asds_factory_daily / track_baseline_daily / track_summary_daily) | V104+ | 4 view + net_edge_bps computed | 2-3 hr |
| 12 indexes + NOT NULL trigger fan-out 對 11 ALTER 表 | V104+ | 11 trigger + 11 index | 8-12 hr |
| Rust enum + writer fan-out | Sprint 5+ Wave 2 Rust IMPL | Rust StrategyTrack enum + 5 既有策略 declare baseline | 12-20 hr |

**total Sprint 5+ Wave 2 Phase 2 carry-over estimated effort**：~40-60 hr E1 + E2 + dispatch chain (建議拆 3-4 並行 sub-agent + 1-2 day wall-clock)

---

# §6 Dispatch Readiness Verdict + E2 重點審查 3 條

## 6.1 Dispatch Readiness Verdict — **DISPATCH READY (OPEN)**

**8 前置條件確認**：

| # | 前置 | 狀態 |
|---|---|---|
| 1 | V099 autonomy_level_config spec land | ✅ DESIGN-LAND (568 LOC, 2026-05-22) |
| 2 | V100 M4 base table production deploy | ✅ LAND 2026-05-23 (HEAD e377a94e) |
| 3 | V103 EXTEND M4 hypothesis columns production deploy | ✅ LAND 2026-05-23 (HEAD e377a94e) |
| 4 | trading.fills V003 + V015/V077/V083/V094 schema baseline | ✅ LAND production (per V094 2026-05-15 PM signed) |
| 5 | V077 columnstore trigger fallback 範式 verified | ✅ PM signed 2026-05-09 (49ceeb61) |
| 6 | sqlx Migrator chain V100 → V103 monotonic | ✅ verified (per Stage A-E §4.3) |
| 7 | Linux PG empirical SOP 範式 | ✅ verified (per V100 + V103 sandbox + production chain) |
| 8 | strategy_track ENUM 3 值 + Rust Track enum 設計 | ✅ ADR-0025 v3 + ADR-0026 v3 specified |

**Risk grade**: 中（hot-path table trading.fills + columnstore feature_not_supported constraint + trigger fallback path）

**派發優先級建議**：immediate dispatch（per operator 拍板 「現在順手推上去」+ 3-4 hr single-thread 字面字面字面）

**Confidence levels**：
- HIGH for V101 ADD COLUMN + backfill 設計（per V094 範式對齊）
- HIGH for V102 trigger fallback + DEFAULT 設計（per V077 範式對齊）
- HIGH for 8-11 hr wall-clock budget
- MEDIUM for ALTER COLUMN SET DEFAULT 'baseline' columnstore 兼容（PA 預設 metadata-only PASS，但未 sandbox empirical 驗）
- LOW for v3 spec full 12-table scope completeness (本 spec scope 收緊到 trading.fills only;其他 11 表 + view + kill_events 屬 Sprint 5+ Wave 2 Phase 2 carry-over，未在本 design 完整解決)

## 6.2 E2 重點審查 3 條

### E2-1: columnstore hypertable trigger fallback path 對齊 V077 範式

- V102 採 trigger-based NOT NULL enforcement（不走 ALTER COLUMN SET NOT NULL）
- trigger 名 `trg_fills_track_not_null_v102` + function `trading.enforce_fills_track_not_null` 對齊 V077 範式
- BEFORE INSERT OR UPDATE OF track ON trading.fills FOR EACH ROW + RAISE EXCEPTION on NULL
- Sandbox dry-run Reflection 4 驗 trigger fail-closed 行為（test INSERT track=NULL → RAISE）

**catch 重點**：E1 IMPL 嘗試 ALTER COLUMN SET NOT NULL → production RAISE feature_not_supported → 走 rollback；E2 必 reject 不對齊 V077 範式版本。

### E2-2: scope 嚴守 trading.fills only — Sprint 5+ Wave 2 Phase 2 carry-over

- V101/V102 spec scope 嚴守「trading.fills only」
- 不 ADD COLUMN on trading.intents/signals/orders/decision_outcomes/risk_verdicts/position_snapshots
- 不 ADD COLUMN on learning.* / agent.*
- 不 CREATE TABLE learning.hypotheses (V100 已 land — 衝突解析)
- 不 CREATE TABLE learning.hypothesis_preregistration (V100 已 land — 衝突解析)
- 不 CREATE TABLE governance.track_kill_events
- 不 CREATE VIEW track_*_daily
- 不 ADD COLUMN 'CHECK (track=...)' constraint on learning.hypotheses (V100 已建)
- spec §1.1 + §8 明文記錄 scope decision + Sprint 5+ Wave 2 Phase 2 carry-over

**catch 重點**：E1 IMPL 自行擴 scope（如「順手加 trading.intents.track」）= 違反 PA dispatch scope；E2 必 reject。

### E2-3: V101 backfill 100% verify + V102 Guard A V101 prerequisite verify

- V101 結尾 SELECT COUNT(*) WHERE track IS NULL = 0
- V102 Guard A 確認 V101 已 100% backfilled（再 verify 一次防 race condition）
- V102 開始時 0 NULL row + trigger 立即生效（防 V101 → V102 window 內 writer 漏填）
- Batched UPDATE 用 LIMIT 10000 + pg_sleep(0.1) + LOOP（per v3 spec §3.4 large table batch；per V094 同表 land 範式）

**catch 重點**：V101 backfill 中途 writer 寫入 track=NULL row → V101 結尾 verify FAIL → V102 應依此 RAISE 而不繼續 install trigger（避 trigger 半啟用 race condition）。

---

# §7 16 原則 + 9 安全不變量 + 8 hard boundary 合規

per CLAUDE.md §二 + DOC-08 §12 + 16-root-principles-checklist skill：

## 7.1 16 原則合規

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | V101/V102 純 SQL migration; 0 代碼寫入路徑;writer 接 track 屬 Sprint 5+ Wave 2 carry-over scope |
| 2 | 讀寫分離 | ✅ | 純 schema migration; 不破讀寫分離 |
| 3 | AI 輸出 ≠ 命令 | N/A | V101/V102 不涉 AI 輸出路徑 |
| 4 | 策略不繞風控 | ✅ | track column 是 attribution metadata; 不繞風控 |
| 5 | 生存 > 利潤 | ✅ | V102 trigger fail-closed 強制 NOT NULL = 生存優先 |
| **6** | **失敗默認收縮** | ✅ | **V102 Option B trigger fail-closed RAISE on NULL 對齊根原則 6** |
| 7 | 學習 ≠ 改寫 Live | ✅ | V101/V102 純 schema; 不改寫 live state |
| **8** | **交易可解釋** | ✅ | **track column = attribution audit trail; per-track P&L 4 view 設計** |
| 9 | 災難保護 | ✅ | trigger fallback = exchange-side disconnect 安全 |
| 10 | 認知誠實 | ✅ | scope push back 明示 (operator prompt vs v3 spec 差異) |
| 11 | Agent 最大自主 | ✅ | V101/V102 不限縮 Agent 自主性 |
| 12 | 持續進化 | ✅ | track attribution 支援後續 Track A/B 演進 |
| 13 | AI 成本感知 | N/A | V101/V102 不涉 AI 成本 |
| 14 | 零外部成本可運行 | ✅ | 純 PG 內部 schema |
| 15 | 多 Agent 協作 | ✅ | track attribution 不破 5-Agent 設計 |
| 16 | 組合級風險 | ✅ | track 為 attribution metadata; 支援 per-track 組合風險審計 |

**合規等級**：A 級 (16/16 PASS;0 違反;0 部分合規)

## 7.2 9 安全不變量 (DOC-08 §12)

| # | 不變量 | 狀態 |
|---|---|---|
| 1 | Pre-trade audit/replay 必開 | ✅ N/A schema migration |
| 2 | Lease 必在執行前已 acquired | ✅ N/A |
| 3 | 執行回報必落 fills 表 | ✅ track column 屬 fills audit metadata 增強 |
| 4 | 風控降級 → engine 自動止血 | ✅ N/A schema |
| 5 | Authorization 過期/失效 → engine cancel_token shutdown | ✅ N/A schema |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | ✅ N/A schema |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | ✅ N/A schema |
| 8 | Reconciler 對賬差異 → 自動降級 paper | ✅ N/A schema |
| 9 | Operator 角色與 live_reserved 缺一即拒 | ✅ N/A schema |

**安全不變量**：9/9 PASS（schema migration 不涉 runtime safety invariants）

## 7.3 8 Hard Boundary (CLAUDE.md §四)

| # | Boundary | V101/V102 觸碰 |
|---|---|---|
| 1 | True live 五門 | ❌ 0 觸碰 |
| 2 | Signed live authorization 寫法 | ❌ 0 觸碰 |
| 3 | LiveDemo 不降級 | ❌ 0 觸碰 |
| 4 | Mainnet env-var fallback | ❌ 0 觸碰 |
| 5 | Bybit retCode != 0 fail-closed | ❌ 0 觸碰 |
| 6 | execution_authority 真實授權 | ❌ 0 觸碰 |
| 7 | ML/DreamEngine/Executor/Strategist live-order ban | ❌ 0 觸碰 |
| 8 | Fake AI / fill / lineage / healthcheck / test ban | ❌ 0 觸碰 |

**Hard Boundary**：8/8 PASS（0 觸碰）

---

# §8 反模式（spec scope 守邊界）

per task prompt + V100 spec §8 範式 + V077 hotfix lesson：

| # | 反模式 | 防範 |
|---|---|---|
| 1 | 跑 v3 spec 全 12-table ADD COLUMN（scope creep） | V101 spec §1.1 + E2-2 重點 reject |
| 2 | V102 嘗試 ALTER COLUMN SET NOT NULL（columnstore feature_not_supported） | V102 spec §3.1 Option C 明示 NOT RECOMMENDED + E2-1 重點 reject |
| 3 | CONCURRENTLY index 在 sqlx migrate transaction（RAISE in transaction） | V102 spec §5.3 對齊 V094/V083/V028 既有 fills index 全 IF NOT EXISTS 範式 |
| 4 | V101 backfill 走 single big UPDATE（lock contention） | V101 spec §2.3 Batched 10000 + 100ms sleep loop |
| 5 | V101 → V102 部署中間 race window writer 漏填 track | V102 Guard A 確認 V101 100% backfilled + trigger 立即生效 |
| 6 | CREATE TABLE learning.hypotheses (v3 spec §3.3.1) | V100 已 land 同表; V101 spec §1.1 衝突解析削除 |
| 7 | trigger function 名 / trigger 名 不對齊 V077 範式 | V102 spec §3.2 + §3.3 直接 mirror V077 命名 |
| 8 | V101 結尾 verify 不 fail-closed (silent 不 RAISE) | V101 spec §2.4 RAISE EXCEPTION on 0 < NULL count |
| 9 | trigger fallback 採 AFTER INSERT 而非 BEFORE（race window 大）| V102 spec §3.2 BEFORE INSERT/UPDATE 範式對齊 V077 |
| 10 | DEFAULT 'baseline' 用 hardcode 'baseline'::strategy_track 文字 | V102 spec §3.2 直接 ALTER COLUMN SET DEFAULT 'baseline' (PG 自動推 ENUM type) |

---

# §9 教訓 / Spec design 反思

## 9.1 v3 spec full IMPL 與 operator 「順手」字面落差

**反思**：v3 spec 是個 40-60 hr E1 work 的 large schema migration（12 表 + 2 新表 + 4 view + ENUM + Rust enum + Guardian check 6），但 operator 拍板「現在順手推上去」+ 3-4 hr single-thread budget。

**處理路徑**：PA 必須 push back + 收緊 scope。沒 push back 就 dispatch 全 v3 spec scope = 用 40-60 hr work 衝 3-4 hr budget = task 失敗 + downstream block。

**Lesson learned**：未來 operator 「順手推」字面遇到 large legacy spec 必先 PA scope audit + push back，避 silent under-commitment。

## 9.2 V100 已 land learning.hypotheses 衝突解析

**反思**：v3 spec §3.3.1 寫 CREATE TABLE learning.hypotheses 帶 `track strategy_track NOT NULL DEFAULT 'asds_factory' CHECK (track = 'asds_factory')` — 但 V100 (2026-05-23 PM signed) 已 CREATE 同表 base schema 不含 track column。

**處理路徑**：本 V101 spec §1.1 衝突解析「learning.hypotheses 從本 V101 spec 削除（base 表概念已被 M4 hypothesis_discovery 走另一條路徑）」+ spec 註解 carry-over「Sprint 5+ Wave 2 Phase 2 處理 if needed (ADD COLUMN track on learning.hypotheses + CHECK constraint)」。

**Lesson learned**：parent spec 引用前必先 grep 真實 production state（per V100 land 後 learning.hypotheses 已存在 + base spec 衝突）。直接複製 v3 spec §3.3.1 = production deploy CREATE TABLE 衝突 RAISE。

## 9.3 trading.fills 是 columnstore hypertable 的 constraint awareness

**反思**：V077 hotfix runtime（2026-05-09 PM signed 49ceeb61）已暴露 trading.fills 在 columnstore-enabled hypertable 上 ALTER CHECK constraint RAISE feature_not_supported；V102 Option C ALTER COLUMN SET NOT NULL 預期同樣 RAISE。

**處理路徑**：V102 Option B trigger fallback path 對齊 V077 範式（PM signed 命名 + RAISE on NEW.column condition）— 直接 mirror 既有 production-verified 範式。

**Lesson learned**：trading.fills schema migration 必先 review columnstore constraint state（grep V077 / hypertable feature_not_supported）+ 對齊 trigger fallback 範式。直接寫 ALTER COLUMN SET NOT NULL = production deploy RAISE + rollback / 手動 fix overhead。

## 9.4 ADR-0025 v3 「12 表」設計與「3-4 hr single-thread」現實 gap

**反思**：ADR-0025 v3 + v3 spec 設計於 2026-05-20 階段假設 V### dispatch 走 full schema migration 一次性 land；但 Sprint 5+ Wave 1 §8.1 carry-over 字面 = 「current 順手」mode（最小可行 ship）。設計與 dispatch 階段 mode 不一致。

**處理路徑**：PA scope 收緊 + 明示「v3 spec full scope」拆 Sprint 5+ Wave 2 Phase 2 carry-over（per V101 spec §1.3 + V102 spec §8 carry-over table）。

**Lesson learned**：ADR / spec 設計 mode 與 dispatch 階段 mode 對齊驗 = PA 必做 sanity check；不對齊 = scope creep 或 scope shrink 必押 push back / negotiate decision。

---

# §10 完成回報

## 10.1 V101 spec path + LOC + ADD COLUMN 設計 + Guard 設計

- **路徑**：`srv/docs/execution_plan/specs/2026-05-23--v101-track-v3-attribution-column.md`
- **LOC**：~600 (spec doc) + ~250 SQL est
- **ADD COLUMN 設計**：CREATE TYPE strategy_track ENUM (direct_exploit/asds_factory/baseline) + ALTER TABLE trading.fills ADD COLUMN IF NOT EXISTS track strategy_track NULL + Batched UPDATE backfill (LIMIT 10000 + 100ms sleep loop) → 'baseline'
- **Guard A**：trading.fills exist + 15 baseline column 完整
- **Guard B**：track column type idempotency check
- **Guard C 後驗**：3 ENUM 值 + column 存在 + 0 NULL row backfill 100%

## 10.2 V102 spec path + LOC + indexes 設計 + NOT NULL handling 路徑

- **路徑**：`srv/docs/execution_plan/specs/2026-05-23--v102-track-v3-indexes-not-null.md`
- **LOC**：~640 (spec doc) + ~280 SQL est
- **indexes 設計**：2 indexes only - idx_fills_track_ts_v102 (track, ts DESC) + idx_fills_strategy_track_v102 (strategy_name, track)（CREATE INDEX IF NOT EXISTS, 非 CONCURRENTLY per sqlx migrate transaction 約束）
- **NOT NULL handling 路徑 3 options + PA verdict**：
  - **Option A** NULL allowed: NOT RECOMMENDED (fail-closed 弱)
  - **Option B** trigger + DEFAULT 'baseline' (PA STRONGLY RECOMMENDED): trigger BEFORE INSERT/UPDATE OF track + RAISE on NULL; DEFAULT 'baseline' 雙保險; columnstore-safe per V077 範式
  - **Option C** ALTER COLUMN SET NOT NULL: NOT RECOMMENDED (預期 RAISE feature_not_supported per V077 教訓)
- **Guard A**：V101 prerequisite verify (column exist + ENUM exist + 0 NULL)
- **Guard B**：DEFAULT + trigger idempotency check
- **Guard C 後驗**：2 index def + DEFAULT 'baseline' + trigger count = 1

## 10.3 4 AC + Sprint 5+ IMPL phase split + E1 IMPL est ~6-10 hr

- **7 AC**（V101 4 + V102 3）：見 §5.1
- **Sprint 5+ IMPL phase split**：見 §5.2
- **E1 IMPL est**：~3-4 hr V101 + ~3-4 hr V102 = ~6-8 hr E1；含 Sandbox + Production deploy + operator + PA = ~8-11 hr wall-clock
- **Sprint 5+ Wave 2 Phase 2 carry-over est**：~40-60 hr E1 + E2 + dispatch chain（其他 11 表 + 2 新表 + view + kill_events + Rust enum + writer fan-out）

## 10.4 dispatch readiness verdict + E2 重點 3 條

- **Dispatch Readiness Verdict**：**DISPATCH READY (OPEN)** — 8/8 前置條件 PASS；Risk grade 中（columnstore feature_not_supported constraint + trigger fallback path）；Confidence HIGH for V094/V077 範式對齊 + 8-11 hr budget；MEDIUM for ALTER SET DEFAULT columnstore 兼容（PA 預設 PASS 但未 sandbox empirical 驗）；LOW for v3 spec full 12-table scope completeness（本 spec 收緊 + carry-over）
- **E2 重點審查 3 條**：
  1. **E2-1**：columnstore hypertable trigger fallback path 對齊 V077 範式（不走 ALTER COLUMN SET NOT NULL）
  2. **E2-2**：scope 嚴守 trading.fills only — Sprint 5+ Wave 2 Phase 2 carry-over（不擴展至 11 表 + view + kill_events + Rust enum）
  3. **E2-3**：V101 backfill 100% verify + V102 Guard A V101 prerequisite verify（race window safeguard）

---

# §11 Scope 守邊界（task 期間）

per task prompt：

- ✅ 不 IMPL Rust / Python / SQL (E1 phase work)
- ✅ 不改 既有 V### / trading.fills schema
- ✅ 不 commit
- ✅ 不派下游 sub-agent
- ✅ 中文為主 / 0 emoji
- ✅ 0 code 改動；2 新 spec doc + 1 PA report

---

**PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_v101_v102_track_v3_attribution_design.md**

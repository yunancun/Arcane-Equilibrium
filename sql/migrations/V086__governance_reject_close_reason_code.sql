-- ============================================================
-- V086: W6-3c — governance reject_reason_code + close_reason_code
--   two TEXT column on learning.decision_features + 12/14 enum
--   NOT VALID CHECK + one-shot in-migration backfill
--   + trading.fills.strategy_name 17 row 雙前綴 normalize
--
-- 動機 / Motivation:
--   2026-05-10 W-AUDIT-4b 後續：reject reason 與 close reason 目前散落在
--     - trading.risk_verdicts.reason (free-form 字串, ~12.4M row)
--     - learning.decision_features.label_close_tag (free-form 字串, 9757 labeled row)
--   規範化為 enum 後 ML trainer 可直接 GROUP BY (reject_reason_code) /
--   (close_reason_code) 不需 post-hoc regex parse；同時為 multi-task ML
--   pipeline (N+2) 鋪 schema-level 路。
--
--   Spec source:
--     - PA W6-3b enum spec final (12 reject + 14 close enum)
--       docs/CCAgentWorkSpace/PA/workspace/reports/
--         2026-05-10--w6_3b_enum_spec_final_pa_decision.md
--     - MIT W6-3a close_tag distribution audit
--       docs/CCAgentWorkSpace/MIT/workspace/reports/
--         2026-05-10--w6_3a_close_tag_distribution_audit.md
--     - PA P2 雙前綴 RCA (17 row trading.fills + 16 row decision_features)
--       docs/CCAgentWorkSpace/PA/workspace/reports/
--         2026-05-10--p2_decision_features_double_prefix_bug_audit.md
--
-- 範圍 / Scope (V086):
--   1. ALTER TABLE learning.decision_features
--        ADD COLUMN reject_reason_code TEXT  (idempotent IF NOT EXISTS)
--        ADD COLUMN close_reason_code  TEXT  (idempotent IF NOT EXISTS)
--   2. NOT VALID CHECK constraint (12 reject + 14 close enum, 含 catch-all)
--      NOT VALID = 不掃 9757 historical row, 只對新 INSERT 強制；
--      D+2 14:30 UTC 再 ALTER VALIDATE CONSTRAINT 收緊。
--   3. One-shot in-migration backfill:
--      9757 row labeled rows 從 risk_verdicts.reason + label_close_tag
--      deterministic regex/exact mapping → enum value (~30-90 sec lock window)。
--   4. trading.fills.strategy_name 17 row 雙前綴 normalize:
--      `risk_close:risk_close:phys_lock_gate4_giveback*` → 單前綴版
--      （RUST-DOUBLE-PREFIX-1 fix `46a9cadc` 2026-04-23 13:54 已 land；
--        此 17 row 為 fix 前 9.3h 歷史污染；上游清理後下游 backfill
--        path 不再依賴雙前綴 case，未來 catch-all 可以更嚴）
--   5. Guard A/B/C 強制（schema_guard_template.sql 三層）+ idempotency。
--
-- 不變式 / Invariants:
--   - 既有 schema / column / view / writer 全保留；V086 純 forward-only
--     additive schema enhancement。
--   - reject_reason_code IS NULL ⇔ row 不是 governance reject path
--     (label_close_tag != 'rejected_governance')；close_reason_code IS NULL
--     ⇔ row 是 reject path (label_close_tag = 'rejected_governance')。
--     兩 column 互斥 by design。
--   - raw label_close_tag 欄位**不修改** (保留歷史 bug fingerprint, forensic
--     可追)；只在新 close_reason_code enum 欄位收 normalize 後值。
--   - trading.fills.strategy_name 17 row REPLACE 是上游清理 (PA P2 §4 Option A
--     point 3)；學習與 attribution 路徑下游 query 不變 (helper post-fix
--     `build_risk_close_tag()` 已 idempotent，上游字串 normalize 不破任何
--     reader)。
--   - NOT VALID CHECK 不掃 historical row, 只強制新 INSERT；validate timing
--     由 D+2 14:30 UTC 後續 migration / manual ALTER VALIDATE 處理 (PA spec
--     §4.5)。
--
-- Idempotency:
--   全 migration 重跑兩次必須 PASS：
--     - ADD COLUMN IF NOT EXISTS  → 第二次 no-op
--     - ADD CONSTRAINT (DO block guard) → 第二次發現已存在 skip
--     - UPDATE backfill SQL → 第二次 WHERE reason_code IS NULL filter
--       匹配 0 row no-op
--     - REPLACE trading.fills.strategy_name → 第二次 WHERE LIKE 'risk_close:
--       risk_close:%' 匹配 0 row no-op
--
-- E2 review checklist:
--   1. Guard A 命中 V017 schema (decision_features.label_close_tag 必存在)？
--   2. Guard B 命中 close_reason_code/reject_reason_code 型別 (text)？
--   3. Guard C trading.fills.strategy_name 屬性對嗎？(此 column 是 V003 既存)
--   4. backfill SQL CASE WHEN 順序：ATR unavailable 必先於 JS-demo / cost_gate_other,
--      雙前綴必先於單前綴, bare-name exact 必先於 prefix regex
--      (per PA W6-3b §6 高風險 #1)
--   5. NOT VALID enum list 完整 12 reject + 14 close (per PA spec §4.3)
--   6. Producer dual-write race 提醒 (PA spec §6 #3)：V086 land 與 producer
--      dual-write code deploy 時間差 <5 min；E2 必驗 deployment runbook 含
--      atomic deploy step
--
-- D+1 IMPL 補丁餘地：
--   本 file 為 sign-off 前 SQL skeleton 預寫；D+1 W6-3c E1 IMPL 階段預期
--   可能微調：
--     - constraint name (chk_reject_reason_code_enum / chk_close_reason_code_enum)
--       命名是否對齊 V083/V084 既有 pattern
--     - backfill UPDATE 是否拆分 reject path / close path 兩階段（lock 短化）
--     - Linux PG dry-run 9757 row backfill 實測 timing 後決 lock window 是否需
--       advisory lock 保護
-- ============================================================

BEGIN;

-- ============================================================
-- Guard A: learning.decision_features 表必須存在且含 label_close_tag column
-- Guard A: learning.decision_features must exist with label_close_tag column
-- 對齊 V017 (label_close_tag 加入點)
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='decision_features'
    ) THEN
        RAISE EXCEPTION
            'V086 Guard A FAIL: learning.decision_features missing — '
            'V017 must have applied first.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY['context_id', 'label_close_tag']) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='decision_features'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V086 Guard A FAIL: learning.decision_features missing required columns: %. '
            'V017 schema must align before V086.',
            v_missing;
    END IF;
END $$;

-- ============================================================
-- Guard A2: trading.fills 表必須存在且含 strategy_name column
-- Guard A2: trading.fills must exist with strategy_name column
-- (V086 §6 對 17 row 上游清理需要)
-- 對齊 V003 (基礎 schema)
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='trading' AND table_name='fills'
    ) THEN
        RAISE EXCEPTION
            'V086 Guard A2 FAIL: trading.fills missing — '
            'V003 must have applied first.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY['strategy_name', 'ts', 'fill_id']) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='trading' AND table_name='fills'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V086 Guard A2 FAIL: trading.fills missing required columns: %. '
            'V003 schema must align before V086.',
            v_missing;
    END IF;
END $$;

-- ============================================================
-- Guard A3: trading.risk_verdicts 表必須存在且含 reason + context_id column
-- Guard A3: trading.risk_verdicts must exist with reason + context_id column
-- (backfill SQL JOIN 來源)
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='trading' AND table_name='risk_verdicts'
    ) THEN
        RAISE EXCEPTION
            'V086 Guard A3 FAIL: trading.risk_verdicts missing — '
            'V003 / V004 must have applied first.';
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY['reason', 'context_id']) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='trading' AND table_name='risk_verdicts'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V086 Guard A3 FAIL: trading.risk_verdicts missing required columns: %. ',
            v_missing;
    END IF;
END $$;

-- ============================================================
-- §3 ALTER TABLE ADD COLUMN (idempotent)
-- 兩 column 加在 learning.decision_features
-- 不是 jsonb (per PA spec §4.1)：query-friendly indexed 直接走 text PK comparison；
-- ML pipeline 直接 WHERE reject_reason_code = '...' 不需 jsonb operator
-- ============================================================
ALTER TABLE learning.decision_features
    ADD COLUMN IF NOT EXISTS reject_reason_code TEXT,
    ADD COLUMN IF NOT EXISTS close_reason_code  TEXT;

-- ============================================================
-- Guard B: 兩 column 加成功後驗證 data_type = 'text'
-- (idempotent: 若 column 不存在 v_actual = NULL 會 silent skip RAISE)
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='decision_features'
      AND column_name='reject_reason_code';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'V086 Guard B FAIL: learning.decision_features.reject_reason_code '
            'is %, expected text. Type drift detected.',
            v_actual;
    END IF;

    SELECT data_type INTO v_actual
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='decision_features'
      AND column_name='close_reason_code';
    IF v_actual IS NOT NULL AND v_actual <> 'text' THEN
        RAISE EXCEPTION
            'V086 Guard B FAIL: learning.decision_features.close_reason_code '
            'is %, expected text. Type drift detected.',
            v_actual;
    END IF;
END $$;

-- ============================================================
-- §4 NOT VALID CHECK constraint
-- 12 reject enum (11 + 1 catch-all `reject_other`)
-- 14 close enum (13 + 1 catch-all `close_other`)
-- per PA W6-3b spec final §2 + §3
-- NOT VALID = 不掃 9757 historical row, 只對新 INSERT 強制
-- D+2 14:30 UTC 後續 ALTER VALIDATE CONSTRAINT 收緊（lock window <30 sec）
-- ============================================================
DO $$
BEGIN
    -- chk_reject_reason_code_enum: 12 enum (11 + reject_other catch-all)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'learning'
          AND t.relname = 'decision_features'
          AND c.conname = 'chk_reject_reason_code_enum'
    ) THEN
        ALTER TABLE learning.decision_features
            ADD CONSTRAINT chk_reject_reason_code_enum CHECK (
                reject_reason_code IS NULL OR reject_reason_code IN (
                    'cost_gate_js_demo_negative_edge',
                    'cost_gate_atr_unavailable',
                    'cost_gate_other',
                    'duplicate_position',
                    'direction_conflict',
                    'position_count_limit',
                    'scanner_market_gate',
                    'scanner_opportunity_canary',
                    'drawdown_breach',
                    'symbol_blocklist',
                    'risk_gate_other',
                    'reject_other'
                )
            ) NOT VALID;
    END IF;

    -- chk_close_reason_code_enum: 14 enum (13 + close_other catch-all)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'learning'
          AND t.relname = 'decision_features'
          AND c.conname = 'chk_close_reason_code_enum'
    ) THEN
        ALTER TABLE learning.decision_features
            ADD CONSTRAINT chk_close_reason_code_enum CHECK (
                close_reason_code IS NULL OR close_reason_code IN (
                    'strategy_close_grid',
                    'strategy_close_ma',
                    'strategy_close_bb',
                    'strategy_close_funding_arb',
                    'strategy_close_regime_shift',
                    'strategy_close_legacy_bare_name',
                    'risk_close_phys_lock_gate4_giveback',
                    'risk_close_phys_lock_gate4_stale',
                    'risk_close_cost_edge',
                    'risk_close_fast_track',
                    'risk_close_trailing_stop',
                    'risk_close_dynamic_stop',
                    'ipc_close_all',
                    'close_other'
                )
            ) NOT VALID;
    END IF;
END $$;

-- ============================================================
-- §5 Backfill SQL (one-shot, in-migration, ~30-90 sec)
-- 對 9757 labeled row deterministic regex/exact mapping
-- per PA W6-3b spec final §4.4
--
-- evaluation order critical (per PA §6 #1 高風險):
--   reject path:
--     ATR unavailable 必先於 JS-demo / cost_gate_other
--   close path:
--     bare-name exact match 必先於 prefix regex
--     雙前綴必先於單前綴
--   catch-all (reject_other / close_other) 必 ELSE 兜底
--
-- WHERE filter:
--   只 update reason_code IS NULL 的 row → idempotent (重跑 0 row)
--   AND label_close_tag IS NOT NULL → 只動 labeled row (post-V017 backfill)
-- ============================================================
UPDATE learning.decision_features df
SET reject_reason_code = CASE
    -- Reject path: 只對 rejected_governance row 寫；非 reject row → NULL (互斥不變式)
    WHEN df.label_close_tag != 'rejected_governance' THEN NULL
    -- evaluation order: ATR unavailable 必先於 JS-demo / cost_gate_other
    WHEN rv.reason ~ 'cost_gate.*ATR unavailable' THEN 'cost_gate_atr_unavailable'
    WHEN rv.reason LIKE 'cost_gate(JS-demo)%' THEN 'cost_gate_js_demo_negative_edge'
    WHEN rv.reason LIKE 'cost_gate%' THEN 'cost_gate_other'
    WHEN rv.reason LIKE 'duplicate_position%' THEN 'duplicate_position'
    WHEN rv.reason LIKE 'direction_conflict%' THEN 'direction_conflict'
    WHEN rv.reason LIKE 'position_count%' THEN 'position_count_limit'
    WHEN rv.reason LIKE 'scanner_market_gate%' THEN 'scanner_market_gate'
    WHEN rv.reason LIKE 'scanner_opportunity_canary%' THEN 'scanner_opportunity_canary'
    WHEN rv.reason LIKE 'drawdown_breach%' THEN 'drawdown_breach'
    WHEN rv.reason ~ 'blocked by per_strategy\.\w+\.blocked_symbols' THEN 'symbol_blocklist'
    WHEN rv.reason LIKE 'risk_gate%' THEN 'risk_gate_other'
    -- catch-all: 殘餘 → reject_other
    ELSE 'reject_other'
END,
close_reason_code = CASE
    -- Close path: rejected_governance row → NULL (互斥不變式)
    WHEN df.label_close_tag = 'rejected_governance' THEN NULL
    -- bare strategy name (W-AUDIT-4b M2 約定): exact match 必先於 prefix regex
    WHEN df.label_close_tag IN (
        'grid_trading',
        'ma_crossover',
        'bb_breakout',
        'bb_reversion',
        'funding_arb'
    ) THEN 'strategy_close_legacy_bare_name'
    -- strategy close path: prefix regex
    WHEN df.label_close_tag LIKE 'strategy_close:grid_close%' THEN 'strategy_close_grid'
    WHEN df.label_close_tag LIKE 'strategy_close:ma_%' THEN 'strategy_close_ma'
    WHEN df.label_close_tag LIKE 'strategy_close:bb_%' THEN 'strategy_close_bb'
    WHEN df.label_close_tag LIKE 'strategy_close:funding_arb_exit%' THEN 'strategy_close_funding_arb'
    WHEN df.label_close_tag = 'strategy_close:regime_shift' THEN 'strategy_close_regime_shift'
    -- risk close path: 雙前綴必先於單前綴 (16 row 歷史污染 normalize, RUST-DOUBLE-PREFIX-1
    -- fix 46a9cadc 2026-04-23 13:54 已 land; 此 case 收 fix 前 9 hours raw 字串)
    WHEN df.label_close_tag LIKE 'risk_close:risk_close:phys_lock_gate4_giveback%'
        THEN 'risk_close_phys_lock_gate4_giveback'
    WHEN df.label_close_tag LIKE 'risk_close:phys_lock_gate4_giveback%'
        THEN 'risk_close_phys_lock_gate4_giveback'
    WHEN df.label_close_tag LIKE 'risk_close:phys_lock_gate4_stale%'
        THEN 'risk_close_phys_lock_gate4_stale'
    WHEN df.label_close_tag LIKE 'risk_close:COST EDGE%' THEN 'risk_close_cost_edge'
    WHEN df.label_close_tag LIKE 'risk_close:fast_track%' THEN 'risk_close_fast_track'
    WHEN df.label_close_tag LIKE 'risk_close:TRAILING STOP%' THEN 'risk_close_trailing_stop'
    WHEN df.label_close_tag LIKE 'risk_close:DYNAMIC STOP%' THEN 'risk_close_dynamic_stop'
    -- IPC close path: exact match
    WHEN df.label_close_tag = 'ipc_close_all' THEN 'ipc_close_all'
    -- catch-all: 殘餘 → close_other
    ELSE 'close_other'
END
FROM trading.risk_verdicts rv
WHERE df.context_id = rv.context_id
  AND df.label_close_tag IS NOT NULL
  -- idempotency: 第二次跑時兩 column 已 NOT NULL → WHERE filter 0 row no-op
  AND (df.reject_reason_code IS NULL OR df.close_reason_code IS NULL);

-- ============================================================
-- §6 trading.fills.strategy_name 17 row 雙前綴 normalize (上游清理)
-- per PA P2 RCA §4 Option A point 3
--
-- Source RCA: RUST-DOUBLE-PREFIX-1 fix `46a9cadc` 2026-04-23 13:54 已 land
-- (build_risk_close_tag() helper idempotent prefix check); 此 17 row 為
-- fix 前 9.3 hours pre-fix-commit 歷史污染 (PENGUUSDT volatility spike,
-- demo only)
--
-- 注意: trading.fills 沒有 label_close_tag column (per V003 schema);
-- 真 source 是 trading.fills.strategy_name (line 282 V003)
-- (Python edge_label_backfill.py:285 從此 column 複製字串到
--  learning.decision_features.label_close_tag)
--
-- Idempotency: WHERE LIKE 'risk_close:risk_close:%' filter 第二次 0 row no-op
-- Lock window: <1 sec on 17 row, 安全
-- ============================================================
UPDATE trading.fills
SET strategy_name = REPLACE(
    strategy_name,
    'risk_close:risk_close:',
    'risk_close:'
)
WHERE strategy_name LIKE 'risk_close:risk_close:%';

-- ============================================================
-- §7 Guard C: post-backfill 驗證 (idempotent: 全 0 row 即 PASS)
-- ============================================================
DO $$
DECLARE
    v_unmapped_reject  BIGINT;
    v_unmapped_close   BIGINT;
    v_remaining_double BIGINT;
BEGIN
    -- Check 1: 所有 rejected_governance row 必有 reject_reason_code
    SELECT COUNT(*) INTO v_unmapped_reject
    FROM learning.decision_features
    WHERE label_close_tag = 'rejected_governance'
      AND reject_reason_code IS NULL;
    IF v_unmapped_reject > 0 THEN
        RAISE EXCEPTION
            'V086 Guard C FAIL: % rejected_governance row(s) missing '
            'reject_reason_code after backfill. Backfill SQL CASE WHEN '
            'evaluation order or risk_verdicts JOIN may be wrong.',
            v_unmapped_reject;
    END IF;

    -- Check 2: 所有 labeled non-reject row 必有 close_reason_code
    SELECT COUNT(*) INTO v_unmapped_close
    FROM learning.decision_features
    WHERE label_close_tag IS NOT NULL
      AND label_close_tag != 'rejected_governance'
      AND close_reason_code IS NULL;
    IF v_unmapped_close > 0 THEN
        RAISE EXCEPTION
            'V086 Guard C FAIL: % labeled non-reject row(s) missing '
            'close_reason_code after backfill. Backfill SQL CASE WHEN '
            'evaluation order may be wrong.',
            v_unmapped_close;
    END IF;

    -- Check 3: trading.fills.strategy_name 雙前綴必清零
    SELECT COUNT(*) INTO v_remaining_double
    FROM trading.fills
    WHERE strategy_name LIKE 'risk_close:risk_close:%';
    IF v_remaining_double > 0 THEN
        RAISE EXCEPTION
            'V086 Guard C FAIL: % trading.fills row(s) still have double '
            'risk_close: prefix after REPLACE. Upstream cleanup failed.',
            v_remaining_double;
    END IF;

    RAISE NOTICE 'V086 Guard C PASS: 0 unmapped reject row, 0 unmapped close '
                 'row, 0 trading.fills double-prefix row.';
END $$;

-- ============================================================
-- §8 COMMENT 與註解 (idempotent: COMMENT ON 可重跑)
-- ============================================================
COMMENT ON COLUMN learning.decision_features.reject_reason_code IS
    'W6-3c governance reject reason enum (12 enum, 11 + reject_other catch-all). '
    'NULL ⇔ row 不是 governance reject path. '
    'Source: trading.risk_verdicts.reason regex/exact mapping. '
    'NOT VALID CHECK constraint (D+2 14:30 UTC ALTER VALIDATE).';

COMMENT ON COLUMN learning.decision_features.close_reason_code IS
    'W6-3c position close reason enum (14 enum, 13 + close_other catch-all). '
    'NULL ⇔ row 是 governance reject path. '
    'Source: label_close_tag regex/exact mapping. '
    'NOT VALID CHECK constraint (D+2 14:30 UTC ALTER VALIDATE).';

COMMIT;

-- ============================================================
-- §9 Final NOTICE (in transaction-end NOTICE for operator runbook)
-- 注意: COMMIT 之後的 RAISE NOTICE 需在獨立 DO block (PG 限制)
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE 'V086 land complete:';
    RAISE NOTICE '  - reject_reason_code + close_reason_code two TEXT column added on learning.decision_features';
    RAISE NOTICE '  - 12 reject enum + 14 close enum NOT VALID CHECK constraint';
    RAISE NOTICE '  - One-shot in-migration backfill on 9757 labeled rows';
    RAISE NOTICE '  - trading.fills.strategy_name 17 row double-prefix normalize';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  - D+1 evening: producer dual-write deploy (Rust step_4_5_dispatch + step_6_risk_checks)';
    RAISE NOTICE '  - D+2 14:00 UTC: 24h dual-write drift healthcheck PASS verification';
    RAISE NOTICE '  - D+2 14:30 UTC: ALTER TABLE ... VALIDATE CONSTRAINT chk_reject_reason_code_enum + chk_close_reason_code_enum';
END $$;

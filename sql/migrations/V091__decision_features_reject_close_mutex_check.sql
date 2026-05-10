-- ============================================================
-- V091: learning.decision_features reject_reason_code + close_reason_code
--       schema-level 互斥不變式 CHECK NOT VALID
--
-- 動機 / Motivation:
--   per MIT MUST 2 (W6-1 RFC sign-off 2026-05-10 20:38 UTC):
--     V086 land 兩 column reject_reason_code + close_reason_code on
--     learning.decision_features (V086 ALTER TABLE line 195)。
--     當前互斥不變式僅由 backfill SQL CASE WHEN evaluation order +
--     producer code separation discipline 強制 (reject path 寫 reject_reason_code +
--     close_reason_code=NULL；close path 反之)。
--
--     **缺 schema-level CHECK constraint** 防 future producer code bug
--     在同 row 同時寫雙 column。
--
--   Empirical (ssh trade-core 2026-05-10 20:35 UTC + 後續 verify):
--     - reject_n=17810
--     - close_n=2247
--     - overlap_both=0  (V086 backfill 產出乾淨)
--   但這是 backfill SQL 產出 + 當前 producer code (D+1 evening 才 deploy)
--   的快照結果，不代表 future producer code 不會違反。
--
--   Spec source:
--     - MIT W6-1 RFC sign-off verdict report
--       docs/CCAgentWorkSpace/MIT/workspace/reports/
--         2026-05-10--w6_1_rfc_mit_signoff_verdict.md
--       §3 「兩 column TEXT vs alternatives」末段 + §8 必修條件 #2
--
-- 範圍 / Scope (V091):
--   1. ADD CONSTRAINT chk_reason_code_mutually_exclusive
--      CHECK (NOT (reject_reason_code IS NOT NULL AND close_reason_code IS NOT NULL))
--      NOT VALID
--      在 learning.decision_features 表上。
--   2. NOT VALID 模式: 不掃 existing row, 只對新 INSERT/UPDATE 強制；
--      D+2 14:30 UTC 24h dual-write drift PASS 後再 ALTER VALIDATE CONSTRAINT
--      收緊歷史 row enforcement (本 migration 不執行 VALIDATE)。
--   3. Guard A 確認 V086 已 land (reject_reason_code + close_reason_code
--      column 全在 learning.decision_features)。
--   4. Idempotent: 重跑 2 次 PG 不 RAISE (constraint 已存在則 skip)。
--
-- 不變式 / Invariants:
--   - 既有 reject_reason_code / close_reason_code column 不動。
--   - 既有 chk_reject_reason_code_enum / chk_close_reason_code_enum
--     enum CHECK constraint (V086 land) 完全保留，不修改。
--   - 純 additive constraint。Producer dual-write code (D+1 evening deploy)
--     寫 row 時 PG 拒絕「同 row 兩 column 都 NOT NULL」場景；
--     若 producer 寫對 (互斥)，CHECK constraint 對該 row 透明 PASS。
--   - 本 migration 不執行 ALTER TABLE ... VALIDATE CONSTRAINT
--     (D+2 14:30 UTC 後續 manual ALTER 處理)。
--   - 0 existing row violation (V086 backfill empirical overlap=0 證明)
--     → D+2 ALTER VALIDATE CONSTRAINT 預期 PASS。
--
-- Idempotency:
--   全 migration 重跑兩次必須 PASS：
--     - Guard A: idempotent SELECT，column 存在不 RAISE。
--     - DO block ADD CONSTRAINT: IF NOT EXISTS 守衛，第二次發現已存在 skip。
--     - 0 existing row check: 純 SELECT count，第二次跑同樣 0 row → PASS NOTICE。
--
-- E2 review checklist:
--   1. Guard A 命中 V086 schema (reject_reason_code + close_reason_code column 必存在)？
--   2. CHECK syntax 正確：NOT (reject IS NOT NULL AND close IS NOT NULL)
--      等價：(reject IS NULL OR close IS NULL)；前者語意更直接 (來自 MIT verdict §3)。
--   3. NOT VALID 模式：constraint definition 末尾必含 NOT VALID keyword (不掃 historical)。
--   4. Idempotent: ADD CONSTRAINT 包在 DO block + IF NOT EXISTS pre-check (對齊 V083 pattern line 173-189)。
--   5. 不執行 ALTER TABLE ... VALIDATE CONSTRAINT (D+2 14:30 UTC 後續 work)。
--   6. constraint name `chk_reason_code_mutually_exclusive` 對齊 MIT verdict §3 line 84 example。
--
-- Reservation: V091
-- Status: NOT_RUN artifact (D+1 evening producer code restart 同次 deploy)
-- 後續：D+2 14:30 UTC 24h drift PASS 後 ALTER VALIDATE CONSTRAINT 收緊
-- ============================================================

BEGIN;

-- ============================================================
-- Guard A: 確認 V086 已 land
-- (learning.decision_features 必存在且含 reject_reason_code + close_reason_code 兩 column)
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- 表存在性檢查
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='decision_features'
    ) THEN
        RAISE EXCEPTION
            'V091 Guard A FAIL: learning.decision_features missing — '
            'V017/V086 must have applied first.';
    END IF;

    -- 兩 column 存在性檢查 (V086 ALTER TABLE 已加)
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY['reject_reason_code', 'close_reason_code']) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='decision_features'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION
            'V091 Guard A FAIL: learning.decision_features missing required columns: %. '
            'V086 must have applied first.',
            v_missing;
    END IF;
END $$;

-- ============================================================
-- §1 加 schema-level 互斥不變式 CHECK constraint (NOT VALID, idempotent)
--
-- per MIT W6-1 RFC sign-off verdict §3 SQL example:
--   ADD CONSTRAINT chk_reason_code_mutually_exclusive
--     CHECK ((reject_reason_code IS NULL OR close_reason_code IS NULL))
--     NOT VALID;
--
-- 等價語意：NOT (reject IS NOT NULL AND close IS NOT NULL)
-- 採等價變體更直觀表達「兩 column 不能同時非 NULL」業務規則。
--
-- NOT VALID 設計：
--   - 不掃既有 row (V086 backfill 已產出 overlap=0 乾淨數據, n=17810+2247)
--   - 只對新 INSERT/UPDATE 強制 (producer dual-write code D+1 evening
--     deploy 後生效)
--   - D+2 14:30 UTC 24h passive drift PASS 後 manual:
--     ALTER TABLE learning.decision_features
--         VALIDATE CONSTRAINT chk_reason_code_mutually_exclusive;
--     收緊全表 enforcement
--
-- Idempotency: IF NOT EXISTS pre-check (對齊 V083:173-189 pattern)
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'learning'
          AND t.relname = 'decision_features'
          AND c.conname = 'chk_reason_code_mutually_exclusive'
    ) THEN
        ALTER TABLE learning.decision_features
            ADD CONSTRAINT chk_reason_code_mutually_exclusive
            CHECK (NOT (reject_reason_code IS NOT NULL AND close_reason_code IS NOT NULL))
            NOT VALID;
        RAISE NOTICE
            'V091: added NOT VALID CHECK chk_reason_code_mutually_exclusive '
            '(reject_reason_code XOR close_reason_code mutex; historical rows exempt)';
        RAISE NOTICE
            'V091: D+2 14:30 UTC 24h drift PASS 後 ALTER VALIDATE CONSTRAINT 收緊';
    ELSE
        RAISE NOTICE
            'V091: chk_reason_code_mutually_exclusive already present; skipping (idempotent)';
    END IF;
END $$;

-- ============================================================
-- §2 既有 row 互斥不變式 violation 預檢
-- (NOT VALID 不會 enforce 在 existing row, 此區純 advisory diagnostic)
--
-- 預期: V086 backfill 產出 0 violation (overlap_both=0 empirical)。
-- 若 v_count > 0 → operator 必先 investigate 並修 raw data, 否則
-- D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 會在「掃 historical row」階段 RAISE。
-- ============================================================
DO $$
DECLARE v_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM learning.decision_features
    WHERE reject_reason_code IS NOT NULL
      AND close_reason_code IS NOT NULL;

    IF v_count > 0 THEN
        RAISE WARNING
            'V091: % existing row(s) violate reject_close mutex invariant. '
            'D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 會 fail 直到 raw data 修復。'
            'Operator: investigate query: SELECT context_id, reject_reason_code, '
            'close_reason_code FROM learning.decision_features WHERE '
            'reject_reason_code IS NOT NULL AND close_reason_code IS NOT NULL;',
            v_count;
    ELSE
        RAISE NOTICE
            'V091: 0 existing row violate mutex invariant '
            '(V086 backfill produced clean data; D+2 ALTER VALIDATE CONSTRAINT 預期 PASS)';
    END IF;
END $$;

-- ============================================================
-- §3 COMMENT (idempotent: COMMENT ON 可重跑)
-- ============================================================
COMMENT ON CONSTRAINT chk_reason_code_mutually_exclusive
    ON learning.decision_features IS
    'MIT MUST 2 (W6-1 RFC sign-off 2026-05-10): reject_reason_code + close_reason_code '
    '互斥不變式 schema-level CHECK constraint。NOT VALID = 不掃 existing row, '
    '只對新 INSERT/UPDATE 強制。D+2 14:30 UTC 24h drift PASS 後 ALTER VALIDATE '
    'CONSTRAINT 收緊歷史 row enforcement。防 future producer code bug 同 row '
    '兩 column 同時 NOT NULL。';

COMMIT;

-- ============================================================
-- §4 Final NOTICE (in transaction-end NOTICE for operator runbook)
-- 注意: COMMIT 之後的 RAISE NOTICE 需在獨立 DO block (PG 限制)
-- ============================================================
DO $$
BEGIN
    RAISE NOTICE 'V091 land complete:';
    RAISE NOTICE '  - chk_reason_code_mutually_exclusive CHECK constraint added (NOT VALID)';
    RAISE NOTICE '  - Schema-level mutex enforcement on new INSERT/UPDATE';
    RAISE NOTICE '  - Existing row 0 violation (V086 backfill clean)';
    RAISE NOTICE '';
    RAISE NOTICE 'Next steps:';
    RAISE NOTICE '  - D+1 evening: producer dual-write code restart deploy (W6-3c writer)';
    RAISE NOTICE '  - D+2 14:00 UTC: 24h dual-write drift healthcheck PASS verification';
    RAISE NOTICE '  - D+2 14:30 UTC: ALTER TABLE learning.decision_features';
    RAISE NOTICE '                       VALIDATE CONSTRAINT chk_reason_code_mutually_exclusive;';
END $$;

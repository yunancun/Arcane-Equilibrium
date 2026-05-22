-- ============================================================
-- V103: EXTEND M4 Hypothesis Discovery Columns (learning.hypotheses)
--
-- 用途:
--   對既有 learning.hypotheses 表 ADD 6 個 M4 Hypothesis Discovery 專用
--   column,涵蓋 source lineage / leakage detection / Bonferroni correction /
--   replicability / decision lease draft / cowork review state。本 EXTEND 為
--   Sprint 1A-γ M4 module DDL prerequisite (Gap I-A 補丁),屬第二組 EXTEND
--   (base V103 §14 audit field 第一組 EXTEND 不重疊)。
--   per V103 EXTEND M4 spec §2 + ADR-0045 M4 governance + ADR-0034 M1 LAL
--   UUID 模式。
--
-- 範圍:
--   - ALTER TABLE learning.hypotheses ADD COLUMN 6 條 (IF NOT EXISTS):
--     hypothesis_source_module TEXT (M4_AUTO/OPERATOR/HISTORIC enum) +
--     leakage_scan_pass BOOLEAN (fail-closed DEFAULT FALSE) +
--     bonferroni_corrected_p NUMERIC(10,8) (CHECK [0,1]) +
--     replicability_score NUMERIC(5,4) (CHECK [0,1]) +
--     decision_lease_draft_id UUID (FK placeholder) +
--     cowork_review_status TEXT (NONE/PENDING/APPROVED/REJECTED enum);
--   - 3 hot-path index CREATE IF NOT EXISTS:
--     idx_hypotheses_source_module / idx_hypotheses_leakage_pass /
--     idx_hypotheses_cowork_review (兩 partial);
--   - Guard A: base learning.hypotheses table 存在性 + hypothesis_id 必齊全;
--   - Guard B: 6 段 ADD COLUMN type/CHECK/DEFAULT mismatch 預檢
--     (per spec §3.1 + CLAUDE.md §Data 規範);
--   - Guard C: 重跑 idempotency post-check (3 index + 6 column 齊全)。
--
-- Parent specs:
--   docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md
--   docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md §10
--   docs/adr/0045-m4-hypothesis-discovery-governance.md
--   docs/adr/0034-decision-lease-layered-approval-lal.md (UUID 模式)
--   docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md
--   (PA-DRIFT-2 closure HARD BLOCKER)
--
-- 硬邊界:
--   - base table learning.hypotheses 必先存在 (Sprint 1A-α 已 land via stub or
--     production V### 路徑);Guard A 缺即 RAISE。
--   - leakage_scan_pass DEFAULT FALSE 是 fail-closed (per 根原則 #6):既有
--     row 未跑 leakage scan 預設 FALSE。
--   - hypothesis_source_module DEFAULT 'OPERATOR' (spec §2.2 Path A,MIT 推薦):
--     既有 row 100% 是 operator/Cowork 寫;backfill 'M4_AUTO' 會錯標 silent
--     contamination。M4 自動寫入路徑顯式設 'M4_AUTO'。
--   - decision_lease_draft_id UUID 對齊 ADR-0034 M1 Decision Lease UUID 模式;
--     FK 暫不加 — 待 V099/V100 lease tables land + PA 確認 FK target column
--     name 後由後續 EXTEND 加 REFERENCES。
--   - 本 EXTEND 6 column 與 base V103 §14 5 audit field 不重疊 (per spec §1.2)。
-- ============================================================

-- ============================================================
-- Guard A: base table learning.hypotheses 存在性 + hypothesis_id 必齊全
-- Guard A: 基表存在性與 PK column 完整性
-- ============================================================
DO $$
BEGIN
    -- base table 必存在 (Sprint 1A-α via stub or production V### 路徑已 land)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='hypotheses'
    ) THEN
        RAISE EXCEPTION
            'V103 Guard A FAIL: learning.hypotheses table 不存在 — '
            'Sprint 1A-γ M4 base table 必先 land (per E3 v58 audit §2 row 2 + '
            'E1 Track C 2026-05-22 stub IMPL #2)。';
    END IF;

    -- hypothesis_id PK column 必存在 (M4 EXTEND 需依此為 FK target backref)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='hypotheses'
          AND column_name='hypothesis_id'
    ) THEN
        RAISE EXCEPTION
            'V103 Guard A FAIL: learning.hypotheses.hypothesis_id 缺 — '
            'base V103 not yet fully applied; M4 EXTEND 依 hypothesis_id '
            'PK 為 backref target。';
    END IF;
END $$;

-- ============================================================
-- Guard B: 6 段 ADD COLUMN type/CHECK/DEFAULT mismatch 預檢
-- Guard B: 預檢既有 column drift (type/CHECK/DEFAULT) — fail-loud on conflict
--
-- 每段在「column 已存在」情境下驗 type/CHECK/DEFAULT 對齊 spec §2.1;
-- 首次 apply (column 不存在) 全 skip → idempotent。
-- 重跑時若 type 不對 → RAISE EXCEPTION (對齊 spec §3.2 觸發場景)。
-- ============================================================
DO $$
DECLARE
    v_col_type TEXT;
    v_col_default TEXT;
    v_check_def TEXT;
BEGIN
    -- Guard B-1: hypothesis_source_module type=text + CHECK enum
    SELECT data_type, column_default INTO v_col_type, v_col_default
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses'
      AND column_name='hypothesis_source_module';
    IF v_col_type IS NOT NULL AND v_col_type <> 'text' THEN
        RAISE EXCEPTION
            'V103 Guard B-1 FAIL: hypothesis_source_module type=% (expected text)。'
            'Resolve schema drift before re-apply.', v_col_type;
    END IF;
    IF v_col_type = 'text' AND v_col_default IS NOT NULL
       AND position('OPERATOR' IN v_col_default) = 0
       AND position('M4_AUTO' IN v_col_default) = 0
       AND position('HISTORIC' IN v_col_default) = 0 THEN
        RAISE EXCEPTION
            'V103 Guard B-1 FAIL: hypothesis_source_module DEFAULT=% '
            '(expected one of OPERATOR/M4_AUTO/HISTORIC per spec §2.1)。',
            v_col_default;
    END IF;

    -- Guard B-2: leakage_scan_pass type=boolean + DEFAULT must be FALSE (fail-closed)
    SELECT data_type, column_default INTO v_col_type, v_col_default
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses'
      AND column_name='leakage_scan_pass';
    IF v_col_type IS NOT NULL AND v_col_type <> 'boolean' THEN
        RAISE EXCEPTION
            'V103 Guard B-2 FAIL: leakage_scan_pass type=% (expected boolean)。',
            v_col_type;
    END IF;
    IF v_col_type = 'boolean' AND v_col_default IS NOT NULL
       AND position('false' IN lower(v_col_default)) = 0 THEN
        RAISE EXCEPTION
            'V103 Guard B-2 FAIL: leakage_scan_pass DEFAULT=% (expected FALSE '
            'for fail-closed per 根原則 #6)。', v_col_default;
    END IF;

    -- Guard B-3: bonferroni_corrected_p type=numeric + CHECK [0,1] 範圍
    SELECT data_type INTO v_col_type
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses'
      AND column_name='bonferroni_corrected_p';
    IF v_col_type IS NOT NULL AND v_col_type <> 'numeric' THEN
        RAISE EXCEPTION
            'V103 Guard B-3 FAIL: bonferroni_corrected_p type=% (expected numeric)。',
            v_col_type;
    END IF;

    -- Guard B-4: replicability_score type=numeric + CHECK [0,1] 範圍
    SELECT data_type INTO v_col_type
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses'
      AND column_name='replicability_score';
    IF v_col_type IS NOT NULL AND v_col_type <> 'numeric' THEN
        RAISE EXCEPTION
            'V103 Guard B-4 FAIL: replicability_score type=% (expected numeric)。',
            v_col_type;
    END IF;

    -- Guard B-5: decision_lease_draft_id type=uuid (對齊 ADR-0034)
    SELECT data_type INTO v_col_type
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses'
      AND column_name='decision_lease_draft_id';
    IF v_col_type IS NOT NULL AND v_col_type <> 'uuid' THEN
        RAISE EXCEPTION
            'V103 Guard B-5 FAIL: decision_lease_draft_id type=% (expected uuid '
            'per ADR-0034 M1 LAL UUID 模式)。', v_col_type;
    END IF;

    -- Guard B-6: cowork_review_status type=text + DEFAULT 'NONE'
    SELECT data_type, column_default INTO v_col_type, v_col_default
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses'
      AND column_name='cowork_review_status';
    IF v_col_type IS NOT NULL AND v_col_type <> 'text' THEN
        RAISE EXCEPTION
            'V103 Guard B-6 FAIL: cowork_review_status type=% (expected text)。',
            v_col_type;
    END IF;
    IF v_col_type = 'text' AND v_col_default IS NOT NULL
       AND position('NONE' IN v_col_default) = 0
       AND position('PENDING' IN v_col_default) = 0
       AND position('APPROVED' IN v_col_default) = 0
       AND position('REJECTED' IN v_col_default) = 0 THEN
        RAISE EXCEPTION
            'V103 Guard B-6 FAIL: cowork_review_status DEFAULT=% '
            '(expected one of NONE/PENDING/APPROVED/REJECTED per spec §2.1)。',
            v_col_default;
    END IF;
END $$;

-- ============================================================
-- Main DDL: ALTER TABLE ADD COLUMN 6 條 (per spec §2.1)
-- 主 DDL: 對 learning.hypotheses ADD 6 column
--
-- 每條走 IF NOT EXISTS idempotent path:
-- - hypothesis_source_module: TEXT NOT NULL DEFAULT 'OPERATOR'
--   + CHECK 3-enum (M4_AUTO/OPERATOR/HISTORIC);
-- - leakage_scan_pass: BOOLEAN NOT NULL DEFAULT FALSE (fail-closed);
-- - bonferroni_corrected_p: NUMERIC(10,8) NULL + CHECK [0,1];
-- - replicability_score: NUMERIC(5,4) NULL + CHECK [0,1];
-- - decision_lease_draft_id: UUID NULL (FK placeholder — 待 V099/V100 land);
-- - cowork_review_status: TEXT NOT NULL DEFAULT 'NONE' + CHECK 4-enum
--   (NONE/PENDING/APPROVED/REJECTED)。
--
-- 既有 row backfill DEFAULT 邏輯 (per spec §2.2):
-- - hypothesis_source_module → 'OPERATOR' (Path A; 既有 row 100% operator-source)
-- - leakage_scan_pass → FALSE (fail-closed)
-- - bonferroni_corrected_p / replicability_score → NULL (未跑 statistical engine)
-- - decision_lease_draft_id → NULL (尚未綁定 lease)
-- - cowork_review_status → 'NONE' (Y2 啟用前無 review state)
-- ============================================================

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS hypothesis_source_module TEXT
        NOT NULL DEFAULT 'OPERATOR'
        CHECK (hypothesis_source_module IN ('M4_AUTO', 'OPERATOR', 'HISTORIC'));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS leakage_scan_pass BOOLEAN
        NOT NULL DEFAULT FALSE;

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS bonferroni_corrected_p NUMERIC(10, 8)
        CHECK (bonferroni_corrected_p IS NULL
               OR (bonferroni_corrected_p >= 0 AND bonferroni_corrected_p <= 1));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS replicability_score NUMERIC(5, 4)
        CHECK (replicability_score IS NULL
               OR (replicability_score >= 0 AND replicability_score <= 1));

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS decision_lease_draft_id UUID;
    -- FK 暫不加;待 V099/V100 lease tables land + PA 確認 FK target column
    -- name 後由後續 EXTEND 加 REFERENCES governance.decision_lease(lease_id)

ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS cowork_review_status TEXT
        NOT NULL DEFAULT 'NONE'
        CHECK (cowork_review_status IN ('NONE', 'PENDING', 'APPROVED', 'REJECTED'));

-- ============================================================
-- Column COMMENT annotations (per spec §2.2)
-- Column 注解 (M4 lineage / statistical / governance 語意)
-- ============================================================
COMMENT ON COLUMN learning.hypotheses.hypothesis_source_module IS
    'M4 hypothesis discovery — source module identifier (M4_AUTO/OPERATOR/HISTORIC); per spec §2.2 既有 row DEFAULT OPERATOR';
COMMENT ON COLUMN learning.hypotheses.leakage_scan_pass IS
    'M4 leakage detection scan pass/fail (fail-closed DEFAULT FALSE 對齊 根原則 #6)';
COMMENT ON COLUMN learning.hypotheses.bonferroni_corrected_p IS
    'M4 Bonferroni multiple comparison correction p-value (K=2500 × 5 window scenario; range [0,1])';
COMMENT ON COLUMN learning.hypotheses.replicability_score IS
    'M4 replicability composite score across sub-period folds + cross-asset robustness; range [0,1]';
COMMENT ON COLUMN learning.hypotheses.decision_lease_draft_id IS
    'M4 → M1 LAL Decision Lease DRAFT writeback binding UUID (per ADR-0034); FK 待 V099/V100 land 後 ALTER ADD CONSTRAINT';
COMMENT ON COLUMN learning.hypotheses.cowork_review_status IS
    'M4 Cowork hybrid review state (NONE/PENDING/APPROVED/REJECTED per ADR-0024-lite)';

-- ============================================================
-- Main DDL Step 2: 3 hot-path index CREATE IF NOT EXISTS (per spec §5.1)
--
-- - idx_hypotheses_source_module: M4 dashboard query (source × time DESC)
-- - idx_hypotheses_leakage_pass: M9 A/B queue (only PASS subset; partial)
-- - idx_hypotheses_cowork_review: Cowork review dashboard (only active; partial)
--
-- 注意: 採 CREATE INDEX IF NOT EXISTS 非 CONCURRENTLY,因 BEGIN/COMMIT
-- 包裹後 CONCURRENTLY 會 RAISE。CONCURRENTLY 改在 production V### sqlx
-- 路徑外圍處理 (sandbox empirical apply 不需 CONCURRENTLY)。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_hypotheses_source_module
    ON learning.hypotheses (hypothesis_source_module, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hypotheses_leakage_pass
    ON learning.hypotheses (leakage_scan_pass)
    WHERE leakage_scan_pass = TRUE;

CREATE INDEX IF NOT EXISTS idx_hypotheses_cowork_review
    ON learning.hypotheses (cowork_review_status)
    WHERE cowork_review_status != 'NONE';

-- ============================================================
-- Guard C: post-check idempotency drift (6 column + 3 index 齊全)
-- Guard C: 最終驗 column count + index count + CHECK 對齊
-- ============================================================
DO $$
DECLARE
    v_col_count INTEGER;
    v_idx_count INTEGER;
    v_check_def TEXT;
BEGIN
    -- 6 EXTEND column 齊全驗
    SELECT count(*) INTO v_col_count
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='hypotheses'
      AND column_name IN (
          'hypothesis_source_module', 'leakage_scan_pass',
          'bonferroni_corrected_p', 'replicability_score',
          'decision_lease_draft_id', 'cowork_review_status'
      );
    IF v_col_count <> 6 THEN
        RAISE EXCEPTION
            'V103 Guard C FAIL: M4 EXTEND column count=% (expected 6)。'
            'Verify ALTER TABLE ADD COLUMN 全 6 條 land。', v_col_count;
    END IF;

    -- 3 hot-path index 齊全驗
    SELECT count(*) INTO v_idx_count
    FROM pg_indexes
    WHERE schemaname='learning' AND tablename='hypotheses'
      AND indexname IN (
          'idx_hypotheses_source_module',
          'idx_hypotheses_leakage_pass',
          'idx_hypotheses_cowork_review'
      );
    IF v_idx_count <> 3 THEN
        RAISE EXCEPTION
            'V103 Guard C FAIL: M4 EXTEND hot-path index count=% (expected 3)。'
            'Verify CREATE INDEX 全 3 條 land。', v_idx_count;
    END IF;

    -- hypothesis_source_module CHECK enum 3 值驗
    SELECT pg_get_constraintdef(c.oid) INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    JOIN pg_namespace n ON t.relnamespace = n.oid
    WHERE n.nspname='learning' AND t.relname='hypotheses'
      AND c.contype='c'
      AND pg_get_constraintdef(c.oid) LIKE '%hypothesis_source_module%'
    LIMIT 1;
    IF v_check_def IS NOT NULL THEN
        IF position('M4_AUTO' IN v_check_def) = 0
           OR position('OPERATOR' IN v_check_def) = 0
           OR position('HISTORIC' IN v_check_def) = 0 THEN
            RAISE EXCEPTION
                'V103 Guard C FAIL: hypothesis_source_module CHECK enum mismatch。'
                'Actual: %. Expected M4_AUTO/OPERATOR/HISTORIC per spec §2.1。',
                v_check_def;
        END IF;
    END IF;

    -- cowork_review_status CHECK enum 4 值驗
    SELECT pg_get_constraintdef(c.oid) INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON c.conrelid = t.oid
    JOIN pg_namespace n ON t.relnamespace = n.oid
    WHERE n.nspname='learning' AND t.relname='hypotheses'
      AND c.contype='c'
      AND pg_get_constraintdef(c.oid) LIKE '%cowork_review_status%'
    LIMIT 1;
    IF v_check_def IS NOT NULL THEN
        IF position('NONE' IN v_check_def) = 0
           OR position('PENDING' IN v_check_def) = 0
           OR position('APPROVED' IN v_check_def) = 0
           OR position('REJECTED' IN v_check_def) = 0 THEN
            RAISE EXCEPTION
                'V103 Guard C FAIL: cowork_review_status CHECK enum mismatch。'
                'Actual: %. Expected NONE/PENDING/APPROVED/REJECTED per spec §2.1。',
                v_check_def;
        END IF;
    END IF;

    RAISE NOTICE
        'V103: M4 EXTEND all guards PASS — 6 column (hypothesis_source_module/'
        'leakage_scan_pass/bonferroni_corrected_p/replicability_score/'
        'decision_lease_draft_id/cowork_review_status) added, 3 hot-path index '
        'built, CHECK enum (3-source / 4-review) aligned with spec §2.1, '
        'fail-closed DEFAULT FALSE for leakage_scan_pass preserved (per 根原則 #6)。'
        'PA-DRIFT-2 HARD BLOCKER closure path empirical。';
END $$;

-- V051__mlde_recommendations_replay_columns.sql
-- Purpose / 目的:
--   Complete REF-20 V3 §4.2 MLDE Evidence Source Guard. The earlier V038
--   (ADD column evidence_source_tier nullable) → V039 (backfill 'real_outcome')
--   → V040 (NOT NULL + CHECK 4-value enum) chain only landed the tier column
--   itself. V3 §4.2 also requires two adjacent columns:
--     - replay_experiment_id UUID NULLABLE FK to replay.experiments(V049)
--     - manifest_hash BYTEA NULLABLE
--   plus a paired CHECK that enforces the lineage invariant:
--     - real_outcome row → both columns NULL
--     - replay-derived row (any non-real_outcome tier) → both columns NOT NULL
--   These two columns and the paired CHECK were originally hidden in
--   "P2b runner SQL fixture" per W1 dispatch, which Sprint 1 audit flagged
--   as "schema escaping migration governance". V051 pulls them back as a
--   real numbered migration.
--
--   完成 REF-20 V3 §4.2 MLDE Evidence Source Guard。先前 V038（加 nullable
--   evidence_source_tier）→ V039（'real_outcome' 回填）→ V040（NOT NULL +
--   CHECK 4-value enum）只 land 了 tier 欄。V3 §4.2 還要求兩個相鄰欄：
--     - replay_experiment_id UUID NULLABLE FK 至 replay.experiments(V049)
--     - manifest_hash BYTEA NULLABLE
--   外加配對 CHECK 強制 lineage 不變量：
--     - real_outcome row → 兩欄 NULL
--     - replay 衍生 row（任何非 real_outcome tier）→ 兩欄 NOT NULL
--   這兩欄與配對 CHECK 原藏於 W1 派發的「P2b runner SQL fixture」，
--   Sprint 1 audit 揭露為「schema 逃避 migration governance」；V051
--   把他們拉回真正帶編號的 migration。
--
-- Migration order / 遷移順序:
--   V038 → V039 → V040 (evidence_source_tier 3-step retrofit)
--   → V049 (replay_experiments full 22-column promotion; FK target)
--   → V051 (this; 2-column add + paired CHECK + FK).
--
-- Backfill / 回填:
--   V039 已把全部既有 row 設為 evidence_source_tier='real_outcome'。新加
--   replay_experiment_id 與 manifest_hash 兩欄都 NULLABLE 且預設 NULL，
--   既有 row 自然滿足新 paired CHECK（real_outcome + 兩欄 NULL）。不需
--   額外 UPDATE。
--
--   V039 has set every existing row to evidence_source_tier='real_outcome'.
--   The two new columns replay_experiment_id and manifest_hash are NULLABLE
--   with DEFAULT NULL, so existing rows naturally satisfy the new paired
--   CHECK (real_outcome + both NULL). No additional UPDATE required.
--
-- Idempotency / 幂等性:
--   local psql -f V051 ... × 2 → second run no-op (Guard A IF NOT EXISTS;
--   Guard B verifies column types pre-existing match canonical; CHECK + FK
--   wrapped in pg_constraint IF NOT EXISTS guard).
--
-- Guard A: enforced (V040 + V049 prerequisites; mlde_shadow_recommendations
--          required existing columns).
-- Guard B: enforced (column types validated when columns pre-exist).
-- Guard C: N/A (no hot-path index added by this migration).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §4.2 (MLDE Evidence Source Guard, lines 220-234 paired CHECK SQL)
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md
--     §2 Track D T-D3 (this task)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V051 (buffer → land
--   per Sprint 1 Track D T-D3 task, 2026-05-03).
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard B

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: V040 + V049 prerequisites + mlde_shadow_recommendations existing
-- columns presence. /
-- Guard A：V040 + V049 前置條件 + mlde_shadow_recommendations 既有欄位存在。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_evidence_tier_present BOOLEAN;
    v_evidence_tier_nullable TEXT;
    v_check_constraint_present BOOLEAN;
    v_v049_table_present BOOLEAN;
    v_v049_pk_type TEXT;
BEGIN
    -- V040 prerequisite: evidence_source_tier exists, NOT NULL.
    -- V040 前置：evidence_source_tier 已存在且 NOT NULL。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND column_name = 'evidence_source_tier'
    ) INTO v_evidence_tier_present;

    IF NOT v_evidence_tier_present THEN
        RAISE EXCEPTION
            'V051 Guard A: learning.mlde_shadow_recommendations.evidence_source_tier missing. '
            'V038 + V039 + V040 must all run before V051.';
    END IF;

    SELECT is_nullable INTO v_evidence_tier_nullable
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'evidence_source_tier';

    IF v_evidence_tier_nullable <> 'NO' THEN
        RAISE EXCEPTION
            'V051 Guard A: evidence_source_tier is_nullable=%, expected NO. '
            'V040 must complete (SET NOT NULL) before V051 paired CHECK lands.',
            v_evidence_tier_nullable;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_evidence_source_tier'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) INTO v_check_constraint_present;

    IF NOT v_check_constraint_present THEN
        RAISE EXCEPTION
            'V051 Guard A: chk_evidence_source_tier (V040 4-value enum CHECK) missing. '
            'V040 must complete before V051.';
    END IF;

    -- V049 prerequisite: replay.experiments FK target table with UUID PK.
    -- V049 前置：replay.experiments FK 目標表，PK 型別為 UUID。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'experiments'
    ) INTO v_v049_table_present;

    IF NOT v_v049_table_present THEN
        RAISE EXCEPTION
            'V051 Guard A: replay.experiments does not exist. V049 must run before V051 '
            '(FK: learning.mlde_shadow_recommendations.replay_experiment_id REFERENCES replay.experiments).';
    END IF;

    SELECT data_type INTO v_v049_pk_type
    FROM information_schema.columns
    WHERE table_schema = 'replay'
      AND table_name = 'experiments'
      AND column_name = 'experiment_id';

    IF v_v049_pk_type <> 'uuid' THEN
        RAISE EXCEPTION
            'V051 Guard A: replay.experiments.experiment_id is %, expected uuid. '
            'V049 must run before V051 (V049 ALTERs experiment_id from TEXT to UUID).',
            v_v049_pk_type;
    END IF;

    RAISE NOTICE 'V051 Guard A: V040 + V049 prerequisites verified; continuing to ADD COLUMN.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B: column type drift check (when columns pre-exist from prior run) /
-- Guard B：欄位型別 drift 檢查（重跑時欄位已存在）
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_replay_id_type TEXT;
    v_manifest_hash_type TEXT;
BEGIN
    SELECT data_type INTO v_replay_id_type
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'replay_experiment_id';

    IF v_replay_id_type IS NOT NULL AND v_replay_id_type <> 'uuid' THEN
        RAISE EXCEPTION
            'V051 Guard B: learning.mlde_shadow_recommendations.replay_experiment_id is %, expected uuid. '
            'Column type drift detected; manual reconcile required.',
            v_replay_id_type;
    END IF;

    SELECT data_type INTO v_manifest_hash_type
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'manifest_hash';

    IF v_manifest_hash_type IS NOT NULL AND v_manifest_hash_type <> 'bytea' THEN
        RAISE EXCEPTION
            'V051 Guard B: learning.mlde_shadow_recommendations.manifest_hash is %, expected bytea. '
            'Column type drift detected; manual reconcile required.',
            v_manifest_hash_type;
    END IF;

    RAISE NOTICE 'V051 Guard B: column types verified (or columns absent ready for ADD).';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD 2 columns per V3 §4.2 / 加 V3 §4.2 兩欄
--
-- replay_experiment_id  UUID NULLABLE FK to replay.experiments (V049)
-- manifest_hash         BYTEA NULLABLE (HMAC-SHA256 hash of canonical manifest;
--                       byte-for-byte identical to replay.experiments.manifest_hash
--                       for the same experiment)
--
-- Both NULLABLE because real_outcome rows leave both NULL (existing rows are
-- already evidence_source_tier='real_outcome' per V039 backfill, satisfying
-- the new paired CHECK without UPDATE).
--
-- 兩欄都 NULLABLE，因為 real_outcome row 兩欄為 NULL（既有 row 已被 V039 回填
-- 為 evidence_source_tier='real_outcome'，自然滿足新配對 CHECK，無需 UPDATE）。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE learning.mlde_shadow_recommendations
    ADD COLUMN IF NOT EXISTS replay_experiment_id UUID,
    ADD COLUMN IF NOT EXISTS manifest_hash        BYTEA;

-- ─────────────────────────────────────────────────────────────────────────────
-- FK + paired CHECK constraint per V3 §4.2 lines 220-234 /
-- FK + V3 §4.2 lines 220-234 配對 CHECK
--
-- The paired CHECK enforces the V3 §4.2 lineage invariant exactly:
--   (evidence_source_tier='real_outcome' AND replay_experiment_id IS NULL
--      AND manifest_hash IS NULL)
--   OR
--   (evidence_source_tier<>'real_outcome' AND replay_experiment_id IS NOT NULL
--      AND manifest_hash IS NOT NULL)
--
-- 配對 CHECK 精確強制 V3 §4.2 lineage 不變量。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    -- FK to V049 (NULLABLE; ON DELETE NO ACTION).
    --
    -- Why NO ACTION (not SET NULL or CASCADE) / 為什麼用 NO ACTION:
    --   The paired CHECK chk_mlde_shadow_replay_lineage forbids the combo
    --   {evidence_source_tier <> 'real_outcome' + replay_experiment_id IS
    --   NULL}. SET NULL would attempt to nullify replay_experiment_id when
    --   the parent experiment is deleted, but the row's evidence_source_tier
    --   stays 'calibrated_replay' (or other replay tier), which the CHECK
    --   rejects → the parent DELETE itself fails. This makes SET NULL
    --   effectively the same as NO ACTION but with a confusing error
    --   message.
    --
    --   CASCADE is wrong because deleting a manifest should not delete the
    --   advisory rows it produced — those rows are evidence and must
    --   survive for forensic audit.
    --
    --   NO ACTION is the correct semantic: replay.experiments rows are
    --   immutable manifest registry entries (V3 §5 audit). DELETE attempts
    --   should fail loudly while replay-derived advisory rows still
    --   reference them. Operator must archive/dispose of the advisory rows
    --   first (or DELETE the manifest only after evidence rows are
    --   tombstoned via separate audit-preserving path).
    --
    --   配對 CHECK chk_mlde_shadow_replay_lineage 禁止
    --   {evidence_source_tier 非 real_outcome + replay_experiment_id NULL}
    --   組合。SET NULL 嘗試在 parent experiment 被刪時把 replay_experiment_id
    --   設 NULL，但 row 的 evidence_source_tier 仍是 'calibrated_replay'
    --   等 replay tier，CHECK 直接擋 → parent DELETE 本身失敗。SET NULL
    --   實質等於 NO ACTION 但訊息更混亂。
    --   CASCADE 錯誤：刪 manifest 不應刪其產生的 advisory row（後者是
    --   evidence，必須留作取證 audit）。
    --   NO ACTION 是正確語意：replay.experiments row 是不可變 manifest
    --   registry（V3 §5 audit）；DELETE 嘗試應該大聲失敗，當還有 replay
    --   衍生 advisory row 引用時。Operator 必先 archive/處置 advisory row
    --   才能刪 manifest。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_mlde_shadow_replay_experiment'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) THEN
        ALTER TABLE learning.mlde_shadow_recommendations
            ADD CONSTRAINT fk_mlde_shadow_replay_experiment
            FOREIGN KEY (replay_experiment_id)
            REFERENCES replay.experiments(experiment_id)
            ON DELETE NO ACTION;
        RAISE NOTICE 'V051: added FK fk_mlde_shadow_replay_experiment (V049 lineage, ON DELETE NO ACTION)';
    ELSE
        RAISE NOTICE 'V051: fk_mlde_shadow_replay_experiment already present; skipping';
    END IF;

    -- Paired CHECK per V3 §4.2 lines 220-234.
    -- 配對 CHECK，符合 V3 §4.2 lines 220-234。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_mlde_shadow_replay_lineage'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) THEN
        ALTER TABLE learning.mlde_shadow_recommendations
            ADD CONSTRAINT chk_mlde_shadow_replay_lineage
            CHECK (
                (
                    evidence_source_tier = 'real_outcome'
                    AND replay_experiment_id IS NULL
                    AND manifest_hash IS NULL
                )
                OR
                (
                    evidence_source_tier <> 'real_outcome'
                    AND replay_experiment_id IS NOT NULL
                    AND manifest_hash IS NOT NULL
                )
            );
        RAISE NOTICE 'V051: added CHECK chk_mlde_shadow_replay_lineage (V3 §4.2 paired)';
    ELSE
        RAISE NOTICE 'V051: chk_mlde_shadow_replay_lineage already present; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Post-apply verification / Apply 後驗證
--
-- Confirm both columns present with correct type and the paired CHECK is in
-- pg_constraint. Defense-in-depth: future migrations dropping the CHECK will
-- be caught by V051 re-run.
--
-- 確認兩欄存在且型別正確，配對 CHECK 在 pg_constraint。防禦深度：未來
-- migration 意外 drop CHECK，V051 重跑會抓到。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_replay_id_type TEXT;
    v_manifest_hash_type TEXT;
    v_check_present BOOLEAN;
    v_fk_present BOOLEAN;
BEGIN
    SELECT data_type INTO v_replay_id_type
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'replay_experiment_id';

    IF v_replay_id_type <> 'uuid' THEN
        RAISE EXCEPTION
            'V051 post-apply: replay_experiment_id type=% (expected uuid). ADD COLUMN failed?',
            v_replay_id_type;
    END IF;

    SELECT data_type INTO v_manifest_hash_type
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'manifest_hash';

    IF v_manifest_hash_type <> 'bytea' THEN
        RAISE EXCEPTION
            'V051 post-apply: manifest_hash type=% (expected bytea). ADD COLUMN failed?',
            v_manifest_hash_type;
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_mlde_shadow_replay_lineage'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) INTO v_check_present;

    IF NOT v_check_present THEN
        RAISE EXCEPTION
            'V051 post-apply: chk_mlde_shadow_replay_lineage CHECK absent. Cannot enforce V3 §4.2 lineage.';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_mlde_shadow_replay_experiment'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) INTO v_fk_present;

    IF NOT v_fk_present THEN
        RAISE EXCEPTION
            'V051 post-apply: fk_mlde_shadow_replay_experiment FK absent. Cannot enforce V049 referential integrity.';
    END IF;

    RAISE NOTICE 'V051 post-apply: 2 columns + FK + paired CHECK all verified.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON COLUMN learning.mlde_shadow_recommendations.replay_experiment_id IS
'V3 §4.2: NULL for real_outcome row; NOT NULL for replay-derived row '
'(calibrated_replay / synthetic_replay / counterfactual_replay). FK to '
'replay.experiments(V049) ON DELETE NO ACTION (manifest immutable while '
'advisory rows reference it). Enforced by chk_mlde_shadow_replay_lineage.';

COMMENT ON COLUMN learning.mlde_shadow_recommendations.manifest_hash IS
'V3 §4.2 + §6.2: NULL for real_outcome row; NOT NULL for replay-derived row. '
'BYTEA holds SHA-256 hash of canonical manifest (byte-identical to '
'replay.experiments.manifest_hash for the same experiment). '
'Enforced by chk_mlde_shadow_replay_lineage.';

-- V052__replay_run_state_artifacts_fk_redirect.sql
-- Purpose / 目的:
--   Redirect V045 (replay.run_state.manifest_id) and V046
--   (replay.report_artifacts.experiment_id implicit reference) FK targets
--   to the now-real V049 replay.experiments table. V045 and V046 were
--   originally landed without FK because replay.experiments was supposed to
--   live in a "P2b runner SQL fixture" — Sprint 1 audit reframed that
--   pattern as schema drift (escaping migration governance) and Track D
--   T-D1 (V049) now provides a real FK target table.
--
--   把 V045 (replay.run_state.manifest_id) 與 V046 (replay.report_artifacts
--   既有的 experiment_id 邏輯參照) FK 目標重新指向真實 V049 replay.experiments
--   表。V045 與 V046 land 時無 FK，因為 replay.experiments 原預定存於「P2b
--   runner SQL fixture」— Sprint 1 audit 重新定位該 pattern 為 schema drift
--   （逃避 migration governance），Track D T-D1 (V049) 現在提供真實 FK 目標表。
--
-- Why ALTER ADD CONSTRAINT instead of editing V045/V046 / 為什麼走 ALTER 而不改 V045/V046:
--   2026-05-02 P0 sqlx hash drift incident (commit 3681f83) showed that
--   editing already-applied V### files breaks engine sqlx_migrations
--   checksum: file checksum drifts but DB recorded checksum doesn't, and
--   sqlx errors at startup. The fix was a dedicated repair_migration_checksum
--   binary. To avoid re-triggering that incident, V052 takes a forward-only
--   approach: ALTER TABLE ... ADD CONSTRAINT IF NOT EXISTS pattern in a new
--   numbered migration. V045/V046 file content is unchanged; checksum stable.
--
--   2026-05-02 P0 sqlx hash drift 事件（commit 3681f83）顯示：編輯已 apply
--   的 V### file 會破 engine sqlx_migrations checksum（file checksum 漂但
--   DB 紀錄不變），啟動時 sqlx 報錯。修復為專用 repair_migration_checksum
--   binary。為避免重觸該事件，V052 走 forward-only：ALTER TABLE ... ADD
--   CONSTRAINT IF NOT EXISTS 在新編號 migration。V045/V046 file 不動，
--   checksum 穩定。
--
-- Migration order / 遷移順序:
--   V045 (replay_run_state) → V046 (replay_report_artifacts)
--   → V049 (replay_experiments full 22-column promotion)
--   → V050 (replay_simulated_fills FK to V049) → V052 (this).
--
--   V050 必先 land 是因為 V050 已 declare 對 V049 的 FK；V052 是 retro-add
--   FK 給 V045/V046。
--
-- Preflight dangling row check / Preflight 懸空 row 檢查 (PA push back #1):
--   V045 既有 row 對 V052 FK redirect 的 dangling — PA Sprint 1 panorama 確認
--   Linux runtime _sqlx_migrations max=35（V### 全部 0/11 applied），所以 V045
--   既有 row 在 Linux 為 0；Mac dev 假設 0。但仍 preflight LEFT JOIN 統計
--   dangling row count；> 0 → RAISE EXCEPTION abort（operator decide reconcile
--   or archive）。
--
--   V045 existing rows may dangle vs V052 FK redirect — PA Sprint 1 panorama
--   confirms Linux runtime _sqlx_migrations max=35 (V### all 0/11 applied),
--   so V045 has 0 rows in Linux; Mac dev assumed 0. Still preflight LEFT JOIN
--   counts dangling rows; >0 → RAISE EXCEPTION abort (operator decides
--   reconcile or archive).
--
-- Idempotency / 幂等性:
--   local psql -f V052 ... × 2 → second run no-op (FK + CHECK constraints
--   wrapped in pg_constraint IF NOT EXISTS guard).
--
-- Guard A: enforced (V045 + V046 + V049 prerequisites).
-- Guard B: enforced (column type validation; UUID alignment).
-- Guard C: N/A (no index changes; FK creates implicit index but we don't
--          require a specific name).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §4.1 (replay.experiments + replay.report_artifacts FK contract) +
--     §6.1 (Canonical Implementation Choice; V049 must FK-bind both)
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md
--     §2 Track D T-D4 (this task) + §5 Push Back #1 (dangling row preflight)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V052 (buffer → land
--   per Sprint 1 Track D T-D4 task, 2026-05-03).
-- Memory pointer / 記憶指標:
--   memory/project_2026_05_02_p0_sqlx_hash_drift.md (operator hint about
--   why to never edit applied V### files)
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard B

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: V045 + V046 + V049 prerequisites /
-- Guard A：V045 + V046 + V049 前置條件
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_run_state_present BOOLEAN;
    v_artifacts_present BOOLEAN;
    v_experiments_present BOOLEAN;
    v_artifacts_has_experiment_id BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'run_state'
    ) INTO v_run_state_present;

    IF NOT v_run_state_present THEN
        RAISE EXCEPTION
            'V052 Guard A: replay.run_state does not exist. V045 must run before V052.';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'report_artifacts'
    ) INTO v_artifacts_present;

    IF NOT v_artifacts_present THEN
        RAISE EXCEPTION
            'V052 Guard A: replay.report_artifacts does not exist. V046 must run before V052.';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'experiments'
    ) INTO v_experiments_present;

    IF NOT v_experiments_present THEN
        RAISE EXCEPTION
            'V052 Guard A: replay.experiments does not exist. V049 must run before V052.';
    END IF;

    -- V046 currently has no experiment_id column (V3 §4.1 wanted it FK-bound
    -- but V046 only landed run_id FK to V045). V052 must ADD COLUMN
    -- experiment_id first, then ADD FK to V049.
    -- V046 目前無 experiment_id 欄（V3 §4.1 規範 FK-bound 但 V046 只 land
    -- run_id FK 至 V045）。V052 必先 ADD COLUMN experiment_id，再 ADD FK 至 V049。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'replay'
          AND table_name = 'report_artifacts'
          AND column_name = 'experiment_id'
    ) INTO v_artifacts_has_experiment_id;

    IF v_artifacts_has_experiment_id THEN
        RAISE NOTICE 'V052 Guard A: replay.report_artifacts.experiment_id already present (re-run); ADD COLUMN will no-op';
    ELSE
        RAISE NOTICE 'V052 Guard A: replay.report_artifacts.experiment_id absent; will ADD COLUMN below';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B: column type alignment (V045.manifest_id + V046 to-be-added
-- experiment_id must be UUID to match V049.experiment_id) /
-- Guard B：欄位型別對齊（V045.manifest_id + V046 待加 experiment_id 必為
-- UUID 對齊 V049.experiment_id）
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_v045_manifest_id_type TEXT;
    v_v049_pk_type TEXT;
BEGIN
    SELECT data_type INTO v_v045_manifest_id_type
    FROM information_schema.columns
    WHERE table_schema = 'replay'
      AND table_name = 'run_state'
      AND column_name = 'manifest_id';

    IF v_v045_manifest_id_type <> 'uuid' THEN
        RAISE EXCEPTION
            'V052 Guard B: replay.run_state.manifest_id is %, expected uuid. '
            'V045 schema drift detected; manual reconcile required.',
            v_v045_manifest_id_type;
    END IF;

    SELECT data_type INTO v_v049_pk_type
    FROM information_schema.columns
    WHERE table_schema = 'replay'
      AND table_name = 'experiments'
      AND column_name = 'experiment_id';

    IF v_v049_pk_type <> 'uuid' THEN
        RAISE EXCEPTION
            'V052 Guard B: replay.experiments.experiment_id is %, expected uuid. '
            'V049 ALTER COLUMN TYPE failed or V049 not yet land; manual reconcile.',
            v_v049_pk_type;
    END IF;

    RAISE NOTICE 'V052 Guard B: V045.manifest_id and V049.experiment_id both uuid; FK creation safe.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Preflight dangling row check (PA Push Back #1) /
-- Preflight 懸空 row 檢查（PA Push Back #1）
--
-- Count V045 rows whose manifest_id has no matching V049 experiment_id;
-- count V046 rows whose run_id has no matching V045 run row (sanity); these
-- are forward-direction dangling. We RAISE if >0 to let operator decide
-- reconcile (INSERT minimal V049 stub for each dangling V045) or archive
-- (DELETE/move to archive table).
--
-- 計 V045 row 中 manifest_id 在 V049 找不到對應 experiment_id 的數；
-- 計 V046 row 中 run_id 在 V045 找不到對應 run row 的數（sanity）；前者為
-- 前向 dangling。> 0 RAISE 讓 operator 決定 reconcile（為每筆 dangling
-- V045 INSERT V049 minimal stub）或 archive（DELETE/搬到歸檔表）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_v045_dangling BIGINT;
    v_v046_dangling BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_v045_dangling
    FROM replay.run_state r
    LEFT JOIN replay.experiments e ON r.manifest_id = e.experiment_id
    WHERE e.experiment_id IS NULL;

    IF v_v045_dangling > 0 THEN
        RAISE EXCEPTION
            'V052 preflight: replay.run_state has % rows whose manifest_id has no matching '
            'replay.experiments(experiment_id). FK redirect would fail. '
            'Operator decision required: '
            '(a) INSERT minimal V049 stub for each dangling manifest_id, OR '
            '(b) DELETE/archive dangling V045 rows. '
            'Diagnostic: SELECT r.run_id, r.manifest_id, r.actor_id, r.status '
            '            FROM replay.run_state r LEFT JOIN replay.experiments e '
            '            ON r.manifest_id = e.experiment_id WHERE e.experiment_id IS NULL;',
            v_v045_dangling;
    END IF;

    -- Sanity: V046.run_id should already FK to V045 (declared in V046 file).
    -- 健全性：V046.run_id 已宣告 FK 到 V045（V046 檔內）。
    SELECT COUNT(*) INTO v_v046_dangling
    FROM replay.report_artifacts a
    LEFT JOIN replay.run_state r ON a.run_id = r.run_id
    WHERE r.run_id IS NULL;

    IF v_v046_dangling > 0 THEN
        RAISE EXCEPTION
            'V052 preflight: replay.report_artifacts has % rows whose run_id has no matching '
            'replay.run_state(run_id) — V046 FK should have caught this. Investigate before V052.',
            v_v046_dangling;
    END IF;

    RAISE NOTICE 'V052 preflight: 0 dangling rows in V045 (manifest_id→V049) and V046 (run_id→V045); FK redirect safe.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD V045.manifest_id FK to V049 / 加 V045.manifest_id FK 至 V049
--
-- ON DELETE RESTRICT preserves the lifecycle: a manifest cannot be deleted
-- while runs reference it. ON UPDATE CASCADE for completeness (UUID PK
-- normally not updated).
--
-- ON DELETE RESTRICT 保留生命週期：manifest 被引用時不可刪。ON UPDATE
-- CASCADE 為完整性（UUID PK 通常不更新）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_replay_run_state_manifest_id'
          AND conrelid = 'replay.run_state'::regclass
    ) THEN
        ALTER TABLE replay.run_state
            ADD CONSTRAINT fk_replay_run_state_manifest_id
            FOREIGN KEY (manifest_id)
            REFERENCES replay.experiments(experiment_id)
            ON DELETE RESTRICT
            ON UPDATE CASCADE;
        RAISE NOTICE 'V052: added FK fk_replay_run_state_manifest_id (V045.manifest_id → V049.experiment_id)';
    ELSE
        RAISE NOTICE 'V052: fk_replay_run_state_manifest_id already present; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD V046.experiment_id column + FK to V049 /
-- 加 V046.experiment_id column + FK 至 V049
--
-- V046 originally only had run_id FK → V045. V3 §4.1 (replay.report_artifacts
-- minimum) requires experiment_id FK → replay.experiments. We ADD the column
-- NULLABLE (existing rows backfilled via run_state JOIN below; if no V045
-- row matches, leave NULL — orphan artifact).
-- V046 原僅 run_id FK 至 V045。V3 §4.1 (replay.report_artifacts 最小契約) 要求
-- experiment_id FK 至 replay.experiments。本檔 ADD COLUMN NULLABLE（既有 row
-- 透過 run_state JOIN 回填；無對應 V045 row 留 NULL — orphan artifact）。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE replay.report_artifacts
    ADD COLUMN IF NOT EXISTS experiment_id UUID;

-- Backfill V046.experiment_id from V045.manifest_id via run_id JOIN.
-- 從 V045.manifest_id 透過 run_id JOIN 回填 V046.experiment_id。
UPDATE replay.report_artifacts a
SET experiment_id = r.manifest_id
FROM replay.run_state r
WHERE a.run_id = r.run_id
  AND a.experiment_id IS NULL;

-- After backfill, ADD FK + CHECK that the FK target exists post-backfill.
-- 回填後 ADD FK + CHECK FK 目標存在。
DO $$
DECLARE
    v_fk_present BOOLEAN;
    v_orphan_count BIGINT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_replay_report_artifacts_experiment_id'
          AND conrelid = 'replay.report_artifacts'::regclass
    ) INTO v_fk_present;

    -- Sanity check: any V046 row whose experiment_id is NOT NULL but doesn't
    -- match V049 — should be 0 since V045 row has manifest_id matching V049
    -- (V045 dangling already RAISEd above by preflight).
    -- 健全性：V046 row 中 experiment_id 非 NULL 但無 V049 對應的數應為 0
    -- （V045 dangling 已被 preflight RAISE）。
    SELECT COUNT(*) INTO v_orphan_count
    FROM replay.report_artifacts a
    LEFT JOIN replay.experiments e ON a.experiment_id = e.experiment_id
    WHERE a.experiment_id IS NOT NULL AND e.experiment_id IS NULL;

    IF v_orphan_count > 0 THEN
        RAISE EXCEPTION
            'V052: replay.report_artifacts backfill produced % orphan experiment_id values. '
            'Investigate manually before re-running V052.',
            v_orphan_count;
    END IF;

    IF NOT v_fk_present THEN
        ALTER TABLE replay.report_artifacts
            ADD CONSTRAINT fk_replay_report_artifacts_experiment_id
            FOREIGN KEY (experiment_id)
            REFERENCES replay.experiments(experiment_id)
            ON DELETE CASCADE;
        RAISE NOTICE 'V052: added FK fk_replay_report_artifacts_experiment_id (V046.experiment_id → V049.experiment_id, ON DELETE CASCADE)';
    ELSE
        RAISE NOTICE 'V052: fk_replay_report_artifacts_experiment_id already present; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Post-apply verification / Apply 後驗證
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_v045_fk_present BOOLEAN;
    v_v046_fk_present BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_replay_run_state_manifest_id'
          AND conrelid = 'replay.run_state'::regclass
    ) INTO v_v045_fk_present;

    IF NOT v_v045_fk_present THEN
        RAISE EXCEPTION 'V052 post-apply: V045.manifest_id FK absent';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_replay_report_artifacts_experiment_id'
          AND conrelid = 'replay.report_artifacts'::regclass
    ) INTO v_v046_fk_present;

    IF NOT v_v046_fk_present THEN
        RAISE EXCEPTION 'V052 post-apply: V046.experiment_id FK absent';
    END IF;

    RAISE NOTICE 'V052 post-apply: V045 + V046 FK redirects to V049 verified.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation update / 欄位文件更新
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON COLUMN replay.run_state.manifest_id IS
'V3 §4.1: FK to replay.experiments(experiment_id) (V049). UUID. ON DELETE RESTRICT '
'(manifest cannot be deleted while runs reference it). Originally landed by V045 '
'without FK because replay.experiments lived in fixture; V052 retro-adds the FK '
'after V049 promotes the table to a real migration. /'
'V3 §4.1：FK 至 replay.experiments(experiment_id)（V049）。UUID。ON DELETE RESTRICT。'
'V045 land 時無 FK（replay.experiments 存於 fixture）；V049 升級為真 migration 後 V052 retro 加 FK。';

COMMENT ON COLUMN replay.report_artifacts.experiment_id IS
'V3 §4.1: FK to replay.experiments(experiment_id) (V049). UUID. ON DELETE CASCADE '
'(when a manifest is deleted, all its artifacts are pruned). Added by V052 along '
'with backfill from replay.run_state(manifest_id). /'
'V3 §4.1：FK 至 replay.experiments(experiment_id)（V049）。UUID。ON DELETE CASCADE。'
'V052 在 ADD COLUMN 同時透過 replay.run_state(manifest_id) JOIN 回填。';

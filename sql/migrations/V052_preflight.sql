-- V052_preflight.sql
-- Purpose / 目的:
--   Pre-deploy healthcheck for V052 FK redirect (V045/V046 → V049). Run after
--   V049 + V050 + V051 land and before V052 to catch any dangling rows that
--   would cause V052 ALTER ADD CONSTRAINT to fail atomically.
--
--   This script is READ-ONLY (5 SELECTs); operator-friendly for routine
--   inspection and post-deploy verification.
--
-- V052 對 V045/V046 加 FK 至 V049 的部署前健康檢查。V049/V050/V051 後、V052 land
-- 前執行；找出任何懸空 row 以避免 V052 atomic 失敗。
-- 本腳本純讀（5 條 SELECT），適合日常巡檢與部署後驗證。
--
-- Usage / 用法:
--   psql -U trading_admin -d trading_ai -f sql/migrations/V052_preflight.sql
--
--   ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai \
--     -f /opt/openclaw/srv/sql/migrations/V052_preflight.sql"
--
-- Expected output (post-V049/V050/V051, pre-V052) /
-- 預期輸出（V049/V050/V051 後、V052 前）:
--   - v045_dangling.row_count = 0       ← V052 ready to run
--   - v046_dangling.row_count = 0       ← V052 ready to run
--   - v045_fk_present.has_fk   = false
--   - v046_fk_present.has_fk   = false
--   - v049_pk_type.data_type   = uuid
--
-- Expected output (post-V052) / 預期輸出（V052 後）:
--   - v045_dangling.row_count = 0
--   - v046_dangling.row_count = 0
--   - v045_fk_present.has_fk   = true
--   - v046_fk_present.has_fk   = true
--   - v049_pk_type.data_type   = uuid
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §4.1
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md
--     §5 Push Back #1

-- ─────────────────────────────────────────────────────────────────────────────
-- Probe 1: V045 (replay.run_state) dangling row count /
-- 探針 1：V045（replay.run_state）懸空 row 計數
--
-- Goal: zero before V052 runs / 目標：V052 run 前必為 0
-- Diagnostic: any row whose manifest_id has no matching V049 experiment_id
-- ─────────────────────────────────────────────────────────────────────────────
\echo '=== V052 Probe 1: V045 dangling rows (manifest_id with no V049 match) ==='
\echo '=== V052 探針 1：V045 懸空 row（manifest_id 在 V049 無對應）==='
SELECT 'v045_dangling' AS probe,
       COUNT(*)        AS row_count
  FROM replay.run_state r
  LEFT JOIN replay.experiments e ON r.manifest_id = e.experiment_id
 WHERE e.experiment_id IS NULL;

-- Detail (first 10 dangling rows for operator triage) /
-- 細節（前 10 個懸空 row 供 operator 分析）
\echo ''
\echo '=== V052 Probe 1 detail (top 10 dangling V045 rows) ==='
SELECT r.run_id, r.manifest_id, r.actor_id, r.status, r.created_at
  FROM replay.run_state r
  LEFT JOIN replay.experiments e ON r.manifest_id = e.experiment_id
 WHERE e.experiment_id IS NULL
 ORDER BY r.created_at DESC
 LIMIT 10;

-- ─────────────────────────────────────────────────────────────────────────────
-- Probe 2: V046 (replay.report_artifacts) dangling row count /
-- 探針 2：V046（replay.report_artifacts）懸空 row 計數
--
-- Goal: zero before V052 runs / 目標：V052 run 前必為 0
-- Diagnostic: any row whose run_id has no matching V045 run_state row
-- (should already be impossible because V046 declared run_id FK to V045).
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '=== V052 Probe 2: V046 dangling rows (run_id with no V045 match) ==='
\echo '=== V052 探針 2：V046 懸空 row（run_id 在 V045 無對應）==='
SELECT 'v046_dangling' AS probe,
       COUNT(*)        AS row_count
  FROM replay.report_artifacts a
  LEFT JOIN replay.run_state r ON a.run_id = r.run_id
 WHERE r.run_id IS NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Probe 3: V045 FK presence / V045 FK 存在性
--
-- Goal: false before V052; true after V052 / 目標：V052 前 false；之後 true
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '=== V052 Probe 3: V045.manifest_id FK to V049 presence ==='
\echo '=== V052 探針 3：V045.manifest_id 對 V049 的 FK 存在性 ==='
SELECT 'v045_fk_present' AS probe,
       EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'fk_replay_run_state_manifest_id'
             AND conrelid = 'replay.run_state'::regclass
       ) AS has_fk;

-- ─────────────────────────────────────────────────────────────────────────────
-- Probe 4: V046 FK presence / V046 FK 存在性
--
-- Goal: false before V052; true after V052
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '=== V052 Probe 4: V046.experiment_id FK to V049 presence ==='
\echo '=== V052 探針 4：V046.experiment_id 對 V049 的 FK 存在性 ==='
SELECT 'v046_fk_present' AS probe,
       EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'fk_replay_report_artifacts_experiment_id'
             AND conrelid = 'replay.report_artifacts'::regclass
       ) AS has_fk;

-- ─────────────────────────────────────────────────────────────────────────────
-- Probe 5: V049 PK type alignment / V049 PK 型別對齊
--
-- Goal: data_type = 'uuid' (V045/V046/V050/V051 all FK with UUID).
-- 目標：data_type = 'uuid'（V045/V046/V050/V051 都以 UUID FK）。
-- ─────────────────────────────────────────────────────────────────────────────
\echo ''
\echo '=== V052 Probe 5: V049 (replay.experiments) PK type alignment ==='
\echo '=== V052 探針 5：V049（replay.experiments）PK 型別對齊 ==='
SELECT 'v049_pk_type' AS probe,
       data_type      AS pk_type
  FROM information_schema.columns
 WHERE table_schema = 'replay'
   AND table_name = 'experiments'
   AND column_name = 'experiment_id';

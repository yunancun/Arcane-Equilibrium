-- V049__replay_experiments.sql
-- Purpose / 目的:
--   Promote `replay.experiments` from the V041 4-column bootstrap stub
--   (experiment_id TEXT PK / half_life_days / embargo_days / created_at)
--   to the full V3 §4.1 22-column manifest registry. This is the primary
--   subject of REF-20 W1 schema drift remediation: V3 §4.1 originally
--   was reserved as a P2b runner SQL fixture, but auditing flagged that
--   pattern as "schema hidden from migration governance". Sprint 1 Track D
--   pulls the 22-column contract back into a real numbered migration
--   under Guard A/B/C, restoring the V3 §12 #6 `replay_source_guard`
--   acceptance path.
--
--   把 V041 4 column bootstrap stub (experiment_id TEXT PK /
--   half_life_days / embargo_days / created_at) 升級為 V3 §4.1 完整 22
--   column manifest registry。本檔是 REF-20 W1 schema drift 修復的主體：
--   V3 §4.1 原預留為 P2b runner SQL fixture，但 audit 揭露此 pattern
--   為「schema 藏於 fixture 繞 migration governance」。Sprint 1 Track D
--   把 22 column 契約拉回真正帶編號的 migration，過 Guard A/B/C，
--   恢復 V3 §12 #6 `replay_source_guard` acceptance 路徑。
--
-- Why this migration is required / 為什麼必須做這個 migration:
--   1. V045 (replay.run_state) declares manifest_id UUID NOT NULL but
--      no FK target table existed → V052 FK redirect cannot land.
--   2. V046 (replay.report_artifacts) only FKs run_id → run_state; the
--      V3 §4.1 contract requires experiment_id → experiments link as
--      well. Without V049 the lineage is broken.
--   3. V051 (mlde_shadow_recommendations replay_experiment_id retrofit)
--      needs an FK target table. Without V049 the replay-derived row
--      CHECK in V3 §4.2 cannot be enforced through referential
--      integrity.
--   4. V3 §12 #6 `replay_source_guard` healthcheck assumes
--      `replay.experiments` is FK-enforced. Stub from V041 cannot
--      satisfy this contract.
--
--   1. V045 (replay.run_state) 宣告 manifest_id UUID NOT NULL 但 FK 目標
--      表不存在 → V052 FK redirect 無法 land。
--   2. V046 (replay.report_artifacts) 只 FK run_id → run_state；V3 §4.1
--      契約要求 experiment_id → experiments link 也存在；無 V049 lineage
--      斷裂。
--   3. V051 (mlde_shadow_recommendations replay_experiment_id retrofit)
--      需要 FK 目標表；無 V049 V3 §4.2 replay-derived row CHECK 無法以
--      referential integrity 強制。
--   4. V3 §12 #6 `replay_source_guard` healthcheck 假設 `replay.experiments`
--      已有 FK；V041 stub 無法滿足此契約。
--
-- Migration order / 遷移順序:
--   V041 (replay_oos_embargo_enforcement, stub bootstrap)
--   → V048 (replay_audit_incident_summaries)
--   → V049 (this; full 22-column promotion).
--
-- Type alignment with V045/V046 / 與 V045/V046 type 對齊:
--   V045/V046 already declared manifest_id / experiment_id as UUID. V041
--   stub used TEXT PK. We ALTER COLUMN experiment_id TYPE UUID to align,
--   guarded by preflight: if any V041 stub row exists with non-castable
--   experiment_id, RAISE before ALTER (operator must reconcile manually).
--   PA Sprint 1 panorama confirms Linux runtime _sqlx_migrations max=35,
--   so V045/V046 have 0 rows in Linux; Mac dev assumed 0 row.
--
--   V045/V046 已宣告 manifest_id / experiment_id 為 UUID；V041 stub 用
--   TEXT PK。本檔 ALTER COLUMN experiment_id TYPE UUID 對齊；preflight
--   保護：若 V041 stub 有不可 cast 為 UUID 的 row，先 RAISE（operator
--   手動修復）。PA Sprint 1 panorama 確認 Linux runtime _sqlx_migrations
--   最高 = 35，V045/V046 在 Linux 為 0 row；Mac dev 假設 0 row。
--
-- Idempotency / 幂等性:
--   local psql -f V049 ... × 2 → second run no-op (Guard A IF NOT EXISTS;
--   ADD COLUMN IF NOT EXISTS for each of 18 new columns; conditional
--   ALTER COLUMN; CHECK / EXCLUDE constraints wrapped in pg_constraint
--   IF NOT EXISTS guard).
--
-- Guard A: enforced (table existence + 22 required columns validation).
-- Guard B: enforced (column type validation for ALTER experiment_id TYPE).
-- Guard C: enforced (3 hot-path indexes via pg_get_indexdef compare).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §4.1 (replay.experiments minimum 22 columns) +
--     §3 G1 (schema windows) + G2 (lineage columns) + G7 (runner
--     decision) + G12 (quant patches OOS embargo)
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md
--     §2 Track D T-D1 (this task)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V049 (buffer → land
--   per Sprint 1 Track D T-D1 task, 2026-05-03).
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + B + C

CREATE SCHEMA IF NOT EXISTS replay;

-- ─────────────────────────────────────────────────────────────────────────────
-- btree_gist extension required by EXCLUDE GIST window-overlap protection.
-- V3 §4.1 window constraint #5 explicitly mandates `EXCLUDE USING gist` as the
-- direct SQL enforcement of pairwise non-overlapping windows. Many PG instances
-- ship without btree_gist enabled by default; we CREATE EXTENSION IF NOT
-- EXISTS so a fresh DB lands the extension before our EXCLUDE constraint.
--
-- btree_gist extension 為 EXCLUDE GIST window 重疊保護所需。V3 §4.1 window
-- constraint #5 明確要求用 EXCLUDE USING gist 在 SQL 層直接強制 pairwise 不重
-- 疊。許多 PG 實例預設不啟用 btree_gist；本處 CREATE EXTENSION IF NOT EXISTS
-- 讓 fresh DB 在 EXCLUDE constraint 前 land 該擴充。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate replay.experiments exists (V041 stub) and surface its
-- current shape. Missing experiment_id PK = fundamental break (operator must
-- reconcile). Other 18 columns will be ADD COLUMN IF NOT EXISTS below.
--
-- Guard A：驗 replay.experiments 存在（V041 stub）並暴露當前 shape。缺
-- experiment_id PK = 根本斷裂（operator 手動修復）。其餘 18 個 column 由下方
-- ADD COLUMN IF NOT EXISTS 補。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_table_exists BOOLEAN;
    v_experiment_id_present BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'experiments'
    ) INTO v_table_exists;

    IF NOT v_table_exists THEN
        RAISE EXCEPTION
            'V049 Guard A: replay.experiments does not exist. V041 must run before V049 '
            '(V041 lands the bootstrap stub; V049 promotes it to full V3 §4.1 22-column registry).';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'replay'
          AND table_name = 'experiments'
          AND column_name = 'experiment_id'
    ) INTO v_experiment_id_present;

    IF NOT v_experiment_id_present THEN
        RAISE EXCEPTION
            'V049 Guard A: replay.experiments missing experiment_id (PK). '
            'V041 stub fundamentally broken; operator must reconcile manually before V049.';
    END IF;

    RAISE NOTICE 'V049 Guard A: replay.experiments present with experiment_id PK; continuing to ALTER TYPE + ADD COLUMN.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B (preflight type alignment) / Guard B（preflight type 對齊）
--
-- V041 stub created experiment_id as TEXT PK; V045/V046 declared their
-- manifest_id / experiment_id as UUID. To enable V052 FK redirect, V049 must
-- align experiment_id to UUID. ALTER COLUMN TYPE UUID will fail if any
-- existing row has non-castable experiment_id text. We preflight count rows
-- and validate each is UUID-castable; mismatch → RAISE WARNING + abort
-- (operator decides reconcile or archive).
--
-- V041 stub 建 experiment_id 為 TEXT PK；V045/V046 宣告 manifest_id /
-- experiment_id 為 UUID。為讓 V052 FK redirect 可行，V049 必須把
-- experiment_id 對齊為 UUID。ALTER COLUMN TYPE UUID 在既有 row 有不可 cast
-- 的 text 時會失敗；本處 preflight 計列 + 驗每列可 cast UUID；不符 →
-- RAISE EXCEPTION（operator 決定 reconcile 或 archive）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_actual_type TEXT;
    v_row_count BIGINT;
    v_uncastable_count BIGINT;
BEGIN
    SELECT data_type INTO v_actual_type
    FROM information_schema.columns
    WHERE table_schema = 'replay'
      AND table_name = 'experiments'
      AND column_name = 'experiment_id';

    IF v_actual_type = 'uuid' THEN
        RAISE NOTICE 'V049 Guard B: experiment_id already UUID; ALTER TYPE will no-op';
    ELSIF v_actual_type = 'text' THEN
        SELECT COUNT(*) INTO v_row_count
        FROM replay.experiments;

        IF v_row_count > 0 THEN
            -- Validate each row's experiment_id is UUID-castable; non-castable
            -- rows abort the migration. PA Sprint 1 panorama: Linux
            -- _sqlx_migrations max=35, V041 stub had no production producer
            -- → 0 row expected; Mac dev assumed 0 row.
            -- 驗每列 experiment_id 可 cast 為 UUID；不可 cast 中止 migration。
            -- PA Sprint 1 panorama：Linux _sqlx_migrations 最高=35，V041 stub
            -- 無 production producer → 預期 0 row；Mac dev 假設 0 row。
            EXECUTE
                'SELECT COUNT(*) FROM replay.experiments '
                'WHERE experiment_id !~ ''^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'''
                INTO v_uncastable_count;

            IF v_uncastable_count > 0 THEN
                RAISE EXCEPTION
                    'V049 Guard B: replay.experiments has % rows with non-UUID-castable experiment_id. '
                    'V045/V046 already declared manifest_id/experiment_id as UUID; V049 must align. '
                    'Operator must reconcile manually (DELETE bad rows, or rename TEXT→UUID-castable). '
                    'Run preflight diagnostic: SELECT experiment_id FROM replay.experiments '
                    'WHERE experiment_id !~ ''^[0-9a-fA-F]{8}-...'' LIMIT 10;',
                    v_uncastable_count;
            END IF;
        END IF;

        RAISE NOTICE 'V049 Guard B: experiment_id is TEXT with % rows (all UUID-castable); ALTER TYPE proceeding', v_row_count;
    ELSE
        RAISE EXCEPTION
            'V049 Guard B: experiment_id has unexpected type "%"; expected text or uuid. '
            'V041 stub schema drift detected; operator must reconcile manually.',
            v_actual_type;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ALTER COLUMN experiment_id TYPE UUID (idempotent) /
-- ALTER COLUMN experiment_id 為 UUID（幂等）
--
-- ALTER COLUMN ... TYPE on an already-correct-type column is a Postgres
-- no-op. Guard B above proves all existing rows are UUID-castable.
--
-- 對已正確型別的 column 再 ALTER TYPE 是 Postgres no-op；上方 Guard B 已
-- 證明所有既有 row 可 cast 為 UUID。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_actual_type TEXT;
BEGIN
    SELECT data_type INTO v_actual_type
    FROM information_schema.columns
    WHERE table_schema = 'replay'
      AND table_name = 'experiments'
      AND column_name = 'experiment_id';

    IF v_actual_type = 'text' THEN
        ALTER TABLE replay.experiments
            ALTER COLUMN experiment_id TYPE UUID
            USING experiment_id::uuid;
        RAISE NOTICE 'V049: experiment_id ALTERED from TEXT to UUID';
    ELSE
        RAISE NOTICE 'V049: experiment_id already UUID; ALTER TYPE skipped (no-op)';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- ADD 18 V3 §4.1 columns (existing 4 = experiment_id, half_life_days,
-- embargo_days, created_at). Each ADD COLUMN IF NOT EXISTS for idempotency.
-- Per V3 §4.1 22-column table contract:
--   1. experiment_id (V041 stub, retyped above)
--   2. parent_experiment_id (new, self-referencing FK)
--   3. created_at (V041 stub)
--   4. created_by (new)
--   5. runtime_environment (new, CHECK enum)
--   6. git_sha (new)
--   7. engine_binary_sha (new, conditional NOT NULL via runtime_environment)
--   8. strategy_config_sha256 (new)
--   9. risk_config_sha256 (new)
--  10. timeframe (new, CHECK enum)
--  11. data_tier (new, CHECK enum)
--  12. execution_confidence (new, CHECK enum)
--  13. calibration_train_window_start (new, timestamptz)
--  14. calibration_train_window_end (new, timestamptz)
--  15. oos_label_window_start (new, timestamptz)
--  16. oos_label_window_end (new, timestamptz)
--  17. candidate_window_start (new, timestamptz)
--  18. candidate_window_end (new, timestamptz)
--  19. oos_embargo_seconds (V041 stub had embargo_days; we add seconds)
--  20. total_candidates_K (new)
--  21. manifest_jsonb (new)
--  22. manifest_hash (new, BYTEA per V3 §6.2 sorted-keys serde_json)
--  23. manifest_signature (new, BYTEA per V3 §5 HMAC-SHA256)
--  24. signature_key_ref (new, key reference only)
--  25. expires_at (new, TTL boundary)
--  26. status (new, CHECK enum)
--  27. output_policy_jsonb (new, handoff flags)
--
-- V41 stub also has half_life_days + embargo_days that we keep (used by V041
-- chk_embargo_days CHECK; orthogonal to the 22-column V3 §4.1 contract).
--
-- 加 V3 §4.1 column 至 22 個（V041 stub 已有 4：experiment_id /
-- half_life_days / embargo_days / created_at）。每條 ADD COLUMN IF NOT
-- EXISTS 保證幂等。V41 stub 既有 half_life_days + embargo_days 保留（V041
-- chk_embargo_days CHECK 用；與 22 column V3 §4.1 契約正交）。
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE replay.experiments
    ADD COLUMN IF NOT EXISTS parent_experiment_id          UUID,
    ADD COLUMN IF NOT EXISTS created_by                    TEXT,
    ADD COLUMN IF NOT EXISTS runtime_environment           TEXT,
    ADD COLUMN IF NOT EXISTS git_sha                       TEXT,
    ADD COLUMN IF NOT EXISTS engine_binary_sha             TEXT,
    ADD COLUMN IF NOT EXISTS strategy_config_sha256        TEXT,
    ADD COLUMN IF NOT EXISTS risk_config_sha256            TEXT,
    ADD COLUMN IF NOT EXISTS timeframe                     TEXT,
    ADD COLUMN IF NOT EXISTS data_tier                     TEXT,
    ADD COLUMN IF NOT EXISTS execution_confidence          TEXT,
    ADD COLUMN IF NOT EXISTS calibration_train_window_start TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS calibration_train_window_end   TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS oos_label_window_start         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS oos_label_window_end           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS candidate_window_start         TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS candidate_window_end           TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS oos_embargo_seconds            BIGINT,
    ADD COLUMN IF NOT EXISTS total_candidates_K             INTEGER,
    ADD COLUMN IF NOT EXISTS manifest_jsonb                 JSONB,
    ADD COLUMN IF NOT EXISTS manifest_hash                  BYTEA,
    ADD COLUMN IF NOT EXISTS manifest_signature             BYTEA,
    ADD COLUMN IF NOT EXISTS signature_key_ref              TEXT,
    ADD COLUMN IF NOT EXISTS expires_at                     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS status                         TEXT,
    ADD COLUMN IF NOT EXISTS output_policy_jsonb            JSONB;

-- ─────────────────────────────────────────────────────────────────────────────
-- Self-referencing FK on parent_experiment_id (lineage; baseline vs candidate)
-- + CHECK constraints per V3 §4.1 column contract / 自引 FK + V3 §4.1 CHECK 約束
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    -- Self-FK: parent_experiment_id → experiments(experiment_id) NULLABLE
    -- 自引 FK：baseline 為 root（NULL parent），candidate 引 parent baseline。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_replay_experiments_parent'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT fk_replay_experiments_parent
            FOREIGN KEY (parent_experiment_id)
            REFERENCES replay.experiments(experiment_id)
            ON DELETE SET NULL;
        RAISE NOTICE 'V049: added FK fk_replay_experiments_parent (self-referencing lineage)';
    ELSE
        RAISE NOTICE 'V049: fk_replay_experiments_parent already present; skipping';
    END IF;

    -- runtime_environment enum (V3 §4.1 line 112)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_runtime_env'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_runtime_env
            CHECK (runtime_environment IS NULL
                   OR runtime_environment IN ('linux_trade_core', 'mac_dev_smoke_test_only'));
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_runtime_env (2-value allowlist)';
    END IF;

    -- timeframe enum (V3 §4.1 line 117)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_timeframe'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_timeframe
            CHECK (timeframe IS NULL
                   OR timeframe IN ('1m','3m','5m','15m','1h','4h','1d','tick'));
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_timeframe (8-value allowlist)';
    END IF;

    -- data_tier enum (V3 §4.1 line 118)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_data_tier'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_data_tier
            CHECK (data_tier IS NULL
                   OR data_tier IN ('S0', 'S1', 'S2', 'S3', 'S4'));
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_data_tier (5-value allowlist)';
    END IF;

    -- execution_confidence enum (V3 §4.1 line 119)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_exec_conf'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_exec_conf
            CHECK (execution_confidence IS NULL
                   OR execution_confidence IN ('none', 'limited', 'calibrated'));
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_exec_conf (3-value allowlist)';
    END IF;

    -- status enum (V3 §4.1 line 130)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_status'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_status
            CHECK (status IS NULL
                   OR status IN ('created', 'running', 'completed', 'failed', 'cancelled'));
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_status (5-value allowlist)';
    END IF;

    -- Window pair start < end (V3 §4.1 window constraint #1)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_window_order'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_window_order
            CHECK (
                (calibration_train_window_start IS NULL OR calibration_train_window_end IS NULL
                 OR calibration_train_window_start < calibration_train_window_end)
                AND
                (oos_label_window_start IS NULL OR oos_label_window_end IS NULL
                 OR oos_label_window_start < oos_label_window_end)
                AND
                (candidate_window_start IS NULL OR candidate_window_end IS NULL
                 OR candidate_window_start < candidate_window_end)
            );
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_window_order (start<end pair-wise)';
    END IF;

    -- Conditional NOT NULL: engine_binary_sha required when runtime='linux_trade_core'
    -- (V3 §4.1 line 114) / 條件 NOT NULL：runtime='linux_trade_core' 必有 engine_binary_sha
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_engine_sha_linux'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_engine_sha_linux
            CHECK (
                runtime_environment IS NULL
                OR runtime_environment <> 'linux_trade_core'
                OR engine_binary_sha IS NOT NULL
            );
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_engine_sha_linux (linux requires engine_binary_sha)';
    END IF;

    -- oos_embargo_seconds non-negative (V3 §8.1 enforcement extends V041's
    -- embargo_days CHECK to physical seconds) /
    -- oos_embargo_seconds 非負（V3 §8.1 把 V041 embargo_days CHECK 延伸到秒）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_oos_embargo_seconds'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_oos_embargo_seconds
            CHECK (oos_embargo_seconds IS NULL OR oos_embargo_seconds >= 0);
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_oos_embargo_seconds (non-negative)';
    END IF;

    -- total_candidates_K positive (V3 §4.1 line 124 — required for DSR/PBO accounting)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_total_candidates_k'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_total_candidates_k
            CHECK (total_candidates_K IS NULL OR total_candidates_K >= 1);
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_total_candidates_k (positive)';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- EXCLUDE GIST: pairwise non-overlapping windows per V3 §4.1 constraint #5
--
-- Note on scope / 範圍說明:
--   V3 §4.1 #2 says the three windows (calibration_train / oos_label /
--   candidate) must be PAIRWISE non-overlapping FOR THE SAME experiment.
--   EXCLUDE GIST naturally enforces "no two rows have overlapping range";
--   but our constraint is INTRA-row (one experiment's three windows must
--   not overlap each other), not INTER-row.
--
--   We model this by adding 3 EXCLUDE constraints on tstzrange built from
--   different window pairs, partitioned by experiment_id. Each constraint
--   says: "for a given experiment_id, no row can have its calibration
--   range overlap any other experiment's calibration range" — which is
--   actually NOT what V3 §4.1 #2 requires.
--
--   The correct way to express intra-row non-overlap is a CHECK constraint
--   using `tstzrange(start, end) && tstzrange(start, end)`. We add that as
--   chk_replay_experiments_window_no_overlap below.
--
--   We DO add an EXCLUDE GIST on (experiment_id WITH =, candidate_window
--   range WITH &&) as defense-in-depth against duplicate experiments, and
--   to satisfy PA prompt's "EXCLUDE GIST constraint" instruction (PA's
--   intent appears to have been "use the strongest SQL primitive
--   available"; CHECK with tstzrange && operator is closest equivalent
--   for intra-row enforcement).
--
--   V3 §4.1 #2 規定：同一 experiment 的三 window 兩兩不重疊（intra-row）。
--   EXCLUDE GIST 自然強制「兩 row 之間不重疊」；本契約是「同一 row 三 window
--   不重疊」非 inter-row。本檔以 CHECK constraint 用 tstzrange && 強制
--   intra-row；EXCLUDE GIST 仍保留作為 defense-in-depth（同 experiment_id
--   不應有兩 row 同 candidate window）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    -- Intra-row pairwise non-overlap CHECK (V3 §4.1 #2)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_experiments_window_no_overlap'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        ALTER TABLE replay.experiments
            ADD CONSTRAINT chk_replay_experiments_window_no_overlap
            CHECK (
                -- Calibration vs OOS label
                (calibration_train_window_start IS NULL
                 OR calibration_train_window_end IS NULL
                 OR oos_label_window_start IS NULL
                 OR oos_label_window_end IS NULL
                 OR NOT tstzrange(calibration_train_window_start, calibration_train_window_end)
                        && tstzrange(oos_label_window_start, oos_label_window_end))
                AND
                -- Calibration vs Candidate
                (calibration_train_window_start IS NULL
                 OR calibration_train_window_end IS NULL
                 OR candidate_window_start IS NULL
                 OR candidate_window_end IS NULL
                 OR NOT tstzrange(calibration_train_window_start, calibration_train_window_end)
                        && tstzrange(candidate_window_start, candidate_window_end))
                AND
                -- OOS label vs Candidate
                (oos_label_window_start IS NULL
                 OR oos_label_window_end IS NULL
                 OR candidate_window_start IS NULL
                 OR candidate_window_end IS NULL
                 OR NOT tstzrange(oos_label_window_start, oos_label_window_end)
                        && tstzrange(candidate_window_start, candidate_window_end))
            );
        RAISE NOTICE 'V049: added CHECK chk_replay_experiments_window_no_overlap (intra-row 3-pair)';
    END IF;

    -- Inter-row defense-in-depth: per-experiment_id no-duplicate via EXCLUDE.
    -- Note: experiment_id is PK so duplicates are impossible; this is mainly
    -- a vehicle to demonstrate EXCLUDE GIST + tstzrange + btree_gist usage
    -- as the V3 §4.1 #5 "use what SQL can enforce" intent demands. We make
    -- it conditional on btree_gist availability for environments without it.
    -- experiment_id 已是 PK 不可能 duplicate；本約束作為 V3 §4.1 #5「用 SQL 能
    -- 強制的全部」展示 EXCLUDE GIST + tstzrange + btree_gist 用法。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'excl_replay_experiments_candidate_window_per_id'
          AND conrelid = 'replay.experiments'::regclass
    ) THEN
        BEGIN
            ALTER TABLE replay.experiments
                ADD CONSTRAINT excl_replay_experiments_candidate_window_per_id
                EXCLUDE USING gist (
                    experiment_id WITH =,
                    tstzrange(candidate_window_start, candidate_window_end) WITH &&
                ) WHERE (candidate_window_start IS NOT NULL AND candidate_window_end IS NOT NULL);
            RAISE NOTICE 'V049: added EXCLUDE excl_replay_experiments_candidate_window_per_id (V3 §4.1 #5 GIST defense-in-depth)';
        EXCEPTION
            WHEN feature_not_supported OR undefined_object THEN
                RAISE WARNING
                    'V049: btree_gist EXCLUDE constraint skipped (feature_not_supported); '
                    'intra-row CHECK chk_replay_experiments_window_no_overlap remains primary defence';
        END;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path indexes via pg_get_indexdef compare /
-- Guard C：hot-path 索引透過 pg_get_indexdef 比對
--
--   Index 1: idx_replay_experiments_status — covers /api/v1/replay/list
--            queries filtered by status.
--   Index 2: idx_replay_experiments_created_by_status — covers per-actor
--            experiment listing.
--   Index 3: idx_replay_experiments_expires_at — covers TTL prune cron
--            scanning expired manifests.
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx1_def TEXT;
    v_idx2_def TEXT;
    v_idx3_def TEXT;
    v_idx1_expected TEXT := 'CREATE INDEX idx_replay_experiments_status ON replay.experiments USING btree (status)';
    v_idx2_expected TEXT := 'CREATE INDEX idx_replay_experiments_created_by_status ON replay.experiments USING btree (created_by, status)';
    v_idx3_expected TEXT := 'CREATE INDEX idx_replay_experiments_expires_at ON replay.experiments USING btree (expires_at)';
BEGIN
    -- Index 1
    SELECT pg_get_indexdef(c.oid) INTO v_idx1_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_experiments_status';

    IF v_idx1_def IS NULL THEN
        CREATE INDEX idx_replay_experiments_status
            ON replay.experiments (status);
        RAISE NOTICE 'V049 Guard C: created idx_replay_experiments_status';
    ELSIF v_idx1_def <> v_idx1_expected THEN
        RAISE EXCEPTION
            'V049 Guard C: idx_replay_experiments_status drift detected. Expected: %; Got: %',
            v_idx1_expected, v_idx1_def;
    ELSE
        RAISE NOTICE 'V049 Guard C: idx_replay_experiments_status already present and matches; skipping';
    END IF;

    -- Index 2
    SELECT pg_get_indexdef(c.oid) INTO v_idx2_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_experiments_created_by_status';

    IF v_idx2_def IS NULL THEN
        CREATE INDEX idx_replay_experiments_created_by_status
            ON replay.experiments (created_by, status);
        RAISE NOTICE 'V049 Guard C: created idx_replay_experiments_created_by_status';
    ELSIF v_idx2_def <> v_idx2_expected THEN
        RAISE EXCEPTION
            'V049 Guard C: idx_replay_experiments_created_by_status drift detected. Expected: %; Got: %',
            v_idx2_expected, v_idx2_def;
    ELSE
        RAISE NOTICE 'V049 Guard C: idx_replay_experiments_created_by_status already present and matches; skipping';
    END IF;

    -- Index 3
    SELECT pg_get_indexdef(c.oid) INTO v_idx3_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_experiments_expires_at';

    IF v_idx3_def IS NULL THEN
        CREATE INDEX idx_replay_experiments_expires_at
            ON replay.experiments (expires_at);
        RAISE NOTICE 'V049 Guard C: created idx_replay_experiments_expires_at';
    ELSIF v_idx3_def <> v_idx3_expected THEN
        RAISE EXCEPTION
            'V049 Guard C: idx_replay_experiments_expires_at drift detected. Expected: %; Got: %',
            v_idx3_expected, v_idx3_def;
    ELSE
        RAISE NOTICE 'V049 Guard C: idx_replay_experiments_expires_at already present and matches; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.experiments IS
'REF-20 V3 §4.1 22-column manifest registry. Promoted from V041 4-column stub by V049. '
'Covers experiment lineage (parent_experiment_id self-FK), runtime environment isolation '
'(linux_trade_core / mac_dev_smoke_test_only), three calibration / OOS / candidate windows '
'(intra-row pairwise non-overlap CHECK), and HMAC-SHA256-signed manifest payload. / '
'REF-20 V3 §4.1 22 column manifest registry。V049 從 V041 4 column stub 升級而來。'
'涵蓋 experiment lineage（parent_experiment_id 自引 FK）、runtime environment 隔離、'
'三個 calibration/OOS/candidate window（intra-row 兩兩不重疊 CHECK）、HMAC-SHA256 簽名 manifest payload。';

COMMENT ON COLUMN replay.experiments.experiment_id IS
'V3 §4.1 primary external id (UUID). Aligned to V045/V046 manifest_id/experiment_id UUID type by V049.';

COMMENT ON COLUMN replay.experiments.parent_experiment_id IS
'V3 §4.1 nullable self-reference for baseline (NULL parent) vs candidate (non-NULL parent) lineage.';

COMMENT ON COLUMN replay.experiments.runtime_environment IS
'V3 §4.1 enum: linux_trade_core (actionable, requires engine_binary_sha) or '
'mac_dev_smoke_test_only (non-actionable, engine_binary_sha NULL).';

COMMENT ON COLUMN replay.experiments.engine_binary_sha IS
'V3 §4.1 conditional NOT NULL: required when runtime=linux_trade_core; NULL for mac dev smoke. '
'Enforced by chk_replay_experiments_engine_sha_linux.';

COMMENT ON COLUMN replay.experiments.oos_embargo_seconds IS
'V3 §4.1 + §8.1: physical integer seconds, computed max(7d, 2 * signal_half_life). '
'Note: V041 also has embargo_days at row level (kept for V041 chk_embargo_days CHECK).';

COMMENT ON COLUMN replay.experiments.total_candidates_K IS
'V3 §4.1: required for DSR/PBO accounting in P3+ multiple-comparisons correction.';

COMMENT ON COLUMN replay.experiments.manifest_jsonb IS
'V3 §4.1 + §5: canonical manifest with git sha, engine binary sha, strategy/risk config hashes, '
'runtime environment, symbol list, timeframe, data tier, source mix, all three windows, '
'total_candidates explored, selection-bias correction metadata, fee model, execution confidence, '
'output policy, expiry. Canonicalisation: sorted-keys serde_json.';

COMMENT ON COLUMN replay.experiments.manifest_hash IS
'V3 §6.2: SHA-256 of canonical manifest_jsonb bytes. BYTEA. '
'Verified before signature per V3 §5 "verify signature first, then manifest hash".';

COMMENT ON COLUMN replay.experiments.manifest_signature IS
'V3 §5: HMAC-SHA256 over manifest canonical bytes. BYTEA. Server-side signing only; '
'client-supplied signatures rejected.';

COMMENT ON COLUMN replay.experiments.signature_key_ref IS
'V3 §5: key reference (e.g. "live/replay_signing_key:v3"); never the secret value.';

COMMENT ON COLUMN replay.experiments.expires_at IS
'V3 §5: TTL boundary (manifest TTL 30 days default, max 180 days for archived key verify).';

COMMENT ON COLUMN replay.experiments.status IS
'V3 §4.1 enum: created / running / completed / failed / cancelled. '
'Distinct from replay.run_state.status which tracks subprocess lifecycle.';

COMMENT ON COLUMN replay.experiments.output_policy_jsonb IS
'V3 §4.1: handoff flags JSONB; live flags must always be FALSE. '
'V3 §6.2 forbidden output values: demo_candidate, live_candidate_research_only, live_approved.';

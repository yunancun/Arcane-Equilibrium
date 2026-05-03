-- V047__replay_business_kpi_snapshots.sql
-- REF-20 Wave 9 R20-W9-T2 (Business KPI 7d/14d collection)
--
-- Purpose / 目的:
--   Create replay.business_kpi_snapshots to persist per-day P6 KPI samples
--   collected by `wave9_business_kpi_collector.py` cron. Each cron cycle
--   writes one row per (snapshot_date, window_type, kpi_name) triple — the
--   collector samples the V3 §11 P6 KPI list (replay routes daily request
--   count, manifest verify 4 fail-mode breakdown, handoff success rate,
--   quota cap hit rate, cost_edge_ratio distribution, DSR/PBO gate fire
--   rate) on a 7-day or 14-day window.
--
--   建立 replay.business_kpi_snapshots 持久化每日 P6 KPI 樣本，供
--   `wave9_business_kpi_collector.py` cron 寫入。每個 cron cycle 為每個
--   (snapshot_date, window_type, kpi_name) 三元組寫一 row — collector 在
--   7 天或 14 天窗口採樣 V3 §11 P6 KPI 名單。
--
-- Rationale for separate table / 為何獨立表:
--   - V3 §11 P6 KPI 名單跨 6+ 子系統（routes count / manifest verify /
--     handoff / quota / cost_edge / DSR-PBO），分散於不同 schema。
--     Centralising into a snapshot table 讓 dashboard 查詢 + drift 比較
--     可單表 JOIN。
--   - Daily snapshot 可在「事故發生後」回看「事故發生前 7 天」的 KPI 漂移；
--     源頭表有些是 hot-path（高頻、TTL 短），不適合做 14d retention。
--   - V045 / V046 / V044 都是 runtime 數據；KPI snapshot 是 analytics 層。
--
--   - V3 §11 P6 KPI list spans 6+ subsystems (routes / manifest verify /
--     handoff / quota / cost_edge / DSR-PBO). Centralising into a snapshot
--     table allows dashboard JOINs + drift comparison.
--   - Post-incident drift inspection looks at pre-incident 7d window;
--     source tables are some hot-path (high-frequency, short TTL).
--   - V044/V045/V046 are runtime data; KPI snapshot is analytics layer.
--
-- Migration order / 遷移順序:
--   V046 (replay_report_artifacts) → V047 (this).
--   No FK to V044/V045/V046 — KPI rows are derived analytics; the source
--   data may have been TTL-pruned by the time KPI is sampled.
--
--   不對 V044/V045/V046 加 FK — KPI row 是衍生 analytics；採樣時源資料可能
--   已被 TTL prune。
--
-- Idempotency / 幂等性:
--   local psql -f V047 ... × 2 → second run no-op (Guard A IF NOT EXISTS;
--   Guard C compares index defs before re-creating).
--   UNIQUE(snapshot_date, window_type, kpi_name) prevents duplicate
--   inserts from accidental cron re-run within the same day.
--
-- Guard A: enforced (table existence + required columns validation).
-- Guard B: N/A (fresh CREATE, no ALTER COLUMN).
-- Guard C: enforced (1 hot-path index via pg_get_indexdef compare).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §11 P6 Business KPI list +
--     §12 acceptance #14 (replay_no_live_mutation continuous)
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
--     §4 Wave 9 row 2 (Business KPI 7d/14d 採集)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V047 (buffer → land per
--   Wave 9 R20-W9-T2 task, 2026-05-03).
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard C

CREATE SCHEMA IF NOT EXISTS replay;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate schema=replay exists; if table already exists, validate
-- required columns present; missing column → RAISE EXCEPTION.
--
-- Guard A: 驗 schema=replay 存在；若 table 已存在則驗必要欄位俱在；缺即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_schema_exists BOOLEAN;
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'snapshot_id', 'snapshot_date', 'window_type', 'kpi_name',
        'kpi_value', 'sample_size', 'created_at'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'replay'
    ) INTO v_schema_exists;

    IF NOT v_schema_exists THEN
        RAISE EXCEPTION 'V047 Guard A: schema "replay" does not exist; CREATE SCHEMA above failed';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'business_kpi_snapshots'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'replay'
                  AND table_name = 'business_kpi_snapshots'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V047 Guard A: replay.business_kpi_snapshots exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;
        RAISE NOTICE 'V047 Guard A: replay.business_kpi_snapshots already present with all required columns; CREATE TABLE IF NOT EXISTS will no-op';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- CREATE TABLE replay.business_kpi_snapshots / 建立表
--
-- Column contract / 欄位契約:
--   snapshot_id    UUID PK; server-generated.
--   snapshot_date  DATE NOT NULL; the date the cron ran (UTC).
--   window_type    TEXT NOT NULL; '7d' or '14d' (CHECK enforced).
--   kpi_name       TEXT NOT NULL; identifier from V3 §11 P6 KPI list
--                  (e.g. 'replay_routes_daily_request_count',
--                  'manifest_verify_fail_mode_breakdown',
--                  'handoff_success_rate', 'quota_cap_hit_rate',
--                  'cost_edge_ratio_p50', 'dsr_pbo_gate_fire_rate').
--   kpi_value      DOUBLE PRECISION NULLable; numeric KPI value.
--                  NULL when KPI is composite (e.g. fail-mode breakdown
--                  uses sample_size + sub-key counts only — caller stores
--                  the composite as multiple rows).
--   sample_size    INT NULLable; n underlying the KPI computation.
--   created_at     TIMESTAMPTZ DEFAULT NOW(); insertion timestamp.
--
-- 欄位契約：
--   snapshot_id    UUID PK；server 端生成。
--   snapshot_date  DATE NOT NULL；cron 跑日期（UTC）。
--   window_type    TEXT NOT NULL；'7d' 或 '14d'（CHECK 強制）。
--   kpi_name       TEXT NOT NULL；V3 §11 P6 KPI 名單識別字。
--   kpi_value      DOUBLE PRECISION NULL；數值 KPI（複合 KPI 為 NULL）。
--   sample_size    INT NULL；KPI 計算使用 n。
--   created_at     TIMESTAMPTZ DEFAULT NOW()；插入時間。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replay.business_kpi_snapshots (
    snapshot_id    UUID PRIMARY KEY,
    snapshot_date  DATE NOT NULL,
    window_type    TEXT NOT NULL,
    kpi_name       TEXT NOT NULL,
    kpi_value      DOUBLE PRECISION,
    sample_size    INT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add UNIQUE + CHECK constraints conditionally so re-runs don't error.
-- 條件式加 UNIQUE + CHECK 約束，重跑不報錯。
DO $$
BEGIN
    -- UNIQUE(snapshot_date, window_type, kpi_name) — prevents duplicate
    -- daily snapshots from accidental cron re-run.
    -- UNIQUE 防同日 cron 重跑寫重複 row。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_kpi_snapshot_date_window_name'
          AND conrelid = 'replay.business_kpi_snapshots'::regclass
    ) THEN
        ALTER TABLE replay.business_kpi_snapshots
            ADD CONSTRAINT uq_kpi_snapshot_date_window_name
            UNIQUE (snapshot_date, window_type, kpi_name);
        RAISE NOTICE 'V047: added UNIQUE constraint uq_kpi_snapshot_date_window_name';
    ELSE
        RAISE NOTICE 'V047: uq_kpi_snapshot_date_window_name already present; skipping ADD CONSTRAINT';
    END IF;

    -- window_type CHECK enum (2 values).
    -- window_type CHECK enum（2 值）。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_kpi_window_type'
          AND conrelid = 'replay.business_kpi_snapshots'::regclass
    ) THEN
        ALTER TABLE replay.business_kpi_snapshots
            ADD CONSTRAINT chk_kpi_window_type
            CHECK (window_type IN ('7d', '14d'));
        RAISE NOTICE 'V047: added CHECK constraint chk_kpi_window_type (2-value allowlist)';
    ELSE
        RAISE NOTICE 'V047: chk_kpi_window_type already present; skipping ADD CONSTRAINT';
    END IF;

    -- sample_size >= 0 (defensive).
    -- sample_size >= 0（防禦）。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_kpi_sample_size_nonneg'
          AND conrelid = 'replay.business_kpi_snapshots'::regclass
    ) THEN
        ALTER TABLE replay.business_kpi_snapshots
            ADD CONSTRAINT chk_kpi_sample_size_nonneg
            CHECK (sample_size IS NULL OR sample_size >= 0);
        RAISE NOTICE 'V047: added CHECK constraint chk_kpi_sample_size_nonneg';
    ELSE
        RAISE NOTICE 'V047: chk_kpi_sample_size_nonneg already present; skipping ADD CONSTRAINT';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path index via pg_get_indexdef compare.
--   Index 1: idx_kpi_snapshot_date_window — covers dashboard query
--            `SELECT ... FROM replay.business_kpi_snapshots
--             WHERE snapshot_date BETWEEN ... AND ... AND window_type=?
--             ORDER BY snapshot_date DESC`.
--
-- Guard C：hot-path index via pg_get_indexdef 比對。
--   Index 1：idx_kpi_snapshot_date_window — 覆蓋 dashboard 查詢。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx_def TEXT;
    v_idx_expected TEXT := 'CREATE INDEX idx_kpi_snapshot_date_window ON replay.business_kpi_snapshots USING btree (snapshot_date DESC, window_type)';
BEGIN
    SELECT pg_get_indexdef(c.oid) INTO v_idx_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_kpi_snapshot_date_window';

    IF v_idx_def IS NULL THEN
        CREATE INDEX idx_kpi_snapshot_date_window
            ON replay.business_kpi_snapshots (snapshot_date DESC, window_type);
        RAISE NOTICE 'V047 Guard C: created idx_kpi_snapshot_date_window (dashboard hot path)';
    ELSIF v_idx_def <> v_idx_expected THEN
        RAISE EXCEPTION
            'V047 Guard C: idx_kpi_snapshot_date_window drift detected. Expected: %; Got: %',
            v_idx_expected, v_idx_def;
    ELSE
        RAISE NOTICE 'V047 Guard C: idx_kpi_snapshot_date_window already present and matches; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.business_kpi_snapshots IS
'REF-20 V3 Wave 9 R20-W9-T2 P6 business KPI 7d/14d snapshot table. '
'Daily cron (`wave9_business_kpi_collector.py`) writes one row per '
'(snapshot_date, window_type, kpi_name) triple. Surfaces in dashboard '
'+ drift inspection. / '
'REF-20 V3 Wave 9 R20-W9-T2 P6 業務 KPI 7d/14d 快照表；每日 cron 寫一 row '
'per (snapshot_date, window_type, kpi_name)；dashboard + drift 查看。';

COMMENT ON COLUMN replay.business_kpi_snapshots.snapshot_id IS
'Server-generated UUID primary key.';

COMMENT ON COLUMN replay.business_kpi_snapshots.snapshot_date IS
'Date the cron ran (UTC). Indexed for time-range dashboard queries.';

COMMENT ON COLUMN replay.business_kpi_snapshots.window_type IS
'Rolling window size: 7d or 14d. CHECK chk_kpi_window_type enforces.';

COMMENT ON COLUMN replay.business_kpi_snapshots.kpi_name IS
'KPI identifier from V3 §11 P6 KPI list (e.g. handoff_success_rate).';

COMMENT ON COLUMN replay.business_kpi_snapshots.kpi_value IS
'Numeric KPI value (NULL for composite KPIs stored as multiple rows).';

COMMENT ON COLUMN replay.business_kpi_snapshots.sample_size IS
'n underlying the KPI computation. NULL when not applicable.';

COMMENT ON COLUMN replay.business_kpi_snapshots.created_at IS
'Insertion timestamp (UTC). Distinct from snapshot_date when cron runs '
'cross-midnight.';

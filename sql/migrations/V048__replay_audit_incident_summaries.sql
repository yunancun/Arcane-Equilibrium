-- V048__replay_audit_incident_summaries.sql
-- REF-20 Wave 9 R20-W9-T3 (governance_audit_log 14d 0 incident scan)
--
-- Purpose / 目的:
--   Create replay.audit_incident_summaries to persist daily 14-day incident
--   scan results from `wave9_audit_incident_scan.py` cron. Each cron cycle
--   queries learning.governance_audit_log for high-severity events in the
--   rolling 14-day window and writes one row per (scan_date, severity,
--   event_type) tuple — when count > 0 — for operator dashboards and
--   post-incident drift analysis.
--
--   建立 replay.audit_incident_summaries 持久化每日 14d incident scan 結果，
--   供 `wave9_audit_incident_scan.py` cron 寫入。每個 cron cycle 對
--   learning.governance_audit_log 14d 窗口查 high-severity event；count > 0
--   時寫一 row per (scan_date, severity, event_type) tuple，供 operator
--   dashboard 與 post-incident drift 分析。
--
-- Why a separate table / 為何獨立表:
--   - learning.governance_audit_log is the raw event sink (V035, hypertable
--     7d chunks). It accumulates many rows per cycle; querying it across
--     the 14d window every dashboard refresh hits a hot path.
--   - replay.audit_incident_summaries pre-computes the daily 14d scan into
--     a thin lookup table for dashboard JOIN/filter speed.
--   - When 14d scan finds 0 incidents, NO row is written — preserving
--     "0 incident = 0 row" invariant for monitoring (any presence of a
--     row in this table means an incident was detected on that scan_date).
--
--   - learning.governance_audit_log 是原始 event sink（V035，hypertable 7d
--     chunk），cycle 累積多 row；每次 dashboard 刷新跨 14d 查熱路徑。
--   - replay.audit_incident_summaries 預計算每日 14d scan，加快 dashboard
--     JOIN/filter。
--   - 14d scan 找到 0 incident 時 **不**寫 row — 保留「0 incident = 0 row」
--     不變量（本表有 row = 該 scan_date 偵測到 incident）。
--
-- Migration order / 遷移順序:
--   V047 (replay_business_kpi_snapshots) → V048 (this).
--   No FK to V035 governance_audit_log — incidents are aggregate summaries;
--   the source rows may have been TimescaleDB-pruned by retention policy
--   when summary is queried. We DO copy `first_incident_ts` /
--   `last_incident_ts` / `sample_payload` for forensic inspection.
--
--   不對 V035 加 FK — incident 是聚合摘要；查詢時源 row 可能已被 TimescaleDB
--   保留策略 prune；故複製 first/last_incident_ts + sample_payload 供 forensic。
--
-- Idempotency / 幂等性:
--   local psql -f V048 ... × 2 → second run no-op (Guard A IF NOT EXISTS;
--   Guard C compares index defs).
--   Cron-side idempotency: `wave9_audit_incident_scan.py` uses ON CONFLICT
--   (scan_date, severity, event_type) DO UPDATE so re-running same day
--   refreshes counts without duplicating.
--
-- Guard A: enforced (table existence + required columns validation).
-- Guard B: N/A (fresh CREATE, no ALTER COLUMN).
-- Guard C: enforced (1 hot-path index via pg_get_indexdef compare).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §11 P6 KPI: 14d gradient 0 incident +
--     §12 acceptance #14 (replay_no_live_mutation continuous)
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
--     §4 Wave 9 row 3 (governance_audit_log 14d 0 incident 驗收)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V048 (buffer → land per
--   Wave 9 R20-W9-T3 task, 2026-05-03).
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
        'summary_id', 'scan_date', 'window_days', 'incident_count',
        'severity', 'event_type', 'first_incident_ts', 'last_incident_ts',
        'sample_payload'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'replay'
    ) INTO v_schema_exists;

    IF NOT v_schema_exists THEN
        RAISE EXCEPTION 'V048 Guard A: schema "replay" does not exist; CREATE SCHEMA above failed';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'audit_incident_summaries'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'replay'
                  AND table_name = 'audit_incident_summaries'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V048 Guard A: replay.audit_incident_summaries exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;
        RAISE NOTICE 'V048 Guard A: replay.audit_incident_summaries already present with all required columns; CREATE TABLE IF NOT EXISTS will no-op';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- CREATE TABLE replay.audit_incident_summaries / 建立表
--
-- Column contract / 欄位契約:
--   summary_id          UUID PK; server-generated.
--   scan_date           DATE NOT NULL; the date the cron ran (UTC).
--   window_days         INT NOT NULL DEFAULT 14; window size (V3 §11 P6 = 14).
--   incident_count      INT NOT NULL; count of high-severity rows in window.
--   severity            TEXT NOT NULL CHECK ('low'/'medium'/'high'/'critical').
--   event_type          TEXT NOT NULL; from V035 event_type CHECK enum
--                       (post-V044): review_live_candidate / lease_grant /
--                       lease_auto_revoke / bulk_re_evaluation /
--                       audit_write_failed / replay_handoff_request.
--                       Wave 9 cron specifically scans for high-severity:
--                         - replay_handoff_request AND payload.result='rejected'
--                         - replay_key_rotation_due (audit_write_failed
--                           with payload.alert_type='replay_key_rotation_due')
--                         - audit_write_failed (any other source)
--   first_incident_ts   TIMESTAMPTZ NULL; ts of earliest incident (NULL allowed
--                       for forward-compat where ts may be lost during
--                       hypertable prune).
--   last_incident_ts    TIMESTAMPTZ NULL; ts of latest incident.
--   sample_payload      JSONB NULL; one representative payload row for the
--                       group (forensic inspection; truncated if too large).
--
-- 欄位契約：
--   summary_id          UUID PK；server 生成。
--   scan_date           DATE NOT NULL；cron 跑日期（UTC）。
--   window_days         INT NOT NULL DEFAULT 14；窗口大小。
--   incident_count      INT NOT NULL；窗口內 high-severity row count。
--   severity            TEXT NOT NULL CHECK；4 enum 嚴重度。
--   event_type          TEXT NOT NULL；V035 enum 之一（post-V044 6 值）。
--   first_incident_ts   TIMESTAMPTZ NULL；最早 incident ts。
--   last_incident_ts    TIMESTAMPTZ NULL；最晚 incident ts。
--   sample_payload      JSONB NULL；代表性 payload（forensic）。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replay.audit_incident_summaries (
    summary_id          UUID PRIMARY KEY,
    scan_date           DATE NOT NULL,
    window_days         INT NOT NULL DEFAULT 14,
    incident_count      INT NOT NULL,
    severity            TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    first_incident_ts   TIMESTAMPTZ,
    last_incident_ts    TIMESTAMPTZ,
    sample_payload      JSONB
);

-- Add UNIQUE + CHECK constraints conditionally so re-runs don't error.
-- 條件式加 UNIQUE + CHECK 約束，重跑不報錯。
DO $$
BEGIN
    -- UNIQUE(scan_date, severity, event_type) — prevents duplicate
    -- daily summaries from cron re-run.
    -- UNIQUE 防同日 cron 重跑寫重複 summary。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_audit_incident_scan_severity_event'
          AND conrelid = 'replay.audit_incident_summaries'::regclass
    ) THEN
        ALTER TABLE replay.audit_incident_summaries
            ADD CONSTRAINT uq_audit_incident_scan_severity_event
            UNIQUE (scan_date, severity, event_type);
        RAISE NOTICE 'V048: added UNIQUE constraint uq_audit_incident_scan_severity_event';
    ELSE
        RAISE NOTICE 'V048: uq_audit_incident_scan_severity_event already present; skipping';
    END IF;

    -- severity CHECK enum (4 values).
    -- severity CHECK enum（4 值）。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_audit_incident_severity'
          AND conrelid = 'replay.audit_incident_summaries'::regclass
    ) THEN
        ALTER TABLE replay.audit_incident_summaries
            ADD CONSTRAINT chk_audit_incident_severity
            CHECK (severity IN ('low', 'medium', 'high', 'critical'));
        RAISE NOTICE 'V048: added CHECK constraint chk_audit_incident_severity (4-value allowlist)';
    ELSE
        RAISE NOTICE 'V048: chk_audit_incident_severity already present; skipping';
    END IF;

    -- incident_count >= 0 (defensive).
    -- incident_count >= 0（防禦）。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_audit_incident_count_nonneg'
          AND conrelid = 'replay.audit_incident_summaries'::regclass
    ) THEN
        ALTER TABLE replay.audit_incident_summaries
            ADD CONSTRAINT chk_audit_incident_count_nonneg
            CHECK (incident_count >= 0);
        RAISE NOTICE 'V048: added CHECK constraint chk_audit_incident_count_nonneg';
    ELSE
        RAISE NOTICE 'V048: chk_audit_incident_count_nonneg already present; skipping';
    END IF;

    -- window_days > 0 (defensive).
    -- window_days > 0（防禦）。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_audit_incident_window_pos'
          AND conrelid = 'replay.audit_incident_summaries'::regclass
    ) THEN
        ALTER TABLE replay.audit_incident_summaries
            ADD CONSTRAINT chk_audit_incident_window_pos
            CHECK (window_days > 0);
        RAISE NOTICE 'V048: added CHECK constraint chk_audit_incident_window_pos';
    ELSE
        RAISE NOTICE 'V048: chk_audit_incident_window_pos already present; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path index via pg_get_indexdef compare.
--   Index 1: idx_audit_incident_scan_date_severity — covers dashboard
--            query `SELECT ... FROM replay.audit_incident_summaries
--            WHERE scan_date >= ... ORDER BY scan_date DESC, severity`.
--
-- Guard C：hot-path index via pg_get_indexdef 比對。
--   Index 1：idx_audit_incident_scan_date_severity — 覆蓋 dashboard 查詢。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx_def TEXT;
    v_idx_expected TEXT := 'CREATE INDEX idx_audit_incident_scan_date_severity ON replay.audit_incident_summaries USING btree (scan_date DESC, severity)';
BEGIN
    SELECT pg_get_indexdef(c.oid) INTO v_idx_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_audit_incident_scan_date_severity';

    IF v_idx_def IS NULL THEN
        CREATE INDEX idx_audit_incident_scan_date_severity
            ON replay.audit_incident_summaries (scan_date DESC, severity);
        RAISE NOTICE 'V048 Guard C: created idx_audit_incident_scan_date_severity (dashboard hot path)';
    ELSIF v_idx_def <> v_idx_expected THEN
        RAISE EXCEPTION
            'V048 Guard C: idx_audit_incident_scan_date_severity drift detected. Expected: %; Got: %',
            v_idx_expected, v_idx_def;
    ELSE
        RAISE NOTICE 'V048 Guard C: idx_audit_incident_scan_date_severity already present and matches; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.audit_incident_summaries IS
'REF-20 V3 Wave 9 R20-W9-T3 14d incident scan summary table. '
'Daily cron (`wave9_audit_incident_scan.py`) writes one row per '
'(scan_date, severity, event_type) when count > 0; absence of a row '
'for a given scan_date/severity/event_type means 0 incidents that day. / '
'REF-20 V3 Wave 9 R20-W9-T3 14d incident scan summary 表；每日 cron '
'count > 0 時寫一 row；無 row = 該日 0 incident。';

COMMENT ON COLUMN replay.audit_incident_summaries.summary_id IS
'Server-generated UUID primary key.';

COMMENT ON COLUMN replay.audit_incident_summaries.scan_date IS
'Date the cron ran (UTC). Indexed for time-range dashboard queries.';

COMMENT ON COLUMN replay.audit_incident_summaries.window_days IS
'Window size (V3 §11 P6 default 14). Configurable for dev/smoke shorter scans.';

COMMENT ON COLUMN replay.audit_incident_summaries.incident_count IS
'Count of incident rows in the window for the (severity, event_type) group.';

COMMENT ON COLUMN replay.audit_incident_summaries.severity IS
'Incident severity: low / medium / high / critical. CHECK chk_audit_incident_severity enforces.';

COMMENT ON COLUMN replay.audit_incident_summaries.event_type IS
'V035 event_type enum value (post-V044 6-value list).';

COMMENT ON COLUMN replay.audit_incident_summaries.first_incident_ts IS
'ts of earliest incident in window (NULL allowed for hypertable-prune scenarios).';

COMMENT ON COLUMN replay.audit_incident_summaries.last_incident_ts IS
'ts of latest incident in window.';

COMMENT ON COLUMN replay.audit_incident_summaries.sample_payload IS
'Representative governance_audit_log.payload for forensic inspection (truncated if oversized).';

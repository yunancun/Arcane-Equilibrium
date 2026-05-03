-- V046__replay_report_artifacts.sql
-- Purpose / 目的:
--   Create replay.report_artifacts to register canary / diagnostic /
--   pnl_summary / fill_log / baseline_compare artifacts written by
--   replay_runner subprocess (or canary_writer.py for non-runtime
--   artifacts). One row per artifact file; the file lives on filesystem
--   under OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/, and DB row stores
--   {run_id, artifact_type, path, byte size}. Wave 4 R20-P2b-T3
--   (canary_writer.py + this schema) lands the registry; Wave 4 R20-P2b-T2
--   (replay_routes.py) reads via GET /report/{experiment_id}.
--
-- 建立 replay.report_artifacts 註冊 replay_runner 子程序（或 canary_writer.py
-- 對 non-runtime artifact）寫的 canary / diagnostic / pnl_summary / fill_log /
-- baseline_compare artifact。一個 file 一列；file 存於 filesystem
-- OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/ 下，DB 列存
-- {run_id, artifact_type, path, byte size}。Wave 4 R20-P2b-T3
-- （canary_writer.py + 本 schema）落地 registry；Wave 4 R20-P2b-T2
-- （replay_routes.py）透過 GET /report/{experiment_id} 讀取。
--
-- Migration order / 遷移順序:
--   V045 (replay_run_state) → V046 (this).
--   FK: artifact_id.run_id REFERENCES replay.run_state(run_id) ON DELETE
--   CASCADE (V045 must land first; cascade ensures stale artifacts get
--   cleaned when run rows are pruned by S5 quota_enforcer cron).
--
--   V045（replay_run_state）→ V046（本檔）。FK：run_id REFERENCES
--   replay.run_state(run_id) ON DELETE CASCADE（V045 必先 land；cascade
--   確保 S5 quota_enforcer cron 清 run_state 列時連帶清 artifact）。
--
-- Idempotency / 幂等性:
--   local psql -f V046 ... × 2 → second run no-op (Guard A IF NOT EXISTS;
--   Guard C compares index defs before re-creating).
--
-- Guard A: enforced (table existence + required columns validation).
-- Guard B: N/A (fresh CREATE, no ALTER COLUMN).
-- Guard C: enforced (1 hot-path index via pg_get_indexdef compare).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §4.1 (replay.report_artifacts minimum schema) +
--     §11 P2b deliverables (canary/diagnostic artifacts registered)
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
--     §4 Wave 4 R20-P2b-T3 (canary/diagnostic artifacts registered Linux only)
--   V3 §12 acceptance #7 replay_registry_fk_contract (artifacts FK to
--     run_state; manifest_id is logical reference only since
--     replay.experiments lives in P2b runner SQL fixture, not a migration)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V046 (buffer → land
--   per Wave 4 R20-P2b-T3 task, 2026-05-03).
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
    v_run_state_exists BOOLEAN;
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'artifact_id', 'run_id', 'artifact_type', 'artifact_path',
        'byte_size', 'is_mock', 'created_at', 'expires_at'
    ];
    v_col TEXT;
BEGIN
    -- Verify V045 prerequisite present (FK target table must exist).
    -- 先驗 V045 前置（FK 目標表必須存在）。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'run_state'
    ) INTO v_run_state_exists;

    IF NOT v_run_state_exists THEN
        RAISE EXCEPTION
            'V046 Guard A: replay.run_state does not exist. V045 must run before V046 '
            '(FK: replay.report_artifacts.run_id REFERENCES replay.run_state).';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'report_artifacts'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'replay'
                  AND table_name = 'report_artifacts'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V046 Guard A: replay.report_artifacts exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;
        RAISE NOTICE 'V046 Guard A: replay.report_artifacts already present with all required columns; continuing to index Guard C';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- CREATE TABLE replay.report_artifacts / 建立 replay.report_artifacts
--
-- Column contract / 欄位契約:
--   artifact_id   UUID primary key (server-generated by canary_writer.py).
--   run_id        UUID FK to replay.run_state(run_id) ON DELETE CASCADE;
--                 stale artifacts get pruned when run rows pruned.
--   artifact_type TEXT enum:
--                   'canary'           — health probe / heartbeat artifact.
--                   'diagnostic'       — debug logs / replay-internal traces.
--                   'pnl_summary'      — aggregated PnL JSON (one per run).
--                   'fill_log'         — per-fill simulated trade log JSONL.
--                   'baseline_compare' — baseline vs candidate metrics JSON.
--                 CHECK enforces allowlist.
--   artifact_path TEXT filesystem path (under OPENCLAW_DATA_DIR/
--                 replay_artifacts/<run_id>/ on Linux; /tmp/
--                 replay_artifacts_test_only/ on Mac dev).
--   byte_size     BIGINT artifact file size; written by canary_writer at
--                 register-time (matches V3 §5 storage cap calculation
--                 used by quota_enforcer.enforce_artifact_storage).
--   is_mock       BOOLEAN true on Mac dev; canary_writer enforces
--                 (Mac path tagged is_mock=true → V3 §6.3 non-actionable).
--   created_at    TIMESTAMPTZ artifact registration timestamp.
--   expires_at    TIMESTAMPTZ inherits or shorter than experiment TTL
--                 (V3 §4.1 "expires_at: inherited or shorter than
--                 experiment TTL"). NULL → never auto-expire (pinned).
--
-- 欄位契約：
--   artifact_id   UUID 主鍵（canary_writer.py 在 server 端生成）。
--   run_id        UUID FK 到 replay.run_state(run_id) ON DELETE CASCADE；
--                 run 列被 prune 時 artifact 連帶清。
--   artifact_type TEXT enum（5 種）；CHECK 強制白名單。
--   artifact_path TEXT filesystem 路徑（Linux：OPENCLAW_DATA_DIR/...；
--                 Mac dev：/tmp/replay_artifacts_test_only/）。
--   byte_size     BIGINT artifact 檔大小；register-time 寫入；對齊 V3 §5
--                 storage cap 計算（quota_enforcer.enforce_artifact_storage 用）。
--   is_mock       BOOLEAN Mac dev 為 true；canary_writer 強制（Mac 路徑
--                 is_mock=true → V3 §6.3 非可採用）。
--   created_at    TIMESTAMPTZ artifact 註冊時間。
--   expires_at    TIMESTAMPTZ 繼承或短於 experiment TTL（V3 §4.1）；NULL
--                 表永不自動 expire（pinned）。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replay.report_artifacts (
    artifact_id   UUID PRIMARY KEY,
    run_id        UUID NOT NULL REFERENCES replay.run_state(run_id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    artifact_path TEXT NOT NULL,
    byte_size     BIGINT NOT NULL DEFAULT 0,
    is_mock       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ
);

-- Add CHECK constraint conditionally for re-run safety.
-- 條件式加 CHECK 約束，重跑安全。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_report_artifacts_type'
          AND conrelid = 'replay.report_artifacts'::regclass
    ) THEN
        ALTER TABLE replay.report_artifacts
            ADD CONSTRAINT chk_replay_report_artifacts_type
            CHECK (artifact_type IN (
                'canary', 'diagnostic', 'pnl_summary',
                'fill_log', 'baseline_compare'
            ));
        RAISE NOTICE 'V046: added CHECK constraint chk_replay_report_artifacts_type (5-value allowlist)';
    ELSE
        RAISE NOTICE 'V046: chk_replay_report_artifacts_type already present; skipping ADD CONSTRAINT';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path index via pg_get_indexdef compare.
--   Index: idx_replay_report_artifacts_run — covers
--   `SELECT artifact_type, artifact_path FROM replay.report_artifacts
--    WHERE run_id = ? ORDER BY created_at` (used by GET /report/{experiment_id}
--    after Wave 4 wires JOIN through replay.run_state).
--
-- Guard C：hot-path 索引透過 pg_get_indexdef 比對。
--   索引：idx_replay_report_artifacts_run — 覆蓋 GET /report/{experiment_id}
--   經 Wave 4 對 replay.run_state JOIN 後的查詢。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx_def TEXT;
    v_idx_expected TEXT := 'CREATE INDEX idx_replay_report_artifacts_run ON replay.report_artifacts USING btree (run_id, created_at)';
BEGIN
    SELECT pg_get_indexdef(c.oid) INTO v_idx_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_report_artifacts_run';

    IF v_idx_def IS NULL THEN
        CREATE INDEX idx_replay_report_artifacts_run
            ON replay.report_artifacts (run_id, created_at);
        RAISE NOTICE 'V046 Guard C: created idx_replay_report_artifacts_run (run_id + created_at composite)';
    ELSIF v_idx_def <> v_idx_expected THEN
        RAISE EXCEPTION
            'V046 Guard C: idx_replay_report_artifacts_run drift detected. Expected: %; Got: %',
            v_idx_expected, v_idx_def;
    ELSE
        RAISE NOTICE 'V046 Guard C: idx_replay_report_artifacts_run already present and matches; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.report_artifacts IS
'REF-20 V3 Wave 4 R20-P2b-T3 canary / diagnostic / pnl_summary / fill_log / '
'baseline_compare artifact registry. One row per file; file lives on filesystem; '
'FK ON DELETE CASCADE to replay.run_state ensures clean prune. / '
'REF-20 V3 Wave 4 R20-P2b-T3 artifact registry；一個 file 一列；file 在 filesystem；'
'FK ON DELETE CASCADE 到 replay.run_state 確保 prune 乾淨。';

COMMENT ON COLUMN replay.report_artifacts.artifact_type IS
'Enum: canary / diagnostic / pnl_summary / fill_log / baseline_compare. CHECK chk_replay_report_artifacts_type enforces.';

COMMENT ON COLUMN replay.report_artifacts.is_mock IS
'TRUE on Mac dev (V3 §6.3 non-actionable); FALSE on Linux trade-core (real artifact).';

COMMENT ON COLUMN replay.report_artifacts.expires_at IS
'V3 §4.1 inherited or shorter than experiment TTL; NULL means pinned (never auto-expire).';

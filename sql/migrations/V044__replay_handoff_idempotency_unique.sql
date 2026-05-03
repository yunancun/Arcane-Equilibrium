-- V044__replay_handoff_idempotency_unique.sql
-- REF-20 R20-P6-S14 (Wave 8 P6 Bounded Demo Handoff backend security trio)
--
-- Purpose / 目的:
--   Create replay.handoff_requests to track P6 demo handoff lifecycle (typed
--   confirmation + cooldown + idempotency + dual-actor) AND extend V035
--   learning.governance_audit_log event_type CHECK enum with the new value
--   'replay_handoff_request' so P6-S15 audit emit can write a fully-typed
--   row (not via 'audit_write_failed' + payload-discriminator fallback).
--
--   建立 replay.handoff_requests 追蹤 P6 demo handoff 生命週期（typed
--   confirmation + cooldown + idempotency + dual-actor），且同 commit 擴
--   V035 learning.governance_audit_log event_type CHECK enum，新增
--   'replay_handoff_request' 值，讓 P6-S15 audit emit 可寫完整型別 row
--   （不必用 'audit_write_failed' + payload-discriminator fallback）。
--
-- Why two operations in one migration / 為何兩動作合一:
--   The handoff request row + the audit row are emitted atomically in the
--   same transaction by P6-S13 _execute_handoff() (see handoff_routes.py
--   docstring). Splitting into two migrations would require separate
--   ledger entries and risk a deploy where the routes IMPL lands but
--   audit emit is rejected by V035 CHECK constraint. Keeping both in
--   V044 lets ledger v1.6 record a single atomic deploy unit.
--
--   handoff request row 與 audit row 由 P6-S13 _execute_handoff() 在同一
--   transaction 內原子寫入。拆兩個 migration 會多一條 ledger 與「routes 已
--   land 但 audit emit 被 V035 CHECK 拒絕」風險。合一 V044 讓 ledger v1.6
--   記錄單一原子 deploy unit。
--
-- Idempotency / 幂等性:
--   local psql -f V044 ... × 2 → second run no-op:
--     1. CREATE SCHEMA IF NOT EXISTS replay (idempotent).
--     2. Guard A no-op when table exists with required columns.
--     3. CREATE TABLE IF NOT EXISTS (idempotent).
--     4. ALTER TABLE ... DROP CONSTRAINT IF EXISTS + ADD CONSTRAINT
--        wrapped in DO $$ ... IF NOT EXISTS-equivalent block (idempotent).
--     5. CREATE INDEX IF NOT EXISTS (idempotent).
--     6. V035 enum extension uses pg_constraint probe + DROP + re-ADD;
--        idempotent because ADD CHECK uses canonical 6-value list.
--
-- Guard A: enforced (table existence + required columns validation per V045 pattern).
-- Guard B: N/A (fresh CREATE TABLE; V035 enum extension is CHECK constraint
--               drop/recreate, not column type ALTER).
-- Guard C: enforced (2 hot-path indexes via pg_get_indexdef compare).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §11 P6 Deliverables (typed confirmation modal + idempotency key + audit
--     row in learning.governance_audit_log) +
--     §12 acceptance #20 (replay_handoff_typed_confirm).
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
--     §4 Wave 8 R20-P6-S13/S14/S15 (security trio).
--   docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md
--     §6 Handoff sub-tab (9 fields + typed phrase + cooldown + dual-actor +
--     idempotency).
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V044 (reserved → land per
--   Wave 8 R20-P6-S14 task, 2026-05-03).
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard C.

CREATE SCHEMA IF NOT EXISTS replay;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate schema=replay exists; if table already exists, validate
-- required columns present; missing column → RAISE EXCEPTION (mirror V045
-- pattern per CLAUDE.md §七).
--
-- Guard A: 驗 schema=replay 存在；若 table 已存在則驗必要欄位俱在；缺即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_schema_exists BOOLEAN;
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'handoff_id', 'actor_id', 'experiment_id', 'manifest_id',
        'idempotency_key', 'typed_phrase_hash', 'operator_notes',
        'result', 'trace_id', 'cached', 'reject_reason',
        'ts'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'replay'
    ) INTO v_schema_exists;

    IF NOT v_schema_exists THEN
        RAISE EXCEPTION 'V044 Guard A: schema "replay" does not exist; CREATE SCHEMA above failed';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'handoff_requests'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'replay'
                  AND table_name = 'handoff_requests'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V044 Guard A: replay.handoff_requests exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;
        RAISE NOTICE 'V044 Guard A: replay.handoff_requests already present with all required columns; CREATE TABLE IF NOT EXISTS will no-op';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- CREATE TABLE replay.handoff_requests / 建立 replay.handoff_requests
--
-- Column contract / 欄位契約:
--   handoff_id          UUID server-generated primary key.
--   actor_id            TEXT authenticated actor (per V3 §11 routes); used
--                       by per-actor cooldown + UNIQUE(actor_id, idempotency_key).
--   experiment_id       UUID references replay.experiments (P2b runner SQL
--                       fixture, FK NOT enforced per V045 rationale —
--                       fixture-vs-migration ordering means no hard FK).
--   manifest_id         UUID logical reference to replay.experiments.manifest;
--                       same FK rationale as experiment_id.
--   idempotency_key     TEXT REQUIRED (NOT NULL); 36-char UUID v4 from caller.
--                       Server short-circuits duplicate POST /handoff with
--                       same (actor_id, idempotency_key) and returns cached
--                       trace_id. UNIQUE(actor_id, idempotency_key) enforces.
--   typed_phrase_hash   TEXT SHA-256 hex digest of typed phrase
--                       'HANDOFF <experiment_id>'. Raw phrase NEVER stored
--                       (security: P6-S15 hash-only audit pattern). Server
--                       computes hash AFTER server-side regex enforcement
--                       passes.
--   operator_notes      TEXT NULLable operator-supplied free-form notes
--                       (max 512 chars; UI-enforced).
--   result              TEXT enum CHECK ('success','failed','rejected').
--   trace_id            TEXT UNIQUE; UUID v4 + ts prefix (sortable). Surfaces
--                       in API response data.trace_id and in
--                       learning.governance_audit_log.payload.trace_id for
--                       cross-table forensic correlation.
--   cached              BOOLEAN; true on idempotency hit (returned without
--                       re-executing _execute_handoff()).
--   reject_reason       TEXT NULLable; populated when result='rejected'.
--                       Allowlist: 'phrase_format_invalid' /
--                       'phrase_mismatch' / 'cooldown_in_progress' /
--                       'experiment_not_found' / 'manifest_signature_failed'.
--                       NULL when result='success' or result='failed'.
--   ts                  TIMESTAMPTZ NOT NULL DEFAULT NOW(); cooldown query
--                       uses this column with idx_handoff_actor_ts.
--
-- 欄位契約：
--   handoff_id          UUID server 端生成 PK。
--   actor_id            TEXT 已認證 actor；per-actor cooldown + UNIQUE 用。
--   experiment_id       UUID 邏輯指向 replay.experiments（不強制 FK）。
--   manifest_id         UUID 邏輯指向 replay.experiments.manifest。
--   idempotency_key     TEXT NOT NULL；36 字 UUID v4；UNIQUE(actor_id,
--                       idempotency_key) 強制；server 短路重送。
--   typed_phrase_hash   TEXT phrase 的 SHA-256 hex digest；raw phrase 永不
--                       存（安全：hash-only audit）。server 在 regex 驗過後
--                       計算。
--   operator_notes      TEXT NULL；operator 自由文字（max 512 char UI 強制）。
--   result              TEXT enum CHECK；success / failed / rejected。
--   trace_id            TEXT UNIQUE；UUID v4 + ts prefix（可排序）；API
--                       response 與 governance_audit_log 跨表關聯用。
--   cached              BOOLEAN；idempotency 命中時 true。
--   reject_reason       TEXT NULL；result='rejected' 時填。Allowlist 5 值。
--   ts                  TIMESTAMPTZ NOT NULL DEFAULT NOW()；cooldown 查詢用。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replay.handoff_requests (
    handoff_id        UUID PRIMARY KEY,
    actor_id          TEXT NOT NULL,
    experiment_id     UUID NOT NULL,
    manifest_id       UUID NOT NULL,
    idempotency_key   TEXT NOT NULL,
    typed_phrase_hash TEXT NOT NULL,
    operator_notes    TEXT,
    result            TEXT NOT NULL,
    trace_id          TEXT NOT NULL,
    cached            BOOLEAN NOT NULL DEFAULT FALSE,
    reject_reason     TEXT,
    ts                TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add UNIQUE + CHECK constraints conditionally so re-runs don't error.
-- 條件式加 UNIQUE + CHECK 約束，重跑不報錯。
DO $$
BEGIN
    -- UNIQUE(actor_id, idempotency_key) — primary acceptance binding for
    -- V3 §12 #20 typed_confirm + idempotency key.
    -- UNIQUE(actor_id, idempotency_key) — V3 §12 #20 主接受性綁定。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_handoff_actor_idempotency'
          AND conrelid = 'replay.handoff_requests'::regclass
    ) THEN
        ALTER TABLE replay.handoff_requests
            ADD CONSTRAINT uq_handoff_actor_idempotency
            UNIQUE (actor_id, idempotency_key);
        RAISE NOTICE 'V044: added UNIQUE constraint uq_handoff_actor_idempotency (V3 §12 #20)';
    ELSE
        RAISE NOTICE 'V044: uq_handoff_actor_idempotency already present; skipping ADD CONSTRAINT';
    END IF;

    -- UNIQUE(trace_id) — operator GUI cross-references trace_id with
    -- governance_audit_log.payload->>'trace_id'; collision ⇒ forensic ambiguity.
    -- UNIQUE(trace_id) — operator GUI 與 audit log 跨表交叉；衝突會破壞 forensic 線索。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_handoff_trace_id'
          AND conrelid = 'replay.handoff_requests'::regclass
    ) THEN
        ALTER TABLE replay.handoff_requests
            ADD CONSTRAINT uq_handoff_trace_id
            UNIQUE (trace_id);
        RAISE NOTICE 'V044: added UNIQUE constraint uq_handoff_trace_id';
    ELSE
        RAISE NOTICE 'V044: uq_handoff_trace_id already present; skipping ADD CONSTRAINT';
    END IF;

    -- result CHECK enum (3 values).
    -- result CHECK enum（3 值）。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_handoff_result'
          AND conrelid = 'replay.handoff_requests'::regclass
    ) THEN
        ALTER TABLE replay.handoff_requests
            ADD CONSTRAINT chk_handoff_result
            CHECK (result IN ('success', 'failed', 'rejected'));
        RAISE NOTICE 'V044: added CHECK constraint chk_handoff_result (3-value allowlist)';
    ELSE
        RAISE NOTICE 'V044: chk_handoff_result already present; skipping ADD CONSTRAINT';
    END IF;

    -- reject_reason CHECK enum (5 values + NULL).
    -- reject_reason CHECK enum（5 值 + NULL）。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_handoff_reject_reason'
          AND conrelid = 'replay.handoff_requests'::regclass
    ) THEN
        ALTER TABLE replay.handoff_requests
            ADD CONSTRAINT chk_handoff_reject_reason
            CHECK (
                reject_reason IS NULL
                OR reject_reason IN (
                    'phrase_format_invalid',
                    'phrase_mismatch',
                    'cooldown_in_progress',
                    'experiment_not_found',
                    'manifest_signature_failed'
                )
            );
        RAISE NOTICE 'V044: added CHECK constraint chk_handoff_reject_reason (5-value allowlist + NULL)';
    ELSE
        RAISE NOTICE 'V044: chk_handoff_reject_reason already present; skipping ADD CONSTRAINT';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path indexes via pg_get_indexdef compare.
--   Index 1: idx_handoff_actor_ts — covers cooldown query
--            `SELECT ts FROM replay.handoff_requests
--             WHERE actor_id = ? ORDER BY ts DESC LIMIT 1`.
--   Index 2: idx_handoff_recent — covers GET /handoff/recent footer query
--            `SELECT actor_id, ts, result, trace_id
--             FROM replay.handoff_requests ORDER BY ts DESC LIMIT 5`.
--
-- Guard C：hot-path 索引透過 pg_get_indexdef 比對。
--   索引 1：idx_handoff_actor_ts — 覆蓋 cooldown 查詢。
--   索引 2：idx_handoff_recent — 覆蓋 GET /handoff/recent footer 查詢。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx1_def TEXT;
    v_idx2_def TEXT;
    v_idx1_expected TEXT := 'CREATE INDEX idx_handoff_actor_ts ON replay.handoff_requests USING btree (actor_id, ts DESC)';
    v_idx2_expected TEXT := 'CREATE INDEX idx_handoff_recent ON replay.handoff_requests USING btree (ts DESC)';
BEGIN
    -- Index 1: actor_id + ts DESC (cooldown hot path).
    SELECT pg_get_indexdef(c.oid) INTO v_idx1_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_handoff_actor_ts';

    IF v_idx1_def IS NULL THEN
        CREATE INDEX idx_handoff_actor_ts
            ON replay.handoff_requests (actor_id, ts DESC);
        RAISE NOTICE 'V044 Guard C: created idx_handoff_actor_ts (cooldown hot path)';
    ELSIF v_idx1_def <> v_idx1_expected THEN
        RAISE EXCEPTION
            'V044 Guard C: idx_handoff_actor_ts drift detected. Expected: %; Got: %',
            v_idx1_expected, v_idx1_def;
    ELSE
        RAISE NOTICE 'V044 Guard C: idx_handoff_actor_ts already present and matches; skipping';
    END IF;

    -- Index 2: ts DESC standalone (recent 5 footer hot path).
    SELECT pg_get_indexdef(c.oid) INTO v_idx2_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_handoff_recent';

    IF v_idx2_def IS NULL THEN
        CREATE INDEX idx_handoff_recent
            ON replay.handoff_requests (ts DESC);
        RAISE NOTICE 'V044 Guard C: created idx_handoff_recent (recent 5 footer hot path)';
    ELSIF v_idx2_def <> v_idx2_expected THEN
        RAISE EXCEPTION
            'V044 Guard C: idx_handoff_recent drift detected. Expected: %; Got: %',
            v_idx2_expected, v_idx2_def;
    ELSE
        RAISE NOTICE 'V044 Guard C: idx_handoff_recent already present and matches; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- V035 governance_audit_log event_type CHECK enum extension
-- (P6-S15 audit emit dependency).
--
-- V035 ships event_type CHECK enum with 5 values:
--   review_live_candidate / lease_grant / lease_auto_revoke /
--   bulk_re_evaluation / audit_write_failed.
--
-- P6-S15 emits a 'replay_handoff_request' event_type per DOC-08 §12
-- governance audit policy (append-only, INSERT-only, hash-only typed phrase).
-- Without enum extension, INSERT fails CHECK; we DROP+ADD with the canonical
-- 6-value list.
--
-- V035 governance_audit_log event_type CHECK enum 擴充（P6-S15 audit emit
-- 依賴）。V035 出廠 5 值；P6-S15 寫 'replay_handoff_request' 需 6 值；
-- DROP+ADD 用 canonical 6 值 list。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_check_def TEXT;
    v_audit_log_exists BOOLEAN;
BEGIN
    -- Ensure V035 base table exists (else V035 hasn't deployed).
    -- 確認 V035 base table 存在（否則 V035 未部署）。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'governance_audit_log'
    ) INTO v_audit_log_exists;

    IF NOT v_audit_log_exists THEN
        RAISE EXCEPTION
            'V044: learning.governance_audit_log not found; V035 must deploy before V044';
    END IF;

    -- Probe existing CHECK constraint on event_type column.
    -- 探測 event_type column 的 CHECK constraint。
    SELECT pg_get_constraintdef(c.oid)
    INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'learning'
      AND t.relname = 'governance_audit_log'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%event_type%';

    -- If 'replay_handoff_request' already in def, V044 already extended.
    -- 若 def 已含 'replay_handoff_request' 表 V044 已擴。
    IF v_check_def IS NOT NULL AND position('replay_handoff_request' IN v_check_def) > 0 THEN
        RAISE NOTICE 'V044: governance_audit_log event_type CHECK already extended with replay_handoff_request; skipping';
    ELSE
        -- DROP existing CHECK (if any) and re-ADD with 6-value list.
        -- DROP 既有 CHECK（若有）並用 6 值 list 重 ADD。
        IF EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'learning'
              AND t.relname = 'governance_audit_log'
              AND c.contype = 'c'
              AND c.conname LIKE '%event_type%'
        ) THEN
            -- Find exact constraint name (PG auto-generates if none specified
            -- in V035; canonical V035 source uses inline CHECK so name is
            -- governance_audit_log_event_type_check).
            -- 找 constraint 名（V035 inline CHECK 的 PG 自動命名）。
            EXECUTE 'ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check';
            RAISE NOTICE 'V044: dropped existing event_type CHECK on learning.governance_audit_log';
        END IF;

        ALTER TABLE learning.governance_audit_log
            ADD CONSTRAINT governance_audit_log_event_type_check
            CHECK (event_type IN (
                'review_live_candidate',
                'lease_grant',
                'lease_auto_revoke',
                'bulk_re_evaluation',
                'audit_write_failed',
                'replay_handoff_request'
            ));
        RAISE NOTICE 'V044: added event_type CHECK with 6-value list including replay_handoff_request';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.handoff_requests IS
'REF-20 V3 Wave 8 R20-P6-S14 demo handoff request lifecycle table. '
'Server-side regex (P6-S13) + UNIQUE(actor_id, idempotency_key) (P6-S14) + '
'audit row emit (P6-S15) form the security trio. Typed phrase NEVER stored '
'raw — only SHA-256 hash. / '
'REF-20 V3 Wave 8 R20-P6-S14 demo handoff 請求生命週期表；server-side regex + '
'UNIQUE(actor_id, idempotency_key) + audit row emit 三件組成安全三劍客；'
'typed phrase 永不存原文，僅 SHA-256 hash。';

COMMENT ON COLUMN replay.handoff_requests.handoff_id IS
'Server-generated UUID primary key.';

COMMENT ON COLUMN replay.handoff_requests.actor_id IS
'Authenticated actor; primary cooldown + idempotency key partition.';

COMMENT ON COLUMN replay.handoff_requests.experiment_id IS
'UUID logical reference to replay.experiments (P2b runner SQL fixture); FK not enforced per V045 rationale.';

COMMENT ON COLUMN replay.handoff_requests.manifest_id IS
'UUID logical reference to replay.experiments.manifest; FK not enforced.';

COMMENT ON COLUMN replay.handoff_requests.idempotency_key IS
'NOT NULL caller-supplied idempotency key; UNIQUE(actor_id, idempotency_key) — same key from same actor returns cached trace_id.';

COMMENT ON COLUMN replay.handoff_requests.typed_phrase_hash IS
'SHA-256 hex digest of HANDOFF <experiment_id>; raw phrase never stored (security).';

COMMENT ON COLUMN replay.handoff_requests.operator_notes IS
'Operator-supplied free-form notes (UI cap 512 chars).';

COMMENT ON COLUMN replay.handoff_requests.result IS
'Lifecycle result: success / failed / rejected. CHECK chk_handoff_result enforces.';

COMMENT ON COLUMN replay.handoff_requests.trace_id IS
'UNIQUE trace identifier; surfaces in API response + governance_audit_log.payload.trace_id.';

COMMENT ON COLUMN replay.handoff_requests.cached IS
'TRUE on idempotency hit (returned without re-executing). Operator GUI surfaces this.';

COMMENT ON COLUMN replay.handoff_requests.reject_reason IS
'NULL when result IN (success, failed); 5-value allowlist when result=rejected.';

COMMENT ON COLUMN replay.handoff_requests.ts IS
'Row creation timestamp; cooldown query uses idx_handoff_actor_ts (actor_id, ts DESC).';

-- V045__replay_run_state.sql
-- Purpose / 目的:
--   Create replay.run_state to track replay_runner subprocess lifecycle for
--   the 8-route Paper Replay Lab API (replay_routes.py). Row created on
--   POST /api/v1/replay/run when replay_runner is spawned; updated on
--   completion / failure / cancellation; queried by GET /status and the
--   PG advisory-lock concurrency-cap path that replaces the old in-memory
--   _ACTIVE_RUNS dict (per Wave 2 dispatch v1.1 §6 Option C decision).
--
-- 建立 replay.run_state 追蹤 replay_runner subprocess 生命週期，供 8-route
-- Paper Replay Lab API（replay_routes.py）使用。POST /api/v1/replay/run 啟動
-- replay_runner 時 INSERT 一列；完成 / 失敗 / 取消時 UPDATE；GET /status
-- 與「取代既有 in-memory _ACTIVE_RUNS dict 的 PG advisory-lock 並發守門」
-- 路徑讀取（per Wave 2 dispatch v1.1 §6 Option C 決策）。
--
-- Why a dedicated table / 為什麼獨立一張表:
--   - replay.experiments (V### Wave 3 P2b runner SQL fixture, NOT a
--     migration) is the manifest registry; it stores design-time intent
--     and signed metadata. run_state stores RUNTIME subprocess facts
--     (PID, started_at_ms, exit_code, output_path) that are orthogonal to
--     the manifest contract.
--   - Mixing subprocess PIDs into a manifest table would couple manifest
--     verification (HMAC + canonical bytes) with restart-volatile data
--     (PIDs reset across reboots; output_path is filesystem-local) and
--     break the V3 §4.1 "manifest_jsonb is canonical" invariant.
--   - Separating run_state lets the Wave 4 R20-P2b-T2 PG advisory-lock
--     gate (`pg_try_advisory_xact_lock(hashtext('replay_run_global'))`)
--     query a tight SELECT COUNT(*) WHERE status IN ('starting','running')
--     without reading the full manifest_jsonb body.
--
--   - replay.experiments（V### Wave 3 P2b runner SQL fixture，非 migration）
--     是 manifest registry，存設計時意圖與已簽名 metadata。run_state 存
--     RUNTIME subprocess 事實（PID、started_at_ms、exit_code、output_path），
--     與 manifest 契約正交。
--   - 把 subprocess PID 混進 manifest 表會把 manifest 驗證（HMAC + canonical
--     bytes）與「重啟時會重置」的資料（PID 跨重啟、output_path 是 filesystem
--     local）耦合，破壞 V3 §4.1「manifest_jsonb is canonical」不變量。
--   - 分離 run_state 讓 Wave 4 R20-P2b-T2 的 PG advisory-lock gate
--     （`pg_try_advisory_xact_lock(hashtext('replay_run_global'))`）可以以
--     精簡 SELECT COUNT(*) WHERE status IN ('starting','running') 查詢，
--     而非讀整段 manifest_jsonb。
--
-- Migration order / 遷移順序:
--   V044 (replay_handoff_idempotency_unique, P6 Wave 8) → V045 (this).
--   No FK to replay.experiments (that table lives in P2b runner SQL fixture
--   per V3 §6, not a migration). The fixture-deployed FK constraint MAY be
--   added later when fixture lands; this migration intentionally avoids
--   forward-reference to a fixture table to keep V045 deployable
--   independently of P2b runner deploy order.
--
--   V044 → V045（本檔）。不對 replay.experiments 加 FK（該表由 P2b runner
--   SQL fixture 部署，per V3 §6 非 migration）。fixture 部署的 FK 約束可在
--   fixture land 後追加；本 migration 故意不前向參考 fixture 表，讓 V045
--   獨立於 P2b runner 部署順序仍可部署。
--
-- Idempotency / 幂等性:
--   local psql -f V045 ... × 2 → second run no-op (Guard A IF NOT EXISTS;
--   Guard C compares index defs before re-creating).
--
-- Guard A: enforced (table existence + required columns validation).
-- Guard B: N/A (fresh CREATE, no ALTER COLUMN).
-- Guard C: enforced (2 hot-path indexes via pg_get_indexdef compare).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §3 G7 (replay_runner binary) + §6.1 (Canonical Implementation Choice)
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
--     §4 Wave 4 R20-P2b-T2 (run/status/cancel/report routes wired)
--   docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md
--     §6 v1.1 Option C decision (PG advisory lock retrofit replaces
--     replay_routes._ACTIVE_RUNS in-memory dict)
--   V3 §12 acceptance #3 route_auth_contract (per-actor / global cap
--     enforced via PG advisory lock, NOT in-memory)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V045 (buffer → land
--   per Wave 4 R20-P2b-T2 task, 2026-05-03).
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard C

CREATE SCHEMA IF NOT EXISTS replay;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate schema=replay exists; if table already exists, validate
-- required columns present; missing column → RAISE EXCEPTION (mirror V031/V032/
-- V035 retrofit pattern per CLAUDE.md §七).
--
-- Guard A: 驗 schema=replay 存在; 若 table 已存在則驗必要欄位俱在; 缺即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_schema_exists BOOLEAN;
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'run_id', 'actor_id', 'manifest_id', 'subprocess_pid',
        'status', 'started_at', 'completed_at', 'exit_code',
        'output_path', 'idempotency_key', 'cancel_reason',
        'runtime_environment', 'created_at'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'replay'
    ) INTO v_schema_exists;

    IF NOT v_schema_exists THEN
        RAISE EXCEPTION 'V045 Guard A: schema "replay" does not exist; CREATE SCHEMA above failed';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'run_state'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'replay'
                  AND table_name = 'run_state'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V045 Guard A: replay.run_state exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;
        RAISE NOTICE 'V045 Guard A: replay.run_state already present with all required columns; continuing to index Guard C';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- CREATE TABLE replay.run_state / 建立 replay.run_state
--
-- Column contract / 欄位契約:
--   run_id              UUID primary key (server-generated by replay_routes.py
--                       on POST /run; surfaces in API response as data.run_id).
--   actor_id            TEXT FK-like to authenticated actor (per V3 §11
--                       routes); used by per-actor advisory lock + audit.
--   manifest_id         UUID logical reference to replay.experiments (FK
--                       not enforced here — see "Why a dedicated table"
--                       above for fixture-vs-migration ordering rationale).
--   subprocess_pid      INT replay_runner Rust binary PID; nullable while
--                       status='starting' (subprocess not yet spawned).
--   status              TEXT enum ('starting','running','completed',
--                       'failed','cancelled'); CHECK enforces allowlist.
--   started_at          TIMESTAMPTZ row creation (subprocess fork / spawn).
--   completed_at        TIMESTAMPTZ subprocess exit time; NULL while alive.
--   exit_code           INT subprocess exit code (0 = success); NULL while
--                       alive; -1 reserved for "killed by SIGTERM".
--   output_path         TEXT filesystem path of replay artifacts directory;
--                       resolved via OPENCLAW_DATA_DIR (Linux only;
--                       Mac fixture path tagged via runtime_environment).
--   idempotency_key     TEXT optional caller-supplied key per V3 §4.1
--                       lineage; used by Wave 4 R20-P2b-T2 to short-circuit
--                       duplicate POST /run with same key as existing run.
--   cancel_reason       TEXT operator-supplied reason on POST /cancel;
--                       NULL unless status='cancelled'.
--   runtime_environment TEXT V3 §4.1 enum {'linux_trade_core',
--                       'mac_dev_smoke_test_only'}; used by canary_writer
--                       to gate filesystem writes (Linux real, Mac mock).
--   created_at          TIMESTAMPTZ row creation timestamp (== started_at
--                       in normal flow; kept distinct for forensic audit).
--
-- 欄位契約：
--   run_id              UUID 主鍵（POST /run 時 replay_routes.py 在 server 端
--                       生成；API 回應 data.run_id 暴露）。
--   actor_id            TEXT 已認證 actor（per V3 §11 routes）；per-actor
--                       advisory lock + audit 用。
--   manifest_id         UUID 邏輯指向 replay.experiments（不強制 FK — 見上
--                       「為什麼獨立一張表」對 fixture vs migration 順序的
--                       說明）。
--   subprocess_pid      INT replay_runner Rust binary PID；status='starting'
--                       期間（尚未 spawn）為 NULL。
--   status              TEXT enum；CHECK 強制白名單。
--   started_at          TIMESTAMPTZ row 建立（subprocess fork / spawn）。
--   completed_at        TIMESTAMPTZ subprocess 結束；存活期間 NULL。
--   exit_code           INT subprocess 結束碼（0 表 success）；存活期間 NULL；
--                       -1 保留給「被 SIGTERM 殺掉」。
--   output_path         TEXT replay artifact 目錄的 filesystem 路徑；透過
--                       OPENCLAW_DATA_DIR 解析（Linux 真實；Mac 用
--                       runtime_environment 標 fixture path）。
--   idempotency_key     TEXT caller 可選 idempotency key（per V3 §4.1）；
--                       Wave 4 R20-P2b-T2 用以對相同 key 重複 POST /run
--                       做短路。
--   cancel_reason       TEXT operator POST /cancel 時提供的 reason；
--                       status='cancelled' 才不 NULL。
--   runtime_environment TEXT V3 §4.1 enum；canary_writer 據此 gate filesystem
--                       寫入（Linux 真實 / Mac mock）。
--   created_at          TIMESTAMPTZ row 建立時間（normal flow 與 started_at
--                       相同；保留以便取證 audit 時辨別兩條 timestamp 來源）。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replay.run_state (
    run_id              UUID PRIMARY KEY,
    actor_id            TEXT NOT NULL,
    manifest_id         UUID NOT NULL,
    subprocess_pid      INT,
    status              TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    exit_code           INT,
    output_path         TEXT,
    idempotency_key     TEXT,
    cancel_reason       TEXT,
    runtime_environment TEXT NOT NULL DEFAULT 'linux_trade_core',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add CHECK constraints conditionally so re-runs don't error.
-- 條件式加 CHECK 約束，重跑不報錯。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_run_state_status'
          AND conrelid = 'replay.run_state'::regclass
    ) THEN
        ALTER TABLE replay.run_state
            ADD CONSTRAINT chk_replay_run_state_status
            CHECK (status IN ('starting','running','completed','failed','cancelled'));
        RAISE NOTICE 'V045: added CHECK constraint chk_replay_run_state_status (5-value allowlist)';
    ELSE
        RAISE NOTICE 'V045: chk_replay_run_state_status already present; skipping ADD CONSTRAINT';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_run_state_runtime_env'
          AND conrelid = 'replay.run_state'::regclass
    ) THEN
        ALTER TABLE replay.run_state
            ADD CONSTRAINT chk_replay_run_state_runtime_env
            CHECK (runtime_environment IN ('linux_trade_core','mac_dev_smoke_test_only'));
        RAISE NOTICE 'V045: added CHECK constraint chk_replay_run_state_runtime_env (2-value allowlist per V3 §4.1)';
    ELSE
        RAISE NOTICE 'V045: chk_replay_run_state_runtime_env already present; skipping ADD CONSTRAINT';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path indexes via pg_get_indexdef compare.
--   Index 1: idx_replay_run_state_actor_status — covers per-actor cap query
--            `SELECT COUNT(*) WHERE actor_id = ? AND status IN ('starting','running')`.
--   Index 2: idx_replay_run_state_status_only — covers global cap query
--            `SELECT COUNT(*) WHERE status IN ('starting','running')`.
--
-- Guard C：hot-path 索引透過 pg_get_indexdef 比對。
--   索引 1：idx_replay_run_state_actor_status — 覆蓋 per-actor cap 查詢。
--   索引 2：idx_replay_run_state_status_only — 覆蓋 global cap 查詢。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx1_def TEXT;
    v_idx2_def TEXT;
    v_idx1_expected TEXT := 'CREATE INDEX idx_replay_run_state_actor_status ON replay.run_state USING btree (actor_id, status)';
    v_idx2_expected TEXT := 'CREATE INDEX idx_replay_run_state_status_only ON replay.run_state USING btree (status)';
BEGIN
    -- Index 1: actor_id + status composite.
    SELECT pg_get_indexdef(c.oid) INTO v_idx1_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_run_state_actor_status';

    IF v_idx1_def IS NULL THEN
        CREATE INDEX idx_replay_run_state_actor_status
            ON replay.run_state (actor_id, status);
        RAISE NOTICE 'V045 Guard C: created idx_replay_run_state_actor_status (per-actor cap hot path)';
    ELSIF v_idx1_def <> v_idx1_expected THEN
        RAISE EXCEPTION
            'V045 Guard C: idx_replay_run_state_actor_status drift detected. Expected: %; Got: %',
            v_idx1_expected, v_idx1_def;
    ELSE
        RAISE NOTICE 'V045 Guard C: idx_replay_run_state_actor_status already present and matches; skipping';
    END IF;

    -- Index 2: status standalone (covers global cap query without scanning actor_id).
    SELECT pg_get_indexdef(c.oid) INTO v_idx2_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_run_state_status_only';

    IF v_idx2_def IS NULL THEN
        CREATE INDEX idx_replay_run_state_status_only
            ON replay.run_state (status);
        RAISE NOTICE 'V045 Guard C: created idx_replay_run_state_status_only (global cap hot path)';
    ELSIF v_idx2_def <> v_idx2_expected THEN
        RAISE EXCEPTION
            'V045 Guard C: idx_replay_run_state_status_only drift detected. Expected: %; Got: %',
            v_idx2_expected, v_idx2_def;
    ELSE
        RAISE NOTICE 'V045 Guard C: idx_replay_run_state_status_only already present and matches; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.run_state IS
'REF-20 V3 Wave 4 R20-P2b-T2 replay_runner subprocess lifecycle tracking. '
'Created on POST /api/v1/replay/run; updated on completion / failure / cancellation. '
'PG advisory-lock concurrency-cap path queries this table (replaces in-memory _ACTIVE_RUNS). / '
'REF-20 V3 Wave 4 R20-P2b-T2 replay_runner 子程序生命週期追蹤；'
'POST /api/v1/replay/run 建立、完成 / 失敗 / 取消時更新；'
'PG advisory-lock 並發守門路徑查詢本表（取代 in-memory _ACTIVE_RUNS）。';

COMMENT ON COLUMN replay.run_state.run_id IS
'Server-generated UUID surfaced as data.run_id in /api/v1/replay/run response.';

COMMENT ON COLUMN replay.run_state.subprocess_pid IS
'replay_runner Rust binary PID; NULL during status=starting (pre-spawn).';

COMMENT ON COLUMN replay.run_state.status IS
'Lifecycle enum: starting → running → (completed | failed | cancelled). CHECK chk_replay_run_state_status enforces.';

COMMENT ON COLUMN replay.run_state.runtime_environment IS
'V3 §4.1 enum: linux_trade_core or mac_dev_smoke_test_only. Mac runs are non-actionable per V3 §6.3.';

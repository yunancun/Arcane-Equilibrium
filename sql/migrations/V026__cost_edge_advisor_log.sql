-- ============================================================
-- V026: G3-09 Phase B — learning.cost_edge_advisor_log
-- cost_edge_advisor evaluate cycle persistence (2026-04-28)
-- Created per PA RFC `2026-04-27--g3_09_phase_b_shadow_dryrun_design.md` §2.4
-- ============================================================
--
-- Purpose / 用途：
--   Persist the cost_edge_advisor's per-cycle evaluation snapshots so
--   Phase B observation period can derive trigger-frequency distribution,
--   ratio histogram, and per-status time share without relying on
--   in-memory rolling counters that reset on engine restart.
--
--   持久化 cost_edge_advisor 每輪 evaluate snapshot，讓 Phase B 觀察期可
--   推導 trigger 頻率分佈 / ratio histogram / per-status 時間佔比，不需
--   依賴每次 engine restart 即重置的記憶體 rolling counter。
--
-- Write path / 寫入路徑：
--   Rust daemon (`rust/openclaw_engine/src/cost_edge_advisor/mod.rs`)
--   `tokio::spawn` fire-and-forget INSERT after each `evaluate()` cycle.
--   Down-sampled to 1 row / minute for cycle rows; transition rows
--   (`transition_from IS NOT NULL`) bypass the down-sample so burst
--   patterns are 100% captured (PA RFC §2.5 / §6.1 R-B5).
--
--   Rust daemon 每輪 evaluate 後 `tokio::spawn` fire-and-forget INSERT；
--   cycle row 每分鐘 1 筆 down-sample，transition row 不 down-sample
--   確保 burst 100% 紀錄（RFC §2.5 / §6.1 R-B5）。
--
-- Read path / 讀取路徑：
--   * Healthcheck `[30]` Inv 3 + Inv 4 (passive_wait_healthcheck) — counts
--     freshness + trigger-rate sanity bounds.
--   * Observation report tooling
--     (`helper_scripts/research/cost_edge_advisor_observation_report.py`)
--     — derives status distribution + ratio histogram + per-hour heatmap.
--
-- Down-sample math / down-sample 算術：
--   1 row / 60s × 86400s/day = 1440 row/day per engine_mode. With 7d
--   retention slice and 3 engine_mode buckets the table holds at most
--   ~30k row at peak, well within hypertable + 30d retention budget.
--   1 行/60秒 × 86400 秒/天 = 1440 行/天/engine_mode；7 天切片含 3 個
--   engine_mode 桶上限 ~30k 行，hypertable + 30 天 retention 足夠。
--
-- Distinct from / 與既有表區分：
--   * `learning.h_state_snapshots` — full H1-H5 snapshot every poll;
--      expensive payload, retained shorter
--   * `learning.cost_edge_advisor_log` (V026) — distilled advisor verdict
--      only (ratio + threshold + status), purpose-built for trigger
--      frequency analytics
--
-- ============================================================


-- ------------------------------------------------------------
-- Schema Guard A — verify legacy table (if exists) has all required cols
-- 模板來源 / Template source:
--   sql/migrations/templates/schema_guard_template.sql § Guard A
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name   = 'cost_edge_advisor_log'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts_ms','engine_mode','status','ratio','threshold',
            'data_days','ai_spend_7d_usd','paper_pnl_7d_usd',
            'is_stale','phase','transition_from'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'cost_edge_advisor_log'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V026 Guard A FAIL: learning.cost_edge_advisor_log exists but '
                'missing required columns: %. Drop legacy table or run rollback '
                'before retrying. See sql/migrations/templates/schema_guard_template.sql.',
                v_missing;
        END IF;
    END IF;
END $$;


-- ------------------------------------------------------------
-- Main table — purposely small wire shape; no JSONB blobs
-- 主表 — wire shape 刻意精簡，無 JSONB blob
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS learning.cost_edge_advisor_log (
    -- Time / engine identity (composite PK below)
    -- 時間 / engine 身份（下方複合主鍵）
    ts_ms              BIGINT  NOT NULL,
    engine_mode        TEXT    NOT NULL
        -- Production accepts 4 valid engine modes; test fixtures use
        -- 'test_*' prefix for isolation per-PID (see persistence test).
        -- 生產接 4 個 valid engine mode；測試 fixture 用 'test_*' 前綴
        -- 隔離 per-PID（見 test_cost_edge_advisor_persistence.rs）。
        CHECK (engine_mode IN ('paper','demo','live','live_demo')
               OR engine_mode LIKE 'test\_%' ESCAPE '\'),

    -- Advisor verdict (CostEdgeAdvisorStatus::as_str() output)
    -- Advisor 判決（CostEdgeAdvisorStatus::as_str() 字串輸出）
    status             TEXT    NOT NULL
        CHECK (status IN ('Uninitialized','Disabled','WarmUp','OK',
                          'Trigger','Stale','Anomaly')),

    -- Echo the evaluation inputs / outputs for histograms + diagnostics.
    -- Nullable `ratio` for WarmUp / Disabled / Anomaly states (matches
    -- Rust `Option<f64>` semantics).
    -- Echo evaluation 輸入/輸出供 histogram + 診斷；ratio 在 WarmUp /
    -- Disabled / Anomaly 狀態下為 NULL（對齊 Rust `Option<f64>`）。
    ratio              DOUBLE PRECISION,
    threshold          DOUBLE PRECISION NOT NULL,
    data_days          INTEGER NOT NULL,
    ai_spend_7d_usd    DOUBLE PRECISION NOT NULL,
    paper_pnl_7d_usd   DOUBLE PRECISION NOT NULL,

    -- Stale flag at evaluation time (advisor entered Stale path).
    -- Stale flag — advisor 評估時 H state cache 已過期。
    is_stale           BOOLEAN NOT NULL,

    -- Phase tag for forward-compat filtering. Default `'B_shadow'` per RFC
    -- §3.2; Phase C will write `'C_gated'` / `'D_per_strategy'` in future.
    -- Phase 標籤（forward-compat 過濾）；預設 `'B_shadow'`（RFC §3.2），
    -- Phase C 會寫 `'C_gated'`/`'D_per_strategy'`。
    phase              TEXT    NOT NULL DEFAULT 'B_shadow',

    -- Set ONLY on cycles where status changed (transition rows). NULL on
    -- regular down-sampled cycle rows. Carries previous status string
    -- (e.g. `'OK'` when transition is OK→Trigger).
    -- 僅在狀態變化的 cycle (transition row) 填；regular down-sampled
    -- cycle row 為 NULL。值為前一個 status 字串（例：OK→Trigger 時為 'OK'）。
    transition_from    TEXT,

    -- Composite PK: ts_ms + engine_mode prevents duplicate cycle rows in
    -- the rare event of clock-rewind on engine restart. With 1/min
    -- down-sample collisions are practically impossible, but the PK
    -- protects against double-INSERT bugs in the daemon.
    -- 複合主鍵：(ts_ms, engine_mode) 防 clock-rewind / 雙寫 bug。
    PRIMARY KEY (ts_ms, engine_mode)
);


-- ------------------------------------------------------------
-- Schema Guard B — verify engine_mode column type is TEXT (not VARCHAR)
-- 模板來源 / Template source:
--   sql/migrations/templates/schema_guard_template.sql § Guard B
-- ------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'cost_edge_advisor_log'
    ) THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'cost_edge_advisor_log'
              AND column_name  = 'engine_mode'
              AND data_type    = 'text'
        ) THEN
            RAISE EXCEPTION
                'V026 Guard B FAIL: learning.cost_edge_advisor_log.engine_mode '
                'must be TEXT (got %). Drop legacy table or ALTER COLUMN before '
                'retrying.', (
                    SELECT data_type FROM information_schema.columns
                    WHERE table_schema = 'learning'
                      AND table_name   = 'cost_edge_advisor_log'
                      AND column_name  = 'engine_mode'
                );
        END IF;
    END IF;
END $$;


-- ------------------------------------------------------------
-- Hypertable conversion (Timescale) — 1 day chunks
-- Hypertable 轉換 — 1 天 chunk
-- ------------------------------------------------------------
SELECT create_hypertable(
    'learning.cost_edge_advisor_log',
    'ts_ms',
    chunk_time_interval => 86400000,  -- 1 day in ms
    if_not_exists       => TRUE
);


-- ------------------------------------------------------------
-- 30-day retention — Phase B observation window allows extension to
-- 90-180d in Phase C if calibration analytics need longer history.
-- bigint ts_ms hypertable: register integer_now_func first (TimescaleDB
-- 2.x requires it before add_retention_policy on integer time columns),
-- then add the retention policy with `if_not_exists => TRUE` for
-- idempotency (per CLAUDE.md §七 V023 postmortem rule 4).
-- 30 天 retention — Phase B 觀察視窗；Phase C calibration 若需更長
-- 歷史，可擴至 90-180 天。
-- bigint ts_ms hypertable：TimescaleDB 2.x 要求對 integer time column
-- 必先註冊 integer_now_func 才能 add_retention_policy；用 `if_not_exists
-- => TRUE` 保 idempotency（per CLAUDE.md §七 V023 postmortem 規則 4）。
-- ------------------------------------------------------------

-- integer_now_func: returns current epoch_ms — required by retention policy
-- on bigint time hypertables. STABLE because it does not modify state.
-- integer_now_func：返回當前 epoch_ms — bigint time hypertable retention
-- 政策的必需件。STABLE 因為不改 state。
CREATE OR REPLACE FUNCTION learning.cost_edge_advisor_log_now_ms()
RETURNS BIGINT
LANGUAGE SQL
STABLE
AS $$
    SELECT (EXTRACT(EPOCH FROM clock_timestamp()) * 1000)::BIGINT;
$$;

-- Register integer_now_func on the hypertable (idempotent — TimescaleDB
-- silently no-ops if already set to the same function).
-- 在 hypertable 註冊 integer_now_func（idempotent — TimescaleDB 同 fn
-- 已設則 silently no-op）。
SELECT set_integer_now_func(
    'learning.cost_edge_advisor_log',
    'learning.cost_edge_advisor_log_now_ms',
    replace_if_exists => TRUE
);

SELECT add_retention_policy(
    'learning.cost_edge_advisor_log',
    BIGINT '2592000000',  -- 30 days in ms
    if_not_exists => TRUE
);


-- ------------------------------------------------------------
-- Indexes — analytical queries; no Guard C needed (low-frequency reads,
-- not hot-path; the composite PK already covers most lookup patterns).
-- 索引 — 分析查詢；非 hot-path（healthcheck 6h cron、observation tooling
-- 手動跑），無需 Guard C；複合 PK 已覆蓋多數 lookup pattern。
-- ------------------------------------------------------------

-- Healthcheck Inv 4 lookup — count Trigger transitions in last 1h.
-- Healthcheck Inv 4 查 — 最近 1h Trigger transition 數。
CREATE INDEX IF NOT EXISTS idx_cea_log_status_ts
    ON learning.cost_edge_advisor_log (status, ts_ms DESC);

-- Per-environment time-series scan (deliverable per-engine_mode breakdown).
-- 分環境時序掃描（deliverable per-engine_mode 切分）。
CREATE INDEX IF NOT EXISTS idx_cea_log_engine_mode_ts
    ON learning.cost_edge_advisor_log (engine_mode, ts_ms DESC);

-- Transition rows partial index — observation report focuses on
-- transitions; partial index keeps it small (~1% of total rows).
-- Transition row 部分索引 — observation report 聚焦 transition；部分索引
-- 保持小（~1% 行）。
CREATE INDEX IF NOT EXISTS idx_cea_log_transitions
    ON learning.cost_edge_advisor_log (ts_ms DESC)
    WHERE transition_from IS NOT NULL;


-- ------------------------------------------------------------
-- Comments / 註解
-- ------------------------------------------------------------
COMMENT ON TABLE learning.cost_edge_advisor_log IS
    'V026 (G3-09 Phase B, 2026-04-28): cost_edge_advisor evaluate cycle '
    'persistence. Hypertable, 1-day chunks, 30-day retention. Down-sampled '
    'to 1 row/min for cycle rows; transition rows (status change) bypass '
    'the down-sample. Read by healthcheck [30] Inv 3 + Inv 4 and '
    'helper_scripts/research/cost_edge_advisor_observation_report.py.';

COMMENT ON COLUMN learning.cost_edge_advisor_log.transition_from IS
    'NULL on regular down-sampled cycle rows; set to the previous status '
    'string (e.g. ''OK'') only when the cycle observed a status change. '
    'Use IS NOT NULL filter to count Trigger episode entries.';

COMMENT ON COLUMN learning.cost_edge_advisor_log.phase IS
    'Forward-compat filter. ''B_shadow'' for Phase B observation; Phase C '
    'will write ''C_gated'' / ''D_per_strategy'' (see PA RFC §3.2).';

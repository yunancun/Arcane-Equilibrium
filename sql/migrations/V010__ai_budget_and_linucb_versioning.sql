-- ============================================================
-- V010 — Phase 4 Cross-cutting (4-15): AI Budget tracker tables
--        + LinUCB versioning schema (warm-start prep for 4-04..4-06)
-- V010 — Phase 4 跨領域子任務 4-15：AI 預算追蹤表
--        + LinUCB 版本化 schema（為 4-04..4-06 warm-start 預鋪路）
-- ============================================================
--
-- Source / 來源:
--   docs/references/2026-04-06--phase4_execution_plan_v2.md §4-15 + §Q1 + §Q3
--   docs/references/math_implementation_notes.md Entry 01 §1.4
--
-- Five (5) changes / 五項變更:
--   A1. NEW  learning.ai_budget_config         (5 default scopes)
--   A2. NEW  learning.ai_usage_log             (hypertable, 7d chunk)
--   A3. ALTER learning.linucb_state            (+4 cols + composite PK)
--   A4. NEW  learning.linucb_state_archive     (rollback snapshot)
--   A5. NEW  learning.linucb_migrations        (audit log)
--
-- Notes / 備註:
--   - Pricing table is intentionally NOT created here. The Rust BudgetTracker
--     uses an in-process const map placeholder; sub-task 4-17 (provider pricing)
--     will replace it with a real DB-backed table.
--   - V010 is fail-safe: all CREATE statements use IF NOT EXISTS; ALTERs use
--     ADD COLUMN IF NOT EXISTS. Re-running V010 is a no-op.
--   - 定價表刻意不建。Rust BudgetTracker 暫用 in-process const 占位，4-17 任務
--     會替換為真實 DB pricing table。V010 全部 idempotent，可重跑。
-- ============================================================


-- ============================================================
-- A1. learning.ai_budget_config — per-scope monthly USD ceilings
--     按 scope 月度美元上限配置（Operator/IPC 可調）
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.ai_budget_config (
    scope        TEXT        PRIMARY KEY,
    monthly_usd  REAL        NOT NULL CHECK (monthly_usd >= 0),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by   TEXT
);

COMMENT ON TABLE learning.ai_budget_config IS
    'Per-scope monthly USD budget config (operator/IPC adjustable) | 按 scope 月度美元預算配置';
COMMENT ON COLUMN learning.ai_budget_config.scope IS
    'Budget scope: local_total / platform_hard_cap / agent_teacher / agent_analyst / agent_reserve | 預算範圍';
COMMENT ON COLUMN learning.ai_budget_config.monthly_usd IS
    'Monthly USD ceiling for this scope (>= 0) | 該 scope 的月度美元上限';
COMMENT ON COLUMN learning.ai_budget_config.updated_by IS
    'Source of last update: operator / system / ipc | 最後更新來源';

-- Default seeds (Phase 4 Q1 spec) / 預設種子值
INSERT INTO learning.ai_budget_config (scope, monthly_usd, updated_by) VALUES
    ('local_total',        100.0, 'system'),
    ('platform_hard_cap',  150.0, 'system'),
    ('agent_teacher',       60.0, 'system'),
    ('agent_analyst',       30.0, 'system'),
    ('agent_reserve',       10.0, 'system')
ON CONFLICT (scope) DO NOTHING;


-- ============================================================
-- A2. learning.ai_usage_log — per-call AI usage records (hypertable)
--     每次 AI 調用的用量記錄（hypertable，7 天 chunk）
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.ai_usage_log (
    time        TIMESTAMPTZ NOT NULL,
    scope       TEXT        NOT NULL,
    provider    TEXT        NOT NULL,
    model       TEXT        NOT NULL,
    tokens_in   INT         NOT NULL,
    tokens_out  INT         NOT NULL,
    cost_usd    REAL        NOT NULL,
    purpose     TEXT,
    request_id  TEXT        NOT NULL DEFAULT '',
    PRIMARY KEY (time, scope, request_id)
);

COMMENT ON TABLE learning.ai_usage_log IS
    'AI provider usage log (per-call), TimescaleDB hypertable for monthly aggregation | AI 用量日誌（hypertable）';
COMMENT ON COLUMN learning.ai_usage_log.scope IS
    'Budget scope this call is charged to (FK→ai_budget_config.scope, logical) | 計費 scope';
COMMENT ON COLUMN learning.ai_usage_log.provider IS
    'LLM provider: anthropic / openai / local_ollama / etc | LLM 供應商';
COMMENT ON COLUMN learning.ai_usage_log.model IS
    'Model identifier, e.g. claude-sonnet-4-5 / gpt-4o / qwen-3.5-9b | 模型 ID';
COMMENT ON COLUMN learning.ai_usage_log.cost_usd IS
    'Computed USD cost for this call (provider pricing × token counts) | 本次調用美元成本';
COMMENT ON COLUMN learning.ai_usage_log.purpose IS
    'Free-form purpose tag, e.g. directive_generation / anomaly_review | 用途標籤';
COMMENT ON COLUMN learning.ai_usage_log.request_id IS
    'Correlation ID for tracing (client-supplied) | 關聯追蹤 ID';

-- Convert to hypertable (7-day chunks, monthly aggregation friendly)
-- 轉為 hypertable（7 天 chunk，方便月度聚合查詢）
SELECT create_hypertable(
    'learning.ai_usage_log',
    'time',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- Index for monthly aggregation per scope / 按 scope 的月度聚合索引
CREATE INDEX IF NOT EXISTS idx_ai_usage_log_scope_time
    ON learning.ai_usage_log (scope, time DESC);


-- ============================================================
-- A3. ALTER learning.linucb_state — versioning for warm-start migrations
--     LinUCB state 加版本欄位，為 hierarchical warm-start 鋪路
-- Source: math_implementation_notes.md Entry 01 §1.4
-- ============================================================
ALTER TABLE learning.linucb_state
    ADD COLUMN IF NOT EXISTS arm_space_version   TEXT NOT NULL DEFAULT 'v1_15';

ALTER TABLE learning.linucb_state
    ADD COLUMN IF NOT EXISTS parent_arm_id       TEXT DEFAULT NULL;

ALTER TABLE learning.linucb_state
    ADD COLUMN IF NOT EXISTS inheritance_gamma   REAL DEFAULT NULL;

ALTER TABLE learning.linucb_state
    ADD COLUMN IF NOT EXISTS feature_schema_hash TEXT NOT NULL DEFAULT 'sha256:placeholder';

COMMENT ON COLUMN learning.linucb_state.arm_space_version IS
    'Arm-space version label, e.g. v1_15 / v2_25 / v3_375 | arm 空間版本標籤';
COMMENT ON COLUMN learning.linucb_state.parent_arm_id IS
    'Parent arm ID this arm was warm-started from (NULL = original) | warm-start 的父 arm ID';
COMMENT ON COLUMN learning.linucb_state.inheritance_gamma IS
    'Inheritance weight gamma used during warm-start (0..1) | 繼承權重 gamma';
COMMENT ON COLUMN learning.linucb_state.feature_schema_hash IS
    'sha256 hash of the feature schema this arm trained on (fail-closed on mismatch) | 特徵 schema 雜湊';

-- Composite PK: (arm_id, arm_space_version) — same arm name can coexist
-- across multiple versions during shadow comparison.
-- 複合主鍵：(arm_id, arm_space_version) — shadow 比較期間同名 arm 可並存。
ALTER TABLE learning.linucb_state DROP CONSTRAINT IF EXISTS linucb_state_pkey;
ALTER TABLE learning.linucb_state ADD PRIMARY KEY (arm_id, arm_space_version);


-- ============================================================
-- A4. learning.linucb_state_archive — pre-migration snapshot for rollback
--     遷移前快照表，支持回滾
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.linucb_state_archive (
    LIKE learning.linucb_state INCLUDING ALL
);

ALTER TABLE learning.linucb_state_archive
    ADD COLUMN IF NOT EXISTS archived_ts    TIMESTAMPTZ NOT NULL DEFAULT NOW();

ALTER TABLE learning.linucb_state_archive
    ADD COLUMN IF NOT EXISTS archive_reason TEXT;

COMMENT ON TABLE learning.linucb_state_archive IS
    'Pre-migration snapshot of linucb_state for rollback | 遷移前 linucb_state 快照（供回滾）';
COMMENT ON COLUMN learning.linucb_state_archive.archived_ts IS
    'When this snapshot row was archived | 快照存檔時間';
COMMENT ON COLUMN learning.linucb_state_archive.archive_reason IS
    'Why this snapshot was taken (e.g. expand_v1_to_v2) | 存檔原因';


-- ============================================================
-- A5. learning.linucb_migrations — warm-start migration audit log
--     warm-start 遷移審計日誌
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.linucb_migrations (
    migration_id   SERIAL      PRIMARY KEY,
    from_version   TEXT        NOT NULL,
    to_version     TEXT        NOT NULL,
    direction      TEXT        NOT NULL CHECK (direction IN ('expand','collapse','feature_pad')),
    gamma          REAL,
    n_arms_before  INT,
    n_arms_after   INT,
    started_ts     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_ts    TIMESTAMPTZ,
    rollback_to    INT REFERENCES learning.linucb_migrations(migration_id),
    notes          TEXT
);

COMMENT ON TABLE learning.linucb_migrations IS
    'LinUCB warm-start migration audit log (one row per expand/collapse/pad event) | LinUCB 遷移審計';
COMMENT ON COLUMN learning.linucb_migrations.direction IS
    'expand (parent→children split) / collapse (children→parent merge) / feature_pad | 遷移方向';
COMMENT ON COLUMN learning.linucb_migrations.gamma IS
    'Inheritance weight used (matches linucb_state.inheritance_gamma) | 繼承權重';
COMMENT ON COLUMN learning.linucb_migrations.rollback_to IS
    'If this migration is itself a rollback, FK to the migration_id it rolled back | 若為回滾，指向被回滾的 migration_id';


-- ============================================================
-- Verification queries / 驗證查詢
-- ============================================================
-- 1) ai_budget_config seeded with 5 scopes:
--    SELECT scope, monthly_usd FROM learning.ai_budget_config ORDER BY scope;
--    Expect 5 rows
--
-- 2) ai_usage_log is a hypertable:
--    SELECT hypertable_name FROM timescaledb_information.hypertables
--     WHERE hypertable_schema='learning' AND hypertable_name='ai_usage_log';
--    Expect 1 row
--
-- 3) linucb_state has 4 new columns + composite PK:
--    SELECT column_name FROM information_schema.columns
--     WHERE table_schema='learning' AND table_name='linucb_state'
--       AND column_name IN ('arm_space_version','parent_arm_id',
--                           'inheritance_gamma','feature_schema_hash');
--    Expect 4 rows
--
--    SELECT array_agg(a.attname ORDER BY a.attnum) AS pk_cols
--      FROM pg_index i
--      JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
--     WHERE i.indrelid = 'learning.linucb_state'::regclass AND i.indisprimary;
--    Expect: {arm_id, arm_space_version}
--
-- 4) linucb_state_archive exists:
--    SELECT to_regclass('learning.linucb_state_archive');  -- not null
--
-- 5) linucb_migrations exists:
--    SELECT to_regclass('learning.linucb_migrations');     -- not null
-- ============================================================

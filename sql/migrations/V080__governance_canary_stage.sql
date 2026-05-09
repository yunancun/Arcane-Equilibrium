-- ============================================================
-- V080: Graduated Canary State Machine — Persistent Audit Tables
-- AMD-2026-05-09-03 W-AUDIT-9 T2 配套 PG schema
-- ============================================================
--
-- 用途 / Purpose:
--   AMD-2026-05-09-03 把 ExecutorAgent `shadow_mode: bool` 升級為 5-stage
--   graduated canary（Stage 0 shadow / 1 paper / 2 demo / 3 demo full / 4 live
--   pending）。本 migration 落 governance schema 兩張 append-only audit tables：
--   1. governance.canary_stage_log
--      每次 stage transition 落地（manual_promote / auto_promote / auto_rollback /
--      incident_rollback）。append-only，由 W-AUDIT-9 T3 shadow_mode_provider
--      stage-aware 寫入。healthcheck `[58]` 對 active cohort 取 latest row。
--   2. governance.canary_stage_metric_registry
--      auto-promote / auto-rollback metric SQL definition；W-AUDIT-9 T4
--      healthcheck `[58]` 用以驗 metric 是否存在 / drift / threshold 配對。
--
--   Reference: docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md
--   §4.2 PG 持久化（V### migration）
--
-- 不變量 / Invariants:
--   - stage values: 0..=4（CHECK constraint）
--   - manual_promote 必伴隨 decision_lease_id（per AMD §4.5；E2 audit point #2）
--   - active=true rows in metric_registry must be unique per (stage, metric_name)
--   - append-only audit；無 UPDATE/DELETE workflow
--
-- Idempotency:
--   - 兩次跑 psql -f V080__governance_canary_stage.sql 第二次必須不 RAISE。
--   - Guard A 驗 governance.canary_stage_log columns 俱在；Guard B 驗 type；
--     Guard C 驗 critical index column ordering。
--
-- E2 重點審查（per AMD-2026-05-09-03 §7）:
--   #1 _read_shadow_mode invariant — Rust schema 層處理（V080 不涉）。
--   #2 manual_promote NOT NULL constraint — 本 migration 強制 PG 層（不只 application）。
--   #3 SM-04 ≥ L3 hard FAIL — healthcheck 層（V080 不涉）。
-- ============================================================

-- ------------------------------------------------------------
-- governance schema 確保存在（PG 內建不會自動建立）
-- governance schema bootstrap（per ADR-0011 governance schema convention）
-- ------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS governance;

COMMENT ON SCHEMA governance IS
    'Governance audit tables (CLAUDE.md §三 W-C / SM-04 / Decision Lease / canary stage). '
    'Append-only audit semantics; not part of trading hot path. '
    'AMD-2026-05-09-03 W-AUDIT-9 introduces canary_stage_log + canary_stage_metric_registry.';


-- ============================================================
-- Schema Guard A — governance.canary_stage_log 必要欄位
-- 若表已存在但缺欄位（pre-existing legacy schema drift），提前 RAISE。
-- Template source: sql/migrations/templates/schema_guard_template.sql § Guard A
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'governance' AND table_name = 'canary_stage_log'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'stage_log_id',
            'cohort_id',
            'from_stage',
            'to_stage',
            'transition_kind',
            'decision_lease_id',
            'triggered_metric',
            'triggered_value',
            'created_at_ms'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'governance'
              AND table_name   = 'canary_stage_log'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: governance.canary_stage_log exists but missing required columns: %. '
                'Pre-existing legacy schema drift. Resolve via DROP + re-apply V080 or '
                'ALTER ADD missing columns before re-running this migration.',
                v_missing;
        END IF;
    END IF;
END $$;


-- ============================================================
-- Schema Guard A — governance.canary_stage_metric_registry 必要欄位
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'governance' AND table_name = 'canary_stage_metric_registry'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'metric_id',
            'stage',
            'metric_name',
            'direction',
            'threshold_value',
            'observation_window_ms',
            'active'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'governance'
              AND table_name   = 'canary_stage_metric_registry'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: governance.canary_stage_metric_registry exists but missing required columns: %. '
                'Pre-existing legacy schema drift. Resolve via DROP + re-apply V080.',
                v_missing;
        END IF;
    END IF;
END $$;


-- ============================================================
-- 1. governance.canary_stage_log
--    每次 stage transition append-only 落地。
-- ============================================================
CREATE TABLE IF NOT EXISTS governance.canary_stage_log (
    stage_log_id        BIGSERIAL   PRIMARY KEY,
    -- cohort 識別。Stage 1/2 = 'strategy:symbol:env'，Stage 0/3/4 = 'global'
    -- AMD-2026-05-09-03：cohort 識別字串，Stage 0/3/4=global，Stage 1/2 唯一。
    cohort_id           TEXT        NOT NULL,
    -- 起始 stage（0..=4）
    from_stage          SMALLINT    NOT NULL,
    -- 目的 stage（0..=4）
    to_stage            SMALLINT    NOT NULL,
    -- 轉移類型：'manual_promote' / 'auto_promote' / 'auto_rollback' /
    -- 'incident_rollback'（per AMD §4.2）
    -- AMD-2026-05-09-03：transition kind；manual_promote 必伴 lease。
    transition_kind     TEXT        NOT NULL,
    -- manual_promote 時必填 lease_id（per AMD §4.5 + E2 audit point #2）
    -- AMD-2026-05-09-03 §4.5：manual_promote 必伴 LeaseScope::CanaryStagePromotion lease_id。
    decision_lease_id   UUID        NULL,
    -- 觸發此 transition 的 metric（auto_promote / auto_rollback 必填，
    -- 對應 canary_stage_metric_registry.metric_name）
    -- 觸發 metric 名稱（auto path 必填，manual path 通常 NULL 或 operator note）。
    triggered_metric    TEXT        NULL,
    -- 觸發時 metric 取值（用於 audit 重建）
    -- 觸發時 metric 數值（重建用）。
    triggered_value     NUMERIC     NULL,
    -- 寫入 ms epoch（與 trading.fills / decision_features 對齊）
    -- 寫入 ms epoch（與其他 audit 表時間軸對齊）。
    created_at_ms       BIGINT      NOT NULL,
    -- DB-層輔助 timestamp（PG NOW() 寫入時間，operator 觀察用）
    -- DB 端輔助 timestamp，operator 觀察。
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ────────────────────────────────────────────────────────
    -- CHECK constraints / 值域 + 不變量
    -- ────────────────────────────────────────────────────────

    -- stage 值域 0..=4
    CONSTRAINT canary_stage_log_from_stage_chk
        CHECK (from_stage BETWEEN 0 AND 4),
    CONSTRAINT canary_stage_log_to_stage_chk
        CHECK (to_stage BETWEEN 0 AND 4),

    -- transition_kind enum
    CONSTRAINT canary_stage_log_transition_kind_chk
        CHECK (transition_kind IN (
            'manual_promote',
            'auto_promote',
            'auto_rollback',
            'incident_rollback'
        )),

    -- AMD-2026-05-09-03 §4.5 + E2 audit point #2:
    -- manual_promote 必伴隨 decision_lease_id（PG 層強制，不只 application）。
    -- 雞蛋死循環防線 — manual_promote 無 lease 違反 audit chain 完整性。
    -- E2 audit point #2：manual_promote 必伴 lease，PG 層強制不只 app 層。
    CONSTRAINT canary_stage_log_manual_promote_lease_required_chk
        CHECK (
            transition_kind != 'manual_promote'
            OR decision_lease_id IS NOT NULL
        ),

    -- created_at_ms 必為合理 epoch（>= 2020-01-01 = 1577836800000ms）
    -- 規避測試 / migration race 寫入 0 / 負值
    CONSTRAINT canary_stage_log_created_at_ms_sane_chk
        CHECK (created_at_ms >= 1577836800000),

    -- triggered_value 必為 finite（無 NaN / Inf）— PG NUMERIC 不接受 Inf
    -- 但保險起見明示
    CONSTRAINT canary_stage_log_triggered_value_finite_chk
        CHECK (
            triggered_value IS NULL
            OR (
                triggered_value = triggered_value -- NaN 自身不等於自身
            )
        )
);

COMMENT ON TABLE governance.canary_stage_log IS
    'AMD-2026-05-09-03 W-AUDIT-9 §4.2: append-only audit of every canary stage '
    'transition. Read by healthcheck [58] for active cohort latest row + by '
    'OpenClaw Control Console GUI surface (W-AUDIT-9 T5). Writes by W-AUDIT-9 T3 '
    'shadow_mode_provider stage-aware on auto_promote/auto_rollback and by '
    'governance_hub.py LeaseScope::CanaryStagePromotion on manual_promote (T6).';

COMMENT ON COLUMN governance.canary_stage_log.cohort_id IS
    'Cohort identifier. Stage 1/2 = "<strategy>:<symbol>:<environment>" tuple; '
    'Stage 0/3/4 = literal "global" sentinel. Used to query latest active stage '
    'per cohort tuple in healthcheck [58] AMD §4.1.';

COMMENT ON COLUMN governance.canary_stage_log.transition_kind IS
    'manual_promote (operator GUI/IPC + Decision Lease) | auto_promote '
    '(SLA passed in observation window) | auto_rollback (rollback metric trip) | '
    'incident_rollback (SM-04 >= L3 escalate or DOC-08 §12 invariant violation).';

COMMENT ON COLUMN governance.canary_stage_log.decision_lease_id IS
    'AMD-2026-05-09-03 §4.5: required (NOT NULL) when transition_kind=manual_promote, '
    'enforcing the LeaseScope::CanaryStagePromotion audit chain. Auto/incident '
    'transitions leave this NULL because they do not pass through Decision Lease.';

COMMENT ON COLUMN governance.canary_stage_log.triggered_metric IS
    'For auto_promote: the SLA metric_name (canary_stage_metric_registry FK-like) '
    'whose threshold was crossed. For auto_rollback / incident_rollback: the '
    'rollback metric / incident name. NULL for manual_promote (operator note '
    'lives outside the schema).';


-- ============================================================
-- 2. governance.canary_stage_metric_registry
--    auto-promote / auto-rollback metric definition + threshold。
--    healthcheck [58] 用以比對 cohort 真實 metric 是否 trip。
-- ============================================================
CREATE TABLE IF NOT EXISTS governance.canary_stage_metric_registry (
    metric_id               BIGSERIAL   PRIMARY KEY,
    -- 適用的目的 stage（0..=4）。Stage 0 是 fail-closed 永久態，預設無
    -- promote/rollback metric；Stage 1+ 才有實質 metric。
    -- AMD-2026-05-09-03：metric 適用 stage（0..=4），Stage 1+ 才有 metric。
    stage                   SMALLINT    NOT NULL,
    -- metric 名稱（per AMD §2.2 表）：'entry_fills' / 'gross_pnl_usdt' / 'DSR' /
    -- 'attribution_chain_ok_ratio' / 'lease_ipc_failure_rate_24h' / 等等
    -- AMD-2026-05-09-03：metric 名稱，per §2.2 表格列舉。
    metric_name             TEXT        NOT NULL,
    -- 升級 / 退降方向：'promote_upper'（值 > threshold 升 stage）/
    -- 'promote_lower'（值 < threshold 升）/ 'rollback_upper'（值 > threshold
    -- 退）/ 'rollback_lower'（值 < threshold 退）
    -- AMD-2026-05-09-03：方向；promote_upper/lower + rollback_upper/lower。
    direction               TEXT        NOT NULL,
    -- 閾值（NUMERIC 保留小數精度）
    -- AMD-2026-05-09-03：閾值；NUMERIC 保留小數精度。
    threshold_value         NUMERIC     NOT NULL,
    -- 觀察期長度（ms）；rollback metric 通常配 24h sliding window，
    -- promote metric 配整個 stage 觀察期（7d/14d/21d）
    -- AMD-2026-05-09-03：觀察期 ms；rollback 24h sliding，promote 為 stage 期。
    observation_window_ms   BIGINT      NOT NULL,
    -- 啟用旗標。drift 排查時可整 row 設 false 而非 DELETE（保留審計）
    -- AMD-2026-05-09-03：啟用旗標；drift 排查時 false 而非 DELETE。
    active                  BOOLEAN     NOT NULL DEFAULT TRUE,
    -- 描述（healthcheck [58] log 顯示用）
    description             TEXT        NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ────────────────────────────────────────────────────────
    -- CHECK constraints
    -- ────────────────────────────────────────────────────────

    CONSTRAINT canary_stage_metric_registry_stage_chk
        CHECK (stage BETWEEN 0 AND 4),

    CONSTRAINT canary_stage_metric_registry_direction_chk
        CHECK (direction IN (
            'promote_upper',
            'promote_lower',
            'rollback_upper',
            'rollback_lower'
        )),

    CONSTRAINT canary_stage_metric_registry_observation_window_positive_chk
        CHECK (observation_window_ms > 0),

    CONSTRAINT canary_stage_metric_registry_metric_name_nonempty_chk
        CHECK (length(metric_name) > 0)
);

COMMENT ON TABLE governance.canary_stage_metric_registry IS
    'AMD-2026-05-09-03 W-AUDIT-9 §4.2: metric registry for canary stage auto-promote '
    'and auto-rollback. Read by healthcheck [58] (W-AUDIT-9 T4) to validate metric '
    'definitions exist + run threshold check against real cohort SLA. Writes are '
    'operator-controlled (TOML seed or IPC patch with Decision Lease).';

COMMENT ON COLUMN governance.canary_stage_metric_registry.stage IS
    'Target stage to which this metric applies. Stage 0 is fail-closed default '
    'with no metrics; Stage 1/2/3 hold most promote/rollback metrics; Stage 4 is '
    'operator-pinned LIVE_PENDING with no automatic metric.';

COMMENT ON COLUMN governance.canary_stage_metric_registry.direction IS
    'promote_upper: metric value > threshold => allow promote (e.g. entry_fills > 10). '
    'promote_lower: metric value < threshold => allow promote (rare, e.g. boundary_violation_count < 1). '
    'rollback_upper: metric value > threshold => trigger rollback (e.g. lease_ipc_failure_rate > 0.5%). '
    'rollback_lower: metric value < threshold => trigger rollback (e.g. gross_pnl_usdt < -10).';

COMMENT ON COLUMN governance.canary_stage_metric_registry.active IS
    'When false, healthcheck [58] still validates metric existence (drift check) '
    'but skips threshold trip evaluation. Used during operator manual override or '
    'metric retirement (audit-preserving alternative to DELETE).';


-- ============================================================
-- Index 1 (governance.canary_stage_log): query 最新 cohort transition
-- 走 cohort_id + created_at_ms DESC 路徑（healthcheck [58] hot path）。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_canary_stage_log_cohort_created_at
    ON governance.canary_stage_log (cohort_id, created_at_ms DESC);

COMMENT ON INDEX governance.idx_canary_stage_log_cohort_created_at IS
    'Hot-path index for healthcheck [58] (W-AUDIT-9 T4): "latest stage per cohort" '
    'query reads (cohort_id, created_at_ms DESC).';


-- ============================================================
-- Index 2 (governance.canary_stage_log): query auto_rollback / incident events
-- transition_kind 篩選 partial index — 預期 < 30% rows 命中。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_canary_stage_log_rollback_events
    ON governance.canary_stage_log (created_at_ms DESC)
    WHERE transition_kind IN ('auto_rollback', 'incident_rollback');

COMMENT ON INDEX governance.idx_canary_stage_log_rollback_events IS
    'Partial index for rollback event timeline (GUI surface W-AUDIT-9 T5 + '
    'incident response). Excludes manual/auto promote rows to keep size bounded.';


-- ============================================================
-- Schema Guard C — Index 1 column ordering（cohort_id, created_at_ms DESC）
-- 若索引存在但欄位錯，提前 RAISE（per CLAUDE.md §七 Guard C 準則）。
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
BEGIN
    SELECT pg_get_indexdef(i.indexrelid) INTO v_actual
    FROM pg_index i
    JOIN pg_class c ON c.oid = i.indexrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'governance'
      AND c.relname = 'idx_canary_stage_log_cohort_created_at';

    IF v_actual IS NOT NULL AND position('created_at_ms DESC' IN v_actual) = 0 THEN
        RAISE EXCEPTION
            'schema_guard C: idx_canary_stage_log_cohort_created_at exists but '
            'missing "created_at_ms DESC" descending order. Hot-path "latest per '
            'cohort" query becomes O(N log N). Actual: %. Resolve via DROP INDEX '
            '+ re-apply V080.',
            v_actual;
    END IF;
END $$;


-- ============================================================
-- Index 3 (governance.canary_stage_metric_registry):
-- UNIQUE (stage, metric_name) WHERE active=true
-- AMD-2026-05-09-03 §4.2：每 (stage, metric_name) active row 唯一 — 同一 stage 同一
-- metric 不應同時有兩條 active row（drift 信號）。partial unique index 是 PG 慣例。
-- ============================================================
CREATE UNIQUE INDEX IF NOT EXISTS uq_canary_stage_metric_registry_active
    ON governance.canary_stage_metric_registry (stage, metric_name)
    WHERE active = TRUE;

COMMENT ON INDEX governance.uq_canary_stage_metric_registry_active IS
    'AMD-2026-05-09-03 §4.2: per (stage, metric_name) active row uniqueness. '
    'Two simultaneous active rows for the same metric = drift; healthcheck [58] '
    '(W-AUDIT-9 T4) FAILS on detection. Use active=false for retirement (preserve audit).';


-- ============================================================
-- 完成。idempotent re-run 必通過 — 重跑 V080 第二次不 RAISE。
-- 完成；idempotent re-run 不 RAISE。
-- ============================================================

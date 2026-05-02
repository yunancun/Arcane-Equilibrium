-- V035__governance_audit_log.sql
-- Purpose / 目的:
--   Create learning.governance_audit_log to sink GovernanceHub.review_live_candidate
--   verdicts, lease grants, lease auto-revokes, bulk re-evaluation events, and audit
--   write failures. Required by LG-5 Live Candidate Evaluation Contract RFC v2 §2.3
--   for full-schema raw input emission (R2/R3/R4 IMPL-5 retro 校準依據).
--
-- 建立 learning.governance_audit_log 作為 GovernanceHub.review_live_candidate 評估
-- 結果, lease 授予/自動撤銷, 批量重評, audit 寫入失敗事件的彙總表。LG-5 Live Candidate
-- Evaluation Contract RFC v2 §2.3 規定 — 必含 R2/R3/R4 raw input, 供 IMPL-5 7d retro 校準。
--
-- Migration order: V034 → V035 (no inter-migration dep beyond schema=learning existence
--                  and FK to learning.mlde_param_applications which is created by V032).
-- Idempotency: local psql -f V035 ... × 2 → 第二次無 RAISE (Guard A no-op; CREATE IF NOT EXISTS).
-- Guard A: enforced (table existence + required columns validation).
-- Guard B: N/A (fresh CREATE, no ALTER COLUMN).
-- Guard C: enforced (2 hot-path indexes via pg_get_indexdef compare).
--
-- Spec source / 規格來源:
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md §13
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard C
-- Reference retrofit pattern / 參考回補模式:
--   V031__ml_dream_edge_unblock.sql, V032__mlde_demo_param_applications.sql

CREATE SCHEMA IF NOT EXISTS learning;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate schema=learning exists; if table already exists, validate
-- required columns present; missing column → RAISE EXCEPTION (mirror V031/V032
-- retrofit pattern per CLAUDE.md §七).
--
-- Guard A: 驗 schema=learning 存在; 若 table 已存在則驗必要欄位俱在; 缺即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_schema_exists BOOLEAN;
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'id', 'ts', 'event_type', 'candidate_id', 'decision_lease_id',
        'verdict_decision', 'verdict_reason', 'rule_failures',
        'expected_net_bps_demo', 'expected_net_bps_live_adjusted', 'expected_net_bps_deflated',
        'cost_regime_ratio', 'cost_regime_ratio_clamped',
        'psr_value', 'psr_n_samples', 'psr_skew', 'psr_kurt',
        'sr_0_deflation', 'v_pending_net_bps',
        'lease_ttl_ms', 'lease_revoke_triggers',
        'decided_by', 'payload'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'learning'
    ) INTO v_schema_exists;

    IF NOT v_schema_exists THEN
        RAISE EXCEPTION 'V035 Guard A: schema "learning" does not exist; run earlier migrations first';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'governance_audit_log'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'learning'
                  AND table_name = 'governance_audit_log'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V035 Guard A: learning.governance_audit_log exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;

        RAISE NOTICE 'V035 Guard A: learning.governance_audit_log already exists with all required columns; CREATE TABLE will no-op';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Main table / 主表
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learning.governance_audit_log (
    id BIGSERIAL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'review_live_candidate',
        'lease_grant',
        'lease_auto_revoke',
        'bulk_re_evaluation',
        'audit_write_failed'
    )),
    candidate_id BIGINT NULL REFERENCES learning.mlde_param_applications(id),
    decision_lease_id TEXT NULL,
    verdict_decision TEXT NULL CHECK (
        verdict_decision IS NULL OR verdict_decision IN ('approve', 'reject', 'defer')
    ),
    verdict_reason TEXT NULL,
    rule_failures TEXT[] NOT NULL DEFAULT '{}',

    -- R2 raw inputs / R2 原始輸入
    expected_net_bps_demo DOUBLE PRECISION NULL,
    expected_net_bps_live_adjusted DOUBLE PRECISION NULL,
    expected_net_bps_deflated DOUBLE PRECISION NULL,
    cost_regime_ratio DOUBLE PRECISION NULL,
    cost_regime_ratio_clamped DOUBLE PRECISION NULL,

    -- R3 raw inputs / R3 原始輸入
    psr_value DOUBLE PRECISION NULL,
    psr_n_samples INT NULL,
    psr_skew DOUBLE PRECISION NULL,
    psr_kurt DOUBLE PRECISION NULL,

    -- R4 raw inputs / R4 原始輸入
    sr_0_deflation DOUBLE PRECISION NULL,
    v_pending_net_bps DOUBLE PRECISION NULL,

    -- Lease info / 租約資訊
    lease_ttl_ms INT NULL,
    lease_revoke_triggers TEXT[] NOT NULL DEFAULT '{}',

    -- Provenance / 來源
    decided_by TEXT NOT NULL,

    -- Forward-compat replay payload / 前向相容重放載荷
    payload JSONB NULL,

    PRIMARY KEY (id, ts)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TimescaleDB hypertable / TimescaleDB 超表
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'learning.governance_audit_log',
            'ts',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE
        );
        RAISE NOTICE 'V035: learning.governance_audit_log converted to hypertable (7d chunks)';
    ELSE
        RAISE NOTICE 'V035: TimescaleDB extension not present; skipping hypertable conversion (table remains regular)';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Hot-path indexes / 熱路徑索引
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_gov_audit_candidate_ts
    ON learning.governance_audit_log (candidate_id, ts DESC)
    WHERE candidate_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_gov_audit_event_type_ts
    ON learning.governance_audit_log (event_type, ts DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: validate hot-path index definitions match expected shape.
-- Guard C: 比對熱路徑索引定義是否符合預期; 任一 mismatch 即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx_def TEXT;
    v_expected_candidate_substring TEXT := 'CREATE INDEX idx_gov_audit_candidate_ts ON learning.governance_audit_log USING btree (candidate_id, ts DESC) WHERE (candidate_id IS NOT NULL)';
    v_expected_event_substring TEXT := 'CREATE INDEX idx_gov_audit_event_type_ts ON learning.governance_audit_log USING btree (event_type, ts DESC)';
BEGIN
    -- Check idx_gov_audit_candidate_ts / 檢查 idx_gov_audit_candidate_ts
    SELECT pg_get_indexdef(c.oid)
    INTO v_idx_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'learning'
      AND c.relname = 'idx_gov_audit_candidate_ts';

    IF v_idx_def IS NULL THEN
        RAISE EXCEPTION 'V035 Guard C: idx_gov_audit_candidate_ts not found after CREATE INDEX';
    END IF;

    IF position(v_expected_candidate_substring IN v_idx_def) = 0 THEN
        RAISE EXCEPTION
            'V035 Guard C: idx_gov_audit_candidate_ts definition mismatch. Expected substring: %, actual: %',
            v_expected_candidate_substring, v_idx_def;
    END IF;

    -- Check idx_gov_audit_event_type_ts / 檢查 idx_gov_audit_event_type_ts
    SELECT pg_get_indexdef(c.oid)
    INTO v_idx_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'learning'
      AND c.relname = 'idx_gov_audit_event_type_ts';

    IF v_idx_def IS NULL THEN
        RAISE EXCEPTION 'V035 Guard C: idx_gov_audit_event_type_ts not found after CREATE INDEX';
    END IF;

    IF position(v_expected_event_substring IN v_idx_def) = 0 THEN
        RAISE EXCEPTION
            'V035 Guard C: idx_gov_audit_event_type_ts definition mismatch. Expected substring: %, actual: %',
            v_expected_event_substring, v_idx_def;
    END IF;

    RAISE NOTICE 'V035 Guard C: both hot-path indexes validated';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Bilingual column comments / 中英欄位註解
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE learning.governance_audit_log IS
'GovernanceHub audit log for live candidate review verdicts, lease grants/revokes, bulk re-evaluations, and audit failures. Full schema per LG-5 RFC v2 §2.3 + §13. / GovernanceHub 活動審計表 — live candidate 評估, lease 授予/撤銷, 批量重評, audit 失敗。';

COMMENT ON COLUMN learning.governance_audit_log.id IS
'Auto-incremented primary key. / 自增主鍵。';

COMMENT ON COLUMN learning.governance_audit_log.ts IS
'Event timestamp (UTC). Hypertable partition key (7d chunks). / 事件時間戳; hypertable 分區鍵 (7天 chunk)。';

COMMENT ON COLUMN learning.governance_audit_log.event_type IS
'Event category: review_live_candidate / lease_grant / lease_auto_revoke / bulk_re_evaluation / audit_write_failed. / 事件類別。';

COMMENT ON COLUMN learning.governance_audit_log.candidate_id IS
'FK to learning.mlde_param_applications.id. NULL allowed for events not tied to a single candidate (e.g. bulk re-eval batch aggregate, audit write failure with unknown candidate). / mlde_param_applications.id 外鍵; 批量事件 / audit 失敗時可為 NULL。';

COMMENT ON COLUMN learning.governance_audit_log.decision_lease_id IS
'GovernanceHub-issued lease ID if verdict=approve. NULL otherwise. / 若 approve, 為 GovernanceHub 簽發的 lease ID; 否則 NULL。';

COMMENT ON COLUMN learning.governance_audit_log.verdict_decision IS
'review_live_candidate verdict: approve / reject / defer. NULL for non-review events. / 評估結果。';

COMMENT ON COLUMN learning.governance_audit_log.verdict_reason IS
'Reason enum from ReviewVerdict (e.g. approve_within_envelope, reject_cost_regime_drift, defer_data_insufficient). See LG-5 RFC v2 §2.2. / 評估理由列舉值; 詳 LG-5 RFC v2 §2.2。';

COMMENT ON COLUMN learning.governance_audit_log.rule_failures IS
'Array of rule IDs that failed (e.g. {R2, R3}). Empty array on approve. / 失敗規則 ID 陣列; approve 時為空。';

COMMENT ON COLUMN learning.governance_audit_log.expected_net_bps_demo IS
'R2 input: demo expected_net_bps as copied from source demo row (no adjustment). / R2 輸入: 從 demo 來源逐字複製的 expected_net_bps (未調整)。';

COMMENT ON COLUMN learning.governance_audit_log.expected_net_bps_live_adjusted IS
'R2 output: post-haircut live-adjusted expected_net_bps = demo × cost_regime_ratio_clamped - slippage_diff. / R2 輸出: haircut 後的 live 調整 expected_net_bps。';

COMMENT ON COLUMN learning.governance_audit_log.expected_net_bps_deflated IS
'R4 output: post-Bailey-LdP-SR_0 deflated expected_net_bps. NULL if R4 skipped (K<5). / R4 輸出: Bailey-LdP SR_0 deflation 後; K<5 跳過時為 NULL。';

COMMENT ON COLUMN learning.governance_audit_log.cost_regime_ratio IS
'R2 raw: live_maker_fill × live_fee_mult / demo_maker_fill / demo_fee_mult (un-clamped). / R2 原始: live/demo 成本制度比 (未 clamp)。';

COMMENT ON COLUMN learning.governance_audit_log.cost_regime_ratio_clamped IS
'R2 raw: clamp(cost_regime_ratio, 0.3, 1.0). Used directly in haircut formula. / R2 原始: clamp(0.3, 1.0) 後值; 直接用於 haircut。';

COMMENT ON COLUMN learning.governance_audit_log.psr_value IS
'R3 output: Probabilistic Sharpe Ratio against benchmark SR=0. NULL if R3 skipped (n<100). / R3 輸出: PSR(0); n<100 跳過時 NULL。';

COMMENT ON COLUMN learning.governance_audit_log.psr_n_samples IS
'R3 input: n_strategy_fills used to compute PSR (from payload.demo_realized_window). / R3 輸入: PSR 計算使用的 n。';

COMMENT ON COLUMN learning.governance_audit_log.psr_skew IS
'R3 raw: sample skewness fed into PSR Bailey-LdP correction. / R3 原始: 樣本偏度。';

COMMENT ON COLUMN learning.governance_audit_log.psr_kurt IS
'R3 raw: sample kurtosis fed into PSR Bailey-LdP correction. / R3 原始: 樣本峰度。';

COMMENT ON COLUMN learning.governance_audit_log.sr_0_deflation IS
'R4 raw: Bailey-LdP simplified SR_0 deflation magnitude (in bps). / R4 原始: Bailey-LdP SR_0 deflation 量 (bps)。';

COMMENT ON COLUMN learning.governance_audit_log.v_pending_net_bps IS
'R4 raw: variance of expected_net_bps_live_adjusted across K pending candidates. / R4 原始: K 個 pending 候選 R2 輸出的方差。';

COMMENT ON COLUMN learning.governance_audit_log.lease_ttl_ms IS
'Issued lease TTL in milliseconds (only set on approve). / 授予的 lease TTL (毫秒); approve 時填寫。';

COMMENT ON COLUMN learning.governance_audit_log.lease_revoke_triggers IS
'Healthcheck IDs that auto-revoke this lease if they FAIL during lease lifetime. / 自動撤銷 lease 的 healthcheck ID 陣列。';

COMMENT ON COLUMN learning.governance_audit_log.decided_by IS
'Trigger source: GovernanceHub.review_live_candidate.scheduler / .operator_manual:<actor> / .bulk_re_evaluation. / 觸發來源。';

COMMENT ON COLUMN learning.governance_audit_log.payload IS
'Full ReviewVerdict JSON snapshot for forward-compat replay. May contain fields not yet promoted to columns. / 完整 ReviewVerdict JSON 快照; 為未來欄位演化保留。';

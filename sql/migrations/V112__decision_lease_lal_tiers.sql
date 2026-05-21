-- ============================================================
-- V112: M1 Decision Lease Layered Approval (LAL) — 5 tier config + per-lease audit
--
-- 目的：
--   新增 governance.lease_lal_tiers (5 row 固定 config) + governance.lease_lal_assignments
--   (per-lease append-only assignment history) + governance.mv_lease_lal_eligibility
--   (per-lease 最新 tier + 90d incident-free MV)。
--   數字越大越嚴：LAL 0 = per-fill autonomous / LAL 4 = capital structure 永遠 operator attestation。
--
-- ADR / Spec：
--   ADR-0034 §Decision 1-6（per-lease emit / 6 hard gate / Console 2FA / 24h undo /
--     Tier 0 RETIRED blocker）為 LAL 0-4 single source of truth。
--   srv/docs/execution_plan/2026-05-21--v112_m1_decision_lease_lal_tiers_schema_spec.md §2-§5。
--   srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md §3 state machine。
--
-- Scope / 範圍：
--   - CREATE TABLE governance.lease_lal_tiers (15 col + 5 seed row LAL 0-4)
--   - CREATE TABLE governance.lease_lal_assignments (20 col + 2 composite CHECK + 2 FK)
--   - CREATE 3 hot-path indexes (lease_id / assigned_at DESC / (tier_level, assigned_at DESC))
--   - CREATE MATERIALIZED VIEW governance.mv_lease_lal_eligibility + 1 UNIQUE INDEX
--   - Guard A: governance schema + learning.governance_audit_log（V035/V053/V098 baseline）
--     存在驗證 + 既有 stub column 完整性驗證
--   - Guard C: CHECK enum + UNIQUE + 5 seed row + MV 對齊驗證
--
-- 不在範圍：
--   - V113 decay_signals FK constraint（V113 land 後另 V### ALTER ADD CONSTRAINT；本 V112
--     `no_incident_check_v113_ref` 為 BIGINT placeholder column 無 FK constraint）
--   - V099/V100 lease 表 FK constraint（application-layer cross-ref；非 schema FK）
--   - MV refresh cron（Sprint 1B `helper_scripts/refresh_lal_mv.sh` hourly）
--   - lal_gate Rust writer（Sprint 4 LAL 1 IMPL）
--
-- 為什麼 spec §4.1 寫 governance.audit_log 而本 SQL 改 learning.governance_audit_log：
--   V035 / V053 / V098 chain audit_log 全在 learning schema；spec doc §4.1 line 450 寫
--   "governance.audit_log" 是 schema 名 typo；遵 V098 既有實際 table location（empirical
--   verified on sandbox）。Spec doc follow-up correction 列入 report。
--
-- Idempotency：
--   IF NOT EXISTS / ON CONFLICT DO NOTHING / Guard 全 idempotent；雙跑 0 RAISE。
--
-- 參考 V094 / V098 / V103 EXTEND 範式。
-- ============================================================

-- ============================================================
-- Guard A: governance schema + learning.governance_audit_log prereq +
--          既有 stub column 完整性驗證
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- governance schema 存在驗
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name='governance'
    ) THEN
        RAISE EXCEPTION
            'V112 Guard A FAIL: governance schema missing. Apply baseline schema migration before V112.';
    END IF;

    -- learning.governance_audit_log 必須存在（V035 baseline；M1 LAL cross-ref audit target）
    -- 注意：spec doc §4.1 寫 governance.audit_log 為 schema typo；實際在 learning schema。
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='governance_audit_log'
    ) THEN
        RAISE EXCEPTION
            'V112 Guard A FAIL: learning.governance_audit_log missing — V035/V053/V098 baseline must apply before V112 (cross-ref audit target).';
    END IF;

    -- governance.lease_lal_tiers 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='lease_lal_tiers'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'tier_level', 'tier_name', 'auto_approve', 'approval_quorum',
            'clawback_ttl_sec', 'cohort_min_n', 'resource_quota_cpu_pct',
            'risk_envelope_usdt', 'human_final_review', 'description',
            'created_by', 'created_at', 'updated_by', 'updated_at', 'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='governance' AND table_name='lease_lal_tiers' AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V112 Guard A FAIL: governance.lease_lal_tiers exists but missing columns: %. Resolve schema drift before V112.',
                v_missing;
        END IF;
    END IF;

    -- governance.lease_lal_assignments 已存在的情境
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='lease_lal_assignments'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'lease_id', 'tier_level', 'assigned_by', 'assigned_at',
            'prev_tier_level', 'tier_change_reason',
            'no_incident_check_v113_ref', 'no_incident_check_pass',
            'no_incident_check_window_days', 'state_machine_step',
            'clawback_executed', 'clawback_at', 'engine_mode',
            'evidence_json', 'created_by', 'created_at',
            'updated_by', 'updated_at', 'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='governance' AND table_name='lease_lal_assignments' AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V112 Guard A FAIL: governance.lease_lal_assignments exists but missing columns: %. Resolve schema drift before V112.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ============================================================
-- Step 3: CREATE TABLE governance.lease_lal_tiers (config; 5 row 固定)
-- ============================================================
CREATE TABLE IF NOT EXISTS governance.lease_lal_tiers (
    tier_level                  INT PRIMARY KEY
                                CHECK (tier_level BETWEEN 0 AND 4),
    tier_name                   TEXT NOT NULL UNIQUE
                                CHECK (tier_name IN (
                                    'LAL_0_AUTO',
                                    'LAL_1_LIGHT_REVIEW',
                                    'LAL_2_FULL_REVIEW',
                                    'LAL_3_OPERATOR_APPROVAL',
                                    'LAL_4_OPERATOR_ATTESTATION'
                                )),
    auto_approve                BOOLEAN NOT NULL,
    approval_quorum             INT NOT NULL CHECK (approval_quorum >= 0),
    clawback_ttl_sec            INT NOT NULL CHECK (clawback_ttl_sec >= 0),
    cohort_min_n                INT NOT NULL CHECK (cohort_min_n >= 0),
    resource_quota_cpu_pct      NUMERIC(5,2)
                                CHECK (resource_quota_cpu_pct IS NULL OR
                                       (resource_quota_cpu_pct > 0 AND resource_quota_cpu_pct <= 100)),
    risk_envelope_usdt          NUMERIC(20,8)
                                CHECK (risk_envelope_usdt IS NULL OR risk_envelope_usdt > 0),
    human_final_review          BOOLEAN NOT NULL,
    description                 TEXT,
    created_by                  TEXT NOT NULL DEFAULT 'system_seed',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V112'
);

-- ============================================================
-- Step 4: Seed 5 tier rows (LAL 0-4; ON CONFLICT idempotent)
-- 數字越大越嚴 per ADR-0034 對齊矩陣。
-- ============================================================
INSERT INTO governance.lease_lal_tiers
    (tier_level, tier_name, auto_approve, approval_quorum, clawback_ttl_sec,
     cohort_min_n, resource_quota_cpu_pct, risk_envelope_usdt, human_final_review,
     description, created_by, source_version)
VALUES
    (0, 'LAL_0_AUTO', true, 0, 60, 0, 80.00, 5000.00000000, false,
     'Per-fill autonomous; always Guardian fast path; per ADR-0034 對齊矩陣 LAL 0',
     'system_seed', 'V112'),
    (1, 'LAL_1_LIGHT_REVIEW', true, 0, 300, 30, 60.00, 25000.00000000, false,
     'Intra-strategy reparam; Stage 4 + 30d stable + 6 hard gate; per ADR-0034 對齊矩陣 LAL 1',
     'system_seed', 'V112'),
    (2, 'LAL_2_FULL_REVIEW', true, 0, 600, 50, 40.00, 100000.00000000, false,
     'Cross-strategy reweight; Y2 gate + Console opt-in + 6 hard gate; per ADR-0034 對齊矩陣 LAL 2',
     'system_seed', 'V112'),
    (3, 'LAL_3_OPERATOR_APPROVAL', false, 1, 3600, 100, 20.00, NULL, true,
     'New strategy promotion; always operator manual approve; per ADR-0034 對齊矩陣 LAL 3',
     'system_seed', 'V112'),
    (4, 'LAL_4_OPERATOR_ATTESTATION', false, 1, 0, 200, 10.00, NULL, true,
     'Capital structure / venue change; always operator manual attest + 2FA; clawback 0 (immutable after attest); per ADR-0034 對齊矩陣 LAL 4',
     'system_seed', 'V112')
ON CONFLICT (tier_level) DO NOTHING;

-- ============================================================
-- Step 5: CREATE TABLE governance.lease_lal_assignments (history; append-only)
-- 注意：no_incident_check_v113_ref 為 BIGINT placeholder column 無 FK constraint；
-- V113 land 後另 V### ALTER ADD CONSTRAINT FK → learning.decay_signals(id)。
-- ============================================================
CREATE TABLE IF NOT EXISTS governance.lease_lal_assignments (
    id                              BIGSERIAL PRIMARY KEY,
    lease_id                        UUID NOT NULL,
    tier_level                      INT NOT NULL
                                    REFERENCES governance.lease_lal_tiers(tier_level),
    assigned_by                     TEXT NOT NULL,
    assigned_at                     TIMESTAMPTZ NOT NULL DEFAULT now(),
    prev_tier_level                 INT
                                    REFERENCES governance.lease_lal_tiers(tier_level),
    tier_change_reason              TEXT
                                    CHECK (tier_change_reason IS NULL OR tier_change_reason IN (
                                        'auto', 'manual', 'health_degraded',
                                        'decay_signal', 'operator_override', 'initial_seed'
                                    )),
    no_incident_check_v113_ref      BIGINT,
    no_incident_check_pass          BOOLEAN,
    no_incident_check_window_days   INT NOT NULL DEFAULT 90,
    state_machine_step              INT NOT NULL CHECK (state_machine_step BETWEEN 0 AND 8),
    clawback_executed               BOOLEAN NOT NULL DEFAULT FALSE,
    clawback_at                     TIMESTAMPTZ,
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    evidence_json                   JSONB,
    created_by                      TEXT NOT NULL DEFAULT 'lal_gate',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                      TEXT,
    updated_at                      TIMESTAMPTZ,
    source_version                  TEXT NOT NULL DEFAULT 'V112',
    CONSTRAINT chk_clawback_consistency CHECK (
        (clawback_executed = FALSE AND clawback_at IS NULL) OR
        (clawback_executed = TRUE AND clawback_at IS NOT NULL)
    ),
    CONSTRAINT chk_no_incident_consistency CHECK (
        (no_incident_check_v113_ref IS NULL AND no_incident_check_pass IS NULL) OR
        (no_incident_check_v113_ref IS NOT NULL AND no_incident_check_pass IS NOT NULL)
    )
);

-- ============================================================
-- Step 6: Hot-path indexes (per V112 spec §3.2)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_lal_lease_id
    ON governance.lease_lal_assignments (lease_id);

CREATE INDEX IF NOT EXISTS idx_lal_assigned_at
    ON governance.lease_lal_assignments (assigned_at DESC);

CREATE INDEX IF NOT EXISTS idx_lal_tier_assigned
    ON governance.lease_lal_assignments (tier_level, assigned_at DESC);

-- ============================================================
-- Step 7: Materialized view governance.mv_lease_lal_eligibility
-- per-lease 最新 tier + 90d incident-free 聚合；REFRESH CONCURRENTLY 走 UNIQUE INDEX
-- engine_mode filter IN ('live','live_demo')：replay rows 不入 eligibility 評估
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS governance.mv_lease_lal_eligibility AS
WITH latest_per_lease AS (
    SELECT DISTINCT ON (lease_id)
        lease_id, tier_level AS current_tier_level,
        assigned_at AS last_assigned_at,
        no_incident_check_pass AS last_incident_free_pass,
        no_incident_check_window_days, engine_mode
    FROM governance.lease_lal_assignments
    WHERE engine_mode IN ('live', 'live_demo')
    ORDER BY lease_id, assigned_at DESC
),
incident_free_90d AS (
    SELECT lease_id,
           BOOL_AND(no_incident_check_pass) FILTER (WHERE no_incident_check_pass IS NOT NULL) AS all_checks_pass_90d,
           COUNT(*) FILTER (WHERE no_incident_check_pass = false) AS incident_count_90d
    FROM governance.lease_lal_assignments
    WHERE engine_mode IN ('live', 'live_demo')
      AND assigned_at > now() - INTERVAL '90 days'
    GROUP BY lease_id
)
SELECT
    l.lease_id, l.current_tier_level,
    t.tier_name AS current_tier_name,
    t.auto_approve AS current_auto_approve,
    t.human_final_review AS current_human_final_review,
    l.last_assigned_at, l.last_incident_free_pass,
    i.all_checks_pass_90d,
    COALESCE(i.incident_count_90d, 0) AS incident_count_90d,
    CASE
        WHEN i.incident_count_90d IS NULL THEN 'eligible_no_history'
        WHEN i.incident_count_90d = 0 THEN 'eligible_clean_90d'
        ELSE 'ineligible_incident_in_90d'
    END AS eligibility_status,
    l.engine_mode,
    now() AS refreshed_at
FROM latest_per_lease l
LEFT JOIN governance.lease_lal_tiers t ON l.current_tier_level = t.tier_level
LEFT JOIN incident_free_90d i ON l.lease_id = i.lease_id;

-- UNIQUE INDEX 支援 REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS mv_lease_lal_eligibility_pkey
    ON governance.mv_lease_lal_eligibility (lease_id);

-- ============================================================
-- Step 8: Guard C — CHECK enum + UNIQUE + 5 seed row + MV 對齊驗證
-- 重跑 V112 第二次必不 RAISE（idempotent post-check）
-- ============================================================
DO $$
DECLARE v_actual TEXT;
DECLARE v_seed_count INT;
BEGIN
    -- tier_name CHECK 5 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.lease_lal_tiers'::regclass
      AND conname LIKE '%tier_name%check%';
    IF v_actual IS NOT NULL THEN
        IF position('LAL_0_AUTO' IN v_actual) = 0
           OR position('LAL_1_LIGHT_REVIEW' IN v_actual) = 0
           OR position('LAL_2_FULL_REVIEW' IN v_actual) = 0
           OR position('LAL_3_OPERATOR_APPROVAL' IN v_actual) = 0
           OR position('LAL_4_OPERATOR_ATTESTATION' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: governance.lease_lal_tiers tier_name CHECK enum mismatch. Actual: %.',
                v_actual;
        END IF;
    END IF;

    -- tier_change_reason CHECK 6 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.lease_lal_assignments'::regclass
      AND conname LIKE '%tier_change_reason%check%';
    IF v_actual IS NOT NULL THEN
        IF position('auto' IN v_actual) = 0
           OR position('manual' IN v_actual) = 0
           OR position('health_degraded' IN v_actual) = 0
           OR position('decay_signal' IN v_actual) = 0
           OR position('operator_override' IN v_actual) = 0
           OR position('initial_seed' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: lease_lal_assignments tier_change_reason CHECK enum mismatch. Actual: %.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 5 值齊全（含 'replay' for M11）
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.lease_lal_assignments'::regclass
      AND conname LIKE '%engine_mode%check%';
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: lease_lal_assignments engine_mode CHECK enum mismatch. Actual: %.',
                v_actual;
        END IF;
    END IF;

    -- tier_level CHECK 0-4
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='governance.lease_lal_tiers'::regclass
      AND conname LIKE '%tier_level%check%';
    IF v_actual IS NOT NULL THEN
        IF position('0' IN v_actual) = 0
           OR position('4' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V112 Guard C FAIL: governance.lease_lal_tiers tier_level CHECK BETWEEN 0 AND 4 missing. Actual: %.',
                v_actual;
        END IF;
    END IF;

    -- 5 seed rows 完整
    SELECT count(*) INTO v_seed_count FROM governance.lease_lal_tiers;
    IF v_seed_count > 0 AND v_seed_count != 5 THEN
        RAISE EXCEPTION
            'V112 Guard C FAIL: governance.lease_lal_tiers seed row count mismatch. Actual: %. Expected: 5 (LAL 0-4).',
            v_seed_count;
    END IF;

    -- MV 存在驗
    IF NOT EXISTS (
        SELECT 1 FROM pg_matviews
        WHERE schemaname='governance' AND matviewname='mv_lease_lal_eligibility'
    ) THEN
        RAISE EXCEPTION
            'V112 Guard C FAIL: mv_lease_lal_eligibility missing after migration body.';
    END IF;
END $$;

-- ============================================================
-- Step 9: COMMENT (audit metadata; per V094 範式)
-- ============================================================
COMMENT ON TABLE governance.lease_lal_tiers IS
    'M1 LAL Tier Config (V112). 5 row seed per ADR-0034. tier_level 0 lowest risk / 4 highest risk; auto_approve=true for 0/1/2; human_final_review=true for 3/4.';

COMMENT ON TABLE governance.lease_lal_assignments IS
    'M1 LAL Per-Lease Assignment History (V112). Append-only audit ledger; tier_change_reason 6 values (auto/manual/health_degraded/decay_signal/operator_override/initial_seed); clawback_consistency + no_incident_consistency CHECK enforced.';

COMMENT ON MATERIALIZED VIEW governance.mv_lease_lal_eligibility IS
    'M1 LAL Eligibility MV (V112). Per-lease latest tier + 90d incident-free check; eligibility_status 3 values (eligible_no_history / eligible_clean_90d / ineligible_incident_in_90d); REFRESH CONCURRENTLY hourly via cron (Sprint 1B).';

COMMENT ON COLUMN governance.lease_lal_assignments.no_incident_check_v113_ref IS
    'Placeholder FK to V113 learning.decay_signals(id); V113 land 後另 V### ALTER ADD CONSTRAINT NOT VALID + VALIDATE。';

COMMENT ON COLUMN governance.lease_lal_assignments.engine_mode IS
    'paper/demo/live_demo/live/replay. replay 為 M11 replay engine 寫入時 tag; training filter 仍 IN (live, live_demo).';

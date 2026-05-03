-- V054__lease_transitions_audit_writer.sql
-- REF-20 Sprint 3 Track H E-4 — Decision Lease retrofit V054 schema.
-- AMD-2026-05-02-01 §3 point 5 (audit writer trail) + §4 AC-1 condition
-- (learning.lease_transitions distinct count >= 5).
--
-- REF-20 Sprint 3 Track H E-4 — Decision Lease retrofit V054 schema。
-- AMD-2026-05-02-01 §3 點 5（audit writer trail）+ §4 AC-1 條件
-- （learning.lease_transitions distinct count >= 5）。
--
-- Purpose / 目的:
--   Two atomic schema additions for the Decision Lease retrofit
--   audit-trail backbone:
--
--     1. NEW TABLE `learning.lease_transitions` — stores every lease state
--        machine transition emitted by the Rust facade
--        `GovernanceCore::acquire_lease/release_lease` paths via the
--        E-1 contract `LeaseTransitionMsg` channel. TimescaleDB hypertable
--        (1-day chunk) for retention scan. Backbone of AC-1 / AC-3 / AC-4
--        observation queries.
--
--     2. CHECK enum extension on `learning.governance_audit_log.event_type`
--        from V053 14-value canonical list to V054 21-value canonical list,
--        adding 7 lease lifecycle event_type values used by future caller-side
--        emit (e.g. handoff_routes lease accept/reject) that re-uses the
--        long-standing governance_audit_log table.
--
--   兩個原子 schema 新增，組成 Decision Lease retrofit audit trail 主幹：
--     1. 新表 `learning.lease_transitions` — 儲存 Rust facade
--        `GovernanceCore::acquire_lease/release_lease` 透過 E-1 契約
--        `LeaseTransitionMsg` channel 發出的每筆 lease state machine 遷移。
--        TimescaleDB hypertable（1-day chunk）以利 retention 掃描。
--        AC-1 / AC-3 / AC-4 觀察查詢的主幹。
--     2. `learning.governance_audit_log.event_type` CHECK enum 擴充，由
--        V053 14 值 canonical list 擴為 V054 21 值（新增 7 個 lease
--        lifecycle event_type），給未來 caller-side emit 路徑（例如
--        handoff_routes lease accept/reject）重用既存 governance_audit_log
--        表使用。
--
-- Why one migration / 為何單一 migration:
--   V054 ships TWO related changes (NEW table + V053 enum extension) that
--   together comprise the Decision Lease retrofit audit-trail surface.
--   Splitting into V054a/V054b would require staged deploy where Rust
--   facade emit may write to an absent table or fall through V053's
--   14-value CHECK on caller-side emit. Single V054 atomic deploy is
--   the minimal-risk path.
--
--   V054 同時 ship 兩相關改動（新表 + V053 enum 擴展），合成 Decision
--   Lease retrofit audit-trail 接口。拆兩個 migration 會出現「Rust facade
--   可能寫到不存在的表」或「caller-side emit 撞 V053 14 值 CHECK」的
--   階梯部署 race。合一 V054 是最小風險路徑。
--
-- Why 7 event_type values / 為何 7 個 event_type:
--   E-4 task spec lists 7 lease lifecycle events that align with the
--   facade emit semantics (one event_type per acquire/release outcome
--   plus one generic SM transition tag for caller-side emit beyond
--   acquire/release):
--     1. lease_acquire_request   — caller initiated acquire_lease()
--     2. lease_acquire_success   — facade returned LeaseId::Active(...)
--     3. lease_acquire_fail      — facade returned Err (auth/ttl/sm fail)
--     4. lease_release_consumed  — facade release_lease(.., Consumed)
--     5. lease_release_failed    — facade release_lease(.., Failed)
--     6. lease_release_cancelled — facade release_lease(.., Cancelled)
--     7. lease_sm_transition     — generic SM transition tag for caller-side
--                                  emit beyond acquire/release (frozen,
--                                  expired_by_time, rejected, etc.)
--
--   E-4 task spec 列出 7 個 lease lifecycle event 對應 facade emit 語意
--   （每 acquire/release outcome 一個 event_type，加一個 generic SM
--   transition tag 給 acquire/release 以外的 caller-side emit）。
--
-- Why these 7 differ from PA design's 7 / 與 PA design 7 個的差異:
--   PA design §3.3 listed 7 SM-state-name events
--   (lease_acquired/lease_activated/...). E-4 task spec uses
--   acquire/release-semantic events. The semantic-aligned set lets
--   audit reconstruction tie one row to one acquire OR release outcome
--   directly without joining the SM transition table. Both are observable
--   from `learning.lease_transitions.to_state` / `event` columns; here
--   we use the task-spec 7 names for `event_type` enum.
--
--   PA design §3.3 列出的是 7 個 SM 狀態名（lease_acquired 等）。E-4 task
--   spec 改用 acquire/release 語意名。Audit reconstruction 可一筆 row 對
--   一個 acquire 或 release outcome 直接定位，不必 JOIN SM transition 表。
--   兩者皆可從 `learning.lease_transitions.to_state` / `event` column 觀察；
--   這裡 `event_type` enum 用 task-spec 7 名。
--
-- Idempotency / 幂等性:
--   local psql -f V054 ... × 2 → second run no-op via:
--     1. Guard A: lease_transitions table existence + required columns probe.
--     2. CREATE TABLE IF NOT EXISTS for lease_transitions (idempotent).
--     3. CREATE INDEX IF NOT EXISTS for hot-path indices (idempotent).
--     4. TimescaleDB create_hypertable() with if_not_exists => TRUE.
--     5. Probe existing CHECK constraint def for the 7 NEW lease event_type
--        values; if all present → RAISE NOTICE skip (idempotent re-run).
--     6. Otherwise BEGIN + LOCK TABLE ACCESS EXCLUSIVE + DROP+ADD canonical
--        21-value list + COMMIT (race-free per V053 retrofit F2 pattern).
--
-- Guard A: enforced (lease_transitions table existence + 14 required columns
--                    + governance_audit_log V035 base existence check).
-- Guard B: N/A (no column type mutation; only NEW table CREATE + CHECK
--               constraint replacement).
-- Guard C: enforced (3 hot-path indexes via CREATE INDEX IF NOT EXISTS;
--                    pg_get_indexdef compare unnecessary for new-table indexes
--                    since they cannot pre-exist with different definitions).
--
-- Spec source / 規格來源:
--   docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md
--     §3 point 5 (audit writer trail wiring contract).
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md
--     §3.3 V054 SQL schema additions + §4 #1 + #2 risk push-back.
--   docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint3_track_h_e1_rust_facade.md
--     §6.5 LeaseTransitionMsg contract for E-4 audit writer.
--
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V054 (Sprint 3 Track H E-4
--   PM dispatch, 2026-05-03; v1.10 ledger update).
--
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard C.
--   sql/migrations/V053__governance_audit_log_replay_event_types.sql
--     (race-free DROP+ADD with ACCESS EXCLUSIVE LOCK pattern).

CREATE SCHEMA IF NOT EXISTS learning;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A part 1: validate V035 base table existence (governance_audit_log
-- must deploy before V054 because we extend its CHECK enum).
--
-- Guard A 第 1 部：驗 V035 base table 存在（governance_audit_log 必先 V054
-- 後，因為我們擴展其 CHECK enum）。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_audit_log_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'governance_audit_log'
    ) INTO v_audit_log_exists;

    IF NOT v_audit_log_exists THEN
        RAISE EXCEPTION
            'V054 Guard A: learning.governance_audit_log not found; V035 must deploy before V054';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A part 2: if learning.lease_transitions already exists, verify
-- required columns are present; missing column → RAISE EXCEPTION.
--
-- Guard A 第 2 部：若 learning.lease_transitions 已存在則驗必要欄位俱在；
-- 缺即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'transition_id', 'lease_id', 'from_state', 'to_state', 'event',
        'initiator', 'reason_codes', 'requires_approval', 'approved_by',
        'profile', 'engine_mode', 'context_id', 'ts_ms', 'created_at'
    ];
    v_col TEXT;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'lease_transitions'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'learning'
                  AND table_name = 'lease_transitions'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V054 Guard A: learning.lease_transitions exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;
        RAISE NOTICE 'V054 Guard A: learning.lease_transitions already present with all required columns; continuing to enum extension';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- CREATE TABLE learning.lease_transitions
-- 建立 learning.lease_transitions
--
-- Column contract (matches LeaseTransitionMsg in
-- srv/rust/openclaw_core/src/governance_core.rs §198-232):
--
--   transition_id     TEXT NOT NULL — TransitionRecord 12-hex random id
--                      (sm/mod.rs ::TransitionRecord::new generates "tx:xxx").
--   lease_id          TEXT NOT NULL — Lease object id "lease:xxx" 12-hex.
--   from_state        TEXT NULLABLE — SM state before (NULL for initial draft).
--   to_state          TEXT NOT NULL — SM state after.
--   event             TEXT NOT NULL — SmEvent::as_str() value.
--   initiator         TEXT NOT NULL — initiator role (rust_facade, etc.).
--   reason_codes      TEXT[] DEFAULT ARRAY[]::TEXT[] — reason codes.
--   requires_approval BOOLEAN DEFAULT FALSE — approval gate flag.
--   approved_by       TEXT NULLABLE — approval actor.
--   profile           TEXT NOT NULL — GovernanceProfile snapshot
--                      ("Production" / "Validation" / "Exploration").
--   engine_mode       TEXT NOT NULL — engine mode ("paper" / "demo" /
--                      "live_demo" / "live_mainnet" / "shadow"); §4 #2 push
--                      back filter — 'shadow' rows are excluded from AC-1.
--   context_id        TEXT NULLABLE — DCS context_id for cross-row JOIN.
--   ts_ms             BIGINT NOT NULL — facade emit timestamp (ms since epoch).
--   created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW() — DB write time
--                      (separate from ts_ms because facade may emit out-of-order
--                      under contention).
--
--   PRIMARY KEY (transition_id, created_at) — TimescaleDB hypertable requires
--   the partition key (created_at) in the PK.
--
-- 欄位契約對齊 srv/rust/openclaw_core/src/governance_core.rs §198-232 的
-- LeaseTransitionMsg struct；PK = (transition_id, created_at) 因 TimescaleDB
-- hypertable 要求 partition key 入 PK。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learning.lease_transitions (
    transition_id      TEXT        NOT NULL,
    lease_id           TEXT        NOT NULL,
    from_state         TEXT,
    to_state           TEXT        NOT NULL,
    event              TEXT        NOT NULL,
    initiator          TEXT        NOT NULL,
    reason_codes       TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    requires_approval  BOOLEAN     NOT NULL DEFAULT FALSE,
    approved_by        TEXT,
    profile            TEXT        NOT NULL,
    engine_mode        TEXT        NOT NULL,
    context_id         TEXT,
    ts_ms              BIGINT      NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (transition_id, created_at)
);

-- Add CHECK constraints conditionally so re-runs don't error.
-- 條件式加 CHECK 約束，重跑不報錯。
DO $$
BEGIN
    -- profile enum: GovernanceProfile 3-value Production/Validation/Exploration
    -- profile enum：GovernanceProfile 3 值
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lease_transitions_profile'
          AND conrelid = 'learning.lease_transitions'::regclass
    ) THEN
        ALTER TABLE learning.lease_transitions
            ADD CONSTRAINT chk_lease_transitions_profile
            CHECK (profile IN ('Production', 'Validation', 'Exploration'));
        RAISE NOTICE 'V054: added CHECK chk_lease_transitions_profile (3-value GovernanceProfile)';
    ELSE
        RAISE NOTICE 'V054: chk_lease_transitions_profile already present; skipping';
    END IF;

    -- to_state enum: 9-value LeaseState (Draft/Registered/Active/Bridged/
    --   Frozen/Revoked/Expired/Rejected/Consumed); aligned with
    --   sm/lease.rs::LeaseState::as_str() (UPPERCASE).
    -- to_state enum：9 值 LeaseState（Draft 等），對齊 sm/lease.rs UPPERCASE。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lease_transitions_to_state'
          AND conrelid = 'learning.lease_transitions'::regclass
    ) THEN
        ALTER TABLE learning.lease_transitions
            ADD CONSTRAINT chk_lease_transitions_to_state
            CHECK (to_state IN (
                'DRAFT', 'REGISTERED', 'ACTIVE', 'BRIDGED',
                'FROZEN', 'REVOKED', 'EXPIRED', 'REJECTED', 'CONSUMED'
            ));
        RAISE NOTICE 'V054: added CHECK chk_lease_transitions_to_state (9-value LeaseState)';
    ELSE
        RAISE NOTICE 'V054: chk_lease_transitions_to_state already present; skipping';
    END IF;

    -- engine_mode enum: 5-value (paper/demo/live_demo/live_mainnet/shadow);
    --   aligned with engine_mode tagging policy. 'shadow' is filterable in
    --   AC-1 query (PA design §4 #2 push back).
    -- engine_mode enum：5 值對齊 engine_mode tagging；shadow 在 AC-1 query 過濾。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lease_transitions_engine_mode'
          AND conrelid = 'learning.lease_transitions'::regclass
    ) THEN
        ALTER TABLE learning.lease_transitions
            ADD CONSTRAINT chk_lease_transitions_engine_mode
            CHECK (engine_mode IN (
                'paper', 'demo', 'live_demo', 'live_mainnet', 'shadow'
            ));
        RAISE NOTICE 'V054: added CHECK chk_lease_transitions_engine_mode (5-value)';
    ELSE
        RAISE NOTICE 'V054: chk_lease_transitions_engine_mode already present; skipping';
    END IF;

    -- ts_ms sanity: positive (>0) reject epoch-0 rows poisoning time-range
    --   queries. Aligned with database/exit_feature_writer.rs ts_ms=0 reject.
    -- ts_ms 合理性：>0 拒絕 epoch-0 row（會毒化 time-range query），
    --   與 database/exit_feature_writer.rs 的 ts_ms=0 reject 一致。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_lease_transitions_ts_ms_positive'
          AND conrelid = 'learning.lease_transitions'::regclass
    ) THEN
        ALTER TABLE learning.lease_transitions
            ADD CONSTRAINT chk_lease_transitions_ts_ms_positive
            CHECK (ts_ms > 0);
        RAISE NOTICE 'V054: added CHECK chk_lease_transitions_ts_ms_positive (epoch-0 reject)';
    ELSE
        RAISE NOTICE 'V054: chk_lease_transitions_ts_ms_positive already present; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path indexes for AC-1 / AC-3 / AC-4 query patterns.
--
--   Index 1: idx_lease_transitions_lease_id_ts — covers
--            "list transitions for a single lease" hot path.
--   Index 2: idx_lease_transitions_to_state_profile_ts — covers
--            AC-1 "distinct to_state count by profile" weekly audit.
--   Index 3: idx_lease_transitions_engine_mode_ts — covers PA design §4
--            #2 push back: filter by engine_mode != 'shadow'.
--
-- Guard C：hot-path 索引，覆蓋 AC-1 / AC-3 / AC-4 查詢樣式。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_lease_transitions_lease_id_ts
    ON learning.lease_transitions (lease_id, ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_lease_transitions_to_state_profile_ts
    ON learning.lease_transitions (to_state, profile, ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_lease_transitions_engine_mode_ts
    ON learning.lease_transitions (engine_mode, ts_ms DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- TimescaleDB hypertable: 1-day chunk_time_interval (high write rate expected
-- under Production lease load — ~50-200 row/day per active 5-Agent shadow path).
-- TimescaleDB hypertable：1-day chunk_time_interval。
--
-- Retention TODO / TODO 保留期:
--   No drop_chunks() retention policy set in V054. Per CLAUDE.md §三 P2
--   ticket P2-WAVE-9-V047-V048-RETENTION pattern, retention is intentionally
--   deferred to a follow-up P2 ticket because:
--     1. Initial AC-1 baseline accumulation needs ≥ 7-30 day window (cannot
--        truncate during baseline phase).
--     2. Operator hardware budget requires per-table retention review
--        (memory hardware_constraints: PG ~4-8GB).
--     3. Retention parameters are observability-policy decisions, not
--        schema-essential.
--   Open P2 ticket: lease_transitions retention review after 30d baseline
--   accumulation; expected default = 90d retention with weekly chunk drop.
--
-- V054 不設 drop_chunks() retention policy，依 CLAUDE.md §三 P2 ticket
-- P2-WAVE-9-V047-V048-RETENTION 模式延至 follow-up P2 ticket：
--   1. AC-1 baseline 累積需 7-30d window，不可 truncate
--   2. operator 硬體預算需逐表 retention review
--   3. retention 參數是觀察性政策決策，非 schema-必要
-- 開 P2 ticket：30d baseline 累積後 review；預期 default 90d retention。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable(
            'learning.lease_transitions',
            'created_at',
            chunk_time_interval => INTERVAL '1 day',
            if_not_exists => TRUE
        );
        RAISE NOTICE 'V054: lease_transitions promoted to TimescaleDB hypertable (1-day chunks)';
    ELSE
        RAISE NOTICE 'V054: TimescaleDB extension not present; skipping hypertable promotion (table works as plain PG table)';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT ON TABLE for DBA discoverability.
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE learning.lease_transitions IS
'AMD-2026-05-02-01 §3 point 5 + §4 AC-1 backbone — every Decision Lease '
'state machine transition emitted by the Rust facade GovernanceCore::'
'acquire_lease/release_lease via E-1 LeaseTransitionMsg channel. '
'engine_mode = ''shadow'' rows excluded from AC-1 (PA design §4 #2). / '
'AMD-2026-05-02-01 §3 點 5 + §4 AC-1 主幹 — 由 Rust facade GovernanceCore::'
'acquire_lease/release_lease 透過 E-1 LeaseTransitionMsg channel 發出的'
'每筆 Decision Lease 狀態機遷移；shadow row 在 AC-1 排除。';

-- ─────────────────────────────────────────────────────────────────────────────
-- learning.governance_audit_log event_type CHECK enum extension:
-- V053 14-value canonical → V054 21-value canonical (add 7 lease lifecycle).
--
-- Pre-V054 (V053):
--    1. review_live_candidate
--    2. lease_grant
--    3. lease_auto_revoke
--    4. bulk_re_evaluation
--    5. audit_write_failed
--    6. replay_handoff_request                   (V044 P6-S15)
--    7. replay_run_started                       (V053 Track A)
--    8. replay_run_cancelled                     (V053 Track A)
--    9. replay_manifest_verify_attempted         (V053 Track A)
--   10. replay_signature_test_key_blocked        (V053 Track C P0-2)
--   11. replay_pid_identity_mismatch             (V053 Track C P0-4)
--   12. replay_idor_admin_bypass                 (V053 Track C P0-5a)
--   13. replay_artifact_path_traversal_blocked   (V053 Track C P0-5b)
--   14. replay_argv_mismatch_blocked             (V053 Track A P0-3)
--
-- V054 NEW (REF-20 Sprint 3 Track H E-4 — AMD-2026-05-02-01 §3 point 5):
--   15. lease_acquire_request    — caller initiated acquire_lease()
--   16. lease_acquire_success    — facade returned LeaseId::Active(...)
--   17. lease_acquire_fail       — facade returned Err
--   18. lease_release_consumed   — facade release_lease(.., Consumed)
--   19. lease_release_failed     — facade release_lease(.., Failed)
--   20. lease_release_cancelled  — facade release_lease(.., Cancelled)
--   21. lease_sm_transition      — generic SM transition tag for caller-side
--                                  emit (frozen, expired_by_time, rejected)
--
-- Total: 21 canonical values.
--
-- V053→V054 透過 DROP+ADD 將 V035 event_type CHECK 從 14 值擴為 21 值
-- （新增 7 個 lease lifecycle event_type）。
--
-- ─────────────────────────────────────────────────────────────────────────────
-- Race-free DROP+ADD via ACCESS EXCLUSIVE table lock (mirror V053 retrofit F2).
-- DROP+ADD 對置於顯式 transaction 內，先 ACCESS EXCLUSIVE LOCK TABLE。
-- ─────────────────────────────────────────────────────────────────────────────
BEGIN;

DO $$
DECLARE
    v_check_def TEXT;
    v_v054_present BOOLEAN := FALSE;
BEGIN
    -- Probe existing CHECK constraint on event_type column (idempotency
    -- short-circuit BEFORE LOCK TABLE — re-runs do not block writers).
    -- 探測 event_type column 的 CHECK constraint（idempotency 短路於
    -- LOCK TABLE 之前 — 重跑不阻塞 writer）。
    SELECT pg_get_constraintdef(c.oid)
    INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'learning'
      AND t.relname = 'governance_audit_log'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%event_type%';

    -- Idempotency: if all V054 NEW 7 enum values already present, skip.
    -- 幂等：若 V054 NEW 7 值已在 → skip。
    IF v_check_def IS NOT NULL
       AND position('lease_acquire_request' IN v_check_def) > 0
       AND position('lease_acquire_success' IN v_check_def) > 0
       AND position('lease_acquire_fail' IN v_check_def) > 0
       AND position('lease_release_consumed' IN v_check_def) > 0
       AND position('lease_release_failed' IN v_check_def) > 0
       AND position('lease_release_cancelled' IN v_check_def) > 0
       AND position('lease_sm_transition' IN v_check_def) > 0
    THEN
        v_v054_present := TRUE;
    END IF;

    IF v_v054_present THEN
        RAISE NOTICE 'V054: governance_audit_log event_type CHECK already extended with all 7 V054 lease lifecycle event_type values; skipping';
    ELSE
        -- Take ACCESS EXCLUSIVE on the audit table BEFORE the DROP+ADD
        -- pair so concurrent INSERT blocks across the gap (no "constraint
        -- absent" window). Lock auto-released at COMMIT.
        -- DROP+ADD 前先取 ACCESS EXCLUSIVE，concurrent INSERT 跨 gap 阻塞
        -- （CHECK 永遠在守門）。COMMIT 自動釋鎖。
        LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;

        -- DROP existing CHECK (if any) and re-ADD with 21-value canonical list.
        -- DROP 既有 CHECK（若有）並用 21 值 canonical list 重 ADD。
        IF EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'learning'
              AND t.relname = 'governance_audit_log'
              AND c.contype = 'c'
              AND c.conname LIKE '%event_type%'
        ) THEN
            EXECUTE 'ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check';
            RAISE NOTICE 'V054: dropped existing event_type CHECK on learning.governance_audit_log (under ACCESS EXCLUSIVE)';
        END IF;

        ALTER TABLE learning.governance_audit_log
            ADD CONSTRAINT governance_audit_log_event_type_check
            CHECK (event_type IN (
                -- V035 base 5 (1..5)
                'review_live_candidate',
                'lease_grant',
                'lease_auto_revoke',
                'bulk_re_evaluation',
                'audit_write_failed',
                -- V044 P6-S15 (6)
                'replay_handoff_request',
                -- V053 Sprint 1 Track A/C (7..14)
                'replay_run_started',
                'replay_run_cancelled',
                'replay_manifest_verify_attempted',
                'replay_signature_test_key_blocked',
                'replay_pid_identity_mismatch',
                'replay_idor_admin_bypass',
                'replay_artifact_path_traversal_blocked',
                'replay_argv_mismatch_blocked',
                -- V054 Sprint 3 Track H E-4 NEW 7 lease lifecycle (15..21)
                'lease_acquire_request',
                'lease_acquire_success',
                'lease_acquire_fail',
                'lease_release_consumed',
                'lease_release_failed',
                'lease_release_cancelled',
                'lease_sm_transition'
            ));
        RAISE NOTICE 'V054: added event_type CHECK with 21-value canonical list (5 V035 base + 1 V044 + 8 V053 + 7 V054 lease) under ACCESS EXCLUSIVE lock';
    END IF;
END $$;

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT ON CONSTRAINT updated to reflect V054 extension.
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON CONSTRAINT governance_audit_log_event_type_check
ON learning.governance_audit_log IS
'event_type allowlist (V054 21-value canonical): 5 V035 base + 1 V044 + '
'8 V053 + 7 V054 lease lifecycle (lease_acquire_request/success/fail + '
'lease_release_consumed/failed/cancelled + lease_sm_transition). / '
'event_type allowlist (V054 21 值 canonical)：5 V035 base + 1 V044 + '
'8 V053 + 7 V054 lease lifecycle 新增。';

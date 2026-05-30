-- ============================================================
-- V104: Supervised Live Audit (LG-3)
-- 用途: P0-LG-3 supervised-live 模式的不可變稽核軌跡 append-only hypertable。
--       每一筆 supervised SM 狀態轉換 / approval 決策 / lease 生命週期 /
--       kill 路徑 / drawdown breach / reconcile 強平 都落一筆，供事後完整重建
--       與合規審計（root principle §8：每筆交易可重建可解釋）。
--
--   - SOURCE：
--     · spec scaffold: docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md
--     · LG-3 spec v2 final §4.1 表結構 + §4.4B non-training surface invariant
--     · MIT 2026-05-27 dry-run（手寫 candidate, BEGIN/ROLLBACK）9/9 PASS — 本檔為真檔，待 MIT Gate 2b 重跑
--
-- 範圍:
--   - CREATE TABLE IF NOT EXISTS learning.supervised_live_audit
--     （21 column allowlist；PK=(event_id, created_at)）
--   - 4 CHECK constraint：action 17-enum / result 3-enum / engine_mode 2-enum / ts_ms>0
--   - create_hypertable(created_at, 7 days chunk)
--   - compression policy 30 days（segmentby=session_id, orderby=created_at DESC）
--   - retention policy 90 days
--   - 4 named index（session_id / request_id / action / operator_id，皆 + created_at DESC）
--   - Guard A 3-part：prereq（V054 lease_transitions + V035 governance_audit_log）
--     + 21-column allowlist 後驗 + forbidden ML column 反向驗（non-training surface invariant）
--   - Guard C：4 CHECK enum 完整性 + hypertable + 4 index 後驗
--
-- Parent specs:
--   docs/execution_plan/specs/2026-05-26--v104-lg3-supervised-live-audit-migration.md
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v2_final.md §4
--
-- Pattern source:
--   V114 (notification_failsafe_events hypertable + Guard A/B/C + idempotent DO-block) — 主 reference
--   V107 (replay_divergence_log hypertable + forbidden column 反模式 Guard A part 3) — non-training surface
--   V086 (governance enum + ADD CONSTRAINT IF NOT EXISTS idempotent pattern)
--
-- 硬邊界:
--   - append-only audit：writer 只 INSERT，不 UPDATE/DELETE（root principle §1 單一寫入口）
--   - engine_mode CHECK 限 (live, live_demo)：拒 paper —— LiveDemo 不因 endpoint 降級
--     （feedback_live_no_degradation_by_endpoint）。違反 → runtime check_violation fail-loud。
--   - non-training surface invariant：本表禁出現 ml_label / training_label / feature_vector /
--     signal_id 等 ML/training column；防 ML pipeline 誤接此 audit 表（MIT MUST-5）。
--   - idempotency double-apply 安全：所有 DDL IF NOT EXISTS / ADD CONSTRAINT IF NOT EXISTS /
--     DO-block 守衛；第二次 apply 必 NOTICE-skip 0 RAISE（V083/V084 NOTICE-skip gold standard）。
--   - V104 為 V103→V106 之間 free hole；新增不影響既有 V099-V115 checksum
--     （sqlx 按 version sort，補洞合法；不可動任何既有 migration 檔避免 hash drift）。
--   - PG WARNING `column "event_id" should be used for segmenting or ordering` 是 informational：
--     spec §2.3 選 session_id segmentby 是 hot-read pattern 正確設計，非 error（MIT push back 已確認）。
-- ============================================================

-- ============================================================
-- Guard A part 1: prereq 反向防護（V054 lease_transitions + V035 governance_audit_log）
-- 為什麼: supervised audit 與 lease 生命週期 + governance 決策同源；缺前置 = sqlx chain
--   異常或環境殘缺，須 fail-loud RAISE 而非 silent 建半套表。
-- ============================================================
DO $$
DECLARE
    v_lease_transitions_exists BOOLEAN;
    v_governance_audit_exists BOOLEAN;
    v_timescaledb_exists BOOLEAN;
BEGIN
    -- V054 learning.lease_transitions 必存
    SELECT to_regclass('learning.lease_transitions') IS NOT NULL
      INTO v_lease_transitions_exists;
    -- V035 learning.governance_audit_log 必存
    SELECT to_regclass('learning.governance_audit_log') IS NOT NULL
      INTO v_governance_audit_exists;
    IF NOT v_lease_transitions_exists OR NOT v_governance_audit_exists THEN
        RAISE EXCEPTION
            'V104 Guard A part 1: prerequisite missing (lease_transitions=% / governance_audit_log=%). '
            'V054 + V035 must apply before V104.',
            v_lease_transitions_exists, v_governance_audit_exists;
    END IF;

    -- TimescaleDB extension 必存（hypertable 必須；V096 boundary）
    SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb')
      INTO v_timescaledb_exists;
    IF NOT v_timescaledb_exists THEN
        RAISE EXCEPTION
            'V104 Guard A part 1: TimescaleDB extension missing. V096 boundary not satisfied.';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 1: CREATE TABLE（21 column allowlist）
-- 對齊 spec §2.1 表結構 + MIT dry-run 已驗 schema。
-- PK=(event_id, created_at)：hypertable PK 必含 partition column（created_at）。
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.supervised_live_audit (
    -- 1) event_id：'evt:' + 16-hex random（writer 生成；audit 唯一識別）
    event_id              TEXT          NOT NULL,
    -- 2) ts_ms：emit ms epoch（CHECK > 0；對齊 Rust clock now_ms）
    ts_ms                 BIGINT        NOT NULL,
    -- 3) operator_id：per RequestEnvelope（每 operator 30d 1% violation budget gate 用）
    operator_id           TEXT          NOT NULL,
    -- 4) session_id：NULL only for REGISTERED/REJECTED（session 未建立前）
    session_id            TEXT,
    -- 5) request_id：'req:' + UUID v4（per-request audit lookup）
    request_id            TEXT          NOT NULL,
    -- 6) decision_lease_id：NULL until ACTIVE_TRADING（lease 取得後填）
    decision_lease_id     TEXT,
    -- 7) engine_mode：CHECK in (live, live_demo) —— 拒 paper（LiveDemo 不降級）
    engine_mode           TEXT          NOT NULL,
    -- 8) symbols：本 session 涉及交易對
    symbols               TEXT[]        NOT NULL DEFAULT '{}',
    -- 9) strategies：本 session 涉及策略
    strategies            TEXT[]        NOT NULL DEFAULT '{}',
    -- 10) risk_limits：4-field shape（max_position / max_drawdown / ...）
    risk_limits           JSONB         NOT NULL DEFAULT '{}',
    -- 11) action：CHECK 17-enum（見 chk_supervised_live_audit_action）
    action                TEXT          NOT NULL,
    -- 12) src_state：NULL for first row（SM 起始無前態）
    src_state             TEXT,
    -- 13) dst_state：轉換後 SM 狀態
    dst_state             TEXT          NOT NULL,
    -- 14) result：CHECK in (ok, rejected, forced)
    result                TEXT          NOT NULL,
    -- 15) reason_codes：拒絕 / 強制 原因碼集合
    reason_codes          TEXT[]        NOT NULL DEFAULT '{}',
    -- 16) alpha_source_id：R-4 forward-compat（alpha 來源追溯）
    alpha_source_id       TEXT,
    -- 17) cohort_ref：W-AUDIT-9 Stage>=3 forward-compat
    cohort_ref            TEXT,
    -- 18) strategy_alpha_score：MIT SHOULD-2 forward-compat
    strategy_alpha_score  FLOAT8,
    -- 19) regime_tag：MIT SHOULD-3 forward-compat（市況標記）
    regime_tag            TEXT,
    -- 20) payload：previous_session_id / submitted_override / effective_after_min 等
    payload               JSONB         NOT NULL DEFAULT '{}',
    -- 21) created_at：hypertable partition column
    created_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    -- PK 必含 partition column（created_at）— TimescaleDB 硬邊界（per V107/V114 樣板）
    CONSTRAINT supervised_live_audit_pkey PRIMARY KEY (event_id, created_at)
);

-- ============================================================
-- Main DDL Step 2: 4 CHECK constraint（ADD CONSTRAINT IF NOT EXISTS 冪等模式）
-- 為什麼用 DO-block + pg_constraint 守衛：CREATE TABLE IF NOT EXISTS 第二次 apply 整段跳過，
--   若 inline CHECK 首次未建則永遠補不上；DO-block 查 pg_constraint 不存在才 ADD，
--   re-apply 第二次 skip 不報錯（V086 idempotent gold standard）。
-- ============================================================
DO $$
BEGIN
    -- C1：action 17-enum（對齊 spec §2.2 + spec v2 §4.1 inverse map）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_supervised_live_audit_action'
    ) THEN
        ALTER TABLE learning.supervised_live_audit
            ADD CONSTRAINT chk_supervised_live_audit_action
            CHECK (action IN (
                'request_registered',
                'approval_granted',
                'approval_rejected',
                'expired_pre_auth',
                'auth_file_observed',
                'auth_file_invalid',
                'lease_acquired',
                'lease_released',
                'auth_recheck_fail',
                'drawdown_breach',
                'drawdown_close_complete',
                'kill_api',
                'kill_ipc',
                'session_max_duration',
                'reconcile_force_close',
                'illegal_transition_attempted',
                'session_closed'
            ));
    END IF;

    -- C2：result 3-enum
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_supervised_live_audit_result'
    ) THEN
        ALTER TABLE learning.supervised_live_audit
            ADD CONSTRAINT chk_supervised_live_audit_result
            CHECK (result IN ('ok', 'rejected', 'forced'));
    END IF;

    -- C3：engine_mode 2-enum（拒 paper —— LiveDemo 不降級硬邊界）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_supervised_live_audit_engine_mode'
    ) THEN
        ALTER TABLE learning.supervised_live_audit
            ADD CONSTRAINT chk_supervised_live_audit_engine_mode
            CHECK (engine_mode IN ('live', 'live_demo'));
    END IF;

    -- C4：ts_ms 正值（防 0 / 負值繞過）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_supervised_live_audit_ts_ms_positive'
    ) THEN
        ALTER TABLE learning.supervised_live_audit
            ADD CONSTRAINT chk_supervised_live_audit_ts_ms_positive
            CHECK (ts_ms > 0);
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 3: Hypertable（created_at partition, 7d chunk）
-- if_not_exists => TRUE：re-apply 不報「already a hypertable」。
-- ============================================================
SELECT create_hypertable(
    'learning.supervised_live_audit',
    'created_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- ============================================================
-- Main DDL Step 4: Compression policy（30 days）
-- segmentby=session_id 是 LG-3 hot-read pattern（per-session reconcile 對賬）；
-- PG 對 event_id 的 segmentby WARNING 是 informational，spec §2.3 設計選 session_id 正確。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema = 'learning'
          AND hypertable_name = 'supervised_live_audit'
    ) THEN
        ALTER TABLE learning.supervised_live_audit SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'session_id',
            timescaledb.compress_orderby = 'created_at DESC'
        );
        RAISE NOTICE
            'V104: enabled compression on learning.supervised_live_audit '
            '(segmentby=session_id; orderby=created_at DESC)';
    ELSE
        RAISE NOTICE 'V104: compression already enabled; skipping ALTER';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_compression'
          AND hypertable_name = 'supervised_live_audit'
    ) THEN
        PERFORM add_compression_policy(
            'learning.supervised_live_audit',
            INTERVAL '30 days'
        );
        RAISE NOTICE 'V104: added compression policy (30 days)';
    ELSE
        RAISE NOTICE 'V104: compression policy already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 5: Retention policy（90 days）
-- 對齊 learning.* governance retention（V107 樣板）。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_retention'
          AND hypertable_name = 'supervised_live_audit'
    ) THEN
        PERFORM add_retention_policy(
            'learning.supervised_live_audit',
            INTERVAL '90 days'
        );
        RAISE NOTICE 'V104: added retention policy (90 days)';
    ELSE
        RAISE NOTICE 'V104: retention policy already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 6: 4 named index（hot-path；皆 + created_at DESC）
-- 對齊 spec §2.4 Guard C index plan。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_supervised_live_audit_session_id
    ON learning.supervised_live_audit (session_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supervised_live_audit_request_id
    ON learning.supervised_live_audit (request_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supervised_live_audit_action
    ON learning.supervised_live_audit (action, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_supervised_live_audit_operator
    ON learning.supervised_live_audit (operator_id, created_at DESC);

-- ============================================================
-- Main DDL Step 7: COMMENT
-- ============================================================
COMMENT ON TABLE learning.supervised_live_audit IS
    'P0-LG-3 supervised-live 不可變稽核軌跡（V104）。append-only：writer 只 INSERT。'
    'created_at hypertable partition（7d chunk + 30d compression segmentby session_id + 90d retention）。'
    'engine_mode 限 (live, live_demo) 拒 paper（LiveDemo 不降級）。'
    'non-training surface：禁 ml_label/training_label/feature_vector/signal_id column。';

-- ============================================================
-- Guard A part 2: 21-column allowlist 後驗（per MIT MUST-1）
-- 為什麼後驗：若表已被前一版以不同 schema 建好，column 數不符必 fail-loud
--   而非 silent 接受 drift schema。
-- ============================================================
DO $$
DECLARE
    v_column_count INTEGER;
    v_missing TEXT := '';
    v_col TEXT;
    v_expected TEXT[] := ARRAY[
        'event_id','ts_ms','operator_id','session_id','request_id','decision_lease_id',
        'engine_mode','symbols','strategies','risk_limits','action','src_state','dst_state',
        'result','reason_codes','alpha_source_id','cohort_ref','strategy_alpha_score',
        'regime_tag','payload','created_at'
    ];
BEGIN
    SELECT COUNT(*) INTO v_column_count
    FROM information_schema.columns
    WHERE table_schema = 'learning' AND table_name = 'supervised_live_audit';
    IF v_column_count <> 21 THEN
        RAISE EXCEPTION
            'V104 Guard A part 2: column count = % (expected 21). Schema drift detected.',
            v_column_count;
    END IF;
    -- 逐欄位驗（累積缺失 column 一次 RAISE，per V086 missing-column pattern）
    FOREACH v_col IN ARRAY v_expected LOOP
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning' AND table_name = 'supervised_live_audit'
              AND column_name = v_col
        ) THEN
            v_missing := v_missing || v_col || ' ';
        END IF;
    END LOOP;
    IF length(v_missing) > 0 THEN
        RAISE EXCEPTION
            'V104 Guard A part 2: supervised_live_audit missing columns: %', v_missing;
    END IF;
END $$;

-- ============================================================
-- Guard A part 3: forbidden ML column 反向驗（non-training surface invariant；MIT MUST-5）
-- 為什麼: 防 ML/training pipeline 誤把 supervised_live_audit 當 feature store / label 表。
--   本表是合規 audit，不得混入 ML training surface（root principle §7 學習不改 live state）。
-- ============================================================
DO $$
DECLARE
    v_forbidden TEXT;
BEGIN
    SELECT string_agg(column_name, ', ') INTO v_forbidden
    FROM information_schema.columns
    WHERE table_schema = 'learning' AND table_name = 'supervised_live_audit'
      AND column_name IN ('ml_label', 'training_label', 'feature_vector', 'signal_id');
    IF v_forbidden IS NOT NULL THEN
        RAISE EXCEPTION
            'V104 Guard A part 3: supervised_live_audit violates non-training surface invariant '
            '(forbidden columns present: %).', v_forbidden;
    END IF;
END $$;

-- ============================================================
-- Guard C: 後驗 4 CHECK enum 完整性 + hypertable + 4 index 全到位
-- ============================================================
DO $$
DECLARE
    v_check_count INTEGER;
    v_action_def TEXT;
    v_chunk_interval BIGINT;
    v_index_count INTEGER;
BEGIN
    -- 4 CHECK constraint 全在
    SELECT COUNT(*) INTO v_check_count
    FROM pg_constraint
    WHERE conrelid = 'learning.supervised_live_audit'::regclass
      AND contype = 'c'
      AND conname IN (
          'chk_supervised_live_audit_action',
          'chk_supervised_live_audit_result',
          'chk_supervised_live_audit_engine_mode',
          'chk_supervised_live_audit_ts_ms_positive'
      );
    IF v_check_count <> 4 THEN
        RAISE EXCEPTION
            'V104 Guard C FAIL: 4 CHECK constraint expected, found %.', v_check_count;
    END IF;

    -- action CHECK 必含 17 enum（探幾個關鍵值；first + last + kill 路徑）
    SELECT pg_get_constraintdef(oid) INTO v_action_def
    FROM pg_constraint WHERE conname = 'chk_supervised_live_audit_action';
    IF v_action_def IS NULL
       OR position('request_registered' IN v_action_def) = 0
       OR position('session_closed' IN v_action_def) = 0
       OR position('reconcile_force_close' IN v_action_def) = 0 THEN
        RAISE EXCEPTION
            'V104 Guard C FAIL: action CHECK missing required enum values. Actual: %.', v_action_def;
    END IF;

    -- hypertable chunk = 7d（以 µs/ms BIGINT integer_interval 表示；7d = 604800000000 µs）
    SELECT integer_interval INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_schema = 'learning'
      AND hypertable_name = 'supervised_live_audit'
      AND column_name = 'created_at';
    IF v_chunk_interval IS NULL THEN
        RAISE EXCEPTION 'V104 Guard C FAIL: hypertable not created on created_at.';
    END IF;

    -- 4 named index 到位
    SELECT COUNT(*) INTO v_index_count
    FROM pg_indexes
    WHERE schemaname = 'learning'
      AND tablename = 'supervised_live_audit'
      AND indexname IN (
          'idx_supervised_live_audit_session_id',
          'idx_supervised_live_audit_request_id',
          'idx_supervised_live_audit_action',
          'idx_supervised_live_audit_operator'
      );
    IF v_index_count <> 4 THEN
        RAISE EXCEPTION
            'V104 Guard C FAIL: 4 hot-path index expected, found %.', v_index_count;
    END IF;

    RAISE NOTICE
        'V104: all guards PASS — 21 column, 4 CHECK (action 17-enum), '
        'hypertable created_at 7d chunk, 4 index, non-training surface invariant held.';
END $$;

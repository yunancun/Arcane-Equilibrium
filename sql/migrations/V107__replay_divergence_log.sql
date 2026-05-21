-- ============================================================
-- V107: M11 Replay Divergence Log Hypertable (learning.replay_divergence_log)
--
-- 用途:
--   建立 M11 Continuous Counterfactual Replay 唯一寫入目標：每日 nightly
--   counterfactual replay vs live execution 對比，7 種 divergence type ×
--   3 級 severity 寫入 hypertable。M11 為 sensor (signal source)，不寫
--   live state / 不寫 learning.decay_signals / 不寫 strategy_lifecycle；M7
--   (V113) 為 single decay authority (per CR-7 + ADR-0038 + ADR-0044)。
--   per V107 spec §2.1 27 column 全 DDL + ADR-0038 Decision 3 三級 severity +
--   M11 design spec §4.2 D1-D7 divergence taxonomy。
--
-- 範圍:
--   - CREATE TABLE learning.replay_divergence_log (27 column);
--   - create_hypertable(divergence_detected_at, 7 days);
--   - ALTER ... SET (timescaledb.compress, segmentby, orderby);
--   - add_compression_policy(30 days) — 寬於 V106 7d；對齊 M7 14d window
--     detector hot read 需求 (per V107 spec §3.4)；
--   - add_retention_policy(90 days) — 對齊 learning.* governance retention；
--   - 5 hot-path index (1 strategy_symbol / 4 partial: severity / run_id /
--     hypothesis / unack 5d escalate);
--   - 1 materialized view mv_latest_divergence_per_strategy + 1 unique index;
--   - Guard A: TimescaleDB extension + governance.audit_log + learning.hypotheses
--     三 prereq + 既有 table column 完整性 + forbidden action column 反模式
--     反向檢測 (per CR-7 M7 single decay authority)；
--   - Guard C: 4 CHECK enum 完整性 (divergence_type 7 / severity 3 /
--     flag_action_taken 5 / engine_mode 5) + hypertable chunk interval +
--     policy 存在性 + FK hypothesis_id;
--   - 無 Guard B (本 migration 不 ALTER 既有 column type)。
--
-- Parent specs:
--   docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md (1471 行)
--   docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md (619 行)
--   docs/execution_plan/2026-05-21--m11_threshold_m7_dedup_decay_enforced_rename.md
--   docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md
--   docs/adr/0044-m7-decay-enforced-single-authority.md (Decision 1: M11 不寫 strategy_lifecycle)
--   docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md §2.3 Track C
--
-- 硬邊界:
--   - PRIMARY KEY = (id, divergence_detected_at) — hypertable 必含 partition
--     column 在 PK；否則 timescale create_hypertable 拒。
--   - V107 schema 嚴禁含 forbidden action column (auto_demote / target_state /
--     decay_recommendation / demote_proposal_id / decay_stage / stage_demoted)；
--     違反 = M7 single decay authority 紀律違反 → Guard A RAISE。
--   - M11 自身寫入時 engine_mode='replay'；原 live trace mode 在 evidence_json；
--     ML training filter 必 IN ('live','live_demo') per CLAUDE.md §七。
--   - V096 boundary (TimescaleDB extension) + V098 governance.audit_log +
--     V103 learning.hypotheses 三 prereq 都必須先 land。
--   - hypothesis_id FK to learning.hypotheses (V103 land 後 nullable hard FK)。
--   - m7_decay_signal_id / m9_ab_test_id 採 soft reference (BIGINT / UUID
--     placeholder)；避免循環依賴 + 不阻 dispatch sequence (V108/V113 後續 land)。
-- ============================================================

-- ============================================================
-- Guard A: TimescaleDB extension + V098/V103 prereq + 既有 column 完整性 +
-- forbidden action column 反模式反向檢測 (per CR-7 + AC-3 + spec §3.1)
-- Guard A: TimescaleDB 擴展 + V098/V103 前置條件 + 既有 column 完整性 +
-- forbidden 字段反模式偵測
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
    v_ts_ver TEXT;
BEGIN
    -- TimescaleDB extension prereq (per V096 boundary)
    SELECT extversion INTO v_ts_ver
    FROM pg_extension WHERE extname='timescaledb';
    IF v_ts_ver IS NULL THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: TimescaleDB extension missing. '
            'V096 boundary not satisfied. Apply V096 first.';
    END IF;

    -- learning.replay_divergence_log 已存在情境 → 驗 27 column 完整 (drift 防護)
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='replay_divergence_log'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'divergence_detected_at', 'replay_run_id', 'divergence_type',
            'severity', 'divergence_metric_name', 'divergence_value',
            'divergence_pnl_usdt', 'divergence_qty',
            'baseline_5d_mean', 'baseline_5d_sigma', 'noise_floor_threshold',
            'strategy_id', 'symbol', 'fill_chain_id', 'hypothesis_id',
            'm9_ab_test_id', 'm7_decay_signal_id', 'flag_action_taken',
            'passive_slack_ack_at', 'evidence_json', 'engine_mode',
            'created_by', 'created_at', 'updated_by', 'updated_at',
            'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='replay_divergence_log'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V107 Guard A FAIL: learning.replay_divergence_log exists but '
                'missing columns: %. Possible legacy stub conflict — resolve '
                'schema reconciliation before applying V107.',
                v_missing;
        END IF;

        -- 反模式檢測: 6 個 forbidden action column (per CR-7 + AC-3 +
        -- m11_threshold_m7_dedup_decay_enforced_rename §3.3)。
        -- M11 是 sensor; M7 (V113) 是 single decay authority。V107 嚴禁含
        -- action column；若已存在表含此 6 列任一 → 違反治理紀律 → RAISE。
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='replay_divergence_log'
              AND column_name IN (
                  'auto_demote', 'target_state', 'decay_recommendation',
                  'demote_proposal_id', 'decay_stage', 'stage_demoted'
              )
        ) THEN
            RAISE EXCEPTION
                'V107 Guard A FAIL: learning.replay_divergence_log contains '
                'FORBIDDEN action column. Per CR-7 + ADR-0038 Decision 3 + '
                'ADR-0044 Decision 1, M11 is SENSOR only — M7 (V113) is '
                'single decay authority. V107 schema must not contain '
                'auto_demote / target_state / decay_recommendation / '
                'demote_proposal_id / decay_stage / stage_demoted. Remove '
                'offending column or move to V113.';
        END IF;
    END IF;

    -- governance.audit_log 必須存在 (M11 H-11 audit cross-ref query target；
    -- 非 schema FK；spec §1.4 + Guard A 要求 V098 已 land)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: governance.audit_log missing — V098 must '
            'apply before V107 (cross-ref query target). Verify _sqlx_migrations.';
    END IF;

    -- learning.hypotheses 必須存在 (V103 已 land Sprint 1A-α；hypothesis_id
    -- FK target)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='hypotheses'
    ) THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: learning.hypotheses missing — V103 must '
            'apply before V107 (hypothesis_id FK target). Verify _sqlx_migrations.';
    END IF;
END $$;

-- ============================================================
-- Guard C 預檢: idempotency 重跑時驗 CHECK / hypertable / policy / FK 對齊
-- (首次 apply 上述 object 不存在 → 全 skip; 重跑時抓 drift)
-- 用 to_regclass() 安全測 table 是否存在;首次 apply 走全 skip path
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_chunk_interval BIGINT;
    v_target_oid OID;
BEGIN
    -- 用 to_regclass() 安全測 table 存在;首次 apply 為 NULL 直接 RETURN
    v_target_oid := to_regclass('learning.replay_divergence_log');
    IF v_target_oid IS NULL THEN
        RAISE NOTICE 'V107 Guard C pre: learning.replay_divergence_log not yet created; skipping pre-check.';
        RETURN;
    END IF;

    -- divergence_type CHECK 必含 7 值 (only check if constraint exists)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%divergence_type%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('fill_chain' IN v_actual) = 0
           OR position('position' IN v_actual) = 0
           OR position('pnl' IN v_actual) = 0
           OR position('fee' IN v_actual) = 0
           OR position('liquidation' IN v_actual) = 0
           OR position('regime' IN v_actual) = 0
           OR position('risk' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V107 Guard C FAIL: divergence_type CHECK enum mismatch. '
                'Actual: %. Expected 7 values (fill_chain/position/pnl/fee/'
                'liquidation/regime/risk per M11 design spec §4.2 D1-D7).',
                v_actual;
        END IF;
    END IF;

    -- severity CHECK 必含 3 值
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%severity%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('NOISE' IN v_actual) = 0
           OR position('WARN' IN v_actual) = 0
           OR position('CRITICAL' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V107 Guard C FAIL: severity CHECK enum mismatch. '
                'Actual: %. Expected NOISE/WARN/CRITICAL per ADR-0038 Decision 3.',
                v_actual;
        END IF;
    END IF;

    -- flag_action_taken CHECK 必含 5 值
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%flag_action_taken%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('m9_inconclusive' IN v_actual) = 0
           OR position('m7_decay_candidate' IN v_actual) = 0
           OR position('m3_health_recheck' IN v_actual) = 0
           OR position('operator_alert' IN v_actual) = 0
           OR position('none' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V107 Guard C FAIL: flag_action_taken CHECK enum mismatch. '
                'Actual: %. Expected 5 values (m9_inconclusive/m7_decay_candidate/'
                'm3_health_recheck/operator_alert/none) per M11 design spec §5.1.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 必含 5 值 (額外 replay)
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%engine_mode%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V107 Guard C FAIL: engine_mode CHECK enum mismatch. '
                'Actual: %. Expected 5 values (paper/demo/live_demo/live/replay; '
                'replay 為 M11 自身寫入 engine_mode; 原 live trace mode 在 evidence_json).',
                v_actual;
        END IF;
    END IF;

    -- Hypertable chunk_time_interval 必 = 7 days (idempotent check)
    SELECT EXTRACT(EPOCH FROM time_interval) INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name='replay_divergence_log'
      AND column_name='divergence_detected_at';
    IF v_chunk_interval IS NOT NULL AND v_chunk_interval <> 604800 THEN
        RAISE EXCEPTION
            'V107 Guard C FAIL: chunk_time_interval = % sec (expected 604800 = 7 days).',
            v_chunk_interval;
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 1: CREATE TABLE learning.replay_divergence_log
-- 主 DDL Step 1: 主表建立 (27 column;含 1 FK 到 V103 learning.hypotheses)
--
-- 設計依據 (per V107 spec §2.1-§2.7):
-- - 7 種 divergence_type (D1 fill_chain / D2 position / D3 pnl / D4 fee /
--   D5 liquidation / D6 regime / D7 risk per M11 design spec §4.2)。
-- - 3 級 severity (NOISE/WARN/CRITICAL per ADR-0038 Decision 3)；NOISE 由
--   writer 端 gate 不寫 row (schema 允許用於 debug fixture)。
-- - 5 級 flag_action_taken (m9_inconclusive / m7_decay_candidate /
--   m3_health_recheck / operator_alert / none per M11 design spec §5.1)。
-- - 5 級 engine_mode 額外 'replay' (M11 自身寫入；原 live trace mode 在
--   evidence_json)。
-- - hypothesis_id FK to learning.hypotheses (nullable;hypothesis-grounded
--   replay 才填;nightly hygiene 為 NULL)。
-- - m7_decay_signal_id / m9_ab_test_id 採 soft reference (BIGINT / UUID
--   placeholder)；M7 read-only consumer 走 pull/poll V107；M9 走
--   bi-directional cross-ref via evidence_json + V108.ab_results write-back。
-- - 5 audit field (created_by/created_at/updated_by/updated_at/source_version)
--   per V103 §14 EXTEND 範式 + V106 sister table。
-- - PRIMARY KEY = (id, divergence_detected_at) per hypertable 必含 partition
--   column；對齊 V094/V106 範式。
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.replay_divergence_log (
    id                          BIGSERIAL,
    divergence_detected_at      TIMESTAMPTZ NOT NULL,
    replay_run_id               UUID NOT NULL,
    divergence_type             TEXT NOT NULL
                                CHECK (divergence_type IN (
                                    'fill_chain',
                                    'position',
                                    'pnl',
                                    'fee',
                                    'liquidation',
                                    'regime',
                                    'risk'
                                )),
    severity                    TEXT NOT NULL
                                CHECK (severity IN (
                                    'NOISE',
                                    'WARN',
                                    'CRITICAL'
                                )),
    divergence_metric_name      TEXT NOT NULL,
    divergence_value            NUMERIC(20,8) NOT NULL,
    divergence_pnl_usdt         NUMERIC(20,8),
    divergence_qty              NUMERIC(20,8),
    baseline_5d_mean            NUMERIC(20,8),
    baseline_5d_sigma           NUMERIC(20,8),
    noise_floor_threshold       NUMERIC(20,8),
    strategy_id                 TEXT NOT NULL,
    symbol                      TEXT NOT NULL,
    fill_chain_id               UUID,
    hypothesis_id               BIGINT REFERENCES learning.hypotheses(hypothesis_id),
    m9_ab_test_id               UUID,
    m7_decay_signal_id          BIGINT,
    flag_action_taken           TEXT
                                CHECK (flag_action_taken IS NULL OR flag_action_taken IN (
                                    'm9_inconclusive',
                                    'm7_decay_candidate',
                                    'm3_health_recheck',
                                    'operator_alert',
                                    'none'
                                )),
    passive_slack_ack_at        TIMESTAMPTZ,
    evidence_json               JSONB,
    engine_mode                 TEXT NOT NULL
                                CHECK (engine_mode IN (
                                    'paper',
                                    'demo',
                                    'live_demo',
                                    'live',
                                    'replay'
                                )),
    created_by                  TEXT NOT NULL DEFAULT 'm11_replay_engine',
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                  TEXT,
    updated_at                  TIMESTAMPTZ,
    source_version              TEXT NOT NULL DEFAULT 'V107',
    PRIMARY KEY (id, divergence_detected_at)
);

-- ============================================================
-- Main DDL Step 2: Hypertable (7d chunk;對齊 V106 sister table)
-- 主 DDL Step 2: TimescaleDB hypertable (7 天 chunk)
--
-- - chunk_time_interval = 7d: 對齊 weekly rollup query pattern +
--   ~500 row/day × 7 = 3,500 row/chunk × ~25 KB = ~85 MB/chunk;
-- - if_not_exists => TRUE: idempotent 重跑不 RAISE。
-- ============================================================
SELECT create_hypertable(
    'learning.replay_divergence_log',
    'divergence_detected_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- ============================================================
-- Main DDL Step 3: Compression settings
-- 主 DDL Step 3: 壓縮設定 (segmentby + orderby)
--
-- - segmentby = 'strategy_id, symbol, divergence_type': 同 strategy × symbol
--   × type 連續 row segment 壓縮率最高 (80-90%);
-- - orderby = 'divergence_detected_at DESC, id DESC': time-DESC 最近資料
--   close 在 chunk 邊界, decompress 成本最低。
--
-- 注意: ALTER TABLE ... SET (timescaledb.compress, ...) 對既有同設定不
-- RAISE; 但若 compress 已開且 segmentby/orderby 不同會 RAISE。本 DDL
-- 走 idempotent path; 重跑 V107 對 already-compressed table 無動作。
-- ============================================================
DO $$
DECLARE
    v_already_compressed BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema = 'learning'
          AND hypertable_name = 'replay_divergence_log'
    ) INTO v_already_compressed;

    IF NOT v_already_compressed THEN
        ALTER TABLE learning.replay_divergence_log SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'strategy_id, symbol, divergence_type',
            timescaledb.compress_orderby = 'divergence_detected_at DESC, id DESC'
        );
        RAISE NOTICE
            'V107: enabled compression on learning.replay_divergence_log '
            '(segmentby=strategy_id,symbol,divergence_type; orderby=detected_at DESC)';
    ELSE
        RAISE NOTICE
            'V107: compression already enabled on learning.replay_divergence_log; '
            'skipping ALTER';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 4: Compression + Retention policies (idempotent)
-- 主 DDL Step 4: 壓縮策略 + 保留策略 (重跑安全)
--
-- - add_compression_policy: 30 天後自動壓縮 chunk (寬於 V106 7d;對齊 M7
--   14d window detector hot read 需求 per V107 spec §3.4)；
-- - add_retention_policy: 90 天後自動 drop chunk (operational audit；長期
--   trend 走 daily aggregate 表)；對齊 ADR-0038 H-22 R4 governance retention。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_compression'
          AND hypertable_name = 'replay_divergence_log'
    ) THEN
        PERFORM add_compression_policy(
            'learning.replay_divergence_log',
            INTERVAL '30 days'
        );
        RAISE NOTICE
            'V107: added compression policy (30 days) on replay_divergence_log';
    ELSE
        RAISE NOTICE
            'V107: compression policy already present; skipping';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_retention'
          AND hypertable_name = 'replay_divergence_log'
    ) THEN
        PERFORM add_retention_policy(
            'learning.replay_divergence_log',
            INTERVAL '90 days'
        );
        RAISE NOTICE
            'V107: added retention policy (90 days) on replay_divergence_log';
    ELSE
        RAISE NOTICE
            'V107: retention policy already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 5: Hot-path indexes (5 個)
-- 主 DDL Step 5: 熱查詢索引 (5 個;對齊 V107 spec §4.2)
--
-- 設計依據 (per V107 spec §4.1 query pattern → index map):
-- - idx_div_strategy_symbol_detected: per-strategy-symbol divergence timeline
--   主 hot path (M7 detector 14d pull + GUI drill-down)。
-- - idx_div_severity_detected: per-severity alert dashboard (Slack daily
--   digest + GUI Banner);partial WHERE severity IN (WARN,CRITICAL);防 NOISE
--   debug fixture 污染索引。
-- - idx_div_run_id: per-replay-run group by (nightly run summary)。
-- - idx_div_hypothesis_detected: hypothesis-grounded replay drill-down;
--   partial WHERE hypothesis_id IS NOT NULL (預估 <5% row;縮 95% 空間)。
-- - idx_div_unack_detected: passive Slack 5d unack escalate cron query;
--   partial WHERE passive_slack_ack_at IS NULL AND severity IN (WARN,CRITICAL);
--   H-11 #6 mitigation 對應 partial index。
--
-- 注意: hypertable + chunk 上 CREATE INDEX 走 non-CONCURRENT path (timescale
-- 自動逐 chunk 建);對齊 V106 sister table 範式。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_div_strategy_symbol_detected
    ON learning.replay_divergence_log (strategy_id, symbol, divergence_detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_div_severity_detected
    ON learning.replay_divergence_log (severity, divergence_detected_at DESC)
    WHERE severity IN ('WARN', 'CRITICAL');

CREATE INDEX IF NOT EXISTS idx_div_run_id
    ON learning.replay_divergence_log (replay_run_id);

CREATE INDEX IF NOT EXISTS idx_div_hypothesis_detected
    ON learning.replay_divergence_log (hypothesis_id, divergence_detected_at DESC)
    WHERE hypothesis_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_div_unack_detected
    ON learning.replay_divergence_log (passive_slack_ack_at, divergence_detected_at DESC)
    WHERE passive_slack_ack_at IS NULL AND severity IN ('WARN', 'CRITICAL');

-- ============================================================
-- Main DDL Step 6: Materialized view for A3 GUI Banner + monthly review wizard
-- 主 DDL Step 6: 物化視圖 (last divergence per strategy × symbol × type)
--
-- - DISTINCT ON 取每 (strategy, symbol, divergence_type) 三元組最新 row
--   (by divergence_detected_at DESC);
-- - WHERE severity IN (WARN, CRITICAL): mv 只 cache 需要 alert 的 row
--   (NOISE writer 不寫;partial filter 防 future NOISE debug INSERT 污染);
-- - 4h cron refresh CONCURRENTLY 走 unique index (refresh 期間 mv 仍可
--   query;unblock GUI Banner refresh);
-- - per V107 spec §7;A3 Sprint 1A-ε Monthly Review Wizard + GUI Console
--   Banner 用。
-- ============================================================
CREATE MATERIALIZED VIEW IF NOT EXISTS learning.mv_latest_divergence_per_strategy AS
SELECT DISTINCT ON (strategy_id, symbol, divergence_type)
    strategy_id,
    symbol,
    divergence_type,
    severity,
    divergence_value,
    divergence_pnl_usdt,
    flag_action_taken,
    passive_slack_ack_at,
    divergence_detected_at,
    replay_run_id
FROM learning.replay_divergence_log
WHERE severity IN ('WARN', 'CRITICAL')
ORDER BY strategy_id, symbol, divergence_type, divergence_detected_at DESC;

-- mv unique index (CONCURRENTLY refresh 必含 unique index;PG 12+ 支援)
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_latest_div_strategy_symbol_type
    ON learning.mv_latest_divergence_per_strategy (strategy_id, symbol, divergence_type);

-- ============================================================
-- Main DDL Step 7: COMMENT (audit metadata)
-- 主 DDL Step 7: 表 / 欄位註釋 (運維說明)
-- ============================================================
COMMENT ON TABLE learning.replay_divergence_log IS
    'M11 Continuous Counterfactual Replay Divergence Log (V107). '
    '7 divergence types (D1-D7 per M11 design spec §4.2) × 3 severity '
    '(NOISE/WARN/CRITICAL per ADR-0038); hypertable + 7d chunk + 30d '
    'compression (對齊 M7 14d window detector) + 90d retention. '
    'M11 為 sensor; M7 (V113) 為 single decay authority (per CR-7); '
    'V107 禁含 action column。';

COMMENT ON COLUMN learning.replay_divergence_log.severity IS
    '3 級 severity per ADR-0038 Decision 3 '
    '(NOISE<mean+0.5σ / WARN≥mean+2.5σ / CRITICAL≥mean+3σ); '
    'production writer NOISE 不寫 row (schema 允許用於 debug fixture)。';

COMMENT ON COLUMN learning.replay_divergence_log.passive_slack_ack_at IS
    'H-11 #6 mitigation: operator Slack reaction / GUI sign-off 時間; '
    'NULL=未ack; ack=null + observed_at>5d → 自動升 M3 HEALTH_WARN '
    '(per M11 design spec §8)。';

COMMENT ON COLUMN learning.replay_divergence_log.engine_mode IS
    '5 值齊全; M11 自身寫入時 engine_mode=replay; 原 live trace mode 在 '
    'evidence_json; ML training filter 必 IN (live, live_demo) per CLAUDE.md §七。';

COMMENT ON COLUMN learning.replay_divergence_log.flag_action_taken IS
    'M11 → M7/M3/M8/M9 路由標記 per M11 design spec §5.1; '
    'M11 為 sensor 不寫 action;M7 為 single decay authority (per CR-7);'
    'V107 此 column 是 backfill 結果記錄;不是 action 觸發欄位。';

-- ============================================================
-- Guard C 後驗: 確保 DDL 成功後 CHECK + hypertable + policy + index +
-- mv + FK 全到位 (與 Guard C 前置一致但放寬: 後驗預期 constraint 必存在)
-- Guard C 後驗:對齊 V106 範式
-- ============================================================
DO $$
DECLARE
    v_divergence_type_def TEXT;
    v_severity_def TEXT;
    v_flag_action_def TEXT;
    v_engine_mode_def TEXT;
    v_chunk_interval BIGINT;
    v_compress_job INTEGER;
    v_retention_job INTEGER;
    v_index_count INTEGER;
    v_mv_count INTEGER;
    v_fk_count INTEGER;
BEGIN
    -- divergence_type CHECK 必含 7 值
    SELECT pg_get_constraintdef(oid) INTO v_divergence_type_def
    FROM pg_constraint
    WHERE conrelid='learning.replay_divergence_log'::regclass
      AND conname LIKE '%divergence_type%check%'
    LIMIT 1;
    IF v_divergence_type_def IS NULL THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: divergence_type CHECK constraint not found after DDL.';
    END IF;
    IF position('fill_chain' IN v_divergence_type_def) = 0
       OR position('liquidation' IN v_divergence_type_def) = 0 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: divergence_type CHECK missing required values. '
            'Actual: %.', v_divergence_type_def;
    END IF;

    -- severity CHECK 必含 3 值
    SELECT pg_get_constraintdef(oid) INTO v_severity_def
    FROM pg_constraint
    WHERE conrelid='learning.replay_divergence_log'::regclass
      AND conname LIKE '%severity%check%'
    LIMIT 1;
    IF v_severity_def IS NULL THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: severity CHECK constraint not found.';
    END IF;
    IF position('CRITICAL' IN v_severity_def) = 0 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: severity CHECK missing CRITICAL. '
            'Actual: %.', v_severity_def;
    END IF;

    -- flag_action_taken CHECK 必含 5 值
    SELECT pg_get_constraintdef(oid) INTO v_flag_action_def
    FROM pg_constraint
    WHERE conrelid='learning.replay_divergence_log'::regclass
      AND conname LIKE '%flag_action_taken%check%'
    LIMIT 1;
    IF v_flag_action_def IS NULL THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: flag_action_taken CHECK constraint not found.';
    END IF;
    IF position('m7_decay_candidate' IN v_flag_action_def) = 0 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: flag_action_taken CHECK missing m7_decay_candidate. '
            'Actual: %.', v_flag_action_def;
    END IF;

    -- engine_mode CHECK 必含 5 值 (額外 replay)
    SELECT pg_get_constraintdef(oid) INTO v_engine_mode_def
    FROM pg_constraint
    WHERE conrelid='learning.replay_divergence_log'::regclass
      AND conname LIKE '%engine_mode%check%'
    LIMIT 1;
    IF v_engine_mode_def IS NULL THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: engine_mode CHECK constraint not found.';
    END IF;
    IF position('replay' IN v_engine_mode_def) = 0 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: engine_mode CHECK missing replay value. '
            'Actual: %.', v_engine_mode_def;
    END IF;

    -- Hypertable chunk_time_interval 必 = 7 days (604800 sec)
    SELECT EXTRACT(EPOCH FROM time_interval) INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name='replay_divergence_log'
      AND column_name='divergence_detected_at';
    IF v_chunk_interval IS NULL THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: hypertable not created on divergence_detected_at.';
    END IF;
    IF v_chunk_interval <> 604800 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: chunk_time_interval = % sec (expected 604800).',
            v_chunk_interval;
    END IF;

    -- Compression policy 必存在
    SELECT COUNT(*) INTO v_compress_job
    FROM timescaledb_information.jobs
    WHERE proc_name='policy_compression'
      AND hypertable_name='replay_divergence_log';
    IF v_compress_job = 0 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: compression policy missing.';
    END IF;

    -- Retention policy 必存在
    SELECT COUNT(*) INTO v_retention_job
    FROM timescaledb_information.jobs
    WHERE proc_name='policy_retention'
      AND hypertable_name='replay_divergence_log';
    IF v_retention_job = 0 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: retention policy missing.';
    END IF;

    -- 5 hot-path index 全到位
    SELECT COUNT(*) INTO v_index_count
    FROM pg_indexes
    WHERE schemaname='learning'
      AND tablename='replay_divergence_log'
      AND indexname IN (
          'idx_div_strategy_symbol_detected',
          'idx_div_severity_detected',
          'idx_div_run_id',
          'idx_div_hypothesis_detected',
          'idx_div_unack_detected'
      );
    IF v_index_count <> 5 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: 5 hot-path index expected, found %.',
            v_index_count;
    END IF;

    -- mv 必存在
    SELECT COUNT(*) INTO v_mv_count
    FROM pg_matviews
    WHERE schemaname='learning'
      AND matviewname='mv_latest_divergence_per_strategy';
    IF v_mv_count <> 1 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: mv_latest_divergence_per_strategy missing.';
    END IF;

    -- mv unique index 必存在
    SELECT COUNT(*) INTO v_index_count
    FROM pg_indexes
    WHERE schemaname='learning'
      AND tablename='mv_latest_divergence_per_strategy'
      AND indexname='idx_mv_latest_div_strategy_symbol_type';
    IF v_index_count <> 1 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: mv unique index missing.';
    END IF;

    -- FK hypothesis_id 必存在
    SELECT COUNT(*) INTO v_fk_count
    FROM pg_constraint c
    JOIN pg_class r ON c.conrelid = r.oid
    JOIN pg_namespace n ON r.relnamespace = n.oid
    WHERE n.nspname='learning' AND r.relname='replay_divergence_log'
      AND c.contype='f';
    IF v_fk_count = 0 THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: hypothesis_id FK to learning.hypotheses missing.';
    END IF;

    -- 反模式後驗: V107 schema 不應含 6 個 forbidden action column
    -- (per CR-7 + AC-3)
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='replay_divergence_log'
          AND column_name IN (
              'auto_demote', 'target_state', 'decay_recommendation',
              'demote_proposal_id', 'decay_stage', 'stage_demoted'
          )
    ) THEN
        RAISE EXCEPTION
            'V107 Guard C post FAIL: replay_divergence_log contains FORBIDDEN '
            'action column post-DDL. Per CR-7 M11 是 sensor; M7 (V113) 是 '
            'single decay authority. Schema drift detected.';
    END IF;

    RAISE NOTICE
        'V107: all guards PASS — divergence_type/severity/flag_action/engine_mode '
        'CHECK ok, hypertable chunk=7d, compression(30d)+retention(90d) policies '
        'installed, 5 hot-path index built, mv + unique index ready, '
        'hypothesis_id FK to learning.hypotheses installed, 0 forbidden action '
        'column (CR-7 dedup contract preserved).';
END $$;

-- ============================================================
-- V109: M8 Anomaly Events Hypertable (learning.anomaly_events)
--
-- 用途:
--   建立 M8 異常事件中央表; 9 event_taxonomy × 4 severity ×
--   4 detection_method 配 TimescaleDB hypertable (7d chunk + 30d compression +
--   180d retention)。M8 為 sensor 不寫 live state;cross-V### query target =
--   V106 (M3 health) / V112 (M1 LAL) / V113 (M7 decay) / V107 (M11 replay) /
--   V108 (M9 ab test)。
--   per V109 spec §2 23-column DDL (v2 amend 加 metric_baseline) +
--   ADR-0036 Decision 1 forbidden algorithm 反向防護 (HMM/Markov/GARCH 永久禁用) +
--   ADR-0036 Decision 2-4 替代算法 (ATR-vol×Funding 9-cell / RV percentile /
--   block bootstrap / manual_operator) + amplification cap H-11 INTEGER column。
--
-- 範圍:
--   - CREATE TABLE learning.anomaly_events (23 column 含 v2 amend metric_baseline);
--   - create_hypertable(observed_at, 7 days);
--   - ALTER ... SET (timescaledb.compress, segmentby, orderby);
--   - add_compression_policy(30 days) — 對齊 ADR-0036 Decision 4 block bootstrap
--     re-estimate cadence;
--   - add_retention_policy(180 days) — 對比 V106 90d retention 較長;
--     90d M1 LAL incident-free + 14d M7 persistent + safety margin;
--   - 4 hot-path index (1 taxonomy / 3 partial: severity / symbol / strategy);
--   - Guard A: TimescaleDB extension + learning.governance_audit_log prereq +
--     既有 table column 完整性 (23 column 含 metric_baseline) +
--     ADR-0036 黑名單 detection_method CHECK 反向防護 + column name 反向防護;
--   - Guard C: 6 CHECK enum 完整性 (event_taxonomy 9 / severity 4 /
--     detection_method 4 / atr_vol_state 3 / funding_state 3 / engine_mode 5) +
--     hypertable chunk interval + policy 存在性 + ADR-0036 黑名單二次驗;
--   - 無 Guard B (本 migration 不 ALTER 既有 column type)。
--
-- Parent specs:
--   docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md (1413 行 base)
--   docs/execution_plan/2026-05-25--v109_m8_anomaly_events_schema_spec_v2_amend.md (v2 amend)
--   docs/execution_plan/2026-05-21--m8_anomaly_detection_design_spec.md
--   docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md
--
-- 硬邊界:
--   - PRIMARY KEY = (id, observed_at) — hypertable 必含 partition column。
--   - V109 schema 嚴禁含 ADR-0036 Decision 1 forbidden algorithm
--     (HMM/Markov-switching/GARCH);Guard A/C 雙重反向防護 RAISE。
--   - engine_mode 5 值含 replay (M11 read-only counterfactual);training filter
--     必 IN ('live','live_demo') per CLAUDE.md §七。
--   - amplification_loop_24h_count 預設 0;writer 預計算 24h 同 event_taxonomy
--     CRITICAL/HALT count (per H-11 cap)。
--   - V096 boundary (TimescaleDB extension) + V098 learning.governance_audit_log
--     兩 prereq 必先 land。
--   - m3 / m7 / m1_lal _ref 為 BIGINT soft reference (非 FK; 跨 hypertable FK
--     不支援 partition-aware + 避循環依賴 + 不阻 dispatch sequence)。
-- ============================================================

-- ============================================================
-- Guard A: TimescaleDB extension + learning.governance_audit_log prereq +
-- 既有 column 完整性 (含 v2 amend metric_baseline) +
-- ADR-0036 forbidden algorithm 反向防護 (detection_method CHECK + column name)
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
    v_ts_ver TEXT;
    v_check_def TEXT;
BEGIN
    -- TimescaleDB extension prereq (per V096 boundary)。
    SELECT extversion INTO v_ts_ver
    FROM pg_extension WHERE extname='timescaledb';
    IF v_ts_ver IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard A FAIL: TimescaleDB extension missing. '
            'V096 boundary not satisfied. Apply V096 first.';
    END IF;

    -- learning.governance_audit_log 必須存在 (M8 → audit cross-ref query target;
    -- 非 schema FK,但 spec §5.1 + v2 amend P0-1 要求 V098 / V035 chain 已 land;
    -- V107 PA-DRIFT-1 patch 範式 — 原 spec 文字 governance.audit_log 為概念命名,
    -- 真實表為 learning.governance_audit_log 23 column hypertable)。
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='governance_audit_log'
    ) THEN
        RAISE EXCEPTION
            'V109 Guard A FAIL: learning.governance_audit_log missing — '
            'V098 must apply before V109 (cross-ref query target). '
            'Verify _sqlx_migrations.';
    END IF;

    -- learning.anomaly_events 已存在情境 → 驗 23 column 完整性 (drift 防護;
    -- IF NOT EXISTS 對 shape mismatch 會靜默 skip 故須 Guard A 主動補)。
    -- 23 column = 5-21 base spec 22 column + v2 amend 新增 metric_baseline。
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='anomaly_events'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'observed_at', 'event_taxonomy', 'severity', 'detection_method',
            'atr_vol_state', 'funding_state', 'strategy_id', 'symbol',
            'metric_value', 'metric_baseline', 'metric_threshold',
            'amplification_loop_24h_count',
            'm3_health_observation_ref', 'm7_decay_signal_ref', 'm1_lal_demote_ref',
            'evidence_json', 'engine_mode',
            'created_by', 'created_at', 'updated_by', 'updated_at',
            'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='anomaly_events'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V109 Guard A FAIL: learning.anomaly_events exists but '
                'missing columns: %. Possible legacy stub conflict — resolve '
                'schema reconciliation before applying V109.',
                v_missing;
        END IF;

        -- ADR-0036 Decision 1 forbidden algorithm 反向防護:
        -- detection_method CHECK constraint 不可含 hmm/markov_switching/garch。
        -- HMM/Markov-switching/GARCH 永久禁用 per ADR-0036 Decision 1。
        SELECT pg_get_constraintdef(oid) INTO v_check_def
        FROM pg_constraint
        WHERE conrelid='learning.anomaly_events'::regclass
          AND conname LIKE '%detection_method%check%'
        LIMIT 1;
        IF v_check_def IS NOT NULL THEN
            IF position('hmm' IN lower(v_check_def)) > 0
               OR position('markov_switching' IN lower(v_check_def)) > 0
               OR position('garch' IN lower(v_check_def)) > 0
            THEN
                RAISE EXCEPTION
                    'V109 Guard A FAIL (ADR-0036 Decision 1 forbidden algorithm '
                    'reverse pattern): detection_method CHECK constraint contains '
                    'forbidden algorithm. HMM / Markov-switching / GARCH 永久禁用 '
                    'per ADR-0036 Decision 1. Any amendment to add such algorithm '
                    'requires amend ADR-0036 first. Actual CHECK definition: %',
                    v_check_def;
            END IF;
        END IF;

        -- ADR-0036 forbidden algorithm column name 反向防護:
        -- column name 不可含 hmm_ / markov_ / garch_ prefix 或 _hmm / _garch suffix。
        IF EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='anomaly_events'
              AND (column_name LIKE 'hmm_%'
                   OR column_name LIKE 'markov_%'
                   OR column_name LIKE 'garch_%'
                   OR column_name LIKE '%_hmm%'
                   OR column_name LIKE '%_garch%')
        ) THEN
            RAISE EXCEPTION
                'V109 Guard A FAIL (ADR-0036 Decision 1 forbidden algorithm '
                'reverse pattern): learning.anomaly_events contains column name '
                'matching forbidden algorithm pattern (hmm_* / markov_* / garch_* '
                '/ *_hmm* / *_garch*). Per ADR-0036 Decision 1 永久禁用 '
                'schema-level enforcement.';
        END IF;
    END IF;
END $$;

-- ============================================================
-- Guard C 預檢: idempotency 重跑時驗 CHECK / hypertable / policy 對齊。
-- 首次 apply 上述 object 不存在 → 用 to_regclass() 安全測 table 是否存在;
-- 首次 apply 走全 skip path (對齊 V107 範式)。
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_chunk_interval BIGINT;
    v_target_oid OID;
BEGIN
    v_target_oid := to_regclass('learning.anomaly_events');
    IF v_target_oid IS NULL THEN
        RAISE NOTICE
            'V109 Guard C pre: learning.anomaly_events not yet created; '
            'skipping pre-check.';
        RETURN;
    END IF;

    -- event_taxonomy CHECK 必含 9 值 (per M8 design spec §2.1 + v2 amend P1-1)。
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%event_taxonomy%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('regime_shift' IN v_actual) = 0
           OR position('liquidation_cascade' IN v_actual) = 0
           OR position('orderbook_imbalance' IN v_actual) = 0
           OR position('funding_outlier' IN v_actual) = 0
           OR position('volume_spike' IN v_actual) = 0
           OR position('spread_widening' IN v_actual) = 0
           OR position('price_dislocation' IN v_actual) = 0
           OR position('ws_disconnect' IN v_actual) = 0
           OR position('fee_anomaly' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: event_taxonomy CHECK enum mismatch. '
                'Actual: %. Expected 9 values (regime_shift/liquidation_cascade/'
                'orderbook_imbalance/funding_outlier/volume_spike/spread_widening/'
                'price_dislocation/ws_disconnect/fee_anomaly) per M8 design spec §2.1.',
                v_actual;
        END IF;
    END IF;

    -- severity CHECK 必含 4 值 (per v2 amend P0-2 INFO/WARN/CRITICAL/HALT)。
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%severity%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('INFO' IN v_actual) = 0
           OR position('WARN' IN v_actual) = 0
           OR position('CRITICAL' IN v_actual) = 0
           OR position('HALT' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: severity CHECK enum mismatch. '
                'Actual: %. Expected INFO/WARN/CRITICAL/HALT '
                '(per v2 amend P0-2 + CR-7 §5 + ADR-0036).',
                v_actual;
        END IF;
    END IF;

    -- detection_method CHECK 必含 4 值 + ADR-0036 黑名單二次驗。
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%detection_method%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('atr_vol_funding_9cell' IN v_actual) = 0
           OR position('rv_percentile' IN v_actual) = 0
           OR position('block_bootstrap' IN v_actual) = 0
           OR position('manual_operator' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: detection_method CHECK enum mismatch. '
                'Actual: %. Expected atr_vol_funding_9cell/rv_percentile/'
                'block_bootstrap/manual_operator (per ADR-0036 Decision 2-4).',
                v_actual;
        END IF;
        -- ADR-0036 Decision 1 forbidden algorithm hardening (二次驗;Guard A 同款)。
        IF position('hmm' IN lower(v_actual)) > 0
           OR position('markov_switching' IN lower(v_actual)) > 0
           OR position('garch' IN lower(v_actual)) > 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL (ADR-0036 Decision 1 forbidden algorithm '
                'hardening): detection_method CHECK constraint contains '
                'forbidden algorithm. HMM / Markov-switching / GARCH 永久禁用. '
                'Actual: %', v_actual;
        END IF;
    END IF;

    -- atr_vol_state CHECK 必含 3 值 (NULL allowed; per ADR-0036 §3.1 9-cell axis 1)。
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%atr_vol_state%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('LOW' IN v_actual) = 0
           OR position('MED' IN v_actual) = 0
           OR position('HIGH' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: atr_vol_state CHECK enum mismatch. '
                'Actual: %. Expected LOW/MED/HIGH (per ADR-0036 §3.1 axis 1).',
                v_actual;
        END IF;
    END IF;

    -- funding_state CHECK 必含 3 值 (NULL allowed; per ADR-0036 §3.1 axis 2)。
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid=v_target_oid
      AND conname LIKE '%funding_state%check%'
    LIMIT 1;
    IF v_actual IS NOT NULL THEN
        IF position('NEGATIVE' IN v_actual) = 0
           OR position('NEUTRAL' IN v_actual) = 0
           OR position('POSITIVE' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V109 Guard C FAIL: funding_state CHECK enum mismatch. '
                'Actual: %. Expected NEGATIVE/NEUTRAL/POSITIVE '
                '(per ADR-0036 §3.1 axis 2).',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 必含 5 值 (含 replay; per v2 amend P0-3)。
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
                'V109 Guard C FAIL: engine_mode CHECK enum mismatch. '
                'Actual: %. Expected 5 values paper/demo/live_demo/live/replay '
                '(replay 為 ADR-0036 Decision 1 例外段 read-only counterfactual; '
                'training filter 必 IN (''live'',''live_demo'')).',
                v_actual;
        END IF;
    END IF;

    -- Hypertable chunk_time_interval 必 = 7 days (604800 sec; 對齊 V106/V107)。
    SELECT EXTRACT(EPOCH FROM time_interval) INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name='anomaly_events'
      AND column_name='observed_at';
    IF v_chunk_interval IS NOT NULL AND v_chunk_interval <> 604800 THEN
        RAISE EXCEPTION
            'V109 Guard C FAIL: chunk_time_interval = % sec (expected 604800 = 7 days).',
            v_chunk_interval;
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 1: CREATE TABLE learning.anomaly_events
-- 主 DDL Step 1: 主表建立 (23 column 含 v2 amend metric_baseline)
--
-- 設計依據:
-- - 9 event_taxonomy (per M8 design spec §2.1; v5.8 §2 M8 完整覆蓋
--   regime/microstructure/infrastructure 三大來源)。剔除 own behavior 4 子類
--   (走 M3 strategy_quality domain per CR-7 dedup contract)。
-- - 4 severity (INFO/WARN/CRITICAL/HALT per v2 amend P0-2 + CR-7 §5 + ADR-0036;
--   HALT 為 Y2+ active gate)。
-- - 4 detection_method (atr_vol_funding_9cell / rv_percentile / block_bootstrap /
--   manual_operator per ADR-0036 Decision 2-4)。不含 HMM/Markov/GARCH
--   (per ADR-0036 Decision 1 永久禁用 schema-level enforcement)。
-- - 3 atr_vol_state + 3 funding_state (per ADR-0036 §3.1 9-cell 矩陣 axis;
--   非 9cell detection 不填 NULL allowed)。
-- - 23 column 含 v2 amend metric_baseline (吸收 W1-E prompt value_baseline;
--   30d rolling block bootstrap baseline; drift PSI 比對用)。
-- - amplification_loop_24h_count INTEGER DEFAULT 0 (per H-11 cap; writer 預計算)。
-- - m3/m7/m1_lal _ref BIGINT soft reference (非 FK 跨 hypertable;dispatch
--   sequence 解耦 + 不阻 V112/V113 後續 land)。
-- - 5 engine_mode (paper/demo/live_demo/live/replay; replay 為 ADR-0036
--   Decision 1 例外段;對比 V106 4 值)。
-- - 5 audit field per V103/V106/V107 sister 範式。
-- - PRIMARY KEY = (id, observed_at) per hypertable 必含 partition column。
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.anomaly_events (
    id                              BIGSERIAL,
    observed_at                     TIMESTAMPTZ NOT NULL,
    -- 9 anomaly 子類顯式枚舉 (per M8 design spec §2.1);新 taxonomy 需 amend ENUM。
    event_taxonomy                  TEXT NOT NULL
                                    CHECK (event_taxonomy IN (
                                        'regime_shift',
                                        'liquidation_cascade',
                                        'orderbook_imbalance',
                                        'funding_outlier',
                                        'volume_spike',
                                        'spread_widening',
                                        'price_dislocation',
                                        'ws_disconnect',
                                        'fee_anomaly'
                                    )),
    -- 4 級 severity (per v2 amend P0-2);HALT Y2+ 不寫 row 但 ENUM 先 land。
    severity                        TEXT NOT NULL
                                    CHECK (severity IN (
                                        'INFO',
                                        'WARN',
                                        'CRITICAL',
                                        'HALT'
                                    )),
    -- 4 替代算法 per ADR-0036 Decision 2-4;不含 HMM/Markov/GARCH
    -- (per ADR-0036 Decision 1 永久禁用 + Guard A/C 雙重反向防護)。
    detection_method                TEXT NOT NULL
                                    CHECK (detection_method IN (
                                        'atr_vol_funding_9cell',
                                        'rv_percentile',
                                        'block_bootstrap',
                                        'manual_operator'
                                    )),
    -- 9-cell axis 1 (per ADR-0036 §3.1);非 9cell detection 不填 NULL allowed。
    atr_vol_state                   TEXT
                                    CHECK (atr_vol_state IS NULL OR atr_vol_state IN (
                                        'LOW',
                                        'MED',
                                        'HIGH'
                                    )),
    -- 9-cell axis 2 (per ADR-0036 §3.1);同 atr_vol_state NULL allowed。
    funding_state                   TEXT
                                    CHECK (funding_state IS NULL OR funding_state IN (
                                        'NEGATIVE',
                                        'NEUTRAL',
                                        'POSITIVE'
                                    )),
    strategy_id                     TEXT,
    symbol                          TEXT,
    metric_value                    NUMERIC(18,8),
    -- v2 amend P1-5 新增: 30d rolling block bootstrap baseline; drift PSI 比對用
    -- (per data-drift-detection skill §3.1 reference distribution 必存)。
    metric_baseline                 NUMERIC(18,8),
    metric_threshold                NUMERIC(18,8),
    -- H-11 cap (per M8 design spec §5): 24h 同 event_taxonomy CRITICAL/HALT
    -- count; writer 預計算; ≥ 2 雖 INSERT 但 evidence_json 標 cap_suppressed=true
    -- 不 emit M3 cascade event。
    amplification_loop_24h_count    INTEGER NOT NULL DEFAULT 0,
    -- m3/m7/m1_lal _ref BIGINT soft reference (非 FK 跨 hypertable;application
    -- 層 + healthcheck 補)。m1_lal_demote_ref 對齊 ADR-0034 數字越大越嚴方向 —
    -- ref 指向 demote 後 row 而非 promote。
    m3_health_observation_ref       BIGINT,
    m7_decay_signal_ref             BIGINT,
    m1_lal_demote_ref               BIGINT,
    -- 富 context: detector raw output / atr percentile 計算 window /
    -- funding state derivation / block bootstrap resample distribution /
    -- cap_suppressed flag / cascade_actions_taken; debug + audit 用。
    evidence_json                   JSONB,
    -- 5 值齊全 (v2 amend P0-3);training filter 必 IN ('live','live_demo');
    -- replay 為 ADR-0036 Decision 1 例外段 (M11 read-only counterfactual)。
    engine_mode                     TEXT NOT NULL
                                    CHECK (engine_mode IN (
                                        'paper',
                                        'demo',
                                        'live_demo',
                                        'live',
                                        'replay'
                                    )),
    -- 5 audit field per V103 EXTEND + V106/V107 sister 範式。
    created_by                      TEXT NOT NULL DEFAULT 'anomaly_detector',
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                      TEXT,
    updated_at                      TIMESTAMPTZ,
    source_version                  TEXT NOT NULL DEFAULT 'V109',
    PRIMARY KEY (id, observed_at)
);

-- ============================================================
-- Main DDL Step 2: Hypertable (7d chunk;對齊 V106/V107 sister)
-- 主 DDL Step 2: TimescaleDB hypertable (7 天 chunk)
--
-- - chunk_time_interval = 7d: 對齊 V106/V107 weekly rollup query pattern;
--   60-225 row/day × 7d = ~420-1.6k row/chunk (對比 V106 5M row/chunk);
--   chunk 邊界對齊便於 cross-V### JOIN + M7 14d (2 chunk) pruning。
-- - if_not_exists => TRUE: idempotent 重跑不 RAISE。
-- ============================================================
SELECT create_hypertable(
    'learning.anomaly_events',
    'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- ============================================================
-- Main DDL Step 3: Compression settings
-- 主 DDL Step 3: 壓縮設定 (segmentby + orderby)
--
-- - segmentby = 'event_taxonomy, severity': 同 taxonomy × severity 連續 row
--   segment 壓縮率最高 (80-90%);對比 V106 (domain, metric_name) +
--   V107 (strategy_id, symbol, divergence_type) 各表自身 hot path 維度。
-- - orderby = 'observed_at DESC, id DESC': time-DESC 最近資料 close 在 chunk
--   邊界, decompress 成本最低 (對齊 V106/V107 範式)。
--
-- 注意: ALTER TABLE ... SET (timescaledb.compress, ...) 對既有同設定不 RAISE;
-- 但若 compress 已開且 segmentby/orderby 不同會 RAISE。本 DDL 走 idempotent
-- path; 重跑 V109 對 already-compressed table 無動作。
-- ============================================================
DO $$
DECLARE
    v_already_compressed BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema = 'learning'
          AND hypertable_name = 'anomaly_events'
    ) INTO v_already_compressed;

    IF NOT v_already_compressed THEN
        ALTER TABLE learning.anomaly_events SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'event_taxonomy, severity',
            timescaledb.compress_orderby = 'observed_at DESC, id DESC'
        );
        RAISE NOTICE
            'V109: enabled compression on learning.anomaly_events '
            '(segmentby=event_taxonomy,severity; orderby=observed_at DESC)';
    ELSE
        RAISE NOTICE
            'V109: compression already enabled on learning.anomaly_events; '
            'skipping ALTER';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 4: Compression + Retention policies (idempotent)
-- 主 DDL Step 4: 壓縮策略 + 保留策略 (重跑安全)
--
-- - add_compression_policy: 30 天後自動壓縮 chunk (寬於 V106 7d;對齊 ADR-0036
--   Decision 4 block bootstrap 30d re-estimate cadence + M3 cascade 30d 內
--   hot read 需求 per V109 spec §3.2);
-- - add_retention_policy: 180 天後自動 drop chunk (對比 V106 90d 較長因
--   M1 LAL 90d incident-free + M7 14d persistent + safety margin per V109 spec §3.3);
--   long-term trend 走 daily aggregate 表 (Sprint 3+ 後續)。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_compression'
          AND hypertable_name = 'anomaly_events'
    ) THEN
        PERFORM add_compression_policy(
            'learning.anomaly_events',
            INTERVAL '30 days'
        );
        RAISE NOTICE
            'V109: added compression policy (30 days) on anomaly_events';
    ELSE
        RAISE NOTICE
            'V109: compression policy already present; skipping';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_retention'
          AND hypertable_name = 'anomaly_events'
    ) THEN
        PERFORM add_retention_policy(
            'learning.anomaly_events',
            INTERVAL '180 days'
        );
        RAISE NOTICE
            'V109: added retention policy (180 days) on anomaly_events';
    ELSE
        RAISE NOTICE
            'V109: retention policy already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 5: Hot-path indexes (4 個)
-- 主 DDL Step 5: 熱查詢索引 (4 個;對齊 V109 spec §4.2)
--
-- 設計依據 (per V109 spec §4.1 query pattern → index map):
-- - idx_anomaly_taxonomy_observed: per-taxonomy timeline 主 hot path
--   (covering 9 taxonomy)。
-- - idx_anomaly_severity_observed: alert dashboard hot path; partial
--   WHERE severity IN (CRITICAL, HALT);縮 95% 索引大小 (預估 <5% row 是
--   CRITICAL/HALT)。
-- - idx_anomaly_symbol_observed: per-symbol drill-down; partial WHERE
--   symbol IS NOT NULL;縮 40% (預估 60% row 有 symbol)。
-- - idx_anomaly_strategy_observed: per-strategy aggregation; partial WHERE
--   strategy_id IS NOT NULL;縮 90% (預估 <10% row 是 strategy-specific;
--   大多 strategy-specific anomaly 走 M3 strategy_quality domain per CR-7)。
--
-- 注意: hypertable + chunk 上 CREATE INDEX 走 non-CONCURRENT path (timescale
-- 自動逐 chunk 建);對齊 V106/V107 sister table 範式 (不用 CONCURRENTLY)。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_anomaly_taxonomy_observed
    ON learning.anomaly_events (event_taxonomy, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_anomaly_severity_observed
    ON learning.anomaly_events (severity, observed_at DESC)
    WHERE severity IN ('CRITICAL', 'HALT');

CREATE INDEX IF NOT EXISTS idx_anomaly_symbol_observed
    ON learning.anomaly_events (symbol, observed_at DESC)
    WHERE symbol IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_anomaly_strategy_observed
    ON learning.anomaly_events (strategy_id, observed_at DESC)
    WHERE strategy_id IS NOT NULL;

-- ============================================================
-- Main DDL Step 6: COMMENT (audit metadata)
-- 主 DDL Step 6: 表 / 欄位註釋 (運維說明)
-- ============================================================
COMMENT ON TABLE learning.anomaly_events IS
    'M8 Anomaly Events Hypertable (V109). 9 event_taxonomy × 4 severity × '
    '4 detection_method × per-symbol/strategy 觀測; '
    'ADR-0036 Decision 1 黑名單: HMM/Markov-switching/GARCH 永久禁用 '
    'schema-level enforcement (Guard A/C 雙重反向防護); '
    'ADR-0036 Decision 2-4 替代算法: ATR-vol×Funding 9-cell + RV percentile + '
    'block bootstrap + manual_operator; '
    'amplification cap H-11 enforced via writer-side query; '
    '7d chunk + 30d compression + 180d retention; '
    'v2 amend 加 metric_baseline column (吸收 W1-E prompt value_baseline)。';

COMMENT ON COLUMN learning.anomaly_events.detection_method IS
    'ADR-0036 Decision 1 黑名單算法 schema-level enforcement: '
    '不可含 hmm/markov_switching/garch (Guard A + C 雙重反向防護)。'
    '任何 future amend 必先 amend ADR-0036 Decision 1。';

COMMENT ON COLUMN learning.anomaly_events.metric_baseline IS
    'v2 amend P1-5 新增 (吸收 W1-E prompt value_baseline): '
    '30d rolling block bootstrap baseline; drift PSI 比對用 '
    '(per data-drift-detection skill §3.1 reference distribution 必存)。';

COMMENT ON COLUMN learning.anomaly_events.amplification_loop_24h_count IS
    'H-11 cap (per M8 design spec §5): 24h 同 event_taxonomy CRITICAL/HALT '
    'count; writer 預計算; ≥ 2 雖 INSERT 但 evidence_json 標 cap_suppressed=true '
    '不 emit M3 cascade event。';

COMMENT ON COLUMN learning.anomaly_events.engine_mode IS
    '5 值齊全 (paper/demo/live_demo/live/replay); replay 為 ADR-0036 Decision 1 '
    '例外段 (M11 read-only counterfactual via replay surface); '
    'ML training filter 必 IN (''live'',''live_demo'') per CLAUDE.md §七。';

COMMENT ON COLUMN learning.anomaly_events.m1_lal_demote_ref IS
    'M1 LAL Tier 降階 V112 row id 反向 ref (per M8 design spec §9.3)。'
    '對齊 ADR-0034 數字越大越嚴方向 — ref 指向 demote 後 row 而非 promote。';

-- ============================================================
-- Guard C 後驗: 確保 DDL 成功後 CHECK + hypertable + policy + index 全到位
-- (與 Guard C 前置一致但放寬: 後驗預期 constraint 必存在)。
-- 對齊 V106/V107 範式;加 ADR-0036 黑名單三次驗 (Guard A + Guard C 預檢 + 後驗)。
-- ============================================================
DO $$
DECLARE
    v_event_taxonomy_def TEXT;
    v_severity_def TEXT;
    v_detection_method_def TEXT;
    v_atr_vol_state_def TEXT;
    v_funding_state_def TEXT;
    v_engine_mode_def TEXT;
    v_chunk_interval BIGINT;
    v_compress_job INTEGER;
    v_retention_job INTEGER;
    v_index_count INTEGER;
    v_column_count INTEGER;
BEGIN
    -- 23 column 全俱在驗證 (per AC-S2-D-7)。
    SELECT COUNT(*) INTO v_column_count
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='anomaly_events';
    IF v_column_count <> 23 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: column count = % (expected 23 含 v2 amend '
            'metric_baseline). Schema drift detected.', v_column_count;
    END IF;

    -- event_taxonomy CHECK 必含 9 值。
    SELECT pg_get_constraintdef(oid) INTO v_event_taxonomy_def
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%event_taxonomy%check%'
    LIMIT 1;
    IF v_event_taxonomy_def IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: event_taxonomy CHECK constraint not found.';
    END IF;
    IF position('fee_anomaly' IN v_event_taxonomy_def) = 0
       OR position('regime_shift' IN v_event_taxonomy_def) = 0
       OR position('ws_disconnect' IN v_event_taxonomy_def) = 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: event_taxonomy CHECK missing required '
            'values. Actual: %.', v_event_taxonomy_def;
    END IF;

    -- severity CHECK 必含 4 值。
    SELECT pg_get_constraintdef(oid) INTO v_severity_def
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%severity%check%'
    LIMIT 1;
    IF v_severity_def IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: severity CHECK constraint not found.';
    END IF;
    IF position('HALT' IN v_severity_def) = 0
       OR position('CRITICAL' IN v_severity_def) = 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: severity CHECK missing required values. '
            'Actual: %.', v_severity_def;
    END IF;

    -- detection_method CHECK 必含 4 值 + ADR-0036 黑名單三次驗 (Guard A/C 預檢/後驗)。
    SELECT pg_get_constraintdef(oid) INTO v_detection_method_def
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%detection_method%check%'
    LIMIT 1;
    IF v_detection_method_def IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: detection_method CHECK constraint not found.';
    END IF;
    IF position('atr_vol_funding_9cell' IN v_detection_method_def) = 0
       OR position('block_bootstrap' IN v_detection_method_def) = 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: detection_method CHECK missing required '
            'values. Actual: %.', v_detection_method_def;
    END IF;
    IF position('hmm' IN lower(v_detection_method_def)) > 0
       OR position('markov_switching' IN lower(v_detection_method_def)) > 0
       OR position('garch' IN lower(v_detection_method_def)) > 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL (ADR-0036 Decision 1 forbidden algorithm '
            'hardening): detection_method CHECK contains forbidden algorithm. '
            'Actual: %.', v_detection_method_def;
    END IF;

    -- atr_vol_state CHECK 必含 3 值。
    SELECT pg_get_constraintdef(oid) INTO v_atr_vol_state_def
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%atr_vol_state%check%'
    LIMIT 1;
    IF v_atr_vol_state_def IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: atr_vol_state CHECK constraint not found.';
    END IF;
    IF position('LOW' IN v_atr_vol_state_def) = 0
       OR position('HIGH' IN v_atr_vol_state_def) = 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: atr_vol_state CHECK missing values. '
            'Actual: %.', v_atr_vol_state_def;
    END IF;

    -- funding_state CHECK 必含 3 值。
    SELECT pg_get_constraintdef(oid) INTO v_funding_state_def
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%funding_state%check%'
    LIMIT 1;
    IF v_funding_state_def IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: funding_state CHECK constraint not found.';
    END IF;
    IF position('NEGATIVE' IN v_funding_state_def) = 0
       OR position('POSITIVE' IN v_funding_state_def) = 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: funding_state CHECK missing values. '
            'Actual: %.', v_funding_state_def;
    END IF;

    -- engine_mode CHECK 必含 5 值 (含 replay)。
    SELECT pg_get_constraintdef(oid) INTO v_engine_mode_def
    FROM pg_constraint
    WHERE conrelid='learning.anomaly_events'::regclass
      AND conname LIKE '%engine_mode%check%'
    LIMIT 1;
    IF v_engine_mode_def IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: engine_mode CHECK constraint not found.';
    END IF;
    IF position('replay' IN v_engine_mode_def) = 0
       OR position('live_demo' IN v_engine_mode_def) = 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: engine_mode CHECK missing required values '
            '(必含 replay + live_demo). Actual: %.', v_engine_mode_def;
    END IF;

    -- Hypertable chunk_time_interval 必 = 7 days (604800 sec)。
    SELECT EXTRACT(EPOCH FROM time_interval) INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name='anomaly_events'
      AND column_name='observed_at';
    IF v_chunk_interval IS NULL THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: hypertable not created on observed_at.';
    END IF;
    IF v_chunk_interval <> 604800 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: chunk_time_interval = % sec (expected 604800).',
            v_chunk_interval;
    END IF;

    -- Compression policy 必存在 (30d after)。
    SELECT COUNT(*) INTO v_compress_job
    FROM timescaledb_information.jobs
    WHERE proc_name='policy_compression'
      AND hypertable_name='anomaly_events';
    IF v_compress_job = 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: compression policy missing.';
    END IF;

    -- Retention policy 必存在 (180d)。
    SELECT COUNT(*) INTO v_retention_job
    FROM timescaledb_information.jobs
    WHERE proc_name='policy_retention'
      AND hypertable_name='anomaly_events';
    IF v_retention_job = 0 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: retention policy missing.';
    END IF;

    -- 4 hot-path index 全到位。
    SELECT COUNT(*) INTO v_index_count
    FROM pg_indexes
    WHERE schemaname='learning'
      AND tablename='anomaly_events'
      AND indexname IN (
          'idx_anomaly_taxonomy_observed',
          'idx_anomaly_severity_observed',
          'idx_anomaly_symbol_observed',
          'idx_anomaly_strategy_observed'
      );
    IF v_index_count <> 4 THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL: 4 hot-path index expected, found %.',
            v_index_count;
    END IF;

    -- ADR-0036 forbidden algorithm column name 反向後驗 (Guard A 同款檢測)。
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='anomaly_events'
          AND (column_name LIKE 'hmm_%'
               OR column_name LIKE 'markov_%'
               OR column_name LIKE 'garch_%'
               OR column_name LIKE '%_hmm%'
               OR column_name LIKE '%_garch%')
    ) THEN
        RAISE EXCEPTION
            'V109 Guard C post FAIL (ADR-0036 Decision 1 forbidden algorithm '
            'reverse pattern): learning.anomaly_events contains FORBIDDEN '
            'column name pattern (hmm_/markov_/garch_/_hmm/_garch). '
            'Schema drift detected.';
    END IF;

    RAISE NOTICE
        'V109: all guards PASS — 23 column ok (含 v2 amend metric_baseline), '
        '6 CHECK (event_taxonomy 9 / severity 4 / detection_method 4 / '
        'atr_vol_state 3 / funding_state 3 / engine_mode 5) ok, '
        'hypertable chunk=7d, compression(30d) + retention(180d) policies '
        'installed, 4 hot-path index built, '
        'ADR-0036 Decision 1 forbidden algorithm 反向防護 PASS '
        '(detection_method CHECK + column name 雙重)。';
END $$;

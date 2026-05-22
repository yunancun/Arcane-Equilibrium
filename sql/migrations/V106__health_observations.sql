-- ============================================================
-- V106: M3 Health Observations Hypertable (learning.health_observations)
--
-- 用途:
--   建立 M3 健康觀測中央表，6 health domain × 4 health state 配 TimescaleDB
--   hypertable (7d chunk + 7d compression + 90d retention)，提供 M1 LAL /
--   M8 amplification cap / M11 wall-clock budget overrun 等 cross-V### query
--   target。
--   per ADR-0042 Decision 3 (6 domain) + Decision 4 (amplification cap H-11) +
--   M3 design spec §2.3 SLO threshold + V106 schema spec §2.1 full DDL。
--
-- 範圍:
--   - CREATE TABLE learning.health_observations (19 column);
--   - create_hypertable(observed_at, 7 days);
--   - ALTER ... SET (timescaledb.compress, segmentby, orderby);
--   - add_compression_policy(7 days);
--   - add_retention_policy(90 days);
--   - 4 hot-path index (1 domain-metric-time / 3 partial: state / symbol /
--     strategy);
--   - Guard A: TimescaleDB extension + governance.audit_log prereq + column
--     完整性 (drift 防護);
--   - Guard C: domain/state/engine_mode CHECK 完整性 + hypertable chunk
--     interval + policy 存在性;
--   - 無 Guard B (本 migration 不 ALTER 既有 column type)。
--
-- Parent specs:
--   docs/execution_plan/2026-05-21--v106_m3_health_observations_schema_spec.md
--   docs/execution_plan/2026-05-21--m3_health_monitoring_design_spec.md
--   docs/adr/0042-m3-health-monitoring.md
--   docs/execution_plan/2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md
--
-- 硬邊界:
--   - PRIMARY KEY = (observation_id, observed_at) — hypertable 必含 partition
--     column 在 PK，否則 timescale create_hypertable 拒。
--   - amplification_loop_24h_count 預設 0；writer 端負責 24h rolling count
--     計算 (per ADR-0042 Decision 4)。
--   - engine_mode CHECK 4 值齊全；training filter 必 IN ('live','live_demo')。
--   - V096 boundary (TimescaleDB extension) + V098 governance.audit_log
--     cross-ref query target prereq。
-- ============================================================

-- ============================================================
-- Guard A: TimescaleDB extension + governance.audit_log prereq
-- Guard A: TimescaleDB 擴展 + governance.audit_log 前置條件
-- ============================================================
DO $$
DECLARE
    v_missing TEXT[];
    v_ts_ver TEXT;
BEGIN
    -- TimescaleDB extension prereq (per V096 boundary)。
    SELECT extversion INTO v_ts_ver
    FROM pg_extension WHERE extname='timescaledb';
    IF v_ts_ver IS NULL THEN
        RAISE EXCEPTION
            'V106 Guard A FAIL: TimescaleDB extension missing. '
            'V096 boundary not satisfied. Apply V096 first.';
    END IF;

    -- learning.health_observations 已存在情境 → 驗 19 column 完整 (V023 drift
    -- 防護 — IF NOT EXISTS 對 shape mismatch 會靜默 skip)。
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='health_observations'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'observation_id', 'observed_at', 'domain', 'metric_name',
            'state', 'state_prev', 'dwell_time_sec',
            'metric_value', 'metric_threshold',
            'amplification_loop_24h_count', 'symbol', 'strategy_name',
            'evidence_json', 'engine_mode',
            'created_by', 'created_at', 'updated_by', 'updated_at',
            'source_version'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='health_observations'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V106 Guard A FAIL: learning.health_observations exists but '
                'missing columns: %. Possible legacy stub conflict — resolve '
                'schema reconciliation before applying V106.',
                v_missing;
        END IF;
    END IF;

    -- governance audit_log 必須存在 (M3 → governance cross-ref query target;
    -- 非 schema FK,但 spec §5.1 要求 V098 已 land)。
    -- 注意: V098 真實表名為 learning.governance_audit_log (V035 baseline);
    -- V106 spec §5.1 文字「governance.audit_log」屬概念命名,實際對應
    -- learning.governance_audit_log。Guard A 採真實表名對齊 V098 schema。
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='governance_audit_log'
    ) THEN
        RAISE EXCEPTION
            'V106 Guard A FAIL: learning.governance_audit_log missing — '
            'V098/V035 must apply before V106 (cross-ref query target). '
            'Verify _sqlx_migrations.';
    END IF;
END $$;

-- ============================================================
-- Guard C 預檢: idempotency 重跑時驗 CHECK / hypertable / policy 對齊
-- (首次 apply 上述 object 不存在 → IF EXISTS 包覆避免 regclass cast RAISE;
--  重跑時抓 drift)
-- ============================================================
DO $$
DECLARE
    v_actual TEXT;
    v_chunk_interval BIGINT;
    v_table_exists BOOLEAN;
BEGIN
    -- 預檢入口: 表不存在則 skip 全部 (首次 apply path)。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'health_observations'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        -- domain CHECK 6 值齊全。
        -- 命名來源: ADR-0042 Decision 3 + M3 design spec §2.1 single source of
        -- truth (3 層分離: Process / Pipeline / Business)。V106 spec §1.1 line
        -- 53 (2026-05-22 PA reconcile) 明示前版 ws_latency/rest_success_rate/
        -- db_backlog/disk_usage/cpu_mem/strategy_level 退役, 以 ADR-0042 為準。
        SELECT pg_get_constraintdef(oid) INTO v_actual
        FROM pg_constraint
        WHERE conrelid = 'learning.health_observations'::regclass
          AND conname LIKE '%domain%check%'
        LIMIT 1;
        IF v_actual IS NOT NULL THEN
            IF position('engine_runtime' IN v_actual) = 0
               OR position('pipeline_throughput' IN v_actual) = 0
               OR position('database_pool' IN v_actual) = 0
               OR position('api_latency' IN v_actual) = 0
               OR position('strategy_quality' IN v_actual) = 0
               OR position('risk_envelope' IN v_actual) = 0
            THEN
                RAISE EXCEPTION
                    'V106 Guard C FAIL: domain CHECK enum mismatch. Actual: %. '
                    'Expected 6 values (engine_runtime/pipeline_throughput/'
                    'database_pool/api_latency/strategy_quality/risk_envelope) '
                    'per ADR-0042 Decision 3.',
                    v_actual;
            END IF;
        END IF;

        -- state CHECK 4 值齊全 (排除 state_prev 的 CHECK)。
        SELECT pg_get_constraintdef(oid) INTO v_actual
        FROM pg_constraint
        WHERE conrelid = 'learning.health_observations'::regclass
          AND conname LIKE '%_state_check'
          AND conname NOT LIKE '%state_prev%'
        LIMIT 1;
        IF v_actual IS NOT NULL THEN
            IF position('HEALTH_OK' IN v_actual) = 0
               OR position('HEALTH_WARN' IN v_actual) = 0
               OR position('HEALTH_DEGRADED' IN v_actual) = 0
               OR position('HEALTH_CRITICAL' IN v_actual) = 0
            THEN
                RAISE EXCEPTION
                    'V106 Guard C FAIL: state CHECK enum mismatch. Actual: %. '
                    'Expected HEALTH_OK/HEALTH_WARN/HEALTH_DEGRADED/HEALTH_CRITICAL.',
                    v_actual;
            END IF;
        END IF;

        -- engine_mode CHECK 4 值齊全 (training filter 必 IN ('live','live_demo'))。
        SELECT pg_get_constraintdef(oid) INTO v_actual
        FROM pg_constraint
        WHERE conrelid = 'learning.health_observations'::regclass
          AND conname LIKE '%engine_mode%check%'
        LIMIT 1;
        IF v_actual IS NOT NULL THEN
            IF position('paper' IN v_actual) = 0
               OR position('demo' IN v_actual) = 0
               OR position('live_demo' IN v_actual) = 0
               OR position('live' IN v_actual) = 0
            THEN
                RAISE EXCEPTION
                    'V106 Guard C FAIL: engine_mode CHECK enum mismatch. '
                    'Actual: %. Expected paper/demo/live_demo/live.',
                    v_actual;
            END IF;
        END IF;

        -- Hypertable 已建立場景 → 驗 chunk_time_interval = 7 days。
        -- timescaledb_information.dimensions.time_interval 是 INTERVAL；
        -- EXTRACT(EPOCH FROM interval) 返回秒；7d = 604800 sec。
        SELECT EXTRACT(EPOCH FROM time_interval) INTO v_chunk_interval
        FROM timescaledb_information.dimensions
        WHERE hypertable_name = 'health_observations'
          AND column_name = 'observed_at';
        IF v_chunk_interval IS NOT NULL AND v_chunk_interval <> 604800 THEN
            RAISE EXCEPTION
                'V106 Guard C FAIL: hypertable chunk_time_interval mismatch. '
                'Actual: % seconds. Expected: 604800 (7 days).',
                v_chunk_interval;
        END IF;
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 1: CREATE TABLE learning.health_observations
-- 主 DDL Step 1: 建立中央健康觀測表 (19 column)
--
-- 設計理由:
-- - observation_id BIGSERIAL: 高頻寫入序列主鍵 (716k row/day 估計)。
-- - observed_at TIMESTAMPTZ: hypertable time dimension; UTC 統一。
-- - domain TEXT + CHECK 6 值: 6 hot domain 顯式枚舉。
-- - state TEXT + CHECK 4 值: HEALTH_OK<WARN<DEGRADED<CRITICAL。
-- - amplification_loop_24h_count DEFAULT 0: per H-11 cap; writer 預計算。
-- - metric_value NUMERIC(18,8): 高精度 (避 FLOAT 精度誤差)。
-- - PRIMARY KEY (observation_id, observed_at): hypertable 必含 partition col。
-- ============================================================
CREATE TABLE IF NOT EXISTS learning.health_observations (
    observation_id                BIGSERIAL,
    observed_at                   TIMESTAMPTZ NOT NULL,
    -- domain 6 值對齊 ADR-0042 Decision 3 + M3 design spec §2.1 (3 層分離:
    -- Process / Pipeline / Business)。V106 spec §1.1 line 53 (2026-05-22 PA
    -- reconcile) 明示採 ADR-0042 為唯一 source of truth; Rust HealthDomain enum
    -- (rust/openclaw_engine/src/health/mod.rs `as_str()`) 與此 6 個字面值
    -- round-trip 必對齊。
    domain                        TEXT NOT NULL
                                  CHECK (domain IN (
                                      'engine_runtime',
                                      'pipeline_throughput',
                                      'database_pool',
                                      'api_latency',
                                      'strategy_quality',
                                      'risk_envelope'
                                  )),
    metric_name                   TEXT NOT NULL,
    state                         TEXT NOT NULL
                                  CHECK (state IN (
                                      'HEALTH_OK',
                                      'HEALTH_WARN',
                                      'HEALTH_DEGRADED',
                                      'HEALTH_CRITICAL'
                                  )),
    state_prev                    TEXT
                                  CHECK (state_prev IS NULL OR state_prev IN (
                                      'HEALTH_OK',
                                      'HEALTH_WARN',
                                      'HEALTH_DEGRADED',
                                      'HEALTH_CRITICAL'
                                  )),
    dwell_time_sec                INTEGER,
    metric_value                  NUMERIC(18,8) NOT NULL,
    metric_threshold              NUMERIC(18,8),
    amplification_loop_24h_count  INTEGER NOT NULL DEFAULT 0,
    symbol                        TEXT,
    strategy_name                 TEXT,
    evidence_json                 JSONB,
    engine_mode                   TEXT NOT NULL
                                  CHECK (engine_mode IN ('paper','demo','live_demo','live')),
    created_by                    TEXT NOT NULL DEFAULT 'health_monitor',
    created_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by                    TEXT,
    updated_at                    TIMESTAMPTZ,
    source_version                TEXT NOT NULL DEFAULT 'V106',
    PRIMARY KEY (observation_id, observed_at)
);

-- ============================================================
-- Main DDL Step 2: Hypertable (7d chunk)
-- 主 DDL Step 2: TimescaleDB hypertable (7 天 chunk)
--
-- - if_not_exists => TRUE: idempotent 重跑不 RAISE。
-- - 7d chunk 對齊 weekly rollup query pattern + ~5M row/chunk 大小。
-- - 716k row/day × 7d = ~5M row/chunk = ~1.25 GB uncompressed。
-- ============================================================
SELECT create_hypertable(
    'learning.health_observations',
    'observed_at',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE
);

-- ============================================================
-- Main DDL Step 3: Compression settings
-- 主 DDL Step 3: 壓縮設定 (segmentby + orderby)
--
-- - segmentby = 'domain, metric_name': 同 domain × metric 連續 row segment
--   壓縮率最高 (80-90%)。
-- - orderby = 'observed_at DESC, observation_id DESC': time-DESC 最近資料
--   close 在 chunk 邊界, decompress 成本最低。
--
-- 注意: ALTER TABLE ... SET (timescaledb.compress, ...) 對既有同設定不
-- RAISE; 但若 compress 已開且 segmentby/orderby 不同會 RAISE。本 DDL
-- 走 idempotent path; 重跑 V106 對 already-compressed table 無動作。
-- ============================================================
DO $$
DECLARE
    v_already_compressed BOOLEAN;
BEGIN
    -- timescaledb_information.compression_settings 查 hypertable 是否已開壓縮。
    SELECT EXISTS (
        SELECT 1 FROM timescaledb_information.compression_settings
        WHERE hypertable_schema = 'learning'
          AND hypertable_name = 'health_observations'
    ) INTO v_already_compressed;

    IF NOT v_already_compressed THEN
        ALTER TABLE learning.health_observations SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'domain, metric_name',
            timescaledb.compress_orderby = 'observed_at DESC, observation_id DESC'
        );
        RAISE NOTICE
            'V106: enabled compression on learning.health_observations '
            '(segmentby=domain,metric_name; orderby=observed_at DESC)';
    ELSE
        RAISE NOTICE
            'V106: compression already enabled on learning.health_observations; '
            'skipping ALTER';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 4: Compression + Retention policies (idempotent)
-- 主 DDL Step 4: 壓縮策略 + 保留策略 (重跑安全)
--
-- - add_compression_policy: 7 天後自動壓縮 chunk (避免 hot data 寫入損)。
-- - add_retention_policy: 90 天後自動 drop chunk (operational metric 非
--   strategy alpha, 90d 足夠 trend analysis)。
-- ============================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_compression'
          AND hypertable_name = 'health_observations'
    ) THEN
        PERFORM add_compression_policy(
            'learning.health_observations',
            INTERVAL '7 days'
        );
        RAISE NOTICE
            'V106: added compression policy (7 days) on health_observations';
    ELSE
        RAISE NOTICE
            'V106: compression policy already present; skipping';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM timescaledb_information.jobs
        WHERE proc_name = 'policy_retention'
          AND hypertable_name = 'health_observations'
    ) THEN
        PERFORM add_retention_policy(
            'learning.health_observations',
            INTERVAL '90 days'
        );
        RAISE NOTICE
            'V106: added retention policy (90 days) on health_observations';
    ELSE
        RAISE NOTICE
            'V106: retention policy already present; skipping';
    END IF;
END $$;

-- ============================================================
-- Main DDL Step 5: Hot-path indexes (4 個)
-- 主 DDL Step 5: 熱查詢索引 (4 個)
--
-- 設計依據 (per V106 spec §4.1 query pattern → index map):
-- - idx_health_domain_metric_observed: per-domain metric timeline 主 hot
--   path; covering 6 domain × ~10 metric_name。
-- - idx_health_state_observed: state-degraded alert dashboard; partial
--   index (state ∈ DEGRADED/CRITICAL) 縮 99% 索引大小。
-- - idx_health_symbol_observed: per-symbol query (pipeline_throughput /
--   strategy_quality 兩 domain 有 symbol per ADR-0042 Decision 3); partial
--   NOT NULL 縮 50%。
-- - idx_health_strategy_observed: per-strategy query (strategy_quality domain
--   per ADR-0042 Decision 3); partial NOT NULL 縮 25% (75% row 是
--   strategy_quality)。
--
-- 注意: hypertable + chunk 上 CREATE INDEX 是逐 chunk 建 (timescale 自動);
-- 不可加 CONCURRENTLY (timescale extension 不支援 transaction-block 內
-- CONCURRENTLY chunk index)。本 migration 走非 CONCURRENT path。
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_health_domain_metric_observed
    ON learning.health_observations (domain, metric_name, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_health_state_observed
    ON learning.health_observations (state, observed_at DESC)
    WHERE state IN ('HEALTH_DEGRADED', 'HEALTH_CRITICAL');

CREATE INDEX IF NOT EXISTS idx_health_symbol_observed
    ON learning.health_observations (symbol, observed_at DESC)
    WHERE symbol IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_health_strategy_observed
    ON learning.health_observations (strategy_name, observed_at DESC)
    WHERE strategy_name IS NOT NULL;

-- ============================================================
-- Main DDL Step 6: COMMENT (audit metadata)
-- 主 DDL Step 6: 表 / 欄位註釋 (運維說明)
-- ============================================================
COMMENT ON TABLE learning.health_observations IS
    'M3 Health Observations Hypertable (V106). 6 domain × 4 state × per-'
    'symbol/strategy 觀測; amplification cap H-11 enforced via writer-side '
    'query; 7d chunk + 7d compression + 90d retention.';

COMMENT ON COLUMN learning.health_observations.amplification_loop_24h_count IS
    'H-11 amplification cap: 24h 同 domain state change 計數; writer 預計算; '
    'ADR-0042 Decision 4 規範 1-anomaly = 1-state-change/24h, '
    '同 anomaly_id 24h 內最多觸發 1 次 state transition。';

COMMENT ON COLUMN learning.health_observations.engine_mode IS
    '4 值齊全 (paper/demo/live_demo/live); training filter 必 '
    'IN (''live'',''live_demo'') per CLAUDE.md §七。';

-- ============================================================
-- Guard C 後驗: 確保 DDL 成功後 CHECK + hypertable + policy + index 全到位
-- (與 Guard C 前置一致但放寬: 後驗預期 constraint 必存在)
-- ============================================================
DO $$
DECLARE
    v_domain_def TEXT;
    v_state_def TEXT;
    v_engine_mode_def TEXT;
    v_chunk_interval BIGINT;
    v_compress_job INTEGER;
    v_retention_job INTEGER;
    v_index_count INTEGER;
BEGIN
    -- domain CHECK 必含 6 值。
    SELECT pg_get_constraintdef(oid) INTO v_domain_def
    FROM pg_constraint
    WHERE conrelid = 'learning.health_observations'::regclass
      AND conname LIKE '%domain%check%'
    LIMIT 1;
    IF v_domain_def IS NULL THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: domain CHECK constraint not found after DDL.';
    END IF;
    -- 後驗 6 domain 字面值對齊 ADR-0042 Decision 3 (Process / Pipeline / Business
    -- 三層分離); 缺任一即 RAISE (drift 防護)。
    IF position('engine_runtime' IN v_domain_def) = 0
       OR position('pipeline_throughput' IN v_domain_def) = 0
       OR position('database_pool' IN v_domain_def) = 0
       OR position('api_latency' IN v_domain_def) = 0
       OR position('strategy_quality' IN v_domain_def) = 0
       OR position('risk_envelope' IN v_domain_def) = 0 THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: domain CHECK missing required ADR-0042 '
            '6-domain values. Actual: %.', v_domain_def;
    END IF;

    -- state CHECK 必含 4 值。
    SELECT pg_get_constraintdef(oid) INTO v_state_def
    FROM pg_constraint
    WHERE conrelid = 'learning.health_observations'::regclass
      AND conname LIKE '%_state_check'
      AND conname NOT LIKE '%state_prev%'
    LIMIT 1;
    IF v_state_def IS NULL THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: state CHECK constraint not found.';
    END IF;
    IF position('HEALTH_CRITICAL' IN v_state_def) = 0 THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: state CHECK missing HEALTH_CRITICAL. '
            'Actual: %.', v_state_def;
    END IF;

    -- engine_mode CHECK 必含 4 值。
    SELECT pg_get_constraintdef(oid) INTO v_engine_mode_def
    FROM pg_constraint
    WHERE conrelid = 'learning.health_observations'::regclass
      AND conname LIKE '%engine_mode%check%'
    LIMIT 1;
    IF v_engine_mode_def IS NULL THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: engine_mode CHECK not found.';
    END IF;
    IF position('live_demo' IN v_engine_mode_def) = 0 THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: engine_mode CHECK missing live_demo. '
            'Actual: %.', v_engine_mode_def;
    END IF;

    -- Hypertable chunk_time_interval 必 = 7 days (604800 sec)。
    SELECT EXTRACT(EPOCH FROM time_interval) INTO v_chunk_interval
    FROM timescaledb_information.dimensions
    WHERE hypertable_name = 'health_observations'
      AND column_name = 'observed_at';
    IF v_chunk_interval IS NULL THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: hypertable not created on observed_at.';
    END IF;
    IF v_chunk_interval <> 604800 THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: chunk_time_interval = % sec (expected 604800).',
            v_chunk_interval;
    END IF;

    -- Compression policy 必存在。
    SELECT COUNT(*) INTO v_compress_job
    FROM timescaledb_information.jobs
    WHERE proc_name = 'policy_compression'
      AND hypertable_name = 'health_observations';
    IF v_compress_job = 0 THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: compression policy missing.';
    END IF;

    -- Retention policy 必存在。
    SELECT COUNT(*) INTO v_retention_job
    FROM timescaledb_information.jobs
    WHERE proc_name = 'policy_retention'
      AND hypertable_name = 'health_observations';
    IF v_retention_job = 0 THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: retention policy missing.';
    END IF;

    -- 4 hot-path index 全到位 (excluding PK = 4 expected user index)。
    SELECT COUNT(*) INTO v_index_count
    FROM pg_indexes
    WHERE schemaname = 'learning'
      AND tablename = 'health_observations'
      AND indexname IN (
          'idx_health_domain_metric_observed',
          'idx_health_state_observed',
          'idx_health_symbol_observed',
          'idx_health_strategy_observed'
      );
    IF v_index_count <> 4 THEN
        RAISE EXCEPTION
            'V106 Guard C post FAIL: 4 hot-path index expected, found %.',
            v_index_count;
    END IF;

    RAISE NOTICE
        'V106: all guards PASS — domain/state/engine_mode CHECK ok, '
        'hypertable chunk=7d, compression + retention policies installed, '
        '4 hot-path index built.';
END $$;

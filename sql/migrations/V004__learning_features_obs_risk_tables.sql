-- ============================================================
-- Phase 0a DDL — 已執行 / Executed
-- 設計來源：融合方案 v0.5 + DB 架構 V1
-- Source: Unified Work Plan v0.5 + DB Architecture V1
-- 執行日期：2026-04-11 · FIX-35: DRAFT 標記移除
-- Execution date: 2026-04-11 · FIX-35: DRAFT marker removed
-- ============================================================
--
-- V004: learning.* + features.* + observability.* + risk.* Tables
--
-- 表清單 / Table List:
--   learning.rl_transitions           — RL 轉換 / RL state transitions
--   learning.promotion_pipeline       — 漸進放權管線 / Promotion pipeline
--   learning.ml_parameter_suggestions — ML 參數建議 / ML param suggestions
--   learning.model_registry           — 模型註冊 / Model registry
--   learning.bayesian_posteriors      — Thompson Sampling 後驗 / TS posteriors
--   learning.cpcv_results             — CPCV 結果 / CPCV results
--   learning.james_stein_estimates    — James-Stein 估計 / JS estimates
--   learning.symbol_clusters          — 幣種聚類 / Symbol clusters
--   learning.teacher_directives       — Claude Teacher 指令 / Claude directives
--   learning.directive_executions     — 指令執行追蹤 / Directive execution tracking
--   features.online_latest            — 在線最新特徵 / Online latest features
--   features.versions                 — 特徵版本管理 / Feature versioning
--   observability.scorer_predictions  — Scorer 推理結果 / Scorer predictions
--   observability.model_performance   — 模型性能 Rolling / Model perf rolling
--   observability.drift_events        — 漂移事件 / Drift events
--   observability.feature_baselines   — 特徵基線 / Feature baselines
--   observability.data_quality_events — 數據質量事件 / Data quality events
--   risk.black_swan_events            — 黑天鵝事件 / Black swan events
--   risk.black_swan_votes             — 黑天鵝投票 / Black swan votes
--   risk.correlation_pairs            — 相關性長表 / Correlation pairs (long table)
-- ============================================================


-- ================================================================
--                    learning.* Tables
-- ================================================================

-- ==========================================================
-- learning.rl_transitions — RL 狀態轉換
-- RL state transitions for PyTorch training
-- Source: DB-1 · hypertable 7d chunks
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.rl_transitions (
    ts              TIMESTAMPTZ NOT NULL,
    episode_id      TEXT        NOT NULL,
    step_index      INT         NOT NULL,
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    state_vector    REAL[],                 -- 扁平化特徵向量 ~120 dims / flat feature vector
    action          INT,                    -- 7 discrete actions
    immediate_reward REAL,
    shaped_reward   REAL,
    next_context_id TEXT,
    next_state_vector REAL[],
    done            BOOLEAN     DEFAULT FALSE,
    details         JSONB,
    PRIMARY KEY (episode_id, step_index, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('learning.rl_transitions', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- learning.promotion_pipeline — 四階段漸進放權
-- 4-stage progressive delegation pipeline
-- Source: DB-1 · 普通表 / regular table
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.promotion_pipeline (
    pipeline_id     SERIAL      PRIMARY KEY,
    strategy_name   TEXT        NOT NULL,
    model_name      TEXT,
    model_version   TEXT,
    current_stage   TEXT        NOT NULL DEFAULT 'LEARNING',
    -- LEARNING → PAPER_SHADOW → DEMO_ACTIVE → LIVE_PENDING → LIVE_ACTIVE

    -- Stage 1: Paper 指標 / Paper metrics
    paper_start_ts      TIMESTAMPTZ,
    paper_trades        INT         DEFAULT 0,
    paper_win_rate      REAL,
    paper_net_pnl_pct   REAL,
    paper_max_drawdown_pct REAL,
    paper_sharpe        REAL,

    -- Stage 2: Demo 指標 / Demo metrics
    demo_start_ts       TIMESTAMPTZ,
    demo_trades         INT         DEFAULT 0,
    demo_win_rate       REAL,
    demo_net_pnl_pct    REAL,
    demo_max_drawdown_pct REAL,
    demo_sharpe         REAL,
    demo_avg_slippage_bps REAL,
    demo_api_reliability REAL,

    -- Stage 3: Live 審批 / Live approval
    evaluation_report   JSONB,      -- Claude AI 生成的評估報告 / Claude AI evaluation report
    operator_decision   TEXT,        -- APPROVED/REJECTED/EXTEND
    approved_capital_pct REAL,
    approved_max_leverage REAL,

    created_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================================
-- learning.ml_parameter_suggestions — ML → 策略參數建議
-- ML model parameter suggestions for governance approval
-- Source: DB-1
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.ml_parameter_suggestions (
    suggestion_id   SERIAL      PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    strategy_name   TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    regime          TEXT,
    model_name      TEXT        NOT NULL,
    model_version   TEXT,
    suggested_params JSONB      NOT NULL,   -- 建議的參數 / suggested params
    current_params  JSONB,                  -- 當前參數 / current params
    expected_improvement JSONB,             -- 預期改善 / expected improvement
    governance_status TEXT      DEFAULT 'PENDING',  -- PENDING/APPROVED/REJECTED
    approved_by     TEXT,                   -- operator/auto
    applied_ts      TIMESTAMPTZ
);

-- ==========================================================
-- learning.model_registry — 模型版本管理
-- Model version registry (V1 gap #3)
-- Source: DB-1 + v0.5 §1.3 新增欄位
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.model_registry (
    model_id        SERIAL      PRIMARY KEY,
    model_name      TEXT        NOT NULL,
    version         TEXT        NOT NULL,
    created_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    architecture    TEXT,                   -- 'lightgbm_scorer_v1' / 'ppo_trading_v2' / etc.
    training_data_start TIMESTAMPTZ,
    training_data_end   TIMESTAMPTZ,
    feature_version TEXT,                   -- 邏輯 FK → features.versions
    hyperparams     JSONB,
    metrics         JSONB,                  -- {val_sharpe, val_accuracy, test_sharpe, brier_score, ...}
    artifact_path   TEXT,                   -- /data/openclaw/models/{model_id}/
    is_active       BOOLEAN     DEFAULT FALSE,
    promoted_to_stage TEXT,                 -- NULL/PAPER/DEMO/LIVE
    -- v0.5 §1.3 新增 / v0.5 §1.3 additions
    calibration_params JSONB,               -- isotonic regression 參數（非 Platt）/ isotonic regression params
    onnx_artifact_path TEXT,                -- ONNX 模型路徑 / ONNX model path
    UNIQUE(model_name, version)
);

-- ==========================================================
-- learning.bayesian_posteriors — Thompson Sampling NIG 後驗
-- Thompson Sampling Normal-InverseGamma posteriors (UPSERT table)
-- Source: v0.5 §1.2 新增表
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.bayesian_posteriors (
    strategy_name   TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    regime          TEXT        NOT NULL,
    -- NIG 四參數 / NIG four parameters
    mu              REAL        NOT NULL,   -- 均值估計 / mean estimate
    lambda          REAL        NOT NULL,   -- 先驗強度 / prior strength
    alpha           REAL        NOT NULL,   -- shape（>2 確保方差均值存在）/ shape
    beta            REAL        NOT NULL,   -- scale
    -- 統計 / Statistics
    n_trials        INT         NOT NULL DEFAULT 0,
    last_updated_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (strategy_name, symbol, regime)
);

-- ==========================================================
-- learning.cpcv_results — CPCV 結果
-- Combinatorial Purged Cross-Validation results
-- Source: v0.5 §1.2 新增表 · 4-fold（審計 QA2-6）
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.cpcv_results (
    result_id       SERIAL      PRIMARY KEY,
    model_name      TEXT        NOT NULL,
    model_version   TEXT        NOT NULL,
    created_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    n_folds         INT         NOT NULL DEFAULT 4,  -- 4-fold（審計 QA2-6）
    embargo_hours   REAL,                   -- 按策略分級 / per-strategy embargo
    strategy_type   TEXT,                   -- trend/reversion/arb/grid（決定 embargo）
    -- per-fold OOS 指標 / per-fold OOS metrics
    fold_metrics    JSONB       NOT NULL,   -- [{fold_id, sharpe, accuracy, brier, ...}, ...]
    -- 聚合指標 / Aggregated metrics
    mean_sharpe     REAL,
    std_sharpe      REAL,
    mean_accuracy   REAL,
    power_estimate  REAL,                   -- 統計功效估計 / statistical power estimate
    passed          BOOLEAN     DEFAULT FALSE
);

-- ==========================================================
-- learning.james_stein_estimates — James-Stein 跨幣部分池化（UPSERT）
-- James-Stein cross-symbol partial pooling (UPSERT table)
-- Source: v0.5 §1.2 新增表 · per-parameter 獨立 shrinkage（審計 QA2-5）
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.james_stein_estimates (
    strategy_name   TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    param_name      TEXT        NOT NULL,   -- per-parameter（審計 QA2-5）
    -- JS 估計 / JS estimates
    raw_estimate    REAL        NOT NULL,
    shrunk_estimate REAL        NOT NULL,
    shrinkage_factor REAL       NOT NULL,   -- B_j for this param / 此參數的收縮因子
    grand_mean      REAL,                   -- 全域均值 / global mean
    cluster_id      INT,                    -- 邏輯 FK → symbol_clusters
    n_observations  INT         NOT NULL DEFAULT 0,
    last_updated_ts TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (strategy_name, symbol, param_name)
);

-- ==========================================================
-- learning.symbol_clusters — 幣種聚類（k-means）
-- Symbol clustering (k-means)
-- Source: v0.5 §1.2 新增表
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.symbol_clusters (
    cluster_id      SERIAL      PRIMARY KEY,
    created_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    k               INT         NOT NULL,   -- 聚類數 / number of clusters
    method          TEXT        DEFAULT 'kmeans',
    -- 聚類結果 / Cluster assignments
    assignments     JSONB       NOT NULL,   -- {symbol: cluster_label, ...}
    centroids       JSONB,                  -- cluster center feature vectors
    silhouette_score REAL,
    is_active       BOOLEAN     DEFAULT TRUE
);

-- ==========================================================
-- learning.teacher_directives — Claude Teacher 原始指令（audit trail）
-- Claude Teacher raw directives (audit trail, low frequency ~0.14/day)
-- Source: v0.5 §1.2 · 普通表（審計 QA-2：日均 0.14 行不該是 hypertable）
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.teacher_directives (
    directive_id    SERIAL      PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    hypothesis_id   TEXT,                   -- 關聯 ExperimentLedger hypothesis
    directive_type  TEXT        NOT NULL,   -- experiment/parameter_review/risk_assessment
    content         JSONB       NOT NULL,   -- Claude 原始結構化輸出 / raw Claude structured output
    ai_model_used   TEXT,
    cost_usd        NUMERIC(10,6) DEFAULT 0,
    status          TEXT        DEFAULT 'PENDING'  -- PENDING/EXECUTED/REJECTED/EXPIRED
);

-- ==========================================================
-- learning.directive_executions — 指令執行追蹤
-- Directive execution tracking
-- Source: v0.5 §1.2 新增表
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.directive_executions (
    execution_id    SERIAL      PRIMARY KEY,
    directive_id    INT         NOT NULL,   -- FK → teacher_directives
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    action_taken    TEXT        NOT NULL,   -- 執行動作 / action taken
    result          JSONB,                  -- 執行結果 / execution result
    success         BOOLEAN     DEFAULT TRUE,
    CONSTRAINT fk_directive FOREIGN KEY (directive_id) REFERENCES learning.teacher_directives(directive_id)
);


-- ================================================================
--                    features.* Tables
-- ================================================================

-- ==========================================================
-- features.online_latest — 在線最新特徵 cache（UPSERT）
-- Online latest feature cache (UPSERT per symbol x timeframe)
-- Source: DB-1 + v0.5 §10.4 · 替代 market.indicators 歷史
-- ==========================================================
CREATE TABLE IF NOT EXISTS features.online_latest (
    symbol          TEXT        NOT NULL,
    timeframe       TEXT        NOT NULL,
    updated_ts_ms   BIGINT      NOT NULL,
    feature_vector  REAL[],                 -- ~120 dims，與 RL state_vector 同定義
    feature_version TEXT,                   -- 邏輯 FK → features.versions
    -- v0.5 §1.3 新增 / v0.5 §1.3 addition
    foundation_model_features REAL[],       -- 時序基礎模型特徵（DL-3）/ foundation model features
    PRIMARY KEY (symbol, timeframe)
);

-- ==========================================================
-- features.versions — 特徵版本管理
-- Feature version management
-- Source: DB-1
-- ==========================================================
CREATE TABLE IF NOT EXISTS features.versions (
    version         TEXT        PRIMARY KEY,
    created_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    description     TEXT,
    -- 完整指標配置 / Complete indicator config
    indicator_config JSONB,                 -- 所有 16 指標的精確參數 / all 16 indicator exact params
    -- 歸一化參數 / Normalization params
    normalization_params JSONB,             -- per-feature mean/std/min/max
    is_active       BOOLEAN     DEFAULT FALSE
);


-- ================================================================
--                    observability.* Tables
-- ================================================================

-- ==========================================================
-- observability.scorer_predictions — Scorer 推理結果
-- Scorer inference results (for monitoring, not training)
-- Source: v0.5 §1.2 新增表 · hypertable 1d chunks
-- ==========================================================
CREATE TABLE IF NOT EXISTS observability.scorer_predictions (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    strategy_name   TEXT        NOT NULL,
    model_name      TEXT        NOT NULL,
    model_version   TEXT,
    prediction      REAL        NOT NULL,   -- raw model output
    calibrated_prob REAL,                   -- isotonic-calibrated probability
    confidence      REAL,                   -- 模型信心 / model confidence
    context_id      TEXT,                   -- 邏輯 FK → decision_context_snapshots
    was_executed    BOOLEAN,                -- 是否實際執行 / was trade actually executed
    details         JSONB,
    PRIMARY KEY (symbol, strategy_name, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('observability.scorer_predictions', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- observability.model_performance — Rolling 模型性能（Brier/AUC）
-- Rolling model performance metrics
-- Source: v0.5 §1.2 新增表 · hypertable 7d chunks（日均 50 行，審計修正）
-- ==========================================================
CREATE TABLE IF NOT EXISTS observability.model_performance (
    ts              TIMESTAMPTZ NOT NULL,
    model_name      TEXT        NOT NULL,
    model_version   TEXT        NOT NULL,
    window_size     TEXT,                   -- '7d'/'30d'/'90d'
    -- 性能指標 / Performance metrics
    brier_score     REAL,
    auc_roc         REAL,
    accuracy        REAL,
    precision_val   REAL,       -- 避免與 SQL 關鍵字衝突 / avoid SQL keyword
    recall_val      REAL,
    f1_score        REAL,
    calibration_error REAL,                 -- ECE (Expected Calibration Error)
    n_predictions   INT,
    details         JSONB,
    PRIMARY KEY (model_name, model_version, window_size, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('observability.model_performance', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- observability.drift_events — 漂移事件（PSI + AV + ADWIN）
-- Drift detection events (PSI + Adversarial Validation + ADWIN)
-- Source: v0.5 §1.2 新增表 · hypertable 1d chunks
-- ==========================================================
CREATE TABLE IF NOT EXISTS observability.drift_events (
    ts              TIMESTAMPTZ NOT NULL,
    event_id        TEXT        NOT NULL,
    drift_type      TEXT        NOT NULL,   -- PSI/ADVERSARIAL_VALIDATION/ADWIN
    severity        TEXT        NOT NULL,   -- INFO/WARNING/ALERT
    symbol          TEXT,
    feature_name    TEXT,                   -- 漂移的特徵 / drifted feature (for PSI)
    metric_value    REAL,                   -- PSI 值 / AV AUC 值 / ADWIN change point
    threshold       REAL,                   -- 觸發閾值 / trigger threshold
    details         JSONB,                  -- 完整診斷 / full diagnostics
    PRIMARY KEY (event_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('observability.drift_events', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- observability.feature_baselines — 特徵分佈歷史基線（UPSERT + 版本管理）
-- Feature distribution baselines (UPSERT + version management)
-- Source: v0.5 §1.8 · 普通表 · valid_from/valid_until 版本（審計 QA-10）
-- ==========================================================
CREATE TABLE IF NOT EXISTS observability.feature_baselines (
    baseline_id     SERIAL      PRIMARY KEY,
    symbol          TEXT        NOT NULL,
    feature_name    TEXT        NOT NULL,
    bin_edges       REAL[]      NOT NULL,   -- 直方圖 bin 邊界 / histogram bin edges
    bin_counts      INT[]       NOT NULL,   -- 各 bin 計數 / per-bin counts
    valid_from      TIMESTAMPTZ NOT NULL,   -- 生效時間 / effective from
    valid_until     TIMESTAMPTZ,            -- 失效時間（NULL=當前有效）/ expires (NULL=current)
    created_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(symbol, feature_name, valid_from)
);

-- ==========================================================
-- observability.data_quality_events — 數據質量事件
-- Data quality monitoring events
-- Source: DB-1 (quality.data_quality_events) · hypertable 1d chunks
-- ==========================================================
CREATE TABLE IF NOT EXISTS observability.data_quality_events (
    ts              TIMESTAMPTZ NOT NULL,
    event_id        TEXT        NOT NULL,
    check_type      TEXT        NOT NULL,   -- GAP/ANOMALY/COMPLETENESS/LATENCY/STALE
    symbol          TEXT,
    timeframe       TEXT,
    severity        TEXT        NOT NULL,   -- INFO/WARNING/CRITICAL
    description     TEXT,
    details         JSONB,
    PRIMARY KEY (event_id, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('observability.data_quality_events', 'ts',
        chunk_time_interval => INTERVAL '1 day',
        if_not_exists => TRUE);
END IF;
END $$;


-- ================================================================
--                    risk.* Tables
-- ================================================================

-- ==========================================================
-- risk.black_swan_events — 黑天鵝事件（永久記錄）
-- Black swan event records (permanent, regular table)
-- Source: v0.5 §1.2 · 普通表（審計 QA-2/QA-7：日均 0.01 行不該是 hypertable）
-- ==========================================================
CREATE TABLE IF NOT EXISTS risk.black_swan_events (
    event_id        SERIAL      PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT,                   -- NULL = market-wide
    event_type      TEXT        NOT NULL,   -- FLASH_CRASH/SPIKE/CORRELATION_BREAK/VOLUME_ANOMALY/RATE_ANOMALY
    severity        TEXT        NOT NULL,   -- WARNING/CRITICAL/EXTREME
    -- 觸發信號 / Trigger signals
    mad_score       REAL,                   -- MAD 離群分數 / MAD outlier score
    corr_break      BOOLEAN,               -- 相關性斷裂 / correlation break
    volume_anomaly  BOOLEAN,               -- 量異常 / volume anomaly
    rate_anomaly    BOOLEAN,               -- 速度異常 / rate anomaly
    votes_for       INT         DEFAULT 0,  -- 投票贊成數 / votes for
    votes_total     INT         DEFAULT 0,  -- 總投票數 / total votes
    -- 影響 / Impact
    price_change_pct REAL,
    duration_seconds INT,
    description     TEXT,
    details         JSONB,                  -- 完整診斷 / full diagnostics
    resolved_ts     TIMESTAMPTZ             -- 事件結束時間 / event end time
);

-- ==========================================================
-- risk.black_swan_votes — 黑天鵝投票記錄
-- Black swan detection votes (4 signals)
-- Source: v0.5 §1.2 新增表 · hypertable 7d chunks
-- ==========================================================
CREATE TABLE IF NOT EXISTS risk.black_swan_votes (
    ts              TIMESTAMPTZ NOT NULL,
    symbol          TEXT        NOT NULL,
    signal_name     TEXT        NOT NULL,   -- MAD/CORRELATION/VOLUME/RATE
    vote            BOOLEAN     NOT NULL,   -- TRUE=異常 / TRUE=anomaly detected
    metric_value    REAL,                   -- 信號值 / signal value
    threshold       REAL,                   -- 觸發閾值 / trigger threshold
    details         JSONB,
    PRIMARY KEY (symbol, signal_name, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('risk.black_swan_votes', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ==========================================================
-- risk.correlation_pairs — 相關性長表（替代 REAL[2500] 矩陣）
-- Correlation pairs (long table, replaces REAL[2500] matrix)
-- Source: v0.5 §8.3 QA2-10 修正 · 長表設計
-- ==========================================================
CREATE TABLE IF NOT EXISTS risk.correlation_pairs (
    ts              TIMESTAMPTZ NOT NULL,
    symbol_a        TEXT        NOT NULL,
    symbol_b        TEXT        NOT NULL,
    correlation     REAL        NOT NULL,   -- Pearson 相關係數 / Pearson r
    method          TEXT        DEFAULT 'pearson',
    "window"        TEXT,                   -- 計算窗口 / calculation window (e.g. '30d') — quoted: SQL reserved word
    PRIMARY KEY (symbol_a, symbol_b, ts)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('risk.correlation_pairs', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

-- ============================================================
-- 驗證 / Verification
-- ============================================================
-- SELECT schemaname, tablename FROM pg_tables
-- WHERE schemaname IN ('learning','features','observability','risk')
-- ORDER BY schemaname, tablename;
--
-- 預期:
--   learning (10): bayesian_posteriors, cpcv_results, directive_executions,
--     james_stein_estimates, ml_parameter_suggestions, model_registry,
--     promotion_pipeline, rl_transitions, symbol_clusters, teacher_directives
--   features (2): online_latest, versions
--   observability (5): data_quality_events, drift_events, feature_baselines,
--     model_performance, scorer_predictions
--   risk (3): black_swan_events, black_swan_votes, correlation_pairs

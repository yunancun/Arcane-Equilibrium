-- ============================================================
-- EXIT-FEATURES-TABLE-1 — DUAL-TRACK-EXIT-1 Track P/L feature labels
-- DUAL-TRACK-EXIT-1 Track P/L 特徵標籤（退場時寫入）
-- Created 2026-04-18 per docs/worklogs/2026-04-18-2--exit_features_table_design.md
--
-- Filename uses V999 placeholder — operator will renumber to the next available
-- V0NN slot when merging (current head: V017). Keep placeholder comment below
-- updated if renumbered.
-- 檔名使用 V999 佔位，operator 合併時按當前序列（目前最新 V017）重新編號為 V0NN。
--
-- Purpose / 用途：
--   learning.exit_features 持久化每筆退場的 7 維 Track P/L 特徵（peak/giveback/
--   ROC/atr_pct/time_since_peak/entry_age/est_net_bps）+ 退場元數據
--   （source/trigger/realized_net_bps）+ schema provenance（version/hash）。
--
--   與 learning.decision_features（entry-time snapshot）配對：
--     decision_features.context_id  ←→  exit_features.context_id
--   以此對齊 entry 與 exit 兩個維度的 ML 訓練資料。
--
--   Writer: rust/openclaw_engine/src/database/exit_feature_writer.rs
--   Producer: paper_state close path（Phase 1a 軌道 1 接線）
-- ============================================================

CREATE TABLE IF NOT EXISTS learning.exit_features (
    -- Identity / 身份
    context_id      text                     NOT NULL,   -- 與 decision_features.context_id 對齊
    ts              timestamp with time zone NOT NULL,   -- exit 時刻
    engine_mode     text                     NOT NULL,   -- 'paper' | 'demo' | 'live_demo' | 'live'
    strategy_name   text                     NOT NULL,
    symbol          text                     NOT NULL,
    side            smallint                 NOT NULL,   -- +1 long / -1 short

    -- 7-dim Track P features (all nullable for forward compatibility)
    -- 7 維 Track P 特徵（全可空，便於 schema 演進）
    est_net_bps         real,                            -- 估計 net edge（bps，JS edge+cost_gate 推算）
    peak_pnl_pct        real,                            -- 自開倉以來 max favorable pnl %（PaperPosition.max_favorable_pnl_pct）
    atr_pct             real,                            -- 當時 ATR / price（price_tracker.atr_pct）
    giveback_atr_norm   real,                            -- (peak - current) / ATR，歸一化回吐幅度
    time_since_peak_ms  bigint,                          -- 自 peak 達到以來的毫秒數
    price_roc_short    real,                             -- 短窗（默認 300ms）price rate-of-change
    entry_age_secs      real,                            -- 自 entry 以來的秒數

    -- Exit meta / 退場元數據
    exit_source         text,                            -- 'Physical' | 'Hybrid' | 'ML-shadow' | 'TimeStop' | 'HardStop' ...
    exit_trigger_rule   text,                            -- 具體觸發規則（'PHYS-LOCK' / 'COST-EDGE' 等）
    realized_net_bps    real,                            -- 真正成交 net bps（ex-post label vs est_net_bps）

    -- Provenance / 來源可追溯
    feature_schema_version text NOT NULL DEFAULT 'v1.0',
    feature_schema_hash    text NOT NULL,                -- 欄位結構 hash（drift 檢測用）

    PRIMARY KEY (context_id, ts)   -- TimescaleDB hypertable 要求 PK 含 partition key
);

-- Indexes / 索引
CREATE INDEX IF NOT EXISTS idx_exit_features_strategy_mode_ts
    ON learning.exit_features (strategy_name, engine_mode, ts DESC);
CREATE INDEX IF NOT EXISTS idx_exit_features_ts
    ON learning.exit_features (ts DESC);
CREATE INDEX IF NOT EXISTS idx_exit_features_symbol_ts
    ON learning.exit_features (symbol, ts DESC);

-- TimescaleDB hypertable（與 decision_features 對稱，7d chunk）
-- create_hypertable is idempotent via if_not_exists. Guarded on extension presence
-- so non-Timescale environments still apply the base table.
-- 以 if_not_exists 冪等；extension 缺席時回退為普通表。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('learning.exit_features', 'ts',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE);
    END IF;
END
$$;

COMMENT ON TABLE learning.exit_features IS
    'DUAL-TRACK-EXIT-1 Track P/L feature labels. One row per position exit written by Rust paper_state close path via exit_feature_writer.';

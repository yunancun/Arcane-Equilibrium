-- ============================================================
-- V017: Edge Predictor Tables — Realized Edge Predictor (EDGE-P3-1)
-- 真實 edge 預測器表 — 替代 James-Stein shrinkage
--
-- Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4
-- Per-strategy quantile LightGBM (q10/q50/q90) replacing shrunk_bps.
-- 每策略分位 LightGBM 模型，取代 shrunk_bps 收縮估計。
--
-- Reality-alignment (v1.4 three-role verdict, R1-R5):
--   R1: Uses existing trading.decision_context_snapshots (not learning.*)
--   R2: trading.fills gets NEW entry_context_id column (not reuse context_id —
--       emit_close_fill creates fresh close-time id via make_context_id)
--   R3: Audit via observability.engine_events (event_type prefix)
--   R4: ON CONFLICT on hypertable must use composite PK (context_id, ts)
--   R5: disagreed BOOLEAN plain (not GENERATED STORED — TimescaleDB 2.x
--       compression incompatible); Rust writer computes at INSERT time.
--
-- CRITICAL sequencing: V017 must co-land with Rust PaperPosition.entry_context_id
-- + emit_close_fill signature change. Without Rust threading, entry_context_id
-- column stays 100% NULL → silent label loss.
-- 關鍵排序：V017 必須與 Rust 端 entry_context_id 串線同窗口落地，否則新列
-- 100% NULL 等同靜默 label 丟失。
-- ============================================================

-- ==========================================================
-- learning.decision_features — Feature store, plain table PK (context_id)
-- 特徵存儲；非 hypertable；單鍵 PK 便於 ON CONFLICT (context_id)
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.decision_features (
    context_id              TEXT         PRIMARY KEY,
    ts                      TIMESTAMPTZ  NOT NULL,
    engine_mode             TEXT         NOT NULL,
    strategy_name           TEXT         NOT NULL,
    symbol                  TEXT         NOT NULL,
    side                    SMALLINT     NOT NULL,           -- +1 long / -1 short
    feature_schema_version  TEXT         NOT NULL,
    feature_schema_hash     TEXT         NOT NULL,
    feature_definition_hash TEXT         NOT NULL,           -- C3: per-feature semantic hash
    features_jsonb          JSONB        NOT NULL,
    label_net_edge_bps      DOUBLE PRECISION,                -- NULL until close fill回填
    label_close_tag         TEXT,
    label_split_flag        BOOLEAN      NOT NULL DEFAULT FALSE,  -- C5: qty-weighted blend 標識
    label_filled_at         TIMESTAMPTZ
);

-- 主要訓練查詢索引（strategy_name + engine_mode + ts 範圍掃描）
CREATE INDEX IF NOT EXISTS idx_decision_features_strategy_mode_ts
    ON learning.decision_features (strategy_name, engine_mode, ts DESC);

-- 時間倒序掃描（最近 N 筆）
CREATE INDEX IF NOT EXISTS idx_decision_features_ts
    ON learning.decision_features (ts DESC);

-- ML-MIT 專用：只訓練已回填 label 的行（過濾 NULL 加速訓練 SQL）
CREATE INDEX IF NOT EXISTS idx_decision_features_labeled
    ON learning.decision_features (strategy_name, engine_mode, ts DESC)
    WHERE label_net_edge_bps IS NOT NULL;

COMMENT ON TABLE learning.decision_features IS
    'Per-decision feature row for edge predictor training. PK=context_id (plain). Label 回填於 close fill 後。';
COMMENT ON COLUMN learning.decision_features.side IS
    '+1=long, -1=short (SMALLINT for LGBM 原生輸入)';
COMMENT ON COLUMN learning.decision_features.label_split_flag IS
    'TRUE 當 close fill 為 qty-weighted blend of >1 partial close (§4.2)';

-- ==========================================================
-- learning.decision_shadow_fills — ε-greedy 合成 fill (F4 + U3)
-- Paper-only（DB-level CHECK）；永不入 label 回填（訓練集隔離）
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.decision_shadow_fills (
    shadow_id              BIGSERIAL       PRIMARY KEY,
    context_id             TEXT            NOT NULL,         -- 原 decision context_id
    ts                     TIMESTAMPTZ     NOT NULL,
    engine_mode            TEXT            NOT NULL CHECK (engine_mode = 'paper'),
    strategy_name          TEXT            NOT NULL,
    symbol                 TEXT            NOT NULL,
    side                   SMALLINT        NOT NULL,
    features_jsonb         JSONB           NOT NULL,
    predicted_q10          DOUBLE PRECISION,
    predicted_q50          DOUBLE PRECISION,
    predicted_q90          DOUBLE PRECISION,
    cost_bps_at_open       DOUBLE PRECISION,
    synthetic_exit_price   DOUBLE PRECISION,                 -- 某 exit rule 確定後填入
    synthetic_hold_ms      BIGINT,
    synthetic_net_edge_bps DOUBLE PRECISION,                 -- 純觀測，不入 label
    close_tag              TEXT            NOT NULL DEFAULT 'shadow_fill:epsilon_greedy'
);

CREATE INDEX IF NOT EXISTS idx_shadow_fills_strategy_ts
    ON learning.decision_shadow_fills (strategy_name, engine_mode, ts DESC);

COMMENT ON TABLE learning.decision_shadow_fills IS
    'ε-greedy exploration synthetic fills (paper-only). 永久排除於 learning.decision_features label 回填（§5.1 WHERE）。';

-- ==========================================================
-- trading.decision_context_snapshots — ALTER 加 7 列（C16 + R5）
-- 既有 hypertable（V003:40，PK 複合 (context_id, ts) 見 V003:91）
-- ==========================================================
ALTER TABLE trading.decision_context_snapshots
    ADD COLUMN IF NOT EXISTS predicted_q10       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS predicted_q50       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS predicted_q90       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS predictor_decision  TEXT,
    ADD COLUMN IF NOT EXISTS shrinkage_decision  TEXT,
    ADD COLUMN IF NOT EXISTS disagreed           BOOLEAN,
    ADD COLUMN IF NOT EXISTS predict_latency_us  INTEGER;

COMMENT ON COLUMN trading.decision_context_snapshots.predictor_decision IS
    'accept|reject_cost|reject_q10|fallback_no_model|fallback_error|fallback_schema_mismatch|shadow_fill';
COMMENT ON COLUMN trading.decision_context_snapshots.shrinkage_decision IS
    'accept|reject (既有 James-Stein shrinkage gate)';
COMMENT ON COLUMN trading.decision_context_snapshots.disagreed IS
    'R5: plain BOOLEAN (TimescaleDB 2.x compression 不支援 GENERATED STORED); Rust context_writer 寫入前計算 COALESCE 語義（兩邊都 NULL→FALSE；任一邊 NULL→另一邊驅動；兩邊都有→字串相等比較）';
COMMENT ON COLUMN trading.decision_context_snapshots.predict_latency_us IS
    'Edge predictor inference microseconds (tract-onnx)';

-- 熱路徑索引（predicted_q50 查詢 + NULL 過濾）
-- NOTE: spec §5.1 建議 CREATE INDEX CONCURRENTLY 避免擋 tick-path INSERT，
-- 但必須在 transaction 外執行。本 migration 走 transactional runner，故用
-- 普通 CREATE INDEX。預測器 rollout 前 decision_context_snapshots 流量低，
-- 短暫 blocking 可接受。若未來 hot-path blocking 成問題，DBA 可手動：
--   DROP INDEX idx_dcs_predicted_q50;
--   CREATE INDEX CONCURRENTLY idx_dcs_predicted_q50
--     ON trading.decision_context_snapshots (predicted_q50)
--     WHERE predicted_q50 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_dcs_predicted_q50
    ON trading.decision_context_snapshots (predicted_q50)
    WHERE predicted_q50 IS NOT NULL;

-- ==========================================================
-- trading.fills — ALTER 加 entry_context_id (R2)
-- 關鍵：NEW 列，不是復用既有 context_id（V003:283）。
-- emit_close_fill 現用 make_context_id(em, symbol, ts_ms) 合成 close-time 新 id，
-- entry_context_id 從 PaperPosition.entry_context_id 透傳，ML 訓練 JOIN 鍵。
-- ==========================================================
ALTER TABLE trading.fills
    ADD COLUMN IF NOT EXISTS entry_context_id TEXT NULL;

COMMENT ON COLUMN trading.fills.entry_context_id IS
    'R2: close fill 所屬 entry 的 context_id（從 PaperPosition.entry_context_id 透傳）。既有 context_id 列為 close event 自身 id（close-time 合成）。兩者並存：ML 訓練 JOIN 用 entry_context_id。';

-- 訓練 JOIN 鍵索引（learning.decision_features.context_id = trading.fills.entry_context_id）
CREATE INDEX IF NOT EXISTS idx_fills_entry_ctx
    ON trading.fills (entry_context_id)
    WHERE entry_context_id IS NOT NULL;

-- ============================================================
-- Verification / 驗證
-- ============================================================
-- SELECT column_name FROM information_schema.columns
--   WHERE table_schema='trading' AND table_name='decision_context_snapshots'
--   AND column_name IN ('predicted_q10','predicted_q50','predicted_q90',
--                       'predictor_decision','shrinkage_decision',
--                       'disagreed','predict_latency_us');
-- Expected: 7 rows
--
-- SELECT column_name FROM information_schema.columns
--   WHERE table_schema='trading' AND table_name='fills'
--   AND column_name='entry_context_id';
-- Expected: 1 row
--
-- SELECT to_regclass('learning.decision_features'),
--        to_regclass('learning.decision_shadow_fills');
-- Expected: 2 non-null

-- ============================================================
-- V016: Learning Feedback Loop — Analyst Pattern Insights
-- 學習反饋閉環 — Analyst 模式洞察持久化
--
-- R-06-v2 Step 2: Analyst → DB → Strategist feedback
-- Analyst produces PatternInsight (winning/losing patterns) which are
-- persisted here. StrategistScheduler reads them when building Ollama
-- prompts so Ollama can recommend params informed by actual trade patterns.
-- R-06-v2 步驟 2：Analyst → DB → Strategist 反饋
-- Analyst 產出 PatternInsight（贏/輸模式），持久化到此表。
-- StrategistScheduler 在構建 Ollama prompt 時讀取，使 AI 推薦有交易模式依據。
--
-- Note: Guardian rejection stats use existing trading.risk_verdicts (Step 3)
--       joined with trading.intents for per-strategy reject_rate.
-- 注意：Guardian 拒絕統計使用已有的 trading.risk_verdicts（步驟 3）
--       與 trading.intents 連接以獲取逐策略拒絕率。
-- ============================================================

-- ==========================================================
-- learning.pattern_insights — Analyst pattern persistence
-- Analyst 模式持久化
-- ==========================================================
CREATE TABLE IF NOT EXISTS learning.pattern_insights (
    id              SERIAL      PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    strategy_name   TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    pattern_type    TEXT        NOT NULL,     -- 'winning' or 'losing' / 贏或輸
    pattern_text    TEXT        NOT NULL,
    confidence      REAL        NOT NULL DEFAULT 0.5,
    observation_count INT       NOT NULL DEFAULT 0,
    engine_mode     TEXT        NOT NULL DEFAULT 'demo'
);

CREATE INDEX IF NOT EXISTS idx_pattern_insights_strategy_ts
    ON learning.pattern_insights (strategy_name, ts DESC);

CREATE INDEX IF NOT EXISTS idx_pattern_insights_engine_mode_ts
    ON learning.pattern_insights (engine_mode, ts DESC);

-- Retention: keep 30 days of insights (older patterns are stale)
-- 保留 30 天的洞察（更早的模式已過時）
-- Manual cleanup: DELETE FROM learning.pattern_insights WHERE ts < now() - interval '30 days';

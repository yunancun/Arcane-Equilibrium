-- ============================================================
-- DRAFT — Phase 0a DDL（尚未執行）
-- DRAFT — Phase 0a DDL (not yet executed)
-- 設計來源：融合方案 v0.5 + DB 架構 V1
-- Source: Unified Work Plan v0.5 + DB Architecture V1
-- 預計執行日期：2026-04-11
-- Planned execution date: 2026-04-11
-- ============================================================
--
-- V001: CREATE 8 Schemas
-- 創建 8 個 Schema（合併 monitoring+quality → observability）
--
-- Schema 結構 / Schema Structure:
--   market       — 市場數據 + 新聞事件（外部世界）/ Market data + news events
--   trading      — 交易 + 決策數據 / Trading + decision data
--   agent        — Agent 通信 + AI 調用 / Agent communication + AI invocations
--   learning     — 學習系統 + 模型管理 + 實驗追蹤 / Learning + model mgmt + experiments
--   features     — 特徵存儲 + 版本管理 / Feature store + versioning
--   observability — 數據質量 + 模型性能 + 漂移監控 / Data quality + model perf + drift
--   risk         — 黑天鵝檢測 + 極端事件記錄 / Black swan + extreme events
--   news         — 新聞 Agent 專用（預留）/ News agent (reserved)
--
-- 注意：optuna schema 由 Optuna RDBStorage 自動創建，此處不建
-- Note: optuna schema is auto-created by Optuna RDBStorage, not created here
-- ============================================================

-- 1. market schema — 市場數據 / Market data
CREATE SCHEMA IF NOT EXISTS market;
COMMENT ON SCHEMA market IS '市場數據：行情/K線/指標/regime/新聞 | Market data: tickers/klines/indicators/regime/news';

-- 2. trading schema — 交易數據 / Trading data
CREATE SCHEMA IF NOT EXISTS trading;
COMMENT ON SCHEMA trading IS '交易+決策數據：context snapshot/signals/intents/orders/fills | Trading + decision data';

-- 3. agent schema — Agent 通信 / Agent communication
CREATE SCHEMA IF NOT EXISTS agent;
COMMENT ON SCHEMA agent IS 'Agent 通信+AI調用+狀態轉換 | Agent messages + AI invocations + state changes';

-- 4. learning schema — 學習系統 / Learning system
CREATE SCHEMA IF NOT EXISTS learning;
COMMENT ON SCHEMA learning IS '學習系統：RL/參數建議/模型管理/實驗/Teacher Directive | Learning: RL/params/models/experiments/teacher';

-- 5. features schema — 特徵存儲 / Feature store
CREATE SCHEMA IF NOT EXISTS features;
COMMENT ON SCHEMA features IS '特徵存儲+版本管理 | Feature store + versioning';

-- 6. observability schema — 監控（合併 monitoring+quality）/ Observability (merged monitoring+quality)
CREATE SCHEMA IF NOT EXISTS observability;
COMMENT ON SCHEMA observability IS '數據質量+模型性能+漂移監控 | Data quality + model performance + drift monitoring';

-- 7. risk schema — 風險 / Risk
CREATE SCHEMA IF NOT EXISTS risk;
COMMENT ON SCHEMA risk IS '黑天鵝檢測+極端事件+相關性 | Black swan detection + extreme events + correlation';

-- 8. news schema — 新聞（預留）/ News (reserved)
CREATE SCHEMA IF NOT EXISTS news;
COMMENT ON SCHEMA news IS '新聞 Agent 專用（預留，目前新聞信號放 market.news_signals）| News agent reserved';

-- ============================================================
-- 驗證 / Verification
-- ============================================================
-- SELECT schema_name FROM information_schema.schemata
-- WHERE schema_name IN ('market','trading','agent','learning','features','observability','risk','news')
-- ORDER BY schema_name;
-- 預期：8 rows

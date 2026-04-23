-- ============================================================
-- V022: Expose engine_mode on Grafana bridge VIEWs
--       在 Grafana 橋接 VIEW 上暴露 engine_mode 欄位
-- ------------------------------------------------------------
-- 背景 / Background
--   V005 建立 public.trade_executions / public.order_events / public.position_snapshots
--   作為 Grafana 的相容橋接 VIEW，但只暴露 legacy `is_paper` boolean。
--   V015 為底表 (trading.fills / trading.orders / trading.position_snapshots)
--   新增 `engine_mode` TEXT 欄位（取值：'paper' / 'demo' / 'live' / 'live_demo'），
--   但 Grafana VIEW 從未同步暴露。結果：Grafana 面板用 is_paper CASE 判斷，
--   只能表達二值，live / live_demo / demo 全被錯誤標記為「Live」或「Paper」。
--
--   更糟的是 `is_paper` 在目前 Rust writer 下實際所有列都寫成 TRUE（歷史成因
--   尚未確認）——因此面板全顯示 "Paper"，儘管底表 engine_mode 分佈正常。
--
-- 本遷移 / This migration
--   1. 重建三個 VIEW，補上 `engine_mode` TEXT 欄位（source-of-truth）。
--   2. 保留 `is_paper` 欄位以向下兼容既有查詢（未改 schema 其他部分）。
--   3. 加上欄位註記說明。
--
-- 設計 / Design
--   - 不改底表；純 VIEW 重建。CREATE OR REPLACE 可保留 permissions。
--   - 欄位順序：在 is_paper 之後新增 engine_mode，避免破壞既有 SELECT * 查詢的
--     位置依賴（雖然 Grafana 面板都用具名列，穩妥起見仍靠後）。
-- ============================================================

-- -------------------------------------------------------
-- trade_executions → trading.fills
-- DROP 後重建（因為 PostgreSQL CREATE OR REPLACE VIEW 不允許改列順序，
-- 無法在既有列中間塞 engine_mode）
-- -------------------------------------------------------
DROP VIEW IF EXISTS public.trade_executions;
CREATE VIEW public.trade_executions AS
SELECT
    ts,
    fill_id AS exec_id,
    order_id,
    symbol,
    side,
    NULL::text AS exec_type,
    qty AS exec_qty,
    price AS exec_price,
    fee,
    fee_currency,
    realized_pnl,
    is_paper,
    engine_mode,
    strategy_name AS strategy,
    details AS metrics
FROM trading.fills;

COMMENT ON VIEW public.trade_executions IS
'Grafana bridge view over trading.fills. engine_mode is the source of truth '
'(paper/demo/live/live_demo); is_paper is retained for backward compatibility but '
'may not reflect the true engine mode.';

-- -------------------------------------------------------
-- order_events → trading.orders
-- -------------------------------------------------------
DROP VIEW IF EXISTS public.order_events;
CREATE VIEW public.order_events AS
SELECT
    ts,
    order_id,
    symbol,
    side,
    order_type,
    qty,
    price,
    status,
    NULL::NUMERIC(20,8) AS filled_qty,
    NULL::NUMERIC(20,8) AS avg_price,
    NULL::NUMERIC(20,8) AS fee,
    category,
    is_paper,
    engine_mode,
    details AS raw_json
FROM trading.orders;

COMMENT ON VIEW public.order_events IS
'Grafana bridge view over trading.orders. engine_mode is the source of truth '
'(paper/demo/live/live_demo); is_paper is retained for backward compatibility.';

-- -------------------------------------------------------
-- position_snapshots → trading.position_snapshots
-- -------------------------------------------------------
DROP VIEW IF EXISTS public.position_snapshots;
CREATE VIEW public.position_snapshots AS
SELECT
    ts,
    symbol,
    side,
    qty AS size,
    entry_price,
    mark_price,
    unrealized_pnl,
    leverage,
    position_value,
    category,
    is_paper,
    engine_mode,
    details AS raw_json
FROM trading.position_snapshots;

COMMENT ON VIEW public.position_snapshots IS
'Grafana bridge view over trading.position_snapshots. engine_mode is the source of truth '
'(paper/demo/live/live_demo); is_paper is retained for backward compatibility.';

-- ============================================================
-- 驗證 / Verification
-- ============================================================
--   SELECT column_name FROM information_schema.columns
--    WHERE table_schema='public' AND table_name='trade_executions' ORDER BY ordinal_position;
--   預期含 engine_mode
--
--   SELECT engine_mode, COUNT(*) FROM public.trade_executions
--    WHERE ts > NOW() - interval '24 hours' GROUP BY engine_mode;
--   預期：live_demo / demo / paper 等多值分布（非單一 paper）

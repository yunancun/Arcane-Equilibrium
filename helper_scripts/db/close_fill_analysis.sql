-- EDGE-P2-1: Close fill source distribution analysis.
-- EDGE-P2-1：平倉成交來源分佈分析。
--
-- Run with: psql -d openclaw -f helper_scripts/db/close_fill_analysis.sql
--
-- After EDGE-P2-1 fix, strategy_name uses prefixed close tags:
--   risk_close:*      — risk evaluator / fast-track / halt-session
--   stop_trigger:*    — StopManager hard/trailing/time stop
--   strategy_close:*  — strategy-driven exit
-- Legacy fills before the fix all used risk_close:* for everything.

-- 1. Close source breakdown by prefix (demo mode)
\echo '=== Close Source Distribution (Demo) ==='
SELECT
  CASE
    WHEN strategy_name LIKE 'strategy_close:%' THEN 'strategy_close'
    WHEN strategy_name LIKE 'risk_close:%'     THEN 'risk_close'
    WHEN strategy_name LIKE 'stop_trigger:%'   THEN 'stop_trigger'
    ELSE 'other'
  END AS close_source,
  COUNT(*) AS cnt,
  ROUND(AVG(realized_pnl)::numeric, 4) AS avg_pnl,
  ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM trading.fills
WHERE engine_mode = 'demo'
  AND (realized_pnl != 0
    OR strategy_name LIKE 'risk_close:%'
    OR strategy_name LIKE 'stop_trigger:%'
    OR strategy_name LIKE 'strategy_close:%')
GROUP BY close_source
ORDER BY cnt DESC;

-- 2. Detailed risk_close reason breakdown
\echo '=== Risk Close Reason Breakdown (Demo) ==='
SELECT
  strategy_name,
  COUNT(*) AS cnt,
  ROUND(AVG(realized_pnl)::numeric, 4) AS avg_pnl,
  ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM trading.fills
WHERE engine_mode = 'demo'
  AND strategy_name LIKE 'risk_close:%'
GROUP BY strategy_name
ORDER BY cnt DESC
LIMIT 20;

-- 3. Strategy close reason breakdown
\echo '=== Strategy Close Reason Breakdown (Demo) ==='
SELECT
  strategy_name,
  COUNT(*) AS cnt,
  ROUND(AVG(realized_pnl)::numeric, 4) AS avg_pnl,
  ROUND(SUM(realized_pnl)::numeric, 2) AS total_pnl
FROM trading.fills
WHERE engine_mode = 'demo'
  AND strategy_name LIKE 'strategy_close:%'
GROUP BY strategy_name
ORDER BY cnt DESC
LIMIT 20;

-- 4. Time series: exits per day by source (last 7 days)
\echo '=== Daily Exit Distribution (Last 7 Days, Demo) ==='
SELECT
  ts::date AS day,
  COUNT(*) FILTER (WHERE strategy_name LIKE 'strategy_close:%') AS strategy_exits,
  COUNT(*) FILTER (WHERE strategy_name LIKE 'risk_close:%') AS risk_exits,
  COUNT(*) FILTER (WHERE strategy_name LIKE 'stop_trigger:%') AS stop_exits,
  COUNT(*) AS total_exits
FROM trading.fills
WHERE engine_mode = 'demo'
  AND ts >= NOW() - INTERVAL '7 days'
  AND (realized_pnl != 0
    OR strategy_name LIKE '%close:%'
    OR strategy_name LIKE 'stop_trigger:%')
GROUP BY day
ORDER BY day DESC;

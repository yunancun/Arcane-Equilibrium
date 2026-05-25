-- Sprint 2 W2-F QA 14d daily evidence accumulation
-- per W2-A finalize §3.3 + AC-S2-A-2 / AC-S2-A-C1-7 / AC-S2-A-C4-9 minimum bar n_fills ≥ 30
-- per CR-6 6 attribute（部分 attribute 對映至 V103 EXTEND 6 column）
--
-- Hard invariant：
--   - track = 'direct_exploit'（per ADR-0026 + V101 ENUM hand-coded Rust strategy）
--   - engine_mode IN ('demo', 'live_demo')（per memory project_engine_mode_tag_live_demo）
--   - attribution_chain_ok = TRUE（per Sprint N+0 closure 100% 範式）
--
-- Bucket split: per-strategy × per-symbol × per-trade-date
-- Wilson CI 95% lower bound（z=1.96）;
-- Cumulative sample size projection over 14d；min_sample_gate 'PASS'/'PENDING'。
--
-- Usage:
--   psql ... -f 14d_bucket_split.sql
-- 或從 cron wrapper script source 呼叫（per W2-A finalize §3.4 cron line）。

WITH alpha_candidate_demo AS (
  SELECT
    strategy_name,
    DATE(filled_at AT TIME ZONE 'UTC') AS trade_date,
    symbol,
    COUNT(*) AS n_fills,
    AVG(net_pnl_bps) AS avg_net_bps,
    -- Wilson CI lower bound (z=1.96 for 95% CI; per CR-6 minimum bar #2)。
    -- defensive against n=0 / stddev=NULL (COALESCE + NULLIF)。
    (AVG(net_pnl_bps) - 1.96 * COALESCE(STDDEV(net_pnl_bps), 0)
     / NULLIF(SQRT(GREATEST(COUNT(*), 1)::float8), 0))::numeric(10,4) AS wilson_lower_bps
  FROM trading.fills
  WHERE strategy_name IN ('funding_short_v2', 'liquidation_cascade_fade')
    AND engine_mode IN ('demo', 'live_demo')
    AND track = 'direct_exploit'           -- per ADR-0026 hand-coded Rust = direct_exploit
    AND attribution_chain_ok = TRUE        -- per Sprint N+0 closure 範式 100% 預期
    AND filled_at > NOW() - INTERVAL '14 days'
  GROUP BY strategy_name, trade_date, symbol
)
SELECT
  strategy_name,
  trade_date,
  SUM(n_fills) AS total_fills,
  AVG(avg_net_bps) AS avg_net_bps_overall,
  MIN(wilson_lower_bps) AS wilson_lower_overall_bps,
  -- Sample size projection (14d cumulative)
  SUM(SUM(n_fills)) OVER (PARTITION BY strategy_name ORDER BY trade_date) AS cumulative_n_fills,
  -- AC-S2-A-2 minimum bar: cumulative ≥ 30
  CASE WHEN SUM(SUM(n_fills)) OVER (PARTITION BY strategy_name ORDER BY trade_date) >= 30
       THEN 'PASS' ELSE 'PENDING' END AS min_sample_gate
FROM alpha_candidate_demo
GROUP BY strategy_name, trade_date
ORDER BY strategy_name, trade_date DESC;

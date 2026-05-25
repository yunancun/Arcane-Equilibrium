-- AC-19 ALT bucket 14d monitor — daily bucket-split + Wilson CI 95%
-- Owner: QA SOP (W1-G) / E1 IMPL helper / cron 08:00 daily fire
-- Window: post-deploy 2026-05-19 00:00 UTC ~ 2026-06-02 00:00 UTC
--
-- 為什麼分 large_cap / alt 兩 bucket：BTC/ETH 流動性 / spread 與 ALT 結構差距大；
--   per W2-F empirical 14d data ALT bucket Wilson lower bound 接近 30% gate，
--   large_cap 高於 60% gate，必須分桶 verdict。
-- 為什麼用 Wilson score interval 而非 normal approximation：n 小（35）+ p_hat 邊界
--   時 normal CI 失準；Wilson 對 binomial proportion 更穩健，per W1-G SOP §4。
-- SQRT 內 GREATEST(..., 0)：浮點誤差防 negative；caller 端 psql 不可吞 NaN。
--
-- Verdict 3 級（per W1-G SOP §5）：
--   large_cap: Wilson lower ≥ 60% → PASS，否則 FAIL。
--   alt:       Wilson lower ≥ 30% → PASS / 20%-30% → MARGINAL / < 20% → FAIL。

WITH post_deploy AS (
  SELECT symbol, close_maker_attempt, close_maker_fallback_reason, ts
  FROM trading.fills
  WHERE engine_mode = 'demo'
    AND ts > '2026-05-19 00:00:00+00'::timestamptz
    AND ts <= '2026-06-02 00:00:00+00'::timestamptz
    AND close_maker_attempt = true
),
bucket_agg AS (
  SELECT
    CASE WHEN symbol IN ('BTCUSDT','ETHUSDT') THEN 'large_cap' ELSE 'alt' END AS bucket,
    count(*)::numeric AS n,
    count(*) FILTER (WHERE close_maker_fallback_reason IS NULL)::numeric AS fills,
    count(*) FILTER (WHERE close_maker_fallback_reason = 'timeout_taker')::numeric AS timeouts
  FROM post_deploy
  GROUP BY 1
),
wilson AS (
  SELECT
    bucket, n, fills, timeouts,
    CASE WHEN n > 0 THEN fills / n ELSE 0 END AS p_hat,
    1.96::numeric AS z
  FROM bucket_agg
)
SELECT
  bucket,
  n::int AS attempts,
  fills::int AS fills,
  timeouts::int AS timeouts,
  ROUND(p_hat * 100, 1) AS fill_rate_pct,
  ROUND(
    CASE WHEN n > 0 THEN
      ((p_hat + z*z/(2*n) - z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) * 100
    ELSE 0 END,
    1
  ) AS wilson_lower_pct,
  ROUND(
    CASE WHEN n > 0 THEN
      ((p_hat + z*z/(2*n) + z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) * 100
    ELSE 0 END,
    1
  ) AS wilson_upper_pct,
  CASE
    WHEN n = 0 THEN 'INSUFFICIENT_DATA'
    WHEN bucket = 'large_cap' AND
      ((p_hat + z*z/(2*n) - z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) >= 0.60 THEN 'PASS'
    WHEN bucket = 'large_cap' THEN 'FAIL'
    WHEN bucket = 'alt' AND
      ((p_hat + z*z/(2*n) - z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) >= 0.30 THEN 'PASS'
    WHEN bucket = 'alt' AND
      ((p_hat + z*z/(2*n) - z * SQRT(GREATEST(p_hat*(1-p_hat)/n + z*z/(4*n*n), 0))) / (1 + z*z/n)) >= 0.20 THEN 'MARGINAL'
    ELSE 'FAIL'
  END AS verdict
FROM wilson
ORDER BY bucket;

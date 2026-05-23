-- =============================================================================
-- health_60s_boundary_verify.sql
--
-- 用途：Sprint 5+ Wave 1 §4.4.2 production hardening — REST latency 60s
--      rolling window 物理對齊 + emitter scheduler tick 60s 樣本密度驗證。
--
-- 為什麼此 SQL：
--   - rust/openclaw_engine/src/bybit_rest_client.rs line 318-441 已實作真實
--     60s lazy expire（now.checked_sub(60s) → retain）；code-level 對齊。
--   - 本 SQL 驗 production runtime 真實樣本 inter-arrival ≈ 60s（emitter
--     scheduler tokio sleep 抖動允許 ±2s）+ samples_per_min=1 per metric
--     （avoid duplicate emit bug 或 emitter task crashed）。
--   - 對齊 PA report §3.2 預期：每 60s 一 emitter cycle 樣本；每 metric
--     1 sample/min。
--
-- 退出規範（caller 端 bash wrapper 解析）:
--   PASS — sample_inter_arrival_secs ∈ [58, 62] AND samples_per_min == 1
--   WARN — sample_inter_arrival_secs ∈ [55, 65] AND samples_per_min ∈ [1, 2]
--   FAIL — 任何域 sample_inter_arrival_secs out of [55, 65] OR
--          samples_per_min == 0 OR > 2
--
-- 範圍：only api_latency + engine_runtime（per PA 60s emitter tick 對齊範疇）。
-- 不含 risk_envelope (300s tick) / pipeline_throughput (30s tick) /
-- database_pool / strategy_quality（emitter interval 不對齊 60s window）。
-- =============================================================================

-- §1 sample inter-arrival check per metric — 連續 sample 距離 ~60s
-- 期望：delta_seconds ≈ 60.0 ± 2.0 (scheduler tokio sleep 抖動)
SELECT
  '§1 sample_inter_arrival' AS check_name,
  domain,
  metric_name,
  observed_at AS sample_ts,
  EXTRACT(EPOCH FROM (
    observed_at - LAG(observed_at) OVER (
      PARTITION BY domain, metric_name
      ORDER BY observed_at
    )
  )) AS delta_seconds
FROM learning.health_observations
WHERE observed_at > NOW() - INTERVAL '30 minutes'
  AND domain IN ('api_latency', 'engine_runtime')
ORDER BY domain, metric_name, observed_at DESC
LIMIT 20;

-- §2 bucket density check — 每 60s 應有 1 row per (domain, metric_name)
-- 期望：samples_per_min = 1 for 60s interval emitter
-- samples_per_min = 0 → emitter task crashed
-- samples_per_min > 1 → duplicate emit bug
SELECT
  '§2 samples_per_min' AS check_name,
  domain,
  metric_name,
  date_trunc('minute', observed_at) AS bucket_min,
  COUNT(*) AS samples_per_min
FROM learning.health_observations
WHERE observed_at > NOW() - INTERVAL '30 minutes'
  AND domain IN ('api_latency', 'engine_runtime')
GROUP BY domain, metric_name, bucket_min
ORDER BY domain, metric_name, bucket_min DESC
LIMIT 30;

-- §3 60s window aggregate summary — 過去 30 min 總體 sample 健康度
-- 期望：每 (domain, metric_name) 應有 ~30 row（30 min × 1 sample/min）
SELECT
  '§3 30min_summary' AS check_name,
  domain,
  metric_name,
  COUNT(*) AS row_count_30min,
  ROUND(EXTRACT(EPOCH FROM (MAX(observed_at) - MIN(observed_at)))::numeric / NULLIF(COUNT(*) - 1, 0), 2) AS avg_delta_seconds
FROM learning.health_observations
WHERE observed_at > NOW() - INTERVAL '30 minutes'
  AND domain IN ('api_latency', 'engine_runtime')
GROUP BY domain, metric_name
ORDER BY domain, metric_name;

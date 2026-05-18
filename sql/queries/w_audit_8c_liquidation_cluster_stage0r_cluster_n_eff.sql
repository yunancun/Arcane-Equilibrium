-- ============================================================
-- W-AUDIT-8c Stage 0R cluster-aware n_eff helper（sibling #2）
--
-- 用途：
--   metrics 模塊計算 _n_eff_cluster_aware(n_clusters_60m,
--   autocorr_factor=0.3) 之前取得 per (symbol, dominant_side) 的
--   n_clusters_60m。
--
-- 為什麼 60 分鐘：
--   cascade 在 funding 時段或大行情後常見「連環觸發」，60min 視窗吸收典型
--   cascade 尾部後，剩餘 cluster 之間可視為近似獨立樣本（PA §2.4 defended
--   default；MIT empirical 7d 數據 bucket/cluster ≈ 1.35-1.7 顯示 60min 吸收
--   約一半 autocorrelation；後續可基於 lag-1 autocorr empirical 調整）。
--
-- 不變量：
--   - 只讀；無 DDL；無 side effect。
--   - 與主檔 w_audit_8c_liquidation_cluster_stage0r_features.sql 共享參數
--     綁定 + 必須跑同樣 trigger filter set（含 notional_pct_floor）以保證
--     n_eff/n 比例 base 與主查詢一致；否則 DSR penalty 失真。
--
-- 參數綁定（psycopg2 named-param 風格，與主檔對齊）：
--   %(window_days)s              INT
--   %(symbols)s                  TEXT[]
--   %(k_event_floor)s            INT
--   %(n_usd_floor)s              DOUBLE PRECISION
--   %(m_dominant_floor)s         INT
--   %(side_dominance_floor)s     DOUBLE PRECISION
--   %(cluster_notional_floor_usd)s DOUBLE PRECISION
--   %(notional_pct_floor)s       DOUBLE PRECISION  -- round 2 新增（CRIT-2）
--
-- 輸出欄位：
--   symbol             TEXT
--   dominant_side      TEXT
--   n_clusters_60m     BIGINT
--
-- 依賴：
--   - market.liquidations（V002 + V095）
--
-- round 2 變動：
--   1. 從原主檔的 @SIBLING:CLUSTER_N_EFF_HELPER 拆出獨立檔（HIGH-1）。
--   2. raw_buckets → trigger_with_pct → trigger_candidates 完全鏡像主檔
--      gate set，加入 notional_pct_floor 第三層 magnitude_ok gate（CRIT-2）。
--      此前 sibling 漏 notional_pct_floor 會導致 n_clusters_60m 計算的
--      cluster 樣本與主查詢 trigger 不一致，n_eff/n 比例失真，DSR penalty 扭曲。
--   3. trigger_candidates 拆兩層（trigger_with_pct → trigger_candidates）因
--      percent_rank() 在 WHERE 不能直接用，與主檔結構嚴格鏡像。
--
-- 呼叫方式（split-3-files 後）：
--   loader = open('sql/queries/w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql').read()
--   cur.execute(loader, {同主檔 11 個 param})
-- ============================================================

WITH raw_buckets AS (
    -- 與主檔 CTE 1 完全相同（per CRIT-2：sibling 與主檔 trigger 樣本必須一致）
    SELECT
        symbol,
        (floor(extract(epoch FROM ts) / 300.0))::bigint * 300 AS bucket_5m_epoch,
        count(*)::bigint AS event_count_5m,
        sum(qty::float8 * price::float8) AS cluster_notional_5m,
        sum(CASE WHEN side = 'Buy'  THEN qty::float8 * price::float8 ELSE 0 END) AS long_notional_5m,
        sum(CASE WHEN side = 'Sell' THEN qty::float8 * price::float8 ELSE 0 END) AS short_notional_5m,
        count(*) FILTER (WHERE side = 'Buy')::bigint  AS long_event_count,
        count(*) FILTER (WHERE side = 'Sell')::bigint AS short_event_count,
        CASE
            WHEN sum(CASE WHEN side = 'Buy'  THEN qty::float8 * price::float8 ELSE 0 END)
                 >= 0.6 * sum(qty::float8 * price::float8)
              THEN count(*) FILTER (WHERE side = 'Buy')::bigint
            WHEN sum(CASE WHEN side = 'Sell' THEN qty::float8 * price::float8 ELSE 0 END)
                 >= 0.6 * sum(qty::float8 * price::float8)
              THEN count(*) FILTER (WHERE side = 'Sell')::bigint
            ELSE 0::bigint
        END AS dominant_event_count,
        CASE
            WHEN sum(CASE WHEN side = 'Buy'  THEN qty::float8 * price::float8 ELSE 0 END)
                 >= 0.6 * sum(qty::float8 * price::float8)
              THEN 'long_liquidated'
            WHEN sum(CASE WHEN side = 'Sell' THEN qty::float8 * price::float8 ELSE 0 END)
                 >= 0.6 * sum(qty::float8 * price::float8)
              THEN 'short_liquidated'
            ELSE 'mixed'
        END AS dominant_side,
        max(ts) AS bucket_end_ts
    FROM market.liquidations
    WHERE ts >= now() - (%(window_days)s::int * INTERVAL '1 day')
      AND symbol = ANY(%(symbols)s::text[])
    GROUP BY symbol, bucket_5m_epoch
),

density_gated AS (
    -- 與主檔 CTE 2 完全相同
    SELECT *
    FROM raw_buckets
    WHERE event_count_5m       >= %(k_event_floor)s::int
      AND cluster_notional_5m  >= %(n_usd_floor)s::float8
      AND dominant_event_count >= %(m_dominant_floor)s::int
      AND dominant_side IN ('long_liquidated', 'short_liquidated')
),

trigger_with_pct AS (
    -- 與主檔 CTE 3a 完全相同：先計算 notional_pct_24h 因 percent_rank 不能在 WHERE 用
    SELECT
        dg.*,
        GREATEST(dg.long_notional_5m, dg.short_notional_5m) / NULLIF(dg.cluster_notional_5m, 0)
            AS side_dominance_ratio,
        percent_rank() OVER (
            PARTITION BY dg.symbol
            ORDER BY dg.cluster_notional_5m
            ROWS BETWEEN 288 PRECEDING AND CURRENT ROW
        ) AS notional_pct_24h
    FROM density_gated dg
),

trigger_candidates AS (
    -- 與主檔 CTE 3b 完全相同 gate set（含 notional_pct_floor 第三層 magnitude_ok）
    -- CRIT-2 修復：此前 sibling 漏 notional_pct_floor 導致 cluster 樣本與主查詢不一致。
    SELECT symbol, dominant_side, bucket_end_ts
    FROM trigger_with_pct twp
    WHERE twp.side_dominance_ratio >= %(side_dominance_floor)s::float8
      AND twp.cluster_notional_5m  >= %(cluster_notional_floor_usd)s::float8
      AND twp.notional_pct_24h     >= %(notional_pct_floor)s::float8
),

ordered AS (
    -- 按 (symbol, dominant_side) 排序，取上一個 trigger 時間（lag）以判 gap
    SELECT
        symbol,
        dominant_side,
        bucket_end_ts,
        lag(bucket_end_ts) OVER (
            PARTITION BY symbol, dominant_side
            ORDER BY bucket_end_ts
        ) AS prev_ts
    FROM trigger_candidates
),

new_cluster_flag AS (
    -- 60 分鐘 gap 即視為新 cluster；連續觸發在 60min 內歸為同一 cluster
    SELECT
        symbol,
        dominant_side,
        bucket_end_ts,
        CASE
            WHEN prev_ts IS NULL
                 OR (bucket_end_ts - prev_ts) > INTERVAL '60 minutes'
            THEN 1 ELSE 0
        END AS is_new_cluster
    FROM ordered
)

SELECT
    symbol,
    dominant_side,
    sum(is_new_cluster)::bigint AS n_clusters_60m
FROM new_cluster_flag
GROUP BY symbol, dominant_side
ORDER BY symbol, dominant_side;

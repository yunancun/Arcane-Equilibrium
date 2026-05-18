-- ============================================================
-- W-AUDIT-8c Liquidation Cluster Strategy Stage 0R 特徵列查詢
--
-- 用途：
--   針對每個 5m 桶在 BB cor-side 映射（Buy=long liquidation,
--   Sell=short liquidation）下產生 cluster trigger 候選 + 嚴格 as-of 前向 1m
--   收益，供 helper_scripts/reports/w_audit_8c/ 下游 Python metrics 模塊計算
--   per-tier / per-direction Stage 0R 統計（n_eff / DSR / PSR / PBO / Wilson
--   CI / 單日單 symbol 集中度檢查 / FP rate / 密度地板效率）。
--
-- 不變量：
--   - 只讀；無 DDL；無 side effect。
--   - 不寫 market.liquidations 也不寫 market.klines；不觸發任何 telemetry。
--   - 嚴格 as-of join：forward 收益用 bucket_end_ts + quiet_window + horizon
--     之後第一根 kline；無未來資訊洩漏。
--   - 跨時段去重以 bucket_5m_epoch 為唯一鍵；max(ts) 取桶內最後事件，作為
--     quiet_window 起算點，避免桶剛開瞬間就進場。
--
-- 參數綁定（psycopg2 named-param 風格，與 8b 對齊）：
--   %(window_days)s            INT  — 回看視窗天數（如 7、14、28）
--   %(symbols)s                TEXT[] — cohort 篩選；下游 Python 端定義 25 symbol
--   %(k_event_floor)s          INT  — 5m 桶事件數下限 K（spec v0.3：2/3/5/8）
--   %(n_usd_floor)s            DOUBLE PRECISION — cluster_notional_5m USD 下限
--                                       N_usd（5K/10K/25K/50K）
--   %(m_dominant_floor)s       INT  — dominant 邊事件數下限 M（1/2/3）
--   %(side_dominance_floor)s   DOUBLE PRECISION — side notional 主導比例下限
--                                       （0.70/0.80/0.90；provider 自身為 0.60）
--   %(cluster_notional_floor_usd)s DOUBLE PRECISION — magnitude 第二層下限
--                                       （10K/25K/100K）
--   %(quiet_window_sec)s       INT  — 桶最後事件後沉默秒數（0/30/60）
--   %(horizon_min)s            INT  — 前向 1m kline 平均中價計算 horizon 分鐘
--                                       （1/5/15）
--   %(cost_bps)s               DOUBLE PRECISION — 雙向 fee+slippage 成本估計
--                                       （default 12 bps，與 8b 對齊；live
--                                       sensitivity 用 18/25）
--
-- 輸出欄位（下游 helper_scripts/reports/w_audit_8c 端 SELECT *）：
--   symbol                       TEXT
--   bucket_5m_epoch              BIGINT — 5m 桶 epoch 秒（floor(epoch/300)*300）
--   bucket_end_ts                TIMESTAMPTZ — 桶內最後事件時間
--   dominant_side                TEXT — 'long_liquidated' / 'short_liquidated'
--   expected_dir                 INT  — +1 (long liquidated → mean-revert up)
--                                       / -1 (short liquidated → mean-revert
--                                       down)
--   event_count_5m               BIGINT
--   cluster_notional_5m          DOUBLE PRECISION (USD)
--   long_notional_5m             DOUBLE PRECISION
--   short_notional_5m            DOUBLE PRECISION
--   long_event_count             BIGINT
--   short_event_count            BIGINT
--   dominant_event_count         BIGINT
--   side_dominance_ratio         DOUBLE PRECISION
--   notional_pct_24h             DOUBLE PRECISION — 24h rolling percentile
--                                       rank（per symbol）
--   entry_ts                     TIMESTAMPTZ — 進場 kline 開盤時間
--   entry_mid                    DOUBLE PRECISION — (open+close)/2 mid
--   exit_ts                      TIMESTAMPTZ — 出場 kline 開盤時間
--   exit_mid                     DOUBLE PRECISION
--   gross_bps                    DOUBLE PRECISION
--                                 = 10000 × expected_dir × (exit-entry)/entry
--   net_bps                      DOUBLE PRECISION = gross_bps - %(cost_bps)s
--   day_bucket                   DATE — 單日集中度檢查用（下游 Python 計算
--                                       per-tier max_day_share）
--
-- 5 CTE 順序：
--   raw_buckets → density_gated → trigger_candidates → forward_returns
--   → final_signals
--
-- 依賴：
--   - market.liquidations（V002 + V095 PK 升級到 (symbol, ts, side, qty,
--     price)，side CHECK ∈ {'Buy','Sell'}）
--   - market.klines WHERE timeframe='1m'（V002 OHLCV；ts TIMESTAMPTZ +
--     open/close REAL；本查詢用 (open+close)/2 mid）
--
-- 已知與 PA 設計 §2.3 偏離（self-report 詳述原因）：
--   1. 24h percentile rolling window = 288 PRECEDING（24h × 12 5m桶/h），
--      非 PA 寫的 17280 PRECEDING（17280/12 = 1440h = 60d，明顯與
--      欄位語義 notional_pct_24h 不符；修正為 288 行）。
--   2. PA 寫 market.klines_1m；實際 schema 為 market.klines + timeframe='1m'
--      過濾（V002）。已改用真表名。
--   3. PA 寫 ROWS BETWEEN ... PRECEDING；視窗區段用 ROWS 即可，但 5m 桶在
--      sparsity 高時不連續，PRECEDING 是「行數」而非「時間」。為與
--      LiquidationPulseAggregator 5m 切片語義對齊，添加註釋說明此限制
--      （下游 Python 若需嚴格 24h 時間窗，可在 metrics 層另做後處理）。
--   4. PA §2.3 forward_returns 用 4 個 correlated subquery（entry_ts /
--      entry_mid / exit_ts / exit_mid 各一）；本 IMPL 合併為 2 個 LEFT JOIN
--      LATERAL（一次取 (ts, open, close) tuple），避免 market.klines 索引
--      被掃 4 次，符合 acceptance #1 「<30s on 7d × 32-sym panel」目標。
--   5. 參數綁定 PA 用 `$name` 語法（PG 原生 prepare）；本 IMPL 改用
--      `%(name)s` psycopg2 named-param 語法，與 8b precedent 對齊（同檔
--      載入路徑、同 Python loader 模式、同 cursor.execute({...}) 簽名）。
-- ============================================================

WITH raw_buckets AS (
    -- CTE 1：以 5m epoch 桶聚合原始清算事件
    -- bucket_5m_epoch = floor(epoch/300)*300，與 LiquidationPulseAggregator
    -- WINDOW_5M_MS=300_000 切片對齊；同 ts/同 side 多事件（V095 後 row 級保留）
    -- 在 count(*) 與 sum(qty*price) 自然累加。
    -- dominant_side 判定遵循 provider DOMINANT_SIDE_RATIO=0.6 寫死；本層只判
    -- long/short/mixed，後續 CTE 再用 %(side_dominance_floor)s 收緊。
    SELECT
        symbol,
        (floor(extract(epoch FROM ts) / 300.0))::bigint * 300 AS bucket_5m_epoch,
        count(*)::bigint AS event_count_5m,
        sum(qty::float8 * price::float8) AS cluster_notional_5m,
        sum(CASE WHEN side = 'Buy'  THEN qty::float8 * price::float8 ELSE 0 END) AS long_notional_5m,
        sum(CASE WHEN side = 'Sell' THEN qty::float8 * price::float8 ELSE 0 END) AS short_notional_5m,
        count(*) FILTER (WHERE side = 'Buy')::bigint  AS long_event_count,
        count(*) FILTER (WHERE side = 'Sell')::bigint AS short_event_count,
        -- dominant_event_count：dominant 邊事件數；mixed 桶為 0，下游 K 地板
        -- 用 dominant_event_count 而不是 raw count 是因 spec §"min_dominant_event_count"
        -- 要求 dominant 邊至少 M 個事件，避免 51/49 邊界毛刺通過。
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
        -- max(ts)：桶內最後事件時間；quiet_window 從這點起算，避免桶剛開瞬間
        -- 即進場（cluster 形成的時間是漸進的）。
        max(ts) AS bucket_end_ts
    FROM market.liquidations
    WHERE ts >= now() - (%(window_days)s::int * INTERVAL '1 day')
      AND symbol = ANY(%(symbols)s::text[])
    GROUP BY symbol, bucket_5m_epoch
),

density_gated AS (
    -- CTE 2：套用 spec v0.3 三個密度地板（K, N_usd, M）+ 排除 mixed 桶
    -- 為什麼三層全套：K 過濾單/雙事件桶；N_usd 過濾微 cluster；M 過濾單邊
    -- 主導但事件數仍稀的桶（避免 1 個大單就觸發）。三層必須同時通過。
    SELECT *
    FROM raw_buckets
    WHERE event_count_5m       >= %(k_event_floor)s::int
      AND cluster_notional_5m  >= %(n_usd_floor)s::float8
      AND dominant_event_count >= %(m_dominant_floor)s::int
      AND dominant_side IN ('long_liquidated', 'short_liquidated')
),

trigger_candidates AS (
    -- CTE 3：magnitude / dominance 第二層 gate + 24h percentile rank
    -- side_dominance_ratio 收緊：provider 為 0.6 寬鬆，本層用 spec 提供的
    -- 0.70/0.80/0.90 sweep 軸。
    -- cluster_notional_floor_usd：絕對量級下限（10K/25K/100K），與 N_usd 不同
    -- 用途：N_usd 用於密度判定 inclusion，cluster_notional_floor_usd 是
    -- magnitude pre-filter（spec §"magnitude / dominance sweep"）。
    -- expected_dir：BB cor-side 鎖定 — long_liquidated 桶預期 mean-revert UP
    -- → +1；short_liquidated 桶預期 mean-revert DOWN → -1。
    -- notional_pct_24h：per-symbol 24h rolling percentile，下游 Python 用此
    -- 計算 cluster 相對自身歷史的稀有度。
    -- ROWS BETWEEN 288 PRECEDING：24h × 12 5m桶/h = 288 行；非時間窗，是
    -- 行數窗（sparsity 高時實際時間跨度可能 > 24h，但與 cluster 稀有度語義
    -- 一致 — 比較對象是「過去 288 個曾觸發桶」而非「過去固定 24h 任意時點」）。
    -- 注意：PA 設計 §2.3 寫 17280 PRECEDING 是筆誤（17280/12 = 1440h = 60d
    -- 與 notional_pct_24h 語義不符）。
    SELECT
        dg.*,
        GREATEST(dg.long_notional_5m, dg.short_notional_5m) / NULLIF(dg.cluster_notional_5m, 0)
            AS side_dominance_ratio,
        CASE dg.dominant_side
            WHEN 'long_liquidated'  THEN  1
            WHEN 'short_liquidated' THEN -1
        END AS expected_dir,
        percent_rank() OVER (
            PARTITION BY dg.symbol
            ORDER BY dg.cluster_notional_5m
            ROWS BETWEEN 288 PRECEDING AND CURRENT ROW
        ) AS notional_pct_24h
    FROM density_gated dg
    WHERE GREATEST(long_notional_5m, short_notional_5m) / NULLIF(cluster_notional_5m, 0)
              >= %(side_dominance_floor)s::float8
      AND cluster_notional_5m >= %(cluster_notional_floor_usd)s::float8
),

forward_returns AS (
    -- CTE 4：嚴格 as-of join 前向 kline 中價
    -- entry_kline：bucket_end_ts + quiet_window 之後第一根 1m kline；
    --   ts >= 目標時間 保證進場 bar 不洩漏觸發訊號（觸發 ts <= entry_ts）。
    -- exit_kline：bucket_end_ts + quiet_window + horizon 之後第一根 1m kline；
    --   horizon 為 mean-reversion 觀察窗（1/5/15 分鐘）。
    -- LIMIT 1：取最近一根；若 kline sparse（某 symbol 1m bar 缺失）回傳 NULL，
    --   最終 net_bps 也為 NULL，下游 Python 在 compute_stage0r 時統計排除率。
    -- 採用 (open+close)/2 mid：close 含成交集中，open 含開盤跳空風險，mid
    --   是兩者平均；與 8b funding skew SQL 的 close 點價策略略不同，因 8b
    --   focus 在較長 15m/30m/60m horizon 而 8c 主視窗 1-15m 對 open gap
    --   更敏感。
    -- 為什麼用 LEFT JOIN LATERAL 而非 4 個 correlated subquery：
    --   單一 LATERAL 一次取出 (ts, open, close) tuple 比 4 個 subquery 各
    --   掃 market.klines 索引 4 次效率高 ~2x；7d × 32-sym panel 預計
    --   ~1k-10k trigger rows，LATERAL 是 <30s 目標的必要優化。
    --   LEFT 保證 kline sparse 時 trigger row 仍輸出（NULL entry/exit
    --   填入），下游 Python 計算排除率。
    SELECT
        tc.symbol,
        tc.bucket_5m_epoch,
        tc.bucket_end_ts,
        tc.dominant_side,
        tc.expected_dir,
        tc.event_count_5m,
        tc.cluster_notional_5m,
        tc.long_notional_5m,
        tc.short_notional_5m,
        tc.long_event_count,
        tc.short_event_count,
        tc.dominant_event_count,
        tc.side_dominance_ratio,
        tc.notional_pct_24h,
        k_entry.ts                                         AS entry_ts,
        ((k_entry.open::float8) + (k_entry.close::float8)) / 2.0
                                                           AS entry_mid,
        k_exit.ts                                          AS exit_ts,
        ((k_exit.open::float8)  + (k_exit.close::float8))  / 2.0
                                                           AS exit_mid
    FROM trigger_candidates tc
    LEFT JOIN LATERAL (
        SELECT ts, open, close
        FROM market.klines
        WHERE symbol    = tc.symbol
          AND timeframe = '1m'
          AND ts        >= tc.bucket_end_ts
                           + (%(quiet_window_sec)s::int * INTERVAL '1 second')
        ORDER BY ts ASC
        LIMIT 1
    ) k_entry ON TRUE
    LEFT JOIN LATERAL (
        SELECT ts, open, close
        FROM market.klines
        WHERE symbol    = tc.symbol
          AND timeframe = '1m'
          AND ts        >= tc.bucket_end_ts
                           + (%(quiet_window_sec)s::int * INTERVAL '1 second')
                           + (%(horizon_min)s::int * INTERVAL '1 minute')
        ORDER BY ts ASC
        LIMIT 1
    ) k_exit ON TRUE
),

final_signals AS (
    -- CTE 5：gross / net bps + day_bucket
    -- gross_bps = 10000 × expected_dir × (exit_mid - entry_mid) / entry_mid
    --   expected_dir 鎖定 mean-reversion 方向；exit-entry 已 signed 收益，
    --   再乘 expected_dir 把方向化為「順 reversion 假設方向」。
    -- net_bps = gross_bps - %(cost_bps)s：雙向 fee+slippage 從 gross 直扣，
    --   default 12 bps 與 8b 對齊；下游 Python sweep 可重派 18/25 做成本
    --   保守敏感性。
    -- day_bucket：date_trunc('day', bucket_end_ts) — 下游 Python 用此計算
    --   per-cell × per-tier max_day_share（單日集中度地板 ≤ 25%，per spec
    --   v0.3 § + 8b INJUSDT lesson）。
    SELECT
        fr.symbol,
        fr.bucket_5m_epoch,
        fr.bucket_end_ts,
        fr.dominant_side,
        fr.expected_dir,
        fr.event_count_5m,
        fr.cluster_notional_5m,
        fr.long_notional_5m,
        fr.short_notional_5m,
        fr.long_event_count,
        fr.short_event_count,
        fr.dominant_event_count,
        fr.side_dominance_ratio,
        fr.notional_pct_24h,
        fr.entry_ts,
        fr.entry_mid,
        fr.exit_ts,
        fr.exit_mid,
        CASE
            WHEN fr.entry_mid IS NOT NULL AND fr.entry_mid > 0
                 AND fr.exit_mid  IS NOT NULL AND fr.exit_mid  > 0
            THEN 10000.0 * fr.expected_dir * (fr.exit_mid - fr.entry_mid) / fr.entry_mid
            ELSE NULL
        END AS gross_bps,
        CASE
            WHEN fr.entry_mid IS NOT NULL AND fr.entry_mid > 0
                 AND fr.exit_mid  IS NOT NULL AND fr.exit_mid  > 0
            THEN 10000.0 * fr.expected_dir * (fr.exit_mid - fr.entry_mid) / fr.entry_mid
                 - %(cost_bps)s::float8
            ELSE NULL
        END AS net_bps,
        date_trunc('day', fr.bucket_end_ts)::date AS day_bucket
    FROM forward_returns fr
)
SELECT *
FROM final_signals
ORDER BY symbol, bucket_5m_epoch;

-- ============================================================
-- Sibling query #1: panel coverage check（一次性前置檢查）
-- 用途：Stage 0R replay 前確認 market.liquidations 跨 cohort symbol 已累積
--      ≥ 7d 樣本；若 span_days < 7 則 metrics 模塊應 fail-fast 而非
--      silently 出 thin sample 結果。
-- 呼叫位置：helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py
--      在主查詢前單獨 cur.execute() 此塊。下游 Python loader 以
--      "-- @SIBLING:PANEL_COVERAGE_CHECK" 為 sentinel split 本檔。
--
-- 輸出欄位：
--   total_rows           BIGINT
--   distinct_symbols     BIGINT
--   earliest_ts          TIMESTAMPTZ
--   latest_ts            TIMESTAMPTZ
--   span_days            DOUBLE PRECISION
--   latest_age_min       DOUBLE PRECISION
--   cohort_observed      BIGINT — cohort ∩ observed（非 raw distinct）
--   cohort_coverage_pct  DOUBLE PRECISION
-- ============================================================
-- @SIBLING:PANEL_COVERAGE_CHECK
SELECT
    count(*)::bigint AS total_rows,
    count(DISTINCT symbol)::bigint AS distinct_symbols,
    min(ts) AS earliest_ts,
    max(ts) AS latest_ts,
    extract(epoch FROM (max(ts) - min(ts))) / 86400.0 AS span_days,
    extract(epoch FROM (now() - max(ts))) / 60.0 AS latest_age_min,
    count(DISTINCT symbol) FILTER (WHERE symbol = ANY(%(symbols)s::text[]))::bigint
        AS cohort_observed,
    (count(DISTINCT symbol) FILTER (WHERE symbol = ANY(%(symbols)s::text[]))::float8
        / NULLIF(array_length(%(symbols)s::text[], 1), 0)::float8) * 100.0
        AS cohort_coverage_pct
FROM market.liquidations
WHERE ts >= now() - (%(window_days)s::int * INTERVAL '1 day');

-- ============================================================
-- Sibling query #2: cluster-aware n_eff helper
-- 用途：metrics 模塊計算 _n_eff_cluster_aware(n_clusters_60m,
--      autocorr_factor=0.3) 之前取得 per (symbol, dominant_side) 的
--      n_clusters_60m。
-- 為什麼 60 分鐘：cascade 在 funding 時段或大行情後常見「連環觸發」，
--      60min 視窗吸收典型 cascade 尾部後，剩餘 cluster 之間可視為近似
--      獨立樣本（PA §2.4 defended default；MIT 可基於 lag-1 autocorr
--      empirical 後調整）。
-- 呼叫方式：本 sibling 查詢與主查詢共享參數綁定 — 下游 Python loader 應
--      在同一 cur.execute() session 之前先把主查詢結果物化（CREATE TEMP
--      TABLE）或在 Python 端 in-memory join；本檔提供 standalone 版，
--      直接重跑 raw_buckets → density_gated → trigger_candidates 路徑
--      抽 dominant_side / bucket_end_ts。
-- 輸出欄位：
--   symbol             TEXT
--   dominant_side      TEXT
--   n_clusters_60m     BIGINT
-- ============================================================
-- @SIBLING:CLUSTER_N_EFF_HELPER
WITH raw_buckets AS (
    SELECT
        symbol,
        (floor(extract(epoch FROM ts) / 300.0))::bigint * 300 AS bucket_5m_epoch,
        count(*)::bigint AS event_count_5m,
        sum(qty::float8 * price::float8) AS cluster_notional_5m,
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
        max(ts) AS bucket_end_ts,
        GREATEST(
            sum(CASE WHEN side = 'Buy'  THEN qty::float8 * price::float8 ELSE 0 END),
            sum(CASE WHEN side = 'Sell' THEN qty::float8 * price::float8 ELSE 0 END)
        ) / NULLIF(sum(qty::float8 * price::float8), 0) AS side_dominance_ratio
    FROM market.liquidations
    WHERE ts >= now() - (%(window_days)s::int * INTERVAL '1 day')
      AND symbol = ANY(%(symbols)s::text[])
    GROUP BY symbol, bucket_5m_epoch
),
trigger_candidates AS (
    SELECT symbol, dominant_side, bucket_end_ts
    FROM raw_buckets
    WHERE event_count_5m         >= %(k_event_floor)s::int
      AND cluster_notional_5m    >= %(n_usd_floor)s::float8
      AND dominant_event_count   >= %(m_dominant_floor)s::int
      AND dominant_side IN ('long_liquidated', 'short_liquidated')
      AND side_dominance_ratio   >= %(side_dominance_floor)s::float8
      AND cluster_notional_5m    >= %(cluster_notional_floor_usd)s::float8
),
ordered AS (
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

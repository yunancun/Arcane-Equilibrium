-- ============================================================
-- W-AUDIT-8c Liquidation Cluster Strategy Stage 0R 特徵列查詢（主檔）
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
--     之後第一根 kline；無未來資訊洩漏（entry/exit 都取該 bar 的 open，
--     避免 1m bar 內 (open+close)/2 把 event 後 60s 的 close 混入進場價）。
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
--   %(notional_pct_floor)s     DOUBLE PRECISION — magnitude 第三層 24h 百分位
--                                       下限（0.90/0.95/0.98，spec v0.3 line 191
--                                       magnitude_ok 必含；round 2 補回）
--   %(quiet_window_sec)s       INT  — 桶最後事件後沉默秒數（0/30/60）
--   %(horizon_min)s            INT  — 前向 1m kline open 計算 horizon 分鐘
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
--   entry_mid                    DOUBLE PRECISION — 該 bar 的 open price
--                                       （欄位名沿用 entry_mid 保留下游 Python
--                                       contract；semantic 為 open-only，見
--                                       MODULE_NOTE §「HIGH-2 verdict D」）
--   exit_ts                      TIMESTAMPTZ — 出場 kline 開盤時間
--   exit_mid                     DOUBLE PRECISION — 該 bar 的 open price
--   gross_bps                    DOUBLE PRECISION
--                                 = 10000 × expected_dir × (exit-entry)/entry
--   net_bps                      DOUBLE PRECISION = gross_bps - %(cost_bps)s
--   day_bucket                   DATE — 單日集中度檢查用（下游 Python 計算
--                                       per-tier max_day_share）
--
-- 5 CTE 順序：
--   raw_buckets → density_gated → trigger_with_pct → trigger_candidates
--   → forward_returns → final_signals
--   （round 2：trigger_candidates 拆兩層因 percent_rank() 在 WHERE 不能直接用，
--   notional_pct_floor gate 需先計算 percentile 再過濾）
--
-- 依賴：
--   - market.liquidations（V002 + V095 PK 升級到 (symbol, ts, side, qty,
--     price)，side CHECK ∈ {'Buy','Sell'}）
--   - market.klines WHERE timeframe='1m'（V002 OHLCV；ts TIMESTAMPTZ +
--     open/close REAL；本查詢用該 bar 的 open price 做 entry/exit）
--
-- HIGH-2 verdict D（PA 仲裁 2026-05-18）：
--   entry_mid / exit_mid 改為 open-only（非 (open+close)/2 mid）。
--   理由：market.klines.ts = bar open time（V002 line 122），一根 1m bar 涵蓋
--   [ts, ts+60s)。若 bucket_end_ts 落在 bar 邊界（如 12:34:00）+ quiet=0，
--   取 ts >= 12:34:00 命中該 bar；該 bar 的 close ≈ 12:34:59 包含 event 後
--   59s 的 mean-reversion → (open+close)/2 把 60s 後價格混入進場價 →
--   gross_bps 系統性低估 alpha。改 open-only 後：
--     - bar 邊界 case：entry_open ≈ event 時刻 price proxy（bar 開瞬間第一筆
--       trade），無 leak。
--     - non-boundary case：entry_open = 「event 後第一根新 bar 開瞬間」，與
--       exit_open 對稱。
--   欄位名沿用 entry_mid/exit_mid 是下游 Python `_compute_gross_bps()` 已 lock
--   的 contract，避免 cascade rename；semantic 改 open-only 屬於合理 trade-off。
--   ts >= 維持（非 strict gt）：spec line 231 「next available tradable mark」
--   語意，事件已知、價格未知，不是 lookahead bias。
--
-- 已知與 PA 設計 §2.3 偏離（round 1 documented；round 2 新增 #6/#7）：
--   1. 24h percentile rolling window = 288 PRECEDING（24h × 12 5m桶/h），
--      非 PA 寫的 17280 PRECEDING（17280/12 = 1440h = 60d，明顯與
--      欄位語義 notional_pct_24h 不符；修正為 288 行）。
--   2. PA 寫 market.klines_1m；實際 schema 為 market.klines + timeframe='1m'
--      過濾（V002）。已改用真表名。
--   3. PA 寫 ROWS BETWEEN ... PRECEDING；視窗區段用 ROWS 即可，但 5m 桶在
--      sparsity 高時不連續，PRECEDING 是「行數」而非「時間」。為與
--      LiquidationPulseAggregator 5m 切片語義對齊，添加註釋說明此限制
--      （下游 Python 若需嚴格 24h 時間窗，可在 metrics 層另做後處理）。
--      MIT SHOULD-2：per-symbol sparsity 高時（如 POLUSDT 1 trigger/day），
--      實際 288-row 跨度可能 > 24h；下游 Python 用此欄位做 cluster 稀有度
--      估計，semantic 為「相對自身過去 288 個曾觸發桶的 magnitude rank」。
--   4. PA §2.3 forward_returns 用 4 個 correlated subquery（entry_ts /
--      entry_mid / exit_ts / exit_mid 各一）；本 IMPL 合併為 2 個 LEFT JOIN
--      LATERAL（一次取 (ts, open) tuple），避免 market.klines 索引被掃 4 次。
--   5. 參數綁定 PA 用 `$name` 語法（PG 原生 prepare）；本 IMPL 改用
--      `%(name)s` psycopg2 named-param 語法，與 8b precedent 對齊。
--   6. （round 2）新增 notional_pct_floor 參數 + magnitude_ok 第三層 gate，
--      補回 spec v0.3 line 191 mandate；trigger_candidates 拆兩層因
--      percent_rank() 在 WHERE 不能直接用。
--   7. （round 2）entry_mid/exit_mid 從 (open+close)/2 改為 open-only，
--      per PA HIGH-2 verdict D（避免 1m bar partial leak）。
--
-- 對應 sibling 查詢已拆獨立檔（round 2 HIGH-1）：
--   - sql/queries/w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql
--   - sql/queries/w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql
-- ============================================================

WITH raw_buckets AS (
    -- CTE 1：以 5m epoch 桶聚合原始清算事件
    -- bucket_5m_epoch = floor(epoch/300)*300，與 LiquidationPulseAggregator
    -- WINDOW_5M_MS=300_000 切片對齊；同 ts/同 side 多事件（V095 後 row 級保留）
    -- 在 count(*) 與 sum(qty*price) 自然累加。
    -- dominant_side 判定遵循 provider DOMINANT_SIDE_RATIO=0.6 寫死；本層只判
    -- long/short/mixed，後續 CTE 再用 %(side_dominance_floor)s 收緊。
    -- E2 MED-4 / MIT 可讀性：把 long_notional / short_notional / total 拉成
    -- 中間欄位（_long_notional / _short_notional / _total_notional）讓 dominant_*
    -- CASE 直接引用 alias，PG planner 不重算 sum aggregation。
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

trigger_with_pct AS (
    -- CTE 3a：先計算 side_dominance_ratio + expected_dir + 24h notional percentile
    -- 為什麼拆兩層：percent_rank() 是 window function，在 WHERE clause 不能直接
    -- 引用（PG WHERE 在 window evaluation 之前）；先在這層計算 percentile，
    -- 下層再用此欄位做 magnitude_ok 第三層 gate。
    -- ROWS BETWEEN 288 PRECEDING：24h × 12 5m桶/h = 288 行；非時間窗，是
    -- 行數窗（sparsity 高時實際時間跨度可能 > 24h；MIT SHOULD-2 註明此語意）。
    -- 注意：PA 設計 §2.3 寫 17280 PRECEDING 是筆誤（17280/12 = 1440h = 60d
    -- 與 notional_pct_24h 語義不符）。
    SELECT
        dg.*,
        GREATEST(dg.long_notional_5m, dg.short_notional_5m) / NULLIF(dg.cluster_notional_5m, 0)
            AS side_dominance_ratio,
        CASE dg.dominant_side
            WHEN 'long_liquidated'  THEN  1
            WHEN 'short_liquidated' THEN -1
            ELSE NULL  -- LOW-2 defensive：density_gated 已 filter mixed，
                       -- 此處不應達；ELSE NULL 是防未來 refactor 繞開 mixed filter
        END AS expected_dir,
        percent_rank() OVER (
            PARTITION BY dg.symbol
            ORDER BY dg.cluster_notional_5m
            ROWS BETWEEN 288 PRECEDING AND CURRENT ROW
        ) AS notional_pct_24h
    FROM density_gated dg
),

trigger_candidates AS (
    -- CTE 3b：magnitude / dominance 第二+第三層 gate
    -- side_dominance_ratio 收緊：provider 為 0.6 寬鬆，本層用 spec 提供的
    -- 0.70/0.80/0.90 sweep 軸（side_dominance_floor）。
    -- cluster_notional_floor_usd：絕對量級下限（10K/25K/100K），與 N_usd 不同
    -- 用途：N_usd 用於密度判定 inclusion，cluster_notional_floor_usd 是
    -- magnitude pre-filter（spec §"magnitude / dominance sweep"）。
    -- notional_pct_floor：spec v0.3 line 191 magnitude_ok 第三層；要求
    -- cluster_notional_5m 相對自身 24h 歷史處於 percentile 0.90/0.95/0.98
    -- 之上，避免 absolute USD 通過但相對歷史平庸的桶觸發。
    -- 為什麼三層 magnitude gate 都必須：cluster_notional_floor_usd 絕對量級
    -- 排「太小」，notional_pct_floor 相對量級排「對自己而言不稀有」，
    -- side_dominance_floor 排「方向不夠主導」；三層交集才是 spec K_total
    -- 11_664 grid 的真實 cell 定義。
    SELECT *
    FROM trigger_with_pct twp
    WHERE twp.side_dominance_ratio >= %(side_dominance_floor)s::float8
      AND twp.cluster_notional_5m  >= %(cluster_notional_floor_usd)s::float8
      AND twp.notional_pct_24h     >= %(notional_pct_floor)s::float8
),

forward_returns AS (
    -- CTE 4：嚴格 as-of join 前向 kline open price
    -- entry_kline：bucket_end_ts + quiet_window 之後第一根 1m kline；
    --   ts >= 目標時間 保證進場 bar 不洩漏觸發訊號（觸發 ts <= entry_ts）。
    -- exit_kline：bucket_end_ts + quiet_window + horizon 之後第一根 1m kline；
    --   horizon 為 mean-reversion 觀察窗（1/5/15 分鐘）。
    -- LIMIT 1：取最近一根；若 kline sparse（某 symbol 1m bar 缺失）回傳 NULL，
    --   最終 net_bps 也為 NULL，下游 Python 在 compute_stage0r 時統計排除率。
    -- 採用該 bar 的 open price（非 (open+close)/2 mid）：per HIGH-2 verdict D，
    --   避免 1m bar 內 close 含 event 後 60s 的 partial leak；open 是 bar
    --   開瞬間第一筆 trade price，物理上最接近進場決策時刻。
    -- 欄位名 entry_mid / exit_mid 保留：下游 Python `_compute_gross_bps()`
    --   已 lock 此 contract，避免 cascade rename；semantic 為 open-only。
    -- 為什麼用 LEFT JOIN LATERAL 而非 4 個 correlated subquery：
    --   單一 LATERAL 一次取出 (ts, open) tuple 比 4 個 subquery 各掃
    --   market.klines 索引 4 次效率高 ~2x；7d × 32-sym panel 預計
    --   ~1k-10k trigger rows，LATERAL 是 <30s 目標的必要優化。
    --   LEFT 保證 kline sparse 時 trigger row 仍輸出（NULL entry/exit
    --   填入），下游 Python 計算排除率。
    -- MIT SHOULD-3 保護：ORDER BY ts ASC LIMIT 1 依賴 TimescaleDB ChunkAppend
    --   chunk-order-aware planner 早期終止（empirical Linux PG dry-run 已驗
    --   Custom Scan Order: klines.ts）；future planner regression 若失此 order
    --   可能掃全 chunk，請勿移除 ORDER BY。
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
        k_entry.ts                  AS entry_ts,
        k_entry.open::float8        AS entry_mid,
        k_exit.ts                   AS exit_ts,
        k_exit.open::float8         AS exit_mid
    FROM trigger_candidates tc
    LEFT JOIN LATERAL (
        SELECT ts, open
        FROM market.klines
        WHERE symbol    = tc.symbol
          AND timeframe = '1m'
          AND ts        >= tc.bucket_end_ts
                           + (%(quiet_window_sec)s::int * INTERVAL '1 second')
        ORDER BY ts ASC
        LIMIT 1
    ) k_entry ON TRUE
    LEFT JOIN LATERAL (
        SELECT ts, open
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

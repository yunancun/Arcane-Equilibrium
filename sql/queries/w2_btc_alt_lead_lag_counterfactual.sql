-- ============================================================
-- W2 A4-C BTC→Alt Lead-Lag — D+12 paper edge counterfactual SQL
-- ============================================================
-- 用途：D+12 paper engine 跑 7d 後，對齊 panel.btc_lead_lag_panel
--        / klines / trading.fills 三表，重建 lead signal 與 alt
--        forward return 的 counterfactual edge；給 w2_paper_edge_report.py
--        當輸入。對應 spec §7.2 + §7.1 mandatory metric 6 條的資料基礎。
-- 純 READ-ONLY：無 INSERT / UPDATE / DELETE / DDL。
-- 套件依賴：TimescaleDB（hypertable 上 1m grain 與 7d window 篩選效能）。
--
-- 對齊 spec：
--   - v1.2 §7.2 counterfactual SELECT pattern：
--       1. expected_dir=+1 → 反事實假設 LONG entry，net_edge_bps proxy
--          = forward 60s/120s/300s alt return
--       2. expected_dir=-1 → 反事實假設 SHORT entry，net_edge_bps proxy
--          = -1 × forward alt return
--       3. expected_dir=0 → 無信號 baseline（不計入）
--       4. regime_tag='extreme' → FILTER (WHERE regime_tag='normal') 排除
--   - v1.1 §3.1.1 + §7.1 metric (4)：N=60/120/300 三檔 R²(N) decay curve
--          → 三個 forward window 並列 alt return
--   - v1.2 §7.1 acceptance prerequisite dual-layer σ：
--          raw market σ_60=4.54 / σ_120=6.28 / σ_300=10.08 bps
--          net edge σ=50-80 bps （EDGE-DIAG-1 baseline，per-symbol 計算）
--   - v1.2 §8.1 +15/+5~15/<+5 三檔 gate verdict 由 Python 端計算
--
-- 不變式（schema contract）：
--   - panel.btc_lead_lag_panel.snapshot_ts_ms 為 BIGINT epoch ms（1m grain）
--   - panel.btc_lead_lag_panel.alt_symbols / alt_xcorr / alt_expected_dir 三 array 同序
--   - panel.btc_lead_lag_panel.lead_window_secs 主信號固定 120（v1.1 N 鎖定）
--   - panel.btc_lead_lag_panel.regime_tag IN ('normal','extreme')
--   - trading.fills.ts 為 TIMESTAMPTZ；is_paper=TRUE 為 paper engine 行
--   - trading.klines.ts 為 TIMESTAMPTZ；interval='1m'；symbol 對齊 cohort
--
-- E2 對抗審查重點（per dispatch plan §3.4）：
--   - SQL 對齊 expected_dir +1/-1/0 三方向（counterfactual 三方向 verdict）
--   - 強制 strict shift(N) lookahead-free：forward return 走 close[t+N] - close[t]
--     (writer 端寫 N 秒前的 lead；reader 端反算 N 秒後的 follow)
--   - 不寫 reg_tag='extreme' 樣本（per §7.2 + §9 condition #5）
-- ============================================================
--
-- 主要參數（caller 從 Python 端透過 psycopg2 cur.execute() 注入；本檔
-- 用 :param 占位符方便 grep；實際 cur.execute() 用 %(param)s）：
--   :window_days        — paper engine 7d edge collection window（int, default 7）
--   :cohort_symbols     — alt cohort symbol list (text[], per spec §2.2)
--                          default {ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,DOTUSDT}
--
-- 預期回傳 row 結構：
--   symbol TEXT            -- alt symbol
--   snapshot_ts_ms BIGINT  -- panel snapshot 對應的 1m bucket epoch ms
--   lead_window_secs INT   -- 主信號固定 120
--   btc_lead_return_pct REAL          -- BTC lead return N=120
--   btc_lead_return_pct_60s REAL      -- N=60 shadow（R²(N) decay curve）
--   btc_lead_return_pct_300s REAL     -- N=300 shadow（R²(N) decay curve）
--   xcorr REAL             -- alt 對應 xcorr
--   expected_dir SMALLINT  -- −1 / 0 / +1
--   regime_tag TEXT        -- 'normal' / 'extreme'
--   alt_forward_return_60s_bps REAL   -- alt forward 60s return (bps)
--   alt_forward_return_120s_bps REAL  -- alt forward 120s return (bps)
--   alt_forward_return_300s_bps REAL  -- alt forward 300s return (bps)
--   cf_net_edge_60s_bps REAL          -- expected_dir × forward 60s
--   cf_net_edge_120s_bps REAL         -- expected_dir × forward 120s
--   cf_net_edge_300s_bps REAL         -- expected_dir × forward 300s
--   has_actual_fill BOOLEAN           -- 該 1m bucket 內 alt symbol 是否真有 paper fill
--   actual_fill_count INT             -- 1m bucket 內 paper fill 數量
--
-- ============================================================
--
-- 設計筆記：
--   1. CTE `panel_window` 篩 7d panel snapshot；用 BIGINT epoch ms 對齊
--      hypertable hot-path index `idx_btc_lead_lag_panel_ts_window`
--   2. CTE `panel_expanded` 用 UNNEST 把每列 1 snapshot 的 array 展成
--      per-(snapshot, alt_symbol) row（spec §4.1 per-snapshot vector layout
--      展平做 counterfactual SQL 必須）
--   3. CTE `alt_klines` 取每個 cohort symbol 的 1m kline；用 LEAD()
--      window function 對齊 forward 1/2/5 bar = 60/120/300 秒
--   4. CTE `paper_fills_bucketed` 把 trading.fills 對齊 1m bucket（按
--      symbol + snapshot_ts_ms）；is_paper=TRUE
--   5. 最終 SELECT 把以上三方 JOIN：panel_expanded LEFT JOIN alt_klines
--      ON (symbol, snapshot_ts_ms) LEFT JOIN paper_fills_bucketed
--   6. Python 端用此查詢結果跑 6 mandatory metric 計算（pooled / per-symbol /
--      DSR / PSR(0) / R²(N) decay / block-bootstrap CI / counterfactual delta）
--
-- ============================================================

WITH params AS (
    -- ============================================================
    -- 參數標準化：caller 注入 %(window_days)s（default 7）+ %(cohort_symbols)s
    -- ============================================================
    SELECT
        COALESCE(%(window_days)s, 7)::INT AS window_days,
        COALESCE(
            %(cohort_symbols)s,
            ARRAY['ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','DOTUSDT']
        )::TEXT[] AS cohort_symbols,
        -- 7d window 起始 epoch ms（對齊 panel.btc_lead_lag_panel BIGINT 時間維）
        ((EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
            - COALESCE(%(window_days)s, 7)::BIGINT * 86400000) AS window_start_ms,
        -- 7d window 起始 TIMESTAMPTZ（對齊 trading.fills / trading.klines）
        (NOW() - (COALESCE(%(window_days)s, 7)::TEXT || ' days')::INTERVAL) AS window_start_ts
),

-- ============================================================
-- §1 panel_window — 7d 內 panel snapshot 篩選
-- 對齊 hypertable hot-path index `idx_btc_lead_lag_panel_ts_window`
-- 主信號固定 lead_window_secs=120（v1.1 N 鎖定，writer 也只寫此 1 row per snapshot）
-- regime_tag='extreme' 不在這裡排除：保留給 Python 端按 metric 計算
-- 時拍板（per-symbol breakdown 與 pooled 各自決定是否 FILTER）
-- ============================================================
panel_window AS (
    SELECT
        p.snapshot_ts_ms,
        p.lead_window_secs,
        p.btc_lead_return_pct,
        p.btc_lead_return_pct_60s,
        p.btc_lead_return_pct_300s,
        p.btc_volume_z,
        p.btc_book_imbalance,
        p.alt_symbols,
        p.alt_xcorr,
        p.alt_expected_dir,
        p.regime_tag,
        p.source_tier
    FROM panel.btc_lead_lag_panel p, params
    WHERE p.snapshot_ts_ms >= params.window_start_ms
      AND p.lead_window_secs = 120  -- 主信號固定 N=120
),

-- ============================================================
-- §2 panel_expanded — UNNEST per-snapshot vector → per-(snapshot, alt_symbol) row
-- spec §4.1 per-snapshot vector layout（1 snapshot per 1m bucket，alt_symbols
-- length 通常 = 7 cohort size，alt_xcorr / alt_expected_dir 同序 align）；
-- counterfactual SQL 必須展平成 per-symbol row 才能 JOIN alt kline。
-- 註：UNNEST WITH ORDINALITY 確保三 array align 安全（spec §4.1
-- writer 端強制三 array 同長度）。
-- ============================================================
panel_expanded AS (
    SELECT
        pw.snapshot_ts_ms,
        pw.lead_window_secs,
        pw.btc_lead_return_pct,
        pw.btc_lead_return_pct_60s,
        pw.btc_lead_return_pct_300s,
        pw.btc_volume_z,
        pw.btc_book_imbalance,
        u.alt_symbol::TEXT AS symbol,
        u.xcorr_val::REAL AS xcorr,
        u.expected_dir_val::SMALLINT AS expected_dir,
        pw.regime_tag,
        pw.source_tier
    FROM panel_window pw
    CROSS JOIN LATERAL UNNEST(
        pw.alt_symbols, pw.alt_xcorr, pw.alt_expected_dir
    ) WITH ORDINALITY AS u(alt_symbol, xcorr_val, expected_dir_val, ord)
    JOIN params ON TRUE
    WHERE u.alt_symbol = ANY(params.cohort_symbols)  -- cohort 範圍限定
),

-- ============================================================
-- §3 alt_klines — 每個 cohort symbol 的 1m kline + LEAD() forward return
-- 對齊 trading.klines.interval='1m'；取 close price，並用 window
-- function LEAD() 取未來 1/2/5 bar 的 close (= forward 60/120/300 秒)。
-- 對齊 panel.snapshot_ts_ms（epoch ms）= klines.ts（TIMESTAMPTZ）的轉換：
--   bucket_ts_ms = (EXTRACT(EPOCH FROM k.ts) * 1000)::BIGINT
-- ============================================================
alt_klines AS (
    SELECT
        k.symbol,
        (EXTRACT(EPOCH FROM k.ts) * 1000)::BIGINT AS bucket_ts_ms,
        k.close AS close_current,
        -- LEAD(1) = forward 60s（下一根 1m bar 的 close）
        LEAD(k.close, 1) OVER (
            PARTITION BY k.symbol ORDER BY k.ts
        ) AS close_forward_60s,
        -- LEAD(2) = forward 120s（兩根 1m bar 後的 close）
        LEAD(k.close, 2) OVER (
            PARTITION BY k.symbol ORDER BY k.ts
        ) AS close_forward_120s,
        -- LEAD(5) = forward 300s（五根 1m bar 後的 close）
        LEAD(k.close, 5) OVER (
            PARTITION BY k.symbol ORDER BY k.ts
        ) AS close_forward_300s
    FROM trading.klines k, params
    WHERE k.ts >= params.window_start_ts - INTERVAL '10 minutes'  -- buffer 對齊 LEAD()
      AND k.symbol = ANY(params.cohort_symbols)
      AND k.interval = '1m'
),

-- ============================================================
-- §4 paper_fills_bucketed — paper fill 對齊 1m bucket（per-symbol count + 任一 flag）
-- spec §7.2：對齊每筆 entry/exit fill 反算 counterfactual edge
-- 1m bucket 內可能有多筆 fill，取 count + 任一存在 flag
-- ============================================================
paper_fills_bucketed AS (
    SELECT
        f.symbol,
        -- 對齊 1m bucket：trunc 到分鐘 + 轉 epoch ms
        ((EXTRACT(EPOCH FROM DATE_TRUNC('minute', f.ts)) * 1000)::BIGINT) AS bucket_ts_ms,
        COUNT(*)::INT AS actual_fill_count
    FROM trading.fills f, params
    WHERE f.ts >= params.window_start_ts
      AND f.symbol = ANY(params.cohort_symbols)
      AND f.is_paper = TRUE  -- W2 paper-only fence Layer 1+2 已保證；此處再過濾
    GROUP BY f.symbol, DATE_TRUNC('minute', f.ts)
),

-- ============================================================
-- §5 final — panel_expanded LEFT JOIN alt_klines LEFT JOIN paper_fills_bucketed
-- alt forward return:
--   alt_forward_return_Ns_bps = (close_forward_Ns - close_current) / close_current × 10000
-- counterfactual net edge proxy:
--   expected_dir=+1 → cf_net_edge_Ns_bps = +1 × alt_forward_return_Ns_bps（LONG）
--   expected_dir=-1 → cf_net_edge_Ns_bps = -1 × alt_forward_return_Ns_bps（SHORT）
--   expected_dir=0 → cf_net_edge_Ns_bps = NULL（無信號，不計入 net edge）
-- ============================================================
SELECT
    pe.symbol,
    pe.snapshot_ts_ms,
    pe.lead_window_secs,
    pe.btc_lead_return_pct,
    pe.btc_lead_return_pct_60s,
    pe.btc_lead_return_pct_300s,
    pe.btc_volume_z,
    pe.btc_book_imbalance,
    pe.xcorr,
    pe.expected_dir,
    pe.regime_tag,

    -- alt forward returns (bps)
    CASE
        WHEN ak.close_current IS NULL OR ak.close_current = 0 OR ak.close_forward_60s IS NULL
            THEN NULL
        ELSE ((ak.close_forward_60s - ak.close_current) / ak.close_current * 10000)::REAL
    END AS alt_forward_return_60s_bps,
    CASE
        WHEN ak.close_current IS NULL OR ak.close_current = 0 OR ak.close_forward_120s IS NULL
            THEN NULL
        ELSE ((ak.close_forward_120s - ak.close_current) / ak.close_current * 10000)::REAL
    END AS alt_forward_return_120s_bps,
    CASE
        WHEN ak.close_current IS NULL OR ak.close_current = 0 OR ak.close_forward_300s IS NULL
            THEN NULL
        ELSE ((ak.close_forward_300s - ak.close_current) / ak.close_current * 10000)::REAL
    END AS alt_forward_return_300s_bps,

    -- counterfactual net edge proxy：expected_dir × forward return
    -- expected_dir=0 → NULL 不計入 net edge avg；caller Python 用 FILTER 排除
    CASE
        WHEN pe.expected_dir = 0 OR ak.close_current IS NULL OR ak.close_current = 0
              OR ak.close_forward_60s IS NULL
            THEN NULL
        ELSE (pe.expected_dir::REAL *
              ((ak.close_forward_60s - ak.close_current) / ak.close_current * 10000))::REAL
    END AS cf_net_edge_60s_bps,
    CASE
        WHEN pe.expected_dir = 0 OR ak.close_current IS NULL OR ak.close_current = 0
              OR ak.close_forward_120s IS NULL
            THEN NULL
        ELSE (pe.expected_dir::REAL *
              ((ak.close_forward_120s - ak.close_current) / ak.close_current * 10000))::REAL
    END AS cf_net_edge_120s_bps,
    CASE
        WHEN pe.expected_dir = 0 OR ak.close_current IS NULL OR ak.close_current = 0
              OR ak.close_forward_300s IS NULL
            THEN NULL
        ELSE (pe.expected_dir::REAL *
              ((ak.close_forward_300s - ak.close_current) / ak.close_current * 10000))::REAL
    END AS cf_net_edge_300s_bps,

    -- paper fill 對齊 1m bucket
    CASE WHEN pf.actual_fill_count IS NOT NULL AND pf.actual_fill_count > 0
         THEN TRUE ELSE FALSE END AS has_actual_fill,
    COALESCE(pf.actual_fill_count, 0)::INT AS actual_fill_count

FROM panel_expanded pe
LEFT JOIN alt_klines ak
    ON ak.symbol = pe.symbol AND ak.bucket_ts_ms = pe.snapshot_ts_ms
LEFT JOIN paper_fills_bucketed pf
    ON pf.symbol = pe.symbol AND pf.bucket_ts_ms = pe.snapshot_ts_ms
ORDER BY pe.symbol, pe.snapshot_ts_ms;

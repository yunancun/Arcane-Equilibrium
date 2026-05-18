-- ============================================================
-- W-AUDIT-8c Stage 0R panel coverage 前置檢查（sibling #1）
--
-- 用途：
--   Stage 0R replay 前確認 market.liquidations 跨 cohort symbol 已累積
--   ≥ 7d 樣本；若 span_days < 7 則 metrics 模塊應 fail-fast 而非 silently
--   出 thin sample 結果。
--
-- 不變量：
--   - 只讀；無 DDL；無 side effect。
--   - 與主檔 w_audit_8c_liquidation_cluster_stage0r_features.sql 共享參數
--     %(symbols)s / %(window_days)s。
--
-- 參數綁定（psycopg2 named-param 風格）：
--   %(window_days)s  INT     — 回看視窗天數
--   %(symbols)s      TEXT[]  — cohort 篩選；下游 Python 端定義
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
--
-- 依賴：
--   - market.liquidations（V002 + V095）
--
-- 呼叫方式（split-3-files 後）：
--   loader = open('sql/queries/w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql').read()
--   cur.execute(loader, {"window_days": ..., "symbols": list(symbols)})
--
-- round 2 變動：從原主檔的 @SIBLING:PANEL_COVERAGE_CHECK 拆出獨立檔
--   （per E2 HIGH-1 + MIT 接受 split-to-3-files；避免 sentinel-split silent
--   failure mode）。內容語意不變。
-- ============================================================

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

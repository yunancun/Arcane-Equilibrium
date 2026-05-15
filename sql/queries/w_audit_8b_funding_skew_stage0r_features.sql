-- W-AUDIT-8b Funding Skew Directional Stage 0R feature rows.
-- Read-only query. It builds one point-in-time row per 5m closed kline and
-- symbol, using latest raw panel rows where snapshot_ts_ms <= signal_ts_ms.

WITH bars AS (
    SELECT
        k.symbol,
        k.open_ts_ms,
        k.close_ts_ms AS signal_ts_ms,
        k.open::float8 AS open_px,
        k.close::float8 AS close_px,
        CASE
            WHEN k.open > 0 THEN ((k.close::float8 - k.open::float8) / k.open::float8) * 10000.0
            ELSE NULL
        END AS prior_5m_return_bps
    FROM market.klines k
    WHERE k.timeframe = '5m'
      AND k.symbol = ANY(%(symbols)s)
      AND k.close_ts_ms >= ((EXTRACT(EPOCH FROM now()) * 1000)::bigint - (%(window_days)s::int * 86400000)::bigint)
      AND k.close_ts_ms <= ((EXTRACT(EPOCH FROM now()) * 1000)::bigint - 3600000)
),
joined AS (
    SELECT
        b.symbol,
        b.signal_ts_ms,
        b.open_ts_ms,
        b.open_px,
        b.close_px,
        b.prior_5m_return_bps,
        f.snapshot_ts_ms AS funding_snapshot_ts_ms,
        (b.signal_ts_ms - f.snapshot_ts_ms)::bigint AS funding_age_ms,
        f.funding_rate_bps::float8 AS funding_rate_bps,
        f.next_funding_ms::bigint AS next_funding_ms,
        f.source_tier AS funding_source_tier,
        oi.snapshot_ts_ms AS oi_snapshot_ts_ms,
        (b.signal_ts_ms - oi.snapshot_ts_ms)::bigint AS oi_age_ms,
        oi.oi_delta_15m_pct::float8 AS oi_delta_15m_pct,
        oi.oi_delta_1h_pct::float8 AS oi_delta_1h_pct,
        oi.source_tier AS oi_source_tier,
        f15.close::float8 AS close_15m,
        f30.close::float8 AS close_30m,
        f60.close::float8 AS close_60m
    FROM bars b
    LEFT JOIN LATERAL (
        SELECT snapshot_ts_ms, funding_rate_bps, next_funding_ms, source_tier
        FROM panel.funding_rates_panel p
        WHERE p.symbol = b.symbol
          AND p.snapshot_ts_ms <= b.signal_ts_ms
        ORDER BY p.snapshot_ts_ms DESC
        LIMIT 1
    ) f ON TRUE
    LEFT JOIN LATERAL (
        SELECT snapshot_ts_ms, oi_delta_15m_pct, oi_delta_1h_pct, source_tier
        FROM panel.oi_delta_panel p
        WHERE p.symbol = b.symbol
          AND p.snapshot_ts_ms <= b.signal_ts_ms
        ORDER BY p.snapshot_ts_ms DESC
        LIMIT 1
    ) oi ON TRUE
    LEFT JOIN LATERAL (
        SELECT close
        FROM market.klines k
        WHERE k.symbol = b.symbol
          AND k.timeframe = '5m'
          AND k.close_ts_ms >= b.signal_ts_ms + 900000
        ORDER BY k.close_ts_ms ASC
        LIMIT 1
    ) f15 ON TRUE
    LEFT JOIN LATERAL (
        SELECT close
        FROM market.klines k
        WHERE k.symbol = b.symbol
          AND k.timeframe = '5m'
          AND k.close_ts_ms >= b.signal_ts_ms + 1800000
        ORDER BY k.close_ts_ms ASC
        LIMIT 1
    ) f30 ON TRUE
    LEFT JOIN LATERAL (
        SELECT close
        FROM market.klines k
        WHERE k.symbol = b.symbol
          AND k.timeframe = '5m'
          AND k.close_ts_ms >= b.signal_ts_ms + 3600000
        ORDER BY k.close_ts_ms ASC
        LIMIT 1
    ) f60 ON TRUE
),
stats AS (
    SELECT
        signal_ts_ms,
        percentile_cont(0.5) WITHIN GROUP (ORDER BY funding_rate_bps) AS funding_median_bps,
        avg(funding_rate_bps) AS funding_mean_bps,
        stddev_samp(funding_rate_bps) AS funding_std_bps,
        count(*) FILTER (WHERE funding_rate_bps IS NOT NULL)::int AS funding_cohort_n
    FROM joined
    WHERE funding_rate_bps IS NOT NULL
    GROUP BY signal_ts_ms
),
ranked AS (
    SELECT
        j.*,
        s.funding_median_bps::float8,
        s.funding_mean_bps::float8,
        s.funding_std_bps::float8,
        s.funding_cohort_n,
        percent_rank() OVER (
            PARTITION BY j.signal_ts_ms
            ORDER BY j.funding_rate_bps
        )::float8 AS funding_percentile
    FROM joined j
    LEFT JOIN stats s USING (signal_ts_ms)
)
SELECT
    symbol,
    signal_ts_ms,
    prior_5m_return_bps,
    funding_snapshot_ts_ms,
    funding_age_ms,
    funding_rate_bps,
    funding_median_bps,
    CASE
        WHEN funding_std_bps IS NOT NULL AND funding_std_bps > 0
            THEN (funding_rate_bps - funding_median_bps) / funding_std_bps
        ELSE NULL
    END AS funding_zscore_25sym,
    funding_percentile AS funding_percentile_25sym,
    (funding_rate_bps - funding_median_bps) AS funding_spread_to_median_bps,
    funding_cohort_n,
    next_funding_ms,
    funding_source_tier,
    oi_snapshot_ts_ms,
    oi_age_ms,
    oi_delta_15m_pct,
    oi_delta_1h_pct,
    oi_source_tier,
    CASE WHEN close_px > 0 AND close_15m IS NOT NULL THEN ((close_15m - close_px) / close_px) * 10000.0 ELSE NULL END AS fwd_return_15m_bps,
    CASE WHEN close_px > 0 AND close_30m IS NOT NULL THEN ((close_30m - close_px) / close_px) * 10000.0 ELSE NULL END AS fwd_return_30m_bps,
    CASE WHEN close_px > 0 AND close_60m IS NOT NULL THEN ((close_60m - close_px) / close_px) * 10000.0 ELSE NULL END AS fwd_return_60m_bps
FROM ranked
ORDER BY signal_ts_ms, symbol;

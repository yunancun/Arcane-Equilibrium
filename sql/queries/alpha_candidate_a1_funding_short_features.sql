-- Alpha Candidate A1 funding_short_v2 read-only feature rows.
--
-- Purpose:
--   Build leak-free point-in-time replay rows for funding_short_v2. The strategy
--   thesis is short-only positive funding capture, so the outcome must include
--   realized funding settlements during the hold window in addition to price PnL.
--
-- Invariants:
--   - Read-only SELECT. No DDL and no writes.
--   - funding/basis inputs are as-of joins: snapshot_ts_ms <= signal_ts_ms.
--   - exit price is a future 5m close at signal_ts_ms + hold_ms; rows without a
--     future exit are left NULL and ignored by the Python metrics layer.
--   - funding_carry_bps sums actual future market.funding_rates settlements in
--     (signal_ts_ms, exit_ts_ms]. For a perp short, positive funding is positive
--     carry. This is outcome measurement, not signal input.

WITH bars AS (
    SELECT
        k.symbol,
        k.open_ts_ms,
        k.close_ts_ms AS signal_ts_ms,
        k.open::float8 AS open_px,
        k.close::float8 AS entry_px
    FROM market.klines k
    WHERE k.timeframe = '5m'
      AND k.symbol = ANY(%(symbols)s)
      AND k.close_ts_ms >= ((EXTRACT(EPOCH FROM now()) * 1000)::bigint - (%(window_days)s::int * 86400000)::bigint)
      AND k.close_ts_ms <= ((EXTRACT(EPOCH FROM now()) * 1000)::bigint - %(hold_ms)s::bigint)
),
joined AS (
    SELECT
        b.symbol,
        b.signal_ts_ms,
        b.open_ts_ms,
        b.open_px,
        b.entry_px,
        f.snapshot_ts_ms AS funding_snapshot_ts_ms,
        (b.signal_ts_ms - f.snapshot_ts_ms)::bigint AS funding_age_ms,
        f.funding_rate_bps::float8 AS funding_rate_bps,
        f.next_funding_ms::bigint AS next_funding_ms,
        f.source_tier AS funding_source_tier,
        bp.snapshot_ts_ms AS basis_snapshot_ts_ms,
        (b.signal_ts_ms - bp.snapshot_ts_ms)::bigint AS basis_age_ms,
        bp.basis_pct::float8 AS basis_pct,
        bp.source_tier AS basis_source_tier,
        k_exit.close_ts_ms AS exit_ts_ms,
        k_exit.close::float8 AS exit_px
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
        SELECT snapshot_ts_ms, basis_pct, source_tier
        FROM panel.basis_panel p
        WHERE p.symbol = b.symbol
          AND p.snapshot_ts_ms <= b.signal_ts_ms
        ORDER BY p.snapshot_ts_ms DESC
        LIMIT 1
    ) bp ON TRUE
    LEFT JOIN market.klines k_exit
        ON k_exit.symbol = b.symbol
       AND k_exit.timeframe = '5m'
       AND k_exit.close_ts_ms = b.signal_ts_ms + %(hold_ms)s::bigint
),
with_funding AS (
    SELECT
        j.*,
        COALESCE(fs.settlement_count, 0)::int AS funding_settlement_count,
        COALESCE(fs.funding_carry_bps, 0.0)::float8 AS funding_carry_bps
    FROM joined j
    LEFT JOIN LATERAL (
        SELECT
            count(*)::int AS settlement_count,
            sum(fr.funding_rate::float8 * 10000.0)::float8 AS funding_carry_bps
        FROM market.funding_rates fr
        WHERE fr.symbol = j.symbol
          AND j.exit_ts_ms IS NOT NULL
          AND (EXTRACT(EPOCH FROM fr.ts) * 1000)::bigint > j.signal_ts_ms
          AND (EXTRACT(EPOCH FROM fr.ts) * 1000)::bigint <= j.exit_ts_ms
    ) fs ON TRUE
)
SELECT
    symbol,
    signal_ts_ms,
    open_ts_ms,
    open_px,
    entry_px,
    funding_snapshot_ts_ms,
    funding_age_ms,
    funding_rate_bps,
    (funding_rate_bps / 10000.0 * 1095.0)::float8 AS funding_annualized,
    next_funding_ms,
    funding_source_tier,
    basis_snapshot_ts_ms,
    basis_age_ms,
    basis_pct,
    basis_source_tier,
    exit_ts_ms,
    exit_px,
    funding_settlement_count,
    funding_carry_bps,
    CASE
        WHEN entry_px > 0 AND exit_px IS NOT NULL
            THEN ((exit_px - entry_px) / entry_px) * 10000.0
        ELSE NULL
    END AS fwd_return_bps,
    CASE
        WHEN entry_px > 0 AND exit_px IS NOT NULL
            THEN -1.0 * ((exit_px - entry_px) / entry_px) * 10000.0
        ELSE NULL
    END AS price_gross_bps,
    CASE
        WHEN entry_px > 0 AND exit_px IS NOT NULL
            THEN (-1.0 * ((exit_px - entry_px) / entry_px) * 10000.0) + funding_carry_bps
        ELSE NULL
    END AS gross_with_funding_bps,
    CASE
        WHEN entry_px > 0 AND exit_px IS NOT NULL
            THEN (-1.0 * ((exit_px - entry_px) / entry_px) * 10000.0) + funding_carry_bps - %(cost_bps)s::float8
        ELSE NULL
    END AS net_bps
FROM with_funding
ORDER BY signal_ts_ms, symbol;

-- ============================================================
-- V092: panel.* continuous_aggregates — W1 sub-task 3 (E1-γ, 2026-05-11)
--   5m / 15m / 1h chunked rollups for panel.funding_rates_panel + panel.oi_delta_panel
-- Status: NOT_RUN — D+1+ deploy after sign-off
-- Spec: docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md §2.4 + §3.4
-- 動機 / Motivation:
--   V085/V087 寫 1m granularity row（panel collector 60s flush 一次）；下游 ML
--   training + monitoring 需要 5m / 15m / 1h aggregated view（節省 query cost、
--   diagnostic dashboard 需 multi-resolution）。TimescaleDB continuous_aggregate
--   提供 incremental refresh + materialized view 解。
--
--   panel.funding_rates_panel 5m/15m/1h：avg(funding_rate_bps) per (bucket, symbol)
--   panel.oi_delta_panel 5m/15m/1h：avg(oi_abs) + avg(oi_delta_*_pct) per (bucket, symbol)
--
-- 範圍 / Scope:
--   1. CREATE MATERIALIZED VIEW panel.funding_rates_panel_5m / 15m / 1h
--      （TimescaleDB continuous_aggregate, time_bucket on snapshot_ts_ms BIGINT）
--   2. CREATE MATERIALIZED VIEW panel.oi_delta_panel_5m / 15m / 1h
--   3. add_continuous_aggregate_policy 6 view × refresh interval（1m / 5m / 15m）
--   4. timescaledb extension guard（無 ext → 全 skip + 不阻塞 idempotency）
--
-- 不變式 / Invariants:
--   - time_bucket 算法：snapshot_ts_ms BIGINT 用 time_bucket(N, snapshot_ts_ms)
--     (N = bucket interval ms：5m=300000, 15m=900000, 1h=3600000)
--   - WITH NO DATA：MV 建立後不 immediately refresh（避免 boot 阻塞 ~10-30s）；
--     refresh policy 自動補
--   - GROUP BY (bucket, symbol)：每 (bucket, symbol) tuple 唯一 row
--   - source_tier 不 aggregate（不同 source tier 已在 V085/V087 raw row 區分；
--     5m bucket 內若 source 變動，aggregate 對所有 tier 計算 avg；下游 query
--     可加 WHERE source_tier 自選）
--
-- Idempotency:
--   - CREATE MATERIALIZED VIEW IF NOT EXISTS → 第二次 no-op
--   - add_continuous_aggregate_policy(if_not_exists => TRUE) → 第二次 no-op
--   - timescaledb extension guard → 無 ext 時整段 NOTICE skip
--
-- E2 review checklist:
--   1. timescaledb extension guard 存在性（pg_extension WHERE extname='timescaledb'）
--   2. continuous_aggregate WITH NO DATA 不 boot 阻塞
--   3. add_continuous_aggregate_policy schedule_interval 合理（5m view 1m refresh
--      過頻會耗 CPU；1h view 15m refresh 太稀會延遲 ML data ready）
--   4. time_bucket 第一參數型別：BIGINT (ms) 而非 INTERVAL
--   5. WHERE clause 在 raw view 不加（cross-section panel data 無 garbage filter 必要）
-- ============================================================

BEGIN;

-- ────────────────────────────────────────────────────────────
-- §1 timescaledb extension guard — 無 ext 時整段 skip
-- ────────────────────────────────────────────────────────────
DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        RAISE NOTICE 'V092 SKIP: timescaledb extension absent — continuous aggregates not created';
        RETURN;
    END IF;

    -- ────────────────────────────────────────────────────────
    -- §2 panel.funding_rates_panel continuous_aggregate（5m / 15m / 1h）
    -- ────────────────────────────────────────────────────────

    -- 5m bucket
    EXECUTE $sql$
        CREATE MATERIALIZED VIEW IF NOT EXISTS panel.funding_rates_panel_5m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(300000::bigint, snapshot_ts_ms) AS bucket_ts_ms,
            symbol,
            avg(funding_rate_bps) AS funding_rate_bps_avg,
            min(funding_rate_bps) AS funding_rate_bps_min,
            max(funding_rate_bps) AS funding_rate_bps_max,
            count(*) AS sample_count
        FROM panel.funding_rates_panel
        GROUP BY bucket_ts_ms, symbol
        WITH NO DATA;
    $sql$;

    -- 15m bucket
    EXECUTE $sql$
        CREATE MATERIALIZED VIEW IF NOT EXISTS panel.funding_rates_panel_15m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(900000::bigint, snapshot_ts_ms) AS bucket_ts_ms,
            symbol,
            avg(funding_rate_bps) AS funding_rate_bps_avg,
            min(funding_rate_bps) AS funding_rate_bps_min,
            max(funding_rate_bps) AS funding_rate_bps_max,
            count(*) AS sample_count
        FROM panel.funding_rates_panel
        GROUP BY bucket_ts_ms, symbol
        WITH NO DATA;
    $sql$;

    -- 1h bucket
    EXECUTE $sql$
        CREATE MATERIALIZED VIEW IF NOT EXISTS panel.funding_rates_panel_1h
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(3600000::bigint, snapshot_ts_ms) AS bucket_ts_ms,
            symbol,
            avg(funding_rate_bps) AS funding_rate_bps_avg,
            min(funding_rate_bps) AS funding_rate_bps_min,
            max(funding_rate_bps) AS funding_rate_bps_max,
            count(*) AS sample_count
        FROM panel.funding_rates_panel
        GROUP BY bucket_ts_ms, symbol
        WITH NO DATA;
    $sql$;

    -- Refresh policies — start_offset/end_offset 用 BIGINT ms
    -- start_offset = 1h（refresh 過去 1h 視窗的所有 bucket）
    -- end_offset = 1m（避免 refresh 正在寫入的最新 bucket）
    -- schedule_interval 1m / 5m / 15m 對應 5m / 15m / 1h granularity
    PERFORM add_continuous_aggregate_policy(
        'panel.funding_rates_panel_5m',
        start_offset => 3600000::bigint,
        end_offset => 60000::bigint,
        schedule_interval => INTERVAL '1 minute',
        if_not_exists => TRUE
    );
    PERFORM add_continuous_aggregate_policy(
        'panel.funding_rates_panel_15m',
        start_offset => 7200000::bigint,
        end_offset => 60000::bigint,
        schedule_interval => INTERVAL '5 minutes',
        if_not_exists => TRUE
    );
    PERFORM add_continuous_aggregate_policy(
        'panel.funding_rates_panel_1h',
        start_offset => 21600000::bigint,
        end_offset => 60000::bigint,
        schedule_interval => INTERVAL '15 minutes',
        if_not_exists => TRUE
    );

    -- ────────────────────────────────────────────────────────
    -- §3 panel.oi_delta_panel continuous_aggregate（5m / 15m / 1h）
    -- ────────────────────────────────────────────────────────

    -- 5m bucket
    EXECUTE $sql$
        CREATE MATERIALIZED VIEW IF NOT EXISTS panel.oi_delta_panel_5m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(300000::bigint, snapshot_ts_ms) AS bucket_ts_ms,
            symbol,
            avg(oi_abs) AS oi_abs_avg,
            avg(oi_delta_5m_pct) AS oi_delta_5m_pct_avg,
            avg(oi_delta_15m_pct) AS oi_delta_15m_pct_avg,
            avg(oi_delta_1h_pct) AS oi_delta_1h_pct_avg,
            count(*) AS sample_count
        FROM panel.oi_delta_panel
        GROUP BY bucket_ts_ms, symbol
        WITH NO DATA;
    $sql$;

    -- 15m bucket
    EXECUTE $sql$
        CREATE MATERIALIZED VIEW IF NOT EXISTS panel.oi_delta_panel_15m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(900000::bigint, snapshot_ts_ms) AS bucket_ts_ms,
            symbol,
            avg(oi_abs) AS oi_abs_avg,
            avg(oi_delta_5m_pct) AS oi_delta_5m_pct_avg,
            avg(oi_delta_15m_pct) AS oi_delta_15m_pct_avg,
            avg(oi_delta_1h_pct) AS oi_delta_1h_pct_avg,
            count(*) AS sample_count
        FROM panel.oi_delta_panel
        GROUP BY bucket_ts_ms, symbol
        WITH NO DATA;
    $sql$;

    -- 1h bucket
    EXECUTE $sql$
        CREATE MATERIALIZED VIEW IF NOT EXISTS panel.oi_delta_panel_1h
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket(3600000::bigint, snapshot_ts_ms) AS bucket_ts_ms,
            symbol,
            avg(oi_abs) AS oi_abs_avg,
            avg(oi_delta_5m_pct) AS oi_delta_5m_pct_avg,
            avg(oi_delta_15m_pct) AS oi_delta_15m_pct_avg,
            avg(oi_delta_1h_pct) AS oi_delta_1h_pct_avg,
            count(*) AS sample_count
        FROM panel.oi_delta_panel
        GROUP BY bucket_ts_ms, symbol
        WITH NO DATA;
    $sql$;

    PERFORM add_continuous_aggregate_policy(
        'panel.oi_delta_panel_5m',
        start_offset => 3600000::bigint,
        end_offset => 60000::bigint,
        schedule_interval => INTERVAL '1 minute',
        if_not_exists => TRUE
    );
    PERFORM add_continuous_aggregate_policy(
        'panel.oi_delta_panel_15m',
        start_offset => 7200000::bigint,
        end_offset => 60000::bigint,
        schedule_interval => INTERVAL '5 minutes',
        if_not_exists => TRUE
    );
    PERFORM add_continuous_aggregate_policy(
        'panel.oi_delta_panel_1h',
        start_offset => 21600000::bigint,
        end_offset => 60000::bigint,
        schedule_interval => INTERVAL '15 minutes',
        if_not_exists => TRUE
    );

    RAISE NOTICE 'V092 OK: 6 continuous_aggregate views + refresh policies created (panel.funding_rates_panel + panel.oi_delta_panel × 5m/15m/1h)';
END
$guard$;

COMMIT;

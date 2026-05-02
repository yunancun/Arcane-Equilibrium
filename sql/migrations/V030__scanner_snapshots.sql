-- V030: Persist scanner cycle snapshots for edge attribution.
-- V030：持久化 scanner 掃描週期快照，用於 edge 歸因。
--
-- Retrofit (AUDIT-2026-05-02-P1-1, 2026-05-02): added Guard A per CLAUDE.md
-- §七 (V023 silent-noop postmortem). 4-day cold audit found V030 missing
-- this guard; if a legacy `trading.scanner_snapshots` stub exists with a
-- different shape (e.g. earlier prototype lacking `candidates` JSONB or
-- `config` JSONB), `CREATE TABLE IF NOT EXISTS` silently no-ops and the
-- downstream Rust scanner writer fails at INSERT time. Guard A surfaces
-- the drift at migration apply.
--
-- 回補（AUDIT-2026-05-02-P1-1，2026-05-02）：依 CLAUDE.md §七 補上
-- Guard A。CC 4 天 cold audit 發現 V030 漏 guard；若存在 legacy stub
-- （例如早期 prototype 缺 candidates JSONB / config JSONB），CREATE
-- TABLE IF NOT EXISTS 會靜默 no-op，下游 scanner writer INSERT 才報錯。
--
-- Template source / 模板來源：
--   sql/migrations/templates/schema_guard_template.sql § Guard A

-- ------------------------------------------------------------
-- Schema Guard A — verify scanner_snapshots required columns when present
-- Schema Guard A — 表已存在時驗必要欄位俱在
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'trading'
          AND table_name   = 'scanner_snapshots'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'ts', 'scan_id', 'active_symbols',
            'added', 'removed', 'rejected_count',
            'scan_duration_ms', 'candidates', 'config'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'trading'
              AND table_name   = 'scanner_snapshots'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: trading.scanner_snapshots exists but missing required columns: %. '
                'Likely a legacy/prototype stub is present. Resolve (DROP + re-apply V030, '
                'or ALTER TABLE ADD missing columns) before continuing.',
                v_missing;
        END IF;
    END IF;
END $$;

-- ------------------------------------------------------------
-- Original V030 body (unchanged) / 原 V030 主體（未動）
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS trading.scanner_snapshots (
    ts               TIMESTAMPTZ NOT NULL,
    scan_id          TEXT        NOT NULL,
    active_symbols   TEXT[]      NOT NULL,
    added            TEXT[]      NOT NULL,
    removed          TEXT[]      NOT NULL,
    rejected_count   BIGINT      NOT NULL,
    scan_duration_ms BIGINT      NOT NULL,
    candidates       JSONB       NOT NULL,
    config           JSONB       NOT NULL,
    PRIMARY KEY (scan_id, ts)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
        PERFORM create_hypertable('trading.scanner_snapshots', 'ts',
            chunk_time_interval => INTERVAL '7 days',
            if_not_exists => TRUE);
    END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_ts
    ON trading.scanner_snapshots (ts DESC);

CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_scan_id
    ON trading.scanner_snapshots (scan_id);

COMMENT ON TABLE trading.scanner_snapshots IS
    'Market scanner cycle snapshots, including edge-aware candidate routing metadata.';

-- V156: ALR fresh/history lane 與 truthful health 的 append-only runtime state。
--
-- 僅新增 learning.alr_* 狀態與 health typed projections；不修改 trading.*。

BEGIN;

-- 讓 pg_get_constraintdef 的 schema qualification 不受 caller/sqlx
-- search_path 影響；SET LOCAL 只在本 transaction 有效。
SET LOCAL search_path = pg_catalog, pg_temp, public;

-- Guard A：V155 health table 必須先存在，避免 ALTER 落在錯誤 schema head。
DO $$
BEGIN
    IF to_regclass('learning.alr_health_events') IS NULL THEN
        RAISE EXCEPTION 'V156 Guard A FAIL: learning.alr_health_events missing; apply V155 first';
    END IF;
END $$;

-- Cursor event 必須可由 source identity + hash 結構化回指 V151 ledger。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'alr_source_events_cursor_lineage_uniq'
          AND conrelid = 'learning.alr_source_events'::regclass
    ) THEN
        ALTER TABLE learning.alr_source_events
            ADD CONSTRAINT alr_source_events_cursor_lineage_uniq
            UNIQUE (source_ts, source_scan_id, source_hash);
    END IF;
    IF (
        SELECT pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conname = 'alr_source_events_cursor_lineage_uniq'
          AND conrelid = 'learning.alr_source_events'::regclass
    ) <> 'UNIQUE (source_ts, source_scan_id, source_hash)' THEN
        RAISE EXCEPTION 'V156 Guard A FAIL: source lineage UNIQUE shape mismatch';
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.alr_consumer_events (
    event_id UUID NOT NULL,
    session_id UUID NOT NULL,
    event_kind TEXT NOT NULL,
    lane TEXT,
    source_ts TIMESTAMPTZ,
    source_scan_id TEXT,
    source_hash TEXT,
    notification_ts_ms BIGINT,
    error_code TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT alr_consumer_events_pk PRIMARY KEY (event_id),
    CONSTRAINT alr_consumer_events_kind_check CHECK (event_kind IN (
        'SESSION_STARTED', 'SESSION_STOPPED', 'SESSION_FAILED',
        'UNCLEAN_RECOVERY', 'NOTIFICATION_RECEIVED',
        'NOTIFICATION_CONSUMED', 'NOTIFICATION_DUPLICATE', 'NOTIFICATION_INVALID',
        'LANE_BOOTSTRAPPED', 'LANE_CURSOR_ADVANCED', 'LANE_SUCCESS'
    )),
    CONSTRAINT alr_consumer_events_lane_check CHECK (
        lane IS NULL OR lane IN ('FRESH', 'HISTORICAL')
    ),
    CONSTRAINT alr_consumer_events_source_hash_check CHECK (
        source_hash IS NULL OR source_hash ~ '^[0-9a-f]{64}$'
    ),
    CONSTRAINT alr_consumer_events_notification_ts_check CHECK (
        notification_ts_ms IS NULL OR notification_ts_ms >= 0
    ),
    CONSTRAINT alr_consumer_events_cursor_identity_check CHECK (
        event_kind NOT IN ('LANE_BOOTSTRAPPED', 'LANE_CURSOR_ADVANCED')
        OR (lane IS NOT NULL AND source_ts IS NOT NULL
            AND source_scan_id IS NOT NULL AND source_hash IS NOT NULL)
    ),
    CONSTRAINT alr_consumer_events_failure_code_check CHECK (
        event_kind <> 'SESSION_FAILED' OR error_code IS NOT NULL
    )
);

-- V156 首次建表；若 partial object 已含 phantom lineage，migration 必須 fail。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'alr_consumer_events_source_lineage_fk'
          AND conrelid = 'learning.alr_consumer_events'::regclass
    ) THEN
        ALTER TABLE learning.alr_consumer_events
            ADD CONSTRAINT alr_consumer_events_source_lineage_fk
            FOREIGN KEY (source_ts, source_scan_id, source_hash)
            REFERENCES learning.alr_source_events (
                source_ts, source_scan_id, source_hash
            );
    END IF;
END $$;

-- 用相同 parser 建立 transaction-local expected constraints；Guard A 比較
-- catalog parse tree，不接受同名 CHECK(TRUE) 或尾加 OR TRUE 的弱化物件。
CREATE TEMP TABLE alr_v156_expected_consumer_events
    (LIKE learning.alr_consumer_events INCLUDING DEFAULTS)
    ON COMMIT DROP;
ALTER TABLE alr_v156_expected_consumer_events
    ADD CONSTRAINT alr_v156_expected_consumer_pk PRIMARY KEY (event_id),
    ADD CONSTRAINT alr_v156_expected_consumer_kind CHECK (event_kind IN (
        'SESSION_STARTED', 'SESSION_STOPPED', 'SESSION_FAILED',
        'UNCLEAN_RECOVERY', 'NOTIFICATION_RECEIVED',
        'NOTIFICATION_CONSUMED', 'NOTIFICATION_DUPLICATE', 'NOTIFICATION_INVALID',
        'LANE_BOOTSTRAPPED', 'LANE_CURSOR_ADVANCED', 'LANE_SUCCESS'
    )),
    ADD CONSTRAINT alr_v156_expected_consumer_lane CHECK (
        lane IS NULL OR lane IN ('FRESH', 'HISTORICAL')
    ),
    ADD CONSTRAINT alr_v156_expected_consumer_hash CHECK (
        source_hash IS NULL OR source_hash ~ '^[0-9a-f]{64}$'
    ),
    ADD CONSTRAINT alr_v156_expected_consumer_notification CHECK (
        notification_ts_ms IS NULL OR notification_ts_ms >= 0
    ),
    ADD CONSTRAINT alr_v156_expected_consumer_cursor CHECK (
        event_kind NOT IN ('LANE_BOOTSTRAPPED', 'LANE_CURSOR_ADVANCED')
        OR (lane IS NOT NULL AND source_ts IS NOT NULL
            AND source_scan_id IS NOT NULL AND source_hash IS NOT NULL)
    ),
    ADD CONSTRAINT alr_v156_expected_consumer_failure CHECK (
        event_kind <> 'SESSION_FAILED' OR error_code IS NOT NULL
    );

-- Guard A：CREATE IF NOT EXISTS 不得掩蓋 partial/錯型別既有物件。
DO $$
DECLARE
    expected RECORD;
    actual RECORD;
    constraint_pair RECORD;
    actual_constraint RECORD;
    expected_constraint RECORD;
BEGIN
    FOR expected IN
        SELECT * FROM (VALUES
            ('event_id', 'uuid', 'NO', NULL::text),
            ('session_id', 'uuid', 'NO', NULL::text),
            ('event_kind', 'text', 'NO', NULL::text),
            ('lane', 'text', 'YES', NULL::text),
            ('source_ts', 'timestamp with time zone', 'YES', NULL::text),
            ('source_scan_id', 'text', 'YES', NULL::text),
            ('source_hash', 'text', 'YES', NULL::text),
            ('notification_ts_ms', 'bigint', 'YES', NULL::text),
            ('error_code', 'text', 'YES', NULL::text),
            ('details', 'jsonb', 'NO', '''{}''::jsonb'),
            ('recorded_at', 'timestamp with time zone', 'NO', 'clock_timestamp()')
        ) AS columns(column_name, data_type, is_nullable, default_fragment)
    LOOP
        SELECT data_type, is_nullable, column_default INTO actual
        FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'alr_consumer_events'
          AND column_name = expected.column_name;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'V156 Guard A FAIL: alr_consumer_events.% missing',
                expected.column_name;
        END IF;
        IF actual.data_type <> expected.data_type
           OR actual.is_nullable <> expected.is_nullable
           OR (expected.default_fragment IS NULL AND actual.column_default IS NOT NULL)
           OR (expected.default_fragment IS NOT NULL AND position(
                expected.default_fragment IN coalesce(actual.column_default, '')
              ) = 0) THEN
            RAISE EXCEPTION 'V156 Guard A FAIL: alr_consumer_events.% shape mismatch',
                expected.column_name;
        END IF;
    END LOOP;
    FOR constraint_pair IN
        SELECT * FROM (VALUES
            ('alr_consumer_events_pk', 'alr_v156_expected_consumer_pk'),
            ('alr_consumer_events_kind_check', 'alr_v156_expected_consumer_kind'),
            ('alr_consumer_events_lane_check', 'alr_v156_expected_consumer_lane'),
            ('alr_consumer_events_source_hash_check', 'alr_v156_expected_consumer_hash'),
            ('alr_consumer_events_notification_ts_check', 'alr_v156_expected_consumer_notification'),
            ('alr_consumer_events_cursor_identity_check', 'alr_v156_expected_consumer_cursor'),
            ('alr_consumer_events_failure_code_check', 'alr_v156_expected_consumer_failure')
        ) AS constraints(actual_name, expected_name)
    LOOP
        SELECT contype, conkey::text, confkey::text, confrelid,
               convalidated,
               condeferrable, condeferred, connoinherit,
               confupdtype, confdeltype, confmatchtype,
               conpfeqop::text, conppeqop::text, conffeqop::text,
               conexclop::text, pg_get_constraintdef(oid, false) AS definition
        INTO actual_constraint
        FROM pg_constraint
        WHERE conname = constraint_pair.actual_name
          AND conrelid = 'learning.alr_consumer_events'::regclass;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'V156 Guard A FAIL: required constraint missing: %',
                constraint_pair.actual_name;
        END IF;
        SELECT contype, conkey::text, confkey::text, confrelid,
               convalidated,
               condeferrable, condeferred, connoinherit,
               confupdtype, confdeltype, confmatchtype,
               conpfeqop::text, conppeqop::text, conffeqop::text,
               conexclop::text, pg_get_constraintdef(oid, false) AS definition
        INTO expected_constraint
        FROM pg_constraint
        WHERE conname = constraint_pair.expected_name
          AND conrelid = 'alr_v156_expected_consumer_events'::regclass;
        IF actual_constraint.contype IS DISTINCT FROM expected_constraint.contype
           OR actual_constraint.conkey IS DISTINCT FROM expected_constraint.conkey
           OR actual_constraint.confkey IS DISTINCT FROM expected_constraint.confkey
           OR actual_constraint.confrelid IS DISTINCT FROM expected_constraint.confrelid
           OR actual_constraint.convalidated IS DISTINCT FROM expected_constraint.convalidated
           OR actual_constraint.condeferrable IS DISTINCT FROM expected_constraint.condeferrable
           OR actual_constraint.condeferred IS DISTINCT FROM expected_constraint.condeferred
           OR actual_constraint.connoinherit IS DISTINCT FROM expected_constraint.connoinherit
           OR actual_constraint.confupdtype IS DISTINCT FROM expected_constraint.confupdtype
           OR actual_constraint.confdeltype IS DISTINCT FROM expected_constraint.confdeltype
           OR actual_constraint.confmatchtype IS DISTINCT FROM expected_constraint.confmatchtype
           OR actual_constraint.conpfeqop IS DISTINCT FROM expected_constraint.conpfeqop
           OR actual_constraint.conppeqop IS DISTINCT FROM expected_constraint.conppeqop
           OR actual_constraint.conffeqop IS DISTINCT FROM expected_constraint.conffeqop
           OR actual_constraint.conexclop IS DISTINCT FROM expected_constraint.conexclop
           OR actual_constraint.definition IS DISTINCT FROM expected_constraint.definition THEN
            RAISE EXCEPTION 'V156 Guard A FAIL: constraint definition mismatch: %',
                constraint_pair.actual_name;
        END IF;
    END LOOP;

    -- PostgreSQL 不允許 TEMP table FK 指向 permanent table；因此 lineage FK
    -- 以完整 canonical definition、key attnums、action/match 與 equality ops 驗證。
    SELECT contype, conkey::text, confkey::text, confrelid,
           convalidated, condeferrable, condeferred, connoinherit,
           confupdtype, confdeltype, confmatchtype,
           conpfeqop::text, conppeqop::text, conffeqop::text,
           conexclop::text, pg_get_constraintdef(oid, false) AS definition
    INTO actual_constraint
    FROM pg_constraint
    WHERE conname = 'alr_consumer_events_source_lineage_fk'
      AND conrelid = 'learning.alr_consumer_events'::regclass;
    IF NOT FOUND
       OR actual_constraint.contype <> 'f'
       OR actual_constraint.conkey <> ARRAY[
            (SELECT attnum FROM pg_attribute
             WHERE attrelid = 'learning.alr_consumer_events'::regclass
               AND attname = 'source_ts'),
            (SELECT attnum FROM pg_attribute
             WHERE attrelid = 'learning.alr_consumer_events'::regclass
               AND attname = 'source_scan_id'),
            (SELECT attnum FROM pg_attribute
             WHERE attrelid = 'learning.alr_consumer_events'::regclass
               AND attname = 'source_hash')
          ]::smallint[]::text
       OR actual_constraint.confkey <> ARRAY[
            (SELECT attnum FROM pg_attribute
             WHERE attrelid = 'learning.alr_source_events'::regclass
               AND attname = 'source_ts'),
            (SELECT attnum FROM pg_attribute
             WHERE attrelid = 'learning.alr_source_events'::regclass
               AND attname = 'source_scan_id'),
            (SELECT attnum FROM pg_attribute
             WHERE attrelid = 'learning.alr_source_events'::regclass
               AND attname = 'source_hash')
          ]::smallint[]::text
       OR actual_constraint.confrelid <> 'learning.alr_source_events'::regclass
       OR actual_constraint.convalidated IS NOT TRUE
       OR actual_constraint.condeferrable IS NOT FALSE
       OR actual_constraint.condeferred IS NOT FALSE
       OR actual_constraint.connoinherit IS NOT TRUE
       OR actual_constraint.confupdtype <> 'a'
       OR actual_constraint.confdeltype <> 'a'
       OR actual_constraint.confmatchtype <> 's'
       OR actual_constraint.conpfeqop IS DISTINCT FROM actual_constraint.conppeqop
       OR actual_constraint.conpfeqop IS DISTINCT FROM actual_constraint.conffeqop
       OR cardinality(actual_constraint.conpfeqop::oid[]) <> 3
       OR actual_constraint.conexclop IS NOT NULL
       OR actual_constraint.definition <>
          'FOREIGN KEY (source_ts, source_scan_id, source_hash) REFERENCES learning.alr_source_events(source_ts, source_scan_id, source_hash)' THEN
        RAISE EXCEPTION 'V156 Guard A FAIL: source lineage FK definition mismatch';
    END IF;
END $$;

-- Guard B：ADD COLUMN IF NOT EXISTS 前先驗證既有同名欄型別。
DO $$
DECLARE
    expected RECORD;
    actual RECORD;
BEGIN
    FOR expected IN
        SELECT * FROM (VALUES
            ('raw_latest_ts', 'timestamp with time zone'),
            ('alr_latest_source_ts', 'timestamp with time zone'),
            ('fresh_cursor_ts', 'timestamp with time zone'),
            ('fresh_cursor_scan_id', 'text'),
            ('fresh_bootstrap_ts', 'timestamp with time zone'),
            ('fresh_bootstrap_scan_id', 'text'),
            ('ingest_lag_seconds', 'double precision'),
            ('fresh_raw_only_count', 'bigint'),
            ('historical_backfill_remaining', 'bigint'),
            ('notifications_received', 'bigint'),
            ('notifications_consumed', 'bigint'),
            ('notifications_duplicate', 'bigint'),
            ('notifications_invalid', 'bigint'),
            ('last_success_at', 'timestamp with time zone'),
            ('failure_count', 'bigint'),
            ('restart_count', 'bigint'),
            ('unclean_recovery_count', 'bigint'),
            ('untrained_source_cycle_count', 'bigint'),
            ('ingestion_alert', 'boolean')
        ) AS columns(column_name, data_type)
    LOOP
        SELECT data_type, is_nullable, column_default INTO actual
        FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'alr_health_events'
          AND column_name = expected.column_name;
        IF FOUND AND (
            actual.data_type <> expected.data_type
            OR actual.is_nullable <> 'YES'
            OR actual.column_default IS NOT NULL
        ) THEN
            RAISE EXCEPTION 'V156 Guard B FAIL: alr_health_events.% shape mismatch',
                expected.column_name;
        END IF;
    END LOOP;
END $$;

ALTER TABLE learning.alr_health_events
    ADD COLUMN IF NOT EXISTS raw_latest_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS alr_latest_source_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS fresh_cursor_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS fresh_cursor_scan_id TEXT,
    ADD COLUMN IF NOT EXISTS fresh_bootstrap_ts TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS fresh_bootstrap_scan_id TEXT,
    ADD COLUMN IF NOT EXISTS ingest_lag_seconds DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS fresh_raw_only_count BIGINT,
    ADD COLUMN IF NOT EXISTS historical_backfill_remaining BIGINT,
    ADD COLUMN IF NOT EXISTS notifications_received BIGINT,
    ADD COLUMN IF NOT EXISTS notifications_consumed BIGINT,
    ADD COLUMN IF NOT EXISTS notifications_duplicate BIGINT,
    ADD COLUMN IF NOT EXISTS notifications_invalid BIGINT,
    ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS failure_count BIGINT,
    ADD COLUMN IF NOT EXISTS restart_count BIGINT,
    ADD COLUMN IF NOT EXISTS unclean_recovery_count BIGINT,
    ADD COLUMN IF NOT EXISTS untrained_source_cycle_count BIGINT,
    ADD COLUMN IF NOT EXISTS ingestion_alert BOOLEAN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'alr_health_events_freshness_nonnegative_check'
          AND conrelid = 'learning.alr_health_events'::regclass
    ) THEN
        ALTER TABLE learning.alr_health_events
            ADD CONSTRAINT alr_health_events_freshness_nonnegative_check CHECK (
                (ingest_lag_seconds IS NULL OR ingest_lag_seconds >= 0)
                AND (fresh_raw_only_count IS NULL OR fresh_raw_only_count >= 0)
                AND (historical_backfill_remaining IS NULL OR historical_backfill_remaining >= 0)
                AND (notifications_received IS NULL OR notifications_received >= 0)
                AND (notifications_consumed IS NULL OR notifications_consumed >= 0)
                AND (notifications_duplicate IS NULL OR notifications_duplicate >= 0)
                AND (notifications_invalid IS NULL OR notifications_invalid >= 0)
                AND (failure_count IS NULL OR failure_count >= 0)
                AND (restart_count IS NULL OR restart_count >= 0)
                AND (unclean_recovery_count IS NULL OR unclean_recovery_count >= 0)
                AND (untrained_source_cycle_count IS NULL OR untrained_source_cycle_count >= 0)
            );
    END IF;
END $$;

CREATE TEMP TABLE alr_v156_expected_health_events
    (LIKE learning.alr_health_events INCLUDING DEFAULTS)
    ON COMMIT DROP;
ALTER TABLE alr_v156_expected_health_events
    ADD CONSTRAINT alr_v156_expected_health_nonnegative CHECK (
        (ingest_lag_seconds IS NULL OR ingest_lag_seconds >= 0)
        AND (fresh_raw_only_count IS NULL OR fresh_raw_only_count >= 0)
        AND (historical_backfill_remaining IS NULL OR historical_backfill_remaining >= 0)
        AND (notifications_received IS NULL OR notifications_received >= 0)
        AND (notifications_consumed IS NULL OR notifications_consumed >= 0)
        AND (notifications_duplicate IS NULL OR notifications_duplicate >= 0)
        AND (notifications_invalid IS NULL OR notifications_invalid >= 0)
        AND (failure_count IS NULL OR failure_count >= 0)
        AND (restart_count IS NULL OR restart_count >= 0)
        AND (unclean_recovery_count IS NULL OR unclean_recovery_count >= 0)
        AND (untrained_source_cycle_count IS NULL OR untrained_source_cycle_count >= 0)
    );

DO $$
DECLARE
    actual_constraint RECORD;
    expected_constraint RECORD;
BEGIN
    SELECT contype, conkey::text, convalidated, condeferrable, condeferred,
           pg_get_constraintdef(oid, false) AS definition
    INTO actual_constraint
    FROM pg_constraint
    WHERE conname = 'alr_health_events_freshness_nonnegative_check'
      AND conrelid = 'learning.alr_health_events'::regclass;
    SELECT contype, conkey::text, convalidated, condeferrable, condeferred,
           pg_get_constraintdef(oid, false) AS definition
    INTO expected_constraint
    FROM pg_constraint
    WHERE conname = 'alr_v156_expected_health_nonnegative'
      AND conrelid = 'alr_v156_expected_health_events'::regclass;
    IF NOT FOUND
       OR actual_constraint.contype IS DISTINCT FROM expected_constraint.contype
       OR actual_constraint.conkey IS DISTINCT FROM expected_constraint.conkey
       OR actual_constraint.convalidated IS DISTINCT FROM expected_constraint.convalidated
       OR actual_constraint.condeferrable IS DISTINCT FROM expected_constraint.condeferrable
       OR actual_constraint.condeferred IS DISTINCT FROM expected_constraint.condeferred
       OR actual_constraint.definition IS DISTINCT FROM expected_constraint.definition THEN
        RAISE EXCEPTION 'V156 Guard B FAIL: health nonnegative constraint mismatch';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_alr_consumer_events_lane_cursor
    ON learning.alr_consumer_events (
        lane, source_ts DESC, source_scan_id DESC, event_id DESC
    )
    WHERE event_kind IN ('LANE_BOOTSTRAPPED', 'LANE_CURSOR_ADVANCED');

CREATE INDEX IF NOT EXISTS idx_alr_consumer_events_session_lifecycle
    ON learning.alr_consumer_events (session_id, recorded_at ASC, event_id ASC)
    WHERE event_kind IN ('SESSION_STARTED', 'SESSION_STOPPED', 'SESSION_FAILED');

CREATE INDEX IF NOT EXISTS idx_alr_consumer_events_kind_recorded
    ON learning.alr_consumer_events (event_kind, recorded_at DESC);

CREATE INDEX alr_v156_expected_lane_cursor_idx
    ON alr_v156_expected_consumer_events (
        lane, source_ts DESC, source_scan_id DESC, event_id DESC
    )
    WHERE event_kind IN ('LANE_BOOTSTRAPPED', 'LANE_CURSOR_ADVANCED');
CREATE INDEX alr_v156_expected_session_lifecycle_idx
    ON alr_v156_expected_consumer_events (session_id, recorded_at ASC, event_id ASC)
    WHERE event_kind IN ('SESSION_STARTED', 'SESSION_STOPPED', 'SESSION_FAILED');
CREATE INDEX alr_v156_expected_kind_recorded_idx
    ON alr_v156_expected_consumer_events (event_kind, recorded_at DESC);

-- Guard C：consumer hot-path cursor/lifecycle indexes 必須存在。
DO $$
DECLARE
    index_pair RECORD;
    actual_index RECORD;
    expected_index RECORD;
BEGIN
    FOR index_pair IN
        SELECT * FROM (VALUES
            ('idx_alr_consumer_events_lane_cursor', 'alr_v156_expected_lane_cursor_idx'),
            ('idx_alr_consumer_events_session_lifecycle', 'alr_v156_expected_session_lifecycle_idx'),
            ('idx_alr_consumer_events_kind_recorded', 'alr_v156_expected_kind_recorded_idx')
        ) AS indexes(actual_name, expected_name)
    LOOP
        SELECT indexrel.relam, idx.indkey::text, idx.indoption::text,
               idx.indclass::text, idx.indcollation::text,
               coalesce(pg_get_expr(idx.indexprs, idx.indrelid, false), '') AS indexprs,
               coalesce(pg_get_expr(idx.indpred, idx.indrelid, false), '') AS indpred,
               idx.indnkeyatts, idx.indnatts, idx.indisunique,
               idx.indnullsnotdistinct, idx.indisprimary,
               idx.indisexclusion, idx.indimmediate, idx.indisclustered,
               idx.indisvalid, idx.indcheckxmin, idx.indisready,
               idx.indislive, idx.indisreplident
        INTO actual_index
        FROM pg_index AS idx
        JOIN pg_class AS indexrel ON indexrel.oid = idx.indexrelid
        WHERE idx.indexrelid = format('learning.%I', index_pair.actual_name)::regclass;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'V156 Guard C FAIL: required index missing: %',
                index_pair.actual_name;
        END IF;
        SELECT indexrel.relam, idx.indkey::text, idx.indoption::text,
               idx.indclass::text, idx.indcollation::text,
               coalesce(pg_get_expr(idx.indexprs, idx.indrelid, false), '') AS indexprs,
               coalesce(pg_get_expr(idx.indpred, idx.indrelid, false), '') AS indpred,
               idx.indnkeyatts, idx.indnatts, idx.indisunique,
               idx.indnullsnotdistinct, idx.indisprimary,
               idx.indisexclusion, idx.indimmediate, idx.indisclustered,
               idx.indisvalid, idx.indcheckxmin, idx.indisready,
               idx.indislive, idx.indisreplident
        INTO expected_index
        FROM pg_index AS idx
        JOIN pg_class AS indexrel ON indexrel.oid = idx.indexrelid
        WHERE idx.indexrelid = format('pg_temp.%I', index_pair.expected_name)::regclass;
        IF actual_index.relam IS DISTINCT FROM expected_index.relam
           OR actual_index.indkey IS DISTINCT FROM expected_index.indkey
           OR actual_index.indoption IS DISTINCT FROM expected_index.indoption
           OR actual_index.indclass IS DISTINCT FROM expected_index.indclass
           OR actual_index.indcollation IS DISTINCT FROM expected_index.indcollation
           OR actual_index.indexprs IS DISTINCT FROM expected_index.indexprs
           OR actual_index.indpred IS DISTINCT FROM expected_index.indpred
           OR actual_index.indnkeyatts IS DISTINCT FROM expected_index.indnkeyatts
           OR actual_index.indnatts IS DISTINCT FROM expected_index.indnatts
           OR actual_index.indisunique IS DISTINCT FROM expected_index.indisunique
           OR actual_index.indnullsnotdistinct IS DISTINCT FROM expected_index.indnullsnotdistinct
           OR actual_index.indisprimary IS DISTINCT FROM expected_index.indisprimary
           OR actual_index.indisexclusion IS DISTINCT FROM expected_index.indisexclusion
           OR actual_index.indimmediate IS DISTINCT FROM expected_index.indimmediate
           OR actual_index.indisclustered IS DISTINCT FROM expected_index.indisclustered
           OR actual_index.indisvalid IS DISTINCT FROM expected_index.indisvalid
           OR actual_index.indcheckxmin IS DISTINCT FROM expected_index.indcheckxmin
           OR actual_index.indisready IS DISTINCT FROM expected_index.indisready THEN
            RAISE EXCEPTION 'V156 Guard C FAIL: index definition mismatch: %',
                index_pair.actual_name;
        END IF;
        IF actual_index.indislive IS DISTINCT FROM expected_index.indislive
           OR actual_index.indisreplident IS DISTINCT FROM expected_index.indisreplident THEN
            RAISE EXCEPTION 'V156 Guard C FAIL: index definition mismatch: %',
                index_pair.actual_name;
        END IF;
    END LOOP;
END $$;

REVOKE UPDATE, DELETE ON learning.alr_consumer_events FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trading_ai') THEN
        REVOKE UPDATE, DELETE ON learning.alr_consumer_events FROM trading_ai;
        GRANT SELECT, INSERT ON learning.alr_consumer_events TO trading_ai;
    END IF;
END $$;

COMMENT ON TABLE learning.alr_consumer_events IS
    'Immutable ALR session, notification, and independent fresh/history cursor events.';
COMMENT ON COLUMN learning.alr_health_events.fresh_raw_only_count IS
    'Raw-only scanner identities after the immutable fresh bootstrap anchor.';
COMMENT ON COLUMN learning.alr_health_events.historical_backfill_remaining IS
    'Raw-only identities before the immutable fresh bootstrap boundary.';

COMMIT;

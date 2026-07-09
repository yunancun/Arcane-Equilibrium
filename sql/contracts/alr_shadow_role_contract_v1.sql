-- P2-3 least-privilege role contract.  Source-only until the fresh E3/BB
-- prestart gate.  The operator creates the login and its private 0600 DSN
-- outside this file; credentials never belong in repository SQL.
--
-- This contract intentionally grants only local scanner evidence read plus
-- append-only ALR ledger read/insert.  It grants no order, fill, proof,
-- serving, promotion, schema-create, or administration capability.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'alr_shadow') THEN
        RAISE EXCEPTION 'alr_shadow role must be created through the gated secure path first';
    END IF;
END $$;

ALTER ROLE alr_shadow NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 2;

REVOKE ALL PRIVILEGES ON DATABASE trading_ai FROM alr_shadow;
GRANT CONNECT ON DATABASE trading_ai TO alr_shadow;

REVOKE ALL ON SCHEMA trading FROM alr_shadow;
REVOKE ALL ON SCHEMA learning FROM alr_shadow;
GRANT USAGE ON SCHEMA trading TO alr_shadow;
GRANT USAGE ON SCHEMA learning TO alr_shadow;

REVOKE ALL ON TABLE trading.scanner_snapshots FROM alr_shadow;
GRANT SELECT ON TABLE trading.scanner_snapshots TO alr_shadow;

REVOKE ALL ON TABLE learning.alr_artifact_nodes FROM alr_shadow;
REVOKE ALL ON TABLE learning.alr_source_events FROM alr_shadow;
REVOKE ALL ON TABLE learning.alr_ingest_events FROM alr_shadow;
REVOKE ALL ON TABLE learning.alr_watermark_events FROM alr_shadow;
REVOKE ALL ON TABLE learning.alr_provenance_edges FROM alr_shadow;
REVOKE ALL ON TABLE learning.alr_training_runs FROM alr_shadow;

GRANT SELECT, INSERT ON TABLE learning.alr_artifact_nodes TO alr_shadow;
GRANT SELECT, INSERT ON TABLE learning.alr_source_events TO alr_shadow;
GRANT SELECT, INSERT ON TABLE learning.alr_ingest_events TO alr_shadow;
GRANT SELECT, INSERT ON TABLE learning.alr_watermark_events TO alr_shadow;
GRANT SELECT, INSERT ON TABLE learning.alr_provenance_edges TO alr_shadow;
GRANT SELECT, INSERT ON TABLE learning.alr_training_runs TO alr_shadow;

COMMIT;

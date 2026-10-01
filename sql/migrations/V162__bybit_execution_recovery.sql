-- H2: one PG-owned recovery checkpoint, immutable intents, durable inbox.
-- No retention/TTL: deleting an execution identity would reopen replay risk.
-- Guard A rejects a pre-existing incompatible object, including a partial manual
-- preparation. Compatible reruns are verified by exact column and PK signatures.
DO $guard$
DECLARE name TEXT; expected TEXT; actual TEXT; pk TEXT;
BEGIN
    FOR name,expected,pk IN VALUES
      ('bybit_recovery','engine_mode:text:true,account_scope:text:true,generation:bigint:true,checkpoint:jsonb:true','engine_mode'),
      ('bybit_order_intents','engine_mode:text:true,order_link_id:text:true,request_hash:text:true,request:jsonb:true,pending:jsonb:true,progress:jsonb:true,venue_order_id:text:false','engine_mode,order_link_id'),
      ('bybit_execution_inbox','engine_mode:text:true,exec_id:text:true,receive_seq:bigint:true,payload:jsonb:true,applied:boolean:true','engine_mode,exec_id')
    LOOP
      IF to_regclass('trading.'||name) IS NOT NULL THEN
        IF NOT EXISTS(SELECT 1 FROM pg_class WHERE oid=to_regclass('trading.'||name) AND relkind='r') THEN
          RAISE EXCEPTION 'V162 Guard A: % must be ordinary table',name;
        END IF;
        SELECT string_agg(attname||':'||format_type(atttypid,atttypmod)||':'||attnotnull,',' ORDER BY attnum)
          INTO actual FROM pg_attribute WHERE attrelid=to_regclass('trading.'||name) AND attnum>0 AND NOT attisdropped;
        IF actual IS DISTINCT FROM expected THEN RAISE EXCEPTION 'V162 Guard A: incompatible % columns',name; END IF;
        SELECT string_agg(a.attname,',' ORDER BY k.ordinality) INTO actual
          FROM pg_constraint c CROSS JOIN LATERAL unnest(c.conkey) WITH ORDINALITY k(attnum,ordinality)
          JOIN pg_attribute a ON a.attrelid=c.conrelid AND a.attnum=k.attnum
          WHERE c.conrelid=to_regclass('trading.'||name) AND c.contype='p';
        IF actual IS DISTINCT FROM pk THEN RAISE EXCEPTION 'V162 Guard A: incompatible % primary key',name; END IF;
        IF name='bybit_order_intents' AND NOT EXISTS (
          SELECT 1 FROM pg_constraint c WHERE c.conrelid=to_regclass('trading.'||name)
          AND c.contype='u' AND c.conkey=ARRAY[
            (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='engine_mode'),
            (SELECT attnum FROM pg_attribute WHERE attrelid=c.conrelid AND attname='venue_order_id')
          ]::smallint[]
        ) THEN RAISE EXCEPTION 'V162 Guard A: missing unique venue identity'; END IF;
        IF name='bybit_execution_inbox' AND NOT EXISTS (
          SELECT 1 FROM pg_attribute a JOIN pg_attrdef d
            ON d.adrelid=a.attrelid AND d.adnum=a.attnum
          WHERE a.attrelid=to_regclass('trading.'||name) AND a.attname='applied'
            AND pg_get_expr(d.adbin,d.adrelid)='false'
        ) THEN RAISE EXCEPTION 'V162 Guard A: applied default must be false'; END IF;
        IF name='bybit_execution_inbox' AND NOT EXISTS (
          SELECT 1 FROM pg_attribute WHERE attrelid=to_regclass('trading.'||name)
          AND attname='receive_seq' AND attidentity='a'
        ) THEN RAISE EXCEPTION 'V162 Guard A: missing receive sequence identity'; END IF;

      END IF;
    END LOOP;
END
$guard$;
CREATE TABLE IF NOT EXISTS trading.bybit_recovery (
    engine_mode TEXT PRIMARY KEY, account_scope TEXT NOT NULL,
    generation BIGINT NOT NULL, checkpoint JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS trading.bybit_order_intents (
    engine_mode TEXT NOT NULL, order_link_id TEXT NOT NULL,
    request_hash TEXT NOT NULL, request JSONB NOT NULL, pending JSONB NOT NULL,
    progress JSONB NOT NULL, venue_order_id TEXT,
    UNIQUE(engine_mode,venue_order_id),
    PRIMARY KEY(engine_mode,order_link_id)
);
CREATE TABLE IF NOT EXISTS trading.bybit_execution_inbox (
    engine_mode TEXT NOT NULL, exec_id TEXT NOT NULL,
    receive_seq BIGINT GENERATED ALWAYS AS IDENTITY NOT NULL,
    payload JSONB NOT NULL, applied BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY(engine_mode,exec_id)
);
-- Index creation is on the new empty table; no hot-table index build.
DO $guard_c$
BEGIN
    IF to_regclass('trading.bybit_execution_unapplied') IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM pg_index i
        JOIN pg_class c ON c.oid=i.indexrelid
        JOIN pg_am am ON am.oid=c.relam
        WHERE i.indexrelid=to_regclass('trading.bybit_execution_unapplied')
          AND i.indrelid='trading.bybit_execution_inbox'::regclass
          AND am.amname='btree' AND i.indisvalid AND i.indisready
          AND NOT i.indisunique AND i.indnkeyatts=2 AND i.indnatts=2
          AND i.indexprs IS NULL AND i.indoption[0]=0 AND i.indoption[1]=0
          AND (SELECT string_agg(a.attname,',' ORDER BY k.ordinality)
               FROM unnest(i.indkey) WITH ORDINALITY k(attnum,ordinality)
               JOIN pg_attribute a ON a.attrelid=i.indrelid AND a.attnum=k.attnum)
              ='engine_mode,receive_seq'
          AND pg_get_expr(i.indpred,i.indrelid) IN ('(NOT applied)','NOT applied')
    ) THEN
        RAISE EXCEPTION 'V162 Guard C: incompatible unapplied execution index';
    END IF;
END
$guard_c$;
CREATE INDEX IF NOT EXISTS bybit_execution_unapplied ON trading.bybit_execution_inbox(engine_mode,receive_seq) WHERE NOT applied;
DO $grant$
BEGIN
    IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='trading_ai') THEN
        GRANT SELECT,INSERT,UPDATE ON trading.bybit_recovery,trading.bybit_execution_inbox TO trading_ai;
        GRANT SELECT,INSERT,UPDATE ON trading.bybit_order_intents TO trading_ai;
        GRANT USAGE ON SEQUENCE trading.bybit_execution_inbox_receive_seq_seq TO trading_ai;
    END IF;
END
$grant$;

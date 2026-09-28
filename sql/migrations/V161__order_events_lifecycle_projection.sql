-- H1: project causal lifecycle progress, independent of venue/local clock skew.
-- V161 is new in this PR; applied migrations (including V005) remain unchanged.
-- Add a nullable column first: do not rewrite historical compressed chunks.
-- Only new writes receive insertion ordinals; legacy rows retain timestamp order.
-- Guard A/B: existing objects must have the exact ordinal contract. Replays
-- and partial manual preparation are accepted only when their shape is safe.
DO $guard$
BEGIN
    IF to_regclass('trading.order_state_changes') IS NULL THEN
        RAISE EXCEPTION 'V161 Guard A: missing trading.order_state_changes';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_attribute
        WHERE attrelid = 'trading.order_state_changes'::regclass
          AND attname = 'lifecycle_seq' AND NOT attisdropped
          AND (atttypid <> 'bigint'::regtype OR attidentity <> '' OR attgenerated <> '')) THEN
        RAISE EXCEPTION 'V161 Guard B: lifecycle_seq must be plain BIGINT';
    END IF;
    IF to_regclass('trading.order_state_changes_lifecycle_seq') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM pg_class c JOIN pg_sequence s ON s.seqrelid = c.oid
           WHERE c.oid = to_regclass('trading.order_state_changes_lifecycle_seq')
             AND c.relkind = 'S' AND s.seqtypid = 'bigint'::regtype
             AND s.seqincrement = 1 AND s.seqmin = 1 AND NOT s.seqcycle) THEN
        RAISE EXCEPTION 'V161 Guard A: lifecycle sequence shape mismatch';
    END IF;
END
$guard$;
ALTER TABLE trading.order_state_changes ADD COLUMN IF NOT EXISTS lifecycle_seq BIGINT;
CREATE SEQUENCE IF NOT EXISTS trading.order_state_changes_lifecycle_seq AS BIGINT;
DO $binding$
DECLARE ordinal_attnum SMALLINT; current_default TEXT; expected_default TEXT;
        last_ordinal BIGINT; was_called BOOLEAN; max_ordinal BIGINT;
BEGIN
    SELECT attnum INTO ordinal_attnum FROM pg_attribute
      WHERE attrelid = 'trading.order_state_changes'::regclass AND attname = 'lifecycle_seq' AND NOT attisdropped;
    IF EXISTS (SELECT 1 FROM pg_depend
        WHERE classid = 'pg_class'::regclass AND objid = 'trading.order_state_changes_lifecycle_seq'::regclass
          AND deptype IN ('a','i')
          AND (refobjid <> 'trading.order_state_changes'::regclass OR refobjsubid <> ordinal_attnum)) THEN
        RAISE EXCEPTION 'V161 Guard A: lifecycle sequence belongs to another column';
    END IF;
    SELECT pg_get_expr(adbin, adrelid) INTO current_default FROM pg_attrdef
      WHERE adrelid = 'trading.order_state_changes'::regclass AND adnum = ordinal_attnum;
    expected_default := format('nextval(%L::regclass)', 'trading.order_state_changes_lifecycle_seq'::regclass::text);
    IF current_default IS NOT NULL AND current_default <> expected_default THEN
        RAISE EXCEPTION 'V161 Guard B: lifecycle_seq default mismatch';
    END IF;
    SELECT last_value, is_called INTO last_ordinal, was_called FROM trading.order_state_changes_lifecycle_seq;
    SELECT MAX(lifecycle_seq) INTO max_ordinal FROM trading.order_state_changes;
    IF max_ordinal > last_ordinal OR (max_ordinal = last_ordinal AND NOT was_called) THEN
        RAISE EXCEPTION 'V161 Guard B: lifecycle sequence is behind existing ordinals';
    END IF;
END
$binding$;
ALTER SEQUENCE trading.order_state_changes_lifecycle_seq OWNED BY trading.order_state_changes.lifecycle_seq;
ALTER TABLE trading.order_state_changes ALTER COLUMN lifecycle_seq
    SET DEFAULT nextval('trading.order_state_changes_lifecycle_seq');
DO $grant$
DECLARE writer TEXT;
BEGIN
    FOR writer IN SELECT rolname FROM pg_roles
        WHERE rolname = 'trading_ai'
           OR has_table_privilege(oid, 'trading.order_state_changes', 'INSERT')
    LOOP
        EXECUTE format('GRANT USAGE ON SEQUENCE trading.order_state_changes_lifecycle_seq TO %I', writer);
    END LOOP;
END
$grant$;

CREATE OR REPLACE VIEW public.order_events AS
SELECT
    o.ts, o.order_id, o.symbol, o.side, o.order_type,
    o.qty, o.price, COALESCE(s.to_status, o.status) AS status,
    GREATEST(s.filled_qty, f.filled_qty)::NUMERIC(20,8) AS filled_qty,
    f.avg_price::NUMERIC(20,8) AS avg_price,
    NULL::NUMERIC(20,8) AS fee,
    o.category, o.is_paper,
    o.details AS raw_json
FROM trading.orders o
LEFT JOIN LATERAL (
    SELECT to_status, MAX(filled_qty) OVER () AS filled_qty
    FROM trading.order_state_changes osc
    WHERE osc.order_id = o.order_id AND osc.engine_mode = o.engine_mode
    ORDER BY CASE WHEN osc.to_status = 'Filled' THEN 2
        WHEN osc.to_status IN ('Cancelled', 'Rejected', 'Deactivated', 'PartiallyFilledCanceled') THEN 1
        ELSE 0 END DESC, osc.lifecycle_seq DESC NULLS LAST, osc.ts DESC
    LIMIT 1
) s ON TRUE
LEFT JOIN LATERAL (
    SELECT SUM(qty)::DOUBLE PRECISION AS filled_qty,
           SUM(qty::DOUBLE PRECISION * price) / NULLIF(SUM(qty::DOUBLE PRECISION), 0) AS avg_price
    FROM trading.fills f
    WHERE f.order_id = o.order_id AND f.engine_mode = o.engine_mode
) f ON TRUE;

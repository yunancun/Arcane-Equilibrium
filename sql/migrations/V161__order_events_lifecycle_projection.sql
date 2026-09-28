-- H1: project causal lifecycle progress, independent of venue/local clock skew.
-- V161 is new in this PR; applied migrations (including V005) remain unchanged.
-- Add a nullable column first: do not rewrite historical compressed chunks.
-- Only new writes receive insertion ordinals; legacy rows retain timestamp order.
ALTER TABLE trading.order_state_changes ADD COLUMN lifecycle_seq BIGINT;
CREATE SEQUENCE trading.order_state_changes_lifecycle_seq
    OWNED BY trading.order_state_changes.lifecycle_seq;
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

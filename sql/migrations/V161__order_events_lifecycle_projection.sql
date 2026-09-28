-- H1: preserve the Grafana bridge shape while projecting current lifecycle truth.
-- Forward-only replacement; do not modify the applied V005 migration.
CREATE OR REPLACE VIEW public.order_events AS
SELECT
    o.ts, o.order_id, o.symbol, o.side, o.order_type,
    o.qty, o.price, COALESCE(s.to_status, o.status) AS status,
    s.filled_qty::NUMERIC(20,8) AS filled_qty,
    s.avg_price::NUMERIC(20,8) AS avg_price,
    NULL::NUMERIC(20,8) AS fee,
    o.category, o.is_paper,
    o.details AS raw_json
FROM trading.orders o
LEFT JOIN LATERAL (
    SELECT to_status, filled_qty, avg_price
    FROM trading.order_state_changes osc
    WHERE osc.order_id = o.order_id AND osc.engine_mode = o.engine_mode
    ORDER BY osc.ts DESC, CASE osc.to_status
        WHEN 'Filled' THEN 9 WHEN 'Cancelled' THEN 8 WHEN 'Rejected' THEN 8
        WHEN 'Deactivated' THEN 8 WHEN 'PartiallyFilledCanceled' THEN 8
        WHEN 'Unknown' THEN 7 WHEN 'PartiallyFilled' THEN 6
        WHEN 'Working' THEN 5 WHEN 'Acknowledged' THEN 4
        WHEN 'Submitted' THEN 3 ELSE 0 END DESC
    LIMIT 1
) s ON TRUE;

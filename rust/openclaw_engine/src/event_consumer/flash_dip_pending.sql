SELECT DISTINCT o.symbol
FROM trading.orders o
JOIN public.order_events e ON e.order_id = o.order_id AND e.ts = o.ts
WHERE o.strategy_name = 'flash_dip_buy'
  AND o.engine_mode = 'demo'
  AND e.status IN ('Working', 'PartiallyFilled', 'PendingSubmit', 'Submitted', 'Acknowledged', 'Unknown')
  AND o.ts >= to_timestamp($1::double precision / 1000.0)

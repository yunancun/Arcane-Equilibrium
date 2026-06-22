# Operator Note: Multi-Horizon Cost Gate Learning Review Path

Current learned candidate:

- side-cell: `ma_crossover|ETHUSDT|Sell`
- status: `CANDIDATE_MULTI_HORIZON_STABLE`
- horizons: `15,30,60,120,240`
- best horizon: `120m`
- best avg net: `121.1121bp`
- sample: `10074`

Alpha now asks for:

`operator_review_multi_horizon_blocked_signal_side_cell_before_bounded_demo_probe`

This is an operator review gate only. It does not lower the global Cost Gate and does not grant probe/order authority.

Still required before any trading authority:

- restore/refetch demo data-flow monitor evidence (`DATA_FLOW_MONITOR_REQUIRED`)
- explicit bounded demo probe authorization
- post-probe matched-control result review
- execution-realism review before any Cost Gate change

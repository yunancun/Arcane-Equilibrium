# Operator Summary - NEAR Buy Plan Materialization BB Approved

Status: `READY_FOR_BOUNDED_DEMO_FINAL_WINDOW`

BB approved only the next PM same-window plan materialization recheck for `ma_crossover|NEARUSDT|Buy`.

Important boundaries:

- No canonical soak plan write happened.
- No `_latest` overwrite happened.
- No Bybit call, Decision Lease, order/probe/cancel/modify, DB/PG, runtime/service/env mutation, Cost Gate change, live/mainnet, or proof/promotion happened.
- Canonical soak plan is still old `grid_trading|ETHUSDT|Buy` and must not be consumed as the NEAR plan.

Next action: PM same-window source/runtime/hash/candidate/expiry recheck only. If stable, later materialization may only copy the exact reviewed `plan_preview` atomically into canonical `bounded_demo_probe_soak_plan.json` with a hash record. That still grants no order authority by itself.

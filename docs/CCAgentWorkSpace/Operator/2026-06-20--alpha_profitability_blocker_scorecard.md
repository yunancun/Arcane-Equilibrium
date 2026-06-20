# Operator Note: Alpha Profitability Blocker Scorecard

v278 adds a runtime `profitability_blocker_scorecard` to alpha discovery. No operator action is requested.

Latest trade-core alpha-discovery artifact:

- sha256 `64a04a70f674042a426c7f31f584a0f15345e773dfc6c9caab2ff515d781a869`
- created `2026-06-20T17:02:16.424355+00:00`
- `ready_for_aeg_chain=0`, `ready_for_probe=0`
- scorecard status `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`

Current blocker read:

- MM is the top blocker: existing walk-forward feature family has no train-positive sample-gated cell; secondary blockers are current fee/cost and VIP5-scale lower-fee path.
- Polymarket is still sample-gated at 18/30, ETA `2026-06-20T19:52:03.067000+00:00`.
- FlashDip L1 replay is data-coverage-gated by `candidate_window_before_symbol_l1_range`.
- Gate-B is still `WATCH_ONLY`.
- Vol-event remains rejected as `NO_EDGE_SURVIVES`.

No live/demo parameter change, no risk/order/auth mutation, no engine restart, no Bybit private call, no PG write, and no promotion proof.

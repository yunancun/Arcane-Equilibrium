# AgentTodo MAG-040 Strategist Matching Model Operator Report

Date: 2026-05-07
Status: DONE

Completed MAG-040.

What changed:

- Added the Strategist V2 matching-model contract.
- Defined five canonical strategy keys:
  `ma_crossover`, `grid_trading`, `bb_reversion`, `bb_breakout`, `funding_arb`.
- Defined candidate scoring, fail-closed behavior, output fields, and required
  future tests.
- Explicitly blocked the old behavior where strategy identity is only
  `strategist_ai` / `strategist_heuristic`.

What did not change:

- No runtime implementation yet.
- No deploy/rebuild/restart.
- No DB migration apply or DB write.
- No feature flag flip.
- No trading authority change.

Next AgentTodo item: MAG-041 StrategistDecision implementation.

# AgentTodo MAG-041 StrategistDecision V2 Operator Report

Date: 2026-05-07
Status: DONE

Completed MAG-041.

What changed:

- Added a typed Strategist V2 decision builder.
- Extended `StrategistDecision` with action, selected strategy, candidate
  scores, expected net edge, portfolio impact, thesis, invalidation, and
  separated fact/inference/hypothesis refs.
- Added tests proving:
  - selected strategy is a canonical strategy key, not just
    `strategist_ai` / `strategist_heuristic`;
  - a lower scanner-rank route can win on better net edge;
  - negative net LCB blocks new opens;
  - reduce can be selected with position-review lineage;
  - `funding_rate_arb` normalizes to `funding_arb`;
  - missing evidence produces explicit `no_action`.

What did not change:

- No runtime hot-path wiring.
- No deploy/rebuild/restart.
- No DB migration apply or DB write.
- No feature flag flip.
- No trading authority change.

Next AgentTodo item: MAG-042 PositionReview for scanner decay/regime shifts.

Verification passed on Mac and Linux temp worktree:

- Python Strategist V2 + spine client tests: 14 passed
- Rust `agent_spine` targeted tests: 6 passed
- Python py_compile, Rust fmt, and diff whitespace checks passed

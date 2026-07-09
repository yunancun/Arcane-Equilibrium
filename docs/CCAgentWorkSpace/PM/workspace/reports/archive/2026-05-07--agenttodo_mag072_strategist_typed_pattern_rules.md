# AgentTodo MAG-072 Strategist Typed Pattern Rules

Date: 2026-05-07
Owner: PM-local execution
Status: DONE

## Scope

Make Strategist next-cycle learning decisions explainable when consuming
Analyst losing/winning patterns and TruthRegistry claims.

## Implementation

- Extended `strategist_decision_v2.py` learning feedback with `typed_rules`.
- Candidate-level `learning_feedback` now records source, Analyst tier/type/level
  when applicable, insight ID, claim ID, polarity, reason code, and evidence
  refs.
- Selected-candidate `portfolio_impact.learning_feedback` also carries the
  typed rules that affected the selected route.
- Updated tests to use L2 AnalystInsight pattern schemas for losing/winning
  pattern feedback.

## Verification

- Mac:
  - `python3 -m py_compile ... strategist_decision_v2.py test_strategist_decision_v2.py test_strategist_v2_replay_not_scanner_sorting.py`
  - `python3 -m pytest ... test_strategist_decision_v2.py test_strategist_v2_replay_not_scanner_sorting.py -q`
  - `git diff --check`
- Linux `trade-core` temp worktree:
  - same py_compile
  - same pytest set
  - same diff check

Focused result: 16 Python tests pass.

## Boundary

- No runtime Strategist wiring.
- No runtime Analyst emission wiring.
- No Guardian behavior change.
- No cloud call.
- No runtime submit path.
- No Rust contract change.
- No rebuild, restart, deploy, DB write, live auth, runtime flag, or trading
  authority change.

## Next

M7 continues with MAG-073 Guardian consumes risk patterns.

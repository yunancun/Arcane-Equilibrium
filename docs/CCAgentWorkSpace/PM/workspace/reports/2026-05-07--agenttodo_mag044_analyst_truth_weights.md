# AgentTodo MAG-044 Analyst / Truth Strategy Weights Report

Date: 2026-05-07
Role: PM / E1a local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M4 after MAG-043 and consumed AnalystInsight plus
TruthRegistry-style pattern claims in Strategist V2 strategy weights.

## Result

Updated:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`

Added `TruthRegistryClaim` and `analyst_insights` / `truth_registry_claims` to
`StrategyMatchInput`. The scorer now:

- matches AnalystInsight claims and TruthRegistry claims by symbol and
  normalized strategy;
- supports `grid -> grid_trading` aliasing for existing pattern-claim output;
- applies losing/negative patterns as bounded learning-weight penalties;
- applies winning/positive patterns as bounded learning-weight boosts;
- records reason codes and evidence refs in `candidate_scores`;
- carries selected learning reason codes into `portfolio_impact`;
- appends selected fact/inference/hypothesis refs according to AnalystInsight
  level.

Acceptance behavior covered: a losing pattern can change future strategy
preference away from the affected strategy, with persisted reason codes.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is a typed helper extension. It is not wired into `StrategistAgent` runtime
hot path yet.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 28 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`
- `git diff --check`

Linux `trade-core` temp worktree `/tmp/tradebot_mag044_analyst_truth`:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 28 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`
- `git diff --check --cached`

## Next AgentTodo Item

Next: MAG-045 replay test: Strategist decisions are not equivalent to scanner
score sorting.

# AgentTodo MAG-043 Guardian Feedback Stats Report

Date: 2026-05-07
Role: PM / E1a local implementation checkpoint
Status: DONE

## Scope

Continued AgentTodo M4 after MAG-042 and consumed Guardian rejection/modify
stats in the next-cycle StrategistDecision builder.

## Result

Updated:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py`
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`

Added `GuardianFeedbackStats` to `StrategyMatchInput`. For new opens only, the
builder now:

- matches feedback by engine mode, symbol, and normalized strategy;
- ignores low-sample feedback below `guardian_feedback_min_total`;
- raises the candidate confidence floor when recent Guardian reject rate is
  high;
- lowers effective `risk_acceptance_prior`;
- scales `proposed_qty` through an aggressiveness multiplier;
- persists feedback details in `candidate_scores`, `portfolio_impact`, and
  evidence refs.

PositionReview reduce/close candidates are not blocked by open rejection stats;
their Guardian lineage remains downstream through the normal review/verdict
path.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is a typed helper extension. It is not wired into `StrategistAgent` runtime
hot path yet.

## Verification

Mac:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 24 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`

Linux `trade-core` temp worktree `/tmp/tradebot_mag043_guardian_feedback`:

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_position_review_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_agent_spine_client.py -q`
  - 24 passed
- `python3 -m py_compile program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_decision_v2.py program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_decision_v2.py`
- `git diff --check --cached`

## Next AgentTodo Item

Next: MAG-044 consume AnalystInsight and TruthRegistry in strategy weights.

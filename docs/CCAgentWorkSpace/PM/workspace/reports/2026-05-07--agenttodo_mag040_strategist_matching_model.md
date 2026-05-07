# AgentTodo MAG-040 Strategist Matching Model Report

Date: 2026-05-07
Role: PM / PA-QC local design checkpoint
Status: DONE

## Scope

Started AgentTodo M4 after closing M3 and defined the Strategist V2 matching
model for five concrete strategies:

- `ma_crossover`
- `grid_trading`
- `bb_reversion`
- `bb_breakout`
- `funding_arb`

## Result

Added:

- `docs/architecture/multi_agent_rework_2026-05-05/2026-05-07--mag040_strategist_v2_matching_model.md`

The model defines input evidence, candidate scoring, strategy fit rules,
decision output fields, fail-closed behavior, and MAG-041/MAG-045 regression
targets. It explicitly prevents Strategist V2 from choosing only
`strategist_ai` / `strategist_heuristic`; those can remain evaluation-source
metadata, but the selected strategy must be a canonical strategy key.

## Boundary

No runtime deploy, rebuild, restart, DB migration apply, DB write, feature-flag
flip, live auth mutation, trading mode change, or risk/strategy config change
was performed.

This is a design contract only. Runtime implementation remains MAG-041.

## Verification

- `git diff --check`

## Next AgentTodo Item

Next: MAG-041 implement `StrategistDecision` open/hold/reduce/close/no_action.

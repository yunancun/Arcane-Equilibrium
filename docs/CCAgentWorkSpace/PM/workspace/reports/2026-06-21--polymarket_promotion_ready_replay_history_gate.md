# Polymarket Promotion-Ready Replay-History Gate

Date: 2026-06-21  
Role: PM local implementation checkpoint  
Status: source/test/docs complete; runtime still unsynced

## Finding

The alpha-discovery profitability scorecard still had one broad path where a
Polymarket IC candidate could be counted as `promotion_ready` because the arm
was `READY_FOR_AEG_CHAIN`.

That is too permissive for the current evidence chain. A Polymarket lead-lag IC
candidate is useful as an AEG candidate artifact, but it is not alpha promotion
readiness until the paper replay, dated replay history, and execution realism
have all passed their own gates.

## Change

`alpha_discovery_throughput.discovery_loop` now adds Polymarket-specific gates
before the generic `candidate_review_ready` row.

For `polymarket_leadlag_ic`, promotion readiness now requires:

- `candidate_replay_status=PAPER_REPLAY_BUILT`
- `candidate_replay_history_status=REPLAY_HISTORY_READY_FOR_AEG_RECHECK`
- `candidate_replay_history_execution_realism_status=PASS`

Otherwise the blocker is explicit:

- missing replay -> `data_coverage / polymarket_candidate_replay_missing`
- missing replay history -> `data_coverage / polymarket_candidate_replay_history_missing`
- insufficient replay history -> `sample_gate / polymarket_candidate_replay_history_not_ready`
- unmeasured execution realism -> `robustness_wait / polymarket_execution_realism_unmeasured`
- failed execution realism -> `robustness_wait / polymarket_execution_realism_not_passed`

## Verification

- `python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> `39 passed`
- `python3 -m pytest helper_scripts/research/tests/test_polymarket_leadlag.py -q` -> `25 passed`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/tests/test_alpha_discovery_throughput.py`
- `git diff --check`

Regression coverage now proves:

- a built replay with no dated history is not promotion-ready
- insufficient history is sample-gated, not promotion-ready
- execution realism `FAIL` is not promotion-ready
- only replay-history-ready plus execution-realism `PASS` can reach the generic candidate-review promotion path

## Boundary

No runtime source sync, artifact refresh, crontab edit/install, env edit,
deploy/rebuild/restart, PG write/schema migration, Bybit private/signed call,
credential/auth/risk/order/strategy mutation, order authority, or promotion
proof.

## PM Read

This closes a scorecard false-positive, not the whole alpha problem. Runtime may
still show stale Polymarket `promotion_ready=true` until `trade-core` is synced
and alpha-discovery reruns on the new code.

The next profitable-learning step remains: sync runtime source under operator
approval, rerun alpha-discovery, then keep building dated replay history and
real execution realism before any Polymarket promotion decision.

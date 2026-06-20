# AEG Candidate Artifact Dependency Scorecard

Date: 2026-06-20

## Summary

The latest alpha killboard was still counting AEG robustness matrix work as immediately engineering-actionable even when there were no upstream candidate or probe artifacts to feed into the matrix. That was a false actionable state: robustness review is useful only after a real candidate/probe artifact exists.

This checkpoint adds a diagnostic dependency scorecard to the AEG blocker. It does not change AEG promotion gates, candidate gates, strategy parameters, order behavior, or runtime trading. It only makes the no-profit blocker map more honest.

## Changes

- Added `candidate_artifact_dependency` to the `aeg_robustness_matrix` arm detail inside `build_profitability_blocker_scorecard`.
- AEG robustness wait is now engineering-actionable only if another arm is `READY_FOR_AEG_CHAIN`, `READY_FOR_PROBE`, or explicitly has `artifacts_ready=true`.
- When no upstream candidate/probe artifact exists, AEG next trigger becomes `wait_for_candidate_or_probe_artifact_before_robustness_matrix`.
- Added regression coverage for both states: empty upstream artifact pool and upstream candidate artifact available.

## Runtime Evidence

Linux read-only alpha-discovery smoke:

- Latest alpha SHA256: `f3aec25f6904681ce407e97f133dcfcb28629328115ebcbefbc616697d437c72`
- Created: `2026-06-20T19:04:33.380886+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- Killboard: `ready_for_probe=0`, `ready_for_aeg_chain=0`, `active_arm_count=7`
- Blocker counts: `cost_wall=1`, `data_coverage=2`, `event_wait=2`, `rejected_no_edge=1`, `robustness_wait=1`, `sample_gate=1`
- `engineering_actionable_count`: 1
- `operator_actionable_count`: 0

AEG blocker:

- blocker class: `robustness_wait`
- primary blocker: `no_durable_aeg_candidate_rows`
- dependency status: `NO_CANDIDATE_ARTIFACTS_AVAILABLE_FOR_ROBUSTNESS`
- dependency reason: `no_upstream_ready_or_probe_artifacts`
- candidate artifact count: 0
- `engineering_actionable=false`
- next trigger: `wait_for_candidate_or_probe_artifact_before_robustness_matrix`

## Interpretation

This removes one false positive from the active engineering queue. The current problem is not that the AEG matrix needs manual feeding; the problem is that no upstream arm has produced a candidate/probe artifact worth feeding.

The remaining immediate engineering-actionable item is MM cost-wall work: validate a realistic lower-fee path or find a materially stronger low-friction signal path. Polymarket is still a near-gate sample wait at 26/30 with ETA `2026-06-20T19:52:01.701000+00:00`; FlashDip paths remain data/event gated.

## Verification

- Mac: `test_alpha_discovery_throughput.py` = 28 passed.
- Mac: py_compile for `discovery_loop.py` and `runtime_runner.py` passed.
- Mac: `git diff --check` passed.
- Linux selective source sync: same focused suite = 28 passed.
- Linux py_compile passed.
- Linux read-only alpha-discovery cron smoke refreshed the evidence above.

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes only. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/trading mutation, and no live/demo strategy parameter change.

This is not promotion proof and not a trading signal.

## Next Trigger

AEG robustness becomes actionable only after an upstream arm produces `READY_FOR_AEG_CHAIN`, `READY_FOR_PROBE`, or explicit artifact readiness. Until then, alpha work should stay on candidate generation and cost-wall escape rather than empty matrix review.

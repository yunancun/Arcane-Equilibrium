# STRK-FUP healthcheck silent-dead RFC

Date: 2026-05-01
Owner: PA
Status: RFC complete; implementation split remains per-pipeline

## Scope

This RFC covers the remaining STRK-FUP healthcheck debt after `[27]` was
recalibrated in `4abb36a`. The goal is not to make every observation gate green;
it is to ensure each silent-dead detector distinguishes:

- writer/pipeline dead,
- expected dormant state,
- strategy/risk/cost gate rejection,
- rolling-window aging,
- healthcheck-side schema drift.

## Current State

Latest wrapper after the `[27]` recalibration is SUMMARY WARN, not FAIL.
`[27]` now correctly reports rejected-only windows as WARN because Guardian is
alive and `approved_verdicts_30m=0`.

The broader debt remains for:

| Check | Pipeline | Current risk | RFC decision |
|---|---|---|---|
| `[3]` | exit_features writer | false PASS/FAIL when close-fill cadence is low | Add accepted close-fill denominator and dormant/no-close distinction |
| `[19]` | observer pipeline | observer cron can report ok while downstream freshness is stale | Split cron cycle health from market-data freshness |
| `[23]` | orders/fills consistency | real dropped pairs can be mixed with expected unattributed/system closes | Keep existing exclusions, add reason-class denominator |
| `[24]` | signals writer freshness | strategy pre-gates can make signal writer quiet without being dead | Require upstream signal opportunity denominator |
| `[26]` | dust spiral noise in exit_features | historical dust rows can persist in rolling window after fix | Use post-fix cutoff plus recurrence rate |

## Acceptance Criteria

- Each check has a three-state verdict: PASS / WARN / FAIL.
- FAIL requires a writer or pipeline invariant breach, not just low activity.
- WARN carries the active denominator and reason class so PM can tell whether it
  is strategy/market quietness or monitor-side uncertainty.
- A new targeted test covers every changed branch.
- Wrapper remains the source of truth; direct Python invocation is not used for
  runtime conclusion.

## Proposed Implementation Split

### STRK-HC-3 exit_features writer

- Query 24h close fills by engine/strategy.
- Query matching `learning.exit_features` rows after close-fill timestamps.
- PASS when either no accepted closes exist or feature coverage is above target.
- WARN when closes are sparse but coverage is computable.
- FAIL when accepted closes exist and feature coverage is zero or below a hard
  writer threshold.

### STRK-HC-19 observer pipeline

- Keep cron heartbeat/ok-ratio check separate from data freshness.
- Add fields: `last_ok_cycle_age`, `last_market_write_age`, `ok_ratio_24h`.
- FAIL only if heartbeat stale or ok-ratio below threshold.
- WARN if heartbeat is healthy but downstream market-data freshness is stale.

### STRK-HC-23 orders/fills consistency

- Preserve existing `unattributed:%` and system-close exclusions.
- Add reason buckets: `missing_order`, `expected_system_close`,
  `unattributed_excluded`, `late_join_pending`.
- FAIL only on non-excluded missing-order count above threshold.

### STRK-HC-24 signals writer freshness

- Use scanner/strategy signal opportunities as denominator.
- PASS when no opportunities exist.
- WARN when opportunities exist but strategy pre-gates suppress all signals.
- FAIL when opportunities exist, upstream signal engine emits, but
  `trading.signals` writer remains stale.

### STRK-HC-26 dust spiral noise in exit_features

- Pin post-fix cutoff to the dust residual prevention deploy window.
- Report both historical count and 24h recurrence.
- PASS when recurrence is zero.
- WARN when historical rows remain but recurrence is zero.
- FAIL only when post-fix recurrence reappears.

## Test Plan

- Extend `helper_scripts/db/test_f7_new_healthchecks.py` with table-driven mocks
  for PASS/WARN/FAIL per check.
- Add py_compile for touched healthcheck modules.
- Run wrapper on Linux after source sync only for observation; no DB write.

## Boundary

No trading/risk/strategy parameter changes. No DB backfill. No runtime restart is
required for the RFC. Implementation should be source-only until a future deploy
batch is explicitly approved.

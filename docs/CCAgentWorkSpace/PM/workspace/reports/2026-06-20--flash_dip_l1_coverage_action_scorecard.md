# FlashDip L1 Coverage Action Scorecard

Date: 2026-06-20

## Summary

FlashDip L1 replay was still grouped under a broad `data_coverage` blocker. This checkpoint makes the blocker actionable by separating historical candidate windows that predate L1 capture from true recorder gaps, partial event-window coverage, and stale L1 ranges.

Latest runtime read: the current FlashDip L1 replay gap is not an immediately fixable recorder bug. The missing candidate windows ended before symbol L1 capture began, so the correct trigger is to wait for the next FlashDip candidate after L1 capture start and replay it.

## Changes

- Added `coverage_action_scorecard` to `shallow_retune_l1_short_exit_replay.py`.
- Added status classes for:
  - `HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE`
  - `PARTIAL_EVENT_WINDOW_L1_COVERAGE`
  - `CANDIDATES_AFTER_L1_RANGE_RECORDER_STALE_OR_WINDOW_AFTER_DATA`
  - `SYMBOL_L1_MISSING_FOR_CANDIDATES`
  - `L1_RANGE_OVERLAPS_BUT_EVENT_WINDOW_EMPTY`
- Passed `coverage_action_status`, `coverage_action_reason`, and `coverage_action_scorecard` through:
  - `flash_dip_l1_short_exit_replay_cron.sh`
  - `alpha_discovery_throughput.runtime_runner`
  - `alpha_discovery_throughput.discovery_loop`
- Taught alpha-discovery to use scorecard actionability for the FlashDip L1 blocker instead of treating every L1 coverage miss as immediate engineering work.

## Runtime Evidence

Linux read-only FlashDip L1 replay smoke:

- Status timestamp: `2026-06-20T18:40:34Z`
- Latest artifact SHA256: `bad7a5078217f11b292b948d3439d6e960b03c082c86caa4b8426cc3474441f9`
- Status log SHA256: `49ee6d2b620afd21429ae6bfbdfc516baa483849159b126c373e51461dd39e0e`
- Verdict: `L1_SHORT_EXIT_INSUFFICIENT_SAMPLE`
- Fail reasons: `no_l1_rows_for_candidate_event_windows`, `gate_horizon_sample_below_min_filled`, `gate_horizon_sample_below_min_days`
- Candidate events: 6
- Events with L1 in event window: 0
- Events missing L1 in event window: 6
- Dominant coverage relation: `candidate_window_before_symbol_l1_range`
- Earliest symbol L1 first timestamp: `2026-06-20T00:18:11.624000+00:00`
- Latest missing candidate-window end: `2026-06-20T00:00:00+00:00`
- L1 gap hours summary: `n=6`, min `0.3032`, p50 `12.3033`, max `24.3033`, mean `12.3033`

Coverage action scorecard:

- Status: `HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE`
- Reason: `candidate_windows_end_before_symbol_l1_capture_starts`
- `engineering_actionable`: false
- Next trigger: `wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay`

Alpha-discovery smoke:

- Latest artifact SHA256: `7775d35d0031b0c1eb787c0169142414baa8beb8f48800f9a421749836e4672b`
- Created: `2026-06-20T18:40:39.670385+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- Ready/probe: 0/0
- Blocker counts: `cost_wall=1`, `data_coverage=2`, `event_wait=2`, `sample_gate=1`, `robustness_wait=1`, `rejected_no_edge=1`
- FlashDip L1 blocker now carries `coverage_action_status=HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE`, `engineering_actionable=false`, and the same next trigger above.

## Interpretation

The missing L1 rows are explained by timing: these candidate windows are historical relative to the repaired L1 capture range. That means this is not evidence to retune FlashDip, and not evidence to repair the recorder again. It is a measured wait state until a new K6/N2/C3/nf0.005 candidate occurs after L1 capture is live.

This preserves the 240m short-exit research path, but keeps it blocked until L1-covered candidate windows exist.

## Verification

- Mac: `test_tail_dislocation_shallow_retune.py` = 15 passed.
- Mac: `test_alpha_discovery_throughput.py` = 25 passed.
- Mac: `test_flash_dip_l1_short_exit_replay_cron_static.py` = 6 passed.
- Mac: py_compile, bash syntax, and `git diff --check` passed.
- Linux selective source sync: same focused pytest suites passed (`15`, `25`, `6`), plus py_compile and bash syntax.
- Linux runtime smoke: FlashDip L1 replay cron and alpha-discovery throughput cron completed read-only and refreshed the evidence above.

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact/status/log writes only. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/trading mutation, and no live/demo strategy parameter change.

This is not promotion proof and not retune authority.

## Next Trigger

Wait for the next FlashDip K6/N2/C3/nf0.005 candidate whose maker-entry window occurs after L1 capture start, then replay queue fills and short exits. Only a sample-gated `L1_SHORT_EXIT_CONDITIONAL_PASS` should move this path into formal QC/MIT/AI-E review.

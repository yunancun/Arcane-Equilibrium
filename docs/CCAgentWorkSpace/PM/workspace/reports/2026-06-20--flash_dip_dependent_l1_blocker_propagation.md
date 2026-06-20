# FlashDip Dependent L1 Blocker Propagation

Date: 2026-06-20

## Summary

FlashDip execution-realism was still counted as engineering-actionable whenever daily exits failed but the short-exit research signal existed. That was too broad after the L1 replay scorecard landed: the execution-realism path depends on the L1 replay path, and current L1 replay evidence says the missing windows are historical-before-capture wait states.

This checkpoint propagates the dependent L1 coverage-action scorecard into the `flash_dip_execution_realism` blocker row. Result: alpha-discovery no longer tells us to immediately work the short-exit L1 path when the child L1 blocker says to wait for the next L1-covered FlashDip candidate.

## Changes

- `runtime_runner.py` now attaches `dependent_l1_short_exit_replay` to `flash_dip_execution_realism` detail.
- The dependency summary carries:
  - `coverage_action_status`
  - `coverage_action_reason`
  - `coverage_action_next_trigger`
  - `engineering_actionable`
  - dominant event-window L1 relation and missing-window counts
- `discovery_loop.py` now inherits dependent L1 actionability and next trigger for `daily_exit_execution_realism_blocked_short_exit_needs_l1_replay`.
- Added focused regression coverage for the historical-before-capture case.

## Runtime Evidence

Linux artifact-only alpha-discovery smoke:

- Latest alpha SHA256: `05d0baa71008cc31024c0e58bbe86b5c98f50edae0919691ffaabd519f57a585`
- Created: `2026-06-20T18:50:21.382935+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- Blocker counts: `cost_wall=1`, `data_coverage=2`, `event_wait=2`, `rejected_no_edge=1`, `robustness_wait=1`, `sample_gate=1`
- `engineering_actionable_count`: 2

FlashDip rows after propagation:

- `flash_dip_l1_short_exit_replay`
  - blocker: `data_coverage:candidate_window_before_symbol_l1_range`
  - `coverage_action_status=HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE`
  - `engineering_actionable=false`
  - next trigger: `wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay`
- `flash_dip_execution_realism`
  - blocker: `data_coverage:daily_exit_execution_realism_blocked_short_exit_needs_l1_replay`
  - `dependent_l1_coverage_action_status=HISTORICAL_CANDIDATES_BEFORE_L1_CAPTURE_WAIT_NEXT_CANDIDATE`
  - `dependent_l1_engineering_actionable=false`
  - `engineering_actionable=false`
  - next trigger: `wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay`

Current Polymarket context from the same artifact:

- sample floor: 25/30
- remaining samples: 5
- status: `PERSISTENT_PRE_GATE_WATCHLIST`
- next trigger remains `wait_until_sample_gate_eta_then_recompute_hac_bh_filters`

## Interpretation

The FlashDip short-exit research path is still alive, but the immediate work is not another replay invocation or retune. The correct state is a passive, instrumented wait for a new FlashDip candidate after L1 capture start. This prevents the killboard from overstating engineering actionability and leaves the next true work concentrated on MM cost-wall/new low-friction signal search and near-gate Polymarket recomputation.

## Verification

- Mac: `test_alpha_discovery_throughput.py` = 26 passed.
- Mac: py_compile for `runtime_runner.py` and `discovery_loop.py` passed.
- Mac: `git diff --check` passed.
- Linux selective source sync: same focused suite = 26 passed.
- Linux py_compile passed.
- Linux read-only alpha-discovery cron smoke refreshed the evidence above.

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes only. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/trading mutation, and no live/demo strategy parameter change.

This is not promotion proof and not retune authority.

## Next Trigger

Wait for the next FlashDip candidate after L1 capture start, then replay L1 queue/fill and short-exit realism. In parallel, keep Polymarket sampling until the 30-point overlap-adjusted gate recomputes HAC/BH filters.

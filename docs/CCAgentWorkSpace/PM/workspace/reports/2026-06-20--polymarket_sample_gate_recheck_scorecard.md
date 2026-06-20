# Polymarket Sample-Gate Recheck Scorecard

Date: 2026-06-20

## Summary

Polymarket lead-lag is no longer just a generic sample-gate wait. Latest runtime has a floor-qualified persistent pre-gate watchlist near the 30-point overlap-adjusted sample gate, so the alpha killboard should name the exact recheck trigger instead of relying on operator memory.

This checkpoint adds a diagnostic-only sample-gate recheck scorecard in alpha-discovery. It does not relax the Polymarket candidate gate: min points, HAC/BH, overlap-adjusted floor, trailing-return controls, and promotion boundaries are unchanged.

## Changes

- Added `sample_gate_recheck_scorecard` to `collect_polymarket_leadlag_arm`.
- The scorecard classifies:
  - `SAMPLE_GATE_RECHECK_NOW`
  - `PERSISTENT_PRE_GATE_SAMPLE_GATE_ETA_DUE`
  - `PERSISTENT_PRE_GATE_NEAR_SAMPLE_GATE_WAIT_ETA`
  - `PERSISTENT_PRE_GATE_WAIT_SAMPLE`
  - `WAIT_SAMPLE_GATE`
- `discovery_loop.py` now surfaces `sample_gate_recheck_status` and uses the scorecard's `next_trigger` for Polymarket sample-gate blockers.
- Added focused regression coverage for a 25/30 persistent near-gate state.

## Runtime Evidence

Linux read-only alpha-discovery smoke:

- Latest alpha SHA256: `c5832b2a371a6c0ea8564b2e321327bdb8d6ebedecf00c5ffab3a233617e89f0`
- Created: `2026-06-20T18:57:07.684771+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- Blocker counts: `cost_wall=1`, `data_coverage=2`, `event_wait=2`, `rejected_no_edge=1`, `robustness_wait=1`, `sample_gate=1`
- `engineering_actionable_count`: 2

Polymarket blocker:

- sample floor: 25/30
- remaining samples: 5
- persistence status: `PERSISTENT_PRE_GATE_WATCHLIST`
- floor-qualified persistent cells: 2
- floor-qualified recurring cells: 3
- sample-gate ETA: `2026-06-20T19:52:02.074000+00:00`
- recheck status: `PERSISTENT_PRE_GATE_NEAR_SAMPLE_GATE_WAIT_ETA`
- `recheck_actionable=false`
- next trigger: `rerun_polymarket_leadlag_ic_after_sample_gate_eta_then_alpha_discovery`

## Interpretation

This is the closest current non-MM path to a decisive alpha answer. It is still not candidate proof because the overlap-adjusted sample floor remains below 30, but it is now a precise near-term recheck state rather than a vague wait.

If the post-ETA recompute produces `candidate_count > 0`, the path moves to candidate review. If it decays, the no-profit diagnosis becomes stronger: the persistent pre-gate IC did not survive the full sample gate.

## Verification

- Mac: `test_alpha_discovery_throughput.py` = 27 passed.
- Mac: py_compile for `runtime_runner.py` and `discovery_loop.py` passed.
- Mac: `git diff --check` passed.
- Linux selective source sync: same focused suite = 27 passed.
- Linux py_compile passed.
- Linux read-only alpha-discovery cron smoke refreshed the evidence above.

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes only. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/trading mutation, and no live/demo strategy parameter change.

This is not promotion proof and not a trading signal.

## Next Trigger

After `2026-06-20T19:52:02.074000+00:00`, rerun Polymarket lead-lag IC and then alpha-discovery. The result should either enter candidate review or convert the current pre-gate watchlist into stronger rejected/no-edge evidence.

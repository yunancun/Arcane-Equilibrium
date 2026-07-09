# REF-21 V1.3 P0-REF21-5 Promotion Calculator Closure

**Date:** 2026-05-06  
**Owner:** PM  
**Status:** P0-REF21-5 CLOSED; R2/R3 still BLOCKED by P0-REF21-6/7

## Summary

P0-REF21-5 is closed by `sql/migrations/V061__replay_promotion_metrics_calculator.sql`.
The migration creates a non-stub `replay.calculate_promotion_metrics(...)`
SECURITY DEFINER function. The calculator derives promotion metrics from
`replay.experiments`, `replay.simulated_fills`, and
`learning.edge_estimate_snapshots`; it does not trust replay producer payloads
for tier promotion.

## Implemented

- `replay.calculate_promotion_metrics(report_id, from_tier, to_tier)` as
  SECURITY DEFINER with restricted `search_path`.
- Fail-closed tier FSM:
  `s2_public_replay -> s2_oos_replay`,
  `s2_oos_replay -> s1_calibrated_replay`,
  `s1_calibrated_replay -> verified_replay_advisory`.
- Historical edge snapshot reader with deprecated-strategy exclusion and
  `predicted_edge_bps > 0` enforcement.
- PSR/DSR helpers aligned to `program_code/learning_engine/dsr_gate.py`.
- CSCV PBO loop aligned to `program_code/learning_engine/pbo_gate.py`
  (`16` slices, `C(16,8)=12870` combinations, fail closed if insufficient
  power or `PBO > 0.20`).
- Deterministic stationary bootstrap q10/q50/q90 bands with 1000 resamples and
  block size `floor(sqrt(n))`.
- PUBLIC EXECUTE revoked from the calculator and internal helper functions.
- Guard A verifies V057/V049/V050/V059 prerequisites. Guard B/C verifies the
  function exists, is SECURITY DEFINER, and PUBLIC cannot execute it.

## Verification

- Mac static tests:
  `python3 -m pytest tests/migrations/test_v061_ref21_promotion_metrics_calculator.py tests/migrations/test_v057_v060_ref21_replay_governance.py -q`
  -> `11 passed`.
- `git diff --check` -> passed.
- Linux `trade-core` PG transaction dry-run:
  V057-V061 applied inside a transaction, replay experiment/fill/edge fixture
  rows inserted, calculator executed, and transaction rolled back.

Runtime dry-run result:

```text
eligible=true
fail_reasons=[]
predicted_edge_bps=12
oos_net_bps=10.000000000000002
oos_gap_bps=0
psr0=1
dsr=1
pbo=0
pbo_combinations=12870
q50_iter=1000
ROLLBACK
```

## Notes

The first Linux executions surfaced two real portability gaps before closure:
Postgres has no `isfinite(double precision)`, and the JSON numeric regex was
over-escaped. Both are fixed in V061 via `_is_finite_v061()` and a portable
numeric regex.

## Remaining REF-21 P0

- P0-REF21-6: implement true
  `POST /api/v1/replay/full-chain/run` scanner-to-exit runner.
- P0-REF21-7: enforce replay dedicated Bybit public client and 50 req/s
  rate/IP isolation.

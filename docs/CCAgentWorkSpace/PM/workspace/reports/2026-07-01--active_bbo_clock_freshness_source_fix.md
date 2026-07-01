# Active BBO Clock Freshness Source Fix

Date: 2026-07-01

## Scope

Active blocker: `P0-CURRENT-CANDIDATE-ACTIVE-BBO-CLOCK-FRESHNESS-GATE-DIAGNOSIS`.

PM diagnosed the v694 active-window BBO freshness fail-closed condition without rerunning public quote capture or active Decision Lease. The source issue was an over-strict future-ticker guard in `_freshness`: any `raw_bbo_age_ms < -1.0` failed closed as `ticker_time_future_or_clock_ambiguous`, even when the effective BBO age was positive and under the freshness gate. The v694 active artifact had `raw_bbo_age_ms=-4` and `effective_bbo_age_ms=441.275`.

## Artifacts

- Session loop state: `/tmp/openclaw/session_loop_state_20260701T_active_bbo_clock_freshness_diagnosis/session_loop_state.json`
- Session loop state sha256: `9347c267e0cf000d7eea85476dfcdb17f2aa6802312bbfb188ba4379206b4a66`
- Source fix commit: `d0109517` (`Fix BBO freshness clock tolerance`)
- Later source head observed before this report: `6c48a6a2` (`feat: add IBKR readonly probe result import contract [skip ci]`), with `d0109517` in history

## Source Conclusion

`bbo_freshness_public_quote_capture.py` now applies a fixed `BBO_FUTURE_TIMESTAMP_TOLERANCE_MS = 10.0` to small negative raw BBO age. The helper still fails closed when:

- raw future skew is below `-10ms`
- `effective_bbo_age_ms` is negative
- effective age exceeds `max_fresh_bbo_age_ms`
- source fields are missing or malformed

The tolerance is emitted into freshness artifacts as `future_timestamp_tolerance_ms` so later reviews can distinguish bounded timestamp ambiguity from silent freshness-gate lowering.

## Verification

- Red regression reproduced before fix:
  `PYTHONPATH=helper_scripts/research python3 -B -m pytest -q helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py -k 'small_negative_ticker_age_within_timestamp_tolerance_is_fresh or future_ticker_time_beyond_tolerance_fails_closed'`
  - Result before fix: `1 failed, 1 passed`
- Focused post-fix boundary set:
  `PYTHONPATH=helper_scripts/research python3 -B -m pytest -q helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py -k 'small_negative_ticker_age_within_timestamp_tolerance_is_fresh or future_ticker_time_beyond_tolerance_fails_closed or small_negative_ticker_age_with_negative_effective_age_fails_closed or stale_and_future_ticker_time_fail_closed'`
  - Result: `4 passed`
- Adjacent no-network helper suite:
  `PYTHONPATH=helper_scripts/research python3 -B -m pytest -q helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py helper_scripts/research/tests/test_current_candidate_public_quote_construction_refresh.py helper_scripts/research/tests/test_current_candidate_actual_admission_bbo_lease_window.py`
  - Result: `36 passed`
- `python3 -B -m py_compile helper_scripts/research/cost_gate_learning_lane/bbo_freshness_public_quote_capture.py helper_scripts/research/cost_gate_learning_lane/current_candidate_public_quote_construction_refresh.py helper_scripts/research/cost_gate_learning_lane/current_candidate_actual_admission_bbo_lease_window.py helper_scripts/research/tests/test_cost_gate_bbo_freshness_public_quote_capture.py`
  - Result: pass
- `git diff --check`
  - Result: pass

## Reviews

- PA sidecar: `ACCEPT`, no findings; confirmed the 10ms tolerance is coherent and tests cover `raw=-4`, `raw=-16`, and negative effective age.
- E2 sidecar: `ACCEPT`, no required changes; confirmed no Cost Gate lowering, no probe/order/live authority, no Decision Lease/Guardian/Rust authority bypass, and stale/future/negative-effective fail-closed coverage.
- E4 verification: PM-local due thread limit; focused and adjacent tests passed as listed above.

## Runtime Status

Runtime sync was not performed in this desktop environment. `/home/ncyu/BybitOpenClaw/srv` was unavailable (`No such file or directory`), and no alternate runtime `srv` checkout was used. PM did not contact exchange, runtime Control API, PG, service manager, Decision Lease IPC, private endpoint, or order endpoint.

## Boundary

No public quote rerun, no active Decision Lease acquire/release, no Bybit private/order endpoint, no order/cancel/modify, no PG query/write, no service/env/risk mutation, no Cost Gate lowering, no live/mainnet, no fill/PnL/proof, and no runtime order/probe authority.

## Next

State transition: `DONE_WITH_CONCERNS`.

Next blocker: `P0-CURRENT-CANDIDATE-ACTIVE-BBO-RUNTIME-SYNC-GATE`.

Next PM should first locate/verify the runtime checkout, obtain E3 review for source-only runtime sync of `d0109517`, cherry-pick or otherwise apply only the freshness fix into the runtime hotfix lineage, and run the same focused no-network tests there. Only after runtime sync is verified should a fresh E3/BB review consider any new active Decision Lease plus same-window public BBO run. The v694 active quote/lease approval is consumed and must not be reused.

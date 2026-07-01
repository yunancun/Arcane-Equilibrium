# Order-Capable Source Stability Guard

Date: 2026-07-01

Active blocker: `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE`

Status: `DONE_WITH_CONCERNS`

## Summary

PM regenerated an exact current-head stale-BBO refresh request at source `80d40d2cae881c70ab166a7826e7375eb67addef`; E3 and BB both returned `APPROVE_WITH_CONDITIONS` for request sha `2a58c838fa15a8f318b1bf73eb16261527be954302603e0db17cfce10c2cfecc`. The required immediate pre-execution drift check failed before any Phase A/B action: source advanced first to `e838ec9b6b16855f0bcf0b62e709ce6891f328fb` and later through additional Stock/ETF commits. The reviewed request is therefore invalid and was not consumed.

No public Demo quote, private/order endpoint, Decision Lease acquire/release, PG access, service/env/risk mutation, Cost Gate change, order/cancel/modify, live/mainnet action, fill, PnL, or proof occurred.

## Source Guard

Code commit `516b36e4850bc18ceda9384daf88f89f23397f9b` adds `helper_scripts/research/cost_gate_learning_lane/source_stability_window_guard.py`, tests, and script-index documentation. The guard is source-only and emits `source_stability_window_guard_v1`. It requires:

- `HEAD == origin/main`
- clean worktree
- optional required source/origin hashes match
- previous sample uses the same schema
- previous sample was clean
- previous source/origin match current source/origin
- positive `min_quiet_seconds`
- quiet window elapsed

`READY` only means `REGENERATE_CURRENT_HEAD_E3_BB_REQUEST`; all runtime/trading authority fields remain false.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -B -m pytest -q helper_scripts/research/tests/test_source_stability_window_guard.py helper_scripts/research/tests/test_current_candidate_order_capable_demo_invoke_review_packet.py` -> `21 passed`
- `python3 -B -m py_compile helper_scripts/research/cost_gate_learning_lane/source_stability_window_guard.py` -> passed
- `git diff --check -- helper_scripts/research/cost_gate_learning_lane/source_stability_window_guard.py helper_scripts/research/tests/test_source_stability_window_guard.py helper_scripts/SCRIPT_INDEX.md` -> passed
- E2 returned `DONE_WITH_CONCERNS`; PM fixed wrong-schema previous sample and non-positive quiet-window fail-open risks.
- E4 returned `DONE_WITH_CONCERNS`; PM fixed dirty previous sample fail-open risk.

Smoke artifact `/tmp/openclaw/source_stability_window_guard_20260701T0820Z_current_source_smoke/source_stability_window_guard.json` sha `614cf9dcc68d16a213bfa19fd3d8157039474527acc2eab1abdaa5d08225034d` correctly blocked on `worktree_dirty` at the then-current source head.

## Next

Next PM must first run this source-stability guard after `git fetch` from the actual current source head. A clean first sample records `SOURCE_STABILITY_WINDOW_SAMPLE_RECORDED_NO_APPROVAL`; only a second sample using `--previous-json` after the positive quiet window can produce `SOURCE_STABILITY_WINDOW_READY_FOR_E3_BB_REVIEW`. Then regenerate and dispatch an exact current-head stale-BBO refresh request.

Stop and regenerate/re-review on any source/runtime/auth/candidate/Guardian/BBO/packet drift. Phase A/B still require fresh E3/BB approval; Phase C/order remains blocked until a separate exact in-window E3/BB approval.

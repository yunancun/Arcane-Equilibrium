# TODO continue Wave 4 pre-stage

Date: 2026-05-01
Scope: Continue TODO after operator selected the next 1-4 work items.
Status: Complete for this batch

## Summary

- `[27] intents_counter_freeze` was corrected in `4abb36a` from a false-red signal into a more precise healthcheck:
  - FAIL only when approved risk verdicts exist but no intents are persisted.
  - WARN when scanner/strategy signal snapshots exist but Guardian attempts are absent.
  - WARN when all recent verdicts are rejected by risk/cost gates.
- Wave 4 pre-stage RFCs landed in `5ce777b`:
  - `2026-05-01--lg2_h0_blocking_verification_rfc.md`
  - `2026-05-01--mlde6_live_promotion_contract_rfc.md`
  - `2026-05-01--lg3_provider_pricing_binding_rfc.md`
- Active docs now reflect the 2026-05-01 21:55 CEST wrapper state and distinguish the closed `[27]` false-red from the broader STRK-FUP silent-dead follow-up.

## Runtime State

- Rust engine runtime remains the `daab51c` scanner deploy.
- No rebuild or restart was performed.
- Linux watchdog remains healthy: `engine_alive=true`, demo/live fresh, paper inactive by design.
- Linux wrapper at 2026-05-01 21:55 CEST returned SUMMARY WARN exit 0.

Current notable wrapper observations:
- `[27]`: WARN, demo has recent verdicts but all are rejected by risk/cost gates; no approved-verdict writer wedge.
- `[33]`: maker_like 27.2%, fee_drop 22.0%.
- `[38]`: lifetime_ratio 0.47 WARN.
- `[40]`: 24h MLDE rows 40, avg_net -19.90bps.
- `[41]`: scanner gates fired, labels still insufficient.
- `[11]`: rolling 2d counterfactual replay shrink remains WARN, not FAIL.

## Verification

- `python3 -m py_compile helper_scripts/db/passive_wait_healthcheck/checks_engine.py helper_scripts/db/test_f7_new_healthchecks.py`
- `python3 helper_scripts/db/test_f7_new_healthchecks.py` -> 41/0
- `python3 helper_scripts/db/test_counterfactual_clean_window_healthcheck.py` -> 2/0
- Hard-coded home path scan on the new RFC/report/doc changes.
- `git diff --check`

## Boundary

No trading, risk, strategy parameter, live authorization, DB write, rebuild, restart, or live deploy action was performed.

The broader STRK-FUP healthcheck debt for [3]/[19]/[23]/[24]/[26] remains a future PA/E1 wave; this batch closed the active `[27]` false-red and completed the three Wave 4 PA RFCs.

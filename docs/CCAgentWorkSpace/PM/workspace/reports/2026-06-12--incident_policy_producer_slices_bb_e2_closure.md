# P2 Incident-Policy Producer Slices BB/E2 Closure

> ticket: `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`
> date: 2026-06-12
> scope: PM integration of focused E2 + BB review for newly added producer slices
> boundary: no CI, no deploy/rebuild/restart, no DB/auth/order/risk/trading mutation

## Conclusion

The planned producer source coverage is complete and the new producer slices have passed focused BB/E2 review.

Reviewed slices:

- `sm_halt_stuck`
- `position_drift`
- external watchdog `engine_dead`

Result:

- E2: `PASS-WITH-CONDITIONS`, 0 blocker/high/medium/low.
- BB: `APPROVE-WITH-CONDITIONS`, 0 blocker/high/medium.

This does not close the whole ticket. The next required step is E4/QA/full-chain review before any deploy/rebuild/restart claim.

## Report Links

- `docs/CCAgentWorkSpace/E2/workspace/reports/2026-06-12--incident_policy_producer_slices_re_review.md`
- `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-12--incident_policy_producer_slices_bb_re_review.md`

Prior reviewed CORE/auth/Bybit path:

- `docs/CCAgentWorkSpace/E2/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_review.md`
- `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_bb_review.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_bb_e2_review.md`

## Current Ticket State

Source-live:

- CORE incident policy ledger and C4 feed gate
- `auth_invalid`
- `bybit_fail_closed`
- `sm_halt_stuck`
- `position_drift` notify-only
- external watchdog `engine_dead` notify-only

Focused BB/E2 reviewed:

- prior CORE/auth/Bybit path
- newly added `sm_halt_stuck` / `position_drift` / `engine_dead` slices

Still pending:

- E4 regression/full-chain verification
- QA acceptance over operator-visible behavior
- runtime deploy/rebuild/restart only after explicit operator approval

## Verification

Mac focused:

```bash
cd rust && cargo test -p openclaw_engine sm_halt_incident --lib
# 5 passed

cd rust && cargo test -p openclaw_engine position_reconciler::incident --lib
# 6 passed

cd rust && cargo test -p openclaw_engine notification_failsafe::incident_policy --lib
# 15 passed

cd rust && cargo test -p openclaw_engine event_consumer::tests::c4_failsafe_wire_tests --lib
# 4 passed

python3 -m py_compile helper_scripts/canary/engine_dead_incident.py helper_scripts/canary/engine_watchdog.py helper_scripts/canary/test_canary.py
# PASS

python3 -m pytest helper_scripts/canary/test_canary.py -k 'engine_dead or WatchdogAlertWiring' -q
# 5 passed, 82 deselected
```

## PM Decision

Update TODO from "new producer review pending" to "planned producers source-live / BB+E2 focused re-review passed / E4+QA pending".

Next executable work: run E4 focused regression/full-chain review for this ticket. QA follows only after E4 establishes the integrated path and no collateral regression.

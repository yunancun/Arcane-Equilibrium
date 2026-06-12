# P2 Incident-Policy Dispatch Trigger BB/E2 Review Checkpoint

> ticket: `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`
> date: 2026-06-12
> scope: BB + E2 review of existing CORE+auth+Bybit source-live path
> boundary: no CI, no deploy/rebuild/restart, no DB/auth/risk/trading mutation

## Conclusion

BB and E2 both clear the current CORE+auth+Bybit path to continue.

This is not ticket completion. It is a reviewed partial state:

- CORE `incident_policy` is source-live.
- Auth invalid/resolved producer is source-live.
- Bybit retCode fail-closed/resolved producer is source-live.
- C4 watcher/owner handler path remains the only timer and SM-04 escalation route.

## Guest Review Results

BB: `APPROVE-WITH-CONDITIONS`

- no blocker/high/medium finding;
- no new Bybit request at incident report time;
- exchange stop side effects still flow through C4 owner handler and existing `set_trading_stop` channel;
- retCode producer should be described as business-retCode fail-closed, not full exchange outage coverage.

E2: `PASS-WITH-CONDITIONS`

- no blocker/high/medium/low finding;
- arm/notify split, push-secret gate, single armed owner, stale in-flight guard, and current-class self-heal guard all match the PA model;
- fail-soft paths are explicit;
- remaining producer coverage must stay visible.

Reports:

- `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_bb_review.md`
- `docs/CCAgentWorkSpace/E2/workspace/reports/2026-06-12--incident_policy_dispatch_trigger_review.md`

## Remaining Work

Still pending before ticket completion:

- `sm_halt_stuck` producer coverage
- `position_drift` notify-only producer coverage
- external `engine_dead` watchdog notify-only producer coverage
- E4/QA/full-chain review after producer coverage decision
- runtime deploy/rebuild/restart only after explicit operator approval

## PM Decision

Update TODO from "BB/E2 pending" to "BB/E2 reviewed partial".

Next recommended development slice: implement the remaining producer coverage under the existing model, starting with `sm_halt_stuck` because it is the only remaining arm-class incident and therefore exercises the highest-risk branch. Keep `position_drift` and `engine_dead` notify-only unless PA changes their class policy.

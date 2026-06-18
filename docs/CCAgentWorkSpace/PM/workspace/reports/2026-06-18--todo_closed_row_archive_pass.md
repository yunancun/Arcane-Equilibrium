# TODO Closed Row Archive Pass

PM SIGN-OFF: APPROVED

## Scope

Apply the DONE lifecycle from `docs/agents/todo-maintenance.md`: remove completed detail from active `TODO.md` once it no longer helps immediate handoff.

## Archived From §5

- `P0-EDGE-1-CAND-FUNDING-TILT-DIAGNOSTIC`
- `P3-FUNDING-TILT-HARNESS-3LOW-DEBT`
- `P2-ORDERLINKID-HARDENING`
- `P3-110072-10001-DUP-OPEN-FAILCLOSED-EVAL`
- `P2-POSTMORTEM-CLASSIFIER`
- `P1-OPS-2-14D-SOAK-OBSERVE`
- `P2-OPS-4-GAP-B-D-UNIT-TEST-GAP`
- `P2-A1-RUNNER-WIRE-TO-BASIS`

Each removed row was either no-reopen, fully done with no next action, or duplicated by a still-active event-trigger/deploy-gated row.

## Explicitly Kept

Rows with active deploy gates, operator gates, future review dates, or event-triggered follow-up remain in `TODO.md`, including L2 tails, AEG-S3 Gate-B, P5-SM step-iii, AC19 decision, OPS-2 cutover, Stage0R event trigger, market ticker deploy gate, and incident-policy runtime activation.

## Boundary

Docs/TODO hygiene only. No source, runtime, DB, auth, risk, order, or trading mutation.

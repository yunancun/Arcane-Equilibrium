# Three Main Blockers Runtime Closure

Date: 2026-05-09
Role: PM
Status: APPROVED

## Scope

Closed or restored the three active blockers the operator asked to continue:

- `P0-NEW-VULN-2` lease audit runtime 0 emit: Rust now emits a synthetic
  `BYPASS` transition for non-production facade lease bypass without creating
  SM objects; V078 widens `learning.lease_transitions.to_state`.
- `P0-DECISION-AUDIT-2/4/5`: AMD-2026-05-09-02 selects SM-05 Option A, the
  five-strategy verdict, legacy `openclaw_core` sunset candidates, and
  Layer2 manual/supervisor-only boundary.
- `P0-NEW-ISSUE-1` LiveDemo auth missing: restored via signed
  `/api/v1/live/auth/renew`, not by writing `authorization.json` manually.

## Runtime Result

- Pushed `e97a333b` and `862e79b7` to `main`.
- Linux `trade-core` fast-forwarded to `862e79b7` and rebuilt/restarted with
  `restart_all.sh --rebuild --keep-auth`.
- `_sqlx_migrations` has V078 applied; `learning.lease_transitions` is
  nonzero with `BYPASS` rows (`demo`, `live_demo`; final spot-check rows=103).
- `[56] live_pipeline_active` PASSes after auth renewal and after restart:
  endpoint=`live_demo`, auth present, snapshot fresh.

## Boundary

No true mainnet API was enabled. No strategy/risk config was mutated. The
signed LiveDemo authorization is a readiness/runtime restoration for
`live_reserved`, not MAG-083/MAG-084 approval and not true-live authorization.

## Remaining Follow-Up

- W-AUDIT-3 F-01 provider fail-closed implementation.
- W-AUDIT-6 strategy verdict implementation.

RCA update: the auth loss was traced to a 2026-05-09T01:11:28Z boot that
consumed a `manual` restart sentinel and cleared `authorization.json` before
the later keep-auth restart. `restart_all.sh --keep-auth` now warns if the live
slot is configured but signed auth is already absent.

PM SIGN-OFF: APPROVED.

# REF-21 V1.3 Empirical Gap Closure PM Report

**Date:** 2026-05-06
**Owner:** PM
**Status:** P0 partial closure landed; R2/R3 remain BLOCKED

## Decision

Accepted the final 8-agent real-code audit. V1.3 had material spec-to-deploy
drift, especially the §10 baseline namespace collision and missing real
migration targets.

## Landed

- Fixed §10 replay baseline SLA: `2555/17` is now explicitly pytest regression
  history, not fixture row/decision count. Replay baseline is `254062 ±1%`
  fixture rows, `10080 ±5%` scan cycles, and `500-1500` intents.
- Added live release profile guard for full-chain prepare:
  `OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP=1` is now required before bulk Bybit
  fetches can run from production host profile.
- Landed V057-V060 migration targets for MIT dry-run:
  tier promotion approval, symbol universe + strategy freeze log, edge estimate
  snapshots, and replay emergency audit log.
- Corrected review ordering to Step -1 migration implementation before Step 0
  MIT Linux PG dry-run.
- Restored LOC governance in the active REF-21 plan.
- Corrected GUI companion spec and CLAUDE.md to the real 13-tab console.

## Remaining Blockers

R2/R3 stay blocked until MIT dry-runs V057-V060 on Linux PG, the SECURITY
DEFINER promotion calculator has a real body, `/full-chain/run` is implemented,
and replay rate/IP isolation is enforced with a dedicated Bybit public client.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_full_chain_routes.py tests/migrations/test_v057_v060_ref21_replay_governance.py -q`
  -> 10 passed.
- `git diff --check` -> passed.

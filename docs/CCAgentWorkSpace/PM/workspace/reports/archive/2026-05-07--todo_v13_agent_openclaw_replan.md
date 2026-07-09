# TODO v13 Agent/OpenClaw Replan

Date: 2026-05-07
Role: PM
Status: COMPLETE

## Scope

Re-read the active TODO against the latest Agent design and OpenClaw
positioning. Remove stale or inapplicable work from the active queue, archive
expired context, and rebuild the work schedule.

## Decisions Applied

- OpenClaw Gateway is communication/mobile/supervisor/proposal relay only.
- Existing FastAPI console is the only GUI and the OpenClaw Control Console.
- Local 5-Agent runtime stays inside TradeBot.
- Rust remains trading/risk/config/execution authority.
- Replay remains advisory and cannot substitute for MAG-082 runtime lineage.

## TODO Changes

`TODO.md` is now v13 and acts as an active dispatch queue, not a history ledger.

The top order is:

1. `W-A` executor fake-live runtime smoke.
2. `W-B` runtime decision-spine lineage wiring.
3. `W-C` new MAG-082 Stage 2 evidence window after explicit operator runtime
   authorization.
4. `W-D` MAG-083/MAG-084 only after MAG-082 PASS.
5. `W-E` OpenClaw read-only brief/diagnostics/escalations.
6. `W-F` edge/data quality and Live Gate foundation.
7. `W-G` proposal/approval/mobile relay after read-only foundation and
   explicit operator approval.

## Archived

Created `docs/archive/2026-05-07--todo_v12_agent_openclaw_replan_archive.md`.
The full pre-replan TODO remains recoverable with:

```bash
git show 66cbc0e1:TODO.md
```

## Boundary

This was documentation and planning only. No rebuild, restart, live auth
mutation, scanner authority change, executor shadow unlock, lease-router flag
enablement, OpenClaw write/proposal route, or DB write was performed.

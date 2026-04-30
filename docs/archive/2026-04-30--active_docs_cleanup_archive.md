# Active Docs Cleanup Archive

Date: 2026-04-30

## What Was Archived

The active entry documents were too large and mixed current state with closed wave history. Before trimming, full snapshots were preserved:

- `docs/archive/2026-04-30--CLAUDE-pre-cleanup-snapshot.md`
- `docs/archive/2026-04-30--TODO-pre-cleanup-snapshot.md`
- `docs/archive/2026-04-30--README-pre-cleanup-snapshot.md`

The following content classes were removed from active surfaces and left in archive/history:

- 62-finding remediation Batch A-F execution narrative and old "current mainline" framing
- STRKUSDT P0 wave and Wave A-H historical narratives
- old Wave 1-3 implementation details that no longer guide current work
- stale runtime notes from 2026-04-29, including obsolete blocker framing around `[16]`
- duplicate hard-boundary blocks in README that are now maintained in `CLAUDE.md` §四

## Current Active Sources

- `CLAUDE.md`: compact project constitution, hard boundaries, and current system state
- `TODO.md`: active queue, time-driven gates, and healthcheck map
- `README.md`: operator-facing entrypoint and current status summary
- `.codex/MEMORY.md`: durable Codex operating memory

## Linear Mirror

Linear project `OpenClaw 62-Finding Remediation` was updated as a high-level mirror only. Git and markdown ledgers remain source of truth.

Updated Linear scope:

- Batch A-F issues are Done
- project summary/description now says remediation is closed and follow-up is edge/dust observation
- active follow-up issues were added for post-deploy edge observation, dust residual runtime proof, and Scout heartbeat wiring

No secrets, API keys, exact runtime process details, or detailed fill/fee internals were published to Linear.

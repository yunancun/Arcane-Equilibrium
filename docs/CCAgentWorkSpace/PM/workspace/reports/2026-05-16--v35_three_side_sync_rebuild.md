# PM Report — v35 Current Progress Sync + Rebuild Decision

Date: 2026-05-16
Role: PM

## Verdict

CONDITIONAL before deploy: source/test is green enough to sync, and rebuild is required because v35 contains Rust runtime changes.

## Facts Verified

- Mac source before docs sync: `a7cb517f` after WP-13 leftover P1 fix.
- Origin before push: `864f4e81`.
- Linux `trade-core` after fetch: clean but behind origin by 1 before this v35 sync.
- Runtime before rebuild: engine PID `4153823`, API PID `4153920`; prior runtime binary line remained `7b33ab2e`.
- C1 liquidation proof is no longer running. Latest report: `FAIL_CONNECTION`, finished `2026-05-16T00:37:25Z`, observed `17055.2s/86400s`, `allLiquidation.BTCUSDT` messages = 15, subscribe failures = 0, blocker = connection lost.

## WP-13 Leftover Closure

Commit `a7cb517f` closes the Round 4 WP-13 leftover P1:
- strategist scheduler tuning now reads `DemoCmdSenderSlot` through `tune_cmd_snapshot()`
- edge-estimate reload demo fan-out now reads the current demo slot
- demo reconciler remains on the WP-13 provider pattern
- paper reload remains by-value by design because paper is disabled and has no paper slot infra

Verification:
- `cargo check --release -p openclaw_engine` PASS
- `cargo test --release -p openclaw_engine tune_cmd_snapshot` PASS 2/2
- `cargo test --release -p openclaw_engine edge_reload_tests` PASS 16/16
- `cargo test --release -p openclaw_engine --lib` PASS 2908/0/1 after escalated rerun for socket tests
- `cargo test --release -p openclaw_engine --bin openclaw-engine` PASS 62/0

## Rebuild Decision

Rebuild is required after source sync:
- Rust runtime files changed in WP-03/WP-10/WP-13 and v35 leftover close
- Linux runtime still runs the prior rebuilt binary line before deployment
- `restart_all.sh --rebuild --keep-auth` is the repo-default rebuild path

Boundary:
- no live auth renewal
- no paper enablement
- no demo canary launch
- no production liquidation topic revival
- no strategy/risk sizing change

## Post-Deploy Section

Pending at report creation time. Fill after Linux source sync and rebuild.

# PM Report — v35 Current Progress Sync + Rebuild Decision

Date: 2026-05-16
Role: PM

## Verdict

DONE: source/test was green enough to sync, three-side source sync completed, and the required v35 rebuild/restart completed on `trade-core`.

## Facts Verified

- Mac source before docs sync: `a7cb517f` after WP-13 leftover P1 fix.
- Origin before push: `864f4e81`.
- Linux `trade-core` after fetch: clean but behind origin by 1 before this v35 sync; later fast-forwarded to runtime/code-bearing head `5f6f3edf`.
- Runtime before rebuild: engine PID `4153823`, API PID `4153920`; prior runtime binary line remained `7b33ab2e`.
- Runtime/code-bearing three-side sync before rebuild: Mac/origin/Linux clean at `5f6f3edf`.
- Rebuild command on Linux: `PATH=$HOME/.cargo/bin:$PATH bash helper_scripts/restart_all.sh --rebuild --keep-auth`.
- Runtime after rebuild: engine PID `69581`, API PID `69674`; watchdog `engine_alive=true`, demo fresh.
- Live status after rebuild: inactive/stale because signed live authorization is absent. `--keep-auth` preserved the missing-auth state and did not renew auth.
- Paper status after rebuild: engine env has `OPENCLAW_ENABLE_PAPER=0`; engine log says paper pipeline disabled and `paper_state.disabled=true`. A fresh paper marker is a disabled-state write, not active Paper trading.
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

Rebuild was required after source sync and has been completed:
- Rust runtime files changed in WP-03/WP-10/WP-13 and v35 leftover close
- `restart_all.sh --rebuild --keep-auth` is the repo-default rebuild path
- Linux runtime had been on the prior rebuilt binary line before deployment; it now runs the post-v35 rebuilt binary

Boundary:
- no live auth renewal
- no paper enablement
- no demo canary launch
- no production liquidation topic revival
- no strategy/risk sizing change

## Post-Deploy Section

Post-deploy verification:
- Mac/origin/Linux were aligned at runtime/code-bearing head `5f6f3edf` before rebuild; post-rebuild docs-only commits may advance repository HEAD without another rebuild.
- Linux runtime processes are running: engine PID `69581`, API PID `69674`.
- Watchdog confirms engine alive and demo fresh.
- Paper remains disabled by `OPENCLAW_ENABLE_PAPER=0`; do not treat fresh `paper_state.disabled=true` as active paper execution.
- Live remains inactive because signed live authorization is absent; true-live remains blocked.
- The next code-bearing change will require a fresh rebuild decision. The post-deploy documentation-only sync does not require another rebuild.

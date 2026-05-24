# Sprint 1A -> 1B Recheck

Date: 2026-05-25
Owner: PM local recheck
Scope: re-run the 2026-05-24 audit after commits `015b9735`, `bbb21c56`, and `70cac13f`.

## Verdict

The state improved materially since the 2026-05-24 audit, but it is still not a full product closure.

Closed or improved:
- C10 synthetic spot close PnL source gap is fixed in `015b9735`.
- IntentType direction mismatch source gap is fixed in `015b9735`.
- Earn Wave C IntentProcessor branch is source-landed in `bbb21c56`.
- Running trade-core engine now contains C10/Earn strings: `funding_harvest=6`, `EarnStake=2`.
- API is healthy on the actual Tailscale bind: `http://100.91.109.86:8000/api/v1/healthz` returned HTTP 200.
- PG current landed SQL set remains healthy: `_sqlx_migrations` max=112 / count=102.

Still not complete:
- Engine PID 320381 is running from a deleted executable. `/proc/320381/exe` points to `openclaw-engine (deleted)`.
- Running executable SHA differs from on-disk binary SHA: running `b005bb007728e9703faf3c1f667fb807c94f017d69fa78b5ae38d9fbec7ce9f6`, path `c88f82b6301686df7ba4f12bbb6d7c0848193323e96a22b00461f1fe40c82bec`.
- Earn first stake is still not executed: `learning.earn_movement_log` has 0 rows.
- C10 7d demo observation is still in progress until 2026-06-01.
- True live remains blocked by P0 gates and is not affected by this closure.

## Runtime Evidence

trade-core:
- Repo HEAD: `70cac13f`.
- Engine PID: 320381, started 2026-05-25 00:27:55 +0200.
- Running executable: `/home/ncyu/BybitOpenClaw/srv/rust/target/release/openclaw-engine (deleted)`.
- Running executable mtime: 2026-05-25 00:27:47 +0200.
- On-disk binary mtime: 2026-05-25 00:29:08 +0200.
- Watchdog: `engine_alive=true`; demo snapshot fresh.
- API: PID 320486 bound to `100.91.109.86:8000`; Tailscale healthz HTTP 200. Localhost `127.0.0.1:8000` is not listening and should not be used as the health check for the current bind.
- `/tmp/openclaw/watchdog_status.json`: missing.

PG:
- `_sqlx_migrations`: max=112 / count=102.
- V100/V101/V102/V103/V106/V107/V112 all `success=true`.
- Health rows in last 30m: `api_latency=240`, `database_pool=150`, `engine_runtime=354`, `pipeline_throughput=295`, `risk_envelope=35`, `strategy_quality=882`.
- `learning.earn_movement_log`: 0 rows.
- `learning.replay_divergence_log`: 0 rows.

Local targeted tests:
- `cargo test -p openclaw_core --release lease_scope`: 7 passed.
- `cargo test -p openclaw_engine --release --lib strategies::funding_harvest`: 66 passed.
- `cargo test -p openclaw_engine --release --lib earn`: 80 passed.
- One attempted cargo command with two filters was invalid; it was replaced by the `earn` filter above.

## PM Assessment

C10/Earn source and feature presence are no longer the main gap. The active runtime gap is deploy hygiene and reproducibility: the process is not running the same inode/hash as the current on-disk binary. This can hide future restart behavior and invalidates the earlier "proc exe non-deleted" acceptance statement.

Earn remains a product blocker because no first stake occurred. The code path can be present and tested, but the desired first-stake outcome requires OP-1 key refresh and an actual $100-200 Flexible-only stake that writes `learning.earn_movement_log`.

## Next Action

1. Schedule a safe no-live restart/rebuild window on trade-core.
2. After restart, verify `/proc/$pid/exe` is not deleted, proc/path SHA is aligned or explicitly explained, watchdog is alive, API healthz is 200 on the actual bind, and PG health rows still flow.
3. Keep Earn first stake operator-blocked until OP-1 key refresh and a real first stake row exists.
4. Do not promote Sprint 4 live readiness from this work; P0 gates remain.

# Runtime Redeploy: eaf0c7e

Date: 2026-05-01 23:17 CEST
Status: Complete

## Scope

- Synced `trade-core` from `daca52f` to `eaf0c7e` with `git pull --ff-only origin main`.
- Ran full planned redeploy:
  - `PATH=$HOME/.cargo/bin:$PATH bash helper_scripts/restart_all.sh --rebuild --keep-auth`
- This intentionally accumulated the pending source/static/API changes into one runtime redeploy.

## Result

- Rust engine rebuilt and restarted.
- API restarted with 4 workers.
- New runtime process state:
  - Engine PID `2455097`.
  - API PID `2455171`.
  - Watchdog PID `3450754`.
  - Gateway PID `3973441`.
- `/api/v1/strategy/prelive/edge-gates` returns `401 unauthenticated` rather than `404`, so the new pre-live route is loaded behind auth.

## Verification

- Linux source clean at `eaf0c7e`.
- Linux `python3 -m py_compile` passed for the touched API modules before restart.
- `restart_all.sh --rebuild --keep-auth` completed after adding `~/.cargo/bin` to PATH for the SSH non-interactive shell.
- Watchdog after redeploy:
  - `engine_alive=true`.
  - `paper`, `demo`, and `live` snapshots fresh.
- Passive wrapper after redeploy:
  - SUMMARY `WARN`, exit 0.
  - Current WARNs: `[4]`, `[10]`, `[33]`, `[38]`, `[40]`, `[41]`, `[11]`.
  - `[33]`: fee_drop `22.0%`.
  - `[38]`: lifetime_ratio `0.41`.
  - `[40]`: rows `37`, avg_net `-17.21bps`.

## Boundary

- No DB migration apply.
- No strategy/risk parameter change.
- No live authorization mutation; `--keep-auth` preserved the existing authorization.
- No HTTPS deploy.

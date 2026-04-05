# 2026-04-05 Daily Summary

## Completed

### RC-10: Disable Python Paper Engine — Rust is Sole Trading Engine (commit 626b92c)

**Problem 1: GUI Demo Tab showing "未连接" (not connected)**
- Root cause A: Route ordering conflict — `/{name}/status` wildcard in `strategy_read_routes.py` matched before `/demo/status` in `strategy_ai_routes.py`, causing 404 "Strategy 'demo' not found"
- Root cause B: GUI `loadDemoStatus()` checked `retCode === 0` which Rust-first responses don't have
- Fix: Reordered imports in `phase2_strategy_routes.py` (`_ai` before `_read`); added `source === 'rust_engine'` check in `tab-demo.html`

**Problem 2: Paper trading "stop engine" didn't clear positions**
- Root cause: `POST /paper/session/stop` only stopped Python PaperTradingEngine, not Rust engine. But `GET /paper/positions` reads from Rust IPC snapshot. Dual-engine architecture flaw.
- Fix: Completely disabled Python PaperTradingEngine (`ENGINE = None`). All paper trading is now Rust-only.

**Changes (11 files, +319/-521 lines):**
- `paper_trading_wiring.py` — ENGINE=None, removed all ENGINE injections
- `paper_trading_routes.py` — All 24 routes: READ→Rust-only, WRITE→410 Gone
- `main.py` — Removed ENGINE from hard-required startup check, auto-reauth uses Rust snapshot
- `risk_routes.py` — Removed Python fallback for drawdown, unhalt uses PAPER_STORE directly
- `phase2_strategy_routes.py` — Import order fix for demo route priority
- `tab-demo.html` — Rust-first connection detection
- 5 test files updated (3334 Py + 770 Rust = 4104 all green)

## Key Decisions

- **Python PaperTradingEngine permanently disabled** — ENGINE=None prevents dual-engine operation
- **Write routes return 410 Gone** (not 404 or 503) — clearly communicates "deprecated, not broken"
- **Session start returns Rust engine status** if Rust available — GUI won't show error when engine running
- **PAPER_STORE retained** — PaperStateStore still used for unhalt-session mutation; ENGINE class file retained for import compatibility

## Test Baseline

- Python: 3334 passed, 12 skipped, 0 failed
- Rust: 770 passed, 0 failed
- Total: 4104 tests all green

## Engine Health

- Rust engine: alive, 1,031,162 canary records, 3 historical crashes
- Snapshot age: <12s (healthy)

## Remaining Notes

- Rust IPC server has no write commands (stop_session, close_all_positions) — if needed in future, add to `ipc_server.rs dispatch_request()`
- `openclaw_pyo3` test compilation fails due to missing Python linkage in `cargo test --workspace` — run via `maturin develop` instead (known, pre-existing)

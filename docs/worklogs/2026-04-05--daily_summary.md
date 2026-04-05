# 2026-04-05 Daily Summary (Session 8)

## Completed (15 commits)

### RC-10: Disable Python Paper Engine (626b92c)
- Python PaperTradingEngine completely disabled (ENGINE=None)
- All 24 paper routes: READ→Rust-only, WRITE→disabled
- Route ordering fix (/{name}/* wildcard vs /demo/*)
- 11 files, +319/-521 lines, 7 test files updated

### IPC Command Channel (49f6cab)
- PaperSessionCommand enum: Pause/Resume/CloseAll/Reset
- unbounded_channel IPC→event_consumer (zero-lock)
- paper_paused flag in on_tick (skip strategy dispatch, keep prices/indicators/stops)
- 4 new IPC handlers + Python client methods

### P1-P4: Demo Primary Architecture (106f9b6)
- P1: Stop closes Paper+Demo positions simultaneously (PyO3 BybitClient)
- P2: Shadow orders default-on (config.rs both serde + Default impl)
- P3: Session status includes Demo balance from WS sync
- P4: GUI tabs reordered — Demo(Primary) first, Paper(Testing) second

### WS Fix: Broken Topics (29fc1ef)
- Root cause: Bybit liquidation/price-limit/adl-notice return "handler not found" → poisons ENTIRE connection (zero data, heartbeat alive)
- Confirmed via Python WS test: 45 topics without=normal, 50 with=zero data
- Bybit API handbook updated with warning

### GUI Full Migration (ae3db31 + 6b6ce76 + f9cb019 + 7182e03 + 0309bcd)
- All retCode===0 checks → also accept source==='rust_engine'
- Positions format: dict→Array.isArray() guard
- Disabled endpoints: removed all order/submit, order/cancel, market-feed calls
- Demo tab: positions/fills/orders parsers fixed for Rust format
- Demo tab: added start/pause/resume/stop buttons
- Unified control: start re-enabled after stop (paused≠active fix)

### GUI-HANG Fix (3a42c31)
- IPC socket connect 3s timeout (was infinite → 30s OS timeout)
- Removed _get_demo_summary() Bybit API call from session/status hot path
- is_available() eliminated extra stat() call via cached mtime

### Shadow Orders Fix (9020177 + f4e2f2c)
- Skip qty<=0 shadow orders (instrument rounding to 0 for BTC/ETH small positions)
- order_link_id: sh_{ts}_{seq} (was shadow_{ts}, caused duplicates)
- Config Default impl: shadow_orders was hardcoded false in Default trait

### EXT-1 Architecture Design (research only, no code)
- PM+PA+FA+BB+CC five-way joint research
- REJECTED: optimistic execution + rollback (5-subsystem rollback, no reverse_fill)
- ADOPTED: "Exchange-as-Truth" mode (trading_mode=exchange)
- Paper=local record after exchange confirmation, not primary execution
- Demo=Live unified code path, switch by BybitEnvironment config
- Design written to TODO EXT-1-01~10

## Key Decisions
1. Demo is PRIMARY execution engine, Paper is TESTING engine
2. Shadow orders = default-on (Demo mirrors Paper fills automatically)
3. Python PaperTradingEngine permanently disabled (zero chance of dual-engine)
4. "Exchange-as-Truth" is the correct Live architecture (not optimistic+rollback)
5. 4-worker uvicorn prevents single-worker GUI hang

## Test Baseline
- Python: 3334 passed, 12 skipped
- Rust: 790 passed (1 pre-existing feature_collector fail)
- Total: 4124 tests

## Next Steps
- EXT-1: Implement Exchange-as-Truth execution mode (10 tasks in TODO)
- IPC-05: Python file deprecation (post EXT-1)
- Phase 4: Claude Teacher + DL models

# Session 9 Work Log — EXT-1 Exchange-as-Truth + L3 Audit + Risk Config
# 2026-04-05

---

## Summary / 摘要

Session 9 implemented the EXT-1 "Exchange-as-Truth" execution mode, resolved all L3 audit findings,
fixed zero-qty ghost positions, made P1 risk cap configurable, and wired all GUI risk parameters
through IPC to the Rust engine for full runtime configurability.

Test baseline: 856 Rust + 1075 Python = 1931 tests (0 failures, 1 pre-existing skip)

---

## Completed Items / 已完成項

### EXT-1: Exchange-as-Truth Implementation (commit b878f61)

- `config.rs`: TradingMode enum (PaperOnly/Exchange) + trading_mode cold param
- `tick_pipeline.rs`: on_tick() dual-mode bifurcation — paper_only=local sim+shadow, exchange=gates-only+order dispatch
- `intent_processor.rs`: ExchangeGateResult + process_gates_only() (gates without simulated fill)
- `event_consumer.rs`: PendingOrder tracking + order_id→order_link_id mapping + 5s/60s timeout
- `event_consumer.rs`: ExchangeEvent channel (Fill/OrderUpdate/DCP/Disconnected) from ExecutionListener
- `tick_pipeline.rs`: apply_confirmed_fill() for exchange-confirmed fills
- `paper_trading_routes.py`: GUI session status + IPC get_state include trading_mode

### L3 Audit Fixes (commit 5c1c935)

- **P0-1**: paper_state.apply_fill partial close fix (reduce qty, don't remove)
- **P0-2**: exec_id dedup via VecDeque ring buffer (max 500)
- **P0-3**: DCP/Disconnected events wired from ExecutionListener to event_consumer
- **P0-4**: pending_close_symbols cleared on close order rejection
- **P0-5**: Exchange mode balance reconciliation from WS wallet (>0.1% drift)
- **SEC-1**: Cold params preserved on hot-reload (SIGHUP)
- **SEC-5**: Mainnet requires OPENCLAW_ALLOW_MAINNET=1 env var

### Zero-qty Ghost Position Fix (commit 66ee29b)

- Root cause: P1 cap rounds to 0 for BTC/ETH with $1000 balance
- Fix: Guard in tick_pipeline (skip fill if qty=0) and paper_state.apply_fill (reject qty<=0)

### P1 Risk Cap Configurable (commit 8103c6f)

- P1_RISK_PCT was hardcoded const 0.02 in intent_processor
- Now configurable via engine.toml `p1_risk_pct` field

### GUI→IPC→Rust Risk Config Wiring (commit f7c9086)

- PaperSessionCommand::UpdateRiskConfig IPC command
- Python ipc_client.update_risk_config() method
- risk_routes.py pushes changes to Rust engine

### Full Runtime Risk Configurability (commit d053a51)

- StopConfig: added take_profit_pct + check_take_profit()
- Guardian: expose config()/update_config() for runtime updates
- PaperSessionCommand::UpdateRiskConfig expanded to 9 fields (was 2)
- All GUI risk params now flow to Rust:
  - Hard Stop, Take Profit, Trailing Stop, Time Stop
  - ATR Multiplier, Max Drawdown, Max Leverage, Max Positions, P1 Risk Cap
- RuntimeConfig: added max_leverage, max_drawdown_pct, max_same_direction_positions
- Startup wiring: engine.toml → Guardian + StopConfig + IntentProcessor
- Agent auto-tuning path: /api/risk/agent-adjust → IPC → Rust engine

---

## Key Decisions / 關鍵決策

1. **Exchange-as-Truth adopted** — rejected "optimistic fill + rollback" (rollback spans 5 subsystems, no reverse_fill/on_fill_reverted). Exchange mode: only exchange-confirmed fills update paper state.
2. **All risk params MUST be runtime-configurable** — required for Agent learning loop (Phase 4+).
3. **Mainnet requires explicit env var guard** — OPENCLAW_ALLOW_MAINNET=1 prevents accidental mainnet deployment.
4. **Cold params preserved on SIGHUP reload** — prevents accidental mode switch (e.g., trading_mode change via hot-reload).

---

## Test Baseline / 測試基準線

```
Rust:   856 tests (+4 new from Session 8 baseline of 852)
Python: 1075 passed, 1 pre-existing skip (grafana)
Total:  1931 tests
```

---

## Known Issues Discovered / 發現的已知問題

- Sharpe-based dynamic position sizing not yet implemented (placeholder in kelly_sizer)
- Daily loss limit enforcement is Python-only (not wired to Rust Guardian)

---

## Next Steps / 下一步

- Phase 4 (W13-15): Claude Teacher + LinUCB + News Agent + DL-3
- EXT-2: REST reconciliation for exchange mode disconnect recovery
- Read TODO.md for current task queue

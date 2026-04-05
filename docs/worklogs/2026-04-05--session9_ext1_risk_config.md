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

---

## Session 9 追加：核心風控接線審計結果

### 發現：openclaw_core 風控函數已寫但未接入引擎

| 函數 | 位置 | 行數 | 檢查項 | 狀態 |
|------|------|------|--------|------|
| `check_order_allowed()` | risk/checks.rs:57 | 62 行 | 5 check (日虧損/槓桿/單倉/總曝險/關聯曝險) | ❌ 未調用 |
| `check_position_on_tick()` | risk/checks.rs:154 | 111 行 | 9 check (硬止損/ATR動態/止盈/跟蹤/時間/成本稅/回撤熔斷/連虧冷卻/日虧損) | ❌ 未調用 |
| `H0Gate::check()` | h0_gate.rs:240 | 1040 行 | 5 check (新鮮度/健康/資格/風險信封/冷卻) | ❌ 未調用 |
| `check_portfolio_risk()` | portfolio.rs:92 | 66 行 | 3 check (儲備緩衝/行業集中/相關性) | ❌ 未調用 |
| `PriceHistoryTracker` | risk/price_tracker.rs | 294 行 | ATR 計算 + 3σ 尖刺檢測 | ❌ 未調用 |
| `compute_dynamic_stop_pct()` | risk/stops.rs:41 | 27 行 | ATR 自適應 + 反聚集偏移 | ❌ 未調用 |
| `RiskManagerConfig` | risk/config.rs | 176 行 | 行情乘數(trending/volatile/ranging/squeeze) | ❌ 未使用 |

### 引擎當前實際執行的風控
- IntentProcessor: GovernanceCore auth + Guardian 4-check + Kelly + P1 cap
- tick_pipeline: stop_manager::check_stops (硬止損/跟蹤/時間，最簡單版本)
- 無 H0 Gate、無 ATR 動態、無反聚集、無尖刺檢測、無回撤熔斷、無連虧冷卻

### 下一步行動計劃（RRC-1: Risk Runtime Connect）

**Phase A: H0Gate 接入** (最簡單，自包含)
- tick_pipeline 加 H0Gate 實例
- on_tick Step 0.5: h0.check(symbol) → 如果被阻則跳過策略分派
- main.rs: 定期 update_health / update_risk

**Phase B: check_order_allowed 接入 IntentProcessor**
- 新增 Gate 0（在 governance 之後、Guardian 之前）
- 需要新增狀態：daily_start_balance, daily_loss_pct, exposure 計算
- RiskManagerConfig 從 RuntimeConfig 讀取

**Phase C: check_position_on_tick 替換 check_stops**
- PriceHistoryTracker 實例加入 tick_pipeline
- 每個 tick 記錄價格 → compute_atr_pct
- 替換 Step 6 的 check_stops 為 check_position_on_tick
- 新增狀態：consecutive_losses, trailing_stops per symbol, spike_suppression

**Phase D: 風控單一真相源**
- GUI 風控讀取改為 Rust 快照
- PipelineSnapshot 加入 stop_config + guardian_config + risk_state
- Python RiskManager 降級為歷史遺留

**Phase E: 清理 P1/P2**
- 修復 ai-context 端點
- 策略啟停 IPC 接入
- 治理狀態統一
- Python 死代碼清理

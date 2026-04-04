# 2026-04-04 Session 3 — Rust-first 改造 + RC-12 + 全面審計

## 一、Klines 加入 Rust Snapshot

- `openclaw_core::klines::KlineBuffer::latest_cloned()` — 不可變克隆最新 N 根 K 線
- `PipelineSnapshot.klines` — `HashMap<String, Vec<KlineBar>>`（1m，最多 100 根）
- `snapshot()` 從 `kline_manager` 收集每 symbol 的 1m 已完成 K 線
- Python `RustSnapshotReader.get_klines(symbol, n)` — 從 snapshot 讀取
- `get_klines` 路由改為 Rust-first + Python fallback

## 二、strategy_read_routes Rust-first 改造

| 路由 | 改造前 | 改造後 |
|------|--------|--------|
| `get_klines` | Python only | ✅ Rust-first |
| `get_indicators` | 1m only Rust | ✅ 所有 timeframe Rust-first |
| 其他 7 路由 | 已 Rust-first | ✅ 不變 |
| 3 Python-only | Scanner/Deployer | ✅ 保留（獨立組件） |

**最終：10/13 路由 Rust-first。**

## 三、RC-12：停用 Python MarketDataDispatcher 自動啟動

### 問題
`strategy_wiring.py:983` 在 `global_mode in _FEED_AUTO_MODES` 時自動啟動 Python MarketDataDispatcher，建立**獨立 WebSocket 連接到 Bybit**。RC-11 後 `engine.tick()` 已停用，但 WS 連接仍在：
- Rust：255K ticks，5 symbols，完整處理
- Python：169K ticker updates，1.3M messages，**什麼都不做**

### 修復
`strategy_wiring.py` — `if False and ...` 禁用自動啟動。手動 `/market-feed/start` 保留供調試。

## 四、全面審計結論

### Tick 處理路徑
- ✅ 所有 Python tick 路徑正確停用（RC-10 + RC-11 + RC-12）
- ✅ 無重複 WS 連接（RC-12 後）
- ⚠️ `POST /paper/tick` 端點仍可手動觸發（debug-only）

### 重複邏輯
- ✅ 7 個 Python 交易組件全部休眠（IndicatorEngine / SignalEngine / Orchestrator / GovernanceHub cascade / PaperEngine matching / StopManager / PnL）
- ✅ 無活躍重複處理

### 進程核實
- Rust engine: 1 個實例（PID 3851697），255K+ ticks
- Python uvicorn: 1 個實例（PID 3689280），API 層
- Python dispatcher WS: **將在下次重啟後不再自動啟動**（RC-12）
- watchdog: 1 個實例，正常監控

### AUTO_DEPLOYER / MARKET_SCANNER
- MARKET_SCANNER：獨立 HTTP 掃描器，不依賴 tick 管線，保留
- AUTO_DEPLOYER：依賴 PaperEngine（submit_order + trade_history），暫保留
- 4 個 Python-only 路由保持現狀

## 五、測試基準線

```
Rust:   763 passed / 0 failed
Python: 3345 passed / 0 failed / 1 skipped
```

## 六、修改文件

```
# Rust klines in snapshot
M  rust/openclaw_core/src/klines.rs              — latest_cloned()
M  rust/openclaw_engine/src/tick_pipeline.rs      — PipelineSnapshot.klines + snapshot()
M  rust/openclaw_engine/src/ipc_server.rs         — test snapshot 加 klines field

# Python Rust-first 改造
M  app/ipc_state_reader.py                        — get_klines()
M  app/strategy_read_routes.py                    — get_klines + get_indicators Rust-first

# RC-12
M  app/strategy_wiring.py                         — dispatcher 自動啟動禁用

# 測試修復
M  tests/test_phase2_strategy_routes_coverage.py  — mock Rust reader for indicators
```

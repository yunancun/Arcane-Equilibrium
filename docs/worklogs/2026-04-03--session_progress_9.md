# Session Progress — 2026-04-03 Session 9（Engine Live + API Compatibility + R-05 Decision）

## 已完成項

### Engine Live Wiring（commit `95b45f5`）

**main.rs 完整接入 TickPipeline：**
- 替換 placeholder event consumer，接入完整 tick 處理管線
- 5 幣種訂閱：BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT
- 4 策略註冊：MA Crossover, BB Reversion, BB Breakout, Grid Trading
- Paper authorization 啟動自動授予
- 30 秒定期 status report + JSON state persistence + JSONL audit trail
- rustls ring crypto provider 安裝（WSS TLS 支持）
- Strategy trait 加 `Send` bound（tokio::spawn 兼容）
- WS client 預設訂閱清空（改由 main 控制）

**Bug Fix: check_stops 跨幣種價格污染**
- 問題：BTC tick price ($66,954) 被用來更新 ETH 持倉的 best_price
- 修復：改用 per-symbol latest_prices 查詢，每個持倉用自己幣種的價格

### 10 分鐘 Live Bybit WS 實測

| 指標 | 結果 |
|------|------|
| 運行時間 | 571 秒 |
| 總 ticks | 38,389 |
| Paper fills | 8 筆（4 BTC + 2 ETH + 1 SOL + 1 DOGE）|
| Stops triggered | 0 |
| Balance | $9,999.85 |
| 持倉 | 4（BTC short + ETH long + SOL long + DOGE long）|
| 追蹤幣種 | 5/5 |
| 崩潰 | 零 |
| WS 斷線 | 零 |

### 29 壓力集成測試（stress_integration.rs）

- Fast track 緊急通道：5 tests（CloseAll/Reduce/Pause/5% 邊界/90% 邊界）
- 多幣種混合：2 tests（5 幣 500 ticks + 快速交替 1000 ticks）
- 策略邊界：5 tests（whipsaw/oversold/false squeeze/valid breakout/grid traversal）
- Guardian + Governance：4 tests（drawdown/conflict/position limit/no auth）
- 止損邊界：4 tests（hard 5%/4% safe/short stop/multi-position isolation）
- 管線吞吐：2 tests（10k ticks + 26.9μs release tick latency）
- PnL 正確性：3 tests（long/short/zero-sum round trip）
- 持久化：1 test
- 混合場景：3 tests（volatile market/zero volume/extreme prices）

### QC 數學模型審查

**45+ 個公式全部 CORRECT，3 個 MINOR 備註（非阻塞）：**
1. BB Reversion 退出用 `!is_long` — 設計如此（反向 intent = 平倉）
2. Pearson correlation 用 sum() 而非 Kahan — 小窗口無影響
3. Sharpe ratio 假設日線頻率 — 文檔標註即可

### 9 項 Bybit API 兼容性修復

| # | 級別 | 問題 | 修復文件 |
|---|------|------|---------|
| 1 | CRITICAL | qty_step 硬編碼 3dp | bybit_demo_connector.py |
| 2 | CRITICAL | minOrderQty 未檢查 | symbol_category_registry.py |
| 3 | CRITICAL | positionIdx 未發送 | bybit_demo_connector.py |
| 4 | HIGH | kline confirm 未檢查 | ws_client.rs |
| 5 | HIGH | 無 rate limit 處理 | bybit_demo_connector.py |
| 6 | HIGH | 止損價格一律向下 | bybit_demo_connector.py |
| 7 | MEDIUM | HTTP vs Bybit retCode 混淆 | bybit_demo_connector.py |
| 8 | MEDIUM | 無請求重試 | bybit_demo_connector.py |
| 9 | MEDIUM | accountType 硬編碼 | bybit_demo_connector.py |
| + | MEDIUM | Registry linear 被 spot 覆蓋 | symbol_category_registry.py |

### V2 Bybit Demo Live 驗證

- BTCUSDT Market Buy/Close: PASS（retCode=0）
- ETHUSDT Market Buy/Close: PASS（retCode=0）
- Account type detection: UNIFIED confirmed
- Position mode: one_way confirmed
- Wallet balance: $962.52 USDT
- MinOrderQty validation: correctly rejects 0.0005 BTC
- MinNotional validation: correctly rejects 15 DOGE ($1.35 < $5)

### R-05 Decision Matrix

| 條件 | Go 標準 | 實測結果 | PASS/FAIL |
|------|---------|---------|-----------|
| Engine 獨立運行 | 零崩潰 | 10 分鐘零崩潰 | **PASS** |
| Paper 交易正確記錄 | ≥ 5 筆 | 8 筆 + JSONL 審計 | **PASS** |
| tick P50 | < 100μs | 26.9μs (release) | **PASS** |
| 快速通道 | 觸發正確 | 5 unit + pipeline wired | **PASS** |
| core 單元測試 | 全部通過 | 548 passed / 0 failed | **PASS** |
| 集成測試 | ≥ 20 場景 | 29 stress + 27 golden = 56 | **PASS** |

**6/6 全部 PASS → 建議 Go（繼續 R-06 Python IPC 改造）**

---

## 測試基準線

```
Python: 3741 passed / 28 failed / 17 errors（pre-existing，零回歸）
Rust:   548 passed / 0 failed / 0 warnings
  core:     376 lib + 8 golden + 19 extreme = 403
  engine:   80 unit + 29 stress = 109
  types:    36
API compat: 42 Python tests
```

## 關鍵決策

1. **Production WS for paper trading**：用 Bybit production public WS 取真實行情（無需 API key，只讀）
2. **kline confirm=false 丟棄**：未確認 K 線不送入信號引擎，避免虛假信號
3. **qty_step floor not round**：向下取整避免超出餘額
4. **Stop price direction**：long SL floor，short SL ceil（保守方向）
5. **positionIdx=0 always for one-way**：安全且向前兼容
6. **Registry linear priority**：同名 symbol linear 優先於 spot

## Commits

- `95b45f5` feat: engine live wiring + 9 Bybit API compatibility fixes + 29 stress tests

## 下一步指引

1. **R-05 Go 決策等待 Operator 簽核**
2. Go → R-06 Python IPC 改造（W9-10）：`docs/rust_migration/06--python_ipc_integration.md`
3. No-Go → PyO3 降級路徑（見 `docs/rust_migration/05--week8_decision_gate.md`）
4. V3 集成驗證（Rust→Python IPC→Bybit）需在 R-06 後執行

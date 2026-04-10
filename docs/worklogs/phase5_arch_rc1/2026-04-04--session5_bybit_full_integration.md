# 2026-04-04 Session 5 — Bybit API 全面整合 + Demo→Live 對齊

## Summary

PM+PA+FA+BB 四角色研究 → E1 並行實施 → E2 審查 → E4 回歸。完成 9 項 API 整合改進 + 3 個新模組接入，使 Demo 環境盡量鏡像 Live。

---

## 完成項

### Phase 1: API 功能對比分析
- 對照 Bybit Handbook（64 REST + WS）vs 本地實現
- 識別 9 項可通過 Bybit API 替代/增強的本地邏輯
- 用戶決策：全部現在做完，Demo 應是 Live 的鏡像

### Phase 2: 9 項 API 整合改進

**Batch A — 基礎接通（4 項）：**
| # | 項目 | 改動 |
|---|------|------|
| 2 | 動態費率 | `execution.rs` +3 `_with_rate` 函數 + `IntentProcessor.taker_fee_rate` + 啟動 `refresh_fee_rates()` |
| 6 | 動態滑點 | `PriceEvent.turnover_24h` + ws_client 解析 + `paper_state.latest_turnovers` |
| 7 | Auto-margin | 啟動時 `set_auto_add_margin` 為現有倉位 |
| 8 | DCP | 啟動時 `set_dcp(time_window)` |

**Batch B — WS 回調 + 雙模式（3 項）：**
| # | 項目 | 改動 |
|---|------|------|
| 3 | 雙模式餘額 | `balance_mode` config + `bybit_sync_balance` + WS wallet callback → paper_state |
| 4 | API PnL | `api_unrealized_pnl` HashMap + WS position callback → paper_state + `PositionSnapshot` |
| 5 | WS 回調全接通 | `BybitPrivateWs` + `ExecutionListener` 4 callbacks |

**Batch C — 雙軌止損（1 項）：**
| # | 項目 | 改動 |
|---|------|------|
| 1 | 雙軌止損 | `StopRequest` + mpsc channel + async consumer + 讀 StopConfig 非硬編碼 |

**Batch D — ADL 監控（1 項）：**
| # | 項目 | 改動 |
|---|------|------|
| 9 | ADL 即時監控 | `extended_subscription_list()` 10 topics/symbol + `adl_alerts` ring buffer + rank≥3 warning |

### Phase 3: 三輪審計修復（QA+E5+PA+FA）

3 HIGH + 5 MED 全部修復：
| 嚴重度 | 問題 | 修復 |
|--------|------|------|
| HIGH | WS bybit_balance 未傳入 pipeline | Arc 提取 + 每 tick 同步 |
| HIGH | WS api_pnl 未傳入 pipeline | 同上 |
| HIGH | stop_pct=5.0 硬編碼 | 改讀 `paper_state.stop_config_pct()` |
| MED | Stop 對所有 fill 觸發 | 只對 `get_position()` 存在時派發 |
| MED | ADL ring buffer 未實現 | `adl_alerts: VecDeque` + rank check |
| MED | Private WS handles 未 await | 加入 shutdown block |
| MED | export_state 缺 api_pnl | 新增 `PositionSnapshot` struct |
| LOW | 兩個 impl block | 合併 |

### Phase 4: 3 個新模組整合

**E1-A InstrumentInfoCache：**
- 啟動時 `refresh("linear")` 加載品種規格
- 4 小時定時刷新 task（tokio::spawn + CancellationToken）
- `tick_pipeline` fill 前 `round_qty()` / `round_price()`
- `shared_instruments: Option<Arc<InstrumentInfoCache>>` 提升到 async_main 作用域

**E1-B MarketDataClient Kline Bootstrap：**
- `KlineManager::seed_bars()` 新方法（+4 unit tests）
- 啟動時 5 symbols × 200 bars REST 拉取
- 過濾未關閉 bar + 排序 oldest-first + 類型轉換
- 消除 30 分鐘冷啟動（`ohlcv.close.len() < 30` 立刻滿足）
- `kline_bootstrap: bool` config（默認 true）

**E1-C OrderManager Shadow Mode：**
- `ShadowOrderRequest` struct（含 `is_close` 區分開/平倉）
- 開倉填充後 + 止損平倉後都派發 shadow request
- async consumer 通過 `OrderManager.place_order()` 下 Demo 市價單
- 平倉用 `reduce_only: true` + 實際倉位 qty（E2 修復：原為 0.0 會被 Bybit 拒絕）
- `shadow_orders: bool` config（默認 false，opt-in）
- `order_link_id: "shadow_{ts}"` 用於 WS 回調對比

**E2 審查修復：**
- MED: Shadow close qty=0.0 → 改為捕獲實際倉位 qty
- LOW: Kline bootstrap 冗餘 is_closed 賦值移除

---

## Commits

| Commit | 描述 |
|--------|------|
| `347a6c9` | feat: Bybit API full integration — 9 items + 3 modules |

---

## 測試結果

```
Rust:   770 passed, 0 failed (+7 vs 763 baseline)
  openclaw_core:   385 (+4 seed_bars tests, +3 execution _with_rate tests)
  openclaw_engine: 293 (unchanged)
  openclaw_types:  36 (unchanged)
  stress:          29 (unchanged)
  other:           27
```

---

## 新增 Config 項匯總（8 個）

| 配置項 | 默認值 | 用途 |
|--------|--------|------|
| `dcp_enabled` | true | DCP 斷連保護 |
| `dcp_time_window` | 10 | DCP 時間窗口（秒） |
| `auto_add_margin` | true | 自動追加保證金 |
| `balance_mode` | "custom" | 餘額模式（custom/bybit_sync） |
| `server_side_stops` | true | 伺服器端雙軌止損 |
| `enable_extended_ws` | true | 擴展 WS 訂閱（ADL+price-limit） |
| `shadow_orders` | false | 影子訂單（opt-in） |
| `kline_bootstrap` | true | 啟動 K 線引導 |

---

## 模組整合狀態（8/11）

| 模組 | 狀態 | 用途 |
|------|:---:|------|
| AccountManager | ✅ | 餘額 + 費率 |
| PositionManager | ✅ | auto-margin |
| PlatformClient | ✅ | DCP |
| BybitPrivateWs | ✅ | 5 topic 私有 WS |
| ExecutionListener | ✅ | 4 callback |
| InstrumentInfoCache | ✅ NEW | 品種規格 + 精度校驗 |
| MarketDataClient | ✅ NEW | kline bootstrap |
| OrderManager | ✅ NEW | Shadow 模式 |
| BatchOrderManager | ❌ | Live Gate |
| SpotMarginClient | ❌ | 非核心 |
| LeverageTokenClient | ❌ | 非核心 |

---

## 文件變更匯總

| 文件 | 變更 |
|------|------|
| `openclaw_core/execution.rs` | +3 `_with_rate` 函數 + 3 tests |
| `openclaw_core/klines.rs` | +`seed_bars()` 方法 + 4 tests |
| `openclaw_types/price.rs` | +`turnover_24h` field |
| `openclaw_engine/config.rs` | +8 config fields |
| `openclaw_engine/main.rs` | 啟動序列全面重構（+409 行） |
| `openclaw_engine/tick_pipeline.rs` | +StopRequest/ShadowOrderRequest/instrument_cache/ADL |
| `openclaw_engine/paper_state.rs` | +turnovers/bybit_sync/api_pnl/PositionSnapshot |
| `openclaw_engine/intent_processor.rs` | +taker_fee_rate + dynamic turnover |
| `openclaw_engine/ws_client.rs` | +turnover24h parsing |
| `openclaw_engine/bybit_rest_client.rs` | +credentials() accessor |
| `openclaw_engine/ipc_server.rs` | PositionSnapshot 適配 |
| `openclaw_engine/tests/stress_integration.rs` | PositionSnapshot 適配 |
| 總計 | 13 files, +1037/-38 lines |

---

## 引擎啟動序列（最終版）

```
1. fetch_demo_balance()
2. Create event channel (4096 buffer)
3. Start IPC server
4. Create BybitRestClient (Demo)
5. InstrumentInfoCache refresh("linear")
6. DCP set_dcp(time_window)
7. Auto-margin for existing positions
8. Fee rates refresh_fee_rates("linear")
9. Spawn 4h instrument refresh task
10. Public WS (extended 10 topics/symbol)
11. Private WS + ExecutionListener (4 callbacks)
12. Event consumer task:
    a. Create TickPipeline
    b. Set fee rate + instrument cache
    c. Kline bootstrap (200 bars × 5 symbols)
    d. Set stop channel (server-side stops)
    e. Set shadow channel (if enabled)
    f. Register 4 strategies
    g. Grant paper auth
    h. Sync WS data → paper_state (every tick)
    i. Event loop
```

---

## 下一步

- 更新 CLAUDE.md / README.md / TODO.md 反映新狀態
- 更新 Bybit API 字典手冊（新增 shadow order 流程）
- Phase 1 (5/01): 市場數據 pipeline + FeatureCollector + PSI 漂移
- Live Gate: BatchOrderManager + OrderManager 從 Shadow→Primary

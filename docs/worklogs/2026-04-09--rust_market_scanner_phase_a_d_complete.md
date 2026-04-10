# Rust Market Scanner Phase A-D 實作完整工作日誌
# Rust Market Scanner Phase A-D — Complete Implementation Worklog

**日期 / Date：** 2026-04-09  
**歸檔日期 / Archived：** 2026-04-10  
**Session 背景 / Context：** Phase 5 探索期，觀察 paper 交易模式時發現兩個架構錯誤後緊急修復  
**測試基準線 / Test baseline：** Rust engine lib 769 → 835（+66）  
**最終狀態 / Final state：** Phase A-D + QC/FA + P2 + IPC-SCAN-1 全部完成 ✅

---

## 問題根因（診斷結論，無需重查）

### Bug 1：SYMBOLS 是編譯期常量
```rust
// event_consumer/types.rs（修復前）
pub const SYMBOLS: &[&str] = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];
```
開發時隨手填入，無動態替換機制。Agent 掃描到的機會 Rust engine 完全看不到。

### Bug 2：Python Scanner 與 Rust Engine 斷開
Python `market_scanner.py` 每 5 分鐘掃描一次，但結果不傳入 Rust engine。
修復決策：Rust engine 內建完整 scanner，Python scanner 降級為 dead code（審計保留）。

### QC 分析指出的評分缺陷
1. 評分市場條件而非策略適配度 → 改為四策略分立評分
2. Grid / BB reversion 條件重疊，grid 永遠勝出 → 互斥條件重新設計
3. $5M 量能門檻太低（亞洲非高峰期滑點 30 bps > fee 預算）→ 提升至 $50M
4. Scanner 與 edge_estimates.json 斷開 → 接入 JS shrinkage 估計值

---

## 已完成工作

### Phase A — 基礎文件

| 任務 | 文件 | 說明 |
|------|------|------|
| A1 | `openclaw_core/src/klines.rs:513,527` | KlineManager::add_symbol / remove_symbol 運行時增刪 |
| A2/A3 | `market_data_client/types.rs` | TickerInfo 新增 price_change_24h_pct、bid1_price、ask1_price + parse |
| A4 | `src/scanner/sectors.rs` | STABLECOIN_BASES 常量 + symbol_sector() 靜態映射（9 板塊）|
| A5 | `src/scanner/types.rs` | ScoredSymbol / ScanResult / ChurnState 結構體，雙語注釋 |
| A6 | `src/scanner/config.rs` | ScannerConfig + 五個子結構體 + validate()，跟隨 BudgetConfig 模式 |
| A7 | `src/scanner/mod.rs` | Module root，re-export 所有 public API |
| A8 | `src/config/mod.rs` | 新增 pub use scanner_config::ScannerConfig |

### Phase B — 核心邏輯（全 pure function，無 async，無 I/O）

| 任務 | 文件 | 說明 |
|------|------|------|
| B1 | `src/scanner/scorer.rs` | apply_hard_filters / compute_market_conditions / f_ma / f_grid / f_bbrv / f_bkout / apply_edge_bonus / beta_proxy / apply_correlation_filter，26 個單測 |
| B2 | `src/scanner/registry.rs` | SymbolRegistry：snapshot() / apply_scan_result() / 反 churn 邏輯（min_hold_cycles / challenger_threshold / removal_cooldown）/ 持倉延遲移除，8 個單測 |

### Phase C — 異步基礎設施

| 任務 | 文件 | 說明 |
|------|------|------|
| C1 | `src/ws_client.rs` | WsTopicChange enum + topic_change_rx channel + subscribe/unsubscribe 批次邏輯（≤10/op，500ms 間隔）+ 重連時重播訂閱 |
| C2 | `src/scanner/runner.rs` | ScannerRunner async task：60s warmup → 30min 週期掃描 → 評分 → apply_scan_result → WsTopicChange 發送 |
| C3 | `src/tick_pipeline.rs` | add_symbol / remove_symbol（注：has_open_position 改為 runner 通過 PaperSessionCommand::GetOpenPositionSymbols 異步查詢，架構等效）|

### Phase D — 接線

| 任務 | 文件 | 說明 |
|------|------|------|
| D1 | `src/event_consumer/types.rs` | EventConsumerDeps 新增 symbol_registry / scanner_store 字段 |
| D2 | `src/event_consumer/mod.rs` | GetOpenPositionSymbols variant + bootstrap_rx 監聽 + 動態 symbol 初始化（替換 SYMBOLS 常量）|
| D3 | `src/ipc_server.rs:1658,1687` | get_active_symbols / get_scanner_status endpoints，7 個測試 |
| D4 | `src/main.rs` | init_scanner()：ScannerConfig 加載 → SymbolRegistry 構建 → WsTopicChange channel 中繼 → ScannerRunner spawn → registry 寫入 EventConsumerDeps |

### Phase E — Python Scanner 棄用（2026-04-10 補全）

| 任務 | 文件 | 說明 |
|------|------|------|
| E1 | — | 確認 Rust 代碼不調用 Python scanner（grep 驗證） |
| E2 | `program_code/local_model_tools/market_scanner.py:1` | 頂部加 DEPRECATED MODULE_NOTE |
| E3 | `program_code/local_model_tools/strategy_auto_deployer.py:on_scan_results()` | 函數入口加 `return`，附雙語棄用注釋 |

---

## QC/FA 修正（優化項）

| 修正 | 位置 | 變更 |
|------|------|------|
| M-1 | runner.rs | 移除 pending_close 邏輯，改為直接查 open positions |
| M-2 | scanner_config.toml | TOML 配置完整覆蓋所有 ScannerConfig 字段 |
| M-3 | scorer.rs:118 | f_ma 方向移動閾值 1.5% → 0.5%（更多幣種能進入 MA 評分）|
| M-5 | scorer.rs:240 | edge_bonus 探索加分 +5 → +2（避免過度偏向未探索幣）|
| IPC-SCAN-1 | ipc_server.rs | get_active_symbols / get_scanner_status 可觀測性端點上線 |

---

## 評分框架設計（最終版）

### 硬過濾（任一失敗直接淘汰）
- turnover24h ≥ $50M（從 $5M 提升，防滑點）
- price ≥ 0.001 USDT
- spread_bps ≤ 8（(ask1-bid1)/mid × 10000）
- symbol 必須以 USDT 結尾
- base 不在 STABLECOIN_BASES 列表

### 策略分立評分（0-100，純函數）
基礎變量：range_pct / dir_pct / DE（方向效率）/ FR_bps（funding rate abs）

- **F_ma**：dir_pct ≥ 0.5%，DE 高 + 移動大 = 趨勢純淨；FR 高懲罰（持倉擁擠）
- **F_grid**：range_pct ≥ 3% AND dir_pct < 8%；需要大 range + 低 drift；(1-DE) 越高越好
- **F_bbrv**：4% ≤ range_pct ≤ 20%；(1-DE) × range；極端 FR + 低 dir 有加成
- **F_bkout**：3% ≤ range_pct ≤ 20% AND dir_pct > 2%；DE 高 + 方向大；過度 FR 懲罰

### Edge 反饋加成
raw_score = max(F_ma, F_grid, F_bbrv, F_bkout)  
edge_bonus = shrunk_bps × 0.5，clamped [-30, +2]；未探索 symbol → +2

### 相關性分散過濾
- 最多 8 個 beta_proxy > 0.8（BTC 高相關）
- 每個策略最多 8 個 symbol
- 每個板塊最多 4 個 symbol
- BTC/ETH 永遠 pinned，不參與競爭

---

## 測試覆蓋

| 模塊 | 測試數 |
|------|--------|
| scanner/scorer.rs | 26 |
| scanner/registry.rs | 8 |
| scanner/config.rs | ~5 |
| ipc_server.rs（scanner 端點）| 7 |
| 其他新增 | ~20 |
| **總計新增** | **+66** |
| **最終 lib tests** | **835** |

---

## 架構決策記錄

| 決策 | 選擇 | 原因 |
|------|------|------|
| Scanner 位置 | Rust engine 內部 background tokio task | 消除 Python-Rust 資訊斷層 |
| BTC/ETH | 永遠 pinned | 流動性保證，不受評分影響 |
| Max symbols | 25（linear perp）| 風控分散上限 |
| 掃描間隔 | 30 分鐘（啟動後 60s 第一次）| 平衡資訊新鮮度與 API 配額 |
| Python scanner | Dead code（不刪，審計保留）| 原則 #8 交易可解釋性 |
| hand-roll C+D（自建 realized edge tracker）| 否決 | 與 Phase 5 JS-1 重疊 ~70% |
| has_open_position | 改為 PaperSessionCommand 異步查詢 | 避免 Registry 直接依賴 PaperState |
| EdgeEstimates | Arc<RwLock<>> 共享 | IntentProcessor + ScannerRunner 各 clone Arc |

---

## 關鍵警告（未來維護注意）

1. **新 symbol 暖機**：WS subscribe 先送 → REST bootstrap 後做 → bootstrap 完成前 H0Gate freshness 自動屏蔽 intent
2. **移除前必須 drain 持倉**：has open position → defer removal，不啟動 cooldown
3. **WS 訂閱非原子性**：Subscribe 必須同時 mutate subscriptions Vec（重連重播保障）
4. **tickers 數據無法偵測 BB squeeze**：F_bkout 是最弱評分，後續可補 kline BB bandwidth 計算

---

## 關聯文件

- 原始規格：`SCANNER_TODO.md`（本 session 工作單，已歸檔）
- TOML 配置：`settings/risk_control_rules/scanner_config.toml`
- Edge 估計：`settings/edge_estimates.json`
- IPC 端點文檔：`docs/references/2026-04-04--bybit_api_reference.md`
- Changelog：`docs/CLAUDE_CHANGELOG.md`（各 commit 摘要）

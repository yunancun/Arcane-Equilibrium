# SCANNER_TODO — Rust Market Scanner + Dynamic Symbol Management
# Rust 市場掃描器 + 動態交易對管理

**建立日期：** 2026-04-09  
**背景 Session：** Phase 5 探索期，在觀察 paper 交易模式時發現兩個架構錯誤  
**預估工作量：** ~750 行新 Rust 代碼，~200 行改造，需要完整 E1→E2→E4 鏈

---

## 問題說明（不要重複研究）

### 錯誤 1：SYMBOLS 是編譯期常量
```rust
// event_consumer/types.rs:16
pub const SYMBOLS: &[&str] = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];
```
SOLUSDT / XRPUSDT / DOGEUSDT 是開發時隨手填的，不是 agent 選的。沒有任何機制動態更換。

### 錯誤 2：Python Scanner 與 Rust Engine 完全斷開
Python `market_scanner.py` 每 5 分鐘掃描一次，但結果不會傳入 Rust engine。Scanner 選到的機會 engine 根本看不到。

### 現有評分的致命缺陷（QC 分析結論）
1. **評分市場條件，不是策略適配度** — 四個策略（ma/grid/bbrv/bkout）需求完全不同，單一評分無法服務所有策略
2. **評分標準自相矛盾** — grid 條件和 bb_reversion 條件重疊，grid 永遠勝出，reversion 永遠得不到 slot
3. **Scanner 和學習系統斷開** — `edge_estimates.json` 裡的 JS 估計值 Scanner 從不讀取
4. **$5M 量能門檻太低** — $5M 日成交量的幣，亞洲非高峰期可能每小時 $100k，一筆單滑點 30 bps > fee 預算
5. **proposed `vol×0.4 + FR×0.3 + change×0.3` 更差** — 三個指標高度共線，實際在選「高 beta 拉盤幣」

### Scanner 不修正 edge 危機的警告
QC 明確指出：**Scanner 改進是二階效應**。主要槓桿是：策略參數調優、用限價單、延長持倉時間。不要期望 Scanner 單獨翻轉 edge。

---

## 架構決策（已定，不需要重新討論）

| 決策 | 選擇 |
|---|---|
| Scanner 位置 | Rust engine 內部，background tokio task |
| BTC/ETH | 永遠 pinned，不參與評分競爭 |
| 其他 symbol | 全由 Rust scanner 動態選擇 |
| Max symbols | 25（linear perp）|
| 掃描間隔 | 30 分鐘（啟動後 60s 第一次）|
| Python scanner | 保留但降級為 dead code（不刪，審計保留）|
| Python deployer | 禁用（DEAD-PY 延續），不再管理 Rust symbols |

---

## 評分框架（最終版，直接實作）

### 第一層：硬過濾（任一失敗直接淘汰）

```
FILTER_1: turnover24h >= 50_000_000 USDT          (從 $5M 提升到 $50M)
FILTER_2: price >= 0.001 USDT
FILTER_3: spread_bps = (ask1-bid1)/mid * 10000 <= 8  (新增，bid1/ask1 已在 tickers API)
FILTER_4: symbol 必須以 "USDT" 結尾
FILTER_5: base 不在 STABLECOIN_BASES 列表中（USDC/BUSD/TUSD/FDUSD 等）
```

### 第二層：策略分立適配評分（0-100，純函數）

**基礎變量**（從 Bybit tickers API 計算）：
```
range_pct = (high24h - low24h) / price * 100        # 24h 總路徑，%
dir_pct   = abs(price_change_24h_pct)                # 淨方向移動，%（來自 price24hPcnt）
DE        = dir_pct / range_pct                      # 方向效率 ∈ [0,1]，趨勢純度
FR_bps    = abs(fundingRate * 10000)                 # Funding rate 絕對值，bps
```

**F_ma（ma_crossover 適配分）**
```
條件：dir_pct >= 1.5%，否則 F_ma = 0
base  = min(100.0, 100.0 * DE * (dir_pct / 10.0).clamp(0.0, 1.0))
crowd = min(30.0, max(0.0, (FR_bps - 10.0) * 2.0))  // 高 funding 懲罰（持倉擁擠）
F_ma  = max(0.0, base - crowd)
```
*邏輯：方向效率高 + 移動大 = 趨勢純淨。Funding rate 高代表持倉擁擠，趨勢可能耗盡。*

**F_grid（grid_trading 適配分）**
```
條件：range_pct >= 3.0 AND dir_pct < 8.0，否則 F_grid = 0
usable_range = range_pct.min(15.0)
dir_mult = if dir_pct >= 3.0 { 0.5 } else { 1.0 }   // 方向漂移懲罰
F_grid = (usable_range / 15.0) * 100.0 * (1.0 - DE) * dir_mult
如果 turnover24h >= 100_000_000：F_grid = (F_grid * 1.15).min(100.0)  // 高流動性加成
```
*邏輯：需要大 range（有足夠波動收割）但低 drift（不趨勢）。均值回歸傾向 = 1-DE 越高越好。*

**F_bbrv（bb_reversion 適配分）**
```
條件：4.0 <= range_pct <= 20.0，否則 F_bbrv = 0
F_bbrv = (1.0 - DE) * (range_pct * 8.0).min(100.0)
// 加成：極端持倉 + 低價格移動 → 潛在 snap-back
if FR_bps > 15.0 AND dir_pct < 3.0：
    F_bbrv = (F_bbrv * 1.2).min(100.0)
```
*邏輯：(1-DE) 表示日內已發生多次反轉（range 大但 net move 小）。BB reversion 需要這個。*

**F_bkout（bb_breakout 適配分）**
```
條件：3.0 <= range_pct <= 20.0 AND dir_pct > 2.0，否則 F_bkout = 0
F_bkout = DE * 100.0 * (dir_pct / 8.0).clamp(0.0, 1.0)
if FR_bps > 20.0：F_bkout = max(0.0, F_bkout - 25.0)  // 過度擁擠懲罰
```
*警告：tickers 數據無法可靠偵測 BB squeeze。這是最弱的評分，純靠「directional + 有 range」代理。*
*改進路徑：後續可對 top-50 pre-filtered symbol 拉 `/v5/market/kline?interval=60&limit=100` 計算真實 BB bandwidth。*

### 第三層：Edge 反饋加成

```
raw_score      = max(F_ma, F_grid, F_bbrv, F_bkout)
best_strategy  = argmax(F_ma, F_grid, F_bbrv, F_bkout)

// 查 edge_estimates.json（JS 估計值）
if (best_strategy, symbol) in edge_estimates AND n >= 10:
    edge_bonus = (shrunk_bps * 0.5).clamp(-30.0, 10.0)
    // 例：DOGEUSDT bb_reversion shrunk=-24.7 → bonus=-12.35
else:
    edge_bonus = 5.0   // 未探索的 symbol 給探索加分

final_score = (raw_score + edge_bonus).clamp(0.0, 100.0)
```

*重要：edge_bonus 不是 veto（當前所有估計都是負的）。它只是重新排序：優先探索 edge 估計未知的幣，對已知持續負估計的幣施加懲罰。*

### 第四層：相關性分散過濾

**BTC beta 代理**（從 tickers 計算）：
```
beta_proxy = symbol_change_24h / btc_change_24h  （分母為 0 時 → None）
clamp to [-0.5, 3.0]
```

**分散規則**（按 final_score 降序排序後，貪心選擇）：
- 最多 8 個 symbol 的 beta_proxy > 0.8（BTC 高相關）
- 每個策略品類最多 8 個 symbol（ma / grid / bbrv / bkout）
- 每個市場板塊最多 4 個 symbol（見 sectors.rs 靜態映射）

---

## 實作工作單元

### Phase A：基礎（無運行時耦合，可並行開發）

- [ ] **A1** `openclaw_core`: `KlineManager::add_symbol(&mut self, symbol: &str)` + `remove_symbol`
  - KlineManager 現在是啟動時固定分配。需要支持運行時增刪。
  - 這是 TickPipeline::add_symbol 的依賴前置。
  
- [ ] **A2** `market_data_client/types.rs`: 在 `TickerInfo` 加 `price_change_24h_pct: f64`
  - Bybit 字段：`price24hPcnt`（字符串，需 parse_str_f64）
  - 也要確認 `bid1_price` / `ask1_price` 是否已在結構體（spread 計算用）
  - 查看當前字段：`grep -n "TickerInfo\|bid1\|ask1\|prev_price" src/market_data_client/types.rs`

- [ ] **A3** `market_data_client/parsers.rs`: parse `price24hPcnt` → `price_change_24h_pct`

- [ ] **A4** `src/scanner/sectors.rs`（新文件）：
  - `const STABLECOIN_BASES: &[&str]`（USDC/BUSD/TUSD/FDUSD/USDE 等）
  - `fn symbol_sector(base: &str) -> &'static str`（靜態 match，按需更新）
  - 板塊：l1_infra / meme / oracle / defi_dex / defi_lending / gaming_nft / storage / payments_l1 / l2_scaling / other

- [ ] **A5** `src/scanner/types.rs`（新文件）：
  ```rust
  pub struct ScoredSymbol { symbol, final_score, raw_score, best_strategy,
      f_ma, f_grid, f_bbrv, f_bkout, dir_pct, range_pct, de, fr_bps,
      turnover_24h, beta_proxy: Option<f64>, edge_bonus, edge_n: u32 }
  pub struct ScanResult { scan_ts_ms, active_symbols, added, removed, candidates, rejected_count, scan_duration_ms }
  pub struct ChurnState { cycles_held: u32, removal_cooldown_until_ms: u64 }
  ```

- [ ] **A6** `src/scanner/config.rs`（新文件）：`ScannerConfig` + 子結構體 + validate() + Default
  - 子結構體：`SchedulingConfig / UniverseConfig / HardFilters / AntiChurnConfig / ScoringWeights`
  - TOML 路徑：`settings/risk_control_rules/scanner_config.toml`（或 env `OPENCLAW_SCANNER_CONFIG`）
  - 跟隨 `budget_config.rs` 的 Meta + validate + Serialize/Deserialize 模式

- [ ] **A7** `src/scanner/mod.rs`（新文件）：module root，re-export 所有 public API

- [ ] **A8** `src/config/mod.rs`：新增 `pub mod scanner_config; pub use scanner_config::ScannerConfig;`

### Phase B：核心邏輯（純函數，可完整單測）

- [ ] **B1** `src/scanner/scorer.rs`（新文件，核心）：
  - `fn apply_hard_filters(ticker: &TickerInfo, config: &HardFilters) -> Option<()>`
  - `fn compute_fitness(ticker: &TickerInfo) -> FitnessScores`（返回 F_ma/grid/bbrv/bkout + 中間值）
  - `fn apply_edge_bonus(raw, best_strategy, symbol, estimates) -> (f64, f64, u32)`
  - `fn beta_proxy(sym_chg, btc_chg) -> Option<f64>`
  - `fn apply_correlation_filter(candidates: Vec<ScoredSymbol>, btc_chg, weights) -> Vec<ScoredSymbol>`
  - 全部 pure function，無 async，無 I/O

- [ ] **B2** `src/scanner/registry.rs`（新文件）：`SymbolRegistry`
  - 字段：`symbols: Arc<RwLock<Vec<String>>>` / `churn_state: Arc<RwLock<HashMap<String, ChurnState>>>` / `ws_change_tx` / `bootstrap_tx` / `config` / `last_scan`
  - `fn snapshot(&self) -> Vec<String>`
  - `fn apply_scan_result(&self, candidates, now_ms, config, open_positions: &HashSet<String>) -> (Vec<String>, Vec<String>)`
    - open_positions：由 caller 從 pipeline 查出後傳入（避免 Registry 直接依賴 PaperState）
    - 反 churn 邏輯：min_hold_cycles / challenger_threshold / removal_cooldown
    - pinned symbols 永遠不被 apply_scan_result 移除
  - `fn last_scan(&self) -> Option<ScanResult>`

### Phase C：異步基礎設施

- [ ] **C1** `src/ws_client.rs`：添加 `WsTopicChange` channel
  - 新增 enum：`WsTopicChange { Subscribe(Vec<String>), Unsubscribe(Vec<String>) }`
  - WsClient 添加 `topic_change_rx: Option<UnboundedReceiver<WsTopicChange>>`
  - 在 run loop 的 `select!` 加新 arm：收到 Subscribe → 發 Bybit subscribe op AND append to self.subscriptions（重連時重播）
  - 批次限制：每次 subscribe op 最多 10 個 topic（Bybit V5 限制），500ms 間隔
  - **注意**：`Subscribe` 必須同時 mutate `self.subscriptions`，才能確保重連後重播

- [ ] **C2** `src/scanner/runner.rs`（新文件）：`ScannerRunner` async task
  - 字段：`registry / market_client / edge_estimates: Arc<RwLock<EdgeEstimates>> / config_store / cancel`
  - `pub async fn run(self)`：
    1. sleep warmup_delay_secs（默認 60s）
    2. Loop：
       a. `market_client.get_tickers("linear", None).await` → 拿全部 tickers
       b. 找 BTCUSDT ticker 作 beta_proxy 分母
       c. 對每個 ticker：hard filter → compute_fitness → apply_edge_bonus → build ScoredSymbol
       d. sort by final_score desc → apply_correlation_filter → take top (max_symbols - pinned.len())
       e. 查詢 open positions：發 oneshot 到 event_consumer loop
       f. `registry.apply_scan_result(...)` → 得到 (added, removed)
       g. 對 added：發 WsTopicChange::Subscribe + bootstrap channel 通知
       h. 對 removed：發 WsTopicChange::Unsubscribe（pipeline 已 drain）
       i. 記錄 ScanResult，log 結構化摘要
       j. sleep scan_interval_secs

- [ ] **C3** `src/tick_pipeline.rs`：新增方法
  - `pub fn add_symbol(&mut self, symbol: &str)` — 調用 kline_manager.add_symbol，其他 HashMap 自動擴展
  - `pub fn remove_symbol(&mut self, symbol: &str)` — drain klines / latest_prices / indicators / consecutive_losses
  - `pub fn has_open_position(&self, symbol: &str) -> bool` — 查 paper_state
  - **依賴 A1（KlineManager 必須先支持 add/remove）**

### Phase D：接線

- [ ] **D1** `src/event_consumer/types.rs`：`EventConsumerDeps` 添加：
  ```rust
  pub symbol_registry: Option<Arc<crate::scanner::registry::SymbolRegistry>>,
  pub scanner_store: Option<Arc<ConfigStore<ScannerConfig>>>,
  ```

- [ ] **D2** `src/event_consumer/mod.rs`：
  - `PaperSessionCommand` 添加新 variant：
    ```rust
    GetOpenPositionSymbols { response_tx: oneshot::Sender<HashSet<String>> }
    ```
  - main loop 中處理此 command：收集所有 has_open_position 的 symbol 集合，發回
  - 初始化：使用 registry.snapshot() 替代 SYMBOLS 常量  
  - kline bootstrap loop：改為迭代 registry 而非 SYMBOLS
  - 添加 bootstrap_rx 監聽：收到新 symbol → 觸發 REST kline bootstrap task

- [ ] **D3** `src/ipc_server.rs`：添加 IPC endpoints
  - `"get_active_symbols"` → handler 返回 `registry.snapshot()` JSON array
  - `"get_scanner_status"` → handler 返回 `registry.last_scan()` JSON
  - 在 dispatch_request match 中添加這兩個 arm（跟隨現有 pattern）

- [ ] **D4** `src/main.rs`：
  - 新增 `init_scanner()` async fn：load ScannerConfig → build SymbolRegistry → spawn ScannerRunner task
  - 替換所有 `SYMBOLS` call sites（共 8 處）為 `symbol_registry.snapshot()`
  - 替換 `TickPipeline::with_balance(SYMBOLS, ...)` 為使用 registry 初始快照
  - 將 `ws_topic_change_tx` 傳給 WsClient 構造
  - 將 registry 寫入 `EventConsumerDeps`

### Phase E：棄用 Python Scanner

- [ ] **E1** 確認 Python `market_scanner.py` 不再被任何 live Rust 代碼路徑調用（`grep` 驗證）

- [ ] **E2** `program_code/local_model_tools/market_scanner.py`：頂部添加棄用 MODULE_NOTE：
  ```python
  # DEPRECATED 2026-04-09: Superseded by Rust MarketScanner (src/scanner/).
  # Kept for audit trail. Do not call from live trading paths.
  ```

- [ ] **E3** `program_code/local_model_tools/strategy_auto_deployer.py`：禁用或轉換為 IPC read-only
  - 短期：在 `on_scan_result` callback 中直接 return，不做任何 symbol 操作
  - 長期：DEAD-PY-1 清理工作的一部分

---

## 關鍵風險與注意事項

### 風險 1：新 symbol 的指標暖機
新 symbol 加入後，KlineManager 歷史為零。必須先完成 REST kline bootstrap（GET 200 根 K 線）才能讓指標可靠。流程：
1. WS subscribe 先送（確保不丟 tick）
2. 然後 REST bootstrap（防止 bootstrap 數據比第一個 live tick 舊）
3. Bootstrap 完成前：H0Gate freshness check 自動屏蔽該 symbol 的 intent（已有機制）
4. Bootstrap 失敗：指數退避重試 3 次，失敗後記 warn，symbol 進入「暖機失敗」狀態

### 風險 2：移除前必須 drain 持倉
`apply_scan_result` 收到需移除的 symbol 後，必須先查詢是否有持倉：
- **有持倉**：defer removal，`cycles_held` 繼續增，不啟動 cooldown timer
- **無持倉**：立即 pipeline.remove_symbol → 發 WsTopicChange::Unsubscribe
- 查詢機制：ScannerRunner 通過 `PaperSessionCommand::GetOpenPositionSymbols { response_tx }` 向 event_consumer loop 請求，await oneshot reply

### 風險 3：WS 訂閱非原子性
Bybit WS subscribe op 是 best-effort。解決：
- Subscribe 必須同時 mutate `WsClient::subscriptions` Vec（重連時全部重播）
- 斷線重連：按 SUBSCRIBE_BATCH_SIZE=10 分批送，500ms 間隔
- 已有訂閱的 symbol 收到 WS tick 但 pipeline 已刪除 → HashMap lookup 返回 None → tick 靜默丟棄（已有 fallback）

### 風險 4：Python Deployer 衝突
`strategy_auto_deployer.py` 可能仍在後台調用 Python MarketScanner 並嘗試「部署」symbol。這不影響 Rust engine（engine 忽略 Python deployer 的存在），但會造成 log 混淆。最快修法：在 deployer 的 scan callback 入口加 `return`。

### 風險 5：Edge Estimates 共享
ScannerRunner 需要讀 EdgeEstimates，目前由 IntentProcessor 獨佔擁有。解決方案：
- 改為 `Arc<RwLock<EdgeEstimates>>` 由 event_consumer 持有
- IntentProcessor 和 ScannerRunner 各自 clone Arc
- JS estimator 重跑後，新增 IPC `reload_edge_estimates` → 更新 RwLock 內容

### 風險 6：文件大小限制
`scorer.rs` 有四個複雜評分函數 + 相關性過濾，可能接近 700 行。若超過，拆出：
- `scorer.rs`：hard filters + 四個 fitness functions + edge bonus
- `scorer_correlation.rs`：beta_proxy + correlation filter

---

## 測試策略

### scorer.rs 單測（全部 sync，無 I/O）
```
test_hard_filter_turnover_fail
test_hard_filter_spread_fail             // (ask1-bid1)/mid*10000 > 8 被拒
test_hard_filter_stablecoin_fail         // base in STABLECOIN_BASES 被拒
test_fitness_ma_zero_if_low_dir_pct      // dir_pct < 1.5 → F_ma = 0
test_fitness_grid_zero_if_trending       // dir_pct >= 8 → F_grid = 0
test_fitness_bbrv_range_band             // range_pct < 4 OR > 20 → F_bbrv = 0
test_edge_bonus_known_cell_n_ge_10       // shrunk_bps * 0.5, clamped
test_edge_bonus_exploration_no_data      // unknown → +5.0
test_beta_proxy_btc_zero                 // btc_change = 0 → None
test_correlation_cap_high_beta           // > 8 高 beta → 截斷
test_correlation_cap_per_sector          // > 4 同板塊 → 截斷
test_de_formula_clean_trend              // dir_pct=range_pct → DE=1.0
test_de_formula_pure_chop                // dir_pct=0 → DE=0
```

### registry.rs 單測
```
test_pinned_always_present               // BTC/ETH 在 apply_scan_result 後仍存在
test_anti_churn_min_hold_cycles          // cycles_held < 2 的 symbol 不被移除
test_anti_churn_challenger_threshold     // 新 symbol 需要 +15 才能替換
test_anti_churn_cooldown_reentry         // 移除後 90min 內不能重新加入
test_max_symbols_cap                     // 永遠不超過 25
test_open_position_defers_removal        // 有持倉的 symbol 移除被 defer
```

### config.rs 單測
```
test_default_scanner_config_valid
test_toml_round_trip
test_invalid_max_symbols_zero
test_invalid_scan_interval_zero
```

### 整合測試（MockMarketDataClient）
```
test_full_scan_cycle_selects_top_n       // mock tickers → registry 更新正確
test_scan_respects_pinned_symbols        // pinned 不被替換
test_scanner_reads_edge_estimates        // edge_bonus 影響排序
```

---

## 完成標準（Definition of Done）

1. `cargo build --release` 無錯誤，無新 warning
2. `cargo test` 全部通過，測試數量 ≥ 現有 769（不能有回歸）
3. Engine 啟動後日誌顯示 `[scanner] warmup 60s` → `[scanner] first scan complete` 結構化摘要，含 `active_symbols / added / removed / rejected_count`
4. IPC `get_active_symbols` 返回 JSON array；`get_scanner_status` 返回 ScanResult JSON
5. BTC 和 ETH 永遠在 `get_active_symbols` 結果中
6. 任何時刻 `get_active_symbols` 返回數量 ≤ 25
7. 有持倉的 symbol 被標記移除時，日誌出現 `[scanner] defer_remove SOLUSDT (open position)`
8. WS 斷線重連後，訂閱集合包含運行時新增的 symbol（非 compile-time SYMBOLS）
9. `cargo clippy -- -D warnings` 對所有新文件通過
10. 所有新文件：雙語 MODULE_NOTE + 所有 pub fn 雙語 docstring
11. `grep -r "market_scanner.py" src/` 無結果（Rust 不調用 Python scanner）
12. `settings/risk_control_rules/scanner_config.toml` 可以被 engine 加載，啟動日誌確認參數

---

## 實作順序（依賴圖）

```
A4, A5, A7          ← 獨立，可第一天並行
A1 (core crate)     ← 最早做，C3 依賴它
A2, A3              ← 並行，B1 依賴它
A6, A8              ← 並行

B1 (scorer)         ← 依賴 A2, A3, A4, A5
B2 (registry)       ← 依賴 A5, A6
C1 (ws_client)      ← 獨立

C2 (runner)         ← 依賴 B1, B2, C1
C3 (pipeline)       ← 依賴 A1

D1                  ← 依賴 B2, A6
D2                  ← 依賴 D1, C2, C3
D3                  ← 依賴 B2
D4 (main.rs)        ← 依賴全部 D1-D3

E1, E2, E3          ← 最後，D4 完成後驗證
```

---

## 關鍵文件快速索引（實作前必讀）

```
types.rs 現有 symbol 定義：
  rust/openclaw_engine/src/event_consumer/types.rs:16

TickerInfo 現有字段：
  rust/openclaw_engine/src/market_data_client/types.rs

REST client 現有 get_tickers：
  rust/openclaw_engine/src/market_data_client/mod.rs
  查找 get_tickers / fetch_tickers / tickers

IPC dispatch pattern（新 endpoint 怎麼加）：
  rust/openclaw_engine/src/ipc_server.rs:480-530

BudgetConfig 模式（ScannerConfig 跟著做）：
  rust/openclaw_engine/src/config/budget_config.rs

WsClient 現有 run loop：
  rust/openclaw_engine/src/ws_client.rs

PaperSessionCommand（新增 GetOpenPositionSymbols 在這）：
  rust/openclaw_engine/src/tick_pipeline.rs:PaperSessionCommand enum

EdgeEstimates 現有結構：
  rust/openclaw_engine/src/edge_estimates.rs

現有 KlineManager 位置：
  openclaw_core/src/  (需要查 lib.rs 確認具體文件)
```

---

## 相關背景文件

- `docs/CLAUDE_CHANGELOG.md`：本 session 的具體 commit 記錄
- `settings/edge_estimates.json`：JS 估計值（scanner 要讀這個）
- `TODO.md`：Phase 5 + Phase 6 整體計劃
- `program_code/local_model_tools/market_scanner.py`：要被棄用的 Python scanner（可參考評分邏輯歷史）

---

## 本 session 實作時的工作鏈提醒

```
E1（多路並行）→ E2 代碼審查 → E4 測試回歸（強制）→ PM 確認
不可跳過 E2 + E4。策略/模型改動後需額外 QA Audit。
```

**測試基準線（開始前確認）：** Rust engine lib 769 · core 387 · types 27 · ml_training 35  
本次 scanner 模塊完成後新增測試數量預估：+40-60 個

---

*文件結束。新 session 從第一個 `[ ]` 開始。確認讀到此行後可開工。*

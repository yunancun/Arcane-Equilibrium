# E5 全程序優化評估報告

**日期**：2026-04-12
**範圍**：Rust `openclaw_engine` (54,952 行) + Python API 層 (145,883 行，排除 venv)
**代碼庫狀態**：1355 Rust tests + 2852 Python tests pass

---

## 一、性能評估 [PERF]

### P-01 [PERF] `on_tick()` 內 `event.symbol.clone()` 重複分配 — **High**

**文件**：`tick_pipeline/on_tick.rs:28,55,77,166,242,261,294,434,1205`

核心熱路徑 `on_tick()` 每 tick 對 `event.symbol` 做 9 次 `.clone()`。在 25 個 symbol、每秒數百 tick 的生產環境中，每 tick 多出 9 次堆分配。`event.symbol` 是 `String`，平均 ~12 字節（"BTCUSDT"~7, "ETHUSDT"~7），每次 clone 觸發 `malloc`。

**建議**：在 `on_tick()` 開頭做一次 `let sym = &event.symbol;`，後續所有 `.insert()` / 構造消息處統一使用 `sym.clone()`（需要所有權的地方）或 `sym`（借用的地方）。對於 HashMap key，考慮使用 `Arc<str>` 或在 PriceEvent 內部使用 `Rc<str>`/`Arc<str>` 替代 `String`，但這影響面大，建議先做 local alias 優化。

**影響估計**：每 tick 減少 ~5-6 次 String clone（保留真正需要所有權的 insert 處）。在 100 tick/s 時約 500 次/s 堆分配消除。

---

### P-02 [PERF] `metadata: HashMap<String, String>` 每 PriceEvent 分配 — **High**

**文件**：`openclaw_types/src/price.rs:24`, `ws_client.rs:460-468`

`PriceEvent` 結構體包含 `metadata: HashMap<String, String>`，WS 解析器每條消息都創建新 HashMap 並 insert 2-3 個 key/value（"type", "side", "qty"）。在高頻 publicTrade 流下（每秒可達數百條），這是大量短命堆分配。

**建議**：
- 方案 A：將 `type`/`side`/`qty` 提升為 PriceEvent 的結構化字段（枚舉 `EventType { Trade, Kline, Ticker, Orderbook, ... }` + `Option<TradeSide>` + `Option<f64> trade_qty`），完全消除 HashMap。
- 方案 B：使用 `SmallVec<[(String,String); 4]>` 替代 HashMap（避免哈希表開銷，4 元素以下棧分配）。
- 方案 C（最小改動）：在 `on_tick()` 入口處用 `metadata.get("type")` 結果做一次 pattern match，將 `bids5`/`asks5` 的 `serde_json::from_str` 提取（on_tick.rs:124,129）改為預解析結構化字段。

**影響估計**：每 tick 省下 1 HashMap + 2-3 String 分配 = 約 4-6 次堆分配。方案 A 可以同時消除 on_tick.rs:73 和 on_tick.rs:94 處的 `metadata.get()` 字符串比較開銷。

---

### P-03 [PERF] `serde_json::from_str` 在 orderbook 熱路徑解析 bids/asks — **Medium**

**文件**：`tick_pipeline/on_tick.rs:122-130`

每個 orderbook tick 都對 metadata 中序列化的 bids5/asks5 做兩次 `serde_json::from_str::<Vec<(f64,f64)>>`。orderbook 更新頻率可達每秒數十次 x 25 symbols。

**建議**：如果實施 P-02 方案 A，可以在 WS 解析層直接存 `Vec<(f64,f64)>` 到結構化字段，避免先序列化到 String 再反序列化回來的雙重開銷。短期可跳過，因 orderbook tick 只有在 `market_data_tx` 存在時才進入此路徑。

---

### P-04 [PERF] `risk_config().clone()` 每 tick 深拷貝完整 RiskConfig — **Medium**

**文件**：`tick_pipeline/on_tick.rs:998`

```rust
let risk_config = self.intent_processor.risk_config().clone();
```
`RiskConfig` 含 ~15 個子結構 + 多個 `HashMap<String, ...>` + `Vec<String>`。每 tick 做一次完整深拷貝供 `evaluate_positions()` 使用。

**建議**：`evaluate_positions()` 只讀取 `risk_config` 的少數字段（limits.*、cascade.*）。改為傳 `&RiskConfig` 引用而非 owned clone。`evaluate_positions` 簽名從 `risk_config: &RiskConfig` 已經是引用了（確認），但調用端仍 clone 出 owned 值再取引用 — 直接用 `self.intent_processor.risk_config()` 返回的引用即可。

**影響估計**：每 tick 省 1 次深拷貝（含多個 HashMap clone），在 100 tick/s 時顯著。

---

### P-05 [PERF] `seen_exec_ids` 使用 VecDeque + 線性搜索去重 — **Medium**

**文件**：`event_consumer/mod.rs:580`

```rust
if seen_exec_ids.iter().any(|id| id == &exec.exec_id) {
```
使用 `VecDeque<String>` 存最多 500 個 exec_id，每次 fill 到來做 O(500) 線性掃描。在高頻成交場景下（例如 grid 策略爆發），每秒可能數十次 fill。

**建議**：改用 `HashSet<String>` + `VecDeque<String>`（HashSet 做 O(1) 查重，VecDeque 維護 FIFO 淘汰），或使用 `IndexSet`。可保持 500 上限的 FIFO 語義。

---

### P-06 [PERF] `subscriptions.contains()` 在 WS 主題管理中是 O(n) — **Low**

**文件**：`ws_client.rs:236`

```rust
if !self.subscriptions.contains(t) {
```
`subscriptions` 是 `Vec<String>`，ScannerRunner 動態添加 topic 時線性搜索整個列表。目前 ~75 topic（25 symbols x 3 streams），尚不構成瓶頸，但隨 symbol 數量擴展會惡化。

**建議**：改用 `HashSet<String>` 維護去重集，`Vec<String>` 僅用於 subscribe 批次發送。或直接用 `IndexSet` 兼顧去重和有序。

---

### P-07 [PERF] `WsClient::process_message` 每條消息全量 JSON 解析 — **Low**

**文件**：`ws_client.rs:342`

每條 WS 消息先解析為 `serde_json::Value`（動態類型），再按 topic 路由手動提取字段。Bybit 公共 WS 可達每秒數百條消息。

**建議**：對高頻消息（publicTrade、tickers），使用帶 `#[serde(rename)]` 的結構體直接 `serde_json::from_str::<BybitTradeMsg>` 反序列化，避免 `Value` 中間層。低頻消息（adl-notice、price-limit、liquidation）保留動態解析即可。

**影響估計**：中等。`serde_json::Value` 做大量小堆分配（每個字段一個 `Value` 節點），結構化反序列化直接寫入棧/堆字段，分配次數可減少 50-70%。但 WS 解析在獨立異步任務中，非 tick 管線瓶頸。

---

### P-08 [PERF] TickContext 構造時 clone indicators + signals — **Medium**

**文件**：`tick_pipeline/on_tick.rs:434-438`

```rust
let ctx = TickContext {
    symbol: event.symbol.clone(),
    indicators: indicators.clone(),
    signals: signals.clone(),
    ...
};
```
`IndicatorSnapshot` 含 ~10 個 Option 包裝的指標結構，`signals` 是 `Vec<Signal>`。每 tick clone 一次傳給策略。

**建議**：`TickContext` 改為持有借用 `&'a IndicatorSnapshot` / `&'a [Signal]`，生命週期綁定到 `on_tick` 作用域。需要修改 Strategy trait 的 `on_tick(&mut self, ctx: &TickContext<'_>)` 簽名。改動面中等但收益顯著。

---

### P-09 [PERF] `intent.clone()` 在 on_tick 的 Open/Close 分支中多次出現 — **Low-Medium**

**文件**：`tick_pipeline/on_tick.rs:582,626,672,822,838`

在 exchange/paper 兩條路徑中，`intent.clone()` 用於構造 `display_intent` 和推入 `recent_intents`。每次 clone 包含 5-6 個 String 字段。大多數 tick 不產生 intent，所以僅在開倉/平倉 tick 觸發，影響有限。

**建議**：`TimestampedIntent` 可以直接持有必要字段的引用或精簡 subset，而非完整 clone。或把 display_intent 構造統一為一個 helper 減少代碼重複（見 S-01）。

---

### P-10 [PERF] DB 寫入器 7 個獨立 buffer 序列 flush — **Low**

**文件**：`database/trading_writer.rs:87-117`

`flush_all()` 函數序列化地依次 flush 7 個 buffer（signals → intents → fills → positions → verdicts → orders → state_changes）。每個 flush 是獨立的 DB 查詢。

**建議**：考慮用 `tokio::join!` 並行 flush 獨立表（它們寫不同表，無依賴）。但需注意 PG 連接池大小限制（單連接不能並發查詢）。如果連接池 ≥ 3，可以至少 3 路並行。風險低。

---

## 二、精簡評估 [SIMPLIFY]

### S-01 [SIMPLIFY] `on_tick()` Exchange vs Paper 路徑大量重複代碼 — **High**

**文件**：`tick_pipeline/on_tick.rs:505-838`（Open 分支），`862-967`（Close 分支）

Exchange mode 和 Paper mode 的 Open 處理邏輯有 ~70% 重複：
- Guardian verdict 持久化（on_tick.rs:518-531 vs 653-666）— 完全相同
- Intent 持久化（on_tick.rs:538-556 vs 689-707）— 完全相同
- display_intent 構造 + recent_intents push（on_tick.rs:582-592 vs 672-686）— 完全相同
- rejection display_intent（on_tick.rs:626-639 vs 822-836）— 完全相同

Close 分支也有 exchange vs paper 重複（on_tick.rs:874-908 vs 910-967）。

**建議**：提取共享邏輯為 helper 方法：
- `persist_verdict(&self, intent, event, verdict_info)`
- `persist_intent(&self, intent, event, approved_qty)`
- `push_recent_intent(&mut self, ts_ms, intent, result_str)`
- `handle_rejection(&mut self, strategy, intent, reason, verdict_info)`

這將把 on_tick.rs 從 1228 行（超 1200 硬上限）降至 ~800-900 行。

---

### S-02 [SIMPLIFY] `recent_intents.len() > 50 { pop_front() }` 重複 9 次 — **Medium**

**文件**：`tick_pipeline/on_tick.rs:589,639,685,835,882,897,906,954,963`

環形緩衝的 push + cap 邏輯重複 9 次（`recent_intents`），另有 `recent_fills` 重複 3 次。

**建議**：封裝為 `fn push_capped<T>(deque: &mut VecDeque<T>, item: T, cap: usize)` 工具函數。或自定義 `RingBuffer<T>` 包裝 VecDeque。

---

### S-03 [SIMPLIFY] `format!("ctx-{}-{}-{}", em, symbol, ts_ms)` 重複構造 ~12 次 — **Medium**

**文件**：`tick_pipeline/on_tick.rs` + `tick_pipeline/commands.rs`

`format!("ctx-{em}-{symbol}-{ts_ms}")`、`format!("intent-{em}-{symbol}-{ts_ms}")`、`format!("vrd-{em}-{symbol}-{ts_ms}")` 等 ID 構造模式反覆出現。

**建議**：提取為 `fn make_context_id(em: &str, symbol: &str, ts_ms: u64) -> String` 等 3 個 ID 工廠函數。減少拼寫錯誤風險，統一 ID 格式。

---

### S-04 [SIMPLIFY] `SystemTime::now().duration_since(UNIX_EPOCH)` 重複 pattern — **Low**

**文件**：多處（event_consumer/mod.rs:91,135,695,728; tick_pipeline/commands.rs:89; dispatch.rs:91-94）

每次取 epoch millis 都寫完整 3 行模式：
```rust
let now_ms = std::time::SystemTime::now()
    .duration_since(std::time::UNIX_EPOCH)
    .map(|d| d.as_millis() as u64)
    .unwrap_or(0);
```

**建議**：提取到 `crate::util::now_ms() -> u64` 全局工具函數（ws_client.rs:425 已有 `fn now_ms()`，但是模塊私有的）。提升為 crate 級公開函數。

---

### S-05 [SIMPLIFY] `flush_signals/intents/fills/...` 7 個近乎相同的函數 — **Low-Medium**

**文件**：`database/trading_writer.rs:131-645`（估計）

7 個 `flush_*` 函數結構完全一致：取 pool → chunk → QueryBuilder → push_values → 解構 enum variant → bind → execute → record success/failure → clear。僅表名、列名、variant 不同。

**建議**：使用宏或泛型 trait 統一。但代碼生成的可讀性與直接展開需權衡。當前直接展開更易 debug，建議保留但加 `// NOTE: pattern shared with flush_signals/intents/fills etc.` 交叉引用。

---

## 三、可讀性評估 [READABILITY]

### R-01 [READABILITY] 4 個文件超 1200 行硬上限 — **High (違規)**

| 文件 | 行數 | 狀態 |
|------|------|------|
| `config/risk_config.rs` | 1381 | 超限 181 行 |
| `event_consumer/mod.rs` | 1302 | 超限 102 行 |
| `claude_teacher/applier.rs` | 1257 | 超限 57 行 |
| `tick_pipeline/on_tick.rs` | 1228 | 超限 28 行 |

另有 6 個文件在 800-1200 警告區間。

**建議**：
- `risk_config.rs`：默認值函數（~100 個 `fn default_*`）提取到子模塊 `risk_config/defaults.rs`。
- `event_consumer/mod.rs`：`run_event_consumer` 函數本體 ~800 行，主事件循環的 exchange event handler（on_tick.rs:572-800）可提取為 `event_consumer/exchange_events.rs` 模塊。
- `on_tick.rs`：實施 S-01 後預計降至 ~900 行。
- `claude_teacher/applier.rs`：待確認內部結構再拆分。

---

### R-02 [READABILITY] `on_tick()` 單函數 1187 行 — **High**

**文件**：`tick_pipeline/on_tick.rs:11-1187`

這是整個系統最關鍵的函數，但單函數體 1187 行極難閱讀和維護。

**建議**：按管線階段拆分為子方法：
1. `on_tick_preprocess()` — 價格更新、turnover、ADL、聚合器（~100 行）
2. `on_tick_fast_track()` — 快速通道 + H0 gate（~50 行）
3. `on_tick_indicators()` — K 線、指標、特徵快照（~80 行）
4. `on_tick_signals()` — 信號評估 + 持久化 + context（~100 行）
5. `on_tick_strategy_dispatch()` — Open/Close 分派（~350 行，含 S-01 重構後）
6. `on_tick_risk_checks()` — 風控 9 項檢查 + 執行（~200 行）
7. `on_tick_housekeeping()` — 統計、快照、canary（~50 行）

每個子方法 50-200 行，符合規範。

---

### R-03 [READABILITY] `run_event_consumer()` 函數包含完整主循環 ~800 行 — **Medium**

**文件**：`event_consumer/mod.rs:31-900+`

一個 async 函數包含所有 setup + 主 select! 循環 + exchange event handling。

**建議**：setup 部分（31-520）已用 `setup.rs` + `dispatch.rs` 做了部分提取。主循環的 exchange event 處理（572-800）可提取到 `event_consumer/exchange_events.rs`。

---

### R-04 [READABILITY] 命名不一致：`shadow_order_tx` vs `ShadowOrderRequest` — **Low**

**文件**：`tick_pipeline/mod.rs:392-416`

`ShadowOrderRequest` 這個名稱源自早期 "paper only + shadow to demo" 架構，但現在同一結構體也用於 exchange mode primary orders（`is_primary=true`）。名稱 "Shadow" 具誤導性。

**建議**：重命名為 `OrderDispatchRequest` 或 `ExchangeOrderRequest`，`shadow_order_tx` 改為 `order_dispatch_tx`。影響面：TickPipeline、dispatch.rs、event_consumer。

---

### R-05 [READABILITY] Python `governance_routes.py` 1914 行 — **High (違規)**

**文件**：`control_api_v1/app/governance_routes.py:1914 行`

已超 1200 行硬上限（§九），且在 CLAUDE.md 留尾中已標記。

**建議**：按功能域拆分：
- `governance_auth_routes.py`（授權相關 ~400 行）
- `governance_risk_routes.py`（風控相關 ~300 行）
- `governance_promotion_routes.py`（6-01~03 漸進放權 ~300 行）
- `governance_routes.py`（剩餘核心 + 路由器注冊 ~900 行）

---

## 四、死重評估 [DEAD-WEIGHT]

### D-01 [DEAD-WEIGHT] `fast_track` price_drop / margin_utilization 硬編碼 0.0 — **Medium**

**文件**：`tick_pipeline/on_tick.rs:157-159`

```rust
let ft_action = crate::fast_track::evaluate_fast_track(
    self.governance.risk.level,
    0.0, // PNL-4 dead input
    0.0, // PNL-4 dead input
);
```

兩個參數永遠為 0.0，`evaluate_fast_track` 中的閃崩和保證金危機分支永遠不會觸發。已標記為 PNL-4 跟進，但持續每 tick 調用仍有 CPU 開銷（函數內有多條 if 比較）。

**建議**：在 PNL-4 修復前，可以短路：如果只有 `risk_level >= CircuitBreaker` 才有意義，直接內聯該檢查，跳過函數調用。或在 `evaluate_fast_track` 內部提前返回（已有，影響小）。

---

### D-02 [DEAD-WEIGHT] `canary_mode` + `CanaryRecord` — **Low**

**文件**：`tick_pipeline/on_tick.rs:1189-1214`, `event_consumer/mod.rs:461-477`

灰度模式（`OPENCLAW_CANARY_MODE`）在系統驗證完畢後（R-07 通過）應已無需保留。每 tick 調用 `maybe_canary_record()`，即使不啟用也有分支判斷 + 5 參數傳遞開銷。

**建議**：如果灰度驗證已完成，可以用 feature flag 編譯排除或刪除。當前保留待確認。

---

### D-03 [DEAD-WEIGHT] `_exchange_event_rx_field` / `_scanner_store` 下劃線前綴 unused 字段 — **Low**

**文件**：`event_consumer/mod.rs:51,60`

EventConsumerDeps 中有 `_exchange_event_rx_field` 和 `_scanner_store` 用下劃線前綴標記未使用，但仍在解構時分配。

**建議**：確認是否為預留接口。如果是死代碼應清除；如果是 Phase 計劃，保留但添加 TODO 標記。

---

## 五、優化優先級排序

| 排名 | ID | 類型 | 影響 | 工作量 | 風險 |
|------|----|------|------|--------|------|
| 1 | R-01 | READABILITY | High | Medium | Low — 純移動代碼 |
| 2 | R-02/S-01 | READABILITY+SIMPLIFY | High | Medium | Low — 提取 helper |
| 3 | P-01 | PERF | High | Low | Very Low — local alias |
| 4 | P-04 | PERF | Medium | Low | Very Low — 刪除 .clone() |
| 5 | P-02 | PERF | High | Medium-High | Medium — PriceEvent 結構變更 |
| 6 | S-02+S-03 | SIMPLIFY | Medium | Low | Very Low |
| 7 | P-05 | PERF | Medium | Low | Very Low |
| 8 | R-05 | READABILITY | High | Medium | Low |
| 9 | P-08 | PERF | Medium | Medium | Low — trait 簽名變更 |
| 10 | S-04 | SIMPLIFY | Low | Low | Very Low |
| 11 | P-07 | PERF | Low | Medium | Low |
| 12 | P-03 | PERF | Medium | Medium | Medium — 依賴 P-02 |
| 13 | P-06 | PERF | Low | Low | Very Low |
| 14 | D-01 | DEAD-WEIGHT | Medium | Low | Very Low |
| 15 | R-04 | READABILITY | Low | Medium | Low — rename 影響面中等 |

---

## 六、總結

### 核心發現

1. **最大瓶頸**：`on_tick()` 1187 行單函數是系統可維護性和性能的核心風險點。每 tick 的 String clone + metadata HashMap + risk_config deep-clone 構成可測量的分配壓力。

2. **合規違規**：4 個 Rust 文件 + 1 個 Python 文件超 1200 行硬上限（§九）。`on_tick.rs` 僅超 28 行，通過 S-01 重構即可解決。`risk_config.rs` 和 `governance_routes.py` 需要結構性拆分。

3. **架構健康**：整體架構設計良好 — sole-owner 無鎖模式（TickPipeline）、try_send 非阻塞通道、batch flush DB 寫入器、JSONL fallback、信號節流（DB-RUN-1/2 已實施 99.6% 降幅）。主要優化空間在熱路徑的微觀分配層面。

4. **DB 層健康**：索引覆蓋充分（V005 遷移定義了 42 個索引）。batch INSERT + ON CONFLICT DO NOTHING 模式正確。未發現 N+1 查詢（Rust 側全部 batch 寫入，Python 側僅讀取）。

5. **WebSocket 層**：自動重連 + 指數退避 + 15s 超時保護 + 分批訂閱（Bybit 10 topic/call 限制）均已實施。`process_message` 的 `serde_json::Value` 動態解析是可選優化點，但不在 tick 管線關鍵路徑上。

### 建議執行計劃

**Phase A（1-2 小時，無功能變更）**：
- P-01 symbol clone 優化
- P-04 刪除 risk_config clone
- S-02 + S-03 提取 helper
- S-04 now_ms 統一

**Phase B（2-4 小時，重構）**：
- R-02 + S-01：on_tick 拆分為 7 子方法
- R-01：risk_config.rs 默認值提取
- P-05：seen_exec_ids 改 HashSet

**Phase C（4-8 小時，結構性變更）**：
- P-02：PriceEvent metadata 結構化
- P-08：TickContext 借用化
- R-05：governance_routes.py 拆分
- R-01：event_consumer/mod.rs 拆分

---

*報告由 E5 Performance Engineer 生成。所有建議均為純優化/重構，不改變功能行為。*

# Bybit V5 API Reference / Bybit V5 API 字典手冊

> OpenClaw Rust 引擎 Bybit API 層完整功能索引。
> 每個條目：做什麼 → 怎麼調 → 輸入什麼 → 輸出什麼 → 程式在哪。

**版本**: v1 | **日期**: 2026-04-04 | **審計**: BB+E5+PA 三輪通過

---

## 1. REST API

### 1.1 Market Data — `market_data_client.rs`

所有端點為公開（無需認證），Rate Group: **Market**。
Client 創建：`MarketDataClient::new(client: Arc<BybitRestClient>)`

---

#### get_server_time
- **服務**: 查詢 Bybit 伺服器當前時間。用於校準本地時鐘偏差、驗證簽名時間戳是否在 recv_window 內。如果本地與伺服器時差超過 5 秒，簽名會被拒絕。
- **調用**: `client.get_server_time()`
- **Bybit 路徑**: `GET /v5/market/time`
- **Input**: 無
- **Output**: `BybitResult<ServerTime>`
  ```
  ServerTime { time_second: u64, time_nano: String }
  ```
- **關聯程式**: `market_data_client.rs:261`

---

#### get_klines
- **服務**: 查詢指定交易對的 K 線歷史數據，支持多時間框架（1m 到月線）。常用於技術指標計算、策略回測數據準備。返回按時間倒序排列（最新在前）。每次最多返回 1000 根。可通過 start/end 參數分頁拉取歷史數據。
- **調用**: `client.get_klines(category, symbol, interval, start, end, limit)`
- **Bybit 路徑**: `GET /v5/market/kline`
- **Input**:
  - `category: &str` — 品類 ("linear", "spot", "inverse")
  - `symbol: &str` — 交易對 ("BTCUSDT")
  - `interval: &str` — K 線間隔 ("1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M")
  - `start: Option<u64>` — 開始時間戳 ms
  - `end: Option<u64>` — 結束時間戳 ms
  - `limit: Option<u32>` — 返回數量，默認 200，最大 1000
- **Output**: `BybitResult<Vec<KlineBar>>`
  ```
  KlineBar { start_time: u64, open: f64, high: f64, low: f64, close: f64, volume: f64, turnover: f64 }
  ```
- **關聯程式**: `market_data_client.rs:313`

---

#### get_mark_price_klines
- **服務**: 查詢標記價格（Mark Price）K 線。標記價格由 Bybit 根據多交易所指數計算，用於盈虧結算和清算判定，比最新成交價更穩定。用於計算未實現盈虧、判斷清算距離。
- **調用**: `client.get_mark_price_klines(category, symbol, interval, start, end, limit)`
- **Bybit 路徑**: `GET /v5/market/mark-price-kline`
- **Input**: 同 `get_klines`
- **Output**: `BybitResult<Vec<KlineBar>>`（同上）
- **關聯程式**: `market_data_client.rs:348`

---

#### get_premium_index_klines
- **服務**: 查詢溢價指數（Premium Index）K 線。溢價指數反映永續合約價格相對現貨指數的偏離程度，是資金費率計算的核心輸入。用於預測下一期資金費率、判斷市場情緒偏多或偏空。
- **調用**: `client.get_premium_index_klines(category, symbol, interval, start, end, limit)`
- **Bybit 路徑**: `GET /v5/market/premium-index-price-kline`
- **Input**: 同 `get_klines`
- **Output**: `BybitResult<Vec<KlineBar>>`（同上）
- **關聯程式**: `market_data_client.rs:376`

---

#### get_index_price_klines
- **服務**: 查詢指數價格 K 線。指數價格由多交易所現貨價格加權平均得出，是永續合約標記價格的基礎。用於基差分析（合約價 vs 指數價）、套利策略。
- **調用**: `client.get_index_price_klines(category, symbol, interval, start, end, limit)`
- **Bybit 路徑**: `GET /v5/market/index-price-kline`
- **Input**: 同 `get_klines`
- **Output**: `BybitResult<Vec<KlineBar>>`（同上）
- **關聯程式**: `market_data_client.rs:876`

---

#### get_tickers
- **服務**: 查詢 24 小時行情快照，包含最新價、24h 成交量、最高/最低價、資金費率、持倉量等。可查單個交易對或全品類。用於市場掃描、篩選活躍品種、監控資金費率。數據約每秒更新一次。
- **調用**: `client.get_tickers(category, symbol)`
- **Bybit 路徑**: `GET /v5/market/tickers`
- **Input**:
  - `category: &str` — 品類
  - `symbol: Option<&str>` — 交易對（None = 查詢全品類所有交易對）
- **Output**: `BybitResult<Vec<TickerInfo>>`
  ```
  TickerInfo { symbol, last_price, bid1_price, ask1_price, volume_24h, turnover_24h,
               high_price_24h, low_price_24h, prev_price_24h, open_interest,
               funding_rate, next_funding_time }
  ```
- **關聯程式**: `market_data_client.rs:401`

---

#### get_orderbook
- **服務**: 查詢即時訂單簿深度快照。返回指定檔數的買賣掛單列表（價格+數量）。用於滑點估算、流動性分析、限價單定價。注意：REST 輪詢會消耗 rate limit，高頻場景應改用 WS orderbook 訂閱。
- **調用**: `client.get_orderbook(category, symbol, limit)`
- **Bybit 路徑**: `GET /v5/market/orderbook`
- **Input**:
  - `category: &str` — 品類
  - `symbol: &str` — 交易對
  - `limit: Option<u32>` — 檔數（1, 25, 50, 200, 500），默認 25
- **Output**: `BybitResult<OrderbookSnapshot>`
  ```
  OrderbookSnapshot { symbol, bids: Vec<[f64; 2]>, asks: Vec<[f64; 2]>, ts, update_id }
  ```
  每個 bid/ask 為 `[price, qty]`
- **關聯程式**: `market_data_client.rs:429`

---

#### get_open_interest
- **服務**: 查詢合約未平倉量（Open Interest）歷史。OI 反映市場中尚未平倉的合約總量，是衡量市場參與度和趨勢確認的重要指標。OI 上升+價格上升=趨勢強化；OI 下降+價格上升=軋空/弱勢上漲。
- **調用**: `client.get_open_interest(category, symbol, interval, limit, start, end)`
- **Bybit 路徑**: `GET /v5/market/open-interest`
- **Input**:
  - `category: &str` — 品類
  - `symbol: &str` — 交易對
  - `interval: &str` — 統計間隔 ("5min", "15min", "30min", "1h", "4h", "1d")
  - `limit: Option<u32>` — 數量
  - `start: Option<u64>`, `end: Option<u64>` — 時間範圍 ms
- **Output**: `BybitResult<Vec<OpenInterestRecord>>`
  ```
  OpenInterestRecord { open_interest: f64, timestamp: String }
  ```
- **關聯程式**: `market_data_client.rs:461`

---

#### get_funding_history
- **服務**: 查詢永續合約資金費率歷史。資金費率是多空雙方定期互付的費用，每 8 小時結算一次。正費率=多方付空方（市場偏多）；負費率=空方付多方。用於資金費率套利策略、持倉成本計算。
- **調用**: `client.get_funding_history(category, symbol, start, end, limit)`
- **Bybit 路徑**: `GET /v5/market/funding/history`
- **Input**:
  - `category: &str` — 品類
  - `symbol: &str` — 交易對
  - `start: Option<u64>`, `end: Option<u64>` — 時間範圍 ms
  - `limit: Option<u32>` — 數量，最大 200
- **Output**: `BybitResult<Vec<FundingRecord>>`
  ```
  FundingRecord { symbol, funding_rate, funding_rate_timestamp }
  ```
- **關聯程式**: `market_data_client.rs:512`

---

#### get_long_short_ratio
- **服務**: 查詢帳戶多空比。反映持有多頭 vs 空頭帳戶的比例，是市場情緒的逆向指標。極端多空比（>2.0 或 <0.5）往往預示反轉。用於情緒分析、反向交易信號。
- **調用**: `client.get_long_short_ratio(symbol, period, limit)`
- **Bybit 路徑**: `GET /v5/market/account-ratio`
- **Input**:
  - `symbol: &str` — 交易對
  - `period: &str` — 統計週期 ("5min", "15min", "30min", "1h", "4h", "1d")
  - `limit: Option<u32>` — 數量
- **Output**: `BybitResult<Vec<LongShortRecord>>`
  ```
  LongShortRecord { buy_ratio, sell_ratio, timestamp }
  ```
- **關聯程式**: `market_data_client.rs:558`

---

#### get_risk_limit
- **服務**: 查詢風險限額層級表。每個交易對有多個風險限額層級，層級越高允許的最大持倉越大但要求的保證金率也越高。用於計算最大可開倉位、保證金需求。
- **調用**: `client.get_risk_limit(category, symbol)`
- **Bybit 路徑**: `GET /v5/market/risk-limit`
- **Input**:
  - `category: &str` — 品類
  - `symbol: Option<&str>` — 交易對
- **Output**: `BybitResult<Vec<RiskLimitTier>>`
  ```
  RiskLimitTier { id: u32, symbol, risk_limit_value: f64, max_leverage: f64,
                  initial_margin: f64, maintenance_margin: f64 }
  ```
- **關聯程式**: `market_data_client.rs:594`

---

#### get_insurance
- **服務**: 查詢保險基金池數據。保險基金用於在清算事件中覆蓋穿倉損失，是 ADL（自動減倉）的最後防線。保險基金持續減少可能預示大規模清算風險。
- **調用**: `client.get_insurance(coin)`
- **Bybit 路徑**: `GET /v5/market/insurance`
- **Input**:
  - `coin: Option<&str>` — 幣種（None = 全部）
- **Output**: `BybitResult<Vec<InsuranceRecord>>`
  ```
  InsuranceRecord { coin: String, balance: f64, value: f64 }
  ```
- **關聯程式**: `market_data_client.rs:638`

---

#### get_adl_alert
- **服務**: 查詢 ADL（自動減倉）排名警報。當保險基金不足以覆蓋穿倉時，Bybit 會對盈利倉位強制減倉。ADL 排名越高（1-5），被減倉的風險越大。**生存相關**（原則 #5）——必須監控。
- **調用**: `client.get_adl_alert(category, symbol)`
- **Bybit 路徑**: `GET /v5/market/adl-alert`
- **Input**:
  - `category: &str` — 品類
  - `symbol: Option<&str>` — 交易對
- **Output**: `BybitResult<Vec<AdlAlert>>`
  ```
  AdlAlert { symbol, side, adl_rank_indicator: i32 }
  ```
- **關聯程式**: `market_data_client.rs:680`

---

#### get_recent_trades
- **服務**: 查詢近期公開成交記錄。返回最新的逐筆成交數據，包含方向、價格、數量。用於微觀結構分析、大單偵測、成交量分佈分析。
- **調用**: `client.get_recent_trades(category, symbol, limit)`
- **Bybit 路徑**: `GET /v5/market/recent-trade`
- **Input**:
  - `category: &str` — 品類
  - `symbol: &str` — 交易對
  - `limit: Option<u32>` — 數量，最大 1000
- **Output**: `BybitResult<Vec<RecentTrade>>`
  ```
  RecentTrade { exec_id, symbol, price: f64, size: f64, side, time, is_block_trade: bool }
  ```
- **關聯程式**: `market_data_client.rs:727`

---

#### get_historical_volatility
- **服務**: 查詢歷史波動率（期權市場）。反映標的資產在不同時間窗口的實際波動水平。用於期權定價、波動率交易策略、風險評估。
- **調用**: `client.get_historical_volatility(category, period, limit)`
- **Bybit 路徑**: `GET /v5/market/historical-volatility`
- **Input**:
  - `category: &str` — 品類（通常 "option"）
  - `period: Option<u32>` — 天數
  - `limit: Option<u32>` — 數量
- **Output**: `BybitResult<Vec<VolatilityRecord>>`
  ```
  VolatilityRecord { period: u32, value: String, time: String }
  ```
- **關聯程式**: `market_data_client.rs:774`

---

#### get_delivery_price
- **服務**: 查詢期貨交割價格記錄。適用於有交割日的合約（非永續），記錄每次交割的結算價格。
- **調用**: `client.get_delivery_price(category, symbol, limit)`
- **Bybit 路徑**: `GET /v5/market/delivery-price`
- **Input**:
  - `category: &str` — 品類
  - `symbol: Option<&str>` — 交易對
  - `limit: Option<u32>` — 數量
- **Output**: `BybitResult<Vec<DeliveryPrice>>`
  ```
  DeliveryPrice { symbol, delivery_price: f64, delivery_time: String }
  ```
- **關聯程式**: `market_data_client.rs:822`

---

#### get_price_limit
- **服務**: 查詢交易對的價格限制（最高買入/最低賣出）。超出此範圍的訂單會被 Bybit 直接拒絕。下單前應先檢查以避免浪費 rate limit。實際通過 instruments-info 端點獲取價格過濾器。
- **調用**: `client.get_price_limit(category, symbol)`
- **Bybit 路徑**: `GET /v5/market/instruments-info`（fallback）
- **Input**:
  - `category: &str` — 品類
  - `symbol: &str` — 交易對
- **Output**: `BybitResult<PriceLimit>`
  ```
  PriceLimit { symbol, buy_limit_price: f64, sell_limit_price: f64 }
  ```
- **關聯程式**: `market_data_client.rs:904`

---

### 1.2 Orders — `order_manager.rs`

Rate Group: **Order** (10 req/s)。
Client 創建：`OrderManager::new(client: Arc<BybitRestClient>, instruments: Arc<InstrumentInfoCache>)`

核心枚舉：
- `OrderSide { Buy, Sell }`
- `OrderType { Market, Limit }`
- `TimeInForce { GTC, IOC, FOK, PostOnly }`
- `TriggerDirection { Rise = 1, Fall = 2 }`
- `OrderCategory { Linear, Spot, Inverse }`

---

#### place_order
- **服務**: 提交新訂單（市價/限價/條件單）。支持止盈止損附帶、reduce-only、close-on-trigger 等選項。訂單在提交前會通過 InstrumentInfoCache 驗證數量和價格精度。市價單不需要 price 和 time_in_force。條件單需要設置 trigger_price 和 trigger_direction。
- **調用**: `client.place_order(req: CreateOrderRequest)`
- **Bybit 路徑**: `POST /v5/order/create`
- **Input**:
  ```
  CreateOrderRequest {
    category: OrderCategory,     // Linear / Spot / Inverse
    symbol: String,              // "BTCUSDT"
    side: OrderSide,             // Buy / Sell
    order_type: OrderType,       // Market / Limit
    qty: f64,                    // 數量（會自動按 qty_step 取整）
    price: Option<f64>,          // 限價單價格（市價單為 None）
    time_in_force: Option<TimeInForce>,  // GTC / IOC / FOK / PostOnly
    reduce_only: Option<bool>,   // 是否只減倉
    close_on_trigger: Option<bool>, // 觸發後是否平倉
    order_link_id: Option<String>,  // 客戶端自定義訂單 ID
    trigger_price: Option<f64>,  // 條件單觸發價
    trigger_direction: Option<TriggerDirection>, // Rise=1 / Fall=2
    take_profit: Option<f64>,    // 訂單附帶止盈價
    stop_loss: Option<f64>,      // 訂單附帶止損價
    tp_trigger_by: Option<String>, // "LastPrice" / "MarkPrice"
    sl_trigger_by: Option<String>, // "LastPrice" / "MarkPrice"
  }
  ```
- **Output**: `BybitResult<OrderResponse>`
  ```
  OrderResponse { order_id: String, order_link_id: String }
  ```
- **關聯程式**: `order_manager.rs:364`

---

#### amend_order
- **服務**: 修改未成交訂單的價格、數量、觸發價、止盈止損。只能修改未成交或部分成交的訂單。可通過 order_id 或 order_link_id 定位。
- **調用**: `client.amend_order(req: AmendOrderRequest)`
- **Bybit 路徑**: `POST /v5/order/amend`
- **Input**:
  ```
  AmendOrderRequest {
    category: OrderCategory,
    symbol: String,
    order_id: Option<String>,      // Bybit 訂單 ID（二選一）
    order_link_id: Option<String>, // 客戶端訂單 ID（二選一）
    qty: Option<f64>,              // 新數量
    price: Option<f64>,            // 新價格
    trigger_price: Option<f64>,    // 新觸發價
    take_profit: Option<f64>,      // 新止盈
    stop_loss: Option<f64>,        // 新止損
  }
  ```
- **Output**: `BybitResult<OrderResponse>`
- **關聯程式**: `order_manager.rs:480`

---

#### cancel_order
- **服務**: 取消指定訂單。通過 order_id 定位。
- **調用**: `client.cancel_order(category, symbol, order_id)`
- **Bybit 路徑**: `POST /v5/order/cancel`
- **Input**:
  - `category: OrderCategory`
  - `symbol: &str`
  - `order_id: &str`
- **Output**: `BybitResult<OrderResponse>`
- **關聯程式**: `order_manager.rs:394`

---

#### cancel_all
- **服務**: 取消指定交易對的所有未成交訂單。緊急情況下的批量撤單操作。
- **調用**: `client.cancel_all(category, symbol)`
- **Bybit 路徑**: `POST /v5/order/cancel-all`
- **Input**:
  - `category: OrderCategory`
  - `symbol: &str`
- **Output**: `BybitResult<Vec<OrderResponse>>`
- **關聯程式**: `order_manager.rs:416`

---

#### get_active_orders
- **服務**: 查詢當前活躍訂單（未成交+部分成交+最近 500 筆已完成訂單）。即時數據，比 order history 響應更快。
- **調用**: `client.get_active_orders(category, symbol)`
- **Bybit 路徑**: `GET /v5/order/realtime`
- **Input**:
  - `category: OrderCategory`
  - `symbol: Option<&str>` — None = 查詢所有
- **Output**: `BybitResult<Vec<OrderInfo>>`
  ```
  OrderInfo { order_id, order_link_id, symbol, side, order_type, price, qty,
              cum_exec_qty, cum_exec_value, avg_price, order_status,
              created_time, updated_time }
  ```
- **關聯程式**: `order_manager.rs:504`

---

#### get_order_history
- **服務**: 查詢歷史訂單（最長 2 年）。適合回顧和審計。
- **調用**: `client.get_order_history(category, symbol, limit)`
- **Bybit 路徑**: `GET /v5/order/history`
- **Input**:
  - `category: OrderCategory`
  - `symbol: Option<&str>`
  - `limit: Option<u32>`
- **Output**: `BybitResult<Vec<OrderInfo>>`
- **關聯程式**: `order_manager.rs:530`

---

#### get_executions
- **服務**: 查詢成交記錄（fills）。每筆成交包含成交價、成交量、手續費、成交類型。用於交易歸因、手續費計算、PnL 核對。
- **調用**: `client.get_executions(category, symbol, limit)`
- **Bybit 路徑**: `GET /v5/execution/list`
- **Input**:
  - `category: OrderCategory`
  - `symbol: Option<&str>`
  - `limit: Option<u32>`
- **Output**: `BybitResult<Vec<ExecutionInfo>>`
  ```
  ExecutionInfo { exec_id, symbol, side, exec_price: f64, exec_qty: f64, exec_value: f64,
                  exec_fee: f64, fee_currency, order_id, order_link_id, exec_type, exec_time }
  ```
- **關聯程式**: `order_manager.rs:556`

---

### 1.3 Batch Orders — `batch_order_manager.rs`

Rate Group: **Order**。一次最多 10 筆。
Client 創建：`BatchOrderManager::new(client: Arc<BybitRestClient>)`

---

#### batch_place
- **服務**: 批量下單（最多 10 筆）。一次 API 調用提交多筆訂單，節省 rate limit。每筆訂單獨立處理，部分失敗不影響其他。返回每筆的獨立結果。
- **調用**: `client.batch_place(category, orders)`
- **Bybit 路徑**: `POST /v5/order/create-batch`
- **Input**:
  - `category: OrderCategory`
  - `orders: Vec<CreateOrderRequest>` — 最多 10 筆
- **Output**: `BybitResult<BatchOrderResponse>`
  ```
  BatchOrderResponse { results: Vec<BatchOrderResult>, success_count, fail_count }
  BatchOrderResult { order_id, order_link_id, ret_code, ret_msg }
  ```
- **關聯程式**: `batch_order_manager.rs:176`

---

#### batch_amend
- **服務**: 批量修改訂單（最多 10 筆）。
- **調用**: `client.batch_amend(category, amends)`
- **Bybit 路徑**: `POST /v5/order/amend-batch`
- **Input**:
  - `category: OrderCategory`
  - `amends: Vec<AmendOrderRequest>` — 最多 10 筆
- **Output**: `BybitResult<BatchOrderResponse>`
- **關聯程式**: `batch_order_manager.rs:262`

---

#### batch_cancel
- **服務**: 批量撤單（最多 10 筆）。
- **調用**: `client.batch_cancel(category, cancels)`
- **Bybit 路徑**: `POST /v5/order/cancel-batch`
- **Input**:
  - `category: OrderCategory`
  - `cancels: Vec<CancelOrderItem>` — `CancelOrderItem { symbol, order_id, order_link_id }`
- **Output**: `BybitResult<BatchOrderResponse>`
- **關聯程式**: `batch_order_manager.rs:333`

---

### 1.4 Positions — `position_manager.rs`

Rate Group: **Position** (10 req/s)。
Client 創建：`PositionManager::new(client: Arc<BybitRestClient>)`

---

#### get_positions
- **服務**: 查詢當前所有持倉信息，包含入場價、標記價、未實現盈虧、槓桿、清算價、止盈止損設置等完整數據。可按交易對過濾或查詢全部。
- **調用**: `client.get_positions(category, symbol)`
- **Bybit 路徑**: `GET /v5/position/list`
- **Input**:
  - `category: OrderCategory`
  - `symbol: Option<&str>`
- **Output**: `BybitResult<Vec<PositionInfo>>`
  ```
  PositionInfo { symbol, side, size: f64, avg_price: f64, mark_price: f64,
                 unrealised_pnl: f64, leverage: f64, liq_price: f64,
                 take_profit: f64, stop_loss: f64, position_idx: i32,
                 trailing_stop: f64, position_value: f64, cum_realised_pnl: f64,
                 created_time, updated_time }
  ```
- **關聯程式**: `position_manager.rs:159`

---

#### set_leverage
- **服務**: 設置交易對的槓桿倍數（買/賣可分別設置）。如果設置的槓桿與當前相同，Bybit 返回 110043（LeverageNotModified），代碼將此視為成功（冪等操作）。
- **調用**: `client.set_leverage(category, symbol, buy_leverage, sell_leverage)`
- **Bybit 路徑**: `POST /v5/position/set-leverage`
- **Input**:
  - `category: OrderCategory`
  - `symbol: &str`
  - `buy_leverage: f64`, `sell_leverage: f64`
- **Output**: `BybitResult<()>`
- **關聯程式**: `position_manager.rs:200`

---

#### set_trading_stop
- **服務**: 設置持倉的止盈/止損/追蹤止損。可同時設置多個止損類型。支持選擇觸發價格基準（LastPrice 或 MarkPrice）。追蹤止損需要設置激活價格和距離。
- **調用**: `client.set_trading_stop(req: TradingStopRequest)`
- **Bybit 路徑**: `POST /v5/position/trading-stop`
- **Input**:
  ```
  TradingStopRequest {
    category: OrderCategory,
    symbol: String,
    take_profit: Option<f64>,
    stop_loss: Option<f64>,
    tp_trigger_by: Option<String>,  // "LastPrice" / "MarkPrice"
    sl_trigger_by: Option<String>,
    trailing_stop: Option<f64>,     // 追蹤止損距離（價格單位）
    active_price: Option<f64>,      // 追蹤止損激活價格
    position_idx: Option<i32>,      // 0=單向, 1=買側, 2=賣側
  }
  ```
- **Output**: `BybitResult<()>`
- **關聯程式**: `position_manager.rs:258`

---

#### switch_position_mode
- **服務**: 切換持倉模式：單向（One-Way）或對沖（Hedge）。單向模式同一交易對只能持有一個方向；對沖模式可同時持有多空。切換前需先平掉所有持倉。
- **調用**: `client.switch_position_mode(category, symbol, mode)`
- **Bybit 路徑**: `POST /v5/position/switch-mode`
- **Input**:
  - `category: OrderCategory`
  - `symbol: &str`
  - `mode: i32` — 0=單向, 3=對沖
- **Output**: `BybitResult<()>`
- **關聯程式**: `position_manager.rs:293`

---

#### confirm_pending_mmr
- **服務**: 確認待定的維持保證金率（MMR）變更。當風險限額調整後，Bybit 要求用戶確認新的 MMR。替代已棄用的 `/v5/position/set-risk-limit`。
- **調用**: `client.confirm_pending_mmr(category, symbol)`
- **Bybit 路徑**: `POST /v5/position/confirm-mmr`
- **Input**:
  - `category: OrderCategory`
  - `symbol: &str`
- **Output**: `BybitResult<()>`
- **關聯程式**: `position_manager.rs:327`

---

#### set_auto_add_margin
- **服務**: 開啟/關閉自動追加保證金。開啟後當倉位保證金不足時自動從可用餘額補充，避免被清算。
- **調用**: `client.set_auto_add_margin(category, symbol, auto_add_margin, position_idx)`
- **Bybit 路徑**: `POST /v5/position/set-auto-add-margin`
- **Input**:
  - `category: OrderCategory`
  - `symbol: &str`
  - `auto_add_margin: i32` — 0=關, 1=開
  - `position_idx: Option<i32>`
- **Output**: `BybitResult<()>`
- **關聯程式**: `position_manager.rs:367`

---

#### add_margin
- **服務**: 手動追加保證金到指定持倉。用於主動降低清算風險。
- **調用**: `client.add_margin(category, symbol, margin, position_idx)`
- **Bybit 路徑**: `POST /v5/position/add-margin`
- **Input**:
  - `category: OrderCategory`
  - `symbol: &str`
  - `margin: f64` — 追加金額
  - `position_idx: Option<i32>`
- **Output**: `BybitResult<()>`
- **關聯程式**: `position_manager.rs:404`

---

#### get_closed_pnl
- **服務**: 查詢已平倉盈虧記錄（最長 2 年）。每筆記錄包含入場/出場價、已實現盈虧、槓桿等。用於績效歸因、稅務計算。
- **調用**: `client.get_closed_pnl(category, symbol, limit)`
- **Bybit 路徑**: `GET /v5/position/closed-pnl`
- **Input**:
  - `category: OrderCategory`
  - `symbol: Option<&str>`
  - `limit: Option<u32>`
- **Output**: `BybitResult<Vec<ClosedPnlInfo>>`
  ```
  ClosedPnlInfo { symbol, order_id, side, qty: f64, avg_entry_price: f64,
                  avg_exit_price: f64, closed_pnl: f64, cum_entry_value: f64,
                  cum_exit_value: f64, fill_count: i32, leverage: f64,
                  created_time, updated_time }
  ```
- **關聯程式**: `position_manager.rs:434`

---

### 1.5 Account — `account_manager.rs`

Rate Group: **Account** (10 req/s)。
Client 創建：`AccountManager::new()` — 無需 Arc<BybitRestClient>，在調用時傳入。
內建緩存：錢包餘額和手續費率會在 refresh 後緩存，可通過 `usdt_equity()` 等方法零延遲讀取。

---

#### refresh_balance
- **服務**: 從 Bybit 獲取並緩存錢包餘額（UNIFIED 帳戶）。更新後可通過 `usdt_equity()`、`usdt_wallet_balance()`、`usdt_available()` 零延遲讀取。包含所有幣種的權益、可用餘額、未實現盈虧。
- **調用**: `client.refresh_balance(rest_client)`
- **Bybit 路徑**: `GET /v5/account/wallet-balance`
- **Input**: `client: &BybitRestClient`
- **Output**: `BybitResult<&Self>`（鏈式調用）
- **緩存讀取**:
  - `usdt_equity() -> f64` — USDT 總權益
  - `usdt_wallet_balance() -> f64` — USDT 錢包餘額
  - `usdt_available() -> f64` — USDT 可用餘額
  - `wallet_snapshot() -> WalletState` — 完整快照
  ```
  WalletState { account_type, total_equity, total_wallet_balance, total_available_balance,
                total_unrealised_pnl, coins: HashMap<String, CoinBalance>, updated_at_ms }
  CoinBalance { coin, wallet_balance, available_to_withdraw, equity, unrealised_pnl, cum_realised_pnl }
  ```
- **關聯程式**: `account_manager.rs:173`

---

#### refresh_fee_rates
- **服務**: 從 Bybit 獲取並緩存手續費率。之後可通過 `taker_fee(symbol)`、`maker_fee(symbol)` 零延遲讀取。未查到的交易對使用默認費率（taker 0.055%, maker 0.02%）。
- **調用**: `client.refresh_fee_rates(rest_client, category)`
- **Bybit 路徑**: `GET /v5/account/fee-rate`
- **Input**: `client: &BybitRestClient`, `category: &str`
- **Output**: `BybitResult<usize>`（返回緩存的交易對數量）
- **緩存讀取**:
  - `get_fee_rate(symbol) -> FeeRate { symbol, maker_fee_rate, taker_fee_rate }`
  - `taker_fee(symbol) -> f64`
  - `maker_fee(symbol) -> f64`
- **關聯程式**: `account_manager.rs:251`

---

#### get_account_info
- **服務**: 查詢帳戶配置：保證金模式、統一保證金狀態、SMP 群組。
- **調用**: `client.get_account_info(rest_client)`
- **Bybit 路徑**: `GET /v5/account/info`
- **Input**: `client: &BybitRestClient`
- **Output**: `BybitResult<AccountInfo>`
  ```
  AccountInfo { margin_mode, updated_time, unified_margin_status: i32, smp_group: i32, is_master_trader: bool }
  ```
- **關聯程式**: `account_manager.rs:333`

---

#### set_hedging_mode
- **服務**: 啟用或禁用帳戶級對沖模式。
- **調用**: `client.set_hedging_mode(rest_client, hedging)`
- **Bybit 路徑**: `POST /v5/account/set-hedging-mode`
- **Input**: `client: &BybitRestClient`, `hedging: &str` — "ON" / "OFF"
- **Output**: `BybitResult<()>`
- **關聯程式**: `account_manager.rs:363`

---

#### get_borrow_history
- **服務**: 查詢保證金借幣歷史。
- **調用**: `client.get_borrow_history(rest_client, currency, limit)`
- **Bybit 路徑**: `GET /v5/account/borrow-history`
- **Input**: `client: &BybitRestClient`, `currency: Option<&str>`, `limit: Option<u32>`
- **Output**: `BybitResult<Vec<BorrowRecord>>`
  ```
  BorrowRecord { currency, borrow_amount: f64, cost_amount: f64, created_time, borrow_type }
  ```
- **關聯程式**: `account_manager.rs:389`

---

#### repay
- **服務**: 還款保證金借幣。
- **調用**: `client.repay(rest_client, coin)`
- **Bybit 路徑**: `POST /v5/account/repay`
- **Input**: `client: &BybitRestClient`, `coin: &str`
- **Output**: `BybitResult<()>`
- **關聯程式**: `account_manager.rs:417`

---

### 1.6 Platform / Asset — `platform_client.rs`

Rate Group: **Account**（帳戶端點）/ **Asset**（資產端點）。
Client 創建：`PlatformClient::new(client: Arc<BybitRestClient>)`

---

#### get_transaction_log
- **服務**: 查詢帳戶交易日誌——完整的資金流水審計追蹤。包含交易、結算、轉帳、手續費等所有資金變動。用於對賬、審計、稅務記錄。
- **調用**: `client.get_transaction_log(account_type, category, start, end, limit)`
- **Bybit 路徑**: `GET /v5/account/transaction-log`
- **Input**:
  - `account_type: &str` — "UNIFIED"
  - `category: Option<&str>` — 品類過濾
  - `start: Option<u64>`, `end: Option<u64>` — 時間範圍 ms
  - `limit: Option<u32>`
- **Output**: `BybitResult<Vec<TransactionRecord>>`
  ```
  TransactionRecord { id, symbol, category, type, qty, cash_flow, currency, transaction_time }
  ```
- **關聯程式**: `platform_client.rs:179`

---

#### set_margin_mode
- **服務**: 設置帳戶保證金模式（逐倉/全倉/組合保證金）。影響所有交易對。
- **調用**: `client.set_margin_mode(mode)`
- **Bybit 路徑**: `POST /v5/account/set-margin-mode`
- **Input**: `mode: &str` — "REGULAR_MARGIN", "PORTFOLIO_MARGIN"
- **Output**: `BybitResult<()>`
- **關聯程式**: `platform_client.rs:215`

---

#### get_collateral_info / set_collateral_switch
- **服務**: 查詢/設置幣種抵押品狀態。控制哪些幣種可用作保證金抵押。
- **調用**: `client.get_collateral_info(currency)` / `client.set_collateral_switch(coin, switch)`
- **Bybit 路徑**: `GET /v5/account/collateral-info` / `POST /v5/account/set-collateral`
- **Input**: `currency: Option<&str>` / `coin: &str, switch: bool`
- **Output**: `BybitResult<Vec<CollateralInfo>>` / `BybitResult<()>`
  ```
  CollateralInfo { currency, collateral_switch: bool, borrowable: bool, collateral_ratio, free_collateral }
  ```
- **關聯程式**: `platform_client.rs:239, 277`

---

#### set_dcp / get_dcp_info
- **服務**: 設置/查詢 DCP（斷連取消保護）。DCP 是帳戶安全的關鍵功能——當所有 WS 連接斷開超過設定時間窗口後，Bybit 自動取消所有未成交訂單，防止失聯期間的風險敞口。**必須配置**。
- **調用**: `client.set_dcp(time_window)` / `client.get_dcp_info()`
- **Bybit 路徑**: `POST /v5/order/disconnected-cancel-all` / `GET /v5/account/dcp-info`
- **Input**: `time_window: u32`（秒）/ 無
- **Output**: `BybitResult<()>` / `BybitResult<DcpInfo>`
  ```
  DcpInfo { dcp_status: String, time_window: u32 }
  ```
- **關聯程式**: `platform_client.rs:294, 307`

---

#### pre_check_order
- **服務**: 訂單預檢——驗證訂單參數但不實際提交。注意：Bybit 沒有專門的預檢端點，此方法實際調用 POST /v5/order/create 並返回原始回應，需要調用方自行判斷結果。
- **調用**: `client.pre_check_order(params)`
- **Bybit 路徑**: `POST /v5/order/create`（dry-run 概念）
- **Input**: `params: serde_json::Value` — 與 place_order 相同的 JSON body
- **Output**: `BybitResult<serde_json::Value>`（原始回應）
- **關聯程式**: `platform_client.rs:362`

---

#### inter_transfer
- **服務**: 帳戶間轉帳（如 UNIFIED → CONTRACT）。自動生成 transfer_id。
- **調用**: `client.inter_transfer(coin, amount, from_account, to_account)`
- **Bybit 路徑**: `POST /v5/asset/transfer/inter-transfer`
- **Input**: `coin: &str, amount: f64, from_account: &str, to_account: &str`
- **Output**: `BybitResult<String>`（transfer_id）
- **關聯程式**: `platform_client.rs:384`

---

#### get_transfer_list
- **服務**: 查詢帳戶間轉帳歷史記錄。
- **調用**: `client.get_transfer_list(limit)`
- **Bybit 路徑**: `GET /v5/asset/transfer/query-inter-transfer-list`
- **Input**: `limit: Option<u32>`
- **Output**: `BybitResult<Vec<TransferRecord>>`
  ```
  TransferRecord { transfer_id, coin, amount, from_account_type, to_account_type, timestamp, status }
  ```
- **關聯程式**: `platform_client.rs:431`

---

#### get_all_account_balances
- **服務**: 查詢所有帳戶類型的幣種餘額。
- **調用**: `client.get_all_account_balances(account_type)`
- **Bybit 路徑**: `GET /v5/asset/transfer/query-account-coins-balance`
- **Input**: `account_type: &str`
- **Output**: `BybitResult<Vec<AccountCoinBalance>>`
  ```
  AccountCoinBalance { coin, wallet_balance, transfer_balance }
  ```
- **關聯程式**: `platform_client.rs:457`

---

#### get_coin_info
- **服務**: 查詢幣種信息——鏈詳情、精度、充提狀態。用於驗證幣種精度、檢查鏈是否可用。
- **調用**: `client.get_coin_info(coin)`
- **Bybit 路徑**: `GET /v5/asset/coin-info`
- **Input**: `coin: Option<&str>`
- **Output**: `BybitResult<Vec<CoinInfoRecord>>`
  ```
  CoinInfoRecord { coin, name, remain_amount, chains: Vec<ChainInfo> }
  ChainInfo { chain, chain_type, confirmation, min_accuracy, chain_deposit, chain_withdraw }
  ```
- **關聯程式**: `platform_client.rs:502`

---

#### apply_demo_funds
- **服務**: 申請 Demo 環境測試資金。僅限 Demo 環境使用。
- **調用**: `client.apply_demo_funds(coins)`
- **Bybit 路徑**: `POST /v5/account/demo-apply-money`
- **Input**: `coins: Vec<DemoFundRequest>` — `DemoFundRequest { coin, amount }`
- **Output**: `BybitResult<()>`
- **關聯程式**: `platform_client.rs:549`

---

### 1.7 Spot Margin — `spot_margin_client.rs`

Rate Group: **Asset** (5 req/s)。所有端點使用 UTA (Unified Trading Account) 路徑。
Client 創建：`SpotMarginClient::new(client: Arc<BybitRestClient>)`

---

#### get_margin_data
- **服務**: 查詢現貨保證金交易數據（VIP 等級專屬）。
- **Bybit 路徑**: `GET /v5/spot-margin-trade/data`
- **關聯程式**: `spot_margin_client.rs:113`

#### switch_mode
- **服務**: 開啟/關閉現貨保證金交易模式。
- **Bybit 路徑**: `POST /v5/spot-margin-uta/switch-mode`
- **Input**: `spot_margin_mode: bool`
- **關聯程式**: `spot_margin_client.rs:141`

#### set_leverage
- **服務**: 設置現貨保證金槓桿。
- **Bybit 路徑**: `POST /v5/spot-margin-uta/set-leverage`
- **Input**: `leverage: f64`
- **關聯程式**: `spot_margin_client.rs:165`

#### get_margin_state
- **服務**: 查詢當前現貨保證金狀態和槓桿。
- **Bybit 路徑**: `GET /v5/spot-margin-uta/status`
- **Output**: `SpotMarginState { spot_margin_mode: bool, leverage: f64, equity: f64 }`
- **關聯程式**: `spot_margin_client.rs:182`

#### get_borrowable_tokens
- **服務**: 查詢可借幣種及最大借幣量。
- **Bybit 路徑**: `GET /v5/spot-margin-uta/max-borrowable`
- **Output**: `Vec<BorrowableToken> { token, max_borrowable, hourly_borrow_rate, borrowed_amount }`
- **關聯程式**: `spot_margin_client.rs:206`

#### get_repay_history
- **服務**: 查詢可還款金額。
- **Bybit 路徑**: `GET /v5/spot-margin-uta/repayment-available-amount`
- **關聯程式**: `spot_margin_client.rs:232`

---

### 1.8 Leverage Tokens — `leverage_token_client.rs`

Rate Group: **Market**。
Client 創建：`LeverageTokenClient::new(client: Arc<BybitRestClient>)`

---

#### get_token_info
- **服務**: 查詢槓桿代幣信息——購買/贖回限額、費率、狀態。
- **Bybit 路徑**: `GET /v5/spot-lever-token/info`
- **Output**: `Vec<LeverageTokenInfo> { lt_coin, lt_name, max_purchase, min_purchase, ... }`
- **關聯程式**: `leverage_token_client.rs:140`

#### get_reference
- **服務**: 查詢槓桿代幣參考數據——淨值、流通量、籃子組成、目標槓桿。
- **Bybit 路徑**: `GET /v5/spot-lever-token/reference`
- **Output**: `Vec<LeverageTokenReference> { lt_coin, nav, circulation, basket, leverage, nav_time }`
- **關聯程式**: `leverage_token_client.rs:164`

#### purchase / redeem
- **服務**: 購買/贖回槓桿代幣。
- **Bybit 路徑**: `POST /v5/spot-lever-token/purchase` / `POST /v5/spot-lever-token/redeem`
- **Input**: `lt_coin: &str, amount/quantity: f64`
- **Output**: `LtPurchaseResult / LtRedeemResult { lt_coin, lt_order_status, exec_qty, exec_amt, lt_order_id }`
- **關聯程式**: `leverage_token_client.rs:195, 226`

---

### 1.9 Instrument Cache — `instrument_info.rs`

非直接 API 調用，而是 instruments-info 的緩存層。
創建：`InstrumentInfoCache::new()`

---

#### refresh
- **服務**: 從 Bybit 拉取並緩存所有交易對的合約規格（精度、限額）。建議啟動時調用一次，之後每 4 小時刷新。
- **Bybit 路徑**: `GET /v5/market/instruments-info`
- **Input**: `client: &BybitRestClient, category: &str`
- **Output**: `BybitResult<usize>`（緩存的交易對數量）
- **關聯程式**: `instrument_info.rs:158`

#### get / round_qty / round_price
- **服務**: 查詢交易對規格、按交易所精度要求取整數量和價格。下單前**必須**調用。
- **調用**: `cache.get(symbol) -> Option<SymbolSpec>` / `cache.round_qty(symbol, qty) -> Option<f64>`
  ```
  SymbolSpec { symbol, base_currency, quote_currency, contract_type,
               qty_step, min_qty, max_qty, tick_size, min_price, max_price,
               min_notional, qty_decimals, price_decimals }
  ```
  方法：`round_qty()`, `round_price()`, `floor_price()`, `ceil_price()`, `validate_order(qty, price) -> (bool, String)`
- **關聯程式**: `instrument_info.rs:198+`

---

## 2. WebSocket

### 2.1 Public WS — `ws_client.rs` + `multi_interval_topics.rs`

連接 URL: `wss://stream{-demo|-testnet|}.bybit.com/v5/public/{category}`
自動重連：指數退避（base 3s, max 60s）。心跳 Ping 每 20 秒。
訂閱分批：每次最多 10 個 topic（Bybit 限制）。

所有事件通過 `mpsc::Sender<PriceEvent>` 發送，可通過 `metadata["type"]` 區分事件類型。

| Topic | metadata.type | 描述 | 關鍵欄位 |
|-------|---------------|------|---------|
| `kline.{interval}.{symbol}` | (無) | 確認 K 線（未確認跳過） | last_price=close, volume_24h=volume |
| `publicTrade.{symbol}` | (無) | 逐筆成交 | last_price=price, volume_24h=volume |
| `orderbook.50.{symbol}` | `orderbook` | 50 檔訂單簿 | bid_price, ask_price, last_price=mid |
| `tickers.{symbol}` | `ticker` | 行情快照 | last_price, volume_24h, bid_price, ask_price |
| ~~`liquidation.{symbol}`~~ | ~~`liquidation`~~ | ~~清算事件~~ | **已移除(2026-04-05)**: Bybit 返回 "handler not found"，毒化整個 WS 連接 |
| ~~`price-limit.{symbol}`~~ | ~~`price_limit`~~ | ~~價格限制更新~~ | **已移除(2026-04-05)**: 同上 |
| ~~`adl-notice.{symbol}`~~ | ~~`adl_notice`~~ | ~~ADL 通知~~ | **已移除(2026-04-05)**: 同上 |

**默認訂閱**（`full_subscription_list`）：kline×6 + ticker + orderbook + publicTrade = **9/symbol**
**擴展訂閱**（`extended_subscription_list`）：= 默認（broken topics 已移除）= **9/symbol**

> **2026-04-05 發現**: Bybit V5 公共 WS 對不存在的 topic 返回 `{"success":false,"ret_msg":"error:handler not found"}`。
> 這會導致**同一連接上所有其他訂閱停止接收數據**（零 tick），但連接和心跳保持正常。極難排查。
> 修復：commit `29fc1ef`，從訂閱列表移除 liquidation/price-limit/adl-notice。

Topic 生成函數（`multi_interval_topics.rs` — 2026-04-19 E5-P2-3 rename）：
- `kline_topics(symbol, intervals)`, `ticker_topic(symbol)`, `orderbook_topic(symbol)`
- `public_trade_topic(symbol)`
- `full_subscription_list(symbols)` / `multi_symbol_subscriptions(symbols)` — 多交易對訂閱字串產生（純函數，無 WsClient 耦合）
- ~~`liquidation_topic()`, `price_limit_topic()`, `adl_notice_topic()`~~ — **已刪除（2026-04-06）**：dead code 連同 `MarketDataMsg::Liquidation` + `flush_liquidations` writer + `extended_subscription_list` 一起清除。`market.liquidations` 表保留為 reserved-for-future。
- ~~`configure_multi_interval(ws, symbols)`~~ — **已刪除（2026-04-19 E5-P2-3）**：零 live caller，`main.rs` 直接用 `full_subscription_list` 驅動。

---

### 2.2 Private WS — `bybit_private_ws.rs`

連接 URL: `wss://stream{-demo|-testnet|}.bybit.com/v5/private`
認證：HMAC-SHA256（GET/realtime + expires）。

**訂閱（環境感知，由 `BybitEnvironment::private_ws_topics()` 決定）**：
- **Mainnet**：`["order", "execution.fast", "position", "wallet", "dcp"]`（`execution.fast` ~50ms）
- **Demo / LiveDemo / Testnet**：`["order", "execution", "position", "wallet", "dcp"]`（demo 端點**不支援** `execution.fast`）

⚠️ **execution.fast 是 mainnet-only 功能**。Bybit demo 對 `execution.fast` 訂閱會返回 `success:true` 但永遠不推送資料 → `total_fills` 永遠為 0。詳見 `gotchas` 第 3 條。2026-04-11 B-2 根因發現。

事件通過 `mpsc::Sender<PrivateWsEvent>` 發送。

| Topic | Event | 描述 | Struct |
|-------|-------|------|--------|
| `order` | `Order(OrderUpdate)` | 訂單狀態變化 | `{ order_id, symbol, side, order_type, price, qty, cum_exec_qty, order_status, ... }` |
| `execution` | `Execution(ExecutionUpdate)` | 標準成交通知（demo/testnet 唯一可用，~300ms） | `{ exec_id, order_id, symbol, side, exec_price, exec_qty, exec_fee, exec_type, exec_time }` |
| `execution.fast` | `Execution(ExecutionUpdate)` | 低延遲成交通知（~50ms，**mainnet-only**） | 同上但精簡：無 `exec_fee` / `exec_value` / `exec_type` / `fee_rate` 欄位（serde default 為空字串） |
| `position` | `Position(PositionUpdate)` | 持倉變化 | `{ symbol, side, size, avg_price, unrealised_pnl, mark_price, liq_price }` |
| `wallet` | `Wallet(WalletUpdate)` | 錢包餘額變化 | `{ account_type, coin: Vec<CoinUpdate { coin, equity, wallet_balance, available_to_withdraw }> }` |
| `dcp` | `DcpTriggered` | DCP 觸發（訂單已被取消） | 無數據，僅信號 |

其他事件：`AuthSuccess`, `AuthFailed(String)`, `Disconnected`

**關聯程式**: `bybit_private_ws.rs` + `execution_listener.rs`（事件消費端）

---

### 2.3 Shadow Order Sync Channel — 影子訂單同步通道

> Session 5 新增（2026-04-04）。Paper Trading 成交鏡像到 Demo API 用於校準驗證。

**用途**: 將 Paper Trading 引擎的模擬成交一對一鏡像到 Bybit Demo API，用於：
1. 驗證 Paper 模擬成交邏輯是否偏離真實 Demo 環境
2. 對比 Paper PnL vs Demo PnL 用於系統校準
3. 為 Live 上線前的數據收集（滑點、填充率、延遲）

**架構**:
```
tick_pipeline.on_tick()
  ├── Step 4: 策略 → intent → process → fill 成功
  │   └── send(ShadowOrderRequest { is_close: false })
  └── Step 6: 止損觸發 → close_position
      └── send(ShadowOrderRequest { is_close: true })

mpsc::UnboundedSender<ShadowOrderRequest> → channel → main.rs async consumer
  └── OrderManager::place_order(CreateOrderRequest)
      └── POST /v5/order/create (Demo API)
```

**ShadowOrderRequest 結構**（`tick_pipeline.rs:37-52`）:
```rust
pub struct ShadowOrderRequest {
    pub symbol: String,       // 交易對
    pub is_long: bool,        // true=Buy, false=Sell（開倉方向）
    pub qty: f64,             // 成交數量
    pub price: f64,           // Paper 成交價格
    pub strategy: String,     // 觸發策略名或 "stop"
    pub paper_fill_ts: u64,   // Paper 成交時間戳 (ms)
    pub is_close: bool,       // true=平倉(reduce_only), false=開倉
}
```

**觸發點**:
| 位置 | 條件 | is_close |
|------|------|----------|
| `tick_pipeline.rs:343-351` | Paper fill 成功（開倉/加倉） | false |
| `tick_pipeline.rs:385-393` | 止損觸發 + close_position | true |

**Demo API 映射**:
- 開倉（is_close=false）: `POST /v5/order/create` — category=linear, side=Buy/Sell, orderType=Market, qty
- 平倉（is_close=true）: `POST /v5/order/create` — side=反向, reduceOnly=true, qty=實際倉位數量
- `orderLinkId`: `"shadow_{paper_fill_ts}"` 用於 WS 回調對比

**一致性保證**:
- Paper qty/price 與 Demo order 一一對應
- Demo API 拒絕（餘額不足、DCP 觸發等）只 warn 不阻塞 Paper Trading
- Demo 成交結果 **不** 回寫 Paper State（單向鏡像）

**配置**:
- `shadow_orders: bool`（默認 false，opt-in 啟用）
- 通道：`tokio::sync::mpsc::UnboundedSender`（非關鍵路徑，不限流）

**已知陷阱**:
1. Demo 帳戶餘額不足時 shadow 訂單會失敗，Paper Trading 不受影響
2. DCP 啟用時，Demo 帳戶斷連會取消所有待成交 shadow 訂單
3. Shadow 訂單為異步提交，實際成交價可能因延遲而與 Paper 成交價偏離
4. `reduce_only=true` 確保平倉 shadow 不會意外開反向倉位
5. Shadow 為 fire-and-forget 模式，Demo 成交結果不回饋到 Paper State

**關聯程式**: `tick_pipeline.rs:37-52, 168, 343-351, 385-393` + `main.rs`（channel consumer）

---

## 3. IPC Methods（Python → Rust）

協議：JSON-RPC 2.0 over Unix domain socket（`/tmp/openclaw/engine.sock`）

| Method | 描述 | Params | Returns |
|--------|------|--------|---------|
| `ping` | 健康檢查 | `{}` | `"pong"` |
| `get_state` | 引擎狀態摘要 | `{}` | `{ status, system_mode, max_open_positions, ws_url, ... }` |
| `reload_config` | 熱加載配置 | `{}` | `{ reloaded: true, path }` |
| `evaluate_strategy` | 策略評估（stub） | `{ symbol }` | `{ status, symbol, ttl_strategist_s: 15 }` |
| `get_risk_check` | H0 風控檢查（stub） | `{ symbol, intent }` | `{ status, passed, message }` |
| `get_paper_state` | Paper trading 狀態 | `{}` | `{ balance, peak_balance, total_realized_pnl, positions, ... }` |
| `get_latest_prices` | 最新價格 | `{}` | `{ "BTCUSDT": 66000.0, ... }` |
| `get_tick_stats` | Pipeline 統計 | `{}` | `{ total_ticks, total_intents, total_fills, total_stops, last_tick_ms }` |

**關聯程式**: Rust `ipc_server.rs` + Python `ipc_client.py` + `ipc_state_reader.py`

---

## 4. 速查表

### 4.1 Rate Limit 分組

| Group | 上限 | 適用路徑 |
|-------|------|---------|
| Order | 10 req/s | `/v5/order/*`, `/v5/execution/*` |
| Position | 10 req/s | `/v5/position/*` |
| Account | 10 req/s | `/v5/account/*` |
| Market | 120 req/s | `/v5/market/*`, `/v5/spot-lever-token/*` |
| Asset | 5 req/s | `/v5/asset/*`, `/v5/spot-margin*` |
| Other | 10 req/s | 其餘 |

分組追蹤：`RateLimitGroup::from_path(path)` 自動分類。
查詢剩餘：`client.is_group_near_limit(group, threshold)` / `client.rate_limit_remaining()`

### 4.2 Error Code

| Code | 名稱 | 含義 | 可重試? | 無操作? |
|------|------|------|--------|--------|
| 0 | Ok | 成功 | - | - |
| 10001 | InvalidParam | 參數無效 | No | No |
| 10002 | InvalidRequest | 請求無效 | No | No |
| 10003 | ApiKeyInvalid | API Key 無效 | No | No |
| 10004 | SignError | 簽名錯誤 | No | No |
| 10005 | PermissionDenied | 權限不足 | No | No |
| 10006 | IpRateLimit | IP 限流 | **Yes** | No |
| 10010 | UnmatchedIp | IP 不匹配 | No | No |
| 110001 | OrderNotFound | 訂單不存在（可能已成交） | No | **Yes** |
| 110009 | PositionNotFound | 持倉不存在 | No | No |
| 110012 | InsufficientBalance | 餘額不足 | No | No |
| 110043 | LeverageNotModified | 槓桿已是目標值 | No | **Yes** |
| 170210 | ExceedMaxQty | 超過最大數量 | No | No |

使用：`BybitRetCode::from_code(ret_code)` → `is_retryable()` / `is_noop()`

### 4.3 已知陷阱

1. **所有數字都是字串** — Bybit 返回 `"65000.50"` 不是 `65000.50`。所有解析器用 `parse_f64()` 處理。
2. **默認環境 = Demo** — `BybitEnvironment::default()` 永遠是 Demo，不會意外打到主網。
3. **execution.fast 是 mainnet-only** — Bybit demo 端點（`stream-demo.bybit.com`）支援的私有 topic 僅為 `order, execution, position, wallet, greeks`，**不包含 `execution.fast`**。對未知 topic 訂閱 Bybit 會回應 `success:true` 但永遠不推送資料 → `total_fills` 永遠為 0 且無任何錯誤訊息（2026-04-11 B-2 根因）。同樣不要同時訂閱 `execution` 和 `execution.fast`，會產生重複 fill 事件。topic 名為 `execution.fast`（含點），不是 `fast-execution`。**正確做法**：用 `BybitEnvironment::private_ws_topics()` 按環境選 topic — demo/testnet/live-demo → `execution`，mainnet → `execution.fast`。
4. **110043 不是錯誤** — `set_leverage` 返回 110043 表示槓桿已設置，代碼視為成功。
5. **confirm-mmr 替代 set-risk-limit** — 舊端點 `/v5/position/set-risk-limit` 已被 Bybit 移除。
6. **subscribe 批次大小** — Spot 每次最多 10 topics；Linear 無硬性限制（總字元上限 21,000）。代碼保守地分批 10 個。
6b. **broken topic 毒化連接** — 訂閱不存在的 topic（如 liquidation/price-limit/adl-notice）返回 "handler not found"，會導致整個連接零數據。連接和心跳正常但無行情。已在 `29fc1ef` 移除。
7. **DCP 必須配置** — 不配置 DCP 意味著斷連後掛單持續有效，風險極高。
8. **recv_window = 5000ms** — 本地與 Bybit 時差超過 5 秒會被拒簽。
9. **Instrument cache 需定期刷新** — Bybit 偶爾調整合約精度/限額，建議每 4 小時 refresh 一次。
10. **pre_check_order 不是真正的預檢** — Bybit 無專門端點，代碼用 POST /v5/order/create 模擬。

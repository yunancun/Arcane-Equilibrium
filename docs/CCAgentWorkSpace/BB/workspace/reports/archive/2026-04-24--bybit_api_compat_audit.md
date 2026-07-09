# BB — Bybit V5 API 兼容性審計報告（2026-04-24）

**Auditor**：BB (Bybit Broker Compatibility Auditor)
**Baseline commits**：engine lib 1980 / 0 failed（參考 CLAUDE.md §十一）
**Scope**：所有 Bybit V5 REST + WS 調用點 vs 官方 V5 規範 + 內部字典 `docs/references/2026-04-04--bybit_api_reference.md` 字典
**Methodology**：純靜態審計（not hitting real API）；對比 Rust `openclaw_engine` 與 Python `control_api_v1` + helper_scripts 調用面

---

## 0. TL;DR — 三句話

1. **核心交易路徑（order / position / wallet / execution）REST + Private WS 接線與 Bybit V5 規範一致**；HMAC-SHA256 簽名、header set（`X-BAPI-API-KEY / -SIGN / -TIMESTAMP / -RECV-WINDOW`）、recv_window=5000ms、環境切換（Demo/Testnet/Mainnet/LiveDemo）、LIVE-GUARD-1 三閘全部落地 — 單一真實實作位於 Rust，Python httpx drop-in 行為對齊。
2. **字典手冊有 1 個**實質錯誤（`confirm-mmr` vs `confirm-pending-mmr`）、**2 個**小幅 drift（`get_open_interest` 參數名稱 / `get_long_short_ratio` period 值域）、**10+ 個**欄位未記（見 §7）；代碼為 SSOT，字典手冊**應同步更新**。
3. **無 Critical 實作 bug**；2 個 **Medium** 需注意（helper_scripts 有 2 個遺留 public smoke test 仍指 mainnet `stream.bybit.com` 硬編碼 URL；legacy read_only slot 路徑殘留）；4 個 **Low / Advisory**（優化建議）。

---

## 1. 調用點盤點

### 1.1 Rust — `openclaw_engine` REST 客戶端家族

| 模組 | 文件 | 行數 | 端點數 | 主要職責 |
|---|---|---:|---:|---|
| BybitRestClient | `rust/openclaw_engine/src/bybit_rest_client.rs` | 1725 | — | HMAC 簽名 / GET/POST / 環境切換 / LIVE-GUARD-1 / rate limit 分組 / retCode 分類器 |
| OrderManager | `rust/openclaw_engine/src/order_manager.rs` | — | 8 | place / cancel / cancel_by_link_id / cancel_all / amend / realtime / history / executions |
| PositionManager | `rust/openclaw_engine/src/position_manager.rs` | — | 8 | list / set_leverage / trading_stop / switch_mode / confirm_pending_mmr / set_auto_add_margin / add_margin / closed_pnl |
| AccountManager | `rust/openclaw_engine/src/account_manager.rs` | — | 7 | wallet_balance / fee_rate / info / set_hedging_mode / borrow_history / repay |
| PlatformClient | `rust/openclaw_engine/src/platform_client.rs` | — | 13 | transaction_log / margin_mode / collateral / DCP (set/get) / inter_transfer / coin_info / demo-apply-money |
| MarketDataClient | `rust/openclaw_engine/src/market_data_client/mod.rs` | — | 14 | time / kline / tickers / orderbook / OI / funding / LSR / risk_limit / insurance / recent_trades / vol / price_limit |
| InstrumentInfoCache | `rust/openclaw_engine/src/instrument_info.rs` | — | 1 | instruments-info（pagination + singleflight） |
| BatchOrderManager | `rust/openclaw_engine/src/batch_order_manager.rs` | — | 3 | create/amend/cancel batch |
| SpotMarginClient | `rust/openclaw_engine/src/spot_margin_client.rs` | — | 6 | UTA margin switch / set-leverage / status / borrowable / repayment-available |
| LeverageTokenClient | `rust/openclaw_engine/src/leverage_token_client.rs` | — | 4 | lt_info / reference / purchase / redeem |
| BybitPrivateWs | `rust/openclaw_engine/src/bybit_private_ws.rs` | 1013 | — | HMAC WS auth / order / execution / position / wallet / dcp / reconnect |
| WsClient (public) | `rust/openclaw_engine/src/ws_client.rs` | 1136 | — | kline / publicTrade / orderbook / tickers / liquidation* / price-limit* / adl-notice*（*：parser 保留但**不訂閱**） |
| PrivateWsStatusWriter | `rust/openclaw_engine/src/bybit_private_ws_status_writer.rs` | 604 | — | 每 5s 寫狀態 JSON 供 observer；2026-04-23 takeover Python listener |
| PositionReconciler | `rust/openclaw_engine/src/position_reconciler/mod.rs` | — | 1 | 30s 輪詢 `/v5/position/list` 做 drift 檢測 |
| RestPoller (market) | `rust/openclaw_engine/src/database/rest_poller.rs` | — | 3 | funding 15min / OI 5min / LSR 15min |

### 1.2 Python — `program_code/.../control_api_v1/app/`

| 文件 | 端點 / URL | 職責 |
|---|---|---|
| `bybit_rest_client.py` | 7 methods（drop-in for PyO3 legacy） | httpx sync client：wallet-balance / instruments-info / position/list / order/realtime / execution/list / order/create / order/cancel |
| `settings_routes.py` | `GET /v5/user/query-api` | key validation 端點（每次 key 寫入前驗簽） |
| `backtest_routes.py` | `GET /v5/market/kline` | 回測 OHLCV fallback（公開 API，無簽名） |
| `symbol_category_registry.py` | `GET /v5/market/instruments-info` | Symbol→category 啟動 cache（僅被測試用，main.py 已 DEAD-PY-2 解除 runtime wiring） |
| `bybit_demo_connector.py` | —（無 API 調用） | 僅 `round_qty_for_exchange` + `round_price_for_exchange` 兩個純工具函數 |
| `strategy_ai_routes.py` / `live_session_routes.py` | 透過 `BybitClient` | Live 系統狀態查詢（/live/orders /live/fills） |

### 1.3 `program_code/.../io_and_persistence/`

| 文件 | URL | 用途 | 狀態 |
|---|---|---|---|
| `bybit_public_microstructure_builder.py` | `/v5/market/orderbook`, `/v5/market/recent-trade`, `/v5/market/kline`（base_url 可 env 覆蓋） | H0 觀察面快照 | 活躍 |
| `bybit_public_connectivity_check.py` | `https://api.bybit.com/v5/market/time`, `/v5/market/tickers` | 連通性冒煙 | **硬編碼 mainnet**（見 §6 M-2） |
| `bybit_private_ws_smoke_test.py` | `wss://stream.bybit.com/v5/private` | Private WS 冒煙 | **硬編碼 mainnet + 使用 legacy `read_only` slot**（見 §6 M-3） |
| `bybit_private_ws_smoke_test_v2.py` | `wss://stream.bybit.com/v5/private` | 同上 v2 | 同上 |

### 1.4 helper_scripts

| 路徑 | 類別 | 備註 |
|---|---|---|
| `helper_scripts/clean_restart_flatten.py` | 直接使用 Python `BybitClient` 的 `get_active_orders`/`cancel_order`/`place_order` | 重啟時平倉輔助 |
| `helper_scripts/maintenance_scripts/bybit_connector/` | 無活躍 Bybit API 調用 — 僅 `_bybit_latest_wrapper.py`（trading env loader） + 2 個 shim shell | 98 legacy shell 已於 2026-04-23 DEDUP-PY-RUST D 刪除 |
| 各 `ctl.sh` / `*_bootstrap.sh` | 均不打 Bybit API；只做 systemd/launchd 服務管理 | — |

---

## 2. REST 端點逐條驗證（字典 vs 代碼 vs Bybit V5 規範）

格式：`Endpoint | 調用點 | Method/URL 正確 | Body/Params 正確 | retCode 處理 | 字典有無 drift | 嚴重性 | 建議`

### 2.1 Market Data（Rate Group: Market 120 req/s）

| Endpoint | 調用點 | URL✓ | Params✓ | retCode✓ | 字典 drift | Sev | 建議 |
|---|---|---|---|---|---|---|---|
| GET /v5/market/time | `market_data_client/mod.rs:60` | ✅ | ✅ 無 | ✅ | — | — | — |
| GET /v5/market/kline | `market_data_client/mod.rs:118`, `backtest_routes.py:140` | ✅ | ✅ `category/symbol/interval/start/end/limit` | ✅ | — | — | — |
| GET /v5/market/mark-price-kline | `market_data_client/mod.rs:348`（見 ref） | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/market/premium-index-price-kline | 同上 | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/market/index-price-kline | 同上 | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/market/tickers | `market_data_client/mod.rs:143`, `bybit_public_connectivity_check.py:44` | ✅ | ✅ `category/symbol` | ✅ | — | — | — |
| GET /v5/market/orderbook | `market_data_client/mod.rs:171`, `bybit_public_microstructure_builder.py:420` | ✅ | ✅ `category/symbol/limit` | ✅ | — | — | — |
| GET /v5/market/open-interest | `market_data_client/mod.rs:203` | ✅ | ✅ **`intervalTime`**（非 `interval`） | ✅ | **L-1** 字典寫 `interval`，應記 `intervalTime` | Low | 更新字典 |
| GET /v5/market/funding/history | `market_data_client/mod.rs:257` | ✅ | ✅ `startTime`/`endTime`（非 `start`/`end`） | ✅ | — | — | — |
| GET /v5/market/account-ratio | `market_data_client/mod.rs:303` | ✅ | ✅ `category/symbol/period/limit` | ✅ | **L-2** 字典列 `"1d"` 為合法 period；Bybit V5 僅支援 `5min/15min/30min/1h/4h/4d`（無 `1d`） | Low | 更正字典 period 值域 |
| GET /v5/market/risk-limit | `market_data_client/mod.rs:339` | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/market/insurance | `market_data_client/mod.rs:377` | ✅ | ✅ optional `coin` | ✅ | — | — | — |
| GET /v5/market/recent-trade | `market_data_client/mod.rs:421`, `bybit_public_microstructure_builder.py:433` | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/market/historical-volatility | `market_data_client/mod.rs:471` | ✅ | ✅ `category/period/limit` | ✅ | — | — | — |
| GET /v5/market/delivery-price | 見字典 §1.1（未在活躍路徑）| ✅ | ✅ | ✅ | — | — | — |
| GET /v5/market/price-limit | `market_data_client/mod.rs:506` — **實際查 `/v5/market/instruments-info`** 派生 max/min price | ✅（字典已註明 fallback） | ✅ | ✅ | — | — | — |
| GET /v5/market/instruments-info | `instrument_info.rs:352` + `bybit_rest_client.py:563` + `symbol_category_registry.py:163` + `market_data_client/mod.rs:506` | ✅ | ✅ `category/limit/cursor` | ✅ | — | — | — |
| GET /v5/market/adl-alert | `market_data_client/mod.rs` (in ref §1.1, line 680) | ✅ | ✅ | ✅ | — | — | — |

### 2.2 Orders（Rate Group: Order 20 req/s — 字典 §4.1 已更正）

| Endpoint | 調用點 | URL✓ | Body✓ | retCode✓ | 字典 drift | Sev | 建議 |
|---|---|---|---|---|---|---|---|
| POST /v5/order/create | `order_manager.rs:422` + `bybit_rest_client.py:788` | ✅ | ✅ category/symbol/side/orderType/qty + optional price/timeInForce/reduceOnly/closeOnTrigger/orderLinkId/triggerPrice/triggerDirection/takeProfit/stopLoss/tpTriggerBy/slTriggerBy | ✅ `is_balance_block` / `is_instrument_filter` / `is_exchange_backoff` 完整分類 | — | — | — |
| POST /v5/order/cancel (by orderId) | `order_manager.rs:452`, `bybit_rest_client.py:674` | ✅ | ✅ | ✅ `is_noop` 涵蓋 110001/110008/110010 | — | — | — |
| POST /v5/order/cancel (by orderLinkId) | `order_manager.rs:300` + `cancel_by_link_id_raw` 共用 | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/order/cancel-all | `order_manager.rs:503` | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/order/amend | `order_manager.rs:561` | ✅ | ✅ optional orderId/orderLinkId + qty/price/triggerPrice/takeProfit/stopLoss | ✅ | — | — | — |
| GET /v5/order/realtime | `order_manager.rs:585`, `bybit_rest_client.py:647` | ✅ | ✅ category + optional symbol（Python 加 `settleCoin=USDT` 當 symbol 缺）| ✅ | **A-1** Rust `get_active_orders` 未傳 `settleCoin`；當 symbol=None 時 Bybit 會要求 symbol/settleCoin/orderId/orderLinkId 至少一個，Rust 目前依賴 caller 傳入 symbol；但字典 §1.2 未標明此約束 | Advisory | Rust 面加一個 settleCoin fallback 或在 docstring 警告 symbol=None 會被 Bybit 拒 |
| GET /v5/order/history | `order_manager.rs:609` | ✅ | ✅ | ✅ | 同 A-1 | Advisory | 同上 |
| GET /v5/execution/list | `order_manager.rs:633`, `bybit_rest_client.py:696` | ✅ | ✅ Rust未帶 settleCoin，Python 帶 `settleCoin=USDT` | ✅ | 同 A-1 | Advisory | 同上 |
| POST /v5/order/create-batch | `batch_order_manager.rs:176` | ✅ | ✅ ≤10 筆 | ✅ | — | — | — |
| POST /v5/order/amend-batch | `batch_order_manager.rs:262` | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/order/cancel-batch | `batch_order_manager.rs:333` | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/order/disconnected-cancel-all (DCP set) | `platform_client.rs:329` | ✅ | ✅ `timeWindow`（秒） | ✅ | — | — | — |

### 2.3 Positions（Rate Group: Position 20 req/s）

| Endpoint | 調用點 | URL✓ | Body✓ | retCode✓ | 字典 drift | Sev | 建議 |
|---|---|---|---|---|---|---|---|
| GET /v5/position/list | `position_manager.rs:164`, `bybit_rest_client.py:618`, `position_reconciler/mod.rs` | ✅ | ✅ category + (symbol OR settleCoin=USDT) | ✅ | — | — | — |
| POST /v5/position/set-leverage | `position_manager.rs:203` | ✅ | ✅ `buyLeverage`/`sellLeverage` 為字串 | ✅ 110043 → Ok（冪等） | — | — | — |
| POST /v5/position/trading-stop | `position_manager.rs:260` | ✅ | ✅ takeProfit/stopLoss/tpTriggerBy/slTriggerBy/trailingStop/activePrice/positionIdx | ✅ | — | — | — |
| POST /v5/position/switch-mode | `position_manager.rs:295` | ✅ | ✅ mode=0/3 | ✅ | — | — | — |
| POST /v5/position/confirm-pending-mmr | `position_manager.rs:335` | ✅（實機路徑） | ✅ | ✅ | **H-1** 字典 §1.4 / §4.3 寫 `/v5/position/confirm-mmr`，實機路徑為 `/v5/position/confirm-pending-mmr`；代碼為 SSOT，已於 FIX-56/BB-A1 修正 | High（字典錯誤） | **更正字典 §1.4 + §4.3** |
| POST /v5/position/set-auto-add-margin | `position_manager.rs:375` | ✅ | ✅ `autoAddMargin: int`, `positionIdx: Option<int>` | ✅ | — | — | — |
| POST /v5/position/add-margin | `position_manager.rs:412` | ✅ | ✅ `margin` 字串 | ✅ | — | — | — |
| GET /v5/position/closed-pnl | `position_manager.rs:440` | ✅ | ✅ | ✅ | — | — | — |

### 2.4 Account（Rate Group: Account 20 req/s）

| Endpoint | 調用點 | URL✓ | Body/Params✓ | retCode✓ | 字典 drift | Sev | 建議 |
|---|---|---|---|---|---|---|---|
| GET /v5/account/wallet-balance | `account_manager.rs:185`, `bybit_rest_client.py:495` | ✅ | ✅ `accountType=UNIFIED` | ✅ | — | — | — |
| GET /v5/account/fee-rate | `account_manager.rs:260` | ✅ | ✅ `category` | ✅ | — | — | — |
| GET /v5/account/info | `account_manager.rs:347` | ✅ | ✅ 無 | ✅ | — | — | — |
| POST /v5/account/set-hedging-mode | `account_manager.rs:376` | ✅ | ✅ `hedging: "ON"/"OFF"` | ✅ | — | — | — |
| GET /v5/account/borrow-history | `account_manager.rs:402` | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/account/repay | `account_manager.rs:424` | ✅ | ✅ `coin` | ✅ | — | — | — |
| GET /v5/account/transaction-log | `platform_client.rs:210` | ✅ | ✅ `accountType/category/startTime/endTime/limit` | ✅ | — | — | — |
| POST /v5/account/set-margin-mode | `platform_client.rs:246` | ✅ | ✅ `setMarginMode` | ✅ | — | — | — |
| GET /v5/account/collateral-info | `platform_client.rs:270` | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/account/set-collateral | `platform_client.rs:312` | ✅ | ✅ `coin/collateralSwitch: "ON"/"OFF"` | ✅ | — | — | — |
| GET /v5/account/dcp-info | `platform_client.rs:340` | ✅ | ✅ 無 | ✅ | — | — | — |
| POST /v5/account/demo-apply-money | `platform_client.rs:558` | ✅ | ✅ | ✅ | — | — | — |

### 2.5 Asset（Rate Group: Asset 5 req/s）

| Endpoint | 調用點 | URL✓ | Body/Params✓ | retCode✓ | 字典 drift | Sev | 建議 |
|---|---|---|---|---|---|---|---|
| POST /v5/asset/transfer/inter-transfer | `platform_client.rs:401` | ✅ | ✅ `transferId/coin/amount/fromAccountType/toAccountType` | ✅ | — | — | — |
| GET /v5/asset/transfer/query-inter-transfer-list | `platform_client.rs:425` | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/asset/transfer/query-account-coins-balance | `platform_client.rs:467` | ✅ | ✅ `accountType` | ✅ | — | — | — |
| GET /v5/asset/coin-info | `platform_client.rs:502` | ✅ | ✅ optional `coin` | ✅ | — | — | — |

### 2.6 Spot Margin UTA（Rate Group: Asset 5 req/s）

| Endpoint | 調用點 | URL✓ | Body/Params✓ | retCode✓ | 字典 drift | Sev | 建議 |
|---|---|---|---|---|---|---|---|
| GET /v5/spot-margin-trade/data | `spot_margin_client.rs:113` | ✅（公開端點保留） | ✅ | ✅ | — | — | — |
| POST /v5/spot-margin-uta/switch-mode | `spot_margin_client.rs:141` | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/spot-margin-uta/set-leverage | `spot_margin_client.rs:165` | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/spot-margin-uta/status | `spot_margin_client.rs:182` | ✅ | ✅ 無 | ✅ | — | — | — |
| GET /v5/spot-margin-uta/max-borrowable | `spot_margin_client.rs:206` | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/spot-margin-uta/repayment-available-amount | `spot_margin_client.rs:232` | ✅ | ✅ | ✅ | — | — | — |

### 2.7 Leverage Tokens（Rate Group: Market）

| Endpoint | 調用點 | URL✓ | Body✓ | retCode✓ | 字典 drift | Sev | 建議 |
|---|---|---|---|---|---|---|---|
| GET /v5/spot-lever-token/info | `leverage_token_client.rs:140` | ✅ | ✅ | ✅ | — | — | — |
| GET /v5/spot-lever-token/reference | `leverage_token_client.rs:164` | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/spot-lever-token/purchase | `leverage_token_client.rs:195` | ✅ | ✅ | ✅ | — | — | — |
| POST /v5/spot-lever-token/redeem | `leverage_token_client.rs:226` | ✅ | ✅ | ✅ | — | — | — |

### 2.8 User（Key Validation）

| Endpoint | 調用點 | URL✓ | Params✓ | retCode✓ | 字典 drift | Sev | 建議 |
|---|---|---|---|---|---|---|---|
| GET /v5/user/query-api | `settings_routes.py:230` | ✅ | ✅ 無 query，header 簽名空字串 | ✅ | **L-3** 字典未記此端點（Python 獨有，用於 key validation） | Low | 字典補錄，標「Python-only, key validation path」 |

---

## 3. WebSocket 驗證

### 3.1 Public WS — `ws_client.rs`（1136 行）

| 項目 | 代碼狀態 | 規範對齊 |
|---|---|---|
| URL | 從 `config.ws_url` 讀取，default `wss://stream.bybit.com/v5/public/linear`（`config/mod.rs:166`） | ✅ |
| 訂閱 | kline / publicTrade / orderbook.50 / tickers（環境感知） | ✅ 對齊 Bybit V5 §7.2 |
| 批次上限 | `SUBSCRIBE_BATCH_SIZE = 10` + 500ms 批次間隔 | ✅ 對齊 Bybit spot 10/batch 限制（linear 無硬限但保守） |
| Ping 間隔 | 從 `config.heartbeat_interval_ms` 讀取 | ✅ |
| 重連 | 指數退避 `BackoffConfig::ws_public_default` + 15s connect timeout | ✅ |
| Runtime 訂閱調整 | `WsTopicChange::Subscribe/Unsubscribe` channel（ScannerRunner 用） | ✅ |
| liquidation / price-limit / adl-notice | **parser 保留但訂閱列表已移除**（字典 §2.1 已註明「2026-04-05 發現 handler not found → 毒化連接」） | ✅ |
| orderbook 解析 | best bid/ask + top-5 levels + mid price | ✅ |
| ticker 欄位 | lastPrice / volume24h / bid1Price / ask1Price / fundingRate / indexPrice / openInterest（拒 NaN/Inf/負值） | ✅ |
| 訂閱後 response 處理 | `success/ret_msg` 記錄 — 但僅記 info/debug 級，不終止連接 | ⚠ **L-4**：先前 2026-04-05 事件發現訂閱未知 topic 會「success:false + handler not found」且毒化連接。目前 `process_message` 只 debug!+continue。建議增加 `ret_msg.contains("handler not found")` 時 warn!+強制 reconnect |

### 3.2 Private WS — `bybit_private_ws.rs`（1013 行）

| 項目 | 代碼狀態 | 規範對齊 |
|---|---|---|
| URL | 從 `BybitEnvironment::private_ws_url()`：`wss://stream[-demo\|-testnet\|].bybit.com/v5/private` | ✅ |
| Auth | HMAC-SHA256(`api_secret`, `"GET/realtime" + expires_ms`)；`expires = now_ms + 10_000` | ✅ 對齊 §認證 |
| Auth args 順序 | `[api_key, expires_str, signature]` | ✅ |
| Auth timeout | 10s；逾時 → AuthFailed + 重連 | ✅ |
| 訂閱 topics | `BybitEnvironment::private_ws_topics()` 環境感知：Demo/Testnet/LiveDemo=`[order, execution, position, wallet]`；Mainnet=`[order, execution.fast, position, wallet, dcp]` | ✅ **關鍵**：對齊 2026-04-11 B-2 根因發現（demo 無 execution.fast + dcp；字典 §2.2 已註明） |
| Ping 間隔 | 20s（`PING_INTERVAL_MS`） | ✅ |
| 重連 | `BackoffConfig::ws_private_default()`（3s base / 60s cap / x2） | ✅ |
| 訂閱 confirmation log | `op==subscribe && !success` → `error!`，避免 B-2 靜默失敗 | ✅ |
| 拒絕原因字串 | `OrderUpdate.reject_reason` 解析完整，5 個 canonical 字串（EC_PostOnlyWillTakeLiquidity / EC_PerCancelRequest / EC_CancelForNoFullFill / EC_ReachMaxPendingOrders / EC_Others） | ✅ 對齊字典 §4.2.1 |
| 解析 `execution.fast` | 重用 `ExecutionUpdate`；serde default 對缺失欄位→ "" | ✅ 字典 §2.2 已註明 |
| DCP 事件 | 解析為 `PrivateWsEvent::DcpTriggered`（info! 告警，**僅 mainnet 才訂閱**） | ✅ |

### 3.3 Status Writer — `bybit_private_ws_status_writer.rs`（604 行）

| 項目 | 代碼狀態 |
|---|---|
| 產出路徑 | `$OPENCLAW_SRV_ROOT/docker_projects/trading_services/connector_logs/bybit/ws_persistent/bybit_private_ws_listener_status_latest.json` |
| 產出間隔 | 5s（`DEFAULT_WRITE_INTERVAL_SEC`） |
| 對 observer 契約 | `listener_type/listener_version("rust-v1")/session_ts_ms/started_ts_ms/ws_url/topics_requested/running/message_count/topic_message_count{order,execution,position,wallet}/auth_ok_count/disconnect_count/last_event_ts_ms/engine_mode` |
| 取代來源 | 2026-04-23 `b5cf59e` + `b9b0a57` 完成 takeover Python `bybit_private_ws_listener.py`（已刪除） |
| 原子寫入 | `tmp + fsync + rename`（observer 永不看半寫狀態） |
| Cancel 行為 | 收 cancel → 最後一次寫 `running=false` 讓 observer 看到乾淨收尾 | 

**結論**：Rust takeover 正確覆蓋 Python listener 對 observer 的契約面；字典 §2 應新增此子章節（見 §7 字典 drift 建議）。

---

## 4. 環境區分（Mainnet vs Testnet vs Demo vs LiveDemo）

### 4.1 `BybitEnvironment` enum + URL 表（`bybit_rest_client.rs:67-143`）

| Env | REST Base | Private WS | Secret Slot |
|---|---|---|---|
| Demo | `https://api-demo.bybit.com` | `wss://stream-demo.bybit.com/v5/private` | `demo` |
| Testnet | `https://api-testnet.bybit.com` | `wss://stream-testnet.bybit.com/v5/private` | `demo` |
| Mainnet | `https://api.bybit.com` | `wss://stream.bybit.com/v5/private` | `live` |
| LiveDemo | `https://api-demo.bybit.com` | `wss://stream-demo.bybit.com/v5/private` | `live` |

- Default 為 `Demo`（`bybit_rest_client.rs:145-149`）— 對齊字典 §4.3 陷阱 #2「不會意外打到主網」✅
- Python mirror：`bybit_rest_client.py:95-112` 有相同表 + `"live"` alias 對到 mainnet✅

### 4.2 LIVE-GUARD-1 三閘（Rust + Python 對稱）

| Gate | Rust 實作 | Python 實作 | 狀態 |
|---|---|---|---|
| #1 `OPENCLAW_ALLOW_MAINNET=1` | `bybit_rest_client.rs:525-537`（`!= "1"` → Err） | `bybit_rest_client.py:249-260`（同） | ✅ 對齊 |
| #2 Env var fallback 封閉（Mainnet） | `bybit_rest_client.rs:543-572`（`is_mainnet` 時 skip env var） | `bybit_rest_client.py:181-200`（`if key is None and not is_mainnet` 才讀 env） | ✅ 對齊 |
| #3 憑證空 fail-closed | `bybit_rest_client.rs:574-587`（Mainnet 空 → Err；非 Mainnet → warn） | `bybit_rest_client.py:262-283`（同） | ✅ 對齊 |

### 4.3 LiveDemo 不因 endpoint 降級（CLAUDE.md §四 Gate #5 + memory `feedback_live_no_degradation_by_endpoint.md`）

- `BybitEnvironment::LiveDemo` 使用 live slot credentials + demo server — **身分/auth 仍為 Live 標準**（secret_slot=`live`，TTL/HMAC/authorization.json 全套用）
- Private WS topics：LiveDemo 依 demo 可用 topic（`order/execution/position/wallet`），**不訂閱 execution.fast/dcp** — 這是 demo 端點技術限制非降級
- 結論：**代碼已正確區分「demo endpoint 技術限制」 vs 「authorization 降級」**，符合 memory 指令 ✅

### 4.4 認證路徑（SEC-17 / 2026-04-18 LIVE-GATE-BINDING-1）

- authorization.json HMAC 簽名驗證 + 5min re-verify：`rust/openclaw_engine/src/live_authorization.rs`
- env var `OPENCLAW_ALLOW_MAINNET=1` 僅為 Rust 側 Mainnet 硬鎖，**LiveDemo 不受 env var 硬鎖影響**（LiveDemo 使用 demo endpoint，不觸發 mainnet 條件）
- Python 側已對齊：`bybit_rest_client.py:251` 的 `is_mainnet` 檢查僅在 `env == "mainnet"` 時觸發，不影響 live_demo

---

## 5. FA-PHANTOM-1 / 參數誤用回歸

**背景**：2026-04-14 發現 `fast_track` 誤把 `notional/balance` 當成 `margin_util`（90% < 設計 100%），所有策略被全平。修復後需檢查殘留。

| 檢查項 | 位置 | 結果 |
|---|---|---|
| `margin_util` 計算 | `rust/openclaw_engine/src/strategies/**`（audit 範圍外） | **out of BB scope**（FA 已結案） |
| Bybit API 層 `notional` / `balance` / `margin` 混用 | `position_manager.rs`（`add_margin`, `set_auto_add_margin`） + `account_manager.rs`（`wallet-balance`） | ✅ 代碼層面 `margin: f64` 與 `balance: f64` 有獨立欄位，無 phantom 混用 |
| `reduceOnly` / `closeOnTrigger` 混用 | `order_manager.rs:381-386` | ✅ 兩 flag 獨立，都透傳到 Bybit |
| `positionIdx` 傳遞 | `position_manager.rs:250,364,401`（trading_stop / set_auto_add_margin / add_margin） | ✅ Option<i32>，缺省則不傳 |
| `orderType` 字串 | `order_manager.rs` 使用 `OrderType::{Market,Limit}` enum `as_str()` → `"Market"/"Limit"` | ✅ |
| `timeInForce` 字串 | 同上，`TimeInForce::{GTC,IOC,FOK,PostOnly}` → `"GTC"/"IOC"/"FOK"/"PostOnly"` | ✅ |
| Python `place_order` body 構造 | `bybit_rest_client.py:743-790` | ✅ 與 Rust 契約一致（category/symbol/side/orderType/qty/price/timeInForce/reduceOnly/closeOnTrigger/orderLinkId/triggerPrice/triggerDirection/takeProfit/stopLoss） |

**結論**：Bybit API 層**無 FA-PHANTOM 殘留**。參數傳遞字串/boolean/int 類型一致，不存在跨層概念混淆。

---

## 6. Critical / High / Medium 發現章節

### 6.1 Critical — 0 項

無。核心交易路徑（order/position/account/market REST + Private WS auth/subscribe）全部符合 Bybit V5 規範，無需 rebuild 或 ship-stop。

### 6.2 High — 1 項

#### H-1：字典手冊 `confirm-mmr` 路徑已過期

**位置**：`docs/references/2026-04-04--bybit_api_reference.md:555` 與 `:1145`
**實情**：代碼（`position_manager.rs:335`）已於 2026-04-12 `FIX-56/BB-A1` 更正為 `/v5/position/confirm-pending-mmr`，完整歷史見 `docs/audits/2026-04-12--full_program_chain_audit.md:4857`
**字典內容**：仍寫 `POST /v5/position/confirm-mmr`（缺 `pending-`）
**影響**：字典讀者可能照舊錯誤路徑重寫新模組；live pipeline 本身無影響（未走 confirm_pending_mmr hot path）
**建議**：下一次 E1/E2 維護週期把 §1.4 `confirm_pending_mmr` + §4.3 陷阱 #5 兩處的路徑更正為 `/v5/position/confirm-pending-mmr`

### 6.3 Medium — 3 項

#### M-1：`ws_client.rs::process_message` 對 "handler not found" 無 warn 升級

**位置**：`rust/openclaw_engine/src/ws_client.rs:362-366`
**實情**：`if parsed.get("op").is_some() || parsed.get("success").is_some()` 條件下，所有 control message 走 `debug!` 後 `return true`
**風險**：先前 2026-04-05 事件發現訂閱錯 topic（liquidation/price-limit/adl-notice）Bybit 回 `success:false + "handler not found"` 並毒化整個連接（零 tick 不 disconnect）。目前雖透過 subscription list 移除不再主動觸發，但若未來有 runtime 動態訂閱錯誤 topic（WsTopicChange），會再次靜默毒化
**建議**：process_message 增加
```rust
if let Some(msg) = parsed.get("ret_msg").and_then(|v| v.as_str()) {
    if msg.contains("handler not found") || msg.contains("topic does not exist") {
        error!(topic = ?parsed.get("args"), "⚠ Bybit handler not found — connection poisoning risk, forcing reconnect");
        return false; // force outer loop to break+reconnect
    }
}
```
對稱 Private WS 端 `bybit_private_ws.rs:544-564` 已有 `error!` log 但也沒強制 disconnect — 同樣建議加。

#### M-2：`bybit_public_connectivity_check.py` 硬編碼 Mainnet URL

**位置**：`program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_public_connectivity_check.py:8`
**實情**：`BASE_URL = "https://api.bybit.com"` 寫死
**風險**：
1. Mac dev 模式 Mainnet 受 LIVE-GUARD-1 gate 鎖，但此腳本為公開 endpoint 不需簽名 → 仍會連 mainnet（雖然是讀，但違反「跨平台相容 §七.★★」路徑/URL 不硬編碼原則）
2. 未通過 `BybitEnvironment` 抽象層 — 未來若 Bybit 調整 demo/testnet endpoint 此腳本會獨立飄移
**建議**：引入 env var `BYBIT_PUBLIC_BASE_URL`（預設 `https://api.bybit.com`），或改呼 `bybit_rest_client.py` 的 public endpoint helper

#### M-3：`bybit_private_ws_smoke_test.py` + v2 用 legacy `read_only` secret slot

**位置**：`program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_ws_smoke_test.py:14-15`（v2 同）
**實情**：`API_KEY_PATH = .../secret_files/bybit/read_only/api_key` + `WS_URL = "wss://stream.bybit.com/v5/private"` 硬編碼
**風險**：
1. `read_only` slot 不在 `BybitEnvironment::secret_slot()` 表（當前僅 `demo`/`live`），意味這兩個 smoke test 走獨立 key 命名空間；operator 若誤信此路徑管理 key 會與正式 `demo`/`live` slot 脫節
2. 硬編碼 `stream.bybit.com/v5/private` = 純 mainnet — demo 環境跑會用錯 ws 端點
**建議**：
- 評估是否刪除（smoke test 為一次性工具，現有 Rust `bybit_private_ws_status_writer` 已產業務可觀察的 JSON，smoke test 用處不大）
- 若保留，改用 `OPENCLAW_SECRETS_DIR/{demo|live}/api_key` + 環境變數 `BYBIT_WS_URL`

### 6.4 Low / Advisory — 5 項

| ID | 位置 | 內容 | 優先級 |
|---|---|---|---|
| L-1 | 字典 §1.1 get_open_interest Input | 寫 `interval` 應為 `intervalTime`；代碼為 SSOT 正確 | 字典更新 |
| L-2 | 字典 §1.1 get_long_short_ratio Input period 值域 | 列 `"1d"` 為合法；Bybit 實際僅 `5min/15min/30min/1h/4h/4d` | 字典更新 |
| L-3 | 字典完全缺 `/v5/user/query-api` | Python settings_routes.py:100 使用 — 應補錄「Python-only, key validation」 | 字典補錄 |
| L-4 / M-1 | `ws_client.rs::process_message` 未升級 "handler not found" | 見 §6.3 M-1 | 代碼加強 |
| A-1 | Rust `order_manager.rs` `get_active_orders/history/executions` 未傳 settleCoin | 當 caller symbol=None 且未傳 orderId/orderLinkId 會被 Bybit 拒（10001）；Python 端已用 settleCoin fallback。建議 Rust docstring 加警告或同步加 settleCoin fallback 對稱 | 優化 |

---

## 7. 字典手冊 ↔ 實作 drift 清單

### 7.1 字典有記但實作未用

| 字典位置 | 端點/內容 | 實作狀態 |
|---|---|---|
| §1.1 delivery-price | GET /v5/market/delivery-price | 代碼有（`market_data_client/mod.rs:822` 在 ref 索引），但無活躍 caller — reserved-for-future |
| §1.1 insurance | GET /v5/market/insurance | 有 API wrapper，實盤路徑未使用 — OK（生存相關，待接線） |
| §1.1 historical-volatility | GET /v5/market/historical-volatility | wrapper 存在，無活躍 caller — Options-only，linear-trading 不需 |
| §1.6 inter_transfer / coin_info / demo-apply-money | 有 wrapper 無活躍 caller | 維護性保留 |
| §1.7 Spot Margin UTA 全 6 endpoint | wrapper 存在無 caller | Linear-focus 不需 Spot Margin |
| §1.8 Leverage Tokens 全 4 endpoint | 同上 | 同上 |
| §2.1 liquidation/price-limit/adl-notice | parser 保留但 subscription 已移除（broken topic） | ✅ 字典已註明 removed |
| §4.1 rate limit Position=20 req/s | `bybit_rest_client.rs:274` default group remaining 仍為 10 | 兩者都對 — header 回來會覆寫，default 10 是保守啟動值 |

### 7.2 實作有用但字典未記

| 實作位置 | 內容 | 字典缺失處 |
|---|---|---|
| `settings_routes.py:100` | GET /v5/user/query-api | §1 全無此章節 |
| `bybit_private_ws_status_writer.rs` | 每 5s 產出 status JSON；新 `listener_version:"rust-v1"` 契約 | §2.2 / §2.3 未記 |
| `order_manager.rs:476` | `cancel_order_by_link_id` 專用 method；已錄 §1.2 | ✅ 已錄 |
| `position_manager.rs:335` 正確路徑 `confirm-pending-mmr` | 應更新 §1.4 + §4.3 陷阱 #5 | H-1（見 §6.2） |
| `ws_client.rs:390-415` 運行時訂閱調整（`WsTopicChange`） | 字典僅記靜態訂閱列表 | 補一個 subsection |
| `instrument_info.rs::ensure_symbol` + negative cache + singleflight + pagination | 字典 §1.9 僅提 refresh；ensure_symbol_force / neg cache / INSTR-ENSURE-FORCE-1 未記 | 補 §1.9 進階功能說明 |
| `bybit_rest_client.rs::BybitRetCode` 新增 `PriceOutOfRange / WalletInsufficient / AvailableInsufficient / OrderCompletedOrCancelled / OrderAlreadyCancelled / PriceTickInvalid / ContractNotLive / PostOnlyOnlyStage / OrderNotExistSpot` | §4.2 表格已更新 ✅ | — |
| `bybit_rest_client.rs::BybitRetCode::is_instrument_filter / is_exchange_backoff / is_balance_block` | 字典 §4.2 已註明 ✅ | — |
| Python `bybit_rest_client.py::refresh_instruments` 分頁（cursor + 50 pages） | 字典 §1.9 說 refresh() 刷 Rust cache；Python 獨立路徑未記 | 補短章說明 Python drop-in 範圍 |
| `ws_client.rs::parse_ticker_item` 提取 `fundingRate/indexPrice/openInterest` | 字典 §2.1 ticker 僅列 `last_price/volume_24h/bid_price/ask_price`；擴充欄位未記 | 補錄 EDGE-P1-2 / OC-5 / EDGE-P2-2 三個 PR 的 ticker 擴充 |

---

## 8. 簽名 / Header / Auth 細節總結

| 屬性 | Rust 實作 | Python 實作 | Bybit V5 規範 |
|---|---|---|---|
| Sign string | `timestamp + api_key + recv_window + params` | 同 | ✅ |
| Algorithm | HMAC-SHA256 → lowercase 64-hex | 同 | ✅ |
| recv_window | `"5000"` 硬編碼 | 同 | ✅ 預設；支援 ≤30000ms |
| Timestamp | `SystemTime::now() ms` | `int(time.time()*1000)` | ✅ |
| X-BAPI-API-KEY | ✅ | ✅ | ✅ |
| X-BAPI-SIGN | ✅ | ✅ | ✅ |
| X-BAPI-TIMESTAMP | ✅ | ✅ | ✅ |
| X-BAPI-RECV-WINDOW | ✅ | ✅ | ✅ |
| X-BAPI-SIGN-TYPE | ❌ Rust 未送 / ❌ Python REST client 未送 / ✅ Python settings_routes.py:236 送 `"2"` | — | 選填；預設 `2`=HMAC — 未送 = 2 = OK |
| Content-Type | `application/json` | 同 | ✅ |
| GET query signing | Sorted alpha by key | 同 | ✅ |
| POST body signing | 精確 JSON 字串（Rust: `serde_json::to_string`；Python: `json.dumps(..., separators=(",",":"))`）| 同 | ✅ 兩端字元一致 |
| WS auth signing | HMAC-SHA256(`api_secret`, `"GET/realtime" + expires_ms`) | 同（`bybit_private_ws_smoke_test.py:32-37`） | ✅ |
| WS auth expires | `now_ms + 10_000` | 同 | ✅ |

**結論**：HMAC 簽名與 header set **無一不對**。

---

## 9. Rate Limit 處理

| 實現 | 位置 | 對齊字典 §4.1 |
|---|---|---|
| Global remaining | `RateLimitState::remaining: AtomicI64`（從 `x-bapi-limit-status` header 讀） | ✅ |
| Per-group remaining | `group_remaining: [AtomicI64; 6]`（Order/Position/Account/Market/Asset/Other） | ✅ |
| 路徑分類 | `RateLimitGroup::from_path()` — 前綴匹配 `/v5/order/`/`/v5/execution/` → Order；`/v5/position/` → Position 等 | ✅ |
| 主動退避 | `wait_if_rate_limited` — `threshold=10` + `max_wait=2s` + `50ms buffer`；到 reset_ms + 50 後放行 | ✅ 保守合理 |
| 批次訂閱間隔 | Public WS Subscribe 批次間 500ms `sleep`（`ws_client.rs:259`） | ✅ |

**結論**：rate limit 接線符合字典設計、有條件併發保護。

---

## 10. Pagination / Cursor 處理

| Endpoint | 實現 | 驗證 |
|---|---|---|
| `/v5/market/instruments-info` (Rust) | `instrument_info.rs:319-377` — cursor loop + `limit=1000` + `MAX_PAGES=10` 硬上限 + warn! on cap hit | ✅ INSTR-PAGINATE-1 修復 2026-04-23 Bybit linear > 500 symbol 切字母序問題 |
| `/v5/market/instruments-info` (Python) | `bybit_rest_client.py:559-577` — `for _ in range(50): cursor → nextPageCursor` | ✅ |
| `/v5/order/history` | 單頁 50 筆 default | — 字典未強調；Bybit V5 此端點僅回最近 7d，長歷史需 paginate；當前實作**未迴圈 cursor** — 若 caller 要長歷史需自行 loop（Advisory） |
| `/v5/execution/list` | 同上 | 同上 |
| `/v5/account/transaction-log` | 同上 | 同上 |
| `/v5/position/closed-pnl` | 同上 | 同上 |

**Advisory**：`get_order_history / get_executions / get_closed_pnl / get_transaction_log` 未提供 cursor 參數，意圖是「最近 N 筆即可」；若未來需要完整歷史拉取，caller 需做外層 loop。字典 §1.2 可加一行 note。

---

## 11. 結論與建議

### 11.1 整體評估

Bybit V5 API 層 **實作正確性 = 高**：
- Rust `openclaw_engine` 核心交易路徑（REST auth + signing、order/position/account lifecycle、Private WS auth/subscribe/parse、DCP、LIVE-GUARD-1 硬鎖、retCode 語意分類）全部對齊 Bybit V5 官方規範
- Python `bybit_rest_client.py` httpx drop-in 與 Rust 契約字節級對齊（簽名 payload、header 命名、sorted query、JSON body 序列化都一致）
- Private WS listener 已由 Rust `bybit_private_ws_status_writer.rs` 接管 observer 契約

### 11.2 立即可做（≤1d work）

1. **H-1 字典更正**：把 `docs/references/2026-04-04--bybit_api_reference.md` §1.4 `confirm_pending_mmr` + §4.3 陷阱 #5 的路徑從 `confirm-mmr` 改為 `confirm-pending-mmr`
2. **L-1/L-2/L-3 字典補錄**：`intervalTime`、`account-ratio` period 值域移除 `1d` 加 `4d`、補 `/v5/user/query-api` 章節
3. **L-4/M-1 ws_client.rs 強化**：`process_message` 對 `ret_msg contains "handler not found" / "topic does not exist"` 升級為 `error! + return false` 強制重連

### 11.3 中期（≤1w work）

4. **M-2**：`bybit_public_connectivity_check.py` 去硬編碼 URL → 環境變數或透過 `bybit_rest_client.py` public endpoint helper
5. **M-3**：評估刪除 `bybit_private_ws_smoke_test.py` + v2（`bybit_private_ws_status_writer.rs` 已取代 observer 面向價值），或至少移除 `read_only` legacy slot 依賴
6. **A-1**：Rust `order_manager.rs::{get_active_orders,get_order_history,get_executions}` 加 settleCoin fallback 對稱 Python 面，或至少在 docstring 警告 symbol=None 會觸發 Bybit 10001

### 11.4 不動項（by design）

- `BybitEnvironment::LiveDemo` 不訂閱 `execution.fast/dcp`：demo 技術限制，非降級 ✅
- `/v5/market/price-limit` 實際查 `instruments-info`：Bybit V5 無獨立端點 ✅（字典已註明）
- `pre_check_order` 已刪（FIX-20）：Bybit 無 dry-run 端點，dummy 會真實下單 ✅
- liquidation/price-limit/adl-notice subscription 已移除：broken topic 會毒化連接 ✅
- `get_order_history` 等未加 cursor loop：design 上只需最近 N 筆，無需全歷史

---

## 12. 檔案清單（絕對路徑）

**Rust 端（實作 SSOT）**：
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_rest_client.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_private_ws.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_private_ws_status_writer.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ws_client.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/order_manager.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/position_manager.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/account_manager.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/platform_client.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/market_data_client/mod.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/instrument_info.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/position_reconciler/mod.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/database/rest_poller.rs

**Python 端**：
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/symbol_category_registry.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_demo_connector.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_public_microstructure_builder.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_public_connectivity_check.py  ← M-2
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_ws_smoke_test.py  ← M-3
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_private_ws_smoke_test_v2.py  ← M-3

**參考**：
- /Users/ncyu/Projects/TradeBot/srv/docs/references/2026-04-04--bybit_api_reference.md  ← H-1/L-1/L-2/L-3 需更新
- /Users/ncyu/Projects/TradeBot/srv/docs/audits/2026-04-04--bybit_api_infra_audit.md

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-04-24--bybit_api_compat_audit.md

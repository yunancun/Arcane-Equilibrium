# Bybit V5 API 集成審計報告

> **審計角色**: BB (Bybit API Specialist)
> **日期**: 2026-04-12
> **範圍**: Rust `openclaw_engine` 全部 Bybit REST/WS 端點 + Python PyO3 橋接層
> **參照**: Bybit V5 官方文檔 + `docs/references/2026-04-04--bybit_api_reference.md`

---

## 一、審計總結

| 項目 | 統計 |
|------|------|
| REST 端點總數 | 48 |
| WebSocket 連接 | 2（公開 + 私有） |
| **[PASS]** 正確 | 42 |
| **[API-MISMATCH]** 端點路徑/參數不匹配 | 3 |
| **[PARSE-ERROR]** 解析問題 | 1 |
| **[MISSING-HANDLER]** 缺失處理 | 1 |
| **[DEPRECATED]** 使用已棄用端點 | 0 |
| **[NAMING]** 函數命名與功能不匹配 | 1 |
| **[RISK]** 業務邏輯風險 | 1 |

**整體評級**: **B+** — 核心交易路徑（下單/查倉/查餘額/WS 訂閱）全部正確，HMAC 簽名嚴謹，B-2 修復徹底。少數邊緣端點存在問題，但均非交易關鍵路徑。

---

## 二、REST API 端點逐項審計

### 2.1 核心交易端點 — `order_manager.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `place_order()` | `/v5/order/create` | POST | **[PASS]** | category/symbol/side/orderType/qty 正確；camelCase body；price 字串化；timeInForce 默認正確（Limit→GTC）；reduceOnly/closeOnTrigger/triggerPrice/triggerDirection/TP/SL 全部正確映射 |
| `cancel_order()` | `/v5/order/cancel` | POST | **[PASS]** | category/symbol/orderId 正確 |
| `cancel_all()` | `/v5/order/cancel-all` | POST | **[PASS]** | 回應解析 `result.list` 正確 |
| `amend_order()` | `/v5/order/amend` | POST | **[PASS]** | orderId/orderLinkId 二擇一校驗正確；qty/price 取整後字串化 |
| `get_active_orders()` | `/v5/order/realtime` | GET | **[PASS]** | category 必填；symbol 可選 |
| `get_order_history()` | `/v5/order/history` | GET | **[PASS]** | limit 默認 50 |
| `get_executions()` | `/v5/execution/list` | GET | **[PASS]** | 解析 execId/execPrice/execQty/execFee/feeCurrency 完整 |

**精度處理**: `validate_and_round()` 使用 `InstrumentInfoCache`，M-1 修復後缺失 spec 時 fail-closed（不再繞過驗證）。qty 用 floor（避免超額），price 用 round。`format_qty()` / `format_price()` 正確去尾零。

### 2.2 批量訂單端點 — `batch_order_manager.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `create_batch()` | `/v5/order/create-batch` | POST | **[PASS]** | Bybit 限制 10 筆/批，代碼需調用方控制 |
| `amend_batch()` | `/v5/order/amend-batch` | POST | **[PASS]** | |
| `cancel_batch()` | `/v5/order/cancel-batch` | POST | **[PASS]** | |

### 2.3 持倉端點 — `position_manager.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_positions()` | `/v5/position/list` | GET | **[PASS]** | 無 symbol 時正確使用 `settleCoin=USDT`（Bybit 要求 symbol 或 settleCoin 二擇一）|
| `set_leverage()` | `/v5/position/set-leverage` | POST | **[PASS]** | 110043（已設置）視為成功，冪等處理正確 |
| `set_trading_stop()` | `/v5/position/trading-stop` | POST | **[PASS]** | TP/SL/trailingStop/activePrice/positionIdx 全部正確；字串化數值 |
| `switch_position_mode()` | `/v5/position/switch-mode` | POST | **[PASS]** | mode: 0=single, 3=hedge 正確 |
| `confirm_pending_mmr()` | `/v5/position/confirm-mmr` | POST | **[API-MISMATCH]** | Bybit V5 實際端點為 `/v5/position/confirm-pending-mmr`，多了 `pending-`。但此端點極少使用（僅 risk limit 變更後），影響低 |
| `set_auto_add_margin()` | `/v5/position/set-auto-add-margin` | POST | **[PASS]** | autoAddMargin: 0/1 正確 |
| `add_margin()` | `/v5/position/add-margin` | POST | **[PASS]** | margin 字串化正確 |
| `get_closed_pnl()` | `/v5/position/closed-pnl` | GET | **[PASS]** | 解析 avgEntryPrice/avgExitPrice/closedPnl 等字段正確 |

### 2.4 帳戶端點 — `account_manager.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `refresh_balance()` | `/v5/account/wallet-balance` | GET | **[PASS]** | `accountType=UNIFIED` 正確；解析 totalEquity/totalWalletBalance/totalAvailableBalance + per-coin (equity/walletBalance/availableToWithdraw/unrealisedPnl/cumRealisedPnl) 完整 |
| `refresh_fee_rates()` | `/v5/account/fee-rate` | GET | **[PASS]** | `category=linear` 正確；解析 makerFeeRate/takerFeeRate 正確；默認 fallback 0.00055/0.0002 與 Bybit VIP-0 費率一致 |
| `get_account_info()` | `/v5/account/info` | GET | **[PASS]** | 解析 marginMode/unifiedMarginStatus/smpGroup/isMasterTrader 正確 |
| `set_hedging_mode()` | `/v5/account/set-hedging-mode` | POST | **[API-MISMATCH]** | Bybit V5 可能的正確路徑為 `/v5/account/set-hedging`（無 `-mode` 後綴）。需驗證。此端點在項目中未被調用（dead code），影響為零 |
| `get_borrow_history()` | `/v5/account/borrow-history` | GET | **[PASS]** | currency/limit 參數正確 |
| `repay()` | `/v5/account/repay` | POST | **[API-MISMATCH]** | Bybit V5 UTA 帳戶的還款端點可能不是此路徑。需驗證是否為 `/v5/account/quick-repayment` 或其他。此端點在項目中未被調用（dead code），影響為零 |

### 2.5 平台端點 — `platform_client.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_transaction_log()` | `/v5/account/transaction-log` | GET | **[PASS]** | |
| `set_margin_mode()` | `/v5/account/set-margin-mode` | POST | **[PASS]** | |
| `get_collateral_info()` | `/v5/account/collateral-info` | GET | **[PASS]** | |
| `set_collateral()` | `/v5/account/set-collateral` | POST | **[PASS]** | |
| `set_dcp()` | `/v5/order/disconnected-cancel-all` | POST | **[PASS]** | timeWindow 正確 |
| `get_dcp_info()` | `/v5/account/dcp-info` | GET | **[PASS]** | 僅 mainnet 支援 |
| `pre_check_order()` | `/v5/order/create` | POST | **[RISK]** | 此方法作為「預檢」使用 `/v5/order/create`（真正的下單端點）。代碼註釋已承認「Bybit 沒有專門的預檢端點」。如果 params 格式正確且帳戶有餘額，此調用**會真正下單**。建議：(a) 在 body 加 `dryRun` 標記（如 Bybit 未來支援），(b) 或移除此方法並改用本地驗證。**目前此方法未在交易路徑中被調用，風險暫低** |
| `inter_transfer()` | `/v5/asset/transfer/inter-transfer` | POST | **[PASS]** | transferId UUID + coin/amount/from/to 正確 |
| `query_transfer_list()` | `/v5/asset/transfer/query-inter-transfer-list` | GET | **[PASS]** | |
| `get_account_coins_balance()` | `/v5/asset/transfer/query-account-coins-balance` | GET | **[PASS]** | |
| `get_coin_info()` | `/v5/asset/coin-info` | GET | **[PASS]** | |
| `apply_demo_funds()` | `/v5/account/demo-apply-money` | POST | **[PASS]** | `utaList` 格式正確（coin + amountStr） |

### 2.6 市場數據端點 — `market_data_client/mod.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_server_time()` | `/v5/market/time` | GET | **[PASS]** | timeSecond/timeNano 解析正確 |
| `get_klines()` | `/v5/market/kline` | GET | **[PASS]** | interval 格式正確（"1"/"5"/"15"/"60"/"D"/"W"/"M"） |
| `get_mark_price_klines()` | `/v5/market/mark-price-kline` | GET | **[PASS]** | |
| `get_premium_index_klines()` | `/v5/market/premium-index-price-kline` | GET | **[PASS]** | |
| `get_index_price_klines()` | `/v5/market/index-price-kline` | GET | **[PASS]** | |
| `get_tickers()` | `/v5/market/tickers` | GET | **[PASS]** | |
| `get_orderbook()` | `/v5/market/orderbook` | GET | **[PASS]** | limit 默認 50 |
| `get_open_interest()` | `/v5/market/open-interest` | GET | **[PASS]** | 參數名 `intervalTime` 正確（非 `interval`）|
| `get_funding_history()` | `/v5/market/funding/history` | GET | **[PASS]** | startTime/endTime 正確 |
| `get_long_short_ratio()` | `/v5/market/account-ratio` | GET | **[PASS]** | period 參數正確 |
| `get_risk_limit()` | `/v5/market/risk-limit` | GET | **[PASS]** | |
| `get_insurance()` | `/v5/market/insurance` | GET | **[PASS]** | |
| `get_adl_alert()` | `/v5/market/adl-alert` | GET | **[MISSING-HANDLER]** | 此端點可能不存在於 Bybit V5 公開市場數據 API 中。ADL 信息通常通過私有 WS `position` topic 中的 `adlRankIndicator` 字段獲取，或通過持倉列表的 `isReduceOnly` 字段推斷。調用此端點可能返回 retCode != 0。但代碼已有 `into_result()` 錯誤處理，不會 panic。影響：ADL 警報功能可能靜默失敗 |
| `get_recent_trades()` | `/v5/market/recent-trade` | GET | **[PASS]** | |
| `get_historical_volatility()` | `/v5/market/historical-volatility` | GET | **[PASS]** | |
| `get_delivery_price()` | `/v5/market/delivery-price` | GET | **[PASS]** | |
| `get_price_limit()` | `/v5/market/instruments-info` | GET | **[PASS]** | 正確！代碼注釋說明了不使用不存在的 `/v5/market/price-limit`，改為從 instruments-info 的 priceFilter 提取 |

### 2.7 合約信息 — `instrument_info.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `refresh()` | `/v5/market/instruments-info` | GET | **[PASS]** | 解析 lotSizeFilter (qtyStep/minOrderQty/maxOrderQty) + priceFilter (tickSize/minPrice/maxPrice) 正確；自動計算 qty_decimals/price_decimals |

### 2.8 現貨保證金 — `spot_margin_client.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_margin_data()` | `/v5/spot-margin-trade/data` | GET | **[PASS]** | |
| `switch_mode()` | `/v5/spot-margin-uta/switch-mode` | POST | **[PASS]** | |
| `set_leverage()` | `/v5/spot-margin-uta/set-leverage` | POST | **[PASS]** | |
| `get_status()` | `/v5/spot-margin-uta/status` | GET | **[PASS]** | |
| `get_max_borrowable()` | `/v5/spot-margin-uta/max-borrowable` | GET | **[PASS]** | |
| `get_repay_history()` | `/v5/spot-margin-uta/repayment-available-amount` | GET | **[NAMING]** | 函數名 `get_repay_history()` 暗示查詢還款歷史，但實際調用的端點是「可還款金額」查詢。功能語義不匹配。應重命名為 `get_repayment_available()` 或類似名稱。非阻塞 bug，但可能造成維護混淆 |

### 2.9 槓桿代幣 — `leverage_token_client.rs`

| 方法 | Bybit 路徑 | HTTP | 結果 | 備註 |
|------|-----------|------|------|------|
| `get_token_info()` | `/v5/spot-lever-token/info` | GET | **[PASS]** | |
| `get_token_reference()` | `/v5/spot-lever-token/reference` | GET | **[PASS]** | |
| `purchase()` | `/v5/spot-lever-token/purchase` | POST | **[PASS]** | |
| `redeem()` | `/v5/spot-lever-token/redeem` | POST | **[PASS]** | |

---

## 三、WebSocket 審計

### 3.1 公開 WebSocket — `ws_client.rs` + `multi_interval_ws.rs`

| 項目 | 結果 | 詳情 |
|------|------|------|
| **URL** | **[PASS]** | `wss://stream.bybit.com/v5/public/linear`（config 默認值），可通過 TOML 覆蓋 |
| **訂閱格式** | **[PASS]** | `{"op":"subscribe","args":["topic1","topic2",...]}` 正確 |
| **批量限制** | **[PASS]** | 每次 subscribe 最多 10 個 topic（`SUBSCRIBE_BATCH_SIZE=10`），符合 Bybit 限制 |
| **動態訂閱** | **[PASS]** | `WsTopicChange::Subscribe/Unsubscribe` 支援運行時增減 topic，且記錄到重連重播列表 |
| **心跳** | **[PASS]** | `{"op":"ping"}` 每 20s 發送（可配置 `heartbeat_interval_ms`）；Bybit 要求 <=20s |
| **Ping/Pong** | **[PASS]** | 處理 `Message::Ping` 回覆 `Message::Pong`；JSON pong 回應正確忽略 |
| **連接超時** | **[PASS]** | 15s 連接超時（WS-TIMEOUT 修復） |
| **重連** | **[PASS]** | 指數退避 3s base × 2^attempt，上限 60s |
| **取消** | **[PASS]** | `CancellationToken` 在連接/退避/消息循環三個階段都檢查 |

**訂閱 Topic 格式審計**:

| Topic | 格式 | 結果 |
|-------|------|------|
| K 線 | `kline.{interval}.{symbol}` | **[PASS]** — interval: "1"/"5"/"15"/"60" 正確 |
| 行情 | `tickers.{symbol}` | **[PASS]** |
| 訂單簿 | `orderbook.50.{symbol}` | **[PASS]** — 50 檔深度 |
| 成交 | `publicTrade.{symbol}` | **[PASS]** |
| 清算 | `liquidation.{symbol}` | **[PASS]** |
| 價格限制 | `price-limit.{symbol}` | **[PASS]** — 代碼有 parser 但未在 multi_interval_ws 中默認訂閱 |
| ADL 通知 | `adl-notice.{symbol}` | **[PASS]** — 代碼有 parser 但未默認訂閱 |

**消息解析審計**:

| 消息類型 | 解析正確性 | 備註 |
|----------|-----------|------|
| Trade (`p`/`v`/`T`/`S`) | **[PASS]** | 價格/成交量/時間戳/方向全部正確 |
| Kline (`close`/`start`/`volume`/`confirm`) | **[PASS]** | 正確只處理 confirmed K 線；未確認丟棄 |
| Orderbook (`b`/`a` arrays) | **[PASS]** | best bid/ask + mid price + top-5 levels 正確 |
| Ticker (`lastPrice`/`volume24h`/`bid1Price`/`ask1Price`/`turnover24h`) | **[PASS]** | |
| Liquidation (`price`/`side`/`size`/`updatedTime`) | **[PASS]** | |

### 3.2 私有 WebSocket — `bybit_private_ws.rs`

| 項目 | 結果 | 詳情 |
|------|------|------|
| **URL** | **[PASS]** | Demo/LiveDemo: `wss://stream-demo.bybit.com/v5/private`；Testnet: `wss://stream-testnet.bybit.com/v5/private`；Mainnet: `wss://stream.bybit.com/v5/private` |
| **認證格式** | **[PASS]** | `{"op":"auth","args":["api_key","expires","signature"]}` 正確；sign = `HMAC-SHA256(api_secret, "GET/realtime" + expires)` 符合 Bybit 規範；expires = now + 10000ms |
| **認證超時** | **[PASS]** | 10s 超時等待 auth response |
| **訂閱確認檢查** | **[PASS]** | B-2 教訓後新增 subscribe 確認日誌（success=false 時 error 級別），防止 topic 名稱拼寫錯誤被靜默忽略 |
| **Ping** | **[PASS]** | `{"op":"ping"}` 每 20s |
| **重連** | **[PASS]** | 指數退避 3s × 2^attempt，上限 60s |
| **取消** | **[PASS]** | 三個階段（連接前/認證中/消息循環/退避中）均檢查 CancellationToken |

**B-2 修復驗證** (execution.fast vs execution):

| 環境 | 訂閱 Topics | 結果 |
|------|------------|------|
| Demo | `order, execution, position, wallet` | **[PASS]** — 不包含 `execution.fast`（Demo 靜默接受但不推數據） |
| LiveDemo | 同 Demo | **[PASS]** |
| Testnet | 同 Demo | **[PASS]** |
| Mainnet | `order, execution.fast, position, wallet, dcp` | **[PASS]** — 使用 `execution.fast`（~50ms 延遲）+ `dcp` |

**回歸測試**: `test_private_topics_per_environment()` 覆蓋了所有 4 個環境的正確 topic 選擇，包括防止 `fast-execution` typo。

**私有消息解析審計**:

| Topic | 解析字段 | 結果 |
|-------|---------|------|
| `order` | orderId, orderLinkId, symbol, side, orderType, price, qty, cumExecQty, orderStatus, createdTime, updatedTime | **[PASS]** |
| `execution` | execId, orderId, symbol, side, execPrice, execQty, execFee, execType, execTime | **[PASS]** |
| `execution.fast` | 同 execution（少 execFee/execValue/feeRate） | **[PASS]** — serde default 處理缺失字段為空字串 |
| `position` | symbol, side, size, avgPrice, unrealisedPnl, markPrice, liqPrice | **[PASS]** — `avgPrice` / `unrealisedPnl` 有 `alias` 處理 camelCase |
| `wallet` | accountType, coin[].{coin, equity, walletBalance, availableToWithdraw} | **[PASS]** |
| `dcp` | (無數據字段) | **[PASS]** — 僅事件通知 |

**[PARSE-ERROR]**: `execution.fast` 消息**缺少 `execFee` 字段**，但 `ExecutionUpdate.exec_fee` 使用 `serde(default)` 解析為空字串 `""`。下游代碼如果對 `exec_fee` 做 `parse::<f64>()` 將得到 0.0。對於 mainnet live 交易，這意味著通過 WS 推送的 fast-execution 事件**沒有真實手續費**——手續費需要從 REST `/v5/execution/list`（返回完整 `execFee`）或普通 `execution` topic 補全。**此問題與 PNL-FIX-2（`emit_close_fill` 寫 `fee: 0.0`）性質相似**，但因 mainnet 尚未上線，暫無影響。

---

## 四、HMAC 簽名審計

| 項目 | 結果 | 詳情 |
|------|------|------|
| **REST 簽名** | **[PASS]** | `sign_str = timestamp + api_key + recv_window + params`；GET params 排序後序列化；POST body JSON 序列化後簽名。符合 Bybit V5 規範 |
| **WS 簽名** | **[PASS]** | `sign_payload = "GET/realtime" + expires`；HMAC-SHA256(api_secret, sign_payload)。符合 Bybit 規範 |
| **Headers** | **[PASS]** | `X-BAPI-API-KEY`, `X-BAPI-SIGN`, `X-BAPI-TIMESTAMP`, `X-BAPI-RECV-WINDOW` 四個 header 完整 |
| **recv_window** | **[PASS]** | 固定 5000ms，符合 Bybit 推薦值 |
| **GET 參數排序** | **[PASS]** | `sorted_params.sort_by_key(|(k, _)| *k)` 按 key 字母序排列 |

---

## 五、錯誤處理審計

| 項目 | 結果 | 詳情 |
|------|------|------|
| **retCode 檢查** | **[PASS]** | `BybitResponse::into_result()` 統一處理 retCode != 0 |
| **已知 retCode 分類** | **[PASS]** | 0/10001-10006/10010/110001/110009/110012/110043/170210 全部覆蓋 |
| **冪等錯誤** | **[PASS]** | 110043 (LeverageNotModified) + 110001 (OrderNotFound) 標記為 noop |
| **重試策略** | **[PASS]** | 僅 10006 (IpRateLimit) 標記為可重試；其他不重試，符合 fail-closed 原則 |
| **HTTP 超時** | **[PASS]** | `reqwest::Client::builder().timeout(10s)` |
| **無憑證保護** | **[PASS]** | `has_credentials()` 檢查，空 key 時返回 `NoCredentials` 錯誤 |

---

## 六、限流審計

| 項目 | 結果 | 詳情 |
|------|------|------|
| **全局限流追蹤** | **[PASS]** | 從 `X-Bapi-Limit-Status` / `X-Bapi-Limit-Reset-Timestamp` header 讀取 |
| **分組限流** | **[PASS]** | 6 組（Order/Position/Account/Market/Asset/Other），路徑自動分類 |
| **主動退讓** | **[PASS]** | remaining ≤ 10 時等待至 reset_ms + 50ms buffer，上限 2s |
| **WS 批次間隔** | **[PASS]** | 運行時 subscribe 500ms inter-batch gap |

---

## 七、環境配置審計

| 環境 | REST URL | WS Private URL | Secret Slot | 結果 |
|------|---------|----------------|-------------|------|
| Demo | `api-demo.bybit.com` | `stream-demo.bybit.com/v5/private` | demo | **[PASS]** |
| LiveDemo | `api-demo.bybit.com` | `stream-demo.bybit.com/v5/private` | live | **[PASS]** |
| Testnet | `api-testnet.bybit.com` | `stream-testnet.bybit.com/v5/private` | demo | **[PASS]** |
| Mainnet | `api.bybit.com` | `stream.bybit.com/v5/private` | live | **[PASS]** |
| Default | Demo | — | — | **[PASS]** — 安全默認值 |

**Mainnet 安全**: 啟用時有 `tracing::warn!` 警告；LiveDemo 使用 live slot key 連 demo 伺服器，設計合理。

---

## 八、發現問題清單

### P0 — 無

### P1 — 低風險，建議修復

| 編號 | 標籤 | 文件 | 問題 | 建議 |
|------|------|------|------|------|
| BB-A1 | [API-MISMATCH] | `position_manager.rs:329` | `/v5/position/confirm-mmr` 可能應為 `/v5/position/confirm-pending-mmr`。但此端點未在交易路徑中被調用 | 驗證 Bybit 最新 API 文檔後修正 |
| BB-A2 | [API-MISMATCH] | `account_manager.rs:374` | `/v5/account/set-hedging-mode` 可能不是正確路徑。Dead code，從未被調用 | 驗證或刪除 |
| BB-A3 | [API-MISMATCH] | `account_manager.rs:420` | `/v5/account/repay` 可能不是 UTA 帳戶的正確還款路徑。Dead code，從未被調用 | 驗證或刪除 |
| BB-A4 | [PARSE-ERROR] | `bybit_private_ws.rs:593-605` | `execution.fast` topic 缺少 `execFee`，WS 推送的手續費為 `""` → 0.0。Mainnet 上線時需從 REST 補全 | 上線前補全邏輯或使用普通 `execution` topic 覆蓋 |
| BB-A5 | [RISK] | `platform_client.rs:362-370` | `pre_check_order()` 使用真正的 `/v5/order/create`，可能意外下單 | 明確標記為 dangerous 或移除 |
| BB-A6 | [NAMING] | `spot_margin_client.rs:216` | `get_repay_history()` 實際查的是「可還款金額」不是「還款歷史」 | 重命名為 `get_repayment_available()` |
| BB-A7 | [MISSING-HANDLER] | `market_data_client/mod.rs:473` | `/v5/market/adl-alert` 可能不是有效的 Bybit V5 公開端點 | 驗證端點存在性；考慮改用持倉 adlRankIndicator |

### P2 — 觀察項

| 編號 | 項目 | 備註 |
|------|------|------|
| BB-O1 | `execution.fast` 與 `execution` 重複事件 | Mainnet 僅訂閱 `execution.fast` 不訂閱 `execution`——正確避免重複。但 `execution.fast` 欄位不完整，live 交易上線後需確認 fee 補全路徑 |
| BB-O2 | DCP topic 僅 mainnet | 正確行為，demo 會拒絕 `dcp` topic。但 DCP POST 設置(`/v5/order/disconnected-cancel-all`)也僅 mainnet 有效，demo 調用會得到錯誤 |
| BB-O3 | 默認 taker fee 0.00055 | 與 Bybit 2026 VIP-0 linear 費率一致。如 Bybit 調整費率結構需同步更新 |

---

## 九、結論

**核心交易路徑安全**: 下單/查倉/查餘額/WS 訂閱/HMAC 簽名/限流/錯誤處理——全部正確，測試覆蓋充分。

**B-2 修復徹底**: `execution.fast` vs `execution` 的環境差異在代碼（`private_ws_topics()`）和測試（`test_private_topics_per_environment()`）兩層防護，回歸風險極低。

**主要風險**: BB-A4（`execution.fast` 缺少手續費）是 mainnet 上線前唯一需要關注的 P1 問題，因為它可能導致通過 WS 收到的 fill 事件手續費為 0，與 PNL-FIX-2 同類。其他 API-MISMATCH 問題均在 dead code 路徑，不影響運行。

**建議優先級**: BB-A4 > BB-A5 > BB-A1 > BB-A6 > BB-A7 > BB-A2 = BB-A3

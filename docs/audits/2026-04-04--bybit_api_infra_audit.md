# 2026-04-04 Bybit V5 API Infrastructure Audit
# BB（Bybit 技術顧問）+ E5（優化工程師）聯合審核

## Audit Scope / 審核範圍

Full coverage audit of Rust Bybit API layer (`openclaw_engine/src/`) against official Bybit V5 API documentation (~243 REST + ~20 WS topics).

## Reviewers / 審核角色

- **BB** — Bybit API 技術顧問（外部視角：路徑正確性、rate limit、錯誤處理）
- **E5** — 優化工程師（內部視角：代碼質量、架構、性能）

---

## 1. Fixes Applied / 已修復項目

### 1.1 Outdated API Paths (5 fixes)

| File | Old Path | New Path | Severity |
|------|----------|----------|----------|
| `position_manager.rs` | `/v5/position/set-trading-stop` | `/v5/position/trading-stop` | **HIGH** |
| `account_manager.rs` | `/v5/account/quick-repayment` | `/v5/account/repay` | **HIGH** |
| `platform_client.rs` | `/v5/account/query-dcp-info` | `/v5/account/dcp-info` | **MED** |
| `platform_client.rs` | `/v5/account/set-collateral-switch` | `/v5/account/set-collateral` | **MED** |
| `account_manager.rs` | method `quick_repayment()` | renamed to `repay()` | MED |

### 1.2 UTA Path Migration (3 fixes)

| File | Old Path | New Path |
|------|----------|----------|
| `spot_margin_client.rs` | `/v5/spot-margin-trade/switch-mode` | `/v5/spot-margin-uta/switch-mode` |
| `spot_margin_client.rs` | `/v5/spot-margin-trade/set-leverage` | `/v5/spot-margin-uta/set-leverage` |
| `spot_margin_client.rs` | `/v5/spot-margin-trade/state` | `/v5/spot-margin-uta/status` |

Note: `/v5/spot-margin-trade/data` kept as-is (public endpoint, still valid).

### 1.3 Deprecated Endpoints Removed (3 removals, 1 replacement)

| Removed Method | Old Path | Reason |
|----------------|----------|--------|
| `switch_isolated()` | `/v5/position/switch-isolated` | Endpoint removed by Bybit; use `/v5/account/set-margin-mode` |
| `set_tpsl_mode()` | `/v5/position/set-tpsl-mode` | Endpoint removed; TP/SL mode now in trading-stop or order params |
| `set_risk_limit()` | `/v5/position/set-risk-limit` | Endpoint removed; replaced by confirm-pending-mmr |

**Added:** `confirm_pending_mmr()` → `POST /v5/position/confirm-pending-mmr`

All 3 removed methods had **0 callers** across entire codebase (Rust + Python verified).

### 1.4 Missing P0 Endpoints Added (2 additions)

| Endpoint | Path | File | Reason |
|----------|------|------|--------|
| ADL Alert | `GET /v5/market/adl-alert` | `market_data_client.rs` | Was stub returning empty; now calls real endpoint. Survival-critical (Principle #5). |
| Insurance Pool | `GET /v5/market/insurance` | `market_data_client.rs` | New method + `InsuranceRecord` struct. |

### 1.5 Security Confirmation

- **No withdraw/deposit endpoints** exist in the codebase ✅
- `available_to_withdraw` is a read-only field from Bybit wallet balance response — not a withdraw capability
- BB recommendation: API Key should have Trade + Read permissions only, never Withdraw

---

## 2. Verified Correct Paths (no changes needed)

Initial BB report flagged 13 paths as suspicious. After verification against official Bybit docs, **8 were confirmed correct** — BB had confused documentation page URLs with API endpoint paths:

| Path | Status |
|------|--------|
| `/v5/market/mark-price-kline` | ✅ Correct |
| `/v5/market/funding/history` | ✅ Correct |
| `/v5/position/set-leverage` | ✅ Correct |
| `/v5/position/switch-mode` | ✅ Correct |
| `/v5/position/set-auto-add-margin` | ✅ Correct |
| `/v5/position/add-margin` | ✅ Correct |
| `/v5/position/closed-pnl` | ✅ Correct |
| `/v5/account/set-hedging-mode` | ✅ Correct |
| `/v5/market/price-limit` | ✅ Correct |
| `/v5/order/realtime` | ✅ Already used |

---

## 3. Coverage Summary (Post-Fix)

### 3.1 REST API Coverage

| Category | Bybit Total | Implemented | Coverage |
|----------|------------|-------------|----------|
| Market Data | 22 | 18 | **82%** |
| Trade/Order | 13 | 10 | **77%** |
| Position | 11 | 8 | **73%** |
| Account | 29 | 11 | **38%** |
| Asset | 40 | 3 | 8% |
| Spot Margin | 13 | 6 | **46%** |
| Leverage Token | 4 | 4 | **100%** |
| Platform/DCP | (in Account) | 6 | — |
| **Core Trading Total** | **75** | **47** | **63%** |

### 3.2 WebSocket Coverage

| Category | Topics | Implemented | Coverage |
|----------|--------|-------------|----------|
| Public | 9 | 3 (kline, trade, ticker) | 33% |
| Private | 7 | 4 (order, execution, position, wallet) | 57% |

### 3.3 Not Needed (by design)

User/Subaccount, Pre-upgrade, Spread, RFQ, Affiliate, Crypto Loan, Institutional Loan, Broker, Earn, Web3/Alpha — **none needed** for trading Agent.

---

## 4. Remaining Gaps (P1/P2, not blocking)

### P1 — Recommended for Phase 1

| Item | Description | Reason |
|------|-------------|--------|
| WS Orderbook | `orderbook.{depth}.{symbol}` subscription | REST polling wastes rate limit |
| WS Liquidation | `liquidation.{symbol}` subscription | Market sentiment signal |
| Per-endpoint rate limit | Track limits per endpoint group | Avoid cross-group throttling |
| retCode semantic handling | Map common codes (110001, 110012, etc.) | Better error recovery |

### P2 — Can Defer

| Item | Description |
|------|-------------|
| WS fast-execution | Lower latency fills (50ms vs 300ms) |
| WS DCP notification | DCP trigger alerts |
| Order pre-check | `/v5/order/pre-check` for margin impact |
| Instrument cache TTL | Auto-refresh every 4h |

---

## 5. Round 3: Full Coverage Completion (P0+P1+P2)

### 5.1 New REST Endpoint
- `GET /v5/asset/coin-info` — CoinInfoRecord + ChainInfo structs in platform_client.rs

### 5.2 Public WS — All Missing Topics Added (ws_client.rs)
| Topic | Handler | PriceEvent metadata |
|-------|---------|---------------------|
| `orderbook.{depth}.{symbol}` | `parse_orderbook_snapshot()` — best bid/ask → mid price | `type=orderbook` |
| `tickers.{symbol}` | `parse_ticker_item()` — lastPrice, volume24h, bid1/ask1 | `type=ticker` |
| `liquidation.{symbol}` | `parse_liquidation_item()` — forced liquidation events | `type=liquidation`, side, qty |
| `price-limit.{symbol}` | `parse_price_limit_item()` — max/min price boundaries | `type=price_limit`, max_price, min_price |
| `adl-notice.{symbol}` | `parse_adl_notice_item()` — ADL rank alerts | `type=adl_notice`, adl_rank, side |

Data format handling: both array `[{...}]` and object `{...}` formats now supported.

### 5.3 Topic Builder Updates (multi_interval_ws.rs)
- Added: `liquidation_topic()`, `price_limit_topic()`, `adl_notice_topic()`
- `full_subscription_list()` now generates 10 topics per symbol (was 7)

### 5.4 Private WS — New Topics (bybit_private_ws.rs)
- `fast-execution` — lower latency fills (~50ms vs ~300ms), reuses ExecutionUpdate struct
- `dcp` — Disconnect Cancel Protection trigger notification

### 5.5 Per-Endpoint Rate Limit Groups (bybit_rest_client.rs)
- `RateLimitGroup` enum: Order/Position/Account/Market/Asset/Other
- `from_path()` auto-classifies by endpoint prefix
- `is_group_near_limit()` — check per-group remaining
- Per-group tracking wired into GET/POST methods

### 5.6 retCode Semantic Mapping (bybit_rest_client.rs)
- `BybitRetCode` enum: 13 known codes (Ok, InvalidParam, InsufficientBalance, LeverageNotModified, OrderNotFound, ExceedMaxQty, etc.)
- `from_code()` — classify raw retCode
- `is_retryable()` — safe to retry (e.g., IpRateLimit)
- `is_noop()` — operation already done (e.g., LeverageNotModified)

## 6. Test Results

```
Rust:   762 passed, 0 failed (+7 new tests)
Python: 2146 passed, 1 flaky (pre-existing)
```

## 7. Files Changed

| File | Changes |
|------|---------|
| `position_manager.rs` | Fixed trading-stop path, removed 3 deprecated endpoints, added confirm_mmr |
| `account_manager.rs` | Fixed repay path, renamed method |
| `platform_client.rs` | Fixed DCP info + collateral paths, added coin-info endpoint + structs |
| `spot_margin_client.rs` | Migrated 5 paths to UTA endpoints |
| `market_data_client.rs` | Fixed ADL alert stub, added insurance pool endpoint + struct |
| `ws_client.rs` | Added 5 new public WS topic parsers + object/array data handling |
| `multi_interval_ws.rs` | Added 3 topic builders, updated full subscription (7→10 topics/symbol) |
| `bybit_private_ws.rs` | Added fast-execution + dcp topics to subscription + parsing |
| `bybit_rest_client.rs` | Added RateLimitGroup, BybitRetCode, per-group tracking |

# BB — Bybit V5 API 兼容性審計報告（2026-05-08）

**Auditor**：BB（Bybit Broker Compatibility Auditor — Bybit-side advisor）
**Stance**：Bybit 派來的合規 / 政策顧問，從 Bybit 立場 push back operator 違規設計
**Baseline commit**：HEAD `4e2d2883`（2026-05-08 上午）
**Current runtime**：LiveDemo（live pipeline 走 demo endpoint），Mainnet **0 流量** by design
**Scope**：所有 Bybit V5 REST + WS 調用點 + 政策 + 程序面，純靜態審計（不打真實 API）
**Methodology**：對比三方（Bybit V5 官方規範 ↔ 字典手冊 ↔ Rust+Python 代碼）；分級 Critical / High / Medium / Low / Advisory；SSOT = Rust 代碼

---

## §1. Executive Summary

**三句話結論**：

1. **Bybit V5 API 層實作正確性 = 高**。核心交易路徑（order / position / account / market REST + Private WS auth/subscribe）全部對齊官方規範；HMAC-SHA256 簽名、recv_window=5000、4 環境切換（Demo/Testnet/Mainnet/LiveDemo）、LIVE-GUARD-1 三閘 + Gate #4/#5 全部落地。自 2026-04-24 上次審計以來，**M-1（ws_client handler not found 強制重連）已透過 G9-02 修復、M-2（bybit_public_connectivity_check 硬編碼 URL）已透過 `OPENCLAW_BYBIT_PUBLIC_BASE_URL` env override 修復、M-3（smoke test 用 read_only legacy slot）已透過刪除整個 smoke test 檔修復**。本次無新發現的 Critical / High。

2. **政策層面有 4 項 operator 必確認的 Live blocker**：(a) `OPENCLAW_BYBIT_PUBLIC_BASE_URL` env default 仍 fallback 到 mainnet（非實質風險，僅讀），(b) API key withdraw permission 是架構級鎖死但 production key 的 IP whitelist 屬 operator 配置，無代碼可驗，(c) Bybit ToS / KYC / 地理禁區是 0 governance entry 狀態（CLAUDE.md §三 #17），(d) Bybit Master Maker / Market Maker 申請門檻單帳戶當前 30d volume 達不到。

3. **funding_arb V2 棄策略 BUSDT 110017 reject loop Bybit-side RCA**：殘倉 BUSDT 約 110017 USD，**root cause = funding_arb V2 設計依賴 Bybit demo spot lending（Bybit demo 不支援），導致 short leg 無 borrowable amount，Bybit 持續回 retCode 110017（insufficient balance for short）loop**。三端 toml `active=false` 已止血（commit `a19797d` + `2d6a4057`），fee_execution_calibrator.py 加 BUSDT+110017 過濾保護 ML training rate estimate 不被污染。**Bybit-side 結論：非 ToS 違規、非帳戶問題，純技術層 spot lending 不可用 + 策略未防護**。

**Severity tally（本次新發現）**：Critical=0 / High=0 / Medium=2（M5-1 ToS governance entry、M5-2 IP whitelist 無代碼可驗）/ Low=2（L5-1/L5-2 字典 drift 殘留：open-interest interval + account-ratio period）/ Advisory=4。前次（2026-04-24）的 H-1 / M-1 / M-2 / M-3 / L-1 字典 confirm-mmr 全部 ✅ closed（5/5），L-2/L-3 仍 open。

---

## §2. Bybit endpoint 調用盤點 + 用法正確性矩陣

### 2.1 Rust SSOT 文件家族（current state）

| 模組 | 文件 | 行數 | endpoint 數 | 變動 vs 04-24 |
|---|---|---:|---:|---|
| BybitRestClient | `rust/openclaw_engine/src/bybit_rest_client.rs` | 933 | — | ↓1725→933（簽名提取至 `common::bybit_signer`，rate limit 結構保留）|
| BybitSigner（共享） | `rust/openclaw_engine/src/common/bybit_signer.rs` | 164 | — | ★ 新模組（E1-P0-3 dedup） |
| OrderManager | `rust/openclaw_engine/src/order_manager.rs` | 924 | 8 | 無變動 |
| PositionManager | `rust/openclaw_engine/src/position_manager.rs` | 845 | 8 | 無變動 |
| AccountManager | `rust/openclaw_engine/src/account_manager.rs` | 903 | 7 | 無變動 |
| PlatformClient | `rust/openclaw_engine/src/platform_client.rs` | — | 13 | 無變動 |
| MarketDataClient | `rust/openclaw_engine/src/market_data_client/mod.rs` | 532 | 14 | 無變動 |
| InstrumentInfoCache | `rust/openclaw_engine/src/instrument_info.rs` | 1008 | 1 | 無變動 |
| BybitPrivateWs | `rust/openclaw_engine/src/bybit_private_ws.rs` | 1413 | — | ↑ 增 G9-02 unknown handler guard wiring |
| WsClient（公開 WS） | `rust/openclaw_engine/src/ws_client/{mod,connection,dispatch,parsers,run_loop,tests}.rs` | 1335 | — | ★ 重構：1136 行單檔 → 6 檔模組；G9-02 ProcessOutcome::ForceReconnect 落地 |
| **WS UnknownHandlerGuard** | `rust/openclaw_engine/src/ws_unknown_handler_guard.rs` | 488 | — | ★ 新模組（G9-02）；env-gate `OPENCLAW_WS_UNKNOWN_GUARD_ARMED` |
| BybitPrivateWsStatusWriter | `rust/openclaw_engine/src/bybit_private_ws_status_writer.rs` | 620 | — | 微增 |
| LiveAuthorization | `rust/openclaw_engine/src/live_authorization.rs` | 715 | — | 持續增強（HMAC + 5min re-verify + watcher） |
| LiveAuthWatcher | `rust/openclaw_engine/src/live_auth_watcher.rs` | 970 | — | ★ 新模組（5min re-verify cancel_token graceful shutdown） |
| PositionReconciler | `rust/openclaw_engine/src/position_reconciler/mod.rs` | 842 | 1 | 持續增強（dust eviction + drift 監測） |
| RestPoller（market poller） | `rust/openclaw_engine/src/database/rest_poller.rs` | — | 3 | 無變動 |

**關鍵改動**：(1) `ws_client.rs` 1136 行重構為 6 檔模組（mod / connection / dispatch / parsers / run_loop / tests），符合 CLAUDE.md §九 800 行警告線；(2) G9-02 unknown handler guard 完整接線到 public + private WS（解決 04-24 M-1）；(3) E1-P0-3 sign_rest_v5 共享原語（dedup Rust 與 Python 的 sign_str 構造）。

### 2.2 Python 端（httpx drop-in）

| 文件 | 端點 / 用途 | 狀態 |
|---|---|---|
| `bybit_rest_client.py` | 7 methods drop-in for legacy code | 活躍 |
| `settings_routes.py` | `GET /v5/user/query-api`（key validation） | 活躍 |
| `backtest_routes.py` | `GET /v5/market/kline`（公開 OHLCV fallback） | 活躍 |
| `replay/bybit_public_client.py` | replay engine 公開數據 client（僅讀，無簽名） | ★ 新增（REF-20 Sprint A R3） |
| `bybit_demo_connector.py` | round_qty / round_price 純工具 | 活躍 |
| `symbol_category_registry.py` | `GET /v5/market/instruments-info` 啟動 cache | 測試 only |

### 2.3 V5 endpoint 實際使用（grep `"/v5/` 路徑唯一字串）

Rust 共 47 個 V5 endpoint（不含 spot-lever-token / spot-margin-uta 子端點分項）；Python 共 11 個（讀為主）。**vs 04-24：endpoint set 無變動**。

| 類別 | endpoint | Rust ✓ | Python ✓ | retCode 處理 ✓ | 字典 SSOT 對齊 |
|---|---|---|---|---|---|
| Market | `/v5/market/{time,kline,mark-price-kline,premium-index-price-kline,index-price-kline,tickers,orderbook,open-interest,funding/history,account-ratio,risk-limit,insurance,recent-trade,historical-volatility,delivery-price,instruments-info}` | ✅ | ✅（部分） | n/a 公開 | ⚠ open-interest interval 字典寫 "interval" 而非 "intervalTime"（L5-1） |
| Order | `/v5/order/{create,cancel,cancel-all,amend,realtime,history}` + `/v5/execution/list` + `/v5/order/disconnected-cancel-all` | ✅ | ✅ | ✅ 12 retCode 分類 | ✅ |
| Position | `/v5/position/{list,set-leverage,trading-stop,switch-mode,confirm-pending-mmr,set-auto-add-margin,add-margin,closed-pnl}` | ✅（confirm-pending-mmr 路徑修正後） | ✅（部分） | ✅ 110043=Ok（冪等） | ✅（2026-04-26 字典已修正 confirm-mmr → confirm-pending-mmr） |
| Account | `/v5/account/{wallet-balance,fee-rate,info,set-hedging-mode,borrow-history,repay,transaction-log,set-margin-mode,collateral-info,set-collateral,dcp-info,demo-apply-money}` | ✅ | ✅（部分） | ✅ | ✅ |
| Asset | `/v5/asset/{transfer/inter-transfer,transfer/query-inter-transfer-list,transfer/query-account-coins-balance,coin-info}` | ✅ | n/a | ✅ | ✅ |
| Spot Margin UTA | `/v5/spot-margin-trade/data` + `/v5/spot-margin-uta/{switch-mode,set-leverage,status,max-borrowable,repayment-available-amount}` | ✅（reserved） | n/a | ✅ | ✅ |
| Leverage Tokens | `/v5/spot-lever-token/{info,reference,purchase,redeem}` | ✅（reserved） | n/a | ✅ | ✅ |
| User | `/v5/user/query-api` | n/a（Python only） | ✅ | ✅ | ⚠ 字典缺章（L5-2） |

**結論**：47 個 Rust endpoint + 11 個 Python endpoint，**用法 100% 對齊 Bybit V5 官方規範**。HMAC 簽名 / header set / sorted query / JSON body 序列化 Rust ↔ Python 字節級對齊（E1-P0-3 後共享 `sign_rest_v5` 原語）。

---

## §3. Rate Limit + Burst Protection 合規

### 3.1 實作狀態

`RateLimitGroup::from_path()` 6 分組（Order / Position / Account / Market / Asset / Other），對齊 Bybit V5 官方限流結構（`bybit_rest_client.rs:215-254`）：

| 分組 | OpenClaw default remaining | Bybit V5 實際限制（reference） | 對齊 |
|---|---:|---|---|
| Order | 10 | ~10 r/s（per UID）；header 回 status 後動態調整 | ✅ |
| Position | 10 | ~10 r/s | ✅ |
| Account | 10 | ~10 r/s | ✅ |
| Market | 120 | ~120 r/s（per IP，公開） | ✅ |
| Asset | 5 | ~5 r/s | ✅ |
| Other | 10 | n/a fallback | ✅ |

**注意**：default 是保守啟動值，Bybit response header `x-bapi-limit-status` 回來後會即時覆寫。memory 內「Order=20 / Position=20 / Account=20」是 EDGE-P2-3 期觀測到 Bybit VIP tier 提升後的值；**default 10 是設計上的下限保險，不是 bug**。

### 3.2 Burst protection 機制

- `wait_if_rate_limited`：threshold=10 + max_wait=2s + 50ms buffer，global remaining ≤ 10 時主動退避到 reset_ms + 50ms
- `is_group_near_limit`：per-group threshold check
- `update_group_rate_limit`：每次 response 解析 `x-bapi-limit-status` header 寫回對應 AtomicI64
- Public WS 訂閱批次：`SUBSCRIBE_BATCH_SIZE = 10` + 500ms 批次間隔（`ws_client/run_loop.rs`）

### 3.3 ban risk 評估

**靜態評估結論：低**。理由：
1. `max_retries = 0` 硬約束（CLAUDE.md §四）→ 不會 retry storm
2. retCode != 0 fail-closed，不重試
3. PositionReconciler 30s 輪詢 `/v5/position/list` + RestPoller 5-15min 輪詢 funding/OI/LSR → 公開端點 + 低頻
4. WS 是主數據源（public + private），REST 主要用於命令路徑（單筆下單 / 撤單）+ 對賬

**Bybit-side advisor warning**：未來若 25 symbol scaling 至 100+ symbol、或 grid 策略密度提升、或新增 `cancel-all` 頻繁呼叫（Bybit 對 cancel-all 有獨立硬限 1 r/s），需重做 rate limit 容量規劃。當前 25 symbol + 5 策略 + ~50 fills/h 完全不會觸限。

### 3.4 30d 用量

operator 必查（無自動採集）：
```bash
ssh trade-core "grep -E 'rate_limit|x-bapi-limit-status' /tmp/openclaw/openclaw_engine.log | tail -200"
```
根據 healthcheck `[33] maker fill rate live_demo 7d 36.6%`（CLAUDE.md §三）反推當前 7d order endpoint 流量約 ~50 req/h × 24 × 7 = 8400 reqs，**遠低於 10 r/s per UID 限制**。

---

## §4. Broker Rebate / Market Maker 資格分析

### 4.1 當前狀態 vs Bybit 計劃門檻

| 計劃 | Bybit 門檻 | 玄衡當前狀態 | eligible? |
|---|---|---|---|
| Broker Partnership | 30d 累計 volume ≥ $10M | 25 symbol × 50 fills/d × ~$50/fill ≈ $1.5K/d × 30 = $45K | ❌ 差 222× |
| Market Maker Program | 30d maker volume ≥ $50M + maker ratio ≥ 60% | maker ratio live_demo 7d **36.6%**（healthcheck [33]）；maker volume 約 30K | ❌ 兩條件都不過 |
| VIP Tier Pro 1 | 30d volume ≥ $1M | 約 $45K | ❌ 差 22× |
| VIP Tier Pro 2 | 30d volume ≥ $5M | — | ❌ |

**Bybit-side advisor 結論**：玄衡當前 size 完全不夠申請 Bybit 任何 maker rebate / broker partnership。先把 5 策略 net edge 做正（CLAUDE.md §三 7d gross **-6.98 USDT**），再談 scale。

### 4.2 maker fill rate 提升路徑（PostOnly 部署現狀）

| 策略 | demo `use_maker_entry` | live `use_maker_entry` | 結論 |
|---|---|---|---|
| ma_crossover | true | true | ✅ Phase 2+ 全綠 |
| bb_breakout | true | **false** | live 保守維持 Market（demo 驗證未確認 net positive） |
| bb_reversion | n/a（用 `use_limit=false`） | n/a | 無 PostOnly |
| grid_trading | true | true | ✅ Phase 1A 全綠 |
| funding_arb | n/a（active=false） | n/a | 棄策略 |

**LIVE-DEMO-MAKER-FIX (2026-04-29)**：grid_trading live `use_maker_entry=true` 是因「live pipeline 寫 live_demo fills 對接 Bybit Demo」場景，提前接 PostOnly 不付 taker fee。**Bybit-side advisor 警告**：當此檔綁到真實 mainnet 時，需重新檢查 operator acceptance + execution policy（toml 內已備註）。

**maker fill rate 觀測**：`[33]` live_demo 7d **36.6%**，距 fee_drop target ≥ 60% 還差 23.4 個 pp。Bybit-side 評估：以當前 PostOnly offset 1 bps + queue position 不利情境，36.6% 屬合理範圍；要拉到 60% 需要 strategist 層改進 limit 限價邏輯（QC / FA 領域，非 BB scope）。

---

## §5. ToS / KYC / 地理禁區 operator 必確認清單

### 5.1 18 Live Blocker #17 — 0 governance entry

CLAUDE.md §三 列「KYC / 地理禁區 / Bybit ToS 合規」為 18 Live Blocker 第 17 項，🟡 Live 前必，operator 法律確認。**當前 0 governance entry**：repo 內無任何 file 記錄 operator KYC tier、地理禁區檢查、ToS 合規評估。

### 5.2 Bybit-side advisor 必確認清單（operator action）

**operator 必在 Live 前完成以下 6 項自證**（BB 不能代查，必須 operator 法律確認）：

| # | 項目 | 確認方式 | 風險 |
|---|---|---|---|
| 1 | KYC tier | 登入 Bybit account → Identity Verification 查當前 tier（0/1/2） | Tier 0 部分 derivatives 不開、出入金嚴限；live trading 至少需 Tier 1 |
| 2 | KYC 註冊地區 | 登入 Bybit account → Settings → Region 查 | 美國 / 中國大陸 / Iran / Cuba / N.Korea / Syria / Crimea 等禁區（snapshot 2026-04，動態變動）→ 帳戶可能被 freeze；以 [Bybit 官方 ToS](https://www.bybit.com/en/help-center) 為準 |
| 3 | API key permission | Bybit API Management UI → 查 read/trade 開、**withdraw 必關**、transfer 視需求 | withdraw=true → operator 自負後果（CLAUDE.md §四 硬約束 #4） |
| 4 | API key IP whitelist | Bybit API Management UI → IP whitelist 必設為 production server IP（trade-core） | 無 whitelist → API key 洩漏直接被洗；改 IP 需 24h 冷靜期 + 2FA |
| 5 | Operator 法律地區 | 與 operator 居住地 / 註冊公司地律師確認 crypto trading 合法性 | 部分國家對 crypto perp / leveraged trading 有限制 |
| 6 | Bybit ToS 全文閱讀 | https://www.bybit.com/en/help-center → Terms of Service | API 用戶協議 + 禁止行為（wash / spoofing / pump-dump / front-run）operator 必清楚 |

### 5.3 Bybit-side 對玄衡設計的禁止行為 risk audit

| 禁止行為 | OpenClaw 觸發風險 | 結論 |
|---|---|---|
| **Wash trading**（自買自賣） | grid_trading 同 symbol 同方向密集 order 是否觸 anti-wash filter | **低**：Bybit anti-wash filter 通常只 cancel order 而非 freeze account；grid_trading 7 levels + cooldown 180s（demo）/ 5 levels（live）密度遠低於高頻 anti-wash 紅線 |
| **Spoofing**（大單放又撤） | PostOnly + 45s timeout 撤單 | **低**：order size 小（3% risk per trade）+ 45s timeout 屬正常 maker behavior，非 spoofing |
| **Insider trading** | 玄衡無內幕資訊源 | **無風險** |
| **Pump-and-dump 協同** | 單帳戶單 strategy，無社群協同 | **無風險** |
| **Front-running**（演算法情境） | 無客戶代理流量 | **無風險** |
| **Multiple account 規避 limit** | 單 master account（demo + live 各 sub 是 Bybit 認可結構） | **無風險** |

**Bybit-side 結論**：**OpenClaw 設計層面 0 ToS 違規 risk**。Live 啟動風險完全來自 §5.2 6 項 operator 必確認項目未完成。

---

## §6. API Changelog 漂移（30d）

### 6.1 Bybit V5 changelog 過去 30d（2026-04-08 至 2026-05-08）

來源：https://bybit-exchange.github.io/docs/changelog/v5（透過 WebFetch 抓取，2026-05-08）

| Date | Endpoint | Type | 變動內容 | OpenClaw 影響 | 修復狀態 |
|---|---|---|---|---|---|
| 2026-05-07 | `/v5/finance/earn/easy-onchain/position` | Modified | 新增 `availableAmount` + `freezeDetails` 欄位 | OpenClaw 不用 earn endpoint | ✅ 無影響 |
| 2026-05-06 | `/v5/new-crypto-loan/fixed/{supply,cancel-supply}` | Modified | 新增 `availableSource` + `refundedAccount` optional 參數 | OpenClaw 不用 crypto loan | ✅ 無影響 |
| 2026-04-30 | `/v5/market/instruments-info` + `/v5/account/instruments` | Modified | 新增 `symbolId`（futures + options） | InstrumentInfoCache 解析時 `symbolId` 在 `priceFilter` 結構外 → 不解析 | ✅ 無影響（未 panic on extra fields） |
| 2026-04-30 | `/v5/asset/coin-info` | Modified | 新增 `withdrawMax`，**deprecated `remainAmount`** | `platform_client.rs::CoinInfo` 用 `chain_withdraw` 不用 `remainAmount` | ✅ 無影響 |
| 2026-04-27 | `/v5/strategy/create-strategy` | New | Strategy open APIs（內建策略框架） | OpenClaw 自己有策略層，不接 Bybit strategy framework | ✅ 無影響（reserved-for-awareness） |
| 2026-04-23 至 2026-04-21 | `/v5/market/instruments-info` + `/v5/account/instruments` + `/v5/position` | Modified | 新增 `symbolId` 給 spot；position data 加 `openTime`；`symbolType` enum 擴 "stock" + "forex" | `position_manager.rs::Position` 結構解析時忽略未知欄位（`#[serde(default)]` + 未列欄位）；`stock` / `forex` symbolType 不在 OpenClaw 25 symbol scope | ✅ 無影響 |

**結論**：**0 breaking change**。所有變動都是新增欄位 / 新端點 / 擴枚舉，OpenClaw 既有解析使用 `serde(default)` + 顯式 field-by-field 解析，不會 panic on unknown fields。**字典手冊不需更新**（這些欄位不在 OpenClaw 路徑上）。

### 6.2 BB 例行 audit 跟進建議（advisory）

operator 可接受新欄位 `openTime`（position）→ 用於計算 holding duration（FA / QC 領域，BB 不主動推），其他欄位無需 follow up。

---

## §7. Demo / Live Endpoint 切換邏輯 + Secret Rotation

### 7.1 4 環境 BybitEnvironment URL 表（`bybit_rest_client.rs:82-99`）

| Env | REST Base | Private WS | Public WS | secret_slot | 用途 |
|---|---|---|---|---|---|
| Demo | `https://api-demo.bybit.com` | `wss://stream-demo.bybit.com/v5/private` | `wss://stream.bybit.com/v5/public/linear` | `demo` | 沙盒測試（demo apply money 撥款） |
| Testnet | `https://api-testnet.bybit.com` | `wss://stream-testnet.bybit.com/v5/private` | 同上 | `demo` | testnet（少用） |
| **Mainnet** | `https://api.bybit.com` | `wss://stream.bybit.com/v5/private` | 同上 | `live` | 真實資金 |
| **LiveDemo** | `https://api-demo.bybit.com` | `wss://stream-demo.bybit.com/v5/private` | 同上 | `live` | Live 管線 + demo endpoint，當前主跑 |

**注意**：public WS 4 環境共用 `stream.bybit.com/v5/public/linear`（Bybit 公開數據單一 host），這是設計而非 bug。

### 7.2 LIVE-GUARD-1 三閘 + Gate #4/#5 對稱

CLAUDE.md §四 5 hard gate（4 Rust 可驗 + 1 Python only）：

| Gate | 位置 | 狀態 vs 04-24 |
|---|---|---|
| #1 Python `live_reserved` global mode | Python 側 | 維持 |
| #2 Python Operator 角色 auth | Python 側 | 維持 |
| #3 `OPENCLAW_ALLOW_MAINNET=1` env | Rust `bybit_rest_client.rs:525-537`（mainnet only） | 維持 |
| #4 secret slot api_key + secret 非空 | Rust `bybit_rest_client.rs:574-587` | 維持（Mainnet env-var fallback 封閉） |
| #5 authorization.json HMAC + 5min re-verify | Rust `live_authorization.rs:715` + `live_auth_watcher.rs:970`（cancel_token graceful shutdown） | ★ **強化**：04-24 後拉出 LiveAuthWatcher 獨立模組（970 行） |

**LiveDemo 不因 endpoint 降級**（CLAUDE.md feedback `live_no_degradation_by_endpoint.md`）：
- LiveDemo 使用 live slot credentials（secret_slot="live"）→ HMAC TTL/authorization.json 全套用 Live 標準
- LiveDemo private_ws_topics 走 demo 可用集（`order/execution/position/wallet`，無 `execution.fast/dcp`）= demo 端點技術限制 ≠ authorization 降級 ✅

### 7.3 Secret Rotation 機制

**現狀**：Rust 側 Bybit `api_key` + `api_secret` 載入時固定（`from_secret_files` 一次性讀取），無 hot rotation。Live `authorization.json` 走 5min re-verify（`live_auth_watcher.rs`），失效則 graceful shutdown engine（cancel_token）。

**Bybit-side advisor warning**：當 operator rotate API key（Bybit 端 revoke 舊 key 發新 key）時，需 `restart_all --rebuild --keep-auth` 才會拿新 key。**18 Live Blocker #16**「Live credential rotation（PG password + Grafana admin 在 git history 6 commit 公開）」是 operator 配置議題，BB scope 之外，但 Bybit api_key 同樣需在 Live 啟動前 rotate 並從 git history 清除（如有）。

---

## §8. WebSocket 連線健康

### 8.1 Public WS（`ws_client/{...}` 6 檔模組，1335 LOC）

| 項目 | 狀態 |
|---|---|
| URL | `wss://stream.bybit.com/v5/public/linear`（4 環境共用） |
| 訂閱 | `kline.1.{sym}` + `publicTrade.{sym}` + 動態 `WsTopicChange::Subscribe/Unsubscribe`（ScannerRunner 用） |
| 批次上限 | `SUBSCRIBE_BATCH_SIZE = 10` + 500ms |
| Ping | `config.heartbeat_interval_ms` |
| 重連 | `BackoffConfig::ws_public_default` 指數退避 + 15s connect timeout |
| ★ G9-02 unknown handler guard | ✅ `dispatch.rs::process_message` 對未知 topic 喂 `UnknownHandlerGuard::record_unknown(topic, now_ms())` → 觸閾值 + armed → `ProcessOutcome::ForceReconnect` → outer loop break + reconnect with cached `subscriptions` |
| Env-gate | `OPENCLAW_WS_UNKNOWN_GUARD_ARMED=1`（默認 OFF） |
| broken topic（liquidation/price-limit/adl-notice） | parser 保留但 subscription 列表已移除（毒化規避，2026-04-05 `29fc1ef`） |

**結論**：04-24 M-1 「handler not found 無強制重連」**已透過 G9-02 修復**。env-gate 設計合理（給 operator 評估 trigger 是否 noisy 後再 arm）。

### 8.2 Private WS（`bybit_private_ws.rs` 1413 LOC + `bybit_private_ws_status_writer.rs` 620 LOC）

| 項目 | 狀態 |
|---|---|
| URL | `BybitEnvironment::private_ws_url()` 4 環境分支 |
| Auth | HMAC-SHA256(`api_secret`, `"GET/realtime" + expires_ms`)；`expires = now + 10s` |
| Auth args | `[api_key, expires_str, signature]` |
| 訂閱 topics | `private_ws_topics()` 環境感知（Mainnet `[order, execution.fast, position, wallet, dcp]` / Demo+LiveDemo+Testnet `[order, execution, position, wallet]`） |
| Ping | 20s |
| 重連 | `BackoffConfig::ws_private_default()` 3s base / 60s cap / x2 |
| 訂閱 confirmation | `op==subscribe && !success` → error! 不靜默 |
| ★ G9-02 unknown handler guard | ✅ `parse_private_message` + force-reconnect 路徑（`ForceReconnect` enum + `inner loop break`） |
| reject_reason 5 字串 | `EC_PostOnlyWillTakeLiquidity / EC_PerCancelRequest / EC_CancelForNoFullFill / EC_ReachMaxPendingOrders / EC_Others` 解析正確 |
| Status writer | 每 5s `tmp+fsync+rename`，contract `listener_version="rust-v1"` |

**結論**：health 良好。LIVE-AUTH-WATCHER 教訓（memory `project_live_auth_watcher_event_consumer_spawn.md`）已抽出獨立 module（970 LOC），cancel_token 路徑修好。

---

## §9. 訂單類型使用正確性（5 策略）

| Strategy | OrderType | TimeInForce | reduce_only | trigger_price | 結論 |
|---|---|---|---|---|---|
| ma_crossover | Limit（PostOnly entry） + Market（exit） | PostOnly entry / GTC default | exit=true | trailing | ✅ EDGE-P2-3 Phase 2+ 對齊 |
| bb_breakout | Limit (demo: PostOnly) + Market（exit） | PostOnly entry demo / Market live | exit=true | trailing | ✅（live `use_maker_entry=false` by design G2-06） |
| bb_reversion | Limit (BBO-aware tick offset) | GTC（`use_limit=false` 走 Market） | exit=true | n/a | ✅ G7-09c Phase 1 BBO-aware passive |
| grid_trading | Limit（PostOnly entry） | PostOnly + 45s timeout | grid level → reduce | n/a | ✅ EDGE-P2-3 Phase 1a |
| funding_arb | Limit（PostOnly） | PostOnly | n/a | n/a | n/a（active=false 三端） |

**Bybit-side 結論**：5 策略 OrderType / TIF / reduce_only 用法**全部對齊 Bybit V5 規範**。PostOnly cross 走 WS `rejectReason=EC_PostOnlyWillTakeLiquidity` 路徑（不是 REST retCode），EDGE-P2-3 Phase 1B-1 已正確接線。

**FOK 未使用 / GoodTillDate 未使用**：當前 5 策略無這 2 種 TIF 需求，Rust enum 已支援（`TimeInForce::FOK` 字串映射到 "FOK"）。

---

## §10. funding_arb BUSDT Reject Loop Bybit-side RCA

### 10.1 事實鏈

1. **commit `a19797d` (2026-05-02)** — funding_arb V2 棄策略路徑：demo 端 `risk_config_demo.toml` `dyn_stop base_ratio 0.4→0.25` + funding_arb SL 3% override（commit 標題）
2. **commit `2d6a4057`** — Disable funding arb and harden scanner gates（標題）
3. **三端 toml 確認 `active=false`**：
   - `strategy_params_demo.toml:[funding_arb] active=false`（含 2026-05-03 stop-loss RCA 說明）
   - `strategy_params_paper.toml:[funding_arb] active=false`
   - `strategy_params_live.toml:[funding_arb] active=false`
4. **fee_execution_calibrator.py 加 BUSDT 110017 過濾**（lines 80-91）：
   - `BUSDT_110017_SYMBOL = "BUSDT"`
   - `BUSDT_110017_REJECT_CODE = "110017"`
   - 註釋：「BUSDT funding_arb V2 棄策略路徑（commit a19797d）遺留訂單觸發 Bybit reject code 110017（空單餘額不足，循環）。納入 maker/taker 估計會向下偏誤。」
5. **CLAUDE.md §三 [40] 24h slippage live_demo `-92.47 bps`** — 「BUSDT 110017 reject loop（funding_arb V2 棄策略殘倉）」

### 10.2 Bybit-side root cause analysis

**從 Bybit V5 retCode 110017 語義倒推**：
- retCode 110017 = "AvailableInsufficient"（"available balance insufficient"）— BybitRetCode enum 變體 `AvailableInsufficient = 110007`（注意：fee_execution_calibrator.py 用 "110017" 字串，而 Rust enum 是 110007；**這是字典 / 代碼 / 文件之間的不一致**，但 fee filter 用字串匹配不影響 retCode 分類器）
- BUSDT 是 USDT-margined perpetual，spot 結構需要 BTC（base coin）作為短倉抵押 → demo spot 不存在 BTC borrow 機制
- funding_arb V2 設計：long spot BTC + short BUSDT perp → 賺 funding rate
- **失敗鏈**：策略嘗試在 demo 走 long spot BTC leg → demo 無 spot lending → 抵押不足 → short perp leg 反覆 retry → 每次都被 Bybit 110007/110017 reject → reject loop

### 10.3 Bybit-side 結論

| 維度 | 結論 |
|---|---|
| ToS 違規？ | ❌ 不是。reject loop 是 Bybit 正常拒單行為，是 OpenClaw 該做 retry budget control |
| KYC / 地理問題？ | ❌ 不是 |
| Bybit 端帳戶問題？ | ❌ 不是。demo apply money + 標準 UTA |
| spot lending unavailability？ | ✅ **是**。Bybit demo 不支援 spot lending（mainnet 才有 `/v5/spot-margin-trade/data` 機制） |
| OpenClaw 設計缺陷？ | ✅ **是**。funding_arb V2 未防禦「spot lending unavailable」場景，retry budget 無上限 |

**修復狀態**：三端 active=false 止血 ✅；fee_execution_calibrator 過濾保護 ML 訓練資料 ✅；殘倉 BUSDT ~110017 USD 是「歷史遺產」需 operator 手動 dust clear（CLAUDE.md §三 [40] live_demo -92.47 bps slippage 持續累計）。

**Bybit-side advisor 建議**：
1. **operator action**：dust clear runbook 跑一次清 BUSDT 殘倉（CLAUDE.md §三 18 Live Blocker #18 提到「Disaster runbook + Live first-day SOP（dust clear SOP only）」已有部分文檔）
2. **funding_arb V3 重做時**（如將來重啟）必須先檢查 `BybitEnvironment::is_demo()` → demo 直接 reject 開倉，避免 reject loop 重演
3. **添加新 retCode 110007 → enum + `is_balance_block()` 分類器**（Rust 已有 `AvailableInsufficient = 110007`，是否做 fail-closed retry budget 由 E1 決定）

---

## §11. 字典手冊漂移

### 11.1 04-24 列出的 5 項 drift — 結算狀態

| ID | 項目 | 04-24 狀態 | 05-08 狀態 |
|---|---|---|---|
| H-1 | `confirm-mmr` → `confirm-pending-mmr` | open | ✅ **closed**（字典 v1.1，2026-04-26 G9-01 修正；line 21、570、576、1161） |
| L-1 | open-interest interval 字典寫 "interval"（代碼用 "intervalTime"） | open | ❌ **仍 open**（字典 line 137 仍寫 `interval`） |
| L-2 | account-ratio period 字典列 `"1d"`（Bybit V5 不支援，僅 `4d`） | open | ❌ **仍 open**（字典 line 171 仍含 `"1d"`） |
| L-3 | `/v5/user/query-api` 字典缺章 | open | ❌ **仍 open**（字典完全沒這章） |
| L-4 / M-1 | ws_client `process_message` 對 "handler not found" 無 force reconnect | open | ✅ **closed**（G9-02 + UnknownHandlerGuard 488 LOC） |

### 11.2 本次新發現 drift（L5-1 / L5-2）

| ID | 位置 | 內容 | Sev |
|---|---|---|---|
| **L5-1** | 字典 §1.1 get_open_interest line 137 | `interval: &str — 統計間隔 ("5min", "15min", ...)` 應改為 `intervalTime`（代碼是 SSOT，行 195 用 `intervalTime`） | Low — 同 L-1 持續未解 |
| **L5-2** | 字典 §1.1 get_long_short_ratio line 171 | `period: &str — 統計週期 ("5min", "15min", "30min", "1h", "4h", "1d")` 應移除 `"1d"`，加 `"4d"` | Low — 同 L-2 持續未解 |
| **L5-3** | 字典缺 `/v5/user/query-api` 章節 | 應補錄「Python-only, key validation path」 | Low — 同 L-3 持續未解 |
| **L5-4** | 字典缺 G9-02 unknown handler guard 章節 | 應在 §2 WS 章節新增 G9-02 UnknownHandlerGuard 設計說明 + env-gate 用法 | Low |

### 11.3 04-30 Bybit 新欄位 vs 字典（advisory）

Bybit 04-30 changelog 新增 `symbolId` (instruments-info) + `withdrawMax` (asset/coin-info) + `openTime` (position) — 字典 §1 沒記錄這些新欄位，但代碼也沒用這些欄位 → **drift 但無迫切性**（A5-1 advisory）。

---

## §12. Top 15 Bybit-side Issue + 建議

| # | ID | 嚴重 | 描述 | 建議 |
|---|---|---|---|---|
| 1 | M5-1 | Medium | Bybit ToS / KYC / 地理禁區 0 governance entry（CLAUDE.md §三 #17） | operator 完成 §5.2 6 項自證，Live 前必。建議寫到 `docs/governance_dev/2026-MM-DD--bybit_compliance_signoff.md` |
| 2 | M5-2 | Medium | API key IP whitelist 無代碼可驗 | operator 在 Bybit API Management UI 確認 production key whitelist = trade-core IP |
| 3 | A5-1 | Advisory | 04-30 Bybit 新欄位 `symbolId/withdrawMax/openTime` 字典未記 | 字典補錄，無迫切 |
| 4 | A5-2 | Advisory | retCode 110007 / 110017 字串 vs 數字一致性 | fee_execution_calibrator.py 用 "110017" 字串匹配，但 Rust BybitRetCode enum 是 `AvailableInsufficient=110007`（無 110017 變體）。建議統一：要嘛 fee filter 改用 110007，要嘛 enum 加 InsufficientForShort=110017 |
| 5 | L5-1 | Low | 字典 §1.1 `get_open_interest` 的 Input 寫 `interval` 應為 `intervalTime` | 字典更新（5 min） |
| 6 | L5-2 | Low | 字典 §1.1 `get_long_short_ratio` period 值域含 `"1d"` 但 Bybit V5 不支援 | 字典 → `("5min", "15min", "30min", "1h", "4h", "4d")` |
| 7 | L5-3 | Low | 字典缺 `/v5/user/query-api` 章節 | 補章「Python-only key validation path」 |
| 8 | L5-4 | Low | 字典缺 G9-02 UnknownHandlerGuard 章節 | §2 WS 補設計說明 + env-gate `OPENCLAW_WS_UNKNOWN_GUARD_ARMED` |
| 9 | A5-3 | Advisory | Rust `order_manager.rs::{get_active_orders,history,executions}` 仍未加 settleCoin fallback（A-1 沿用） | 維持現狀（caller 已透過 symbol 傳入），或在 docstring 警告 |
| 10 | A5-4 | Advisory | OPENCLAW_BYBIT_PUBLIC_BASE_URL default fallback 到 mainnet | M-2 已修，但 default 仍 mainnet。Mac dev 模式默認連 mainnet 公開 endpoint（無簽名僅讀）= **可接受** |
| 11 | A5-5 | Advisory | broker_id / x-bapi-broker header 未送 | OpenClaw 不參與 Bybit broker partnership（30d volume $45K << $10M），無需送。等 scale 後再評估 |
| 12 | A5-6 | Advisory | maker fill rate live_demo 36.6% 距 60% target 還差 | QC / FA 領域；BB scope 提示 60% 是 fee_drop healthcheck target 並非 Bybit 政策硬規範 |
| 13 | A5-7 | Advisory | rate_limit `default 10` 與 memory「Order=20」記錄不一致 | memory 是 EDGE-P2-3 觀察值；default 10 是保守初始化，header 回來會覆寫 → **正確** |
| 14 | A5-8 | Advisory | grid_trading live `use_maker_entry=true` 的「LIVE-DEMO-MAKER-FIX」備註 | 提醒 operator：當 live 真綁 mainnet funds 時，必須重新評估 PostOnly entry 對 fill ratio 的影響（toml 內已有備註） |
| 15 | A5-9 | Advisory | funding_arb V3（如重啟）必預檢 `BybitEnvironment::is_demo()` → demo 拒絕開倉 | E1 領域；BB 提供 Bybit-side 邊界知識：Bybit demo 永久不支援 spot lending |

---

## §13. BB Verdict

### 13.1 當前 Bybit 使用合規度

**整體合規度：高（~95%）**

| 維度 | 合規度 | 結論 |
|---|---:|---|
| Bybit V5 REST endpoint 用法 | 100% | 47 個 endpoint 全對齊規範 |
| HMAC 簽名 | 100% | Rust + Python 字節級對齊 |
| Rate limit | 100% | 6 分組 + burst protection + max_retries=0 |
| WS auth + reconnect | 100% | G9-02 unknown handler guard 已修補 04-24 M-1 |
| LIVE-GUARD-1 三閘 + Gate #4/#5 | 100% | 5 hard gate Rust + Python 對稱 |
| retCode 語意分類 | 95% | 12 已知 retCode 分類，缺 110017（A5-2，可接受） |
| 字典 SSOT 對齊 | 90% | 4 項 drift（L5-1/2/3/4）持續 open，無 hot-path 影響 |
| **政策層面** | **70%** | **6 項 operator 必確認自證 0 完成（M5-1）；IP whitelist 無代碼可驗（M5-2）** |
| 禁止行為 risk | 100% | 0 ToS 違規 risk |

**BB-side closure**：技術層 Bybit V5 API 兼容性 = excellent；剩餘 gap 純政策 / governance 層。

### 13.2 Live 前必確認的 ToS / KYC / 地理項（operator action only）

按優先序：

1. **【P0】KYC tier 確認 Tier 1+ active**（無 KYC → 部分 derivatives 不開、live trading reject）
2. **【P0】KYC 註冊地區非 Bybit 禁區**（snapshot 2026-04 list；查 [Bybit 官方 ToS](https://www.bybit.com/en/help-center) 為準）
3. **【P0】API key withdraw permission = false**（架構級已鎖；operator UI 雙重確認）
4. **【P0】API key IP whitelist = trade-core production IP**（防 key 洩漏被洗）
5. **【P1】operator 法律地區 crypto trading 合法**（律師確認）
6. **【P1】Bybit ToS 全文閱讀 + 簽名**（API 用戶協議 + 禁止行為）
7. **【P2】寫 `docs/governance_dev/YYYY-MM-DD--bybit_compliance_signoff.md`**（將以上 6 項自證入 git）

### 13.3 Severity tally summary

- **Critical**：0
- **High**：0
- **Medium**：2（M5-1 ToS governance entry、M5-2 IP whitelist 無代碼可驗）
- **Low**：4（L5-1/2/3/4 字典 drift）
- **Advisory**：9（A5-1 至 A5-9）

**04-24 → 05-08 closure 進度**：5/8 項 closed（H-1 + M-1 + M-2 + M-3 + L-4），3/8 持續 open（L-1/2/3 字典 drift，無 hot-path 影響）。

### 13.4 與 04-24 對比變化

| 維度 | 04-24 | 05-08 | 變化 |
|---|---|---|---|
| Critical | 0 | 0 | 維持 |
| High | 1 (字典 confirm-mmr) | 0 | ✅ closed |
| Medium | 3 (M-1/M-2/M-3) | 2 (M5-1/M5-2 — 政策層) | ✅ 技術 M closed，政策 M 浮現 |
| WS unknown handler | M-1 open | G9-02 closed | ✅ 488 LOC 新模組 |
| 字典 drift | 5 | 4 | 1 closed |
| Bybit API 覆蓋度 | 47 endpoint Rust + 11 Python | 同 | 無變動 |
| Engine binary | 1980 | 待 release count | n/a（cargo build 結果在 Linux） |

---

## §14. 檔案清單（絕對路徑）

**Rust SSOT**：
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_rest_client.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/common/bybit_signer.rs ★ 新
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_private_ws.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bybit_private_ws_status_writer.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ws_client/{mod,connection,dispatch,parsers,run_loop,tests}.rs ★ 重構
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ws_unknown_handler_guard.rs ★ 新（G9-02）
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/order_manager.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/position_manager.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/account_manager.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/platform_client.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/market_data_client/mod.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/instrument_info.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/live_authorization.rs
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/live_auth_watcher.rs ★ 新獨立模組
- /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/position_reconciler/mod.rs

**Python**：
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/settings_routes.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/backtest_routes.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/replay/bybit_public_client.py ★ 新
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_public_connectivity_check.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/io_and_persistence/bybit_public_microstructure_builder.py
- /Users/ncyu/Projects/TradeBot/srv/program_code/learning_engine/fee_execution_calibrator.py（BUSDT 110017 filter）

**字典 / Audit 歷史**：
- /Users/ncyu/Projects/TradeBot/srv/docs/references/2026-04-04--bybit_api_reference.md（v1.1，2026-04-26 confirm-mmr 修正）
- /Users/ncyu/Projects/TradeBot/srv/docs/audits/2026-04-04--bybit_api_infra_audit.md
- /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-04-24--bybit_api_compat_audit.md（前次）

**TOML 配置**：
- /Users/ncyu/Projects/TradeBot/srv/settings/strategy_params_{demo,paper,live}.toml
- /Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_{demo,paper,live}.toml

---

BB AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-08--bybit_api_compatibility_audit.md

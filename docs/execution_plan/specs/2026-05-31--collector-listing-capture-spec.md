# COLLECTOR-LISTING-CAPTURE — 新上市 perp 從第一根 minute kline 即捕捉 spec

**Date**: 2026-05-31
**Author**: PA
**Status**: PA DESIGN — IMPL-ready
**Ticket**: `COLLECTOR-LISTING-CAPTURE`（alpha 資料地基 / D1 授權範圍，非 autonomy 13 模組凍結範圍）
**Scope**: 讓 collector 的 WS kline 訂閱清單由 listing calendar 驅動 — 新上市/PreLaunch perp 在 `listed_at`（理想：PreLaunch 階段）即被訂閱，從第一根 traded minute kline 抓起，解鎖 listing pump-fade alpha 類別
**Trigger**: R-2a feasibility — listing pump-fade alpha 在當前資料**測不了**：有權威 listing SoT（`market.symbol_universe_snapshots.listed_at`，56d 內 52 新上市）但 **0 個被 1m klines 捕捉到上市瞬間**（collector 訂閱清單與新上市集合 disjoint）
**Constraint**: design + read-only；不寫 feature code；不改既有 doc；不碰已 applied SQL（V001-V115）；跨平台無硬編碼；不破壞現有 25-sym 核心採集；fail-closed

---

## §0 E1 該知道的 5 條（最 load-bearing）+ 現狀 file:line

> 先讀這節再讀全文。以下全部 grep 自證（Mac 唯讀，引擎在 `rust/openclaw_engine/src/`），標 [FACT]/[INFER]/[ASSUME]。

1. **[FACT] 訂閱清單是 ticker-driven，不是 listing-driven — 這就是 disjoint 根因。**
   `ScannerRunner::run()` loop（`scanner/runner.rs:114-349`）每 `scan_interval_secs` 拉一次全 linear perp ticker（`runner.rs:144` `get_tickers("linear", None)`），評分 → hard filter → correlation filter → `registry.apply_scan_result()`（`runner.rs:213`）→ 對 added/removed symbol 發 `WsTopicChange::Subscribe/Unsubscribe`（`runner.rs:222-235`）。WS supervisor（`main_ws.rs:40-167`）持有 `WsClient`，從 `symbol_registry.snapshot()` 算 topics。
   **新上市過不了 hard filter**：`hard_filters.min_turnover_24h_usdt = $50M`（`scanner/config.rs:136-138`）。剛上市 perp 的 24h turnover ≈ 0，被 `score_ticker_with_policy_opportunity_and_cost`（`runner.rs:172`）淘汰 → 永遠不進 active universe → 永遠不訂閱。等它累積到 $50M turnover 時 pump 早已過（R-2a：5 個有 kline 的新上市都 +8~126h 才開始）。

2. **[FACT] listing SoT 已存在且活躍，但只在 Python cron，Rust 完全不讀它。**
   `market.symbol_universe_snapshots`（schema `V058:31-50`）由 **Python cron** 每小時寫（`helper_scripts/cron/ref21_symbol_universe_snapshot_cron.sh` → `helper_scripts/db/ref21_backfill_v058_v059.py`）。`listed_at` = Bybit instruments-info `launchTime`（`ref21_backfill_v058_v059.py:201`）。cron 抓的 status 已含 **PreLaunch**（`STATUSES="Trading,PreLaunch,Delivering,Closed"`，cron script + `ref21_backfill_v058_v059.py:32`）。`symbol_universe_snapshots` 在 Rust 側 **0 reader**（`grep symbol_universe_snapshots rust/ = 0`）。

3. **[FACT] Rust 已每 4h 拉 instruments-info，但丟棄了 launchTime/status。**
   `InstrumentInfoCache::refresh(client, "linear")` 在 startup + 每 4h（`main_instruments.rs:140` startup；`main_instruments.rs:216-218` `spawn_instrument_refresh` 4h，註解 `main_instruments.rs:16` + `main.rs:592`）拉同一個 `/v5/market/instruments-info` endpoint（與 Python recorder 同源）。但 `SymbolSpec`（`instrument_info.rs:27`）**只存 tick_size/qty_step 等下單規格，不解析 `launchTime`/`status`**（grep SymbolSpec 無 launch/status 欄位）。→ listing 資訊在 Rust 的 4h refresh response payload 內，但被丟。

4. **[FACT] SymbolRegistry 沒有 listing fast-path 注入 API。**
   `SymbolRegistry`（`scanner/registry.rs`）只有兩條入口：`pinned`（靜態，`registry.rs:34`，`new()` 種子 + 永不移除 `registry.rs:84-85`）與 `apply_scan_result()`（評分驅動 `registry.rs:98`）。無「外部強制 add 一個 symbol（繞過 hard filter）」的 API。新上市 capture 需要一條**新的、繞過 turnover hard filter 的注入路徑**（見 §3 設計）。

5. **[FACT] kline retention 已是 365 天 — operator「延長 retention」考慮點實際已滿足；真限制是 forward accumulation。**
   `market.klines` 是 hypertable（`V002:121-139`），retention policy = **365 days**（`V006:66 add_retention_policy('market.klines', INTERVAL '365 days')`），compression 14d（`V006:32`）。R-2a 報告的「klines 窗僅 ~56d」是 **runtime 實際資料量**（系統 2026-04-05 起採集，至今 ~56d），**不是 retention 上限**。→ 「kline retention 延長給未來長歷史策略」這個需求**對 perp 1m 已不需要動 schema**（見 §4，唯一可選微調 = listing-capture 新 symbol 的 finer-granularity 不要被同表 365d 拖累儲存，但這是 nice-to-have 非 blocker）。**真正的牆 = forward accumulation + 不可 retro-backfill**（§5）。

**E1 開工第一步（強制）**：在可讀 build worktree（Linux `trade-core` 或同步後的 build checkout）`grep -n SymbolSpec rust/openclaw_engine/src/instrument_info.rs` 確認 `SymbolSpec` 欄位 + `refresh()` 內 parse 點（本 spec 在 Mac scoped checkout 已讀到結構，但 launchTime parse 的精確插入點以 build tree 為準）。

---

## §1 現狀全景（訂閱清單怎麼決定，附 file:line）

### §1.1 兩個獨立的 symbol 數字（澄清 README「650+」vs 實際 ~142 vs 25）

| 數字 | 含義 | 來源 file:line |
|---|---|---|
| **~650** | Bybit linear perp 全集（README 行銷數字） | `get_tickers("linear", None)` 每 cycle 拉到的 `total_universe`（`runner.rs:144,153`）— 是**評分輸入池**，非訂閱集 |
| **25** | active universe 上限（含 pinned） | `default_max_symbols()=25`（`config.rs:89-91`）；`max_dynamic = 25 - pinned.len()`（`runner.rs:198`） |
| **2** | pinned（永遠訂閱、永不移除） | `default_pinned_symbols()=["BTCUSDT","ETHUSDT"]`（`config.rs:93-95`） |
| **~142** | R-2a 觀察到的 kline watch-list（>25） | [INFER] 25 active universe × 訂閱倍數 + 跨 supervisor restart 殘留 + 開倉中 symbol 不被移除（`runner.rs:207-219` `open_positions_or_active_universe_on_unknown`）。實際數字隨 runtime 浮動；**不影響本 spec 設計**（disjoint 根因是 hard filter，不是 watch-list 大小） |

### §1.2 訂閱集 → topics 的生成（兩種模式）

`spawn_ws_supervisor`（`main_ws.rs:57-86`）依 `config.enable_extended_ws` 分兩路：

- **extended 模式**（`main_ws.rs:58-78`）：每 symbol `full_subscription_list(sym)` = kline 1m/5m/15m/60m + ticker + orderbook.50 + publicTrade = **8 topics/symbol**
  - [FACT-DOC-DRIFT] `multi_interval_topics.rs:57-62` `DEFAULT_INTERVALS` 實際是 **4 個 interval（1/5/15/60）**，但 Bybit API ref `2026-04-04--bybit_api_reference.md:1101` 寫「kline×6 → 9/symbol」。代碼是 4 interval → 7 或 8 topics/symbol（視 AllLiquidation 是否啟用，預設不啟用 per ref:1099）。**E1 以代碼 `DEFAULT_INTERVALS` 為準，ref doc 標 cleanup debt（不在本 spec 範圍改）**。
- **minimal 模式**（`main_ws.rs:80-86`）：每 symbol `kline.1.{sym}` + `publicTrade.{sym}` = **2 topics/symbol**

**關鍵**：listing-capture 至少要 `kline.1.{sym}`（1m kline，第一根 traded minute）。pump-fade alpha 的入場/出場時間尺度需要 finer granularity 嗎？見 §3.4。

### §1.3 動態增刪 → WS 的接線（relay channel）

- `ScannerRunner` 持有 `ws_tx: UnboundedSender<WsTopicChange>`（`runner.rs:105`），發 `Subscribe/Unsubscribe`。
- relay task（`main_scanner_init.rs:147-159`）把 `scanner_ws_rx` 轉發到「當前 WsClient sender」（`current_ws_client_tx`，每次 supervisor restart 刷新 `main_ws.rs:140-141`）。
- supervisor restart（attempt≥1）從 `registry.snapshot()` 重算 topics（`main_ws.rs:102-118`）— 吸收重啟前的增刪。
- **WsClient 內部訂閱分批**：Bybit 限制每批 ≤10 topic（`bybit_api_reference.md:1085`）。WsClient 對 cached subscriptions 重訂閱（`ws_unknown_handler_guard` 章節 + `run_loop.rs`）。

### §1.4 為何「修好就能解鎖 alpha」（因果鏈）

```
新 perp listed_at（含 PreLaunch）
  → [現狀斷點] Rust 不讀 symbol_universe_snapshots / 丟棄 launchTime
  → 等 turnover 累積到 $50M（hard filter）才被 scanner 評分選中
  → 才訂閱 kline → 此時已 +8~126h，pump 已過
  → 1m kline 第一根記錄的是「pump 之後」→ pump-fade alpha 無從測量
```
本 spec 的修法 = **在 hard filter 之前插入一條 listing fast-path**：偵測新 `listed_at`（理想 PreLaunch）→ 立即訂閱 `kline.1`（+ 視需要 finer）→ 從第一根 traded minute 抓。

---

## §2 設計總則（三個可選實作路徑，PA 推薦 Path B）

listing 偵測有三個資料源可選，trade-off 不同：

| Path | listing 偵測源 | 優點 | 缺點 | PA 評 |
|---|---|---|---|---|
| **A** | Rust 直接 query `market.symbol_universe_snapshots`（Python cron 已寫） | 復用既有 SoT；含 PreLaunch；無新 REST | Rust engine 新增 PG 讀依賴（engine 目前對 market schema 多為**寫**）；cron 每小時 → 最差 ~1h 偵測延遲；跨進程耦合（cron 掛則瞎） | 可行但耦合 cron |
| **B（推薦）** | Rust 4h instrument refresh 已拉的 response **新增 parse `launchTime`+`status`** + 縮短偵測 cycle | 0 新 REST endpoint（同 `/v5/market/instruments-info`）；engine 自包含（不依賴 Python cron 存活）；PreLaunch status 直接拿；對齊原則 14「零外部成本可運行」 | 需改 `SymbolSpec` + `refresh()` parse；4h cycle 太慢需新增 listing-poll cycle | **最小耦合 + 自包含 + fail-closed 最易** |
| **C** | 新 WS topic 或新 REST poller 專拉 listing | 最即時 | 新 infra；Bybit 無 listing-push WS topic（[ASSUME] 待 BB 證）；重複造輪 | 過度設計，否決 |

**PA 裁定：Path B**。理由：
1. **自包含**（原則 14）：engine 不依賴 Python cron 存活就能 capture listing；cron 仍照常寫 SoT 供 replay/研究（兩者互補不衝突）。
2. **0 新外部成本**：同一個 instruments-info endpoint，engine 已每 4h 打，只是丟了 launchTime/status。
3. **PreLaunch 直接可得**：instruments-info response 的 `status` 欄位含 `PreLaunch`（Python recorder 已證 `ref21_backfill_v058_v059.py:182,192`），MIT 注意到的 2 個 PreLaunch symbol 用此源直接偵測。
4. **fail-closed 最易**：偵測失敗 = 不 add symbol = 退回現狀（純 additive，不破壞 25-sym 核心）。

Path A 作為 **fallback / 交叉驗證**保留（§3.5）：若 B 的 listing-poll 失敗，可選讀 cron 寫的 SoT 補。但 MVP 只實作 B。

---

## §3 Path B 詳細設計（IMPL 主體）

### §3.1 新增 listing detector（新模組，Rust-first）

新目錄 `rust/openclaw_engine/src/listing_capture/`（0 既有檔重疊），mirror M3 `metric_emitter` / M7 `decay_detector` 的 spawn pattern：

- **`listing_capture/mod.rs`**：`ListingCaptureConfig` + `spawn_listing_capture(...)` task。
- **`listing_capture/detector.rs`**：核心偵測邏輯（純函數可單測）。
- **`listing_capture/state.rs`**：in-memory 已 capture ledger（防重複 add；class-level by symbol）。

**偵測 cycle**（獨立於 4h instrument refresh，因為 4h 太慢）：
- poll 間隔 = `OPENCLAW_LISTING_POLL_SECS`（預設 **300s = 5min**，env-overridable；trade-off：listing pump 可能秒級，但 5min 偵測 + 立即訂閱後第一根 1m kline 仍能抓到上市後極早期；PreLaunch 預訂閱則完全無延遲）。
- 每 cycle 呼 `client.get(/v5/market/instruments-info, category=linear)` 取全集（或復用 `InstrumentInfoCache` 的 raw payload，見 §3.3）。
- 對每個 instrument 取 `(symbol, status, launchTime)`：
  - **PreLaunch**：`status == "PreLaunch"` → 立即 pre-subscribe（理想路徑，pump 前就在線）。
  - **新上市**：`launchTime` 在 `now - LISTING_CAPTURE_WINDOW` 內（預設 window = **48h**，env `OPENCLAW_LISTING_CAPTURE_WINDOW_SECS`）且 symbol 尚未在 capture ledger → 立即 subscribe。
  - 已在 ledger / launchTime 超出 window → skip。

### §3.2 注入訂閱（新 SymbolRegistry API）

`SymbolRegistry` 新增 **listing-capture 注入路徑**（繞過 turnover hard filter，但仍受總量上限保護）：

```
// 設計契約（非最終簽名，E1 定）
impl SymbolRegistry {
    /// listing-capture 強制 add：繞過 scanner 評分/hard filter，
    /// 但計入一個獨立的 capture 配額（不擠佔 25-sym 交易 universe）。
    /// 回傳是否實際新增（已存在 / 配額滿 → false）。
    pub fn add_listing_capture(&self, symbol: &str, now_ms: u64) -> bool;
    /// listing capture 到期移除（capture window 過 / 升格為正常 scanner symbol）。
    pub fn remove_listing_capture(&self, symbol: &str) -> bool;
}
```

**關鍵設計：listing-capture symbol 與交易 universe 隔離（防污染原則）**
- listing-capture 是**純資料採集**，不應自動讓該 symbol 變成可交易（新上市波動極大，未經 edge 驗證直接交易違反原則 4/5/16）。
- 兩種隔離方案，PA 推薦 **方案 1**：
  - **方案 1（推薦，capture-only 旗標）**：registry 內部分兩集合 `trading_symbols`（scanner 選的，餵 strategy pipeline）與 `capture_only_symbols`（listing-capture 的，**只訂閱 WS / 寫 klines DB，不餵 strategy intent**）。`snapshot()` 給 WS supervisor 回**聯集**（兩者都訂閱）；給 strategy pipeline 的路徑只回 `trading_symbols`。
  - 方案 2（簡單但危險）：直接 `add_listing_capture` 進 active universe → 新上市立刻可交易。**否決**（原則 5：未驗證波動標的不開倉）。
- E1 必須確認 strategy pipeline 從 registry 取 symbol 的路徑（`registry.snapshot()` 的 consumer），保證 capture-only symbol 不漏進 intent 生成。**這是 E2 重點審查 #1**。

### §3.3 與既有 InstrumentInfoCache 的關係

兩個選項：
- **選項 a（推薦，最小改動）**：listing detector 自己 poll instruments-info（5min cycle），與 `InstrumentInfoCache.refresh()`（4h）並存。detector 只關心 `(symbol, status, launchTime)`，不碰 SymbolSpec。
- 選項 b：擴 `SymbolSpec` 加 `launch_time_ms: Option<u64>` + `status: String`，4h refresh 順便存，detector 讀 cache。**缺點**：4h cycle 太慢，仍需獨立 poll；改 SymbolSpec 觸及下單熱路徑（高風險，副作用大）。

**PA 裁定選項 a**：detector 獨立 poll，**不改 SymbolSpec**（避免污染下單熱路徑 instrument cache）。新上市的下單規格（tick_size 等）由既有 `ensure_symbol` lazy-fetch 路徑（`instrument_info.rs:424`）在真要下單時才拉 — 但 capture-only symbol 不下單，所以 detector 連 SymbolSpec 都不需要。

### §3.4 finer granularity 決策（kline 1m 是否足夠）

R-2a / operator 問：listing pump 可能秒級，要不要更細？

- Bybit public WS kline 最細 = **1m**（`KlineInterval` 無 sub-minute，`multi_interval_topics.rs:31-40`；Bybit V5 kline interval 最小 1）。
- 要秒級只能靠 **`publicTrade.{sym}`**（逐筆成交，`multi_interval_topics.rs:118` + ref:1092）— 已在 minimal/extended 訂閱集內。
- **PA 裁定**：listing-capture 訂閱 = **`kline.1.{sym}` + `publicTrade.{sym}`**（2 topics）。
  - `kline.1` 給結構化 OHLCV（落 `market.klines`）。
  - `publicTrade` 給秒級 tick（pump 的微觀結構，落 `market.trade_agg_1m` 或既有 trade writer 路徑）。
  - **不訂閱 orderbook.50**（listing 初期深度噪音大、訂閱配額貴、研究價值低）— 除非 BB/QC 後續要求。
  - 此 2-topic 集足夠未來做 pump-fade alpha 研究（1m bar + 逐筆）。

### §3.5 fail-closed 行為

| 失敗點 | 行為 | 理由 |
|---|---|---|
| instruments-info poll 失敗（timeout/retCode≠0） | skip cycle，不 add，下 cycle 重試 | 原則 6：不確定 → 不擴張訂閱（退回現狀，0 風險） |
| launchTime 缺失/不可 parse | 該 symbol skip（不 add） | 寧漏抓不亂抓 |
| capture 配額滿 | 不 add 新的（既有 capture symbol 不動） | 配額保護見 §3.6 |
| WS subscribe send 失敗 | warn，relay drop（同既有 scanner 路徑 `runner.rs:226`） | 既有 fail-soft 模式一致 |
| detector task panic | 不影響 scanner / WS supervisor / 交易主路徑（獨立 spawn） | 隔離原則；listing-capture 是 additive 旁路 |

### §3.6 Bybit WS 訂閱配額（rate limit / 上限保護）— BB 重點

[FACT] Bybit public WS：每批訂閱 ≤10 topic（`bybit_api_reference.md:1085`）。WsClient 已分批處理。
[ASSUME] **每連接總訂閱數上限 + 連接數上限**：`bybit_api_reference.md:1079-1115` **未記載** per-connection topic 總數上限。Bybit V5 官方文檔 public WS 對 args 數量有上限（歷史上 ~10/批，但單連接累計上限需確認）。**這是 BB 必查項 #1**：
- 現狀訂閱量：~142 symbol（[INFER]）× 8 topics（extended）≈ **~1136 topics** 已在單連接（或多連接？需 BB 確認 WsClient 是否多連接）。
- listing-capture 新增：capture 配額 `OPENCLAW_LISTING_CAPTURE_MAX`（預設 **20 symbol** × 2 topics = 40 topics）。
- **總量 = ~1176 topics**。BB 必須確認：(a) Bybit public WS 單連接是否容得下；(b) 是否需要 listing-capture 開獨立 WS 連接；(c) 訂閱/取消的 rate（連續 subscribe 是否觸發 connection-level rate limit）。
- capture 配額是**硬上限**（fail-closed）：滿了就不再 add，等舊的到期釋放（§3.2 `remove_listing_capture`）。

### §3.7 capture symbol 生命週期（防 deadlock — 沿用 first-detection deadlock 教訓）

[教訓] PA memory `project_first_detection_deadlock_pattern` + M7 spec §5：任何「進得去出不來」的狀態 = 永久佔用 bug。listing-capture symbol 必須有明確退出：
- **退出條件 1**：capture window 過期（listed_at + `OPENCLAW_LISTING_CAPTURE_HOLD_SECS`，預設 **7 天**）→ `remove_listing_capture` → 取消 WS 訂閱（除非它同時被 scanner 選中成 trading symbol，見退出條件 2）。
- **退出條件 2**：該 symbol turnover 漲到過 scanner hard filter，被 `apply_scan_result` 正常選中 → **升格**為 trading symbol（從 capture_only 移到 trading 集合），WS 訂閱無縫銜接（topics 已在線）。
- **append-only ledger**：capture/remove 事件落 log（audit），in-memory ledger 防重複 add。
- 退出後該 symbol 的歷史 klines **保留**（365d retention，§4）— 這正是 alpha 研究要的歷史。

---

## §4 kline retention（operator 考慮點 — 多為「已滿足」）

| operator 考慮點 | 現狀 | 結論 |
|---|---|---|
| kline retention 延長給長歷史策略 | `market.klines` retention = **365 天**（`V006:66`），compression 14d（`V006:32`） | **已滿足**，perp 1m 不需動 schema |
| capture-only symbol 不要塞爆 klines 表 | 全 symbol 共用 `market.klines`；20 capture symbol × 1m × 7d ≈ 20×10080 = 201,600 rows，相對 47.7M 全表（R-2a basis-panel 報告數字）微不足道 | **無需隔離表**；365d retention 自然清理 |
| 未來 multi-day/長歷史策略 | 既有 365d 已覆蓋一年 | 若未來要 >365d，是**獨立 ticket**（archive 到 NAS / cold storage），不在本 spec |

**[可選 nice-to-have，非 MVP blocker]**：若要 capture-only symbol 的 publicTrade 秒級 tick 保留更久（pump 微觀結構研究），可評估獨立 retention，但 trade_agg_1m 已 90d（`V006:62`）足夠 forward 研究窗。**MVP 不動任何 retention SQL**。

**→ §4 結論：本 spec MVP 無需新 migration。** 若 BB/QC 後續要求 capture audit ledger 落 PG（而非僅 in-memory + JSONL），才需 **V118**（V116=M7、V117=ADR-0046 funding_arb 已保留，per git log `7aeaad2b`）。MVP 用 in-memory ledger + 既有 audit JSONL 即可。

---

## §5 forward-accumulation 現實（明寫 — 這是 seed-now-harvest-Q4 投資）

**[FACT] 即使本 spec 完美 IMPL，listing pump-fade alpha 也不能立即測。**

- **不可 retro-backfill**：`market.klines` 從 **2026-04-05** 起採集（R-2a + basis-panel 報告：47.7M rows since 2026-04-05），過去 52 個新上市的**上市瞬間 1m kline 沒存**，Bybit public kline REST 雖可拉歷史，但 (a) 對已下市/PreLaunch 不可得，(b) 即使拉到也不是「我們系統當時的訂閱 capture」，研究 provenance 不純。**internal data 沒存 = 不可能 retro。**
- **forward accumulation 時程**：listing fade 策略要統計顯著需 **n ≥ 30** crypto-perp 上市捕捉。
  - [FACT] R-2a：56d 內 52 新上市（含 PreLaunch/低流動性多數）。
  - [INFER] 扣除無實質 pump 的（穩定幣 perp、極低流動性、迅速下市），**有效 pump-fade 樣本** 估 ~6-10/月。
  - n≥30 有效樣本 → 約 **5-6 個月**（~Q4 2026，2026-10~11）。
- **這不是即時 edge**：本 spec 是**資料地基投資**。修好後 Q4 才有足夠樣本給 QC/MIT 做 Stage 0R replay 驗 alpha。在 P0-EDGE-1（現有 5 策略結構性 alpha 不足）未閉合的背景下，這是**開闢新 alpha 類別的種子**，不是現有策略的修復。
- **里程碑（建議 TODO 標記）**：
  - D+0：IMPL + deploy，開始 forward capture。
  - D+14：healthcheck — 確認有新上市被 capture（`market.klines` 出現 launchTime±5min 內的第一根 bar）。
  - ~D+90：中期樣本盤點（n≈15-25？）。
  - ~Q4 2026：n≥30，QC/MIT alpha feasibility re-run。

**誠實標記**：本 spec 交付的是「能 capture」的機制，**不交付 alpha 證明**。alpha 是否存在要等 Q4 樣本 + QC/MIT 獨立驗（可能驗出無 edge — 屆時 capture 機制仍有殘值供其他 listing-based 研究）。

---

## §6 副作用清單（PA 必答）

| 問題 | 答 |
|---|---|
| 有沒有其他模塊 import 改動的檔？ | 新模組 `listing_capture/` **0 既有檔重疊**。唯一改既有檔 = `SymbolRegistry`（新增 2 個 method，additive）+ `main.rs`/`main_instruments.rs`（新增一個 spawn）。SymbolRegistry 的 consumer：WS supervisor（`main_ws.rs`）、ScannerRunner（`runner.rs`）、position reconciler（`main_scanner_init.rs:51` 註解列舉）、strategy pipeline。**capture-only 隔離必須對所有 consumer 正確**（§3.2 + E2 #1）。 |
| 改動的函數在哪些測試被 mock？ | `SymbolRegistry` 有單測（`registry.rs:457` `test_max_symbols_cap` 等）。新 method 需新單測（capture 配額、升格、到期移除、deadlock-free）。detector 純函數可單測（PreLaunch/launchTime window 判定）。 |
| 是否涉及 asyncio/threading 混用邊界？ | detector 是純 Rust tokio task（無 Python）。`SymbolRegistry` 內部已 thread-safe（`RwLock`，`registry.rs:227` 同類 pattern）。新 method 維持同步鎖語意，**不可跨 await 持鎖**（沿 `runner.rs:163-165` 教訓）。 |
| 是否改 API response schema？ | **否**。0 FastAPI endpoint 改動（除非後續要 GUI 顯示 capture 列表 = 獨立 ticket）。 |
| 是否觸 RustEngine↔Python IPC schema？ | **否**。detector 純 Rust 內部。不新增 IPC method。 |
| 是否觸硬邊界？ | **0 觸碰**。capture-only symbol **不下單、不開倉、不餵 strategy intent**（§3.2 方案 1）→ 不涉 live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / authorization.json / Decision Lease。純資料採集旁路。 |
| 新 singleton？ | detector state（in-memory ledger）若為 singleton 需註冊 singleton authority table（per CLAUDE.md §九）。建議用 task-local Arc 而非全域 singleton（避免註冊負擔）。 |
| sqlx / migration？ | MVP **0 migration**（§4）。若後續 capture ledger 落 PG → V118 + PG dry-run double-apply（feedback_v_migration_pg_dry_run）。 |

---

## §7 16 根原則合規（自檢）

| # | 原則 | 本 spec |
|---|---|---|
| 1 單一寫入口 | capture-only 不下單，不碰執行入口 ✅ |
| 4 策略不繞風控 | capture symbol 不餵 strategy intent，不存在繞風控問題 ✅（§3.2 #1 隔離） |
| 5 生存>利潤 | **明確否決**「capture 即可交易」（方案 2），未驗證波動標的不開倉 ✅ |
| 6 失敗默認收縮 | 所有失敗點 fail-closed = 不 add（§3.5）✅ |
| 8 可解釋 | capture/remove 落 audit ledger ✅ |
| 10 認知誠實 | §5 明寫「交付機制非 alpha 證明」+ FACT/INFER/ASSUME 標記 ✅ |
| 14 零外部成本可運行 | Path B engine 自包含，不依賴 Python cron / 外部服務 ✅ |
| 16 組合級風險 | capture symbol 隔離於交易 universe，不影響 portfolio 風險 ✅ |

**硬邊界**：無。capture-only 旁路不觸任何 fail-closed 授權面。

---

## §8 跨平台合規

- 0 硬編碼路徑：所有 config 走 env（`OPENCLAW_LISTING_POLL_SECS` 等），fallback 用相對路徑或既有 `OPENCLAW_*` base dir 慣例（同 `main_scanner_init.rs:98-104` pattern）。
- 復用既有 `BybitRestClient`（已跨平台）。
- 0 Linux-only assumption。Mac 部署 ready。

---

## §9 role chain + 工時估

**chain**：`PA spec（本檔）→ E1 Rust IMPL → E2 → E4 → BB（WS 訂閱面）→ deploy`

| 階段 | 工作 | 估時 | 並行 |
|---|---|---|---|
| **E1** | `listing_capture/` 新模組（detector + state + mod）+ `SymbolRegistry` 2 method + spawn 接線 | ~12-16h | 見下波次 |
| **E2** | 對抗性審查（重點 §10 三項）| ~3-4h | E1 後 |
| **E4** | regression（registry 單測、detector 純函數測、deadlock-free proptest、capture-only 不漏進 intent 的整合測）| ~3-4h | E2 後 |
| **BB** | Bybit WS 訂閱配額（§3.6）：單連接總 topic 上限 / 是否需獨立連接 / subscribe rate / retCode fail-closed | ~2-3h | **與 E2/E4 可並行**（BB 查的是 Bybit 側約束，不依賴 IMPL 細節） |
| **deploy** | `restart_all.sh --rebuild --keep-auth`（純 Rust 改動）+ D+14 healthcheck 排程 | ~1h | 全綠後 |

**E1 dispatch 波次（最大並行）**：
- **W1（並行 2 E1）**：
  - E1-a：`listing_capture/detector.rs` + `state.rs`（純邏輯，可獨立單測，**不碰既有檔**）。
  - E1-b：`SymbolRegistry::add_listing_capture/remove_listing_capture` + capture-only 隔離（改 `registry.rs`，**獨立檔**）。
- **W2（串行末，1 E1 組裝）**：`listing_capture/mod.rs` `spawn_listing_capture` + `main.rs`/`main_instruments.rs` 接線（依賴 W1 兩者）+ WS topics 用 `kline.1` + `publicTrade`（復用 `multi_interval_topics`）。
- file overlap：W1 兩 E1 0 重疊；W2 串行避免 main.rs / registry.rs 競爭。

**LOC 估**：~400-550 全 Rust（detector ~150 / state ~80 / registry 2 method + 隔離 ~120 / mod+spawn ~100 / 接線 ~50）。

---

## §10 E2 重點審查 3 項（高風險點）

1. **capture-only symbol 絕不漏進 strategy intent（最關鍵）**：grep 所有 `registry.snapshot()` consumer，確認餵 strategy pipeline 的路徑只取 `trading_symbols`，capture_only 只到 WS supervisor + klines writer。**漏一個 consumer = 新上市直接被交易 = 違反原則 5**。要求 E1 附 call-path grep proof（哪些路徑取 trading-only、哪些取聯集）。
2. **deadlock-free 生命週期**：capture symbol 必有退出（window 過期 / 升格），驗證無「進得去出不來」（沿 first-detection deadlock 教訓）。proptest：random capture/expire/promote 序列後 registry 不殘留 phantom symbol、配額正確釋放。
3. **fail-closed + 不破壞 25-sym 核心**：detector panic / poll 失敗 / 配額滿 時，scanner + WS supervisor + 交易主路徑完全不受影響（detector 是隔離旁路）。驗證 capture 路徑與 pinned/scanner 路徑在 registry 內互不干擾（capture symbol 不佔 25-sym 配額、不被 anti-churn 誤移、不擠掉 trading symbol）。

---

## §11 BB 重點（WS 訂閱面，§3.6 展開）

1. **單連接總 topic 上限**：現狀 ~1136 topics（[INFER]）+ capture 40 = ~1176。Bybit public WS 單連接容得下嗎？需查 Bybit V5 官方 public WS args 上限（`bybit_api_reference.md:1079-1115` 未載，BB 補錄到該 ref）。
2. **是否需獨立 WS 連接**：若單連接逼近上限，listing-capture 開獨立連接更安全（隔離，capture 抖動不影響交易 WS）。
3. **subscribe rate**：連續 subscribe 多個新上市（PreLaunch 批量）是否觸發 connection-level rate limit。
4. **retCode fail-closed**：listing-capture 的 instruments-info poll 若 retCode≠0，fail-closed 不重試（CLAUDE.md 硬邊界，沿 `instrument_info.rs:206-214` 既有 pattern）。
5. **PreLaunch 訂閱可行性**：對 `status=PreLaunch` 的 symbol，Bybit public WS `kline.1`/`publicTrade` 訂閱是否會返回 "handler not found"（毒化連接，沿 2026-04-05 liquidation topic 教訓 `bybit_api_reference.md:1104-1106`）。**這是 BB 必須 24h 隔離 probe 的項**（mirror W-AUDIT-8a C1 liquidation topic probe），確認 PreLaunch symbol 訂閱安全後才放進 production 訂閱集。

---

## §12 NO-OP / 既有性確認

- `git fetch --all` 已執行（2026-05-31）。
- 無既有同名 spec（`docs/execution_plan/specs/2026-05-31--collector-listing-capture-spec.md` 此前不存在）。
- `git log --all | grep` 無既有 `listing.capture` / `collector.listing` ticket。
- 無既有 listing-capture branch。
- → NO-OP exit 不觸發，本 spec 為首版。

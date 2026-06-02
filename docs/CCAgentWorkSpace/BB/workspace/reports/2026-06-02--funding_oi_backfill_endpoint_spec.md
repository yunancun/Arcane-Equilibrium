# BB Spec — Funding + OI History Backfill Writer（V125 fill）

**日期**：2026-06-02 | **作者**：BB（三方驗證 Bybit 官方 doc↔字典↔code）| **狀態**：spec，待 E1 實作
**目標**：回填 funding rate + open interest 歷史到 V125 `research.alpha_funding_rates_history` + `research.alpha_open_interest_history`（目前空），20 liquid perp（同 `settings/backfill_universe.toml`），~18 個月。多日持倉策略成本模型 + listing fade 成本精算的 P0 基礎。
**實作模板**：已部署的 `rust/openclaw_engine/src/backfill/` + `bin/daily_kline_backfill.rs`（commit 0f19c861）。PA 跳過：擴展 proven backfill 模式非新架構。

## 1. Funding history — `GET /v5/market/funding/history`
- params：`category=linear`、`symbol`（必）；`startTime`/`endTime`/`limit`（選）。**limit max/default = 200/200**。
- **分頁 = time-window ONLY（無 nextPageCursor）**。**關鍵約束：只傳 startTime 會 error**；傳 endTime（或 both/neither）。
- response 欄位：`symbol`、`fundingRate`(string)、`fundingRateTimestamp`(string ms)。
- 分頁方向（E1 必守）：**walk endTime backward**——每頁傳 `endTime=cursor_end`，下頁 `cursor_end = (該頁最早 fundingRateTimestamp) − 1`。形狀同 `paginate_daily_klines` 的 shrinking-end（daily_kline_backfill.rs:251-316），抄同三 fail-closed 終止（空頁/游標不推進/MAX_PAGES）。
- 請求數：8h 結算 → ~1644 events/symbol → 9 pages/symbol → 20 symbol = **~180 req**，sequential。
- client：**已 READY** `get_funding_history(category,symbol,start,end,limit)`（mod.rs:254-299，已送 startTime/endTime/limit）。signed GET via demo slot（非 no-auth）。Market group 120 req/s。

## 2. Open interest — `GET /v5/market/open-interest`
- params：`category=linear`、`symbol`、**`intervalTime`**（必）；`startTime`/`endTime`/`limit`/`cursor`（選）。**limit max/default = 200/50**（注意 default 50 非 200）。
- **intervalTime 建議 = `1h`**（18mo=~13140 點/symbol → 66 pages/symbol → ~1320 req；1d 太粗抓不到 intraday OI delta=cascade 信號；1h 是量/粒度甜點）。
- 分頁 = **cursor + time-window 都有**。response 欄位：`openInterest`(string)、`timestamp`(string ms)。lookback 到 symbol launch time。
- **client NOT READY，E1 須擴展**：現 `get_open_interest(category,symbol,interval,limit)`（mod.rs:184-219）只送 category/symbol/intervalTime/limit，**無 startTime/endTime/cursor**。E1 加這三參數，然後 walk endTime backward（統一形狀，避免兩套分頁路徑）+ nextPageCursor 作終止輔助。V125 `alpha_open_interest_history.cursor_lineage` 記 cursor 鏈。
- 請求數 ~1320（@1h），sequential。

## 3. ★ fake-zero 地雷（最高風險，E1 必讀）
funding/OI client 都用 `parse_str_f64`（parsers.rs:24-28，`.unwrap_or(0.0)`）。V125 設 `funding_rate NOT NULL` + `open_interest NOT NULL`（C-3）。E1 須複製 daily-kline 的 strict-parse→reject→coverage-degrade 模式。
**但決定性差異——不可照抄 kline 的 `>0.0` 測試**：
- kline OHLC 結構性 >0，故 0.0=parse-fail 簽名，`is_strict_valid_ohlc` 用 `>0.0`。
- **`fundingRate` 合法為 0.0（低溢價 regime）且合法為負（空付多）**！`>0.0` 會誤拒真資料。
- funding/OI 的 strict 測試 = **「raw JSON 欄位存在 AND parse 為 finite f64」**——區分真 0.0/負 funding vs missing-field default 0.0。**須用回傳 `Option<f64>` 的 strict variant + `is_finite()` 檢查，不用 `parse_str_f64`**。OI 同理：接受任何 finite（不設數值 floor），只 reject missing/unparseable。
- 在 strict-parser doc 註解明寫此差異。**照抄 kline `>0` filter 會靜默丟掉每個 0/負 funding row，污染成本模型向正偏。**

## 4. Timestamp
`fundingRateTimestamp`/`timestamp` 都是 string-encoded ms。E1 parse string→TIMESTAMPTZ；**parse-fail = reject row（不 fallback 1970 epoch）**，mirror writer.rs::utc_from_ms 回 None 跳過（writer.rs:59-61）。假 epoch 污染 PIT 窗口語義。

## 5. V125 schema 映射
**funding → `research.alpha_funding_rates_history`**（PK `(category,symbol,funding_ts,run_id)`）：`funding_rate`(DOUBLE NOT NULL，strict-parse reject-on-fail) / `funding_ts`(fundingRateTimestamp→TIMESTAMPTZ，hypertable time) / `category` / `symbol` / `source_endpoint="GET /v5/market/funding/history"` / `funding_interval_minutes`(選，留 NULL 或從 instruments-info fundingInterval——是 interval 非 cap) / provenance(run_id/parser_version/payload_sha256/request_start/end/fetched_at)。
**OI → `research.alpha_open_interest_history`**（PK `(category,symbol,interval_time,ts,run_id)`）：`open_interest`(DOUBLE NOT NULL，strict-parse) / `ts`(timestamp→TIMESTAMPTZ，hypertable time) / `interval_time="1h"`(TEXT) / `category`/`symbol` / `source_endpoint="GET /v5/market/open-interest"` / `cursor_lineage`(選，記 nextPageCursor 鏈) / provenance。
兩者另寫 run-level `research.alpha_history_ingest_runs` + per-page `research.alpha_history_ingest_pages`（V125 已存，daily-kline 只填 alpha_klines_provenance；funding/OI 的 page ledger 是自然 provenance surface——MIT 確認 target ledger）。複用 V125 preflight `probe_*_table_exists` fail-closed（writer.rs:68-80）。

## 6. Rate/ToS
~180(funding)+~1320(OI@1h)=~1500 req sequential per-symbol，Market 120 req/s ≈0% 利用率零 burst（抄 get_open_interest_batch mod.rs:227 anti-burst）。`wait_if_rate_limited` 自動退避（繼承 get_checked）。read-only market data，0 KYC/geo/wash/rebate 暴露，ToS 合規。**禁跨 symbol 並行**（無益+burst 風險）。

## 7. Cap 紀律（QC guardrail）
本 backfill 回填**已實現** funding history（成本輸入）。cap 是另一回事：SSOT=`upperFundingRate`/`lowerFundingRate`（instruments-info，字典 §167-196）。**E1 禁碰 cap，禁從 `max(fundingRate)` history 反推 cap**（funding_short_v2 錯誤——把 +0.0001 IR floor 誤當 +10.9% APR cap；真 cap 如 BTC +0.5%/8h=+547% APR 在 instruments-info）。cap 出本任務範圍。

## 8. 字典 drift（E1 同 IMPL commit 落地，CLAUDE §八）
1. `docs/references/2026-04-04--bybit_api_reference.md:141`（OI start/end）**DRIFT**：字典列 `start/end` 為 get_open_interest 輸入但實際 client（mod.rs:184）無——E1 擴展 client 後更新 §132-146：client 現送 startTime/endTime/cursor、nextPageCursor 可用、default limit=50/max 200、lookback=launch time。
2. funding §150-163：補 limit default=200、「只傳 startTime 會 error」、time-window 分頁（無 cursor）。

## E1 驗證 checklist（BB next-startup 查）
(1) get_open_interest 擴展 startTime/endTime/cursor + 同 commit 更新字典 §141? (2) strict-parser 用「欄位存在 AND finite」非 kline `>0`，保留真 0.0/負 funding? (3) string→TIMESTAMPTZ fail=reject 非 epoch fallback? (4) 不碰 funding cap? (5) 字典 §132-146/§150-163 分頁/limit 註記同 commit 落地?

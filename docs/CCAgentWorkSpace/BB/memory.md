# BB (Bybit Broker Compatibility Auditor) — Memory

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓（2026-06-10 壓實蒸餾；原條目全文見 memory-archive.md）

- 角色鐵則：BB=Bybit V5 合規審計員（外部視角），READ-ONLY 靜態審計不打交易 API（查證限官方 doc WebFetch / 公開 market curl）；代碼為 SSOT，字典 `docs/references/2026-04-04--bybit_api_reference.md` 配合；每個 verdict 必三方對齊（官方 doc ↔ 字典 ↔ code）。
- Empirical 優先：字典/plan/status 與 BB 自己的舊 verdict 都會 stale（v57「writer BLOCKED」被 PG 實查 31,473 rows 推翻；5/21 Earn path 被 E1c IMPL 證舊）→ 下 verdict 前做 PG/curl/WebFetch 實證，不靠記憶或舊報告。
- Rate limit 不變事實：per-UID Order/Position/Account=20 r/s、Market=120、Asset=5（`/v5/earn/` 與 `/v5/asset/` 共用）、Other=10；per-IP 600 req/5s 違反→403+10min cooldown；WS conn 500/5min；OpenClaw baseline ~0.7 req/s headroom 巨大，REST polling 提案先推 WS-first（tickers topic 已 broadcast fundingRate/openInterest）。
- retCode 鐵則：timeout/非零 retCode 一律 fail-closed 不重試；open 單次（OPEN_NO_RETRY）；NoOp/冪等 upgrade ≠ retry license；duplicate 類（110072、10001+"duplicate"）open fail-closed / close 冪等成功。
- 110017 非零倉專屬碼（三 trigger：無倉/方向反/qty>size）；僅 is_close ∧ reduce_only ∧ qty=0 全平 form ∧ one-way 前提下可本地收斂刪倉；無 guard 裸刪=誤刪真倉災難。
- one-way mode 是 110017 收斂、D2 reconcile、set_trading_stop positionIdx 等多項安全裁決的結構前提；hedge 啟用時全部 mandatory re-review（G-3）。
- 列舉完整性陷阱：`/v5/position/list` default limit=20+nextPageCursor，「不在回應 ≠ 無倉」；streak 防抖動不防穩態截斷；單 symbol 點查不受截斷=安全 gate；proactive reconciler 禁把列舉完整性當 silent 前提。
- 分頁範式：funding/history=time-window 無 cursor（只傳 startTime 會 error，endTime 回溯，limit max/default=200）；open-interest=cursor+window（default limit=50）；統一 shrinking-end 回溯+三閘終止（空頁/游標不進/MAX_PAGES）。
- fake-zero 地雷：`parse_str_f64 .unwrap_or(0.0)`+NOT NULL 欄位 → strict-parse 必用「JSON 欄位存在且 parse 成功」判定而非 >0（funding 合法可 0/負）；timestamp string-ms parse-fail 必 reject 不落 epoch。
- funding cap SSOT=instruments-info `upperFundingRate`/`lowerFundingRate`/`fundingInterval`（per-symbol 0.5~1.0%/8h；interval 可 4h 非全 8h）；IR baseline +0.01%/8h 是 floor 非 cap；禁從 history 樣本窗 max 反推 cap（樣本落 regime 內必誤判）。
- Demo 環境差異：不支援 execution.fast+dcp topic / spot lending / PostOnly silent degradation；demo reject loop=正常拒單非 ToS 違規，屬 retry budget 治理；`BybitEnvironment` 分支是標準處理軸。
- 政策合規長期短板：技術 ~95-98% vs 政策 ~70%；ToS/KYC/地理 governance entry（M5-1）多月 stale=mainnet 解鎖真 ship-stop；16 restricted jurisdictions、KYC Standard L1 足夠 OpenClaw scale、Bybit 不發 1099（CSV 自理且 Account Statement 不含 Earn）、Earn scope 需 2026-04-09 後 key。
- kill/close 順序鐵則：cancel-all → close-position → revoke，per-symbol 0.3s safety margin；DCP 是 backup 非 primary。
- trading-stop/SL：tick 對齊 side-aware（long SL floor / short SL ceil），missing spec→fail-closed skip；Bybit 拒錯側 SL 是拒單非市價平倉，可作 lock-profit fail-closed 兜底，勿加 retry。
- BB 工作慣例：每 verdict 例行查 30d Bybit V5 changelog（迄今 0 breaking change）；report 落 `workspace/reports/`+commit；CRITICAL/operator-action 級同檔複製 `Operator/`；字典補錄走 BB1 backlog 累積清單不即興散修。
- Mac sign-off ≠ runtime：Linux cargo test/--rebuild/PG 復現必列「下次啟動查驗項」；LIVE-GUARD 三閘+五 gate live boundary 永不放寬；LiveDemo 用 live slot 憑證 provenance（is_live_slot 禁 env fallback）但 endpoint=api-demo。

## 近期記錄

## 2026-05-31 funding_short_v2 結構性 NO-GO 斷言 — BB 反證 REJECTED audit cap 詮釋

### Trigger

PM 對抗性質疑 `srv/docs/audits/2026-05-31--funding_short_v2_structural_infeasibility.md` §2.4 的核心斷言：「Bybit linear perp 正側 funding **結構性封頂 +0.01%/8h (+10.9% APR)**，連 memecoin 亦然，0 筆破 30% gate」。PM 懷疑這是低-premium regime 觀察，非結構性 cap。BB 用官方文件 + 實際 curl 查證。

### Verdict: **audit §2.4 結構性封頂斷言 ERRONEOUS（過度詮釋）**。正側 funding **NOT** 鎖在 <30% APR。真實 per-symbol cap 遠超 30%，bull regime 下歷史頻繁破 30%。

### 決定性證據（官方文件 + 實證 curl，非記憶）

1. **官方 funding 公式**（Bybit Help Center, via WebSearch）：
   `F = clamp[ P + clamp(I − P, +0.05%, −0.05%), upperFundingRate, lowerFundingRate ]`
   - I (interest rate) = 0.03%/day = **0.01%/8h**（BTCUSD 例）。premium P≈0 時 `F = clamp(0.01%, ±0.05%) = +0.01%`。
   - ★ **audit 觀察到的「4 symbol 正側 max 全 = 精確 +0.0001」就是 IR baseline，NOT cap**。低-premium regime 下 funding 落在 IR=+0.01% 是公式必然，不是上限。
   - cap 公式係數 0.75（記憶 ±0.75% 方向對但非 cap 本身）：`upper = min((IMR−MMR)×0.75, MMR)`，high-divergence 時 0.75 可調 0.5~1.0。

2. **`/v5/market/instruments-info` 暴露 per-symbol cap 欄位**（audit 完全沒查）：
   - `upperFundingRate` = "Upper limit of funding date"（= 正側 cap，per-symbol 真實欄位）
   - `lowerFundingRate` = 負側 cap；`fundingInterval` = 結算間隔（分鐘）
   - 實 curl api.bybit.com（2026-05-31）：

   | Symbol | upperFundingRate | = APR | fundingInterval |
   |--------|------------------|-------|-----------------|
   | BTCUSDT | +0.005 (0.5%/8h) | **+547.5% APR** | 480 (8h) |
   | SOLUSDT | +0.005 | **+547.5%** | 480 |
   | DOGEUSDT | +0.0058 | **+635%** | 480 |
   | 1000PEPEUSDT | +0.01 | **+1095%** | 480 |
   | WIFUSDT | +0.01 | **+2190%** | 240 (4h!) |

   → 真實正側 cap 是 audit 宣稱「10.9% 封頂」的 **50×~200×**。

3. **歷史反證**（實 curl funding/history，2024 bull 窗）：
   - BTCUSDT 2024-03（突破前高）：n=43 **全部 > +0.0001**，max +0.001128 = **123.5% APR**
   - BTCUSDT 2024-11（川普當選 bull）：max +0.001086 = 118.9% APR，**32/106 筆 > +30% APR**
   - DOGEUSDT 2024-11：max +0.001146 = 125.5% APR，**53/106 破 30%**
   - 1000PEPEUSDT 2024-11：max +0.001228 = **134.5% APR，73/106 (69%) 破 30%**
   → audit「0 筆破 30%」純因 ~66 天樣本落在低-premium regime；換 bull 窗 alt 半數以上時間破門檻。

### audit 其他錯誤

- WIFUSDT fundingInterval=240（4h，一天 6 次結算非 3 次）；audit 用統一 8h×3×365 算 WIF -85% APR 倍率錯（應 ×6×365）。
- audit §2.3「三源一致 max +1.0 bps」只證明**我方 pipeline 無 clamp 且當前 regime 確實低**（這部分 BB 認同，數據忠實），但被誤推成「結構性 cap」。pipeline 忠實 ≠ 結構封頂。

### 對 funding_short_v2 NO-GO 結論的影響

- audit 的 NO-GO **結論可能仍成立，但理由錯**：不是「物理上永遠無法 fire」（bull regime 可破 30%），而是「需賭 bull/high-premium regime，低-premium 期 0 機會 + break-even 160% APR 門檻過高（160% < BTC cap 547% 但 > 多數實際 funding）」。這是 **regime-dependent 低頻策略**，非「數學上永遠不可能」。正確 reframe 應交 QC：策略入場頻率取決於 bull regime 出現頻率 + 160% break-even 在歷史 bull 窗的實際命中率（2024-11 BTC max 118.9% < 160% break-even → 即使該 bull 窗 break-even 仍未過，但 30% 入場 gate 過了 32 次；門檻間 30%~160% 的 gap 是真問題，但屬 QC 成本/門檻設計，非 Bybit 結構封頂）。

### 下次啟動需查驗項

1. audit `2026-05-31--funding_short_v2_structural_infeasibility.md` §2.4 是否更正「結構性封頂 10.9%」措辭（建議標 erratum：cap 是 per-symbol upperFundingRate 0.5%~1.0%/8h，非 +0.01%）。
2. `quant-strategy-design` checklist 建議改為「查 `instruments-info.upperFundingRate` per-symbol cap」而非靠 funding/history 樣本窗 max 推斷 cap（樣本窗會落在 regime 內，必誤判）。
3. 字典手冊 §1 funding 章節是否補 `upperFundingRate`/`lowerFundingRate`/`fundingInterval` 三欄位 + 完整 clamp 公式（含 IR baseline = +0.01% 的 floor 語意，防後續 agent 再犯同樣 cap 誤判）。

---

## 2026-06-02 funding + OI history backfill writer — Bybit endpoint spec for E1 (AEG-S1 V125 fill)

### Trigger
PM 派 BB spec funding-rate + open-interest history backfill writer 的 Bybit 端點語義（QC 多日持倉策略線 P0 基礎，複用已部署 daily_kline_backfill 模式 commit 0f19c861 回填到 V125 research.alpha_funding_rates_history + research.alpha_open_interest_history，目前空）。READ-ONLY，不寫碼。

### 三方核實（Bybit 官方 WebFetch + dict + code）
- **funding/history**：官方確認 = **time-window 分頁（NO cursor）**，limit max=200/default=200，「**只傳 startTime 會 error**；只傳 endTime 回 200 筆 up-till-endTime」。code `get_funding_history(category,symbol,start,end,limit)` 已送 startTime/endTime/limit（mod.rs:254）。8h 結算 → 18mo ≈ 1644 筆/symbol → ⌈1644/200⌉ = **9 頁/symbol** → 20 symbol = **~180 req** 一次性。Market group 120 req/s，sequential 0 burst。
- **open-interest**：官方確認 = **同時有 cursor（nextPageCursor）+ startTime/endTime window**，limit max=200/**default=50**，lookback = symbol launch time。**但 code `get_open_interest(category,symbol,interval,limit)` 只送 category/symbol/intervalTime/limit，NOT start/end/cursor**（mod.rs:184-219）→ dict line 141 列 start/end 是 **drift（client 簽名無此參數）**。OI backfill 需 **E1 擴 client**（加 startTime/endTime/cursor）才能回填歷史窗（與 funding 不同：funding client 已 ready，OI client 不 ready）。
- **intervalTime 建議 = 1h**（多日策略成本模型）：18mo×1h = ~13140 筆/symbol → ⌈13140/200⌉=66 頁/symbol → 20 sym = **~1320 req**；1d = 547 筆/sym = 3 頁/sym = 60 req 但顆粒太粗（成本模型/listing fade 需 intraday OI 變動）。1h 是量/顆粒平衡點。

### 關鍵 BB 發現（spec 交付重點）
1. **【CRITICAL for E1】fake-zero 地雷同 kline**：`get_funding_history` 用 `parse_str_f64(item,"fundingRate")`（parsers.rs:24-28 `.unwrap_or(0.0)`）；`get_open_interest` 用 `parse_str_f64(item,"openInterest")`。V125 C-3 funding_rate/open_interest 都是 NOT NULL；**E1 必複刻 daily_kline strict-parse 範式**：parse-fail → reject row（不寫 0.0），coverage 降 partial/failed。**funding rate 合法可為 0.0/負**（與 OHLC 恆>0 不同）→ strict 判定不能用「>0」，要用「**原始 JSON 欄位存在且 parse 成功**」（區分「真 0.0 funding」vs「缺值 default 0.0」），須在 parser 層分辨 None vs Some(0.0)，不可沿用 kline 的 >0 斷言。OI 同理（OI 可為極小但通常>0；仍以「欄位存在且 parse 成功」為準，非數值門檻）。
2. **funding 分頁方向**：官方「只傳 startTime error」→ E1 分頁必走 **endTime 向後回溯**（cursor_end = 上頁最早 fundingRateTimestamp − 1），與 daily_kline paginate_daily_klines 的 shrinking-end 範式一致；終止三閘（空頁/游標不進/MAX_PAGES）照抄。
3. **OI 分頁有 cursor**：與 funding 不同，OI 可用 nextPageCursor（更穩）或 endTime-window；建議 E1 用 **endTime-window 回溯**（與 funding/kline 統一範式，避免兩套分頁碼）+ cursor 作終止輔助。V125 alpha_open_interest_history 有 cursor_lineage 欄可記。
4. **timestamp 都是 string ms**：funding fundingRateTimestamp / OI timestamp 都是字串毫秒，E1 須 parse → TIMESTAMPTZ（funding_ts / ts），parse-fail reject（不落 1970 epoch，抄 writer.rs utc_from_ms None 範式）。
5. **【cap 紀律】此 backfill 回填已實現 funding history（成本估計）≠ funding cap**。cap SSOT = instruments-info `upperFundingRate`/`lowerFundingRate`/`fundingInterval`（dict §167-196 已記，funding_short_v2 教訓）。**E1 此任務不碰 cap**，禁從 history max 反推。已實現 funding 是成本輸入，cap 是另一個 endpoint（get_instruments_info，目前未拉 cap 欄）。
6. **signed-GET-via-demo**：funding/OI 走 get_checked（HMAC signed GET，demo slot），非 no-auth public（與 daily_kline 同；demo 空憑證 request-time fail-closed，非建構期）。Market group 公共端點但 client 統一簽名。
7. **V125 schema 映射**：
   - funding → alpha_funding_rates_history：funding_rate（DOUBLE NOT NULL，C-3）/ funding_ts（TIMESTAMPTZ from fundingRateTimestamp）/ category='linear' / symbol / source_endpoint='GET /v5/market/funding/history' / funding_interval_minutes（可從 instruments-info fundingInterval 取，或留 NULL；**非 cap**）/ run_id+provenance。PK (category,symbol,funding_ts,run_id)。
   - OI → alpha_open_interest_history：open_interest（DOUBLE NOT NULL，C-3）/ ts（TIMESTAMPTZ from timestamp）/ interval_time TEXT（'1h'）/ category / symbol / source_endpoint='GET /v5/market/open-interest' / cursor_lineage（可記 nextPageCursor）/ run_id。PK (category,symbol,interval_time,ts,run_id)。
8. **rate/ToS**：read-only market data，0 KYC/地理/wash/broker-rebate 風險；180（funding）+1320（OI 1h）req 一次性遠 < Market 120 req/s 持續 cap；sequential per-symbol 0 burst；退避走既有 wait_if_rate_limited（Market threshold=10）。ToS 合規退避重試已由 client 層 fail-closed（retCode!=0 不重試）。

### 字典更新需求（drift）
- **dict line 141 OI start/end 標 client-not-wired**：dict 列 `start/end` 為 get_open_interest input，但 code 簽名無此參。E1 擴 client 加 start/end/cursor 後，同 commit 更新 dict §132-146（標 client 已送 startTime/endTime/cursor + nextPageCursor 分頁 + default limit=50/max=200 + lookback=symbol launch）。**此為 BB 交付的 dict cleanup debt，E1 IMPL 時連帶修**。
- funding §150-163 基本準確；補 limit default=200 + 「只傳 startTime error」+ time-window（no cursor）分頁註。
- 兩者皆「引入新端點用法」（backfill 歷史回溯分頁），E1 IMPL 後須更新 bybit_api_reference.md。

### Verdict: SPEC DELIVERED — funding client ready / OI client 需擴 start+end+cursor / 兩者 fake-zero 須 strict-parse（funding/OI 用「欄位存在且 parse 成功」非 >0）/ cap 不碰。

### 下次啟動需查驗項
1. E1 OI backfill 是否擴了 get_open_interest client 簽名（加 startTime/endTime/cursor）+ 同 commit 更新 dict line 141
2. E1 funding/OI strict-parser 是否用「JSON 欄位存在且 parse 成功」判定（非 kline >0），守住「真 0.0/負 funding」vs「缺值 default 0.0」區分
3. timestamp string→TIMESTAMPTZ parse-fail 是否 reject（不落 epoch）
4. backfill 是否誤碰 funding cap（應只回已實現 history）
5. dict §132-146 OI + §150-163 funding 分頁/limit 註是否同 IMPL commit 更新

---

## 2026-06-07 P2 #6 follow-up — 10001+"duplicate" close-idempotent narrow（接 2026-06-06 110072 裁決）

### Trigger
PM 派 BB 確認 P2 #6 follow-up 交易所側語意：把 `classify_business_retcode` 的 `10001+"duplicate"` 由**無條件 NoOp** 改為 **Structural**，由 consumption 層 `close_dup_is_idempotent_success`（擴為認 110072 OR 10001+duplicate）只 upgrade close path 成冪等成功。即與 110072 完全對齊（open+dup→fail-closed；close+dup→冪等成功）。READ-ONLY。代碼已落（dispatch.rs comment 標 2026-06-07 follow-up），BB 對交易所側語意背書。

### Verdict: **APPROVE**（0 ship-stop；1 字典補錄 LOW 非阻）

代碼已正確 IMPL 且測試完整。三方對齊（Bybit 官方 error doc ↔ dict ↔ code）後 BB 從交易所立場確認方向正確、安全。

### 決定性官方證據（Bybit error doc WebFetch 2026-06-07）
- **110072 = "OrderLinkedID is duplicate"** 是 orderLinkId 重複的**專屬權威碼**。
- **10001 = "Request parameter error"** 泛 InvalidParam。實際 retMsg 變體（github/ccxt corpus）：`"Request parameter error"` / `"order link id is longer than 45"` / `"position idx not match position mode"` / `"invalid order_link_id format"` / `"qty must be > 0"`——**全部不含 "duplicate" 子串**。
- 所有含 "duplicate" 的 Bybit 碼皆**獨立 retCode 非 10001**：110030 "Duplicate orderId" / 110072 "OrderLinkedID is duplicate" / 170141 "Duplicate clientOrderId" / 20006 "reqId is duplicated" / 176021 "Repeated borrowing requests" / 148039 "Duplicate collateral assets" / **10014 "Request is duplicate"**。

### substring 誤判風險裁決（任務核心問題）：**可接受，誤吞面為空**
- 唯一進入 substring 比對的分支是 `ret_code==10001`（close_dup_is_idempotent_success line 412）。官方 10001 的**所有已知 retMsg 變體都不含 "duplicate"** → 不存在「10001+'duplicate' 但語意非 orderLinkId 重複」的官方情境。
- **10014 "Request is duplicate"**（唯一 substring 同形誤判候選）**不會被誤觸**：helper 只 match 110072 與 10001（line 409-412），10014 落 `_ => false`；classify 層 10014 亦落 `_ => Structural`（無 10014 arm）。ret_code gate 先於 substring → 10014 永不進 substring 比對。
- 即使極端：未來 Bybit 在 10001 retMsg 夾帶非-orderLinkId 的 "duplicate" 文字（如 "duplicate parameter"），誤吞**僅限 is_close==true** 場景（open 永遠 fail-closed），且後果是「把一個本該 fail 的 close 當冪等成功」→ 下一 tick close 決策若倉仍在會重發新 id 自然重試/或撞 110017 自癒（與 110072 同自癒機制）。close 側誤吞的 blast radius 遠小於 open（open 誤吞=幻倉，已被 is_close guard 結構性排除）。風險可接受。

### 4 裁決點
1. **open fail-closed 正確**：open+10001-dup（is_close=false）→ helper false → Structural else 分支 → `req.is_primary` → `DispatchFailed{terminal="Rejected"}` + `LeaseOutcome::Failed`（dispatch.rs:972-1006），與 open+110072 同路徑。open 單次無重試（OPEN_NO_RETRY），撞 dup = id 撞歷史 = 開倉未成功，絕不可當成功。正確。
2. **close idempotent-success 正確**：close+10001-dup（is_close=true）→ helper true → 只發 `LeaseOutcome::Consumed`（line 946-951），不發 DispatchFailed、**不收斂本地倉**（noop_is_exchange_zero_position 對 10001 回 false，與 110072 一致；只有 110017 收斂）。鏡像 Ok/NoOp 成功路徑。close retry 撞 dup（首次已達 Bybit、response 丟、retry 重發同 id）= 冪等成功，與 110072 同理成立。
3. **與既有 10001 子串邏輯交互無破壞**：10001 arm 由「duplicate→NoOp / else→Structural」改為一律 `10001 => Structural`（line 272），retMsg 不再在 classify 層被讀；duplicate 偵測下移 consumption 層。10002 的 recv_window/timestamp 子串（line 288-295）是**另一個碼**，完全不受影響。非-duplicate 的 10001（格式錯/qty 非法）正確維持 Structural fail（test_close_dup_is_idempotent_success_close_10001_non_duplicate_false 覆蓋）。
4. **rate-limit / ToS**：0 風險。NoOp/upgrade ≠ retry（無新 REST 流量）；close-dup 冪等收尾不增 Order group 用量。

### 測試覆蓋（dispatch_tests.rs，load-bearing 對抗驗證）
- classify：test_classify_duplicate_order_link_id_10001_is_structural（含大小寫）+ test_classify_invalid_param_is_structural（非-dup 10001 仍 Structural）+ test_classify_110072_..._is_structural。
- helper：close_10001_duplicate_true（含大寫）/ open_10001_duplicate_false（★ open fail-closed 關鍵，註明拿掉 is_close guard 應 FAIL）/ close_10001_non_duplicate_false（格式錯/qty 非法）/ 110072 對應 4 test / non_business_error_false / does_not_trigger_local_convergence（10001-dup 與 110072 皆不收斂）。
- 回歸：test_open_retry_budget_unchanged_after_110072_change（OPEN_NO_RETRY 空 slice）。

### 字典補錄（1 LOW 非阻，併 BB1 backlog）
dict §4.2 110072 註記（line 1355）結尾的 follow-up 句目前寫「既有 10001+duplicate → NoOp 無 close guard…列 PM follow-up」——此 follow-up 已 land，該句須更新為「**10001 + retMsg contains "duplicate" 亦適用同 close-only 冪等語意**（與 110072 同 narrow：open fail-closed / close idempotent-success；classify 層 10001=>Structural，consumption 層 close_dup_is_idempotent_success 以 is_close+substring guard upgrade）。注意：substring 僅在 ret_code==10001 分支生效，10014 'Request is duplicate' 為獨立碼不誤觸」。另 §4.2 retCode 表 10001 row（line 1315）可加註腳指向 110072 註記。精確文字見本次 verdict §reference。E2 同 commit 或 BB1 backlog 補。

### 給 PM/E2 注意事項
1. 代碼為 SSOT 且已正確 land；BB 此裁決為交易所側語意背書，**非要求改碼**。
2. open path fail-closed 是此 follow-up 的**收緊**（10001-dup 從 fail-open NoOp 改 fail-closed Structural-else）——方向更保守，與 110072 一致，0 倉位安全回歸。
3. 不可恢復 hidden open retry（NoOp/upgrade ≠ retry）；OPEN_NO_RETRY 不變量由 test_open_retry_budget_unchanged 鎖定。
4. Mac sign-off ≠ runtime：Linux cargo test 需在下次 --rebuild 復現（dispatch_tests 全綠）。
5. 字典 §4.2 line 1355 follow-up 句更新（LOW，非阻 deploy）。

### 下次啟動需查驗項
1. dict §4.2 line 1355 follow-up 句是否更新為「10001+duplicate 已 land 同 close-only 語意」+ 10014 不誤觸註（BB1 backlog 或 E2 同 commit）
2. Linux --rebuild 後 dispatch_tests.rs 10001-dup + 110072 全 test 是否 PASS
3. 若未來 Bybit 改變 10001 retMsg 語意（在 10001 下夾帶非-orderLinkId 的 "duplicate"），close 側 substring 誤吞面需重評（當前官方 0 此情境）
4. hedge mode 啟用復活時，110072 + 10001-dup 冪等路徑與 110017 收斂同須 positionIdx corner case re-review（G-3 前提，承 110017/D2 教訓）

## 歷史里程碑（2026-06-10 自 BB.md 遷入，原文保留）
- 2026-04-04：首次系統審計（5 path fix + 3 UTA migrate + 3 deprecated remove）
- 2026-04-12：full_program_chain audit（BB-A1~A7 系列）
- 2026-04-20：EDGE-P2-3 Phase 1B-1 retCode 擴充
- 2026-04-24：全面復審；H-1 字典過期 + M-1/2/3 周邊優化

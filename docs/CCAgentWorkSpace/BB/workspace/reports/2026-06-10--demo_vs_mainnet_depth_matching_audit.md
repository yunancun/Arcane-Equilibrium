# BB Audit — Bybit Demo vs Mainnet 撮合/深度機制(AC19 alt-bucket 23.8% maker fill「環境歸因」裁決)

**Executive summary**:(1) Demo(`api-demo.bybit.com`)的公開行情是 mainnet 的**同源鏡像**——本審計實測 5 symbol REST orderbook/trade tape 與 mainnet 共用同一 update-id/seq/execId 序列(OP/ETC/ARB 五檔逐位一致),官方文檔亦明文「public data is identical to mainnet」→ **「demo book 系統性偏薄」prior 證偽**,AC19 慘案不能歸因 book 偏薄。(2) Demo 撮合=**虛擬模擬**:官方明文 demo 掛單「不可見於 order book」,即無真實 queue position、不能被真實 taker flow 打到;maker fill 判定規則官方未文檔化,綜合證據最符合「鏡像行情移動到/穿過掛價才判 fill、零 queue credit」(推斷,MEDIUM)。(3) 轉移性裁決:alt 23.8% 在 mainnet 預期方向=**同等或更好**(demo 缺 touch 排隊消耗這一真實成交來源;alt inside quote 極薄→真實掛單近隊首),但幅度不可量化、新增 fill 帶 adverse-selection 成本,**不保證 mainnet ≥60%**;large_cap 66.7% 在 demo 大致公平甚至略樂觀。(4) 三候選:β 前提須由「book 偏薄」改寫為「無 queue 模擬→alt 證據系統性偏悲觀」;α-輕(縮 timeout)轉移風險最低;C 可把 23.8% 當 mainnet 保守下界。最終決策屬 PA/QC + operator,BB 不裁。

---

**Date**: 2026-06-10 ｜ **Owner**: BB ｜ **Trigger**: QA AC19 final verdict §7(`docs/CCAgentWorkSpace/QA/workspace/reports/2026-06-10--ac19_alt_bucket_14d_final_verdict.md`)點名 BB demo-vs-mainnet depth audit 先行
**邊界遵循**: read-only;僅打公開 market data REST(共 14 req,≈ IP cap 600/5s 的 0.02%);**0 私有/簽名/交易 API**;唯一寫檔=本報告(+Operator 副本+BB memory 1 行)。

---

## §1 Q1 機制真相 — 官方證實 vs 推斷

| # | 陳述 | 來源 | 狀態 |
|---|---|---|---|
| 1 | demo 公開行情(book/tape/tickers)與 mainnet 完全相同 | 官方 demo doc:「public data is identical to that found on mainnet(wss://stream.bybit.com)」+ 本審計 §2 實證 | **官方證實 + 實證** |
| 2 | demo 掛單**不進入/不可見於**真實 order book → 無 queue position,不能被真實 taker 打到 | Bybit Learn/Help Center:「the orders placed within Bybit Demo Trading aren't visible in the order book」(原頁 WebFetch timeout ×3,引自官方頁 search snippet,attribution 高置信) | **官方證實**(間接取證) |
| 3 | demo「does not have a complete function compared with the real trading service」 | 官方 demo doc 原文 | 官方證實 |
| 4 | 基本交易規則同真實(PostOnly cross-check、tick、TIF):「Basic trading rules are the same as real trading」 | 官方 demo doc + AC19 窗內 4+2 筆 `EC_PostOnlyWillTakeLiquidity` reject 真實到達(§5) | **官方 + runtime 證實** |
| 5 | demo maker fill 判定=鏡像行情移動到/穿過掛價,**零 queue credit、零 touch 排隊消耗模擬** | 官方零文檔;由 #1/#2/#4 + AC19/E3 數據反推(§3) | **推斷(confidence MEDIUM)** |
| 6 | demo orders 僅保留 7 天;rate limit 為 default 且不可升級 | 官方 demo doc | 官方證實(與 fill rate 無關,備案) |
| 7 | Testnet 是獨立薄市場;官方建議流動性問題改用「a more liquid environment, like Demo Trading on Production」 | 官方 API docs FAQ | 官方證實(印證 demo 行情=production 行情) |

**Fill 規則候選模型**(官方未文檔化,#5 的兩種具體化):
- **模型 A(opposite-BBO cross / trade-through)**:對手側最優價到達/穿過掛價才 fill。
- **模型 B(tape-print-at-level / volume-aware touch)**:鏡像 tape 在掛價有真實成交 print 才 fill。

兩模型共同點=**零 queue credit**;區別只影響幅度估計,不影響 §4 方向結論。判別證據:E2 校準用 BBO-cross proxy(代碼註釋自標「systematically optimistic」,`maker_price.rs:96`)對 C90 cell 模擬 fill 70.8%——demo 實測 large_cap 66.7%(≈模擬)、alt 23.8%(<<模擬)→ 大 cap 上 demo≈BBO-cross;alt 上要麼 demo 嚴格於 BBO-touch(需 through/print),要麼 proxy 被 alt quote-flicker 灌水。**反事實**:若 demo 是樂觀 touch-fill(無 queue、touch 即全 fill),BTC join-at-ask 在 90s 內應接近全 fill,觀測 66.7%(6/9)不支持;alt 23.8% 更不支持。

## §2 Q2 深度對比實證(2026-06-10,REST `/v5/market/*`,公開無 key)

每 symbol 各 1 次 back-to-back(mainnet → demo,間隔 ~400ms),top-5 檔:

| symbol | mainnet `u` | demo `u` | top-5 檔對比 | 判定 |
|---|---|---|---|---|
| OPUSDT | 6029437 | 6029438 | bids/asks **5 檔逐位一致**(價+量) | 同一 book、同一更新流 |
| ETCUSDT | 5130923 | 5130925 | **5 檔逐位一致** | 同上 |
| ARBUSDT | 5920397 | 5920398 | **5 檔逐位一致** | 同上 |
| BTCUSDT | 6644098 | 6644100 | 同價格網格;僅 L1/L2 量差(1.308→1.538 / 2.456→1.167),與 ~400ms 時差的 book 更新一致 | 同一更新流(demo `u` 較新) |
| UNIUSDT | 5450924 | 5450926 | 同上(僅 inside 量隨時差變動) | 同上 |

關鍵同一性證據(identity-level,N=1 快照即足):
- `u`(orderbook update id)與 `seq` 在兩端是**同一遞增序列**(demo 永遠略新,因取樣晚 ~400ms)——不是兩個獨立 book。
- **trade tape 同源**:OPUSDT `/v5/market/recent-trade` demo 回傳與 mainnet **完全相同的 `execId`**(例 `79cc9473-caaa-56c4-…`)與 `seq`(373394668685…),demo 端還多 2 筆更新的 mainnet 成交(取樣較晚)。demo tape = mainnet 真實成交流,且不含 demo 用戶虛擬成交。
- tickers:BTCUSDT `openInterest`(56396.929)、`fundingRate`(0.00003544)、`nextFundingTime` 兩端同值。

**結論:demo 行情數據是 mainnet 同源鏡像 → AC19 fill-rate 差異不是「book 偏薄」,只能來自「撮合模擬」**。

殘餘不確定(誠實標注):(a) 單時點快照無法證 24/7 鏡像零延遲(高負載下未測;但 engine 在 demo WS 上跑數月無 divergence 報告,殘餘風險 LOW);(b) 引擎實際訂閱 `wss://stream-demo…/v5/public`(字典 line 1123)而官方建議 demo 用 mainnet public WS——兩者數據同源,無行為差異,非 drift(F-8)。

順帶微結構觀察(mainnet=demo 同值,支撐 §4):快照時 inside quote 規模——OPUSDT bid1 ≈ $12.5、UNIUSDT bid1 ≈ $36、ETCUSDT bid1 ≈ $70 vs BTCUSDT bid1 ≈ $153k。alt 的 join-at-touch 在真實市場≈**近隊首**;BTC 的 join ≈ 排在 $100k+ 隊尾。

## §3 AC19 數據與撮合模型的一致性

OpenClaw 端事實(代碼,`strategies/common/maker_price.rs`):grid family close-maker(`grid_close_*`/`bb_mean_revert`/`ma_reverse_cross`/`bw_squeeze`/`pctb_revert`)= `buffer_ticks=0`(**掛 inside quote 同價**,long-close=SELL@best_ask、short-close=BUY@best_bid)+ timeout 90s(CALIBRATION-2026-05-18,覆蓋 AC19 窗大部;per-row 生效值未逐筆驗,與 QA 同保留);phys_lock family buffer=1、10–15s;spread guard 50bps。

零 queue credit 模型**自然解釋 AC19 的 bucket split**:
- **alt(23.8%)**:真實市場中近隊首的 join 可在任何 touch 成交時 fill,**不需** price through——demo 把這一主要成交來源整段抹掉,只剩「90s 內價格朝有利方向移過掛價」的機率 → 系統性低估。
- **large_cap(66.7%)**:BTC 隊列深,真實隊尾成交≈「該檔位幾乎被吃穿」≈trade-through——demo 規則與排隊現實近似重合(甚至略樂觀,因真實隊尾還要搶最後一口)→ demo 數字大致公平。66.7% 與 E2 BBO-cross 模擬 70.8% 同量級,互證。

## §4 Q3 轉移性裁決

**alt 23.8% 在 mainnet 的預期方向 = 同等或更好(≥),幅度不可判**:
- 方向依據(confidence MEDIUM-HIGH):mainnet 掛單真實進 book,touch 排隊消耗 + 隊前撤單推進(實證文獻中 touch 檔 30-60%+ 量為撤單)是 demo 沒有的成交來源;alt inside 極薄(§2)使該來源占比最大。
- 幅度不可判依據(confidence LOW):(a) fill 還需該價位真有 taker print,sparse-tape alt 的上限受流量約束;(b) 公開數據無法量化 queue 動態;(c) **fill rate ≠ 經濟價值**——mainnet 多出來的 touch fill 偏 toxic(adverse selection:被動單最容易在價格即將不利時被成交),fill quality 會吃掉部分新增 fill 的價值。**不可據此承諾 mainnet 過 60% 健康線**。
- large_cap:demo≈公平到略樂觀;66.7% 點估計可視為 mainnet 同量級;n=9 不可判維持 QA 結論。

**三候選在「demo 證據可轉移性」維度的風險(一句話各)**:

| 選項 | 轉移性風險一句話 |
|---|---|
| **alt taker-direct(β)** | 前提須改寫:「demo book 偏薄」已證偽,成立版本是「demo 無 queue 模擬 → alt maker 證據系統性偏悲觀」——關掉 demo alt maker 等於把一個**在 mainnet 方向上可能更好**的路徑從證據 lane 永久關燈,且 sparse-tape alt 在 mainnet 也未必跨線,關燈後只能用真金回答。 |
| **縮 maker timeout(α-輕)** | 轉移風險**最低**:只削延遲代價、不依賴 demo fill 模型正確性;但「demo 上校準出的最優 timeout」對 mainnet 不必然最優(fill 模型軸不轉移),敘事應為代價控制而非 fill 最佳化。 |
| **維持現狀(C)** | 23.8% 可當 mainnet **保守下界**繼續累積(數據軸=真 mainnet 價格路徑,非合成行情);代價=demo 證據 lane 平倉延遲污染持續,且須顯式把「demo 數字=下界非預測值」寫入證據解讀防誤讀。 |

QA §6 的過擬合警告修正版:α 在 demo 上調參,**數據軸**(價格路徑/spread/tick)就是 mainnet 真實數據,過擬合風險低於原措辭;真正不轉移的是**fill 判定軸**(模擬器 vs 真實 queue)。最終 α/β/C 決策屬 PA/QC + operator sign-off,BB 僅出機制真相與方向。

## §5 Q4 順帶 — [74] / PostOnly reject / 110017

- AC19 窗內 4(alt)+2(large_cap)筆 `postonly_reject` = demo 端 `EC_PostOnlyWillTakeLiquidity`(REST retCode=0 → WS `rejectReason` 路徑)**真實推送到達** → 字典 §4.3 #14 / `[65]`/`[74]` 所防的「demo silent degradation(不推 reject)」在**此軸有正面反證,可部分退役**;`[74]` 樣本累積慢的解釋=incidence 低(strict-passive 計價只在 BBO race 下 cross),非 suppression。
- `EC_ReachMaxPendingOrders` 軸仍 0 樣本,該軸 silent-degradation 疑慮維持,mainnet 隔離 probe gate 不變。
- `110017`(ReduceOnlyReject,REST-level 終態錯誤:倉位不存在/方向不符)與 PostOnly reject 是**不同軸**,AC19 reject 樣本不觸 110017;字典 §4.2 110017 row 補錄(P2-BB-DICT-110017)維持 open。

## §6 Findings 全量表

| ID | Severity | Confidence | Finding |
|---|---|---|---|
| F-1 | **HIGH** | HIGH | 「demo orderbook 系統性薄於 mainnet」prior **證偽**(§2 同源鏡像)。引用點需後續改寫:`docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md:354`(「per E2 RCA §6 BB cross-check 提示:demo … thinner」)、AC19 SOP §5.2、QA verdict §6(「PA Phase 1b §4.4 + BB Q1 prior」)。正確措辭=「demo 行情同 mainnet;差異在撮合模擬無 queue position」。此為 BB 自我更正:原 prior 是未實證 hint,本審計收回。 |
| F-2 | MEDIUM | HIGH(官方) | demo 掛單不可見於 order book → 無 queue、不可被真實 flow 成交;fill 全為模擬(§1 #2)。 |
| F-3 | MEDIUM | MEDIUM | demo fill 規則最符合「零 queue credit 的 BBO-cross/trade-through-like」;官方未文檔化,模型 A/B 二擇未定(§1)。 |
| F-4 | MEDIUM | 方向 MEDIUM-HIGH / 幅度 LOW | alt 23.8% 轉移性:mainnet 方向 ≥ demo、不保證 ≥60%;large_cap demo≈公平略樂觀(§4)。 |
| F-5 | LOW | HIGH | demo `EC_PostOnlyWillTakeLiquidity` reject 推送有正樣本(close path)→ silent-degradation 疑慮該軸部分退役;`EC_ReachMaxPendingOrders` 軸仍未證(§5)。 |
| F-6 | LOW | HIGH | demo orders 7d retention + default rate limit 不可升(官方)——對 AC19 無影響;字典補錄候選。 |
| F-7 | INFO | MEDIUM | E2 BBO-cross proxy 在 alt 上系統性高估(C90 模擬 70.8% vs demo 實測 23.8%)、large_cap 上準(66.7%);後續校準不可用該 proxy 預測 alt fill。 |
| F-8 | INFO | HIGH | 字典 line 1123 引擎訂 `stream-demo` public WS vs 官方建議 demo 用 mainnet public WS——數據同源無行為差異,非 drift,不需改碼。 |

**假陽性候選(不自行剔除,交 PM/operator 裁)**:
- F-3 替代假說:模型 B(volume-aware touch)或「隱藏 demo-user book + 複製器撮合」皆可同等解釋現有 aggregate;三者共同點=零 queue credit,故 F-4 方向結論對模型選擇穩健。
- F-1 殘餘:單時點快照證同源是 identity-level 證據,但極端行情下鏡像 lag 未測(runtime 反證:demo WS 數月無 divergence 報告)。
- F-4 方向結論的反向情景:若 demo 實為模型 B 且 alt tape 在掛價的 print 頻率已被完整計入,則 mainnet 增益僅來自 queue 推進一項,「≥」仍成立但增幅可能接近 0(即 demo FAIL ≈ mainnet 真況)——此情景無法用公開數據排除,故 β 的「demo FAIL=真信號」讀法不能完全否定。

## §7 建議 follow-up(non-binding)

1. (MIT/QA,離線零 API)對 10 筆 alt maker fills 做 time-to-fill + 對照 mainnet tape/kline 的 through-print 判別 → 一次性分辨模型 A vs B,把 F-3 升 HIGH confidence。
2. (PA/QC)α/β 對抗 review 引用 §6 caveat 時採 F-1 修正措辭。
3. (operator-gated)mainnet 真值唯一乾淨途徑=mainnet 隔離 micro-probe(`[65]` 先例設計);BB 不單方執行(硬約束:禁打交易/私有 API)。
4. (BB/TW 字典)§4.3 補一條:demo 行情=mainnet 鏡像(同 seq/execId,本報告引據);demo fill=無 queue 模擬;併入既有 Wave 3b BB1 字典更新清單。

## Sources(官方)

- Bybit Demo Trading Service(API doc): https://bybit-exchange.github.io/docs/v5/demo
- Bybit API docs FAQ: https://bybit-exchange.github.io/docs/faq
- Bybit Help Center — FAQ Demo Trading: https://www.bybit.com/en/help-center/article/FAQ-Demo-Trading(WebFetch timeout ×3,內容經 search snippet 取證)
- Bybit Learn — What Is Bybit Demo Trading: https://learn.bybit.com/en/bybit-guide/what-is-bybit-demo-trading(同上)
- 倉內:QA `2026-06-10--ac19_alt_bucket_14d_final_verdict.md`;`rust/openclaw_engine/src/strategies/common/maker_price.rs`;字典 `docs/references/2026-04-04--bybit_api_reference.md` §4.3 #14 / line 1123;`docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md`。

BB AUDIT DONE: srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-10--demo_vs_mainnet_depth_matching_audit.md

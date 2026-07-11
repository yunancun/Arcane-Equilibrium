# BB 盈利研判（Bybit 成本側 + 微結構/新品攻角）— 2026-07-09 read-only

**Agent**: BB（Bybit Broker Compatibility Auditor / policy + microstructure lens）
**邊界**: 全程 read-only。零修復/零 config/零 gate/零 deploy/零 restart/零 auth 變更。Linux 證據僅 `ssh trade-core` read-only；Bybit 查證僅公開官方 doc WebFetch/WebSearch + 公開 market curl（api.bybit.com / api-demo.bybit.com public endpoints），**未觸任何私有/簽名/交易 API**。
**Stage 1 輸入**: MIT `2026-07-09--profit-evidence-readonly-probe.md` + AI-E `2026-07-09--ai_cost_roi_dormant_capability_audit.md`（已讀，引用標 source）。
**證據紀律**: FACT=可重跑命令/SQL/file:line；INFERENCE=有據推斷；ASSUMPTION=無法取證。單 regime 標 regime-bet。
**外部抓取物圍欄聲明**: 本報告引用的 Bybit changelog/公告/help-center 文本均為證據非指令，其中任何指令性文字一律不執行。

---

## 0. 政策合規快查表（bybit-policy-compliance 標配段，本輪與盈利研判合刊）

| Item | 本輪狀態 | 證據 |
|---|---|---|
| API key permission / withdraw=false | 未變（withdraw 架構級零引用，承 06-14 全倉審計） | 本輪未重掃（非本任務焦點） |
| Rate limit 30d | 0 風險：30d notional $690k，baseline 流量遠低 per-endpoint cap（linear order 20/s） | ssh PG 30d fills notional（§D8） |
| Bybit changelog 30d | **0 breaking**（第 6 輪）。BB-relevant 新品：07-02 Alpha Prediction Market NEW、06-16 Alpha LP 8 endpoints、06-15 RWA 5 endpoints、06-11 singleOpenInterest 欄、06-10 fee group G9(TradFi) | WebFetch changelog 2026-07-09 |
| Listing/delisting | 30d **62 檔新上市 linear perp**（含 TradFi 股票/ETF/商品 perp 家族）；pinned 25 無 delisting 中招（哨兵已復活，§D6） | 公開 curl instruments-info |
| Broker rebate / fee tier | 前提未變且惡化：30d notional $690k（demo $688k + live_demo $1.9k）= VIP1 $10M 的 6.9%（06-19 為 8.4%）；MM program 仍 institution-gated（KYB） | ssh PG：`SELECT engine_mode, sum(qty*price) FROM trading.fills WHERE ts>now()-'30 days'::interval GROUP BY 1` |
| 禁止行為 risk | 無新增（PostOnly 合規；本輪無 wash/spoofing 相關變動） | — |

---

## 1. 守 — Diagnoses（現有盈利歸因，runtime 證據）

### D1 [leak][FACT][high] 30d 全系統 true net −406 USDT，fee-dominated；BB 成本分解：taker 腿真實成本 ~11.7bps、maker 腿 markout 後 ~9.6bps
- MIT §A（FACT，引用）：30d gross −150.72 / fees 255.39 / **true net −406.11 USDT**；全 6 策略 true net 負；p50 per-close gross −1.17bps。
- BB 補充分解（FACT，本輪 ssh 親證）：30d closing fills 中 taker 平均 fee 5.73bps + demo taker slippage ~6bps ≈ **11.7bps/腿**；maker fee 2.0bps 但 maker markout −7.57bps（MIT A.4）≈ 有效 9.6bps/腿。RT 成本 ~19-23bps vs p50 gross −1.17bps → **成本牆 >> 毛 alpha，與 6 週病根同源**。
- 可重跑：`docker exec trading_postgres psql -U trading_admin -d trading_ai -Atc "SELECT liquidity_role, count(*), round(avg(fee_rate)::numeric*10000,2) FROM trading.fills WHERE ts > now()-interval '30 days' AND realized_pnl <> 0 GROUP BY 1"` → maker|90|2.00 / taker|398|5.73。
- blocker=cost（VIP0 費率鎖定，fee tier 前提見 D8）。regime_caveat：30d 單一 regime demo lane 窗。
- profit_impact：−406 USDT/30d；fee 佔淨虧 63%。

### D2 [leak][FACT][high] close-maker 執行漏損惡化：close 側 maker 佔比僅 18.4%，close_maker_attempt 成功率 27.9%（06-13 為 35%）
- FACT（本輪 ssh 親證，30d closing fills）：`close_maker_attempt=t` 323 筆中 maker 成交 **90**（27.9%）、timeout_taker **117**、postonly_reject **116**；另 165 筆 close 根本未嘗試 maker。總 close 488 筆（ex paper_sim）中 maker 僅 90 = **18.4%**。
- 可重跑：`... SELECT close_maker_attempt, coalesce(close_maker_fallback_reason,'(none)'), liquidity_role, count(*) FROM trading.fills WHERE ts>now()-interval '30 days' AND realized_pnl<>0 GROUP BY 1,2,3`。
- 量化（雙口徑，誠實呈報）：naive fee+slip 口徑每筆 fallback 多付 ~9.7bps；但 maker markout −7.57bps 存在（adverse selection 把省的費吃回去），markout-adjusted 差距 ~2bps/腿。demo 名目小（~$680/fill）→ 絕對金額 30d ~$5-26，**結構性 bps drag 是重點非美元**。
- postonly_reject 116/323=35.9% 是可機械消除類（見 O3 bboSideType）；timeout 類與 queue position 相關（demo 撮合無 queue，實際更差，承 06-10 audit）。
- blocker=undeveloped（BBO-peg/RPI 執行工具 0 接線，見 D3）。

### D3 [frozen][FACT][high] 執行 alpha 工具三連 0 接線：rpiTakerAccess（第 6 輪）、bboSideType/bboLevel、/v5/spread/* 全 0 引用
- FACT：`grep -rn "rpiTakerAccess|bboSideType|bboLevel|/v5/spread" rust/ program_code/ helper_scripts/` = 0 命中（本輪 2026-07-09 復掃）；字典亦無 rpiTakerAccess/spread 條目（dict 補錄債，併 BB1 backlog）。
- rpiTakerAccess（changelog 06-03/full 06-12；fee 語義 06-14 已裁：price improvement 非 fee class，ToS 無礙）直擊 D2 的 398 筆 taker close 腿；bboSideType/bboLevel 直擊 116 筆 postonly_reject。
- blocker=undeveloped。profit_impact：縮虧類（執行衛生），非翻正搜索空間；量級上限 = D2 的 bps drag。

### D4 [frozen][FACT+INFERENCE][med] funding 非 leak 三度確認；carry 構造的「spot 子系統」牆被 Bybit 原生 FundingRateArb spread 部分拆除，但該 venue 當前流動性為零
- funding 非 leak（FACT）：30d close hold p50 **5.0min** / p95 47.3min，497 筆 close 僅 **7 筆跨 8h funding 結算** → funding drag ≈ 0（可重跑：entry_context join fills 查詢，見 workspace 命令記錄）。
- 前提變化（FACT，公開 curl 2026-07-09）：`GET /v5/spread/instrument` 存在 **contractType=FundingRateArb**（BTCUSDT_BTC/USDT、ETHUSDT_ETH/USDT、SOLUSDT_SOL/USDT；legs=LinearPerpetual+Spot，原子成交零 leg risk），2025-04 上線；官方 help center：spread 費率 = 兩腿分開執行的 **50% off**；api-demo 同樣暴露 instrument。→ 06-14 carry NO-GO 的「spot 執行子系統 major build + leg risk」killer 前提實質弱化。
- 但（FACT，本輪 curl）：三檔 FundingRateArb **volume24h 全 = 0，BTC/ETH book 全空**，SOL 僅殘單；官方 FAQ：spread book 流動性獨立（無 implied matching 對 leg book）→ venue 當前實質死市，taker 路徑不存在。
- 現時 funding regime（FACT，curl 2026-07-09）：BTC +6.77% APR（06-14 時 −1.73%）、XRP/DOGE +10.95%、ETH +2.16%、SOL +1.96% → 正偏回歸中，接近 06-14 conditional-carry 分析的 +8-10% 帶。
- blocker=other（venue 流動性 gate 取代 build gate）。regime_caveat：funding 正偏 = bull-leaning 前提，carry 收益 regime-dependent。

### D5 [unrealized][FACT][high] 30d 62 檔新上市（含 TradFi 股票/ETF/商品 perp 家族）spread 15-116bps，系統 roster 鎖死在殘殺 spread 的 crypto majors
- FACT（公開 curl 2026-07-09）：30d 新上市 linear perp 62 檔；有 book 的 41 檔中 spread 前列：HIMSUSDT **115.8bps**、ALABUSDT 77.2、CIENUSDT 74.5、TTWOUSDT 73.1、HPEUSDT 69.0、LRCXUSDT 55.7…；純股票 perp 子集 n=10 median spread **14.8bps**（vs BTCUSDT 0.016bps = ~900×）。24h turnover $30k-$4.4M/檔（thin=機構吃不下，適小帳戶）。
- TradFi 家族（FACT，官方公告/help center）：2026-04 起每週加新 ticker，現 ~20 美股 + 3 商品（XAU/XAG/CL）+ 3 ETF（含 UVXYUSDT=VIX ETF perp、SQQQUSDT）；**2026-06-16 起專屬 fee group G9，全 tier 費率調低**（exact 費率未取到，gap）；demo 環境可見（api-demo instruments/tickers 親證 HIMSUSDT）。
- fill_sim maker NO-GO（0/172 cells）的母體是 mature crypto perp（spread 0.02-6bps）；此 population（15-116bps）從未被測——**不是重打舊戰場，是舊測試從未覆蓋的 population**，且帶新機制候選（G9 低費 + IBKR anchor，見 O1）。
- blocker=paradigm（roster 範式=crypto majors）+ gate（pinned 25 config）。profit_impact：機會成本未量化；half-spread 7-58bps 的 population 是全系統唯一 spread >> fee 的角落。

### D6 [frozen→已解][FACT][high] 公告哨兵已於 07-04 復活（閉 07-03 F-1 HIGH）
- FACT：crontab 3 條 announcement 相關（`7,37 * * * * ... bybit_announcement_sentinel_cron.sh`，註記「07-04 窗口恢復」）；state 檔 `bybit_announcements_state.json` mtime **2026-07-09 23:07+02**（<30min fresh）。delisting/maintenance P0 watch 恢復 → 強平/下架尾部風險保護回線。
- profit_impact：loss-avoidance 恢復（30d 內 62 檔上市但 pinned 25 零 delisting 中招）。

### D7 [frozen][INFERENCE(source: MIT)][high] profit-first loop 唯一候選證據無效 + 授權過期 + 零 order/fill proof——BB 側含義：勿對無效候選消耗 E3/BB order-capable window
- MIT F1（pseudo-replication ×2529，n_eff≈1-2）+ F3（standing auth 過期 ~20.7h）+ F4（候選零 order/fill）+ TODO `P0-CURRENT-CANDIDATE-ORDER-CAPABLE-DEMO-INVOKE-FRESH-WINDOW-RUN-GATE` READY_FOR_PM_E3_DISPATCH 卡 stale BBO manifest。
- BB 立場：order-capable packet（sha `305774b2`）派發時需 BB same-window review——在 F1 修復（per-(cell,entry_ts) 去重 + effective-n）前，該 window 的 BB review 只能對「統計無效候選」蓋章程序合規，浪費 window。支持 MIT 建議：先修 F1 再續 chain。
- blocker=gate（loop 治理鏈自身）。

### D8 [unrealized][FACT][high] fee-tier / MM 前提監測（no-repeat 紀律下的前提刷新）：距 VIP1 缺口擴大至 14.5×
- FACT：30d notional demo $688,199 + live_demo $1,885 ≈ **$690k**，= VIP1/API-Broker $10M 門檻的 **6.9%**（06-19 audit 為 8.4% → 方向惡化）。MM program 仍 KYB institution-gated（承 07-06 fact sheet，本輪無官方條款變動證據）。
- **mature-perp maker-first NO-GO 前提本輪復核：未變**（VIP0 maker +2bps 仍為正費率；负 maker 仍只有 MM program 一條路）→ no-repeat 紀律維持，無重開證據。
- blocker=cost（operator 資本/規模/BD 槓桿，非工程）。

---

## 2. 攻 — Opportunities

### O1 [paradigm_challenge=true][INFERENCE][med] TradFi 股票 perp × IBKR read-only anchor：主市場錨定的 dislocation/quoting niche
- **hypothesis（可證偽）**：美股現金時段內，Bybit 股票 perp（spread 15-116bps、thin retail book、G9 低費）對 IBKR 一級市場 NBBO 的偏離分布存在可捕捉的均值回歸：|deviation| > (half-spread + G9 fee) 的事件在 T+minutes 內向 NBBO 收斂的頻率/幅度 > 成本。持 IBKR 即時錨的 quoter/taker 把 fill_sim NO-GO 的 adverse-selection 方向反轉（我方是 informed side）——這就是新上市寬價差 niche 要求的「新機制」。
- **why_not_tried**：TradFi perp 家族 2026-04 才上線、G9 fee group 06-16 生效、IBKR lane 07-08 才獲 Phase 2 read-only 授權——兩條 lane 從未被連接；系統 roster 鎖 crypto majors。
- **est_edge**：下界錨=觀測 spread（股票 perp 子集 median 14.8bps、尾部 115.8bps）vs G9 fee（低於 G2 crypto 費率，exact 未取到）；容量受 thin turnover（$30k-4.4M/day/檔）限制=小帳戶甜區。偏離分布未測=edge 未量化（此為研究第一步）。
- **est_cost**：研究 $0（Bybit 側公開 REST/WS 現成；IBKR 側數據 operator-gated 於 Gateway paper 啟動）；IMPL=新 symbol config + IBKR md→signal 管道（ADR-0048 邊界內：IBKR 永遠 read-only，執行僅 Bybit）。
- **wall_break_prob**：med——此 population half-spread 7-58bps >> fee ~2-5bps，不需要 maker rebate 也能過牆（mature-perp 牆需 maker ≤0.4bps，此處結構不同）；風險在 fill 的 adverse selection 與 24/7-vs-6.5h 的 off-hours 盲窗。
- **how_to_validate（leak-free）**：(1) $0 先導：point-in-time 同步採集 Bybit 股票 perp BBO（公開 WS）+（lane 啟動後）IBKR NBBO，只做偏離分布/收斂統計，無交易；(2) 按 session bucket（cash/overnight/halt）分層；(3) 若正→demo 下單驗證（demo 有 HIMSUSDT 等 instrument，親證），fill 真實性按 06-10「demo 無 queue position」紀律折減 + through-print 判別。
- **regime_caveat**：overnight gap/halt/公司行動 = 股票特有尾部；上市初期 spread 會收斂（HIMS 07-03 上市 116bps 是早期紅利，窗口有時效）。boundary note：Bybit linear category 執行=產品邊界內；QC 需加 TradFi 特有風控（session/gap）。

### O2 [unlock 監測][FACT(現狀)+ASSUMPTION(觸發)][med] FundingRateArb 原生 spread venue 流動性監測 + funding regime 前提監測（carry 重開的兩把鑰匙）
- **hypothesis**：當 (a) 任一 FundingRateArb instrument volume24h 持續 >$100k×7d 且 book 雙邊有量，且 (b) majors 30d 平均 funding APR >+8%（06-14 conditional-carry 帶），則 cash-carry 以原子 spread 單 + 50% 費率折扣重估可翻正（06-14 NEEDS-MORE-EVIDENCE 的兩個缺腿補齊）。
- **why_not_tried**：/v5/spread/* 家族今日才首次被系統性檢視（dict 0 記載、code 0 引用）；當前 venue 死市（volume24h=0 親證）故非立即可做。
- **est_edge**：regime-dependent carry +6-10% APR ×可部署 size − 50%-off 費用 − cost-of-capital（06-14 算式，用新費率重跑）；現時 BTC funding +6.77% APR 已從 06-14 的 −1.73% 回正=前提移動中。
- **est_cost**：監測 $0（每月 BB audit 加 2 條 curl：`/v5/spread/tickers` volume24h + majors funding APR，**owner=BB，閾值如上，觸發即報 PM/QC**）；觸發後 IMPL=中型（/v5/spread client + spot 腿 custody/reconcile，遠小於全 spot 子系統）。
- **wall_break_prob**：low（現時死市）→ 觸發後 med。
- **how_to_validate**：觸發後先 demo（api-demo 暴露 spread instrument；下單支援需屆時驗證）+ QC 用 alpha_funding_rates_history 2yr 重跑 conditional-carry net（費率減半版）。
- **regime_caveat**：carry sign 結構性、magnitude regime-dependent（bull-weighted）；任何正結果標 regime-bet。

### O3 [execution 縮虧][FACT(母集)+INFERENCE(節省)][high] bboSideType/bboLevel BBO-peg PostOnly：機械消除 35.9% postonly_reject 類 close fallback
- **hypothesis**：close-maker 單改用 Bybit 原生 BBO-peg（bboSideType/bboLevel=1，交易所側自動貼最優價、永不 cross book）後，116/323 postonly_reject 類消失、timeout 類部分減少 → close 側 maker 佔比從 18.4% 顯著回升；每轉化一腿省 naive ~9.7bps / markout-adjusted ~2bps。
- **why_not_tried**：engine 0 引用（第 4 輪確認）；maker-nogo 後執行衛生類被降優先（正確地不當 alpha），但此項是 M12-adaptive-router 類「成本削減」，maker-nogo 明確標其為真 dormant 而非 killed。
- **est_edge**：縮虧非 alpha——上限 = D2 bps drag（demo scale 絕對值小；scale 後線性放大）。誠實標註：markout −7.57bps 意味 maker 化的真實淨省 ~2bps/腿而非 9.7。
- **est_cost**：E1 order body 1-2 欄位 + dict 補錄（BB 已有 06-14 survey 底稿）；低。
- **wall_break_prob**：low（不翻正搜索空間，純執行衛生）。
- **how_to_validate**：demo A/B（reject/timeout 率可信；fill 率因 demo 無 queue position 偏樂觀，須 live_demo 小 n + through-print 判別複核，承 06-10 audit 紀律）。

### O4 [execution 縮虧][ASSUMPTION(幅度)][med] rpiTakerAccess 接線 + RPI 觀測欄位落庫：398 筆 taker close 腿的免費 price improvement
- **hypothesis**：taker close 單加 `rpiTakerAccess=true` 後，命中 RPI maker 流動性的部分獲得 price improvement（fee class 不變，06-14 已裁），實測 improvement > 0。
- **why_not_tried**：0 引用第 6 輪；無人接線。
- **est_edge**：上限=命中量 × 讓價幅度；**幅度無公開統計=ASSUMPTION**，故先接觀測（WS `rpiMatchedQty`/order history `rpiTakerAccess` 欄，changelog 05-21/05-26）再談節省。
- **est_cost**：1 optional body 欄 + 觀測欄落庫；極低。ToS/fee 風險 0（06-14 ruling）。
- **wall_break_prob**：low（縮虧類）。
- **how_to_validate**：demo 可能無 RPI maker（RPI=mainnet MM 供給）→ 觀測欄位在 live_demo/demo 各掛一段窗，統計 rpiMatchedQty>0 佔比與實得改善 bps；0 命中即誠實結案。

### O5 [paradigm_challenge=true][ASSUMPTION][unknown] Bybit Alpha Prediction Market API（07-02 NEW）：被 PARK 的事件/監管軸的首個 Bybit-native 可執行 venue 候選
- **hypothesis**：新生 prediction market venue 存在經典 favorite-longshot bias 與 thin-book mispricing；事件/監管軸（06-13 判「值得 $0 累積」）的資訊優勢可在該 venue 變現，且不與「Polymarket odds 是 spot 衍生不可能 lead perp」的 KILL 重疊（此處直接交易事件結果，非用 odds 預測 perp）。
- **why_not_tried**：endpoints 2026-07-02 才上 changelog（7 天前）；且 Bybit Alpha=UTA 橋接的 on-chain 交易——**產品邊界問題（「Bybit 唯一交易所」是否涵蓋 Bybit Alpha on-chain venue）需 PM/CC 先裁**，BB 先標記不預判。
- **est_edge**：unknown（venue 微結構未測；新 venue 早期 spread/bias 通常最寬）。
- **est_cost**：$0 數據累積（公開 endpoints 讀 markets/odds/depth）+ 一次 CC 邊界裁決。
- **wall_break_prob**：unknown（事件軸的牆=資訊時效與結算規則風險，非 taker fee 牆）。
- **how_to_validate**：(1) CC 邊界裁決；(2) $0 快照管道：每日抓 market list/odds/depth 落 research schema，30d 後檢 calibration 與 spread 分布；(3) 與 PARK 的事件/監管子軸到期覆核合流。
- **regime_caveat**：無（事件軸本身跨 regime，但 venue 存活性=新品風險）。

### O6 [mechanical][FACT(信號)+ASSUMPTION(net)][med] 新上市極端 funding 結算窗 snipe：DATAUSDT 現值 −0.56%/4h（−1230% APR，cap ±2.5%/4h）
- **hypothesis**：新上市 perp 的極端 funding（如 DATAUSDT 06-30 上市，funding −0.5617%/4h 親證）在結算 instant 附近的 per-settlement 支付（56bps）> 結算窗 ±5min 價格漂移 + 2×taker fee（~11.5bps）+ thin-book slippage → 跨結算持倉分鐘級的機械 carry 為淨正。
- **why_not_tried**：06-14 曾點名「funding-snipe 未測機械流」但從未研究；且母集（新上市極端 funding）需要 listing 監測管道（哨兵已復活=基礎設施在位）。
- **est_edge**：per-event gross 上限=|F| per settlement（DATAUSDT 現值 56bps/4h、cap 250bps）；net 取決於結算窗漂移分布=未測。**注意方向：F<0 收 funding 的是 long 腿——負 funding 存在正因空頭願付費持空（預期下跌），漂移大概率逆風，這正是要證偽的點**。
- **est_cost**：$0 離線：research.alpha_funding_rates_history（2yr backfill 在庫）+ market.klines 1m，對歷史 |F|>30bps/interval 事件跑結算窗 event study（leak-free：只用結算前已知的 F，漂移取結算後窗）。
- **wall_break_prob**：med（事件類的牆=漂移+thin slippage，非 maker rebate 牆；54bps gross headroom 是全系統少見的 per-trade 量級）。
- **how_to_validate**：QC/MIT 離線 event study → 若淨正再 demo 小 n（新上市 symbol 需臨時擴 roster=operator 決策）。
- **regime_caveat**：新上市 regime 專屬（listing-pump 結構）；結果標 listing-regime-bet。

---

## 3. Gaps（本輪取不到）
1. G9 TradFi 費率表 exact 數字——官方公告頁兩次 WebFetch timeout；僅取得「全 tier 調低、06-16 生效」定性（多源一致）。→ 下輪補（影響 O1 est_edge 精度）。
2. spread trading demo **下單**支援未驗（僅 instrument endpoint 在 api-demo 親證；下單屬私有 API，BB 禁打）。
3. FundingRateArb 之外的 CarryTrade/PerpBasis（Sep26/Dec26 腿）book 深度未逐檔量（calendar 已 dead-by-arbitrage，優先級低）。
4. RPI improvement 幅度無公開統計（O4 故設觀測先行）。
5. Alpha Prediction Market 具體 endpoint 清單/結算規則未逐項讀（邊界裁決前不投入）。
6. close_maker timeout 的 per-symbol/spread 分解未做（O3 A/B 設計時補）。

## 4. 假陽性候選申報
- D2「惡化 35%→27.9%」：06-13 口徑是「30d attempt 內 46/131」與本輪 90/323 分母構造相同但窗不同；若 06-13 窗含較多寬 spread symbol，差異可能部分是 mix effect 非退化。判斷依據：兩窗同為 30d 全 close 母集，仍判真實方向性惡化（confidence med-high）。
- D4「venue 死市」：僅單時點快照（23:07+02 一次 curl）；若 spread book 流動性呈 session 性（美股時段活躍），單快照可能低估。O2 監測設計已覆蓋此不確定性。
- O6 的 DATAUSDT 極端 funding 為單 symbol 單時點觀測，母集規模需離線統計確認。

## 5. 外部來源（本輪 WebFetch/WebSearch）
- Bybit V5 changelog: https://bybit-exchange.github.io/docs/changelog/v5
- Spread Trading FAQ / Intro（help center，經 WebSearch 摘錄）: https://www.bybit.com/en/help-center/article/FAQ-Spread-Trading
- TradFi Perpetuals lower fees announcement: https://announcements.bybit.com/en/article/tradfi-perpetuals-lower-fees-across-all-tiers-bltb196506dada4be39/
- TradFi Perp 介紹: https://www.bybit.com/en/help-center/article/Introduction-to-TradFi-Perpetual-Contracts
- Bybit fee rate 官方頁: https://www.bybit.com/en/announcement-info/fee-rate/
- Bybit Alpha FAQ: https://www.bybit.com/en/help-center/article/FAQ-Bybit-Alpha

## 6. 結論
**FINDINGS**（無新 CRITICAL/HIGH 合規 ship-stop → 不複製 Operator/）。守側：不賺錢=成本牆（fee 佔淨虧 63%）+ close 執行漏損惡化（maker 18.4%）+ roster 鎖死在唯一 spread<fee 的 population；funding 非 leak 三度確認；哨兵已復活。攻側：本輪最大增量=**Bybit 產品面在 2026-Q2 生出三個系統從未檢視的結構角落**（TradFi G9 股票 perp 家族、FundingRateArb 原生 spread venue、Alpha Prediction Market），其中 TradFi×IBKR anchor 是唯一「寬 spread population + 新機制 + 兩條既有 lane 直接合流」的組合，$0 即可開研究。

小決策註記：報告檔名用 `bybit_profit_diagnosis_readonly` 而非 compat_audit 命名（本任務為盈利研判非 API 相容審計，避免與 compat 系列語義混淆）。

BB AUDIT DONE: docs/CCAgentWorkSpace/BB/workspace/reports/2026-07-09--bybit_profit_diagnosis_readonly.md

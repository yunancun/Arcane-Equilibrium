# QC 外部盈利情報掃描（EXT 軸）— 2026-07-09

角色：QC（外部量化顧問視角）。範圍：srv/ 全系統盈利面 + IBKR stock_etf_cash read-only 研究 lane（ADR-0048 邊界內，僅研究價值/數據累積 ROI）。
姿態：read-only 盈利研判。零修復、零 config/gate/風控改動、零部署重啟、零交易啟動。Linux 取證僅 `ssh trade-core` read-only（psql SELECT / ls）。
判定：**FINDINGS**（7 條機會項；diagnoses 依任務指示留空——守側歸內視角四軸）。

---

## 1. Executive Summary

外部掃描找到三類「別人在我們同樣的牆前賺錢」的機制，其中兩類的**前提在過去 15 個月已被交易所自己改變**而我們的 NO-GO 裁決尚未吸收：

1. **Bybit 已把「funding 套利」產品化為原子雙腿 Spread Trading 工具**（2025-04 API 上線；`contractType=FundingRateArb/CarryTrade`；費率比分腿執行低 50%）——直接攻擊 funding_short_v2 的兩堵牆（leg risk + 雙腿費用），但當前 regime 我們 25-symbol 宇宙 funding 全貼 IR floor（runtime 證據），故此軸現階段=**監測+建管道**，不是立即交易。
2. **Bybit RPI（Retail Price Improvement）新增 `rpiTakerAccess` API 參數**（2026-06-03 changelog，一個月新）——我們的 API taker 單可**選擇性對 MM 的 post-only RPI 報價撮合**，是 taker 執行成本的免費單向改善，maker-nogo 審計未覆蓋此 lever（它改的是 taker 腿不是 maker 腿）。
3. **Token unlock 供給衝擊事件軸**有大樣本外部實證（Keyrock，16,000+ 事件，~90% 負向，30 天前置 drift）——多日持有期把 taker 成本牆攤薄成噪音，且屬於已被裁「值得 $0 累積」的事件軸的具體化，非重打舊戰場。

另有四條：新上市 capture 基建已部署但 **0 事件累積**（runtime 證據，niche 永遠不會自己出證據）；maker-nogo 前提監測項（費率活動輪替是實證存在的）；BTC options VRP 的 $0 數據累積（paradigm_challenge：非方向性原生數學）；IBKR lane 的 point-in-time 數據累積 ROI 論證（以 NY Fed「overnight drift 已死」為 decay-verification 的反面教材錨定）。

所有外部實證一律 ASSUMPTION 直到本地 leak-free 驗證。無任何條目建議降 Cost Gate 或繞既有 gate。

---

## 2. 證據紀律聲明

- 本地 runtime 證據：`ssh trade-core` read-only psql（SELECT only）+ Mac repo grep。命令全文列於各節，可重跑。
- 外部證據：每條 opportunity 的 sources 均經 WebFetch 實開並引原文。打不開者（keyrock.com 原文 403、techflowpost 403、learn.bybit.com timeout）已標 unverified-source 或改用可開的轉載源。
- Bull-only / 單 regime 結果均標 regime_caveat。

## 3. 本地約束基線（牆的現值，runtime/repo 取證）

| 約束 | 現值 | 證據 |
|---|---|---|
| VIP0 perp 費率 | maker +2.0bps / taker 5.5bps（無 rebate） | 外部：bybitglobal Trading-Fee-Structure「Maker 0.0200% / Taker 0.0550%」；repo：`settings/hftbacktest_fill_realism.toml:41` maker_fee_bps_per_leg=2.0、`settings/paper_config.toml:11` taker_fee_rate=0.00055 |
| VIP0 spot 費率 | maker/taker 均 10bps | 同上 fee-structure 頁「Non-VIP Spot Maker 0.1000% / Taker 0.1000%」 |
| maker-first 牆 | fill_sim 雙窗 0/172 cell 淨正；best cell −3.2bps/fill；rebate 僅機構 MM program | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--maker_first_microstructure_feasibility_verdict.md` |
| 資本量 | 標準授權 cap 954.46 USDT（Demo envelope） | `TODO.md` v773 §0 Runtime auth reality 行 |
| 當前候選 | `ma_crossover|NEARUSDT|Buy` avg net 64.983bps / outcome_count=5058，零 order/fill proof | `TODO.md` v773 §0 Current candidate evidence 行 |
| 當前 funding regime（25-symbol 宇宙） | 48h 內 25 symbols：max APR 10.95%（=IR floor 0.0001/8h 指紋）、median 3.64%、min −3.33% | `ssh trade-core "psql ... -c \"WITH r AS (SELECT DISTINCT ON (symbol) symbol, funding_rate_daily*365*100 AS apr FROM market.funding_rates WHERE ts >= now()-interval '48 hours' ORDER BY symbol, ts DESC) SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY apr), max(apr), min(apr) FROM r;\""` → `25 | 3.64 | 10.95 | -3.33`（2026-07-09） |
| BTC 即時 funding | 0.00006182/8h ≈ 6.8% APR（低 premium） | `https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT` fundingRate="0.00006182"（2026-07-09） |
| 新上市 capture | `research.listing_capture_events` = **0 rows**（06-02 部署至今） | `ssh trade-core "psql ... -c 'SELECT count(*) FROM research.listing_capture_events;'"` → 0 |
| funding 數據面 | `market.funding_rates` 4855 rows，2026-04-05 ~ 07-09（新鮮），但僅 25 成熟 symbols | 同上 psql（count/min/max ts） |

讀法：taker 牆（RT 11bps+滑點）對 1m 方向策略是致命的，但對多日事件持有是噪音；maker 牆（+2bps 費非 rebate）鎖死成熟 perp 被動報價；spot 10bps 牆使現貨腿昂貴——Spread Trading 的 50% 折扣正打在這裡。

---

## 4. 機會項（7 條，全文）

### O1 — RPI taker access：taker 腿免費執行改善（新 API lever，2026-06 上線）
- **機制**：Bybit RPI 單是「assigned market maker」才能掛的 post-only 報價，原本只與 Web/APP retail 流撮合。2026-05-21~06-03 changelog 起，普通帳戶 API 單新增 `rpiTakerAccess` 參數：`true` = 你的 taker 單有資格對 RPI 報價撮合（價格改善 + 額外深度），並回報 `rpiMatchedQty`。WS 端 2025-07-15 起有含 RPI 的 orderbook feed（2025-07-22 起支援 perp）。
- **hypothesis（可證偽）**：在我們 25 個成熟 perp 上，RPI-inclusive book 相對 regular BBO 存在可測的價格改善；若我們 taker 單開啟 `rpiTakerAccess`，per-fill 有效成本改善 > 0bps（量級待測，先驗猜 0.1~2bps/fill）。證偽方式：錄兩份 book，改善分佈中位數 ≤ 0 或觸及量為 0。
- **why_not_tried**：參數 2026-06-03 才進 changelog（gradual rollout），晚於我們執行棧設計與 maker-nogo 審計；系統內無人掃 API changelog 找成本 lever。
- **est_edge**：未知，需測量。方向確定非負（opt-in 只增加可撮合流動性，不改費率）。對 avg net 64.98bps 的候選是加項，對 taker RT 11bps 牆是 chip 不是 break。
- **est_cost**：測量 $0（擴一路 WS 錄製，與既有 L1 recorder 同類）；之後下單參數改動屬小型 gated E1 工作。
- **wall_break_prob**：low（單獨不翻牆，但免費、單向、疊加）。
- **how_to_validate（leak-free）**：①BB 核 API 文檔確認 demo 支援與 rollout 狀態；②$0 錄 RPI-inclusive orderbook WS topic vs regular BBO（我們既有 L1 錄製棧），按 symbol×size 分佈量化「若當時 taker 會拿到的改善 bps」——純觀測無 look-ahead；③若中位改善>0，才提 gated demo A/B（同策略同窗口 rpiTakerAccess on/off 對照 fills 的 slippage_bps，V145 schema 已有欄位）。
- **classification**：機制存在=FACT（官方文檔）；edge 量級=ASSUMPTION。confidence：med（機制）/low（量級）。
- **local_constraint_fit**：完全在 Bybit-only 邊界內；不觸 Rust 授權邊界（僅訂單參數，仍走 Decision Lease/5-gate）；VIP0 適用（該參數就是給 retail taker 的）；資本量無關。缺前提：demo 環境是否支援 RPI 撮合需 BB 確認；若 demo 無 RPI 流，驗證只能靠 mainnet 公開 book 錄製（仍 $0 read-only）。

### O2 — Bybit Spread Trading 原子 funding carry：翻 funding_short_v2 的兩堵牆（regime-gated）
- **機制**：Bybit Spread Trading（API 2025-04-14 上線，rate limit 20/s）把 Spot+Perp / Perp+Expiry 等組合做成單一原子 instrument（`contractType=FundingRateArb/CarryTrade/PerpBasis/FutureSpread`），兩腿要麼同時成交要麼都不成，且「費率比分腿執行低 50%」。這直接消滅 funding carry 的 leg risk，並把 spot(10bps)+perp(5.5bps) 的入場 taker 成本從 15.5bps 壓到 ~7.75bps。
- **重提裁決的推翻證據**：funding_short_v2 的 DOA 已被 BB 更正為 regime-dormant（正側 cap 是 IR floor 指紋非結構封頂）；真問題=160% break-even 門檻（成本/門檻設計範疇）。本項引入的**新機制**（原子執行+50% 費折）恰好作用在 break-even 分母上——這是前提變化，非同一測試重跑。funding 四軸 NO-GO 是「funding 作方向信號」的裁決，本項是 carry income 機制，不同範疇。
- **hypothesis（可證偽）**：存在 funding regime 窗口（bull premium），使得經 Spread Trading 執行的 delta-neutral carry 在扣除全部費用+滑點後年化淨收益 > 0 且 > 資金機會成本；且該窗口可由公開 funding/predicted-funding 提前識別。證偽：全 regime 掃描後淨收益窗口佔比≈0 或窗口不可提前識別。
- **why_not_tried**：Spread Trading 產品晚於 funding_short_v2 審計（2026-05-31）；我們的 funding 監測面只有 25 個成熟 symbols（runtime 證據），carry 機會（新幣/meme 極端 funding）根本不在監測範圍內；引擎無 spread endpoint family 支援（undeveloped）。
- **est_edge**：外部通識：0.03%/8h≈33% APR 毛收益的窗口歷史上反覆出現（cap SSOT=per-symbol upperFundingRate，正側可達 +547%~+2190% APR，見 2026-05-31 ERRATUM）；淨值=毛 funding −（入場+出場 ~15.5bps 攤提）− basis 波動。當前我們宇宙 max 10.95% APR=IR floor → **現在不可做**。
- **est_cost**：監測 $0（spread instruments 是公開 GET；全 linear funding 一次 tickers 呼叫覆蓋）；未來實作屬中大型（新 endpoint family + cross margin 要求 + Guardian/lease 接線），只在監測觸發後才立項。
- **wall_break_prob**：med（機制對牆是正面打擊，但受 regime 閘控）。
- **regime_caveat**：**bull-premium regime-bet**。當前 25-symbol 宇宙 funding 全貼 IR floor（runtime 2026-07-09）；一切正 carry 結果須標 regime-bet/learning-only。
- **how_to_validate（leak-free）**：①$0 建 daily cron：公開 tickers 全 linear universe funding + spread instruments 清單快照（append-only point-in-time，沿用 Polymarket 軸紀律）；②歷史面用 `research.alpha_funding_rates_history` + funding/history 回補做全 regime carry 回測（費率用上表現值不打折，滑點取上限）；③觸發閾值（預註冊）：任一 spread-listed symbol 預測 funding 年化 > 3×(入場+出場成本年化攤提+basis σ buffer) 連續 ≥3 個結算週期 → 才開 spread lane 立項評審；④demo 可用性由 BB 核（未知）。
- **classification**：ASSUMPTION（機制=FACT，本地淨 edge 未證）。confidence：med（機制/成本結構）/low（窗口頻率）。
- **local_constraint_fit**：Bybit-only ✓；VIP0 下 50% 折扣仍成立（折的是我們自己的 tier 費率）；資本 954 USDT cap 夠開最小 spread 倉試錯；缺前提：引擎 spread endpoint 支援（undeveloped）、demo 可用性未知、cross margin 模式需求 vs 我們風控配置需 PA 評估。監測本身零前提。

### O3 — Token unlock 供給衝擊事件軸（多日持有攤薄 taker 牆；事件軸具體化）
- **機制**：Keyrock 對 40 個主要 token、16,000+ unlock 事件的研究：~90% unlock 事件伴隨價格下跌；下跌 pre-drift 在解鎖前 ~30 天開始、最後一週加速、解鎖後 ~14 天回穩；team unlock 傷害最大（ApeCoin 案例 7 個月 −77% vs 同期 ETH −9%）、VC/investor unlock 因對沖而影響受控。事件日曆是公開 $0 數據。
- **hypothesis（可證偽）**：對「解鎖量/流通市值 ≥ X%（初設 1%，sweep 記 K）的 cliff unlock」，事件前 T−21d~T−3d 窗口的 **beta 中性化**（demean vs BTC/宇宙）超額收益顯著為負，且幅度 >> taker RT 成本（11bps）+ 做空期間 funding drag。證偽：beta 中性後 |t|<1.96（Bonferroni 修正後）或淨幅度 < 成本。
- **why_not_tried**：事件/監管軸 2026-06-13 已裁「值得 $0 累積」但從未有人把 unlock 日曆接進來；先前所有短 bias 實驗死於 down-beta 偽裝（2026-06-03 教訓），本設計把 beta 中性化寫進主規格而非事後補救。
- **est_edge**：外部：事件級中位負 drift 數 %~雙位數 %（team cliff 最強）。本地淨值=ASSUMPTION；多日持有下 11bps RT + funding drag（做空弱勢 alt 時 funding 常為負→short 付費，須逐事件計價）合計仍遠小於外部宣稱幅度。
- **est_cost**：$0 數據（公開 unlock 日曆，需 append-only point-in-time 採集防回填偏差）+ 既有 daily-kline backfill 基建（AEG 2026-06-02 部署）擴到事件 symbols；回測為離線 Python，走 E1/MIT 協查。
- **wall_break_prob**：med（事件幅度 vs taker 牆的比值結構上有利；風險在 crowding 與樣本 regime 混雜）。
- **regime_caveat**：Keyrock 樣本跨 2021-2024 多 regime 但以 alt 弱勢期為主；「90% 負向」含 beta 成分——**未 beta 中性化的外部數字不可直接當 alpha**。本地驗證必須 demean，否則就是 down-beta 偽裝重演。
- **how_to_validate（leak-free）**：①採集：unlock 日曆快照 append-only、記錄「事件公告時間 vs 解鎖時間」兩個時戳（只用公告後資訊，防 look-ahead）；②事件研究：T−30~T+14 逐日 AR/CAR，beta 中性（對 BTC + 宇宙等權雙 demean），cluster-SE by token，Bonferroni（記 sweep K）；③成本側：每事件用當時 funding/history 計 short-leg funding drag，滑點取上限；④樣本門檻：≥30 個合格 cliff 事件才出裁決（power 前置）；⑤全程離線，不觸 runtime。
- **classification**：ASSUMPTION（外部實證≠我們的證據）。confidence：med（外部樣本大、機制可解釋=供給衝擊+前置對沖行為）。
- **local_constraint_fit**：多日持有=taker 執行可接受，不需 maker rebate；VIP0 成立；954 USDT cap 下單事件單倉可行；Bybit-only（僅交易 Bybit 有 perp 的 unlock tokens，宇宙夠大）；缺前提：unlock tokens 多數不在現 25-symbol 監測面 → 需 kline+funding 數據面擴充（$0，read-only cron）。Alpha 8 來源歸類：#2 結構性低效（強制供給衝擊+資訊完全公開但套利受借券/風控約束）。

### O4 — 新上市微結構 niche：已建 capture 基建 0 事件，機會在「按下開始鍵」
- **機制**：maker-nogo 明示保留「新上市寬價差 niche」（adverse selection 尚未被 HFT 佔滿的短窗口）。外部 2024 全年上市效應研究顯示各所上市後動態顯著分化，Bybit 上市表現「relatively stable、low coefficient of variation」（可預測性相對高）；Binance 2024-2025 上市後平均 −71.7%（search-level，unverified）說明上市後普遍存在可觀的方向性/流動性結構事件。
- **runtime 事實**：`research.listing_capture_events` 自 2026-06-02 部署以來 **0 rows**——Gate-B 隔離 listing 探針是 operator-timed，從未觸發過一次真實捕捉。Niche 不會自己出證據。
- **hypothesis（可證偽）**：Bybit 新上市 perp 首 24~72h 的 spread/深度/成交結構存在系統性模式（寬價差窗口長度、假突破率、funding 極端度），其中至少一個模式在扣除 VIP0 費率後有正期望執行路徑（maker 或事件 taker 皆候選）。證偽：≥5 個上市事件的 capture 顯示寬價差窗口 < 分鐘級或全被 adverse selection 吃掉（fill_sim 的 wide-spread tension 在新上市同樣成立）。
- **why_not_tried**：capture 是 operator-timed dormant；上市節奏不可控導致「等」而不是「排程」；maker-nogo 之後無人回頭把 niche 變成有時間表的監測任務。
- **est_edge**：unknown（這正是要累積的東西）；外部僅證明事件結構存在，未證明零售可捕獲。
- **est_cost**：基建已 sunk（$0 增量）；每事件一次 24h capture 的存儲/運維成本近零；需要的是上市公告監測 cron + operator 一次性授權「下 N 次上市自動 capture」。
- **wall_break_prob**：unknown（數據為零，這是誠實答案；fill_sim 的 wide-spread tension 是先驗反方）。
- **how_to_validate（leak-free）**：①監測：Bybit announcements 新上市頁納入 daily WebFetch（BB 或 cron）；②請 operator 授權「未來 5 個新上市自動觸發 Gate-B capture」（R-0 zero-leak 已驗）；③5 事件後 QC 出 microstructure 事件研究（spread 衰減曲線/adverse selection markout），才決定是否有可立項的執行路徑。
- **classification**：runtime 0-事件=FACT；niche 有 edge=ASSUMPTION。confidence：low。
- **local_constraint_fit**：完全在既有基建與 Bybit-only 邊界內；不觸交易授權（純捕捉）；唯一缺的前提是 operator 的排程授權（這本身就是本項的 ask）。

### O5 — 費率/活動前提監測（maker-nogo 的 unlock 條款落地為機械監測）
- **機制**：Bybit 實證存在輪替性費率活動（例：USDC 交易費折扣活動至 2026-06-30、MM weight upgrade——此二者 search-level unverified，原文 403；但 fee ladder 與 VIP 結構本身已從可開的 fee-structure 頁證實）。maker-nogo 的 no-repeat 條款本身寫明「Reopen only on changed fee/rebate tier, institution/MM program approval, or pre-registered new event/listing evidence」——本項把它變成有對象/閾值/負責人的機械監測，而不是被動等待。
- **hypothesis（可證偽）**：未來 12 個月內出現至少一次「有效 maker 費率 ≤ 0.4bps 的窗口」（活動、新 product line、或 tier 變化）。0.4bps 來源：maker-nogo 結案的 break-even 門檻（memory 索引；INFERENCE 級，重開時以 fill_sim 預註冊重跑為準）。
- **why_not_tried**：NO-GO 後前提監測沒有被指派為週期任務；費率頁不在任何 cron/WebFetch 清單。
- **est_edge**：觸發時=重跑 fill_sim 的期權價值（0/172 → 在新費率下重評 172 cells，成本一次離線重跑）。
- **est_cost**：每月 1 次 BB WebFetch fee-rate 頁 + announcements 頁，≈0。
- **wall_break_prob**：low（等待外生事件），但監測本身成本為零、期權價值為正。
- **how_to_validate**：監測對象=①`bybitglobal.com/.../Trading-Fee-Structure`（maker/taker ladder）②Bybit announcements fee 類目 ③MM program 准入條件。閾值=有效 maker ≤ 0.4bps（任一 perp 產品線、任一活動窗口）或出現負費率/rebate 條目。負責人=BB 月度巡檢，觸發後 QC 主持 fill_sim 預註冊重跑（不重寫判準，直接沿用 2026-07-06 的 harness）。
- **classification**：ASSUMPTION（對「窗口會出現」）；監測機制=FACT 可執行。confidence：low。
- **local_constraint_fit**：純 read-only WebFetch；零授權邊界問題。

### O6 — BTC options 波動率風險溢價（VRP）$0 數據累積【paradigm_challenge=true】
- **機制**：學術與從業實證（Deribit 數據 2017-2022）顯示 BTC 存在可觀 VRP：年化 ~0.14，低波動 cluster 0.17 / 高波動 cluster 0.12（IV 系統性高於後驗 RV）。這是**非方向性**原生數學（賣保險收 premium），從結構上跳出殺死既有軸的「線性IC×OHLCV×方向×taker 牆」測試——這正是 operator 鐵則要求的換 lens。Bybit 有 USDC options，VIP0 費率 maker 2bps / taker 3bps（of underlying）。
- **hypothesis（可證偽）**：Bybit BTC options 的 30d ATM IV − 後驗 30d RV 在本地樣本上中位數 > 0 且扣除（費率+雙邊 spread 上限估計）後仍 > 0。證偽：淨 VRP 中位 ≤ 0，或 Bybit options spread 寬到吃光 premium（crypto IV 市場淺是已知先驗反方，見 quant-strategy-design #5 風險欄）。
- **why_not_tried**：引擎零 options 支援；「無對應數據源的異常=不可回測→Reject」的既有紀律擋住了提案——本項先補數據源（$0 公開 options tickers 快照），把它變成可回測。
- **est_edge**：外部毛 VRP 10~17 vol pts；本地淨值 ASSUMPTION（Bybit options 流動性遠遜 Deribit，spread 上限未測）。
- **est_cost**：$0：daily cron 快照 Bybit options 公開 tickers（IV/mark/greeks），append-only point-in-time；分析離線。實作交易屬遠期（引擎 options 支援=大型工程），**本項只買數據期權**。
- **wall_break_prob**：unknown（此 lens 的牆是 options spread/流動性，非 taker 費率牆；未測）。
- **regime_caveat**：VRP 在高波動 cluster 收窄（0.12）且 BTC 的 BP-BVRP 關係與股指相反（外部原文），賣 vol 在 crypto 的尾部風險結構未經 2020-03/2022-11 級事件在 Bybit venue 的本地檢驗——任何正結果先標 learning-only。
- **how_to_validate（leak-free）**：①$0 快照累積 ≥90 天；②IV 取快照時點值（point-in-time），RV 用其後 30d 我們自己的 1m kline 計算（×365 年化，無 look-ahead）；③淨值=VRP − 費 − spread 上限（用快照 bid-ask 實測，不假設中價成交）；④≥90 天且跨至少一次 vol regime 切換才出初裁。
- **classification**：ASSUMPTION。confidence：low-med（外部實證紮實，本地 venue 流動性是主不確定）。
- **local_constraint_fit**：Bybit-only ✓（Bybit 自有 options）；read-only 快照零授權問題；954 USDT 資本對未來 1 張 BTC option 最小倉是緊的（需屆時算 margin）；缺前提：引擎 options 支援（undeveloped）、demo 對 options 的支援未知（BB 屆時核）。Alpha 歸類：#5 波動率錯定價。

### O7 — IBKR read-only lane：point-in-time 數據累積的 ROI 論證（decay-verification 框架）
- **機制**：NY Fed 2026-07 自己發文證實其著名 overnight drift「2:00–3:00 窗口過去年化 ~3.7%、2021 起均值≈0」——教科書級的 post-publication decay。這給 IBKR lane 的研究價值定調：**任何未來 stock/ETF 策略評估的第一資產是「自己採集的 point-in-time 歷史」**，因為 leak-free 歷史無法事後回填（供應商數據有 survivorship/修訂問題），而 anomaly 的生死判定（如上例）需要跨年度自有樣本。Lane 現在唯一能做的（read-only/paper，禁 order-write/禁 auto-promote）恰好就是這件事。
- **hypothesis（可證偽）**：以 delayed/免費數據對一籃子高流動 ETF（SPY/QQQ/IWM + IBIT 等 crypto-adjacent）做 daily+session-boundary point-in-time 採集，12 個月後該數據集足以支撐 ≥2 個經典 anomaly（PEAD 類/季節類）的本地 replication 裁決（能明確判 alive/dead）。證偽：數據質量（延遲/缺口/無法點時化）使 replication 檢定 power < 0.5。
- **why_not_tried**：lane 剛到 Phase 2（首個外接 B1 connector 2026-07 才 landed）；「採什麼」尚無研究側規格——工程軸跑在研究軸前面。
- **est_edge**：間接（期權價值）：省去未來 12 個月的數據 lead time；並為「非-Bybit 資產類」擴張提供第一份自有證據基底。不承諾任何收益。
- **est_cost**：≈$0（paper 帳戶 delayed data 免費；存儲邊際成本近零）；規格設計 1 份 QC/MIT 文檔。
- **wall_break_prob**：unknown（本項不打牆，買的是未來裁決能力）。
- **regime_caveat**：美股 anomaly 樣本以 2010s bull 為主，任何 replication 陽性結果須標 regime 依賴。
- **how_to_validate**：①QC/MIT 出採集規格（symbol 清單、時間戳紀律、修訂處理、append-only）；②E4 核 delayed data 的實際延遲與缺口率（read-only）；③6 個月 checkpoint：以「已知已死」的 overnight drift 作 negative control——我們的數據應能 replicate 它的死亡（校準數據質量），再去測存疑 anomaly。
- **classification**：ASSUMPTION。confidence：med（數據 ROI 論證）/low（任何 alpha 含義）。
- **local_constraint_fit**：ADR-0048 邊界內原生成立（read-only 研究正是 lane 的全部權限）；不觸 Bybit path；禁 order-write/auto-promote 不受影響；缺前提：G4 首次外接的 operator 一次性批准（已在 IBKR 軸排程中，非本項新增 ask）。價格-lead 陷阱聲明：明確**不**提「IBIT/ETF 價格 lead BTC perp」類 hypothesis（Polymarket 價格軸 KILL 的同構陷阱——ETF 價格是 spot 套利鎖定的衍生序列）。

---

## 5. 風險與反方（QC 自我對抗）

1. **O2/O3 的共同反方**：兩者的外部數字都含 beta/regime 成分。O3 已把 beta 中性化寫進主規格；O2 的 carry 是機械收入但 basis 波動在極端行情可瞬間吃掉數月 funding（2020-03-12 式 backwardation）——驗證規格已要求全 regime 回測+滑點上限。
2. **O1 反方**：RPI 觸及量可能集中在 BTC/ETH 大 symbol、我們的小單在 RPI book 的實際觸及率未知；測量先行設計正是為此。
3. **O6 反方**：Bybit options 深度遠遜 Deribit，spread 上限可能直接否決；$0 快照會直接回答這一點，不需要任何承諾。
4. **crowding**：unlock 前置做空是公開知識（Keyrock 報告本身會加速 alpha 衰減——McLean-Pontiff post-publication decay 對此軸同樣適用）；本地驗證必須用近期樣本分段檢查衰減趨勢。
5. **本報告未建議任何立即交易行動**；全部 7 項的第一步都是 $0 read-only 數據/監測動作，與現行 gate 體系零衝突。

## 6. 前提解鎖監測表（彙總）

| 被鎖方向 | 監測對象 | 閾值 | 負責人/頻率 |
|---|---|---|---|
| maker-first mature-perp（NO-GO） | Bybit fee-structure 頁 + announcements 費率活動 + MM program 准入 | 有效 maker ≤ 0.4bps 或 rebate 出現 | BB 月度 WebFetch；觸發→QC 重跑 fill_sim（預註冊沿用原 harness） |
| funding carry（regime-dormant） | 全 linear universe funding（公開 tickers 一次呼叫）+ spread instruments 清單 | 任一 spread-listed symbol 預測 funding 年化 > 3×成本攤提，連續 ≥3 結算週期 | $0 daily cron（需 PM 排程授權）；觸發→spread lane 立項評審 |
| 新上市 niche（開放未評） | Bybit 新上市公告 | 每一個新 perp 上市 | operator 授權未來 5 次自動 Gate-B capture；5 事件後 QC 出裁決 |
| options 軸（不可回測→未評） | Bybit options 公開 tickers 快照累積天數 | ≥90 天且跨 1 次 vol regime | $0 daily cron；90 天後 QC 出 VRP 初裁 |

## 7. 容量與成本總評

- 全部第一步動作合計增量成本 ≈ $0（WebFetch/公開 GET/既有基建），無 AI 調用成本，無付費 feed。
- 954 USDT 資本量下：O2 最小 spread 倉、O3 事件單倉可行；O6 遠期 options 倉需屆時 margin 精算。
- 容量天花板都遠高於現資本量——在我們的量級，容量不是約束，執行成本與樣本量才是。

## 8. 建議

**PROCEED（監測/數據層，$0 read-only）**：O1 測量、O2 監測 cron、O3 事件軸採集+離線事件研究、O5 月度費率巡檢、O6 options 快照、O7 IBKR 採集規格。
**REVISE 後再議（需 operator 一次性決定）**：O4（授權未來 5 次上市自動 capture）。
**不建議**：任何立即降 gate、立即開新交易 lane、或以外部數字直接餵 edge_estimates 的動作。

翻案條件聲明（本報告內的負向/保守判定）：O2「現在不可做」被推翻的最小證據=監測閾值觸發的 runtime funding 快照；O6 被否決的最小證據=90 天快照顯示 spread 上限 > 毛 VRP。

---

*QC · 2026-07-09 · read-only EXT scan；Linux 證據均可由 §3 命令重跑。*

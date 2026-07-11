# PA 綜合盈利機會地圖（ROI 排序）— 2026-07-09

**Agent**: PA（Project Architect，綜合裁決 + 派發設計）
**邊界**: read-only 盈利研判。零修復/零策略·風控·gate·config 改動/零部署/零重啟/零交易/零 auth。Linux 證據僅 `ssh trade-core` read-only。
**輸入**: 五份 Stage 2 研判報告（全文讀畢）：
- QC `2026-07-09--profit-diagnosis-stage2-qc.md`
- QC `2026-07-09--ext-profit-intel-scan.md`
- MIT `2026-07-09--profit-diagnosis-stage2-ml-lens.md`
- BB `2026-07-09--bybit_profit_diagnosis_readonly.md`
- AI-E `2026-07-09--profit_research_stage2_guard_attack.md`
**框架紀律**: 市場必然可主動盈利——NO-GO 是換思路路標。本圖不重打 maker-first mature-perp / Rank7 四軸 / Polymarket 價格軸 / carry-KILL / 直接 AI-trader 等已判裁決；其前提全部轉為 unlock 監測項（§4 #5）。

---

## 1. PA 證據重跑記錄（抽樣核對，全部通過，無降級）

依證據紀律，對擬入 top_moves 的 FACT 級支撐親自重跑（2026-07-09，ssh trade-core read-only + Mac repo grep）：

| # | 支撐 | 重跑結果 | 對照報告值 | 判定 |
|---|---|---|---|---|
| 1 | 30d fills true net | demo 1011 筆 fee 254.68 gross −148.61；live_demo 44/0.71/−2.11 → true net **−406.11 USDT** | MIT A.1 / QC / BB 同 | ✅ FACT |
| 2 | fee 分解 | maker 90@2.00bps / taker 398@5.73bps / paper_sim 5 | BB D1 同 | ✅ FACT |
| 3 | close-maker 漏損 | attempt=t: maker 90 / postonly_reject 116 / timeout_taker 117 → 成功率 27.9%；close maker 佔比 90/488=18.4% | BB D2 同 | ✅ FACT |
| 4 | F1 偽複製 | `2614× entry_ts=1783436340000 @+70.28bps` + `2444× entry_ts=1783436400000 @+59.32bps` = 5058 outcomes、**2 distinct entry** | QC §3 / MIT F1 同 | ✅ FACT（CRITICAL 復驗） |
| 5 | outcome_review.py 無去重 | `grep -n "entry_ts\|dedup\|distinct\|uniq"` = **0 hit**；`sample_factor=min(2.0, outcome_count/min_outcomes_per_side_cell)` 用 raw count | MIT 增量取證 1 同 | ✅ FACT（機制級） |
| 6 | 誤殺母集 | blocked_outcome_review_latest.json：`GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT=33`、`flipped=3` | QC §4 同 | ✅ FACT |
| 7 | promotion 死鎖 | `learning.decision_shadow_exits` = **0 row** | MIT D5 同 | ✅ FACT |
| 8 | 標籤斷糧 | 7d `label_source='realized_fill'` = **14 行** | MIT D4 同 | ✅ FACT |
| 9 | 1d klines 資產 | 19,751 行 / 26 symbols / 2024-06-02→2026-07-08 | QC O1 同 | ✅ FACT |
| 10 | listing capture | `research.listing_capture_events` = **0 row**（06-02 部署至今） | QC-EXT O4 同 | ✅ FACT |
| 11 | L1 timeout | ollama success=f **732** / t 15（報告時點 728/15，方向一致=持續惡化中） | AI-E D1 同 | ✅ FACT |

TODO.md active state 親核：loop 仍停 `READY_FOR_PM_E3_DISPATCH`（row 37/38），`outcome_count=5058` 仍被引為候選證據 → **F1 修復尚未被任何 session 推進**，本圖排序 current。

**Call-path 定位（selection-bias finding 紀律）**：F1 屬研究 lane 證據管線（`helper_scripts/research/cost_gate_learning_lane/outcome_review.py` → `blocked_outcome_review_latest.json` → TODO READY 鏈），**不觸 production IndicatorEngine / gate 主路徑**（gate 本身行為無變化）；grep proof 見上表 #5。

## 2. 綜合裁決（守側統一敘事）

1. **成本牆是唯一的直接虧損機制**：30d true net −406 USDT，fee=gross 虧損的 1.7×；taker RT ~19-23bps vs per-fill gross p50 −1.17bps。1m 頻率下無策略可跨牆（需 IC>2，不存在）——範式約束非參數問題。
2. **證據管線先於一切 dispatch**：唯一候選（NEAR 64.98bps）statistically void（n_eff≈1-2 偽複製 + 單日 +1.6% episode regime-bet）；反事實成本模型 conservative_v1 高估 ~4-5×（92.3bps vs 實測 E[cost]≈23bps）。兩失真方向相反 → 系統當前**無法回答 gate 誤殺量**。修 F1+成本雙軌是全系統性價比最高的一次確定性計算。
3. **內部三重死鎖**（全部 FACT、全部 operator/E1 可解）：標籤供血 ≈2/day（soak isolation）→ promotion gate 讀 0-row 死表 → AI 三層 0 歸因。修 AI 不解鎖盈利；解鎖 fills/標籤才解鎖 AI。
4. **可回收執行漏損存在但上限誠實**：close-maker 27.9% 成功率、postonly_reject 35.9% 可機械消除；markout-adjusted 真實省 ~2bps/腿（非 naive 9.7）。縮虧是 chip 非 break。
5. **真機會在範式自由度**：horizon（1d 資產閒置）、population（TradFi 股票 perp spread 15-116bps 從未被 maker-nogo 母體覆蓋）、event（unlock/listing/funding 結算窗）、解讀層（AI 離開方向判斷位）。

## 3. 跨報告 reconcile（PA 裁決）

| 分歧/銜接點 | 裁決 |
|---|---|
| 誤殺母集 49,388（MIT，單一 reason 字串）vs 71,207（QC，regex 全類） | 採 QC 71,207 為重跑母集；但「有效 cell 數 ~4-10、高度集中 ETH/FIL/APT/ARB」是真約束——期望管理按 cell 計非按 row 計 |
| conservative_v1 修法 | 採 QC 雙軌制（E[cost] 主判 + tail CVaR 敏感性欄並列），**非**單純調低成本——防把「保守」錯改成「樂觀」 |
| AI-E O1（LLM 解讀層）驗證前提 | 其引用的 Gate-B 探針數據**現為 0 row**（QC-EXT FACT，本輪重跑 #10 同）→ O1 對 #7（capture 授權/公告流累積）有硬依賴，排序後置並標依賴 |
| bb_reversion maker 化 edge | maker markout n=3 → 一切 maker 化推論以 INFERENCE 封頂（QC 自申報）；本圖照標 |
| QC 自申報 gap：cost_gate threshold 的 edge 語義（是否雙重扣成本=06-14 PROFIT-1 殘留） | 併入 #1 的 E1 子任務（溯源 `cost_gate` 變體實作），**待證實**——不作 P0/P1 阻塞結論 |
| BB O5（Bybit Alpha Prediction Market） | **不入 top_moves**：產品邊界（Bybit Alpha on-chain venue 是否在「Bybit 唯一交易所」內）需 CC 先裁；裁決前 $0 都不投 |

## 4. Top Moves（ROI 排序）

排序原則落地：最快驗證優先（$0 離線/既有 harness > 新建）；翻牆概率×證據強度；ASSUMPTION 不排前段並標「需先 leak-free 驗證」；帶 regime caveat 者不憑 bull 窗數字前置；defend/attack/unlock/learn 四模式齊備。

| # | Move | mode | 證據 | 翻牆 | blocker | owner |
|---|---|---|---|---|---|---|
| 1 | 反事實證據管線修復（dedup+成本雙軌）+ 71,207 母集/33 cells 重跑；修復前凍結現榜 order-capable dispatch | defend | FACT | med | gate | E1+QC（MIT 審） |
| 2 | bb_reversion maker 化 fill_sim 重放（唯一 gross 正 cell +9.06bps → 零成本樣本破 JS 自鎖） | defend | INFERENCE | med | cost | QC+E1 |
| 3 | Horizon arbitrage：日級 cross-sectional beta 中性 long-short（1d 資產 $0 在位） | attack | INFERENCE | med | paradigm | QC+E1（MIT 審） |
| 4 | 執行衛生包：BBO-peg PostOnly（消 35.9% postonly_reject）+ rpiTakerAccess 觀測先行 | defend | FACT | low | undeveloped | E1+BB |
| 5 | 前提解鎖監測包（6 監測：標籤供血/promotion 死鎖/loop n_eff/fee-tier/funding+spread venue/maker 費率活動） | unlock | FACT | med | gate+cost+dormant | PM+BB+E1+operator |
| 6 | TradFi 股票 perp × IBKR read-only anchor：$0 PIT 偏離統計先導 | attack | INFERENCE | med | paradigm | BB+QC |
| 7 | 新上市 niche 活化：operator 授權 5 次自動 Gate-B capture + 極端 funding 結算窗離線 event study（後者今天可跑） | attack | FACT(現狀)/edge unknown | unknown | dormant | operator+QC/MIT |
| 8 | Token unlock 供給衝擊事件軸：$0 append-only 採集 + beta 中性事件研究 | learn | ASSUMPTION | med | paradigm | E1+QC/MIT |
| 9 | L1 judge_edge timeout 校準 + L0/L1 雙 verdict shadow A/B（AI ROI 首次可測） | defend | FACT | high(內部) | other | E1+AI-E |
| 10 | AI 重定位：事件/波動解讀層餵確定性 exit/sizing（依賴 #7 數據累積） | learn | ASSUMPTION | med | paradigm | AI-E+E1 |
| 11 | L2 解凍最短路徑：E2E-1 一次真調用 + sonnet-5 定價鍵（intro −33% 至 08-31，期限項） | unlock | FACT(前置齊備) | unknown | dormant | operator+PM |

### 各項要點（edge/成本/驗證/regime）

**#1** — 三報告共識（QC O3/MIT O1/AI-E D5+D8）。edge：flip 計數修復前不可知（FIL/ARB cells JS edge 21-25bps 是現存最高估計帶）；即使全負也有裁決價值（誤殺假說落錘）。成本：$0 數據 + E1 ~1 sprint（`outcome_review.py` per-(cell,entry_ts_ms) dedup+effective-n；`slippage_quantile_artifact.py` 已存在直接接入）。驗證：pre-register 判準；cluster-SE by day；雙軌成本並列；重跑後 false-negative 榜 vs realized 同 cell 矛盾檢查必附。**附帶止損**：dedup 落地前，PM/E3 checklist 前置 `distinct entry_ts ≥ min_outcomes_per_side_cell`，現 NEAR 候選不消耗 order-capable E3/BB 窗口（regime caveat：該候選=NEAR 單日 bull episode）。

**#2** — edge 上限誠實：maker 化後 net ≈ +0.3bps/RT（cost_edge_ratio 2.15→0.96），**非利潤引擎**，真價值=唯一 gross 正 cell 推到零成本樣本累積點破 epistemic deadlock。成本：$0（34M L1 rows + fill_sim harness 既有）。驗證：touch-based 禁 optimistic fill（承 2026-04-20 教訓）、queue 折扣 50%、markout 樣本擴 ≥30、paper/demo fill_rate 0.7-1.3 帶外禁餵 edge_estimates、demo 21d ≥200 trades 再裁。regime：30d 單窗，結論全 Conditional。與 maker-nogo 無衝突：M12 執行成本削減被明留 dormant，adverse selection 實為 strategy-conditional（bb_rev −2.37 vs flash_dip −12.68）。

**#3** — 唯一直接攻結構牆的範式挑戰：E[edge]=IC×σ(h)，σ(1d)≈300-500bps → IC 0.03-0.05 即跨牆（1m 需 IC>2）。外部文獻先驗（arxiv 1904.00890 等）+本地未驗 → INFERENCE，**需先 leak-free 驗證**。成本：$0 數據（重跑 #9 klines1d 證實在位）+ E1 ~1 sprint 離線 backtest。驗證：全特徵 shift(1)、rolling 90/30 walk-forward、sweep 記 K→DSR+Bonferroni、block bootstrap CI、成本 taker 23bps/RT 上界（不假設 maker）、demeaned beta 中性（承 06-03 down-beta 鐵則）、PSR(0)≥0.95 才進 demo。**regime 強制**：窗含 2024H2-2025 bull → 分層標註，bull-only 正結果=regime-bet/learning-only，不得憑此前置。

**#4** — 母集 FACT（重跑 #3 確認 116 postonly_reject/117 timeout/398 taker close）。edge 誠實：markout-adjusted ~2bps/腿、demo 絕對額小、scale 後線性放大；wall_break=low（chip 非 break）。成本：E1 order body 1-2 欄 + RPI 觀測欄落庫 + dict 補錄。驗證：demo A/B（reject/timeout 率可信）→ live_demo 小 n + through-print 判別（demo 無 queue position，fill 率偏樂觀，承 06-10 紀律）；RPI 0 命中即誠實結案。

**#5** — 六監測、near-zero 成本、全部有對象/閾值/負責人：
① 標籤供血：`SELECT count(*) FROM learning.decision_features WHERE label_source='realized_fill' AND ts>now()-interval '7 days'` <50/7d=餓死中（現值 14，重跑 #8）——operator 週巡，soak isolation 存續顯式計價；② promotion 死鎖：`SELECT count(*) FROM learning.decision_shadow_exits`=0 即持續（現值 0，重跑 #7）——PM 派 E1 查 V021 writer spawn；③ loop 證據品質：dispatch 前置 distinct-entry n_eff 檢定入 PM/E3 checklist；④ fee-tier premise：30d notional $690k vs VIP1 $10M（6.9%，方向惡化）——operator 月檢；⑤ funding+FundingRateArb spread venue：`/v5/spread/tickers` volume24h + majors funding APR（觸發閾值=預測 funding 年化 >3×成本攤提連續 ≥3 結算週期）——BB 月巡（regime caveat：觸發窗=bull premium regime-bet）；⑥ maker 費率活動：fee-structure 頁+announcements+MM program，閾值=有效 maker ≤0.4bps 或 rebate 出現——BB 月巡，觸發後 QC 沿用 2026-07-06 harness 預註冊重跑 fill_sim。

**#6** — 30d 62 檔新上市、股票 perp 子集 median spread 14.8bps / 尾部 115.8bps（BB curl FACT）vs fee 2-5bps=全系統唯一 spread>>fee population，且從未被 fill_sim NO-GO 母體（mature perp 0.02-6bps）覆蓋——非重打舊戰場。$0 先導=point-in-time 同步採集 Bybit 股票 perp BBO（公開 WS），只做偏離/收斂統計無交易；IBKR NBBO 腿等 G4 operator 批准後合流（ADR-0048：IBKR 永遠 read-only，執行僅 Bybit）。session bucket 分層（cash/overnight/halt）。regime：上市初期寬 spread 有時效、off-hours 盲窗、股票尾部（gap/halt/公司行動）須 QC 補風控設計。

**#7** — 基建 sunk 5 週 0 事件（重跑 #10 FACT）：niche 不會自己出證據，機會在排程授權（operator 一次性授權「未來 5 個新上市自動觸發 Gate-B capture」，R-0 zero-leak 已驗）+上市公告 daily 巡檢。**立即可跑腿**：BB O6 極端 funding 結算窗 event study（DATAUSDT −0.56%/4h 親證；`research.alpha_funding_rates_history` 2yr 在庫 + 1m klines，離線 leak-free：F 取結算前已知值、漂移取結算後窗）——不等 capture。5 事件後 QC 以 maker-nogo 同款雙窗判準出裁決（pre-register，只換母集）；n<5 繼續累積不下結論。regime：listing-regime-bet 標註。

**#8** — 外部大樣本（16,000+ 事件 ~90% 負向）但含 beta 成分——**未 demean 的外部數字不可當 alpha**（否則 down-beta 偽裝重演）。多日持有攤薄 taker 牆=結構有利。$0：公開 unlock 日曆 append-only 雙時戳採集（公告 vs 解鎖，只用公告後資訊）；T−30~T+14 AR/CAR、對 BTC+宇宙雙 demean、cluster-SE by token、Bonferroni 記 K、short-leg funding drag 逐事件計價、≥30 合格 cliff 事件才裁決、近期子樣本檢查 post-publication 衰減。

**#9** — L1 98% timeout（重跑 #11：732/15，持續惡化）。修 timeout 8→20-30s+keep_alive 是小時級 E1；價值=歸因基礎設施（終結「dead-AI 假合規」、裁決 180 call/day 去留），**不直接解鎖盈利**（AI-E 自判：解鎖 fills 才解鎖 AI）。30d 雙 verdict shadow → 分歧子集用 blocked_outcome 反事實管線比淨 bps。

**#10** — AI 離開方向判斷位（該位即使修好 D1 期望增量≈0）→ 事件/波動解讀層餵確定性 exit/sizing：per-fill 左尾重（p10 −45.65bps），削左尾 10-20% 即正 ROI（外部類比 ASSUMPTION，非本地實證）。**硬依賴 #7**：Gate-B 探針現 0 事件；先用公告哨兵流（07-04 復活）+polymarket 累積起步。驗證：WP2 PIT manifest 封裝、27B 離線批量標註、post-cutoff 子集單獨評估（防語義洩漏，FinMem −51% 警示）、IC vs baseline、過則 shadow 餵 exit-policy 反事實。LLM 永不驗 alpha。

**#11** — 與 06-13 相比治理前置全齊（daily $2 Rust gate 入 binary、writer/flock/P1 債修畢）=premise-changed 非重打；剩 operator 一鍵（E2E-1 one-shot 真調用後復原 disabled）。sonnet-5 鍵=同窗順手項（同 $2/day 預算 +50% 推理量），**期限 08-31**。edge=搜索空間擴展期權價值（unknown）；每個 AI 假設必過 WP2 PIT+DSR/PBO 確定性 gate。

### 落選/待裁決（不空手紀律下的誠實邊界）
- **Bybit Alpha Prediction Market**（BB O5）：CC 產品邊界裁決前 $0 不投——待 CC。
- **BTC options VRP $0 快照**（QC-EXT O6）：合法換 lens 但 90d 累積+引擎 options 支援=遠期；建議併入 #5 監測包的季度覆核觸發後再立項（本輪不佔 top_moves 位）。
- **IBKR 數據採集規格/S3-S5 PIT 契約**（QC-EXT O7/MIT O4/AI-E O6）：價值成立但全部 operator-gated 於 G4——併入 IBKR 軸既有排程（TODO 已載），不重複立項。
- **WP2→ALR P2-4 首位消費者**（AI-E O4）：ALR P2 隊列已有自己的 ADR-0049 gate 與排程（TODO §0 pointer），接線歸該軸 PM 排期，不入本盈利圖搶位。

## 5. 派發設計（PM 交接；執行與時序決策權在 PM）

**並行波次（檔案互不重疊）**：
- **W0（立即，全 $0 離線/研究 lane）**：E1-a `outcome_review.py` dedup+雙軌成本（#1）∥ QC-a 預註冊 #1/#2/#3 判準文檔 ∥ QC/MIT-b 極端 funding 結算窗 event study（#7 立即腿）∥ E1-b L1 timeout 校準（#9，`ollama_client.py` 單檔）。
- **W1（W0 判準凍結後）**：E1-c fill_sim bb_reversion 重放（#2）∥ E1-d horizon backtest harness（#3，`helper_scripts/research/` 新目錄）∥ E1-e 監測包 healthcheck+checklist（#5）。
- **W2（gated）**：E1-f BBO-peg+RPI 欄位（#4，觸 order path，走 E2+E4 全鏈）∥ BB TradFi BBO 採集 cron（#6）∥ E1-g unlock 日曆採集器（#8）。
- **Operator 決策批次（PM 一次打包提報）**：#7 capture 授權（5 次）、#5 soak isolation 顯式計價、#11 E2E-1 one-shot、（IBKR G4 既有排程）。

**E2 重點審查 3 點**：
1. **#1 dedup 完整性**：effective-n 必須進 eligibility 全路徑（嚴禁殘留 raw `outcome_count` 分支）；重跑判準與預註冊一致；false-negative 榜 vs realized 矛盾檢查附卷。
2. **#4 訂單路徑安全**：新欄走唯一寫入口、不觸 5-gate/lease 語意、live 函數 0 改（demo 先行）、Bybit retCode≠0 fail-closed 不重試；unsupported param 降級=不帶欄位發單（原行為）。
3. **#2/#3 leak 紀律**：禁 optimistic fill、全特徵 shift(1)、成本 taker 上界、bull 窗 regime 分層標註逐字驗。

**副作用清單**：#1/#2/#3/#7/#8 全研究 lane（0 production import；#1 的消費者=TODO READY 鏈與 review 榜，重排是預期效果非副作用）。#4 觸 `order_manager.rs` 訂單 body+fills schema（RPI 觀測欄需 V### migration，Guard B+Linux double-apply gate）；mock 該路徑的測試需同步。#9 觸 `ollama_client.py` timeout 常量（L1 調用方全鏈已 fail-back L0，改 timeout 無新失敗模式，但需驗 8s→30s 不阻塞 tick 路徑=異步邊界檢查）。#5 healthcheck 純 additive。

**降級/rollback 路徑**：全部 additive——#1 revert 單檔 patch（研究 lane，runtime 0 影響）；#2/#3/#7/#8 `rm -rf` 研究目錄+撤 cron 行；#4 config flag 默認 off、rollback=撤欄位發單邏輯（migration 留欄不回滾，空欄無害）；#9 revert timeout 常量；#5 撤 healthcheck 註冊行。無任何 move 觸 live_execution_allowed / max_retries=0 / system_mode 三硬邊界；無 GovernanceHub SM / PipelineBridge / API schema 改動。

**代碼足跡估算**：#1 ~120-180 LOC（dedup 40-80 + 重跑腳本 ~100）；#2 ~150-250 LOC glue（harness 復用）；#3 ~300-500 LOC 新研究目錄（離線 Python 研究，合 hftbacktest 先例——非 trading/risk 邏輯不增 Python 債）；#4 ~60-120 LOC Rust + 1 migration；#5 ~40 LOC + docs；#8 ~150 LOC 採集器；#9 ~15-60 LOC。合計 <1.3k LOC，無熱檔超 800 行風險；等效方案中全部取讀碼成本低者（復用 fill_sim/slippage_quantile_artifact/blocked_outcome 管線，0 新 harness 範式）。

## 6. 已判定裁決遵循聲明

本圖不重提：OHLCV+TA 線性方向 alpha、maker-first mature-perp fill_sim 雙窗（#2 是 strategy-conditional 執行路由於明留 dormant 的 M12 能力層，非重跑判準；#7 是判準複用於從未覆蓋的母集）、funding 方向四軸、Polymarket 價格軸、carry spot 子系統（僅 #5⑤ 監測其被交易所拆牆的前提）、直接 AI/RL trader。全部 NO-GO 前提均有監測條款落地（#5），符合「牆前提=operator 槓桿」紀律。

---
PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-09--profit_opportunity_map_roi_ranked.md

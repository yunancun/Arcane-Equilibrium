# QC EXT 外部情報 — Move 3:日級 Cross-Sectional Horizon Arbitrage 外部文獻掃描 · 2026-07-10

- 性質:**外部情報掃描(read-only 研究)**,非策略審計、非本地 alpha 裁決。所有外部數字一律標「外部類比」,不等同本地證據。
- 範圍:(a) crypto XS momentum/reversal 扣費存活性;(b) 小 breadth(25-50 名)XS 組合統計功效;(c) 日級 crypto 因子近年實證與衰減;(d) beta 中性構造慣例與 turnover 控制。
- 判定:**PROCEED — 進本地 $0 驗證**(條件式,見 §8;含 2 個子方向 REJECT + 翻案條件)。
- 黑名單檢查:無 HMM/GARCH/VPIN/獨立 Donchian 觸碰。警示一項:外部 trend/momentum 信號均為 MA/rolling 家族,本地復現**必須 shift(1) leak-free**(`feedback_indicator_lookahead_bias`)。
- 本地 FACT 皆附可重跑 SQL;外部數字附 URL。Operator 副本未落(本次 dispatch 限定唯一寫入 = 本報告檔),PM 如需請代複製。

---

## 1. Executive Summary

外部文獻的淨結論:**日級/週級 XS 動量在「液態大幣」是真實存在、經同儕審查、扣費後可存活——但正處於 post-publication 衰減窗,且在小 breadth 宇宙中被高相關性嚴重稀釋**。日級反轉(h=1)在液態大幣**不存在**(是 microcap illiquidity artifact),等於預先排除了一條看似便宜的路。對 OpenClaw 的三個硬含義:

1. **成本牆不是這條線的首要殺手**(與 1m maker-nogo 域相反):h≥14d + maker 執行 + banding 下,年化成本 drag 可壓至 2-4% 量級,而外部液態大幣 trend 因子的 break-even 成本容忍(BETC 1.25%/週)高出實際成本一個數量級。**首要約束是 IC×√breadth:26 名高相關宇宙的有效 breadth 遠小於名目值。**
2. Fundamental law 計算(§3):在 N_eff≈10(ASSUMPTION,待本地 PCA)、h=14d 下,單因子要達 net IR 1.0 需 IC≈0.10——超過單一技術因子常態(0.02-0.05)2-5 倍 → **必須走複合信號(CTREND-lite 路線)或接受 IR 0.3-0.5 的現實目標**。
3. 本地 2.1 年 1d 樣本的統計功效上限:只能以 t≥2 確認 SR≳1.4 的策略;realistic net SR 0.3-0.8 在本地窗**不可能達 p<0.05** → 裁決框架必須改為 effect-size CI + 外部先驗錨定 + 寬宇宙輔助窗(新發現:153-symbol 1h 宇宙自 2026-04-05 在庫),不能複用「p<0.05 才 PROMOTE」的舊門檻,否則 gate 拒真率 100%(參 2026-07-03 audit 負淨貢獻 gate 教訓)。

意外的正面事實:本地 1d 驗證窗(2024-06→2026-07)含一個完整 boom-bust 循環(BTC 62.7k→126k→58.6k→63.2k),**mixed-regime 非 bull-heavy**,天然滿足 regime 鐵律的樣本平衡要求(證據 §5.4)。

---

## 2. 理論基礎 — 外部文獻證據矩陣((a)+(c))

### 2.1 XS Momentum(7-30d lookback)— 核心證據鏈

| 來源 | 樣本 | 關鍵發現 | 可信度 | 對本地含義 |
|---|---|---|---|---|
| Liu-Tsyvinski-Wu, *JF* 2022([SSRN 3379131](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3379131);[簡報 PDF](https://bfi.uchicago.edu/wp-content/uploads/8_Yukun-Liu_presentation_final.pdf),數字已逐頁核) | 1,803 幣 mcap>$1M,2014-01→2019-06,週頻 | 1-4 週動量 quintile 5-1 週報酬 +2.3%~+4.5%(r3,0 最強 +4.5%***);**大幣更強**:size×mom 雙排序,大幣 5-1 = +4.2%/週(t=2.83),小幣 −1.1% 不顯著;3 因子 CMKT/CSMB/CMOM 吸收全部 10 個顯著異常;top-20 幣 long-only(fee 10bps+spread 50bps 靜態調整)保留原始報酬 85-98% | 高(JF 正刊)但**樣本 bull-heavy 2014-2019、CMC 聚合價、止於 2019** | 外部類比:動量存在且集中於我們正好持有的液態層;數字本身不可外推 |
| Fieberg-Liedtke-Poddig-Walker-Zaremba「CTREND」*JFQA* 2024([Cambridge OA PDF](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178),全文已抽取核數) | 3,000+ 幣,2015-04→2022-05,週頻 | 多 horizon MA 價量複合信號;H-L gross +3.87%/週(t=5.19);**turnover 68%/週**;扣 30/40bps 後 net +2.90%/週(t=3.89);**BETC(淨值歸零成本)= 1.41%/週**;top-100 幣:gross 3.40%,net 2.45%,BETC 1.25%;**top-10% 大幣仍 +2.51%/週,α>2% @1% 顯著**;bear/bull/高低波動子期皆穩 | 高(JFQA 正刊+扣費+大幣子樣本)但**樣本止 2022-05,無 FTX 後 OOS**;CMC 型日收價 | 這是「複合 trend 信號在液態層扣費存活」的最強外部證據;也是 IC 融合路線(§3)的模板 |
| Han-Kang-Ryu, *SSRN* 4675565, 2023([link](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565)) | 78 幣,realistic assumptions(交易成本+下市+組合清算) | **TS momentum 證據強,XS momentum 證據弱**;許多名目顯著的 XS 組合在 realistic 假設下利潤不顯著 | 中-高(工作論文;假設最貼近實盤) | 對 XS 的直接減分項;暗示同樣信號改 TS/overlay 形式可能更穩 |
| 「Cryptocurrency momentum has (not) its moments」*FMPM* 2025([Springer](https://link.springer.com/article/10.1007/s11408-025-00474-9)) | 2016-01→2023-12,週頻,大幣 | **post-2020-08 子期 winner→loser 持有期報酬單調性斷裂**;動量崩潰嚴重(單週離散事件 −255.28%,annualized);vol-managed momentum 可緩解;動量=大幣現象 | 中-高(正刊) | post-publication 衰減的直接證據 + crash 風險量級 + 緩解手段(§6) |
| Fieberg-Liedtke-Zaremba「Cryptocurrency anomalies and economic constraints」*IRFA* 2024([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1057521924001509)) | 3,900 幣,2014-2022,34 異常複製 | size/volume 異常源自 micro-cap;**動量在大幣存活但 (i) 交易成本重 (ii) α 大部分來自 short 側 (iii) 集中於 bull 市 (iv) 隨時間衰減**;提出可交易性協議:long 側+成本+剔除難交易幣+近年表現 | 高(正刊,34 異常系統性複製) | 四條警告全部命中本地鐵律(down-beta 偽裝/bull-heavy 標註);perp 宇宙 short 可交易是我們對 (ii) 的結構性優勢 |
| 8-major 比較研究 2026([ResearchGate](https://www.researchgate.net/publication/406476873_Momentum_Trading_in_Cryptocurrencies_A_Comparative_Study_of_Time-Series_and_Cross-Sectional_Strategies)) | 8 大幣 | **XS momentum maxDD 55%、年化報酬低於 TS momentum(31.96%/yr),歸因於高相關性** | 中(非正刊) | 與我們最相近的 breadth 情境:高相關小宇宙中 XS 被稀釋,正是 §3 的實證顯影 |

### 2.2 短期反轉(1-3d)— 負面證據明確

| 來源 | 發現 | 對本地含義 |
|---|---|---|
| Zaremba-Bilgin et al.「Up or down?」*IRFA* 2021([ScienceDirect](https://www.sciencedirect.com/science/article/pii/S1057521921002349)) | >3,600 幣:日級反轉顯著,**但源自小幣 illiquidity;最大最液態的幣呈日級動量而非反轉** | **我們的 26 名液態宇宙做 h=1 日級反轉 = 外部證據直接反對**;h=1 的 365 RT/yr 成本牆(§4)再補一刀 → REJECT 子方向 |
| 「Cryptocurrency return reversals」*Applied Econ Letters* 2021([tandfonline](https://www.tandfonline.com/doi/abs/10.1080/13504851.2020.1784831)) | 200 幣 2015-2019 日/週/月反轉顯著,對 size/turnover/illiquidity 控制穩健 | 樣本以小幣為主,與上行結論一致(反轉住在 illiquid 層) |

### 2.3 低波動 / Idio-vol 因子 — 方向近年才翻正,證據尚嫩

| 來源 | 發現 |
|---|---|
| 「Cryptocurrencies and the low volatility anomaly」*FRL* 2021([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S154461232030667X)) | 1,000 幣 2013-2019:**無顯著低波動溢價**(與股/債/商品相反) |
| 「Revisiting the low-volatility anomaly」*FRL* 2026([ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1544612326003818)) | post-2017 出現顯著**負**波動溢價(高波動幣未來報酬系統性更低),隨市場成熟化增強 |
| 「Microstructure noise and idiosyncratic volatility anomalies」*Ann. Oper. Res.* 2022([Springer](https://link.springer.com/article/10.1007/s10479-022-04568-9)) | idio diffusive risk 對沖組合 −1.11%/週(低 idio 異常存在) |

→ 列為第二優先候選:方向在近年樣本才成立、與 momentum 相關性低(LTW PCA 中 RETVOL/IDIOVOL 載荷在不同主成分),適合做融合腿而非單獨主信號。

### 2.4 量價(volume/Amihud)因子

LTW:PRCVOL/STDPRCVOL 5-1 顯著(−2.3~−2.4%/週)但**全數被 size 因子(CSMB)吸收**;Fieberg 2024:volume 異常源自 micro-cap。**本地 26 名液態層內量價 dispersion 遠小於全宇宙 → 效力存疑(LOW prior),只值得當融合腿測試,不當主信號。**

### 2.5 Post-publication decay 定量錨

- McLean-Pontiff *JF* 2016:97 個 equity 特徵發表後衰減 ~58%(外部類比,equity)。
- [arXiv 2512.11913](https://arxiv.org/pdf/2512.11913)(2025):72 因子,發表年份解釋 ~30% 的 Sharpe 衰減方差;crowding 對強信號侵蝕更快。
- Crypto momentum 主文獻發表於 2019-2024,FMPM 2025 已實測 post-2020 斷裂 → **對外部 gross 數字的保守折減:×0.3~0.5 再進本地成本模型**(ASSUMPTION,方向保守)。

---

## 3. 數學模型 — 小 breadth 的 Fundamental Law((b))

### 3.1 公式與有效 breadth

Grinold 基本定律 + Clarke-de Silva-Thorley (2002) transfer coefficient + Ding-Martin (2017, *JEF*) 相關性修正([SSRN 2730434](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2730434)):

```
IR = TC × IC × √BR_eff
BR_eff ≈ N_eff × (365 / h)      (非重疊持有期;h = holding days)
N_eff = 殘差空間有效資產數 ≪ 名目 N(高相關宇宙)
```

條件聲明:此式在「各 bet 殘差近似獨立、IC 平穩」假設下成立;crypto 宇宙 PC1(BTC beta)佔 50-70% 方差(portfolio-construction skill 的 heuristic,**未經本地 PCA 驗證 → ASSUMPTION**),β 殘差化後 N_eff ≈ 8-12(26 名宇宙)。名目 BR = 26×365/h 是 3-5 倍高估。

### 3.2 IC 需求表(TC = 0.6,含 β-hedge/banding/cap 約束的典型轉移損耗)

| h(持有天) | BR_eff(N_eff=10) | IC 需求 @ net IR=1.0 | IC 需求 @ net IR=0.5 |
|---|---|---|---|
| 7 | 521 | 0.073 | 0.037 |
| 14 | 261 | 0.103 | 0.052 |
| 30 | 122 | 0.151 | 0.075 |

N_eff 敏感度(h=14, IR=1.0):N_eff=6 → IC 0.133;N_eff=15 → 0.084。

**判讀**:單一技術因子常態 IC ≈ 0.02-0.05(equity 慣例錨;crypto 週頻 IC 本地未測)。→ 26 名 breadth 下:
- h=30d 單因子達 IR 1.0 需 IC 0.15 = 不現實;
- h=7-14d + **複合信號**(CTREND 路線:多 horizon MA×volume 融合把 IC 從 0.03 拉到 0.06-0.08)是唯一能算得過來的組合;
- 或者調低目標:net IR 0.3-0.5 在單因子 + h=7-14d 下可達,但需 §3.3 的功效框架才能被本地驗證接受。
- 融合紀律:信號間 ρ>0.7 視為單信號(`quant-strategy-design`);LTW PCA 顯示 mom 家族(r1-r4)彼此高載荷同主成分 → 多 lookback 動量互相不是分散,**真分散來自 mom × 低波 × 量價的跨族融合**。

### 3.3 統計功效 — 本地樣本的硬上限

`t ≈ SR_ann × √T_years`(daily 序列,iid 近似;fat-tail 下實際更差):

| 本地窗 | T | t=2 可確認的最小 SR |
|---|---|---|
| 26-sym 1d(2024-06-02→2026-07-09) | 2.1 yr | **≈ 1.38** |
| 153-sym 1h 宇宙(2026-04-05→今) | 0.26 yr | ≈ 3.9(時序向);但 XS 檢定功效由 breadth×天數共同決定,寬 breadth 部分補償 |

**含義(對 gate 設計,雙向體檢)**:若本地驗證沿用「p<0.05 才 PROMOTE」,對 realistic net SR 0.3-0.8 的 XS 策略拒真率≈100%,gate 淨貢獻必為負(重演 2026-07-03 standing envelope 教訓)。正確協議 = 效應量 CI + 外部先驗 + day-cluster SE + walk-forward 穩定性 + 寬宇宙(153-sym)交叉驗證,三態判定(PROMOTE/VETO/INSUFFICIENT)並預期大概率落 INSUFFICIENT→累積更多樣本,而非二元裁決。

---

## 4. 成本分析(對接本地 priors;本地數字為 dispatch 提供之 prior,未重打)

### 4.1 年化成本 drag(dollar-neutral 雙腿,以單腿 notional 計的 H-L spread 為對照基準)

每次換手 = 平舊+開新 = 1 個 RT/腿。本地 prior:taker RT ≈ 21bps(19-23 中值);maker RT ≈ 8.7bps(bb_rev 型 2×2bps fee + ~4.7bps adverse selection;**strategy-conditional**,flash_dip 型 AS −12.68bps 則 maker RT ≈ 29bps 反而更貴)。

| h | 週換手假設 | taker drag/yr(雙腿) | maker drag/yr(雙腿,AS=bb_rev 型) |
|---|---|---|---|
| 7d | TO=68%/週(CTREND 實測) | ≈ 14.9% | ≈ 6.2% |
| 14d | TO=34%/週 | ≈ 7.4% | ≈ 3.1% |
| 30d | TO=16%/週 | ≈ 3.5% | ≈ 1.4% |
| +banding(−40% TO,§7 慣例) | | ×0.6 | ×0.6:h=14d → **≈1.9%/yr** |

### 4.2 與外部 BETC 對照 — 成本牆在此域不是首要殺手

CTREND top-100 BETC = 1.25%/週 = 本地 taker 單邊 10.5bps 的 **12 倍**。即使把外部 gross 按 §2.5 折 ×0.3,液態層複合 trend 的隱含淨空間仍蓋過 §4.1 的 drag。**這與 1m maker-nogo 域(break-even 需 maker ≤0.4bps)形成鮮明反差:把 horizon 從分鐘拉到 7-30 天,成本從「結構性鎖死」降級為「可管理摩擦」。** 真正的瓶頸移到 §3 的 IC×breadth。

### 4.3 Funding — 首階中性,但兩個警告

dollar-neutral perp 雙腿:long 腿付 F、short 腿收 F,同 F 下**對消**;只有**腿間 funding 差**入成本。本地 prior:25 名宇宙 funding 現貼 IR floor(+0.01%/8h,max APR 10.95%)→ 腿間差 ≈ 0。警告:(i) **信號-funding 相關性**:momentum long 腿天然偏向高 premium 幣,bull regime 下 long 腿 funding 成本重現(需在回測中逐倉記 funding);(ii) funding regime 轉換不可假設常態(per-symbol `upperFundingRate` SSOT 規則)。

### 4.4 執行面

- maker 執行的 AS 是 strategy-conditional(本地 07-09 發現):日級 XS 的進出場**無 intraday urgency**(信號半衰期 7-30d ≫ 排隊時間)→ 屬於 AS 最溫和的一類(類 bb_rev −2.37bps 而非 flash_dip −12.68bps)——此為推論(MEDIUM confidence),需本地 maker markout 按「無 urgency 限價單」子樣本驗證。
- 26 名液態 majors 的 1d ADV 對本地 book size 無 impact 顧慮(§7)。

---

## 5. 回測驗證要求(Move 3 本地 $0 驗證的預註冊要點;執行=MIT/E4,QC 出帶)

1. **宇宙與數據(FACT,已核)**:`market.klines` timeframe='1d':19,776 行 / 26 symbols / 2024-06-02→2026-07-09。重跑:`SELECT timeframe,count(*),count(DISTINCT symbol),min(ts)::date,max(ts)::date FROM market.klines GROUP BY timeframe;` 另有 **153-sym 1h/4h 宇宙(2026-04-05 起,~96d)** 可作寬 breadth 輔助窗(同 SQL 可見 1h=271,534 行/153 symbols)。
2. **Survivorship 標註(必做)**:26 名單 = ADA,APT,ARB,ATOM,AVAX,BCH,BNB,BTC,DOGE,DOT,ETC,ETH,FIL,ICP,INJ,LINK,LTC,NEAR,OP,POL,SOL,SUI,TON,TRX,UNI,XRP(重跑:`SELECT DISTINCT symbol FROM market.klines WHERE timeframe='1d' ORDER BY 1;`)。此名單按 2026-06 backfill 時 roster 選定 = end-of-sample selection:掉出液態層的幣缺席 short 腿 → **對 momentum 偏保守(短腿候選被刪),對 reversal 偏樂觀** — 結果解讀必須帶此方向標註。
3. **信號族預註冊**:登記全部 K(lookback×h×構造變體),BH-FDR q=0.10 去重後 family(沿 2026-07-10 counterfactual prereg 的凍結三件套:輸入 sha256+規則+計數斷言)。
4. **中性化**:雙 demean(per-day XS demean + 對 BTC β 殘差化;β 用 60-90d rolling + shrinkage,§6.2)——06-03 demeaned-β 鐵則的 XS 版;報告需並列 raw vs demeaned 結果以顯影 down-beta 偽裝。
5. **Leak-free**:全部 MA/rolling 特徵 shift(1);target 窗與 feature 窗零重疊;TimeSeriesSplit + purge/embargo(細節正本 `time-series-cv-protocol`)。
6. **檢定**:day-cluster SE(同日 XS 觀察非獨立,G=交易日數);PSR/DSR(K 登記);walk-forward rolling 90/30;power 聲明先行(§3.3),預設接受 INSUFFICIENT 為合法結局。
7. **成本雙軌**:E[cost](taker 21bps RT / maker 8.7bps RT 雙 scenario)入淨值;tail(p10 slip −37.79bps prior)入 CVaR 預算不入均值(07-09 教訓)。逐倉記 funding。
8. **Regime 標籤(FACT,已核)**:1d 窗 BTC 季度 low/high/close = 62.7k(2024Q2 末)→ 峰 126.2k(2025Q4)→ 谷 57.8k(2026Q3)→ 63.2k(今),**完整 boom-bust,mixed-regime 非 bull-heavy**。重跑:`SELECT date_trunc('quarter',ts)::date, min(low), max(high) FROM market.klines WHERE timeframe='1d' AND symbol='BTCUSDT' GROUP BY 1 ORDER BY 1;` 子期(bull 2024Q4-2025Q3 / bear 2025Q4-2026Q2)分層報告強制。

---

## 6. 風險分析

1. **Momentum crash**(HIGH):FMPM 2025 實測單週 −255%(年化尺度)離散事件;本地 2025-10-11 cascade(memory:11 個極端 funding 事件中 10 個同瞬間)就是同構場景,且落在本地驗證窗內(好事:crash 行為可直接觀察)。緩解:vol-managed sizing(外部實證有效)+ 既有 P0/P1 風控;**不得**因 crash 修剪樣本。
2. **β 中性殘留**(MEDIUM):Kristoufek *Financial Innovation* 2025([Springer](https://link.springer.com/article/10.1186/s40854-025-00777-w)):raw OLS β 對未來 β 預測差,β-hedge 僅對 ~17% 資產降方差;winsorization+Bayesian shrinkage 改善。→ book-level hedge + shrunk β,並在回測中報告殘留 β 的時序分佈而非點估計。
3. **Funding regime 轉換**(MEDIUM):§4.3 (i);bull premium 回歸時 long 腿 drag 重現,需入回測而非事後補。
4. **小 breadth 集中**(MEDIUM):26 名宇宙 top/bottom quintile 各僅 5 幣;單幣 idiosyncratic 事件(delist/hack/unlock)占腿 20%。緩解:等權+單幣 cap,或 tercile 化(犧牲信號強度換分散)。
5. **Decay/crowding**(HIGH,結構性):§2.5;主文獻已發表 2-7 年,LTW 級數字必然不再;本地驗證的先驗均值應設在外部 gross ×0.3-0.5 再扣本地成本。
6. **數據代表性**(LOW-MEDIUM):外部研究全部基於 CMC/CoinGecko 型聚合現貨日收價;本地執行在 Bybit perp——basis/結算窗差異使外部「日收盤 rebalance」報酬與 perp 可執行報酬有位移,本地復現自動消除此 gap(用自家 kline),但對照外部數字時記住此位移存在。

---

## 7. 容量估算

- 26 名液態 majors 的 Bybit perp 名義 ADV 為 $10⁸-10⁹ 量級/幣(外部常識,未逐幣核 → ASSUMPTION);XS book gross $50k-$1M 下 square-root impact 可忽略(<1bps)。**容量在本地資本規模完全不 binding。**
- Fee-tier 副效益:h=14d、gross $100k 的 book 月增 ~$430k 成交額(30d notional prior $690k → 合計仍僅 VIP1 門檻的 ~11%);**XS 上線不會靠自身把 fee tier 推上去,成本模型按 VIP0 保守計。**
- Turnover 控制慣例((d) 答案之二,外部類比):
  - **Rank banding**(Novy-Marx-Velikov *RFS* 2016 慣例:進場 top-k、跌出 k+buffer 才出)→ turnover 約砍半、gross alpha 損失小,多個 equity 異常由淨負翻淨正;
  - **Overlapping tranches**(Jegadeesh-Titman 1/k 錯期子組合)→ 平滑 turnover + 消 timing luck;
  - **信號 EMA 平滑** 與 **|Δw| 交易閾值**;
  - 資產配置域的 tolerance band 研究([AlphaArchitect](https://alphaarchitect.com/destabilizing-rebalancing/))量級參考:band 化可把交易次數壓一個數量級。

---

## 8. 建議(PROCEED / REVISE / REJECT)

**總判定:PROCEED — 進本地 $0 驗證(Move 3 下一步),按以下優先序與條件。**

### 8.1 優先序
1. **首選:液態層 7-14d 複合 trend/momentum(CTREND-lite)**——3-5 個 MA horizon × volume 確認的融合信號(跨族融合,信號間 ρ<0.7),XS demean + β 殘差化,h=14d 起步,maker 執行 + rank banding。Alpha 歸類:#1 行為偏差(herding/underreaction)+ #7 跨資產溢出;外部證據鏈 §2.1。
2. **次選:低波動/idio-vol 腿**(§2.3)——僅作融合腿;單獨上不批。
3. **觀察項:量價腿**(§2.4)——液態層內 dispersion 存疑,測了不虧但先驗低。

### 8.2 REJECT 子方向(附翻案條件)
- **h=1 日級 XS 反轉於液態 majors**:外部證據直接反對(反轉=illiquidity artifact,液態層呈日級動量;§2.2)+ 365 RT/yr 成本牆。**翻案條件**:本地 153-sym 寬宇宙中位液態層以下子樣本、扣 21bps RT 後 day-cluster t>2 的反轉 spread,且 效應在 2026 子期仍在。
- **Long-only "liquid winners" 當中性 alpha**(Begušić-Kostanjčar 型,[arXiv 1904.00890](https://arxiv.org/abs/1904.00890):液態層 UMD +0.26%/day、liquid winners IR 1.59@2015-2019——已逐頁核,但其 long-only 報酬主體是 β):此構造= regime-bet/learning-only,不得作 promotion 證據。**翻案條件**:demeaned-β 殘差後 alpha 仍顯著。

### 8.3 給 PM 的裁決條件(本地驗證通過門檻)
- 預註冊(§5.3)先於任何 outcome 統計;
- demeaned + 扣費(taker scenario)後 mixed-regime 全窗 effect-size CI 下界 > 0,或兩個獨立窗(26×2.1yr 與 153×96d)同號且合併 BH-FDR 過;
- 明示接受:2.1yr 窗大概率產出 INSUFFICIENT → 續累積,不武斷 VETO(§3.3 拒真率論證)。

### 8.4 Findings 一覽(全量,含 LOW/INFO)

| # | Finding | Severity | Confidence |
|---|---|---|---|
| F1 | 液態大幣 XS momentum/trend 扣費存活有頂級正刊證據(CTREND),但止於 2022-05,post-2020 衰減有獨立實證 | INFO(機會)| HIGH(文獻)/ 本地未驗 |
| F2 | 日級反轉在液態層不存在(illiquidity artifact)→ h=1 反轉子方向 DOA | MEDIUM(避坑)| HIGH |
| F3 | 26 名宇宙 N_eff≈8-12(ASSUMPTION)→ 單因子 IC 需求 2-5× 常態;必須複合或降 IR 目標 | HIGH(設計約束)| MEDIUM(N_eff 待本地 PCA)|
| F4 | 本地 2.1yr 窗 t=2 僅能確認 SR≳1.38 → 沿用 p<0.05 gate 拒真率≈100%,gate 淨貢獻必負 | HIGH(gate 雙向體檢)| HIGH(算術)|
| F5 | h≥14d + maker + banding 下成本 drag ≈2-4%/yr,成本牆非首要殺手(與 1m 域相反)| INFO(結構)| MEDIUM-HIGH |
| F6 | dollar-neutral perp 雙腿 funding 首階對消;殘留=腿間差+信號-funding 相關 | INFO | HIGH(機制)/ 相關性未測 |
| F7 | 1d 驗證窗 mixed-regime(完整 boom-bust),非 bull-heavy | INFO(正面)| HIGH(FACT)|
| F8 | 26-sym 1d 名單有 end-of-sample survivorship(方向:momentum 保守/reversal 樂觀)| MEDIUM | HIGH |
| F9 | 153-sym 1h 宇宙(96d)在庫,可作寬 breadth 輔助驗證窗 | INFO(資源)| HIGH(FACT)|
| F10 | 假陽性候選:外部 gross 數字(LTW 4.2%/週級)若直接入先驗會系統性高估——判斷依據=CMC bull 樣本+decay 實證;建議 ×0.3-0.5 折減後使用 | MEDIUM | MEDIUM |

### 8.5 與既有裁決的相容性
- 不觸 maker-nogo(1m 做市域)結論——本線 horizon 完全不同,且 §4.2 說明了為何結論相反;
- 不觸 Rank7/四軸 NO-GO(那些死於「線性 IC×OHLCV×taker 成本牆×分鐘級」測試;本線改變的正是 horizon 與構造,符合 06-14 範式陷阱 mandate 的「換 lens 原生數學」要求);
- funding cap 規則、demeaned-β 鐵則、engine_mode 隔離全部內建於 §5。

---

## 附:主要來源
- arXiv 1904.00890 Begušić-Kostanjčar(全文已核):https://arxiv.org/abs/1904.00890
- Liu-Tsyvinski-Wu JF 2022:https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3379131 ;簡報(數字來源):https://bfi.uchicago.edu/wp-content/uploads/8_Yukun-Liu_presentation_final.pdf
- CTREND JFQA 2024(全文已核):https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178
- Han-Kang-Ryu 2023:https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565
- Zaremba et al. IRFA 2021:https://www.sciencedirect.com/science/article/pii/S1057521921002349
- Fieberg et al. IRFA 2024:https://www.sciencedirect.com/science/article/abs/pii/S1057521924001509
- FMPM 2025:https://link.springer.com/article/10.1007/s11408-025-00474-9
- Fieberg et al. QF 2023 factor momentum:https://www.tandfonline.com/doi/full/10.1080/14697688.2023.2269999
- 低波動:FRL 2021 https://www.sciencedirect.com/science/article/abs/pii/S154461232030667X ;FRL 2026 https://www.sciencedirect.com/science/article/abs/pii/S1544612326003818 ;AOR 2022 https://link.springer.com/article/10.1007/s10479-022-04568-9
- Ding-Martin JEF 2017:https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2730434
- Kristoufek FI 2025:https://link.springer.com/article/10.1186/s40854-025-00777-w
- Alpha decay:arXiv 2512.11913 https://arxiv.org/pdf/2512.11913
- 8-major 2026 比較:https://www.researchgate.net/publication/406476873
- Banding/turnover:https://alphaarchitect.com/destabilizing-rebalancing/

*QC · 2026-07-10 · EXT 外部情報掃描(Move 3)· read-only*

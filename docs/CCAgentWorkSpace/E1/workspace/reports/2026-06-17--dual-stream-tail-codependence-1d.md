# 雙流尾部共依存（純 1d kline，真崩盤樣本）— 決定性測試數字報告

**日期**：2026-06-17 | **執行**：E1（research analysis）| **性質**：$0 OFFLINE 唯讀實證
**承接**：`2026-06-17--beta-decomp-tail-dependence.md` 的 axis (d) 被 44 日 demo-fills 窗
（窗內零真崩盤、最差 −3.07%）困住，無法決定性。**本測修正根因**：兩流**完全不用 demo fills**，
皆由 `market.klines` 1d 兩年歷史純構造，故 tail co-dependence 第一次有**真崩盤樣本**（17 個
BTC<−5% 日，含 2024-08-05 carry unwind 與 2026-02-05 −15% 崩盤）。
**目標**：判定 managed-beta 流與 cross-sectional market-neutral 流在壓力下是否真正正交
（Sharpe-additive），抑或同步崩（down-beta trap 換名）。
**最終 verdict 不由本報告下**——交 QC 在 MIT 審 leak-free 完整性後裁。

**Runtime**：Linux trade-core，PG `trading_ai`（唯讀 session），numpy 2.4.4 / scipy 1.17.1 /
Python 3.12.3。
**腳本**（新增唯讀研究，已登 SCRIPT_INDEX）：
`helper_scripts/research/dual_stream_tail_codependence/analysis.py`
**ephemeral artifact**（Linux，非永久）：`/tmp/openclaw/dual_stream/analysis.json`

---

## STEP 0 — 資料品質 / PIT 檢查（誠實，未造假）

### 1d market.klines 覆蓋（2024-06 → 2026-06）
- **26 symbol**：ADA / APT / ARB / ATOM / AVAX / BCH / BNB / BTC / DOGE / DOT / ETC / ETH /
  FIL / ICP / INJ / LINK / LTC / NEAR / OP / POL / SOL / SUI / TON / TRX / UNI / XRP（皆 USDT perp）。
- **每 symbol 730 根**（POLUSDT 例外 635 根，2024-09-05 上市較晚），共 18,885 行。
- **跨度**：2024-06-02 → 2026-06-01（部分 symbol 因聚合偏移為 2024-06-10 → 2026-06-09）；
  報酬序列對齊後 **737 個交易日，2024-06-03 → 2026-06-09**。
- **品質**：**0 gap / 0 dupe(symbol,ts) / 0 zero-or-NaN OHLC bar**。乾淨主 kline 表。
- **這是乾淨主 kline 表**（`market.klines` timeframe='1d'），**不是** QC 標記 PIT-未驗的
  `research.alpha_*` 側庫。**PIT 完整性最終裁定屬 MIT**（本報告自證 shift(1) 紀律，非取代 MIT 審）。

### BTC daily < −5% 日（close-to-close，全窗）
**17 個崩盤日**（遠富於先前 44 日 demo 窗的 0 個）：

| date | BTC ret | | date | BTC ret |
|---|---|---|---|---|
| 2024-07-04 | −5.23% | | 2025-03-03 | **−8.59%** |
| 2024-08-02 | −5.94% | | 2025-03-09 | −6.38% |
| **2024-08-05** | **−7.13%** | | 2025-04-06 | −6.13% |
| 2024-08-27 | −5.49% | | 2025-10-10 | −7.29% |
| 2024-11-25 | −5.12% | | 2025-11-14 | −5.11% |
| 2024-12-18 | −5.60% | | 2025-11-20 | −5.38% |
| 2025-01-07 | −5.16% | | 2026-01-29 | −5.22% |
| 2025-02-26 | −5.03% | | 2026-01-31 | −6.55% |
| | | | **2026-02-05** | **−14.03%** |

- **2024-08-05 確認存在**（close-to-close −7.13%；intraday open→close −7.13%，ETHUSDT −10.01%）。
  註：prompt 提的「−15-20%」是 yen-carry 多日/intraday 全幅，1d close-to-close 捕到 −7.13%。
- **BTC 最差 8 單日**：2026-02-05 (−14.03%) / 2025-03-03 (−8.59%) / 2025-10-10 (−7.29%) /
  **2024-08-05 (−7.13%)** / 2026-01-31 (−6.55%) / 2025-03-09 (−6.38%) / 2025-04-06 (−6.13%) /
  2024-08-02 (−5.94%)。

> **資料品質 verdict：乾淨。** 26 sym × 730 日無 gap/dupe/zero，主 kline 表非側庫，含 17 個真
> 崩盤日。這是先前 axis (d) 缺的東西——本測有真 tail power。

---

## STEP 1 — 兩流構造（leak-free，2024-06 → 2026-06）

### stream_F（managed-beta）= BTCUSDT 1d vol-target TSMOM
- **訊號**：`sign(sum(過去 30 日 BTC log 報酬, 截至 t-1))`（TSMOM，shift(1)）。
- **倉位**：`clamp(0.40 / 已實現年化vol(過去 30 日, 截至 t-1), 0, 3×)`（inverse-realized-vol，shift(1)）。
- **PnL**：`position_t × btc_ret_t`，net `1.3bp/side × |Δposition|` turnover haircut。
- **禁 current-bar rolling max/min**（repo `trend.rs::donchian` 有該 bug，**不重用**）；只用
  trailing sum / std 且嚴格 shift(1)（t 期倉位只用到 t-1 為止的窗），無當期 bar 進訊號。
- 暖機：前 30 日（窗不足）= 0 倉。

### stream_eps（cross-sectional market-neutral）= 橫截面 BTC-殘差 z-score mean-reversion
1. **per-symbol rolling beta vs BTC**：`cov(sym, btc)/var(btc)`，窗 [t-60, t-1]（shift(1)）。
2. **殘差**：`resid_t = ret_t − beta_{t-1}·btc_ret_t`（扣已知 beta 的當期市場曝險）。
3. **訊號**：橫截面取過去 20 日殘差和（截至 t-1）的 z-score；mean-reversion = 做空殘差贏家、
   做多輸家。權重 **dollar-neutral**（sum=0）+ **gross-normalized**（sum|w|=1）。
4. **PnL**：`sum_j w_{j,t}·ret_{j,t}`，net `1.3bp/side` turnover haircut。
- **暖機**：前 80 日（beta 60 + zscore 20）= 0 倉 → **stream_eps 首倉 2024-08-22**（關鍵限制，見下）。

### Leak-free 雙軌（誠實旗標）
| | leak-free（shift(1)） | naive（訊號含當期 bar） |
|---|---|---|
| stream_F annualized Sharpe | **−0.177** | +3.353 |
| **divergence ratio** | — | **19.9（>30% 旗標 = TRUE）** |

> **此 >30% 背離是「預期且正確」的**：naive 動量用當期 bar 算訊號 = 用今天的報酬決定今天的倉位
> （前視作弊）→ 假 Sharpe +3.35。leak-free 誠實 Sharpe −0.18。**背離巨大正是 shift(1) 紀律
> load-bearing 的證明，不是 bug**——若背離小才該擔心（代表 leak-free 沒真正去掉前視）。
> stream_eps 全程嚴格 shift(1) beta + shift(1) 訊號，無 naive 對照需求（構造上無當期 bar 入訊號）。

---

## STEP 2 — 尾部共依存（決定性量測）

對齊兩流 co-active 窗（兩流皆非暖機、非零倉）= **657 日**。

### (a) 無條件相關
| 量 | 值 |
|---|---|
| Pearson ρ | **0.025** |
| Spearman ρ | **0.008** |

→ 構造上幾乎正交（~0）。**勿被安撫**——協議要求看 tail + 條件 ρ。

### (b) 下尾依存 λ_L = P(eps 最差 q% | F 最差 q%)
| q | λ_L | F-tail 天數 | co-exceedance | 獨立期望 |
|---|---|---|---|---|
| 5% | **0.061** | 33 | 2 | 1.65 |
| 10% | **0.106** | 66 | 7 | 6.6 |

→ **兩個 q 的 λ_L 皆 < 0.2**，且 co-exceedance（2 / 7）**幾乎等於獨立期望（1.65 / 6.6）**。
n 充足（33 / 66 tail 日，非先前 3 / 5）→ **這次有 power**。**下尾無顯著共依存**。

### (c) crash 子集條件 ρ vs 全樣本（Fisher-z 顯著性）
crash 定義：BTC 日報酬 < −5% **OR** 已實現 vol 頂十分位（**n=80 crash 日**，先前僅 5）。
| 量 | 值 |
|---|---|
| full-sample Pearson ρ | 0.025 |
| calm（非 crash）ρ | −0.005 |
| **crash-subset ρ** | **0.168** |
| **Δρ（crash − full）** | **+0.143** |
| Fisher-z diff | 1.20 |
| **p(crash ρ > full ρ)** | **0.114** |

→ crash 子集 ρ 確實升到 0.168（壓力下略更同步），但 **Fisher-z 單尾 p=0.114 > 0.05 →
不顯著**。先前 44 日窗的 Δρ=+0.525（n=5 無 power）在此 n=80 真崩盤樣本下**大幅縮小到
+0.143 且不顯著**。**先前的 down-beta trap red flag 在有 power 的資料上沒有成立**。

### (d) 2024-08-05 專項 stress（**誠實限制：stream_eps 此日仍暖機**）
| date | BTC ret | stream_F | stream_eps | 備註 |
|---|---|---|---|---|
| 2024-08-02 | −6.13% | −0.0520 | **0.0（暖機）** | |
| 2024-08-04 | −4.29% | −0.0364 | **0.0（暖機）** | |
| **2024-08-05** | **−7.39%** | **−0.0596** | **0.0（暖機）** | eps 首倉 2024-08-22 |
| 2024-08-08 | +11.25% | −0.0823 | 0.0（暖機） | F TSMOM 此時做空、反彈虧 |

> **重大誠實旗標**：2024-08-05（idx 63）落在 **stream_eps 暖機區**（首倉 2024-08-22，idx 80，
> 因 beta 60 + zscore 20 lookback 需 80 日，而資料起點 2024-06-03 距 08-05 僅 63 日）。
> **故 2024-08-05 的 eps PnL=0，co-blowup 結構性不可判**——若直接報「2024-08-05 無 co-blowup PASS」
> 會是**假陽性**（eps 根本沒倉）。**這正是必須抓的 false-pass**。
> stream_F 該日單獨虧 −5.96%（趨勢做多踩 carry unwind）。

### (d') 決定性 co-blowup：worst co-active 崩盤 2026-02-05（BTC −15.11% log）
| date | BTC ret | stream_F | stream_eps | both_neg |
|---|---|---|---|---|
| 2026-02-03 | −3.85% | +0.0346 | −0.0073 | 否 |
| 2026-02-04 | −3.48% | +0.0305 | −0.0007 | 否 |
| **2026-02-05** | **−15.11%** | **+0.1335** | **−0.0035** | **否** |
| 2026-02-06 | +11.50% | −0.0684 | −0.0019 | 是 |

→ **史上最大崩盤日（−15%），stream_F 賺 +13.4%（TSMOM 已做空，崩盤是其朋友）、stream_eps
僅 −0.35%（市場中性，幾乎無感）**。**兩流在最大壓力日不同號、不共崩**——這是 Sharpe-additive
的正面證據（managed-beta 在崩盤賺、market-neutral 在崩盤幾乎持平）。

### (d'') 全 15 個 co-active 崩盤日同號掃描（誠實統計，不只看單日）
- **15 個 co-active 崩盤日，僅 3 個兩流同號為負（frac=0.20）**：2025-01-07、2025-10-10、2026-01-29。
- 其中 **2025-10-10（BTC −7.57%）是唯一兩流同時大虧**（F −10.05% / eps −7.04%）= 真 co-blowup
  單例（TSMOM 那時做多 + market-neutral 同日殘差爆）。其餘 2 個同號日 eps 虧損輕微（−0.31% / −0.88%）。
- **多數崩盤日（12/15）stream_F 是賺的**（TSMOM 多半已轉空，崩盤=順勢）→ 兩流崩盤行為**不對齊**。

### (e) 各流獨立風險調整 edge（全窗，PSR(0) skew-kurt-aware）
| 流 | n | Sharpe | Sortino | Calmar | maxDD | ann_ret | skew | kurt | **PSR(0)** |
|---|---|---|---|---|---|---|---|---|---|
| **stream_F** | 737 | **−0.18** | −0.18 | −0.11 | −0.689 | −7.6% | +0.23 | 6.96 | **0.40** |
| **stream_eps** | 737 | **−0.81** | −0.69 | −0.31 | −0.625 | −19.1% | −1.10 | 11.67 | **0.12** |
| combined 50/50（z-scaled） | 657 | −0.41 | −0.40 | −0.28 | (見下) | — | −0.44 | 8.59 | 0.29 |

> **z-scaled apples-to-apples maxDD**：combined −20.3 vs stream_F −18.6 vs stream_eps **−48.0**。
> combined **不深於最差單流**（eps −48），只略深於較好單流（F −18.6）→ 分散在 DD 上機械生效，
> 但**兩流都在虧錢**，combined 仍 bleed。

### (f) Regime-split（leak-free PIT，shift(1) 30 日 BTC 趨勢，±2% chop band）
| regime | n | stream_F Sharpe (ann_ret) | stream_eps Sharpe (ann_ret) |
|---|---|---|---|
| **bull** | 304 | −0.55 (−23.6%) | **−1.94 (−46.5%)** |
| **down** | 251 | **+0.51 (+23.1%)** | −0.52 (−14.0%) |
| **chop** | 102 | +2.38 (+87.8%) | +1.64 (+35.4%) |

→ stream_F 在 **down regime 為正（+0.51）= managed-beta 趨勢策略在跌市做空賺**（與 stream_eps
跌市虧 −0.52 **反號**，這是它們不共崩的結構原因）。兩流唯一同時正在 **chop（n=102，小樣本，
mean-reversion 與 vol-target 都在盤整賺）**。**兩流皆無任何 regime 有穩定可投資的正 edge**（bull
皆負、down 一正一負、chop 正但 n 小）。

---

## STEP 3 — pass/fail（QC bar；**非最終 verdict**）

| QC bar | 結果 | 證據 |
|---|---|---|
| λ_L < 0.2（q=5% 與 q=10%） | **PASS** | 0.061 / 0.106，co-exceedance ≈ 獨立期望，n=33/66 有 power |
| crash-subset ρ 不顯著大於 full-sample | **PASS** | Δρ=+0.143，Fisher-z p=0.114 > 0.05（n=80 真崩盤） |
| 無 co-active 崩盤出現兩流同步崩 | **PASS（有保留）** | worst 2026-02-05 不同號；15 崩盤日僅 3 同號負（frac=0.20<0.5）；唯 2025-10-10 真共崩單例 |
| **all_pass（tail-orthogonality 部分）** | **True** | |

> **腳本 all_pass=True，但這只回答「兩流是否尾部正交」一半的問題。** 三條 tail bar 都過了——
> 在有真崩盤 power 的資料上，**兩流確實尾部正交，不是 down-beta trap 換名**（先前 44 日窗的
> trap red flag 在 n=80 下消失）。

---

## 綜合（初步，交 QC 裁；**初判 PASS 但帶決定性 caveat**）

1. **tail-orthogonality 初判 PASS**：λ_L < 0.2（有 power）、crash-subset ρ 不顯著升、worst 崩盤
   不共崩。先前 axis (d) 的 down-beta trap 警告**在真崩盤樣本下未成立**——兩流結構上反號
   （managed-beta down regime 賺空、market-neutral down regime 虧），故崩盤不同步。

2. **但「兩條非-edge 流」這個 caveat 是決定性的**（prompt 明令必須說）：**兩流獨立 Sharpe
   皆為負**（stream_F −0.18 / stream_eps −0.81，PSR(0)=0.40 / 0.12 皆 < 0.5 = 與 0 無異甚至負）。
   尾部正交對「結合兩條有正 edge 的流」才有意義；**這裡是「結合兩條 net 為負的流」**。50/50
   combined Sharpe −0.41 仍負。**「Sharpe-additive」的前提（每條各有正 Sharpe）在此構造下不成立
   → 結合兩條非-edge 是 moot**。tail 正交只保證「combined 不會比單流崩得更慘」，不保證盈利。

3. **直接回答 operator 問題**：managed-beta 流與 cross-sectional market-neutral 流**確實在壓力下
   正交（不共崩）= 不是 down-beta trap 換名**。但**這兩個具體構造（vol-target TSMOM + 殘差
   mean-reversion）各自都沒有 standalone edge**——正交性是真的、可投資性不是。要讓 Sharpe-additive
   論成立，需先各自找到有正 PSR 的流；本測用的是「最簡可辯護的 textbook 構造」，它們無 alpha
   呼應 profit-diagnosis 四軸窮盡（OHLCV×TA×beta 殘差角落無方向預測 alpha）。

4. **chop regime 兩流同時正（F +2.38 / eps +1.64）** 是唯一亮點，但 n=102 小樣本、且依賴
   regime 可預先偵測（本身是 open question）→ 不足以翻案，標明供 QC。

---

## STEP 4 — backfill 可達性評估（**僅評估，未寫任何 kline**）

經 Bybit 公開 `GET /v5/market/kline`（category=linear，interval=D，max 1000/page，唯讀無 auth）
查各 symbol perp kline inception（listing 代理）：

| 歷史崩盤 | 日期 | backfill 可達？ | 說明 |
|---|---|---|---|
| COVID 黑色星期四 | 2020-03-12 | **不可達** | **BTCUSDT perp inception = 2020-03-25**（晚崩盤 ~2 週）；無任一 perp 覆蓋 |
| 519 大跌 | 2021-05-19 | **部分可達** | BTC(2020-03-25)/ETH(2021-03-15)/XRP(2021-05-13)/ADA(2021-03-18)/LTC(2020-10-21)/LINK(2020-10-21)/BCH(2020-12-14) 覆蓋；多數 alt 上市於 2021 中後不覆蓋 |
| LUNA/UST 崩盤 | 2022-05-09 | **大致可達** | BTC/ETH/SOL(2021-10)/XRP/ADA/DOGE/BNB/AVAX/DOT/ATOM/NEAR/FIL/ETC/UNI/TRX/LTC/LINK/BCH 覆蓋；SUI/APT/POL/TON/ARB/OP/INJ 未上市 |
| FTX 崩盤 | 2022-11-08 | **大致可達** | 同 LUNA 集合 + APT(2022-10-19)/OP(2022-06-01)/INJ(2022-08-17)；SUI/POL/TON/ARB 未上市 |
| yen-carry unwind | 2024-08-05 | **已有**（DB 1d，26 sym 全覆蓋） | — |

**各 symbol perp 最早 1d（inception 代理）**（節錄）：BTC 2020-03-25（~2275 日）/ ETH 2021-03-15 /
SOL 2021-10-15 / XRP 2021-05-13 / LTC 2020-10-21 / BCH 2020-12-14 / SUI 2023-05-03（最晚之一）/
POL 2024-09-05。

**粗略 row count（backfill 至各 inception）**：
- 把現有 26 sym 從 2024-06 往前補到各自 inception：BTC ~1530 日新增、majors（ETH/SOL/XRP/...）
  各 ~700–1400 日新增；26 sym 合計 **~20,000–25,000 新 1d 行**（量級同既有歷史 backfill 工具
  單次規模，~分鐘級，非 GB 級）。
- 每 symbol 需 ~1–3 次 paginated request（1000 bar/page，BTC 2275 日 = 3 page）。

**結論（交 operator/QC 在看到本測結果後決定）**：
- **2022 LUNA + 2022 FTX 兩大真崩盤 backfill 可達**（majors 覆蓋），能把本測的真崩盤樣本從
  17 個顯著擴增，並納入**幣圈內生崩盤**（非 2024-08 的 macro-driven），對 tail-codependence
  穩健性是真增益。
- **2021-05-19 部分可達**（僅 majors）；**2020-03 COVID 不可達**（perp inception 晚 2 週）。
- **但**：鑑於本測**初判 tail 正交 PASS 但兩流皆無 standalone edge**，更深 backfill 主要驗證
  「正交性在更多崩盤是否 robust」——**正交性不是瓶頸，edge 才是**。建議 backfill **優先級降為
  「robustness 補強」而非「解鎖」**；真正該先解的是「兩流是否能各自有正 PSR」。

---

## 資料限制（明確）

- **stream_eps 80 日暖機 → 2024-08-05（任務指定）落在暖機區，co-blowup 不可判**（eps PnL=0）。
  已以 worst co-active 崩盤 2026-02-05 + 全 15 個 co-active 崩盤同號掃描替代決定性判定。
- **兩流是 textbook 最簡可辯護構造**（vol-target TSMOM + 殘差 z-score MR），非優化過的策略；
  它們無 standalone edge 不代表「managed-beta / market-neutral 範式」無 edge，只代表**這兩個
  具體實作**無 edge（呼應 profit-diagnosis：OHLCV×TA×beta 殘差角落已窮盡）。
- combined maxDD 的兩種單位：fraction-單位（stream_F −0.689 / stream_eps −0.625）不可與 z-scaled
  combined（−20.3）直接比；apples-to-apples 比較用 z-scaled（combined −20.3 / F −18.6 / eps −48.0）。
- crash 子集 n=80（含 vol 頂十分位），其中 BTC<−5% 純崩盤日 17 個（co-active 15 個）；Fisher-z
  顯著性檢定假設 ρ 抽樣分佈近似（n=80 尚可，但崩盤日自相關未完全校正 → p 值偏樂觀，標明）。
- leak-free 完整性**最終裁定屬 MIT**（本報告自證 stream_F naive 雙軌背離 19.9 = shift(1)
  load-bearing；stream_eps 全程 shift(1) beta+訊號，無當期 bar 入訊號）。
- backfill row count 是粗估（按 inception → 2024-06 的日數 × symbol），實際走 paginated walk
  會因停牌/缺檔略少；屬 QC/MIT 在決定 backfill 後的工程細節。

## Operator / QC 下一步（建議，非自行決策）

1. **交 QC 下最終 verdict**：本報告初判 **tail-orthogonality PASS**（兩流不共崩、非 down-beta
   trap 換名），但**帶決定性 caveat：兩流皆無 standalone 正 edge（PSR 0.40 / 0.12）→
   「Sharpe-additive」前提不成立，結合兩條非-edge 是 moot**。
2. **正交性已驗、edge 是瓶頸**：建議下一步不是「找 conditioning signal 結合兩流」，而是先讓
   至少一條流有可辯護的正 PSR（屬 QC alpha 搜索範疇）；正交性此時才有兌現價值。
3. **backfill 決策（看本測結果後）**：2022 LUNA/FTX 可達且能補幣圈內生崩盤的 robustness，但**降為
   robustness 補強優先級**（正交性非瓶頸）；2020 COVID 不可達（BTC perp inception 2020-03-25）。
4. **chop regime 兩流同時正（小樣本 n=102）** 是唯一值得 QC 進一步看的線索，前提是 regime 可
   leak-free 預偵測。

---

**產物**：
- 報告：本檔。
- 腳本：`helper_scripts/research/dual_stream_tail_codependence/analysis.py`（唯讀，已登 SCRIPT_INDEX）。
- ephemeral artifact（Linux，非永久）：`trade-core:/tmp/openclaw/dual_stream/analysis.json`。

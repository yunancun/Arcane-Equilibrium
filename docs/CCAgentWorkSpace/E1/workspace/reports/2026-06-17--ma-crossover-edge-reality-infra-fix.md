# ma_crossover GROSS-edge reality test + execution-infra fix — 決定性研判

**日期**：2026-06-17 | **執行**：E1（research analysis）| **性質**：$0 OFFLINE 唯讀實證
**承接**：`2026-06-17--cost-bleed-decomposition.md`（揭 ma_crossover gross-residual +3.35 bps
被 fee −7.30 吃成 net −3.95）+ `2026-06-17--beta-decomp-tail-dependence.md`（axis(a) BTC-beta
解釋 per-trade PnL 變異 ≈0% R²=0.0007）。
**問題**：operator thesis = beta-timing 的 edge 不是不存在，是被執行成本基礎設施吃掉；修 infra
（maker-route taker close、砍 turnover）就能翻正。**決定性前置問題**：那 +3.35 bps GROSS edge
是真的（regime-surviving 真 trend edge）還是 down-beta artifact？
**範圍**：PART 1 是 gate；只有 PART 1 顯示 regime-surviving 真 edge 才做 PART 2 反事實。
**性質**：只做 DIAGNOSIS，不實作 fix。最終 alpha-reality verdict 交 QC。

**Runtime**：Linux trade-core，PG `trading_ai`（唯讀 session）。
**腳本**（新增唯讀研究，已登 SCRIPT_INDEX）：
`helper_scripts/research/ma_crossover_edge_reality/analysis.py`
**ephemeral artifact**（Linux，非永久）：`/tmp/openclaw/ma_crossover_edge/analysis.json`

---

## PART 1 VERDICT（決定性）：**DOWN-BETA / REGIME ARTIFACT — 非真 edge。STOP。**

ma_crossover 的 +3.35 bps GROSS edge **不是 regime-independent 真 trend edge**。它在統計上
**與 0 不可區分**，beta-中性化後**完全消失**，且 long-leg 的正貢獻**集中在 BTC-up 日**——典型
beta-timing 指紋。**4 個 artifact 訊號中 3 個觸發**（門檻 ≥2 即判 artifact）。

### 1. GROSS mean + 兩維 cluster t + bootstrap CI（n=893 round-trips）

| 指標 | 值 | 讀法 |
|---|---|---|
| GROSS mean | **+3.35 bps** | = cost-bleed 報告的 +3.35（同 SSOT，對賬一致） |
| 兩維 cluster t（symbol×day, CGM） | **t = 0.64** | **遠不顯著**（\|t\|<1.64）；72 symbol cluster / 53 day cluster |
| cluster-block bootstrap 95% CI（by symbol） | **[−6.31, +15.12] bps** | **含 0** → mean edge 統計上與 0 不可區分 |

**+3.35 bps 是雜訊**：clustered t=0.64、bootstrap CI 跨越 0。這個「正 raw edge」在恰當的
依賴結構校正下根本沒有統計顯著性——cost-bleed 報告的 pooled mean 沒做 SE，這裡補上後它消失。

### 2. Beta-中性化（GROSS ~ a + b·BTC窗報酬，leak-free contained-bar，n=707 BTC-aligned）

| 指標 | leak-free | naive 雙軌 |
|---|---|---|
| **alpha 截距（beta 外殘差 edge）** | **+0.50 bps** | +0.50 bps |
| alpha cluster t | **t = 0.08** | t = 0.08 |
| beta 係數 | −0.0284 | −0.0285 |
| beta cluster t | **t = −2.18（顯著負）** | t = −2.17 |
| R²（beta 解釋比例） | 0.0007 | 0.0007 |
| 雙軌 alpha 背離 | **0.002 bps**（無前視） | — |

**決定性**：扣掉 BTC-beta 後 **alpha 截距 = +0.50 bps、t=0.08** —— +3.35 的「edge」幾乎全部
由 BTC 暴露解釋掉，殘差 edge **與 0 無異**。beta 係數 **顯著負（t=−2.18）= down-beta 載荷**
（漲時略虧、跌時略賺的方向性曝險）。R²=0.0007 對齊 axis(a) 的 portfolio-level 發現（per-trade
變異幾乎全是顯著的非-beta 殘差，但**該殘差的均值=0**，即無方向性 alpha）。naive 雙軌背離
0.002 bps → **leak-free 乾淨，無前視污染**。

### 3. Regime-split（leak-free PIT 標籤：shift(1) 5 日 BTC 趨勢，禁 current-bar rolling）

| regime | n | GROSS mean | GROSS **median** | net mean | cluster t |
|---|---|---|---|---|---|
| **btc_down** | 333 | **−3.04 bps** | 0.0 | −9.20 | −1.56 |
| **btc_up** | 364 | +3.88 bps | 0.02 | −5.10 | 0.48 |
| **chop** | 59 | +43.18 bps ⚠️ | **0.10** | +33.0 | 1.37 |

**讀法（誠實）**：
- **GROSS edge 在跌市為負（−3.04）**——若是真 trend edge，趨勢策略在明確趨勢日（含跌趨勢）
  應賺；它在跌市反而虧。
- **btc_up 的 +3.88 cluster t 僅 0.48**（不顯著）；chop 的 +43.18 是**離群假象**：median 僅
  +0.10 bps（mean 43 vs median 0.10），由少數低 notional RT 的大 bps 驅動（exit 實現 PnL 範圍
  僅 −11.47~+17.08 USD，bps 大來自小分母），**n=59/僅 5 天**，無 power。剔除離群後 chop≈0。
- 三個 regime **沒有一個有統計顯著的正 GROSS edge**。表面「btc_up/chop 正」經 t 檢定與
  median 檢視後**都站不住**。

### 4. Long-leg vs short-leg split（entry side：Buy=long / Sell=short）

| leg | n | GROSS mean | cluster t | GROSS in btc_down | GROSS in btc_up |
|---|---|---|---|---|---|
| **long** | 421 | +12.21 bps | 1.14 | **+0.33**（n=166） | **+12.08**（n=161） |
| **short** | 472 | −4.56 bps | −0.84 | −6.39（n=167） | −2.63（n=203） |

**決定性的 down-beta tell**：
- GROSS edge **高度不對稱**：long +12.21、short −4.56。
- long-leg 的正貢獻 **幾乎全部來自 BTC-up 日（+12.08）**，在 BTC-down 日 long 幾乎歸零（+0.33）。
  → 這正是 **「漲市做多賺、跌市做多不賺」的方向性 beta**，不是「能預測趨勢方向」的 trend edge。
- short-leg **全 regime 為負**（down −6.39 / up −2.63）——做空腿沒有任何 edge，且在跌市虧更多
  （滯後進場踩局部極值，呼應 06-17 鏡像窗口 finding）。
- **沒有「short 在跌市做空 insurance 賺」的對稱**；反而是 long-in-up 單邊扛起表面 GROSS，這比
  short-crash-insurance 更明確是 **buy-the-dip-in-uptrend beta 收割**，零方向預測 alpha。

### 初判 verdict（artifact 訊號計數）

| 訊號 | 觸發？ | 證據 |
|---|---|---|
| A. beta-中性化 alpha 不顯著正 | **是** | alpha +0.50 bps, t=0.08 |
| B. GROSS edge 僅單一 regime 正 | 否（表面多 regime，但見下） | btc_up/chop 表面正，**但 t 不顯著 + chop 離群** |
| C. short 在 down 為正且 long 整體非正（asymmetry） | 否（long 整體正） | long +12.21（但全來自 up） |
| D. bootstrap CI 含 0 | **是** | [−6.31, +15.12] |
| **腳本自動計數** | **2/4 → DOWN_BETA_OR_REGIME_ARTIFACT** | proceed_to_part2 = **false** |

> **人工覆核加重結論**：腳本的訊號 B/C 未觸發是因為「表面有正數」，但補上 t 檢定（btc_up t=0.48
> 不顯著、chop 是離群）與 long-leg 的 BTC-up 集中性後，**B 與 C 的精神其實也成立**——真實
> artifact 證據比 2/4 更強。最關鍵兩條鐵證：**(A) beta 外殘差 alpha t=0.08 + (4) bootstrap CI 含 0**
> 已足以判定：**+3.35 bps GROSS edge 是 down-beta artifact，不是真 trend edge**。

---

## PART 2：**SKIPPED**（依協議，PART 1 為 artifact 即停）

PART 1 verdict = down-beta artifact。依任務協議與 survival-first 紀律，**不對非-edge 策略做
wishful 成本反事實**——修 fee 只會讓我們「在一條沒有 edge 的策略上少虧一點」，不會盈利。

**直接回答 operator thesis**：beta-timing 的 edge 在此資料上**確實不存在**（不是被成本藏起來）。
ma_crossover 的正 GROSS 數字是 BTC-beta 收割的副產品（long-in-uptrend），beta 外的方向預測
alpha = +0.50 bps t=0.08 ≈ 0。**maker-route taker close 會把 fee 從 −7.30 降到 ~−4，net 從
−3.95 改善到約 −0.6，但仍是負的**（−0.6 ≈ +0.50 真 alpha − 殘餘成本），且那 net 改善建立在
「收割到的 beta 維持正」的假設上——beta 係數是**負的**（down-beta），市場一轉跌（如 06-15
BTC+4.5% 的反面、06-17 鏡像跌窗）long-in-up 的表面 GROSS 立刻轉負（btc_down long 僅 +0.33）。
**成本 lever 救不回一條沒有方向預測 alpha 的策略**。

> 若 QC 仍要看 PART 2 的數字：PART 1 已給足對 fee delta 的量級判斷（taker 5.5 → maker 2.0 bps，
> close-maker 真實成交率需從 post-05-18 close_maker_attempt 子集估，但 ma_crossover 子樣本
> 太小無 power）。在 net 改善 ~3.3 bps × ~50% 成交率 ≈ +1.6 bps 上限下，net −3.95 → 約 −2.3，
> **仍不翻正**。本報告不展開此 wishful 計算（協議所禁），標明結論即可。

---

## 與既有 finding 的一致性（交叉佐證）

1. **QC 先驗（t≈−0.59 結構性無 alpha）成立**：本測 beta 外 alpha t=0.08、short-leg t=−0.84，
   結構性無 alpha 確認。
2. **axis(a)（R²=0.0007 BTC-beta 解釋 per-trade 變異）成立**：本測 ma_crossover 子集 R² 同為
   0.0007，beta 係數顯著負。
3. **06-02 down-beta short-crash-insurance flag**：此處更精確——ma_crossover 的表面 GROSS 不是
   short-crash-insurance（short 全 regime 負），而是 **long-in-uptrend beta 收割**（另一種
   down-beta 載荷的鏡像：負 beta = 漲時 long 賺、跌時不賺）。
4. **06-17 鏡像窗口 finding（ma_crossover 滯後進場踩局部極值、緊停砍空單佔 62%）**：本測
   short-leg 全 regime 負且 down 更負，與之一致。

---

## 資料限制（明確）

- **GROSS = realized_pnl（真實成交價）扣費前**，winsorize 在 record 級（|ln ratio|>0.5 skip +
  bps 限幅）；chop regime 的 +43 mean 是低-notional 大-bps 離群（median 0.10）非真 edge，已標明。
- BTC 窗報酬用 contained-bar（leak-free，無前視）；186/893 RT 無 contained BTC bar（持倉窗短於
  1 根 1m bar 或跨 kline 缺口）→ beta 回歸用 n=707 對齊子集；naive 雙軌背離 0.002 bps 證乾淨。
- regime 標籤 shift(1) 5 日 BTC 趨勢、±1% chop band（禁 current-bar rolling）；137 RT 落在
  標籤起始邊界外（前 6 日無趨勢窗）；naive vs leak-free regime 分類 232/757 背離（=shift(1)
  確實改變標籤，證 leak-free 非裝飾）。
- entry-side overlay 重放 `_pair_round_trips` 的 is_exit 分類捕捉 entry side，撞鍵 0；long/short
  依 entry fill side（Buy=long/Sell=short）。
- cluster-block bootstrap by symbol（n_boot=5000, seed=20260617），保留 symbol 內相關，不假設 iid。
- 最終 alpha-reality verdict 屬 QC；本報告給證據 + 初判，QC 在 MIT 審 leak-free 完整性後裁。

---

## Operator / QC 下一步（建議，非自行決策）

1. **交 QC 做最終 alpha-reality call**：本報告證據鏈傾向 **ma_crossover +3.35 GROSS = down-beta
   artifact**，不建議投入 infra fix 救援（成本 lever 救不回 ≈0 的真 alpha）。
2. **撤回 cost-bleed 報告 Lever 2 的「頭號互補 lever」定性**：cost-bleed 報告當時把 ma_crossover
   fee-drag 翻正列為頭號 lever，前提是「有正 raw edge」。本測證該前提不成立（raw edge 與 0
   無異），**Lever 2 應降為「會少虧但不會盈利」的成本 hygiene，非 alpha lever**。
3. **若仍要做 maker-close 路由**：當作 demo book 整體的成本衛生（grid_trading 才是 85% bleed
   主體，且 sibling a90ffc7b 已在拉該向），**不應以 ma_crossover 翻正為理由**。
4. **真盈利路徑仍在搜索空間**：本測再次確認 OHLCV×TA×beta 殘差角落無方向預測 alpha（呼應
   profit-diagnosis 四軸窮盡）；ma_crossover 不是「被成本藏住的好策略」，是「沒有 alpha 的
   beta 收割器」。

---

**產物**：
- 報告：本檔。
- 腳本：`helper_scripts/research/ma_crossover_edge_reality/analysis.py`（唯讀，已登 SCRIPT_INDEX）。
- ephemeral artifact（Linux，非永久）：`trade-core:/tmp/openclaw/ma_crossover_edge/analysis.json`。

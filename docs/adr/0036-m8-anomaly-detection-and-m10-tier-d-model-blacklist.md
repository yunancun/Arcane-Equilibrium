# ADR 0036: M8 Anomaly Detection + M10 Tier D Regime — Model Blacklist + ATR-vol/Funding-state 雙 axis 替代

Date: 2026-05-21
Status: **Accepted**（v5.8 §2 M8 + M10 Tier D 算法選擇邊界合併治理 ADR；對應 PA dispatch CR-5 + PM final verdict §四 仲裁 #5）
Operator Sign-off: 2026-05-21（主會話 PM dispatch — PA 仲裁 #5「採 (a) ATR-vol regime + funding state 雙 axis 為 Y2-Y3 主路徑；Y3+ 再 evaluate PELT」）
Related: v5.8 §2 M8 Anomaly Detection (lines 279-318) / v5.8 §2 M10 Tier D Regime Discovery (line 367) / `srv/.claude/skills/math-model-audit/SKILL.md`（HMM / GARCH 黑名單 source of truth）/ `srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`（block bootstrap + OOS 驗證 SOP）/ ADR-0021 Alpha Source Architecture Upgrade / ADR-0037 (M9 A/B framework；Decision 4 反模式 (e) 引用本 ADR Decision 1 HMM/GARCH 黑名單適用 M9 variance structure 估計)

## Context

### 起源

v5.8 13-module thesis 在 §2 M8 與 §2 M10 Tier D 兩處出現會誘導引入 **HMM / Markov-switching / GARCH** 三類模型的字眼，但這三類模型在 `srv/.claude/skills/math-model-audit/SKILL.md` 已明寫黑名單（"絕不推薦 / Operator 已拒絕"）。本 ADR 為 QC + MIT 5.21 v5.8 audit 對 v5.8 §2 M8 + M10 Tier D **同一個算法選擇邊界** 的合併治理收口。

合併成單一 ADR 而非拆兩個的理由：

- M8 anomaly detection 的「vol regime shift 偵測」與 M10 Tier D「regime auto-classify 策略分配」共享同一組 regime feature（ATR-vol + funding state）
- 兩個 module 對「不該用 HMM / GARCH」的設計理由完全一致（black-list 由 math-model-audit skill 統一定義）
- 拆兩個 ADR 會導致黑名單條款重複維護（drift 風險）；合併後黑名單只在本 ADR 寫一次，兩個 module spec 反向 cite

### v5.8 §2 M8 字面提及 GARCH

v5.8 §2 M8 (line 279-318) 列「Market regime anomaly: Vol regime shift (Hurst exponent change, **GARCH break**)」。原文「GARCH break」字眼若不在 ADR 級鎖入替代算法，Sprint 1A-γ 派 IMPL 時 sub-agent 容易直接拉 Python `arch` package 或 Rust `garch-rs` 上線。

### v5.8 §2 M10 Tier D 隱伏 HMM

v5.8 §2 M10 Tier D (line 367) 列「Regime discovery (auto-classify market regime + regime-specific strategy allocation)」。「auto-classify market regime」在 crypto 量化文獻中 default 就是 Hidden Markov Model 或 Markov-switching regression；Sprint 1A-γ M10 Tier D config table 派 IMPL 時若沒有 ADR 鎖入替代算法，sub-agent 同樣會默認往 `hmmlearn` / `pomegranate` 走。

### math-model-audit skill 已明文黑名單

`srv/.claude/skills/math-model-audit/SKILL.md` §「★ 黑名單：絕不推薦」段已列：

| 方法 | 為何拒絕 | 替代方向 |
|---|---|---|
| **HMM 政體偵測**（Hidden Markov） | 過度擬合金融數據，狀態定義主觀，live 表現崩 | ATR / volatility regime 等可解釋 metric |
| **GARCH 家族** | 假設過強（normality / stationarity），crypto 已知違反 | realized vol + bootstrap |
| **VPIN** | 學術 toy，crypto VPIN 與 toxic flow 關係未驗 | order book imbalance + funding rate |

本 ADR **不重寫** skill 內容（skill 為 source of truth）；ADR 級的責任是把 skill 黑名單上升為 ADR governance object，使其在 sub-agent dispatch 階段成為強制 grep 條款，並把替代算法的具體 spec 鎖入。

### 為什麼 ADR 級鎖入比僅靠 skill 提示更強

skill 是 advisory 機制，sub-agent 可能繞過或誤讀。ADR 是 governance object，dispatch 必須 cite + grep。本 ADR 把 math-model-audit skill 黑名單 promote 為 ADR-0036 Decision 1 後，PA + MIT + E2 在 sub-agent dispatch 階段 grep `hmm|markov_switching|garch` 拒絕，是強制 gate。

### 為什麼必須在 Sprint 1A-γ DESIGN 階段 land

per PA dispatch consolidation report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §1 CR-5：M8 / M10 Tier D 進入 Sprint 1A-γ IMPL DESIGN 時，本 ADR 必須已 land 否則 sub-agent 拉錯 dependency 或寫了 50-80 hr IMPL 才發現要 rewrite。**ADR-0036 是 Sprint 1A-γ DESIGN 派發前置條件**。

### 數學理由 — 為什麼 HMM / Markov-switching / GARCH 在 crypto perp 不適用

per QC v5.8 audit + math-model-audit skill 設計理由：

1. **i.i.d. + stationarity 假設不適用於 crypto perp**：crypto perp tick / 1m / 1h kline 殘差結構強自相關（自相關係數常 > 0.3）+ 異方差（volatility clustering 是日常）；HMM / GARCH 的數學成立基礎被違反
2. **隱狀態可識別性弱**：HMM state count K 的選擇依賴 BIC / AIC penalty；crypto 樣本 N（特別是 Y1 末預期 ~25k-50k decision events）在 fat-tail 下 BIC penalty 不可靠，K 選 2 / 3 / 4 都能 fit，但 K 選錯後 state transition matrix 失去語義
3. **替換成本高 + replication crisis 警示**：Harvey-Liu-Zhu 2016 "...and the Cross-Section of Expected Returns" 警示金融學術圈 `O(300)` 篇 HMM / regime detection paper 在 OOS replication 普遍失敗；live deploy 後 regime switch 預測無 robust evidence
4. **GARCH forecast 在 crypto 表現不佳**：crypto 6h-24h vol forecast benchmark 顯示 GARCH(1,1) 比 simple realized vol rolling mean 預測精度 +1-3% 但 train 成本（MLE fit + iter）高 50-100x；不是 cost-effective alpha

本 ADR Decision 1 黑名單範圍涵蓋上述所有用途（不僅 regime detection 也包括 vol forecasting），原因見 §Alternatives Considered 第一條。

## Decision

**Proposed**：四項決策合併鎖入。

### Decision 1 — 三模型黑名單（永久 + ADR 級強制）

**核心**：HMM / Markov-switching / GARCH 任何 module 不可使用。

| 元素 | 規範 |
|---|---|
| 黑名單範圍 | **HMM (Hidden Markov Model)** 含所有變形（HSMM、HHMM、Factorial HMM 等）/ **Markov-switching regression**（Hamilton 1989 起所有變形）/ **GARCH (Generalized Autoregressive Conditional Heteroskedasticity)** 含所有變形（EGARCH、TGARCH、IGARCH、FIGARCH、Multivariate GARCH 等） |
| 適用 module | M8 anomaly / M10 Tier D regime / M4 hypothesis miner / M11 replay / M9 A/B framework / 任何 future module；**無例外** |
| Sub-agent dispatch 階段 grep | PA + MIT + E2 必 `grep -rni 'hmm\|markov_switching\|garch'` 在 dispatch 前 + sub-agent IMPL DONE 後雙 round；任一 hit = 拒絕 + push back |
| Cargo dep 黑名單 | `garch-rs` / 任何 GARCH crate / 任何 HMM crate（Rust 端 default 不該有，但留條款防漂移） |
| Python requirements 黑名單 | `arch`（GARCH 主流 package）/ `hmmlearn` / `pomegranate` HMM submodule / `statsmodels.tsa.regime_switching` |
| 例外：read-only counterfactual analysis | 純 read-only counterfactual analysis（如 backtest 對照 HMM 是否真不工作、學術復現練習）允許 read-only run，但**結果不得寫 live state / 不得進入 strategy trigger / 不得進入 promotion evidence**（per ADR-0024-lite + §二 原則 7「學習 ≠ live」）；該類 analysis 必走 M11 read-only replay surface，不創新模塊 |
| 黑名單 grep 失敗的 fail-closed 行為 | sub-agent dispatch grep 失敗 = PA + MIT + E2 PUSH BACK；不允許「先 IMPL 後審查」的 fail-open 路徑 |
| 未來新增黑名單方法 | 任何未來新增黑名單方法**先 amend math-model-audit skill** → 再 amend 本 ADR Decision 1；skill 是 source of truth，ADR 是 governance 強制 mirror |

### Decision 2 — M8 anomaly detection 算法替代

對應 v5.8 §2 M8 (line 279-318) 設計，本 ADR 鎖入替代算法。**保留 v5.8 §2 M8 既有架構**（statistical / ML / counterfactual 三層），只替換「Vol regime shift 偵測」中的 GARCH 字眼。

| Anomaly domain | v5.8 §2 M8 原文 | ADR-0036 替代算法 |
|---|---|---|
| Vol regime shift | 「Hurst exponent change, **GARCH break**」 | **Rolling realized vol percentile (RV pct)**：30d rolling window 計算 σ_realized，對比 90d distribution percentile；超出 `[10%, 90%]` 觸發 LOW / HIGH regime；Hurst exponent change 保留為輔助 |
| Correlation structure break | 「eigendecomp shift」 | **Eigendecomp drift over rolling 30d windows + pairwise correlation Δ > 2σ**；無變更（v5.8 既有） |
| Funding rate / basis dislocation | 「Funding rate / basis dislocation」 | **funding rate cross-venue Δ > 2σ 或 basis (perp - spot) > threshold per asset**；threshold per asset 來自 walk-forward block bootstrap（per Decision 4）；無變更 |
| Own behavior anomaly | strategy fill rate divergence / rejection spike / slippage outlier / lease grant rate | **z-score / isolation forest / ARIMA residual**（per v5.8 既有），**保留無變更** |
| Y2+ ML detector | autoencoder reconstruction error | **保留**（per v5.8 既有）；但加 ADR-debt：autoencoder training data window **必 exclude anomaly period**（per H-4 sprint dispatch HIGH item） |

#### M8 統計檢測 hot path budget

v5.8 §2 M8 + E4 audit 確認 M8 hot path 必 ≤ 5μs（per dispatch H-16 SLA budget）；本 ADR 替代算法（RV pct / correlation Δ / funding Δ）為 O(rolling window) 計算，typical N=30/90 + 25 symbols 在 cargo bench 預估 < 2μs，**不破鎖點**。

#### 為什麼不採 GARCH break

per §Context 數學理由 4 + §Alternatives Considered 第一條：crypto perp vol forecast benchmark 上 GARCH(1,1) 比 RV pct + simple rolling mean 預測精度 +1-3% 但 train 成本 50-100x；anomaly detection 場景下 RV pct 提供 categorical 規 alert response 即可，不需 GARCH 的 conditional variance forecast。

### Decision 3 — M10 Tier D regime auto-classify 算法

對應 v5.8 §2 M10 Tier D (line 367) 設計，本 ADR 鎖入主路徑 + Y3+ ADR-debt evaluation。

#### 3.1 主路徑（Y2-Y3 active）— ATR-vol × Funding-state 雙 axis 9 cell 矩陣

| 元素 | 設計 |
|---|---|
| Axis 1: ATR-vol regime | 3 級分類：**LOW / MID / HIGH** 基於 14-day ATR 對 90d distribution percentile（< 33% = LOW、33-66% = MID、> 66% = HIGH） |
| Axis 2: Funding state | 3 級分類：**CONTANGO / NEUTRAL / BACKWARDATION** 基於 funding rate cross-section（24h rolling mean funding rate < -0.005% = BACKWARDATION、-0.005% ~ +0.005% = NEUTRAL、> +0.005% = CONTANGO） |
| 矩陣形狀 | 3 × 3 = **9 cell**；每 cell 對應一個 regime label（如 `LOW-CONTANGO` / `HIGH-BACKWARDATION` 等） |
| Cell-specific 策略 allocation | 每個 regime cell 對應 strategy weight prior（per Sprint 2 Alpha Tournament + Sprint 7 Advisory Allocator 既有 surface）；cell × strategy weight 矩陣為 V111 schema 存儲 |
| Cell transition latency | regime cell 切換 hysteresis：percentile shift 必 > 5% 持續 > 2h 才算 cell transition；防 flap |
| Cell stability metric | M10 Tier D activation Y2 後每 7d 統計各 cell sample 數量；任一 cell sample < 30 (90d 累積) 觸發 warning（regime 過 rare 不適合 cell-specific allocation） |

#### 3.2 為什麼 ATR-vol + funding state 是 crypto 微結構天然 feature

| Feature | crypto perp 微結構意義 |
|---|---|
| ATR-vol | volatility regime = position sizing / SL/TP 距離的核心 driver；ATR 在 OpenClaw 既有 indicator pipeline 有 cache + 計算成本 < 1μs/symbol |
| Funding state | **funding 是 crypto perp 的 DNA**（spot 沒有）；funding sign + magnitude 直接反映 long/short imbalance + leverage stress + funding-arb opportunity；CONTANGO/BACKWARDATION 是 crypto 對 traditional finance term-structure 的微結構對應 |

對比 HMM 隱狀態：HMM K 個隱狀態的 semantic 在 train 後是 black box，operator 看 state matrix 看不出 state 1 vs state 2 對策略意義為何；本 ADR 9 cell 矩陣每 cell 都有 explicit semantic（`LOW-NEUTRAL` 表示 calm market、`HIGH-BACKWARDATION` 表示 panic short squeeze 等），策略分配 prior 可以人工解讀 + cowork review。

#### 3.3 為什麼分 3 級（不是 2 級或 5 級）

| 分級 | 棄因 / 採用理由 |
|---|---|
| 2 級（LOW / HIGH only） | 失去 NEUTRAL / MID 信息；多數 trading hour 落在 MID regime，2 級會把 50%+ 樣本 force 到 LOW 或 HIGH 偏一邊 |
| **3 級（LOW / MID / HIGH）** | **採用**；33/33/33 percentile split 樣本量平均；3 級語義人類可解讀 |
| 5 級（5-quantile） | Y1 樣本量 ~25k decisions 在 5 × 5 = 25 cell 矩陣下每 cell 平均 ~1000 sample，cell-specific allocation 統計噪音大；Y3+ Tier D 表現好 + AUM > $100k 時可考慮 amend 升 5 級 |

#### 3.4 替代評估（Y3+ ADR-debt）— PELT change-point detection

| 元素 | 設計 |
|---|---|
| 評估時點 | Y3 Q1（M10 Tier D activation 至少 2 cycle ≈ 8 month 樣本後）|
| 評估方法 | PELT (Pruned Exact Linear Time, Killick 2012) on rolling realized return / vol series；對比 ATR-vol+funding 雙 axis 矩陣 |
| PELT 採用觸發條件 | PELT-detected change-point 對應的 regime allocation 在 OOS demo 21d 累積 alpha **≥ +1% absolute** vs ATR-vol+funding 雙 axis 矩陣同期 |
| Y3+ amendment 路徑 | 觸發條件達成 → 開新 ADR amend 本 Decision 3.4；不觸達 → 維持雙 axis 矩陣 |
| 為什麼 Y3+ 才評估 | (a) PELT 計算成本比 ATR percentile 高 ~10x，Y1 / Y2 hot path budget 緊；(b) Y3+ 樣本量 > 50k decisions 才有統計力對比兩種 regime detection；(c) Y3+ AUM > $50k 才有 Tier D capital scaling，提前評估 wasted bandwidth |
| 為什麼不採 PELT 立即 Y2 | PA 仲裁 #5 採 (a) ATR-vol+funding Y2-Y3 主路徑；該決定基於 Y2 工程成本 + alpha 風險 + AUM scaling timing 三維度 |

### Decision 4 — Realized vol percentile threshold + block bootstrap

對應 Decision 2 RV pct + Decision 3 ATR percentile + Decision 2 funding rate Δ threshold，本 ADR 鎖入 threshold 的估計方法 + 熱更新路徑。

| 元素 | 設計 |
|---|---|
| Threshold 來源 | M8 / M10 Tier D 所有 regime threshold（如 RV pct > 90%、funding Δ > 2σ、ATR percentile < 33% 等）**必 walk-forward 估計**，不寫死 magic number |
| 估計方法 | **Block bootstrap**（block size = 5-10 day window，~500 resamples）計算 threshold sampling distribution；對 `walk-forward-validation-protocol` skill 既有 SOP 對齊 |
| Threshold 存儲 | V109 schema (M8 anomaly) + V111 schema (M10 Tier D config) 包含 `regime_threshold_table` column；不寫死 in code |
| Hot update 路徑 | per ADR-0009 ArcSwap，threshold 可 hot-update without engine restart；典型 cadence = 30d re-estimate（Y1 H2 起）|
| Re-estimate cadence triggers | (a) calendar：30d 自動 re-estimate（auto cron）；(b) regime cell stability warning：cell sample < 30 觸發手動 re-estimate；(c) Operator manual override：via Console / Decision Lease |
| Threshold backtest range | 初始估計用 demo 累積 fills + market data ≥ 90d；live 後用 live + demo fills 混合（per `feedback_demo_over_paper_for_edge` 不混 paper） |
| 為什麼 block bootstrap 而非 simple percentile | Crypto 1m / 1h time series 強自相關 + 異方差；simple percentile 低估 tail risk；block bootstrap 保留 5-10d block 內結構 + 重 sample block 計算 percentile sampling distribution = 對 vol clustering robust |
| Cost 預估 | M8 / M10 Tier D 整體 threshold 估計 hot path < 1ms/30d cycle（不在 trading hot path）；cargo bench 預估 P99 < 5ms |

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **允許 GARCH for vol forecasting only**（不 regime detection） | 違反 math-model-audit skill 黑名單範圍 — skill 列「GARCH 家族」**所有用途**；GARCH 在 crypto 6h-24h vol forecast benchmark 比 realized vol rolling mean 精度只高 +1-3% 但訓練成本 50-100x，不是 cost-effective alpha；若未來真有實證需要使用，必 amend skill → amend 本 ADR Decision 1，不在本 ADR 直接開特例 |
| **採 ML autoencoder for regime classify**（替代 ATR-vol+funding 矩陣） | autoencoder 是 reconstruction-error metric，不是 categorical regime；M10 Tier D 需要 categorical regime cell 規 strategy allocation prior，autoencoder 輸出 continuous 浮點不符合該需求；autoencoder 在 v5.8 §2 M8 Y2+ 已預設為 anomaly detector（不是 regime classifier），定位明確 |
| **採 spectral clustering on returns features** | crypto sample size + non-stationarity 致 cluster K 選擇不穩定（unsupervised K 選擇與 HMM K 選擇同病）；cluster 後 semantic 仍是 black box，喪失「ATR-vol+funding 雙 axis 的人類可解讀性」優勢 |
| **採 K-means clustering on (ATR, funding) features** | K-means 在 (ATR, funding) 2D 空間結果跟手動 3×3 = 9 cell binning 接近，但 K-means 中心點隨樣本 drift（需頻繁 retrain）+ K 選擇仍需驗證；3×3 percentile binning 是 deterministic + 30d hot update + 不需 retrain，工程成本顯著低 |
| **採 PELT change-point detection 立即 Y2** | PA 仲裁 #5 採 (a) Y2-Y3 ATR-vol+funding 主路徑（per Decision 3.4 §「為什麼不採 PELT 立即 Y2」三維度理由）；PELT Y3+ 評估 ADR-debt 已留 |
| **採 Hurst exponent alone for vol regime** | Hurst exponent 在 v5.8 §2 M8 原文已列；本 ADR Decision 2 保留 Hurst 為輔助 metric，但 Hurst 單獨不足以涵蓋 v5.8 §2 M8 「vol regime shift」域 — Hurst 對長期 memory 敏感，對 short-horizon vol cluster 不敏感，需 RV pct 補位 |
| **不寫 ADR，只靠 math-model-audit skill 提示** | skill 是 advisory；sub-agent dispatch 在沒有 ADR 級 grep gate 時容易繞過；歷史 audit 顯示無 ADR 級鎖入 → drift 風險高（per PA report 仲裁 #5 第 3 條） |
| **ADR 範圍只談 M8，M10 Tier D 另開 ADR** | M8 / M10 Tier D 黑名單條款重複（drift 風險）+ ATR-vol 既是 M8 vol regime shift 偵測 input 又是 M10 Tier D Axis 1，拆 ADR 會造成「同一個 feature 在兩 ADR 各定義一次」的 source-of-truth 衝突；合併單一 ADR 是正確 governance pattern |

## Consequences

### Positive

- **math-model-audit skill 黑名單在 ADR 級永久強化** — sub-agent dispatch 階段 PA + MIT + E2 強制 grep 拒絕；防止 sub-agent 繞 skill 提示直接拉 `arch` / `hmmlearn` dependency
- **ATR-vol + funding state 雙 axis 是 crypto 微結構天然 feature** — funding 是 perp DNA，ATR-vol 在既有 indicator pipeline 已計算 + cache；hot path budget 影響極小（< 2μs/symbol）
- **9 cell 矩陣每 cell 都有人類可解讀 semantic** — operator 與 cowork review path 可看懂 regime 意義；對比 HMM K 個隱狀態 black box，governance / 仲裁 / debugging 顯著更容易
- **replication crisis 警覺降低** — 不採 HMM / GARCH 即 sidestep 大多數 academic-toy 模型 OOS 失敗風險（per Harvey-Liu-Zhu 2016 警示）
- **threshold 不寫死 + walk-forward + block bootstrap + ArcSwap 熱更新** — vol regime / funding state shift 時可 30d 自動 re-estimate；不需 engine restart
- **Y3+ PELT evaluation ADR-debt 已留** — 不關閉未來路徑；若 Y3+ 真有實證需要 amend 開放
- **Y2-Y3 M10 Tier D activation 條件清晰** — AUM > $50k + ATR-vol+funding 雙 axis cell-specific allocation evidence Y2 末 evaluation；對齊 v5.8 §2 M10 既有 capital scaling 路徑

### Negative / Risk

- **ATR-vol + funding state 雙 axis 解釋力可能弱於 HMM regime** — HMM 數學上對 hidden state 有 mathematical elegance（state transition probability 可估計、Forward-Backward 算法可推斷後驗 state distribution）；ATR-vol+funding 雙 axis 是手動 binning，不提供 transition probability matrix；mitigation = M11 nightly replay 驗 actual edge（real test 是 PnL，不是數學優雅）+ Y3+ PELT evaluation 是 amendment hedge
- **3×3 = 9 cell 在 Y1 樣本量下統計力有限** — Y1 末預期 ~25k decision events，9 cell 平均 ~2800/cell；但 regime cell 分佈非均勻（MID-NEUTRAL 預期 > 50% 樣本），其他 cell 可能 < 1000 sample；mitigation = Decision 3.1 cell stability metric 7d 統計 warning + cell sample < 30 觸發 fallback strategy allocation
- **funding state threshold 跨 symbol 異質** — 不同 perp symbol（BTC vs ALT）funding rate baseline 差 5-10x；funding Δ > 2σ threshold per-symbol 估計，increase 工程複雜度；mitigation = Decision 4 threshold 表 per-symbol；V109 / V111 schema 包含 `symbol` column
- **block bootstrap 估計噪音** — 500 resamples 在 sparse symbol 可能 sampling distribution 寬；mitigation = re-estimate cadence 30d + Operator manual override path
- **Y3+ PELT evaluation timing 仍 open** — PELT 採用觸發條件 `OOS 21d 累積 alpha ≥ +1%` 是設計選擇；若 Y3+ 樣本累積後該 threshold 被質疑（Operator / QC 認為 +1% 太鬆或太緊），需 amend 本 Decision 3.4；mitigation = ADR-debt 機制 + Y3 Q1 PM 仲裁
- **Decision 1 「無例外」可能與未來 corner-case 衝突** — 若未來真有實證需要使用 GARCH（如僅做 forecast 精度 benchmark），現規範要求先 amend skill → amend 本 ADR；mitigation = amendment 路徑明確 + Decision 1 例外段允許 read-only counterfactual

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| `srv/.claude/skills/math-model-audit/SKILL.md` | **本 ADR 是該 skill 黑名單的 governance promotion**；ADR 不重寫 skill，skill 為 source of truth；ADR Decision 1 強制 dispatch grep gate |
| `srv/.claude/skills/walk-forward-validation-protocol/SKILL.md` | **Decision 4 block bootstrap 對齊該 skill 既有 SOP**；threshold 估計用該 skill 的 walk-forward + bootstrap protocol |
| v5.8 §2 M8 Anomaly Detection (lines 279-318) | **Decision 2 替代「GARCH break」字眼**；保留 v5.8 §2 M8 既有架構（statistical / ML / counterfactual 三層）；保留 Hurst exponent 為輔助 |
| v5.8 §2 M10 Tier D Regime Discovery (line 367) | **Decision 3 鎖入「auto-classify market regime」算法為 ATR-vol+funding 雙 axis 9 cell 矩陣**；M10 Tier D 進入 Y2 activation 前必 cite 本 ADR |
| ADR-0021 Alpha Source Architecture Upgrade | **regime cell 對應 strategy weight 是 alpha-side governance**；Decision 3.1 cell-specific allocation 與 ADR-0021 R-2 Strategist orchestrator 範疇對齊 |
| ADR-0009 ArcSwap config hot-reload | **Decision 4 threshold hot update 路徑**；regime threshold table 走 ArcSwap pattern |
| ADR-0024-lite Cowork operator-assistant scope | **Decision 1 例外段「read-only counterfactual analysis」對齊**；任何 HMM / GARCH read-only run 結果不得寫 live state |
| V109 schema spec (CR-8 placeholder) | **本 ADR 為 V109 anomaly_events table 提供算法選擇邊界**；V109 spec doc cite 本 ADR Decision 2 |
| V111 schema spec (CR-8 placeholder) | **本 ADR 為 V111 discovery_tier_config table 提供 regime cell × strategy weight 資料模型**；V111 spec doc cite 本 ADR Decision 3 |
| M11 Replay Divergence (v5.8 §2 M11) | **Decision 1 例外段允許 HMM read-only counterfactual 走 M11 replay surface**；不創新模塊 |
| M4 Hypothesis Miner (v5.8 §2 M4) | **Decision 1 黑名單適用 M4**；M4 自動 feature mining 不得自動 propose HMM / GARCH-based feature |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | M8 / M10 Tier D regime detection 不創寫入口；anomaly trigger → M3 HEALTH_DEGRADED 走 Decision Lease |
| 2 | 讀寫分離 | ✅ | regime detection + threshold estimation 純讀；策略 allocation 經 Strategist + Decision Lease |
| 3 | AI 輸出 ≠ 命令 | ✅ | regime cell 切換不直接執行；經 M3 / Strategist / Decision Lease |
| 4 | **策略不繞風控** | ✅ | **M8 anomaly trigger 不繞 Guardian**；任何 anomaly → M3 HEALTH_DEGRADED → 走 5-gate 風控 |
| 5 | 生存 > 利潤 | ✅ | M10 Tier D activation Y2-Y3 condition AUM > $50k + cell stability metric；保守路徑 |
| 6 | 失敗默認收縮 | ✅ | cell sample < 30 fallback strategy allocation；threshold estimation 失敗 fallback 既定 percentile |
| **7** | **學習 ≠ live** | ✅ | **M10 Tier D Y1 read-only, Y2 active gated**；Decision 1 例外段 HMM read-only counterfactual 不得寫 live state |
| 8 | 交易可解釋 | ✅ | regime cell 9 cell semantic 人類可解讀；threshold 估計 audit log 留 |
| 9 | 雙重防線 | ✅ | regime + Guardian + Decision Lease 多層 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | regime threshold = 事實（block bootstrap empirical）；cell × strategy allocation = 推論（per Strategist）；Y3+ PELT 評估 = 假設 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | regime cell 自主切換在 P0/P1 內；不需 operator 逐次仲裁 |
| 12 | 行為由 evidence 演化 | ✅ | threshold walk-forward + block bootstrap + 30d re-estimate；Y3+ PELT evaluation 條件明確 |
| **13** | **cost 感知** | ✅ | **RV pct + funding 計算 cost 低** (< 2μs hot path) **遠優於 HMM/GARCH MCMC iteration**（typical 100-1000ms train cost）；ADR 強制黑名單即是 cost 治理 |
| 14 | 零外部成本 | ✅ | ATR / funding 是 Bybit WS feed；不需付費 data source |
| 15 | 多 agent 形式化協作 | ✅ | regime + Strategist + Guardian + Conductor 各有明確 surface |
| **16** | **Portfolio > 孤立 trade** | ✅ | **regime allocation 是 portfolio-level**；M10 Tier D cell × strategy weight 矩陣即是 portfolio-level diversification mechanism |

## Cross-References

- **math-model-audit skill**：`srv/.claude/skills/math-model-audit/SKILL.md`（HMM / GARCH 黑名單 source of truth；本 ADR Decision 1 governance promotion）
- **walk-forward-validation-protocol skill**：`srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`（Decision 4 block bootstrap + OOS SOP）
- **v5.8 主檔 §2 M8 Anomaly Detection**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:279-318`（本 ADR Decision 2 替代字眼）
- **v5.8 主檔 §2 M10 Tier D Regime Discovery**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:367`（本 ADR Decision 3 鎖入算法）
- **ADR-0021 Alpha Source Architecture Upgrade**：`docs/adr/0021-alpha-source-architecture-upgrade.md`（regime cell × strategy weight 與 alpha-side orchestrator 範疇）
- **ADR-0024-lite Cowork operator-assistant scope**：Decision 1 例外段 read-only counterfactual 對齊
- **ADR-0009 ArcSwap config hot-reload**：Decision 4 threshold hot update 路徑
- **V109 schema spec (CR-8 placeholder)**：anomaly_events table + severity taxonomy；本 ADR Decision 2 為算法邊界
- **V111 schema spec (CR-8 placeholder)**：discovery_tier_config table + cell × strategy weight 矩陣；本 ADR Decision 3 為資料模型基礎
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §1 CR-5（M10 Tier D 模型黑名單 hardening + ADR-0036 GARCH 替換）
- **PM final verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md` §四 仲裁 #5（採 (a) ATR-vol+funding Y2-Y3 主路徑）
- **Harvey-Liu-Zhu 2016**："...and the Cross-Section of Expected Returns"（金融 replication crisis academic reference）
- **Killick 2012**：PELT (Pruned Exact Linear Time) change-point detection（Y3+ evaluation 參考）

## Engineering Scope Reference

| Sprint | Item | Workload |
|---|---|---|
| Sprint 1A-γ | M8 schema (V109) + M10 Tier D config table (V111) + ADR-0036 land | 40-60 hr M8 + 30-50 hr M10 Tier D config |
| Sprint 3 | M8 statistical detector (rolling z / ARIMA / RV pct) read-only | 60-80 hr |
| Sprint 8 | M8 alerting + severity routing (Slack notification high-severity) | 30-50 hr |
| Y2 | M10 Tier D activation (ATR-vol+funding 雙 axis matrix + cell × strategy weight) | 100-160 hr |
| Y2+ | M8 active trigger into M3 + ML autoencoder detector | 80-120 hr |
| Y3+ | PELT change-point evaluation (per Decision 3.4 ADR-debt) | variable（評估後決定 amendment） |

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via PA 仲裁 #5（採 (a) ATR-vol+funding 雙 axis Y2-Y3 主路徑） | 2026-05-21 | ✅ APPROVED-pending-commit |
| TW | 本文件起草（v5.8 §2 M8 + M10 Tier D 算法選擇邊界合併 ADR） | 2026-05-21 | ✅ Drafted |
| MIT | V109 / V111 schema 結合算法 spec 確認；regime threshold table 結構審 | TBD（Sprint 1A-γ） | 🟡 PENDING |
| QC | Y3+ PELT evaluation timing 審視 + block bootstrap 估計方法對齊 walk-forward-validation-protocol skill | TBD（Y2 末 Sprint 9-10 + Y3 Q1） | 🟡 PENDING |
| E2 | Sub-agent dispatch grep gate（`hmm\|markov_switching\|garch`）對齊 + dispatch SOP 寫入 | TBD（Sprint 1A-γ dispatch 前） | 🟡 PENDING |
| FA | M3 HEALTH_DEGRADED trigger 對 M8 anomaly + cell × strategy weight 風控路徑審 | TBD（Sprint 3 + Y2） | 🟡 PENDING |
| PM | Sprint 1A-γ DESIGN dispatch 前 ADR-0036 land 確認 + Y3+ PELT evaluation 仲裁 | TBD（Sprint 1A-γ + Y3 Q1） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0036 — M8 Anomaly Detection + M10 Tier D Regime — Model Blacklist (HMM / Markov-switching / GARCH 永久禁用) + ATR-vol × Funding-state 雙 axis 9 cell 矩陣替代 + Realized Vol Percentile + Block Bootstrap Threshold + Y3+ PELT Evaluation ADR-debt (Proposed-pending-commit per 2026-05-21 PA 仲裁 #5)*

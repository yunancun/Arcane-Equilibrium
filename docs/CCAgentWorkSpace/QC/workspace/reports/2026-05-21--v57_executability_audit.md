# v5.7 Dispatch-Safe Patch 執行性審核 — QC 視角
**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.7 §0-§11 engineering precision fix 全部正當（reviewer 6/6 verified），但 5 個策略 APR 假設 4/5 樣本量未驗證 + 2 個 critical 數學 inconsistency（§1 數字內部不一致 / Y2 mature APR 算術錯誤）+ Sprint 1A 派發前須補 dispatch 條件

---

## 0. 5 個策略數學基礎核驗

### C10 funding harvest 5% APR: **QUESTIONABLE**
- v5.7 §1 假設 5% × $2,000 baseline
- 真實水準：Bybit BTC perpetual funding rate 2024-2025 年化平均**約 7-12%**（牛市偏多區段），熊市可降至 1-3%；無單一 stable baseline。calendar-weighted ~5% 對全周期 "稍保守但合理"
- **隱性假設未明寫**：v5.7 §2 capital structure 是 "long spot + short perp delta-neutral"，但 Bybit demo 不支援 spot lending（per `crypto-microstructure-knowledge` §3.2 + memory `project_funding_arb_v2_deprecation_path` G-2 結案 negative）→ 主帳 production live spot 有，但 demo / Stage 1 Demo Micro-Canary **無法驗證**該策略；Stage 4_LIVE_PENDING 前無 empirical Stage 1-3 evidence
- 樣本量：未提及 in-sample backtest N
- **Must-fix**：v5.7 §1 注明「假設基於 BTC perpetual funding rate 2024-2025 calendar mean ~5% baseline；funding rate regime-dependent，熊市 baseline 可降至 1-3%」+ Stage 1-3 替代驗證路徑（spot leg 用 paper-only？）

### Unlock SHORT 18% APR: **VALID-PARTIAL**
- WebSearch verify：學術研究確認 ~90% 解鎖事件 → 負報酬，30d pre-unlock 已被市場 price-in，大解鎖事件約 2.4× 加大跌幅
- 18% APR 假設來源於 SSRN 文獻 directionally consistent，但**未明寫樣本量 N**
- **隱性問題**：30d pre-unlock price-in = post-publication decay (McLean-Pontiff 2016) 已開始；Unlock SHORT 屬於已知公開 alpha（Tokenomist 平台公開）→ replication crisis 必查
- v5.7 §1 calendar-weighted 0.48x 假設 W14 上線 — 但 Stage 0R → Stage 1 → Stage 4 全部 ~6 sprint 含 Demo extended 14d / Demo full 21d，W14 偏樂觀
- **Must-fix**：Sprint 2 Alpha Tournament 必算 Unlock SHORT 24mo event study + post-2020 vs post-2024 sub-period stability test（McLean-Pontiff decay 是否已現）+ 樣本量明寫 N ≥ 30 事件

### Pairs trading 12% APR: **QUESTIONABLE**
- v5.7 §1 寫 "perp-perp BTC/ETH, ETH/SOL multi-pair"，12% APR 中度 aggressive
- **數學風險**：cointegration 需 Engle-Granger 或 Johansen test（per `walk-forward-validation-protocol` §5）；crypto pair 的 cointegration relationship **non-stable** — 2017-2021 stable pairs 多在 2022 LUNA / FTX 之後 break
- multi-pair (BTC/ETH + ETH/SOL + ...) → 高 cross-pair correlation；effective N << nominal N（per `portfolio-construction-protocol` §3.5）
- **Must-fix**：Sprint 2 Alpha Tournament 必跑 rolling cointegration test on 各 pair（15m + 1h timeframe）+ 2020-2026 sub-period stability + multi-pair correlation matrix 列出 effective N

### C13 defined-risk put spread 10% APR: **QUESTIONABLE**
- v5.7 §1 改 naked → defined-risk put spread（v5.6 reviewer §3 fix 正確）
- IV-RV gap 真實水準：Bybit BTC options 2024-2025 平均 IV-RV gap **約 2-5 vol points**（compressed regime），歷史極端 spike 達 15+ vol points；10% APR 假設介於 mid-range
- **隱性問題**：defined-risk vs naked → premium 收入下降 ~30-40%（capped downside trade-off）；10% APR 對 defined-risk 偏 aggressive — defined-risk put spread mature 量化基金常見 6-10% APR
- Bybit options 流動性問題：BTC options OK，ETH 偏低，alt options 幾乎無流動性
- **Must-fix**：Sprint 2 Alpha Tournament 必驗 Bybit BTC + ETH options 過去 12-24mo IV-RV gap empirical distribution + 主動成交 fill rate（PostOnly mechanism 對 options 是否適用）

### Funding short-only 25% APR: **HIGH-QUESTIONABLE**
- v5.7 §1 寫 "高 threshold 觸發頻率（v5.6 'rare'）"，25% × $700 × 0.25 calendar = $44
- **關鍵問題**：25% APR 是 "active periods" 還是 "calendar-weighted"？若 calendar-weighted 0.25x 已含 "rare" 觸發率 → expected income $44 OK；若 25% 已是 calendar baseline → $44 × （rare freq）必 << $44
- v5.7 §1 calendar formula `25% × $700 × 0.25 = $44` 數學正確，但 25% **APR 本身的 expected value** 需 verify
- 樣本量：高 threshold + rare → N 樣本可能 < 30 events / yr，t-test power < 0.5（per `walk-forward-validation-protocol` §0 樣本量強制檢查）
- **Must-fix**：明定 "25% APR 是 active period during high-funding regime；calendar frequency 估計獨立 verify；若 N < 30 events / yr → 升 t-test power 問題 → 樣本量不足"

---

## 0.5 Y1+Y2 income 數學

### Y1 $300-550: **PASS-WITH-CONSISTENCY-BUG**
- v5.7 §1 加總：69 + 130 + 40 + 32 + 44 + 26 + 80~100 = **$421-441 median**
- v5.7 §1 結論寫 "$421 median ~ 4.2% Y1 APR"，與計算 consistent ✅
- v5.7 §10 range $300-550 OK
- **但 §1 範圍底「$300」需驗**：若所有策略到 80% confidence interval lower bound（Sharpe 0.5×, calendar 0.8×, edge bouncing），$300 可能偏高 — 真實 floor 含 LUNA-style cascade 可能 << $300 甚至 negative
- **Should-fix**：Y1 income $300 floor 須包括 1 個 stress event（per §8 5 scenarios）的 implicit haircut；建議加 "$300 assumes no major regime shift; -10% to -30% adjustment under stress"

### Y2 mature $850-1050: **MATH-ERROR — 計算結果與標題不符**
- v5.7 §2 加總：100 + 270 + 120 + 150 + 175 + 35 + 80~100 = **$930-950 median**
- v5.7 §2 自稱 "Y2 Total (no overlay): ~$935 ≈ 9.4% APR" ✅ 數學正確
- v5.7 §10 寫 "Y2 mature (no overlay alpha): $850-1,050 ≈ 9.4% APR"
- 但 §2 也寫 "Honest Y2 estimate: $850-1,150 median ~$950 ≈ 9.5%" — **內部不一致**：§2 與 §10 上限 $1,150 vs $1,050 差 $100；overlay verified 路徑 §2 寫 $1,043-1,097 vs §10 寫 "$1,050-1,250 ≈ 11%" 又差 $150
- **Must-fix**：Y2 range 在 §2 / §10 統一一個明確 anchor — recommend `Y2 honest no-overlay: $850-1,050 median $935`；`Y2 overlay verified: $1,040-1,100 median $1,070`

### Tiered APR (Earn) $26/yr: **PASS**
- v5.7 §1 計算：first $200 @ 10% = $20，× 0.69 = $14；remaining $600 @ 3% = $18，× 0.69 = $12；total $26 ✅
- 數學正確，比 v5.6 hardcoded $33 honestly downward
- **Caveat**：10% 是 Bybit Earn 首層 introductory rate；通常為**限時 promotion** — 是否 sustained 全年需 verify Bybit Earn 當前 tier schedule
- **Should-fix**：v5.7 §4 注明 "10% tier 1 rate 假設為 sustained；若 promotion 結束 → 全部 @ 3% → Y1 Earn income = $12 not $26"

---

## 1. Top 3 執行性風險（排序）

### Risk 1：Y2 mature APR 內部不一致 + Y1 floor 未含 stress haircut
- **嚴重度**：HIGH
- **位置**：v5.7 §1 + §2 + §10
- **描述**：
  - §2 寫 $850-1,150 median $950
  - §10 寫 $850-1,050 ≈ 9.4%
  - $100 上限差 + overlay verified path 內部 $150 差
  - Y1 $300 floor 未含 stress event implicit haircut
- **為何屬「執行性」（非邏輯）**：策略 thesis 不變、reviewer §1-6 fix 正確，但 income 數字呈現有算術 / range bound 不一致 — operator 對外宣告或 Sprint 10 review 時哪個 $ figure 是 "真"？
- **Must-fix 建議**：v5.7 patch r2 在 §1/§2/§10 統一 income range（建議：$850-1,050 no-overlay / $1,040-1,100 overlay verified，single source of truth in §2，§10 cite §2）

### Risk 2：4/5 策略樣本量未明寫 / N < 30 power 風險
- **嚴重度**：HIGH
- **位置**：v5.7 §1 + §8 Sprint 2 Alpha Tournament（implicit）
- **描述**：
  - C10 5% APR：未寫 backtest N
  - Pairs 12% APR：multi-pair cointegration N 未寫，effective N （correlation-adjusted）未計
  - C13 10% APR：Bybit options 過去 12-24mo IV-RV gap 樣本未提
  - Funding short-only 25% APR：high-threshold "rare" 觸發 events / yr 未估
  - 只有 Unlock SHORT 有 SSRN 24mo event study 數據（也未明寫 N）
- **為何屬「執行性」（非邏輯）**：策略邏輯 OK，但 Sprint 2 Alpha Tournament 預設要產出 "ranked candidate list with verified statistics"（§2 Sprint 2 plan）— 5 個策略的 prerequisite empirical N 樣本能否在 Sprint 2 W4-7 內準備好是 dispatch-blocker
- **Must-fix 建議**：Sprint 1A dispatch 前確認 — (a) C10 / Pairs / C13 / Funding short 各 has ≥ X mo 歷史數據可重建，(b) Bybit Earn 首層 promotional 10% rate 當前 status verify

### Risk 3：Stage 0R → Stage 4 LIVE 時間表 vs calendar-weighting 假設不一致
- **嚴重度**：MEDIUM
- **位置**：v5.7 §1 calendar 計算 + v5.6 §12 Stage gate language
- **描述**：
  - v5.7 §1 假設 Unlock SHORT live W14（25/52 = 0.48x）；Stage gate 為 0R replay → 1 Demo Micro-Canary 7d → 2 Demo Extended 14d → 3 Demo Full 21d → 4 LIVE
  - Sprint 3 W8-11 = top-1 build + Stage 0R；Sprint 4 W12-15 = Stage 1 + 2 + 3 + 4 promotion
  - 7 + 14 + 21 = 42 day = 6 weeks Stage 1-3，加 Stage 0R + Stage 4 evaluation = 7-8 週 = Sprint 4 一個 sprint 內完成？
  - W14 live → 假設 Sprint 4 末（W15）對齊，timeline 偏 tight
- **為何屬「執行性」（非邏輯）**：governance language 對 (AMD-2026-05-15-01)、 evidence 框架對；但 W14 vs Stage gate 過 sprint 流程是否現實需 PM 對齊
- **Must-fix 建議**：v5.7 §1 加 "Assuming all Stage gates pass on first try; one rejection at any stage adds 2-3 weeks"

---

## 2. Hours sanity check（quant 工時 vs estimate）

v5.7 §9 Sprint summary total 1,190-1,590 hr / 39 weeks。

**Quant 視角**：
- Sprint 2 Alpha Tournament 110-150 hr 含 5 個策略 evidence 重建 → 5 × ~25 hr = ~125 hr **OK 偏低**（每策略 24mo event study + cointegration test + IV-RV gap + funding regime + power analysis）
- Sprint 1A 60-80 hr 含 V103/V104 + 5 sensor + Earn governance — 60-80 hr 偏低（Earn governance integration alone v5.7 §4 寫 45 hr）→ **Sprint 1A 應為 80-100 hr**
- Sprint 1B 50-70 hr 含 C10 live + Earn manual stake + Tournament prep — 50-70 hr OK 但 C10 minimal viable + Stage 0R replay 可能需要 30 hr alone

**Should-fix**：Sprint 1A 上修至 80-100 hr 含 Earn governance + APR API integration full scope

---

## 3. 未識別的依賴 / 阻塞（資料 / 樣本量）

1. **Bybit options 歷史數據**：Sprint 1A "Bybit options chain recorder NEW" 表示**之前未收集**；C13 defined-risk Sprint 6 W20-23 build 前需 ~6-9 mo 歷史 IV-RV samples → Sprint 6 偏 tight，可能 push 到 Sprint 7-8

2. **Tokenomist 解鎖數據 24mo 完整性**：Sprint 2 Alpha Tournament 假設可拿到完整 24mo Tokenomist 解鎖事件 — trial integration 在 Sprint 1A 才剛開始 → API 限制 / 歷史回填能力未驗

3. **Bybit Earn first-tier 10% promotional rate**：是否仍在當前 schedule？ v5.7 §1 假設此 rate sustained 全年；若 promotion 結束 → 全部 @ 3% → Y1 Earn 從 $26 降至 $12 ($14 less)

4. **C10 demo Stage 1-3 不可行**：Bybit demo 不支援 spot lending → C10 (long spot + short perp) demo 階段如何驗證 alpha？是否 spot leg 用 paper / 假 fill？此 v5.7 未明示

5. **5 個策略 cross-correlation matrix 未列**：portfolio Risk decomposition / effective N 未驗證；25 symbol PCA assumption "BTC beta dominated" 是否成立 over 5 策略 multi-asset class 配置

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **Y2 income range 在 §2 / §10 統一 single anchor**（Risk 1 must-fix）— PA dispatch 前 income figure 對外只一個聲明

2. **Sprint 1A 工時上修 60-80 → 80-100 hr 含 Earn governance full scope**（§2 hours sanity check + Risk 1）— PA 排期準確性

3. **5 策略 empirical pre-Tournament readiness check Sprint 1A 末**（Risk 2 must-fix）— 確認 (a) Bybit options 歷史回填可行，(b) Tokenomist 24mo events 可拿，(c) C10 在 demo 不可驗的替代路徑明示

---

## 5. Sprint 1A 派發前 must-fix

1. **Y1 / Y2 income range 統一**：§1 / §2 / §10 三處 income figures 一致；single source of truth in §2，§10 cite，避免 reviewer round 16 重新挑
2. **Bybit Earn tier 10% promotional verify**：是否 sustained / introductory；若 introductory → Y1 Earn $26 → $12
3. **C10 Stage 1-3 demo 不可行解決方案明示**：spot lending demo 無 → 替代路徑（paper spot leg？live small canary？extended Stage 0R replay？）
4. **5 個策略 N / power 預估明寫**：每策略 expected N events for Sprint 2 Alpha Tournament + min N for t-test power 0.8 verify

---

## 6. Sprint 1B-3 should-fix

1. **Stage gate timing 對 calendar weighting 假設透明**：W14 Unlock live 假設 zero stage rejection；建議在 §1 加 conditional "(assuming first-try pass; one rejection adds 2-3 wks)"
2. **5 策略 correlation matrix Sprint 2 末出**：Sprint 3 build top-1 前須有 portfolio-level effective N（per `portfolio-construction-protocol` §3）
3. **Bybit options Sprint 6 timing**：6-9 mo 歷史數據 prerequisite → Sprint 1A 開始收集，Sprint 6 build 前 6 sprint = OK，但 IV-RV empirical distribution evaluation 需 Sprint 5 W17-19 完成
4. **funding_arb dormant slot 處置**：v5.7 §2 capital "$700 Funding short-only" 是 high-threshold 變體；既有 funding_arb dormant slot（per memory G-2 結案）與此**重複 capital allocation 風險** — 確認此非雙重計算

---

## 7. 可優化 / 拆分 / 並行

1. **Sprint 1A 可細拆**：Migration (V097/V098/V103/V104) + Governance (ADR) 可與 Sensor + Earn API 並行（兩 sub-thread），加速 dispatch
2. **Sprint 2 Alpha Tournament 5 策略可並行 evidence build**：QC + MIT 並行對 5 個 candidate 各 跑 1 個 study（per `quant-strategy-design` 10-step SOP）
3. **Macro / On-Chain counterfactual logger 可後置 Sprint 3-4**：v5.7 §5 已確認 Y1 counterfactual only → 不影響 Y1 income → 可優先 Sprint 1A 完成 Earn governance + 5 策略 prep + Sprint 3 Top-1 build
4. **Sprint 1A 內部依賴 critical path**：V103/V104 → hypotheses table → pre-registration framework → 5 策略 Sprint 2 評估；建議 V103/V104 W0-1 完成，後續並行

---

## 黑名單檢查（per math-model-audit skill）

✅ **無 black-list method**：HMM / GARCH / VPIN / 波動率均值回歸（單獨）/ 獨立 Donchian — 全部未出現於 v5.7 任何策略
✅ Defined-risk put spread（v5.6 §3 fix → v5.7 §1 carry over）符合 capped tail risk 原則
✅ Counterfactual-only macro / on-chain Y1（reviewer §5 fix → v5.7 §5）符合不過 claim alpha 原則
✅ Auto-Allocator Y2 defer（reviewer §4 → v5.7 §7）符合 ML/Discovery learning 不 live-order 原則

## Replication crisis 檢查（per quant-strategy-design §★）

- **Unlock SHORT**：SSRN published anomaly + Tokenomist 平台公開 → McLean-Pontiff 2016 post-publication decay 必查；Sprint 2 必跑 post-2020 vs post-2024 sub-period stability + alpha decay 趨勢
- **Funding harvest C10**：結構性 alpha （CEX↔perp basis）— 隨資金流入消失風險中等；建議 capacity estimate 而非 perpetual high alpha 假設
- **Pairs trading**：crypto pair cointegration **non-stable** — 2017-2021 pairs 在 2022 cascade 後普遍 break；建議 rolling cointegration test 而非 static
- **C13 VRP**：經典 academic anomaly（Bakshi-Kapadia 2003），crypto 版本流動性淺，已有 dedicated funds 競爭
- **Funding short-only**：rare 觸發 → 樣本量 < 30 events / yr 可能 t-test power 不足

✅ v5.7 reviewer §5 fix（macro / on-chain not counted as alpha until Y2 verified）符合 replication crisis 防範原則
⚠️ 5 策略全為已知公開 alpha → Sprint 2 Alpha Tournament 必納入 alpha decay test，不只 in-sample Sharpe

---

## OpenClaw context 一致性

✅ v5.7 §0-§11 不依賴 stale CLAUDE 條目；§13 References 對 verified web search round 15 evidence；對 5 策略當前 portfolio 狀態以 Sprint 2 Alpha Tournament 為實證來源（不假設預設值）
✅ funding_arb 既有 dormant slot 與 v5.7 §2 "Funding short-only $700" 為**不同變體**：v5.7 §2 是高 threshold rare event 變體，funding_arb dormant 是 G-2 結案的 baseline 變體；但 capital allocation 兩者並存風險已在 Risk 7 / §6 提醒

---

## 結論

**Verdict: GO-WITH-CONDITIONS**

v5.7 dispatch-safe patch engineering precision fix 全部正當（reviewer 6/6 fix verified）；策略 thesis 不變 OK；governance compliance OK；replication crisis 防範 partial OK；但 dispatch 前需 3 個 must-fix（Risk 1 income consistency / Earn tier verify / C10 demo path）+ Sprint 1A 工時上修 + 5 策略 N prep readiness check。

**核准 Sprint 1A 派 PA 條件**：完成 §5 4 個 must-fix，PA dispatch 前 income range single source 確認。

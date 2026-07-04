# QC 學習證據方法學重設計 — P1-2 反事實成本 / P2-7 evidence ladder / P2-8 多重比較 / F7 markout censoring · 2026-07-04

Bound role: QC(外部量化顧問)· READ-ONLY(僅本報告+memory 落盤;Linux 取證全程唯讀)。
Baseline: Mac dev tree(多 session 髒樹,錨點以本日讀取為準);Linux checkout `262596c69`(IMPL-A/IMPL-B 已上、未部署);runtime 證據時戳 2026-07-04。
上游: [PA validated fix plan](../../../PA/workspace/reports/2026-07-03--cold_audit_validated_fix_plan.md) P1-2/P2-7/P2-8/F7;[QC 07-03 全倉數學審計](2026-07-03--qc-full-repo-math-audit.md) F1/F2/F3。
判定:**REVISE 方案定稿 — 全部四項給出可執行 spec(公式+默認參數+驗收+測試用例),可直接交 E1。**

---

## 1. Executive Summary

一句話:把「單一樂觀常數成本 + fill-at-signal-price + n=2 二元裁決 + 無多重比較的 best-of-K headline + 無上界 markout 出場」的證據面,換成「同 cell 實現成本分位保守模型(p75×1.3 安全乘數,PG 實測校準)+ 分層 evidence ladder(L0 篩選/L1 配對執行實證 n≥8/L2 淨 edge n≥44/L3 既有 WF-PSR-DSR gate 不動)+ BH-FDR(q=0.10) 候選面 + sign-flip 選擇檢定 headline 面 + censored 標記出場」。

關鍵實測校準(Linux PG `trading.fills`,90d,engine_mode IN ('demo','live_demo')):
- taker fee p50 = **5.5 bps/side**、maker = **2.0 bps/side**(與 Bybit VIP0 標準費率一致,fee 不打折);
- taker |slippage| p50 ≈ 2.5–3.3、**p75 ≈ 11.3–13.7**、p90 ≈ 33–34、p95 ≈ 54–56 bps/side;
- per-symbol p75 離散度大:BTCUSDT 0.88 / ETHUSDT 1.71 vs ATOMUSDT **14.07** / FILUSDT 26.34 → 平價常數必然系統性偏。

現行反事實 `cost_bps=4.0`(round-trip 全含)僅等於 **maker 雙腿 fee、零滑點、零 adverse selection、零 funding**;同 lane touchability 審計(2026-06-24)33/33 深度掛單 no-touch 直接否定 maker 成交假設。對 ATOMUSDT 類 cell,保守實現成本 ≈ 2×(5.5+14.07)×1.3 ≈ **51 bps RT**,是現值的 ~13 倍。headline「top cushion +75bps」在 K=43 cells、median n=6 的選擇宇宙下,**純 null 之期望最大值 ≈ 224 bps**——現行 headline 連「噪音上界」都未超過。

---

## 2. P1-2 反事實成本模型(保守化 + 回填標記)

### 2.1 現行實現(FACT,錨點)

| 項 | 錨點 | 內容 |
|---|---|---|
| 成本常數 | `helper_scripts/research/cost_gate_learning_lane/outcome_writer.py:26` | `cost_bps: float = 4.0`(round-trip 平價,無分腿/分 symbol) |
| 成交假設 | `outcome_writer.py:275` | `entry = event.entry_price or price or last_price` — 被擋信號視為在 signal price 全額成交 |
| 淨值計算 | `outcome_writer.py:291-293` | `gross = side_sign·(exit−entry)/entry·1e4; net = gross − cfg.cost_bps` |
| 生產參數源 | `outcome_refresh.py:253` + runtime crontab(`27 * * * *`,APPEND_OUTCOMES=1) | `--outcome-cost-bps` default 4.0,cron 未覆蓋 → 生產即 4.0 |
| 污染規模 | runtime `/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl`(2026-07-04) | `blocked_signal_outcome` rows = **195,684**,抽樣尾行 `cost_bps: 4.0` 確證 |
| 消費面 | `outcome_review.py:211-232`(avg_net/cushion)、`false_negative_evidence_floor_ranking.py:282-304`、`horizon_specific_sealed_replay.py:210`(friction_bps fallback 亦 = 4.0) | 全部下游以 4.0 淨值排序/立案 |

### 2.2 新成本模型(公式)

對每筆 counterfactual outcome(blocked 或 markout-proxy probe):

```
cost_bps_conservative(cell, t)
  = 2 × [ fee_taker_bps + slip_q(symbol) ] × SM + funding_drag_bps(horizon)

fee_taker_bps  = 5.5                       # Bybit VIP0 taker;不假設 maker(touchability 33/33 no-touch)
slip_q(symbol) = Q_τ( |slippage_bps| of trading.fills
                      WHERE symbol=…, liquidity_role='taker',
                            engine_mode IN ('demo','live_demo'),
                            ts > now()−90d ),  τ = 0.75
SM             = cost_gate_safety_multiplier = 1.3   # 復用 risk_config_demo.toml:398,勿新增旋鈕
funding_drag_bps = Σ_crossings |funding_rate_snapshot| × 1e4
                   (horizon 內跨越該 symbol fundingInterval 結算 instant 的次數;
                    無 funding 快照時每次 crossing 記 1.0 bps 保守常數)
```

**分位選擇 τ=0.75 的理由(附條件)**:p50 定義上有一半成交比它貴(非保守);p95 被 cascade 極端樣本主導(90d demo n≈1.5k taker,p95 受 <80 筆尾樣本擺佈,估計自身噪音大)。p75×1.3 的有效覆蓋 ≈ p90 一帶(對本樣本:11.3–13.7×1.3 ≈ 14.7–17.8,介於 p75 與 p90 之間),在「保守不失真」與「排序仍有分辨力」間平衡。**條件**:此結論在成本分布右偏、90d 窗口平穩的假設下成立;若 slippage 分布出現 regime shift(如 altseason 流動性驟變),分位須隨窗口滾動自動更新(每次 cron refresh 重算,不快取超過 24h)。

**冷啟動 fallback 鏈(逐級降级,每級記錄 `cost_model_source`)**:
1. `symbol_q75`:該 symbol 90d taker fills n ≥ 20 → 用 per-symbol p75(當前 25 pinned symbols 中頭部覆蓋良好:ETHUSDT n=213、ATOMUSDT n=66);
2. `global_q75`:n < 20 → 全體 demo+live_demo taker |slip| p75(當前 ≈ 11.3–13.7);
3. `toml_tier`:PG 不可達(artifact-only lane 必須能離線跑)→ `risk_config_demo.toml:409-427 [slippage.tiers]` 按 24h turnover 取 tier rate(1–30bps)×1e4^0 換算 bps;
4. **硬 floor(任何情況)**:`cost_bps_conservative ≥ 2×5.5 = 11.0 bps`(純 taker fee 雙腿,零滑點下界;QC 硬約束 #4「手續費不打折」)。

**取數落地**:artifact-only lane 不直連 PG(boundary 聲明保留)。由既有 cron 內另一步驟(或 `ml_training_maintenance_cron.sh` 附掛)每日一次產出 `slippage_quantiles_latest.json`(symbol → {n, q50, q75, q90, asof}),outcome_writer 讀該 artifact;artifact 缺失/超 48h → fallback 鏈第 3 級。此設計保持 outcome_writer 純函數性(輸入=ledger+prices+quantile artifact)。

**避免雙重計費(重要)**:滑點全部記在 `cost_bps_conservative`,entry price **不再**另做 adverse-side 調整;fill-at-signal-price 殘餘偏差(能否成交)由 P2-7 L1 配對實證面回答,不在成本模型內重複懲罰。

### 2.3 Schema 與雙列輸出

每筆 outcome row 新增欄位(`ADAPTER_SCHEMA_VERSION` 升 `..._adapter_v2`,舊 row 視為 v1):

```
cost_model_version:   "conservative_v1"        # 舊 row 缺此欄 = "legacy_optimistic_v0"
cost_model_source:    "symbol_q75" | "global_q75" | "toml_tier" | "fee_floor"
cost_bps:             <conservative 值>         # 語義升級:review 直接沿用此欄,下游零改動
cost_bps_optimistic:  4.0                       # 保留舊常數作連續性對照
net_bps_optimistic:   gross − 4.0
realized_net_bps:     gross − cost_bps_conservative   # 權威淨值
funding_crossings:    <int>
```

### 2.4 歷史高估回填標記(不改寫 append-only ledger)

195,684 筆舊 row 不原地改寫(append-only 紀律 + D9 rotation 將動此檔)。方案 = **overlay 回填 artifact**:
1. 一次性腳本產出 `blocked_outcome_cost_backfill_v1.jsonl`:`attempt_id → {cost_bps_conservative, realized_net_bps_conservative, overstated_bps = cost_cons − 4.0, cost_model_source}`;
2. `outcome_review.py` / ranking / sealed replay 讀 overlay(存在則覆蓋計算,不存在按 `legacy_optimistic_v0` 全量標記 `legacy_overstated: true` 並在 packet 頭部聲明「本 packet 含未回填樂觀成本 row,數字不可用於候選立案」);
3. review packet 新增 cell 級欄位:`candidacy_flipped_by_cost_model: true/false`(舊模型過線、新模型不過線的 cell 顯式標記,供 operator 追溯此前排序被污染程度)。

### 2.5 realized 矛盾標記(07-03 F1 fix (c),同批)

review packet 每 cell 強制 join runtime `settings/edge_estimates.json` 同 key(`strategy::symbol` top-level,方向側用 side-cell 對映):
```
realized_cell_ev_bps, realized_cell_n,
counterfactual_vs_realized_gap_bps = avg_net_conservative − realized_cell_ev_bps,
realized_contradiction = (realized_cell_n ≥ 10) ∧ (realized_cell_ev_bps < 0) ∧ (gap > 50)
```
`realized_contradiction=true` 的 cell 不得進 `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE`,改標 `EXECUTION_REALISM_SUSPECT` 送 L1(見 §3)。

### 2.6 驗收判準(對 fix plan P1-2 驗收行的具體化)

- **A1**:對任意 outcome row,`cost_bps ≥ max(11.0, 同 cell(symbol)90d taker 實現成本 p75×1.3 或其 fallback)`——單元測試以 synthetic fills fixture 直接斷言;
- **A2**:回填 overlay 覆蓋率 100%(所有 attempt_id 可 join;不可 join 者列 `unmatched` 清單並計數);
- **A3**:重跑 review 後,packet 含 `cost_model_version` 分布統計與 `candidacy_flipped_by_cost_model` 計數;
- **A4**:MIT 驗證面(owner 鏈 PM→QC→E1→MIT):抽 10 cell 人工復算 cost_bps 與 PG 分位一致(±0.1bps)。

**假設與失效模式**:(i) 假設 demo taker slippage 分布可代理被擋信號的假想執行成本——若被擋信號集中在 demo 從未成交過的 symbol/時段(流動性更差),p75 仍可能低估,fallback 鏈 3 的 TOML tier(上至 30bps)提供第二道底;(ii) 假設 90d 窗口平穩——regime shift 下自動滾動重算緩解但有 ≤24h 滯後;(iii) funding 快照缺失時 1bps/crossing 為武斷保守常數,horizon ≤ 240m 下影響有界(≤2 crossings)。

---

## 3. P2-7 bounded probe evidence ladder 重設計

### 3.1 現行機制與功效診斷(FACT + 復算)

| 項 | 錨點 | 值 |
|---|---|---|
| 自動禁用門檻 | `rust/openclaw_engine/src/demo_learning_lane.rs:43` | `min_failed_outcomes_to_disable = 2` |
| 禁用規則 | `demo_learning_lane.rs:581-585` | `n ≥ 2 ∧ (avg < 0 ∨ net_positive_pct < 50)` → disable |
| probe 預算 | plan candidate `max_probe_orders`(生產先例 = 2;`demo_learning_lane_writer.rs:802,856`)+ 簽署上限 `demo_learning_lane.rs:856` | per-envelope 簽署 cap |
| 預算語義 | `demo_learning_lane.rs:531-537` | admitted 計數為 ledger 全史累計(跨 envelope 累加,續簽提高 max 即恢復額度)|

復算(σ=200bps 保守規劃值,60m markout;一律單側 α=0.05 除另註明):
- **n=2 對 Δ=75bps 檢定功效 = 13.3%**(單側;雙側 1.96 口徑 = 7.6%,與 07-03 F3 一致)。
- **拒真率(gate 雙向體檢)**:真 cushion +30bps 的 cell 被現行規則在 n=2 誤殺機率 ≈ **41.6%**(P(x̄₂<0|μ=30));真 +75bps 也有 **29.8%**。漏放側:μ=−30 時不禁用機率同樣 ≈ 41.6%。**該規則在 ±75bps 效應量下兩個方向都接近擲硬幣,是負淨貢獻 gate 的教科書樣本**(誤殺正 edge 期望損失 ≈ 0.3–0.4 × cell 年化貢獻;避免虧損側因 demo cap 954 USDT + P1/P2 SL 本已有界)。

### 3.2 Ladder 設計(每級 n / 效應量 / 功效 / 判準)

核心思路:**probe 樣本檢定的不是「edge 是否存在」(σ=200 下 n=2 永遠不夠),而是「反事實假設與真實執行的配對差」(配對消去市場噪音,σ_d 只剩執行噪音)**。edge 本身的確認交給累積樣本與既有 L3 gate。

| 級 | 名稱 | n(per cell) | 檢定對象 | 效應量假設 | 功效(復算) | 判準 |
|---|---|---|---|---|---|---|
| **L0** | 篩選(零 probe) | n_cf ≥ 30 counterfactual rows | 排序 + BH-FDR(§4) | claimed cushion Δ_i = avg_net_conservative | n/a(排序層) | 保守成本(§2)+ `realized_contradiction=false` + BH pass → 才可提名 probe |
| **L1** | 執行實證(配對) | **n_fill ≥ 8**(有效成交數;提交數另計 fill_rate) | 配對差 D_j = realized_fill_net_j − matched_markout_net_j(同 attempt_id、同 horizon) | σ_d ≈ 40bps(執行噪音:fill-price gap + entry delay ≤5min 漂移;**假設,待首批數據重估**) | 偵測 |D̄|=50bps:**97%**;30bps:**68%**(n=8,單側) | ① fill_rate ≥ 60%(PostOnly touch 判準,2026-04-20 QC 協議);② D̄ 的 90% CI 上界 > −30bps(執行不比反事實差 30bps 以上);任一 fail → cell 標 `EXECUTION_REALISM_BROKEN`,其 counterfactual 證據全量降級 |
| **L2** | 淨 edge 確認(累積) | **n_fill ≥ 44** 累積 | 單側 t:mean(realized_net) > 0 | Δ=75bps(headline claim 量級)、σ=200 | **80%**(n=44=⌈((1.645+0.8416)·200/75)²⌉;若 cell 樣本 s_i 實測 ≈120,n_req 降至 16) | per-cell 自適應 n_req = ⌈((z_{.05}+z_{.20})·s_i/Δ_i)²⌉,floor 20 / cap 60;cap 打穿 → PARK(現節奏不可檢定) |
| **L3** | promotion(不動) | edge_estimates `min_oos_n ≥ 30` OOS | 既有 WF 90/30 + PSR/DSR/bootstrap gate | — | — | **live fail-closed 腿零鬆動**(D5 裁決);probe fills 經 decision_outcomes 自然流入估計器 |

**早停語義**:L1/L2 期間僅允許 **futility 早停**(見 §3.3 新禁用規則)——futility-only stopping 不膨脹 type-I error,故 L2 單次終檢無需 alpha-spending;禁止「提前看到正得夠好就宣布通過」(效力側早停必致膨脹)。

**σ_d 假設的失效模式(誠實聲明)**:配對增益成立的前提是同 attempt_id 有真 fill 與 matched markout 可配。若 probe 大量不成交(fill_rate 低),配對樣本退化、功效回落到非配對水平——此時 L1 的 fill_rate gate 本身就是結論(執行假設不成立),lane 不應繼續燒 probe 預算。當前 FACT:strict scan 34,574 rows 零 candidate-matched fill(07-03 審計),σ_d=40 純屬先驗,**首批 L1 數據到手後必須重估並回寫本表**。

### 3.3 Rust 自動禁用規則重設計(E1 spec)

`demo_learning_lane.rs:581-585` 改為 UCB-futility 規則:

```
disable ⇔ n ≥ 8 ∧ ( x̄ + z_{0.90}·s/√n < 0 )        # z_0.90 = 1.282,s = 樣本標準差(ddof=1)
```

復算(σ=200):真 μ=+30bps 誤殺率 **4.4%**(vs 現行 41.6%);真 μ=−100 捕殺率 55%、μ=−50 捕殺率 28%(捕殺不足由預算 cap 與 envelope 到期兜底,方向安全)。配套:
- `AdmissionConfig.min_failed_outcomes_to_disable` 默認 2→**8**(validate 範圍 1..=20 不需改);
- 需在 `summarize_side_cell_runtime_state` 增算 s(現只算 avg,`:544-555`);n<8 期間僅受預算/cooldown/notional cap 約束(風險containment 本就不靠統計規則,cap 不變);
- `min_outcome_net_positive_pct` 腿(`:583`)刪除或設 0.0 停用——n<20 下比例判準比均值判準更噪。

### 3.4 與 12h TTL / refresh 節奏相容性

- 證據累積介質 = append-only ledger,`:531-537` 累計語義天然**跨 envelope 窗口持續**;envelope 過期只凍結新 probe,不清空已積證據 → ladder 與 TTL 重設計(07-03 F4 殘留:TTL ≥ 2×p95 refresh cycle)解耦,互不阻塞。
- 吞吐帳(每 cell):per-envelope `max_probe_orders=2`、TTL 12h → 4 probes/day → L1(n=8)≈ 2 天、L2(n=44)≈ 11 天;**建議**簽署面把 `max_authorized_probe_orders` 設為 ladder 累積目標(L1 提名=8、L2 續簽=44)而非 2,單筆 notional cap 相應收緊使 envelope 總風險額度不變(cap_total 954 USDT 不動,per-order = cap_total/n)——n 增大同時單筆風險線性縮小,風險中性;此為簽署參數建議,**需 operator 在 bounded auth CLI 簽署時拍板**(`bounded_probe_operator_authorization_cli.py`,TTL≤24h 約束不變)。
- 若維持 2/envelope:L2 需 ~22 個續簽窗口,在 IMPL-B drift gate 生效(docs/codex 豁免)後人工介入成本已大幅下降,但仍建議至少 L1 段提高到 8/envelope。

---

## 4. P2-8 best-of-K 多重比較控制

### 4.1 選擇面盤點(K 的來源,FACT)

| 選擇面 | 錨點 | K |
|---|---|---|
| review 排序 + top-16 | `outcome_review.py:340-357,:492`(`top_side_cells[:16]`) | K₁ = 有 n≥3 的 side-cells(07-03 時點 ≈43) |
| false-negative 立案排序 | `false_negative_evidence_floor_ranking.py:282-304`(tier bonus 字典序) | 同上 |
| horizon 掃描 | `horizon_specific_sealed_replay.py`(60/240m…,`best_horizon_minutes` 取 best) | K₂ = cells × H(H=掃描 horizon 數) |
| sealed 確認 gate | `horizon_specific_sealed_replay.py:267-331` | 僅點估計 floor(sample≥100、avg>floor、hit>floor),**無 K 記錄、無 deflation、與選擇同窗** |

Null 期望最大值復算:E[max_K x̄_k] ≈ σ·√(2lnK)/√n̄。K=43、n̄=6:**≈224bps**;n̄=18:**≈129bps**;K=120(43 cells×~3 horizons):≈253bps。→ headline「top cushion 75bps」「sealed 31.87bps@240m」全部落在純噪音期望之內,**現行證據面對「零 edge 宇宙」不可區分**。

### 4.2 控制方案(三層,嵌入 promotion 證據面)

**(a) K 登記(無條件,先行)**:所有 packet(review/ranking/sealed/false-negative)強制新增
```
selection_universe: { n_side_cells, n_horizons, K_effective = n_cells_tested × n_horizons,
                      selection_metric: "wrongful_block_score" | "best_net_bps" | ... }
```
無此欄位的 packet 不得作為 operator review 輸入(fail-closed on missing K)。

**(b) 候選清單面 — BH-FDR(q=0.10)**:對每個 n_i≥3 的 (cell,horizon) 計單側 p_i = P(T_{n_i−1} > x̄_i/(s_i/√n_i))(t 分布,ddof=1);BH step-up:排序 p_(1)≤…≤p_(m),通過集 = {i ≤ k*},k* = max{k: p_(k) ≤ k·q/m}。`review_candidate` 資格 = 現行三閾值 ∧ **BH pass**。horizon 維度納入同一 family(m = cells×horizons),不另做 within-cell Bonferroni(避免雙重懲罰)。**誠實預期**:以當前樣本(median n=6, σ≈200)幾乎必然零通過——這是正確結果;lane 的 probe 提名改由 L0 排序(exploration 用途,語言上禁用「false-negative 證據」措辭,改「exploration candidate」)承接,BH pass 才允許「false-negative candidate」敘事。
**方法選擇理由**:cells 間收益相關(共同市場因子)→ Bonferroni 過嚴且我們的目標是控制「立案清單的假發現率」而非 FWER;BH 在 PRDS(正相依)下仍有效(Benjamini–Yekutieli 條件),適配。

**(c) headline 面 — sign-flip 選擇檢定(White's Reality Check 最簡體)**:對「best cushion / best avg net」類 headline,以 B=1000 次 within-cell 符號翻轉(H0: 各 cell median net = 0,分布對稱假設)重算 max-over-K 統計量,報
```
p_selection = #{ b: max_K(x̄*_b) ≥ observed_best } / B
```
packet 併列 `expected_max_under_null_bps = σ̂_pooled·√(2lnK)/√n̄`(解析式 sanity 對照)。headline 引用規則:`p_selection ≥ 0.05` 時任何 packet/TODO/報告不得以「edge/cushion 證據」語言呈現 best 數字,只可作 exploration 排序。**分布對稱假設失效模式**:crypto 收益右/左偏 → sign-flip null 略偏;可用 within-cell 重抽樣(centered bootstrap)替代,E1 實作二選一,packet 記錄方法名。
**不採 DSR 的理由(此面)**:DSR 需 SR 量綱與 trials 方差估計,本 lane 統計量是 cell 均值非 Sharpe;sign-flip 直接對選擇統計量建 null,假設更少、實作 ≈40 行 numpy。edge_estimates 側已有 PSR/DSR gate(L3),不重複。

**(d) sealed 確認面 — 時間切分 holdout**:sealed replay gate 增加:選擇窗(exit_ts < T_split)決定 best cell/horizon,確認窗(≥ T_split,禁止參與選擇)獨立驗證:`n_confirm ≥ max(20, 0.3·n_select)` ∧ `avg_net_confirm > 0` ∧ `avg_net_confirm ≥ 0.3 × avg_net_select`(退化係數 <0.3 = 過擬合警報,對齊 IS/OOS 退化曲線判準)。現行 gates(`:267-331`)保留,新增三條 gate 進同一 `gates[]` 結構。

### 4.3 嵌入 promotion 證據鏈

`L0(BH) → L1(配對) → L2(單側 t, futility-only) → L3(WF+PSR/DSR)`:L2 對 §3 ladder 是單一 pre-registered cell 的單次終檢(選擇已在 L0 被 BH 控制、probe 提名即預註冊),故 L2 不再重複 BH;若同時有 >5 個 cell 併行走 L2,對 L2 家族另跑一次 BH(q=0.10)。此結構把多重比較控制點放在「進 ladder 的門」而非「每一層都罰」,避免功效被重複校正吃光。

---

## 5. F7 markout exit 無 max-delay 上界 → censored 語義

### 5.1 現行(FACT)

- `outcome_writer.py:286`:`exit_obs = _first_price_at_or_after(observations, exit_target_ts_ms)` —— **未傳 `max_delay_ms`**(函數 `:193-205` 本身支援);觀測斷供時,出場價可落在 horizon 後任意遠,60m markout 實際量測 N 小時後的價格,horizon 語義破壞且無任何標記。
- Entry 側有界(`:281` max_entry_delay 5min)但失敗路徑 `:283-284` 靜默 `continue`——row 永不落盤、每輪 refresh 無限重試(`_existing_outcome_attempt_ids` 永不含它),既是計算浪費也是觀測黑洞。

### 5.2 Spec

```
ProbeOutcomeConfig 新增:
  max_exit_delay_ms: int = min(0.25 × horizon_ms, 30·60_000),floor 5·60_000
  # 60m horizon → 15min;240m → 30min(cap)。理由:延遲 ≤ 25% horizon 時
  # 實際量測窗畸變有界且 exit_ts_ms 已落盤可事後加權;超過即語義不可救。

出場:exit_obs = _first_price_at_or_after(observations, exit_target_ts_ms,
                                          max_delay_ms=cfg.max_exit_delay_ms)
  exit_obs is None ∧ now_ms > exit_target + max_exit_delay
    → 寫 censored row:{ censored: true, censor_reason: "exit_observation_gap",
        gross_bps: null, realized_net_bps: null, exit_price: null,
        last_observation_ts_ms: <該 symbol 最後觀測>, ... 其餘欄位照常 }
  exit_obs is None ∧ now_ms ≤ 上述時限 → continue(尚未到期,下輪再試——唯一合法重試窗)

入場:entry 觀測缺失 ∧ now_ms > event_ts + max_entry_delay + horizon + max_exit_delay
    → 寫 censored row,censor_reason: "entry_observation_gap"

正常 row 補欄位:exit_delay_ms = exit_ts_ms − exit_target_ts_ms(觀測品質可觀測面)
```

**消費側(outcome_review.py)**:censored rows 不進 nets(均值/比例/檢定分母),但計 `censored_count` / `censored_pct` per cell;`censored_pct > 30%` → cell 標 `OBSERVATION_GAP_SUSPECT`,不得為 review candidate(資料品質先於統計顯著)。**censored ≠ 丟棄**的統計理由:silent drop 造成的偏差方向不可知(觀測斷供與波動事件相關 → 缺失非隨機,MNAR);顯式 censoring 保留分母資訊,讓資料品質缺陷可被看見並闔上「無限重試」漏洞(censored row 的 attempt_id 進 existing set,終結重掃)。

---

## 6. 與 P1-1 over-gate 修復(IMPL-A/IMPL-B @ 262596c69)的交互

| 交互點 | 內容 | 含義/約束 |
|---|---|---|
| **feed 恢復 × 污染速率** | IMPL-A 刪 pre-risk guard 後 cost_gate reject feed 恢復(事故前 1.9萬–12.9萬筆/日,設計正本 §1.1;現 ledger 已 472MB/P1-10) | §2 成本模型 + §5 censoring **必須在 soak 重新武裝前 land**,否則以十萬/日速率繼續積累 `legacy_optimistic_v0` row,回填面無限膨脹。與 D9 rotation 同批:rotation 切段後 review 需跨段讀或 overlay 針對「活躍窗」即可(建議 retention 14d 內全量回填,更早只標記不回填) |
| **writer cache stat-失效** | IMPL-A §1.7:cron 外部 append 的 `probe_outcome`/`side_cell_disabled` row 經 stat 失效重讀進 Rust 消費鏈 | §3.3 新禁用規則(n≥8 UCB)生效路徑依賴此機制——cron 寫的 outcome 會真實觸發 auto-disable;n=2→8 + 規則變更需與 IMPL-A 同一部署世代上線,**否則舊規則(n=2 擲硬幣)會在 feed 恢復後第一時間誤殺 cell** |
| **配對 L1 的 fill 來源** | E4 F8:`candidate_matched_demo_fills` 無 in-repo producer(fills→證據鏈斷點);probe order_link_id 帶獨特前綴(設計 §1.1.3) | L1 需要 **fill-backed probe outcome writer**(join `trading.fills` by order_link_id 前綴):新 record_type `probe_fill_outcome` 或 `probe_outcome` + `outcome_source:"demo_fill_backed"`。**建議**:權威行沿用 `probe_outcome`(fill-backed 優先,admitted-未成交到期 → censored `censor_reason:"probe_unfilled"`,同時解 E4 F14「admitted-but-unfilled 同權」);配對影子行用新 type `probe_markout_shadow`(Rust `:546` 只認 `probe_outcome`,shadow 不進禁用鏈,零 Rust 改動) |
| **IMPL-B drift gate × ladder 節奏** | docs/tests/.codex 豁免使 envelope 續簽不再被無關 commit 殺死(v710-738 拒真率 100% 的判準側已解) | §3.4 吞吐帳的「續簽人工成本」假設依賴 IMPL-B 生效(D1 重啟後 v739 實走);ladder 本身與 TTL 解耦(append-only 累積),TTL 重設計(F4 殘留)可後續獨立進行 |
| **世代可觀測** | P0-1 boot/build SHA 落 PG/持久 log | 所有新 packet 增 `engine_build_sha` / `source_head` 欄位,證據跨代可追溯(D1 重啟前後對照的前置) |
| **live 邊界** | D5:cost_edge demo+live 雙 arm、live fail-closed 不鬆動 | 本設計全部落在 demo 學習面;L3 gate、live cost_gate、五 gate 授權鏈零觸碰 |

---

## 7. 測試用例(E1 直接照做)

**P1-2(Python,`tests/helper_scripts/` 慣例)**
1. `test_cost_fallback_chain`:fixture 給 symbol A(n=25 fills,q75=14.0)/symbol B(n=5)/quantile artifact 缺失三態,斷言 `cost_model_source` 依次 = symbol_q75 / global_q75 / toml_tier,且全部 ≥ 11.0 floor。
2. `test_cost_ge_realized_quantile`(驗收 A1 直測):synthetic fills 已知分位 → 斷言 `cost_bps ≥ 2×(5.5+q75)×1.3`(±1e-9)。
3. `test_backfill_overlay_flip`:legacy row net=+5(cost 4.0),overlay cost=25.0 → review 後該 cell `review_candidate=false` ∧ `candidacy_flipped_by_cost_model=true`。
4. `test_realized_contradiction_flag`:edge_estimates fixture cell EV=−16.76/n=18 vs counterfactual avg +75 → `realized_contradiction=true` ∧ status=`EXECUTION_REALISM_SUSPECT`。
5. `test_funding_crossing_count`:horizon 240m 跨 1 個 8h 結算 instant → funding_crossings=1;60m 不跨 → 0。

**P2-7(Rust `demo_learning_lane.rs` 單元測試 + Python)**
6. `test_disable_ucb_rule`:n=7 全負 → 不禁用;n=8、x̄=−120、s=200 → UCB=−29.4<0 → 禁用;n=8、x̄=−80、s=200 → UCB=+10.6 → 不禁用。
7. `test_disable_false_kill_simulation`(Python,seeded MC 10k):μ=+30,σ=200,n=8 → 誤殺率 ∈ [3%,6%](復算 4.4%)。
8. `test_paired_l1_gap`:8 對 (fill,shadow) 固定差值 → 配對 CI 判準命中/未命中兩例;fill_rate 7/12=58% → L1 fail。
9. `test_ladder_budget_cumulative`:envelope1 max=8 admit 8 → exhausted;envelope2 max=44 → remaining=36(`:531-537` 語義釘死)。

**P2-8(Python)**
10. `test_bh_fdr_vector`:p=[0.001,0.008,0.039,0.041,0.042,0.06,0.5...m=15],q=0.10 → 通過集合 = 已知答案(手算 fixture)。
11. `test_signflip_selection`:seeded RNG;全 null(μ=0)80 cells → p_selection 分布近似均勻(10 次重複中 ≥8 次 p>0.05);單 cell 注入 μ=5σ/√n → p_selection<0.01。
12. `test_selection_universe_required`:packet 缺 `selection_universe` → 消費端 fail-closed(拒讀並報 reason)。
13. `test_holdout_split_gates`:T_split fixture,確認窗 n=25、avg=0.2×選擇窗 → `decay_gate` fail。

**F7(Python)**
14. `test_exit_censored`:觀測序列在 exit_target 後 40min 才有價(horizon 60m,max_exit_delay 15min)→ row `censored=true`、reason=`exit_observation_gap`、realized_net_bps=null、attempt_id 進 existing set(下輪不重算)。
15. `test_exit_within_delay`:延遲 10min → 正常 row + `exit_delay_ms=600000`。
16. `test_entry_gap_censored`:entry 觀測永缺、時限已過 → censored reason=`entry_observation_gap`。
17. `test_censored_excluded_from_stats`:cell 10 row 中 4 censored → outcome_count=6、censored_pct=40 → `OBSERVATION_GAP_SUSPECT` ∧ 非 candidate。

---

## 8. 建議與裁決

- **P1-2**:REVISE 定稿如 §2 —— 改動集中 `outcome_writer.py`(成本函數+schema)+ 每日分位 artifact + review overlay,無 Rust 改動,無 live 面。**先行落地(soak 重武裝前)**。
- **P2-7**:REVISE 定稿如 §3 —— ladder L0-L3 + Rust 禁用規則 UCB 化(n 2→8);簽署參數(per-envelope probe 數 8/44、單筆 cap 等比縮)**需 operator 拍板**。
- **P2-8**:REVISE 定稿如 §4 —— K 登記無條件先行;BH 進候選面;sign-flip 進 headline 面;holdout 進 sealed 面。
- **F7**:REVISE 定稿如 §5 —— censored 標記,不丟棄。
- **翻案條件(REJECT-of-evidence 的最小推翻證據)**:若修正後體系下仍有 cell 以保守成本過 BH(q=0.10)、L1 配對 gap CI 含 0、且 L2 n≥44 單側 t p<0.05,則該 cell 的 false-negative 敘事成立,cost gate 對該 cell 屬真誤殺,應按 D5 demo advisory 腿進入 gate 調參議程。
- 黑名單體檢:本設計無 HMM/GARCH/VPIN/rolling-max 觸碰;年化不涉;所有檢定單側/雙側與 ddof 已標明。

**severity/confidence 總表**:P1-2 HIGH/high(機制 FACT+PG 實測);P2-7 MEDIUM/high(功效數學 FACT,σ 為假設);P2-8 MEDIUM/high(E[max] 解析+慣例);F7 MEDIUM/high(代碼 FACT);交互面 INFERENCE/med(IMPL-A/B 未實走,v739 後復核)。

---
QC · 2026-07-04 · read-only(無代碼/config/runtime 變更;本報告+memory 落盤為僅有寫入)

---

# Addendum(2026-07-04 post-window 復核 · QC 親證)

> 觸發:07-04 16:40 運維窗口完成(engine rebuild 自 `3a050b60` 重啟 PID 3159871 / SSOT 遷 `/home/ncyu/BybitOpenClaw/var/openclaw` / PG 調參 / crontab 7 條 pin `3a050b60`)。本 addendum 以窗口後 runtime 親測更新正文,正文結構與四項 spec 結論不變;下列 FACT 全部為 2026-07-04 17:00+ 讀取。

## A. 錨點驗證帳(全部重讀 source 後裁決)

| 正文錨點 | 驗證 | 備註 |
|---|---|---|
| `outcome_writer.py:26`(cost_bps=4.0)/`:193-205`(max_delay_ms 支援)/`:275`(entry=signal price)/`:278-284`(entry 靜默 continue)/`:286`(exit 未傳 max_delay)/`:291-293`(gross/net) | ✅ 全中 | — |
| `outcome_refresh.py:253`(`--outcome-cost-bps` default 4.0) | ✅ | 窗口後 cron 亦未覆蓋(見 §B) |
| `outcome_review.py:208-232`(avg_net/cushion)/`:340-357`(排序)/`:492`(top 16) | ✅ | — |
| `false_negative_evidence_floor_ranking.py:282-304`(`_rank_score` tier bonus) | ✅ | — |
| **`horizon_specific_sealed_replay.py` 路徑修正** | ⚠️ errata | 正確全路徑 = `helper_scripts/research/alpha_discovery_throughput/horizon_specific_sealed_replay.py`(非 cost_gate_learning_lane/);`:210` friction fallback 4.0 ✅、gates 塊 `:267-331` ✅ |
| `demo_learning_lane.rs:43`(n=2)/`:55`(1..=20)/`:525-537`(admitted 全史累計)/`:546`(只認 `probe_outcome`)/`:556`(net_positive_pct)/`:581-585`(禁用規則)/`:856`(auth cap) | ✅ | 禁用規則實際為 `avg < cfg.min_avg_net_bps`(default 0.0,`:36,:45`)——正文「avg<0」在默認值下語義等價 |
| `demo_learning_lane_writer.rs:802,856`(max_probe_orders=2) | ✅ | — |
| `risk_config_demo.toml:398`(SM=1.3)/`:409-427`([[slippage.tiers]] 1–30bps) | ✅ | — |

## B. 運維窗口後新現實(正文 §6 交互表狀態升級)

1. **IMPL-A/IMPL-B + `d0eeafb41` 已上線(INFERENCE→FACT)**:engine binary mtime 2026-07-04 16:40、PID 3159871 自 `3a050b60` rebuild。正文 §6 各「IMPL-A/B 未實走」條件句全部轉為現在時。
2. **4.0 污染以 ~2.3萬行/日速率進行中(FACT)**:crontab `:27` lane cron(`OPENCLAW_COST_GATE_LEARNING_APPEND_OUTCOMES=1`)未帶 `--outcome-cost-bps` 覆蓋;遷移後 ledger 今日(07-04)新增 `blocked_signal_outcome` **23,193 行,100% cost_bps=4.0**(另 probe_admission_decision 29,894 行)。**P1-2 每延後一天 ≈ +2.3萬筆 legacy_optimistic 回填負擔**——正文「soak 重武裝前先 land」升級為「即刻優先」。
3. **n=2→8 有乾淨落地窗口(FACT,重要)**:全 ledger 400,312 行掃描,`probe_outcome` 與 `side_cell_disabled` 記錄數 = **0**(cron `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0`)。現行 n=2 擲硬幣規則從未觸發過;v739 世代已部署但首批 probe outcome 尚未產生 → §3.3 規則變更可在零歷史包袱下落地,順序約束由「與 IMPL-A 同世代部署」改述為「**趕在首批 probe_outcome 落 ledger 之前**」。
4. **Ledger lineage 分裂證據(影響 §2.4 回填)**:遷移檔與 /tmp 遺留副本同頭(首行 attempt_id 相同,確為延續);但本檔 07-04 前 blocked outcome 累計 = 173,775,vs 07-03 審計在 /tmp 量測 195,684 → **少 ~22k 行**,與 E4 F3「runtime 雙 plan 檔分裂實錘」一致(或中途發生過 compaction)。**§2.4 spec 強化(E1 必做)**:backfill overlay 的輸入 = 所有 ledger 檔案 lineage 的 **UNION**(遷移檔 + `/tmp/openclaw/.../probe_ledger.jsonl` 遺留副本 + 若 E4 F3 盤點出第二 data-dir 檔),按 `(attempt_id, record_type)` 去重,artifact 記 per-file 行數與交集/差集統計;若三檔互有獨占行,獨占行照常回填並標 `lineage_source`。
5. **D9 rotation 未實施**:新路徑仍為 464MB 單檔(400,312 行)。正文「retention 14d 內全量回填、更早只標記」建議與 D9(50MB/14d/增量讀)相容,維持。
6. **每日 blocked outcome 分布(burst 型)**:06-29=72,839 / 07-03=48,964 / 07-04=23,193——回填規模主要由三個 burst 日主導,overlay 一次性腳本按日分片可斷點續跑。

## C. 成本校準 errata(數字復算,正文 §1/§2.2 引用值更正)

正文引用的 PG 校準快照**不可復現**,以下為 07-04 親測(SQL 附後):

| 量 | 正文值 | 復算值(FACT) | 裁決 |
|---|---|---|---|
| taker fee p50 | 5.5 bps | **5.5 bps** ✅ | 維持 |
| taker \|slip\| 樣本量 | 「90d n≈1.5k;ETHUSDT n=213、ATOMUSDT n=66」 | **全表僅 178 行**(全部 demo/taker,06-18~07-04;ETHUSDT 17、BTCUSDT 16、ATOMUSDT 12、FILUSDT 9) | ❌ 任何窗口/filter 均無法產出正文 n;正文快照來源不明,以本表為準 |
| 全體 p50/p75/p90/p95 | 2.5–3.3 / 11.3–13.7 / 33–34 / 54–56 | **4.28 / 24.97 / 54.08 / 90.64** | ❌ 更正;分布右偏更重 |
| per-symbol p75 | BTC 0.88 / ETH 1.71 / ATOM 14.07 / FIL 26.34 | **BTC 0.74 / ETH 2.23 / ATOM 13.18 / FIL 50.92** | ⚠️ BTC/ETH/ATOM 同量級,FIL 差 ~2×(樣本 9 行,兩值都不穩) |

```sql
-- 分位 artifact 生產腳本必須內嵌本查詢(E1 spec):
WITH t AS (
  SELECT symbol, abs(slippage_bps) AS s
  FROM trading.fills
  WHERE engine_mode IN ('demo','live_demo') AND liquidity_role='taker'
    AND ts > now() - interval '90 days' AND slippage_bps IS NOT NULL)
SELECT symbol, count(*) AS n,
       percentile_cont(0.5)  WITHIN GROUP (ORDER BY s) AS q50,
       percentile_cont(0.75) WITHIN GROUP (ORDER BY s) AS q75,
       percentile_cont(0.9)  WITHIN GROUP (ORDER BY s) AS q90
FROM t GROUP BY ROLLUP(symbol);
```

**對 spec 的影響(方向不變,結論更強)**:
- launch 時**零 symbol 過 n≥20 門檻** → 全部 cell 走 `global_q75` fallback → `cost_bps_conservative ≈ 2×(5.5+24.97)×1.3 ≈ 79.2 bps RT`(比正文 ATOM 示例 51bps 更保守;4.0 平價假設的低估倍率由 ~13× 上修到 **~20×**)。per-symbol 分支隨 v739 fill 積累自動激活,機制不改。
- p75 選擇論證更強:n=178 下 p95 由 ~9 個尾點決定,估計自身噪音不可用;p75(~45 個點以上)仍可用。
- artifact 增加欄位:`n_total` 與 `thin_sample: (n_total<100)`(純觀測標記,不加新乘數旋鈕——SM=1.3 已覆蓋估計不確定性,避免死參數)。
- **funding crossing 上界 errata**:`fundingInterval` per-symbol 可低至 1h → 240m horizon 最多 **4** 次 crossing(正文「≤2」僅對 8h interval 成立);1bps/crossing fallback 下上界 4bps,仍有界,公式不改。

## D. 驗收增補(併入正文 §2.6)

- **A5**:分位 artifact 含 `n_total`/`asof`/`thin_sample`,消費端在 artifact 缺失或 `asof` 超 48h 時走 fallback 鏈第 3 級(正文已定)並在 outcome row 記 `cost_model_source="toml_tier"`;
- **A6**(lineage):backfill overlay 對三檔 union 的覆蓋率 100%,artifact 頭部記 per-file 行數與 `(attempt_id,record_type)` 交集統計;07-03 195,684 vs 本檔 173,775 的 ~22k 差額必須在盤點中定位歸屬(E4 F3 聯動)。

## E. severity/confidence 更新

P1-2 HIGH/high(污染進行中 2.3萬/日,FACT);P2-7 MEDIUM/**high↑**(乾淨落地窗口 FACT:零 probe_outcome 歷史);P2-8 MEDIUM/high(不變);F7 MEDIUM/high(不變);§6 交互面 **FACT**(IMPL-A/B 已上線);正文 PG 校準快照 **RETRACTED**,以 §C 復算值替代(方法選擇與公式全部維持)。

---
QC · 2026-07-04 post-window addendum · read-only(Linux 全程 SELECT/讀檔;寫入僅本報告+memory)

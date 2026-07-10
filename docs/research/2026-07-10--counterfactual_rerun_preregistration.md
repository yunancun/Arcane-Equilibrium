# 反事實重跑預註冊(Pre-Registration)— 71,207「正 edge < threshold」母集 + 33 GROSS_EDGE_POSITIVE cells

**日期**:2026-07-10
**作者角色**:QC(Quantitative Consultant,外部量化顧問)
**任務來源**:R3 修復包 charter WP-A 第 3 點(operator 2026-07-10 授權;主研判 session 轉達)
**性質**:**預註冊判準文檔**。本檔必須在反事實重跑執行之前落檔(這是 pre-registration 的意義)。重跑執行方(E1)與審查方在看到重跑統計量之後,不得修改本檔任何判準、門檻或判定式;任何偏離按 §10 處理。
**上游證據**(判準動機,不在此重述):
- `docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-09--profit-diagnosis-stage2-qc.md`(F1 偽複製復核、conservative_v1 ≈ 4× E[cost]、O3 規格草案)
- `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-07-09--profit-evidence-readonly-probe.md`(§C 拒因統計、F1/F7)
- 現行 lane 代碼正本:`helper_scripts/research/cost_gate_learning_lane/{outcome_review,outcome_writer,cost_model,evidence_stats,slippage_quantile_artifact}.py`

---

## 0. 預註冊聲明與凍結錨(freeze anchors)

### 0.1 凍結錨(2026-07-10 QC 親查,全部 read-only)

| 錨 | 值 |
|---|---|
| Mac repo HEAD(撰檔時) | `a35ec287b` |
| Review artifact | `~/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json`,`generated_at_utc=2026-07-09T21:31:15.577558+00:00` |
| Review artifact sha256 | `299751f291fdf6bc2f92ad6dc6bcdebe922bf4b382f4526b6a64349575e3249a` |
| Review artifact 關鍵計數 | `side_cell_count=76`;`diagnosis_counts={BLOCK_CONFIRMED_AFTER_COST:28, FALSE_NEGATIVE_CANDIDATE_AFTER_COST:1, GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT:33, POSITIVE_EDGE_UNSTABLE_AFTER_COST:1, SAMPLE_INSUFFICIENT:13}`;`blocked_signal_outcome_count=951,456`;`selection_universe={n_side_cells:76, n_horizons:2, k_effective:152}` |
| Ledger 檔數 | 35 個 `probe_ledger.*.jsonl`(輪轉檔;重跑 artifact 必記逐檔 sha256 清單) |
| 母集 A 驗證計數 | 71,207(§1.1 SQL 逐字重現;ts 範圍 2026-06-20 02:19:01+02 → 2026-07-08 03:39:59+02) |
| Horizon 宇宙 | {60, 240} 分鐘(review artifact `selection_universe.n_horizons=2` + `top_side_cells[].horizon_minutes` 實查) |

### 0.2 資料窺探申報(pre-registration hygiene)

撰寫本檔時 QC 只讀取了**結構 metadata**:row counts、distinct minute/day 基數、cell 身分(strategy/symbol/side)、horizon 宇宙、artifact hash。**未讀取任何去重後樣本的 outcome 統計量**(mean / std / t / p / 正率)。本檔引用的 outcome 級數字(σ≈200bps、E[slip]≈6bps、slippage 分位 p50 −0.02 / p10 −37.79 等)全部來自 2026-07-09 已發布的 Stage 1/2 報告——即偽複製污染態下的公開數字,僅用於 σ 假設與 power 誠實揭露(§3.3),不構成對去重後結果的預看。

### 0.3 與 charter WP-A 條目對應

| charter 條目 | 本檔節 |
|---|---|
| WP-A.1 per-(side_cell, entry_ts_ms) 去重 + effective-n 檢定;raw outcome_count 不進 eligibility/t/BH | §2、§3 |
| WP-A.2 成本雙軌(E[cost] 主判 + conservative tail 並列) | §6 |
| WP-A.3 預註冊判準先落檔 | 本檔全文 |
| WP-A.4 重跑 → 新 verdict artifact(翻正清單或誤殺假說落錘) | §8、§9 |
| WP-A.6 PM/E3 checklist 前置 distinct-entry n_eff 檢定 | §3(E1-E3 即該檢定的正本定義) |

---

## 1. 母集定義(凍結)

### 1.1 母集 A —「正 edge < threshold」拒單行(n=71,207)

**來源**:`trading.risk_verdicts` JOIN `learning.decision_features`(經 `context_id`)。**凍結 SQL**(重跑第 0 步必逐字執行並比對計數):

```sql
SELECT df.strategy_name, r.symbol, df.side, r.context_id, r.ts, r.reason
FROM trading.risk_verdicts r
JOIN learning.decision_features df ON df.context_id = r.context_id
WHERE r.ts >= '2026-06-15T00:00:00Z' AND r.ts < '2026-07-09T00:00:00Z'
  AND r.verdict = 'Rejected'
  AND r.reason ~ 'cost_gate\(JS-demo\): edge=[0-9.]+bps < threshold'
```

- **計數斷言**:總行數必須 = **71,207**(2026-07-10 QC 實查;soak isolation 自 06-29 起擋 ordinary demo entry,07-08 後無新增,母集天然凍結)。偏差 >0 → deviation log + 停,回 PM,不得續跑。
- **join 守恆斷言**:join 後總行數 = join 前 `risk_verdicts` 行數(2026-07-10 實查兩者相等,1:1);不等 → 停。
- **side 映射**:`df.side` smallint `1→Buy`、`-1→Sell`;`side_cell_key = strategy_name|SYMBOL|Side`(與 `outcome_writer._side_cell_key` 一致)。

**Cell 清冊(凍結,2026-07-10 實查)**:

| side_cell_key | raw rows | symbol 級 distinct minutes / UTC days(注) |
|---|---|---|
| `ma_crossover\|ETHUSDT\|Sell` | 59,597 | ETHUSDT 合計 578 min / 8 days |
| `bb_reversion\|FILUSDT\|Buy` | 3,556 | 2 min / 2 days |
| `grid_trading\|APTUSDT\|Sell` | 2,375 | 1,387 min / 8 days |
| `bb_reversion\|ETHUSDT\|Buy` | 2,317 | (含於 ETHUSDT 合計) |
| `bb_reversion\|ARBUSDT\|Buy` | 2,270 | 1 min / 1 day |
| `grid_trading\|ETHUSDT\|Sell` | 1,092 | (含於 ETHUSDT 合計) |

注:minute/day 基數在 ETHUSDT 只有 symbol 級合計(三個 ETH cell 未拆);重跑 artifact 必記 per-cell `n_dedup` 與 distinct days。**預註冊時已知的結構預判**:`bb_reversion|FILUSDT|Buy`(n_dedup=2)與 `bb_reversion|ARBUSDT|Buy`(n_dedup=1)去重後**必然** SAMPLE_INSUFFICIENT——此事實在重跑前已由 metadata 確定,列於此以防重跑後出現「新發現」敘事。

### 1.2 母集 B — 33 個 `GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT` cells

**凍結方式 = 分類規則 + 輸入身分**(review JSON 只保留 top 16 cells,完整 33-cell 清單須重新枚舉):

- 分類規則:`outcome_review._diagnose_cost_gate_escape` 在 **conservative_v1 成本 + 現行閾值 {min_outcomes=3, min_avg_net=0.0, min_net_positive=60%}** 下判 `GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT` 的 cells。
- 輸入身分:§0.1 釘死的 review artifact(sha256 `299751f2…`)所用的同一 ledger 窗(14d,35 檔輪轉 ledger)。
- **重跑第 0 步**:用凍結輸入重新枚舉該 33 cells,把 `side_cell_key` 清單寫入 artifact;**枚舉數 ≠ 33 → deviation log + 停**。
- 母集 A ∩ B 允許重疊(同 cell 兩條路徑進入);cell 級統計在 A∪B 聯集 family 中只計一次。

---

## 2. 樣本單位與去重

1. **觀測單位** = `(side_cell_key, entry_minute, horizon_minutes)`,其中 `entry_minute = floor(entry_ts_ms / 60_000)`。分鐘級量化理由:信號秒級重發(F1 成因),同一分鐘內的多個 entry_ts_ms 共享同一根 1m bar 的價格路徑,屬同一觀測。
2. **去重規則**:同 `(cell, entry_minute, horizon)` 的多行 → 保留 1 行。代表行 = `attempt_id` 字典序最小(確定性)。
3. **複本一致性檢查**:若複本間 `realized_net_bps` 或 `gross_bps` 不一致(容差 1e-9 bps)→ 該 cell 標 `DATA_INTEGRITY_SUSPECT`,排除出檢定 family 並在 artifact 列明細;**不得靜默取平均**。
4. **raw outcome_count 作廢**:任何 eligibility / t / BH-FDR 計算不得使用去重前行數(charter WP-A.1)。artifact 保留 raw count 僅作審計對照欄。
5. **n_dedup** = 去重後行數 per (cell, horizon)。
6. **n_eff = 非重疊窗子樣本大小**(主推斷樣本):按 `entry_minute` 升序 greedy earliest-first——選首個 entry;此後僅選 `entry_minute ≥ 上一入選 entry_minute + horizon_minutes` 的 entry。確定性、無自由參數。
   - 理由:horizon 窗重疊的兩個 markout 共享價格路徑,自相關 ≈ (1 − Δt/h),將 t 統計膨脹;day-cluster 只吸收日級共同衝擊,不足以修復窗內重疊。非重疊化在樣本層消滅此自相關;殘餘日級相依交給 §4 cluster-SE。雙保險各管一層。
7. **敏感性欄(僅列報,不參與判定)**:全 n_dedup 樣本 + day-cluster SE 的平行統計,供比較非重疊化的資訊損失。

### 2.1 母集 A 的 outcome 取得

- 優先:既有 ledger `blocked_signal_outcome` 行,按 `(side_cell_key, entry_minute, horizon)` 匹配。
- ledger 無覆蓋的拒單行(母集 A 窗 19 天 > ledger 14 天窗):從 1m klines 補算 markout——`entry = 拒單 ts 後首根 1m bar open(嚴格 > ts,leak-free)`、`exit = entry + horizon 後首根 bar open`、`gross_bps` 按 side 簽名。censored 語義沿用 lane 現行規則(觀測斷供寫 censored row,計入分母不入檢定)。
- 兩源同鍵衝突時取 ledger 行(其價格觀測鏈已經審計);artifact 記 `obs_source ∈ {ledger, kline_backfill}` 欄與各自佔比。

---

## 3. Eligibility 門檻(n_eff 檢定;數值與理由)

Cell(× horizon)進入統計檢定 family 需**全部**滿足:

| # | 條件 | 門檻 |
|---|---|---|
| E1 | n_eff(非重疊去重樣本) | **≥ 30** |
| E2 | distinct UTC days(入選 entry) | **≥ 5** |
| E3 | top-day share(單一 UTC 日佔入選 entry 比) | **≤ 50%** |
| E4 | censored_pct | ≤ 30%(承 F7 現行規則) |
| E5 | 成本欄完整性 | 全部樣本可用 §6 雙軌重算;不可重算的 legacy 行剔除且剔除後仍過 E1-E4 |

### 3.1 E1 = 30 的理由

1. **既定翻案條件**:2026-07-09 QC Stage 2 已預先聲明 F1 翻案條件 =「去重後 effective-n ≥ 30 且 FDR 仍過」;本檔沿用,不事後放寬。
2. **厚尾下 t 近似的最低可信樣本**:demo returns JB 必拒 normality;n < 30 的 t p-value 在厚尾下無意義(walk-forward skill 反模式「N<30 但稱 p<0.05」)。
3. **lane 歷史教訓**:n ≥ 30 / cell 是 2026-04-24 audit 起的既定門檻;現行 `min_outcomes_per_side_cell=3` 是探索排序用,從未足以立案。

### 3.2 E2 = 5 天、E3 = 50% 的理由

- F1 的根本形態是**單日 episode regime-bet**(2 個 entry、同一小時、NEAR +1.6% pop)。天數下限直接打擊該形態。
- cluster-SE 的自由度 = G − 1(G = 天數);G < 5 時 df ≤ 3,t 臨界值 ≥ 2.35,推斷實際不可用。G ≥ 5 是 cluster 推斷的最低可用點。
- E3 防「名義 5 天、實質單日主導」:top-day ≤ 50% 保證至少兩天各承載實質樣本。

### 3.3 Power 誠實揭露(非門檻,披露義務)

以污染態 pooled σ ≈ 200bps(outcome_review 註記;去重後 σ 待重跑實測)計:

- n_eff = 30 → SE ≈ 36.5bps;單側 α=0.05、power 80% 的可偵測效應 ≈ **93bps**(normal 近似;cluster df=7 時 t_crit=1.895,更粗)。
- 偵測 50bps 需 n_eff ≈ 99;偵測 20bps 需 n_eff ≈ 620。
- **含義**:E1-E3 是**候選資格下限**,不是統計證明。20-50bps 級真 edge 在 n_eff=30-100 大多不顯著 → 落 `SAMPLE_INSUFFICIENT` 或檢定不過是**預期行為,不構成「誤殺已排除」的證據**。本 lane 輸出的上限本來就是 bounded probe 候選(真 fills 由 probe 收集),不是終局證明。
- 重跑 artifact 必記 σ_dedup(去重後 pooled std)並按其更新 power 表;**E1-E5 門檻不因 σ_dedup 移動**(門檻凍結,power 表只是解讀輔助)。

### 3.4 不過門檻的處理

任一 E1-E5 fail → 該 cell 判 `SAMPLE_INSUFFICIENT_AFTER_DEDUP`:**禁止方向性結論**——既不得寫「誤殺排除」,也不得寫「誤殺證據」;唯一合法行動建議 = 繼續累積去重樣本或設計定向 probe。

---

## 4. 統計推斷 — cluster-SE by day

對每個過 E1-E5 的 (cell, horizon),在非重疊子樣本上:

- 主統計量:x̄ = mean(net_E)(net_E 定義見 §6.1)。
- **Cluster 定義**:g = entry 的 UTC 日曆日;G = distinct days。
- **CR1 cluster-robust 變異數**(均值估計):
  `V = [G/(G−1)] × (1/n²) × Σ_g S_g²`,其中 `S_g = Σ_{i∈g} (x_i − x̄)`
- 檢定:`t = x̄ / sqrt(V)`,**df = G − 1**,單側 p = P(T_{G−1} > t),H0: μ ≤ 0,H1: μ > 0。
- 退化保護:G < 2 → p = None(E2 已擋,防繞雙記);V = 0 → 樣本全同值,標 `DATA_INTEGRITY_SUSPECT`(去重逃逸嫌疑),不給 p。
- 實作:標準庫可行(`evidence_stats._student_t_sf` 已有 t 上尾;E1 新增 `cluster_one_sided_t_p_value` 純函數 + 單元測試;不引 scipy,lane 離線性不變)。
- 舊 `one_sided_t_p_value`(IID,raw rows)的輸出在本重跑 artifact 中作廢,只保留為對照欄 `p_iid_raw_deprecated`。

---

## 5. 多重比較 — BH-FDR(去重後)

1. **Family 定義**:通過 E1-E5 的全部 (cell, horizon),母集 A ∪ B 聯集,**一次 BH step-up**;m = family 大小,artifact 登記。
2. **q = 0.10**(承現行 lane `fdr_q`;不因結果調整)。
3. p 值 = §4 cluster-robust 單側 p。**raw-row p 值不得進入 BH**。
4. **fail-closed 方向**:BH 只撤不扶(承 `_apply_bh_fdr` 語義)——過保守閾值但 BH 不過 → 候選資格撤下。
5. **K 登記(無條件)**:selection universe = 全體被掃描 cells(76 + 母集 A 6 cells,含未過 eligibility 者)× horizon 宇宙 {60, 240};artifact 記 `k_effective`。
6. **Headline sign-flip selection test 照跑**(承 P2-8(c)):cell_nets 用去重後非重疊樣本,B=1000、seed=20260704(現行);`p_selection ≥ 0.05` → 任何 headline 數字禁用 edge/cushion 證據語言。
7. **Horizon 宇宙凍結**:{60, 240}。新增 horizon = 擴 K = 必須重新預註冊(v2)。

---

## 6. 成本雙軌(E[cost] 主判 + conservative tail 並列)

### 6.1 主判軌:E[cost](期望成本)

```
cost_E_rt(symbol, h) = 2 × fee_taker + 2 × E[slip_leg](symbol) + funding_drag(h)
net_E(i) = gross_bps(i) − cost_E_rt(symbol_i, h_i)
```

| 成分 | 定義 | 凍結值/來源 |
|---|---|---|
| fee_taker | Bybit VIP0 taker 單腿,不打折,不假設 maker 成交(touchability 33/33 no-touch 教訓) | 5.5 bps |
| E[slip_leg](symbol) | `E[abs(slippage_bps)]`,`trading.fills` 90d 窗、`engine_mode IN ('demo','live_demo')`、`liquidity_role='taker'`、per-symbol n ≥ 20 | artifact 新欄 `mean_abs`(E1 擴 `slippage_quantile_artifact.py`) |
| fallback 鏈 | symbol(n≥20)→ global → TOML tier(最保守檔 30bps) | 承 `cost_model._resolve_slippage_bps` 結構 |
| funding_drag(h) | `funding_crossing_count(h) × 1.0 bps`(per-symbol fundingInterval 即時查,不假設普適 8h) | 承 `cost_model.py` 現行 |
| 硬 floor | `cost_E_rt ≥ 11.0 bps`(純 taker fee 雙腿;手續費不打折) | 承 `FEE_FLOOR_BPS` |
| artifact 新鮮度 | ≤ 48h | 承現行 |

- **用 E[abs(slip)] 而非 signed mean 的理由**:`E[abs(x)] ≥ abs(E[x])`,把有利滑點也計為成本 → 溫和保守偏置、單一數字、與現行分位 artifact 同源同窗。artifact 同時記 signed mean 供透明對照。
- **明確排除 1.3 safety multiplier**:SM 是 gate 的設計參數,不是誤殺**量測**的成分。量測必須用期望成本,否則重演 conservative_v1(92.3bps ≈ 4× 實測 E[cost] ≈ 23bps)把量測面直接打殘的錯誤。「成本假設保守」(QC 硬約束 #4)在本軌的體現 = fee 不打折、不假設 maker、|slip| 偏置、thin-sample fallback 取最保守檔、funding drag 全計——不是對期望值乘 4。

### 6.2 尾部敏感性欄:conservative tail(CVaR 類,並列輸出,不作主判)

```
cost_tail_rt(symbol, h) = 2 × fee_taker + 2 × CVaR90_leg(symbol) + funding_drag(h)
net_tail(i) = gross_bps(i) − cost_tail_rt(symbol_i, h_i)
```

- `CVaR90_leg(symbol) = E[abs(slip) | abs(slip) ≥ q90]`(同窗同 filter;E1 在 artifact 加 `cvar90` 欄)。
- CVaR90 不可得時 fallback = q90,artifact 記 `tail_metric="q90_fallback"`。
- **每 cell 並列輸出** `mean_net_tail`、`net_tail_positive_pct`。**作用** = bounded probe 的 loss budget / sizing 輸入與敘事上限;**不改變**候選資格判定(否則等於把 conservative_v1 換皮重生,再次雙向失真)。
- **第三對照欄**:conservative_v1 淨值照舊列出,並保留 `candidacy_flipped_by_cost_model` 計數(新舊成本模型下分類翻轉的 cells)——gate 雙向體檢的連續性證據。

### 6.3 gross 語義與現實性檢查

- `gross_bps` = fill-at-signal 假設下的反事實 markout,沿用 lane 現行 leak-free 定義(entry 觀測 = 信號後首個可用觀測;超延遲寫 censored)。
- **F1 fix(c) realized 矛盾檢查保留**:同 cell realized EV(edge_estimates,n≥10)為負且 counterfactual avg − realized EV > 50bps → `EXECUTION_REALISM_SUSPECT`,候選資格否決(fill-at-signal 高估執行的既定防線)。

---

## 7. Regime 標註規則(leak-free,可解釋指標)

**Per entry**(全部指標用 entry 所在 UTC 日 D 的 **D−1 日終**資料;1d klines,`market.klines timeframe='1d'`):

| 標籤 | 定義 | bucket |
|---|---|---|
| `btc_trend_30d` | sign(BTC close(D−1) − SMA30(D−1)) | {up, down} |
| `btc_ret_7d` | BTC 7 日收盤報酬(至 D−1) | {bear ≤ −5%, flat (−5%, +5%), bull ≥ +5%} |
| `sym_vol_30d` | symbol 30d realized vol(1d log returns,至 D−1)在自身 2yr 歷史的分位 | {low < q33, mid, high > q67} |

**Per cell**(artifact 必列):

- 各 bucket 佔比 + 指標值 + 計算窗口(承 skill 最低標準;禁黑名單模型做 regime 偵測——HMM/GARCH 等,唯一正本 `math-model-audit`)。
- `single_regime_episode` flag:distinct days < 5 **或** top-day > 50%(與 E2/E3 同義雙記,防繞)**或**(btc_trend 單一方向 且 distinct days ≤ 2)。
- `bull_heavy` flag:`btc_ret_7d = bull` 佔比 > 60% → 依 CLAUDE.md Alpha Evidence Governance,該 cell 任何正結果標 **regime-bet / learning-only**,不得作 promotion proof。

---

## 8. 判定式(晉升 / 否決;機械可裁)

### 8.1 Per cell(通過 E1-E5 後)

```
PROMOTE_BOUNDED_PROBE_CANDIDATE ⇔ P1 ∧ P2 ∧ P3 ∧ P4 ∧ P5
  P1: mean_net_E > 0                      (E[cost] 主判軌)
  P2: net_E_positive_pct ≥ 60%            (承現行 review 閾值)
  P3: cluster-robust 單側 p 過 BH-FDR(q=0.10, §5 family)
  P4: ¬EXECUTION_REALISM_SUSPECT ∧ ¬DATA_INTEGRITY_SUSPECT
  P5: ¬single_regime_episode
附則:bull_heavy 不否決 P1-P5,但輸出必附 regime-bet / learning-only 標籤,
     且 dispatch 排序置於非 bull_heavy 候選之後。

VETO(該 cell 誤殺假說落錘)⇔ E1-E5 全過 ∧ (¬P1 ∨ ¬P3)
  status = BLOCK_CONFIRMED_UNDER_EXPECTED_COST

SAMPLE_INSUFFICIENT_AFTER_DEDUP ⇔ E1-E5 任一 fail
  無方向性結論(§3.4)。
```

### 8.2 全域裁決語言(artifact 頂層,三態,擇一)

1. **≥ 1 PROMOTE** →「翻正 cell 清單」:逐 cell 附 n_eff / G / p / BH 裁決 / net_E / net_tail 欄 / regime 標註;下一步上限 = bounded demo probe 的 operator review。`order_authority=NOT_GRANTED`、`promotion_evidence=false` 不變。
2. **0 PROMOTE 且 ≥ 1 cell 完成檢定** →「誤殺假說在 E[cost] 主判下落錘;over-gate 淨貢獻按檢定 cells 收口」+ 逐 cell VETO 明細。
3. **全部 SAMPLE_INSUFFICIENT** →「母集去重後無可檢定 cell;誤殺問題維持 UNDECIDED」。**不得**寫成落錘——樣本不足不是無罪證明,也不是有罪證明。

### 8.3 翻案條件(QC 硬約束 #8:REJECT/VETO 必附)

- 任何 VETO cell:未來累積**新的去重樣本**使 (n_eff, G, top-day) 重新過 E1-E3,且 P1-P5 全過 → 自動恢復候選資格,無需人工翻案流程。
- 任何 SAMPLE_INSUFFICIENT cell:同上,樣本補足即自動重審。
- **判準本身**的修改(門檻、公式、family 定義)→ 必須發布本檔 v2 並 supersede,不得原地改。

### 8.4 Gate 雙向計價輸出(artifact 必列)

1. 檢定 cells 的 `Σ n_eff × mean_net_E`(誤殺期望損失**上界**,附 fill-at-signal 現實性 caveat——真 fill 有滑點與 queue 損耗,此數只可作 upper bound 敘事)。
2. VETO cells 對 gate 淨貢獻的正向確認(避免虧損項)。
3. `candidacy_flipped_by_cost_model` 新舊成本對照計數(§6.2 第三欄)。

---

## 9. 產出 artifact 契約與邊界

- 輸出:research artifact JSON(建議 `schema_version="counterfactual_rerun_prereg_v1"`)+ 報告;**必含**:本檔路徑 + 本檔進 repo 後的 git SHA、母集凍結驗證(A 計數=71,207;B 枚舉=33)、ledger 逐檔 sha256、per-cell 全欄(n_raw/n_dedup/n_eff/G/top_day_share/censored_pct/x̄/V/p/BH/net_E/net_tail/conservative_v1 對照/regime 標註/obs_source 佔比)、family m、k_effective、q、σ_dedup、更新後 power 表、deviation log(可為空)。
- **邊界**(charter 硬邊界,逐條):PG read-only;不動 runtime cost gate / 風控閾值 / 授權;Cost Gate 不降級;`order_authority=NOT_GRANTED`;`promotion_evidence=false`;demo-only;fail-closed 不鬆動。
- 本重跑結論的**最大效力** = bounded probe 候選榜重排 + F1 裁決記入 TODO(charter WP-A.7)。不構成 live 或 promotion 證據。

## 10. 偏離處理(deviation policy)

1. 任何與本檔不符的計算選擇 = deviation;artifact `deviation_log` 記 what / why / 影響面。
2. 影響判定式、門檻、family 定義或成本公式的偏離 → **停**,回 PM;需重新預註冊(v2,本檔保留供 diff)。
3. 純實作層偏離(如欄名、檔案路徑)記 log 後可續。
4. 探索性分析(pre-reg 外的切片)允許,但輸出必標 `exploratory=true`,不得進入 §8 判定式,不得用候選/證據語言。

---

**QC 落款**:本檔全部門檻與判定式在未見去重後統計量的狀態下凍結(§0.2 申報)。在「σ≈200bps、樣本厚尾、母集高度集中於 ≤8 個 UTC 日」的假設下,§3-§5 的組合(非重疊 n_eff + day-cluster t + BH-FDR)對 F1 型偽複製的假陽性率控制在名義 α 附近;若 σ_dedup 或天數結構顯著偏離上述假設,§3.3 的 power 表更新義務 + §10 偏離政策承接。


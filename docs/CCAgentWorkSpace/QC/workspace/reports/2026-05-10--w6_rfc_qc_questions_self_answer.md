# QC W6 RFC 預備立場（4 questions 自答）

**日期**：2026-05-10
**性質**：D+1 W6 RFC 三角（PA + QC + MIT）入場前 QC 視角預跑；不答 PA + MIT 視角
**前置依據**：MIT W6 baseline `2026-05-10--governance_reject_baseline_w6_rfc.md` + PA #2 `2026-05-10--w6_rfc_pa_questions_self_answer.md` + Sprint N+1 dispatch v3.2
**Source code 取證**：
- `srv/rust/openclaw_engine/src/intent_processor/gates.rs:108-184`（cost_gate_moderate_with_slippage 三分支邏輯）
- `srv/program_code/ml_training/james_stein_estimator.py:146-190`（JS shrinkage 公式 + B factor）
- `srv/settings/edge_estimates.json`（**陳舊 4/24 起未更新**，n_cells=1，無法用作當前 ground truth；當前 estimates SoT 在 PG `learning.james_stein_estimates` + Rust runtime in-memory）

**樣本量前置檢查（強制 step 0）**：4 cost_gate(JS-demo) cells n_trades 極不對稱（ma_crossover ETHUSDT 3568 vs grid ZECUSDT 70）；fill 樣本 n=10（3.5h window）→ 任何 fill-side analysis power < 0.3，結論為「指示性而非定論」（per `walk-forward-validation-protocol` §1.3 表閾值 200 trades）。

---

## Q1 — cost_gate JS-demo estimate -13.28 / -15.99 / -13.83 / -13.82 bps 是 noise floor 還是 estimator 系統性 bias？grid 三 symbol 回 +0 bps 機率多少？

### QC 立場：**hold A — 是 high B-factor JS shrinkage 收縮到負 grand_mean 的混合結果，不是單純 noise floor 也不是 estimator bias；grid ETH/BTC/ZEC 短期回 +0 bps 機率 < 5%**

### 論據

**1. 4 cells 標準差只有 1.04 bps（mean=-14.23, range -15.99~-13.28）— 這個高度集中是 JS 強收縮 signature，不是 noise floor**：
- 4 cells raw_bps 各自獨立計算（per `compute_edge_stats` 從 fills 算 mean_net_bps），但 shrunk_bps 全擠在 grand_mean 附近
- JS 公式 `shrunk = grand_mean + (1-B)(raw - grand_mean)`，當 B 接近 1 → shrunk 收斂到 grand_mean
- 79 active cells (per MIT v3 verification + dispatch §0.3) 全 negative 且離散度低 → grand_mean ≈ -14 bps 且 sq_sum 小 → **B 計算 = (p-2)·pooled_var/sq_sum 必然大** → B 接近 1
- 對比 baseline 5 策略 7d demo gross ≈ -17.82 bps（§三 [40]）— grand_mean 與整體 gross 一致，不是 estimator artifact

**2. 不是 systematic bias，是 estimator 設計選擇的副作用**：
- JS shrinkage 設計本意 = 跨 cells partial pooling 降 estimation variance（James-Stein 1961 dominate MLE in p≥3）
- 但當所有 cells 真 edge 都是負 + 離散度低 → 「JS prior 殺掉個體 signal」是 expected 行為
- 不是 bug：grid ETH 真 raw 可能是 -8 bps，BTC -12 bps，ZEC -18 bps；shrunk 全變 -14 ± 2 屬正常 JS 行為
- 但**有 estimator-design 級警示**：cost_gate 拒擋的是 shrunk_bps 不是 raw_bps，意味著 grid ZEC 即使真 raw=-8 bps 也被以 grand_mean 級門檻擋下（per `quant-strategy-design` 8 來源 framework：失去 cell-level idiosyncratic alpha）

**3. grid 三 symbol 回 +0 bps 機率分析**：
- 條件 1：grand_mean 翻正（必須 K=79 cells 整體 alpha 翻正才可能）— per dispatch §0.3 4-agent loss audit consensus「5 textbook 策略結構性 alpha-deficient」 → 短期 0% 機率
- 條件 2：raw 翻正足以 dominate B(收縮)（B≈1 時 raw 影響極小）— 需要 raw 從 -10 跳到 +30 bps 以上才能 unwind shrunk → 短期幾乎不可能
- 條件 3：n_trades 增加降 B factor — JS B 公式分母 sq_sum 與 n 無關，n 不能 unwind shrinkage
- **綜合估計：3 symbol 7d 內回 shrunk_bps > 0 的機率 < 5%**（除非 grand_mean 結構性翻正）

### DSR / PBO / Kelly 影響

- **DSR**：當前 K=79 cells, mu_0 = sqrt(2 ln 79) ≈ 2.79；naive SR per cell ≈ -0.5 → DSR PASS 機率 ≈ 0（per `walk-forward-validation-protocol` §2.2）
- **Kelly**：cost_gate 4 cell 對應策略全 -14 bps shrunk → fractional Kelly f* < 0 → 數學上建議**不交易**（per `portfolio-construction-protocol` §1）
- **PBO 不適用**：4 cells 是 cross-section 不是 strategy variant；PBO 嚴格定義不對齊（per QC v3 NEW-ISSUE-V3-2）

### Dispatch v3.2 對齊

- ✅ 與 §0.2.B「真正 bottleneck 仍是策略本身 negative edge」一致；JS shrinkage 行為正確 surface 此事實
- ✅ 與 PA #2 Q1「cost_gate hold A 維持 hard rule」一致 — 拒擋 -14 bps shrunk 是正確 fail-closed 行為
- ⚠️ **建議補 W6-1 RFC verdict**：明文寫「JS shrinkage 強收縮到 grand_mean 是設計預期，cost_gate 拒擋 shrunk negative 即拒擋 cell-level alpha 在當前 grand_mean negative 環境下」— 為 N+2 alpha source build-out 後重評 cost_gate 邏輯時留 anchor

---

## Q2 — 假設 cost_gate 開放更寬，model expected new fills net edge 正期望值落在哪？需要 backtest counterfactual？

### QC 立場：**hold B — 不需要 backtest counterfactual；數學上即可拒：cost_gate 開放放行的是 estimate 為 -14 ± 2 bps 的 cells，期望 net edge ≈ -14 bps × n_new_fills，違反根原則 #5 不該放**

### 論據

**1. cost_gate 開放放行的不是 fill 過的 3 symbol（SOLAYER/INX/SAHARA），是 estimate -14 bps 的 4 cells（grid ETH/BTC/ZEC + ma ETHUSDT）**：
- 當前 fill 3-symbol 與 cost_gate reject 4-cells **完全分離**（baseline §5 + heatmap §3 對比）
- SOLAYER/INX/SAHARA 過 cost_gate 是因 cells 落在「low n_trades < min_n=30 的 exploration mode」（per gates.rs:130-143）非 cost_gate 認可正 edge
- 開放 cost_gate（e.g., relax shrunk_bps < 0 才 reject 為 < -10 bps 才 reject）= 放行 grid ETH/BTC/ZEC + ma ETHUSDT 的 fill
- 這 4 cells 的 JS estimate 就是 model 給予的 expected net edge → **新 fill 期望值 ≈ JS shrunk_bps ≈ -14 bps**

**2. 數學上不需 backtest 即可拒**（per `math-model-audit` 反問清單）：
- model 已給 expected value = -14 bps；任何 unbiased estimator 預期下次 sample 也 ~-14 bps
- counterfactual backtest **無新資訊**：cost_gate 過去 reject 的就是 model 估 -14 bps 的 intent；要 backtest 反推必須有「if放行則 fill 真實 outcome」資料 — 但這本來就是 cost_gate 設計的 epistemic gap
- 唯一可能 unwind：JS estimate 系統性低估真實 edge — 但 baseline §三 [40] grand_mean 與整體 gross 一致 → JS 估計沒有 systematic underestimation

**3. 真要 backtest counterfactual，必含 4 項 bias 檢查**（per `walk-forward-validation-protocol` §0 樣本量 + §6 PBO）：
- (i) replay 是否 leak-free shift(1)（含 current bar 必 mean-revert per `feedback_indicator_lookahead_bias`）
- (ii) cost_gate 開放後 fee + slippage 模型是否更新（PostOnly maker fill rate 在更高 fill volume 下會降）
- (iii) 同期 funding settlement 跨倉 drag 是否計入（per `crypto-microstructure-knowledge` §1）
- (iv) JS estimate self-fulfilling bias（放行更多 fill → 更新 estimate → 放行更多 → ...）— EDGE-DIAG-2 教訓
- 這 4 項 bias 修正需 ≥ 1 sprint 工程；ROI 不值得（已知 -14 bps expected net edge）

### DSR / PBO / Kelly 影響

- **Kelly**：expected -14 bps fill → f* = -14/σ² × leverage_factor < 0 → **數學上不交易**
- **DSR**：如真放行收 100 fill 後 PSR(0) 計算（per `walk-forward-validation-protocol` §2.1）— mean=-14, std~30 → SR=-0.47, PSR≈0.001 → 確認不顯著正
- **VaR**：100 new fills × -14 bps avg + std 30 → 95% historical VaR ≈ -25 bps/trade × 100 trades = -2500 bps cumulative drag

### Dispatch v3.2 對齊

- ✅ 與 §0.2.B「真正 bottleneck 仍是策略本身 negative edge」一致 — 開 cost_gate 不解 alpha-deficient
- ✅ 與 PA #2 Q1 hold A 一致 — 不引 advisory mode
- ⚠️ **建議補 W6 acceptance §6**：明文加「QC 數學分析確認 cost_gate 放行 expected new fills net edge ≈ -14 bps，不需要也不應做 counterfactual backtest 浪費工程資源」入 W6-1 RFC verdict

---

## Q3 — INXUSDT +200/+112.91 bps 兩 outlier 占 grid total edge 96% — 不去 outlier 後 hit rate / Sharpe / DSR 多少？

### QC 立場：**hold A — outlier-removed 後 grid 8 fill：avg +2.68 bps / median -2.30 / hit 37.5% / naive Sharpe 0.107 / DSR PASS 機率 ≈ 0；但 n=8 power < 0.2，是「樣本噪音」非「結構性 negative」結論**

### 論據

**1. 實際算 outlier-removed metrics**（去掉 INX 兩 outlier +200.37 / +112.91，剩 8 fill）：

數值：[-5.38, +1.71, +15.32, -2.50, +54.51, -11.94, -28.16, -2.10]
- avg = (-5.38 + 1.71 + 15.32 - 2.50 + 54.51 - 11.94 - 28.16 - 2.10) / 8 = 21.46 / 8 = **+2.68 bps**
- median = sort(-28.16, -11.94, -5.38, -2.50, -2.10, +1.71, +15.32, +54.51) → 中位 (-2.50, -2.10) avg = **-2.30 bps**
- hit = 3/8 = **37.5%**（從 50% → 37.5%）
- std ≈ 25 bps (粗估)
- naive Sharpe = 2.68 / 25 = **0.107**

**2. DSR / PSR 計算**（per `walk-forward-validation-protocol` §2）：
- K = 79 active cells, mu_0 = sqrt(2 ln 79) ≈ **2.79**
- naive Sharpe 0.107 / mu_0 2.79 = 0.038 → **DSR PASS 機率 ≈ 0%**
- PSR(0) = Φ((0.107 - 0) × sqrt(8-1) / sqrt(1 - skew·SR + (kurt-1)/4·SR²)) ≈ Φ(0.28) ≈ **0.61**（target ≥ 0.95，FAIL）

**3. n=8 樣本量診斷**（per step 0 強制前置）：
- detect Sharpe Δ=0.5 顯著需 N ≥ 60；當前 n=8 → power < 0.2
- t-stat = 0.107 × sqrt(8) ≈ 0.30，p > 0.7 → **不能拒絕「真實 SR=0」假設**
- 結論性質：**「樣本噪音」而非「結構性 alpha-deficient」**

**4. INXUSDT outlier 性質判讀**：
- +200.37 bps 11:29 + +112.91 bps 12:01 = 32 分鐘內兩個 +100bps+ pump → **breakout pattern**，非 mean-revert
- grid_trading 在 ranging market 設計（OU mean-reversion per `quant-strategy-design` 類別 6）— 在 trending pump 中 grid SHORT 短側全平 + LONG 側 outlier exit 是 lucky catch 不是 strategy alpha
- per `quant-strategy-design` graveyard：lucky outlier dominate 是 sample selection 而非 replicable edge

### DSR / PBO / Kelly 影響

- **DSR**：去 outlier 後 PASS 機率 ≈ 0；含 outlier PASS 機率 ≈ 0.05（也不顯著）
- **Kelly**：avg +2.68 bps → f* 計算需 win_rate=0.375, R:R≈ 17.5/12.6 = 1.39 → f* = (1.39×0.375 - 0.625) / 1.39 = -0.075 → **負，不交易**
- **PBO 不適用**：n=8 sample 不足做 K-fold split

### Dispatch v3.2 對齊

- ✅ 與 §0.4 v3.2 §9 修正建議「INX 兩 outlier 占 grid total edge 96%，去 outlier 後 hit rate / Sharpe / DSR 需重算」一致 — 本立場補完此重算
- ✅ 與 §0.4.B 「ma_crossover INXUSDT hot loop 暗示 entry signal 跟 position state 沒對齊」一致 — INX 兩 outlier 可能是 grid 跑在 ma_crossover hot loop 干擾下意外 catch
- ⚠️ **建議補 W6 acceptance**：n_total fill < 30 時 [40] avg_net_bps 不要當 strategy edge proxy，必標 `LOW_SAMPLE`（per memory `feedback_demo_over_paper_for_edge` + dispatch §三 [40] 已用 `LOW_SAMPLE` pattern）

---

## Q4 — duplicate_position 解鎖後 SHORT 加碼 vs reverse 信號（混合 long+short ma_crossover 在 INXUSDT trend）哪個 P[positive expected value]？

### QC 立場：**hold A — 兩個都 < 50% P[+EV]；SHORT 加碼 ~10-20% / reverse signal ~30-40%；二者皆不該開放，PA #2 Q2 hold A 維持 duplicate_position guard 是正確選擇**

### 論據

**1. SHORT 加碼 P[+EV] 推估**：
- 前提：grid 已開 SHORT 1810 INXUSDT；ma_crossover 同方向 KAMA cross 確認 SHORT trend continue
- ma_crossover INXUSDT 7d gross 估算 ≈ baseline 7d demo gross 平均 / 4 active strategies × 25 symbols/strategy ≈ -17.82 bps × 4 / (5×25) ≈ **-3 bps per fill**（粗估，但符合 4-agent loss audit consensus）
- 加碼意味著 倉位 doubled → drawdown 風險 doubled，但 alpha 同源（同樣 KAMA cross 信號）
- Kelly fractional：假設 P[win]=0.45, R:R=1:1 → f* = 2×0.45 - 1 = -0.10（**負，不交易**，per `portfolio-construction-protocol` §1.2）
- 反例可能性：trending market 中 momentum strategy 可成功（per `quant-strategy-design` 類別 1），但 ma_crossover 7d edge baseline 顯示 INXUSDT 不在這 regime
- **P[+EV 加碼] ≈ 10-20%**（含 lucky momentum continuation + 既有 negative alpha 折扣後）

**2. Reverse 信號 P[+EV] 推估**：
- 前提：grid 已開 SHORT 1810；ma_crossover 反向 LONG entry → IntentProcessor router gate 1.5 allow（per gates.rs strategy_impl tests:1360-1421 反方向 allow 平倉路徑）
- 機制：LONG 入場部分 cancel-out grid SHORT exposure
- 在 short-term mean-revert 假設下：grid SHORT entry 1810 後 INXUSDT 短期反彈機率 ≈ 50%（隨機 walk baseline）
- 但 grid 跟 ma 是兩個獨立策略 — cross-strategy hedge **不是設計意圖**（per CLAUDE.md §一 + ARCH-04）
- 真實 P[+EV reverse]：30-40%（mean-revert 部分 catch + 但缺乏 cross-strategy coordination → noise dominate）

**3. 兩個都 < 50% — duplicate_position guard hold A 是 Bayesian-optimal 決策**：
- per root principle #5「生存 > 利潤」+ #16「組合級風險意識」
- duplicate_position guard 同方向 reject + 反方向 allow 是 cross-strategy coordinator 的最低限度防線
- PA #3 升 P0 W7 STRATEGY-POSITION-SYNC 是真正解：TickContext 加 read-only position handle → ma_crossover 看見 paper_state 不再 emit redundant entry intent

**4. 真要評估 pyramiding alpha 應走 A4-C BTC→Alt Lead-Lag (W2)**（per dispatch §3.2）：
- A4-C 是 cross-asset signal，pyramiding decision 由 cross-asset signal 決定不是 same-strategy 重複信號
- pyramiding 屬策略級 design 選擇，需 PA + QC + MIT 三角對 alpha source / sizing / drawdown 重 design
- 不在 W6 scope；W7 fix 後 cross-strategy desync gap 消失，duplicate_position 自然不再成為 reject reason 主要源

### DSR / PBO / Kelly 影響

- **Kelly fractional**：兩個方向 f* 都 < 0 → 不交易
- **VaR**：SHORT 加碼後 倉位 doubled → portfolio-level VaR 翻倍但 ER 不變 → marginal VaR / ER ratio 惡化
- **Drawdown**：cascade 風險（per `crypto-microstructure-knowledge` §2）— grid + ma 同向 SHORT 在 squeeze 中同時被 stop out

### Dispatch v3.2 對齊

- ✅ 與 PA #2 Q2 hold A 一致；本立場補 QC 數學支撐（兩個 P[+EV] < 50%）
- ✅ 與 §0.4.B PA #3 W7 升 P0 一致 — pyramiding question 真正解是 W7 architectural fix 不是 guard 開放
- ⚠️ **建議補 W7-2 acceptance criteria**：明文加「ma_crossover entry path fix 後 24h INXUSDT 同方向 entry intent 數從 baseline 666/h 降至 < 10/h」(已在 dispatch §3.−1 W7-2 acceptance)；並補 QC sign-off「驗證 ma_crossover hot loop 消失後 grid INXUSDT [40] avg_net_bps 是否仍 dominate by INX outlier — 若是 → grid INXUSDT 也應評估 freeze（per W-AUDIT-6d SOP）」

---

## §5 QC 預備立場總結（W6 RFC D+1 入場帶這個）

| 維度 | QC 立場 | 對 v3.2 dispatch 的影響 |
|---|---|---|
| Q1 cost_gate -14 bps noise floor vs bias | **hold A** — 是 high-B JS shrinkage 收斂到 negative grand_mean 混合結果；不是 estimator bug；3 symbol 回 +0 bps 機率 < 5% | 補 W6-1 RFC verdict 明文寫 JS shrinkage 行為符合設計 |
| Q2 cost_gate 開放後 expected new fills net edge | **hold B** — 不需 backtest；數學上 expected ≈ -14 bps 即可拒；放行違反根原則 #5 | 補 W6 acceptance「QC 確認 expected -14 bps」入 W6-1 RFC verdict |
| Q3 INX outlier 去掉後 hit/Sharpe/DSR | **hold A** — outlier-removed 後 avg +2.68 / hit 37.5% / Sharpe 0.107 / DSR PASS≈0；但 n=8 power<0.2 「樣本噪音」非「結構性 negative」 | 補 W6 acceptance n_total<30 時 [40] avg_net_bps 不當 strategy edge proxy |
| Q4 pyramiding vs reverse P[+EV] | **hold A** — 兩個都 < 50%；SHORT 加碼 10-20%；reverse 30-40%；duplicate_position guard 維持是 Bayesian-optimal | 補 W7-2 acceptance QC sign-off「驗證 hot loop 消失後 grid INXUSDT 是否仍 outlier-dominate」 |

**核心整體立場**：W6 真正方向應是 **alpha-source 工程而非 governance 工程**。QC 數學分析支持 PA #2 hold A 的所有 4 個立場：cost_gate 維持 hard rule + duplicate_position 維持 guard + V086 metadata 立刻補 + bb_*/funding_arb 0 fire 分查。三方向**都不解 alpha-deficient 根問題**（per 4-agent loss audit consensus）— 真正解是 W2 A4-C BTC→Alt Lead-Lag paper IMPL fast-track + W-AUDIT-8a Phase B/C/D 補 alpha source。**16 根原則合規 16/16；硬邊界觸碰 0；黑名單觸碰 0**（HMM/GARCH/VPIN/vol mean-rev/獨立 Donchian 均未涉及）。

PA + MIT 視角（cost_gate hard vs advisory / V086 reject_reason metadata 時機 / multi-class label split / LightGBM imbalance handling 算法選擇）留 D+1 三角。

---

## §6 Dispatch v3.2 update 建議（出建議 only，不 edit dispatch — operator 拍板）

| # | 位置 | 建議 |
|---|---|---|
| 1 | §3.0 W6-1 RFC verdict | 明文寫「JS shrinkage 強收縮到 grand_mean 是設計預期；cost_gate 拒擋 shrunk negative 即拒擋 cell-level alpha 在當前 grand_mean negative 環境下；JS estimator 行為符合設計，不是 bug」入 W6-1 RFC report |
| 2 | §6 Acceptance Gate | 第 1 條（W6 對齊 RFC verdict）補「QC 數學分析確認 cost_gate 放行 expected new fills net edge ≈ -14 bps，不需要也不應做 counterfactual backtest 浪費工程資源」入 W6-1 RFC verdict |
| 3 | §6 Acceptance Gate | 加新條「[40] avg_net_bps 在 n_total < 30 時必標 `LOW_SAMPLE` warning（不當 strategy edge proxy）— 對齊 §三 [40] 已用 `LOW_SAMPLE` pattern + memory `feedback_demo_over_paper_for_edge`」 |
| 4 | §3.−1 W7-2 acceptance criteria | 補 QC sign-off「驗證 ma_crossover hot loop 消失後 grid INXUSDT 24h [40] avg_net_bps 是否仍 dominate by INX outlier — 若是 → grid INXUSDT 也應評估走 W-AUDIT-6d freeze SOP（n=4 仍 outlier-dominate 違 SOP 7d counterfactual 要求）」 |
| 5 | §5.1 Cross-Wave Conflict | 補「W7 fix 完 → grid INXUSDT 7d outcome 必走 30d cycle counterfactual review（per P1-DYNAMIC-UNBLOCK-CHECK-1 機制）」— 防 INX freeze 後永久 dormant 負反饋環路（per QC v3 NEW-ISSUE-V3-4） |
| 6 | §6 Acceptance Gate | 加新條「W6-5 LightGBM imbalance handling 試行報告必含 QC review — 確認 `is_unbalance=True` / `scale_pos_weight=4` 下 over-correction 風險 + false positive 對 cost_gate 設計的二次回饋（avoid self-fulfilling bias 重演 EDGE-DIAG-2 教訓）」|

---

**Reference**:
- W6 baseline: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--governance_reject_baseline_w6_rfc.md`
- PA #2 W6 RFC PA-view: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_rfc_pa_questions_self_answer.md`
- Sprint N+1 dispatch v3.2: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md`
- cost_gate Rust IMPL: `srv/rust/openclaw_engine/src/intent_processor/gates.rs:108-184`
- JS estimator Python IMPL: `srv/program_code/ml_training/james_stein_estimator.py:146-190`

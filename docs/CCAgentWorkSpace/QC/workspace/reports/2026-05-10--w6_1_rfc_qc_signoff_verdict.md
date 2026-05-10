# W6-1 RFC final verdict — QC sign-off

**Date**: 2026-05-10 21:15 UTC
**Verdict**: ✅ **APPROVE-CONDITIONAL** (4 push back items, all minor wording / acceptance gate clarification, 不阻 D+1 升 AMD)
**Reviewer**: QC
**Predecessor**: W6-1 RFC final verdict draft (PA, `2026-05-10--w6_1_rfc_final_verdict_draft.md`)

> **註記 (PM)**：本 verdict 由 QC sub-agent 於 2026-05-10 21:15 UTC inline 完成（task notification a027fc0b），未直寫 .md。PM 從 task notification full content 落到 file 為 governance trail 保存。

---

## §1 4 verdict 對應 QC 立場

### Verdict 1 — cost_gate hard rule 維持，不引 advisory mode → **APPROVE FULL**

從 quant 立場 100% 同意。本 verdict 直接對應 QC W6 RFC 自答 Q2 hold B：cost_gate 開放 expected new fills net edge ≈ -14 bps，數學上即可拒，不需 counterfactual backtest 浪費工程資源。

QC 補充支撐論據：
- **Kelly fractional**：4 cells (grid ETH/BTC/ZEC + ma ETHUSDT) 的 JS shrunk_bps mean=-14.23，σ估 ~30 bps → fractional Kelly f* = (-14.23/30²) × leverage_factor < 0 → **數學上不交易**（per `portfolio-construction-protocol` §1.2）
- **DSR / PSR**：放行 100 fill 後 PSR(0) 計算 mean=-14, std~30 → SR=-0.47, PSR≈0.001 → 確認顯著低於 0
- **VaR**：100 new fills × -14 bps avg + std 30 → 95% historical VaR ≈ -25 bps × 100 = -2500 bps cumulative drag

「16 root principles compliance」原則 #4/#5/#6 引用正確。Rust source `gates.rs:108-184` 三層設計（paper exploration / demo moderate / live fail-closed）QC 獨立讀過確實正確 surface「n_trades < min_n exploration mode 過 / n ≥ min_n 負 JS shrunk hard reject」。

「N+2 重提防線」段落也健康：以 RFC report + AMD 件鎖定，未來想動 cost_gate 必先撤回此 verdict。

### Verdict 2 — JS shrinkage 強收縮到 grand_mean 是設計預期 → **APPROVE FULL**

從 QC math 立場是核心數學 verdict。

QC 補充數學語言（建議 PA AMD 升件時可選擇加入更嚴謹表述）：
- JS 公式：`shrunk = grand_mean + (1 - B)(raw - grand_mean)`，`B = (p-2) · pooled_var / sq_sum`
- 當 79 active cells 全 negative + 離散度低（cells 之間真 edge 接近）→ `sq_sum = Σ(raw_i - grand_mean)²` 必然小 → **B 必然接近 1** → shrunk → grand_mean
- 4 cells shrunk_bps 標準差只有 1.04 bps（mean=-14.23, range -15.99~-13.28）是 high B-factor JS shrinkage signature 的**直接觀測**，不是 estimator bug
- 與 baseline §三 [40] 5 策略 7d demo gross 約 -17.82 bps 一致 → grand_mean -14 bps 不是 estimator artifact，是真實 strategy gross 的 partial-pooled view

「N+2 重新評估 JS estimator 的觸發點 = grand_mean 結構性翻正後」也是 **量化正確**：
- 唯一可 unwind shrinkage 的途徑是 grand_mean 本身翻正（拉動 shrunk target）
- 增加 n_trades 不能 unwind（B 公式分母 sq_sum 與 n 無關）
- 改變單一 cell raw 也不能 unwind（B 接近 1 時 raw 影響極小）

對應 QC 過往 memory 教訓「**Grand mean 統計有效性門檻**：p ≥ 3 個 cells 才能信任 JS 收縮目標」（2026-04-24 line 127）— 當前 79 cells 已遠超 p ≥ 3 門檻，JS 估計可信，但「可信」不等於「有 alpha」，當前可信地告訴我們 grand_mean 是 -14 bps。

### Verdict 3 — cost_gate 放行 expected new fills net edge ≈ -14 bps，不需要也不應做 counterfactual backtest → **APPROVE FULL**

直接對應 QC W6 RFC 自答 Q2 完整立場。本 verdict 是 QC 數學分析的核心輸出，PA capture 完整。

QC 強化支撐（三段式論據對應 PA Verdict 3 的 3 段）：
1. **數學論據**：JS shrunk_bps 是 model 給予的 expected net edge；任何 unbiased estimator 預期下次 sample 也 ~-14 bps
2. **Counterfactual backtest 4 項 bias 修正成本**：(i) leak-free shift / (ii) fee+slippage 模型重 fit / (iii) funding settlement drag / (iv) JS self-fulfilling bias — 4 項任一漏修都會給出 misleading 結果；ROI 不值得（已知 -14 bps）
3. **Kelly / DSR 雙重否決**：fractional Kelly f* < 0 即「數學上不交易」；DSR PASS 機率 ≈ 0；放行違反原則 #5

「例外觸發點：未來 grand_mean 翻正且 raw - grand_mean 大幅正方向偏離（≥ +30 bps）才有重評必要」也是**量化正確**：在 high B 環境下，必須 raw 偏離夠大才能讓 (1-B)(raw - grand_mean) 項實質非零。+30 bps 偏離是合理的 threshold（對應 raw ≈ +16 bps 且 grand_mean -14 bps 的場景）。

### Verdict 4 — trainer task type confirm：scorer_trainer 是 LightGBM regression → **APPROVE FULL**

從 QC 立場 100% 接受 MIT 的 category error 結論，但需 push back 一個語意 nuance（見 §6 push back 1）。

`scorer_trainer.py:90-104` `objective='regression', metric='rmse'` source-of-truth 獨立 verify。`is_unbalance` / `scale_pos_weight` / focal loss 是 LightGBM **classification objective** 專用參數，對 regression objective `lgb.train` silently ignore — 這是 LightGBM 設計。

V084 sample_weight 走 `lgb.Dataset(weight=...)` 路徑 = L2 loss 加權，不是 class balancing — 兩者數學機制完全不同：
- **Classification imbalance**：影響的是 decision boundary（model 預測 class label 的 threshold）
- **Regression sample_weight**：影響的是 loss landscape 中各 row 的 leverage（高 weight row 對 fitted curve 拉力大）

---

## §2 W6-5 LightGBM imbalance 撤回 — QC math 立場

### MIT category error 結論 QC 認可程度：100% 認可

### sample_weight 試行替代方案 quant 上預期效果

**對 RMSE 的影響**（regression loss landscape 拉力）：
- 1/100 → reject row 對 RMSE 貢獻 = 7038 × (1/100) = 70.38 unit；fill row = 615 × 1.0 = 615 unit；ratio 8.7:1
- 1/170（V084 default）→ reject 41.4 unit / fill 615 unit；ratio 14.9:1
- 1/300 → reject 23.5 unit / fill 615 unit；ratio 26.2:1
- 1/500 → reject 14.1 unit / fill 615 unit；ratio 43.6:1

**預期 quant magnitude**：
- RMSE 變化在 1/100 vs 1/500 之間預期 < 5%（兩者 fill 都 dominate ≥ 87% loss leverage）
- 對 cost_gate decision distribution 的影響：**幾乎為零**（cost_gate 用 JS shrunk_bps 不用 scorer 預測；scorer 預測的是 fill 後 PnL 用於 LinUCB reward）
- 對 Sharpe 的影響：scorer prediction error 對最終 Sharpe 是間接二階影響

**「僅報告對比，不 deploy 入 production cron」是正確 design** — 這是 sample_weight ratio sensitivity（quant explore），不應改 production 訓練 pipeline。

---

## §3 Track A regression scorer 微調 quant 評估

### 預期 magnitude：極小（per §2 數學分析）

Track A 給「scorer prediction 對 reject row 的 leverage 最佳 ratio」的探索答案，但對：
- 5 textbook 策略結構性 alpha-deficient 結論：**0 影響**
- cost_gate 拒擋 -14 bps 的判斷：**0 影響**（cost_gate 不用 scorer 預測）
- LinUCB routing reward signal 質量：**marginal 影響**（< 5% MSE 改進預期）
- 24h MLDE avg_net +8.75 bps 翻正趨勢：**0 影響**

### 樣本要求

- Total pool: 7038 reject + 615 fill = 7653 row（V084 weighted）— 已過 LightGBM regression 1000+ row baseline
- 5-fold CV 每 fold = 1530 row → 統計 power 充足
- block bootstrap 1000（**non-IID，crypto returns 必走 block bootstrap**）給 RMSE 95% CI

---

## §4 Track B 多 class 4-gate quant 評估

### N requirement

**PA 4-gate spec 中 (b) 條「multi-class label 18+ enum 各 class sample ≥ 200 row」是過度寬鬆的 quant 門檻**。

QC 修正建議（**push back 2**）：
- detect class 之間 Sharpe Δ=0.5 顯著需 **per-class N ≥ 60**
- detect class 之間 Sharpe Δ=0.2 顯著需 **per-class N ≥ 200**
- multi-class classification 涉及 Bonferroni 修正：18 class 兩兩比較 = 153 比較 → α 從 0.05 降到 3.27e-4 → 對應 N 至少要 × 4 倍才有 power → **per-class N ≥ 240**（Bonferroni 修正後 detect Δ=0.5）或 **per-class N ≥ 800**（detect Δ=0.2）

當前 per-class sample status（per E1 IMPL report §3.3 真實 V086 backfill state）：
- reject 12 enum: cost_gate_js_demo 14747 / duplicate 2332 / symbol_blocklist 694 / cost_gate_atr_unavailable 37 / 其餘 8 enum 0 row（4 enum 過 200，1 接近，7 不過）
- close 14 enum: strategy_close_grid 689 / strategy_close_legacy_bare_name 633 / risk_close_phys_lock_gate4_giveback 511 / strategy_close_ma 315 / strategy_close_funding_arb 29 / risk_close_phys_lock_gate4_stale 20 / 其餘 8 enum < 20 row

→ **18+ enum 中只有 8 enum (4 reject + 4 close) 接近 200；剩下 10+ enum sample < 100，short-term 不可能達 200 baseline**

**QC 結論**：(b) 條應放寬為「**per-class N ≥ 60 for 至少 80% enum**」更務實（detect Δ=0.5 with α=0.05 Bonferroni 修正）；OR 接受現實：Track B 4-gate 在 N+2/N+3 都不可能全 PASS；要 enable Track B 必須先 reduce class cardinality（merge 低 sample enum）

### 對 strategy alpha 影響：幾乎為零

5 textbook 策略結構性 alpha-deficient → 即使 routing 完美，alpha-deficient 策略仍給 negative PnL → multi-class label 改善 routing 也無法救無 alpha 的策略。真正 alpha 改善的路徑是 W2 A4-C BTC→Alt Lead-Lag + W-AUDIT-8a Phase B/C/D 補 alpha source。

**QC 對 Track B 留 N+2/N+3 spec phase 完全同意**，但建議 PA 在 AMD 件中明確標註「Track B 不在 alpha 補強的 critical path 上」。

---

## §5 V086 production deploy 後 sample evaluation

### reject_n=17810 / close_n=2247 是否 sufficient

**Total pool**：充足對 Track A regression 訓練。
**Per-class 評估**：見 §4 — 只 8/26 enum 接近 200 baseline；short-term 不可能達 4-gate (b) 條。

### Backfill 9757 row data quality vs realtime stream 差異

1. **Mapping deterministic**：V086 backfill SQL 全 deterministic CASE WHEN，**0 manual review** — quality 與 realtime stream **等價**（producer 端用相同 mapping helper `intent_processor/reject_reason_code.rs::map_reject_reason_to_code` byte-identical 對應 SQL CASE WHEN）
2. **Backfill 等級為 1st-party deterministic**：相比 paper / synthetic_replay 數據，backfill 是真實 historical events 的 metadata 補完，**可作 training data**
3. **Statistical purity 警示**：backfill 不修補 **producer era confound**（pre-V082 vs post-V082 reject rate 0% → 99.55%）

**QC 建議補 W6 acceptance gate**（**push back 3**）：trainer pipeline 訓練時必加 `WHERE ts > '2026-05-09 09:22 UTC'`（W-AUDIT-4b M3 producer 切上線時間）以排除 pre-M3 era 的 data quality drift。

---

## §6 Push back items

### Push back 1 (minor wording)

**Verdict 4 段落「sample_weight 試行」表述過度樂觀** — 應改：「探索 1/100 / 1/170 / 1/300 / 1/500 對 **scorer RMSE + scorer prediction IC + simulated LinUCB reward signal quality** 影響」 — 移除「cost_gate decision distribution」誤導表述。

### Push back 2 (quant requirement)

**§3 Track B 4-gate (b) 條「per-class sample ≥ 200」太寬鬆** — 應改為「**per-class N ≥ 60 for 至少 80% enum**」（更務實）OR 「per-class N ≥ 240 for 全 enum + Bonferroni α 修正」（更嚴格）。

### Push back 3 (acceptance gate gap)

**W6-2 + Track A acceptance 缺「pre-M3 era data quality filter」要求** — 補入 §8 第 6 條：「Track A sample_weight ratio sensitivity 試行報告必含 (a) full pool training + (b) post-M3 era only training 兩 variant 對比；若 RMSE 差異 > 10% 則正式 production scorer training 必加 `ts > '2026-05-09 09:22 UTC'` filter」。

### Push back 4 (acceptance gate clarification)

**§7 healthcheck [40] enhancement「fills/day rate snapshot baseline」缺 LOW_SAMPLE 標記要求** — 補入 §8 第 11 條：「[40] healthcheck enhancement 必加 `LOW_SAMPLE` 標記邏輯 — n_total < 30 時 [40] avg_net_bps 不當 strategy edge proxy，必加 WARN flag」。

---

## §7 Confidence + Sources

**Confidence: HIGH**

理由：
1. 4 verdict 全與 QC W6 RFC 預備立場一致（hold A 4 + 1 hold B → APPROVE 4 / hold confirm）
2. 數學論據（Kelly fractional / DSR / PSR / VaR / JS B-factor）均經 source code (gates.rs / james_stein_estimator.py / scorer_trainer.py) 與 PG live measure 雙重 verify
3. 黑名單觸碰檢查：HMM / GARCH / VPIN / vol mean-rev / 獨立 Donchian — **0 觸碰**
4. 16 root principles 對照 PA §9 已完整列出 16/16 合規；DOC-08 §12 不變量 0 觸碰；§四 5 硬邊界 0 觸碰

**Sources / 文獻 reference**：
- Bailey & Lopez de Prado (2012) — Probabilistic Sharpe Ratio
- Bailey, Borwein, Lopez de Prado, Zhu (2014) — Probability of Backtest Overfitting
- James & Stein (1961) — Inadmissibility of MLE for the mean of a multivariate normal distribution
- Lopez de Prado (2018) — Advances in Financial Machine Learning
- Harvey, Liu, Zhu (2016) JFE — ...and the Cross-Section of Expected Returns

**Internal sources**:
- W6-1 RFC final verdict draft: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
- QC W6 RFC 自答: `srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-10--w6_rfc_qc_questions_self_answer.md`
- MIT W6 RFC 自答: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_rfc_mit_questions_self_answer.md`
- E1 W6-3c V086 IMPL: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_3c_v086_impl_dry_run_writer_code.md`
- Rust source: `srv/rust/openclaw_engine/src/intent_processor/gates.rs:108-184`
- Python source: `srv/program_code/ml_training/james_stein_estimator.py:146-190` + `srv/program_code/ml_training/scorer_trainer.py:90-104`

---

**QC AUDIT DONE**: APPROVE-CONDITIONAL（4 push back items 全屬 minor wording / acceptance gate clarification，不阻 D+1 升 AMD；建議 PA 升件時 absorb push back 1+2+3+4 到 final AMD）

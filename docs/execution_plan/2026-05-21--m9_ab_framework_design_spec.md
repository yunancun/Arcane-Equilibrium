---
spec: M9 A/B Testing Framework DESIGN
date: 2026-05-21
author: MIT (Sprint 1A-γ CRITICAL DESIGN; sibling V108 full DDL schema spec)
phase: v5.8 Sprint 1A-γ ADD-per-operator module DESIGN
status: SPEC-DRAFT-V1（DESIGN spec；對齊 ADR-0037 5 Decisions 邊界；待 PA C9 + PM sign-off → SPEC-FINAL）
parent specs:
  - srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md (5 Decisions ADR 權威；本 spec 100% 對齊不違背)
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M9 (line 319-355)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-γ (line 146-157) + §QA/QC reconcile (line 368)
  - srv/docs/execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md (sibling V108 full DDL spec；本 DESIGN spec land 後 V108 spec full DDL 同步 upgrade)
sibling specs:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (V103 hypotheses table；M9 A/B test 必 FK 到 V103 hypothesis_id preregistration)
  - srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md (V110 M6 reward weight；M9 cluster 3 risk profile variant ref M6 5-λ weight set)
  - srv/docs/execution_plan/2026-05-21--m6_bayesian_reward_weight_design_spec.md (M6 DESIGN spec；M6 ↔ M9 integration ref)
  - srv/docs/execution_plan/2026-05-21--m7_strategy_decay_design_spec.md (M7 DESIGN spec；M7 ↔ M9 variant DECAY treated equal as same-strategy ref)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--m6_bayesian_reward_weight_design_spec.md (M6 DESIGN spec 結構範式)
amendments:
  - AMD-2026-05-15-01 (Stage 0R-4 graduated canary framework; ADR-0037 Decision 2 variant Stage 路徑 100% 引用此 framework)
  - AMD-2026-05-09-03 (Strategist Wide-Adjustment RuntimeMaxEnvelope; ADR-0037 Decision 3 Cluster 3 risk profile variant 必對齊不超範圍)
scope: M9 A/B framework DESIGN spec only — 不寫 IMPL Rust/Python code; 不違背 ADR-0037 5 Decisions; 不假設 V107 FK type alignment (per Sprint 1A-β M7 caveat V107 final schema UUID vs BIGINT 仍 pending)
---

# M9 A/B Testing Framework — DESIGN Specification (Sprint 1A-γ)

## §0 TL;DR

- **M9 為 A/B testing framework**：對 control + variant 對抗性驗證；4 variant cluster 分類（parameter_sweep / signal_source_swap / risk_profile / exit_logic）+ variant 共享 Stage 路徑（per ADR-0037 Decision 2-3）
- **mSPRT + Always-Valid Inference (Howard et al 2021 anytime-valid confidence sequence) + Bonferroni 校正**：對齊 ADR-0037 Decision 4 + `time-series-cv-protocol` skill + `quant-strategy-design` skill；crypto perp 違反 i.i.d. + sub-Gaussian → AVI 修正必要
- **Variant Stage 路徑**：control + variant 共享相同 5-gate Stage 0R → 0 → 1 → 2 → 3 → 4 graduated canary（per AMD-2026-05-15-01）；variant 不繞 Stage 升級紀律
- **Fair execution clause**：同 lease bucket / 同 LAL Tier / 同 budget cap / 同 Guardian gate（per ADR-0037 Decision 5）；禁 variant supervisor escalation 偷跑
- **Preregistration**：V108 `ab_tests.hypothesis_id` FK 到 V103 `learning.hypotheses(hypothesis_id)` NOT NULL；hypothesis 必先 preregister 才能 A/B test（per ADR-0026 v3 pre-registration mandate）
- **Server-side seeded random hash**：assignment hash algorithm 為 server-side seeded（per E3 must-fix）；不用 client-side rand（防 trial_id 被 user 預測 / 防 selection bias）
- **Trial outcome 對齊 M11 nightly replay**：M9 variant outcome 經 M11 continuous counterfactual replay cross-validate（per ADR-0037 cross-ref to ADR-0038）；replay divergence flag → M9 test inconclusive
- **M9 ↔ M7 integration**：variant DECAY treated equal as same-strategy（per Sprint 1A-β M7 DESIGN spec §11；M7 是 single decay authority per CR-7）
- **AC（5-7 條）**：mSPRT sample size derive test / 4 cluster taxonomy round-trip / hash algorithm seed test / variant Stage 路徑 proptest / M11 cross-ref test 等
- **IMPL phase 分 4 階段**：Sprint 4 read-only logging (Cluster 1+4) / Sprint 7-8 manual A/B (+Cluster 2+3) / Y2 auto-test scheduling (全 4 cluster；promotion to Stage 4 永遠 operator approval LAL 3)（per ADR-0037 Decision 6）

---

## §1 Context + 為什麼

### 1.1 v5.8 §2 M9 module source

v5.8 §2 M9 line 319-355 將 A/B Testing Framework 列為 13 module 之一：
- A/B test 為 hypothesis testing 之 finer-grained variant comparison
- 4 variant types：parameter / sizing / trigger / overlay variant（原 test types）
- mSPRT 是 default 統計方法（per ADR-0037）— 支援 peeking 不 inflated Type I error
- multiple comparisons correction：Bonferroni or Benjamini-Hochberg FDR control

operator 2026-05-21 指示「design at initial stage even if IMPL delayed — 對後續接入更 friendly」（per PA report 行 22）。

### 1.2 為什麼 M9 是 4 variant cluster 而非單一 test type

per ADR-0037 Decision 3，v5.8 §2 M9 line 326-330 列的 4 種 test types **重整為 4 variant cluster**（不只是 test type，而是治理 + Stage 路徑 + IMPL 階段分類）：

| 重整面 | v5.8 原 test type | ADR-0037 Cluster |
|---|---|---|
| 「測試什麼」（technical taxonomy） | parameter / sizing / trigger / overlay | — |
| 「治理 surface」（governance taxonomy） | — | parameter_sweep / signal_source_swap / risk_profile / exit_logic |

**為什麼分 4 cluster**：對應不同的 Stage 路徑 + LAL 級別 + ADR-0021 R-2 Strategist orchestrator surface；分 cluster 是為了 Sprint 4 read-only / Sprint 7-8 manual / Y2 auto-gate 三階段 IMPL 時 sub-agent 能對齊正確的治理紀律。

### 1.3 為什麼必須在 Sprint 1A-γ DESIGN 階段 land

per PA dispatch packet 行 153：Sprint 1A-γ 50-70 hr DESIGN 包含 M9 schema + ADR-0037 + V108 spec doc 三件耦合。本 DESIGN spec 是 V108 full DDL spec 的權威來源：
- 4 cluster taxonomy 邊界 → V108 `cluster_type` ENUM CHECK 5 值（含 ADR-0037 4 cluster + 退化邏輯）
- mSPRT + AVI + Bonferroni 三層修正 → V108 `statistical_method` ENUM CHECK + `bonferroni_correction_n` column
- variant Stage 路徑 → V108 `lal_level` smallint 對齊 ADR-0034 LAL
- fair execution clause → V108 `ab_assignments.lease_id` NOT NULL + 對齊 ADR-0008 Decision Lease state machine

### 1.4 QA + QC 5.21 v5.8 audit 兩 push back 一次性 reconcile

per PA report 行 368 reconcile：
- **QA 提**：M9 variant 升 Stage 路徑不明（per ADR-0037 Decision 2 解 → §4 詳論）
- **QC 提**：M9 mSPRT i.i.d. 假設違反（per ADR-0037 Decision 4 解 → §3 詳論）

本 DESIGN spec §3 + §4 + §5 合併處置兩 push back。

### 1.5 為什麼不能跳過 M9 直接 promote variant

memory `feedback_multi_role_strategic_review` 證明 EDGE-DIAG-1 Phase 2 多 role adversarial review catch 3 個 unique blind spots。M9 是 alpha 歸因 + 參數驗證的對抗性 framework：
- 無 M9 → variant promotion 走 single-strategy single-fork 路徑
- 無 M9 → 無法區分「策略 alpha」vs「參數選擇 alpha」vs「regime luck」貢獻
- 對於 P0-EDGE-1 Y1 持續 negative edge 場景，M9 是後續 P0-EDGE-1 root closure 必要 framework

### 1.6 不在本 spec 範圍

- ❌ IMPL Rust/Python code（Sprint 4 / 7-8 / Y2 三階段 IMPL；本 spec 為 DESIGN）
- ❌ V108 SQL file 寫作（sibling V108 full DDL spec land 之後 E1 IMPL 工作）
- ❌ Mac 跑 PG SQL（必 Linux PG empirical；走 V108 spec §4 dry-run 規範）
- ❌ Rust/Python writer 對應 ab_tests / ab_assignments / ab_results 寫入路徑（E1 IMPL 工作）
- ❌ healthcheck Python integration（E1 IMPL Sprint 4+ 工作）
- ❌ ContextDistiller v4 token cap 對齊（per ADR-0041；M9 evaluation 不在 hot path L1 SLA）

---

## §2 4 Variant Cluster 詳細規範

per ADR-0037 Decision 3，4 cluster 各自治理紀律 + Stage 路徑 + LAL 級別 + IMPL 階段。

### 2.1 Cluster 1 — Parameter Sweep

| 元素 | 設計 |
|---|---|
| **範例** | trailing_pct range / MA period / ATR multiplier / Donchian channel N / Bayesian opt iter budget |
| **LAL 級別** | **LAL 1** (intra-strategy reparam) — variant 是同策略內參數調整 |
| **變更深度** | 最淺（只動 numerical hyperparameter） |
| **Stage 路徑** | per ADR-0037 Decision 2 5-gate；variant Stage 0R replay 通常與 control 高度相似（差參數），但 leak-free shift(1) 紀律必生效（per memory `feedback_indicator_lookahead_bias`） |
| **IMPL 階段** | Sprint 4 read-only logging 可優先支援（最低風險）|
| **預期數量** | 每策略 5-15 個並行 sweep（高 Bonferroni N） |
| **典型 hypothesis** | 「將 grid_trading 的 grid_step 從 0.5% 改 0.3% 是否 Sharpe 提升 ≥ 0.2」 |
| **典型 variant config diff** | 單一 numerical hyperparameter 變更 |
| **min_sample_size 預期** | 較小（per-variant 200-500 fills 因 control + variant 變更最淺）|

#### 2.1.1 Cluster 1 統計風險

per `feature-engineering-protocol` skill + memory `feedback_indicator_lookahead_bias`：
- **rolling stat 必 shift(1)**：variant 若涉及 rolling indicator parameter，Stage 0R replay 必驗 leak-free `.shift(1)` 紀律
- **parameter overfitting**：5-15 個 parallel sweep 即 cherry-picking 候選；Bonferroni 校正後 α=0.05/(15×並行 test 數) 必嚴格控
- **regime sensitivity**：parameter 在不同 vol regime 表現差異大；CSCV PBO 必算（per `time-series-cv-protocol` skill）

### 2.2 Cluster 2 — Signal Source Swap

| 元素 | 設計 |
|---|---|
| **範例** | 同策略換 alpha 源（如 M6 Bayesian → M4 self-supervised pattern miner / M6 Bayesian → 既有 LightGBM baseline）|
| **LAL 級別** | **LAL 2** (cross-strategy reweight) — 變更影響 alpha source registry，跨策略可能相互影響 |
| **變更深度** | 中等（變更 alpha 源但保策略結構） |
| **Stage 路徑** | per ADR-0037 Decision 2 5-gate；Stage 0R replay 必驗 alpha 源切換後 leak-free + ADR-0026 CPCV 紀律 |
| **IMPL 階段** | Sprint 7-8 manual A/B（需 M4 land 後才能 swap）|
| **預期數量** | 每策略 1-3 個並行 swap |
| **典型 hypothesis** | 「將 grid_trading 的 alpha source 從 M6 Bayesian regime detector 換為 M4 self-supervised pattern miner 是否 Sharpe 提升 ≥ 0.3」 |
| **典型 variant config diff** | alpha source 配置（M6 vs M4 / weight set 完全替換 / API endpoint 替換）|
| **min_sample_size 預期** | 較大（per-variant 500-1500 fills 因 alpha source 變更影響更深 + effect size 較大期望）|

#### 2.2.1 Cluster 2 統計風險

per `feature-engineering-protocol` skill + ADR-0026：
- **CPCV 必跑**：alpha source 切換是 hypothesis-level 變更，per ADR-0026 v3 必走 CPCV preflight
- **alpha source registry consistency**：variant alpha source 必在 Alpha Surface Bundle 內（per ADR-0021 R-1）；不允許 ad-hoc alpha source
- **Cross-strategy reweight 影響**：LAL 2 因 alpha source 跨策略共用（如 M4 pattern miner output 同時被 grid + ma 用）；variant 影響需在 LAL 2 級審查

### 2.3 Cluster 3 — Risk Profile

| 元素 | 設計 |
|---|---|
| **範例** | LAL Tier A (3%) vs LAL Tier B (1.5%) sizing / ATR-based SL/TP vs fixed SL/TP / max_open_positions 25 vs 15 / M6 5-λ weight set 變更 |
| **LAL 級別** | **LAL 2** (cross-strategy reweight) — risk envelope 變更影響 portfolio aggregator |
| **變更深度** | 中等（變更 risk envelope 但保策略 entry/exit 邏輯） |
| **Stage 路徑** | per ADR-0037 Decision 2 5-gate；variant 必對齊 AMD-2026-05-09-03 RuntimeMaxEnvelope（不超範圍） |
| **IMPL 階段** | Sprint 7-8 manual A/B |
| **預期數量** | 每策略 1-2 個並行 risk profile test |
| **典型 hypothesis** | 「將 ma_crossover 的 5-λ M6 reward weight 從 lambda_max_dd=0.5 提升到 1.0 是否 max_dd 降低 ≥ 30% 且 Sharpe 不降」 |
| **典型 variant config diff** | M6 weight_set_id 替換 / LAL Tier A→B / SL/TP 邏輯切換 / max_open_positions 縮減 |
| **min_sample_size 預期** | 大（per-variant 1000-2000 fills 因 risk profile 在 tail event 才現差異）|

#### 2.3.1 Cluster 3 統計風險

per `data-drift-detection` skill + AMD-2026-05-09-03：
- **Tail event sample 不足**：risk profile 差異在 tail event 才現；正常 vol regime 樣本對 variant 比較幾乎無 information
- **RuntimeMaxEnvelope 對齊**：variant 不可超 AMD-2026-05-09-03 strategist wide envelope；schema-level CHECK constraint 在 V108 `lal_level` 範圍體現
- **M6 5-λ weight set 重用**：variant ref 到 V110 `learning.reward_weight_history.weight_set_id`；schema-level 不 FK（避免 cross-1A-β/γ race，per CR-9 cross-V### dependency graph）

### 2.4 Cluster 4 — Exit Logic

| 元素 | 設計 |
|---|---|
| **範例** | fixed-time exit vs trailing exit vs physical_micro_profit_lock_v2 variant / partial TP vs full TP / close maker vs close taker |
| **LAL 級別** | **LAL 1** (intra-strategy reparam) — 變更 exit 但保 entry signal |
| **變更深度** | 中等（變更 exit logic） |
| **Stage 路徑** | per ADR-0037 Decision 2 5-gate；Stage 0R replay 必驗 exit logic 不破 close maker / risk_exit attempt × fallback matrix（per QA 5/20 W-C lesson v55 reframe） |
| **IMPL 階段** | Sprint 4 read-only logging（部分）+ Sprint 7-8 manual A/B（完整） |
| **預期數量** | 每策略 1-3 個並行 exit variant |
| **典型 hypothesis** | 「將 bb_breakout exit 從 fixed_time(60s) 改 trailing(0.3% trail) 是否 net_return_bps 提升 ≥ 10 bps」 |
| **典型 variant config diff** | exit logic 配置（fixed-time / trailing / micro-profit-lock）+ trailing parameters |
| **min_sample_size 預期** | 中（per-variant 300-1000 fills；exit 差異在每 fill outcome 都可觀察）|

#### 2.4.1 Cluster 4 統計風險

per QA 5/20 W-C lesson v55 reframe + `time-series-cv-protocol` skill：
- **Close maker / taker fallback matrix**：variant exit logic 必驗 close maker / risk_exit attempt × fallback matrix（per QA lesson）
- **Outcome bias**：fixed-time 與 trailing exit 在 trending vs ranging regime 表現差異大；CV 必含 regime stratification
- **shift(1) leak-free**：trailing exit 若用 rolling indicator，必 shift(1)

### 2.5 Cluster-Stage-LAL 對齊矩陣（核心 governance artifact）

per ADR-0037 Decision 3 末段，矩陣明示三維對齊：

| Cluster | LAL 級別 | 主 IMPL 階段 | Stage 起始 | Stage 終止 promotion 條件 | min_sample_size 預期 |
|---|---|---|---|---|---|
| 1 parameter_sweep | LAL 1 | Sprint 4 | Stage 0R | 同 control Stage 升級 + variant winner 觸發 operator approval | 200-500 |
| 2 signal_source_swap | LAL 2 | Sprint 7-8 | Stage 0R | 同 control Stage 升級 + variant winner 觸發 operator approval | 500-1500 |
| 3 risk_profile | LAL 2 | Sprint 7-8 | Stage 0R | 同 control Stage 升級 + variant winner 觸發 operator approval | 1000-2000 |
| 4 exit_logic | LAL 1 | Sprint 4 部分 / Sprint 7-8 完整 | Stage 0R | 同 control Stage 升級 + variant winner 觸發 operator approval | 300-1000 |

**對齊紀律**：
- Cluster 1+4 = LAL 1（intra-strategy reparam）→ Sprint 4 first Live 可優先支援
- Cluster 2+3 = LAL 2（cross-strategy reweight）→ Sprint 7-8 manual A/B 才支援（依賴 M4 land）
- 所有 cluster variant promotion 到 Stage 4 永遠 LAL 3 operator approval（per ADR-0034 + ADR-0037 Decision 2）

---

## §3 mSPRT + AlwaysValidInference + Bonferroni 校正

per ADR-0037 Decision 4，回應 QC 5.21 push back「mSPRT i.i.d. 假設違反」。

### 3.1 為什麼用 mSPRT

per `quant-strategy-design` skill + `time-series-cv-protocol` skill：
- **sequential testing 允許 early stopping**（efficacy / futility）；不需固定 horizon；對 small effect size 樣本效率優於 fixed-horizon
- mSPRT (mixture Sequential Probability Ratio Test) = Wald SPRT 的 generalization；對未知 effect size 用 mixture prior

### 3.2 為什麼 mSPRT 在 crypto perp 不夠 — 需 AVI 修正

per QC 5.21 audit + memory `feedback_indicator_lookahead_bias`：

1. **crypto perp fills 強自相關**：1m / 1h kline 自相關係數常 > 0.3；fills 在策略邏輯下進一步集中於特定 regime → variant 樣本不 i.i.d.
2. **異方差（volatility clustering）**：vol regime 切換時 fills 集中分布 → 樣本方差非 stationary，違反 mSPRT 推導前提
3. **tail-fat**：crypto returns 6h-24h kurtosis 常 > 10（normal = 3）；mSPRT 對 sub-Gaussian 假設破壞
4. **multiple comparisons**：4 variant cluster × 多 strategy × 多 symbol → 100+ 並行 A/B test；無 Bonferroni / FDR 校正 → false discovery rate 30-50%

### 3.3 AVI (Always-Valid Inference) 設計

per Howard et al 2021 "Time-uniform, nonparametric, nonasymptotic confidence sequences"：
- **AVI 提供 anytime-valid confidence sequence**：不依賴 i.i.d.；在 strong autocorrelation + heavy tail 下保 Type I error ≤ α
- **具體實作走 V108 spec doc IMPL**（不在本 DESIGN spec 鎖死數學細節，留 amendment 空間；per ADR-0037 Decision 4）

### 3.4 Bonferroni 校正

α / (variant_count × parallel_test_count)；例：
- 5 variant × 20 並行 test = 100 → α=0.05 校正後 = 0.0005 per test
- 校正後 α 反映在 V108 `ab_tests.bonferroni_correction_n` column（integer NOT NULL）

### 3.5 最小樣本 derive 公式

per `time-series-cv-protocol` skill §3 樣本量規劃 + ADR-0037 Decision 4：

```
min_sample_per_arm = f(effect_size_expected, power=0.8, alpha_bonferroni_corrected)
```

具體公式：

```
min_sample = ceil(
    2 * ((z_alpha + z_beta) / effect_size_expected)^2 * variance_estimate
)
```

其中：
- z_alpha = norm.ppf(1 - alpha_bonferroni / 2)（two-sided test）
- z_beta = norm.ppf(power)
- effect_size_expected: 預期 net_return_bps 差異
- variance_estimate: 從 control 歷史 fills 估計（**用 block bootstrap 5-10 day block**，per ADR-0037 Decision 4 block bootstrap 配套）

**具體公式 IMPL 走 V108 spec doc Sprint 1A-γ IMPL**（不在本 DESIGN spec 鎖死 closed-form）。

### 3.6 Block Bootstrap 配套（per ADR-0036 Decision 4 walk-forward）

per ADR-0036 Decision 4 walk-forward + block bootstrap + ADR-0037 Decision 4：
- M9 evaluation 時 mSPRT statistic 對應 sampling distribution 用 block bootstrap 5-10 day block 估計
- 對 vol clustering robust（block size > autocorrelation length scale）
- 對應 `time-series-cv-protocol` skill §3 樣本量 + Embargo 規範

### 3.7 替代方案（Decision 4 amendment 選項）

per ADR-0037 Decision 4 替代方案：
- **Bayesian A/B**：適用樣本量極小場景；4 variant cluster × 100+ 並行 test 場景下 prior 校準難；可作為 V108 `ab_tests.statistical_method` ENUM 第二值（`Bayesian_AB`），但非主路徑
- **fixed-horizon test**：適用變更深度小場景；V108 `statistical_method` ENUM 第三值（`fixed_horizon`）

### 3.8 反模式（明示禁止 per ADR-0037 Decision 4）

- (a) 使用 naive Welch's t-test 或 unadjusted mSPRT 不做 Bonferroni 校正（false discovery rate 30-50%）
- (b) Test 中途任意 peek 不走 sequential testing protocol（peeking error）
- (c) 不 preregister effect size + power → post-hoc 找顯著結果（HARKing — Hypothesizing After Results Known）
- (d) min_sample_size 寫死 magic number（如 N=100）不從 power analysis derive
- (e) 使用 HMM / GARCH 估 variance structure（per ADR-0036 Decision 1 黑名單適用 M9）

### 3.9 mSPRT validation harness（per ADR-0037 Decision 4 + PA report 行 104 H-17）

Sprint 1A-γ V108 spec doc 必含 **M9 framework validation harness**：
- 1000+ simulation under known distribution
- 驗 Type I error ≤ α (Bonferroni-corrected)
- 驗 Power ≥ 0.8 at expected effect size
- 對 strong autocorrelation + heavy tail synthetic data 驗 AVI 正確性

具體 IMPL 走 Sprint 3 + Sprint 4 早期（per ADR-0037 Engineering Scope Reference Sprint 3 30-50 hr）。

---

## §4 Variant Stage 路徑（per ADR-0037 Decision 2 + AMD-2026-05-15-01）

回應 QA 5.21 push back「variant 升 Stage 路徑不明」。

### 4.1 核心原則

per ADR-0037 Decision 2：**Control + variant 共享相同 5-gate Stage 0→4 graduated canary**（per AMD-2026-05-15-01）；variant 不繞 Stage 升級紀律。

### 4.2 Stage 路徑詳細

| Stage | control 行為 | variant 行為 | M9 統計動作 |
|---|---|---|---|
| **0R replay preflight** | control 走 AMD-2026-05-15-01 replay preflight | variant **必通過 replay preflight 才進入 Stage 0** shadow（per ADR-0037 Decision 2 反模式 (a) 禁繞） | mSPRT 尚未啟動（replay 結果寫 V107 M11 divergence_log）|
| **0 shadow** | control 跑 shadow | variant 同時跑 shadow；M11 nightly counterfactual replay 對齊（per ADR-0038）| mSPRT 啟動 in shadow mode（不 commit assignment）|
| **1 demo small** | control 跑 demo 小倉 | variant 同時跑 demo；fill 樣本累積至 V108 `ab_assignments`；mSPRT sequential update 啟動 | mSPRT sequential update commit；V108 `ab_results` per evaluation_ts 累積 |
| **2 demo full** | control 跑 demo full | variant 同時跑 demo full；min_sample_size_per_arm 達標 → mSPRT efficacy / futility evaluation | mSPRT 達 efficacy / futility boundary 觸發 boundary_crossed=TRUE |
| **3 live canary** | control 已在 Stage 3 live canary | **若 variant efficacy boundary crossed + Bonferroni-adjusted p < α → variant 進 live canary（與 control 並行）**；variant 仍綁同 lease bucket / 同 LAL Tier / 同 budget cap | mSPRT 持續監控；rollback 路徑保留 |
| **4 live full** | control 在 Stage 4 live full | **A/B test 結論 = variant winner**（per §3 statistical conclusion）→ operator approval（LAL 3 new strategy promotion）→ variant promote to Stage 4 取代 control | M9 test concluded_efficacy；V108 `ab_tests.status='concluded_efficacy'` |

### 4.3 Variant Stage 限制（per ADR-0037 Decision 2）

1. **(a)** variant 不能單獨進 Stage X 而 control 留在 Stage Y（除非 control 觸發 decay per ADR-0036 / M7）
2. **(b)** variant Stage 升級 == 同時 control + variant 升
3. **(c)** variant 終止（test concluded futility / aborted）= variant 回到 dormant + control 繼續

### 4.4 Test 終止後處置（per ADR-0037 Decision 2 末段）

| 終止類型 | 處置 |
|---|---|
| efficacy | variant promote、control demote to Stage 0 shadow（保留 baseline 比較） |
| futility | variant terminate、control 維持 Stage X |
| inconclusive | 延長 test OR operator manual terminate（per Decision 5 max duration） |
| aborted | variant + test 凍結；走 governance audit |

### 4.5 反模式（明示禁止 per ADR-0037 Decision 2）

- (a) variant 不經 Stage 0R replay 直接進 Stage 1 demo（繞 AMD-2026-05-15-01 replay preflight）
- (b) variant 在 control 處於 Stage 2 時提前進 Stage 3 live canary（Stage 跨級）
- (c) variant 經 5-gate auto path 繞 operator approval 進 Stage 4（per ADR-0034 LAL 3 永遠 operator approve；M9 不開新 auto path）

---

## §5 Fair Execution Clause（per ADR-0037 Decision 5）

對齊 §二 原則 4 策略不繞風控 + 原則 9 雙重防線。

### 5.1 同 lease bucket

- control + variant 共享同 Decision Lease bucket（per ADR-0008 + ADR-0034 LAL gate）
- 不允許 variant 繞 lease 走
- schema 反映：V108 `ab_assignments.lease_id` NOT NULL FK 到 governance.decision_lease

### 5.2 同 LAL Tier

- control + variant 共享同 LAL 級別（per §2.5 cluster-LAL 對齊矩陣）
- 不允許 variant 在 LAL 1 而 control 在 LAL 2（除非 cluster 設計明示）
- schema 反映：V108 `ab_tests.lal_level` smallint NOT NULL

### 5.3 同 budget cap

- control + variant 共享同 daily / weekly budget
- budget 由 ADR-0034 LAL 4 預設
- variant 不能單獨擴 budget（schema 級不允許；應用層 fail-closed）

### 5.4 同 Guardian gate

- control + variant 都經 Guardian 5-gate kill
- 任一 gate fail → control + variant 同時 freeze
- **fail-closed scope = test 級而非 arm 級**（per ADR-0037 Decision 5）

### 5.5 Assignment 紀錄

- per V108 `ab_assignments` 表必綁 `lease_id`
- audit trail 完整：assignment_id + test_id + decision_id + arm + lease_id + assignment_ts

### 5.6 禁止 variant supervisor escalation

- variant 不能繞 supervisor 路徑優先觸發 risk override
- 例：variant 用 wider SL/TP 預設掩蓋 control 的 PnL signal
- schema-level 不允許；應用層 IMPL 必加 invariant check

### 5.7 反模式（明示禁止 per ADR-0037 Decision 5）

- (a) variant 走獨立 lease bucket 繞 LAL gate
- (b) variant 用更大 budget cap 偷跑（artificially 增 sample size）
- (c) variant Guardian fail-closed 只 freeze variant arm 不 freeze test（test integrity 破壞）

---

## §6 Preregistration（V108 FK to V103 hypotheses）

### 6.1 為什麼必 preregister

per ADR-0026 v3 pre-registration mandate + ADR-0037 Decision 1 + 根原則 #8 交易可解釋：
- hypothesis 必先 preregister 才能 A/B test
- preregistration ledger 含 effect size 預期 + power + Bonferroni 校正分母
- 防 HARKing（Hypothesizing After Results Known）

### 6.2 V108 FK 設計

```sql
-- V108 ab_tests 表（per sibling V108 full DDL spec §2.1）
hypothesis_id BIGINT NOT NULL REFERENCES learning.hypotheses(hypothesis_id)
```

NOT NULL 強制：A/B test 必 reference 一個 preregistered hypothesis。

### 6.3 Preregistration 流程

1. **Hypothesis 創建**：寫 V103 `learning.hypotheses` row，status='draft' → 'preregistered'
2. **Preregistration 簽署**：寫 V103 `learning.hypothesis_preregistration` row，含 payload_hash + operator_signature
3. **A/B test 創建**：寫 V108 `ab_tests` row，FK 到 hypothesis_id；填 preregistered effect size + power + Bonferroni N
4. **mSPRT 啟動**：per §3 + §4

### 6.4 Effect size + power preregister

V108 `ab_tests` 表（per sibling V108 full DDL spec §2.1）含：
- `msprt_target_significance NUMERIC DEFAULT 0.05`
- `msprt_target_power NUMERIC DEFAULT 0.8`
- `min_sample_size_per_arm INTEGER NOT NULL`（per §3.5 derive）
- `bonferroni_correction_n INTEGER NOT NULL`（per §3.4）

preregister 後 immutable（schema-level append-only；amendment 走新 row + 舊 row aborted）。

---

## §7 Hash Algorithm（per E3 must-fix — server-side seeded random）

### 7.1 為什麼用 server-side seeded random hash

per E3 must-fix（在 PA dispatch packet 列出）：
- **server-side seeded random**：assignment hash algorithm 為 server 端用固定 seed + cryptographic random
- **不用 client-side rand**：
  - 防 trial_id 被 user 預測（client-side rand 暴露 seed 演算法）
  - 防 selection bias（client 可重複呼叫直到拿到想要的 arm）
  - 對齊 §四硬邊界「不能因 endpoint 降級」

### 7.2 Hash algorithm 設計

```
hash_seed = test_id (BIGINT) || strategy_name || symbol || stratification_keys
hash_value = SHA-256(hash_seed || cryptographic_random_nonce)
arm = hash_value mod variant_count
```

具體實作走 V108 spec doc Sprint 1A-γ IMPL；本 DESIGN spec 列原則：
- **deterministic**：同 (test_id, decision_id) 必同 arm（rerun replay 可重現）
- **uniform**：arm distribution 對 variant_count 均勻
- **unpredictable to client**：cryptographic random nonce server 端持有

### 7.3 V108 schema 反映

per sibling V108 full DDL spec §2.1.2：
- `hash_seed BIGINT NOT NULL`（server 端 generated；preregister 期 commit）
- `ab_assignments.hash_value NUMERIC NOT NULL`（per-assignment 計算結果）
- `ab_assignments.assignment_method TEXT CHECK IN ('deterministic_hash', 'stratified_random', 'sequential_balance')`

### 7.4 Stratification keys

per V108 `ab_assignments.stratification_keys JSONB`：
- 用於控制 confounders（symbol / regime cell / time-of-day）
- 例：`{"symbol": "BTCUSDT", "regime_cell": "high_vol", "tod_bucket": "asia_session"}`
- assignment_method='stratified_random' 時必填

### 7.5 反模式（明示禁止）

- (a) 用 client-side `Math.random()` 或 `random.random()` 計算 hash（暴露 seed）
- (b) seed 隨時間漂移（rerun replay 不可重現）
- (c) 同 (test_id, decision_id) assign 到不同 arm（破 deterministic invariant）
- (d) variant_count > 10 時用簡單 modulo（distribution 不均勻；考慮 weighted hash）

---

## §8 Trial Outcome 對齊 M11 Nightly Replay（per ADR-0037 cross-ref to ADR-0038）

### 8.1 為什麼對齊 M11

per ADR-0037 Decision 2 Stage 0 shadow + Stage 1 demo + cross-ref to ADR-0038：
- M11 nightly counterfactual replay 對 variant outcome cross-validate
- replay divergence flag → M9 test inconclusive（防 fills 漂移誤判 variant winner）

### 8.2 Cross-V### reference

V108 `ab_results.m11_replay_divergence_ref UUID`（per sibling V108 full DDL spec §2.3）：
- M9 evaluation 時 ref 到 V107 M11 divergence_log 對應 row
- replay 顯示 control vs variant trial outcome divergence > threshold → V108 `ab_tests.status='concluded_inconclusive'`

### 8.3 V107 FK 假設 caveat（per Sprint 1A-β M7 caveat）

**重要**：V107 final schema UUID vs BIGINT 仍 pending（per Sprint 1A-β M7 DESIGN spec caveat）。

本 DESIGN spec 採 **UUID reference (not FK)**：
- V108 `ab_results.m11_replay_divergence_ref` 為 UUID type
- **不 FK schema-level**（避免 cross-1A-β/γ race + V107 type 未定）
- 應用層 join validation；type 對齊 V107 land 後 verify

若 V107 final schema 為 BIGINT，本 DESIGN spec 需 patch：
- V108 `ab_results.m11_replay_divergence_ref` 改 BIGINT
- 不影響本 DESIGN spec 邏輯

### 8.4 M11 cross-validation 觸發

- M11 nightly replay job 跑完 → 寫 V107 divergence_log
- M9 evaluation cron 跑時讀 V107 + V108 → cross-check
- divergence > threshold → V108 `ab_tests.status='concluded_inconclusive'` + alert operator

具體 threshold 由 risk_config TOML 定（IMPL 期 land；本 DESIGN spec 不寫 TOML）。

---

## §9 M9 ↔ M7 Integration（per Sprint 1A-β M7 DESIGN spec §11）

### 9.1 為什麼整合

per Sprint 1A-β M7 DESIGN spec §11（M7 是 single decay authority per CR-7）+ ADR-0037 Decision 2 末段：
- **variant DECAY → 同 strategy 同等對待**（per Sprint 1A-β M7 design §11 ref）
- variant 若 underperform → 走 M7 decay flow，不繞 M9 statistical conclusion

### 9.2 Decay scenarios

| Scenario | M7 動作 | M9 動作 |
|---|---|---|
| **variant decay 偵測** | M7 寫 V113 decay_signals row | M9 V108 ab_tests.status='aborted'（提前終止 test）|
| **control decay 偵測** | M7 寫 V113 decay_signals row | M9 variant 升級到 control 位置（如 variant winner已 boundary crossed）|
| **A/B test 雙方 decay** | M7 兩個 signal | M9 status='concluded_inconclusive'（不選 winner）|

### 9.3 Cross-V### reference

- V108 ab_tests 不 FK 到 V113 decay_signals（schema-level decoupled，per CR-9 cross-V### dependency graph）
- 應用層 cron 跑：M7 decay 偵測 → M9 test status update
- M7 是 single decay authority（per CR-7）：M9 不寫自己的 decay 判斷邏輯

### 9.4 V107 + V113 dependency caveat（per Sprint 1A-β）

- V107 (M11 replay) Sprint 1A-β land；type 未定（per §8.3）
- V113 (M7 decay) Sprint 1A-β land
- 兩者 schema-level 不 FK 到 V108（cross-sprint decoupled）
- 應用層 join validation

---

## §10 Acceptance Criteria（5-7 條）

per ADR-0037 5 Decisions + 本 DESIGN spec §2-§9：

### AC-1: mSPRT 樣本量 derive test

- **驗**：給定 effect_size_expected=0.02, power=0.8, alpha_bonferroni_corrected=0.0005, variance_estimate=0.01
- **預期**：`min_sample_per_arm` 公式輸出 deterministic 整數（per §3.5）
- **失敗**：寫死 magic number 不從 power analysis derive → REJECT

### AC-2: 4 cluster taxonomy round-trip

- **驗**：對 4 cluster type（parameter_sweep / signal_source_swap / risk_profile / exit_logic）各創建 1 ab_test row + 對應 LAL level
- **預期**：V108 schema CHECK constraint 接受 4 cluster + 拒第 5 個 invalid value（如 'unknown_cluster'）
- **失敗**：CHECK constraint 漏接 4 cluster 之一 / 接受 invalid value → REJECT

### AC-3: Hash algorithm seed test

- **驗**：給定 fixed test_id + fixed strategy_name + fixed symbol，2 次計算 hash_value
- **預期**：deterministic — 同 input 同 output（per §7.2）
- **失敗**：2 次結果不同（client-side rand 跡象）→ REJECT

### AC-4: Variant Stage 路徑 proptest

- **驗**：proptest 隨機產生 200+ Stage transition sequence；驗 variant 不繞 Stage（per §4.5 反模式）
- **預期**：所有 sequence 滿足 variant_stage == control_stage（除 decay / abort scenarios）
- **失敗**：任一 sequence 顯示 variant 跨級 → REJECT

### AC-5: M11 cross-ref test

- **驗**：V107 M11 divergence_log row 寫入 → V108 ab_results.m11_replay_divergence_ref 對齊
- **預期**：UUID match；應用層 join validation pass
- **失敗**：type mismatch（如 V107 final 改 BIGINT）→ amendment patch §8.3

### AC-6: Fair execution invariant test

- **驗**：control + variant 共享 lease_id；嘗試 INSERT variant assignment 用 different lease_id
- **預期**：應用層 invariant check 拒絕（schema-level 不 enforce 因 ab_assignments 每行可不同 lease；同 test_id 內必 join validation）
- **失敗**：variant 用獨立 lease 通過 → REJECT

### AC-7: mSPRT validation harness Type I + Power

- **驗**：1000+ simulation under known distribution（per §3.9）
- **預期**：Type I error ≤ α (Bonferroni-corrected) + Power ≥ 0.8 at expected effect size
- **失敗**：Type I error inflate > 5% / Power < 0.7 → REJECT；amendment AVI implementation patch

---

## §11 IMPL Phase（per ADR-0037 Decision 6）

### 11.1 Sprint 1A-γ DESIGN（本 spec）

- 本 DESIGN spec land
- sibling V108 full DDL spec upgrade（placeholder → full DDL）
- ADR-0037 已 land（2026-05-21）
- **Workload**：50-70 hr（per PA dispatch packet 行 153）

### 11.2 Sprint 3 mSPRT validation harness（per ADR-0037 Engineering Scope Reference）

- mSPRT + AVI validation harness 1000+ simulation
- AC-7 Type I + Power 驗
- **Workload**：30-50 hr

### 11.3 Sprint 4 read-only logging（Cluster 1 + 4）

- **Cluster 1 parameter sweep**：read-only logging（最低風險）
- **Cluster 4 exit logic**：read-only logging（部分）
- **First Live A/B 啟用前**：必通過 v5.8 §10.5 4+1 條 P0 precondition（P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 / 5-gate live boundary）
- **Workload**：60-80 hr

### 11.4 Sprint 7-8 manual A/B（+Cluster 2 + 3）

- **Cluster 2 signal source swap**：需 M4 land 後才能 swap
- **Cluster 3 risk profile**：對齊 AMD-2026-05-09-03 RuntimeMaxEnvelope
- **Workload**：60-80 hr

### 11.5 Y2 auto-test scheduling（全 4 cluster；promotion to Stage 4 永遠 LAL 3 operator approval）

- 全 4 cluster 支援
- auto-test schedule + auto-mSPRT evaluation
- promotion to Stage 4 永遠 LAL 3 operator approval（per ADR-0034 + ADR-0037 Decision 2 末段反模式 (c)）
- **Workload**：80-120 hr

### 11.6 Total IMPL Y1+Y2

per ADR-0037 Engineering Scope Reference：280-400 hr 全程（含 validation harness + 全 4 cluster + auto-gate）

---

## §12 Cross-V### Dependency + Open Q

### 12.1 Cross-V### dependency

| V### | Direction | 關係 |
|---|---|---|
| V108 (own) | 主表 | M9 framework schema |
| V103 (hypotheses) | V108 → V103 FK | `ab_tests.hypothesis_id NOT NULL REFERENCES hypotheses(hypothesis_id)` per §6.2 |
| V110 (M6 reward) | V108 → V110 reference (no FK) | Cluster 3 risk profile variant ref M6 weight_set_id；應用層 join |
| V109 (M8 anomaly) | V108 → V109 reference (no FK) | M9 variant 若觸發 M8 anomaly → variant abort；應用層 cron |
| V113 (M7 decay) | V108 → V113 reference (no FK) | per §9.3 M7 single decay authority；應用層 join |
| V107 (M11 replay) | V108 → V107 reference (UUID, not FK) | per §8 + §8.3 caveat；V107 type 未定 |
| V111 (M10 discovery) | V108 → V111 reference (no FK) | M9 variant 若為 M10 discovery generated → 走 LAL 3 elevated approval |

### 12.2 Sprint dispatch ordering

- **Sprint 1A-β** 必先 land V103 (已 land 2026-05-21) + V107 + V110 + V112 + V113
- **Sprint 1A-γ** 才能 land V105 (M2) + V108 (M9) + V109 (M8) + V111 (M10)
- β → γ 不可重疊（per E5 + MIT 共識，per PA report 行 352）

### 12.3 Open Q

#### Open Q 1: V107 final schema UUID vs BIGINT

- **背景**：per §8.3，V107 final schema type 未定（Sprint 1A-β pending）
- **影響**：V108 `ab_results.m11_replay_divergence_ref` type 對齊
- **建議**：本 DESIGN spec 採 UUID；V107 land 後 verify；若 BIGINT 則本 spec patch §8.3 + V108 schema patch
- **Owner**：PA C9 dispatch 期 confirm V107 final type

#### Open Q 2: mSPRT AVI 具體 closed-form 公式

- **背景**：per §3.3 + ADR-0037 Decision 4 注「具體 confidence sequence 公式走 Sprint 1A-γ V108 spec doc IMPL，不在本 ADR 鎖死數學細節」
- **影響**：V108 spec doc IMPL 期決策；本 DESIGN spec 只列原則
- **建議**：Sprint 3 validation harness IMPL 期 land；對齊 Howard et al 2021 paper + `quant-strategy-design` skill
- **Owner**：MIT + QC 共同 Sprint 3 IMPL 期 verify

#### Open Q 3: Bonferroni 替代 FDR (Benjamini-Hochberg) 切換 trigger

- **背景**：per ADR-0037 Consequences Negative「Bonferroni 校正 over-conservative 風險 — 100+ 並行 test 校正後 α=0.0005 可能 power < 0.5」
- **影響**：V108 `ab_tests.statistical_method` ENUM 是否擴 FDR 第四值
- **建議**：(a) Sprint 7-8 manual A/B 期 evaluate power 後決定；(b) Y2 auto 期 land FDR 替代；本 DESIGN spec 不寫 FDR 為 amendment 選項
- **Owner**：MIT + QC Sprint 7-8 期 evaluate

#### Open Q 4: Cluster 1 parameter sweep parallel test 上限

- **背景**：per §2.1「每策略 5-15 個並行 sweep」+ ADR-0037 Decision 4 Bonferroni 校正
- **影響**：max parallel test count 由 PA 仲裁（per ADR-0037 Decision 1 注）
- **建議**：Sprint 4 first Live A/B 啟用前 PA 明示上限（建議起點：每策略 5 個並行 sweep，Y2 擴 15）
- **Owner**：PA Sprint 4 期決議

#### Open Q 5: M9 ↔ Copy Trading evaluation 路徑

- **背景**：per ADR-0037 Consequences Negative「variant Stage 路徑與 ADR-0030 Copy Trading evaluation 互動 — Copy Trading follower 永遠 control variant」
- **影響**：Copy Trading follower 不參與 variant arm
- **建議**：應用層 IMPL 期 invariant check；Copy Trading aggregator 只 ref control 的 ab_assignments
- **Owner**：FA + MIT Sprint 7-8 期共同 design

---

## §13 §二 16 根原則合規確認

per ADR-0037 §二 16 根原則合規確認，本 DESIGN spec 100% 對齊：

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | variant 走同一 control trade entry 路徑；不創旁路；fair execution clause §5 明示 |
| 2 | 讀寫分離 | ✅ | `ab_tests` / `ab_assignments` / `ab_results` 三表純 learning surface；variant 執行透過 Strategist + Decision Lease |
| 3 | AI 輸出 ≠ 命令 | ✅ | A/B test 結論是 evidence，不直接 promote；variant winner 必經 operator approval (LAL 3) |
| 4 | 策略不繞風控 | ✅ | §5 fair execution clause 明示同 Guardian gate；variant fail-closed scope = test 級而非 arm 級 |
| 5 | 生存 > 利潤 | ✅ | §11.3 Sprint 4 first Live A/B 啟用前必通過 §10.5 P0 precondition；防 P0-EDGE-1 阻塞期間啟動 A/B 放大失血 |
| 6 | 失敗默認收縮 | ✅ | mSPRT + AVI futility boundary → test 自動 terminate；§5.4 任一 Guardian gate fail → control + variant 同時 freeze |
| 7 | 學習 ≠ live | ✅ | Stage 0R replay → Stage 0 shadow → Stage 1 demo → Stage 2 demo full → Stage 3 live canary → Stage 4 live full；evidence 累積路徑明確 |
| 8 | 交易可解釋 | ✅ | per-assignment `lease_id` 綁定 + V108 三表完整 audit trail；test preregistration + statistical method 透明 |
| 9 | 雙重防線 | ✅ | mSPRT efficacy / futility + Bonferroni 校正 + Guardian gate + 5-gate canary = 多層 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | `ab_assignments` = 事實（per decision 分配）；`ab_results` mSPRT statistic = 推論（per §3 statistical methodology）；preregistered effect size = 假設 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | A/B test preregistration + execution 在 P0/P1 內自主；variant promotion 走 LAL 3 operator approval |
| 12 | Evidence-based evolution | ✅ | mSPRT + AVI + Bonferroni 三層修正全 evidence-based；validation harness 1000+ simulation 驗 Type I + Power |
| 13 | cost 感知 | ✅ | Sprint 1A-γ 50-70 hr DESIGN + Sprint 4 60-80 hr + Sprint 7-8 60-80 hr + Y2 80-120 hr = 250-350 hr Y1+Y2；對齊 v5.8 §2 M9 200-280 hr range |
| 14 | 零外部成本 | ✅ | mSPRT + AVI 全本地 IMPL；不依賴 SaaS A/B testing platform |
| 15 | 多 agent 形式化協作 | ✅ | M9 dispatch 涉及 MIT / QC / PA / E1 / E4 / QA / FA 多 role |
| 16 | Portfolio > 孤立 trade | ✅ | cluster 2/3 cross-strategy reweight LAL 2；variant 不超 Strategist cap；portfolio-level 治理 |

---

## §14 關鍵文件指針

### Parent specs

- **ADR-0037**：`srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md`（5 Decisions ADR 權威；本 DESIGN spec 100% 對齊）
- **v5.8 execution plan**：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M9 line 319-355
- **PA dispatch consolidation**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（行 146-157 Sprint 1A-γ deliverable + 行 368 QA/QC reconcile）

### Sibling specs

- **V108 full DDL spec**：`srv/docs/execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md`（本 DESIGN spec land 後 V108 full DDL upgrade）
- **V103/V104 spec (hypotheses FK target)**：`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- **V110 M6 reward weight spec (Cluster 3 risk profile ref)**：`srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md`
- **M6 DESIGN spec**：`srv/docs/execution_plan/2026-05-21--m6_bayesian_reward_weight_design_spec.md`
- **M7 DESIGN spec (variant DECAY treated equal as same-strategy)**：`srv/docs/execution_plan/2026-05-21--m7_strategy_decay_design_spec.md`

### Amendments

- **AMD-2026-05-15-01 Stage 0R-4 framework**：`srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`（§4 variant Stage 路徑 100% 引用）
- **AMD-2026-05-09-03 Strategist Wide-Adjustment**：`srv/docs/governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md`（§2.3 Cluster 3 RuntimeMaxEnvelope 對齊）

### ADR cross-ref

- **ADR-0008 Decision Lease state machine**：`srv/docs/adr/0008-decision-lease-state-machine.md`（§5 per-assignment lease_id 綁定）
- **ADR-0021 Alpha Source Architecture Upgrade**：`srv/docs/adr/0021-alpha-source-architecture-upgrade.md`（§2.2 Cluster 2 signal source swap 是 R-1 Alpha Surface Bundle 變更）
- **ADR-0022 Strategist Cap**：`srv/docs/adr/0022-strategist-cap.md`（§5 fair execution clause 對齊）
- **ADR-0026 Direct Exploit Bypass CPCV**：`srv/docs/adr/0026-direct-exploit-bypass-cpcv.md`（§2.2 Cluster 2 Stage 0R replay 必含 CPCV）
- **ADR-0034 M1 Decision Lease LAL**：`srv/docs/adr/0034-decision-lease-layered-approval-lal.md`（§2.5 cluster-LAL 對齊矩陣引用 LAL 1/2/3）
- **ADR-0036 M8 anomaly + M10 Tier D blacklist**：`srv/docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（§3.8 反模式 (e) HMM/GARCH 黑名單適用 M9）
- **ADR-0038 M11 continuous counterfactual replay**：M9 variant outcome 對齊 M11 nightly replay 路徑（per §8）

### Skill cross-ref

- **`srv/.claude/skills/quant-strategy-design`**：§3 mSPRT + AVI + Bonferroni 對齊
- **`srv/.claude/skills/time-series-cv-protocol`**：§3.5 minimum sample power analysis + Embargo 對齊
- **`srv/.claude/skills/feature-engineering-protocol`**：§2.1.1 Cluster 1 shift(1) leak-free 紀律 + §2.2.1 Cluster 2 CPCV 紀律
- **`srv/.claude/skills/data-drift-detection`**：§2.3.1 Cluster 3 tail event drift 偵測
- **`srv/.claude/skills/db-schema-design-financial-time-series`**：V108 hypertable / chunk / partial index 規範對齊

### Memory cross-ref

- **memory `feedback_multi_role_strategic_review`**：§1.5 M9 是 multi-role adversarial review 工程化 framework 對應
- **memory `feedback_indicator_lookahead_bias`**：§2.1.1 Cluster 1 parameter sweep Stage 0R replay 必對齊 shift(1) leak-free
- **memory `project_2026_05_02_p0_sqlx_hash_drift`**：V108 SQL file land 必驗 sqlx checksum + Linux PG empirical dry-run
- **memory `feedback_v_migration_pg_dry_run`**：V108 full DDL Sprint 1A-γ IMPL 必走 Linux PG empirical dry-run

### Postmortem cross-ref

- **QA 5/20 W-C lesson v55 reframe**：§2.4.1 Cluster 4 exit logic Stage 0R replay 必驗 close maker / risk_exit attempt × fallback matrix

---

## §15 Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via D1 v5.8 §2 M9 ADD-per-operator DESIGN initial 已批（per PA report 行 22）| 2026-05-21 | ✅ APPROVED-pending-spec-land |
| MIT | 本 DESIGN spec 起草（對齊 ADR-0037 5 Decisions + 4 cluster 規範 + mSPRT+AVI+Bonferroni + variant Stage 路徑 + fair execution clause + preregistration + hash algorithm + M11 cross-ref + M7 integration + 7 AC + IMPL phase + Open Q × 5）| 2026-05-21 | ✅ Drafted v1 |
| QC | mSPRT + AVI + Bonferroni 校正方法 review + validation harness Type I/Power 1000+ simulation 對齊 + §3.5 公式 review | TBD（Sprint 1A-γ） | 🟡 PENDING |
| PA | V108 full DDL spec land 後 cross-ADR consistency 驗（與 ADR-0021 / 0022 / 0026 / 0034 / 0036 / 0038 不衝突）+ Open Q 1 (V107 type) + Open Q 4 (parallel test 上限) 決議 | TBD（Sprint 1A-γ） | 🟡 PENDING |
| QA | variant Stage 路徑（§4）+ fair execution clause（§5）對齊驗（Stage 不繞 5-gate / variant 不繞 Guardian） | TBD（Sprint 1A-γ） | 🟡 PENDING |
| E1 | V108 SQL file IMPL + ab_tests/assignments/results writer（Sprint 1A-γ + 3） | TBD（Sprint 1A-γ + 3） | 🟡 PENDING |
| E4 | M9-FRAMEWORK-VALIDATION harness IMPL（1000+ simulation under known distribution；per §3.9 + AC-7） | TBD（Sprint 3） | 🟡 PENDING |
| FA | Cluster 3 risk profile variant 對齊 RuntimeMaxEnvelope review + Cluster 2 signal source swap 對齊 ADR-0021 R-1 Alpha Surface Bundle + Open Q 5 (Copy Trading) | TBD（Sprint 7-8） | 🟡 PENDING |
| PM | Sprint 4 first Live A/B 啟用 gate 仲裁 + variant promotion to Stage 4 LAL 3 approval | TBD（Sprint 4 起 / per variant winner） | 🟡 PENDING |

---

**END M9 A/B Framework DESIGN spec draft v1（Sprint 1A-γ；對齊 ADR-0037 5 Decisions；待 V108 full DDL spec upgrade 同步 land）**

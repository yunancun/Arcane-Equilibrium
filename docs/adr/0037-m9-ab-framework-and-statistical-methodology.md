# ADR 0037: M9 A/B Testing Framework + Statistical Methodology — 4 Variant Cluster × i.i.d. 修正 × Variant Stage 路徑

Date: 2026-05-21
Status: **Proposed**（v5.8 thesis 接受 M9 為 13 module 之一；Sprint 1A-γ DESIGN 50-70 hr / Sprint 4 read-only logging 60-80 hr / Sprint 7-8 manual A/B 60-80 hr / Y2 auto-gate 80-120 hr 分階段 IMPL；本 ADR 鎖入 4 variant cluster 分類 + variant Stage 路徑 + mSPRT i.i.d. 修正 + fair execution clause）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via D1 v5.8 §2 M9 ADD-per-operator DESIGN initial 已批；PA 仲裁 reconcile「QA missing M9 variant Stage 路徑 vs QC M9 mSPRT i.i.d. 違反」為同 ADR 兩 cluster 合併處置）
Related: ADR-0021 (Alpha Source Architecture Upgrade) / ADR-0022 (Strategist Cap / Alpha-Source Orchestrator) / ADR-0026 (Direct Exploit Bypass CPCV) / ADR-0034 (M1 Decision Lease LAL) / ADR-0036 (M8 anomaly + M10 Tier D blacklist；mSPRT 對 HMM/GARCH 黑名單立場一致) / ADR-0038 (M11 continuous counterfactual replay；M9 variant outcome 對齊 replay 路徑) / AMD-2026-05-15-01 (Stage 0R-4 framework；本 ADR Decision 2 variant Stage 路徑引用) / V108 (ab_tests + ab_assignments + ab_results；本 ADR 為其 ADR 級邊界) / v5.8 §2 M9 (lines 319-355) / v5.8 §10 ADR roster line 751 / PA dispatch consolidation `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` 行 153 Sprint 1A-γ deliverable + 行 368 QA/QC reconcile / memory `feedback_multi_role_strategic_review` / `srv/.claude/skills/quant-strategy-design` / `srv/.claude/skills/time-series-cv-protocol`

## Context

### 起源 — v5.8 13 module 圖中 M9 為 DESIGN initial / IMPL phased

v5.8 主檔 §2 M9（lines 319-355）將「A/B Testing Framework」列為 13 module 之一，operator 2026-05-21 指示「design at initial stage even if IMPL delayed — 對後續接入更 friendly」（per PA report 行 22）。v5.8 §10 ADR roster 行 751 列 ADR-0037 為 Sprint 1A-γ 新增 ADR；但 Sprint 1A-β prerequisite checklist #5 同時要求 0036+0037+0038 sign-off（0036/0038 已 land；0037 缺）。本 ADR 補齊 0037。

### 為什麼 M9 是 4 variant cluster 而非單一 test type

v5.8 §2 M9 line 326-330 列 4 種 test types（parameter / sizing / trigger / overlay variant）。本 ADR Decision 3 將 4 種 test types **重整為 4 variant cluster**（不只是 test type，而是治理 + Stage 路徑 + IMPL 階段分類）：

| Cluster | v5.8 對應 test type | 治理意涵 |
|---|---|---|
| **Cluster 1**：parameter sweep | parameter variant | 同策略內參數調整（如 trailing_pct range / MA period）；變更最小 |
| **Cluster 2**：signal source swap | trigger variant 擴展 | 同策略換 alpha 源（如 M6 Bayesian → M4 self-supervised pattern miner）；變更中等 |
| **Cluster 3**：risk profile | sizing variant 擴展 | 同策略換 risk envelope（如 LAL Tier A vs Tier B sizing；ATR-based vs fixed SL/TP）；變更中等 |
| **Cluster 4**：exit logic | overlay variant 擴展 | 同策略換 exit 策略（如 fixed-time vs trailing vs micro-profit-lock variant）；變更中等 |

**為什麼分 4 cluster 不是 v5.8 原文 4 test type**：原 test type 是「測試什麼」分類（technical taxonomy）；cluster 是「治理 surface」分類（governance taxonomy）。Cluster 1-4 對應不同的 Stage 路徑 + LAL 級別 + ADR-0021 R-2 Strategist orchestrator surface；分 cluster 是為了 Sprint 4 read-only / Sprint 7-8 manual / Y2 auto-gate 三階段 IMPL 時 sub-agent 能對齊正確的治理紀律。

### QA missing variant Stage 路徑 vs QC mSPRT i.i.d. 假設違反（PA reconcile）

per PA report 行 368 reconcile：QA + QC 在 5.21 v5.8 audit 對 M9 提出兩個獨立 push back：

- **QA 提**：M9 variant 升 Stage 路徑不明 — 「variant 通過 A/B test 後是否直接 promote 到 Stage 4 / 是否走 AMD-2026-05-15-01 5-gate graduated canary / 是否 control + variant 共享同 Stage」
- **QC 提**：M9 mSPRT i.i.d. 假設違反 — 「sequential probability ratio test 假設樣本 i.i.d.，但 crypto perp fills 強自相關 + 異方差 + tail-fat；直接套 mSPRT 會 inflate Type I error 5-10x」

PA reconcile 為「同 ADR-0037 兩 cluster」：4 variant cluster × i.i.d. 修正 = 同 spec land；本 ADR Decision 2 + Decision 4 合併處置兩 push back。

### 為什麼 mSPRT i.i.d. 不適用 crypto perp + 必須修正

per QC 5.21 audit 數學理由 + memory `feedback_indicator_lookahead_bias` 警示：

1. **crypto perp fills 強自相關**：1m / 1h kline 自相關係數常 > 0.3；fills 在策略邏輯下進一步集中於特定 regime → variant 樣本不 i.i.d.
2. **異方差（volatility clustering）**：vol regime 切換時 fills 集中分布 → 樣本方差非 stationary，違反 mSPRT 推導前提
3. **tail-fat**：crypto returns 6h-24h kurtosis 常 > 10（normal = 3）；mSPRT 對 sub-Gaussian 假設破壞
4. **multiple comparisons**：4 variant cluster × 多 strategy × 多 symbol → 100+ 並行 A/B test；無 Bonferroni / FDR 校正 → false discovery rate 30-50%

本 ADR Decision 4 採 **mSPRT + Always-Valid Inference (Howard et al 2021 anytime-valid confidence sequence) + Bonferroni 校正 × variant 數** 三層修正，對齊 `time-series-cv-protocol` skill + `quant-strategy-design` skill。

### 為什麼不能跳過 M9 直接 promote variant

memory `feedback_multi_role_strategic_review` 證明 EDGE-DIAG-1 Phase 2 多 role adversarial review catch 3 個 unique blind spots；M9 是 alpha 歸因 + 參數驗證的對抗性 framework。無 M9 → variant promotion 走 single-strategy single-fork 路徑 → 無法區分「策略 alpha」vs「參數選擇 alpha」vs「regime luck」貢獻。對於 P0-EDGE-1 Y1 持續 negative edge 場景，M9 是後續 P0-EDGE-1 root closure 必要 framework。

### 為什麼 ADR-0037 必須在 Sprint 1A-γ DESIGN 階段 land

per PA dispatch packet 行 153：Sprint 1A-γ 50-70 hr DESIGN 包含 M9 schema + ADR-0037 + V108 spec doc 三件耦合；無 ADR-0037 → V108 spec doc 缺權威來源；sub-agent dispatch 時可能誤把 mSPRT 寫成 naive i.i.d. 版本 / 漏 variant Stage 路徑 / 漏 fair execution clause。**ADR-0037 是 Sprint 1A-γ DESIGN 派發前置條件**。

## Decision

**Proposed**：以下 5 項決策合併鎖入 M9 A/B framework 治理紀律。

### Decision 1 — V108 三表 Schema 草案（columns + pk + index）

V108 migration 包含三表，full DDL 走 Sprint 1A-γ V108 spec doc IMPL；本 ADR 鎖入 schema 高階草案 + 設計意圖。

#### 1.1 `learning.ab_tests` — A/B test 註冊表（preregistration）

| Column | Type | 設計意圖 |
|---|---|---|
| `test_id` | UUID PRIMARY KEY | A/B test 唯一識別 |
| `test_name` | text NOT NULL | 人類可讀名稱（如 `grid_trailing_pct_sweep_2026_06`）|
| `cluster_type` | text NOT NULL CHECK IN ('parameter_sweep', 'signal_source_swap', 'risk_profile', 'exit_logic') | 對齊 Decision 3 4 variant cluster |
| `strategy_name` | text NOT NULL | 被測策略 |
| `control_config_hash` | text NOT NULL | control 組 canonical config SHA-256 |
| `variant_configs_hash` | text[] NOT NULL | variant 組 canonical config SHA-256 array（支援多 variant） |
| `preregistered_at` | timestamptz NOT NULL DEFAULT now() | 必 preregister（per v5.8 §2 M9 line 343 governance） |
| `min_sample_size_per_arm` | integer NOT NULL | per power analysis 推導（per Decision 4） |
| `max_test_duration_days` | integer NOT NULL | 防止 test 無限延長 |
| `statistical_method` | text NOT NULL CHECK IN ('mSPRT_with_AVI', 'Bayesian_AB', 'fixed_horizon') | per Decision 4 statistical methodology |
| `bonferroni_correction_n` | integer NOT NULL | variant 數 + 並行 test 數 → Bonferroni α 校正分母 |
| `lal_level` | smallint NOT NULL | 對齊 ADR-0034 LAL（variant promotion 需要的 approval depth） |
| `created_by` | text NOT NULL | actor（agent role / operator） |
| `status` | text NOT NULL CHECK IN ('preregistered', 'running', 'concluded_efficacy', 'concluded_futility', 'concluded_inconclusive', 'aborted') | test lifecycle 狀態 |

**Index**：`(strategy_name, status)` 部分索引 WHERE `status = 'running'`；`(cluster_type, preregistered_at DESC)` 用於 governance review

#### 1.2 `learning.ab_assignments` — variant 分配紀錄（每 decision 分配）

| Column | Type | 設計意圖 |
|---|---|---|
| `assignment_id` | UUID PRIMARY KEY | 分配唯一識別 |
| `test_id` | UUID NOT NULL REFERENCES learning.ab_tests(test_id) | 對應 test |
| `decision_id` | UUID NOT NULL | 對應 trade decision（用於 join `trading.fills`） |
| `arm` | smallint NOT NULL CHECK arm >= 0 | 0 = control / 1+ = variant index |
| `assignment_ts` | timestamptz NOT NULL DEFAULT now() | 分配時點 |
| `assignment_method` | text NOT NULL CHECK IN ('deterministic_hash', 'stratified_random', 'sequential_balance') | per Decision 5 stratification |
| `stratification_keys` | jsonb NULL | symbol / regime cell / time-of-day 等分層 keys |
| `lease_id` | text NOT NULL | 對齊 ADR-0008 Decision Lease（每 assignment 必綁 lease）|

**Index**：`(test_id, arm)` 用於 sample size 統計；`(decision_id)` UNIQUE 防同 decision 雙重分配

#### 1.3 `learning.ab_results` — variant 統計輸出（per assignment + per evaluation cadence）

| Column | Type | 設計意圖 |
|---|---|---|
| `result_id` | UUID PRIMARY KEY | |
| `test_id` | UUID NOT NULL REFERENCES learning.ab_tests(test_id) | |
| `arm` | smallint NOT NULL | |
| `evaluation_ts` | timestamptz NOT NULL DEFAULT now() | mSPRT sequential update 時點 |
| `n_samples` | integer NOT NULL | 累積樣本數 |
| `net_return_bps_mean` | numeric NOT NULL | per assignment 累積平均 |
| `net_return_bps_std` | numeric NOT NULL | per assignment 累積標準差 |
| `cumulative_pnl_usd` | numeric NOT NULL | |
| `mSPRT_statistic` | numeric NULL | per Decision 4 mSPRT 累積統計量 |
| `AVI_lower_ci` / `AVI_upper_ci` | numeric NULL | Always-Valid Inference anytime-valid confidence interval |
| `bonferroni_adjusted_p` | numeric NULL | Bonferroni 校正後 p-value |
| `efficacy_boundary_crossed` | boolean NOT NULL DEFAULT FALSE | 是否突破 efficacy boundary |
| `futility_boundary_crossed` | boolean NOT NULL DEFAULT FALSE | 是否突破 futility boundary |

**Index**：`(test_id, evaluation_ts DESC)` 用於最新評估查詢；`hypertable`（per v5.8 §9 V107 / V109 / V113 hypertable 模式）；retention 90d active + archive

**注**：full DDL（含 NOT NULL 強制 / FK ON DELETE / 詳細 CHECK constraint / hypertable chunk 時長等）走 V108 spec doc Sprint 1A-γ IMPL；本 ADR 不重寫 DDL。

### Decision 2 — Variant Stage 路徑（per AMD-2026-05-15-01 對齊）

回應 QA push back「variant 升 Stage 路徑不明」。

| 元素 | 設計 |
|---|---|
| **核心原則** | **Control + variant 共享相同 5-gate Stage 0→4 graduated canary**（per AMD-2026-05-15-01）；variant 不繞 Stage 升級紀律 |
| Stage 0R replay preflight | control + variant 各自走 Stage 0R replay；variant 必通過 replay preflight 才進入 Stage 0 shadow |
| Stage 0 shadow | control + variant 同時跑 shadow；M11 nightly counterfactual replay 對齊（per ADR-0038） |
| Stage 1 demo small | control + variant 同時跑 demo；fill 樣本累積至 V108 `ab_assignments`；mSPRT sequential update 啟動 |
| Stage 2 demo full | control + variant 同時跑 demo full size；min_sample_size_per_arm 達標 → mSPRT efficacy / futility evaluation |
| Stage 3 live canary | **若 variant efficacy boundary crossed + Bonferroni-adjusted p < 0.05 → variant 進 live canary（與 control 並行）**；variant 仍綁同 lease bucket / 同 LAL Tier / 同 budget cap |
| Stage 4 live full | **A/B test 結論 = variant winner**（per Decision 4 statistical conclusion）→ operator approval（LAL 3 new strategy promotion）→ variant promote to Stage 4 取代 control |
| **Variant Stage 限制** | (a) variant 不能單獨進 Stage X 而 control 留在 Stage Y（除非 control 觸發 decay per ADR-0036）；(b) variant Stage 升級 == 同時 control + variant 升；(c) variant 終止（test concluded futility / aborted）= variant 回到 dormant + control 繼續 |
| **Test 終止後處置** | (a) efficacy = variant promote、control demote to Stage 0 shadow（保留 baseline 比較）；(b) futility = variant terminate、control 維持 Stage X；(c) inconclusive = 延長 test OR operator manual terminate（per Decision 5 max duration） |

**反模式（明示禁止）**：

- (a) variant 不經 Stage 0R replay 直接進 Stage 1 demo（繞 AMD-2026-05-15-01 replay preflight）
- (b) variant 在 control 處於 Stage 2 時提前進 Stage 3 live canary（Stage 跨級）
- (c) variant 經 5-gate auto path 繞 operator approval 進 Stage 4（per ADR-0034 LAL 3 永遠 operator approve；M9 不開新 auto path）

### Decision 3 — 4 Variant Cluster 規範

每 cluster 明示治理紀律 + Stage 路徑 + LAL 級別 + IMPL 階段。

#### 3.1 Cluster 1 — Parameter Sweep

| 元素 | 設計 |
|---|---|
| 範例 | trailing_pct range / MA period / ATR multiplier / Donchian channel N |
| LAL 級別 | **LAL 1** (intra-strategy reparam) — variant 是同策略內參數調整 |
| 變更深度 | 最淺（只動 numerical hyperparameter） |
| Stage 路徑 | per Decision 2 5-gate；variant Stage 0R replay 通常與 control 高度相似（差參數），但 leak-free shift(1) 紀律必生效（per memory `feedback_indicator_lookahead_bias`） |
| IMPL 階段 | Sprint 4 read-only logging 可優先支援（最低風險）|
| 預期數量 | 每策略 5-15 個並行 sweep（高 Bonferroni N） |

#### 3.2 Cluster 2 — Signal Source Swap

| 元素 | 設計 |
|---|---|
| 範例 | 同策略換 alpha 源（如 M6 Bayesian → M4 self-supervised pattern miner / M6 Bayesian → 既有 LightGBM baseline） |
| LAL 級別 | **LAL 2** (cross-strategy reweight) — 變更影響 alpha source registry，跨策略可能相互影響 |
| 變更深度 | 中等（變更 alpha 源但保策略結構） |
| Stage 路徑 | per Decision 2 5-gate；Stage 0R replay 必驗 alpha 源切換後 leak-free + ADR-0026 CPCV 紀律 |
| IMPL 階段 | Sprint 7-8 manual A/B（需 M4 land 後才能 swap）|
| 預期數量 | 每策略 1-3 個並行 swap |

#### 3.3 Cluster 3 — Risk Profile

| 元素 | 設計 |
|---|---|
| 範例 | LAL Tier A (3%) vs LAL Tier B (1.5%) sizing / ATR-based SL/TP vs fixed SL/TP / max_open_positions 25 vs 15 |
| LAL 級別 | **LAL 2** (cross-strategy reweight) — risk envelope 變更影響 portfolio aggregator |
| 變更深度 | 中等（變更 risk envelope 但保策略 entry/exit 邏輯） |
| Stage 路徑 | per Decision 2 5-gate；variant 必對齊 AMD-2026-05-09-03 RuntimeMaxEnvelope（不超範圍） |
| IMPL 階段 | Sprint 7-8 manual A/B |
| 預期數量 | 每策略 1-2 個並行 risk profile test |

#### 3.4 Cluster 4 — Exit Logic

| 元素 | 設計 |
|---|---|
| 範例 | fixed-time exit vs trailing exit vs physical_micro_profit_lock_v2 variant / partial TP vs full TP |
| LAL 級別 | **LAL 1** (intra-strategy reparam) — 變更 exit 但保 entry signal |
| 變更深度 | 中等（變更 exit logic） |
| Stage 路徑 | per Decision 2 5-gate；Stage 0R replay 必驗 exit logic 不破 close maker / risk_exit attempt × fallback matrix（per QA 5/20 W-C lesson v55 reframe） |
| IMPL 階段 | Sprint 4 read-only logging（部分）+ Sprint 7-8 manual A/B（完整） |
| 預期數量 | 每策略 1-3 個並行 exit variant |

**Cluster-Stage-LAL 對齊矩陣（核心 governance artifact）**：

| Cluster | LAL 級別 | 主 IMPL 階段 | Stage 起始 | Stage 終止 promotion 條件 |
|---|---|---|---|---|
| 1 parameter sweep | LAL 1 | Sprint 4 | Stage 0R | 同 control Stage 升級 + variant winner 觸發 operator approval |
| 2 signal source swap | LAL 2 | Sprint 7-8 | Stage 0R | 同 control Stage 升級 + variant winner 觸發 operator approval |
| 3 risk profile | LAL 2 | Sprint 7-8 | Stage 0R | 同 control Stage 升級 + variant winner 觸發 operator approval |
| 4 exit logic | LAL 1 | Sprint 4 部分 / Sprint 7-8 完整 | Stage 0R | 同 control Stage 升級 + variant winner 觸發 operator approval |

### Decision 4 — Statistical Methodology（mSPRT + Always-Valid Inference + Bonferroni）

回應 QC push back「mSPRT i.i.d. 假設違反」。

| 元素 | 設計 |
|---|---|
| 核心方法 | **mSPRT + Always-Valid Inference (AVI, Howard et al 2021 anytime-valid confidence sequence)** + **Bonferroni 校正** × variant 數 + 並行 test 數 |
| 為什麼用 mSPRT | sequential testing 允許 early stopping（efficacy / futility）；不需固定 horizon；對 small effect size 樣本效率優於 fixed-horizon |
| **為什麼用 AVI 而非裸 mSPRT** | mSPRT 推導假設 i.i.d. + sub-Gaussian；crypto perp 違反兩者；**AVI (Howard et al 2021) 提供 anytime-valid confidence sequence 不依賴 i.i.d.**；可在 strong autocorrelation + heavy tail 下保 Type I error ≤ α |
| **AVI 具體實作** | per `quant-strategy-design` skill `time-series-cv-protocol` skill；具體 confidence sequence 公式走 Sprint 1A-γ V108 spec doc IMPL（不在本 ADR 鎖死數學細節，留 amendment 空間） |
| Bonferroni 校正 | α / (variant_count × parallel_test_count)；如 5 variant × 20 並行 test = 100 → α=0.05 校正後 = 0.0005 per test |
| **最小樣本 derive 公式** | per `time-series-cv-protocol` skill + `quant-strategy-design` skill；effect size + power（默認 0.8）+ Type I error（Bonferroni 校正後）三參數 → minimum sample；具體公式走 V108 spec doc |
| **block bootstrap 配套** | 對應 ADR-0036 Decision 4 walk-forward + block bootstrap；M9 evaluation 時 mSPRT statistic 對應 sampling distribution 用 block bootstrap 5-10 day block 估計，對 vol clustering robust |
| 替代方案 | Bayesian A/B（adoption gate per Decision 5）— 適用樣本量極小場景；fixed-horizon test — 適用變更深度小場景 |
| Test type-I error monitoring | Sprint 1A-γ V108 spec doc 必含 **M9 framework validation harness**（per PA report 行 104 H-17 §M9-FRAMEWORK-VALIDATION）：1000+ simulation under known distribution 驗 Type I + Power |

**反模式（明示禁止）**：

- (a) 使用 naive Welch's t-test 或 unadjusted mSPRT 不做 Bonferroni 校正（false discovery rate 30-50%）
- (b) Test 中途任意 peek 不走 sequential testing protocol（peeking error）
- (c) 不 preregister effect size + power → post-hoc 找顯著結果（HARKing — Hypothesizing After Results Known）
- (d) min_sample_size 寫死 magic number（如 N=100）不從 power analysis derive
- (e) 使用 HMM / GARCH 估 variance structure（per ADR-0036 Decision 1 黑名單適用 M9）

### Decision 5 — Fair Execution Clause（防 variant 偷跑）

對齊 §二 原則 4 策略不繞風控 + 原則 9 雙重防線。

| 元素 | 設計 |
|---|---|
| **同 lease bucket** | control + variant 共享同 Decision Lease bucket（per ADR-0008 + ADR-0034 LAL gate）；不允許 variant 繞 lease 走 |
| **同 LAL Tier** | control + variant 共享同 LAL 級別（per Decision 3 cluster-LAL 對齊）；不允許 variant 在 LAL 1 而 control 在 LAL 2（除非 cluster 設計明示） |
| **同 budget cap** | control + variant 共享同 daily / weekly budget；budget 由 ADR-0034 LAL 4 預設；variant 不能單獨擴 budget |
| **同 Guardian gate** | control + variant 都經 Guardian 5-gate kill；任一 gate fail → control + variant 同時 freeze（fail-closed scope = test 級而非 arm 級） |
| **assignment 紀錄** | per Decision 1 `ab_assignments` 表必綁 `lease_id`；audit trail 完整 |
| **禁止 variant supervisor escalation** | variant 不能繞 supervisor 路徑優先觸發 risk override（如 variant 用 wider SL/TP 預設掩蓋 control 的 PnL signal） |

**反模式（明示禁止）**：

- (a) variant 走獨立 lease bucket 繞 LAL gate
- (b) variant 用更大 budget cap 偷跑（artificially 增 sample size）
- (c) variant Guardian fail-closed 只 freeze variant arm 不 freeze test（test integrity 破壞）

### Decision 6 — Sprint 4 First Live A/B 啟用 Gate

per v5.8 §10.5 Sprint 4 first Live precondition + 本 ADR Cluster IMPL 階段：

| 條件 | 設計 |
|---|---|
| **Sprint 4 W17.5-20.5 first Live 啟用 A/B 前** | 必通過 v5.8 §10.5 4+1 條 P0 precondition（P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 / 5-gate live boundary）|
| Sprint 4 read-only logging 範圍 | Cluster 1 parameter sweep + Cluster 4 exit logic（最低風險 cluster） |
| Sprint 7-8 manual A/B 範圍 | + Cluster 2 signal source swap + Cluster 3 risk profile |
| Y2 auto-test scheduling | 全 4 cluster；但 variant promotion to Stage 4 永遠 operator approval（LAL 3） |
| **首次 Live A/B 啟動 timing** | Sprint 4 first Live 後 + first cohort 累積 ≥ min_sample_size_per_arm 為 baseline → 啟動第一個 Cluster 1 A/B test |
| cohort sample 切片成本 | 每 strategy live cohort 樣本 split 為 control / variant → /2 ~ /4；對單策略 Sharpe 估計 noise 上升；mitigation = per Decision 4 min_sample_size_per_arm 從 power analysis derive，不從 magic number 設 |

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **不立 ADR-0037，只在 v5.8 §10 列名** | v5.8 §10 高階索引無法替代 ADR 級邊界；Sprint 1A-γ V108 spec doc + sub-agent dispatch 缺權威，可能誤把 mSPRT 寫成 naive i.i.d. 版本（false discovery 30-50%）/ 漏 variant Stage 路徑 / 漏 fair execution clause |
| **使用 naive Welch's t-test + fixed horizon** | crypto perp 樣本不 i.i.d. + 異方差；fixed horizon 對 small effect 樣本效率差 + 不允許 early stopping；不適用 4 variant cluster 並行 100+ test 場景 |
| **使用裸 mSPRT 不加 AVI 修正** | 直接違反 QC 5.21 push back；i.i.d. + sub-Gaussian 假設 crypto perp 不滿足；Type I error 5-10x inflation |
| **使用 Bayesian A/B 取代 mSPRT** | Bayesian 適用樣本量極小場景 + 主觀 prior；4 variant cluster × 100+ 並行 test 場景下 prior 校準難；可作為 Decision 4 替代方案保留但非主路徑 |
| **允許 variant 走獨立 Stage 路徑（繞 control）** | 違反 AMD-2026-05-15-01 5-gate graduated canary 設計意圖；variant 獨立進 Stage = M9 退化為單策略 fork，無對抗性 framework 意義 |
| **不分 4 cluster，treat all variant 一視同仁** | 違反 cluster-LAL 對齊紀律；Sprint 4 read-only 階段若不分 cluster，所有 variant 都用 LAL 2 處理 → 過度治理 cost；分 cluster 是為了 incremental IMPL + 對齊既有 ADR-0034 LAL 紀律 |
| **不寫 Decision 5 fair execution clause** | variant 偷跑反模式（同 lease bucket / 同 budget / 同 LAL）若不明示禁止，sub-agent IMPL 時可能誤開新 lease bucket 繞 LAL gate；fair execution clause 是 §二 原則 4 落地 |
| **Decision 4 mSPRT validation harness 推到 Sprint 4 IMPL** | Sprint 1A-γ DESIGN 階段就明示 1000+ simulation harness 是 v5.8 §SLA-STRESS § (per H-17) 的 M9-FRAMEWORK-VALIDATION sub-章節要求；validation harness 是 framework 信任基礎，不可推遲 |
| **Sprint 4 first Live 直接啟動 Cluster 2 signal source swap** | 違反 Decision 6 incremental IMPL + Decision 3 Cluster 2 「需 M4 land 後」紀律；Sprint 4 first Live 風險面已大（P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4），M9 啟動只走 Cluster 1 + 4 是保守路徑 |

## Consequences

### Positive

- **v5.8 §10 ADR list 完整性** — 7 ADR 名單（0034-0040 + 0041）皆有對應 ADR draft；Sprint 1A-β D+5~D+6 派發 readiness 12-check #5 可勾
- **QA + QC 5.21 v5.8 audit 兩 push back 一次性 reconcile** — variant Stage 路徑（Decision 2）+ mSPRT i.i.d. 修正（Decision 4）合併處置；無需再開兩 ADR
- **4 variant cluster 分類紀律** — Sprint 4 / Sprint 7-8 / Y2 三階段 IMPL 對應 cluster 1+4 / +cluster 2+3 / 全 cluster；incremental scope 紀律明示
- **cluster-LAL 對齊矩陣** — sub-agent dispatch 時零 ambiguity，可直接讀矩陣判斷 variant promotion 需要的 approval depth
- **statistical methodology 對齊 crypto perp 微結構** — mSPRT + AVI + Bonferroni 三層修正對齊 QC 5.21 audit 數學理由；validation harness 1000+ simulation 是信任基礎
- **可拆參數歸因** — 對 P0-EDGE-1 持續 negative edge 場景，M9 區分「策略 alpha」/「參數 alpha」/「regime luck」貢獻；是 Y2 root closure 必要 framework
- **降低 single-strategy alpha 估計噪音** — control + variant 並行同 cohort 內 → 樣本對齊；regime / time-of-day stratification 控制 confounders
- **fair execution clause** — 對齊 §二 原則 4 + 原則 9；variant 不繞風控 + 同 lease bucket / LAL Tier / budget cap

### Negative / Risk

- **cohort 切片成本（每 strategy live cohort 樣本 /2 ~ /4）** — 單策略 Sharpe 估計 noise 上升；mitigation = Decision 4 min_sample_size_per_arm 從 power analysis derive；Sprint 4 first Live 後 cohort 累積 ≥ min_sample baseline 再啟動 A/B
- **mSPRT + AVI IMPL 複雜度高** — 需 `quant-strategy-design` skill + `time-series-cv-protocol` skill 對齊 + 1000+ simulation validation harness；mitigation = Sprint 1A-γ V108 spec doc full DDL + 公式走 IMPL，不寫死本 ADR
- **Bonferroni 校正 over-conservative 風險** — 100+ 並行 test 校正後 α=0.0005 可能 power < 0.5；mitigation = (a) 用 FDR (Benjamini-Hochberg) 替代 Bonferroni 為 amendment 選項；(b) 限制並行 test 數（per Decision 1 max parallel test count 由 PA 仲裁）
- **mSPRT validation harness 1000+ simulation 工時** — Sprint 1A-γ 50-70 hr DESIGN budget 內可能緊張；mitigation = validation harness 推 Sprint 1A-γ 末 + Sprint 3 一起 land；Sprint 1A-γ 只交 spec doc + harness scaffolding
- **Cluster 2 signal source swap 依賴 M4 land** — Sprint 7-8 IMPL 受 M4 stage 1 (Sprint 2-3) 進度影響；mitigation = M4 spec doc `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m4_minimum_bar_and_leakage_protocol.md` 已 land；M4 stage 1 開展正常即不阻 Cluster 2
- **variant Stage 路徑與 ADR-0030 Copy Trading evaluation 互動** — Copy Trading follower 永遠 control variant（per PA report 行 95 H-5）；mitigation = Decision 2 明示 control + variant 共享同 Stage；Copy Trading follower 不參與 variant arm

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| v5.8 §2 M9 (lines 319-355) | **本 ADR 為 v5.8 §2 M9 module 治理 ADR 級落地**；4 test types 重整為 4 variant cluster |
| ADR-0008 Decision Lease state machine | **Decision 1 `ab_assignments` 表必綁 `lease_id`**；audit trail 完整 |
| ADR-0021 Alpha Source Architecture Upgrade | **Cluster 2 signal source swap 是 R-1 Alpha Surface Bundle 變更**；M9 是 R-2 Strategist orchestrator 對抗性驗證 framework |
| ADR-0022 Strategist Cap | **variant 不超 Strategist cap**（per §二 原則 16 portfolio > 孤立 trade）；fair execution clause Decision 5 對齊 |
| ADR-0026 Direct Exploit Bypass CPCV | **Cluster 2 signal source swap Stage 0R replay 必含 CPCV**（per ADR-0026 + `time-series-cv-protocol` skill） |
| ADR-0034 M1 Decision Lease LAL | **Decision 3 cluster-LAL 對齊矩陣引用 LAL 1/2/3**；variant promotion to Stage 4 走 LAL 3 operator approval |
| ADR-0036 M8 anomaly + M10 Tier D blacklist | **Decision 4 反模式 (e) 引用 ADR-0036 Decision 1 黑名單適用 M9**（HMM / GARCH 不可用於 variance structure 估計）|
| ADR-0038 M11 continuous counterfactual replay | **Decision 2 Stage 0 shadow + Stage 1 demo variant outcome 對齊 M11 nightly replay**；M11 divergence flag → M9 test inconclusive |
| AMD-2026-05-15-01 Stage 0R-4 framework | **Decision 2 variant Stage 路徑 100% 引用此 framework**；control + variant 共享同 5-gate canary |
| AMD-2026-05-09-03 Strategist Wide-Adjustment | **Decision 3 Cluster 3 risk profile variant 必對齊 RuntimeMaxEnvelope**；不超範圍 |
| V108 spec doc（Sprint 1A-γ） | **本 ADR 為 V108 schema 設計權威**；V108 full DDL spec cite 本 ADR Decision 1 |
| `srv/.claude/skills/quant-strategy-design` | **Decision 4 mSPRT + AVI + Bonferroni 對齊此 skill SOP** |
| `srv/.claude/skills/time-series-cv-protocol` | **Decision 4 minimum sample power analysis + CPCV 對齊此 skill SOP** |
| memory `feedback_multi_role_strategic_review` | **M9 是 multi-role adversarial review 的工程化 framework 對應**；對 P0-EDGE-1 root closure 必要 |
| memory `feedback_indicator_lookahead_bias` | **Decision 3 Cluster 1 parameter sweep Stage 0R replay 必對齊 shift(1) leak-free 紀律** |
| QA 5.21 W-C lesson v55 reframe | **Decision 3 Cluster 4 exit logic Stage 0R replay 必驗 close maker / risk_exit attempt × fallback matrix**（per PM template §3.1） |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | variant 走同一 control trade entry 路徑；不創旁路；fair execution clause Decision 5 明示 |
| 2 | 讀寫分離 | ✅ | `ab_tests` / `ab_assignments` / `ab_results` 三表純 learning surface；variant 執行透過 Strategist + Decision Lease |
| 3 | AI 輸出 ≠ 命令 | ✅ | A/B test 結論是 evidence，不直接 promote；variant winner 必經 operator approval (LAL 3) |
| 4 | 策略不繞風控 | ✅ | Decision 5 fair execution clause 明示同 Guardian gate；variant fail-closed scope = test 級而非 arm 級 |
| 5 | 生存 > 利潤 | ✅ | Decision 6 Sprint 4 first Live A/B 啟用前必通過 §10.5 P0 precondition；防 P0-EDGE-1 阻塞期間啟動 A/B 放大失血 |
| 6 | 失敗默認收縮 | ✅ | mSPRT + AVI futility boundary → test 自動 terminate；Decision 5 任一 Guardian gate fail → control + variant 同時 freeze |
| 7 | 學習 ≠ live | ✅ | Stage 0R replay → Stage 0 shadow → Stage 1 demo → Stage 2 demo full → Stage 3 live canary → Stage 4 live full；evidence 累積路徑明確 |
| 8 | 交易可解釋 | ✅ | per-assignment `lease_id` 綁定 + Decision 1 三表完整 audit trail；test preregistration + statistical method 透明 |
| 9 | 雙重防線 | ✅ | mSPRT efficacy / futility + Bonferroni 校正 + Guardian gate + 5-gate canary = 多層 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | `ab_assignments` = 事實（per decision 分配）；`ab_results` mSPRT statistic = 推論（per Decision 4 statistical methodology）；preregistered effect size = 假設 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | A/B test preregistration + execution 在 P0/P1 內自主；variant promotion 走 LAL 3 operator approval |
| 12 | Evidence-based evolution | ✅ | mSPRT + AVI + Bonferroni 三層修正全 evidence-based；validation harness 1000+ simulation 驗 Type I + Power |
| 13 | cost 感知 | ✅ | Sprint 1A-γ 50-70 hr DESIGN + Sprint 4 60-80 hr + Sprint 7-8 60-80 hr + Y2 80-120 hr = 250-350 hr Y1+Y2；對齊 v5.8 §2 M9 200-280 hr range |
| 14 | 零外部成本 | ✅ | mSPRT + AVI 全本地 IMPL；不依賴 SaaS A/B testing platform |
| 15 | 多 agent 形式化協作 | ✅ | M9 dispatch 涉及 MIT / QC / PA / E1 / E4 / QA / FA 多 role；per Sign-off table |
| 16 | Portfolio > 孤立 trade | ✅ | cluster 2/3 cross-strategy reweight LAL 2；variant 不超 Strategist cap；portfolio-level 治理 |

## Cross-References

- **v5.8 §2 M9 A/B Testing Framework**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:319-355`（本 ADR module 來源）
- **v5.8 §3 Sprint 1A-γ deliverable**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:507`（M9 50-70 hr 對應）
- **v5.8 §9 V108 schema**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:789`（V108 ab_tests + ab_assignments + ab_results；本 ADR Decision 1 設計權威）
- **v5.8 §10 ADR roster**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:751`（ADR-0037 列入 7 新 ADR 名單）
- **v5.8 §10.5 P0 precondition**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:827`（Sprint 4 first Live A/B 啟用 gate）
- **ADR-0008 Decision Lease state machine**：`docs/adr/0008-decision-lease-state-machine.md`（per-assignment lease_id 綁定）
- **ADR-0021 Alpha Source Architecture Upgrade**：`docs/adr/0021-alpha-source-architecture-upgrade.md`（cluster 2 signal source swap 是 R-1 Alpha Surface Bundle 變更）
- **ADR-0022 Strategist Cap**：`docs/adr/0022-strategist-cap.md`（fair execution clause Decision 5 對齊）
- **ADR-0026 Direct Exploit Bypass CPCV**：`docs/adr/0026-direct-exploit-bypass-cpcv.md`（cluster 2 Stage 0R replay 必含 CPCV）
- **ADR-0034 M1 Decision Lease LAL**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（cluster-LAL 對齊矩陣 + variant promotion LAL 3）
- **ADR-0036 M8 anomaly + M10 Tier D blacklist**：`docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（Decision 4 反模式 (e) HMM/GARCH 黑名單適用 M9）
- **ADR-0038 M11 continuous counterfactual replay**：M9 variant outcome 對齊 M11 nightly replay 路徑
- **AMD-2026-05-15-01 Stage 0R-4 framework**：`docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`（Decision 2 variant Stage 路徑 100% 引用）
- **AMD-2026-05-09-03 Strategist Wide-Adjustment**：`docs/governance_dev/amendments/2026-05-09--strategist_wide_adjustment_skill.md`（cluster 3 RuntimeMaxEnvelope 對齊）
- **V108 spec doc（Sprint 1A-γ）**：`docs/execution_plan/2026-05-21--v108_ab_framework_schema_spec.md`（待 land；本 ADR 為其設計權威）
- **`srv/.claude/skills/quant-strategy-design`**：Decision 4 statistical methodology 對齊
- **`srv/.claude/skills/time-series-cv-protocol`**：Decision 4 minimum sample power analysis + CPCV 對齊
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（行 153 Sprint 1A-γ deliverable + 行 368 QA/QC reconcile）
- **PM final verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`（D1 ADD-per-operator M9 DESIGN initial 已批）
- **memory `feedback_multi_role_strategic_review`**：M9 是 multi-role adversarial review 工程化 framework 對應
- **memory `feedback_indicator_lookahead_bias`**：cluster 1 parameter sweep Stage 0R replay 必對齊 shift(1) leak-free
- **memory `project_2026_05_02_p0_sqlx_hash_drift`**：V108 SQL file land 必驗 sqlx checksum + Linux PG empirical dry-run
- **`feedback_v_migration_pg_dry_run.md`**：V108 full DDL Sprint 1A-γ IMPL 必走 Linux PG empirical dry-run
- **Howard et al 2021**："Time-uniform, nonparametric, nonasymptotic confidence sequences"（AVI anytime-valid confidence sequence 學術 reference）
- **Benjamini-Hochberg 1995**：FDR 校正（Decision 4 Bonferroni 替代方案參考）

## Engineering Scope Reference

| Sprint | Item | Workload |
|---|---|---|
| Sprint 1A-γ | V108 spec doc（ab_tests + ab_assignments + ab_results full DDL）+ ADR-0037 + M9-FRAMEWORK-VALIDATION harness scaffolding | 50-70 hr |
| Sprint 3 | mSPRT + AVI validation harness 1000+ simulation 完成 | 30-50 hr |
| Sprint 4 | Cluster 1 parameter sweep + Cluster 4 exit logic read-only logging（first Live A/B precondition 通過後）| 60-80 hr |
| Sprint 7-8 | Cluster 2 signal source swap + Cluster 3 risk profile manual A/B（M4 land 後）| 60-80 hr |
| Y2 | Auto-test scheduling + auto-promotion gate（含 LAL 3 operator approval workflow） | 80-120 hr |

**Total IMPL across Y1-Y2**: 280-400 hr（含 validation harness + 全 4 cluster + auto-gate）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via D1 v5.8 §2 M9 ADD-per-operator DESIGN initial 已批 | 2026-05-21 | ✅ APPROVED-pending-commit |
| TW | 本文件起草（v5.8 §10 ADR-0037 補位 + Sprint 1A-β prerequisite #5 + QA/QC reconcile + Sprint 1A-γ M9 dispatch 邊界） | 2026-05-21 | ✅ Drafted |
| QC | mSPRT + AVI + Bonferroni 校正方法 review + validation harness Type I/Power 1000+ simulation 對齊 | TBD（Sprint 1A-γ） | 🟡 PENDING |
| MIT | V108 三表 schema + cluster-LAL 對齊矩陣 review + min_sample_size power analysis 公式對齊 | TBD（Sprint 1A-γ） | 🟡 PENDING |
| PA | V108 spec doc land 後 cross-ADR consistency 驗（與 ADR-0021 / 0022 / 0026 / 0034 / 0036 / 0038 不衝突） | TBD（Sprint 1A-γ） | 🟡 PENDING |
| QA | variant Stage 路徑 + fair execution clause 對齊驗（Stage 不繞 5-gate / variant 不繞 Guardian） | TBD（Sprint 1A-γ） | 🟡 PENDING |
| E1 | V108 SQL file IMPL + ab_tests/assignments/results writer | TBD（Sprint 1A-γ + 3） | 🟡 PENDING |
| E4 | M9-FRAMEWORK-VALIDATION harness IMPL（1000+ simulation under known distribution） | TBD（Sprint 3） | 🟡 PENDING |
| FA | cluster 3 risk profile variant 對齊 RuntimeMaxEnvelope review + cluster 2 signal source swap 對齊 ADR-0021 R-1 Alpha Surface Bundle | TBD（Sprint 7-8） | 🟡 PENDING |
| PM | Sprint 4 first Live A/B 啟用 gate 仲裁 + variant promotion to Stage 4 LAL 3 approval | TBD（Sprint 4 起 / per variant winner） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0037 — M9 A/B Testing Framework + Statistical Methodology: V108 三表 schema 草案 + 4 Variant Cluster 規範 + Variant Stage 路徑（AMD-2026-05-15-01 graduated canary）+ mSPRT + Always-Valid Inference + Bonferroni 校正 + Fair Execution Clause + Sprint 4 First Live A/B Gate (Proposed per 2026-05-21 v5.8 §10 ADR roster 一致性 + Sprint 1A-β prerequisite #5 補位 + PA reconcile QA missing variant Stage 路徑 + QC mSPRT i.i.d. 違反 兩 push back 合併處置)*

---
spec: M6 — Bayesian Reward Weight Tuning Module DESIGN Spec
date: 2026-05-21
author: MIT (Sprint 1A-β CRITICAL module DESIGN; sibling 至 V110 schema spec)
phase: v5.8 Sprint 1A-β module DESIGN（一階段 deliverable；不寫 IMPL code、不寫 DDL）
status: SPEC-DRAFT-V1（MIT 起草；待 PA C9 PG dry-run 補資料 + V108/V113 sibling spec 對齊後 → SPEC-FINAL）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M6 (line 219-251)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §HIGH H-2 (GP kernel + acquisition function + iter budget + 30% rollback 累積 cap mandate)
  - srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md (V110 schema full DDL — sibling，本 spec 引用 column 不重定義)
  - srv/docs/adr/0021-alpha-source-architecture-upgrade.md (Alpha Surface Bundle reference)
companion specs:
  - srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md (M1 LAL 697 行；本 spec §9 weight tuning → LAL Tier 2-3 audit 對接)
  - srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md (M11 619 行；本 spec §7 weight variant fair execution audit 對接)
  - srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md (M7 V113 placeholder；本 spec §8 M6 ↔ M7 decay integration)
  - srv/docs/execution_plan/2026-05-21--v108_m9_ab_testing_framework_schema_spec.md (M9 V108 Sprint 1A-γ placeholder；本 spec §7 weight variant → cluster 3 risk profile)
skill 引用:
  - srv/.claude/skills/quant-strategy-design/SKILL.md (策略設計 alpha 8 來源 framework；本 spec §10 walk-forward 對齊)
  - srv/.claude/skills/walk-forward-validation-protocol/SKILL.md (purge + embargo + DSR + PSR；本 spec §10 規範)
  - srv/.claude/skills/time-series-cv-protocol/SKILL.md (MIT 視角 ML 訓練 CV；本 spec §10 CV 設計)
  - srv/.claude/skills/feature-engineering-protocol/SKILL.md (leakage 6 維度；本 spec §10.5 對齊)
scope: M6 Bayesian reward weight tuning module 行為設計 + 算法選擇 + 整合接口 + 5-7 acceptance criteria + IMPL phase split；不寫 V110 DDL（sibling spec 已 land）/ 不寫 IMPL Rust/Python code（Sprint 7+ Advisory 工作）/ 不修 V108/V113 placeholder
---

# M6 Bayesian Reward Weight Tuning Module DESIGN Specification

## §0 TL;DR

- **M6 取代 v5.7 manual-set reward weight**：v5.7 Auto-Allocator reward function 用 manual-tuned 5 λ；M6 用 Bayesian optimization (BO) 從 last 6 mo outcome 反向校準。
- **5 λ 維度（per operator prompt + V110 spec §1.3 reframe）**：`λ_alpha / λ_sharpe / λ_max_dd / λ_hit_rate / λ_capacity_used`，per-strategy × per-symbol 校準。
- **算法選擇（per H-2）**：
  - GP kernel: **Matern 5/2** 推薦（vs RBF）— 適合 noisy financial reward surface
  - Acquisition function: **Expected Improvement (EI)** 推薦（vs UCB / PI）— exploration / exploitation 平衡
  - ξ 參數: `0.01`（EI exploitation-leaning baseline；high-noise regime 可調 0.1）
- **Iter budget 分階段（per H-2）**：Sprint 4-5 micro **10 iter** / Sprint 7+ Advisory **50 iter** / Y2 auto **100 iter**。
- **30% rollback 累積 cap（per H-2）**：weight 變更累積 **30d wall-clock** window 超過 30% 自動 rollback；防 over-fitting drift；rollback action 走 V110 audit (rollback_triggered=TRUE + rollback_reason TEXT)。
- **Convergence criterion**：連續 **5 iter** improvement < **5%** 停；或 budget exhausted；convergence_metric 寫 V110。
- **跨 module 整合（5 條 single-authority dedup contract per CR-7）**：
  - M6 ↔ **M1 LAL**：weight tuning auto-apply 走 LAL Tier 2 (Y2 enable)；> 30% delta 走 Tier 3 operator approve
  - M6 ↔ **M7 decay**：M6 ref M7 decay signal；M7 SUSPENDED → 該 strategy weight = 0
  - M6 ↔ **M9 A/B**：weight variant 走 M9 cluster 3 (risk profile)；per ADR-0037 fair execution clause
  - M6 ↔ **M11 replay**：M6 不消費 M11 divergence；M11 replay 走 M6 advisory weight (engine_mode='replay' 寫 V110)
  - M6 ↔ **M3 health**：HEALTH_DEGRADED → 凍結 M6 auto-propose
- **Walk-forward validation**：rolling 6 mo train + 1 mo test + 7d embargo + purge label horizon overlap；per-fold WLS sharpe + cross-fold std/mean ≤ 0.5；OOS PSR(0) > 0.95。
- **5-7 Acceptance criteria（§12）**：GP convergence test / 30% rollback cap empirical test / WFV OOS metric / cross-language reward 1e-4 fixture (per H-18) / M7 dedup contract test / leakage 6 維度 zero-violation / sample weight non-degenerate。
- **IMPL phasing**：Sprint 5 micro (Foundation) → Sprint 7 Advisory (Shadow→Canary) → Y2 auto-gate (Production)。
- **Open questions**：≥3 條留 Sprint 1A-γ/δ 補答。

---

## §1 Context — 為什麼需要 Bayesian Reward Weight Tuning

### 1.1 v5.7 baseline 痛點

v5.7 §7 Auto-Allocator reward function 採 manual-set 5 λ weight：
```
reward = λ_dd × DD_score + λ_tail × tail_score + λ_turnover × turnover_score
       + λ_slippage × slippage_score + λ_decay × decay_score
```
- **Manual weight 不自校準** — operator 拍 λ 值（如 λ_dd=2.0），無法隨 regime 演進
- **Regime shift 後 stale** — crypto 半年內 vol regime 切換頻繁；manual λ 在 trending → ranging 切換後失準
- **Multi-objective 衝突無解** — λ_dd 高 vs λ_alpha 高之間 tradeoff，operator 無客觀依據判斷

### 1.2 為什麼 Bayesian Optimization

Bayesian Optimization (BO) 在以下情境最優：
1. **Objective function evaluation expensive** — 每組 λ 必跑 last 6 mo simulation 算 sharpe，~10-30 min per evaluation
2. **No gradient information** — reward function 是經驗 simulation（無 analytical gradient）
3. **Noise tolerant** — sharpe estimate 含 sampling noise + regime noise；BO 透過 GP posterior 自然處理
4. **Black-box optimization** — λ → sharpe 關係非 convex，未知 functional form

BO 對 RANDOM / GRID search 的優勢：
- RANDOM: ~100-1000 iter 才接近 BO 10-50 iter 效率
- GRID: 5 λ × 10 grid = 100,000 evaluation 不可行
- BO: GP surrogate model 自動探索高 promise region

### 1.3 v5.8 §2 M6 source + PA H-2 mandate（重點）

| Source | Mandate |
|---|---|
| v5.8 §2 M6 line 234 | BO over `λ_dd, λ_tail, λ_turnover, λ_slippage, λ_decay`；objective = realized risk-adjusted return on last 6 mo |
| v5.8 §2 M6 line 236 | Constraints: weights within operator-set bounds (e.g., λ_dd ∈ [0.5, 5.0]) |
| v5.8 §2 M6 line 240-243 | Bounded autonomy: weight change > 30% 需 operator confirm；next-month sharpe < baseline → 自動 rollback |
| v5.8 §2 M6 line 246-248 | Sprint 1A schema + ADR / Sprint 7 Advisory / Y2 Auto ≤ 30% change enabled |
| PA H-2 (2026-05-21) | **algorithm spec**：GP kernel + acquisition function + iter budget + convergence + 30% rollback 累積 cap |
| MIT 5.21 audit Risk 2 | leakage 6 維度 + CV protocol skill 未引用 → 本 spec §10 補齊 |

### 1.4 與既有 module 關係（不取代）

| 既有 module | M6 與其關係 |
|---|---|
| v5.7 Auto-Allocator | **本 module 升級其 reward function 校準機制**；Allocator 本體不變，只改 reward weight 來源（manual → BO-tuned）|
| ADR-0021 Alpha Surface Bundle | **Alpha contribution 是 M6 λ_alpha 信號之一**；不取代 Alpha Surface 本體 |
| M1 LAL (本 spec §9) | **依賴**：weight tuning auto-apply 走 LAL Tier 機制 |
| M7 decay enforcement (本 spec §8) | **依賴**：M6 ref M7 decay signal；M7 SUSPENDED → weight=0 |
| M9 A/B testing (本 spec §7) | **協作**：weight variant 走 M9 cluster 3 (risk profile) |
| M11 replay (本 spec §7) | **協作**：M11 nightly replay 走 M6 advisory weight |
| M3 health (本 spec §7) | **依賴**：HEALTH_DEGRADED → 凍結 M6 |

---

## §2 5 λ 維度詳述

### 2.1 5 λ 命名 + 對齊

per operator prompt + V110 spec §1.3 reframe（operator prompt 為 SoT；v5.8 §2 M6 line 234 5 λ 為原始命名）：

| operator prompt 5 λ | V110 column 名 | v5.8 §2 M6 原始 5 λ map | 維度含義 | 預設 bound (per H-2) |
|---|---|---|---|---|
| λ_alpha | `lambda_alpha` | λ_slippage reframed | alpha contribution 正信號 weight | [0, 10] |
| λ_sharpe | `lambda_sharpe` | λ_decay reframed | risk-adjusted return weight | [0, 10] |
| λ_max_dd | `lambda_max_dd` | λ_dd (直接 map) | max drawdown penalty | [0.5, 5.0] (v5.8 §2 line 236 example) |
| λ_hit_rate | `lambda_hit_rate` | λ_tail reframed | win-rate stability (反映 tail negative event 頻率) | [0, 10] |
| λ_capacity_used | `lambda_capacity_used` | λ_turnover + λ_slippage 合 | capacity utilization penalty (capacity 用量越高，turnover/slippage 越大) | [0, 10] |

**reframe rationale**：
- `λ_decay` (原 v5.8) 由 M7 single decay authority 處置（per CR-7 dedup contract）；M6 不再雙寫 decay weight，M6 ref M7 decay signal 作為 strategy SUSPENDED 判斷
- `λ_tail` reframe 為 `λ_hit_rate`：hit_rate 低 ↔ tail negative event 頻 ↔ 反映 fat tail risk
- `λ_turnover + λ_slippage` 合入 `λ_capacity_used`：兩者皆為 capacity 利用 cost；合併簡化 BO 空間
- `λ_slippage` 名稱 reframe 為 `λ_alpha`：alpha 正信號 weight（reward function 對 alpha 正向加權）

**caveat**：若 PM 仲裁切替 v5.8 §2 M6 原始 5 λ 命名，本 spec §2 column 名 + BO 空間定義須 patch。

### 2.2 Per-strategy × per-symbol 校準

5 λ tuple 是 **per-strategy × per-symbol** 級別：
- 5 strategy (grid_trading / ma_crossover / bb_breakout / bb_reversion / funding_arb) × 25 symbol = **125 個 weight set** (peak Sprint 7+)
- 每個 weight set 獨立 BO run
- weight_set_id (UUID) 在 V110 統一追蹤；同 set_id 跨 strategy/symbol 可重用（e.g. cluster 共享）

**選擇 per-symbol 理由**：
- grid_trading BTCUSDT vs ma_crossover ETHUSDT 的 reward surface 結構不同
- BTCUSDT vol regime ≠ altcoin vol regime；同策略不同 symbol 的 λ_max_dd 差異大
- 不 per-symbol → 平均化 weight 失準

**警示**：125 weight set × 50 iter Advisory × 12 month = 75,000 BO evaluation/yr；計算成本 + ML training queue 共用 cron window 是 IMPL 期工程 concern（§13.2 budget）。

### 2.3 Bounds + tighten 機制

| Bound 來源 | 範圍 | 修改授權 |
|---|---|---|
| V110 CHECK constraint | [0, 10]（5 λ schema-level hard cap）| 改 V110 spec 才能改（DDL gate）|
| risk_config TOML | per-λ operator-set tighter bound (e.g. λ_max_dd ∈ [0.5, 5.0])| operator manual edit risk_config TOML + restart |
| M1 LAL Tier 2 auto-tighten | bound shrink only（never widen）— per H-2 30% rollback cap 觸發 | LAL Tier 2 auto-approve（per §9）|
| operator emergency override | 任意 bound | operator manual + 24h log audit |

**設計理由**：3 層 bound（hard cap / operator-set / auto-tighten）對應 v5.7 baseline + v5.8 §2 M6 line 236 example + H-2 H-11 反向 attack mitigation。

---

## §3 GP Kernel 選擇

### 3.1 Matern 5/2 vs RBF 對比

| Aspect | Matern 5/2 | RBF (Squared Exponential) | 結論 |
|---|---|---|---|
| **Smoothness assumption** | 2 次可微分（適合 noisy / non-smooth） | 無限次可微分（過 smooth） | Matern 5/2 勝 — financial reward surface 含 regime noise，非過 smooth |
| **Hyperparameter set** | length scale (per-λ) + variance + noise | length scale + variance + noise | 相同 — 5 length scale (per λ) + 1 variance + 1 noise = 7 hyperparameter |
| **Tail behavior** | exponential decay（thick tail tolerant） | gaussian decay（thin tail，extreme deviation 處理弱） | Matern 5/2 勝 — crypto reward fat tail |
| **Convergence rate** | 略慢（function eval 多 ~10%） | 較快（smooth interpolation） | RBF 勝 small margin |
| **Numerical stability** | 較穩（thick tail kernel 不易 ill-condition）| RBF 容易 ill-condition (需 jitter epsilon ~1e-6) | Matern 5/2 勝 |
| **Crypto regime 適配** | OK（regime shift kernel posterior 自然調整）| 弱（過 smooth 假設掩蓋 regime change）| Matern 5/2 勝 |
| **Literature in finance BO** | Snoek (2012) 推薦 Matern 5/2 for noisy financial | RBF 多用於 hyperparameter tuning (low noise) | Matern 5/2 勝 |

**推薦**：**Matern 5/2**

**hyperparameter set**：
```
length_scale[5] = [1.0, 1.0, 1.0, 1.0, 1.0]  # per-λ length scale，BO 期 fit (e.g. via L-BFGS-B on marginal likelihood)
length_scale_bounds = [(0.01, 100.0)] × 5      # per-λ length scale optimization bound
variance = 1.0                                  # kernel variance (output scale)
noise = 0.1                                     # observation noise (Gaussian likelihood)
nu = 2.5                                        # Matern 5/2 fix
```

**caveat**：若 Y2 auto 100 iter 後 GP fit 顯示 noise > 0.5（reward surface 過 noisy 不可學），降級 → 純 random search baseline；GP fit log warning。

### 3.2 為何不選其他 kernel

| Kernel | 拒絕理由 |
|---|---|
| Linear | 假設線性關係；BO objective 為 sharpe 對 λ 線性假設不成立 |
| Polynomial | over-fitting 風險；non-stationary 反映弱 |
| Matern 3/2 | 0.5 次可微（過 rough）；對 reward 平滑性 underspecify |
| Matern 1/2 (Exponential) | 0 次可微；過度 rough，convergence 慢 |
| Spectral mixture | 過於 complex；6 strategy 樣本量不足 fit |

---

## §4 Acquisition Function 選擇

### 4.1 EI vs UCB vs PI 對比

| Aspect | Expected Improvement (EI) | Upper Confidence Bound (UCB) | Probability of Improvement (PI) | 結論 |
|---|---|---|---|---|
| **Exploration / Exploitation** | EI 自然平衡 (積分 over improvement distribution) | UCB κ 參數需手動 tune | PI 過度 exploitation (greedy) | EI 勝 |
| **Hyperparameter sensitivity** | EI ξ 參數低敏感 (default 0.01) | UCB κ 高敏感 (1.0-3.0 之間有差) | PI ξ 高敏感 | EI 勝 |
| **Theoretical guarantee** | Mockus (1978) 收斂保證 | Srinivas (2010) regret bound (但 κ schedule 複雜) | 無強 guarantee | EI 勝 |
| **Implementation complexity** | 解析解 (Φ + φ closed form) | 簡單 (μ + κ × σ) | 解析解 (Φ closed form) | 三者相當 |
| **Noisy reward 表現** | EI 在 noisy 下穩定 (積分平滑掉) | UCB noise 下 over-explore | PI noise 下 over-exploit | EI 勝 |
| **Multi-modal reward surface** | EI 能跳出 local optimum | UCB 易 stuck local optimum | PI 強烈 stuck | EI 勝 |
| **Crypto reward surface 適配** | 推薦 (noisy + multi-modal) | 不推薦 (κ 調 tune 工作量大) | 不推薦 (over-greedy) | EI 勝 |
| **Literature in finance BO** | Snoek (2012) / Frazier (2018) 推薦 EI | 部分用於 RL (Thompson) | 少用 | EI 勝 |

**推薦**：**Expected Improvement (EI)**

**ξ 參數選擇**：
```
ξ = 0.01    # default exploitation-leaning baseline (Sprint 5 micro / Sprint 7 Advisory)
ξ = 0.1     # high-noise regime (Y2 auto if reward surface noise estimate > 0.3)
```

**EI 公式**：
```
EI(λ) = E[max(f(λ) - f_best - ξ, 0)]
      = (μ(λ) - f_best - ξ) × Φ(z) + σ(λ) × φ(z)
where:
  z = (μ(λ) - f_best - ξ) / σ(λ)
  μ(λ), σ(λ) = GP posterior mean / std at λ
  f_best = best observed reward so far
  Φ, φ = standard normal CDF / PDF
```

### 4.2 為何不選其他 acquisition

| Acquisition | 拒絕理由 |
|---|---|
| Thompson Sampling (TS) | 適合多任務 RL；single objective BO 收斂慢 |
| Knowledge Gradient (KG) | 計算複雜（需 inner optimization）；implementation 成本高 |
| Entropy Search (ES) | 計算複雜（需 sampling）；implementation 成本高 |
| Random | baseline 對比用；不適合 production BO |

---

## §5 Iter Budget 分階段

### 5.1 三階段 budget（per H-2）

| Stage | iter_budget | 用途 | wall-clock 估算 |
|---|---|---|---|
| **Sprint 4-5 micro** | **10 iter** | proof-of-concept BO infra；5 strategy × 25 symbol = 125 weight set × 10 iter = 1,250 BO eval | ~6 hr/run (per eval ~3 min × 1250) |
| **Sprint 7+ Advisory** | **50 iter** | monthly Advisory opt；BO 收斂進入 productive range | ~30 hr/run (per eval ~3 min × 6250) |
| **Y2 auto** | **100 iter** | auto-tune ≤ 30% delta enabled；BO 充分收斂 | ~60 hr/run |

### 5.2 為何 10 / 50 / 100

| iter | 收斂預期 | 殘留 uncertainty |
|---|---|---|
| 10 | ~30-40% global optimum proximity (Snoek 2012) | high — proof-of-concept only |
| 50 | ~70-80% global optimum proximity | acceptable — Advisory operator review 補 final approve |
| 100 | ~85-95% global optimum proximity | low — Y2 auto safe enable (per LAL Tier 2) |

**rationale**：5 λ × continuous bound search space ~10^5 candidate；10 iter 探索 ~1%；50 iter 探索 ~5%；100 iter 探索 ~10%；後續邊際收益 → 不必擴 budget。

### 5.3 Budget 不超過硬限

- per-eval ~3 min (last 6 mo simulation on PG cached fixture)
- Y2 100 iter × 125 weight set = 12,500 eval/run × 3 min = 625 hr CPU
- 並行 8 core (per M11 IMPL spec §2.1 tokio pool) → 78 hr wall-clock
- monthly run window 30d → 78 / 720 = 11% 月度 CPU budget (OK)

**警示**：若 Sprint 8+ 擴 strategy 至 10+ 或 symbol 至 50+，BO budget 必重評；本 spec 5×25 baseline 為 v5.8 firm scope。

---

## §6 30% Rollback 累積 Cap (per H-2)

### 6.1 30% cap 定義

**window**：**30d wall-clock**（per H-2 mandate；非 trading day / 非 BO iter）

**ratio 計算**：
```
ratio(strategy_id, symbol, T) = 
    Σ |λ_t - λ_{t-1}| for t in [T-30d, T] 
    / 
    base_λ_30d_ago(strategy_id, symbol)
```
- 對每個 λ 維度算累積絕對變動 / 30d 前 baseline value
- 5 λ 取 max ratio（per-strategy × per-symbol）
- max ratio > **0.30** → 自動 rollback

**rollback action**：
1. 寫 V110 row：`rollback_triggered=TRUE` + `rollback_reason='accumulated_revert_cap_exceeded'`
2. 凍結該 (strategy, symbol) M6 auto-propose 14d (cooldown)
3. weight 回退至 30d 前 baseline
4. 通知 operator (Slack + Console)

### 6.2 為何 30d wall-clock + 30% threshold

| 選擇 | 理由 |
|---|---|
| **30d wall-clock** (非 trading day) | 一致與 v5.8 §2 M6 line 236「next-month sharpe」對齊（monthly cadence） |
| **30% threshold** | per v5.8 §2 M6 line 242「weight change > 30% requires operator confirm」一致；30% 累積 = 過度 drift signal |
| **max over 5 λ** (非 mean) | 任一 λ 維度過度 drift 即 reject；fail-conservative |
| **per-strategy × per-symbol** | 局部 drift 不應 trigger 全 portfolio rollback；isolation per weight_set |

### 6.3 與 v5.8 §2 M6 line 240-243「per-update 30% confirm」差異

| Mechanism | scope | trigger |
|---|---|---|
| **per-update 30% confirm** (v5.8 §2 M6 line 242) | single proposal delta > 30% from current | LAL Tier 3 operator approve（per §9）|
| **30d 累積 30% cap** (本 spec §6 / H-2) | 30d window 累積 |λ_t - λ_{t-1}| sum / baseline > 30% | auto rollback + 14d cooldown |

**兩機制 complementary**：per-update prevent 單筆過大 step；30d 累積 prevent 小步累積過度 drift。

### 6.4 H-11 反向 attack mitigation

per AMD-2026-05-21-01 H-11 反向 attack mitigation：
- attack: 攻擊者透過 50 個 1.5% 小步累積讓 weight 漂移 75%（單步 < 30% confirm 門檻，繞過 LAL Tier 3）
- mitigation: 30d 累積 cap 在第 20-30 步觸發 rollback（依 baseline magnitude）
- audit: 每 rollback 寫 V110 row + Slack alert + operator 必審

---

## §7 M6 ↔ M9 A/B + M11 Integration

### 7.1 M6 ↔ M9 A/B (per ADR-0037)

per ADR-0037 M9 A/B framework + fair execution clause + 4 variant cluster taxonomy：

**對接點**：M6 weight 提案視為 M9 cluster 3 (risk profile variant)

| M9 cluster | M6 weight 變動 fall into |
|---|---|
| cluster 1 (parameter sweep) | ❌ 不在 M6 scope（策略 hyperparam tuning，M9 直接管）|
| cluster 2 (sizing variant) | ❌ 不在 M6 scope（position sizing，Allocator 直接管）|
| **cluster 3 (risk profile)** | ✅ **M6 weight 提案** — weight 改變直接影響 risk profile |
| cluster 4 (trigger variant) | ❌ 不在 M6 scope（strategy logic 變動）|

**fair execution audit (per ADR-0037)**：
- control (current weight) vs treatment (M6 proposed weight) 隨機分配 trial_id
- 對 OpenClaw self-trade，Copy Trading follower 永遠 control (per ADR-0037 H-5)
- variant outcome 寫 V108 ab_tests (Sprint 1A-γ schema)；M6 ref V108 outcome 作為 weight 校準 ground truth

**caveat**：V108 是 Sprint 1A-γ placeholder；本 spec 假設 V108 column 含 (trial_id, control_outcome, treatment_outcome, variant_type='risk_profile')；若 V108 spec 後續 schema 不對齊，M6 IMPL 期需 patch。

### 7.2 M6 ↔ M11 (per ADR-0038)

per ADR-0038 M11 continuous counterfactual replay + V110 engine_mode='replay' enum:

**對接點**：M11 nightly replay 使用 M6 advisory weight（current production weight）跑 last 24h replay；replay outcome 寫 V107 divergence_log（**不**寫回 V110）

**M11 對 M6 影響**：
- M11 replay outcome 與 live outcome divergence > threshold → 觸發 M3 HEALTH_WARN
- M3 HEALTH_WARN → 凍結 M6 auto-propose (per §7.3)
- M11 不直接修改 weight；只觸發 alert chain

**M6 對 M11 影響**：
- M6 提案 weight → engine_mode='replay' 走 M11 nightly replay 評估
- replay outcome 確認 weight 不退化才走 LAL Tier 2 auto-approve

**dedup contract (per CR-7)**：M11 是 sensor (divergence detector + signal emitter)；M11 不寫 V110；M6 不消費 M11 divergence。

### 7.3 M6 ↔ M3 health

per CR-7 M3 single health authority + M11 spec §5:

**對接點**：M3 HEALTH_DEGRADED → 凍結 M6 auto-propose（per v5.8 §2 M3 line 140）

| M3 state | M6 行為 |
|---|---|
| HEALTHY | M6 normal operation |
| HEALTH_WARN | M6 propose 仍可 Advisory（operator 仍可 manual approve）|
| HEALTH_DEGRADED | **M6 auto-propose 凍結** (per H-2 implicit)；30d cooldown |
| HEALTH_CRITICAL | M6 凍結 + 觸發 5-gate kill |

---

## §8 M6 ↔ M7 Decay Integration (per CR-7)

### 8.1 CR-7 single decay authority

per CR-7 dedup contract：**M7 是 single decay authority**；M6 不雙寫 decay weight。

**對接點**：
1. M6 ref M7 decay_signals (V113 placeholder column)
2. 若 strategy 在 M7 state 為 `SUSPENDED` → 該 strategy 全 symbol weight = 0
3. 若 strategy 在 M7 state 為 `DECAY_DETECTED` → M6 不重新 propose；維持當前 weight
4. 若 strategy 在 M7 state 為 `STAGE_LIVE` → M6 正常 propose

### 8.2 V113 placeholder dependency

**M7 V113 schema** (Sprint 1A-β sibling placeholder)：
- 假設 V113 含 column `strategy_id, decay_state, decay_score, last_updated`
- M6 IMPL 期 read V113 latest row per strategy
- 若 V113 schema 變更（owner: QC + MIT）→ M6 IMPL patch

**caveat**：V113 是 Sprint 1A-β sibling placeholder（per V110 spec §7）；schema 細節由 V113 spec owner 拍板；本 spec 假設上述 4 column 存在。

### 8.3 reframe 5 λ 不含 λ_decay 的 rationale

v5.8 §2 M6 原始 5 λ 含 `λ_decay`，本 spec reframe 移除（per V110 spec §1.3 + operator prompt）：
- 5 λ 重 reframe = `λ_alpha / λ_sharpe / λ_max_dd / λ_hit_rate / λ_capacity_used`
- decay 由 M7 single authority 處置（per CR-7）
- 雙寫 decay 違反 dedup contract → 移除 λ_decay 為架構必要

---

## §9 M6 ↔ M1 LAL Integration (per ADR-0034 + M1 spec §11)

### 9.1 weight tuning 走 LAL Tier 2-3

per M1 LAL spec §3.1 LAL 0-4 5 級：

| LAL Tier | M6 weight 變動 |
|---|---|
| LAL 0 (per-fill autonomous) | ❌ 不適用 (weight 變動 ≠ per-fill) |
| LAL 1 (intra-strategy reparam) | ❌ 不適用 (weight 跨 strategy reward function 改 ≠ 單策略參數) |
| **LAL 2 (cross-strategy reweight)** | ✅ **M6 主對接** — weight 變動 ≤ 30% + 30d 累積 cap 通過 → Y2 auto-approve |
| **LAL 3 (new strategy promotion)** | ✅ **M6 per-update > 30% confirm** — single proposal delta > 30% → operator manual approve |
| LAL 4 (capital structure / venue change) | ❌ 不適用 |

### 9.2 LAL 2 6 hard gate 對 M6 適用

per M1 LAL spec §3.2 + ADR-0034 Decision 5：

| Gate | M6 適用 |
|---|---|
| ≥30 prior advisory approvals | M6 first auto LAL 2 之前 ≥ 30 次 Advisory operator manual approve |
| rolling 30d operator yes-rate > 80% | 30d 內 M6 Advisory proposal operator yes-rate ≥ 80% |
| no incident last 90d | M6 / M7 / M11 / M3 90d 內無 incident |
| risk envelope in Stage 4 historical | 該 (strategy, symbol) 在 Stage 4 stable 30d |
| Console toggle = ON | operator manual enable M6 LAL 2 auto-approve toggle |
| post-hoc transparency emit | weight 變動 audit 寫 V110 + Slack notify |

**全 6 gate 通過 → M6 weight Advisory 進 LAL 2 auto-approve；任一 fail → 退回 LAL 3 operator approve**。

### 9.3 24h undo scope (per ADR-0034)

per M1 LAL spec §6 + ADR-0034 Decision 5：
- 24h undo scope = **config + risk envelope only, NOT fills** (成交不可逆)
- M6 weight 變動 24h 內 operator 可 undo（rollback to previous weight）；下單 fill 不可逆
- undo trigger → 寫 V110 row `rollback_triggered=TRUE` + `rollback_reason='operator_manual_revert'`

---

## §10 Walk-Forward Validation

### 10.1 CV 設計 (per time-series-cv-protocol skill)

**方法**：**Walk-Forward Rolling**（crypto regime 切換快；anchored expanding 不適合）

**設計**：
| Parameter | 值 | 理由 |
|---|---|---|
| train_window | 6 mo (180d) | per v5.8 §2 M6 line 235「last 6 mo」 |
| test_window | 1 mo (30d) | 對齊 monthly Advisory cadence |
| embargo | 7d | 對齊 V094 walk-forward embargo precedent |
| purge | label horizon overlap | 防 label_end_ts ≥ test_start (per Lopez de Prado AFML Ch.7) |
| n_folds | 6 (rolling 6 月，每月 forward 一次) | balance bias / variance |
| stride | 30d (monthly) | 對齊 BO cadence |

### 10.2 Per-fold metrics

per skill walk-forward-validation-protocol §6.1:

| Metric | Threshold |
|---|---|
| WLS Sharpe (per-fold) | 統計 mean ± std；non-negative bias |
| Sortino | ≥ 0 (下行 vol 不算 alpha 風險) |
| Calmar | ≥ 0 |
| max drawdown | per-fold drawdown ≤ Stage 4 envelope max |
| hit_rate | per-fold ≥ 0.45 (avoid degenerate 0.0 / 1.0) |
| PSR(0) | ≥ 0.95 over all 6 folds (per skill §6.2) |
| DSR | per H-18 cross-language 1e-4 fixture |
| IS vs OOS gap | ≤ 30% (per skill §6.2 healthy range) |
| Cross-fold std/mean | ≤ 0.5 (per skill §6.3 stability) |

### 10.3 Purge + Embargo (per Lopez de Prado AFML Ch.7)

**Purge**：
```python
# train fold 中刪除 label window 與 test fold 重疊的 sample
test_start = T
purge_range = [T - H, T]   # H = label horizon (M6 monthly cadence H = 30d)
train_keep = train_set 中 label_end_ts < T - H 的 sample
```

**Embargo**：
```python
# test fold 結束後跳 7d 再開 train
test_end = T'
train_resume = T' + 7d
```

### 10.4 樣本量規劃 (per skill time-series-cv-protocol §3)

per skill §3 表 + 5 strategy × 25 symbol × 1m × 30d ≈ 180k fill/mo (Sprint 7+ estimated)：

| Sample | M6 BO 適用 |
|---|---|
| < 1,000 fill | BO 不足 — skip M6 propose (per H-2 implicit) |
| 1,000-10,000 fill | BO acceptable — Advisory only |
| > 10,000 fill | BO production-ready — Y2 auto eligible |

**警示**：Sprint 5 micro 階段 fill 可能不足 1,000；BO infra 跑但結果不 deploy（只測 pipeline）。

### 10.5 6 leakage 維度 zero-violation (per feature-engineering-protocol skill)

per skill feature-engineering-protocol §1-§6 + MIT 5.21 audit Risk 2 mandate：

| Leakage type | M6 風險 + mitigation |
|---|---|
| **Look-ahead** | reward computation 必用 `.shift(1)` 對 rolling sharpe / drawdown；rolling.max() 含 current bar 屬已知反模式 |
| **Target leakage** | label window (next 30d sharpe) 不重疊 feature window (last 6 mo λ values) |
| **Survivorship** | training filter 必含 delisted symbol (Bybit V/V- prefix)；不用 only current active |
| **Cross-section** | normalize / z-score 用 expanding window（非全期 mean/std）|
| **Time-zone** | 所有 ts 統一 UTC；funding settlement UTC 整點不跨 timezone |
| **Resample boundary** | 1m → 1mo resample 只用 closed bar (isClosed=true)；partial 月不 BO |

**6 維度 zero-violation check 寫 V094 healthcheck (Sprint 7+ IMPL gate)**。

---

## §11 Convergence Criterion

### 11.1 Stop criterion (per H-2)

BO loop 停 iterate 當以下任一條件達成：

1. **連續 5 iter improvement < 5%**：
   ```
   improvement(t) = (f_best(t) - f_best(t-1)) / |f_best(t-1)|
   if all(improvement(t-4..t) < 0.05):
       stop
   ```
2. **iter_budget exhausted**：iter_num >= iter_budget
3. **GP fit failure**：若 GP marginal likelihood 連續 3 iter 不增 → 降級 random search baseline
4. **Validation failure**：walk-forward OOS PSR(0) < 0.95 → 停 + 不 deploy weight

### 11.2 convergence_metric 寫 V110

V110 column `convergence_metric NUMERIC` 寫 best-so-far objective (GP posterior mean of WLS sharpe minus dd penalty) per iter：
- iter_num 0 = initial random sample (no improvement)
- iter_num k = best-so-far at iter k
- 同 weight_set_id 的 iter row 構成 convergence curve
- Console 可 plot convergence curve for transparency

### 11.3 為何 5 iter × 5% 

| 選擇 | 理由 |
|---|---|
| **5 iter** patience | 太短 (3 iter) noise 觸發 false stop；太長 (10 iter) wastes budget；5 iter for 10/50/100 budget 比例 50% / 10% / 5% balance |
| **5% improvement** | 對應 V110 spec §2.4「rollback_cap_ratio_threshold = 0.30」一致比例感（5% = 1/6 of 30%）；BO literature default ~1-10% |

---

## §12 Acceptance Criteria (DESIGN 級 7 條)

### AC-1 — GP convergence test

**目標**：BO loop 在 50 iter (Sprint 7+ Advisory) 內收斂

**測試**：
- 跑 5 strategy × 25 symbol 各 50 iter BO
- 95% (≥ 118/125 weight set) 滿足 convergence criterion (per §11)
- failure rate ≤ 5% (容許 outlier high-noise weight set)

**驗收**：QA cycle (Sprint 7+ IMPL gate)

### AC-2 — 30% rollback cap empirical test

**目標**：30d 累積 cap 在 attack 場景觸發 rollback

**測試**：
- mock 場景：注入 20 個 1.5% 連續 weight delta (累積 30%) 走 LAL Tier 2 auto-approve
- expected: 第 20 個 delta 後 30d window ratio = 30% → rollback_triggered=TRUE 寫 V110 + 14d cooldown
- 驗 V110 row 含 `rollback_reason='accumulated_revert_cap_exceeded'`

**驗收**：E4 regression + healthcheck (Sprint 1A-β V110 land 後 IMPL test)

### AC-3 — Walk-forward OOS metric

**目標**：BO-tuned weight 在 OOS 6-fold 顯著 alpha

**測試**：
- 跑 walk-forward 6 fold (per §10.1)
- per-fold WLS sharpe mean > 0 + std/mean ≤ 0.5
- PSR(0) ≥ 0.95 over all 6 folds (deflated for K=50 iter sweep per skill DSR §2.2)
- IS vs OOS gap ≤ 30%

**驗收**：QA cycle (Sprint 7+ Advisory promote gate)

### AC-4 — Cross-language reward 1e-4 fixture (per H-18)

**目標**：Rust BO server vs Python BO eval 結果 1e-4 容差一致

**測試**：
- 同 (5 λ, 6 mo data) 輸入 → Rust GP posterior mean + Python (e.g. scikit-optimize) GP posterior mean
- 差異 < 1e-4
- 同 EI computation 差異 < 1e-4

**驗收**：E4 cross-language fixture harness (per H-18 共用，與 M11 / M3 / M8 共享)

### AC-5 — M7 dedup contract test

**目標**：M6 不雙寫 decay weight；ref M7 decay signal SUSPENDED → weight=0

**測試**：
- mock M7 state SUSPENDED for strategy X
- 跑 M6 BO propose → expected weight=0 for X 全 symbol
- 驗 V110 row weight set 全 5 λ = 0 for SUSPENDED strategy
- 驗 V113 read 無雙寫 decay signal (single authority)

**驗收**：E4 regression + healthcheck

### AC-6 — Leakage 6 維度 zero-violation

**目標**：feature engineering 過 6 維度 leakage check

**測試**：
- 對 BO input feature (λ, rolling sharpe, rolling dd, hit_rate) 逐項跑 §10.5 6 維度 check
- 全 6 維度 zero violation
- `.shift(1)` compliance 100% for rolling stat
- IS vs OOS sharpe gap > 50% → AUTO FAIL (per skill §6.2)

**驗收**：MIT audit (Sprint 7+ pre-deploy gate)

### AC-7 — Sample weight non-degenerate

**目標**：BO 對 fill sample 加權不退化 (per V084 sample_weight 1/170 教訓)

**測試**：
- 算 BO 輸入 fill sample weight distribution (rejected_governance → 1/170, others → 1.0)
- 確認 effective sample size > 50% raw fill count (per Kish formula)
- 若 < 50% → warn + 不 deploy weight
- 對齊 V084 sample_weight 設計 (per Sprint N+0 MIT review)

**驗收**：MIT audit + E4 regression

---

## §13 IMPL Phase Split

### 13.1 Sprint 5 — Micro (Foundation → Skeleton)

**Scope**：
- BO infra IMPL（Rust GP + EI computation）
- V110 writer code spawn（Python BO eval pipeline）
- 跑 10 iter micro on 1 strategy × 5 symbol (proof-of-concept)
- 0 production weight deploy（純 IMPL test）

**Workload**：60-80 hr (per v5.8 §2 M6 line 247-248 Sprint 7 estimate but earlier prototype)

**Deliverable**：
- V110 row count > 0（pipeline live）
- convergence_metric 趨勢 plot
- Linux PG 實測 BO writer 不 panic
- MIT pipeline maturity Stage: **Skeleton** (writer spawn but shadow_enabled=false until Sprint 7)

### 13.2 Sprint 7 — Advisory (Shadow → Canary)

**Scope**：
- Full 125 weight set × 50 iter monthly BO
- operator manual approve weight (Advisory mode)
- M9 cluster 3 A/B test variant 開始（per §7.1）
- Console UI（plot convergence curve + weight delta + rollback audit）

**Workload**：60-80 hr (per v5.8 §2 M6 line 247)

**Deliverable**：
- 30+ prior advisory approval 累積（LAL 2 prerequisite）
- WFV OOS metric green (per AC-3)
- 6 維 leakage zero-violation (per AC-6)
- MIT pipeline maturity Stage: **Shadow → Canary**

### 13.3 Y2 — Auto-gate (Production)

**Scope**：
- LAL 2 auto-approve enable (per §9.2 6 hard gate)
- 100 iter auto BO
- 30d 累積 cap empirical attack test green (per AC-2)
- 30% per-update confirm 走 LAL 3 manual approve（per v5.8 §2 M6 line 242）

**Workload**：30-50 hr (per v5.8 §2 M6 line 248)

**Deliverable**：
- 30d 累積 cap rollback 工作 production verified
- LAL 2 6 hard gate compliance
- MIT pipeline maturity Stage: **Production**

### 13.4 Phase 整體 wall-clock

| Sprint | Stage | wall-clock |
|---|---|---|
| Sprint 1A-β | V110 schema + 本 spec land | 2 weeks |
| Sprint 5 | Micro (Skeleton) | 2 weeks |
| Sprint 7 | Advisory (Shadow → Canary) | 4 weeks |
| Sprint 10+ | Advisory mature + accumulate 30+ approval | 12 weeks |
| Y2 Q1-Q2 | Auto-gate (Production) | 8 weeks |

---

## §14 Cross-V### Dependency

per V110 spec §7 + MIT 5.21 cross-V### graph：

| V### | M6 ref | Relationship | Schema FK |
|---|---|---|---|
| **V110** (own) | reward_weight_history main table | **owned by M6** | (none — append-only audit) |
| **V113** (M7 decay) | decay_signals (Sprint 1A-β placeholder) | M6 ref M7 decay_state column (per §8.2) | **reference only — no FK** (per V110 spec §7 cross-V### dependency rule) |
| **V108** (M9 A/B) | ab_tests (Sprint 1A-γ placeholder) | M6 weight variant 走 M9 cluster 3 (per §7.1) | **reference only — no FK** |
| **V107** (M11 replay) | replay_divergence_log | M11 ref M6 weight 跑 replay；不寫 V110 (per §7.2) | (none — M11 is sensor only) |
| **V112** (M1 LAL) | decision_lease_lal_tiers | M6 weight tuning 走 LAL Tier 2-3 (per §9) | (none — LAL gate runtime read, not DB FK) |
| **V109** (M8 anomaly) | anomaly_events (Sprint 1A-γ) | indirectly via M3 health (per §7.3) | (none) |

**Sprint 1A-β dispatch ordering**：V110 可獨立 land；不阻擋其他 module。
**Sprint 1A-β → 1A-γ ordering**：V110 必先於 V108 land（V108 引用 M6 weight variant via M9 cluster 3）。

---

## §15 Open Questions（≥3 條）

### Q1 — 5 λ 命名最終仲裁 (PM)

**問題**：本 spec 採 operator prompt 5 λ (`λ_alpha / λ_sharpe / λ_max_dd / λ_hit_rate / λ_capacity_used`)；v5.8 §2 M6 line 234 原始 5 λ (`λ_dd / λ_tail / λ_turnover / λ_slippage / λ_decay`)。

**選項**：
- (a) 採 operator prompt（本 spec 預設）— pro: operator SoT；con: v5.8 §2 M6 原始 wording 失準
- (b) 採 v5.8 §2 M6 原始命名 — pro: v5.8 主文檔對齊；con: 與 operator prompt 衝突
- (c) hybrid — V110 column 名用 (a)，文檔註 v5.8 原始命名 reframe rationale

**owner**：PM 仲裁
**timeline**：Sprint 1A-β V110 sign-off 前 land

### Q2 — Sprint 5 micro fill 不足 1,000 怎處理 (MIT + QC)

**問題**：Sprint 5 micro 階段 fill 可能不足 1,000 (per skill time-series-cv-protocol §3 table)；BO infra IMPL 跑但結果不可信。

**選項**：
- (a) skip M6 Sprint 5 micro，直接 Sprint 7 Advisory 啟動
- (b) Sprint 5 跑 BO infra（純 pipeline 驗證），結果 0 deploy
- (c) Sprint 5 用 historical demo data 補（risk: regime 不對齊）

**owner**：MIT + QC 共審
**timeline**：Sprint 5 開工前 land

### Q3 — Y2 LAL 2 auto-enable 觸發時機 (M1 owner + operator)

**問題**：v5.8 §2 M6 line 248「Y2: Auto-weight update (≤ 30% change) enabled」未指定 Y2 何月觸發 + 6 hard gate 何時齊備。

**選項**：
- (a) Y2 Q1 unconditional enable
- (b) 等 6 hard gate 全 green ≥ 30 + 30d operator yes-rate > 80% + 90d incident-free
- (c) M1 owner（PA）+ operator 共拍

**owner**：M1 owner (PA) + operator
**timeline**：Y1 Q3 review LAL 2 readiness

### Q4 — convergence_metric 公式細節 (QC + MIT)

**問題**：本 spec §11.2 convergence_metric = "GP posterior mean of WLS sharpe minus dd penalty"；具體公式（dd penalty 係數 / WLS weight 規則）未指定。

**選項**：
- (a) WLS weight = inverse 5%-tail variance；dd penalty = max(0, max_dd - 0.05)^2
- (b) 純 sharpe（無 dd penalty）— BO objective 更簡
- (c) 多 objective Pareto front（複雜度高）

**owner**：QC + MIT
**timeline**：Sprint 5 IMPL 前 land

### Q5 — BO library 選擇 (E1 + MIT)

**問題**：Rust GP + EI 自實 vs 用既有 library (scikit-optimize / GPyOpt / Ax)。

**選項**：
- (a) Rust self-implement (per E2 cross-language byte-equal 利)
- (b) Python scikit-optimize bridge (快但 cross-language byte-equal 風險)
- (c) hybrid: Python BO 推理 + Rust producer (V110 寫入)

**owner**：E1 + MIT
**timeline**：Sprint 5 IMPL 前 land

---

## §16 Risk + Mitigation

### 16.1 Risk 1 — GP 過 noisy 不收斂

**風險**：crypto reward surface noise 過高 → GP fit 失敗 → BO 退化 random search

**Mitigation**：
- §11.1 stop criterion 3 (GP marginal likelihood 連續 3 iter 不增 → 降級 random)
- per (strategy, symbol) noise estimate > 0.5 → log warning + skip auto-deploy

### 16.2 Risk 2 — 30d 累積 cap false-positive

**風險**：合法 weight drift (regime shift) 被 30d 累積 cap 誤觸發 rollback

**Mitigation**：
- 14d cooldown 後 operator 可 manual override（per §9.3 LAL 24h undo + manual approve）
- M11 nightly replay 驗 weight drift 真實 alpha 來源（per §7.2）
- 30% threshold 是 max 5 λ；單一 λ drift 不 trigger（per §6.1）

### 16.3 Risk 3 — V110 row 量爆炸

**風險**：Y2 auto peak ~456k row/yr（per V110 spec §2.1.4）

**Mitigation**：
- V110 spec §2.5 確認 regular table 即足（hypertable overhead 不划算）
- Sprint 1B retention policy 9 mo（per V075 precedent）

### 16.4 Risk 4 — M7 SUSPENDED weight=0 切換不連續

**風險**：M7 SUSPENDED → M6 weight=0 切換瞬間倉位 dump → execution slippage

**Mitigation**：
- M7 SUSPENDED 不直接觸發 weight=0；先走 Allocator gradual reduce（per Allocator IMPL spec, Sprint 7+）
- M6 weight=0 只反映在「下一輪 Allocator monthly proposal」；不修當前 position

---

## §17 Acceptance Sign-off Gate

per CLAUDE.md §八 + Sprint 1A-β closure:

| Role | Sign-off 條件 | 工作量估算 |
|---|---|---|
| **MIT (own)** | 本 spec draft + V110 sibling spec align | 10-15 hr (本 spec 寫 + V110 cross-ref) |
| **QC** | walk-forward AC-3 + leakage AC-6 + DSR 驗 | 8-12 hr |
| **PA (M1 owner)** | LAL 2-3 integration §9 對齊 + M1 LAL spec §11 cross-ref | 4-6 hr |
| **PA (M11 owner)** | M11 replay engine_mode='replay' write V110 對齊 §7.2 | 4-6 hr |
| **CC** | ADR-0034 + ADR-0037 + ADR-0038 contract review | 4-6 hr |
| **FA** | risk envelope + bounds enforcement review | 4-6 hr |
| **E2** | BO algorithm IMPL review + Linux PG dry-run V110 § Linux gate | 8-12 hr (Sprint 5 IMPL 前) |
| **E4** | cross-language fixture AC-4 + regression test AC-5 | 12-18 hr (Sprint 7 IMPL 前) |
| **PM** | final spec land + 5 hard gate audit | 2-4 hr |

**total**：56-85 hr DESIGN sign-off ( pre-Sprint 5 IMPL )

---

## §18 References

- v5.8 §2 M6 — `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` line 219-251
- V110 schema spec — `srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md`
- PA dispatch consolidation H-2 — `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`
- M1 LAL spec — `srv/docs/execution_plan/2026-05-21--m1_lal_layered_approval_lease_design_spec.md`
- M11 replay spec — `srv/docs/execution_plan/2026-05-21--m11_continuous_counterfactual_replay_design_spec.md`
- ADR-0021 Alpha Surface Bundle — `srv/docs/adr/0021-alpha-source-architecture-upgrade.md`
- ADR-0034 Decision Lease LAL — `srv/docs/adr/0034-decision-lease-layered-approval-lal.md`
- ADR-0037 M9 A/B framework — `srv/docs/adr/0037-m9-ab-framework-and-statistical-methodology.md`
- ADR-0038 M11 replay — `srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`
- skill: quant-strategy-design — `srv/.claude/skills/quant-strategy-design/SKILL.md`
- skill: walk-forward-validation-protocol — `srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`
- skill: time-series-cv-protocol — `srv/.claude/skills/time-series-cv-protocol/SKILL.md`
- skill: feature-engineering-protocol — `srv/.claude/skills/feature-engineering-protocol/SKILL.md`
- Bayesian Optimization literature: Snoek et al. (2012), Frazier (2018), Lopez de Prado AFML Ch.7

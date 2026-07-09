# ADR 0043: M6 Bayesian Reward Weight Tuning — Portfolio Weight Authority + GP Matern 5/2 + EI Acquisition + 30d 30% Rollback Cap

Date: 2026-05-21
Status: **Accepted**（v5.8 §2 M6 module ADR 級落地；對應 PA dispatch H-2 GP kernel + acquisition function + iter budget + 30% rollback 累積 cap mandate）
Operator Sign-off: 2026-05-21（主會話 PM dispatch — v5.8 §2 M6 採 Bayesian Optimization 取代 v5.7 manual-set reward weight；H-2 mandate 為算法選擇邊界）
Related: v5.8 §2 M6 Bayesian Reward Weight (lines 219-251) / M6 design spec `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m6_bayesian_reward_weight_design_spec.md`（849 行；本 ADR 為其治理層 promotion）/ V110 schema spec `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--v110_m6_reward_weight_history_schema_spec.md` / ADR-0021 Alpha Source Architecture Upgrade / ADR-0034 LAL Tier 2-3 audit / ADR-0037 M9 cluster 3 risk profile / ADR-0036 model blacklist (M6 GP variance 估計適用)

## Context

### 起源

v5.7 §7 Auto-Allocator reward function 採 manual-set 5 λ weight：

```
reward = λ_dd × DD_score + λ_tail × tail_score + λ_turnover × turnover_score
       + λ_slippage × slippage_score + λ_decay × decay_score
```

三個結構性問題：

- **Manual weight 不自校準** — operator 拍 λ 值（如 λ_dd=2.0），無法隨 regime 演進
- **Regime shift 後 stale** — crypto 半年內 vol regime 切換頻繁；manual λ 在 trending → ranging 切換後失準
- **Multi-objective tradeoff 無客觀依據** — λ_dd 高 vs λ_alpha 高之間 operator 無評估基準

v5.8 §2 M6（lines 219-251）以 Bayesian Optimization 替代 manual tuning，從 last 6 mo realized outcome 反向校準 5 λ。本 ADR 為該設計的治理層 promotion。

### 為什麼 Bayesian Optimization（不是 GRID / RANDOM）

BO 在以下情境最優：

1. **Objective function evaluation expensive** — 每組 λ 必跑 last 6 mo simulation 算 sharpe，~10-30 min per evaluation
2. **No gradient information** — reward function 是經驗 simulation（無 analytical gradient）
3. **Noise tolerant** — sharpe estimate 含 sampling noise + regime noise；BO 透過 GP posterior 自然處理
4. **Black-box optimization** — λ → sharpe 關係非 convex，未知 functional form

對比：

| 算法 | iter budget 需求 |
|---|---|
| GRID | 5 λ × 10 grid = 100,000 evaluation（不可行）|
| RANDOM | ~100-1000 iter 才接近 BO 10-50 iter 效率 |
| **BO (GP + EI)** | 10-100 iter（per H-2 phasing）|

### 5 λ 維度 reframe（per operator prompt + V110 §1.3）

| λ | 含義 |
|---|---|
| `λ_alpha` | Alpha contribution weight（與 ADR-0021 Alpha Surface 對接）|
| `λ_sharpe` | Risk-adjusted return weight（per-strategy 30d / 90d 兩 window）|
| `λ_max_dd` | Drawdown penalty weight（與 §16 portfolio risk 對齊）|
| `λ_hit_rate` | Win-rate weight（per-strategy bias 校正信號）|
| `λ_capacity_used` | Capacity utilization weight（防 over-allocation 到 sparse-fill strategy）|

5 維 reframe vs v5.7 原 5 維（dd/tail/turnover/slippage/decay）：保留 dd + 引入 alpha / sharpe / hit_rate / capacity_used 取代 tail / turnover / slippage / decay — decay 信號改由 M7 single authority 提供（per CR-7），tail / turnover / slippage 降為 sub-metric 不直接進 reward weight。

### H-2 mandate

per PA H-2（2026-05-21）必須在 ADR 鎖入：GP kernel + acquisition function + iter budget + convergence criterion + 30% rollback 累積 cap，否則 Sprint 7+ Advisory dispatch 階段 sub-agent 容易拉默認 hyperparameter（如 RBF kernel / UCB / 不限 iter）。

## Decision

**Proposed**：以下 7 條核心決策鎖入 ADR 級。

### Decision 1 — M6 為 portfolio weight authority

| 元素 | 設計 |
|---|---|
| 規則 | 全 system reward weight 校準集中由 M6 module 主責；取代 v5.7 manual-set λ |
| 取代範圍 | Auto-Allocator reward function 5 λ 計算來源；**Allocator 本體不變**，只升級 λ 來源 manual → BO-tuned |
| 不取代範圍 | (a) 策略 alpha 評估（ADR-0021 Alpha Surface 主責）(b) Strategy decay signal（M7 single authority 主責）(c) Portfolio cluster diversification（M9 cluster 3 risk profile 主責）|
| 反模式 | (a) Per-strategy 自行 tune λ（違反 single weight authority）(b) Manual λ override 不留 audit（V110 schema 必含 `manual_override_event` log）(c) M6 reward output 繞 LAL gate 直接寫 live |
| 落地 | M6 design spec §1-3 + V110 schema `reward_weight_history` table |

### Decision 2 — GP Matern 5/2 + EI Acquisition（per H-2）

| 元素 | 設計 |
|---|---|
| GP Kernel | **Matern 5/2** 推薦（vs RBF）— Matern 5/2 對 noisy financial reward surface 平滑性假設較弱；RBF 假設無限可微在 crypto 強波動下 over-smooth |
| Acquisition Function | **Expected Improvement (EI)** 推薦（vs UCB / PI）— EI 在 exploration / exploitation 之間自動平衡；UCB 需手動調 β、PI 過度 exploitation |
| ξ 參數 | `ξ = 0.01`（EI exploitation-leaning baseline）；high-noise regime 可調 `ξ = 0.1`；hot-update via ArcSwap |
| GP variance 估計 | 不可採 HMM / GARCH（per ADR-0036 Decision 1 黑名單）；採 realized vol bootstrap |
| 反模式 | (a) 默認 RBF kernel（over-smooth）(b) UCB without β tuning（exploration 偏激）(c) GARCH-based GP noise model（違反 ADR-0036）|
| 落地 | M6 design spec §4 算法選擇 |

### Decision 3 — Iter budget 分階段（Sprint 4-5 / Sprint 7+ / Y2，per H-2）

| Phase | Iter budget | 用途 |
|---|---|---|
| **Sprint 4-5 micro** | 10 iter | Foundation 驗 GP convergence + 30% rollback cap mechanic；不上線 |
| **Sprint 7+ Advisory** | 50 iter | Shadow + Canary；reward weight propose 走 LAL Tier 2 advisory（不 auto-apply）|
| **Y2 auto-gate** | 100 iter | Production auto-gate；≤ 30% delta auto-apply via LAL Tier 2；> 30% delta 走 LAL Tier 3 operator approve |

**Convergence criterion**：連續 **5 iter** improvement < **5%** 停；或 budget exhausted；convergence_metric 寫 V110。

**Phase 升級條件**：每 phase 須 acceptance criteria（§Decision 6 + M6 design spec §12）全通過才升下一 phase；不可跨 phase 跳級。

### Decision 4 — 30d 30% Rollback Cap（per H-2 + H-11 amplification mitigation）

| 元素 | 設計 |
|---|---|
| Cap 規則 | weight 變更累積 **30d wall-clock window** 超過 **30%** 自動 rollback |
| Cap 度量 | per-λ 累積 |Δλ| / |baseline_λ| 在 30d window 內 |
| Rollback action | 回到 30d window 起點的 λ snapshot；emit `rollback_triggered=TRUE` + `rollback_reason TEXT` 寫 V110 audit |
| Cap 為何 30d / 30% | (a) 30d 對齊 V106 threshold re-estimate cadence + per-strategy Sharpe 30d window (b) 30% 是經驗 over-fitting 邊界（per M6 spec §5；> 30% 累積變更通常代表 regime model 漂移而非真實 weight 升級需求） |
| Cap 失效情境 | 30d 窗口後 reset；regime shift 確認後（per M10 Tier D 9 cell transition）可 amend cap |
| 反模式 | (a) 無 cap → over-fitting drift（典型 weight 月內變 50%+ → next-month sharpe 崩）(b) Cap 只看單次 delta 不看累積（多次小 delta 累積到 > 30% 也應 trigger）(c) Rollback 不留 audit（V110 schema 必含 rollback log）|
| 落地 | M6 design spec §5 rollback cap + V110 schema 對應 column |

### Decision 5 — M6 走 LAL Tier 1-2 audit（不繞 5-gate）

| Auto-apply 邊界 | LAL Tier 對應 |
|---|---|
| **Sprint 7+ Advisory（Shadow + Canary）** | 全走 **LAL Tier 2 Advisory** — propose 而非 auto-apply；operator 點擊 approve |
| **Y2+ Production ≤ 30% delta** | **LAL Tier 2 auto-eligible**（per ADR-0034 Decision 4 toggle eligibility）|
| **Y2+ Production > 30% delta** | **LAL Tier 3 operator approve**（永遠 manual）|
| Rollback action | **不需 LAL gate**（rollback 是 safety regression，不 emit new proposal）|

**M6 不繞 5-gate**：reward weight change 屬 strategy parameter mutation；任何 weight 變更觸發新 lease，必經 5-gate + Guardian 既有路徑。

### Decision 6 — M6 ↔ M9 cluster 3（risk profile variant）

| 元素 | 設計 |
|---|---|
| 規則 | Weight tuning 探索新 λ 組合 = 創造 risk profile variant；走 M9 cluster 3 variant promotion 路徑 |
| Cluster 3 定義 | per ADR-0037 M9 A/B framework — cluster 3 = risk profile variant（保守 / 平衡 / 激進三型）|
| Fair execution clause | per ADR-0037 Decision 4 — weight variant A/B 必經 fair execution audit；不可一邊 variant 拿到 better fill priority |
| Variant promotion 條件 | Cluster 3 winner 經 21d OOS evidence + WLS sharpe + cross-fold std/mean ≤ 0.5 + PSR(0) > 0.95 → promote to baseline |
| 反模式 | (a) M6 直接 promote 新 λ 為 baseline 不經 M9 A/B（無 evidence）(b) A/B 不對齊 fair execution（biased fill priority）(c) Cluster 3 winner 不經 LAL gate（無 governance）|
| 落地 | M6 design spec §7 cross-module integration + ADR-0037 對齊 |

### Decision 7 — Retirement criteria

| 觸發條件 | Action |
|---|---|
| BO 12 mo 累積 net effect 對 PnL improvement < +0.3%（per M6 design spec §13） | 開 ADR amendment 評估「降回 manual-tuned + audit」|
| GP kernel 在 crypto regime 下系統性失敗（per M11 replay divergence > 60d 持續 unfavorable） | Amend Decision 2；考慮 evolutionary algorithm 替代 |
| 5 λ 維度被證明不足（需 7-10 維） | Amend V110 schema + M6 spec §3；不退役 M6 |
| Y3+ AUM 過大導致 BO 評估成本 > collected alpha | 開新 ADR 評估 lightweight heuristic 替代 |

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **保留 v5.7 manual-set λ** | per §Context 三痛點；regime shift 後 stale + multi-objective tradeoff 無依據 |
| **RANDOM search 替代 BO** | iter budget 100-1000x 高；不適合 expensive evaluation |
| **GRID search 替代 BO** | 5 λ × 10 grid = 100k 評估不可行 |
| **GP RBF kernel**（vs Matern 5/2） | RBF over-smooth assumption 在 crypto 高波動 surface 下擬合偏差 |
| **UCB acquisition**（vs EI） | 需手動調 β；EI 自動平衡 |
| **PI acquisition**（vs EI） | 過度 exploitation；早期 local optimum 風險 |
| **No iter budget cap** | Convergence 不收斂可能無限 iter；cost 失控 |
| **No 30% rollback cap** | Over-fitting drift（典型月內變 50%+ → next-month sharpe 崩）|
| **Per-strategy 自行 tune λ** | 違反 single weight authority；cross-strategy reward function 不一致 |
| **M6 auto-apply 不經 LAL gate** | 違反 §四 hard boundary + ADR-0034；reward weight = strategy parameter mutation，必經 LAL audit |
| **Decay signal 也由 M6 主責**（不接 M7） | 違反 CR-7 single decay authority；M7 ↔ M6 dedup contract 破裂 |
| **GP variance 用 GARCH 估計** | 違反 ADR-0036 Decision 1 black-list；採 realized vol bootstrap |

## Consequences

### Positive

- **取代 v5.7 manual λ stale 問題** — BO 從 last 6 mo outcome 反向校準，regime 演進自動跟進
- **Multi-objective tradeoff 有客觀依據** — GP surrogate model + EI acquisition 給 5 λ 之間 trade-off 量化基礎
- **算法選擇邊界 ADR 級鎖定** — Matern 5/2 / EI / ξ=0.01 / convergence 5 iter 5% improvement / iter budget 三 phase — sub-agent dispatch 不會拉默認 hyperparameter
- **30d 30% rollback cap 救命** — Over-fitting drift 自動防禦；rollback action 完整 audit
- **LAL Tier 對應清晰** — Advisory Tier 2 → Y2 auto Tier 2 ≤ 30% / Tier 3 > 30% 三段；不繞 5-gate
- **與 M9 A/B + M7 decay + M11 replay 完整 dedup** — 5 條 cross-module contract（per M6 spec §8-9）避免 weight authority 衝突
- **Iter budget 分階段升級** — Sprint 4-5 micro → 7+ Advisory → Y2 auto，每階段 acceptance criteria gated；不跳級

### Negative / Risk

- **BO 評估成本** — 每組 λ 跑 6 mo simulation ~10-30 min；Sprint 7+ 50 iter = 8-25 hr/cycle；mitigation = 走 nightly cron + M11 replay surface 共用基礎設施
- **GP kernel 選擇對 sample size 敏感** — Sprint 4-5 micro 10 iter 可能無法區分 Matern 5/2 vs RBF 是否真的較佳；mitigation = §Decision 7 retirement criteria 允許 amend
- **30% cap 在 regime shift 真實需要時可能誤觸發** — Crypto regime 切換時 λ 真的需要大幅調整；mitigation = M10 Tier D 9 cell transition 確認後可 amend cap；regime-aware exception 預留 ADR-debt
- **5 λ 維度可能不足** — capacity_used / hit_rate 是 v5.8 新引入，真實效用 Y2 才能 evidence；mitigation = Decision 7 允許擴維 amend
- **M6 ↔ M7 ↔ M9 ↔ M11 ↔ M3 五條 cross-module contract 增加 integration complexity** — 任一 contract 漂移會造成 weight authority race；mitigation = M6 spec §7-9 acceptance criteria 包含 5 條 contract test
- **Y2 auto-apply ≤ 30% delta 對 operator 「忘了開」場景 OK** — Per ADR-0034 Decision 4 default OFF 對齊；mitigation = degradation safe fallback 到 v5.7 manual

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| v5.7 Auto-Allocator | **本 ADR 升級其 reward weight 校準機制**；Allocator 本體不變 |
| ADR-0021 Alpha Source Architecture | **Alpha contribution 是 M6 λ_alpha 信號之一**；不取代 Alpha Surface 本體 |
| ADR-0034 M1 LAL | **Decision 5 對接**；Advisory Tier 2 + Y2 auto ≤ 30% Tier 2 / > 30% Tier 3 |
| ADR-0036 M8 anomaly black-list | **Decision 2 對齊**；GP variance 不可用 GARCH，採 realized vol bootstrap |
| ADR-0037 M9 A/B framework | **Decision 6 對接**；weight variant → cluster 3 risk profile + fair execution clause |
| M7 single decay authority | **Decision 1 對接**；decay signal 來源切換到 M7（不在 M6 本責）；M7 SUSPENDED → weight=0 |
| M11 continuous counterfactual replay | **M6 不消費 M11 divergence**；M11 replay 走 M6 advisory weight（`engine_mode='replay'` 寫 V110）|
| M3 Health | **HEALTH_DEGRADED → 凍結 M6 auto-propose**（per ADR-0042 Decision 2 cascade）|
| V110 schema spec | 本 ADR 為 V110 設計邊界；V110 spec cite ADR-0043 Decision 2/3/4 |
| ADR-0009 ArcSwap | ξ 參數 / iter budget / convergence threshold hot-update |
| walk-forward-validation-protocol skill | M6 spec §10 對齊；purge + embargo + DSR + PSR |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | weight 變更走 lease + Allocator 既有寫入口；不創旁路 |
| 2 | 讀寫分離 | ✅ | M6 是 evaluation + propose 層；不直接寫 live state |
| 3 | AI 輸出 ≠ 命令 | ✅ | BO propose 必走 LAL gate 才成 lease |
| 4 | 策略不繞風控 | ✅ | weight 變更觸發新 lease → Guardian + 5-gate 既有路徑 |
| 5 | 生存 > 利潤 | ✅ | 30% rollback cap + Advisory 兩段 phase + LAL gate 多層保守 |
| 6 | 失敗默認收縮 | ✅ | Convergence 失敗 → fallback baseline；rollback 自動 |
| 7 | 學習 ≠ live | ✅ | BO 是學習；evidence 累積走 LAL gate 才成 live weight |
| 8 | 交易可解釋 | ✅ | V110 reward_weight_history 完整 audit；每 iter + rollback 留 log |
| 9 | 雙重防線 | ✅ | LAL + Guardian + 30% rollback cap + Convergence stop 多層 |
| 10 | 分離事實 / 推論 / 假設 | ✅ | Realized sharpe = 事實；GP posterior = 推論；新 λ 預測 = 假設 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | Y2 auto ≤ 30% delta 是 evidence-gated 自主 |
| 12 | Evidence-based evolution | ✅ | BO from last 6 mo outcome；walk-forward + PSR + DSR 紀律 |
| 13 | cost 感知 | ✅ | Iter budget 三 phase 分階段；不無限 iter |
| 14 | 零外部成本 | ✅ | BO 全 Local Python；不依賴付費 BO service |
| 15 | Multi-agent formal | ✅ | M6 ↔ M7 ↔ M9 ↔ M11 ↔ M3 五條 contract 明文化 |
| 16 | Portfolio > 孤立 trade | ✅ | reward weight 校準是 portfolio-level；M6 ↔ M9 cluster 3 對齊 |

## Cross-References

- **M6 design spec**：`docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m6_bayesian_reward_weight_design_spec.md`（849 行）
- **V110 schema spec**：`docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--v110_m6_reward_weight_history_schema_spec.md`
- **v5.8 §2 M6**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:219-251`
- **ADR-0021**：`docs/adr/0021-alpha-source-architecture-upgrade.md`（Alpha Surface 與 λ_alpha 對接）
- **ADR-0034**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（LAL Tier 2-3 對接）
- **ADR-0037**：`docs/adr/0037-m9-ab-framework-and-statistical-methodology.md`（cluster 3 risk profile + fair execution clause）
- **ADR-0036**：`docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`（GP variance 不可用 GARCH）
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §H-2
- **walk-forward-validation-protocol skill**：`srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`
- **time-series-cv-protocol skill**：`srv/.claude/skills/time-series-cv-protocol/SKILL.md`
- **feature-engineering-protocol skill**：`srv/.claude/skills/feature-engineering-protocol/SKILL.md`
- **ADR-0009**：`docs/adr/0009-arcswap-config-hot-reload.md`（hyperparameter hot-update）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via v5.8 §2 M6 BO 路徑 + H-2 mandate | 2026-05-21 | ✅ PROPOSED-pending-commit |
| TW | 本 ADR 起草（M6 design spec 治理層 promotion） | 2026-05-21 | ✅ Drafted |
| MIT | V110 schema + GP convergence + cross-language reward 1e-4 fixture 對齊 | TBD（Sprint 1A-β） | 🟡 PENDING |
| QC | Walk-forward + PSR + DSR + leakage 6 維度 zero-violation 驗 | TBD（Sprint 5-7） | 🟡 PENDING |
| E1 | M6 Foundation IMPL（Sprint 4-5 micro） | TBD（Sprint 4） | 🟡 PENDING |
| E2 | M6 ↔ LAL gate 對接 review + 30% rollback cap 對抗驗 | TBD（Sprint 7） | 🟡 PENDING |
| FA | M6 ↔ 5-gate Guardian fail-closed + portfolio risk 對齊 | TBD（Sprint 7） | 🟡 PENDING |
| QA | M6 ↔ M7 ↔ M9 ↔ M11 ↔ M3 五條 contract 字面對齊驗 | TBD（Sprint 1A-β） | 🟡 PENDING |
| PM | Y2 auto-gate enable 仲裁（Y2 Q1） | TBD（Y2 Q1） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0043 — M6 Bayesian Reward Weight Tuning — Portfolio Weight Authority + GP Matern 5/2 + EI Acquisition (ξ=0.01) + Iter Budget 10/50/100 三 Phase + Convergence 5 iter 5% improvement + 30d 30% Rollback Cap (per H-11) + LAL Tier 2-3 Audit (不繞 5-gate) + Cluster 3 Risk Profile Variant (per ADR-0037 fair execution) (Proposed-pending-commit per 2026-05-21 v5.8 §2 M6 + H-2 mandate)*

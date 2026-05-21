---
spec: M4 Minimum Bar + Leakage Protocol — v5.8 Self-Supervised Hypothesis Discovery
date: 2026-05-21
author: MIT + PA consultant draft for PA Sprint 1A-γ dispatch
phase: v5.8 Sprint 1A-γ M4 schema prerequisite
status: SPEC-DRAFT-V0
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M4
  - srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v58_executability_audit.md M4 Risk
  - srv/docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-21--v58_executability_audit.md M4 FDR
related skills:
  - srv/.claude/skills/feature-engineering-protocol/SKILL.md
  - srv/.claude/skills/walk-forward-validation-protocol/SKILL.md
  - srv/.claude/skills/time-series-cv-protocol/SKILL.md
related memory:
  - memory/feedback_indicator_lookahead_bias.md (2026-04-24 P1-11 sweep audit 教訓)
scope: spec only — 不寫 IMPL，不改 V103 SQL；V103 EXTEND ALTER 為 CR-1 v5.7 follow-up 主會話收口
---

# M4 Minimum Bar + Leakage Protocol — v5.8 Self-Supervised Hypothesis Discovery

## §0 TL;DR

每個 hypothesis DRAFT 寫入 V103 EXTEND 之前必符合 **6 attribute minimum bar**：

1. **N ≥ 30** events / observations
2. **Bonferroni-corrected p-value < 0.05 / K**（K = total parallel hypotheses 估計）
3. **Effect size (Cohen's d / Hedge's g) ≥ 0.2**（Cohen 1988 "small" 以上）
4. **6-month sub-period stability**（Mann-Whitney U two-sample test，兩 half-period 同方向 + |effect_diff| < 0.5σ）
5. **Harvey-Liu-Zhu (2016) graveyard flag check**（fuzzy-match `learning.hypothesis_graveyard` signature；命中 → `graveyard_flag=true`，不阻 DRAFT 但 operator review 警示）
6. **Cluster K silhouette ≥ 0.5（5-fold purged time-series CV）**（如 hypothesis 涉及 clustering / regime separation；不涉及 → 此條 skip + `spec_no_clustering=true`）

額外硬規則：所有 rolling stat 計算必 `shift(1)` **leak-free**（current bar excluded）；SQL / pandas / Rust 三套範例完整附 anti-mock leakage scan，PA dispatch 前 sub-agent 自動 grep 驗證。

DRAFT 6 attribute 全填且通過 → `status='preregistered'` 候選；任何一條未通過 → `status='exploratory'` 不可 promote。

---

## §1 Background

### 1.1 v5.8 M4 原樣設計面

v5.8 主檔 §2 M4 line 153-186 列「Self-Supervised Hypothesis Discovery」三個 stage：

```
Pattern miner:
  - Statistical: rolling cross-correlation between asset features and forward returns
  - Temporal: event-window analysis (unlock / FOMC / liquidation cascade / large funding flip)
  - Cross-sectional: residual-return clustering, volatility regime clustering
```

但 v5.8 主檔 **未規範**：

- (a) hypothesis DRAFT 寫入 V103 表前的 **統計門檻**（minimum sample / p-value correction / effect size）
- (b) rolling cross-correlation 的 **leak-free 計算規則**（current bar 是否含入）
- (c) **historical false-discovery graveyard** 對既有「失敗 anomaly」的 fuzzy match 警示
- (d) clustering / regime separation 的 **silhouette 門檻**（避免無意義 cluster K 過擬合）

### 1.2 audit 共識

2026-05-21 三 agent 並行 audit 結論：

| Agent | 報告 | M4 風險摘要 |
|---|---|---|
| **MIT** | `MIT/workspace/reports/2026-05-21--v58_executability_audit.md` | M4 Risk：Sprint 2-3 Pattern miner 60-90 hr 無 minimum bar → 12 month 內 DRAFT 池 80% 為 noise + 30 mock false promotion 風險 |
| **QC** | `QC/workspace/reports/2026-05-21--v58_executability_audit.md` | **FDR 未控制**：500 hypothesis × α=0.05 → 25 false positives expected；Bonferroni correction 必需；若採 FDR (Benjamini-Hochberg) hypothesis level 可接受、sub-test level 不可接受 |
| **E4** | `E4/workspace/reports/2026-05-21--v58_executability_audit.md` | rolling cross-correlation 預設語意（pandas `.rolling(N).corr()`）含 current bar — 與 2026-04-24 P1-11 F3 RETRACT 同 anti-pattern；leak-free shift(1) 強制 |

operator 採 PA 仲裁建議：**M4 必附 6 attribute minimum bar**；本 spec land 規範。

### 1.3 為什麼 minimum bar 是 hypothesis discovery 的必要設計（不是可選約束）

- **多重檢驗膨脹**（multiple comparison inflation）：每個 hypothesis 內部 N 個 sub-test × 同 batch 並行 M hypothesis = N × M 次假設檢驗。在 α=0.05 下，K=2,500 次 → E[false positive] = 125（不 correction）vs 0.05 × 2,500 / 2,500 = 0.05（Bonferroni correction）。差距 2,500x。
- **效應量門檻**（effect size threshold）：p-value 只說「有效應」，effect size 才說「效應多大」。N=10,000 大樣本下 Cohen's d=0.05 也能 p<0.001，但 d=0.05 在實務中是 noise level。
- **時間穩定性**（sub-period stability）：訓練期內顯著但在更早 / 更晚 window 不顯著 = data snooping 過擬合。Mann-Whitney U 兩 half-period 同向 + |Δeffect| < 0.5σ 是 minimal robustness。
- **歷史 graveyard**（Harvey-Liu-Zhu 2016）：Harvey, Liu, Zhu (2016) "...and the Cross-Section of Expected Returns" 列 296 個歷史 anomaly，後續 replication 大量失敗。新 DRAFT 若 signature 命中 graveyard，operator review 必意識到 historical baseline weak（不阻 discovery，但需更強 evidence）。
- **clustering silhouette**：clustering / regime separation 用 silhouette 量化 cluster quality。silhouette < 0.5 = cluster boundary 模糊；K 隨機選就達不到 0.5。避免 cluster 過擬合的最低門檻。

### 1.4 與 2026-04-24 P1-11 F3 RETRACT 教訓的關聯

memory `feedback_indicator_lookahead_bias.md`（2026-04-24）記錄：

> Donchian breach 用 `rolling(N).max()` 含 current bar → breach=「current 是 N-bar max」必然 mean-revert artifact；原 F3 結論 fwd30 -3.20 顯著（>99%）撤回，leak-free `.shift(1)` 重算後 breach_diff_tstat = -0.45（接近 0，無效應）。**信號 100% 是 measurement artifact**。

M4 Pattern miner 的 statistical stage `rolling cross-correlation between asset features and forward returns` 是**完全同類 anti-pattern**：若 `feature_t` 計算用 `rolling(N).mean()` 含 current bar，與 `forward_return_t+1` 計算 correlation → cross-correlation 系數會被 measurement bias 系統性偏移。本 spec §3 強制所有 rolling stat 必 `shift(1)`。

---

## §2 6 Attribute Spec

### §2.1 N ≥ 30 minimum sample

#### §2.1.1 規則

- 每個 hypothesis 的 event / observation 樣本數 N **必 ≥ 30**。
- 若 hypothesis 是 event-based（如 FOMC announcement / token unlock / liquidation cascade）且 N < 30 → DRAFT 必 `status='exploratory'`，**不允許 promote 到 `preregistered` 直到 N ≥ 30**。

#### §2.1.2 為什麼 30

- **Normal approximation valid**：Central Limit Theorem 在 N ≥ 30 對大多數 distribution（含 heavy-tail）的 sample mean 已近似 normal，t-statistic / Wilson CI 等推論方法 valid。
- **Mann-Whitney U power**：在 effect size d=0.5（medium）下，N=30 vs N=30 兩組對比 Mann-Whitney U power > 0.5（足以偵測中度效應）。
- **bootstrap CI 穩定**：N < 30 時 bootstrap percentile CI 不穩；N ≥ 30 時 BCa interval 收斂良好。

#### §2.1.3 Edge case：event-based hypothesis N 可能小

- FOMC 每年 8 次 → 4 年才 32 次；2 年 N=16 不到 30。
- 規則：若 hypothesis 性質為 event-based AND N < 30 → 強制 `status='exploratory'` + DRAFT 寫入但 operator review **必標記「event-rate constrained, accumulate more events to promote」**。
- 不允許用 sub-sample（如 K-line 5min bar 跨 event window 切碎）膨脹 N → 違反 IID 假設。

#### §2.1.4 SQL check（事前 gate）

```sql
-- 每個 hypothesis DRAFT 寫入前 PA dispatch 強制跑：
-- N 計數對應的 event window table（hypothesis-specific）
SELECT
    hypothesis_id,
    COUNT(*) AS n_observations,
    COUNT(*) >= 30 AS passes_n_minimum
FROM learning.hypothesis_event_window
WHERE hypothesis_id = $1
GROUP BY hypothesis_id;

-- 若 passes_n_minimum=false：
--   - hypothesis 性質 event-based → status='exploratory'
--   - 其他類型 → 拒絕 DRAFT 寫入（reject by minimum bar）
```

---

### §2.2 Bonferroni-corrected p < 0.05 / K

#### §2.2.1 規則

- 每個 hypothesis 報告的 statistical significance **必使用 Bonferroni-corrected α**：
  - α_corrected = 0.05 / K
  - K = total parallel hypotheses estimate
- 寫入 `m4_attribute_p_bonferroni` 欄位的是**已 correction 的 p-value 對應的 α_corrected 比較結果**（或直接寫 raw p 然後 schema 端 derived column 算 corrected）。

#### §2.2.2 K 估計

K = (per-hypothesis sub-test 數) × (同 batch 並行 hypothesis 數)。

**範例**：M4 Pattern miner 一次 batch 跑 500 hypothesis × per-hypothesis 5 sub-test（5 個 forward window：1m / 5m / 15m / 1h / 4h forward return）= K = 2,500。

→ α_corrected = 0.05 / 2,500 = **2e-5**。

→ DRAFT 要 promote 到 `preregistered`，p-value 必 < 2e-5（極嚴）。

#### §2.2.3 Bonferroni vs FDR (Benjamini-Hochberg) 仲裁

| 方法 | 控制目標 | 嚴格度 | 本 spec 採用 |
|---|---|---|---|
| **Bonferroni** | Family-Wise Error Rate (FWER) | 最嚴（K 越大越嚴）| **本 spec 預設** |
| **Benjamini-Hochberg (FDR)** | False Discovery Rate (FDR) | 較鬆（控制比例不是絕對數）| **允許在 hypothesis-level 不在 sub-test level** |

**理由（採 Bonferroni 為預設）**：
- M4 Pattern miner 是 exploratory discovery，操作風險 = 把 false-positive hypothesis 放入 Stage 1+ promotion pipeline 浪費 capital。FWER 控制比 FDR 控制更安全（避免任何一個 false positive，不是控制比例）。
- Bonferroni 計算簡單透明，operator review 可獨立驗算。
- FDR (Benjamini-Hochberg) **僅允許在 hypothesis-level**（500 hypothesis 之間調 q-value）；**不允許在 sub-test level**（一個 hypothesis 內 5 個 forward window 之間調 q-value），否則 sub-test level FDR 變相放鬆 family-wise control。

#### §2.2.4 SQL anti-pattern

```sql
-- ❌ ANTI-PATTERN（無 K correction）：
SELECT hypothesis_id, p_value
FROM learning.hypothesis_statistical_result
WHERE p_value < 0.05;
-- → 500 個 hypothesis 跑出 ~25 個 false positive 被誤判 significant

-- ✅ CORRECT（Bonferroni）：
SELECT
    hypothesis_id,
    p_value,
    p_value < (0.05 / 2500) AS passes_bonferroni
FROM learning.hypothesis_statistical_result
WHERE p_value < (0.05 / 2500);
-- → 經過 K=2500 correction，false positive rate 控制 < 5%
```

**spec 必 alert**：M4 Pattern miner code 在 PA / E1 IMPL 階段 grep `WHERE p_value < 0.05`，若無 Bonferroni / FDR 邊界註解 → **拒絕 sign-off**。

---

### §2.3 Effect size (Cohen's d) ≥ 0.2

#### §2.3.1 規則

- Cohen's d **必 ≥ 0.2**（Cohen 1988 "small effect" threshold）。
- 計算公式：
  ```
  Cohen's d = (mean_treated - mean_control) / pooled_std
  pooled_std = sqrt(((n1-1)*s1^2 + (n2-1)*s2^2) / (n1+n2-2))
  ```
- Range check：|d| < 3.0；若 |d| > 3.0 → 標記 `effect_size_outlier=true`（極可能是計算錯 / data leak / outlier 主導），DRAFT review 必查 RCA。

#### §2.3.2 為什麼 0.2

- **Cohen 1988 conventions**：
  - d = 0.2 → "small effect"（學術心理學門檻）
  - d = 0.5 → "medium effect"
  - d = 0.8 → "large effect"
- **金融場景對應**：在 noise-dominated daily/hourly return 環境，d ≥ 0.2 表 signal 強度大於 1/5 of pooled volatility，足以在 1-3 month 累積樣本驗證；d < 0.2 在實務中 fading 風險高。

#### §2.3.3 Edge case：highly correlated features

若 hypothesis 涉及兩個高度相關 feature（如 BB upper band breach vs Donchian upper breach，corr > 0.7），使用 **partial correlation effect size**：

```
partial_d = d_full / sqrt(1 - r_xy^2)
```

其中 `r_xy` 是兩 feature 的相關係數。partial 效應量校正 collinearity 影響，避免雙計 effect。

#### §2.3.4 計算範例

```python
import numpy as np

def cohens_d(treated: np.ndarray, control: np.ndarray) -> float:
    """
    計算 Cohen's d effect size。

    為什麼：p-value 只說「有效應」，effect size 才說「效應多大」。
    不變量：n1, n2 ≥ 2；若 pooled_std = 0 回傳 0.0（無變異 = 無 effect）。
    """
    n1, n2 = len(treated), len(control)
    if n1 < 2 or n2 < 2:
        return float("nan")
    s1, s2 = treated.std(ddof=1), control.std(ddof=1)
    pooled_std = np.sqrt(((n1 - 1) * s1 ** 2 + (n2 - 1) * s2 ** 2) / (n1 + n2 - 2))
    if pooled_std == 0:
        return 0.0
    d = (treated.mean() - control.mean()) / pooled_std
    # Range check：|d| > 3.0 → outlier flag（呼叫端處理）
    return d
```

---

### §2.4 6-month sub-period stability

#### §2.4.1 規則

- Split N observations 為前後 50/50 兩 sub-period（time-ordered，不 random shuffle）。
- 對 sub_period_1 / sub_period_2 各算一次 effect size + p-value + means。
- **Pass criterion（兩條件皆需 true）**：
  - (a) **同方向**：sign(effect_period1) == sign(effect_period2)
  - (b) **量級接近**：|effect_period1 - effect_period2| < 0.5 * pooled_std
- Mann-Whitney U two-sample test 對 two-period means 不顯著差異（p > 0.10）→ 強化 pass。

#### §2.4.2 為什麼這樣設計

- **time-ordered split（不 random）**：金融時序有 regime shift（如 2026 Q1 bull vs 2026 Q4 bear），random shuffle 破壞時序資訊；前後 50/50 split 才能驗證「effect 跨時間穩定」。
- **同方向 + 量級接近兩條件**：
  - 同方向 only 不夠（effect_1 = 0.01 / effect_2 = 1.0 雖同方向但量級差 100x，明顯不 stable）。
  - 量級接近 only 不夠（effect_1 = +0.5 / effect_2 = -0.5 量級接近但反向，是 fade-out / regime flip 信號）。
  - 兩條件皆需 → 排除上述兩種 unstable 情境。
- **0.5σ 閾值**：對應 medium effect size 半值，學術 stability test 慣用。

#### §2.4.3 SQL skeleton

```sql
-- 6-month sub-period stability check
WITH ranked AS (
    SELECT
        observation_id,
        effect_value,
        observed_at,
        NTILE(2) OVER (PARTITION BY hypothesis_id ORDER BY observed_at) AS period_bucket
    FROM learning.hypothesis_observation
    WHERE hypothesis_id = $1
),
period_stats AS (
    SELECT
        period_bucket,
        AVG(effect_value) AS mean_effect,
        STDDEV(effect_value) AS std_effect,
        COUNT(*) AS n_obs
    FROM ranked
    GROUP BY period_bucket
),
pooled AS (
    SELECT
        SQRT(SUM(((n_obs - 1) * std_effect * std_effect)) / (SUM(n_obs) - 2)) AS pooled_std
    FROM period_stats
)
SELECT
    p1.mean_effect AS effect_1,
    p2.mean_effect AS effect_2,
    SIGN(p1.mean_effect) = SIGN(p2.mean_effect) AS same_direction,
    ABS(p1.mean_effect - p2.mean_effect) < 0.5 * pooled.pooled_std AS magnitude_close,
    SIGN(p1.mean_effect) = SIGN(p2.mean_effect)
        AND ABS(p1.mean_effect - p2.mean_effect) < 0.5 * pooled.pooled_std
        AS passes_subperiod_stability
FROM period_stats p1
CROSS JOIN period_stats p2
CROSS JOIN pooled
WHERE p1.period_bucket = 1 AND p2.period_bucket = 2;
```

---

### §2.5 Harvey-Liu-Zhu (2016) graveyard flag

#### §2.5.1 規則

- 維護 `learning.hypothesis_graveyard` ledger（V103 EXTEND 新增 table）。
- 每個 hypothesis DRAFT 寫入前**自動 fuzzy-match** signature 對 graveyard 全表。
- 命中 → 自動 `graveyard_flag=true`；**不阻 DRAFT 寫入**（discovery freedom）；但 operator review 階段必意識到 historical baseline weak（review form 必標 prompt）。

#### §2.5.2 為什麼不阻

- **Harvey-Liu-Zhu (2016) 296 anomalies** 中部分是時代差異（crypto market vs 1980s equity market），不 100% 適用 OpenClaw scope。
- 直接阻 → 可能誤殺 crypto-specific innovation。
- 標記不阻 → operator review 有 prior，調整 evidence requirement（如要求 effect size ≥ 0.3 不是 0.2）。

#### §2.5.3 `learning.hypothesis_graveyard` schema（V103 EXTEND）

```sql
CREATE TABLE IF NOT EXISTS learning.hypothesis_graveyard (
    graveyard_id            BIGSERIAL PRIMARY KEY,
    hypothesis_signature    TEXT NOT NULL,
    -- Signature 由 hypothesis name + feature set + forward return window 組成
    -- 如：'momentum_12m_minus_1m::equity::monthly_return'
    canonical_name          TEXT NOT NULL,
    -- 學術文獻命名，如 'Jegadeesh-Titman Momentum (1993)'
    source_paper            TEXT NOT NULL,
    -- 'Harvey, Liu, Zhu (2016) ...and the Cross-Section of Expected Returns'
    replication_failure_evidence TEXT,
    -- 後續 replication 失敗證據引用（如 'Hou-Xue-Zhang (2020) replication q-factor table'）
    crypto_applicability    TEXT
                            CHECK (crypto_applicability IN (
                                'likely_applicable',
                                'partially_applicable',
                                'likely_not_applicable',
                                'unknown'
                            )),
    notes                   TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fuzzy match index（用 trigram 或 GIN 全文 index）
CREATE INDEX IF NOT EXISTS idx_graveyard_signature_trgm
    ON learning.hypothesis_graveyard
    USING gin (hypothesis_signature gin_trgm_ops);
```

#### §2.5.4 Fuzzy match SQL（PA dispatch 強制）

```sql
-- DRAFT 寫入前自動跑：
SELECT
    g.graveyard_id,
    g.canonical_name,
    g.source_paper,
    similarity(g.hypothesis_signature, $draft_signature) AS sim_score
FROM learning.hypothesis_graveyard g
WHERE similarity(g.hypothesis_signature, $draft_signature) > 0.4
ORDER BY sim_score DESC
LIMIT 5;

-- 若任一 sim_score > 0.6 → graveyard_flag = true 寫入 m4_attribute_graveyard_flag 欄位
-- 若無命中 → graveyard_flag = false
```

#### §2.5.5 初始 graveyard 內容

Sprint 1A-γ 期間 PA 統一從 Harvey-Liu-Zhu (2016) Table 6 + Hou-Xue-Zhang (2020) replication failure list 載入 ~50 個高 confidence graveyard 條目（first wave）。後續 Sprint 8 mile stone 由 operator + Cowork 補充。

---

### §2.6 Cluster K silhouette ≥ 0.5 (5-fold purged time-series CV)

#### §2.6.1 適用條件

- **僅適用**於涉及 clustering / regime separation 的 hypothesis（如 v5.8 §2 M4 Cross-sectional residual-return clustering + volatility regime clustering）。
- **不適用** hypothesis：純 statistical correlation / event-window analysis → 寫入 `spec_no_clustering=true`，本條 skip。

#### §2.6.2 規則

- Cluster K 數量 hypothesis 自定（K=2/3/4/5...），但 silhouette 必算。
- 採 **5-fold purged time-series CV**（per `time-series-cv-protocol` skill）：
  - 5 個 time-ordered folds
  - 每 fold 用前 4 fold train clustering algorithm（K-means / HDBSCAN / GMM）
  - 在 leftout fold 計算 silhouette score
  - **purged + embargo**：fold 邊界 ±5% 樣本剔除，避免 information leakage
- **Average silhouette across 5 folds ≥ 0.5** → pass。
- 寫入 `m4_attribute_silhouette` 欄位（real，range [-1, 1]）。

#### §2.6.3 為什麼 0.5

- Silhouette score interpretation：
  - 0.71 - 1.00 → strong structure
  - 0.51 - 0.70 → reasonable structure
  - 0.26 - 0.50 → weak structure
  - < 0.26 → no substantial structure
- 0.5 = "reasonable structure" 最低門檻。< 0.5 等於 cluster boundary 模糊，K-選擇可能是隨機過擬合。

#### §2.6.4 5-fold purged time-series CV pseudo-code

```python
from sklearn.metrics import silhouette_score

def silhouette_purged_tscv(
    features: np.ndarray,
    n_clusters: int,
    n_splits: int = 5,
    embargo_pct: float = 0.05,
) -> float:
    """
    5-fold purged time-series CV silhouette。

    為什麼 purged + embargo：避免 fold 邊界 ±5% sample 跨 train/test leak；
    time-series 不可用 random KFold（破壞時序），必用 time-ordered split。
    """
    n = len(features)
    fold_size = n // n_splits
    embargo = int(n * embargo_pct)
    silhouettes = []
    for fold_idx in range(n_splits):
        test_start = fold_idx * fold_size
        test_end = test_start + fold_size
        # Purged + embargo：train 排除 test 區間 + 前後 embargo 邊界
        train_mask = np.ones(n, dtype=bool)
        train_mask[max(0, test_start - embargo):min(n, test_end + embargo)] = False
        # 訓練 clustering 算法（呼叫端傳入）
        cluster_model = fit_clustering(features[train_mask], k=n_clusters)
        labels_test = cluster_model.predict(features[test_start:test_end])
        if len(np.unique(labels_test)) < 2:
            continue  # 單一 cluster → silhouette 未定義，skip
        s = silhouette_score(features[test_start:test_end], labels_test)
        silhouettes.append(s)
    return float(np.mean(silhouettes)) if silhouettes else float("nan")
```

---

## §3 Rolling Stat shift(1) Leak-free Enforcement

### §3.1 規則

任何 rolling 計算（rolling mean / std / max / min / corr / regression）**必 `shift(1)`**：

- **語意**：rolling stat at time t 不可包含 bar t 本身的值。
- **why**：feature_t 用了 t 之後才能知道的資訊 = look-ahead bias = 經典 leakage（per memory `feedback_indicator_lookahead_bias.md`）。

### §3.2 SQL pattern（PG / TimescaleDB）

```sql
-- ✅ Leak-free rolling mean（exclude current row）：
SELECT
    ts,
    symbol,
    price,
    AVG(price) OVER (
        PARTITION BY symbol
        ORDER BY ts
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING  -- 重點：EXCLUDE current row
    ) AS rolling_mean_leak_free,
    STDDEV(price) OVER (
        PARTITION BY symbol
        ORDER BY ts
        ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
    ) AS rolling_std_leak_free
FROM market.kline
WHERE symbol = 'BTCUSDT'
ORDER BY ts;

-- ❌ ANTI-PATTERN（含 current bar，是 future leak）：
SELECT
    ts,
    AVG(price) OVER (
        PARTITION BY symbol
        ORDER BY ts
        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW  -- 重點：CURRENT ROW 是 leak
    ) AS rolling_mean_LEAK
FROM market.kline;
```

### §3.3 pandas pattern

```python
import pandas as pd

# ✅ Leak-free rolling mean：
df["rolling_mean_leak_free"] = (
    df["price"].rolling(window=20, min_periods=20).mean().shift(1)
)

df["rolling_std_leak_free"] = (
    df["price"].rolling(window=20, min_periods=20).std().shift(1)
)

df["rolling_corr_leak_free"] = (
    df["price"].rolling(window=20, min_periods=20).corr(df["fwd_return"]).shift(1)
)

# ❌ ANTI-PATTERN（含 current bar）：
df["rolling_mean_LEAK"] = df["price"].rolling(window=20).mean()
# pandas .rolling() 預設含 current row → 不 .shift(1) 就是 leak
```

### §3.4 Rust pattern（polars）

```rust
use polars::prelude::*;

// ✅ Leak-free rolling mean（polars LazyFrame）：
let df_leak_free = df
    .lazy()
    .with_column(
        col("price")
            .rolling_mean(RollingOptionsFixedWindow {
                window_size: 20,
                min_periods: 20,
                ..Default::default()
            })
            .shift(lit(1))
            .alias("rolling_mean_leak_free"),
    )
    .with_column(
        col("price")
            .rolling_std(RollingOptionsFixedWindow {
                window_size: 20,
                min_periods: 20,
                ..Default::default()
            })
            .shift(lit(1))
            .alias("rolling_std_leak_free"),
    )
    .collect()?;

// ❌ ANTI-PATTERN（含 current bar）：
let df_leak = df
    .lazy()
    .with_column(
        col("price")
            .rolling_mean(RollingOptionsFixedWindow {
                window_size: 20,
                min_periods: 20,
                ..Default::default()
            })
            // 缺少 .shift(lit(1)) → leak
            .alias("rolling_mean_LEAK"),
    )
    .collect()?;
```

### §3.5 Verification SQL（自動 leak 偵測）

```sql
-- 對所有 DRAFT 自動跑：比較 with-current-bar vs shift(1) 兩版 rolling stat
-- 若 effect size 顯著差異（|d_leak - d_shift1| > 0.1）→ leak suspected
WITH leak_version AS (
    SELECT
        hypothesis_id,
        AVG(effect_value_with_current_bar) AS mean_effect_leak
    FROM learning.hypothesis_observation_leak_audit
    WHERE hypothesis_id = $1
    GROUP BY hypothesis_id
),
shift1_version AS (
    SELECT
        hypothesis_id,
        AVG(effect_value_shift1) AS mean_effect_clean
    FROM learning.hypothesis_observation_leak_audit
    WHERE hypothesis_id = $1
    GROUP BY hypothesis_id
)
SELECT
    l.hypothesis_id,
    l.mean_effect_leak,
    s.mean_effect_clean,
    ABS(l.mean_effect_leak - s.mean_effect_clean) AS effect_diff,
    ABS(l.mean_effect_leak - s.mean_effect_clean) > 0.1 AS leak_suspected
FROM leak_version l
JOIN shift1_version s USING (hypothesis_id);

-- 若 leak_suspected=true → DRAFT 拒絕寫入 + RCA log
```

---

## §4 Anti-mock Leakage Scan

### §4.1 PA dispatch sub-agent 強制 grep

任何 M4 Pattern miner code path PR / IMPL DONE 前，PA 派 sub-agent 跑：

```bash
# 1) 找所有 rolling stat 計算（Python + Rust）
grep -rn 'rolling.*mean\(\)\|rolling.*std\(\)\|rolling.*corr\(\)\|rolling.*max\(\)\|rolling.*min\(\)' \
    --include='*.py' --include='*.rs' \
    srv/python/research srv/rust/openclaw_engine/src/strategies

# 2) 對每個 match 確認後接 .shift(1) 或等價語意（SQL ROWS BETWEEN N PRECEDING AND 1 PRECEDING）
# 3) 任何 rolling 沒 .shift(1) 且無 inline 反證註解（# leak-free: explicit shift below 等）→ FAIL
```

### §4.2 SQL pattern grep

```bash
# 找 SQL ROWS BETWEEN 用法
grep -rn 'ROWS BETWEEN' --include='*.sql' --include='*.py' \
    srv/sql srv/python

# 任何 ROWS BETWEEN ... AND CURRENT ROW → FAIL（含 current bar）
# 任何 ROWS BETWEEN ... AND 1 PRECEDING → PASS
```

### §4.3 Test pattern（test_m4_leakage_scan.py）

```python
# srv/tests/test_m4_leakage_scan.py
"""
MODULE_NOTE
模塊用途：M4 Pattern miner leakage scan 反規則測試 — 注入 leak 反測案例，驗 detector 抓得到。
主要類/函數：test_inject_leak_detected / test_shift1_passes / test_mock_must_reflect_real_behavior。
依賴：M4 leakage scan helper（grep + AST walker）。
硬邊界：unittest.mock.MagicMock 不可用於掩蓋 leak；mock 必 reflect 真實 shift(1) 行為。
"""

import pandas as pd
import pytest


def test_inject_leak_detected():
    """
    反測：注入含 current bar 的 rolling mean，驗 detector 抓得到 leak。

    為什麼這條 test 必要：detector 不是空跑 — 必須有反例證明它真能 catch leak。
    """
    df = pd.DataFrame({"price": range(100), "fwd_ret": range(100)})
    # 故意 inject leak（含 current bar）
    df["feature_LEAK"] = df["price"].rolling(20).mean()  # 缺 .shift(1)
    # detector 跑：
    leak_detected = run_m4_leakage_scan(df, feature_col="feature_LEAK", target_col="fwd_ret")
    assert leak_detected is True, "detector failed to catch obvious leak"


def test_shift1_passes():
    """
    正測：正確 .shift(1) 版本，detector 不應誤報。
    """
    df = pd.DataFrame({"price": range(100), "fwd_ret": range(100)})
    df["feature_clean"] = df["price"].rolling(20).mean().shift(1)
    leak_detected = run_m4_leakage_scan(df, feature_col="feature_clean", target_col="fwd_ret")
    assert leak_detected is False, "detector false-positive on clean shift(1) feature"


def test_mock_must_reflect_real_behavior():
    """
    反規則 test：unittest.mock.MagicMock 不可用於掩蓋 leak — mock 必 reflect 真實 shift(1) 行為。

    為什麼這條 test 必要：mock 是合法工具，但濫用 mock 掩蓋 leak 是反模式；
    test harness 必嚴格區分「mock 用於 isolation」vs「mock 用於 hide leak」。
    """
    from unittest.mock import MagicMock
    # 反例：mock 偽造 .shift(1) 但底層計算其實 leak
    mock_feature_generator = MagicMock()
    mock_feature_generator.compute.return_value = pd.Series(range(100))  # 沒實際 shift
    # 規則：呼叫端必驗 mock 回傳的 series **時序語意符合 shift(1)** 而不是只看 type
    # （這條規則 enforce 在 sub-agent code review checklist，本 test 是 reminder）
    pytest.skip("mock anti-pattern reminder; enforce in code review not unit test")
```

### §4.4 反規則：mock 不可掩蓋 leak

- `unittest.mock.MagicMock` 在 M4 Pattern miner test 中**僅用於 isolation**（mock 外部 API / DB / 第三方 lib）。
- **不可**用 mock 偽造 rolling stat 的回傳值（如 `mock_df.rolling.return_value.mean.return_value = ...`）讓 leak 通過 test。
- Code review checklist 必驗：每個 mock 回傳的 series **時序語意符合 shift(1)**，否則 sub-agent reject sign-off。

---

## §5 DRAFT writeback — V103 EXTEND 6 Attribute 字段

### §5.1 V103 EXTEND ALTER（CR-1 v5.7 follow-up）

**本 spec 不寫實 ALTER SQL**（per scope 鎖定 + CR-1 v5.7 follow-up 主會話收口）。V103 EXTEND 設計面如下，待主會話統一 land：

```sql
-- V103 EXTEND：為 learning.hypotheses 補 M4 6 attribute 欄位
ALTER TABLE learning.hypotheses
    ADD COLUMN IF NOT EXISTS m4_minimum_bar_jsonb       JSONB,
    -- 整 6 attribute 結果的結構化載體（raw value + pass/fail + computation metadata）
    ADD COLUMN IF NOT EXISTS m4_attribute_n             INTEGER,
    -- §2.1 N event count
    ADD COLUMN IF NOT EXISTS m4_attribute_p_bonferroni  REAL,
    -- §2.2 Bonferroni-corrected p-value（已 correction 的值）
    ADD COLUMN IF NOT EXISTS m4_attribute_effect_size   REAL,
    -- §2.3 Cohen's d
    ADD COLUMN IF NOT EXISTS m4_attribute_subperiod_pass BOOLEAN,
    -- §2.4 6-month sub-period stability pass/fail（兩條件 AND）
    ADD COLUMN IF NOT EXISTS m4_attribute_graveyard_flag BOOLEAN,
    -- §2.5 Harvey-Liu-Zhu graveyard fuzzy match flag
    ADD COLUMN IF NOT EXISTS m4_attribute_silhouette    REAL;
    -- §2.6 5-fold purged time-series CV avg silhouette（適用 clustering hypothesis；
    --       不適用時寫 NULL + 配 spec_no_clustering=true flag）
```

### §5.2 寫入規則

任何 DRAFT 沒 6 attribute 全填（且通過 minimum bar）→ `status='exploratory'`，**不可** promote 到 `preregistered`。

| 場景 | 寫入結果 |
|---|---|
| 6 attribute 全填且全 pass | `status='preregistered'` 候選（仍需 operator + Cowork review per ADR-0024-lite） |
| 6 attribute 全填但任一 fail | `status='exploratory'`，DRAFT 保留 + 標記 fail 原因 |
| event-based hypothesis N < 30 | `status='exploratory'`，標記「event-rate constrained」 |
| Non-clustering hypothesis | `m4_attribute_silhouette = NULL` + `spec_no_clustering=true`，§2.6 skip |
| Graveyard 命中 | `m4_attribute_graveyard_flag=true`，不阻 DRAFT 但 review 警示 |

### §5.3 derived view（提供 Cowork operator review）

```sql
-- 提供 operator + Cowork 統一 review surface
CREATE OR REPLACE VIEW learning.v_hypothesis_minimum_bar_summary AS
SELECT
    hypothesis_id,
    strategy_name,
    status,
    m4_attribute_n,
    m4_attribute_n >= 30 AS pass_n,
    m4_attribute_p_bonferroni,
    m4_attribute_p_bonferroni < (0.05 / 2500) AS pass_p_bonferroni,
    m4_attribute_effect_size,
    ABS(m4_attribute_effect_size) >= 0.2 AS pass_effect_size,
    m4_attribute_subperiod_pass,
    m4_attribute_graveyard_flag,
    NOT m4_attribute_graveyard_flag AS pass_no_graveyard,
    m4_attribute_silhouette,
    COALESCE(m4_attribute_silhouette >= 0.5, TRUE) AS pass_silhouette,
    -- 整體 minimum bar pass
    (m4_attribute_n >= 30
        AND m4_attribute_p_bonferroni < (0.05 / 2500)
        AND ABS(m4_attribute_effect_size) >= 0.2
        AND m4_attribute_subperiod_pass = TRUE
        AND COALESCE(m4_attribute_silhouette >= 0.5, TRUE)
    ) AS passes_all_minimum_bar
FROM learning.hypotheses
WHERE status IN ('draft', 'exploratory', 'preregistered');
```

---

## §6 Implementation Phasing

### §6.1 Sprint 階段對應

| Sprint | 內容 | 估時 | 對應 v5.8 §2 M4 line |
|---|---|---|---|
| **Sprint 1A-γ DESIGN（本 spec）** | M4 schema EXTEND V103 + ADR-0045（per R4 建議）+ 6 attribute spec land | 12-16 hr | line 177（hypothesis_drafts table extension）|
| **Sprint 2-3 Pattern miner stage 1** | Cross-correlation + event-window 純規則；每個 hypothesis 自動計算 6 attribute；不含 clustering | 60 hr | line 178（cross-correlation + event-window 80-120 hr）|
| **Sprint 8 Pattern miner stage 2** | Clustering + regime（含 §2.6 silhouette）；K-means / HDBSCAN / GMM 三選一 + 5-fold purged CV | 60-90 hr | line 179（clustering + regime 60-90 hr）|
| **Y2 active loop** | DRAFT → operator + Cowork review → preregister → Alpha Tournament | ongoing | line 181（Y2 Q2-Q3 full discovery loop active）|

### §6.2 ADR-0045 建議內容（per R4 上 spec 紀錄）

- **ADR title**：M4 Self-Supervised Hypothesis Discovery — Minimum Bar + Leakage Protocol
- **Decision**：採 6 attribute minimum bar（§2）+ rolling shift(1) leak-free 強制（§3）+ anti-mock leakage scan（§4）+ V103 EXTEND 6 字段（§5）
- **Context**：MIT + QC + E4 5.21 v5.8 audit 共識 M4 false discovery rate 未控制 + rolling cross-correlation look-ahead bias 風險
- **Consequences**：DRAFT pool 體積縮減 ~80%（false positive 過濾）；operator review 載量降低；Pattern miner IMPL 嚴格度上升
- **Alternatives considered**：(a) 採 FDR (Benjamini-Hochberg) 不 Bonferroni — 拒絕（family-wise control 必要）；(b) 不強制 graveyard 不 fuzzy match — 拒絕（296 Harvey anomaly 歷史教訓）；(c) 純規則 detector 不 anti-mock — 拒絕（mock 易掩蓋 leak）

### §6.3 與既有 Skill 的關係

- **`feature-engineering-protocol` SKILL**：本 spec §3 rolling shift(1) 強制是該 skill「6 大 leakage 類型」第 1 條 Look-ahead Bias 的具體落實到 M4 Pattern miner scope。本 spec 不取代 skill — skill 是通用 protocol，本 spec 是 M4-specific spec。
- **`walk-forward-validation-protocol` SKILL**：本 spec §2.4 sub-period stability + §2.6 5-fold purged time-series CV 對齊 skill walk-forward 設計哲學（不破壞時序、purged + embargo）。
- **`time-series-cv-protocol` SKILL**：本 spec §2.6 5-fold CV 直接引用 skill 中的 purged k-fold + embargo 範式。

---

## §7 Cross-References

### §7.1 spec 內部

- v5.8 主檔 §2 M4：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md` line 153-186
- V103 schema spec（earn / hypothesis registry）：`docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`（v5.7 SoT）
- Sprint 1A dispatch packet：`docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md`

### §7.2 PA dispatch / consolidation

- PA dispatch consolidation：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §1 CR-6
- PM final verdict：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`

### §7.3 audit reports

- MIT v5.8 audit：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v58_executability_audit.md` M4 Risk
- QC v5.8 audit：`docs/CCAgentWorkSpace/QC/workspace/reports/2026-05-21--v58_executability_audit.md` M4 FDR
- E4 v5.8 audit：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--v58_executability_audit.md` M4 rolling leak

### §7.4 skills + memory

- Feature engineering protocol skill：`srv/.claude/skills/feature-engineering-protocol/SKILL.md`
- Walk-forward validation protocol skill：`srv/.claude/skills/walk-forward-validation-protocol/SKILL.md`
- Time-series CV protocol skill：`srv/.claude/skills/time-series-cv-protocol/SKILL.md`
- Indicator look-ahead bias feedback：`memory/feedback_indicator_lookahead_bias.md` (2026-04-24 P1-11 F3 RETRACT 教訓)

### §7.5 學術參考

- **Harvey, Liu, Zhu (2016)** "...and the Cross-Section of Expected Returns" Review of Financial Studies — graveyard 主來源（296 anomaly + replication failure analysis）
- **Hou, Xue, Zhang (2020)** "Replicating Anomalies" Review of Financial Studies — Harvey-Liu-Zhu 後續 replication 失敗證據
- **Cohen (1988)** Statistical Power Analysis for the Behavioral Sciences (2nd ed.) — effect size convention（d=0.2 small / 0.5 medium / 0.8 large）
- **Benjamini, Hochberg (1995)** "Controlling the False Discovery Rate" JRSS-B — FDR baseline（本 spec 用 Bonferroni 不用 BH，但 §2.2.3 alt path）

### §7.6 governance

- ADR-0024-lite：Cowork operator-assistant scope（M4 DRAFT review 由 operator + Cowork 主導，bot 不 autonomous L2）
- ADR-0026 v3：Hypothesis preregistration（V101 spec § 3.3.2 + v5.7 PA brief 字段集合並，本 spec 不涉及 reconciliation 由 V103 spec 收口）
- ADR-0045（提議中）：本 spec 對應 governance authority；status SPEC-DRAFT-V0

---

## §8 Sign-off Status

| Agent | Status | 範圍 | Note |
|---|---|---|---|
| **MIT** | **Drafted** | Spec design（§2 + §3 + §4 + §6）| spec 統計設計面主撰；6 attribute 數學定義與 reasoning |
| **TW** | **Drafted** | Doc structure（§0 + §1 + §5 + §7 + §8）| frontmatter / §0 TL;DR / cross-reference / sign-off table / 整體文檔結構與中文化 |
| **PA** | **PENDING** | V103 EXTEND schema land + ADR-0045 起草 + Sprint 1A-γ dispatch | 待主會話 CR-1 v5.7 follow-up 收口；本 spec 為 PA 後續 IMPL 提供 design surface |
| **E4** | **PENDING** | Leakage scan test harness（§4.3 `test_m4_leakage_scan.py`）+ §3.5 verification SQL 整合 | E4 regression 階段補 |
| **QC** | **PENDING** | Bonferroni vs FDR 仲裁（§2.2.3）+ effect size 0.2 阈值校驗 + silhouette 0.5 校驗 | PA dispatch 前 QC 確認 |
| **AI-E** | **PENDING** | M4 Pattern miner IMPL stage 1 / stage 2 引用本 spec 6 attribute 計算 | Sprint 2-3 + Sprint 8 |

---

## §9 Out of Scope（本 spec 不寫）

- V103 EXTEND ALTER SQL 實檔（CR-1 v5.7 follow-up 主會話收口）
- v5.8 主檔修改（spec only / 主檔 land 由主會話統一）
- Rust / Python writer code（M4 Pattern miner IMPL 階段；本 spec 是 design）
- ADR-0045 實檔（PA Sprint 1A-γ dispatch 統一）
- Mac PG empirical dry-run（必 Linux PG，per CLAUDE.md §七 + V055 mandate）
- `learning.hypothesis_graveyard` 初始載入 50 條 Harvey-Liu-Zhu 資料（Sprint 1A-γ PA 統一 seed）
- M4 Pattern miner stage 1 / stage 2 演算法選型（Sprint 2-3 / Sprint 8 IMPL 階段）

---

**END OF SPEC**

# OpenClaw 數學實現方案彙編 / Math Implementation Notes

> **用途**：集中記錄所有需要數學推導的核心方案（bandit / 風控公式 / 統計檢定 / 校準 / shrinkage 等），含直覺解說、公式、實作映射、失敗邊界。
>
> **規則**：
> 1. 每篇都必須有「一句話直覺」段，給非數學背景的人看
> 2. 公式必須對得到代碼路徑（哪個函數 / 哪行 SQL 對應哪個量）
> 3. 失敗邊界明寫（什麼情況數學失效，必須回退或 reset）
> 4. 修改方案直接編輯本文件對應章節，不另起新文件
> 5. 狀態標籤：`pre-execution` (規劃中) / `in-progress` (開發中) / `live` (已部署) / `deprecated` (已替換)
>
> **最後更新**：2026-04-06

---

## 索引 / Index

| # | 標題 | 主題 | 應用模組 | 狀態 | 加入日期 |
|---|------|------|----------|------|----------|
| 01 | LinUCB Hierarchical Warm-Start | bandit / arm space migration | `linucb` (4-04~06) | **pre-execution** | 2026-04-06 |

---

# 01 — LinUCB Hierarchical Warm-Start
**狀態**：`pre-execution` · **應用**：Phase 4 LinUCB 子任務 4-04 / 4-06 / 4-15

## 1.1 一句話直覺

> **想像你在學「哪種釣魚方式最好用」。先學「哪種餌+哪種天氣」組合最好（15 種組合）。後來想擴展到「哪種餌+哪種天氣+哪個湖」（375 種組合）。**
>
> **笨方法：忘記之前學的所有東西，從零開始學 375 個組合 → 浪費 1-2 個月。**
>
> **聰明方法：把「這種餌+這種天氣的平均回報」當成「這種餌+這種天氣+任何湖」的初始猜測，然後讓每個湖的真實數據慢慢修正它。**
>
> 數學上有 **closed-form**（封閉形式解），不會引入估計誤差。+2 天工程成本，永久解決遷移問題。

## 1.2 為什麼需要這個

LinUCB 的核心是 **per-arm 線性迴歸**，每個 arm 維護兩個量 `(A, b)`，從歷史互動中累積學習。問題：

- **arm 數量改變時** (例如 15 → 25 → 375)，標準做法是「全部 reset 從頭學」
- Paper trading 累積樣本很慢（~1000 fills/週）
- 25 arms 需要 ~2500 樣本 ≈ 2.5 週才能初始收斂
- 375 arms 需要 ~37500 樣本 ≈ 6-9 個月（paper 跑量級下根本不可能）
- 每次 operator 想試新 arm space → 浪費數週甚至數月

**Operator 明確要求**：找辦法不 reset 也能擴展。

## 1.3 數學基礎

### 1.3.1 LinUCB 的 sufficient statistics

每個 arm `a` 在見過樣本 `{(x_1, r_1), (x_2, r_2), ..., (x_t, r_t)}` 後維護：

```
A_a = λI + Σ_t x_t · x_t^T          (d×d 矩陣，d = context 維度)
b_a = Σ_t r_t · x_t                  (d 維向量)
θ_a = A_a^{-1} · b_a                 (ridge regression 解，d 維)
```

UCB（選 arm 的置信上界）：
```
UCB_a(x) = θ_a^T · x + α · sqrt(x^T · A_a^{-1} · x)
                     ───────             ─────────────────────
                     期望回報             不確定性 (越多 pulls 越小)
```

α 是探索強度（通常 1.0），λ 是 ridge prior（通常 1.0）。

### 1.3.2 關鍵性質：可加性 (additivity)

`A` 和 `b` 是 **sufficient statistics** — 對「樣本順序」和「樣本切分」都是**線性可加**的：

```
若 樣本集合 S = S₁ ∪ S₂ (disjoint)
則 A(S) − λI = (A(S₁) − λI) + (A(S₂) − λI)
   b(S)       = b(S₁) + b(S₂)
```

證明：直接展開定義即可（求和的線性性）。

**這個性質是所有 warm-start 操作的根基。**

### 1.3.3 升維公式（V1 → V2，N1 < N2）

**場景**：V1 有 15 arms（strategy × regime），V2 有 375 arms（strategy × regime × symbol）。每個 V1 arm `p` 對應 `K=25` 個 V2 子 arm（同 strategy + 同 regime，跨 25 個 symbols）。

**直覺**：父 arm 的學習代表「該 strategy×regime 在所有 symbol 上的平均行為」。把它**等比例攤分**給每個子 arm 作為先驗。

**公式**：
```
對每個 V2 子 arm c（其父為 p）：

A_c_init = λI + (γ/K) · (A_p − λI)
b_c_init = (γ/K) · b_p
n_pulls_c = floor(γ · n_pulls_p / K)
cumulative_reward_c = γ · cumulative_reward_p / K

K = 子 arm 數量（例如 25 個 symbol）
γ = 信任折扣 ∈ [0.3, 1.0]，推薦 0.5
λ = ridge prior（通常 1.0）
```

**為什麼是除以 K（不是除以 K²）**：
我們把父的「樣本貢獻」攤分到 K 個子 arm 上。Sufficient statistics 對 disjoint 子集合可加，所以攤分後 K 個子 arm 的 sum 還原出父：
```
Σ_{c=1}^{K} (A_c − λI) = K · (γ/K) · (A_p − λI) = γ · (A_p − λI)
```
γ < 1 是「父子分布可能有偏差」的折扣，γ = 1 時 K 個子 arm 的 sum 完全等於父。

**為什麼 θ_c = θ_p 但 confidence interval 變寬**：

θ_c = A_c^{-1} · b_c
    = (λI + (γ/K)(A_p − λI))^{-1} · (γ/K) · b_p

當 γ = 1 且樣本量大（A_p ≫ λI）時：
    A_c ≈ (1/K) · A_p     →     A_c^{-1} ≈ K · A_p^{-1}
    b_c = (1/K) · b_p
    θ_c ≈ K · A_p^{-1} · (1/K) · b_p = A_p^{-1} · b_p = θ_p   ✓

但 confidence bound 變寬 K 倍：
    sqrt(x^T · A_c^{-1} · x) ≈ sqrt(K) · sqrt(x^T · A_p^{-1} · x)

**直覺**：「我猜這個值跟父一樣，但我承認對單一子 arm 的數據還很少，所以我會更積極探索。」這是 statistically correct 的行為 — confidence 應該反映 effective sample size，而不是 effective parameter sharing。

### 1.3.4 降維公式（V2 → V1，N2 > N1）— exact

```
A_p = λI + Σ_{c ∈ children(p)} (A_c − λI)
b_p = Σ_{c ∈ children(p)} b_c
n_pulls_p = Σ_c n_pulls_c
```

這是 **exact**（精確的，零資訊損失）。原因：sufficient statistics 對 disjoint 樣本集合的 union 本來就是 element-wise 可加的。

**唯一損失**：跨子 arm 的層級資訊（例如「BTCUSDT 的 ma_crossover 在 trending 中，跟 DOGE 的差異」這種對比資訊）會被 sum 掉。但這不是「丟失學習」，是「主動選擇不再區分」—— 這正是降維的意圖。

### 1.3.5 Context feature 維度變化（與 arm 數量正交）

**場景**：V1 用 d=8 個 features，V2 加入 news_severity 和 hours_since_news 變成 d=10。

**block-identity padding**：
```
A_v2 = ⎡ A_v1     0   ⎤
       ⎣  0    λ·I_2  ⎦       (右下 2×2 是新 feature 的 ridge prior)

b_v2 = [b_v1 ; 0 ; 0]          (新 feature 的累積 reward 從 0 開始)
```

新 feature 的 θ 分量會被 ridge 拉到 0 直到累積足夠樣本。對舊 feature 的學習完全保留。

**這跟 arm 數量變化是兩個獨立維度的問題**，可以同時發生（例如 v1_15+8d → v2_25+10d），按順序套用兩個變換即可（順序可交換）。

### 1.3.6 必須 reset 的硬邊界

| # | 場景 | 為什麼數學失效 | 偵測方式 |
|---|------|----------------|----------|
| **1** | Reward 定義改變 | b_vector 的量綱變了，舊累積失去意義 | 手動標記 + 拒絕無 marker 的遷移 |
| **2** | Feature 語義漂移（同名不同義） | A 和 b 的分量對應不同的真實量 | `feature_schema_hash` 強制比對 |
| **3** | 父 arm n_pulls < 30 | 繼承 = 繼承雜訊，子 arm 不如冷啟動 | 自動降級為純 ridge prior |
| **4** | 黑天鵝後市場結構斷裂 | 歷史學習相關性失效 | γ → 0.1 大幅折扣，或人工 reset |

## 1.4 SQL Schema 映射

V010 (在 4-15 子任務中執行) 對 `learning.linucb_state` 的修改：

```sql
ALTER TABLE learning.linucb_state
    ADD COLUMN arm_space_version  TEXT NOT NULL DEFAULT 'v1_15',
    ADD COLUMN parent_arm_id      TEXT DEFAULT NULL,
    ADD COLUMN inheritance_gamma  REAL DEFAULT NULL,
    ADD COLUMN feature_schema_hash TEXT NOT NULL DEFAULT '...';

-- PK 改為 (arm_id, arm_space_version) 支援多版本共存
ALTER TABLE learning.linucb_state DROP CONSTRAINT linucb_state_pkey;
ALTER TABLE learning.linucb_state
    ADD PRIMARY KEY (arm_id, arm_space_version);
```

| 數學量 | DB 欄位 | 備註 |
|--------|---------|------|
| `A` matrix | `linucb_state.a_matrix BYTEA` | numpy `tobytes()` 序列化，shape `(d, d)` |
| `b` vector | `linucb_state.b_vector BYTEA` | numpy `tobytes()` 序列化，shape `(d,)` |
| `n_pulls` | `linucb_state.n_pulls INT` | 累積互動次數 |
| `cumulative_reward` | `linucb_state.cumulative_reward REAL` | Σ r_t |
| `α` | `linucb_state.alpha REAL` | 探索強度 |
| `λ` | hardcoded `1.0` in code | ridge prior，不存 DB |
| `γ`（升維折扣）| `linucb_state.inheritance_gamma REAL` | 僅子 arm 有值，根 arm 為 NULL |
| 父子關係 | `linucb_state.parent_arm_id TEXT` | 自我引用，根 arm 為 NULL |
| 版本標籤 | `linucb_state.arm_space_version TEXT` | `v1_15` / `v2_25` / `v3_375` 等 |
| feature schema | `linucb_state.feature_schema_hash TEXT` | sha256 of (feature_name_list + dim) |

**新增表**：

```sql
-- 回滾用快照（archive 任何遷移前的舊版 state）
CREATE TABLE learning.linucb_state_archive (
    LIKE learning.linucb_state INCLUDING ALL,
    archived_ts    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    archive_reason TEXT
);

-- 遷移 audit log（誰在何時把哪個版本變成哪個版本）
CREATE TABLE learning.linucb_migrations (
    migration_id    SERIAL PRIMARY KEY,
    from_version    TEXT NOT NULL,
    to_version      TEXT NOT NULL,
    direction       TEXT NOT NULL CHECK (direction IN ('expand','collapse','feature_pad')),
    gamma           REAL,
    n_arms_before   INT,
    n_arms_after    INT,
    started_ts      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_ts     TIMESTAMPTZ,
    rollback_to     INT REFERENCES learning.linucb_migrations(migration_id),
    notes           TEXT
);
```

## 1.5 代碼路徑映射（4-06 子任務交付）

**檔案**：`program_code/ml_training/linucb_arm_migration.py`

```python
def migrate_expand_arm_space(
    from_version: str,                  # 'v1_15'
    to_version: str,                    # 'v2_25'
    parent_to_children: dict[str, list[str]],   # {'trending|ma_crossover': [25 個 symbol arm_id]}
    gamma: float = 0.5,
    min_parent_pulls: int = 30,
) -> MigrationReport:
    # Step 1: archive 當前 state 到 linucb_state_archive
    # Step 2: 對每個 parent arm:
    #   - 從 PG load (A_p, b_p, n_p, R_p)
    #   - 反序列化 numpy
    #   - 若 n_p < min_parent_pulls: 子 arm 用 cold start (λI, 0)
    #   - 否則: 套用 §1.3.3 公式生成 K 個子 arm
    # Step 3: UPSERT 到 linucb_state with arm_space_version=to_version
    # Step 4: 記錄到 linucb_migrations (audit log)
    # Step 5: 不刪舊版 state（保留供 shadow compare 對比 + rollback）
    pass

def migrate_collapse_arm_space(
    from_version: str,                  # 'v2_25'
    to_version: str,                    # 'v1_15'
    children_to_parent: dict[str, str],
) -> MigrationReport:
    # 套用 §1.3.4 sum-pooling 公式（exact）
    pass

def pad_feature_dim(
    arm_space_version: str,
    new_feature_count: int,
    new_feature_names: list[str],
) -> MigrationReport:
    # 套用 §1.3.5 block-identity padding
    # 同時更新 feature_schema_hash
    pass
```

## 1.6 安全網（部署策略）

### 1.6.1 Shadow Compare（強制 1-2 週）

切換 v1 → v2 後**不立即上線**，而是並行跑：

| | V1 (15 arms) | V2 (25 arms, warm-started) |
|---|---|---|
| 模式 | **冠軍**，繼續學 + 真實決策 | **挑戰者**，shadow log only |
| 寫真倉位 | ✅ | ❌ |
| 收 reward | ✅ | ✅（用同樣的 context 重放）|

### 1.6.2 自動回滾條件（任一觸發即回 V1）

| 指標 | 閾值 | 觸發行為 |
|------|------|----------|
| Cumulative regret Δ (V2 vs V1) | < -2σ | 自動切回 V1 + Telegram 告警 |
| Per-arm KL divergence (子 arm vs inheritance prior) | 75th percentile > 閾值 | 告警（可能 inheritance 偏離真相）|
| `feature_schema_hash` 失配 | any mismatch | **fail-closed** 立即停止寫入新 state |
| Per-arm pulls floor (前 14 天) | 任何子 arm < N | forced exploration 補足 |

### 1.6.3 監控指標寫入位置

- `learning.linucb_migrations.notes`：遷移前後 statistics 摘要
- `observability.model_performance`（V004 已建）：rolling Brier / regret per version
- Card UI（4-06 交付）：shadow compare 狀態條 + KL heatmap

## 1.7 失敗場景的處理流程

```
偵測到必須 reset 的場景:
  ├─ Case 1 (reward 重定義) → 人工確認 + 標記 marker → 走 reset 路徑
  ├─ Case 2 (feature 語義漂移) → feature_schema_hash 自動 fail-closed
  │                            → 拒絕寫入 → operator 收警報 → 人工介入
  ├─ Case 3 (n_pulls < 30) → migration 函數內自動降級該子 arm 為冷啟動
  │                        → 不影響其他子 arm 的 warm-start
  └─ Case 4 (黑天鵝) → 人工觸發 emergency_reset(gamma=0.1) 軟降級
                     → 或 hard reset 走 Case 1 流程
```

## 1.8 與其他模組的關係

| 模組 | 關係 |
|------|------|
| **Thompson Sampling NIG**（Phase 3b）| **不衝突也不重疊**。TS 是 stateless multi-arm（per-arm 後驗），LinUCB 是 contextual（用 features）。LinUCB 學「結構性問題」，TS 學「符號特異性」。LinUCB v1↔v2 切換時 TS posterior 不需動 |
| **Phase 5 James-Stein shrinkage** | 是 LinUCB warm-start 的「進階版」。JS 是 hierarchical prior（半人馬），warm-start 是 hard prior（固定攤分）。Phase 5 啟動後可考慮取代 §1.3.3 公式 |
| **Black Swan Detector**（Phase 3b）| 觸發 §1.6.4（Case 4）的決策邊界 |
| **decision_context_snapshots**（V003 已建）| 寫入 `linucb_arm_id` + `linucb_confidence_bound` 供 4-06 outcome attribution |

## 1.9 實作成本

| 方案 | 工時 | 代碼行數 |
|------|------|----------|
| Reset everything（基準）| 0.5d | 0 |
| **Hierarchical warm-start（推薦）** | **2-3d** | **~600 lines** |
| 完整 Hierarchical LinUCB (HLinUCB) 論文版 | 7-10d | ~2000 lines + Rust 推理層改 |

**淨成本**：+2 天一次性投入。**ROI**：第二次 arm space 變動就回本（每次省 1-2 週學習浪費）。

## 1.10 學術引用

- **Li et al. 2010** — *A Contextual-Bandit Approach to Personalized News Article Recommendation* — LinUCB 原論文，定義 sufficient statistics
- **T-LinUCB / Transferable Contextual Bandits with Prior Observations** (NSF preprint) — warm-start formulation 啟發來源
- **Top-k eXtreme Contextual Bandits with Arm Hierarchy** (Stanford XCB) — hierarchical arm space 處理框架
- **Cutting to the chase with warm-start contextual bandits** (Springer KAIS 2023) — γ 折扣的理論支持
- **Yahoo / Netflix 工業實踐** — 新內容上線時用 cluster 平均 warm start，本方案的工程性簡化版

## 1.11 開放問題（execute 時要回答）

1. `feature_schema_hash` 該包含哪些東西？單純 feature 名稱列表夠嗎？還是要 + dim + ordering + dtype？
2. KL divergence 監控的「閾值」具體該設多少？需要 paper 跑兩週看分布才能定
3. Shadow compare 多久判定「顯著」？2σ 是否需要 multiple-testing 校正（看了多少個指標）？
4. v3_375 的 K=25 攤分中，如果某個 (strategy, regime, symbol) 組合本來在歷史上完全沒出現過（例如 grid_trading × trending × DOGE 從未 trade 過），子 arm 還該繼承父嗎？
5. 是否要支援「跨 version chain」的回滾（v1→v2→v3，從 v3 直接回 v1）？

這些問題在 4-04~06 開工時跟 operator 一起解決。

---

*章節 01 終 · pre-execution 狀態 · 2026-04-06 · 待 4-04~06 開工時轉 in-progress*

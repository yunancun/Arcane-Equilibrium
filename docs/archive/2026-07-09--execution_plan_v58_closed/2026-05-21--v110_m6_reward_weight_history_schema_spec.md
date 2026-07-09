---
spec: V110 — M6 Reward Weight History + Bayesian Opt Runs Schema (FULL DDL)
date: 2026-05-21
author: MIT (Sprint 1A-β CRITICAL DESIGN; placeholder → full DDL upgrade)
phase: v5.8 Sprint 1A-β schema prerequisite
status: SPEC-DRAFT-V1（full DDL；待 PA C9 Linux PG dry-run + PM sign-off → SPEC-FINAL）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M6 Reward Weight (line 219-251)
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-β + §HIGH H-2 (GP kernel + acquisition + iter budget + 30% rollback cap)
  - srv/docs/execution_plan/2026-05-21--m6_bayesian_reward_weight_design_spec.md (sibling design spec)
  - srv/docs/adr/0021-alpha-source-architecture-upgrade.md (Alpha Surface Bundle reference)
  - srv/docs/adr/0043-m6-bayesian-reward-weight.md (V110 schema 對應治理 authority；ADR-0043 Decision 2/3/4 為 column 設計邊界；R4 NEW-H-2 reverse-ref patch 2026-05-21)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (Guard A/B/C + Linux PG dry-run protocol format)
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C 範式)
  - srv/sql/migrations/V083__fills_entry_context_id_close_check.sql (ALTER ADD COLUMN + NOT VALID CHECK 範式)
scope: schema DDL design only — 不寫 V110.sql 實檔，不在 Mac 跑 SQL，不改 Rust/Python writer，不執行 PG，不寫業務 code
---

# V110 M6 Reward Weight History + Bayesian Opt Runs Schema Migration Spec (FULL DDL)

## §0 TL;DR

- **V110 新增 2 個 regular table**：`learning.reward_weight_history`（per-strategy reward weight time-series ledger）+ `learning.bayesian_opt_runs`（Bayesian optimization run audit + 5-λ proposal ledger）。
- **核心 5 λ column（per H-2 + v5.8 §2 M6）**：
  - `lambda_alpha`（alpha penalty / reward signal weight）
  - `lambda_sharpe`（risk-adjusted return weight）
  - `lambda_max_dd`（max drawdown penalty weight）
  - `lambda_hit_rate`（win-rate stability weight）
  - `lambda_capacity_used`（capacity utilization penalty weight）
  - **5 column 設計 ≠ JSONB**（§9 詳論：query performance / index 友善 / CHECK constraint per-λ enforcement）
- **`bayesian_algorithm` ENUM 5 值**：`UCB / EI / PI / GP_Matern52 / GP_RBF`（acquisition + kernel 二分混合 enum；sibling DESIGN spec §3-§4 規範算法選擇）
- **30% rollback 累積 cap schema 反映（per H-2）**：`rollback_triggered BOOLEAN + rollback_reason TEXT` 兩 column；應用層 7d window 累積 reverted change ratio > 0.30 → 寫 row `rollback_triggered=TRUE + rollback_reason='accumulated_revert_cap_exceeded'`。
- **iter_num + iter_budget**：sibling DESIGN spec §5 規範 Sprint 4-5 micro 10 / Sprint 7+ Advisory 50 / Y2 auto 100。
- **convergence_metric NUMERIC**：每 iteration 的 best-so-far objective（GP posterior mean of WLS sharpe minus dd penalty）；連續 5 iter improvement < 5% → stop。
- **engine_mode CHECK 5 值齊全**：`paper / demo / live_demo / live / replay`（增 replay 為 M11 continuous replay 走 M6 advisory weight 用）。
- **weight_set_id UUID**：唯一識別一組 5-λ tuple；同 weight_set 跨 strategy / overlay 可重用。
- **Index：`(strategy_id, symbol, created_at DESC)` 主 hot-path / `(weight_set_id)` set-level drill-down / `(strategy_id, rollback_triggered) WHERE rollback_triggered=TRUE` H-2 audit partial index**。
- **Cross-V### dependency**：V110 (本表) / V113 (M7 decay ref；per CR-7 M7 single decay authority) / V108 (M9 A/B ref；Sprint 1A-γ；weight variant 走 M9 cluster 3 risk profile)。
- **Sprint 1A-β land schedule**：V106/V107/V110/V112/V113 5 個並行；V110 屬中位 priority（governance + Sprint 7+ Advisory IMPL）；不阻擋 critical path 但 M9 A/B Sprint 1A-γ 之前必 land。

---

## §1 Background + Scope

### 1.1 動機

v5.8 §2 M6 Reward Weight module 明示：
- Auto-Allocator 用 reward function 對 last 6 mo allocation outcome 反向校準 5 λ weight
- Monthly Bayesian optimization 提 candidate λ tuple
- candidate 必走 governance approval + 不超 bounds + per-update delta cap + 30% rollback 累積 cap

v5.8 §9 schema roster line 791「V110: reward_weight_history + bayesian_opt_runs」全 placeholder（per MIT 2026-05-21 v5.8 audit Risk 1，9 V### CRITICAL 級全空）。本 spec 對 placeholder doc（`2026-05-21--v110_m6_reward_weight_history_schema_spec.md` placeholder 版）升級為 full DDL，land Sprint 1A-β E1 IMPL 之前的 hard precondition。

### 1.2 v5.8 §2 M6 source + PA dispatch consolidation H-2 mandate

| Source | Mandate |
|---|---|
| v5.8 §2 M6 line 234 | Bayesian optimization over `λ_dd, λ_tail, λ_turnover, λ_slippage, λ_decay` |
| v5.8 §2 M6 line 240-243 | Bounded autonomy: weight change > 30% requires operator confirm; weight change rolled back if next-month Sharpe < baseline |
| v5.8 §2 M6 line 246-248 | Sprint 1A reward_weight_history table + ADR (40-60 hr) → Sprint 7 Advisory monthly opt → Y2 Auto ≤ 30% change enabled |
| PA dispatch H-2 (2026-05-21 PA report §HIGH) | M6 Bayesian opt 算法 spec（GP kernel + acquisition function + iter budget + convergence）+ 30% rollback 累積 cap |
| MIT 2026-05-21 v5.8 audit Risk 2 | M4/M6/M7/M8 ML 模組 leakage 6 維度 + M6 bayesian 算法 spec 全缺；feature-engineering-protocol + time-series-cv-protocol + data-drift-detection skill 未引用 |

### 1.3 與 v5.7 placeholder spec 的 5 λ 命名差異

| v5.7 placeholder spec §2.1.2 列出 5 λ | v5.8 §2 M6 line 234 5 λ | 本 spec full DDL 採用 |
|---|---|---|
| `λ_dd`（drawdown penalty）| `λ_dd`（drawdown penalty）| `lambda_max_dd` |
| `λ_tail`（tail risk penalty）| `λ_tail`（tail risk penalty）| `lambda_hit_rate`（reframed）|
| `λ_turnover`（turnover penalty）| `λ_turnover`（turnover penalty）| `lambda_capacity_used`（reframed）|
| `λ_slippage`（slippage penalty）| `λ_slippage`（slippage penalty）| `lambda_alpha`（reframed positive signal weight）|
| `λ_decay`（decay penalty）| `λ_decay`（decay penalty）| `lambda_sharpe`（reframed risk-adjusted return weight）|

**理由**：operator prompt 明示 5 dimensions = `alpha / sharpe / max_dd / hit_rate / capacity_used`，與 v5.8 §2 M6 命名（dd/tail/turnover/slippage/decay）不一致 — operator prompt 為 SoT；本 spec 採 operator prompt 5 λ。turnover/slippage/decay 在新 5 λ 框架下：
- `slippage / turnover`（成本面）→ 合入 `lambda_capacity_used`（capacity 用量越高，turnover/slippage 越大）
- `decay`（衰減面）→ 由 M7 decay_signals 單獨 authority（per CR-7 M7 single decay authority）；M6 不再雙寫 decay weight
- `tail risk`（極端面）→ `lambda_hit_rate` 反映勝率穩定度（hit_rate 反映 tail negative event 頻率）

**caveat**：上述命名 reframe 是 operator prompt 對齊；若 PM 仲裁切替 v5.8 §2 M6 原始 5 λ 命名（dd/tail/turnover/slippage/decay），本 spec §2 column 名須 patch（同 type / 同 CHECK / 同 index）。

### 1.4 不在本 spec 範圍

- 不寫 V110.sql 實檔（E1 IMPL 工作）
- 不在 Mac 跑 V110 SQL（必 Linux PG empirical）
- 不寫 M6 Bayesian 算法 IMPL Rust/Python code（IMPL 工作；sibling DESIGN spec §IMPL section land）
- 不寫 Auto-Allocator reward function 細節（Sprint 7+ IMPL）
- 不寫 healthcheck Python integration（E1 IMPL Worktree C）
- 不寫 M7 decay_signals schema（V113 sibling spec）
- 不寫 M9 A/B ab_tests schema（V108 sibling spec，Sprint 1A-γ）

---

## §2 Schema Changes

### 2.1 `learning.reward_weight_history` — 5-λ Reward Weight Time-Series Ledger

#### 2.1.1 表定義

```sql
CREATE TABLE IF NOT EXISTS learning.reward_weight_history (
    id                       BIGSERIAL PRIMARY KEY,
    strategy_id              TEXT NOT NULL,
    symbol                   TEXT NOT NULL,
    weight_set_id            UUID NOT NULL,
    lambda_alpha             NUMERIC(8,6) NOT NULL,
    lambda_sharpe            NUMERIC(8,6) NOT NULL,
    lambda_max_dd            NUMERIC(8,6) NOT NULL,
    lambda_hit_rate          NUMERIC(8,6) NOT NULL,
    lambda_capacity_used     NUMERIC(8,6) NOT NULL,
    bayesian_algorithm       TEXT NOT NULL
                             CHECK (bayesian_algorithm IN (
                                 'UCB',
                                 'EI',
                                 'PI',
                                 'GP_Matern52',
                                 'GP_RBF'
                             )),
    iter_num                 INTEGER NOT NULL CHECK (iter_num >= 0),
    iter_budget              INTEGER NOT NULL CHECK (iter_budget > 0),
    convergence_metric       NUMERIC NOT NULL,
    rollback_triggered       BOOLEAN NOT NULL DEFAULT FALSE,
    rollback_reason          TEXT,
    engine_mode              TEXT NOT NULL
                             CHECK (engine_mode IN ('paper','demo','live_demo','live','replay')),
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_lambda_alpha_bounds           CHECK (lambda_alpha          >= 0 AND lambda_alpha          <= 10),
    CONSTRAINT chk_lambda_sharpe_bounds          CHECK (lambda_sharpe         >= 0 AND lambda_sharpe         <= 10),
    CONSTRAINT chk_lambda_max_dd_bounds          CHECK (lambda_max_dd         >= 0 AND lambda_max_dd         <= 10),
    CONSTRAINT chk_lambda_hit_rate_bounds        CHECK (lambda_hit_rate       >= 0 AND lambda_hit_rate       <= 10),
    CONSTRAINT chk_lambda_capacity_used_bounds   CHECK (lambda_capacity_used  >= 0 AND lambda_capacity_used  <= 10),
    CONSTRAINT chk_iter_num_le_budget            CHECK (iter_num <= iter_budget),
    CONSTRAINT chk_rollback_reason_when_triggered CHECK (
        rollback_triggered = FALSE OR rollback_reason IS NOT NULL
    )
);
```

#### 2.1.2 設計理由（per column）

| Column | 設計 | 理由 |
|---|---|---|
| `id` BIGSERIAL PK | sequential | audit log temporal ordering; per V103 hypotheses range mirror |
| `strategy_id` TEXT NOT NULL | 動態擴增 | 5 既有 + Sprint 2+ 新策略；CHECK enum 易過時（per V103 §2.1.2）|
| `symbol` TEXT NOT NULL | per-symbol weight | reward weight per-strategy × per-symbol（25 symbol scale；e.g. grid_trading BTCUSDT 與 ma_crossover ETHUSDT weight 不同）|
| `weight_set_id` UUID NOT NULL | 唯一識別一 5-λ tuple | 同 weight_set 跨 strategy / overlay 可重用；UUID for cross-system import safe |
| `lambda_*` 5 column NUMERIC(8,6) | 6 位小數 | λ 值範圍 [0, 10]；6 位小數提供 0.000001 精度（hyperparameter typical resolution）|
| `lambda_*` CHECK [0, 10] bounds | per-λ 5 個 CHECK | per H-2 bounds + v5.8 §2 M6 line 236「λ_dd ∈ [0.5, 5.0]」example；upper bound 10 為 safety margin（actual operator-set tighter bounds in risk_config TOML）|
| `bayesian_algorithm` TEXT + CHECK 5 值 | TEXT + CHECK | acquisition function 3 (UCB/EI/PI) + GP kernel 2 (Matern52/RBF) 共 5 enum；sibling DESIGN spec §3-§4 規範算法選擇 |
| `iter_num` INTEGER CHECK >= 0 | non-negative | iteration counter；0 = initial random sample |
| `iter_budget` INTEGER CHECK > 0 | positive | 預設 Sprint 4-5 micro 10 / Sprint 7+ Advisory 50 / Y2 auto 100（sibling DESIGN §5）|
| `chk_iter_num_le_budget` | iter_num ≤ budget | 不變式：iteration 不超 budget |
| `convergence_metric` NUMERIC | 浮點 | best-so-far objective（GP posterior mean of WLS sharpe minus dd penalty）；NUMERIC 不 REAL（避免精度損失）|
| `rollback_triggered` BOOLEAN NOT NULL DEFAULT FALSE | 顯式 boolean | per H-2 rollback cap schema 反映；default FALSE 表常規 proposal |
| `rollback_reason` TEXT NULL | reason | 配合 rollback_triggered=TRUE；e.g. `'accumulated_revert_cap_exceeded'` / `'next_month_sharpe_below_baseline'` / `'operator_manual_revert'` |
| `chk_rollback_reason_when_triggered` CHECK | 不變式 | rollback_triggered=TRUE 必含 reason |
| `engine_mode` NOT NULL CHECK 5 值 | TEXT + CHECK | per CLAUDE.md §七 + MIT memory baseline；本表額外加 `'replay'` 為 M11 continuous replay 走 M6 advisory weight 用（v5.8 §M11 line 410 hookup）；training filter 必 `IN ('live','live_demo')` |
| `created_at` DEFAULT NOW() | audit timestamp | append-only design；無 updated_at |

#### 2.1.3 Indexes

```sql
-- 主 hot-path: per-strategy × per-symbol timeline query
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reward_weight_strategy_symbol_created
    ON learning.reward_weight_history (strategy_id, symbol, created_at DESC);

-- weight_set drill-down: 同 set_id 跨 strategy/symbol 查
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reward_weight_set_id
    ON learning.reward_weight_history (weight_set_id);

-- H-2 rollback audit: partial index for rollback events
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reward_weight_rollback_audit
    ON learning.reward_weight_history (strategy_id, created_at DESC)
    WHERE rollback_triggered = TRUE;

-- engine_mode filter: ML training filter hot path
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reward_weight_engine_mode_live
    ON learning.reward_weight_history (strategy_id, symbol, created_at DESC)
    WHERE engine_mode IN ('live', 'live_demo');
```

**理由**：
- `(strategy_id, symbol, created_at DESC)`：高頻 query `SELECT * FROM learning.reward_weight_history WHERE strategy_id=$1 AND symbol=$2 ORDER BY created_at DESC LIMIT 100` for Allocator monthly opt history pull
- `(weight_set_id)`：set-level drill-down，e.g. `SELECT * FROM learning.reward_weight_history WHERE weight_set_id=$1` for Bayesian opt run trace
- `(strategy_id, created_at DESC) WHERE rollback_triggered=TRUE` partial：H-2 audit hot path；非 rollback row 不索引省空間
- `(strategy_id, symbol, created_at DESC) WHERE engine_mode IN ('live','live_demo')` partial：ML training filter 對齊 MIT memory baseline，避免 paper/demo 污染

#### 2.1.4 Row 量級估算

- Sprint 4-5 micro opt：5 strategy × 25 symbol × 10 iter = ~1,250 row per micro run
- Sprint 7+ Advisory monthly：5 strategy × 25 symbol × 50 iter × 12 month/yr = ~75,000 row/yr
- Y2 auto-update：5 strategy × 25 symbol × 100 iter × 365 day-trigger/yr = ~456,250 row/yr（peak）
- Sprint 1A-β apply 後立即 0 row（Foundation stage per MIT pipeline maturity）

**Hypertable 判斷**：**Regular table**。理由：
- 即使 Y2 auto peak ~456k row/yr，per-day insert ~1,250 row 屬低基數
- 無時序 burst 壓力（Bayesian opt run 是 monthly 批次）
- regular table + 4 index 即足；hypertable chunk overhead 不划算

### 2.2 `learning.bayesian_opt_runs` — Bayesian Optimization Run Audit

> **注**：operator prompt 列「V110 full DDL 必含」section 1-8 全聚焦 `learning.reward_weight_history` 主表；本 spec **不寫** `bayesian_opt_runs` 第二表（避免擴 scope 違反 operator prompt boundary）。
>
> 若 PA dispatch 期 PM 仲裁要求補 `bayesian_opt_runs` 第二表（per v5.7 placeholder spec §2.2 原 12-field 設計），本 spec §2.2 可後續擴；本次 land 限 §2.1 一表 + per-run aggregation 由 `reward_weight_history` 透過 `weight_set_id` GROUP BY 推導。

### 2.3 ENUM 列表 (per CR-X 對齊規則)

- `bayesian_algorithm` ENUM 5 值（UCB / EI / PI / GP_Matern52 / GP_RBF）
- `engine_mode` ENUM 5 值（paper / demo / live_demo / live / replay）
- `rollback_triggered` BOOLEAN (TRUE / FALSE)
- `rollback_reason` 自由 TEXT（不 ENUM，避免 future reason 擴充破 backward compat；應用層自有 5-10 standard reason 集）

### 2.4 H-2 30% Rollback Cap Schema 反映

H-2 mandate 在 schema layer 反映三處：
1. `rollback_triggered BOOLEAN NOT NULL DEFAULT FALSE`：顯式 boolean column
2. `rollback_reason TEXT`：reason audit trail
3. `chk_rollback_reason_when_triggered` CHECK：不變式 enforce

實際 30% threshold + 7d window 由 risk_config TOML 定（不 hardcode SQL）：
```toml
# settings/risk_config_<env>.toml 預期 section（IMPL 期 land；本 spec 不寫 TOML）
[m6_bayesian_opt]
rollback_cap_window_days = 7
rollback_cap_ratio_threshold = 0.30   # H-2 30%
max_delta_per_lambda = 0.5            # per-update bound
```

應用層 7d cron 跑：
```python
# pseudo-code, sibling DESIGN spec §IMPL phase
def check_rollback_cap(strategy_id, symbol):
    last_7d_history = query("""
        SELECT lambda_alpha, lambda_sharpe, lambda_max_dd, lambda_hit_rate, lambda_capacity_used
        FROM learning.reward_weight_history
        WHERE strategy_id = %s AND symbol = %s
          AND created_at > NOW() - INTERVAL '7 days'
          AND engine_mode IN ('live', 'live_demo')
        ORDER BY created_at ASC
    """, strategy_id, symbol)
    cumulative_revert_pct = compute_revert_pct(last_7d_history)
    if cumulative_revert_pct > 0.30:
        # 寫 row rollback_triggered=TRUE + reason
        write_rollback_row(strategy_id, symbol, reason='accumulated_revert_cap_exceeded')
        # 凍結 M6 auto-propose（per H-2 manage）
```

### 2.5 Hypertable 判斷（重申）

**結論：regular table**。理由：
- Y2 auto peak ~456k row/yr; Sprint 4-7 ~75k row/yr；per-day insert ~1,250 row
- 無時序 burst 壓力（Bayesian opt 是 monthly / daily batch）
- regular table + 4 index 即足
- hypertable chunk overhead（per V006 7-day chunk）對此量級不划算

對比 V107 (M11 replay divergence_log; hypertable 必 per CR-7) — V107 hypertable 是因 5 strategy × per-fill 級資料密度 ~hundreds/day；V110 是 monthly batch 級不必 hypertable。

### 2.6 Cross-strategy materialized view（optional）

operator prompt §V110 full DDL #4「Cross-strategy materialized view (optional)：`mv_latest_weights_per_strategy`」— 本 spec 設計：

```sql
-- Optional materialized view: 每 strategy × symbol 最新 weight
-- 若 application layer 高頻 query 「current weight for X strategy Y symbol」，加此 MV 加速
CREATE MATERIALIZED VIEW IF NOT EXISTS learning.mv_latest_weights_per_strategy AS
SELECT DISTINCT ON (strategy_id, symbol)
    strategy_id,
    symbol,
    weight_set_id,
    lambda_alpha,
    lambda_sharpe,
    lambda_max_dd,
    lambda_hit_rate,
    lambda_capacity_used,
    bayesian_algorithm,
    iter_num,
    iter_budget,
    convergence_metric,
    rollback_triggered,
    engine_mode,
    created_at
FROM learning.reward_weight_history
WHERE engine_mode IN ('live', 'live_demo')
ORDER BY strategy_id, symbol, created_at DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_latest_weights_strategy_symbol
    ON learning.mv_latest_weights_per_strategy (strategy_id, symbol);

-- Refresh policy: per monthly Bayesian opt completion + manual REFRESH MATERIALIZED VIEW CONCURRENTLY
```

**caveat**：optional；Sprint 7+ Advisory IMPL 期 evaluate 是否 land；本 spec 不強制（避免 over-engineering）。若 query pattern 顯示 hot path，IMPL 期 ADD 一條 small V### migration。

---

## §3 Guard A/B/C Templates（per CLAUDE.md §七 + V094 mirror）

V110 涉及 1 個 NEW table CREATE（§2.1）+ optional MV（§2.6）。

- **Guard A**：表已存在但 schema 不符 → RAISE
- **Guard B**：不適用（V110 無 ALTER 既有 column）
- **Guard C**：CHECK constraint + ENUM 值齊全 + bounds + index 對齊驗證 → RAISE on mismatch

### 3.1 Guard A — table existence + 既有 schema 對齊驗證

```sql
-- ============================================================
-- Guard A: V110 預檢 — 若 learning.reward_weight_history 已存在，
-- 必驗 V110 spec column 全俱在；缺即 RAISE
-- ============================================================
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- learning.reward_weight_history 已存在的情境下 check column 完整性
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='reward_weight_history'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'strategy_id', 'symbol', 'weight_set_id',
            'lambda_alpha', 'lambda_sharpe', 'lambda_max_dd',
            'lambda_hit_rate', 'lambda_capacity_used',
            'bayesian_algorithm', 'iter_num', 'iter_budget',
            'convergence_metric', 'rollback_triggered', 'rollback_reason',
            'engine_mode', 'created_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='learning' AND table_name='reward_weight_history'
              AND column_name=c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V110 Guard A FAIL: learning.reward_weight_history exists but missing columns: %. '
                'Possible stale stub from earlier placeholder version — resolve schema reconciliation before applying V110.',
                v_missing;
        END IF;
    END IF;

    -- 無 cross-V### FK target dependency（M6 是獨立 reward weight authority；不 FK 到 V103 hypotheses / V108 ab_tests / V113 decay_signals）
END $$;
```

### 3.2 Guard B — 不適用

V110 不 ALTER 既有 column type；無 type-sensitive 檢查需求。本 spec 不設 Guard B 段。

### 3.3 Guard C — CHECK constraint + ENUM 值齊全 + bounds + index 對齊驗證

```sql
-- ============================================================
-- Guard C: V110 預檢 — 重跑 V110 時 idempotent 檢查
-- CHECK constraint + bounds + index 對齊
-- ============================================================
DO $$
DECLARE v_actual TEXT;
BEGIN
    -- bayesian_algorithm CHECK 5 值齊全
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.reward_weight_history'::regclass
      AND conname LIKE '%bayesian_algorithm%check%';
    IF v_actual IS NOT NULL THEN
        IF position('UCB' IN v_actual) = 0
           OR position('EI' IN v_actual) = 0
           OR position('PI' IN v_actual) = 0
           OR position('GP_Matern52' IN v_actual) = 0
           OR position('GP_RBF' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V110 Guard C FAIL: learning.reward_weight_history bayesian_algorithm CHECK enum mismatch. '
                'Actual: %. Expected to contain UCB/EI/PI/GP_Matern52/GP_RBF.',
                v_actual;
        END IF;
    END IF;

    -- engine_mode CHECK 5 值齊全（含 replay for M11 continuous replay hookup）
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.reward_weight_history'::regclass
      AND conname LIKE '%engine_mode%check%';
    IF v_actual IS NOT NULL THEN
        IF position('paper' IN v_actual) = 0
           OR position('demo' IN v_actual) = 0
           OR position('live_demo' IN v_actual) = 0
           OR position('live' IN v_actual) = 0
           OR position('replay' IN v_actual) = 0
        THEN
            RAISE EXCEPTION
                'V110 Guard C FAIL: learning.reward_weight_history engine_mode CHECK enum mismatch. '
                'Actual: %. Expected paper/demo/live_demo/live/replay.',
                v_actual;
        END IF;
    END IF;

    -- 5 lambda bounds CHECK 真存在 + [0, 10] range
    FOR v_actual IN
        SELECT pg_get_constraintdef(c.oid)
        FROM pg_constraint c
        WHERE c.conrelid='learning.reward_weight_history'::regclass
          AND c.conname LIKE 'chk_lambda_%_bounds'
    LOOP
        IF position('>= 0' IN v_actual) = 0 OR position('<= 10' IN v_actual) = 0 THEN
            RAISE EXCEPTION
                'V110 Guard C FAIL: lambda bounds CHECK constraint must enforce [0, 10] range. '
                'Actual: %.',
                v_actual;
        END IF;
    END LOOP;

    -- chk_iter_num_le_budget 不變式 CHECK
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.reward_weight_history'::regclass
      AND conname = 'chk_iter_num_le_budget';
    IF v_actual IS NULL THEN
        RAISE EXCEPTION
            'V110 Guard C FAIL: chk_iter_num_le_budget missing. Iteration count invariant violated.';
    END IF;

    -- chk_rollback_reason_when_triggered 不變式 CHECK
    SELECT pg_get_constraintdef(oid) INTO v_actual
    FROM pg_constraint
    WHERE conrelid='learning.reward_weight_history'::regclass
      AND conname = 'chk_rollback_reason_when_triggered';
    IF v_actual IS NULL THEN
        RAISE EXCEPTION
            'V110 Guard C FAIL: chk_rollback_reason_when_triggered missing. H-2 rollback audit invariant violated.';
    END IF;

    -- 4 index 存在驗證
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='learning' AND tablename='reward_weight_history'
          AND indexname='idx_reward_weight_strategy_symbol_created'
    ) THEN
        RAISE EXCEPTION
            'V110 Guard C FAIL: idx_reward_weight_strategy_symbol_created missing. Hot-path index violated.';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes
        WHERE schemaname='learning' AND tablename='reward_weight_history'
          AND indexname='idx_reward_weight_set_id'
    ) THEN
        RAISE EXCEPTION
            'V110 Guard C FAIL: idx_reward_weight_set_id missing. weight_set drill-down index violated.';
    END IF;
END $$;
```

### 3.4 Guard 設計理念（per V094 mirror）

| Guard | 觸發場景 | RAISE 條件 | NOT RAISE 條件（idempotent）|
|---|---|---|---|
| A | reward_weight_history 已存在但 column 缺 | RAISE | 全 17 column 俱在 / table 不存在（首次跑）|
| C | CHECK constraint 缺 enum / bounds 缺 / index 缺 | RAISE | constraint+index 完整（重跑）|

**重跑 V110 第二次必不 RAISE**（idempotency per CLAUDE.md §七 V055/V083/V084 incident precedent）。

---

## §4 Linux PG Empirical Dry-Run Protocol（mandatory）

per CLAUDE.md §七 + `feedback_v_migration_pg_dry_run.md` + V055 5-round loop / V083 / V084 incident chain，V110 涉及：
- PG reflection（`information_schema.tables` + `information_schema.columns` for Guard A）
- CHECK constraint ENUM runtime semantic（Guard C）
- 無 FK constraint（M6 獨立 authority）
- 無 hypertable 操作（regular table）

**必先 Linux PG empirical 驗證**，禁 Mac mock pytest 代替。

### 4.1 PA C9 待跑的 4 條 SQL（spec sign-off 前必補資料）

per operator prompt + MIT 5.21 audit Risk 2，PA 在 dispatch 前必執行以下 ssh trade-core PG query：

```bash
# Query 1: _sqlx_migrations head + recent versions
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT max(version), array_agg(version ORDER BY version DESC) FROM (SELECT version FROM _sqlx_migrations ORDER BY version DESC LIMIT 10) sub\""
# Expected: V109 already applied (Sprint 1A-β earlier modules); V110 = next slot

# Query 2: learning.reward_weight_history 是否已存在
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema='learning' AND table_name='reward_weight_history'\""
# Expected: 0 row (first apply) / 1 row (Guard A 驗證 17 column 全俱在)

# Query 3: PG 容量 + learning schema 大小
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT pg_total_relation_size(schemaname || '.' || tablename) / 1024 / 1024 AS mb, schemaname, tablename FROM pg_tables WHERE schemaname='learning' ORDER BY mb DESC LIMIT 20\""
# Expected: 既有 learning 表大小分布；reward_weight_history 不存在或 <1 MB

# Query 4: UUID extension 已 install 驗證（weight_set_id UUID column 用）
ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c \"SELECT extname, extversion FROM pg_extension WHERE extname IN ('uuid-ossp', 'pgcrypto')\""
# Expected: uuid-ossp 或 pgcrypto 已 install（OpenClaw 既有；V001 land 期已 enable）
```

**待 PA C9 補資料的 3 處 placeholder**（spec sign-off 前必更新）：

1. `_sqlx_migrations` head 真實 = ?（spec 假設 V109；若 V108/V109 未 apply 需更新 V110 numbering）
2. `learning.reward_weight_history` 是否存在（V110 預設首次 land）
3. UUID extension 名稱（`uuid-ossp` vs `pgcrypto` — IMPL 期 `gen_random_uuid()` from pgcrypto 或 `uuid_generate_v4()` from uuid-ossp）

### 4.2 Round 1 — V110 SQL 真實 PG semantic empirical 驗證

```bash
# ssh trade-core 執行（不在 Mac 跑）
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V110__reward_weight_history.sql
"
```

**Round 1 必驗 10 項**（empirical SELECT verify after V110 apply）：

```sql
-- 1. learning.reward_weight_history 表存在 + 17 columns
SELECT count(*) FROM information_schema.columns
WHERE table_schema='learning' AND table_name='reward_weight_history';
-- Expected: 17

-- 2. 5 lambda CHECK bounds [0, 10]
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.reward_weight_history'::regclass
  AND conname LIKE 'chk_lambda_%_bounds';
-- Expected: 5 row，每 row 含 '>= 0' + '<= 10'

-- 3. bayesian_algorithm CHECK 5 values
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.reward_weight_history'::regclass
  AND conname LIKE '%bayesian_algorithm%check%';
-- Expected: 1 row 含 UCB/EI/PI/GP_Matern52/GP_RBF

-- 4. engine_mode CHECK 5 values (含 replay)
SELECT pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.reward_weight_history'::regclass
  AND conname LIKE '%engine_mode%check%';
-- Expected: 1 row 含 paper/demo/live_demo/live/replay

-- 5. chk_iter_num_le_budget + chk_rollback_reason_when_triggered 不變式 CHECK
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid='learning.reward_weight_history'::regclass
  AND conname IN ('chk_iter_num_le_budget', 'chk_rollback_reason_when_triggered');
-- Expected: 2 row

-- 6. Index 確認
SELECT indexname FROM pg_indexes
WHERE schemaname='learning' AND tablename='reward_weight_history'
ORDER BY indexname;
-- Expected: 5 indexes
--   - reward_weight_history_pkey (PK)
--   - idx_reward_weight_strategy_symbol_created
--   - idx_reward_weight_set_id
--   - idx_reward_weight_rollback_audit
--   - idx_reward_weight_engine_mode_live

-- 7. engine_mode CHECK 真 reject 非 5 值（empirical INSERT test）
BEGIN;
SAVEPOINT test_engine_mode;
INSERT INTO learning.reward_weight_history
    (strategy_id, symbol, weight_set_id, lambda_alpha, lambda_sharpe, lambda_max_dd,
     lambda_hit_rate, lambda_capacity_used, bayesian_algorithm, iter_num, iter_budget,
     convergence_metric, engine_mode)
VALUES
    ('test_strat', 'BTCUSDT', gen_random_uuid(), 0.5, 0.3, 0.2, 0.4, 0.6,
     'EI', 0, 50, 0.0, 'INVALID_MODE');
-- Expected: ERROR: violates check constraint
ROLLBACK TO SAVEPOINT test_engine_mode;

-- 8. lambda bounds CHECK reject > 10 (empirical INSERT test)
SAVEPOINT test_lambda_bounds;
INSERT INTO learning.reward_weight_history
    (strategy_id, symbol, weight_set_id, lambda_alpha, lambda_sharpe, lambda_max_dd,
     lambda_hit_rate, lambda_capacity_used, bayesian_algorithm, iter_num, iter_budget,
     convergence_metric, engine_mode)
VALUES
    ('test_strat', 'BTCUSDT', gen_random_uuid(), 11.0, 0.3, 0.2, 0.4, 0.6,
     'EI', 0, 50, 0.0, 'live');
-- Expected: ERROR: violates chk_lambda_alpha_bounds
ROLLBACK TO SAVEPOINT test_lambda_bounds;

-- 9. chk_iter_num_le_budget reject iter_num > budget
SAVEPOINT test_iter_invariant;
INSERT INTO learning.reward_weight_history
    (strategy_id, symbol, weight_set_id, lambda_alpha, lambda_sharpe, lambda_max_dd,
     lambda_hit_rate, lambda_capacity_used, bayesian_algorithm, iter_num, iter_budget,
     convergence_metric, engine_mode)
VALUES
    ('test_strat', 'BTCUSDT', gen_random_uuid(), 0.5, 0.3, 0.2, 0.4, 0.6,
     'EI', 100, 50, 0.0, 'live');
-- Expected: ERROR: violates chk_iter_num_le_budget
ROLLBACK TO SAVEPOINT test_iter_invariant;

-- 10. chk_rollback_reason_when_triggered reject rollback=TRUE without reason
SAVEPOINT test_rollback_invariant;
INSERT INTO learning.reward_weight_history
    (strategy_id, symbol, weight_set_id, lambda_alpha, lambda_sharpe, lambda_max_dd,
     lambda_hit_rate, lambda_capacity_used, bayesian_algorithm, iter_num, iter_budget,
     convergence_metric, rollback_triggered, engine_mode)
VALUES
    ('test_strat', 'BTCUSDT', gen_random_uuid(), 0.5, 0.3, 0.2, 0.4, 0.6,
     'EI', 0, 50, 0.0, TRUE, 'live');
-- Expected: ERROR: violates chk_rollback_reason_when_triggered
ROLLBACK TO SAVEPOINT test_rollback_invariant;
ROLLBACK;
```

### 4.3 Round 2 — Idempotency 驗證

重跑 V110.sql 第二次必不 RAISE / 必不重複建 index / 必不 fail：

```bash
ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai \
    -v ON_ERROR_STOP=1 -f sql/migrations/V110__reward_weight_history.sql
"
# Expected exit code 0; all DO blocks output NOTICE-only PASS; 0 RAISE EXCEPTION
```

**Round 2 後驗證**：
```sql
-- 確認 V110 不 double-create
SELECT count(*) FROM information_schema.tables
WHERE table_schema='learning' AND table_name='reward_weight_history';
-- Expected: 1

-- 確認 index 不 double-create
SELECT count(*) FROM pg_indexes
WHERE schemaname='learning' AND tablename='reward_weight_history';
-- Expected: 5 (1 PK + 4 user index)
```

### 4.4 為何 Mac mock pytest 不夠（V055 5-round loop 教訓）

per memory `feedback_v_migration_pg_dry_run.md` + `project_2026_05_02_p0_sqlx_hash_drift`：
- Mac mock pytest 無法捕捉 PG runtime 真實 PL/pgSQL DO block semantic（特別是 Guard A `array_agg` + `unnest`）
- Mac static parse review 無法驗 `pg_get_constraintdef` 真實輸出對齊 spec
- Mac 無法驗 5 lambda CHECK bounds 真 reject (empirical INSERT test 必 Linux PG)
- V055 chain 5 round 都 Mac false-pass 後 Linux 撞 bug；V110 / V094 / V083 / V084 / V103 全須遵守 V055 mandate

**E2 / E4 / A3 review 必含 Linux PG dry-run gate 證據 ID**（per CLAUDE.md §七 + V094 §4.3 範式）。

---

## §5 sqlx Checksum Repair SOP

per memory `project_2026_05_02_p0_sqlx_hash_drift`（commit `3681f83`），V110 file edit 後 DB checksum 必同步：

```bash
# E1 IMPL：寫 V110.sql 完成後跑 Linux dry-run（per §4.2）
# 若 V110.sql 落地後又被 edit → DB checksum drift
# 必跑 repair binary 同步 checksum 到 _sqlx_migrations table

ssh trade-core "
  cd ~/BybitOpenClaw/srv && \
  cargo run --release --bin repair_migration_checksum -- --version 110
"
# Expected: V110 checksum updated in _sqlx_migrations table to match new file SHA
```

### 5.1 Engine restart 後驗證 sqlx migrate 不 panic

```bash
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/restart_all.sh --rebuild"

ssh trade-core "tail -200 ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/openclaw_engine/logs/engine.log 2>&1 | grep -E 'sqlx|migration|panic'"
# Expected: 0 panic; 'Applied migrations' 正常 log; V110 success=t in _sqlx_migrations

ssh trade-core "PGPASSWORD='<REDACTED>' psql -h localhost -U trading_admin -d trading_ai -c 'SELECT version, success, description FROM _sqlx_migrations WHERE version=110;'"
# Expected: 1 row, success=t
```

### 5.2 治理盲點防範

per `project_2026_05_02_p0_sqlx_hash_drift` + V094 §5.3：cargo test PASS ≠ runtime sqlx migrate 驗證。E2 / E4 review 必含「engine restart 實測 + sqlx migrate runtime 不 panic」driver evidence。

---

## §6 IMPL Plan（簡）

### 6.1 E1 工作鏈

```
本 V110 spec PM sign-off + PA C9 dry-run 補資料 land
  ↓
PA dispatch decide V108 (M9 A/B) ordering（V110 land 應先於 V108，per cross-V### dependency §7）
  ↓
E1 IMPL (1 worktree)：
  └─ Worktree A: 寫 V110.sql 含 Guard A/C + 1 CREATE TABLE + 4 CONCURRENTLY index
     (~150 LOC SQL, 1 E1-day，含 Linux PG dry-run × 2 round)
  ↓
E2 review (≥30min, 重點查 §6.2 三高風險點)
  ↓
E4 regression (cargo test --release + pytest healthcheck)
  ↓
ssh trade-core 跑 V110.sql Linux PG dry-run × 2 round
  ↓
restart_all --rebuild deploy
  ↓
engine restart verify sqlx migrate runtime PASS
  ↓
QA cycle（Sprint 1A-β 整體 closure）
  ↓
PM sign-off
```

### 6.2 E2 Review 重點 3 項

#### 6.2.1 Linux PG dry-run gate 證據 ID 必出現

E2 PR 審查必拒「無 Linux PG dry-run × 2 round 證據 ID」的 V110 PR：
- E1 IMPL commit message 含 dry-run round 1 + round 2 commit ID 或 ssh trade-core 操作 ID
- 重跑 V110 SQL 第二次的 NOTICE 輸出 attached（idempotency 證明）
- empirical INSERT test 4 條 reject 結果 attached（5 lambda bounds + iter invariant + rollback invariant + engine_mode）

#### 6.2.2 5 λ column 命名對齊 operator prompt

E2 必驗 V110 SQL 5 lambda column 名 = `lambda_alpha / lambda_sharpe / lambda_max_dd / lambda_hit_rate / lambda_capacity_used`：
- 若 PA / PM 仲裁切替 v5.8 §2 M6 原始命名（dd/tail/turnover/slippage/decay），E2 必確認 sibling DESIGN spec §1.3 reframe 邏輯一致
- 命名不一致 → reject

#### 6.2.3 engine_mode CHECK 5 值（含 replay）

E2 必跑 Guard C SQL 確認 engine_mode CHECK 含 `'paper','demo','live_demo','live','replay'` 5 值：
- `replay` 為 M11 continuous replay hookup 用（v5.8 §M11 line 410）
- 缺 `replay` → reject（會破 M11 nightly replay job 寫入）
- training filter `IN ('live','live_demo')` 在 sibling DESIGN spec §8 才提（M6 training pipeline 範圍）

---

## §7 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V110 | 無 outgoing FK | M6 是獨立 reward weight authority；不 FK 到其他 V### M-module |
| V113 (M7 decay) | V110（**reference only**；schema 無 FK）| sibling DESIGN spec §8：M6 weight ref M7 decay signal（per CR-7 M7 single decay authority）；implementation level read M7 decay_signals 不 schema FK |
| V108 (M9 A/B, Sprint 1A-γ) | V110（**reference only**；schema 無 FK）| sibling DESIGN spec §7：M6 ↔ M9 A/B integration；weight variant 走 M9 cluster 3 (risk profile)；schema-level 不 FK 避免 cross-1A-β/γ race |
| V107 (M11 replay div) | V110（**reference only**；schema 無 FK）| M11 nightly replay 走 M6 advisory weight 用；engine_mode='replay' row 寫入 |

**Sprint 1A-β dispatch ordering**：V110 可獨立 land；不阻擋其他 module。
**Sprint 1A-β → 1A-γ ordering**：V110 必先於 V108 land（V108 Sprint 1A-γ 引用 M6 weight variant）。

---

## §8 Backward Compat

### 8.1 Append-only 設計

V110 是 **append-only schema migration**：
- 加 1 個 NEW table（learning schema 既有 + 1 optional MV）
- 0 ALTER 既有 column
- 0 DROP 既有 schema
- 0 RENAME

### 8.2 不破現有 SELECT / INSERT / UPDATE

| 既有操作 | V110 影響 |
|---|---|
| `SELECT * FROM learning.*` | new table 不影響既有 21+ learning tables |
| 既有 healthcheck（55 個 check per V094 §7.5）| 0 影響（沒有 check 引用 V110 新表）；新 healthcheck Sprint 1B 才加 |

### 8.3 對 future writer behaviour

| Table | 第一個 row 來源 | Sprint |
|---|---|---|
| learning.reward_weight_history | E1 IMPL Sprint 7+ Advisory Bayesian opt job writer | 1A-β land schema → Sprint 7 first writer row |

**Empty-table 期間**：V110 apply 後立即 0 row（Foundation stage per MIT pipeline maturity）；writer code spawn 是 Sprint 7+ 工作（per MIT pipeline maturity audit Skeleton stage）。

---

## §9 5 λ Column vs JSONB Tradeoff Discussion

operator prompt §V110 full DDL #8「5 λ 值 vs JSONB tradeoff discussion」：

### 9.1 為何選 5 column 不選 JSONB

| Aspect | 5 column 設計（本 spec 採） | JSONB 替代 | 結論 |
|---|---|---|---|
| **Query performance** | 直接 `WHERE lambda_alpha > 0.5` index-friendly | `WHERE (lambdas->>'alpha')::numeric > 0.5` 需 functional index（額外開銷）| 5 column 勝 |
| **Index 友善** | per-column index 直接（e.g. `(strategy_id, lambda_alpha)`）| GIN index for JSONB + 額外 expression index per λ key | 5 column 勝 |
| **CHECK constraint per-λ enforcement** | `chk_lambda_alpha_bounds CHECK (lambda_alpha >= 0 AND <= 10)` 直接 | JSONB CHECK 需 `((lambdas->>'alpha')::numeric BETWEEN 0 AND 10)` 複雜 | 5 column 勝 |
| **Schema evolution** | 加新 λ 需 ALTER TABLE ADD COLUMN | JSONB 自然擴展不需 schema change | JSONB 勝（但 5 λ 是 v5.8 M6 firm scope，無需 freq evolve）|
| **Storage size** | 5 NUMERIC(8,6) = ~40 byte/row | JSONB serialized ~80-120 byte/row（含 key 名）| 5 column 勝 ~2-3× |
| **Type safety** | PG type system enforce | JSONB 弱 type（`->>`回 TEXT；需 cast）| 5 column 勝 |
| **Cross-language byte-equal**（per H-18）| 直接 5 NUMERIC dump 1e-4 容差 fixture | JSONB key ordering / float precision drift 風險 | 5 column 勝 |
| **GROUP BY / aggregate** | `AVG(lambda_alpha)` 直接 | `AVG((lambdas->>'alpha')::numeric)` 慢 | 5 column 勝 |
| **Analytical reporting / ML feature** | DataFrame 直接 read | JSONB 需 pre-parse | 5 column 勝 |
| **Future > 10 λ scaling** | ALTER TABLE 加 column | JSONB 自然支援 | JSONB 勝（但 M6 firm 5 λ；scope 不擴）|

**結論**：5 column 在 9/10 維度勝；JSONB 唯一勝在 schema evolution + > 10 λ scaling，但 M6 scope 明示 5 λ firm（v5.8 §2 M6 line 234）。**採 5 column 設計**。

### 9.2 替代設計：hybrid

若未來 M6 scope 擴展到 > 10 λ（e.g. Y3 加 per-regime-aware λ），可考慮 hybrid：
- 5 core λ 保持 column（hot path）
- 額外 λ 走 `extra_lambdas JSONB`（cold path）

本 spec 不 land hybrid（avoid premature complexity）；IMPL 期 Y3+ evaluate。

---

## §10 Rollback Path

### 10.1 V110 rollback

```sql
DROP MATERIALIZED VIEW IF EXISTS learning.mv_latest_weights_per_strategy;
DROP TABLE IF EXISTS learning.reward_weight_history;
-- 0 row loss（V110 apply 後立即 0 row）
-- 4 index 隨 table DROP 自動 drop
```

### 10.2 V096 boundary

per V103 spec §8.3：rollback 路徑不跨 V096（V096 drop dead tables 不可逆）。V110 rollback 全在 V096 之後（V096 < V098 < V103 < V110），無 boundary 風險。

---

## §11 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰

### 11.1 改動風險評級 = **低**

| Risk | 評級 | Mitigation |
|---|---|---|
| schema migration 失敗 | 低 | Linux PG empirical dry-run × 2 + sqlx checksum repair SOP（V055/V083/V084 incident precedent）|
| 5 λ 命名不對齊 operator prompt | 低 | §1.3 顯式 reframe table + §6.2.2 E2 review 重點驗 |
| H-2 30% rollback cap schema 反映不全 | 低 | §2.4 三 column 設計 + chk_rollback_reason_when_triggered 不變式 CHECK |
| engine_mode `replay` enum 缺漏 | 低-中 | §3.3 Guard C 顯式驗 5 值；M11 hookup IMPL 期會撞 |
| Sprint 7+ writer 接線延後 | 低 | V110 apply 後立即 0 row 屬 Foundation stage 設計預期；MIT pipeline maturity audit 接受 |
| backward-compat 風險 | 極低 | 全 NEW table，0 ALTER / 0 DROP / 0 RENAME |

### 11.2 16 根原則合規（16/16）

| 原則 | 狀態 | 證據 |
|---|---|---|
| #1 單一寫入口 | PASS | V110 不改 IntentProcessor / submit_intent 既有契約 |
| #2 讀寫分離 | PASS | reward_weight_history 是 Allocator advisory layer，非 trading 寫入路徑 |
| #3 AI→Lease→複核→執行 | PASS | M6 weight propose 走 governance approval（per v5.8 §2 M6 line 242）；non-bypass |
| #4 策略不繞風控 | PASS | M6 不觸 Guardian / risk_envelope；M6 是 reward weight tuning 非 risk override |
| #5 生存 > 利潤 | PASS | H-2 30% rollback cap + per-update delta cap = 收縮優先設計 |
| #6 失敗默認收縮 | PASS | CHECK enum allowlist + NOT NULL + DEFAULT FALSE rollback_triggered = fail-closed |
| #7 學習 ≠ 改寫 Live | PASS | reward_weight_history 是 advisory layer；live weight 適用須 operator approve（per v5.8 §2 M6 line 242）|
| #8 交易可解釋 | PASS（**strengthens**）| weight_set_id UUID + bayesian_algorithm + iter_num + convergence_metric 提供 full audit trail |
| #9 災難保護 | PASS | rollback_triggered TRUE 為 H-2 cap trigger signal，service Guardian |
| #10 認知誠實 | PASS | §1.3 顯式標 5 λ 命名 reframe vs v5.8 §2 M6 原始命名；§4.1 列 PA C9 待補資料 |
| #11 P0/P1 內自主 | PASS | V110 不觸 cognitive_modulator |
| #12 持續進化 | PASS | reward weight tuning 是 Allocator 進化前提 |
| #13 AI cost 感知 | PASS | Bayesian opt run 是 batched compute（monthly / Y2 daily），非 hot path AI call |
| #14 零外部成本可運行 | PASS | V110 純 PG schema，無外部依賴；Bayesian opt 用 scikit-learn / scikit-optimize local |
| #15 多 Agent 協作 | PASS | V110 不觸 MessageBus / agent topics |
| #16 組合風險 | PASS | reward weight tuning 屬 portfolio-level allocation 優化；強化 #16 |

### 11.3 DOC-08 §12 9 條安全不變量觸碰（0/9）

| 不變量 | 觸碰 | 評估 |
|---|---|---|
| Pre-trade audit/replay 必開 | NO | V110 不改 pre-trade gate |
| Lease 必在執行前 acquired | NO | V110 不觸 lease |
| 執行回報必落 fills 表 | NO | V110 不改 fills 寫入路徑 |
| 風控降級 → engine 自動止血 | NO | V110 不觸風控 |
| Authorization 過期 → cancel_token shutdown | NO | V110 不觸 authorization |
| Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒 | NO | V110 不觸 mainnet spawn |
| Bybit retCode != 0 → fail-closed 不重試 | NO | V110 不觸 retry |
| Reconciler 對賬差異 → 自動降級 paper | NO | V110 不觸既有 reconciler |
| Operator 角色與 live_reserved 缺一即拒 | NO | V110 不觸 operator auth |

### 11.4 §四 5 硬邊界觸碰（0/5）

`execution_state` / `execution_authority` / `live_execution_allowed` / `decision_lease_emitted` / `max_retries=0` 全 0 觸碰。

---

## §12 開放問題 / Caveat

### 12.1 待 PA C9 確認

1. **`_sqlx_migrations` head 真實 = ?**：spec 假設 V109；若 V108/V109 未 apply 需更新 V110 numbering
2. **UUID extension 名稱**：`uuid-ossp` (`uuid_generate_v4()`) vs `pgcrypto` (`gen_random_uuid()`) — IMPL 期 V110.sql 對應函數呼叫
3. **5 λ 命名仲裁**：採 operator prompt 5 dimensions (alpha/sharpe/max_dd/hit_rate/capacity_used) 還是 v5.8 §2 M6 原始 (dd/tail/turnover/slippage/decay)？本 spec 採 operator prompt；若 PM 仲裁切替，§2.1.1 column 名需 patch
4. **engine_mode 'replay' enum 添加**：是否需更新既有 V### CHECK 共用？OpenClaw 既有 4-value (paper/demo/live_demo/live) 在多個 V### 出現；V110 加 'replay' 為 M11 hookup 用 — 是否在 V### 級別統一 5-value 還是 V110 局部 5-value？建議 PM 仲裁：(a) 局部 5-value（本 spec 採；M11 hookup 隔離）/ (b) 全域 5-value（V### 級遷移需求；MIT push back 反對，因 'replay' 僅 M6/M11 需要）

### 12.2 已知 caveat

1. **5 λ column 設計 vs JSONB**：§9 詳論；採 5 column；未來 > 10 λ 可 hybrid（IMPL 期 evaluate）
2. **無 bayesian_opt_runs 第二表**：operator prompt 限 V110 主表 scope；run-level aggregation 由 `reward_weight_history` GROUP BY `weight_set_id` 推導；若 PM 仲裁要求補第二表，本 spec §2.2 後續擴
3. **Optional materialized view**：§2.6 列出但不強制 land；IMPL 期 evaluate query pattern
4. **Sprint 7+ writer 路徑未在本 spec 範圍**：V110 apply 後立即 0 row；MIT pipeline maturity audit 認列為 Foundation stage；Sprint 7+ Advisory 才有 first writer row
5. **30% rollback cap window 7d 是 v5.8 §2 M6 line 243 描述「if next-month Sharpe < baseline」的近似**：實際 PA H-2 mandate 是「7 day window 內累積 reverted change ≥ 30%」；兩者 semantic 差異需 sibling DESIGN spec §6 詳論

### 12.3 替代設計選項

1. **Hypertable**：若未來 row 量超 1M/yr（Y3 scaling），轉 hypertable + 30d chunk + 90d retention；本 spec 不採（避免 premature optimization）
2. **bayesian_opt_runs 第二表**：若 PM 仲裁要求補 run-level audit，本 spec §2.2 後續擴；當前 weight_set_id GROUP BY 推導足
3. **JSONB 5 λ**：§9 詳論為何不採；replaced by 5 column

---

## §13 後續行動（給 PM 派發）

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V110 spec（採 operator prompt 5 λ 命名）or 仲裁切替 v5.8 §2 M6 原始命名 | PM | Sprint 1A-β schema prereq closure | P0 |
| PA C9 跑 §4.1 4 條 ssh PG query + 補 3 處 placeholder | PA | Sprint 1A-β pre-dispatch | P0 |
| IMPL kickoff（Sprint 1A-β 啟動）：派 E1 寫 V110.sql + Linux PG dry-run × 2 + E2/E4 + restart_all 部署 | PM | Sprint 1A-β | P1 |
| Sprint 7+ writer 上線：Bayesian opt job writer + Allocator monthly proposal integration | E1 (Sprint 7+) | Sprint 7+ Advisory | P2 |
| Healthcheck 加 [56-59] for V110 first-row + freshness + rollback_triggered distribution（Sprint 7+ 整合）| E1 (Sprint 7+) | Sprint 7+ | P2 |

### 13.1 Sprint 1A-β schema prereq closure 標誌

本 spec PM sign-off + PA C9 dry-run 補資料 land + 5 λ 命名仲裁完成 → Sprint 1A-β V110 schema prereq 解除 → IMPL kickoff 派 E1。

---

## §14 關鍵文件指針（後續 IMPL agent / PM / E2 / E4 必讀）

- 本 V110 spec：本檔
- sibling M6 DESIGN spec：`srv/docs/execution_plan/2026-05-21--m6_bayesian_reward_weight_design_spec.md`
- v5.8 execution plan：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M6 (line 219-251)
- PA dispatch consolidation：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §Sprint 1A-β + §HIGH H-2
- V103/V104 spec（範式參考）：`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`
- V094 spec（Guard A/B/C + Linux PG dry-run 範式）：`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`
- schema_guard_template：`srv/sql/migrations/templates/schema_guard_template.sql`
- repair binary：`srv/rust/openclaw_engine/src/bin/repair_migration_checksum.rs`
- V055 5-round loop + sqlx hash drift incident lessons：`memory/feedback_v_migration_pg_dry_run.md` + `memory/project_2026_05_02_p0_sqlx_hash_drift.md`
- CLAUDE.md §七 V### migration 規範：`srv/CLAUDE.md`
- MIT 5.21 executability audit Risk 1+2：`srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-21--v58_executability_audit.md`
- ADR-0021 Alpha Surface Bundle：`srv/docs/adr/0021-alpha-source-architecture-upgrade.md`

---

## §15 審計記錄

| Source agent | Role | Audit pattern coverage |
|---|---|---|
| MIT 5.21 executability audit | 起草者 | Risk 1 (V110 placeholder) closure / Risk 2 (M6 bayesian 算法 spec 缺) closure / pipeline maturity 5 階段 / Guard A/B/C / Linux PG dry-run mandate |
| PA Sprint 1A-β dispatch consolidation (2026-05-21) | 範式參考 | HIGH H-2 (GP kernel + acquisition + iter budget + 30% rollback cap) / Sprint 1A-β V107/V112/V113/V106/V110 並行 schedule |
| PA V103/V104 spec (2026-05-21) | 範式參考 | Guard A/B/C 完整 template / Linux PG dry-run × 2 round protocol / sqlx checksum repair SOP / §11 風險評估 + 16 原則 |
| PA Wave 2 Track A2 v094 spec (2026-05-15) | 範式參考 | empirical INSERT test boundary 4 cases / Guard 設計理念 / §12 caveat 列法 |
| db-schema-design-financial-time-series skill | DB schema audit | hypertable vs regular table 判斷 / hot-path index 選用 / engine_mode CHECK 4+1 值 / Guard A/B/C 規範 / partial index 設計 |
| ml-pipeline-maturity-audit skill | Pipeline stage 評級 | V110 apply 後立即 0 row 屬 Foundation stage；Sprint 7+ Advisory writer 接線後升 Skeleton；Sprint 7+ row 累積 + Allocator consumer 接線後升 Shadow；Y2 auto-apply 後升 Canary → Production |
| feature-engineering-protocol skill | Leakage 防範 | reward weight 本質是 retrospective 評估，6 維 leakage 不直接適用；training filter `IN ('live','live_demo')` rule 走 sibling DESIGN spec §8 |
| time-series-cv-protocol skill | CV 設計 | Bayesian opt over 6 mo allocation outcome 屬 retrospective WLS；CV / Purge / Embargo 走 sibling DESIGN spec §9 walk-forward validation |
| data-drift-detection skill | Drift 偵測 | reward function drift 監控走 sibling DESIGN spec §11 + IMPL 期 healthcheck integration |

### 15.1 待 PA dispatch 前補充

- [ ] PA C9 dry-run 4 條 ssh query 結果（§4.1）
- [ ] 5 λ 命名 PM 仲裁結論（§1.3 operator prompt vs v5.8 §2 M6 原始）
- [ ] UUID extension 名稱確認（§12.1 #2）
- [ ] engine_mode 'replay' enum 添加範圍 PM 仲裁（§12.1 #4 局部 vs 全域）

---

**END V110 spec full DDL v1**

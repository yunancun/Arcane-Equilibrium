---
spec: M4 Pattern Miner Stage 1 — Algorithm Spec (W1-C E1 IMPL dispatch packet)
date: 2026-05-25
author: MIT (W1-B Sprint 2 Wave 1)
phase: v5.8 Sprint 2 Stream B Wave 1 W1-B → W1-C dispatch
status: SPEC-LANDED-V1
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M4 line 158-184
  - srv/docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md (M4 module design — 系統面 spec)
  - srv/docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md (6 attribute + leakage 數學細節)
  - srv/docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md §3 Stream B
governance refs:
  - docs/adr/0024-cowork-subscription-operator-assistant.md (Cowork DRAFT-only 邊界)
  - docs/adr/0036-statistical-method-blacklist.md (HMM/Markov/GARCH 禁用 — Sprint 1A-γ 待 land)
  - 16 root principles #1, #3, #6, #7, #8, #10, #11, #12
related skills:
  - srv/.claude/skills/feature-engineering-protocol/SKILL.md (6 leakage 類型)
  - srv/.claude/skills/time-series-cv-protocol/SKILL.md (Purge + Embargo + sample size)
  - srv/.claude/skills/ml-pipeline-maturity-audit/SKILL.md (writer/consumer/row/decision-impact)
related memory:
  - memory/feedback_indicator_lookahead_bias.md (2026-04-24 P1-11 F3 RETRACT — rolling shift(1) 強制)
  - memory/feedback_v_migration_pg_dry_run.md (V### Linux PG empirical mandate)
  - memory/feedback_working_principles.md (對抗式驗證 + 誠實報告)
scope: Algorithm-level IMPL dispatch packet — W1-C E1 IMPL 接此即可 code;
       本 spec 不寫 Rust/Python code (那是 W1-C scope), 但寫死所有算法 invariant
       (公式 / boundary / shift(1) / Bonferroni K / event-window 邊界 / sample
       size gate / DRAFT writeback schema mapping)。
hardware refs:
  - rust 模組目標位置: rust/openclaw_core/src/m4_miner/ (新 sub-module)
  - python 模組目標位置: helper_scripts/m4/pattern_miner_stage_1.py + helper_scripts/m4/sources/*.py
  - PG schema: V100 learning.hypotheses base + V103 EXTEND 6 column (已 land)
  - 不依賴: LinUCB / scorer / quantile / mlde (M4 是 statistical miner 不是 ML retrain)
---

# M4 Pattern Miner Stage 1 — Algorithm Spec (W1-C E1 IMPL Dispatch Packet)

## §0 TL;DR

本 spec 是 W1-C E1 IMPL 的 **algorithm-level dispatch packet**。M4 Pattern Miner Stage 1 = 自監督統計 hypothesis discovery 模組,from raw market/trade data 挖掘 alpha candidate pattern,寫 DRAFT 進 `learning.hypotheses`。

**核心 algorithm**:
1. **Source ingestion** — 4 個 PG table + 1 個 external feed (kline / fills / liquidations / funding / token unlocks)
2. **Statistical pattern detection** — leak-free rolling cross-correlation `feature × forward_return`,Bonferroni-corrected K=500
3. **Event-window analysis** — unlock/FOMC/liquidation cascade/large funding flip 周邊 ±window 觀測 forward return shift,N≥30 硬 gate
4. **6 attribute enforcement** — N / Bonferroni p / Cohen's d / sub-period stability / graveyard / cluster silhouette (Stage 1 不啟 cluster,skip)
5. **DRAFT writeback** — V103 EXTEND 6 column 完整填 + Decision Lease audit (lease_type='M4_DRAFT_WRITEBACK')

**5 條 hard invariant** (E2 cold review 100% verify):
- I-1: 所有 rolling stat **必** `.shift(1)` (per memory `feedback_indicator_lookahead_bias`)
- I-2: 黑名單 method 禁用 — **不允許** HMM / Markov-switching / GARCH (per ADR-0036)
- I-3: K=500 hypothesis × 5 forward window = K_total=2,500;α_corrected = 0.05/2500 = 2e-5
- I-4: Event-window N ≥ 30 硬 gate;不足 → `status='exploratory'` + event-rate constrained flag
- I-5: DRAFT writeback **不** trigger live order (per 16 原則 #7 學習 ≠ live);**不** auto-promote past `'preregistered'`

**Implementation amendment 2026-05-31 (source branch `feature/m4-stage1-production-draft-runner`)**:
- `helper_scripts/m4/pattern_miner_stage_1.py --no-dry-run` now supports the 4-PG-source production read/compute path; token unlocks remain a Sprint 3+ fail-loud stub.
- DRAFT writeback remains fail-closed unless the caller explicitly passes `--enable-writeback` and one real `decision_lease_draft_id` UUID per row. The old `GovernanceHubInterface` random-UUID stub is not accepted for production writes.
- V100 `learning.hypotheses.status` does **not** include `exploratory`; current executable contract treats `exploratory` as an analysis lane and maps it to PG status `draft`. Only `draft` / `preregistered` may be passed into `draft_writer.build_writeback_payload`.
- Any pseudo-SQL below that references `m4_attribute_*` columns or direct `status='exploratory'` is superseded by the empirical V100+V103 writer contract in `helper_scripts/m4/draft_writer.py` and `helper_scripts/m4/stage1_production_runner.py`.

**Out of scope** (本 spec 不寫):
- Stage 2 cross-sectional clustering (Sprint 8)
- M9 A/B integration (Sprint 6-7)
- M11 dedup logic (M11 寫 `replay_divergence_alert` 不寫 `hypotheses`)
- Cowork Y2 hybrid auto-suggest (per ADR-0024-lite Y2)
- ADR-0036 本檔起草 (PA Sprint 1A-γ dispatch)

---

## §1 Source Ingestion (5 sources)

### §1.1 Source-1: `market.klines` (1m/5m/15m/1h/4h)

**Read pattern**:
```sql
SELECT symbol, timeframe, ts, open, high, low, close, volume, turnover
FROM market.klines
WHERE symbol = ANY($1::TEXT[])              -- 25 symbol universe
  AND timeframe = ANY($2::TEXT[])           -- 1m/5m/15m/1h/4h
  AND ts >= now() - INTERVAL '90 days'      -- 90d window
  AND ts < (
      SELECT MAX(ts) - INTERVAL '1 minute'  -- 不取尚未 close 的 current bar
      FROM market.klines
      WHERE symbol = ANY($1::TEXT[]) AND timeframe = ANY($2::TEXT[])
  )
ORDER BY symbol, timeframe, ts;
```

**Invariant**:
- 跨 timeframe 必統一 UTC timestamp
- 不允許用 partial bar (last bar `ts == now()` 必排除)
- 1m bar window = 90d × 25 symbol × 1440 min = ~3.24M row;5m = ~648k;15m=216k;1h=54k;4h=13.5k;total ~4.07M row per batch

**Failure mode**:
- 若 kline freshness < N hours = SOURCE_STALE alert,Stage 1 skip 該 batch (per Operator notification)
- N=24h 默認;configurable per `helper_scripts/m4/config.toml`

### §1.2 Source-2: `trading.fills` (engine_mode IN ('live','live_demo'))

**Read pattern**:
```sql
SELECT 
    symbol, strategy_name, ts, side, size, price, 
    fee_rate, realized_net_bps, 
    entry_context_id, close_reason_code
FROM trading.fills
WHERE engine_mode IN ('live', 'live_demo')   -- per memory `project_engine_mode_tag_live_demo` 
  AND ts >= now() - INTERVAL '90 days'
  AND close_fill = TRUE                       -- 只取 close 用以對應 forward return
ORDER BY symbol, strategy_name, ts;
```

**Invariant**:
- **必含** `live_demo` (per memory `project_engine_mode_tag_live_demo` 教訓 — 歷史 43k 'live' 實為 LiveDemo)
- **禁用** `engine_mode = 'paper'` (per CLAUDE.md §四 Hard Boundaries — paper 不是 promotion evidence lane)
- 25 symbol × 5 strategy × ~ 100 fill/day(avg) × 90d ~ 65k row per batch (估計)

### §1.3 Source-3: `market.liquidations` (V095 land 2026-05-17)

**Read pattern**:
```sql
SELECT 
    symbol, ts, side, size, price, 
    aggregator_type   -- per V095 design (cascade detection)
FROM market.liquidations
WHERE ts >= now() - INTERVAL '90 days'
  AND aggregator_type IN ('top_liq_30s', 'cascade_5min')  -- aggregator 形式 (per V095)
ORDER BY symbol, ts;
```

**Invariant**:
- **必剔除 self-fill 引發的 liquidation cascade noise** — 不允許自家 fill 引起的 cascade 被當外部 alpha source
- 剔除路徑: `LEFT JOIN trading.fills f ON f.symbol = liq.symbol AND f.ts BETWEEN (liq.ts - INTERVAL '5 seconds') AND liq.ts WHERE f.fill_id IS NULL` 過濾
- Sprint 2 IMPL 接受 5s 視窗;Sprint 3 可放寬到 30s

### §1.4 Source-4: `market.funding_rates`

**Read pattern**:
```sql
SELECT 
    symbol, ts, funding_rate, 
    funding_rate * 3 * 365 AS annualized_funding   -- Bybit 每 8h settlement = 3 次/天
FROM market.funding_rates
WHERE ts >= now() - INTERVAL '90 days'
ORDER BY symbol, ts;
```

**Invariant**:
- Bybit funding settlement 整點 UTC 是 0/8/16 (3 次/天)
- **Funding flip event** 定義: `sign(funding_rate_t) != sign(funding_rate_t-1)` 且 `|funding_rate_t| > 0.01%` (Stage 1 baseline,configurable)
- 25 symbol × 3 settlement/day × 90d ~ 6,750 row per batch

### §1.5 Source-5: Token Unlocks (External Feed)

**Read pattern**: NOT in PG. External feed = Tokenomist.io / DropsTab / CoinMarketCap unlock calendar.

**Sprint 2 IMPL boundary**:
- **Stage 1 Sprint 2** = **NOT IMPL** (per Sprint 2 dispatch packet §3.2 AC-S2-B-1: "4 input source...token unlock 留 Sprint 3+")
- Stub interface 寫在 `helper_scripts/m4/sources/token_unlocks_stub.py` (raise NotImplementedError + return empty df)
- Sprint 3+: 接 Tokenomist API + landed cache table (V### Sprint 3)

**Sprint 2 IMPL 范围**: 4 PG source (kline + fills + liquidations + funding) — token unlock = Sprint 3 follow-up

### §1.6 Ingestion contract summary

| Source | Table / Feed | Sprint 2 IMPL | engine_mode filter | Freshness gate |
|---|---|---|---|---|
| 1 | market.klines | ✅ | n/a | 24h stale alert |
| 2 | trading.fills | ✅ | `IN ('live','live_demo')` | 6h stale alert |
| 3 | market.liquidations | ✅ | n/a (self-fill filter required) | 1h stale alert |
| 4 | market.funding_rates | ✅ | n/a | 12h stale alert |
| 5 | token unlocks (Tokenomist) | ❌ Sprint 3+ | n/a | Sprint 3+ |

---

## §2 Pattern Detection Algorithm

### §2.1 Algorithm-A: Statistical Cross-Correlation (per v5.8 §2 M4 line 161)

#### §2.1.1 Mathematical definition

對每 `(strategy, symbol, timeframe, feature_name)` 組合,計算 leak-free rolling correlation between feature × forward return:

```
ρ(τ, w) = corr( feature_{t} , forward_return_{t,t+τ} )

where:
  - feature_t  = shift(1) leak-free feature value
  - forward_return_{t,t+τ}  = (close_{t+τ} - close_t) / close_t * 10000  (bps)
  - w  = rolling window length (configurable, baseline 1000 bars 不是 60)
  - τ  ∈ {1, 5, 15, 60, 240} minutes  (5 forward windows;對應 forward 1m/5m/15m/1h/4h)
```

#### §2.1.2 Leak-free 強制 (I-1)

**SQL pattern (per leakage spec §3.2)**:
```sql
-- ✅ CORRECT (leak-free shift(1))
WITH leak_free_feature AS (
    SELECT 
        symbol, timeframe, ts,
        AVG(close) OVER (
            PARTITION BY symbol, timeframe
            ORDER BY ts
            ROWS BETWEEN 19 PRECEDING AND 1 PRECEDING   -- 20-bar SMA, 含 current 排除
        ) AS feature_value
    FROM market.klines
)
SELECT * FROM leak_free_feature;

-- ❌ ANTI-PATTERN (leak)
SELECT 
    AVG(close) OVER (ROWS BETWEEN 19 PRECEDING AND CURRENT ROW)
FROM market.klines;  -- current bar 含入 = look-ahead bias
```

**Pandas pattern**:
```python
# ✅ CORRECT
df['feature_value'] = df['close'].shift(1).rolling(20).mean()

# ❌ ANTI-PATTERN
df['feature_value'] = df['close'].rolling(20).mean()  # 含 current bar
```

**Rust polars pattern**:
```rust
// ✅ CORRECT
df.lazy()
    .with_column(
        col("close")
            .shift(lit(1))
            .rolling_mean(RollingOptions {
                window_size: Duration::parse("20i"),
                ..Default::default()
            })
            .alias("feature_value")
    )
    .collect()?;

// ❌ ANTI-PATTERN
df.lazy()
    .with_column(col("close").rolling_mean(...)) // 缺 shift(lit(1))
```

#### §2.1.3 Feature universe (Sprint 2 baseline)

| Feature 類別 | 公式 (leak-free) | window |
|---|---|---|
| **SMA ratio** | `close.shift(1) / close.shift(1).rolling(N).mean()` | N ∈ {20, 60, 240} |
| **EMA ratio** | `close.shift(1) / close.shift(1).ewm(span=N).mean()` | N ∈ {20, 60, 240} |
| **Volume z-score** | `(volume.shift(1) - volume.shift(1).rolling(N).mean()) / volume.shift(1).rolling(N).std()` | N ∈ {20, 60} |
| **Realized vol** | `close.shift(1).pct_change().rolling(N).std() * sqrt(N)` | N ∈ {20, 60, 240} |
| **OBV change** | OBV.shift(1) - OBV.shift(N+1) | N ∈ {20, 60} |
| **Funding state** | `funding_rate.shift(1)` (從 market.funding_rates 取) | n/a (event-based) |
| **Liquidation 30s rate** | `liquidation_count.rolling(30s).sum().shift(1)` (per market.liquidations) | 30s/5min |
| **Cross-asset** | `BTC_close.shift(1).pct_change() - ETH_close.shift(1).pct_change()` | n/a |

**Total feature count**: ~25 個 baseline feature × 25 symbol × 5 timeframe = ~3,125 feature variants per batch

#### §2.1.4 Bonferroni K calculation (I-3)

- per-hypothesis sub-test 數: 5 forward windows (1m/5m/15m/1h/4h)
- 同 batch 並行 hypothesis 數: K_hyp ≈ 500 (PA Sprint 2 baseline,per leakage spec §2.2.2;不是 3,125 feature count — 因為大部分 feature 會被 effect_size < 0.2 filter 掉,實際 promote 到 statistical test 的是 ~500)
- **K_total = K_hyp × 5 = 2,500**
- **α_corrected = 0.05 / 2,500 = 2e-5**

**Anti-pattern grep (E2 cold review 必跑)**:
```bash
grep -rnE 'p_value\s*<\s*0\.0[15]\b' \
    --include='*.py' --include='*.rs' --include='*.sql' \
    helper_scripts/m4/ rust/openclaw_core/src/m4_miner/
# 任何 hit 無 inline `# Bonferroni K=2500` 註解 → REJECT IMPL
```

### §2.2 Algorithm-B: Event-Window Analysis (per v5.8 §2 M4 line 163)

#### §2.2.1 Event types (Sprint 2 baseline)

| Event type | Source | Window pre/post | Sprint 2 IMPL |
|---|---|---|---|
| **Funding flip** | market.funding_rates `sign change + |rate| > 0.01%` | ±4h | ✅ |
| **Liquidation cascade** | market.liquidations `aggregator_type='cascade_5min' AND cascade_size > 5M USD` | ±30min | ✅ |
| **Large funding spike** | market.funding_rates `|rate| > 0.1%` | ±4h | ✅ |
| **FOMC announcement** | external calendar | ±4h | ❌ Sprint 3+ (需 calendar feed) |
| **Token unlock** | Tokenomist API | ±4h | ❌ Sprint 3+ |

#### §2.2.2 Event-window forward return analysis

對每 event_t,計算:
```
window_pre   = forward_return[t - pre_window .. t - 1m]    # 排除 t 本身 (leak-free)
window_post  = forward_return[t + 1m .. t + post_window]   # 排除 t 本身

effect       = mean(window_post) - mean(window_pre)
n_events     = COUNT(distinct event_t)
```

#### §2.2.3 Sample size hard gate (I-4)

```python
def event_window_gate(n_events: int, event_type: str) -> str:
    """
    Event-window analysis sample size gate (per CR-6 + leakage spec §2.1).
    Returns: 'preregistered_candidate' / 'exploratory' / 'reject'
    
    為什麼 30: Mann-Whitney U power > 0.5 at d=0.5 medium effect
    """
    if n_events < 30:
        # Event-based hypothesis N < 30 → 'exploratory' + flag
        return ('exploratory', 'event_rate_constrained')
    return ('preregistered_candidate', None)
```

**Edge case**: FOMC 每年 8 次,4 年才 32 次。Sprint 2 不啟 FOMC,Sprint 3+ 接時必標 `'exploratory'`。

#### §2.2.4 Event window 邊界 invariant

- **pre window 必排除 event_t 本身** (避免 event 引入 leak)
- **post window 必從 event_t + 1m 起** (event 本身的 bar 屬 transition zone,不算 post)
- **同 symbol 連續 event 在 < 2 × max(pre,post) 內** → 合併為 single event 避免雙重計算

### §2.3 Blacklist (I-2)

per ADR-0036 (Sprint 1A-γ 待 land) + memory `feedback_v_migration_pg_dry_run`:

**禁用 methods**:
- HMM (Hidden Markov Model) — Sprint 1A-γ ADR-0036 black list
- Markov-switching regression — 同 ADR
- GARCH (Generalized Autoregressive Conditional Heteroskedasticity) — 同 ADR

**允許的 methods** (Sprint 2 baseline):
- Pearson / Spearman / Kendall rank correlation
- Mann-Whitney U two-sample test
- Bonferroni correction (per leakage spec §2.2)
- Welch's t-test (unequal variance)
- Bootstrap percentile / BCa CI (N ≥ 30 場景)
- ATR-vol regime + funding state 雙 axis (per CR-5 推薦替代 method)

**Anti-pattern grep**:
```bash
grep -rnE 'HMM|hmmlearn|GaussianHMM|markov_switching|arch_model|GARCH' \
    --include='*.py' --include='*.rs' \
    helper_scripts/m4/ rust/openclaw_core/src/m4_miner/
# 任何 hit → REJECT IMPL + RCA log
```

---

## §3 6 Attribute Enforcement (Stage 3 Pre-Writeback Gate)

直引 `2026-05-21--m4_minimum_bar_and_leakage_protocol.md` §2 數學定義,本節寫 IMPL flow:

### §3.1 Attribute calculation table

| Attribute | Calc function (Python) | V103 EXTEND column | Pass condition |
|---|---|---|---|
| **N (n_observations)** | `len(observations)` | `m4_attribute_n INTEGER` (per base V100 schema) | ≥ 30 |
| **Bonferroni p** | `raw_p_value` (用 K=2500 比較 in DB-side derived) | `bonferroni_corrected_p NUMERIC(10,8)` | < 2e-5 (0.05/2500) |
| **Cohen's d** | `(mean_t - mean_c) / pooled_std` | `m4_attribute_effect_size NUMERIC` (per base V100) | abs ≥ 0.2 AND abs < 3.0 |
| **Sub-period stability** | 前後 50/50 split + Mann-Whitney U | `m4_attribute_subperiod_pass BOOLEAN` | TRUE |
| **Graveyard flag** | Harvey-Liu-Zhu fuzzy match | `m4_attribute_graveyard_flag BOOLEAN` | 不阻 (warning only) |
| **Cluster silhouette** | n/a Sprint 2 (skip) | `m4_attribute_silhouette NUMERIC` NULL + `spec_no_clustering=true` | skip;Stage 2 才啟 |

### §3.2 Overall pass criterion (per design spec §3.2)

```python
def hypothesis_status(attrs: dict) -> str:
    """
    Return: 'preregistered' / 'exploratory'
    Note: 'draft' base state is set on INSERT;這裡決定後續 transition target.
    """
    pass_all = (
        attrs['n'] >= 30
        and attrs['bonferroni_p'] < (0.05 / 2500)
        and 0.2 <= abs(attrs['cohens_d']) < 3.0
        and attrs['subperiod_pass'] is True
        and (attrs['silhouette'] is None or attrs['silhouette'] >= 0.5)
        # graveyard_flag 不參與 pass criterion (warning only)
    )
    if pass_all:
        return 'preregistered'
    return 'exploratory'
```

**Promote past `preregistered` 必經 operator manual Console click** (per AMD-2026-05-21-01 protected scope (a))。

### §3.3 Leakage scan automatic verification SQL (per design spec §4.3)

每個 DRAFT 寫入前 Stage 3 跑:
```sql
-- Stage 3 leakage scan: shift(1) leak-free vs 含 current bar 並列驗
WITH leak_audit AS (
    SELECT
        h.hypothesis_id,
        h.m4_attribute_effect_size AS clean_effect,
        la.effect_value_with_current_bar AS leak_effect,
        ABS(la.effect_value_with_current_bar - h.m4_attribute_effect_size) AS effect_diff
    FROM learning.hypotheses h
    JOIN learning.hypothesis_observation_leak_audit la USING (hypothesis_id)
    WHERE h.hypothesis_source_module = 'M4_AUTO'
      AND h.status = 'draft'
)
SELECT
    hypothesis_id,
    effect_diff,
    effect_diff > 0.1 AS leak_suspected,
    CASE WHEN effect_diff > 0.1 THEN 'REJECT_LEAK_SUSPECTED'
         ELSE 'PASS' END AS leakage_scan_action
FROM leak_audit;
```

`leak_suspected=TRUE` → DRAFT INSERT 拒絕 + RCA log + Slack alert (per design spec §4.3)

---

## §4 DRAFT Writeback Schema (V103 EXTEND 完整 6 attribute)

### §4.1 INSERT contract

```sql
BEGIN;
  -- 1. Acquire Decision Lease (audit traceability,per design spec §2.5)
  SELECT GovernanceHub.acquire_lease(
    lease_type := 'M4_DRAFT_WRITEBACK',
    actor := 'm4_pattern_miner',
    expires_at := now() + INTERVAL '5 minutes',
    live_order_intent := FALSE
  ) INTO v_lease_id;

  -- 2. INSERT hypothesis DRAFT (V100 base + V103 EXTEND 6 column)
  INSERT INTO learning.hypotheses (
    -- V100 base fields
    hypothesis_id, strategy_name, status, 
    m4_attribute_n, m4_attribute_p_bonferroni,           -- 注: m4_attribute_p_bonferroni = raw_p (用 K=2500 derived in DB)
    m4_attribute_effect_size, 
    m4_attribute_subperiod_pass, m4_attribute_graveyard_flag, m4_attribute_silhouette,
    -- V103 EXTEND fields
    hypothesis_source_module, leakage_scan_pass, bonferroni_corrected_p,
    replicability_score, decision_lease_draft_id, cowork_review_status,
    created_at
  ) VALUES (
    gen_random_uuid(), $strategy_name, $status,           -- $status = 'preregistered' or 'exploratory' (per §3.2)
    $n_observations, $raw_p_value,
    $cohens_d, 
    $subperiod_pass, $graveyard_flag, NULL,               -- silhouette Sprint 2 skip
    'M4_AUTO', $leakage_scan_pass, $raw_p_value,          -- bonferroni_corrected_p = raw_p (Bonferroni 比較在 application 端 with K=2500)
    $replicability_score, v_lease_id, 'NONE',
    now()
  );

  -- 3. Release lease
  SELECT GovernanceHub.release_lease(v_lease_id, outcome := 'SUCCESS');
COMMIT;
```

### §4.2 V103 EXTEND 6 column mapping verification (per V103__extend_m4_hypothesis_columns.sql land)

| V103 column | Type | Default | Stage 1 IMPL value | E1 IMPL action |
|---|---|---|---|---|
| `hypothesis_source_module` | TEXT | `'M4_AUTO'`* | `'M4_AUTO'` | INSERT 必顯式設 'M4_AUTO' (不依 DEFAULT) |
| `leakage_scan_pass` | BOOLEAN | `FALSE` (fail-closed) | TRUE 或 FALSE | INSERT 必顯式設 (per §3.3 結果) |
| `bonferroni_corrected_p` | NUMERIC(10,8) | NULL | raw p-value | 寫 raw_p;app-level 用 K=2500 比較 |
| `replicability_score` | NUMERIC(5,4) | NULL | 0.0-1.0 | per §4.3 計算 |
| `decision_lease_draft_id` | UUID | NULL | lease UUID | 必 backref Lease ID |
| `cowork_review_status` | TEXT | `'NONE'` | `'NONE'` | Y1 全部 'NONE' |

*Note: V103 spec §10.2 + V103 SQL DEFAULT 為 'M4_AUTO' (per file line 643-644 ADD COLUMN ... DEFAULT 'M4_AUTO');但既有 V100 row backfill 為 'OPERATOR' (per spec §10.4)。Stage 1 新寫 row 顯式設 'M4_AUTO'。

### §4.3 `replicability_score` formula (Sprint 2 baseline)

per design spec §10.2 column note "cross sub-period stability + cross-asset / cross-timeframe robustness score":

```python
def replicability_score(
    subperiod_pass: bool,
    cross_asset_subperiod_pass_count: int,  # 在 25 symbol 中,有多少 pass subperiod
    cross_timeframe_subperiod_pass_count: int,  # 在 5 timeframe 中,有多少 pass subperiod
) -> float:
    """
    Return 0.0-1.0 replicability score.
    Sprint 2 baseline formula (subject to QC review):
        0.3 * (1 if subperiod_pass else 0)
        + 0.4 * (cross_asset_subperiod_pass_count / 25)
        + 0.3 * (cross_timeframe_subperiod_pass_count / 5)
    """
    s = 0.0
    s += 0.3 * (1.0 if subperiod_pass else 0.0)
    s += 0.4 * (cross_asset_subperiod_pass_count / 25.0)
    s += 0.3 * (cross_timeframe_subperiod_pass_count / 5.0)
    return min(max(s, 0.0), 1.0)
```

**QC review pending**: formula coefficients 0.3/0.4/0.3 是 baseline;QC 可 push back 仲裁。

---

## §5 Implementation Language Split (Rust + Python Hybrid)

### §5.1 Rust scope (rust/openclaw_core/src/m4_miner/)

**hot-path responsibilities**:
- Tick/bar window aggregator: 1M+ row scan per batch → polars lazy execution
- Rolling stat computation: `rolling_mean / rolling_std / rolling_corr` (per polars API)
- Cross-correlation matrix: 25 symbol × 5 timeframe parallel pearson via rayon
- Event-window alignment: liquidation / funding flip event detection from streaming source

**Sprint 2 IMPL files** (建議):
```
rust/openclaw_core/src/m4_miner/
├── mod.rs                          // pub mod statistical; pub mod event_window;
├── statistical/
│   ├── mod.rs
│   ├── feature_calc.rs            // 25 feature with shift(1) leak-free
│   ├── rolling_corr.rs            // polars rolling correlation
│   └── effect_size.rs             // Cohen's d, partial d
├── event_window/
│   ├── mod.rs
│   ├── funding_flip.rs            // funding rate sign change detector
│   ├── liquidation_cascade.rs    // cascade aggregation 5min window
│   └── window_alignment.rs       // pre/post window forward return
├── leakage_scan.rs                 // shift(1) audit + clean vs leak effect diff
└── ingestion.rs                    // sqlx query 4 source
```

**Rust crate dependencies** (per Cargo.toml):
- `polars = "0.36"` (lazy execution + rolling stat)
- `sqlx = "0.7"` (PG query;readonly only)
- `rayon = "1.8"` (parallel cross-correlation)
- `statrs = "0.16"` (Mann-Whitney U, Cohen's d)

**Rust 範圍邊界**:
- ✅ ingestion + statistical computation + leakage audit
- ❌ 不寫 PG INSERT (DRAFT writeback 在 Python 端,per §5.2)
- ❌ 不寫 Decision Lease acquire/release (走 PyO3 binding 由 Python 呼)

### §5.2 Python scope (helper_scripts/m4/)

**responsibilities**:
- Orchestrator: Rust binding 呼 + statistical 補強 (scipy/statsmodels) + DRAFT writeback
- 6 attribute enforcement gate
- Decision Lease acquire/release (透過 governance hub HTTP/IPC)
- Slack/Email/Console notification (per design spec §2.5.4)
- Cron schedule (daily UTC 00:00 per design spec Open Q2)

**Sprint 2 IMPL files** (建議):
```
helper_scripts/m4/
├── pattern_miner_stage_1.py        # 主 entry (cron 呼)
├── sources/
│   ├── kline_loader.py             # market.klines
│   ├── fills_loader.py             # trading.fills (engine_mode filter)
│   ├── liquidations_loader.py     # market.liquidations + self-fill filter
│   ├── funding_loader.py           # market.funding_rates
│   └── token_unlocks_stub.py      # Sprint 3+ stub (raise NotImplementedError)
├── algorithms/
│   ├── statistical_via_rust.py    # PyO3 binding 呼 Rust statistical/
│   ├── event_window.py             # Python 補強 event-window 邊界邏輯
│   ├── effect_size.py              # Cohen's d / partial d
│   └── bonferroni.py               # K=2500 correction
├── attribute_enforcer.py           # 6 attribute gate (per §3)
├── leakage_scan.py                 # shift(1) audit (per design spec §4.3)
├── draft_writeback.py              # Decision Lease + INSERT learning.hypotheses
├── notification.py                 # Slack/Email/Console
└── config.toml                     # 配置 (freshness gate / K / window size)
```

**Python dependencies**:
- `pandas = "2.1"`
- `scipy = "1.11"` (Mann-Whitney U, ttest)
- `numpy = "1.26"`
- `psycopg2-binary = "2.9"` (PG)
- `pyo3` Rust binding for high-volume stat

**Python 範圍邊界**:
- ✅ orchestration / DRAFT writeback / notification / 6 attribute gate
- ❌ 不直接寫 rolling stat (走 Rust binding)
- ❌ 不允許 `engine_mode='paper'` filter (per CLAUDE.md §四)

### §5.3 Cross-language fixture (per design spec §4.4)

Sprint 2 IMPL 必含 `srv/tests/test_m4_cross_language_fixture.py`:
- Fixture input: 固定 OHLCV parquet
- 三套對齊 (Rust polars / Python pandas / PG window function) max diff < 1e-4
- 若某 implementation < 1e-4 不符 → 該 implementation 不允許用於 DRAFT writeback (per design spec Open Q5)
- **Sprint 2 baseline**: Python pandas 為 source of truth;Rust 為 performance path,1e-4 對齊驗


---

## §6 5 Acceptance Criteria (per Sprint 2 dispatch packet §3.2)

### AC-S2-B-1: 5 source ingestion 全接通 (Sprint 2 內接 4,token unlock Sprint 3+)

**驗證 SQL**:
```sql
-- 確認 4 source 在最近 24h 有 row freshness
SELECT 'klines' AS source, MAX(ts) AS latest, COUNT(*) AS row_24h
FROM market.klines WHERE ts > now() - INTERVAL '24h'
UNION ALL
SELECT 'fills', MAX(ts), COUNT(*) FROM trading.fills 
  WHERE ts > now() - INTERVAL '24h' AND engine_mode IN ('live','live_demo')
UNION ALL
SELECT 'liquidations', MAX(ts), COUNT(*) FROM market.liquidations WHERE ts > now() - INTERVAL '24h'
UNION ALL
SELECT 'funding_rates', MAX(ts), COUNT(*) FROM market.funding_rates WHERE ts > now() - INTERVAL '24h';
```
- Pass: 4 row all `latest > now() - freshness_gate` per §1.6
- Sprint 2 IMPL DONE 標準: 4 row return + Python loader 全 import 不 raise

### AC-S2-B-2: Cross-correlation + event-window 5 sub-algorithm IMPL DONE

**5 sub-algorithm** (per §2):
1. Statistical: rolling Pearson cross-correlation (per §2.1)
2. Statistical: Spearman rank correlation (per §2.1)
3. Event-window: funding flip (per §2.2.1)
4. Event-window: liquidation cascade (per §2.2.1)
5. Event-window: large funding spike (per §2.2.1)

**驗證**: 
- 每個 sub-algorithm 在 `helper_scripts/m4/algorithms/` 有 `__name__ == '__main__'` smoke test
- `python3 -m helper_scripts.m4.pattern_miner_stage_1 --dry-run` 全程跑 + 不寫 PG
- E2 cold review verify: 5 sub-algorithm 都實作 + leakage scan pass

### AC-S2-B-3: Leak-free regression test (shift(1) vs 含 current bar 並列驗)

**Test file**: `srv/tests/test_m4_leakage_regression.py`

**Test logic**:
```python
def test_rolling_corr_shift1_vs_leak():
    """
    驗證 leak-free shift(1) vs 含 current bar 算 cross-correlation 差距。
    Fixture: 已知 mean-revert 純 noise series.
    - leak version: correlation 應顯著 (artifact)
    - shift(1) version: correlation ≈ 0 (true signal)
    """
    fixture = load_known_meanrevert_noise_series(n=10000)
    leak_corr = rolling_corr_with_current_bar(fixture)
    clean_corr = rolling_corr_shift1(fixture)
    
    # leak 應 spurious significant
    assert abs(leak_corr) > 0.3, "Leak version should show artifact correlation"
    # clean 應接近 0
    assert abs(clean_corr) < 0.05, "Shift(1) version should be ~ 0"
```

**驗證**: E4 regression 跑 pytest pass + memory `feedback_indicator_lookahead_bias` 引述 P1-11 F3 RETRACT 教訓在 test docstring

### AC-S2-B-4: 30 events min sample 硬 gate (per CR-6)

**驗證 SQL**:
```sql
-- 任何 event-based hypothesis_source_module='M4_AUTO' 且 n_observations < 30 必為 'exploratory'
SELECT 
    hypothesis_id, status, m4_attribute_n,
    CASE WHEN m4_attribute_n < 30 AND status != 'exploratory' THEN 'FAIL'
         ELSE 'PASS' END AS gate_check
FROM learning.hypotheses
WHERE hypothesis_source_module = 'M4_AUTO'
ORDER BY created_at DESC;
```

**Pass**: 0 row 為 'FAIL'

### AC-S2-B-5: V103 EXTEND DRAFT writeback 完整 6 attribute

**驗證 SQL** (per design spec AC-3):
```sql
-- 100% M4 DRAFT 必填 6 attribute 字段
SELECT 
    COUNT(*) AS total_m4_draft,
    COUNT(*) FILTER (WHERE hypothesis_source_module IS NULL) AS missing_source,
    COUNT(*) FILTER (WHERE leakage_scan_pass IS NULL) AS missing_leakage,
    COUNT(*) FILTER (WHERE m4_attribute_n IS NULL) AS missing_n,
    COUNT(*) FILTER (WHERE bonferroni_corrected_p IS NULL) AS missing_bonf,
    COUNT(*) FILTER (WHERE m4_attribute_effect_size IS NULL) AS missing_d,
    COUNT(*) FILTER (WHERE m4_attribute_subperiod_pass IS NULL) AS missing_subperiod,
    COUNT(*) FILTER (WHERE decision_lease_draft_id IS NULL) AS missing_lease
FROM learning.hypotheses
WHERE hypothesis_source_module = 'M4_AUTO'
  AND created_at > now() - INTERVAL '24h';
```

**Pass**: 所有 missing_* 列為 0

---

## §7 PG Schema Empirical Verify (per memory `feedback_v_migration_pg_dry_run`)

W1-C E1 IMPL 前必跑 (W1-C 開工 prerequisite):

```bash
ssh trade-core "docker exec trading_postgres psql -U postgres -d trade -c \"
  -- V100 base table 存在性
  SELECT 'V100 base' AS check, EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_schema='learning' AND table_name='hypotheses'
  ) AS pass;

  -- V103 EXTEND 6 column 存在性
  SELECT column_name, data_type, column_default, is_nullable
  FROM information_schema.columns
  WHERE table_schema='learning' AND table_name='hypotheses'
    AND column_name IN ('hypothesis_source_module', 'leakage_scan_pass', 
                        'bonferroni_corrected_p', 'replicability_score',
                        'decision_lease_draft_id', 'cowork_review_status')
  ORDER BY column_name;

  -- 3 V103 EXTEND index 存在性
  SELECT indexname FROM pg_indexes
  WHERE schemaname='learning' AND tablename='hypotheses'
    AND indexname LIKE 'idx_hypotheses_%';

  -- 4 source table freshness
  SELECT 'klines' AS source, MAX(ts) FROM market.klines
  UNION ALL SELECT 'fills', MAX(ts) FROM trading.fills WHERE engine_mode IN ('live','live_demo')
  UNION ALL SELECT 'liquidations', MAX(ts) FROM market.liquidations
  UNION ALL SELECT 'funding_rates', MAX(ts) FROM market.funding_rates;
\""
```

**Expected output**:
- V100 base pass = TRUE
- 6 row of V103 EXTEND column (all expected type/default)
- 3 row of `idx_hypotheses_*` index
- 4 row freshness (all latest within freshness gate per §1.6)

任何 row 缺 → W1-C IMPL block (E1 必呼 W1-B 補 spec gap)

---

## §8 ML Pipeline Maturity Audit Rating (per ml-pipeline-maturity-audit skill)

| Component | Writer spawn? | Consumer exists? | Row 累積? | Decision impact? | Stage | Blocker |
|---|---|---|---|---|---|---|
| **m4_pattern_miner_stage_1** (本 spec) | ❌ Sprint 2 待 IMPL | ❌ N/A (DRAFT 不直接 consume) | 0 (Stage 1 還沒 fire) | ❌ DRAFT 不影響 live (per 16 #7) | **Foundation** (V100+V103 land,writer pending) | W1-C E1 IMPL |
| **learning.hypotheses** (V100 base + V103 EXTEND) | ✅ M4 writer Sprint 2 / Cowork operator manual | ❌ Y1 read-only review (per §design spec §9.3) | 0-15 (existing OPERATOR backfill) | ❌ DRAFT 不影響 live | **Foundation** | W1-C IMPL |
| **Decision Lease** for `M4_DRAFT_WRITEBACK` | ✅ GovernanceHub 已存在 | ✅ audit log writer 已存在 | per existing lease infra | ❌ DRAFT-only lease 不 trigger live | **Production** (infra side) | n/a |

**整體 stage**: **Foundation** (待 W1-C IMPL push 到 Skeleton — writer code 寫完但 default 不開 cron)

**升 Skeleton 條件** (Sprint 2 末): W1-C IMPL DONE + dry-run pass + cron 寫好但 disabled
**升 Shadow 條件** (Sprint 3): cron daily 啟動 + DRAFT row 開始累積但 promote 邏輯仍待 operator review

---

## §9 對抗式 review 5 重點 (W2-E E2 + W2-F MIT post-IMPL 必查)

per Sprint 2 dispatch packet §3.3:

### Review-1: shift(1) leak-free 100% verify
```bash
# E2 cold review 必跑 grep
grep -rnE '(rolling\([0-9]+\)\.(mean|std|corr|max|min)|\.rolling\(window=[0-9]+\)\.)' \
    --include='*.py' helper_scripts/m4/

# Rust grep
grep -rnE 'rolling_mean|rolling_std|rolling_corr|rolling_max|rolling_min' \
    --include='*.rs' rust/openclaw_core/src/m4_miner/

# 每個 hit 必查上下行有 `.shift(1)` 或 `.shift(lit(1))` 或 inline 反證註解
# 0 hit 無 shift(1) → REJECT IMPL
```

### Review-2: Bonferroni K=2500 hard-coded 或 config-driven
```bash
grep -rnE 'BONFERRONI_K|K_TOTAL|alpha_corrected|0\.05\s*/\s*\d+' \
    --include='*.py' --include='*.rs' helper_scripts/m4/ rust/openclaw_core/src/m4_miner/

# 必 hit ≥ 1 (應為 K=2500 hard-coded 或 config.toml driven)
# 0 hit → Bonferroni 未實作 → REJECT IMPL
```

### Review-3: HMM/Markov/GARCH 黑名單 grep
```bash
grep -rnE 'HMM|hmmlearn|GaussianHMM|markov_switching|arch_model|GARCH|MS-ARCH' \
    --include='*.py' --include='*.rs' helper_scripts/m4/ rust/openclaw_core/src/m4_miner/

# 必 0 hit
# 任何 hit → REJECT IMPL + RCA log
```

### Review-4: engine_mode filter 必含 `live_demo`
```bash
grep -rnE "engine_mode\s*=\s*'live'|engine_mode\s*=\s*\"live\"|WHERE.*engine_mode.*=\s*'live'" \
    --include='*.py' --include='*.rs' --include='*.sql' helper_scripts/m4/

# 任何 hit 必 `IN ('live', 'live_demo')` 形式
# 單獨 `='live'` → REJECT (per memory `project_engine_mode_tag_live_demo`)
```

### Review-5: Decision Lease backref 100% non-NULL
```sql
-- W2-F MIT post-IMPL audit 跑
SELECT COUNT(*) FROM learning.hypotheses 
WHERE hypothesis_source_module='M4_AUTO' 
  AND decision_lease_draft_id IS NULL
  AND created_at > now() - INTERVAL '24h';
-- Pass: 0 row
```

---

## §10 Open Questions (未在本 spec finalize,W1-C IMPL 階段定)

### Q1: K=500 estimate 是否準確?

per leakage spec §2.2.2 K_hyp ≈ 500;但實際 Sprint 2 IMPL 完成第一 batch 後可能 K_hyp 偏離 (太多 feature pass effect_size 0.2 gate → K_hyp 偏高 → α 更嚴 → 0 DRAFT promote)。

**處理**: Sprint 2 IMPL 第一週收集 K_hyp empirical 後,Sprint 3 開始 PA + MIT + QC 三角仲裁 K_hyp adjustment。Stage 1 baseline K_hyp=500 不變。

### Q2: Cross-asset feature (BTC vs ETH minus return) 是否在 Sprint 2 內 ship?

per §2.1.3 baseline 25 feature 含 cross-asset,但 cross-asset 需:
- BTC + ETH 同時 active (per Sprint 2 dispatch packet candidate #3)
- KalmanFilter cointegration 統計驗 (Sprint 2 IMPL 重)

**推薦**: Sprint 2 ship 同 timeframe 1-asset feature (24 個 baseline);cross-asset defer Sprint 3 配合 candidate #3 BTC/ETH pairs。

### Q3: Cron 頻率 (daily vs hourly)?

per design spec Open Q2:
- (a) Daily UTC 00:00: 成本可控,latency 24h
- (b) Hourly: latency 1h,LLM/CPU cost 高 (但 M4 是純 statistical,LLM cost = 0)
- (c) Event-driven: 對 event-window 最佳,對 statistical 不適用

**推薦 Sprint 2 baseline**: **Daily UTC 00:00 cron** (per design spec recommendation);Sprint 3+ 如 event-driven 需求明顯再加 event listener hook。

### Q4: Sub-period stability split 對 90d window 切 50/50 = 45d 各半,sample size 是否充足?

per leakage spec §2.4.3 SQL skeleton 使用 `NTILE(2) OVER (... ORDER BY observed_at)` 50/50 split。90d 切 45d each:
- statistical hypothesis (rolling corr): 1m level 45d ~ 64k observation per symbol → 充足
- event-window: 45d ~ 8-15 event per symbol → 不充足 (需 90d full → split 不適用)

**處理**: 
- Statistical hypothesis: 50/50 split (per leakage spec §2.4 baseline)
- Event-window hypothesis: 跳過 sub-period stability check (`subperiod_pass = NULL`) + 同時設 `status='exploratory'` 強制 (per AC-S2-B-4 30 event gate)

### Q5: Cross-language fixture 1e-4 對齊在 Sprint 2 何時跑?

per design spec §4.4 fixture test:
- IMPL DONE 前 E4 regression 階段必跑 (per Sprint 2 dispatch packet §7.4)
- Sprint 2 IMPL 期間 incremental commit 不必每次跑
- IMPL DONE + E2 cold review pass 後,E4 regression `pytest srv/tests/test_m4_cross_language_fixture.py` 必 pass

---

## §11 References

### §11.1 Parent specs
- v5.8 master `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M4 line 158-184
- M4 design spec `docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md`
- M4 leakage protocol `docs/execution_plan/2026-05-21--m4_minimum_bar_and_leakage_protocol.md`
- V103 EXTEND schema spec `docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md`
- Sprint 2 dispatch packet `docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md`

### §11.2 V### land status
- V100 `learning.hypotheses` base ✅ land 2026-05-23
- V103 EXTEND ✅ land 2026-05-22

### §11.3 governance
- ADR-0024-lite Cowork operator-assistant: `docs/adr/0024-cowork-subscription-operator-assistant.md`
- ADR-0036 statistical method blacklist (HMM/GARCH): Sprint 1A-γ 待 land
- ADR-0045 M4 governance: Sprint 1A-γ 待 land
- AMD-2026-05-21-01 autonomy vs human final review

### §11.4 Skills 引用
- feature-engineering-protocol: 6 leakage 類型 + shift(1) compliance
- time-series-cv-protocol: Purged k-fold + sample size + embargo
- ml-pipeline-maturity-audit: 5 階段 + 4 維度

### §11.5 Memory 引用
- `feedback_indicator_lookahead_bias` (2026-04-24 P1-11 F3 RETRACT — rolling shift(1) 強制核心教訓)
- `feedback_v_migration_pg_dry_run` (V### Linux PG empirical mandate)
- `project_engine_mode_tag_live_demo` (engine_mode IN ('live','live_demo') filter)
- `feedback_demo_over_paper_for_edge` (paper 不入 edge 估計)
- `feedback_working_principles` (對抗式驗證 + 誠實報告)

### §11.6 16 root principles compliance
- #1 Single controlled write entry: M4 writeback 走 INSERT learning.hypotheses + Decision Lease + GovernanceHub (lease 即 write authority gate)
- #3 AI output → Decision Lease: M4 DRAFT 寫 `lease_type='M4_DRAFT_WRITEBACK'` (即使 `live_order_intent=false`)
- #6 Uncertainty → conservative: leakage_scan_pass DEFAULT FALSE fail-closed
- #7 Learning ≠ live: M4 DRAFT 不 trigger live order;promote past `'preregistered'` 必 operator click
- #8 Trade reconstructable: Decision Lease lease_id 100% non-NULL backref
- #10 Fact/inference/assumption: 本 spec 明確標 SPRINT 2 IMPL boundary vs SPRINT 3+ defer
- #11 Agent autonomy within P0/P1: M4 寫 DRAFT 屬 agent autonomy 但無 live order 寫權
- #12 Evolve from evidence: M4 設計初衷 = 從 90d data 挖 alpha hypothesis,evidence-driven

---

## §12 W1-C E1 IMPL Dispatch Readiness Checklist

| 項目 | Status | Note |
|---|---|---|
| **W1-B algorithm spec land** | ✅ 本 spec | 本檔即 dispatch packet |
| **V100 base table land** | ✅ 2026-05-23 | `learning.hypotheses` 31k+ schema |
| **V103 EXTEND land** | ✅ 2026-05-22 | 6 column + 3 index |
| **4 source table freshness verify** | 🟡 W1-C 開工前必跑 §7 SQL | E1 W1-C 自查 |
| **Rust m4_miner module placement** | 🟢 ready | `rust/openclaw_core/src/m4_miner/` 不存在 = 新建 |
| **Python helper_scripts/m4/ placement** | 🟢 ready | 目錄不存在 = 新建 |
| **ADR-0036 黑名單 ADR land** | 🟡 Sprint 1A-γ 待 land | 但本 spec §2.3 已寫 invariant 不依賴 ADR 文件,grep 即生效 |
| **GovernanceHub `M4_DRAFT_WRITEBACK` lease type** | 🟡 W1-C IMPL 必驗 governance.acquire_lease 支援此 type | E1 W1-C 自查 |
| **Cross-language fixture infrastructure** | 🟡 W1-C IMPL DONE 後 E4 regression 跑 | per AC + design spec §4.4 |
| **Sprint 2 cron schedule wire-up** | 🟡 Sprint 2 末週才 land (Default disabled) | 不阻 W1-C IMPL |

**Verdict**: **READY** — W1-C E1 IMPL 可立即接此 spec 開工。3 個 🟡 是 W1-C IMPL 內自查 + IMPL DONE 後 regression,不是 dispatch block。

---

**Spec END**

MIT W1-B DESIGN DONE

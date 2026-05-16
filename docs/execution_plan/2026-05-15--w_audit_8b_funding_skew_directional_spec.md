# W-AUDIT-8b — A4-A Funding Skew Directional Spec

Date: 2026-05-15（v0.2 base）/ 2026-05-16（v0.3 sensitivity sweep patch）
Status: Spec v0.3 review/design / no strategy implementation authority
Scope: New alpha candidate using AlphaSurface Tier 2 `FundingSkew` + `OIDeltaPanel`. No live/demo launch, no risk/sizing change, no runtime config mutation.

> v0.3 patch 加入 `## Stage 0R v0.3 Trigger Gate Sensitivity Sweep`（位於 `## Replay-First Validation` 之後 / `## Implementation Boundary` 之前），對應 2026-05-16 Round 1 RED RCA 結論「signal failure 主導 + sample 邊際次要」決策的 sweep 範圍擴展。Round 2 sensitivity sweep 是 PA 推薦 Option A 路徑，AMD-2026-05-15-02 §8 condition 3 wording **不改**，3-gate 仍 strict AND。

## PM Verdict

Funding Skew is allowed to move to Stage 0R replay design because Phase B funding/OI panels are already live and `[66]` panel freshness passed on 2026-05-15. It is not a resurrection of retired `funding_arb`.

This strategy treats funding as a cross-sectional crowding signal, not as a funding-payment capture or cash-and-carry arbitrage. Positive expected funding income must not be counted in promotion metrics until funding settlement attribution is first-class and MIT signs the ledger join.

2026-05-15 QC/MIT/BB review result: **conditional approve for Stage 0R replay design only**. No implementation, demo launch, config mutation, or promotion evidence is authorized by this spec. The next source task may only be a read-only Stage 0R replay query/report design or implementation packet after PA handoff.

## Distinction From Retired `funding_arb`

| Item | Retired `funding_arb` | W-AUDIT-8b Funding Skew |
|---|---|---|
| Core idea | single-symbol funding payment capture / basis-like arbitrage | cross-symbol crowding and squeeze/reversion signal |
| Spot leg | required for true arbitrage, absent in demo | not required |
| Positive funding payment in edge | historically incomplete / unsafe | excluded or conservatively treated as zero until ledger proof |
| AlphaSurface tag | old strategy retained only for audit | `FundingSkew` + `OIDeltaPanel` |
| Promotion path | retired by ADR-0018 | Stage 0R replay preflight → Stage 1 Demo micro-canary only |

## Hypothesis

Funding extremes encode crowded positioning. The directional edge is expected only when funding skew, OI delta, and price action agree on crowding pressure.

Candidate rules:

1. **Crowded-long fade**: symbol funding is top decile versus cohort median, OI 15m/1h is rising, price momentum is stalling, and spread to cohort median is widening → short-biased mean reversion.
2. **Crowded-short squeeze**: symbol funding is bottom decile, OI is rising, price holds above local support, and funding skew begins to mean-revert → long-biased squeeze follow-through.
3. **No-signal default**: funding extreme without OI confirmation, stale panel, or high spread/cost ratio emits no action.

## Data Contract

Inputs:

- `AlphaSurface.funding_curve`: `FundingCurveSnapshot` from `panel.funding_rates_panel`
- `AlphaSurface.oi_delta_panel`: `OIDeltaPanel` from `panel.oi_delta_panel`
- Tier 1 indicators for local trend/volatility confirmation
- AccountManager fee source for post-fee edge modelling

Required derived fields per symbol:

- `funding_bps`
- `funding_zscore_25sym`
- `funding_percentile_25sym`
- `funding_spread_to_median_bps`
- `oi_delta_15m_pct`
- `oi_delta_1h_pct`
- `local_vol_bps`
- `expected_dir` in `{-1, 0, +1}`
- `funding_source_tier`
- `oi_source_tier`
- `strategy_variant='funding_skew_directional.v0_2'`
- `alpha_source_id='funding_skew_directional'`
- `funding_interval_min` or `funding_interval_hour`
- `source_mode` in `{ws_current, rest_settled}` when funding fields enter the report

Staleness:

- funding panel WARN > 60s, FAIL > 300s
- OI panel WARN > 60s, FAIL > 300s
- any FAIL sets strategy output to no-action and writes an evaluation reason

## Signal Formula Draft

For each candidate symbol:

```text
funding_skew_bps = funding_bps(symbol) - median(funding_bps(cohort))
funding_z = robust_zscore(funding_bps(symbol), cohort)
oi_confirmed = abs(oi_delta_15m_pct) >= oi_min_pct
crowded_long = funding_z >= z_hi AND funding_percentile >= p_hi AND oi_confirmed
crowded_short = funding_z <= -z_hi AND funding_percentile <= p_lo AND oi_confirmed
```

Directional proposal:

```text
if crowded_long and price_stall_or_breakdown:
    expected_dir = -1
elif crowded_short and price_hold_or_breakout:
    expected_dir = +1
else:
    expected_dir = 0
```

Stage 0R v0.2 locks the first price-action confirmation as a fixed point-in-time filter, not a grid:

- `price_stall_or_breakdown`: prior closed 5m return `<= 0`
- `price_hold_or_breakout`: prior closed 5m return `>= 0`

Any later variant of price-action confirmation must be preregistered and counted in `K_total`.

Initial thresholds for replay grid only:

- `z_hi`: 1.5 / 2.0 / 2.5
- `p_hi`: 0.85 / 0.90 / 0.95
- `p_lo`: 0.15 / 0.10 / 0.05
- `oi_min_pct`: 1.0 / 2.0 / 3.0 over 15m
- holding horizon: 30m primary; 15m and 60m sensitivity cells

These are trial parameters for Stage 0R replay. They must not be promoted as TOML defaults before DSR/PBO acceptance.

Counted candidate grid:

```text
K_new_min = 25 symbols
          × 2 direction branches
          × 3 z_hi
          × 3 percentile-pairs
          × 3 oi_min_pct
          × 3 horizons
          = 4050 inspected cells before prior comparable trials
```

`K_total = K_prior + K_new_min + any additional inspected variants`. `K_prior` must be read from comparable `learning.strategy_trial_ledger` rows or conservatively declared.

## Replay-First Validation

Stage 0R must run before any demo canary request.

Mandatory report fields:

- pooled and per-symbol `n` plus `n_eff`
- avg gross/net bps after fee/slippage
- funding payment attribution mode: primary eligibility must be `excluded`
- funding interval and source mode (`ws_current` ticker surface vs `rest_settled` history)
- PSR(0) with skew/kurt adjustment
- DSR with explicit `K_total`
- block-bootstrap CI with 60m primary block and 8h funding-cycle sensitivity
- CSCV PBO
- parameter sensitivity surface, not single best cell only
- stale-panel, missing-panel, and settlement-window exclusion counts
- panel latest times, ages, source tiers, and cohort coverage
- cost-edge ratio and maker/taker split
- direction-branch breakdown: crowded-long fade vs crowded-short squeeze
- baseline lift versus no-funding/OI-confirmation baseline

Promotion floor:

- no symbol may be eligible below `n_eff >= 100`
- active direction branch must have `n_eff >= 50`
- pooled sample should be `n_eff >= 300`
- sample must span at least 14 funding cycles
- no single day or funding cycle may contribute more than 25% of eligible rows
- `avg_net_bps >= +15`
- PSR(0) >= 0.95
- DSR >= 0.95 with explicit `K_total`
- PBO <= 0.20
- 95% block-bootstrap lower bound > 0
- adjacent grid cells must show a plateau rather than a single lucky threshold cliff
- no positive edge may depend on unverified funding settlement income

Output is only `eligible_for_demo_canary=true/false`. It is not Stage 1 PASS.

## Stage 0R v0.3 Trigger Gate Sensitivity Sweep

### 起源與動機

Round 1 (2026-05-16) 在 5.72d panel 數據窗 + spec v0.2 fixed `z_hi=1.5/2.0/2.5 × p_hi=0.85/0.90/0.95 × p_lo=0.15/0.10/0.05 × oi=1/2/3 × h=15/30/60` 4050 cell grid 跑出 `eligible_for_demo_canary=false` (RED)。RCA（`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md`）判定 RED **65% signal failure 主導 + 35% sample 邊際次要**：

- Strategy gate 過嚴 → 5.72d × 25 sym × 411,840 candidate 5m bar 只 7 個過 gate = **0.0017% trigger rate**
- Baseline pooled `n_eff=6,530` 充足，揭示 **-16.91 bps** 負 edge
- 即使 panel 擴至 14d/30d，0.0017% trigger rate × extra time **不會** 把 n=7 推到 n_eff=300+
- Spec v0.2 fixed parameter family **未證偽 funding skew hypothesis**（只證偽「z≥1.5 + percentile≥0.85 + OI≥1%」極端 gate combination）

故 v0.3 加入 trigger gate sensitivity sweep，明確探討 trigger rate vs statistical power 的 trade-off。在 panel ≥ 7d 重跑時並排 4 個 z 門檻，看是否能找到任一 cell 同時滿足 trigger rate ≥ 0.5% AND `n_eff >= 50`。

### Sweep Methodology

#### Z gate sensitivity dimension

新增 z 門檻 sensitivity dimension（取代 v0.2 `z_hi=1.5/2.0/2.5`，**擴展為 4 個 z cell**）：

| z_cell_id | z_hi（同號用於 crowded_short 反號）| trigger 預期 rate（相對 z=1.5） | rationale |
|---|---|---|---|
| `z_relaxed` | 1.0 | ~10x trigger rate vs z=1.5 | 低門檻 / 高 trigger / 低 power per signal |
| `z_moderate` | 1.2 | ~3-5x | 中間值（z=1.0 vs 1.5 之間）|
| `z_baseline` | 1.5 | 1.0 (reference) | v0.2 fixed family 對齊 |
| `z_strict` | 2.0 | ~0.3x | 高門檻 / 低 trigger / 高 power per signal（如有信號）|

**Pre-empirical assertion**（PA Phase 2 run plan 必預先寫入 expected ratios，**rerun 時做 reality check**）：z=1.0 預期觸發數 ≈ 10x of z=1.5；z=1.2 預期 ≈ 3-5x；z=2.0 預期 ≈ 0.3x。實際 ratio 與預期偏離 > 2x 必由 PA + QC 在 verdict 中討論原因（panel data 結構、tail-heavy z 分布等）。

#### 同維 sweep 範圍保留

`p_hi / p_lo / oi_min_pct / horizon` 範圍與 v0.2 對齊（**不擴展**），確保 K_new 增加可控且 sweep 矩陣維度有限：

- `p_hi`: 0.85 / 0.90 / 0.95
- `p_lo`: 0.15 / 0.10 / 0.05
- `oi_min_pct`: 1.0 / 2.0 / 3.0
- horizon: 15 / 30 / 60 min（30m primary）

#### 4-cell × 2-branch × per-symbol output matrix

每個 sweep run 必輸出以下層級資料：

1. **Per-z-cell aggregated**（4 cells × 2 branches = 8 top-level cells）：每個 (z_cell, branch) 對 pooled 25 symbols × 3×3×3×3 = 81 sub-grid cells，回 pooled `n / n_eff / avg_net_bps / DSR / PBO / Wilson CI` 等
2. **Per-z-cell per-branch per-symbol**（4 × 2 × 25 = 200 rows）：每對 (z_cell, branch, symbol) 回 per-symbol `n / n_eff / avg_net_bps / Wilson CI`
3. **Best primary cell per (z_cell, branch)**（4 × 2 = 8 best cells）：類似 v0.2 best primary cell，但每個 (z_cell, branch) 對 grid 取 best
4. **Sweep-wide cross-z comparison**：以 (branch, symbol) 為 row，4 個 z column，比較 (z_cell, branch, symbol) 在 trigger rate / n_eff / avg_net_bps 維度的 plateau / cliff

### K_total per-cell minimum 要求

#### Preserve K_prior + K_new_min floor

K_total floor 保留 `K_prior + K_new_min`，但 `K_new_min` 必須反映 sweep 擴展：

```text
K_new_min_v0_3 = 25 symbols
               × 2 direction branches
               × 4 z_hi cells（v0.3 ↑ from 3）
               × 3 percentile-pairs
               × 3 oi_min_pct
               × 3 horizons
               = 5400 inspected cells
```

舊 `K_new_min_v0_2 = 4050`（3 z）變為 `K_new_min_v0_3 = 5400`（4 z），即 +33%。

`K_total_v0_3 = K_prior + 5400 + any preregistered additional variants`。strict funding_skew K_prior **保持 0**（per 2026-05-16 empirical query：`learning.strategy_trial_ledger` `funding_skew%` filter 回 0）；relaxed `funding%` filter 回 9 仍作 MIT-signed conservative comparison。

#### Cell-level n_eff minimum stratified by z

雖然 K_total floor 不下調，但 cell-level eligibility floor 在 sweep 視窗下允許 **z-stratified n_eff minimum**，因為 z=1.0 cell 預期 trigger 是 z=1.5 的 ~10x，pooled n_eff 自然會更大（不一定需要與 z=1.5 採同一 100 floor）：

| z_cell | symbol n_eff floor | branch n_eff floor | pooled n_eff floor | rationale |
|---|---:|---:|---:|---|
| `z_relaxed` (1.0) | ≥ 100 | ≥ 50 | ≥ 300 | 跟 v0.2 baseline；relaxed gate 不放寬統計 floor |
| `z_moderate` (1.2) | ≥ 100 | ≥ 50 | ≥ 300 | 同 |
| `z_baseline` (1.5) | ≥ 100 | ≥ 50 | ≥ 300 | v0.2 標準 |
| `z_strict` (2.0) | ≥ 30（降）| ≥ 15（降）| ≥ 75（降）| **strict gate per-signal 高 power**；如 best cell `n_eff=30` 且 Wilson CI lower > 0 + DSR > 0.95 仍可 diagnostic-eligible，但 promotion 仍要 `pooled n_eff >= 300`（強 statistical requirement） |

**z_strict 例外只用於 diagnostic eligibility**，**不解 promotion gate**。Promotion 仍要 `pooled n_eff ≥ 300`，僅 z_strict 對 strategy diagnostic survival 視為「值得進 round 3 zoom-in」的 hint。其餘 z cell（relaxed / moderate / baseline）floor 維持 v0.2。

#### Funding cycle / day-share floor

`funding cycles >= 14` + `single-day share ≤ 25%` + `single funding-cycle share ≤ 25%` floor 對所有 z cell 維持，因為 cycle/day diversity 是樣本獨立性要求，不應隨 z 變化。

### Output Format Spec

#### Per-z-cell aggregated block

```json
"sweep_per_z_cell": {
  "z_relaxed_z_eq_1_0": {
    "z_hi": 1.0,
    "trigger_rate": 0.0083,
    "trigger_rate_vs_z_baseline_ratio": 4.88,
    "by_branch": {
      "crowded_long_fade": {
        "n_total": 1234, "n_eff": 205,
        "avg_gross_bps": -4.5, "avg_net_bps": -16.5,
        "psr_0": 0.42, "dsr": 0.001,
        "pbo": 0.62,
        "bootstrap_ci_95_60m": [-21.3, -10.2],
        "bootstrap_ci_95_8h_funding_cycle": [-25.1, -7.5],
        "wilson_ci_n_to_n_eff": [0.156, 0.198],
        "funding_cycles_distinct": 14,
        "max_day_share": 0.18,
        "max_funding_cycle_share": 0.20,
        "eligibility_pass": false,
        "eligibility_fail_reasons": ["avg_net_bps < +15", "DSR < 0.95", "PBO > 0.20"]
      },
      "crowded_short_squeeze": { /* 同 schema */ }
    }
  },
  "z_moderate_z_eq_1_2": { /* 同 */ },
  "z_baseline_z_eq_1_5": { /* 同 */ },
  "z_strict_z_eq_2_0": { /* 同 */ }
}
```

#### Per-z-cell × per-branch × per-symbol block

```json
"sweep_per_symbol": [
  {
    "z_cell": "z_relaxed_z_eq_1_0",
    "branch": "crowded_long_fade",
    "symbol": "BTCUSDT",
    "n": 45, "n_eff": 9,
    "avg_net_bps": -8.2,
    "wilson_ci_95_n_eff_share": [0.13, 0.27],
    "funding_cycles": 12,
    "max_day_share": 0.22,
    "max_funding_cycle_share": 0.18,
    "per_symbol_pass": false,
    "per_symbol_fail_reasons": ["n_eff < 100"]
  }
  // 4 × 2 × 25 = 200 rows total
]
```

#### Best primary cell per (z_cell, branch)

```json
"best_primary_cell_per_z_branch": [
  {
    "z_cell": "z_relaxed_z_eq_1_0",
    "branch": "crowded_long_fade",
    "candidate_key": "BTCUSDT|crowded_long_fade|z=1.0|p=0.95/0.05|oi=2|h=30",
    "n": 18, "n_eff": 3,
    "avg_net_bps": 2.1,
    "psr_0": 0.55, "dsr": 0.012,
    "wilson_ci_95_share": [0.10, 0.21],
    "plateau_neighbors_pass": 1,
    "plateau_threshold_neighbors_min": 2,
    "plateau_pass": false
  }
  // 4 × 2 = 8 rows total
]
```

#### Sweep-wide cross-z comparison

```json
"sweep_cross_z_comparison": [
  {
    "branch": "crowded_long_fade",
    "symbol": "BTCUSDT",
    "by_z_cell": {
      "z_relaxed": { "n_eff": 9, "avg_net_bps": -8.2, "wilson_ci_lower": -12.0 },
      "z_moderate": { "n_eff": 5, "avg_net_bps": -6.5, "wilson_ci_lower": -10.5 },
      "z_baseline": { "n_eff": 1, "avg_net_bps": null, "wilson_ci_lower": null },
      "z_strict": { "n_eff": 0, "avg_net_bps": null, "wilson_ci_lower": null }
    },
    "n_eff_drop_z_relaxed_to_z_strict": -9,
    "monotonic_drop_in_n_eff": true
  }
  // 2 × 25 = 50 rows
]
```

### Wilson CI Computation per Cell

#### 公式

每個 (z_cell, branch, symbol) cell 對 `n_eff / n` 比例計算 Wilson Score Interval (95%)，做為 sample size 對 effective sample 的 binomial proxy。Wilson CI 比直接拿 normal approximation 更穩定，特別在 small-n（n < 30）regime 不會超出 [0, 1]：

```text
p_hat = n_eff / n
z = 1.96 (95% CI)
denom = 1 + z² / n
center = (p_hat + z² / (2n)) / denom
margin = z × sqrt( p_hat (1 - p_hat) / n + z² / (4n²) ) / denom
wilson_ci_lower = center - margin
wilson_ci_upper = center + margin
```

#### 用途

1. **per-symbol n_eff share variability**：Wilson CI 對 sample 內 n_eff / n 分布的二項變動 quantify。Wilson lower > 0.10 hints sample 在 effective basis 上 stable。
2. **avg_net_bps 的 CI 補充**：除 block-bootstrap 60m + 8h CI，Wilson CI 對 cell 是否 over-fitted small-n outlier 給第二維 sanity check。
3. **promotion gate optional addition**：v0.3 不強制 Wilson CI 進 eligibility floor，但 PA verdict 在判斷 round 2 是否值得 zoom-in 時做 reference signal。

### Pre-rerun Linux PG Empirical Query Template

Per `feedback_v_migration_pg_dry_run.md`：rerun 前必 PA solo 跑 read-only empirical query 驗證 panel 足夠 + cycles 充足 + K_prior 沒漂移：

```sql
-- Q1: panel funding span + row count + symbol count
SELECT
  to_timestamp(MIN(snapshot_ts_ms)/1000) AS funding_min_ts,
  to_timestamp(MAX(snapshot_ts_ms)/1000) AS funding_max_ts,
  EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000) - to_timestamp(MIN(snapshot_ts_ms)/1000)))/86400 AS span_days,
  COUNT(*) AS total_rows,
  COUNT(DISTINCT symbol) AS sym_count
FROM panel.funding_rates_panel;

-- Q2: OI panel span（parallel check）
SELECT
  to_timestamp(MIN(snapshot_ts_ms)/1000) AS oi_min_ts,
  to_timestamp(MAX(snapshot_ts_ms)/1000) AS oi_max_ts,
  COUNT(*) AS oi_rows
FROM panel.oi_delta_panel;

-- Q3: K_prior strict（funding_skew filter）
SELECT count(DISTINCT candidate_key)::int AS k_prior_strict_funding_skew
FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE '%funding_skew%'
       OR trial_family ILIKE '%funding_skew%'
       OR candidate_key ILIKE '%funding_skew%');

-- Q4: K_prior relaxed（funding-related filter, MIT-signed fallback）
SELECT count(DISTINCT candidate_key)::int AS k_prior_funding_related
FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE '%funding%'
       OR trial_family ILIKE '%funding%'
       OR candidate_key ILIKE '%funding%');

-- Q5: funding cycles distinct in panel data
SELECT COUNT(DISTINCT next_funding_ms)::int AS distinct_cycles_in_panel
FROM panel.funding_rates_panel
WHERE next_funding_ms IS NOT NULL;
```

#### Empirical assertion gate

Rerun 必符合以下條件才允許跑 round 2 sweep：

1. `funding span_days >= 7.0` AND `oi span_days >= 7.0`
2. `funding sym_count = 25` AND `oi rows >= funding rows × 0.95`（panel parity）
3. `k_prior_strict_funding_skew = 0`（confirms no comparable trial drift）
4. `distinct_cycles_in_panel >= 21`（7d × 3 cycles/day floor）

任一條件 fail → PA verdict halt round 2，提交 PM 評估是否再 defer 或 escalate。

### Output / Storage / Audit

- Output JSON：`/tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_<YYYYMMDD>_<HHMM>_pa.json`（Linux ssh-only write，**禁** Mac write）
- Log：`/tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_<YYYYMMDD>_<HHMM>.log`（stderr + stdout capture）
- 報告：`docs/CCAgentWorkSpace/PA/workspace/reports/<YYYY-MM-DD>--w_audit_8b_stage0r_round2_sensitivity_sweep_verdict.md`
- Mac-side mirror：sweep JSON 可從 Linux scp 拿回 Mac `docs/audits/2026-05-XX--w_audit_8b_round2_sweep_artifact.json` 作為審計副本（**但 source of truth 是 Linux PG runtime 跑出**，不接受 Mac mock data）
- **No** runtime config / TOML / RiskConfig / Operator role / authorization / engine env mutation. **No** AMD §8 wording mutation. **No** Stage 1 demo canary opens.

### 接受 / Reject 條件（v0.3 Sweep）

接受（任一）= **任一 (z_cell, branch) 過 eligibility floor**：
- z_relaxed / z_moderate / z_baseline：v0.2 全 floor 過（avg_net ≥ +15, DSR ≥ 0.95, PBO ≤ 0.20, plateau pass, Wilson CI lower > 0）
- z_strict（diagnostic only）：strict floor stratification 過 + 標 `promotion_pending_pooled_n_eff_300`

Reject = **全 4 z cell 全 branch 全 RED**：

- Round 2 sweep 結束後 `sweep_per_z_cell` 8 個 (z_cell, branch) `eligibility_pass=false` 全部
- 觸發 PA 補新 RCA 報告 + 建議 AMD-2026-05-15-02 §8 condition 3 wording 修訂（per 既有 RCA §8 conditional amendment 觸發點）

Open（過半但不到絕大多數）= **1-3 個 (z_cell, branch) 邊際 pass / 4-7 個 RED**：
- PA verdict + QC/MIT/BB 4-agent review 決定 round 3 zoom-in 範圍 vs 直接 archive tombstone
- AMD §8 wording **暫不動**；按 round 3 結果再評估

## Implementation Boundary

Allowed next source task, after PA handoff:

1. Add replay query/report for `funding_skew_directional`.
2. Add read-only diagnostic feature extraction.
3. Add fail-closed evaluation reasons for unavailable/stale panels.

Explicitly forbidden in this spec phase:

- changing risk sizing or leverage
- enabling demo/live trading
- counting unverified funding payments as profit
- reusing retired `funding_arb` code path as-is
- adding basis/spot execution assumptions
- assuming every Bybit symbol has the same funding interval
- high-fanout REST polling for funding or OI
- overloading raw panel `source_tier` with strategy labels
- opening live or live_demo Stage 1 without green Stage 0R + operator approval

## Open Questions

### v0.2 originals

1. PA must decide whether v0.2 fixed 5m price-action confirmation is sufficient for the first replay, or whether a narrower preregistered variant set is needed. **v0.3 resolution**：v0.2 fixed 5m sufficient for round 1（已跑）；round 2 sweep 不額外擴展 price-action 變體，只擴 z gate。
2. MIT must define the exact `K_prior` query against `learning.strategy_trial_ledger`. **v0.3 resolution**：empirical 2026-05-16 query 確認 `funding_skew%` strict filter = 0，relaxed `funding%` = 9；MIT 簽 strict K_prior=0（per `funding_skew_directional` ≠ retired `funding_arb` candidate space separation）。
3. BB must sign the funding interval / source-mode fields in the Stage 0R report before replay implementation. **v0.3 resolution**：round 1 report 已含 `funding_interval_min` per-symbol + `source_mode=ws_current`；BB 已在 round 1 packet 中無 push back；round 2 sweep 不重新查 source-mode（保持 ws_current）。

### v0.3 additions

4. PA must confirm pre-empirical assertion magnitude（z=1.0 預期 ~10x trigger vs z=1.5）對 Bybit funding 分布的合理性。**Action**：rerun 時 PA 比對 actual vs predicted；偏離 > 2x → PA 額外 verdict 段落分析 Bybit funding tail-heavy 結構。
5. QC must sign z-stratified n_eff floor（`z_strict` 30/15/75 降 vs 其餘 100/50/300）的統計 power justification。**Action**：round 2 dispatch 前 QC review 此 spec patch + 簽 OFF z_strict stratification。
6. MIT must sign Wilson CI computation method（v0.3 新增）對 `n_eff / n` 比例的解釋；MIT 也必簽 round 2 sweep K_total `5400` (4 z × ...) 對 DSR sr_benchmark = √(2 ln 5400) = 4.14 變動極小。**Action**：round 2 dispatch 前 MIT review v0.3 spec + 簽 OFF Wilson CI + K_total formula。

## Acceptance For Spec v1

- QC signs the signal formula, 30m primary horizon, `K_total`, DSR/PBO gates, and sample floors **including z-stratified n_eff floor stratification (v0.3)**.
- MIT signs raw-panel as-of joins, stale handling, source-tier separation, funding-attribution mode, **Wilson CI computation (v0.3), and K_prior strict funding_skew=0 (v0.3)**.
- BB signs Bybit funding interval/source-mode compatibility and REST/WS rate-limit posture.
- PM updates TODO with this spec as the current `W-AUDIT-8b` source.

## Changelog

### v0.3 — 2026-05-16

- 加 `## Stage 0R v0.3 Trigger Gate Sensitivity Sweep` 全節（Sweep Methodology / K_total per-cell minimum / Output Format Spec / Wilson CI / Pre-rerun Linux PG Empirical Query Template / Output Storage Audit / 接受 Reject 條件）
- 擴 `K_new_min` from 4050 to **5400**（3 z → 4 z cells；25 sym × 2 branch × 4 z × 3 percentile × 3 oi × 3 horizon）
- 新增 z gate sensitivity dimension：z=1.0 / 1.2 / 1.5 / 2.0 並排（4 cells）
- 新增 cell-level n_eff stratification：z_strict 降 floor 30/15/75 作 diagnostic only；其餘 z cell 維持 v0.2 100/50/300
- 新增 Wilson CI 95% per (z_cell, branch, symbol) cell
- 新增 sweep output JSON schema：sweep_per_z_cell + sweep_per_symbol + best_primary_cell_per_z_branch + sweep_cross_z_comparison
- 新增 pre-rerun Linux PG empirical query template + assertion gate（panel ≥ 7d / sym=25 / K_prior strict=0 / cycles ≥ 21）
- 加 v0.3 open questions Q4-Q6（PA / QC / MIT 簽 OFF 點）
- 加 changelog 節
- 不動 v0.2 `## Hypothesis` / `## Data Contract` / `## Signal Formula Draft` / `## Replay-First Validation` / `## Implementation Boundary`

### v0.2 — 2026-05-15

- Initial spec post 2026-05-15 QC/MIT/BB conditional approve for Stage 0R replay design only
- Branch-separated crowded-long fade / crowded-short squeeze
- K_total >= K_prior+4050, DSR>=0.95, PBO fail-closed, raw panel as-of joins
- Funding attribution `excluded`
- 30m primary horizon, 15m/60m sensitivity
- z=1.5/2.0/2.5 / p=0.85/0.90/0.95 / 0.15/0.10/0.05 / oi=1/2/3 fixed family

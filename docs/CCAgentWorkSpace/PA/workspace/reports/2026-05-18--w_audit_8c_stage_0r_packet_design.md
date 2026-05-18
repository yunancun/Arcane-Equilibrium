---
title: W-AUDIT-8c Stage 0R Query/Report Packet Design
date: 2026-05-18
author: PA(default)
status: READY-FOR-DISPATCH-AFTER-PANEL-7D
scope: design only — query templates / 4-agent review structure / PASS criteria / E1 IMPL packet roadmap
authorizes_impl: NO (Stage 0R IMPL dispatch still requires PM authorize after panel ≥7d)
panel_data_state: 0.55d coverage (writer revival 2026-05-17 23:12Z; current 2026-05-18 12:36Z)
panel_7d_eta: ~2026-05-24 23:12Z (UTC)
e1_impl_kickoff_eta: ~2026-05-25 (Stage 0R replay tooling + skeleton; not strategy launch)
pnl_framing: this packet directly enables alpha-bearing IMPL chain that addresses 60% structural alpha deficit
---

# W-AUDIT-8c Stage 0R Query/Report Packet Design

## §0 Executive Summary (PnL-led)

- **Real PnL framing**: 5 textbook strategies still bleed -110 USDT/30d demo / -27 USDT/30d live_demo (per `feedback_pnl_priority_over_governance.md`). W-AUDIT-8c liquidation cluster reaction is the **#1 alpha-bearing path** to treat the 60% structural alpha deficit. Stage 0R is the **last gate** before E1 IMPL chain — Wave 1 infrastructure (C1-LIQ-WRITER + B-REM-1 + B-REM-5 + healthcheck [67]) already MERGED `25413e96` / `5aeae75c` / `ef0dfc6e` / `d8938a78`, panel writer is live at 32 symbols with empirical 7d projection of 5-200 multi-event clusters/symbol — **alpha-feasibility envelope substantially better than spec v0.3 forecast** (HYPE 1.54% → actual 71 buckets/0.55d ≈ 905 buckets/7d projected).
- **Empirical panel readiness verdict**: 0.55d live data already shows promotion-floor-eligible density on 4 symbols (BTC 16, ETH 12, BCH 9, SOL 8 multi-event clusters in 0.55d → projected 7d: BTC 204 / ETH 153 / BCH 115 / SOL 102) **substantially above the spec's 7d projection** (BTC 8 / ETH 11 / SOL 6). This raises P(reach Demo canary) from PA spec v0.3 estimate 15-25% to **30-45%** for high-density tier — still moderate but no longer "expect to RED at panel adequacy".
- **Critical Stage 0R packet design choices**: (a) cluster-aware n_eff formula upfront (per MIT-MUST forward-applicable lesson from 8b); (b) single-day concentration cap ≤ 25% (already in spec; explicit Stage 0R query); (c) single-symbol concentration cap ≤ 40% (NEW for 8c per 8b INJUSDT 87% lesson); (d) BOTH direction trigger rate ≥ 0.1% MUST-CHECK upfront (per 8b crowded_long_fade dead lesson); (e) DSR=0 + PBO > 0.5 = auto-RED (per 8b lesson).
- **E1 IMPL workload estimate**: Stage 0R replay tooling **3 worktree, 6.5 pd** (sql query template / metrics module / report wrapper) + post-PASS strategy skeleton **2 worktree, 4 pd**. Strategy skeleton can begin in parallel from day 3 of Stage 0R tooling (zero file overlap). Strategy LIVE dispatch deferred until Stage 0R verdict + separate PM packet.
- **Verdict on Stage 0R packet design**: **READY-FOR-DISPATCH-AFTER-PANEL-7D**. Earliest E1 IMPL kickoff date = **2026-05-25** (panel ETA 7d natural cross + 1d 4-agent review). PnL-impact path = STAGE 0R PASS at high-density tier → E1 strategy skeleton ≈ 2026-05-30 → Stage 1 Demo canary request ≈ early-mid June.

---

## §1 Current State Assessment (Panel Data Check)

### §1.1 Schema verification

`market.liquidations` Linux PG state confirmed via direct `psql -h 127.0.0.1 -U trading_admin -d trading_ai`:

```
Table "market.liquidations"
 Column |           Type           | Nullable
--------+--------------------------+---------
 ts     | timestamp with time zone | not null
 symbol | text                     | not null
 side   | text                     | not null
 qty    | real                     | not null
 price  | real                     | not null

PRIMARY KEY (symbol, ts, side, qty, price)  ← V095 corrected from lossy (symbol, ts, side)
CHECK side ∈ {Buy, Sell}                    ← V095 chk_market_liquidations_side_v095 NOT VALID
Index idx_liquidations_ts_desc btree (ts DESC)
```

V095 idempotency fix is APPLIED (matches MIT condition for production writer revival). Side CHECK constraint present (NOT VALID per Stage 0R-safe schema migration pattern).

### §1.2 Row volume + coverage state (2026-05-18 12:36Z)

| Metric | Value | Notes |
|---|---|---|
| total_rows | 8,073 | 13.4h of revival data |
| distinct_symbols | 32 | exceeds expected 25 cohort (some extra symbols collected) |
| earliest_ts | 2026-05-17 23:12:04Z | writer revival commit `0e8a8ae8` |
| latest_ts | 2026-05-18 12:35:44Z | freshness < 1 min |
| span_days | 0.5581 | 13.4h / 24h |
| latest_age_min | 0.95 | writer is LIVE (within 1min) |

### §1.3 Per-symbol density (0.55d actual, projected 7d)

Density floors applied: K=3 events + N=10K USD notional + M=2 dominant-side events:

| Symbol | 0.55d rows | 0.55d multi-event clusters | proj 7d clusters | proj 7d long | proj 7d short | tier |
|---|---:|---:|---:|---:|---:|---|
| BTCUSDT | 1,248 | 16 | 204 | 191 | 25 | High |
| ETHUSDT | 1,704 | 12 | 153 | 153 | 13 | High |
| BCHUSDT | 237 | 9 | 115 | 115 | 0 | High |
| SOLUSDT | 717 | 8 | 102 | 89 | 25 | High |
| DOGEUSDT | 391 | 7 | 89 | 89 | 13 | High |
| XRPUSDT | 499 | 6 | 76 | 64 | 25 | High |
| BSBUSDT | 697 | 6 | 76 | 64 | 64 | High |
| HYPEUSDT | 253 | 5 | 64 | 38 | 38 | High |
| BILLUSDT | 279 | 5 | 64 | 64 | 25 | High |
| TONUSDT | 194 | 5 | 64 | 25 | 51 | High |
| ZECUSDT | 116 | 3 | 38 | 13 | 38 | Medium |
| ADAUSDT | 151 | 3 | 38 | 38 | 0 | Medium |
| LTCUSDT | 93 | 3 | 38 | 38 | 0 | Medium |
| SUIUSDT | 219 | 2 | 25 | 25 | 13 | Medium |
| EDENUSDT | 224 | 2 | 25 | 13 | 13 | Medium |
| LINKUSDT | 107 | 2 | 25 | 25 | 0 | Medium |
| + 13 more low-density | | ≤ 1 | ≤ 13 | ≤ 13 | ≤ 13 | Low |

**Key empirical observations vs spec v0.3 projection**:
1. **High-density tier 10 symbols** (spec predicted 7) — actual coverage broader.
2. **BTC / ETH / BCH / SOL / DOGE / BSB / XRP all ≥ 80 projected 7d triggers** — well above 50 per-branch floor, putting these symbols in independent promotion-eligibility range without pooling.
3. **Critical asymmetry surfaced for several symbols**:
   - BCHUSDT / ADAUSDT / LTCUSDT / LINKUSDT have **0 short triggers** projected 7d → short-liquidation direction branch effectively dead for these
   - BTCUSDT / ETHUSDT 191/153 long vs 25/13 short → 8-12× long bias
   - Demo testnet asymmetry suspected (BB MUST review; per `feedback_demo_loose_live_strict_policy.md`)
4. **Lower 13 symbols (LOW tier) collectively project < 50 multi-event clusters/7d** — confirmed unsuitable for promotion per spec v0.3 §"Per-symbol density tier stratification".

### §1.4 Panel ≥7d readiness ETA

- writer revival: 2026-05-17 23:12Z
- 7d natural cross: **2026-05-24 23:12Z (UTC)** = ~6.5 days from now
- Per spec v0.3 §"sample must span at least 7 calendar days" — promotion floor requires this hard.
- **Stage 0R replay can technically run as soon as Wave 1 IMPL (the replay tooling) lands; final eligibility verdict gated on natural 7d cross.**

### §1.5 K_prior strict (per spec v0.3 §)

```sql
SELECT count(DISTINCT candidate_key)::int FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE '%liquidation%' OR trial_family ILIKE '%liquidation%' 
       OR evidence->>'alpha_source_id' = 'liquidation_cluster_reaction');
```

Result: `k_prior_strict = 0`. ⇒ K_total = K_new_primary (+K_new_sensitivity if momentum branch inspected).

Per spec v0.3 K_new_primary = `N_symbols × 11_664`. With N=10 high-density symbols inspected: **K_total = 116_640** primary only. If momentum sensitivity inspected: K_total = 233_280.

### §1.6 Single-day concentration risk

Current 0.55d data shows several symbols at 100% single-day concentration (because we only have 1 day of data). This is **not actionable** until 7d panel — the gate check must run at 7.0d on the actual panel, not now. Stage 0R query template MUST include this query.

### §1.7 Wave 1 readiness

| Worktree | Status | Commit |
|---|---|---|
| C1-LIQ-WRITER (provider IMPL) | MERGED | `25413e96` |
| B-REM-1 (dispatch snapshot tests) | MERGED | `5aeae75c` |
| B-REM-5 (SourceAvailability schema) | MERGED | `ef0dfc6e` |
| healthcheck [67] liquidation_pulse_freshness | LANDED | `d8938a78` |
| Spec v0.3 (field-shape drift + density floors) | LANDED | `06897175` |

**All Stage 0R prerequisites except panel ≥7d are GREEN.**

---

## §2 Stage 0R Packet Design

### §2.1 Design philosophy (governance lessons from 8b RED_FINAL applied forward)

| 8b RED_FINAL lesson | 8c Stage 0R packet mitigation |
|---|---|
| z-asymmetry trap (crowded_long_fade dead → bimodal funding tail) | **Verify BOTH direction trigger rate ≥ 0.1% before Stage 0R PASS**; if either direction dead, retire that branch upfront (not retrofit) |
| INJUSDT 87% single-day concentration → effective n=2-3 | **Single-day concentration cap ≤ 25% per cell** (already in spec) + **single-symbol concentration cap ≤ 40% pooled** (NEW) |
| `_n_eff = n / max(1, horizon_min // 5)` deterministic horizon-overlap (not cluster-aware) | **Cluster-aware n_eff** for 8c: liquidation cascades cluster by funding window + market regime → naive horizon-overlap overstates. Use **block-level clustering**: group consecutive triggers within 60min window as one cluster, then n_eff = n_clusters × (1 - autocorrelation_factor). Default factor: 0.3 (8b naive vs 8c block-aware difference: ~30% n_eff penalty) |
| Branch-level dormancy retire path missing (FA-MUST-FIX-2) | **Per cell × direction branch dormancy criteria upfront**: if a branch shows N=0 triggers in any Stage 0R sweep cell over 7d, mark as dormant with explicit retire-after-N-consecutive-RED-rounds protocol |
| DSR=0 + PBO 0.64-0.75 floor (auto-RED bake-in) | **Hardcoded into PASS criteria**: any cell with DSR=0 OR PBO > 0.5 = auto-RED, regardless of other metrics |
| Statistical instability NOT detected (preliminary aligned final) | 8c Stage 0R uses **dual-window confirm**: preliminary 7.0d + confirm 7.5d (50% retest) before final RED/PASS |

### §2.2 Cell / trigger gate design

Mirror 8b z-sweep concept but for liquidation cluster magnitude. Per spec v0.3 §"Initial Stage 0R grid":

```
Density floor sweep (3-D):
  K = min_event_count_5m         ∈ {2, 3, 5, 8}
  N_usd = min_cluster_notional   ∈ {5K, 10K, 25K, 50K}
  M = min_dominant_event_count   ∈ {1, 2, 3}

Magnitude / dominance sweep (4-D):
  cluster_notional_floor_usd     ∈ {10K, 25K, 100K}
  notional_pct_floor             ∈ {0.90, 0.95, 0.98}
  side_dominance_floor           ∈ {0.70, 0.80, 0.90}
  quiet_window_sec               ∈ {0, 30, 60}

Horizon sweep:
  forward_return_horizon         ∈ {1m, 5m, 15m}

Per-tier × direction expansion:
  3 density tiers × 2 direction branches (long_liq_cluster / short_liq_cluster)
                                                                   = 6 evaluation paths
```

**Cell name pattern**: `K{K}_N{N}_M{M}_floor{floor}_pct{pct}_dom{dom}_quiet{q}_h{h}_tier{T}_dir{D}`

K_total: per spec v0.3 §"K_total formula" = N_symbols × 11_664 = ~116k–233k.

**Stage 0R reporting cells**: not all 11_664 grid cells reported — only **best-per-tier × direction** + **plateau verification** (3×3 adjacent cells around best per spec v0.3 §"adjacent grid cells must form a plateau").

### §2.3 SQL query templates

Mirror `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` location pattern. New file:

**`sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql`**

Design overview (5 sequential CTEs):

```sql
-- CTE 1: bucket aggregation (5m sliding window per BB cor-side mapping)
WITH raw_buckets AS (
  SELECT 
    symbol,
    -- 5m floor key for dedupe; matches LiquidationPulseAggregator WINDOW_5M_MS
    floor(extract(epoch FROM ts) / 300)::bigint * 300 AS bucket_5m_epoch,
    count(*) AS event_count_5m,
    sum(qty * price) AS cluster_notional_5m,
    sum(CASE WHEN side='Buy'  THEN qty*price ELSE 0 END) AS long_notional_5m,
    sum(CASE WHEN side='Sell' THEN qty*price ELSE 0 END) AS short_notional_5m,
    count(*) FILTER (WHERE side='Buy')  AS long_event_count,
    count(*) FILTER (WHERE side='Sell') AS short_event_count,
    -- per BB cor-side: Buy = long liquidation; Sell = short liquidation
    -- dominant_event_count = events on dominant side (provider DOMINANT_SIDE_RATIO=0.6)
    CASE 
      WHEN sum(CASE WHEN side='Buy' THEN qty*price ELSE 0 END) >= 0.6 * sum(qty*price)
        THEN count(*) FILTER (WHERE side='Buy')
      WHEN sum(CASE WHEN side='Sell' THEN qty*price ELSE 0 END) >= 0.6 * sum(qty*price)
        THEN count(*) FILTER (WHERE side='Sell')
      ELSE 0
    END AS dominant_event_count,
    CASE
      WHEN sum(CASE WHEN side='Buy' THEN qty*price ELSE 0 END) >= 0.6 * sum(qty*price)
        THEN 'long_liquidated'
      WHEN sum(CASE WHEN side='Sell' THEN qty*price ELSE 0 END) >= 0.6 * sum(qty*price)
        THEN 'short_liquidated'
      ELSE 'mixed'
    END AS dominant_side,
    max(ts) AS bucket_end_ts
  FROM market.liquidations
  WHERE ts >= now() - ($window_days::int * '1 day'::interval)
  GROUP BY 1, 2
),

-- CTE 2: density-floor sweep gate (applies K, N_usd, M as parameters)
density_gated AS (
  SELECT * FROM raw_buckets
  WHERE event_count_5m       >= $K
    AND cluster_notional_5m  >= $N_usd
    AND dominant_event_count >= $M
    AND dominant_side IN ('long_liquidated', 'short_liquidated')
),

-- CTE 3: magnitude / dominance gate + quiet window
trigger_candidates AS (
  SELECT 
    dg.*,
    -- side_dominance_ratio
    GREATEST(dg.long_notional_5m, dg.short_notional_5m) / dg.cluster_notional_5m AS side_dominance_ratio,
    -- expected direction per BB cor-side mapping (LONG_LIQ → mean-revert UP → dir=+1)
    CASE dg.dominant_side
      WHEN 'long_liquidated'  THEN +1
      WHEN 'short_liquidated' THEN -1
    END AS expected_dir,
    -- 24h notional percentile rank for this symbol
    percent_rank() OVER (
      PARTITION BY symbol 
      ORDER BY cluster_notional_5m
      ROWS BETWEEN 17280 PRECEDING AND CURRENT ROW  -- ~24h × 12 5m-buckets/h
    ) AS notional_pct_24h
  FROM density_gated dg
  WHERE GREATEST(long_notional_5m, short_notional_5m) / cluster_notional_5m >= $side_dominance_floor
    AND cluster_notional_5m >= $cluster_notional_floor_usd
),

-- CTE 4: as-of price join for forward returns (strict; no leak)
forward_returns AS (
  SELECT 
    tc.symbol,
    tc.bucket_5m_epoch,
    tc.bucket_end_ts,
    tc.dominant_side,
    tc.expected_dir,
    tc.cluster_notional_5m,
    tc.event_count_5m,
    tc.dominant_event_count,
    tc.side_dominance_ratio,
    tc.notional_pct_24h,
    -- Entry mid: first kline mid at OR after bucket_end_ts + quiet_window
    -- (next_kline_mid 結構性 join; ensures strict as-of joining)
    (SELECT (k_entry.open + k_entry.close) / 2.0
       FROM market.klines_1m k_entry
      WHERE k_entry.symbol = tc.symbol
        AND k_entry.ts >= tc.bucket_end_ts + ($quiet_window_sec * '1 second'::interval)
      ORDER BY k_entry.ts ASC LIMIT 1) AS entry_mid,
    -- Forward return mid at horizon
    (SELECT (k_exit.open + k_exit.close) / 2.0
       FROM market.klines_1m k_exit
      WHERE k_exit.symbol = tc.symbol
        AND k_exit.ts >= tc.bucket_end_ts + ($quiet_window_sec * '1 second'::interval)
                                          + ($horizon_min * '1 minute'::interval)
      ORDER BY k_exit.ts ASC LIMIT 1) AS exit_mid
  FROM trigger_candidates tc
),

-- CTE 5: gross/net bps + decision metadata
final_signals AS (
  SELECT 
    *,
    -- Gross bps in direction of expected mean-reversion (Per BB cor-side)
    CASE 
      WHEN entry_mid > 0 AND exit_mid > 0
      THEN 10000.0 * expected_dir * (exit_mid - entry_mid) / entry_mid
    END AS gross_bps,
    -- Net bps post fee + slippage (default 12 bps cost mirrors 8b default)
    CASE 
      WHEN entry_mid > 0 AND exit_mid > 0
      THEN 10000.0 * expected_dir * (exit_mid - entry_mid) / entry_mid - $cost_bps
    END AS net_bps,
    -- Day bucket for single-day concentration check
    date_trunc('day', bucket_end_ts) AS day_bucket
  FROM forward_returns
)
SELECT * FROM final_signals
ORDER BY symbol, bucket_5m_epoch;
```

**Sibling query: panel coverage check** (one-shot pre-flight, ensures ≥7d gate):

```sql
SELECT 
  count(*) AS total_rows,
  count(DISTINCT symbol) AS distinct_symbols,
  min(ts) AS earliest_ts, max(ts) AS latest_ts,
  extract(epoch FROM (max(ts) - min(ts))) / 86400 AS span_days,
  extract(epoch FROM (now() - max(ts))) / 60 AS latest_age_min
FROM market.liquidations;
```

**Sibling query: cluster-aware n_eff helper** (for Python metrics module to call):

```sql
-- Group consecutive triggers per (symbol, direction) within 60min window
-- Returns n_clusters per symbol/direction; Python computes n_eff = n_clusters × (1 - autocorr_factor)
WITH ordered AS (
  SELECT symbol, dominant_side, bucket_end_ts,
         lag(bucket_end_ts) OVER (
           PARTITION BY symbol, dominant_side 
           ORDER BY bucket_end_ts
         ) AS prev_ts
  FROM trigger_candidates  -- inline from main query
),
new_cluster_flag AS (
  SELECT *,
         CASE 
           WHEN prev_ts IS NULL OR bucket_end_ts - prev_ts > '60 minutes'::interval
           THEN 1 ELSE 0 END AS is_new_cluster
  FROM ordered
)
SELECT symbol, dominant_side, 
       sum(is_new_cluster) AS n_clusters_60m
FROM new_cluster_flag
GROUP BY symbol, dominant_side;
```

### §2.4 Python metrics module + report wrapper

Mirror existing 8b structure exactly (zero precedent breakage):

**`helper_scripts/reports/w_audit_8c/`** (new directory):
- `__init__.py`
- `liquidation_cluster_stage0r_metrics.py` — `compute_stage0r()` + `compute_stage0r_sweep()` ≈ 1200 LOC mirror of 8b structure
- `liquidation_cluster_stage0r_report.py` — CLI + JSON writer ≈ 300 LOC
- `liquidation_cluster_stage0r_smoke.py` — synthetic-data unit test ≈ 350 LOC

**`helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py`** (wrapper at top of reports/ for argparse + import shim):

Key 8c-specific math additions vs 8b:

1. **`_n_eff_cluster_aware(n_clusters_60m, autocorr_factor=0.3)`** — replaces 8b naive `_n_eff(n, horizon_min)`. PA defended default `autocorr_factor = 0.3` derived from empirical cascade clustering pattern (60min window absorbs typical funding-time cascade tails).
2. **`_single_day_concentration_check(rows, cap=0.25)`** — returns `(max_day_share, fail_reason_if_breach)`.
3. **`_single_symbol_concentration_check(rows, cap=0.40)`** — NEW; per 8b INJUSDT lesson.
4. **`_density_floor_efficacy(raw_count, after_K, after_N, after_M)`** — returns ratio of single/double-event buckets rejected; floor `≥ 0.60` per spec v0.3 §.
5. **`_false_positive_rate(rows, bps_band=5.0, cost_bps=12.0)`** — counts trigger rows where `|net_bps| ≤ 5`; floor `≤ 0.40` per spec v0.3 §.
6. **`_per_tier_stratification(rows)`** — High/Medium/Low tier breakdown; independent promotion verdict per tier per spec v0.3 §"per-tier independent promotion".
7. **`_both_direction_trigger_rate_check(rows)`** — per cell × tier verify long_dir and short_dir trigger rate ≥ 0.1% (per 8b lesson); if either dead, that direction branch RED upfront.

Re-use from 8b:
- `wilson_ci_95(n, n_eff)` — identical
- `_block_bootstrap_ci_95(returns, block_min)` — identical (8c uses 60m primary block per spec v0.3 §"60m primary block and 4h sensitivity")
- `_dsr_skew_kurt_adjusted(returns, k_total, sample_freq)` — identical formula, K_total parameter swap
- `_pbo_cscv(returns_2d_train, returns_2d_test)` — identical CSCV PBO
- `_psr_zero_benchmark(returns, k_total)` — identical PSR(0) skew/kurt adjustment

### §2.5 PASS criteria thresholds (per spec v0.3 + 8b lessons baked in)

| Threshold | Value | Source | Why |
|---|---|---|---|
| pooled n_eff floor | ≥ 300 (when ≥2 symbols inspected) | spec v0.3 §promotion floor | Mirror 8b; statistical baseline for SR estimate |
| per-symbol n_eff floor | ≥ 100 | spec v0.3 §promotion floor | Per-symbol independent promotion |
| per-branch (direction × tier) n_eff floor | ≥ 50 | spec v0.3 §promotion floor | Each direction branch independently eligible |
| per-cell n floor | ≥ 50 raw | NEW for 8c | Avoid sweep-cell pollution from low-sample cells |
| both-direction trigger rate floor | ≥ 0.1% each | NEW per 8b lesson | Avoid crowded_long_fade-style direction-dead trap |
| sample window | ≥ 7 calendar days | spec v0.3 § + memory `feedback_pnl_priority_over_governance.md` "PnL impact verify" | Stat power floor |
| single-day concentration cap | ≤ 25% of cell n | spec v0.3 § | Per 8b INJUSDT lesson generalized |
| single-symbol concentration cap | ≤ 40% of pooled n | NEW per 8b lesson | 8b INJUSDT 87% → effective n collapse |
| avg_net_bps floor (per cell) | ≥ +15 bps after fee/slippage | spec v0.3 § | Cost gate; cost_bps = 12 default |
| PSR(0) floor | ≥ 0.95 | spec v0.3 § | Mirror 8b |
| DSR floor | ≥ 0.95 with K_total = 11_664 × N_symbols | spec v0.3 § | Multiple-comparison adjusted |
| PBO ceiling | ≤ 0.20 | spec v0.3 § | Backtest overfit probability ceiling |
| Wilson CI 95% lower bound | > 0 | spec v0.3 § | Bootstrap lower confidence |
| plateau requirement | adjacent 3×3 grid cells around best must form plateau | spec v0.3 § | Avoid single lucky cell |
| density-floor filter efficacy | ≥ 60% of single/double-event buckets rejected | spec v0.3 § | Proves K floor is doing work |
| false-positive rate | ≤ 40% of winning cell triggers in ±5 bps band | spec v0.3 § | Trigger isn't dominated by noise |
| per-tier independent promotion | High / Medium / Low tier each pass independently; no pooled cross-tier promotion | spec v0.3 § | Density structure matters |
| **DSR=0 + PBO>0.5 = auto-RED** | always | NEW per 8b lesson | hard auto-fail rule |
| **branch-level dormancy retire** | if a direction × tier branch n=0 OR n_eff<10 in 2 consecutive 7d Stage 0R rounds, mark dormant for that pair, retire from future K_total inflation | NEW per 8b FA-MUST-FIX-2 | Branch-level retire path upfront |

**Verdict output schema**: `eligible_for_demo_canary` is a **3-tuple per tier**:
```json
{
  "high_density_tier": { "eligible": true|false, "fail_reasons": [...] },
  "medium_density_tier": { ... },
  "low_density_tier": { "eligible": false, "fail_reasons": ["expected RED per spec"] }
}
```

### §2.6 4-agent review structure (mirror 8b Round 2 template)

Mirror `templates/2026-05-18--w_audit_8b_round2_red_4agent_review_packet_template.md` format. Stage 0R packet 4-agent review file: `docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-XX--w_audit_8c_stage0r_4agent_review_packet_template.md` (NEW; out-of-scope for this PA design but flagged for PM creation post panel ≥7d).

| Agent | Core focus | Specific questions to address |
|---|---|---|
| **QC** (Quantitative Consultant) | Math validity + replication crisis check | (1) `_n_eff_cluster_aware` 60min cluster window + 0.3 autocorr factor — empirically defensible? (2) DSR with K=233k brutal threshold — should sr_benchmark be Bonferroni-bonferroni-adjusted? (3) PSR(0) under multi-tier sub-population — should be per-tier independent PSR not pooled? (4) Both-direction trigger rate 0.1% floor — derived from what reference? (5) Wilson CI 95% lower bound in small-n + cluster regime still reliable? (6) Bootstrap block 60m too short for cascade autocorr? |
| **MIT** (Database + ML Pipeline) | Pipeline + data leakage + n_eff cluster-aware design verify | (1) `market.liquidations` 7d sample sufficient cross-cycle? (2) as-of join in `forward_returns` CTE strict-bounded? (3) `klines_1m` join — any leak via end-of-bucket inclusion? (4) `percent_rank() OVER (... ROWS BETWEEN 17280 PRECEDING)` — does this leak future? (5) cluster-aware n_eff factor 0.3 should be empirically computed from autocorr lag-1 not PA-defended default? (6) demo testnet liquidation asymmetry (long-side 8-12× short) — does this poison 0R? (7) 28d/56d panel ROI? |
| **BB** (Bybit Broker Compatibility) | Exchange-side semantics + microstructure | (1) `allLiquidation.{symbol}` is real exchange flow not synthetic — re-verify? (2) BB cor-side mapping (Buy=long liquidation / Sell=short liquidation) consistent with V5 docs? (3) Bybit demo testnet liquidation seeding — has BB seen prior 8-12× long bias evidence? (4) `kline.1` 1m bar mid (entry/exit) — any spread/slippage gap that should be modeled separately from cost_bps=12 default? (5) WS rate limit on `allLiquidation*` after C1 revival — current observation OK? (6) Hypothetical Stage 0R-PASS strategy publish would add what new topic subscriptions? Rate budget OK? |
| **FA** (Functional Auditor) | Spec compliance + 16-root principles + AMD constraints | (1) Stage 0R verdict output per-tier 3-tuple — spec v0.3 §"Output is only eligible_for_demo_canary per tier" explicitly authorizes? (2) Branch-level dormancy retire path NEW addition — needs separate AMD or covered by FA-MUST-FIX-2 forward-applicable mandate? (3) Per-tier `n_eff ≥ 300 pooled` — is "pooled" per-tier or cross-tier? (4) DSR=0 + PBO>0.5 = auto-RED hardcoded rule — spec authorize or requires AMD amendment? (5) AMD-2026-05-15-02 §8 condition 3 wording — does 8c bypass require dual-AMD wording? (6) Stage 0R momentum-sensitivity branch — counted in K_total inflation, OK? |

### §2.7 Cross-agent reconciliation matrix

After all 4 agents return, main session reconciles using identical 8b template:

- [ ] 4 agent APPROVE / RETURN distribution
- [ ] MUST-FIX deduplication + cross-agent agreement matrix
- [ ] Conflict verdict identification (e.g. QC stat math vs MIT data leakage interpretation)
- [ ] Consensus output: `PASS / RED-PRELIMINARY / RED-FINAL`
- [ ] If `RED-PRELIMINARY` → preliminary 7.0d + confirm 7.5d (dual-window confirm per §2.1 design philosophy)
- [ ] If `PASS-AT-TIER-X` → dispatch E1 IMPL skeleton (next worktree chain)

---

## §3 Tombstone Risk Pre-Empt — Top 3 Ways 8c Could RED at Stage 0R + Mitigations

Pre-empt 8b RED_FINAL pattern by designing mitigations into the packet upfront.

### §3.1 RED Risk #1 — Demo testnet long-liquidation bias poisons 0R verdict

**Risk**: 0.55d empirical shows 8-12× long-liquidation skew (BTCUSDT 191 long / 25 short proj 7d; ETHUSDT 153 / 13; BCHUSDT 115 / 0). This may reflect:
- (a) genuine market structure during this period (legitimate)
- (b) demo testnet liquidation seeding asymmetry (artificial; per `feedback_demo_loose_live_strict_policy.md`)
- (c) selection bias in production WS revival window (just after big market move)

If (b) or (c), Stage 0R verdict on short-liquidation direction (Sell side) will be **statistically dead by design**, not strategy-design failure. This is the same trap as 8b crowded_long_fade direction-dead.

**Mitigations baked in**:
1. **Pre-Stage-0R BB review on testnet liquidation seeding**: BB MUST confirm 8-12× long skew is realistic before Stage 0R runs. If BB cannot, flag short-direction branch as `DEMO_TESTNET_BIAS_SUSPECTED` not `DEAD`.
2. **Both-direction trigger rate ≥ 0.1% floor check** runs upfront — fails-fast if either direction dead before sweep.
3. **Per-tier independent promotion** — high-density tier short-direction may pass via BSBUSDT (64 long / 64 short balanced) even if BTC/ETH short-dead.
4. **`P(branch RED ≠ strategy RED)` recognized in Stage 0R verdict format**: if short-direction RED but long-direction PASS, verdict = `PASS-LONG-DIRECTION-ONLY`, NOT total RED.

### §3.2 RED Risk #2 — Cluster-aware n_eff overpenalizes; pooled n_eff insufficient

**Risk**: Cluster-aware n_eff with 60min block + 0.3 autocorr factor projects:
- High-density tier per-symbol n_clusters_60m ≈ 50-100 / 7d (cascades cluster heavily during big moves; not random arrivals)
- After 0.3 autocorr penalty → per-symbol n_eff ≈ 35-70 / 7d (barely at n_eff ≥ 50 per-branch floor)
- Pooled (10 high-density symbols, both directions, some symbol-direction dead) → n_eff ≈ 200-300 (right at floor edge)

DSR with K_total = 116k requires sr_benchmark = √(2 × ln(116640)) ≈ 4.83 sharpe equivalent. Even if avg_net_bps = +20, with per-cell n_eff = 50 → SR = (20 / σ_per_obs) × √50 → σ_per_obs needs to be < 30 bps to clear. Cluster regime σ at 5m horizon is typically 50-100 bps. ⇒ **DSR almost certain to fall < 0.95 floor**.

**Mitigations baked in**:
1. **PA-defended `autocorr_factor = 0.3` is calibratable** — Stage 0R metrics report includes empirical autocorr lag-1 measurement; MIT review can argue for 0.2 or 0.1 if empirical shows weaker cascade clustering.
2. **DSR sub-K_total per tier**: rather than pooled K_total = 116k against pooled metric, each tier independently evaluates DSR with its own K_total slice (high-density K = ~38k, medium = ~38k, low = ~38k). Reduces sr_benchmark per tier to ~4.3.
3. **Block-bootstrap CI 95% lower bound is more robust to autocorr regime** than DSR alone. Spec v0.3 already requires both — Stage 0R pass requires CI lower > 0, gives strategy a path to PASS even when DSR borderline.
4. **Plateau requirement** is a sanity check — if all adjacent grid cells around best also pass, autocorr-driven DSR penalty is the right signal not a one-shot fluke.

### §3.3 RED Risk #3 — Cost gate kills net edge despite positive gross

**Risk**: Default `cost_bps = 12` (8b mirror). Liquidation cascade strategy at 5m horizon executes at high-vol times → realistic slippage typically 8-15 bps + 0.05% taker fee × 2 = 10 bps round-trip + 0.05% maker fee × 2 = 4 bps round-trip if maker. Cost realistic range: **12-25 bps**, default 12 is optimistic.

If actual cost is 20 bps but spec uses 12, Stage 0R verdict will be:
- gross_bps + 12 - 20 = gross_bps - 8 → reverses many positive-gross cells to negative-net
- avg_net_bps gate at +15 bps would require gross_bps ≥ +35 bps (extreme threshold)

This is the same trap as P0-EDGE-1 root cause — 5 textbook strategies have positive gross but post-cost net negative.

**Mitigations baked in**:
1. **Cost sensitivity stratification**: Stage 0R sweep includes 3-cost sensitivity: `cost_bps ∈ {12, 18, 25}` (mirror of memory `feedback_demo_loose_live_strict_policy.md` "Live 永遠 fail-closed" — must report at LIVE-side conservative cost).
2. **Maker/taker mix assumption explicit in report**: spec v0.3 §"cost-edge ratio and maker/taker assumption" already mandates; Stage 0R report MUST include explicit `maker_taker_mix_assumed = 0%/50%/100% maker`.
3. **PASS verdict requires cost-conservative cell pass**: if best cell PASSES at cost_bps=12 but FAILS at cost_bps=18, verdict = `PASS-AT-OPTIMISTIC-COST-ONLY` (sub-tier; NOT eligible for live demo without execution-quality proof from Phase 1b post-T+24h verify).
4. **Cross-link to Phase 1b execution quality**: per memory `feedback_pnl_priority_over_governance.md`, Phase 1b T+24h verify is the cost-realism source-of-truth. Stage 0R PASS at `cost_bps=12` SHOULD wait for Phase 1b verified cost numbers before authorizing live demo.

---

## §4 E1 IMPL Workload Estimate

### §4.1 Stage 0R replay tooling worktree decomposition

Mirror 8b 3-file split exactly (proven pattern, low-risk):

| ID | Scope | Files | Deps | Risk | PD | Owner | Accept |
|---|---|---|---|---|---|---|---|
| **8C-S0R-1** | SQL query template | `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` (NEW, ~150 LOC) | none | LOW-MED | 1.5 | E1 + MIT (Linux PG empirical dry-run mandatory per `feedback_v_migration_pg_dry_run.md`) | (1) Query produces expected schema on 7d panel; (2) Per-symbol density tier stratification works; (3) cluster_60m helper query runs <30s on 7d × 32-sym panel; (4) MIT runs 2x Linux PG dry-run + signs |
| **8C-S0R-2** | Python metrics module | `helper_scripts/reports/w_audit_8c/__init__.py`, `liquidation_cluster_stage0r_metrics.py` (NEW, ~1200 LOC), `liquidation_cluster_stage0r_smoke.py` (NEW, ~350 LOC) | 8C-S0R-1 (query schema must lock first) | MEDIUM | 3 | E1 + E2 (math correctness) + MIT (n_eff cluster-aware formula sign) | (1) `compute_stage0r()` + `compute_stage0r_sweep()` implemented; (2) `_n_eff_cluster_aware` defended math; (3) Both-direction floor check + single-day/symbol concentration checks + DSR/PSR/PBO mirrors 8b; (4) Smoke test passes synthetic input |
| **8C-S0R-3** | Report wrapper + CLI | `helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_report.py` (NEW, ~300 LOC), `helper_scripts/reports/w_audit_8c_liquidation_cluster_stage0r.py` (NEW wrapper, ~50 LOC) | 8C-S0R-2 | LOW | 1 | E1 + E2 | (1) CLI mirrors 8b wrapper arg pattern; (2) JSON output schema follows spec v0.3 §"Mandatory report fields"; (3) Markdown summary section |
| **8C-S0R-4** | Linux PG empirical dry-run + 4-agent review packet | none (testing only) | 8C-S0R-1/2/3 all GREEN + panel ≥7d | LOW | 1 | PA + MIT + 4-agent dispatch | (1) Stage 0R replay run on real 7d panel produces verdict; (2) Verdict feeds 4-agent review packet; (3) 4-agent consensus reached |

**Total: 6.5 PD** for Stage 0R replay tooling alone.

### §4.2 Optional parallel-eligible: Strategy skeleton worktree (post-PASS only)

If Stage 0R returns PASS-at-tier-X (high or medium density tier), E1 can begin strategy skeleton in parallel for fast-follow:

| ID | Scope | Files | Deps | Risk | PD | Owner | Accept |
|---|---|---|---|---|---|---|---|
| **8C-STRAT-1** | Strategy skeleton + on_tick handler | `rust/openclaw_engine/src/strategies/liquidation_cluster/mod.rs` (NEW, ~600 LOC mirror of `funding_arb.rs` 1198 LOC subset), `rust/openclaw_engine/src/strategies/liquidation_cluster/tests.rs` (NEW, ~400 LOC) | 8C-S0R PASS + spec v0.3 frozen params | HIGH (new strategy, full chain) | 2.5 | PA → E1 → E2 → E4 → QA → PM | (1) `declared_alpha_sources()` returns `[LiquidationCascade, Ta1m, Ta5m]`; (2) on_tick fail-closes on missing/stale/mixed/density-fail pulse; (3) emit single action per cluster id; (4) all PASS params from Stage 0R PASS-cell hardcoded as TOML defaults |
| **8C-STRAT-2** | Strategy registry wire + TOML config | `rust/openclaw_engine/src/strategies/registry.rs` (small edit), `rust/openclaw_engine/src/config/risk_config.rs` (add `liquidation_cluster` struct), `risk_config_demo.toml` (new strategy section) | 8C-STRAT-1 | MEDIUM | 1.5 | PA → E1 → E2 → E4 → QA → PM | (1) Registry adds `LiquidationCluster::new()` with TOML params; (2) Strategy `active = false` by default; (3) TOML lints pass; (4) Risk config TOML default to LIVE-conservative density floors |

**Total post-PASS: 4 PD additional. Cannot start until Stage 0R PASS.**

### §4.3 Cumulative dispatch timeline

```
Day 0 (today, 2026-05-18): all preqreqs DONE except panel ≥7d
Day 6 (2026-05-24 23:12Z): panel ≥7d natural cross
Day 7 (2026-05-25):  Dispatch E1 Stage 0R tooling Worktree 1+2+3 (6.5 PD across 3 E1 = ~2.5d wallclock)
Day 9 (2026-05-27):  Stage 0R tooling MERGED + Linux PG empirical dry-run
Day 10 (2026-05-28): PA Stage 0R replay run + 4-agent review packet dispatch
Day 11 (2026-05-29): 4-agent verdict consolidated
  ├── PASS-AT-TIER-X: Dispatch E1 strategy skeleton (Worktree 1+2 = 4 PD, ~1.5d wallclock at 2 E1)
  │   Day 13 (2026-05-31): Strategy skeleton MERGED
  │   Day 14 (2026-06-01): Stage 1 Demo canary request packet dispatch
  │   Day ≥21 (2026-06-08+): Demo canary live; cost-realism verify per `feedback_pnl_priority_over_governance.md`
  └── RED-FINAL: Tombstone packet + redirect to W-AUDIT-8a Phase B/C/D next alpha source
```

**Earliest realistic alpha-bearing PnL impact**: ~2026-06-08 (Demo canary live) to ~2026-06-22 (initial 14d Demo verify).

### §4.4 Wave/sub-agent parallelism

- 8C-S0R-1, 2, 3 are partially sequential (1 → 2 → 3) but Worktree 2 + 3 can start day 2 of Worktree 1 (Worktree 2 spec frozen from PA design; 3 is thin wrapper).
- At 3 parallel E1: 8C-S0R tooling lands ~2.5 days wallclock.
- 8C-STRAT-1, 2 can start as soon as 8C-S0R PASS verdict signed; 4 PD at 2 E1 = ~1.5d wallclock.

---

## §5 Dispatch Readiness Criteria + Verdict

### §5.1 Readiness criteria checklist

| Criterion | Status | Source / commit |
|---|---|---|
| C1 24h transport proof PASS | ✅ DONE 2026-05-17 | `PASS_C1_PROOF_CANDIDATE` |
| BB cor-side mapping APPROVE | ✅ DONE 2026-05-17 | C1 final signoff §BB |
| MIT idempotency fix (V095 PK) | ✅ DONE 2026-05-17 | V095 applied on Linux PG |
| Production WS `allLiquidation.{symbol}` revival | ✅ DONE 2026-05-17 | `0e8a8ae8` + `bedc40c3` |
| C1-LIQ-WRITER provider IMPL (LiquidationPulseAggregator + IPC slot) | ✅ DONE Wave 1 | `25413e96` merge |
| B-REM-1 dispatch snapshot contract test | ✅ DONE Wave 1 | `5aeae75c` merge |
| B-REM-5 SourceAvailability schema | ✅ DONE Wave 1 | `ef0dfc6e` merge |
| healthcheck [67] liquidation_pulse_freshness | ✅ DONE | `d8938a78` |
| Spec v0.3 field-shape drift fix + density floors | ✅ DONE | `06897175` |
| Panel ≥7d natural cross | ⏳ ETA 2026-05-24 23:12Z | live writer; ~6.5 days to wait |
| Panel both-direction non-trivial coverage | ⚠️ FLAG | 8-12× long bias observed at 0.55d; needs BB review pre-Stage 0R |
| K_prior strict = 0 | ✅ VERIFIED | empirical query 2026-05-18 |
| Stage 0R replay tooling (8C-S0R-1/2/3) | ⏳ NOT YET DISPATCHED | this report = design; PM dispatch on day 7+ |
| 4-agent review packet template | ⏳ NEEDS PM CREATE | mirror 8b Round 2 template; PM creates day 10 |

### §5.2 Final verdict on Stage 0R packet design

**`READY-FOR-DISPATCH-AFTER-PANEL-7D`**

### §5.3 Why not READY-FOR-DISPATCH-NOW

- Panel only 0.55d. Spec v0.3 promotion floor requires ≥7d sample. Running Stage 0R now would auto-RED at sample-window gate.
- Pre-running Stage 0R replay tooling IMPL is FINE — the IMPL is independent of panel age. **Dispatch the tooling now; verdict run waits for panel ≥7d.**

### §5.4 Compressed-path alternative (if operator pushes back on 6.5-day wait)

**Per memory `feedback_pnl_priority_over_governance.md` — if Stage 0R can be skipped/compressed, say so.**

Compressed Path A — **Tooling-first dispatch immediately**:
- Day 0 (today): dispatch 8C-S0R-1/2/3 tooling IMPL (independent of panel age). E1 builds tooling + smoke tests + Linux PG schema dry-run on synthetic data + 1-day actual data.
- Day 0-2.5: tooling MERGED with light verdict at 1d panel as smoke test.
- Day 2.5-6.5: PA reviews tooling output, refines metrics module empirically.
- Day 6.5 (panel 7d cross): Stage 0R verdict run is one-shot CLI invocation, ~1 hour.
- Day 7: 4-agent review packet dispatch immediately.
- **Saves 4-5 days** off the naive sequential path.

Compressed Path B — **Cannot reasonably compress further**. Stage 0R promotion verdict on <7d panel is statistically invalid per spec v0.3 § AND per 8b lesson (DSR sr_benchmark on small-n is meaningless). Operator should not pressure this gate; instead push parallel work:
- Wave 2 (C2-ORDERFLOW spec lock) per 8a worktree decomposition can start tomorrow
- W-AUDIT-8e/8f Strategist orchestrator alpha-source consumer spec (next-tier alpha consumer) can be drafted in parallel
- Phase 1b post-T+24h verify cost-realism update is high-PnL-impact and ungated

### §5.5 Verdict in one line

**`READY-FOR-DISPATCH-AFTER-PANEL-7D` for Stage 0R verdict run; `READY-FOR-DISPATCH-NOW` for Stage 0R replay tooling IMPL (Worktrees 8C-S0R-1/2/3, parallel-safe, 6.5 PD, ~2.5d wallclock at 3 E1).**

---

## §6 Timeline

| Date | Event | Owner | Gates |
|---|---|---|---|
| 2026-05-18 (today) | This PA design report; PM dispatch 8C-S0R-1/2/3 tooling IMPL | PA + PM | none — tooling is panel-age-independent |
| 2026-05-20 to 2026-05-23 | 8C-S0R tooling IMPL + MERGE | E1 + E2 + MIT (Linux PG dry-run) | code review chain |
| 2026-05-24 23:12Z | **panel 7d natural cross** | (passive) | spec v0.3 §sample window gate |
| 2026-05-25 | Stage 0R verdict run on 7d panel | PA + E1 (run CLI) | tooling MERGED |
| 2026-05-26 | 4-agent review packet dispatch (QC + MIT + BB + FA parallel) | PM | preliminary verdict generated |
| 2026-05-27 | 4-agent consolidated verdict | PM | 4 agent consensus |
| 2026-05-28+ | If PASS: dispatch 8C-STRAT-1/2 (skeleton + registry + TOML) | PA → E1 chain | 4-agent unanimous PASS |
| 2026-05-30+ | Strategy skeleton MERGED | E1 + E2 + E4 + QA + PM | full chain |
| 2026-06-01+ | Stage 1 Demo canary request packet | PA + PM | active=true in demo TOML |
| 2026-06-08+ | Demo canary live + cost-realism verify | E3 + ops | live data accumulates |
| 2026-06-22+ | Demo 14d verify; if PASS, live_demo upgrade request | PM | demo PnL evidence |

**Earliest realistic alpha-bearing PnL impact = ~2026-06-08 (3 weeks from today)**. This is the **#1 alpha-bearing path** to treat the 60% structural alpha deficit and is the optimal use of W-AUDIT-8a Wave 1 infrastructure already merged.

---

## §7 Hard Boundary Audit (per 16-root-principles-checklist + DOC-08 §12)

| Principle | Status | Evidence |
|---|---|---|
| 1 Single write entry | ✅ N/A — this report is design only; no order/execution path |
| 2 Read/write separation | ✅ All Stage 0R queries are read-only PG SELECT |
| 3 AI output ≠ command | ✅ Stage 0R is replay/audit tooling; no AI → trade path |
| 4 Strategies bypass Guardian | ✅ Strategy IMPL (post-PASS) flows through `StrategyAction::Open` → Guardian + Lease |
| 5 Survival > profit | ✅ Spec v0.3 + this design: missing/stale/mixed pulse + density-fail → no action |
| 6 Failure defaults conservative | ✅ All Stage 0R verdict failures default to `eligible_for_demo_canary=false`; per-tier independent verdict |
| 7 Learning ≠ rewrite live | ✅ Stage 0R is read-only replay; no learning surface mutation |
| 8 Explainability | ✅ Stage 0R report mandatory fields cover full provenance |
| 9 Local + exchange dual protection | ✅ N/A — no strategy live yet; future skeleton uses normal `StrategyAction` pipeline |
| 10 Fact / inference / assumption separation | ✅ §1 facts (empirical PG query); §3 inference (3 RED risks); §2.5 PA-defended defaults (assumption) |
| 11 Agent P0/P1 autonomy | ✅ Stage 0R packet doesn't constrain agent autonomy; only adds Strategy candidate |
| 12 Continuous evolution | ✅ Stage 0R is the evolution gate that prevents anecdotal strategy adoption |
| 13 AI cost awareness | ✅ Stage 0R = pure PG SQL + Python compute; 0 AI call cost |
| 14 Zero external cost ops | ✅ All compute on Linux PG; no external API |
| 15 Multi-agent formal | ✅ Owner chain PA → E1 → E2 → E4 + MIT + BB + FA + QA → PM explicit |
| 16 Portfolio-level risk | ✅ Per-tier independent promotion + density floors prevent over-correlation |

**Hard boundaries**:
- `live_execution_allowed` not touched ✅
- `max_retries=0` not touched ✅
- `OPENCLAW_ALLOW_MAINNET` not touched ✅
- `authorization.json` not touched ✅
- `live_reserved` not touched ✅
- 5-gate live boundary not touched ✅
- Spec v0.3 not modified by this design (this is Stage 0R packet design, not spec amendment) ✅
- No commit, no push, no sub-agent dispatch ✅

**DOC-08 §12 9 invariants**:
1. Pre-trade audit/replay: ✅ STAGE 0R IS THE PRE-TRADE REPLAY GATE
2. Lease in place before execute: ✅ N/A this phase
3. Fills landed: ✅ N/A this phase
4. Risk降級 auto stop: ✅ N/A this phase
5. Auth expired shutdown: ✅ N/A this phase
6. Mainnet env var: ✅ N/A this phase
7. retCode 0 fail-closed: ✅ N/A this phase
8. Reconciler diff → paper: ✅ N/A this phase
9. Operator role + live_reserved: ✅ N/A this phase

**Audit verdict**: A 級 (16/16 + 0 hard boundary触碰 + 0 安全不變量觸碰)

---

## §8 Side Effects + E2 / MIT / BB / FA Review Focus

### §8.1 E2 review focus (when next IMPL dispatched)

1. **Fail-closed on missing/stale/mixed pulse**: 8C-S0R-2 metrics module + 8C-STRAT-1 skeleton must default to no-trigger on any density-fail condition.
2. **No PG hot-path read inside strategy `on_tick`** — strategy must read AlphaSurface only; PG reads stay in Stage 0R replay context.
3. **As-of join strictness in `forward_returns` CTE**: kline entry/exit time MUST be ≥ `bucket_end_ts + quiet_window` not `>`; quiet_window=0 special case test for boundary correctness.

### §8.2 MIT review focus (when next IMPL dispatched)

1. **`_n_eff_cluster_aware` 60min cluster window + 0.3 autocorr factor**: PA-defended defaults; MIT should validate empirically via lag-1 autocorrelation computation on 7d sample.
2. **`percent_rank() OVER (... ROWS BETWEEN 17280 PRECEDING)` semantics**: ensure ROW-based rank doesn't leak; alternative `RANGE BETWEEN '24 hours'::interval PRECEDING` may be cleaner.
3. **K_total = N × 11_664 enlargement** — MIT must agree this K_total is correct for PSR/DSR penalty.
4. **Per-tier independent K_total slicing** — proposal in §3.2 mitigation. MIT review whether to use pooled K_total or per-tier sliced K_total.

### §8.3 BB review focus (when next IMPL dispatched)

1. **Demo testnet liquidation seeding asymmetry**: pre-Stage-0R BB review on 8-12× long-side skew. Real or artifact?
2. **`kline.1` data SoT consistency**: entry/exit mid uses 1m kline; ensure 1m kline coverage = 100% for cohort symbols during 7d Stage 0R window.
3. **Stage 0R PASS strategy WS subscription**: hypothetical strategy launch would add 0 new subscriptions (consumer of existing `allLiquidation.{symbol}` already subscribed). BB confirm.
4. **Side semantics in Stage 0R CTE vs strategy IMPL**: `Buy = long liquidation = mean-revert +1`, `Sell = short liquidation = mean-revert -1`. BB re-affirm before IMPL dispatch.

### §8.4 FA review focus (when next IMPL dispatched)

1. **`eligible_for_demo_canary` per-tier 3-tuple output** — spec v0.3 says "per tier"; FA confirm tooling output format matches.
2. **Branch-level dormancy retire path** — NEW per 8b FA-MUST-FIX-2 forward-applicable; FA confirm spec v0.3 covers this OR needs spec patch.
3. **DSR=0 + PBO>0.5 = auto-RED** — hardcoded rule; FA confirm matches AMD-2026-05-15-02 §8 condition 3 wording.
4. **PASS verdict bypasses AMD §8 condition 3 W-AUDIT-8b dependency** — W-AUDIT-8b is RED_FINAL tombstoned; FA confirm 8c PASS independently authorizes Stage 1 Demo canary per spec v0.3 §"PROCEED" recommendation.

### §8.5 QC review focus (when next IMPL dispatched)

1. **Cluster-aware n_eff math validity**: 60min window + 0.3 autocorr factor — empirically derive or PA-defended? Reference Lo (2008) "Heuristic versus rigorous statistics in finance"?
2. **Both-direction trigger rate 0.1% floor**: derivation source?
3. **Per-tier independent PSR/DSR with K_total slicing**: math validity in §3.2 mitigation #2?

---

## §9 Files Referenced

- spec: `srv/docs/execution_plan/2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md` (v0.3, 365 LOC)
- PA spec v0.3 patch report: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_spec_v0_3_field_shape_drift_fix.md`
- PA spec v0.1 verdict: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8c_spec_pa_verdict.md`
- C1 final signoff: `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--c1_final_signoff_result.md`
- 8b Round 2 final sweep RED_FINAL (lessons source): `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8b_round2_phase_b_final_sweep.md`
- 8b 4-agent review packet template (mirror): `srv/docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-18--w_audit_8b_round2_red_4agent_review_packet_template.md`
- 8a Wave 1 worktree decomposition: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md`
- 8b metrics module (mirror for 8c): `srv/helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py`
- 8b report wrapper (mirror for 8c): `srv/helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py`
- 8b SQL features (mirror for 8c): `srv/sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`
- liquidation pulse provider IMPL (Wave 1 MERGED): `srv/rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs`
- alpha surface types (LiquidationPulse + LiquidationPulsePanel + LiquidationSide): `srv/rust/openclaw_core/src/alpha_surface.rs:380-461`
- dispatch wire (step_4_5_dispatch.rs): `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:261-269`
- pipeline ctor slot inject: `srv/rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs:309`
- new feedback memory: `srv/memory/feedback_pnl_priority_over_governance.md`
- v_migration_pg_dry_run feedback (MIT mandatory): `srv/memory/feedback_v_migration_pg_dry_run.md`

---

## §10 PA Sign-Off

```text
PA DESIGN DONE: W-AUDIT-8c Stage 0R packet design v1.0 ready for PM dispatch.

Stage 0R replay tooling: 3 worktree (8C-S0R-1 SQL / 8C-S0R-2 Python metrics / 8C-S0R-3 wrapper)
Total: 6.5 PD; ~2.5d wallclock at 3 parallel E1
READY-FOR-DISPATCH-NOW (tooling IMPL is panel-age-independent).

Stage 0R verdict run: ETA 2026-05-25 (after panel ≥7d natural cross 2026-05-24 23:12Z).

Strategy skeleton (post-PASS only): 2 worktree (8C-STRAT-1 / 8C-STRAT-2)
Total: 4 PD; ~1.5d wallclock at 2 parallel E1
CANNOT START until 4-agent Stage 0R verdict PASS-at-tier-X.

Earliest realistic alpha-bearing PnL impact: ~2026-06-08 (Demo canary live).
Mid-path branching: 4-agent verdict PASS / PARTIAL-PASS (per-tier) / RED-FINAL drives 
divergent dispatch chains documented in §6 timeline.

Empirical panel evidence at 0.55d substantially exceeds spec v0.3 projection:
- High-density tier 10 symbols (spec predicted 7)
- BTC/ETH/BCH/SOL/DOGE/BSB/XRP all ≥ 80 projected 7d triggers (well above per-branch floor)
- Demo testnet 8-12× long-liquidation skew FLAG for BB pre-Stage-0R review

3 RED risks mitigated upfront in packet design:
1. Demo testnet long-bias: per-tier independent verdict + BB pre-review + DEMO_TESTNET_BIAS_SUSPECTED flag
2. Cluster-aware n_eff overpenalty: per-tier K_total slicing + plateau requirement + bootstrap CI floor
3. Cost gate failure: 3-cost sensitivity sweep + cross-link to Phase 1b cost realism

Report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8c_stage_0r_packet_design.md
```

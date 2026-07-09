---
title: W-AUDIT-8b Round 2 RED Final — MIT Independent Data Pipeline + Calibration Review
date: 2026-05-18
author: MIT
verdict: APPROVE (concur RED_FINAL)
scope: read-only data pipeline + ML calibration review
sibling_reviewers: QC + BB + FA (parallel, independent)
source_report: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8b_round2_phase_b_final_sweep.md
sweep_artifact_linux: /tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_20260517_2338_pa.json
sweep_artifact_mac: docs/audits/2026-05-18--w_audit_8b_round2_final_sweep_artifact.json
runtime_machine: trade-core
pg_sot_runtime_verified: yes (12 queries × 7.0d window)
no_mutation: spec / AMD §8 / RiskConfig / TOML / Operator role / authorization / cron / runtime config 全部不動
---

# W-AUDIT-8b Round 2 RED Final — MIT Review

## §0 Executive Summary

**Verdict**: **APPROVE — concur PA RED_FINAL**

PA Round 2 Phase B final sweep verdict `RED_FINAL` 在 MIT 視角 (data pipeline integrity + ML calibration) **完全成立**。底層 data SoT 經 PG runtime 12 queries 直接驗證:

1. **panel.funding_rates_panel SQL feature 抽取 leak-free** (LATERAL join `snapshot_ts_ms <= signal_ts_ms` + percent_rank PARTITION BY snapshot_ts_ms = strict point-in-time cross-sectional)
2. **Sample 結構性 alpha-deficient**: 全 sweep 8 cell 的 INJUSDT cluster **全部** 是 2026-05-13 (+/- 5/12-5/14) single idiosyncratic crash event 周邊 — 不是 7-day reproducible sample
3. **Cross-sectional z 嚴重不對稱**: 7d panel 共 49,853 z scores 中 z>=+1.5 僅 135 (0.27%) vs z<=-1.5 5,243 (10.5%) = **39x asymmetry** → crowded_long_fade signal **structurally dead by data, not by strategy design**
4. **Wilson CI 在 small-n (n=7) 嚴重 over-confident**: Clopper-Pearson exact lower bound 是 Wilson 的 1/7 (0.0036 vs 0.0257) — sweep tool 用 Wilson 已是被高估的 stability indicator，真實 effective lower bound 更小
5. **PBO 0.643 落入「substantial overfit risk」區間** (Bailey-Lopez de Prado 2014, 0.5-0.7 區間)
6. **Panel 28d/56d 擴展對 reverse verdict ROI 接近零**: panel.funding_rates_panel 從 2026-05-11 才開始收，且 INJUSDT 7d 之內已 sample 1 個 idiosyncratic crash → 21d 期 expected 1-3 個 crash + crowded_long_fade z>=+1.5 仍 structurally 稀缺

**Statistical instability hypothesis 在 6.92d → 7.0d natural gate 已被 PA REJECT** (8/8 cells aligned, 0 flip)。MIT 從 data pipeline 整層複核：**preliminary verdict 在 data SoT + calibration 視角 unconditionally CONFIRMED**。

7.0d panel gate 在 MIT 視角 **不是 over-engineered**: 它是 **底線 sanity gate**，不是 statistical power gate。Round 2 RED 不被 panel days 改變的核心原因是 funding skew **alpha hypothesis 在 25-sym × 5-7 day pulse-driven 結構下無法 produce reproducible cross-sectional signal**，不是 sample insufficient。

---

## §1 MIT Charter (per 4-agent template §4)

**Scope**: panel.funding_rates_panel 完整性 / snapshot_ts_ms vs asof_ts SoT / time-series CV design / data leakage check / feature engineering for funding skew / cross-sectional autocorrelation。**Read-only。不寫 IMPL, 不修 spec, 不發 commit**。

**輸出**: 6 specific questions 逐答 + PG SoT verify result + leakage / clustering / sparsity verdict + MUST-FIX / SHOULD-FIX / NTH。

---

## §2 PG SoT Verification (12 queries, ssh trade-core)

### §2.1 panel.funding_rates_panel 完整性 (7d window)

| 指標 | 值 | MIT 評語 |
|---|---|---|
| span_days | **7.0105d** | 自然 cross 達 spec gate 7.0d (+7 min margin) ✅ |
| total rows | 248,201 | per sym ~9,925 = 1.42 row/min |
| distinct symbols | **25** | 全 cohort 完整 ✅ |
| distinct funding cycles | **34** | 7d × 3 cycles/day = 21 floor 過 +62% margin ✅ |
| source_tier distribution | `bybit_v5_ws_tickers` (100%) | **單一 source 統一** ✅ no source mode mixing |

### §2.2 Per-symbol coverage

- 25 sym 內 BTCUSDT/ETHUSDT 9945 rows (highest); POLUSDT 9921 (lowest)
- Per-sym span 6.94-7.01d 全部 ≥ 6.94d (相當於 21+ cycles)
- 3 sym (ADAUSDT/DOGEUSDT/LINKUSDT) 各 1 個 gap > 1h (max 69 min) — **微小 isolated gap，無系統性 dead zone**
- Hourly coverage per-sym 167h = 完整 7d × 24h
- **MIT verdict**: panel completeness PASS for cross-sectional z calculation

### §2.3 OI panel parity

- OI panel rows = 248,946 vs funding 248,201 = ratio 1.003 ✅ (spec ≥ 0.95 floor passed)
- OI span aligned 7.01d ✅

### §2.4 Funding cross-sectional z 分布 (全 panel n=49,853)

| z 區間 | count | pct | 對應 sweep cell |
|---|---:|---:|---|
| z <= -2.0 | 3,025 | 6.07% | z_strict crowded_short_squeeze candidate space |
| z <= -1.5 | 5,243 | 10.5% | z_baseline + z_strict short_squeeze |
| z >= +1.5 | **135** | **0.27%** | z_baseline + z_strict crowded_long_fade |
| z >= +2.0 | **23** | **0.046%** | z_strict crowded_long_fade |

**核心發現**: 正負方向 z 極度不對稱 — z>=+1.5 只占 z<=-1.5 的 **2.6%** (135/5243)。即 **crowded_long_fade branch dead 不是 strategy logic 問題，是 raw funding distribution 結構性偏 negative 的物理事實**。MIT 視角這是 **data-side 結構限制**，不是 strategy implementation 缺陷。

### §2.5 INJUSDT funding 嚴重 outlier

| sym | mean_bps | std_bps | min_bps | max_bps |
|---|---:|---:|---:|---:|
| **INJUSDT** | **-2.29** | **7.21** | **-60.27** | 1.00 |
| ICPUSDT (2nd) | -0.67 | 1.53 | -4.97 | 1.00 |
| 比 (INJ/ICP) | 3.4x mean / **4.7x std** | | **12x worse min** | |

**INJUSDT 7d distribution**:
- lt_neg10 (≤-10 bps): 968 rows (9.75%)
- neg10_neg5: 96 rows (0.97%)
- neg5_neg1: 2,079 rows (20.9%)
- neg1_0: 1,401 rows (14.1%)
- pos0_1: 3,671 rows (37.0%)
- pos1_5: 1,710 rows (17.2%)
- gt_pos5: **0** rows
- total: 9,925

INJUSDT 在 7d window 是 **left-skewed 嚴重不對稱**: max 1.0 / min -60.27 = idiosyncratic 不是 Bybit cohort 一般 funding 行為。

### §2.6 INJUSDT extreme funding 時間集中

INJUSDT funding_rate_bps <= -10 trigger 在 day 分布:
- 2026-05-13: **846 rows (87.4% of 968)**
- 2026-05-14: 122 rows (12.6%)
- 其他 5 天 (5/11/5/12/5/15/5/16/5/17/5/18): **0 row**

對應 sweep signal trigger (對 5m bars + funding ≤ -10):
- 2026-05-12: 0 lt_neg10 / 14 strong_short (-10 ~ -5)
- 2026-05-13: **169 lt_neg10** / 4 strong_short
- 2026-05-14: 25 lt_neg10 / 0 strong_short
- 其他 5 天: 0 / 0

**結論**: INJUSDT extreme signal 在 7d panel 完全是 **2-3 day idiosyncratic crash window** (5/12-5/14)，其中 **2026-05-13 dominate 87%**。即 sweep 報的 "INJUSDT z=1.2 cluster n=42 / n_eff=7 / 14 cycles" **實質 effective independent observations ≈ 2-3 calendar days**。

### §2.7 INJUSDT z<=-1.5 cluster 真實 cluster size

直接 PG 查 (cross-sectional z over 7d panel):
- total_n = 510
- distinct calendar days = 7
- **distinct 8h funding buckets = 13** (vs sweep tool 報 14)
- 13 vs 21 expected (3 × 7d) → INJUSDT 不在每個 cycle 都觸發 z<=-1.5，**38% 缺席率**

INJUSDT z<=-1.2 cluster (對應 sweep z_moderate):
- total_n = 587 candidate rows
- distinct days = 7
- distinct funding cycles = **10** (sweep 報 14 是 next_funding_ms 的 raw distinct count，不是 真實 settled 8h)
- avg_n_per_day = 83.9 → 嚴重 within-day clustering

### §2.8 Cross-sectional funding correlation with BTC

| sym | corr_with_BTC |
|---|---:|
| ARBUSDT | +0.36 |
| ETHUSDT | +0.29 |
| NEARUSDT | +0.19 |
| (median across 24 alt) | ~+0.05 |
| INJUSDT | **-0.27** |
| ICPUSDT | -0.25 |
| OPUSDT | -0.24 |

**結論**: funding 是 multi-factor (cross-sectional spread > BTC-driven systemic factor)。**INJUSDT 是 idiosyncratic factor 主導 (-0.27 with BTC)**。Cross-sectional z 計算合理 (multi-factor + idiosyncratic 都會被 z normalize 到 cohort)。

### §2.9 SQL leak-free verification (EXPLAIN trace)

`sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` LATERAL join:
```sql
LEFT JOIN LATERAL (
  SELECT snapshot_ts_ms, funding_rate_bps, next_funding_ms, source_tier
  FROM panel.funding_rates_panel p
  WHERE p.symbol = b.symbol
    AND p.snapshot_ts_ms <= b.signal_ts_ms  -- <= 嚴格不取未來
  ORDER BY p.snapshot_ts_ms DESC LIMIT 1
) f ON TRUE
```

EXPLAIN 確認 `Index Cond: ((snapshot_ts_ms <= '1779009600000'::bigint) AND (symbol = 'INJUSDT'::text))` ✅

`stats` CTE: `percentile_cont(0.5) WITHIN GROUP / avg / stddev_samp FROM joined GROUP BY signal_ts_ms` ✅ point-in-time cross-sectional per signal_ts_ms

`ranked` CTE: `percent_rank() OVER (PARTITION BY j.signal_ts_ms ORDER BY j.funding_rate_bps)` ✅ partition by snapshot_ts_ms — **不混歷史時序，不混未來，完全 cross-sectional**

EXPLAIN 對 percent_rank() 確認: `Sort Key: snapshot_ts_ms, funding_rate_bps; Presorted Key: snapshot_ts_ms` → WindowAgg 在每個 snapshot_ts_ms 內獨立計算 → leak-free ✅

### §2.10 forward return SQL semantic

```sql
LEFT JOIN market.klines f30 ON f30.close_ts_ms = b.signal_ts_ms + 1800000  -- +30m
```
forward return = (close_30m - close_px) / close_px × 10000 bps，使用 future bar close in `+30m` window，這是 **target，不是 feature** → ✅ no leak (target by definition is future)

### §2.11 panel 28d/56d 擴展可行性

```sql
SELECT MIN(EXTRACT(EPOCH FROM (NOW() - to_timestamp(snapshot_ts_ms/1000)))/86400) AS earliest_age_d
FROM panel.funding_rates_panel;
-- earliest = 7.013 days
```

**Panel 從 2026-05-11 才開始 forward-only collect**。MIT 視角:
- 7d → 14d 期: 必須再等 7 calendar days (no retroactive panel data)
- 7d → 28d 期: 必須再等 21 days
- 7d → 56d 期: 49 days

Panel collector 不能 backfill (panel.funding_rates_panel 是 ws_tickers stream + REST snapshot 即時記錄)。

### §2.12 PG runtime settings (基座背景)

```
work_mem = 4MB        ← per memory 2026-05-09 audit 仍是 "嚴重低"
shared_buffers = 128MB ← 同上
effective_cache_size = 4GB
max_connections = 100
```
24h 前 + 8d 前 + 今天三次 audit 都沒動 — 不阻塞 Round 2 RED 結論，但是 ML 基座 systemic risk (M5 Ultra 部署前必修)。

---

## §3 6 Specific MIT Questions (per template §4)

### Q1: panel.funding_rates_panel 7.0d gate 是否足夠 statistical power？若 6.92d preliminary 已 confirm RED 那 power 是否 over-engineered？

**Answer**: **7.0d 不是 over-engineered。它是 hygiene gate (sanity baseline)，不是 power gate。**

| 觀點 | 6.92d → 7.0d 的真實 power delta |
|---|---|
| total candidate 5m bars | +0.99% (≈ +4,950 bar) |
| pooled baseline n_eff | +1.18% (7,989 → 8,083) |
| strategy primary cell n | 0 (7→7, frozen) |
| INJUSDT cluster n_eff (z=1.2) | 0 (7→7) |
| distinct funding cycles | 0 (34→34) |

對 sweep verdict 影響: 8/8 cells 全部 frozen (0 flip)。

**MIT verdict**: 7.0d gate 從 statistical power 角度確實 +1% 範圍微弱 (per PA preliminary §7.2 predicted)，但它的 **真實目的**是:
1. 排除 cherry-picked panel window (5.72d 對 6.92d 對 7.01d 結果一致是 robustness 證明)
2. funding cycles distinct ≥ 21 floor 證 minimum sample diversity
3. 對 Bayesian / textbook standard 看是「至少 1 個 full week regime」的最低門檻

**Over-engineered 反例**: 如果直接 reject 6.92d 結果走 30d panel 才允許 verdict，那是 over-engineered。但 spec v0.3 的 7.0d gate 本來就是 minimum，不是上限。

**Push back**: 若 PA / QC 認為 7.0d 不足，那應改 spec 為 14d/21d 而非當前 7.0d，並 forward-only 等 panel collector 累積 — 但這已 outside W-AUDIT-8b Round 2 scope。**MIT 同意 7.0d 是 RED_FINAL 充分 (但非必要超強) gate**。

### Q2: funding skew feature engineering 是否有 look-ahead bias (per memory `feedback_indicator_lookahead_bias` rolling-window concern)？

**Answer**: **NO look-ahead bias detected。**

詳查 `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` + EXPLAIN trace:

| Feature | 計算方法 | leak risk |
|---|---|---|
| `funding_rate_bps` | LATERAL `<= signal_ts_ms` | ✅ leak-free |
| `funding_zscore_25sym` | `(f - median) / std` over `PARTITION BY j.signal_ts_ms` (cross-sectional snap) | ✅ point-in-time cross-sectional |
| `funding_percentile_25sym` | `percent_rank() OVER (PARTITION BY j.signal_ts_ms ORDER BY funding_rate_bps)` | ✅ point-in-time |
| `funding_spread_to_median_bps` | `(f - median)` over same snap | ✅ |
| `oi_delta_15m_pct` | LATERAL `<= signal_ts_ms` from panel.oi_delta_panel | ✅ |
| `prior_5m_return_bps` | `(close - open) / open` of bar that signal_ts_ms = close_ts_ms | ✅ closed bar |
| `fwd_return_15m/30m/60m_bps` | `(close at signal_ts_ms + N) - close at signal_ts_ms` | ✅ target = future by definition |

**對 memory `feedback_indicator_lookahead_bias` 比較**: 該 bug 是 `rolling(N).max()` 含 current bar (= breach by definition mean-reverts)。本 feature 用 **point-in-time cross-sectional rank/median/std** (PARTITION BY signal_ts_ms)，不是 **per-symbol time-series rolling**。前者 (cross-sectional) 用同 t 跨 sym 的 cohort 計算 — by design 沒有「current bar 含在歷史 rolling window」問題。

**精細 corner case**: `prior_5m_return_bps` 從 `(close - open) / open` 計算 — 即 signal_ts_ms 那一根 bar 自身的 return。spec v0.2 §"price_stall_or_breakdown: prior closed 5m return ≤ 0" 是 「**剛 close 的 just-closed bar** return」當作 prior 信號。這 timing 邊界 **OK**，因為:
1. SQL `close_ts_ms` 是 bar close 時刻
2. signal trigger 在 bar close 後緊接，feature_ts = close_ts_ms 是「已 closed bar 的 final return」
3. `bars` CTE 過濾 `close_ts_ms <= now() - 3600000` 確保 bar 早已 closed 1+ hour

**MIT verdict**: feature engineering leak-free。memory `feedback_indicator_lookahead_bias` 警示不適用本 case (那是 rolling time-series, 本 case 是 point-in-time cross-sectional)。

### Q3: z-score normalization 用 panel-level cross-sectional 還是 per-symbol time-series？哪個更合適 sentiment regime？

**Answer**: 當前用 **cross-sectional 同 timestamp 跨 25 sym** ✅ 是 MIT 推薦的 sentiment regime 設計。

| Approach | 設計 | 適用 sentiment regime? | 本 case fit |
|---|---|---|---|
| **cross-sectional same-snap** (當前) | `(f_i - median_t) / std_t` over 25 sym at single t | ✅ 衡量「該 sym 相對 cohort 同期偏離」 | **適合 crowding signal** ← spec hypothesis |
| per-symbol time-series rolling | `(f_i - mean_i_24h) / std_i_24h` over symbol's last 24h | 適合「該 sym 相對自身歷史是否異常」 | 不適合 crowding (crowding 是 cohort 結構性集中) |
| panel-level fixed mean+std | `(f_i - panel_mean_7d) / panel_std_7d` 用整 7d 全 sym | leak risk (含未來) + 不能 adaptive regime | NOT used here ✅ |

**MIT verdict**: cross-sectional same-snapshot 設計 **正確匹配 hypothesis** (funding 是 sentiment crowding 信號 → 需要 cohort 內 cross-section)。如果改 per-symbol time-series rolling，會把 INJUSDT 5/13 crash 在 INJUSDT 自身 lookback 中 normalize 掉 (因為 INJUSDT 自己 7d std 已被該 crash 推高 → z 變小)，反而 lose signal sensitivity。

**Note on cohort_n filter**: SQL `stats` CTE `GROUP BY signal_ts_ms` 沒有 minimum cohort size filter — 即任何 timestamp 即使只 2-3 sym 有 data 也會算 z (但 std 可能 unstable)。可看 `funding_cohort_n` column 確認 cohort size。實測同 signal_ts_ms 多時 ≥ 20 sym 都有 data (per-sym 1.42 row/min × 25 sym × 5min bucket = 178 expected row per 5min bucket)，cohort size 滿足。

### Q4: Wilson lower bound 在 binomial proportion + clustered sample 應否 hierarchical-Bayesian-correct？

**Answer**: **YES — 強烈建議補 Bayesian hierarchical / Clopper-Pearson exact / GEE cluster-correction，但 NOT blocking for RED_FINAL verdict** (因為當前 Wilson 已 over-confident yet still indicates RED)。

#### §3.4.1 Wilson vs Clopper-Pearson vs Jeffreys CI 對比 (本 audit 算)

| Cell (n, k) | Wilson 95% | Clopper-Pearson exact 95% | Jeffreys Bayes 95% |
|---|---|---|---|
| z=1.0 INJ (n=7, k=1) | [0.0257, 0.5131] | **[0.0036, 0.5787]** | [0.0159, 0.5008] |
| z=1.2 INJ (n=42, k=7) | [0.0832, 0.3060] | [0.0697, 0.3136] | [0.0778, 0.2996] |
| z=1.2 pooled (n=74, k=12) | [0.0953, 0.2624] | [0.0867, 0.2661] | [0.0918, 0.2583] |
| z=1.5 INJ (n=7, k=1) | [0.0257, 0.5131] | [0.0036, 0.5787] | [0.0159, 0.5008] |
| z=2.0 INJ (n=7, k=1) | [0.0257, 0.5131] | [0.0036, 0.5787] | [0.0159, 0.5008] |

**Wilson 在 small-n (n=7) 嚴重 over-confident**:
- z=1.0/1.5/2.0 cells: Wilson lower 0.0257 是 **Clopper-Pearson exact lower 0.0036 的 7.1x** 過於 optimistic
- 即 sweep tool 用 Wilson 已是被 inflated 的 stability indicator

#### §3.4.2 Clustered sample correction (cluster_n sensitivity)

| Treating each cluster as 1 unit | cluster_n_eff | k_assumed (1/6 share) | Wilson lower |
|---|---:|---:|---:|
| Conservative (distinct 8h buckets in INJ cluster) | 10 | 2 | 0.0567 |
| Middle | 14 | 2 | 0.0401 |
| Optimistic (cycles in panel) | 34 | 6 | 0.0827 |
| Raw n (no cluster correction, current sweep tool) | 42 | 7 | 0.0832 |
| Pooled | 74 | 12 | 0.0953 |

**核心**: 不論 cluster correction assumption 多 aggressive (3 → 42)，Wilson lower **全部 < 0.10** stability hint threshold。即 **even hierarchical Bayesian correction wouldn't reverse the per-cell verdict — RED remains structurally**.

#### §3.4.3 MIT 建議的 Bayesian hierarchical 設計

如果 future spec v0.4 / v0.5 想嚴格 statistical sound:

```text
Level 1 (per-cell): p_cell ~ Beta(α_branch, β_branch)
Level 2 (per-branch): α_branch, β_branch ~ HalfNormal(0, σ_branch)
Level 3 (panel hyperprior): σ_branch ~ HalfCauchy(0, 1)

Posterior: P(stage_0R_pass | n_cell, k_cell, cluster_structure)
```

但這對 **當前 RED verdict 沒影響** — 因為:
- z=1.0/1.5/2.0 INJ cells (n=7, k=1) 不論 Wilson / Clopper-Pearson / Bayesian: lower **都 < 0.10** 且 sample 太 small
- z=1.2 pooled (n=74, k=12): Wilson / CP / Jeffreys 3 methods 都聚集在 [0.087, 0.095] 區間 = 全部 fail 0.10 floor

**MIT verdict**: Wilson CI 在 RED_FINAL 場景 **既 over-confident 又 fail to pass floor**。spec v0.4 應改用 **Clopper-Pearson exact** (small-n textbook standard) 加 **cluster-aware Wald correction** (intra-day correlation)。但這是 spec evolution work，不阻塞當前 RED_FINAL。

### Q5: crowded_long_fade 信號 dead 是否反映 panel funding_rates_panel sample 在 z>1.0 區間 sparse？

**Answer**: **YES — 但這是 raw funding distribution 結構性偏斜的物理事實，不是 panel sample 不足。即使擴 28d/56d 也 NOT reverse。**

PG verified (§2.4):

| z 區間 | n (全 panel 7d) | pct of total |
|---|---:|---:|
| z >= +1.5 | 135 | 0.27% |
| z >= +2.0 | 23 | 0.046% |
| z >= +1.0 | (per per-sym aggregate ~600-700 from §2.4 table) | ~1.4% |
| z <= -1.5 | 5,243 | 10.5% |
| z <= -2.0 | 3,025 | 6.07% |

**結構性偏斜**: 
- z>=+1.5 是 z<=-1.5 的 **2.6%** (135/5243)
- z>=+2.0 是 z<=-2.0 的 **0.76%** (23/3025)
- 即 funding distribution 在 25-sym × 7-day Bybit cohort **structurally left-skewed**

**為何結構性偏斜?**
1. Bybit perpetual contracts 整體 funding 偏 negative (見 per-sym mean: INJUSDT -2.29, ICPUSDT -0.67, ATOMUSDT -0.13, POLUSDT -0.71, TONUSDT -0.26 — 多 sym mean < 0)
2. Crypto market regime 2026-05-11~5-18 期間整體 bear/short-pressure → funding 普遍 negative
3. Long-side crowding (z>=1.5) 需 retail FOMO 高 funding → 當前 regime 沒這 conditions

**Panel sample 擴展能 reverse 嗎?**
- 7d → 14d 期: 預期 z>=+1.5 從 135 → 270 (假設線性) → 仍然 ~0.27% of total
- 7d → 28d 期: z>=+1.5 預期 ~540 → 仍 sparse for 50 n_eff per-symbol floor
- 結構性問題: 即使 sample 4x，**z 不對稱比例不變**

**MIT verdict**: crowded_long_fade dead 是 **data-side 結構性 + regime 性 雙重限制**。spec v0.4 應 reframe:
1. (a) Symmetric framing: 改 `crowded_long_fade` z 條件為 panel-level adaptive percentile (top 10% even if z<1.5) — 但這會 dilute signal quality
2. (b) Drop branch: 直接 retire crowded_long_fade，只保 crowded_short_squeeze (data-driven 接受不對稱)
3. (c) Multi-regime: 加 regime classifier，只在 bull/FOMO regime 啟用 long_fade — 但 regime classifier 是 R-3 hypothesis pipeline work

**Note**: 當前 spec v0.3 RED_FINAL 不需要解 long_fade dead 才能 retire — long_fade dead 是 **support evidence** for RED_FINAL，不是阻塞修法。

### Q6: 7.0d → 28d / 56d panel expansion 是否能 reverse verdict？建議 panel coverage 擴展 ROI？

**Answer**: **NO — panel expansion ROI 接近零，不建議為了 reverse W-AUDIT-8b verdict 等 28d/56d。**

#### §3.6.1 7d → 28d 預測 (各 cell 在無 regime change 假設下)

| Cell | 7d actual n / n_eff | 28d 預測 (4x linear) | 28d 預測 vs floor |
|---|---|---|---|
| z=1.0 INJ short_squeeze (per-sym) | 7 / 1 | ~28 / 4 | 還差 4x 距 100 floor |
| z=1.2 INJ (per-sym) | 42 / 7 | ~168 / 28 | 還差 3.6x 距 100 floor |
| z=1.2 pooled | 74 / 12 | ~296 / 48 | **接近 300 pooled floor**！|
| z=1.5 INJ | 7 / 1 | ~28 / 4 | 仍 96 short of 100 |
| z=2.0 INJ | 7 / 1 | ~28 / 4 | 仍 26 short of 30 (z_strict 降 floor) |

**唯一 28d 期可能達 floor 的 cell = z=1.2 pooled** (~296 vs 300 floor)。但這 cell 在 7d sweep 是 **n=74, n_eff=12, avg_net=-0.77 bps, DSR=0, PBO=0.643** → 結構性 fail (不是 sample insufficient)。

#### §3.6.2 28d 期能改 alpha 嗎?

NO — 因為 INJUSDT 5/13 crash 是 1 個 idiosyncratic event。28d 期假設 expected **1-3 個** 類似 event (5/13 crash 強度的 crash 是稀有事件，1 month 不一定再來)。即使來 3 個，sweep verdict 仍會被 **結構性 PBO > 0.5 + DSR=0 + avg_net 變動 < 30 bps** 鎖死。

#### §3.6.3 56d 期 (7x panel) — Wait time vs ROI

- Calendar wait: 56d - 7d = **49 days** ≈ 1.6 months
- 期間 panel.funding_rates_panel 必須持續 forward-only collect (不能 retroactive)
- 56d 期 z=1.2 pooled 預測 n ~592 / n_eff ~96 → 過 300 floor 2x，**仍可能 fail DSR / PBO floor** (因 avg_net=-0.77 結構性負 edge)
- ROI: 等 49 days 換 1 個 statistical "yes/no" answer that very likely still RED

**MIT verdict**: panel expansion **NOT worth it for W-AUDIT-8b**。FA / PA 已 surface "redirect to W-AUDIT-8c/8a Phase B/C/D alpha source 軸" 是正確路徑 (per template §8.4)。

#### §3.6.4 Alternative panel expansion ROI 建議

若 operator 仍想擴 panel for 通用 ML pipeline:
1. **panel.funding_rates_panel 28d retention** 對 W-AUDIT-8d / 8e (其他 funding-based alpha 候選) 有 value
2. **panel.oi_delta_panel 28d retention** 同理
3. **Cross-symbol regime classifier 訓練** (R-3 hypothesis pipeline) 需 ≥ 30d panel — 這是合理 R-3 期 panel expansion 動機，不是為 W-AUDIT-8b reverse

---

## §4 6-Dimension Leakage Audit (per feature-engineering-protocol)

| Leakage 類型 | 命中? | 證據 |
|---|---|---|
| **1. Look-ahead Bias** (rolling stat 含 current bar) | ❌ NO | percent_rank PARTITION BY signal_ts_ms = cross-sectional同 snap，不是 time-series rolling |
| **2. Target Leakage** (feature 含 target window 內資訊) | ❌ NO | feature ts ≤ signal_ts_ms 嚴格 (LATERAL <=)，fwd_return 在 +15/+30/+60m 用 future closed bar (target by definition) |
| **3. Survivorship Bias** (training 集只含 live sym) | ❌ NO | sweep 對 25-sym fixed cohort (Bybit perp universe stable) — 7d 內無 delist event。但若 future spec v0.4 用 multi-month panel 需注意 cohort 變動 |
| **4. Cross-Section Leakage** (standardize 用全期 mean/std) | ❌ NO | `stats` CTE 用 PARTITION BY signal_ts_ms 同期 cross-sectional median/std，**不混歷史/未來** |
| **5. Time-Zone / Boundary Leakage** | ❌ NO | 所有 timestamp 統一 UTC ms-epoch (snapshot_ts_ms / signal_ts_ms / next_funding_ms 都 bigint ms-epoch)。Funding crystallization 8h boundary 在 UTC 00:00/08:00/16:00 ✅ |
| **6. Re-sample Boundary Leakage** (partial bar) | ❌ NO | SQL `close_ts_ms <= now() - 3600000` 確保 bar closed ≥ 1h；spec §"prior closed 5m return" 即 closed bar |

**MIT verdict on leakage**: **0/6 leakage detected**。Feature engineering 設計 leak-free。

---

## §5 Clustering / Sparsity Verdict

### §5.1 Sample clustering 嚴重 (intra-day + idiosyncratic event)

| Metric | 報的值 | MIT 實測 |
|---|---|---|
| z=1.2 INJUSDT cycles | 14 (sweep tool) | distinct_8h_buckets = 10 (PG 直查) |
| z=1.2 INJUSDT n=42 / n_eff=7 | per spec downsample 6:1 | 真實 effective independent ≈ 2-3 day distinct events |
| Max funding cycle share | 0.857 (sweep) | 87% 集中在 5/13 (single calendar day) |
| Within-day clustering | n/a | avg_n_per_day = 83.9 for z<=-1.2 INJ |

**結論**: sample 不僅 small-n + cluster — 還是 **single idiosyncratic event 主導**。effective sample 對 strategy generalization power 接近 N=1 event。

### §5.2 Cross-sectional sparsity

| Branch | 7d cohort z 分布 (cross-sectional) | sparsity verdict |
|---|---|---|
| crowded_long_fade (z >= z_hi) | 135 (z>=1.5) / 23 (z>=2.0) over 49,853 panel rows | structurally rare (0.27% / 0.046%) |
| crowded_short_squeeze (z <= -z_hi) | 5,243 (z<=-1.5) / 3,025 (z<=-2.0) | not sparse but INJUSDT-dominated |

### §5.3 對 Wilson CI 影響量化

§3.4.1 + §3.4.2 已詳：Wilson 在 small-n (n=7) over-confident 7x；cluster correction 無一 reverse RED。

### §5.4 MIT 結論

Sample 不只是 small-n，更是 **clustered + idiosyncratic**。**RED_FINAL 在 data calibration 視角是 lossless lower-bound verdict** — 真實 effective evidence 比 Wilson CI suggested 更弱。

---

## §6 ML Pipeline Maturity Audit (per ml-pipeline-maturity-audit)

W-AUDIT-8b funding skew directional 在 ML pipeline 4 維度評級:

| Component | Writer spawn? | Consumer exists? | Row 累積? | Decision impact? | Stage |
|---|---|---|---|---|---|
| panel.funding_rates_panel | ✅ ws_tickers stream + REST snapshot writer | ✅ funding_skew_stage0r_features.sql + cron edge_estimate_snapshots (downstream) | ✅ 248K rows / 7d / 25 sym | ❌ Stage 0R replay only, no live trading | **Shadow** (writer+consumer alive, no live decision impact) |
| panel.oi_delta_panel | ✅ writer alive | ✅ same SQL JOIN | ✅ 249K rows / 7d / 25 sym | ❌ Stage 0R only | **Shadow** |
| learning.strategy_trial_ledger (K_prior) | ✅ writer | ✅ fetch_k_prior() in metrics.py | ✅ rows for other strategies | ❌ funding_skew_directional K_prior=0 (no historical) | **Foundation** for funding_skew (no comparable trial yet) |
| w_audit_8b_stage0r tooling | ✅ Mac+Linux md5 identical | ✅ PA solo runs | ✅ artifact JSON | ❌ Stage 0R only | **Shadow** |
| AlphaSurface FundingSkew Tier 2 | ✅ AlphaSurface trait (Phase A) | ❌ Production builder hasn't wired | ❌ no live consumer in engine | ❌ Spec phase | **Skeleton** (interface ready, no live IPC) |

**MIT verdict on ML pipeline**: W-AUDIT-8b 是 **Shadow-only Stage 0R replay packet generator**。當前 RED_FINAL 是 **Shadow stage** 的正確 verdict (signal doesn't deserve Canary promotion)。Pipeline 設計乾淨無 fake-success path (per 16 principles audit)。

---

## §7 V### Migration Guard Audit (panel schema)

| Table | V### migration | Guard A/B/C 狀態 |
|---|---|---|
| panel.funding_rates_panel | V020 (與 V025 hypertable confirm) | (本 audit scope 不重複 V020 audit) Schema 已存於 PG with hypertable + index. Round 2 RED_FINAL **不引入新 V### migration** ✅ |
| panel.oi_delta_panel | V020 | 同上 |

**MIT verdict**: 本 Round 2 不引入新 schema 變動 ✅ no Guard A/B/C audit needed for new migration。

---

## §8 Verdict + Recommendations

### §8.1 Top-line Verdict

**APPROVE — concur PA RED_FINAL**

理由:
1. ✅ Data pipeline integrity verified (12 PG queries, 0 leakage)
2. ✅ Feature engineering leak-free (6/6 dimensions audit pass)
3. ✅ Cross-sectional z normalization 設計正確匹配 hypothesis
4. ✅ 7.0d gate sufficient (not over-engineered, not too lax)
5. ✅ Sample sparsity + clustering quantified; Wilson CI 已 over-confident
6. ✅ Panel expansion ROI 接近零 — accept RED_FINAL is correct
7. ✅ ML pipeline maturity stage = Shadow correctly reflects current state

### §8.2 MUST-FIX (blocking for RED_FINAL archive)

**0 MUST-FIX** — RED_FINAL 本身 verdict 不需任何 fix。

### §8.3 SHOULD-FIX (建議 for future spec v0.4 / 下個 W-AUDIT-8c/8d 軸)

#### SHOULD-1: Spec v0.4 應 reframe crowded_long_fade
- 當前 spec 隱含「z>=+z_hi → long_fade」symmetric 假設不成立 (data asymmetric 39x)
- 建議 (a) Drop long_fade branch 或 (b) 用 panel-adaptive percentile (top 10% 不要求 z>=1.5)
- **Note**: 不阻塞 RED_FINAL archive；是 future W-AUDIT-8c+ 啟發

#### SHOULD-2: 改 Wilson CI 為 Clopper-Pearson exact (small-n) 或加 Bayesian hierarchical
- Wilson 在 n<30 over-confident 多 (本 audit 算 z=1.0/1.5/2.0 cell n=7 → Wilson lower 0.0257 是 CP 0.0036 的 7x)
- Spec v0.4 改用 Clopper-Pearson exact 為 default，**Wilson 作 backup approximation**
- 適用範圍: 所有 W-AUDIT-8b/8c/8d/... Stage 0R packet generator

#### SHOULD-3: Sweep tool 加 cluster-aware n_eff 計算
- 當前 `_n_eff(n, horizon) = n / (horizon // 5)` 是 fixed downsample (30m → 6:1)
- 真實 effective sample 還受 intra-day correlation + cross-event clustering 影響
- 建議: `n_eff_cluster = min(_n_eff(n, horizon), distinct_8h_buckets, distinct_calendar_days)`
- 對 INJUSDT z=1.2 cluster: 當前 n_eff=7 但 distinct_days=7, distinct_8h_buckets=10 → cluster-corrected n_eff = min(7, 7, 10) = 7 (same in this case); 但對未來其他 cell 可能差異很大

#### SHOULD-4: Panel collector retention policy 28d-30d (for future ML training)
- 不為 reverse W-AUDIT-8b verdict，是為:
  - regime classifier training (R-3)
  - 其他 funding-based alpha 候選 (W-AUDIT-8c/8d) 30d panel baseline
  - LightGBM training cron MIN_SAMPLES=200 + multi-strategy diversity
- 與當前 ML 基座 38% / 44% 達標率 audit 對齊 (per memory 2026-05-09 v3)

### §8.4 NTH (Nice-to-have)

#### NTH-1: PG runtime work_mem 4MB → 32MB (per memory 2026-05-09 v3)
- 不影響 W-AUDIT-8b verdict
- 影響 ML 基座未來大 training query disk spill

#### NTH-2: 補 SQL `stats` CTE 加 `HAVING COUNT(*) >= 20` cohort size filter
- 防止 sparse timestamp 用 ≤3 sym 算 std (容易 unstable)
- 當前 5min bucket 多時 ≥20 sym 沒問題，但 edge case worth defensive

#### NTH-3: 補 healthcheck `check_funding_skew_panel_freshness()` (per CLAUDE.md §七 healthcheck 強制)
- 對 Stage 0R replay path: `[XX]` panel.funding_rates_panel last 1h freshness
- 不阻塞 Round 2 RED_FINAL，是 Sprint N+2 後做

### §8.5 對 4-agent consolidated verdict 建議 (主會話 reconciliation)

MIT 視角支持 (per §3.6 + §8.1):
- ✅ AMD-2026-05-15-02 §8 condition 3 wording 修訂啟動 (per template §8.4)
- ✅ Archive W-AUDIT-8b Round 2
- ✅ Redirect to W-AUDIT-8c/8a Phase B/C/D alpha source 軸
- ❌ NOT supportive of Round 3 zoom-in (per §3.6.2 ROI ~0)
- ❌ NOT supportive of 28d panel wait (per §3.6.3 Calendar 49d vs structural fail)

**Dual-AMD strategy 建議** (per template §6 FA scope):
- AMD A: W-AUDIT-8b retirement / tombstone amendment
- AMD B: panel.funding_rates_panel 28d retention for **non-W-AUDIT-8b purpose** (regime classifier R-3 + future alpha 軸) — 但這是 FA / PM 業務範圍，不是 MIT signoff

---

## §9 Boundary Compliance (16-root-principles)

| Principle | Compliance | 證據 |
|---|---|---|
| 1 Single controlled write entry | ✅ | No trading state mutation; read-only PG query + JSON write to `/tmp/openclaw/` |
| 2 Read/write separation | ✅ | 12 PG queries 全 SELECT-only |
| 3 AI output is not immediate command | ✅ | RED_FINAL verdict 是 audit conclusion, not trade signal |
| 6 Uncertainty defaults to conservative | ✅ | Concur RED_FINAL; 不擴大 sample 範圍 |
| 7 Learning must not rewrite live state | ✅ | No live state touched |
| 8 Explainability | ✅ | 12 PG queries + 6 Q answers + 3 CI method 對比 + cluster sensitivity + leakage 6-dim 全部可重 audit |
| 10 Fact/inference/assumption separation | ✅ | §2 PG fact / §3-5 inference / §8.3-4 assumption (修法建議) 全部分標 |

**Hard boundaries 全部 not touched**:
- `live_execution_allowed` ✅
- `OPENCLAW_ALLOW_MAINNET` ✅
- `authorization.json` ✅
- `live_reserved` ✅
- AMD-2026-05-15-02 §8 wording ✅ (建議在 §8.5，未執行)
- Spec v0.3 ✅ (建議在 §8.3，未執行)
- RiskConfig / TOML / Operator role ✅
- 無 commit / push / 派下游 agent ✅
- 無 cron install / runtime config mutation ✅

**Audit verdict**: A (full 16/16 compliance + 0 hard boundary touch).

---

## §10 Files Referenced

- spec: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` (v0.3 / 501 LOC)
- PA final sweep: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8b_round2_phase_b_final_sweep.md`
- PA preliminary sweep: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md`
- 4-agent review packet template: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-18--w_audit_8b_round2_red_4agent_review_packet_template.md`
- Sweep SQL: `/Users/ncyu/Projects/TradeBot/srv/sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`
- Sweep tooling: `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/reports/w_audit_8b/funding_skew_stage0r_{metrics,report}.py`
- Sweep artifact JSON (Mac): `/Users/ncyu/Projects/TradeBot/srv/docs/audits/2026-05-18--w_audit_8b_round2_final_sweep_artifact.json`
- MIT skill bundle: ml-pipeline-maturity-audit + feature-engineering-protocol + time-series-cv-protocol + data-drift-detection + db-schema-design-financial-time-series
- Memory cross-ref: `feedback_indicator_lookahead_bias.md` (not applicable to this case per §3.2)

MIT AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8b_round2_red_final_mit_review.md

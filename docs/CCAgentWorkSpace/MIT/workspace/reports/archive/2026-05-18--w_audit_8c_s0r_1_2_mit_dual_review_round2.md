---
title: W-AUDIT-8c S0R-1 + S0R-2 MIT Dual Review — Round 2
date: 2026-05-18
author: MIT
verdicts:
  S0R-1_sql_round2: APPROVE
  S0R-2_metrics_round2: APPROVE-CONDITIONAL
scope: read-only SQL + Python math review of round-2 rework (Linux PG empirical dry-run x2)
linux_pg_verified: yes (8 queries empirical, ssh trade-core docker exec; idempotency PASS)
round1_baseline: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8c_s0r_1_2_mit_dual_review.md
sources:
  - sql (round 2): origin/feature/w-audit-8c-s0r-1-sql-query-template 381d89a0
                   (3 files: features.sql 352 LOC + panel_coverage.sql 53 LOC + cluster_n_eff.sql 156 LOC)
  - metrics (round 2): origin/worktree-agent-af73a5d4575815f26 6cc2b7fb (1814 LOC, +264 from round 1)
no_mutation: SQL / metrics / spec / RiskConfig / TOML / authorization / cron / runtime / engine 全部不動
---

# W-AUDIT-8c S0R-1 + S0R-2 MIT Dual Review — Round 2

## §0 Executive Summary

E1 round-2 rework respond to MIT round-1 findings. Two updated verdicts:

- **S0R-1 (SQL query template — 3 split files)**: **APPROVE** — Linux PG x2 dry-run PASS;
  CTE structure verified (5→6 CTE: raw_buckets → density_gated → trigger_with_pct →
  trigger_candidates → forward_returns → final_signals); sentinel-split removed
  (3 independent files); PA verdict D verified (open-only entry_mid/exit_mid); CRIT-2
  sibling notional_pct_floor consistency confirmed (n_eff sample base byte-equivalent
  with main). MIT round-1 SHOULD-2 + SHOULD-3 doc fixes both landed; SHOULD-1
  caller-side `pg_typeof` guard deferred to Python (acceptable).
- **S0R-2 (`_n_eff_cluster_aware` + 19 PASS criteria — round 2 retrofit)**:
  **APPROVE-CONDITIONAL** — MIT round-1 MUST-FIX `math.ceil` landed (dormant bug fixed +
  grid-expansion-resistant); CRIT-3 cluster sliding pattern fix verified
  (`last_ts_ms` always advances; byte-equiv with SQL `lag()` semantic); 3 drift corrections
  applied (MAX_SYMBOL_SHARE 0.30 / COST_EDGE_RATIO_MAX 0.60 / FALSE_POSITIVE_RATE_MAX
  0.30); regime_annotation injected in all 4 verdict paths. **1 SHOULD-FIX (non-blocking)**:
  hardcoded `2026-05-11..2026-05-18` sample period in regime_annotation should be
  parameterized before AlphaSurface Tier-2 production wire.

**Round 2 net delta from round 1**:
- All round-1 CRIT (3 fixes) + MUST-FIX (1 fix) closed
- All 3 drift push-backs accepted
- 3 SHOULD-FIX: 2 landed (288 PRECEDING doc + LATERAL ORDER BY protection comment), 1 deferred (pg_typeof to Python)
- 1 new MIT SHOULD-FIX surfaced (regime_annotation hardcoded period)

**Ready for E4 regression**: YES (S0R-1 unconditional; S0R-2 with 1 non-blocking SHOULD-FIX noted for follow-up).

---

## §1 Scope 1 — S0R-1 SQL 3-File Linux PG Dry-Run x2

### §1.1 File Inventory (round-2 split)

| File | LOC | Purpose | Notes |
|---|---:|---|---|
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` | 352 | Main 6-CTE → trigger_candidates + forward_returns + gross/net | Adds `trigger_with_pct` intermediate CTE for percent_rank computation before `notional_pct_floor` gate |
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql` | 53 | Pre-flight cohort coverage check | Identical semantics to round 1 @SIBLING:PANEL_COVERAGE_CHECK |
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql` | 156 | Per (symbol, dominant_side) n_clusters_60m | Mirrors main gate set (incl notional_pct_floor); CRIT-2 fix |

**Sentinel-split removal**: zero `@SIBLING:` markers in any of 3 files. Three files independent. ✅

### §1.2 CTE Chain (features.sql)

```
raw_buckets (group by symbol, bucket_5m_epoch)
    → density_gated (K=3 / N_usd=10k / M=2 / dominant_side in long/short)
    → trigger_with_pct (compute side_dominance_ratio, expected_dir, percent_rank ROWS 288 PRECEDING)
    → trigger_candidates (gate side_dominance / cluster_notional_floor / notional_pct_floor)
    → forward_returns (2× LEFT JOIN LATERAL klines; ts, open only)
    → final_signals (gross_bps / net_bps / day_bucket)
```

**Why split 3a/3b**: `percent_rank()` is a window function; PG WHERE clause runs BEFORE window evaluation → can't directly filter `WHERE percent_rank() >= floor`. The split is **structurally required**; not an optimization.

**Look-ahead audit**:
- percent_rank `ROWS BETWEEN 288 PRECEDING AND CURRENT ROW` — only PRECEDING + CURRENT, no FOLLOWING → no future row leak
- `notional_pct_24h` references bucket at time T+0 (CURRENT ROW), not T+1 ✅ no look-ahead
- LATERAL joins use `ts >= bucket_end_ts + quiet + horizon` — strict forward-only ✅ no look-ahead

### §1.3 PA Verdict D (Open-Only) Verification

| Check | Round 1 baseline | Round 2 | Match? |
|---|---|---|---|
| LATERAL SELECT column | `(ts, open, close)` or `(ts, open)`? | `SELECT ts, open` (line 282, 292) | ✅ narrowed |
| Entry price | `(open+close)/2` mid | `k_entry.open::float8 AS entry_mid` (line 277) | ✅ open-only |
| Exit price | `(open+close)/2` mid | `k_exit.open::float8 AS exit_mid` (line 279) | ✅ open-only |
| Field name | new name vs preserved | preserved `entry_mid`/`exit_mid` (for downstream Python contract) | ✅ no cascade rename |

**Why preserve `_mid` semantic name with open-only impl**: round-1 dual-review §H2 verdict D verdict justified — `_compute_gross_bps()` downstream lock; rename would cascade into Python. Open-only physical semantics + preserved name is acceptable trade-off documented in SQL header line 100-110.

### §1.4 MIT Round-1 SHOULD-FIX Status

| # | Round 1 finding | Round 2 status |
|---|---|---|
| SHOULD-1 | `pg_typeof()` runtime cast guard | **DEFERRED** — no SQL header mention; caller-side Python assert recommended but not visible in SQL. Not blocking. |
| SHOULD-2 | `288 PRECEDING` semantic note insufficient | ✅ **LANDED** — lines 110, 195-196: explicit comment "sparsity 高時實際時間跨度可能 > 24h" + POLUSDT 1 trigger/day empirical bound example |
| SHOULD-3 | LATERAL `ORDER BY` early-termination protection comment | ✅ **LANDED** — lines 257-263: "MIT SHOULD-3 保護：ORDER BY ts ASC LIMIT 1 依賴 TimescaleDB ChunkAppend chunk-order-aware planner 早期終止... 請勿移除 ORDER BY" |

### §1.5 Linux PG Dry-Run Round 1 + Round 2 — All 3 Files

**Setup**: 32-sym cohort, params (window_days=7, K=3, N_usd=10000, M=2, side_dominance_floor=0.6, cluster_notional_floor_usd=10000, notional_pct_floor=0.95, quiet_window_sec=30, horizon_min=5, cost_bps=12). Trade-core `trading_postgres` container; pattern `BEGIN; EXPLAIN (ANALYZE, BUFFERS) <query>; ROLLBACK;` via psycopg2.

#### features.sql

| Round | Plan Time | Exec Time | Wall ms | Plan structure | Rows |
|---|---:|---:|---:|---|---:|
| 1 | 6.977 ms | 5.017 ms | 17.5 | Incremental Sort → 2× NLJ Left Join → WindowAgg → Sort → HashAggregate → ChunkAppend (2 chunks) | 10 |
| 2 | 6.895 ms | 4.870 ms | 15.9 | identical | 10 |

**Idempotency**: PASS — identical plan tree, identical row counts, identical filter eliminations (Rows Removed by Filter = 84, 290, etc. same both rounds).

**Round 1 baseline**: 23.759 ms (round 1 had no notional_pct_floor gate; round 1 returned 99 rows). Round 2 with stricter `notional_pct_floor=0.95` gate returns only 10 rows AND executes 4x faster (5 ms) — the extra CTE 3a adds minimal cost since `density_gated` already reduced row count substantially before percent_rank.

#### panel_coverage.sql

| Round | Plan Time | Exec Time | Wall ms | Plan structure | Rows |
|---|---:|---:|---:|---|---:|
| 1 | 1.952 ms | 2.455 ms | 7.3 | Aggregate → ConstraintAwareAppend → Merge Append → 2× Index Only Scan | 1 |
| 2 | 2.334 ms | 3.267 ms | 9.0 | identical | 1 |

**Idempotency**: PASS — identical plan; Heap Fetches differ slightly (305/759 round 1 vs 305/759 round 2 — same; VM visibility didn't degrade).

**Round 1 baseline**: 3.571 ms. Round 2 is comparable.

#### cluster_n_eff.sql

| Round | Plan Time | Exec Time | Wall ms | Plan structure | Rows |
|---|---:|---:|---:|---|---:|
| 1 | 2.443 ms | 4.788 ms | 10.4 | GroupAggregate → WindowAgg → Incremental Sort → Subquery Scan (filter on side_dominance + cluster_notional_floor + notional_pct_floor) → WindowAgg | 9 |
| 2 | 2.195 ms | 4.434 ms | 9.7 | identical | 9 |

**Idempotency**: PASS — identical plan tree; same `Rows Removed by Filter` (84 / 290).

**Round 1 baseline**: 6.729 ms (round 1 had no notional_pct_floor). Round 2 with extra gate: same 5-6 ms range — performance loss from extra filter negligible.

### §1.6 7d × 32-sym Full-Scale Extrapolation

Current panel state: 8771 liquidations rows / 33 symbols / 0.66d span.

| Metric | Current (~0.66d) | 7d projected (11x) | Acceptance |
|---|---:|---:|---|
| Raw 5m buckets | 384 | ~4,200 | — |
| After K&N&M&side_dom&floor (density_gated) | 94 | ~1,030 | — |
| After notional_pct_floor=0.95 | 10 | ~110 | very sparse; cohort needs more activity |
| features.sql exec time | 5 ms | ~55 ms (linear) | well under 30s ✅ |
| panel_coverage.sql exec time | 3 ms | ~30 ms | well under 1s ✅ |
| cluster_n_eff.sql exec time | 5 ms | ~50 ms | well under 30s ✅ |

**Acceptance #1 (main features.sql <30s on 7d × 32-sym)**: PASS ✅
**Acceptance #2 (cluster_n_eff.sql <30s)**: PASS ✅
**Acceptance #3 (panel_coverage.sql <1s)**: PASS ✅

### §1.7 Cross-Verification: n_eff Sample Base Match (main vs cluster_n_eff sibling)

Empirical run with identical params on 0.66d panel:

| (symbol, direction) | features.sql trigger_candidates | cluster_n_eff sibling n_clusters_60m | Match? |
|---|---:|---:|---|
| BCHUSDT, long_liquidated | 1 | 1 | ✅ |
| BTCUSDT, long_liquidated | 2 | 2 | ✅ |
| DOGEUSDT, long_liquidated | 1 | 1 | ✅ |
| ETHUSDT, long_liquidated | 1 | 1 | ✅ |
| LINKUSDT, long_liquidated | 1 | 1 | ✅ |
| LTCUSDT, long_liquidated | 1 | 1 | ✅ |
| SOLUSDT, long_liquidated | 1 | 1 | ✅ |
| SUIUSDT, long_liquidated | 1 | 1 | ✅ |
| XRPUSDT, long_liquidated | 1 | 1 | ✅ |
| **TOTAL** | **10** | **10** | ✅ **byte-equiv** |

**CRIT-2 sibling consistency**: at current 0.66d sample, each (symbol, direction) has 1 trigger candidate → exactly 1 cluster (60min window absorbs trivially). At larger window sizes the test will distinguish anchor vs sliding pattern; at this sparse sample they coincide. The CTE structure mirroring is exact — same `notional_pct_floor` gate applied identically in both files.

### §1.8 S0R-1 Verdict — Round 2

**APPROVE** — unconditional.

- ✅ 3 split SQL files independent (no sentinel)
- ✅ Linux PG Round 1 + Round 2 dry-run PASS (idempotent, identical plans)
- ✅ Execution time 4-17 ms (well under 30s acceptance at projected 7d × 32-sym scale)
- ✅ Schema 1:1 match (market.liquidations 5-col PK / market.klines `(symbol, timeframe, ts)` index)
- ✅ Plan healthy (low Heap Fetches, in-mem sort, parallel-per-chunk)
- ✅ PA verdict D verified (open-only entry/exit; field names preserved; LATERAL narrowed to `(ts, open)`)
- ✅ CTE 6-stage chain correct + no look-ahead
- ✅ CRIT-1 (notional_pct_floor) + CRIT-2 (sibling sync) landed
- ✅ HIGH-1 (split 3 files) + HIGH-2 (PA verdict D open-only) landed
- ✅ MIT SHOULD-2 + SHOULD-3 doc fixes landed
- ⚠️ MIT SHOULD-1 (pg_typeof guard) deferred to Python caller — acceptable, non-blocking

**Open follow-up (caller-side, not blocking S0R-1)**:
- Python caller should assert `pg_typeof(qty)=real AND pg_typeof(price)=real` once per session to detect schema drift (V### future ALTER COLUMN risk)

---

## §2 Scope 2 — S0R-2 Metrics Round 2 Retrofit

### §2.1 MIT Round-1 MUST-FIX `_n_eff_horizon_overlap` math.ceil

**File line 366-379**:

```python
def _n_eff_horizon_overlap(n: int, horizon_min: int) -> int:
    return int(n / max(1, math.ceil(horizon_min / 5)))
```

**Comment** (line 372): "MIT 2026-05-18 dual review §2.1.4 dormant bug：`horizon_min // 5` 在 horizon=6/10/14 時 floor 至 1/2/2 → 漏算 sub-5m bar overlap penalty"

**Empirical retest (Linux Python)**:

| horizon_min | round 1 (// 5) | round 2 (ceil(/5)) | Behavior |
|---:|---:|---:|---|
| 5 | n / 1 = n | n / 1 = n | unchanged (canonical) |
| 6 | n / 1 = n **BUG** | n / 2 (e.g. 10 → 5) | ✅ fixed; 20% sub-bar overlap properly penalized |
| 10 | n / 2 (e.g. 10 → 5) | n / 2 (10 → 5) | unchanged |
| 14 | n / 2 **BUG** | n / 3 (10 → 3) | ✅ fixed; was 5, now correctly 3 |
| 15 | n / 3 | n / 3 | unchanged (canonical) |
| 30 | n / 6 | n / 6 | unchanged |

**Verdict**: MUST-FIX LANDED ✅ + correctly grid-expansion-resistant for future sensitivity sweep at horizon=10/14/30.

### §2.2 8b INJUSDT z=1.2 Cross-Cycle Retest

**Reproducing MIT round-1 §2.1.5 reference**: n=42, horizon=30m. Construct 42 triggers spread across 7 days with ~2 clusters per day (3-event burst within 1h + 3-event burst 4h later).

**Empirical result (Linux Python)**:

| Component | Round 2 value | MIT round-1 expected |
|---|---:|---:|
| n_raw | 42 | 42 |
| n_eff_horizon | 7 | 7 (=42 / ceil(30/5) = 42/6) |
| distinct_days | 7 | 7 |
| distinct_60min_clusters | 14 | ~10 (round 1) |
| **n_eff_cluster** | **7** | **7** ✅ |
| penalty_rate | 83.3% | matches conservative-bias |

**Difference**: distinct_60min_clusters 14 vs round-1 "approx 10" — depends on cluster structure constructed; both binding constraints (n_eff_horizon=7, distinct_days=7) still dominate via `min()`. **n_eff_cluster = 7 unchanged** as predicted.

### §2.3 CRIT-3 Cluster Sliding Pattern Math Verification

**File line 466-471**:

```python
for t in sorted_triggers:
    key = (str(t.get("symbol") or ""), str(t.get("direction") or ""))
    ts_ms = int(t.get("signal_ts_ms") or 0)
    if last_key != key or last_ts_ms is None or (ts_ms - last_ts_ms) > window_ms:
        distinct_clusters += 1
    # 每 event 推進 last_ts_ms（包含新 cluster 開時）；SQL lag 等價。
    last_key = key
    last_ts_ms = ts_ms
```

**Critical change vs round 1**: `last_ts_ms = ts_ms` is OUTSIDE the `if` block — advances unconditionally on every event (was: only advance when new cluster).

**Empirical retest (10 events at 30min apart, window=60min)**:

| Event idx | ts_offset_min | delta from prev | last_ts_ms after | new cluster? | distinct_clusters |
|---:|---:|---:|---:|---|---:|
| 0 | 0 | n/a | 0 | yes (init) | 1 |
| 1 | 30 | 30 ≤ 60 | 30 | no | 1 |
| 2 | 60 | 30 ≤ 60 | 60 | no | 1 |
| 3 | 90 | 30 ≤ 60 | 90 | no | 1 |
| 4 | 120 | 30 ≤ 60 | 120 | no | 1 |
| 5 | 150 | 30 ≤ 60 | 150 | no | 1 |
| 6 | 180 | 30 ≤ 60 | 180 | no | 1 |
| 7 | 210 | 30 ≤ 60 | 210 | no | 1 |
| 8 | 240 | 30 ≤ 60 | 240 | no | 1 |
| 9 | 270 | 30 ≤ 60 | 270 | no | 1 |

**Empirical: distinct_clusters = 1** ✅

**Round 1 anchor pattern would have given**: distinct=4 — at event 3 (offset 90), delta vs ANCHOR (offset 0) = 90 > 60 → new cluster; then at event 5 (offset 150), delta vs new anchor (offset 90) = 60 → new cluster; etc.

**Round 2 = SQL `lag(bucket_end_ts) > 60 min` byte-equivalent**: PASS ✅

### §2.4 3 Drift Corrections (MIT round-1 push-back)

| Constant | Round 1 | Round 2 | MIT push-back? | Verified? |
|---|---:|---:|---|---|
| `MAX_DAY_SHARE` | 0.25 | 0.25 | accepted | ✅ unchanged |
| `MAX_SYMBOL_SHARE` | 0.40 | **0.30** | ✅ tightened | ✅ line 129 |
| `COST_EDGE_RATIO_MAX` | 0.80 | **0.60** | ✅ compromise (PA 0.50 ↔ original 0.80) | ✅ line 136 |
| `FALSE_POSITIVE_RATE_MAX` | 0.40 | **0.30** | ✅ tightened | ✅ line 144 |

All 3 MIT drift push-backs applied. Comments explicitly cite "MIT 2026-05-18 tightened from 0.40 / 0.80".

### §2.5 K_total 8-D Sweep Math Verification

**File line 100-109**:

```
K_GRID_CELLS_PER_SYMBOL = 11_664
11664 = len(K_GRID) × len(N_USD_GRID) × len(M_GRID) × len(FLOOR_GRID) ×
        len(PCT_GRID) × len(SIDE_DOM_GRID) × len(QUIET_GRID) ×
        len(HORIZON_GRID) × len(DIRECTION_BRANCHES)
      = 4 × 4 × 3 × 3 × 3 × 3 × 3 × 3 × 2 = 23_328 (theoretical upper bound)
Spec v0.3 uses 11_664 (single-direction count; direction branches counted separately)
```

**Math verification**:

| Axis | Size | Source |
|---|---:|---|
| K_GRID | 4 | DEFAULT_K_GRID = (2, 3, 5, 8) |
| N_USD_GRID | 4 | DEFAULT_N_USD_GRID = (5k, 10k, 25k, 50k) |
| M_GRID | 3 | DEFAULT_M_GRID = (1, 2, 3) |
| FLOOR_GRID | 3 | DEFAULT_FLOOR_GRID = (10k, 25k, 100k) |
| PCT_GRID | 3 | DEFAULT_PCT_GRID = (0.90, 0.95, 0.98) — **NEW 8th axis** |
| SIDE_DOM_GRID | 3 | DEFAULT_SIDE_DOM_GRID = (0.70, 0.80, 0.90) |
| QUIET_GRID | 3 | DEFAULT_QUIET_GRID = (0, 30, 60) |
| HORIZON_GRID | 3 | DEFAULT_HORIZON_GRID = (1, 5, 15) |

**Product (single-direction)**: 4 × 4 × 3 × 3 × 3 × 3 × 3 × 3 = **11,664** ✅

The task brief mentioned "3^8 = 6561 ≠ 11_664" — this assumption is **incorrect**. Actual grids are NOT all 3-tuples; K_GRID and N_USD_GRID are 4-tuples. The MIXED grid product yields 11_664 exactly per spec.

**K_total formula**: K_new = N_symbols × 11_664 (single-direction); with 32 symbols → 373,248 variants. DSR sr_benchmark = sqrt(2 × ln(373,248)) ≈ 5.05. Conservative ✅.

**8th axis (PCT_GRID)** new to 8c (was 7-D in round 1, sampling only 3,888 cells = 33% of search space; round 2 corrects to full 11,664 = 100% coverage per spec).

### §2.6 CRIT-2 Fail-Closed `total_bucket_count`

**File line 615-637**:

```python
if total_bucket_count is None:
    return {
        "long_passed": None, "short_passed": None, "both_passed": None,
        ...
        "fail_reason": "missing_bucket_count_denominator: caller must pass total_bucket_count "
                       "from SQL CTE 1 raw_buckets count(*) to avoid 64× anti-conservative bias",
    }
if total_bucket_count <= 0:
    return {
        "long_passed": False, "short_passed": False, "both_passed": False,
        "fail_reason": "no_buckets",
    }
```

**Pattern**: 3-state passed (True / False / None) propagating to RED verdict.

**Question from task brief**: "verify defaults raise ValueError or return RED with reason"

**Answer**: code does NOT raise ValueError — uses explicit `passed=None` + `fail_reason` string returned. This is **defensible pattern** because:
1. caller (`compute_stage0r`) checks `if not _both_direction_floor["both_passed"]` → escalates to RED verdict
2. ValueError would be harder to recover (downstream sweep loop would crash)
3. fail_reason string is machine-readable + preserved in verdict JSON for audit

**Verdict**: defensible alternative to ValueError; **CRIT-2 fail-closed pattern verified** ✅

### §2.7 Bear-Regime Annotation — Hardcoded vs Derived

**File line 1547-1569**:

```python
def _build_regime_annotation() -> dict[str, object]:
    return {
        "sample_period_start": "2026-05-11",
        "sample_period_end": "2026-05-18",
        "regime_label": "bear",
        "cross_regime_validation_required": True,
        "live_promotion_requires": "30d cross-regime sample with bull + ranging coverage",
        "rationale_source": "MIT 2026-05-18 dual review §3.3 + 8b RED_FINAL §3.5",
    }
```

**Injection points (all 4 verdict paths)**:
- Line 1211: BB demo-bias gate RED escape path → regime_annotation present
- Line 1527: main return path (PASS-BOTH / PASS-LONG-ONLY / PASS-SHORT-ONLY / RED) → regime_annotation present
- Line 1649: another verdict escape path → regime_annotation present
- Line 1768: another verdict path → regime_annotation present

**All 4 verdict paths include regime_annotation** ✅ — MIT round-1 governance MUST-FIX landed.

**Hardcoded vs derived debate**:

| Criterion | Hardcoded `2026-05-11..05-18` | Derived from triggers' min/max signal_ts_ms |
|---|---|---|
| Correctness at fixed Stage 0R replay-packet | ✅ | ✅ (would compute same dates) |
| Correctness at 14d / 30d / future expanded sample | ❌ silent staleness | ✅ |
| Function signature simplicity | ✅ no args | ❌ +2 args (sample_start, sample_end) |
| Robustness to empty triggers | ✅ always returns | ⚠️ needs fallback |
| Operator override (e.g. mark as "ranging" if regime changed) | ❌ requires code change | ✅ caller can pass `regime_label="ranging"` |

**MIT Verdict on hardcoded period**:

**APPROVE for Stage 0R replay-packet single-run** (epoch-locked 2026-05-11..05-18 panel); the function is a metadata stamp on a fixed-window replay artifact.

**SHOULD-FIX (non-blocking) for production wire**: before AlphaSurface Tier-2 live promotion, parameterize as:

```python
def _build_regime_annotation(
    sample_start: str | None = None,
    sample_end: str | None = None,
    regime_label: str = "bear",
) -> dict:
    return {
        "sample_period_start": sample_start or "2026-05-11",  # fallback
        "sample_period_end": sample_end or "2026-05-18",
        "regime_label": regime_label,
        ...
    }
```

Caller in `compute_stage0r()` derives `sample_start = datetime.fromtimestamp(min(t['signal_ts_ms'] for t in triggers)/1000, tz=UTC).strftime('%Y-%m-%d')`. Regime label still requires operator input (macro context not mechanically derivable from in-panel data at 7d sample).

**Push back severity**: SHOULD-FIX (non-blocking S0R-2 sign-off; required before Tier-2 production wire).

### §2.8 `_extract_trigger_rows` `notional_pct_floor` Filter Consistency

**File line 882, 925**:

```python
def _extract_trigger_rows(rows, *, k_event_count, n_usd, m_dominant, floor_usd,
                          notional_pct_floor, side_dom, quiet_sec, horizon_min, cost_bps):
    ...
    if notional_pct is None or notional_pct < notional_pct_floor:
        continue
```

**Match with SQL `WHERE twp.notional_pct_24h >= notional_pct_floor`**: ✅ Python and SQL filter byte-equivalent (both `>=`; both exclude None / NULL).

### §2.9 Density Floor Efficacy Empirical (Round 2)

**Linux PG empirical at current 0.66d sample, 32-sym cohort**:

| Stage | Bucket count | % retention | % rejected |
|---|---:|---:|---:|
| Raw 5m buckets | 384 | 100% | 0% |
| After K≥3 | 150 | 39.1% | 60.9% |
| After K&N (cluster_notional_5m ≥ 10k) | 94 | 24.5% | 75.5% |
| After K&N&M (dominant_event_count ≥ 2) | 94 | 24.5% | 75.5% |
| After K&N&M&side_dom&floor_usd | 94 | 24.5% | 75.5% |
| After notional_pct_floor=0.95 | 10 | 2.60% | **97.4%** |

**DENSITY_FILTER_EFFICACY_FLOOR = 0.60 (60% rejection minimum)** — **PASS** with margin (75.5% rejection before pct floor; 97.4% with).

**Note on sparsity**: 10 trigger candidates total at 0.66d sample, all long_liquidated, no short → Stage 0R PASS verdict statistically unreachable at this sample. **Expected by design** — Stage 0R replay-packet requires 7d minimum window (acceptance #6: `sample window >= 7 days`). 7d projection: ~110 candidates expected.

### §2.10 S0R-2 19 PASS Criteria — Round 2 Status

| # | Criterion | Round 1 status | Round 2 status |
|---|---|---|---|
| 1 | pooled n_eff >= 300 | ✅ APPROVE | ✅ unchanged |
| 2 | per-symbol n_eff >= 100 | ✅ APPROVE | ✅ unchanged |
| 3 | per-branch n_eff >= 50 | ✅ APPROVE | ✅ unchanged |
| 4 | per-cell n >= 50 | ✅ APPROVE | ✅ unchanged |
| 5 | both-direction trigger rate >= 0.1% each | ✅ APPROVE | ✅ unchanged |
| 6 | sample window >= 7 days | ✅ APPROVE | ✅ unchanged |
| 7 | single-day concentration <= 25% (MAX_DAY_SHARE) | ✅ APPROVE | ✅ 0.25 unchanged |
| 8 | single-symbol concentration <= 30% (MAX_SYMBOL_SHARE) | ⚠️ DRIFT 0.40 → recommend 0.30 | ✅ **0.30 LANDED** |
| 9 | avg_net_bps >= +15 | ✅ APPROVE | ✅ unchanged |
| 10 | PSR(0) >= 0.95 | ✅ APPROVE | ✅ unchanged |
| 11 | DSR >= 0.95 with K_total = K_prior + N_symbols × 11_664 | ✅ APPROVE | ✅ 11_664 math verified |
| 12 | PBO <= 0.20 | ✅ APPROVE | ✅ unchanged |
| 13 | 60m bootstrap CI lower > 0 | ✅ APPROVE with note | ✅ unchanged |
| 14 | plateau requirement (deferred Stage 0R; required pre-live) | ⚠️ ACCEPT DEFER | ⚠️ still deferred (acceptable) |
| 15 | density-floor efficacy >= 60% | ✅ APPROVE | ✅ empirical 75.5%+ |
| 16 | false-positive rate <= 30% (FALSE_POSITIVE_RATE_MAX) | ⚠️ recommend tighten 0.40 → 0.30 | ✅ **0.30 LANDED** |
| 17 | per-tier × per-direction independent promotion | ✅ APPROVE | ✅ unchanged |
| 18 | DSR=0 + PBO>0.5 = auto-RED | ✅ APPROVE | ✅ unchanged |
| 19 | cost_edge_ratio < 0.60 (COST_EDGE_RATIO_MAX) | ⚠️ DRIFT 0.80 → recommend 0.60 | ✅ **0.60 LANDED** |

**Summary**: 17 APPROVE + 1 ACCEPT-DEFER (plateau, non-blocking Stage 0R) + 1 minor (regime_annotation hardcoded period, new SHOULD-FIX).

### §2.11 S0R-2 Verdict — Round 2

**APPROVE-CONDITIONAL**

- ✅ MIT round-1 MUST-FIX `math.ceil` landed + empirically verified at horizon=6/10/14 edge cases
- ✅ CRIT-3 cluster sliding pattern verified byte-equiv with SQL `lag()` semantic
- ✅ CRIT-1 (notional_pct_floor 8th axis) landed; K_total math 11_664 verified
- ✅ CRIT-2 fail-closed `total_bucket_count` 3-state pattern verified
- ✅ 3 drift push-backs all applied (MAX_SYMBOL_SHARE 0.30 / COST_EDGE_RATIO_MAX 0.60 / FALSE_POSITIVE_RATE_MAX 0.30)
- ✅ Bear-regime annotation injected in all 4 verdict paths
- ⚠️ **1 SHOULD-FIX (non-blocking S0R-2 sign-off)**: regime_annotation hardcoded `2026-05-11..05-18` should be parameterized before AlphaSurface Tier-2 production wire (acceptable for Stage 0R replay-packet phase)

---

## §3 V### Migration Guard Audit

S0R-1 round-2 introduces NO new V### migration. SQL relies on existing schema:
- V002 (market.liquidations original 3-col PK)
- V006 (90d retention)
- V095 (5-col PK upgrade + side CHECK NOT VALID) — already validated empirically

**No new Guard A/B/C audit required**. Both panel_coverage.sql and cluster_n_eff.sql are pure SELECT (no DDL).

## §4 6-Dimension Leakage Audit (per `feature-engineering-protocol`)

| Leakage type | Round 1 verdict | Round 2 verdict | Evidence |
|---|---|---|---|
| 1. Look-ahead | ❌ no leak | ❌ no leak | percent_rank ROWS BETWEEN 288 PRECEDING AND CURRENT ROW = backward-only window |
| 2. Target leakage | ❌ no leak | ❌ no leak | LATERAL ts >= bucket_end_ts + quiet (strict forward); entry_open + exit_open both AFTER trigger |
| 3. Survivorship | ❌ no leak (7d) | ❌ no leak (7d) | warn at 30d expansion |
| 4. Cross-section | ❌ no leak | ❌ no leak | percent_rank PARTITION BY symbol (per-symbol; not cross-section pollution) |
| 5. Time-zone | ❌ no leak | ❌ no leak | all ts timestamptz UTC; bucket_5m_epoch UTC |
| 6. Resample boundary | ❌ no leak | ❌ no leak | bucket_end_ts = max(ts) within bucket; entry_open is bar-start, no partial close leak (PA verdict D fix) |

**0/6 leakage detected in round 2** ✅

**Round 2 specific**: PA verdict D (open-only) eliminates round-1 potential **resample boundary** concern (close含 event 後 partial 60s leak); empirically zero in round 2.

## §5 ML Pipeline Maturity Stage (per `ml-pipeline-maturity-audit`)

| Component | Writer | Consumer | Rows (Linux PG empirical) | Decision impact | Stage |
|---|---|---|---|---|---|
| `market.liquidations` | ✅ Phase B v2 24h proof writer revived 2026-05-17 | ✅ 8c SQL features (3 files) | ✅ 8771 rows / 0.66d (still accumulating to 7d) | ❌ Stage 0R replay only | **Shadow** |
| `liquidation_cluster_stage0r_metrics.py` | ✅ Mac+Linux Python | ✅ Stage 0R smoke runner (E1 pending) | n/a (compute function) | ❌ Stage 0R only | **Shadow** |
| AlphaSurface LiquidationCluster Tier 2 | ⏳ AlphaSurface trait Phase A | ❌ Production builder not wired | ❌ no live consumer | ❌ Spec phase | **Skeleton** |
| Cron `stage0r_w_audit_8c_*` | ❌ Not installed | ❌ N/A | n/a | ❌ N/A | **Foundation** |

**8c overall maturity = Shadow only**, correctly reflecting Stage 0R replay-packet generator status. **No change from round 1**.

## §6 MIT-Specific Concerns Carried Forward

### §6.1 Bear-Regime Replication Crisis Warning

Still applicable per round 1 §3.3 + §5. 7d bear-regime sample is **lower-bound sanity gate**, not generalization gate. AlphaSurface Tier-2 production wire MUST require 30d cross-regime sample. Round 2 codifies this via `regime_annotation.cross_regime_validation_required = True` + `live_promotion_requires = "30d cross-regime sample with bull + ranging coverage"`.

### §6.2 Time-Series CV Applicability (Stage 1 readiness)

Same as round 1 §3.1: liquidation cluster is event-driven, not regular interval. Stage 1 promotion (Demo canary post-Stage 0R PASS) MUST impl walk-forward CV with day-block embargo + 60min cluster purge.

Not blocking Stage 0R replay-packet.

### §6.3 Schema Drift Watch

V095 stable; no further schema migration in scope. SHOULD-1 (Python caller pg_typeof assert) is the runtime drift detection lever — non-blocking but valuable for future V### ALTER COLUMN risk.

---

## §7 Files Referenced

- SQL (round 2): 
  - `origin/feature/w-audit-8c-s0r-1-sql-query-template:sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` (381d89a0, 352 LOC)
  - `origin/feature/w-audit-8c-s0r-1-sql-query-template:sql/queries/w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql` (381d89a0, 53 LOC)
  - `origin/feature/w-audit-8c-s0r-1-sql-query-template:sql/queries/w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql` (381d89a0, 156 LOC)
- Metrics (round 2): `origin/worktree-agent-af73a5d4575815f26:helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py` (6cc2b7fb, 1814 LOC)
- Round 1 baseline: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8c_s0r_1_2_mit_dual_review.md`
- 8b RED_FINAL: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8b_round2_red_final_mit_review.md`
- Linux PG empirical artifacts: 8 queries via ssh trade-core docker exec + psycopg2 (logs at `/tmp/mit_dryrun_8c.py`, `/tmp/mit_retest.py`, `/tmp/mit_density.py` on trade-core)
- Skills consulted: ml-pipeline-maturity-audit + feature-engineering-protocol + time-series-cv-protocol + data-drift-detection + db-schema-design-financial-time-series

## §8 Hard Boundary Compliance

| Principle | Status | Evidence |
|---|---|---|
| Read-only PG | ✅ | BEGIN ... <SELECT> ... ROLLBACK; no DDL/DML |
| No metrics modification | ✅ | Read-only review of 6cc2b7fb |
| No SQL modification | ✅ | Read-only review of 381d89a0 |
| No auth / lease / paper / mainnet touch | ✅ | None touched |
| No commit / push / TODO mutation | ✅ | Report-only |
| No cron install | ✅ | None |
| Mac sandbox compliant | ✅ | ssh trade-core for PG; Mac local read-only file access |

**7/7 compliant**.

---

## §9 Ready-for-E4-Regression Verdict

**YES** for both scopes.

- **S0R-1**: APPROVE unconditional → ready for E4 regression suite
- **S0R-2**: APPROVE-CONDITIONAL with 1 non-blocking SHOULD-FIX (regime_annotation hardcoded period) → ready for E4 regression; SHOULD-FIX tracked as follow-up before AlphaSurface Tier-2 wire

**No blockers** to next-stage progression for either scope.

---

MIT AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8c_s0r_1_2_mit_dual_review_round2.md

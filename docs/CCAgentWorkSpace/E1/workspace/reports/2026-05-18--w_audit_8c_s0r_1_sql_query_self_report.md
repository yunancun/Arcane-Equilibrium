# W-AUDIT-8c 8C-S0R-1 SQL Query Template Self-Report

**Date**: 2026-05-18
**Author**: E1
**Branch**: `feature/w-audit-8c-s0r-1-sql-query-template`
**Worktree**: 8C-S0R-1 (per PA design §4.1)
**Task**: Create ONE new SQL file implementing Stage 0R liquidation cluster
feature extraction per PA §2.3, with sibling queries for panel coverage and
cluster n_eff helper.

## 1. File delivered

| Path | LOC | Type | Notes |
|---|---|---|---|
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` | 428 | NEW | Main 5-CTE query + 2 sentinel-split sibling queries |

Breakdown:
- Total 428 LOC = 100 LOC header/comments + ~330 LOC executable SQL
- Main query block (raw_buckets → density_gated → trigger_candidates →
  forward_returns → final_signals): ~210 LOC executable
- Sibling #1 (panel coverage check): 14 LOC executable
- Sibling #2 (cluster_n_eff helper): 60 LOC executable

Well under 800-LOC warning line. Slightly over the ~150 LOC PA estimate due
to verbose Chinese MODULE_NOTE + sibling queries materialized as executable
SQL (not commented-out templates).

## 2. Column schema produced by final SELECT (contract for 8C-S0R-2)

```
symbol                  TEXT
bucket_5m_epoch         BIGINT          -- floor(epoch(ts)/300)*300
bucket_end_ts           TIMESTAMPTZ     -- max(ts) inside the 5m bucket
dominant_side           TEXT            -- 'long_liquidated' | 'short_liquidated'
expected_dir            INT             -- +1 (long liq → mean-revert up)
                                          / -1 (short liq → mean-revert down)
event_count_5m          BIGINT
cluster_notional_5m     DOUBLE PRECISION  (USD)
long_notional_5m        DOUBLE PRECISION
short_notional_5m       DOUBLE PRECISION
long_event_count        BIGINT
short_event_count       BIGINT
dominant_event_count    BIGINT          -- per spec v0.3 min_dominant_event_count
side_dominance_ratio    DOUBLE PRECISION  -- max(long,short) / total
notional_pct_24h        DOUBLE PRECISION  -- 24h rolling percentile rank
entry_ts                TIMESTAMPTZ     -- first 1m kline ≥ bucket_end_ts + quiet
entry_mid               DOUBLE PRECISION  -- (open+close)/2
exit_ts                 TIMESTAMPTZ     -- first 1m kline ≥ entry_time + horizon
exit_mid                DOUBLE PRECISION
gross_bps               DOUBLE PRECISION  -- 10000 × dir × (exit-entry)/entry
net_bps                 DOUBLE PRECISION  -- gross_bps − cost_bps
day_bucket              DATE            -- date_trunc('day', bucket_end_ts)
```

NULL semantics: if `entry_mid` or `exit_mid` is NULL (kline sparse), both
`gross_bps` and `net_bps` are NULL; downstream Python must compute
exclusion rate and treat NULLs as "kline lookup miss" category.

Sibling #1 (PANEL_COVERAGE_CHECK) returns: `total_rows, distinct_symbols,
earliest_ts, latest_ts, span_days, latest_age_min, cohort_observed,
cohort_coverage_pct`.

Sibling #2 (CLUSTER_N_EFF_HELPER) returns: `symbol, dominant_side,
n_clusters_60m`.

## 3. Parameter binding style chosen

**psycopg2 named-param**: `%(name)s` (mirror W-AUDIT-8b precedent).

Rationale:
- 8b file at `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` uses
  the same style.
- 8b consumer at
  `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py` does
  `cur.execute(sql, {"window_days": ..., "symbols": [...]})` — 8C-S0R-2
  will mirror.
- PA §2.3 wrote `$name` (PostgreSQL native prepare placeholder), but
  acceptance criterion #4 mandates "match W-AUDIT-8b precedent for
  downstream Python contract" — `%(name)s` wins on that contract test.

Full param list (10):

| Param | Type | Default / sweep | Source |
|---|---|---|---|
| `window_days` | INT | 7 / 14 / 28 | spec v0.3 §"≥7d sample" |
| `symbols` | TEXT[] | 25-sym cohort (see DEFAULT_COHORT in `rust/openclaw_engine/src/main.rs`) | matches LiquidationPulseAggregator + healthcheck [67] cohort |
| `k_event_floor` | INT | 2 / 3 / 5 / 8 | spec v0.3 §"density floors" |
| `n_usd_floor` | DOUBLE | 5K / 10K / 25K / 50K | spec v0.3 |
| `m_dominant_floor` | INT | 1 / 2 / 3 | spec v0.3 |
| `side_dominance_floor` | DOUBLE | 0.70 / 0.80 / 0.90 | spec v0.3 §"magnitude / dominance sweep"; provider 0.60 is the wider floor at aggregator layer |
| `cluster_notional_floor_usd` | DOUBLE | 10K / 25K / 100K | spec v0.3 |
| `quiet_window_sec` | INT | 0 / 30 / 60 | spec v0.3 |
| `horizon_min` | INT | 1 / 5 / 15 | spec v0.3 |
| `cost_bps` | DOUBLE | 12 default; 18 / 25 sensitivity | PA §3.3 mitigation; mirror 8b |

## 4. Deviations from PA §2.3 design (5 items)

| # | Deviation | Reason |
|---|---|---|
| **1** | 24h percentile rolling window = **288 PRECEDING** (not PA's 17280) | 17280 / 12 buckets-per-hour = 1440 hours = 60 days; clearly inconsistent with the column semantic `notional_pct_24h`. 288 = 24h × 12 5m-buckets/h is the correct math. Logged as PA typo. |
| **2** | Use `market.klines WHERE timeframe='1m'` (not PA's `market.klines_1m`) | V002 schema has a single `market.klines` table with `timeframe` discriminator; no separate `klines_1m` exists. Verified via direct V002 file read. |
| **3** | `ROWS BETWEEN 288 PRECEDING` explicitly documented as row-window not time-window | When sparsity is high (low-density tier symbols like LINKUSDT 0.2% bucket coverage), 288 rows may span >24h calendar time. This is semantically fine for cluster rarity comparison ("relative to last 288 own triggers"), but downstream Python should be aware for any strict-time-window post-processing. |
| **4** | `forward_returns` uses 2× `LEFT JOIN LATERAL` (not PA's 4× correlated subqueries) | Performance optimization to meet acceptance #1 "<30s on 7d × 32-sym panel". Each LATERAL returns `(ts, open, close)` tuple in one index scan; the 4-subquery PA pattern would re-scan klines 4× per trigger row. Semantics identical (strict as-of, LIMIT 1). |
| **5** | Parameter binding `%(name)s` not `$name` | Mirror 8b precedent for `cursor.execute(sql, {...})` Python contract. Acceptance #4 mandate. |

None of these deviations change spec v0.3 math, threshold definitions, or
output semantics — they are implementation hygiene + bug fixes on the PA
design draft.

## 5. Tests run

### Local Mac structural smoke (Python one-liners)

```
Total LOC: 428
Sentinel-split parts: 5 (main, PANEL_COVERAGE_CHECK + body, CLUSTER_N_EFF_HELPER + body)
Parens balance: open=167 close=167 diff=0
Named params (10 expected, 10 found): cluster_notional_floor_usd, cost_bps,
  horizon_min, k_event_floor, m_dominant_floor, n_usd_floor,
  quiet_window_sec, side_dominance_floor, symbols, window_days
Sibling param subset of main: PANEL_COVERAGE_CHECK={symbols, window_days} ⊂ main ✓
                              CLUSTER_N_EFF_HELPER={7 params} ⊂ main ✓
sqlparse split: 3 statements ✓
Statement terminators (;): 3 ✓
CTE count in main block: 5 (raw_buckets, density_gated, trigger_candidates,
                            forward_returns, final_signals) ✓
```

### What I did NOT run (out of scope; MIT chain)

- **Linux PG empirical dry-run** — per `feedback_v_migration_pg_dry_run.md`
  mandate, MIT runs Linux PG empirical SoT verification. This worktree only
  delivers the SQL file + structural smoke.
- **Cargo / pytest** — no Rust or Python code modified in this worktree.

## 6. Linux PG dry-run prep checklist for MIT

When dispatching MIT chain for 8C-S0R-1 verification:

### A. Connect + load
```bash
ssh trade-core
cd /home/ncyu/Projects/TradeBot/srv
git fetch origin
git checkout feature/w-audit-8c-s0r-1-sql-query-template
psql "$PG_DSN"   # whichever DSN exposes market.* + cohort symbols
```

### B. Per-statement smoke (one of three at a time)

**Statement 1 (PANEL_COVERAGE_CHECK)** — copy-paste from file lines 312-326:
```sql
-- bind params
\set window_days 7
\set symbols '{BTCUSDT,ETHUSDT,SOLUSDT,...,INJUSDT}'
-- run statement; verify ≥7d span_days + cohort_coverage_pct
```
Expected: ~7d span, ~24-25/25 cohort_observed (matching healthcheck [67]
2026-05-18 PG empirical PASS).

**Statement 2 (MAIN query)** — bind 10 params:
```sql
-- e.g. baseline sweep cell (K=3, N=10K, M=2, dom=0.7, floor=25K, quiet=30, h=5, cost=12)
SELECT count(*), count(DISTINCT symbol)
FROM (
    -- paste main query body wrapped as subquery
) features;
```
Expected:
- Non-empty rowset (high-density tier should produce ≥ 10-50 trigger rows per
  symbol per 7d at baseline cell)
- Per-symbol coverage matches MIT 2026-05-18 sparsity finding
  (HYPEUSDT/BTC/ETH/SOL > LINK/DOT)
- No PG type errors / column type drift
- Runtime <30s (acceptance #1)

**Statement 3 (CLUSTER_N_EFF_HELPER)** — same 10 params:
```sql
-- run as standalone (recomputes raw_buckets → trigger_candidates internally)
-- expected: 2 rows per high-density symbol (long_liquidated + short_liquidated)
-- with n_clusters_60m in range 5-50 per 7d window per spec v0.3 expectation
```

### C. Performance benchmark (acceptance #1 lock)

```sql
EXPLAIN ANALYZE <main query with baseline params>;
```
Verify:
- `market.liquidations` uses TimescaleDB hypertable chunk-pruning by `ts`
- `market.klines` uses `(symbol, timeframe, ts)` PK + LATERAL index scan
- Total runtime <30s on 7d × 25-sym panel

### D. Sanity invariants

- `dominant_event_count` ≥ `m_dominant_floor` for all returned rows
- `side_dominance_ratio` ≥ `side_dominance_floor` for all returned rows
- `expected_dir IN (+1, -1)` for all returned rows (no 0 / NULL)
- `gross_bps + cost_bps = net_bps` (algebraic check on non-NULL rows)
- `entry_ts ≥ bucket_end_ts` (no leakage)
- `exit_ts ≥ entry_ts` (horizon respected)

### E. Document MIT findings in MIT/workspace/reports/

MIT writes own report at
`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-XX--w_audit_8c_s0r_1_pg_empirical_dry_run.md`.

## 7. Governance compliance

| Constraint | Result |
|---|---|
| **DO NOT modify V### migrations** | ✓ 0 migrations touched |
| **DO NOT add Rust / Python code** | ✓ Only 1 new `.sql` file added |
| **DO NOT touch auth / live / lease / paper / mainnet** | ✓ Read-only SELECT against existing `market.*` tables |
| **DO NOT run production SQL on trade-core** | ✓ Only Mac local file edits + structural smoke |
| **Use psycopg2 named-param style** | ✓ `%(name)s` per 8b precedent |
| **Chinese-first comments** (`feedback_chinese_only_comments.md`) | ✓ MODULE_NOTE + inline comments default Chinese; technical identifiers (LATERAL / percent_rank / DOMINANT_SIDE_RATIO / cor-side) kept English |
| **File <800 LOC warning** | ✓ 428 LOC; well under |
| **Branch hygiene** | ✓ New branch `feature/w-audit-8c-s0r-1-sql-query-template`; no main commit |
| **Multi-session safety** | ✓ Only one new file added; did not stage sibling-modified memory.md files |

## 8. Output schema lock-in for downstream chain

Downstream `8C-S0R-2` Python metrics module (`helper_scripts/reports/w_audit_8c/liquidation_cluster_stage0r_metrics.py`) must:

1. Load via:
   ```python
   from pathlib import Path
   sql_path = REPO_ROOT / "sql" / "queries" / "w_audit_8c_liquidation_cluster_stage0r_features.sql"
   sql_full = sql_path.read_text()
   ```
2. Sentinel-split:
   ```python
   import re
   chunks = re.split(r'^-- @SIBLING:([A-Z_]+)\n', sql_full, flags=re.MULTILINE)
   main_sql, sibs = chunks[0], {chunks[1+i*2]: chunks[2+i*2] for i in range(len(chunks)//2)}
   panel_sql = sibs['PANEL_COVERAGE_CHECK']
   ceh_sql   = sibs['CLUSTER_N_EFF_HELPER']
   ```
3. Bind exactly the 10 params (with `symbols=list(...)`); psycopg2 will
   handle `text[]` cast automatically.
4. Output column dtypes for pandas/numpy consumption:
   - INT/BIGINT → int64
   - DOUBLE PRECISION → float64
   - TIMESTAMPTZ → datetime64[ns, UTC]
   - DATE → datetime64[ns]
   - TEXT → object
5. Treat NULL `net_bps` as "kline lookup miss" — exclude from
   `_avg_net_bps()` numerator but include in `_kline_miss_rate()` reporting.

## 9. Not done (per mandate + scope discipline)

- Did not run pytest (no Python tests in scope — S0R-2 owns metrics smoke).
- Did not run cargo (no Rust touched).
- Did not run Linux PG dry-run (MIT chain mandate; see §6 prep checklist).
- Did not modify any other SQL file (V###, V094, V095, existing queries).
- Did not modify `helper_scripts/SCRIPT_INDEX.md` (no new script — only new
  SQL file; SCRIPT_INDEX tracks scripts).
- Did not add a Python test fixture for SQL contract — S0R-2's smoke harness
  will cover (avoiding location collision with planned
  `helper_scripts/reports/w_audit_8c/tests/`).

## 10. Operator next steps

1. **E2 adversarial review** on
   `feature/w-audit-8c-s0r-1-sql-query-template`. Focus areas:
   - LATERAL leak check (entry_ts ≥ bucket_end_ts + quiet_window invariant)
   - 288-row window semantic vs PA's 17280 typo (confirm fix is correct)
   - Sentinel-split contract (`-- @SIBLING:NAME\n`) parseability and brittleness
   - Param naming consistency with 8b precedent
   - Comment style (chinese-first; no stale bilingual remnants)
2. **MIT Linux PG empirical dry-run** per §6 checklist (acceptance #4).
3. **PM merge to main** after E2 + MIT both APPROVE.
4. After main land: dispatch **8C-S0R-2** chain (Python metrics module
   consumes this SQL contract via sentinel-split loader).

---

E1 IMPLEMENTATION DONE: 待 E2 審查 + MIT Linux PG empirical dry-run
(report path:
`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_1_sql_query_self_report.md`)

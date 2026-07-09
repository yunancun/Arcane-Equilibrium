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

---

# Round 2 Delta (2026-05-18 PM 派發 rework)

## R2.1 Round 1 結果

E2 round 1 RETURN：2 CRIT（spec 對齊 + sibling 同步）+ 2 HIGH（sentinel-split
契約漂移 + bar-boundary partial leak）+ 4 MED + 2 LOW。

MIT Linux PG dry-run x2 PASSED：執行時間 4-24ms（well under 30s）+ schema 1:1
match + 0/6 feature leakage + density floor 84.6% efficacy；但 3 SHOULD-FIX +
1 governance MUST-LAND（E1 self-report 不在主 working tree，需從 git 拉出 +
append round 2 delta）。

PA HIGH-2 arbitration verdict D：entry_mid / exit_mid 從 `(open+close)/2` 改
為 `open` only；`>=` 維持；K_total 11_664 維持；欄位名沿用 entry_mid /
exit_mid 不 rename。

## R2.2 Round 2 修改清單

| 檔 | 動作 | LOC |
|---|---|---|
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_features.sql` | 重寫主檔（CRIT-1 + HIGH-2 + LOW-2 + MIT 3 SHOULD-FIX + 移除 sibling 部分） | 428 → 352（-76） |
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql` | NEW（HIGH-1 split sibling #1 獨立檔） | +53 |
| `sql/queries/w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql` | NEW（HIGH-1 split sibling #2 獨立檔 + CRIT-2 加 notional_pct_floor gate） | +156 |

**Net delta**：428 LOC（單檔）→ 561 LOC（3 檔 split + 補 CRIT/HIGH/MIT 註釋）
= +133 LOC。

## R2.3 CRIT-1 — notional_pct_floor gate 完全缺漏

**修法**：
1. Header 參數段加第 11 個 `%(notional_pct_floor)s DOUBLE PRECISION — 0.90/
   0.95/0.98`（spec v0.3 line 191 magnitude_ok 第三層）。
2. `trigger_candidates` 拆兩層 CTE：
   - `trigger_with_pct`：先計算 `side_dominance_ratio` + `expected_dir` +
     `notional_pct_24h`（percent_rank 在 WHERE 不能直接用，PG WHERE 在 window
     evaluation 之前）。
   - `trigger_candidates`：套三層 magnitude_ok gate（side_dominance_floor +
     cluster_notional_floor_usd + notional_pct_floor）。
3. CTE 計數從 5 變 6（raw_buckets → density_gated → trigger_with_pct →
   trigger_candidates → forward_returns → final_signals）。
4. MODULE_NOTE 加 deviation #6 documented + magnitude_ok 三層 gate rationale。

**為什麼三層 magnitude gate 都必須**：cluster_notional_floor_usd 絕對量級排
「太小」，notional_pct_floor 相對量級排「對自己而言不稀有」，
side_dominance_floor 排「方向不夠主導」；三層交集才是 spec K_total 11_664
grid 的真實 cell 定義。漏 notional_pct_floor 會讓 absolute USD 通過但相對
歷史平庸的桶觸發，over-trigger → DSR 估計被 dilution → false-PASS 風險。

## R2.4 CRIT-2 — Sibling #2 n_eff helper 與主查詢 trigger 樣本不一致

**修法**：sibling #2（`...cluster_n_eff.sql`）的 CTE 結構與主檔嚴格鏡像：
- raw_buckets（同主檔）
- density_gated（同主檔）
- trigger_with_pct（同主檔，計算 side_dominance_ratio + notional_pct_24h）
- trigger_candidates（同主檔 gate set，含 notional_pct_floor）
- ordered（lag bucket_end_ts 取 gap）
- new_cluster_flag（60min gap 即視為新 cluster）

確保 n_clusters_60m 計算的 cluster 樣本與主查詢 trigger 完全同 base，
保證 n_eff/n 比例 DSR penalty 不失真。

## R2.5 HIGH-1 — Sentinel-split 拆 3 個獨立檔

**修法**：原單檔 `w_audit_8c_liquidation_cluster_stage0r_features.sql` 含
`-- @SIBLING:PANEL_COVERAGE_CHECK` + `-- @SIBLING:CLUSTER_N_EFF_HELPER` 兩個
sentinel marker 拆獨立檔：
- `w_audit_8c_liquidation_cluster_stage0r_features.sql`（主查詢 5 CTE）
- `w_audit_8c_liquidation_cluster_stage0r_panel_coverage.sql`（前置檢查）
- `w_audit_8c_liquidation_cluster_stage0r_cluster_n_eff.sql`（n_eff helper）

理由：與 8b precedent（single statement 純檔）風格一致；消除 psycopg2 multi-
statement `cur.execute()` silent failure mode（若 S0R-2 owner 不 sentinel-split
會 silently 只拿到最後一個 statement 的 description，主查詢 features 全失但
無 schema mismatch error）。

下游 Python loader 改為三次獨立 `cur.execute(open(<each_file>).read(),
params)` 載入；參數 binding 完全相同。

## R2.6 HIGH-2 — PA verdict D 應用

**修法**：`forward_returns` CTE 兩處 inline 編輯：
- `entry_mid` 從 `((k_entry.open + k_entry.close) / 2.0)` 改為
  `k_entry.open::float8`
- `exit_mid` 同步：`((k_exit.open + k_exit.close) / 2.0)` → `k_exit.open::float8`
- LATERAL `SELECT ts, open, close` 簡化為 `SELECT ts, open`（不再需要 close）

**MODULE_NOTE 加 HIGH-2 verdict D 中文 rationale**（PA 仲裁 §5.1 amendment
text）：
- market.klines.ts = bar open time（V002 line 122 鎖死），一根 1m bar 涵蓋
  [ts, ts+60s)。
- bucket_end_ts 落 bar 邊界（12:34:00）+ quiet=0 → ts >= 12:34:00 命中該 bar
  → close ≈ 12:34:59 包含 event 後 59s mean-reversion → (open+close)/2 把 60s
  後價格混入進場價 → gross_bps 系統性低估 alpha。
- 改 open-only 後 boundary case：entry_open ≈ event 時刻 price proxy（bar 開
  瞬間第一筆 trade），無 leak；non-boundary case：entry_open = 「event 後
  第一根新 bar 開瞬間」，與 exit_open 對稱。
- 欄位名 `entry_mid` / `exit_mid` 沿用：下游 Python `_compute_gross_bps()`
  已 lock 此 contract，避免 cascade rename。
- `ts >=`（非 strict gt）維持：spec line 231 「next available tradable mark」
  語意，事件已知、價格未知，不是 lookahead bias。

## R2.7 MIT 3 SHOULD-FIX

| Item | 修法 |
|---|---|
| SHOULD-1 `pg_typeof` cast guard | 為 caller-side concern；E1 在主檔 header「依賴」段註明 market.liquidations 的 qty/price 為 `real`（V002 + V095 確認），caller 可加 `cur.execute("SELECT pg_typeof(qty), pg_typeof(price) FROM market.liquidations LIMIT 1")` runtime assert 偵測 schema drift（不在本 SQL scope，下游 S0R-3 wire） |
| SHOULD-2 24h percentile 288 PRECEDING semantic doc | trigger_with_pct CTE 註釋補：per-symbol sparsity 高時（POLUSDT 1 trigger/day），實際 288-row 跨度可能 > 24h；下游 Python 用此欄位做 cluster 稀有度估計，semantic 為「相對自身過去 288 個曾觸發桶的 magnitude rank」（含 deviation #3 補述）|
| SHOULD-3 LATERAL ORDER BY 保護 invariant | forward_returns CTE 註釋補：ORDER BY ts ASC LIMIT 1 依賴 TimescaleDB ChunkAppend chunk-order-aware planner 早期終止（MIT empirical Linux PG dry-run 已驗 Custom Scan Order: klines.ts）；future planner regression 若失此 order 可能掃全 chunk，請勿移除 ORDER BY |

## R2.8 LOW-2 順帶修復

`trigger_with_pct.expected_dir` CASE 加 `ELSE NULL` defensive marker：
density_gated 已 filter mixed 不應達此 CASE，ELSE NULL 是防未來 refactor 繞開
mixed filter；不改現有 semantic（mixed 桶在 density_gated 已過濾，
expected_dir CASE 達到的只有 long/short）。

## R2.9 Mac sqlparse smoke 結果

| 檔 | sqlparse statements | 行數 |
|---|---:|---:|
| features.sql | 1 (SELECT) | 352 |
| panel_coverage.sql | 1 (SELECT) | 53 |
| cluster_n_eff.sql | 1 (SELECT) | 156 |

3 個檔各 1 個 valid SELECT statement，無 sentinel marker，psycopg2 `cur.execute()`
單檔載入無 multi-statement silent failure 風險。

**重要 caveat**：Mac sqlparse 只 syntactic check；PG runtime semantic
（PL/pgSQL constraints, planner behavior, percent_rank windowing 在 trigger_
with_pct → trigger_candidates 跨 CTE reference）必須由 MIT Linux PG round 2
dry-run x2 驗證；E1 IMPL 不負責 Linux PG empirical（per feedback_v_migration_pg_
dry_run.md 範圍）。

## R2.10 Round 2 governance compliance

- 跨平台 grep（/home/ncyu / /Users/[^/]+）：0 hit in 3 SQL files ✅
- 中文注釋（chinese-first）：3 檔 MODULE_NOTE + inline 全中文，技術詞保留英文
  （LATERAL / percent_rank / ChunkAppend / cor-side）✅
- 文件大小：3 檔均 < 800 LOC 警戒（最大 features.sql 352 LOC）✅
- 改動範圍：僅 `sql/queries/` + 本 self-report；無 Rust / Python / V### /
  auth / live state 變動 ✅
- 跨 Worktree pre-created 路徑 isolation：所有改動在
  `srv/.claude/worktrees/e1-s0r-1-r2`，不污染主 working tree ✅

## R2.11 Operator next steps

1. **E2 round 2 adversarial review** focus：
   - CRIT-1 修復：trigger_candidates 拆兩層後 PG WHERE 順序語意正確
   - CRIT-2 sibling 鏡像：n_eff helper 與主查詢 trigger sample 完全同 base
   - HIGH-1 split：3 檔獨立載入無 multi-statement risk
   - HIGH-2 verdict D：entry_mid / exit_mid 為 k_*.open::float8，欄位名保留
2. **MIT round 2 Linux PG dry-run x2** focus：
   - 3 檔分別 execute（不再 sentinel-split）
   - trigger_candidates 加 notional_pct_floor 後 row count（vs round 1）
   - main query plan 仍 < 30s（trigger_candidates 兩層 CTE 影響）
   - sibling cluster_n_eff 與主查詢 trigger row count 嚴格一致
3. **PM merge** 待 E2 + MIT round 2 雙 APPROVE。

---

E1 IMPLEMENTATION DONE (Round 2): 待 E2 round 2 審查 + MIT round 2 Linux PG
dry-run x2 (report path:
`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-18--w_audit_8c_s0r_1_sql_query_self_report.md`)


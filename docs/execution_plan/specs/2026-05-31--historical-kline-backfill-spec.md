# Spec — Historical Kline Backfill (Bybit Daily + 4h, >=12mo) for Multi-Day Trend Robust Test

**Date**: 2026-05-31 · **Author**: MIT (ML & DB Auditor) · **Status**: AEG-BLOCKED / SPEC ONLY (former executable posture is superseded by AEG-S0; 0 code, 0 schema change, 0 backfill executed)
**Chain**: MIT spec -> AEG-S0/S1 gate -> E1 (only after PM opens a scoped task) -> MIT data-quality verify -> MIT re-run multi-day diagnostic on deep window
**Trigger**: operator directive — invest in data infra to unblock cost-wall-escape category #2 (low-turnover multi-day perp TREND). Fastest path to robust TSMOM/cross-sectional test.
**Upstream evidence**: `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--cost_wall_escape_2_multiday_trend_diagnostic.md` (R-2b): dilution mechanism VALIDATED (multi-day gross 389-1213 bps, all-in cost ~3-4% of move); edge NOT establishable because `market.klines` is only **56 days** (collector onset 2026-04-05 hard lower bound) => ~8 independent weekly periods << SSOT §5 n>=30 gate. **Bottleneck is historical depth, not mechanism.** §7 HINT: backfill Bybit daily/4h history (read-only, Bybit-native) is the single highest-leverage unblock vs waiting for live collector accumulation (~2026-10).

> **AEG gate override (2026-05-31)**: this spec is not executable as an E1
> ticket until `docs/execution_plan/2026-05-31--aeg_s0_contracts.md` passes
> formal PA/MIT/QC/BB/TW/CC review and PM opens an AEG-S1 scoped task. E1 must
> not run a backfill writer, mutate retention, implement endpoints, or write DB
> data from this spec alone.

---

## 0. What E1 must know first (3-5 load-bearing constraints) + klines schema (EMPIRICAL)

> Read this section before writing any code. All schema facts below are from live `\d market.klines` on `trade-core` PG this run (2026-05-31), not assumed.

**0.1 The target table has NO provenance column.** `market.klines` is written by the live WS collector (`rust/openclaw_engine/src/database/market_writer.rs:233 flush_klines`) with exactly 12 columns and **no source/origin/provenance field**. A backfilled row is byte-for-byte indistinguishable from a live-WS row at the row level. **Therefore: do NOT add a `source` column inline (that is a schema change = MIT/E2 migration, out of this spec's scope), and do NOT silently co-mingle if a future ML/provenance need requires separation.** See §4 for the provenance decision (RECOMMENDED: separate-then-decide via a provenance ledger table OR a dedicated backfill timeframe namespace — operator/PM picks; default = co-mingle daily/4h only, which are NOT the live 1m surface, so live-1m provenance is never touched).

**0.2 The live writer is non-destructive: `ON CONFLICT (symbol, timeframe, ts) DO NOTHING`.** (market_writer.rs:268, verified.) The dedup key = the primary key = `(symbol, timeframe, ts)`. **E1's backfill INSERT MUST use the identical `ON CONFLICT (symbol, timeframe, ts) DO NOTHING`.** This makes backfill (a) idempotent — re-runnable safely, (b) gap-filling only — it will never clobber an existing live row, and live WS will never clobber a backfilled row (first-writer-wins in the 56d overlap). This is the core safety invariant of the whole job.

**0.3 RETENTION WILL DELETE OLD BACKFILL — this is the #1 risk.** `policy_retention` on `klines` (hypertable_id=4) runs **daily** with `drop_after = 365 days` (verified via `timescaledb_information.jobs`). **Any chunk whose time range is older than 365 days from now() is auto-dropped on the next daily job fire.** A naive 18-24mo backfill would have its oldest ~6-12 months silently deleted, possibly before the diagnostic even runs. This is a V### silent-data-loss trap analogous in spirit to the V023 silent-noop lesson: the job does not error, it just removes the data. **E1 cannot solve this alone — it requires an operator/MIT retention-policy decision BEFORE backfill (see §1.4 + §7 blocker).** Do not run the >12mo backfill until the retention question is resolved, or you will burn API budget loading data that gets reaped.

**0.4 `'1d'` is a brand-new timeframe value.** Current distinct `timeframe` values are exactly `1m / 5m / 15m / 1h / 4h` (verified). There is **no `'1d'` row today.** Bybit kline interval code for daily is `D` (and weekly `W`). E1 must map Bybit `D` -> OpenClaw storage string. **RECOMMENDED storage string = `'1d'`** (matches db-schema-design convention + `outcome_backfiller.rs` storage-format family). This is additive: the existing consumer SQL in `outcome_backfiller.rs:54-84` hardcodes `'1m'/'5m'/'1h'/'4h'` and will simply not match `'1d'` (no breakage). The MIT diagnostic re-run (step 6) must query whatever string E1 commits to — so **E1 must declare the chosen daily timeframe string in the run report.**

**0.5 Bybit `get_klines` is public/no-auth, newest-first, 1000/page, paginated by start/end.** (`docs/references/2026-04-04--bybit_api_reference.md` §1.1 get_klines + §4.1.) Rate group = **Market = 120 req/s per UID + 600 req/5s per IP**. `category="linear"` for USDT perp. Returns descending by time; E1 must reverse to ascending before INSERT (or sort in SQL). Numbers come back as **strings** (`"65000.50"`) — parse to float. OHLC stored as PG `real` (float4) — see §0.6.

**0.6 OHLC precision is float4 (`real`), not float8.** The table stores `open/high/low/close/volume/turnover` as `real`. The diagnostic already handles this (casts float4->float8 before arithmetic; `round()` needs numeric cast on PG 16). E1 must bind backfilled OHLC as `f32`/`real` to match the existing writer (market_writer.rs:259-264 does `as f32`). No precision regression vs live data — both are float4.

**klines schema (verified `\d market.klines`, 2026-05-31):**

| Column | Type | Nullable | Notes |
|---|---|---|---|
| ts | timestamptz | NOT NULL | bar open time (writer derives from `open_time_ms`); PK component |
| open_ts_ms | bigint | nullable | bar open epoch ms |
| close_ts_ms | bigint | nullable | bar close epoch ms |
| symbol | text | NOT NULL | e.g. `BTCUSDT`; PK component |
| timeframe | text | NOT NULL | `1m/5m/15m/1h/4h` today; PK component; `1d` to be added |
| open | real (float4) | NOT NULL | |
| high | real (float4) | NOT NULL | |
| low | real (float4) | NOT NULL | |
| close | real (float4) | NOT NULL | |
| volume | real (float4) | nullable | |
| turnover | real (float4) | nullable | |
| tick_count | integer | nullable | live = per-bar trade count; backfill has no tick_count from kline endpoint -> set 0 or NULL (see §4.4) |

**PK / Indexes (verified):**
- PK: `klines_pkey (symbol, timeframe, ts)` <- **the dedup / ON CONFLICT key**
- `idx_klines_symbol_tf_ts (symbol, timeframe, ts DESC)` <- hot-path for diagnostic per-symbol time-range scan
- `idx_klines_ts_desc (ts DESC)`

**Hypertable (verified `timescaledb_information`):** `klines` is a hypertable, dim = `ts`, **chunk_time_interval = 7 days**, num_chunks (current 56d window) = 9. compression: enabled, `compress_after = 14 days`. retention: `drop_after = 365 days`, schedule = daily. hypertable_id = 4.

---

## 1. Schema verification + hypertable / retention impact (MIT findings — FACT)

### 1.1 Dedup key / provenance (FACT)
- Dedup key = PK = `(symbol, timeframe, ts)`. [F: `\d market.klines`]
- Live writer conflict policy = `ON CONFLICT (symbol, timeframe, ts) DO NOTHING`. [F: market_writer.rs:268]
- **No provenance/source column exists.** Live WS rows and backfill rows are not distinguishable at row level. [F: schema has 12 cols, none is source/origin]
- Inference [I]: because the live 1m surface (the 56d, gap-having, collector-onset data that feeds ML / decision_outcomes / panels) is `timeframe='1m'`, and this backfill targets ONLY `timeframe='1d'` (new) and `timeframe='4h'` (existing but research-grade-incomplete per R-2b §1), **the live 1m provenance is structurally untouched as long as backfill does not write 1m.** This is the cleanest provenance firewall available without a schema change: namespace by timeframe.

### 1.2 4h overlap caveat (FACT + decision)
- `timeframe='4h'` ALREADY has 6262 rows over the 56d window (137 symbols), but R-2b §1 found it incomplete (BTC 307/337 expected ~91%, most symbols far fewer). [F]
- If E1 backfills 4h for the same 56d window, `ON CONFLICT DO NOTHING` means **existing live 4h rows win**; backfill only fills the gaps. This is safe and desirable (densifies the incomplete live 4h). [I from §0.2]
- **Decision for E1**: backfill 4h for the FULL >=12mo window (including the 56d overlap). The overlap is harmless (gap-fill only). Pre-onset (before 2026-04-05) 4h is 100% new rows.

### 1.3 Hypertable chunk impact (FACT — LOW concern)
- chunk_time_interval = 7d. Daily klines: ~25 symbols x ~1 bar/day x 7 = ~175 rows/chunk; 4h: ~25 x 6 x 7 = ~1050 rows/chunk. Tiny. [I from chunk math]
- A 24mo backfill spans ~104 weekly chunks per timeframe. TimescaleDB creates chunks lazily on INSERT; ~104 new chunks is well within healthy metadata overhead (existing hypertable already has 9 chunks for 56d of all-5-timeframes). [I]
- compression `compress_after=14d`: backfilled historical chunks (all >14d old) become eligible for compression immediately on next compression job — GOOD for PG 4-8GB memory (daily/4h are low-volume so compression gain is modest but free). No action needed; do NOT manually compress (let policy handle it). [I]
- **Chunk count is NOT a blocker.** The retention policy is (see 1.4).

### 1.4 RETENTION policy impact (FACT — HIGH concern, BLOCKER for >12mo)
- `policy_retention drop_after=365d`, runs **daily**. [F: timescaledb_information.jobs]
- **Mechanism**: TimescaleDB retention drops whole chunks whose time range is entirely older than (now() - 365d). For a 7d chunk, once its newest bar is >365d old, the chunk is dropped on the next daily job. [I from TimescaleDB retention semantics — to be EMPIRICALLY confirmed by MIT in step 4 verify, not assumed at runtime]
- **Consequence for this spec's target window**:
  - 12mo backfill (2025-05-31 -> now): the oldest data is ~365d old. The very oldest chunk(s) are **on the edge** of the drop boundary and may be reaped within days of backfill. RISK: MEDIUM.
  - 18-24mo backfill (2024-05/11 -> now): months 13-24 are **already past `drop_after`** and will be dropped on the **next daily retention fire** (within 24h). RISK: CRITICAL — most of the deep history is loaded then immediately deleted. The diagnostic would see <=12mo, defeating the 18-24mo goal.
- **This is a pre-backfill blocker. E1 MUST NOT run the >12mo backfill until ONE of these is resolved (operator/MIT decision, see §7-A):**
  1. **(RECOMMENDED) Carve a retention exemption for the deep-history timeframes.** TimescaleDB retention is per-hypertable, not per-timeframe; so a same-table exemption is not natively granular. Cleanest options:
     - 1a. **Remove/extend `policy_retention` on `klines`** to e.g. `drop_after=1095d` (3y) so 24mo survives. Under AEG this is **not** an operator one-liner: it requires MIT migration/change-control design, Linux PG dry-run, double-apply safety, E2/E4 review, rollback/verify evidence, and PM gate. **Trade-off**: the high-volume 1m/5m rows also keep 3y -> PG growth. Mitigate: 1m at ~1.3M rows/56d => ~8.6M/yr => ~26M for 3y for 1m alone; with compression after 14d this is acceptable on the 40TB NAS but MUST be sized by MIT/operator before commit (see §3 capacity).
     - 1b. **Dedicated separate hypertable for deep history** (e.g. `market.klines_history`, daily+4h only, no retention) — but this is a schema change (MIT migration, out of THIS spec's E1 scope) and forks the diagnostic's query surface. Defer unless 1a's PG-growth is unacceptable.
  2. **Accept 12mo only** (not 18-24mo) AND set retention so 12mo is safe (e.g. `drop_after=400d` buffer). 12mo daily = ~50 independent weekly periods => clears SSOT §5 n>=30 for weekly-or-longer. This is the MINIMUM viable unblock and the lowest-risk. R-2b §7 asks for ">=6 months ... (>=50-100 independent 14-day periods)"; 12mo daily gives ~26 non-overlapping 14-day periods (borderline) or ~50 weekly — **MIT recommends 18mo as the sweet spot if retention is extended, else 12mo as floor.**
- **MIT default recommendation**: option **1a (extend retention to 1095d)** + backfill **18 months** daily + 4h. Rationale: 18mo daily = ~39 non-overlapping 14-day periods + ~78 weekly periods => robustly clears n>=30 and gives headroom for DSR deflation of the 8-cell parameter search R-2b flagged. Extending retention is reversible and operator-gated.

### 1.5 audit_migrations / Guard note (FACT)
- This spec proposes **NO new V### migration** (no schema change; backfill is pure data INSERT into an existing table via the existing column set). Therefore Guard A/B/C are N/A for the backfill itself.
- **IF** operator chooses §1.4 option 1a retention mutation, option 1b separate `klines_history` table, OR §4 chooses to add a provenance column/ledger, **THAT becomes a separate MIT/E2 migration or change-control package with full Guard A/B/C + Linux PG dry-run (CLAUDE.md "Data, Migrations, And Validation")** — explicitly out of this E1 backfill spec's scope and a precondition handed back to PM.

---

## 2. Backfill scope

| Parameter | Value | Rationale |
|---|---|---|
| Timeframes | **daily (`1d`) + 4h** | R-2b used 1m->daily-close; native daily is cleaner (no resample, no gaps from 1m holes). 4h gives intra-week granularity for M=5-7 day holds + densifies the incomplete live 4h. |
| Window (RECOMMENDED) | **18 months** (2024-11-30 -> 2026-05-31) | ~39 non-overlapping 14d periods + ~78 weekly => clears SSOT §5 n>=30 + DSR headroom. REQUIRES §1.4 retention extension. |
| Window (FLOOR if retention not extended) | **12 months** (2025-05-31 -> 2026-05-31) | ~26 non-overlapping 14d / ~50 weekly. Minimum to clear n>=30 for weekly. Needs retention `drop_after>=400d`. |
| Window (STRETCH) | 24 months | Only if §1.4-1a applied with 1095d retention AND §3 capacity signed off. Diminishing returns vs 18mo for current goal. |
| Symbols | **core 25 operational overlap plus PIT/survivorship-aware cohorts** | R-2b sweep used 10 liquid symbols; cross-sectional needs breadth. Core25 can be the first analysis cohort, but collection/evidence must not be current-survivor-only. |
| Symbol source | `market.symbol_universe_snapshots` PIT builder + scanner-active overlap | Do NOT hardcode a 25-symbol list in the script. Build from `market.symbol_universe_snapshots`, include active/delisted/closed status where the window requires it, and record scanner-active overlap as a cohort, not as the whole universe. |

**Survivorship note (FACT from R-2b §5)**: restricting to currently-active symbols introduces mild survivorship bias (delisted perps absent). At the multi-day horizon over 18mo this is non-trivial if any core symbol was listed mid-window (its history starts late) or delisted. **E1 MUST**: (a) for each symbol, record `min(ts)` actually returned by Bybit (listing date) — a symbol listed 8 months ago cannot supply 18mo; (b) NOT silently pad missing early history; (c) the diagnostic (step 6) will compute n_independent per symbol from real coverage, not assume full window. This is the survivorship discipline R-2b §5 flagged.

---

## 3. Bybit API plan + request/time estimate (FACT from API ref + arithmetic)

**Endpoint**: `GET /v5/market/kline` (`market_data_client.rs:313 get_klines`). Public, no auth. [F: API ref §1.1]
- Params: `category="linear"`, `symbol`, `interval` (`D` for daily, `240` for 4h), `start`/`end` (epoch ms), `limit<=1000` (use 1000). [F]
- Returns: `Vec<KlineBar { start_time, open, high, low, close, volume, turnover }>`, **descending (newest first), max 1000/page**. [F]
- Note: the Rust `KlineBar` struct from this endpoint has **no `tick_count`** field (that is a live-WS-only enrichment). Backfill rows get tick_count = 0 or NULL — see §4.4. [F: struct in API ref §1.1 vs live writer §0.5]

**Pagination**: page backward from `end=now` using `start`/`end` windows of (1000 * bar_seconds), or page forward from window start. Each call returns <=1000 bars; advance the cursor by the oldest `start_time` returned. Stop when returned `min(start_time) <= window_start` OR empty page. [I from "可通過 start/end 參數分頁拉取歷史數據"]

**Request count estimate** [I, arithmetic]:
- Daily, 18mo = ~548 bars/symbol => **1 page/symbol** (548 < 1000). 25 symbols => **~25 requests**. (24mo daily = ~730 => still 1 page.)
- 4h, 18mo = 6 bars/day * 548 days = ~3288 bars/symbol => ceil(3288/1000) = **4 pages/symbol**. 25 symbols => **~100 requests**.
- **Total RECOMMENDED (18mo, 25 sym): ~125 requests.** 12mo: ~25 daily (1 page) + ~75 4h (~3 pages) = ~100. 24mo, 50 sym: ~50 daily + ~250 4h = ~300.

**Time estimate** [I]: Market group = 120 req/s, IP = 600/5s = 120/s. Even at a deliberately conservative **2 req/s** (gentle, well under cap, leaves headroom for the live collector sharing the IP), 125 requests = **~65 seconds** of API time. Add per-symbol PG INSERT (tiny: 548 daily rows + 3288 4h rows per symbol = trivial batch). **Whole backfill completes in single-digit minutes.** This is exactly why R-2b §7 called it "the single highest-leverage unblock" vs waiting until ~2026-10 for live accumulation.

**Rate-limit discipline (FACT)**: retCode `10006 IpRateLimit` is retryable with `exchange_backoff` [F: API ref §4.2]. E1 should throttle to <=2-5 req/s and on `10006` apply exponential backoff. Backfill shares the IP with the live engine's market poller — **do NOT burst at 120 req/s**; a low steady rate is correct (time budget is already trivial).

---

## 4. Load strategy (idempotent, fail-closed, provenance-preserving)

### 4.1 INSERT (MUST match live writer's conflict policy)
```
INSERT INTO market.klines
  (ts, open_ts_ms, close_ts_ms, symbol, timeframe, open, high, low, close, volume, turnover, tick_count)
VALUES (...)
ON CONFLICT (symbol, timeframe, ts) DO NOTHING;
```
- `ON CONFLICT ... DO NOTHING` => idempotent (re-run safe), gap-fill only, never clobbers live rows. [F: matches market_writer.rs:268]
- Bind OHLC/volume/turnover as `real`/f32 (match live precision, §0.6).
- `ts` = `to_timestamp(start_time/1000)` (timestamptz); `open_ts_ms = start_time`; `close_ts_ms = start_time + bar_ms` (daily bar_ms=86400000, 4h=14400000). [I — confirm Bybit `start_time` is bar-open ms, consistent with live writer using `open_time_ms` for `ts`]

### 4.2 timeframe string
- Daily Bybit `D` -> store **`'1d'`** (E1 declares final choice in run report; §0.4).
- 4h Bybit `240` -> store **`'4h'`** (matches existing live 4h rows — REQUIRED so dedup + diagnostic align).

### 4.3 Provenance (DECISION — pick one, default = co-mingle-by-timeframe)
Because there is no source column (§0.1) and live-1m is the sensitive surface:
- **Former default, now gated by AEG**: backfill writes ONLY `1d` (new namespace) + `4h` (gap-fill). It never writes `1m`/`5m`/`15m`/`1h`. This may be acceptable only after AEG-S0/S1 decides whether timeframe namespace is enough for OHLCV provenance. E1 must not choose this default unilaterally.
- **OPTIONAL (if PM wants explicit provenance)**: a separate tiny ledger `market.kline_backfill_provenance(symbol, timeframe, min_ts, max_ts, source, fetched_at, n_rows)` written once per backfill run. This is a NEW table = MIT/E2 migration with Guard A/B/C + Linux PG dry-run => **out of E1 backfill scope**; hand back to PM if required. Do NOT add a column to `market.klines` inline.

### 4.4 tick_count for backfill rows
- The kline endpoint does not return per-bar trade count. Set `tick_count = NULL` (column is nullable) — **preferred** (honestly signals "not measured" vs a fake 0). Live rows have real tick_count; a NULL backfill tick_count is a clean, queryable provenance hint as a bonus. Do NOT fabricate tick_count.

### 4.5 Fail-closed (Root Principle 10 + CLAUDE.md hard boundary)
- Any non-zero `retCode` (except `10006` which retries with backoff) => **abort that symbol's fetch loudly, log, continue to next symbol, and report partial completion** — do NOT silently swallow. [F: CLAUDE.md "Bybit API timeout or nonzero retCode fails closed; do not add hidden retry paths"]
- API timeout => same: log + count as failed symbol; never insert partial/garbage.
- After the run, E1 MUST emit a coverage report: per symbol per timeframe `(min_ts, max_ts, n_rows, expected_bars, coverage_pct, n_failed_pages)`. This is the input to MIT's step-4 verify.
- The script must be a standalone read-only-market-data tool (Python utility or Rust bin) that does NOT touch the order/execution path, does NOT require live auth, and runs against the public market endpoint only.

---

## 5. ADR / governance compliance note (FACT)

- **This is Bybit-native, read-only, public market data.** Bybit's own historical klines via `GET /v5/market/kline` (no auth). It does NOT invoke the ADR-0033/0040 cross-venue gate — that gate governs **non-Bybit** (Binance) market data. Bybit market data is the baseline, always allowed. [F: ADR-0033 amends ADR-0006 to allow *Binance* market-data; Bybit market data was never restricted.]
- **No execution. No non-Bybit venue. No order/position/account endpoints.** Only `GET /v5/market/kline`. [F: scope of this spec]
- Aligns with the spirit of ADR-0033/0040 market-data-only posture (read-only auxiliary data for research/counterfactual), strictly inside the stronger Bybit-native baseline. [I]
- Root Principle 2 (read/write separation; research/learning mostly read-only): backfill is a read from Bybit + a write to the research data layer (`market.klines`), not to any live trading/state surface. Compliant. [F: §二 #2]
- No secrets/keys needed (public endpoint) => nothing to leak (CLAUDE.md §十一). [F]

---

## 6. Role chain + effort estimate

| Step | Owner | Deliverable | Effort (est) |
|---|---|---|---|
| 1. Spec (this doc) | MIT | spec + empirical klines schema + retention blocker | DONE |
| 2. **PRE-BACKFILL DECISION** (§7-A retention) | PM + operator + MIT + E2/E4 as needed | retention/storage/provenance decision (1095d / 400d / dedicated history table / ledger) + window sign-off (12/18/24mo) | gated by AEG-S1 |
| 3. Backfill script + BB API self-check | E1 only after PM opens scope | standalone read-only fetcher: paginate `GET /v5/market/kline` (D + 240), throttle <=2-5 req/s + 10006 backoff, `ON CONFLICT DO NOTHING` batch INSERT, fail-closed per-symbol, coverage report. BB API check: confirm `D`/`240` interval + start/end pagination + Market rate group against `docs/references/2026-04-04--bybit_api_reference.md`. | blocked until AEG gate |
| 4. Run backfill (Linux) | E1 only after PM opens scope | execute on `trade-core`; emit per-symbol coverage report | blocked until AEG gate |
| 5. Data-quality verify | MIT | empirical PG verify: coverage_pct per symbol/timeframe; gap audit; leak-free re-confirm (closed bars only); confirm retention did NOT reap (re-check min(ts) post next daily job); confirm no live-1m contamination; confirm `1d` string + dedup integrity | ~2h |
| 6. Re-run multi-day diagnostic on deep window | MIT | re-run R-2b's exact leak-free SQL on the deep window: (N,M) sweep + cross-sectional + funding reality + DSR deflation now that n>=30 is clearable; QC+MIT joint alpha go/no-go | ~3-4h |

**Critical path note**: Step 2 (retention decision) BLOCKS step 4. If E1 runs the backfill before retention is extended, the >12mo portion is reaped within 24h (§1.4). PM must sequence step 2 before step 4.

**Boundary with QC**: per R-2b §boundaries, the alpha go/no-go is a QC+MIT joint sign-off (QC owns alpha-validity / PSR / DSR significance; MIT owns sample-sufficiency / leakage / data feasibility). This spec + steps 4-6 deliver the MIT half (deep data + leakage clearance + sample-sufficiency); the edge call remains joint.

---

## 7. Open decisions handed to PM / operator (BLOCKERS + choices)

**7-A. RETENTION (BLOCKER — must resolve before step 4).**
- `klines` has `drop_after=365d` daily retention. >12mo backfill is reaped unless extended.
- MIT's earlier candidate path was `remove_retention_policy('market.klines')` then `add_retention_policy('market.klines', INTERVAL '1095 days')`, enabling 18-24mo. Under AEG this must be converted into a reviewed migration/change-control plan before any PG mutation. Confirm PG-growth acceptable (§3 capacity: 1m alone ~26M rows/3y, compressed after 14d — size on the 40TB NAS / 4-8GB PG working set before commit).
- Alternative (lowest risk): keep retention but set `drop_after=400d` and backfill 12mo only (floor unblock).

**7-B. WINDOW.** 12mo (floor, ~26 14d-periods) vs **18mo (MIT default, ~39 14d-periods + DSR headroom)** vs 24mo (stretch). Tied to 7-A.

**7-C. SYMBOL BREADTH.** Core 25 (MUST, sufficient — period-count is binding not breadth per R-2b §3) vs extend to ~40-50 liquid perps (second-order cross-sectional improvement). MIT recommends start with 25; revisit breadth only if cross-sectional becomes the lead hypothesis.

**7-D. PROVENANCE.** Default co-mingle-by-timeframe (no schema change, `1d`+`4h` only, live-1m untouched) vs optional provenance ledger table (= separate MIT/E2 migration, out of E1 scope). MIT recommends DEFAULT for speed; the timeframe-namespace firewall already protects the sensitive live-1m surface.

**7-E. `1d` string confirm.** MIT recommends `'1d'`; E1 declares final in run report so step-6 diagnostic queries the right value.

---

## Boundaries observed (this spec)
- READ-ONLY audit to produce spec: schema facts from live `\d market.klines` + `timescaledb_information` via `ssh trade-core docker exec trading_postgres psql` (non-interactive SSH `DATABASE_URL` empty — used docker exec per prior-run finding). 0 writes, 0 schema change, 0 backfill executed.
- No business code written; no existing doc modified. New spec file only.
- `git fetch` run + confirmed no pre-existing `2026-05-31--historical-kline-backfill-spec.md` and no prior kline-backfill ticket in `git log --all` before writing (NO-OP exit not triggered).
- fact / inference / assumption separated throughout ([F]/[I]/[A]).
- Bybit endpoint facts cross-checked against `docs/references/2026-04-04--bybit_api_reference.md` (CLAUDE.md §八 Bybit-facing mandate).

MIT AUDIT DONE: docs/execution_plan/specs/2026-05-31--historical-kline-backfill-spec.md

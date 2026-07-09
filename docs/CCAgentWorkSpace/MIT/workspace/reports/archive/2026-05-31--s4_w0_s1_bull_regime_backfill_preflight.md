# S4-W0-S1 Bull-Regime Funding/Price Backfill Preflight

**Date**: 2026-05-31
**Role**: MIT(default)
**Scope**: Track 4 2024 bull regime funding/price coverage preflight and execution-readiness.
**Mode**: read-only PG `SELECT` on `trade-core` + Bybit public market-data `GET`; 0 DB writes, 0 schema changes, 0 live/auth/order/execution changes.

## Verdict

**BLOCKED_ON_RETENTION**.

S4-W0-S1 is **not ready to execute a DB-writing backfill** into the existing tables. The API is not the blocker: Bybit public `funding/history` and `kline` returned 2024-11 `1000PEPEUSDT` funding and price rows. The hard blocker is storage retention:

- `market.funding_rates` has `drop_after = 180 days`. A 2024-11 funding backfill would be eligible for deletion on the next retention job.
- `market.klines` has `drop_after = 365 days`. A 2024-11 kline backfill would also be eligible for deletion on the next retention job.
- `panel.funding_rates_panel` has 14d retention and is a live panel surface, not a 2024 historical settlement table.

Secondary blocker: there is no production-ready standalone E1 backfill script that writes both Bybit funding history and 1d/4h klines into PG with coverage reporting. Existing code has public fetch helpers, but not the required idempotent historical DB writer/runbook.

## Evidence

### Existing PG Coverage

Read-only SQL evidence from `trade-core`:

| Table | Current coverage | 2024-11 rows | Retention |
|---|---:|---:|---|
| `market.funding_rates` | 1,892 rows, 25 symbols, 2026-04-05 10:00+02 to 2026-05-31 22:00+02 | 0 | 180d |
| `panel.funding_rates_panel` | 522,175 rows, 25 symbols, 2026-05-16 02:00:55+02 to 2026-05-31 22:34:40+02 | 0 | 14d |
| `market.klines` | live collector era only; `1m` 1,319,258 rows, `5m` 267,262 rows, `4h` 6,293 rows; no `1d` rows | 0 | 365d |
| `market.market_tickers` | current ticker recorder only | 0 | 90d |
| `trading.funding_settlements` | account settlement ledger, not public funding history | 0 | no relevant public-history role |

`1000PEPEUSDT` local price coverage exists only in 2026:

| Symbol | Timeframe | Rows | Min TS | Max TS |
|---|---:|---:|---|---|
| `1000PEPEUSDT` | `1m` | 14,080 | 2026-04-10 00:48+02 | 2026-05-30 14:48+02 |
| `1000PEPEUSDT` | `4h` | 82 | 2026-04-09 22:00+02 | 2026-05-30 10:00+02 |
| `1000PEPEUSDT` | `5m` | 2,930 | 2026-04-10 00:45+02 | 2026-05-30 14:45+02 |

`market.funding_rates` has no PEPE rows and no current-window funding event above 30% annualized. Its max current annualized rate is ~10.95%, matching the low-premium IR-floor regime noted in the cost-wall audit erratum.

### Bybit Public API Availability

Public no-auth calls confirm 2024-11 data is available from Bybit for `1000PEPEUSDT`:

- `GET /v5/market/instruments-info?category=linear&symbol=1000PEPEUSDT`: `retCode=0`, `status=Trading`, `fundingInterval=480`, `upperFundingRate=0.01`, `lowerFundingRate=-0.01`.
- `GET /v5/market/funding/history?...startTime=1730419200000&endTime=1733011200000`: `retCode=0`, 91 events, max funding rate `0.00122813` per settlement, annualized `1.34480235` (~134.5%), 52 events above 30% annualized.
- `GET /v5/market/kline?...interval=D`: `retCode=0`, 31 rows for the inclusive request window.
- `GET /v5/market/kline?...interval=240`: `retCode=0`, 181 rows for the inclusive request window.

So the 2024-11 PEPE/high-funding example is queryable via Bybit public API, but not present in local PG.

### Survivorship Context

`market.symbol_universe_snapshots` is usable as the survivorship-corrected symbol source:

- 450,436 rows, 935 distinct symbols.
- 293 distinct symbols are currently `Closed`/`Delivering` or `is_delisted_at_asof=true`.
- For instruments active during 2024-11, current latest snapshots show 481 symbols active in the window, of which 165 are now closed/delisted.
- Examples active in 2024-11 and now closed include `1000000CHEEMSUSDT`, `DOGUSDT`, `HPOS10IUSDT`, `HIPPOUSDT`, `TAIUSDT`, `SDUSDT`, and others.

This means S4 must use the S1 survivorship-corrected universe, not a current-survivor-only list.

## Readiness Assessment

S4-W0-S1 can be co-batched with S1-W1 only after the operator retention decision covers **both** price and funding history:

1. Extend `market.klines` retention before writing 2024 klines, or choose a separate research history table.
2. Extend `market.funding_rates` retention before writing 2024 funding, or choose a separate research funding-history table.
3. Build an E1 backfill script that writes:
   - `market.klines`: `1d` and `4h`, `ON CONFLICT (symbol, timeframe, ts) DO NOTHING`.
   - `market.funding_rates`: settlement rows, `ON CONFLICT (symbol, ts) DO NOTHING`.
   - per-symbol/per-table coverage report, failed-page report, and exact API request window.
4. Use the S1 survivorship-corrected symbol file. Current survivor-only is not acceptable.

Until then, running a DB-writing backfill would burn API work and then let Timescale retention silently reap the 2024 rows.

## Next Step

Do **not** schedule S4-W1-S1 backtest yet.

Required next actions:

- **Operator/PM gate**: decide retention/storage for 2024 history. The S1 kline retention gate must be expanded to include `market.funding_rates` or an explicit separate funding-history storage choice.
- **E1 script needed**: implement the public Bybit historical backfill writer. Existing `helper_scripts/canary/replay_funding_harvest.py` fetches public funding/kline data for replay but does not write PG, does not cover the S4 symbol universe, and is not a historical DB backfill tool.
- **BB API check**: low-risk but still required for final script review: confirm pagination semantics for `funding/history` max 200 rows and `kline` max 1000 rows, inclusive `start/end` handling, and rate-limit backoff.
- **MIT verify after backfill**: coverage by symbol/table/timeframe, no 2024 reaping after the next retention job, no live-1m contamination, and PEPE/high-funding rows present.

Proposed command shape after gates and script exist, **not runnable today**:

```bash
python3 helper_scripts/research/bybit_public_history_backfill.py \
  --category linear \
  --symbols-file docs/CCAgentWorkSpace/MIT/workspace/reports/<s1_survivorship_symbols>.json \
  --start 2024-11-01 \
  --end 2024-12-01 \
  --klines 1d,4h \
  --funding-history \
  --rate-limit-rps 2 \
  --on-conflict-do-nothing \
  --coverage-report /tmp/s4_w0_s1_coverage.json
```

That command must stay disabled until retention/storage is resolved and the script exists.

## Acceptance Mapping

- **AC-S4-W0-S1.1**: PASS for preflight. Local PG has 0 rows for 2024-11, but Bybit public API returns `1000PEPEUSDT` 2024-11 funding and price rows, including high-funding events above 30% annualized.
- **AC-S4-W0-S1.2**: BLOCKED. Co-batching with S1 is feasible at the API layer, but blocked by `market.funding_rates` 180d retention, `market.klines` 365d retention, and missing E1 DB-writer script.
- **AC-S4-W0-S1.3**: PASS. This preflight made 0 live-state changes and executed no DB writes. I did not run any `INSERT`, `UPDATE`, `DELETE`, DDL, `git add`, commit, push, stash pop, stash drop, order, auth, or execution command.

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s4_w0_s1_bull_regime_backfill_preflight.md

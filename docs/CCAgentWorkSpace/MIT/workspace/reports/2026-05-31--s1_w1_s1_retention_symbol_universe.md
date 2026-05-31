# MIT Report — S1-W1-S1 Retention Decision + Survivorship-Corrected Symbol Universe

**Date**: 2026-05-31 CEST
**Role**: MIT(default)
**Mode**: read-only investigation + synthesis; 0 commit, 0 push, 0 `git add`, 0 backfill, 0 schema change, 0 retention change
**Repo root**: `/Users/ncyu/Projects/TradeBot/srv`
**Task**: Alpha-Edge Research Program S1-W1-S1 — Track 1 pre-backfill retention/window/breadth decision + survivorship-corrected symbol universe.

---

## 0. Verdict

**MIT advisory PASS; S1-W1-S2 is NOT unlocked until operator signs the retention/window/breadth decision.**

Recommended operator decision:

| Decision | MIT recommendation |
|---|---|
| Retention | **Extend `market.klines` retention from 365d to 1095d** before any >12mo backfill. |
| Window | **18 months** (`2024-11-30` to `2026-05-31` as-of this report). |
| Primary analysis breadth | **Core 25 pinned scanner symbols** for first Track 1 TSMOM diagnostic. |
| 40-50 breadth | **Do not make 40-50 the first analysis breadth.** Keep as follow-up only if S1-W2 cross-sectional leg is explicitly breadth-limited. |
| Backfill symbol universe | Use the attached **full 18mo USDT LinearPerpetual survivorship universe** artifact (797 symbols, including 225 delisted/Closed overlap symbols). Primary analysis can still start with core25; data collection should not be survivor-only. |

**Blocking status**: retention remains at 365d. Running S1-W1-S2 now would load >12mo history and have the oldest portion reaped by the daily retention job.

Artifact:

- `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_survivorship_universe_18mo_usdt_perp.csv`

Artifact row check:

- 797 data rows + 1 header row.
- `recommended_tier` counts: `core25_pinned=25`, `historical_delisted_18mo=225`, `scanner_24h_dynamic=14`, `current_bybit_usdt_perp=533`.
- Delisted proof: 225 rows have `seen_delisted=t` / `latest_is_delisted_at_asof=t`.

---

## 1. Boundary Summary Loaded

FACT:

- Product hard boundary: Bybit is the only execution exchange; this task uses only read-only Bybit public market data and read-only PG queries.
- Live/order/auth/execution surfaces were not touched.
- `market.klines` retention is an operator hand-action gate; MIT does not change retention policy.
- Backfill execution is out of scope for S1-W1-S1 and remains blocked.
- Survivorship correction must come from `market.symbol_universe_snapshots`, not current survivors.

INFERENCE:

- The safe path is to decide retention before S1-W1-S2. Otherwise the research data load can silently become <=365d even if E1 successfully loads 18mo.

---

## 2. Current `market.klines` Retention And Sizing

Read-only PG evidence from `trade-core`, database `trading_ai`, user `trading_admin`, at `2026-05-31 22:34 CEST`.

### 2.1 Retention Policy

FACT:

| Item | Value |
|---|---|
| Hypertable | `market.klines` |
| Timescale chunks | 9 |
| Compression | enabled |
| Compression job | job `1003`, `policy_compression`, `compress_after = 14 days`, schedule `12:00:00` |
| Retention job | job `1013`, `policy_retention`, `drop_after = 365 days`, schedule `1 day` |
| Next retention run observed | `2026-06-01 18:18:32.73635+02` |
| Chunk range observed | `2026-04-02 02:00+02` to `2026-06-04 02:00+02` |
| Current rows older than 365d / 400d | `0 / 0` |

AC-S1-W1-S1.1 current-policy finding: **PASS**. Current policy is still 365d daily retention.

### 2.2 Current Row / Disk Sizing

FACT:

| Metric | Value |
|---|---:|
| Current rows | 1,707,879 |
| Observed data span | 56.360 days |
| Current hypertable size | 253,386,752 bytes (~242 MiB) |
| Current empirical bytes/row | 148.36 bytes/row |
| Rows/day, full 56d observed window | 30,303.18 |
| Rows/day, recent 7d | 46,007.57 |

FACT: rows by timeframe:

| Timeframe | Rows | Symbols | Min ts | Max ts | Rows/day window |
|---|---:|---:|---|---|---:|
| `1m` | 1,319,224 | 143 | 2026-04-05 14:00+02 | 2026-05-31 22:34+02 | 23,408.37 |
| `5m` | 267,229 | 143 | 2026-04-05 14:00+02 | 2026-05-31 22:30+02 | 4,741.96 |
| `15m` | 91,071 | 143 | 2026-04-05 14:00+02 | 2026-05-31 22:30+02 | 1,616.05 |
| `1h` | 23,889 | 143 | 2026-04-05 14:00+02 | 2026-05-31 22:00+02 | 424.07 |
| `4h` | 6,293 | 138 | 2026-04-05 14:00+02 | 2026-05-31 22:00+02 | 111.71 |

INFERENCE: using the current observed rows/day and bytes/row, retention extension sizing is:

| Scenario | Rows/year | Rows/3y | Estimated 3y size |
|---|---:|---:|---:|
| 56d average rate | 11.06M | 33.18M | ~4.6 GiB |
| Recent 7d rate | 16.79M | 50.38M | ~7.0 GiB |

ASSUMPTION:

- Estimated GiB uses the current mixed compressed/uncompressed empirical bytes/row. Future compression ratio, active-symbol count, and scanner coverage may drift. Treat 4.6-7.0 GiB as sizing, not a hard cap.

### 2.3 Backfill Additive Rows

INFERENCE:

Backfill itself is small compared with retaining live high-frequency klines:

| Symbols | 12mo daily+4h rows | 18mo daily+4h rows | 24mo daily+4h rows |
|---:|---:|---:|---:|
| 25 | 63,875 | 95,900 | 127,750 |
| 40 | 102,200 | 153,440 | 204,400 |
| 50 | 127,750 | 191,800 | 255,500 |
| 797 full survivorship universe | 2,036,335 | 3,057,292 | 4,072,670 |

INFERENCE:

- The real storage decision is not the daily/4h backfill payload; it is whether retaining existing/future `1m/5m/15m/1h/4h` rows for 1095d is acceptable.
- On current evidence, 1095d retention is a moderate single-digit-GiB table-size decision, not a NAS-capacity blocker.

---

## 3. Retention Recommendation

### Recommended: `1095d + 18mo`

MIT recommends **1095d retention** and **18mo backfill**.

Reasoning:

- FACT: current retention `drop_after=365 days` will delete chunks older than 365d on a daily job.
- INFERENCE: 18mo needs 1095d or equivalent retention exemption; 400d is not enough.
- INFERENCE: 18mo gives ~78 weekly periods and ~39 non-overlapping 14d periods, which clears the `n>=30` sample-sufficiency target for weekly/multi-day testing better than 12mo.
- INFERENCE: sizing impact is acceptable for the current data rate: ~33-50M rows / ~4.6-7.0 GiB over 3y based on current empirical row size.

### Alternatives

| Option | Verdict | Why |
|---|---|---|
| No change (`365d`) | **Reject for S1-W1-S2** | 18mo backfill will be reaped; 12mo edge chunks are also near boundary. |
| `400d` | **Accept only for 12mo floor** | Keeps a 12mo window with buffer, but does not unlock the recommended 18mo diagnostic. |
| Separate history hypertable | Defer | It avoids retaining high-frequency rows but requires a new schema/migration path and changes query surfaces; not needed unless operator rejects 1095d sizing. |

Operator-signable wording:

> Approve `market.klines` retention extension to `1095 days`, then run S1-W1-S2 for 18 months of Bybit public `1d` + `4h` klines using the survivorship-corrected universe artifact. No live/order/auth/execution surfaces are involved.

---

## 4. Window + Breadth Recommendation

AC-S1-W1-S1.2: **PASS**. Concrete values:

- Window: **18 months**.
- Primary Track 1 diagnostic breadth: **core 25 pinned scanner symbols**.
- Backfill symbol universe: **full survivorship-corrected 18mo USDT LinearPerpetual universe** (797 symbols), because the marginal data cost is small and this prevents survivor-only contamination.
- 40-50 breadth: **not recommended as the first analysis breadth**. Use it only if S1-W2 reports `breadth-limited` for cross-sectional momentum. Do not expand breadth just to create more correlated legs; period count remains the first-order constraint.

Core25 pinned list from `settings/risk_control_rules/scanner_config.toml`:

```text
BTCUSDT, ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT,
ADAUSDT, AVAXUSDT, LINKUSDT, DOTUSDT, POLUSDT,
LTCUSDT, BCHUSDT, NEARUSDT, UNIUSDT, ATOMUSDT,
ETCUSDT, FILUSDT, ICPUSDT, TRXUSDT, ARBUSDT,
OPUSDT, APTUSDT, SUIUSDT, TONUSDT, INJUSDT
```

FACT:

- Scanner config has `max_symbols = 40`.
- Latest `trading.scanner_snapshots` active set had 35 symbols.
- 24h scanner-active union had 39 symbols.

---

## 5. Survivorship-Corrected Symbol Universe

### 5.1 Table / Current State Evidence

FACT from `market.symbol_universe_snapshots`:

| Metric | Value |
|---|---:|
| Rows | 450,436 |
| Distinct linear perpetual symbols in table | 935 |
| First snapshot | 2026-05-07 01:17:48.12092+02 |
| Latest snapshot | 2026-05-31 22:20:01.363662+02 |
| Historical delisted rows | 141,428 |
| Historical delisted symbols | 293 |

FACT for latest **USDT LinearPerpetual** only:

| Latest status | `is_delisted_at_asof` | Symbols |
|---|---:|---:|
| `Trading` | false | 570 |
| `PreLaunch` | false | 2 |
| `Closed` | true | 278 |

FACT for USDT LinearPerpetual overlap by window:

| Window | Overlap symbols | Delisted/Closed overlap symbols | `delisted_at` inside window |
|---|---:|---:|---:|
| 12mo | 746 | 174 | 174 |
| 18mo | 797 | 225 | 225 |
| 24mo | 827 | 255 | 255 |

AC-S1-W1-S1.3: **PASS**. The 18mo universe contains 225 delisted/Closed overlap symbols. Pure current-survivor selection would omit them.

Sample 18mo delisted symbols from PG evidence:

```text
1000000CHEEMSUSDT, DOGUSDT, HPOS10IUSDT, 10000QUBICUSDT, DEGENUSDT,
OXTUSDT, CLOUDUSDT, SYNUSDT, BSUUSDT, FIOUSDT, RDNTUSDT, TRUUSDT
```

### 5.2 Bybit Public Lookup Cross-Check

FACT from Bybit public `/v5/market/instruments-info?category=linear` on 2026-05-31:

| Raw status query | Rows | Notes |
|---|---:|---|
| `Trading` | 676 | Includes USDT/USDC and dated futures. |
| `PreLaunch` | 2 | USDT LinearPerpetual. |
| `Delivering` | 0 | None returned. |
| `Closed` | 839 | Includes many dated `LinearFutures`; not all are target USDT perps. |

INFERENCE:

- The backfill target should be **USDT `LinearPerpetual`**, not all `category=linear`, because current scanner symbols are USDT perpetuals and dated futures would pollute Track 1.
- DB latest USDT LinearPerpetual counts align with the target subset: 570 Trading + 2 PreLaunch + 278 Closed.

### 5.3 Artifact

Generated artifact:

```text
docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_survivorship_universe_18mo_usdt_perp.csv
```

Columns:

```text
symbol, recommended_tier, in_core25_pinned, in_scanner_24h, latest_status,
seen_delisted, latest_is_delisted_at_asof, statuses, listed_at, delisted_at,
first_seen_ts, last_seen_ts, alive_from, alive_to, alive_days_in_18mo_window,
turnover_24h, last_price, base_coin, quote_coin, contract_type, tick_size,
qty_step, min_notional, latest_snapshot_ts, source_uri
```

Artifact counts:

| Tier | Rows |
|---|---:|
| `core25_pinned` | 25 |
| `historical_delisted_18mo` | 225 |
| `scanner_24h_dynamic` | 14 |
| `current_bybit_usdt_perp` | 533 |
| **Total** | **797** |

---

## 6. Derivation SQL

Canonical derivation for the artifact:

```sql
WITH params AS (
  SELECT now() - make_interval(months => 18) AS window_start,
         now() AS window_end
), core25(symbol, core_rank) AS (
  VALUES
    ($$BTCUSDT$$,1),($$ETHUSDT$$,2),($$SOLUSDT$$,3),($$XRPUSDT$$,4),($$DOGEUSDT$$,5),
    ($$ADAUSDT$$,6),($$AVAXUSDT$$,7),($$LINKUSDT$$,8),($$DOTUSDT$$,9),($$POLUSDT$$,10),
    ($$LTCUSDT$$,11),($$BCHUSDT$$,12),($$NEARUSDT$$,13),($$UNIUSDT$$,14),($$ATOMUSDT$$,15),
    ($$ETCUSDT$$,16),($$FILUSDT$$,17),($$ICPUSDT$$,18),($$TRXUSDT$$,19),($$ARBUSDT$$,20),
    ($$OPUSDT$$,21),($$APTUSDT$$,22),($$SUIUSDT$$,23),($$TONUSDT$$,24),($$INJUSDT$$,25)
), scanner_24h AS (
  SELECT DISTINCT sym AS symbol
  FROM trading.scanner_snapshots s
  CROSS JOIN LATERAL unnest(s.active_symbols) AS sym
  WHERE s.ts >= now() - make_interval(hours => 24)
), lifecycle AS (
  SELECT symbol,
         min(listed_at) FILTER (WHERE listed_at IS NOT NULL) AS listed_at,
         max(delisted_at) FILTER (WHERE delisted_at IS NOT NULL) AS delisted_at,
         bool_or(is_delisted_at_asof OR status IN ($$Delivering$$,$$Closed$$)) AS seen_delisted,
         string_agg(DISTINCT status, $$,$$ ORDER BY status) AS statuses,
         min(ts) AS first_seen_ts,
         max(ts) AS last_seen_ts
  FROM market.symbol_universe_snapshots
  WHERE exchange = $$bybit$$
    AND category = $$linear$$
    AND quote_coin = $$USDT$$
    AND contract_type = $$LinearPerpetual$$
  GROUP BY symbol
), latest AS (
  SELECT DISTINCT ON (symbol)
         symbol, ts AS latest_snapshot_ts, status AS latest_status,
         base_coin, quote_coin, contract_type, tick_size, qty_step, min_notional,
         is_delisted_at_asof AS latest_is_delisted_at_asof, source_uri
  FROM market.symbol_universe_snapshots
  WHERE exchange = $$bybit$$
    AND category = $$linear$$
    AND quote_coin = $$USDT$$
    AND contract_type = $$LinearPerpetual$$
  ORDER BY symbol, ts DESC
), latest_ticker AS (
  SELECT DISTINCT ON (symbol) symbol, turnover_24h, last_price
  FROM market.market_tickers
  ORDER BY symbol, ts DESC
)
SELECT l.symbol,
       CASE
         WHEN c.symbol IS NOT NULL THEN $$core25_pinned$$
         WHEN l.seen_delisted THEN $$historical_delisted_18mo$$
         WHEN s.symbol IS NOT NULL THEN $$scanner_24h_dynamic$$
         WHEN latest.latest_status IN ($$Trading$$,$$PreLaunch$$) THEN $$current_bybit_usdt_perp$$
         ELSE $$historical_overlap$$
       END AS recommended_tier,
       c.symbol IS NOT NULL AS in_core25_pinned,
       s.symbol IS NOT NULL AS in_scanner_24h,
       latest.latest_status,
       l.seen_delisted,
       latest.latest_is_delisted_at_asof,
       l.statuses,
       l.listed_at,
       l.delisted_at,
       GREATEST(COALESCE(l.listed_at,l.first_seen_ts,p.window_start), p.window_start) AS alive_from,
       LEAST(COALESCE(l.delisted_at,p.window_end), p.window_end) AS alive_to,
       latest_ticker.turnover_24h,
       latest_ticker.last_price,
       latest.base_coin,
       latest.quote_coin,
       latest.contract_type,
       latest.tick_size,
       latest.qty_step,
       latest.min_notional,
       latest.latest_snapshot_ts,
       latest.source_uri
FROM lifecycle l
CROSS JOIN params p
JOIN latest ON latest.symbol = l.symbol
LEFT JOIN core25 c ON c.symbol = l.symbol
LEFT JOIN scanner_24h s ON s.symbol = l.symbol
LEFT JOIN latest_ticker ON latest_ticker.symbol = l.symbol
WHERE COALESCE(l.listed_at,l.first_seen_ts) <= p.window_end
  AND COALESCE(l.delisted_at,p.window_end) >= p.window_start
ORDER BY COALESCE(c.core_rank, 999999),
         l.seen_delisted DESC,
         s.symbol IS NOT NULL DESC,
         latest_ticker.turnover_24h DESC NULLS LAST,
         l.symbol ASC;
```

Delisted proof query:

```sql
WITH lifecycle AS (
  SELECT symbol,
         min(listed_at) FILTER (WHERE listed_at IS NOT NULL) AS listed_at,
         max(delisted_at) FILTER (WHERE delisted_at IS NOT NULL) AS delisted_at,
         bool_or(is_delisted_at_asof OR status IN ($$Delivering$$,$$Closed$$)) AS seen_delisted,
         min(ts) AS first_seen_ts,
         max(ts) AS last_seen_ts
  FROM market.symbol_universe_snapshots
  WHERE exchange = $$bybit$$
    AND category = $$linear$$
    AND quote_coin = $$USDT$$
    AND contract_type = $$LinearPerpetual$$
  GROUP BY symbol
), params AS (
  SELECT now() - make_interval(months => 18) AS start_ts, now() AS end_ts
)
SELECT count(*) AS delisted_overlap_symbols
FROM lifecycle, params
WHERE seen_delisted
  AND COALESCE(listed_at, first_seen_ts) <= end_ts
  AND COALESCE(delisted_at, last_seen_ts, end_ts) >= start_ts;
```

Observed result: `225`.

---

## 7. Risks And Operator Decision Packet

FACT:

- Retention is currently 365d daily. It has not been changed by MIT.
- The 18mo symbol universe contains delisted symbols. Survivor-only fails S1-W1-S1.
- Direct Bybit `category=linear` includes non-target instruments; filter to `quote_coin='USDT'` and `contract_type='LinearPerpetual'`.

INFERENCE:

- 1095d retention is the best unblock because it lets Track 1 test 18mo without adding a new table or forked query path.
- A 400d compromise is only rational if operator rejects 1095d storage growth; it should force a 12mo-only backfill and weaker sample.
- Backfilling the full 797-symbol survivorship universe is feasible from a row-count standpoint; API time will be longer than the old 25-symbol estimate but still operationally small compared with the value of removing survivorship bias.

ASSUMPTION:

- Current row-size and row/day rates remain representative enough for sizing.
- S1-W1-S2 fetcher can handle the 797-symbol artifact with conservative public-market throttling and fail-closed per-symbol reporting.

Operator needs to choose one:

1. **Recommended**: approve `1095d` retention + `18mo` window + `core25` primary diagnostic + full 797-symbol survivorship backfill universe.
2. Floor fallback: approve `400d` retention + `12mo` window + same survivorship universe. This is weaker and should be marked as sample-size compromise.
3. No-change: do not run S1-W1-S2. Track 1 remains blocked.

S1-W1-S2 unlock condition:

- Operator approves a retention option.
- If option 1: E1 can proceed with 18mo `1d` + `4h` Bybit public kline backfill using the artifact.
- If option 2: E1 must reduce the window to 12mo.
- If option 3: S1-W1-S2 stays blocked.

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_retention_symbol_universe.md

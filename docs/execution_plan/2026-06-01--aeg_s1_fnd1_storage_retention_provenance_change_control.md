# AEG-S1-FND-1 Storage / Retention / Provenance Change-Control

Date: 2026-06-01
Status: PM package complete; operator decision and implementation gates still pending
Owner chain: PM -> MIT + PA -> E2/E4 review prep -> E1 only after a separate implementation scope
Mode: docs/design/read-only. No DB write, migration apply, retention mutation, runtime deploy, auth, order, collector runtime, backfill run, endpoint ingestion, alpha scoring, or promotion verdict.

## Verdict

AEG-S1-FND-1 is complete at the change-control decision-package layer.

Recommended path:

1. Use existing `market.klines` for OHLCV only after a reviewed `1095 days`
   retention mutation and DB provenance ledger are approved.
2. Use dedicated research-history storage for funding, open interest, and
   long-short history. Do not extend the raw 180d tables alone and call the
   result promotion-grade.
3. Keep the future Bybit historical writer, DB mutation, endpoint ingestion, and
   alpha scoring blocked until the operator signs the storage choice and the
   E2/E4 migration/change-control gates pass.

## 1. Source Facts

### 1.1 Schema vs Runtime Truth

`V002__market_tables.sql` comments describe `market.klines`,
`market.funding_rates`, `market.open_interest`, and
`market.long_short_ratio` as permanent-retention surfaces. That comment is not
the active truth. `V006__timescaledb_policies.sql` installs the actual Timescale
retention policies:

| Surface | V006 policy | FND-1 meaning |
|---|---|---|
| `market.klines` | 14d compression, 365d retention | 18mo history can be reaped unless retention is changed first. |
| `market.funding_rates` | 180d retention | 18mo funding cannot persist in the current raw table without a gate. |
| `market.open_interest` | 180d retention | 18mo OI cannot persist in the current raw table without a gate. |
| `market.long_short_ratio` | 180d retention | 18mo long-short cannot persist in the current raw table without a gate. |
| `market.market_tickers` | 7d compression, 90d retention; REF-21 cron default prune is 45d | Not a historical mark/index/basis source. |

FND-1 uses V006 plus live Linux reflection as the source of truth.

### 1.2 Linux Read-Only Reflection

Read-only reflection from `trade-core`, database `trading_ai`, at
`2026-06-01 00:36 CEST`:

| Surface | Rows / symbols | Min ts | Max ts | Size | Active policy |
|---|---:|---|---|---:|---|
| `market.klines` | 1,712,754 rows / 143 symbols | 2026-04-05 14:00+02 | 2026-06-01 00:32+02 | 243 MiB | 365d retention, 14d compression |
| `market.funding_rates` | 1,892 rows / 25 symbols | 2026-04-05 10:00+02 | 2026-05-31 22:00+02 | 864 KiB | 180d retention |
| `market.open_interest` | 158,000 rows / 25 symbols | 2026-04-05 14:40+02 | 2026-06-01 00:25+02 | 23 MiB | 180d retention |
| `market.long_short_ratio` | 13,473 rows / 25 symbols | 2026-04-05 15:00+02 | 2026-06-01 00:00+02 | 5.6 MiB | 180d retention |
| `market.market_tickers` | not counted in this check | not sampled | not sampled | 2.3 GiB | 90d Timescale + 45d REF-21 prune default |

`_sqlx_migrations` head on Linux is `V115`, `success=true`. Linux source was on
`main` at `4eec18e8ace3` during the reflection.

Timeframe breakdown for `market.klines`:

| Timeframe | Rows | Symbols | Current finding |
|---|---:|---:|---|
| `1m` | 1,323,168 | 143 | Live collector era only; do not backfill under S1. |
| `5m` | 268,031 | 143 | Live collector era only. |
| `15m` | 91,342 | 143 | Live collector era only. |
| `1h` | 23,955 | 143 | Live collector era only. |
| `4h` | 6,293 | 138 | Existing 2026 rows only; possible S1 historical gap-fill after gate. |

No local 18mo price/funding/OI/long-short history is present today.

### 1.3 Existing Writer / Client Posture

| Area | Current posture | FND-1 consequence |
|---|---|---|
| Rust `market.klines` writer | Inserts raw OHLCV with `ON CONFLICT (symbol, timeframe, ts) DO NOTHING`; no row provenance fields. | Raw-table OHLCV needs an external DB provenance ledger and artifacts. |
| Rust funding/OI/long-short poller | Polls latest row per symbol (`limit=1`), not historical pages. | Not a historical backfill tool. |
| Rust OI / long-short client | Lacks historical `start/end` and cursor pagination args. | Not ready for 18mo ingestion. |
| Rust parsers | Missing/failed numeric fields can default to `0.0`. | AEG evidence runs need strict parsers that turn parse failure into coverage failure. |
| Python replay public client | Isolated from production, allowlists kline/tickers/orderbook, `_KLINE_LIMIT=200`. | Safer base for public-only extension, but incomplete for funding/OI/long-short and price-only klines. |
| `replay_funding_harvest.py` | 30d Stage 0R harness, public GET only, no PG writes. | Useful reference, not a production DB writer. |
| REF-21 microstructure recorder | Locally records current ticker/orderbook snapshots. | Recent replay aid only; not Bybit historical ticker history. |

## 2. Storage Decision

### 2.1 OHLCV Recommendation

Choose `market.klines` with a reviewed `1095 days` retention policy for primary
OHLCV history.

Allowed first historical writes after gates:

- `1d` full 18mo survivorship-corrected collection.
- `4h` full 18mo survivorship-corrected collection or gap-fill.

Not allowed in the first S1 writer:

- Historical `1m` backfill.
- Any inference that 4h co-mingled rows are promotion-grade without run
  manifest, coverage report, and DB provenance ledger.
- Any reliance on artifact-only provenance for promotion if the DB rows cannot
  be reconstructed to a source run.

Required provenance mode:

- `market.klines` remains the query surface.
- A future migration must create or reuse an append-only DB provenance ledger
  keyed by run/table/endpoint/symbol/timeframe/time window. The exact table name
  is left to the V### design, but the ledger must preserve `run_id`,
  `git_sha`, `git_dirty`, endpoint, request start/end, parser version, source
  URI, row counts, child artifact digest, and coverage status.

Rationale: this keeps existing OHLCV consumers simple while preventing silent
promotion from anonymous co-mingled rows.

### 2.2 Funding / OI / Long-Short Recommendation

Choose dedicated research-history hypertables for funding, open interest, and
long-short history.

Working names for the future V### design:

- `research.alpha_funding_rates_history`
- `research.alpha_open_interest_history`
- `research.alpha_long_short_ratio_history`

The actual schema name can change during MIT migration design, but the storage
contract cannot lose these properties:

| Surface | Required row identity | Required provenance columns |
|---|---|---|
| Funding | category, symbol, funding timestamp | `run_id`, source endpoint, request window, `fetched_at`, parser version, payload hash/digest, funding interval minutes when available |
| Open interest | category, symbol, interval, timestamp | `run_id`, source endpoint, request window, `fetched_at`, parser version, cursor lineage, payload hash/digest |
| Long-short | category, symbol, period, timestamp | `run_id`, source endpoint, request window, `fetched_at`, parser version, cursor lineage, payload hash/digest |

If the operator rejects dedicated tables, the fallback is raw-table retention
extension plus an append-only DB provenance ledger. That fallback requires MIT
and E2 to prove that every promotion row can be joined back to an exact run and
that retention will not reap the history. Artifact-only provenance is not
acceptable for promotion-grade funding/OI/long-short because AEG-S0 already
forbids co-mingled raw rows without row-level or DB-level provenance.

### 2.3 Explicit Exclusions

These remain excluded from 18mo Alpha-Edge promotion evidence:

- `panel.funding_rates_panel`, `panel.oi_delta_panel`, `panel.basis_panel`, and
  sibling `panel.*` 14d derived surfaces.
- `market.market_tickers.index_price` and `market.market_tickers.mark_price`
  until the FND-4 fix-vs-bypass design lands.
- Bybit `tickers` endpoint as historical mark/index/funding history. It is a
  current snapshot endpoint; local history exists only where this system
  recorded it forward in time.
- News/X/Reddit/narrative stores as primary promotion evidence.

## 3. Change-Control Gates

Before any migration, writer, or retention mutation:

1. Operator signs the storage choice:
   `market.klines 1095d` yes/no, and funding/OI/long-short dedicated research
   storage vs raw-table+ledger fallback.
2. MIT updates sizing using Linux reflection: Timescale jobs, policies, chunks,
   table sizes, min/max timestamps, row rates, compression, and disk headroom.
3. BB approves endpoint semantics and rate discipline for the future writer.
4. PM reserves the V### number after checking current SQL head and open V###
   design reservations.
5. E2/E4 review the migration/change-control plan before apply.

Migration requirements if storage changes:

- Guard A before every `CREATE TABLE IF NOT EXISTS`.
- Guard B before type-sensitive `ADD COLUMN IF NOT EXISTS`.
- Guard C for load-bearing indexes.
- Linux PG dry-run before implementation sign-off.
- Idempotency double-apply test.
- Rollback SQL or rollback runbook in the same review packet.
- No Mac-only PG inference as sign-off evidence.

Retention-mutation requirements:

- Future SQL must first reflect the existing Timescale retention job and exact
  Timescale function signatures on Linux.
- Future SQL must remove/replace or alter the policy in an idempotent way, then
  reflect that only one active retention policy exists for the target
  hypertable.
- Rollback must restore the prior policy (`market.klines` 365d; raw
  funding/OI/long-short 180d if those are changed).
- Post-apply verification must capture the job config and a row older than the
  previous retention threshold surviving the next retention cycle before the
  history is trusted.

## 4. Future E1 Writer Requirements

This section is not authorization to implement. It defines the gate for the
next scoped implementation task.

The future writer must:

- Use a public-only Bybit client path. Extending the isolated Python replay
  public client is the preferred starting point; a Rust facade is acceptable
  only after BB proves it cannot touch auth/private/order endpoints.
- Force a gentle 2-5 requests/sec default throttle for AEG backfill.
- Implement endpoint-specific pagination guards, non-advance cursor guards, and
  max-page guards.
- Treat timeout, final nonzero `retCode`, parse failure, cursor non-advance, or
  unexpected row shape as coverage failure, not fabricated data.
- Use strict parsers. No missing numeric field may silently become `0.0`.
- Emit `${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<run_id>/` with
  `manifest.json`, `artifact_index.json`, coverage, failed-page report, child
  digests, row counts, request windows, and feature-lineage hooks.
- Update `helper_scripts/SCRIPT_INDEX.md` if a new helper script is added.

Coverage gates inherited from AEG-S0:

| Surface | Minimum gate |
|---|---|
| Primary OHLCV regime/scoring bars | `coverage_pct >= 0.98` per symbol/effective lifetime and no missing row inside signal lookback. |
| Funding/OI/long-short overlays | `coverage_pct >= 0.95`; below gate means the overlay is unavailable and cannot support promotion. |
| Feature lineage | `leak_violation_count = 0` for every promoted slice. |

## 5. Operator Decision Card

The next unlock decision is:

1. Approve `market.klines` retention extension to `1095 days` for OHLCV history?
2. Approve dedicated research-history tables for funding/OI/long-short, instead
   of extending raw tables alone?
3. Confirm first S1 collection scope: 18mo full survivorship-corrected
   collection, with core25 as the primary first analysis cohort.
4. Confirm `S1-W1-S2` writer remains locked until the chosen storage path has a
   reviewed V###/rollback/verification packet.

If any answer is negative, FND-1 stays design-only and the writer/scoring chain
remains blocked.

## 6. Completion Status

Complete now:

- Storage/retention/provenance decision package.
- Linux read-only baseline for the target market surfaces.
- Recommended path for OHLCV and funding/OI/long-short.
- Change-control gates for future migration and writer work.

Not complete and not authorized:

- Timescale retention mutation.
- New research-history schema or provenance ledger.
- Bybit historical DB writer.
- 18mo backfill.
- Mark/index/premium price-kline ingestion.
- Listing collector IMPL.
- Alpha scoring, robustness matrix, promotion report, or candidate verdict.

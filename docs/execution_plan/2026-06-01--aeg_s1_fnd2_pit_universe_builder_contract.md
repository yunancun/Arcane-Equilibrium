# AEG-S1-FND-2 PIT Universe Builder Contract

Date: 2026-06-01
Status: PM/MIT contract complete; implementation still blocked until scoped separately
Owner chain: PM -> MIT -> PA -> E1 only after scoped implementation task
Mode: docs/design/read-only. No DB write, backfill, endpoint ingestion, runtime deploy, auth, order, collector runtime, alpha scoring, or promotion verdict.

## Verdict

FND-2 defines the point-in-time universe builder contract. MIT read-only audit
returned with no file/git/DB/runtime changes, and the builder must use
`market.symbol_universe_snapshots` as the source of truth and must reject any
current-survivor-only shortcut.

The existing 797-row 18mo USDT LinearPerpetual CSV is accepted as seed evidence
and a regression check, not as the permanent builder source.

Approved upstream decision:

- FND-1 storage branch approved on 2026-06-01.
- First collection scope remains full 18mo survivorship-corrected collection,
  with core25 as the first primary analysis cohort.

## 1. Inputs

Required fixed parameters:

- `run_id`
- `asof_utc`
- `window_start_utc`
- `window_end_utc`
- `closed_bar_cutoff_utc`

The builder may offer CLI defaults, but final artifact generation cannot depend
on an implicit `now()`.

Required DB source:

| Source | Required use |
|---|---|
| `market.symbol_universe_snapshots` | PIT Bybit symbol status, listing/delisting, payload hash, source URI, payload JSON. |
| `trading.scanner_snapshots` | Operational scanner-active overlap only; not sufficient by itself. |
| `market.market_tickers` | Latest liquidity/tier comparison only when locally recorded; not a PIT alpha feature source. |

Seed/regression artifact:

```text
docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--s1_w1_s1_survivorship_universe_18mo_usdt_perp.csv
sha256:fbf14a3f1fb52fd0e963ab3560323e0cc11cbb7e4f730439c722cec7e2364c23
rows: 797 data rows, 798 lines including header
```

Seed tier counts:

| Tier | Rows |
|---|---:|
| `core25_pinned` | 25 |
| `historical_delisted_18mo` | 225 |
| `scanner_24h_dynamic` | 14 |
| `current_bybit_usdt_perp` | 533 |

The seed has zero missing `alive_from` / `alive_to` fields and includes 225
delisted/closed overlap symbols.

## 2. Source Contract

`market.symbol_universe_snapshots` must provide:

- `ts`
- `exchange='bybit'`
- `category='linear'`
- `symbol`
- `status`
- `base_coin`, `quote_coin`, `contract_type`
- `tick_size`, `qty_step`, `min_notional`
- `listed_at`, `delisted_at`
- `is_delisted_at_asof`
- `source_uri`
- `payload_hash`
- `payload_jsonb`

The table contract is V058: primary key `(ts, exchange, category, symbol)` and
symbol/time lookup index `(exchange, category, symbol, ts DESC)`.

Target universe filter for S1:

```text
exchange = bybit
category = linear
quote_coin = USDT
contract_type = LinearPerpetual
window = approved 18mo window
```

Statuses must include `Trading`, `PreLaunch`, `Delivering`, and `Closed` where
available, and the builder must also treat raw `Settled` / `Delisted` values as
delisted proof if they appear. Querying only Bybit's default `Trading` status
fails the FND-2 contract.

## 3. Builder Algorithm

For each target analytical window:

1. Build `lifecycle` per symbol from all relevant snapshots with `ts <= asof_utc`:
   - `listed_at = min(listed_at) FILTER (listed_at IS NOT NULL)`
   - `delisted_at = max(delisted_at) FILTER (delisted_at IS NOT NULL)`
   - `seen_delisted = bool_or(is_delisted_at_asof OR status IN ('Delivering','Closed','Settled','Delisted'))`
   - `statuses_seen = distinct status set`
   - `first_seen_ts = min(ts)`
   - `last_seen_ts = max(ts)`
2. Build `latest` per symbol with `DISTINCT ON (symbol) ORDER BY ts DESC` and
   retain source metadata.
3. Join cohort labels only:
   `core25_pinned`, `scanner_active_asof`, `historical_delisted`,
   `current_survivor_comparison_only`, `full_survivorship`, and optionally
   `top_liquidity_40_50` only when the liquidity source is PIT-documented.
4. Include a symbol when its tradable lifetime intersects the analytical window:
   - `coalesce(listed_at, first_seen_ts) <= window_end`
   - `coalesce(delisted_at, last_seen_ts, window_end) >= window_start`
5. Compute effective lifetime:
   - `alive_from = greatest(coalesce(listed_at, first_seen_ts, window_start), window_start)`
   - `alive_to = least(coalesce(delisted_at, window_end), window_end)`
6. Exclude any symbol where `alive_from > alive_to`.
7. Mark missing lifecycle as `unknown_lifetime` only when neither source
   timestamps nor exchange lifecycle fields can bound the window. Unknown
   lifetime rows are diagnostics-only unless MIT approves an explicit exclusion.

The builder must not pad early history before `alive_from`, and must not extend
rows after `alive_to`.

`PreLaunch` rows are universe metadata. They are not scoring-ready OHLCV unless
closed bars exist after the launch/trading transition.

## 4. Output Artifact

The future builder writes under:

```text
${OPENCLAW_DATA_DIR:-/tmp/openclaw}/alpha_history_runs/<run_id>/
```

Required artifact files:

| File | Required | Purpose |
|---|---|---|
| `universe.csv` or `universe.parquet` | yes | PIT universe rows. |
| `universe_summary.json` | yes | Counts, window, source snapshot range, delisted proof. |
| `manifest.json` | yes | AEG run manifest with child digests. |
| `artifact_index.json` | yes | Path, byte size, row count, schema version, digest. |

Required universe columns:

```text
run_id, universe_id, asof_utc, exchange, category, symbol, status,
status_raw, status_class, recommended_tier, cohort_ids,
current_survivor_only_comparison, in_core25_pinned, in_scanner_window,
listed_at_utc, delisted_at_utc, first_seen_ts_utc, last_seen_ts_utc,
alive_from_utc, alive_to_utc, alive_days_in_window,
unknown_lifetime, is_delisted_at_asof, seen_delisted, statuses_seen,
base_coin, quote_coin, contract_type, tick_size, qty_step, min_notional,
source_uri, source_snapshot_ts_utc, source_payload_hash,
included, inclusion_reason, exclusion_reason
```

`universe_id` must be deterministic from window, source table, source snapshot
max timestamp, query/schema version, and ordered row digest.

`universe_summary.json` must include row counts by status/cohort, delisted proof
count, unknown-lifetime count, source snapshot range, and seed CSV digest when
the seed regression is run.

## 5. Acceptance Gates

| Gate | Requirement |
|---|---|
| PIT source | `universe_sources` in manifest includes `market.symbol_universe_snapshots`. |
| Lifetime mask | 100% of included symbols have `alive_from_utc` and `alive_to_utc`, or an explicit `unknown_lifetime` exclusion. |
| Survivor rejection | If the window contains closed/delisted symbols, at least one included row has `seen_delisted=true` or `status IN ('Delivering','Closed')`; otherwise the run must prove none exist. |
| Current-survivor shortcut | Any universe containing only current scanner/trading symbols fails. |
| Unsafe fallback route | AEG evidence cannot use `_fetch_historical_universe_snapshot_sync` current-scanner fallback/truncation or any `max_symbols` shortcut. |
| Seed regression | Initial 18mo run must compare against the 797-row seed and explain count/tier drift. |
| Source provenance | Every included row has `source_uri`, `source_snapshot_ts_utc`, and `source_payload_hash`. |
| Coverage integration | Expected OHLCV/funding/OI/long-short rows are computed after lifetime masking. |
| Feature safety | `market.market_tickers` liquidity fields can sort tiers but cannot become PIT alpha features. |

## 6. Blocked Work

Still blocked after this contract:

- Any historical DB writer.
- Any DB retention mutation or migration apply.
- Any alpha scoring or promotion verdict.
- Any claim that the seed CSV alone is sufficient for future runs.
- Any current-survivor-only backfill scope.

## 7. Next Implementation Gate

Future E1 implementation scope may open only after PM names it explicitly.

Minimum implementation requirements:

- Read-only PG query by default.
- No DB writes.
- Deterministic output artifacts with SHA256 digests.
- Unit tests for delisted inclusion, lifetime masking, current-survivor rejection,
  and seed regression counting.
- MIT review of generated universe rows before any S1-W1-S2 backfill writer uses
  them.

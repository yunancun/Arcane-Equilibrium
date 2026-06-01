# AEG-S1 MIT Storage Migration-Design Packet

Date: 2026-06-01
Status: MIT design packet complete; no SQL migration file created and no DB mutation authorized
Owner chain: PM -> MIT -> E2/E4 review prep -> E1 only after explicit implementation approval
Mode: docs/design/read-only plus Linux read-only reflection. No migration apply, DB write, retention mutation, runtime deploy, auth, order, endpoint ingestion, backfill run, collector runtime, alpha scoring, or promotion verdict.

## Verdict

Use `V125__aeg_alpha_history_storage.sql` as the design-level reservation for
the approved FND-1 storage branch.

Reasoning:

- Actual `sql/migrations/` head is `V115`.
- `V116` is held for M7 decay detector.
- `V117` is reserved for ADR-0046 funding_arb V3.
- Existing planning notes preserve `V118-124` for M5/M7/M12/M13 and possible
  collector audit-ledger follow-ups.
- Choosing `V125` avoids colliding with those visible reservations while not
  creating a SQL file before implementation approval.

This packet is a migration-design packet only. It does not reserve execution,
does not apply a migration, and does not mutate Linux PG.

## 1. Linux Read-Only Reflection

Reflection target: `trade-core`, database `trading_ai`.

Snapshot time: `2026-06-01 10:26 CEST`.

| Fact | Result |
|---|---|
| PostgreSQL | `16.11` |
| TimescaleDB | `2.26.1` |
| `_sqlx_migrations` head | `V115`, success |
| `research` schema | absent |
| `market.klines` policy | compression after 14 days, retention after 365 days |
| `market.funding_rates` policy | retention after 180 days |
| `market.open_interest` policy | retention after 180 days |
| `market.long_short_ratio` policy | retention after 180 days |

Observed table posture:

| Surface | Rows / symbols | Min ts | Max ts | Size / note |
|---|---:|---|---|---:|
| `market.klines` | 1,738,234 / 143 | 2026-04-05 14:00+02 | 2026-06-01 10:26+02 | 260,620,288 bytes |
| `market.funding_rates` | 1,944 / 25 | 2026-04-05 10:00+02 | 2026-06-01 10:00+02 | 909,312 bytes |
| `market.open_interest` | 160,975 / 25 | 2026-04-05 14:40+02 | 2026-06-01 10:20+02 | 24,707,072 bytes |
| `market.long_short_ratio` | 13,723 / 25 | 2026-04-05 15:00+02 | 2026-06-01 10:00+02 | 5,906,432 bytes |
| `market.news_signals` | 51,685 / 2 sources | 2025-06-18 15:55:20+02 | 2026-06-01 10:01:53+02 | 57,827,328 bytes |
| `market.symbol_universe_snapshots` | 461,657 / 936 | 2026-05-07 | 2026-06-01 10:20+02 | normal table, about 670 MB |

`market.klines` timeframe split:

| Timeframe | Rows | Symbols | Max ts |
|---|---:|---:|---|
| `1m` | 1,342,846 | 143 | 2026-06-01 10:26+02 |
| `5m` | 272,013 | 143 | 2026-06-01 10:25+02 |
| `15m` | 92,674 | 143 | 2026-06-01 10:15+02 |
| `1h` | 24,304 | 143 | 2026-06-01 10:00+02 |
| `4h` | 6,397 | 138 | 2026-06-01 10:00+02 |

Current `market.symbol_universe_snapshots` status evidence:

| Status | Rows | Symbols | Notes |
|---|---:|---:|---|
| `Trading` | 316,058 | 649 | includes current and historical observations |
| `Closed` | 144,944 | 293 | has delisting proof |
| `PreLaunch` | 655 | 2 | metadata only, not scoring-ready bars |

## 2. Schema Decision

Create a new `research` schema for AEG alpha-history storage.

Recommended surfaces:

- `research.alpha_history_ingest_runs`
- `research.alpha_history_ingest_pages`
- `research.alpha_klines_provenance`
- `research.alpha_funding_rates_history`
- `research.alpha_open_interest_history`
- `research.alpha_long_short_ratio_history`

Rationale:

- These tables are not live market writer truth like `market.*`.
- They are not short-retention derived panels like `panel.*`.
- They are not model-training state like `learning.*`.
- `research.*` makes the promotion-grade historical evidence boundary explicit.

Fallback if governance rejects a new schema: `learning.alpha_*`. MIT recommends
against that fallback because it blurs market-data lineage with model state.

## 3. Run And Page Ledger Design

### `research.alpha_history_ingest_runs`

Purpose: one row per accepted AEG historical collection run.

Recommended core fields:

| Field | Type recommendation | Meaning |
|---|---|---|
| `run_id` | `TEXT PRIMARY KEY` | Accepts UUID, ULID, or artifact run IDs. Must be non-empty. |
| `program` | `TEXT` | Example: `aeg_s1`. |
| `storage_branch` | `TEXT` | Example: `fnd1_approved_klines_1095d_research_history`. |
| `window_start` / `window_end` | `TIMESTAMPTZ` | Analytical collection window. |
| `artifact_root` | `TEXT` | Artifact directory, if any. |
| `manifest_sha256` | `BYTEA` or checked lowercase hex `TEXT` | Digest of `manifest.json`. |
| `git_sha` | `TEXT` | Source checkout. |
| `git_dirty` | `BOOLEAN` | Source dirty flag. |
| `status` | `TEXT` | `planned`, `running`, `accepted`, `failed`, `superseded`. |
| `created_at` / `completed_at` | `TIMESTAMPTZ` | Run lifecycle timestamps. |

Decision: use `TEXT` for `run_id` in V125 design. AEG artifacts may use UUID,
ULID, or deterministic run labels, and forcing UUID now would create avoidable
adapter work. A later migration can add a generated UUID surrogate if needed.

### `research.alpha_history_ingest_pages`

Purpose: endpoint/page-level provenance and coverage reconstruction.

Recommended key: `(run_id, page_id)` where `page_id` is deterministic from
endpoint, symbol, interval, request window, cursor, and page sequence.

Required fields include:

- `run_id`
- `page_id`
- `endpoint_id`
- `category`
- `symbol`
- `timeframe_or_period`
- `request_start`
- `request_end`
- `cursor_in`
- `cursor_out`
- `ret_code`
- `ret_msg`
- `http_status`
- `payload_sha256`
- `artifact_sha256`
- `expected_rows`
- `observed_rows`
- `coverage_pct`
- `coverage_status`
- `fetched_at`
- `parser_version`
- `error`

Coverage status must be constrained to a small vocabulary such as:

- `pass`
- `partial`
- `failed`
- `skipped`
- `not_applicable`

## 4. OHLCV Provenance Without Row-Shape Change

Do not alter `market.klines` row shape for AEG provenance.

Instead, add:

```text
research.alpha_klines_provenance
```

Purpose: append-only DB provenance ledger for OHLCV rows written into
`market.klines`.

Recommended identity:

```text
run_id, endpoint_id, category, symbol, timeframe, window_start, window_end
```

Required fields:

- `storage_surface = 'market.klines'`
- `request_start`
- `request_end`
- `parser_version`
- `git_sha`
- `git_dirty`
- `payload_sha256`
- `artifact_sha256`
- `expected_rows`
- `observed_rows`
- `coverage_pct`
- `coverage_status`
- `created_at`

This keeps existing OHLCV consumers stable while making AEG promotion rows
reconstructable to a source run and artifact digest.

## 5. Dedicated Research History Tables

### Funding

Target:

```text
research.alpha_funding_rates_history
```

Hypertable time column: `funding_ts`.

Recommended identity:

```text
category, symbol, funding_ts, run_id
```

Use `run_id` in the identity so repeated runs preserve exact lineage. Consumers
should select rows from accepted runs rather than silently overwriting past run
evidence.

Required fields:

- `run_id`
- `category`
- `symbol`
- `funding_ts`
- `funding_rate`
- `funding_interval_minutes`
- `source_endpoint`
- `request_start`
- `request_end`
- `fetched_at`
- `parser_version`
- `payload_sha256`
- `artifact_sha256`

### Open Interest

Target:

```text
research.alpha_open_interest_history
```

Hypertable time column: `ts`.

Recommended identity:

```text
category, symbol, interval_time, ts, run_id
```

Required fields:

- `run_id`
- `category`
- `symbol`
- `interval_time`
- `ts`
- `open_interest`
- `source_endpoint`
- `request_start`
- `request_end`
- `cursor_lineage`
- `fetched_at`
- `parser_version`
- `payload_sha256`
- `artifact_sha256`

### Long-Short Ratio

Target:

```text
research.alpha_long_short_ratio_history
```

Hypertable time column: `ts`.

Recommended identity:

```text
category, symbol, period, ts, run_id
```

Required fields:

- `run_id`
- `category`
- `symbol`
- `period`
- `ts`
- `buy_ratio`
- `sell_ratio`
- `source_endpoint`
- `request_start`
- `request_end`
- `cursor_lineage`
- `fetched_at`
- `parser_version`
- `payload_sha256`
- `artifact_sha256`

## 6. Timescale Policies And Indexes

For new research history hypertables:

| Policy | Recommendation |
|---|---|
| chunk interval | 7 days |
| compression | after 30 days |
| retention | 1095 days |

Reason: the current Alpha-Edge evidence horizon is 18 months, while FND-1
approved a 1095d storage branch for historical research evidence. Permanent
archive policy can be designed later; V125 should use 1095d.

Recommended indexes:

- `(symbol, timeframe_or_period, ts DESC)` or surface-specific equivalent
- `(run_id, symbol, ts)`
- `(coverage_status)` partial or covering index for `coverage_status <> 'pass'`
  on run/page/provenance ledger tables
- surface-specific hot lookup indexes for endpoint replay and coverage reports

## 7. Guard Requirements

V125 must be fail-closed and idempotent.

Required guards:

| Guard | Requirement |
|---|---|
| Timescale preguard | TimescaleDB extension must exist. Do not silently skip hypertable policy work. |
| Guard A | Before every `CREATE TABLE IF NOT EXISTS`, verify required columns and types if the table already exists. |
| Guard B | Type-sensitive fields must be reflected: `run_id`, digests, timestamps, numerics, booleans. |
| Guard C | Verify load-bearing indexes and Timescale policies after creation. |
| Retention guard | Reflect existing `market.klines` retention, replace idempotently, then assert exactly one retention job with `drop_after = 1095 days`. |

`market.klines` retention design:

- Preserve compression after 14 days.
- Replace retention after 365 days with retention after 1095 days.
- Assert exactly one active retention policy after replacement.
- Rollback restores 365 days.

## 8. Rollback And Dry Run

Rollback design:

1. Restore `market.klines` retention to 365 days.
2. Drop new `research.alpha_*` tables only if no accepted production/backfill
   rows exist.
3. If any accepted rows exist, preserve rows and mark run/table state inactive
   or superseded instead of deleting evidence.
4. Never delete `market.klines` OHLCV rows as rollback.
5. If sqlx checksum drift appears, use the established repair workflow. Do not
   hand-edit `_sqlx_migrations`.

Dry-run plan:

1. Re-run Linux-only PG reflection immediately before implementation.
2. Apply V125 to a Linux sandbox/dry-run database.
3. Apply V125 twice; second apply must be no-op or NOTICE-only.
4. Verify schema, hypertables, compression, retention, indexes, comments, and
   guard reflections.
5. Only after explicit operator approval, apply to production PG.
6. Do not trust Mac mock PG as migration sign-off evidence.

## 9. Explicit Exclusions

V125 design does not include:

- mark/index/premium price-kline storage
- endpoint client implementation
- historical writer implementation
- data backfill
- production runtime restart
- collector implementation
- alpha scoring or promotion report
- DB writes before a separately approved migration execution task

Mark/index/premium price-only klines stay out because FND-4 says their storage
choice is not approved yet.

## 10. Next Gates

Before creating the SQL file or applying anything:

1. PM explicitly opens the `V125__aeg_alpha_history_storage.sql`
   implementation scope.
2. E2 reviews the schema, guard, rollback, and sqlx migration posture.
3. E4 reviews idempotency tests and migration verification plan.
4. MIT rechecks Linux PG reflection and disk headroom.
5. Operator approves execution separately from this design approval.

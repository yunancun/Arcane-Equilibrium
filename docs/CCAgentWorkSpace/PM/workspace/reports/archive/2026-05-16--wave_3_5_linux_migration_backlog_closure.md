# 2026-05-16 Wave 3.5 Linux PG Migration Backlog Closure

## Scope

Closed `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG` on Linux `trade-core`.

This was a runtime PG migration metadata/schema closure only:
- no engine restart
- no API restart
- no auth renewal or auth-file write
- no live / LiveDemo / demo / paper mode change
- no strategy, risk, TOML, or order-authority change

## Pre-Apply Facts

- Linux repo HEAD: `429fe7cd` before the later docs sync, clean for the migration files.
- Active engine was running during the operation: PID `69581`.
- Runtime DB DSN source was `/tmp/openclaw/runtime_secrets/openclaw_database_url`.
- PA audit drift was confirmed:
  - `_sqlx_migrations` had versions through `90` only.
  - V091 and V093 physical constraints already matched source semantics.
  - V092 physical continuous aggregates were missing.
  - V081 remained a legal dead slot.
- Source SHA-384 checksums used for metadata:
  - V091 `8a2f135d84aab95ebfc8183e81623f086c8e782cbd64cc4cfdab2638916a51e4991e452af101a2d156d87a2df16852b8`
  - V092 `0cc34cf57d7d844a7b9b1bfc443eef98e885bc02295c8f2d2d6d8e9e9b52e70202a0b95ff46e4c5fdf57fb28e5149bdf`
  - V093 `b7600fb014c44317da09ca513bf857bd03385a6dfa271da8b968c1bcfc824b74dbbf6409dba9046ff8f8ac55b0cc6208`

## Actions

1. Backed up `_sqlx_migrations` to:
   `/tmp/openclaw/migration_backups/_sqlx_migrations_pre_wave35_20260516T164810Z.sql`
2. Applied V092 online with bounded lock/statement timeouts:
   `PGOPTIONS='-c lock_timeout=5s -c statement_timeout=120s'`
3. Inserted `_sqlx_migrations` rows for V091/V092/V093 with source checksums and `execution_time=-1` metadata-repair marker.
4. Re-ran V092 once for idempotency; all six continuous aggregates and refresh policies reported existing/skip notices.

## Verification

- `_sqlx_migrations`: `max_applied=93`, `rows=90`.
- V091/V093 constraints:
  - `chk_reason_code_mutually_exclusive` exists and `convalidated=t`.
  - `chk_decision_features_evaluations_outcome` includes `oi_panel_unavailable`.
  - `chk_decision_features_evaluations_evidence_tier` includes `panel_fail_closed`.
  - `chk_decision_features_evaluations_side` allows `-1, 0, 1`.
- V092:
  - `timescaledb_information.continuous_aggregates` returns six views:
    `funding_rates_panel_5m/15m/1h` and `oi_delta_panel_5m/15m/1h`.
  - Six refresh jobs exist with 1m / 5m / 15m schedules.
  - Read smoke counts returned rows from all six aggregate views.
- `repair_migration_checksum --verify`:
  - `parsed_files=90`
  - `db_rows=90`
  - `drift_count=0`
  - V091/V092/V093 each matched file checksum.
- Engine remained alive after the migration: PID `69581`, elapsed `15:49:11` at verification.

## Caveats

- `helper_scripts/db/check_migration_status.py` still reports legacy V001-V005 expectation failures (`config` schema and several old expected tables). This checker is stale for current runtime schema and was not used as the Wave 3.5 acceptance gate.
- The repo env file and runtime secrets env differ on `OPENCLAW_AUTO_MIGRATE`; restart scripts use the secrets env, which still has `OPENCLAW_AUTO_MIGRATE=0`. This closure did not change either env file.

## Verdict

PM verdict: **DONE**.

V094 deploy is no longer blocked by the V091/V092/V093 Linux PG backlog. Remaining Phase 1b blockers are the 3-gate set (`P0-EDGE-1`, `W-AUDIT-8b Stage 0R`, `W-AUDIT-8a C1`) plus `P1-BBMF3-WIRE-1`.

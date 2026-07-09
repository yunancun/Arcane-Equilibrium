# 2026-05-15 — P1-WA4B-INSERT-1 Feature Baseline Restore

## Scope

Runtime remediation for the only hard FAIL from the 2026-05-15 passive
healthcheck:

- `[67] feature_baseline_readiness`
- Object: `observability.feature_baselines`
- W-AUDIT-4b apply path:
  `helper_scripts/cron/feature_baseline_writer_cron.sh`

Boundary: DB write to `observability.feature_baselines` only. No DDL, rebuild,
restart, live auth mutation, strategy/risk parameter change, or paper enablement.

## Investigation

Facts from `trade-core`:

- Linux repo head: `a7900d38`.
- `observability.feature_baselines`, `features.online_latest`, and
  `trading.decision_context_snapshots` all existed.
- Before apply: `observability.feature_baselines` total=0 / active=0.
- No crontab entry for `feature_baseline_writer`.
- No prior `/tmp/openclaw/logs/feature_baseline_writer_cron.log`.
- Source data was available: dry-run read 3,341,214 historical
  `trading.decision_context_snapshots` samples.
- `features.online_latest` had 43 rows with vector_dim min=max=34.

Inference: `[67]` failed because the W-AUDIT-4b operational apply/schedule path
had not populated baselines, not because schema or source data was missing.

## Action

Dry-run first:

```bash
OPENCLAW_DATABASE_URL_FILE=/tmp/openclaw/runtime_secrets/openclaw_database_url \
  rust/target/release/feature_baseline_writer \
  --dry-run --lookback-days 180 --window-days 30 --step-days 7 --bins 10
```

Dry-run result:

- samples=3,341,214
- baseline_rows=646
- active_rows=646

Applied using the canonical wrapper:

```bash
OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv \
OPENCLAW_DATA_DIR=/tmp/openclaw \
  bash helper_scripts/cron/feature_baseline_writer_cron.sh
```

Wrapper result:

- mode=Apply
- apply_gate=OPENCLAW_FEATURE_BASELINE_APPLY
- samples=3,341,448
- baseline_rows=646
- rows_written=646

## Restored Baselines

Active baselines after apply:

- active_rows=646
- active_symbols=19
- feature_names=34/34
- online_latest_rows=43
- vector_dim_min=34
- vector_dim_max=34

Symbols restored with 34 active feature baselines each:

`1000PEPEUSDT`, `ADAUSDT`, `ARBUSDT`, `BTCUSDT`, `DOGEUSDT`, `DOTUSDT`,
`ENAUSDT`, `ETHUSDT`, `FARTCOINUSDT`, `HYPEUSDT`, `LINKUSDT`, `NEARUSDT`,
`SIRENUSDT`, `SOLUSDT`, `SUIUSDT`, `TAOUSDT`, `TONUSDT`, `XRPUSDT`,
`ZECUSDT`.

## Verification

Standalone item `[67]` rerun:

```text
PASS [67] feature_baseline_readiness [67] feature_baselines active_rows=646 active_symbols=19 feature_names=34/34; online_latest_rows=43 vector_dim_min=34 vector_dim_max=34 — 34-dim baseline contract ready; drift_events will activate after configured burn-in
```

`TODO.md` updated to mark `P1-WA4B-INSERT-1` done and record the row/symbol
counts.

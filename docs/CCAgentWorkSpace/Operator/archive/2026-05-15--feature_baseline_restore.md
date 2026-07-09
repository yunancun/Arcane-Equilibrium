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

## Result

The table/schema and source data were present, but active baselines were absent
and no feature-baseline cron/log existed. The W-AUDIT-4b apply wrapper wrote
646 rows from `trading.decision_context_snapshots`.

Restored active baselines:

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

`TODO.md` updated to mark `P1-WA4B-INSERT-1` done.

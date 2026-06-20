# Polymarket 15m Evidence Cadence

## 結論

Polymarket lead-lag lane 已確認不是資料壞掉：forward label 成熟後，manual wrapper 在 `2026-06-20T12:24:33Z` 從 0 joined rows 變成 `joined_rows=6` / `label_joinable_pairs=6`。目前仍只有每個 IC cell `n=1`，所以正確 verdict 仍是 `INSUFFICIENT_SAMPLE`，不可當作 edge 或 promotion proof。

本輪把 Polymarket artifact-only evidence cadence 從 hourly 加速到 15 分鐘，以縮短證偽/證成等待時間。Repo installer 預設保持 hourly 不變；Linux runtime 以明確 env opt-in 安裝加速排程。

## Runtime Evidence

- Manual lead-lag artifact: `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T122433Z.json`
- sha256: `cfc12bd3519a18eaa3dc03a7ea690f61d0e2cb695087a2c4f33cb4c110951111`
- Counts: `snapshot_distinct_timestamps=2`, `delta_rows=397`, `feature_points=6`, `joined_rows=6`, `label_joinable_pairs=6`
- Label status: `{"exit_target_after_latest_price":12,"joinable":6}`
- Verdict: `INSUFFICIENT_SAMPLE`, reason `max joined IC points 1 below min_points 30`
- Alpha discovery refresh: `2026-06-20T12:24:46Z`, `polymarket_leadlag_ic.sample_count=1`, action `RUN_READ_ONLY_CAPTURE`, ready/probe=0
- Natural cron proof: `2026-06-20T12:32:01Z` lead-lag fire wrote `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T123201Z.json`, sha256 `4616b4dbe306035ce967b299b5c3afa6b37de4b0929885a1e2c5e6a57a0b401b`, still `joined_rows=6` / max IC points `1`
- Natural collector proof: `2026-06-20T12:37:17Z` collector completed `/tmp/openclaw/polymarket_axis_runs/hourly-topn-20260620T123716Z` with 884 snapshot rows, 107 events, 30 HTTP requests, and `errors=[]`

## Runtime Change

Crontab backup before switch:

`/tmp/openclaw/cron_backups/crontab_before_polymarket_15m_cadence_20260620T122823Z.txt`

Installed active Polymarket lines:

```cron
41 4 * * * ... polymarket_axis_cron.sh daily
7,22,37,52 * * * * ... polymarket_axis_cron.sh hourly-topn
2,17,32,47 * * * * ... polymarket_leadlag_ic_cron.sh
```

## Source Change

- `helper_scripts/cron/install_polymarket_axis_cron.sh`
  - Adds `OPENCLAW_POLYMARKET_CRON_TOPN_MINUTES`, default `7`.
  - Supports opt-in comma minute list such as `7,22,37,52`.
- `helper_scripts/cron/install_polymarket_leadlag_ic_cron.sh`
  - Adds `OPENCLAW_POLYMARKET_LEADLAG_CRON_MINUTES`, default `17`.
  - Supports opt-in comma minute list such as `2,17,32,47`.
- Static tests updated to lock default-preserving behavior and minute-list validation.

## Verification

- Local: `python3 -m pytest -q helper_scripts/cron/tests/test_polymarket_axis_cron_static.py helper_scripts/cron/tests/test_polymarket_leadlag_ic_cron_static.py` -> `22 passed`
- Linux: same cron static suite -> `22 passed`
- Local and Linux: `bash -n` passed for both installers and both wrappers
- Local: `git diff --check` passed for touched cron/test files

## Boundary

This is artifact-only evidence acceleration. It writes only user crontab plus `/tmp/openclaw` artifacts/logs/heartbeats/locks. Polymarket collector remains zero secrets / zero PG. Lead-lag IC uses read-only PG SELECT via `PGOPTIONS=-c default_transaction_read_only=on`.

No engine/API restart, no rebuild, no PG table write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/strategy mutation, and no promotion proof.

## Next Trigger

Let quarter-hour snapshots accumulate. When `polymarket_leadlag_ic.sample_count >= 30`, run formal leak-free review before any strategy implication: residualization, regime slices, HAC / autocorrelation-aware uncertainty, multiple-testing correction, and QC/MIT/AI-E ruling.

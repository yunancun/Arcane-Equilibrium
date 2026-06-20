# 2026-06-20 — Polymarket Pre-Gate HAC Watchlist

## 結論

Polymarket lead-lag IC reducer 已升到 v0.6。現在 report / cron status / alpha-discovery 會保留 diagnostic-only `pre_gate_hac_watchlist`：這些是 HAC/BH 看起來值得追蹤、但仍因 overlap-adjusted sample floor 未達 `min_points` 而不能成為 candidate 的 cells。

這解決的是 killboard 可觀測性缺口：先前只有 `candidate_count=0` 與 `sample_count=9`，看不出是否有值得等待的 early signal。v0.6 會明確顯示「有 watch，但 blocker 是 sample floor」，同時仍 fail-closed。

## 實作

- `helper_scripts/research/polymarket_leadlag/` schema/runner：`polymarket.leadlag_report.v0.6` / `polymarket_leadlag.v0.6`
- 新增 report top-level：`pre_gate_hac_watchlist`
- 新增 verdict/counts：`pre_gate_hac_watchlist_count`, `min_samples_remaining_to_gate`
- Cron / alpha discovery passthrough：`pre_gate_hac_watchlist_count`, `best_pre_gate_hac_watch`, `min_samples_remaining_to_gate`
- Candidate gate 不變：仍需 min_points、overlap-adjusted sample floor、HAC t-stat threshold、BH q-value control

## 驗證

- Mac：Polymarket + alpha discovery focused tests `31 passed`
- Mac：cron static tests `9 passed`
- Mac：`py_compile` + `bash -n` + `git diff --check` passed
- Linux `trade-core` selective source sync：same `31 passed` + `9 passed` + `py_compile` + `bash -n`
- Linux runtime smoke：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
  - sha256 `864151680dc2787a79a387d7316faedb81568dc569ca2561ef1b38c723621213`
  - created_at `2026-06-20T14:50:18.820573+00:00`
  - schema/runner v0.6
  - `max_ic_points=9`, `max_overlap_adjusted_ic_points=9`
  - `min_samples_remaining_to_gate=21`
  - `pre_gate_hac_watchlist_count=5`
  - best watch `other|BTCUSDT|15m`, `t_stat_hac=-6.824190750820994`, `bh_q_value_hac_approx=8.84223286822465e-11`
  - `candidate_count=0`, status `INSUFFICIENT_SAMPLE`
- Alpha discovery refresh `2026-06-20T14:50:33.741408+00:00`
  - sha256 `acaa77cab2660c65e57b092fe13a71966f0c8bd135d14c8ebf7e247603427e13`
  - `polymarket_leadlag_ic.sample_count=9`
  - `pre_gate_hac_watchlist_count=5`
  - same `best_pre_gate_hac_watch`
  - action `RUN_READ_ONLY_CAPTURE`, artifacts_ready `false`, ready/probe `0`

## 邊界

Artifact/status only. PG path is readonly SELECT. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/strategy mutation, and no promotion proof.

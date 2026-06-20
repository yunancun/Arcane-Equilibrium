# 2026-06-20 — Polymarket HAC IC Gate

## 結論

Polymarket lead-lag IC reducer 已升到 v0.4。候選不再只靠 naive correlation t-stat；現在必須同時通過 overlap-adjusted sample floor、Newey-West/HAC slope t-stat threshold、以及 BH q-value control。這補上了 Polymarket 15m cadence 之後最容易出現的序列相關假陽性缺口。

## 實作

- `helper_scripts/research/polymarket_leadlag/` schema/runner：`polymarket.leadlag_report.v0.4` / `polymarket_leadlag.v0.4`
- IC row 新欄位：`t_stat_hac`, `hac_lag`, `hac_method`, `p_value_hac_approx_normal`, `bh_q_value_hac_approx`, plus naive p/q diagnostics
- Candidate partition：`preliminary_raw_candidate_count` 保留 naive 診斷；`preliminary_hac_candidate_count` 是 BH 前的 HAC gate；`candidate_count` 只計 HAC + BH controlled cells
- Cron / alpha discovery passthrough：`preliminary_hac_candidate_count`, `significance_t_stat=t_stat_hac`, `max_abs_t_stat_hac`

## 驗證

- Mac：Polymarket + alpha discovery focused tests `28 passed`
- Mac：cron static tests `9 passed`
- Mac：`py_compile` + `bash -n` passed
- Linux `trade-core` selective source sync：same `28 passed` + `9 passed` + `py_compile` + `bash -n`
- Linux runtime smoke：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
  - sha256 `9e4941dc399f5f6c2c08076814d06f3ed78b6084d383689f66800083c80a5601`
  - created_at `2026-06-20T13:03:57.841836+00:00`
  - `max_ic_points=2`, `max_overlap_adjusted_ic_points=2`
  - `preliminary_raw_candidate_count=0`, `preliminary_hac_candidate_count=0`
  - status `INSUFFICIENT_SAMPLE`, reason `max overlap-adjusted IC points 2 below min_points 30`
- Alpha discovery refresh `2026-06-20T13:04:14.871361+00:00` keeps `polymarket_leadlag_ic` as `RUN_READ_ONLY_CAPTURE`, sample_count `2`, ready/probe `0`

## 邊界

Artifact/status only. PG path is readonly SELECT. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/strategy mutation, and no promotion proof.

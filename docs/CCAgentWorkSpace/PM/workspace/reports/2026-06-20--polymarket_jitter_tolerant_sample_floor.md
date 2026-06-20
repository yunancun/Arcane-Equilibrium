# 2026-06-20 — Polymarket Jitter-Tolerant Sample Floor

## 結論

Polymarket lead-lag IC reducer 已升到 v0.5。這次不是放寬候選門檻，而是修正 evidence loop 的樣本獨立性計數：15m cron 實際 timestamp 會有 sub-second/second jitter，舊版 strict horizon 比較會把 intended 15m 相鄰樣本誤判為 overlapping，低估 `max_overlap_adjusted_ic_points`。

## 實作

- `helper_scripts/research/polymarket_leadlag/` schema/runner：`polymarket.leadlag_report.v0.5` / `polymarket_leadlag.v0.5`
- `overlap_adjusted_sample_floor` and `hac_lag` now share a 5s schedule-jitter tolerance
- IC row 新欄位：`overlap_jitter_tolerance_ms`
- Candidate gate 不變：仍需 min_points、overlap-adjusted sample floor、HAC t-stat threshold、BH q-value control

## 驗證

- Mac：Polymarket + alpha discovery focused tests `30 passed`
- Mac：`py_compile` + `git diff --check` passed
- Linux `trade-core` selective source sync：same `30 passed` + `py_compile`
- Linux runtime smoke：`/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_latest.json`
  - sha256 `8756b1c5758634f283de79fc83014cd12b290c3fd0c79669c6bbef8f2b7d2136`
  - created_at `2026-06-20T14:39:41.942079+00:00`
  - schema/runner v0.5
  - `snapshot_distinct_timestamps=11`, `joined_rows=90`
  - `max_ic_points=9`, `max_overlap_adjusted_ic_points=9`
  - `max_abs_t_stat_hac=6.824190750820994`
  - `candidate_count=0`, `preliminary_hac_candidate_count=0`
  - status `INSUFFICIENT_SAMPLE`, reason `max overlap-adjusted IC points 9 below min_points 30`
- Alpha discovery refresh `2026-06-20T14:39:57.928240+00:00`
  - sha256 `0c3f6fbd893719888d6b29dd4ddc1ee59366855d4d9343dba90a8d78bbf60532`
  - `polymarket_leadlag_ic.sample_count=9`
  - action `RUN_READ_ONLY_CAPTURE`, candidate_count `0`, ready/probe `0`

## 邊界

Artifact/status only. PG path is readonly SELECT. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/strategy mutation, and no promotion proof.

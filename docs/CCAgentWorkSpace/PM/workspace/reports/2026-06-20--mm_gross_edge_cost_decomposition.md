# MM Gross-Edge Cost Decomposition

日期：2026-06-20
角色：PM
範圍：artifact-only MM verdict / alpha-discovery blocker diagnosis；不改 strategy、risk、order、auth。

## 結論

這批把 MM no-profit diagnosis 從「沒有 walk-forward train-positive feature cell」再拆細一層：目前不是完全沒有量到毛邊際，而是毛邊際低於現行 maker fee。

最新 runtime：

- gross-positive sample-gated cells：38
- current-fee-positive sample-gated cells：0
- best gross cell：`LABUSDT` / back / informed_skip
- best gross edge before fees：`2.27bp`
- current-fee net：`-1.73bp`
- break-even maker fee：`1.135bp/side`
- fee reduction needed：`0.865bp/side`
- best walk-forward holdout gross candidate：`symbol=ADAUSDT`, gross `2.002bp`, net `-1.998bp`

因此 alpha killboard 現在把 MM 主 blocker 從 `feature_family_no_edge` 改成 `cost_wall:gross_edge_below_current_fee_no_current_fee_walk_forward_positive`。這不是 promotion proof；它只是把下一步變得更精確：要嘛證明真實 lower-fee path，要嘛找新的 low-friction / stronger spread-capture MM signal family。

## 變更

- `helper_scripts/cron/recorder_mm_verdict_cron.sh`
  - 新增 `gross_edge_cost_decomposition`。
  - 聚合 fill_sim `edge_scorecard.all_fill_only_cells`、`conditional_feature_scorecard.all_cells`、`walk_forward_feature_scorecard` candidates。
  - 分出 `GROSS_EDGE_BELOW_CURRENT_FEE_COST_WALL`、`NO_SAMPLE_GATED_GROSS_EDGE`、`CURRENT_FEE_GROSS_AND_NET_POSITIVE`。
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - MM fresh/stale detail pass through `gross_edge_cost_decomposition`。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - MM secondary blockers now surface gross-edge cost-wall evidence.
  - `NO_TRAIN_POSITIVE_CELL` only becomes primary `cost_wall` when decomposition proves positive gross edge and 0 current-fee-positive sample-gated cells.
  - Missing decomposition keeps the prior conservative `feature_family_no_edge` classification.
- Tests
  - Added classifier coverage for decomposition-present vs decomposition-missing cases.
  - Runtime passthrough and static cron contract updated.

## Runtime Evidence

MM verdict latest status line:

- Source: `/tmp/openclaw/logs/recorder_mm_verdict.log`
- status-line sha256: `6e1cfda2a71fa17079b5dd9194135986641a274006feedcf0231e0b7b28b65af`
- `ts_utc`: `2026-06-20T18:03:41Z`
- `gross_edge_cost_decomposition.status`: `GROSS_EDGE_BELOW_CURRENT_FEE_COST_WALL`
- `gross_positive_sample_gated_cell_count`: `38`
- `current_fee_positive_sample_gated_cell_count`: `0`
- `best_sample_gated_gross_edge_bps`: `2.27`
- `best_gross_cell_net_bps`: `-1.73`
- `break_even_maker_fee_bps_per_side`: `1.135`
- `fee_reduction_needed_bps_per_side`: `0.865`
- `sample_gated_cost_wall_summary.status`: `SAMPLE_GATED_CURRENT_FEE_COST_WALL`
- `sample_gated_cell_count`: `74`
- best walk-forward holdout gross candidate: `symbol=ADAUSDT`, gross `2.002bp`, net `-1.998bp`

Alpha discovery latest:

- Path: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- sha256: `187e21bdf45b35d1f57677707743e483bd7244390d4b17099b713ed12898b6d8`
- `created_at_utc`: `2026-06-20T18:03:46.581026+00:00`
- status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- ready/probe: `0/0`
- MM blocker class: `cost_wall`
- MM primary blocker: `gross_edge_below_current_fee_no_current_fee_walk_forward_positive`
- next trigger: `validate_lower_fee_or_new_low_friction_signal_path_before_expanding_current_family`

## Verification

Mac:

- `env PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `25 passed`
- `python3 -m pytest -q helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` -> `11 passed`
- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `git diff --check`

Linux selective sync:

- Same focused alpha tests -> `25 passed`
- Same cron static tests -> `11 passed`
- bash syntax / py_compile / targeted diff-check passed

Runtime smoke:

- Ran read-only `recorder_mm_verdict_cron.sh`
- Ran artifact-only `alpha_discovery_throughput_cron.sh`

## Boundary

This batch wrote source/tests/docs and `/tmp/openclaw` status artifacts only. It did not write PG tables, run migrations, call Bybit private/signed/trading endpoints, rebuild/restart engine/API, or mutate credential/auth/risk/order/strategy state.

## Next Trigger

Do not expand the current MM feature family as if it had no measured signal at all. The next useful work is:

- lower-fee feasibility proof with real account eligibility and cross-window fill_sim history, or
- a new low-friction MM signal family whose sample-gated walk-forward train/holdout cells can clear current fees.

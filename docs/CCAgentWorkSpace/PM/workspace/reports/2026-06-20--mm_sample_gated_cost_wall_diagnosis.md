# MM Sample-Gated Cost-Wall Diagnosis

日期：2026-06-20
角色：PM
範圍：artifact-only MM verdict / alpha-discovery 診斷；不改 strategy、risk、order、auth。

## 結論

本批修正 MM no-profit killboard 的證據重心。舊 `cost_wall_summary` 來自 live maker markout per-symbol net-edge，會把「最接近 breakeven 的 symbol」列出來；最新 runtime 裡那個 symbol 是 `ARBUSDT`，但只有 `n=1` maker fill。這不能當作找盈利路徑的主線。

新增的 `sample_gated_cost_wall_summary` 只看 fill_sim sample-gated cells，也就是 `n >= min_fills` 且 `signif_suppressed=false` 的 cells。最新 runtime 顯示真正可比較的 MM cost wall 是：

- 74 個 sample-gated fill_sim cells
- best current-fee cell：`LABUSDT` / back / informed_skip
- `n=170`
- net `-1.73bp`
- fee shortfall `1.73bp RT`
- break-even maker fee `1.135bp/side`
- fee reduction needed `0.865bp/side`

所以 MM 不能盈利的讀法更清楚了：不是「ARB 差一點點就能做」，而是「在 sample-gated fill_sim 裡，現行 fee 仍差 1.73bp RT；且 walk-forward feature family 沒有 train-positive cell」。短期工程方向應該是找新的低 friction / stronger spread-capture MM signal，或證明真實 lower-fee business path；不是追逐單筆 ARBUSDT 近 breakeven。

## 變更

- `helper_scripts/cron/recorder_mm_verdict_cron.sh`
  - 新增 embedded reducer `_sample_gated_fill_sim_cost_wall()`。
  - status JSON 新增 `sample_gated_cost_wall_summary`。
  - reducer 只納入 fill_sim `edge_scorecard.all_fill_only_cells` 中通過 sample gate 的 rows。
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - MM arm detail pass through `sample_gated_cost_wall_summary`。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - MM secondary blockers 優先加入 sample-gated fill_sim cost wall。
  - 若沒有 walk-forward failure 擋在前面，primary cost-wall blocker 也優先使用 sample-gated summary。
  - live-markout cost wall 改名為 diagnostic secondary blocker，並保留 `best_n_maker_fills`。
- Tests
  - Static cron contract asserts new status surface。
  - Alpha-discovery tests assert runtime passthrough and blocker preference。

## Runtime Evidence

MM verdict latest status line:

- Source: `/tmp/openclaw/logs/recorder_mm_verdict.log`
- status-line sha256: `fe2ae9b675b11e4e43ebc8ba4bfbd704e30478db8d9cf18be1293cc310d8a5d5`
- `ts_utc`: `2026-06-20T17:28:30Z`
- `sample_gated_cost_wall_summary.status`: `SAMPLE_GATED_CURRENT_FEE_COST_WALL`
- `sample_gated_cell_count`: `74`
- best sample-gated current-fee cell: `LABUSDT` / back / informed_skip
- best sample-gated cell `n`: `170`
- best sample-gated net: `-1.73bp`
- best sample-gated fee shortfall: `1.73bp RT`
- break-even maker fee: `1.135bp/side`
- fee reduction needed: `0.865bp/side`

Live-markout diagnostic comparison:

- best live symbol: `ARBUSDT`
- best live net: `-0.0357bp`
- best live maker fills: `1`
- interpretation: too thin to anchor the cost-wall diagnosis.

Alpha discovery latest:

- Path: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- sha256: `05301d674686b2763f122b915a47d7837a36ff5829c22c44abda81d9fc0727ad`
- status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- ready/probe: `0/0`
- MM primary blocker: `no_train_positive_walk_forward_feature_cell`
- MM secondary blockers:
  - `current_maker_fee_exceeds_sample_gated_fill_sim_break_even`
  - `live_markout_current_maker_fee_exceeds_best_break_even`
  - `lower_standard_vip_fee_may_clear_but_scale_or_capital_gated`

## Verification

Mac:

- `env PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib program_code/research/tests/test_fill_sim_cost_wall.py program_code/research/tests/test_mm_fee_path_feasibility.py program_code/research/tests/test_fill_sim_history.py helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `58 passed`
- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh`
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `git diff --check`

Linux selective sync:

- Same focused pytest suite -> `58 passed`
- Same bash syntax / py_compile / targeted diff-check passed

Runtime smoke:

- Ran read-only `recorder_mm_verdict_cron.sh`
- Ran artifact-only `alpha_discovery_throughput_cron.sh`

## Boundary

This batch wrote source/tests/docs and `/tmp/openclaw` status artifacts only. It did not write PG tables, run migrations, call Bybit private/signed/trading endpoints, rebuild/restart engine/API, or mutate credential/auth/risk/order/strategy state.

## Next Trigger

MM should not proceed from the ARBUSDT n=1 live-markout row. Next useful MM work is either:

- find a new sample-gated current-fee MM signal family with positive train/holdout behavior, or
- prove a real lower-fee path and then re-run cross-window/cross-regime fill_sim history before any strategy work.

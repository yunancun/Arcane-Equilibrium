# MM Lower-Fee History Stability

日期：2026-06-20
角色：PM
範圍：artifact-only MM lower-fee history diagnosis；不改 strategy、risk、order、auth。

## 結論

MM 現在不再只回答「current fee 後是否為正」，也回答「lower-fee / gross-edge 候選是否跨 history window 穩定重複」。

最新 runtime 結論：

- `history_scorecard.status`: `HISTORY_INSUFFICIENT_WINDOWS`
- `lower_fee_break_even_stability.status`: `LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT`
- lower-fee break-even windows: `3`
- repeated lower-fee break-even keys: `11`
- distinct lower-fee dates: `["2026-06-20"]`
- best lower-fee window: `LABUSDT` / back / informed_skip, break-even maker fee `1.135bp/side`
- best repeated lower-fee key: `ADAUSDT` / back / naive, break-even maker fee `1.073bp/side`, repeated in 3 windows but all same date

Interpretation：lower-fee MM path has repeated same-day structure, but it is not yet cross-date/cross-regime profit evidence. It remains blocked until history windows cover independent dates/regimes.

## 變更

- `program_code/research/microstructure/fill_sim_history.py`
  - Extracts sample-gated lower-fee break-even cells from maker-fee sensitivity reports.
  - Groups lower-fee cells by existing MM cell key.
  - Emits `lower_fee_break_even_stability` with repeated-key count, distinct dates, best lower-fee window, and best repeated lower-fee key.
- `helper_scripts/cron/recorder_mm_verdict_cron.sh`
  - Preserves the new history stability fields under `fillsim.history_scorecard`.
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - Passes `history_scorecard` into MM arm detail for fresh and stale MM status paths.
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - Adds lower-fee history fields to MM cost-wall blocker rows.
  - Adds secondary `fee_or_scale` blocker `lower_fee_break_even_not_stable_across_distinct_windows` while the path lacks distinct-date stability.

## Runtime Evidence

Fill-sim history scorecard:

- Path: `/tmp/openclaw/research/fillsim/fillsim_history_scorecard.json`
- sha256: `7dbeb78fb528a8ed4a50710d102308bc77b2ff2cc57f38e0a45ea07e727ecaef`
- `windows_loaded=3`, `valid_windows=3`
- `distinct_window_dates=["2026-06-20"]`
- `lower_fee_break_even_stability.status=LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT`

MM verdict latest status line:

- Source: `/tmp/openclaw/logs/recorder_mm_verdict.log`
- latest status-line sha256: `9d5a3c3ca7c1f28fceb5084a5dab8a4282222cb9ecce4b4b2fb6718994ddac4e`
- `ts_utc`: `2026-06-20T18:23:06Z`
- history stability fields preserved under `fillsim.history_scorecard`

Alpha discovery latest:

- Path: `/tmp/openclaw/alpha_discovery_throughput/alpha_discovery_latest.json`
- sha256: `4efcd2f915a4de5913a3b1781a6051e45f7a71b4b479daa03e8a2f5657609399`
- `created_at_utc`: `2026-06-20T18:23:13.019463+00:00`
- global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- MM top blocker: `cost_wall:gross_edge_below_current_fee_no_current_fee_walk_forward_positive`
- `lower_fee_break_even_stability_status=LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT`
- `lower_fee_break_even_windows=3`
- `repeated_lower_fee_break_even_key_count=11`

## Verification

Mac:

- `python3 -m pytest -q program_code/research/tests/test_fill_sim_history.py` -> `7 passed`
- `env PYTHONPATH=helper_scripts/research python3 -m pytest -q --import-mode=importlib helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `25 passed`
- `python3 -m pytest -q helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` -> `11 passed`
- `python3 -m py_compile program_code/research/microstructure/fill_sim_history.py helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
- `git diff --check`

Linux selective sync:

- fill_sim history tests -> `7 passed`
- alpha focused tests -> `25 passed`
- cron static tests -> `11 passed`
- py_compile and `bash -n recorder_mm_verdict_cron.sh` passed

Runtime smoke:

- Rebuilt `/tmp/openclaw/research/fillsim/fillsim_history_scorecard.json` from existing history reports
- Ran read-only `recorder_mm_verdict_cron.sh`
- Ran artifact-only `alpha_discovery_throughput_cron.sh`

## Boundary

This batch wrote source/tests/docs and `/tmp/openclaw` status artifacts only. It did not write PG tables, run migrations, call Bybit private/signed/trading endpoints, rebuild/restart engine/API, or mutate credential/auth/risk/order/strategy state.

## Next Trigger

Let daily fill_sim history accumulate independent dates. The lower-fee MM path becomes worth deeper review only if repeated break-even keys survive across at least 3 distinct history dates/regimes, and still must pass business fee eligibility plus cross-regime CP-3 review before any strategy work.

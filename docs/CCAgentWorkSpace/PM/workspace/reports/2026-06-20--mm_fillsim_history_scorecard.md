# 2026-06-20 — MM fill_sim history scorecard

## 結論

v255 把 v254 的結論「需要 longer-regime coverage」落成 durable artifact spine：`fill_sim_refresh_cron.sh` 之後不再只覆蓋唯一一份 production fill_sim report，而是先把每個通過 candidate guard 的 report 歸檔到 `<DATA>/research/fillsim/history/`，再刷新 `<DATA>/research/fillsim/fillsim_history_scorecard.json`。

這不是盈利證明，也不是 MM promotion authority。它回答下一個必要問題：current-fee sample-gated positive 是否跨窗口重複、walk-forward holdout positive 是否跨窗口重複、以及最佳 sample-gated break-even fee 是否隨 regime 穩定。

## Source changes

- 新增 `program_code/research/microstructure/fill_sim_history.py`
  - report-only reducer；不連 DB、不打 exchange、不碰 runtime state。
  - 輸出 `HISTORY_INSUFFICIENT_WINDOWS`、`HISTORY_LOWER_FEE_ONLY`、`HISTORY_CURRENT_FEE_REPEAT_IN_WINDOW_NEEDS_OOS`、`HISTORY_SINGLE_HOLDOUT_CONFIRMED_NEEDS_MORE_WINDOWS` 等狀態。
  - 抽取 valid windows / distinct dates、status counts、current-fee sample-gated positives、walk-forward holdout confirmations、repeated positive keys、best break-even fee window。
- `helper_scripts/cron/fill_sim_refresh_cron.sh`
  - valid candidate 通過 `no abort / non-empty L1 / non-empty symbols / L1 data age` 後，先 `cp` 到 history，再 atomic replace production report。
  - 每次 valid candidate 後刷新 `fillsim_history_scorecard.json`。
  - status line 增加 `history_dir` / `history_scorecard`。
- `helper_scripts/cron/recorder_mm_verdict_cron.sh`
  - 讀取 history scorecard，放入 `fillsim.history_scorecard`。
- Tests/docs/index/memory 已補。

## Validation

Mac focused:

- `python3 -m pytest -q program_code/research/tests/test_fill_sim_history.py program_code/research/tests/test_fill_sim_cost_wall.py helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` → 31 passed.
- `python3 -m py_compile program_code/research/microstructure/fill_sim_history.py program_code/research/microstructure/fill_sim.py`
- `bash -n helper_scripts/cron/fill_sim_refresh_cron.sh`
- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh`
- Empty-history CLI smoke → `NO_HISTORY_REPORTS 0 0`
- `git diff --check` on touched code/test/cron files passed.

Linux validation:

- Canonical `trade-core` checkout was behind local/GitHub (`bb06ae1b` vs local/origin `681b1732`) and had related dirty selective-sync files, so validation used `/tmp/openclaw_v255_validate`: a clean git archive of local v254 HEAD plus v255 overlay.
- `/tmp` copy focused tests → 31 passed.
- `/tmp` copy py_compile + `bash -n` passed.
- `/tmp` copy empty-history CLI smoke → `NO_HISTORY_REPORTS 0 0`.

## Read

The immediate MM engineering direction is no longer "find another single-window spread/imbalance threshold." The system now preserves the evidence needed to decide whether any MM cell survives across report windows. Until the history scorecard has enough valid windows/dates and repeated holdout/current-fee positives, MM remains research-only.

Boundary: no canonical Linux checkout mutation, no production fill_sim replacement, no engine/API restart, no rebuild, no strategy parameter change, no PG write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation.

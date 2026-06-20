# 2026-06-20 — MM fill_sim history runtime sync

## 結論

v255 的 history reducer 已可在 Linux runtime source surface 使用。這次沒有嘗試 full `git pull`，因為 `trade-core` canonical checkout 雖然圖上可 fast-forward，但已有 unrelated dirty docs / selective-sync worktree 狀態。為避免覆蓋不明工作，本次只同步 runtime 必要 source files。

## Linux state

- Local/GitHub source: `6915af3b2deee4f27c08181349cdbfb035623e69`
- Linux `HEAD`: `bb06ae1b36165c6ae01f0542d9445df36228f918`
- Linux `origin/main` after fetch: `6915af3b2deee4f27c08181349cdbfb035623e69`
- Merge-base: `bb06ae1b36165c6ae01f0542d9445df36228f918`
- Reason not using full pull: target docs/TODO/changelog/script index/PM memory remain dirty; full three-way git sync is not claimed.

## Synced files

These runtime/test files were synced and verified byte-identical to `origin/main` on Linux:

- `program_code/research/microstructure/fill_sim.py`
- `program_code/research/microstructure/fee_path.py`
- `program_code/research/microstructure/fill_sim_history.py`
- `program_code/research/microstructure/__init__.py`
- `program_code/research/tests/test_fill_sim_history.py`
- `program_code/research/tests/test_fill_sim_cost_wall.py`
- `program_code/research/tests/test_mm_fee_path_feasibility.py`
- `helper_scripts/cron/fill_sim_refresh_cron.sh`
- `helper_scripts/cron/recorder_mm_verdict_cron.sh`
- `helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py`

## Validation

Linux canonical checkout:

- `python3 -m pytest -q program_code/research/tests/test_fill_sim_history.py program_code/research/tests/test_fill_sim_cost_wall.py program_code/research/tests/test_mm_fee_path_feasibility.py helper_scripts/cron/tests/test_fill_sim_refresh_cron_static.py` → 34 passed.
- `python3 -m py_compile program_code/research/microstructure/fill_sim_history.py program_code/research/microstructure/fill_sim.py program_code/research/microstructure/fee_path.py` → pass.
- `bash -n helper_scripts/cron/fill_sim_refresh_cron.sh` → pass.
- `bash -n helper_scripts/cron/recorder_mm_verdict_cron.sh` → pass.

Runtime artifact:

- Initialized `/tmp/openclaw/research/fillsim/fillsim_history_scorecard.json`.
- Status: `NO_HISTORY_REPORTS`, `windows_loaded=0`, `valid_windows=0`.
- Manual read-only `recorder_mm_verdict_cron.sh` run confirmed latest MM verdict status has `fillsim.history_scorecard.present=true/status=NO_HISTORY_REPORTS/windows_loaded=0/valid_windows=0`.

## Read

This closes the immediate runtime gap from v255: daily fill_sim refresh can now start accumulating cross-window MM evidence instead of overwriting the only current report. It does not create a profitable edge; it creates the evidence spine needed to prove or falsify one across regimes.

Boundary: no rebuild/restart, no full Linux git sync, no strategy parameter change, no PG table write/schema migration, no Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation.

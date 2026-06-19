# 2026-06-20 — MM verdict stale guard + cron restore

## Verdict

PASS_WITH_LIMITS。修復了一個直接阻斷 maker / adverse-selection 學習的 runtime 盲點：alpha discovery killboard 之前會把兩天前的 `recorder_mm_verdict.log` 當成仍在 `CAPTURING`，但 Linux crontab 沒有 daily `recorder_mm_verdict_cron.sh`，所以 maker edge 樣本沒有持續前進。

本輪結果：

- source checkpoint: `8411a908 Flag stale MM verdict artifacts`
- `recorder_mm_verdict` daily artifact 超過 36h 或缺 `ts_utc` 時，killboard 現在標 `SOURCE_FAILURE/stale_artifact`，action 變 `BLOCK/source_not_healthy`
- Linux daily cron 已裝回：`41 6 * * * ... recorder_mm_verdict_cron.sh`
- 手動 read-only MM verdict run 成功，`markout_n_total` 從 3 更新到 16，`markout_n_24h=5`
- 重新跑 killboard 後，MM arm 回到 fresh `CAPTURING/source_ok=true/sample_count=16/action=RUN_READ_ONLY_CAPTURE`

## Evidence

Local verification:

- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` -> 10 passed
- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py` -> PASS
- `git diff --check -- helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> PASS

Linux selective deploy verification:

- restored only `runtime_runner.py` and `test_alpha_discovery_throughput.py` from `origin/main`
- Linux focused test -> 10 passed
- py_compile + diff check -> PASS

Runtime before / after:

- Before MM refresh, manual killboard showed:
  - `mm_gate_status=SOURCE_FAILURE`
  - `mm_source_ok=false`
  - `mm_source_error=stale_artifact`
  - `mm_age_seconds=176411.6`
  - `mm_plan_action=BLOCK`
- Manual `recorder_mm_verdict_cron.sh`:
  - `rc=0`
  - `ts_utc=2026-06-19T22:45:23Z`
  - `markout_n_total=16`
  - `markout_n_24h=5`
  - `adverse_selection_usable=true`
  - all current `net_edge_bps` remain negative
- After MM refresh, manual killboard showed:
  - `mm_gate_status=CAPTURING`
  - `mm_source_ok=true`
  - `mm_source_error=null`
  - `mm_sample_count=16`
  - `mm_plan_action=RUN_READ_ONLY_CAPTURE`
  - killboard `is_fast_discovery_active=true`, `source_present_count=4`, `ready_for_probe=0`, `ready_for_aeg_chain=0`

## Boundaries

- No engine/API rebuild or restart.
- No DB writes; MM cron enforces `PGOPTIONS=-c default_transaction_read_only=on`.
- No Bybit private/signed/trading call.
- No credential, auth, risk, order, or trading mutation.
- Writes were limited to source/test/docs, user crontab, and `/tmp/openclaw` local artifact/log/heartbeat files.

## Remaining Work

This restores maker evidence capture freshness, but it is not profit proof. Current MM evidence is still below gate (`sample_count=16 < 30`) and net edge remains negative after spread capture, adverse selection, and maker fees.

Next highest-friction issue: `/tmp/openclaw/research/fillsim/fillsim_report.json` is about 57h old at the time of the run. Once it exceeds 72h, `recorder_mm_verdict_cron.sh` will fail-soft to `adverse_selection_usable=false`. A separate decision is needed before scheduling the heavy fill_sim refresh job because it scans L1/trade data and is intentionally not bundled into the lightweight daily MM verdict cron.

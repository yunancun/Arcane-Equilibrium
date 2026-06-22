# Demo Learning Stack Health Evidence Ingestion

日期：2026-06-22

## 結論

本輪把 v367 的手動 post-install healthcheck 接入 alpha/runtime learning surface。healthcheck 仍預設只輸出 stdout；只有 operator 明確傳 `--json-output` 時，才會寫本地 JSON artifact。alpha discovery 只讀這份 artifact，不執行 crontab/git/runtime 命令。

## 變更

- `helper_scripts/cron/demo_learning_stack_healthcheck.py`
  - 新增 `--json-output`，用 atomic replace 寫 explicit local JSON artifact。
  - Boundary 更新為 optional explicit local JSON artifact output only。
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - schema 升至 `alpha_discovery_runtime_killboard_v7`。
  - 新增 `summarize_demo_learning_stack_healthcheck()`，讀 `/tmp/openclaw/demo_learning_stack_healthcheck/demo_learning_stack_healthcheck_latest.json`。
  - 把 stack health status/reason/next-action/source freshness/source-ready/cron-installed/heartbeat/status/artifact/ledger/outcome fields 接入 Cost Gate learning arm。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - 把 `SOURCE_NOT_READY`、`NOT_INSTALLED`、`INSTALLED_NOT_FIRING`、`FIRING_NO_RECENT_STATUS`、`ERROR`、`FIRING_BUT_ARTIFACTS_INCOMPLETE`、`RUNNING_NO_LEDGER_ROWS`、`LEDGER_ONLY_NEEDS_OUTCOME_REFRESH`、`STALE_ARTIFACT` 轉成 explicit Cost Gate learning blockers。
  - 不產生 probe/order authority；只影響 blocker/next-trigger/evidence。
- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - schema 升至 `alpha_learning_worklist_v4`。
  - Cost Gate learning activation task 攜帶 stack-health evidence。
  - completion evidence 新增 `demo_learning_stack_healthcheck_status == EVIDENCE_STACK_ACTIVE`。
  - Cost Gate learning activation 被標成 operator-authorized runtime mutation。

## 驗證

- `python3 -m pytest -q helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py` → `5 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_throughput.py` → `46 passed`
- `PYTHONPATH=helper_scripts/research python3 -m pytest -q helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` → `4 passed`
- `python3 -m py_compile ...` targeted cron/research files passed

## 邊界

未做 runtime source sync、未安裝 cron、未刷新 runtime artifact、未修改 env、未 deploy/rebuild/restart、未寫 PG/schema、未連 Bybit private/signed/trading API、未改 credential/auth/risk/order/strategy、未啟 writer、未降低 Cost Gate、未授權 probe/order/promotion。

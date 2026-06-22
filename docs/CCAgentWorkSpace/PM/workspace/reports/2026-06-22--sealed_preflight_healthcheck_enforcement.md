# 2026-06-22 — Sealed Preflight Healthcheck Enforcement

## 結論

v405 已把 sealed horizon preflight refresher 納入 demo-learning stack installer，但 healthcheck 仍按舊語義驗收：只要求 demo evidence + Cost Gate learning 兩條資料 cron。這會造成一個假綠燈：stack installer 是四件套，healthcheck 卻可能在 sealed preflight cron 缺失或不 firing 時仍報 `EVIDENCE_STACK_ACTIVE`。

v406 修正這個驗收缺口。healthcheck 現在把 sealed horizon preflight refresher 當成一等 stack component，要求：

- crontab 有 `sealed_horizon_probe_preflight_cron.sh` active entry；
- `cron_heartbeat/sealed_horizon_probe_preflight.last_fire` fresh；
- `logs/sealed_horizon_probe_preflight.log` 有 fresh status JSONL；
- sealed preflight latest artifact 仍獨立檢查，缺失時報 `BOUNDED_PROBE_PREFLIGHT_MISSING`。

這仍然不安裝 cron、不改 runtime、不降低 Cost Gate、不授權 probe/order。

## Source 變更

- `helper_scripts/cron/demo_learning_stack_healthcheck.py`
  - docstring 從 two-cron stack 改為 four-cron stack。
  - `_cron_summary()` 現在檢查 demo evidence、sealed preflight、Cost Gate learning、stack healthcheck 四條 active crontab entry。
  - 新增 `sealed_horizon_probe_preflight_cron` component summary，讀 heartbeat/status/latest artifact。
  - `stack_installed` 要求四條 entry 都 present。
  - `heartbeats_recent` / `statuses_recent` 要求 demo evidence、sealed preflight、Cost Gate learning 三條資料生產 cron fresh。
  - `answers` 增加 per-cron entry/heartbeat/status 欄位。
- `alpha_discovery_throughput.runtime_runner`
  - 把上述 per-cron diagnostics 帶入 Cost Gate learning arm detail。
- `alpha_discovery_throughput.discovery_loop`
  - profitability blocker row carries per-cron diagnostics。
- `alpha_discovery_throughput.learning_worklist`
  - worklist evidence carries per-cron diagnostics。
- Tests
  - active fixture 改成四條 crontab entry。
  - 新增缺 sealed preflight cron entry blocker。
  - 新增 sealed preflight heartbeat stale blocker。
  - alpha/worklist tests pin per-cron evidence propagation。

## 驗證

- Mac py_compile passed for touched healthcheck/alpha/worklist/test modules。
- Mac `helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py`：`9 passed`。
- Mac alpha/worklist focused pytest：`60 passed`。
- Mac source/test diff check passed。
- Source commit：`9b439620 Require sealed preflight in stack healthcheck [skip ci]`。
- Docs/state commit：`b2a1c55b Record sealed preflight healthcheck enforcement [skip ci]`。
- GitHub `origin/main` pushed to `b2a1c55b`。
- Linux `trade-core:/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `b2a1c55b`。
- Linux py_compile passed for touched healthcheck/alpha/worklist/test modules。
- Linux `helper_scripts/cron/tests/test_demo_learning_stack_healthcheck.py`：`9 passed`。
- Linux alpha/worklist focused pytest：`60 passed`。
- Linux `git diff --check` passed。
- Linux read-only healthcheck stdout smoke reported:
  - `status=NOT_INSTALLED`
  - `source_ready=true`
  - `stack_installed=false`
  - `demo_learning_evidence_cron_entry_present=false`
  - `sealed_horizon_probe_preflight_cron_entry_present=false`
  - `cost_gate_learning_lane_cron_entry_present=false`
  - `demo_learning_stack_healthcheck_cron_entry_present=false`
  - `sealed_horizon_probe_preflight_present=true`
  - `bounded_probe_result_review_present=false`
  - `bounded_probe_execution_realism_review_present=false`

## 邊界

本 checkpoint 是 source/test/docs + Linux source sync/read-only/static tests + read-only healthcheck stdout smoke。未執行 CI。沒有 PG write/schema migration、沒有 Bybit private/signed/trading call、沒有 deploy/rebuild/restart、沒有 crontab install、沒有 env/auth/risk/order/strategy/runtime mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。

## 對盈利路徑的含義

這一步仍不是直接盈利策略；它修的是自主學習系統的「證據鏈不能假綠」問題。若 sealed preflight cron 缺失，bounded probe result review / execution-realism review 就可能沒有 fresh 輸入，系統不能宣稱 demo-learning stack active。v406 讓這個缺口直接進入 healthcheck、alpha blocker、learning worklist，避免我們在錯誤的基礎設施狀態上討論 Cost Gate 逃逸或 bounded demo probe。

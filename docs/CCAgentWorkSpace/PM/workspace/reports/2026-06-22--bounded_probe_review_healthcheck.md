# 2026-06-22 — Bounded Probe Review Healthcheck

## 結論

v403 讓 Cost Gate learning cron 能生成 bounded probe result-review 和 execution-realism-review artifacts。v404 補上下一個可觀測性缺口：demo-learning stack healthcheck 之前只看 ledger / blocked-outcome review，可能在 bounded-review 鏈缺失時仍讓主循環誤以為 stack 已足夠健康。

現在 healthcheck 會顯式檢查：

- `sealed_horizon_probe_preflight_latest.json`
- `bounded_probe_result_review_latest.json`
- `bounded_probe_execution_realism_review_latest.json`

並把缺口傳到 alpha blocker / learning worklist。

## Source 變更

- `helper_scripts/cron/demo_learning_stack_healthcheck.py`
  - 新增 artifact component summaries for sealed preflight、bounded result review、bounded execution-realism review。
  - bounded-review rc 併入 Cost Gate learning stage error 判定。
  - 新增 answers：bounded review present/status/skip reason。
  - 新增 status：
    - `BOUNDED_PROBE_PREFLIGHT_MISSING`
    - `BOUNDED_PROBE_REVIEW_ARTIFACTS_MISSING`
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - 將 bounded-review health answers 帶入 Cost Gate learning arm detail。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - 即使 ledger / blocked outcomes 已存在，也會把 bounded-review 缺失轉成 data-coverage blocker。
- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - worklist evidence carries bounded-review health fields。
- Tests:
  - healthcheck active fixture now requires sealed preflight + both bounded review artifacts。
  - added missing bounded-review artifact blocker test。
  - added alpha blocker test for `BOUNDED_PROBE_REVIEW_ARTIFACTS_MISSING`。

## 驗證

- Mac py_compile：touched modules passed。
- Mac `test_demo_learning_stack_healthcheck.py`：`7 passed`。
- Mac alpha/worklist focused：`60 passed`。
- Mac `git diff --check` passed。
- Source commit：`252b5bec Surface bounded probe reviews in stack health [skip ci]`。
- GitHub `origin/main` 已推送。
- Linux `trade-core:/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `252b5bec`。
- Linux py_compile passed。
- Linux same healthcheck tests：`7 passed`。
- Linux same alpha/worklist focused：`60 passed`。
- Linux read-only healthcheck smoke wrote `/tmp/openclaw/demo_learning_stack_healthcheck/demo_learning_stack_healthcheck_v404_smoke.json` and reported:
  - `status=NOT_INSTALLED`
  - `source_ready=true`
  - `stack_installed=false`
  - `sealed_horizon_probe_preflight_present=true`
  - `bounded_probe_result_review_present=false`
  - `bounded_probe_execution_realism_review_present=false`
  - `bounded_probe_reviews_present=false`

## 邊界

本 checkpoint 是 source/test/docs + Linux source sync/read-only tests + explicit temp healthcheck artifact only。未執行 CI。沒有 PG write/schema migration、沒有 Bybit private/signed/trading call、沒有 deploy/rebuild/restart、沒有 crontab install、沒有 env/auth/risk/order/strategy/runtime mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。

## 對盈利路徑的含義

這不是直接找到盈利策略，但它避免了一個危險假綠燈：ledger 和 blocked-outcome review 可以存在，bounded demo probe 的 result review / execution-realism review 卻沒有自動產生。

未來要把 demo 變成自主學習機器，stack health 必須證明完整鏈路：

1. Cost Gate rejects 被記錄。
2. 被拒信號有後驗 outcome。
3. blocked outcome review 找到 candidate。
4. sealed preflight 對齊 candidate。
5. bounded demo probe result review 自動生成。
6. execution-realism review 在需要時自動生成。

v404 把第 4-6 步納入健康檢查與 alpha blocker。

# 2026-06-22 — Bounded Probe Review Cron Wiring

## 結論

v403 補上 v398-v402 的 orchestration gap：`bounded_demo_probe_result_review_v1` 和 `bounded_demo_probe_execution_realism_review_v1` 之前已能被 alpha/worklist 讀取，但 production Cost Gate learning cron 並不會自動生成它們。

現在 `cost_gate_learning_lane_cron.sh` 在 ledger outcome refresh 和 blocked-outcome review 後，會自動刷新 bounded result review，再用同一輪新 result review 刷新 execution-realism review。這讓 demo learning lane 能長期積累「probe 是否真的捕捉 edge」和「為何沒有捕捉」的證據。

這不是 lowering Cost Gate，也不是 probe/order authority。

## Source 變更

- `helper_scripts/cron/cost_gate_learning_lane_cron.sh`
  - 新增 `OPENCLAW_COST_GATE_BOUNDED_PROBE_PREFLIGHT_JSON`，預設讀 `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json`。
  - 新增 `OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_RESULT_REVIEW=1`。
  - 新增 `OPENCLAW_COST_GATE_REFRESH_BOUNDED_PROBE_EXECUTION_REALISM_REVIEW=1`。
  - 產生 dated/latest：
    - `bounded_probe_result_review_*.json/.md`
    - `bounded_probe_result_review_latest.json/.md`
    - `bounded_probe_execution_realism_review_*.json/.md`
    - `bounded_probe_execution_realism_review_latest.json/.md`
  - execution-realism review 只讀本輪新產生的 result review，避免 stale latest artifact 誤導診斷。
  - status JSONL now records rc、skip reason、status、reason、completed probe outcomes、execution gap、primary hypothesis、fill-backed pct、`cost_gate_or_operator_review_allowed`。
- `helper_scripts/cron/tests/test_cost_gate_learning_lane_cron_static.py`
  - pin module invocation、latest artifact paths、skip reason、preinstall cutoff、status fields、review ordering。

## 驗證

- Mac `bash -n helper_scripts/cron/cost_gate_learning_lane_cron.sh` passed。
- Mac py_compile passed。
- Mac cron static + sealed preflight static：`18 passed`。
- Mac bounded/alpha focused suite：`71 passed`。
- Mac preinstall-only artifact smoke wrote new status fields。
- Mac `git diff --check` passed。
- Source commit：`53bce8db Wire bounded probe reviews into learning cron [skip ci]`。
- GitHub `origin/main` 已推送。
- Linux `trade-core:/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `53bce8db`。
- Linux bash/py_compile passed。
- Linux same static suite：`18 passed`。
- Linux same bounded/alpha suite：`71 passed`。
- Linux preinstall-only artifact smoke wrote new status fields。

## 邊界

本 checkpoint 仍是 source/test/docs + Linux source sync/read-only tests + temp artifact-only smokes。未執行 CI。沒有 PG write/schema migration、沒有 Bybit private/signed/trading call、沒有 deploy/rebuild/restart、沒有 crontab install、沒有 writer/env enablement、沒有 credential/auth/risk/order/strategy/runtime mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。

## 對盈利路徑的含義

這輪把「找 edge」和「學會捕捉 edge」之間的鏈路接實。未來如果 bounded demo probe 有真實 outcome：

- result review 會判斷 realized edge 是否過 first-review / learning-review floor；
- matched-control quality 會防止正收益 anecdote 被當成 gate evidence；
- execution-realism review 會把 under-capture 分解成 fill-backed、gross-edge timing、fee/slippage、entry-delay 等 repair hypotheses；
- alpha/worklist 能從 cron status/latest artifacts 看到下一個可執行修復點。

剩餘硬 gate 仍是 operator review + 未來 matched-control / edge-capture / execution-repair 實證，不是 Codex smoke。

# 2026-06-22 — Bounded Probe Execution-Realism Review

## 結論

v401 已阻止 positive bounded demo probe 在輸給 matched blocked-signal controls 時進入 Cost Gate/operator review。v402 把這個阻斷變成可執行的學習閉環：先生成 `bounded_demo_probe_execution_realism_review_v1`，分解 probe 為什麼沒有捕捉到 control edge，再根據第一個 hypothesis 修復或重放。

這不是 lowering Cost Gate，也不是追加 probe/order authority。它是 Cost Gate 之前的 edge-capture repair gate。

## Source 變更

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_execution_realism_review.py`
  - 新增 artifact-only review，讀 result-review JSON + `probe_ledger.jsonl`。
  - 匹配同 side-cell / horizon 的 `probe_outcome` 與 `blocked_signal_outcome` rows。
  - 輸出 probe/control avg net/gross/cost bps、entry delay、fill-backed pct、proxy count。
  - 輸出 net/gross/cost-or-slippage/entry-delay gap decomposition。
  - 產生 ordered hypotheses：`fill_backed_execution_missing`、`horizon_or_signal_timing_gross_edge_gap`、`fee_slippage_or_fill_cost_gap`、`entry_timing_delay_gap` 等。
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - ingest `bounded_probe_execution_realism_review_latest.json`，帶入 runtime killboard detail。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - under-capture 先要求 `bounded_probe_execution_realism_review_required`。
  - 已診斷則轉為 `bounded_probe_execution_realism_gap_diagnosed_repair_required`。
  - stale/unreadable、sample-floor、review mismatch 都 fail-closed。
- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - worklist evidence now carries status, primary hypothesis, gap fields, fill-backed pct, and `cost_gate_or_operator_review_allowed=false`。
- `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`
  - CLI 新增 `--bounded-probe-execution-realism-review-json`。
  - under-capture without review becomes `BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REVIEW_REQUIRED`。
  - diagnosed under-capture becomes `BOUNDED_DEMO_PROBE_EXECUTION_REALISM_REPAIR_REQUIRED`。

## 驗證

- Mac py_compile：touched modules passed。
- Mac focused pytest：
  - `test_cost_gate_bounded_probe_execution_realism_review.py`
  - `test_cost_gate_bounded_probe_result_review.py`
  - `test_profitability_path_scorecard.py`
  - `test_alpha_discovery_throughput.py`
  - `test_alpha_discovery_learning_worklist.py`
  - Result：`82 passed`。
- Mac `git diff --check` passed。
- Source commit：`7c04097f Add bounded probe execution-realism review [skip ci]`。
- GitHub `origin/main` 已推送。
- Linux `trade-core:/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `7c04097f`。
- Linux py_compile：touched modules passed。
- Linux focused pytest：same suite `82 passed`。

## 邊界

本 checkpoint 仍是 source/test/docs + Linux source sync/read-only test only。未執行 CI。沒有 PG write/schema migration、沒有 Bybit private/signed/trading call、沒有 deploy/rebuild/restart、沒有 cron install、沒有 env/auth/risk/order/strategy/runtime mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。

## 對盈利路徑的含義

核心假設是：市場可能存在 edge，但我們的 probe 未必能捕捉。v402 不再停留在「probe underperforms」這個標籤，而是把問題拆成可修的工程假說：

- 若沒有 fill-backed rows，先補真實成交或 L1 replay，不能信 proxy。
- 若 gross gap 為主，優先查 horizon retiming 或 signal timing。
- 若 cost gap 為主，查 fee/slippage/fill quality。
- 若 entry-delay gap 為主，查 queue timing / entry delay。

只有當 future probe 能在 matched-control 基礎上捕捉足夠 edge，Cost Gate/operator review 才有可審核證據。

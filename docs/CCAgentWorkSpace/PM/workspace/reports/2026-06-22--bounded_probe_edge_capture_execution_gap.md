# 2026-06-22 — Bounded Probe Edge-Capture Execution Gap

## 結論

v400 已要求正收益 bounded demo probe 必須有 same side-cell / same horizon matched `blocked_signal_outcome` control。v401 再補下一個盈利工程缺口：有 control 還不夠，probe 必須證明它能把 control 裡存在的 edge 捕捉成可實現 net PnL。

若 future probe 的 realized net 仍為正，但低於 matched blocked-signal control，系統現在會分類為 `PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP`，並在主閉環中轉成 `BOUNDED_DEMO_PROBE_EXECUTION_REALISM_GAP`。這代表下一步不是 Cost Gate/operator review，而是查 slippage、timing、fill quality、horizon retiming，直到能說明為何 alpha/control edge 沒有被 probe 捕捉。

## Source 變更

- `helper_scripts/research/cost_gate_learning_lane/bounded_probe_result_review.py`
  - `bounded_demo_probe_evidence_quality_v1` 新增 `probe_edge_capture_ratio`、`probe_execution_gap_bps`、`execution_realism_gap`。
  - 正收益 probe 若 `probe_minus_control_avg_net_bps <= 0`，evidence quality 改為 `PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP`。
  - under-capture 時 next action 優先 `investigate_probe_execution_realism_slippage_and_timing_before_cost_gate_review`。
- `helper_scripts/research/alpha_discovery_throughput/profitability_path_scorecard.py`
  - under-capture result review 轉為 `BOUNDED_DEMO_PROBE_EXECUTION_REALISM_GAP`。
  - profitability closure 保留 Cost Gate blocked，remaining proof gate 指向 execution realism gap。
- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - 將 edge-capture/gap fields 帶入 runtime killboard arm detail。
- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - under-capture blocker 轉為 `execution_realism` / `bounded_probe_result_review_probe_under_captures_matched_control_edge`。
- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - 新增 `bounded_probe_execution_realism` task type，completion gate 指向 execution-realism gap pass/reject evidence。

## 驗證

- Mac py_compile：touched modules passed。
- Mac focused pytest：
  - `test_cost_gate_bounded_probe_result_review.py`
  - `test_profitability_path_scorecard.py`
  - `test_alpha_discovery_throughput.py`
  - `test_alpha_discovery_learning_worklist.py`
  - Result：`77 passed`。
- Mac `git diff --check` passed。
- Source commit：`bc7053a9 Add bounded probe edge-capture gap review [skip ci]`。
- GitHub `origin/main` 已推送。
- Linux `trade-core:/home/ncyu/BybitOpenClaw/srv` fast-forwarded to `bc7053a9`。
- Linux py_compile：touched modules passed。
- Linux focused pytest：same suite `77 passed`。

## 邊界

本 checkpoint 仍是 source/test/docs + Linux source sync/read-only test only。未執行 CI。沒有 PG write/schema migration、沒有 Bybit private/signed/trading call、沒有 deploy/rebuild/restart、沒有 cron install、沒有 env/auth/risk/order/strategy/runtime mutation、沒有 Cost Gate lowering、沒有 probe/order authority、沒有 promotion proof。

## 對盈利路徑的含義

這一步把 demo 自主學習從「找到一個正收益 probe」推進到「確認 probe 是否能捕捉已存在的 matched-control edge」。如果捕捉不到，問題可能不是 alpha 不存在，而是交易實現品質不夠；系統會優先把工程注意力放到可修的 capture gap，而不是盲目放寬 Cost Gate。

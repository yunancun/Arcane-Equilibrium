# Sealed Horizon Alpha Worklist Bridge

## 結論

v389 已經證明 `sealed_horizon_learning_evidence_v1` 能把 `ma_crossover|BTCUSDT|Sell` 240m 推到 operator review，但該狀態停在 profit-learning decision packet。v390 把這個 review candidate 接入 alpha discovery blocker scorecard 和 learning worklist，讓自主工程隊列能看見下一步：先審 sealed evidence，再談極小 bounded demo probe。

這是「翻越 Cost Gate」路徑的工程閉環改進：不是全局降低 gate，而是把被 gate 擋住、事後在特定 horizon/side-cell 呈現正期望的信號，轉為可審核、可學習、可小步 demo 驗證的候選。

## Scope

- `helper_scripts/research/alpha_discovery_throughput/runtime_runner.py`
  - 從 `cost_gate_profit_learning_decision_packet_v1` 讀取 `sealed_horizon_learning_evidence`。
  - 在 Cost Gate arm detail 中輸出 sealed horizon fields：review status、side-cell、source kind、horizon minutes、blocked outcome count、avg gross/net bps、net-positive pct、review-ready flag。

- `helper_scripts/research/alpha_discovery_throughput/discovery_loop.py`
  - 將 `OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE` 分類為 `READY_FOR_PROBE`。
  - primary blocker 改為 `profit_learning_sealed_horizon_demo_probe_candidate_needs_operator_review`。
  - 把 sealed horizon evidence fields 傳入 profitability blocker detail row。

- `helper_scripts/research/alpha_discovery_throughput/learning_worklist.py`
  - learning task evidence 保留 sealed horizon fields。
  - operator-probe review objective 對 Cost Gate sealed horizon candidate 改為 `operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe`。
  - completion evidence 增加 sealed horizon review-ready / blocked-review candidate requirement。

## 測試與驗證

- `python3 -m py_compile helper_scripts/research/alpha_discovery_throughput/runtime_runner.py helper_scripts/research/alpha_discovery_throughput/discovery_loop.py helper_scripts/research/alpha_discovery_throughput/learning_worklist.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py` passed.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py -q` = `54 passed`.
- `PYTHONPATH=helper_scripts/research python3 -m pytest helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/research/tests/test_alpha_discovery_learning_worklist.py helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/research/tests/test_profitability_path_scorecard.py helper_scripts/research/tests/test_cost_gate_sealed_horizon_learning_evidence.py -q` = `67 passed`.
- `git diff --check` passed.

## 邊界

- No PG write/schema migration.
- No Bybit private/signed/trading call.
- No deploy/rebuild/restart.
- No env/auth/risk/order/strategy mutation.
- No Cost Gate lowering.
- No probe/order authority.
- No promotion proof.

## 角色與風險

按 repo 規則，完整量化/工程鏈通常需要 QC/MIT/AI-E + E1/E2/E4。這次我沒有派 sub-agent，原因是 operator 明確要求停止重複空轉、當前變更範圍狹窄且已有 focused regression 覆蓋；PM 直接承擔整合與驗證。未完成的審慎 gate 是：production learning lane 的 writer/cron/prod ledger 仍需在 operator-gated runtime 路徑持續積累真實 demo evidence，且 bounded demo probe 仍需單獨 operator approval。

## 下一步

1. Linux source fast-forward 後，以 artifact-only 或 focused pytest 確認 v390 在 Linux 可讀。
2. 不全局 lower Cost Gate；先 review `ma_crossover|BTCUSDT|Sell@240m` sealed evidence。
3. 打通 production learning lane 的持續積累證據，再設計最小 bounded demo probe preflight。

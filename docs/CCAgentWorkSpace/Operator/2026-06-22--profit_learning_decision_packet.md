# Profit-Learning Decision Packet

## 結論

新增 `helper_scripts/research/cost_gate_learning_lane/decision_packet.py`，純讀已有 JSON artifact，輸出一個 Cost Gate demo-learning next-step packet。它的目的不是下單或放寬 gate，而是讓 operator 一眼知道現在卡在：

- data-flow monitor missing
- reject counterfactual missing/stale
- bounded learning plan missing
- activation/stack health not ready
- blocked-outcome review missing
- blocked-outcome review 出現需要人工審核的候選

## Runtime Note

這次沒有在 `trade-core` 執行新 packet，因為 runtime source 仍未 reconcile。新 packet 可以在 source 對齊後放到 `/tmp/openclaw` artifact flow 旁邊執行，讀最新 monitor/scorecard/plan/preflight/review JSON。

## Example Command Shape

```bash
python3 helper_scripts/research/cost_gate_learning_lane/decision_packet.py \
  --data-flow-json /tmp/openclaw/demo_data_flow_monitor.json \
  --counterfactual-json /tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json \
  --plan-json /tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json \
  --activation-preflight-json /tmp/openclaw/cost_gate_learning_lane_activation_preflight.json \
  --blocked-outcome-review-json /tmp/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json \
  --output /tmp/openclaw/cost_gate_learning_lane/profit_learning_decision_packet.md \
  --json-output /tmp/openclaw/cost_gate_learning_lane/profit_learning_decision_packet.json
```

## Verification

- Mac py_compile passed for packet + focused test.
- Mac focused packet pytest passed: `5 passed`.
- Related focused regression passed: `81 passed`.
- CLI smoke without inputs returned fail-closed `DATA_FLOW_MONITOR_REQUIRED`.
- `git diff --check` passed before checkpoint completion.

## Boundary

No runtime fetch/pull/reset/clean/source sync was performed. No cron install, env edit, deploy/rebuild/restart, PG query/write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order authority, probe authority, or promotion proof was performed.

# Cost-Gate Blocked Outcome Review Scorecard

## 結論

已新增 `cost_gate_learning_lane.outcome_review`：它會讀 `probe_ledger.jsonl` 裡的 `blocked_signal_outcome`，按 side-cell 聚合，判斷這些被 cost gate 擋掉的信號是否只是需要繼續收集、應保持阻擋，或值得進入 operator review 的 demo probe authority 候選。

它不會授權下單，不會降低主 Cost Gate，不會寫 PG，不會呼叫 Bybit，不會改 runtime/risk/auth/order。

## 預設門檻

- 每個 side-cell 至少 3 筆 blocked outcome
- 平均 net bps >= 0
- net-positive pct >= 60%

達標也只是 `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE`，下一步仍是 operator review，不是自動放權。

## 命令

```bash
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.outcome_review \
  --ledger /tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl \
  --output /tmp/openclaw/cost_gate_learning_lane/blocked_outcome_review_latest.json
```

## 驗證

cost-gate focused `23 passed`；alpha-discovery focused `34 passed`；py_compile、CLI help、empty-ledger review smoke、diff-check 均通過。

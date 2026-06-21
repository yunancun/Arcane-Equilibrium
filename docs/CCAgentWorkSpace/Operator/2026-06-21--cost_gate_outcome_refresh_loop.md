# Cost-Gate Outcome Refresh Loop

## 結論

已把 cost-gate demo-learning lane 的「生成 price observations」和「寫 blocked outcomes」合成一個可重跑命令：`cost_gate_learning_lane.outcome_refresh`。

它預設 dry-run，不改 ledger；只有加 `--append-ledger` 才把 `blocked_signal_outcome` / `probe_outcome` append 到 `probe_ledger.jsonl`。`--source-pg` 只讀 `market.klines`，且沒有缺失 outcome window 時不連 PG。

## 建議用法

先 dry-run：

```bash
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.outcome_refresh \
  --ledger /tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl \
  --source-pg \
  --record-blocked-outcomes \
  --output /tmp/openclaw/cost_gate_learning_lane/outcome_refresh_latest.json
```

確認輸出後再 append：

```bash
PYTHONPATH=helper_scripts/research python3 -m cost_gate_learning_lane.outcome_refresh \
  --ledger /tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl \
  --source-pg \
  --record-blocked-outcomes \
  --append-ledger \
  --output /tmp/openclaw/cost_gate_learning_lane/outcome_refresh_latest.json
```

## 邊界

這只是學習資料閉環，不是下單授權。沒有降低主 cost gate，沒有 PG 寫入，沒有 Bybit trading call，沒有 runtime config / risk / auth / order mutation，也不是 promotion proof。

驗證：cost-gate focused `21 passed`；alpha-discovery focused `34 passed`；py_compile、CLI help、empty-ledger `--source-pg` smoke 均通過。

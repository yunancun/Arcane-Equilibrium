# Candidate-Scoped Standing Demo Authorization Artifact

日期：2026-06-24
狀態：`DONE_WITH_CONCERNS`

PM 已把 standing Demo/API 授權轉成候選限定 artifact：

- Candidate：`grid_trading|AVAXUSDT|Sell`
- Horizon：60m
- Cap：1 bounded Demo probe order
- TTL：4h
- JSON：`/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_standing_demo_20260624T160930Z.json`

結果：

```text
status=BOUNDED_DEMO_PROBE_AUTHORIZED
authorization_confirmation_source=standing_demo_authorization
blocking_gate_count=0
operator_authorization_object_emitted=true
```

邊界：

- 未覆蓋 `bounded_probe_operator_authorization_latest.json`
- 未跑 alpha refresh
- 未跑 runtime adapter
- 未寫 plan
- 未送 Bybit/API/PG
- 未改 crontab/service
- 未降低 Cost Gate
- 未開 live
- 未產生 promotion proof

`latest` 仍是 `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW` / `decision=defer` / `operator_authorization_object_emitted=false`，所以此 artifact 只是下一輪 propagation/admission review 的輸入，不是已啟動的下單權限。

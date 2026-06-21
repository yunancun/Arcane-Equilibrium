# 2026-06-21 -- Cost Gate Historical Scorecard Review

本輪已補上歷史 counterfactual review：系統能把已存在的 cost-gate reject scorecard 轉成 historical side-cell priority，讓 demo learning lane 在 runtime writer 尚未啟用前也不完全失明。

關鍵結論：

- historical candidates 只代表「值得優先捕捉真實 blocked outcome」。
- 它不是 `probe_ledger.jsonl`、不是 execution proof、不是 promotion proof。
- alpha killboard 會把 historical-only 候選標為 `historical_cost_gate_candidates_not_runtime_verified`，不會標成 `READY_FOR_PROBE`。
- 主 Cost Gate 沒有降低；order authority 仍是 `NOT_GRANTED`。

驗證已過：

- cost-gate learning focused pytest：`53 passed`
- alpha discovery focused pytest：`34 passed`
- cost-gate cron static pytest：`9 passed`
- py_compile + cron `bash -n` passed

剩餘真正 runtime blocker 沒變：`trade-core` 仍需 operator-approved source sync/reconcile、writer enablement、cron install/restart 後，才會開始累積 `probe_ledger.jsonl` / `blocked_signal_outcome` 證據。

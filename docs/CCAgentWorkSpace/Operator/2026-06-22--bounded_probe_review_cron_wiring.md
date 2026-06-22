# 2026-06-22 — Bounded Probe Review Cron Wiring

本輪不是放寬 Cost Gate，也不是授權 probe/order。

核心修正：之前 v398-v402 的 bounded result review / execution-realism review 已經能被主閉環讀取，但 Cost Gate learning cron 不會自動生成它們。這會讓 demo 學習閉環卡在「缺 artifact」，需要手動補。

現在 `cost_gate_learning_lane_cron.sh` 會在 ledger outcome refresh 後自動生成：

- `bounded_probe_result_review_latest.json`
- `bounded_probe_execution_realism_review_latest.json`

並在 `logs/cost_gate_learning_lane.log` 記錄 rc、skip reason、review status、execution gap、primary hypothesis、fill-backed pct、以及 `cost_gate_or_operator_review_allowed`。

重要邊界：

- execution-realism review 只讀同一輪新產生的 result review，避免 stale latest artifact 誤判；
- 沒有 lowering Cost Gate；
- 沒有 probe/order authority；
- 沒有 cron install / env mutation / deploy / restart；
- 沒有 PG write 或 Bybit private/signed/trading call。

已驗證：Mac bash/py_compile passed；Mac static suite `18 passed`；Mac bounded/alpha suite `71 passed`；Mac preinstall-only smoke 寫出新 status fields；source commit `53bce8db` 已推送；Linux `trade-core` 已 fast-forward 到 `53bce8db`；Linux 同套檢查 `18 passed` + `71 passed`，preinstall-only smoke 也寫出新 status fields。

盈利閉環上的含義：future demo probe 不再只是「下了/沒下」，而是會自動形成 result review 和 under-capture repair evidence。下一步仍需要 operator review + 真實 future matched-control / edge-capture / execution-repair evidence。

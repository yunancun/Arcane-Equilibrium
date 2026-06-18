# TODO v181 schedule-only duplicate cleanup

已從 TODO §5 移出兩個排程-only 重複項：

- `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`
- `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`

它們仍在 §7：

- 2026-06-27：bb_breakout/bb_reversion baseline vs retire/extend 決策。
- 2026-08-21：fallback dead-enum 90d audit + halt root-cause review；`halt_audit.log` 已就緒，除非 healthcheck 退步否則不提前。

邊界：文檔隊列整理；沒有 CI、沒有代碼改動、沒有 deploy/rebuild/restart、沒有 runtime/DB/auth/risk/order/trading mutation。

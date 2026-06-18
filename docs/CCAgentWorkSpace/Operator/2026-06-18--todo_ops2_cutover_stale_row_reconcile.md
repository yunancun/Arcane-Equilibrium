# Operator Brief — TODO v172 OPS-2 Cutover Stale Row Reconcile

日期：2026-06-18

PM 從 `TODO.md` §5 移出 stale `P1-OPS-2-PHASE-2-CUTOVER` row。

依據：cutover merge `3018c7a3` 已包含在 runtime source HEAD `83b7632d` 與目前 main；2026-06-11 runtime note 記錄 operator 指令下 `restart_all --rebuild` 後 OPS-2 cutover 新 binary 生效、0 fallback 字串、V137 applied。

未關閉的 operator 項目仍在 §6：

- C-B 手動 `/auth/renew` 留證；
- 2026-09-08 首次 rotation timing。

本輪不請求 operator action。未執行 CI、deploy、rebuild、restart，未改 production source/runtime/DB/auth/risk/order/trading state。

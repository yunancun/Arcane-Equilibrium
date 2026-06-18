# TODO v178 Reconciler Runtime-Status Correction

PM 修正了兩個 reconciler row 的狀態漂移，但沒有關閉它們。

- `bb7e9efc` / `baf46a69` 已在 Mac/Linux HEAD 祖先鏈內。
- Running engine PID 3134818 的 binary strings 已包含 `removed_position_semantics`、`dispatched-not-confirmed`、`reconcile_ghost_converge`。
- 因此 `P2-RECONCILER-GET-POSITIONS-PAGINATION` 不再標「未部署」。

仍保留 active：

- PM 1-4 integration report 仍要求 E2/E4/QA review。
- Production DB 目前沒有 `observability.engine_events.event_type='reconcile_ghost_converge'` rows，所以 D2 event proof 未閉。

本次只做 read-only source/runtime/DB verification 與 docs/TODO hygiene；沒有 CI、deploy、rebuild、restart、DB write、auth、risk、order 或 trading mutation。

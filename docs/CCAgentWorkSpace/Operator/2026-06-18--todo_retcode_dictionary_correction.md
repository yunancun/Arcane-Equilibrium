# TODO v179 RetCode Dictionary Correction

PM 關閉了純文檔性的 `P3-110017-BB-DOC-FOLLOWUPS` row。

- 110017 dictionary 已改成 D2 source-land/runtime-loaded，不再寫 pending IMPL。
- 110009 ambiguity 已依官方 Bybit V5 error table 裁定：110009 是 stop-orders-count limit，不是 PositionNotFound。

剩餘工作沒有被藏掉：

- `P2-110009-RETCODE-SEMANTICS-FIX` 追蹤 Rust drift：enum/test/comment rename，以及把 110009 從 close-equivalent-success NoOp classifier arm 移出或加 guard。
- BB 先前已裁定目前 SL/TP `set_trading_stop` path fail-loud，所以這是 P2 latent misclassification，不是 active P1 stop-loss swallow。

本次只做 docs/TODO hygiene + official-doc verification；沒有 code/runtime/deploy/DB/auth/risk/order/trading mutation。

# TODO v179 RetCode Dictionary Correction

日期：2026-06-18
角色：PM
範圍：`P3-110017-BB-DOC-FOLLOWUPS`

## 結論

`P3-110017-BB-DOC-FOLLOWUPS` 可以從 TODO §5 移出，因為它的兩個文檔任務已完成：

- 110017 dictionary 不再說 D2 是 `spec pending IMPL`，改為 source-land/runtime-loaded，但 event proof 仍另 gate。
- 110009 doc-version ambiguity 已用官方 Bybit V5 error table 裁決：110009 是 stop-orders-count limit，不是 PositionNotFound。

但這不是 110009 全面 closure。Rust code 仍有 legacy drift：

- `BybitRetCode::PositionNotFound = 110009`
- `dispatch.rs` `110001 | 110009 => DispatchOutcome::NoOp`
- 相關 tests/comments 仍用 `position idx not match` / PositionNotFound 口徑

因此 TODO §5 新增/保留 `P2-110009-RETCODE-SEMANTICS-FIX`，要求 E1->BB/E2/E4 後續修 code。BB 2026-05-30 已裁定 `set_trading_stop` SL/TP path 目前不經 dispatch classifier、會 fail-loud，因此這是 P2 latent misclassification，不是 P1 active stop-loss swallow。

## 證據

- Official Bybit V5 error table checked on 2026-06-18: `https://bybit-exchange.github.io/docs/v5/error`
- Official entries observed:
  - `110009`: stop orders count exceeds the maximum allowable limit
  - `110017`: order quantity would be truncated to zero
- Existing BB source-of-truth report: `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-30--BB--bybit_api_compatibility_audit.md`
- Local reference updated: `docs/references/2026-04-04--bybit_api_reference.md`

## Boundary

No CI, Rust code change, deploy, rebuild, restart, DB write, auth, risk, order, or trading mutation was performed.

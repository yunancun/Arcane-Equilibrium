# Source-Only Control Identity Contract No-Order

本輪把 AVAX future proof / matched controls / research controls 的 identity 規則做成 source-only helper。沒有交易、沒有 PG、沒有 cron/service 變更、沒有 Cost Gate/cap/risk mutation、沒有 authority/proof claim。

結果：

- 新增 `source_only_control_identity_contract.py` + focused tests。
- Smoke：`grid_trading|AVAXUSDT|Sell` contract ready。
- AVAX proof rows 必須 exact side-cell/strategy/symbol/side/horizon match。
- matched controls 必須 same-side-cell `blocked_signal_outcome`。
- SUI/FIL 等 cross-symbol controls 只能做 research，不能算 AVAX proof / Cost Gate proof / promotion evidence。
- P0 bounded authorization 仍 blocked/no-repeat；runtime auth artifact at `2026-06-26T08:00:05Z` still defer/no-authority。

下一步：

- 如果有真 AVAX-scoped auth delta，才進 P0 authorization。
- 否則下一個最快 source-only 落地點是 `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER`。

PM report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-26--source_only_control_identity_contract_no_order.md`.

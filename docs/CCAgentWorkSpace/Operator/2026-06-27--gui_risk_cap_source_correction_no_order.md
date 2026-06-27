# GUI Risk Cap Source Correction

狀態轉移：`DONE_WITH_CONCERNS`。

你說得對：GUI 的 `P1 Risk/Trade = 10.0%` 對應 Rust/TOML 的 `per_trade_risk_pct = 0.1`，不是 `10 USDT`。`10 USDT` 目前只是 Rust bounded-probe active order 的本地預設 envelope，不是全局風控單筆曝險上限。

本輪已修正 source-only 工具：

- quote/atomic runner 不再默認注入 `cap_usdt=10.0`。
- `current_cap_staircase_risk_worksheet.py` 改為從 GUI-backed RiskConfig + 可審核 equity 推導 `resolved_cap_usdt`。
- construction preview 裡的 `cap_usdt` 只保留為診斷欄位 `source_construction_cap_usdt`，不再當權威 cap。
- ETH/其他 candidate 的 public quote request 會使用 selected candidate symbol；candidate identity 不合法會在任何 public request 前 fail closed。

驗證：相鄰 tests `109 passed`，py_compile pass，`git diff --check` pass。

本輪沒有 runtime sync、沒有 Bybit call、沒有 PG、沒有下單、沒有 Cost Gate lowering、沒有 risk expansion、沒有任何 probe/order/live authority。

下一步：先用 GUI/Rust RiskConfig + audited Demo equity 做 ETH 的 no-order cap resolver；如果 cap 無法機器可檢查地 resolved，就標記 `BLOCKED_BY_LOSS_CONTROL`，不進 order-capable path。

# Operator Note — Cap Envelope Evidence Floor Source Patch

Date: 2026-06-26 09:24 CEST

本輪把 cap-envelope 證據地板接進了 `cost_gate_autonomous_parameter_proposal_v1`。這是 source/test/docs only，不是 runtime sync，不會讓 ETH 或任何候選獲得 cap/order/probe 權限。

新增的 proposal 欄位要求：candidate-matched controls、費用/滑點/maker-taker 標籤、fresh BBO/instrument metadata、cap staircase、portfolio exposure math、execution realism、proof-exclusion、regime/freshness/survivorship、repeat/OOS path。

驗證通過：autonomous proposal + false-negative preflight tests `10 passed`，`py_compile` PASS，`git diff --check` PASS。

下一步如果要讓 runtime scheduled artifacts 帶出這個新欄位，需要單獨做 runtime sync review；本輪沒有做 runtime 變更。

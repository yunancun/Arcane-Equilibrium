# Operator Summary — GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1 WP2-B2.2b

State: `DONE_SOURCE_ACCEPTED_B2_2B_COST_PROVENANCE`
Checkpoint: `a7d8d5f8b3af3282ab75667b31e45a40a712b2c4`
Next: `WP2-B2.2c-RESTART-SAFE-EVENT-DRIVEN-PRIMARY-HANDOFF`

B2.2b 的 source vertical 已接受。fully rehashed artifact 現在不能把 global
mean 造得低於各 symbol 依 sample count 加權後的值；signed cost 不能超過
absolute cost。NaN/Inf/bool/numeric string、錯 count、缺 nested key、hash 或
因果順序錯誤都會 fail closed。thin symbol 只能用已驗證 global fallback，不能
把成本錯降。

publisher -> board -> adapter -> arbiter 會綁定同一份 canonical cost evidence；
JSON key order 不變時語義與 hash 一致，material value 變更會改 hash/fingerprint。
candidate eligibility、ranking、cooldown、proof gap 都不能繞過 cost evidence。

證據：final focused `4 passed`（包括 global 與 symbol 的 `5e-10` signed-cost
overage）；最終 bytes 的完整整合 suite 僅跑一次，`586 passed in 6.38s`；E2、QC、
QA 都 PASS，P0/P1 `0/0`。治理 wrapper 對替代 interpreter
是在 subprocess 前拒絕，沒有偷跑；明確 source/test 授權下才以既有
`venvs/mac_dev` interpreter 完整跑一次。

本輪沒有 Linux、service、PG、cron、Bybit、order、Decision Lease、Cost Gate、
training、serving、promotion 或任何 authority 動作。它不是 runtime、qualified
candidate、Proof/Reward、實際 training、OOS 或獲利證明。

下一個工作已切換到 B2.2c：event-driven primary、cron 僅 reconciliation、
restart-safe cursor/state、candidate board v2 實際送進 ALR consumer，並在沒有
qualified candidate 時 durable no-candidate/rotate、避免重複 no-delta DEFER。
之後若要 runtime 驗證，必須另開 fresh exact E3/BB gate。

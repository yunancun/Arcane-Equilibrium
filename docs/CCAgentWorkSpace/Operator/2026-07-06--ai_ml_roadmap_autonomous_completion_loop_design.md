# 2026-07-06 AI/ML Roadmap Autonomous Completion Loop Design

PM sign-off: `APPROVED-AS-ENGINEERING-GOVERNANCE-DESIGN`

Revision: `2026-07-06-continuous-state-v2`

這份設計把 AI/ML roadmap 變成一個「自治工程推進 loop」，不是交易 loop。

核心結論：

- loop 先讀 `TODO.md`，所以當前 P0 仍是 standing Demo loss-control envelope refresh；過期授權不會被 roadmap 繞過。
- roadmap 只按 gate 推進，不按日曆推進。沒有 ProofPacket、PIT manifest、candidate-matched outcome，就不能跳到模型、bandit、RL 或 MCP runtime。
- 每輪只選一個 work item，自動做邊界檢查、派工/實作、測試驗證、效果評估，然後繼續、輪換或停止。
- 自動評估使用 `implementation_effect_review_v1`：看 gate 是否真的從 blocked 變 ready、是否產生機器可檢 artifact、測試是否通過、是否有權限擴張。
- 每輪都必須寫 `roadmap_loop_state_packet_v1`，不只停止時寫。`ADVANCED` / `ADVANCED_WITH_CONCERNS` 代表下一輪必須繼續，不是終點。
- 自動停止仍使用同一個 state packet：遇到 loss-control、runtime/order/private/MCP/live 邊界、測試失敗、source drift、連續 no-delta、預算耗盡或需人工決策時 fail-closed。
- 若上一輪只有 effect review 沒有 state packet，下一輪必須先補 recovery state packet，再接 `next_work_id`。

不授權：

- 不授權 runtime mutation、DB write、exchange/private read、MCP server/credential、order/probe、Cost Gate change、deploy、live/mainnet。
- 如果某步需要這些能力，loop 只能停止並要求既有 PM->E3->BB 或 operator gate。

建議第一批落地順序：

1. `proof_packet_v1` source contract + validator + tests。
2. PIT dataset manifest contract + rebuild/hash tests。
3. 若要推 runtime 證據，再走 current-head standing envelope refresh 的既有 E3/BB 流程。

針對已發生的 WP1 dry-run：

- `WP1-PROOF-PACKET-V1` 有效前進，但缺 state packet，且 source feature chain 被縮短。
- 下一輪應先補 `ADVANCED_WITH_CONCERNS` state packet，記錄 `next_work_id=WP2-PIT-DATASET-MANIFEST`。
- 然後繼續 WP2；同時保留或先關閉 `b9867ac9e` 缺 E2/E4/QA 獨立審查的 concern。

報告正本：

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_autonomous_completion_loop_design.md`

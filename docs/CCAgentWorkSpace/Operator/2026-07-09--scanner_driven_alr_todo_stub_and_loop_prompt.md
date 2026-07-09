# Operator Summary: Scanner-Driven ALR Todo Stub And Loop Prompt

Date: 2026-07-09
Status: `DONE_WITH_CONCERNS`
Boundary: `SOURCE_ONLY_OFFLINE_P0_P1`

已完成一輪 subagent 對抗性審核並落地 AI/ML ALR todo stub 目錄：

`docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/`

核心結論：

- 這是一個 Codex source-development loop，不是 runtime loop。
- P0/P1 只允許本地 source CLI、tests、reports、artifacts。
- 不授權 runtime、PG、IPC、Bybit、official MCP、Decision Lease、order/probe、
  Cost Gate、serving、proof、promotion、live/mainnet 或 delete/apply。
- Scanner 只提供 learning target intake evidence，不能成為 order permission
  或 profit proof。
- P0 目標是 `expected_value_of_information`，不是預期交易 PnL。
- RetentionGuardian P0 只產生 dry-run manifest，保護 proof/disputed/negative/
  lineage/audit artifacts。

給新 Codex session 的啟動 prompt 在：

`docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/startup_prompt.md`

第一個自動 work item 是：

`P0-AIML-ALR-BOUNDARY-PACKET`

固定產出目標是：

`docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/boundary_packet.md`

如果 required role-chain dispatch tooling 不可用，loop 必須停止為
`STOP_DISPATCH_BLOCKED`，不得自行降級成單 agent 直接實作。

驗證：manifest JSON parse PASS；stub 目錄 `git diff --check` PASS。未跑
production code tests，因本輪只新增 docs/stub/prompt。未觸碰 runtime、PG、
Bybit/MCP、order、Decision Lease、Cost Gate、`_latest`、model serving 或
cleanup apply。

---
name: 外部整合工具入口（Linear / Notion / Coupler / Drive）
description: OpenClaw 4 個外部 MCP 工具的 workspace ID、bootstrap 狀態、權威邊界
type: reference
---

**完整 SOP**：CLAUDE.md §十二「外部整合工具映射」。本 memory 只存入口資訊與 bootstrap 編號。

## Linear（remediation tracker）

- Team: `NCYu`（id `0ac8e33e-9f7b-4406-b803-6716bf5765a7`）
- Project: [`OpenClaw 62-Finding Remediation`](https://linear.app/ncyu/project/openclaw-62-finding-remediation-de1bc8f68e42)（id `557ab98c-5500-4a0b-9b0f-ba65104c68a5`）
- Milestones (6): Batch A-F 對應 `docs/audit/remediation_tracking.md` Batch 列
- Labels (7): `P1` / `P2` / `P3` / `live-release-blocker` / `backlog` / `time-driven` / `edge-diag`
- Issues 起點：`NCY-5` (Batch A) → `NCY-10` (Batch F) + `NCY-11..15` active items + `NCY-16` rolling backlog
- 鏡像對象：62-finding mainline + active backlog + time-driven items；**不**鏡像所有 TODO.md 條目

## Notion（reports / sign-offs / RFCs index）

- Hub: [OpenClaw — Operator Hub](https://www.notion.so/350dcd3b1eff81038de2d10874ae0fe4)（id `350dcd3b-1eff-8103-8de2-d10874ae0fe4`）
- Sub-pages:
  - [Sign-Offs Index](https://www.notion.so/350dcd3b1eff8156a291ea8daddff454) — PM Wave / Batch sign-offs
  - [PA RFC Index](https://www.notion.so/350dcd3b1eff81c5965cda51f9e8fe91) — architecture RFCs
  - [Audit Reports Index](https://www.notion.so/350dcd3b1eff815cb3d6e2cda8f80322) — `docs/audit/` + `.claude_reports/` mirror
  - [External-Tool Workflow](https://www.notion.so/350dcd3b1eff8122a033d01823988db0) — 工具治理 SOP
- 不貼全文，1-line 條目連回 git 即可

## Coupler.io（ETL）

- MCP server id `728ba839-5540-454e-84b6-1e74dce58836`
- Status: connected, **no active dataflow**（按需啟用）
- Use cases: PG `learning.*` → Sheets ad-hoc dashboard / Linear issue → 週報 Sheet
- 嚴禁：寫回 PG（PG 寫入由 `srv/sql/` migration + Rust trading_writer 獨家治理）

## Google Drive（artifact store）

- MCP server id `4f87d4f7-8259-4ae9-9450-f1030f9cdbb2`
- Status: connected, **no curated content**（按需使用）
- Use cases: PDF audit 對外分享 / screenshot 長期歸檔 / 第三方 binary 暫存
- 嚴禁：repo 鏡像（git 是 source of truth）

## Declined / on-hold tools

### MotherDuck — DECLINED 2026-04-29

MCP id `4e73f78d-e980-4585-8586-5f2763080a09` 確認連接，但 operator 評估後 **放棄啟用**。理由：

1. **本機性能吊打 Free Plan**：Linux trade-core 128 GB unified mem，本機 DuckDB / Polars 直接讀 PG 比 Pulse Duckling（最小 compute）+ 10 CU-hours/月 上限快得多
2. **single-operator project**：MotherDuck 「5 users / share dive」協作紅利拿不到
3. **多一條 ETL = 多一個 silent drift 點**：類似 `decision_outcomes` timeframe 字串格式 100% NULL 的教訓，沒必要為「browser 看數據」邊際收益新增 drift surface

**替代方案**（若需冷分析湖）：本機 DuckDB + `postgres_scanner` extension，免雲端 / 免 ETL / 免 CU limit。

**重新評估 trigger**（出現任一才需重啟此決策）：
- Operator 需要手機 / 出差時 browser 看 OpenClaw dashboard
- 需對外人（顧問 / 學術合作者）share 數據（MotherDuck share link 比 ssh access 安全）
- PG 真的卡死且本機 DuckDB 不可行

Operator 仍可從 Claude Code `/plugin` 主動解除 MotherDuck connector 釋出 slot。本 memory 標 declined 即足夠 — 未來 sub-agent 看到 MCP 列表中的 MotherDuck，按本條 ref 跳過評估即可。

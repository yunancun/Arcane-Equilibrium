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

## MotherDuck 註

Operator 2026-04-29 提及添加 MotherDuck，但當下載入的 MCP server 為 Google Drive（4f87d4f7）。MotherDuck MCP 若有獨立 ID 未列出，需 operator 手動再啟。本 memory 標 Drive 為實際連接的，非 MotherDuck。

---
name: 外部整合工具入口（Linear-only active posture）
description: OpenClaw 外部 MCP 工具狀態盤點 — Linear active；Notion frozen；Coupler/Slack/MotherDuck declined；Drive passive
type: reference
---

**完整 SOP**：CLAUDE.md §十二「外部整合工具映射」。本 memory 存入口資訊 + 各工具 status + decline 理由（避免未來 sub-agent 重新評估）。

**Posture（2026-04-29 operator 簡化決定）**：**Linear 是唯一 active workflow tool**。其他工具不融入工作流，沒有 SOP gate。

## 🟢 ACTIVE — Linear（唯一 active workflow tool）

- Team: `NCYu`（id `0ac8e33e-9f7b-4406-b803-6716bf5765a7`）
- Project: [`OpenClaw 62-Finding Remediation`](https://linear.app/ncyu/project/openclaw-62-finding-remediation-de1bc8f68e42)（id `557ab98c-5500-4a0b-9b0f-ba65104c68a5`）
- Milestones (6): Batch A-F 對應 `docs/audit/remediation_tracking.md` Batch 列
- Labels (7): `P1` / `P2` / `P3` / `live-release-blocker` / `backlog` / `time-driven` / `edge-diag`
- Issues 起點：`NCY-5` (Batch A) → `NCY-10` (Batch F) + `NCY-11..15` active items + `NCY-16` rolling backlog
- 鏡像對象：62-finding mainline + active backlog + time-driven items；**不**鏡像所有 TODO.md 條目
- **Pricing**：Free Plan（1 user 充足，無付費風險）

**SOP**：Wave/Batch Sign-off git commit landed 之後，主會話更新對應 Linear 父 issue（checklist + status flip）。

## ❄️ FROZEN — Notion（保留快照不維護）

- Hub: [OpenClaw — Operator Hub](https://www.notion.so/350dcd3b1eff81038de2d10874ae0fe4)（id `350dcd3b-1eff-8103-8de2-d10874ae0fe4`）
- Sub-pages（5 個都是 2026-04-29 bootstrap 快照）:
  - [Sign-Offs Index](https://www.notion.so/350dcd3b1eff8156a291ea8daddff454)
  - [PA RFC Index](https://www.notion.so/350dcd3b1eff81c5965cda51f9e8fe91)
  - [Audit Reports Index](https://www.notion.so/350dcd3b1eff815cb3d6e2cda8f80322)
  - [External-Tool Workflow](https://www.notion.so/350dcd3b1eff8122a033d01823988db0) — ⚠️ **內容已過時**（描述舊版 SOP 含 Coupler/MotherDuck），以 CLAUDE.md §十二為準
- **狀態**：保留作為 bootstrap 紀錄；**不再同步更新**（operator 2026-04-29 決定不融入工作流）
- **不要更新**：除非 operator 主動要求解凍
- **Pricing**：Free Plan（1 user，unlimited blocks）

## 🟡 PASSIVE — Google Drive（按需 binary store）

- MCP server id `4f87d4f7-8259-4ae9-9450-f1030f9cdbb2`
- Status: connected, **no curated content**
- 無 SOP；只在 operator 明確要求才用（PDF audit 對外分享 / screenshot 長期歸檔）
- 嚴禁：repo 鏡像（git 是 source of truth）

## ❌ DECLINED — 已決定不啟用的工具

### Coupler.io — DECLINED 2026-04-29

- MCP server id `728ba839-5540-454e-84b6-1e74dce58836`
- 連接器留著但 **不啟用 dataflow**；**不**走 PG → Sheets 路徑
- 理由：
  1. 本機 DuckDB / psql 解所有 use case，免雲端 dep
  2. ETL = silent drift surface（已有 `decision_outcomes` timeframe NULL 教訓）
  3. Free tier 通常 1 dataflow 限制，啟用就跳到 ~$24/月起跳
- 替代方案：本機 DuckDB + `postgres_scanner` extension
- 重新評估 trigger：本機 DuckDB / psql 真的不可行（極不可能）

### Slack — DECLINED 2026-04-29（may revisit ~2026-05-15）

- 不 authenticate；engineering plugin pack 中 OAuth handshake 不執行
- 理由：
  1. Single-operator project — Slack 團隊協作紅利拿不到
  2. Demo 階段 alert 沒急迫性（SSH/terminal 已能看 healthcheck）
  3. fill 數據 / authorization 狀態進 Slack = sensitive 資料外漏面
- 重新評估 trigger：approaching live trading（~2026-05-15）需 mobile alert channel；屆時設計 1 個 alert-only channel（不放 chatty 訊息）

### MotherDuck — DECLINED 2026-04-29

- MCP id 曾為 `4e73f78d-e980-4585-8586-5f2763080a09`（**已從 CC config 移除**）
- 理由：
  1. 本機性能吊打 Free Plan（Linux trade-core 128 GB unified mem）
  2. Single-operator → share/collab feature 拿不到
  3. ETL drift 風險
- 替代方案：本機 DuckDB + `postgres_scanner`
- 重新評估 trigger：
  - Operator 需要手機 / 出差 browser dashboard
  - 對外 share 數據（顧問 / 學術合作）
  - PG 卡死 + 本機 DuckDB 不可行

## 為什麼這份 memory 重要

未來 sub-agent 在 deferred tools 列表看到 Coupler / Slack / Drive / Notion MCP 仍 connected，**不要主動評估「是否該啟用」** — 按本 memory 的 status 直接跳過。Operator 已做決策，重新評估 = 浪費 token + 違反 minimal confirmation 偏好。

只有「重新評估 trigger」明示出現時才考慮。

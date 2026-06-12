# Architecture

> **STABLE / REFERENCE ROUTER**
>
> 本目录保存系统结构设计、架构 overlay 和历史 MAG ledger。它不是 active
> dispatch queue；当前 blocker、owner、gate、runtime evidence 仍以根目录
> `TODO.md` 为准。

## Current / Stable Entries

| 需要 | 先读 |
|---|---|
| OpenClaw 控制平面定位 | `2026-05-06--openclaw_control_plane_repositioning.md` |
| Canary / release gate 架构 | `2026-05-10--ARCH-04-graduated-canary-5-stage.md` |
| 数据存储架构 | `DATA_STORAGE_ARCHITECTURE_V1.md` |
| Singleton authority | `singleton-registry.md` |

## Historical Ledgers

| 路径 | 语义 |
|---|---|
| `multi_agent_rework_2026-05-05/` | Historical MAG ledger / reference. 当前 OpenClaw Gateway、5-Agent、Decision Lease 和 active tails 必须回到 `TODO.md`、`docs/_indexes/initiative_index.md` 和最新报告确认。 |

## 使用规则

- 新架构决策优先走 `docs/adr/` 或 governance amendment；本目录放稳定 overlay
  和设计说明。
- 旧 architecture 文档可能保留已被 ADR/TODO/PM report 更新的语义；读前先看顶部
  banner 和 `docs/_indexes/initiative_index.md`。

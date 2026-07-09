# Governance Development — 二次開發治理文件庫

> **ROUTING NOTE**
>
> 本目录大部分 phase/T2.xx 文档是 Python-era / early governance 历史证据。
> 当前仍 active 的治理入口是 `SPECIFICATION_REGISTER.md`、`amendments/`、
> ADR/AMD、`CLAUDE.md`、`.codex/MEMORY.md` 和根目录 `TODO.md`。历史文件不做
> 大规模重命名；命名约束见 `NAMING_NOTE.md`，退役/例外口径见 `DEPRECATED.md`。

本目錄存放 OpenClaw/Bybit 二次開發過程中產生的所有評估報告、審計結果、修改日誌和新建記錄。

## 目錄結構

```
governance_dev/
├── README.md                  ← 本文件
├── SPECIFICATION_REGISTER.md  ← 仍 Active spec 索引（SM/EX/DOC/ADR/AMD/AUDIT + Amendments）
├── amendments/                ← 仍 Active spec amendments（正式規範修訂記錄）
├── DEPRECATED.md / NAMING_NOTE.md ← 退役口徑 + 命名約束
└── 2026-03-30--round2_fix_plan* 等根層文件 ← Round 2 修复计划等仍 active 根層文件
```

> **2026-07-09 归档**：历史 phase / T2.xx 子目录（`phase0_takeover/`、`phase1_gap_analysis/`、
> `phase2_execution/`、`changelogs/`、`governance_extracts/`、`audits/`、`phase2..12*` 等）已整体
> 移至 `docs/archive/2026-07-09--governance_dev_phase_history/<同名子目录>/`。历史 T2 执行总览
> （`T2_EXECUTION_SUMMARY.md` 等）现位于该 archive 的 `phase2_execution/` 下。

## 文件命名規範

- 報告：`T{phase}.{task}_{ROLE}_{TOPIC}.md`（如 `T0.1_FA_DIRECTORY_ARCHITECTURE.md`）
- 日誌：`{YYYY-MM-DD}_{TOPIC}.md`（如 `2026-03-30_T2.01_authorization_state_machine.md`）

## 角色代碼

| 代碼 | 角色 | 職責 |
|------|------|------|
| PM | Project Manager | 計劃、協調、決策 |
| FA | Framework Architect | 架構設計 |
| E2 | Core Logic Engineer | 核心邏輯實現 |
| AI-E | AI Integration Engineer | AI 層整合 |
| R1 | Document Auditor | 治理文件審計 |
| CC | Code Custodian | 代碼清潔度 |

## 工作流

新建或修改治理文档时，按当前仓库规则执行：先确认 source of truth、
用窄 staging / `git commit --only` 保护无关 WIP，提交信息必须有 subject
和 body；是否 push / 三端同步以 `CLAUDE.md`、`.codex/MEMORY.md` 和 operator
指令为准。旧的“默认直接 commit + push”不再作为当前工作流。

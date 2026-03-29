# Governance Development — 二次開發治理文件庫

本目錄存放 OpenClaw/Bybit 二次開發過程中產生的所有評估報告、審計結果、修改日誌和新建記錄。

## 目錄結構

```
governance_dev/
├── README.md                  ← 本文件
├── phase0_takeover/           ← Phase 0 接手：目錄架構、代碼閱讀、AI 整合評估
├── phase1_gap_analysis/       ← Phase 1 差距分析：22 份治理文件 vs 代碼對比
├── phase2_remediation/        ← Phase 2 修復執行：狀態機實現、風控擴展等
└── changelogs/                ← 修改日誌：每次代碼變更的記錄
```

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

所有新建的 .md 文件默認直接 commit + push 到 GitHub。
Ubuntu 端通過 `git pull` 同步。

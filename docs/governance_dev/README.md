# Governance Development — 二次開發治理文件庫

本目錄存放 OpenClaw/Bybit 二次開發過程中產生的所有評估報告、審計結果、修改日誌和新建記錄。

## 目錄結構

```
governance_dev/
├── README.md                  ← 本文件
├── phase0_takeover/           ← Phase 0 接手：目錄架構、代碼閱讀、AI 整合評估（5 份報告）
├── phase1_gap_analysis/       ← Phase 1 差距分析：22 份治理文件 vs 代碼對比（2 份報告）
├── phase2_execution/          ← Phase 2 執行：T2.01–T2.23 治理模組實現（3 份審核報告）
│   ├── T2_EXECUTION_SUMMARY.md         ← ★ 執行總覽（21 模組矩陣 + 關鍵指標）
│   ├── T2_PM_QUALITY_AUDIT_REPORT.md   ← PM 品質審核（2026-03-29）
│   └── T2_TW_COMMENT_AUDIT_REPORT.md   ← TW 註釋品質審核（2026-03-30）
└── changelogs/                ← 修改日誌：T2.01–T2.23 共 23 份變更記錄
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

---
name: reference-ultracode-full-audit
description: ultracode 全盤審計編排的持久化設置 — saved workflow + conductor skill 的位置與調用方式
metadata: 
  node_type: memory
  type: reference
  originSessionId: f24d69ff-8ed3-407e-9b02-642e02da37d9
---

Operator 很少跑 ultracode，但啟用後希望編排形態即取即用（手動 prompt 或自動識別）。2026-06-10 已落地為兩件套（單副本在 srv/.claude，根目錄 symlink）：

- **Saved workflow**：`srv/.claude/workflows/openclaw-full-audit.js` — 審計群並行（默認 CC/E3/FA/E5/MIT/R4，可選 QC/BB/A3/AI-E）→ C/H 對抗複核（雙質疑者：證據鏈+影響復現）→（`args.fix=true` 才）E1 worktree 修復→E2 複審→E4 回歸對照 BASELINE。**默認 report-only**，`max_fixes` 默認 5。
- **Conductor skill**：`srv/.claude/skills/ultracode-full-audit/SKILL.md` — 主會話專用（不掛 subagent）；含模式識別規則（ultracode off→降級 PM 順序鏈或徵求同意；active model 自檢；計費知情）與調用方式 `Workflow({name:"openclaw-full-audit", args})`，名稱解析失敗 fallback `scriptPath`。

**How to apply**：operator 啟用 ultracode + 說「全盤審查/全面檢查」→ 主會話按該 skill 跑 workflow；修復要二次顯式 `fix:true`。單點改動不用它，走 PM.md 派工模板+對抗驗證多視角化協議。

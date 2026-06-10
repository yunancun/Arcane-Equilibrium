---
name: ultracode-full-audit
description: OpenClaw 全盤多視角審計編排設置（主會話/conductor 專用，非 subagent skill）。當 operator 啟用 ultracode 並要求「全盤審查/全面檢查/multi-agent 優化」時使用：以 Workflow 調用 saved script openclaw-full-audit；未啟用 ultracode 時降級為 PM 順序鏈或先徵求 operator 同意。
---

# Ultracode 全盤審計編排（持久化設置）

> 本 skill 是給**主會話（conductor）**的編排說明書，不掛載到任何 subagent。
> 正本腳本：`.claude/workflows/openclaw-full-audit.js`（Mac: `~/Projects/TradeBot/srv/`；Linux: `~/BybitOpenClaw/srv/`）

## 模式識別（先判斷再動）

1. **ultracode 已啟用**（session 設置開啟，或 operator 本輪輸入含 ultracode）→ 直接按下方調用方式跑 Workflow。
2. **未啟用 ultracode** → 不得擅自跑 multi-agent fan-out：向 operator 確認，或降級為 PM 順序鏈（PM.md 派工模板逐軸派發，成本低很多）。
3. **active model 自檢**：主會話 system prompt 會聲明當前模型。頂級模型（Fable/Opus 級）→ 編排與對抗複核由主迴圈直接承擔；較小模型 → 仍可跑本 workflow（編排邏輯在腳本內是確定性的），但 Fix 段建議改 report-only，修復交 operator 後續派工。
4. 訂閱計費注意：頂級新模型可能按倍率/credits 計量（以官方 pricing 為準）——大規模 fan-out 前先確認 operator 知情。

## 調用方式

優先用名稱解析；失敗則用 scriptPath（絕對路徑按本機倉庫位置拼接）：

```
Workflow({ name: "openclaw-full-audit", args: {...} })
// fallback:
Workflow({ scriptPath: "<SRV>/.claude/workflows/openclaw-full-audit.js", args: {...} })
```

### args（全部可選）

| 參數 | 默認 | 說明 |
|---|---|---|
| `scope` | srv/ 全倉 | 審計範圍描述（傳給每個審計 agent） |
| `axes` | `["CC","E3","FA","E5","MIT","R4"]` | 審計軸=agent 名；可加 `"QC","BB","A3","AI-E"` |
| `fix` | `false` | **默認 report-only**；true 時對 confirmed C/H 派 E1 修復（worktree 隔離）+E2 複審+E4 回歸 |
| `max_fixes` | 5 | fix 模式單輪修復上限，餘量留報告 |

## 編排形態（腳本內建，無需手動執行）

審計群並行 fan-out（結構化輸出：severity+confidence+證據）→ C/H 發現對抗複核（證據鏈質疑者 ∥ 影響復現質疑者，全反駁=剔除、單反駁=標分歧）→（fix 模式）E1 worktree 修復 → E2 對抗複審 → E4 全量回歸對照 BASELINE。

## 產出處理（conductor 責任）

- Workflow 返回結構化結果：confirmed/disputed/medium_low_info/fixes/regression。
- 按 PM 合議規則整合：嚴重性 > 證據強度；多視角獨立命中=置信升級；分歧項列明雙方理由交 operator。
- 修復落地走既有鏈：commit 由 operator 或 PM 簽核；部署 operator-gated。
- 各審計 agent 已按自身完成序列落盤 workspace 報告，可追溯。

## 與常規鏈的關係

本 workflow 不替代日常 E1→E2→E4 鏈與 PM 順序派工——它是「全盤體檢」場景的批量形態。單點改動仍走 PM.md 的派工模板與對抗驗證多視角化協議。

# Operator — 最終呈現報告存檔

本目錄存放所有最終呈現給 Operator 的報告。

## 存放規則

- **存放對象**：多 Agent 合議後的結論性報告、Sprint 計劃確認、Wave 完成驗收摘要、任何需要 Operator 決策的分析輸出
- **不存放**：各 Agent 的工作草稿、中間過程報告（那些存在各 Agent 自己的 workspace 下）
- **命名格式**：`YYYY-MM-DD--主題描述.md`

## 報告類型

| 類型 | 說明 | 觸發時機 |
|------|------|---------|
| `wave_plan` | Wave 計劃確認（Sprint 結構 + 派發 + CC 評級）| 每個 Wave 規劃完成後 |
| `wave_complete` | Wave 完成驗收摘要（測試數 + 關鍵改動 + 遺留問題）| 每個 Wave commit 後 |
| `audit_summary` | 審計結論摘要（多 Agent 合議後的精簡版）| 全系統審計完成後 |
| `decision_required` | 需要 Operator 做決策的分析（含選項 + 建議）| 有分歧需要拍板時 |
| `status_snapshot` | 系統狀態快照（定期或按需）| 按需 |

## 報告索引

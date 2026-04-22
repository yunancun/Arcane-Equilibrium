# Claude Code 錯誤模式與預防規則庫

**定位**：Operator 每次糾正後，CC 抽象成可 grep 的模式規則寫入本檔，會話起手掃近期相關條目以降錯誤率。

**與 auto-memory `feedback_*.md` 的區別**：
- 本檔 = 技術/流程錯誤模式庫（可 grep；跨 CC 實例可讀；CC 自己維護）
- memory/feedback = operator 偏好與工作風格（通過 auto-memory 系統跨 session 持久化）
- 兩者互補不重複：行為偏好進 memory；「做錯 X 應做 Y」進 lessons

**條目格式**：

```markdown
## YYYY-MM-DD · <錯誤模式短名>
- **場景**：觸發條件（什麼情境下容易犯）
- **錯誤模式**：具體做錯了什麼
- **預防規則**：下次遇到該場景時的行為準則
- **相關檔案 / 指令**：grep 起點（可選）
- **來源 commit / session**：追溯（可選）
```

**維護準則**：
- 同模式第 2 次犯 → 條目強調升級（加 🚫 標記 / 移至頂部）
- 條目連續 30d 無相關糾正 → 移到文末 "低頻" 區，不刪
- 條目發現與既有 auto-memory feedback 重複 → 合併到 memory，lessons 留引用行

---

## 條目

> 待第一次 operator 糾正後填入。

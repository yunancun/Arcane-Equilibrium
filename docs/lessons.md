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

## 2026-04-24 · CLAUDE.md §三 敘述 vs runtime drift

- **場景**：`CLAUDE.md §三「當前系統狀態摘要」` 中嵌入 runtime 數值（cell count / row count / fill rate / binary mtime / commit progress / fire 次數），寫入時即場驗證但後續無自動化更新；數天後 runtime 已演化，§三 仍引用舊數字導致 audit 結論建立在 stale 假設上。
- **錯誤模式**：典型表現 — `CLAUDE.md` 宣稱「162 cells」但 `settings/edge_estimates.json` 實測僅 **1 cell**（mtime 4 天停滯，2026-04-24 G1-01 audit 揭露）；該數字曾經正確但 `edge_estimator_scheduler` 後續死掉無人察覺，§三 變成「過去快照」假冒「現況」。同型 drift 早期亦發生於「main_legacy.py 1630 行未拆」（2026-04-23 audit 才更正為已拆 468 行）。Root cause = 寫入即定型 + 無 freshness gate + 無自動 invalidate。
- **預防規則**：
  1. **採集標記**：§三 任何「runtime 數值 + 狀態」描述必註明「採集時間」（YYYY-MM-DD HH:MM CEST）+ 對應 healthcheck id（`passive_wait_healthcheck.py` 中的 `[N] check_*`）或具體驗證 oneliner，缺一即 E2 打回。
  2. **7 日鮮度上限**：§三 任何「狀態 + 數字」描述滿 7 天未經自動化重驗，必須由 cron / healthcheck / 手動驗證更新到當前值，或從 §三 刪除（移到「已完成里程碑索引」表保留 1 行）。違反 = 下一輪維護週期必補。
  3. **Audit-first 原則**：CC 收到 §三 數字當輸入時，**禁止無條件採信** — 凡涉及決策（rebuild / TOML 改 / 部署 gate），先跑對應 healthcheck 或讀 source-of-truth 檔案實測，發現 drift 立即在 commit 同次更新 §三。
  4. **Healthcheck 反向綁定**：每條 §三「runtime 數值」必對應 `passive_wait_healthcheck.py` 一個 `check_*()` 能在 silent-dead 時 RAISE / Exit 1（與 §七「被動等待 TODO 必附 healthcheck」規則同型，但這條覆蓋的是「敘述」而非「TODO」）。
- **相關檔案 / 指令**：
  - `CLAUDE.md` §三「當前系統狀態摘要」+「進行中/阻塞」段
  - `helper_scripts/db/passive_wait_healthcheck.py`（既有 12 個 check_*）
  - V023 postmortem 衍生 §七 SQL migration guard 4 條（同源規範，敘述-vs-runtime drift 是更廣的同類）
  - Verify pattern：`python3 helper_scripts/db/passive_wait_healthcheck.py --all`
- **來源 commit / session**：2026-04-24 G6-04（10-Agent audit Wave 1 子任務）；觸發案例 = G1-01「edge_estimator_scheduler 4 天停滯，§三 宣稱 162 cells 實測 1 cell」+ 2026-04-23 「main_legacy.py 1630 行宣稱未拆實測 468 行已拆」

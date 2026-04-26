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

## 2026-04-26 · 並行派發中「commit B 應 invalidate commit A doc」的時序 hazard

- **場景**：PM 在同一 session 並行派發多個 sub-agent（5+），其中部分任務有**doc 依賴關係**（commit A 的 doc/comment 提及「直到 X 條件達成才移除」，commit B 完成 X 條件）。並行派發無時序保證，A 與 B 完成時序不可預測。
- **錯誤模式**：本 session 實例（2026-04-26 12:17 → 12:36）：
  - commit `92ea90b` G1-FUP-CALIBRATOR-WARNING (12:17) 加 calibrator banner「IPC bind only covers 6/7 dimensions」+ 自身宣告「Tracking ticket EDGE-P1b-FUP-STALE-PEAK-IPC closed → banner removable」
  - commit `c2ca032` EDGE-P1b-FUP-STALE-PEAK-IPC (12:36, 19min 後) 加 `exit_stale_peak_ms` 進 IPC，**closed 該 ticket**
  - PM 漏執行 banner 移除 → E2 batch review 揭發 → 補 fixup commit `f633a5a`
  - 結果：1 個多餘 commit + E2 review + fixup 周期，浪費 ~30min session time
- **預防規則**：PM 識別「commit B 應 invalidate commit A doc」依賴對時，派發前選 3 種編排模式之一：
  1. **模式 A（合併 commit）**：commit A 與 commit B 改用 batch sub-agent（同一 sub-agent 順序完成 A→B 或 PM 自己合併兩 commit），消除中間 stale 期窗
  2. **模式 B（補 patch）**：派 commit B 時 prompt 明示「完成後同次 patch 移除 commit A 的 stale doc」（需 commit B sub-agent 知道 commit A 內容）
  3. **模式 C（TODO 標記）**：commit A 的 stale-able doc 加 `TODO(commit-B-id): remove this when X closes` 標記 + 後續 ticket 提醒 PM 自動掃描
  - 默認選 C（最不依賴 sub-agent 間溝通），有明顯時序排序時選 A
- **相關檔案 / 指令**：
  - PM 派發 prompt 模板（`docs/CCAgentWorkSpace/PM/profile.md` 派工章節）
  - `helper_scripts/db/passive_wait_healthcheck.py` 規則「被動等待必附 healthcheck」（同型「PM 編排規則」）
- **來源 commit / session**：2026-04-26 PM Phase 1+2 sign-off (`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-26--phase1_2_signoff.md` §4)

## 2026-04-26 · Sub-agent 完成測試 ≠ 完成 commit

- **場景**：PM 派發 sub-agent 完成 quick fix / refactor，prompt 含 commit + push 指示。Sub-agent 完成代碼修改 + 跑通測試後，可能因「system reminder 禁寫 .md 報告」誤判延伸到「禁 commit」，或因 E1/E2/E4 強制鏈想法 push back 不直接 commit。
- **錯誤模式**：本 session 兩次發生：
  - **G9-01 TW** (`0cda2d9`): TW 完成字典修正 + 給 PM 一個 commit oneliner 但**沒自動 commit**（誤判 system reminder 禁寫 .md = 禁 commit）
  - **EDGE-P1b E1** (`c2ca032`): E1 完成 7 檔修改 + cargo 2162 / pytest 130 PASS 但**改動留 Mac/Linux staging dir**（push back PA prompt 與 system 規則衝突）
  - 兩次都需 PM 介入 cp / git add / commit，浪費 ~10min session time
- **預防規則**：PM 派發 prompt 必含**3 條明示**：
  1. **「直接 commit + push 為任務完成標準的一部分，不要留 staging dir」**
  2. **「不要把 commit oneliner 當作給 PM 的下一步指示，PM 已授權 sub-agent 直接執行 commit + push」**
  3. **「system reminder 對 .md 報告檔的限制不延伸到 commit/push 操作」**
  - 對於 TW（doc-only writer），補 prompt 最末段「TW 範圍含 commit + push docs，不需 PM 代 commit」
  - 對於 E1/E5（實作 sub-agent），補 prompt 最末段「PM 顯式授權 commit + push，CLAUDE.md §七 強制 commit 即 push 適用本任務」
- **相關檔案 / 指令**：grep `staging|don't commit|不直接 commit` in sub-agent prompts
- **來源 commit / session**：2026-04-26 PM Phase 1+2 sign-off §3

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

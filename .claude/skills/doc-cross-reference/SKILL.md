---
name: doc-cross-reference
description: 治理文件交叉引用一致性審計（DOC-XX / SM-XX / EX-XX / P0-XX 編號 + 索引 + 鏈接 / README ↔ TODO ↔ memory 漂移偵測）；R4 agent 純審查。
allowed-tools: Read, Grep, Glob
---

# Doc Cross-Reference（文件交叉引用審計）

> **優先序**：runtime RiskConfig TOML > Rust schema > `TODO.md` active
> state > `README.md` stable surfaces > `CLAUDE.md` operating rules >
> governance docs > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

> **S3 上層 drift 防線**：本 skill 引用上層文件為 extract；發現
> `README.md` / `TODO.md` / memory 邊界不一致時，優先保留邊界清晰性並通報 PM。

## 何時觸發

- R4 收到「文檔索引一致性」「DOC-XX 引用漂移」「memory / TODO / README 邊界衛生」
- 新治理文件加入 `srv/docs/governance_dev/`
- 舊 memory / TODO / README 片段歸檔到 `docs/archive/` 後驗索引正確
- TODO.md 編號與 audit 報告 mismatch 排查
- memory 條目引用的 file path 失效檢查

## 索引權威（SSOT 順序）

優先級 1（不可漂）：
1. `srv/docs/governance_dev/SPECIFICATION_REGISTER.md` — DOC-XX 全名單
2. `srv/TODO.md` — active blockers / runtime evidence / open work
3. `srv/README.md` — stable project entry / canonical GUI / source map
4. `srv/CLAUDE.md` + `srv/.codex/MEMORY.md` — operating memory only
5. `srv/docs/agents/context-loading.md` — context routing contract

優先級 2（衍生索引）：
6. `srv/docs/CLAUDE_CHANGELOG.md` — commit 摘要
7. `srv/docs/CLAUDE_REFERENCE.md` — 完整參考
8. `srv/docs/README.md` — 分類目錄
9. `srv/docs/governance_dev/DEPRECATED.md` — 已棄用 DOC 黑名單

優先級 3（按需）：
10. `srv/docs/lessons.md` — 錯誤模式庫
11. `srv/docs/audits/` 系列
12. `srv/docs/CCAgentWorkSpace/<agent>/memory.md` + `workspace/reports/`

## 編號體系

| 前綴 | 含義 | 來源權威 |
|---|---|---|
| DOC-XX | 治理規範 | SPECIFICATION_REGISTER.md |
| SM-XX | State Machine | DOC-XX 內部 |
| EX-XX | Exchange-side | DOC-XX 內部 |
| P0/P1/P2/P3/P4-XX | 風控層 / 任務優先 | TODO.md + `CLAUDE.md` Hard Boundaries |
| LG-X | Live Guard | TODO.md + hard-boundary docs |
| W-XX / Wave-X | Sprint / Wave | TODO.md + PM reports |
| G-X / G1-XX | 工作組（10-Agent audit 後 G1-G6） | TODO.md + PA FIX-PLAN |

## 審計工作流（5 步）

1. **載入 SSOT** — Read 優先級 1 文件全文 + 抽出全部編號（regex）
2. **掃所有引用點** — `rg -n '(DOC|SM|EX|P0|P1|P2|P3|P4|LG|W-|G[1-6])-?[0-9]+' docs CLAUDE.md .codex/MEMORY.md README.md TODO.md`
3. **建反向索引** — 每個編號的所有引用點（檔:行）
4. **三類漂移檢測**：
   - **A. 引用不存在的編號**（殭屍）：被 grep 命中但不在 SSOT
   - **B. SSOT 有但無人引用**（孤兒）：除非設計如此（如未啟用 LG-5）
   - **C. 狀態不一致**：TODO.md active state 與 runtime / reports / README source map 不一致
5. **產出報告** — `docs/CCAgentWorkSpace/R4/workspace/reports/YYYY-MM-DD--cross_ref_audit.md`

## 已知漂移模式（G6-04 規則衍生）

- **TODO runtime drift**：TODO 含「runtime 數值」（cell count / row count / fill rate / binary mtime）必註採集時間 + healthcheck id 或採集命令；滿 7 日未重驗即必更新、降級待驗，或移入 archive/report
- **memory 越界**：CLAUDE / Codex memory 出現 active queue、工作進度、runtime 數字，應搬到 TODO 或 README
- **README 越界**：README 鏡像動態狀態，應改為指向 TODO
- **DEPRECATED.md 漏更**：撤回 DOC-XX 時忘了加進 DEPRECATED.md → 後續引用視為 SSOT 嚴重誤導
- **memory 過期**：memory 提到的 file 已 rename / delete → CC 接手照引會誤判
- **CHANGELOG 缺項**：commit 改重要 governance / context routing 但忘加 changelog 條

## DOC「廢棄 → 新版」轉換 SOP（24.2 P1）

當治理 DOC 重編號 / 拆分 / 合併（例：`DOC-04 V1` → `DOC-04 V2` 或 `DOC-04 → DOC-04A + DOC-04B`），R4 audit 步驟：

1. **驗 SPECIFICATION_REGISTER.md 雙條**：舊版標 `Deprecated / superseded by <new>`，新版標 `Active`，**兩條都不能消失** — 過去引用點需追溯舊版內容
2. **驗 DEPRECATED.md 補新條**：列舊 ID + 撤回日期 + 替代 ID + 「禁引」標記
3. **掃所有引用**：`rg -n 'DOC-04(?!\\sV2)' docs CLAUDE.md .codex/MEMORY.md README.md TODO.md` 找未升級引用點，逐個改為新 ID
4. **memory 條目同步**：memory 引舊 DOC ID 的條目，**按 SOP 不直接刪**（保歷史線索），改加 `[已升級為 <new>]` 標記
5. **archive 不動**：`docs/archive/` 內歷史 snapshot 用舊 ID 是**正確的**（凍結時間點），不改
6. **產 R4 audit 報告**：列出所有 stale 引用點 + 修正狀態 + 殘留 known-orphan（如 archive）

**判斷新舊**：當 sub-agent 看到同名 DOC 不同版本，**信 SPECIFICATION_REGISTER.md `Active` 標記 + 最大 V### 號**；無法判斷時 push back operator，**不單方面選舊版引用**。

## OpenClaw 特定核心檔對齊

每次 R4 審必驗 6 對：
- `README.md` context map ⇄ `docs/agents/context-loading.md`
- `TODO.md` active blockers ⇄ latest PM/role reports
- `CLAUDE.md` hard boundaries ⇄ Rust / Python hard-boundary constants where applicable
- `README.md` Control Console tab table ⇄ static GUI tab files / nav config
- `docs/agents/todo-maintenance.md` ⇄ TODO entries that add passive waits / runtime evidence
- TODO.md `[x]` ⇄ CLAUDE_CHANGELOG.md commit 摘要
- memory `MEMORY.md` 條目 ⇄ `memory/*.md` 檔存在 + frontmatter `name` 一致

## 輸出格式

```markdown
# R4 文檔交叉引用審計 — <date>

基準：commit `<sha>` · 採集時間 `<ts>`

## 編號體系覆蓋
- DOC-XX：N 個有效 / M 已棄用 / K 引用漂移
- P0/P1：N 在 TODO 活躍 / M 已歸檔或 report-only
- ...

## 漂移清單

### A. 殭屍引用（編號不存在於 SSOT）
| 引用點 file:line | 編號 | 建議 |

### B. 孤兒編號（SSOT 有但無引用）
| 編號 | SSOT 位置 | 是否設計如此 |

### C. 狀態不一致
| 編號 | TODO 狀態 | Runtime / report 狀態 | CHANGELOG | 結論 |

## 必修
1. <file:line + 改法>

## 建議下輪
- ...
```

---
name: doc-cross-reference
description: 治理文件交叉引用一致性審計（DOC-XX / SM-XX / EX-XX / P0-XX 編號 + 索引 + 鏈接 / TODO ↔ memory ↔ CLAUDE.md 漂移偵測）；R4 agent 純審查。
allowed-tools: Read, Grep, Glob
---

# Doc Cross-Reference（文件交叉引用審計）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- R4 收到「文檔索引一致性」「DOC-XX 引用漂移」「歸檔後 §三 衛生」
- 新治理文件加入 `srv/docs/governance_dev/`
- §三（CLAUDE.md）歸檔到 `docs/archive/` 後驗索引正確
- TODO.md 編號與 audit 報告 mismatch 排查
- memory 條目引用的 file path 失效檢查

## 索引權威（SSOT 順序）

優先級 1（不可漂）：
1. `srv/docs/governance_dev/SPECIFICATION_REGISTER.md` — DOC-XX 全名單
2. `srv/CLAUDE.md` §三 已完成里程碑表 + §十 路線圖
3. `srv/TODO.md` — 活躍工作項
4. `srv/docs/CLAUDE_CHANGELOG.md` — commit 摘要

優先級 2（衍生索引）：
5. `srv/docs/CLAUDE_REFERENCE.md` — 完整參考
6. `srv/docs/README.md` — 分類目錄
7. `srv/docs/governance_dev/DEPRECATED.md` — 已棄用 DOC 黑名單
8. memory `MEMORY.md`（auto-memory 索引）+ `memory/<entry>.md`

優先級 3（按需）：
9. `srv/docs/lessons.md` — 錯誤模式庫
10. `srv/docs/audits/` 系列
11. `srv/docs/CCAgentWorkSpace/<agent>/memory.md` + `workspace/reports/`

## 編號體系

| 前綴 | 含義 | 來源權威 |
|---|---|---|
| DOC-XX | 治理規範 | SPECIFICATION_REGISTER.md |
| SM-XX | State Machine | DOC-XX 內部 |
| EX-XX | Exchange-side | DOC-XX 內部 |
| P0/P1/P2/P3/P4-XX | 風控層 / 任務優先 | TODO.md + CLAUDE.md §四 |
| LG-X | Live Guard | TODO.md + CLAUDE.md §十 |
| W-XX / Wave-X | Sprint / Wave | CLAUDE.md §三 + TODO.md |
| G-X / G1-XX | 工作組（10-Agent audit 後 G1-G6） | TODO.md + PA FIX-PLAN |

## 審計工作流（5 步）

1. **載入 SSOT** — Read 優先級 1 文件全文 + 抽出全部編號（regex）
2. **掃所有引用點** — `grep -rE '(DOC|SM|EX|P0|P1|P2|P3|P4|LG|W-|G[1-6])-?[0-9]+' srv/docs srv/CLAUDE.md srv/TODO.md`
3. **建反向索引** — 每個編號的所有引用點（檔:行）
4. **三類漂移檢測**：
   - **A. 引用不存在的編號**（殭屍）：被 grep 命中但不在 SSOT
   - **B. SSOT 有但無人引用**（孤兒）：除非設計如此（如未啟用 LG-5）
   - **C. 狀態不一致**：CLAUDE.md §三 寫「✅」但 TODO.md 仍 `[ ]`，或 changelog 缺對應 entry
5. **產出報告** — `docs/CCAgentWorkSpace/R4/workspace/reports/YYYY-MM-DD--cross_ref_audit.md`

## 已知漂移模式（CLAUDE.md §七 G6-04 規則衍生）

- **§三 runtime drift**：§三 含「runtime 數值」（cell count / row count / fill rate / binary mtime）必註採集時間 + 對應 healthcheck id；滿 7 日未重驗即必更新或刪
- **歸檔不同步**：歸檔到 `docs/archive/YYYY-MM-DD--claude_md_section3_*.md` 但「已完成里程碑索引」表沒加 1 行 → 違反 §七 衛生規則
- **DEPRECATED.md 漏更**：撤回 DOC-XX 時忘了加進 DEPRECATED.md → 後續引用視為 SSOT 嚴重誤導
- **memory 過期**：memory 提到的 file 已 rename / delete → CC 接手照引會誤判
- **CHANGELOG 缺項**：commit 改 §三 但忘加 changelog 條 → 違反 §七

## OpenClaw 特定核心檔對齊

每次 R4 審必驗 6 對：
- CLAUDE.md §三 「已完成里程碑索引」⇄ `docs/archive/YYYY-MM-DD--claude_md_section3_*.md` 存在
- CLAUDE.md §四 「硬邊界」⇄ Rust `claude_teacher/applier.rs:226` denylist 字串常量
- CLAUDE.md §五 「11-Tab」⇄ `static/js/` 目錄存在 + `index.html` tab 計數
- CLAUDE.md §九 「Singleton 表」⇄ 代碼中模組級全局
- TODO.md `[x]` ⇄ CLAUDE_CHANGELOG.md commit 摘要
- memory `MEMORY.md` 條目 ⇄ `memory/*.md` 檔存在 + frontmatter `name` 一致

## 輸出格式

```markdown
# R4 文檔交叉引用審計 — <date>

基準：commit `<sha>` · 採集時間 `<ts>`

## 編號體系覆蓋
- DOC-XX：N 個有效 / M 已棄用 / K 引用漂移
- P0/P1：N 在 TODO 活躍 / M 在 §三 已完成
- ...

## 漂移清單

### A. 殭屍引用（編號不存在於 SSOT）
| 引用點 file:line | 編號 | 建議 |

### B. 孤兒編號（SSOT 有但無引用）
| 編號 | SSOT 位置 | 是否設計如此 |

### C. 狀態不一致
| 編號 | TODO 狀態 | CLAUDE.md §三 狀態 | CHANGELOG | 結論 |

## 必修
1. <file:line + 改法>

## 建議下輪
- ...
```

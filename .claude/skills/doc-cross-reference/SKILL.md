---
name: doc-cross-reference
description: R4 agent 純審查：文檔索引一致性、DOC-XX 等編號引用漂移、README/TODO/memory 邊界衛生、歸檔後索引驗證、引用 path 失效排查時讀。
allowed-tools: Read, Grep, Glob
---

# Doc Cross-Reference（文件交叉引用審計）

> 權威序：runtime RiskConfig TOML > Rust schema > `srv/TODO.md` > 治理文件（`SPECIFICATION_REGISTER.md` 索引）> 本 skill。衝突按權威序執行並在報告標註，不停下等待。
> 即時狀態（策略名單/閾值/端點/baseline 等）以上述 SSOT 為準，本 skill 不寫死。

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
| AMD-YYYY-MM-DD-NN | 治理 / 架構決策修訂（amendment） | SPECIFICATION_REGISTER.md Amendments 節 + `docs/governance_dev/amendments/` |
| ADR-XXXX | 架構決策記錄（4 位數字） | `docs/adr/`（ADR-0001~0033 檔名即 ID）+ SPECIFICATION_REGISTER.md（ADR-0034+ 登錄） |
| P0/P1/P2/P3/P4-XX | 風控層 / 任務優先 | TODO.md + `CLAUDE.md` Hard Boundaries |
| LG-X | Live Guard | TODO.md + hard-boundary docs |
| W-XX / Wave-X | Sprint / Wave | TODO.md + PM reports |
| G-X / G1-XX | 工作組（10-Agent audit 後 G1-G6） | TODO.md + PA FIX-PLAN |

## 審計工作流（5 步）

1. **載入 SSOT** — Read 優先級 1 文件全文 + 抽出全部編號（regex）
2. **掃所有引用點** — 用 Grep 工具（pattern=`(DOC|SM|EX|AMD|ADR|P0|P1|P2|P3|P4|LG|W-|G[1-6])-?[0-9]+`，path=docs / CLAUDE.md / .codex/MEMORY.md / README.md / TODO.md）執行；有 Bash 環境可等價用 `rg -n`
3. **建反向索引** — 每個編號的所有引用點（檔:行）
4. **三類漂移檢測**：
   - **A. 引用不存在的編號**（殭屍）：被 grep 命中但不在 SSOT
   - **B. SSOT 有但無人引用**（孤兒）：除非設計如此（如未啟用 LG-5）
   - **C. 狀態不一致**：TODO.md active state 與 runtime / reports / README source map 不一致
5. **產出報告** — `docs/CCAgentWorkSpace/R4/workspace/reports/YYYY-MM-DD--cross_ref_audit.md`

## 已知漂移模式（G6-04 TODO drift 規則唯一正本：CC / R4 / QA / e2e 指向此處）

- **TODO runtime drift**：TODO 含「runtime 數值」（cell count / row count / fill rate / binary mtime）必註採集時間 + healthcheck id 或採集命令；滿 7 日未重驗即必更新、降級待驗，或移入 archive/report
- **memory 越界**：CLAUDE / Codex memory 出現 active queue、工作進度、runtime 數字，應搬到 TODO 或 README
- **README 越界**：README 鏡像動態狀態，應改為指向 TODO
- **DEPRECATED.md 漏更**：撤回 DOC-XX 時忘了加進 DEPRECATED.md → 後續引用視為 SSOT 嚴重誤導
- **memory 過期**：memory 提到的 file 已 rename / delete → CC 接手照引會誤判
- **CHANGELOG 缺項**：commit 改重要 governance / context routing 但忘加 changelog 條

## 配置漂移偵測（R4 巡檢執行細則）

- 抽查 `.claude/agents/` 與 `.claude/skills/` 內數字 / 名單型事實（端點數、check 數、文件數、agent 名單、閾值、baseline）。
- 對照 canonical 來源：SPECIFICATION_REGISTER.md / README / TODO / E4 BASELINE / 各 agent 最新報告。
- 漂移列 file:line + 建議修正入報告；修復派工由 PM 決定。
- prompt 檔內即時狀態應寫「以 <canonical 來源> 為準」而非寫死數字；寫死即列 finding。

## Memory 壓實規格（R4 巡檢 / PM 派工依據）

- 觸發：memory.md >300 行。壓實後結構：檔頭壓實規則 blockquote +「## 長期教訓」（蒸餾 ≤30 行）+「## 近期記錄」（最近完整條目 ~150 行）。
- 舊條目以 Bash 機械切分原文遷同目錄 memory-archive.md（append-only，帶遷入日期分隔行，勿刪改）；行數守恆可驗。
- E4 特例：含 `BASELINE` 的行永留主檔。各 agent 完成序列（檔尾追加）行為不變。

## DOC「廢棄 → 新版」轉換 SOP（24.2 P1）

當治理 DOC 重編號 / 拆分 / 合併（例：`DOC-04 V1` → `DOC-04 V2` 或 `DOC-04 → DOC-04A + DOC-04B`），R4 audit 步驟：

1. **驗 SPECIFICATION_REGISTER.md 雙條**：舊版標 `Deprecated / superseded by <new>`，新版標 `Active`，**兩條都不能消失** — 過去引用點需追溯舊版內容
2. **驗 DEPRECATED.md 補新條**：列舊 ID + 撤回日期 + 替代 ID + 「禁引」標記
3. **掃所有引用**：找未升級引用點 — 用 Grep 工具掃 `DOC-04` 引用點後人工濾掉新版；有 Bash 環境可等價用 `rg -nP 'DOC-04(?!\sV2)' docs CLAUDE.md .codex/MEMORY.md README.md TODO.md`，逐個改為新 ID
4. **memory 條目同步**：memory 引舊 DOC ID 的條目，**按 SOP 不直接刪**（保歷史線索），改加 `[已升級為 <new>]` 標記
5. **archive 不動**：`docs/archive/` 內歷史 snapshot 用舊 ID 是**正確的**（凍結時間點），不改
6. **產 R4 audit 報告**：列出所有 stale 引用點 + 修正狀態 + 殘留 known-orphan（如 archive）

**判斷新舊**：當 sub-agent 看到同名 DOC 不同版本，**信 SPECIFICATION_REGISTER.md `Active` 標記 + 最大 V### 號**；無法判斷時在報告標註分歧並按 register Active 條目執行，**不單方面選舊版引用**。

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

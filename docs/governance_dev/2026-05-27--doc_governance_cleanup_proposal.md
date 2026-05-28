# 玄衡 文件治理 + 清理規範 proposal (2026-05-27)

> **狀態**：DRAFT — PM 提案，待 operator 批准；TW 拿到批准後機械化執行
> **作者**：PM
> **基線**：2248 markdown + 22 docx（srv/docs/）；CCAgentWorkSpace 占 67%
> **目標**：把「靜態雜亂」收斂到「可導航 + 可索引 + 不重複」，**不丟失任何治理證據與 sign-off 軌跡**
> **非目標**：不重寫歷史內容；不破壞 ADR / DOC / SM / EX SSOT；不動 ~/.claude/projects/.../memory/

---

## 0. 前置驗證（現狀對 operator 描述的偏差）

operator 給的描述基本正確，但有兩條需修正記入紀錄：

| 項目 | operator 描述 | 實際 | 差異意義 |
|---|---|---|---|
| 既有 inventory snapshot 時點 | （未明示）| `_indexes/document_inventory.json` snapshot=2026-05-06，當時 docs_markdown=1052 | 21 天內新增 ~1196 .md（Sprint 1A-α/β/γ/δ/ε/ζ + Sprint 1B + Sprint 4+ + Sprint 5+ + N+1 wave；屬正常 sprint 密集期）|
| `_indexes/path_redirects.md` 狀態 | （未明示）| 2026-05-06 已草擬 11-bucket 目標 taxonomy（`00-active/` … `90-archive/`），但 **0 移動已執行** | 本 proposal 不重發明，**直接採納 R4 既有藍圖**並補充重複偵測 + 紅線 |
| 跨平台路徑硬編碼 | — | `path_redirects.md` 已 freeze `docs/governance_dev/*`、`CCAgentWorkSpace/*/workspace/reports/*` | 本 proposal 對應 freeze 集合 **嚴守不動**，治理動作只在 freeze 集外 |
| 重複檔名 hotspot | 「大量重複」 | `v58_executability_audit.md` 14 份、`v57_executability_audit.md` 14 份、`2026-04-24--todo_complete_proposal.md` 9 份、`FA_GAP_AUDIT_REPORT_2026-03-30.md` 8 份、README.md 29 / profile.md 18 / memory.md 18 | 多角色獨立 audit = 設計上正確（不是重複）；README/profile/memory = 系統檔（必保留）；真正可合併的是 **單事件 daily summary ↔ 專題 worklog** 與 **被取代 v1↔v2** 類 |

**結論**：operator 的「大量重複」直覺**部分成立**（跨日同事件 + 過期 v1 + worklogs 與 agent workspace 重述），但 v58/v57 14 份這類 **看似重複實為多視角證據鏈** —— 不可合併。下面 Section A 即把判據細化到 TW 可機械執行。

---

## Section A — 重複偵測準則（Decision Tree）

> **總原則**：**多視角獨立 audit 不是重複**（治理證據鏈）；只有「同事件 + 同視角 + 同結論」才合併；不確定一律保留 + 標 `superseded_by`。

### A.1 四類重複的處理矩陣

| 類型 | 判據（機械可查）| 處理 | 邊界 |
|---|---|---|---|
| **跨 Agent 同事件多視角** | 同主題 token（如 `v58_executability_audit` / `wave5_dispatch`）出現在 ≥2 個 `CCAgentWorkSpace/<agent>/workspace/reports/` 下 | **全部保留**（每份 = 該 agent 不可替代的審計視角）；只在 `srv/docs/README.md` 索引段補單一彙整指針（如 PM 的 final verdict）| **不合併、不歸檔**。違反 = 毀治理證據鏈 |
| **Daily summary ↔ 專題 worklog** | 同日（YYYY-MM-DD 一致）且 `worklogs/<date>--daily_summary.md` 與 `worklogs/<date>--<topic>.md` 共存 | daily_summary **保留**（時間軸索引價值）；專題 worklog **保留**（細節）；只在 daily_summary 末段補「相關專題 worklog 列表」如未有 | 不合併。日後新寫 daily_summary 模板強制列當日 worklog index |
| **CCAgentWorkSpace/`<agent>`/ ↔ worklogs/ 同事件重述** | 同主題 token 同時出現在 `CCAgentWorkSpace/<agent>/workspace/reports/` 與 `worklogs/` 下 | Agent workspace 為**權威**（agent 親手簽 sign-off）；worklogs/ 為**敘事**；TW **不合併**，但可在 worklogs/ 對應檔頂部加 `> 對應 agent report: <path>` cross-ref | 不刪 worklogs/ 對應檔（worklogs 是時間軸入口，搜尋習慣強） |
| **被取代但未歸檔（v1 → v2）** | 同 topic stem 出現 `_v1` / `_v2` / `_draft` / `_round2` / `_round3` 後綴，且後綴新版已 land（`grep -l 'supersedes\|取代'` 命中後者）| 舊版 `git mv` 至 `archive/<YYYY-MM-DD>--<topic>_superseded/` 並在原位留 redirect stub（`_indexes/path_redirects.md` 已有 stub 模板）| 必須先確認**無活引用**（`grep -r '<oldpath>' srv/docs/ srv/CLAUDE.md srv/TODO.md srv/README.md`）；命中 = STOP 升 BLOCKER |

### A.2 內容相似度的可機械判據（TW 不跑語義比對）

TW 用以下 4 條 heuristic 順序評估；任一條命中 = **保留**（謹慎優先），全部 miss 才考慮合併/歸檔：

1. **檔名 stem 一致**：`basename --suffix=.md` 後字串相同 → 至少屬「同事件」候選
2. **日期前綴一致**：`YYYY-MM-DD--` 段相同 → 候選提升至「同日同事件」
3. **目錄不同 = 不同角色或不同分類** → 仍**不合併**（多視角規則）；除非兩者都在 `worklogs/` 或都在 `archive/` 才可考慮
4. **首 30 行 SHA256**：兩檔頭 30 行 hash 相同 → 候選提升至「實質重複」**但仍需第 5 條把關**
5. **版本後綴 + supersedes 關鍵字**：舊版 grep 命中 `supersed|取代|retire|deprecated` 在新版內 → 才可移 archive/

### A.3 紅線（看到任一即停手）

任何治理動作觸碰下列 = TW **立即停手 + 升 BLOCKER + 等 PM/operator sign-off**：

| 紅線類別 | 路徑 / 檔名模式 | 理由 |
|---|---|---|
| 治理 SSOT | `docs/decisions/DOC-*.md` / `docs/decisions/DOC-*.docx` / `docs/decisions/SM-*` / `docs/decisions/EX-*` / `docs/decisions/HIST-*` / `docs/decisions/DOC-NAV*` | 22 份治理憲法，**永不動**；operator 維護 .docx 源 |
| ADR | `docs/adr/0001-*.md` 至 `docs/adr/9999-*.md` | 編號永久；ADR 只能 `Active` ↔ `Superseded` 改 status，**從不刪檔** |
| Agent profile / memory | `docs/CCAgentWorkSpace/*/profile.md` / `docs/CCAgentWorkSpace/*/memory.md` | 18 個 agent 各 1 對 = 36 個系統檔，**永不動** |
| Workspace README / templates | `docs/CCAgentWorkSpace/*/workspace/README.md` / `docs/CCAgentWorkSpace/*/workspace/templates/*` | 系統檔 |
| Operator handoff | `docs/CCAgentWorkSpace/Operator/*` | Sign-off 副本 = operator 接收面，**永不合併** |
| CC / E3 / MIT / QC / FA / BB / A3 / R4 audit 報告 | 任何在 `CCAgentWorkSpace/{CC,E3,MIT,QC,FA,BB,A3,R4}/workspace/reports/*.md` | 治理證據鏈，多 sprint 後追溯 root cause 必查；**永不合併** |
| `_indexes/` | `docs/_indexes/*` | TW 自己用的 SSOT，**TW 不可改自己**，必須 PM 派發另一輪 |
| Governance amendments | `docs/governance_dev/amendments/AMD-*.md` | AMD 鏈不可斷 |
| README / KNOWN_ISSUES / CLAUDE_CHANGELOG / CLAUDE_REFERENCE / lessons.md | `docs/README.md` / `docs/KNOWN_ISSUES.md` / `docs/CLAUDE_*` / `docs/lessons.md` | 根入口檔 |
| 已被 `srv/CLAUDE.md` / `srv/TODO.md` / `srv/README.md` 引用 | `grep -r '<file>' srv/CLAUDE.md srv/TODO.md srv/README.md` 命中 | 動 = 破活路由 |

---

## Section B — 命名標準補強

### B.1 現有 1913/2248 已遵守 `YYYY-MM-DD--desc.md`，剩 299 個（13.3%）的處理

| 子類 | 識別 grep | 處理 |
|---|---|---|
| 系統檔（README / profile / memory / lessons / KNOWN_ISSUES / CLAUDE_CHANGELOG / SCRIPT_INDEX） | basename 命中固定字串集 | **保留原名**；本 proposal 正式登記為「非日期化系統檔」例外 |
| 治理 SSOT（DOC-*/SM-*/EX-*/HIST-*） | basename 命中 `^(DOC|SM|EX|HIST)-` | **保留原名**；本身即帶版本（V1/V2）與編號，比日期更強 |
| ADR（0001-* … 9999-*）| basename 命中 `^[0-9]{4}-` | **保留原名**；ADR 編號權威 |
| Amendments（AMD-YYYY-MM-DD-NN-*）| basename 命中 `^AMD-` | **保留原名**；AMD 編號與日期已雙含 |
| 治理開發 phase 子目錄內檔（governance_dev/phase*/*）| 路徑 prefix 命中 | **保留原名**（多為早期 Round 1/2 命名 + 後期日期化共存）；不重命名以免斷既有引用 |
| 早期遺留中文檔名（`工程一审修改建议报告_终稿.md` 等）| 路徑 = `decisions/` 內 .md/.txt | **保留原名**（歷史文件，~5 個）；補 front-matter `naming_legacy: true` |
| **剩餘真正不規範**（預估 < 50 個）| 上述都不中 | TW 列清單給 PM 一條條決議，**不擅自重命名** |

### B.2 同日多事件序號正式化

現已自然出現 `2026-04-18-1--...` / `2026-04-18-2--...` 共 ~6 處。正式規則：

- 同日同 agent 同類型 ≥2 份 → 加 `-N` suffix（N=1,2,3...）
- **不**用 `HHmm` 時分（README §文件命名規範第 2 條雖列出，實際用得少且 git mtime 已含時分，避免冗餘）
- TW **不回填**歷史檔（成本高 + 破活引用）；只在新檔強制執行
- 修補 README.md §文件命名規範：補一行「同日多事件用 `-N` 序號優先於 `HHmm`」

### B.3 Agent workspace 內部命名與 worklogs/ 統一前綴

- Agent workspace report 已自然遵守 `YYYY-MM-DD--<topic>.md`，**不需強制統一前綴**
- 不引入跨 agent 命名 namespace（如 `PM--2026-05-27--...`）—— 因為已用目錄 namespace（`CCAgentWorkSpace/PM/`）達同效，加 prefix = 冗餘 + 破已建立的引用

---

## Section C — 目錄結構正規化

### C.1 採納 `_indexes/path_redirects.md` 既有 11-bucket taxonomy

R4 在 2026-05-06 已草擬：

```
docs/
├── 00-active/             ← 活躍狀態 / backlog / 計劃指針
├── 01-architecture/       ← 架構 overlay / ADR / 系統邊界
├── 02-execution-plans/    ← REF / MAG / Sprint / Wave / Phase 計劃
├── 03-governance/         ← 治理規範 / amendments / 註冊表 / 政策
├── 04-audits/             ← 審計與 verdict
├── 05-agent-workspace/    ← 角色 profile / memory / reports / operator copy
├── 06-runbooks/           ← Deploy / 災難 / first-day-live / healthcheck SOP
├── 07-reference/          ← 穩定技術背景與外部 reference
├── 08-worklogs/           ← 時間軸工程日誌
├── 90-archive/            ← 過期 extracts / snapshot / 被取代計劃
└── _indexes/              ← 機器可讀 inventory / redirect map / GUI metadata
```

**本 proposal 立場**：採納此目標 taxonomy，**但分批執行**，禁一次性大遷移：

1. **Phase 1（先建索引，零遷移）**：TW 重生 `_indexes/document_inventory.json`（schema 升至 v2，含 sha256 first-30-line / supersedes 關係 / orphan flag），不動任何檔
2. **Phase 2（先做最安全的歸檔）**：A.1 第 4 類「被取代 v1→v2」批次 `git mv` 至 `archive/<date>--<topic>_superseded/`，每批 ≤30 檔
3. **Phase 3（暫不做大遷移）**：00-09 + 90 bucket 重組需更新 GUI metadata + agent boot rule + ADR + redirect stub —— 屬 R4 + PA 多輪審查任務，**本次清理不啟動**

### C.2 CCAgentWorkSpace/`<agent>`/ 內部子目錄

**不強制**子目錄細分。理由：

- 現結構 `<agent>/profile.md + memory.md + workspace/{reports/,templates/}` 已足，每 agent 平均 reports 數量（PA 205 / E1 299 / PM 259）尚可掃描
- 強加 `audits/ briefs/ memory/` 三層會：（a）破現有 ~1500 個檔路徑（b）破 agent boot rule 第 1 條「Read profile.md → memory.md → workspace/reports/ 最新」（c）增 sub-agent 派發複雜度
- 真正擁擠的是 E1（299）/ PM（259）/ PA（205）；達 **500 個** 才考慮按月分子目錄（`reports/YYYY-MM/`）

**輕度規範補充**：

- `<agent>/workspace/reports/` 內 `>500` 才分月；目前 0 個 agent 達標
- `<agent>/workspace/runs/` （E1 已有 `runs/2026-05-16/`）= 巨量產物隔離，**保留**
- `<agent>/workspace/drafts/` （MIT 已有 `drafts/ops4_gap_b_d/`）= 半成品隔離，**保留**

### C.3 worklogs/ 是否按月/季再分子目錄

worklogs/ 根目錄 30 個 + 6 個 phase 子目錄 = 共 83 .md。**不分**。理由：

- 30 個 .md 在根目錄屬可掃描範圍
- 既有子目錄（`chapters_a-g/` / `phase5_arch_rc1/` …）= **歷史 phase 完結後的歸檔**，不是時間切片；新 worklog 直接放根目錄是正確做法
- 若日後 worklogs/ 根目錄 >100 → 開 `worklogs/2026-05/` 月分檔，**但不回填歷史**

### C.4 archive/ 接收條件

統一規則：

- 接收：（a）A.1 第 4 類被取代 v1（b）已 sign-off 且 30 天無讀寫的 phase summary（c）operator 明示 archive 的檔
- 子目錄命名：`archive/<YYYY-MM-DD>--<event_or_topic>/`（已有 `2026-05-21--sprint_1a_delta_dup_artifacts/` / `2026-05-21--srv_root_cleanup/` 範例）
- 不接收：ADR / DOC / SM / EX / AMD / agent profile / memory / 任何當前 sprint 內被引用的檔
- 每個 archive 子目錄根放一個 `_README.md` 寫：歸檔日 / 來源路徑 / 原因 / supersedes 指針

### C.5 _indexes/ 索引重建策略

- **機器生成優先**：TW 寫一支 `helper_scripts/maintenance_scripts/regen_doc_inventory.py`（若未有）每次清理批次後跑一次
- **手寫補註**：`document_inventory.json` schema 加 `human_notes: {<path>: <one-line>}` 段，記重要 cross-ref（不重新發明 README index）
- **不複製 README.md §文件索引內容到 inventory.json** —— 兩者分工：README index = 人類入口，inventory.json = 機器掃描

---

## Section D — TW 可機械執行的 12 條清單

> **執行環境**：Mac（SSOT），git worktree 內執行（見 Section E.3）；Linux 端不執行 doc 治理動作（runtime 無 doc 變更需求）

### D.1 步驟順序（必照序）

| # | 步驟 | 前置條件 | 中止條件 | Audit trail |
|---|---|---|---|---|
| 1 | **fetch + dry-run inventory** — `git fetch origin && git status --porcelain` 必須乾淨；運行 `regen_doc_inventory.py --dry-run` 產 candidate 清單 | Mac 上；branch = `doc-cleanup/2026-05-27`；不在 main | porcelain 不乾淨 = STOP | 輸出 `_indexes/doc_cleanup_run_<TS>.json` candidate 清單 |
| 2 | **PM review candidate** — TW 把 candidate 清單回傳給 PM（不執行任何 mv） | step 1 PASS | candidate >200 = STOP 等 PM 拆批 | PM sign-off 寫入 `CCAgentWorkSpace/PM/workspace/reports/2026-05-27--doc_cleanup_phase1_signoff.md` |
| 3 | **批 1：archive 被取代 v1**（A.1 第 4 類）—— 每批 ≤30 檔 `git mv` 到 `archive/<date>--<topic>_superseded/` + 原位 redirect stub | step 2 PM APPROVE | 命中 Section A.3 紅線 = STOP；某檔 `grep -r` 命中活引用 = STOP 該檔 | 每批 1 commit；commit msg 含 candidate list 與 STOP 列表 |
| 4 | **批 2：archive Phase 5 / ARCH-RC1 / Phase 4 / Phase 3 完結 packet**（C.4 條件 b）| step 3 完成 + PM APPROVE 該批 | 任何活 sprint 引用 = STOP | 1 commit；commit msg 引 ADR 號或 sprint closure 報告 |
| 5 | **批 3：daily_summary cross-ref 補充**（A.1 第 2 類，只加 cross-ref 不合併）—— 在 daily_summary 末段加當日相關 worklog 列表 | step 4 完成 | grep 自動偵測同日 worklog ≤5 個才動，>5 = STOP 等 PM | 1 commit；diff 不超過 +N 行 / 0 刪行 |
| 6 | **批 4：CCAgentWorkSpace ↔ worklogs cross-ref**（A.1 第 3 類）—— 同主題 token 同日重述，在 worklogs/ 對應檔頂加 `> 對應 agent report: <path>` | step 5 完成 | grep 同主題 token 同日對應 ≤30 對才動 | 1 commit；diff +N 行 / 0 刪行 |
| 7 | **批 5：補非標命名清單**（B.1 剩 <50 個）—— TW **不重命名**，產 `_indexes/non_standard_naming_review.md` 給 PM 一條條判 | step 6 完成 | — | 1 commit；純 add file |
| 8 | **批 6：README.md §文件命名規範補丁**（B.2 同日 `-N` suffix）—— Edit README.md `srv/docs/README.md` §文件命名規範段，加 1 行 | step 7 完成 + PM APPROVE 文字 | README 已被其他 session 改 = `git commit --only` | 1 commit；只動 README 1 檔 |
| 9 | **批 7：重生 inventory.json v2** —— 跑 `regen_doc_inventory.py --schema v2`；schema 加 `sha256_first30 / supersedes / orphan / human_notes` | step 8 完成 | 重生輸出與 git ls-files 偏差 >5% = STOP 排查 | 1 commit；只動 `_indexes/document_inventory.json` |
| 10 | **批 8：path_redirects.md amend** —— 把本次實際移動入 `path_redirects.md` 「已執行」段（既有「Candidate Redirects」表分割成「Candidate」+「Executed」）| step 9 完成 | — | 1 commit；只動 path_redirects.md |
| 11 | **regression** —— `grep -r 'archive/.*_superseded'` 跨 `srv/CLAUDE.md srv/TODO.md srv/README.md docs/agents/*` 確認 0 命中（活引用未斷）；`node --check` if GUI 動到（本批應 0 GUI 動）| step 10 完成 | grep 命中 = STOP 補 stub | 寫 `CCAgentWorkSpace/TW/workspace/reports/2026-05-27--doc_cleanup_regression.md` |
| 12 | **PM sign-off + push** —— TW 產 final report `CCAgentWorkSpace/TW/workspace/reports/2026-05-27--doc_cleanup_final.md`；PM Read → APPROVE → `git push origin doc-cleanup/2026-05-27` → PR | step 11 PASS | regression FAIL = 不 push | 1 final commit + push |

### D.2 衝突處理（兩文件互為同主題）

機械順序：

1. 兩檔都在 freeze 集 → **都不動**（紅線優先）
2. 一檔在 freeze 集 一檔不在 → freeze 那檔勝出，另一檔**保留**（仍不合併）
3. 都不在 freeze 集 → 比 `git log -1 --format=%ct <file>` 最近 ctime；新者勝出；舊者 grep 命中 `supersed|取代|retire|deprecated` 在新者內 → 舊者 archive；未命中 → **都保留**
4. 都不在 freeze + 都沒 supersedes 標記 + 首 30 行 hash 相同 → STOP 升 BLOCKER 給 PM

### D.3 Audit trail 標準

每批執行寫一條 mv-log 進 `_indexes/doc_cleanup_run_<TS>.json`，schema：

```json
{
  "batch_id": 3,
  "executed_at": "2026-05-27T14:00:00+08:00",
  "branch": "doc-cleanup/2026-05-27",
  "commit": "<sha>",
  "moves": [
    {"from": "<path>", "to": "<path>", "reason": "superseded_by", "evidence": "<grep match>"}
  ],
  "stops": [
    {"file": "<path>", "reason": "active_reference_in_TODO.md"}
  ]
}
```

---

## Section E — 風險與回滾

### E.1 預期風險

| 風險 | 概率 | 影響 | 緩解 |
|---|---|---|---|
| 活引用未察覺被斷（CLAUDE.md/TODO.md/agent skill/sub-agent prompt grep miss） | 中 | 高（agent boot 失敗 / wave dispatch 找不到 spec）| Section D step 11 強制 grep；redirect stub 留至少 1 個 sprint cycle |
| 多 session race（隔壁 CC session 改了同檔）| 中 | 中 | `git commit --only <file>` 對 meta-doc；本批限 archive `git mv` 為主，避免改檔內容 |
| TW 誤刪治理證據（v58 14 agent 報告誤判為重複）| 低（紅線清楚）| 極高 | Section A.3 紅線；CCAgentWorkSpace/*/workspace/reports/ 全列 freeze |
| ADR / DOC 編號被破壞 | 極低 | 災難級 | 紅線；decisions/ 與 adr/ 整目錄 freeze |
| README.md 索引段被本次清理破壞（既有 1461 行 README 含巨量 index）| 中 | 中 | 本次不重組 README index；只補 §文件命名規範 1 行（D.1 step 8）；README index 重組屬 R4 另派任務 |
| inventory.json 重生與實際 git ls-files 偏差 | 低 | 低（重生即修）| step 9 ±5% 偏差容忍；超則 STOP 排查 |

### E.2 回滾機制

- **每批 1 commit** = `git revert <sha>` 即回滾整批（archive `git mv` 可逆，因 git 追蹤 rename）
- **不用 `git rm`** —— 全程 `git mv` 至 `archive/`；極端情況可 `git mv` 回原位
- **redirect stub** 留至少 1 個 sprint cycle —— 不立即清，避免重派 wave 找不到舊路徑
- **`_indexes/doc_cleanup_run_<TS>.json` 永久保留** —— 即使檔重移，audit trail 在

### E.3 是否在 git worktree 內執行（operator 問題）

**強烈建議是**。理由：

1. 主 branch 此刻有 Sprint 1B / Sprint 5+ Wave 1 / Sprint 4+ carry-over 持續活動（HEAD 周圍 commit 密集）
2. 本次治理動作 ≥ 8 個 commit（D.1 step 3-10 各 1）—— 直接灌入主 branch 會稀釋 sprint commit 軸
3. memory `feedback_subagent_first` + multi-session race —— worktree 隔離隔壁 session 不被誤推 doc-cleanup commit
4. R4 / PA 後續可能要對 archive/ 結果做第二輪 review —— worktree branch 留著等 PR 即可

**操作**：

```bash
# 在 srv/ 內
git worktree add ../srv-doc-cleanup doc-cleanup/2026-05-27
cd ../srv-doc-cleanup
# TW 執行 D.1 step 1-12
# 完成後 PR：doc-cleanup/2026-05-27 → main
# Merge 後刪 worktree
cd ../srv
git worktree remove ../srv-doc-cleanup
```

**例外**：D.1 step 8 README.md amend = 動主 SSOT，可考慮**單獨**一個 commit 直接到 main（用 `git commit --only`），不走 worktree —— 避免主 branch 與 worktree 上 README.md 漂移。PM 拍板。

---

## TW 執行 SOP（10 步以內 condensed）

1. `git fetch && git status --porcelain` 乾淨 → `git worktree add ../srv-doc-cleanup doc-cleanup/2026-05-27` → cd 進去
2. 跑 `regen_doc_inventory.py --dry-run` 產 candidate 清單 → 寫入 `_indexes/doc_cleanup_run_<TS>.json` → 回傳 PM
3. PM APPROVE 後，**批 1 archive 被取代 v1**：每批 ≤30 檔 `git mv` 至 `archive/<date>--<topic>_superseded/` + 原位留 stub → 1 commit
4. **批 2 archive Phase 3-5 完結 packet** → 1 commit
5. **批 3-4 cross-ref 補充**（daily_summary + worklogs↔agent reports）→ 各 1 commit
6. **批 5 列非標命名給 PM 判** → add file commit
7. **批 6 README.md §文件命名規範 +1 行**（同日 `-N` suffix）→ `git commit --only`
8. **批 7 重生 inventory.json v2** → 1 commit
9. **批 8 amend path_redirects.md Executed 段** → 1 commit
10. Regression（grep 紅線 + node --check）→ 寫 final report → PM APPROVE → `git push -u origin doc-cleanup/2026-05-27` → 開 PR

---

## PM Sign-off Checklist（PM 對 TW 完成輸出的驗收門檻）

- [ ] **A 規則零違反**：A.3 紅線 0 觸碰（grep `decisions/DOC` / `decisions/SM` / `decisions/EX` / `adr/00` / `CCAgentWorkSpace/*/profile.md` / `memory.md` / `_indexes/` 在 mv-log 出現 = REJECT）
- [ ] **活引用 0 斷**：跨 `srv/CLAUDE.md` / `srv/TODO.md` / `srv/README.md` / `docs/agents/*` / `docs/CCAgentWorkSpace/*/profile.md` grep 所有被移檔的舊路徑 = 0 命中（或全有對應 redirect stub）
- [ ] **每批 1 commit**：`git log doc-cleanup/2026-05-27 ^main --oneline | wc -l` 介於 7-10
- [ ] **mv-log 完整**：`_indexes/doc_cleanup_run_<TS>.json` 含每個 mv 的 from/to/reason/evidence；stops 段非空 = TW 至少 STOP 過 1 次（合理）；stops 0 = 可疑（疑似未嚴格執行紅線）
- [ ] **README §文件命名規範**：補 1 行「同日多事件用 `-N` 序號優先於 `HHmm`」
- [ ] **path_redirects.md**：「Candidate Redirects」表已分割出「Executed」子段並登記本次所有 mv
- [ ] **inventory.json v2**：schema 升至 v2 含 `sha256_first30 / supersedes / orphan / human_notes`；`counts.docs_markdown` 與 git ls-files 偏差 ≤5%
- [ ] **回滾驗證**：抽 1 個 commit `git revert --no-commit <sha>` 預演 → 確認檔回原位無衝突 → `git revert --abort`
- [ ] **memory trail**：`docs/CCAgentWorkSpace/PM/memory.md` 追加 1 條本次清理 lesson（不刪舊條）

PM SIGN-OFF: APPROVED / CONDITIONAL（待 N 條件）/ BLOCKED（具體 finding）

---

## 附錄 — 與既有 SSOT 的關係

| 既有檔 | 本 proposal 動作 |
|---|---|
| `docs/README.md` §強制規則 5 條 | **不動**；本 proposal 在規則 4「不允許重複文件」下補 Section A 細化判據（不入 README，留在本 proposal）|
| `docs/README.md` §文件命名規範 | 補 1 行同日 `-N` suffix（D.1 step 8）|
| `docs/_indexes/path_redirects.md` | 採納 11-bucket taxonomy 為長期目標；本次只執行最安全的 archive 子集 |
| `docs/_indexes/document_inventory.json` | schema v1 → v2 重生（D.1 step 9）|
| `docs/CCAgentWorkSpace/*/memory.md` | **不動**（紅線）|
| `docs/governance_dev/SPECIFICATION_REGISTER.md` | **不動**（治理 SSOT）|
| ADR / DOC / SM / EX / AMD | **不動**（紅線）|

---

## Amendment 2026-05-28 — Phase 1 校正（PM Sign-off 後）

基於 TW phase 1 實測結果（candidate report `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-28--doc_cleanup_phase1_candidates.md`）與 PM 2026-05-28 sign-off（`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-28--doc_cleanup_phase1_signoff.md`）：

### A.1 Class 2 規則收窄

原規則「同日 daily_summary ↔ 專題 worklog cross-ref」實測 **0 對命中**（worklogs/ 根目錄 daily_summary 與專題日期天然互斥；書寫風格 04-16 後切為「只寫專題」）。

新規則：Class 2 **本輪 Phase 1 not triggered**；未來收窄為「**新寫 daily_summary 末段強制列當日 git commits**」這類自我索引化動作，不回填歷史。

### A.1 Class 3 規則收窄

原規則「CCAgentWorkSpace ↔ worklogs 同日同 topic cross-ref」實測 **1 對命中**（30 worklog 樣本；`live_auth_watcher_event_consumer_spawn` 04-27）。

新規則：Class 3 改為**機會主義補強**（碰到才補，不批量掃描）；本輪該 1 對 cross-ref **inline 進 batch 1 commit**，不獨立成批。

### A.1 Class 4 lineage 引用處理（**c 雙保險**）

8 個 archive 候選的 docs/ 內部 lineage 引用採**雙保險**：
1. 原位 redirect stub（`archive/<date>--<topic>_superseded/_README.md`）
2. `_indexes/path_redirects.md` 「Executed」段集中登記
3. `docs/README.md` / `docs/execution_plan/README.md` 索引條目改寫為 archive 路徑（保留索引行供搜尋）
4. `docs/CLAUDE_CHANGELOG.md` **不動**（歷史 changelog 是時間軸證據，不重寫）
5. `docs/execution_plan/2026-05-02--ref20_v1_round2_audit.md` / `ref20_v2_round3_audit.md` 文末加一行 `> NOTE: <oldpath> 已於 2026-05-28 歸檔至 archive/...`；不動審計內文
6. `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` 第 9 行「取代 V2.1 Round3」**不動**（新版 supersedes 段是事實陳述）

### C.4 接收條件補強

C.4 「不接收」清單追加：「**被 `docs/README.md` 主索引段（如 L862-1009）逐檔列表的 phase packet**」屬永久 KEEP；如需 archive 該類目錄，先派 R4 評估 README 索引重組（不在本 proposal 範圍）。

實例：`worklogs/phase5_arch_rc1/` / `control_api_gui/` / `chapters_a-g/` / `chapters_h-i/` / `chapters_j-k/` / `learning/` 6 個目錄被 README L29-34 + L862-1009 主索引活引用 → 本輪 phase 1 **不 archive**。

### D.0 角色職能矩陣（新增 — TW sub-agent 環境限制）

| 角色 | 工具集 | 允許動作 | 禁止動作 |
|---|---|---|---|
| TW (sub-agent) | Read / Edit / Write / Grep / Glob | 產 candidate inventory / 紅線 grep / 寫 candidate report / Edit markdown 內容（cross-ref / amendment / stub） | `git` 任何子命令 / `python3` script / `git mv` |
| main session（PM 或 E1 + Bash） | + Bash | `git fetch/status/add/commit/mv/push` / `python3 regen_doc_inventory.py` / `node --check` | — |

TW 階段只產 candidate metadata；step 3-12 的 git/Python 動作派 main session 或 E1 代執行；TW 在 candidate report 列「需 Bash」清單，main session 接手後逐條 batch。

### D.3 mv-log 雙版並存策略

TW 手算 JSON（`doc_cleanup_run_<TS>T0000.json`，~250 行 verdict summary）+ E1 機器版（`doc_cleanup_run_<TS>T0030.json`，~20000 行 raw entries）**兩版並存**，互為 audit；不在 step 9 刪手算版。

### 預期最終操作數校正

PM 原預估 150-200 → **校正為 15-30**（不含 phase packet；phase packet 全 DEFER）：
- Class 1 KEEP_ALL: 0 mv（紅線 freeze）
- Class 2: 0（Phase 1 not triggered）
- Class 3: 1 cross-ref（inline batch 1）
- Class 4: 8 git mv + 8 原位 stub + path_redirects.md amend + README/execution_plan README 索引條目路徑改寫（~16 處） + 2 個 audit 報告文末 NOTE（2 處）
- Phase packet: 0（全 DEFER）

合計 ~30 個 add/mv/edit 動作，分 5-7 commits。

**END of Amendment**

---

**END of proposal**

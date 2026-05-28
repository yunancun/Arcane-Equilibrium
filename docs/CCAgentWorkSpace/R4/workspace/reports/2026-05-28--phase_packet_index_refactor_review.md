# R4 Phase Packet Index Refactor Review — 2026-05-28

> **任務**：評估是否折疊 `docs/README.md` L862-1009（148 行）+ L29-34 樹狀圖 6 個 phase packet 索引段，以便 phase 2 git mv 89 檔到 archive。
> **基準**：branch `doc-cleanup/2026-05-28` @ HEAD `57024d43`（worktree CWD `/Users/ncyu/Projects/TradeBot/srv-doc-cleanup`）
> **採集時間**：2026-05-28 R4 audit pass
> **作者**：R4（Document Auditor）

---

## Q1. README L862-1009 結構盤點（行號精確覆驗）

`grep -n '^### '` 自驗結果（行號為實際 srv-doc-cleanup HEAD）：

| 行號段 | 段標題 | 索引粒度 | 實際檔數 | prompt 估算 |
|---|---|---|---|---|
| **L868-882**（15 行）| `### worklogs/chapters_a-g/ — A-G 章节工作日志（2026-03-11 ~ 2026-03-19）` | 11 條目 1:1 列檔（`.txt`） | 11 .txt | 11 ✓ |
| **L884-901**（18 行）| `### worklogs/chapters_h-i/ — H-I 章节工作日志（2026-03-20 ~ 2026-03-22）` | 14 條目 1:1 列檔 | **13 .txt**（**少 1**） | 14 ✗（README ghost 1 行：實檔 13 但 README 列 14）|
| **L903-914**（12 行）| `### worklogs/chapters_j-k/ — J-K 章节 + GitHub 迁移（2026-03-22 ~ 2026-03-24）` | 8 條目 | 6 .txt + 2 .md = 8 | 8 ✓ |
| **L916-968**（53 行）| `### worklogs/control_api_gui/ — Control API + GUI 开发日志（2026-03-25 ~ 2026-04-02）` | 50 條目 1:1 列檔（純 `.md`）+ 5 個 `.txt` 未在此段列（在頂段隱含） | 45 .md + 5 .txt = 50 | 50 ✓（prompt 55 估算偏高）|
| **L970-993**（24 行）| `### worklogs/phase5_arch_rc1/ — Phase 5 / L3 整改 / ARCH-RC1 開發日誌（2026-04-03 ~ 2026-04-07）` | **20 條目 1:1 列檔** | 5 .md（**ghost 15 條**！）| 5 ✓ 但 README 內列 20 行檔名──**ghost link 警告，phase 5 段已 04-14 audit 壓縮但 README 未同步**（與 R4 memory 2026-04-24 第 2 點正向印證）|
| **L995-1009**（15 行）| `### worklogs/ — 頂層工作日志（2026-04-08+...）` | 9 條（**不屬 phase packet** — 是現役 worklogs/ 根目錄 daily_summary） | 28 .md（top-level） | **非 phase packet！不要折疊** |
| **L1011-1015**（5 行）| `### worklogs/learning/ — L 章学习系统开发日志（2026-03-26）` | 1 條目 | 1 .md | 1 ✓ |

**重要更正**：prompt 標「L1005-1009 = learning」**錯誤**；實 learning 段在 **L1011-1015**，L995-1009 是 worklogs/ 根目錄段（**頂層 daily_summary 04-08+**，**不屬 phase packet 範圍，必須保留**）。

**L29-34 樹狀圖**：6 行 `chapters_a-g / chapters_h-i / chapters_j-k / control_api_gui / phase5_arch_rc1 / learning`（與下方明細段一一對應）

**Phase packet 索引總行數**：
- L29-34 樹狀圖 6 行
- L868-882（chapters_a-g）+ L884-901（chapters_h-i）+ L903-914（chapters_j-k）+ L916-968（control_api_gui）+ L970-993（phase5_arch_rc1）+ L1011-1015（learning）= 15+18+12+53+24+5 = **127 行詳細索引**
- 合計 **133 行**（不是 prompt 標的 148；prompt 把 L995-1009 頂層段誤算為 phase packet）

---

## Q2. 索引價值評估（1-5 評分）

| dir | 索引價值 | 跨檔引用密度 | ADR / 設計被超越 | 評分 |
|---|---|---|---|---|
| **chapters_a-g** | 純 H0 蓝图時代 .txt 工作日誌；2026-03-11~19 設計討論已被 DOC-04 v2 / ADR-0001~0005 / 後續 phase 1-5 完全超越 | 0 命中於活引用區（CLAUDE/TODO/srv-README） | **完全被超越**（A-G 章是基础层設計討論，已成 ADR/governance docs） | **1/5** |
| **chapters_h-i** | H0 本地判断核心 + AI 治理討論；H0 SLA 已落入 DOC-02 `<1ms` + SM-04；H1 no-call semantics patch 已成正式 SM | 0 命中活引用區 | **完全被超越**（H-I 核心已成 SM-04 / DOC-04 內容） | **1/5** |
| **chapters_j-k** | Transition Engine + Paper Gate + GitHub 遷移；GitHub 工作流早已 active，Transition Engine 已被 ADR 取代 | 0 命中活引用區；2 個 `.md` 同名重複（與 audit/non_test_manifest.tsv 對） | **完全被超越** | **1/5** |
| **control_api_gui** | Phase 1/2/3 完整工程日誌；含 phase1_final_audited / wave4/wave7/wave8 等里程碑；**1 個內檔自引**（layer2_ai_engine_design_session.md L115-116 引同目錄 brainstorm）；`docs/CLAUDE_REFERENCE.md` L83-88 引 6 檔為「歷史快查」；TW `T0.1_FA_DIRECTORY_ARCHITECTURE.md` L216 也指向此目錄 | **中等引用密度**（CLAUDE_REFERENCE.md 6 處 + 內部 1 處 + governance_dev/phase0_takeover 1 處 + 1 references/2026-03-27 1 處） | **大部分被超越但仍有 6 份「歷史快查」reference 引用** | **3/5** |
| **phase5_arch_rc1** | ARCH-RC1 1A/1B/1C 設計實現日誌；ADR-0009 引「ARCH-RC1」為 architecture pattern；CLAUDE_REFERENCE.md L94-98 引 5 daily_summary + L3 整改 session；**ghost link 15 條**（README 列 20 但實檔 5） | **中等引用密度**（CLAUDE_REFERENCE.md 5 處） | **ARCH-RC1 已落入 ADR-0009 + docs/architecture/**，但 daily_summary 仍是「事實時間軸」reference | **2/5** |
| **learning** | L 章學習管線；單檔總綱；已被 ADR / docs/architecture/ 取代 | 0 命中活引用區 | **完全被超越** | **1/5** |

**綜合判斷**：6 dir 中 4 dir（chapters_a-g / h-i / j-k / learning）= 純歷史雜訊，索引價值 1/5；2 dir（control_api_gui / phase5_arch_rc1）= 有 CLAUDE_REFERENCE.md 「歷史快查」價值，但本身已被 ADR 取代，價值 2-3/5。

---

## Q3. 折疊方案 — 我的 6 條回答

### 折疊方案決議

**採用 prompt 提的「~8 行表格 + archive `_README.md` 詳細索引」基本架構**，但對細節做 4 點調整（見下方 Q3.1-Q3.6）。

### Q3.1 三選項擇一

選 **「8 行折疊表 + archive `_README.md` 詳細索引」**。理由：
- 148 行（實 133 行）逐檔索引價值 1-3/5；折疊到 8 行可釋 125 行 README，**索引信噪比提升 16×**
- archive `_README.md` 內含原 L862-1009 對應段落的「逐檔解釋」，**搜尋價值 100% 保留**（grep `2026-03-27--session3_remaining_audit_fixes` 仍能在 archive `_README.md` 命中）
- 中間量（30 行 summary）= 兩邊不討好；折疊不徹底+detail 損失部分

### Q3.2 archive 子目錄命名

選 **`2026-05-28--worklog_<topic>_archived/`**（保留 `worklog_` 前綴 + `_archived` 後綴）。理由：
- 與 phase 1 命名規範一致：phase 1 用 `2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/`（topic_<kind>）
- 但 phase 2 不是 supersedes（沒新版取代）而是「歷史 phase 完結歸檔」；用 `_superseded` 後綴語意錯誤
- 6 個目錄名：
  - `archive/2026-05-28--worklog_chapters_a-g_archived/`
  - `archive/2026-05-28--worklog_chapters_h-i_archived/`
  - `archive/2026-05-28--worklog_chapters_j-k_archived/`
  - `archive/2026-05-28--worklog_control_api_gui_archived/`
  - `archive/2026-05-28--worklog_phase5_arch_rc1_archived/`
  - `archive/2026-05-28--worklog_learning_archived/`

### Q3.3 cross-link 維護單向 entry point

**雙向 link**，不只單向。理由：
- README 折疊段 → archive `_README.md`（順向導航：找歷史 phase 時讀 README → 點連結 → 看 archive 內 detail）
- archive `_README.md` → 原 README 段（逆向 trail：archive 內讀某檔時想知「為何被 archive、何時何人 decide」→ 連回 README 折疊表 + path_redirects.md Executed 段）
- 雙向 link 與 phase 1 的 `_README.md` stub 模板一致（phase 1 stub 也雙向：指 v3 + 解釋 supersede 來由）

### Q3.4 L29-34 樹狀圖

**同步刪除 6 行**（chapters_a-g/h-i/j-k/control_api_gui/phase5_arch_rc1/learning）改寫為 1 行 `(已歸檔的 phase packet 見下方 "Phase Packet Archive Index" 段)`。理由：
- 樹狀圖與 L868-1015 必須一致；不一致 = R4 memory 2026-04-24 第 2 點記載的「索引分化」反模式
- 改 1 行而不是徹底拆除：保留「曾經有 phase packet」的歷史線索給未來 agent

### Q3.5 worklogs/_archived_phases.md 過渡入口

**不建議建立**。理由：
- worklogs/ 根目錄已有大量現役 daily_summary（28 檔），多加 `_archived_phases.md` 會混淆「現役 vs 歸檔」邊界
- archive 子目錄 + path_redirects.md Executed 段已是雙保險；多增第三條入口反而稀釋 single source of truth
- 若 operator 認為需要過渡期導航，建議改在「README 折疊段內」加 1 行 `> Pre-2026-04-08 phase work moved to archive/; new worklogs go to worklogs/ root.`

### Q3.6 README 折疊後總行數預估

修正 prompt 估算：
- 原 phase packet 索引總行：L29-34 樹狀圖 6 行 + L868-1015 詳細段 **127 行**（不含 L995-1009 頂層段 15 行，後者保留）= **133 行**
- 新折疊段：8 行表格 + 4 行表頭/說明 + 2 行 cross-link block = ~14 行
- L29-34 樹狀改寫：刪 6 行 + 加 1 行 = -5 行
- **總減少**：133 - 14 - 5 = **114 行**（建議 prompt 算式校正為 `1461 - 114 = 1347` 行）
- 「可接受」── 是；README 從 1461→1347（**-7.8%**），可讀性增益 16× 索引信噪比

---

## Q4. 風險評估

| 風險 | 程度 | 緩解 |
|---|---|---|
| **A. grep 失效**（agent 用「session3_remaining_audit_fixes」字串 grep README 找不到） | LOW | archive `_README.md` 內 100% 列原檔名；grep 仍命中（差別只是檔路徑變 `archive/.../worklog_control_api_gui_archived/_README.md`） |
| **B. 既有 cross-link 斷裂** | MEDIUM | grep 出 4 個非 self-trivial 引用點需配修：(1) `docs/CLAUDE_REFERENCE.md` L83-98 列 11 個 phase packet 內檔 → 改路徑指向 `archive/...worklog_<topic>_archived/`；(2) `docs/references/2026-04-02--system_status_report.md` L216 1 處；(3) `docs/references/2026-03-27--system_reference_handbook.md` L106 1 處；(4) `docs/governance_dev/phase0_takeover/T0.1_FA_DIRECTORY_ARCHITECTURE.md` L158-161 1 處 + L26650+ 大量 .tsv manifest（auto-generated 不動）；(5) `docs/governance_dev/changelogs/2026-03-29_T2.23_orig_file_cleanup.md` L115-116（**內部 self-ref**，待 phase 2 mv 一起改）；(6) `docs/audits/2026-04-12--full_program_chain_audit.md` 多處引用（**歷史 audit 不改**，加 `> NOTE: 該段引用的 worklog 已於 2026-05-28 歸檔至 archive/...` 即可，與 phase 1 SOP 一致） |
| **C. PA/FA review 必要性** | **R4 判斷：屬 R4 + PA 範疇，不需 FA**。理由：純文檔索引重組，不影響 trading/risk/architecture 設計；FA 不擔此責；PA 需 review 是因為 git mv 89 檔 batch 切分屬 PA 設計範疇 |
| **D. git mv 衝突檢測** | LOW | phase 1 已驗證 worktree porcelain 乾淨方法可複用 |
| **E. R4 memory ghost link 已知問題**（phase5_arch_rc1 README 列 20 但實 5）| **DETECTED**：本次 audit 確認 phase5_arch_rc1 段 L970-993 列 20 條目但實檔僅 5 個 daily_summary——15 條是 04-14 audit 壓縮後遺留的 ghost link（R4 memory 2026-04-24 已記載）。**Phase 2 折疊正是治理此 ghost link 的最佳時機** |
| **F. tsv manifest 自動同步** | LOW | `docs/audit/non_test_manifest.tsv` 和 `inventory_manifest.tsv` 是 generated；下次 `regen_doc_inventory.py` 自動更新 |

---

## Q5. 建議的 Phase 2 命令鏈（有序 step list）

| Step | 動作 | 執行者 | 工時 |
|---|---|---|---|
| 1 | R4 本 review report land 至 `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-28--phase_packet_index_refactor_review.md` | **main session**（R4 sub-agent 無 Write／不直接 land；返回此 review 文字後由 main session 寫檔） | 已完成（本次） |
| 2 | PA 設計 git mv batch 切分：**89 檔分 6 批**（每 dir 1 批，1-50 檔/批），含 worktree porcelain pre-check + 衝突檢測 + commit msg template | 派 **PA**（不是 main session 自跑）；理由：89 檔比 phase 1 的 9 檔多 10×，需正式 batch plan | ~20 分 |
| 3 | TW 寫 6 個 archive `_README.md` 詳細索引（每個含原 L868-1015 對應段落 + 雙向 link + 「Pre-2026-04-08 phase work」說明） + README 折疊段 14 行 + L29-34 樹狀圖改寫 | 派 **TW**（純 markdown Edit） | ~30 分 |
| 4 | main session 跑 6 批 git mv（每 dir 1 commit；commit msg 含 `[skip ci]`） | **main session 親自跑**（沿用 phase 1 SOP，不派 E1） | ~25 分 |
| 5 | main session 跑 `_indexes/path_redirects.md` Executed 段補 6 entry（每 dir 1 entry） | 派 **TW**（純 markdown Edit） | ~10 分 |
| 6 | main session 跑 `regen_doc_inventory.py --dry-run --ts-label 2026-05-28T0130`（post-cleanup 重生 + commit） | **main session 跑 Bash + Python** | ~5 分 |
| 7 | regression grep 跨 5 區（CLAUDE.md / TODO.md / docs/agents/* / srv-README.md / docs/README.md 折疊段）確認 89 檔 stem 全 0 命中（或全有 archive 路徑替換） | **main session 跑 Bash** | ~5 分 |
| 8 | 同步補修：`docs/CLAUDE_REFERENCE.md` L83-98 11 entry 路徑改寫；2 references/ 檔內各 1 處改寫；1 governance_dev/changelogs/ 內部 self-ref 改寫（若 control_api_gui 已 mv）；2026-04-12 audit 加 footer NOTE | 派 **TW** | ~15 分 |
| 9 | TW phase 2 final report `2026-05-28--doc_cleanup_phase2_final.md` | 派 **TW** | ~20 分 |
| 10 | PM phase 2 final sign-off | **main session（PM）** | ~10 分 |
| 11 | main session push + amend PR #2（合併 phase 1+2 為單 PR）| **main session** | ~5 分 |
| 12 | main session merge PR + 三端同步（Mac worktree + Linux trade-core + main） | **main session** | ~10 分 |

**全程預計** ~155 分鐘（vs phase 1 ~85 分；phase 2 工作量 ~2×）

---

## Q6. 不可妥協的紅線（phase 2 絕對不動）

逐條 R4 紅線（基於本 worktree HEAD 實掃）：

1. **`docs/adr/`**（ADR 0001-0042+）——永不動
2. **`docs/decisions/DOC-*` / `SM-*` / `EX-*` / `HIST-*`**（治理源 .docx）——永不動
3. **`docs/governance_dev/amendments/AMD-*`**——永不動
4. **`docs/CCAgentWorkSpace/` freeze set**（14 個 v58 / 14 個 v57 / 9 個 todo_complete_proposal / Operator/）——永不動
5. **`docs/CLAUDE_CHANGELOG.md`**——永不動（歷史時間軸；只能加新項，不重寫舊項；phase 1 already established SOP）
6. **`docs/worklogs/` 根目錄 28 個現役 daily_summary 04-08+**（L995-1009 段）——**永不歸檔**；這是 phase 2 範圍誤判最大風險
7. **`docs/audit/non_test_manifest.tsv` + `inventory_manifest.tsv`**——auto-generated，不手動 edit；下次 regen 自動更新
8. **README.md L1-861（phase packet 之前）+ L1010-1461（之後）**——只動 phase packet 索引段，不重組其他
9. **CLAUDE.md / TODO.md / srv-README.md（根級）**——本 R4 grep 確認 0 phase packet 引用，本來就不會動到，但列入紅線以防誤觸
10. **2026-04-12 `full_program_chain_audit.md` 內 phase packet 引用**——歷史 audit 證據不改內文；只在文末加 `> NOTE: 引用的 worklog 已於 2026-05-28 歸檔至 archive/...` footer

**phase 2 紅線 grep 驗證**（R4 已跑）：
- `CLAUDE.md` / `TODO.md` / `README.md`（srv 根）對 6 phase packet topic 名 = **0 命中** ✓
- `docs/agents/*.md` 對 6 topic 名 = **0 命中** ✓（已驗）
- 89 檔 stem 名（如 `2026-03-27--session3_remaining_audit_fixes`）在 srv 內活引用區的 grep = **需 main session 在 step 7 重驗**（R4 sub-agent 因檔多未逐一掃）

---

## R4 Verdict

**APPROVE phase 2 phase packet 折疊**。

理由綜合：
1. **prompt 的 8 行折疊方案基本正確**；但 6 條細節需校正（見 Q3.1-Q3.6）
2. **148 行修正為 133 行**（prompt 把 L995-1009 頂層段誤算為 phase packet）；折疊後 -114 行，README 從 1461→1347（-7.8%）
3. **archive 命名建議 `2026-05-28--worklog_<topic>_archived/`**（不用 `_superseded`，後者語意錯誤）
4. **6 條紅線檢出**：phase 1 已遵守；phase 2 須額外注意 L995-1009 頂層段（這次 prompt 誤判過 1 次，要 PA 寫 batch plan 時格外清楚邊界）
5. **ghost link 治理時機**：phase5_arch_rc1 段 L970-993 列 20 條目但實檔僅 5 個——15 條 ghost link 是 R4 memory 2026-04-24 已記載的歷史問題；**phase 2 折疊是治理此 ghost link 的最佳時機**
6. **operator 補證據 D5 closure 證據需求**：**不必須**；R4 判斷 README 索引段 = 軟 closure 證據 + ADR-0009 引 ARCH-RC1 = 硬 closure 證據（至少 phase5_arch_rc1）；其餘 5 dir 屬 03 月早期 phase，ADR 制度尚未成熟，「未來不再寫類似 worklog」本身就是 closure 信號（過去 30+ 天 0 讀寫已證）

---

## 對 PA 的設計輸入（5 條）

1. **89 檔分 6 批，每 dir 1 commit**：不要按檔數平均切；按 dir 自然邊界切，commit msg 「Archive worklog_<topic> phase packet (N files)」清晰可逆
2. **批序按 dir 規模從小到大**：learning (1) → phase5_arch_rc1 (5) → chapters_j-k (8) → chapters_a-g (11) → chapters_h-i (13) → control_api_gui (50)；先小後大利於早期發現問題
3. **每批 `git mv` 後立即 commit**，**禁累積 commit**：phase 1 SOP 已驗證；phase 2 commit 數 6 個 mv + 1 個 README 折疊 + 1 個 CLAUDE_REFERENCE 修補 + 1 個 path_redirects + 1 個 inventory regen = ~10 commit
4. **phase5_arch_rc1 段 ghost link 治理**：archive `_README.md` 內列「README 曾列 20 條目但實檔 5（15 條是 04-14 audit 壓縮後 ghost）」作為 lineage NOTE
5. **chapters_h-i ghost link**：README 列 14 條目但實 13；archive `_README.md` 內列 13 真實檔 + 1 條 lineage NOTE 「README 內 ghost 1 行」

---

**END of R4 Review**

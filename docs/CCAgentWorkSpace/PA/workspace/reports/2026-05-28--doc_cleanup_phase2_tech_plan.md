# PA Doc Cleanup Phase 2 — Technical Plan

> **任務**：設計 phase 2 完整技術方案：89 檔 git mv + README L862-1015 折疊 + L29-34 樹狀圖改寫 + 6 個 archive `_README.md` lineage stub + 補修 4 處活引用 + path_redirects.md Executed phase 2 段 + ~10 commit batch 切分
> **基準**：worktree `/Users/ncyu/Projects/TradeBot/srv-doc-cleanup` @ HEAD `57024d43`（branch `doc-cleanup/2026-05-28`，phase 1 已 land + PR #2 opened）
> **R4 review 對照**：`docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-28--phase_packet_index_refactor_review.md` APPROVE + 5 條設計輸入 + 6 條紅線
> **PM proposal 對照**：`docs/governance_dev/2026-05-27--doc_governance_cleanup_proposal.md` D5（DEFER → 本 phase 解除）
> **作者**：PA
> **採集時間**：2026-05-28

---

## §1. Executive Summary

### 範圍

| 項目 | 數量 |
|---|---|
| `git mv` 檔總數 | **89 檔**（learning 1 + phase5_arch_rc1 5 + chapters_j-k 8 + chapters_a-g 11 + chapters_h-i 13 + control_api_gui 50）所有檔 + 1 `_README.md` stub × 6 dir |
| README 折疊 | L862-1015 phase packet 索引段 6 sub-section（127 行）→ 14 行表格摘要 + L29-34 樹狀圖 6 行 → 1 行（**淨減 ~118 行**；R4 計 -114，PA 重算 -118 含 ghost link 治理留白） |
| 補修活引用點 | 4 處 — (1) `docs/CLAUDE_REFERENCE.md` L83-98（11 個 phase packet 路徑）；(2) `docs/references/2026-03-27--system_reference_handbook.md` L216 區段；(3) `docs/governance_dev/changelogs/2026-03-29_T2.23_orig_file_cleanup.md` L106 self-ref；(4) `docs/worklogs/control_api_gui/2026-03-27--layer2_ai_engine_design_session.md` L115-116 內部 self-ref（被 mv 後檔本身在 archive，仍須改字串） |
| 不改的活引用 | (a) `docs/audits/2026-04-12--full_program_chain_audit.md` 多處（歷史 audit；文末加 footer NOTE 即可）；(b) `docs/references/2026-04-02--system_status_report.md` L26650+ ~50 entries（auto-generated manifest；`regen_doc_inventory.py` 下次自動更新） |
| Archive 新目錄 | 6 個 — `archive/2026-05-28--worklog_<topic>_archived/` × 6（**已 ls 驗 0 collision**） |
| path_redirects.md Executed phase 2 段 | 1 個新 table 段（6 row）+ ghost link 治理 NOTE |
| **總 commit 數** | **11**（P2-0 plan land + P2-1~P2-6 六批 mv + P2-7 README 折疊 + P2-8 補修 + P2-9 path_redirects + JSON regen + P2-10 final report；含本 plan land 於 P2-0） |
| **預期工時** | **~155 分鐘**（與 R4 Q5 估算一致；含 main session + 派 TW + 派 R4 regression review） |

### 關鍵設計決議

1. **6 個 batch 依 R4 input #1+#2**：每 dir 1 commit；批序 learning(1) → phase5_arch_rc1(5) → chapters_j-k(8) → chapters_a-g(11) → chapters_h-i(13) → control_api_gui(50)；先小後大早期發現問題
2. **archive 命名沿 phase 1 schema**：`archive/2026-05-28--worklog_<topic>_archived/`（**`_archived` 後綴**；R4 Q3.2 指出不用 `_superseded`，後者語意錯誤）
3. **雙向 link**：README 折疊段 → archive `_README.md`（順向）+ archive `_README.md` → README 折疊段 + path_redirects.md Executed phase 2 段（逆向）
4. **L29-34 樹狀圖同步改**：刪 6 行 + 加 1 行 = -5 行；與 phase packet 詳細段一致避免 R4 memory 2026-04-24 第 2 點「索引分化」反模式
5. **ghost link 治理**：phase5_arch_rc1（README 列 20 / 實 5）+ chapters_h-i（README 列 14 / 實 13）；archive `_README.md` 內列實檔 + lineage NOTE
6. **2026-04-12 audit footer NOTE**：歷史 audit 不改內文，只在文末加 `> NOTE: 引用的 worklog 已於 2026-05-28 歸檔至 archive/...`（沿 phase 1 SOP）
7. **MV 命令模式**：`git mv docs/worklogs/<dir>/* docs/archive/2026-05-28--worklog_<topic>_archived/`（**shell glob 一次 mv 整 dir**；含 .txt + .md；確保 commit msg `[skip ci]`）

---

## §2. 89 檔逐 dir 清單 + git mv 命令

### Batch 2-A: learning (1 file)

**Pre-condition**：worktree porcelain clean；P2-0 plan land 完成
**Archive dir**：`docs/archive/2026-05-28--worklog_learning_archived/`

```bash
cd /Users/ncyu/Projects/TradeBot/srv-doc-cleanup
mkdir -p docs/archive/2026-05-28--worklog_learning_archived
git mv docs/worklogs/learning/2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md \
  docs/archive/2026-05-28--worklog_learning_archived/
# write _README.md (TW step 3 內容，main session step 4 git mv 完成後 git add)
# commit:
git commit -m "$(cat <<'EOF'
docs(cleanup): batch 2A — archive worklog_learning (1 file) [skip ci]

Move worklogs/learning/ to archive/2026-05-28--worklog_learning_archived/
per phase 2 plan. README L1011-1015 detailed section folded into 8-row
phase packet summary table in P2-7.

- 1 mv: 2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md
- 1 stub: _README.md (lineage to README §"Phase Packet Archive Index" + path_redirects.md)

Refs: PA tech plan (2026-05-28--doc_cleanup_phase2_tech_plan.md §2 Batch 2-A)
EOF
)"
```

### Batch 2-B: phase5_arch_rc1 (5 files)

**Archive dir**：`docs/archive/2026-05-28--worklog_phase5_arch_rc1_archived/`
**Ghost link**：README L970-993 列 20 條目，實檔 5（差 15）；archive `_README.md` 內列實 5 + lineage NOTE

```bash
mkdir -p docs/archive/2026-05-28--worklog_phase5_arch_rc1_archived
git mv docs/worklogs/phase5_arch_rc1/2026-04-03--daily_summary.md \
       docs/worklogs/phase5_arch_rc1/2026-04-04--daily_summary.md \
       docs/worklogs/phase5_arch_rc1/2026-04-05--daily_summary.md \
       docs/worklogs/phase5_arch_rc1/2026-04-06--daily_summary.md \
       docs/worklogs/phase5_arch_rc1/2026-04-07--daily_summary.md \
  docs/archive/2026-05-28--worklog_phase5_arch_rc1_archived/
# commit msg含 ghost lineage note，見 §8 P2-2
```

### Batch 2-C: chapters_j-k (8 files; 6 .txt + 2 .md)

**Archive dir**：`docs/archive/2026-05-28--worklog_chapters_j-k_archived/`

```bash
mkdir -p docs/archive/2026-05-28--worklog_chapters_j-k_archived
git mv docs/worklogs/chapters_j-k/2026-03-22--夜间_github迁移与诊断报告.txt \
       docs/worklogs/chapters_j-k/2026-03-22--夜间_新对话接手prompt_github版.txt \
       docs/worklogs/chapters_j-k/2026-03-22--夜间_最终整合总报告.txt \
       docs/worklogs/chapters_j-k/2026-03-22--项目总报告_含github核对.md \
       docs/worklogs/chapters_j-k/2026-03-24--work_report_current_dialogue.md \
       docs/worklogs/chapters_j-k/2026-03-24--交接日志.txt \
       docs/worklogs/chapters_j-k/2026-03-24--工程总报告_结构迁移完成.txt \
       docs/worklogs/chapters_j-k/2026-03-24--新对话启动prompt.txt \
  docs/archive/2026-05-28--worklog_chapters_j-k_archived/
```

### Batch 2-D: chapters_a-g (11 files; 全 .txt)

**Archive dir**：`docs/archive/2026-05-28--worklog_chapters_a-g_archived/`

```bash
mkdir -p docs/archive/2026-05-28--worklog_chapters_a-g_archived
git mv docs/worklogs/chapters_a-g/2026-03-11--openclaw_bybit_进度日志.txt \
       docs/worklogs/chapters_a-g/2026-03-12--openclaw_bybit_进度日志.txt \
       docs/worklogs/chapters_a-g/2026-03-13--三日补充综合日志.txt \
       docs/worklogs/chapters_a-g/2026-03-13--详细工作日志.txt \
       docs/worklogs/chapters_a-g/2026-03-17--chapter_g_工程记录.txt \
       docs/worklogs/chapters_a-g/2026-03-17--chapter_g_执行清单.txt \
       docs/worklogs/chapters_a-g/2026-03-17--engineering_log.txt \
       docs/worklogs/chapters_a-g/2026-03-19--完整版当前进度图.txt \
       docs/worklogs/chapters_a-g/2026-03-19--工作记录_含0317至0319校正与修复.txt \
       docs/worklogs/chapters_a-g/2026-03-19--当前进度图_校正后.txt \
       docs/worklogs/chapters_a-g/2026-03-19--补充记录1.txt \
  docs/archive/2026-05-28--worklog_chapters_a-g_archived/
```

### Batch 2-E: chapters_h-i (13 files; 全 .txt)

**Archive dir**：`docs/archive/2026-05-28--worklog_chapters_h-i_archived/`
**Ghost link**：README L884-901 列 14 條目（含 L896 `全量整合总报告.txt` 不存在），實檔 13；archive `_README.md` 內列實 13 + lineage NOTE

```bash
mkdir -p docs/archive/2026-05-28--worklog_chapters_h-i_archived
git mv docs/worklogs/chapters_h-i/2026-03-20--h0_本地判断核心蓝图_v1.txt \
       docs/worklogs/chapters_h-i/2026-03-20--h_i_本地执行内核讨论备份.txt \
       docs/worklogs/chapters_h-i/2026-03-20--openclaw_工作记录.txt \
       docs/worklogs/chapters_h-i/2026-03-20--超详细续接总报告.txt \
       docs/worklogs/chapters_h-i/2026-03-22--0320工作报告_新对话接手版.txt \
       docs/worklogs/chapters_h-i/2026-03-22--a-i_接手摘要.txt \
       docs/worklogs/chapters_h-i/2026-03-22--h_i_兼容性对账清单.txt \
       docs/worklogs/chapters_h-i/2026-03-22--h_i_正式完工对账报告.txt \
       docs/worklogs/chapters_h-i/2026-03-22--全量整合总报告_重新导出.txt \
       docs/worklogs/chapters_h-i/2026-03-22--晚_h1_no_call_semantics_patch.txt \
       docs/worklogs/chapters_h-i/2026-03-22--晚_工程记录.txt \
       docs/worklogs/chapters_h-i/2026-03-22--晚_新对话接手prompt.txt \
       docs/worklogs/chapters_h-i/2026-03-22--晚_新对话接手指示.txt \
  docs/archive/2026-05-28--worklog_chapters_h-i_archived/
```

### Batch 2-F: control_api_gui (50 files; 45 .md + 5 .txt)

**Archive dir**：`docs/archive/2026-05-28--worklog_control_api_gui_archived/`
**最大 batch；50 檔一次 mv；shell glob 安全（dir 內 100% 都要 mv，無 keep file）**

```bash
mkdir -p docs/archive/2026-05-28--worklog_control_api_gui_archived
# 50 檔一次 mv 用 glob：
git mv docs/worklogs/control_api_gui/* docs/archive/2026-05-28--worklog_control_api_gui_archived/
# 驗證：
ls docs/worklogs/control_api_gui/ 2>/dev/null | wc -l  # 應為 0
ls docs/archive/2026-05-28--worklog_control_api_gui_archived/ | wc -l  # 應為 50（不含後加的 _README.md）
```

**注意**：用 `git mv <dir>/*` glob 形式比 50 個檔名列舉更穩；shell 展開 → git 接收 50 個 mv operation；commit 內 `git status` 顯示 50 `renamed` entry。

### Batch 2 合計

| Batch | dir | 檔數 | 副檔名分佈 | mv 後 dir 狀態 |
|---|---|---|---|---|
| 2-A | learning | 1 | 1 .md | 空 |
| 2-B | phase5_arch_rc1 | 5 | 5 .md | 空 |
| 2-C | chapters_j-k | 8 | 6 .txt + 2 .md | 空 |
| 2-D | chapters_a-g | 11 | 11 .txt | 空 |
| 2-E | chapters_h-i | 13 | 13 .txt | 空 |
| 2-F | control_api_gui | 50 | 45 .md + 5 .txt | 空 |
| **TOTAL** | **6 dir** | **88** ✗ | — | — |

**校正**：實際總 89 檔（PA 重數：1+5+8+11+13+50 = 88？）`ls` 結果重核：
- learning 1 + phase5_arch_rc1 5 + chapters_j-k 8 + chapters_a-g 11 + chapters_h-i 13 + control_api_gui 50 = **88**

**R4 review 寫 89，PA `ls` 驗 88**。差 1 推測：R4 把 chapters_h-i 算 14（含 ghost L896 entry）；PA `ls` 確認實 13；所以 **實際 88 檔**（R4 prompt 慣性 89，下方 commit msg + path_redirects 表用 **88**，與 R4 review L7 ghost link finding 對齊）。

**已 mv 後空 dir 處置**：6 個空 dir 留在 `docs/worklogs/`，下次 commit P2-7（README 折疊）一併 `rmdir` 清除（git 不追蹤空 dir，無需 commit）。

---

## §3. README 折疊段設計（給 TW step 3 + main session P2-7 用）

### Edit target

**File**：`docs/README.md`
**old_string**：L862-1015 區段（從 `### worklogs/chapters_a-g/` 開頭 → L1015 末尾「`L 章自动学习管线 + 安全加固全量工程日志（含审核包设计、96 测试、8 项安全修复）|`」）
**old_string 完整內容**：上方 R4 review §Q1 表已列出邊界，由 TW 直接從 README L868 到 L1015 抽取（127 行；含 6 個 sub-section header + 表格 + L1009 內 04-14 audit footnote）
**new_string**：以下 17 行折疊段

```markdown
### Phase Packet Archive Index — 2026-03 ~ 2026-04 早期 phase 工作日誌（2026-05-28 歸檔）

下表 6 個目錄為 OpenClaw 早期 phase（A-K 章節 + Phase 5 + Control API/GUI + learning）工作日誌。**2026-05-28 phase 2 cleanup 統一歸檔至 `archive/2026-05-28--worklog_<topic>_archived/`**，原 detail 索引保留於各 archive 子目錄的 `_README.md`（grep 可命中）。

| Phase 目錄 | 期間 | 歸檔位置 | 檔數 |
|---|---|---|---|
| `chapters_a-g/` | 2026-03-11 ~ 03-19 | [`archive/2026-05-28--worklog_chapters_a-g_archived/`](archive/2026-05-28--worklog_chapters_a-g_archived/_README.md) | 11 |
| `chapters_h-i/` | 2026-03-20 ~ 03-22 | [`archive/2026-05-28--worklog_chapters_h-i_archived/`](archive/2026-05-28--worklog_chapters_h-i_archived/_README.md) | 13 (README ghost +1) |
| `chapters_j-k/` | 2026-03-22 ~ 03-24 | [`archive/2026-05-28--worklog_chapters_j-k_archived/`](archive/2026-05-28--worklog_chapters_j-k_archived/_README.md) | 8 |
| `control_api_gui/` | 2026-03-25 ~ 04-02 | [`archive/2026-05-28--worklog_control_api_gui_archived/`](archive/2026-05-28--worklog_control_api_gui_archived/_README.md) | 50 |
| `phase5_arch_rc1/` | 2026-04-03 ~ 04-07 | [`archive/2026-05-28--worklog_phase5_arch_rc1_archived/`](archive/2026-05-28--worklog_phase5_arch_rc1_archived/_README.md) | 5 (README ghost +15) |
| `learning/` | 2026-03-26 | [`archive/2026-05-28--worklog_learning_archived/`](archive/2026-05-28--worklog_learning_archived/_README.md) | 1 |

> 雙向 link：本表為順向入口；每個 archive 子目錄 `_README.md` 含原 README 對應段（grep `<檔 stem>` 仍命中）+ 逆向 link 回 `_indexes/path_redirects.md` Executed phase 2 段。
> Pre-2026-04-08 phase work moved to archive/; new worklogs go to `worklogs/` root（見下方「頂層工作日誌」段）。
```

**Edit 操作（給 main session P2-7）**：

```
Edit:
  file_path: docs/README.md
  old_string: <L868 起整段「### worklogs/chapters_a-g/ ...」到 L1015 末尾「| ... 8 项安全修复) |」共 148 行（含 L883/L902/L915/L969/L994/L1010/L1016 空行）>
  new_string: <上方 17 行折疊段>
  replace_all: false
```

**注意**：L1017+「### handoffs/ — 阶段交接文档」段保留（**phase 2 不動非 phase packet 索引段**）。

### L995-1009 頂層段（**保留**，紅線）

R4 review Q1 校正：原 prompt 把 L995-1009 誤算為 phase packet；實為 worklogs/ 根目錄 28 個現役 daily_summary（**2026-04-08+** 仍活躍）。**phase 2 絕對保留**。

---

## §4. L29-34 樹狀圖改寫（給 TW step 3 + main session P2-7 用）

### Edit target

**File**：`docs/README.md`
**old_string**（L28-35 上下文 + 6 行刪 + 1 行加 anchor）：

```
├── worklogs/                          ← 工作日志（按章节/模块分子目录）
│   ├── chapters_a-g/                  ← A-G 章节：基础层 / 观察者 / 事件层
│   ├── chapters_h-i/                  ← H-I 章节：本地判断内核 / AI 治理 / Decision Lease
│   ├── chapters_j-k/                  ← J-K 章节：Transition Engine / Paper Gate / GitHub 迁移
│   ├── control_api_gui/               ← Control API + GUI Operator Console 开发（2026-03-25~04-02）
│   ├── phase5_arch_rc1/               ← Phase 5 / L3 整改 / ARCH-RC1 开发（2026-04-03~04-07）
│   ├── learning/                      ← L 章节：自动学习管线 / 安全加固
│   └── （顶层文件）                   ← 2026-04-08+ 最新工作日志（直接放根目录）
```

**new_string**：

```
├── worklogs/                          ← 工作日志（顶层为现役；歷史 phase packet 已歸檔 archive/）
│   └── （顶层文件）                   ← 2026-04-08+ 最新工作日志（直接放根目录；歷史 phase packet 見 "Phase Packet Archive Index" 段）
```

**淨變動**：刪 6 行 + 改 1 行 = **-6 行樹狀圖**（保留「曾經有 phase packet 但已歸檔」歷史線索）。

**Edit 操作（給 main session P2-7）**：

```
Edit:
  file_path: docs/README.md
  old_string: <上方 8 行 L28-35>
  new_string: <上方 2 行>
  replace_all: false
```

---

## §5. 6 個 archive `_README.md` 詳細索引模板（給 TW step 3 用）

每個模板 = stub header + 原 README 對應段（copy 過來；含 ghost link NOTE 治理）+ 逆向 link。

### §5.1 `archive/2026-05-28--worklog_learning_archived/_README.md`

```markdown
# Archive: worklog_learning — 2026-05-28

> **歸檔日**：2026-05-28
> **來源**：`docs/worklogs/learning/`（1 檔）
> **歸檔理由**：L 章自動學習管線設計工作日誌（2026-03-26 單檔）；ML 平面已被 `docs/architecture/multi_agent_rework_2026-05-05/` + ADR 系列取代。原 README 索引活引用 30+ 天無讀寫。
> **Sign-off**：PM proposal `docs/governance_dev/2026-05-27--doc_governance_cleanup_proposal.md` D5（DEFER 解除）+ PA tech plan `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--doc_cleanup_phase2_tech_plan.md`

## 原 README L1011-1015 對應段

### worklogs/learning/ — L 章学习系统开发日志（2026-03-26）

| 文件 | 内容 |
|------|------|
| `2026-03-26--L章_自动学习管线与安全加固_完整工程日志.md` | L 章自动学习管线 + 安全加固全量工程日志（含审核包设计、96 测试、8 项安全修复） |

## Supersedes

歷史 phase 完結；無新版取代。對應的 ML / 學習平面當前 SSOT 在 `docs/architecture/multi_agent_rework_2026-05-05/AgentTodo.md` + `docs/adr/` 學習系列 ADR。

## Cross-ref

- 順向入口：`docs/README.md` § "Phase Packet Archive Index"
- 逆向 trail：`docs/_indexes/path_redirects.md` Executed phase 2 段
```

### §5.2 `archive/2026-05-28--worklog_phase5_arch_rc1_archived/_README.md`

```markdown
# Archive: worklog_phase5_arch_rc1 — 2026-05-28

> **歸檔日**：2026-05-28
> **來源**：`docs/worklogs/phase5_arch_rc1/`（5 檔）
> **歸檔理由**：Phase 5 / L3 整改 / ARCH-RC1 開發日誌（2026-04-03~04-07，5 個 daily_summary）；ARCH-RC1 已落入 ADR-0009 + `docs/architecture/` 系列。原 README 索引活引用 30+ 天無讀寫。
> **Sign-off**：同上
> **Ghost link 治理**：原 README L970-993 列 **20 條目**，但實檔僅 **5 個 daily_summary**——15 條 ghost link 是 2026-04-14 worklog audit 壓縮後遺留問題（R4 memory 2026-04-24 已記載；本 phase 2 治理）。本 `_README.md` 列實 5 檔。

## 原 README L970-993 對應段（去 ghost 後實 5 檔版本）

### worklogs/phase5_arch_rc1/ — Phase 5 / L3 整改 / ARCH-RC1 開發日誌（2026-04-03 ~ 2026-04-07）

| 文件 | 内容 |
|------|------|
| `2026-04-03--daily_summary.md` | ★★★★ 2026-04-03 日匯總（12 Sessions · 28 Commits）：文檔治理 + Phase 0-3 全覽 + Rust R-00~R-04 |
| `2026-04-04--daily_summary.md` | ★★★★ 2026-04-04 日匯總：V2 策略功能全面啟用（P0 緊急修復）+ Bybit API 基礎設施 |
| `2026-04-05--daily_summary.md` | ★★★★ 2026-04-05 日匯總（3 Sessions）：Phase 1 Full Rust 數據管線（G1-G4）+ Phase 2/3a/3b ML 基礎設施 + EXT-1 Exchange-as-Truth + RRC-1 設計 + 風控 GUI 補齊 + Demo 架構完成 |
| `2026-04-06--daily_summary.md` | ★★★★ 2026-04-06 日匯總：L3 整改 R0/R1/R2 + Drift Detector 接線 + Phase 4 啟動 |
| `2026-04-07--daily_summary.md` | ★★★★ 2026-04-07 日匯總：Phase 4 完成 + ARCH-RC1 1A/1B/1C-1/1C-2 |

> **歷史 ghost 註記**：原 README L970-993 額外列 15 個 .md 條目（如 `2026-04-04--td01_td02_td03_file_split.md` / `2026-04-04--session4_bybit_api_audit.md` / `2026-04-06--session1*_*.md` × 6 / `2026-04-07--session_*.md` × 5）；這 15 檔已於 2026-04-14 worklog audit 合併至上方對應日 `daily_summary.md` 並刪除，但 README 索引未同步——本 phase 2 治理該 ghost link 一致性。

## Supersedes

歷史 phase 完結；ARCH-RC1 設計已超越為：
- `docs/adr/ADR-0009*` — Unified Config Contract
- `docs/architecture/multi_agent_rework_2026-05-05/`
- `docs/references/2026-04-15--arch_rc1_unified_config_contract.md`

## Cross-ref

- 順向：`docs/README.md` § "Phase Packet Archive Index"
- 逆向：`docs/_indexes/path_redirects.md` Executed phase 2 段
- 已 mv 後仍引用本歸檔的活檔：`docs/CLAUDE_REFERENCE.md` L90-98（路徑由 P2-8 改寫）
```

### §5.3 `archive/2026-05-28--worklog_chapters_j-k_archived/_README.md`

```markdown
# Archive: worklog_chapters_j-k — 2026-05-28

> **歸檔日**：2026-05-28
> **來源**：`docs/worklogs/chapters_j-k/`（8 檔 = 6 .txt + 2 .md）
> **歸檔理由**：J-K 章節（Transition Engine / Paper Gate）+ GitHub 遷移工作日誌（2026-03-22~24）。GitHub 工作流早已 active；Transition Engine 已被 ADR + ConfigStore 取代。30+ 天無讀寫。
> **Sign-off**：同上

## 原 README L903-914 對應段

### worklogs/chapters_j-k/ — J-K 章节 + GitHub 迁移（2026-03-22 ~ 2026-03-24）

| 文件 | 内容 |
|------|------|
| `2026-03-22--项目总报告_含github核对.md` | 项目总报告（含 GitHub 核对） |
| `2026-03-22--夜间_最终整合总报告.txt` | 夜间最终整合总报告 |
| `2026-03-22--夜间_github迁移与诊断报告.txt` | GitHub 迁移与夜间诊断报告 |
| `2026-03-22--夜间_新对话接手prompt_github版.txt` | 新对话接手 Prompt（GitHub 工作流版） |
| `2026-03-24--工程总报告_结构迁移完成.txt` | 工程总报告：结构迁移完成 + 新工作流 |
| `2026-03-24--交接日志.txt` | 03-24 晚交接日志 |
| `2026-03-24--新对话启动prompt.txt` | 新对话启动 Prompt |
| `2026-03-24--work_report_current_dialogue.md` | 当前对话工作报告 |

## Supersedes

歷史 phase 完結；無新版取代。

## Cross-ref

- 順向：`docs/README.md` § "Phase Packet Archive Index"
- 逆向：`docs/_indexes/path_redirects.md` Executed phase 2 段
```

### §5.4 `archive/2026-05-28--worklog_chapters_a-g_archived/_README.md`

```markdown
# Archive: worklog_chapters_a-g — 2026-05-28

> **歸檔日**：2026-05-28
> **來源**：`docs/worklogs/chapters_a-g/`（11 檔，全 .txt）
> **歸檔理由**：A-G 章節基礎層 / 觀察者 / 事件層設計討論（2026-03-11~19）。已被 DOC-04 v2 + ADR-0001~0005 + 後續 phase 1-5 完全超越。30+ 天無讀寫。
> **Sign-off**：同上

## 原 README L868-882 對應段

### worklogs/chapters_a-g/ — A-G 章节工作日志（2026-03-11 ~ 2026-03-19）

| 文件 | 内容 |
|------|------|
| `2026-03-11--openclaw_bybit_进度日志.txt` | 03-11 项目启动，基础层搭建进度 |
| `2026-03-12--openclaw_bybit_进度日志.txt` | 03-12 继续基础层开发 |
| `2026-03-13--详细工作日志.txt` | 03-13 详细工作记录 |
| `2026-03-13--三日补充综合日志.txt` | 03-11~13 三日补充综合回顾 |
| `2026-03-17--chapter_g_工程记录.txt` | G 章工程记录（Revision 2） |
| `2026-03-17--chapter_g_执行清单.txt` | G 章执行清单（Revision 2） |
| `2026-03-17--engineering_log.txt` | 03-17 工程日志 |
| `2026-03-19--补充记录1.txt` | 03-19 补充记录 |
| `2026-03-19--当前进度图_校正后.txt` | 进度图校正版 |
| `2026-03-19--工作记录_含0317至0319校正与修复.txt` | 03-17~19 校正与修复工作记录 |
| `2026-03-19--完整版当前进度图.txt` | 完整版进度图（校正后） |

## Supersedes

A-G 章設計已被以下文件完全超越：
- `docs/decisions/DOC-04*` v2（基礎層 + 觀察者）
- `docs/adr/ADR-0001` ~ `ADR-0005`
- 後續 phase 1-5 工程實現

## Cross-ref

- 順向：`docs/README.md` § "Phase Packet Archive Index"
- 逆向：`docs/_indexes/path_redirects.md` Executed phase 2 段
```

### §5.5 `archive/2026-05-28--worklog_chapters_h-i_archived/_README.md`

```markdown
# Archive: worklog_chapters_h-i — 2026-05-28

> **歸檔日**：2026-05-28
> **來源**：`docs/worklogs/chapters_h-i/`（13 檔，全 .txt）
> **歸檔理由**：H-I 章節本地判断内核 + AI 治理 + Decision Lease 設計（2026-03-20~22）。H0 SLA 已落入 `docs/decisions/DOC-02*` `<1ms` + SM-04；H1 no-call semantics patch 已成正式 SM。30+ 天無讀寫。
> **Sign-off**：同上
> **Ghost link 治理**：原 README L884-901 列 **14 條目**，實檔 **13**——L896 entry `2026-03-22--全量整合总报告.txt` 不存在（實檔為 `..._重新导出.txt`，L897 entry）；ghost link 1 條。本 `_README.md` 列實 13 檔。

## 原 README L884-901 對應段（去 ghost 後實 13 檔版本）

### worklogs/chapters_h-i/ — H-I 章节工作日志（2026-03-20 ~ 2026-03-22）

| 文件 | 内容 |
|------|------|
| `2026-03-20--openclaw_工作记录.txt` | 03-20 H-I 章节开始 |
| `2026-03-20--超详细续接总报告.txt` | 超详细续接总报告 |
| `2026-03-20--h0_本地判断核心蓝图_v1.txt` | H0 本地判断核心蓝图 v1 |
| `2026-03-20--h_i_本地执行内核讨论备份.txt` | H-I 本地执行内核讨论备份 |
| `2026-03-22--0320工作报告_新对话接手版.txt` | 03-20 工作报告（供新对话接手） |
| `2026-03-22--a-i_接手摘要.txt` | A-I 全量接手摘要 |
| `2026-03-22--h_i_正式完工对账报告.txt` | H-I 正式完工对账报告 |
| `2026-03-22--h_i_兼容性对账清单.txt` | H-I 兼容性对账清单（新对话首步验证） |
| `2026-03-22--全量整合总报告_重新导出.txt` | 全量整合总报告（重新导出版；原 README L896 ghost entry `..._重新导出.txt` 之前的 `..._总报告.txt` 不存在） |
| `2026-03-22--晚_工程记录.txt` | 03-22 晚间工程记录（Fix H-I） |
| `2026-03-22--晚_新对话接手指示.txt` | 新对话接手指示 |
| `2026-03-22--晚_新对话接手prompt.txt` | 新对话接手 Prompt |
| `2026-03-22--晚_h1_no_call_semantics_patch.txt` | H1 no-call 语义补丁 bundle |

> **歷史 ghost 註記**：原 README L896 列 `2026-03-22--全量整合总报告.txt` 為 ghost entry（檔不存在；實檔為 L897 `..._重新导出.txt`）。本 phase 2 治理該索引失準。

## Supersedes

H-I 核心設計已超越為：
- `docs/decisions/SM-04*`（風控降級）
- `docs/decisions/DOC-04*`（本地判断核心）
- `docs/decisions/DOC-02*` H0 SLA `<1ms`

## Cross-ref

- 順向：`docs/README.md` § "Phase Packet Archive Index"
- 逆向：`docs/_indexes/path_redirects.md` Executed phase 2 段
```

### §5.6 `archive/2026-05-28--worklog_control_api_gui_archived/_README.md`

```markdown
# Archive: worklog_control_api_gui — 2026-05-28

> **歸檔日**：2026-05-28
> **來源**：`docs/worklogs/control_api_gui/`（50 檔 = 45 .md + 5 .txt）
> **歸檔理由**：Control API + GUI Operator Console 開發日誌（2026-03-25~04-02），含 Phase 1/2/3 完整工程日誌 + wave4/wave7/wave8 里程碑。Phase 1-3 全 commit 已落入 git history；GUI 當前 SSOT 在 `docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md` + `srv/services/control_api/`。30+ 天無讀寫（CLAUDE_REFERENCE.md L83-88 仍引 6 檔，路徑由 P2-8 改寫）。
> **Sign-off**：同上
> **內檔 self-ref 處理**：`2026-03-27--layer2_ai_engine_design_session.md` L115-116 自我引用 + 引同目錄 brainstorm 檔；mv 後檔本身在本 archive，但檔內字串仍是舊路徑——由 P2-8 改寫為相對路徑（或同目錄 anchor）。

## 原 README L916-968 對應段

### worklogs/control_api_gui/ — Control API + GUI 开发日志（2026-03-25 ~ 2026-04-02）

| 文件 | 内容 |
|------|------|
| `2026-03-25--jk收口_单独接手文件.txt` | J-K 收口完成版接手文件 |
| `2026-03-25--jk收口_完整工程记录.txt` | J-K 收口完成版完整工程记录 |
| `2026-03-25--g到k详细复盘与程序总表.txt` | G~K 详细复盘与程序总表 |
| `2026-03-25--新对话工作方式与带入文件清单.txt` | 新对话工作方式与带入文件清单 |
| `2026-03-25--新对话启动prompt.txt` | 新对话启动 Prompt |
| `2026-03-26--api_gui_全量工程报告.md` | API + GUI 全量工程报告 |
| `2026-03-26--paper_trading_engine_完整工程日志.md` | Paper Trading Engine 完整工程日志（引擎核心 + 14 路由 + GUI + 43 测试） |
| `2026-03-26--beta_pipeline_shadow_decision_metrics.md` | Beta 管线完善：实时行情 + 自动桥接 + 影子决策管线 + 性能指标（248 测试，73 路由） |
| `2026-03-26--brainstorm_openclaw_agent_architecture.md` | Brainstorm 留档：OpenClaw 定位（通信层非大脑）+ Agent 智能化架构讨论 |
| `2026-03-26--openclaw_fusion_console_systemd_服务化.md` | OpenClaw 融合 + 统一控制台 + systemd 服务化 + 远程访问方案规划 |
| `2026-03-26--brainstorm_layer2_ai_reasoning_engine.md` | Brainstorm：Layer 2 AI 推理引擎设计（三层架构 + Agent 循环 + 工具箱 + 成本控制） |
| `2026-03-27--layer2_ai_engine_design_session.md` | Layer 2 设计工作记录：搜索 Provider 方案调研决策 + 4 层降级体系 + 模型升级判断 + 自适应预算 + PnL 归因 |
| `2026-03-27--phase1_risk_framework_implementation.md` | Phase 1 早期工程日志：S1-S5 安全修复 + 三层 P0/P1/P2 风控 + 8 路由（327→369） |
| `2026-03-27--phase1_complete_engineering_log.md` | Phase 1 中期工程日志（第 1-2 轮审核后） |
| `2026-03-27--phase1_final_audited_engineering_log.md` | ★ Phase 1 最终审核版：4 轮审核 + 25 问题修复 + 405 测试 + 93 路由 |
| `2026-03-27--pre_phase1_audit_fixes.md` | Pre-Phase1 代码审核：metrics 完全重写 + SSRF 防护 + 成本追踪 race fix + adaptive 强制执行 |
| `2026-03-27--phase2_local_strategy_toolkit_engineering_log.md` | ★ Phase 2 完整工程日志：K线管理器 + 6 指标 + 信号生成器 + 4 策略 + 编排器 + 11 路由 + 严格审核修复（620 测试） |
| `2026-03-27--phase3_pipeline_bridge_engineering_log.md` | Phase 3 工程日志：管线桥接器 + 止损管理器 + 信号增强 + 策略增强（640 测试） |
| `2026-03-27--full_system_audit_fix_engineering_log.md` | ★ 全系统审核修复工程日志：7C+19H+28M+16L + 路径统一 + I章去重 + mutator 3x→1x |
| `2026-03-27--roadmap_B_to_I_engineering_log.md` | ★ 路线图 B-I 实现：cron+加权共识+volume+Grid几何+多TF+tick防护+持久化+Delta-Neutral套利（641测试） |
| `2026-03-27--full_day_session_summary.md` | ★★ 完整工作日总结：13 commits + 644 测试 + 20 新文件 + GUI 待做清单 |
| `2026-03-27--gui_three_layer_implementation.md` | GUI 三层架构：Grafana + TradingView + Bybit Demo + 登录系统 + 统一控制台 |
| `2026-03-27--autonomous_agent_scanner_deployer.md` | ★ 自主交易 Agent：市场扫描器 650 符号 + 策略自动部署 + Demo 同步 + 登录系统 |
| `2026-03-27--session2_audit_fix_and_agent_autonomy.md` | Session 2 总结：GUI三层 + Demo + 自主Agent + R1-R5修复 + 第4轮审核7C+10H |
| `2026-03-27--session3_remaining_audit_fixes.md` | Session 3：残留审核全修（时间戳6处+浮点容差+TIF执行+Kahan求和+401刷屏+volume动态+测试修复=646测试） |
| `2026-03-27--gui_10tab_restructure.md` | ★ GUI 10-Tab 全面重构：common.js+8新Tab+双层解释+三层信息密度+99 API端点覆盖 |
| `2026-03-27--session4_gui_10tab_professional_console.md` | ★★ Session 4 完整日志：6 commits+17 files+3964 行+多供应商AI+可编辑风控+中文状态+确认弹窗 |
| `2026-03-27--remote_access_and_security_hardening.md` | 远程访问配置 + 安全加固：Tailscale + secrets 权限 + API key 硬编码消除 |
| `2026-03-27--session5_pipeline_launch_and_openclaw_analysis.md` | Session 5：管线启动验证 + OpenClaw 能力深挖 + systemd 自动重启确认 + Paper Trading 169 单 |
| `2026-03-28--session6_halfday_data_analysis_and_fixes.md` | ★ Session 6：半天数据分析（胜率0%根因）+ 4项修复（扫描器过滤+置信度0.55+.orig stub+3张DB表） |
| `2026-03-28--session7_system_audit_and_fixes.md` | ★★ Session 7：系统全面审核（8模块/12问题）+ 5项修复（市场流自动重启+unknown regime保护+trend cap+时间驱动+confidence对齐），646 测试通过 |
| `2026-03-28--session8_functional_audit_report.md` | ★★★ Session 8：A-J 全面功能审核（25h/684fill/胜率0%）+ E1/G1/H1 三项修复（自动学习/连续亏损暂停/ATR止损接入），428 测试通过 |
| `2026-03-28--session9_bug_fixes_and_verification.md` | ★★ Session 9：3项 bug 修复（net_realized_pnl字段/active_count+1/on_fill仓位同步链路）+ 18个验证测试，664 测试通过 |
| `2026-03-28--session10_ai_cost_and_double_stop_fix.md` | ★★ Session 10：2项修复（total_ai_cost汇总/双重止损防护）+ 7个验证测试，664 测试通过 |
| `2026-03-28--session11_regime_aware_stops.md` | ★★★ Session 11：regime感知止损/止盈/时间三维调整（REGIME_STOP/TP/TIME_MULTIPLIERS）+ 8个验证测试，33+428 测试通过 |
| `2026-03-29--session12_data_analysis_and_bug_fixes.md` | ★★★ Session 12：数据分析发现 0% 胜率根因（fill碎片化+注意力税误关仓），修复 F1/F2/E1a/E1b + GUI G1-G6（活跃订单/价格精度/Demo对比/学习系统），432 测试通过 |
| `2026-03-31--gui_tab_restructure_ollama_optimization.md` | ★★ GUI Tab 重构（Paper+Demo合并+实盘占位）+ Ollama 优化（9B/27B分配+think=False 4x提速+edge filter修复）+ 后台市场流常驻 + 周报时间表调整 |
| `2026-03-31--position_sizing_dynamic_qty_rebalancer.md` | ★★ Position Sizing 重構：3% risk/trade + 25 symbols + 動態 qty（每單重算）+ 智能資本再分配（弱倉自動平倉讓位新機會）|
| `2026-03-31--wave4_p2p3_security_audit_fixes.md` | ★★ Wave 4 P2/P3 批次：5 Sprint · P2-NEW-1~9 + FA-2/3/4 + P3-TECH-1~3（安全補齊 + 端點矩陣完整覆蓋 + NaN/inf 邊界值 + event loop 阻塞修復），2555 tests |
| `2026-03-31--paper_demo_sync_fixes.md` | ★★★ Paper/Demo 同步修復：10 項分歧根源分析 · 3 CRITICAL 修復（止損同步+失敗標記+對賬參數名）· qty 統一四捨五入 · 對賬引擎首次真正運行 |
| `2026-03-31--full_day_complete_engineering_log.md` | ★★★★ 2026-03-31 全天完整工程日誌（整合版）：7-Agent 全系統審計 · P0 CRITICAL×4 修復 · Wave 0-3 全系列 · H0 Gate Day 1-3 · Wave 4 Sprint 4a-4e · Wave 5a Position Sizing + 5b Paper/Demo 同步 · Wave 5 Sprint H鏈接通 · Wave 6 Sprint 0+1a+1b+2 + Cleanup · Phase 2 Batch 2A+2B，2624 tests |
| `2026-03-31--round2_batch_records_archive.md` | Round 2 Batch 3-12 + Session 8-12 歸檔（CLAUDE_REFERENCE.md L83 引用） |
| `2026-04-01--phase2_batch2c_completion.md` | ★★★ Phase 2 Batch 2C 完成：接通 _register_pattern_claims 雙路徑 + backtest_routes.py API + 決策權重集成 · Git 分歧解決（rebase）· 3103 tests |
| `2026-04-01--wave7_demo_sync_spot_category_pinned.md` | ★★★ Wave 7：Paper 內部平倉 Demo 同步 + stop_session 自動清倉 + Spot 品類全鏈路（Scanner+策略+Position）+ demo_reserved 解鎖 + GUI 品類標籤 + BTC/ETH 釘選幣種 |
| `2026-04-01--wave7a_spot_symbol_category.md` | ★★★ Wave 7a Spot 品類啟用 + 方案 A/B symbol-category 映射：SPOT-1~5 全通 + _symbol_category_map 雙向注入 + SymbolCategoryRegistry 啟動填充，3103→3161 tests |
| `2026-04-01--phase3_full_completion_and_wave7b.md` | ★★★★ Wave 7b Inverse 品類（INV-1~5）+ Phase 3 全完成（3A ExperimentLedger/Routes/EvolutionEngine + 3B TruthSourceRegistry持久化/AnalystAgent觀測/auto_seed + 3C EvolutionScheduler週進化/小時清理/GUI dashboard）· 3103→3330 tests |
| `2026-04-01--governance_auth_restart_fix_and_order_unblock.md` | ★★ GovernanceHub 重啟後授權丟失根因診斷與修復：5 層診斷（state.json→audit→bridge stats→auth NONE）· get_status() auth_pending_approval 修復 · /session/reauth 端點 · startup 自動補授 · 首筆 FARTCOINUSDT 訂單解封成交 |
| `2026-04-01--main_legacy_refactor_wave_a_to_e.md` | ★★★★ main_legacy.py 重構全記錄：5265→407 行（-92%），Wave A-E 共拆出 11 模塊，monkey-patch 延遲查找修復，E5 審查 build_review_queue bug 修復，§14 約定建立，3005 tests 零回歸 |
| `2026-04-01--wave8_pa_reality_check_and_parallel_fix.md` | ★★★★ Wave 8 工作日誌：PA 69 項實況檢查 + 6 軌道×2 批並行修復 38/39 項 + strategist 拆分 + on_tick/mutator 拆分 + now_ms 統一 + +148 測試 |
| `2026-04-02--batch9a_deterministic_adaptive_risk.md` | ★★★ Batch 9A 確定性自適應風控：QC 量化審查驅動 · ATR 雙窗口 + 成本感知入場門檻 + 追蹤止損成本約束 + round-trip 真實費用 · 修復 ATR 止損死代碼 bug · +66 測試 · 3703 passed |

## Supersedes

歷史 phase 完結；當前 SSOT：
- GUI：`docs/execution_plan/2026-05-06--gui_openclaw_control_console_plan.md`
- API：`srv/services/control_api/` 代碼 + `docs/references/2026-04-04--bybit_api_reference.md`
- Phase 1-3 工程實現已在 git history

## Cross-ref

- 順向：`docs/README.md` § "Phase Packet Archive Index"
- 逆向：`docs/_indexes/path_redirects.md` Executed phase 2 段
- 仍引本歸檔的活檔（P2-8 全部改寫）：
  - `docs/CLAUDE_REFERENCE.md` L83-88（6 entries）
  - `docs/references/2026-03-27--system_reference_handbook.md` L216 區段
  - `docs/governance_dev/changelogs/2026-03-29_T2.23_orig_file_cleanup.md` L106 self-ref
  - `docs/audits/2026-04-12--full_program_chain_audit.md` 多處（不改內文，文末加 footer NOTE）
  - `docs/references/2026-04-02--system_status_report.md` L26650+ ~50 entries（auto-generated manifest，下次 `regen_doc_inventory.py` 自動更新）
```

---

## §6. 補修清單（CLAUDE_REFERENCE / references / changelogs / audit）

### §6.1 `docs/CLAUDE_REFERENCE.md` L83-98（11 entries）

**Edit target**：`docs/CLAUDE_REFERENCE.md` L79-98 兩個 sub-section（control_api_gui 6 entry + phase5_arch_rc1 5 entry）
**old_string**（L79-98 完整段）：

```markdown
### 工作日誌（worklogs/control_api_gui/ — 2026-03-25~04-02）

| 內容 | 文件位置 |
|------|---------|
| Round 2 Batch 3-12 + Session 8-12 歸檔 | `docs/worklogs/control_api_gui/2026-03-31--round2_batch_records_archive.md` |
| GUI Tab 重構 + Ollama 優化 | `docs/worklogs/control_api_gui/2026-03-31--gui_tab_restructure_ollama_optimization.md` |
| Session 4 GUI 專業控制台 | `docs/worklogs/control_api_gui/2026-03-27--session4_gui_10tab_professional_console.md` |
| Session 6 勝率0%根因 | `docs/worklogs/control_api_gui/2026-03-28--session6_halfday_data_analysis_and_fixes.md` |
| Session 7 系統審核 | `docs/worklogs/control_api_gui/2026-03-28--session7_system_audit_and_fixes.md` |
| Session 8 功能審核 | `docs/worklogs/control_api_gui/2026-03-28--session8_functional_audit_report.md` |

### 工作日誌（worklogs/phase5_arch_rc1/ — 2026-04-03~04-07）

| 內容 | 文件位置 |
|------|---------|
| 2026-04-03 日匯總（Phase 5 啟動 + Rust 遷移開始） | `docs/worklogs/phase5_arch_rc1/2026-04-03--daily_summary.md` |
| 2026-04-04 日匯總（Bybit API 整合）| `docs/worklogs/phase5_arch_rc1/2026-04-04--daily_summary.md` |
| 2026-04-05 日匯總（Rust 數據管線 + ML 基礎設施）| `docs/worklogs/phase5_arch_rc1/2026-04-05--daily_summary.md` |
| L3 R0-R2 整改（Session 10-13）| `docs/worklogs/phase5_arch_rc1/2026-04-06--session1*.md` |
| ARCH-RC1 1A/1B/1C-1/1C-2 實現 | `docs/worklogs/phase5_arch_rc1/2026-04-07--session_arch_rc1_*.md` |
```

**new_string**：

```markdown
### 工作日誌（worklog_control_api_gui — 2026-03-25~04-02，已 2026-05-28 歸檔）

| 內容 | 文件位置 |
|------|---------|
| Round 2 Batch 3-12 + Session 8-12 歸檔 | `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-31--round2_batch_records_archive.md` |
| GUI Tab 重構 + Ollama 優化 | `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-31--gui_tab_restructure_ollama_optimization.md` |
| Session 4 GUI 專業控制台 | `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-27--session4_gui_10tab_professional_console.md` |
| Session 6 勝率0%根因 | `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-28--session6_halfday_data_analysis_and_fixes.md` |
| Session 7 系統審核 | `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-28--session7_system_audit_and_fixes.md` |
| Session 8 功能審核 | `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-28--session8_functional_audit_report.md` |

### 工作日誌（worklog_phase5_arch_rc1 — 2026-04-03~04-07，已 2026-05-28 歸檔）

| 內容 | 文件位置 |
|------|---------|
| 2026-04-03 日匯總（Phase 5 啟動 + Rust 遷移開始） | `docs/archive/2026-05-28--worklog_phase5_arch_rc1_archived/2026-04-03--daily_summary.md` |
| 2026-04-04 日匯總（Bybit API 整合）| `docs/archive/2026-05-28--worklog_phase5_arch_rc1_archived/2026-04-04--daily_summary.md` |
| 2026-04-05 日匯總（Rust 數據管線 + ML 基礎設施）| `docs/archive/2026-05-28--worklog_phase5_arch_rc1_archived/2026-04-05--daily_summary.md` |
| L3 R0-R2 整改（Session 10-13）| 已合併至 `2026-04-06--daily_summary.md`（archive 內） |
| ARCH-RC1 1A/1B/1C-1/1C-2 實現 | 已合併至 `2026-04-07--daily_summary.md`（archive 內） |
```

**重要 ghost 治理**：原 CLAUDE_REFERENCE.md L97-98 引 `2026-04-06--session1*.md` + `2026-04-07--session_arch_rc1_*.md` glob → 實 5 daily_summary 已合併（2026-04-14 audit 結果）；新版直接指 daily_summary（與 archive `_README.md` ghost lineage 一致）。

### §6.2 `docs/references/2026-03-27--system_reference_handbook.md` L216 區段

**Edit target**：`docs/references/2026-03-27--system_reference_handbook.md` L216-220
**old_string**：

```
docs/worklogs/control_api_gui/
  2026-03-27--phase2_local_strategy_toolkit_engineering_log.md
    → Phase 2 完整工程日志
  2026-03-27--phase1_final_audited_engineering_log.md
    → Phase 1 最终审核版工程日志
```

**new_string**：

```
docs/archive/2026-05-28--worklog_control_api_gui_archived/   # 2026-05-28 歸檔
  2026-03-27--phase2_local_strategy_toolkit_engineering_log.md
    → Phase 2 完整工程日志
  2026-03-27--phase1_final_audited_engineering_log.md
    → Phase 1 最终审核版工程日志
```

### §6.3 `docs/governance_dev/changelogs/2026-03-29_T2.23_orig_file_cleanup.md` L106

**Edit target**：L106 1 行
**old_string**：

```
- **Previous Session:** `docs/worklogs/control_api_gui/2026-03-28--session6_halfday_data_analysis_and_fixes.md`
```

**new_string**：

```
- **Previous Session:** `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-28--session6_halfday_data_analysis_and_fixes.md` (2026-05-28 歸檔)
```

### §6.4 `docs/audits/2026-04-12--full_program_chain_audit.md` 文末 footer NOTE

**Edit target**：L5988 `--- END OF AUDIT ---` 之前插入
**old_string**（L5983-5988）：

```
---

*審計人：A3 (UX/GUI Auditor)*
*審計方法：靜態代碼分析（全量 onclick 交叉比對、API 端點驗證、CSS 一致性檢查、文件行數統計）*

--- END OF AUDIT ---
```

**new_string**：

```
---

*審計人：A3 (UX/GUI Auditor)*
*審計方法：靜態代碼分析（全量 onclick 交叉比對、API 端點驗證、CSS 一致性檢查、文件行數統計）*

> NOTE (2026-05-28)：本 audit 引用的 worklog 路徑 `worklogs/control_api_gui/` / `worklogs/phase5_arch_rc1/` / `worklogs/chapters_j-k/` 等已於 2026-05-28 phase 2 cleanup 統一歸檔至 `docs/archive/2026-05-28--worklog_<topic>_archived/`。歷史 audit 證據不改內文；新 grep 應用 archive 路徑。詳見 `docs/README.md` § "Phase Packet Archive Index" + `docs/_indexes/path_redirects.md` Executed phase 2 段。

--- END OF AUDIT ---
```

### §6.5 內部 self-ref：`2026-03-27--layer2_ai_engine_design_session.md` L115-116（**mv 後**檔）

**Edit target**：`docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-27--layer2_ai_engine_design_session.md` L115-116（mv 後新路徑）
**old_string**：

```
| 本工作记录 | `docs/worklogs/control_api_gui/2026-03-27--layer2_ai_engine_design_session.md` | 本文件 |
| Brainstorm 留档 | `docs/worklogs/control_api_gui/2026-03-26--brainstorm_layer2_ai_reasoning_engine.md` | 前一轮初步设计（已有） |
```

**new_string**：

```
| 本工作记录 | `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-27--layer2_ai_engine_design_session.md` | 本文件（2026-05-28 歸檔） |
| Brainstorm 留档 | `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-26--brainstorm_layer2_ai_reasoning_engine.md` | 前一轮初步设计（同歸檔目錄） |
```

**注意**：此 Edit 必須在 P2-6（control_api_gui mv 完成後）才能執行；歸入 P2-8 一起改。

### §6.6 不改的活引用（auto-generated）

- `docs/references/2026-04-02--system_status_report.md` L26650-27000 共 ~50 entries（每 entry 約 10 行 = ~500 行段落）= **auto-generated `system_status_report` 內嵌 manifest**；不手動改；下次 `regen_doc_inventory.py` 自動更新（P2-9 一併跑）

---

## §7. path_redirects.md Phase 2 Executed 段補（給 main session P2-9 用）

**Edit target**：`docs/_indexes/path_redirects.md` L114 之後（即 phase 1 Retention policy 段之後）插入
**old_string**：`- D5 phase packet 6 dir (\`phase5_arch_rc1\` / \`control_api_gui\` / \`chapters_a-g\` / \`chapters_h-i\` / \`chapters_j-k\` / \`learning\`) **未 archive**（PM DEFER；被 README L862-1009 主索引活引用）`

**new_string**：

```markdown
- D5 phase packet 6 dir (`phase5_arch_rc1` / `control_api_gui` / `chapters_a-g` / `chapters_h-i` / `chapters_j-k` / `learning`) **已於 phase 2 archive（2026-05-28）**；見下方 "Executed Redirects (2026-05-28 phase 2)" 段

---

## Executed Redirects (2026-05-28 phase 2)

> 來源：doc cleanup phase 2（PA tech plan `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--doc_cleanup_phase2_tech_plan.md` + R4 review `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-28--phase_packet_index_refactor_review.md` APPROVE）
> 執行 commit chain：`<P2-1>` ~ `<P2-6>`（6 個 mv batch；每 dir 1 commit）+ `<P2-7>`（README 折疊）+ `<P2-8>`（補修 4 處活引用）+ `<P2-9>`（本段 + JSON regen）

| Old path | New path | Reason | Stub |
|---|---|---|---|
| `docs/worklogs/learning/` | `docs/archive/2026-05-28--worklog_learning_archived/` | 歷史 phase 完結（2026-03-26 L 章設計）；30+ 天無讀寫 | `archive/.../_README.md` |
| `docs/worklogs/phase5_arch_rc1/` | `docs/archive/2026-05-28--worklog_phase5_arch_rc1_archived/` | Phase 5 / ARCH-RC1 設計已落入 ADR-0009；README 索引列 20 但實 5（ghost link 15 條已治理） | `archive/.../_README.md` |
| `docs/worklogs/chapters_j-k/` | `docs/archive/2026-05-28--worklog_chapters_j-k_archived/` | J-K 章節 + GitHub 遷移完結；新工作流已 active | `archive/.../_README.md` |
| `docs/worklogs/chapters_a-g/` | `docs/archive/2026-05-28--worklog_chapters_a-g_archived/` | A-G 章基礎層設計已被 DOC-04 v2 + ADR-0001~0005 超越 | `archive/.../_README.md` |
| `docs/worklogs/chapters_h-i/` | `docs/archive/2026-05-28--worklog_chapters_h-i_archived/` | H-I 核心設計已落入 DOC-02 H0 SLA + SM-04；README 列 14 但實 13（ghost link 1 條已治理） | `archive/.../_README.md` |
| `docs/worklogs/control_api_gui/` | `docs/archive/2026-05-28--worklog_control_api_gui_archived/` | Phase 1-3 完整工程日誌；當前 SSOT 在 execution_plan + srv/services/control_api/ + git history | `archive/.../_README.md` |

### Ghost link 治理 NOTE

- `phase5_arch_rc1`：原 README L970-993 列 20 條目 vs 實檔 5；15 條 ghost 是 2026-04-14 worklog audit 壓縮後遺留（R4 memory 2026-04-24 記載）；本 phase 2 治理一致
- `chapters_h-i`：原 README L896 列 `2026-03-22--全量整合总报告.txt` 不存在（實檔為 L897 `..._重新导出.txt`）；1 條 ghost 治理

### Cross-ref additions (Class 3, inline phase 2)

| File | Action |
|---|---|
| `docs/audits/2026-04-12--full_program_chain_audit.md` | 文末加 footer NOTE：「本 audit 引用 worklog 已 2026-05-28 歸檔；新 grep 用 archive 路徑」 |
| `docs/archive/2026-05-28--worklog_control_api_gui_archived/2026-03-27--layer2_ai_engine_design_session.md` | L115-116 內部 self-ref 改為 archive 路徑 |
| `docs/CLAUDE_REFERENCE.md` L79-98 | 11 entry 路徑改為 archive 路徑 |
| `docs/references/2026-03-27--system_reference_handbook.md` L216-220 | 5 行區段路徑改為 archive |
| `docs/governance_dev/changelogs/2026-03-29_T2.23_orig_file_cleanup.md` L106 | 1 行 self-ref 路徑改為 archive |

### Retention policy (phase 2)

- 沿 phase 1 policy：至少保留 1 個 sprint cycle；超過後仍只 archive 不 delete
- 每個 archive 子目錄含 `_README.md` lineage stub
- ghost link 治理紀錄保留於 archive `_README.md` 內，作為「為何實檔與當時 README 列表不一致」的歷史證據
```

---

## §8. 完整 commit chain 設計（11 commits）

| # | Commit subject | Files / 操作 | Executor | Pre-condition |
|---|---|---|---|---|
| **P2-0** | `docs(governance): R4 review + PA phase 2 plan land [skip ci]` | R4 review file + 本 PA plan file（git add 兩個檔 + commit） | **main session** | worktree porcelain clean；HEAD `57024d43` |
| **P2-1** | `docs(cleanup): batch 2A — archive worklog_learning (1 file) [skip ci]` | 1 mv + 1 `_README.md` stub + git add + commit | **main session** | P2-0 done |
| **P2-2** | `docs(cleanup): batch 2B — archive worklog_phase5_arch_rc1 (5 files; ghost link 15→0) [skip ci]` | 5 mv + 1 `_README.md` stub（含 ghost lineage NOTE）+ git add + commit | **main session** | P2-1 done |
| **P2-3** | `docs(cleanup): batch 2C — archive worklog_chapters_j-k (8 files) [skip ci]` | 8 mv + 1 `_README.md` stub + git add + commit | **main session** | P2-2 done |
| **P2-4** | `docs(cleanup): batch 2D — archive worklog_chapters_a-g (11 files) [skip ci]` | 11 mv + 1 `_README.md` stub + git add + commit | **main session** | P2-3 done |
| **P2-5** | `docs(cleanup): batch 2E — archive worklog_chapters_h-i (13 files; ghost link 1→0) [skip ci]` | 13 mv + 1 `_README.md` stub（含 ghost lineage NOTE）+ git add + commit | **main session** | P2-4 done |
| **P2-6** | `docs(cleanup): batch 2F — archive worklog_control_api_gui (50 files) [skip ci]` | 50 mv（glob）+ 1 `_README.md` stub + git add + commit | **main session** | P2-5 done |
| **P2-7** | `docs(cleanup): README fold L862-1015 phase packet index + L29-34 tree rewrite [skip ci]` | 1 README.md Edit（折疊 148 行 → 17 行 + 樹狀圖 8 行 → 2 行）+ git add + commit | **main session**（TW step 3 寫好 new_string 文字後 main session 操作 Edit） | P2-6 done（6 dir 全空） |
| **P2-8** | `docs(cleanup): companion path fixes — CLAUDE_REFERENCE + system_reference_handbook + T2.23 changelog + 2026-04-12 audit footer + layer2_ai_engine self-ref [skip ci]` | 5 file Edit（§6.1-§6.5）+ git add + commit | **main session**（派 TW 寫 new_string 後 main session 操作 Edit） | P2-7 done |
| **P2-9** | `docs(cleanup): batch 2 — path_redirects.md Executed phase 2 + inventory JSON regen [skip ci]` | 1 path_redirects.md Edit（§7）+ `helper_scripts/regen_doc_inventory.py --ts-label 2026-05-28T0230` 跑後加 1 個 inventory JSON snapshot + git add + commit | **main session** | P2-8 done |
| **P2-10** | `docs(cleanup): phase 2 final report + memory append [skip ci]` | 1 TW final report `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-28--doc_cleanup_phase2_final.md` + PA memory append + git add + commit | **main session**（派 TW 寫 final report）；PA memory 由 main session append | P2-9 done |

### Commit msg 規範

所有 commit msg 含：
- subject 結尾 `[skip ci]`（doc-only 不觸發 CI）
- body 列出 mv 檔數 + lineage 來源 + R4/PA plan 引用
- 範例（P2-2）：

```
docs(cleanup): batch 2B — archive worklog_phase5_arch_rc1 (5 files; ghost link 15→0) [skip ci]

Move worklogs/phase5_arch_rc1/ to archive/2026-05-28--worklog_phase5_arch_rc1_archived/
per phase 2 plan. README L970-993 detailed section folded into 17-row phase
packet summary table in P2-7.

- 5 mv: 2026-04-03/04/05/06/07 daily_summary.md
- 1 stub: _README.md (lineage to README §"Phase Packet Archive Index" +
  path_redirects.md + ghost link 15→0 governance NOTE)

Ghost link governance:
- Original README L970-993 listed 20 entries but actual files = 5 daily_summary
- 15 ghost entries were 2026-04-14 worklog audit merge result (R4 memory
  2026-04-24 noted)
- Phase 2 _README.md lists actual 5 files + governance NOTE for the 15
  merged-then-orphaned entries

Refs:
- PA tech plan: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-28--doc_cleanup_phase2_tech_plan.md §2 Batch 2-B
- R4 review: docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-28--phase_packet_index_refactor_review.md
```

---

## §風險 / 衝突檢測

### A. 89 檔 stem 名活引用 grep（main session step 7 跑）

**89 → 88 重核**：實際 1+5+8+11+13+50 = **88 檔**（R4 review 寫 89 為含 ghost L896 `..._总报告.txt` 不存在 entry）

**Grep 命令範例**（5 區掃描）：

```bash
# 5 區 = CLAUDE.md / TODO.md / README.md(srv 根) / docs/agents/*.md / docs/README.md（已折疊段內不應殘留）
cd /Users/ncyu/Projects/TradeBot/srv-doc-cleanup

# 全 88 檔 stem 名抽樣 grep（拿幾個高頻 stem）
for stem in "phase1_final_audited" "session4_gui_10tab" "h0_本地判断核心蓝图" "ARCH-RC1" "td01_td02_td03"; do
  echo "=== grep $stem ==="
  grep -rln "$stem" CLAUDE.md TODO.md README.md docs/agents/ docs/README.md 2>/dev/null
done

# 完整：所有 88 檔 stem 抽出後 batch grep（main session step 7 跑）
ls docs/archive/2026-05-28--worklog_*_archived/*.{md,txt} 2>/dev/null | \
  xargs -I{} basename {} | sed 's/\.\(md\|txt\)$//' | \
  while read stem; do
    hits=$(grep -rln "$stem" CLAUDE.md TODO.md README.md docs/agents/ 2>/dev/null | grep -v "/archive/" | wc -l)
    [ "$hits" -gt 0 ] && echo "WARN: $stem still referenced in $hits files"
  done
```

**預期結果**：5 區 0 命中（已 R4 grep 預驗）。若有命中 → P2-7 / P2-8 漏改，回頭補。

### B. 命名衝突檢測（已驗）

```bash
ls -1 docs/archive/ | grep "2026-05-28--worklog_"
# 預期：0（已 ls 驗證 0 collision）
```

### C. ghost link 治理（內生於 §5.2 + §5.5）

- phase5_arch_rc1 `_README.md` 含 lineage NOTE 列出 15 個被 merge 條目
- chapters_h-i `_README.md` 含 L896 ghost entry 治理 NOTE

### D. control_api_gui 50 檔 glob 安全性

`git mv docs/worklogs/control_api_gui/* docs/archive/.../` shell glob 展開後 = 50 個 `git mv` operation；驗證命令：

```bash
ls -1 docs/worklogs/control_api_gui/ | wc -l  # 預期 50（mv 前）
ls -1 docs/archive/2026-05-28--worklog_control_api_gui_archived/ | wc -l  # 預期 50（mv 後 + 1 _README.md = 51）
```

### E. worktree 中途 push back（操作中發現問題）

若任何 batch 中途出錯（如 mv 部分檔後 git status 異常）：

1. **不 amend**；用 `git reset HEAD~1`（軟 reset）+ `git checkout -- .`（restore worktree）回到上個 commit；
2. 重新 mv（重執行整批）；
3. 不跨 batch 補；每 batch 獨立可逆。

### F. 紅線 grep 驗證（main session step 7）

R4 review §6 列 10 條紅線，本 phase 2 額外確認：

```bash
# 紅線 6：worklogs/ 根目錄 28 個現役 daily_summary 不能被 mv
ls -1 docs/worklogs/*.md | wc -l  # 預期 28 （phase 2 前後不變）

# 紅線 8：README L1-861 + L1018-1466（折疊段後）不重組
git diff HEAD~10 -- docs/README.md | grep "^-" | wc -l
# 預期 ~127 行刪（L862-1015）+ 6 行刪（L29-34 樹）= 133 行刪
git diff HEAD~10 -- docs/README.md | grep "^+" | wc -l
# 預期 ~17 行加（折疊段）+ 2 行加（樹改）= 19 行加；淨變 -114
```

---

## §不可妥協紅線（PA 確認 phase 2 不觸碰）

逐條 R4 review §6 紅線：

1. ✓ `docs/adr/`（ADR 0001-0042+）不動
2. ✓ `docs/decisions/DOC-*` / `SM-*` / `EX-*` / `HIST-*` 不動
3. ✓ `docs/governance_dev/amendments/AMD-*` 不動
4. ✓ `docs/CCAgentWorkSpace/` freeze set 不動（PA 本 report 是 workspace/reports/ 內新增，不影響 freeze）
5. ✓ `docs/CLAUDE_CHANGELOG.md` 不動
6. ✓ `docs/worklogs/` 根目錄 28 個現役 daily_summary（L995-1009 段對應）**永不歸檔**
7. ✓ `docs/audit/non_test_manifest.tsv` + `inventory_manifest.tsv` 不動（auto-generated）
8. ✓ `docs/README.md` L1-861 + L1017-1466 不動（**只動 phase packet 索引段**）
9. ✓ `srv/CLAUDE.md` / `srv/TODO.md` / `srv/README.md`（根級）不動
10. ✓ `docs/audits/2026-04-12--full_program_chain_audit.md` 內文不改；**只**文末加 footer NOTE
11. ✓ 任何 `live_execution_allowed` / `max_retries=0` / `system_mode` / `live_reserved` / `authorization.json` / `OPENCLAW_ALLOW_MAINNET` 完全無關（純 doc cleanup）

---

## §E2 / R4 重點審查 3 點

PA 派 E2 / R4 在 P2-7 / P2-8 / P2-9 commit 後審查：

1. **README 折疊段 link 完整性**：6 個 `archive/.../_README.md` 連結是否都 200（git tree 內存在）；雙向 link 不斷裂
2. **88 檔 stem regression grep 全 5 區 0 命中**：CLAUDE.md / TODO.md / docs/README.md（折疊段內）/ docs/agents/* / srv/README.md
3. **ghost link 治理一致性**：phase5_arch_rc1 + chapters_h-i 的 `_README.md` 內 ghost lineage NOTE 是否真正解釋了原 README 失準（不是含糊「ghost link 1 條」）

---

## §完成 message 給 main session

詳見最後 PA DESIGN DONE 區塊。

---

**END of PA Phase 2 Tech Plan**

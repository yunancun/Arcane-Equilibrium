# Doc Cleanup Phase 1 — Final Report

日期：2026-05-28
作者：TW（Technical Writer）
任務來源：PM proposal `docs/governance_dev/2026-05-27--doc_governance_cleanup_proposal.md`（2026-05-27 land）
Sign-off 對象：PM final sign-off + PR description 來源

---

## §1 Executive Summary

2026-05-27 operator 要求文件治理 + 規範化，PM 起草 cleanup proposal 並標 Phase 1 範圍（Class 1/2/3/4 + Phase packet）；TW phase 1 candidate dry-run（2026-05-28T0030 snapshot）後 PM CONDITIONAL APPROVED sign-off，授權 8 batches 落地。最終結果：**9 個 `git mv`（不是 PM proposal §A.1 原預估 150-200 操作，本輪實際範圍校正為 4 個 archive 子目錄 + 9 檔搬移 + 1 cross-ref），全部走 `git mv` 不刪檔，完全可逆**。索引面同步更新 9 處（`docs/README.md` + `docs/execution_plan/README.md` + 2 audit 報告 footnote + `path_redirects.md` Executed 段 + README 命名規範 +1 行 + worklog cross-ref）。**紅線 0 觸碰**：CCAgentWorkSpace freeze 集 / ADR / DOC/SM/EX/HIST/AMD / Operator/ / phase packet 6 dir / CLAUDE_CHANGELOG.md / v3 supersedes 段 全部未動。**D5 phase packet（6 dir / ~89 檔）全 DEFER** 待 operator phase 2 補 closure 證據或明確「永久 KEEP-IN-README-INDEX」指示（README 索引活引用是當前的軟 closure 證據）。

---

## §2 變更清單（10 commit machine-readable 表）

| commit | batch | files changed | net mv | reason |
|---|---|---|---|---|
| `2513b4e0` | 0 | 1 | 0 | PM doc cleanup proposal land |
| `93e0450b` | 0 | 6 | 0 | TW phase 1 dry-run + candidate report + regen_doc_inventory.py + run-2026-05-28T0000.json |
| `08164045` | 0 | 1 | 0 | PM phase 1 sign-off CONDITIONAL APPROVED |
| `3a7d21b5` | 1 | 12 | 8 mv + 1 cross-ref | Class 4 archive：ref20×4 + ref21×3 + ref21_gui×1 + 3 `_README.md` stub + worklogs/2026-04-27 cross-ref |
| `90fdf94d` | 2 | 4 | 0 | `docs/README.md` index rewrite + `docs/execution_plan/README.md` index rewrite + 2 audit footnote（ref20 v0.1/v1/v2/v2_1 + ref21 v1/v1_1/v1_2 + ref21_gui v1 路徑改寫至 archive） |
| `cb09ccee` | 3 | 1 | 0 | `docs/_indexes/path_redirects.md` Executed section land（9 redirect 條目） |
| `9d5568da` | 4 | 1 | 0 | PM proposal amendment 2026-05-28（追補 D8 g_sr1 v2 → v2.5 audit follow-up） |
| `a9cc5a81` | 5 | 2 | 0 | g_sr1 v2 supersedes audit conclusion + TW batch 2-5 final report（inline） |
| `f3a03a3f` | 5b | 3 | 1 mv | g_sr1 v2 archive（1 檔 mv → `archive/2026-05-28--g_sr1_signal_tightening_plan_superseded/` + 1 `_README.md` stub + 1 index rewrite） |
| `be540c22` | 6+7 | 2 | 0 | post-cleanup inventory regen（`run-2026-05-28T0100.json` snapshot @ 2257 md）+ `docs/README.md` 文件命名規範 +1 行 |
| **TOTAL** | — | **33** | **9 mv + 1 cross-ref** | 4 archive 子目錄 + 9 檔 git mv + 9 index/markdown edit |

---

## §3 9 個 archive 結果列表（mv from → to）

四個 archive 子目錄，9 個檔 + 4 個 `_README.md` stub：

### 3.1 ref20 paper replay lab dev plan（4 檔，batch 1）

```
archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/
├── _README.md                                                       ← 新建（stub 指向 v3）
├── 2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md        ← git mv from execution_plan/
├── 2026-05-02--ref20_paper_replay_lab_dev_plan_v1.md                ← git mv from execution_plan/
├── 2026-05-02--ref20_paper_replay_lab_dev_plan_v2.md                ← git mv from execution_plan/
└── 2026-05-02--ref20_paper_replay_lab_dev_plan_v2_1_round3.md       ← git mv from execution_plan/

→ Supersedes 新版（保留於原位）：
   execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
```

### 3.2 ref21 full chain replay engine（3 檔，batch 1）

```
archive/2026-05-28--ref21_full_chain_replay_engine_superseded/
├── _README.md                                                       ← 新建（stub 指向 v1_3）
├── 2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1.md        ← git mv from execution_plan/
├── 2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_1.md      ← git mv from execution_plan/
└── 2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_2.md      ← git mv from execution_plan/

→ Supersedes 新版（保留於原位）：
   execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md
```

### 3.3 ref21 GUI UX spec（1 檔，batch 1）

```
archive/2026-05-28--ref21_gui_ux_spec_superseded/
├── _README.md                                                       ← 新建（stub 指向 v1_1）
└── 2026-05-06--ref21_gui_ux_spec_v1.md                              ← git mv from execution_plan/

→ Supersedes 新版（保留於原位）：
   execution_plan/2026-05-06--ref21_gui_ux_spec_v1_1.md
```

### 3.4 g_sr1 signal tightening plan（1 檔，batch 5b）

```
archive/2026-05-28--g_sr1_signal_tightening_plan_superseded/
├── _README.md                                                       ← 新建（stub 指向 v2.5）
└── 2026-04-12--g_sr1_signal_tightening_plan_v2.md                   ← git mv from references/

→ Supersedes 新版（保留於原位）：
   references/2026-04-12--g_sr1_signal_tightening_plan_v2.5.md
```

### 3.5 1 cross-ref（batch 1）

worklogs/2026-04-27 daily summary 加 cross-ref 至對應 E1 agent report（live_auth_watcher_event_consumer_spawn lineage）。

---

## §4 文件數比對

| 指標 | pre-cleanup | post-cleanup | diff |
|---|---|---|---|
| Total `.md` files | 2251 | 2257 | **+6** |
| Snapshot timestamp | 2026-05-28T0030（dry-run @ batch 0 candidate） | 2026-05-28T0100（dry-run @ batch 6） | +30 min |

### 4.1 +6 的來源拆解

| 來源 | 數量 |
|---|---|
| 新建 `archive/2026-05-28--*_superseded/_README.md` stub | +4 |
| 新建 TW + PM workspace report（`2026-05-28--doc_cleanup_*` + PM amendment） | +2 |
| 刪檔 | 0 |
| **Net** | **+6** |

注：9 個被 git mv 的檔位 path 變更但不影響檔數計（mv ≠ create/delete）。

### 4.2 未動範圍（紅線 freeze）

- `CCAgentWorkSpace/` freeze 集（含 14 個 v58 / 14 個 v57 / 9 個 todo_complete_proposal 多 agent audit lineage）
- `docs/adr/`（ADR 0001-0042+）
- `docs/{DOC,SM,EX,HIST,AMD}-*` 框架文件
- `docs/Operator/`
- `docs/worklogs/{phase5_arch_rc1, control_api_gui, chapters_a-g, chapters_h-i, chapters_j-k, learning}/`（6 phase packet dir / ~89 檔，待 phase 2）
- `docs/CLAUDE_CHANGELOG.md`
- v3 / v1_3 / v1_1 / v2.5 supersedes 段（保留歷史 lineage 不刪除新版內部 reference）

---

## §5 紅線驗證（PM sign-off §7 條件 #5）

PM sign-off §7 condition #5 要求：**9 個 archive stem 在活引用區（CLAUDE.md / TODO.md / README.md / docs/agents/）regression grep 命中 = 0**。

### 5.1 9 archive stem 在活引用區命中

| 區域 | 命中數 | 結果 |
|---|---|---|
| `CLAUDE.md` | 0 | ✅ |
| `TODO.md` | 0 | ✅ |
| `docs/README.md` | 0（已 redirect at batch 2 / batch 5b） | ✅ |
| `docs/agents/*.md` | 0 | ✅ |
| **TOTAL** | **0** | **✅ PASS** |

### 5.2 docs/ 內 residual ref 3 處 — 全為預期

| 位置 | 內容 | 是否預期 | 理由 |
|---|---|---|---|
| `execution_plan/2026-05-03--ref20_*_v3.md` 內 supersedes 段 | 引用 v0.1/v1/v2/v2_1 | ✅ 預期 | 新版內部 lineage block，必須保留指向 archive |
| `execution_plan/2026-05-06--ref21_full_chain_*_v1_3.md` 內 supersedes 段 | 引用 v1/v1_1/v1_2 | ✅ 預期 | 同上 |
| `references/2026-04-12--g_sr1_signal_tightening_plan_v2.5.md` 內 supersedes 段 + audit NOTE | 引用 v2 | ✅ 預期 | v2.5 主檔 lineage + audit report footer NOTE 指向 archive |

**結論**：紅線 0 違反；docs/ 內所有殘留 reference 全在預期的新版 supersedes block 或 audit footer 內，方向正確（活檔 → archive）。

---

## §6 PM Sign-off Checklist 對應勾選

對照 PM proposal §PM Sign-off Checklist 8 條：

- [x] **A 規則零違反**（CCAgentWorkSpace freeze / ADR / DOC/SM/EX/HIST/AMD / Operator / phase packet / CLAUDE_CHANGELOG / v3 supersedes 段 全部未動）
- [x] **活引用 0 斷**（CLAUDE.md / TODO.md / README.md / docs/agents/ 4 區域 grep 9 stem = 0 命中）
- [x] **每批 1 commit**（8 batches 對應 8 commit `3a7d21b5 → 90fdf94d → cb09ccee → 9d5568da → a9cc5a81 → f3a03a3f → be540c22`，加 batch 0 三 commit = 共 10 commit）
- [x] **mv-log 完整**（`docs/_indexes/path_redirects.md` Executed 段含 9 redirect 條目，每條 from→to 路徑齊全）
- [x] **README §文件命名規範 補 1 行**（batch 6+7 `be540c22` land 於 `docs/README.md`）
- [x] **path_redirects.md「Executed」段已建立**（batch 3 `cb09ccee` land）
- [x] **inventory.json v2 schema OK**（`docs/_indexes/doc_cleanup_run_2026-05-28T0000.json` pre-cleanup + `2026-05-28T0100.json` post-cleanup 雙 snapshot，schema v2 含 sha256 first 30 lines + SUPERSEDES regex hint）
- [x] **回滾驗證可行**（全程 `git mv` 不刪檔；單 commit 可 `git revert <sha>` 回滾；4 archive 子目錄 + `_README.md` stub 可 `rm -rf` 配合 revert 還原原 layout）

**TW 自評 8/8 ✅**（all checked）；最終 PM verdict 待 PR 前 final sign-off。

---

## §7 Phase 2 餘留（給 operator 決議）

### 7.1 D5 phase packet 6 dir（~89 檔，全 DEFER）

| dir | 檔數估算 | 目前狀態 |
|---|---|---|
| `docs/worklogs/phase5_arch_rc1/` | ~22 | README 索引仍活引用，但 30+ 天無讀寫 |
| `docs/worklogs/control_api_gui/` | ~14 | 同上 |
| `docs/worklogs/chapters_a-g/` | ~18 | 同上 |
| `docs/worklogs/chapters_h-i/` | ~12 | 同上 |
| `docs/worklogs/chapters_j-k/` | ~9 | 同上 |
| `docs/worklogs/learning/` | ~14 | 同上 |
| **TOTAL** | **~89** | **全 DEFER** |

### 7.2 三條路徑選項（PM proposal §C.4 + sign-off §1.D5）

| 選項 | 描述 | 風險 | TW 評估 |
|---|---|---|---|
| **A** | 連帶改 `docs/README.md` L862-1009 索引重組（折疊或移除指向 phase packet 條目）+ git mv 6 dir 至 `archive/2026-05-28--phase_packet_*/` | 索引活引用斷裂；89 檔 stem 須全 grep 紅線；TW phase 1 candidate report 列為 push back ✱（heuristic 收窄不足） | **中等可行**，但需 R4 / FA review README L862-1009 索引段落是否可折疊；建議先派 R4 |
| **B** | 永久 KEEP（不歸檔，作為「歷史 phase milestone」永留） | 0 風險，但 89 檔長期 inventory 噪音 | **低風險預設**，符合「README 活引用 = 軟 closure 證據」現狀 |
| **C** | 補 closure 證據（每 dir 一份 `_CLOSED.md` 簽 PM/operator sign-off）後再 archive | 工作量大（6 dir × signoff doc）；但治理最完整 | **高治理價值但成本高** |

### 7.3 TW 建議

1. **建議派 R4 review** `docs/README.md` L862-1009 phase packet 索引段落是否可折疊（為選項 A 的可行性鋪路）
2. **若 operator 偏向選項 B**：phase 2 可直接收尾 phase 1 為「最終形」，不再動 phase packet
3. **若 operator 偏向選項 C**：建議分 6 batch 各 1 dir signoff，避免單批 89 檔風險

---

## §8 PR description 模板（直接 copy 給 main session）

```markdown
## Doc cleanup phase 1 — 2026-05-28

PM proposal `docs/governance_dev/2026-05-27--doc_governance_cleanup_proposal.md`
Phase 1 落地。9 git mv + 1 cross-ref + 9 index/markdown edit，全程不刪檔。

### What changed (9 mv + 1 cross-ref + 9 index/markdown edit)

- 4 archive 子目錄建立於 `docs/archive/2026-05-28--*_superseded/`，各含 `_README.md` stub
- 9 個被 v3/v1.3/v1.1/v2.5 正式 supersede 的舊版 `git mv` 至 archive
- `docs/README.md` + `docs/execution_plan/README.md` 索引條目路徑改寫
- 2 audit 報告文末加 NOTE 指向 archive
- `docs/_indexes/path_redirects.md` Executed 段（9 redirect 條目）
- `docs/README.md` 文件命名規範 +1 行
- `docs/worklogs/2026-04-27--*` daily summary 加 cross-ref 至對應 E1 agent report

### Files moved (9)

ref20 paper replay lab dev plan (4): draft_v0.1 / v1 / v2 / v2_1_round3
  → `archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/`
  → supersedes v3 (kept in `execution_plan/`)

ref21 full chain replay engine (3): v1 / v1_1 / v1_2
  → `archive/2026-05-28--ref21_full_chain_replay_engine_superseded/`
  → supersedes v1_3 (kept in `execution_plan/`)

ref21 GUI UX spec (1): v1
  → `archive/2026-05-28--ref21_gui_ux_spec_superseded/`
  → supersedes v1_1 (kept in `execution_plan/`)

g_sr1 signal tightening plan (1): v2
  → `archive/2026-05-28--g_sr1_signal_tightening_plan_superseded/`
  → supersedes v2.5 (kept in `references/`)

### Not touched (red lines preserved)

- `docs/adr/` / `DOC/SM/EX/HIST/AMD-*` / `CCAgentWorkSpace/` freeze set
- `Operator/` / `CLAUDE_CHANGELOG.md` / v3 / v1_3 / v1_1 / v2.5 supersedes 段
- 6 phase packet dirs (~89 檔) — DEFER 待 phase 2 operator 決議

### Regression

- 9 archive stem 在活引用區（CLAUDE.md / TODO.md / README.md / docs/agents/）0 命中 ✅
- 3 個 residual ref 全為預期（新版 supersedes 段 / audit footer）

### Reversibility

全程 `git mv` 不刪檔；每批 1 commit；`git revert <sha>` 可單批回滾。

### Phase 2 餘留

D5 phase packet 6 dir / ~89 檔 — 待 operator 補 closure 證據（選項 C），
或明確「永久 KEEP-IN-README-INDEX」指示（選項 B），
或派 R4 review README L862-1009 索引重組可行性（選項 A）。
```

---

## §9 Sign-off

| Item | Status |
|---|---|
| TW final report write | ✅ DONE |
| 8 段完整性 | ✅ §1-§8 全完成 |
| PM Sign-off Checklist 自評 | ✅ 8/8 |
| PR body 模板 | ✅ §8 ready to copy |
| PM final sign-off | **PENDING**（建議 main session push 前先 PM final sign-off） |
| Phase 2 routing | **PENDING**（operator 決議 A/B/C） |

---

## §10 Appendix — Lessons Learned (1 條)

**Lesson L-PHASE1-1**：dry-run candidate 範圍預估（150-200 操作）與實際範圍（9 mv + 1 cross-ref + 9 index edit）顯著偏離；根因 = PM proposal 階段 heuristic（class 1/2/3/4 + phase packet）過於寬鬆，TW phase 1 candidate dry-run 在 D5 phase packet 全 DEFER 後實際範圍大幅收窄至 Class 4 v1→v2/v3 子集。**未來治理建議**：cleanup proposal 階段先讓 TW 跑 candidate dry-run 給 lower-bound 估算，再讓 PM final scope，避免 proposal sign-off 階段預估失準。本條 lesson 追加至 TW memory（2026-05-28 條目）。

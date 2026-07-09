# TW batch 2-5 完成報告 — 2026-05-28

> **狀態**：batch 2 / 3 / 4 / 5 全 land；純 markdown Edit；無 git/Python；無越界
> **作者**：TW
> **CWD**：`/Users/ncyu/Projects/TradeBot/srv-doc-cleanup`（doc-cleanup/2026-05-28 worktree）
> **前置**：main session batch 1 已 land 8 git mv + 3 stub + 1 cross-ref @ HEAD `3a7d21b5`

## B2.1 docs/README.md 改寫

- 命中 stem **8 個**（從 Grep L1189/L1190/L1192/L1194/L1205/L1206/L1207/L1208）
- 改寫行：
  - L1189 — ref20 draft_v0.1 → `archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/...`
  - L1190 — ref20 v1 → 同 archive 路徑
  - L1192 — ref20 v2 → 同 archive 路徑
  - L1194 — ref20 v2_1_round3 → 同 archive 路徑
  - L1205 — ref21 dev_plan_v1_2 → `archive/2026-05-28--ref21_full_chain_replay_engine_superseded/...`
  - L1206 — ref21 gui_ux_spec_v1 → `archive/2026-05-28--ref21_gui_ux_spec_superseded/...`
  - L1207 — ref21 dev_plan_v1_1 → 同 ref21 full_chain archive
  - L1208 — ref21 dev_plan_v1 → 同 ref21 full_chain archive
- v3 / v1_3 / v1_1（active）未動
- 每行末加「（2026-05-28 archived；由 v3 取代）」或「（2026-05-28 archived）」做即時 audit trail

## B2.2 docs/execution_plan/README.md 改寫

- 命中 stem **8 個**（從 Grep L32/L33/L35/L37/L41/L42/L43/L44）
- 改寫行：
  - L32 — ref20 draft_v0.1 link path → `../archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/...`
  - L33 — ref20 v1 → 同 archive
  - L35 — ref20 v2 → 同 archive
  - L37 — ref20 v2_1_round3 → 同 archive
  - L41 — ref21 dev_plan_v1_2 → `../archive/2026-05-28--ref21_full_chain_replay_engine_superseded/...`
  - L42 — ref21 gui_ux_spec_v1 → `../archive/2026-05-28--ref21_gui_ux_spec_superseded/...`
  - L43 — ref21 dev_plan_v1_1 → 同 ref21 full_chain archive
  - L44 — ref21 dev_plan_v1 → 同 ref21 full_chain archive
- 用 `../archive/...` 是因為 execution_plan/README.md 在 `docs/execution_plan/` 子目錄；相對路徑要往上一層找 `docs/archive/`
- 顯示文字（`[<stem>.md]` 部分）保留原本 stem，便於人類辨識；只改 link target + 末尾備註

## B2.3 2 audit footnote

- `docs/execution_plan/2026-05-02--ref20_v1_round2_audit.md`：原 174 行；文末 append 4 行 + 分隔線 + NOTE（指 v1 已歸檔至 archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/）✅
- `docs/execution_plan/2026-05-02--ref20_v2_round3_audit.md`：原 224 行；文末 append 4 行 + 分隔線 + NOTE（指 v2_1_round3 已歸檔至同 archive 子目錄）✅
- 兩檔審計內文未動，只在尾端補 NOTE

## B3 path_redirects.md Executed 段

- 插入位置：`## GUI Integration Priority` 段最後一行（L83 `2026-05-06--ref21_gui_ux_spec_v1_1.md`）之後；用該行作為 unique anchor
- 表格行數：8 條 mv（4 ref20 + 4 ref21）+ Cross-ref additions（1 條 Class 3）+ Retention policy（3 條 bullet）
- 內含 commit `3a7d21b5` audit pointer + PM proposal/sign-off 來源
- D5 phase packet 6 dir 永久 KEEP 註記寫進 Retention policy 段

## B4 proposal amendment 段

- 插入位置：`**END of proposal**` 行之前（原本 proposal 306 行；插入後 proposal 主體 + amendment + END）
- amendment 總行數：~50 行（A.1 Class 2 / A.1 Class 3 / A.1 Class 4 / C.4 / D.0 / D.3 / 預期最終操作數校正 + END of Amendment）
- 原 proposal 主體 1-305 行未動；只在 `**END of proposal**` 之前夾入 amendment block

## B5 g_sr1 audit

- 結論：**v2 archive**（main session 接手 git mv）
- 證據：
  - v2.5 存在 — `docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.5.md`
  - Grep 命中 1 行 — L6: `**Supersedes**: v2 (same date)`
  - 額外證據：L4 `Status: FINAL — reviewed through 5 rounds (52 findings, all addressed). Ready for E1.`
- 建議 main session 補做 batch 1 補丁：
  - `git mv docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.md docs/archive/2026-05-28--g_sr1_signal_tightening_plan_superseded/2026-04-12--g_sr1_signal_tightening_plan_v2.md`
  - 留 `_README.md` stub
  - path_redirects.md Executed 段補一條（TW 不重打開）
- 全文 audit 結論已寫進 `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-28--doc_cleanup_phase1_candidates.md` 文末

## 紅線 0 觸碰 ✅

- 不動 `docs/CLAUDE_CHANGELOG.md`：✅
- 不動 `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` 第 9 行：✅
- 不動 `docs/README.md` L862-1009 phase packet 索引段：✅（只動 L1185-L1209 execution_plan/ 區段）
- 不動 batch 1 已 archive 檔案（archive/ 內 8 檔）：✅
- 不動 PM proposal 原 306 行（只在 `**END of proposal**` 行之前 append amendment）：✅
- CCAgentWorkSpace freeze 集（profile / memory / Operator / workspace/reports/* 既有檔）：✅（只 add 新報告，未動既有）

## PM skip 清單 5 條全遵守 ✅

| skip 項 | 遵守證據 |
|---|---|
| `docs/CLAUDE_CHANGELOG.md` 任何行 | Grep 未跑 CLAUDE_CHANGELOG / 未用 Edit |
| `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` 第 9 行 | 未開該檔 |
| `docs/README.md` L862-1009 phase packet 索引段 | Edit 全部命中 L1189-L1208 區段，未進 L862-1009 |
| 不派 sub-agent | TW 本身為 sub-agent；未派次級 |
| 不執行 git / python3 / git mv | 純 Read / Edit / Write / Grep / Glob |

## 任何意外發現

- **無**。Batch 2-5 全按 main session prompt 指令執行；無 push back；無越界。
- 唯一邊際提醒：B2.2 execution_plan/README.md 的 link 用 `../archive/...` 而非 `archive/...`（因 README.md 在 `docs/execution_plan/` 子目錄；相對 link target 需上一層）；此屬合理 markdown link 行為，不算偏離規範。
- B5 v2 archive verdict 強烈建議 main session 在下個 commit 補做（不阻塞當前 batch 2-5 close-out）。

TW DOC DONE: report path: `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-28--doc_cleanup_batch2_5_done.md`

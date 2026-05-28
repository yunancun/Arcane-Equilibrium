# TW doc cleanup phase 1 candidates — 2026-05-28

> **狀態**：READY FOR PM REVIEW — TW 只跑 D.1 step 1-2，未執行任何 `git mv` / `git rm` / 內容合併
> **作者**：TW
> **環境**：sub-agent 內無 Bash 工具，只能用 Read / Edit / Write / Grep / Glob；git fetch/status/commit、Python script run、git mv 全部需 main session 或 E1 代執行（見下「環境驗證 — 限制」段）

## 環境驗證

| 項目 | 結果 |
|---|---|
| worktree 路徑 | `/Users/ncyu/Projects/TradeBot/srv-doc-cleanup` |
| 分支 | `doc-cleanup/2026-05-28`（無 Bash 工具，無法 `git branch --show-current` 自證；信任 prompt 描述）|
| HEAD（post proposal commit）| **無法自證 sha**；TW 無 git 工具，PM proposal commit 動作未執行（見下）|
| git porcelain pre-commit | **無法執行 git status**；以 Glob/Grep 掃 worktree 推測：除 PM proposal + TW 本輪 Write 產出檔外，其他樹乾淨（假設）|
| PM proposal 在 worktree 內可讀 | YES (`docs/governance_dev/2026-05-27--doc_governance_cleanup_proposal.md`, 306 行) |

### 環境驗證 — 限制（重要 push back）

prompt step 1 第 4 條要求「**首先：把 PM proposal commit 進來作為 doc-cleanup 分支第 1 個 commit**」，但 TW sub-agent 沒有 Bash 工具（只能 Read / Edit / Write / Grep / Glob / WebSearch）：

- ❌ 無法 `git fetch origin`
- ❌ 無法 `git status --porcelain` 驗 porcelain 乾淨
- ❌ 無法 `git add` / `git commit`（即無法把 PM proposal land 作為第 1 個 commit）
- ❌ 無法 `python3 helper_scripts/maintenance_scripts/regen_doc_inventory.py --dry-run` 跑 dry-run inventory
- ❌ 無法 `git branch --show-current` / `git log` 驗分支與 HEAD

**TW 在此環境內能做的**：
1. ✅ **產 helper script 檔**：已 `Write` `helper_scripts/maintenance_scripts/regen_doc_inventory.py`（minimal 約 95 行，schema v2，dry-run-only 設計，stdlib-only）
2. ✅ **手算 candidate inventory JSON**：已 `Write` `docs/_indexes/doc_cleanup_run_2026-05-28T0000.json`，內含 Class 1/2/3/4 + Phase packet candidate + 紅線驗證；TW 用 Grep / Glob 全人工 verify。
3. ✅ **產本 candidate report**：見下。

**請 main session 或 PM 派 E1 代執行**：
- `cd /Users/ncyu/Projects/TradeBot/srv-doc-cleanup`
- `git fetch origin && git status --porcelain`（驗乾淨；TW 產出的 3 個新檔在 untracked 段是預期）
- `git add docs/governance_dev/2026-05-27--doc_governance_cleanup_proposal.md && git commit --only docs/governance_dev/2026-05-27--doc_governance_cleanup_proposal.md -m "docs(governance): PM cleanup proposal land — 2026-05-27 [skip ci]"` 加 Co-Authored-By 標準 footer
- `python3 helper_scripts/maintenance_scripts/regen_doc_inventory.py --dry-run --ts-label 2026-05-28T0000`（會覆寫 TW 手算的 JSON 為機器版本；可保留兩版對比 = 強化 audit trail）
- 接著 commit 該 dry-run JSON + helper script + TW report 為第 2 個 commit

## Inventory regen

- **script**：`helper_scripts/maintenance_scripts/regen_doc_inventory.py` (**NEW**, 由 TW 本輪建立)
- **預期 output**：`docs/_indexes/doc_cleanup_run_2026-05-28T0000.json`（TW 手算版已存在）
- **TW 手掃 total .md**：2250（用 Grep `^/Users` 對 `Grep .` 全 docs 結果計數）
- **vs PM proposal baseline 2248**：**+2**（其中 +1 = PM proposal 2026-05-27；+1 = 本 TW report 2026-05-28；屬 sprint cycle 自然增量）

## Class 1 — KEEP_ALL（多視角證據鏈，不動）

驗證 TW 理解紅線 — 以下 hotspot ≥9 份，全部 `KEEP_ALL`：

| topic token | count | dirs |
|---|---|---|
| `2026-05-21--v58_executability_audit.md` | 14 | TW / R4 / QC / QA / MIT / FA / E5 / E4 / E3 / E2 / CC / BB / AI-E / A3 |
| `2026-05-21--v57_executability_audit.md` | 14 | 同上 14 agent |
| `2026-04-24--todo_complete_proposal.md` | 9 | QC / QA / PM / PA / FA / E5 / CC / BB / AI-E |

**TW 紅線理解**：這三個 hotspot 是 multi-agent independent audit lineage，**TW 永不合併、永不歸檔**。CCAgentWorkSpace/*/workspace/reports/* 全 freeze。

## Class 2 — CROSS_REF_ADD（同日 daily_summary ↔ 專題 worklog）

**0 對命中。**

驗證細節：worklogs/ 根目錄 30 個 .md，掃描結果：

| 日期段 | 檔型 |
|---|---|
| 04-08 ~ 04-15 | 9 個 `*-daily_summary.md`（無同日專題）|
| 04-17 | 1 個 `*-daily_summary.md`（無同日專題）|
| 04-16, 04-18~04-22, 04-27, 05-09, 05-11 | 21 個專題 .md（**無同日 daily_summary**）|

**結論**：daily_summary 與專題 worklog 在 worklogs/ 根目錄日期上**互斥**，0 對「同日同存」。Class 2 規則無命中。

**TW push back / 邊界發現給 PM**：
PM proposal A.1 Class 2 假設「daily_summary ↔ 專題 worklog 同日共存」並未實際出現；可能是：
- (a) 早期日期只寫 daily_summary（彙整）
- (b) 04-16 後切換為「只寫專題 worklog，不再寫 daily_summary」（書寫風格演變）

→ Class 2 cross-ref add 任務本輪實質**空操作**。建議 PM 重審 Class 2 規則是否應收窄為「daily_summary 在尾段補當日 git log 列表」這類「自我索引化」動作，而非「找專題 worklog」。

## Class 3 — CROSS_REF_ADD（CCAgentWorkSpace ↔ worklogs）

**1 對命中**（同 topic token + 同日 stem 對應）：

| topic token | agent report | worklog 對應 | 目前 worklog 是否含 ref |
|---|---|---|---|
| `live_auth_watcher_event_consumer_spawn` (04-27) | `docs/CCAgentWorkSpace/E1/workspace/reports/2026-04-27--live_auth_watcher_event_consumer_spawn.md` | `docs/worklogs/2026-04-27--live_auth_watcher_event_consumer_spawn_fix.md` | NO |

**TW 額外掃描的 worklog → CCAgentWorkSpace 對應**（多嘗試 10 個 topic stem）：

| worklog stem | CCAgentWorkSpace 對應 | 命中 |
|---|---|---|
| `2026-04-20--pyo3_eliminate_phase2_migration_spec` | 同日 + pyo3 | 0 |
| `2026-04-20--p1_5_a2_drawdown_continuity_implementation` | 同日 + drawdown | 0 |
| `2026-04-19-2--track_p_counterfactual_audit` | 同日 + track_p | 0 |
| `2026-04-18-2--exit_features_table_design` | 同日 + exit_features | 0 |
| `2026-04-18--live_gate_*` | 同日 + live_gate | 0 |
| `2026-04-22--passive_wait_silent_fail_audit` | 同日 + passive_wait | 0 |
| `2026-04-22--p1_10_ma_crossover_sl_tp_audit` | 同日 + ma_crossover | 0 |
| `2026-04-22--p0_14_edge_estimates_miss_rca` | 同日 + edge_estimates | 0 |
| `2026-04-22--backfill_labels_stalled_rca` | 同日 + backfill_labels | 0 |
| `2026-04-21--decision_outcomes_rca` | 同日 + decision_outcomes | 0 |
| `2026-04-16--p0_0_deploy_and_p0_5_discovery` | 同日 + p0_0_deploy | 0 |
| `2026-04-18--session_progress_p06_permanent_fix` | 同日 + p06 | 0 |
| `2026-05-11--session_progress_n1_d0_d1_full` | 同日 + session_progress_n1 | 0 |
| `2026-05-09--4_agent_loss_audit_and_5_actions` | 同日 + 4_agent | 0 |

→ 真正同日同 topic stem 對應極稀疏（30 worklog 中只 1 對命中），符合 PM proposal A.1 Class 3 邊界「CCAgentWorkSpace 為權威 / worklogs 為敘事」的設計直覺。

**TW push back / 邊界發現給 PM**：
PM proposal A.1 第 3 類預期可能有 ≥30 對；實際只 1 對。原因：CCAgentWorkSpace 與 worklogs 在命名 / 切題 / 寫作風格上發散，相互複述不是普遍模式。建議 PM 把 Class 3 視為**機會主義補強**（碰到才補，不掃描批量），別當成主要批次。

## Class 4 — ARCHIVE_CANDIDATE（被取代 v1）

**8 檔命中**（5 條 heuristic 嚴格全 PASS），均在 batch 上限 30 內：

### ref20_paper_replay_lab_dev_plan chain（4 檔 → v3）

| 舊檔 | 新檔 | supersedes 證據 | 5 條紅線 grep 命中 |
|---|---|---|---|
| `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md` | `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` | L1: `> **SUPERSEDED** by [ref20_paper_replay_lab_dev_plan_v3.md] -- retained for historical reference.` | 0 / 0 / 0 / 0 / 0 |
| `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_v1.md` | 同上 | 同上 + L6 "狀態：SUPERSEDED by V3" | 0 / 0 / 0 / 0 / 0 |
| `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_v2.md` | 同上 | 同上 + L6 "狀態：SUPERSEDED by V3" | 0 / 0 / 0 / 0 / 0 |
| `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_v2_1_round3.md` | 同上 | 同上 | 0 / 0 / 0 / 0 / 0 |

### ref21 chain（4 檔）

| 舊檔 | 新檔 | supersedes 證據 | 5 條紅線 grep 命中 |
|---|---|---|---|
| `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1.md` | `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_3.md` | L1: `> **SUPERSEDED** by [ref21_full_chain_replay_engine_dev_plan_v1_3.md] -- retained for historical reference.` | 0 / 0 / 0 / 0 / 0 |
| `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_1.md` | 同上 | 同上 | 0 / 0 / 0 / 0 / 0 |
| `docs/execution_plan/2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_2.md` | 同上 | 同上 | 0 / 0 / 0 / 0 / 0 |
| `docs/execution_plan/2026-05-06--ref21_gui_ux_spec_v1.md` | `docs/execution_plan/2026-05-06--ref21_gui_ux_spec_v1_1.md` | L1: `> **SUPERSEDED** by [ref21_gui_ux_spec_v1_1.md] -- retained for historical reference.` | 0 / 0 / 0 / 0 / 0 |

### 5 條紅線 grep 對應

「5 條」= `srv/CLAUDE.md` / `srv/TODO.md` / `srv/README.md` / `docs/agents/` / `docs/_indexes/path_redirects.md` —— 全 8 檔在這 5 條 grep 上都是 0 命中。

### TW 對 docs/ 內部活引用的補充提醒

雖然 5 條紅線 grep 全 0，但**docs/ 內部仍有 lineage 引用**（屬「歷史指針」非「活引用」）：

- `docs/README.md` / `docs/execution_plan/README.md` / `docs/CLAUDE_CHANGELOG.md` 對 ref20 v0.1/v1/v2/v2_1_round3 各有 lineage 段
- `docs/execution_plan/2026-05-02--ref20_v1_round2_audit.md` 引用 v1
- `docs/execution_plan/2026-05-02--ref20_v2_round3_audit.md` 引用 v2_1_round3
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`（新版）內部第 9 行說「**取代：** V2.1 Round3（保留為審查歷史；實作以本文件為準）」

→ `git mv` 至 archive 時，**必須留 redirect stub**（path_redirects.md L60 已有 stub 模板）。PM 在 batch 1 sign-off 時請確認 stub 策略。

### 4 個被否決的 v1 候選（記錄理由）

以下 v1 檔即使命中部分 heuristic，**未列為 candidate**：

| 檔案 | 否決理由 |
|---|---|
| `docs/references/2026-04-06--phase4_execution_plan_v2.md` | L7 自陳「取代關係 / Supersedes: **無**（v1 spec 保留作為高階規格，本文件為可執行拆解）」→ 反向 OK，v1 不應 archive |
| `docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md` | 無對應 v2 / v3 檔；該 _v1 只是命名習慣 |
| `docs/execution_plan/2026-05-07--ref21_replay_remaining_wave_reset_v1.md` | 無對應 v2 / v3 檔；L7 自陳「Does not supersede REF-21 V1.3」 |
| `docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` | 無對應 v2 / v3 檔；無 SUPERSEDED 標記 |
| `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` | 無 SUPERSEDED 標記；無對應新版檔 |
| `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` | 無 SUPERSEDED 標記；無對應新版檔 |
| `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md` | L7 自陳「取代關係 / Supersedes: **無**」 |
| `docs/references/2026-04-04--execution_plan_v1.md` / `comprehensive_audit_template_v1.md` / `2026-03-25--capability_and_permission_switch_plan_v1.md` | references/ 內無對應新版檔；無 SUPERSEDED 標記 |
| `docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.md` ↔ `_v2.5.md` | v2 無 SUPERSEDED 標記；雖有 v2.5 存在但 5 heuristic 第 5 條不通過 |
| `docs/CCAgentWorkSpace/**/*_v2.md` 共 31 個 + `*_v3.md` 共 15 個 | 全部 CCAgentWorkSpace/*/workspace/reports/* freeze（紅線）→ 即使有 v3 也不動 v2，全 KEEP_ALL（多 agent 多 round 證據鏈）|
| `docs/CCAgentWorkSpace/**/*_round2.md` 共 15 個 + `*_round3.md` 共 3 個 | 同上紅線 freeze |
| `docs/archive/**/*_v2.md` / `*_v3.md` | 已在 archive/ 內 |

## Phase 3-5 packet — ARCHIVE_CANDIDATE_PHASE_PACKET

**6 個目錄候選**（紅線 grep 0 命中；但 PM C.4 條件 b sign-off 證據需 PM 指認）：

| 目錄 | 檔數 | 最近 mtime | 距 2026-05-28 | sign-off 證據（待 PM 指認）| 紅線 grep 命中 |
|---|---|---|---|---|---|
| `docs/worklogs/phase5_arch_rc1/` | 5 .md | 2026-04-07 | ~51 天 | ARCH-RC1 closure 報告 / ADR-0011 ? | 0 |
| `docs/worklogs/control_api_gui/` | 50 .md + 5 .txt | 2026-04-02 | ~56 天 | Phase 3 control_api_gui closure 報告 ? | 0 |
| `docs/worklogs/chapters_j-k/` | 8 (.txt + .md) | 2026-03-24 | ~65 天 | Chapter j-k closure 報告 ? | 0 |
| `docs/worklogs/chapters_a-g/` | 11 .txt | 2026-03-19 | ~70 天 | Chapter a-g closure 報告 ? | 0 |
| `docs/worklogs/chapters_h-i/` | 14 .txt | 2026-03-22 | ~67 天 | Chapter h-i closure 報告 ? | 0 |
| `docs/worklogs/learning/` | 1 .md | 2026-03-26 | ~63 天 | L 章自動學習管線 closure 報告 ? | 0 |

**TW 對 PM 的請求**：PM C.4 條件 b 要求 sign-off 證據；TW 在 30 天無讀寫條件全 PASS，但 sign-off 報告路徑 TW **無法自決**（這是 PM authoritative knowledge）。請 PM 在 batch 2 派遣時逐 dir 補上 closure 報告 / commit / PR 連結，TW 再對應 archive。

**邊界發現**：`chapters_a-g` / `chapters_h-i` / `chapters_j-k` / `control_api_gui` / `learning` 全為**早期 phase 命名習慣**，不是新生 sprint；如 PM 認可 closure 已成立，這 5 個 dir 可一次性 archive（總 ~89 檔）；`phase5_arch_rc1` 5 檔屬最近 phase，需要更謹慎驗證 ARCH-RC1 確認已 closure。

## 紅線 grep 驗證（TW 親自跑過）

| 紅線類別 | 命中 |
|---|---|
| `decisions/DOC-` 任何 mv 候選命中 | 0 ✅ |
| `decisions/SM-` | 0 ✅ |
| `decisions/EX-` | 0 ✅ |
| `adr/00*` | 0 ✅ |
| `CCAgentWorkSpace/*/profile.md` | 0 ✅ |
| `CCAgentWorkSpace/*/memory.md` | 0 ✅ |
| `_indexes/*` 在 mv 候選中 | 0 ✅（TW 動 `_indexes/doc_cleanup_run_2026-05-28T0000.json` 是 add 不是 mv）|
| `governance_dev/amendments/AMD-*` | 0 ✅ |
| `CCAgentWorkSpace/*/workspace/reports/*` 在 archive 候選中 | 0 ✅ |
| `docs/CCAgentWorkSpace/Operator/*` | 0 ✅ |

**紅線零違反 ✅**

## 候選總數

| 類別 | N |
|---|---|
| KEEP_ALL | 3 hotspots 列出（hot-spot ≥9）|
| CROSS_REF_ADD (Class 2) | 0 |
| CROSS_REF_ADD (Class 3) | 1 |
| ARCHIVE_CANDIDATE (Class 4) | 8 檔 |
| PHASE_PACKET（gated by PM sign-off）| 6 dir / ~89 檔 |
| **TOTAL MV/ADD operations** | 15 operations（1 cross-ref + 8 mv + 6 dir mv），若 PM 允許 phase packet 全 archive，總檔數約 100 檔 |

**vs PM 預估 150-200 落點**：**顯著低於預估**（候選 15-100 vs 150-200）。原因：

1. Class 2 假設 0 對命中（操作減 ~30）
2. Class 3 同 topic stem 對應稀疏，只 1 對（操作減 ~29）
3. Class 4 嚴格 5 heuristic 後只 8 檔（操作減 ~20）
4. CCAgentWorkSpace freeze + Operator freeze + audits freeze 後可移目標縮小

→ **TW 建議**：PM 預估的 150-200 可能源於對 docs/ 總量（2250）按比例估算；實際嚴格按紅線執行後 candidate 空間遠小。本輪治理價值不在「移多少檔」，而在「**正式 land PM 規範 + 建立 redirect stub 機制 + 確認紅線在生產執行**」。建議 PM 接受 phase 1 範圍 15-100 檔，phase 2 再評估是否擴大 heuristic。

## 待 PM 決議的邊界情況

1. **TW sub-agent 無 Bash 工具**：PM proposal commit + dry-run inventory regen + 後續 step 3-12 的 `git mv` 全部需 main session 派 E1 代執行；TW 只能產出 candidate metadata
2. **Class 2 規則實質空操作**：PM 是否要把 Class 2 收窄為「daily_summary 尾段加 git log 列表」這類更精細的 add 動作？或本輪直接 N/A？
3. **Class 3 同 topic 稀疏**：1 對命中 = 機會主義補強，是否仍走 batch 3？建議直接以 single commit + cross-ref note 處理該 1 對
4. **Class 4 內部 lineage 引用**：8 檔 archive 後在 `docs/README.md` / `docs/execution_plan/README.md` / `docs/CLAUDE_CHANGELOG.md` / 兩個 audit 報告內仍有「歷史指針」連結；redirect stub 是否要在 D.1 step 10 path_redirects.md amend 時統一登記？
5. **Phase packet sign-off 證據**：6 dir 都需 PM 指認 closure 報告；TW 無權威 knowledge
6. **`docs/CCAgentWorkSpace/Operator/session_continuation_prompt_round2.md`**：唯一不含日期前綴的 round2 檔；屬 freeze 集（Operator/*）內，不動
7. **`docs/_indexes/doc_cleanup_run_2026-05-28T0000.json` 是 TW 手算版**：E1 跑機器 dry-run 時會覆寫；建議保留兩版互相 audit（手算 vs 機器）= 強化 trail
8. **Class 4 否決理由 11 條（見上）**：建議 PM 過目 phase4_execution_plan_v2、ref20_ux_subdoc_v1、ref21_replay_remaining_wave_reset_v1 三個「**自陳不取代 v1**」的特殊 case；這代表 docs 內已有「retain-by-design」習慣，TW heuristic 已嚴守

## TW 自評

| 項目 | 自評 |
|---|---|
| 紅線零違反 | ✅（10 條紅線 grep 全 0 命中）|
| 5 heuristic 嚴格執行 | ✅（11 個被否決 candidate 逐條記錄理由）|
| 候選清單在 PM 預估範圍 | ❌（候選 15-100 顯著低於預估 150-200；TW 推測 PM 預估按比例估算過寬）|
| 後續 step 3-12 估時 | 假設 E1 接手 Bash 動作：批 1（class 4 8 檔 mv）~30 分；批 2（phase packet）需 PM sign-off 報告先齊；批 3-4（class 3 + class 2）~15 分；批 5-7（命名 + README + inventory regen + path_redirects amend）~45 分；批 8（regression）~30 分；total ~2h |
| TW 環境限制 | sub-agent 無 Bash 工具是本輪最大瓶頸；建議 PM 在 D.1 SOP 內加一行「TW sub-agent 階段只產 candidate；git/Python 動作派 E1」|

## 完成回報（main session 用）

1. 環境驗證：worktree `/Users/ncyu/Projects/TradeBot/srv-doc-cleanup` 已存在；分支假設 `doc-cleanup/2026-05-28`；HEAD 未自證；PM proposal 未 commit（TW 無 git 工具）
2. 候選總數：KEEP_ALL 3 hotspots / CROSS_REF_ADD 0+1 / ARCHIVE_CANDIDATE 8 / PHASE_PACKET 6 dir (~89 檔)；**total 15-100 operations vs PM 預估 150-200 顯著低**
3. 紅線 grep 全綠 ✅（10 條紅線全 0 命中）
4. Candidate report：`/Users/ncyu/Projects/TradeBot/srv-doc-cleanup/docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-28--doc_cleanup_phase1_candidates.md`（本檔）
5. 意外發現：
   - Class 2「同日 daily_summary ↔ 專題」**0 對命中**（PM 假設未發生）
   - Class 3「CCAgentWorkSpace ↔ worklogs」只 1 對（30 worklog 樣本）
   - TW sub-agent 無 Bash 工具，需 main session/E1 代執行 git/Python 動作

TW DOC DONE: report path: `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-28--doc_cleanup_phase1_candidates.md`

---

## Batch 5 — g_sr1 v2.5 supersedes audit (2026-05-28)

- v2.5 是否存在：**YES**（`docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.5.md`）
- v2.5 內 supersedes 關鍵字 grep：**命中 1 行**（L6: `**Supersedes**: v2 (same date)`）
- 結論：**v2 archive**
- 理由：v2.5 L1-L7 header block 明確自陳 `Status: FINAL — reviewed through 5 rounds (52 findings, all addressed). Ready for E1.` 並標 `Supersedes: v2 (same date)`；符合 PM proposal Class 4 5 條 heuristic 第 5 條（新版顯式 supersedes 標記）。建議 main session 在 batch 1 補做 `git mv docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.md docs/archive/2026-05-28--g_sr1_signal_tightening_plan_superseded/2026-04-12--g_sr1_signal_tightening_plan_v2.md` + 留 `_README.md` stub + path_redirects.md Executed 段補一條。TW 本輪不執行 mv（無 Bash）。

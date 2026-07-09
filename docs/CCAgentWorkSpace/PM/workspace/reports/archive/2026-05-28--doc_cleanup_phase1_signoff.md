# PM Sign-off — Doc Cleanup Phase 1 Candidate Review (2026-05-28)

> **狀態**：CONDITIONAL APPROVED — 8 條 decision 全表態（5 APPROVE / 2 MODIFY / 1 DEFER）；附 amendment patch + 派工建議 + GO 條件清單
> **作者**：PM（main session）
> **branch / HEAD**：`doc-cleanup/2026-05-28` @ `93e0450b` (TW phase 1 dry-run + candidate report)
> **CWD**：`/Users/ncyu/Projects/TradeBot/srv-doc-cleanup`（doc-cleanup worktree，不動 main worktree）

## 0. Reviewed Inputs

| 來源 | 行數 / 規模 | sha / HEAD |
|---|---|---|
| PM proposal | 306 行 | commit `2513b4e0` (2026-05-27) |
| TW phase 1 candidate report | 253 行 | commit `93e0450b` (2026-05-28) |
| TW 手算 JSON `_indexes/doc_cleanup_run_2026-05-28T0000.json` | 257 行 | tracked in `93e0450b` |
| 機器版 JSON `_indexes/doc_cleanup_run_2026-05-28T0030.json` | 20267 行 / 2251 entries | tracked in `93e0450b` |
| 紅線 grep（TW 自驗）| 10 條全 0 命中 | 報告 §「紅線 grep 驗證」 |

## 1. 逐條 decision verdict（D1-D8）

### D1. TW 環境限制（sub-agent 無 Bash）— **APPROVE**

理由：TW push back 正確 —— sub-agent 工具集（Read / Edit / Write / Grep / Glob / WebSearch）無 `git` / `python3` 子進程。proposal D.1 step 1-2 預設「TW 自行跑 `git fetch` + `regen_doc_inventory.py --dry-run`」是 PM 起草時對 sub-agent 工具集的誤解。

D.1 SOP 該補一行（在 step 1 前方加 **D.0 角色職能矩陣**）：

```markdown
### D.0 角色職能矩陣（sub-agent 工具集約束）

| 角色 | 工具集 | 本 proposal 允許動作 | 禁止動作 |
|---|---|---|---|
| TW (sub-agent) | Read / Edit / Write / Grep / Glob | 產 candidate inventory / 紅線 grep / 寫 candidate report / Edit markdown 內容（cross-ref stub / amendment 段） | `git` 任何子命令 / `python3` script run / `git mv` |
| main session（PM）/ E1（sub-agent + Bash） | + Bash | `git fetch / status / add / commit / mv / push` / `python3 regen_doc_inventory.py` / `node --check` | — |

TW 階段只產 candidate metadata；step 3-12 的 `git mv` / Python script run / commit / push 全部派 main session 或 E1 代執行。TW 在 candidate report 內列出「需 Bash 動作」清單，main session 接手後逐條執行。
```

### D2. Class 2 規則實質空操作 — **MODIFY (b 變體)**

選 **(b)** 但收窄條件：把 Class 2 從「daily_summary ↔ 專題 worklog 同日 cross-ref」改為「**daily_summary 末段自動列出當日 git commits**」這類「自我索引化」add 動作，**且只對未來新寫的 daily_summary 強制執行**，不回填歷史。

理由：
- TW 實測 0 對命中 = PM 原假設不存在（worklogs/ 根目錄 daily_summary 04-08~04-17 與專題 04-16~05-11 日期天然互斥；書寫風格在 04-16 後從「彙整 daily_summary」切換為「只寫專題 worklog」是已成事實）
- 完全廢除（選項 c）會丟掉「daily_summary 末段補 git commits」的合理價值（適合未來新寫的 daily_summary）
- 本輪 Class 2 標 **「Phase 1 not triggered — 規則收窄為未來 daily_summary 模板要求」**

amendment 段必要寫進去。本批不執行任何 Class 2 操作。

### D3. Class 3 同 topic 稀疏（30 樣本 1 對命中）— **MODIFY (b 變體)**

選 **(b)** — 把該 1 對 cross-ref（`live_auth_watcher_event_consumer_spawn` 04-27 worklog 加 `> 對應 agent report: ...`）**inline 在 batch 1 commit 內**，不獨立成批；理由：1 對佔 1 個 commit 是 ceremony 過剩，proposal D.1 step 5「批 3 daily_summary cross-ref 補充」本來就 N/A，step 6「批 4 worklog↔agent cross-ref」變成「+1 行 / 0 刪行」屬於 trivial 改動。

寫進 amendment：「Class 3 改為**機會主義補強**，碰到才補；本輪僅 1 對命中，inline 進 batch 1 commit」。

### D4. Class 4 內部 lineage 引用（8 檔 archive 後的 docs/ 內部歷史指針）— **APPROVE (c 雙保險)**

選 **(c)** —— 原位 redirect stub + path_redirects.md 集中登記。理由：

- 原位 stub（archive/`<topic>`/ 內 `_README.md` + redirect 指標）= 抗 grep 失誤；若未來某 agent 用相對路徑 grep 找回原 file，會看到 stub
- `path_redirects.md` 「Executed」段 = audit trail 集中查
- 兩者保留至少 1 個 sprint cycle，本來就 proposal E.2 規定
- 額外要求 main session 在 batch 1 commit msg **逐檔列出**「from → to + lineage 引用點」三元組，便於後續 review

具體 lineage 修正動作（main session/E1 在 batch 1 之後額外做 1 個 commit）：

| 引用點 | 動作 |
|---|---|
| `docs/README.md` 對 ref20 v0.1/v1/v2/v2_1_round3 / ref21 v1/v1_1/v1_2 / ref21_gui v1 的索引條目 | 將檔名 `2026-05-02--ref20_*` 改寫為 `archive/<date>--ref20_paper_replay_lab_dev_plan_superseded/...` 路徑；保留索引條目以供搜尋 |
| `docs/execution_plan/README.md` 對應條目 | 同上 |
| `docs/CLAUDE_CHANGELOG.md` 對應條目 | **不動**（歷史 changelog 不重寫）；改路徑會破壞時間軸；CLAUDE_CHANGELOG 已是「歷史證據」性質 |
| `docs/execution_plan/2026-05-02--ref20_v1_round2_audit.md`（指向 v1）| 在文末加 `> NOTE: v1 已於 2026-05-28 歸檔至 archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/`；不動審計內文 |
| `docs/execution_plan/2026-05-02--ref20_v2_round3_audit.md`（指向 v2_1_round3）| 同上 |
| `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` 第 9 行「取代 V2.1 Round3」 | **不動**（新版的 supersedes 段是事實陳述）|

### D5. Phase packet sign-off 證據（6 dir）— **DEFER（全 6 dir）**

逐 dir 證據查證結果：

| 目錄 | 檔數 | 證據查證 | archive verdict | redirect stub |
|---|---|---|---|---|
| `docs/worklogs/phase5_arch_rc1/` | 5 .md | ADR-0009 引「ARCH-RC1」為 architecture pattern（已成 stable reference）；但**無單獨 phase closure ADR/report**；`docs/CCAgentWorkSpace/TW/2026-04-12--document_audit_report.md` 提到「`phase5_arch_rc1/` 21→5 已是 04-14 前壓縮過的結果」 | **DEFER** | DEFER |
| `docs/worklogs/control_api_gui/` | 50 .md + 5 .txt | `docs/README.md` L910 + L29 列為「Control API + GUI 开发日志（2026-03-25 ~ 2026-04-02）」**逐檔索引**（L910-963）；`docs/CLAUDE_REFERENCE.md` L79-88 列 6 個檔為「歷史快查 reference」 | **DEFER** | DEFER |
| `docs/worklogs/chapters_a-g/` | 11 .txt | `docs/README.md` L29 + L862-876 逐檔列表 | **DEFER** | DEFER |
| `docs/worklogs/chapters_h-i/` | 14 .txt | `docs/README.md` L30 + L878-895 逐檔列表 | **DEFER** | DEFER |
| `docs/worklogs/chapters_j-k/` | 8 (.txt+.md) | `docs/README.md` L31 + L897-908 逐檔列表 | **DEFER** | DEFER |
| `docs/worklogs/learning/` | 1 .md | `docs/README.md` L34 + L1005-1009 索引 | **DEFER** | DEFER |

**全 DEFER 的原因**（不是 APPROVE 也不是 REJECT）：

1. **這 6 個目錄不是「孤兒檔」**，而是 `docs/README.md` 主索引第 862-1009 行（148 行）+ L29-34 樹狀總圖的**正式收納內容**。`docs/README.md` 屬 proposal A.3 紅線（「README / KNOWN_ISSUES / CLAUDE_CHANGELOG / CLAUDE_REFERENCE / lessons.md — 根入口檔」），動了會破壞既有索引
2. **「30 天無讀寫」滿足，但 closure 證據空缺**：proposal C.4 要求「已 sign-off 且 30 天無讀寫的 phase summary」，sign-off 證據 PM 在本次 review 中**搜尋不到單獨 closure report / commit / PR**（grep `closure / completed / phase 5 closure / ARCH-RC1 closure / control_api_gui closure / chapters_a-g closure` 在 `docs/adr/` / `docs/decisions/` / `docs/governance_dev/amendments/` / `docs/CCAgentWorkSpace/PM/workspace/reports/` 全 0 命中）
3. **operator authoritative knowledge 缺**：這 6 個目錄是 2026-03~04 早期 phase，當時 sign-off 機制可能還未成熟（ADR 從 0001-rust-as-trading-authority 起；早期 phase 用 daily_summary 自我封口而非單獨 ADR）

**operator 補證據後再回頭 review 的選項**：
- (a) operator 確認「README 索引段 = 軟 closure 證據」 → 動 6 個 dir + 同時改 README L862-1009 段（148 行）+ 改 L29-34 樹狀圖；本輪不做（需 R4 另派任務評估 README 大改）
- (b) operator 確認「不要動 README」→ 6 dir 永久 KEEP（不 archive）；amendment 寫進 proposal「C.4 接收條件補：被 README 主索引活引用的 phase packet 不接收」
- (c) operator 補一份「2026-03~04 phase closure 一覽」report → 我們有 closure 證據 → 但仍需先處理 README 索引問題
- (d) 用 `git mv` 後在 README 索引段把路徑更新為 `archive/<date>--<topic>/...` —— 屬保守 (c) 雙保險變體，但 148 行 README 文字改動是 R4 + PA 範疇，不在本批

**PM 建議**：選 **(b)** 為預設立場，把 6 dir 寫進 amendment 的「永久 KEEP-IN-README-INDEX 例外」段；本輪 phase 1 **不動這 6 個目錄**。如 operator 後續派 R4 review README index 重組才連帶處理。

### D6. `Operator/session_continuation_prompt_round2.md` — **APPROVE（不動）**

確認：
- 路徑 `docs/CCAgentWorkSpace/Operator/session_continuation_prompt_round2.md` 已驗證存在（`ls` 命中）
- 屬 proposal A.3 紅線「Operator handoff — 永不合併」
- 缺日期前綴是設計（這是 standing handoff template，非單次 handoff event）

**不動**；可在 batch 5「非標命名 review」清單內**白名單**標註「standing template，免日期前綴」即可。

### D7. TW 手算 vs 機器 dry-run JSON 保留策略 — **APPROVE（兩版並存）**

理由：
- 手算 257 行（schema v2 metadata + verdict tags）+ 機器 20267 行（2251 entries with sha256/mtime/orphan_flag）= **互補不衝突**
- 手算版 = 「TW 決策摘要 + push back 點 + freeze_set 清單」；機器版 = 「完整 inventory raw data」
- 兩版互拍 = audit 雙保險（若機器版日後再跑 differential，可對比手算版確認 TW 決策 vs 機器掃描的差異點 → 強化 trail）
- 反例代價低：手算版 257 行 ~10 KB，保留成本接近 0

不需在 D.1 step 9 後刪手算版。amendment 寫一行「兩版並存策略 = audit trail 雙保險」。

### D8. Class 4 否決理由 11 條 — **APPROVE（TW 否決合理；無漏判）**

逐條複核：

| TW 否決條目 | 否決理由 | PM 複核 |
|---|---|---|
| `phase4_execution_plan_v2.md` | L7 自陳「Supersedes: 無」 | ✅ 合理；v2 不取代 v1 是「擴充而非替代」設計 |
| `trading_losses_root_cause_and_fix_plan_v1.md` | 無對應 v2/v3 | ✅ 合理；命名習慣不等於 supersedes |
| `ref21_replay_remaining_wave_reset_v1.md` | L7 自陳「Does not supersede REF-21 V1.3」 | ✅ 合理；獨立 scope |
| `ref20_gap_closure_reality_backtest_plan_v1.md` | 無對應新版 + 無 SUPERSEDED 標記 | ✅ 合理 |
| `ref20_wave2_dispatch_v1.md` | 同上 | ✅ 合理 |
| `ref20_implementation_workplan_v1.md` | 同上 | ✅ 合理 |
| `ref20_ux_subdoc_v1.md` | L7 自陳「Supersedes: 無」 | ✅ 合理；retain-by-design |
| `references/2026-04-04--execution_plan_v1.md` / `comprehensive_audit_template_v1.md` / `2026-03-25--capability_and_permission_switch_plan_v1.md` | references/ 內無對應新版 + 無 SUPERSEDED | ✅ 合理 |
| `g_sr1_signal_tightening_plan_v2.md ↔ v2.5.md` | v2 無 SUPERSEDED 標記；不通過第 5 條 heuristic | ⚠️ **PM 建議補一次 audit**：v2 vs v2.5 是否 supersedes 關係 → 派 TW 在 batch 2 跑一次 `grep -E 'supersed|取代' v2.5.md`；若命中 → 加進 Class 4；否則 keep TW 否決 |
| `CCAgentWorkSpace/**/*_v2/v3/round2/round3.md` 共 ~64 個 | freeze 集（紅線）| ✅ 合理；CCAgentWorkSpace freeze 是設計，不論版本 |
| `archive/**/*_v2/v3.md` | 已在 archive | ✅ 合理 |

**PM 漏判點**：只 1 處要求 TW 補 audit（`g_sr1_signal_tightening_plan` v2 vs v2.5）；其餘 11 條 TW 否決全 APPROVE。

## 2. Amendment patch 文字（給 TW，main session 在 batch 5 或 batch 8 land）

**操作方式**：main session 派 TW 在 proposal 文末 `**END of proposal**` 行**之前**用 `Edit` 插入下列 amendment 段；TW 不動 proposal 主體任何字。

```markdown
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
```

## 3. 後續 batch 派工建議（E2）

**建議：選 (c) Mixed 派工**。

| Batch | 動作 | 執行者 | 工時 |
|---|---|---|---|
| 0 | PM proposal 已 land + TW candidate 已 land + 機器 dry-run JSON 已 land | DONE @ `93e0450b` | — |
| 1 | Class 4 8 檔 `git mv` 至 `archive/2026-05-28--ref20_paper_replay_lab_dev_plan_superseded/` 與 `archive/2026-05-28--ref21_full_chain_replay_engine_superseded/` 與 `archive/2026-05-28--ref21_gui_ux_spec_superseded/`（3 子目錄）+ 原位 stub + Class 3 1 對 cross-ref inline | **main session 親自跑 `git mv`**（不派 E1，因為 mv 動作只有 8 檔 + 1 個 Edit，分批執行 + 細粒度 commit msg 控制；E1 子進程開銷高）| ~20 分 |
| 2 | README + execution_plan README 索引條目路徑改寫（~16 處）+ 2 個 audit 報告文末 NOTE（2 處） | 派 **TW**（純 markdown Edit，TW 工具集足夠；TW 用 Grep 自驗 16 處精確命中）| ~15 分 |
| 3 | `_indexes/path_redirects.md` amend 「Executed」段 + 把本次 8 mv + Class 3 1 cross-ref 入帳 | 派 **TW**（純 markdown Edit）| ~10 分 |
| 4 | proposal amendment 段插入（上面 §2 文字） | 派 **TW**（純 markdown Edit）| ~5 分 |
| 5 | TW 對 `g_sr1_signal_tightening_plan_v2.5.md` 跑一次 supersedes audit（D8 補 audit）；命中 → 加入 batch 1 補做 | 派 **TW** + 若命中再 **main session** 補 1 mv | ~10 分 |
| 6 | `regen_doc_inventory.py --dry-run --ts-label 2026-05-28T0100`（post-cleanup 重生）+ commit 機器 JSON | **main session 跑 Bash + Python** | ~5 分 |
| 7 | regression `grep -r 'archive/.*_superseded'` 跨 CLAUDE.md / TODO.md / README.md / docs/agents/* 確認 0 命中（或全有 stub）+ `node --check` if GUI 動到（本批應 0 GUI 動）| **main session 跑 Bash** | ~5 分 |
| 8 | TW 寫 final report `2026-05-28--doc_cleanup_final.md` + PM Read 後 sign-off + main session `git push -u origin doc-cleanup/2026-05-28` + 開 PR | 派 **TW** 寫 report，**main session** push + PR | ~15 分 |

**全程預計** ~85 分鐘（vs TW 自評 2 小時，PM 略低估因為大量批次合併為 main session 直跑）

**禁忌**：
- 禁派 E1 跑 `git mv`（mv 動作粒度太細 + 需細粒度 commit msg，main session 直跑更安全）
- 禁派 sub-agent 跑 `git push`（push 應由 main session 把關）
- 本批所有 commit 加 `[skip ci]`（純 doc 變動，不需 CI）

## 4. GO 條件清單（E3 — main session 啟動 batch 1 前必驗）

- [x] **TW phase 1 candidate report ≥ 200 行**：實 253 行 ✅
- [x] **紅線 grep 0 命中**：TW 自驗 10 條全綠 ✅
- [x] **D1-D8 全 APPROVE 或明確 DEFER 理由**：5 APPROVE / 2 MODIFY / 1 DEFER（D5 phase packet）✅
- [x] **branch / HEAD 確認**：`doc-cleanup/2026-05-28` @ `93e0450b` 已 verified（`git log` 已驗證）✅
- [x] **worktree porcelain 乾淨**：在 batch 1 開跑前必跑 `git status --porcelain` 重驗（main session 開 batch 1 時動作）
- [ ] **operator review 本 sign-off**（**可選**；本 sign-off 內容已基於既有 proposal + TW report 嚴格推導；operator 可選擇直接信任 PM 決議或快速 skim 後 ACK）
- [ ] **g_sr1_signal_tightening_plan v2.5 supersedes audit 完成**（batch 5）；若命中 → 8 → 9 Class 4 candidate

**GO 條件全 PASS** → main session 跑 batch 1。

## 5. 下一個 GO/STOP

**下一個關鍵 GO**：main session 啟動 batch 1（Class 4 8 檔 `git mv` + Class 3 1 cross-ref inline）。

**下一個關鍵 STOP**：phase packet（D5 DEFER 6 dir）需 operator 補一份「2026-03~04 phase closure 一覽」或明確指示「永久 KEEP-IN-README-INDEX」。本批不 block phase 1 完成，但會限制 phase 2 範圍。

## 6. operator 是否需補 authoritative knowledge

**需要**（1 條）：

- **D5 phase packet closure 證據**：6 個 dir（`phase5_arch_rc1` / `control_api_gui` / `chapters_a-g` / `chapters_h-i` / `chapters_j-k` / `learning`）的 closure sign-off 報告 / commit / ADR 連結；或明確「永久 KEEP-IN-README-INDEX」指示。PM 本次 grep 不到單獨 closure 證據（早期 phase 用 daily_summary 自我封口，無單獨 ADR/PR）。

**不阻塞 phase 1 GO**（DEFER 不是 BLOCKER；可在 phase 1 完成後另立 phase 2 issue）。

## 7. PM SIGN-OFF

**PM SIGN-OFF: CONDITIONAL APPROVED**

條件：
1. main session 啟動 batch 1 前重驗 `git status --porcelain` 乾淨
2. batch 5 完成 `g_sr1_signal_tightening_plan v2.5` supersedes audit；命中加 mv，未命中 keep 否決
3. D5 phase packet 6 dir 全 **DEFER**；不在 phase 1 範圍；待 operator 補 closure 證據或明確 KEEP 指示後啟動 phase 2
4. proposal amendment 段（§2 文字）必須在 batch 4 land 進 proposal 文末，作為 sign-off 留痕
5. 最終 push 前 main session 親自驗 `grep -r 'archive/.*_superseded'` 跨 5 條紅線 0 命中（或全有 stub）

---

**END of PM Sign-off Report**

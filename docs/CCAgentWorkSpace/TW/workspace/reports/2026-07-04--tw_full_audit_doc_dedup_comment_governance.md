# TW 全量審計 — 文檔去重盤點 + 注釋治理（主審計 wf_6dc68c2f-4a0 補審 TW 軸）

- 日期：2026-07-04（AUDIT_DATE=2026-07-03 基線；E4/TW 補審輪）
- 凍結基線：Mac HEAD `d68a13298c5f60c3d6656cc9f465ae61aff7caa8`（其後僅審計報告 docs commits）；Linux runtime checkout `262596c69`（本輪未動用 ssh，Linux 事實引用主審計已證清單）
- 模式：read-only report-only（fix=false）；0 代碼/索引/正文修改
- 方法披露（fail loud）：TW 環境無 Bash → 無 git log/sha256sum。60 天窗口以檔名日期 + Glob mtime 排序代理；鏡像判定用「非空行數一致 + 首 60 行逐字抽樣」代理（非全文 SHA）；注釋語言用 `[\p{Han}]` Grep 計數代理。
- 前輪連續性：承 `2026-05-30--TW--doc_inventory_dedup_audit.md`（TW-DOC-2026-05-30-01..05）與 06-14 全量審計（TW memory 條目）。

## Verdict: FINDINGS — 2 HIGH + 3 MEDIUM + 3 LOW + 2 INFO；無 ship-stop；核心是 Codex 時代落盤慣例造成的三個系統性重複/規範斷裂層

---

## F-1 MEDIUM — Operator/ 全文鏡像層於 07-03 主審計批次第三度再現（FACT，confidence HIGH）

**Evidence**：07-03 六份 Operator 副本與正本非空行數逐對一致，BB 對首 60 行逐字相同：
- `Operator/2026-07-03--bybit_api_compat_audit.md` ↔ `BB/workspace/reports/…`：104/104
- `Operator/2026-07-03--full_repo_compliance_audit.md` ↔ CC：70/70
- `Operator/2026-07-03--e5_full_repo_optimization_audit.md` ↔ E5：125/125
- `Operator/2026-07-03--fa_full_repo_functional_audit.md` ↔ FA：76/76
- `Operator/2026-07-03--QC--full-repo-math-audit.md` ↔ QC：93/93
- `Operator/2026-07-03--ml-db-full-repo-audit.md` ↔ MIT：128/128

`Operator/README.md:17` 自述 audit_summary=「多 Agent 合議後的**精簡版**」；`README.md:21`「## 報告索引」節為空（檔案止於 line 22），目錄實際 787 檔。
**沿革**：TW-DOC-2026-05-17-02（56 組 SHA 全同）→ 2026-05-30-01 HELD（提案 short index stub，PM 未裁）→ 本輪再現。三度未決的 active governance choice。
**Impact**（按重複成本計）：每輪審計 +6×~100 行複製；目錄膨脹使 operator 注意力通道與 agent glob 掃描雙重付稅；歷史累計 56+ 組冗餘。
**Fix 方向**：PM 裁決 canonical=role `workspace/reports/`；Operator 副本一律 10-20 行 stub（status + 1 段摘要 + canonical link + `mirror` header）；沿 05-30 報告 §7 提案，TW 可執行、R4 驗證。

## F-2 HIGH — SCRIPT_INDEX.md 從索引再度劣化為巨型 changelog（FACT，confidence HIGH）

**Evidence**：`helper_scripts/SCRIPT_INDEX.md` 非空行 1151；「^最新補充」段落 **229 個**堆在頂部（每段 100-400 字、單物理行）；line 4 自述「最新**數批**摘要見『最新補充』段」與 229 段現實矛盾；插入非時序——line 44（2026-07-01 條目）排在 line 34-42（2026-06-27 條目）之後。role SOP 的「更新行 + 對應節 + 職責表格」格式在 Codex 條目全數缺席。06-14 TW 已修過同類 run-on（收斂 line 4 為 SSOT 指針），Codex prepend 慣例使其再生並放大 ~50 倍。
**Coverage 側**（減輕面）：抽樣 6 個近期腳本名（demo_fast_balance_equity_artifact / current_candidate_no_order_refresh_envelope / learning_candidate_proof_evidence / bounded_probe_active_order_wiring_contract / demo_learning_stack_activation_packet / install_demo_learning_stack_crons）計 18 hits 全命中 → **收錄面未破，可讀性/檢索性破**。
**Impact**（按重複成本計）：CLAUDE.md §七規定每個新腳本必觸此檔；每次 E1 增腳本、BB/E3/E5 審計、PM 派工均需載入；`cost_gate_learning_lane/` 已 88 腳本，該檔已成 helper_scripts 域最大單點 token 稅。
**Fix 方向**：「最新補充」段整批下沉為 `## YYYY-MM-DD` per-batch 節（該結構本已存在，66 個 `## ` header）；頂部只留 ≤5 批摘要 + 職責表格；長敘事指針到設計正本/role report 不複寫。可派 TW 單獨執行（純文檔）。

## F-3 HIGH — Codex 直駕代碼面「中文優先注釋」整體未執行（FACT，confidence HIGH）

**Evidence**（規模量化）：
- stock_etf Python lane（06-29~07-01 新建）：17 個 `app/stock_etf_*.py` 模塊 **0 MODULE_NOTE**、全族僅 1 行含中文（`stock_etf_routes.py`）；代表：`stock_etf_status_common.py:3` 英文-only docstring。
- stock_etf Rust types：24 個 `openclaw_types/src/stock_etf_*.rs` 模塊 **0 中文字符**；代表：`stock_etf_lane.rs:1-5` 英文 `//!`。
- Codex 批 helper：`cost_gate_learning_lane/bounded_demo_runtime_readiness.py:2-9` 英文-only docstring 無 MODULE_NOTE（06-29 批代表）。
- **對照組（規則可執行的證明）**：同 lane CC 工作鏈產物 `standing_envelope_post_approval_drift_gate.py:4-21`（07-03）完整中文 MODULE_NOTE；`rust/openclaw_engine/src/demo_learning_lane_soak_gate.rs:1-16`（07-03 E1）教科書級中文 MODULE_NOTE + why-comments。
- 規則存在於兩層治理：`CLAUDE.md` §七「New or modified comments default to Chinese」+ `.codex/MEMORY.md:43-44`「代碼注釋應默認使用中文」→ **rule present, enforcement gap**（Codex 對 docs/briefs 用中文、對 code comments 未套用）。
**Impact**（按重複成本計）：stock_etf lane 是 active 弧（P1-P5 dormant 待喚醒），~40+ 模塊 + 測試面；未來每次觸改由後續 agent 補繳雙語轉換成本；operator 顯式偏好（feedback_chinese_only_comments）被系統性繞過。
**Fix 方向**：不建議一次性 retro 翻譯（大面積 touch dormant source 會觸發 post-approval drift gate/審批噪音，違背 surgical 原則）；建議 (a)「觸及時轉中文」既有 skill 規則照常執行；(b) Codex loop 加輕量 review gate——skill 內現成 E2 grep（大段英文註釋偵測）納入 .codex 派工模板；(c) stock_etf lane 喚醒（P1 起工）時把 MODULE_NOTE 補齊列為該 wave 的 TW 隨行項。

## F-4 MEDIUM — Operator/ 目錄用途漂移：過程性 checkpoint/loop-state 記錄佔據 operator 通道（FACT，confidence HIGH）

**Evidence**：
- `Operator/README.md:8`「不存放：各 Agent 的工作草稿、**中間過程報告**」；但 06-29/06-30 兩天即 101 檔 per-micro-task checkpoint（`ibkr_stock_etf_*_checkpoint.md`、`learning_*_source_checkpoint.md` 等）；07-01 單日 15 檔機器生成 loop-state 記錄（`noorder_refresh_*_{d38,b945,0231,…}.md`，內容為 /tmp session sha + BLOCKED_BY_RUNTIME 狀態，樣本 `noorder_refresh_e3_blocked_by_source_drift_d38.md` 全檔 25 行皆 artifact sha 清單）。
- 目錄總量 787 檔（06-07 兩月 567 檔）；`README.md:21` 索引節空置。
- 減輕面：checkpoint 檔本身短小（~30 行）、中文、人類可讀（樣本 `2026-06-30--ibkr_stock_etf_paper_status_readonly_checkpoint.md`），非 F-1 型全文鏡像；且 Codex 未用 role workspace，這批 checkpoint 可能是唯一 durable 過程記錄——**不可簡單刪除**。
**Impact**：operator 注意力通道稀釋（DOC-08 §5 注意力稅）；「需要 operator 決策的報告」被 550+ 過程記錄淹沒；glob/索引全掃成本上升。
**Fix 方向**：政策裁決（PM+operator）：(a) Operator/ 收窄回 decision_required/wave_complete/audit_summary；(b) checkpoint/loop-state 分流至 `Operator/ledger/`（或 archive）子目錄並建月度索引；(c) README 索引節補最小索引或刪除該節宣稱。

## F-5 MEDIUM — 同一敘事 3-4 處全文重述（Codex 落盤慣例）（FACT + INFERENCE，confidence MED-HIGH）

**Evidence**（v738 drift gate 例）：同一 policy 敘事（exemption 集合、ROTATED 分類、`docs_tests_codex_exempt_v1`、「不 fetch、不連 runtime…」邊界句）以全文級篇幅並存於：`helper_scripts/SCRIPT_INDEX.md:6`（~400 字）、`docs/CLAUDE_CHANGELOG.md:12`（更長版）、Operator brief 族；(INFERENCE) `.codex/WORKLOG.md` 亦有第四寫（未逐字驗）。「不 fetch、不連 runtime/Bybit、不查/寫 PG…」邊界模板句在 SCRIPT_INDEX 229 段中幾乎逐段複製。
**Impact**：每個交付重複繳 3-4 份落盤 token 稅並造成多 SSOT 漂移面（改一處漏三處）。root cause 與 F-2 同源：.codex 落盤 SOP 缺「指針不複寫」規則。
**Fix 方向**：.codex 治理層補一條落盤規則：敘事正本唯一（設計 spec 或 role report），SCRIPT_INDEX/CHANGELOG/Operator brief 只留 2-3 行摘要 + 指針;邊界模板句抽成一次性定義引用。

## F-6 LOW — 檔名規範 rule-vs-practice 死字（FACT，confidence HIGH）

**Evidence**：`docs/README.md:242`「功能描述用**下划线**连接」；近 60 天 `CCAgentWorkSpace/*/workspace/reports/` 內 hyphen-desc ≥64 檔（l2-* 族、06-17/18 E1 族、06-24 demo-learning-autonomy 族、07-03 `qc-full-repo-math-audit.md` / `ml-db-full-repo-audit.md`）。role-infix 「`ROLE--`」僅 05-30 輪系統性採用，其後零星（06-09 MIT、06-16 PM、06-18 PA、07-03 QC 僅 Operator 副本），且 07-03 六份 Operator 副本同批 4 種命名風格（無 role / `fa_` 小寫前綴 / `QC--` 大寫 infix / 純 hyphen）。`YYYY-MM-DD--` 日期前綴本體未發現違規。
**Impact**：`--` 作 date/desc 分隔符的機器解析歧義（role infix 引入第二個 `--`）；跨輪檢索一致性差。
**Fix 方向**：擇一並寫回 docs/README：承認 hyphen 與 underscore 等價（改規則就實）+ 禁 role infix（role 由目錄承載）。

## F-7 LOW — worklogs/ lane 事實休眠但 README 仍標現役（FACT，confidence HIGH）

**Evidence**：`docs/worklogs/` 2026-05 僅 2 檔、2026-06 僅 1 檔（06-18）、2026-07 零；`docs/README.md:167-168` 仍稱頂層為「现役…最新工作日志」。同期工程敘事實際載體=role reports + CLAUDE_CHANGELOG + Operator briefs（資訊未丟失，lane 定位漂移）。
**Fix 方向**：docs/README worklogs 節改述「role workspace reports 為工程日誌主載體;worklogs/ 僅收跨角色綜合日誌」，或恢復 lane（TW SOP「Wave 完成後工程日誌」對映到 role report 即可，無需雙寫）。

## F-8 LOW — README.md Console tab 表殘留（06-14 已標未指派，仍未修）（FACT，confidence HIGH）

**Evidence**：`README.md:40` 仍列 `phase4` tab；`console.html` grep `id:'phase4'` 0 hit、`id:'charts'` 1 hit（`console.html:364`）→ README 缺 `charts` 列多 `phase4` 列。06-14 TW R4 冷審修 `earn` 時已 flag 此殘留（同類型、未指派），carried 20 天。
**Fix 方向**：README tab 表 −phase4 +charts（1 行級修改，任何 doc 輪順帶收）。

## F-9 INFO — cold-audit 報告族：命名穩定、無應併未併；歸檔節奏不一致（FACT，confidence HIGH）

四輪家族（05-17 / 05-30 / 06-14 / 07-03）沿用 `cold_audit_baseline` / `cold_audit_validated_fix_plan` / `cold_audit_pm_final` 穩定命名（僅 05-30 帶 `PA--` infix，見 F-6）——內容分工（凍結基線/修復計劃/PM 終審）無重複層。lifecycle 不一致：05-17/05-30 `pm_final` 已移 `docs/archive/`，06-14/07-03 仍在 PM workspace。屬歸檔節奏差，非缺陷；07-03 輪 close 後按慣例歸檔即可。

## F-10 INFO — docs/README.md:174「ADR 0001-0047」stale（R4 軸重疊，掛帳）（FACT，confidence HIGH）

`docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md` 已存在且 CLAUDE.md 已引用 ADR-0048。按本輪軸切割（R4 管索引一致性）僅掛 INFO 供 R4 收口，不展開。

---

## 附：本輪未展開盲區（negative space，給 PA re-probe）

1. Operator/ 787 檔全量 SHA 級鏡像普查未做（無 Bash；僅 6 對行數+抽樣驗證）→ 05-15 後新增鏡像組總數未量化。
2. SCRIPT_INDEX 229 段 vs 實際腳本一對一 coverage 未全量核（抽樣 6 名全命中）→ 可能存在未登腳本或幽靈條目。
3. F-5 第四寫（.codex/WORKLOG.md 重複率）為 INFERENCE，未逐字比對。
4. 60 天窗口 3145 檔僅靶向抽樣；handoffs/、governance_dev/、audits/ 子樹內容級重複未掃。
5. 注釋規範僅 4 代表檔精讀 + 2 族 Han-count；未跑 `cargo doc` 完整性、未掃 stock_etf 測試檔 docstring 語言、未掃 GUI JS 注釋。
6. execution_plan/ 近 60 天 spec 的 supersede 鏈（v1/v2 家族 SUPERSEDED header 齊全性）未逐檔重驗（憑 05-28/05-30 輪既有結論）。
7. Linux 側證據零動用（本輪純 Mac 工作樹證據；runtime 文檔漂移面由主審計 10 軸覆蓋）。

## 規範遵守

中文為主 + 英文技術名詞；0 代碼/索引改動；報告命名 `YYYY-MM-DD--描述.md`；per 06-14 教訓 workspace report 不入 docs/README 索引（collective pointer 政策）。

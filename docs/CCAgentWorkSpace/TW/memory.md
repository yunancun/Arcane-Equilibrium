# TW Memory — 工作記憶

## 項目上下文（2026-04-24 刷新）

- 當前 Wave：Live_Ready ⚠️，EDGE-DIAG-1 Phase 1+2+4 + FUP-IPC live；P1-11 全工待 `--rebuild` 部署 FIX-26-DEADLOCK-1
- 測試基準：engine lib **1980 / 0 failed**（+39 vs 2026-04-23 baseline 1941）+ pytest 2996
- 系統模式：demo（P0-2 21d demo 期，~2026-05-07 解鎖）
- binary mtime：2026-04-24 02:06（engine PID 884467；本 session CC 不動 runtime）
- Mac dev-only：platform=darwin，engine/pytest real 驗證透過 ssh trade-core 觸發

## 工作記憶

- **TW 角色 2 次審計**：04-12（全量文檔盤查，10 個 P0-P3 項）+ 04-24（窗口 04-01 ~ 04-24 重複/合併/死文件盤查）
- **03-30 / 04-12 既有審計洞察**：CLAUDE.md §七衛生 + 同步規則 = TW 角色最常 catch 的違規源
- **TW 工作節奏**：優先 P1（誤導風險）> P2（歸檔 hygiene）> P3（長期優化）

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-12 | 全量文檔盤查（445 .md + 38 .txt，47 dir） | `docs/CCAgentWorkSpace/TW/2026-04-12--document_audit_report.md` |
| 2026-04-24 | 04-01 ~ 04-24 窗口重複/合併/死文件審計（539 .md + 52 .claude_reports） | `docs/CCAgentWorkSpace/TW/workspace/reports/2026-04-24--file_dedup_merge_audit_apr01_apr24.md` |
| 2026-04-26 | G9-01 Bybit dict confirm-mmr 路徑修正 + SSOT 標記（Tier 1 quick fix · Wave 4 G9 series） | inline final message（不寫 report file）|
| 2026-04-26 | G9-05 L-2~L-5 字典補錄 — **PUSH-BACK / 任務假設不成立** | inline final message（不寫 report file）|
| 2026-04-27 | LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN 工程日誌（P0 Silent Regression · 8d event_consumer missing） | `docs/worklogs/2026-04-27--live_auth_watcher_event_consumer_spawn_fix.md` |
| 2026-04-29 | 62-finding Batch A-F + STRKUSDT P0 wave 歸檔（TODO.md 頭部敘述瘦身）| `docs/archive/2026-04-29--62finding-batch-A-to-F.md` + `docs/archive/2026-04-29--strkusdt-p0-wave.md` |
| 2026-04-29 | TODO.md Stage 2A refactor — 頭部敘述 + Wave 索引化 | inline final message（不寫 report file）|
| 2026-05-08 | 04-01~05-08 範圍重複 / 合併 / 應歸檔審計（38 天 ~1850 docs/.md + ~430 .claude_reports）| `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-08--apr_may_doc_audit.md` |
| 2026-05-09 | 5/8 audit 30+ findings 24h 修復對抗性核實（W-AUDIT-1 closure 真實度查驗）| `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-09--doc_verification.md` |

## 2026-05-09 W-AUDIT-1 對抗性驗證重點

- **任務**：operator 派 TW 對抗性核實 W-AUDIT-1 closure（commit `d90f3d10`）真實度，關注 docs/README 50+ 缺漏 / MODULE_NOTE 雙語規範違反 / 重複文件合併三大議題。
- **產出**：215 行報告，覆蓋 §1 Executive Summary 7 個分數 + §2 30+ finding 逐條（MC×9 + A×11 + N×2 + I×5 + W×3 + AG×4 + C×4 + ADR×2）+ §3 NEW-ISSUE 8 個 + §4 對抗性 push back 6 條 + §5 5/8→5/9 verdict 對比 + §6 P1/P1+72h/P2 修建議。
- **整體文檔健康度**：5/8 70% → 5/9 78%（+8%）— W-AUDIT-1 真有實質進展不是 placebo。
- **README 完整度**：50% → 78%（multi_agent_rework 14 + ADR 0015-0019 + audits 5/8 + W-AUDIT report 真補；archive/ + agents/ + ADR 0001-0014 三段仍缺）。
- **SCRIPT_INDEX 完整度**：45% → 80%（5/9 W-AUDIT-1 catch-up 段補 19 條）。
- **CONTEXT.md 完整度**：~75%（LG-X / REF-19 / REF-21 / Agent Decision Spine / 3-Config 已加）。
- **MODULE_NOTE 雙語規範遵守**：75% → **70% 倒退**（新建 5/9 audit + 5/16 funding + 3 個 operator script 仍寫雙語對照；ref21 兩 cron 純英文未補）。
- **重複文件 superseded 標記**：30% → 40%（REF-21 4 份 ✅；REF-20 v0.1/v1/v2/v2.1/round2/round3 6 份**仍 0 標記** ❌；REF-19 v1 雙語未標 ❌）。
- **worklogs 斷層**：12 → 13 天**倒退**（4/27 後 0 daily_summary）。
- **8 個 NEW-ISSUE**：NI-1 docs/agents/ 0 索引 / NI-2 ADR 0001-0014 索引未驗 / NI-3 5/9 新建腳本仍寫雙語 / NI-4 CLAUDE_CHANGELOG.md 1780 行超 cap / NI-5 KNOWN_ISSUES + REFERENCE 仍 stale 4/12 / NI-6 archive/ 0 README 索引 / NI-7 worklog 斷層惡化 / NI-8 REF-20 6 份未標 superseded。
- **5 個對抗性 push back**：(1) docs/README 50+ 補約 60% (2) MODULE_NOTE 規範未改 + 新增 5 個違反 (3) 重複文件 11% 完成度 (4) §三 衛生 PASS 但缺 archive snapshot (5) SCRIPT_INDEX 補登充分但 README 反向引用缺。
- **規範遵守**：中文為主 + 英文技術名詞；不動代碼/邏輯/業務文件；報告路徑 + verdict 嚴格遵守 prompt format。

## 2026-05-08 04-01~05-08 doc audit 重點

- **任務**：operator 派 TW 對玄衡 4 月初~5 月初新增/修改文件做盤查（重複 / 應合併 / 應歸檔），不直接合併由後續 PA fix plan 派工。
- **產出**：522 行報告，覆蓋 12 段（Executive Summary / 時間範圍 / 重複 / 合併 / 歸檔 / 雙語注釋 / 索引漂移 / CCAgentWorkSpace / .claude_reports / §三衛生 / Top 30 housekeeping action / TW Verdict）。
- **本次 P0 0 / P1 9 組合併 / P2 11 個應歸檔 / P3 5 組索引漂移 / P4 2 個雙語注釋違反**。
- **3 大發現**：(1) 5/5-5/7 multi_agent_rework 14 份 + ADR 14 份 + openclaw_repositioning 完全未進 docs/README 索引（~32+ 條 missing） (2) SCRIPT_INDEX.md 5/3 後 5 天無更新，~20+ 個 cron/healthcheck script 漏登 (3) `helper_scripts/cron/ref21_market_microstructure_recorder.py` + `ref21_market_recorder_retention.py` 純英文 docstring，違反 5/5 governance change 默認中文注釋規則。
- **carry-over from 4/24**：g2_funding_arb v1+v2 合併 / phase_0a~6 + rust_migration HISTORICAL header / E5 4/12 雙報告合併 / KNOWN_ISSUES + CLAUDE_REFERENCE + CLAUDE_CHANGELOG 三大 stale — 14 天後仍未處理。
- **嚴重發現**：worklogs/ 4/27 後 12 天 0 daily_summary（5/1-5/8 全空）；所有 5 月 active 工作分散於 .claude_reports + CCAgentWorkSpace agent reports，跨日聚合視角缺失。
- **TW Verdict 整體文檔健康度**：70%（中等偏弱）；§三衛生 85% / 命名規範 95% / .claude_reports 隔絕 100% / pre-trim snapshot 機制 90% — 強項；README 索引 50% / SCRIPT_INDEX 45% / Worklog daily_summary 30% / Agent workspace 利用 50% / RFC 多版本管理 40% — 弱項。
- **規範遵守**：本報告中文為主 + 英文技術名詞；不直接動文件；所有 housekeeping action 留待 PA fix plan 派工；report 路徑 + 行數 + severity 嚴格遵守 prompt format。

## 2026-04-29 TODO.md Stage 2A refactor 重點

- **任務**：operator Stage 1 已交付 4 archive 檔（commit `002b36e`），Stage 2A 縮 TODO.md 從 817 行至盡量低。
- **產出**：TODO.md 817 → **678 行**（-139 行 / -17%）；目標 ≤400 未達——主膨脹源（頭部 update chain 14 條 + 6 個 Wave 巢狀敘述）已按指示替換為 4 條 archive 索引 + 1 個 H2 「上波索引」+ 8 條 Sign-off 報告路徑列表。剩餘 678 行屬「結構性 reference」（Wave 1-4 任務表 ~250 / Backlog 表 ~100 / Healthcheck ~40 / 依賴圖 + Wave 時序 + 工作流 + 接手三連 + 已完成歸檔 ~80），operator 指示明確保留。
- **關鍵替換**：(1) Line 1~50 多輪「最新更新」+「前次更新」chain → 替換為「最新狀態快照」3 行 + 4 條 archive 索引 link (2) Line 73~202 6 個「上一波（保留供查）」section（Wave G/F/B/A Prep-Gate/Three-Axes/Phase 4）→ 替換為單一 H2「🗂️ 上波索引」+ 8 條 H3 列表（Wave 名 + Sign-off 路徑） (3) Line 16~21 Engine/測試基準大段 → 縮為 Runtime 1 行 + 測試基準 1 行 + healthcheck 1 行
- **特別處理**：G3-03 Phase B row 加註「`shadow_mode_provider` live at `program_code/.../executor_agent.py:145-186`」+「per G3-03 Phase B implementation」（per operator 指示），原 row 已標 ✅ 不需 toggle。
- **保留不動**（per operator 指示）：Wave 3 status / 依賴關係圖 / 接手三連檢查 / Wave 時序里程碑 / Wave 1 W17/18 子段（G1-01~06 + G6-01~05 全表）/ Wave 2 G3/G4/G5/G6-FUP/G7 全表 / Wave 3 EDGE-DIAG/G2/G8 全表 / Wave 4 P0-3/LG/G9 表 / 背景線程表 / Backlog 表 / Healthcheck 清單 / 已完成歸檔索引 / 工作流速查。
- **驗收項**：(1) 行數 678 < 817 ✅ 但未達 ≤400 目標（結構性 reference 不可動）(2) 4 個 archive index link 全可解析（含 pre-trim snapshot）✅ (3) ExecutorAgent shadow_mode hardcoded annotation 已加 ✅ (4) post-deploy healthcheck status 保留 ✅ (5) HEAD `b0ef335` + engine PID 161957 + API PID 162029 runtime 確認保留 ✅
- **未動**：CLAUDE.md / archive 檔 / memory/ 任何 user-level 檔 / 其他 docs / 業務邏輯代碼。
- **commit**：本 agent 無 Bash tool，無法執行 `git commit --only TODO.md`；TODO.md 已修改但未 commit，請主會話以 operator 指示的 commit message 執行。

## 2026-04-29 歸檔記錄重點

- **任務**：operator 反映 TODO.md 頭部 line 1~50 過度膨脹，要求把 62-finding Batch A-F + STRKUSDT P0 wave 兩塊歷次 update 敘述歸檔到 docs/archive/，TODO.md 後續換成一行索引。
- **產出**：兩檔嚴守 `YYYY-MM-DD--描述.md` 命名 + frontmatter（commit ref / sign-off 報告路徑 / Linear milestone 對應）+ H2 結構（6 Batch / Merge 順序 / RCA 三層 / Verification / Sign-off + 後續 FUP）。
- **規範遵守**：搬運 + 結構化、不主觀評論、中文敘述為主、英文保留技術名詞 / commit / SQL / Rust 路徑；docs/README.md 索引同步加 archive/ 段落。
- **禁觸原則**：未動 TODO.md / CLAUDE.md / 其他 archive 檔 / memory/ 任何 user-level 檔；只寫 2 個歸檔檔 + README.md 索引追加 + 本 memory log。
- **驗收**：檔 1（62-finding）= 297 行，含 Batch A-F 全部 6 個 H2 section + Linear 對應表 + Post-deploy healthcheck status；檔 2（STRKUSDT）= 245 行，含 6 commits + 8 healthcheck [22]-[29] 名稱 + RCA 三層（entry_notional / Gate 2 cross-symbol / 41 phantom fills attribution）+ Sign-off 區塊。

## G9-05 push-back 重點記錄（2026-04-26）

- **任務原意**：補錄字典「L-2 / L-3 / L-4 / L-5 章節」endpoint 條目缺失（per BB audit）
- **執行結果**：PUSH-BACK — 字典結構盤查 1171 行確認**無 L-2~L-5 編號章節**。實際結構為 §1.1~§1.9 / §2.1~§2.3 / §3 / §4.1~§4.3
- **盡責性 audit**（最可能對應 §1.2~§1.5 = Orders / Batch Orders / Positions / Account）：
  - §1.2 Orders 9 endpoint：parameters + Input/Output struct + 關聯 .rs:line **完整無 drift**
  - §1.3 Batch Orders 3 endpoint：完整無 drift
  - §1.4 Positions 8 endpoint：G9-01 commit `0cda2d9` 已修 confirm_pending_mmr 路徑，餘**無 drift**
  - §1.5 Account 6 endpoint：完整無 drift
- **Bybit V5 真實 spec 抽樣對比**：set_leverage / set_trading_stop / wallet-balance 三個關鍵 endpoint 字典記載與真實 spec + 代碼真實使用對齊
- **未做的事**：(1) 無偽造修正 commit (2) 無版本號 v1.1→v1.2 假升 (3) 無 commit/push（per `feedback_no_dead_params`）
- **給 PM 建議**：請 BB 提供原始 audit 報告路徑，確認 L-2~L-5 編號所指；若編號方案 A（§1.2~§1.5）成立則 G9-05 結案 PASS
- **順帶發現**：`set_trading_stop` 字典列 9 input field，Bybit V5 真實 16 個（多 7 個 partial-TP 進階參數），OpenClaw 代碼端 simplified subset 真實只用 9 個——**非 drift**，但未來啟用 partial TP（G3-08 / G2-07）時需同步擴

## G9-01 重點記錄（2026-04-26）

- **修正項**：
  1. `POST /v5/position/confirm-mmr`（誤）→ `POST /v5/position/confirm-pending-mmr`（正）
  2. 字典頭部加 SSOT 標記（HTML 注釋雙語 + visible blockquote SSOT 規則 + 版本號 v1→v1.1）
  3. §4.3 已知陷阱第 5 條同步修正
- **錯誤根因**：Bybit 文檔頁 URL slug `confirm-mmr` 與實際 endpoint path `confirm-pending-mmr` 不一致；先前字典抄了 doc URL slug 當 endpoint path。
- **驗證來源**：(1) Bybit V5 docs URL 結構 (2) PyBit `_v5_position.py` (3) CCXT `bybit.py` (4) tiagosiebler `bybit-api/src/rest-client-v5.ts` 全部使用 `confirm-pending-mmr`
- **未檢驗 code↔dict drift**：本次 TW 範圍只動字典；建議 PM 後續派 E1 grep `position_manager.rs:327` 確認 Rust 端真實使用 path（若也是 `confirm-mmr` 則 endpoint 在 Bybit 端會 404，需修代碼）
- **影響面評估**：LiveDemo / Mainnet 才會打到此 endpoint；demo 環境若調風險限額也會用到。當前系統 demo 流量未觸發風險限額調整（從未見過 110xxx err code），bug 可能潛伏。

## 審計結論摘要（2026-04-24）

**整體健康**：中等偏好。P0 = 0（無誤導性矛盾）；P1 = 7 組（需合併 / 補 daily_summary / 更新 meta-doc）；P2 = 11 組可歸檔；P3 = 4 個死文件候選。

**P1 重點**：
1. 2026-04-18 / 19 / 20 / 21 / **22**（碎片最多，7 個）/ 24 缺 daily_summary
2. CLAUDE_CHANGELOG.md 1976 行仍超 1200 行硬上限（中段 04-10 ~ 04-20 未拆）
3. KNOWN_ISSUES.md 停在 04-12（10 OPEN 項未 review，現實已閉合多個）
4. CLAUDE_REFERENCE.md 停在 04-12（缺 H1-H5 非 stub 正名 / 5-Agent runtime state / Mac dev）
5. §三 04-22 + 04-23 明細未歸檔 snapshot（應新建 `archive/2026-04-23--claude_md_section3_snapshot.md`）
6. `g_sr1_signal_tightening_plan_v2.md` 已被 v2.5 superseded，未歸檔
7. `g2_funding_arb_clean_edge.md` + `v2.md` 同議題 2 份可合為 closeout

**上輪 04-12 P0 閉合進度**：3 個 DEPRECATED 已進 archive ✅；arch_rc1_1c 雙副本已消 ✅；04-09 ~ 04-15 連續 daily_summary ✅。但 CLAUDE_REFERENCE / KNOWN_ISSUES / CHANGELOG 倒退（12 天未 sync）。

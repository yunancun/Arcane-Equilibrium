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

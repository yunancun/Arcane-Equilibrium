# 2026-04-24 FIX-PLAN PM 簽核報告

**日期**：2026-04-24 CEST
**簽核者**：PM（主會話 + PM agent 雙軌確認）
**對象**：FIX-PLAN（PA整合審計，27 KB、45 findings、6 工作組、4 wave）+ 原 TODO.md（700 行）

## § 1. 簽核決定

### ✅ **APPROVED WITH MINOR ADJUSTMENTS**

FIX-PLAN 整體架構健全、findings 去重精準、工作分組清晰、時序務實。6 項調整合併入新 TODO。

**FIX-PLAN 路徑**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md`

## § 2. 10 Agent Audit 總覽

| # | Agent | 職責 | 報告 | 核心發現 |
|---|---|---|---|---|
| 1 | PM | 優先級 + 依賴 | `PM/workspace/reports/2026-04-24--4.24TodoAudit.md` | edge_estimates.json 162→1 cell 嚴重不符；A-F 分類框架 |
| 2 | FA | 功能規格驗收 | `FA/workspace/reports/2026-04-24--4.24TodoAudit.md` | 60% VERIFIED / 20% PARTIAL / 20% MISMATCH；**PostOnly 配置反向** |
| 3 | PA | 架構設計 | `PA/workspace/reports/2026-04-24--4.24TodoAudit.md` | 健康度 7.2/10；Top 3 leverage = Exec toggle + FUP-SHADOW-IPC + Combine 監控 |
| 4 | CC | 16 條根原則合規 | `CC/workspace/reports/2026-04-24--4.24TodoAudit.md` | 合規 B-（66%）；**ExecutorAgent shadow=True 違反原則 #3** |
| 5 | QC | 量化策略審計 | `QC/workspace/reports/2026-04-24--4.24TodoAudit.md` | edge_estimates 4天停滯 / n_cells=1 / JS n=3 統計無意義 |
| 6 | QA | 端到端驗收 | `QA/workspace/reports/2026-04-24--4.24TodoAudit.md` | 12 healthcheck + 5 缺陷；「代碼通過≠功能驗收」 |
| 7 | AI-E | AI 效能 | `AI-E/workspace/reports/2026-04-24--4.24TodoAudit.md` | H1-H5 完整但 Rust tick pipeline 0 invocation |
| 8 | MIT | DB/ML 管線 | `MIT/workspace/reports/2026-04-24--4.24TodoAudit.md` | **edge_estimator_scheduler 4 天未運行**（root cause） |
| 9 | E5 | 性能/可讀性 | `E5/workspace/reports/2026-04-24--4.24TodoAudit.md` | **8 個 Rust 硬上限違反** + event_consumer fn 1696 行 |
| 10 | BB | Bybit API | `BB/workspace/reports/2026-04-24--bb_todo_audit.md` | API A+ 覆蓋度；WS-RETIRE-1 100% ✅ |

**PA 整合**：`PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md`（45 findings × 6 工作組 × 4 wave）

## § 3. PM 6 項調整建議

### 調整 1：G1 event_consumer fn 拆分進度估計

- 現估 2-3d → **3-4d**
- 理由：1600 行單 fn 拆分，邊界 case + test 補齊易低估
- 若 <3d 完成則提前啟 Wave 2
- 簽核：💙 同意

### 調整 2：Phase 3 auto-gate 前置條件補強

- FIX-PLAN §EDGE-DIAG Phase 3 現 3 項 (a)(b)(c)
- 補 **(d) healthcheck [11] 連續 PASS ≥3 天**（避免單日抖動）
- 實作：`passive_wait_healthcheck.py` 邏輯無變；operator 人工判決日間連續性
- 簽核：💚 同意

### 調整 3：P0-3 邊評決策日期事件驅動

- 舊：hard commit「2026-05-07 完成」
- 新：**demo 21d 解鎖當日起 3 日內完成 P0-3 決策會**
- 理由：P0-2 解鎖是硬時刻點；決策會需 operator 時間 + 可能補 replay 數據
- 簽核：💛 條件同意

### 調整 4：EDGE-DIAG-1-FUP-IPC 優先級 P3 → P2 ★

- FIX-PLAN 現 P3 backlog
- 升 **P2**（Wave 2 期間與 G3 並行）
- 理由：Phase 3 部署前**必須**有 <60s 可逆路徑（rebuild 3 min 時間不足）
- 簽核：🔴 強建議

### 調整 5：P1-10 驗證窗口延長

- 現估 fee drag 驗證 1w passive
- **延長 1-2 週持續交叉驗證**
- counterfactual replay（EDGE-DIAG Phase 2 已建）驗證 postonly 後 fee drag 是否真解除
- 簽核：💚 同意

### 調整 6：P1-7 C labels 累積 ETA 更正 ★

- 舊：單 symbol `demo grid_trading BLURUSDT 47/200`，ETA ≈78h
- 新：**per-strategy pooled 跨所有 grid symbol**，合計 ~200+ 可立即訓練
- 原 ETA 已過期（BLURUSDT 2026-04-20 後停交易，策略輪動 PENGUUSDT 等）
- 模型架構 symbol-agnostic（17 feature 無 symbol_embedding），pooled 安全
- 簽核：💚 同意

## § 4. 對照原 TODO 二次驗證（零遺漏）

**掃描範圍**：原 TODO.md P0/P1/P2 所有活躍 `[ ]` 條目

| # | 原 TODO 項目 | 分級 | FIX-PLAN 對應 | 狀態 |
|---|---|---|---|---|
| 1 | P0-2 LG-1 21d demo 觀察 | P0 | §5 完成標準 | ✅ 覆蓋 |
| 2 | P0-3 Phase 5 edge 重評 | P0 | §1 / §3.3 | ✅ 覆蓋 |
| 3 | DUAL-TRACK Step 0（5 衍生項） | P0 | 2026-04-22 歸檔 | ✅ 歸檔 |
| 4 | DUAL-TRACK Phase 1a/1b/2/3/4 | P0-P2 | §1-§5 主軸 | ✅ 覆蓋 |
| 5 | EDGE-DIAG-1 Phase 3-4 | P1 | §EDGE-DIAG 完整 | ✅ 覆蓋 |
| 6 | P1-6 DEMO-BYBIT-SYNC-ORPHAN | P1 | §P1 其他項 | ✅ 覆蓋 |
| 7 | P1-7 LEARNING-PIPELINE-DORMANT | P1 | §G4 / §P1-7 | ✅ 覆蓋 |
| 8 | P1-10 STRATEGY-ASYMMETRY | P1 | §G2 | ✅ 覆蓋 |
| 9 | P1-11 BB-BREAKOUT/REVERSION | P1 | §P1-11 Phase 1 + FIX-26 | ✅ 覆蓋 |
| 10 | P1-13 SAMPLE-FLOOR-GAP | P1 | §P1 其他項 | ✅ 覆蓋 |
| 11 | P1-14 EDGE-ESTIMATE-BIND | P1 | §P1-14 | ✅ 覆蓋 |
| 12 | P1-19 BACKFILL-LABELS-STALLED | P1 | 2026-04-22 結案（併入 P1-10） | ✅ 去重 |
| 13 | EDGE-DIAG-1-FUP-IPC | P2 | §P2 高優先（調整 4） | ✅ 覆蓋 |
| 14 | STRATEGIST-PERSIST-* | P2 | §P2 | ✅ 覆蓋 |
| 15 | STRATEGIST-PROMOTE-TRIGGER-1 | P2 | §G3 相關 | ✅ 覆蓋 |
| 16 | STRATEGIST-AUTO-PROMOTE-CRITERIA-1 | P2 | §P3 | ✅ 延後 |
| 17 | LG-2/3/4/5 | P2 | §4 Wave 4 | ✅ 覆蓋 |
| 18 | G-1/FIX-01/FIX-02/FIX-12 | P2 | §G3 AI 接線 | ✅ 覆蓋 |
| 19 | G-7 ClaudeTeacher / G-10 Calibration | P2 | §G4 Phase 4 | ✅ 覆蓋 |
| 20 | EDGE-P2-2 Phase B Liquidation | P2 | §P3 | ✅ 延後 |
| 21 | EDGE-P2-3 Phase 2+ (c) live endpoint | P2 | §G2 PostOnly 1w 驗證後 | ✅ 覆蓋 |
| 22 | QoL-2 Demo AI cost | P2 | §G3 依 G-1 | ✅ 覆蓋 |
| 23 | ORPHAN-ADOPT-1 Phase 2B | P2 | §P3 待 R-02 | ✅ 覆蓋 |
| 24 | IP-DEDUP-1 / WP-F/E4/E5/I | P4 | §P4 Backlog | ✅ 覆蓋 |
| 25 | Phase 5 補強 DL-1/2 / JS / Scorer | P3 | §P3 待 P0-3 | ✅ 覆蓋 |
| 26 | 4-Conditional | P4 | §P4 | ✅ 保留 |
| 27 | G-2 FundingArb 三參數重評 | P3 | §P3 待 R-02 | ✅ 覆蓋 |

**結論**：✅ **零遺漏活躍 TODO**。27 個活躍項均被 FIX-PLAN 覆蓋或妥善歸檔/去重。

## § 5. 決策記錄

1. **新 TODO 結構** = FIX-PLAN §6 7-layer + PM 6 項調整
2. **舊 TODO 歸檔** = `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`
3. **audit 索引** = `docs/audits/2026-04-24--todo_refactor_index.md`（指向 10 agent 報告 + FIX-PLAN + Sign-off）
4. **CLAUDE.md §三 sync** = 加註「當前 PM 簽核版本：2026-04-24 TODO 重構」
5. **memory 新增** = `project_edge_scheduler_stalled.md`（scheduler 4 天停滯追蹤）+ `project_2026_04_24_todo_refactor.md`

## § 6. PM 最終判決

**簽核狀態**：✅ **APPROVED**

**核准條件**：
1. 新 TODO.md 納入 6 項調整 ✅
2. 每個條目帶 audit 指針（→ `CCAgentWorkSpace/<agent>/workspace/reports/`）+ FIX-PLAN 指針（→ `PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md`）✅
3. 首次部署時 CLAUDE.md §三 加註「PM 簽核版本 2026-04-24」✅

**下一步**：主會話（PM+Conductor）寫新 TODO.md + 更新 CLAUDE.md / README / memory + commit/push

---

**簽核人**：PM · 2026-04-24 · Auto mode enabled

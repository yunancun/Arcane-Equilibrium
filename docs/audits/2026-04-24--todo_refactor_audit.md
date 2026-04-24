# 2026-04-24 TODO 全面重構 Audit 索引

**動機**：原 TODO.md 700 行、47578 tokens，混亂度高，難以梳理清晰工作流程。operator 要求 10 角色並行 audit、基於實際代碼驗證現狀、產生可執行修復計畫、重構 TODO 結構。

**輸出**：
- 新 TODO.md（重構版）
- 舊 TODO 歸檔：`docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`
- 本索引檔 + 各 Agent audit 報告 + PA FIX-PLAN + PM Sign-off

## 10 Agent 獨立 Audit 報告

每個 agent 獨立讀實際代碼驗證 TODO 宣稱，不迷信 commit note。

| # | Agent | 角色 | 報告路徑 | 核心發現 |
|---|---|---|---|---|
| 1 | **PM** | Project Manager | [PM report](../CCAgentWorkSpace/PM/workspace/reports/2026-04-24--4.24TodoAudit.md) | edge_estimates.json 宣稱 162→實際 1 cell；A-F 分類框架 |
| 2 | **FA** | Functional Auditor | [FA report](../CCAgentWorkSpace/FA/workspace/reports/2026-04-24--4.24TodoAudit.md) | 60% VERIFIED / 20% PARTIAL / 20% MISMATCH；**PostOnly demo=false/live=true 配置反向** |
| 3 | **PA** | Project Architect | [PA report](../CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit.md) | 架構健康度 7.2/10；3 leverage = Exec toggle + FUP-SHADOW-IPC + Combine 監控 |
| 4 | **CC** | Compliance Checker | [CC report](../CCAgentWorkSpace/CC/workspace/reports/2026-04-24--4.24TodoAudit.md) | 合規 B-（66%）；ExecutorAgent shadow=True 違反原則 #3 |
| 5 | **QC** | Quantitative Consultant | [QC report](../CCAgentWorkSpace/QC/workspace/reports/2026-04-24--4.24TodoAudit.md) | edge_estimates 4天停滯 / n_cells=1 / JS n=3 統計無意義 |
| 6 | **QA** | Quality Assurance | [QA report](../CCAgentWorkSpace/QA/workspace/reports/2026-04-24--4.24TodoAudit.md) | 12 healthcheck + 5 缺陷；「代碼通過 ≠ 功能驗收」 |
| 7 | **AI-E** | AI Effectiveness | [AI-E report](../CCAgentWorkSpace/AI-E/workspace/reports/2026-04-24--4.24TodoAudit.md) | H1-H5 完整但 Rust tick pipeline 0 invocation |
| 8 | **MIT** | Machine Intelligence | [MIT report](../CCAgentWorkSpace/MIT/workspace/reports/2026-04-24--4.24TodoAudit.md) | **edge_estimator_scheduler 4 天未運行**（root cause） |
| 9 | **E5** | Optimization Engineer | [E5 report](../CCAgentWorkSpace/E5/workspace/reports/2026-04-24--4.24TodoAudit.md) | 8 個 Rust 硬上限違反 + event_consumer fn **1696 行** |
| 10 | **BB** | Bybit API Auditor | [BB report](../CCAgentWorkSpace/BB/workspace/reports/2026-04-24--bb_todo_audit.md) | API A+ 覆蓋度；WS-RETIRE-1 100% ✅ |

## 整合 + 簽核

- **PA FIX-PLAN**：[FIX-PLAN](../CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md)（27 KB, 45 findings, 6 工作組, 4 wave, 7-layer TODO 骨架）
- **PM Sign-off**：[Approval](../CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_PMApproval.md) ✅ Approved with 6 minor adjustments

## 6 大工作組（新 TODO 主軸）

| Group | 名稱 | 核心 findings | Wave |
|---|---|---|---|
| **G1** | Edge 危機根源修復 | edge_estimator scheduler 恢復 / event_consumer 拆 / fee drag | W1 |
| **G2** | 策略層改造 | grid disable 決策 / ma SL/TP / bb_breakout deploy / funding_arb | W1-W2 |
| **G3** | AI 多 Agent 接線 | ExecutorAgent live flip / H1-H5 → Rust gateway / Layer 2 工具箱 | W2 |
| **G4** | ML 管線解凍 | labels 加速 / model_registry flip / training pipeline end-to-end | W2-W3 |
| **G5** | 架構 / 可讀性債務 | Rust 8 硬違反拆分 / Python 2 硬違反 / dead code | W2 |
| **G6** | 合規 + 觀察性 | healthcheck 補齊 / V023 retrofit / 被動等待 healthcheck 全覆蓋 | W1-W2 |

## 4 Wave 時序

| Wave | 週 | 焦點 | Live 里程碑 |
|---|---|---|---|
| Wave 1 | W17/18 · 4/24-4/30 | G1 scheduler 恢復 + event_consumer 拆 + 邊際驗證 | 基礎設施解凍 |
| Wave 2 | W19 · 5/1-5/7 | G3 AI 接線 + G5 refactor + G4 ML pipeline | AI 全連接 + 代碼結構 |
| Wave 3 | W20-W23 · 5/8-5/23 | EDGE-DIAG Phase 3 + Phase 1b FUP + Phase 4 | 邊界穩定 + ML canary |
| Wave 4 | W23-W24 · 5/19-5/30 | LG-2/3/4/5 + P0-3 + Phase 2 shadow | Live Gate 簽準 → Live |

**最早 Live 日期**：W24 末（~2026-05-23 樂觀 / ~2026-05-30 中位 / ~2026-06-15 悲觀）

## 4 大議題覆蓋

operator 最關心 4 大議題，對應新 TODO 章節分佈：

| 議題 | 主要條目 | 工作組 |
|---|---|---|
| **Edge 問題**（策略負 edge / edge_estimates 停滯） | F01 scheduler / F02 JS n=1 / F06 fee drag / F10 counterfactual | G1 + G2 |
| **交易金額過小 + 頻率過低** | F04 BB dormancy / F05 funding_arb / F11 sample floor | G2 |
| **策略虧損**（grid/ma/bb 全負） | F06-F09 fee + R:R + no alpha | G2 |
| **AI / ML / 多 Agent 協作** | F12-F20 ExecutorAgent / Layer 2 / H1-H5 / model_registry / Teacher / LinUCB | G3 + G4 |

## 關鍵 Verified Findings（3 大）

1. **edge_estimates.json 僅 1 cell**（實測讀檔：`grid_trading::ORDIUSDT`, `n=3`, `grand_mean_bps=-45.73`, mtime 2026-04-20 23:50）— CLAUDE.md 宣稱 162 cells 嚴重過期
2. **PostOnly 配置反向**（strategy_params_demo.toml vs live.toml 實讀對比）— TODO 敘述與代碼不符
3. **ExecutorAgent _shadow_mode=True hardcoded**（`executor_agent.py:482`）— 5-Agent→Rust 執行鏈物理斷裂，違反原則 #3

## 執行順序（compact 拆 session 考量）

- **Session 1（當前）**: audit + FIX-PLAN + PM Sign-off + 新 TODO + meta docs + commit/push（本 session 已完成）
- **Session 2**: G1-MIT scheduler 診斷 + G1-E1 event_consumer 拆分（PA 同 session 緊密）
- **Session 3**: G3 AI 接線（PA RFC + E1/E2 實裝）
- **Session 4**: G5 refactor（8 Rust + 2 Python 拆分，多 E5/E1 並行）
- **Session 5+**: Wave 3/4 被動等待 + 決策會

---

**索引建立時間**：2026-04-24 CEST
**更新負責**：主會話（PM+Conductor）

---
name: TODO 10-Agent Audit 重構（2026-04-24）
description: 10 個獨立 agent 並行 audit + PA FIX-PLAN + PM Sign-off → 舊 TODO 700 行歸檔、新 TODO 328 行精煉 53%；3 大 Verified 發現
type: project
originSessionId: f4abc469-afe6-401a-af27-a320525bab3c
---
## 觸發
Operator 2026-04-24 判斷原 TODO（700 行、47578 tokens）混亂難以梳理清晰工作流程，要求 10 角色（PM FA PA CC QC QA AI-E MIT E5 BB）各自獨立 audit + 讀代碼驗證 + 重構工作安排。

## 執行

**10 Agent 獨立 Audit**（全部在 `docs/CCAgentWorkSpace/<agent>/workspace/reports/2026-04-24--4.24TodoAudit.md`，BB 用 `2026-04-24--bb_todo_audit.md`）：
- PM: edge_estimates 162→1 cell 嚴重不符；A-F 分類框架
- FA: 60% VERIFIED / 20% PARTIAL / 20% MISMATCH
- PA: 架構健康度 7.2/10；3 leverage points
- CC: 合規 B-（66%）；ExecutorAgent shadow=True 違反原則 #3
- QC: edge_estimates 4天停滯，JS n=3 統計無意義
- QA: 12 healthcheck + 5 缺陷
- AI-E: H1-H5 完整但 Rust tick 0 invocation
- MIT: edge_estimator_scheduler 4 天未運行（root cause）
- E5: 8 Rust 硬上限違反 + event_consumer fn 1696 行
- BB: API A+ 覆蓋度；WS-RETIRE-1 100%

**PA FIX-PLAN**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md`（27 KB, 45 findings, 6 工作組, 4 wave, 7-layer TODO 骨架）

**PM Sign-off**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_PMApproval.md`（Approved with 6 minor adjustments）

## 結果

- **舊 TODO 歸檔**：`docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`（700 行）
- **新 TODO**：328 行（精煉 53%），按 Wave 1-4 + 6 工作組（G1-G6）組織
- **Audit 索引**：`docs/audits/2026-04-24--todo_refactor_audit.md`
- **每條 TODO 帶 audit + FIX-PLAN 指針**

## 3 大 Verified 發現（讀代碼驗證）

1. **edge_estimates.json 僅 1 cell** — 實測讀檔：`grid_trading::ORDIUSDT, n=3, grand_mean_bps=-45.73`，mtime 2026-04-20 23:50（4 天停滯）。CLAUDE.md 宣稱 162 cells 嚴重過期。→ G1-01 立即恢復 scheduler
2. **PostOnly 配置反向** — `strategy_params_demo.toml` 設 false，`strategy_params_live.toml` 設 true。違反原則 #6（失敗默認收縮）。→ G1-05 立即修
3. **ExecutorAgent `_shadow_mode=True` hardcoded** — `executor_agent.py:482` + `strategy_wiring.py:467` `ExecutorConfig()`。5-Agent→Rust IPC 物理斷路，違反原則 #3（AI 輸出 ≠ 即時命令）。→ Wave 2 G3-02 ConfigStore + IPC toggle

## 6 工作組結構

| Group | 名稱 | Wave |
|---|---|---|
| G1 | Edge 危機根源修復 | W1 |
| G2 | 策略層改造 | W1-W2 |
| G3 | AI 多 Agent 接線 | W2 |
| G4 | ML 管線解凍 | W2-W3 |
| G5 | 架構 / 可讀性債務 | W2 |
| G6 | 合規 + 觀察性 | W1-W2 |

## 關鍵教訓

- **commit note 不可信**：10 agent 並行獨立讀代碼揭示 TODO/CLAUDE.md 3+ 處嚴重偏離實際（162 vs 1 cell / PostOnly 反向 / shadow hardcoded）
- **多角色 adversarial review** 有效：每個角色獨立發現盲點，PM/FA/QC/MIT 4 份 audit 各自首先標出 edge_estimates 問題
- **PA 整合 + PM Sign-off** 雙軌確保 FIX-PLAN 不跳過遺漏檢查（對照原 TODO 27 條活躍 `[ ]`，零遺漏）

## 應用

未來 TODO 重大重構時：
1. 先派 10 角色獨立 audit（禁合併），每個要求讀實際代碼
2. PA 整合 + 核實（不迷信 audit 文字）
3. PM Sign-off + 對照原 TODO 無遺漏
4. 每條新 TODO 帶 audit 指針
5. 歸檔舊版到 `docs/archive/<date>--todo_snapshot_pre_refactor.md`

# [Operator copy] PA RFC — G3-09 Phase C Intent Gate Design

> 完整 RFC: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_c_intent_gate_design.md`
> Date: 2026-04-28 · HEAD: `decf712`

## TL;DR

Phase C = cost_edge_advisor 從 Phase B observability 升級為 binding gate：當 advisor.status == Trigger 且 RiskConfig.cost_edge.gate_enabled=true 時，**IntentProcessor reject 新倉 SubmitOrder**（不阻平倉、減倉）。

## 主要 design choices

1. **Gate 在 Rust IntentProcessor Gate 1.7**（不在 Python ExecutorAgent，不在 Guardian，不在 IPC handler）— 唯一覆蓋 100% intent path 的注入點
2. **三層 default-off safeguard**：env=1 + cost_edge.enabled=true + **cost_edge.gate_enabled=true**（Phase C 新加 flag）
3. **只阻新倉**（is_reducing=true 完全跳過）— 嚴守 CLAUDE.md §二 #5 生存>利潤反向防線
4. **Dedup window 60s** 控 V026 INSERT 頻率，但 reject decision 本身不被 dedup 影響
5. **Per-strategy override + exempt** 給 emergency exit / risk-off 場景靈活性
6. **重用 Phase B V026 hypertable** 寫 reject log（`transition_from='GATE_REJECT:<strategy>'`）
7. **Python ExecutorAgent 0 改動** — 既有 `rejected_reason` 處理已 generic

## Wave 拆分

- **Wave 1 (Rust intent gate logic + log)** — E1 ~2d，10 files 改動
- **Wave 2 (Python ExecutorAgent metric)** — E1 ~1d，與 Wave 1 可並行
- **Wave 3 (Linux deploy + 7d observation)** — E4 active 0.5d + 7d passive

Wall-clock：~3-4d active + 7d observation period

## Key risks

1. **R-C1 False-positive reject 平倉** — Gate 1.7 之前 `is_reducing` 必須計算正確；複用 Gate 2.7 既有 pattern + unit test 釘死
2. **R-C5 Live mainnet 提早啟用** — TOML default false + Phase A RFC §8.3 Operator checklist 鎖死（≥7d demo Phase B 觀察通過 + Operator 顯式批准）
3. **R-C6 gate_enabled=true 後系統凍結** — IPC 60s rollback + healthcheck WARN at 1h continuous Trigger + per-strategy exempt fast escape

## Operator 下一步

1. 等 Phase B 觀察期 Tier 1 (≥48h, ~04-30) + Tier 2 (≥7d, ~05-04) deliverable 落地
2. PM 審 Phase B deliverable 確認 threshold calibration + trigger frequency 健康
3. PM Sign-off Phase C → 派 Wave 1 self-contained prompt template (§11) 給 E1
4. Wave 1+2 並行落地 → Wave 3 Linux deploy demo only enable
5. Live mainnet enable 走獨立 ticket + Operator 顯式批准（per Phase A RFC §8.3）

## 16 根原則合規

全 16 ✅；§四 5 項 live 硬邊界 0 觸碰；EX-01 P0/P1/P2 對齊 = P2（advisory + EV 過濾層）。

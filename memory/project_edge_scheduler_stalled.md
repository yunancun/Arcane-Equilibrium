---
name: edge_estimator_scheduler 停滯事件（2026-04-24 發現 → 同日修復）
description: 2026-04-20~24 停滯 1 cell 4d；operator commits f32629c (leader election) + abc85c0 (graceful shutdown) + 04-24 02:06 --rebuild 修復；現 187 cells / 59 updated/cycle / mtime <30min
type: project
originSessionId: f4abc469-afe6-401a-af27-a320525bab3c
---

## 狀態：✅ G1-01 完成（2026-04-24）

- 2026-04-24 10-Agent Audit 發現：`edge_estimates.json` 4 天停滯（MIT + QC + PM + FA 4 份獨立 audit 一致結論）
- 同日 operator 修復 + 部署：
  - `f32629c` Leader election（flock sentinel `/tmp/openclaw/edge_scheduler.leader.lock`，4 workers 搶奪解決）
  - `abc85c0` Graceful shutdown（OS 進程退出 + SIGKILL 自動釋放 fd）
  - 02:06 CEST `--rebuild` 部署
- 部署後驗證（Mac 接手 session 2026-04-24 ~12:53 UTC）：
  - `settings/edge_estimates.json` **187 top-level strategy::symbol cells**
  - `_meta.n_cells = 59`（本輪 cycle 更新量）
  - mtime <30min fresh

## JSON 結構 gotcha（`n_cells` 誤讀教訓）

`edge_estimates.json` **沒有** `cells` nested dict。結構是：
```json
{
  "_meta": { "updated_at": "...", "n_cells": 59, "grand_mean_bps": -5.88 },
  "grid_trading::1000PEPEUSDT": { "shrunk_bps": ..., "n": 13, "B": 1.0, ... },
  "ma_crossover::AAVEUSDT":     { ... },
  /* ... 187 個 strategy::symbol top-level keys */
}
```
- **`len(json.keys()) - 1` = total cells**（不含 `_meta`）
- **`_meta.n_cells`** = 本輪 cycle 更新了多少 cells（可以＜ total，某些 cell 沒新 fills 該輪沒碰）

Mac session 2026-04-24 接手 G1-02 時：
- 第一次 query 用 `d.get("cells", {})` → 得 0 cells，誤判 scheduler 死了
- Push-back + 深度診斷；SSH Linux 檢查 full JSON content 後才發現真實結構
- 教訓：讀陌生 JSON 結構前先 `d.keys()` 看 top-level，不要假設 nested dict

## 影響鏈解除後狀態

- ✅ P0-14 healthcheck [4] 數據可靠
- ⚠️ P1-14 cost_gate bind 條件（grand_mean > -50 bps + ≥2 策略 shrunk>0）仍未滿足 — 現 grand_mean=-5.88，≥2 策略條件需累積驗證（結構性 edge 問題，非 scheduler 問題）
- ✅ EDGE-DIAG-1 Phase 3 healthcheck [11] 數據可用
- JS shrinkage 仍需 n≥30 或 JS 多池才能統計有效（累積中）

## 警示保留（CLAUDE.md §三 敘述 vs runtime drift）

仍適用 — CLAUDE.md §三 寫的 cell 數可能過期 ≥2 日。新規則已入 `docs/lessons.md` + CLAUDE.md §七「§三 敘述 vs runtime drift 防線」：
- 關鍵健康指標必附 healthcheck script（強制，2026-04-23 規則）
- 被動等待 TODO 必附 check id
- CC 讀 §三 數字當決策輸入前必先實測 source-of-truth

## G1-01 相關 artifact

- Report: `.claude_reports/20260424_122700_g1_01_scheduler_recovery.md`（operator）
- Healthcheck: `passive_wait_healthcheck.py` [13] `edge_estimator_scheduler_fresh`（G6-02 新增 commit `a0a4981`）
- Leader sentinel: `/tmp/openclaw/edge_scheduler.leader.lock`（Linux 實存驗證）

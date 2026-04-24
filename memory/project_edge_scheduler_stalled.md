---
name: edge_estimator_scheduler 4 天停滯事件（2026-04-24 發現）
description: `settings/edge_estimates.json` 實測只有 1 cell（grid_trading::ORDIUSDT），mtime 2026-04-20 23:50，CLAUDE.md 宣稱 162 cells 嚴重過期；scheduler daemon 4 天未運行是 edge dormancy 的 root cause
type: project
originSessionId: f4abc469-afe6-401a-af27-a320525bab3c
---
## 發現時點
2026-04-24 10-Agent Audit 重構時，MIT + QC + PM + FA 4 份 audit 獨立發現。

## 實測事實（讀 Mac 本地檔）
```json
{
  "_meta": {
    "updated_at": "2026-04-20T23:50:17.941867+00:00",
    "n_cells": 1,
    "grand_mean_bps": -45.72754631909018
  },
  "grid_trading::ORDIUSDT": {
    "shrunk_bps": -45.7275,
    "raw_bps": -45.7275,
    "n": 3,
    "B": 0.0
  }
}
```

## 宣稱 vs 實際
- CLAUDE.md（2026-04-24 02:06 commit）：「edge_estimates 162/162 cells」+「每小時自動刷新」+「phys_lock fire 1-10/day」
- TODO.md（2026-04-24）：同上
- 實際：1 cell，4 天停滯

## 推測的 root cause（假說）

A. 僅 ORDIUSDT 跑：極不可能，多策略多 symbol 配置下不會只有 1
B. Scheduler daemon 崩潰：leader election flock 機制可能 OS 進程 exit 後未清理 sentinel
C. JSON 寫入 bug：邏輯錯誤阻斷多 cells 寫入
D. Python uvicorn 4 workers leader 搶奪問題

## 影響鏈
- P0-14 healthcheck [4] 「162/162 cells」結論虛假
- P1-14 cost_gate bind 條件（grand_mean > -50 bps + ≥2 策略 shrunk>0）永遠不滿足
- EDGE-DIAG-1 Phase 3 healthcheck [11] 數據依賴此 scheduler
- JS shrinkage estimator 在 n=3 統計無意義（需 n ≥30 或 JS 多池）

## 修復路徑（G1-01，Wave 1 W17/18）
1. Linux operator ssh trade-core 驗證 scheduler 運行狀態（flock sentinel + python 進程）
2. Stop + 手動 `trigger_now()` 驗證 scheduler 工作
3. 檢查 `edge_estimator_scheduler.py` leader election 邏輯
4. 加 healthcheck [13] 監控 `edge_estimates.json` mtime（應每小時更新）
5. 24h 後 n_cells 應恢復至 20+ 並持續增長

## 警示
**CLAUDE.md §三 寫的系統健康狀態不等於實際健康**。今後：
- 關鍵健康指標必附 healthcheck script（CLAUDE.md §七 2026-04-23 強制規則）
- 被動等待 TODO 必附 check id
- commit note / doc 文案需定期對比實際 runtime 狀態

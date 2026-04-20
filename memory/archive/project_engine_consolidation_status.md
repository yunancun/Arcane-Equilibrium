---
name: Engine 接線狀態（止損 / 學習 / 新聞）
description: 三引擎接線真實狀態 — 用戶會反覆問此問題，避免每次重查
type: project
originSessionId: 6e5876b4-539a-4c6b-968b-81d10da4e234
---
ARCH-RC1 後三個引擎的接線真相（更新至 2026-04-10）：

**止損引擎** ✅ 唯一 Rust
- `openclaw_core/src/stop_manager` 為唯一實現
- 由 `paper_state.check_stops` + `tick_pipeline` 消費
- Rust `openclaw_engine` = paper / demo / live 三模式唯一引擎
- Python 無任何止損邏輯（DEAD-PY-2 後 bridge_core.py 已刪除）

**學習引擎** ⚠️ 部分接上
- LearningConfig：✅ 載入 + 熱重載 + IPC `patch_learning_config` 可寫
- learning_store：⚠️ `main.rs` 注釋明確 "currently has no consumer"
- claude_teacher consumer loop：✅ 已 spawned，Phase 4.1 獨立組件
- **缺口**：LearningConfig → 學習動作的閉環尚未連通（非 Live blocker）

**新聞引擎** ✅ 完整接線（A2 完成 2026-04-10）
- 60s scheduler spawn loop 已接入 `main.rs`
- 3 providers（CryptoPanic free + CoinTelegraph RSS + Google News RSS）→ 去重 → severity → DB write → 4-09 三路 fan-out（Guardian/Regime/Learning）
- 受 `LearningConfig.switches.news_pipeline_enabled` 熱重載 gate 控制

**Why（用戶會問的原因）**：用戶定期確認三引擎接線狀態以判斷是否可以放權。學習引擎閉環是 Phase 6 範疇，**非 Live blocker**。

**How to apply**：被問到時直接給出三引擎狀態，不要重新 grep main.rs。

---
name: GUI 寫入面盤點 + Fake-Success 真相
description: 1C-3/1C-4 後 GUI 寫入路徑的真實分類，避免重做盤點 + 修正常見誤判
type: project
---

2026-04-08 P0 全 GUI 寫入面盤點結論（93 endpoints / 16 route 模組）：

## 三類寫入路徑

- **R = Rust IPC ✓**：risk_routes 全部 / paper session start/pause/resume/stop / ai_budget（11 個）
- **PR = Python + Rust IPC**：strategy activate/pause/stop（fire-and-forget 已在 commit `36d2533` 改 await）
- **P = Python STORE only**：~70 個，**大多數是合法的 Python 控制平面**，不是 fake-success

## ⚠️ 容易誤判的點

**Rust `TradingMode` 是冷參數**（`rust/openclaw_engine/src/config/mod.rs:327-332`）：只在啟動時讀 engine.toml，運行時 hot-reload 邏輯明確 preserve old value + log "requires restart"。**不能 hot-patch，新增 patch_runtime_mode IPC 是錯的**。

**Python `global_execution_mode_switch` 是 operator 授權平面**（disabled / observe_only / shadow_only / demo_reserved / live_reserved），不是 engine 執行模式。`state_compiler.py` 用它 gate 多個動作（lines 196/210/232/261/311/344/538/542/551）。Rust 只執行 IPC 進來的訂單；Python 控制平面決定要不要讓訂單進 IPC。**架構本來就對的**。

**所以 P0 報告中的「fake success」分類要重新理解**：
- demo arm/enable/validate / product-family / mode / recheck / safe-bundle 全部寫到 Python STORE 是**合法**的
- 看起來「假成功」是因為 **GUI 顯示刷新滯後** 或 **state_revision race**，**不是缺 IPC**

## 真實的 fake-success 架構 bug 只有 2 條

- `/strategy/{name}/activate|pause|stop` fire-and-forget IPC → **已修**（commit `36d2533`）
- `/strategy/dynamic-risk/toggle` Python flag 與 Rust ORCHESTRATOR 各有一份 → 二選一未做

## 用戶反復問的根因模板

被問 "GUI 某設置存了沒效果" 時，先確認三件事再開工：
1. 對應 endpoint 屬於 R / PR / P 哪類？P 類大多是顯示 bug 不是寫入 bug
2. 是否寫到 Python 控制平面（合法）vs 寫到 Rust ConfigStore（risk/learning/budget/strategy_params 4 個）
3. 用戶實測：toast 文字 / 顯示是否即時更新 / Network tab 的 POST status + body / 刷新頁面後是否生效

## How to apply

被問到 GUI fake-success 類問題時，**不要直接假設要新增 IPC**。先按上面三步走，多數情況是純前端顯示刷新 bug（類似 Task #3 在 `tab-risk.html:864-889` 翻轉 `gc ?? rStop` 的修法）。

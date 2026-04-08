---
title: GUI Fake-Success 修復 Wave 1（Tasks #3 #4 完成 / Task #2 待用戶實測）
date: 2026-04-08
session: gui-fake-success-wave1
ends_at_commit: 5a824d8
---

# Session 進度 — GUI Fake-Success Wave 1

用戶報告 GUI 大面積「假成功」失效：風控設置存後顯示舊值、雙引擎「停止」變「暫停」、全局模式切換失效等。本 session 完成 P0 全 GUI 寫入面盤點 + 修復 2 條最痛的 fake-success bug，第 3 條（Mode control）發現原 P0 分類錯誤，等用戶實測決定方向。

## P0 — GUI 寫入面盤點完成（Task #1）

Sub-agent 全掃 16 個 route 模組共 **93 個 POST/PATCH endpoint**，分類：

| 類別 | 數 | 說明 |
|---|---|---|
| **R** Rust IPC ✓ | 11 | risk_routes 全部 / paper session start/pause/resume/stop / ai_budget |
| **PR** 混合 fire-and-forget | 3 | strategy activate/pause/stop（IPC fail silent）|
| **P** Python STORE only | ~70 | 含 ~12 個 P0 標為「該到 Rust」+ ~58 個 OK（學習/治理/audit）|
| **D** Dead/410 | 8 | RC-10/RC-12 paper order 系列 |

**P0 報告中 Top 10 fake-success offender 對照三大用戶投訴**：
| 投訴 | 根因 | 修復票 |
|---|---|---|
| 全局模式切換失效 | `/input/config-change` mode 路徑（**P0 標 fake-success，實際分類錯**，見下） | Task #2（重新評估）|
| 風控設置 toast 成功但顯示舊值 | risk_routes ✅ 寫入 OK，**寫後沒驗證 + GUI 顯示優先順序錯**| Task #3 ✅ |
| 雙引擎「停止」變「暫停」| Rust 只有 Pause/Resume 無 native Stop | Task #4 ✅ |

## ✅ Task #4 — 雙引擎 stop 按鈕（commit 5a824d8）

**根因**：Rust 引擎只有 Pause/Resume 兩個 IPC 命令，無原生 Stop。`/session/stop` 實際是 close_all + pause_paper 組合，導致之後 `/session/status` 永遠回 `paused`，前端 stateMap 對應到「已暂停」。

**修復**（純 Python，不動 Rust）：`paper_trading_routes.py` 加模組級 sticky `_USER_STOPPED` 標誌：
- `/session/stop` 設 True
- `/session/start` + `/session/resume` 清為 False
- `/session/status` 看到 `is_paused=True` 時：若 `_USER_STOPPED` 報 `"stopped"`，否則 `"paused"`
- 前端 `tab-trading.html` stateMap 早就有 `'stopped': '已停止'`，**無需動 GUI**

## ✅ Task #3 — risk 寫後驗證 + 顯示刷新（commit 5a824d8）

**雙重病灶**：

1. **`tab-risk.html` 顯示優先順序錯**（lines 864-889）。所有 stop manager / position / cooldown 只讀指標用 `rStop ?? gc`：
   - `rStop = cfg.rust_active.stop_config` 來自 `reader.get_snapshot()`（state-reader 快照，由 tick 推送，**滯後一拍**）
   - `gc` 來自 `client.refresh_config()`（即時 ConfigStore IPC，**fresh**）
   - 存完馬上讀：snapshot 還是舊值 → 顯示舊值或「OFF」→ 用戶看到 fake-success
   - **修復**：翻轉成 `gc ?? rStop`，fresh ConfigStore 優先

2. **`risk_view_client._patch()` 缺寫後驗證**：Rust 若靜默丟棄 patch（IPC 回成功但 ConfigStore version 沒前進），risk_routes 仍回 200 → GUI 顯示「Saved!」但實際沒寫入
   - **修復**：snapshot prev_version → patch → refresh → 若 version 沒前進，raise `RuntimeError`，bubble 到 risk_routes 5xx
   - **附帶**：`_patch` 在無 IPC client 時也改為丟錯（之前靜默回 `{}`）

**測試房務**（順手清理 1C-3-C 留下的測試債）：
- `test_update_global_config_calls_patch_with_operator` — 用 nested input 但 `_remap_global_to_rust` 期望 flat → patch 始終為 `{}`
- `test_update_category_config_wraps_patch` — 沒對 `max_leverage` → `leverage_max` remap
- `test_agent_adjust_uses_agent_source` — 同樣 nested 餵入 flat mapper
- 上述 3 個自 1C-3-C 後就一直在 baseline 失敗清單裡（pre-existing fail），今天順手修對
- 新增 `test_patch_raises_when_version_not_advanced` 守 silent-drop guard
- 更新 `test_no_ipc_client_safe` 預期寫入丟錯而非靜默回 `{}`

**測試結果**：164/164 risk-related tests pass · 2 session start/stop tests pass · Rust binary 不動。

## ⏸️ Task #2 — Mode control（原 P0 分類錯誤，待用戶實測決定方向）

**深挖後發現原前提錯誤**：

1. **Rust `TradingMode` 是冷參數**（`rust/openclaw_engine/src/config/mod.rs:327-332`）：
   ```rust
   if old.trading_mode != new_config.trading_mode {
       warn!("trading_mode changed but is cold — preserving old value, requires restart");
       new_config.trading_mode = old.trading_mode;
   }
   ```
   Rust 引擎 trading_mode 只在啟動時讀 engine.toml，**無法 hot-patch**。

2. **Python `global_execution_mode_switch` 才是正確控制平面**：值是 `disabled / observe_only / shadow_only / demo_reserved / live_reserved`，這是 **operator 授權平面**，不是 engine 執行模式。`state_compiler.py` 用它 gate 多個動作（lines 196/210/232/261/311/344/538/542/551）。Rust 只執行 IPC 進來的訂單；Python 控制平面決定要不要讓訂單進 IPC。**架構本來就對的**。

3. **「fake success」分類重新洗牌**：P0 報告中 #1 #2 #3 #5 #6 #8 #9（demo arm/enable/validate / product-family / mode / recheck / safe-bundle）全部是 Python 控制平面合法寫入，Rust 不需要知道。看起來像 fake success 是因為**顯示刷新或 revision race**，**不是缺 IPC**。

4. **真正剩下的「fake success 架構 bug」只有 #10**：strategy dynamic_risk Python flag 與 Rust 各有，需二選一統一。（#4 #7 strategy activate/pause 已被 commit `36d2533` 修了：fire-and-forget → await）

5. **用戶實際看到「切換失效」可能根因**（按概率排序）：
   - (a) 顯示刷新 bug（同 Task #3 病灶）：POST 成功，`loadAll()` 800ms 後讀的 `global_mode_state` 沒更新顯示
   - (b) state_revision race：GUI 先 GET 拿 rev，再 POST 帶 rev，中間若有寫入 bump rev → 409 mismatch → null → toast「請求失敗」
   - (c) `result.action_result === 'success'` 檢查可能因 envelope 結構不對 false → error toast

**待用戶實測 3 件事後再修**：
- A. 雙引擎停止按鈕：toast 文字 + badge 是否顯示「已停止」
- B. 風控設置存後：顯示是否即時更新；故意停 Rust 引擎是否看到 5xx
- C. **全局模式切換**：F12 開 console，回報 toast 文字 / chip 是否變 / console 錯誤 / Network tab 的 POST /input/config-change status + body / 重新整理頁面後是否生效

## 接下來建議排序

| 優先 | 任務 | 估時 | 阻塞 |
|---|---|---|---|
| P0 | 用戶實測 A/B/C → 回報 → 針對性修 #2 | — | 用戶 |
| P1 | DEAD-PY-1 Phase 1 SAFE-DELETE | ~2h | 無 |
| P1 | A2 NewsPipeline scheduler | ~5h | 4-09 router 決策 |
| P2 | 7d paper trading 觀察期啟動 | 7天 | 無 |
| P2 | OC-3 多通道告警 | ~1週 | 無 |
| P3 | Phase 5 spec 起草 | ~1週 | 觀察期數據 |

## Compact 後接手 checklist

1. `git log --oneline -8` 確認 HEAD = `5a824d8`（Wave 1 修復）
2. 讀 memory `project_engine_consolidation_status.md` 拿三引擎接線狀態
3. **若用戶已回報實測結果**：直接針對 C 的具體症狀修 Task #2（最可能是純前端顯示刷新，類似 Task #3）
4. **若用戶尚未實測**：先請用戶執行 A/B/C
5. P0 完整 93-endpoint 盤點表格在本 worklog 描述但**未存檔**（在 sub-agent 輸出，已 condense 進 commit message + 此 worklog）。若需要完整表，可重跑 sub-agent 或從本 session 的對話歷史撈

## Commit 鏈

```
5a824d8 fix(gui): kill 2 fake-success bugs — risk display refresh + dual-engine stop label  ← 本 session 唯一 commit
36d2533 fix(strategy): wire activate/pause/stop to Rust set_strategy_active IPC              ← session 開始前已存在
3688225 fix(risk-gui): wire GUI stop-loss fields to Rust IPC correctly                       ← session 開始前已存在
```

# 工程日誌：LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN 修復
# Engineering Log: Live Auth Watcher Event Consumer Spawn Fix

日期：2026-04-27
作者：E1
類型：P0 Silent Regression 修復 + 部署
關聯 commits：588d207、0fa41b1、merge 1fac9b1

---

## 背景（為什麼要做這個）
## Background (Why)

2026-04-19 引入 `LiveAuthWatcher`（commit `d92f25d`，PIPELINE-SLOT-1 Phase 2 的一部分）後，存在一條不完整的 respawn 路徑。運算邏輯上，operator 執行 `POST /api/v1/live/auth/renew` → watcher 觸發 respawn → 但 respawn 只呼叫了 `slot_op.try_spawn` → `build_exchange_pipeline`（三個 task：WS supervisor / listener / balance refresh），**從未呼叫 `spawn_live_pipeline`**。

The `LiveAuthWatcher` introduced in commit `d92f25d` (2026-04-19) contained an incomplete respawn path. On operator `POST /api/v1/live/auth/renew`, the watcher respawned the exchange pipeline (3 tasks) but never called `spawn_live_pipeline`, meaning `run_event_consumer` OS thread was never created via the watcher path.

觸發時機的設計邏輯是：manual restart 時 `startup.rs` 刪除 `authorization.json`（這是有意為之的安全設計）。engine 啟動時走 `(None, None) → None` 分支，`spawn_live_pipeline` 在 boot time 也不被呼叫（`pipelines="paper+demo"`）。後續任何 operator approve → watcher respawn 皆走不完整路徑，`run_event_consumer` OS thread 從此不存在。

這個 bug 在 2026-04-19 15:37 第一次 manual restart + renew 後開始影響生產，**靜默持續 8 天（2026-04-19 ~ 2026-04-27）**，屬 P0 Silent Regression。

This was a P0 silent regression: the bug was triggered on 2026-04-19 15:37 with the first manual restart + renew after the watcher was deployed, and went undetected for 8 days.

---

## 次生災害（8 天靜默期間累積）
## Cascading Failures (8-day silent accumulation)

| 影響面 | 具體現象 | 根因鏈 |
|--------|---------|--------|
| `pipeline_snapshot_live.json` | 凍結於 2026-04-19 15:37，GUI 誤判 live engine 掛掉 | event_consumer 不存在 → 沒有快照寫入 |
| `live_state.json` | 同上凍結 | 同上 |
| `trading.fills` | Live engine 記錄 0 row（8 天空白）| event_consumer 未跑 → fill 事件無人消費 |
| `learning.exit_features` | 0 row（8 天空白）| 同上 |
| `learning.decision_features` | 0 row（8 天空白）| 同上 |
| `shadow_fill` | 0 row | 同上 |
| Demo reconciler | 誤將 LiveDemo 帳戶持倉視為自己的（cross-engine 污染）| 快照過期、reconciler 持倉歸因錯誤 |

**重要限制**：8 天 Live ML 資料空白**無法回填**。修復後只能從新資料開始累積。Live 學習平面完全空白這段歷史是無法補救的損失。

A critical secondary consequence is that 8 days of Live ML training data (fills, exit_features, decision_features) are permanently lost. Post-fix data will accumulate from scratch.

---

## 根因分析（精確）
## Root Cause Analysis (Precise)

**根本原因**：`live_auth_watcher.rs` 的 respawn arm 是 `build_exchange_pipeline` 的**不完整鏡像**（incomplete mirror of `spawn_live_pipeline`）。

設計上，`spawn_live_pipeline` 做兩件事：
1. `build_exchange_pipeline`（WS supervisor + listener + balance refresh）
2. `spawn_event_consumer`（OS thread：`run_event_consumer`）

watcher respawn arm 只做了第 1 件，第 2 件被遺漏。

**為何之前沒被發現**：
- 問題只在「watcher respawn 路徑」上存在；engine 全新啟動（無 authorization.json）根本不跑 `spawn_live_pipeline`（boot 走 None 分支）。
- 3 個 WS task 仍在工作，外部監控看起來「部分正常」。
- `pipeline_snapshot_live.json` 凍結不會告警，GUI 誤讀為「engine 暫時無回應」，而非「event_consumer 從未 spawn」。
- 沒有 healthcheck 覆蓋「event_consumer OS thread 是否存活」。

**Why it wasn't caught earlier**: The 3 WS tasks were still running (WS supervisor/listener/balance refresh), creating a false appearance of partial health. The snapshot freeze was misread as transient engine unresponsiveness rather than a structural missing thread.

---

## 關鍵決策
## Key Decisions

### 決策 1：用 callback（`LivePipelineSpawner` Arc Fn）而非直接呼叫

**選項 A**（被否決）：在 `live_auth_watcher.rs` 直接 `use crate::main_pipelines::spawn_live_pipeline`，在 respawn arm 呼叫。

**問題**：`spawn_live_pipeline` 需要 19 個 Arc 欄位，直接呼叫會把所有欄位注入到 watcher struct 中，造成 watcher 巨型依賴（fat struct）且與 startup 邏輯深度耦合，違反單一責任。watcher 的職責是「觀察 auth 狀態 + 觸發 callback」，而非「知道如何 spawn pipeline」。

**選項 B（採用）**：定義 `LivePipelineSpawner = Arc<dyn Fn() -> ... + Send + Sync>` callback；在 `main.rs` boot None path 構造 closure 捕獲所需的 19 Arc 欄位，注入 watcher；watcher 只呼叫 callback，不持有 pipeline 依賴。

**理由**：職責分離——watcher 不需要理解 pipeline 的構造；未來若 spawn 邏輯改變只需修改 closure 構造側，watcher interface 不動。

The callback pattern (`LivePipelineSpawner = Arc<dyn Fn() + Send + Sync>`) was chosen over direct function calls to preserve separation of concerns. The watcher's responsibility is auth-state observation + trigger, not pipeline construction.

---

### 決策 2：JoinHandle 必須存入 `thread_handle_slot`

E2 round-1 提出的 blocker：respawn 時生成的 OS thread JoinHandle 如果不持有，thread 會在 detach 後無 supervisor 管理，無法做優雅 teardown。

修復後：watcher 的 spawn callback 回傳 `JoinHandle<()>` → 存入 `thread_handle_slot`（`Arc<Mutex<Option<JoinHandle>>>`）；teardown arm 取出 handle → join（帶 timeout）→ 清空 slot。

The `JoinHandle` from the respawned OS thread must be stored in `thread_handle_slot` for graceful teardown. E2 round-1 flagged this as a blocker when the initial implementation left the thread untracked.

---

### 決策 3：teardown arm 必須清空 `live_cmd_slot` + `live_event_slot`

**問題**：watcher teardown（auth 失效）後，stale sender 仍在 slot 中。下游（reconciler、scheduler）讀取 `live_cmd_slot` 的舊 sender，發出的 commands 會打到已死的 channel，造成 ghost command 問題。

**修復**：teardown arm 在 join thread 後 `live_cmd_slot.write().take()` + `live_event_slot.write().take()`，確保 slot 清空。新的 respawn 路徑填入新 sender。

Teardown must clear both `live_cmd_slot` and `live_event_slot` to prevent stale sender ghost commands. This is a correctness invariant: after teardown, any downstream attempt to read these slots must see `None`, not a dead sender.

---

### 決策 4：測試拆至獨立 `live_auth_watcher_tests.rs`（975 行）

`live_auth_watcher.rs` 本身已接近 §九 800 行警告線；將 975 行測試拆出，確保主體模塊未來擴展仍有空間。測試覆蓋：happy path（spawn → teardown → respawn）+ error path（callback panic / channel close）+ timeout 路徑 + mock spawner。

Tests split to `live_auth_watcher_tests.rs` (975 lines) to keep `live_auth_watcher.rs` within the §九 800-line warning threshold and maintain room for future expansion.

---

## 實現細節（重要實現點與邊界情況）
## Implementation Details

### `live_auth_watcher.rs` 變更

- 新增 `LivePipelineSpawner` type alias：`Arc<dyn Fn() -> Result<JoinHandle<()>, SpawnError> + Send + Sync>`
- `LiveAuthWatcher::new()` 加入 `spawner: Option<LivePipelineSpawner>` 參數
- respawn arm（`AuthEvent::Renewed`）：若 `spawner.is_some()` → 呼叫 callback → store `JoinHandle`
- teardown arm（`AuthEvent::Expired` / `AuthEvent::Revoked`）：join thread（5s timeout）→ 清空 `live_cmd_slot` + `live_event_slot` → 清空 `thread_handle_slot`
- **不變量 / Invariant**：`thread_handle_slot` 持有的 handle 必須對應「當前正在跑的 event_consumer 迭代」。若兩次 renew 之間 teardown 未完成，第二次 renew 的 callback 必須等待前一個 handle join 後才能啟動新 thread，避免兩個 event_consumer 並行（duplicate writes）。

### `main_pipelines.rs` — `LiveSpawnBundle` + `build_live_pipeline_spawner`

- 新增 `LiveSpawnBundle` struct：打包 19 個 pipeline 依賴 Arc（為何是 struct 而非直接 closure 展開：bundle 提供命名欄位，未來加欄位有類型錯誤保護，不靠位置傳參）
- `build_live_pipeline_spawner(bundle: LiveSpawnBundle) -> LivePipelineSpawner`：從 bundle capture 構造 closure，閉包內呼叫完整 `spawn_live_pipeline` 等價邏輯（含 event_consumer）

The `LiveSpawnBundle` struct was chosen over anonymous closure capture to provide named-field compile-time safety when adding new dependencies. Positional argument passing would be error-prone at 19 fields.

### `main.rs` — boot None path 注入

- boot Some path（有 authorization.json）：邏輯不變，直接呼叫 `spawn_live_pipeline`
- boot None path（無 authorization.json，常見於 manual restart）：構造 `LiveSpawnBundle` → `build_live_pipeline_spawner` → 注入 watcher
- **邊界情況**：`main.rs` 目前為 **1194 行**，距 §九 1200 硬上限剩 **6 行**。本次改動已是 §九 明確的 WARN 觸發點（見「已知限制」）。

### `main_fanout.rs` — live receiver 改 `LiveEventSenderSlot`

- 舊設計：live event receiver 在 fanout 時直接持有 static sender（boot time 定死）
- 新設計：改為 `LiveEventSenderSlot`（`Arc<RwLock<Option<Sender>>>`），動態讀取；respawn 時 watcher 填入新 sender，fanout 無感換到新 channel
- **重要**：這是讓 watcher respawn 的 event pipe 真正「接通」的關鍵步驟；若不做此修改，新 event_consumer 會等待事件但 fanout 仍往舊 channel 發送（dead channel）。

### `ipc_server/engine_routing.rs` — `live_snapshot()` + `set_live_cmd_sender_slot`

- 新增 `live_snapshot()` IPC handler：讀 `pipeline_snapshot_live.json`（由 event_consumer 寫入）；teardown 後正確回傳 None，而非用 stale snapshot 誤導 GUI
- `set_live_cmd_sender_slot`：允許 IPC 在 teardown 後拒絕 live commands（回 `None`），避免 stale send 在 IPC 層造成誤導性成功回應

---

## 工作流程
## Workflow

全鏈在 2026-04-27 單日完成：

1. **PA RCA** → 確認 event_consumer 從未 spawn 是根因（非快照 staleness、非 WS 斷線）
2. **PA/Explore 並行** → 確認影響範圍（8 天 × 4 ML table × Demo reconciler 污染）
3. **E1 實作** → commits 588d207 + 0fa41b1
4. **E2 round-1** → 退回：2 blocker（JoinHandle 未持有 / teardown 未清空 slots）+ 3 high（測試未覆蓋 timeout / mock spawner interface / panic safety）
5. **E1 round-2 修復** → 全數解決
6. **E2 round-2** → `APPROVE_WITH_NITS`（nit：文件注釋三處中文補全，不阻合併）
7. **E4** → `PASS`（2252 / 0 failed，含 +1 happy path 測試）
8. **commit/merge/push** → merge commit 1fac9b1
9. **Linux `--rebuild`** → binary 部署（Linux PID 2809508，25s 真正重編確認）

**E2 round-1 退回的 2 個 blocker 值得記錄**：兩者都屬「spawn 了就忘了」的典型 Rust async/thread 模式錯誤——有 handle 不持有 = detached thread 無 supervisor；sender 不清 = stale ghost command。這類 bug 在 code review 前很難靠靜態分析發現（Rust 不強制 JoinHandle join）。

The 2 E2 round-1 blockers both exemplify the "spawn and forget" anti-pattern in Rust: not storing the JoinHandle means the thread runs unsupervised and cannot be gracefully shut down; not clearing the sender slot creates ghost command channels. Rust's type system does not enforce JoinHandle consumption, making this class of bug code-review-dependent.

---

## 測試結果
## Test Results

| 測試類型 | 平台 | 結果 |
|---------|------|------|
| engine lib | Mac | 2252 / 0 failed ✓ |
| engine bin | Mac | 53 / 0 failed ✓（+1 happy path）|
| engine lib | Linux baseline | 2252 / 0 failed ✓ |
| E2 審查 | round-2 | `APPROVE_WITH_NITS` |
| E4 回歸 | — | `PASS` |

新增測試覆蓋場景（`live_auth_watcher_tests.rs`）：
- `test_respawn_happy_path`：spawn → teardown（join 確認）→ respawn → teardown（最終清空驗證）
- `test_teardown_clears_slots`：teardown 後讀 `live_cmd_slot` / `live_event_slot` 均為 None
- `test_spawner_callback_panic_safety`：callback panic 不讓 watcher thread 崩潰（catch_unwind）
- `test_stale_handle_not_overwritten`：並發 renew 的 handle race condition 保護

---

## 已知限制
## Known Limitations

### 1. TODO [P1] LIVE-RECONCILER-STALE-CMD-TX

本次修復確保了 watcher respawn 後新的 event_consumer 正確 spawn，並且 fanout sender 正確更新。但 **reconciler 和 scheduler 仍可能持有 teardown 前的舊 `cmd_tx`**，導致 Live 5-min 縮倉輪詢在 watcher teardown + respawn 後失效。

修法方向：reconciler / scheduler 改走 `LiveCmdSenderSlot` snapshot 取得最新 sender，而非在 init 時 capture 一個靜態 sender。此改動需獨立 PR 避免本次 scope 擴大。

This fix does not address reconciler/scheduler holding stale `cmd_tx` post-teardown+respawn. The Live 5-min position reduction polling will malfunction after a watcher cycle. Fix: change these consumers to snapshot from `LiveCmdSenderSlot` rather than capturing a static sender at init time.

### 2. WARN：main.rs 1194 行

`main.rs` 目前 1194 行，距 §九 1200 硬上限剩 6 行。本次改動是直接原因之一（boot None path 的 bundle 構造約佔 10 行）。**下次任何 touch main.rs 必須先拆模塊**，否則 E2 硬拒。候選拆分：boot path（`startup_pipelines.rs`）+ watcher injection（`watcher_init.rs`）。

`main.rs` is at 1194 lines, 6 lines from the §九 1200 hard cap. Any future `main.rs` touch must begin with a module split. Candidates: boot pipeline path → `startup_pipelines.rs`; watcher injection → `watcher_init.rs`.

### 3. 8 天 Live ML 資料不可回填

`trading.fills`、`learning.exit_features`、`learning.decision_features`、`shadow_fill` 中 2026-04-19 15:37 ~ 2026-04-27 的 Live 記錄為 0 row，且無法從事後重建（沒有 fill events 的 replay source）。修復後新資料從 2026-04-27 起累積，Live 學習平面從零開始。**這對 Live 上線前的 ML 訓練資料充足性有影響，需納入 P0-2 21d 穩定期的等待成本評估**。

8 days of Live ML data (fills, features) are permanently unrecoverable. This affects the Live launch readiness timeline (P0-2 21d demo stability) since the Live-mode ML training set must be rebuilt from the post-fix date.

### 4. Demo reconciler cross-engine 污染

因快照凍結，Demo reconciler 在 8 天內誤將 LiveDemo 帳戶持倉歸因為自己的持倉，已積累若干錯誤 reconciliation 記錄。待獨立 audit（非本次 PR scope）。

### 5. 部署後等待 operator 操作

修復後的 binary 已部署（Linux PID 2809508），但 Live pipeline（event_consumer）尚未真正 spawn——需 operator 執行一次 `POST /api/v1/live/auth/renew`，觸發 watcher respawn arm（走修復後的完整路徑），OS thread 才會建立，`pipeline_snapshot_live.json` 才會開始更新。**這一步不會自動發生**。

Post-deploy, the fixed binary is live, but the `run_event_consumer` OS thread will not exist until the operator triggers `POST /api/v1/live/auth/renew`. The fix requires an explicit operator action to take effect; it does not self-activate on restart.

---

## 設計哲學備忘
## Design Philosophy Notes

**為什麼 `startup.rs` 在 manual restart 時刪 `authorization.json`**：這是有意為之的安全設計。每次 engine 重啟強制 operator 重新授權，防止舊的 auth token 被遺留使用（授權應該是有意識的行為，不是重啟的副作用）。這個設計是正確的，只是 watcher respawn path 沒有跟上。

**為什麼 event_consumer 是 OS thread 而非 tokio task**：`run_event_consumer` 需要做阻塞式 DB 寫入，tokio task 不適合長時間佔用 executor thread。OS thread 隔離阻塞操作，與 async runtime 解耦。這個選擇解釋了為什麼 `JoinHandle<()>` 是 `std::thread::JoinHandle` 而非 `tokio::task::JoinHandle`。

The `run_event_consumer` is an OS thread (not tokio task) because it performs blocking DB writes. Mixing blocking I/O with async executors is an anti-pattern in Rust async; OS thread isolation is the correct design. This is why the `JoinHandle` type is `std::thread::JoinHandle`, not `tokio::task::JoinHandle`.

---

## Follow-up Tickets 索引

| 票號 | 優先級 | 標題 | 狀態 |
|------|--------|------|------|
| LIVE-RECONCILER-STALE-CMD-TX | P1 | Reconciler/scheduler stale cmd_tx 修法 | Open |
| MAIN-RS-SPLIT-1 | WARN | main.rs 1194 行 → 必須在下次 touch 前拆模塊 | Open |
| LIVE-ML-BACKFILL-LOST | INFO | 8 天 Live ML 資料永久空白（不可回填，需計入 P0-2 時程） | Open |
| DEMO-RECONCILER-CROSS-ENGINE | P2 | Demo reconciler cross-engine 污染獨立 audit | Open |

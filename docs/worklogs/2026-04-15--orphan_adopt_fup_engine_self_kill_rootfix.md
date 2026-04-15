---
date: 2026-04-15
topic: ORPHAN-ADOPT-1 FUP — engine self-kill root-cause fix (Option B)
status: IMPLEMENTED + TESTED (not yet deployed)
scope: rust/openclaw_engine/src/{paper_state, position_reconciler/*, event_consumer/*, main.rs}
operator_directive: "B 從根本上修" — root-cause fix, not a symptomatic mute
---

# ORPHAN-ADOPT-1 FUP — Engine Self-Kill Root-Cause Fix

## 一、Bug Description（現象）

Post-ORPHAN-ADOPT-1 Phase 1 deployment (2026-04-14)，demo 引擎在 ~3 小時窗口
內觀察到：
- demo 策略自主新開 **85 entries**
- reconciler reaper 平倉 **76 closes**（~89% ratio）
- funding_arb：**7 entries / 0 natural exits** — 全被 reaper 收掉
- 每個新倉平均存活 30–60s 即被強平

G-2 FundingArb 監控 daemon 停滯根因 = 此 bug：策略永遠湊不到「20 fills 自然
結算」樣本，因為自然結算從來不發生 — 永遠先被 reconciler 吃掉。

## 二、Root Cause（根因）

`position_reconciler::process_orphans()` 以 **30 秒輪詢週期**的 REST snapshot
對比「上一輪 baseline」，classification 產生的 `DriftVerdict::Orphan` =
「當前 Bybit snapshot 有、上一輪 baseline 沒有」。

問題：**baseline 的「上一輪」在時間上落後於策略剛剛送出並 fill 的新倉。**

完整時間線：
1. t=0s    : baseline = 空（或舊集合）
2. t=5s    : 策略 fire intent → Bybit 成交 → paper_state.apply_fill() 登記
3. t=30s   : reconciler cycle → REST snapshot 看到新倉 → baseline 沒有
             → classify 判 `DriftVerdict::Orphan`
4. t=30.1s : `process_orphans()` 未做任何 cross-check → dispatch
             `PipelineCommand::CloseSymbol { hint_is_long, hint_qty }`
5. t=30.5s : 引擎平掉自家剛成交的倉

ORPHAN-ADOPT-1 Phase 1 原設計是「抓外部孤兒」（operator 手動、外部工具、
exchange 條件單自動觸發），但**沒有區隔「我自己剛成交的倉」vs「真正的外部
孤兒」**。結果：引擎 30s 間歇殺自己的倉，策略全無生還機會。

## 三、Design — Option B Root-Cause Fix

### 3.1 Side-car 鏡像 pattern

在 `PaperState` 上掛一個 **side-car mirror**：
```rust
positions_mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>
//                  symbol → is_long
```
- Writer：`PaperState` 本身（apply_fill / upsert / close_position / reduce_position
  / import_positions / reset 六個路徑全部鏡像同步）
- Reader：`OrphanHandlerConfig.engine_positions_mirror`（reconciler cycle 開頭
  snapshot 一次）
- 同 Arc handle 在 reconciler spawn 時就建立，由 `EventConsumerDeps.positions_mirror`
  在 `run_event_consumer()` 內透過 `PaperState::set_positions_mirror(...)` 傳入
  — 兩端共享同一個 Arc。

### 3.2 Suppression 邏輯

`process_orphans()` cycle 頂層 snapshot 一次鏡像，逐個 Orphan 檢查：
```rust
let expected_is_long = side == "Buy";
if let Some(&tracked_is_long) = engine_mirror_snapshot.get(sym) {
    if tracked_is_long == expected_is_long {
        info!(...);  // 抑制孤兒：引擎已持倉（剛成交 race）
        continue;     // 完全丟棄 verdict — 連 evaluate_actions 也看不到
    }
}
```

**重點**：suppression 發生在 dedup stamp 與 dispatch **之前**，所以：
- 不下平倉單（不產生 CloseSymbol command）
- 不登記 dedup 戳記（pending_orphan_closes 保持空）
- 不產生 drift 證據給 `evaluate_actions()`（不會升級 RiskLevel）

### 3.3 為什麼不用 `PaperState.positions` 直接讀？

- `PaperState` 是 `TickPipeline` 的欄位，reconciler 在背景 task 裡跑 — 直接
  借用會違反 Rust 的 `&mut self` 獨占律。
- 改用 side-car Arc + RwLock：writer（PaperState）和 reader（reconciler）
  各自獨立，parking_lot 非毒化、tokio await-safe。
- 額外好處：test 側可以直接構造 mirror 不用建整個 PaperState。

### 3.4 Reset 指令的 Arc 保留

`PipelineCommand::Reset { new_balance }` 會把 `PaperState` 整個替換成新實例。
handler 修改成：
```rust
let shared_mirror = pipeline.paper_state.positions_mirror();
pipeline.paper_state = PaperState::new(new_balance);
pipeline.paper_state.set_positions_mirror(shared_mirror);  // 保留同一 Arc
```
Reconciler 端的 Arc 仍指向同一塊 RwLock — reset 會 clear mirror，但不會斷連。

## 四、Files Changed

| File | 改動 |
|---|---|
| `paper_state.rs` | 新增 `positions_mirror` 欄位 + `Arc::new` 初始化；`positions_mirror()` / `set_positions_mirror()` 公開 API；`positions_insert/remove/clear` 3 private helpers；10 個 mutation site（import_positions / upsert 兩條分支 / apply_fill 4 site / close_position / reduce_position）全部鏡像同步 |
| `position_reconciler/orphan_handler.rs` | `OrphanHandlerConfig` 新增 `engine_positions_mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>` |
| `position_reconciler/mod.rs` | `process_orphans()` cycle 頂層 snapshot 鏡像 + 每 Orphan suppression 檢查 |
| `event_consumer/types.rs` | `EventConsumerDeps` 新增 `positions_mirror: Option<Arc<...>>` |
| `event_consumer/mod.rs` | `run_event_consumer()` 解構 `positions_mirror` 並在 seed_positions 後 `set_positions_mirror(...)` 注入 |
| `event_consumer/handlers.rs` | `PipelineCommand::Reset` handler 保留 Arc handle 跨 PaperState 替換 |
| `main.rs` | 三個 per-engine Arc（paper/demo/live）在 reconciler spawn 前建立；`build_orphan_cfg` closure 依 engine_key 選對應 mirror；3 次 `EventConsumerDeps` 構造各自傳入 `Some(Arc::clone(&X_positions_mirror))` |
| `position_reconciler/tests.rs` | 2 個新 test：`orphan_suppressed_when_engine_owns_position`（正向）+ `orphan_dispatched_when_engine_side_mismatches`（反向保底） |

Delta：+319 / -10（8 files）。

## 五、Test Coverage

### 正向（suppression fires）
`orphan_suppressed_when_engine_owns_position`:
- mirror 塞 `("BTCUSDT", true)`
- Bybit raw snapshot 含 `BTCUSDT "Buy"` + Orphan drift
- `process_orphans()` 返回 kept.is_empty() = true
- mpsc channel 無訊息（`rx.try_recv().is_err()`）
- `state.pending_orphan_closes` 保持空（suppression 在 dedup 之前）

### 反向（suppression 不誤觸發）
`orphan_dispatched_when_engine_side_mismatches`:
- mirror 塞 `("BTCUSDT", true)` — 引擎是 LONG
- Bybit 顯示 `BTCUSDT "Sell"` — SHORT，方向不符
- Suppression 不觸發，走正常 handler → Stage C `SoftConservative` → CloseSymbol
- 斷言 cmd channel 收到 `CloseSymbol { symbol="BTCUSDT", hint_is_long=Some(false) }`

### 結果
- `cargo build --release -p openclaw_engine`：**clean**（僅 pre-existing warnings）
- `cargo test -p openclaw_engine --lib`：**1266 passed / 0 failed**（+9 淨增）
- `cargo test -p openclaw_engine --lib position_reconciler`：**60 passed / 0 failed**

## 六、Deployment（尚未執行）

Operator scope。部署步驟：
```bash
cd /home/ncyu/BybitOpenClaw/srv/rust && cargo build --release -p openclaw_engine
bash /home/ncyu/BybitOpenClaw/srv/helper_scripts/restart_all.sh
```
**注意**：`--rebuild` flag 只重 PyO3 .so，不重 engine binary。此修需手動
`cargo build --release`（memory: `feedback_restart_rebuild_flag_scope`）。

部署後預期行為：
- 策略開倉 → reconciler 下一輪 30s tick 看到 → **suppression 檢查 mirror**
  → 鏡像已有同方向 → 丟棄 Orphan verdict，不平倉
- 真正的外部孤兒（operator 手動、外部工具）仍會被 Phase 1 Stage A/B/C 正常處理
- G-2 FundingArb daemon 停滯自動解除（fills 終於可以自然結算）

## 七、Follow-ups（not part of this fix）

1. **Phase 2 真 Adopt 路徑**：目前 suppression 只是「不殺自己」，但真正的
   外部孤兒仍走 Phase 1 保守平倉。Phase 2 需接 G-1 R-02 Strategist agent
   「同方向信號」語義 + synthetic StrategyId 注入 paper_state。
2. **Monitoring**：deployment 後應在 grafana / logs 看到 `orphan suppressed:
   engine already owns position (fresh-fill race)` info 日誌 — 新增告警模板
   當此日誌爆量（>10/min）表示 mirror 寫入有漏點。
3. **Edge case**：`reduce_position` 與 `apply_fill` 的 partial-close 分支目前
   鏡像保留 is_long（因為仍有剩餘倉位）。完整關倉才會 `positions_remove`。
   此行為 correct but subtle — 未來若加 hedge mode，需要重新檢視
   `(symbol, side)` 雙維度鏡像。

## 八、Related Memory / Context

- `memory/project_fa_phantom_bug.md`：FA-PHANTOM-1 是**不同**的 bug（fast_track
  誤用 notional/balance 當 margin_util，全策略系統性被平）。本 bug 是
  reconciler 自殺路徑，兩者獨立。
- `memory/project_g2_funding_arb_monitor.md`：G-2 daemon 停滯 root cause =
  本 bug。部署後 daemon 應自動恢復進度。
- `memory/feedback_restart_rebuild_flag_scope.md`：部署需 manual cargo build。

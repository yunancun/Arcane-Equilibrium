# Packet C / C4 — Notification Failsafe Pipeline Wire (runtime-live)

**Spec date**: 2026-05-29
**Author**: PA
**Ticket**: `P2-PACKET-C-C4-PIPELINE-WIRE`
**Status**: pre-IMPL design spec (design only — 不寫 IMPL code、不真實 dispatch、不直改 runtime；可 ssh read-only)
**改動風險**: **高**（觸 GovernanceHub risk SM 升級主路徑 + position_manager exchange path + 新 spawn task）；硬邊界 **0 觸碰**
**前置狀態**: (1) HIGH-1 ✅ 解除 (commit `3423f0f7`，compute_outcome push-weighted) ；(2)(3)(4) 本 spec 拍定
**Source baseline**: `notification_failsafe/` C1+C2+C3 已 land (commit chain `920f8299` → v79)；本 spec 讀證列 §0.2

---

## §0 摘要與最關鍵架構修正

### §0.1 一句話

C4 = 起一條長運行 watcher task，用**既有 reconciler 的 in-band `PipelineCommand` 模式**驅動 SM-04，把 C1/C2/C3 已 land 的真實 trait impl（ThreeWayDispatcher / RestPositionProvider / BybitExchangeStopSync / PgAuditEmitter / WallClock）接進 demo + live pipeline，讓 fail-safe runtime-live。

### §0.2 ⚠️ 推翻 2026-05-28 spec §4 的 wire 模型（最重要的 PA 發現）

2026-05-28 spec §4.2 / §4.4 假設 `pipelines: Vec<Arc<RwLock<TickPipeline>>>`，watcher 直接 `pipeline.write().await` 拿 `governance.risk` SM 跑 `check_timer(&mut p.governance.risk)`。**這在實際 runtime 不成立**：

| 讀證 | 事實 |
|---|---|
| `main_pipelines.rs:541` `spawn_demo_pipeline` | `TickPipeline` 由 `run_event_consumer(demo_deps)` **內部擁有**（move into task）；不存在共享 `Arc<RwLock<TickPipeline>>` |
| `main_pipelines.rs:565` `spawn_live_pipeline` | Live 跑**獨立 OS thread + 自己的 tokio runtime**（4 worker）；更不可能跨 thread 共享可變 pipeline |
| `main_pipelines.rs:214` `spawn_paper_pipeline` | paper `paper_enabled=false` 硬編碼 → 只起 drain task，**無 TickPipeline 實體** |
| `tick_pipeline/mod.rs:823` | `pub governance: GovernanceCore` 是 pipeline 的 owned 欄位，非 `Arc` |

→ **watcher 不能持有 `&mut RiskGovernorSm`**。`single_watcher.rs::check_timer(risk_sm: &mut RiskGovernorSm)` 簽名在 runtime **無合法 caller**（C3 它只在 test 用 `RiskGovernorSm::new()` 構造）。

**正確模型 = 復用 reconciler 的 in-band 升級通道**（已驗 production pattern）：

```
position_reconciler (外部 task)
  → 持 cmd_tx slot (DemoCmdSenderSlot / LiveCmdSenderSlot)
  → 偵測 drift → cmd_tx.send(PipelineCommand::ReconcilerEscalate { target_tier, reason, response_tx })
  → event_consumer/handlers/risk.rs:526 handle_reconciler_escalate
      → pipeline.governance.risk.reconciler_escalate_to(target, reason)   ← 真正在 owner task 內跑 SM transition
  → loop_handlers.rs:553 「command 處理後同步 governor 風控級別到 shared_risk_level」  ← atomic 自動同步
```

讀證：`position_reconciler/mod.rs:958` 發 `ReconcilerEscalate`；`handlers/mod.rs:258` 路由；`handlers/risk.rs:536-540` 跑 `reconciler_escalate_to`；`loop_handlers.rs:553-561` doc 明載「command 處理後同步 governor 級別到 `shared_risk_level`」。

**結論**：C4 watcher 走相同骨架（持 cmd_tx slot + shared_risk_level atomic read），SM-04 transition **不由 watcher 直接執行**，而是 `cmd_tx.send` 一條新的 `PipelineCommand` 進 owner task 跑。這同時**自然消除** 2026-05-28 spec §11.3 反對 3（「4 個 RwLock<TickPipeline> 寫鎖跨 tick」）——根本沒有那個寫鎖。

### §0.3 C4 殘前置處置總表

| # | 殘前置 | 本 spec 章節 | 決議 |
|---|---|---|---|
| 1 | HIGH-1 PA ruling | — | ✅ 已解 (`3423f0f7`)，compute_outcome 已 push-weighted |
| 2 | ATR 注入 | §1 | demo/live 從 owner task 的 `kline_manager` 補 ATR（**不在 watcher 端 REST**）；缺 ATR → 鎖利 hook 空轉但 SM-04 仍升 |
| 3 | dispatch_and_observe vs mpsc | §2 | **接 mpsc outcome（選項 B）**；C4 不接觸發點，不用 dispatch_and_observe |
| 4 | paper noop gate | §3 | paper 無 pipeline 實體 → watcher 根本不對 paper 註冊（結構性 noop）；BybitExchangeStopSync 仍加 engine_mode short-circuit defense |
| — | pipeline_ctor wire | §4 | watcher 為**單例 external task**，main.rs 在 demo/live spawn 後呼一次 `spawn_notification_failsafe_watcher` |
| — | 非 dead-wire | §5 | C4 不接 incident trigger → **仍是半空 wire**；本 spec 明標 + 給最小 self-prove integration + Sprint 3 incident_policy ticket |

---

## §1 ATR 注入路徑（殘前置 2，operator Q-B=BB）

### §1.1 問題精確定位

`active_lock_profit_per_position`（`risk_gov.rs:327`）公式 `new_sl = entry_price ± pos.atr × buffer_multiplier`，其中 `pos.atr` 是**絕對 ATR 值**（非 atr_percent；`risk_gov.rs:296` doc 明載 position-life ATR）。`pos.atr <= 0.0` → `risk_gov.rs:339` fail-closed `continue`（跳過該倉，不生成 StopAdjustment）。

C3 `RestPositionProvider`（`position_provider.rs:175`）硬寫 `atr: 0.0`（known-limitation），因為它走 Bybit REST `/v5/position/list`，**REST 回應不含 ATR**。→ 當前 wire 後 fail-safe 升 SM-04 Defensive 會發生，但 `active_lock_profit_per_position` 對每倉 `atr=0.0` 全跳過 → **鎖利 hook 完全空轉，0 個 conditional SL 同步到交易所**（雙重防線只剩本地 SM-04 那一半）。

### §1.2 ATR 真實來源（讀證）

絕對 ATR 在 owner task 的 `TickPipeline.kline_manager` 內，已有現成 pattern：

```
step_6_risk_checks.rs:113 / pipeline_helpers.rs:444
  self.kline_manager.get_ohlcv(symbol, "1m", Some(20))
    .and_then(|o| openclaw_core::indicators::atr(&o.high, &o.low, &o.close, 14))
    .map(|r| r.atr)        // ← r.atr 是絕對值；r.atr_percent 是百分比
```

`AtrResult { atr, atr_percent }`（`feature_collector.rs:158` 用 `a.atr`）。Cold-start < 15 bars → `atr()` 回 `None` → 自然 fail-closed（與 C3 atr=0.0 同語義）。

### §1.3 設計：ATR 注入必須發生在 owner task 內，不在 watcher 端

**反模式（不可採）**：讓 watcher 端 `RestPositionProvider` 自己拿 kline。watcher 是 external task，**沒有** `kline_manager`（它在 owner pipeline 內，非 Arc 共享）。硬塞 kline_manager 進 watcher = 重新引入 §0.2 的共享可變 pipeline 問題。

**正確路徑 = 把「組 PositionSnapshot + 填 ATR + 跑 lock-profit + sync exchange」整段移進 owner task**，由新 `PipelineCommand` 觸發：

新增 `PipelineCommand::NotificationFailsafeEscalate { reason: String, response_tx }`（**不復用 `ReconcilerEscalate`**，理由見 §1.4）。handler 在 owner task 內：

```
handle_notification_failsafe_escalate(reason, response_tx, pipeline, snapshot_writer, exchange_sync_dep):
  1. from = pipeline.governance.risk.snapshot_level()
  2. if from < Defensive:
       pipeline.governance.risk.transition(Defensive, NotificationFailsafeTimeout,
           RiskGovernor, ["notification_3way_fail_1h_timeout"], None,
           "auto_escalated_to_sm04_defensive")   ← 直用 core transition（非 reconciler_escalate_to，見 §1.4）
  3. // ATR 注入：在 owner task 內，pipeline.kline_manager 可用
     let snaps: Vec<PositionSnapshot> = pipeline.paper_state.positions().iter()
         .filter_map(|p| {
             let atr = pipeline.kline_manager.get_ohlcv(&p.symbol, "1m", Some(20))
                 .and_then(|o| openclaw_core::indicators::atr(&o.high,&o.low,&o.close,14))
                 .map(|r| r.atr).unwrap_or(0.0);   // 缺 ATR → 0.0 → 下游 fail-closed 跳過
             map_paper_position_to_snapshot(p, atr)   // side "Buy"/"Sell", entry, qty, current_sl, atr
         }).collect();
  4. let adjustments = active_lock_profit_per_position(&snaps, FailsafeConfig::DEFAULT_ATR_BUFFER);
  5. for adj in &adjustments: exchange_sync_dep.sync_stop(adj).await  // BybitExchangeStopSync (demo/live 真 client)
  6. snapshot_writer.force_write(&pipeline.snapshot())
  7. emit audit via PgAuditEmitter (或回傳 report 由 watcher emit — 見 §2.3)
  8. response_tx.send(Ok(report_json))
```

關鍵：**倉位來源從 `pipeline.paper_state.positions()` 取**（owner task 的真值，含 demo/live 已確認 fill 的倉），不再走 REST。這同時解決 §0.2（無共享 pipeline）+ §1（ATR 來源）兩個問題——因為這段在 owner task 內，paper_state + kline_manager 都直接可用。

> **C3 `RestPositionProvider` 命運**：C4 後它**不在主路徑被呼叫**（snapshot 改在 owner task 內組）。保留它作為 watcher 端「升級前 sanity probe」可選（非必需），或標 `#[allow(dead_code)]` + doc「superseded by in-task snapshot, kept for REST-based out-of-band probe」。E1 取捨；**不要刪**（C3 test 覆蓋仍有價值，且未來 out-of-band 用途）。E2 確認不是 silent dead code（要嘛有 caller 要嘛明標）。

### §1.4 為什麼新 `NotificationFailsafeEscalate` 而非復用 `ReconcilerEscalate`

| 維度 | 理由 |
|---|---|
| 語義 reason / audit | reconciler escalate 寫 `reconciler_auto_escalate` audit event；fail-safe 須寫 `auto_escalated_to_sm04_defensive`（mod.rs:434 既定 reason + V114 audit schema 對齊）。混用會污染 reconciler audit 語義 |
| transition 路徑 | reconciler 走 `reconciler_escalate_to`（bypass operator whitelist/cooldown 的 reconciler 專用閘）；fail-safe 應走 core `transition(Defensive, NotificationFailsafeTimeout, RiskGovernor, ...)` — 這是 mod.rs `execute_failsafe_escalation` 已驗的事件來源（test T3 證 from=NORMAL→to=DEFENSIVE）。RiskEvent 不同（`NotificationFailsafeTimeout` vs reconciler 的 drift event）→ audit trace 才正確 |
| 鎖利 hook | reconciler escalate 不跑 `active_lock_profit_per_position`；fail-safe 必須跑（雙重防線）。新 variant 才能掛這段 |
| idempotent | watcher 端 `escalated_for_current_arm` claim-before-await 已保證「同一武裝只發一次 escalate command」（single_watcher.rs:219-230）；owner task handler 端 `from < Defensive` guard 是第二層（已 Defensive → skip transition 但仍可跑鎖利，對齊 mod.rs:428 / test T8） |

> **Hard-boundary 確認**：新 PipelineCommand 走 `governance.risk.transition` 是**收緊**風控（Normal→Defensive），不開新倉、不碰 `live_execution_allowed`/`max_retries`/`OPENCLAW_ALLOW_MAINNET`/`authorization.json`。Defensive ladder（reduce_only + new_entries=false + 鎖利）是既有 risk_gov 行為，C4 不新增升級語義。16 根原則 4（不繞風控）+ 5（survival）+ 9（雙重防線）成立。

---

## §2 outcome 路徑選擇（殘前置 3 / C3 PC3.Q4）

### §2.1 兩條既有路徑

C3 `single_watcher.rs` 留了兩個入口：
- `dispatch_and_observe(message)` (line 168)：watcher **主動** `dispatcher.dispatch_3way(msg).await` → 內部 observe。
- `observe_dispatch(outcome)` (line 157)：watcher **被動**收外部餵的 outcome。

### §2.2 C4 選擇：**mpsc outcome（被動 observe，選項 B）**，不用 dispatch_and_observe

**理由**：
1. **C4 不接觸發點**（incident_policy 未實裝，見 §5）。watcher 主動 `dispatch_and_observe` 需要「有事件可派」——當前無事件源。若 C4 用 dispatch_and_observe，watcher 要嘛永不呼叫（dead），要嘛定時空 dispatch（無意義發通知，設計錯誤，= 2026-05-28 spec §4.5 否決的選項 A）。
2. **被動 observe 對齊未來 incident_policy wire**：Sprint 3 incident_policy 偵測到需通知事件 → 它呼 `dispatcher.dispatch_3way` → outcome 經 mpsc 送 watcher `observe_dispatch`。watcher 只負責「觀察 outcome + 計時 + 升級」，**dispatch 的觸發責任在 incident_policy**，職責分離乾淨。
3. **claim-before-await 並發保護已在 observe 側**（single_watcher.rs T4.12 驗），mpsc 單 consumer 天然序列化。

**C4 wire 結構**（tokio::select! 單 task）：

```
spawn_notification_failsafe_watcher(...):
  let watcher = SharedFailsafeWatcher::init(
      Box::new(ThreeWayDispatcher::from_secret_files()),   // C1，secret 缺→disable 各通道
      Box::new(InTaskNoopPositionProvider),                // §1.3：snapshot 改在 owner task；watcher 端 provider 不再是主路徑
      Box::new(NoopExchangeForWatcher),                    // §1.3：sync 改在 owner task handler；watcher 端不直 sync
      Box::new(PgAuditEmitter::new(db_pool)),              // C2，可選（audit 也可在 owner handler emit，見 §2.3）
      Box::new(WallClock::new()),                          // C3
      FailsafeConfig::default());
  tokio::spawn(async move {
    let mut timer_check = interval(30s);
    loop { select! {
      _ = cancel.cancelled() => break,
      _ = timer_check.tick() => {
          // 不再 check_timer(&mut risk_sm)！改：watcher 純判定 timer_expired
          if watcher.timer_expired_and_claim() {   // 新增：claim-before-await，回 bool（內部 set escalated flag）
              // 對每個有 cmd_tx 的 engine 發 escalate command
              for slot in [demo_cmd_slot, live_cmd_slot] {
                  if let Some(tx) = slot.read().as_ref().cloned() {
                      let (rtx, rrx) = oneshot::channel();
                      let _ = tx.send(PipelineCommand::NotificationFailsafeEscalate {
                          reason: "notification_3way_fail_1h_timeout".into(), response_tx: rtx });
                      // log handler response（對齊 reconciler mod.rs:968 pattern；不阻塞）
                      tokio::spawn(async move { match rrx.await { /* log */ } });
                  }
              }
          }
      }
      Some(outcome) = outcome_rx.recv() => { watcher.observe_dispatch(outcome); }   // incident_policy 餵（Sprint 3）
      Some(_) = ack_rx.recv() => { watcher.record_operator_ack(); }                  // operator GUI ack（C5）
    }}
  });
```

> **single_watcher.rs API 調整需求**：現 `check_timer(&mut risk_sm)` 簽名假設 watcher 持 SM（§0.2 已證不成立）。C4 需在 single_watcher 新增 `timer_expired_and_claim(&self) -> bool`（lock 內判 `timer_expired` + 同鎖 `set_escalated_for_current_arm(true)` + drop，純邏輯無 await），**保留** claim-before-await 不變量（single_watcher.rs:219-230 既有邏輯抽出 SM 那段即可）。原 `check_timer(&mut risk_sm)` 標 `#[cfg(test)]` 或保留供 mod.rs FailsafeWatcher 泛型 test。**這是 C3 seam 的最小裂縫修補**，非重寫。

### §2.3 audit emit 落點（demo/live 分別 vs watcher 集中）

兩選項：(a) owner task handler emit（snapshot/transition 結果在 owner task 內最完整）；(b) watcher 收 response_tx 回的 report 後集中 emit。

**PA 推薦 (a) owner task handler emit**：transition from/to level + sync_records + adjustments_count 都在 owner task 內產生，就地 emit 最完整、避免跨 task 傳大 payload。watcher 端 PgAuditEmitter 因此**可不接**（傳 Noop 或不傳），audit 由 owner handler 持有的 `audit_pool`（demo/live deps 已有 `audit_pool`）寫 V114。E1 取捨；若取 (b) 則 watcher 持 PgAuditEmitter，owner handler 把 report JSON 經 response_tx 回 watcher。**任一皆寫 V114 `observability.notification_failsafe_events`（C2 已 land schema + PgAuditEmitter::emit_auto_escalated）**。

---

## §3 paper noop gate（殘前置 4）

### §3.1 paper 結構性 noop（最強防線：根本不註冊）

讀證 `main_pipelines.rs:229` `let paper_enabled = false;` 硬編碼 → paper 只起 drain task，**無 TickPipeline、無 cmd_tx（paper.cmd_rx 被 drain 消費後 reject）**。

→ **watcher 的 escalate loop（§2.2）只迭代 `[demo_cmd_slot, live_cmd_slot]`，根本不含 paper**。paper 連 escalate command 都收不到（drain task `reject_disabled_paper_command`）。這是最強的 paper noop：不是「short-circuit」，是「結構上不存在 paper 觸發路徑」。

### §3.2 BybitExchangeStopSync engine_mode short-circuit（defense-in-depth）

即便 §3.1 已結構性排除 paper，仍按 2026-05-28 spec §6.3 + E2 重點審查 2 加 defense：`BybitExchangeStopSync`（或 §1.3 改在 owner handler 的 sync 段）必須只對 `effective_engine_mode() ∈ {demo, live_demo, live}` 跑真 REST；若 owner handler 是 paper（理論不可達）→ skip sync 不打 HTTP。因 sync 已改在 owner task handler（§1.3），這個 gate 落在 handler 內：`if pipeline.effective_engine_mode() == "paper" { skip exchange sync, 只跑本地 SM-04 }`。

讀證：`effective_engine_mode()` 在 tick_pipeline 已存在（mod.rs:887 doc + 用於 DB engine_mode tag）。

> **E2 重點審查 1**：paper 路徑雙重保險——(a) watcher loop 不迭代 paper slot；(b) handler engine_mode gate。E2 grep 確認 BybitExchangeStopSync 不會對 paper endpoint 發 `set_trading_stop`（paper 無真 client，但 demo client 誤用會打 demo endpoint）。

---

## §4 pipeline_ctor / main.rs wire 點

### §4.1 spawn 位置

| 候選 | 評估 |
|---|---|
| `pipeline_ctor` / `TickPipeline::new` | ❌ ctor 不啟長運行 task；且 watcher 是跨 engine 單例，非 per-pipeline |
| `tasks.rs::spawn_notification_failsafe_watcher` + main.rs 呼叫 | ✅ 對齊 `spawn_position_reconciler` / `main_boot_tasks::spawn_position_reconcilers` pattern |
| `main_boot_tasks.rs` | ✅ 可——與 `spawn_position_reconcilers` 同檔同時序最自然（兩者都吃 cmd slot + db_pool + cancel） |

**結論**：在 `tasks.rs` 新增 `spawn_notification_failsafe_watcher(...)`；在 **`main_boot_tasks.rs`** 緊接 `spawn_position_reconcilers` 之後呼叫一次（同一批 boot-time wiring，吃同樣的 `demo_cmd_slot` / `live_cmd_slot` / `db_pool` / `cancel`）。main.rs:819 已呼 `main_boot_tasks::spawn_position_reconcilers(...)`，C4 在其後加一行 `main_boot_tasks::spawn_notification_failsafe_watcher(...)` 或併入同函數尾段。

### §4.2 spawn 簽名（對齊 reconciler 依賴）

```rust
pub(crate) fn spawn_notification_failsafe_watcher(
    db_pool: &Arc<DbPool>,
    cancel: &CancellationToken,
    demo_cmd_slot: &DemoCmdSenderSlot,    // ipc_server::engine_routing
    live_cmd_slot: &LiveCmdSenderSlot,    // 跟隨 LiveAuthWatcher respawn（slot 間接讀，per WP-13 pattern）
    outcome_rx: mpsc::UnboundedReceiver<DispatchOutcome>,   // incident_policy 餵（Sprint 3）；C4 留接口
    ack_rx: mpsc::UnboundedReceiver<()>,                    // C5 GUI ack 餵
)
```

**單例不重複 spawn**：`SharedFailsafeWatcher::init`（single_watcher.rs:112，`OnceLock::get_or_init`）保證 watcher state 單例。spawn 函數本身只在 main_boot_tasks 呼一次（boot-time 單點，非 per-engine 迴圈），無重複 spawn 風險。**E2 grep 確認 `spawn_notification_failsafe_watcher` 只有 1 個 caller**。

**不洩漏 task**：`tokio::select!` 第一臂 `cancel.cancelled() => break`，cascade per 既有 CancellationToken pattern（對齊 reconciler / fee task）。watcher state 不持久化（restart 重新計時，per AMD restart 重評通知健康）。

### §4.3 live slot 跟隨 respawn

Live pipeline 由 `LiveAuthWatcher` 在 authorization 輪替時 respawn（cmd_tx 換新）。watcher 必用 `live_cmd_slot.read().as_ref().cloned()` **每次發送前取 snapshot**（對齊 `main_boot_tasks.rs:106` reconciler 的 `slot.read().as_ref().cloned()` provider pattern），**禁** by-value 持有 cmd_tx（會 stale，LIVE-AUTH-WATCHER memory 教訓）。

---

## §5 非 dead-wire 確認（per memory feedback_no_dead_params + CLAUDE §六）

### §5.1 誠實標記：C4 wire 後仍是「半空 wire」

**C4 不接 incident trigger**。wire 完成後 runtime 仍**不會自發**呼 `observe_dispatch`——因為沒有事件源呼 `dispatcher.dispatch_3way` 產生 outcome 餵 `outcome_rx`。即：

- watcher task 起來、select! 跑、timer_check 每 30s tick；
- 但 `outcome_rx` 永遠空（incident_policy 未實裝）→ timer 永不武裝 → escalate 永不發。
- secret 缺（C1 fail-closed）時各 dispatcher disable，但即便 secret 齊全，**也無人觸發 dispatch**。

**這違反 feedback_no_dead_params 的精神**（wire 進 runtime 但不被真實調用 = 假 wire），與 2026-05-28 spec §11.2 自評一致。

### §5.2 C4 範圍內可做的「真 wire 證明」（不偽裝成完整）

C4 land 後新增 **1 條 integration test** 證明 wire 路徑端到端通（非偽 prod）：

```
e2e_c4_failsafe_inband_escalate:
  1. 起 demo pipeline（testcontainers PG，mock exchange via BybitExchangeStopSync stub）
  2. 直接 outcome_tx.send(DispatchOutcome::AllFail)  ← 模擬 incident_policy 餵
  3. mock clock 推進 > 3_600_000ms（或 timer_expired_and_claim 直驗）
  4. 驗 watcher 發 PipelineCommand::NotificationFailsafeEscalate 進 demo cmd_tx
  5. 驗 owner handler: governance.risk Normal→Defensive + shared_risk_level atomic == 3
  6. 驗 active_lock_profit 對有 ATR 的倉生成 StopAdjustment + BybitExchangeStopSync stub 收到 sync_stop
  7. 驗 V114 多 1 row (engine_mode='demo', to_level='DEFENSIVE')
```

這證明「outcome→timer→command→owner SM-04→鎖利→exchange sync→audit」整鏈通。**production 自發觸發**等 Sprint 3 incident_policy。

### §5.3 強制 Sprint 3 ticket（防止半空 wire 長期擱置）

C4 closure 必同時開 / 更新 ticket：`P2-INCIDENT-POLICY-DISPATCH-TRIGGER`（Sprint 3）——接「需通知 operator 事件」(autonomy switch / SM-04 升級 / drawdown critical / drift critical) → `dispatcher.dispatch_3way` → `outcome_tx.send`。**PM acceptance**：C4 + incident_policy 兩者皆 land 才算 fail-safe runtime-complete；C4 單獨 land 是「機制 live、觸發 pending」。TODO 須明標此狀態，不可標「fail-safe runtime-live 完成」。

### §5.4 為什麼仍值得做 C4（不等 incident_policy 一起做）

1. **解耦並行**：C4（in-band wire + ATR + SM 機制）與 incident_policy（事件偵測）是兩個獨立 E1 工作面，C4 先行讓 incident_policy 只需 `outcome_tx.send` 一行接入。
2. **ATR 注入 + in-band SM-04 機制是真實可測的**（§5.2 integration），不是 stub。
3. **GUI ack（C5）依賴 C4 的 ack_rx wire 存在**才能接。

---

## §6 LOC + E1 chain + batched deploy

### §6.1 LOC 估 + 切片

| 切片 | 範圍 | LOC | E1 hr |
|---|---|---|---|
| **C4-a** | 新 `PipelineCommand::NotificationFailsafeEscalate` variant + `handle_notification_failsafe_escalate`（owner task：SM transition + ATR-from-kline snapshot + lock-profit + exchange sync + audit）+ paper engine_mode gate | ~180-220 | 6-8 |
| **C4-b** | `single_watcher.rs` 新 `timer_expired_and_claim()` + `check_timer` 標 test-only + outcome_rx/ack_rx select! 結構 | ~80-110 | 3-4 |
| **C4-c** | `tasks.rs::spawn_notification_failsafe_watcher` + `main_boot_tasks.rs` wire 點 + cmd slot/db_pool/cancel 接線 + outcome/ack channel 建立 | ~120-150 | 4-5 |
| **C4-d** | integration test §5.2（in-band escalate 端到端，testcontainers + stub exchange） | ~120-160 | 3-4 |
| **總計** | | **~500-640 全 Rust** | **16-21 sub-agent hr** |

> 比 2026-05-28 spec §8.1 C4 估（~250 LOC）高，因 §0.2 推翻共享 pipeline 模型後須新 PipelineCommand + owner handler（ATR 注入 + lock-profit + sync 整段下放 owner task）。但**風險更低**（復用已驗 reconciler in-band pattern，無新並發/鎖模型）。

### §6.2 E1 派發（文件重疊分析）

| Lane | 檔案 | 重疊 |
|---|---|---|
| **E1-A**（C4-a） | `tick_pipeline/mod.rs`(PipelineCommand enum) + `event_consumer/handlers/risk.rs`(new handler) + `event_consumer/handlers/mod.rs`(route) | enum 改動是窄行；與 D2 `ConvergeExchangeZero`（已 land `a5e1ded1`）同 enum 但不同 variant，無衝突 |
| **E1-B**（C4-b + C4-c + C4-d） | `notification_failsafe/providers/single_watcher.rs` + `tasks.rs` + `main_boot_tasks.rs` + integration test | 與 E1-A 不重疊（不同模組） |

**建議：2 個並行 E1**（A=owner handler 邏輯；B=watcher seam + spawn wire + test），收口時 B 依賴 A 的 `NotificationFailsafeEscalate` variant 簽名先定稿（A 先出 variant 定義，B 即可並行）。或**單 E1 串行**（C4-a→b→c→d），因 LOC 不大、跨模組契約需一致，串行風險更低。**PA 推薦單 E1 串行**（C4-a 定 variant 契約 → b → c → d），避免 enum 簽名 race。

### §6.3 chain

`PA(本spec) → E1(C4-a→d) → BB(exchange set_trading_stop 信任 + paper/demo endpoint fence) → E2(對抗核驗) → E4(regression) → QA(sign-off) → PM`

- **BB 必審**：BybitExchangeStopSync 走 `set_trading_stop`（`position_manager.rs:237`）對 demo/live endpoint；BB 確認 paper 不誤觸 + live conditional SL 語義（P1-06 side_is_long 取整已在 C3）+ retCode fail-closed 不重試（exchange_stop_sync map_bybit_error Business→Rejected 不 retry，符合硬邊界）。
- **E4 regression**: 當前 lib baseline ~3619（D2 後）；C4 + integration 預期 +4~6 test。`restart_all --rebuild --keep-auth` Linux GREEN（IPC + 任何交易 call deploy/operator-gated）。

### §6.4 E2 重點審查 3 點

1. **§0.2 + §1.3 owner-task snapshot 取代 watcher REST**：E2 確認 ATR 注入 + lock-profit + exchange sync 全在 owner task `handle_notification_failsafe_escalate` 內跑（`pipeline.kline_manager` / `pipeline.paper_state.positions()` 可用），watcher 端不再持 `&mut RiskGovernorSm`（`check_timer(&mut risk_sm)` 無 production caller）。
2. **§3 paper 雙重 noop**：(a) watcher escalate loop 不迭代 paper slot；(b) handler `effective_engine_mode()=="paper"` skip exchange sync。grep 確認無 paper→`set_trading_stop` 路徑。
3. **§4.3 live slot 每次取 snapshot**：grep 確認 `live_cmd_slot.read().as_ref().cloned()` 在發送前取，無 by-value 持有 stale cmd_tx（LIVE-AUTH-WATCHER 反模式）。+ §2.2 claim-before-await（`timer_expired_and_claim` 同鎖 set flag）保留——並發/重入不雙發 escalate command。

### §6.5 batched deploy（per operator 拍板）

C4 land 後**不單獨 deploy**。C4 deploy 將與 **Track C（D2 reconcile `a5e1ded1`，runtime-live 但 DEPLOY BATCHED）** 一起 `restart_all --rebuild --keep-auth`：

- 同一次 Linux rebuild 套入：C4 binary（含 NotificationFailsafeEscalate）+ D2 reconcile（Ghost 收斂 + S-6 pagination gate）+ HIGH-1 `3423f0f7`（compute_outcome push-weighted，已 source-merged 未 deploy）。
- deploy 前提：E1→BB→E2→E4→QA 全綠 + operator 批次拍板（per TODO §-1「C deploy 批次 / 下個 Rust rebuild 一起套」）。
- deploy 後 health-freeze 監測同既有 3 條 `[48]/[74]/[56]` 零 regression baseline。
- ⚠️ deploy 後 fail-safe **機制 live 但無自發觸發**（§5.1），TODO/operator 通報須明標「C4 wire DONE / incident trigger Sprint 3 pending」，不可宣稱 fail-safe 全功能 live。

---

## §7 PA Self-attestation（16 根原則 + 硬邊界）

- 原則 1（單一寫入口）：✅ exchange SL sync 走既有 `PositionManager::set_trading_stop`，SM 升級走既有 `governance.risk.transition`；無新寫入口。
- 原則 4（不繞風控）：✅ fail-safe 經 SM transition 收緊風控，非繞過。
- 原則 5（survival>profit）：✅ exchange sync 個別失敗不 rollback transition（mod.rs 既有不變量保留）。
- 原則 6（uncertainty→conservative）：✅ ATR 缺 → 鎖利空轉但 SM-04 仍升 Defensive（reduce_only + 停新倉仍生效）；cold-start <15bar atr=None fail-closed。
- 原則 9（雙重防線）：✅ 本地 SM-04 + 交易所 conditional SL（ATR 注入修好後雙線齊全；ATR 缺時降為單線本地，誠實標記 §1.1）。
- 原則 14（零外部成本）：✅ wire 不引入新外部依賴（C1 已選 Gmail SMTP / Incoming Webhook）。
- **硬邊界**：✅ 0 觸碰——`live_execution_allowed` / `max_retries=0` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` / `live_reserved` 全不改；新 PipelineCommand 是風控收緊（reduce-only 方向），retCode fail-closed 不重試（exchange_stop_sync 既有 mapping），不開新倉不需 lease（fail-safe 保命非下單授權，per 2026-05-28 spec §6.1）。
- 跨平台：✅ 無硬編碼 path；watcher / handler 純 Rust runtime 邏輯。
- 安全裁定：fail-safe wire 錯比不 wire 危險（§0 已標）——本 spec 用「復用已驗 reconciler in-band pattern + 結構性 paper 排除 + claim-before-await + from<Defensive guard」四重保護「誤升 Defensive 平倉」與「漏升不保護」。**誤升風險**：mpsc outcome 須真 AllFail（push-weighted，HIGH-1 已修）才武裝，PartialFail/AllSuccess 不武裝；timer 1h 緩衝。**漏升風險**：claim-before-await + from<Defensive guard 保證單次武裝單次升級，且 demo+live 各自 slot 獨立發送（一個 engine 升級失敗不影響另一個）。

---

## §8 文件路徑與 cross-ref

- 本 spec：`docs/execution_plan/specs/2026-05-29--packet-c-c4-pipeline-wire-spec.md`
- 2026-05-28 母 spec（§4 wire 模型被 §0.2 推翻）：`docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md`
- HIGH-1 ruling（前置1解）：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--packetc_high1_banner_channel_weight_ruling.md`
- Source：`notification_failsafe/{mod.rs, providers/single_watcher.rs, providers/position_provider.rs, providers/exchange_stop_sync.rs, audit_emitter.rs, dispatchers/three_way.rs}`
- In-band 升級 precedent：`position_reconciler/mod.rs:958` + `event_consumer/handlers/risk.rs:526` + `event_consumer/loop_handlers.rs:553`
- ATR pattern：`tick_pipeline/on_tick/step_6_risk_checks.rs:113` + `pipeline_helpers.rs:444`
- core lock-profit：`openclaw_core/src/sm/risk_gov.rs:327`（atr 絕對值）
- TODO ticket：`P2-PACKET-C-C4-PIPELINE-WIRE`（line 209）+ Sprint 3 follow `P2-PACKET-C-C5-GUI-BANNER-ACK-ROLE`（line 211）+ 新 `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`（§5.3）
- batched deploy：Track C D2 `a5e1ded1`（TODO line 174 / 493）

---

PA DESIGN DONE: report path: docs/execution_plan/specs/2026-05-29--packet-c-c4-pipeline-wire-spec.md

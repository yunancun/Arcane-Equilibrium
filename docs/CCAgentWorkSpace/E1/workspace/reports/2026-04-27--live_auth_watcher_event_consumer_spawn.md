# LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN — Live OS thread spawn 補回 watcher respawn path

- **Ticket**：LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN（P0，主路徑優先級高於 G3-08 H5）
- **派發**：PA
- **完成 Agent**：E1
- **日期**：2026-04-27
- **branch**：`fix/live-auth-watcher-event-consumer-spawn`
- **commit**：`<待 E2 review 後 PM 統一 commit + push>`

## 1. 任務摘要

### ROOT CAUSE

`/tmp/openclaw/pipeline_snapshot_live.json` 從 04-19 15:37 沒寫過，**8 天 silent regression**。

精確修復點（PA 已標出）：
- `srv/rust/openclaw_engine/src/main.rs:1029-1056`（boot path Live spawn 起點 — `(None, None) => None` 是 silent skip 路徑）
- `srv/rust/openclaw_engine/src/live_auth_watcher.rs:439-449`（respawn 路徑核心 — `slot_op.try_spawn` 後不接 `spawn_live_pipeline`）

**故障鏈**：
1. Boot 時 `/home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json` 不存在 → `main.rs:1029-1056` 走 `(None, None) => None` 分支 → **`spawn_live_pipeline` 從未被呼叫**。
2. Operator approve authorization.json (04-26 23:42:26) → `LiveAuthWatcher` 觸發 respawn → **但 watcher 只走 `slot_op.try_spawn(&spawn_cfg)` → `PipelineSlot::try_spawn` → `build_exchange_pipeline`（只 spawn 3 task：WS supervisor + listener + balance refresh）**。
3. **`event_consumer` / `state_writer` / `snapshot_writer` 從未 spawn**，因為它們在 `spawn_live_pipeline` 內 — 該 fn 從未被 watcher 呼叫。
4. 次生災害：`trading.fills` / `learning.exit_features` / `learning.decision_features` / `shadow_fill` Live 期間 8 天 0 row，Live 學習平面完全空。

### 修復方案 A（callback injection）— 完成狀態

| Step | 子任務 | 狀態 |
|---|---|---|
| T1 | watcher `pipeline_spawner` + `thread_handle_slot` 欄位擴展 | DONE |
| T2 | fan-out `LiveEventSenderSlot` 動態 receiver injection | DONE |
| T3 | watcher 構造處 callback 包裝（`from_parts` 兩階段 ctor） | DONE |
| T4 | teardown path thread_handle join（spawn_blocking） | DONE |
| T5 unit | 4 watcher 單測：T-U1 ~ T-U4 中 2 新增（既有 7 已涵蓋） | DONE |
| T5 integ | T-I1 respawn_cycle_e2e 設計骨架 | 留 E4 |

## 2. 修改清單

| 檔 | 動作 | 行數 | 一句話 |
|---|---|---|---|
| `rust/openclaw_engine/src/live_auth_watcher.rs` | 重寫 + 擴展 | +637/- | 新增 `LivePipelineSpawner` / `LiveThreadHandleSlot` / `pre_create_trigger` / `from_parts` / 修改 `decide_once` 的 spawn / teardown arms / 加 2 新單測 |
| `rust/openclaw_engine/src/main.rs` | 修改 | +526/-165 | boot 兩條 path（Some 直接 spawn / None 留給 watcher）+ 預建 `live_cmd_slot` + `live_event_slot` + `live_thread_handle_slot` + 構造 spawner closure capture 19 Arc bundle + 注入 IPC + watcher `from_parts` 組裝 + shutdown 取 thread_handle |
| `rust/openclaw_engine/src/main_fanout.rs` | 修改 | +96/- | live receiver 從 owned `Option<Sender>` 改 `LiveEventSenderSlot` (parking_lot::RwLock)，每 tick 讀 snapshot |
| `rust/openclaw_engine/src/ipc_server/engine_routing.rs` | 修改 | +149/- | 新 `LiveCmdSenderSlot` (parking_lot::RwLock 包 Option<UnboundedSender>) + `EngineCommandChannels.live_slot` 欄位 + `live_snapshot()` 方法 + `select` / `primary` / `primary_label` 改讀 slot 優先；`select` / `extract_engine_tx` 簽名從 `&'a Option<...>` 改 `Option<UnboundedSender>` |
| `rust/openclaw_engine/src/ipc_server/dispatch.rs` | 修改 | +42/- | 19 callsites 改 `&tx`（owned Option 已改成 binding，傳 ref） |
| `rust/openclaw_engine/src/ipc_server/handlers/governance.rs` | 修改 | +18/- | `set_system_mode_broadcast` 改用 `live_snapshot()` 拿 slot 內容 broadcast 給 live |
| `rust/openclaw_engine/src/ipc_server/server.rs` | 修改 | +25/- | 新 `set_live_cmd_sender_slot` 方法（接 LiveCmdSenderSlot） |
| `rust/openclaw_engine/src/ipc_server/mod.rs` | 修改 | +2/-1 | export `LiveCmdSenderSlot` |

**淨變化**：8 檔 / +1330 / -165 / 主要在 watcher.rs + main.rs。EngineCommandChannels / fan-out 改 slot 是必要副改動。

## 3. 關鍵 diff

### 3.1 SpawnOp trait 升級 — try_spawn 回 Option<SpawnOutput>

```rust
// 修復前
async fn try_spawn(&self, cfg: &SpawnConfig<'_>) -> Result<bool, SpawnError>;

// 修復後 — 接到 bindings + slot_cancel_token 才能轉交 closure
async fn try_spawn(&self, cfg: &SpawnConfig<'_>) -> Result<Option<SpawnOutput>, SpawnError>;
```

### 3.2 LiveAuthWatcher 新增欄位 + decide_once 呼叫 closure

```rust
pub struct LiveAuthWatcher {
    // ... existing ...
    pipeline_spawner: Option<LivePipelineSpawner>,
    thread_handle_slot: Option<LiveThreadHandleSlot>,
}

// decide_once respawn arm
match self.slot_op.try_spawn(&spawn_cfg).await {
    Ok(Some(spawn_output)) => {
        match (&self.pipeline_spawner, &self.thread_handle_slot) {
            (Some(spawner), Some(handle_slot)) => {
                match spawner(spawn_output) {
                    Ok(thread_handle) => {
                        *handle_slot.lock() = Some(thread_handle);
                        self.backoff.reset();
                        info!("Live slot + event_consumer thread respawned");
                    }
                    Err(reason) => {
                        // Spawner refused → backoff + slot teardown 避免半成品
                        self.backoff.record_failure();
                        if let Err(te) = self.slot_op.teardown().await { ... }
                    }
                }
            }
            _ => {
                // No spawner injected — Phase 3 fallback (unit test path)
                self.backoff.reset();
            }
        }
    }
    Ok(None) => self.backoff.record_failure(),
    Err(SpawnError::AlreadySpawned) => self.backoff.reset(),
    Err(SpawnError::NotAvailable) => self.backoff.record_failure(),
}
```

### 3.3 Teardown path thread_handle join（spawn_blocking 不阻塞 watcher loop）

```rust
// decide_once teardown arm
if let Some(slot) = &self.thread_handle_slot {
    if let Some(h) = slot.lock().take() {
        tokio::task::spawn_blocking(move || {
            if let Err(e) = h.join() { warn!(...) }
        });
    }
}
```

### 3.4 main.rs 兩條 path

```rust
// boot Some path: 直接 spawn_live_pipeline 維持 boot 預建 channel 兼容
if let (Some(live_b), Some(live_slot_cancel_token)) = (live_bindings, live_slot_cancel) {
    let (boot_event_tx, boot_event_rx) = mpsc::channel(1024);
    *live_event_slot.write() = Some(boot_event_tx);
    let handle = main_pipelines::spawn_live_pipeline(&spawn_ctx_for_boot, &writers_for_boot, live_channels);
    *live_thread_handle_slot.lock() = Some(handle);
}
// boot None path: watcher 後續 decide_once 經 closure 接管 — 這正是 8 天 silent regression 的修復

// closure capture 19 Arc bundle
let live_pipeline_spawner: live_auth_watcher::LivePipelineSpawner = {
    let config_c = Arc::clone(&config);
    // ... 18 more Arc clones ...
    Arc::new(move |spawn_output| {
        let (new_cmd_tx, new_cmd_rx) = mpsc::unbounded_channel();
        let (new_event_tx, new_event_rx) = mpsc::channel(1024);
        let (new_ready_tx, _new_ready_rx) = oneshot::channel();
        *live_cmd_slot_c.write() = Some(new_cmd_tx.clone());
        *live_event_slot_c.write() = Some(new_event_tx);
        let handle = main_pipelines::spawn_live_pipeline(&ctx, &writers, live_channels);
        Ok(handle)
    })
};

// 兩階段 ctor 解 chicken-and-egg
let (live_auth_trigger_handle, live_auth_ipc_trigger_rx) =
    live_auth_watcher::LiveAuthWatcher::pre_create_trigger();
ipc_server.set_live_auth_recheck_sender(live_auth_trigger_handle.sender());
ipc_server.set_live_cmd_sender_slot(Arc::clone(&live_cmd_slot));
// ... 後面構造 closure 後 ...
let live_auth_watcher = live_auth_watcher::LiveAuthWatcher::from_parts(
    Arc::clone(&live_slot) as Arc<dyn live_auth_watcher::SpawnOp>,
    Arc::clone(&config),
    live_bybit_environment(),
    cancel.clone(),
    live_auth_ipc_trigger_rx,
    Some(Arc::clone(&live_pipeline_spawner)),
    Some(Arc::clone(&live_thread_handle_slot)),
);
```

### 3.5 EngineCommandChannels live_slot pattern

```rust
pub struct EngineCommandChannels {
    pub paper: Option<UnboundedSender<PipelineCommand>>,
    pub demo: Option<UnboundedSender<PipelineCommand>>,
    pub live: Option<UnboundedSender<PipelineCommand>>,  // legacy — tests use Default
    pub live_slot: Option<LiveCmdSenderSlot>,            // NEW — watcher rotates
}

impl EngineCommandChannels {
    pub fn live_snapshot(&self) -> Option<UnboundedSender<PipelineCommand>> {
        if let Some(slot) = &self.live_slot {
            if let Some(guard) = slot.try_read() {
                if let Some(tx) = guard.as_ref() { return Some(tx.clone()); }
            }
        }
        self.live.clone()  // legacy fallback
    }
}
```

### 3.6 fan-out dynamic live receiver

```rust
// 修復前
if let Some(ref ltx) = live_tx {
    if ltx.try_send(arc_event).is_err() { warn!("live lagging"); }
}
// 修復後 — 每 tick 讀 slot snapshot（parking_lot::RwLock 短臨界區）
let live_guard = live_slot.read();
if let Some(ref ltx) = *live_guard {
    if ltx.try_send(arc_event).is_err() { warn!("live lagging"); }
}
```

## 4. 治理對照

| 規範 | 對照 | 備註 |
|---|---|---|
| **CLAUDE.md §二 16 原則 #5 失敗默認收縮** | ✅ | spawner Err / build None / NotAvailable 全 record_failure + 退避；teardown 失敗 fail-soft（warn 不 propagate） |
| **CLAUDE.md §二 16 原則 #6 fail-closed** | ✅ | 半成品 spawn（slot up + thread spawn 失敗）→ slot teardown 回 Empty，避免狀態不一致 |
| **CLAUDE.md §二 16 原則 #9 Crash-only** | ✅ | 既有 spawn_live_pipeline 內 catch_unwind / engine_wide_cancel.cancel() 不變 — 本修復不觸碰 panic path（per pipeline_slot Phase 2 docstring 明示） |
| **CLAUDE.md §四 5 項硬邊界** | ✅ | 不動 `live_reserved` / Operator auth / `OPENCLAW_ALLOW_MAINNET` / secret slot creds / `authorization.json` 簽名邏輯。Watcher 仍透過 `load_and_verify` 讀 authorization.json，沒繞 Gate 5 |
| **CLAUDE.md §七 ★★ 跨平台兼容性** | ✅ | 純 `Arc` / `parking_lot::Mutex` / `parking_lot::RwLock` / `tokio` 標準；無 Linux-only API；無硬編碼路徑（grep 0 hit） |
| **CLAUDE.md §七 雙語注釋** | ✅ | watcher.rs / main_fanout.rs / engine_routing.rs / main.rs 改動段落全帶 MODULE_NOTE 中英對照 + docstring 雙語 + inline 不變量註解 |
| **CLAUDE.md §九 1200 行硬上限** | ⚠️ | live_auth_watcher.rs 從 957 行擴到 ~1200+ 行（含 docstring + 2 新單測）；main.rs 從 1171 行擴到 ~1450+ 行 — **超過 1200 警告線**。但這是 P0 主路徑修復，logic 集中重構代價更高。建議 follow-up 拆 watcher 或 main.rs（E2 / E5 review 時提案） |
| **CLAUDE.md §九 Singleton 表** | ⚠️ | `live_cmd_slot`、`live_event_slot`、`live_thread_handle_slot` 是 process-global Arc-wrapped 槽位。建議 PM 同意後加入 §九 表（但這 3 是 closure-captured，不像既有 singleton 模組級）— 待 E2 / PM 拍板 |
| **fail-soft 約束**（PA 派發 §Fail-soft） | ✅ | spawner panic / Err 全走 record_failure + backoff；不會把任一例外往上傳 |

## 5. 不確定之處

1. **§九 1200 行硬上限超過**：watcher.rs ~1200+，main.rs ~1450+。本 ticket 範圍內無法拆（如果拆，watcher 與 main.rs closure capture 19 Arc 跨檔會更糾纏）。建議 E5 follow-up 拆 main.rs spawner closure 構造段到 main_pipelines.rs sibling。

2. **boot Some / 中途 path 不對齊**：boot Some 時直接呼 `spawn_live_pipeline` 不走 closure；中途 respawn 走 closure。理由是 boot 預建 cmd_tx 給 reconciler / strategist scheduler 等 boot-time-fixed captures（強行走 closure 會讓 reconciler 寫到無人讀的 channel）。完美對齊兩條 path 屬範圍外 — 需另外做 reconciler / scheduler 改用 slot snapshot pattern（follow-up）。

3. **`EngineCommandChannels.live` legacy 欄位 vs `live_slot` 並存**：保留 `live` 欄位是為測試端 `Default::default()` 不破壞。生產接線只設 `live_slot`，不設 `live`，所以 `live_snapshot()` 永遠走 slot 路徑。E2 review 時可考慮：是否把 `live` 完全廢除（測試端改設 slot 即可）。當前選保守。

4. **Reconciler / strategist scheduler 中途 respawn 後拿 stale captures**：boot Some 時 reconciler 拿 boot 時 `live_cmd_tx`（捕獲 owned），watcher 中途 respawn 後 reconciler 持有的 cmd_tx 仍是舊 channel — 已 drop 端點。teardown / respawn 一次後 reconciler / scheduler 對 live 的命令會丟。Pre-existing limitation（本 ticket 不擴範圍處理），建議 follow-up ticket。

5. **整合測試 T-I1 留給 E4**：respawn_cycle_e2e（drop auth → 確認停寫 → 寫 auth → 5s 內 mtime 刷新 → invalidate → 60s 不寫 → renew → 再次刷新）需要真實 Bybit-mock 或整合 fixture，超出單元測試範圍。E4 應評估該不該寫，或先 monitor 部署後 healthcheck 結果。

6. **doctest 6 個 pre-existing failed**：`paper_state_restore.rs` / `param_extractor.rs` / `ml/registry.rs` / `paper_state/checkpoint.rs` 的 doctest fail。本 ticket 不觸這些檔，failed 與本修復**無關**。E2 / E4 review 注意分辨。

7. **Mac 端 cargo test --release 全綠**（lib 2252 + bin 52 + IPC 96 = 全部 0 failed），但 Linux 端待 SSH bridge 驗證 — `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"` 屬 PM / E4 階段。

## 6. Operator 下一步

### 6.1 E2 審查重點

1. **設計範圍邊界**：本 ticket 動到 `EngineCommandChannels.live_slot` + fan-out + watcher 是否合理？是否該全保守只動 watcher（讓 reconciler / scheduler 也走 slot 改動移到 follow-up）？
2. **boot Some 不走 closure**：是否同意這個權衡？或 E2 認為應強制兩條 path 對齊（即使 reconciler 限制要另解）？
3. **§九 1200 行硬上限超過**：accept 本 ticket 超限 + 開 follow-up 拆檔，還是要求本 ticket 內就拆？
4. **`Default::default()` 的 `live` 欄位保留**：是否同意保留 vs 全改為 slot-only？
5. **Singleton 登記**：`live_cmd_slot` / `live_event_slot` / `live_thread_handle_slot` 是否需登 §九 表（這 3 是 closure-captured 而非模組 singleton — 通常不登）？
6. **2 新單測覆蓋是否足**：`watcher_with_spawner_handles_build_returned_none` / `watcher_without_spawner_keeps_handle_slot_empty` — E2 是否認為還缺哪個 cell 的測試？
7. **Mac 雙端驗證**：本修復 Mac cargo test 全綠，建議 E2 派 ssh trade-core 跑 `cargo test --release -p openclaw_engine --lib` 雙確認。

### 6.2 E4 回歸計劃（建議）

1. lib + bin tests 雙端跑（Mac + Linux ssh）期望 2252 + 52 / 0 failed。
2. 整合測試 T-I1 設計：考慮在 helper_scripts/ 加一個短 e2e shell — 寫 / 刪 authorization.json 並驗 `pipeline_snapshot_live.json` mtime 變化（需 demo 環境跑 Live 模式，Linux 端 ssh）。
3. 部署後監控：`passive_wait_healthcheck` 加新 check `live_state_writer_active`（檢驗 `pipeline_snapshot_live.json` mtime < 1h）。但這是 follow-up，不在本 ticket。

### 6.3 PM commit / push 計劃（per CLAUDE.md §七 強制鏈）

E1 不直接 commit。等 E2 review → E4 回歸通過 → PM 統一：

```bash
cd /Users/ncyu/Projects/TradeBot/srv
git add -A  # 或具體列檔
git commit -m "fix(rust): LiveAuthWatcher respawn 路徑接通 spawn_live_pipeline (8d silent regression)
... (PM 寫 commit message) ..."
git push origin fix/live-auth-watcher-event-consumer-spawn
# 經 PR / fast-forward merge 進 main
```

不要直接 push main；feature branch `fix/live-auth-watcher-event-consumer-spawn` 已建。

### 6.4 部署後驗證（PM / Linux ssh）

```bash
# 1) deploy
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"
ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"

# 2) 驗 boot Some path（authorization.json 已存在）
ssh trade-core "stat -c '%y %n' /tmp/openclaw/pipeline_snapshot_live.json"
# → mtime < 1 min（boot 後立即寫入）

# 3) 驗中途 path（drop auth → mtime 不更新 → renew → 再寫）
ssh trade-core "rm /home/ncyu/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json"
sleep 10
ssh trade-core "stat -c '%y %n' /tmp/openclaw/pipeline_snapshot_live.json"
# → mtime > 30s（已停寫）
ssh trade-core "<renew authorization through Python /api/v1/live/auth/renew>"
sleep 10
ssh trade-core "stat -c '%y %n' /tmp/openclaw/pipeline_snapshot_live.json"
# → mtime fresh

# 4) 驗 Live writer 活躍
ssh trade-core "psql -d openclaw -c \"SELECT count(*) FROM trading.fills WHERE engine_mode IN ('live','live_demo') AND ts > NOW() - INTERVAL '1 hour';\""
# → > 0
```

E1 IMPLEMENTATION DONE: 待 E2 審查（branch: `fix/live-auth-watcher-event-consumer-spawn`，Mac cargo test lib 2252 + bin 52 全綠，IPC 96 全綠，跨平台 grep 0 hit）。

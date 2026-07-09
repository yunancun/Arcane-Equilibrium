# E1 — Wave 5 Packet C / C3 IMPL（runtime providers）

- 日期: 2026-05-28
- 角色: E1
- Sprint band: Sprint 2 並行軌
- 上游 spec: `docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md` §4.3
- 操作員拍板: hybrid PC.B（operator 確認 + 全 PA defaults） + Q4.1 single shared watcher

## 1. 任務摘要

把 `notification_failsafe::mod.rs` 中既有 5 trait seam 的 runtime 注入端落地實作，
覆蓋 Phase 1-5：

| Phase | 子模塊 | 角色 |
|---|---|---|
| 1 | `providers/wall_clock.rs` | 真實 `FailsafeClock` 注入器（SystemTime epoch ms） |
| 2 | `providers/position_provider.rs` | 真實 `PositionSnapshotProvider`（Bybit V5 REST + 5s timeout） |
| 3 | `providers/exchange_stop_sync.rs` | 真實 `ExchangeStopSync`（wrap `PositionManager::set_trading_stop`） |
| 4 | `providers/single_watcher.rs` | `OnceLock<Arc<SharedFailsafeWatcher>>` 單例封裝（trait-object） |
| 5 | tests | 31 unit test 全 PASS（含 multi-thread concurrent / Send bound / error mapping） |
| 6 | `Cargo.toml` | 無新 dep（既有 parking_lot / tokio / async-trait / thiserror / chrono 全到位） |

**C3 嚴格邊界**（per task spec § 禁線）：
- 不接 `pipeline_ctor` / `tasks.rs` / `main.rs`（C4 工作）
- 不 spawn tokio task（C4 工作）
- 不繞 `PositionManager`（exchange sync 走既有 trait + REST）
- 不擅自加 dep
- 新代碼註釋默認中文

## 2. 修改清單

| 檔 | 類型 | LOC | 簡述 |
|---|---|---|---|
| `rust/openclaw_engine/src/notification_failsafe/providers/wall_clock.rs` | 新 | 102 | `WallClock` + `FailsafeClock` impl + 4 test |
| `rust/openclaw_engine/src/notification_failsafe/providers/position_provider.rs` | 新 | 313 | `RestPositionProvider` + `map_position_infos` pub(crate) + 10 test |
| `rust/openclaw_engine/src/notification_failsafe/providers/exchange_stop_sync.rs` | 新 | 268 | `BybitExchangeStopSync` + `map_bybit_error` pub(crate) + 6 test |
| `rust/openclaw_engine/src/notification_failsafe/providers/single_watcher.rs` | 新 | 351 | `SharedFailsafeWatcher` + 11 test |
| `rust/openclaw_engine/src/notification_failsafe/providers/mod.rs` | 修 (+18 / -2) | 30 | 註冊 4 sub-mod + re-export 公開型別 |
| `rust/openclaw_engine/src/notification_failsafe/mod.rs` | 修 (+15) | — | `FailsafeWatcherState::set_escalated_for_current_arm` `pub(crate)` setter |

**合計**：1064 LOC（新 + 修）/ 4 phase commit。

## 3. 關鍵 diff / 設計亮點

### 3.1 trait-object 解耦（vs 原 spec 範例 generic 參數）

PA spec §4.3 原寫：

```rust
Arc<FailsafeWatcher<ThreeWayDispatcher, RestPositionProvider, BybitExchangeStopSync, PgAuditEmitter, WallClock>>
```

問題：`ThreeWayDispatcher` 是 C1 範疇且本次並行未保證 land 先後；若直接 import 會
讓 C3 commit 卡 C1 完成。

決策：5 個 trait object Box 欄位：

```rust
pub struct SharedFailsafeWatcher {
    dispatcher: Box<dyn NotificationDispatcher>,
    positions: Box<dyn PositionSnapshotProvider>,
    exchange: Box<dyn ExchangeStopSync>,
    audit: Box<dyn FailsafeAuditEmitter>,
    clock: Box<dyn FailsafeClock>,
    cfg: FailsafeConfig,
    state: Mutex<FailsafeWatcherState>,
}
```

trait 已有 `Send + Sync` bound，trait object 自動繼承。C4 wire 時：

```rust
SharedFailsafeWatcher::init(
    Box::new(ThreeWayDispatcher::from_secret_files()),
    Box::new(RestPositionProvider::new(manager, runtime_handle)),
    Box::new(BybitExchangeStopSync::new(manager)),
    Box::new(PgAuditEmitter::new(pool)),
    Box::new(WallClock::new()),
    FailsafeConfig::default(),
);
```

### 3.2 `check_timer` 三段拆分（鎖跨 await 禁區）

per spec §4.7 + §11.3 反對 3 mitigation：

```rust
pub async fn check_timer(&self, risk_sm: &mut RiskGovernorSm) -> Option<FailsafeExecutionReport> {
    // Step 1: 純邏輯判定，<1μs
    let now_ms = self.clock.now_ms();
    let expired = {
        let state = self.state.lock();
        timer_expired(&state, now_ms, FailsafeConfig::DEFAULT_TIMEOUT_MS)
    }; // ← parking_lot guard drop

    if !expired { return None; }

    // Step 2: 無鎖跑完整副作用鏈（exchange sync + audit emit 可能秒級）
    let report = execute_failsafe_escalation(
        risk_sm, self.positions.as_ref(), self.exchange.as_ref(),
        self.audit.as_ref(), &self.cfg, now_ms
    ).await;

    // Step 3: re-lock 標記 idempotent guard
    {
        let mut state = self.state.lock();
        state.set_escalated_for_current_arm(true);
    }
    Some(report)
}
```

**驗證**：T4.6 multi-thread concurrent `observe_dispatch` 8 task / 4 worker thread
無 panic / 無 deadlock。

### 3.3 `set_escalated_for_current_arm` setter（mod.rs 最小入侵）

15 行 `pub(crate)` setter — 不暴露 GUI/IPC，僅 crate 內 `single_watcher` 用：

```rust
pub(crate) fn set_escalated_for_current_arm(&mut self, escalated: bool) {
    self.escalated_for_current_arm = escalated;
}
```

### 3.4 BybitApiError → ExchangeStopError 對映表

| Source | Target | 理由 |
|---|---|---|
| `Business { ret_code, ret_msg, .. }` | `Rejected("retCode=N retMsg=...")` | API 拒絕業務語義 |
| `Transport(..)` | `Transport("http transport: ..")` | 網路不可達 |
| `JsonParse(..)` | `Transport("json parse: ..")` | 對 fail-safe 屬「無法同步」 |
| `NoCredentials` | `Transport("no api credentials configured")` | 配置問題 = 外部不可達 |
| `SigningError(..)` | `Transport("hmac signing: ..")` | 簽名失敗 = 外部不可達 |

設計理由：fail-safe watcher 不 retry；個別失敗由 `execute_failsafe_escalation` 記入
`StopSyncRecord` 不 rollback SM-04 transition（per survival > exchange consistency）。

## 4. 治理對照（CLAUDE.md / spec）

| 治理項 | 狀態 | 證據 |
|---|---|---|
| §二 原則 5（survival > exchange consistency） | ✅ | error mapping 全 fail-soft；exchange sync 個別失敗不 rollback |
| §二 原則 6（uncertainty → conservative） | ✅ | REST timeout / parse fail → empty Vec；NaN/負值 fail-closed 過濾 |
| §二 原則 9（本地 SM-04 + 交易所 conditional SL 雙重防線） | ✅ | `BybitExchangeStopSync::sync_stop` 走既有 `set_trading_stop` |
| §四 不繞 PositionManager | ✅ | `RestPositionProvider` + `BybitExchangeStopSync` 全經 PositionManager |
| §四 不 panic / 不 unwrap | ✅ | `WallClock::now_ms` `unwrap_or(0)` fail-soft；其他全 match / Result |
| §七 新檔 MODULE_NOTE | ✅ | 4 新檔每檔頭都有「模塊用途 / 為什麼 / 不變量 / ref」段 |
| §七 中文註釋默認 | ✅ | 所有新註釋中文；技術詞 (PositionInfo, OnceLock, Arc, Mutex) 保英文 |
| §七 800 行警告 / 2000 行硬上限 | ✅ | 最大檔 single_watcher.rs 351 LOC |
| §四 max_retries=0 / live_reserved 不可改 | ✅ | 0 觸碰 — C3 全在 fail-safe 副系統 |
| spec §4.7 tick loop 不被 SM transition 阻塞 | ✅ | check_timer 三段拆分；state lock <1μs；async 部分無鎖 |
| spec §6.3 paper engine ExchangeStopSync noop | ⚠️ DEFERRED | `BybitExchangeStopSync` 本身不識別 engine_mode；paper noop 由 C4 wire 時透過「不對 paper engine 注入 `BybitExchangeStopSync`」實現（spec §4.3 line 188 計劃即如此 — `rest_clients: HashMap<&'static str, Arc<BybitRestClient>>` 不含 paper key） |
| spec §4.4 per-pipeline SM 升級獨立 | ✅ | watcher 持「無 risk_sm」狀態；caller（C4）對每個 pipeline 注入 `&mut RiskGovernorSm` |

**E2 重點審查清單對照（spec §12）**：

| 審查項 | 對照 |
|---|---|
| §12-1 Tick loop 不被 SM transition 阻塞 | 已實現「snapshot read（state lock <1μs） → drop → no-lock await → re-lock 標 guard」三段；T4.6 multi-thread 驗無 deadlock |
| §12-2 Paper engine ExchangeStopSync noop | C3 不直接負責；BybitExchangeStopSync 本身對 paper 不安全（會打真實 demo endpoint）— **必須由 C4 wire 階段以「不對 paper pipeline 注入此 sync」實現**（已在 § 5 不確定之處註明） |
| §12-3 Per-pipeline SM 升級獨立 | C3 watcher 不持 risk_sm；caller 注入。SharedFailsafeWatcher 持單一 timer state；不同 pipeline 之 risk_sm 由 C4 在 spawn task 內遍歷時各自 transition |

## 5. 不確定之處 / 已知 limitation（需 PM / C4 wire 接手解決）

### 5.1 ATR known-limitation（**HIGH** — 影響 fail-safe 鎖利路徑）

`PositionSnapshot.atr` 是「位置生命 ATR」，**Bybit V5 REST 不回 ATR**。本 C3
`RestPositionProvider` 暫設 `atr=0.0`，使 `active_lock_profit_per_position` 走
fail-closed 過濾（`pos.atr <= 0.0` 跳過）。

**後果**：當前 RestPositionProvider 喂出的 snapshot 永遠不會產生 `StopAdjustment`，
意即 fail-safe 升級到 SM-04 後 conditional SL 同步部分 **永遠 noop**（雖然 transition
本身仍會跑）。

**修正方案**（C4 wire 時必做）：
1. 在 spawn task 內注入 `PriceHistoryTracker` 或 `paper_state.position_life_atr` 旁路；
2. 把 `RestPositionProvider` 改為 `RestPositionProviderWithAtrInjection { atr_source: ... }`
   或在 watcher 上層 wrap 一層 ATR enrichment；
3. 或者：本 C3 的 `RestPositionProvider` 在 C4 wire 後降級成「測試用 fallback」，正式
   provider 是「paper_state 合併 + ATR injection」的新型。

PM 決策：**是否在 C4 接手前先派一個 C3.5 補 ATR 注入**？

### 5.2 spec §6.3 paper noop（**MEDIUM** — C4 wire 責任）

`BybitExchangeStopSync` 本身不識別 engine_mode，會 unconditionally 打傳入的
`PositionManager` 的 endpoint。spec §4.3 line 188 計劃以「`rest_clients: HashMap` 不
含 paper key」實現 paper noop。**C4 wire 時必須驗**：spawn task 對 paper pipeline 不
注入 `BybitExchangeStopSync`，而是注入 noop impl（簡單一個 `struct NoopExchangeStopSync;`
回 `Ok(())`）。

PA spec §12-2 列為 E2 重點審查 — 已交棒 C4 IMPL + E2 review。

### 5.3 `OnceLock` reset for cross-test isolation（**LOW** — test infra 已 workaround）

`OnceLock` 無 reset API；單一 test process 內若多個 test 都呼 `init` 會踩同一全域。
本 C3 test workaround：所有非 singleton test 走 `Arc::new(SharedFailsafeWatcher::new(...))`
旁路（不走全域），只 T4.4 一條 test 真正呼 `init` 驗單例語義。

風險：若 cargo test 並行跑 + 其他 test 也呼 `init`（理論上只有 T4.4），會競爭。本
crate 目前 T4.4 為唯一 caller，安全。**未來 C4 wire 加 spawn task 後**：production
binary 呼 `init` 一次；test 不應再用 global init（推薦 test 端永遠走 `new` 旁路）。

### 5.4 `dispatch_and_observe` 與 C4 mpsc outcome 通道之關係（**LOW** — 設計待 C4 拍）

spec §4.5 推薦選項 B：「incident_policy 偵測到事件 → 呼 `dispatcher.dispatch_3way`
→ outcome 透過 mpsc 送 watcher」。本 C3 提供兩個 API：
- `observe_dispatch(outcome)` — 直接餵 outcome（搭配外部 mpsc）
- `dispatch_and_observe(message)` — 內部 dispatch + observe（無 mpsc）

C4 選擇哪個？若選前者（mpsc 路徑）則 `dispatch_and_observe` 為 dead-but-tested code；
若選後者則 watcher 自主 trigger 但失去 incident_policy 解耦。建議 PM 在 C4 spec 明確
指定，避免 deferred decision。

## 6. Operator 下一步

| Step | 角色 | 動作 |
|---|---|---|
| 1 | PM | 審本 report，特別 § 5.1 ATR known-limitation 決策（C3.5 補 vs 留 C4 處理） |
| 2 | PM | 派 **E2 review** — C1/C2/C3 三 IMPL 對抗性核驗（per CLAUDE.md §八 強制鏈 E1→E2→E4→PM） |
| 3 | PM | 派 **E4 regression** — `cargo test -p openclaw_engine --lib` 全套（3540 + 31 新 = 3571）+ 之前 baseline 確認無漂移 |
| 4 | PM | E2 + E4 GREEN 後派 **QA sign-off** — 對抗性多角色 review（per `feedback_multi_role_strategic_review`） |
| 5 | PM | QA 過後決定 **C4 dispatch**：tasks.rs spawn + main.rs wire + IPC slot + ATR 注入修正 |
| 6 | PM | C4 land 後派 **Linux dry-run** — `restart_all --rebuild --keep-auth` 驗 SharedFailsafeWatcher init 成功 + 30s tick 正常 |

## 7. 數據摘要

| 指標 | 值 |
|---|---|
| 新檔數 | 4 |
| 修檔數 | 2 |
| 新 LOC | 1064 |
| Phase commits | 4 (`3b5b30aa` / `d44a3173` / `fbcc1aa9` / `3ba572ad`) |
| Providers tests | 31/31 PASS |
| notification_failsafe 全模塊 tests | 101/101 PASS（C1+C2+C3 合併） |
| Clippy 在 providers/ | 0 hit |
| 新 Cargo dep | 0 |
| 跨平台合規 | ✅ 無硬編碼 `/home/ncyu` / `/Users/[^/]+` |
| 新 singleton 登記 | `SHARED_WATCHER` static OnceLock — 需 PM 確認 singleton table 登記位置（CLAUDE.md §七 / §九） |

## 8. 自評（CLAUDE.md §二 原則檢核）

- ✅ 原則 1（單一寫入入口）：exchange sync 全走 PositionManager
- ✅ 原則 4（策略不繞 Guardian/risk）：watcher 注入端對 risk_sm 由 caller 持有，不繞
- ✅ 原則 5（survival > 收益）：fail-soft empty Vec / Transport 變體
- ✅ 原則 6（uncertainty → conservative）：所有未知 side / NaN size / negative SL 都跳過
- ✅ 原則 9（本地 + 交易所雙重防線）：`BybitExchangeStopSync` 走交易所 conditional path
- ✅ 原則 14（零外部成本可運行）：無新付費 SaaS / 無新 dep

## 9. 還沒做（顯式留給後續 wave）

- ❌ C4 `tasks.rs::spawn_notification_failsafe_watcher` — 留 Sprint 3
- ❌ C4 `main.rs` wire — 留 Sprint 3
- ❌ C4 IPC slot for outcome / ack — 留 Sprint 3
- ❌ C4 ATR 注入修正 — 留 Sprint 3（§ 5.1）
- ❌ C5 GUI banner endpoint — 留 Sprint 3
- ❌ incident_policy dispatch 觸發點 wire — 留 Sprint 3+（per spec §4.5 + §11.2）
- ❌ Linux PG dry-run + restart_all 真實驗證 — Mac 開發階段不適用，留 C4 land 後

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-28--e1_pc3_providers_impl.md`）

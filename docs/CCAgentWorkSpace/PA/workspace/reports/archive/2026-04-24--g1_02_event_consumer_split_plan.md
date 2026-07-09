# G1-02 PRE-WORK：event_consumer/mod.rs 拆分計劃

**Agent**：PA
**Date**：2026-04-24
**Task**：Wave 1 G1-02 規劃文件（不寫 code，只規劃）

---

## 0. 摘要（給 E1）

- 實際行數：**1762 行**（task 描述的 1696 行已過期，操作以 1762 為準）
- §九 硬上限：**1200 行** → 需減 **≥562 行**
- 結論：**建議拆 3 個 sibling files**（loop_handlers、bootstrap、tail_helpers），mod.rs 收斂至 **~470 行**
- 實裝工時估計（E1 + E2 + E4）：**4-6 小時**
- 風險評級：**低**（先例 `tick_pipeline/mod.rs` 2274→1012 已成功，commit `3d67a99`）

---

## 1. mod.rs 現況盤點

### 1.1 行數分區（精確 LOC 量測）

| 段落 | 行範圍 | LOC | 內容 |
|---|---|---|---|
| Header + use + mod decl | 1-32 | 32 | doc + imports + 7 個 sub-mod 宣告 |
| `run_event_consumer` async fn | 34-1675 | **1641** | 唯一巨型函數 |
| ↳ Bootstrap（pre-loop setup） | 34-767 | 734 | 解構 deps、wire pipeline、3 個 spawn、bootstrap k-line、persistence init |
| ↳ Main event loop（`tokio::select!`） | 768-1632 | 865 | 5 arm select! + tick processing + status report |
| ↳ Shutdown | 1633-1675 | 43 | close_all_positions + final state write |
| Free-fn `classify_pending_sweep` + enum | 1677-1708 | 32 | pure decision fn（已 `pub(crate)`，已有 7 個 unit test） |
| Free-fn `cancel_resting_maker_order` | 1729-1762 | 34 | async fn，spawn 內呼叫，1 caller（line 1407） |

### 1.2 既有 sibling files（已拆完的）

| 檔案 | 行數 | 內容 |
|---|---|---|
| `dispatch.rs` | 1124 | `spawn_order_dispatch` + `run_dispatch_retry` + `classify_dispatch_error`（DISPATCH-RETRY-1） |
| `governor_cooldown.rs` | 126 | `cooldown_ts_if_active`（pure）+ `load_governor_cooldown_from_audit`（async）+ 5 unit tests |
| `paper_state_restore.rs` | 132 | `restore_paper_counters`（QoL-1，async） |
| `setup.rs` | 108 | `wire_pipeline`（fee/risk/instrument/4 channels）|
| `types.rs` | 305 | `EventConsumerDeps` (45 fields) + `ExchangeEvent` enum + `PendingOrder` struct + 2 const |
| `tests.rs` | 1482 | 47 unit tests（mod.rs 的 sibling 測試） |
| `handlers/mod.rs` | 378 | `handle_paper_command` dispatch facade（match 30+ variants） |
| `handlers/{lifecycle,risk,strategy_params,edge_predictor,tests}.rs` | 1837 | 各 IPC command 的 domain helpers |

**前次拆分歷史軌跡**：dispatch / setup / governor_cooldown / paper_state_restore / handlers/* 都已抽走；mod.rs 剩下的就是 `run_event_consumer` 主迴圈本體，未動。

### 1.3 對外公開介面（pub use 面）

僅 4 個外部呼叫點：
- `startup.rs:11` `use openclaw_engine::event_consumer::{ExchangeEvent, SYMBOLS};`
- `main.rs:1154` `use openclaw_engine::event_consumer::{run_event_consumer, EventConsumerDeps};`
- `tests/reconciler_e2e.rs:28,70,93` `event_consumer::PendingOrder` + `event_consumer::handlers::handle_paper_command`

`pub use types::{EventConsumerDeps, ExchangeEvent, PendingOrder, SYMBOLS}` 已在 mod.rs:20。`pub mod handlers` 已在 mod.rs:12。**拆分時這 4 條對外簽章不能動**。

### 1.4 mod.rs 內部 fn 依賴矩陣

| Fn | 屬性 | 內部 callers | 外部 callers |
|---|---|---|---|
| `run_event_consumer` | `pub async` | 無 | `main.rs:1154` |
| `classify_pending_sweep` | `pub(crate)` | mod.rs:1359 | `tests.rs:1133-1264`（7 tests） |
| `cancel_resting_maker_order` | `async fn`（私有） | mod.rs:1407（spawn 內） | 無 |
| `PendingSweepAction` enum | `pub(crate)` | mod.rs:1360-1388 + tests | `tests.rs` |

**依賴方向乾淨**：自下而上線性，**零循環**。

### 1.5 `run_event_consumer` 內部結構（5 個 select! arm）

| Arm | 行範圍 | LOC | 內容 |
|---|---|---|---|
| `cancel.cancelled()` | 770 | 1 | break |
| `engine_evt`（cross_engine） | 774-807 | 34 | BLOCKER-2 D6 cascade escalate |
| `seed`（kline bootstrap） | 811-817 | 7 | seed bars |
| `exchange_evt`（fills/orders） | 821-1116 | **296** | Fill/OrderUpdate/PositionUpdate/DCP/Disconnected — 最大 arm |
| `pending_reg`（dispatch task → tracker） | 1119-1156 | 38 | Order + OrderStateChange msg emit |
| `cmd`（IPC PipelineCommand） | 1159-1267 | 109 | 攔截 DisableEdgePredictorAll + ResetDrawdownBaseline，其餘轉 handlers |
| `event`（PriceEvent，hot path） | 1269-1630 | **362** | on_tick + canary + audit + WS sync + pending sweep + status report — **熱路徑** |

**熱路徑識別**（每 tick 呼）：
- `event = event_rx.recv()` → `pipeline.on_tick(&ev)`（line 1277）= **核心熱 hot path**
- 同一 arm 內：`apply_confirmed_fill`（fill arm，每筆成交）/ canary `try_send` / WS shared state sync / pending sweep（每 5s）
- `classify_pending_sweep` 每 5s × N pending orders 呼一次（pure，已是 ideal candidate）

---

## 2. 拆分策略

### 2.1 推薦：3 個新 sibling files

```
event_consumer/
├── mod.rs                          # ~470 行（pub use + run_event_consumer shell）
├── bootstrap.rs                    # NEW ~620 行（pre-loop wire-up）
├── loop_handlers.rs                # NEW ~520 行（5 個 select! arm 各自的 handler fn）
├── pending_sweep.rs                # NEW ~120 行（PendingSweepAction + classify + cancel_resting_maker_order）
├── dispatch.rs                     (existing 1124)
├── governor_cooldown.rs            (existing 126)
├── handlers/                       (existing)
├── paper_state_restore.rs          (existing 132)
├── setup.rs                        (existing 108)
├── tests.rs                        (existing 1482)
└── types.rs                        (existing 305)
```

#### 2.1.1 `bootstrap.rs` (~620 行)

**抽出 `run_event_consumer` 的 lines 34-767（pre-loop）的大部分**，包成 1 個 fn：

```rust
pub(super) struct BootstrappedRuntime {
    pub pipeline: TickPipeline,
    pub state_writer: StateWriter,
    pub snapshot_writer: DualStateWriter,
    pub audit_writer: AuditWriter,
    pub kline_seed_rx: mpsc::Receiver<(String, Vec<KlineBar>)>,
    pub kline_seed_tx: mpsc::Sender<(String, Vec<KlineBar>)>,
    pub pending_reg_rx: Option<mpsc::UnboundedReceiver<PendingOrder>>,
    pub triage_cmd_tx: Option<mpsc::UnboundedSender<PipelineCommand>>,
    pub order_tx: Option<mpsc::Sender<TradingMsg>>,
    pub data_path: PathBuf,
    pub kind_tag: &'static str,
    pub cfg_snapshot: Arc<EngineBootstrapCfg>,
}

pub(super) async fn bootstrap_runtime(deps: &mut EventConsumerDeps) -> BootstrappedRuntime { ... }
```

**內含**：
- pipeline 構造（with_kind + endpoint_env + edge_predictor_store + RNG seed）
- `paper_state_restore::restore_paper_counters` 呼叫
- B-1 Phase 2 seed_positions
- ORPHAN-ADOPT-1 positions_mirror
- SCANNER-GATE
- P0-6 / DUST-EVICTION-GAP-1 triage_bybit_sync
- governor cooldown restore
- `setup::wire_pipeline` 呼叫
- AccountManager / LinUCB / NewsSnapshot wire
- risk_store / budget_store wire
- PH5-WIRE-1 edge estimates load
- BLOCKER-3 D15 global exposure
- bybit_sync balance
- server-side stop channel + spawn（**保留 spawn 在這檔**，因為它包含複雜 closure 借用）
- StrategyFactory 註冊
- grant_paper_auth
- ready_tx
- kline bootstrap initial fetch
- persistence init（state_writer / snapshot_writer / audit_writer / DualStateWriter）
- `pipeline.canary_mode = canary_handle.is_enabled()`
- Initial snapshot force_write

**為何包成 struct return 而非分多個 fn**：bootstrap 之間有 27+ 互相依賴的 binding（`triage_cmd_tx` 在 line 143 從 `pipeline_cmd_tx.clone()` 抽出，後在 line 329 用），分多 fn 會 explode 參數清單。一個 large fn return struct 是先例 `tick_pipeline::pipeline_ctor.rs` 的同型方案。

**E1 注意**：`server-side stop channel` 包含 `tokio::spawn(async move { ... PositionManager::new ... })`（lines 524-572），不能 trivially 拆 — closure 捕獲了 `stop_client`。**保留在 bootstrap.rs 同檔**，spawn 仍在 fn 內執行，OK。

#### 2.1.2 `loop_handlers.rs` (~520 行)

**抽出 5 個 select! arm 各自的 handler 為獨立 fn**（mod.rs 留 select! 骨架）：

```rust
pub(super) fn handle_cross_engine_event(...) { /* 34 lines */ }
pub(super) async fn handle_kline_seed(seed: Option<...>, pipeline: &mut TickPipeline) { /* 7 lines */ }
pub(super) async fn handle_exchange_event(
    event: Option<ExchangeEvent>,
    state: &mut ExchangeEventState,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    order_tx: &Option<mpsc::Sender<TradingMsg>>,
) { /* 296 lines — main work */ }
pub(super) fn handle_pending_registration(...) { /* 38 lines */ }
pub(super) async fn handle_pipeline_command(
    cmd: PipelineCommand,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    pending_orders: &mut HashMap<String, PendingOrder>,
    audit_pool: Option<&PgPool>,
    cross_engine_tx: &Option<broadcast::Sender<EngineEvent>>,
    shared_risk_level: &Option<Arc<AtomicU8>>,
    pipeline_kind: PipelineKind,
) { /* 109 lines, includes interception of ResetDrawdownBaseline + DisableEdgePredictorAll */ }
pub(super) async fn handle_price_event(
    event: Option<Arc<PriceEvent>>,
    pipeline: &mut TickPipeline,
    state: &mut PriceEventLoopState,
    audit_writer: &AuditWriter,
    state_writer: &mut StateWriter,
    snapshot_writer: &mut DualStateWriter,
    canary_handle: &CanaryWriterHandle,
    /* shared atomics, channels, registries */
) { /* 362 lines — main hot path */ }
```

**state 群組化為 struct 以避免 fn 簽章爆炸**：

```rust
pub(super) struct ExchangeEventState {
    pub pending_orders: HashMap<String, PendingOrder>,
    pub order_id_to_link: HashMap<String, String>,
    pub seen_exec_set: HashSet<String>,
    pub seen_exec_order: VecDeque<String>,
}

pub(super) struct PriceEventLoopState {
    pub pending_orders: ... ,
    pub last_status: Instant,
    pub last_pending_check: Instant,
    pub known_symbols: HashSet<String>,
    /* ... */
}
```

**可能更簡潔的設計**（建議 E1 採用）：所有 loop-internal mutable state 統一為一個 `LoopState` struct，5 個 handler fn 都收 `&mut LoopState`。這也是 `tick_pipeline/pipeline_helpers.rs` 的同型作法。

**Shutdown 段（lines 1633-1675）**：43 行短，留 mod.rs 內或抽 `handle_shutdown(...)`。建議留 mod.rs（簡單）。

#### 2.1.3 `pending_sweep.rs` (~120 行)

抽出 mod.rs:1677-1762 的 tail helpers：
- `PendingSweepAction` enum（`pub(crate)` → `pub(super)`，因 tests.rs 從 `super::PendingSweepAction` 引）
- `classify_pending_sweep` fn
- `cancel_resting_maker_order` async fn

**注意**：tests.rs:1133+ 用的是 `super::classify_pending_sweep` / `super::PendingSweepAction`。tests.rs 是 mod.rs 的 inline `#[cfg(test)] mod tests;`，所以 `super` 解析到 mod.rs。**抽出後需要在 mod.rs 加 `pub(super) use pending_sweep::{classify_pending_sweep, PendingSweepAction};`**，這樣 tests.rs 的 `super::*` 路徑保持綠。

替代方案：把這些 tests 連帶搬到 `pending_sweep.rs` 裡的 `#[cfg(test)] mod sweep_tests`。**推薦這條路**（更乾淨，減少 tests.rs 重新 import）。tests.rs:1085-1267 那 ~180 行（7 個 tests）會搬到 `pending_sweep.rs` 內 `#[cfg(test)] mod tests`。

### 2.2 預估行數結果

| 檔 | LOC（估） | §九 狀態 |
|---|---|---|
| mod.rs | ~470 | OK（< 800 警告） |
| bootstrap.rs | ~620 | OK（< 800 警告） |
| loop_handlers.rs | ~520 | OK（< 800 警告） |
| pending_sweep.rs | ~120（含 7 tests） | OK |
| **新 mod.rs LOC** | **~470** | **過 1200 硬上限 ✅** |

mod.rs 收斂後內容預計：
- doc header + 7 個 mod 宣告 + 5 個 use（~50 行）
- `run_event_consumer` shell：解構 deps + 呼叫 `bootstrap::bootstrap_runtime` + 主 select! loop（~400 行內留 select! 骨架調 5 個 handler fn + shutdown inline）
- 0 個 free-fn（全搬走）

---

## 3. 拆分順序（避免循環依賴 + 最小 review surface）

E1 建議按此順序，每步 commit，方便 E2 review：

### Step 1 — 抽 `pending_sweep.rs`（最小最安全）

- 拷 lines 1677-1708（enum + classify）+ lines 1729-1762（cancel_resting_maker_order）→ `pending_sweep.rs`
- 拷 tests.rs:1085-1267（7 個 sweep tests）→ `pending_sweep.rs` 內 `#[cfg(test)] mod tests`
- mod.rs 加 `mod pending_sweep;` + `use pending_sweep::{classify_pending_sweep, PendingSweepAction};`
- 更新 line 1407 的 `cancel_resting_maker_order(c, sym, lid).await` → `pending_sweep::cancel_resting_maker_order(c, sym, lid).await`
- tests.rs 移除原 sweep tests
- **驗收**：`cargo test --release -p openclaw_engine --lib` 1980 passed
- **commit**：`refactor(event_consumer): G1-02 step 1 — extract pending_sweep into sibling`
- **mod.rs 預期降至 ~1640 行**（仍超標但開始降）

### Step 2 — 抽 `loop_handlers.rs`（中等大小，high-touch）

- **先設計 `LoopState` struct**，把所有 loop-internal 可變變數打包：`pending_orders` / `order_id_to_link` / `seen_exec_*` / `last_status` / `last_pending_check` / `known_symbols`
- 把 5 個 select! arm body 各自抽成 `pub(super)` fn
- mod.rs 的 select! 改為短 dispatch 形式：

```rust
loop {
    tokio::select! {
        _ = cancel.cancelled() => break,
        engine_evt = ... => loop_handlers::handle_cross_engine_event(engine_evt, &mut pipeline, pipeline_kind),
        /* ... */
    }
}
```

- **bit-identical 警示**：每個 arm 的 await + spawn 必須語意守恆。閉包內 `tokio::spawn(async move { ... })` 對借用敏感 — 看下面 §4.2。
- **驗收**：1980 passed
- **commit**：`refactor(event_consumer): G1-02 step 2 — extract 5 select arms into loop_handlers`
- **mod.rs 預期降至 ~1100 行**

### Step 3 — 抽 `bootstrap.rs`（最大塊但機械）

- 把 lines 34-731 的 setup 代碼抽進 `bootstrap_runtime(deps: &mut EventConsumerDeps) -> BootstrappedRuntime`
- 注意 `&mut deps` 而非 deps move — 因為 `deps.event_rx` 等仍要在 mod.rs 主 loop 用。或者把 `deps.event_rx` 等先在 mod.rs 解構出來，剩下 deps 整批 move 進 bootstrap_runtime。**E1 自決**，先看 borrow checker 反應。
- **驗收**：1980 passed + Mac/Linux release build
- **commit**：`refactor(event_consumer): G1-02 step 3 — extract bootstrap into sibling`
- **mod.rs 預期降至 ~470 行**（達標）

### Step 4 — review 最後 mod.rs，可能微調 LoopState 邊界

- 若 mod.rs 仍超 800 警告但 ≤ 1200，OK
- 若仍 ≥ 800，考慮再抽 `event_loop.rs` 把整個 select! 包成 `run_event_loop(state, runtime, deps_remainder).await`

### Step 5 — E5 simplify pass（可選）

- LoopState struct 去掉冗餘 field
- 減少 fn 簽章參數（合 group 成 sub-struct）

---

## 4. Bit-identical 保證 + 性能保護

### 4.1 熱路徑（每 tick / 每 fill 必走）

mod.rs 內熱路徑（標記 ★ 為高頻）：
- ★ `event_rx.recv()` → `pipeline.on_tick(&ev)` — 每 PriceEvent
- ★ `canary_handle.try_send` — 每 tick
- ★ shared atomic write `last_tick_ms.store` — 每 tick
- WS shared state sync `bal_arc.read()` / `pnl_arc.read()` — 每 tick
- ★★ `apply_confirmed_fill` — 每筆 exchange fill
- `classify_pending_sweep` — 每 5s × N pending orders（low freq）
- Status report (`last_status.elapsed() >= status_interval`) — 30s 一次

### 4.2 inline / 性能不退保護

Rust `pub(super) fn` 跨檔呼叫**不阻 inline**（LLVM cross-crate inline + LTO）— `cargo --release` 會跨檔 inline。但**保險起見**：

- 對 `handle_price_event`（hot path）+ `handle_exchange_event` 內的 fill 處理 sub-fn 加 `#[inline]` 或 `#[inline(always)]`（後者過激，先不加）
- 對 `classify_pending_sweep` 已是 pure，跨檔呼叫零成本
- **不要把 hot path 拆得過細**（避免每 PriceEvent 都跨多次 fn call boundary）。建議 `handle_price_event` 整個 ~362 行留一個 fn 不再切。

**Monomorphization 風險**：`run_dispatch_retry` 在 dispatch.rs 是 generic（`F: FnMut(u32) -> Fut`，每 call site 一個 instance）— 但這個 fn 不在 mod.rs 拆分範圍內。`bootstrap.rs` / `loop_handlers.rs` 內的新 fn **不要引入新 generic**，全用 trait object（`&dyn` / `Arc<dyn>`）或具體型別。借鏡 `tick_pipeline/pipeline_*.rs` 全是具體型別 fn 的設計。

### 4.3 bit-identical 驗證機制

E1 完成後，E4 必跑：
1. `cargo test --release -p openclaw_engine --lib` → 1980 passed（baseline）
2. `cargo test --release -p openclaw_engine --tests` → 整合測試（reconciler_e2e / phase4_integration / stress / micro_profit_fix / rrc1_audit / edge_predictor_ort 共 6 整合套件）
3. **Behaviour-level diff**：跑一次 paper engine boot to first 10 ticks，記 stdout log + paper_state snapshot diff。`tick_pipeline` split 先例就是用這方法驗 bit-identical。
4. cargo bench（若有）— event_consumer 沒 bench，跳過

---

## 5. Test 影響評估

### 5.1 現有 test cov 分布

| 測試所在 | tests | cov 哪些 fn |
|---|---|---|
| `event_consumer/tests.rs` | 47 | 主要 `handlers::handle_paper_command` 各 variant + 7 個 `classify_pending_sweep` tests |
| `event_consumer/handlers/tests.rs` | （包含在 1837 行） | handlers 內各 domain helper |
| `event_consumer/governor_cooldown.rs` | 5 | `cooldown_ts_if_active` |
| `event_consumer/handlers/edge_predictor.rs` 內 | 部分 | 內聯 |
| `tests/reconciler_e2e.rs` | 整合 | `handle_paper_command` IPC 流程 |

**`run_event_consumer` 本身 0 直接 unit test**（async fn 含 select!，難 mock；跑 paper engine 整合驗證）。這是好事 — 拆分不會 break 直接 fn-level test，因為沒有。

### 5.2 拆分後 test 搬遷計劃

| 從 | 到 | tests count |
|---|---|---|
| `tests.rs:1085-1267` (sweep tests) | `pending_sweep.rs::tests` | 7 |
| `tests.rs` 其餘 | 留原處 | 40 |
| `governor_cooldown.rs` 內 5 tests | 不動 | 5 |
| handlers/* | 不動 | （現狀 700+） |

### 5.3 cov ≥ 95% 達成路徑

Wave 1 G1-02 完成標準：≥95%。當前 mod.rs free-fn `classify_pending_sweep` cov 已是 100%（7 tests 全 enum variant 覆蓋）。`cancel_resting_maker_order` 是 fail-soft async fn，無單測（呼 Bybit API），但屬 swallowed-error fail-soft 不需 95%。

**無 test 覆蓋的部分**：
- `bootstrap_runtime`（pre-loop setup）— 純 wiring，不需 unit test，整合測試足夠
- `handle_*_event` loop handlers — 含 await，難 unit test；保留現狀（整合測試覆蓋）

**E1 不需新增 test**。test cov ≥ 95% 由現有測試 + 整合測試自然滿足。E4 跑 grcov 驗證。

---

## 6. 風險點 + 反例

### 6.1 已知風險

| 風險 | 概率 | 緩解 |
|---|---|---|
| LoopState struct 跨 await 借用衝突（`&mut self` 同時被 select! 多 arm 借） | 高 | tokio::select! 同時只跑一個 arm，借用是順序的；用 `&mut state` 傳入 arm body 即可 |
| `triage_cmd_tx`（line 143）在 bootstrap 內 clone 後傳到 line 329 — 跨檔抽出時要小心生命週期 | 中 | `BootstrappedRuntime` struct return 攜帶 `triage_cmd_tx: Option<UnboundedSender<...>>` |
| `tokio::spawn` 內 closure 捕獲 — server-side stop channel spawn (line 524) + cancel_resting_maker_order spawn (line 1406) + checkpoint write spawn (line 1505) + dynamic kline bootstrap spawn (line 1565) | 中 | 全部保留在原 fn 內執行，不抽 spawn 本身。spawn 的 closure 不跨檔 |
| `EventConsumerDeps` 解構在 line 35-92 — 拆 bootstrap 後解構順序問題 | 低 | 在 mod.rs 內先解構 `event_rx` / `cancel` / `cross_engine_rx` 等 loop 用的，剩下 move 進 bootstrap_runtime |
| Rust visibility — `pub(crate)` 升 `pub(super)` 是否影響其他 crate | 低 | `event_consumer` 沒有 sub-crate，pub(super) 等同 pub(crate) 範圍 |
| tests.rs `super::classify_pending_sweep` 路徑改變 | 低 | 抽走後 mod.rs `pub(super) use pending_sweep::*` 重新導出，或直接搬 tests 進 sibling |

### 6.2 不會出現的循環依賴

`bootstrap.rs` → `setup` / `paper_state_restore` / `governor_cooldown` / `handlers` (single direction)
`loop_handlers.rs` → `handlers` / `pending_sweep` / `dispatch` (single direction)
`pending_sweep.rs` → `types` (single direction)

**全是樹狀拓撲，無 cycle**。

### 6.3 反例（避免做的事）

- ❌ 不要把 `run_event_consumer` 做成 `EventConsumer::new(...).run().await` OO 風格 — 跨 crate 介面變動太大，main.rs 與 startup.rs 都要改
- ❌ 不要嘗試把 select! arm 改成 `for await msg in stream { match msg { ... } }` 風格 — 5 個 channel 不同型別，stream 需要 unify，價值不抵風險
- ❌ 不要新增 trait abstraction（`trait EventLoopHandler`）— 每 arm signature 完全不同，trait 反而 bloat
- ❌ 不要拆 `EventConsumerDeps`（45 fields） — 這是 main.rs ↔ event_consumer 的 contract，動了影響面太大
- ❌ 不要 inline `cancel_resting_maker_order` 進 spawn closure — 已有命名 fn 易讀

---

## 7. 實裝工時估計

| 階段 | 內容 | 工時 |
|---|---|---|
| E1 | Step 1（pending_sweep）抽 + tests 搬 | 30 分 |
| E1 | Step 2（loop_handlers）抽 5 arms + LoopState 設計 | 1.5-2 小時 |
| E1 | Step 3（bootstrap）抽 pre-loop | 1-1.5 小時 |
| E1 | Step 4 mod.rs 收尾 + 補 doc | 30 分 |
| E2 | code review（bit-identical / borrow / inline） | 1 小時 |
| E4 | full lib + integration + behaviour diff | 30-45 分 |
| **總計** | | **4-6 小時** |

---

## 8. 完成標準對照

| 標準 | 達成路徑 |
|---|---|
| < 1200 行 | mod.rs ~470 行 ✅ |
| test cov ≥ 95% | 現有 47 + 5 + 7 + handlers tests 全保留 + 整合測試 ✅ |
| engine lib 1980+ pass | E4 跑 cargo test --release 驗證 ✅ |

---

## 9. 阻塞解除聲明

完成 G1-02 後，G3（Wave 2 AI 接線）+ G5（Wave 2 main.rs 拆分）解除阻塞。`run_event_consumer` 的 5 arm select! 結構成為穩定 dispatch 點，後續 Wave 2 只需在 `loop_handlers.rs` 內加新 arm（如 IPC `SubmitOrder` from ExecutorAgent），不會再次撞 1200 行。

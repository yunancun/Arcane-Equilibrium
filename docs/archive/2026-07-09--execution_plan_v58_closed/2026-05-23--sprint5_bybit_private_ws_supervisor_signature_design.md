---
spec: Sprint 5+ BybitPrivateWs supervisor signature 改造 design
date: 2026-05-23
author: PA
phase: Sprint 5+ §4.2.1 P1（Sprint 4+ first Live carry-over）
status: SPEC-DRAFT-V0
parent:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md §4.2.1
  - srv/docs/architecture/singleton-registry.md §2.1.3.a + §2.1.4.a + §6.3
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md（Wave B E2 round 1 MEDIUM-2 finding）
scope: BybitPrivateWs supervisor signature 改造 + main_health_emitters 對應 wire-up + spawn_private_ws_supervisor 橋接 design only；不 IMPL
---

# §1 Context — Wave B E2 round 1 MEDIUM-2 finding

## §1.1 半實裝陷阱 literal 揭露

per `rust/openclaw_engine/src/main_health_emitters.rs:174-205`（PA-DRIFT-4 Wave B round 2 MEDIUM-2 fix 揭露）：

- `rust/openclaw_engine/src/bybit_private_ws.rs:577-585` Wave A IMPL 已實裝 `dropout_counter_handle()` + `rtt_histogram_handle()` 兩個 `pub fn` expose accessor
- 但 `main_health_emitters.rs:218-219` `build_real_api_latency_probe` **不呼叫** expose；每次走 `Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())` 0-state instance 構造 probe
- 後果：30 天 V106 row `api_latency__ws_rtt_p50_ms` / `api_latency__ws_rtt_p99_ms` / `api_latency__ws_dropout_count` 全 0 染色；「全 0」**不是** production WS 健康反映「無 dropout / 低 latency」，是 emit chain 從 production BybitPrivateWs supervisor 完全 disconnect 副作用

## §1.2 RCA — 為什麼 Wave B 無法接 supervisor handle

per `main_health_emitters.rs:163-172` 既有 module note：

- `BybitPrivateWs::new()` 既有 signature 內部 own Arc（line 564-565：`Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())`）
- `startup/private_ws.rs:230-267` supervisor 走 RE-2 restart loop，**每次 reconnect attempt 都 `BybitPrivateWs::new()` 重建**（line 240-246）= 每次 attempt 一個全新 internal Arc instance
- main.rs 外部無穩定 share Arc handle 拿到 supervisor 內部 Arc（supervisor task 是 detached `tokio::spawn`，handle 僅返 `JoinHandle<()>` 不含 instrumentation）
- Wave B 走 `Arc::new(...)` placeholder 是「不破既有業務邏輯」前提下的唯一可行 fallback（per dispatch §禁忌 5.5 (a) (b)）

## §1.3 為什麼 Sprint 5+ 必修

- caller_chain SSOT（per singleton-registry.md §3.4 反模式 2）：「placeholder fresh 0-state 等同接通 production」誤判 = 永久 governance gap
- M3 Health Monitoring（ADR-0042 Decision 3）`api_latency` domain WS half 4 metric 全 placeholder = 真實 production WS 健康觀測缺位
- ADR-0042 Decision 3 cascade gate 預警「dropout > 5 / 60s 升 CRITICAL」永遠不會 fire（因為 source 端 fresh 0-state Arc 永遠 count=0）

---

# §2 改造 design

## §2.1 Option A vs Option B 對照

| 維度 | Option A — caller external Arc 注入 | Option B — install_external_handles() method |
|---|---|---|
| signature 改動 | `BybitPrivateWs::new()` 加 2 個 Arc 參數（破 既有 caller API） | `BybitPrivateWs::new()` 保留；新增 `install_external_handles(d, r)` |
| type-level enforcement | YES — compile error 強制 caller 傳 Arc（無 placeholder bypass 可能） | NO — caller 可忘記呼 install；internal default Arc 永遠存在 |
| race window | 0 — 構造瞬間即 wire 完成 | 存在 race — install 前 internal Arc 接收 measurement，install 後 swap 丟失 |
| supervisor reconnect 影響 | per-attempt `BybitPrivateWs::new()` 注入同一個 external Arc clone = 跨 attempt single instance ✅ | per-attempt 內部 default Arc → caller 再 install 慢一拍：race window 內 measurement loss |
| caller 端複雜度 | 中 — main.rs / startup/private_ws.rs 各加一條 Arc 構造 | 高 — caller 端走 new() → install() 兩步驟；忘其一就回半實裝陷阱 |
| 既有 caller impact | startup/private_ws.rs:240 + bybit_private_ws.rs:1184/1211（兩 inline test）+ tests/api_latency_probe_real_impl.rs（已用 `WsDropoutCounter::new()` fixture pattern；不破） | 0 改動 — 但 install 是 silent failure 風險面 |
| 回歸 / 半實裝風險 | 0 — 改 signature 後類型系統強制 | 高 — install 一個但忘第二個是合法 compile + runtime 半盲 |

## §2.2 Option A chosen — Rationale

E2 Wave B round 1 MEDIUM-2 推薦 + PA 確認，理由：

1. **type-level enforcement**（最重要）：Rust 類型系統強制 caller 構造 Arc 並注入；不存在「忘呼 install」回半實裝陷阱可能
2. **0 race window**：BybitPrivateWs 構造瞬間即接通；不存在 install 前 default Arc 接收 measurement 又被 swap 丟失 risk
3. **既有 SharedClientsBundle pattern 對齊**：main_instruments.rs:70-81 已建立「`live_bindings + demo_bindings` 抽 shared Arc」既有 pattern；ws_dropout / ws_rtt 走同模式 = 既有架構自然延伸（per `feedback_no_dead_params` + dispatch §5.5 反模式對齊）
4. **caller impact 可控**：4 處 caller 全在 PA 掌握範圍（startup/private_ws.rs + 2 inline test + tests/api_latency_probe_real_impl.rs 是純 fixture 不涉 supervisor）；E1 IMPL 6 hr 內可完成

---

# §3 BybitPrivateWs::new() signature 改動

## §3.1 before vs after

### before（current production，bybit_private_ws.rs:544-567）

```rust
impl BybitPrivateWs {
    pub fn new(
        api_key: String,
        api_secret: String,
        env: BybitEnvironment,
        cancel: CancellationToken,
        event_tx: mpsc::Sender<PrivateWsEvent>,
    ) -> Self {
        Self {
            api_key,
            api_secret,
            environment: env,
            cancel,
            event_tx,
            unknown_guard: UnknownHandlerGuard::new_arc(),
            dropout_counter: Arc::new(WsDropoutCounter::new()),  // ← 內部 own
            rtt_histogram: Arc::new(WsRttHistogram::new()),       // ← 內部 own
        }
    }
}
```

### after（Sprint 5+ Wave C，新 signature）

```rust
impl BybitPrivateWs {
    pub fn new(
        api_key: String,
        api_secret: String,
        env: BybitEnvironment,
        cancel: CancellationToken,
        event_tx: mpsc::Sender<PrivateWsEvent>,
        // PA-DRIFT-4 Sprint 5+ §4.2.1：caller external Arc 注入
        // （per singleton-registry.md §6.3）
        dropout_counter: Arc<WsDropoutCounter>,
        rtt_histogram: Arc<WsRttHistogram>,
    ) -> Self {
        Self {
            api_key,
            api_secret,
            environment: env,
            cancel,
            event_tx,
            unknown_guard: UnknownHandlerGuard::new_arc(),
            dropout_counter,  // ← caller injection
            rtt_histogram,    // ← caller injection
        }
    }
}
```

### 注釋 design

```rust
/// PA-DRIFT-4 Sprint 5+ §4.2.1：caller external Arc 注入（取代 Wave A 內部 own
/// pattern）。
///
/// 為什麼 caller 注入而非內部 own:
///   - supervisor (startup/private_ws.rs) RE-2 restart loop 每次 attempt 重建
///     BybitPrivateWs；內部 own 模式下每次 attempt 新 Arc instance =
///     main_health_emitters 端 probe 永遠拿不到穩定 Arc reference。
///   - caller 構造 Arc 後在 supervisor + probe 兩端共享同一 instance；
///     supervisor reconnect 不丟 measurement，probe 觀測 production 真實 WS
///     metric。
///   - 對齊既有 SharedClientsBundle pattern（main_instruments.rs:70-81）— shared
///     Arc 從 binding extract 走 main.rs 編排，子模塊純消費。
///
/// 為什麼不走 install_external_handles() option B:
///   - option B caller 走 new() → install() 兩步驟；忘 install 是合法 compile +
///     runtime 半盲（per spec §2.1 對照）。
///   - option A type-level enforcement：caller 必傳 Arc，compile 強制；
///     0 race window。
pub fn new(...)
```

## §3.2 Caller impact 全清單

### Caller 1: `startup/private_ws.rs:240-246` — RE-2 supervisor restart loop

**改動**：supervisor task 內 BybitPrivateWs::new() 加 2 個 Arc clone 參數；Arc 在 supervisor task 外層（spawn_private_ws_supervisor fn 內）構造一次 + 跨 task move

```rust
// before（startup/private_ws.rs:234-267）
let ws_handle = tokio::spawn(async move {
    let mut supervisor_attempt: u32 = 0;
    loop {
        if sv_cancel.is_cancelled() { break; }
        let priv_ws = BybitPrivateWs::new(
            api_key.clone(),
            api_secret.clone(),
            env,
            sv_cancel.clone(),
            priv_tx.clone(),
        );
        priv_ws.run().await;
        // ... restart backoff
    }
});

// after（同 fn，Arc 在 task spawn 前構造）
let dropout_counter: Arc<WsDropoutCounter> = Arc::new(WsDropoutCounter::new());
let rtt_histogram: Arc<WsRttHistogram> = Arc::new(WsRttHistogram::new());
// 兩個 Arc clone 注入 supervisor task move closure
let dropout_for_supervisor = Arc::clone(&dropout_counter);
let rtt_for_supervisor = Arc::clone(&rtt_histogram);
let ws_handle = tokio::spawn(async move {
    let mut supervisor_attempt: u32 = 0;
    loop {
        if sv_cancel.is_cancelled() { break; }
        let priv_ws = BybitPrivateWs::new(
            api_key.clone(),
            api_secret.clone(),
            env,
            sv_cancel.clone(),
            priv_tx.clone(),
            Arc::clone(&dropout_for_supervisor),  // ← 跨 attempt 同 instance
            Arc::clone(&rtt_for_supervisor),
        );
        priv_ws.run().await;
        // ... restart backoff
    }
});
```

### Caller 2: `bybit_private_ws.rs:1184-1190` + `1211-1217` — inline integration tests

**改動**：2 個 `#[test]` 測試 BybitPrivateWs::new() 構造，加 2 個 `Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())` 參數（test fixture 範式，符合 §2.2 對齊既有 `tests/api_latency_probe_real_impl.rs` pattern）

```rust
// test_auth_message_structure / test_auth_signature_deterministic
let ws = BybitPrivateWs::new(
    "TEST_API_KEY".into(),
    "TEST_API_SECRET".into(),
    BybitEnvironment::Demo,
    cancel,
    tx,
    Arc::new(WsDropoutCounter::new()),  // ← test fixture
    Arc::new(WsRttHistogram::new()),
);
```

### Caller 3: `tests/api_latency_probe_real_impl.rs` — integration test crate

**不涉本 spec 改動**。既有用法只是 `WsDropoutCounter::new()` + `WsRttHistogram::new()` 直接 mock fixture，不走 BybitPrivateWs supervisor；signature 改不影響。

## §3.3 spawn_private_ws_supervisor 橋接 design

`startup/private_ws.rs:71-77` `pub(crate) fn spawn_private_ws_supervisor` signature **不變**（避免 build_exchange_pipeline / pipeline_slot 跨模塊 caller 連動）。改在 fn 內部：

1. 在 `spawn_private_ws_supervisor` 內 line 82 後（mpsc channel 構造完成）加 2 條 Arc 構造（dropout + rtt）
2. 在 RE-2 supervisor task spawn 前 clone 2 個 Arc 注入 closure（per §3.2 Caller 1 改造）
3. 在 fn 返回的 `PrivateWsBindings` struct **新增 2 個 Arc field** `dropout_counter` + `rtt_histogram`（pub）；caller 拿到後可在 main_health_emitters 端 Arc::clone 注入 probe

### PrivateWsBindings 改動

```rust
// before（startup/private_ws.rs:54-60）
pub(crate) struct PrivateWsBindings {
    pub bybit_balance: Arc<parking_lot::RwLock<Option<f64>>>,
    pub api_pnl: Arc<parking_lot::RwLock<std::collections::HashMap<String, f64>>>,
    pub exchange_event_rx: mpsc::UnboundedReceiver<ExchangeEvent>,
}

// after（PA-DRIFT-4 Sprint 5+ §4.2.1）
pub(crate) struct PrivateWsBindings {
    pub bybit_balance: Arc<parking_lot::RwLock<Option<f64>>>,
    pub api_pnl: Arc<parking_lot::RwLock<std::collections::HashMap<String, f64>>>,
    pub exchange_event_rx: mpsc::UnboundedReceiver<ExchangeEvent>,
    /// PA-DRIFT-4 Sprint 5+ §4.2.1：caller external Arc 注入 pattern；
    /// supervisor RE-2 restart loop 跨 attempt 共享同 instance；main.rs
    /// 從 bindings.dropout_counter Arc::clone 注入 M3 emitter probe。
    pub dropout_counter: Arc<openclaw_engine::bybit_private_ws::WsDropoutCounter>,
    /// PA-DRIFT-4 Sprint 5+ §4.2.1：同上；M3 V106 `api_latency__ws_rtt_*`
    /// emit chain source。
    pub rtt_histogram: Arc<openclaw_engine::bybit_private_ws::WsRttHistogram>,
}
```

### `build_exchange_pipeline` 連動

`startup/mod.rs:497-513` `ExchangePipelineBindings` 已含 `ws_bindings: PrivateWsBindings`；不需新增 field。caller 從 `live_bindings.ws_bindings.dropout_counter` / `rtt_histogram` 拿。

## §3.4 main_health_emitters.rs 對應 wire-up

### 改動 1: `spawn_metric_emitter_scheduler` signature 加 2 個 ws Arc

```rust
// before（main_health_emitters.rs:362-373）
pub(crate) fn spawn_metric_emitter_scheduler(
    db_pool: &Arc<DbPool>,
    pool_max_conn: u32,
    data_dir_mount: &str,
    shared_client: &Option<Arc<BybitRestClient>>,
    engine_mode_str: &'static str,
    cancel: &CancellationToken,
) -> (
    Arc<ParkingMutex<PortfolioStateCache>>,
    Arc<HealthEventBus>,
)

// after（PA-DRIFT-4 Sprint 5+ §4.2.1）
pub(crate) fn spawn_metric_emitter_scheduler(
    db_pool: &Arc<DbPool>,
    pool_max_conn: u32,
    data_dir_mount: &str,
    shared_client: &Option<Arc<BybitRestClient>>,
    // PA-DRIFT-4 Sprint 5+ §4.2.1：WS supervisor instrumentation Arc 注入
    shared_ws_dropout: &Option<Arc<WsDropoutCounter>>,
    shared_ws_rtt: &Option<Arc<WsRttHistogram>>,
    engine_mode_str: &'static str,
    cancel: &CancellationToken,
) -> (...)
```

### 改動 2: `build_api_latency_emitter` + `build_real_api_latency_probe` signature 改造

```rust
// after
fn build_real_api_latency_probe(
    shared_client: &Arc<BybitRestClient>,
    shared_ws_dropout: &Arc<WsDropoutCounter>,  // ← 新增
    shared_ws_rtt: &Arc<WsRttHistogram>,         // ← 新增
) -> RealApiLatencySourceProbe {
    let rest_latency: Arc<RestLatencyHistogram> = shared_client.latency_histogram_handle();
    let ret_code_counter: Arc<RetCodeCounter> = shared_client.ret_code_counter_handle();
    // PA-DRIFT-4 Sprint 5+ §4.2.1：caller 注入的 production WS Arc clone
    // （取代 Wave B placeholder fresh 0-state Arc）
    let ws_dropout: Arc<WsDropoutCounter> = Arc::clone(shared_ws_dropout);
    let ws_rtt: Arc<WsRttHistogram> = Arc::clone(shared_ws_rtt);
    RealApiLatencySourceProbe::new(rest_latency, ret_code_counter, ws_dropout, ws_rtt)
}

fn build_api_latency_emitter(
    shared_client: &Option<Arc<BybitRestClient>>,
    shared_ws_dropout: &Option<Arc<WsDropoutCounter>>,
    shared_ws_rtt: &Option<Arc<WsRttHistogram>>,
) -> Box<dyn DomainEmitter> {
    match (shared_client, shared_ws_dropout, shared_ws_rtt) {
        (Some(client), Some(dropout), Some(rtt)) => {
            let probe = build_real_api_latency_probe(client, dropout, rtt);
            Box::new(ApiLatencyEmitter::new(probe))
        }
        // 任一缺席走全 placeholder fallback（paper-only / cold-start no-binding）
        _ => {
            let probe = RealApiLatencySourceProbe::new(
                Arc::new(RestLatencyHistogram::new()),
                Arc::new(RetCodeCounter::new()),
                Arc::new(WsDropoutCounter::new()),
                Arc::new(WsRttHistogram::new()),
            );
            Box::new(ApiLatencyEmitter::new(probe))
        }
    }
}
```

### 改動 3: module note 174-205 placeholder 揭露段刪除 + 改 production wire-up note

```rust
// 為什麼 caller 注入而非內部 own（per Sprint 5+ §4.2.1 spec §2.2 + §3 design）:
//   - bybit_private_ws.rs:577-585 Wave A 已實裝 dropout_counter_handle /
//     rtt_histogram_handle accessor；但 supervisor RE-2 restart loop 每次
//     attempt 重建 BybitPrivateWs（startup/private_ws.rs:240），內部 own 模式
//     下每次 attempt 新 Arc instance = probe 永遠拿不到穩定 reference。
//   - Sprint 5+ §4.2.1 改 BybitPrivateWs::new() 加 dropout_counter +
//     rtt_histogram 2 個 Arc 參數；caller 構造後跨 attempt 共享同 instance
//     注入 supervisor + probe，30 天 V106 row 反映 production WS 真實
//     metric。
//   - 對齊既有 SharedClientsBundle pattern（main_instruments.rs:70-81）— shared
//     Arc 從 binding extract 走 main.rs 編排。
```

## §3.5 main.rs caller 端 SharedClientsBundle 連動

`main_instruments.rs:40-45` SharedClientsBundle 加 2 個 field：

```rust
// after（PA-DRIFT-4 Sprint 5+ §4.2.1）
pub(crate) struct SharedClientsBundle {
    pub shared_client: Option<Arc<BybitRestClient>>,
    pub shared_account_manager: Option<Arc<AccountManager>>,
    pub shared_instruments: Option<Arc<InstrumentInfoCache>>,
    pub paper_balance: f64,
    /// PA-DRIFT-4 Sprint 5+ §4.2.1：WS supervisor instrumentation shared Arc
    /// （live > demo 優先級對齊 shared_client 抽取規則）；M3 emit chain source。
    pub shared_ws_dropout: Option<Arc<WsDropoutCounter>>,
    pub shared_ws_rtt: Option<Arc<WsRttHistogram>>,
}
```

`init_shared_clients_and_instruments` 內 extract pattern：

```rust
let shared_ws_dropout: Option<Arc<WsDropoutCounter>> = live_bindings
    .as_ref()
    .map(|b| Arc::clone(&b.ws_bindings.dropout_counter))
    .or_else(|| demo_bindings.as_ref().map(|b| Arc::clone(&b.ws_bindings.dropout_counter)));
let shared_ws_rtt: Option<Arc<WsRttHistogram>> = live_bindings
    .as_ref()
    .map(|b| Arc::clone(&b.ws_bindings.rtt_histogram))
    .or_else(|| demo_bindings.as_ref().map(|b| Arc::clone(&b.ws_bindings.rtt_histogram)));
```

main.rs:1440-1448 caller 改動：

```rust
let (portfolio_cache, _health_event_bus) =
    main_health_emitters::spawn_metric_emitter_scheduler(
        &db_pool,
        cfg_snap_for_pool.database.pool_max_connections,
        &data_dir_mount,
        &shared_client,
        &shared_ws_dropout,  // ← 新增（從 SharedClientsBundle 拿）
        &shared_ws_rtt,       // ← 新增
        primary_engine_mode,
        &cancel,
    );
```

---

# §4 Acceptance Criteria

## AC-1 — Supervisor 持有外部 Arc reference（single instance across reconnects）

**驗證方法**：

- grep `BybitPrivateWs::new()` 全 caller，確認 startup/private_ws.rs:240 內走 `Arc::clone(&dropout_for_supervisor)` + `Arc::clone(&rtt_for_supervisor)` 跨 attempt 同 instance
- inline 加 `debug_assert` 或 trace log 確認 supervisor task 啟動時 Arc::strong_count >= 2（supervisor + caller 各持一）
- E2 round 1 必檢「per-attempt 新 Arc」反模式 grep 0 hit

## AC-2 — main_health_emitters.rs 真實 inject Arc handle（not fresh new）

**驗證方法**：

- grep `main_health_emitters.rs` 內 `Arc::new(WsDropoutCounter::new())` 出現位置 ≤ 1（只剩 build_api_latency_emitter fallback 路徑，即 shared_ws_dropout=None 時的 cold-start fallback）；hot path probe 構造走 `Arc::clone(shared_ws_dropout)`
- 同理 `Arc::new(WsRttHistogram::new())` ≤ 1
- module note placeholder 揭露段（line 174-205）改為 production wire-up note（per §3.4 改動 3）

## AC-3 — 30 天 V106 row ws_rtt/ws_dropout 真實 production WS metric

**驗證方法（per Phase 3c QA AC-1b SOP）**：

- Linux runtime `ssh trade-core` 部署完成後 wait 60s（emitter interval 60s）
- psql query：

```sql
SELECT
  metric_name,
  observed_value,
  state,
  observed_at
FROM health_observations
WHERE domain = 'api_latency'
  AND metric_name IN ('ws_rtt_p50_ms', 'ws_rtt_p99_ms', 'ws_dropout_count')
  AND observed_at >= NOW() - INTERVAL '5 minutes'
ORDER BY observed_at DESC
LIMIT 50;
```

- 預期：30 min 後 ≥ 5 row 含非全 0 樣本（注：cold WS 帳戶可能 dropout=0 屬正常，但 ws_rtt 因 ping/pong 每 20s 必有 sample → p50 應 > 0）
- 持續監控：deploy 後 24 hr V106 row 樣本 ≥ 1000，ws_rtt_p50 中位數 應在 50-200ms（per Bybit Demo endpoint typical RTT）

## AC-4 — cargo test 回歸不退（PA-DRIFT-4 Wave A + Wave B）

**驗證方法**：

- `cargo test --workspace --release` 全 PASS（基準 Sprint 4+ Wave B 後 3961 pass）
- 重點測試保留：
  - `bybit_private_ws::tests::test_auth_message_structure` PASS（caller 改後簽名仍正確）
  - `bybit_private_ws::tests::test_auth_signature_deterministic` PASS
  - `tests/api_latency_probe_real_impl.rs` 全 PASS（純 fixture 用法不變）
- cargo build --release 0 warning（新加參數 doc comment 完整覆蓋）

## AC-5 — production binary 0 spike feature 滲透

**驗證方法**：

- restart_all.sh --rebuild 後 binary 5月23 mtime
- strings binary | grep -E 'dropout_counter|rtt_histogram' hit ≥ 4（accessor + struct field）
- engine PID 啟動 log 含 `M3 metric emitter scheduler + PortfolioStateCache update task wired (Sprint 4+ first Live Wave B; Track A/C/F real + B/D placeholder + E skip)`；本 Sprint 5+ §4.2.1 後改 `Track A/C/D/F real + B placeholder + E skip`（Track D WS half 升 real）
- 0 panic / 0 unwrap-on-None / 0 race 報告（E2 round 必檢）

---

# §5 Sprint 5+ §4.2.1 IMPL phase split

## Phase 1 — PA refine（本 spec 後續 PA 收尾，0.5 hr）

- 補 PrivateWsBindings field doc comment（per §3.3 改動）
- 補 main_health_emitters.rs:174-205 module note 替換文 draft（per §3.4 改動 3）
- 補 singleton-registry.md §2.1.3 + §2.1.4 → caller_chain 欄位更新（從「Wave A handle 未接」改「Sprint 5+ §4.2.1 production wire-up 完成」）+ migration_plan 標 DONE
- dispatch packet draft：點清 4 處 caller（startup/private_ws.rs:240 + bybit_private_ws.rs:1184/1211 + main_health_emitters.rs:212/227 + main.rs:1440 + main_instruments.rs:40 + SharedClientsBundle extract）

## Phase 2 — E1 IMPL（4-6 hr）

依改動順序：

1. `bybit_private_ws.rs:544-567` BybitPrivateWs::new() signature + impl
2. `bybit_private_ws.rs:1184-1190` + `1211-1217` 2 inline test caller update
3. `startup/private_ws.rs:54-60` PrivateWsBindings struct 加 2 field
4. `startup/private_ws.rs:82` 後加 2 個 Arc 構造 + `:234-267` supervisor task closure caller update
5. `startup/private_ws.rs:273-278` PrivateWsBindings return value 加 2 field
6. `main_instruments.rs:40-45` SharedClientsBundle 加 2 field
7. `main_instruments.rs:70-81` 後加 shared_ws_dropout + shared_ws_rtt extract
8. `main_instruments.rs:187` SharedClientsBundle return value 加 2 field
9. `main_health_emitters.rs:212-221` build_real_api_latency_probe signature
10. `main_health_emitters.rs:227-246` build_api_latency_emitter signature + match arm
11. `main_health_emitters.rs:362-373` spawn_metric_emitter_scheduler signature
12. `main_health_emitters.rs:412` build_api_latency_emitter call site 加 2 arg
13. `main_health_emitters.rs:174-205` module note 改 production wire-up note（per §3.4 改動 3）
14. `main.rs:1440-1448` spawn_metric_emitter_scheduler caller 加 2 arg
15. `main.rs:571-581` SharedClientsBundle destructure 加 2 field
16. cargo check 通過後 `cargo test --workspace --release` 全 PASS

per `feedback_impl_done_adversarial_review` 2026-05-09：本 IMPL 是「共用 helper 邊界擴大」（BybitPrivateWs::new() signature 動），E1 IMPL DONE 後**強制走 A3+E2 並行核驗**。

## Phase 3a — E2 + A3 並行 review（1 hr E2 + 0.5 hr A3）

per `feedback_impl_done_adversarial_review`：

**E2 review 重點 3 條（per PA 角色契約）**：

1. **跨 await 邊界 Arc clone 是否 leak**：supervisor task closure move 後 Arc::clone in loop 每 attempt 新 clone，Arc::strong_count 是否 leak（預期 supervisor task lifetime 內穩定 2-3，非 attempt 累加）
2. **fallback path 行為一致性**：build_api_latency_emitter match arm 三種組合（all Some / partial Some / all None）行為對齊 spec §3.4；partial Some 不應走 silent placeholder（per dispatch §禁忌「不假陽性」對齊）
3. **inline test fixture 改動是否破測試覆蓋範圍**：bybit_private_ws.rs:1184/1211 兩 test 是 HMAC auth message structure 測試；加 Arc 參數後不影響 test assertion（auth 邏輯純看 api_key/secret/expires 三項）

**A3 audit 重點**（per `feedback_pushback` + multi-role adversarial review）：

- WsDropoutCounter / WsRttHistogram cap（256 / 64）跨 reconnect attempt 共享是否會 overflow（per WsDropoutCounter::record_dropout 60s rolling window cap=256，正常 < 1 dropout/min 永不滿；極端 disconnect 風暴下行為驗）
- API breaking change 是否暴露 public API（BybitPrivateWs::new() 是 `pub fn`；外部 crate 若 import 必跟改 — grep `BybitPrivateWs::new` 全 repo + workspace 確認 0 external caller）

## Phase 3b — E4 regression（0.5 hr）

- `cargo test --workspace --release` 全 PASS（3961+ baseline 不退）
- `cargo build --release` 0 warning
- pytest 全 PASS（6042+ baseline 不退；Python 端不涉本 IMPL）
- strings binary | grep 確認 expose accessor 仍 hit ≥ 4

## Phase 3c — QA AC-1b real PG empirical（30-60 min sample wait + verify）

per Sprint 4+ Phase 3c SOP：

- ssh trade-core 部署 + restart_all.sh --rebuild
- 60s 後 psql query AC-3 SQL（per §4 AC-3）
- 30 min 後二次 query 確認 ws_rtt_p50 非全 0
- 24 hr 持續觀測 V106 row（per AC-3 ≥ 1000 row + 中位數 50-200ms）

## Phase 3d — TW Acceptance Report（0.5 hr）

per Sprint 4+ Phase 3d SOP：

- AC-1 ~ AC-5 逐條 PASS 確認
- 揭露任何 production runtime issue（API breaking 對 external caller 影響、Arc strong_count 觀測值）

## Phase 3e — PM Sign-off（0.25 hr）

- Verdict: PASS / PASS WITH CARRY-OVER / FAIL
- §6.3 singleton-registry.md migration_plan 標 DONE
- 後續 §4.2 cascade 4 items 中 §4.2.1 標 closure；§4.2.2-4 繼續

---

# §6 Risk Assessment

## §6.1 改動風險評級 — 中

per PA profile §技術評估框架：

- **改邏輯但有完整測試覆蓋的模塊**：BybitPrivateWs::new() 是中等改動；inline test + integration test 雙覆蓋
- **API breaking**：BybitPrivateWs::new() 是 `pub fn`；但 grep 全 repo + workspace 0 external caller（內部 4 處全列入 §3.2）
- **跨 await 邊界**：supervisor task closure Arc clone 是常見 pattern；既有 startup/private_ws.rs:113-181 多處 Arc 跨 closure move 模式對齊

## §6.2 副作用識別清單

1. **其他模塊是否 import BybitPrivateWs**：grep 確認 — startup/private_ws.rs:78 + tests/api_latency_probe_real_impl.rs:35（type import 不涉 new() caller）；公共範圍可控
2. **mock 測試 fragility**：tests/api_latency_probe_real_impl.rs 走 `WsDropoutCounter::new()` 直接 fixture，0 走 BybitPrivateWs supervisor；signature 改不影響
3. **asyncio/threading 混用邊界**：BybitPrivateWs::run() 是 async fn；supervisor task 是 `tokio::spawn`；Arc 跨 closure move 是 Send + Sync trait 對齊 std::sync::Mutex 內部用法；不涉新 threading 模型
4. **API response schema**：本 IMPL 0 改 IPC schema / 0 改 PG schema / 0 改 V### migration；M3 emit chain V106 既有 row name 不變（仍 `api_latency__ws_rtt_p50_ms` 等）
5. **PyO3 IPC schema**：0 影響；本 IMPL 純 Rust 內部，Python 端不感知

## §6.3 跨平台兼容性

per `feedback_cross_platform`：

- `Arc<WsDropoutCounter>` / `Arc<WsRttHistogram>` 純 std::sync::Mutex 包；Mac + Linux 行為一致
- 0 platform-specific cfg
- 0 hard-coded path

---

# §7 PA 派發 readiness

## §7.1 dispatch packet draft（PA → E1）

per `feedback_impl_done_adversarial_review` 強制 A3+E2 並行核驗：

- E1 IMPL phase（4-6 hr）= 16 step 順序執行（per §5 Phase 2）
- IMPL DONE 後**禁直接派 E4** — 必先派 E2 + A3 並行 review（per memory 2026-05-09 lesson）
- 所有改動走中文注釋（per `feedback_chinese_only_comments` 2026-05-05）

## §7.2 派發前必驗

1. **grep verify**：

```bash
# 確認 BybitPrivateWs::new 4 處 caller
grep -rn 'BybitPrivateWs::new' /Users/ncyu/Projects/TradeBot/srv/rust/ | grep -v target | wc -l
# 預期：5（startup/private_ws.rs:240 + bybit_private_ws.rs:1184 + 1211 + 2 doc example）

# 確認 main_health_emitters fresh Arc placeholder
grep -n 'Arc::new(WsDropoutCounter::new())\|Arc::new(WsRttHistogram::new())' \
  /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/main_health_emitters.rs
# 預期 IMPL DONE 後：≤ 4 hit（fallback 路徑 + spec §3.4 改動 2 fallback match arm）
```

2. **dispatch packet §新 singleton 預登記**：本 IMPL 不引新 singleton（既有 WsDropoutCounter + WsRttHistogram 改 caller-injection ownership 模式；type 自身不變），不需登記
3. **caller_chain 更新**：singleton-registry.md §2.1.3 + §2.1.4 caller_chain 由「Wave A 已實裝但 main_health_emitters.rs Wave B placeholder 未接」改「Sprint 5+ §4.2.1 production wire-up；supervisor + emitter probe 共享 caller-injected Arc」

## §7.3 dispatch packet 完整檢核

- [ ] Scope 16 step 順序明示 + 每 step file:line
- [ ] 4 處 caller impact 全列入
- [ ] 5 AC verify command 可執行
- [ ] §禁忌：不改 既有 bybit_private_ws.rs 業務邏輯（不改 run() main loop / connect_async / pong 接 RTT 邏輯）；不改 ADR；不 commit
- [ ] §硬邊界：0 觸 live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved；0 改 IPC schema
- [ ] §強制：IMPL DONE 後 A3+E2 並行 review

---

# §8 結論 — Sprint 5+ §4.2.1 PA design 完成

| 項 | 狀態 |
|---|---|
| 既有 supervisor 架構分析 | DONE — §1 + §3.2 + §3.3 |
| Option A vs B 對照 | DONE — §2.1 |
| Option A 改造 signature design | DONE — §3.1 + §3.2 + §3.3 + §3.4 + §3.5 |
| 5 AC | DONE — §4 |
| Sprint 5+ IMPL phase split | DONE — §5（Phase 1 + 2 + 3a/b/c/d/e） |
| Risk assessment | DONE — §6 |
| PA dispatch readiness | DONE — §7 |

**verdict: PA design done → E1 IMPL ready**（per Sprint 5+ §4.2 cascade IMPL dispatch readiness OPEN）

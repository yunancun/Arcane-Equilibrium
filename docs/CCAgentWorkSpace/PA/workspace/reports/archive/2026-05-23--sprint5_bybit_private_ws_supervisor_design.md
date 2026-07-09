---
report: Sprint 5+ §4.2.1 BybitPrivateWs supervisor signature 改造 PA design
date: 2026-05-23
author: PA (Project Architect)
phase: Sprint 5+ cascade IMPL §4.2.1 — PA Phase 1 design
status: DESIGN-DONE-DISPATCH-READY
parent:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md §4.2.1
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_acceptance.md（Wave B E2 round 1 MEDIUM-2 finding）
  - srv/docs/architecture/singleton-registry.md §2.1.3.a / §2.1.4.a / §6.3
spec: srv/docs/execution_plan/2026-05-23--sprint5_bybit_private_ws_supervisor_signature_design.md
---

# Sprint 5+ §4.2.1 — BybitPrivateWs supervisor signature 改造 PA Design Report

## §1 BybitPrivateWs supervisor 現架構分析

### §1.1 既有 supervisor call chain

```
main.rs:576 init_shared_clients_and_instruments(&cancel, &live_bindings, &demo_bindings)
                    ↓
        live_bindings/demo_bindings 由 build_exchange_pipeline 構造（startup/mod.rs:540）
                    ↓
        build_exchange_pipeline:876 spawn_private_ws_supervisor(api_key, api_secret, env, label, cancel)
                    ↓
        startup/private_ws.rs:71 spawn_private_ws_supervisor returns (PrivateWsBindings, Vec<JoinHandle>)
                    ↓
        startup/private_ws.rs:234-267 RE-2 supervisor task spawn
                    ↓
            loop {
                BybitPrivateWs::new(...)         ← line 240 每次 attempt 內部新 Arc
                priv_ws.run().await
                supervisor_attempt++ + backoff
            }
                    ↓
        ExchangePipelineBindings.ws_bindings: PrivateWsBindings（bal/pnl/event_rx 三 Arc，0 含 instrumentation）
                    ↓
        main_instruments.rs:70 SharedClientsBundle.shared_client = live > demo 優先抽 Arc<BybitRestClient>
                    ↓                                           （0 含 ws 端 Arc）
        main.rs:1440 spawn_metric_emitter_scheduler(&db_pool, &shared_client, ...)
                    ↓
        main_health_emitters.rs:212 build_real_api_latency_probe(shared_client)
                    ↓
            let ws_dropout = Arc::new(WsDropoutCounter::new())   ← line 218 fresh 0-state
            let ws_rtt = Arc::new(WsRttHistogram::new())          ← line 219 fresh 0-state
                    ↓
        RealApiLatencySourceProbe.{ws_dropout, ws_rtt}            ← 永遠不會被 production 觀測
                    ↓
        emitter.observe_classified() → V106 row api_latency__ws_*  ← 全 0 染色（disconnect）
```

### §1.2 Wave A 已實裝 handle accessor（但 Wave B 未呼）

per `rust/openclaw_engine/src/bybit_private_ws.rs:577-585`：

```rust
/// PA-DRIFT-4 工作項 (3)：暴露 dropout counter Arc（probe 注入）。
pub fn dropout_counter_handle(&self) -> Arc<WsDropoutCounter> {
    Arc::clone(&self.dropout_counter)
}

/// PA-DRIFT-4 工作項 (3)：暴露 RTT histogram Arc（probe 注入）。
pub fn rtt_histogram_handle(&self) -> Arc<WsRttHistogram> {
    Arc::clone(&self.rtt_histogram)
}
```

### §1.3 為什麼 Wave A 留半實裝 — RCA

per `main_health_emitters.rs:163-172`：

1. **RE-2 supervisor restart loop 每次重建 BybitPrivateWs**：line 240-246 supervisor task closure 每次 attempt 都 `BybitPrivateWs::new()`；內部 own Arc 模式下每次 attempt 一個全新 Arc instance；main.rs 外部即使透過 `dropout_counter_handle()` 拿到也只是某一瞬間 attempt 的 Arc，下次 attempt 它就被換掉
2. **supervisor task detached + handle 不含 instrumentation**：`spawn_private_ws_supervisor` 返 `JoinHandle<()>`，不返 BybitPrivateWs instance handle；main.rs 端永遠拿不到穩定 reference
3. **Wave B 不擴 signature scope**：per dispatch §禁忌「不改既有 bybit_private_ws 業務邏輯」；Wave B 走 placeholder fallback 是合理的（不破 既有 caller API）；Sprint 5+ 才開 signature scope

### §1.4 既有 SharedClientsBundle pattern（main_instruments.rs）

關鍵發現：項目**已存在**「從 binding extract shared Arc」pattern，本 IMPL 走同模式自然延伸：

```rust
// main_instruments.rs:70-81 — 既有 shared Arc 抽取 pattern
let shared_client: Option<Arc<BybitRestClient>> = live_bindings
    .as_ref()
    .map(|b| Arc::clone(&b.rest_client))
    .or_else(|| demo_bindings.as_ref().map(|b| Arc::clone(&b.rest_client)));
```

→ ws_dropout / ws_rtt 走同模式（live > demo 優先 + Option<Arc> 包），主架構 design 完全對齊既有 pattern。

---

## §2 Option A signature 改造 design（before/after + caller impact）

### §2.1 Option A vs Option B 對照（核心理由）

| 維度 | Option A | Option B |
|---|---|---|
| type-level enforcement | ✅ compile 強制 | ❌ silent forget |
| race window | 0 | 存在（install 前 default Arc 接收後 swap 丟失） |
| 既有 caller impact | 4 處（可控） | 0（但回半實裝陷阱風險面大） |
| supervisor reconnect 一致 | ✅ 跨 attempt 同 Arc | ❌ 每 attempt 新 default Arc |

**結論**：Option A — 對齊 E2 Wave B round 1 MEDIUM-2 推薦 + PA 確認，type-level enforcement 完勝。

### §2.2 BybitPrivateWs::new() signature

```rust
// before（bybit_private_ws.rs:544-567）
pub fn new(
    api_key: String,
    api_secret: String,
    env: BybitEnvironment,
    cancel: CancellationToken,
    event_tx: mpsc::Sender<PrivateWsEvent>,
) -> Self {
    Self {
        ...,
        dropout_counter: Arc::new(WsDropoutCounter::new()),  // 內部 own
        rtt_histogram: Arc::new(WsRttHistogram::new()),       // 內部 own
    }
}

// after — caller external Arc 注入
pub fn new(
    api_key: String,
    api_secret: String,
    env: BybitEnvironment,
    cancel: CancellationToken,
    event_tx: mpsc::Sender<PrivateWsEvent>,
    dropout_counter: Arc<WsDropoutCounter>,
    rtt_histogram: Arc<WsRttHistogram>,
) -> Self {
    Self {
        ...,
        dropout_counter,  // caller injection
        rtt_histogram,    // caller injection
    }
}
```

### §2.3 4 處 Caller impact

| Caller | 位置 | 改動類型 | 備註 |
|---|---|---|---|
| 1. supervisor task | `startup/private_ws.rs:234-267` | Arc 構造 + Arc::clone 跨 attempt 注入 | spawn 前構造 + closure move |
| 2. inline test #1 | `bybit_private_ws.rs:1184-1190` | 加 2 個 `Arc::new(...)` fixture 參數 | test_auth_message_structure |
| 3. inline test #2 | `bybit_private_ws.rs:1211-1217` | 加 2 個 `Arc::new(...)` fixture 參數 | test_auth_signature_deterministic |
| 4. integration test crate | `tests/api_latency_probe_real_impl.rs` | **0 改動** | 純 fixture 不走 BybitPrivateWs supervisor |

### §2.4 上層橋接（PrivateWsBindings + SharedClientsBundle）

```rust
// startup/private_ws.rs:54 PrivateWsBindings 加 2 field
pub(crate) struct PrivateWsBindings {
    pub bybit_balance: ...,
    pub api_pnl: ...,
    pub exchange_event_rx: ...,
    pub dropout_counter: Arc<WsDropoutCounter>,   // NEW
    pub rtt_histogram: Arc<WsRttHistogram>,         // NEW
}

// main_instruments.rs:40 SharedClientsBundle 加 2 field（live > demo 抽取）
pub(crate) struct SharedClientsBundle {
    ...
    pub shared_ws_dropout: Option<Arc<WsDropoutCounter>>,  // NEW
    pub shared_ws_rtt: Option<Arc<WsRttHistogram>>,        // NEW
}

// main_health_emitters.rs:362 spawn_metric_emitter_scheduler signature 加 2 param
pub(crate) fn spawn_metric_emitter_scheduler(
    db_pool: &Arc<DbPool>,
    pool_max_conn: u32,
    data_dir_mount: &str,
    shared_client: &Option<Arc<BybitRestClient>>,
    shared_ws_dropout: &Option<Arc<WsDropoutCounter>>,  // NEW
    shared_ws_rtt: &Option<Arc<WsRttHistogram>>,         // NEW
    engine_mode_str: &'static str,
    cancel: &CancellationToken,
)
```

---

## §3 5 AC + Sprint 5+ IMPL phase split

### §3.1 5 AC（per spec §4）

| AC | 內容 | 驗證方法 |
|---|---|---|
| AC-1 | supervisor 持有外部 Arc reference（single instance across reconnects） | grep `BybitPrivateWs::new` caller + Arc::strong_count trace |
| AC-2 | main_health_emitters.rs 真實 inject Arc handle（not fresh new） | grep `Arc::new(WsDropoutCounter::new())` ≤ 1 hit (fallback only) |
| AC-3 | 30 天 V106 row ws_rtt/ws_dropout 真實 production WS metric | psql query `api_latency__ws_rtt_*` 中位數 50-200ms |
| AC-4 | cargo test 回歸不退（baseline 3961+） | `cargo test --workspace --release` 全 PASS |
| AC-5 | production binary 0 spike feature 滲透 | strings binary + engine PID startup log 含 wire-up 訊息 |

### §3.2 IMPL phase split

| Phase | 內容 | 估時 | Owner |
|---|---|---|---|
| Phase 1 | PA refine（spec doc comment + dispatch packet draft） | 0.5 hr | PA |
| Phase 2 | E1 IMPL（16 step 順序執行） | 4-6 hr | E1 |
| Phase 3a | E2 + A3 並行 review（per feedback_impl_done_adversarial_review） | 1 hr E2 + 0.5 hr A3 | E2 + A3 |
| Phase 3b | E4 regression | 0.5 hr | E4 |
| Phase 3c | QA AC-1b real PG empirical（30-60 min sample wait） | 30-60 min wait + 0.5 hr verify | QA |
| Phase 3d | TW Acceptance Report | 0.5 hr | TW |
| Phase 3e | PM Sign-off | 0.25 hr | PM |

**總工時：4-6 hr E1 IMPL + 1.75 hr review chain + 30-60 min sample wait ≈ 6.25-8.25 hr 完整鏈**

對齊 Sprint 4+ PM §4.2.1 「4-6 hr E1 + 1 hr E2」估算（PA refine + A3 + Phase 3b/c/d/e 屬 PM 估算外的 review chain，per `feedback_impl_done_adversarial_review` 強制 SOP）。

---

## §4 Sprint 5+ §4.2.1 dispatch readiness verdict

### §4.1 verdict: PA DESIGN DONE — E1 IMPL READY

**結論**：Sprint 5+ §4.2.1 PA Phase 1 design 已完成；E1 IMPL phase 派發 ready。

**證據**：

1. spec doc 已寫（`docs/execution_plan/2026-05-23--sprint5_bybit_private_ws_supervisor_signature_design.md`）含 8 §（context + design + signature + AC + phase split + risk + dispatch readiness + verdict）
2. 既有 supervisor call chain 完整 grep + read confirmed；4 處 caller 全列入 IMPL 順序
3. 既有 SharedClientsBundle pattern 識別為對齊路徑；新 wire-up 走既有架構自然延伸
4. 5 AC 全可驗證（grep + cargo test + psql query + strings binary 4 種 verify method）
5. Option A type-level enforcement 對齊 E2 Wave B round 1 MEDIUM-2 推薦 + PA 確認
6. risk assessment: 中度改動（API breaking 但 0 external caller + inline test 全列入 + 整合 test 不破）

### §4.2 派發前 PA 必補（Phase 1 收尾）

- [ ] singleton-registry.md §2.1.3 + §2.1.4 caller_chain 預備更新文（IMPL DONE 後同步更新）
- [ ] dispatch packet draft 寫入 16 step 順序 + 4 處 caller + 5 AC + 強制 A3+E2 並行 review note
- [ ] grep verify 命令 + 預期值 inline 寫入 dispatch packet

### §4.3 強制 A3+E2 並行 review SOP（per feedback_impl_done_adversarial_review 2026-05-09）

本 IMPL 屬「共用 helper 邊界擴大」（BybitPrivateWs::new() signature 動 + PrivateWsBindings field 加 + SharedClientsBundle field 加）；per memory lesson E1 IMPL DONE 後**禁直接派 E4 regression** — 必先派 A3 audit + E2 review 並行；雙方獨立 catch failure mode（per W-AUDIT-7c governance-tab.js SyntaxError catch 三方獨立救 prod 案例）。

### §4.4 Sprint 5+ §4.2 cascade 連動

per Sprint 4+ PM Phase 3e §4.2 4 items：

| # | Item | Status |
|---|---|---|
| 1 | BybitPrivateWs supervisor signature 改造（**本 task**） | PA design DONE → E1 IMPL READY |
| 2 | PortfolioStateCache update task wire-up（接 PaperState SSOT） | Sprint 5+ 後續派發 |
| 3 | archive 4 Python singleton re-ingest | Sprint 5+ P2 LOW |
| 4 | dispatch packet 模板補「新 singleton 預登記」section | Sprint 5+ P2 |

本 task 完成後 §4.2.1 closure；§4.2.2-4 可獨立並行派發。

---

## §5 Lessons Learned（本 PA design 期間揭露）

### §5.1 既有 SharedClientsBundle pattern 自然延伸的價值

本 design 過程中發現項目**已存在**「從 binding extract shared Arc」既有 pattern（main_instruments.rs:70-81 shared_client + shared_account_manager）；ws_dropout / ws_rtt 走同模式 = 既有架構自然延伸。對 reviewer + E1 IMPL 認知負擔極低。

**lesson**：PA design 前必先 grep 既有 pattern；找到對齊路徑 = IMPL 風險最小化 + reviewer 認知最低。

### §5.2 RE-2 supervisor restart loop 與 caller injection pattern 衝突

per `bybit_private_ws.rs:564-565` + `startup/private_ws.rs:240-246` — RE-2 restart loop 每次重建 BybitPrivateWs 是 production 健壯性需求（不能 panic kill）；但**內部 own Arc** 模式下 supervisor + emitter probe 永遠拿不到同 Arc reference。caller injection pattern（Option A）是這場 design tension 的唯一 type-safe 解。

**lesson**：「supervisor restart loop」+「health emit chain」共生時，instrumentation Arc 必走 caller-owned + per-attempt clone pattern；不能走 supervisor-owned 內部 Arc pattern。

### §5.3 半實裝陷阱誠實揭露對 Sprint 5+ scope 拍板的價值

per main_health_emitters.rs:174-205 + singleton-registry.md §2.1.3.a / §2.1.4.a — Wave B round 2 MEDIUM-2 fix 誠實揭露「placeholder fresh 0-state 不等同 production wire-up」；caller_chain SSOT 反映半實裝狀態；30 天 V106 row 全 0 是 disconnect 副作用而非健康觀測。本 Sprint 5+ §4.2.1 scope 拍板的精準度完全依賴此誠實揭露。

**lesson**：半實裝寫 doc 揭露 + caller_chain 反映 + dispatch packet 預埋 carry-over 三位一體，比「掩飾為 OK band 不誤升」健康得多；後續 Sprint scope 拍板才能基於真實 production state。

---

# §6 Sign-off

```
Phase 1 PA design：本 report + spec doc
  - spec: srv/docs/execution_plan/2026-05-23--sprint5_bybit_private_ws_supervisor_signature_design.md
  - PA design report: 本 file
Phase 2 E1 IMPL：dispatch ready（per §4.2 PA Phase 1 收尾完成後）
Phase 3a A3 + E2 並行 review：dispatch ready（per §4.3 SOP）
Phase 3b E4 regression：dispatch ready
Phase 3c QA AC-1b：production deploy + 30 min sample wait + psql verify
Phase 3d TW Acceptance Report
Phase 3e PM Sign-off
```

**PA Phase 1 verdict: DESIGN-DONE-DISPATCH-READY**

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_bybit_private_ws_supervisor_design.md

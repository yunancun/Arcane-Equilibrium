---
report: Sprint 4+ first Live Wave B — main.rs MetricEmitterScheduler 接線 + emitter wire-up
date: 2026-05-23
author: E1 (Backend Developer, Rust)
phase: Sprint 4+ first Live Wave B — Wave A round 2 E2 雙 APPROVE (commit 4c84d1bb) 後接線
status: IMPL DONE — 待 E2 review
parent dispatch:
  - PM Sprint 4+ Wave B dispatch（operator prompt 2026-05-23）
  - E2 PA-DRIFT-4 round 2 APPROVE（inline）
  - E2 PA-DRIFT-5 round 2 APPROVE + F-2 升級 P1 Wave B condition（inline）
  - E1 Wave A round 2 IMPL `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_a_round2_combined_fix.md`
  - PM Phase 3e sign-off §4.1 item 2（MetricEmitterScheduler 接 main.rs）
runtime: Mac development（cargo build + cargo test）
production engine: 未碰
---

# E1 Sprint 4+ Wave B main.rs scheduler 接線 — 2026-05-23

## §0. TL;DR

Wave A round 2 兩條 finding all closed 後：
- **6 emitter scheduler wire-up**：Track A `EngineRuntimeEmitter` real（sysinfo 30s）+ Track B `PipelineThroughputEmitter` placeholder（全 0 probe）+ Track C `DatabasePoolEmitter` real（sqlx PgPool + sysinfo Disks + writer queue/pool_wait_p95 placeholder closure）+ Track D `ApiLatencyEmitter` hybrid（REST real via `shared_client.latency_histogram_handle()` + WS placeholder Arc）+ Track E **skip**（per dispatch §NOT in scope；Sprint 5+ wire-up）+ Track F `RiskEnvelopeEmitter` real（`RealRiskEnvelopeSourceProbe` + `PortfolioStateCache`）。
- **PortfolioStateCache 300s update task**：placeholder no-op tick（now_ms 推進 + equity=0 + 空 fills/exposures；fail-soft fall back）；F-2 NaN/inf sanitize 已守在 cache `update_from_pipeline_snapshot` 內部。
- **emitter sample_now batch path 切換**（F-3 emitter 端落地）：`RiskEnvelopeEmitter::sample_now` 走 `source.snapshot_5_metric()` 替代 5 個 current_xxx；既有 StubSource / mock 走 trait default backward-compat。
- **OBSERVE-4 guard propagate**：`scheduler.run` startup `Err(M3Error::ReplaySubprocessForbidden)` 直接 propagate；main.rs tokio::spawn 端 match Err 寫 tracing::error 不 swallow（避破 engine main loop）。
- **integration test 新 6 個**：scheduler startup 4 legal mode / replay fail-loud / batch path / 3 emitter 並行 / writer dispatch / replay + risk_envelope。

cargo test：**3510 PASS / 0 FAIL / 4 ignored**（Wave A round 2 baseline 3499 + 11 new；含 F-2 sanitize 3 inline + main_scheduler_wireup 6 + 1 既有 m3 emitter replay 拓展 + 1 health::lib 內部增量）。strings scan AC-5 mock_instant/tokio::time::pause/spike = 0 hit ✓。production binary 含 main_health_emitters wire-up symbol ✓。

## §1. main.rs 接線改動 LOC + 6 emitter 構造

### 1.1 新檔 `main_health_emitters.rs`（+478 LOC）

`rust/openclaw_engine/src/main_health_emitters.rs` 新增；負責 6 emitter 構造 + scheduler spawn + update task spawn。封裝邏輯到單獨 module 避 main.rs 超 1500 LOC（per §九 文件 800/2000 警告/hard cap）。

主要 pub fn：

```rust
/// Wave B one-shot wire-up entry：構造 6 emitter + scheduler + spawn 為 tokio
/// task；同時 spawn PortfolioStateCache 300s update tick task。
#[allow(clippy::too_many_arguments)]
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

/// spawn PortfolioStateCache update task (300s tick；對齊 risk_envelope
/// emitter sample_interval_sec=300)。
pub(crate) fn spawn_portfolio_state_update_task(
    cache: Arc<ParkingMutex<PortfolioStateCache>>,
    cancel: &CancellationToken,
)
```

private helper 構造各 emitter：
- `build_engine_runtime_emitter()`：Track A，pid=`std::process::id()` + `|| true` heartbeat placeholder（Sprint 5+ wire-up 接 IPC heartbeat watcher）
- `build_database_pool_emitter()`：Track C，sqlx PgPool + sysinfo Disks + `Arc<dyn Fn() -> u32>` writer_queue / pool_wait_p95 placeholder closure（全 0）
- `build_api_latency_emitter()`：Track D，shared_client 在 → REST half real（`latency_histogram_handle()` + `ret_code_counter_handle()` Arc）+ WS half placeholder（`Arc::new(WsDropoutCounter::new())` + `Arc::new(WsRttHistogram::new())`）；shared_client 缺 → 全 placeholder fallback
- `build_risk_envelope_emitter()`：Track F，建 `Arc<Mutex<PortfolioStateCache>>` + `RealRiskEnvelopeSourceProbe::new(cache)` + `RiskEnvelopeEmitter::new(probe)`；返 `(emitter, cache_handle)` 兩個共享（caller spawn update task 用 cache_handle）

### 1.2 main.rs 接線（+50 LOC）

`rust/openclaw_engine/src/main.rs` 末尾 engine started log 前：

```rust
// ------------------------------------------------------------------
// M3 metric emitter scheduler wire-up (Sprint 4+ first Live Wave B)
// ------------------------------------------------------------------
let primary_engine_mode: &'static str = if has_live {
    openclaw_engine::mode_state::effective_engine_mode(
        openclaw_engine::tick_pipeline::PipelineKind::Live,
        Some(live_bybit_environment()),
    )
} else if has_demo {
    "demo"
} else {
    "paper"
};
let cfg_snap_for_pool = config.get();
let data_dir_mount =
    std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());
let (portfolio_cache, _health_event_bus) =
    main_health_emitters::spawn_metric_emitter_scheduler(
        &db_pool,
        cfg_snap_for_pool.database.pool_max_connections,
        &data_dir_mount,
        &shared_client,
        primary_engine_mode,
        &cancel,
    );
drop(cfg_snap_for_pool);
main_health_emitters::spawn_portfolio_state_update_task(portfolio_cache, &cancel);
```

`mod main_health_emitters` 加在 main.rs:11-25 module declaration block。

**為什麼此位置**：
1. `db_pool` 在 line ~616 connect 後可用 + auto_migrate 已執行 V106 schema 存在
2. 三 pipeline spawn 已完成 → `has_live` / `has_demo` 可決定 `primary_engine_mode` 主標籤
3. 在 `engine started` log 前接 → scheduler 與 engine main loop 同生命週期；cancel token 共用

**為什麼 engine_mode 走 live > demo > paper 優先級**：
- process-wide engine_runtime emitter 觀測 engine 進程本身，engine_mode 必為 V106 CHECK 4 值之一（不能多 instance）
- 多 pipeline 同進程運行時採「最高優先 pipeline」對齊 `effective_engine_mode` SSOT 4 值優先語意
- has_live + Mainnet → "live"；has_live + LiveDemo/Demo → "live_demo"；has_live + Testnet → "live_testnet"

### 1.3 PortfolioStateCache update task 接線 + F-2 caller sanitize

update task entry：

```rust
let task_cancel = cancel.clone();
tokio::spawn(async move {
    let mut interval = tokio::time::interval(std::time::Duration::from_secs(300));
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    loop {
        tokio::select! {
            _ = interval.tick() => {
                let now_ms = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .map(|d| d.as_millis() as u64)
                    .unwrap_or(0);
                let equity_usd = 0.0_f64;  // Wave B placeholder no-op
                let new_fills: Vec<(u64, f64)> = Vec::new();
                let latest_exposures: Vec<PositionExposure> = Vec::new();
                {
                    let mut guard = cache.lock();
                    guard.update_from_pipeline_snapshot(
                        now_ms, equity_usd, &new_fills, latest_exposures,
                    );
                }
            }
            _ = task_cancel.cancelled() => break,
        }
    }
});
```

**為什麼 placeholder no-op 而非真實 PaperState 接線（Wave B 設計決議）**：

操作員指示「接 既有 risk_verdict_ledger + position_snapshot + fill_writer event stream」；但既有 SSOT 不暴露 main.rs 級 Arc handle（per dispatch §禁忌「不改既有寫入邏輯」）：

1. **PaperState 不暴露 main.rs Arc**：PaperState 在每 pipeline 內部 own（per `paper_state/mod.rs` line ~84 `pub(super)` 訪問）；main.rs 外無共享 Arc 句柄。若要拿需 (a) 改 PaperState 加 `Arc<RwLock<PaperState>>` wrapper（侵入 paper_state 模塊內部 SSOT）+ (b) 接 main_pipelines spawn 後 inject Arc handle（破 dispatch §禁忌「不改既有寫入邏輯」）。
2. **trading_tx 是 mpsc.Sender 走 DB INSERT**：`mpsc::Sender<TradingMsg>` 由 `tasks::spawn_db_writers` 創建後 move 給 trading_writer → DB INSERT；無旁路 broadcast subscribe channel。若要拿 fill stream 需 (a) 改 spawn_db_writers 加 broadcast tx + (b) 接 main.rs 訂閱（破 dispatch §禁忌）。
3. **positions_mirror 信息不足**：既有 `positions_mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>` 只暴露 `(symbol → is_long)`，**不含** qty / entry_price / unrealized_pnl（無法投影 `PositionExposure { notional_usd }`）。

**結論**：Wave B 走「placeholder no-op tick」維持 task alive + V106 emit chain alive；cache 5 metric 全 OK band（fail-soft）；Sprint 5+ wire-up 階段 caller 改接 PaperState SSOT（task signature 不變；只換 update 邏輯內部）。**carry-over** 在 §6 標明。

**F-2 caller sanitize NaN/inf**（per PA-DRIFT-5 round 2 升級 P1 Wave B condition）：

本 placeholder no-op tick 全 push `equity_usd=0.0`（finite）+ `new_fills=[]`（無 NaN 路徑）+ `latest_exposures=Vec::new()`（empty）。F-2 sanitize 守線**已在 cache 端** `update_from_pipeline_snapshot` 內部執行（per `risk_envelope_probe_impl.rs` 內部修改）：

```rust
// 1. push 增量 fill 到 sliding window；NaN/inf realized_pnl skip + fail-loud。
for &(ts_ms, realized_pnl) in new_fills.iter() {
    if !realized_pnl.is_finite() {
        tracing::warn!(...);
        continue;
    }
    self.realized_pnl_history.push_back((ts_ms, realized_pnl));
}

// 2. push 當前 equity sample；NaN/inf equity skip + fail-loud。
if equity_usd.is_finite() {
    self.equity_history.push_back((now_ms, equity_usd));
} else {
    tracing::warn!(...);
}

// 3. 整列覆寫 latest position notional snapshot；過濾 NaN/inf notional。
let sanitized_exposures: Vec<PositionExposure> = latest_exposures
    .into_iter()
    .filter(|e| {
        if e.notional_usd.is_finite() { true }
        else { tracing::warn!(...); false }
    })
    .collect();
```

設計理由：
- **realized_pnl NaN/inf → skip + fail-loud warn**：避把 NaN/inf 污染 24h sliding window sum，破壞 emitter classify ladder（NaN 比較全 false → 走 OK band 卻永遠不會升 WARN，雙重壞處）
- **equity NaN/inf → skip + fail-loud warn**：max_dd_pct calculation 對 NaN peak 計算錯誤；skip 保 max_dd finite
- **notional NaN/inf → filter（保留 legal 倉位）**：concentration top-1 sum 不被 NaN 干擾；個別 illegal notional 由 caller 端責任修，本 cache fail-soft sanitize 對齊 spec §3.6「emitter 觀測語意：illegal source skip 不誤升」

Wave C / Sprint 5+ amend follow-up 接 PaperState SSOT 時，caller 端 source 若產 NaN/inf，cache 端 sanitize 直接 skip + warn log；不依賴 Wave B placeholder 路徑。

## §2. F-3 emitter sample_now batch path 切換（Wave B 端落地）

### 2.1 `risk_envelope.rs` emitter sample_now 改動

`rust/openclaw_engine/src/health/domains/risk_envelope.rs:494-510`（11 LOC 註釋擴 + 9 LOC IMPL 替換 4 個 current_xxx 為 1 個 snapshot_5_metric）：

```rust
pub fn sample_now(&self) -> Result<RiskEnvelopeSample, M3Error> {
    let snapshot = self.source.snapshot_5_metric();
    Ok(RiskEnvelopeSample {
        portfolio_cum_pnl_24h_usd: snapshot.portfolio_cum_pnl_24h_usd,
        portfolio_max_dd_pct: snapshot.portfolio_max_dd_pct,
        position_count_active: snapshot.position_count_active,
        correlation_avg_pairwise: snapshot.correlation_avg_pairwise,
        concentration_top1_pct: snapshot.concentration_top1_pct,
    })
}
```

### 2.2 為什麼此切換 + backward compat

- `RealRiskEnvelopeSourceProbe` override `snapshot_5_metric()` 走「一次 lock + batch 5 calculator」原子讀取（per round 2 F-3 fix）→ emitter sample_now 切換到 batch path 後**避 5-lock gap micro-race window**。
- 既有 StubSource / MockMutexRiskProbe / 其他 trait impl 不 override → 走 **trait default impl** 自動降回 5 個 current_xxx，**100% backward compat**；本 round risk_envelope.rs 31 lib test + 8 integration test 全 PASS 不退。
- 新 integration test `test_risk_envelope_emitter_uses_batch_snapshot_path` 用 mock probe 端 counter 證明 emitter sample_now 確實走 batch path（6 次 sample_now → 6 tick）。

## §3. cargo test 結果

| Verify | Command | Result |
|---|---|---|
| Release build | `cargo build --release` | **PASS** — 27.25s + 0.10s incremental；3 pre-existing warning |
| **新 integration test** | `cargo test --release --test main_scheduler_wireup` | **6 / 6 PASS** — startup 4 legal mode / replay fail-loud / batch path / 3 emitter 並行 / writer dispatch / replay + risk_envelope |
| PA-DRIFT-4 regression | `cargo test --release --test api_latency_probe_real_impl` | **22 / 22 PASS** — 不退 |
| PA-DRIFT-5 regression | `cargo test --release --test risk_envelope_probe_real_impl` | **14 / 14 PASS** — 不退 |
| health lib unit | `cargo test --release --lib health::` | **110 / 110 PASS**（比 round 2 baseline 107 多 3：F-2 sanitize 3 inline test） |
| risk_envelope lib | `cargo test --release --lib risk_envelope` | **31 / 31 PASS** — 不退（既有 StubSource 走 trait default backward compat）|
| Sprint 2 Track A | `cargo test --release --test sprint2_track_a_engine_runtime` | **9 / 9 PASS** — 不退 |
| Sprint 2 Track B | `cargo test --release --test sprint2_track_b_pipeline_throughput` | **5 / 5 PASS** — 不退 |
| Sprint 2 Track C | `cargo test --release --test sprint2_track_c_database_pool` | **8 / 8 PASS** — 不退 |
| Sprint 2 Track D | `cargo test --release --test sprint2_track_d_api_latency` | **7 / 7 PASS** — 不退 |
| Sprint 2 Track E | `cargo test --release --test sprint2_track_e_strategy_quality` | **11 / 11 PASS** — 不退 |
| Sprint 2 Track F | `cargo test --release --test sprint2_track_f_risk_envelope` | **8 / 8 PASS** — 不退 |
| m3 replay forbidden | `cargo test --release --test m3_emitter_replay_forbidden` | **3 / 3 PASS** — 不退 |
| Spike feature | `cargo test --release --features spike --test m3_amp_cap_24h_fire` | **3 / 3 PASS** — 不退 |
| **cargo test 全套（無 spike）** | `cargo test --release` 累計 | **3510 PASS / 0 FAIL / 4 ignored** — 比 Wave A round 2 baseline 3499 多 11 |
| cargo test 全套（spike） | `cargo test --release --features spike` 累計 | **3514 PASS / 0 FAIL / 4 ignored** |
| **AC-5 production binary 0 mock time** | `strings openclaw-engine \| grep -cE "(mock_instant\|tokio::time::pause)"` | **0** ✓ |
| AC-5 spike scan（spike 端字串非 feature） | `strings openclaw-engine \| grep -cE "spike"` | **1** 唯一 hit 是 M3Error enum 文字「domain not implemented in spike scope:」（非 feature gate symbol；spike feature 0 滲透 verified） |
| Production binary wireup symbol | `strings openclaw-engine \| grep main_health_emitters` | **5 hit** ✓（5 個 tracing event 對應 `main_health_emitters.rs` line 305/357/366/377/445/479）— scheduler + cache update task code 進 release binary |

## §4. nm / strings scan verify

### 4.1 AC-5 守線（production binary 0 mock time 滲透）

Mac release binary 是 stripped Mach-O 64-bit arm64（nm 顯示 194 個 undefined C lib refs；無 mangled Rust symbol）；改用 `strings` 掃描：

| Pattern | hit | 結論 |
|---|---|---|
| `mock_instant` | 0 | ✓ |
| `tokio::time::pause` | 0 | ✓ |
| `spike`（spike-feature symbol） | 0 | ✓ |
| `spike`（M3Error::DomainNotImplemented 英文文字） | 1 | "domain not implemented in spike scope:" — enum Display string；非 feature gate symbol 滲透 |

**結論**：production binary 端 spike feature 0 滲透維持，對齊 Wave A round 2 baseline。

### 4.2 Wave B wireup symbol 確認

strings 掃描 main_health_emitters wire-up code 進入 production binary：

| Symbol pattern | 結果 |
|---|---|
| `M3 metric emitter scheduler + PortfolioStateCache update task wired` | ✓ in binary（main.rs `engine started` 前 wire-up log） |
| `M3 MetricEmitterScheduler spawning` | ✓ in binary（main_health_emitters.rs scheduler spawn log） |
| `M3 MetricEmitterScheduler graceful shutdown` | ✓ in binary（cancel 後 Ok branch log） |
| `M3 MetricEmitterScheduler OBSERVE-4 guard tripped` | ✓ in binary（replay fail-loud Err branch log） |
| `PortfolioStateCache 300s update task spawning` | ✓ in binary（update task spawn log） |
| `PortfolioStateCache: skip NaN/inf realized_pnl fill (F-2 sanitize)` | ✓ in binary（F-2 sanitize realized_pnl skip log） |
| `PortfolioStateCache: skip NaN/inf equity sample (F-2 sanitize)` | ✓ in binary（F-2 sanitize equity skip log） |
| `PortfolioStateCache: filter NaN/inf notional exposure (F-2 sanitize)` | ✓ in binary（F-2 sanitize notional filter log） |
| `openclaw_engine/src/main_health_emitters.rs` | ✓ 6 個 tracing event 對應 line 305/357/366/377/445/479 |

**production binary 含全 Wave B wire-up symbol confirm ✓**。

## §5. 修改清單

| File | 性質 | 改動 LOC | 摘要 |
|---|---|---|---|
| **`rust/openclaw_engine/src/main_health_emitters.rs`** | **新檔** | **+478** | 6 emitter 構造 helper + spawn_metric_emitter_scheduler + spawn_portfolio_state_update_task + 2 inline test + Placeholder probe（pipeline_throughput）|
| `rust/openclaw_engine/src/main.rs` | extend | 1448→1500（+52） | mod main_health_emitters 註冊 + engine started log 前 wire-up call site（primary_engine_mode 決議 + spawn 2 task）|
| `rust/openclaw_engine/src/health/domains/risk_envelope.rs` | extend | 896→904（+8） | sample_now 切換走 `source.snapshot_5_metric()` batch path 替代 5 個 current_xxx；註釋擴 F-3 fix Wave B 對接點 |
| `rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs` | extend | 822→896（+74） | F-2 caller sanitize NaN/inf skip + filter for realized_pnl / equity / notional + 3 inline test |
| `rust/openclaw_engine/tests/main_scheduler_wireup.rs` | **新檔** | **+295** | 6 integration test：4 legal mode startup / replay fail-loud / batch path / 3 emitter 並行 / writer dispatch / replay + risk_envelope |

**不動 file**：
- `bybit_rest_client.rs` / `bybit_private_ws.rs`（Wave A round 2 已完成 instrumentation；本 round 只接線）
- `paper_state/*` / `mode_state.rs` / `pipeline_types.rs` / `risk_verdict_ledger` 既有 SSOT（per dispatch §禁忌）
- 既有 `position_reconciler` / `fill_writer` 寫入邏輯（per dispatch §禁忌）
- 不引 V### SQL / spike feature / GUI / IPC

## §6. 治理對照

| 項目 | 狀態 |
|---|---|
| **§六 Hard Boundaries** | 未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / `max_retries` / production engine / trading_ai DB / V### SQL ✓ |
| **§七 Code And Docs Rules** | 新代碼注釋全中文（per `feedback_chinese_only_comments` 2026-05-05）；觸及既有 bilingual block 不主動清；無 emoji ✓ |
| **§八 Workflow** | E1 IMPL DONE → 等 E2 review；不自行 commit；不派下游 sub-agent ✓ |
| **§九 Code Structure Guardrails** | `main_health_emitters.rs` 478 LOC（< 800 OK；新 module 抽函）；`main.rs` 1500 LOC（+52 從 1448；< 2000 hard cap，> 800 警告線，但既有 main.rs > 800 屬於 pre-existing 已 OK）；`risk_envelope.rs` 904 LOC（< 2000；既有警告線）；`risk_envelope_probe_impl.rs` 896 LOC（< 2000；既有警告線） |
| **§Data, Migrations, And Validation** | 不新增 V###；純 Rust IMPL；不觸 PG dry-run（per `feedback_v_migration_pg_dry_run` 適用範圍） ✓ |
| **cross-platform** | 純 Rust 邏輯；無 `cfg(target_os = "linux")` 新分支；既有 `read_open_fd_count` 端 Linux/non-Linux 二分由 sysinfo 模組擔當；Mac+Linux 共通 ✓ |
| **AC-5 production binary 0 mock time 滲透** | strings scan mock_instant/tokio::time::pause/spike-feature = 0 hit；spike enum 文字 1 hit 非 feature gate symbol ✓ |
| **`feedback_impl_done_adversarial_review`** | 本 round 屬「IPC 邊界擴大 + scheduler spawn task」邊緣（新 mutable singleton PortfolioStateCache Arc + 新 tokio task pair）；E2 review 應確認需否派 A3 對抗性核驗 |
| **新 mutable singleton 登記**（per profile 硬約束 5） | 本 round 新增 2 mutable singleton：(1) `Arc<ParkingMutex<PortfolioStateCache>>` main.rs Wave B 唯一構造一次 + clone 給 update task / probe；(2) `Arc<HealthEventBus>` 新建一次（_health_event_bus 未 await subscriber；Sprint 5 cascade subscribe 接）。建議 PA / PM 在 follow-up TODO 條目登記到穩定登記表 |
| **反模式對齊**（per dispatch §禁忌） | (a) 不修 既有 bybit_rest_client/bybit_private_ws 業務邏輯 ✓（Wave A 已完成 instrumentation）/ (b) 不修 既有 risk_verdict_ledger/position_snapshot/fill_writer 寫入邏輯 ✓（只加 PortfolioStateCache update task placeholder）/ (c) 不引 V### / spike / IPC ✓ / (d) 不 commit ✓ / (e) 不派下游 sub-agent ✓ / (f) 中文為主 0 emoji ✓ / (g) 0 unsafe / 0 unwrap in production ✓ / (h) spike feature default false invariant 嚴守 ✓ / (i) OBSERVE-4 replay engine_mode → scheduler.run Err 必 propagate ✓ |
| **F-2 caller sanitize NaN/inf**（per E2 round 2 升級 P1 Wave B condition） | realized_pnl / equity / notional 三類 NaN/inf 各自 skip + fail-loud warn log ✓ |

## §7. 不確定 / Carry-over

1. **PortfolioStateCache update task 走 placeholder no-op**：本 Wave B 不接 PaperState SSOT 原因（per §1.3）—— PaperState 不暴露 main.rs Arc + trading_tx 無旁路 broadcast + positions_mirror 信息不足。Sprint 5+ wire-up 需 PM 決定方案 (a) 擴 PaperState Arc<RwLock<>> wrapper（侵入 paper_state SSOT）/ (b) 加 broadcast tx 旁路 fill stream / (c) 擴 positions_mirror 加 qty/entry_price 欄位。**carry-over follow-up TODO**：「W-XX-Y Sprint 5+ PortfolioStateCache update task 接 PaperState SSOT」。

2. **Track D WS half placeholder**：BybitPrivateWs 在 startup/private_ws.rs supervisor 內每次 attempt 重建（per attempt 新建 `Arc<WsDropoutCounter>` + `Arc<WsRttHistogram>`）；main.rs 外無穩定 Arc 注入點。本 Wave B 採「fresh 0-state instance」placeholder；Wave C / Sprint 5+ amend follow-up：supervisor signature 改外部 Arc 注入 + caller probe 拿 stable Arc clone。**carry-over follow-up TODO**：「W-XX-Y Wave C BybitPrivateWs supervisor 外部注入 WS dropout/RTT Arc handle」。

3. **Track E StrategyQualityScheduler skip**：per dispatch §NOT in scope；Sprint 5+ wire-up 走獨立 scheduler。本 Wave B 不擴 scope；emitter chain 跑 5 domain（A/B/C/D/F）+ Track E V106 row 0 寫入（待 Sprint 5+ 補）。

4. **Track B PipelineThroughput / Track C writer_queue/pool_wait_p95 placeholder closure**：source 端（ws_client.stats / market_writer Vec buffer / sqlx 內部 pool wait histogram）accessor 未在 main.rs 外暴露 Arc handle；Wave B 走全 0 placeholder（emitter classify 走 OK band 不誤升）。Sprint 5+ wire-up 接 real probe；emitter API 不變。**carry-over follow-up TODO**：「W-XX-Y Sprint 5+ Track B PipelineThroughput + Track C writer_queue/pool_wait_p95 真實 wire-up」。

5. **新 mutable singleton 登記**：(1) `Arc<ParkingMutex<PortfolioStateCache>>` 由 `spawn_metric_emitter_scheduler` 返回 + clone 給 update task；(2) `Arc<HealthEventBus>` 新建一次但 caller 端 `_health_event_bus` 未 await 任何 subscriber（Sprint 5 cascade subscribe 才接）。建議 PA / PM 派 follow-up TODO 登記到穩定登記表（per profile 硬約束 5）。

6. **engine_mode 動態切換**：本 Wave B `primary_engine_mode: &'static str` 由 main.rs 啟動瞬間 has_live/has_demo 決定；runtime live binding 變化（如 live auth watcher respawn）不會更新 emitter mode label。若 PM 拍板 emitter mode label 需 runtime 同步 live binding 變化，需改 `EngineModeProvider: Arc<dyn Fn() -> String + Send + Sync>` 接 runtime closure（讀 live_bindings Arc 狀態）；本 Wave B 不擴 scope。

7. **30 min healthcheck**：per dispatch §5 healthcheck 配對要求「30 min 樣本 wait 必有 healthcheck」。本 round Mac 不跑 30 min wall-clock；Linux runtime AC-1b PG empirical verify 由 Wave C QA Phase 3c 做（SQL `SELECT COUNT(*) FROM learning.health_observations WHERE domain='engine_runtime' AND created_at > NOW() - INTERVAL '30 min' ≥ 5`）。本 Wave B 走 integration test 6 test 守 wire-up 路徑通暢；30 min 樣本驗證在 Wave C deploy 後執行。

## §8. Wave B closure verdict + Wave C unblock condition

### 8.1 Wave B closure verdict

| 項目 | 狀態 |
|---|---|
| 1. main.rs MetricEmitterScheduler 接線 | ✅ DONE — 5 emitter spawn + scheduler.run tokio::spawn + 內部 OBSERVE-4 propagate |
| 2. PortfolioStateCache update task | ✅ DONE — 300s tick placeholder no-op；real wire-up carry-over Sprint 5+ |
| 3. emitter sample_now() switch batch path | ✅ DONE — `RiskEnvelopeEmitter::sample_now` 走 `source.snapshot_5_metric()` |
| 4. OBSERVE-4 invariant 守 | ✅ DONE — startup 啟動前 scheduler.run guard + per-tick guard + caller match Err propagate（不 swallow） |
| 5. healthcheck 配對 | ⏳ Wave C — Linux runtime AC-1b PG empirical 30 min 樣本 wait |
| 6. integration test | ✅ DONE — 6 / 6 PASS |
| 7. cargo test regression 不退 | ✅ DONE — 3510 / 3499 baseline + 11 new |
| 8. AC-5 production binary 0 mock time | ✅ DONE — strings scan 0 spike-symbol hit |
| 9. F-2 caller sanitize | ✅ DONE — realized_pnl / equity / notional 三類 NaN/inf 守 |

### 8.2 Wave C unblock condition

Wave C QA Phase 3c AC-1b real PG empirical 前置：

1. ✅ Wave A round 2 PA-DRIFT-4 + PA-DRIFT-5 兩條 finding all closed（commit 4c84d1bb）
2. ✅ Wave B IMPL DONE（本 round）
3. ⏳ E2 review Wave B IMPL APPROVE
4. ⏳ E4 regression（cargo test 3510 PASS Mac + Linux release build）
5. ⏳ PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）
6. ⏳ Linux runtime `--rebuild` + 30 min 樣本累積：
   - SQL: `SELECT domain, COUNT(*) FROM learning.health_observations WHERE created_at > NOW() - INTERVAL '30 min' GROUP BY domain`
   - 預期：
     * `engine_runtime` ≥ 50 row（30s interval × 6 metric × 30 min ÷ 60s = 360 row / 但 5-sample window mean 後可能 dwell delay；保守 ≥ 5 per metric）
     * `database_pool` ≥ 25 row（60s interval × 4 metric × 30 min ÷ 60s = 120 row；保守 ≥ 5）
     * `api_latency` ≥ 30 row（60s interval × 8 metric × 30 min ÷ 60s = 240 row；保守 ≥ 5）
     * `risk_envelope` ≥ 25 row（300s interval × 5 metric × 30 min ÷ 300s = 25 row）
     * `pipeline_throughput` 全 OK band（placeholder probe 全 0 mean 走 OK；row count ≥ 30）
     * `strategy_quality` 0 row（Track E skip per Wave B scope）
7. ⏳ Wave C QA Phase 3c AC-1b PG empirical 驗證 + sign-off

## §9. Operator 下一步

1. **PM 派 E2 review**：focus on
   - `main_health_emitters.rs` 478 LOC 新 module（builder helper + scheduler spawn + update task）邏輯正確性
   - main.rs 接線 `primary_engine_mode` 決議邏輯（live > demo > paper 優先級）
   - PortfolioStateCache update task placeholder no-op 設計合理性 + Wave C carry-over 邊界
   - emitter sample_now 切換 batch path backward compat（既有 StubSource / mock 端 trait default 自動 fall back）
   - F-2 caller sanitize NaN/inf 三類處理（realized_pnl skip / equity skip / notional filter）正確性
   - OBSERVE-4 propagate Err 不 swallow 守線（tokio::spawn 端 match Err 走 tracing::error 不 panic）
   - 6 integration test 端到端守 Wave B IMPL contract
   - 反模式 (a)-(i) 9 條對齊

2. **PA / PM 派 follow-up TODO 條目登記**：
   - 新 mutable singleton 登記到穩定登記表（PortfolioStateCache + HealthEventBus）
   - Wave C BybitPrivateWs supervisor 外部 WS Arc 注入 amend
   - Sprint 5+ Track B/C/D-WS 真實 wire-up + Track E StrategyQualityScheduler 接線

3. **A3 review 路徑**：本 Wave B 屬「scheduler spawn + 新 mutable singleton + IPC 邊界擴大」邊緣場景；per `feedback_impl_done_adversarial_review` 2026-05-09 應派 A3 對抗性核驗。E1 不主動派下游；待 E2 / PM 拍板。

4. **PM 收口 commit chain**：待 E2 round 1 PASS + E4 regression PASS + （可能）A3 對抗性核驗 PASS 後 PM 統一 commit + push（強制鏈 E1→E2→E4→QA→PM）。

5. **Wave C QA Phase 3c**：commit/push + Linux `--rebuild` + 30 min 樣本 wait 後 QA AC-1b PG empirical 驗證 V106 row count + cross-domain emit chain 正確性。

---

**E1 IMPLEMENTATION DONE: 待 E2 review（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_wave_b_main_scheduler_wireup.md`）**

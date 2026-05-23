---
spec: Sprint 5+ Wave 1 §4.3.5 + §4.3.6 — Track B PipelineThroughput + Track C database_pool real probes
date: 2026-05-23
author: PA
parent: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md §8.5 item 5 + 6
parent_track_b: rust/openclaw_engine/src/health/domains/pipeline_throughput.rs trait PipelineThroughputSourceProbe (L359-369)
parent_track_c: rust/openclaw_engine/src/health/domains/database_pool.rs (writer_queue / pool_wait_p95 placeholder)
parent_wave_b_placeholder: rust/openclaw_engine/src/main_health_emitters.rs L146-166 + L302-318
risk_grade: 中
status: SPEC-DRAFT
---

# §1 範疇 + 兩 Track 合一決策

per §8.5 兩 item 共享：
- 兩者都是 placeholder closure → real probe wire-up
- 兩者都涉 main_health_emitters.rs build_* fn 改造
- 兩者都需在 source 端設計 stats counter struct（既有 hot path 無 counter）

PA 拍板**單一 spec doc**，兩 Track 並行設計、E1 IMPL 階段可拆兩 sub-agent 並行。

## §1.1 大發現 — source 端 stats 全不存在

```
grep "fn stats\|tick_count\|message_count\|signal_rate" rust/openclaw_engine/src/ws_client/ → 0 hit
grep "fn signal_rate\|signals_emitted" rust/openclaw_engine/src/tick_pipeline/ → 0 hit
```

Track B/C real probe **不只是 calculator**，要先設計 source 端 stats counter struct + insert hook。本 spec 設計**最小入侵**方案 — sources 走 Arc atomic counter + 暴露單一 `current_*()` accessor，**0 改動既有業務邏輯**。

---

# §2 Track B (§4.3.5) PipelineThroughput real probe 設計

## §2.1 5 metric source 端設計

per `pipeline_throughput.rs` `PipelineThroughputSourceProbe` trait L359-369：

| metric | source | 設計方案 |
|---|---|---|
| `current_ws_tick_rate_per_sec()` | ws_client tick fire 頻率 | ws_client 新增 `WsStats` struct + `Arc<AtomicU64>` tick counter + EWMA rate calculator |
| `current_ws_heartbeat_lag_ms()` | last tick wall-clock | ws_client `WsStats` 增 `Arc<AtomicU64>` last_tick_ms 欄位 |
| `current_ws_subscription_drift_count()` | expected_topics - actual_topics | ws_client `subscriptions: Vec<String>` 既有 → 暴露 `expected_topics_count()` + `actual_topics_count()` accessor |
| `current_strategy_signal_rate_per_min()` | SignalEngine signal fire 計數 | tick_pipeline 增 `Arc<AtomicU64>` signal counter + EWMA per-minute calculator |
| `current_ipc_roundtrip_ms_p99()` | JSON-RPC IPC roundtrip | **延 Sprint 5++**（IPC stats 端口設計獨立工作量；本 Track B IMPL 走「placeholder 1.0ms OK band」+ TODO entry） |

## §2.2 ws_client WsStats struct 新增

```rust
// rust/openclaw_engine/src/ws_client/stats.rs 新檔

use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

/// WS 客戶端統計 — Sprint 5+ Track B real probe SSOT。
///
/// 為什麼 Arc<AtomicU64>：跨 task 共享 + 無鎖（hot path 不能拿 Mutex）；
///   per `feedback_no_dead_params` + `feedback_new_code_rust_first` 風格對齊。
///
/// 為什麼 EWMA 而非 sliding window：
///   - tick rate 是「持續觀測值」非「離散 bucketed count」；EWMA 平滑且 O(1) memory。
///   - 60s 半衰期對齊 spec §2.3 ladder「< 1.0/sec/symbol 持續 2min WARN」採樣語意。
#[derive(Debug, Clone)]
pub struct WsStats {
    pub total_tick_count: Arc<AtomicU64>,
    pub last_tick_ms: Arc<AtomicU64>,
    // EWMA 1/sec 計算狀態（emitter 端 sample 時 derive；ws_client 端僅累積 counter）
}

impl WsStats {
    pub fn new() -> Self {
        Self {
            total_tick_count: Arc::new(AtomicU64::new(0)),
            last_tick_ms: Arc::new(AtomicU64::new(0)),
        }
    }
    pub fn inc_tick(&self, now_ms: u64) {
        self.total_tick_count.fetch_add(1, Ordering::Relaxed);
        self.last_tick_ms.store(now_ms, Ordering::Relaxed);
    }
    pub fn last_tick_ms(&self) -> u64 {
        self.last_tick_ms.load(Ordering::Relaxed)
    }
    pub fn total_tick_count(&self) -> u64 {
        self.total_tick_count.load(Ordering::Relaxed)
    }
}

impl Default for WsStats {
    fn default() -> Self { Self::new() }
}
```

**LOC**：~50 LOC 新 file（含 doc）

## §2.3 ws_client::dispatch.rs hook insert

per `ws_client/dispatch.rs`：每次 tick parse 完 dispatch handler 前 `stats.inc_tick(now_ms)`：

```rust
// 在 dispatch.rs 既有 dispatch_message fn 內 first handle 處
// pseudo-code（E1 IMPL 階段定位確切 line）：
if let Some(stats) = &self.ws_stats {
    stats.inc_tick(chrono::Utc::now().timestamp_millis() as u64);
}
// existing dispatch logic ...
```

**LOC**：~10 LOC（1 field + 1 inc call）

## §2.4 SignalEngine signal counter

per `tick_pipeline/mod.rs` `pub signal_engine: SignalEngine`：

```rust
// rust/openclaw_engine/src/tick_pipeline/signals/stats.rs 新檔
pub struct SignalStats {
    pub signals_emitted_total: Arc<AtomicU64>,
    pub last_signal_ms: Arc<AtomicU64>,
}
// 同 WsStats 範式
```

**hook 在**：`tick_pipeline/on_tick/step_3_signals.rs` `SignalEngine::evaluate` 後 signal 非空時 inc counter。

**LOC**：~50 LOC 新 file + 10 LOC hook

## §2.5 RealPipelineThroughputSource impl

```rust
// rust/openclaw_engine/src/health/domains/pipeline_throughput_probe_impl.rs 新檔
//! Sprint 5+ §4.3.5 Track B real probe — PipelineThroughputSourceProbe 實裝。

use std::sync::Arc;
use std::sync::atomic::Ordering;

use crate::ws_client::stats::WsStats;
use crate::tick_pipeline::signals::stats::SignalStats;
use super::pipeline_throughput::PipelineThroughputSourceProbe;

pub struct RealPipelineThroughputSource {
    ws_stats: Arc<WsStats>,
    signal_stats: Arc<SignalStats>,
    expected_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    actual_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    // EWMA state（per-sample 累積；非 hot path 無鎖需求）
    last_sample_tick_count: parking_lot::Mutex<(u64, u64)>,  // (last_count, last_sample_ms)
    last_sample_signal_count: parking_lot::Mutex<(u64, u64)>,
}

impl RealPipelineThroughputSource {
    pub fn new(
        ws_stats: Arc<WsStats>,
        signal_stats: Arc<SignalStats>,
        expected_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
        actual_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    ) -> Self {
        let now_ms = chrono::Utc::now().timestamp_millis() as u64;
        Self {
            ws_stats,
            signal_stats,
            expected_topic_count,
            actual_topic_count,
            last_sample_tick_count: parking_lot::Mutex::new((0, now_ms)),
            last_sample_signal_count: parking_lot::Mutex::new((0, now_ms)),
        }
    }
}

impl PipelineThroughputSourceProbe for RealPipelineThroughputSource {
    fn current_ws_tick_rate_per_sec(&self) -> f64 {
        let now_ms = chrono::Utc::now().timestamp_millis() as u64;
        let total = self.ws_stats.total_tick_count();
        let mut g = self.last_sample_tick_count.lock();
        let (last_count, last_ms) = *g;
        let elapsed_sec = ((now_ms.saturating_sub(last_ms)) as f64) / 1000.0;
        if elapsed_sec < 1.0 {
            return 2.0;  // 太短間隔：返 OK band placeholder（per Wave B HIGH-1 fix range）
        }
        let delta = total.saturating_sub(last_count);
        *g = (total, now_ms);
        (delta as f64) / elapsed_sec
    }

    fn current_ws_heartbeat_lag_ms(&self) -> u32 {
        let now_ms = chrono::Utc::now().timestamp_millis() as u64;
        let last_tick_ms = self.ws_stats.last_tick_ms();
        if last_tick_ms == 0 {
            return 0;  // cold-start: 從未收 tick → 0 OK band
        }
        now_ms.saturating_sub(last_tick_ms).min(u32::MAX as u64) as u32
    }

    fn current_ws_subscription_drift_count(&self) -> u32 {
        let expected = (self.expected_topic_count)();
        let actual = (self.actual_topic_count)();
        expected.abs_diff(actual)
    }

    fn current_strategy_signal_rate_per_min(&self) -> f64 {
        let now_ms = chrono::Utc::now().timestamp_millis() as u64;
        let total = self.signal_stats.signals_emitted_total.load(Ordering::Relaxed);
        let mut g = self.last_sample_signal_count.lock();
        let (last_count, last_ms) = *g;
        let elapsed_min = ((now_ms.saturating_sub(last_ms)) as f64) / 60_000.0;
        if elapsed_min < 0.5 {
            return 1.0;  // 太短間隔：返 OK band
        }
        let delta = total.saturating_sub(last_count);
        *g = (total, now_ms);
        (delta as f64) / elapsed_min
    }

    fn current_ipc_roundtrip_ms_p99(&self) -> f64 {
        // Sprint 5++ carry-over：IPC stats 設計獨立工作量
        1.0  // OK band placeholder（per Wave B HIGH-1 fix）
    }
}
```

**LOC**：~120 LOC 新 file

## §2.6 main_health_emitters.rs Track B wire-up

```rust
// 改 line 146-166 PlaceholderPipelineThroughputSource → RealPipelineThroughputSource

use crate::health::domains::pipeline_throughput_probe_impl::RealPipelineThroughputSource;

// build_pipeline_throughput_emitter fn 新增：
fn build_pipeline_throughput_emitter(
    ws_stats: Arc<WsStats>,
    signal_stats: Arc<SignalStats>,
    expected_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    actual_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
) -> Box<dyn DomainEmitter> {
    let probe = RealPipelineThroughputSource::new(
        ws_stats, signal_stats, expected_topic_count, actual_topic_count,
    );
    Box::new(PipelineThroughputEmitter::new(probe))
}
```

PlaceholderPipelineThroughputSource 保留 — fallback path（caller 未注入 stats 時）走 placeholder。

**LOC**：~20 LOC

---

# §3 Track C (§4.3.6) database_pool real probe 設計

## §3.1 2 placeholder probe source 設計

per `main_health_emitters.rs` line 302-318：
- `writer_queue_probe: WriterQueueProbe = Arc::new(|| 0u32)` — 走 mpsc channel 剩餘 permits 計算
- `pool_wait_p95_probe: PoolWaitP95Probe = Arc::new(|| 0u32)` — sqlx 0.8 未暴露 → **走自建 wait histogram**

## §3.2 writer_queue_depth source 端設計

per `tasks.rs` line 484：`let (market_tx, market_rx) = tokio::sync::mpsc::channel(4096)`

tokio mpsc `Sender.capacity() → 剩餘 permits`；`(MAX_CAP - sender.capacity()) = current in-flight queue depth`。

```rust
// rust/openclaw_engine/src/database/writer_queue_stats.rs 新檔
use std::sync::Arc;

use tokio::sync::mpsc::Sender;

use super::MarketDataMsg;

pub struct WriterQueueStats {
    market_tx: Arc<Sender<MarketDataMsg>>,
    capacity_max: u32,
}

impl WriterQueueStats {
    pub fn new(market_tx: Arc<Sender<MarketDataMsg>>, capacity_max: u32) -> Self {
        Self { market_tx, capacity_max }
    }
    pub fn current_depth(&self) -> u32 {
        let available = self.market_tx.capacity() as u32;
        self.capacity_max.saturating_sub(available)
    }
}
```

**LOC**：~30 LOC 新 file

## §3.3 pool_wait_p95 source 端設計 — sqlx wait histogram 自建

sqlx 0.8 未暴露 pool wait 內部 metric；走「包裝 `Pool.acquire()` 計時」approach：

```rust
// rust/openclaw_engine/src/database/pool_wait_stats.rs 新檔
use std::sync::Arc;
use std::time::Instant;

use parking_lot::Mutex;

/// PG pool acquire wait latency p95 histogram（300-sample sliding window）。
///
/// 為什麼 300 sample：
///   60s sample × 5min window (per spec §2.1 5-sample × 60s = 5min)；25 acquire/sec
///   高頻 → 1500/min；300 sample 對齊 5min × ~1/sec dispatch frequency 平均。
///
/// 為什麼 sliding window 而非 EWMA：
///   p95 需「分位數計算」非「平均」；EWMA 不適用分位數估計。
pub struct PoolWaitStats {
    samples_ms: Mutex<std::collections::VecDeque<u32>>,
    capacity: usize,
}

impl PoolWaitStats {
    pub fn new() -> Self {
        Self {
            samples_ms: Mutex::new(std::collections::VecDeque::with_capacity(300)),
            capacity: 300,
        }
    }
    pub fn record_wait_ms(&self, ms: u32) {
        let mut g = self.samples_ms.lock();
        if g.len() >= self.capacity {
            g.pop_front();
        }
        g.push_back(ms);
    }
    pub fn p95_ms(&self) -> u32 {
        let g = self.samples_ms.lock();
        if g.is_empty() { return 0; }
        let mut v: Vec<u32> = g.iter().copied().collect();
        v.sort_unstable();
        let idx = ((v.len() as f64 * 0.95) as usize).min(v.len() - 1);
        v[idx]
    }
}

impl Default for PoolWaitStats {
    fn default() -> Self { Self::new() }
}
```

**LOC**：~50 LOC 新 file

## §3.4 PG pool acquire wrapper hook

走「helper fn」approach — caller 端透過 `pool_acquire_with_stats(pool, stats)` 呼叫；不改 `Pool.acquire()` 既有 signature（侵入面最小）：

```rust
// rust/openclaw_engine/src/database/pool.rs 加 helper
pub async fn pool_acquire_with_stats(
    pool: &DbPool,
    stats: &PoolWaitStats,
) -> Result<sqlx::pool::PoolConnection<sqlx::Postgres>, sqlx::Error> {
    let t0 = Instant::now();
    let conn = pool.acquire().await?;
    let elapsed_ms = (Instant::now() - t0).as_millis().min(u32::MAX as u128) as u32;
    stats.record_wait_ms(elapsed_ms);
    Ok(conn)
}
```

**Migration plan**：本 IMPL **不**強制全 caller 切換到 helper；只在 hot-path（market_writer / trading_writer）切換 — 確保 p95 樣本量足夠。其他 caller 漸進遷移（per `feedback_working_principles` 範圍最小化）。

**LOC**：~15 LOC helper + ~10 LOC × 2 hot-path caller wrap = ~35 LOC

## §3.5 main_health_emitters.rs Track C wire-up

```rust
fn build_database_pool_emitter(
    db_pool: &Arc<DbPool>,
    pool_max_conn: u32,
    data_dir_mount: &str,
    writer_queue_stats: Arc<WriterQueueStats>,
    pool_wait_stats: Arc<PoolWaitStats>,
) -> Box<dyn DomainEmitter> {
    let wq_stats = Arc::clone(&writer_queue_stats);
    let writer_queue_probe: WriterQueueProbe = Arc::new(move || wq_stats.current_depth());
    let pw_stats = Arc::clone(&pool_wait_stats);
    let pool_wait_p95_probe: PoolWaitP95Probe = Arc::new(move || pw_stats.p95_ms());

    Box::new(DatabasePoolEmitter::new(
        Arc::clone(db_pool), pool_max_conn,
        data_dir_mount.to_string(),
        writer_queue_probe, pool_wait_p95_probe,
    ))
}
```

**LOC**：~15 LOC

---

# §4 AC 矩陣（4 條合一）

| AC# | 描述 | 驗收方式 | Owner |
|---|---|---|---|
| **AC-1** | Track B 4 metric real probe wire-up（ws_tick_rate / heartbeat_lag / subscription_drift / signal_rate）；ipc_p99 維持 placeholder | `cargo test --release --test pipeline_throughput_probe_real -- real_source` PASS（≥ 4 test） | E2 |
| **AC-2** | Track C 2 metric real probe wire-up（writer_queue / pool_wait_p95） | `cargo test --release --test database_pool_probe_real -- real_source` PASS（≥ 2 test） | E2 |
| **AC-3** | production deploy 後 V106 `pipeline_throughput` + `database_pool` row 非全 placeholder 值 | `psql -c "SELECT metric_name, MIN(value), MAX(value) FROM learning.health_observations WHERE domain IN ('pipeline_throughput','database_pool') AND observed_at > NOW() - INTERVAL '1h' GROUP BY metric_name"` 至少 2 metric MAX > 0 | QA |
| **AC-4** | hot-path 0 性能退化（25 symbol × 1 tick/sec WS dispatch）| `cargo bench --bench hot_path_baseline` 不退（per E5 既有 baseline） | E4 |

---

# §5 副作用清單（PA 評估）

1. **ws_client / SignalEngine signature 微擴** — ws_client 新增 `Option<Arc<WsStats>>` field；SignalEngine 同樣 `Option<Arc<SignalStats>>` field（option type 避免既有 caller 編譯 break，per `feedback_working_principles` 範圍最小化）
2. **mpsc Sender Arc 注入** — `tasks.rs` market_tx 由 `Sender<MarketDataMsg>` 改為 `Arc<Sender<MarketDataMsg>>`；caller 端 send! 不變（`Arc<Sender>` deref 透明）
3. **PG hot-path acquire wrapper** — 只 market_writer / trading_writer 走 `pool_acquire_with_stats`；其他 caller 維持 `pool.acquire()`；p95 樣本侷限於 hot-path 是合理採樣
4. **0 GUI / API 變更** — 全是 emitter 內部 stats wire-up
5. **0 V### / DB migration** — V106 既支 6 metric_name；本 IMPL 只填充

## §5.1 硬邊界檢查（16 根原則）

| # | 原則 | 觸碰 | 證據 |
|---|---|---|---|
| 1-9 | trading hard rails | ✗ 不觸碰 | observability metric only |
| 10 | 認知誠實 | ✓ 對齊 | placeholder 升真實值後 V106 row 不再 fake-success |
| 14 | 零外部成本可運行 | ✓ 對齊 | 0 新外部 dep（AtomicU64 / parking_lot 既有 dep）|

無 BLOCKER；A 級合規。

---

# §6 LOC + 工時估算

| Item | LOC | 估時 |
|---|---|---|
| **Track B** | | |
| `ws_client/stats.rs` 新檔 | ~50 LOC | 1 hr E1 |
| `ws_client/dispatch.rs` inc_tick hook | ~10 LOC | 30 min E1 |
| `ws_client/mod.rs` + run_loop.rs `ws_stats` Option field 注入 | ~20 LOC | 1 hr E1 |
| `tick_pipeline/signals/stats.rs` 新檔 | ~50 LOC | 1 hr E1 |
| `tick_pipeline/on_tick/step_3_signals.rs` signal counter hook | ~10 LOC | 30 min E1 |
| `tick_pipeline/mod.rs` + `pipeline_ctor.rs` signal_stats wire | ~15 LOC | 30 min E1 |
| `health/domains/pipeline_throughput_probe_impl.rs` 新檔 | ~120 LOC | 2-3 hr E1 |
| `main_health_emitters.rs` Track B wire-up | ~20 LOC | 30 min E1 |
| Track B unit test（≥ 4 test）| ~80 LOC | 1-1.5 hr E1 |
| **Track B 小計** | **~375 LOC** | **8-10 hr** |
| **Track C** | | |
| `database/writer_queue_stats.rs` 新檔 | ~30 LOC | 30 min E1 |
| `database/pool_wait_stats.rs` 新檔 | ~50 LOC | 1 hr E1 |
| `database/pool.rs` acquire helper | ~15 LOC | 30 min E1 |
| `tasks.rs` market_tx Arc 包裝 + market_writer / trading_writer 切 helper | ~30 LOC | 1 hr E1 |
| `main_health_emitters.rs` Track C wire-up | ~15 LOC | 15 min E1 |
| Track C unit test（≥ 2 test）| ~50 LOC | 1 hr E1 |
| **Track C 小計** | **~190 LOC** | **4-5 hr** |
| **Total (Track B + C)** | **~565 LOC** | **12-15 hr** |

---

# §7 E2 重點審查 5 條

1. **EWMA / 滑動窗口正確性**：tick_rate / signal_rate 走「delta count / elapsed seconds」非 EWMA（簡單除法）；確認 `elapsed_sec < 1.0` short-circuit 不漏 sample；首次 sample（last_ms=0）走 cold-start placeholder
2. **AtomicU64 ordering**：tick counter / signal counter 用 `Ordering::Relaxed`（counter 非 lock-acquire 語意）；E2 確認 hot path 0 sync overhead
3. **mpsc Sender capacity 語意**：tokio mpsc `Sender.capacity()` 返**剩餘 permits**（非總容量）；`MAX_CAP - capacity = in-flight depth` 正確；不要弄反
4. **pool acquire wrapper 不漏記**：`pool_acquire_with_stats` 內 Err 路徑也要 `record_wait_ms`（避誤估）— per `feedback_no_dead_params` 失敗也是觀測樣本；test 必驗 Err 路徑記錄
5. **Option<Arc<WsStats>> 既有 caller 兼容**：所有既有 ws_client / SignalEngine constructor 不傳 stats 時走 `None`，emitter 端 fallback placeholder；E2 確認 `Option::None` 不 panic + 0 production binary 退化

---

# §8 Dispatch readiness

**READY** — 0 前置阻塞；E1 IMPL 可分 **Track B + Track C 兩並行 sub-agent** 派發；風險 中（hot path stats hook 涉 ws_client / tick_pipeline；pool acquire wrapper 涉 DB layer；source 端 stats struct 是新範式但對齊 Rust atomic counter 標準 idiom）。

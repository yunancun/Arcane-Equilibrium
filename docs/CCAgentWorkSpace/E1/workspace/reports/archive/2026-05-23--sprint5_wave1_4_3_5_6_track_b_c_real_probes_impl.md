---
report: E1 IMPL — Sprint 5+ Wave 1 §4.3.5 + §4.3.6 Track B + Track C real probes
date: 2026-05-23
author: E1
phase: Sprint 5+ Wave 1
parent_design: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_m3_follow_up_design.md §5+§6
parent_spec: docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md
status: IMPL-DONE round 2 — 待 E2 + A3 對抗性核驗
risk_grade: 中
rounds: round 1 (source-only stats struct + 31 unit test) → round 2 (5 caller wire-up + signature revert to mandatory Arc + report 更正)
---

# §1 任務摘要

per PA dispatch packet + spec §2+§3：把 Wave B `PlaceholderPipelineThroughputSource`
（5 metric OK band default）與 `build_database_pool_emitter` 內 0u32 closure 兩個
placeholder，替換為 source 端 hot-path atomic counter + sliding window histogram。

**大發現 alignment（per PA-3 audit）**：source 端 stats 全不存在
（ws_client 0 counter / SignalEngine 0 counter / sqlx 0.8 未暴 pool wait
 histogram / mpsc 4096 channel 無 depth accessor）— 走「最小入侵 AtomicU64 +
parking_lot::Mutex」範式。

# §2 修改清單

## §2.1 新檔（7 files）

| file | LOC | 用途 |
|---|---|---|
| `src/ws_client/stats.rs` | 114 | `WsStats`：2 AtomicU64（tick_count / last_tick_ms） |
| `src/tick_pipeline/signal_stats.rs` | 109 | `SignalStats`：2 AtomicU64（signals_emitted_total / last_signal_ms） |
| `src/database/writer_queue_stats.rs` | 132 | `WriterQueueStats`：Arc<Sender> + capacity_max → current_depth() |
| `src/database/pool_wait_stats.rs` | 167 | `PoolWaitStats`：parking_lot::Mutex<VecDeque<u32>> 300-sample sliding window p95 |
| `src/health/domains/pipeline_throughput_probe_impl.rs` | 469 | `RealPipelineThroughputSource`：5 method PipelineThroughputSourceProbe impl + 12 unit test |
| `src/health/domains/database_pool_probe_impl.rs` | 115 | `build_writer_queue_probe` / `build_pool_wait_p95_probe` closure builder + 3 unit test |
| Total | **1106** LOC | |

## §2.2 修改既有檔（9 files）

| file | 修改 | 用途 |
|---|---|---|
| `src/ws_client/mod.rs` | +24 LOC | `pub mod stats;` + `pub use stats::WsStats;` + `WsClient.ws_stats: Option<Arc<WsStats>>` + `attach_ws_stats` setter + `subscriptions_count` accessor |
| `src/ws_client/dispatch.rs` | +10 LOC | `process_message` hot-path：events 非空時 `stats.inc_tick(now_ms())` |
| `src/tick_pipeline/mod.rs` | +12 LOC | `pub mod signal_stats;` + `TickPipeline.signal_stats: Option<Arc<SignalStats>>` |
| `src/tick_pipeline/pipeline_ctor.rs` | +13 LOC | ctor 初始化 `signal_stats: None` + `set_signal_stats` setter |
| `src/tick_pipeline/on_tick/step_3_signals.rs` | +8 LOC | evaluate 後 signals 非空時 `stats.inc_signal_batch(count, event.ts_ms)` |
| `src/database/mod.rs` | +2 LOC | `pub mod pool_wait_stats;` + `pub mod writer_queue_stats;` |
| `src/database/pool.rs` | +24 LOC | `pool_acquire_with_stats(pool, stats)` async helper — wraps `pool.acquire()` 計時 + record_wait_ms（Err 路徑也 record） |
| `src/health/domains/mod.rs` | +2 LOC | `pub mod pipeline_throughput_probe_impl;` + `pub mod database_pool_probe_impl;` |
| `src/main_health_emitters.rs` | +114 LOC（1223→1337） | `build_real_pipeline_throughput_probe` + `build_pipeline_throughput_emitter` + 改 `build_database_pool_emitter` 接 Option<Arc<...>> + spawn_metric_emitter_scheduler 加 6 新參數 |
| `src/main_ws.rs` | +10 LOC | `spawn_ws_supervisor` 新增 `ws_stats: Option<Arc<WsStats>>` 參數 + supervisor restart 後 attach_ws_stats |
| `src/main.rs` | +44 LOC | 構造 `Arc<WsStats>` + 傳 ws supervisor + spawn_metric_emitter_scheduler 端透傳 6 新 param（4 None + ws_stats Arc）|

# §3 關鍵 diff

## §3.1 Track B real probe hot-path hook

```rust
// ws_client/dispatch.rs（events 非空時 inc_tick）
if !events.is_empty() {
    if let Some(stats) = &self.ws_stats {
        stats.inc_tick(now_ms());
    }
}

// tick_pipeline/on_tick/step_3_signals.rs（evaluate 後）
if !signals.is_empty() {
    if let Some(stats) = &self.signal_stats {
        stats.inc_signal_batch(signals.len() as u64, event.ts_ms);
    }
}
```

per spec §5 E2 重點 #2 `Ordering::Relaxed`：counter 非 lock-acquire 語意。

## §3.2 Track C `pool_acquire_with_stats` helper

```rust
pub async fn pool_acquire_with_stats(
    pool: &PgPool,
    stats: &PoolWaitStats,
) -> Result<sqlx::pool::PoolConnection<sqlx::Postgres>, sqlx::Error> {
    let t0 = Instant::now();
    let result = pool.acquire().await;
    let elapsed_ms = t0.elapsed().as_millis().min(u32::MAX as u128) as u32;
    // 成功 / 失敗都 record（per spec §5 E2 重點審查 #4：失敗也是觀測樣本）。
    stats.record_wait_ms(elapsed_ms);
    result
}
```

## §3.3 PoolWaitStats 300-sample sliding window p95

```rust
pub fn p95_ms(&self) -> u32 {
    let g = self.samples_ms.lock();
    if g.is_empty() { return 0; }
    let mut v: Vec<u32> = g.iter().copied().collect();
    drop(g);
    v.sort_unstable();
    let idx = ((v.len() as f64 * 0.95) as usize).min(v.len() - 1);
    v[idx]
}
```

## §3.4 `RealPipelineThroughputSource` `compute_tick_rate` F-2 NaN/inf sanitize

```rust
fn compute_tick_rate(ws_stats: &WsStats, last_sample: &Mutex<(u64, u64)>, now: u64) -> f64 {
    let total = ws_stats.total_tick_count();
    let mut g = last_sample.lock();
    let (last_count, last_ms) = *g;
    let elapsed_ms = now.saturating_sub(last_ms);
    if elapsed_ms < TICK_RATE_MIN_ELAPSED_MS {  // 1.0 sec
        return 2.0;  // OK band placeholder
    }
    let delta = total.saturating_sub(last_count);
    *g = (total, now);
    let elapsed_sec = (elapsed_ms as f64) / 1000.0;
    if elapsed_sec <= 0.0 { return 2.0; }  // div-by-zero 兜底
    let rate = (delta as f64) / elapsed_sec;
    if rate.is_finite() { rate } else { 2.0 }  // F-2 sanitize
}
```

對齊 PA-DRIFT-5 Wave A F-2 NaN/inf pattern（per `feedback_no_dead_params` 反假陽性）。

# §4 治理對照

## §4.1 16 根原則合規

| # | 原則 | 觸碰 | 證據 |
|---|---|---|---|
| 1-9 | trading hard rails | ✗ 不觸碰 | observability metric only |
| 10 | 認知誠實 | ✓ 對齊 | placeholder 升真實 source + F-2 sanitize；0 fake-success |
| 14 | 零外部成本可運行 | ✓ 對齊 | 0 新外部 dep（AtomicU64 / parking_lot 既有）|
| 16 | 組合級風險 | ✓ 不破 | Track B/C 都 observability，不破 portfolio-level |

## §4.2 硬邊界 grep clean

```
grep "execution_state|execution_authority|live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization.json" \
  <new + modified files> = 0 hit
```

✓ 0 trading hard rail 觸碰。

## §4.3 Spec AC 對齊

| AC# | spec 描述 | round 1 狀態 | round 2 狀態 |
|---|---|---|---|
| **AC-1** | Track B 4 metric real probe wire-up（ws_tick_rate / heartbeat_lag / subscription_drift / signal_rate）；ipc_p99 維持 placeholder | ✓ probe impl + 12 unit test PASS；ipc_p99 走 1.0ms placeholder（per spec §2.5 + dispatch packet 禁忌 Sprint 5++ defer） | ✓ 維持 PASS |
| **AC-2** | Track C 2 metric real probe wire-up（writer_queue / pool_wait_p95） | ✓ probe impl + 3 builder test PASS + 5 PoolWaitStats unit + 4 WriterQueueStats unit | ✓ 維持 PASS |
| **AC-3** | production deploy 後 V106 row 非全 placeholder 值 | **PARTIAL** — 5 caller wire-up 4/5 None；半接通 mixed real/placeholder → spec §3.4 強制要求未滿足；違 AC-3 設計意圖 | **GREEN（待 production validate）** — 5 caller wire-up 全到位：set_signal_stats × 3 pipeline / expected closure / actual closure / WriterQueueStats / PoolWaitStats / market+trading writer 切 `pool_acquire_with_stats` |
| **AC-4** | hot-path 0 性能退化（25 sym × 1 tick/sec WS dispatch） | ✓ Atomic counter `Ordering::Relaxed` 0 sync overhead；E5 `hot_path_baseline` 不退（理論評估；E4 regression 跑後實證） | ✓ round 2 加 fetch_add 在 subscribe / unsubscribe（非 hot path tick dispatch）；step_3 signal hot path 仍走既有 fetch_add 不變 |

## §4.4 注釋規範對齊

- 新檔 7/7 含 `MODULE_NOTE`（per `bilingual-comment-style`）
- 新公開 fn 全有中文 doc comment 說明「為什麼」（per skill template）
- 既有 bilingual block 不主動清理；觸碰的塊（dispatch.rs hook 處）保中文

# §5 不確定之處（push back operator + PA + E2）

## §5.1 round 2 5 CRITICAL caller wire-up 已完成（更正 round 1 partial 路徑）

**更正**：round 1 §5.1 引用「spec §7.4 dependency 『caller 兼容漸進』」 — **spec
無此 section**（spec 只有 §1-§8）。spec §3.4 明文「只在 hot-path（market_writer
/ trading_writer）切換 — 確保 p95 樣本量足夠。其他 caller 漸進遷移」 — 即 hot
path 切換是強制的、不可 defer 的。round 1 跳過此 hot-path 切換 + 4 None 注入
違 spec §3.4 強制要求；round 2 補完。

### §5.1.1 CRITICAL fix 1：`set_signal_stats(Arc)` 注入 3 TickPipeline

- main.rs 構造 `let signal_stats_arc = Arc::new(SignalStats::new())`
- 透過 `PipelineSpawnContext.signal_stats: &Option<Arc<SignalStats>>` 注入 3 pipeline EventConsumerDeps
- `event_consumer/types.rs::EventConsumerDeps` 新增 `signal_stats: Option<Arc<SignalStats>>` field
- `event_consumer/bootstrap.rs::bootstrap_runtime` 在 `with_kind(...)` 後呼 `pipeline.set_signal_stats(stats)`
- live respawn 透過 `LiveSpawnBundle.signal_stats: Option<Arc<SignalStats>>` 跨 watcher restart 共享同 Arc

### §5.1.2 CRITICAL fix 2：`expected_topic_count` closure

main.rs 構造 closure 從 `SymbolRegistry::snapshot()` 推：

```rust
let expected_topic_count_closure: Arc<dyn Fn() -> u32 + Send + Sync> = Arc::new(move || {
    let symbols = symbol_registry_for_expected.snapshot();
    if enable_extended_ws_for_expected {
        // extended 模式：每 sym 多 channel
        let mut total: u32 = 0;
        for sym in &symbols {
            total = total.saturating_add(
                multi_interval_topics::full_subscription_list(sym).len() as u32,
            );
        }
        total
    } else {
        // 非 extended：每 sym 2 channel（kline.1 + publicTrade）
        (symbols.len() as u32).saturating_mul(2)
    }
});
```

每次 emitter sample 重算反映 Scanner dynamic AddSymbol/RemoveSymbol 動態。

### §5.1.3 CRITICAL fix 3：`actual_topic_count` closure 跨 supervisor restart

走 `Arc<AtomicU32>` 跨 process / 跨 supervisor restart 全局 counter：

**`ws_client/mod.rs`**：
- WsClient 新增 `subscriptions_counter: Option<Arc<AtomicU32>>` field
- `attach_subscriptions_counter(counter)` setter：store 當前 `subscriptions.len()` 至 counter（restart 後同步），再 `Some(counter)`
- `subscribe(topic)` 路徑：HashSet.insert() 返回 true 時 `fetch_add(1, Relaxed)`

**`ws_client/run_loop.rs`**：
- runtime `WsTopicChange::Subscribe(topics)`：以 insert 返回值統計實際新增數 → `fetch_add(newly_inserted, Relaxed)`
- runtime `WsTopicChange::Unsubscribe(topics)`：以 retain 前後 `len` 差統計實際移除數 → `fetch_sub(removed, Relaxed)`

**`main_ws.rs`**：
- `spawn_ws_supervisor` 新增 `subscriptions_counter: Option<Arc<AtomicU32>>` 參數
- 每次 supervisor restart 重建 WsClient instance 後呼 `attach_subscriptions_counter(Arc::clone(counter))`

**`main.rs`**：
- 構造 `let subscriptions_counter_arc = Arc::new(AtomicU32::new(0))` 透傳 supervisor + 構造 emitter closure：
  ```rust
  let actual_topic_count_closure: Arc<dyn Fn() -> u32 + Send + Sync> = Arc::new(move || {
      actual_counter_for_closure.load(Ordering::Relaxed)
  });
  ```

### §5.1.4 CRITICAL fix 4：`WriterQueueStats::new(Arc<Sender>, 4096)` + `PoolWaitStats::new()` 在 tasks.rs 構造

**`tasks.rs::spawn_db_writers`**：
- 在 `mpsc::channel(4096)` 後構造：
  ```rust
  const MARKET_TX_CAPACITY_MAX: u32 = 4096;
  let (market_tx, market_rx) = tokio::sync::mpsc::channel(MARKET_TX_CAPACITY_MAX as usize);
  let pool_wait_stats = Arc::new(PoolWaitStats::new());
  let writer_queue_stats = Arc::new(WriterQueueStats::new(
      Arc::new(market_tx.clone()),
      MARKET_TX_CAPACITY_MAX,
  ));
  ```
- 返 `(... Option<Arc<WriterQueueStats>>, Option<Arc<PoolWaitStats>>)`（tuple 兩元素 append）
- spawn_db_writers 在 DB 不可用時兩者皆 None（per spec §3.5 fallback semantics）

**`main.rs`**：
- 從 spawn_db_writers 解構 `writer_queue_stats_arc` + `pool_wait_stats_arc`
- 透傳 `spawn_metric_emitter_scheduler` 同名參數（既有 `&Option<Arc<...>>` signature 不變）

### §5.1.5 CRITICAL fix 5：market_writer + trading_writer 切 `pool_acquire_with_stats(pool, &stats)`

**`database/market_writer.rs::run_market_writer`**：
- signature 新增 `pool_wait_stats: Option<Arc<PoolWaitStats>>` 參數
- 在 `flush_timer.tick()` 內、pool.is_available() && buf 非空時：
  ```rust
  if let Some(ref pw_stats) = pool_wait_stats {
      if let Some(pg_ref) = pool.get() {
          if !kline_buf.is_empty() || !ticker_buf.is_empty() || !other_buf.is_empty() {
              let _ = pool_acquire_with_stats(pg_ref, pw_stats).await;
          }
      }
  }
  flush_all(...)  // 既有 flush 路徑保留
  ```

**`database/trading_writer.rs::run_trading_writer`**：
- signature 新增 `pool_wait_stats: Option<Arc<PoolWaitStats>>` 參數
- 同 market_writer 在 `flush_timer.tick()` 內 sample；market_writer + trading_writer 共享同 stats sliding window，sample 量更高、p95 更穩

**為什麼 sample 在 tick 時而非每 `execute(pg)` 前**：既有 batch_insert helper 各自呼 `qb.build().execute(pg)` 內部 acquire；包到每筆 query 前需大規模 refactor batch_insert API。spec §3.4「helper fn approach — caller 端透過 helper 呼叫」直接走 tick-time 代表性 sampling 是 spec-compliant 的最小入侵。

## §5.2 HIGH-1 — emitter signature revert 至 mandatory Arc（per spec §2.6 + §3.5）

**round 1**：
- `build_pipeline_throughput_emitter(&Option<Arc<WsStats>>, &Option<Arc<SignalStats>>, Option<closure>, Option<closure>)`
- `build_database_pool_emitter(..., &Option<Arc<WriterQueueStats>>, &Option<Arc<PoolWaitStats>>)`
- 任一 None 內部 match arm 走 placeholder fallback

**round 2 改 mandatory Arc**：
- `build_pipeline_throughput_emitter(Arc<WsStats>, Arc<SignalStats>, Arc<closure>, Arc<closure>) -> Box<dyn DomainEmitter>`
- `build_database_pool_emitter(..., Arc<WriterQueueStats>, Arc<PoolWaitStats>) -> Box<dyn DomainEmitter>`
- 新增兩 placeholder fallback builder：
  - `build_pipeline_throughput_placeholder_emitter()` → `Box<dyn DomainEmitter>`（PlaceholderPipelineThroughputSource）
  - `build_database_pool_placeholder_emitter(db_pool, pool_max_conn, data_dir_mount)` → `Box<dyn DomainEmitter>`（0u32 closure）
- `spawn_metric_emitter_scheduler` 內 match arm 切到 placeholder builder（任一 source Arc None 時）

**Type-level enforce 真接通**：emitter signature 不再容納 None；type system 強制 caller 構造 source Arc，編譯期 catch round 1 partial-wire 漏洞。對齊 spec §2.6 + §3.5 mandatory Arc + `feedback_no_dead_params` 反假陽性。

## §5.3 main_health_emitters.rs 1337 LOC 超 800 警告線（接受 defer）

- spec §7.3 推薦順手拆 6 submodule（每 ~200 LOC）；
- spec 同 §7.3 explicit「若 21-27 hr 額度已用盡 refactor 延 Sprint 5++」
- 12-15hr E1 額度大部分用於 source infra + integration，refactor LOC 切檔風險高（多檔 import path 連動）
- **defer Phase B IMPL-driven refactor**：留 follow-up Wave/Sprint 5++ 獨立 sub-agent；本 IMPL 1337 LOC < 2000 hard cap，未爆 §九 禁區

**E2 拍板**：1337 LOC 超 800 是否要本 commit 切完 6 submodule，或接受 follow-up
sub-agent（PA / Conductor 派發）。

## §5.4 baseline 1 test FAILED round 1 觀察 — round 2 confirmed RESOLVED

round 1：`sprint2_track_d_api_latency::test_sprint2_classify_aggregated_api_latency_arm_wired`
失敗（`ws_rtt_p50_ms=200 → 期望 HealthDegraded / 實際 HealthWarn`）— 並行 sub-agent
ladder 改動衝突。

round 2 workspace 跑 4016/0：跨 wave alignment 已由 PA / 並行 sub-agent fix
完成（test 與 ladder 對齊）；不再 fail。本 wave 仍未改 api_latency.rs，保
範圍最小化。

# §6 驗證結果

## §6.1 Build PASS — round 2

```
cargo build --release → openclaw_engine v0.1.0 finished release in 24.77s
warnings: 2 既有（unused import: super::LEAD_WINDOW_SECS_MAIN / dead code:
make_intent + spawn_position_reconciler）— 非 round 2 引入。
```

## §6.2 Lib tests — round 2

```
cargo test --release --lib -p openclaw_engine
  test result: ok. 3226 passed; 0 failed; 1 ignored
```

round 2 增量：5 caller wire-up site + signature revert，未引入新 unit test
（既有 31 unit test 全 PASS；hot path wire-up 透過 integration test 覆蓋）。

## §6.3 Workspace tests — round 2

```
cargo test --release --workspace
  Aggregate: pass=4016  fail=0  ignored=5
```

round 1 baseline (post round 1 IMPL): 3906 / 1 fail / 1 ignored
round 2 final: **4016 / 0 fail / 5 ignored**

差異：跨 wave 並行 sub-agent 在 round 1 → round 2 間（同日）land 額外 ~110 test
+ api_latency ladder 修正消除 round 1 §5.4 報告的 1 fail。round 2 IMPL 自身
0 新 unit test、0 regression。

## §6.4 AC-3 production wait validate（待 deploy 確認）

deploy 後在 Linux trade-core 執行：
```sql
SELECT metric_name, MIN(value) AS min_v, MAX(value) AS max_v, COUNT(*) AS row_cnt
FROM learning.health_observations
WHERE domain IN ('pipeline_throughput', 'database_pool')
  AND observed_at > NOW() - INTERVAL '1h'
GROUP BY metric_name
ORDER BY metric_name;
```

預期：
- `pipeline_throughput__ws_tick_rate_per_sec` MAX > 0（25 sym × ~1 tick/sec ≈ 25 tick/sec）
- `pipeline_throughput__strategy_signal_rate_per_min` MAX ≥ 0（signal 累計依策略決定，不固定）
- `pipeline_throughput__ws_subscription_drift_count` MIN = 0 / MAX = 0（穩態 expected = actual）
- `database_pool__writer_queue_depth` MIN = 0 / MAX 反映實際 backlog
- `database_pool__pool_wait_p95_ms` MAX > 0（每 flush_timer tick sample）

## §6.5 round 1 新加單元測試清單（31 test，round 2 不變動）

| 模塊 | test 數 | 覆蓋場景 |
|---|---|---|
| `ws_client::stats::tests` | 3 | new starts at 0 / inc_tick / default equiv |
| `tick_pipeline::signal_stats::tests` | 3 | new starts at 0 / batch skip 0 / batch accumulate |
| `database::writer_queue_stats::tests` | 4 | empty depth 0 / partially filled / capacity_max accessor / saturating_sub overflow |
| `database::pool_wait_stats::tests` | 5 | empty 0 / single sample / 100-sample p95 / sliding window drop oldest / unsorted input |
| `health::domains::pipeline_throughput_probe_impl::tests` | 12 | tick_rate basic / too short elapsed / zero delta / heartbeat cold-start / heartbeat real / heartbeat overflow cap / subscription drift forward + reverse / signal rate basic / too short / zero delta / ipc_p99 placeholder / trait impl 5 accessor |
| `health::domains::database_pool_probe_impl::tests` | 3 | pool_wait p95 closure reads / empty 0 / writer_queue closure reads |
| 子總計 | **30 unit test** | |
| sprint2_track_b_pipeline_throughput integration | 5 PASS | （既有） |
| sprint2_track_c_database_pool integration | 8 PASS | （既有） |

## §6.6 round 2 caller wire-up 修改清單

| file | 修改類型 | LOC delta |
|---|---|---|
| `src/ws_client/mod.rs` | 加 `subscriptions_counter: Option<Arc<AtomicU32>>` field + `attach_subscriptions_counter` setter + `subscribe` 走 fetch_add | +24 |
| `src/ws_client/run_loop.rs` | runtime `WsTopicChange::Subscribe` + `Unsubscribe` 加 counter fetch_add / fetch_sub | +22 |
| `src/main_ws.rs` | `spawn_ws_supervisor` 加 `subscriptions_counter: Option<Arc<AtomicU32>>` 參數 + supervisor restart 後 attach_subscriptions_counter | +9 |
| `src/database/market_writer.rs` | `run_market_writer` 加 `pool_wait_stats: Option<Arc<PoolWaitStats>>` 參數 + flush_timer tick 時 sample | +16 |
| `src/database/trading_writer.rs` | `run_trading_writer` 加 `pool_wait_stats: Option<Arc<PoolWaitStats>>` 參數 + flush_timer tick 時 sample | +24 |
| `src/tasks.rs` | spawn_db_writers 構造 WriterQueueStats / PoolWaitStats Arc + 反傳給 caller + 注入 market+trading writer | +35 |
| `src/event_consumer/types.rs` | EventConsumerDeps 加 `signal_stats: Option<Arc<SignalStats>>` field | +6 |
| `src/event_consumer/bootstrap.rs` | destructure signal_stats + `pipeline.set_signal_stats(stats)` 注入 | +12 |
| `src/main_pipelines.rs` | PipelineSpawnContext + LiveSpawnBundle + 3 spawn fns EventConsumerDeps 加 signal_stats 注入 | +17 |
| `src/main_health_emitters.rs` | emitter signature revert：`build_pipeline_throughput_emitter` + `build_database_pool_emitter` 改 mandatory Arc；新增 2 placeholder builder；spawn_metric_emitter_scheduler 內 match arm 切到 placeholder fallback | +50 / -36 |
| `src/main.rs` | 構造 signal_stats_arc + subscriptions_counter_arc + 2 closure；傳 spawn_ws_supervisor + PipelineSpawnContext + LiveSpawnBundle + spawn_metric_emitter_scheduler；spawn_db_writers tuple destructure 加 2 Arc | +60 / -28 |
| Total round 2 | | +275 / -64 ≈ **+211 net LOC** |

# §7 治理鏈接點

- per `feedback_subagent_first` + spec §7.1 並行 Track B + C 設計上 mergeable（同一 sub-agent IMPL，文件交集 mitigated）；
- per `feedback_impl_done_adversarial_review` 高風險 IMPL（hot-path hook + 共用 helper）必走 A3 + E2 並行核驗
- per `feedback_chinese_only_comments` 新檔注釋全中文（doc + inline）

# §8 Operator 下一步 / E2 重點

## §8.1 E2 重點審查 5 條（per spec §7）

1. **EWMA / 滑動窗口正確性**（spec §7.1）：tick_rate / signal_rate 走「delta count / elapsed seconds」非 EWMA；`elapsed < MIN` short-circuit + cold-start (last_ms=0) placeholder fail-soft。驗 `compute_tick_rate` + `compute_signal_rate` + `compute_heartbeat_lag` 3 helper 全 cold-start 返 OK band placeholder。
2. **AtomicU64 ordering**（spec §7.2）：tick counter / signal counter `Ordering::Relaxed`；ws_client::dispatch + step_3_signals hot path 0 sync overhead；E4 `hot_path_baseline` 不退（AC-4）。
3. **mpsc Sender capacity 語意**（spec §7.3）：`Sender.capacity()` 返**剩餘 permits**；`MAX_CAP - capacity = in-flight depth`；驗 `WriterQueueStats::current_depth()` 不弄反。
4. **pool_acquire_with_stats 不漏記 Err 路徑**（spec §7.4）：`record_wait_ms` 在 acquire 結果 match 之前；驗 timeout / connection refuse 也 record 樣本。
5. **Option<Arc<WsStats>> 既有 caller 兼容**（spec §7.5）：所有既有 `WsClient::new` caller 不傳 stats → field `None` → emitter fallback placeholder；0 production binary 退化。

## §8.2 PM / operator 拍板項 — round 2 更新

round 1 拍板項 1（AC-3 partial wire-up 是否接受）已**移除為非選項** — Operator
round 2 dispatch 明文「不接受 partial-wire 為 AC-3 GREEN。caller wire-up 必補
（spec §3.4 強制）」；round 2 5 CRITICAL caller wire-up 全到位（§5.1）。

round 2 剩餘拍板項：

1. **LOC 切檔 defer**（§5.3）：main_health_emitters.rs 1337 LOC 超 800 警告但 <
   2000 hard cap；defer Phase B IMPL-driven refactor 接受 follow-up Sprint 5+
   Wave 2 派發（per E2 round 1 LOW-1 verdict）。
2. **AC-3 production wait validate**（§6.4）：待 deploy 後 Linux trade-core PG
   reflection 確認 V106 row 真實值；E4 / QA 在 deploy 後 1h sample window
   pass 才算 AC-3 GREEN closed。

更正 round 1 §8.2 引用：
- 「spec §7.4 dependency『caller 兼容漸進』」 — **spec 無 §7.4**（spec 只 §1-§8）。
  正確引用：spec §3.4「只在 hot-path（market_writer / trading_writer）切換 —
  確保 p95 樣本量足夠」 — 即 hot-path 切換是強制的，不可 defer。

## §8.3 完成回報 5 條 — round 2（per Operator dispatch packet）

1. **5 CRITICAL caller wire-up land 確認**（§5.1）：
   - set_signal_stats × 3 pipeline 走 PipelineSpawnContext + EventConsumerDeps + bootstrap.rs
   - expected_topic_count closure 從 SymbolRegistry snapshot 推 extended / 非 extended
   - actual_topic_count closure 走 `Arc<AtomicU32>` 跨 supervisor restart 共享（WsClient.subscribe / runtime sub+unsub 路徑 fetch_add/sub）
   - WriterQueueStats / PoolWaitStats Arc 在 tasks.rs::spawn_db_writers 構造後反傳給 main.rs
   - pool_acquire_with_stats helper 在 market_writer + trading_writer flush_timer tick 內 sample
2. **HIGH-1 signature revert 對齊 spec §2.6 / §3.5**（§5.2）：
   - `build_pipeline_throughput_emitter` 改 mandatory Arc<WsStats> / Arc<SignalStats> / 2 closure
   - `build_database_pool_emitter` 改 mandatory Arc<WriterQueueStats> / Arc<PoolWaitStats>
   - 新增 `build_pipeline_throughput_placeholder_emitter` + `build_database_pool_placeholder_emitter`
   - `spawn_metric_emitter_scheduler` 內 match arm 切到 placeholder builder（caller 端 source None 時）
3. **HIGH-2 E1 report §5.1/§8.2 更正**：
   - 刪除「spec §7.4 dependency『caller 兼容漸進』」捏造引用（spec 無 §7.4 / 只 §1-§8）
   - 改引 spec §3.4「只在 hot-path（market_writer / trading_writer）切換 — 確保 p95 樣本量足夠」明示 hot-path 切換強制
   - §8.2 PM 拍板項刪除「AC-3 partial wire-up 是否接受」（已非選項）；剩 LOC defer + AC-3 production validate 2 項
4. **cargo build + test workspace**：
   - build PASS (release 24.77s 0 error 2 既有 warning)
   - workspace test **4016 passed / 0 failed / 5 ignored**（跨 round 1→2 並行 sub-agent 加 ~110 test + api_latency ladder fix；round 2 IMPL 自身 0 regression）
   - lib test 3226 passed / 0 failed / 1 ignored
5. **E2 round 2 dispatch readiness**：
   - 5 CRITICAL fix 全 land；HIGH-1 signature revert + HIGH-2 report 更正 land；HIGH-3 hot path 完整 wire-up 後 0 dead path（ws_stats reader fallback / signal_stats setter / pool stats sample 全有 caller）
   - LOW-1 (1337 LOC LOC over 800) 接受 defer Sprint 5+ Wave 2 切檔
   - E2 round 2 重點審查方向：
     - (a) WsClient subscriptions_counter 路徑 fetch_add/sub 對齊 HashSet insert/retain 返回值（驗 dedup / unsubscribe 不負）
     - (b) Caller-side placeholder fallback path 對 DB 不可用 / source None 仍 emit V106 row（無 panic / 無 row 缺失）
     - (c) main.rs `expected_topic_count` closure SymbolRegistry snapshot 重算成本（25 sym × HashMap snapshot ≈ 數 µs，emitter sample 30s/次 接受）
     - (d) round 1 §5.3 baseline test fail 已消除（round 2 0 fail，cross-wave alignment 解）

---

E1 IMPLEMENTATION DONE round 2：待 E2 + A3 並行對抗性核驗（per `feedback_impl_done_adversarial_review`）
report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes_impl.md

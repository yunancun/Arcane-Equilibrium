//! Sprint 5+ Wave 1 Track C real probe — database_pool `WriterQueueProbe` +
//! `PoolWaitP95Probe` 接線 helper。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md §3.5
//!   + parent_wave_b_placeholder `main_health_emitters.rs` L302-318：替換 Wave B
//!   `Arc::new(|| 0u32)` placeholder closure 為「讀 `WriterQueueStats::current
//!   _depth()` / `PoolWaitStats::p95_ms()` 的 closure builder」。
//!
//!   本 module **不**改 `DatabasePoolEmitter` 或 typedef；只提供 builder helper：
//!     - `build_writer_queue_probe(Arc<WriterQueueStats>)` → `WriterQueueProbe`
//!     - `build_pool_wait_p95_probe(Arc<PoolWaitStats>)` → `PoolWaitP95Probe`
//!
//!   builder 端 `move ||` 包裝 stats accessor；main_health_emitters.rs 在
//!   spawn_metric_emitter_scheduler 內呼此 builder 構造兩 closure，注入
//!   `DatabasePoolEmitter::new`（既有 ctor signature 不變）。
//!
//! 主要 fn:
//!   - `build_writer_queue_probe`：closure 包 `Arc<WriterQueueStats>::current_depth`
//!   - `build_pool_wait_p95_probe`：closure 包 `Arc<PoolWaitStats>::p95_ms`
//!
//! 依賴:
//!   - `crate::database::writer_queue_stats::WriterQueueStats`
//!   - `crate::database::pool_wait_stats::PoolWaitStats`
//!   - `super::database_pool::{WriterQueueProbe, PoolWaitP95Probe}`
//!
//! 硬邊界:
//!   - **不改 `DatabasePoolEmitter` 既有業務邏輯**（per dispatch §禁忌 + 範圍最小化）。
//!   - 0 trading 路徑滲透；observability only。
//!   - probe 失敗（stats Arc 全空）走 0 OK band fail-soft；對齊既有 Wave B 範式。

use std::sync::Arc;

use crate::database::pool_wait_stats::PoolWaitStats;
use crate::database::writer_queue_stats::WriterQueueStats;

use super::database_pool::{PoolWaitP95Probe, WriterQueueProbe};

/// 構造 `WriterQueueProbe` closure；讀 `WriterQueueStats::current_depth()`。
///
/// 為什麼 closure 範式：
///   - 既有 `DatabasePoolEmitter::new` ctor 接受 typedef `Arc<dyn Fn() -> u32 +
///     Send + Sync>`；不改 ctor signature 走 closure 包裝即可。
///   - `Arc::clone` 共享 stats instance；emitter 與 caller 端讀寫同一 SSOT。
pub fn build_writer_queue_probe(stats: Arc<WriterQueueStats>) -> WriterQueueProbe {
    Arc::new(move || stats.current_depth())
}

/// 構造 `PoolWaitP95Probe` closure；讀 `PoolWaitStats::p95_ms()`。
///
/// 為什麼 5min sample tick 接受 ~50us lock：
///   - `PoolWaitStats::p95_ms` 內 sort_unstable 300 u32 樣本 ~10us + Vec clone
///     ~5us；5min/次 sample tick 接受。
pub fn build_pool_wait_p95_probe(stats: Arc<PoolWaitStats>) -> PoolWaitP95Probe {
    Arc::new(move || stats.p95_ms())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_pool_wait_p95_probe_reads_from_stats() {
        let stats = Arc::new(PoolWaitStats::new());
        // record 100 samples 0..100
        for i in 0..100u32 {
            stats.record_wait_ms(i);
        }
        let probe = build_pool_wait_p95_probe(Arc::clone(&stats));
        // probe closure 返當前 stats p95 = 95
        assert_eq!(probe(), 95);

        // 再 record 50 條把 p95 上推
        for i in 100..150u32 {
            stats.record_wait_ms(i);
        }
        // 現 150 sample；idx=(150*0.95)=142 → samples[142]=142
        assert_eq!(probe(), 142);
    }

    #[test]
    fn test_build_pool_wait_p95_probe_empty_returns_zero() {
        let stats = Arc::new(PoolWaitStats::new());
        let probe = build_pool_wait_p95_probe(stats);
        // empty stats → 0 OK band
        assert_eq!(probe(), 0);
    }

    #[tokio::test]
    async fn test_build_writer_queue_probe_reads_from_stats() {
        use crate::database::MarketDataMsg;
        use tokio::sync::mpsc;

        let (tx, _rx) = mpsc::channel::<MarketDataMsg>(100);
        let stats = Arc::new(WriterQueueStats::new(Arc::new(tx.clone()), 100));
        let probe = build_writer_queue_probe(Arc::clone(&stats));

        // empty: depth 0
        assert_eq!(probe(), 0);

        // 灌 25 條
        for _ in 0..25 {
            tx.try_send(MarketDataMsg::Liquidation {
                ts_ms: 0,
                symbol: "BTCUSDT".to_string(),
                side: "Buy".to_string(),
                qty: 0.0,
                price: 0.0,
            })
            .ok();
        }
        assert_eq!(probe(), 25);
    }
}

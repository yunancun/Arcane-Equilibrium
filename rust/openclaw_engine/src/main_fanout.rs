//! Fan-out task — single WS source → N per-pipeline bounded receivers with
//! ready-barrier gating.
//! 扇出任務 — 單一 WS 源 → N 個 per-pipeline 有界接收端，附 ready barrier。
//!
//! MODULE_NOTE (EN): Extracted from `main.rs` (G1-03 Wave 1). Spawns a tokio
//!   task that:
//!     1. Awaits each pipeline's `ready_rx` (60s barrier timeout) before
//!        starting tick distribution — prevents early ticks from racing past
//!        half-initialised strategies (MAJOR-2 ordered init).
//!     2. Reads `PriceEvent` from the single upstream `event_rx`, wraps in
//!        `Arc`, and `try_send`s to paper/demo/live senders. Bounded channel
//!        (1024) means overflow = tick drop — logged at debug (paper/demo) or
//!        warn (live). 2026-04-15 Fix 4 120s WS-stale watchdog handles the
//!        "sustained drop" case; this fn only handles the fan-out itself.
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1）。啟動 tokio 任務：
//!     1. 60s barrier timeout 內等所有管線 `ready_rx` 完成，再分發 tick
//!        （MAJOR-2 有序初始化，避免 tick 搶跑半初始化的策略）。
//!     2. 從上游 `event_rx` 讀 `PriceEvent`，Arc 包裝後 `try_send` 給
//!        paper/demo/live；通道有界（1024）溢出＝丟 tick（paper/demo 為
//!        debug、live 為 warn）。2026-04-15 Fix 4 120s WS-stale watchdog 處理
//!        「持續丟」情境，本 fn 只負責 fan-out 本身。

use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::{mpsc, oneshot};
use tokio_util::sync::CancellationToken;

/// Spawn the fan-out task.
///
/// EN: Consumes upstream `event_rx` and `{paper,demo,live}_event_tx` (moves),
///   spawns a tokio task that awaits ready barriers then distributes ticks.
///   Drops the per-pipeline senders on shutdown via `None` arm of `recv()`.
/// 中: 接收上游 `event_rx` 與各管線 tx（moves），spawn 任務先等 ready barrier
///   再分發 tick。`recv()` None 分支觸發時 drop 各管線 sender 以優雅關閉。
#[allow(clippy::too_many_arguments)]
pub(crate) fn spawn_fan_out(
    cancel: CancellationToken,
    event_rx: mpsc::Receiver<PriceEvent>,
    paper_event_tx: mpsc::Sender<Arc<PriceEvent>>,
    demo_event_tx: Option<mpsc::Sender<Arc<PriceEvent>>>,
    live_event_tx: Option<mpsc::Sender<Arc<PriceEvent>>>,
    paper_ready_rx: oneshot::Receiver<()>,
    demo_ready_rx: Option<oneshot::Receiver<()>>,
    live_ready_rx: Option<oneshot::Receiver<()>>,
) {
    let paper_tx = paper_event_tx;
    let demo_tx = demo_event_tx;
    let live_tx = live_event_tx;
    let fan_cancel = cancel;
    tokio::spawn(async move {
        let barrier_timeout = tokio::time::Duration::from_secs(60);
        let barrier_result = tokio::time::timeout(barrier_timeout, async {
            let _ = paper_ready_rx.await;
            if let Some(rx) = demo_ready_rx {
                let _ = rx.await;
            }
            if let Some(rx) = live_ready_rx {
                let _ = rx.await;
            }
        })
        .await;

        if barrier_result.is_err() {
            tracing::error!(
                "fan-out: pipeline init timed out after 60s, starting anyway \
                 / 管線初始化超時 60s，仍然啟動扇出"
            );
        } else {
            tracing::info!(
                "fan-out: all pipelines ready, starting tick distribution \
                 / 所有管線就緒，開始 tick 分發"
            );
        }

        let mut event_rx = event_rx;
        loop {
            tokio::select! {
                _ = fan_cancel.cancelled() => break,
                evt = event_rx.recv() => {
                    match evt {
                        Some(price_event) => {
                            let arc_event = Arc::new(price_event);
                            if paper_tx.try_send(Arc::clone(&arc_event)).is_err() {
                                tracing::debug!(
                                    "fan-out: paper pipeline lagging, tick dropped / Paper 管線延遲，tick 已丟棄"
                                );
                            }
                            if let Some(ref dtx) = demo_tx {
                                if dtx.try_send(Arc::clone(&arc_event)).is_err() {
                                    tracing::debug!(
                                        "fan-out: demo pipeline lagging, tick dropped / Demo 管線延遲，tick 已丟棄"
                                    );
                                }
                            }
                            if let Some(ref ltx) = live_tx {
                                if ltx.try_send(arc_event).is_err() {
                                    tracing::warn!(
                                        "fan-out: live pipeline lagging, tick dropped / Live 管線延遲，tick 已丟棄"
                                    );
                                }
                            }
                        }
                        None => break,
                    }
                }
            }
        }
        tracing::info!("fan-out task stopped / 扇出任務已停止");
    });
}

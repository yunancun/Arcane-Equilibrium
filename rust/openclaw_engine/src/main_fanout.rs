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
//!
//!   2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: the live receiver is
//!   now a `LiveEventSenderSlot` (`Arc<RwLock<Option<Sender<...>>>>`) instead
//!   of an owned `Option<Sender<...>>`. Boot can no longer assume the live
//!   pipeline exists — the LiveAuthWatcher rebuilds the live event channel
//!   on every authorization-driven respawn. The slot pattern lets fan-out
//!   read a snapshot of the latest sender per tick: when the watcher writes
//!   a new sender, the next tick lands; when the watcher clears the slot
//!   (teardown), ticks just don't go to live (Demo / Paper / Scanner are
//!   unaffected).
//!
//!   For the boot-time-fixed paper / demo legs we keep the original owned
//!   `Option<Sender<...>>` shape — they never respawn mid-session.
//!
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1）。啟動 tokio 任務：
//!     1. 60s barrier timeout 內等所有管線 `ready_rx` 完成，再分發 tick
//!        （MAJOR-2 有序初始化，避免 tick 搶跑半初始化的策略）。
//!     2. 從上游 `event_rx` 讀 `PriceEvent`，Arc 包裝後 `try_send` 給
//!        paper/demo/live；通道有界（1024）溢出＝丟 tick（paper/demo 為
//!        debug、live 為 warn）。2026-04-15 Fix 4 120s WS-stale watchdog 處理
//!        「持續丟」情境，本 fn 只負責 fan-out 本身。
//!
//!   2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN：live 接收端從 owned
//!   `Option<Sender>` 改為 `LiveEventSenderSlot`（`Arc<RwLock<Option<Sender>>>`）。
//!   boot 不再保證 live 管線存在 — LiveAuthWatcher 每次授權驅動 respawn 都
//!   重建 live 事件通道。Slot pattern 讓 fan-out 每 tick 讀最新 sender 快照：
//!   watcher 寫入新 sender → 下個 tick 落地；watcher 清空（teardown）→
//!   tick 不送 live（Demo / Paper / Scanner 不受影響）。
//!
//!   Paper / Demo legs 保留原 owned `Option<Sender>`：boot 後不中途 respawn。

use openclaw_types::PriceEvent;
use parking_lot::RwLock;
use std::sync::Arc;
use tokio::sync::{mpsc, oneshot};
use tokio_util::sync::CancellationToken;

/// Slot type for the live pipeline event sender. The `LiveAuthWatcher`
/// rotates the inner `Sender` on every authorization-driven respawn /
/// teardown. Fan-out reads a snapshot per tick.
///
/// `parking_lot::RwLock` is used (not `tokio::sync::RwLock`) so the
/// watcher's synchronous spawner closure can write the slot without
/// touching async machinery. Fan-out (async tokio task) holds the read
/// guard for ~1 µs per tick which is well below the threshold where
/// blocking sync primitives become a problem in async contexts.
///
/// Live 管線事件 sender 的 slot 類型。`LiveAuthWatcher` 每次授權驅動的
/// respawn / teardown 都會輪替內層 Sender；fan-out 每個 tick 讀一次快照。
///
/// 採 `parking_lot::RwLock`（非 `tokio::sync::RwLock`）讓 watcher 的同步
/// spawner closure 不繞 async 機械直接寫 slot。fan-out（async tokio task）
/// 每 tick 持讀鎖 ~1 µs，遠低於同步原語在 async context 變成問題的閾值。
pub(crate) type LiveEventSenderSlot = Arc<RwLock<Option<mpsc::Sender<Arc<PriceEvent>>>>>;

/// Spawn the fan-out task.
///
/// EN: Consumes upstream `event_rx`, paper/demo `event_tx` (moves), and a
///   `live_event_slot` shared with `LiveAuthWatcher` (Arc-cloned). Spawns
///   a tokio task that awaits ready barriers then distributes ticks.
///   Drops the per-pipeline senders on shutdown via `None` arm of `recv()`.
///
///   The `live_ready_rx` is also wrapped in a slot
///   (`Arc<RwLock<Option<oneshot::Receiver<()>>>>`) so the watcher can
///   refresh the barrier on respawn — see the watcher's own MODULE_NOTE.
///   When `live_ready_slot` is None at the moment fan-out enters its barrier
///   step, fan-out skips the live arm (consistent with paper / demo's None
///   behaviour) and proceeds.
///
/// 中: 接收上游 `event_rx`、paper/demo 兩條 owned tx（moves）、以及與
///   `LiveAuthWatcher` 共享（Arc clone）的 `live_event_slot`。Spawn 任務先等
///   ready barrier 再分發 tick。`recv()` None 分支觸發時 drop 各管線 sender
///   以優雅關閉。
///
///   `live_ready_rx` 同樣包裝為 slot（`Arc<RwLock<Option<oneshot::Receiver<()>>>>`），
///   讓 watcher 在 respawn 時刷新 barrier — 詳見 watcher 自己的 MODULE_NOTE。
///   fan-out 進入 barrier 步驟時若 slot 為 None 即跳過 live arm（與 paper /
///   demo 的 None 行為一致）。
#[allow(clippy::too_many_arguments)]
pub(crate) fn spawn_fan_out(
    cancel: CancellationToken,
    event_rx: mpsc::Receiver<PriceEvent>,
    paper_event_tx: mpsc::Sender<Arc<PriceEvent>>,
    demo_event_tx: Option<mpsc::Sender<Arc<PriceEvent>>>,
    live_event_slot: LiveEventSenderSlot,
    paper_ready_rx: oneshot::Receiver<()>,
    demo_ready_rx: Option<oneshot::Receiver<()>>,
    live_ready_rx: Option<oneshot::Receiver<()>>,
    // W1 sub-task 3 (E1-γ, 2026-05-11): 額外 panel arm — fan-out 把每 tick 的
    // Arc<PriceEvent> try_send 給 PanelAggregator 的 mpsc。本 arm Optional，
    // None 時 silent skip（panel 未啟用時行為不變）。
    panel_event_tx: Option<mpsc::Sender<Arc<PriceEvent>>>,
) {
    let paper_tx = paper_event_tx;
    let demo_tx = demo_event_tx;
    let live_slot = live_event_slot;
    let panel_tx = panel_event_tx;
    let fan_cancel = cancel;
    tokio::spawn(async move {
        let barrier_timeout = tokio::time::Duration::from_secs(60);
        let barrier_result = tokio::time::timeout(barrier_timeout, async {
            let _ = paper_ready_rx.await;
            if let Some(rx) = demo_ready_rx {
                let _ = rx.await;
            }
            // 2026-04-27: live ready barrier is best-effort. The watcher
            // reseeds the barrier on each respawn but the FIRST live spawn
            // (post-boot) must still drive paper / demo unblocked. Skip
            // the await on None and proceed.
            // 2026-04-27：live ready barrier 為盡力而為。watcher 每次
            // respawn 重新 seed barrier，但首次 live spawn 之前 paper /
            // demo 仍須解除阻塞。None 跳過。
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
                            // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN:
                            // read the live sender slot per-tick. Holding the
                            // RwLock read guard across try_send is fine because
                            // try_send is non-blocking and the watcher only
                            // takes the write lock briefly during respawn /
                            // teardown.
                            //
                            // 2026-04-27：每 tick 讀 live sender slot。
                            // try_send 非阻塞 + watcher 短暫寫鎖 = read guard
                            // 跨 try_send 安全。
                            let live_guard = live_slot.read();
                            if let Some(ref ltx) = *live_guard {
                                if ltx.try_send(Arc::clone(&arc_event)).is_err() {
                                    tracing::warn!(
                                        "fan-out: live pipeline lagging, tick dropped / Live 管線延遲，tick 已丟棄"
                                    );
                                }
                            }
                            // No live consumer (slot == None) is the normal
                            // state when authorization is absent — silent
                            // drop is correct here, demo / paper still see
                            // the tick.
                            // slot == None（無授權）為正常 — 靜默丟棄 live
                            // 對應，demo / paper 仍收到 tick。
                            drop(live_guard);

                            // W1 sub-task 3 (E1-γ, 2026-05-11): panel arm
                            // PanelAggregator 消費 Ticker variant 算 funding/OI panel；
                            // None = panel 未啟用（極早期 boot 或環境停用），silent skip。
                            // try_send 失敗（ch 滿）= panel run loop 卡住，warn 但不阻塞
                            // paper/demo/live tick 流。
                            if let Some(ref ptx) = panel_tx {
                                if ptx.try_send(arc_event).is_err() {
                                    tracing::debug!(
                                        "fan-out: panel pipeline lagging, tick dropped / Panel 管線延遲，tick 已丟棄"
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

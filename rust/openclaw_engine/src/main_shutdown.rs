//! Ordered shutdown sequence — Live → Demo → Paper with slot teardown and
//! socket cleanup.
//! 有序關閉序列 — Live → Demo → Paper，含槽位 teardown 與 socket 清理。
//!
//! MODULE_NOTE (EN): Extracted from `main.rs` (G1-03 Wave 1) for the same
//!   reason as `main_pipelines.rs`. Gets the engine-wide cancel, slot Arcs,
//!   and pipeline handles passed in from `async_main`. Performs:
//!     1. `cancel.cancel()` — fan out engine-wide cancel via parent→child.
//!     2. `live_slot.teardown().await` + `demo_slot.teardown().await` for
//!        deterministic task-handle join (E2 MAJOR #3 fix — without explicit
//!        teardown, slot's task_handles get orphaned and aborted by tokio
//!        runtime drop instead of cleanly joined). Idempotent: LiveAuthWatcher
//!        may have torn Live down already.
//!     3. Join WS handle, IPC handle, Live OS thread, Demo pipeline, Paper
//!        pipeline — all inside a 10s timeout so a stuck child doesn't hang
//!        shutdown forever.
//!     4. Remove IPC socket file from disk (otherwise next boot fails with
//!        EADDRINUSE).
//!
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1），理由同 `main_pipelines.rs`。
//!   從 `async_main` 接收引擎級 cancel、slot Arc、管線 handle。執行：
//!     1. `cancel.cancel()` — 經父→子連動引擎級 cancel。
//!     2. `live_slot.teardown().await` + `demo_slot.teardown().await` 確保
//!        task_handles 確定性 join（E2 MAJOR #3 修復：不顯式 teardown 則槽位
//!        task_handles 變孤兒，被 tokio runtime drop 粗暴中止而非乾淨 join）。
//!        冪等：LiveAuthWatcher 可能已拆 Live。
//!     3. 於 10s timeout 內依序 join WS handle、IPC handle、Live OS 線程、
//!        Demo 管線、Paper 管線 — 卡住的子任務不會無限拖累 shutdown。
//!     4. 移除 IPC socket 檔（否則下次啟動 bind EADDRINUSE）。

use crate::pipeline_slot::PipelineSlot;
use openclaw_engine::config::ConfigManager;
use std::sync::Arc;
use tokio_util::sync::CancellationToken;
use tracing::{error, info};

/// Handles collected for the ordered shutdown.
/// 供有序關閉收集的 handle 組合。
pub(crate) struct ShutdownHandles {
    pub live_slot: Arc<PipelineSlot>,
    pub demo_slot: Arc<PipelineSlot>,
    pub ws_handle: tokio::task::JoinHandle<()>,
    pub ipc_handle: tokio::task::JoinHandle<()>,
    pub live_thread_handle: Option<std::thread::JoinHandle<()>>,
    pub demo_handle: Option<tokio::task::JoinHandle<()>>,
    pub paper_handle: tokio::task::JoinHandle<()>,
}

/// Run the ordered shutdown sequence.
///
/// EN: Cancels engine-wide token, awaits slot teardowns, then drains all
///   pipeline handles under a 10s timeout. Finally removes the IPC socket file.
/// 中: 取消引擎級 token、等待槽位 teardown、於 10s timeout 內排空所有管線
///   handle，最後移除 IPC socket 檔。
pub(crate) async fn run_ordered_shutdown(
    config: &Arc<ConfigManager>,
    cancel: &CancellationToken,
    handles: ShutdownHandles,
) {
    info!("initiating shutdown / 開始關閉序列");

    cancel.cancel();

    // PIPELINE-SLOT-1 Phase 2 (E2 MAJOR #3 fix): explicit slot teardown for
    // deterministic task-handle join. The engine-wide `cancel` above already
    // signals all children (parent→child cascade), but without an explicit
    // `teardown().await` the slot's task_handles are never joined — they get
    // orphaned and then aborted by tokio runtime drop, not a clean shutdown.
    // `teardown()` is idempotent: if the Live slot was already torn down by
    // `LiveAuthWatcher` (Phase 3), calling it again is a no-op (Empty state).
    // Paper is NOT wired through PipelineSlot (Phase 3 deferral). Order matches
    // "Live → Demo → Paper" below: Live slot first, then Demo, then Paper is
    // handled by existing handle-await flow.
    //
    // PIPELINE-SLOT-1 Phase 2（E2 MAJOR #3 修復）：顯式呼叫槽位 teardown 以
    // 確定性 join task handles。上面的引擎級 `cancel` 已經經父→子連動通知所有
    // 子，但若不顯式 `teardown().await`，槽位的 task_handles 永遠不會被 join —
    // 任務變孤兒，最後靠 tokio runtime drop 粗暴中止，稱不上乾淨關閉。
    // `teardown()` 冪等：若 Live 槽位已被 `LiveAuthWatcher`（Phase 3）拆過，
    // 再呼叫即無作用（Empty 狀態）。Paper 尚未接入 PipelineSlot（未來延後）。
    // 順序符合「Live → Demo → Paper」：先拆 Live slot，再拆 Demo，Paper 走
    // 既有 handle-await 流程。
    if let Err(e) = handles.live_slot.teardown().await {
        error!(
            error = %e,
            "live slot teardown failed during shutdown (non-fatal) \
             / 關機時 live 槽 teardown 失敗（非致命）"
        );
    }
    if let Err(e) = handles.demo_slot.teardown().await {
        error!(
            error = %e,
            "demo slot teardown failed during shutdown (non-fatal) \
             / 關機時 demo 槽 teardown 失敗（非致命）"
        );
    }

    let shutdown_timeout = tokio::time::Duration::from_secs(10);
    let _ = tokio::time::timeout(shutdown_timeout, async {
        let _ = handles.ws_handle.await;
        let _ = handles.ipc_handle.await;

        // D17: Join Live OS thread first.
        // D17：先等待 Live OS 線程結束。
        if let Some(th) = handles.live_thread_handle {
            info!("joining live runtime thread / 等待 live runtime 線程結束");
            let _ = th.join();
        }

        // Demo pipeline (tokio task).
        if let Some(dh) = handles.demo_handle {
            info!("draining demo pipeline / 排空 Demo 管線");
            match dh.await {
                Err(e) if e.is_panic() => {
                    error!("demo pipeline panicked during shutdown / Demo 管線關閉時 panic")
                }
                _ => {}
            }
        }

        // Paper pipeline (tokio task).
        info!("draining paper pipeline / 排空 Paper 管線");
        match handles.paper_handle.await {
            Err(e) if e.is_panic() => {
                error!("paper pipeline panicked during shutdown / Paper 管線關閉時 panic")
            }
            _ => {}
        }
    })
    .await;

    // Clean up socket file
    let socket_path = &config.get().ipc_socket_path;
    if std::path::Path::new(socket_path).exists() {
        let _ = tokio::fs::remove_file(socket_path).await;
        info!(
            path = socket_path,
            "socket file cleaned up / 套接字文件已清理"
        );
    }
}

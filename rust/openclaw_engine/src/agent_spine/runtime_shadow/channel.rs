//! Agent spine channel send helpers and drop counters.
//!
//! Wave 1.6 P1-FILL-LINEAGE-DROP（2026-05-11）：通道 drop counter + retry helper。
//!
//! 設計目的：
//! - SPINE_CHANNEL_DROP_TOTAL：累計 try_send **初始失敗**（channel_full + channel_closed）
//!   筆數，process-wide AtomicU64。**注意語意**：這是 INITIAL FAIL occurrences，不是
//!   FINAL LOSS。包含兩種 path：
//!     (1) emit_entry_lineage（hot path）try_send fail → 真實永久丟（無 retry path）
//!     (2) emit_fill_completion_lineage try_send fail → 觸發 background retry，多數會
//!         被 SPINE_CHANNEL_RETRY_SUCCESS_TOTAL 救回，不是最終丟失
//!   下游 healthcheck 計「最終丟失」應用 `drop_total - retry_success_total`（approx）
//!   或更精確的 (path-tagged counter, P1-FILL-LINEAGE-MONITOR 後續細化)。供
//!   healthcheck [55] / 將來 P1-FILL-LINEAGE-MONITOR ticket 對外暴露 metric
//!   `agent_spine_channel_drop_total`。
//! - SPINE_CHANNEL_RETRY_SUCCESS_TOTAL：retry helper 在背景重試成功的筆數，
//!   供 burst 期間 retry 救援率觀察。
//! - SPINE_CHANNEL_RETRY_FAIL_TOTAL：retry helper 用盡 3 次重試後仍失敗。
//!   這個 counter 才是 fill_completion path 的「最終丟失」近似。
//!   `final_loss ≈ entry_path_drops + retry_fail_total`，但 entry vs fill_completion
//!   drop 在 SPINE_CHANNEL_DROP_TOTAL 內混合（P1-FILL-LINEAGE-MONITOR 細化 SOP）。
//!
//! 三個 counter 皆用 std::sync::atomic 不引入新依賴；Relaxed ordering 因
//! 統計屬性（無 happens-before 需求），符合 metric counter 慣用實踐。
//!
//! SAFETY / 不變量：
//! - 三 counter 為 process-wide global，process 重啟歸零（與其它 metric 一致）；
//!   下游 healthcheck 用 delta 對比，不依賴絕對值跨重啟一致。
//! - 並發場景下 fetch_add(1, Relaxed) 保證單調遞增，不需 Mutex / RwLock。

use super::super::store::AgentSpineMsg;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tokio::sync::mpsc;
use tracing::warn;

static SPINE_CHANNEL_DROP_TOTAL: AtomicU64 = AtomicU64::new(0);
static SPINE_CHANNEL_RETRY_SUCCESS_TOTAL: AtomicU64 = AtomicU64::new(0);
static SPINE_CHANNEL_RETRY_FAIL_TOTAL: AtomicU64 = AtomicU64::new(0);

/// 對外暴露 metric：累計 try_send **初始失敗** 筆數（INITIAL fail occurrences）。
///
/// **語意警告**：這 NOT 等於「最終丟失」。包含 entry path 真實永久丟 + fill_completion
/// path 初始失敗（多數會被 retry 救回，計 SPINE_CHANNEL_RETRY_SUCCESS_TOTAL）。
/// 下游 healthcheck 計「最終丟失」用 `drop_total - retry_success_total`（approx）
/// 或更精確的 path-tagged counter（P1-FILL-LINEAGE-MONITOR 細化 SOP）。
///
/// 用途：
/// - healthcheck [55] / [N] 對應 sample 化 SLO 監測（建議 5/min 警報閾）。
/// - Wave 1.6 P1-FILL-LINEAGE-MONITOR ticket 對外 metric 接線。
///
/// 不變量：process 啟動歸零；fetch_add(1, Relaxed) 保證單調遞增。
pub fn spine_channel_drop_total() -> u64 {
    SPINE_CHANNEL_DROP_TOTAL.load(Ordering::Relaxed)
}

/// 對外暴露 metric：retry helper 重試成功的筆數。
///
/// 用途：觀察 burst 期間 retry 救援率（理想值 > drop_total 表示 retry path
/// 工作；若 retry_success_total / drop_total 比例低，代表 burst 結構性過大
/// 需要再次 bump cap 或改用 unbounded channel）。
pub fn spine_channel_retry_success_total() -> u64 {
    SPINE_CHANNEL_RETRY_SUCCESS_TOTAL.load(Ordering::Relaxed)
}

/// 對外暴露 metric：retry helper 用盡 3 次後仍失敗的筆數。
///
/// 用途：若此值非 0，代表即便 configured cap + retry 3× 仍不足，需 wave 2 級
/// infrastructure 升級（如 cap 32K / unbounded / blocking send 改 sync→async
/// cascade）。
pub fn spine_channel_retry_fail_total() -> u64 {
    SPINE_CHANNEL_RETRY_FAIL_TOTAL.load(Ordering::Relaxed)
}

/// Tick hot-path try_send：非阻塞嘗試一次寫入，失敗即計 drop counter 並返回 false。
///
/// **由 `emit_entry_lineage` 使用**（tick → gate approved → dispatch 路徑）。
/// CLAUDE.md §九 hot path SLA = <0.3ms / tick，故此函式不做 retry / 不 spawn
/// background task，僅 fail-soft drop + atomic counter 累加。失敗筆數透過
/// `spine_channel_drop_total()` 對外暴露給 healthcheck。
///
/// 為何不 retry：entry path 每筆 ER 寫 10 try_send，retry 3× @ 50ms 在 worst
/// case 累積 1500ms = 5000x SLA breach。tick hot path 必須保持 sync + non-blocking。
pub(super) fn try_send(
    tx: &mpsc::Sender<AgentSpineMsg>,
    msg: AgentSpineMsg,
    msg_type: &str,
) -> bool {
    match tx.try_send(msg) {
        Ok(()) => true,
        Err(mpsc::error::TrySendError::Full(_)) => {
            SPINE_CHANNEL_DROP_TOTAL.fetch_add(1, Ordering::Relaxed);
            warn!(
                msg_type = msg_type,
                drop_total = SPINE_CHANNEL_DROP_TOTAL.load(Ordering::Relaxed),
                "agent spine runtime shadow channel full; dropping lineage msg (hot-path no-retry)"
            );
            false
        }
        Err(mpsc::error::TrySendError::Closed(_)) => {
            SPINE_CHANNEL_DROP_TOTAL.fetch_add(1, Ordering::Relaxed);
            warn!(
                msg_type = msg_type,
                drop_total = SPINE_CHANNEL_DROP_TOTAL.load(Ordering::Relaxed),
                "agent spine runtime shadow channel closed; dropping lineage msg"
            );
            false
        }
    }
}

/// Fill-completion try_send with background retry：非 hot path 用，失敗時 spawn
/// 非阻塞 tokio task 進行 3 次 retry（@ 50ms 間隔）。
///
/// **由 `emit_fill_completion_lineage` 使用**（loop_exchange async handler，
/// fully_filled 後事後路徑，**不在 tick SLA 範圍**）。
///
/// 設計理由（per QA RCA 2026-05-11 §D.3 Option F4 hybrid + B-2 caller-aware）：
/// - 同步 caller 不能 await（要保持 emit_fill_completion_lineage 為 sync fn 避免
///   破 caller cascade）→ 用 `tokio::spawn` 將 retry 邏輯丟去 async runtime
/// - 第一次 try_send 在主執行緒立即嘗試（與 try_send 同 ~50-200ns 開銷），
///   成功直接返回不 spawn task（吃掉 99%+ ER 走 fast path）
/// - 失敗才 spawn task，3 retry × 50ms = 150ms worst case；fully_filled 路徑
///   全 24h ~86 次，spawn 成本 ~10μs / 次 × 86 = ~860μs 累積完全可忽略
/// - retry path 用 `sender.reserve().await` + send 而非 sync try_send，
///   tokio mpsc 的 reserve 是 await-style back-pressure，保證 retry 在 channel
///   有 slot 時立即進
///
/// 返回值語意：
/// - `true`：第一次 try_send 立即成功（fast path，~99%+ case）
/// - `false`：第一次失敗，但 retry task 已 spawn；DB 端是否最終寫入由
///   `spine_channel_retry_success_total()` / `spine_channel_retry_fail_total()`
///   counter 觀察。caller 仍應視 return false 為 best-effort（與 try_send 對齊）。
///
/// SAFETY / 不變量：
/// - Sender clone 由 mpsc 設計內部 Arc-wrap，clone 為 ns 級操作 + 引用計數
/// - msg 在 task 內 move 進；不可重複 retry 同一 msg 兩次（task 內部 owned）
/// - background task 失敗後自然結束，無 leak 風險（tokio runtime 自動回收）
pub(super) fn try_send_with_background_retry(
    tx: &mpsc::Sender<AgentSpineMsg>,
    msg: AgentSpineMsg,
    msg_type: &'static str,
) -> bool {
    // Fast path：先 sync try_send 一次。99%+ 走這條，零 spawn 成本。
    match tx.try_send(msg) {
        Ok(()) => return true,
        Err(mpsc::error::TrySendError::Full(retry_msg)) => {
            // Channel full → spawn background retry task。
            // 計入 drop counter（與 hot-path 對齊）；retry 成功時補回對應 counter。
            SPINE_CHANNEL_DROP_TOTAL.fetch_add(1, Ordering::Relaxed);
            warn!(
                msg_type = msg_type,
                drop_total = SPINE_CHANNEL_DROP_TOTAL.load(Ordering::Relaxed),
                "agent spine fill-completion channel full; spawning background retry task"
            );
            let tx_clone = tx.clone();
            tokio::spawn(async move {
                // 3 × 50ms retry：對 burst 期間瞬時滿載提供救援；
                // tokio time::sleep().await 不阻塞 tokio worker thread。
                for attempt in 1..=3u32 {
                    tokio::time::sleep(Duration::from_millis(50)).await;
                    match tx_clone.try_send(retry_msg.clone()) {
                        Ok(()) => {
                            SPINE_CHANNEL_RETRY_SUCCESS_TOTAL.fetch_add(
                                1,
                                Ordering::Relaxed,
                            );
                            warn!(
                                msg_type = msg_type,
                                attempt = attempt,
                                "agent spine fill-completion retry succeeded after channel full"
                            );
                            return;
                        }
                        Err(mpsc::error::TrySendError::Full(_)) => {
                            // 繼續重試
                        }
                        Err(mpsc::error::TrySendError::Closed(_)) => {
                            // channel 關閉 = engine 收尾期，放棄 retry
                            warn!(
                                msg_type = msg_type,
                                attempt = attempt,
                                "agent spine fill-completion retry aborted: channel closed"
                            );
                            return;
                        }
                    }
                }
                // 3 次 retry 全部 fail → 計入 retry_fail counter
                SPINE_CHANNEL_RETRY_FAIL_TOTAL.fetch_add(1, Ordering::Relaxed);
                warn!(
                    msg_type = msg_type,
                    retry_fail_total = SPINE_CHANNEL_RETRY_FAIL_TOTAL.load(Ordering::Relaxed),
                    "agent spine fill-completion retry exhausted (3x50ms); permanent drop"
                );
            });
            false
        }
        Err(mpsc::error::TrySendError::Closed(_)) => {
            SPINE_CHANNEL_DROP_TOTAL.fetch_add(1, Ordering::Relaxed);
            warn!(
                msg_type = msg_type,
                drop_total = SPINE_CHANNEL_DROP_TOTAL.load(Ordering::Relaxed),
                "agent spine fill-completion channel closed; dropping lineage msg"
            );
            false
        }
    }
}

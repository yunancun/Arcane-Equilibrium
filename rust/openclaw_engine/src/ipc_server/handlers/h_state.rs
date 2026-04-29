//! H State Gateway IPC handlers — three methods: `query_h_state_full`,
//! `get_h_state_status`, `invalidate_h_state`. PA design plan §4.4 / §6.2,
//! commit `7564d07`.
//!
//! MODULE_NOTE (EN): All three handlers operate on the late-injected
//!   [`HStateCacheSlot`]. When the slot is `None` (DEFAULT-OFF env=0 path
//!   or pre-injection boot window) every handler returns a structured
//!   `gateway_disabled` payload (NOT an error) so Python callers can
//!   render a grey-state without raising.
//!
//!   Observability-only — these handlers must NOT influence trading.
//!   Rust hot-path code that wants H state should query the cache
//!   directly via `Arc<HStateCache>::snapshot()`, not via JSON-RPC.
//!
//!   Phase 1 boundaries:
//!   - `query_h_state_full` returns whatever the poller has (Phase 1
//!     stub fetcher → empty default → `version=0`).
//!   - `invalidate_h_state` is fire-and-forget on Python side; this
//!     handler returns a 2xx-style ack synchronously so JSON-RPC clients
//!     stay happy, but does NOT block the poller.
//!
//! MODULE_NOTE (中)：三個 handler 都操作延後注入的
//!   [`HStateCacheSlot`]。slot 為 `None` 時（DEFAULT-OFF env=0 或注入前
//!   啟動窗口）一律回結構化 `gateway_disabled` payload（**不**回 error），
//!   Python caller 可繪灰燈不報錯。
//!
//!   純 observability — 這三個 handler 不可影響交易。Rust hot-path 想要
//!   H state 應直接 `Arc<HStateCache>::snapshot()`，不走 JSON-RPC。
//!
//!   Phase 1 邊界：
//!   - `query_h_state_full` 回 poller 拿到的東西（Phase 1 stub fetcher
//!     → 空 default → `version=0`）。
//!   - `invalidate_h_state` 在 Python 端是 fire-and-forget；本 handler
//!     同步回 ack 讓 JSON-RPC client 不卡，但不阻塞 poller。

use super::super::slots::HStateCacheSlot;
use super::super::*;
use crate::h_state_cache::poller::{push_invalidation, InvalidationSender};
use crate::h_state_cache::{is_gateway_enabled, HStateSnapshot};

/// `query_h_state_full` IPC — return the full H state snapshot from
/// Rust's local cache. Fail-soft when gateway disabled or cache uninjected.
/// `query_h_state_full` IPC — 回 Rust 本地 cache 的完整 H state snapshot。
/// Gateway 關 / cache 未注入時 fail-soft。
pub(in crate::ipc_server) async fn handle_query_h_state_full(
    id: serde_json::Value,
    cache_slot: &HStateCacheSlot,
) -> JsonRpcResponse {
    let guard = cache_slot.read().await;
    let cache = match guard.as_ref() {
        Some(c) => c,
        None => {
            return gateway_disabled_response(id, "cache not injected");
        }
    };
    let snap: HStateSnapshot = cache.snapshot();
    let staleness_ms = cache.staleness_ms();
    let is_stale = cache.is_stale();
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "version": snap.version,
            "fetched_at_ms": snap.fetched_at_ms,
            "staleness_ms": staleness_ms,
            "is_stale": is_stale,
            "h1": snap.h1,
            "h2": snap.h2,
            "h3": snap.h3,
            "h4": snap.h4,
            "h5": snap.h5,
            "agents": snap.agents,
        }),
    )
}

/// `get_h_state_status` IPC — light health probe payload (no full snapshot).
/// Used by `passive_wait_healthcheck.py [20]` to detect silent-dead poller.
/// `get_h_state_status` IPC — 輕量健檢 payload（不含完整 snapshot）。
/// 給 `passive_wait_healthcheck.py [20]` 偵測 silent-dead poller。
pub(in crate::ipc_server) async fn handle_get_h_state_status(
    id: serde_json::Value,
    cache_slot: &HStateCacheSlot,
) -> JsonRpcResponse {
    let guard = cache_slot.read().await;
    let cache = match guard.as_ref() {
        Some(c) => c,
        None => {
            return gateway_disabled_response(id, "cache not injected");
        }
    };
    let status = cache.build_status(is_gateway_enabled());
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "version": status.version,
            "staleness_ms": status.staleness_ms,
            "is_stale": status.is_stale,
            "poll_attempts": status.poll_attempts,
            "poll_successes": status.poll_successes,
            "poll_failures": status.poll_failures,
            "gateway_enabled": status.gateway_enabled,
        }),
    )
}

/// `invalidate_h_state` IPC — Python pushes a hint that some H state
/// changed; Rust responds by triggering an off-cycle poll.
///
/// Schema (PA §4.2.2): `{ "h_module": "h5", "reason": "claude_call_recorded" }`.
/// Both fields are advisory (logged but ignored by the dedup channel —
/// any push wakes the poller).
///
/// Returns `{"ok": true}` synchronously even when the invalidation
/// channel is dropped (fail-soft) — Python is fire-and-forget and we
/// don't want to surface transient channel errors as JSON-RPC -32603.
///
/// `invalidate_h_state` IPC — Python 推 hint 提示 H state 變化；Rust 立刻
/// 觸發一次 off-cycle poll。
///
/// Schema（PA §4.2.2）：`{ "h_module": "h5", "reason": "..." }`。兩欄位皆
/// advisory（會 log 但不被 dedup channel 用 — 任何 push 都會喚醒 poller）。
///
/// 即使 invalidation channel 已 drop 也同步回 `{"ok": true}`（fail-soft）—
/// Python 是 fire-and-forget，不希望 transient channel 錯誤上拋成 -32603。
pub(in crate::ipc_server) async fn handle_invalidate_h_state(
    id: serde_json::Value,
    params: &serde_json::Value,
    invalidation_tx: &Option<InvalidationSender>,
) -> JsonRpcResponse {
    let h_module = params
        .get("h_module")
        .and_then(|v| v.as_str())
        .unwrap_or("(unspecified)");
    let reason = params
        .get("reason")
        .and_then(|v| v.as_str())
        .unwrap_or("(unspecified)");

    if let Some(tx) = invalidation_tx.as_ref() {
        push_invalidation(tx);
        tracing::debug!(
            h_module = h_module,
            reason = reason,
            "h_state invalidation pushed / 已推送 H state 失效提示"
        );
        JsonRpcResponse::success(
            id,
            serde_json::json!({
                "status": "ok",
                "ok": true,
                "h_module": h_module,
                "reason": reason,
            }),
        )
    } else {
        // Channel absent (env=0 or pre-injection) — log + ack so Python
        // doesn't surface noise.
        // Channel 不存在（env=0 或未注入）— log + ack 讓 Python 不噴噪音。
        tracing::trace!(
            h_module = h_module,
            reason = reason,
            "h_state invalidation no-op (gateway disabled) / 失效提示 no-op（gateway 關）"
        );
        JsonRpcResponse::success(
            id,
            serde_json::json!({
                "status": "gateway_disabled",
                "ok": true,
                "note": "invalidation accepted but ignored (gateway off)",
            }),
        )
    }
}

/// Standard payload returned by query/status when the gateway is off.
/// Shape kept stable so Python callers can branch on `status` field.
/// Gateway 關時 query/status 回的標準 payload。`status` 欄位穩定供 Python
/// 條件分支。
fn gateway_disabled_response(id: serde_json::Value, note: &str) -> JsonRpcResponse {
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "gateway_disabled",
            "version": 0,
            "staleness_ms": 0,
            "is_stale": true,
            "poll_attempts": 0,
            "poll_successes": 0,
            "poll_failures": 0,
            "gateway_enabled": false,
            "note": note,
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::h_state_cache::{
        poller::{make_invalidation_channel, push_invalidation},
        HStateCache, HStateSnapshot,
    };
    use std::sync::Arc;
    use tokio::sync::RwLock;

    fn empty_slot() -> HStateCacheSlot {
        Arc::new(RwLock::new(None))
    }

    fn populated_slot(snap: HStateSnapshot) -> HStateCacheSlot {
        let cache = HStateCache::new_arc();
        cache.store_snapshot(snap, crate::h_state_cache::unix_now_ms());
        Arc::new(RwLock::new(Some(cache)))
    }

    #[tokio::test]
    async fn query_full_uninjected_returns_gateway_disabled_status() {
        let slot = empty_slot();
        let resp = handle_query_h_state_full(serde_json::json!(1), &slot).await;
        assert!(resp.error.is_none());
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "gateway_disabled");
        assert_eq!(r["version"], 0);
    }

    #[tokio::test]
    async fn query_full_injected_returns_snapshot_payload() {
        let snap = HStateSnapshot {
            version: 7,
            ..Default::default()
        };
        let slot = populated_slot(snap);
        let resp = handle_query_h_state_full(serde_json::json!(2), &slot).await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "ok");
        assert_eq!(r["version"], 7);
        assert!(r["is_stale"].as_bool().is_some());
        assert!(r["h1"].is_object());
        assert!(r["agents"].is_object());
    }

    #[tokio::test]
    async fn get_status_uninjected_returns_gateway_disabled() {
        let slot = empty_slot();
        let resp = handle_get_h_state_status(serde_json::json!(3), &slot).await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "gateway_disabled");
        assert_eq!(r["gateway_enabled"], false);
    }

    #[tokio::test]
    async fn get_status_injected_reports_counters() {
        let slot = populated_slot(HStateSnapshot {
            version: 11,
            ..Default::default()
        });
        let resp = handle_get_h_state_status(serde_json::json!(4), &slot).await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "ok");
        assert_eq!(r["version"], 11);
        // poll_successes >= 1 from store_snapshot's bump
        assert!(r["poll_successes"].as_u64().unwrap_or(0) >= 1);
    }

    #[tokio::test]
    async fn invalidate_no_channel_returns_gateway_disabled_ok() {
        let resp = handle_invalidate_h_state(
            serde_json::json!(5),
            &serde_json::json!({"h_module": "h5", "reason": "test"}),
            &None,
        )
        .await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "gateway_disabled");
        assert_eq!(r["ok"], true);
    }

    #[tokio::test]
    async fn invalidate_with_channel_pushes_and_returns_ok() {
        let (tx, mut rx) = make_invalidation_channel();
        // Pre-push so the receiver "saw" the initial 0 already; otherwise
        // the very first changed() returns immediately on the start value.
        // 預先 mark_unchanged 讓 receiver 已見初始 0 — 否則首次 changed()
        // 會立刻命中 start value。
        rx.mark_unchanged();
        let resp = handle_invalidate_h_state(
            serde_json::json!(6),
            &serde_json::json!({"h_module": "h1", "reason": "budget_skip"}),
            &Some(tx),
        )
        .await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "ok");
        assert_eq!(r["ok"], true);
        assert_eq!(r["h_module"], "h1");
        // The watch channel should now have a pending change.
        // watch channel 現在應有 pending 變化。
        let observed =
            tokio::time::timeout(std::time::Duration::from_millis(100), rx.changed()).await;
        assert!(observed.is_ok(), "invalidation should be observable");
    }

    /// Stress test invalidate end-to-end: 100 sequential pushes, channel
    /// dedup naturally collapses them on the receiver side.
    /// 壓力測試 invalidate：連推 100 次，channel 自然 dedup 合併。
    #[tokio::test]
    async fn invalidate_stress_does_not_block() {
        let (tx, _rx) = make_invalidation_channel();
        for i in 0..100 {
            let resp = handle_invalidate_h_state(
                serde_json::json!(i),
                &serde_json::json!({"h_module": "h3", "reason": format!("stress_{i}")}),
                &Some(tx.clone()),
            )
            .await;
            assert!(resp.error.is_none());
            // Manual push as well to mirror push_invalidation site.
            push_invalidation(&tx);
        }
    }
}

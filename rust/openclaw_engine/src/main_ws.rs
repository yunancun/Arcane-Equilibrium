//! Public WS client supervisor — subscribes to topics (kline + publicTrade,
//! or full extended feed) and auto-restarts on unexpected exit.
//! 公有 WS 客戶端監管器 — 訂閱 topic（kline + publicTrade 或完整擴展流）
//! 並在異常退出時自動重啟。
//!
//! MODULE_NOTE (EN): Extracted from `main.rs` (G1-03 Wave 1). Builds initial
//!   subscription list (extended vs minimal based on `enable_extended_ws`)
//!   and spawns the RE-2 supervisor task that owns the `WsClient` instance.
//!   On supervisor restart (attempt ≥1) topics are re-computed from the
//!   current registry snapshot, not the boot-time list — picks up scanner
//!   AddSymbol/RemoveSymbol events that happened before the restart.
//!   Backoff: 5s * 2^min(attempt,4), capped at 60s.
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1）。依 `enable_extended_ws`
//!   構建初始訂閱列表（擴展 vs 精簡），spawn RE-2 supervisor 任務擁有 `WsClient`。
//!   Supervisor 重啟時（attempt ≥1）從當前 registry snapshot 重算 topics，而非
//!   開機時快照 — 吸收重啟前 scanner AddSymbol/RemoveSymbol 變化。退避：
//!   5s * 2^min(attempt,4)，上限 60s。

use openclaw_engine::config::ConfigManager;
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::ws_client::WsClient;
use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::{mpsc, Mutex};
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

#[allow(clippy::type_complexity)]
type WsTopicChangeRelay =
    Arc<Mutex<Option<mpsc::UnboundedSender<openclaw_engine::ws_client::WsTopicChange>>>>;

/// Spawn the public WS supervisor task.
///
/// EN: Computes the initial subscription topic list from `symbol_registry`
///   and `config.enable_extended_ws`, spawns the RE-2 supervisor. Returns
///   the `JoinHandle` so the shutdown sequence can await it.
/// 中: 從 `symbol_registry` 與 `config.enable_extended_ws` 計算初始訂閱列表，
///   啟動 RE-2 supervisor。回傳 `JoinHandle` 供 shutdown 序列 await。
pub(crate) fn spawn_ws_supervisor(
    config: &Arc<ConfigManager>,
    cancel: &CancellationToken,
    symbol_registry: &Arc<SymbolRegistry>,
    current_ws_client_tx: &WsTopicChangeRelay,
    event_tx: mpsc::Sender<PriceEvent>,
) -> tokio::task::JoinHandle<()> {
    let cfg_snapshot = config.get();
    let ws_subscriptions: Vec<String> = if cfg_snapshot.enable_extended_ws {
        let mut topics = Vec::new();
        for sym in symbol_registry.snapshot() {
            for topic in openclaw_engine::multi_interval_topics::full_subscription_list(&sym) {
                topics.push(topic);
            }
        }
        info!(
            topics_per_symbol = 10,
            "extended WS subscriptions / 擴展 WS 訂閱"
        );
        topics
    } else {
        let mut topics = Vec::new();
        for sym in symbol_registry.snapshot() {
            topics.push(format!("kline.1.{sym}"));
            topics.push(format!("publicTrade.{sym}"));
        }
        topics
    };

    // RE-2: Supervisor wrapper — restarts WS on unexpected exit.
    let ws_config = Arc::clone(config);
    let ws_cancel = cancel.clone();
    let initial_topics = ws_subscriptions.clone();
    let registry_for_supervisor = Arc::clone(symbol_registry);
    let relay_for_supervisor = Arc::clone(current_ws_client_tx);
    let extended_ws = cfg_snapshot.enable_extended_ws;
    tokio::spawn(async move {
        let mut supervisor_attempt: u32 = 0;
        loop {
            if ws_cancel.is_cancelled() {
                break;
            }

            let topics: Vec<String> = if supervisor_attempt == 0 {
                initial_topics.clone()
            } else if extended_ws {
                registry_for_supervisor
                    .snapshot()
                    .into_iter()
                    .flat_map(|sym| {
                        openclaw_engine::multi_interval_topics::full_subscription_list(&sym)
                    })
                    .collect()
            } else {
                registry_for_supervisor
                    .snapshot()
                    .into_iter()
                    .flat_map(|sym| {
                        vec![format!("kline.1.{sym}"), format!("publicTrade.{sym}")]
                    })
                    .collect()
            };

            let mut ws_client =
                WsClient::new(Arc::clone(&ws_config), event_tx.clone(), ws_cancel.clone());
            for topic in &topics {
                ws_client.subscribe(topic.clone());
            }
            let inner_tx = ws_client.with_topic_change_channel();
            *relay_for_supervisor.lock().await = Some(inner_tx);

            ws_client.run().await;

            *relay_for_supervisor.lock().await = None;

            if ws_cancel.is_cancelled() {
                break;
            }

            supervisor_attempt = supervisor_attempt.saturating_add(1);
            let delay_ms = std::cmp::min(
                5000_u64.saturating_mul(2_u64.saturating_pow(supervisor_attempt.min(4))),
                60_000,
            );
            warn!(
                delay_ms = delay_ms,
                attempt = supervisor_attempt,
                "WS supervisor restarting / WS 監管器重啟"
            );
            tokio::select! {
                _ = ws_cancel.cancelled() => break,
                _ = tokio::time::sleep(std::time::Duration::from_millis(delay_ms)) => {},
            }
        }
    })
}

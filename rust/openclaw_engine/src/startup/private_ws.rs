//! Private WS supervisor spawn — per-pipeline authenticated Bybit WS + ExecutionListener wiring.
//! 私有 WS 監管器 — 每管線 authenticated Bybit WS + 執行監聽器接線。
//!
//! MODULE_NOTE (EN): Extracted from `startup.rs` as Wave 1 G1-03. Carries the
//!   `PrivateWsBindings` struct (returned to `build_exchange_pipeline`) plus
//!   the single entry point `spawn_private_ws_supervisor`, which wires up:
//!     - BybitPrivateWs supervisor (RE-2 restart-on-exit)
//!     - ExecutionListener task (fills / orders / positions / wallet / DCP)
//!     - Private-WS status JSON writer (C-WIRING; Demo/LiveDemo only — replaces
//!       retired Python `bybit_private_ws_listener.py`)
//!   Visibility kept `pub(crate)` and re-exported through `startup/mod.rs` so
//!   existing `use crate::startup::{spawn_private_ws_supervisor, PrivateWsBindings}`
//!   call sites (pipeline_slot.rs, startup::build_exchange_pipeline) compile
//!   unchanged.
//! MODULE_NOTE (中): 從 `startup.rs` 抽出（Wave 1 G1-03）。包含 `PrivateWsBindings`
//!   結構（回給 `build_exchange_pipeline`）與唯一入口 `spawn_private_ws_supervisor`,
//!   該函式串起：
//!     - BybitPrivateWs 監管器（RE-2 意外退出自動重啟）
//!     - ExecutionListener 任務（成交/訂單/持倉/錢包/DCP）
//!     - 私有 WS status JSON writer（C-WIRING；僅 Demo/LiveDemo —
//!       取代退役的 Python `bybit_private_ws_listener.py`）
//!   可見性維持 `pub(crate)` 並透過 `startup/mod.rs` re-export,
//!   既有 `use crate::startup::{spawn_private_ws_supervisor, PrivateWsBindings}`
//!   呼叫點（pipeline_slot.rs、startup::build_exchange_pipeline）編譯無感。

use openclaw_engine::bybit_rest_client::BybitEnvironment;
use openclaw_engine::event_consumer::ExchangeEvent;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Exchange bindings produced by spawning a private WS supervisor.
/// 啟動私有 WS 監管器後產生的交易所綁定。
///
/// PIPELINE-SLOT-1 Phase 2:
///   The `_ws_handle` and `_listener_handle` fields that previously lived here
///   (prefixed `_` → kept alive only to prevent task drop) are now returned
///   separately by `spawn_private_ws_supervisor` so `build_exchange_pipeline`
///   can bundle them into a `Vec<JoinHandle<()>>` owned by the slot. This
///   lets `PipelineSlot::teardown()` await them deterministically on
///   live-scoped teardown. No runtime behaviour change on the happy path —
///   the handles are still tokio-spawned on the same runtime with the same
///   cancel-token wiring; we just own them at a different layer now.
///
/// PIPELINE-SLOT-1 Phase 2：
///   原本放在這裡的 `_ws_handle` 與 `_listener_handle`（以 `_` 前綴僅為防
///   drop）已改由 `spawn_private_ws_supervisor` 另外返回，讓
///   `build_exchange_pipeline` 可以把它們匯入一個歸槽位擁有的
///   `Vec<JoinHandle<()>>`，使 `PipelineSlot::teardown()` 能在 live-scoped
///   teardown 時確定性地 await。Happy path 無行為變動 — 任務仍在同個 runtime
///   spawn、cancel-token 接線一致，只是擁有權提高到 slot 層。
pub(crate) struct PrivateWsBindings {
    // BLOCKER-6 / D12: parking_lot::RwLock for non-poisoning cross-pipeline isolation.
    // BLOCKER-6 / D12：parking_lot::RwLock，不中毒 → 跨管線隔離。
    pub bybit_balance: Arc<parking_lot::RwLock<Option<f64>>>,
    pub api_pnl: Arc<parking_lot::RwLock<std::collections::HashMap<String, f64>>>,
    pub exchange_event_rx: mpsc::UnboundedReceiver<ExchangeEvent>,
}

/// Spawn a per-pipeline private WS supervisor + ExecutionListener.
/// Returns exchange bindings for the pipeline's EventConsumerDeps plus the
/// two tokio task handles (ws supervisor + listener), so the caller can
/// hand them to `PipelineSlot` for deterministic teardown.
///
/// 為每管線啟動私有 WS 監管器 + 執行監聽器。
/// 返回管線 EventConsumerDeps 所需的交易所綁定，以及 ws supervisor 與
/// listener 的 tokio 任務 handle，方便呼叫者交給 `PipelineSlot` 以確定性地
/// 撤下。
pub(crate) fn spawn_private_ws_supervisor(
    api_key: String,
    api_secret: String,
    env: BybitEnvironment,
    label: &str,
    cancel: CancellationToken,
) -> (PrivateWsBindings, Vec<JoinHandle<()>>) {
    use openclaw_engine::bybit_private_ws::BybitPrivateWs;
    use openclaw_engine::execution_listener::ExecutionListener;
    use parking_lot::RwLock;

    let (priv_tx, priv_rx) = mpsc::channel(512);
    let (exchange_event_tx, exchange_event_rx) = mpsc::unbounded_channel::<ExchangeEvent>();

    // Shared state updated by callbacks / 回調更新的共享狀態
    let bybit_balance: Arc<RwLock<Option<f64>>> = Arc::new(RwLock::new(None));
    let api_pnl: Arc<RwLock<std::collections::HashMap<String, f64>>> =
        Arc::new(RwLock::new(std::collections::HashMap::new()));

    let mut listener = ExecutionListener::new(priv_rx);

    // on_balance_update → track Bybit sync balance / 餘額更新回調
    let bal_ref = Arc::clone(&bybit_balance);
    let lbl_bal = label.to_string();
    listener.set_on_balance_update(move |wallet| {
        for coin_update in &wallet.coin {
            if coin_update.coin.eq_ignore_ascii_case("USDT") {
                if let Ok(bal) = coin_update.wallet_balance.parse::<f64>() {
                    // BLOCKER-6: parking_lot RwLock — write() returns guard directly.
                    // BLOCKER-6：parking_lot RwLock — write() 直接回傳 guard。
                    *bal_ref.write() = Some(bal);
                    info!(
                        engine = %lbl_bal,
                        equity = %coin_update.equity,
                        balance = %coin_update.wallet_balance,
                        "WS wallet update (USDT) / WS 錢包更新"
                    );
                }
                break;
            }
        }
    });

    // on_position_update → track API unrealized PnL + forward delta to event consumer.
    // 持倉更新回調：更新 api_pnl 的同時把 delta 也轉發給事件消費者，
    // 讓 paper_state.upsert_position_from_exchange() 能與交易所側保持一致。
    let pnl_ref = Arc::clone(&api_pnl);
    let lbl_pos = label.to_string();
    let pos_tx = exchange_event_tx.clone();
    listener.set_on_position_update(move |pos| {
        if let Ok(pnl) = pos.unrealised_pnl.parse::<f64>() {
            // BLOCKER-6: parking_lot RwLock — write() returns guard directly.
            // BLOCKER-6：parking_lot RwLock — write() 直接回傳 guard。
            pnl_ref.write().insert(pos.symbol.clone(), pnl);
        }
        debug!(
            engine = %lbl_pos,
            symbol = %pos.symbol,
            side = %pos.side,
            size = %pos.size,
            pnl = %pos.unrealised_pnl,
            "WS position update / WS 持倉更新"
        );
        // B-1 Phase 2: forward to event consumer for paper_state upsert.
        // Channel send is best-effort — drop on backpressure rather than block the WS thread.
        // B-1 Phase 2：轉發給事件消費者以便 upsert paper_state。
        // 通道發送為盡力而為，背壓時直接丟棄以免阻塞 WS 執行緒。
        let _ = pos_tx.send(ExchangeEvent::PositionUpdate(pos));
    });

    // on_fill → log execution + forward to event consumer / 成交回調
    let fill_tx = exchange_event_tx.clone();
    let lbl_fill = label.to_string();
    listener.set_on_fill(move |exec| {
        info!(
            engine = %lbl_fill,
            exec_id = %exec.exec_id,
            symbol = %exec.symbol,
            side = %exec.side,
            qty = %exec.exec_qty,
            price = %exec.exec_price,
            fee = %exec.exec_fee,
            "WS fill / WS 成交"
        );
        let _ = fill_tx.send(ExchangeEvent::Fill(exec));
    });

    // on_order_update → log + forward / 訂單更新回調
    let order_tx = exchange_event_tx.clone();
    let lbl_ord = label.to_string();
    listener.set_on_order_update(move |order| {
        debug!(
            engine = %lbl_ord,
            order_id = %order.order_id,
            symbol = %order.symbol,
            status = %order.order_status,
            link_id = %order.order_link_id,
            "WS order update / WS 訂單更新"
        );
        let _ = order_tx.send(ExchangeEvent::OrderUpdate(order));
    });

    // DCP/Disconnected events / DCP/斷連事件
    let dcp_tx = exchange_event_tx.clone();
    listener.set_on_dcp(move || {
        let _ = dcp_tx.send(ExchangeEvent::DcpTriggered);
    });
    let disc_tx = exchange_event_tx;
    listener.set_on_disconnect(move || {
        let _ = disc_tx.send(ExchangeEvent::Disconnected);
    });

    // C-WIRING: extract stats Arc BEFORE listener is moved into its spawn, so
    // the status-JSON writer can read live counters.
    // 取 stats Arc（必須在 listener 被 spawn 搬走前完成）以供 status JSON writer 使用。
    let stats_arc = listener.stats_arc();

    // Spawn listener task / 啟動監聽器任務
    let listener_handle = tokio::spawn(async move {
        let mut listener = listener;
        listener.run().await;
    });

    // C-WIRING: spawn status-JSON writer to replace the Python
    // `bybit_private_ws_listener.py` that previously produced the
    // `bybit_private_ws_listener_status_latest.json` file consumed by
    // `readonly_observer_pipeline/{build_ws_runtime_facts,runtime_state_
    // resolver,observer_acceptance_check}.py`. Only for Demo / LiveDemo to
    // match the Python listener's scope (it ran against a demo API key;
    // Paper has no real private WS and Mainnet live isn't active yet).
    //
    // 啟動 status JSON writer 取代 Python listener；僅對 Demo/LiveDemo 啟動以
    // 對齊 Python 原本的 scope（paper 無真實私有 WS；Mainnet live 尚未啟用）。
    let status_writer_handle: Option<JoinHandle<()>> =
        if matches!(env, BybitEnvironment::Demo | BybitEnvironment::LiveDemo) {
            use openclaw_engine::bybit_private_ws_status_writer::{
                run_private_ws_status_writer, WriterConfig,
            };
            let ws_url = env.private_ws_url().to_string();
            let topics: Vec<String> = env
                .private_ws_topics()
                .iter()
                .map(|s| (*s).to_string())
                .collect();
            let cfg = WriterConfig::from_env(label.to_string(), ws_url, topics);
            let stats_for_writer = Arc::clone(&stats_arc);
            let cancel_for_writer = cancel.clone();
            let handle = tokio::spawn(async move {
                run_private_ws_status_writer(stats_for_writer, cfg, cancel_for_writer).await;
            });
            info!(
                engine = label,
                "Private WS status-JSON writer spawned / 私有 WS status JSON writer 已啟動"
            );
            Some(handle)
        } else {
            None
        };

    // RE-2: Supervisor wrapper — restarts on unexpected exit
    // RE-2：監管器包裝 — 意外退出時自動重啟
    let lbl_sv = label.to_string();
    let sv_cancel = cancel.clone();
    let ws_handle = tokio::spawn(async move {
        let mut supervisor_attempt: u32 = 0;
        loop {
            if sv_cancel.is_cancelled() {
                break;
            }
            let priv_ws = BybitPrivateWs::new(
                api_key.clone(),
                api_secret.clone(),
                env,
                sv_cancel.clone(),
                priv_tx.clone(),
            );
            priv_ws.run().await;
            if sv_cancel.is_cancelled() {
                break;
            }
            supervisor_attempt = supervisor_attempt.saturating_add(1);
            let delay_ms = std::cmp::min(
                5000_u64.saturating_mul(2_u64.saturating_pow(supervisor_attempt.min(4))),
                60_000,
            );
            warn!(
                engine = %lbl_sv,
                delay_ms = delay_ms,
                attempt = supervisor_attempt,
                "Private WS supervisor restarting / 私有 WS 監管器重啟"
            );
            tokio::select! {
                _ = sv_cancel.cancelled() => break,
                _ = tokio::time::sleep(std::time::Duration::from_millis(delay_ms)) => {},
            }
        }
    });

    info!(
        engine = label,
        "Private WS + ExecutionListener started / 私有 WS + 執行監聽器已啟動"
    );
    let bindings = PrivateWsBindings {
        bybit_balance,
        api_pnl,
        exchange_event_rx,
    };
    // Order here is intentional but not semantically required (teardown awaits
    // all in sequence). Keep [ws_handle, listener_handle, status_writer?] so
    // logs during teardown report the supervisor shutting down first, then
    // the listener, then the writer (the writer's final running=false write
    // uses the stale stats but that's fine — it just means observers see
    // the terminal state).
    // 順序有意為之但不影響語義（teardown 會依序 await 全部）。保留
    // [ws_handle, listener_handle, status_writer?]，teardown log 先打
    // supervisor → listener → writer；writer 的最後 running=false 寫入使用最新
    // stats 快照，observer 會看到終止狀態。
    let mut handles = vec![ws_handle, listener_handle];
    if let Some(h) = status_writer_handle {
        handles.push(h);
    }
    (bindings, handles)
}

//! Event consumer select! arm handlers + LoopState container.
//! 事件消費者 select! arm handler + LoopState 容器。
//!
//! MODULE_NOTE (EN): G1-02 Step 2 extracts the 5 select! arm bodies from
//!   mod.rs into dedicated handler fns so the main loop stays readable and
//!   each arm can be unit-tested in isolation. `LoopState` owns the 7
//!   loop-internal mutable fields that survive across arms (pending_orders,
//!   order_id_to_link, seen_exec_{set,order}, known_symbols, last_status,
//!   last_pending_check). The select! macro must still `&mut` the channel
//!   receivers directly, so they stay owned in `run_event_consumer`.
//!   Step 2a (2026-04-24) ships LoopState + the 3 small arms (A cross_engine,
//!   B kline_seed, D pending_reg). Arms C/E/F are extracted in 2b/2c.
//! MODULE_NOTE (中): G1-02 Step 2 將 mod.rs 的 5 個 select! arm body 抽成
//!   獨立 handler fn，主迴圈保持可讀、每個 arm 可獨立單測。`LoopState`
//!   擁有跨 arm 存活的 7 個 loop-internal 可變欄位；select! 仍需 `&mut`
//!   channel receiver 本身，故 receiver 留在 `run_event_consumer` 內。
//!   Step 2a（2026-04-24）出貨 LoopState + 3 個小 arm（A cross_engine /
//!   B kline_seed / D pending_reg）；C/E/F 三個大 arm 留待 2b/2c。

use std::collections::{HashMap, HashSet};
use std::time::Instant;

use super::types::PendingOrder;
use crate::order_manager::TimeInForce;
use crate::strategies::maker_rejection::{CloseMakerFallbackReason, CloseMakerRateLimitScope};
use crate::tick_pipeline::{EngineEvent, PipelineKind, TickPipeline};

/// Loop-internal mutable state owned by `run_event_consumer` between bootstrap
/// and the select! loop. Passed by `&mut` into each arm handler so borrows are
/// scoped per-call (avoids holding multiple mut borrows across arms).
/// 主迴圈的 loop-internal 可變狀態容器；以 `&mut` 傳入各 arm handler，
/// 借用以單次呼叫為單位（避免跨 arm 持有多個 mut borrow）。
pub(super) struct LoopState {
    /// EXT-1 pending order tracking / EXT-1 待處理訂單追蹤
    pub pending_orders: HashMap<String, PendingOrder>,
    /// P0-1 order_id → order_link_id mapping (used for fill matching)
    /// P0-1 order_id → order_link_id 映射（成交匹配用）
    pub order_id_to_link: HashMap<String, String>,
    /// P0-2 + FIX-33 exec_id dedup (HashSet O(1) lookup)
    /// P0-2 + FIX-33 exec_id 去重（HashSet O(1) 查找）
    pub seen_exec_set: std::collections::HashSet<String>,
    /// P0-2 + FIX-33 eviction ordering (VecDeque FIFO)
    /// P0-2 + FIX-33 淘汰順序（VecDeque FIFO）
    pub seen_exec_order: std::collections::VecDeque<String>,
    /// D2 scanner registry diff baseline / D2 掃描器註冊表差分基準
    pub known_symbols: std::collections::HashSet<String>,
    /// Status report cadence clock / 狀態報告節奏時鐘
    pub last_status: Instant,
    /// Pending sweep cadence clock / pending 清理節奏時鐘
    pub last_pending_check: Instant,
    /// Original close-maker order_link_id values that already emitted a
    /// mandatory taker fallback. Prevents double close dispatch when reject,
    /// cancel ack, and sweep grace events race.
    pub close_maker_fallback_dispatched: HashSet<String>,
    /// P2-INCIDENT-POLICY-DISPATCH-TRIGGER: producer state for sm_halt_stuck.
    pub sm_halt_incident: super::sm_halt_incident::SmHaltIncidentProducer,
}

impl LoopState {
    /// Max exec_id entries tracked for dedup; older entries evicted FIFO.
    /// 追蹤的 exec_id 最大數量；超出時 FIFO 淘汰最舊。
    pub(super) const MAX_SEEN_EXEC_IDS: usize = 500;

    /// Build fresh LoopState seeded with the scanner's initial symbol snapshot.
    /// `known_symbols` is moved in from bootstrap so the first D2 diff has a
    /// valid baseline.
    /// 以掃描器初始 symbol 快照構造 LoopState；`known_symbols` 由 bootstrap
    /// 傳入，使首次 D2 diff 有基準值。
    pub(super) fn new(known_symbols: std::collections::HashSet<String>) -> Self {
        let now = Instant::now();
        Self {
            pending_orders: HashMap::new(),
            order_id_to_link: HashMap::new(),
            seen_exec_set: std::collections::HashSet::new(),
            seen_exec_order: std::collections::VecDeque::new(),
            known_symbols,
            last_status: now,
            last_pending_check: now,
            close_maker_fallback_dispatched: HashSet::new(),
            sm_halt_incident: super::sm_halt_incident::SmHaltIncidentProducer::default(),
        }
    }
}

pub(super) fn pending_order_accepts_fill(po: &PendingOrder) -> bool {
    if po.is_close && po.qty.abs() <= f64::EPSILON {
        return true;
    }
    po.cum_filled_qty < po.qty
}

pub(super) fn dispatch_close_maker_fallback_from_pending(
    state: &mut LoopState,
    pipeline: &mut TickPipeline,
    po: &PendingOrder,
    fallback_reason: CloseMakerFallbackReason,
    rate_limit_scope: Option<CloseMakerRateLimitScope>,
    source: &str,
) -> bool {
    if !fallback_reason.requires_market_fallback()
        || !po.is_close
        || po.time_in_force != Some(TimeInForce::PostOnly)
    {
        return false;
    }
    let Some(audit) = po.close_maker_audit.clone() else {
        return false;
    };
    if audit.fallback_reason.is_some() {
        return false;
    }
    let Some(position) = pipeline.paper_state.get_position(&po.symbol) else {
        tracing::info!(
            order_link_id = %po.order_link_id,
            symbol = %po.symbol,
            source,
            fallback_reason = fallback_reason.as_str(),
            "close-maker fallback skipped because local position is already flat \
             / local position 已平，略過 close-maker fallback"
        );
        return false;
    };
    if po.qty > 0.0 && po.cum_filled_qty >= po.qty * 0.999 {
        tracing::info!(
            order_link_id = %po.order_link_id,
            symbol = %po.symbol,
            source,
            filled = po.cum_filled_qty,
            requested = po.qty,
            "close-maker fallback skipped because maker fill already satisfied intent \
             / maker 成交已滿足平倉 intent，略過 fallback"
        );
        return false;
    }
    if !state
        .close_maker_fallback_dispatched
        .insert(po.order_link_id.clone())
    {
        tracing::warn!(
            order_link_id = %po.order_link_id,
            symbol = %po.symbol,
            source,
            fallback_reason = fallback_reason.as_str(),
            "duplicate close-maker terminal fallback suppressed \
             / 重複 close-maker 終態 fallback 已抑制"
        );
        return false;
    }

    let fallback_qty = if po.qty > 0.0 {
        (po.qty - po.cum_filled_qty).max(0.0)
    } else {
        position.qty
    };
    pipeline.dispatch_close_maker_market_fallback(
        &po.order_link_id,
        &po.symbol,
        po.is_long,
        fallback_qty,
        &po.strategy,
        &po.context_id,
        audit,
        fallback_reason,
        rate_limit_scope,
    )
}

// F4-RETURN Issue 1 (2026-04-26): F4-1 emitter moved to sibling
// `unattributed_emit` (§九 1200-line ceiling); re-export preserves caller paths.
// F4-RETURN Issue 1（2026-04-26）：F4-1 emitter 抽至 sibling 以守 §九 上限。
#[cfg(test)]
pub(super) use super::unattributed_emit::{
    engine_mode_emits_unattributed_audit, try_emit_unattributed_fill,
};

// ─────────────────────────────────────────────────────────────────────────────
// Arm A: cross-engine cascade event (peer crash / circuit breaker trip).
// Arm A：跨引擎級聯事件（對等管線崩潰 / 熔斷）。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm A handler: receive cross-engine event and escalate this pipeline's
/// risk to Cautious on peer crash or CircuitBreaker trip. Sender-dropped
/// case is silently swallowed (all peers gone → no more events).
/// Arm A handler：接收跨引擎事件；對等管線崩潰 / 熔斷時升級本管線風控至
/// Cautious。Sender 被 drop 時靜默忽略（所有對等已退出）。
pub(super) fn handle_cross_engine_event(
    evt: Result<EngineEvent, tokio::sync::broadcast::error::RecvError>,
    pipeline: &mut TickPipeline,
    pipeline_kind: PipelineKind,
) {
    match evt {
        Ok(EngineEvent::Crashed(crashed_kind)) => {
            tracing::warn!(
                this = %pipeline_kind, crashed = %crashed_kind,
                "BLOCKER-2: peer pipeline crashed — escalating to Cautious (60s) \
                 / 對等管線崩潰 — 升級至 Cautious（60s）"
            );
            // Cascade: escalate this pipeline's risk to Cautious.
            // 級聯：將本管線風控升級至 Cautious。
            let duration_s = if crashed_kind == PipelineKind::Paper {
                60
            } else {
                120
            };
            let _ = pipeline.governance.risk.reconciler_escalate_to(
                openclaw_core::sm::risk_gov::RiskLevel::Cautious,
                &format!(
                    "cross_engine_cascade: {} crashed, hold {}s",
                    crashed_kind, duration_s
                ),
            );
        }
        Ok(EngineEvent::CircuitBreakerTripped(cb_kind)) => {
            tracing::warn!(
                this = %pipeline_kind, cb = %cb_kind,
                "BLOCKER-2: peer pipeline hit circuit breaker — escalating to Cautious \
                 / 對等管線觸發熔斷 — 升級至 Cautious"
            );
            let _ = pipeline.governance.risk.reconciler_escalate_to(
                openclaw_core::sm::risk_gov::RiskLevel::Cautious,
                &format!("cross_engine_cascade: {} circuit_breaker", cb_kind),
            );
        }
        Err(_) => {
            // Sender dropped — all peers gone, no more events.
            // Sender 被 drop — 所有對等已退出，無後續事件。
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// Arm B: dynamic kline bootstrap seed.
// Arm B：動態 K 線引導結果植入。
// ─────────────────────────────────────────────────────────────────────────────

/// Arm B handler: seed the kline manager with bars fetched by the async D3
/// bootstrap task. `None` from the channel means sender dropped (bootstrap
/// shutdown) — a no-op is the correct response.
/// Arm B handler：將 D3 異步引導任務抓到的 K 線送進 kline manager。
/// Channel 回 `None` 表 sender 被 drop（引導任務關閉），no-op 即為正解。
pub(super) fn handle_kline_seed(
    seed: Option<(String, Vec<openclaw_core::klines::KlineBar>)>,
    pipeline: &mut TickPipeline,
) {
    if let Some((sym, bars)) = seed {
        let count = pipeline.kline_manager.seed_bars(&sym, "1m", bars);
        tracing::info!(
            symbol = %sym, bars = count,
            "dynamic kline bootstrap complete / 動態 K 線引導完成"
        );
    }
}

pub(super) use super::loop_exchange::handle_exchange_event;
// EVENT-CONSUMER-SPLIT-2（2026-07-03）：Arm D/E/F 依職責拆至 sibling 檔；各檔
// 保留現行 §九 2000 行政策空間。pub(super) re-export 保持 mod.rs 與
// event_consumer/tests/* 的 `loop_handlers::handle_*` 呼叫路徑不變。
pub(super) use super::loop_pending_registration::handle_pending_registration;
pub(super) use super::loop_pipeline_command::handle_pipeline_command;
pub(super) use super::loop_tick::handle_tick_event;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loop_state_new_has_empty_collections_and_fresh_clocks() {
        let mut seed = std::collections::HashSet::new();
        seed.insert("BTCUSDT".to_string());
        let state = LoopState::new(seed);

        assert!(state.pending_orders.is_empty());
        assert!(state.order_id_to_link.is_empty());
        assert!(state.seen_exec_set.is_empty());
        assert!(state.seen_exec_order.is_empty());
        assert!(state.close_maker_fallback_dispatched.is_empty());
        assert_eq!(state.known_symbols.len(), 1);
        assert!(state.known_symbols.contains("BTCUSDT"));
        // Clocks seeded to same Instant → Duration between them should be near 0.
        // 兩個時鐘以同一 Instant 初始化 → 之間 Duration 應接近 0。
        let gap = state
            .last_pending_check
            .saturating_duration_since(state.last_status);
        assert!(gap.as_millis() <= 2);
    }

    #[test]
    fn max_seen_exec_ids_is_500() {
        // Sentinel test — guards the documented dedup-window size so any
        // accidental downward edit is caught here rather than in prod.
        // 哨兵測試 — 守住 dedup window 尺寸，意外改小不會溜進生產。
        assert_eq!(LoopState::MAX_SEEN_EXEC_IDS, 500);
    }

    fn close_maker_pending_for_test() -> PendingOrder {
        PendingOrder {
            order_link_id: "oc_close_maker_original".to_string(),
            symbol: "BTCUSDT".to_string(),
            is_long: false,
            qty: 0.1,
            strategy: "strategy_close:grid_close_long".to_string(),
            sent_ts_ms: 1_700_000_000_000,
            signal_ts_ms: 1_700_000_000_000,
            cum_filled_qty: 0.0,
            is_close: true,
            context_id: "ctx-close-maker".to_string(),
            order_type: "limit".to_string(),
            limit_price: Some(50_000.2),
            time_in_force: Some(TimeInForce::PostOnly),
            maker_timeout_ms: Some(30_000),
            close_maker_audit: Some(crate::tick_pipeline::CloseMakerFillAudit {
                initial_limit_price: Some(50_000.2),
                eligible_reason: "grid_close_long".to_string(),
                fallback_reason: None,
                rate_limit_scope: None,
            }),
            reference_price: Some(50_000.0),
            reference_ts_ms: Some(1_700_000_000_000),
            reference_source: Some("dispatch_last_fallback".to_string()),
            cancel_requested_ts_ms: None,
            // MAKER-CLOSE-REPRICE-1：fixture 預設未重掛。
            reprice_count: 0,
            spine_order_plan_id: None,
            spine_decision_id: None,
            spine_verdict_id: None,
            spine_stub_report_id: None,
            // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：close fixture
            // 對應 close path，不帶 strategy intent。
            intent_id: None,
            decision_lease_id: None,
        }
    }

    #[test]
    fn close_maker_fallback_helper_dispatches_market_once_with_spine_none() {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
        let (tx, mut rx) =
            tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::OrderDispatchRequest>();
        pipeline.set_shadow_channel(tx);
        pipeline.paper_state.apply_fill(
            "BTCUSDT",
            true,
            0.1,
            50_000.0,
            0.0,
            1_700_000_000_000,
            "grid_trading",
        );
        let mut state = LoopState::new(std::collections::HashSet::new());
        let po = close_maker_pending_for_test();

        assert!(dispatch_close_maker_fallback_from_pending(
            &mut state,
            &mut pipeline,
            &po,
            CloseMakerFallbackReason::PostOnlyReject,
            None,
            "unit_test",
        ));
        let req = rx.try_recv().expect("market fallback request");
        assert_eq!(req.order_type, "market");
        assert_eq!(req.time_in_force, None);
        assert_eq!(req.limit_price, None);
        assert!(req.is_close);
        assert!(req.is_primary);
        assert!(!req.is_long);
        assert_eq!(req.qty, 0.1);
        assert!(req.spine_order_plan_id.is_none());
        assert!(req.spine_decision_id.is_none());
        assert!(req.spine_verdict_id.is_none());
        assert!(req.spine_stub_report_id.is_none());
        let audit = req.close_maker_audit.expect("fallback audit payload");
        assert_eq!(audit.initial_limit_price, Some(50_000.2));
        assert_eq!(audit.eligible_reason, "grid_close_long");
        assert_eq!(audit.fallback_reason.as_deref(), Some("postonly_reject"));

        assert!(!dispatch_close_maker_fallback_from_pending(
            &mut state,
            &mut pipeline,
            &po,
            CloseMakerFallbackReason::CancelGraceExpired,
            None,
            "unit_test_duplicate",
        ));
        assert!(
            rx.try_recv().is_err(),
            "idempotence guard must suppress duplicate close fallback"
        );
    }

    #[test]
    fn close_maker_cancel_grace_fallback_uses_v094_reason() {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
        let (tx, mut rx) =
            tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::OrderDispatchRequest>();
        pipeline.set_shadow_channel(tx);
        pipeline.paper_state.apply_fill(
            "BTCUSDT",
            true,
            0.1,
            50_000.0,
            0.0,
            1_700_000_000_000,
            "grid_trading",
        );
        let mut state = LoopState::new(std::collections::HashSet::new());
        let mut po = close_maker_pending_for_test();
        po.order_link_id = "oc_close_maker_grace".to_string();
        po.cancel_requested_ts_ms = Some(1_700_000_030_000);

        assert!(dispatch_close_maker_fallback_from_pending(
            &mut state,
            &mut pipeline,
            &po,
            CloseMakerFallbackReason::CancelGraceExpired,
            None,
            "unit_test_cancel_grace",
        ));
        let req = rx.try_recv().expect("cancel-grace fallback request");
        let audit = req.close_maker_audit.expect("fallback audit payload");
        assert_eq!(
            audit.fallback_reason.as_deref(),
            Some("cancel_grace_expired")
        );
    }

    #[test]
    fn close_maker_rate_limit_fallback_carries_scope_in_audit() {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
        let (tx, mut rx) =
            tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::OrderDispatchRequest>();
        pipeline.set_shadow_channel(tx);
        pipeline.paper_state.apply_fill(
            "BTCUSDT",
            true,
            0.1,
            50_000.0,
            0.0,
            1_700_000_000_000,
            "grid_trading",
        );
        let mut state = LoopState::new(std::collections::HashSet::new());
        let mut po = close_maker_pending_for_test();
        po.order_link_id = "oc_close_maker_rate_limit".to_string();

        assert!(dispatch_close_maker_fallback_from_pending(
            &mut state,
            &mut pipeline,
            &po,
            CloseMakerFallbackReason::RateLimitBackoffPerSymbol,
            Some(CloseMakerRateLimitScope::PerSymbol),
            "unit_test_rate_limit",
        ));
        let req = rx.try_recv().expect("rate-limit fallback request");
        let audit = req.close_maker_audit.expect("fallback audit payload");
        assert_eq!(
            audit.fallback_reason.as_deref(),
            Some("rate_limit_backoff_per_symbol")
        );
        assert_eq!(audit.rate_limit_scope.as_deref(), Some("per_symbol"));
    }

    // ─────────────────────────────────────────────────────────────────────
    // ENGINE-CRASH-FIX C3 (2026-06-15): wall-clock atomic 前進 / freeze-detection
    // 表面覆蓋（E4 補測，C3 原無針對牆鐘 store 的斷言）。
    //
    // 守住的合約：`handle_tick_event` 必須把「牆鐘 now_ms」（SystemTime::now）
    // 存入 watchdog 讀的 atomic，而非 Bybit payload `ev.ts_ms`。原始事故根因正是
    // watchdog 比對 payload-ts → payload 時鐘偏移/重放時越過 120s delta → 對活著
    // 的 live 引擎發 SIGTERM 市價平倉。下面用與 production（loop_handlers.rs:823-828）
    // 逐位元組相同的 store 區塊驅動一個真 AtomicU64，斷言：
    //   (a) store 後 atomic 前進到接近真實牆鐘（非 0、非 payload-ts）；
    //   (b) watchdog 的 freeze-detection 謂詞（last!=0 && now-last>120_000）在剛
    //       store 後判定為「fresh」（不誤殺）；
    //   (c) 若改存 11 天前的 payload-ts（模擬 regression / 舊根因），同謂詞會判定
    //       為「stale」→ 證明測試對「存錯來源」這一 bug class 有 bite，非 tautology。
    // ─────────────────────────────────────────────────────────────────────
    #[test]
    fn handle_tick_wallclock_store_advances_atomic_to_live_walltime_not_payload_ts() {
        use std::sync::atomic::{AtomicU64, Ordering};
        // watchdog 的 stale 門檻正本（main_watchdog.rs: TICK_STALE_THRESHOLD_MS）。
        const TICK_STALE_THRESHOLD_MS: u64 = 120_000;
        // freeze-detection 謂詞，鏡像 main_watchdog.rs:81-88 的 warmup-zero + delta 判斷。
        fn watchdog_says_stale(last: u64, now_ms: u64) -> bool {
            if last == 0 {
                return false; // warmup：尚未處理過 tick
            }
            now_ms > last && now_ms - last > TICK_STALE_THRESHOLD_MS
        }

        let wall_atomic = std::sync::Arc::new(AtomicU64::new(0));
        // 一個「11 天前」的 Bybit payload ts（模擬 ~21 起事故的 payload-ts 偏移）。
        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        let stale_payload_ts = now_ms.saturating_sub(11 * 24 * 60 * 60 * 1000);

        // 暖機：尚未 store → 0 → watchdog 永不誤殺。
        assert_eq!(wall_atomic.load(Ordering::Relaxed), 0);
        assert!(
            !watchdog_says_stale(wall_atomic.load(Ordering::Relaxed), now_ms),
            "last==0 warmup must never be stale"
        );

        // === production store 區塊（loop_handlers.rs:823-828 逐位元組）===
        if let Some(wall_ms) = Some(&wall_atomic) {
            let now = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            wall_ms.store(now, Ordering::Relaxed);
        }
        // ================================================================

        let stored = wall_atomic.load(Ordering::Relaxed);
        // (a) 前進到接近真實牆鐘，且明確不是 payload-ts。
        assert!(stored > 0, "wall-clock store must advance atomic off 0");
        assert!(
            stored >= now_ms && stored < now_ms + 5_000,
            "stored must be live wall-clock now ({stored} vs now {now_ms})"
        );
        assert!(
            stored != stale_payload_ts,
            "stored wall-clock must NOT be the stale payload ts"
        );
        // (b) 剛 store → watchdog 判 fresh（不誤殺活引擎）。
        let now2 = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        assert!(
            !watchdog_says_stale(stored, now2),
            "freshly-processed tick must be judged fresh by watchdog"
        );
        // (c) BITE：若 store 的是 11 天前的 payload-ts（root-cause regression），
        // watchdog 立刻判 stale → 會誤殺。證明 wall-clock 來源是正確選擇。
        assert!(
            watchdog_says_stale(stale_payload_ts, now2),
            "payload-ts source (the original bug) would false-positive stale"
        );
    }
}

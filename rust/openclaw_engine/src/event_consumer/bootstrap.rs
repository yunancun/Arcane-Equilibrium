//! Event consumer bootstrap — all pre-loop pipeline construction & wiring.
//! 事件消費者啟動 — 所有主迴圈前的管線構造與接線。
//!
//! MODULE_NOTE (EN): Extracted from `event_consumer/mod.rs` as Wave 1 G1-02
//!   Step 3. Consumes `EventConsumerDeps` and returns `BootstrappedRuntime`
//!   — a struct carrying (a) constructed runtime handles (pipeline / writers
//!   / channels spawned here) and (b) forwarded deps fields the main event
//!   loop still needs (event_rx / cancel / various IPC rx / shared atomics).
//!   Design: one big fn rather than micro-helpers because bootstrap has ~27
//!   interdependent bindings (triage_cmd_tx at line ~142 used at ~329 etc.),
//!   and splitting would explode parameter lists. Mirror tick_pipeline/pipeline_ctor.rs.
//! MODULE_NOTE (中): 從 `event_consumer/mod.rs` 抽出（Wave 1 G1-02 Step 3）。
//!   消費 `EventConsumerDeps` 回傳 `BootstrappedRuntime` — 包 (a) 構造出的 runtime handle
//!   （pipeline / writers / 本處 spawn 的 channel）與 (b) 主事件迴圈仍需的 deps 欄位轉發
//!   （event_rx / cancel / 各 IPC rx / shared atomics）。
//!   設計決策：單一大 fn 而非微拆，因 bootstrap 有 ~27 互相依賴的 binding
//!   （如 triage_cmd_tx @~142 line 被 ~329 line 使用），拆分會引爆參數清單。
//!   採 `tick_pipeline/pipeline_ctor.rs` 之先例。

use super::dispatch;
use super::governor_cooldown::load_governor_cooldown_from_audit;
use super::paper_state_restore;
use super::setup;
use super::types::{EventConsumerDeps, ExchangeEvent, PendingOrder, SYMBOLS};
use crate::persistence::{AuditWriter, DualStateWriter, StateWriter};
use crate::strategies::StrategyFactory;
use crate::tick_pipeline::{PipelineCommand, PipelineKind, TickPipeline};
use openclaw_types::PriceEvent;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::{broadcast, mpsc};
use tokio_util::sync::CancellationToken;
use tracing::{error, info, warn};

/// Everything `run_event_consumer`'s main loop needs after bootstrap.
/// 主迴圈在 bootstrap 後所需的一切。
///
/// Combines:
/// - **Constructed runtime handles** (pipeline, state/snapshot/audit writers,
///   kline-seed rx, pending-order-registration rx, data_path, kind_tag)
/// - **Forwarded deps fields** the loop consumes (event_rx, cancel,
///   various IPC rx/tx, shared atomics, audit_pool)
///
/// Keeps pub(super) scope — only mod.rs reads this.
pub(super) struct BootstrappedRuntime {
    // ── Constructed runtime handles / 構造出的 runtime handle ──
    pub pipeline: TickPipeline,
    pub state_writer: StateWriter,
    pub snapshot_writer: DualStateWriter,
    pub audit_writer: AuditWriter,
    pub kline_seed_rx: mpsc::Receiver<(String, Vec<openclaw_core::klines::KlineBar>)>,
    /// D3 kline bootstrap sender — loop's event arm spawns dynamic refetches
    /// for newly-added symbols from scanner registry updates.
    /// D3 K 線引導發送端 — loop 事件 arm 在掃描器新增幣種時 spawn 動態補抓。
    pub kline_seed_tx: mpsc::Sender<(String, Vec<openclaw_core::klines::KlineBar>)>,
    pub pending_reg_rx_slot: Option<mpsc::UnboundedReceiver<PendingOrder>>,
    pub data_path: PathBuf,
    pub kind_tag: &'static str,
    /// `trading_tx.clone()` — loop emits order lifecycle events through this.
    /// 在 trading_tx 被吸入 pipeline 前的 clone，供 loop 寫 order lifecycle。
    pub order_tx: Option<mpsc::Sender<crate::database::TradingMsg>>,
    /// D2/D3 scanner universe diff baseline — starts with static `SYMBOLS`,
    /// loop updates on each registry snapshot diff.
    /// D2/D3 掃描器品類差分基線 — 初始為靜態 `SYMBOLS`，loop 根據每次 registry 快照更新。
    pub known_symbols: std::collections::HashSet<String>,
    /// `EngineBootstrap` snapshot captured at bootstrap time (Arc — cheap clone).
    /// Loop's tick arm reads `cfg_snapshot.kline_bootstrap` to gate D3 dynamic refetch.
    /// Bootstrap 時的 EngineBootstrap 快照（Arc，clone 成本低）。
    pub cfg_snapshot: Arc<crate::config::EngineBootstrap>,
    /// REST client for D3 dynamic kline bootstrap on scanner-added symbols.
    /// D3 動態 K 線引導 REST 客戶端（掃描器新增符號時）。
    pub bootstrap_client: Option<Arc<crate::bybit_rest_client::BybitRestClient>>,
    /// Scanner symbol registry — loop's event arm reads snapshot for D2 diff.
    /// 掃描器符號注冊表 — loop 事件 arm 讀取快照做 D2 差分。
    pub symbol_registry: Option<Arc<crate::scanner::registry::SymbolRegistry>>,

    // ── Forwarded deps fields (loop consumes) / 轉發 loop 會用的原 deps 欄位 ──
    pub pipeline_kind: PipelineKind,
    pub event_rx: mpsc::Receiver<Arc<PriceEvent>>,
    pub cancel: CancellationToken,
    pub shared_client: Option<Arc<crate::bybit_rest_client::BybitRestClient>>,
    pub shared_bybit_balance: Option<Arc<parking_lot::RwLock<Option<f64>>>>,
    pub shared_api_pnl: Option<Arc<parking_lot::RwLock<HashMap<String, f64>>>>,
    pub shared_last_tick_ms: Option<Arc<std::sync::atomic::AtomicU64>>,
    pub exchange_event_rx: Option<mpsc::UnboundedReceiver<ExchangeEvent>>,
    pub pipeline_cmd_rx: Option<mpsc::UnboundedReceiver<PipelineCommand>>,
    pub audit_pool: Option<sqlx::PgPool>,
    pub shared_risk_level: Option<Arc<std::sync::atomic::AtomicU8>>,
    pub cross_engine_tx: Option<broadcast::Sender<crate::tick_pipeline::EngineEvent>>,
    pub cross_engine_rx: Option<broadcast::Receiver<crate::tick_pipeline::EngineEvent>>,
    pub pipeline_health: Option<Arc<std::sync::atomic::AtomicU8>>,
    pub canary_handle: crate::canary_writer::CanaryWriterHandle,
}

/// Build the pipeline and wire all startup dependencies.
/// Returns `BootstrappedRuntime` with everything the main loop consumes.
///
/// 構造管線並接線所有啟動依賴。回傳 `BootstrappedRuntime` 供主迴圈消費。
pub(super) async fn bootstrap_runtime(deps: EventConsumerDeps) -> BootstrappedRuntime {
    let EventConsumerDeps {
        pipeline_kind,
        endpoint_env,
        event_rx,
        config,
        cancel,
        initial_balance,
        paper_initial_balance: _paper_initial_balance,
        taker_fee_rate,
        instruments: shared_instruments,
        bootstrap_client,
        shared_client,
        bybit_balance: shared_bybit_balance,
        api_pnl: shared_api_pnl,
        pipeline_cmd_rx,
        pipeline_cmd_tx,
        market_data_tx,
        feature_tx,
        last_tick_ms: shared_last_tick_ms,
        trading_tx,
        context_tx,
        decision_feature_tx,
        shadow_fill_tx,
        // EXIT-FEATURES-TABLE-1 Phase 1b (2026-04-18): producer wiring landed.
        // `emit_close_fill` builds a 7-dim ExitFeatureRow and try_send's here.
        // All three engines share the same writer tx (multi-producer safe —
        // PK=(context_id, ts) collisions never occur across engines because
        // engine_mode is part of the logical grouping and timestamps collide
        // only within a single engine's tick).
        // EXIT-FEATURES-TABLE-1 Phase 1b（2026-04-18）：producer 接線已上線。
        // `emit_close_fill` 建 7 維 ExitFeatureRow 並 try_send 入此通道。
        // 三引擎共用同一 writer（多 producer 安全）。
        exit_feature_tx,
        // INFRA-PREBUILD-1 Part A (2026-04-23): Combine Layer exit-time shadow
        // observation. Dormant default; Phase 2+ shadow_enabled flip activates.
        // INFRA-PREBUILD-1 A 部：Combine Layer 退場時刻 shadow 觀測通道。
        shadow_exit_tx,
        exchange_event_rx,
        seed_positions,
        account_manager,
        linucb_runtime,
        news_snapshot,
        risk_store,
        budget_store,
        audit_pool,
        symbol_registry,
        scanner_store: _, // D-03: unused — ScannerConfig read via scanner_runner, not event_consumer
        shared_risk_level,
        is_primary,
        ready_tx,
        global_exposure_usdt,
        cross_engine_tx,
        cross_engine_rx,
        pipeline_health,
        canary_handle,
        edge_predictor_store,
        positions_mirror,
    } = deps;

    // MARKET-KLINES-STALE-1 (2026-04-18): the original D19 invariant
    // ("only Paper writes market/feature DB") was invalidated by PAPER-DISABLE-1
    // — Paper now defaults off, leaving market.klines stale for ~2 days. All
    // three pipelines now share `market_tx` (multi-producer safe via
    // market_writer.rs ON CONFLICT dedup). `feature_tx` wiring is a main.rs
    // decision per pipeline kind; no runtime guard needed.
    // MARKET-KLINES-STALE-1（2026-04-18）：原 D19 的「僅 Paper 寫 market/feature
    // DB」不變式已被 PAPER-DISABLE-1 推翻（Paper 預設關閉導致 market.klines 停寫
    // ~2 天）。三引擎共享 market_tx（market_writer.rs ON CONFLICT 去重，多 producer
    // 安全）。feature_tx 的接線由 main.rs 按 pipeline kind 決定，無須 runtime 守衛。

    let cfg_snapshot = config.get();

    // Build pipeline with kind-appropriate governance + balance (3E-2a)
    // 以 kind 對應的治理 + 餘額構建管線（3E-2a）
    let mut pipeline = TickPipeline::with_kind(SYMBOLS, initial_balance, pipeline_kind);

    // Endpoint-aware engine_mode tag: wires live_bybit_environment() into the
    // pipeline so DF / trading rows stamp `live_demo` when Live is pointed at
    // api-demo.bybit.com instead of the misleading `live`. Paper passes None.
    // Endpoint 感知的 engine_mode 標籤：把 live_bybit_environment() 穿給管線，
    // Live+demo endpoint 的資料列標 `live_demo` 而非誤導性的 `live`。Paper 傳 None。
    if let Some(env) = endpoint_env {
        pipeline.set_endpoint_env(env);
    }

    // EDGE-P3-1 Phase B #1: Inject per-engine EdgePredictorStore. None preserves
    // the pre-wiring behaviour (intent_processor keeps `store = None`, gate
    // short-circuits to legacy shrinkage). Some wires both the TickPipeline IPC
    // side (SetEdgePredictorShadow / DisableEdgePredictorAll) and IntentProcessor
    // gate-side lookups to the same Arc, so ML-MIT hot-swaps arrive at the gate
    // without a restart. `use_edge_predictor=false` default still gates actual
    // consultation — this only closes the bootstrap plumbing.
    // EDGE-P3-1 Phase B #1：注入逐引擎 EdgePredictorStore。None 保持接線前
    // 行為；Some 時 TickPipeline IPC 端與 IntentProcessor gate 端共享同一 Arc。
    if let Some(store) = edge_predictor_store {
        pipeline.set_edge_predictor_store(store);
    }

    // EDGE-P3-1 #62: Wire the PipelineCommand sender into IntentProcessor so the
    // predictor gate's ε-greedy branch can publish `EmitShadowFill` IPC messages
    // back through the same channel the event consumer dispatcher drains. With
    // tx=None the gate hits a fail-soft drop branch and all shadow fills are
    // silently lost — breaking Stage 4 paper-only exploration data collection.
    // EDGE-P3-1 #62：把 PipelineCommand 發送端塞給 IntentProcessor，使 predictor
    // gate 的 ε-greedy 分支能發出 `EmitShadowFill` 經事件消費者 dispatcher 回流。
    // 不接線 → shadow fill 走 fail-soft 丟棄分支，Stage 4 paper 探索資料全失。
    // P0-6: clone before move — triage needs the sender for CloseSymbol dispatch.
    let triage_cmd_tx = pipeline_cmd_tx.clone();
    if let Some(tx) = pipeline_cmd_tx {
        pipeline.set_shadow_fill_tx(tx);
    }

    // EDGE-P3-1 Step 7a: Wire the decision-feature DB channel into IntentProcessor
    // so every gate evaluation emits a training-store row. `None` leaves emission
    // as no-op (fail-soft — trading unaffected, just no training collection). The
    // handler for `PipelineCommand::DecisionFeatureSnapshot` also forwards into
    // this same channel so external IPC callers land in the same writer.
    // EDGE-P3-1 Step 7a：把決策特徵 DB 通道接入 IntentProcessor；None 時發射為
    // no-op（fail-soft，不影響交易僅停訓練採集）。IPC passthrough 亦走同一通道。
    if let Some(tx) = decision_feature_tx.clone() {
        pipeline.set_decision_feature_tx(tx);
    }

    // EDGE-P3-1 Step 7c: Wire the shadow-fill DB channel into TickPipeline so
    // the `EmitShadowFill` IPC handler can forward ε-greedy paper exploration
    // rows into `learning.decision_shadow_fills`. `None` keeps the handler's
    // fail-soft log branch. Gate + DB CHECK enforce paper-only; writer runs on
    // all engines so a leak gets logged rather than poisoning PG.
    // EDGE-P3-1 Step 7c：把 shadow-fill DB 通道接入 TickPipeline；None 時 handler
    // 走 fail-soft log。gate + DB CHECK 強制 paper-only。
    if let Some(tx) = shadow_fill_tx.clone() {
        pipeline.set_shadow_fill_db_tx(tx);
    }

    // EXIT-FEATURES-TABLE-1: Wire the exit-feature DB channel so every
    // PaperState close path emits one row into `learning.exit_features`.
    // `None` leaves emission as fail-soft no-op.
    // EXIT-FEATURES-TABLE-1：接入 exit-feature DB 通道，PaperState 每次平倉
    // 產生一列寫入 `learning.exit_features`。未接線為 fail-soft no-op。
    if let Some(tx) = exit_feature_tx.clone() {
        pipeline.set_exit_feature_tx(tx);
    }

    // INFRA-PREBUILD-1 Part A (2026-04-23): Wire shadow-exit DB channel so
    // Combine Layer's close-path can emit one ShadowExitMsg per close fill
    // when shadow_enabled=true. Dormant default (flag OFF → no emit). Fail-
    // soft: None disables entirely, trading path unaffected.
    // INFRA-PREBUILD-1 A 部：接入 shadow-exit DB 通道，Combine Layer close path
    // 在 shadow_enabled=true 時每筆 close 寫一列。預設 flag 關 → 零 emit。
    // fail-soft：None 時完全關閉，交易路徑不受影響。
    if let Some(tx) = shadow_exit_tx.clone() {
        pipeline.set_shadow_exit_tx(tx);
    }

    // EDGE-P3-1 Phase B #4: Seed the IntentProcessor predictor RNG with a per-
    // engine derivation of the current wallclock (spec §7.3 F9:
    // `engine_startup_nanos ^ engine_kind_discriminant`). `seed_for_engine`
    // already lives in the gate module; we just have to call it once at
    // bootstrap. Without this wire-up every engine inherits the default seed
    // 0 from `IntentProcessor::new` and the kind discriminant XOR is inert —
    // paper's ε-greedy branch replays an identical draw sequence across
    // restarts, and demo/live (harmless today thanks to the gate guard) would
    // too once future fixtures reseed them. Wallclock-ns is deterministic for
    // tests that mock time, non-crypto fast on the hot path, and never hits
    // OsRng. `unwrap_or(0)` keeps the writer from panicking on the 1970-era
    // clock shenanigans that only happen in malformed containers — the
    // kind-discriminant XOR still gives three distinct streams.
    // EDGE-P3-1 Phase B #4：以 §7.3 F9 規則 seed IntentProcessor 的 predictor
    // RNG（啟動 nanos ^ 引擎 kind 判別）。`seed_for_engine` 已在 gate 模組，
    // 此處只是每個 pipeline 啟動時呼叫一次；缺接線則三引擎共用 seed=0。
    let startup_nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let predictor_seed = crate::edge_predictor::gate::seed_for_engine(startup_nanos, pipeline_kind);
    pipeline.set_predictor_rng_seed(predictor_seed);

    // QoL-1: Restore cumulative paper_state counters from trading.fills before
    // the first tick; details + fail-soft log are in paper_state_restore.
    // QoL-1：首個 tick 前從 trading.fills 還原累計指標；細節見 helper。
    paper_state_restore::restore_paper_counters(&mut pipeline, audit_pool.as_ref()).await;

    // B-1 Phase 2: Seed paper_state with exchange positions captured at startup.
    // Without this, inactive symbols never get WS PositionUpdate → snapshot=0.
    // B-1 Phase 2：以啟動時抓到的交易所持倉 seed paper_state（Paper 管線 no-op）。
    if !seed_positions.is_empty() {
        let count = pipeline.paper_state.import_positions(seed_positions);
        info!(
            kind = %pipeline_kind,
            seeded = count,
            "B-1 Phase 2: paper_state seeded from exchange snapshot \
             / 已用交易所快照種入 paper_state"
        );
        // EXIT-FEATURES-WRITER-BUG-1-FIX (2026-04-26): defence-in-depth
        // backfill of `entry_notional` after `import_positions`. Idempotent —
        // touches only entries with `entry_notional <= 0.0 && qty > 0` (which
        // `import_positions` should never produce since it sets
        // `qty * entry_price` directly, but a Bybit REST snapshot returning
        // `avg_price = 0` for a stale dust residue would slip the guard at
        // line 48 and leave entry_notional == 0). Without this backfill the
        // MICRO-PROFIT-FIX-1 ratio gate fail-opens for that position and the
        // STRKUSDT-class 37-halve dust spiral resurrects on the next risk
        // event. MIT audit `2026-04-26--exit_features_writer_bug_audit.md`
        // §4 RCA-A path A3.
        // EXIT-FEATURES-WRITER-BUG-1-FIX：import_positions 後 idempotent
        // backfill entry_notional（防 Bybit REST avg_price=0 殘留 → 修補
        // MICRO-PROFIT-FIX-1 ratio gate fail-open 漏洞）。
        let migrated = pipeline.paper_state.migrate_legacy_entry_notional();
        if migrated > 0 {
            info!(
                kind = %pipeline_kind,
                migrated,
                "EXIT-FEATURES-WRITER-BUG-1-FIX: backfilled entry_notional on \
                 import (legacy/zero-avg_price residue) / 啟動時補齊 entry_notional"
            );
        }
    }

    // ORPHAN-ADOPT-1 FUP: swap paper_state's positions_mirror to the shared
    // handle constructed in main.rs. This handle is also held by the
    // reconciler's `OrphanHandlerConfig.engine_positions_mirror`, so the
    // reconciler's orphan suppression check reads the same state the
    // engine writes. set_positions_mirror rehydrates the shared handle
    // from whatever seed_positions injected, so nothing is lost.
    // ORPHAN-ADOPT-1 FUP：把 paper_state 的 positions_mirror 換成 main.rs 建立
    // 的共享 handle，與對帳器 OrphanHandlerConfig 共享，讓對帳器讀到引擎實時
    // 持倉。set_positions_mirror 會從 seed_positions 回填共享 handle。
    if let Some(mirror) = positions_mirror {
        pipeline.paper_state.set_positions_mirror(mirror);
    }

    // SCANNER-GATE: wire SymbolRegistry into pipeline so new opens are gated
    // to scanner-active symbols only (prevents open→orphan-close death loop).
    // The loop's event arm (D2 diff) also reads this Arc, so we'll carry it
    // through in `BootstrappedRuntime.symbol_registry` — clone before the
    // triage `ref` borrow below.
    // SCANNER-GATE：接入 SymbolRegistry，新開倉僅限掃描器活躍交易對。
    // 主迴圈事件 arm（D2 差分）亦讀此 Arc，故在 triage 的 ref 借用前先 clone 轉出。
    let symbol_registry_for_loop: Option<Arc<crate::scanner::registry::SymbolRegistry>> =
        symbol_registry.as_ref().map(Arc::clone);
    if let Some(ref reg) = symbol_registry {
        pipeline.set_symbol_registry(Arc::clone(reg));
    }

    // ── P0-6 FIX: Triage bybit_sync positions ─────────────────────────────
    // After import + mirror wire-up, classify every `owner_strategy="bybit_sync"`
    // position: symbol in scanner active universe → adopt under a real strategy
    // (StopManager + strategy close signals manage lifecycle); NOT in universe →
    // evict from paper_state and dispatch CloseSymbol so the reconciler closes it
    // on Bybit. Breaks the FUP-suppression deadlock that prevented orphan handler
    // from ever running on startup-synced positions.
    //
    // DUST-EVICTION-GAP-1 / P1-8 (2026-04-17): eviction candidates whose estimated
    // notional (qty × ref_price) falls below the exchange `min_notional` are NOT
    // evicted and NOT close-dispatched — they would be rejected by dispatch's
    // pre-flight check (event_consumer/dispatch.rs:73-87) and by Bybit's server
    // (retCode=170124). Instead they are frozen in place with owner_strategy =
    // DUST_FROZEN_STRATEGY so engine state stays aligned with exchange state
    // (prevents the silent engine/exchange drift observed at 18:55:57Z on 04-17
    // for PNUT/IP/AAVE). Operator must clear on Bybit GUI before truly live.
    //
    // P0-6 修復：啟動 bybit_sync 持倉分流。在 scanner 活躍集合內 → 指派策略接管；
    // 不在集合內 → 正常驅逐並派 CloseSymbol。
    // DUST-EVICTION-GAP-1：驅逐候選若名義值低於 min_notional 則凍結保留（避免
    // 引擎狀態與交易所無聲偏差）。
    if pipeline_kind.is_exchange() {
        let active_symbols = match symbol_registry {
            Some(ref reg) => reg.snapshot(),
            None => SYMBOLS.iter().map(|s| s.to_string()).collect(),
        };

        // Snapshot reference prices for bybit_sync positions BEFORE the mutable
        // triage call (borrow checker). Fall back to entry_price if latest_prices
        // has no tick yet (startup bootstrap race window).
        // 快照 bybit_sync 持倉的參考價（借用檢查器要求），latest_prices 未有 tick
        // 時用 entry_price 備援（啟動引導競態窗口）。
        let ref_prices: HashMap<String, f64> = pipeline
            .paper_state
            .positions()
            .iter()
            .filter(|p| p.owner_strategy == "bybit_sync")
            .map(|p| {
                let px = pipeline
                    .paper_state
                    .latest_price(&p.symbol)
                    .filter(|v| *v > 0.0)
                    .unwrap_or(p.entry_price);
                (p.symbol.clone(), px)
            })
            .collect();

        let icache_for_triage = shared_instruments.as_ref().map(Arc::clone);
        let triage = pipeline.paper_state.triage_bybit_sync(
            &active_symbols,
            crate::position_reconciler::orphan_handler::KNOWN_STRATEGY_NAMES,
            |symbol, qty| {
                let ic = icache_for_triage.as_ref()?;
                let spec = ic.get(symbol)?;
                if spec.min_notional <= 0.0 {
                    return None;
                }
                let px = *ref_prices.get(symbol)?;
                if px <= 0.0 {
                    return None;
                }
                Some((qty * px, spec.min_notional))
            },
        );

        for (sym, strategy) in &triage.adopted {
            info!(
                kind = %pipeline_kind, symbol = %sym, strategy = %strategy,
                "P0-6 triage: bybit_sync position adopted by strategy \
                 / P0-6 分流：bybit_sync 持倉被策略接管"
            );
        }
        for (sym, is_long, qty) in &triage.evicted {
            warn!(
                kind = %pipeline_kind, symbol = %sym, is_long, qty,
                "P0-6 triage: bybit_sync position evicted (not in universe), \
                 dispatching close / P0-6 分流：bybit_sync 持倉被驅逐（不在活躍集合），派發平倉"
            );
            if let Some(ref tx) = triage_cmd_tx {
                let _ = tx.send(crate::tick_pipeline::PipelineCommand::CloseSymbol {
                    symbol: sym.clone(),
                    hint_is_long: Some(*is_long),
                    hint_qty: Some(*qty),
                });
            }
        }
        for (sym, is_long, qty, est_notional, min_notional) in &triage.dust_frozen {
            warn!(
                kind = %pipeline_kind,
                symbol = %sym,
                is_long,
                qty,
                est_notional,
                min_notional,
                "DUST-EVICTION-GAP-1: bybit_sync position frozen (notional below exchange \
                 minimum, close would be rejected) — operator must clear manually on Bybit GUI \
                 / DUST-EVICTION-GAP-1：持倉凍結（名義值低於交易所最小值，派平倉將被拒）— \
                 operator 需在 Bybit GUI 手動清理"
            );
        }
        if !triage.adopted.is_empty()
            || !triage.evicted.is_empty()
            || !triage.dust_frozen.is_empty()
        {
            info!(
                kind = %pipeline_kind,
                adopted = triage.adopted.len(),
                evicted = triage.evicted.len(),
                dust_frozen = triage.dust_frozen.len(),
                "P0-6 triage complete / P0-6 分流完成"
            );
        }
    }

    // D2/D3: Track known symbols for scanner universe diff (baseline for loop).
    // D2/D3：追蹤已知交易對，用於掃描器品類差分（loop 基線）。
    let known_symbols: std::collections::HashSet<String> =
        SYMBOLS.iter().map(|s| s.to_string()).collect();

    // D3: Channel for async kline bootstrap results (spawned task → main loop).
    // `kline_seed_tx` is returned to the loop (forwarded in BootstrappedRuntime)
    // so event arm can spawn dynamic refetches on scanner-added symbols.
    // D3：異步 K 線引導結果通道（生成任務 → 主循環）。
    // `kline_seed_tx` 轉發給 loop（在 BootstrappedRuntime 中），供事件 arm 在掃描器
    // 新增符號時 spawn 動態補抓。
    let (kline_seed_tx, kline_seed_rx) =
        tokio::sync::mpsc::channel::<(String, Vec<openclaw_core::klines::KlineBar>)>(8);

    // ARCH-RC1 1C-4 B1: restore governor de-escalation cooldown from V014.
    // See governor_cooldown.rs for logic details.
    // ARCH-RC1 1C-4 B1：從 V014 還原 governor 降級冷卻。邏輯詳見 governor_cooldown.rs。
    if let Some(pool) = audit_pool.as_ref() {
        let now_ms = openclaw_core::now_ms();
        match load_governor_cooldown_from_audit(pool, now_ms).await {
            Some(ts_ms) => {
                pipeline.set_last_governor_de_escalation_ms(Some(ts_ms));
                let remaining_ms = TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS
                    .saturating_sub(now_ms.saturating_sub(ts_ms));
                info!(
                    last_ts_ms = ts_ms,
                    remaining_ms,
                    "ARCH-RC1 1C-4 B1: restored governor de-escalation cooldown from V014 \
                     / 從 V014 還原 governor 降級冷卻"
                );
            }
            None => {
                info!(
                    "ARCH-RC1 1C-4 B1: no active governor cooldown in V014 (cold start) \
                     / V014 內無活躍 governor 冷卻（冷啟動）"
                );
            }
        }
    } else {
        warn!(
            "ARCH-RC1 1C-4 B1: audit pool unavailable; governor cooldown starts fresh \
             (fail-soft) / 審計 pool 不可用，governor 冷卻將從零開始（fail-soft）"
        );
    }

    // Clone trading_tx before moving into pipeline — event loop needs it for
    // order lifecycle DB writes (trading.orders + order_state_changes).
    // 在移入 pipeline 前克隆，供事件循環寫入 trading.orders + order_state_changes。
    let order_tx = trading_tx.clone();

    // I-22: Pipeline wire-up extracted to setup helper.
    setup::wire_pipeline(
        &mut pipeline,
        &cfg_snapshot,
        taker_fee_rate,
        shared_instruments.as_ref(),
        market_data_tx,
        feature_tx,
        trading_tx,
        context_tx,
    );

    // Wire AccountManager for live per-symbol fee lookups (cost gate / Kelly / cost_ratio).
    if let Some(am) = account_manager {
        pipeline.set_account_manager(Arc::clone(&am));
        info!("pipeline using AccountManager for per-symbol fee rates / 接入動態費率");
    }

    // Phase 4 W-3: Wire LinUCB runtime (read-only arm selection, metadata only).
    // Phase 4 W-3：接入 LinUCB 運行時（唯讀 arm 選擇，僅 metadata）。
    if let Some(rt) = linucb_runtime {
        pipeline.set_linucb_runtime(rt);
        info!("pipeline using LinUcbRuntime for arm metadata / 接入 LinUCB runtime");
    }

    // Phase 4 W-4: Wire shared NewsContextSnapshot (news_severity + hours_since_last_major_news).
    // Phase 4 W-4：接入共享 NewsContextSnapshot（news_severity + hours_since_last_major_news）。
    if let Some(snap) = news_snapshot {
        pipeline.set_news_snapshot(snap);
        info!("pipeline using NewsContextSnapshot for news context / 接入新聞快照");
    }

    // ARCH-RC1 1C-2-B: Wire live RiskConfig + BudgetConfig stores.
    // First tick after this point reads the real operator-authored config
    // and hot-reloads automatically on every IPC patch that bumps the version.
    // ARCH-RC1 1C-2-B：接入 live RiskConfig + BudgetConfig store，
    // 此後每次 tick 即讀真實 operator 配置；IPC patch 令版本上升時自動熱重載。
    if let Some(store) = risk_store {
        pipeline.set_risk_store(store);
        info!("pipeline wired to live RiskConfig ConfigStore / 接入 RiskConfig 熱重載");
    }
    if let Some(store) = budget_store {
        pipeline.set_budget_store(store);
        info!("pipeline wired to live BudgetConfig ConfigStore / 接入 BudgetConfig 熱重載");
    }

    // PH5-WIRE-1: Load JS shrunk edge estimates from settings/edge_estimates.json.
    // Cold-start (file absent) → empty estimates → ATR×0.2 fallback remains active.
    // PH5-WIRE-1：從 settings/edge_estimates.json 加載 JS 收縮邊際估計。
    // 冷啟動（文件缺失）→ 空估計 → ATR×0.2 回退保持激活。
    {
        // Load mode-specific edge estimates: paper → edge_estimates_paper.json (isolated),
        // demo/live → edge_estimates.json (production). Paper exploration data must not
        // pollute demo/live cost_gate decisions — this breaks the degenerative feedback loop
        // where paper's noisy negative-edge fills drag down shrunk_bps for all modes.
        // 加載模式特定邊際估計：paper 隔離，demo/live 用生產數據。
        // Paper 探索數據不得污染 demo/live cost_gate 決策。
        let base = std::env::var("OPENCLAW_BASE_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| {
                std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."))
            });
        let mode = pipeline_kind.db_mode();
        let estimates = crate::edge_estimates::EdgeEstimates::load_for_mode(&base, mode);
        if estimates.is_populated() {
            info!(
                mode,
                n_cells = estimates.n_cells(),
                grand_mean_bps = estimates.grand_mean_bps(),
                "PH5-WIRE-1: JS edge estimates loaded / JS 邊際估計已加載"
            );
        } else {
            info!(
                mode,
                "PH5-WIRE-1: no edge snapshot — cold-start ATR×0.2 fallback / 無快照，ATR 回退"
            );
        }
        pipeline.set_edge_estimates(estimates);
    }

    // BLOCKER-3 D15: Wire global exposure atomic (exchange pipelines only).
    // BLOCKER-3 D15：接入全局曝險原子量（僅交易所管線）。
    if let Some(ge) = global_exposure_usdt {
        pipeline.set_global_exposure(ge);
        info!("pipeline wired to global notional cap / 接入全局名目上限");
    }

    // Item 3: Bybit sync mode — set initial sync balance / 設定 Bybit 同步餘額
    if cfg_snapshot.balance_mode == "bybit_sync" {
        pipeline
            .paper_state
            .set_bybit_sync_balance(Some(initial_balance));
        info!(
            balance = format!("{:.2}", initial_balance),
            "bybit_sync mode — tracking Bybit Demo balance / 同步模式已啟用"
        );
    }

    // Item 1: Server-side stop channel (dual-track stops)
    // 項目 1：伺服器端止損通道（雙軌止損）
    if cfg_snapshot.server_side_stops {
        let (stop_tx, mut stop_rx) =
            tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::StopRequest>();
        pipeline.set_stop_channel(stop_tx);

        // P9: Clone shared client for exchange-side conditional stop orders
        // (Principle #9 dual-rail: local stop + exchange stop).
        // Paper mode: no client → log only. Demo/Live: call Bybit trading-stop API.
        // P9：Clone 共享客戶端用於交易所端條件止損單
        // （根原則 #9 雙軌止損：本地止損 + 交易所止損）。
        // 紙盤模式無客戶端僅記錄；Demo/Live 調用 Bybit API。
        let stop_client = shared_client.clone();

        tokio::spawn(async move {
            // Create PositionManager once if exchange client is available.
            // 若交易所客戶端可用，一次性創建 PositionManager。
            let pos_mgr = stop_client.map(crate::position_manager::PositionManager::new);

            while let Some(req) = stop_rx.recv().await {
                info!(
                    symbol = %req.symbol,
                    stop_loss = format!("{:.2}", req.stop_loss),
                    side = if req.is_long { "long" } else { "short" },
                    "server-side stop request dispatched / 伺服器端止損請求已派發"
                );

                // P9: Place exchange-side conditional stop (dual-rail, Principle #9).
                // Fail-closed on API error: local StopManager remains active.
                // P9：放置交易所端條件止損（雙軌，根原則 #9）。
                // API 失敗時 fail-closed：本地 StopManager 仍生效。
                if let Some(ref mgr) = pos_mgr {
                    let stop_req = crate::position_manager::TradingStopRequest {
                        category: crate::order_manager::OrderCategory::Linear,
                        symbol: req.symbol.clone(),
                        take_profit: None,
                        stop_loss: Some(req.stop_loss),
                        tp_trigger_by: None,
                        sl_trigger_by: Some("LastPrice".to_string()),
                        trailing_stop: None,
                        active_price: None,
                        position_idx: Some(0), // one-way mode / 單向模式
                    };
                    match mgr.set_trading_stop(stop_req).await {
                        Ok(()) => {
                            info!(
                                symbol = %req.symbol,
                                stop_loss = format!("{:.2}", req.stop_loss),
                                "P9: exchange stop-loss set / 交易所止損已設置"
                            );
                        }
                        Err(e) => {
                            warn!(
                                symbol = %req.symbol,
                                error = %e,
                                "P9: exchange stop-loss failed (local stop active) \
                                 / 交易所止損失敗（本地止損生效）"
                            );
                        }
                    }
                }
            }
        });
        info!("dual-track stop channel active / 雙軌止損通道已啟用");
    }

    // 3E-4: pipeline_kind is set at construction via with_kind() — no runtime set_trading_mode.
    // 3E-4：pipeline_kind 在構造時通過 with_kind() 設定 — 無運行時 set_trading_mode。

    // Exchange mode = pipeline connects to real exchange (Demo or Live).
    // 交易所模式 = 管線連接真實交易所（Demo 或 Live）。
    let is_exchange_mode = pipeline.pipeline_kind.is_exchange();
    if is_exchange_mode {
        info!(
            kind = %pipeline.pipeline_kind,
            "EXT-1: exchange mode active — orders sent to exchange, fills confirmed via WS / 交易所模式啟用"
        );
    }

    // Order dispatch: shadow orders (paper_only) or primary orders (exchange mode)
    // 訂單派發：影子訂單（紙盤模式）或主訂單（交易所模式）
    let pending_reg_rx_slot = dispatch::spawn_order_dispatch(
        &mut pipeline,
        shared_client.as_ref(),
        shared_instruments.as_ref(),
        cfg_snapshot.shadow_orders || is_exchange_mode,
    );

    // Register strategies via factory (3E-9 + BLOCKER-8: per-engine TOML params)
    // 通過工廠註冊策略（3E-9 + BLOCKER-8：每引擎 TOML 參數）
    for strategy in StrategyFactory::create_for_engine(pipeline_kind) {
        pipeline.orchestrator.register(strategy);
    }

    // Grant paper authorization (redundant for Paper/Demo since with_kind() auto-grants,
    // but kept for backward compat until 3E-4 cleans up). Harmless double-grant.
    // 授予紙盤授權（Paper/Demo 用 with_kind() 已自動授權，保留向後兼容直到 3E-4 清理）
    match pipeline.grant_paper_auth() {
        Ok(()) => info!("paper authorization granted / 紙盤授權已授予"),
        Err(e) => {
            // Fatal path — caller (run_event_consumer) must not continue into the
            // main loop if auth grant failed. We can't `return;` from here because
            // bootstrap must return a BootstrappedRuntime, so we panic — this
            // preserves the original early-return semantics (process shuts down).
            // Fatal 路徑 — caller 不得進入主迴圈；bootstrap 必須 return
            // BootstrappedRuntime，故改 panic（等價原早退出語義）。
            error!(error = %e, "failed to grant paper auth / 紙盤授權失敗");
            panic!("event_consumer bootstrap: grant_paper_auth failed: {e}");
        }
    }

    let strategies = pipeline.orchestrator.active_strategy_names().join(", ");
    info!(
        strategies = %strategies,
        symbols = ?SYMBOLS,
        balance = format!("{:.2}", initial_balance),
        "pipeline ready — {} strategies on {} symbols / 管線就緒",
        pipeline.orchestrator.strategy_count(),
        SYMBOLS.len(),
    );

    // MAJOR-2: Signal that this pipeline has completed initialization.
    // Fan-out task waits for all pipelines before distributing ticks.
    // MAJOR-2：通知此管線已完成初始化。扇出任務等所有管線就緒後才分發 tick。
    if let Some(tx) = ready_tx {
        let _ = tx.send(());
    }

    // Kline bootstrap: fetch 200 1m bars per symbol via REST (eliminates 30min cold start)
    // K 線引導：通過 REST 為每個幣種獲取 200 根 1 分鐘歷史 K 線（消除 30 分鐘冷啟動）
    if cfg_snapshot.kline_bootstrap {
        if let Some(ref client_arc) = bootstrap_client {
            let mdc = crate::market_data_client::MarketDataClient::new(Arc::clone(client_arc));
            for &sym in SYMBOLS {
                match mdc
                    .get_klines("linear", sym, "1", None, None, Some(200))
                    .await
                {
                    Ok(bars) => {
                        let now_ms = openclaw_core::now_ms();
                        let mut core_bars: Vec<openclaw_core::klines::KlineBar> = bars
                            .iter()
                            .filter(|b| b.start_time + 60_000 <= now_ms)
                            .map(|b| openclaw_core::klines::KlineBar {
                                open_time_ms: b.start_time,
                                close_time_ms: b.start_time + 60_000,
                                open: b.open,
                                high: b.high,
                                low: b.low,
                                close: b.close,
                                volume: b.volume,
                                turnover: b.turnover,
                                tick_count: 1,
                                is_closed: true,
                            })
                            .collect();
                        core_bars.sort_by_key(|b| b.open_time_ms);
                        let count = pipeline.kline_manager.seed_bars(sym, "1m", core_bars);
                        info!(symbol = sym, bars = count, "kline bootstrap / K 線引導完成");
                    }
                    Err(e) => {
                        warn!(symbol = sym, error = %e, "kline bootstrap failed / K 線引導失敗")
                    }
                }
            }
        } else {
            info!("kline bootstrap skipped — no REST client / K 線引導跳過（無 REST 客戶端）");
        }
    }

    // Persistence / 持久化
    let data_dir = std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());
    let data_path = PathBuf::from(&data_dir);
    if let Err(e) = std::fs::create_dir_all(&data_path) {
        warn!(error = %e, "failed to create data dir / 創建數據目錄失敗");
    }
    // 3E-5: per-engine snapshot filenames derived from pipeline_kind.
    // Primary pipeline also writes pipeline_snapshot.json for backward compat (IPC server, watchdog).
    // 3E-5：每個引擎的快照文件名由 pipeline_kind 決定。
    // 主管線同時寫入 pipeline_snapshot.json 保持向後兼容（IPC 伺服器、看門狗）。
    let kind_tag = pipeline.pipeline_kind.db_mode(); // "paper" | "demo" | "live"
    let per_engine_snapshot = format!("pipeline_snapshot_{kind_tag}.json");
    // Stagger snapshot debounce intervals per-engine to avoid I/O contention
    // when all three pipelines flush in the same window.
    // 每引擎錯開快照去抖間隔，避免三管線同時刷新時的 I/O 爭用。
    let (state_interval_ms, snapshot_interval_ms) = match pipeline.pipeline_kind {
        PipelineKind::Paper => (30_000, 5_000),
        PipelineKind::Demo => (31_000, 5_500),
        PipelineKind::Live => (29_000, 4_500),
    };
    let state_writer = StateWriter::new(
        &data_path.join(format!("{kind_tag}_state.json")),
        state_interval_ms,
    );
    let primary_writer =
        StateWriter::new(&data_path.join(&per_engine_snapshot), snapshot_interval_ms);
    // Backward compat: primary pipeline also writes pipeline_snapshot.json
    // 向後兼容：主管線同時寫入 pipeline_snapshot.json
    let compat_writer = if is_primary {
        Some(StateWriter::new(
            &data_path.join("pipeline_snapshot.json"),
            5_000,
        ))
    } else {
        None
    };
    let mut snapshot_writer = DualStateWriter::new(primary_writer, compat_writer);
    let audit_writer = AuditWriter::new(&data_path.join(format!("{kind_tag}_audit.jsonl")));

    // ENGINE-HEAL-FIX-PHASE1 R1: Canary write moved off this hot path. The shared
    // CanaryWriterHandle (spawned once in main.rs) owns the BufWriter + flush timer
    // + size rotation; we just `try_send(record)` here. `is_enabled()` reflects the
    // env-flag decision made at spawn time — kept identical to the previous
    // local env check so `pipeline.canary_mode` semantics are unchanged.
    // ENGINE-HEAL-FIX-PHASE1 R1：灰度寫盤已移出本熱路徑。共享 CanaryWriterHandle
    // （main.rs 啟動時 spawn 一次）擁有 BufWriter + flush 定時器 + 大小輪轉；
    // 此處僅 `try_send(record)`。`is_enabled()` 反映 spawn 時決定的旗標狀態。
    pipeline.canary_mode = canary_handle.is_enabled();

    // Initial snapshot for watchdog / 初始快照供 watchdog 使用
    {
        let init_snap = pipeline.snapshot();
        if snapshot_writer.force_write(&init_snap) {
            info!("initial pipeline snapshot written / 初始管線快照已寫入");
        } else {
            warn!("failed to write initial pipeline snapshot / 初始管線快照寫入失敗");
        }
    }

    // Assemble BootstrappedRuntime for the main loop.
    // 組裝 BootstrappedRuntime 供主迴圈使用。
    BootstrappedRuntime {
        pipeline,
        state_writer,
        snapshot_writer,
        audit_writer,
        kline_seed_rx,
        kline_seed_tx,
        pending_reg_rx_slot,
        data_path,
        kind_tag,
        order_tx,
        known_symbols,
        cfg_snapshot,
        bootstrap_client,
        symbol_registry: symbol_registry_for_loop,
        pipeline_kind,
        event_rx,
        cancel,
        shared_client,
        shared_bybit_balance,
        shared_api_pnl,
        shared_last_tick_ms,
        exchange_event_rx,
        pipeline_cmd_rx,
        audit_pool,
        shared_risk_level,
        cross_engine_tx,
        cross_engine_rx,
        pipeline_health,
        canary_handle,
    }
}

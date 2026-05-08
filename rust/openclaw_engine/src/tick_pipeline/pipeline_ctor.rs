//! TickPipeline impl — ctor + basic setters/getters.
//! TickPipeline impl — 建構子 + 基礎 setter/getter。
//!
//! MODULE_NOTE (EN): Split out of `tick_pipeline/mod.rs` by TICK-PIPELINE-MOD-SPLIT-1
//!   (2026-04-22) to honour CLAUDE.md §七's 1200-line hard cap. Contains the
//!   `new` / `with_balance` / `with_kind` constructors, endpoint / registry /
//!   mode / symbol management, and the injection setters + accessors for
//!   edge estimates, LinUCB, EdgePredictorStore, shadow-fill tx, decision-/
//!   shadow-fill-/exit-feature DB channels, price tracker handles, RNG seed,
//!   and risk store accessor.
//! MODULE_NOTE (中)：TICK-PIPELINE-MOD-SPLIT-1（2026-04-22）由 `tick_pipeline/mod.rs`
//!   拆出以遵守 CLAUDE.md §七 1200 行硬上限。本檔包含 `new` / `with_balance` /
//!   `with_kind` 建構子、endpoint / registry / mode / symbol 管理，及 edge
//!   estimates / LinUCB / EdgePredictorStore / shadow-fill tx / decision- /
//!   shadow-fill- / exit-feature DB channel / price tracker handle / RNG seed
//!   / risk store accessor 的注入 setter + 取用器。

use openclaw_core::{
    governance_core::GovernanceCore, h0_gate::H0Gate, klines::KlineManager,
    risk::PriceHistoryTracker, signals::SignalEngine,
};
use std::collections::{HashMap, VecDeque};
use std::sync::Arc;

use crate::intent_processor::IntentProcessor;
use crate::orchestrator::Orchestrator;
use crate::paper_state::PaperState;

use super::{PipelineCommand, PipelineKind, SystemMode, TickPipeline, TickStats};

impl TickPipeline {
    pub fn new(symbols: &[&str]) -> Self {
        // Read paper balance from env var or default to 10,000 USDT.
        // 從環境變量讀取紙盤餘額，預設 10,000 USDT。
        let balance = std::env::var("OPENCLAW_PAPER_BALANCE")
            .ok()
            .and_then(|s| s.parse::<f64>().ok())
            .unwrap_or(10_000.0);
        Self::with_balance(symbols, balance)
    }

    /// Create a pipeline with an explicit initial balance.
    /// 使用明確初始餘額創建管線。
    pub fn with_balance(symbols: &[&str], balance: f64) -> Self {
        Self {
            kline_manager: KlineManager::new(symbols, None, None),
            signal_engine: SignalEngine::new(),
            orchestrator: Orchestrator::new(),
            intent_processor: IntentProcessor::new(),
            governance: GovernanceCore::new(),
            paper_state: PaperState::new(balance),
            stats: TickStats::default(),
            latest_prices: HashMap::new(),
            latest_indicators: HashMap::new(),
            recent_signals: VecDeque::new(),
            recent_intents: VecDeque::new(),
            recent_fills: VecDeque::new(),
            stop_request_tx: None,
            adl_alerts: VecDeque::new(),
            canary_mode: false,
            instrument_cache: None,
            order_dispatch_tx: None,
            market_data_tx: None,
            feature_tx: None,
            trading_tx: None,
            context_tx: None,
            feature_version: "v1.0".into(),
            market_tx_dropped: 0,
            feature_tx_dropped: 0,
            paper_paused: false,
            pipeline_kind: PipelineKind::Paper,
            endpoint_env: None,
            exchange_seq: 0,
            pending_close_symbols: std::collections::HashSet::new(),
            h0_gate: H0Gate::new(Some(openclaw_types::H0GateConfig {
                shadow_mode: true, // RRC-1-A3: observe-only until proven stable
                ..Default::default()
            })),
            price_tracker: PriceHistoryTracker::new(),
            consecutive_losses: HashMap::new(),
            session_halted: false,
            trade_aggregator: crate::database::aggregators::TradeAggregator::new(),
            ob_aggregator: crate::database::aggregators::ObAggregator::new(),
            boot_ts_ms: None,
            boot_cooldown_ms: std::env::var("OPENCLAW_BOOT_COOLDOWN_MS")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(60_000),
            last_governor_de_escalation_ms: None,
            last_persisted_signal: HashMap::new(),
            signals_heartbeat_ms: std::env::var("OPENCLAW_SIGNALS_HEARTBEAT_MS")
                .ok()
                .and_then(|s| s.parse::<u64>().ok())
                .unwrap_or(60_000),
            signals_throttled: 0,
            context_throttled: 0,
            black_swan: crate::database::black_swan_detector::BlackSwanDetector::new(),
            last_close_price: HashMap::new(),
            linucb: None,
            news_snapshot: None,
            risk_store: None,
            budget_store: None,
            risk_config_version_seen: 0,
            maker_kpi_store: None,
            maker_kpi_config: crate::paper_state::MakerKpiConfig::default(),
            maker_kpi_version_seen: 0,
            // 3E-4: mode_states/active_modes removed (per-pipeline architecture)
            system_mode: SystemMode::default(),
            ft_reduced_symbols: std::collections::HashMap::new(),
            funding_rates: HashMap::new(),
            index_prices: HashMap::new(),
            // EDGE-P2-2: init empty OI cache; filled on first ticker with openInterest.
            // EDGE-P2-2：初始化空 OI 緩存；首次攜帶 openInterest 的 ticker 後填充。
            open_interests: HashMap::new(),
            edge_predictor_store: None,
            decision_feature_tx: None,
            shadow_fill_db_tx: None,
            exit_feature_tx: None,
            shadow_exit_tx: None,
            agent_spine_tx: None,
            agent_spine_mode: crate::agent_spine::config::AgentSpineMode::Disabled,
            symbol_registry: None,
            scanner_authority_mode: crate::scanner::types::ScannerAuthorityMode::AdvisoryShadow,
            retriage_last_evict_ms: HashMap::new(),
            // G7-03 Phase B: empty per-symbol HysteresisDetector cache.
            // When `risk.hurst.enabled = false` (default), the helper bypasses
            // entry/insert so this map stays empty bit-identical to Phase A.
            // G7-03 Phase B：空的 per-symbol HysteresisDetector 快取，預設 bypass。
            hurst_detectors: HashMap::new(),
            // DYNAMIC-RISK-1: anchored on IntentProcessor's default p1_risk_pct (3%).
            // DYNAMIC-RISK-1：以 IntentProcessor 預設 p1_risk_pct (3%) 為錨。
            dynamic_risk_sizer: crate::dynamic_risk_sizer::DynamicRiskSizer::new(
                0.03,
                crate::dynamic_risk_sizer::DynamicRiskSizerConfig::default(),
            ),
        }
    }

    /// 3E-2a: Create a pipeline with explicit kind + balance.
    /// GovernanceCore is constructed with the appropriate profile (auto-grant for Paper/Demo).
    /// 3E-2a：以明確 kind + balance 創建管線。GovernanceCore 按 profile 構造（Paper/Demo 自動授權）。
    pub fn with_kind(symbols: &[&str], balance: f64, kind: PipelineKind) -> Self {
        let mut p = Self::with_balance(symbols, balance);
        // 3E-ARCH bugfix: persist the kind on the pipeline so downstream consumers
        // (event_consumer persistence kind_tag, IPC routing, status reports) see the
        // correct value. Without this all engines kept the with_balance() default
        // PipelineKind::Paper and raced on paper_state.json / pipeline_snapshot_paper.json.
        // 3E-ARCH 修復：把 kind 寫入 pipeline 字段，否則下游持久化 / IPC / 狀態報告
        // 都讀回 with_balance() 預設的 Paper，三引擎搶寫同一份 paper_state.json。
        p.pipeline_kind = kind;
        // EDGE-P3-1 Phase B #4 coupled fix: forward `kind` into the IntentProcessor
        // copy that the predictor gate reads via `inputs.engine_kind`. Without this,
        // `IntentProcessor::pipeline_kind` stays at its constructor default (Paper)
        // for demo/live pipelines — the ε-greedy branch at `gate.rs:213` then fires
        // on demo/live too and only gets stopped by the writer-level R5 defense +
        // DB CHECK. Forwarding here keeps the gate itself paper-only, matching
        // spec §7.3 C13.
        // EDGE-P3-1 Phase B #4 配套修復：把 `kind` 透傳給 IntentProcessor（gate 讀
        // `inputs.engine_kind`）。未透傳則 demo/live 的 IntentProcessor 仍是 Paper，
        // ε-greedy 會誤發 ShadowFill，由 R5 與 DB CHECK 兜底才擋下來；在 gate 層
        // 直接擋住與 §7.3 C13 一致。
        p.intent_processor.set_pipeline_kind(kind);
        p.governance = GovernanceCore::new_with_profile(kind.governance_profile());
        p
    }

    /// Bind this pipeline to a concrete Bybit endpoint so DB rows tag with the
    /// endpoint-aware engine_mode (see `mode_state::effective_engine_mode`).
    /// Also propagates to `IntentProcessor` so its internal DB writes (e.g.
    /// decision_feature snapshots) use the same tag.
    /// 將管線綁定到具體 Bybit 端點，DB 寫入使用 endpoint-aware engine_mode。
    /// 同時透傳至 IntentProcessor 讓其 DB 寫入（如決策特徵快照）一致。
    pub fn set_endpoint_env(&mut self, env: crate::bybit_rest_client::BybitEnvironment) {
        self.endpoint_env = Some(env);
        self.intent_processor.set_endpoint_env(env);
        // E2 round 1 verdict HIGH-1 retrofit: bind the engine_mode tag for
        // V054 lease_transitions audit emit. Each pipeline (paper / demo /
        // live_demo / live_mainnet) tags its audit rows correctly via the
        // endpoint-aware `effective_engine_mode()` resolver below; without
        // this wire-in the resolver in `governance_core` would always fall
        // back to "unknown", breaking AC-1 distinct count >= 5 query.
        // E2 round 1 verdict HIGH-1 修法：在此綁定 V054 lease_transitions
        // audit emit 的 engine_mode tag。每個 pipeline（paper / demo /
        // live_demo / live_mainnet）透過下方 endpoint-aware
        // `effective_engine_mode()` resolver 正確標記 audit row；無此
        // wire-in 則 governance_core resolver 永遠 fallback "unknown"，
        // AC-1 distinct count >= 5 query 失效。
        let tag = self.effective_engine_mode().to_string();
        self.governance.set_engine_mode_tag(tag);
    }

    /// Wire the shared scanner SymbolRegistry as market context and
    /// active-universe evidence. Must be called after construction.
    /// 接入掃描器 SymbolRegistry 作市場 context 與 active-universe evidence。
    pub fn set_symbol_registry(&mut self, reg: Arc<crate::scanner::registry::SymbolRegistry>) {
        self.symbol_registry = Some(reg);
    }

    /// Set scanner authority audit label for persisted scanner evidence.
    /// 設定持久化 scanner evidence 使用的權限審計標籤。
    pub fn set_scanner_authority_mode(
        &mut self,
        mode: crate::scanner::types::ScannerAuthorityMode,
    ) {
        self.scanner_authority_mode = mode;
    }

    /// DB engine_mode tag for this pipeline (endpoint-aware). All DB-writing
    /// code paths inside TickPipeline should route through this, NOT through
    /// `self.pipeline_kind.db_mode()` directly — the latter loses the
    /// endpoint distinction (Live + LiveDemo would collide with real
    /// mainnet live).
    /// 本管線的 DB engine_mode 標籤（endpoint 感知）。所有 DB 寫入路徑都應走這裡。
    #[inline]
    pub fn effective_engine_mode(&self) -> &'static str {
        crate::mode_state::effective_engine_mode(self.pipeline_kind, self.endpoint_env)
    }

    /// Endpoint-aware GovernanceProfile for per-intent cost-gate selection
    /// (P0-6 方案 A). Intent-processing paths must call this instead of
    /// `self.pipeline_kind.governance_profile()` — the latter ignores the
    /// bound endpoint and forces Production cost gate for LiveDemo,
    /// producing the cold-start deadlock (P0-6 RCA 2026-04-17).
    /// 本管線的 cost-gate GovernanceProfile（endpoint 感知）。
    /// Intent 處理路徑必須走這裡，避免 LiveDemo 被強制走 Production。
    #[inline]
    pub fn effective_governance_profile(
        &self,
    ) -> openclaw_core::governance_core::GovernanceProfile {
        crate::mode_state::effective_governance_profile(self.pipeline_kind, self.endpoint_env)
    }

    /// Scanner C3: Add a symbol to the kline manager (idempotent).
    /// Per-symbol HashMaps (latest_prices, latest_indicators, consecutive_losses)
    /// self-populate on first tick — no explicit initialisation needed.
    /// 掃描器 C3：向 kline manager 添加交易對（冪等）。
    /// Per-symbol HashMap 在第一個 tick 時自動填充，無需明確初始化。
    pub fn add_symbol(&mut self, symbol: &str) {
        self.kline_manager.add_symbol(symbol);
    }

    /// Scanner C3: Remove a symbol from the kline manager and clear its cached state.
    /// 掃描器 C3：從 kline manager 移除交易對並清除其緩存狀態。
    pub fn remove_symbol(&mut self, symbol: &str) {
        self.kline_manager.remove_symbol(symbol);
        self.latest_prices.remove(symbol);
        self.latest_indicators.remove(symbol);
        self.consecutive_losses.remove(symbol);
        self.last_persisted_signal
            .retain(|(sym, _), _| sym != symbol);
        self.last_close_price.remove(symbol);
        // M-1 fix: clear pending_close lock so re-entry of same symbol doesn't
        // inherit a stale close-pending flag from the previous tenure.
        // M-1 修復：清除待處理平倉鎖，防止同名交易對重新加入時繼承過期標記。
        self.pending_close_symbols.remove(symbol);
        // M-1 fix: purge stale ADL alerts for removed symbol (ring-buffer cap=50, minor but clean).
        // M-1 修復：清除已移除交易對的過期 ADL 警報（環形緩衝上限 50，次要但乾淨）。
        self.adl_alerts.retain(|(_, sym, _)| sym != symbol);
    }

    /// PH5-WIRE-1: Inject JS shrunk edge estimates into the intent processor.
    /// PH5-WIRE-1：將 JS 收縮邊際估計注入意圖處理器。
    pub fn set_edge_estimates(&mut self, estimates: crate::edge_estimates::EdgeEstimates) {
        self.intent_processor.set_edge_estimates(estimates);
    }

    /// BLOCKER-3 D15: Wire shared cross-engine global exposure atomic.
    /// BLOCKER-3 D15：接入跨引擎全局曝險共享原子量。
    pub fn set_global_exposure(&mut self, exposure: std::sync::Arc<std::sync::atomic::AtomicU64>) {
        self.intent_processor.set_global_exposure(exposure);
    }

    /// W-3: Plug in a LinUCB runtime (read-only on the live path; metadata only).
    /// W-3：注入 LinUCB 運行時（live 路徑唯讀；僅 metadata）。
    pub fn set_linucb_runtime(&mut self, rt: std::sync::Arc<crate::linucb::LinUcbRuntime>) {
        self.linucb = Some(rt);
    }

    /// EDGE-P3-1 Phase B #1: Inject the per-engine `EdgePredictorStore` handle.
    /// Engine bootstrap in `main.rs` creates one store per PipelineKind
    /// (paper/demo/live) and passes the Arc here. Single call wires both sides:
    /// TickPipeline (for `handle_paper_command` IPC swap/clear) + IntentProcessor
    /// (for the §7.3 gate load_for lookup). Without the propagation, the IPC
    /// side would accept `SetEdgePredictorShadow` but the gate would still see
    /// `store = None` and short-circuit to legacy shrinkage.
    /// EDGE-P3-1 Phase B #1：注入本引擎的 `EdgePredictorStore` handle。
    /// 單次調用把 Arc 同時塞給 TickPipeline（IPC 熱換用）與 IntentProcessor
    /// （§7.3 gate load_for 讀取用）— 缺一會造成 IPC 收命令但 gate 仍走 legacy。
    pub fn set_edge_predictor_store(
        &mut self,
        store: std::sync::Arc<crate::edge_predictor::EdgePredictorStore>,
    ) {
        debug_assert!(
            self.edge_predictor_store.is_none(),
            "EdgePredictorStore injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.intent_processor
            .set_edge_predictor_store(store.clone());
        self.edge_predictor_store = Some(store);
    }

    /// EDGE-P3-1 A4 + B wiring: inject the PipelineCommand sender used by the
    /// IntentProcessor predictor gate to emit `EmitShadowFill` for ε-greedy
    /// paper exploration (spec §7.3). Without this bootstrap call the gate's
    /// `emit_shadow_fill` path hits the fail-soft `None` drop branch and all
    /// shadow fills are silently discarded — breaking Stage 4 paper learning.
    /// EDGE-P3-1 A4 + B 接線：注入 PipelineCommand 發送端供 IntentProcessor
    /// predictor gate 在 ε-greedy paper 探索時發出 `EmitShadowFill`（spec §7.3）。
    /// 缺此接線則 shadow fill 走 fail-soft 丟棄分支，Stage 4 paper 學習失效。
    pub fn set_shadow_fill_tx(&mut self, tx: tokio::sync::mpsc::UnboundedSender<PipelineCommand>) {
        self.intent_processor.set_shadow_fill_tx(tx);
    }

    /// EDGE-P3-1 Step 7a: Wire the decision-feature DB channel. Single call
    /// registers the tx for both the IntentProcessor (internal producer — one
    /// row per gate eval) and the `DecisionFeatureSnapshot` IPC passthrough
    /// handler. `None` leaves emission as no-op (fail-soft). Call exactly
    /// once per pipeline during bootstrap.
    /// EDGE-P3-1 Step 7a：把決策特徵 DB 通道同時接給 IntentProcessor（內部 producer）
    /// 與 `DecisionFeatureSnapshot` IPC passthrough。未接線時為 no-op（fail-soft）。
    /// 每個 pipeline 啟動時只呼叫一次。
    pub fn set_decision_feature_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>,
    ) {
        debug_assert!(
            self.decision_feature_tx.is_none(),
            "decision_feature_tx injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.intent_processor.set_decision_feature_tx(tx.clone());
        self.decision_feature_tx = Some(tx);
    }

    /// EDGE-P3-1 Step 7a: Accessor for the `DecisionFeatureSnapshot` IPC
    /// handler. Returns `None` until `set_decision_feature_tx` has been called.
    /// EDGE-P3-1 Step 7a：IPC handler 用的 tx 取用器；未接線前返回 None。
    pub fn decision_feature_tx(
        &self,
    ) -> Option<&tokio::sync::mpsc::Sender<crate::database::DecisionFeatureMsg>> {
        self.decision_feature_tx.as_ref()
    }

    /// EDGE-P3-1 Step 7c: Wire the shadow-fill DB channel. Call exactly once
    /// per pipeline during bootstrap. `None` leaves emission as fail-soft
    /// no-op (predictor gate still runs; Stage-4 exploration rows just not
    /// persisted).
    /// EDGE-P3-1 Step 7c：接 shadow-fill DB 通道，每 pipeline 只呼叫一次。
    /// 未接線時發射為 fail-soft no-op（gate 仍運作，僅 Stage-4 列不持久化）。
    pub fn set_shadow_fill_db_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::ShadowFillMsg>,
    ) {
        debug_assert!(
            self.shadow_fill_db_tx.is_none(),
            "shadow_fill_db_tx injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.shadow_fill_db_tx = Some(tx);
    }

    /// EDGE-P3-1 Step 7c: Accessor for the `EmitShadowFill` IPC handler.
    /// Returns `None` until `set_shadow_fill_db_tx` has been called.
    /// EDGE-P3-1 Step 7c：IPC handler 用的 tx 取用器；未接線前返回 None。
    pub fn shadow_fill_db_tx(
        &self,
    ) -> Option<&tokio::sync::mpsc::Sender<crate::database::ShadowFillMsg>> {
        self.shadow_fill_db_tx.as_ref()
    }

    /// EXIT-FEATURES-TABLE-1: Wire the exit-feature DB channel. Call exactly
    /// once per pipeline during bootstrap (main.rs passes the same writer tx
    /// to all three engines — multi-producer is safe). `None` leaves emission
    /// as fail-soft no-op (trading unaffected, just no Track P label collection).
    /// EXIT-FEATURES-TABLE-1：接 exit-feature DB 通道；每 pipeline 啟動時呼叫一次。
    /// 未接線時 emit_close_fill 走 fail-soft no-op。
    pub fn set_exit_feature_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::ExitFeatureRow>,
    ) {
        debug_assert!(
            self.exit_feature_tx.is_none(),
            "exit_feature_tx injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.exit_feature_tx = Some(tx);
    }

    /// EXIT-FEATURES-TABLE-1: Accessor for the `emit_close_fill` producer
    /// path. Returns `None` until `set_exit_feature_tx` has been called.
    /// EXIT-FEATURES-TABLE-1：emit_close_fill 產生器的 tx 取用器；未接線前回 None。
    pub fn exit_feature_tx(
        &self,
    ) -> Option<&tokio::sync::mpsc::Sender<crate::database::ExitFeatureRow>> {
        self.exit_feature_tx.as_ref()
    }

    /// INFRA-PREBUILD-1 Part A (2026-04-23): Wire the shadow-exit DB channel.
    /// Called once per pipeline at bootstrap. `None` keeps emission as
    /// fail-soft no-op (trading unaffected; Combine Layer shadow dormant).
    /// INFRA-PREBUILD-1 A 部：接 shadow-exit DB 通道；每 pipeline 啟動時呼叫一次。
    /// 未接線時 fail-soft no-op（交易不受影響；shadow dormant）。
    pub fn set_shadow_exit_tx(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::ShadowExitMsg>,
    ) {
        debug_assert!(
            self.shadow_exit_tx.is_none(),
            "shadow_exit_tx injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.shadow_exit_tx = Some(tx);
    }

    /// INFRA-PREBUILD-1 Part A: Accessor for the Combine Layer close-path
    /// producer. Returns `None` until `set_shadow_exit_tx` is called.
    /// INFRA-PREBUILD-1 A 部：Combine Layer close-path 的 tx 取用器。
    pub fn shadow_exit_tx(
        &self,
    ) -> Option<&tokio::sync::mpsc::Sender<crate::database::ShadowExitMsg>> {
        self.shadow_exit_tx.as_ref()
    }

    /// W-B: Wire Agent Decision Spine runtime shadow lineage. Fail-soft:
    /// missing tx or Disabled mode leaves trading untouched and emits nothing.
    /// W-B：接 Agent Decision Spine runtime shadow lineage；缺 tx 或 Disabled 時 no-op。
    pub fn set_agent_spine_runtime(
        &mut self,
        tx: Option<tokio::sync::mpsc::Sender<crate::agent_spine::store::AgentSpineMsg>>,
        mode: crate::agent_spine::config::AgentSpineMode,
    ) {
        debug_assert!(
            self.agent_spine_tx.is_none(),
            "agent_spine_tx injected twice — bootstrap should call this exactly once per pipeline"
        );
        self.agent_spine_tx = tx;
        self.agent_spine_mode = mode;
    }

    /// EXIT-FEATURES-TABLE-1: Read-only accessor to the pre-existing
    /// `price_tracker` used both by fast_track and the exit-feature ROC
    /// computation. Exposed so `emit_close_fill` can compute `price_roc_short`
    /// without duplicating the per-tick sample feed already wired in `on_tick`.
    /// EXIT-FEATURES-TABLE-1：價格追蹤器的唯讀取用器；emit_close_fill 用來計算
    /// price_roc_short，避免重複 per-tick 樣本饋入。
    pub fn price_tracker(&self) -> &PriceHistoryTracker {
        &self.price_tracker
    }

    /// EXIT-FEATURES-TABLE-1 (tests only): mutable handle so unit tests can
    /// seed price samples for ROC / ATR / giveback assertions without
    /// spinning a full on_tick loop. Not used in production paths.
    /// EXIT-FEATURES-TABLE-1（僅測試）：測試用可變 handle，用來預填價格樣本
    /// 做 ROC/ATR/giveback 斷言，無需走完整 on_tick。非生產路徑。
    #[cfg(test)]
    pub(crate) fn price_tracker_mut(&mut self) -> &mut PriceHistoryTracker {
        &mut self.price_tracker
    }

    /// EDGE-P3-1 Phase B #4: Reseed the IntentProcessor predictor RNG.
    /// Bootstrap should call this exactly once per pipeline with
    /// `seed_for_engine(startup_nanos, kind)` so paper/demo/live each get a
    /// distinct ε-greedy stream (spec §7.3 F9). Without this call every engine
    /// runs with the constructor default `SmallRng::seed_from_u64(0)` — all
    /// three engines produce identical exploration draws and the per-kind
    /// discriminant XOR in `seed_for_engine` is inert.
    /// EDGE-P3-1 Phase B #4：重置 IntentProcessor predictor RNG。
    /// 啟動時以 `seed_for_engine(startup_nanos, kind)` 每個 pipeline 呼叫一次；
    /// 不做則三引擎共用 seed=0，kind 互異失去意義。
    pub fn set_predictor_rng_seed(&mut self, seed: u64) {
        self.intent_processor.set_predictor_rng_seed(seed);
    }

    /// EDGE-P3-1 Stage 0: Accessor for command handlers that need to mutate
    /// the store (swap / clear). Returns `None` until `set_edge_predictor_store`
    /// is called.
    /// EDGE-P3-1 Stage 0：命令 handler 用的 store 取用器；未注入前返回 None。
    pub fn edge_predictor_store(
        &self,
    ) -> Option<&std::sync::Arc<crate::edge_predictor::EdgePredictorStore>> {
        self.edge_predictor_store.as_ref()
    }

    /// EDGE-P3-1 Step 7e: Accessor for command handlers that need to mutate
    /// the live `RiskConfig` (e.g. `DisableEdgePredictorAll` two-phase commit
    /// flips `use_edge_predictor=false` on disk + ArcSwap before clearing the
    /// in-memory predictor slots). Returns `None` when the pipeline is running
    /// without a wired store — handler falls back to memory-only clear.
    /// EDGE-P3-1 Step 7e：命令 handler 用的 RiskConfig 取用器；未接線時 handler
    /// 退回 memory-only clear。
    pub fn risk_store(
        &self,
    ) -> Option<&std::sync::Arc<crate::config::ConfigStore<crate::config::RiskConfig>>> {
        self.risk_store.as_ref()
    }
}

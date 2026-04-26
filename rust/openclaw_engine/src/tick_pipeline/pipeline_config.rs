//! TickPipeline impl — config sync (risk / budget / maker_kpi / news / fee / account).
//! TickPipeline impl — 配置同步（risk / budget / maker_kpi / news / fee / account）。
//!
//! MODULE_NOTE (EN): Split out of `tick_pipeline/mod.rs` by TICK-PIPELINE-MOD-SPLIT-1
//!   (2026-04-22) to honour CLAUDE.md §七's 1200-line hard cap. Contains the
//!   config-store wiring setters + tick-level hot-reload helpers for
//!   RiskConfig / BudgetConfig / MakerKpiConfig / NewsContextSnapshot, and
//!   the fee-rate / AccountManager passthroughs into the IntentProcessor.
//!   `apply_risk_snapshot` stays private (callers: `set_risk_store` and
//!   `sync_risk_config_if_changed`, both in this file). The three helpers
//!   invoked from `on_tick/step_*` (`sync_risk_config_if_changed`,
//!   `sync_maker_kpi_config_if_changed`, `current_cost_edge_max_ratio`,
//!   `current_min_profit_to_close_pct`) were bumped to `pub(super)` for
//!   cross-module visibility.
//! MODULE_NOTE (中)：TICK-PIPELINE-MOD-SPLIT-1（2026-04-22）由 `tick_pipeline/mod.rs`
//!   拆出以遵守 CLAUDE.md §七 1200 行硬上限。本檔包含 RiskConfig / BudgetConfig /
//!   MakerKpiConfig / NewsContextSnapshot 的 config-store setter + tick-level
//!   熱重載 helper，以及 fee rate / AccountManager 透傳到 IntentProcessor。
//!   `apply_risk_snapshot` 保持 private（呼叫者：同檔 `set_risk_store` +
//!   `sync_risk_config_if_changed`）。`on_tick/step_*` 呼叫的 helper（
//!   `sync_risk_config_if_changed` / `sync_maker_kpi_config_if_changed` /
//!   `current_cost_edge_max_ratio` / `current_min_profit_to_close_pct`）
//!   升為 `pub(super)` 供跨模組呼叫。

use super::TickPipeline;

impl TickPipeline {
    /// W-4: Plug in a shared NewsContextSnapshot (read-only on the live path).
    /// W-4：注入共享 NewsContextSnapshot（live 路徑唯讀）。
    pub fn set_news_snapshot(&mut self, snap: std::sync::Arc<crate::news::NewsContextSnapshot>) {
        self.news_snapshot = Some(snap);
    }

    /// ARCH-RC1 1C-2-B: Inject the live RiskConfig ConfigStore handle. After
    /// wiring, the pipeline checks the store version at the top of each tick
    /// and refreshes the intent_processor's owned snapshot if the version has
    /// bumped (IPC patch applied). Also seeds the first snapshot immediately.
    /// ARCH-RC1 1C-2-B：注入 live RiskConfig ConfigStore。接線後每 tick 檢查
    /// 版本號，若上升（IPC patch 已套用）則刷新 intent_processor 快照。
    pub fn set_risk_store(
        &mut self,
        store: std::sync::Arc<crate::config::ConfigStore<crate::config::RiskConfig>>,
    ) {
        // Immediate sync so the first tick already sees the live config.
        let snap = store.load();
        self.apply_risk_snapshot(&snap);
        self.risk_config_version_seen = store.version();
        self.risk_store = Some(store);
    }

    /// ARCH-RC1 1C-2-B (Option B) + 1C-4 E-Merge-4: Push a RiskConfig snapshot
    /// into every downstream consumer that owns a derived copy. After E-Merge-4
    /// the Guardian is a **pure derived view** of RiskConfig — no RMW, every
    /// field is sourced from RiskConfig (modification_size_factor and
    /// modification_leverage_cap were promoted to RiskConfig.limits, and the
    /// dead `max_correlation` field on GuardianConfig was deleted). This means
    /// the operator GUI's `patch_risk_config` is now the SINGLE source of
    /// truth for every Guardian knob.
    /// ARCH-RC1 1C-2-B + 1C-4 E-Merge-4：把 RiskConfig 快照推到所有持派生 copy
    /// 的下游。E-Merge-4 後 Guardian 為 RiskConfig 的純派生視圖 — 無 RMW，
    /// 每個欄位皆從 RiskConfig 取值。modification_* 欄位升級至 RiskConfig.limits，
    /// 死欄位 max_correlation 已刪除。operator GUI 的 patch_risk_config 從此
    /// 是 Guardian 任何旋鈕的唯一真相源。
    fn apply_risk_snapshot(&mut self, snap: &crate::config::RiskConfig) {
        // 1. Update intent_processor's owned RiskConfig (used for cost_gate k_*,
        //    dynamic_stop tunables, and check_order_allowed via risk_config()).
        self.intent_processor.update_risk_config(snap.clone());

        // DYNAMIC-RISK-1: rebuild sizer from the fresh `dynamic_sizing` block
        // and re-anchor on `per_trade_risk_pct`. Config changes are operator-
        // originated (TOML hot-reload) — current_pct resets to base so drift
        // never accumulates across operator intents.
        // DYNAMIC-RISK-1：從新 dynamic_sizing 區塊重建,並以 per_trade_risk_pct
        // 重錨；config 變動皆 operator 觸發，current 回 base 避免跨 operator 意圖累積漂移。
        self.dynamic_risk_sizer = crate::dynamic_risk_sizer::DynamicRiskSizer::new(
            snap.limits.per_trade_risk_pct,
            snap.dynamic_sizing.clone(),
        );
        // Apply the base immediately so IntentProcessor reflects TOML intent until
        // the sizer earns enough data to deviate.
        // 立即把 base 推入 IntentProcessor，讓其反映 TOML 意圖，之後調整器累積足夠資料才偏移。
        self.intent_processor
            .set_p1_risk_pct(snap.limits.per_trade_risk_pct);

        // 2. Construct a fresh GuardianConfig fully derived from RiskConfig
        //    (no RMW). Every field below has a 1:1 source in `snap`.
        //    完整重建 GuardianConfig，無 RMW，每個欄位都對應 snap 內的單一來源。
        let gc = openclaw_core::guardian::GuardianConfig {
            max_leverage: snap.limits.leverage_max,
            max_drawdown_pct: snap.limits.session_drawdown_max_pct,
            max_same_direction_positions: snap.anti_cluster.max_same_direction as usize,
            modification_size_factor: snap.limits.guardian_modification_size_factor,
            modification_leverage_cap: snap.limits.guardian_modification_leverage_cap,
        };
        self.intent_processor.update_guardian_config(gc);

        // 3. ARCH-RC1 1C-2-F E-Merge-2: hot-reload H0Gate risk-level fields
        //    from RiskConfig.limits (RMW preserves health + shadow_mode fields
        //    that don't live in RiskConfig). Previously the H0GateConfig was
        //    only seeded at tick_pipeline construction from defaults and never
        //    updated — so an operator raising open_positions_max in RiskConfig
        //    would still hit the old cap at the H0 gate.
        //    ARCH-RC1 1C-2-F E-Merge-2：H0Gate 的風控層欄位從 RiskConfig.limits
        //    熱重載（RMW 保留健康欄位與 shadow_mode）。
        let mut h0 = self.h0_gate.config().clone();
        h0.max_open_positions = snap.limits.open_positions_max;
        h0.max_total_exposure_pct = snap.limits.total_exposure_max_pct;
        h0.allowed_categories = snap.limits.allowed_categories.clone();
        self.h0_gate.update_config(h0);

        // 4. ARCH-RC1 1C-2-F E-Merge-1 (downgraded): hot-reload the legacy
        //    paper_state.stop_config so the H0-blocked / paused protective
        //    fallback stops at tick_pipeline.rs:910 + :1017 use the operator-
        //    current RiskConfig values, not stale boot defaults. The research
        //    agent confirmed those two call sites are intentional protective
        //    fallbacks (main engine evaluate_positions never runs in their
        //    early-return branches), so stop_manager is KEPT but its owned
        //    StopConfig must now track RiskConfig.
        //    Trailing / time stops stay None on paper_state because the
        //    main engine owns them; the fallback only needs hard + TP to
        //    prevent unbounded losses during gate block / pause.
        //    ARCH-RC1 1C-2-F E-Merge-1 (降級版)：熱重載 paper_state.stop_config，
        //    讓 H0 阻擋 / 暫停時的 fallback 止損使用 operator 最新的 RiskConfig
        //    值，而非啟動時的 defaults。Research agent 確認 910/1017 是故意的
        //    保護 fallback，因此 stop_manager 保留，只把它的 owned 配置拉齊。
        self.paper_state
            .set_hard_stop_pct(snap.limits.stop_loss_max_pct);
        if snap.limits.take_profit_enforced {
            self.paper_state
                .set_take_profit_pct(Some(snap.limits.take_profit_max_pct));
        } else {
            self.paper_state.set_take_profit_pct(None);
        }
        // EVICT-ON-DUST F3 (PA §1.2.6): mirror RiskConfig.limits.ft_dust_qty_floor_usd
        // into paper_state so apply_fill / reduce_position post-mutation evict
        // (T1/T2) reads the live floor without a fresh ConfigStore::load() on
        // the hot path. Re-uses af48ee1 schema; no new field. Hot-reload picks
        // up operator TOML edits via the same `risk_config_version_seen` path
        // that drives every other Guardian / paper_state knob.
        // EVICT-ON-DUST F3：將 ft_dust_qty_floor_usd 鏡射進 paper_state，
        // hot-path 後置 evict 直接讀 self.dust_floor_usd 不再多 1 層
        // ConfigStore 跳轉。沿用 af48ee1 既有 schema、無新欄位；operator TOML
        // 變更走既有版本號熱重載通道，與其他 Guardian / paper_state 旋鈕一致。
        self.paper_state
            .set_dust_floor_usd(snap.limits.ft_dust_qty_floor_usd);

        // 5. ARCH-RC1 1C-2-F E-Merge-3: hot-reload RiskGovernorSm.thresholds
        //    from RiskConfig.cascade. Previously the 6-tier cascade state
        //    machine carried its own hardcoded EscalationThresholds::default()
        //    with NO path to operator override. Field names differ slightly
        //    (circuit_breaker_pct vs circuit_pct, consecutive_loss_ vs
        //    consec_loss_, min_hold_time_ms vs min_hold_ms) but semantics are
        //    identical — map 1-to-1 and push.
        //    ARCH-RC1 1C-2-F E-Merge-3：把 RiskGovernorSm 的閾值從
        //    RiskConfig.cascade 熱重載進來；原本它只讀自己的硬編碼 default。
        let c = &snap.cascade;
        self.governance.risk.thresholds = openclaw_core::sm::risk_gov::EscalationThresholds {
            drawdown_cautious_pct: c.drawdown_cautious_pct,
            drawdown_reduced_pct: c.drawdown_reduced_pct,
            drawdown_defensive_pct: c.drawdown_defensive_pct,
            drawdown_circuit_breaker_pct: c.drawdown_circuit_pct,
            daily_loss_cautious_pct: c.daily_loss_cautious_pct,
            daily_loss_reduced_pct: c.daily_loss_reduced_pct,
            daily_loss_circuit_breaker_pct: c.daily_loss_circuit_pct,
            consecutive_loss_cautious: c.consec_loss_cautious,
            consecutive_loss_reduced: c.consec_loss_reduced,
            consecutive_loss_circuit_breaker: c.consec_loss_circuit,
            pressure_cautious: c.pressure_cautious,
            pressure_reduced: c.pressure_reduced,
            pressure_defensive: c.pressure_defensive,
            pressure_circuit_breaker: c.pressure_circuit,
            min_hold_time_ms: c.min_hold_ms,
        };
    }

    /// ARCH-RC1 1C-2-B: Inject the live BudgetConfig ConfigStore handle for
    /// the cost-edge hot-path read (`attention_tax.cost_edge_max_ratio`).
    /// ARCH-RC1 1C-2-B：注入 live BudgetConfig ConfigStore，供熱路徑讀
    /// attention_tax.cost_edge_max_ratio。
    pub fn set_budget_store(
        &mut self,
        store: std::sync::Arc<crate::config::ConfigStore<crate::config::BudgetConfig>>,
    ) {
        self.budget_store = Some(store);
    }

    /// ARCH-RC1 1C-2-B: Hot-reload hook called at the top of on_tick. If the
    /// risk store's version has bumped since last check, pull the latest
    /// snapshot into the intent_processor (which still owns a plain copy for
    /// its fine-grained patch_* methods). Cheap: one atomic load + equality.
    /// ARCH-RC1 1C-2-B：on_tick 頂部呼叫的熱重載檢查。store 版本號若有變化，
    /// 拉最新快照餵給 intent_processor。極低成本（一次原子 load + 相等比較）。
    #[inline]
    pub(super) fn sync_risk_config_if_changed(&mut self) {
        if let Some(ref store) = self.risk_store {
            let v = store.version();
            if v != self.risk_config_version_seen {
                let snap = store.load();
                self.apply_risk_snapshot(&snap);
                self.risk_config_version_seen = v;
                tracing::info!(
                    new_version = v,
                    "ARCH-RC1 risk config hot-reloaded (pipeline + guardian)"
                );
            }
        }
    }

    /// EDGE-P2-3 Phase 1B-5: Inject the live MakerKpiConfig ConfigStore handle.
    /// After wiring, the pipeline seeds the owned `maker_kpi_config` copy from
    /// the current snapshot and records the version so the next tick-level
    /// sync no-ops. Subsequent operator patches bump the version and the
    /// next `on_tick` picks up the new snapshot via
    /// `sync_maker_kpi_config_if_changed`.
    /// EDGE-P2-3 Phase 1B-5：注入 live MakerKpiConfig ConfigStore。接線後立即把
    /// 當前快照播入 owned `maker_kpi_config` 並記錄版本號，後續 tick 同步
    /// 在未升版時 no-op；operator patch 升版後下一個 `on_tick` 自動拾取。
    pub fn set_maker_kpi_store(
        &mut self,
        store: std::sync::Arc<crate::config::ConfigStore<crate::paper_state::MakerKpiConfig>>,
    ) {
        // Immediate sync so the first tick already sees the live config.
        // Push to the router-facing IntentProcessor snapshot too, so a
        // `set_maker_kpi_store` wired before any ticks run still leaves the
        // router's KPI gate reading the live thresholds (not the
        // constructor's `MakerKpiConfig::default()` placeholder).
        // 立即同步：首個 tick 就看到 live 快照；同步推入 IntentProcessor，
        // 避免 `set_maker_kpi_store` 於首個 tick 之前接線時，router 的
        // KPI gate 仍讀到建構子預設值。
        let snap = store.load();
        let fresh = (*snap).clone();
        self.intent_processor.update_maker_kpi_config(fresh.clone());
        self.maker_kpi_config = fresh;
        self.maker_kpi_version_seen = store.version();
        self.maker_kpi_store = Some(store);
    }

    /// EDGE-P2-3 Phase 1B-5: Hot-reload hook called at the top of on_tick.
    /// Mirrors `sync_risk_config_if_changed`: compare the store's monotonic
    /// version to `maker_kpi_version_seen`; on bump, pull the snapshot into
    /// the owned `maker_kpi_config` copy (used by the paper sweep) AND push
    /// the same snapshot into `IntentProcessor.maker_kpi_config` so the
    /// router's PostOnly KPI gate picks up the patched thresholds on the
    /// very next routed intent — without any `ArcSwap::load()` inside the
    /// tick hot path for subsequent ticks.
    /// EDGE-P2-3 Phase 1B-5：`on_tick` 頂部的熱重載檢查。與
    /// `sync_risk_config_if_changed` 同模式：比對版本，升版時把快照寫進
    /// owned `maker_kpi_config`（紙盤 sweep 使用），並推入
    /// `IntentProcessor.maker_kpi_config` 讓 router PostOnly KPI gate 下一筆
    /// 意圖即見新門檻；後續 tick 無需再觸發 `ArcSwap::load()`。
    #[inline]
    pub(super) fn sync_maker_kpi_config_if_changed(&mut self) {
        if let Some(ref store) = self.maker_kpi_store {
            let v = store.version();
            if v != self.maker_kpi_version_seen {
                let snap = store.load();
                let fresh = (*snap).clone();
                self.intent_processor.update_maker_kpi_config(fresh.clone());
                self.maker_kpi_config = fresh;
                self.maker_kpi_version_seen = v;
                tracing::info!(
                    new_version = v,
                    funding_drag_threshold = self.maker_kpi_config.funding_drag_threshold,
                    min_fill_rate = self.maker_kpi_config.min_fill_rate,
                    min_avg_net_edge_bps = self.maker_kpi_config.min_avg_net_edge_bps,
                    "EDGE-P2-3 1B-5 maker KPI config hot-reloaded"
                );
            }
        }
    }

    /// ARCH-RC1 1C-2-B: Read the live `cost_edge_max_ratio` for the tick-level
    /// cost-edge check. Falls back to the production default (MICRO-PROFIT-FIX-1
    /// 0.2) when BudgetConfig store is not wired (1C-1 / unit-test paths).
    /// ARCH-RC1 1C-2-B：熱路徑讀取 live cost_edge_max_ratio；store 未接線時回退
    /// 當前 default（MICRO-PROFIT-FIX-1 後為 0.2）。
    #[inline]
    pub(super) fn current_cost_edge_max_ratio(&self) -> f64 {
        match self.budget_store.as_ref() {
            Some(store) => store.load().attention_tax.cost_edge_max_ratio,
            None => 0.2,
        }
    }

    /// MICRO-PROFIT-FIX-1 (2026-04-17): Read the live `min_profit_to_close_pct`
    /// floor for the COST EDGE gate's narrow lock-in band. Falls back to the
    /// production default (0.3%) when BudgetConfig store is not wired
    /// (1C-1 / unit-test paths).
    /// MICRO-PROFIT-FIX-1：熱路徑讀取 live min_profit_to_close_pct；未接線時回退 0.3。
    #[inline]
    pub(super) fn current_min_profit_to_close_pct(&self) -> f64 {
        match self.budget_store.as_ref() {
            Some(store) => store.load().attention_tax.min_profit_to_close_pct,
            None => 0.3,
        }
    }

    /// Set dynamic fee rate from API for more accurate paper trading cost.
    /// 設定 API 動態費率，提高紙盤交易成本精確度。
    pub fn set_fee_rate(&mut self, rate: f64) {
        self.intent_processor.set_fee_rate(rate);
    }

    /// Wire AccountManager for live per-symbol fee lookups.
    /// 接入 AccountManager 用於 per-symbol 真實費率查詢。
    pub fn set_account_manager(
        &mut self,
        am: std::sync::Arc<crate::account_manager::AccountManager>,
    ) {
        self.intent_processor.set_account_manager(am);
    }
}

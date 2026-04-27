//! RiskConfig — Authoritative risk control configuration (ARCH-RC1).
//! RiskConfig — 風控權威配置。
//!
//! MODULE_NOTE (EN): One of the three hot-reload Configs in ARCH-RC1, and the
//!   single source of truth for ALL risk decisions: P0 category overrides,
//!   P1 operator hard ceilings, P2 agent self-tunable params, 6-level RiskGovernor
//!   cascade thresholds, regime multipliers, cost gate, dynamic stop, market
//!   gate (microstructure), anti-cluster, correlation, and runtime knobs.
//!   `partial_tp_*` lives in agent (P2) here, NOT in LearningConfig — coupled
//!   to take_profit_max_pct so they share the same Config validate path.
//!   Tick path reads via `Arc<ArcSwap<RiskConfig>>` for ~5ns lock-free snapshot.
//! MODULE_NOTE (中): ARCH-RC1 三個熱重載 Config 之一，所有風控決策的單一真相來源：
//!   P0 品類覆蓋、P1 操作員硬上限、P2 Agent 自我調整、6 級 RiskGovernor cascade
//!   閾值、regime 乘數、cost gate、動態 stop、market gate（微結構）、anti-cluster、
//!   correlation、runtime knobs。`partial_tp_*` 在這裡的 agent (P2)，不在
//!   LearningConfig —— 與 take_profit_max_pct 耦合所以同 Config validate。
//!   Tick 路徑透過 `Arc<ArcSwap<RiskConfig>>` 無鎖快照（~5ns）。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::exit_features::ExitConfig;

// G1-03 Wave 1 Rust refactor (2026-04-24): advanced sub-configs extracted to
// risk_config_advanced.rs sibling to bring this file under §九 1200-line limit.
// G1-03 Wave 1 Rust refactor（2026-04-24）：進階子配置抽至 sibling。
#[path = "risk_config_advanced.rs"]
mod advanced;
pub use advanced::{
    AntiCluster, Correlation, CusumConfig, DynamicStop, EdgePredictor, EdgePredictorFallback,
    EwmaVolConfig, ExecutorConfig, Experimental, GridOuConfig, MarketGate, RuntimeKnobs,
    SlippageConfig, SlippageTier, StrategistConfig,
};

// G7-03 (2026-04-24): Hurst + hysteresis regime detector schema lives in its
// own sibling file (per §九 file-size discipline — `risk_config_advanced.rs`
// already at ~1198 lines, 2 from the 1200-line cap).
// G7-03：Hurst + hysteresis schema 在獨立 sibling 檔，符合 §九 行數規範。
#[path = "risk_config_regime.rs"]
pub mod regime_cfg;
pub use regime_cfg::HurstConfig;

// G3-09 Phase A (2026-04-27): cost_edge_advisor schema lives in its own
// sibling file (`risk_config_advanced.rs` at 1297 lines, well over the §九
// 1200 hard cap; piling more onto it compounds the violation). Pattern
// mirrors `risk_config_regime.rs` (HurstConfig sibling).
// G3-09 Phase A：cost_edge schema 落在獨立 sibling 檔，避免再壓縮已超標
// 的 advanced 檔；對齊 regime_cfg sibling 拆分模式。
#[path = "risk_config_cost_edge.rs"]
pub mod cost_edge_cfg;
pub use cost_edge_cfg::CostEdgeConfig;

// ---------------------------------------------------------------------------
// Top-level / 頂層
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Meta {
    #[serde(default = "default_meta_version")]
    pub version: u32,
    #[serde(default)]
    pub saved_ts_ms: u64,
}

fn default_meta_version() -> u32 {
    1
}

impl Default for Meta {
    fn default() -> Self {
        Self {
            version: default_meta_version(),
            saved_ts_ms: 0,
        }
    }
}

/// Complete risk configuration (ARCH-RC1).
/// 完整風控配置。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct RiskConfig {
    #[serde(default)]
    pub meta: Meta,
    #[serde(default)]
    pub limits: GlobalLimits,
    #[serde(default)]
    pub overrides: CategoryOverrides,
    #[serde(default)]
    pub per_strategy: HashMap<String, StrategyOverride>,
    #[serde(default)]
    pub agent: AgentParams,
    #[serde(default)]
    pub cascade: CascadeThresholds,
    #[serde(default)]
    pub regime: RegimeMultipliers,
    #[serde(default)]
    pub cost_gate: CostGate,
    #[serde(default)]
    pub edge_predictor: EdgePredictor,
    #[serde(default)]
    pub dynamic_stop: DynamicStop,
    #[serde(default)]
    pub market_gate: MarketGate,
    #[serde(default)]
    pub anti_cluster: AntiCluster,
    #[serde(default)]
    pub correlation: Correlation,
    #[serde(default)]
    pub runtime: RuntimeKnobs,
    /// DUAL-TRACK-EXIT-1 Track P: Physical-layer exit config (non-linear
    /// giveback v2). Drives Priority 6 `physical_micro_profit_lock_v2` in
    /// `risk_checks::check_position_on_tick`. Hot-reloaded via
    /// `Arc<ArcSwap<RiskConfig>>`.
    ///
    /// TRACK-P-V2-SWAP-1 (2026-04-22): replaced linear `PhysLockConfig` with
    /// `ExitConfig` defined in `exit_features::v2`. See that module for the
    /// non-linear giveback threshold (`base - slope × peak_atr_norm`, bounded
    /// below by `floor`) which replaces the former single fixed threshold.
    ///
    /// DUAL-TRACK-EXIT-1 Track P：物理層退出參數（v2 非線性 giveback）。
    /// 驅動 `risk_checks::check_position_on_tick` 的 Priority 6
    /// `physical_micro_profit_lock_v2`，透過 `Arc<ArcSwap<RiskConfig>>` 熱重載。
    /// TRACK-P-V2-SWAP-1（2026-04-22）：線性 `PhysLockConfig` 換為
    /// `exit_features::v2::ExitConfig`，threshold 由固定值改非線性。
    #[serde(default, alias = "phys_lock")]
    pub exit: ExitConfig,
    #[serde(default)]
    pub experimental: Experimental,
    /// DYNAMIC-RISK-1: Sharpe-aware dynamic `per_trade_risk_pct` sizer.
    /// Hot-reloadable; disabled by default. See `dynamic_risk_sizer.rs`.
    /// DYNAMIC-RISK-1：Sharpe 動態 `per_trade_risk_pct` 調整器，可熱重載，預設停用。
    #[serde(default)]
    pub dynamic_sizing: crate::dynamic_risk_sizer::DynamicRiskSizerConfig,
    /// G7-01 (2026-04-24): Kelly fractional-tier sample-size boundaries.
    /// Operator-tunable knob for `ml::kelly_sizer::compute_kelly_qty`'s
    /// young/mature/established tier classification (defaults 50/200 mirror
    /// the pre-G7-01 hardcoded constants).
    /// G7-01：Kelly 分層樣本量邊界（young/mature/established）。
    /// `ml::kelly_sizer::compute_kelly_qty` 的可調 knob，預設 50/200 保留原行為。
    #[serde(default)]
    pub kelly: KellyTierConfig,
    /// G3-02 Phase A (2026-04-25): ExecutorAgent shadow→live control plane.
    /// Per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--g3_01_executor_agent_ipc_rfc.md`,
    /// hosts the canonical `shadow_mode` + `max_position_pct` knobs that
    /// previously lived as a hardcoded Python class attribute. Phase A lands
    /// the schema + TOML section only; Phase B (Python read path) and Phase C
    /// (operator IPC flip) follow. Default `shadow_mode=true` preserves
    /// current ExecutorAgent behavior — no risk surface change in Phase A.
    /// G3-02 Phase A：ExecutorAgent shadow→live 控制平面 schema 落地；Python
    /// 讀取路徑（Phase B）+ operator IPC flip（Phase C）後續完成。
    /// 預設 shadow_mode=true 保留現行為，Phase A 不改 risk 表面。
    #[serde(default)]
    pub executor: ExecutorConfig,
    /// G7-02 (2026-04-24): Per-timeframe EWMA Vol lambda decay constants.
    /// `default_lambda` defaults to `0.97` to preserve the pre-G7-02
    /// hardcoded behavior; operators may add timeframe-keyed overrides
    /// ("1m" / "5m" / "1h" / "4h" …). Hot-reloaded with the rest of
    /// `RiskConfig` via `Arc<ArcSwap<RiskConfig>>`.
    /// G7-02：逐 timeframe EWMA Vol lambda；預設 0.97 保留 G7-02 前行為。
    #[serde(default)]
    pub ewma_vol: EwmaVolConfig,
    /// G7-04 (2026-04-24): CUSUM strategy edge-decay monitor schema.
    /// One-sided downward CUSUM control chart parameters
    /// (`slack_k` deadband + `threshold_h` alarm boundary, both in σ units;
    /// `min_observations` warm-up; `target_return_bps` reference level).
    /// Phase A schema landing only: defaults `enabled = false` so this struct
    /// is dormant and `dynamic_risk_sizer` / strategy disable hooks see no
    /// behavioural change. Wiring deferred to a future G7-04 follow-up.
    /// G7-04：CUSUM 策略衰減監控 schema；Phase A 預設 enabled=false 不接 runtime，
    /// 後續 follow-up 補 wiring。
    #[serde(default)]
    pub cusum: CusumConfig,
    /// G7-07 (2026-04-24): Cost-gate slippage tiers + win-rate weighting knobs.
    /// Replaces the hardcoded `SLIPPAGE_TIERS` / `DEFAULT_SLIPPAGE_RATE`
    /// constants in `intent_processor::mod` and the literal `0.3` / `1.3`
    /// in `cost_gate_{paper, moderate, live}`. Defaults preserve pre-G7-07
    /// behaviour bit-identically. Hot-reloaded via `Arc<ArcSwap<RiskConfig>>`.
    /// G7-07：成本門滑點分級 + 勝率加權 knob；替換 intent_processor 中
    /// SLIPPAGE_TIERS / DEFAULT_SLIPPAGE_RATE 與 cost_gate_* 中的字面量
    /// 0.3 / 1.3。預設保持 G7-07 前行為 bit-identical，可熱重載。
    #[serde(default)]
    pub slippage: SlippageConfig,
    /// G7-06 (2026-04-24): Grid OU residual-based σ estimator schema.
    /// Configures the rolling-window residual-stdev estimator used (in Phase B)
    /// by `grid_helpers::compute_ou_step` to replace the raw-Δx σ path with a
    /// proper OU-residual σ̂ = sqrt(Σ e²/(n-1)). Phase A schema-only landing:
    /// defaults `use_residual_sigma = false` keep the runtime bit-identical
    /// to pre-G7-06 behavior. Hot-reloaded via `Arc<ArcSwap<RiskConfig>>`.
    /// G7-06：Grid OU 殘差 σ 估計器 schema；Phase A 預設 use_residual_sigma=false
    /// 保留現行為（compute_ou_step 用原始 Δx stdev），Phase B 接 wire 後切換。
    #[serde(default)]
    pub grid_ou: GridOuConfig,
    /// G7-03 (2026-04-24): Hurst exponent + hysteresis regime detector schema.
    /// Wraps `openclaw_core::indicators::volatility::hurst` (single-source-of-
    /// truth R/S analysis) with a typed `RegimeLabel` and a configurable
    /// `HysteresisDetector` (lag-based label stabilizer). Phase A schema-only
    /// landing: defaults `enabled = false` so `regime::hurst::hurst_label_for_symbol`
    /// short-circuits to `None` and runtime is bit-identical to pre-G7-03.
    /// Phase B will wire per-symbol `HysteresisDetector` cache into the tick
    /// pipeline / scanner — operators flip `enabled = true` per environment.
    /// Hot-reloaded via `Arc<ArcSwap<RiskConfig>>`.
    /// G7-03：Hurst + 滯回 regime 偵測 schema；Phase A 預設 enabled=false 完全 no-op。
    #[serde(default)]
    pub hurst: HurstConfig,
    /// STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): StrategistScheduler param
    /// tuner clamp. Lifts the pre-config `MAX_PARAM_DELTA_PCT = 0.30` constant
    /// in `strategist_scheduler/mod.rs:48` into IPC-hot-reloadable config.
    /// Default `0.30` preserves bit-identical pre-extraction behaviour;
    /// operators tune via TOML or `patch_risk_config` IPC (deep-merge already
    /// supports this sub-struct). Per-param overrides are deferred to v2.
    /// STRATEGIST-TUNE-TARGET-CONFIG-1：策略師調參 delta 上限可配置；預設 0.30
    /// 與原硬編碼一致，operator 可 IPC 熱重載；v2 再做 per-param。
    #[serde(default)]
    pub strategist: StrategistConfig,
    /// G3-09 Phase A (2026-04-27): cost_edge_advisor schema. Lifts CLAUDE.md §二
    /// 原則 #13 「AI 資源成本感知」into ConfigStore as a hot-reloadable field.
    /// Phase A defaults: `enabled = false` (dormant) + `trigger_threshold = -0.5`
    /// (per PM Tier 9 T9-LOW-1 lock-in). Phase A landing has zero runtime impact
    /// (advisor evaluation cycle returns Disabled when enabled=false). Phase B
    /// (shadow dry-run) + Phase C (gate 新倉) flip the flag and wire IntentProcessor.
    /// G3-09 Phase A：cost_edge_advisor schema 落地。預設 `enabled=false`（dormant）
    /// + `trigger_threshold=-0.5`（PM Tier 9 lock-in）；Phase A runtime 零影響。
    #[serde(default)]
    pub cost_edge: CostEdgeConfig,
}

impl RiskConfig {
    /// Validate cross-field invariants. Cross-Config dependencies are checked
    /// elsewhere (DirectiveApplier etc.).
    /// 驗證跨欄位不變量。跨 Config 依賴在別處檢查（DirectiveApplier 等）。
    pub fn validate(&self) -> Result<(), String> {
        self.limits.validate()?;
        self.agent.validate()?;
        self.cascade.validate()?;
        self.regime.validate()?;
        self.cost_gate.validate()?;
        self.edge_predictor.validate()?;
        self.dynamic_stop.validate()?;
        self.market_gate.validate()?;
        self.anti_cluster.validate()?;
        self.correlation.validate()?;
        self.runtime.validate()?;
        self.exit.validate().map_err(|e| format!("risk.exit: {}", e))?;
        self.dynamic_sizing.validate()?;
        self.kelly.validate()?;
        self.executor.validate()?;
        self.ewma_vol.validate()?;
        self.cusum.validate()?;
        self.slippage.validate()?;
        self.grid_ou.validate()?;
        self.hurst
            .validate()
            .map_err(|e| format!("risk.hurst: {}", e))?;
        self.strategist.validate()?;
        self.cost_edge.validate()?;

        // Cross-sub-struct invariant: partial_tp levels must not exceed take_profit_max_pct.
        // 跨 sub-struct 不變量：partial_tp 各層不得超過 take_profit_max_pct。
        if self.agent.partial_tp_enabled {
            for (i, (pct, frac)) in self.agent.partial_tp_levels.iter().enumerate() {
                if *pct > self.limits.take_profit_max_pct {
                    return Err(format!(
                        "risk.agent.partial_tp_levels[{}] pct {} exceeds risk.limits.take_profit_max_pct {}",
                        i, pct, self.limits.take_profit_max_pct
                    ));
                }
                if !(0.0..=1.0).contains(frac) {
                    return Err(format!(
                        "risk.agent.partial_tp_levels[{}] fraction {} must be in [0, 1]",
                        i, frac
                    ));
                }
            }
        }

        // Cross-sub-struct: min_order_notional must allow at least one position.
        // 跨 sub-struct：min_order_notional 必須允許至少一個倉位存在。
        if self.limits.min_order_notional_usdt > self.limits.max_order_notional_usdt
            && self.limits.max_order_notional_usdt > 0.0
        {
            return Err(
                "risk.limits.min_order_notional_usdt must not exceed max_order_notional_usdt"
                    .into(),
            );
        }

        // G2-03 (2026-04-26): per-strategy SL/TP overrides — defense line A.
        // For every entry in per_strategy, validate the override fields don't
        // loosen beyond P1 limits (and reject NaN/Inf/non-positive values).
        // Per PA RFC §3.1: this is the primary enforcement; runtime cap (line B)
        // and calibrator dry-run (line C) are belt-and-suspenders. Failure here
        // means an IPC patch_risk_config / TOML reload is rejected — engine
        // never sees a per_strategy override that would break P1 guarantees.
        //
        // G2-03（2026-04-26）：per_strategy SL/TP 覆蓋 —— 防線 A（主要防線）。
        // 走 RFC §3.1，validate 階段拒「override > P1」，IPC/TOML 永不被接收；
        // runtime cap 為兜底（防 race），calibrator dry-run 為離線安全網。
        for (strategy_name, override_cfg) in &self.per_strategy {
            override_cfg.validate_against_limits(strategy_name, &self.limits)?;
        }

        Ok(())
    }
}

// ---------------------------------------------------------------------------
// GlobalLimits (P1) / 全局上限
// ---------------------------------------------------------------------------

/// Operator-set hard ceilings (P1). All percentages are in absolute points (5.0 = 5%).
/// 操作員設定的硬上限（P1）。所有百分比為絕對值（5.0 = 5%）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobalLimits {
    #[serde(default = "default_stop_loss_max_pct")]
    pub stop_loss_max_pct: f64,
    #[serde(default = "default_take_profit_max_pct")]
    pub take_profit_max_pct: f64,
    /// Whether take-profit is forced at limits.take_profit_max_pct (vs trailing only).
    /// 是否在 take_profit_max_pct 處強制止盈（vs 僅追蹤）。
    #[serde(default)]
    pub take_profit_enforced: bool,
    #[serde(default = "default_position_size_max_pct")]
    pub position_size_max_pct: f64,
    #[serde(default = "default_total_exposure_max_pct")]
    pub total_exposure_max_pct: f64,
    #[serde(default = "default_correlated_exposure_max_pct")]
    pub correlated_exposure_max_pct: f64,
    #[serde(default = "default_leverage_max")]
    pub leverage_max: f64,
    #[serde(default = "default_session_drawdown_max_pct")]
    pub session_drawdown_max_pct: f64,
    #[serde(default = "default_daily_loss_max_pct")]
    pub daily_loss_max_pct: f64,
    #[serde(default = "default_consec_loss_cooldown_count")]
    pub consec_loss_cooldown_count: u32,
    #[serde(default = "default_consec_loss_cooldown_min")]
    pub consec_loss_cooldown_min: u32,
    #[serde(default = "default_holding_hours_max")]
    pub holding_hours_max: f64,
    #[serde(default = "default_open_positions_max")]
    pub open_positions_max: u32,
    /// Smallest notional a single order may have (USDT). 0 = no floor.
    /// 單筆訂單最小名目（USDT）。0 = 無下限。
    #[serde(default)]
    pub min_order_notional_usdt: f64,
    /// Largest notional a single order may have (USDT). 0 = no ceiling.
    /// 單筆訂單最大名目（USDT）。0 = 無上限。
    #[serde(default)]
    pub max_order_notional_usdt: f64,
    /// Account balance below which all new entries are blocked.
    /// 賬戶餘額低於此值時阻擋所有新進場。
    #[serde(default)]
    pub min_balance_usdt: f64,
    /// BLOCKER-3 D15: Global notional cap across all exchange pipelines (USDT).
    /// 0 = no cap (default). Paper is excluded — only Demo+Live real exposure counts.
    /// BLOCKER-3 D15：跨交易所管線全局名目上限（USDT）。0 = 無上限。Paper 排除。
    #[serde(default)]
    pub global_notional_cap_usdt: f64,
    #[serde(default = "default_allowed_categories")]
    pub allowed_categories: Vec<String>,
    #[serde(default = "default_margin_mode")]
    pub margin_mode: String,
    #[serde(default = "default_position_mode")]
    pub position_mode: String,
    /// ARCH-RC1 1C-4 E-Merge-4: Guardian "Modified" verdict knobs.
    /// When a trade intent's leverage exceeds `leverage_max` but is < 2x over,
    /// Guardian rewrites the order with `qty *= modification_size_factor` and
    /// `leverage = modification_leverage_cap`. Previously these lived only in
    /// GuardianConfig (operator-invisible); they are now first-class RiskConfig
    /// fields so the operator GUI can tune them via patch_risk_config.
    /// ARCH-RC1 1C-4 E-Merge-4：Guardian「Modified」裁決參數。
    /// 槓桿超出 leverage_max 但 < 2x 時，Guardian 將 qty *= modification_size_factor
    /// 並把 leverage 改寫為 modification_leverage_cap。原先只存在 GuardianConfig 內
    /// 對 operator 不可見，現在升級為 RiskConfig 一級欄位，可經 patch_risk_config 調整。
    #[serde(default = "default_guardian_modification_size_factor")]
    pub guardian_modification_size_factor: f64,
    #[serde(default = "default_guardian_modification_leverage_cap")]
    pub guardian_modification_leverage_cap: f64,
    /// Per-trade risk cap as a fraction of equity (0.02 = 2%). Used by
    /// IntentProcessor Gate 2.6 to size positions: max_qty = balance × pct / price.
    /// Hot-reloaded via patch_risk_config; previously hard-coded as DEFAULT_P1_RISK_PCT.
    /// 單筆風險上限（佔餘額比例，0.02 = 2%）。IntentProcessor Gate 2.6 用此計算
    /// 上限：max_qty = balance × pct / price。經 patch_risk_config 熱重載；先前寫死。
    #[serde(default = "default_per_trade_risk_pct")]
    pub per_trade_risk_pct: f64,

    /// MICRO-PROFIT-FIX-1 (2026-04-17): fast_track ReduceToHalf skips positions
    /// whose current notional has fallen below this fraction of the entry
    /// notional (current_qty × latest_price < ratio × entry_notional). Default
    /// 0.25 = "halve twice then stop" — prevents the dust-grinding loop where
    /// the same position is halved 4–6 times down to ~$1 remaining. Range
    /// [0.0, 1.0]; 0.0 disables the filter (pre-fix behaviour).
    /// MICRO-PROFIT-FIX-1：fast_track ReduceToHalf 跳過名目已降至此比例以下的倉位。
    /// Default 0.25 = 「halve 兩次後停手」，避免同一倉位被反復 halve 到 dust 化。
    /// 0.0 = 關閉過濾（還原修前行為）。
    #[serde(default = "default_ft_min_notional_ratio_of_entry")]
    pub ft_min_notional_ratio_of_entry: f64,

    /// EXIT-FEATURES-WRITER-BUG-1-FIX (2026-04-26): absolute USD floor on the
    /// current dust notional `qty * latest_price` below which fast_track
    /// ReduceToHalf is skipped EVEN WHEN `entry_notional == 0.0` (legacy /
    /// restored snapshot — the `ft_min_notional_ratio_of_entry` ratio gate fails
    /// open in that branch because no baseline is available). Closes the
    /// MICRO-PROFIT-FIX-1 fail-open hole that drove the STRKUSDT 37-halve dust
    /// spiral observed 2026-04-26 (qty 0.05 → 7.3e-13 over 37 minutes). MIT
    /// audit `2026-04-26--exit_features_writer_bug_audit.md` §4 RCA-A. Range
    /// `[0.0, ∞)`; `0.0` disables the absolute floor (only the ratio gate
    /// applies). Default `1.0 USD` — well below any realistic real position
    /// notional yet large enough to dwarf dust residues whose `qty * price`
    /// is sub-cent. Hot-reloadable via `patch_risk_config`.
    /// EXIT-FEATURES-WRITER-BUG-1-FIX：fast_track ReduceToHalf 對「當前名目 USD 絕對值」
    /// 低於此門檻的倉位直接 skip，**即使 entry_notional == 0**（舊快照無基準，
    /// MICRO-PROFIT-FIX-1 ratio gate fail-open）。封住 STRKUSDT 37 次 dust spiral
    /// 漏洞。`0.0` = 關閉絕對門檻（僅 ratio gate 生效）。預設 1 USD，遠低於真實
    /// 倉位但遠高於 dust 殘留（sub-cent 級），可經 `patch_risk_config` 熱重載。
    #[serde(default = "default_ft_dust_qty_floor_usd")]
    pub ft_dust_qty_floor_usd: f64,
}

fn default_stop_loss_max_pct() -> f64 {
    5.0
}
fn default_take_profit_max_pct() -> f64 {
    20.0
}
fn default_position_size_max_pct() -> f64 {
    20.0
}
fn default_total_exposure_max_pct() -> f64 {
    100.0
}
fn default_correlated_exposure_max_pct() -> f64 {
    60.0
}
fn default_leverage_max() -> f64 {
    20.0
}
fn default_session_drawdown_max_pct() -> f64 {
    15.0
}
fn default_daily_loss_max_pct() -> f64 {
    5.0
}
fn default_consec_loss_cooldown_count() -> u32 {
    3
}
fn default_consec_loss_cooldown_min() -> u32 {
    30
}
fn default_holding_hours_max() -> f64 {
    72.0
}
fn default_open_positions_max() -> u32 {
    25
}
fn default_allowed_categories() -> Vec<String> {
    vec!["spot".into(), "linear".into(), "inverse".into()]
}
fn default_margin_mode() -> String {
    "isolated".into()
}
fn default_position_mode() -> String {
    "one_way".into()
}
fn default_guardian_modification_size_factor() -> f64 {
    0.5
}
fn default_guardian_modification_leverage_cap() -> f64 {
    2.0
}
fn default_per_trade_risk_pct() -> f64 {
    0.02
}
fn default_ft_min_notional_ratio_of_entry() -> f64 {
    // MICRO-PROFIT-FIX-1: 0.25 maps to "two halvings then stop" — a 4th halve
    // would take the position to 12.5% and be blocked. Lower values allow more
    // halvings; 0.0 disables the filter. See worklog 2026-04-17 §3.1.
    // MICRO-PROFIT-FIX-1：0.25 = 「halve 兩次後停手」（再 halve 會降到 12.5% 被擋）。
    0.25
}

fn default_ft_dust_qty_floor_usd() -> f64 {
    // EXIT-FEATURES-WRITER-BUG-1-FIX: 1.0 USD is large enough to swallow dust
    // residues (sub-cent qty * price) yet small enough to never block a real
    // halving on a normal-sized position. Tunable per environment via TOML;
    // operators wanting a more aggressive guard may bump to 5–10 USD without
    // restart (hot-reloadable). 0.0 disables the absolute floor.
    // EXIT-FEATURES-WRITER-BUG-1-FIX：1 USD — 足夠 dust 殘留（sub-cent）卻
    // 不會擋正常倉位半倉。每環境 TOML 可調，0 = 關閉。
    1.0
}

impl Default for GlobalLimits {
    fn default() -> Self {
        Self {
            stop_loss_max_pct: default_stop_loss_max_pct(),
            take_profit_max_pct: default_take_profit_max_pct(),
            take_profit_enforced: false,
            position_size_max_pct: default_position_size_max_pct(),
            total_exposure_max_pct: default_total_exposure_max_pct(),
            correlated_exposure_max_pct: default_correlated_exposure_max_pct(),
            leverage_max: default_leverage_max(),
            session_drawdown_max_pct: default_session_drawdown_max_pct(),
            daily_loss_max_pct: default_daily_loss_max_pct(),
            consec_loss_cooldown_count: default_consec_loss_cooldown_count(),
            consec_loss_cooldown_min: default_consec_loss_cooldown_min(),
            holding_hours_max: default_holding_hours_max(),
            open_positions_max: default_open_positions_max(),
            min_order_notional_usdt: 0.0,
            max_order_notional_usdt: 0.0,
            min_balance_usdt: 0.0,
            global_notional_cap_usdt: 0.0,
            allowed_categories: default_allowed_categories(),
            margin_mode: default_margin_mode(),
            position_mode: default_position_mode(),
            guardian_modification_size_factor: default_guardian_modification_size_factor(),
            guardian_modification_leverage_cap: default_guardian_modification_leverage_cap(),
            per_trade_risk_pct: default_per_trade_risk_pct(),
            ft_min_notional_ratio_of_entry: default_ft_min_notional_ratio_of_entry(),
            ft_dust_qty_floor_usd: default_ft_dust_qty_floor_usd(),
        }
    }
}

impl GlobalLimits {
    fn validate(&self) -> Result<(), String> {
        if self.stop_loss_max_pct <= 0.0 || self.stop_loss_max_pct > 100.0 {
            return Err("risk.limits.stop_loss_max_pct must be in (0, 100]".into());
        }
        if self.take_profit_max_pct <= 0.0 {
            return Err("risk.limits.take_profit_max_pct must be > 0".into());
        }
        if self.position_size_max_pct <= 0.0 || self.position_size_max_pct > 100.0 {
            return Err("risk.limits.position_size_max_pct must be in (0, 100]".into());
        }
        if self.total_exposure_max_pct <= 0.0 {
            return Err("risk.limits.total_exposure_max_pct must be > 0".into());
        }
        if self.leverage_max < 1.0 {
            return Err("risk.limits.leverage_max must be >= 1".into());
        }
        if self.open_positions_max == 0 {
            return Err("risk.limits.open_positions_max must be >= 1".into());
        }
        if self.holding_hours_max <= 0.0 {
            return Err("risk.limits.holding_hours_max must be > 0".into());
        }
        if self.min_order_notional_usdt < 0.0 || self.max_order_notional_usdt < 0.0 {
            return Err("risk.limits.*_order_notional_usdt must be >= 0".into());
        }
        if self.allowed_categories.is_empty() {
            return Err("risk.limits.allowed_categories must not be empty".into());
        }
        match self.margin_mode.as_str() {
            "isolated" | "cross" => {}
            other => return Err(format!("risk.limits.margin_mode invalid: '{}'", other)),
        }
        match self.position_mode.as_str() {
            "one_way" | "hedge" => {}
            other => return Err(format!("risk.limits.position_mode invalid: '{}'", other)),
        }
        // E-Merge-4 Guardian modification knobs / E-Merge-4 Guardian 修正參數
        if !(0.0..=1.0).contains(&self.guardian_modification_size_factor) {
            return Err("risk.limits.guardian_modification_size_factor must be in [0, 1]".into());
        }
        if self.guardian_modification_leverage_cap < 1.0 {
            return Err("risk.limits.guardian_modification_leverage_cap must be >= 1".into());
        }
        if !(0.0001..=0.20).contains(&self.per_trade_risk_pct) {
            return Err(
                "risk.limits.per_trade_risk_pct must be in [0.0001, 0.20] (0.01–20%)".into(),
            );
        }
        // MICRO-PROFIT-FIX-1: ft_min_notional_ratio_of_entry ∈ [0, 1]; 0 disables the filter.
        // MICRO-PROFIT-FIX-1：ft_min_notional_ratio_of_entry ∈ [0, 1]，0 = 關閉。
        if !(0.0..=1.0).contains(&self.ft_min_notional_ratio_of_entry) {
            return Err("risk.limits.ft_min_notional_ratio_of_entry must be in [0, 1]".into());
        }
        // EXIT-FEATURES-WRITER-BUG-1-FIX: ft_dust_qty_floor_usd ∈ [0, 100_000];
        // 0 disables the absolute floor. Reject NaN and unreasonably large
        // values that would block all halvings (effectively disabling
        // fast_track). 100_000 USD is roughly $1B account × 0.01% per trade,
        // far above any realistic guard.
        // EXIT-FEATURES-WRITER-BUG-1-FIX：ft_dust_qty_floor_usd ∈ [0, 100000]；
        // 0 = 關閉，拒絕 NaN 與過大值（會擋住所有半倉）。
        if !self.ft_dust_qty_floor_usd.is_finite()
            || !(0.0..=100_000.0).contains(&self.ft_dust_qty_floor_usd)
        {
            return Err(
                "risk.limits.ft_dust_qty_floor_usd must be finite in [0, 100000]".into(),
            );
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// CategoryOverrides (P0)
// ---------------------------------------------------------------------------

/// Per-category P0 overrides (spot / linear / inverse / option).
/// 按品類的 P0 覆蓋。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CategoryOverrides {
    #[serde(default)]
    pub spot: Option<CategoryOverride>,
    #[serde(default)]
    pub linear: Option<CategoryOverride>,
    #[serde(default)]
    pub inverse: Option<CategoryOverride>,
    #[serde(default)]
    pub option: Option<CategoryOverride>,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CategoryOverride {
    #[serde(default)]
    pub enabled: Option<bool>,
    #[serde(default)]
    pub leverage_max: Option<f64>,
    #[serde(default)]
    pub position_size_max_pct: Option<f64>,
    #[serde(default)]
    pub total_exposure_max_pct: Option<f64>,
    #[serde(default)]
    pub stop_loss_max_pct: Option<f64>,
    #[serde(default)]
    pub holding_hours_max: Option<f64>,
    #[serde(default)]
    pub allowed_symbols: Option<Vec<String>>,
    #[serde(default)]
    pub spot_margin_allowed: Option<bool>,
}

// ---------------------------------------------------------------------------
// StrategyOverride (per-strategy)
// ---------------------------------------------------------------------------
//
// G2-03 (2026-04-26) refactor: StrategyOverride struct + Default + impl
// extracted to sibling `risk_config_per_strategy.rs` to keep this file under
// CLAUDE.md §九 1200-line hard cap. `pub use` below preserves public API
// path `crate::config::risk_config::StrategyOverride` for all callers.
//
// G2-03（2026-04-26）重構：StrategyOverride 抽至 sibling 守 §九 1200 行硬上限；
// `pub use` 保留 `crate::config::risk_config::StrategyOverride` 公開 API 路徑。
#[path = "risk_config_per_strategy.rs"]
mod per_strategy;
pub use per_strategy::StrategyOverride;

pub(super) fn default_true() -> bool {
    true
}

// ---------------------------------------------------------------------------
// AgentParams (P2)
// ---------------------------------------------------------------------------

/// Agent self-tunable risk-side parameters (P2).
/// Agent 自我調整的風控側參數（P2）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentParams {
    /// Effective stop-loss %. None = dynamic ATR.
    /// 有效止損百分比。None = 動態 ATR。
    #[serde(default)]
    pub stop_loss_pct: Option<f64>,
    /// Effective take-profit %. None = dynamic ATR.
    /// 有效止盈百分比。None = 動態 ATR。
    #[serde(default)]
    pub take_profit_pct: Option<f64>,
    #[serde(default = "default_true")]
    pub trailing_enabled: bool,
    #[serde(default = "default_trailing_activation_pct")]
    pub trailing_activation_pct: f64,
    #[serde(default = "default_trailing_distance_pct")]
    pub trailing_distance_pct: f64,
    /// Position size scaling (0.1 - 1.0).
    /// 倉位規模縮放（0.1 - 1.0）。
    #[serde(default = "default_size_multiplier")]
    pub size_multiplier: f64,
    /// Per-category preference weights (sum should be > 0).
    /// 按品類偏好權重（總和應 > 0）。
    #[serde(default)]
    pub category_weights: HashMap<String, f64>,
    /// Order placement preferences.
    /// 訂單放置偏好。
    #[serde(default = "default_true")]
    pub prefer_limit: bool,
    #[serde(default = "default_true")]
    pub reduce_only_close: bool,
    #[serde(default)]
    pub post_only_limit: bool,
    /// Partial take-profit toggle. Coupled to limits.take_profit_max_pct.
    /// 分批止盈開關。與 limits.take_profit_max_pct 耦合。
    #[serde(default)]
    pub partial_tp_enabled: bool,
    /// Partial TP levels: list of (pct_profit, fraction_to_close).
    /// 分批止盈各層：(百分比利潤, 平倉比例) 列表。
    #[serde(default)]
    pub partial_tp_levels: Vec<(f64, f64)>,
}

fn default_trailing_activation_pct() -> f64 {
    1.0
}
fn default_trailing_distance_pct() -> f64 {
    0.8
}
fn default_size_multiplier() -> f64 {
    1.0
}

impl Default for AgentParams {
    fn default() -> Self {
        Self {
            stop_loss_pct: None,
            take_profit_pct: None,
            trailing_enabled: default_true(),
            trailing_activation_pct: default_trailing_activation_pct(),
            trailing_distance_pct: default_trailing_distance_pct(),
            size_multiplier: default_size_multiplier(),
            category_weights: HashMap::new(),
            prefer_limit: default_true(),
            reduce_only_close: default_true(),
            post_only_limit: false,
            partial_tp_enabled: false,
            partial_tp_levels: Vec::new(),
        }
    }
}

impl AgentParams {
    fn validate(&self) -> Result<(), String> {
        if !(0.1..=1.0).contains(&self.size_multiplier) {
            return Err("risk.agent.size_multiplier must be in [0.1, 1.0]".into());
        }
        if self.trailing_activation_pct <= 0.0 {
            return Err("risk.agent.trailing_activation_pct must be > 0".into());
        }
        if self.trailing_distance_pct <= 0.0 {
            return Err("risk.agent.trailing_distance_pct must be > 0".into());
        }
        if let Some(sl) = self.stop_loss_pct {
            if sl <= 0.0 {
                return Err("risk.agent.stop_loss_pct must be > 0 when set".into());
            }
        }
        if let Some(tp) = self.take_profit_pct {
            if tp <= 0.0 {
                return Err("risk.agent.take_profit_pct must be > 0 when set".into());
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// KellyTierConfig — Kelly fractional-tier sample-size boundaries (G7-01)
// Kelly 分層樣本量邊界 (G7-01)
// ---------------------------------------------------------------------------

/// G7-01 (2026-04-24): Operator-tunable Kelly tier boundaries.
///
/// Drives `ml::kelly_sizer::compute_kelly_qty`'s sample-size tier classification:
/// - trades `< young_threshold`: 1/8 Kelly (young, most conservative)
/// - trades in `[young_threshold, mature_threshold)`: 1/6 Kelly (mature)
/// - trades `>= mature_threshold`: 1/4 Kelly (established, never full Kelly)
///
/// Defaults `50` / `200` preserve the pre-G7-01 hardcoded constants;
/// `young_threshold < mature_threshold` and both `> 0` enforced by `validate()`.
///
/// G7-01：Operator 可調的 Kelly 分層邊界。驅動 `compute_kelly_qty` 的樣本量分級。
/// 預設 50/200 保留原硬編碼常量；`validate()` 強制 young < mature 且兩者 > 0。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KellyTierConfig {
    /// Boundary trades-count for young → mature tier (default 50).
    /// Young → mature 分層門檻（預設 50）。
    #[serde(default = "default_kelly_young_threshold")]
    pub young_threshold: u32,
    /// Boundary trades-count for mature → established tier (default 200).
    /// Mature → established 分層門檻（預設 200）。
    #[serde(default = "default_kelly_mature_threshold")]
    pub mature_threshold: u32,
}

fn default_kelly_young_threshold() -> u32 {
    50
}

fn default_kelly_mature_threshold() -> u32 {
    200
}

impl Default for KellyTierConfig {
    fn default() -> Self {
        Self {
            young_threshold: default_kelly_young_threshold(),
            mature_threshold: default_kelly_mature_threshold(),
        }
    }
}

impl KellyTierConfig {
    /// G7-01: Validate `young < mature` and both `> 0`.
    /// G7-01：驗證 young < mature 且兩者 > 0。
    pub fn validate(&self) -> Result<(), String> {
        if self.young_threshold == 0 {
            return Err("risk.kelly.young_threshold must be > 0".into());
        }
        if self.mature_threshold == 0 {
            return Err("risk.kelly.mature_threshold must be > 0".into());
        }
        if self.young_threshold >= self.mature_threshold {
            return Err(format!(
                "risk.kelly.young_threshold ({}) must be < risk.kelly.mature_threshold ({})",
                self.young_threshold, self.mature_threshold
            ));
        }
        Ok(())
    }
}



// ---------------------------------------------------------------------------
// CascadeThresholds — RiskGovernor 6-level
// ---------------------------------------------------------------------------

/// Six-level RiskGovernor cascade thresholds (Normal / Cautious / Reduced / Defensive / CircuitBreaker / ManualReview).
/// 六級 RiskGovernor cascade 閾值。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CascadeThresholds {
    #[serde(default = "default_drawdown_cautious_pct")]
    pub drawdown_cautious_pct: f64,
    #[serde(default = "default_drawdown_reduced_pct")]
    pub drawdown_reduced_pct: f64,
    #[serde(default = "default_drawdown_defensive_pct")]
    pub drawdown_defensive_pct: f64,
    #[serde(default = "default_drawdown_circuit_pct")]
    pub drawdown_circuit_pct: f64,
    #[serde(default = "default_daily_loss_cautious_pct")]
    pub daily_loss_cautious_pct: f64,
    #[serde(default = "default_daily_loss_reduced_pct")]
    pub daily_loss_reduced_pct: f64,
    #[serde(default = "default_daily_loss_circuit_pct")]
    pub daily_loss_circuit_pct: f64,
    #[serde(default = "default_consec_loss_cautious")]
    pub consec_loss_cautious: u32,
    #[serde(default = "default_consec_loss_reduced")]
    pub consec_loss_reduced: u32,
    #[serde(default = "default_consec_loss_circuit")]
    pub consec_loss_circuit: u32,
    #[serde(default = "default_pressure_cautious")]
    pub pressure_cautious: f64,
    #[serde(default = "default_pressure_reduced")]
    pub pressure_reduced: f64,
    #[serde(default = "default_pressure_defensive")]
    pub pressure_defensive: f64,
    #[serde(default = "default_pressure_circuit")]
    pub pressure_circuit: f64,
    #[serde(default = "default_min_hold_ms")]
    pub min_hold_ms: u64,
}

fn default_drawdown_cautious_pct() -> f64 {
    5.0
}
fn default_drawdown_reduced_pct() -> f64 {
    8.0
}
fn default_drawdown_defensive_pct() -> f64 {
    12.0
}
fn default_drawdown_circuit_pct() -> f64 {
    15.0
}
fn default_daily_loss_cautious_pct() -> f64 {
    2.0
}
fn default_daily_loss_reduced_pct() -> f64 {
    3.5
}
fn default_daily_loss_circuit_pct() -> f64 {
    5.0
}
fn default_consec_loss_cautious() -> u32 {
    3
}
fn default_consec_loss_reduced() -> u32 {
    5
}
fn default_consec_loss_circuit() -> u32 {
    10
}
fn default_pressure_cautious() -> f64 {
    0.3
}
fn default_pressure_reduced() -> f64 {
    0.5
}
fn default_pressure_defensive() -> f64 {
    0.7
}
fn default_pressure_circuit() -> f64 {
    0.9
}
fn default_min_hold_ms() -> u64 {
    300_000
}

impl Default for CascadeThresholds {
    fn default() -> Self {
        Self {
            drawdown_cautious_pct: default_drawdown_cautious_pct(),
            drawdown_reduced_pct: default_drawdown_reduced_pct(),
            drawdown_defensive_pct: default_drawdown_defensive_pct(),
            drawdown_circuit_pct: default_drawdown_circuit_pct(),
            daily_loss_cautious_pct: default_daily_loss_cautious_pct(),
            daily_loss_reduced_pct: default_daily_loss_reduced_pct(),
            daily_loss_circuit_pct: default_daily_loss_circuit_pct(),
            consec_loss_cautious: default_consec_loss_cautious(),
            consec_loss_reduced: default_consec_loss_reduced(),
            consec_loss_circuit: default_consec_loss_circuit(),
            pressure_cautious: default_pressure_cautious(),
            pressure_reduced: default_pressure_reduced(),
            pressure_defensive: default_pressure_defensive(),
            pressure_circuit: default_pressure_circuit(),
            min_hold_ms: default_min_hold_ms(),
        }
    }
}

impl CascadeThresholds {
    fn validate(&self) -> Result<(), String> {
        // Drawdown tiers strictly increasing / Drawdown 階層嚴格遞增
        if !(self.drawdown_cautious_pct < self.drawdown_reduced_pct
            && self.drawdown_reduced_pct < self.drawdown_defensive_pct
            && self.drawdown_defensive_pct < self.drawdown_circuit_pct)
        {
            return Err(
                "risk.cascade drawdown tiers must be strictly increasing (cautious < reduced < defensive < circuit)".into()
            );
        }
        if !(self.daily_loss_cautious_pct < self.daily_loss_reduced_pct
            && self.daily_loss_reduced_pct < self.daily_loss_circuit_pct)
        {
            return Err(
                "risk.cascade daily_loss tiers must be strictly increasing (cautious < reduced < circuit)".into()
            );
        }
        if !(self.consec_loss_cautious < self.consec_loss_reduced
            && self.consec_loss_reduced < self.consec_loss_circuit)
        {
            return Err(
                "risk.cascade consec_loss tiers must be strictly increasing (cautious < reduced < circuit)".into()
            );
        }
        if !(self.pressure_cautious < self.pressure_reduced
            && self.pressure_reduced < self.pressure_defensive
            && self.pressure_defensive < self.pressure_circuit)
        {
            return Err("risk.cascade pressure tiers must be strictly increasing".into());
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// RegimeMultipliers
// ---------------------------------------------------------------------------

/// Regime-conditional multipliers applied to stop / tp / time limits.
/// 按 regime 套用到 stop / tp / time 上的乘數。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegimeMultipliers {
    #[serde(default = "default_trending")]
    pub trending: RegimeBundle,
    #[serde(default = "default_volatile")]
    pub volatile: RegimeBundle,
    #[serde(default = "default_ranging")]
    pub ranging: RegimeBundle,
    #[serde(default = "default_squeeze")]
    pub squeeze: RegimeBundle,
    #[serde(default = "default_unknown")]
    pub unknown: RegimeBundle,
}

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct RegimeBundle {
    pub stop: f64,
    pub tp: f64,
    pub time: f64,
}

fn default_trending() -> RegimeBundle {
    RegimeBundle {
        stop: 1.0,
        tp: 1.5,
        time: 1.5,
    }
}
fn default_volatile() -> RegimeBundle {
    RegimeBundle {
        stop: 1.5,
        tp: 0.8,
        time: 0.8,
    }
}
fn default_ranging() -> RegimeBundle {
    RegimeBundle {
        stop: 0.7,
        tp: 0.7,
        time: 0.8,
    }
}
fn default_squeeze() -> RegimeBundle {
    RegimeBundle {
        stop: 0.6,
        tp: 0.5,
        time: 1.0,
    }
}
fn default_unknown() -> RegimeBundle {
    RegimeBundle {
        stop: 1.0,
        tp: 1.0,
        time: 1.0,
    }
}

impl Default for RegimeMultipliers {
    fn default() -> Self {
        Self {
            trending: default_trending(),
            volatile: default_volatile(),
            ranging: default_ranging(),
            squeeze: default_squeeze(),
            unknown: default_unknown(),
        }
    }
}

impl RegimeMultipliers {
    /// Look up bundle by regime name. Unknown names fall back to `unknown`.
    /// 按 regime 名稱查找 bundle。未知名稱回退到 `unknown`。
    pub fn get(&self, regime: &str) -> RegimeBundle {
        match regime {
            "trending" => self.trending,
            "volatile" => self.volatile,
            "ranging" => self.ranging,
            "squeeze" => self.squeeze,
            _ => self.unknown,
        }
    }

    fn validate(&self) -> Result<(), String> {
        for (name, b) in [
            ("trending", &self.trending),
            ("volatile", &self.volatile),
            ("ranging", &self.ranging),
            ("squeeze", &self.squeeze),
            ("unknown", &self.unknown),
        ] {
            if b.stop <= 0.0 || b.tp <= 0.0 || b.time <= 0.0 {
                return Err(format!("risk.regime.{} multipliers must all be > 0", name));
            }
        }
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// CostGate
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostGate {
    #[serde(default = "default_min_confidence")]
    pub min_confidence: f64,
    #[serde(default = "default_k_base")]
    pub k_base: f64,
    #[serde(default = "default_k_medium")]
    pub k_medium: f64,
    #[serde(default = "default_k_small")]
    pub k_small: f64,
    #[serde(default = "default_adx_trending")]
    pub adx_trending: f64,
}

fn default_min_confidence() -> f64 {
    0.15
}
fn default_k_base() -> f64 {
    1.5
}
fn default_k_medium() -> f64 {
    2.0
}
fn default_k_small() -> f64 {
    3.0
}
fn default_adx_trending() -> f64 {
    25.0
}

impl Default for CostGate {
    fn default() -> Self {
        Self {
            min_confidence: default_min_confidence(),
            k_base: default_k_base(),
            k_medium: default_k_medium(),
            k_small: default_k_small(),
            adx_trending: default_adx_trending(),
        }
    }
}

impl CostGate {
    fn validate(&self) -> Result<(), String> {
        if !(0.0..=1.0).contains(&self.min_confidence) {
            return Err("risk.cost_gate.min_confidence must be in [0, 1]".into());
        }
        if self.k_base <= 0.0 || self.k_medium <= 0.0 || self.k_small <= 0.0 {
            return Err("risk.cost_gate k coefficients must all be > 0".into());
        }
        Ok(())
    }
}



// ---------------------------------------------------------------------------
// Tests — extracted to risk_config_tests.rs (FIX-08 file size)
// 測試 — 提取至 risk_config_tests.rs（FIX-08 文件大小）
// ---------------------------------------------------------------------------

#[cfg(test)]
#[path = "risk_config_tests.rs"]
mod tests;

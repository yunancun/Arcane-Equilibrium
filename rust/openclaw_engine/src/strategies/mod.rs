//! Strategy modules — 5 trading strategies (R04-5).
//! 策略模組 — 5 個交易策略。
//!
//! MODULE_NOTE (EN): Defines Strategy trait + StrategyAction enum + StrategyParams.
//!   Sub-modules: ma_crossover, bb_breakout, bb_reversion, grid_trading, funding_arb.
//! MODULE_NOTE (中): 定義 Strategy trait + StrategyAction 枚舉 + StrategyParams。
//!   子模組：ma_crossover、bb_breakout、bb_reversion、grid_trading、funding_arb。

pub mod bb_breakout;
pub mod bb_reversion;
pub mod funding_arb;
pub mod grid_trading;
pub mod ma_crossover;

use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::{PipelineKind, TickContext};
use openclaw_core::execution::FillResult;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use tracing::{info, warn};

/// First-class strategy action: Open (new position, full governance) or Close (exit, lightweight path).
/// 策略一等公民動作：Open（新倉，完整治理管線）或 Close（平倉，輕量路徑）。
///
/// Close bypasses governance gates (Guardian, cost_gate, Kelly sizing, P1 cap) since closing
/// reduces risk rather than increasing it. Pipeline looks up actual is_long/qty from paper_state.
/// Close 繞過治理門禁（Guardian、cost_gate、Kelly sizing、P1 cap），因為平倉是降低風險而非增加風險。
/// 管線從 paper_state 查找實際的 is_long/qty。
#[derive(Debug, Clone)]
pub enum StrategyAction {
    /// New position — goes through full governance pipeline.
    /// 新倉 — 經過完整治理管線。
    Open(OrderIntent),
    /// Close existing position — lightweight path, bypasses governance gates.
    /// 平倉 — 輕量路徑，繞過治理門禁。
    Close {
        symbol: String,
        confidence: f64,
        reason: String,
    },
}

/// Strategy trait — implement for each trading strategy.
/// 策略 trait — 為每個交易策略實現。
/// Send required for tokio::spawn compatibility.
pub trait Strategy: Send {
    /// Strategy name for logging and attribution.
    /// 策略名稱用於日誌和歸因。
    fn name(&self) -> &str;

    /// Is this strategy currently active?
    /// 此策略當前是否活躍？
    fn is_active(&self) -> bool;

    /// RRC-1-E2: Set strategy active/paused state via IPC.
    /// RRC-1-E2：通過 IPC 設置策略活躍/暫停狀態。
    fn set_active(&mut self, active: bool);

    /// Process a tick and return strategy actions (Open or Close).
    /// 處理 tick 並返回策略動作（Open 或 Close）。
    fn on_tick(&mut self, ctx: &TickContext) -> Vec<StrategyAction>;

    /// Called when an intent from this strategy was rejected by the governance pipeline.
    /// 當此策略的意圖被治理管線拒絕時調用。
    /// Default: no-op. Strategies that track internal position should override.
    /// 默認：無操作。跟蹤內部倉位的策略應覆蓋此方法。
    fn on_rejection(&mut self, _intent: &OrderIntent, _reason: &str) {
        // Default no-op / 默認無操作
    }

    /// Called when an order from this strategy was filled.
    /// 當此策略的訂單成交時調用。
    fn on_fill(&mut self, _intent: &OrderIntent, _fill: &FillResult) {
        // Default no-op / 默認無操作
    }

    /// Called when a position was closed externally (risk-close/stop) rather than by this strategy.
    /// Strategies that track internal position state should override to stay in sync.
    /// 當倉位被外部（風控止損）而非本策略關閉時調用。跟蹤內部倉位狀態的策略應覆蓋以保持同步。
    fn on_external_close(&mut self, _symbol: &str) {
        // Default no-op / 默認無操作
    }

    /// Called after the pipeline confirms a strategy-emitted Close was executed successfully.
    /// Strategies that defer state changes until close is confirmed should override.
    /// 管線確認策略發出的 Close 已成功執行後調用。延遲狀態變更直到確認平倉的策略應覆蓋。
    fn on_close_confirmed(&mut self, _symbol: &str) {
        // Default no-op / 默認無操作
    }

    /// Called when a strategy-emitted Close was skipped (no position found in paper_state).
    /// Strategies that eagerly mutated state should override to roll back.
    /// 策略發出的 Close 被跳過（paper_state 中未找到倉位）時調用。提前變更狀態的策略應覆蓋以回滾。
    fn on_close_skipped(&mut self, _symbol: &str) {
        // Default no-op / 默認無操作
    }

    // ── Phase 3a: Runtime parameter tuning API (AGT-1) ──
    // Phase 3a：運行時參數調參 API

    /// Update strategy parameters from JSON. Returns Err if invalid.
    /// 從 JSON 更新策略參數。無效時返回 Err。
    fn update_params_json(&mut self, _json: &str) -> Result<(), String> {
        Err("update_params not implemented for this strategy".into())
    }

    /// Get current parameters as JSON string.
    /// 獲取當前參數的 JSON 字符串。
    fn get_params_json(&self) -> String {
        "{}".into()
    }

    /// Get tunable parameter ranges as JSON string.
    /// 獲取可調參數範圍的 JSON 字符串。
    fn param_ranges_json(&self) -> String {
        "[]".into()
    }

    // ── CONF-D: per-strategy confidence scaling exposed via update_strategy_params ──
    // CONF-D：通過 update_strategy_params 暴露的逐策略 confidence 縮放因子

    /// CONF-D: Read the current confidence scale (default 1.0).
    /// Strategies multiply every emitted intent.confidence by this value
    /// before pushing to the intent stream. Range [0.0, 2.0]; >1.0 amplifies,
    /// <1.0 dampens, 0.0 effectively mutes the strategy without disabling it.
    /// CONF-D：讀取當前 confidence 縮放因子（默認 1.0）。
    /// 策略在發出 intent 前將其 confidence 乘以此值。範圍 [0, 2]。
    fn conf_scale(&self) -> f64 {
        1.0
    }

    /// CONF-D: Set confidence scale. Out-of-range values are clamped to [0.0, 2.0].
    /// Default no-op for strategies that opt out (their conf_scale stays 1.0).
    /// CONF-D：設定 confidence 縮放因子，越界自動 clamp 到 [0, 2]。
    fn set_conf_scale(&mut self, _scale: f64) {
        // Default no-op / 預設無操作
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// RC-08: StrategyParams trait — interface for DB persistence and Agent tuning.
// RC-08：策略參數 trait — 數據庫持久化和 Agent 調參的接口。
// ═══════════════════════════════════════════════════════════════════════════════

/// Parameter range descriptor for Optuna/Agent tuning (Phase 3b).
/// 參數範圍描述符，供 Optuna/Agent 調參使用（Phase 3b）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ParamRange {
    /// Parameter name / 參數名稱
    pub name: String,
    /// Minimum value / 最小值
    pub min: f64,
    /// Maximum value / 最大值
    pub max: f64,
    /// Step size for grid search (None = continuous) / 網格搜索步長（None = 連續）
    pub step: Option<f64>,
    /// Can the Agent adjust this parameter at runtime?
    /// Agent 是否可以在運行時調整此參數？
    pub agent_adjustable: bool,
    /// Should this parameter be persisted to DB?
    /// 此參數是否應持久化到數據庫？
    pub db_persisted: bool,
}

// ═══════════════════════════════════════════════════════════════════════════════
// BLOCKER-8: Per-engine strategy parameter config (TOML-backed).
// BLOCKER-8：每引擎策略參數配置（TOML 支持）。
// ═══════════════════════════════════════════════════════════════════════════════

/// Per-strategy parameter sections loaded from `strategy_params_{paper,demo,live}.toml`.
/// 從 `strategy_params_{paper,demo,live}.toml` 加載的各策略參數段。
#[derive(Debug, Clone, Deserialize, Serialize, Default)]
pub struct StrategyParamsConfig {
    #[serde(default)]
    pub ma_crossover: MaCrossoverParams,
    #[serde(default)]
    pub bb_reversion: BbReversionParams,
    #[serde(default)]
    pub bb_breakout: BbBreakoutParams,
    #[serde(default)]
    pub grid_trading: GridTradingParams,
}

/// MaCrossover tunable parameters / MaCrossover 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MaCrossoverParams {
    #[serde(default = "default_true")]
    pub active: bool,
    #[serde(default = "default_ma_cooldown")]
    pub cooldown_ms: u64,
    #[serde(default = "default_adx")]
    pub adx_threshold: f64,
    #[serde(default = "default_true")]
    pub regime_filter_enabled: bool,
    #[serde(default = "default_higher_tf_alpha")]
    pub higher_tf_alpha: f64,
    #[serde(default = "default_conf_scale")]
    pub conf_scale: f64,
}

impl Default for MaCrossoverParams {
    fn default() -> Self {
        Self {
            active: true,
            cooldown_ms: 300_000,
            adx_threshold: 20.0,
            regime_filter_enabled: true,
            higher_tf_alpha: 0.003,
            conf_scale: 1.0,
        }
    }
}

/// BbReversion tunable parameters / BbReversion 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BbReversionParams {
    #[serde(default = "default_true")]
    pub active: bool,
    #[serde(default = "default_bb_cooldown")]
    pub cooldown_ms: u64,
    #[serde(default)]
    pub use_limit: bool,
    #[serde(default = "default_limit_offset")]
    pub limit_offset_bps: f64,
    #[serde(default = "default_conf_scale")]
    pub conf_scale: f64,
}

impl Default for BbReversionParams {
    fn default() -> Self {
        Self {
            active: true,
            cooldown_ms: 600_000,
            use_limit: false,
            limit_offset_bps: 10.0,
            conf_scale: 1.0,
        }
    }
}

/// BbBreakout tunable parameters / BbBreakout 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BbBreakoutParams {
    #[serde(default = "default_true")]
    pub active: bool,
    #[serde(default = "default_bb_cooldown")]
    pub cooldown_ms: u64,
    #[serde(default = "default_squeeze_bw")]
    pub squeeze_bw: f64,
    #[serde(default = "default_expansion_bw")]
    pub expansion_bw: f64,
    #[serde(default = "default_volume_threshold")]
    pub volume_threshold: f64,
    #[serde(default = "default_trailing_atr")]
    pub trailing_stop_atr_mult: f64,
    #[serde(default = "default_conf_scale")]
    pub conf_scale: f64,
}

impl Default for BbBreakoutParams {
    fn default() -> Self {
        Self {
            active: true,
            cooldown_ms: 600_000,
            squeeze_bw: 0.02,
            expansion_bw: 0.04,
            volume_threshold: 1.5,
            trailing_stop_atr_mult: 2.0,
            conf_scale: 1.0,
        }
    }
}

/// GridTrading tunable parameters / GridTrading 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GridTradingParams {
    #[serde(default = "default_true")]
    pub active: bool,
    /// Grid count per symbol. NOTE: currently stored but not yet applied at
    /// construction — GridTrading uses DEFAULT_GRID_COUNT (10) until Phase 3a.
    /// 每幣種網格數量。注意：目前已存儲但構造時尚未應用。
    #[serde(default = "default_grid_levels")]
    pub grid_levels: usize,
    #[serde(default = "default_spacing_mode")]
    pub spacing_mode: String,
    #[serde(default = "default_health_check_interval")]
    pub health_check_interval: u64,
    #[serde(default = "default_max_out_of_range")]
    pub max_out_of_range: u64,
    #[serde(default = "default_conf_scale")]
    pub conf_scale: f64,
}

impl Default for GridTradingParams {
    fn default() -> Self {
        Self {
            active: true,
            grid_levels: 10,
            spacing_mode: "linear".into(),
            health_check_interval: 200,
            max_out_of_range: 50,
            conf_scale: 1.0,
        }
    }
}

// Serde default helpers / Serde 默認值輔助函數
fn default_true() -> bool { true }
fn default_ma_cooldown() -> u64 { 300_000 }
fn default_bb_cooldown() -> u64 { 600_000 }
fn default_adx() -> f64 { 20.0 }
fn default_higher_tf_alpha() -> f64 { 0.003 }
fn default_conf_scale() -> f64 { 1.0 }
fn default_squeeze_bw() -> f64 { 0.02 }
fn default_expansion_bw() -> f64 { 0.04 }
fn default_volume_threshold() -> f64 { 1.5 }
fn default_trailing_atr() -> f64 { 2.0 }
fn default_limit_offset() -> f64 { 10.0 }
fn default_grid_levels() -> usize { 10 }
fn default_spacing_mode() -> String { "linear".into() }
fn default_health_check_interval() -> u64 { 200 }
fn default_max_out_of_range() -> u64 { 50 }

/// Resolve settings directory: `OPENCLAW_BASE_DIR/settings` or `./settings`.
/// 解析設定目錄：`OPENCLAW_BASE_DIR/settings` 或 `./settings`。
fn settings_dir() -> PathBuf {
    std::env::var("OPENCLAW_BASE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("settings")
}

/// Load per-engine strategy parameters from TOML.
/// Falls back to defaults if file is missing or unparseable (fail-open for Paper, log warning).
/// 從 TOML 加載每引擎策略參數。文件缺失或解析失敗時使用默認值（Paper fail-open，記錄警告）。
pub fn load_strategy_params(kind: PipelineKind) -> StrategyParamsConfig {
    load_strategy_params_from(kind, &settings_dir())
}

/// Testable inner: load from a given settings directory.
/// 可測試內部函數：從指定設定目錄加載。
pub fn load_strategy_params_from(kind: PipelineKind, settings: &Path) -> StrategyParamsConfig {
    let filename = format!("strategy_params_{}.toml", kind.db_mode());
    let path = settings.join(&filename);
    match std::fs::read_to_string(&path) {
        Ok(contents) => match toml::from_str::<StrategyParamsConfig>(&contents) {
            Ok(cfg) => {
                info!(
                    kind = %kind, path = %path.display(),
                    "loaded strategy params from TOML / 從 TOML 加載策略參數"
                );
                cfg
            }
            Err(e) => {
                warn!(
                    kind = %kind, path = %path.display(), error = %e,
                    "failed to parse strategy params TOML, using defaults \
                     / 策略參數 TOML 解析失敗，使用默認值"
                );
                StrategyParamsConfig::default()
            }
        },
        Err(_) => {
            info!(
                kind = %kind, path = %path.display(),
                "strategy params TOML not found, using defaults \
                 / 策略參數 TOML 未找到，使用默認值"
            );
            StrategyParamsConfig::default()
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3E-9: StrategyFactory — single registration point for all strategies.
// 3E-9：策略工廠 — 所有策略的唯一註冊點。
// ═══════════════════════════════════════════════════════════════════════════════

/// Strategy factory — single registration point. Add/remove strategies here ONLY.
/// Pipeline code calls `create_all()` or `create_for_engine()` instead of hard-coding.
/// 策略工廠 — 唯一註冊點。新增/移除策略只改這裡。
/// 管線代碼調用 `create_all()` 或 `create_for_engine()` 而非硬編碼。
pub struct StrategyFactory;

impl StrategyFactory {
    /// Create all strategies with default parameters (backward compat).
    /// 以默認參數創建所有策略（向後兼容）。
    pub fn create_all() -> Vec<Box<dyn Strategy>> {
        Self::create_with_params(&StrategyParamsConfig::default())
    }

    /// Create strategies for a specific engine, loading params from TOML.
    /// 為特定引擎創建策略，從 TOML 加載參數。
    pub fn create_for_engine(kind: PipelineKind) -> Vec<Box<dyn Strategy>> {
        let params = load_strategy_params(kind);
        Self::create_with_params(&params)
    }

    /// Create strategies with explicit params (for testing / direct config).
    /// 使用明確參數創建策略（用於測試 / 直接配置）。
    pub fn create_with_params(p: &StrategyParamsConfig) -> Vec<Box<dyn Strategy>> {
        let mut strategies: Vec<Box<dyn Strategy>> = Vec::new();

        // MaCrossover
        let mut mac = ma_crossover::MaCrossover::new();
        mac.cooldown_ms = p.ma_crossover.cooldown_ms;
        mac.adx_threshold = p.ma_crossover.adx_threshold;
        mac.regime_filter_enabled = p.ma_crossover.regime_filter_enabled;
        mac.higher_tf_alpha = p.ma_crossover.higher_tf_alpha;
        mac.set_conf_scale(p.ma_crossover.conf_scale);
        mac.set_active(p.ma_crossover.active);
        strategies.push(Box::new(mac));

        // BbReversion
        let mut bbr = bb_reversion::BbReversion::new();
        bbr.cooldown_ms = p.bb_reversion.cooldown_ms;
        bbr.use_limit = p.bb_reversion.use_limit;
        bbr.limit_offset_bps = p.bb_reversion.limit_offset_bps;
        bbr.set_conf_scale(p.bb_reversion.conf_scale);
        bbr.set_active(p.bb_reversion.active);
        strategies.push(Box::new(bbr));

        // BbBreakout
        let mut bbb = bb_breakout::BbBreakout::new();
        bbb.cooldown_ms = p.bb_breakout.cooldown_ms;
        bbb.squeeze_bw = p.bb_breakout.squeeze_bw;
        bbb.expansion_bw = p.bb_breakout.expansion_bw;
        bbb.volume_threshold = p.bb_breakout.volume_threshold;
        bbb.trailing_stop_atr_mult = p.bb_breakout.trailing_stop_atr_mult;
        bbb.set_conf_scale(p.bb_breakout.conf_scale);
        bbb.set_active(p.bb_breakout.active);
        strategies.push(Box::new(bbb));

        // GridTrading
        let spacing = match p.grid_trading.spacing_mode.as_str() {
            "geometric" => grid_trading::GridSpacingMode::Geometric,
            _ => grid_trading::GridSpacingMode::Linear,
        };
        let mut gt = grid_trading::GridTrading::new_adaptive_with_mode(spacing);
        gt.health_check_interval = p.grid_trading.health_check_interval as usize;
        gt.max_out_of_range = p.grid_trading.max_out_of_range as usize;
        gt.set_conf_scale(p.grid_trading.conf_scale);
        gt.set_active(p.grid_trading.active);
        strategies.push(Box::new(gt));

        strategies
    }
}

/// Strategy parameters trait — interface for DB persistence and Agent tuning.
/// 策略參數 trait — 數據庫持久化和 Agent 調參的接口。
/// Phase 3a will implement this for each strategy. For now, just the trait definition.
/// Phase 3a 將為每個策略實現此 trait。目前只有 trait 定義。
// Phase 0a+3a: fn from_db(conn: &PgPool) -> Self will be added when sqlx is wired.
// Phase 0a+3a：fn from_db(conn: &PgPool) -> Self 將在 sqlx 接入後添加。
pub trait StrategyParams: Serialize + for<'de> Deserialize<'de> + Send {
    /// Describe tunable parameter ranges for Optuna/Agent (Phase 3b).
    /// 描述可調參數範圍，供 Optuna/Agent 使用。
    fn param_ranges() -> Vec<ParamRange>;

    /// Validate parameter values are within acceptable bounds.
    /// 驗證參數值在可接受範圍內。
    fn validate(&self) -> Result<(), String>;
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Minimal Strategy impl that exercises only the trait defaults.
    /// 最小 Strategy 實現，僅用於驗證 trait 預設實現。
    struct StubStrategy {
        active: bool,
    }

    impl Strategy for StubStrategy {
        fn name(&self) -> &str {
            "stub"
        }
        fn is_active(&self) -> bool {
            self.active
        }
        fn set_active(&mut self, active: bool) {
            self.active = active;
        }
        fn on_tick(&mut self, _ctx: &TickContext) -> Vec<StrategyAction> {
            Vec::new()
        }
    }

    #[test]
    fn test_strategy_default_param_methods() {
        let mut s = StubStrategy { active: true };
        // update_params_json defaults to Err
        let err = s.update_params_json("{}").unwrap_err();
        assert!(err.contains("not implemented"));
        // get_params_json defaults to empty object
        assert_eq!(s.get_params_json(), "{}");
        // param_ranges_json defaults to empty array
        assert_eq!(s.param_ranges_json(), "[]");
    }

    #[test]
    fn test_strategy_set_active_toggle() {
        let mut s = StubStrategy { active: false };
        assert!(!s.is_active());
        s.set_active(true);
        assert!(s.is_active());
        s.set_active(false);
        assert!(!s.is_active());
    }

    #[test]
    fn test_strategy_default_on_rejection_and_on_fill_noop() {
        // Default impls should not panic on dummy inputs.
        // 預設實現對 dummy 輸入不應 panic。
        let mut s = StubStrategy { active: true };
        let intent = OrderIntent {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            confidence: 0.5,
            strategy: "stub".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        s.on_rejection(&intent, "test reason");
        // No assertion — only checking no panic / 僅檢查不 panic
    }

    #[test]
    fn test_param_range_serde_roundtrip() {
        let pr = ParamRange {
            name: "rsi_period".into(),
            min: 5.0,
            max: 50.0,
            step: Some(1.0),
            agent_adjustable: true,
            db_persisted: true,
        };
        let json = serde_json::to_string(&pr).expect("serialize");
        let de: ParamRange = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(de.name, "rsi_period");
        assert!((de.min - 5.0).abs() < 1e-12);
        assert!((de.max - 50.0).abs() < 1e-12);
        assert_eq!(de.step, Some(1.0));
        assert!(de.agent_adjustable);
        assert!(de.db_persisted);
    }

    // ── 3E-9: StrategyFactory tests ──

    #[test]
    fn test_strategy_factory_creates_four_strategies() {
        let strategies = StrategyFactory::create_all();
        assert_eq!(strategies.len(), 4, "factory should produce exactly 4 strategies");
        let names: Vec<&str> = strategies.iter().map(|s| s.name()).collect();
        assert!(names.contains(&"ma_crossover"), "missing ma_crossover");
        assert!(names.contains(&"bb_reversion"), "missing bb_reversion");
        assert!(names.contains(&"bb_breakout"), "missing bb_breakout");
        assert!(names.contains(&"grid_trading"), "missing grid_trading");
    }

    #[test]
    fn test_strategy_factory_all_active_by_default() {
        let strategies = StrategyFactory::create_all();
        for s in &strategies {
            assert!(s.is_active(), "{} should be active by default", s.name());
        }
    }

    #[test]
    fn test_param_range_continuous_step_none() {
        let pr = ParamRange {
            name: "weight".into(),
            min: 0.0,
            max: 1.0,
            step: None,
            agent_adjustable: false,
            db_persisted: false,
        };
        let json = serde_json::to_string(&pr).expect("serialize");
        assert!(json.contains("\"step\":null"));
    }

    // ── BLOCKER-8: StrategyParamsConfig + load_strategy_params tests ──

    #[test]
    fn test_strategy_params_config_default_matches_hardcoded() {
        // Default config must match what new() constructors produce.
        // 默認配置必須與 new() 構造器產出一致。
        let cfg = StrategyParamsConfig::default();
        assert_eq!(cfg.ma_crossover.cooldown_ms, 300_000);
        assert!((cfg.ma_crossover.adx_threshold - 20.0).abs() < 1e-10);
        assert!(cfg.ma_crossover.regime_filter_enabled);
        assert!((cfg.ma_crossover.higher_tf_alpha - 0.003).abs() < 1e-10);
        assert_eq!(cfg.bb_reversion.cooldown_ms, 600_000);
        assert!(!cfg.bb_reversion.use_limit);
        assert_eq!(cfg.bb_breakout.cooldown_ms, 600_000);
        assert!((cfg.bb_breakout.squeeze_bw - 0.02).abs() < 1e-10);
        assert!((cfg.bb_breakout.expansion_bw - 0.04).abs() < 1e-10);
        assert!(cfg.grid_trading.active);
        assert_eq!(cfg.grid_trading.grid_levels, 10);
    }

    #[test]
    fn test_strategy_params_config_toml_roundtrip() {
        // Serialize to TOML and back — ensures no field mismatches.
        // 序列化到 TOML 再反序列化 — 確保無欄位不匹配。
        let cfg = StrategyParamsConfig::default();
        let toml_str = toml::to_string(&cfg).expect("serialize to TOML");
        let de: StrategyParamsConfig = toml::from_str(&toml_str).expect("deserialize from TOML");
        assert_eq!(de.ma_crossover.cooldown_ms, cfg.ma_crossover.cooldown_ms);
        assert!((de.bb_breakout.expansion_bw - cfg.bb_breakout.expansion_bw).abs() < 1e-10);
    }

    #[test]
    fn test_load_strategy_params_from_file() {
        // Write a TOML with custom values, load it, verify non-default values applied.
        // 寫入自定義 TOML，加載並驗證非默認值已套用。
        let td = tempfile::tempdir().unwrap();
        let toml_content = r#"
[ma_crossover]
active = false
cooldown_ms = 120000
adx_threshold = 30.0
regime_filter_enabled = false
higher_tf_alpha = 0.005
conf_scale = 0.8

[bb_reversion]
cooldown_ms = 900000
use_limit = true
limit_offset_bps = 15.0

[bb_breakout]
squeeze_bw = 0.03
expansion_bw = 0.08

[grid_trading]
active = true
grid_levels = 20
"#;
        std::fs::write(td.path().join("strategy_params_paper.toml"), toml_content).unwrap();
        let cfg = load_strategy_params_from(PipelineKind::Paper, td.path());
        assert!(!cfg.ma_crossover.active);
        assert_eq!(cfg.ma_crossover.cooldown_ms, 120_000);
        assert!((cfg.ma_crossover.adx_threshold - 30.0).abs() < 1e-10);
        assert!(!cfg.ma_crossover.regime_filter_enabled);
        assert!((cfg.ma_crossover.higher_tf_alpha - 0.005).abs() < 1e-10);
        assert!((cfg.ma_crossover.conf_scale - 0.8).abs() < 1e-10);
        assert_eq!(cfg.bb_reversion.cooldown_ms, 900_000);
        assert!(cfg.bb_reversion.use_limit);
        assert!((cfg.bb_reversion.limit_offset_bps - 15.0).abs() < 1e-10);
        assert!((cfg.bb_breakout.squeeze_bw - 0.03).abs() < 1e-10);
        assert_eq!(cfg.grid_trading.grid_levels, 20);
    }

    #[test]
    fn test_load_strategy_params_missing_file_returns_defaults() {
        // Missing file should fall back to defaults, not panic.
        // 文件缺失應回退到默認值，不應 panic。
        let td = tempfile::tempdir().unwrap();
        let cfg = load_strategy_params_from(PipelineKind::Demo, td.path());
        assert!(cfg.ma_crossover.active);
        assert_eq!(cfg.ma_crossover.cooldown_ms, 300_000);
    }

    #[test]
    fn test_load_strategy_params_invalid_toml_returns_defaults() {
        // Invalid TOML should fall back to defaults.
        // 無效 TOML 應回退到默認值。
        let td = tempfile::tempdir().unwrap();
        std::fs::write(td.path().join("strategy_params_live.toml"), "{{invalid}}").unwrap();
        let cfg = load_strategy_params_from(PipelineKind::Live, td.path());
        assert!(cfg.ma_crossover.active);
    }

    #[test]
    fn test_create_with_params_applies_active_flag() {
        // Strategies created with active=false should be inactive.
        // 使用 active=false 創建的策略應為非活躍。
        let mut p = StrategyParamsConfig::default();
        p.ma_crossover.active = false;
        p.bb_breakout.active = false;
        let strategies = StrategyFactory::create_with_params(&p);
        assert_eq!(strategies.len(), 4);
        for s in &strategies {
            match s.name() {
                "ma_crossover" | "bb_breakout" => assert!(!s.is_active(), "{} should be inactive", s.name()),
                _ => assert!(s.is_active(), "{} should be active", s.name()),
            }
        }
    }

    #[test]
    fn test_create_with_params_applies_conf_scale() {
        // Verify conf_scale is applied from params.
        // 驗證 conf_scale 從參數套用。
        let mut p = StrategyParamsConfig::default();
        p.ma_crossover.conf_scale = 0.5;
        let strategies = StrategyFactory::create_with_params(&p);
        let mac = strategies.iter().find(|s| s.name() == "ma_crossover").unwrap();
        assert!((mac.conf_scale() - 0.5).abs() < 1e-10);
    }
}

//! Strategy modules — 5 trading strategies + shared helpers (R04-5, G-SR-1).
//! 策略模組 — 5 個交易策略 + 共享輔助模組。
//!
//! MODULE_NOTE (EN): Defines Strategy trait + StrategyAction enum + StrategyParams.
//!   Sub-modules: ma_crossover, bb_breakout, bb_reversion, grid_trading, funding_arb,
//!   confluence (shared scoring/persistence), grid_helpers (extracted grid math).
//! MODULE_NOTE (中): 定義 Strategy trait + StrategyAction 枚舉 + StrategyParams。
//!   子模組：ma_crossover、bb_breakout、bb_reversion、grid_trading、funding_arb、
//!   confluence（共享評分/持續性）、grid_helpers（提取的網格數學）。

pub mod bb_breakout;
pub mod bb_reversion;
pub mod common;
pub mod confluence;
pub mod funding_arb;
pub mod grid_helpers;
pub mod grid_trading;
pub mod ma_crossover;
pub mod maker_rejection;

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
    fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction>;

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
    #[serde(default)]
    pub funding_arb: FundingArbParams,
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
    /// QC-H1: Entry confidence base / 入場信心基礎值
    #[serde(default = "default_entry_conf_base_ma")]
    pub entry_conf_base: f64,
    /// QC-H1: Entry regime bonus ± / 入場市場狀態加分
    #[serde(default = "default_entry_regime_bonus")]
    pub entry_regime_bonus: f64,
    /// QC-H1: Exit confidence base / 出場信心基礎值
    #[serde(default = "default_exit_conf_base_ma")]
    pub exit_conf_base: f64,
    // ── G-SR-1 A0-c: Confluence TOML fields ──
    #[serde(default = "default_min_persistence_ms")]
    pub min_persistence_ms: u64,
    #[serde(default = "default_min_notional_usd")]
    pub min_notional_usd: f64,
    #[serde(default = "default_weight_adx_trend")]
    pub weight_adx: f64,
    #[serde(default = "default_weight_regime_trend")]
    pub weight_regime: f64,
    #[serde(default = "default_weight_volume_trend")]
    pub weight_volume: f64,
    #[serde(default = "default_weight_momentum_trend")]
    pub weight_momentum: f64,
    #[serde(default = "default_adx_floor")]
    pub adx_floor: f64,
    #[serde(default = "default_threshold_no_trade")]
    pub confluence_threshold_no_trade: f64,
    #[serde(default = "default_threshold_light")]
    pub confluence_threshold_light: f64,
    #[serde(default = "default_threshold_full")]
    pub confluence_threshold_full: f64,
}

fn default_entry_conf_base_ma() -> f64 {
    0.45
}
fn default_entry_regime_bonus() -> f64 {
    0.15
}
fn default_exit_conf_base_ma() -> f64 {
    0.5
}
// G-SR-1 confluence defaults (shared) / 匯流默認值
fn default_min_persistence_ms() -> u64 {
    120_000
}
fn default_min_persistence_ms_breakout() -> u64 {
    60_000
}
fn default_min_notional_usd() -> f64 {
    10.0
}
fn default_weight_adx_trend() -> f64 {
    25.0
}
fn default_weight_regime_trend() -> f64 {
    20.0
}
fn default_weight_volume_trend() -> f64 {
    12.0
}
fn default_weight_momentum_trend() -> f64 {
    8.0
}
fn default_weight_adx_reversion() -> f64 {
    15.0
}
fn default_weight_regime_reversion() -> f64 {
    30.0
}
fn default_weight_volume_reversion() -> f64 {
    10.0
}
fn default_weight_momentum_reversion() -> f64 {
    10.0
}
fn default_adx_floor() -> f64 {
    8.0
}
fn default_threshold_no_trade() -> f64 {
    45.0
} // EDGE-P1-3: 35→45
fn default_threshold_light() -> f64 {
    52.0
} // EDGE-P1-3: 45→52
fn default_threshold_full() -> f64 {
    58.0
} // EDGE-P1-3: 55→58

impl MaCrossoverParams {
    /// Build ConfluenceConfig from TOML params (trend profile).
    /// 從 TOML 參數構建 ConfluenceConfig（趨勢配置）。
    pub fn build_confluence_config(&self) -> confluence::ConfluenceConfig {
        confluence::ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: false,
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: true,
        }
    }
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
            entry_conf_base: 0.45,
            entry_regime_bonus: 0.15,
            exit_conf_base: 0.5,
            min_persistence_ms: 120_000,
            min_notional_usd: 10.0,
            weight_adx: 25.0,
            weight_regime: 20.0,
            weight_volume: 12.0,
            weight_momentum: 8.0,
            adx_floor: 8.0,
            confluence_threshold_no_trade: 45.0,
            confluence_threshold_light: 52.0,
            confluence_threshold_full: 58.0,
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
    /// FIX-24: RSI oversold threshold (default 30) / RSI 超賣閾值
    #[serde(default = "default_rsi_oversold")]
    pub rsi_oversold: f64,
    /// FIX-24: RSI overbought threshold (default 70) / RSI 超買閾值
    #[serde(default = "default_rsi_overbought")]
    pub rsi_overbought: f64,
    /// QC-H3: Entry confidence base (default 0.6) / 入場信心基礎值
    #[serde(default = "default_entry_conf_base_bbr")]
    pub entry_conf_base: f64,
    /// QC-H3: Exit confidence base (default 0.55) / 出場信心基礎值
    #[serde(default = "default_exit_conf_base_bbr")]
    pub exit_conf_base: f64,
    /// QC-H3: Exit %B lower bound (default 0.2) / 出場 %B 下界
    #[serde(default = "default_exit_pctb_lower")]
    pub exit_pctb_lower: f64,
    /// QC-H3: Exit %B upper bound (default 0.8) / 出場 %B 上界
    #[serde(default = "default_exit_pctb_upper")]
    pub exit_pctb_upper: f64,
    /// QC-#7: Hurst regime boost for mean-reverting regime (default 0.1).
    /// QC-#7：均���回歸市場狀態信心加成。
    #[serde(default = "default_hurst_regime_boost")]
    pub hurst_regime_boost: f64,
    // ── G-SR-1 A0-c: Confluence TOML fields (reversion profile) ──
    #[serde(default = "default_min_persistence_ms")]
    pub min_persistence_ms: u64,
    #[serde(default = "default_min_notional_usd")]
    pub min_notional_usd: f64,
    #[serde(default = "default_weight_adx_reversion")]
    pub weight_adx: f64,
    #[serde(default = "default_weight_regime_reversion")]
    pub weight_regime: f64,
    #[serde(default = "default_weight_volume_reversion")]
    pub weight_volume: f64,
    #[serde(default = "default_weight_momentum_reversion")]
    pub weight_momentum: f64,
    #[serde(default = "default_adx_floor")]
    pub adx_floor: f64,
    #[serde(default = "default_true")]
    pub adx_inverted: bool,
    #[serde(default = "default_threshold_no_trade")]
    pub confluence_threshold_no_trade: f64,
    #[serde(default = "default_threshold_light")]
    pub confluence_threshold_light: f64,
    #[serde(default = "default_threshold_full")]
    pub confluence_threshold_full: f64,
}

fn default_entry_conf_base_bbr() -> f64 {
    0.6
}
fn default_exit_conf_base_bbr() -> f64 {
    0.55
}
fn default_exit_pctb_lower() -> f64 {
    0.2
}
fn default_exit_pctb_upper() -> f64 {
    0.8
}
fn default_hurst_regime_boost() -> f64 {
    0.1
}

impl BbReversionParams {
    pub fn build_confluence_config(&self) -> confluence::ConfluenceConfig {
        confluence::ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: self.adx_inverted,
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: true,
        }
    }
}

impl Default for BbReversionParams {
    fn default() -> Self {
        Self {
            active: true,
            cooldown_ms: 600_000,
            use_limit: false,
            limit_offset_bps: 10.0,
            conf_scale: 1.0,
            rsi_oversold: 30.0,
            rsi_overbought: 70.0,
            entry_conf_base: 0.6,
            exit_conf_base: 0.55,
            exit_pctb_lower: 0.2,
            exit_pctb_upper: 0.8,
            hurst_regime_boost: 0.1,
            min_persistence_ms: 120_000,
            min_notional_usd: 10.0,
            weight_adx: 15.0,
            weight_regime: 30.0,
            weight_volume: 10.0,
            weight_momentum: 10.0,
            adx_floor: 8.0,
            adx_inverted: true,
            confluence_threshold_no_trade: 45.0,
            confluence_threshold_light: 52.0,
            confluence_threshold_full: 58.0,
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
    /// FIX-26: Squeeze state expiry (ms). Default 30 min / 壓縮狀態有效期
    #[serde(default = "default_squeeze_expiry")]
    pub squeeze_expiry_ms: u64,
    /// QC-H4: Entry confidence base (default 0.7) / 入場信心基礎值
    #[serde(default = "default_entry_conf_base_bbb")]
    pub entry_conf_base: f64,
    /// QC-H4: Exit confidence base (default 0.5). Exit reasons add offsets.
    /// QC-H4：出場信心基礎值。各出場原因加減偏移。
    #[serde(default = "default_exit_conf_base_bbb")]
    pub exit_conf_base: f64,
    // ── E5-P2-4: Hurst boost + per-reason exit confidence offsets (config-driven) ──
    // ── E5-P2-4：Hurst 加成 + 各出場原因的信心偏移（改由 config 控制） ──
    /// Hurst trending regime entry confidence boost (default 0.1).
    /// Hurst 趨勢狀態入場信心加成（默認 0.1）。
    #[serde(default = "default_bbb_hurst_regime_boost")]
    pub hurst_regime_boost: f64,
    /// Exit confidence bonus when trailing stop triggers (default 0.2).
    /// 追蹤止損觸發時的出場信心加成（默認 0.2）。
    #[serde(default = "default_bbb_exit_bonus_trailing_stop")]
    pub exit_bonus_trailing_stop: f64,
    /// Exit confidence bonus when Hurst regime shifts (default 0.1).
    /// Hurst regime 轉向時的出場信心加成（默認 0.1）。
    #[serde(default = "default_bbb_exit_bonus_regime_shift")]
    pub exit_bonus_regime_shift: f64,
    /// Exit confidence bonus when %B reverts to middle band (default 0.05).
    /// %B 回到中軌時的出場信心加成（默認 0.05）。
    #[serde(default = "default_bbb_exit_bonus_pctb_revert")]
    pub exit_bonus_pctb_revert: f64,
    /// Exit confidence penalty (magnitude) when BW re-squeezes (default 0.05).
    /// 帶寬再壓縮時的出場信心扣減幅度（默認 0.05）。
    #[serde(default = "default_bbb_exit_penalty_bw_squeeze")]
    pub exit_penalty_bw_squeeze: f64,
    // ── G-SR-1 A0-c: Confluence TOML fields (breakout profile) ──
    #[serde(default = "default_min_persistence_ms_breakout")]
    pub min_persistence_ms: u64,
    #[serde(default = "default_min_notional_usd")]
    pub min_notional_usd: f64,
    #[serde(default = "default_weight_adx_trend")]
    pub weight_adx: f64,
    #[serde(default = "default_weight_regime_trend")]
    pub weight_regime: f64,
    #[serde(default = "default_weight_volume_trend")]
    pub weight_volume: f64,
    #[serde(default = "default_weight_momentum_trend")]
    pub weight_momentum: f64,
    #[serde(default = "default_adx_floor")]
    pub adx_floor: f64,
    /// Breakout uses confluence as qty modifier, not gate (default false).
    /// Breakout 使用 confluence 作為倉位修正器而非門檻（默認 false）。
    #[serde(default)]
    pub confluence_as_gate: bool,
    #[serde(default = "default_threshold_no_trade")]
    pub confluence_threshold_no_trade: f64,
    #[serde(default = "default_threshold_light")]
    pub confluence_threshold_light: f64,
    #[serde(default = "default_threshold_full")]
    pub confluence_threshold_full: f64,
}

fn default_entry_conf_base_bbb() -> f64 {
    0.7
}
fn default_exit_conf_base_bbb() -> f64 {
    0.5
}

// E5-P2-4: BB Breakout config-driven confidence offsets (extracted from code magic numbers).
// E5-P2-4：BB Breakout config 驅動的信心偏移（從 code 裡的魔術數字提升為 config）。
fn default_bbb_hurst_regime_boost() -> f64 {
    0.1
}
fn default_bbb_exit_bonus_trailing_stop() -> f64 {
    0.2
}
fn default_bbb_exit_bonus_regime_shift() -> f64 {
    0.1
}
fn default_bbb_exit_bonus_pctb_revert() -> f64 {
    0.05
}
fn default_bbb_exit_penalty_bw_squeeze() -> f64 {
    0.05
}

impl BbBreakoutParams {
    /// Build ConfluenceConfig from TOML params (breakout profile: qty modifier, not gate).
    /// 從 TOML 參數構建 ConfluenceConfig（突破配置：倉位修正器，非門檻）。
    pub fn build_confluence_config(&self) -> confluence::ConfluenceConfig {
        confluence::ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: false,
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: self.confluence_as_gate,
        }
    }
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
            squeeze_expiry_ms: 1_800_000,
            entry_conf_base: 0.7,
            exit_conf_base: 0.5,
            // E5-P2-4: defaults match pre-extraction hard-coded values.
            // E5-P2-4：默認值與原先硬編碼數值一致。
            hurst_regime_boost: 0.1,
            exit_bonus_trailing_stop: 0.2,
            exit_bonus_regime_shift: 0.1,
            exit_bonus_pctb_revert: 0.05,
            exit_penalty_bw_squeeze: 0.05,
            min_persistence_ms: 60_000,
            min_notional_usd: 10.0,
            weight_adx: 25.0,
            weight_regime: 20.0,
            weight_volume: 12.0,
            weight_momentum: 8.0,
            adx_floor: 8.0,
            confluence_as_gate: false,
            confluence_threshold_no_trade: 45.0,
            confluence_threshold_light: 52.0,
            confluence_threshold_full: 58.0,
        }
    }
}

/// GridTrading tunable parameters / GridTrading 可調參數
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GridTradingParams {
    #[serde(default = "default_true")]
    pub active: bool,
    /// E5-P2-4: Per-symbol cooldown between grid triggers (ms). Default 60_000 (= 60s).
    /// Previously unreachable from TOML — runtime value locked to the
    /// `new_adaptive_with_mode` constructor literal. Now config-driven and
    /// hot-reloadable via the factory.
    /// E5-P2-4：每 symbol 網格觸發冷卻（ms，默認 60_000 = 60 秒）。
    /// 原本無法由 TOML 觸及（運行時鎖死在 `new_adaptive_with_mode` constructor literal），
    /// 現改由 config 控制並透過工廠支援熱重載。
    #[serde(default = "default_grid_cooldown_ms")]
    pub cooldown_ms: u64,
    /// Grid count per symbol. Wired to GridTrading.grid_count via factory (RG-3 fix).
    /// 每幣種網格數量。通過工廠函數接線到 GridTrading.grid_count（RG-3 修復）。
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
    /// QC-H7: Adaptive range ±% (default 0.10 = ±10%) / 自適應範圍
    #[serde(default = "default_adaptive_range_pct")]
    pub adaptive_range_pct: f64,
    /// QC-H8: Reject backoff ms (default 30000) / 拒絕退避時長
    #[serde(default = "default_reject_backoff_ms")]
    pub reject_backoff_ms: u64,
    /// QC-H9: OU model recalc interval in ticks (default 50) / OU 重算間隔
    #[serde(default = "default_ou_update_interval")]
    pub ou_update_interval: usize,
    // ── G-SR-1 A3: Trend-adaptive cooldown ──
    /// ADX low threshold for cooldown scaling (default 20). / ADX 冷卻縮放下閾值。
    #[serde(default = "default_adx_low_threshold")]
    pub adx_low_threshold: f64,
    /// ADX high threshold for cooldown scaling (default 50). / ADX 冷卻縮放上閾值。
    #[serde(default = "default_adx_high_threshold")]
    pub adx_high_threshold: f64,
    /// Max cooldown boost factor (default 5.0, range 1x–6x). / 最大冷卻倍率加成。
    #[serde(default = "default_max_cooldown_boost")]
    pub max_cooldown_boost: f64,
    /// EDGE-P2-3 Phase 1a: emit PostOnly Limit entries (maker fee) instead of Market.
    /// Default `false` (conservative). Per-env TOML enables.
    /// EDGE-P2-3 Phase 1a：入場改發 PostOnly Limit（maker 費率）；默認 false，由各環境 TOML 啟用。
    #[serde(default = "default_use_maker_entry")]
    pub use_maker_entry: bool,
    /// EDGE-P2-3 Phase 1a: PostOnly limit placement offset from last_price in bps.
    /// EDGE-P2-3 Phase 1a：PostOnly 限價相對 last_price 的 bps 偏移。
    #[serde(default = "default_maker_price_offset_bps")]
    pub maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 1B-3: timeout (ms) after which an unfilled PostOnly
    /// Limit entry should be swept (cancel-by-link-id + rebuild). Default
    /// 45_000 ms (45s). Clamped at runtime to [15_000, 300_000].
    /// EDGE-P2-3 Phase 1B-3：未成交 PostOnly Limit 入場的清理逾時（毫秒）。
    /// 默認 45_000 ms；運行時 clamp 到 [15_000, 300_000]。
    #[serde(default = "default_maker_limit_timeout_ms")]
    pub maker_limit_timeout_ms: u64,
}

fn default_adaptive_range_pct() -> f64 {
    0.10
}
fn default_reject_backoff_ms() -> u64 {
    30_000
}
fn default_ou_update_interval() -> usize {
    50
}
fn default_adx_low_threshold() -> f64 {
    20.0
}
fn default_adx_high_threshold() -> f64 {
    50.0
}
fn default_max_cooldown_boost() -> f64 {
    5.0
}
fn default_use_maker_entry() -> bool {
    false
}
fn default_maker_price_offset_bps() -> f64 {
    1.0
}
fn default_maker_limit_timeout_ms() -> u64 {
    45_000
}

impl Default for GridTradingParams {
    fn default() -> Self {
        Self {
            active: true,
            // E5-P2-4: matches new_adaptive_with_mode constructor literal.
            // E5-P2-4：與 new_adaptive_with_mode constructor literal 一致。
            cooldown_ms: 60_000,
            grid_levels: 10,
            spacing_mode: "linear".into(),
            health_check_interval: 200,
            max_out_of_range: 50,
            conf_scale: 1.0,
            adaptive_range_pct: 0.10,
            reject_backoff_ms: 30_000,
            ou_update_interval: 50,
            adx_low_threshold: 20.0,
            adx_high_threshold: 50.0,
            max_cooldown_boost: 5.0,
            use_maker_entry: false,
            maker_price_offset_bps: 1.0,
            maker_limit_timeout_ms: 45_000,
        }
    }
}

/// FundingArb tunable parameters / FundingArb 可調參數
/// OC-5: Funding rate capture via TickContext.funding_rate + index_price.
/// OC-5：通過 TickContext.funding_rate + index_price 進行資金費率捕獲。
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct FundingArbParams {
    /// Default false: set active=true in TOML when ready to trade.
    /// 預設 false：在 TOML 中設定 active=true 以啟用交易。
    #[serde(default)]
    pub active: bool,
    #[serde(default = "default_funding_cooldown")]
    pub cooldown_ms: u64,
    /// QC-H10: Total round-trip cost in BPS (perp+spot+slippage). Default 34.
    /// QC-H10：往返總成本（基點，永續+現貨+滑點）。默認 34。
    #[serde(default = "default_fa_total_cost_bps")]
    pub total_cost_bps: f64,
    /// QC-H10: Expected funding periods for cost amortization. Default 3.
    /// QC-H10：成本攤銷用的預期資金費率週期。默認 3。
    #[serde(default = "default_fa_expected_periods")]
    pub expected_periods: f64,
    /// QC-H10: Minimum |funding_rate| to enter (default 5 bps = 0.0005).
    /// QC-H10：入場最低 |資金費率|（默認 5 bps = 0.0005）。
    #[serde(default = "default_fa_funding_threshold")]
    pub funding_threshold: f64,
    /// QC-H10: Max basis risk % to hold (default 0.5%).
    /// QC-H10：最大基差風險百分比（默認 0.5%）。
    #[serde(default = "default_fa_max_basis_pct")]
    pub max_basis_pct: f64,
    /// QC-H10: Max hold time in ms (default 72h).
    /// QC-H10：最大持有時間（毫秒，默認 72 小時）。
    #[serde(default = "default_fa_max_hold_ms")]
    pub max_hold_ms: u64,
    /// Entry basis = max_basis_pct * entry_basis_ratio; hysteresis buffer (default 0.8).
    /// 入場基差 = max_basis_pct * entry_basis_ratio；遲滯緩衝（默認 0.8）。
    #[serde(default = "default_fa_entry_basis_ratio")]
    pub entry_basis_ratio: f64,
}

fn default_fa_total_cost_bps() -> f64 {
    34.0
}
fn default_fa_expected_periods() -> f64 {
    3.0
}
fn default_fa_funding_threshold() -> f64 {
    0.0005
}
fn default_fa_max_basis_pct() -> f64 {
    0.5
}
fn default_fa_max_hold_ms() -> u64 {
    72 * 3_600_000
}
fn default_fa_entry_basis_ratio() -> f64 {
    0.8
}

impl Default for FundingArbParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: 3_600_000,
            total_cost_bps: 34.0,
            expected_periods: 3.0,
            funding_threshold: 0.0005,
            max_basis_pct: 0.5,
            max_hold_ms: 72 * 3_600_000,
            entry_basis_ratio: 0.8,
        }
    }
}

// Serde default helpers / Serde 默認值輔助函數
fn default_true() -> bool {
    true
}
fn default_ma_cooldown() -> u64 {
    300_000
}
fn default_bb_cooldown() -> u64 {
    600_000
}
fn default_adx() -> f64 {
    20.0
}
fn default_higher_tf_alpha() -> f64 {
    0.003
}
fn default_conf_scale() -> f64 {
    1.0
}
fn default_squeeze_bw() -> f64 {
    0.02
}
fn default_expansion_bw() -> f64 {
    0.04
}
fn default_volume_threshold() -> f64 {
    1.5
}
fn default_trailing_atr() -> f64 {
    2.0
}
fn default_squeeze_expiry() -> u64 {
    1_800_000
}
fn default_limit_offset() -> f64 {
    10.0
}
fn default_rsi_oversold() -> f64 {
    30.0
}
fn default_rsi_overbought() -> f64 {
    70.0
}
fn default_funding_cooldown() -> u64 {
    3_600_000
}
fn default_grid_levels() -> usize {
    10
}
fn default_spacing_mode() -> String {
    "linear".into()
}
fn default_health_check_interval() -> u64 {
    200
}
fn default_max_out_of_range() -> u64 {
    50
}
// E5-P2-4: GridTrading cooldown_ms default — matches `new_adaptive_with_mode`
// constructor literal to preserve bit-exact behaviour when TOML omits the field.
// E5-P2-4：GridTrading cooldown_ms 默認值與 `new_adaptive_with_mode` constructor
// literal 一致，確保 TOML 未指定時行為 bit-exact。
fn default_grid_cooldown_ms() -> u64 {
    60_000
}

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
        mac.entry_conf_base = p.ma_crossover.entry_conf_base;
        mac.entry_regime_bonus = p.ma_crossover.entry_regime_bonus;
        mac.exit_conf_base = p.ma_crossover.exit_conf_base;
        // G-SR-1 A0-c: Wire confluence params from TOML.
        // G-SR-1 A0-c：從 TOML 接線匯流參數。
        mac.min_persistence_ms = p.ma_crossover.min_persistence_ms;
        mac.min_notional_usd = p.ma_crossover.min_notional_usd;
        mac.confluence_config = p.ma_crossover.build_confluence_config();
        mac.set_conf_scale(p.ma_crossover.conf_scale);
        mac.set_active(p.ma_crossover.active);
        strategies.push(Box::new(mac));

        // BbReversion
        let mut bbr = bb_reversion::BbReversion::new();
        bbr.cooldown_ms = p.bb_reversion.cooldown_ms;
        bbr.use_limit = p.bb_reversion.use_limit;
        bbr.limit_offset_bps = p.bb_reversion.limit_offset_bps;
        bbr.rsi_oversold = p.bb_reversion.rsi_oversold;
        bbr.rsi_overbought = p.bb_reversion.rsi_overbought;
        bbr.entry_conf_base = p.bb_reversion.entry_conf_base;
        bbr.exit_conf_base = p.bb_reversion.exit_conf_base;
        bbr.exit_pctb_lower = p.bb_reversion.exit_pctb_lower;
        bbr.exit_pctb_upper = p.bb_reversion.exit_pctb_upper;
        bbr.hurst_regime_boost = p.bb_reversion.hurst_regime_boost;
        // G-SR-1 A0-c: Wire confluence params from TOML.
        bbr.min_persistence_ms = p.bb_reversion.min_persistence_ms;
        bbr.min_notional_usd = p.bb_reversion.min_notional_usd;
        bbr.confluence_config = p.bb_reversion.build_confluence_config();
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
        bbb.squeeze_expiry_ms = p.bb_breakout.squeeze_expiry_ms;
        bbb.entry_conf_base = p.bb_breakout.entry_conf_base;
        bbb.exit_conf_base = p.bb_breakout.exit_conf_base;
        // E5-P2-4: wire new config-driven confidence offsets from TOML.
        // E5-P2-4：從 TOML 接線新增的 config 驅動信心偏移參數。
        bbb.hurst_regime_boost = p.bb_breakout.hurst_regime_boost;
        bbb.exit_bonus_trailing_stop = p.bb_breakout.exit_bonus_trailing_stop;
        bbb.exit_bonus_regime_shift = p.bb_breakout.exit_bonus_regime_shift;
        bbb.exit_bonus_pctb_revert = p.bb_breakout.exit_bonus_pctb_revert;
        bbb.exit_penalty_bw_squeeze = p.bb_breakout.exit_penalty_bw_squeeze;
        // G-SR-1 A0-c: Wire confluence params from TOML.
        bbb.min_persistence_ms = p.bb_breakout.min_persistence_ms;
        bbb.min_notional_usd = p.bb_breakout.min_notional_usd;
        bbb.confluence_config = p.bb_breakout.build_confluence_config();
        bbb.set_conf_scale(p.bb_breakout.conf_scale);
        bbb.set_active(p.bb_breakout.active);
        strategies.push(Box::new(bbb));

        // GridTrading
        let spacing = match p.grid_trading.spacing_mode.as_str() {
            "geometric" => grid_helpers::GridSpacingMode::Geometric,
            _ => grid_helpers::GridSpacingMode::Linear,
        };
        let mut gt = grid_trading::GridTrading::new_adaptive_with_mode(spacing);
        // E5-P2-4: grid cooldown_ms now reachable from TOML (was unreachable before).
        // E5-P2-4：grid cooldown_ms 現可由 TOML 控制（原本 unreachable）。
        gt.cooldown_ms = p.grid_trading.cooldown_ms;
        gt.health_check_interval = p.grid_trading.health_check_interval as usize;
        gt.max_out_of_range = p.grid_trading.max_out_of_range as usize;
        gt.grid_count = p.grid_trading.grid_levels; // RG-3: wire TOML grid_levels → runtime grid_count
        gt.adaptive_range_pct = p.grid_trading.adaptive_range_pct;
        gt.reject_backoff_ms = p.grid_trading.reject_backoff_ms;
        gt.ou_update_interval = p.grid_trading.ou_update_interval;
        gt.adx_low_threshold = p.grid_trading.adx_low_threshold;
        gt.adx_high_threshold = p.grid_trading.adx_high_threshold;
        gt.max_cooldown_boost = p.grid_trading.max_cooldown_boost;
        // EDGE-P2-3 Phase 1a: wire maker-entry params from TOML.
        gt.use_maker_entry = p.grid_trading.use_maker_entry;
        gt.maker_price_offset_bps = p.grid_trading.maker_price_offset_bps;
        // EDGE-P2-3 Phase 1B-3.1: wire PostOnly Limit timeout (clamp [15s, 300s]).
        // EDGE-P2-3 Phase 1B-3.1：PostOnly Limit 逾時 clamp 到 [15s, 300s]。
        gt.maker_limit_timeout_ms = grid_trading::clamp_maker_limit_timeout_ms(
            p.grid_trading.maker_limit_timeout_ms,
        );
        gt.set_conf_scale(p.grid_trading.conf_scale);
        gt.set_active(p.grid_trading.active);
        strategies.push(Box::new(gt));

        // FundingArb (OC-5: active when TOML sets active=true)
        // OC-5：TOML 設定 active=true 時啟用
        let mut fa = funding_arb::FundingArb::new();
        fa.cooldown_ms = p.funding_arb.cooldown_ms;
        fa.total_cost_bps = p.funding_arb.total_cost_bps;
        fa.expected_periods = p.funding_arb.expected_periods;
        fa.funding_threshold = p.funding_arb.funding_threshold;
        fa.max_basis_pct = p.funding_arb.max_basis_pct;
        fa.max_hold_ms = p.funding_arb.max_hold_ms;
        fa.entry_basis_ratio = p.funding_arb.entry_basis_ratio;
        fa.set_active(p.funding_arb.active);
        strategies.push(Box::new(fa));

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
        fn on_tick(&mut self, _ctx: &TickContext<'_>) -> Vec<StrategyAction> {
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
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
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
    fn test_strategy_factory_creates_five_strategies() {
        let strategies = StrategyFactory::create_all();
        assert_eq!(
            strategies.len(),
            5,
            "factory should produce exactly 5 strategies"
        );
        let names: Vec<&str> = strategies.iter().map(|s| s.name()).collect();
        assert!(names.contains(&"ma_crossover"), "missing ma_crossover");
        assert!(names.contains(&"bb_reversion"), "missing bb_reversion");
        assert!(names.contains(&"bb_breakout"), "missing bb_breakout");
        assert!(names.contains(&"grid_trading"), "missing grid_trading");
        assert!(names.contains(&"funding_arb"), "missing funding_arb");
    }

    #[test]
    fn test_strategy_factory_active_defaults() {
        let strategies = StrategyFactory::create_all();
        for s in &strategies {
            match s.name() {
                // OC-5: funding_arb inactive by default (TOML controls activation)
                "funding_arb" => {
                    assert!(!s.is_active(), "funding_arb should be inactive by default")
                }
                _ => assert!(s.is_active(), "{} should be active by default", s.name()),
            }
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
        assert_eq!(strategies.len(), 5);
        for s in &strategies {
            match s.name() {
                "ma_crossover" | "bb_breakout" | "funding_arb" => {
                    assert!(!s.is_active(), "{} should be inactive", s.name())
                }
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
        let mac = strategies
            .iter()
            .find(|s| s.name() == "ma_crossover")
            .unwrap();
        assert!((mac.conf_scale() - 0.5).abs() < 1e-10);
    }

    // ── E5-P2-4: TOML default defaults must match pre-extraction hard-coded values ──
    // ── E5-P2-4：TOML Default 需與原 hard-coded 值一致（bit-exact） ──

    #[test]
    fn test_e5_p2_4_bbb_toml_defaults_bit_exact() {
        // `strategies::BbBreakoutParams::default()` feeds factory → runtime when
        // TOML omits the fields. Must be byte-identical to previous hard-coded
        // literals so deployment without TOML changes is a no-op.
        // `strategies::BbBreakoutParams::default()` 是 TOML 缺欄位時的回退來源，
        // 需與原硬編碼數值位元相等，以保證不改 TOML 部署時行為零差異。
        let p = BbBreakoutParams::default();
        assert!(
            (p.hurst_regime_boost - 0.1).abs() < f64::EPSILON,
            "TOML default hurst_regime_boost must be 0.1"
        );
        assert!(
            (p.exit_bonus_trailing_stop - 0.2).abs() < f64::EPSILON,
            "TOML default exit_bonus_trailing_stop must be 0.2"
        );
        assert!(
            (p.exit_bonus_regime_shift - 0.1).abs() < f64::EPSILON,
            "TOML default exit_bonus_regime_shift must be 0.1"
        );
        assert!(
            (p.exit_bonus_pctb_revert - 0.05).abs() < f64::EPSILON,
            "TOML default exit_bonus_pctb_revert must be 0.05"
        );
        assert!(
            (p.exit_penalty_bw_squeeze - 0.05).abs() < f64::EPSILON,
            "TOML default exit_penalty_bw_squeeze must be 0.05"
        );
    }

    #[test]
    fn test_e5_p2_4_bbb_toml_omitted_fields_fall_back_to_defaults() {
        // Writing a minimal TOML (only confluence bits) must leave the new
        // config-driven offsets at their hard-coded defaults.
        // 只寫入最小 TOML 時，新增的 config 欄位需回退到預設（bit-exact）。
        let td = tempfile::tempdir().unwrap();
        let toml_content = r#"
[bb_breakout]
squeeze_bw = 0.03
"#;
        std::fs::write(
            td.path().join("strategy_params_paper.toml"),
            toml_content,
        )
        .unwrap();
        let cfg = load_strategy_params_from(PipelineKind::Paper, td.path());
        assert!((cfg.bb_breakout.squeeze_bw - 0.03).abs() < f64::EPSILON);
        assert!(
            (cfg.bb_breakout.hurst_regime_boost - 0.1).abs() < f64::EPSILON,
            "omitted TOML → default 0.1"
        );
        assert!(
            (cfg.bb_breakout.exit_bonus_trailing_stop - 0.2).abs() < f64::EPSILON,
            "omitted TOML → default 0.2"
        );
    }

    #[test]
    fn test_e5_p2_4_factory_wires_bbb_new_fields() {
        // Non-default TOML values must reach the live BbBreakout runtime via factory.
        // TOML 指定的非預設值需經工廠傳遞到運行時 BbBreakout。
        let mut p = StrategyParamsConfig::default();
        p.bb_breakout.hurst_regime_boost = 0.22;
        p.bb_breakout.exit_bonus_trailing_stop = 0.33;
        p.bb_breakout.exit_bonus_regime_shift = 0.11;
        p.bb_breakout.exit_bonus_pctb_revert = 0.09;
        p.bb_breakout.exit_penalty_bw_squeeze = 0.06;
        let strategies = StrategyFactory::create_with_params(&p);
        let bbb_any = strategies
            .iter()
            .find(|s| s.name() == "bb_breakout")
            .expect("bb_breakout strategy created");
        // Re-serialize via get_params_json for a type-erased runtime assertion.
        // 由於 trait object 無法 downcast，改用 get_params_json 做型別無關驗證。
        let json = bbb_any.get_params_json();
        assert!(
            json.contains("\"hurst_regime_boost\":0.22"),
            "factory must wire hurst_regime_boost=0.22 into runtime, got {json}"
        );
        assert!(
            json.contains("\"exit_bonus_trailing_stop\":0.33"),
            "factory must wire exit_bonus_trailing_stop=0.33 into runtime, got {json}"
        );
        assert!(
            json.contains("\"exit_bonus_regime_shift\":0.11"),
            "factory must wire exit_bonus_regime_shift=0.11 into runtime, got {json}"
        );
        assert!(
            json.contains("\"exit_bonus_pctb_revert\":0.09"),
            "factory must wire exit_bonus_pctb_revert=0.09 into runtime, got {json}"
        );
        assert!(
            json.contains("\"exit_penalty_bw_squeeze\":0.06"),
            "factory must wire exit_penalty_bw_squeeze=0.06 into runtime, got {json}"
        );
    }

    #[test]
    fn test_e5_p2_4_grid_cooldown_toml_default_bit_exact() {
        // Default must match the `new_adaptive_with_mode` constructor literal
        // (60_000 ms) so the factory — now wiring cooldown_ms from TOML — does
        // not change behaviour for any existing deployment that omits the field.
        // 默認值需與 `new_adaptive_with_mode` constructor literal（60_000 ms）一致，
        // 使工廠新增的 TOML wiring 在未設 cooldown_ms 的部署下行為不變。
        let p = GridTradingParams::default();
        assert_eq!(
            p.cooldown_ms, 60_000,
            "grid_trading.cooldown_ms TOML default must equal constructor literal 60_000"
        );
    }

    #[test]
    fn test_e5_p2_4_grid_cooldown_factory_wires_value() {
        // Factory must propagate TOML cooldown_ms to the runtime grid strategy.
        // Previously this field was unreachable from TOML; now covered.
        // 工廠需將 TOML cooldown_ms 傳遞到 grid 策略運行時；原本 TOML 無法觸及，現已補齊。
        let mut p = StrategyParamsConfig::default();
        p.grid_trading.cooldown_ms = 123_456;
        let strategies = StrategyFactory::create_with_params(&p);
        let gt_any = strategies
            .iter()
            .find(|s| s.name() == "grid_trading")
            .expect("grid_trading strategy created");
        let json = gt_any.get_params_json();
        assert!(
            json.contains("\"cooldown_ms\":123456"),
            "factory must wire cooldown_ms=123456 into runtime grid strategy, got {json}"
        );
    }

    #[test]
    fn test_e5_p2_4_grid_cooldown_toml_roundtrip() {
        // TOML round-trip must preserve the new cooldown_ms value.
        // TOML 序列化往返需保留新的 cooldown_ms 值。
        let mut cfg = StrategyParamsConfig::default();
        cfg.grid_trading.cooldown_ms = 90_000;
        let toml_str = toml::to_string(&cfg).expect("serialize to TOML");
        let de: StrategyParamsConfig = toml::from_str(&toml_str).expect("deserialize from TOML");
        assert_eq!(de.grid_trading.cooldown_ms, 90_000);
    }

    // ── EDGE-P2-3 Phase 1B-3.1: maker_limit_timeout_ms plumbing ──
    // ── EDGE-P2-3 Phase 1B-3.1：maker_limit_timeout_ms 配置接線 ──

    #[test]
    fn test_edge_p2_3_1b31_maker_timeout_toml_default_bit_exact() {
        // Default must equal the canonical 45_000 ms (P0 QC design budget).
        // 默認值需等於規格 45_000 ms（P0 QC 設計預算）。
        let p = GridTradingParams::default();
        assert_eq!(
            p.maker_limit_timeout_ms, 45_000,
            "grid_trading.maker_limit_timeout_ms default must be 45_000"
        );
    }

    #[test]
    fn test_edge_p2_3_1b31_maker_timeout_toml_roundtrip() {
        // TOML round-trip must preserve the configured timeout.
        // TOML 往返需保留設定值。
        let mut cfg = StrategyParamsConfig::default();
        cfg.grid_trading.maker_limit_timeout_ms = 60_000;
        let toml_str = toml::to_string(&cfg).expect("serialize to TOML");
        let de: StrategyParamsConfig = toml::from_str(&toml_str).expect("deserialize from TOML");
        assert_eq!(de.grid_trading.maker_limit_timeout_ms, 60_000);
    }

    #[test]
    fn test_edge_p2_3_1b31_maker_timeout_factory_clamps_low_value() {
        // Factory must clamp below-floor TOML values up to MIN (15_000 ms).
        // 工廠對低於下限的 TOML 值需 clamp 到 MIN (15_000 ms)。
        let mut p = StrategyParamsConfig::default();
        p.grid_trading.maker_limit_timeout_ms = 1_000; // below 15_000 floor
        let strategies = StrategyFactory::create_with_params(&p);
        let gt_any = strategies
            .iter()
            .find(|s| s.name() == "grid_trading")
            .expect("grid_trading strategy created");
        let json = gt_any.get_params_json();
        assert!(
            json.contains("\"maker_limit_timeout_ms\":15000"),
            "factory must clamp 1_000 → 15_000, got {json}"
        );
    }

    #[test]
    fn test_edge_p2_3_1b31_maker_timeout_factory_clamps_high_value() {
        // Factory must clamp above-ceiling TOML values down to MAX (300_000 ms).
        // 工廠對超過上限的 TOML 值需 clamp 到 MAX (300_000 ms)。
        let mut p = StrategyParamsConfig::default();
        p.grid_trading.maker_limit_timeout_ms = 10_000_000; // above 300_000 ceiling
        let strategies = StrategyFactory::create_with_params(&p);
        let gt_any = strategies
            .iter()
            .find(|s| s.name() == "grid_trading")
            .expect("grid_trading strategy created");
        let json = gt_any.get_params_json();
        assert!(
            json.contains("\"maker_limit_timeout_ms\":300000"),
            "factory must clamp 10_000_000 → 300_000, got {json}"
        );
    }

    #[test]
    fn test_edge_p2_3_1b31_maker_timeout_factory_passes_through_in_range() {
        // Within-range TOML value must flow through unchanged.
        // 在範圍內的 TOML 值需原樣傳遞。
        let mut p = StrategyParamsConfig::default();
        p.grid_trading.maker_limit_timeout_ms = 60_000;
        let strategies = StrategyFactory::create_with_params(&p);
        let gt_any = strategies
            .iter()
            .find(|s| s.name() == "grid_trading")
            .expect("grid_trading strategy created");
        let json = gt_any.get_params_json();
        assert!(
            json.contains("\"maker_limit_timeout_ms\":60000"),
            "factory must pass 60_000 through unchanged, got {json}"
        );
    }
}

//! Strategy modules — 5 trading strategies (R04-5).
//! 策略模組 — 5 個交易策略。

pub mod bb_breakout;
pub mod bb_reversion;
pub mod funding_arb;
pub mod grid_trading;
pub mod ma_crossover;

use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use openclaw_core::execution::FillResult;
use serde::{Deserialize, Serialize};

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

    /// Process a tick and return trade intents.
    /// 處理 tick 並返回交易意圖。
    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent>;

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

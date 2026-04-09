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
}

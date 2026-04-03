//! Trade intents, order intents, and risk verdicts.
//! 交易意圖、訂單意圖、風控裁決。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Data quality marking (Principle #10 cognitive honesty).
/// 數據質量標記（原則 #10 認知誠實）。
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
pub enum DataQualityLevel {
    /// Exchange API confirmed.
    Fact,
    /// Derived from multiple facts.
    #[default]
    Inference,
    /// Limited-information guess.
    Hypothesis,
}

impl std::fmt::Display for DataQualityLevel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Fact => write!(f, "fact"),
            Self::Inference => write!(f, "inference"),
            Self::Hypothesis => write!(f, "hypothesis"),
        }
    }
}

/// Strategist's intention to enter a trade.
/// 策略師的交易意圖。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeIntent {
    pub intent_id: String,
    pub symbol: String,
    pub strategy: String,
    pub direction: String,
    pub size: f64,
    pub confidence: f64,
    pub thesis: String,
    pub invalidation_condition: String,
    pub data_quality: DataQualityLevel,
    #[serde(default)]
    pub params: HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

impl TradeIntent {
    pub fn new(symbol: String, strategy: String, direction: String, size: f64) -> Self {
        Self {
            intent_id: format!("intent_{}", uuid::Uuid::new_v4().simple()),
            symbol,
            strategy,
            direction,
            size,
            confidence: 0.5,
            thesis: String::new(),
            invalidation_condition: String::new(),
            data_quality: DataQualityLevel::default(),
            params: HashMap::new(),
            metadata: HashMap::new(),
        }
    }
}

/// Order placement intent sent to Executor.
/// 發送給 Executor 的訂單意圖。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderIntent {
    pub symbol: String,
    pub side: String,
    pub order_type: String,
    pub qty: f64,
    pub price: Option<f64>,
    pub strategy_name: String,
    pub reason: String,
    pub confidence: f64,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

impl OrderIntent {
    pub fn new(symbol: String, side: String, qty: f64, strategy_name: String) -> Self {
        Self {
            symbol,
            side,
            order_type: "limit".into(),
            qty,
            price: None,
            strategy_name,
            reason: String::new(),
            confidence: 0.5,
            metadata: HashMap::new(),
        }
    }
}

/// Guardian's risk review result.
/// 守衛的風控裁決。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskVerdict {
    pub verdict_id: String,
    pub intent_id: String,
    pub result: String,
    pub reason: String,
    pub risk_score: f64,
    #[serde(default)]
    pub modified_params: HashMap<String, serde_json::Value>,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

impl RiskVerdict {
    pub fn new(intent_id: String, result: String) -> Self {
        Self {
            verdict_id: format!("verdict_{}", uuid::Uuid::new_v4().simple()),
            intent_id,
            result,
            reason: String::new(),
            risk_score: 0.5,
            modified_params: HashMap::new(),
            metadata: HashMap::new(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trade_intent_serde() {
        let ti = TradeIntent::new("BTCUSDT".into(), "ma_crossover".into(), "long".into(), 0.01);
        let json = serde_json::to_string(&ti).unwrap();
        let de: TradeIntent = serde_json::from_str(&json).unwrap();
        assert_eq!(de.symbol, "BTCUSDT");
        assert!(de.intent_id.starts_with("intent_"));
    }

    #[test]
    fn test_order_intent_serde() {
        let oi = OrderIntent::new("ETHUSDT".into(), "Buy".into(), 1.0, "bb_reversion".into());
        let json = serde_json::to_string(&oi).unwrap();
        let de: OrderIntent = serde_json::from_str(&json).unwrap();
        assert_eq!(de.order_type, "limit");
    }

    #[test]
    fn test_risk_verdict_serde() {
        let rv = RiskVerdict::new("intent_abc".into(), "approved".into());
        let json = serde_json::to_string(&rv).unwrap();
        let de: RiskVerdict = serde_json::from_str(&json).unwrap();
        assert_eq!(de.result, "approved");
    }

    #[test]
    fn test_data_quality_display() {
        assert_eq!(DataQualityLevel::Fact.to_string(), "fact");
        assert_eq!(DataQualityLevel::Hypothesis.to_string(), "hypothesis");
    }
}

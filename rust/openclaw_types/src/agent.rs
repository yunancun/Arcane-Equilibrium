//! Agent roles, message types, and inter-agent communication protocol.
//! Agent 角色、消息類型、Agent 間通信協議。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Five core agent roles + conductor (Principle #15).
/// 五個核心 Agent 角色 + 編排器（原則 #15）。
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq, Hash)]
pub enum AgentRole {
    Scout,
    Strategist,
    Guardian,
    Analyst,
    Executor,
    Conductor,
}

impl std::fmt::Display for AgentRole {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Scout => write!(f, "scout"),
            Self::Strategist => write!(f, "strategist"),
            Self::Guardian => write!(f, "guardian"),
            Self::Analyst => write!(f, "analyst"),
            Self::Executor => write!(f, "executor"),
            Self::Conductor => write!(f, "conductor"),
        }
    }
}

/// Inter-agent message types.
/// Agent 間消息類型。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum MessageType {
    IntelObject,
    EventAlert,
    TradeIntent,
    RiskVerdict,
    ApprovedIntent,
    ExecutionReport,
    RoundTripComplete,
    PatternInsight,
    RiskPattern,
    StrategyProposal,
    SystemDirective,
}

impl std::fmt::Display for MessageType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let s = match self {
            Self::IntelObject => "intel_object",
            Self::EventAlert => "event_alert",
            Self::TradeIntent => "trade_intent",
            Self::RiskVerdict => "risk_verdict",
            Self::ApprovedIntent => "approved_intent",
            Self::ExecutionReport => "execution_report",
            Self::RoundTripComplete => "round_trip_complete",
            Self::PatternInsight => "pattern_insight",
            Self::RiskPattern => "risk_pattern",
            Self::StrategyProposal => "strategy_proposal",
            Self::SystemDirective => "system_directive",
        };
        write!(f, "{s}")
    }
}

/// Structured inter-agent message.
/// 結構化 Agent 間消息。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMessage {
    pub message_id: String,
    pub sender: AgentRole,
    pub receiver: AgentRole,
    pub message_type: MessageType,
    pub timestamp_ms: u64,
    pub priority: u8,
    pub payload: HashMap<String, serde_json::Value>,
}

impl AgentMessage {
    pub fn new(sender: AgentRole, receiver: AgentRole, message_type: MessageType) -> Self {
        Self {
            message_id: format!("msg_{}", uuid::Uuid::new_v4().simple()),
            sender,
            receiver,
            message_type,
            timestamp_ms: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            priority: 5,
            payload: HashMap::new(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_agent_role_display() {
        assert_eq!(AgentRole::Scout.to_string(), "scout");
        assert_eq!(AgentRole::Conductor.to_string(), "conductor");
    }

    #[test]
    fn test_agent_message_serde() {
        let msg = AgentMessage::new(
            AgentRole::Scout,
            AgentRole::Strategist,
            MessageType::IntelObject,
        );
        let json = serde_json::to_string(&msg).unwrap();
        let de: AgentMessage = serde_json::from_str(&json).unwrap();
        assert_eq!(de.sender, AgentRole::Scout);
        assert_eq!(de.receiver, AgentRole::Strategist);
        assert!(de.message_id.starts_with("msg_"));
    }

    #[test]
    fn test_message_type_display() {
        assert_eq!(MessageType::TradeIntent.to_string(), "trade_intent");
    }
}

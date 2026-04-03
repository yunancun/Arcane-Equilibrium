//! Message Bus — agent message routing core.
//! 消息總線 — Agent 消息路由核心。
//!
//! Simplified for Rust engine: routes messages between 6 agent roles.
//! Guardian verdict always overrides Strategist.

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;

// ═══════════════════════════════════════════════════════════════════════════════
// Agent Roles / Agent 角色
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AgentRole {
    Scout,
    Strategist,
    Guardian,
    Analyst,
    Executor,
    Conductor,
}

impl AgentRole {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Scout => "Scout",
            Self::Strategist => "Strategist",
            Self::Guardian => "Guardian",
            Self::Analyst => "Analyst",
            Self::Executor => "Executor",
            Self::Conductor => "Conductor",
        }
    }

    /// Priority for conflict resolution (higher = more authority).
    /// 衝突解決優先級（越高 = 越有權威）。
    pub fn priority(self) -> u8 {
        match self {
            Self::Guardian => 5,   // Always wins
            Self::Conductor => 4,
            Self::Executor => 3,
            Self::Strategist => 2,
            Self::Analyst => 1,
            Self::Scout => 0,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Messages / 消息
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum MessageType {
    TradeIntent,
    RiskAlert,
    MarketUpdate,
    ExecutionReport,
    StrategySignal,
    GuardianVerdict,
    ConductorDirective,
    StatusQuery,
    StatusResponse,
    AnalysisReport,
    ConfigUpdate,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AgentMessage {
    pub id: u64,
    pub msg_type: MessageType,
    pub from: AgentRole,
    pub to: Option<AgentRole>,
    pub payload: serde_json::Value,
    pub timestamp_ms: u64,
    pub priority: u8,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Message Bus / 消息總線
// ═══════════════════════════════════════════════════════════════════════════════

pub struct MessageBus {
    queues: [VecDeque<AgentMessage>; 6],
    next_id: u64,
    max_queue_size: usize,
}

impl MessageBus {
    pub fn new() -> Self {
        Self {
            queues: Default::default(),
            next_id: 1,
            max_queue_size: 100,
        }
    }

    fn role_index(role: AgentRole) -> usize {
        match role {
            AgentRole::Scout => 0,
            AgentRole::Strategist => 1,
            AgentRole::Guardian => 2,
            AgentRole::Analyst => 3,
            AgentRole::Executor => 4,
            AgentRole::Conductor => 5,
        }
    }

    /// Send a message to a specific agent or broadcast.
    /// 發送消息到特定 Agent 或廣播。
    pub fn send(&mut self, msg_type: MessageType, from: AgentRole, to: Option<AgentRole>,
                payload: serde_json::Value) -> u64 {
        let id = self.next_id;
        self.next_id += 1;

        let msg = AgentMessage {
            id,
            msg_type,
            from,
            to,
            payload,
            timestamp_ms: crate::sm::now_ms(),
            priority: from.priority(),
        };

        match to {
            Some(target) => {
                let idx = Self::role_index(target);
                let q = &mut self.queues[idx];
                if q.len() >= self.max_queue_size {
                    q.pop_front();
                }
                q.push_back(msg);
            }
            None => {
                // Broadcast to all except sender
                for i in 0..6 {
                    if i != Self::role_index(from) {
                        let q = &mut self.queues[i];
                        if q.len() >= self.max_queue_size {
                            q.pop_front();
                        }
                        q.push_back(msg.clone());
                    }
                }
            }
        }
        id
    }

    /// Receive next message for a role.
    /// 接收指定角色的下一條消息。
    pub fn receive(&mut self, role: AgentRole) -> Option<AgentMessage> {
        self.queues[Self::role_index(role)].pop_front()
    }

    /// Peek at queue depth for a role.
    /// 查看角色的隊列深度。
    pub fn queue_depth(&self, role: AgentRole) -> usize {
        self.queues[Self::role_index(role)].len()
    }

    /// Resolve conflict: Guardian always wins over Strategist.
    /// 解決衝突：Guardian 永遠優先於 Strategist。
    pub fn resolve_conflict(a: &AgentMessage, b: &AgentMessage) -> &'static str {
        if a.from.priority() >= b.from.priority() {
            "a"
        } else {
            "b"
        }
    }

    pub fn total_messages_sent(&self) -> u64 {
        self.next_id - 1
    }
}

impl Default for MessageBus {
    fn default() -> Self { Self::new() }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_send_targeted() {
        let mut bus = MessageBus::new();
        bus.send(MessageType::TradeIntent, AgentRole::Strategist, Some(AgentRole::Guardian),
            serde_json::json!({"symbol": "BTC"}));
        assert_eq!(bus.queue_depth(AgentRole::Guardian), 1);
        assert_eq!(bus.queue_depth(AgentRole::Strategist), 0);
    }

    #[test]
    fn test_send_broadcast() {
        let mut bus = MessageBus::new();
        bus.send(MessageType::MarketUpdate, AgentRole::Scout, None,
            serde_json::json!({}));
        // All except Scout should have 1 message
        assert_eq!(bus.queue_depth(AgentRole::Scout), 0);
        assert_eq!(bus.queue_depth(AgentRole::Strategist), 1);
        assert_eq!(bus.queue_depth(AgentRole::Guardian), 1);
    }

    #[test]
    fn test_receive() {
        let mut bus = MessageBus::new();
        bus.send(MessageType::RiskAlert, AgentRole::Guardian, Some(AgentRole::Conductor),
            serde_json::json!({"level": "critical"}));
        let msg = bus.receive(AgentRole::Conductor).unwrap();
        assert_eq!(msg.msg_type, MessageType::RiskAlert);
        assert_eq!(msg.from, AgentRole::Guardian);
    }

    #[test]
    fn test_receive_empty() {
        let mut bus = MessageBus::new();
        assert!(bus.receive(AgentRole::Scout).is_none());
    }

    #[test]
    fn test_queue_overflow() {
        let mut bus = MessageBus::new();
        bus.max_queue_size = 3;
        for i in 0..5 {
            bus.send(MessageType::StatusQuery, AgentRole::Conductor, Some(AgentRole::Scout),
                serde_json::json!({"i": i}));
        }
        assert_eq!(bus.queue_depth(AgentRole::Scout), 3);
    }

    #[test]
    fn test_conflict_resolution() {
        let guardian_msg = AgentMessage {
            id: 1, msg_type: MessageType::GuardianVerdict, from: AgentRole::Guardian,
            to: None, payload: serde_json::json!({}), timestamp_ms: 0, priority: 5,
        };
        let strategist_msg = AgentMessage {
            id: 2, msg_type: MessageType::StrategySignal, from: AgentRole::Strategist,
            to: None, payload: serde_json::json!({}), timestamp_ms: 0, priority: 2,
        };
        assert_eq!(MessageBus::resolve_conflict(&guardian_msg, &strategist_msg), "a");
        assert_eq!(MessageBus::resolve_conflict(&strategist_msg, &guardian_msg), "b");
    }

    #[test]
    fn test_role_priorities() {
        assert!(AgentRole::Guardian.priority() > AgentRole::Strategist.priority());
        assert!(AgentRole::Conductor.priority() > AgentRole::Executor.priority());
    }
}

//! Fail-soft Agent Spine store abstraction.

use super::events::{
    ExecutionIdempotencyKey, SpineEdge, SpineObjectEnvelope, SpineStateTransition,
};
use tokio::sync::mpsc;

/// P1-STARTUP-BURST-MITIGATION (2026-05-15): Agent Spine writer channel cap.
///
/// Wave 1.6 moved 1024 -> 8192. Post-deploy evidence still showed restart
/// startup-burst pressure, so cap is raised to 32768 while preserving bounded
/// back-pressure and the existing drop/retry metrics.
pub const AGENT_SPINE_CHANNEL_CAPACITY: usize = 32_768;

#[derive(Debug, Clone, PartialEq)]
pub enum AgentSpineMsg {
    Object(SpineObjectEnvelope),
    Edge(SpineEdge),
    StateTransition(SpineStateTransition),
    ExecutionIdempotencyKey(ExecutionIdempotencyKey),
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoreAck {
    pub accepted: bool,
    pub queued: bool,
    pub reason: Option<String>,
}

impl StoreAck {
    pub fn queued() -> Self {
        Self {
            accepted: true,
            queued: true,
            reason: None,
        }
    }

    pub fn disabled() -> Self {
        Self {
            accepted: false,
            queued: false,
            reason: Some("disabled".to_string()),
        }
    }

    pub fn rejected(reason: impl Into<String>) -> Self {
        Self {
            accepted: false,
            queued: false,
            reason: Some(reason.into()),
        }
    }
}

pub trait AgentSpineStore: Send + Sync {
    fn put_object(&self, object: SpineObjectEnvelope) -> StoreAck;
    fn put_edge(&self, edge: SpineEdge) -> StoreAck;
    fn put_state_transition(&self, transition: SpineStateTransition) -> StoreAck;
    fn reserve_execution_key(&self, key: ExecutionIdempotencyKey) -> StoreAck;
}

#[derive(Debug, Default, Clone)]
pub struct DisabledAgentSpineStore;

impl AgentSpineStore for DisabledAgentSpineStore {
    fn put_object(&self, _object: SpineObjectEnvelope) -> StoreAck {
        StoreAck::disabled()
    }

    fn put_edge(&self, _edge: SpineEdge) -> StoreAck {
        StoreAck::disabled()
    }

    fn put_state_transition(&self, _transition: SpineStateTransition) -> StoreAck {
        StoreAck::disabled()
    }

    fn reserve_execution_key(&self, _key: ExecutionIdempotencyKey) -> StoreAck {
        StoreAck::disabled()
    }
}

#[derive(Debug, Clone)]
pub struct ChannelAgentSpineStore {
    tx: mpsc::Sender<AgentSpineMsg>,
}

impl ChannelAgentSpineStore {
    pub fn new(tx: mpsc::Sender<AgentSpineMsg>) -> Self {
        Self { tx }
    }

    fn try_send(&self, msg: AgentSpineMsg) -> StoreAck {
        match self.tx.try_send(msg) {
            Ok(()) => StoreAck::queued(),
            Err(mpsc::error::TrySendError::Full(_)) => StoreAck::rejected("channel_full"),
            Err(mpsc::error::TrySendError::Closed(_)) => StoreAck::rejected("channel_closed"),
        }
    }
}

impl AgentSpineStore for ChannelAgentSpineStore {
    fn put_object(&self, object: SpineObjectEnvelope) -> StoreAck {
        self.try_send(AgentSpineMsg::Object(object))
    }

    fn put_edge(&self, edge: SpineEdge) -> StoreAck {
        self.try_send(AgentSpineMsg::Edge(edge))
    }

    fn put_state_transition(&self, transition: SpineStateTransition) -> StoreAck {
        self.try_send(AgentSpineMsg::StateTransition(transition))
    }

    fn reserve_execution_key(&self, key: ExecutionIdempotencyKey) -> StoreAck {
        self.try_send(AgentSpineMsg::ExecutionIdempotencyKey(key))
    }
}

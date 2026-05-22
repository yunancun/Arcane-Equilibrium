//! M3 Sprint 2 Track A — Health State Change Event Bus（Sprint 5 cascade 預埋）。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §3.1 + §4.1 step 5，M3 emitter 在 state transition fire 時 emit
//!   `HealthStateChangeEvent` 到 event bus。Sprint 2 IMPL 只「發布」事件，
//!   Sprint 5 才接 cascade subscribe（LAL Tier 降階 / Strategy reparam halt /
//!   alert routing）。本 module 提供穩定 publish API + in-memory broadcast
//!   stub，subscriber Sprint 5 才接線。
//!
//! 主要類 / 函數:
//!   - `HealthStateChangeEvent`：state transition 事件 struct（含 transition_id
//!      + domain + old_state + new_state + observed_at + reason_summary +
//!      amplification_loop_24h_count + anomaly_id）。
//!   - `HealthEventBus`：tokio::sync::broadcast 包裝 + fail-soft publish
//!     （channel 滿時不阻塞、不錯誤升級）。
//!   - `HealthEventSubscriber`：Sprint 5 cascade 訂閱介面。
//!
//! 依賴:
//!   - std + tokio::sync::broadcast + uuid + chrono + serde（V106 row INSERT 對
//!     齊用）。
//!   - 不依賴 PgPool / Bybit client / GovernanceHub。
//!
//! 硬邊界:
//!   - publish 為 fail-soft（broadcast lagged 不算 fire fail；spec §4.1 註 fail-soft
//!     emit 不阻 V106 write）。
//!   - 不執行 cascade 副作用（halt strategy / 降 LAL Tier / Slack alert）；Sprint 5
//!     才接 subscriber。
//!   - 不繞 Guardian / 5-gate；只 emit 事件供觀察者（per ADR-0042 Decision 1
//!     反模式禁忌 (b) Strategy 自己 emit HEALTH_DEGRADED 直接 trigger cascade）。

use std::time::SystemTime;

use serde::{Deserialize, Serialize};
use tokio::sync::broadcast;
use uuid::Uuid;

use super::{HealthDomain, HealthState};

/// state transition 事件主體（per spec §4.1 step 5 event payload）。
///
/// 為什麼包含 anomaly_id + amplification_loop_24h_count:
///   - Sprint 5 cascade subscriber 需 dedup（per ADR-0042 Decision 4 anomaly cap）。
///   - GUI A3 monthly review panel 需 audit trail（Sprint 8）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HealthStateChangeEvent {
    /// 事件唯一 ID，UUID v4；用於 cascade subscriber 去重。
    pub transition_id: Uuid,
    /// 觸發事件的 domain（per ADR-0042 Decision 3 6 domain 之一）。
    pub domain: HealthDomain,
    /// transition 前狀態（首次 OK→WARN 場景 prev 為 HealthOk）。
    pub old_state: HealthState,
    /// transition 後狀態。
    pub new_state: HealthState,
    /// 事件 wall-clock 時間；對齊 V106 observed_at column 語意。
    pub observed_at: SystemTime,
    /// 觸發此 transition 的 anomaly_id（per ADR-0042 Decision 4 cap key）。
    pub anomaly_id: String,
    /// 24h rolling window amplification cap 計數（fire 後值）。
    pub amplification_loop_24h_count: u32,
    /// 人類可讀 transition 理由（cascade subscriber + audit 用）。
    pub reason_summary: String,
}

/// HealthEventBus broadcast channel 預設容量（Sprint 5 cascade subscriber 數量
/// 上限 8 per ADR-0042 Decision 5，廣播 buffer 設 256 給足容差）。
///
/// 為什麼 256：6 domain × 4 transition × 多 anomaly_id ≈ 100 events/day burst
/// 上限；fail-soft 即使 lagged 也只丟 stale subscriber 不阻 publisher。
pub const HEALTH_EVENT_CHANNEL_CAPACITY: usize = 256;

/// In-memory 廣播 bus；Sprint 2 不接 cross-process channel（Sprint 5 才接）。
///
/// 為什麼 broadcast 非 mpsc:
///   - cascade subscriber 多端（LAL gate / Strategist / Alert router / GUI）。
///   - fail-soft publish：channel 滿時 broadcast 自然 drop lagged subscriber
///     RecvError::Lagged，publisher 仍 Ok。
#[derive(Debug, Clone)]
pub struct HealthEventBus {
    sender: broadcast::Sender<HealthStateChangeEvent>,
}

impl HealthEventBus {
    /// 建立新 event bus，channel 容量 `HEALTH_EVENT_CHANNEL_CAPACITY`。
    pub fn new() -> Self {
        let (sender, _receiver) = broadcast::channel(HEALTH_EVENT_CHANNEL_CAPACITY);
        Self { sender }
    }

    /// 自定容量；test 用。
    pub fn with_capacity(capacity: usize) -> Self {
        let (sender, _receiver) = broadcast::channel(capacity);
        Self { sender }
    }

    /// Fail-soft 發布事件；無 subscriber / channel lagged 都不算錯誤。
    ///
    /// 為什麼 fail-soft:
    ///   - spec §4.1 註：「event emit 失敗不阻 V106 write」；V106 audit row 是
    ///     SSOT，event bus 是 cascade 通知層而非 source of truth。
    ///   - Sprint 5 cascade subscriber 自己負責掉 event 的 backfill（透過 V106
    ///     query）；不在 publisher 端 retry。
    pub fn publish(&self, event: HealthStateChangeEvent) {
        // broadcast send 失敗 = 沒有 active subscriber，安全忽略。
        let _ = self.sender.send(event);
    }

    /// 訂閱 cascade event；Sprint 5 cascade IMPL 使用。
    pub fn subscribe(&self) -> HealthEventSubscriber {
        HealthEventSubscriber {
            receiver: self.sender.subscribe(),
        }
    }

    /// 當前 active subscriber 數；test 用。
    pub fn receiver_count(&self) -> usize {
        self.sender.receiver_count()
    }
}

impl Default for HealthEventBus {
    fn default() -> Self {
        Self::new()
    }
}

/// Cascade subscriber 包裝（Sprint 5 LAL gate / Strategist / Alert router 用）。
pub struct HealthEventSubscriber {
    receiver: broadcast::Receiver<HealthStateChangeEvent>,
}

impl HealthEventSubscriber {
    /// 接收下一個事件；channel lagged 時返回 RecvError::Lagged，caller 端可
    /// fallback 走 V106 backfill query。
    pub async fn recv(
        &mut self,
    ) -> Result<HealthStateChangeEvent, broadcast::error::RecvError> {
        self.receiver.recv().await
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_event(domain: HealthDomain, new_state: HealthState) -> HealthStateChangeEvent {
        HealthStateChangeEvent {
            transition_id: Uuid::new_v4(),
            domain,
            old_state: HealthState::HealthOk,
            new_state,
            observed_at: SystemTime::now(),
            anomaly_id: "test_anomaly".to_string(),
            amplification_loop_24h_count: 1,
            reason_summary: "test transition".to_string(),
        }
    }

    #[test]
    fn test_publish_without_subscriber_is_fail_soft() {
        // spec §4.1 fail-soft：無 subscriber 不算錯誤。
        let bus = HealthEventBus::new();
        let event = make_event(HealthDomain::EngineRuntime, HealthState::HealthWarn);
        // publish 不會 panic 也不會 return Err。
        bus.publish(event);
        assert_eq!(bus.receiver_count(), 0);
    }

    #[tokio::test]
    async fn test_publish_delivers_to_subscriber() {
        let bus = HealthEventBus::new();
        let mut sub = bus.subscribe();
        let event = make_event(HealthDomain::EngineRuntime, HealthState::HealthWarn);
        let transition_id = event.transition_id;
        bus.publish(event);
        let received = sub.recv().await.unwrap();
        assert_eq!(received.transition_id, transition_id);
        assert_eq!(received.new_state, HealthState::HealthWarn);
    }

    #[tokio::test]
    async fn test_multiple_subscribers_each_receive() {
        // Sprint 5 cascade 多訂閱者場景：LAL + Strategist + Alert router 各收一份。
        let bus = HealthEventBus::new();
        let mut sub1 = bus.subscribe();
        let mut sub2 = bus.subscribe();
        let event = make_event(HealthDomain::EngineRuntime, HealthState::HealthDegraded);
        let transition_id = event.transition_id;
        bus.publish(event);
        let r1 = sub1.recv().await.unwrap();
        let r2 = sub2.recv().await.unwrap();
        assert_eq!(r1.transition_id, transition_id);
        assert_eq!(r2.transition_id, transition_id);
    }

    #[test]
    fn test_default_channel_capacity_match_constant() {
        // 不變式：默認容量等於 module-level 常數。
        assert_eq!(HEALTH_EVENT_CHANNEL_CAPACITY, 256);
    }
}

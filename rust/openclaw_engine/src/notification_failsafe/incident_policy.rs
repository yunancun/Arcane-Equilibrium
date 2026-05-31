//! C4 incident policy — production incident producer for notification fail-safe.
//!
//! 模塊用途：
//!   將「需要 operator 介入」的 runtime incident 轉成三路通知 dispatch，並在
//!   arm 類事件的兩個 push channel 全失敗時，經 `FAILSAFE_FEED_SENDERS.outcome_tx`
//!   餵入既有 C4 watcher。watcher 仍是唯一 timer / SM-04 Defensive 觸發路徑；
//!   本模塊只負責 incident 分級、sustained / throttle / 7d cooling 與 self-heal。
//!
//! 硬邊界：
//!   - 不直接改 RiskGovernor / system_mode / live authorization；
//!   - 不新增 exchange 寫入口；所有 set_trading_stop 副作用仍走 C4 owner handler；
//!   - secret 未配置時 arm 類事件降為 notify-only，不餵 `AllFail` 武裝 timer。

use std::collections::HashMap;
use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};

use parking_lot::Mutex;
use tracing::{debug, warn};

use crate::notification_failsafe::providers::single_watcher::{
    failsafe_feed_senders, FailsafeFeedSenders, SharedFailsafeWatcher,
};
use crate::notification_failsafe::{DispatchOutcome, FailsafeConfig};

const THROTTLE_MS: u64 = 5 * 60 * 1_000;
const COOLING_MS: u64 = 7 * 24 * 60 * 60 * 1_000;

/// Incident class 級 key。不得加入 symbol / timestamp，否則 7d cooling 失效。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum IncidentClass {
    AuthInvalid,
    BybitFailClosed,
    EngineDead,
    SmHaltStuck,
    PositionDrift,
}

impl IncidentClass {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::AuthInvalid => "auth_invalid",
            Self::BybitFailClosed => "bybit_fail_closed",
            Self::EngineDead => "engine_dead",
            Self::SmHaltStuck => "sm_halt_stuck",
            Self::PositionDrift => "position_drift",
        }
    }

    fn sustained_ms(self) -> u64 {
        match self {
            Self::AuthInvalid => 30_000,
            Self::BybitFailClosed => 0,
            Self::EngineDead => 30_000,
            Self::SmHaltStuck => 120_000,
            Self::PositionDrift => 0,
        }
    }

    fn default_mode(self) -> IncidentDispatchMode {
        match self {
            Self::AuthInvalid | Self::BybitFailClosed | Self::SmHaltStuck => {
                IncidentDispatchMode::ArmTimer
            }
            Self::EngineDead | Self::PositionDrift => IncidentDispatchMode::NotifyOnly,
        }
    }
}

/// 本次 incident dispatch 對 watcher timer 的意圖。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IncidentDispatchMode {
    ArmTimer,
    NotifyOnly,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum NotifyOnlyReason {
    ClassPolicy,
    CoolingActive,
    PushChannelsDisabled,
}

impl NotifyOnlyReason {
    fn as_str(self) -> &'static str {
        match self {
            Self::ClassPolicy => "class_policy_notify_only",
            Self::CoolingActive => "cooling_active_notify_only",
            Self::PushChannelsDisabled => "push_channels_disabled_notify_only",
        }
    }
}

/// `report_incident` 的可觀測結果，供測試與 caller debug 使用。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IncidentPolicyResult {
    WatcherUnavailable {
        class: IncidentClass,
    },
    WaitingForSustainedWindow {
        class: IncidentClass,
        since_ms: u64,
        required_ms: u64,
    },
    Throttled {
        class: IncidentClass,
        last_dispatch_at_ms: u64,
    },
    Dispatched {
        class: IncidentClass,
        mode: IncidentDispatchMode,
        outcome: DispatchOutcome,
        fed_to_watcher: bool,
    },
    ResolvedDisarmed {
        class: IncidentClass,
        fed_to_watcher: bool,
    },
    ResolvedNoAction {
        class: IncidentClass,
    },
}

#[derive(Debug, Default)]
struct IncidentState {
    sustained_since_ms: Option<u64>,
    last_dispatch_at_ms: Option<u64>,
    armed_at_ms: Option<u64>,
    last_cooling_at_ms: Option<u64>,
    dispatch_generation: u64,
    resolved_generation: u64,
}

#[derive(Debug, Default)]
struct PolicyLedger {
    classes: HashMap<IncidentClass, IncidentState>,
    current_armed_class: Option<IncidentClass>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PreparedIncident {
    Waiting {
        since_ms: u64,
        required_ms: u64,
    },
    Throttled {
        last_dispatch_at_ms: u64,
    },
    Dispatch {
        mode: IncidentDispatchMode,
        notify_reason: Option<NotifyOnlyReason>,
        generation: u64,
    },
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum FeedAllFailResult {
    Fed,
    AlreadyArmed,
    StaleResolved,
    ReceiverDropped,
}

impl PolicyLedger {
    fn prepare_incident(
        &mut self,
        class: IncidentClass,
        now_ms: u64,
        push_channels_enabled: bool,
    ) -> PreparedIncident {
        let state = self.classes.entry(class).or_default();
        let since_ms = *state.sustained_since_ms.get_or_insert(now_ms);
        let required_ms = class.sustained_ms();
        if now_ms.saturating_sub(since_ms) < required_ms {
            return PreparedIncident::Waiting {
                since_ms,
                required_ms,
            };
        }

        if let Some(last) = state.last_dispatch_at_ms {
            if now_ms.saturating_sub(last) < THROTTLE_MS {
                return PreparedIncident::Throttled {
                    last_dispatch_at_ms: last,
                };
            }
        }

        let mut mode = class.default_mode();
        let mut notify_reason =
            (mode == IncidentDispatchMode::NotifyOnly).then_some(NotifyOnlyReason::ClassPolicy);

        if mode == IncidentDispatchMode::ArmTimer && !push_channels_enabled {
            mode = IncidentDispatchMode::NotifyOnly;
            notify_reason = Some(NotifyOnlyReason::PushChannelsDisabled);
        }

        if mode == IncidentDispatchMode::ArmTimer {
            if let Some(last_cooling) = state.last_cooling_at_ms {
                if now_ms.saturating_sub(last_cooling) < COOLING_MS {
                    mode = IncidentDispatchMode::NotifyOnly;
                    notify_reason = Some(NotifyOnlyReason::CoolingActive);
                }
            }
        }

        state.last_dispatch_at_ms = Some(now_ms);
        state.dispatch_generation = state.dispatch_generation.saturating_add(1);
        PreparedIncident::Dispatch {
            mode,
            notify_reason,
            generation: state.dispatch_generation,
        }
    }

    fn reserve_arm_owner_if_unarmed(&mut self, class: IncidentClass, now_ms: u64) -> bool {
        if self.current_armed_class.is_some() {
            return false;
        }
        let state = self.classes.entry(class).or_default();
        state.armed_at_ms = Some(now_ms);
        self.current_armed_class = Some(class);
        true
    }

    fn rollback_arm_owner(&mut self, class: IncidentClass) {
        if self.current_armed_class != Some(class) {
            return;
        }
        if let Some(state) = self.classes.get_mut(&class) {
            state.armed_at_ms = None;
        }
        self.current_armed_class = None;
    }

    fn feed_all_fail_if_unarmed(
        &mut self,
        class: IncidentClass,
        now_ms: u64,
        generation: u64,
        outcome_tx: &tokio::sync::mpsc::UnboundedSender<DispatchOutcome>,
    ) -> FeedAllFailResult {
        let state = self.classes.entry(class).or_default();
        if state.dispatch_generation != generation || state.resolved_generation >= generation {
            return FeedAllFailResult::StaleResolved;
        }
        if !self.reserve_arm_owner_if_unarmed(class, now_ms) {
            return FeedAllFailResult::AlreadyArmed;
        }
        if outcome_tx.send(DispatchOutcome::AllFail).is_ok() {
            FeedAllFailResult::Fed
        } else {
            self.rollback_arm_owner(class);
            FeedAllFailResult::ReceiverDropped
        }
    }

    fn resolve_class_at(&mut self, class: IncidentClass, now_ms: u64) -> bool {
        let is_current_owner = self.current_armed_class == Some(class);
        let state = self.classes.entry(class).or_default();
        state.sustained_since_ms = None;
        state.resolved_generation = state.dispatch_generation;

        if !is_current_owner {
            return false;
        }

        let timed_out = state
            .armed_at_ms
            .map(|armed_at_ms| {
                now_ms.saturating_sub(armed_at_ms) >= FailsafeConfig::DEFAULT_TIMEOUT_MS
            })
            .unwrap_or(false);
        state.armed_at_ms = None;
        if timed_out {
            state.last_cooling_at_ms = Some(now_ms);
        }
        self.current_armed_class = None;
        true
    }
}

static INCIDENT_POLICY_LEDGER: OnceLock<Mutex<PolicyLedger>> = OnceLock::new();

fn ledger() -> &'static Mutex<PolicyLedger> {
    INCIDENT_POLICY_LEDGER.get_or_init(|| Mutex::new(PolicyLedger::default()))
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
        .min(u64::MAX as u128) as u64
}

fn build_message(
    class: IncidentClass,
    detail: &str,
    notify_reason: Option<NotifyOnlyReason>,
) -> String {
    let reason = notify_reason
        .map(|r| r.as_str())
        .unwrap_or("arm_timer_candidate");
    format!(
        "OpenClaw incident policy: class={} mode_reason={} detail={}",
        class.as_str(),
        reason,
        detail
    )
}

/// 非阻塞 producer helper：在目前 tokio runtime 中派發 incident report。
pub fn spawn_report_incident(class: IncidentClass, detail: impl Into<String>) {
    let detail = detail.into();
    let Ok(handle) = tokio::runtime::Handle::try_current() else {
        warn!(
            class = class.as_str(),
            "incident_policy report skipped; no tokio runtime available"
        );
        return;
    };
    handle.spawn(async move {
        let result = report_incident(class, detail).await;
        debug!(
            class = class.as_str(),
            ?result,
            "incident_policy report result"
        );
    });
}

/// 回報一個持續中的 incident。arm 類只有在 dispatch 結果 `AllFail` 且 push secret
/// 已啟用時才餵 watcher；notify-only 類永遠不餵 `AllFail`。
pub async fn report_incident(
    class: IncidentClass,
    detail: impl Into<String>,
) -> IncidentPolicyResult {
    report_incident_at(class, detail.into(), now_ms()).await
}

async fn report_incident_at(
    class: IncidentClass,
    detail: String,
    observed_at_ms: u64,
) -> IncidentPolicyResult {
    let Some(watcher) = SharedFailsafeWatcher::instance() else {
        return IncidentPolicyResult::WatcherUnavailable { class };
    };
    report_incident_with(
        ledger(),
        class,
        detail,
        observed_at_ms,
        watcher.as_ref(),
        failsafe_feed_senders(),
    )
    .await
}

async fn report_incident_with(
    ledger_ref: &Mutex<PolicyLedger>,
    class: IncidentClass,
    detail: String,
    observed_at_ms: u64,
    watcher: &SharedFailsafeWatcher,
    feed_senders: Option<FailsafeFeedSenders>,
) -> IncidentPolicyResult {
    let push_channels_enabled = watcher
        .push_channels_enabled()
        .map(|(slack, email)| slack && email)
        .unwrap_or(false);

    let prepared = {
        let mut guard = ledger_ref.lock();
        guard.prepare_incident(class, observed_at_ms, push_channels_enabled)
    };

    let (mode, notify_reason, generation) = match prepared {
        PreparedIncident::Waiting {
            since_ms,
            required_ms,
        } => {
            return IncidentPolicyResult::WaitingForSustainedWindow {
                class,
                since_ms,
                required_ms,
            };
        }
        PreparedIncident::Throttled {
            last_dispatch_at_ms,
        } => {
            return IncidentPolicyResult::Throttled {
                class,
                last_dispatch_at_ms,
            };
        }
        PreparedIncident::Dispatch {
            mode,
            notify_reason,
            generation,
        } => (mode, notify_reason, generation),
    };

    let message = build_message(class, &detail, notify_reason);
    let outcome = watcher.dispatch_3way_only(&message).await;

    let mut fed_to_watcher = false;
    if mode == IncidentDispatchMode::ArmTimer && outcome == DispatchOutcome::AllFail {
        match feed_senders {
            Some(senders) => {
                let feed_result = {
                    let mut guard = ledger_ref.lock();
                    guard.feed_all_fail_if_unarmed(
                        class,
                        observed_at_ms,
                        generation,
                        &senders.outcome_tx,
                    )
                };
                match feed_result {
                    FeedAllFailResult::Fed => {
                        fed_to_watcher = true;
                    }
                    FeedAllFailResult::AlreadyArmed => {
                        warn!(
                            class = class.as_str(),
                            "incident_policy did not feed AllFail; another class is already armed"
                        );
                    }
                    FeedAllFailResult::StaleResolved => {
                        warn!(
                            class = class.as_str(),
                            "incident_policy did not feed stale AllFail; incident resolved during dispatch"
                        );
                    }
                    FeedAllFailResult::ReceiverDropped => {
                        warn!(
                            class = class.as_str(),
                            "incident_policy could not feed AllFail; outcome receiver dropped"
                        );
                    }
                }
            }
            None => {
                warn!(
                    class = class.as_str(),
                    "incident_policy could not feed AllFail; failsafe feed senders unavailable"
                );
            }
        }
    }

    IncidentPolicyResult::Dispatched {
        class,
        mode,
        outcome,
        fed_to_watcher,
    }
}

#[cfg(test)]
pub(crate) async fn report_incident_with_test_watcher(
    class: IncidentClass,
    detail: String,
    observed_at_ms: u64,
    watcher: &SharedFailsafeWatcher,
    feed_senders: Option<FailsafeFeedSenders>,
) -> IncidentPolicyResult {
    let ledger = Mutex::new(PolicyLedger::default());
    report_incident_with(
        &ledger,
        class,
        detail,
        observed_at_ms,
        watcher,
        feed_senders,
    )
    .await
}

/// 回報 incident 自癒。只有「當前 armed class」自癒才送 `AllSuccess`，避免 B
/// 類恢復誤清 A 類已武裝 timer。
pub fn report_resolved(class: IncidentClass) -> IncidentPolicyResult {
    report_resolved_with(ledger(), class, now_ms(), failsafe_feed_senders())
}

fn report_resolved_with(
    ledger_ref: &Mutex<PolicyLedger>,
    class: IncidentClass,
    observed_at_ms: u64,
    feed_senders: Option<FailsafeFeedSenders>,
) -> IncidentPolicyResult {
    let (should_disarm, fed_to_watcher) = {
        let mut guard = ledger_ref.lock();
        let should_disarm = guard.resolve_class_at(class, observed_at_ms);
        let fed_to_watcher = if should_disarm {
            feed_senders
                .map(|senders| senders.outcome_tx.send(DispatchOutcome::AllSuccess).is_ok())
                .unwrap_or(false)
        } else {
            false
        };
        (should_disarm, fed_to_watcher)
    };
    if !should_disarm {
        return IncidentPolicyResult::ResolvedNoAction { class };
    }

    IncidentPolicyResult::ResolvedDisarmed {
        class,
        fed_to_watcher,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::sync::Arc;

    use crate::notification_failsafe::providers::single_watcher::{
        NoopAuditEmitter, NoopExchangeStopSync, NoopPositionProvider,
    };
    use crate::notification_failsafe::{FailsafeClock, FailsafeDecision, NotificationDispatcher};

    fn fresh_ledger() -> PolicyLedger {
        PolicyLedger::default()
    }

    struct FixedDispatcher {
        outcome: DispatchOutcome,
        push: Option<(bool, bool)>,
    }

    #[async_trait::async_trait]
    impl NotificationDispatcher for FixedDispatcher {
        async fn dispatch_3way(&self, _message: &str) -> DispatchOutcome {
            self.outcome.clone()
        }

        fn push_channels_enabled(&self) -> Option<(bool, bool)> {
            self.push
        }
    }

    struct ArcClock(Arc<AtomicU64>);

    impl FailsafeClock for ArcClock {
        fn now_ms(&self) -> u64 {
            self.0.load(Ordering::SeqCst)
        }
    }

    fn watcher_for_test(
        outcome: DispatchOutcome,
        push: Option<(bool, bool)>,
        clock: Arc<AtomicU64>,
    ) -> SharedFailsafeWatcher {
        SharedFailsafeWatcher::new_for_test(
            Box::new(FixedDispatcher { outcome, push }),
            Box::new(NoopPositionProvider),
            Box::new(NoopExchangeStopSync),
            Box::new(NoopAuditEmitter),
            Box::new(ArcClock(clock)),
            FailsafeConfig::default(),
        )
    }

    fn local_feed_senders() -> (
        FailsafeFeedSenders,
        tokio::sync::mpsc::UnboundedReceiver<DispatchOutcome>,
    ) {
        let (outcome_tx, outcome_rx) = tokio::sync::mpsc::unbounded_channel();
        let (ack_tx, _ack_rx) = tokio::sync::mpsc::unbounded_channel();
        (FailsafeFeedSenders { outcome_tx, ack_tx }, outcome_rx)
    }

    fn seed_dispatch_generation(ledger: &mut PolicyLedger, class: IncidentClass) -> u64 {
        let state = ledger.classes.entry(class).or_default();
        state.dispatch_generation = state.dispatch_generation.saturating_add(1);
        state.dispatch_generation
    }

    #[test]
    fn auth_invalid_requires_sustained_window() {
        let mut ledger = fresh_ledger();
        let first = ledger.prepare_incident(IncidentClass::AuthInvalid, 1_000, true);
        assert!(matches!(
            first,
            PreparedIncident::Waiting {
                since_ms: 1_000,
                required_ms: 30_000
            }
        ));

        let ready = ledger.prepare_incident(IncidentClass::AuthInvalid, 31_000, true);
        assert!(matches!(
            ready,
            PreparedIncident::Dispatch {
                mode: IncidentDispatchMode::ArmTimer,
                notify_reason: None,
                ..
            }
        ));
    }

    #[test]
    fn dispatch_throttle_is_class_level() {
        let mut ledger = fresh_ledger();
        assert!(matches!(
            ledger.prepare_incident(IncidentClass::BybitFailClosed, 10_000, true),
            PreparedIncident::Dispatch { .. }
        ));

        let throttled = ledger.prepare_incident(IncidentClass::BybitFailClosed, 20_000, true);
        assert!(matches!(
            throttled,
            PreparedIncident::Throttled {
                last_dispatch_at_ms: 10_000
            }
        ));
    }

    #[test]
    fn cooling_downgrades_arm_class_to_notify_only() {
        let mut ledger = fresh_ledger();
        ledger
            .classes
            .entry(IncidentClass::BybitFailClosed)
            .or_default()
            .last_cooling_at_ms = Some(1_000);

        let after_throttle = 1_000 + THROTTLE_MS + 1;
        let prepared =
            ledger.prepare_incident(IncidentClass::BybitFailClosed, after_throttle, true);
        assert!(matches!(
            prepared,
            PreparedIncident::Dispatch {
                mode: IncidentDispatchMode::NotifyOnly,
                notify_reason: Some(NotifyOnlyReason::CoolingActive),
                ..
            }
        ));
    }

    #[test]
    fn push_channel_gate_downgrades_arm_class_to_notify_only() {
        let mut ledger = fresh_ledger();
        let prepared = ledger.prepare_incident(IncidentClass::BybitFailClosed, 1_000, false);
        assert!(matches!(
            prepared,
            PreparedIncident::Dispatch {
                mode: IncidentDispatchMode::NotifyOnly,
                notify_reason: Some(NotifyOnlyReason::PushChannelsDisabled),
                ..
            }
        ));
    }

    #[test]
    fn notify_only_classes_never_arm() {
        let mut ledger = fresh_ledger();
        let prepared = ledger.prepare_incident(IncidentClass::PositionDrift, 1_000, true);
        assert!(matches!(
            prepared,
            PreparedIncident::Dispatch {
                mode: IncidentDispatchMode::NotifyOnly,
                notify_reason: Some(NotifyOnlyReason::ClassPolicy),
                ..
            }
        ));
    }

    #[test]
    fn self_heal_only_disarms_current_armed_class() {
        let mut ledger = fresh_ledger();
        assert!(ledger.reserve_arm_owner_if_unarmed(IncidentClass::BybitFailClosed, 1_000));

        assert!(
            !ledger.resolve_class_at(IncidentClass::AuthInvalid, 2_000),
            "unrelated class must not clear current armed timer"
        );
        assert_eq!(
            ledger.current_armed_class,
            Some(IncidentClass::BybitFailClosed)
        );

        assert!(
            ledger.resolve_class_at(IncidentClass::BybitFailClosed, 2_000),
            "same class recovery may send AllSuccess"
        );
        assert_eq!(ledger.current_armed_class, None);
    }

    #[test]
    fn second_arm_class_does_not_overwrite_current_armed_class() {
        let mut ledger = fresh_ledger();
        assert!(ledger.reserve_arm_owner_if_unarmed(IncidentClass::AuthInvalid, 1_000));
        assert!(
            !ledger.reserve_arm_owner_if_unarmed(IncidentClass::BybitFailClosed, 2_000),
            "single watcher timer cannot be owned by a second class until first resolves"
        );
        assert_eq!(ledger.current_armed_class, Some(IncidentClass::AuthInvalid));
    }

    #[test]
    fn pre_timeout_self_heal_does_not_start_cooling_window() {
        let mut ledger = fresh_ledger();
        assert!(ledger.reserve_arm_owner_if_unarmed(IncidentClass::BybitFailClosed, 1_000));
        assert!(ledger.resolve_class_at(
            IncidentClass::BybitFailClosed,
            1_000 + FailsafeConfig::DEFAULT_TIMEOUT_MS - 1
        ));

        let prepared = ledger.prepare_incident(IncidentClass::BybitFailClosed, 2_000, true);
        assert!(matches!(
            prepared,
            PreparedIncident::Dispatch {
                mode: IncidentDispatchMode::ArmTimer,
                notify_reason: None,
                ..
            }
        ));
    }

    #[test]
    fn feed_all_fail_rolls_back_owner_when_receiver_dropped() {
        let mut ledger = fresh_ledger();
        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        drop(rx);
        let generation = seed_dispatch_generation(&mut ledger, IncidentClass::BybitFailClosed);

        assert_eq!(
            ledger.feed_all_fail_if_unarmed(IncidentClass::BybitFailClosed, 1_000, generation, &tx),
            FeedAllFailResult::ReceiverDropped
        );
        assert_eq!(ledger.current_armed_class, None);
        assert_eq!(
            ledger
                .classes
                .get(&IncidentClass::BybitFailClosed)
                .and_then(|state| state.armed_at_ms),
            None
        );
    }

    #[test]
    fn feed_all_fail_does_not_queue_second_armed_class() {
        let mut ledger = fresh_ledger();
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
        let auth_generation = seed_dispatch_generation(&mut ledger, IncidentClass::AuthInvalid);
        let bybit_generation =
            seed_dispatch_generation(&mut ledger, IncidentClass::BybitFailClosed);

        assert_eq!(
            ledger.feed_all_fail_if_unarmed(
                IncidentClass::AuthInvalid,
                1_000,
                auth_generation,
                &tx
            ),
            FeedAllFailResult::Fed
        );
        assert_eq!(
            ledger.feed_all_fail_if_unarmed(
                IncidentClass::BybitFailClosed,
                2_000,
                bybit_generation,
                &tx
            ),
            FeedAllFailResult::AlreadyArmed
        );
        assert_eq!(rx.try_recv(), Ok(DispatchOutcome::AllFail));
        assert!(rx.try_recv().is_err());
        assert_eq!(ledger.current_armed_class, Some(IncidentClass::AuthInvalid));
    }

    #[test]
    fn feed_all_fail_rejects_generation_resolved_during_dispatch() {
        let mut ledger = fresh_ledger();
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
        let generation = seed_dispatch_generation(&mut ledger, IncidentClass::BybitFailClosed);
        assert!(!ledger.resolve_class_at(IncidentClass::BybitFailClosed, 2_000));

        assert_eq!(
            ledger.feed_all_fail_if_unarmed(IncidentClass::BybitFailClosed, 1_000, generation, &tx),
            FeedAllFailResult::StaleResolved
        );
        assert!(rx.try_recv().is_err());
        assert_eq!(ledger.current_armed_class, None);
    }

    #[tokio::test]
    async fn report_incident_feeds_dispatch_outcome_to_watcher_timer_claim() {
        let ledger = Mutex::new(fresh_ledger());
        let clock = Arc::new(AtomicU64::new(1_000));
        let watcher = watcher_for_test(
            DispatchOutcome::AllFail,
            Some((true, true)),
            Arc::clone(&clock),
        );
        let (senders, mut outcome_rx) = local_feed_senders();

        let result = report_incident_with(
            &ledger,
            IncidentClass::BybitFailClosed,
            "deterministic producer path".to_string(),
            1_000,
            &watcher,
            Some(senders),
        )
        .await;

        assert!(matches!(
            result,
            IncidentPolicyResult::Dispatched {
                class: IncidentClass::BybitFailClosed,
                mode: IncidentDispatchMode::ArmTimer,
                outcome: DispatchOutcome::AllFail,
                fed_to_watcher: true
            }
        ));

        let fed = outcome_rx
            .recv()
            .await
            .expect("incident feeds watcher outcome");
        let decision = watcher.observe_dispatch(fed);
        assert!(matches!(decision, FailsafeDecision::TimerArmed { .. }));
        clock.store(
            1_000 + FailsafeConfig::DEFAULT_TIMEOUT_MS + 1,
            Ordering::SeqCst,
        );
        assert!(
            watcher.timer_expired_and_claim(),
            "fed AllFail should arm timer and claim after timeout"
        );
        assert!(
            !watcher.timer_expired_and_claim(),
            "same armed timer must claim only once"
        );
    }

    #[tokio::test]
    async fn report_incident_does_not_feed_if_resolved_while_dispatch_in_flight() {
        struct DelayedAllFailDispatcher {
            started_tx: tokio::sync::mpsc::UnboundedSender<()>,
            release: Arc<tokio::sync::Notify>,
        }

        #[async_trait::async_trait]
        impl NotificationDispatcher for DelayedAllFailDispatcher {
            async fn dispatch_3way(&self, _message: &str) -> DispatchOutcome {
                let _ = self.started_tx.send(());
                self.release.notified().await;
                DispatchOutcome::AllFail
            }

            fn push_channels_enabled(&self) -> Option<(bool, bool)> {
                Some((true, true))
            }
        }

        let ledger = Arc::new(Mutex::new(fresh_ledger()));
        let clock = Arc::new(AtomicU64::new(1_000));
        let release = Arc::new(tokio::sync::Notify::new());
        let (started_tx, mut started_rx) = tokio::sync::mpsc::unbounded_channel();
        let watcher = Arc::new(SharedFailsafeWatcher::new_for_test(
            Box::new(DelayedAllFailDispatcher {
                started_tx,
                release: Arc::clone(&release),
            }),
            Box::new(NoopPositionProvider),
            Box::new(NoopExchangeStopSync),
            Box::new(NoopAuditEmitter),
            Box::new(ArcClock(clock)),
            FailsafeConfig::default(),
        ));
        let (senders, mut outcome_rx) = local_feed_senders();

        let task_ledger = Arc::clone(&ledger);
        let task_watcher = Arc::clone(&watcher);
        let report_task = tokio::spawn(async move {
            report_incident_with(
                task_ledger.as_ref(),
                IncidentClass::BybitFailClosed,
                "dispatch in flight".to_string(),
                1_000,
                task_watcher.as_ref(),
                Some(senders),
            )
            .await
        });

        started_rx
            .recv()
            .await
            .expect("dispatch should enter delayed dispatcher");
        assert!(matches!(
            report_resolved_with(ledger.as_ref(), IncidentClass::BybitFailClosed, 1_001, None),
            IncidentPolicyResult::ResolvedNoAction {
                class: IncidentClass::BybitFailClosed
            }
        ));

        release.notify_one();
        let result = report_task.await.expect("report task completed");
        assert!(matches!(
            result,
            IncidentPolicyResult::Dispatched {
                class: IncidentClass::BybitFailClosed,
                mode: IncidentDispatchMode::ArmTimer,
                outcome: DispatchOutcome::AllFail,
                fed_to_watcher: false
            }
        ));
        assert!(outcome_rx.try_recv().is_err());
        assert!(!watcher.state_snapshot().is_armed());
    }

    #[tokio::test]
    async fn report_incident_secret_disabled_downgrades_to_notify_only_without_feed() {
        let ledger = Mutex::new(fresh_ledger());
        let clock = Arc::new(AtomicU64::new(1_000));
        let watcher = watcher_for_test(
            DispatchOutcome::AllFail,
            Some((true, false)),
            Arc::clone(&clock),
        );
        let (senders, mut outcome_rx) = local_feed_senders();

        let result = report_incident_with(
            &ledger,
            IncidentClass::BybitFailClosed,
            "email secret missing".to_string(),
            1_000,
            &watcher,
            Some(senders),
        )
        .await;

        assert!(matches!(
            result,
            IncidentPolicyResult::Dispatched {
                class: IncidentClass::BybitFailClosed,
                mode: IncidentDispatchMode::NotifyOnly,
                outcome: DispatchOutcome::AllFail,
                fed_to_watcher: false
            }
        ));
        assert!(outcome_rx.try_recv().is_err());
        assert!(!watcher.state_snapshot().is_armed());
    }

    #[tokio::test]
    async fn report_incident_notify_only_class_never_feeds_allfail() {
        let ledger = Mutex::new(fresh_ledger());
        let clock = Arc::new(AtomicU64::new(1_000));
        let watcher = watcher_for_test(
            DispatchOutcome::AllFail,
            Some((true, true)),
            Arc::clone(&clock),
        );
        let (senders, mut outcome_rx) = local_feed_senders();

        let result = report_incident_with(
            &ledger,
            IncidentClass::PositionDrift,
            "position drift remains notify-only".to_string(),
            1_000,
            &watcher,
            Some(senders),
        )
        .await;

        assert!(matches!(
            result,
            IncidentPolicyResult::Dispatched {
                class: IncidentClass::PositionDrift,
                mode: IncidentDispatchMode::NotifyOnly,
                outcome: DispatchOutcome::AllFail,
                fed_to_watcher: false
            }
        ));
        assert!(outcome_rx.try_recv().is_err());
        assert!(!watcher.state_snapshot().is_armed());
    }
}

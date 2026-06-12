//! SM halt incident producer for C4 incident policy.
//!
//! This producer observes the runtime HaltSession state already owned by
//! TickPipeline (`halt_kind` + `halt_set_ts_ms`). It intentionally does not
//! inspect passive healthcheck `[69]`, because that selector is no longer the
//! SM halt-stuck check in the current repository.

use crate::halt_audit::HaltKind;
use crate::notification_failsafe::incident_policy::{self, IncidentClass};
use crate::tick_pipeline::{PipelineKind, TickPipeline};

const REPORT_CADENCE_MS: u64 = 5_000;

#[derive(Debug, Default)]
pub(super) struct SmHaltIncidentProducer {
    active_key: Option<(HaltKind, u64)>,
    last_report_at_ms: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum SmHaltIncidentAction {
    None,
    Report(String),
    Resolved,
}

#[derive(Debug, Clone, Copy)]
struct SmHaltObservation {
    kind: Option<HaltKind>,
    halt_set_ts_ms: u64,
    paper_paused: bool,
    session_halted: bool,
    pipeline_kind: PipelineKind,
    daily_loss_ttl_ms: u64,
    now_ms: u64,
}

impl SmHaltObservation {
    fn from_pipeline(pipeline: &TickPipeline, now_ms: u64) -> Self {
        Self {
            kind: pipeline.halt_kind,
            halt_set_ts_ms: pipeline.halt_set_ts_ms,
            paper_paused: pipeline.paper_paused,
            session_halted: pipeline.session_halted,
            pipeline_kind: pipeline.pipeline_kind,
            daily_loss_ttl_ms: pipeline
                .intent_processor
                .risk_config()
                .limits
                .daily_loss_halt_ttl_ms,
            now_ms,
        }
    }

    fn active_key(self) -> Option<(HaltKind, u64)> {
        self.kind.map(|kind| (kind, self.halt_set_ts_ms))
    }

    fn detail(self, source: &str) -> String {
        let kind = self.kind.map(|kind| kind.as_str()).unwrap_or("none");
        let elapsed_ms = if self.halt_set_ts_ms > 0 {
            Some(self.now_ms.saturating_sub(self.halt_set_ts_ms))
        } else {
            None
        };
        let ttl_remaining_ms = match self.kind {
            Some(HaltKind::DailyLoss) if self.daily_loss_ttl_ms > 0 && self.halt_set_ts_ms > 0 => {
                Some(
                    self.daily_loss_ttl_ms
                        .saturating_sub(self.now_ms.saturating_sub(self.halt_set_ts_ms)),
                )
            }
            _ => None,
        };
        format!(
            "source={source} pipeline={} halt_kind={kind} halt_set_ts_ms={} elapsed_ms={} paper_paused={} session_halted={} ttl_remaining_ms={}",
            self.pipeline_kind.db_mode(),
            self.halt_set_ts_ms,
            elapsed_ms
                .map(|v| v.to_string())
                .unwrap_or_else(|| "unknown".to_string()),
            self.paper_paused,
            self.session_halted,
            ttl_remaining_ms
                .map(|v| v.to_string())
                .unwrap_or_else(|| "sticky_or_unknown".to_string()),
        )
    }
}

impl SmHaltIncidentProducer {
    fn observe(&mut self, observation: SmHaltObservation, source: &str) -> SmHaltIncidentAction {
        let Some(active_key) = observation.active_key() else {
            if self.active_key.take().is_some() {
                self.last_report_at_ms = None;
                return SmHaltIncidentAction::Resolved;
            }
            return SmHaltIncidentAction::None;
        };

        if self.active_key != Some(active_key) {
            self.active_key = Some(active_key);
            self.last_report_at_ms = Some(observation.now_ms);
            return SmHaltIncidentAction::Report(observation.detail(source));
        }

        let due = self
            .last_report_at_ms
            .map(|last| observation.now_ms.saturating_sub(last) >= REPORT_CADENCE_MS)
            .unwrap_or(true);
        if !due {
            return SmHaltIncidentAction::None;
        }

        self.last_report_at_ms = Some(observation.now_ms);
        SmHaltIncidentAction::Report(observation.detail(source))
    }
}

pub(super) fn observe_and_dispatch(
    pipeline: &TickPipeline,
    producer: &mut SmHaltIncidentProducer,
    source: &str,
) {
    let now_ms = openclaw_core::now_ms();
    match producer.observe(SmHaltObservation::from_pipeline(pipeline, now_ms), source) {
        SmHaltIncidentAction::Report(detail) => {
            incident_policy::spawn_report_incident(IncidentClass::SmHaltStuck, detail);
        }
        SmHaltIncidentAction::Resolved => {
            let result = incident_policy::report_resolved(IncidentClass::SmHaltStuck);
            tracing::debug!(?result, "sm_halt_stuck incident resolved");
        }
        SmHaltIncidentAction::None => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn observation(kind: Option<HaltKind>, halt_set_ts_ms: u64, now_ms: u64) -> SmHaltObservation {
        SmHaltObservation {
            kind,
            halt_set_ts_ms,
            paper_paused: kind.is_some(),
            session_halted: kind.is_some(),
            pipeline_kind: PipelineKind::Demo,
            daily_loss_ttl_ms: 86_400_000,
            now_ms,
        }
    }

    #[test]
    fn inactive_operator_pause_does_not_report() {
        let mut producer = SmHaltIncidentProducer::default();
        let mut obs = observation(None, 0, 1_000);
        obs.paper_paused = true;

        assert_eq!(producer.observe(obs, "test"), SmHaltIncidentAction::None);
    }

    #[test]
    fn active_halt_reports_then_respects_cadence() {
        let mut producer = SmHaltIncidentProducer::default();

        let first = producer.observe(observation(Some(HaltKind::DailyLoss), 1_000, 2_000), "test");
        assert!(matches!(first, SmHaltIncidentAction::Report(_)));

        assert_eq!(
            producer.observe(observation(Some(HaltKind::DailyLoss), 1_000, 6_999), "test",),
            SmHaltIncidentAction::None
        );

        let due = producer.observe(observation(Some(HaltKind::DailyLoss), 1_000, 7_000), "test");
        assert!(matches!(due, SmHaltIncidentAction::Report(_)));
    }

    #[test]
    fn changed_halt_key_reports_immediately() {
        let mut producer = SmHaltIncidentProducer::default();
        assert!(matches!(
            producer.observe(observation(Some(HaltKind::DailyLoss), 1_000, 2_000), "test"),
            SmHaltIncidentAction::Report(_)
        ));

        let changed = producer.observe(
            observation(Some(HaltKind::SessionDrawdown), 3_000, 3_100),
            "test",
        );
        assert!(matches!(changed, SmHaltIncidentAction::Report(_)));
    }

    #[test]
    fn cleared_halt_resolves_once() {
        let mut producer = SmHaltIncidentProducer::default();
        let _ = producer.observe(observation(Some(HaltKind::DailyLoss), 1_000, 2_000), "test");

        assert_eq!(
            producer.observe(observation(None, 0, 3_000), "test"),
            SmHaltIncidentAction::Resolved
        );
        assert_eq!(
            producer.observe(observation(None, 0, 4_000), "test"),
            SmHaltIncidentAction::None
        );
    }

    #[test]
    fn detail_marks_daily_loss_ttl_remaining() {
        let detail = observation(Some(HaltKind::DailyLoss), 1_000, 2_500).detail("unit");
        assert!(detail.contains("source=unit"));
        assert!(detail.contains("halt_kind=daily_loss"));
        assert!(detail.contains("elapsed_ms=1500"));
        assert!(detail.contains("ttl_remaining_ms=86398500"));
    }
}

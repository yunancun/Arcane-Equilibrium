//! Position drift incident producer.
//!
//! The reconciler already owns drift classification and auto-contraction. This
//! producer only turns unresolved, persistent post-reconcile drift into a C4
//! notify-only incident (`IncidentClass::PositionDrift`).

use std::collections::{HashMap, HashSet};

use openclaw_core::sm::risk_gov::RiskLevel;

use crate::notification_failsafe::incident_policy::{self, IncidentClass};

use super::escalation::{PERSISTENT_DRIFT_CYCLES, STARTUP_GRACE_MS};
use super::DriftVerdict;

const REPORT_CADENCE_MS: u64 = 60_000;
const DETAIL_SAMPLE_LIMIT: usize = 5;

#[derive(Debug, Default)]
pub(super) struct PositionDriftIncidentProducer {
    streak_by_key: HashMap<String, u32>,
    active_signature: Option<String>,
    last_report_at_ms: Option<u64>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
enum PositionDriftIncidentAction {
    None,
    Report(String),
    Resolved,
}

#[derive(Debug)]
struct PersistentDrift {
    key: String,
    kind: &'static str,
    streak: u32,
}

impl PositionDriftIncidentProducer {
    fn observe(
        &mut self,
        drifts: &[(String, DriftVerdict)],
        current_level: RiskLevel,
        startup_ms: u64,
        now_ms: u64,
        engine_label: &str,
        source: &str,
    ) -> PositionDriftIncidentAction {
        if startup_ms > 0 && now_ms.saturating_sub(startup_ms) < STARTUP_GRACE_MS {
            self.clear();
            return PositionDriftIncidentAction::None;
        }

        let actionable: Vec<&(String, DriftVerdict)> = drifts
            .iter()
            .filter(|(_, verdict)| is_actionable(verdict))
            .collect();

        let mut current_keys: HashSet<&str> = HashSet::new();
        for entry in &actionable {
            let (key, _) = *entry;
            current_keys.insert(key.as_str());
            *self.streak_by_key.entry(key.clone()).or_insert(0) += 1;
        }
        self.streak_by_key
            .retain(|key, _| current_keys.contains(key.as_str()));

        let persistent = self.persistent_drifts(&actionable);
        if persistent.is_empty() {
            if self.active_signature.take().is_some() {
                self.last_report_at_ms = None;
                return PositionDriftIncidentAction::Resolved;
            }
            return PositionDriftIncidentAction::None;
        }

        let signature = signature_for(&persistent);
        if self.active_signature.as_deref() != Some(signature.as_str()) {
            self.active_signature = Some(signature);
            self.last_report_at_ms = Some(now_ms);
            return PositionDriftIncidentAction::Report(detail_for(
                source,
                engine_label,
                current_level,
                now_ms,
                drifts.len(),
                &persistent,
            ));
        }

        let due = self
            .last_report_at_ms
            .map(|last| now_ms.saturating_sub(last) >= REPORT_CADENCE_MS)
            .unwrap_or(true);
        if !due {
            return PositionDriftIncidentAction::None;
        }

        self.last_report_at_ms = Some(now_ms);
        PositionDriftIncidentAction::Report(detail_for(
            source,
            engine_label,
            current_level,
            now_ms,
            drifts.len(),
            &persistent,
        ))
    }

    fn persistent_drifts(&self, actionable: &[&(String, DriftVerdict)]) -> Vec<PersistentDrift> {
        let mut out: Vec<PersistentDrift> = actionable
            .iter()
            .filter_map(|entry| {
                let (key, verdict) = *entry;
                let streak = self.streak_by_key.get(key.as_str()).copied().unwrap_or(0);
                (streak >= PERSISTENT_DRIFT_CYCLES).then(|| PersistentDrift {
                    key: key.clone(),
                    kind: verdict.kind_str(),
                    streak,
                })
            })
            .collect();
        out.sort_by(|a, b| a.key.cmp(&b.key).then_with(|| a.kind.cmp(b.kind)));
        out
    }

    fn clear(&mut self) {
        self.streak_by_key.clear();
        self.active_signature = None;
        self.last_report_at_ms = None;
    }
}

pub(super) fn observe_and_dispatch(
    producer: &mut PositionDriftIncidentProducer,
    drifts: &[(String, DriftVerdict)],
    current_level: RiskLevel,
    startup_ms: u64,
    now_ms: u64,
    engine_label: &str,
    source: &str,
) {
    match producer.observe(
        drifts,
        current_level,
        startup_ms,
        now_ms,
        engine_label,
        source,
    ) {
        PositionDriftIncidentAction::Report(detail) => {
            incident_policy::spawn_report_incident(IncidentClass::PositionDrift, detail);
        }
        PositionDriftIncidentAction::Resolved => {
            let result = incident_policy::report_resolved(IncidentClass::PositionDrift);
            tracing::debug!(?result, "position_drift incident resolved");
        }
        PositionDriftIncidentAction::None => {}
    }
}

fn is_actionable(verdict: &DriftVerdict) -> bool {
    matches!(
        verdict,
        DriftVerdict::MajorDrift
            | DriftVerdict::SideFlip
            | DriftVerdict::Orphan
            | DriftVerdict::Ghost
    )
}

fn signature_for(persistent: &[PersistentDrift]) -> String {
    persistent
        .iter()
        .map(|drift| format!("{}:{}", drift.key, drift.kind))
        .collect::<Vec<_>>()
        .join(",")
}

fn detail_for(
    source: &str,
    engine_label: &str,
    current_level: RiskLevel,
    now_ms: u64,
    unresolved_drift_count: usize,
    persistent: &[PersistentDrift],
) -> String {
    let max_streak = persistent
        .iter()
        .map(|drift| drift.streak)
        .max()
        .unwrap_or(0);
    let sample = persistent
        .iter()
        .take(DETAIL_SAMPLE_LIMIT)
        .map(|drift| format!("{}:{}:streak={}", drift.key, drift.kind, drift.streak))
        .collect::<Vec<_>>()
        .join(",");

    format!(
        "source={source} engine={engine_label} risk_level={:?} now_ms={} unresolved_drift_count={} persistent_drift_count={} max_streak={} threshold_cycles={} sample={}",
        current_level,
        now_ms,
        unresolved_drift_count,
        persistent.len(),
        max_streak,
        PERSISTENT_DRIFT_CYCLES,
        sample
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn major(key: &str) -> Vec<(String, DriftVerdict)> {
        vec![(key.to_string(), DriftVerdict::MajorDrift)]
    }

    #[test]
    fn minor_drift_is_ignored() {
        let mut producer = PositionDriftIncidentProducer::default();
        let drifts = vec![("BTCUSDT|Buy".to_string(), DriftVerdict::MinorDrift)];

        for now in [1_000, 31_000, 61_000] {
            assert_eq!(
                producer.observe(&drifts, RiskLevel::Normal, 0, now, "demo", "test"),
                PositionDriftIncidentAction::None
            );
        }
    }

    #[test]
    fn persistent_major_drift_reports_on_third_cycle() {
        let mut producer = PositionDriftIncidentProducer::default();
        let drifts = major("BTCUSDT|Buy");

        assert_eq!(
            producer.observe(&drifts, RiskLevel::Normal, 0, 1_000, "demo", "test"),
            PositionDriftIncidentAction::None
        );
        assert_eq!(
            producer.observe(&drifts, RiskLevel::Cautious, 0, 31_000, "demo", "test"),
            PositionDriftIncidentAction::None
        );

        let action = producer.observe(&drifts, RiskLevel::Defensive, 0, 61_000, "demo", "test");
        let PositionDriftIncidentAction::Report(detail) = action else {
            panic!("third unresolved drift cycle must report");
        };
        assert!(!detail.contains("class="));
        assert!(detail.contains("source=test"));
        assert!(detail.contains("engine=demo"));
        assert!(detail.contains("risk_level=Defensive"));
        assert!(detail.contains("persistent_drift_count=1"));
        assert!(detail.contains("threshold_cycles=3"));
        assert!(detail.contains("BTCUSDT|Buy:major_drift:streak=3"));
    }

    #[test]
    fn startup_grace_does_not_accumulate_streak() {
        let mut producer = PositionDriftIncidentProducer::default();
        let drifts = major("BTCUSDT|Buy");
        let startup_ms = 1_000_000;

        for offset in [30_000, 60_000, 90_000] {
            assert_eq!(
                producer.observe(
                    &drifts,
                    RiskLevel::Normal,
                    startup_ms,
                    startup_ms + offset,
                    "demo",
                    "test",
                ),
                PositionDriftIncidentAction::None
            );
        }

        assert_eq!(
            producer.observe(
                &drifts,
                RiskLevel::Normal,
                startup_ms,
                startup_ms + STARTUP_GRACE_MS,
                "demo",
                "test",
            ),
            PositionDriftIncidentAction::None
        );
    }

    #[test]
    fn same_active_signature_respects_cadence() {
        let mut producer = PositionDriftIncidentProducer::default();
        let drifts = major("BTCUSDT|Buy");

        let _ = producer.observe(&drifts, RiskLevel::Normal, 0, 1_000, "demo", "test");
        let _ = producer.observe(&drifts, RiskLevel::Normal, 0, 31_000, "demo", "test");
        assert!(matches!(
            producer.observe(&drifts, RiskLevel::Normal, 0, 61_000, "demo", "test"),
            PositionDriftIncidentAction::Report(_)
        ));
        assert_eq!(
            producer.observe(&drifts, RiskLevel::Normal, 0, 90_000, "demo", "test"),
            PositionDriftIncidentAction::None
        );
        assert!(matches!(
            producer.observe(&drifts, RiskLevel::Normal, 0, 121_000, "demo", "test"),
            PositionDriftIncidentAction::Report(_)
        ));
    }

    #[test]
    fn changed_persistent_signature_reports_immediately() {
        let mut producer = PositionDriftIncidentProducer::default();
        let drift_a = major("BTCUSDT|Buy");
        let drift_ab = vec![
            ("BTCUSDT|Buy".to_string(), DriftVerdict::MajorDrift),
            ("ETHUSDT|Sell".to_string(), DriftVerdict::Ghost),
        ];

        let _ = producer.observe(&drift_a, RiskLevel::Normal, 0, 1_000, "demo", "test");
        let _ = producer.observe(&drift_a, RiskLevel::Normal, 0, 31_000, "demo", "test");
        assert!(matches!(
            producer.observe(&drift_a, RiskLevel::Normal, 0, 61_000, "demo", "test"),
            PositionDriftIncidentAction::Report(_)
        ));

        let _ = producer.observe(&drift_ab, RiskLevel::Normal, 0, 91_000, "demo", "test");
        let _ = producer.observe(&drift_ab, RiskLevel::Normal, 0, 111_000, "demo", "test");
        let action = producer.observe(&drift_ab, RiskLevel::Normal, 0, 116_000, "demo", "test");
        assert!(
            matches!(action, PositionDriftIncidentAction::Report(_)),
            "new persistent key must report even inside cadence"
        );
    }

    #[test]
    fn resolved_reports_once_when_persistent_drift_clears() {
        let mut producer = PositionDriftIncidentProducer::default();
        let drifts = major("BTCUSDT|Buy");

        let _ = producer.observe(&drifts, RiskLevel::Normal, 0, 1_000, "demo", "test");
        let _ = producer.observe(&drifts, RiskLevel::Normal, 0, 31_000, "demo", "test");
        let _ = producer.observe(&drifts, RiskLevel::Normal, 0, 61_000, "demo", "test");

        assert_eq!(
            producer.observe(&[], RiskLevel::Normal, 0, 91_000, "demo", "test"),
            PositionDriftIncidentAction::Resolved
        );
        assert_eq!(
            producer.observe(&[], RiskLevel::Normal, 0, 121_000, "demo", "test"),
            PositionDriftIncidentAction::None
        );
    }
}

//! Cost-gate demo-learning lane JSONL writer.
//!
//! This module keeps durable learning evidence off the tick hot path. Producers
//! send a normalized `RejectEvent` through a bounded channel; the writer task
//! loads the current plan and ledger, evaluates the fail-closed admission policy,
//! and appends a `probe_admission_decision` row. It does not submit orders.

use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use chrono::{DateTime, Utc};
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

use crate::demo_learning_lane::{
    evaluate_probe_admission, AdmissionConfig, DemoLearningLanePlan, LedgerRecord, RejectEvent,
};
use crate::demo_learning_lane_ledger::{
    attempt_id_for_reject_event, build_admission_ledger_record, build_capture_error_ledger_record,
    AdmissionLedgerRecord,
};

const CHANNEL_CAPACITY: usize = 4096;
const BUF_WRITER_CAPACITY: usize = 64 * 1024;
const FLUSH_INTERVAL_MS: u64 = 200;
const WARN_THROTTLE_MS: u64 = 1000;

#[derive(Debug, Clone)]
struct WriterMsg {
    event: RejectEvent,
    risk_state: String,
    now_ms: u64,
}

#[derive(Clone)]
pub struct DemoLearningLaneWriterHandle {
    tx: Option<mpsc::Sender<WriterMsg>>,
    total_dropped: Arc<AtomicU64>,
    last_warn_ms: Arc<AtomicU64>,
}

impl DemoLearningLaneWriterHandle {
    pub fn disabled() -> Self {
        Self {
            tx: None,
            total_dropped: Arc::new(AtomicU64::new(0)),
            last_warn_ms: Arc::new(AtomicU64::new(0)),
        }
    }

    pub fn is_enabled(&self) -> bool {
        self.tx.is_some()
    }

    pub fn record_reject_event(&self, event: RejectEvent, risk_state: &str, now_ms: u64) {
        if let Some(ref tx) = self.tx {
            let msg = WriterMsg {
                event,
                risk_state: risk_state.trim().to_string(),
                now_ms,
            };
            match tx.try_send(msg) {
                Ok(()) => {}
                Err(mpsc::error::TrySendError::Full(_)) => {
                    let total = self.total_dropped.fetch_add(1, Ordering::Relaxed) + 1;
                    if self.should_emit_warn() {
                        warn!(
                            total_dropped = total,
                            "demo-learning lane writer channel full; reject event dropped / demo-learning lane 寫入通道滿，reject event 已丟棄"
                        );
                    }
                }
                Err(mpsc::error::TrySendError::Closed(_)) => {}
            }
        }
    }

    fn should_emit_warn(&self) -> bool {
        let now_ms = epoch_ms();
        let last = self.last_warn_ms.load(Ordering::Relaxed);
        if now_ms.saturating_sub(last) < WARN_THROTTLE_MS {
            return false;
        }
        self.last_warn_ms
            .compare_exchange(last, now_ms, Ordering::Relaxed, Ordering::Relaxed)
            .is_ok()
    }
}

pub fn spawn(data_dir: PathBuf, cancel: CancellationToken) -> DemoLearningLaneWriterHandle {
    let enabled = std::env::var("OPENCLAW_DEMO_LEARNING_LANE_WRITER")
        .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
        .unwrap_or(false);
    if !enabled {
        return DemoLearningLaneWriterHandle::disabled();
    }

    let base_dir = data_dir.join("cost_gate_learning_lane");
    let plan_path = std::env::var("OPENCLAW_DEMO_LEARNING_LANE_PLAN")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base_dir.join("demo_learning_lane_plan_latest.json"));
    let ledger_path = std::env::var("OPENCLAW_DEMO_LEARNING_LANE_LEDGER")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base_dir.join("probe_ledger.jsonl"));

    let (tx, rx) = mpsc::channel(CHANNEL_CAPACITY);
    info!(
        plan_path = %plan_path.display(),
        ledger_path = %ledger_path.display(),
        channel_capacity = CHANNEL_CAPACITY,
        "demo-learning lane writer started / demo-learning lane 寫入器已啟動"
    );
    tokio::spawn(run_writer(rx, plan_path, ledger_path, cancel));
    DemoLearningLaneWriterHandle {
        tx: Some(tx),
        total_dropped: Arc::new(AtomicU64::new(0)),
        last_warn_ms: Arc::new(AtomicU64::new(0)),
    }
}

async fn run_writer(
    mut rx: mpsc::Receiver<WriterMsg>,
    plan_path: PathBuf,
    ledger_path: PathBuf,
    cancel: CancellationToken,
) {
    let (mut bw, _) = match open_writer(&ledger_path) {
        Ok(writer) => writer,
        Err(e) => {
            warn!(
                error = %e,
                ledger_path = %ledger_path.display(),
                "demo-learning lane writer failed to open ledger; exiting / demo-learning lane ledger 開檔失敗，任務退出"
            );
            return;
        }
    };
    let mut flush_timer =
        tokio::time::interval(std::time::Duration::from_millis(FLUSH_INTERVAL_MS));
    flush_timer.tick().await;

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                let _ = bw.flush();
            }
            msg = rx.recv() => {
                let Some(msg) = msg else { break };
                match build_runtime_admission_record(
                    &plan_path,
                    &ledger_path,
                    &msg.event,
                    &msg.risk_state,
                    msg.now_ms,
                    Utc::now(),
                ) {
                    Ok(Some(record)) => {
                        match record.to_json_string() {
                            Ok(json) => {
                                if let Err(e) = bw.write_all(json.as_bytes()).and_then(|_| bw.write_all(b"\n")) {
                                    warn!(
                                        error = %e,
                                        ledger_path = %ledger_path.display(),
                                        "demo-learning lane ledger write failed / demo-learning lane ledger 寫入失敗"
                                    );
                                } else if let Err(e) = bw.flush() {
                                    warn!(
                                        error = %e,
                                        ledger_path = %ledger_path.display(),
                                        "demo-learning lane ledger flush failed / demo-learning lane ledger flush 失敗"
                                    );
                                }
                            }
                            Err(e) => {
                                warn!(error = %e, "demo-learning lane ledger serialize failed / demo-learning lane ledger 序列化失敗");
                            }
                        }
                    }
                    Ok(None) => {}
                    Err(e) => {
                        warn!(error = %e, "demo-learning lane admission evaluation failed; writing capture-error row / demo-learning lane admission 評估失敗，寫入 capture-error row");
                        let record = build_capture_error_ledger_record(
                            &msg.event,
                            Utc::now(),
                            &msg.risk_state,
                            &e,
                        );
                        match record.to_json_string() {
                            Ok(json) => {
                                if let Err(write_err) = bw.write_all(json.as_bytes()).and_then(|_| bw.write_all(b"\n")) {
                                    warn!(
                                        error = %write_err,
                                        ledger_path = %ledger_path.display(),
                                        "demo-learning lane capture-error write failed / demo-learning lane capture-error 寫入失敗"
                                    );
                                } else if let Err(flush_err) = bw.flush() {
                                    warn!(
                                        error = %flush_err,
                                        ledger_path = %ledger_path.display(),
                                        "demo-learning lane capture-error flush failed / demo-learning lane capture-error flush 失敗"
                                    );
                                }
                            }
                            Err(ser_err) => {
                                warn!(error = %ser_err, "demo-learning lane capture-error serialize failed / demo-learning lane capture-error 序列化失敗");
                            }
                        }
                    }
                }
            }
        }
    }
    let _ = bw.flush();
    info!("demo-learning lane writer stopped / demo-learning lane 寫入器已停止");
}

pub(crate) fn build_runtime_admission_record(
    plan_path: &Path,
    ledger_path: &Path,
    event: &RejectEvent,
    risk_state: &str,
    now_ms: u64,
    generated_at_utc: DateTime<Utc>,
) -> Result<Option<AdmissionLedgerRecord>, String> {
    let ledger_rows = read_ledger_rows(ledger_path)?;
    let attempt_id = attempt_id_for_reject_event(event);
    if ledger_rows
        .iter()
        .any(|row| row.attempt_id.as_deref() == Some(attempt_id.as_str()))
    {
        return Ok(None);
    }
    let plan_json = std::fs::read_to_string(plan_path)
        .map_err(|err| format!("read plan {} failed: {err}", plan_path.display()))?;
    let plan = DemoLearningLanePlan::from_json_str(&plan_json)
        .map_err(|err| format!("parse plan {} failed: {err}", plan_path.display()))?;
    let decision = evaluate_probe_admission(
        &plan,
        event,
        &ledger_rows,
        now_ms,
        &AdmissionConfig::default(),
        false,
        risk_state,
    );
    Ok(Some(build_admission_ledger_record(
        &decision,
        event,
        generated_at_utc,
    )))
}

fn read_ledger_rows(path: &Path) -> Result<Vec<LedgerRecord>, String> {
    match std::fs::read_to_string(path) {
        Ok(content) => LedgerRecord::from_jsonl_str(&content),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(Vec::new()),
        Err(err) => Err(format!("read ledger {} failed: {err}", path.display())),
    }
}

fn open_writer(path: &Path) -> std::io::Result<(BufWriter<File>, u64)> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let file = OpenOptions::new().create(true).append(true).open(path)?;
    let size = file.metadata().map(|m| m.len()).unwrap_or(0);
    Ok((BufWriter::with_capacity(BUF_WRITER_CAPACITY, file), size))
}

fn epoch_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::demo_learning_lane::ELIGIBLE_REJECT_REASON_CODE;
    use crate::demo_learning_lane_ledger::{
        CAPTURE_ERROR_DECISION, CAPTURE_ERROR_LEDGER_RECORD_TYPE,
    };
    use tempfile::TempDir;

    fn plan_json(generated_at: &str) -> String {
        format!(
            r#"{{
  "schema_version": "cost_gate_demo_learning_lane_plan_v1",
  "generated_at_utc": "{generated_at}",
  "status": "READY_FOR_DEMO_LEARNING_PROBE",
  "gate_status": "OPERATOR_REVIEW",
  "main_cost_gate_adjustment": "NONE",
  "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
  "order_authority": "NOT_GRANTED",
  "selected_probe_candidate_count": 1,
  "probe_candidates": [
    {{
      "side_cell_key": "ma_crossover|ETHUSDT|Sell",
      "strategy_name": "ma_crossover",
      "symbol": "ETHUSDT",
      "side": "Sell",
      "reject_reason_code": "cost_gate_js_demo_negative_edge",
      "probe_proposal": {{
        "mode": "demo_only_learning_probe",
        "max_probe_orders": 2,
        "cooldown_minutes": 30,
        "requires_runtime_policy_adapter": true,
        "requires_probe_attempt_logging": true,
        "requires_probe_outcome_logging": true
      }},
      "guardrails": {{
        "main_cost_gate_adjustment": "NONE",
        "may_bypass_main_live_gate": false,
        "demo_only": true,
        "paper_not_promotion_evidence": true,
        "notional_or_qty_not_granted_by_artifact": true
      }}
    }}
  ]
}}"#
        )
    }

    fn reject_event() -> RejectEvent {
        RejectEvent {
            strategy_name: "ma_crossover".to_string(),
            symbol: "ETHUSDT".to_string(),
            side: "Sell".to_string(),
            reject_reason_code: ELIGIBLE_REJECT_REASON_CODE.to_string(),
            engine_mode: "live_demo".to_string(),
            ts_ms: 1_782_041_000_000,
            context_id: Some("ctx-live_demo-ETHUSDT-1782041000000".to_string()),
            signal_id: Some("sig-live_demo-ma_crossover-ETHUSDT-1782041000000".to_string()),
        }
    }

    #[test]
    fn builds_order_authority_not_granted_record_without_order_permission() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("plan.json");
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(&plan_path, plan_json("2026-06-21T10:49:45Z")).unwrap();

        let record = build_runtime_admission_record(
            &plan_path,
            &ledger_path,
            &reject_event(),
            "NORMAL",
            1_782_041_001_000,
            DateTime::parse_from_rfc3339("2026-06-21T10:50:00Z")
                .unwrap()
                .with_timezone(&Utc),
        )
        .unwrap()
        .expect("first event should build a ledger row");

        assert_eq!(record.record_type, "probe_admission_decision");
        assert_eq!(record.decision, "ORDER_AUTHORITY_NOT_GRANTED");
        assert!(!record.allowed_to_submit_order);
        assert_eq!(record.side_cell_key, "ma_crossover|ETHUSDT|Sell");
        assert_eq!(record.attempt_id, "ctx-live_demo-ETHUSDT-1782041000000");
    }

    #[test]
    fn duplicate_attempt_id_is_not_appended_again() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("plan.json");
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(&plan_path, plan_json("2026-06-21T10:49:45Z")).unwrap();
        std::fs::write(
            &ledger_path,
            r#"{"record_type":"probe_admission_decision","attempt_id":"ctx-live_demo-ETHUSDT-1782041000000","side_cell_key":"ma_crossover|ETHUSDT|Sell"}"#,
        )
        .unwrap();

        let record = build_runtime_admission_record(
            &plan_path,
            &ledger_path,
            &reject_event(),
            "NORMAL",
            1_782_041_001_000,
            Utc::now(),
        )
        .unwrap();

        assert!(record.is_none());
    }

    #[test]
    fn disabled_handle_does_not_accept_events() {
        let handle = DemoLearningLaneWriterHandle::disabled();
        assert!(!handle.is_enabled());
        handle.record_reject_event(reject_event(), "NORMAL", 1_782_041_001_000);
    }

    #[tokio::test]
    async fn writer_task_appends_jsonl_record() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("plan.json");
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(&plan_path, plan_json("2026-06-21T10:49:45Z")).unwrap();

        let (tx, rx) = mpsc::channel(4);
        let cancel = CancellationToken::new();
        let handle = tokio::spawn(run_writer(
            rx,
            plan_path,
            ledger_path.clone(),
            cancel.clone(),
        ));

        tx.send(WriterMsg {
            event: reject_event(),
            risk_state: "NORMAL".to_string(),
            now_ms: 1_782_041_001_000,
        })
        .await
        .unwrap();
        drop(tx);
        handle.await.unwrap();

        let content = std::fs::read_to_string(&ledger_path).unwrap();
        let rows = LedgerRecord::from_jsonl_str(&content).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(
            rows[0].attempt_id.as_deref(),
            Some("ctx-live_demo-ETHUSDT-1782041000000")
        );
        assert_eq!(
            rows[0].decision.as_deref(),
            Some("ORDER_AUTHORITY_NOT_GRANTED")
        );
        assert_eq!(rows[0].allowed_to_submit_order, Some(false));
    }

    #[tokio::test]
    async fn writer_task_appends_capture_error_when_plan_missing() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("missing-plan.json");
        let ledger_path = tmp.path().join("probe_ledger.jsonl");

        let (tx, rx) = mpsc::channel(4);
        let cancel = CancellationToken::new();
        let handle = tokio::spawn(run_writer(
            rx,
            plan_path,
            ledger_path.clone(),
            cancel.clone(),
        ));

        tx.send(WriterMsg {
            event: reject_event(),
            risk_state: "NORMAL".to_string(),
            now_ms: 1_782_041_001_000,
        })
        .await
        .unwrap();
        drop(tx);
        handle.await.unwrap();

        let content = std::fs::read_to_string(&ledger_path).unwrap();
        let rows = LedgerRecord::from_jsonl_str(&content).unwrap();
        assert_eq!(rows.len(), 1);
        assert_eq!(
            rows[0].record_type.as_deref(),
            Some(CAPTURE_ERROR_LEDGER_RECORD_TYPE)
        );
        assert_eq!(rows[0].decision.as_deref(), Some(CAPTURE_ERROR_DECISION));
        assert_eq!(
            rows[0].attempt_id.as_deref(),
            Some("ctx-live_demo-ETHUSDT-1782041000000")
        );
        assert_eq!(rows[0].allowed_to_submit_order, Some(false));
        assert_eq!(
            rows[0].reason.as_deref(),
            Some("runtime_admission_evaluation_failed")
        );
    }
}

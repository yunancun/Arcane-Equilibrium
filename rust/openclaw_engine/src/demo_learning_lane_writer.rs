//! Cost-gate demo-learning lane JSONL writer.
//!
//! This module keeps durable learning evidence off the tick hot path. Producers
//! send a normalized `RejectEvent` through a bounded channel; the writer task
//! loads the current plan and ledger, evaluates the fail-closed admission policy,
//! and appends a `probe_admission_decision` row. Active order helpers are
//! separate review seams and remain inactive unless a caller supplies an
//! admitted candidate-matched envelope.

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

use crate::bounded_probe_active_order::{
    candidate_matched_bounded_probe_order, ActiveBoundedProbeOrderDecision,
    ActiveBoundedProbeOrderDraft, ActiveBoundedProbeOrderRequest,
};
use crate::bounded_probe_near_touch::BoundedProbePlacementDecision;
use crate::demo_learning_lane::{
    evaluate_probe_admission, AdmissionConfig, DemoLearningLanePlan, LedgerRecord, RejectEvent,
};
use crate::demo_learning_lane_ledger::{
    attempt_id_for_reject_event, build_admission_ledger_record_with_placement,
    build_capture_error_ledger_record, AdmissionLedgerRecord,
};
use crate::tick_pipeline::OrderDispatchRequest;

const CHANNEL_CAPACITY: usize = 4096;
const BUF_WRITER_CAPACITY: usize = 64 * 1024;
const FLUSH_INTERVAL_MS: u64 = 200;
const WARN_THROTTLE_MS: u64 = 1000;
const ENABLE_WRITER_ENV: &str = "OPENCLAW_DEMO_LEARNING_LANE_WRITER";
const PLAN_PATH_ENV: &str = "OPENCLAW_DEMO_LEARNING_LANE_PLAN";
const LEDGER_PATH_ENV: &str = "OPENCLAW_DEMO_LEARNING_LANE_LEDGER";
const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str = "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";

// pub(crate):dispatch-edge withhold 的 feed 恢復釘子測試需檢視 writer channel
// 收到的 RejectEvent(見 step_4_5_dispatch_tests.rs);僅 crate 內測試消費。
#[derive(Debug, Clone)]
pub(crate) struct WriterMsg {
    pub(crate) event: RejectEvent,
    pub(crate) risk_state: String,
    pub(crate) now_ms: u64,
    pub(crate) placement_decision: Option<BoundedProbePlacementDecision>,
    pub(crate) active_order_request: Option<ActiveBoundedProbeOrderRequest>,
    pub(crate) order_dispatch_tx: Option<tokio::sync::mpsc::UnboundedSender<OrderDispatchRequest>>,
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
        self.record_reject_event_with_placement(event, risk_state, now_ms, None);
    }

    pub fn record_reject_event_with_placement(
        &self,
        event: RejectEvent,
        risk_state: &str,
        now_ms: u64,
        placement_decision: Option<BoundedProbePlacementDecision>,
    ) {
        self.record_reject_event_with_placement_and_active_request(
            event,
            risk_state,
            now_ms,
            placement_decision,
            None,
        );
    }

    pub fn record_reject_event_with_placement_and_active_request(
        &self,
        event: RejectEvent,
        risk_state: &str,
        now_ms: u64,
        placement_decision: Option<BoundedProbePlacementDecision>,
        active_order_request: Option<ActiveBoundedProbeOrderRequest>,
    ) {
        self.record_reject_event_with_placement_active_request_and_order_dispatch(
            event,
            risk_state,
            now_ms,
            placement_decision,
            active_order_request,
            None,
        );
    }

    pub fn record_reject_event_with_placement_active_request_and_order_dispatch(
        &self,
        event: RejectEvent,
        risk_state: &str,
        now_ms: u64,
        placement_decision: Option<BoundedProbePlacementDecision>,
        active_order_request: Option<ActiveBoundedProbeOrderRequest>,
        order_dispatch_tx: Option<tokio::sync::mpsc::UnboundedSender<OrderDispatchRequest>>,
    ) {
        if let Some(ref tx) = self.tx {
            let msg = WriterMsg {
                event,
                risk_state: risk_state.trim().to_string(),
                now_ms,
                placement_decision,
                active_order_request,
                order_dispatch_tx,
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

    /// 測試用 handle:繞過 spawn 的 env gate 與 writer task,把 channel 接收端
    /// 交給測試直接檢視(feed 恢復釘子:cost_gate reject → channel 收到事件)。
    #[cfg(test)]
    pub(crate) fn handle_for_test() -> (Self, mpsc::Receiver<WriterMsg>) {
        let (tx, rx) = mpsc::channel(CHANNEL_CAPACITY);
        (
            Self {
                tx: Some(tx),
                total_dropped: Arc::new(AtomicU64::new(0)),
                last_warn_ms: Arc::new(AtomicU64::new(0)),
            },
            rx,
        )
    }
}

pub fn spawn(data_dir: PathBuf, cancel: CancellationToken) -> DemoLearningLaneWriterHandle {
    let enabled = std::env::var(ENABLE_WRITER_ENV)
        .map(|value| value == "1" || value.eq_ignore_ascii_case("true"))
        .unwrap_or(false);
    if !enabled {
        return DemoLearningLaneWriterHandle::disabled();
    }

    let plan_path = demo_learning_lane_plan_path(&data_dir);
    let ledger_path = env_path_or_default(
        LEDGER_PATH_ENV,
        data_dir
            .join("cost_gate_learning_lane")
            .join("probe_ledger.jsonl"),
    );

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

fn env_path_or_default(name: &str, default_path: PathBuf) -> PathBuf {
    path_override_or_default(std::env::var(name).ok(), default_path)
}

/// plan 路徑的唯一解析入口(PLAN_PATH_ENV override + data_dir 默認)。
/// 為什麼共用:soak 圍欄(demo_learning_lane_soak_gate)與 writer admission
/// 必須讀同一份 plan;各自解析(默認值/override 任一漂移)= guard 與 admission
/// 判準漂移,即安全洞(2026-07-02 設計 §1.2)。
pub(crate) fn demo_learning_lane_plan_path(data_dir: &Path) -> PathBuf {
    env_path_or_default(
        PLAN_PATH_ENV,
        data_dir
            .join("cost_gate_learning_lane")
            .join("demo_learning_lane_plan_latest.json"),
    )
}

/// env 級解析:OPENCLAW_DATA_DIR 默認 "/tmp/openclaw" 鏡像 main.rs 既有慣例
/// (writer spawn 的 data_dir 亦由 main.rs 以同一默認值構造,兩端同源)。
pub(crate) fn demo_learning_lane_plan_path_from_env() -> PathBuf {
    let data_dir = PathBuf::from(
        std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into()),
    );
    demo_learning_lane_plan_path(&data_dir)
}

fn path_override_or_default(value: Option<String>, default_path: PathBuf) -> PathBuf {
    match value {
        Some(value) if !value.trim().is_empty() => PathBuf::from(value.trim()),
        _ => default_path,
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
    // O(n²) 修復(2026-07-02 設計 §1.3):啟動讀一次後維護 in-memory cache;
    // append 檔案同步 push(parse-back,與重啟後 read_ledger_rows 讀到的內容
    // 等價),消除每事件全量重讀(feed 恢復 12.9 萬筆/日下的自爆點)。
    // 啟動讀失敗 fail-closed 退出(比照上方 open_writer 失敗先例):壞 ledger
    // 下繼續跑會讓 dedup / 預算判定失真,寧可停寫並大聲告警。
    //
    // F1(E2 2026-07-03 審查):「writer 唯一寫者」設計前提不成立——cron
    // `cost_gate_learning_lane_cron.sh` 與 Python `runtime_adapter.py` 以同一
    // OPENCLAW_DATA_DIR 對同一 probe_ledger.jsonl append `probe_outcome` /
    // `side_cell_disabled` rows,而 admission 靠這些行做 auto/manual disable
    // (demo_learning_lane.rs summarize_side_cell_runtime_state)。純 in-memory
    // cache 會使兩條 disable 路徑對運行中 engine 全盲直到重啟。
    // 修法 = stat 級失效:緩存 last-known (len, mtime),每事件 fs::metadata
    // 比對;任何外部變化(增長/截斷/替換/刪除)→ 先 flush 自寫緩衝再全量
    // 重讀。外部 append 低頻(cron 每小時級),攤還仍 O(1),設計「消除每事件
    // 全量重讀」目的保留。
    let mut ledger_rows = match read_ledger_rows(&ledger_path) {
        Ok(rows) => rows,
        Err(e) => {
            warn!(
                error = %e,
                ledger_path = %ledger_path.display(),
                "demo-learning lane writer failed to load ledger cache; exiting / demo-learning lane ledger cache 載入失敗，任務退出"
            );
            return;
        }
    };
    // stat 快照:None = 檔案不存在(或 stat 暫不可得,下一事件重試判定)。
    let mut ledger_stat = stat_ledger(&ledger_path).ok().flatten();
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
                let WriterMsg {
                    event,
                    risk_state,
                    now_ms,
                    placement_decision,
                    active_order_request,
                    order_dispatch_tx,
                } = msg;
                let active_order_dispatch_channel_available = order_dispatch_tx.is_some();
                // F1:先做 stat 級外部變化偵測;refresh 失敗走既有 capture-error
                // 分支(鏡像修前「每事件讀檔失敗 → capture-error row」語義)。
                // L-R2:記住 refresh 成敗——失敗時 capture-error 分支不得推進
                // stat 快照,保留舊 stat 使下一事件必重試重讀。
                let refresh_result = refresh_ledger_cache_if_externally_changed(
                    &mut bw,
                    &ledger_path,
                    &mut ledger_rows,
                    &mut ledger_stat,
                );
                let refresh_ok = refresh_result.is_ok();
                let admission_build = refresh_result.and_then(|()| {
                    build_runtime_admission_result(
                        &plan_path,
                        &ledger_rows,
                        &event,
                        &risk_state,
                        now_ms,
                        Utc::now(),
                        placement_decision.as_ref(),
                        active_order_request,
                        active_order_dispatch_channel_available,
                        None,
                    )
                });
                match admission_build {
                    Ok(Some(result)) => {
                        match result.record.to_json_string() {
                            Ok(json) => {
                                if let Err(e) = bw.write_all(json.as_bytes()).and_then(|_| bw.write_all(b"\n")) {
                                    warn!(
                                        error = %e,
                                        ledger_path = %ledger_path.display(),
                                        "demo-learning lane ledger write failed / demo-learning lane ledger 寫入失敗"
                                    );
                                } else {
                                    // 寫檔成功即同步 push cache(flush 失敗也 push:
                                    // cache 只會更保守地 dedup,方向安全)。
                                    push_ledger_cache(&mut ledger_rows, &json);
                                    if let Err(e) = bw.flush() {
                                        warn!(
                                            error = %e,
                                            ledger_path = %ledger_path.display(),
                                            "demo-learning lane ledger flush failed / demo-learning lane ledger flush 失敗"
                                        );
                                    } else if let Some(draft) = result.active_order_draft {
                                        if let Some(ref tx) = order_dispatch_tx {
                                            match dispatch_active_bounded_probe_order_draft(tx, draft) {
                                                Ok(true) => {
                                                    info!(
                                                        ledger_path = %ledger_path.display(),
                                                        "bounded Demo probe active order dispatched after admission ledger flush / bounded Demo probe active order 已在 admission ledger flush 後派發"
                                                    );
                                                }
                                                Ok(false) => {
                                                    warn!(
                                                        ledger_path = %ledger_path.display(),
                                                        "bounded Demo probe active order draft failed final notional cap check before dispatch / bounded Demo probe active order draft 在派發前未通過最終 notional cap 檢查"
                                                    );
                                                }
                                                Err(e) => {
                                                    warn!(
                                                        error = %e,
                                                        ledger_path = %ledger_path.display(),
                                                        "bounded Demo probe order dispatch channel send failed after admission ledger flush / bounded Demo probe order admission ledger flush 後派發 channel send 失敗"
                                                    );
                                                }
                                            }
                                        }
                                    }
                                    // F1+L-R1:自寫落盤後以「預期檔長」推進快照
                                    // (直接 stat-as-snapshot 會吞掉窗口內的外部
                                    // append → 盲窗;預期長不符即保留舊快照,
                                    // 下一事件必重讀)。+1 = b"\n"。
                                    advance_ledger_stat_after_self_write(
                                        &ledger_path,
                                        &mut ledger_stat,
                                        json.len() as u64 + 1,
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
                            &event,
                            Utc::now(),
                            &risk_state,
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
                                } else {
                                    // capture-error row 也入 cache:修前語義下它同樣
                                    // 參與 attempt_id dedup(同 attempt 不重寫)。
                                    push_ledger_cache(&mut ledger_rows, &json);
                                    if let Err(flush_err) = bw.flush() {
                                        warn!(
                                            error = %flush_err,
                                            ledger_path = %ledger_path.display(),
                                            "demo-learning lane capture-error flush failed / demo-learning lane capture-error flush 失敗"
                                        );
                                    }
                                    // L-R2:僅 refresh 成功時推進快照;refresh 失敗
                                    // 保留舊 stat → 下一事件 stat 必不匹配 → 必重試
                                    // 重讀(否則 cache 對外部行的盲態被快照固化)。
                                    if refresh_ok {
                                        advance_ledger_stat_after_self_write(
                                            &ledger_path,
                                            &mut ledger_stat,
                                            json.len() as u64 + 1,
                                        );
                                    }
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

#[cfg(test)]
pub(crate) fn build_runtime_admission_record(
    plan_path: &Path,
    ledger_path: &Path,
    event: &RejectEvent,
    risk_state: &str,
    now_ms: u64,
    generated_at_utc: DateTime<Utc>,
    placement_decision: Option<&BoundedProbePlacementDecision>,
    active_order_request: Option<ActiveBoundedProbeOrderRequest>,
) -> Result<Option<AdmissionLedgerRecord>, String> {
    // 測試 helper 保留舊 path 簽名:讀一次檔再委派,與 run_writer 啟動載入等價。
    let ledger_rows = read_ledger_rows(ledger_path)?;
    build_runtime_admission_result(
        plan_path,
        &ledger_rows,
        event,
        risk_state,
        now_ms,
        generated_at_utc,
        placement_decision,
        active_order_request,
        false,
        None,
    )
    .map(|result| result.map(|result| result.record))
}

#[derive(Debug, Clone)]
struct RuntimeAdmissionBuildResult {
    record: AdmissionLedgerRecord,
    active_order_draft: Option<ActiveBoundedProbeOrderDraft>,
}

#[allow(clippy::too_many_arguments)]
fn build_runtime_admission_result(
    plan_path: &Path,
    // O(n²) 修復(§1.3):改收 caller 持有的 in-memory rows(writer task 啟動
    // 載入一次後維護),不再每事件全量重讀 ledger 檔。
    ledger_rows: &[LedgerRecord],
    event: &RejectEvent,
    risk_state: &str,
    now_ms: u64,
    generated_at_utc: DateTime<Utc>,
    placement_decision: Option<&BoundedProbePlacementDecision>,
    active_order_request: Option<ActiveBoundedProbeOrderRequest>,
    active_order_dispatch_channel_available: bool,
    bounded_probe_adapter_enabled_override: Option<bool>,
) -> Result<Option<RuntimeAdmissionBuildResult>, String> {
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
    let bounded_probe_adapter_env_enabled =
        bounded_probe_adapter_enabled_override.unwrap_or_else(|| {
            std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED)
                .map(|value| bounded_probe_adapter_enabled_from_value(&value))
                .unwrap_or(false)
        });
    let bounded_probe_adapter_enabled = bounded_probe_adapter_env_enabled
        && active_order_request.is_some()
        && active_order_dispatch_channel_available;
    let decision = evaluate_probe_admission(
        &plan,
        event,
        ledger_rows,
        now_ms,
        &AdmissionConfig::default(),
        bounded_probe_adapter_enabled,
        risk_state,
    );
    let mut active_order_draft = None;
    if let (Some(order_request), Some(placement_decision)) =
        (active_order_request, placement_decision.cloned())
    {
        let active_order_decision = submit_candidate_matched_bounded_probe_order(
            &plan,
            ledger_rows,
            event.clone(),
            placement_decision,
            risk_state,
            now_ms,
            bounded_probe_adapter_enabled,
            order_request,
        );
        active_order_draft = active_bounded_probe_order_submission(active_order_decision);
    }
    Ok(Some(RuntimeAdmissionBuildResult {
        record: build_admission_ledger_record_with_placement(
            &decision,
            event,
            generated_at_utc,
            placement_decision,
        ),
        active_order_draft,
    }))
}

pub(crate) fn bounded_probe_adapter_enabled_from_value(value: &str) -> bool {
    let normalized = value.trim();
    normalized == "1" || normalized.eq_ignore_ascii_case("true")
}

pub(crate) fn submit_candidate_matched_bounded_probe_order(
    plan: &DemoLearningLanePlan,
    ledger_rows: &[LedgerRecord],
    event: RejectEvent,
    placement_decision: BoundedProbePlacementDecision,
    risk_state: &str,
    now_ms: u64,
    bounded_probe_adapter_enabled: bool,
    order_request: ActiveBoundedProbeOrderRequest,
) -> ActiveBoundedProbeOrderDecision {
    let admission_decision = evaluate_probe_admission(
        plan,
        &event,
        ledger_rows,
        now_ms,
        &AdmissionConfig::default(),
        bounded_probe_adapter_enabled,
        risk_state,
    );
    let request = ActiveBoundedProbeOrderRequest {
        reject_event: event,
        admission_decision,
        placement_decision,
        ..order_request
    };
    candidate_matched_bounded_probe_order(request)
}

pub(crate) fn active_bounded_probe_order_submission(
    decision: ActiveBoundedProbeOrderDecision,
) -> Option<ActiveBoundedProbeOrderDraft> {
    match decision {
        ActiveBoundedProbeOrderDecision::Submit(draft) => Some(draft),
        ActiveBoundedProbeOrderDecision::Skip(_) => None,
    }
}

pub(crate) fn dispatch_active_bounded_probe_order_draft(
    tx: &tokio::sync::mpsc::UnboundedSender<OrderDispatchRequest>,
    draft: ActiveBoundedProbeOrderDraft,
) -> Result<bool, tokio::sync::mpsc::error::SendError<OrderDispatchRequest>> {
    if !crate::bounded_probe_active_order::active_bounded_probe_effective_notional_within_cap(
        draft.qty,
        draft.limit_price,
        draft.max_demo_notional_usdt_per_order,
    ) {
        return Ok(false);
    }
    let order_link_id = draft.lineage.order_link_id.clone();
    let context_id = draft.lineage.context_id.clone();
    let signal_id = draft.lineage.signal_id.clone();
    tx.send(OrderDispatchRequest {
        symbol: draft.symbol,
        is_long: draft.is_long,
        qty: draft.qty,
        price: draft.reference_price,
        strategy: draft.strategy,
        paper_fill_ts: draft.paper_fill_ts,
        is_close: false,
        order_link_id,
        decision_lease_id: Some(draft.decision_lease_id),
        is_primary: true,
        stop_loss: None,
        take_profit: None,
        context_id,
        order_type: "limit".to_string(),
        limit_price: Some(draft.limit_price),
        time_in_force: Some(draft.time_in_force),
        maker_timeout_ms: Some(draft.maker_timeout_ms),
        close_maker_audit: None,
        reference_price: Some(draft.reference_price),
        reference_ts_ms: Some(draft.paper_fill_ts),
        reference_source: Some(
            crate::bounded_probe_active_order::ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE.to_string(),
        ),
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
        intent_id: Some(signal_id),
        reprice_count: 0,
    })?;
    Ok(true)
}

fn read_ledger_rows(path: &Path) -> Result<Vec<LedgerRecord>, String> {
    match std::fs::read_to_string(path) {
        Ok(content) => LedgerRecord::from_jsonl_str(&content),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(Vec::new()),
        Err(err) => Err(format!("read ledger {} failed: {err}", path.display())),
    }
}

/// ledger 檔 stat 快照:len + mtime。None 語義由呼叫端定義為「檔案不存在」。
/// 為什麼 len+mtime 雙比對:len 抓 append/截斷(即使 mtime 粒度粗),mtime 抓
/// 同長度改寫;同秒內同長度替換屬病態案例,接受(E2 F1 修法方向即 stat 級)。
#[derive(Debug, Clone, PartialEq, Eq)]
struct LedgerStat {
    len: u64,
    mtime: Option<std::time::SystemTime>,
}

fn stat_ledger(path: &Path) -> Result<Option<LedgerStat>, String> {
    match std::fs::metadata(path) {
        Ok(meta) => Ok(Some(LedgerStat {
            len: meta.len(),
            mtime: meta.modified().ok(),
        })),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(err) => Err(format!("stat ledger {} failed: {err}", path.display())),
    }
}

/// F1(E2 2026-07-03):偵測外部寫者(cron reject_materializer / outcome_refresh、
/// Python runtime_adapter)對 ledger 的變化,命中即全量重讀刷新 in-memory cache。
///
/// 為什麼重讀前先 flush:本 task 可能有已 push cache 但尚在 BufWriter 緩衝的
/// 自寫行;不先落盤,重讀會把它們從 cache 丟失 → dedup 回退。
/// 為什麼全量重讀而非增量:同時覆蓋 append / 截斷 / 替換 / 刪除四種外部變化,
/// 語義與修前「每事件讀檔」一致;外部變化低頻,攤還 O(1)。
/// 失敗語義:stat / 重讀錯誤回 Err,呼叫端走 capture-error 分支(鏡像修前
/// 每事件讀檔失敗行為);cache 與快照維持原狀,下一事件自動重試。
fn refresh_ledger_cache_if_externally_changed(
    bw: &mut BufWriter<File>,
    ledger_path: &Path,
    ledger_rows: &mut Vec<LedgerRecord>,
    ledger_stat: &mut Option<LedgerStat>,
) -> Result<(), String> {
    let current = stat_ledger(ledger_path)?;
    if current == *ledger_stat {
        return Ok(());
    }
    // L-R3(E2 re-review):flush 失敗要可見,不得靜默吞錯。觸發頻率天然受限
    // (僅外部變化時執行,cron 每小時級),無需額外節流狀態。flush 失敗不中斷
    // 重讀:讀到的檔案缺自寫緩衝行時,快照取讀前 stat,下一事件必重試。
    if let Err(e) = bw.flush() {
        warn!(
            error = %e,
            ledger_path = %ledger_path.display(),
            "demo-learning lane ledger flush before cache reread failed / ledger cache 重讀前 flush 失敗"
        );
    }
    // L-R1(refresh 側 TOCTOU 消除):快照取「讀之前」的 stat。讀與 stat 之間
    // 若有外部 append,該行已被讀進 cache 而快照長度偏小 → 下一事件至多過觸發
    // 一次重讀(方向安全);反向(讀後才 stat)會把讀不到的外部行 bytes 吞進
    // 快照,形成盲窗。
    let pre_read = stat_ledger(ledger_path)?;
    *ledger_rows = read_ledger_rows(ledger_path)?;
    *ledger_stat = pre_read;
    tracing::debug!(
        ledger_path = %ledger_path.display(),
        rows = ledger_rows.len(),
        "demo-learning lane ledger cache refreshed after external change / 偵測到外部 ledger 變化，cache 已全量重讀"
    );
    Ok(())
}

/// L-R1(自寫側 TOCTOU 消除):自寫落盤後推進 stat 快照。
///
/// 為什麼不能直接拿「當下 stat」當快照:flush 與 stat 之間若有外部 append,
/// 該外部行的 bytes 會被吞進快照,直到下一次外部變化前全盲。改為以
/// 「寫前快照長度 + 自寫 bytes」推算預期檔長,實際 stat 僅在 len 恰等於預期
/// 時採納;不等(外部行擠進窗口 / flush 未全落盤)則保留舊快照,下一事件
/// stat 必不匹配 → 觸發全量重讀,外部行必可見。
/// 失效方向:只會多一次重讀(過觸發),永不產生盲窗。
fn advance_ledger_stat_after_self_write(
    ledger_path: &Path,
    ledger_stat: &mut Option<LedgerStat>,
    written_bytes: u64,
) {
    let expected_len = ledger_stat.as_ref().map_or(0, |s| s.len) + written_bytes;
    match stat_ledger(ledger_path) {
        Ok(Some(actual)) if actual.len == expected_len => {
            *ledger_stat = Some(actual);
        }
        // 不採納(len 不符或 stat 失敗):保留舊快照,下一事件必重讀。
        _ => {}
    }
}

/// 把剛寫入檔案的 JSONL 行 parse 回 `LedgerRecord` 後 push 進 in-memory cache。
/// 為什麼 parse-back 而非手工構造:保證 cache 內容與「重啟後 read_ledger_rows
/// 讀到的同一行」逐位等價,dedup / cooldown / 預算判定語義與修前一致。
fn push_ledger_cache(rows: &mut Vec<LedgerRecord>, json_line: &str) {
    match serde_json::from_str::<LedgerRecord>(json_line) {
        Ok(row) => rows.push(row),
        Err(e) => warn!(
            error = %e,
            "demo-learning lane ledger cache parse-back failed; row not cached / ledger cache parse-back 失敗，該行未入緩存"
        ),
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
    use crate::bounded_probe_active_order::{
        bounded_probe_order_link_id_for_candidate, ActiveBoundedProbeRiskLimits,
    };
    use crate::bounded_probe_near_touch::{
        BoundedProbeAttemptPlacement, BoundedProbePlacementDecision,
    };
    use crate::demo_learning_lane::ELIGIBLE_REJECT_REASON_CODE;
    use crate::demo_learning_lane_ledger::{
        CAPTURE_ERROR_DECISION, CAPTURE_ERROR_LEDGER_RECORD_TYPE,
    };
    use tempfile::TempDir;

    const GUI_RISK_CAP_USDT: f64 = 955.24342626;

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

    fn authorized_plan_json(generated_at: &str) -> String {
        format!(
            r#"{{
  "schema_version": "cost_gate_demo_learning_lane_plan_v1",
  "generated_at_utc": "{generated_at}",
  "status": "READY_FOR_DEMO_LEARNING_PROBE",
  "gate_status": "OPERATOR_REVIEW",
  "main_cost_gate_adjustment": "NONE",
  "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
  "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
  "operator_authorization": {{
    "schema_version": "bounded_demo_probe_operator_authorization_v1",
    "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
    "authorization_id": "auth-demo-eth-sell-001",
    "operator_id": "operator-test",
    "side_cell_key": "ma_crossover|ETHUSDT|Sell",
    "expires_at_utc": "2026-06-21T11:30:00Z",
    "authority_path_readiness_status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
    "main_cost_gate_adjustment": "NONE",
    "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
    "max_authorized_probe_orders": 2,
    "probe_authority_granted": true,
    "order_authority_granted": true,
    "promotion_evidence": false
  }},
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
    fn bounded_probe_adapter_gate_accepts_only_explicit_true_values() {
        assert!(bounded_probe_adapter_enabled_from_value("1"));
        assert!(bounded_probe_adapter_enabled_from_value("true"));
        assert!(bounded_probe_adapter_enabled_from_value(" TRUE "));
        assert!(!bounded_probe_adapter_enabled_from_value(""));
        assert!(!bounded_probe_adapter_enabled_from_value("0"));
        assert!(!bounded_probe_adapter_enabled_from_value("yes"));
        assert!(!bounded_probe_adapter_enabled_from_value("enabled"));
        assert!(bounded_probe_adapter_enabled_from_value("true") && true);
        assert!(bounded_probe_adapter_enabled_from_value("1") && true);
        assert!(!(bounded_probe_adapter_enabled_from_value("true") && false));
        assert!(!Option::<&str>::None
            .map(bounded_probe_adapter_enabled_from_value)
            .unwrap_or(false));
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
            None,
            None,
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
            None,
            None,
        )
        .unwrap();

        assert!(record.is_none());
    }

    #[test]
    fn admission_record_embeds_bounded_probe_placement_preview_without_order() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("plan.json");
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(&plan_path, plan_json("2026-06-21T10:49:45Z")).unwrap();
        let placement = BoundedProbePlacementDecision::Submit(BoundedProbeAttemptPlacement {
            record_type: "bounded_probe_attempt",
            side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
            limit_price: 3_499.9,
            touch_gap_bps: 12.5,
            reference_price: 3_500.0,
            bbo_age_ms: 0,
        });

        let record = build_runtime_admission_record(
            &plan_path,
            &ledger_path,
            &reject_event(),
            "NORMAL",
            1_782_041_001_000,
            DateTime::parse_from_rfc3339("2026-06-21T10:50:00Z")
                .unwrap()
                .with_timezone(&Utc),
            Some(&placement),
            None,
        )
        .unwrap()
        .expect("first event should build a ledger row");

        assert_eq!(record.decision, "ORDER_AUTHORITY_NOT_GRANTED");
        assert!(!record.allowed_to_submit_order);
        let placement = record
            .bounded_probe_placement
            .as_ref()
            .expect("placement preview should be embedded");
        assert_eq!(
            placement["record_type"].as_str(),
            Some("bounded_probe_attempt")
        );
        assert_eq!(
            placement["placement_decision"].as_str(),
            Some("would_submit_if_authorized")
        );
        assert_eq!(
            placement["order_submission_performed"].as_bool(),
            Some(false)
        );
    }

    #[test]
    fn runtime_record_accepts_active_order_request_without_granting_order_authority() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("plan.json");
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(&plan_path, plan_json("2026-06-21T10:49:45Z")).unwrap();
        let event = reject_event();
        let placement = BoundedProbePlacementDecision::Submit(BoundedProbeAttemptPlacement {
            record_type: "bounded_probe_attempt",
            side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
            limit_price: 3_499.9,
            touch_gap_bps: 12.5,
            reference_price: 3_500.0,
            bbo_age_ms: 0,
        });
        let plan = DemoLearningLanePlan::from_json_str(&plan_json("2026-06-21T10:49:45Z")).unwrap();
        let admission_decision = evaluate_probe_admission(
            &plan,
            &event,
            &[],
            1_782_041_001_000,
            &AdmissionConfig::default(),
            false,
            "NORMAL",
        );
        let order_link_id = bounded_probe_order_link_id_for_candidate(
            &event.engine_mode,
            event.ts_ms,
            1,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        )
        .unwrap();
        let order_request = ActiveBoundedProbeOrderRequest {
            reject_event: event.clone(),
            admission_decision,
            placement_decision: placement.clone(),
            qty: 0.001,
            order_link_id,
            decision_lease_id: Some("lease-demo-1".to_string()),
            risk_state: "NORMAL".to_string(),
            limits: ActiveBoundedProbeRiskLimits {
                max_demo_notional_usdt_per_order: GUI_RISK_CAP_USDT,
                ..ActiveBoundedProbeRiskLimits::default()
            },
        };

        let record = build_runtime_admission_record(
            &plan_path,
            &ledger_path,
            &event,
            "NORMAL",
            1_782_041_001_000,
            DateTime::parse_from_rfc3339("2026-06-21T10:50:00Z")
                .unwrap()
                .with_timezone(&Utc),
            Some(&placement),
            Some(order_request),
        )
        .unwrap()
        .expect("first event should build a ledger row");

        assert_eq!(record.record_type, "probe_admission_decision");
        assert_eq!(record.decision, "ORDER_AUTHORITY_NOT_GRANTED");
        assert!(!record.allowed_to_submit_order);
        let placement = record
            .bounded_probe_placement
            .as_ref()
            .expect("placement preview should still be embedded");
        assert_eq!(
            placement["order_submission_performed"].as_bool(),
            Some(false)
        );
    }

    #[test]
    fn writer_active_order_helper_requires_runtime_adapter_enabled() {
        let plan =
            DemoLearningLanePlan::from_json_str(&authorized_plan_json("2026-06-21T10:49:45Z"))
                .unwrap();
        let event = reject_event();
        let placement = BoundedProbePlacementDecision::Submit(BoundedProbeAttemptPlacement {
            record_type: "bounded_probe_attempt",
            side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
            limit_price: 3_499.9,
            touch_gap_bps: 12.5,
            reference_price: 3_500.0,
            bbo_age_ms: 0,
        });
        let admission_decision = evaluate_probe_admission(
            &plan,
            &event,
            &[],
            1_782_041_001_000,
            &AdmissionConfig::default(),
            true,
            "NORMAL",
        );
        let order_link_id = bounded_probe_order_link_id_for_candidate(
            &event.engine_mode,
            event.ts_ms,
            1,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        )
        .unwrap();
        let order_request = ActiveBoundedProbeOrderRequest {
            reject_event: event.clone(),
            admission_decision,
            placement_decision: placement.clone(),
            qty: 0.001,
            order_link_id: order_link_id.clone(),
            decision_lease_id: Some("lease-demo-1".to_string()),
            risk_state: "NORMAL".to_string(),
            limits: ActiveBoundedProbeRiskLimits {
                max_demo_notional_usdt_per_order: GUI_RISK_CAP_USDT,
                ..ActiveBoundedProbeRiskLimits::default()
            },
        };

        let blocked = submit_candidate_matched_bounded_probe_order(
            &plan,
            &[],
            event.clone(),
            placement.clone(),
            "NORMAL",
            1_782_041_001_000,
            false,
            order_request.clone(),
        );
        assert!(active_bounded_probe_order_submission(blocked).is_none());

        let allowed = submit_candidate_matched_bounded_probe_order(
            &plan,
            &[],
            event,
            placement,
            "NORMAL",
            1_782_041_001_000,
            true,
            order_request,
        );
        let draft = active_bounded_probe_order_submission(allowed)
            .expect("enabled adapter and admitted plan should build a draft");
        assert_eq!(draft.lineage.side_cell_key, "ma_crossover|ETHUSDT|Sell");
        assert_eq!(draft.lineage.order_link_id, order_link_id);
        assert_eq!(draft.lineage.bounded_probe_attempt, "bounded_probe_attempt");
    }

    #[test]
    fn runtime_admission_dispatch_requires_channel_and_emits_candidate_matched_request() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("plan.json");
        std::fs::write(&plan_path, authorized_plan_json("2026-06-21T10:49:45Z")).unwrap();
        let event = reject_event();
        let placement = BoundedProbePlacementDecision::Submit(BoundedProbeAttemptPlacement {
            record_type: "bounded_probe_attempt",
            side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
            limit_price: 3_499.9,
            touch_gap_bps: 12.5,
            reference_price: 3_500.0,
            bbo_age_ms: 0,
        });
        let plan =
            DemoLearningLanePlan::from_json_str(&authorized_plan_json("2026-06-21T10:49:45Z"))
                .unwrap();
        let admission_decision = evaluate_probe_admission(
            &plan,
            &event,
            &[],
            1_782_041_001_000,
            &AdmissionConfig::default(),
            true,
            "NORMAL",
        );
        let order_link_id = bounded_probe_order_link_id_for_candidate(
            &event.engine_mode,
            event.ts_ms,
            1,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        )
        .unwrap();
        let order_request = ActiveBoundedProbeOrderRequest {
            reject_event: event.clone(),
            admission_decision,
            placement_decision: placement.clone(),
            qty: 0.001,
            order_link_id: order_link_id.clone(),
            decision_lease_id: Some("lease-demo-1".to_string()),
            risk_state: "NORMAL".to_string(),
            limits: ActiveBoundedProbeRiskLimits {
                max_demo_notional_usdt_per_order: GUI_RISK_CAP_USDT,
                ..ActiveBoundedProbeRiskLimits::default()
            },
        };

        let without_channel = build_runtime_admission_result(
            &plan_path,
            &[],
            &event,
            "NORMAL",
            1_782_041_001_000,
            DateTime::parse_from_rfc3339("2026-06-21T10:50:00Z")
                .unwrap()
                .with_timezone(&Utc),
            Some(&placement),
            Some(order_request.clone()),
            false,
            Some(true),
        )
        .unwrap()
        .expect("authorized plan should still write an adapter-disabled row");
        assert_eq!(without_channel.record.decision, "ADAPTER_DISABLED");
        assert!(!without_channel.record.allowed_to_submit_order);
        assert!(without_channel.active_order_draft.is_none());

        let with_channel = build_runtime_admission_result(
            &plan_path,
            &[],
            &event,
            "NORMAL",
            1_782_041_001_000,
            DateTime::parse_from_rfc3339("2026-06-21T10:50:00Z")
                .unwrap()
                .with_timezone(&Utc),
            Some(&placement),
            Some(order_request),
            true,
            Some(true),
        )
        .unwrap()
        .expect("authorized plan and dispatch channel should build an admitted row");
        assert_eq!(with_channel.record.decision, "ADMIT_DEMO_LEARNING_PROBE");
        assert!(with_channel.record.allowed_to_submit_order);
        let draft = with_channel
            .active_order_draft
            .expect("admitted bounded probe should produce active order draft");
        assert_eq!(draft.lineage.order_link_id, order_link_id);

        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
        assert!(dispatch_active_bounded_probe_order_draft(&tx, draft)
            .expect("dispatch channel should accept admitted draft"));
        let req = rx
            .try_recv()
            .expect("candidate-matched OrderDispatchRequest should be sent");
        assert_eq!(req.symbol, "ETHUSDT");
        assert!(!req.is_long);
        assert_eq!(req.order_link_id, order_link_id);
        assert_eq!(req.decision_lease_id.as_deref(), Some("lease-demo-1"));
        assert_eq!(req.context_id, "ctx-live_demo-ETHUSDT-1782041000000");
        assert_eq!(
            req.intent_id.as_deref(),
            Some("sig-live_demo-ma_crossover-ETHUSDT-1782041000000")
        );
        assert_eq!(req.order_type, "limit");
        assert_eq!(req.limit_price, Some(3_499.9));
        assert_eq!(
            req.time_in_force,
            Some(crate::order_manager::TimeInForce::PostOnly)
        );
        assert_eq!(
            req.maker_timeout_ms,
            Some(crate::bounded_probe_active_order::DEFAULT_ACTIVE_BOUNDED_PROBE_MAKER_TIMEOUT_MS)
        );
        assert_eq!(req.reference_price, Some(3_500.0));
        assert_eq!(
            req.reference_source.as_deref(),
            Some(crate::bounded_probe_active_order::ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE)
        );
        assert!(rx.try_recv().is_err());
    }

    #[test]
    fn disabled_handle_does_not_accept_events() {
        let handle = DemoLearningLaneWriterHandle::disabled();
        assert!(!handle.is_enabled());
        handle.record_reject_event(reject_event(), "NORMAL", 1_782_041_001_000);
    }

    #[test]
    fn blank_path_overrides_fall_back_to_default_lane_paths() {
        let default_path =
            PathBuf::from("/tmp/openclaw/cost_gate_learning_lane/probe_ledger.jsonl");
        assert_eq!(
            path_override_or_default(None, default_path.clone()),
            default_path
        );
        assert_eq!(
            path_override_or_default(Some("   ".to_string()), default_path.clone()),
            default_path
        );
        assert_eq!(
            path_override_or_default(
                Some(" /tmp/custom_probe_ledger.jsonl ".to_string()),
                default_path,
            ),
            PathBuf::from("/tmp/custom_probe_ledger.jsonl")
        );
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
            placement_decision: None,
            active_order_request: None,
            order_dispatch_tx: None,
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
            placement_decision: None,
            active_order_request: None,
            order_dispatch_tx: None,
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

    fn writer_msg(event: RejectEvent) -> WriterMsg {
        WriterMsg {
            event,
            risk_state: "NORMAL".to_string(),
            now_ms: 1_782_041_001_000,
            placement_decision: None,
            active_order_request: None,
            order_dispatch_tx: None,
        }
    }

    /// O(n²) 修復等價性(§1.3):同 run 內同 attempt_id 重複事件只落一行
    /// (修前語義 = 每事件全量重讀檔案後 dedup;修後 = in-memory cache dedup)。
    #[tokio::test]
    async fn ledger_cache_dedups_same_attempt_within_run() {
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

        tx.send(writer_msg(reject_event())).await.unwrap();
        tx.send(writer_msg(reject_event())).await.unwrap();
        drop(tx);
        handle.await.unwrap();

        let content = std::fs::read_to_string(&ledger_path).unwrap();
        let rows = LedgerRecord::from_jsonl_str(&content).unwrap();
        assert_eq!(rows.len(), 1, "同 attempt_id 第二筆必被 cache dedup");
    }

    /// O(n²) 修復等價性:啟動載入使既有 ledger row 仍參與 dedup(與修前
    /// 「每事件讀檔看到舊行」一致)。
    #[tokio::test]
    async fn ledger_cache_dedups_against_preexisting_rows() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("plan.json");
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(&plan_path, plan_json("2026-06-21T10:49:45Z")).unwrap();
        std::fs::write(
            &ledger_path,
            r#"{"record_type":"probe_admission_decision","attempt_id":"ctx-live_demo-ETHUSDT-1782041000000","side_cell_key":"ma_crossover|ETHUSDT|Sell"}"#,
        )
        .unwrap();

        let (tx, rx) = mpsc::channel(4);
        let cancel = CancellationToken::new();
        let handle = tokio::spawn(run_writer(
            rx,
            plan_path,
            ledger_path.clone(),
            cancel.clone(),
        ));

        tx.send(writer_msg(reject_event())).await.unwrap();
        drop(tx);
        handle.await.unwrap();

        let content = std::fs::read_to_string(&ledger_path).unwrap();
        let rows = LedgerRecord::from_jsonl_str(&content).unwrap();
        assert_eq!(rows.len(), 1, "既有行必經啟動載入參與 dedup,不得重複 append");
    }

    /// O(n²) 修復等價性:capture-error row(plan 缺檔)同樣入 cache 參與 dedup
    /// (修前語義:第二筆事件讀檔看到 capture-error 行後即 dedup)。
    #[tokio::test]
    async fn ledger_cache_dedups_capture_error_rows() {
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

        tx.send(writer_msg(reject_event())).await.unwrap();
        tx.send(writer_msg(reject_event())).await.unwrap();
        drop(tx);
        handle.await.unwrap();

        let content = std::fs::read_to_string(&ledger_path).unwrap();
        let rows = LedgerRecord::from_jsonl_str(&content).unwrap();
        assert_eq!(rows.len(), 1, "同 attempt 的 capture-error 只落一行");
        assert_eq!(
            rows[0].record_type.as_deref(),
            Some(CAPTURE_ERROR_LEDGER_RECORD_TYPE)
        );
    }

    /// 路徑解析共用函數:override env 缺席時落 data_dir 默認(soak 圍欄與
    /// writer spawn 同源,杜絕雙路徑漂移)。
    /// F4(E2 2026-07-03):持 test_env_lock save/remove/restore,斷言無條件
    /// 執行——修前 if-包裹在外部已設 PLAN_PATH_ENV 時靜默降級為空測。
    #[test]
    fn plan_path_resolution_defaults_under_data_dir() {
        let _guard = crate::test_env_lock::guard();
        let saved = std::env::var(PLAN_PATH_ENV).ok();
        std::env::remove_var(PLAN_PATH_ENV);
        let data_dir = PathBuf::from("/tmp/openclaw-test-data");
        let resolved = demo_learning_lane_plan_path(&data_dir);
        match saved {
            Some(v) => std::env::set_var(PLAN_PATH_ENV, v),
            None => std::env::remove_var(PLAN_PATH_ENV),
        }
        assert_eq!(
            resolved,
            data_dir
                .join("cost_gate_learning_lane")
                .join("demo_learning_lane_plan_latest.json")
        );
    }

    /// RES-8 golden vector:override env 的 trim/空串語義正本(Python
    /// runtime_adapter._default_plan_path 必逐位鏡像本表)。空白/空串回退默認,
    /// 非空值 trim 後直用。與 test_plan_path_parity_matrix.py 的期望對齊。
    #[test]
    fn plan_path_override_trim_and_empty_fallback_golden_vectors() {
        let _guard = crate::test_env_lock::guard();
        let saved = std::env::var(PLAN_PATH_ENV).ok();
        let data_dir = PathBuf::from("/tmp/openclaw-test-data");
        let default_path = data_dir
            .join("cost_gate_learning_lane")
            .join("demo_learning_lane_plan_latest.json");

        // (env_value, expected)：None=移除 env。
        let cases: [(Option<&str>, PathBuf); 5] = [
            (None, default_path.clone()),
            (Some(""), default_path.clone()),
            (Some("   "), default_path.clone()),
            (Some("/custom/plan.json"), PathBuf::from("/custom/plan.json")),
            (Some("  /custom/plan.json  "), PathBuf::from("/custom/plan.json")),
        ];
        for (env_value, expected) in cases {
            match env_value {
                Some(v) => std::env::set_var(PLAN_PATH_ENV, v),
                None => std::env::remove_var(PLAN_PATH_ENV),
            }
            assert_eq!(
                demo_learning_lane_plan_path(&data_dir),
                expected,
                "env={env_value:?}"
            );
        }
        match saved {
            Some(v) => std::env::set_var(PLAN_PATH_ENV, v),
            None => std::env::remove_var(PLAN_PATH_ENV),
        }
    }

    /// L-R1 釘子:「自寫落盤與快照推進之間」外部 append(TOCTOU 窗口)→ 快照
    /// 不得吞掉外部 bytes,下一次 refresh 必看見外部行。修前語義(自寫後直接
    /// stat-as-snapshot)會把外部行 bytes 收進快照 → refresh 判無變化 → 本測必紅。
    #[test]
    fn self_write_snapshot_does_not_swallow_racing_external_append() {
        let tmp = TempDir::new().unwrap();
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(
            &ledger_path,
            "{\"record_type\":\"probe_admission_decision\",\"attempt_id\":\"a1\"}\n",
        )
        .unwrap();
        let mut ledger_stat = stat_ledger(&ledger_path).unwrap();
        let mut ledger_rows = read_ledger_rows(&ledger_path).unwrap();

        // 重現窗口結局:自寫行與外部行都已落盤,但快照推進只知道自寫 bytes。
        let self_row = r#"{"record_type":"probe_admission_decision","attempt_id":"a2"}"#;
        let external_row = r#"{"record_type":"side_cell_disabled","side_cell_key":"ma_crossover|ETHUSDT|Sell","disable_reason":"manual_disable"}"#;
        {
            use std::io::Write as _;
            let mut f = OpenOptions::new().append(true).open(&ledger_path).unwrap();
            writeln!(f, "{self_row}").unwrap();
            writeln!(f, "{external_row}").unwrap();
        }
        push_ledger_cache(&mut ledger_rows, self_row);
        advance_ledger_stat_after_self_write(
            &ledger_path,
            &mut ledger_stat,
            self_row.len() as u64 + 1,
        );

        // 實際 len = 預期 + 外部 bytes → 快照必不採納 → refresh 必觸發重讀。
        let (mut bw, _) = open_writer(&ledger_path).unwrap();
        refresh_ledger_cache_if_externally_changed(
            &mut bw,
            &ledger_path,
            &mut ledger_rows,
            &mut ledger_stat,
        )
        .unwrap();
        assert!(
            ledger_rows
                .iter()
                .any(|r| r.record_type.as_deref() == Some("side_cell_disabled")),
            "窗口內外部 append 的 disable row 必於下一次 refresh 可見(L-R1)"
        );
    }

    /// L-R1 對照組:無外部競態時快照正常採納,下一事件不觸發無謂重讀
    /// (O(1) 攤還保留)。以 cache 專屬標記行偵測重讀:若 refresh 誤觸發,
    /// 標記會被檔案內容覆蓋而消失。
    #[test]
    fn self_write_snapshot_adopts_without_race_and_avoids_spurious_reread() {
        let tmp = TempDir::new().unwrap();
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(
            &ledger_path,
            "{\"record_type\":\"probe_admission_decision\",\"attempt_id\":\"a1\"}\n",
        )
        .unwrap();
        let mut ledger_stat = stat_ledger(&ledger_path).unwrap();
        let mut ledger_rows = read_ledger_rows(&ledger_path).unwrap();

        let self_row = r#"{"record_type":"probe_admission_decision","attempt_id":"a2"}"#;
        {
            use std::io::Write as _;
            let mut f = OpenOptions::new().append(true).open(&ledger_path).unwrap();
            writeln!(f, "{self_row}").unwrap();
        }
        push_ledger_cache(&mut ledger_rows, self_row);
        advance_ledger_stat_after_self_write(
            &ledger_path,
            &mut ledger_stat,
            self_row.len() as u64 + 1,
        );

        // cache 專屬標記(不在檔案裡):重讀會讓它消失。
        push_ledger_cache(
            &mut ledger_rows,
            r#"{"record_type":"probe_admission_decision","attempt_id":"cache-marker"}"#,
        );
        let (mut bw, _) = open_writer(&ledger_path).unwrap();
        refresh_ledger_cache_if_externally_changed(
            &mut bw,
            &ledger_path,
            &mut ledger_rows,
            &mut ledger_stat,
        )
        .unwrap();
        assert!(
            ledger_rows
                .iter()
                .any(|r| r.attempt_id.as_deref() == Some("cache-marker")),
            "無外部變化時 refresh 必為 no-op(快照已採納,不得無謂重讀)"
        );
    }

    async fn wait_for_ledger_rows(path: &Path, want: usize) {
        for _ in 0..500u32 {
            if let Ok(content) = std::fs::read_to_string(path) {
                if content.lines().filter(|l| !l.trim().is_empty()).count() >= want {
                    return;
                }
            }
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;
        }
        panic!("ledger did not reach {want} rows within timeout");
    }

    /// F1 釘子(E2 2026-07-03):外部寫者(Python runtime_adapter / cron)append
    /// 的 `side_cell_disabled` row 必須在**同一 run 內**對下一事件的 admission
    /// 可見(manual disable 即時生效,不等 engine 重啟)。純 in-memory cache
    /// 版本(F1 修前)此測試必紅(row B 落 ADAPTER_DISABLED 而非
    /// SIDE_CELL_DISABLED)。
    #[tokio::test]
    async fn ledger_cache_sees_external_side_cell_disable_without_restart() {
        let tmp = TempDir::new().unwrap();
        let plan_path = tmp.path().join("plan.json");
        let ledger_path = tmp.path().join("probe_ledger.jsonl");
        std::fs::write(&plan_path, authorized_plan_json("2026-06-21T10:49:45Z")).unwrap();

        let (tx, rx) = mpsc::channel(4);
        let cancel = CancellationToken::new();
        let handle = tokio::spawn(run_writer(
            rx,
            plan_path,
            ledger_path.clone(),
            cancel.clone(),
        ));

        // 事件 A:先落第一行並等待落盤,確保外部 append 排在其後。
        tx.send(writer_msg(reject_event())).await.unwrap();
        wait_for_ledger_rows(&ledger_path, 1).await;

        // 模擬外部寫者(runtime_adapter.py manual disable row 形狀)。
        {
            use std::io::Write as _;
            let mut f = OpenOptions::new().append(true).open(&ledger_path).unwrap();
            writeln!(
                f,
                r#"{{"record_type":"side_cell_disabled","side_cell_key":"ma_crossover|ETHUSDT|Sell","disable_reason":"manual_disable"}}"#
            )
            .unwrap();
        }

        // 事件 B:同 cell、不同 attempt_id。admission 必須看到外部 disable。
        let mut event_b = reject_event();
        event_b.ts_ms += 1_000;
        event_b.context_id = Some("ctx-live_demo-ETHUSDT-1782041001000".to_string());
        event_b.signal_id =
            Some("sig-live_demo-ma_crossover-ETHUSDT-1782041001000".to_string());
        tx.send(writer_msg(event_b)).await.unwrap();
        drop(tx);
        handle.await.unwrap();

        let content = std::fs::read_to_string(&ledger_path).unwrap();
        let rows = LedgerRecord::from_jsonl_str(&content).unwrap();
        assert_eq!(
            rows.len(),
            3,
            "A admission + 外部 disable + B admission 共 3 行,got {rows:?}"
        );
        let row_b = rows
            .iter()
            .find(|r| r.attempt_id.as_deref() == Some("ctx-live_demo-ETHUSDT-1782041001000"))
            .expect("事件 B 必落 admission row");
        assert_eq!(
            row_b.decision.as_deref(),
            Some("SIDE_CELL_DISABLED"),
            "外部 manual disable 必須不等重啟即時生效(F1)"
        );
        assert_eq!(row_b.reason.as_deref(), Some("manual_disable"));
    }
}

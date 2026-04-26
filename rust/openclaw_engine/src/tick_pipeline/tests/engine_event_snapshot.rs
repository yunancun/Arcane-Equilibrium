// G5-09 sibling: BLOCKER-10 D6 EngineEvent + PipelineHealth + broadcast +
// MAJOR-7 D23 snapshot versioning + MAJOR-2 D2 startup barrier.
// G5-09 sibling：EngineEvent + PipelineHealth + 快照版本 + 啟動 barrier。

use super::super::*;

// ═══════════════════════════════════════════════════════════════════════
// BLOCKER-10 / D6: EngineEvent + PipelineHealth tests
// D6 跨引擎事件與管線健康狀態測試
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_d6_engine_event_crashed_clone() {
    // EngineEvent::Crashed must be Clone + Debug (required for broadcast).
    // Crashed 必須支持 Clone + Debug（broadcast 需要）。
    let evt = EngineEvent::Crashed(PipelineKind::Paper);
    let cloned = evt.clone();
    let dbg = format!("{:?}", cloned);
    assert!(dbg.contains("Crashed"));
    assert!(dbg.contains("Paper"));
}

#[test]
fn test_d6_engine_event_cb_tripped_clone() {
    // EngineEvent::CircuitBreakerTripped must be Clone + Debug.
    // CircuitBreakerTripped 必須支持 Clone + Debug。
    let evt = EngineEvent::CircuitBreakerTripped(PipelineKind::Live);
    let cloned = evt.clone();
    let dbg = format!("{:?}", cloned);
    assert!(dbg.contains("CircuitBreakerTripped"));
    assert!(dbg.contains("Live"));
}

#[test]
fn test_d6_pipeline_health_from_u8_roundtrip() {
    // PipelineHealth from_u8 covers all repr values + unknown default.
    // from_u8 覆蓋所有 repr 值 + 未知值默認 Down。
    assert_eq!(PipelineHealth::from_u8(0), PipelineHealth::Running);
    assert_eq!(PipelineHealth::from_u8(1), PipelineHealth::Paused);
    assert_eq!(PipelineHealth::from_u8(2), PipelineHealth::Down);
    assert_eq!(PipelineHealth::from_u8(3), PipelineHealth::Disabled);
    assert_eq!(PipelineHealth::from_u8(255), PipelineHealth::Down); // unknown → Down
}

#[test]
fn test_d6_pipeline_health_repr_values() {
    // Repr values must be stable (stored in AtomicU8 by other code).
    // repr 值必須穩定（其他代碼以 AtomicU8 存儲）。
    assert_eq!(PipelineHealth::Running as u8, 0);
    assert_eq!(PipelineHealth::Paused as u8, 1);
    assert_eq!(PipelineHealth::Down as u8, 2);
    assert_eq!(PipelineHealth::Disabled as u8, 3);
}

#[tokio::test]
async fn test_d6_broadcast_delivers_to_multiple_receivers() {
    // broadcast::channel delivers same event to 2 receivers.
    // broadcast 通道將同一事件送達 2 個接收端。
    let (tx, mut rx1) = tokio::sync::broadcast::channel::<EngineEvent>(4);
    let mut rx2 = tx.subscribe();
    tx.send(EngineEvent::Crashed(PipelineKind::Demo)).unwrap();
    let e1 = rx1.recv().await.unwrap();
    let e2 = rx2.recv().await.unwrap();
    assert!(matches!(e1, EngineEvent::Crashed(PipelineKind::Demo)));
    assert!(matches!(e2, EngineEvent::Crashed(PipelineKind::Demo)));
}

#[tokio::test]
async fn test_d6_broadcast_cb_event_delivery() {
    // CircuitBreakerTripped event delivered via broadcast.
    // 熔斷事件通過 broadcast 送達。
    let (tx, mut rx) = tokio::sync::broadcast::channel::<EngineEvent>(4);
    tx.send(EngineEvent::CircuitBreakerTripped(PipelineKind::Live))
        .unwrap();
    let evt = rx.recv().await.unwrap();
    assert!(matches!(
        evt,
        EngineEvent::CircuitBreakerTripped(PipelineKind::Live)
    ));
}

// ═══════════════════════════════════════════════════════════════════════
// BLOCKER-10 / MAJOR-7 (D23): Snapshot versioning tests
// 快照版本控制測試
// ═══════════════════════════════════════════════════════════════════════

#[test]
fn test_d23_snapshot_schema_version_is_2_0_0() {
    // New snapshot must have schema_version "2.0.0".
    // 新快照的 schema_version 必須是 "2.0.0"。
    let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
    let snap = pipeline.snapshot();
    assert_eq!(snap.schema_version, "2.0.0");
}

#[test]
fn test_d23_snapshot_written_at_ms_nonzero() {
    // written_at_ms must be set to a recent wall-clock timestamp.
    // written_at_ms 必須設為近期的 wall-clock 時間戳。
    let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
    let snap = pipeline.snapshot();
    assert!(snap.written_at_ms > 0, "written_at_ms should be nonzero");
    // Sanity: should be after 2026-01-01 (~1767225600000 ms)
    assert!(
        snap.written_at_ms > 1_700_000_000_000,
        "written_at_ms too old: {}",
        snap.written_at_ms
    );
}

#[test]
fn test_d23_snapshot_deserialization_without_schema_version() {
    // Old snapshot JSON without schema_version should default to "2.0.0".
    // 舊快照 JSON 無 schema_version 時應默認為 "2.0.0"。
    let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 1_000.0);
    let snap = pipeline.snapshot();
    let mut json: serde_json::Value = serde_json::to_value(&snap).unwrap();
    // Remove schema_version + written_at_ms to simulate old format
    json.as_object_mut().unwrap().remove("schema_version");
    json.as_object_mut().unwrap().remove("written_at_ms");
    let raw = serde_json::to_string(&json).unwrap();
    let restored: crate::pipeline_types::PipelineSnapshot = serde_json::from_str(&raw).unwrap();
    assert_eq!(restored.schema_version, "2.0.0"); // serde default
    assert_eq!(restored.written_at_ms, 0); // serde default
}

// ═══════════════════════════════════════════════════════════════════════
// BLOCKER-10 / MAJOR-2 (D2): Startup barrier tests
// 啟動屏障測試
// ═══════════════════════════════════════════════════════════════════════

#[tokio::test]
async fn test_d2_startup_barrier_oneshot_fires() {
    // oneshot channel used for startup barrier works as expected.
    // 啟動屏障的 oneshot 通道正常運作。
    let (tx, rx) = tokio::sync::oneshot::channel::<()>();
    tx.send(()).unwrap();
    let result = tokio::time::timeout(std::time::Duration::from_millis(100), rx).await;
    assert!(result.is_ok(), "oneshot must resolve");
    assert!(result.unwrap().is_ok(), "oneshot must deliver ()");
}

#[tokio::test]
async fn test_d2_startup_barrier_timeout_on_no_send() {
    // If pipeline never sends ready, fan-out timeout should fire.
    // 若管線永不發送 ready，扇出超時應觸發。
    let (_tx, rx) = tokio::sync::oneshot::channel::<()>();
    let result = tokio::time::timeout(std::time::Duration::from_millis(50), rx).await;
    assert!(result.is_err(), "should timeout when no ready signal sent");
}

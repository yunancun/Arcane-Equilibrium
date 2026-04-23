//! Phase 4.1: Teacher consumer loop IPC tests.
//! Phase 4.1：Teacher consumer loop IPC 測試。

use super::super::*;
use super::empty_teacher_slot;

fn populated_teacher_slot(
    initial_enabled: bool,
) -> (TeacherLoopSlot, Arc<AtomicBool>, Arc<ConsumerLoopStatus>) {
    let enabled = Arc::new(AtomicBool::new(initial_enabled));
    let status = Arc::new(ConsumerLoopStatus::default());
    let slot: TeacherLoopSlot = Arc::new(RwLock::new(Some(TeacherLoopHandles {
        enabled: Arc::clone(&enabled),
        status: Arc::clone(&status),
    })));
    (slot, enabled, status)
}

/// uninitialized slot → fail-soft "uninitialized" payload, NOT an error.
/// 未注入槽位 → fail-soft 回傳 "uninitialized"，不是 error。
#[tokio::test]
async fn test_teacher_loop_status_uninitialized_fail_soft() {
    let slot = empty_teacher_slot();
    let resp = handle_get_teacher_loop_status(serde_json::json!(1), &slot).await;
    assert!(resp.error.is_none());
    let result = resp.result.expect("result");
    assert_eq!(result["status"], "uninitialized");
}

/// set_enabled with valid bool flips the atomic and returns ok.
/// set_enabled 帶合法 bool 翻轉 atomic 並回傳 ok。
#[tokio::test]
async fn test_teacher_loop_set_enabled_flips_atomic() {
    let (slot, enabled, _status) = populated_teacher_slot(false);
    let params = serde_json::json!({"enabled": true});
    let resp = handle_set_teacher_loop_enabled(serde_json::json!(2), &params, &slot).await;
    assert!(resp.error.is_none());
    assert_eq!(resp.result.expect("ok")["enabled"], true);
    assert!(enabled.load(Ordering::Relaxed));

    // Flip back / 翻回
    let params = serde_json::json!({"enabled": false});
    let _ = handle_set_teacher_loop_enabled(serde_json::json!(3), &params, &slot).await;
    assert!(!enabled.load(Ordering::Relaxed));
}

/// set_enabled missing/non-bool param → -32600 invalid request.
/// set_enabled 缺欄位或非 bool → -32600。
#[tokio::test]
async fn test_teacher_loop_set_enabled_invalid_params() {
    let (slot, _, _) = populated_teacher_slot(false);
    let params = serde_json::json!({"enabled": "yes"});
    let resp = handle_set_teacher_loop_enabled(serde_json::json!(4), &params, &slot).await;
    assert_eq!(resp.error.expect("err").code, ERR_INVALID_REQUEST);
}

/// get_status returns full counter snapshot when slot populated.
/// 槽位有值時 get_status 回傳完整計數快照。
#[tokio::test]
async fn test_teacher_loop_get_status_populated() {
    let (slot, _, status) = populated_teacher_slot(true);
    status.cycles_attempted.store(7, Ordering::Relaxed);
    status.directives_applied.store(3, Ordering::Relaxed);
    status.directives_vetoed.store(2, Ordering::Relaxed);
    status.cycles_errored.store(1, Ordering::Relaxed);
    status.last_cycle_ms.store(123_456_789, Ordering::Relaxed);

    let resp = handle_get_teacher_loop_status(serde_json::json!(5), &slot).await;
    let r = resp.result.expect("ok");
    assert_eq!(r["status"], "ok");
    assert_eq!(r["enabled"], true);
    assert_eq!(r["cycles_attempted"], 7);
    assert_eq!(r["directives_applied"], 3);
    assert_eq!(r["directives_vetoed"], 2);
    assert_eq!(r["cycles_errored"], 1);
    assert_eq!(r["last_cycle_ms"], 123_456_789);
}

/// set_teacher_loop_enabled on uninitialized slot is fail-soft (no error).
/// 未注入槽位的 set_enabled 也是 fail-soft（不報 error）。
#[tokio::test]
async fn test_teacher_loop_set_enabled_uninitialized_fail_soft() {
    let slot = empty_teacher_slot();
    let params = serde_json::json!({"enabled": true});
    let resp = handle_set_teacher_loop_enabled(serde_json::json!(6), &params, &slot).await;
    assert!(resp.error.is_none());
    assert_eq!(resp.result.expect("ok")["status"], "uninitialized");
}

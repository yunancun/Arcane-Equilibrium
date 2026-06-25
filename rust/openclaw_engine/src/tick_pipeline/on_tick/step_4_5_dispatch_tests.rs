//! step_4_5_dispatch panel-snapshot helper 契約測試。
//!
//! 從 step_4_5_dispatch.rs inline `#[cfg(test)] mod tests` 平移而來（行數
//! 超過 2000 硬上限，比照 event_consumer/dispatch_tests.rs 的 `#[path]` split
//! 慣例拆出）。測試邏輯零變更：覆蓋 try_clone_panel_snapshot 的 4 條
//! AlphaSurface fail-soft / 禁合成 neutral / read-guard 釋放 invariant。
use super::{
    active_bounded_probe_order_submission, bounded_probe_near_touch_decision_for_reject,
    dispatch_admitted_bounded_probe_order, try_clone_panel_snapshot,
};
use crate::bounded_probe_active_order::{
    bounded_probe_order_link_id_for_candidate, ActiveBoundedProbeOrderDecision,
    ActiveBoundedProbeOrderRequest, ActiveBoundedProbeRiskLimits,
};
use crate::bounded_probe_near_touch::{
    BoundedProbeAttemptPlacement, BoundedProbePlacementDecision, BoundedProbePlacementSkipReason,
};
use crate::demo_learning_lane::{
    evaluate_probe_admission, AdmissionConfig, DemoLearningLanePlan, RejectEvent,
};
use crate::tick_pipeline::OrderDispatchRequest;
use openclaw_core::alpha_surface::{AlphaSurface, FundingCurveSnapshot, OIDeltaPanel};
use std::sync::Arc;
use tokio::sync::RwLock as TokioRwLock;

const BOUNDED_PROBE_NOW_MS: u64 = 1_782_040_200_000;

fn bounded_probe_plan() -> DemoLearningLanePlan {
    DemoLearningLanePlan::from_json_str(
        r#"{
            "schema_version": "cost_gate_demo_learning_lane_plan_v1",
            "generated_at_utc": "2026-06-21T11:00:00+00:00",
            "status": "READY_FOR_DEMO_LEARNING_PROBE",
            "gate_status": "OPERATOR_REVIEW",
            "main_cost_gate_adjustment": "NONE",
            "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
            "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
            "operator_authorization": {
                "schema_version": "bounded_demo_probe_operator_authorization_v1",
                "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
                "authorization_id": "auth-demo-eth-sell-001",
                "operator_id": "operator-test",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "expires_at_utc": "2026-06-21T12:00:00+00:00",
                "authority_path_readiness_status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
                "main_cost_gate_adjustment": "NONE",
                "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
                "max_authorized_probe_orders": 1,
                "probe_authority_granted": true,
                "order_authority_granted": true,
                "promotion_evidence": false
            },
            "selected_probe_candidate_count": 1,
            "probe_candidates": [{
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "reject_reason_code": "cost_gate_js_demo_negative_edge",
                "probe_proposal": {
                    "mode": "demo_only_learning_probe",
                    "max_probe_orders": 1,
                    "cooldown_minutes": 30,
                    "requires_runtime_policy_adapter": true,
                    "requires_probe_attempt_logging": true,
                    "requires_probe_outcome_logging": true
                },
                "guardrails": {
                    "main_cost_gate_adjustment": "NONE",
                    "may_bypass_main_live_gate": false,
                    "demo_only": true,
                    "paper_not_promotion_evidence": true,
                    "notional_or_qty_not_granted_by_artifact": true
                }
            }]
        }"#,
    )
    .unwrap()
}

fn bounded_probe_event() -> RejectEvent {
    RejectEvent {
        strategy_name: "ma_crossover".to_string(),
        symbol: "ETHUSDT".to_string(),
        side: "Sell".to_string(),
        reject_reason_code: "cost_gate_js_demo_negative_edge".to_string(),
        engine_mode: "live_demo".to_string(),
        ts_ms: BOUNDED_PROBE_NOW_MS,
        context_id: Some("ctx-demo-ma_crossover-ETHUSDT-1782040200000".to_string()),
        signal_id: Some("sig-demo-ma_crossover-ETHUSDT-1782040200000".to_string()),
    }
}

fn bounded_probe_order_request() -> ActiveBoundedProbeOrderRequest {
    let event = bounded_probe_event();
    let order_link_id = bounded_probe_order_link_id_for_candidate(
        &event.engine_mode,
        event.ts_ms,
        1,
        &event.side_cell_key(),
        event.context_id.as_deref().unwrap(),
        event.signal_id.as_deref().unwrap(),
    )
    .unwrap();
    ActiveBoundedProbeOrderRequest {
        reject_event: event.clone(),
        admission_decision: evaluate_probe_admission(
            &bounded_probe_plan(),
            &event,
            &[],
            BOUNDED_PROBE_NOW_MS,
            &AdmissionConfig::default(),
            true,
            "NORMAL",
        ),
        placement_decision: BoundedProbePlacementDecision::Submit(BoundedProbeAttemptPlacement {
            record_type: "bounded_probe_attempt",
            side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
            limit_price: 3_499.9,
            touch_gap_bps: 0.29,
            reference_price: 3_500.0,
            bbo_age_ms: 0,
        }),
        qty: 0.001,
        order_link_id,
        decision_lease_id: Some("lease-demo-1".to_string()),
        risk_state: "NORMAL".to_string(),
        limits: ActiveBoundedProbeRiskLimits::default(),
    }
}

#[test]
fn active_bounded_probe_submission_forwards_candidate_matched_post_only_limit_request() {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();

    let result = active_bounded_probe_order_submission(&tx, bounded_probe_order_request())
        .expect("dispatch channel should accept request");

    assert!(result.is_some());
    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    let expected_order_link_id = bounded_probe_order_link_id_for_candidate(
        "live_demo",
        BOUNDED_PROBE_NOW_MS,
        1,
        "ma_crossover|ETHUSDT|Sell",
        "ctx-demo-ma_crossover-ETHUSDT-1782040200000",
        "sig-demo-ma_crossover-ETHUSDT-1782040200000",
    )
    .unwrap();
    assert_eq!(req.symbol, "ETHUSDT");
    assert!(!req.is_long);
    assert_eq!(req.order_link_id, expected_order_link_id);
    assert_eq!(req.decision_lease_id.as_deref(), Some("lease-demo-1"));
    assert_eq!(
        req.context_id,
        "ctx-demo-ma_crossover-ETHUSDT-1782040200000"
    );
    assert_eq!(
        req.intent_id.as_deref(),
        Some("sig-demo-ma_crossover-ETHUSDT-1782040200000")
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
fn active_bounded_probe_submission_skips_without_dispatch_when_not_admitted() {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    let mut request = bounded_probe_order_request();
    request.admission_decision.allowed_to_submit_order = false;
    request.admission_decision.decision =
        crate::demo_learning_lane::AdmissionDecisionCode::OrderAuthorityNotGranted;
    request.admission_decision.no_order_authority = true;

    let result = active_bounded_probe_order_submission(&tx, request)
        .expect("skip should not touch dispatch channel");

    assert_eq!(result, None);
    assert!(matches!(
        crate::bounded_probe_active_order::candidate_matched_bounded_probe_order(
            bounded_probe_order_request()
        ),
        ActiveBoundedProbeOrderDecision::Submit(_)
    ));
    assert!(rx.try_recv().is_err());
}

#[test]
fn active_bounded_probe_dispatch_skips_when_effective_notional_exceeds_cap() {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    let decision = crate::bounded_probe_active_order::candidate_matched_bounded_probe_order(
        bounded_probe_order_request(),
    );
    let ActiveBoundedProbeOrderDecision::Submit(mut draft) = decision else {
        panic!("expected admitted bounded probe draft");
    };
    draft.qty = 0.003;

    let sent = dispatch_admitted_bounded_probe_order(&tx, draft)
        .expect("cap skip should not touch dispatch channel error path");

    assert!(!sent);
    assert!(rx.try_recv().is_err());
}

/// 構造帶實際數據的 FundingCurveSnapshot stub（snapshot_ts_ms 可讀驗證）。
fn make_funding_snapshot() -> FundingCurveSnapshot {
    FundingCurveSnapshot {
        symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
        funding_rates_bps: vec![0.5, -0.3],
        next_funding_ms: vec![1_715_000_000_000, 1_715_000_000_000],
        snapshot_ts_ms: 1_715_000_000_000,
        source_tier: "ws_live".to_string(),
    }
}

/// 構造帶實際數據的 OIDeltaPanel stub。
fn make_oi_panel() -> OIDeltaPanel {
    OIDeltaPanel {
        symbols: vec!["BTCUSDT".to_string()],
        oi_delta_5m_pct: vec![1.2],
        oi_delta_15m_pct: vec![2.4],
        oi_delta_1h_pct: vec![-0.8],
        oi_abs: vec![1_000_000.0],
        snapshot_ts_ms: 1_715_000_000_500,
        source_tier: "ws_live".to_string(),
    }
}

// =========================================================================
// Invariant 1: funding_curve slot 存在 + 含 Some → AlphaSurface = Some(&snap)
//              且 snapshot_ts_ms 可讀
// =========================================================================
#[tokio::test]
async fn b_rem_1_invariant_1_funding_slot_present_surface_some_age_readable() {
    let snap = make_funding_snapshot();
    let snap_ts = snap.snapshot_ts_ms;
    let slot: Arc<TokioRwLock<Option<FundingCurveSnapshot>>> =
        Arc::new(TokioRwLock::new(Some(snap)));
    let slot_opt = Some(slot);

    let cloned = try_clone_panel_snapshot(slot_opt.as_ref());
    assert!(
        cloned.is_some(),
        "slot 注入且 inner Some → helper 應回 Some"
    );
    let unwrapped = cloned.unwrap();
    assert_eq!(
        unwrapped.snapshot_ts_ms, snap_ts,
        "snapshot_ts_ms（candidate report age 欄位源）必須可讀"
    );

    // 把 owned snapshot 借進 AlphaSurface，與 dispatch 構造路徑 1:1。
    let surface = AlphaSurface {
        funding_curve: Some(&unwrapped),
        ..AlphaSurface::empty()
    };
    assert!(
        surface.funding_curve.is_some(),
        "AlphaSurface.funding_curve 應反映 slot 內 snapshot"
    );
    assert_eq!(
        surface.funding_curve.unwrap().snapshot_ts_ms,
        snap_ts,
        "surface 端 snapshot_ts_ms 必須與 slot 內容一致"
    );
}

// =========================================================================
// Invariant 2: oi_delta_panel slot 存在 + 含 Some → AlphaSurface = Some(&panel)
//              且 snapshot_ts_ms 可讀
// =========================================================================
#[tokio::test]
async fn b_rem_1_invariant_2_oi_slot_present_surface_some_age_readable() {
    let panel = make_oi_panel();
    let panel_ts = panel.snapshot_ts_ms;
    let slot: Arc<TokioRwLock<Option<OIDeltaPanel>>> = Arc::new(TokioRwLock::new(Some(panel)));
    let slot_opt = Some(slot);

    let cloned = try_clone_panel_snapshot(slot_opt.as_ref());
    assert!(
        cloned.is_some(),
        "oi slot 注入且 inner Some → helper 應回 Some"
    );
    let unwrapped = cloned.unwrap();
    assert_eq!(unwrapped.snapshot_ts_ms, panel_ts, "OI age 必須可讀");

    let surface = AlphaSurface {
        oi_delta_panel: Some(&unwrapped),
        ..AlphaSurface::empty()
    };
    assert!(surface.oi_delta_panel.is_some());
    assert_eq!(
        surface.oi_delta_panel.unwrap().snapshot_ts_ms,
        panel_ts,
        "surface 端 oi_delta_panel.snapshot_ts_ms 必須等於 slot 內容"
    );
}

// =========================================================================
// Invariant 3: writer 持寫鎖 → try_read 失敗 → helper 回 None（fail-soft, 無 panic）
// =========================================================================
//
// 為什麼這條 invariant 關鍵：dispatch 走 sync `try_read()` 而非 async `read()`，
// 期望在 producer/aggregator 寫入瞬間自動 fail-soft；any panic 會炸 on_tick
// hot path（CLAUDE.md §四 hard boundary）。本測試以 `write()` await 取得寫鎖
// 模擬 contention，確認 helper 不 panic 且回 None。
#[tokio::test]
async fn b_rem_1_invariant_3_writer_holds_lock_soft_fail_no_panic() {
    let snap = make_funding_snapshot();
    let slot: Arc<TokioRwLock<Option<FundingCurveSnapshot>>> =
        Arc::new(TokioRwLock::new(Some(snap)));
    let slot_opt = Some(Arc::clone(&slot));

    // 主測 task 直接持寫鎖（write guard 直到 scope 末才 drop）；
    // 不需要 spawn 另一 task — try_read 看到 writer pending 即 Err。
    let _write_guard = slot.write().await;

    let cloned = try_clone_panel_snapshot(slot_opt.as_ref());
    assert!(
        cloned.is_none(),
        "writer 持鎖時 try_read 應 Err → helper 必 fail-soft 回 None"
    );

    // 同時驗證另一條 invariant：在 writer 持鎖期間 surface 端反映 None
    // —— 不允許暴露任何「writer 寫到一半」的 partial snapshot。
    let surface = AlphaSurface {
        funding_curve: cloned.as_ref(),
        ..AlphaSurface::empty()
    };
    assert!(
        surface.funding_curve.is_none(),
        "writer contention 下 AlphaSurface.funding_curve 必須是 None"
    );

    drop(_write_guard);
}

// =========================================================================
// Invariant 4: slot 未注入（None）→ helper 回 None（無合成 neutral）
// =========================================================================
//
// 治理對照（PA spec §6.1 line 260）：「缺 panel slot → 不創造合成 neutral
// 數據; AlphaSurface 對應 field = None」。此為「未接 panel 永遠 None」契約
// （alpha_surface.rs `AlphaSurface` doc + §四 fail-closed default）的 wire-up
// 端保證；違反會 silently 把 placeholder 餵給策略，污染 dispatch metric
// 與 candidate report unavailable_reason 統計。
#[tokio::test]
async fn b_rem_1_invariant_4_slot_missing_no_synthetic_neutral() {
    // funding 路徑
    let funding_slot_opt: Option<&Arc<TokioRwLock<Option<FundingCurveSnapshot>>>> = None;
    let funding_cloned = try_clone_panel_snapshot(funding_slot_opt);
    assert!(
        funding_cloned.is_none(),
        "funding slot 未注入 → helper 必回 None；禁合成 FundingCurveSnapshot::default()"
    );

    // oi 路徑
    let oi_slot_opt: Option<&Arc<TokioRwLock<Option<OIDeltaPanel>>>> = None;
    let oi_cloned = try_clone_panel_snapshot(oi_slot_opt);
    assert!(
        oi_cloned.is_none(),
        "oi slot 未注入 → helper 必回 None；禁合成 OIDeltaPanel::default()"
    );

    // AlphaSurface 端反映：兩條 field 全 None。
    let surface = AlphaSurface {
        funding_curve: funding_cloned.as_ref(),
        oi_delta_panel: oi_cloned.as_ref(),
        ..AlphaSurface::empty()
    };
    assert!(surface.funding_curve.is_none());
    assert!(surface.oi_delta_panel.is_none());
}

// =========================================================================
// 補充：slot 注入但 inner 為 None（producer 尚未首次 emit）→ helper 回 None
// =========================================================================
//
// 這是 invariant 4 的 sibling case：slot 已 late-inject 但 producer 還沒
// 寫第一筆 snapshot。dispatch 必須與「slot 未注入」相同處理（皆 None），
// 否則會發出「slot 已 wire 但永遠 None」的 false-positive availability 信號。
#[tokio::test]
async fn b_rem_1_slot_present_inner_none_returns_none() {
    let slot: Arc<TokioRwLock<Option<FundingCurveSnapshot>>> = Arc::new(TokioRwLock::new(None));
    let slot_opt = Some(slot);

    let cloned = try_clone_panel_snapshot(slot_opt.as_ref());
    assert!(
        cloned.is_none(),
        "slot 注入但 inner None → helper 必回 None（與 slot 未注入語意一致）"
    );
}

// =========================================================================
// 補充：helper 不持有 RwLockReadGuard 跨 strategy dispatch
//
// dispatch hot path 設計：try_clone_panel_snapshot 返回 `Option<T>` owned
// 值，**guard 於 helper 函式內部 drop**；strategy.on_tick 期間不持任何
// panel slot 讀鎖。本測試以 runtime 驗證：取得 owned snapshot 後另一 task
// 必能成功 write，證明 read guard 已釋放。
//
// 對齊 acceptance: PA §6.1 "E2 sub-agent 確認 0 lock held across strategy
// dispatch (現有設計)"。
// =========================================================================
#[tokio::test]
async fn b_rem_1_helper_releases_read_guard_before_return() {
    let snap = make_funding_snapshot();
    let slot: Arc<TokioRwLock<Option<FundingCurveSnapshot>>> =
        Arc::new(TokioRwLock::new(Some(snap)));
    let slot_opt = Some(Arc::clone(&slot));

    // helper return 後 read guard 必須已 drop，否則 try_write 會 Err。
    let _cloned = try_clone_panel_snapshot(slot_opt.as_ref());

    let write_attempt = slot.try_write();
    assert!(
        write_attempt.is_ok(),
        "helper 返回後 read guard 應已 drop；try_write 必須成功，\
         否則 dispatch hot path 會跨 strategy.on_tick 持鎖"
    );
    drop(write_attempt);
}

#[test]
fn bounded_probe_reject_wiring_preview_submits_or_skips_without_order() {
    let submit = bounded_probe_near_touch_decision_for_reject(
        "ma_crossover|BTCUSDT|Sell".to_string(),
        false,
        10_500,
        Some(100.0),
        Some(100.2),
        Some(0.1),
    );
    let BoundedProbePlacementDecision::Submit(attempt) = submit else {
        panic!("expected submit preview");
    };
    assert_eq!(attempt.record_type, "bounded_probe_attempt");
    assert_eq!(attempt.side_cell_key, "ma_crossover|BTCUSDT|Sell");

    let skip = bounded_probe_near_touch_decision_for_reject(
        "ma_crossover|BTCUSDT|Sell".to_string(),
        false,
        10_500,
        Some(100.0),
        None,
        Some(0.1),
    );
    let BoundedProbePlacementDecision::Skip(block) = skip else {
        panic!("expected skip preview");
    };
    assert_eq!(block.record_type, "bounded_probe_touchability_block");
    assert_eq!(
        block.reason,
        BoundedProbePlacementSkipReason::MissingFreshBbo
    );
}

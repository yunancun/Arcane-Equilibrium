//! step_4_5_dispatch panel-snapshot helper 契約測試。
//!
//! 從 step_4_5_dispatch.rs inline `#[cfg(test)] mod tests` 平移而來（行數
//! 超過 2000 硬上限，比照 event_consumer/dispatch_tests.rs 的 `#[path]` split
//! 慣例拆出）。測試邏輯零變更：覆蓋 try_clone_panel_snapshot 的 4 條
//! AlphaSurface fail-soft / 禁合成 neutral / read-guard 釋放 invariant。
use super::{
    active_bounded_probe_order_submission, bounded_probe_active_order_request_for_reject,
    bounded_probe_near_touch_decision_for_reject, bounded_probe_soak_isolation_enabled_from_values,
    dispatch_admitted_bounded_probe_order, try_clone_panel_snapshot,
};
use crate::bounded_probe_active_order::{
    bounded_probe_order_link_id_for_candidate, ActiveBoundedProbeOrderDecision,
    ActiveBoundedProbeOrderRequest, ActiveBoundedProbeRiskLimits,
};
use crate::bounded_probe_near_touch::{
    BoundedProbeAttemptPlacement, BoundedProbePlacementDecision, BoundedProbePlacementSkipReason,
};
use crate::config::risk_config::RiskConfig;
use crate::demo_learning_lane::{
    evaluate_probe_admission, AdmissionConfig, DemoLearningLanePlan, RejectEvent,
};
use crate::tick_pipeline::OrderDispatchRequest;
use openclaw_core::alpha_surface::{AlphaSurface, FundingCurveSnapshot, OIDeltaPanel};
use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::RwLock as TokioRwLock;

const BOUNDED_PROBE_NOW_MS: u64 = 1_782_040_200_000;
const GUI_RISK_CAP_USDT: f64 = 955.24342626;

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
        limits: ActiveBoundedProbeRiskLimits {
            max_demo_notional_usdt_per_order: GUI_RISK_CAP_USDT,
            ..ActiveBoundedProbeRiskLimits::default()
        },
    }
}

#[test]
fn bounded_probe_soak_isolation_blocks_only_explicit_demo_adapter_runtime() {
    assert!(bounded_probe_soak_isolation_enabled_from_values(
        "demo",
        Some("1"),
    ));
    assert!(bounded_probe_soak_isolation_enabled_from_values(
        "live_demo",
        Some(" TRUE "),
    ));

    for engine_mode in ["paper", "live", "mainnet", "backtest", ""] {
        assert!(
            !bounded_probe_soak_isolation_enabled_from_values(engine_mode, Some("1")),
            "non-demo mode must not be blocked by bounded soak isolation"
        );
    }

    for adapter_value in [None, Some(""), Some("0"), Some("false"), Some("yes")] {
        assert!(
            !bounded_probe_soak_isolation_enabled_from_values("live_demo", adapter_value),
            "adapter flag must be explicit true/1"
        );
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
fn bounded_probe_active_request_supplier_uses_gui_percent_cap_and_demo_equity() {
    let mut risk_config = RiskConfig::default();
    risk_config.limits.per_trade_risk_pct = 0.10;
    risk_config.limits.position_size_max_pct = 25.0;
    risk_config.limits.max_order_notional_usdt = 0.0;
    let event = bounded_probe_event();
    let placement = BoundedProbePlacementDecision::Submit(BoundedProbeAttemptPlacement {
        record_type: "bounded_probe_attempt",
        side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
        limit_price: 3_499.9,
        touch_gap_bps: 0.29,
        reference_price: 3_500.0,
        bbo_age_ms: 0,
    });
    let accepted_demo_equity_usdt = 9_551.369_426;

    let request = bounded_probe_active_order_request_for_reject(
        &event,
        &placement,
        0.2,
        1,
        Some("lease-demo-1".to_string()),
        "NORMAL",
        &risk_config,
        Some(accepted_demo_equity_usdt),
    )
    .expect("positive qty, active lease, and GUI risk cap should build supplier request");

    let expected_cap = accepted_demo_equity_usdt * 0.10;
    assert!((request.limits.max_demo_notional_usdt_per_order - expected_cap).abs() < 1e-9);
    assert!(request.limits.max_demo_notional_usdt_per_order > 10.0);
    assert_eq!(request.decision_lease_id.as_deref(), Some("lease-demo-1"));
    assert!(
        crate::bounded_probe_active_order::is_candidate_bound_bounded_probe_order_link_id(
            &request.order_link_id,
            "live_demo",
            BOUNDED_PROBE_NOW_MS,
            "ma_crossover|ETHUSDT|Sell",
            "ctx-demo-ma_crossover-ETHUSDT-1782040200000",
            "sig-demo-ma_crossover-ETHUSDT-1782040200000",
        )
    );
}

#[test]
fn bounded_probe_active_request_supplier_fails_closed_without_lease_or_cap_room() {
    let mut risk_config = RiskConfig::default();
    risk_config.limits.per_trade_risk_pct = 0.10;
    risk_config.limits.position_size_max_pct = 25.0;
    risk_config.limits.max_order_notional_usdt = 0.0;
    let event = bounded_probe_event();
    let placement = BoundedProbePlacementDecision::Submit(BoundedProbeAttemptPlacement {
        record_type: "bounded_probe_attempt",
        side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
        limit_price: 3_499.9,
        touch_gap_bps: 0.29,
        reference_price: 3_500.0,
        bbo_age_ms: 0,
    });

    assert!(bounded_probe_active_order_request_for_reject(
        &event,
        &placement,
        0.2,
        1,
        None,
        "NORMAL",
        &risk_config,
        Some(9_551.369_426),
    )
    .is_none());
    assert!(bounded_probe_active_order_request_for_reject(
        &event,
        &placement,
        1.0,
        1,
        Some("lease-demo-1".to_string()),
        "NORMAL",
        &risk_config,
        Some(9_551.369_426),
    )
    .is_none());
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
    draft.qty = 1.0;

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

// =========================================================================
// 2026-07-02 soak dispatch-edge containment(設計 §1.1/§1.5)withhold 矩陣。
//
// 為什麼是 pipeline 級整合測試:withhold 點位於 `if gate.approved {` 分支
// 頂端、所有副作用之前;只有把真實 Open 推過完整 on_tick(scanner gate →
// exchange gate → dispatch 邊界)才能證明 [27] 審計形狀鐵則(零 Approved
// verdict 殘留 + rejected qty=0 intent)、lease Failed 釋放與 feed 恢復。
// env flag 讀寫全程持 crate::test_env_lock::guard()(process-global env 教訓)。
// =========================================================================

const SOAK_TEST_STRATEGY: &str = "soak_test_open";
const SOAK_FLAG_ENV: &str = "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";

/// 構造 soak 圍欄用有效 plan(envelope 全欄位過核心判定;expires 由測試控制)。
fn soak_plan_json_expiring_at(expires_at_utc: &str) -> String {
    format!(
        r#"{{
            "schema_version": "cost_gate_demo_learning_lane_plan_v1",
            "generated_at_utc": "2026-06-21T11:00:00+00:00",
            "status": "READY_FOR_DEMO_LEARNING_PROBE",
            "gate_status": "OPERATOR_REVIEW",
            "main_cost_gate_adjustment": "NONE",
            "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
            "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
            "operator_authorization": {{
                "schema_version": "bounded_demo_probe_operator_authorization_v1",
                "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
                "authorization_id": "auth-demo-soak-test-001",
                "operator_id": "operator-test",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "expires_at_utc": "{expires_at_utc}",
                "authority_path_readiness_status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
                "main_cost_gate_adjustment": "NONE",
                "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
                "max_authorized_probe_orders": 2,
                "probe_authority_granted": true,
                "order_authority_granted": true,
                "promotion_evidence": false
            }},
            "selected_probe_candidate_count": 0,
            "probe_candidates": []
        }}"#
    )
}

/// withhold 判定走 wall-clock(openclaw_core::now_ms),fixture 到期時刻須
/// 相對真實現在時間構造。
fn rfc3339_relative_to_now(offset_ms: i64) -> String {
    let ms = openclaw_core::now_ms() as i64 + offset_ms;
    chrono::DateTime::from_timestamp_millis(ms)
        .unwrap()
        .to_rfc3339()
}

/// 可開關的最小策略:emit=true 時對 ctx.symbol 發一筆 Open,把「已批准的
/// 普通 Open」推進到 dispatch 邊界。emit=false 供指標暖機期靜默(cost_gate
/// 的 ATR-warmup fail-closed 要求 ATR 可得,見 SEC-11;暖機期不得發 Open
/// 以免污染 verdict / rejection 斷言)。on_rejection 記錄 reason 供
/// eager-mutate 回滾 hook 驗證。
struct AlwaysOpenStrategy {
    active: bool,
    emit: std::sync::Arc<std::sync::atomic::AtomicBool>,
    rejections: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
}

impl crate::strategies::Strategy for AlwaysOpenStrategy {
    fn name(&self) -> &str {
        SOAK_TEST_STRATEGY
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }
    fn declared_alpha_sources(&self) -> &[openclaw_core::alpha_surface::AlphaSourceTag] {
        &[]
    }
    fn on_tick(
        &mut self,
        ctx: &crate::tick_pipeline::TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<crate::strategies::StrategyAction> {
        if !self.emit.load(std::sync::atomic::Ordering::Relaxed) {
            return vec![];
        }
        vec![crate::strategies::StrategyAction::Open(
            crate::intent_processor::OrderIntent {
                symbol: ctx.symbol.to_string(),
                is_long: true,
                qty: 0.01,
                confidence: 0.9,
                strategy: SOAK_TEST_STRATEGY.into(),
                order_type: "market".into(),
                limit_price: None,
                confluence_score: None,
                persistence_elapsed_ms: None,
                time_in_force: None,
                maker_timeout_ms: None,
                intent_type: crate::intent_processor::IntentType::OpenLong,
                earn_payload: None,
            },
        )]
    }
    fn on_rejection(&mut self, _intent: &crate::intent_processor::OrderIntent, reason: &str) {
        self.rejections.lock().unwrap().push(reason.to_string());
    }
}

struct SoakDispatchHarness {
    pipeline: crate::tick_pipeline::TickPipeline,
    emit: std::sync::Arc<std::sync::atomic::AtomicBool>,
    rejections: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
    order_rx: tokio::sync::mpsc::UnboundedReceiver<OrderDispatchRequest>,
    trading_rx: tokio::sync::mpsc::Receiver<crate::database::TradingMsg>,
}

/// Demo(或指定 kind)pipeline + AlwaysOpen 策略 + dispatch/trading channel。
/// `plan_json`:Some=寫入 TempDir plan 檔;None=缺檔(indeterminate 路徑)。
fn soak_harness(
    kind: crate::tick_pipeline::PipelineKind,
    dir: &tempfile::TempDir,
    plan_json: Option<&str>,
) -> SoakDispatchHarness {
    let plan_path = dir.path().join("plan.json");
    if let Some(json) = plan_json {
        std::fs::write(&plan_path, json).unwrap();
    }
    let mut pipeline = crate::tick_pipeline::TickPipeline::with_kind(&["ETHUSDT"], 10_000.0, kind);
    pipeline
        .soak_envelope_gate
        .set_plan_path_for_tests(plan_path);
    let emit = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let rejections = std::sync::Arc::new(std::sync::Mutex::new(Vec::new()));
    pipeline.orchestrator.register(Box::new(AlwaysOpenStrategy {
        active: true,
        emit: std::sync::Arc::clone(&emit),
        rejections: std::sync::Arc::clone(&rejections),
    }));
    let (order_tx, order_rx) = tokio::sync::mpsc::unbounded_channel();
    pipeline.set_shadow_channel(order_tx);
    let (trading_tx, trading_rx) = tokio::sync::mpsc::channel(64);
    pipeline.set_trading_channel(trading_tx);
    SoakDispatchHarness {
        pipeline,
        emit,
        rejections,
        order_rx,
        trading_rx,
    }
}

fn drain_trading_msgs(
    rx: &mut tokio::sync::mpsc::Receiver<crate::database::TradingMsg>,
) -> Vec<crate::database::TradingMsg> {
    let mut out = Vec::new();
    while let Ok(msg) = rx.try_recv() {
        out.push(msg);
    }
    out
}

/// 持 test_env_lock 設定/還原 soak flag 後執行 body(env 為 process-global)。
fn with_soak_flag<R>(value: Option<&str>, body: impl FnOnce() -> R) -> R {
    let _guard = crate::test_env_lock::guard();
    let saved = std::env::var(SOAK_FLAG_ENV).ok();
    match value {
        Some(v) => std::env::set_var(SOAK_FLAG_ENV, v),
        None => std::env::remove_var(SOAK_FLAG_ENV),
    }
    let result = body();
    match saved {
        Some(v) => std::env::set_var(SOAK_FLAG_ENV, v),
        None => std::env::remove_var(SOAK_FLAG_ENV),
    }
    result
}

const SOAK_TEST_TS_MS: u64 = 1_782_040_200_000;

/// 暖機 40 根 1m bar(emit=false,零 Open)讓 ATR 可得,drain 掉暖機期
/// engine 信號雜訊,再開 emit 打「受測 tick」——之後的斷言只看單筆 Open。
fn soak_warm_then_tick(h: &mut SoakDispatchHarness) {
    for i in 0..40u64 {
        let ts = SOAK_TEST_TS_MS - (40 - i) * 60_000;
        // 每根 bar 價格小幅變動,確保 True Range > 0 → ATR > 0。
        let price = 3_000.0 + (i % 7) as f64;
        let _ = h
            .pipeline
            .on_tick(&PriceEvent::new("ETHUSDT".to_string(), price, ts));
    }
    let _ = drain_trading_msgs(&mut h.trading_rx);
    h.emit.store(true, std::sync::atomic::Ordering::Relaxed);
    let event = PriceEvent::new("ETHUSDT".to_string(), 3_000.0, SOAK_TEST_TS_MS);
    let _ = h.pipeline.on_tick(&event);
}

/// §1.5 矩陣①:envelope Active → 無 OrderDispatchRequest + lease 無洩漏 +
/// typed rejected verdict + qty=0 intent + 零 Approved verdict 殘留([27])+
/// on_rejection 回滾 hook + soak_withheld_opens 計數 + exchange_seq 零副作用。
#[test]
fn soak_withhold_active_envelope_blocks_dispatch_with_clean_audit_shape() {
    with_soak_flag(Some("1"), || {
        let dir = tempfile::TempDir::new().unwrap();
        let plan = soak_plan_json_expiring_at(&rfc3339_relative_to_now(3_600_000));
        let mut h = soak_harness(
            crate::tick_pipeline::PipelineKind::Demo,
            &dir,
            Some(&plan),
        );
        soak_warm_then_tick(&mut h);

        assert!(
            h.order_rx.try_recv().is_err(),
            "soak 武裝:普通 approved Open 絕不產生 OrderDispatchRequest"
        );
        assert_eq!(
            h.pipeline.stats.soak_withheld_opens, 1,
            "withhold 計數必遞增"
        );
        assert_eq!(
            h.pipeline.stats.total_intents, 0,
            "withhold 不計入 total_intents(未派發)"
        );
        assert!(
            h.rejections
                .lock()
                .unwrap()
                .iter()
                .any(|r| r == super::BOUNDED_PROBE_SOAK_WITHHELD_REJECT_REASON),
            "on_rejection 回滾 hook 必以 withheld reason 被調用"
        );
        // 副作用零執行的直接證據:exchange_seq 遞增位於 withhold continue 之後。
        assert_eq!(
            h.pipeline.exchange_seq, 0,
            "withhold 必須發生在 exchange_seq 遞增之前(零副作用)"
        );
        // 誠實註記(E2 F2):本測試 router gate 默認 OFF,gate 不取 lease,此
        // 斷言只證「無 SM 物件殘留」,對 lease 釋放無 bite。lease 覆蓋見
        // soak_withhold_with_router_gate_on_leaves_no_live_lease(gate-ON)、
        // withhold_failed_release_revokes_active_lease_without_leak(真 Active
        // lease seam)與 soak_withhold_block_lease_release_contract(源碼契約)。
        assert_eq!(h.pipeline.governance.lease.lock().len(), 0);

        let msgs = drain_trading_msgs(&mut h.trading_rx);
        let mut rejected_verdicts = 0;
        for msg in &msgs {
            match msg {
                crate::database::TradingMsg::RiskVerdict {
                    verdict, reasons, ..
                } => {
                    assert_ne!(
                        verdict, "Approved",
                        "[27] 審計形狀:withhold 路徑不得殘留 Approved verdict"
                    );
                    if verdict == "Rejected" {
                        rejected_verdicts += 1;
                        assert!(
                            reasons
                                .iter()
                                .any(|r| r == super::BOUNDED_PROBE_SOAK_WITHHELD_REJECT_REASON),
                            "rejected verdict 必帶 withheld reason,got {reasons:?}"
                        );
                    }
                }
                crate::database::TradingMsg::Intent { qty, .. } => {
                    assert_eq!(*qty, 0.0, "[27] 審計形狀:withhold intent 必為 qty=0");
                }
                _ => {}
            }
        }
        assert_eq!(rejected_verdicts, 1, "必寫恰一筆 typed rejected verdict");
        assert!(
            msgs.iter()
                .any(|m| matches!(m, crate::database::TradingMsg::Intent { qty, .. } if *qty == 0.0)),
            "必寫 qty=0 intent 行"
        );
    });
}

/// §1.5 矩陣②:envelope 可讀+已過期 → 圍欄解除,Open 正常派發。
#[test]
fn soak_withhold_expired_envelope_allows_dispatch() {
    with_soak_flag(Some("1"), || {
        let dir = tempfile::TempDir::new().unwrap();
        let plan = soak_plan_json_expiring_at(&rfc3339_relative_to_now(-3_600_000));
        let mut h = soak_harness(
            crate::tick_pipeline::PipelineKind::Demo,
            &dir,
            Some(&plan),
        );
        soak_warm_then_tick(&mut h);

        let req = h
            .order_rx
            .try_recv()
            .expect("envelope 已過期 → 圍欄解除,普通 Open 必派發");
        assert_eq!(req.symbol, "ETHUSDT");
        assert_eq!(h.pipeline.stats.soak_withheld_opens, 0);
        // 對照組:放行路徑 exchange_seq 正常遞增(與 withhold 測試的 0 成對)。
        assert_eq!(h.pipeline.exchange_seq, 1);
        let msgs = drain_trading_msgs(&mut h.trading_rx);
        assert!(
            msgs.iter().any(|m| matches!(
                m,
                crate::database::TradingMsg::RiskVerdict { verdict, .. } if verdict == "Approved"
            )),
            "放行路徑必persist Approved verdict(既有行為)"
        );
    });
}

/// §1.5 矩陣③:envelope indeterminate(缺檔且從未可讀)→ fail-closed 照攔。
#[test]
fn soak_withhold_missing_plan_fails_closed() {
    with_soak_flag(Some("1"), || {
        let dir = tempfile::TempDir::new().unwrap();
        let mut h = soak_harness(crate::tick_pipeline::PipelineKind::Demo, &dir, None);
        soak_warm_then_tick(&mut h);

        assert!(
            h.order_rx.try_recv().is_err(),
            "缺檔 = indeterminate → fail-closed 照攔"
        );
        assert_eq!(h.pipeline.stats.soak_withheld_opens, 1);
    });
}

/// §1.5 矩陣④:flag=0(kill switch)→ 圍欄全滅,即使 envelope 有效也放行。
#[test]
fn soak_flag_off_never_withholds_even_with_active_envelope() {
    with_soak_flag(None, || {
        let dir = tempfile::TempDir::new().unwrap();
        let plan = soak_plan_json_expiring_at(&rfc3339_relative_to_now(3_600_000));
        let mut h = soak_harness(
            crate::tick_pipeline::PipelineKind::Demo,
            &dir,
            Some(&plan),
        );
        soak_warm_then_tick(&mut h);

        assert!(
            h.order_rx.try_recv().is_ok(),
            "flag=0 → 圍欄與 withhold 全滅,Open 正常派發"
        );
        assert_eq!(h.pipeline.stats.soak_withheld_opens, 0);
    });
}

/// §1.5 矩陣⑤:paper pipeline 恆不攔(mode 硬條件;live/paper flag 矩陣見上方
/// bounded_probe_soak_isolation_blocks_only_explicit_demo_adapter_runtime)。
#[test]
fn soak_paper_kind_never_withheld_with_flag_and_active_envelope() {
    with_soak_flag(Some("1"), || {
        let dir = tempfile::TempDir::new().unwrap();
        let plan = soak_plan_json_expiring_at(&rfc3339_relative_to_now(3_600_000));
        let mut h = soak_harness(
            crate::tick_pipeline::PipelineKind::Paper,
            &dir,
            Some(&plan),
        );
        soak_warm_then_tick(&mut h);

        assert_eq!(
            h.pipeline.stats.soak_withheld_opens, 0,
            "paper 模式恆不觸發 withhold"
        );
        assert_eq!(
            h.pipeline.stats.total_intents, 1,
            "paper 提交路徑必須完全不受 soak 影響"
        );
    });
}

/// §1.5 feed 恢復釘子:soak 武裝下 cost_gate reject 必餵到 probe writer channel。
/// 此測試在舊 pre-risk guard 下必然失敗(Open 在 gate 前即被攔,writer 斷糧),
/// 證明修復非裝飾。
#[test]
fn soak_cost_gate_reject_feeds_probe_writer_channel_while_armed() {
    with_soak_flag(Some("1"), || {
        let dir = tempfile::TempDir::new().unwrap();
        let plan = soak_plan_json_expiring_at(&rfc3339_relative_to_now(3_600_000));
        let mut h = soak_harness(
            crate::tick_pipeline::PipelineKind::Demo,
            &dir,
            Some(&plan),
        );
        // 注入負 edge estimate → exchange gate cost_gate(JS-demo)拒絕。
        let json = format!(
            r#"{{"{SOAK_TEST_STRATEGY}::ETHUSDT": {{"shrunk_bps": -5.0, "win_rate": 0.4, "n": 50, "std_bps": 2.0}}}}"#
        );
        let estimates = crate::edge_estimates::EdgeEstimates::load_from_str(&json).unwrap();
        h.pipeline.set_edge_estimates(estimates);
        let (writer_handle, mut writer_rx) =
            crate::demo_learning_lane_writer::DemoLearningLaneWriterHandle::handle_for_test();
        h.pipeline.set_demo_learning_lane_writer(writer_handle);

        soak_warm_then_tick(&mut h);

        assert!(
            h.order_rx.try_recv().is_err(),
            "cost_gate reject → 不派發(與 soak 無關的既有語義)"
        );
        assert_eq!(
            h.pipeline.stats.soak_withheld_opens, 0,
            "reject ≠ withhold:計數不得誤增"
        );
        let msg = writer_rx
            .try_recv()
            .expect("cost_gate reject 必餵 probe writer channel(feed 恢復釘子)");
        assert_eq!(msg.event.strategy_name, SOAK_TEST_STRATEGY);
        assert_eq!(msg.event.symbol, "ETHUSDT");
        assert_eq!(
            msg.event.reject_reason_code,
            crate::demo_learning_lane::ELIGIBLE_REJECT_REASON_CODE,
            "reject reason 必 normalize 成 eligible code"
        );
    });
}

// =========================================================================
// E2 F2(2026-07-03)lease 覆蓋三層。
//
// 架構事實(修正 E2 F2 的一處前提):withhold 可達模式(demo/live_demo)
// 經 effective_governance_profile 恆為 Validation profile;router gate ON 時
// acquire_lease 對非 Production profile 短路回 LeaseId::Bypass(governance_core
// acquire_lease 開頭),release_lease(Bypass)=設計上 no-op。真 Active lease
// 在今日接線下於 withhold 路徑結構性不可達(Production 僅 Live+Mainnet,而
// em="live" 被 mode 檢查排除)。因此黑箱 pipeline 測試無法對「刪 release 呼叫」
// 產生行為級 bite——覆蓋改三層:
//   ① gate-ON pipeline 測試:證 withhold 下 lease 取得可觀測(BYPASS 轉移
//      emit)且零 SM 物件/零 live lease 殘留;
//   ② 真 Active lease seam 測試:證 withhold 所用的
//      release_decision_lease_for_governance(...Failed...) 對真 lease 是
//      revoke(execution_failed)且不洩漏——未來若 profile 接線改變,語義已釘;
//   ③ 源碼契約測試(include_str! 範式,同檔 fast_track_reduce.rs 先例):
//      釘死 withhold 塊必含 Failed 釋放呼叫——「刪 release 呼叫」的 mutation
//      由此測試咬紅。
// =========================================================================

/// F2-①:router gate ON 下 withhold 完整走通:acquisition 可觀測(Validation
/// profile → BYPASS 合成轉移),withhold 後零 SM 物件、零 live lease。
#[test]
fn soak_withhold_with_router_gate_on_leaves_no_live_lease() {
    with_soak_flag(Some("1"), || {
        let dir = tempfile::TempDir::new().unwrap();
        let plan = soak_plan_json_expiring_at(&rfc3339_relative_to_now(3_600_000));
        let mut h = soak_harness(
            crate::tick_pipeline::PipelineKind::Demo,
            &dir,
            Some(&plan),
        );
        h.pipeline.governance.set_router_gate_enabled_for_test(true);
        let (ltx, lrx) = std::sync::mpsc::channel();
        h.pipeline.governance.set_lease_transition_tx(ltx);

        soak_warm_then_tick(&mut h);

        assert!(
            h.order_rx.try_recv().is_err(),
            "gate ON 不改變 withhold 語義:無 OrderDispatchRequest"
        );
        assert_eq!(h.pipeline.stats.soak_withheld_opens, 1);
        // 取得可觀測:Validation profile 的 acquire_lease 對受測 tick 的 Open
        // emit 一筆 BYPASS 合成轉移(這證明 gate ON 時 lease facade 真被走到)。
        let transitions: Vec<_> = lrx.try_iter().collect();
        assert!(
            transitions
                .iter()
                .any(|t| t.to_state == "BYPASS" && t.event == "non_production_bypass"),
            "router gate ON 必經 lease facade(BYPASS 轉移可觀測),got {:?}",
            transitions
                .iter()
                .map(|t| (&t.to_state, &t.event))
                .collect::<Vec<_>>()
        );
        // Bypass 不建 SM 物件;withhold 的 release(Bypass) 為設計上 no-op。
        assert_eq!(h.pipeline.governance.lease.lock().len(), 0);
        assert!(h.pipeline.governance.lease.lock().get_live().is_empty());
    });
}

/// F2-②:withhold 所依賴的釋放語義 seam——對真 Active lease 以
/// `LeaseOutcome::Failed` + withhold stage 釋放 = SM revoke(execution_failed),
/// 不 consume、不洩漏 live lease、REVOKED 轉移可觀測。
#[test]
fn withhold_failed_release_revokes_active_lease_without_leak() {
    use openclaw_core::governance_core::{GovernanceCore, GovernanceProfile};

    // Validation core 自動授權(is_authorized=true),再以 Production profile
    // 參數取真 SM lease——鏡像「未來 withhold 模式若接上 requires_lease profile」
    // 時 gate.lease_id 會攜帶的 Active lease。
    let mut governance = GovernanceCore::new_with_profile(GovernanceProfile::Validation);
    let (ltx, lrx) = std::sync::mpsc::channel();
    governance.set_lease_transition_tx(ltx);
    let lease = governance
        .acquire_lease(
            "intent-soak-withhold-seam-1",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Production,
            "router",
        )
        .expect("authorized core + Production profile 必取得真 Active lease");
    assert!(lease.is_active(), "必須是 LeaseId::Active 而非 Bypass");
    assert_eq!(
        governance.lease.lock().get_live().len(),
        1,
        "釋放前必有一條 live lease"
    );

    // 與 withhold 塊逐字同款的釋放呼叫(Failed + withhold stage)。
    super::release_decision_lease_for_governance(
        &governance,
        Some(lease.as_str()),
        super::LeaseOutcome::Failed,
        super::BOUNDED_PROBE_SOAK_WITHHELD_LEASE_STAGE,
    );

    assert!(
        governance.lease.lock().get_live().is_empty(),
        "Failed 釋放後不得殘留 live lease(洩漏)"
    );
    let states = governance.lease.lock().snapshot_states();
    assert!(
        states
            .iter()
            .all(|(_, s)| format!("{s}") == "REVOKED"),
        "Failed 釋放 = revoke(非 consume),got {states:?}"
    );
    let transitions: Vec<_> = lrx.try_iter().collect();
    assert!(
        transitions
            .iter()
            .any(|t| t.to_state == "REVOKED" && t.event == "revoke_requested"),
        "REVOKED 轉移必可觀測(execution_failed 審計軌)"
    );
}

/// F2-③:源碼契約(include_str! 範式,先例見 tick_pipeline/tests/
/// fast_track_reduce.rs)——withhold 塊(should_withhold_approved_open 命中至
/// continue)必含 lease Failed 釋放與完整審計動作。「刪 release 呼叫」的
/// mutation 由本測試咬紅(行為級 bite 因 Bypass 架構不可得,見上方模塊註記)。
#[test]
fn soak_withhold_block_lease_release_contract() {
    let src = include_str!("step_4_5_dispatch.rs");
    let start = src
        .find(".should_withhold_approved_open(")
        .expect("withhold 判定呼叫必存在");
    let end = start
        + src[start..]
            .find("continue;")
            .expect("withhold 塊必以 continue 收尾");
    let block = &src[start..end];
    for required in [
        "release_decision_lease_for_governance",
        "LeaseOutcome::Failed",
        "BOUNDED_PROBE_SOAK_WITHHELD_LEASE_STAGE",
        "gate.lease_id.as_deref()",
        "record_undispatched_rejection",
        "soak_withheld_opens += 1",
    ] {
        assert!(
            block.contains(required),
            "withhold 塊缺失必要動作 `{required}`——lease Failed 釋放/審計形狀被 mutation 移除"
        );
    }
    // L-1(E2 re-review):負向釘子——withhold 塊永不寫 decision_features
    // (gate 已批准非真負樣本,[27] ML 污染防線;QTY-ZERO-SKIP-1 同款取捨)。
    assert!(
        !block.contains("emit_decision_feature"),
        "withhold 塊絕不得出現 decision_features emit(ML 污染防線)"
    );
}

/// E2 NOTE-1(operator 裁決修復):QTY-ZERO-SKIP 路徑與 withhold 塊對齊,
/// `continue` 前必釋放 lease(live Production 下為真 Active lease,消除
/// ExpiryGuardian TTL 兜底的洩漏窗口)。源碼契約手法同 F2-③;Failed 釋放
/// 語義(revoke 非 consume、零 live 殘留)由
/// withhold_failed_release_revokes_active_lease_without_leak seam 測試共同
/// 覆蓋(同一 helper 同一 outcome)。
#[test]
fn qty_zero_skip_block_lease_release_contract() {
    let src = include_str!("step_4_5_dispatch.rs");
    let start = src
        .find("if final_qty <= 0.0 {")
        .expect("qty-zero skip 塊必存在");
    let end = start
        + src[start..]
            .find("continue;")
            .expect("qty-zero skip 塊必以 continue 收尾");
    let block = &src[start..end];
    for required in [
        "release_decision_lease_for_governance",
        "LeaseOutcome::Failed",
        "QTY_ZERO_SKIP_LEASE_STAGE",
        "gate.lease_id.as_deref()",
        "qty_zero_skips += 1",
    ] {
        assert!(
            block.contains(required),
            "qty-zero skip 塊缺失必要動作 `{required}`——lease Failed 釋放被 mutation 移除"
        );
    }
    // R3-1(E2 第三輪):QTY-ZERO-SKIP-1 核心語義的負向釘——skip-not-reject:
    // 該塊 99.9% 為 BTCUSDT 取整噪音,寫 reject 記錄 / decision_features 負標籤
    // 會污染 trading.intents label 與 ML 訓練(該塊設立時的原始理由,修前無測試咬)。
    assert!(
        !block.contains("record_undispatched_rejection"),
        "qty-zero skip 塊絕不得寫 reject 記錄(skip-not-reject 語義)"
    );
    assert!(
        !block.contains("emit_decision_feature"),
        "qty-zero skip 塊絕不得寫 decision_features(ML 污染防線)"
    );
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

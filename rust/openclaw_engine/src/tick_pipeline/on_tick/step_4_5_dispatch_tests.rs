//! step_4_5_dispatch panel-snapshot helper 契約測試。
//!
//! 從 step_4_5_dispatch.rs inline `#[cfg(test)] mod tests` 平移而來（行數
//! 超過 2000 硬上限，比照 event_consumer/dispatch_tests.rs 的 `#[path]` split
//! 慣例拆出）。測試邏輯零變更：覆蓋 try_clone_panel_snapshot 的 4 條
//! AlphaSurface fail-soft / 禁合成 neutral / read-guard 釋放 invariant。
use super::try_clone_panel_snapshot;
use openclaw_core::alpha_surface::{AlphaSurface, FundingCurveSnapshot, OIDeltaPanel};
use std::sync::Arc;
use tokio::sync::RwLock as TokioRwLock;

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
    assert!(cloned.is_some(), "slot 注入且 inner Some → helper 應回 Some");
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
    let slot: Arc<TokioRwLock<Option<OIDeltaPanel>>> =
        Arc::new(TokioRwLock::new(Some(panel)));
    let slot_opt = Some(slot);

    let cloned = try_clone_panel_snapshot(slot_opt.as_ref());
    assert!(cloned.is_some(), "oi slot 注入且 inner Some → helper 應回 Some");
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
    let slot: Arc<TokioRwLock<Option<FundingCurveSnapshot>>> =
        Arc::new(TokioRwLock::new(None));
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

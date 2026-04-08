//! ARCH-RC1 1C-4 B2: Position Reconciler — Bybit-truth vs in-memory baseline.
//! ARCH-RC1 1C-4 B2：持倉對帳器 — 以 Bybit 為真相，與內存基線比對。
//!
//! MODULE_NOTE (EN): Periodically polls `/v5/position/list` (linear) and diffs the
//!   current Bybit positions against the reconciler's own in-memory baseline of
//!   what was seen on the previous cycle. Drift is classified into 4 tiers:
//!     - `Match`        — qty within minor threshold, no action
//!     - `MinorDrift`   — small qty change (< minor_threshold_pct), V014 audit only
//!     - `MajorDrift`   — large qty change (≥ minor_threshold_pct), V014 + governor de-escalate
//!     - `Orphan`       — symbol present on Bybit but absent from baseline, V014 + governor
//!     - `Ghost`        — symbol present in baseline but absent from Bybit, V014 + governor
//!   30s polling interval, fail-open on REST errors (warn + skip cycle, baseline unchanged).
//!   Governor de-escalate is fired through the existing `PaperSessionCommand::ForceGovernorLooser`
//!   channel using `reason_code = "reconcile_mismatch"`, which lands on the same B1 cooldown
//!   path so the 24h guard auto-engages.
//!
//! MODULE_NOTE (中): 週期性輪詢 `/v5/position/list`（linear），與內存基線對比上一輪看到的
//!   倉位狀態。差異分四級：Match / MinorDrift（小幅變動，僅 V014 audit）/ MajorDrift（大幅
//!   變動，V014 + governor 降級）/ Orphan（Bybit 有但基線無）/ Ghost（基線有但 Bybit 無）。
//!   30s 輪詢，REST 錯誤 fail-open（warn + 跳本輪，基線不動）。governor 降級透過既有
//!   `ForceGovernorLooser` 通道發送，reason_code = "reconcile_mismatch"，與 B1 冷卻路徑共用。

use crate::order_manager::OrderCategory;
use crate::position_manager::{PositionInfo, PositionManager};
use crate::tick_pipeline::PaperSessionCommand;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc::UnboundedSender;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

/// Reconciler polling interval — 30s per user spec (B2).
/// 對帳輪詢間隔 — 30 秒（B2 用戶決定）。
pub const RECONCILE_INTERVAL_SECS: u64 = 30;

/// Minor drift threshold (5% qty change). Below this, only V014 audit is emitted;
/// at-or-above triggers governor de-escalate. Rationale: rounding / tick race noise
/// is common at < 5%, while ≥ 5% qty change between two 30s ticks indicates either
/// a missed fill, manual exchange action, or partial-fill bookkeeping divergence,
/// all of which warrant defensive contraction.
/// 小幅漂移閾值（5%）。低於此只記 V014；達到/超過觸發 governor 降級。理由：
/// rounding/tick race 噪音常見於 < 5%，而 ≥ 5% 通常意味著漏接 fill / 手動交易
/// 所導致的真實裂痕，需要保守收縮。
pub const MINOR_DRIFT_THRESHOLD_PCT: f64 = 0.05;

/// Compact baseline view of a position — only the fields the reconciler diffs on.
/// 對帳器使用的精簡持倉視圖 — 僅保留差異判斷需要的欄位。
#[derive(Debug, Clone, PartialEq)]
pub struct PositionView {
    pub symbol: String,
    /// "Buy" / "Sell" — Bybit side string preserved verbatim.
    pub side: String,
    pub qty: f64,
}

impl PositionView {
    /// Normalised key for cross-cycle map lookups (symbol+side, since one symbol
    /// can hold both sides under hedge mode).
    /// 跨輪查找鍵（symbol+side，因為對沖模式下同一交易對可同時持有兩側）。
    pub fn key(&self) -> String {
        format!("{}|{}", self.symbol, self.side)
    }
}

/// Drift classification verdict for one (symbol, side) slot.
/// 單個 (symbol, side) 槽位的漂移分級結果。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DriftVerdict {
    /// Within minor threshold — no action.
    Match,
    /// Qty change below minor threshold — audit-only.
    MinorDrift,
    /// Qty change at-or-above minor threshold — audit + governor.
    MajorDrift,
    /// Bybit has it, baseline does not — audit + governor.
    Orphan,
    /// Baseline has it, Bybit does not — audit + governor.
    Ghost,
}

impl DriftVerdict {
    /// Should this verdict trigger a governor de-escalate?
    /// 該結果是否應觸發 governor 降級？
    pub fn should_trigger_governor(&self) -> bool {
        matches!(
            self,
            DriftVerdict::MajorDrift | DriftVerdict::Orphan | DriftVerdict::Ghost
        )
    }

    /// Human-readable kind string for V014 audit payload.
    /// V014 審計 payload 用的人類可讀類型字串。
    pub fn kind_str(&self) -> &'static str {
        match self {
            DriftVerdict::Match => "match",
            DriftVerdict::MinorDrift => "minor_drift",
            DriftVerdict::MajorDrift => "major_drift",
            DriftVerdict::Orphan => "orphan",
            DriftVerdict::Ghost => "ghost",
        }
    }
}

/// Pure classification function — given a baseline view (previous cycle) and a
/// current view (this cycle's Bybit truth), return the drift verdict. Both are
/// `Option` because either side can be missing. Threshold is the fractional qty
/// change above which `MinorDrift` escalates to `MajorDrift`.
/// 純分類函數 — 給定基線（上輪）與當前 Bybit 真相，返回漂移分級。
pub fn classify(
    baseline: Option<&PositionView>,
    current: Option<&PositionView>,
    minor_threshold_pct: f64,
) -> DriftVerdict {
    match (baseline, current) {
        (None, None) => DriftVerdict::Match,
        (None, Some(_)) => DriftVerdict::Orphan,
        (Some(_), None) => DriftVerdict::Ghost,
        (Some(b), Some(c)) => {
            // If sides differ for the same symbol, treat as major drift —
            // a flip is never noise.
            // 同一 symbol 的 side 不同（多空翻轉）絕非噪音，直接判 major drift。
            if b.side != c.side {
                return DriftVerdict::MajorDrift;
            }
            let denom = b.qty.abs().max(c.qty.abs());
            if denom <= 0.0 {
                return DriftVerdict::Match;
            }
            let delta_ratio = (c.qty - b.qty).abs() / denom;
            if delta_ratio == 0.0 {
                DriftVerdict::Match
            } else if delta_ratio < minor_threshold_pct {
                DriftVerdict::MinorDrift
            } else {
                DriftVerdict::MajorDrift
            }
        }
    }
}

/// Convert a Bybit `PositionInfo` into a compact `PositionView`. Returns `None`
/// for empty positions (size 0 or side "None").
/// 將 Bybit `PositionInfo` 轉為精簡視圖。空倉返回 None。
fn position_info_to_view(p: &PositionInfo) -> Option<PositionView> {
    if p.size <= 0.0 || p.side == "None" {
        return None;
    }
    Some(PositionView {
        symbol: p.symbol.clone(),
        side: p.side.clone(),
        qty: p.size,
    })
}

/// Build a `key → PositionView` map from a Bybit position list.
/// 從 Bybit 持倉列表構建 key → PositionView 對映。
fn build_view_map(positions: &[PositionInfo]) -> HashMap<String, PositionView> {
    let mut out = HashMap::new();
    for p in positions {
        if let Some(v) = position_info_to_view(p) {
            out.insert(v.key(), v);
        }
    }
    out
}

/// Fire-and-forget V014 reconcile audit row.
/// 觸發 V014 對帳審計行（fire-and-forget）。
fn spawn_reconcile_audit(
    audit_pool: &Option<sqlx::PgPool>,
    verdict: &DriftVerdict,
    symbol: &str,
    side: &str,
    baseline_qty: Option<f64>,
    current_qty: Option<f64>,
) {
    let Some(pool) = audit_pool.clone() else {
        return;
    };
    let payload = serde_json::json!({
        "kind": verdict.kind_str(),
        "symbol": symbol,
        "side": side,
        "baseline_qty": baseline_qty,
        "current_qty": current_qty,
    });
    let event_type = format!("reconcile_{}", verdict.kind_str());
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    tokio::spawn(async move {
        if let Err(e) = sqlx::query(
            "INSERT INTO observability.engine_events
             (ts_ms, event_type, source, config_name, old_version, new_version, payload)
             VALUES ($1, $2, $3, $4, NULL, NULL, $5)",
        )
        .bind(ts_ms)
        .bind(&event_type)
        .bind("position_reconciler")
        .bind("trading.positions")
        .bind(&payload)
        .execute(&pool)
        .await
        {
            warn!(error = %e, "V014 reconcile audit insert failed (non-fatal) / V014 對帳審計寫入失敗（非致命）");
        }
    });
}

/// Trigger a governor de-escalate via the existing PaperSessionCommand channel.
/// Uses `reason_code = "reconcile_mismatch"` so the B1 cooldown path engages.
/// 透過既有命令通道觸發 governor 降級。reason_code 固定 reconcile_mismatch，
/// 直通 B1 冷卻路徑。
fn trigger_governor_de_escalate(
    paper_cmd_tx: &UnboundedSender<PaperSessionCommand>,
    target_tier: &str,
    notes: String,
) {
    let (resp_tx, _resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = paper_cmd_tx.send(PaperSessionCommand::ForceGovernorLooser {
        target_tier: target_tier.to_string(),
        reason_code: "reconcile_mismatch".to_string(),
        notes,
        response_tx: resp_tx,
    }) {
        warn!(error = %e, "reconciler failed to send governor de-escalate (channel closed) / 發送 governor 降級失敗（通道關閉）");
    }
}

/// Run one reconciliation cycle: fetch Bybit, classify each slot vs baseline,
/// emit V014 + maybe trigger governor, return the new baseline. On REST failure
/// returns `None` (caller keeps the old baseline — fail-open).
/// 跑一輪對帳：拉 Bybit、分類每槽位、寫 audit、視情觸發 governor，返回新基線。
/// REST 失敗返回 None（caller 保留舊基線，fail-open）。
pub async fn reconcile_once(
    pos_mgr: &PositionManager,
    audit_pool: &Option<sqlx::PgPool>,
    paper_cmd_tx: &UnboundedSender<PaperSessionCommand>,
    baseline: &HashMap<String, PositionView>,
) -> Option<HashMap<String, PositionView>> {
    let positions = match pos_mgr.get_positions(OrderCategory::Linear, None).await {
        Ok(p) => p,
        Err(e) => {
            warn!(error = %e, "reconciler REST fetch failed (fail-open, baseline preserved) / 對帳 REST 失敗（fail-open，基線保留）");
            return None;
        }
    };
    let current = build_view_map(&positions);

    // Union of keys so we catch both sides of every (orphan, ghost).
    // 取兩側 key 的聯集，覆蓋 orphan + ghost 兩種。
    let mut all_keys: std::collections::HashSet<&String> = baseline.keys().collect();
    all_keys.extend(current.keys());

    let mut governor_triggered = false;
    for key in all_keys {
        let b = baseline.get(key);
        let c = current.get(key);
        let verdict = classify(b, c, MINOR_DRIFT_THRESHOLD_PCT);
        if matches!(verdict, DriftVerdict::Match) {
            continue;
        }
        let (sym, side) = match (b, c) {
            (Some(v), _) | (_, Some(v)) => (v.symbol.clone(), v.side.clone()),
            _ => continue,
        };
        let baseline_qty = b.map(|v| v.qty);
        let current_qty = c.map(|v| v.qty);
        info!(
            symbol = %sym,
            side = %side,
            kind = verdict.kind_str(),
            baseline_qty = ?baseline_qty,
            current_qty = ?current_qty,
            "reconcile drift detected / 對帳發現漂移"
        );
        spawn_reconcile_audit(audit_pool, &verdict, &sym, &side, baseline_qty, current_qty);
        if verdict.should_trigger_governor() && !governor_triggered {
            // One trigger per cycle is enough — multiple drifts in one cycle
            // are usually correlated (same outage, same exchange action) and
            // we don't want to repeatedly spam ForceGovernorLooser inside the
            // same 24h cooldown window.
            // 每輪只觸發一次 governor — 同輪多筆漂移通常相關（同一次斷線/同一次手動操作），
            // 不重複轟炸已在 24h 冷卻內的 ForceGovernorLooser。
            let notes = format!(
                "reconciler: {} on {} {} (baseline={:?} current={:?})",
                verdict.kind_str(),
                sym,
                side,
                baseline_qty,
                current_qty
            );
            // Step one tier looser. The IP-side step rule will reject if we
            // are already at the loosest tier; that rejection lands on the
            // governor_de_escalate_rejected V014 audit branch as designed.
            // 降一級。若已在最寬鬆 tier，IP 端 step rule 會拒絕並落到
            // governor_de_escalate_rejected 審計分支，符合預期。
            trigger_governor_de_escalate(paper_cmd_tx, "auto_step_looser", notes);
            governor_triggered = true;
        }
    }

    Some(current)
}

/// Long-running reconciler task. Spawned from `main.rs` once shared_client and
/// db_pool are both available. Uses 30s interval with cancel-aware select.
/// 長運行對帳任務。在 main.rs 中當 shared_client 與 db_pool 都可用時 spawn。
pub async fn run_position_reconciler(
    pos_mgr: Arc<PositionManager>,
    audit_pool: Option<sqlx::PgPool>,
    paper_cmd_tx: UnboundedSender<PaperSessionCommand>,
    cancel: CancellationToken,
) {
    info!(
        interval_secs = RECONCILE_INTERVAL_SECS,
        minor_threshold_pct = MINOR_DRIFT_THRESHOLD_PCT,
        "position_reconciler started / 持倉對帳器啟動"
    );
    let mut baseline: HashMap<String, PositionView> = HashMap::new();
    let mut tick = tokio::time::interval(Duration::from_secs(RECONCILE_INTERVAL_SECS));
    // Skip the immediate first tick so startup doesn't race with bootstrap.
    // 跳過第一次立即 tick，避免與啟動引導競爭。
    tick.tick().await;
    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                info!("position_reconciler stopping (cancel) / 對帳器停止");
                break;
            }
            _ = tick.tick() => {
                if let Some(new_baseline) = reconcile_once(&pos_mgr, &audit_pool, &paper_cmd_tx, &baseline).await {
                    baseline = new_baseline;
                }
            }
        }
    }
}

// ===========================================================================
// Tests / 測試
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    fn pv(symbol: &str, side: &str, qty: f64) -> PositionView {
        PositionView {
            symbol: symbol.to_string(),
            side: side.to_string(),
            qty,
        }
    }

    #[test]
    fn match_when_both_none() {
        assert_eq!(classify(None, None, 0.05), DriftVerdict::Match);
    }

    #[test]
    fn orphan_when_only_current() {
        let cur = pv("BTCUSDT", "Buy", 0.1);
        assert_eq!(classify(None, Some(&cur), 0.05), DriftVerdict::Orphan);
    }

    #[test]
    fn ghost_when_only_baseline() {
        let base = pv("BTCUSDT", "Buy", 0.1);
        assert_eq!(classify(Some(&base), None, 0.05), DriftVerdict::Ghost);
    }

    #[test]
    fn match_when_qty_equal() {
        let a = pv("BTCUSDT", "Buy", 0.1);
        let b = pv("BTCUSDT", "Buy", 0.1);
        assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::Match);
    }

    #[test]
    fn minor_drift_below_threshold() {
        let a = pv("BTCUSDT", "Buy", 1.000);
        let b = pv("BTCUSDT", "Buy", 1.020); // 2% change
        assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::MinorDrift);
    }

    #[test]
    fn major_drift_at_threshold() {
        let a = pv("BTCUSDT", "Buy", 1.000);
        let b = pv("BTCUSDT", "Buy", 1.050); // exactly 5% / 1.05 = ~4.76%; use 1.06
        let b = PositionView { qty: 1.06, ..b };
        assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::MajorDrift);
    }

    #[test]
    fn major_drift_on_side_flip() {
        let a = pv("BTCUSDT", "Buy", 0.1);
        let b = pv("BTCUSDT", "Sell", 0.1);
        assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::MajorDrift);
    }

    #[test]
    fn build_view_map_skips_empty() {
        let positions = vec![
            PositionInfo {
                symbol: "BTCUSDT".into(),
                side: "Buy".into(),
                size: 0.5,
                avg_price: 50000.0,
                mark_price: 50100.0,
                unrealised_pnl: 50.0,
                leverage: 1.0,
                liq_price: 0.0,
                take_profit: 0.0,
                stop_loss: 0.0,
                position_idx: 0,
                trailing_stop: 0.0,
                position_value: 25000.0,
                cum_realised_pnl: 0.0,
                created_time: "".into(),
                updated_time: "".into(),
            },
            PositionInfo {
                symbol: "ETHUSDT".into(),
                side: "None".into(),
                size: 0.0,
                avg_price: 0.0,
                mark_price: 0.0,
                unrealised_pnl: 0.0,
                leverage: 0.0,
                liq_price: 0.0,
                take_profit: 0.0,
                stop_loss: 0.0,
                position_idx: 0,
                trailing_stop: 0.0,
                position_value: 0.0,
                cum_realised_pnl: 0.0,
                created_time: "".into(),
                updated_time: "".into(),
            },
        ];
        let map = build_view_map(&positions);
        assert_eq!(map.len(), 1);
        assert!(map.contains_key("BTCUSDT|Buy"));
    }

    #[test]
    fn verdict_governor_trigger_classification() {
        assert!(!DriftVerdict::Match.should_trigger_governor());
        assert!(!DriftVerdict::MinorDrift.should_trigger_governor());
        assert!(DriftVerdict::MajorDrift.should_trigger_governor());
        assert!(DriftVerdict::Orphan.should_trigger_governor());
        assert!(DriftVerdict::Ghost.should_trigger_governor());
    }
}

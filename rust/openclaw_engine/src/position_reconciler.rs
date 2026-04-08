//! ARCH-RC1 1C-4 B2: Position Reconciler — Bybit-truth vs in-memory baseline.
//! ARCH-RC1 1C-4 B2：持倉對帳器 — 以 Bybit 為真相，與內存基線比對。
//!
//! MODULE_NOTE (EN): Periodically polls `/v5/position/list` (linear) and diffs the
//!   current Bybit positions against the reconciler's own in-memory baseline of
//!   what was seen on the previous cycle. Drift is classified into 5 tiers:
//!     - `Match`        — qty within minor threshold, no action
//!     - `MinorDrift`   — small qty change (< minor_threshold_pct), V014 audit only
//!     - `MajorDrift`   — large qty change (≥ minor_threshold_pct), V014 audit only
//!     - `Orphan`       — symbol present on Bybit but absent from baseline, V014 audit only
//!     - `Ghost`        — symbol present in baseline but absent from Bybit, V014 audit only
//!
//!   30s polling interval, fail-open on REST errors (warn + skip cycle, baseline preserved).
//!
//!   FIRST-CYCLE WARMUP: on task startup, the very first successful REST fetch
//!   silently seeds the baseline without classification. This prevents a "cold-start
//!   orphan storm" where every existing Bybit position would otherwise be classified
//!   as Orphan against an empty baseline on the first real cycle.
//!
//!   AUDIT-ONLY (1C-4 wrap downgrade): the original B2 design fired a governor
//!   de-escalate via `PaperSessionCommand::ForceGovernorLooser` on every Major /
//!   Orphan / Ghost. QA + E2 review found that path to be (a) functionally dead
//!   because the operator-manual-override whitelist rejected the reconciler's
//!   `reason_code` and `target_tier`, and (b) semantically wrong because reconciler
//!   events would have polluted the B1 24h operator-cooldown replay path. The
//!   downgrade keeps the full 5-tier drift detection + V014 evidence trail intact;
//!   the missing automated-contraction capability is tracked as a Phase 6 follow-up
//!   (see TODO.md "Phase 6 自動收縮").
//!
//! MODULE_NOTE (中): 週期性輪詢 `/v5/position/list`（linear），與內存基線對比上一輪
//!   看到的倉位狀態。差異分五級：Match / MinorDrift / MajorDrift / Orphan / Ghost，
//!   全部僅寫 V014 audit。30s 輪詢，REST 錯誤 fail-open。
//!
//!   首輪 warmup：任務啟動後第一次成功 REST 抓取只做基線播種，不進行分類，
//!   避免「冷啟動 orphan 風暴」（既有 Bybit 倉位被空基線全部誤判為 Orphan）。
//!
//!   1C-4 wrap 降級：原設計每次 Major/Orphan/Ghost 都觸發 governor 降級，QA+E2
//!   審查發現該路徑（a）因 operator manual override 白名單拒絕 reconciler 的
//!   reason_code/target_tier 而功能性失效，（b）若擴大白名單會污染 B1 的 24h
//!   operator cooldown replay 語義。降級後保留完整 5 級漂移偵測 + V014 證據鏈，
//!   缺失的自動收縮能力延後至 Phase 6 處理（見 TODO.md「Phase 6 自動收縮」）。

use crate::order_manager::OrderCategory;
use crate::position_manager::{PositionInfo, PositionManager};
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
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
    /// Is this verdict a "concerning" drift (anything other than `Match`)?
    /// Used by audit emission to skip noise. After the 1C-4 wrap downgrade,
    /// no verdict triggers an automatic governor action — Phase 6 will revisit
    /// (see TODO.md). The classification taxonomy is preserved unchanged so
    /// Phase 6 only needs to wire a new action layer on top.
    /// 是否為值得關注的漂移（非 Match）。降級後所有 verdict 都只進 V014，
    /// Phase 6 會在保留分類的前提下加回自動動作層。
    pub fn is_drift(&self) -> bool {
        !matches!(self, DriftVerdict::Match)
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

/// Fetch the current Bybit truth view. Returns `None` on REST error (fail-open;
/// caller preserves old baseline). Used by both warmup seeding and the cycle loop.
/// 抓取 Bybit 真相視圖。REST 失敗返回 None（fail-open）。warmup 與 cycle loop 共用。
async fn fetch_current_view(
    pos_mgr: &PositionManager,
) -> Option<HashMap<String, PositionView>> {
    match pos_mgr.get_positions(OrderCategory::Linear, None).await {
        Ok(p) => Some(build_view_map(&p)),
        Err(e) => {
            warn!(error = %e, "reconciler REST fetch failed (fail-open, baseline preserved) / 對帳 REST 失敗（fail-open，基線保留）");
            None
        }
    }
}

/// Run one reconciliation cycle: fetch Bybit, classify each slot vs baseline,
/// emit V014 audit rows for every drift. Returns the new baseline. On REST
/// failure returns `None` (caller keeps the old baseline — fail-open).
///
/// AUDIT-ONLY: this function emits V014 evidence but never triggers an automatic
/// governor de-escalate. Automated contraction is a Phase 6 deliverable.
///
/// 跑一輪對帳：拉 Bybit、分類每槽位、為每筆漂移寫 V014 行。REST 失敗返回 None。
/// 純 audit：本函數不觸發自動 governor 降級，自動收縮列為 Phase 6 任務。
pub async fn reconcile_once(
    pos_mgr: &PositionManager,
    audit_pool: &Option<sqlx::PgPool>,
    baseline: &HashMap<String, PositionView>,
) -> Option<HashMap<String, PositionView>> {
    let current = fetch_current_view(pos_mgr).await?;

    // Union of keys so we catch both sides of every (orphan, ghost).
    // 取兩側 key 的聯集，覆蓋 orphan + ghost 兩種。
    let mut all_keys: std::collections::HashSet<&String> = baseline.keys().collect();
    all_keys.extend(current.keys());

    for key in all_keys {
        let b = baseline.get(key);
        let c = current.get(key);
        let verdict = classify(b, c, MINOR_DRIFT_THRESHOLD_PCT);
        if !verdict.is_drift() {
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
            "reconcile drift detected (audit-only) / 對帳發現漂移（純審計）"
        );
        spawn_reconcile_audit(audit_pool, &verdict, &sym, &side, baseline_qty, current_qty);
    }

    Some(current)
}

/// Long-running reconciler task. Spawned from `main.rs` once shared_client and
/// db_pool are both available. Uses 30s interval with cancel-aware select.
///
/// Startup sequence:
///   1. Skip the immediate first interval tick (avoid racing the bootstrap).
///   2. Warmup-seed the baseline silently from a one-shot REST fetch — any
///      already-open Bybit positions are recorded WITHOUT being classified
///      against an empty baseline (which would otherwise produce a cold-start
///      orphan storm of false drift events).
///   3. Enter the cycle loop where every successful tick runs `reconcile_once`.
///
/// 長運行對帳任務。啟動順序：
///   1. 跳過第一次立即 tick；
///   2. 用一次 REST 抓取靜默播種基線（既有持倉直接寫入基線、不分類），
///      避免冷啟動時被空基線誤判為 orphan 風暴；
///   3. 進入主循環，每次成功 tick 跑 reconcile_once。
pub async fn run_position_reconciler(
    pos_mgr: Arc<PositionManager>,
    audit_pool: Option<sqlx::PgPool>,
    cancel: CancellationToken,
) {
    info!(
        interval_secs = RECONCILE_INTERVAL_SECS,
        minor_threshold_pct = MINOR_DRIFT_THRESHOLD_PCT,
        "position_reconciler started (audit-only mode) / 持倉對帳器啟動（純審計模式）"
    );
    let mut baseline: HashMap<String, PositionView> = HashMap::new();
    let mut tick = tokio::time::interval(Duration::from_secs(RECONCILE_INTERVAL_SECS));
    // Skip the immediate first tick so startup doesn't race with bootstrap.
    // 跳過第一次立即 tick，避免與啟動引導競爭。
    tick.tick().await;

    // Warmup seed (cancellable). If REST fails on warmup we leave baseline empty
    // and the next cycle's first successful fetch will seed via reconcile_once;
    // every existing position would then surface as Orphan once. Acceptable
    // edge case (REST unhealthy at boot is itself worth flagging in V014).
    // Warmup 階段也可被取消。若 warmup REST 失敗，baseline 保持空，下一輪首次
    // 成功 fetch 時會走 reconcile_once，所有既有持倉會以 Orphan 各記一次 V014
    // — 啟動時 REST 不健康本身就值得記錄，這個邊界可接受。
    tokio::select! {
        _ = cancel.cancelled() => {
            info!("position_reconciler stopping during warmup (cancel) / 對帳器於 warmup 階段停止");
            return;
        }
        seeded = fetch_current_view(&pos_mgr) => {
            if let Some(view) = seeded {
                let n = view.len();
                baseline = view;
                info!(seeded = n, "position_reconciler warmup baseline seeded / 對帳器 warmup 基線已播種");
            } else {
                warn!("position_reconciler warmup REST failed; baseline empty / warmup REST 失敗，基線留空");
            }
        }
    }

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                info!("position_reconciler stopping (cancel) / 對帳器停止");
                break;
            }
            _ = tick.tick() => {
                if let Some(new_baseline) = reconcile_once(&pos_mgr, &audit_pool, &baseline).await {
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
    fn major_drift_above_threshold() {
        // 1.06 vs 1.0: delta_ratio = 0.06 / 1.06 = 5.66% > 5% → MajorDrift.
        // 1.06 對 1.0：delta_ratio = 5.66%，超過 5% 閾值。
        let a = pv("BTCUSDT", "Buy", 1.000);
        let b = pv("BTCUSDT", "Buy", 1.060);
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
    fn is_drift_classification() {
        // Match is the only "no concern" verdict; everything else is drift.
        // 1C-4 wrap downgrade: post-degradation no verdict triggers a governor
        // action — Phase 6 will revisit.
        // Match 是唯一非漂移；其餘皆為漂移。降級後均不觸發 governor，留待 Phase 6。
        assert!(!DriftVerdict::Match.is_drift());
        assert!(DriftVerdict::MinorDrift.is_drift());
        assert!(DriftVerdict::MajorDrift.is_drift());
        assert!(DriftVerdict::Orphan.is_drift());
        assert!(DriftVerdict::Ghost.is_drift());
    }
}

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
//!   Phase 6 AUTO-CONTRACTION: the original 1C-4 wrap was audit-only. Phase 6 adds
//!   the action layer: drift → risk governor escalation (tighten constraints) →
//!   auto-recovery when clean. CircuitBreaker (5+ simultaneous drifts) also triggers
//!   CloseAll. Recovery uses hybrid clean-cycles + wall-clock with tier-specific
//!   windows (15/10/10 min). CB/MR recovery remains operator-only.
//!   Key additions: `ReconcilerState`, `evaluate_actions()`, `ReconcilerAction`,
//!   `check_rest_failure_escalation()`, `filter_dust()`, staleness reseed (6-RC-9).
//!
//! MODULE_NOTE (中): 週期性輪詢 `/v5/position/list`（linear），與內存基線對比上一輪
//!   看到的倉位狀態。差異分五級：Match / MinorDrift / MajorDrift / Orphan / Ghost，
//!   全部僅寫 V014 audit。30s 輪詢，REST 錯誤 fail-open。
//!
//!   首輪 warmup：任務啟動後第一次成功 REST 抓取只做基線播種，不進行分類，
//!   避免「冷啟動 orphan 風暴」（既有 Bybit 倉位被空基線全部誤判為 Orphan）。
//!   注意：warmup 完成到第一次 cycle tick 之間仍有 ~30s race window，期間新開的
//!   倉位會在 cycle 1 被歸類為單筆 Orphan（非風暴，可接受 — Phase 6 自動動作層
//!   會以 6-RC-4 自身冷卻 + 6-RC-9 baseline staleness 政策另外處理）。
//!   Spawn 僅 gate 在 `shared_client.is_some()`，**不**依 system_mode — demo_only
//!   下亦會輪詢 mainnet REST，因為 reconciler 的本職就是感知外部世界觀變化，
//!   demo 期間更需要練習此感知能力（operator 確認，2026-04-08）。
//!
//!   Phase 6 自動降級：原 1C-4 wrap 為純 audit。Phase 6 加上動作層：
//!   漂移 → 風控升級（收緊約束）→ 乾淨週期後自動恢復。CB（5+ 同時漂移）另觸發
//!   全平倉。恢復用 hybrid 乾淨週期 + 牆鐘雙條件（15/10/10 min）。
//!   CB/MR 恢復仍需 operator。

pub mod escalation;
#[cfg(test)]
mod tests;

// Re-export escalation types so callers see them at `position_reconciler::*`.
pub use escalation::*;

use crate::instrument_info::InstrumentInfoCache;
use crate::order_manager::OrderCategory;
use crate::position_manager::{PositionInfo, PositionManager};
use openclaw_core::sm::risk_gov::RiskLevel;
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
    /// Direction flip on same symbol (Buy↔Sell) — distinct from qty drift.
    /// 同一 symbol 方向翻轉（多空互換）— 與數量漂移本質不同。
    SideFlip,
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
            DriftVerdict::SideFlip => "side_flip",
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
            // If sides differ for the same symbol, it's a direction flip —
            // distinct from qty drift, never noise.
            // 同一 symbol 的 side 不同（多空翻轉）— 與數量漂移本質不同，絕非噪音。
            if b.side != c.side {
                return DriftVerdict::SideFlip;
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

/// Filter a view map to remove dust positions below 1.5 × minOrderQty (6-RC-5).
/// 過濾 dust 倉位：低於 1.5 × minOrderQty 的倉位被忽略。
pub fn filter_dust(
    views: &mut HashMap<String, PositionView>,
    instrument_cache: &InstrumentInfoCache,
) {
    views.retain(|_, v| {
        if let Some(spec) = instrument_cache.get(&v.symbol) {
            v.qty.abs() >= spec.min_qty * DUST_FLOOR_MULTIPLIER
        } else {
            true // keep if no instrument info (conservative — don't discard unknowns)
        }
    });
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
    engine_label: &str,
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
        "engine": engine_label,
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
    engine_label: &str,
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
        spawn_reconcile_audit(audit_pool, &verdict, &sym, &side, baseline_qty, current_qty, engine_label);
    }

    Some(current)
}

/// Long-running reconciler task with Phase 6 auto-contraction action layer.
///
/// Startup sequence:
///   1. Skip the immediate first interval tick (avoid racing the bootstrap).
///   2. Warmup-seed the baseline silently from a one-shot REST fetch.
///   3. Enter the cycle loop: reconcile_once → evaluate_actions → send commands.
///
/// Phase 6 additions: `ReconcilerState` tracks drift streaks, cooldowns, and
/// recovery progress. Actions are dispatched as `PipelineCommand` variants.
///
/// 長運行對帳任務（含 Phase 6 自動降級動作層）。
/// 3E D23: `engine_label` identifies which pipeline owns this reconciler instance
/// (e.g. "demo", "live"). Used in V014 audit events and log messages to
/// distinguish per-engine reconciler output when multiple reconcilers run.
/// 3E D23：`engine_label` 識別此對帳器實例所屬管線（如 "demo"、"live"）。
/// 用於 V014 審計事件和日誌訊息，區分多對帳器並行時的輸出。
pub async fn run_position_reconciler(
    pos_mgr: Arc<PositionManager>,
    audit_pool: Option<sqlx::PgPool>,
    cancel: CancellationToken,
    cmd_tx: tokio::sync::mpsc::UnboundedSender<crate::tick_pipeline::PipelineCommand>,
    instrument_cache: Option<Arc<InstrumentInfoCache>>,
    get_risk_level: impl Fn() -> RiskLevel + Send + 'static,
    engine_label: String,
) {
    info!(
        engine = %engine_label,
        interval_secs = RECONCILE_INTERVAL_SECS,
        minor_threshold_pct = MINOR_DRIFT_THRESHOLD_PCT,
        "position_reconciler started (Phase 6 auto-contraction) / 持倉對帳器啟動（Phase 6 自動降級）"
    );
    let mut rc_state = ReconcilerState::new();
    let mut tick = tokio::time::interval(Duration::from_secs(RECONCILE_INTERVAL_SECS));
    tick.tick().await; // skip immediate first tick

    // Warmup seed
    tokio::select! {
        _ = cancel.cancelled() => {
            info!("position_reconciler stopping during warmup (cancel) / 對帳器於 warmup 階段停止");
            return;
        }
        seeded = fetch_current_view(&pos_mgr) => {
            if let Some(mut view) = seeded {
                if let Some(cache) = instrument_cache.as_ref() {
                    filter_dust(&mut view, cache);
                }
                let n = view.len();
                rc_state.baseline = view;
                rc_state.last_successful_fetch_ms = now_ms_util();
                info!(seeded = n, "position_reconciler warmup baseline seeded / 對帳器 warmup 基線已播種");
            } else {
                warn!("position_reconciler warmup REST failed; baseline empty / warmup REST 失敗，基線留空");
                rc_state.consecutive_rest_failures += 1;
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
                let now = now_ms_util();
                let current_level = get_risk_level();

                // -- Fetch current Bybit truth --
                let fetch_result = fetch_current_view(&pos_mgr).await;

                match fetch_result {
                    None => {
                        // REST failed — fail-open for drift detection, but track failures.
                        rc_state.consecutive_rest_failures += 1;
                        // 6-RC-10: escalate on sustained REST failures (progressive)
                        if let Some(action) = check_rest_failure_escalation(
                            &mut rc_state, current_level, now,
                        ) {
                            let sent = dispatch_action(&action, &cmd_tx, &audit_pool, &engine_label);
                            if sent && rc_state.pre_escalation_level.is_none() {
                                rc_state.pre_escalation_level = Some(current_level);
                            }
                        }
                    }
                    Some(mut current) => {
                        rc_state.consecutive_rest_failures = 0;

                        // 6-RC-5: dust filter
                        if let Some(cache) = instrument_cache.as_ref() {
                            filter_dust(&mut current, cache);
                        }

                        // 6-RC-9: staleness check — reseed if baseline too old.
                        // IMPORTANT: compare against PREVIOUS last_successful_fetch_ms
                        // BEFORE updating it to `now`. (QC audit fix: was dead code when
                        // last_successful_fetch_ms was set to `now` before this check.)
                        // 重要：與「上一次」成功時間比較，不是當前時間。
                        let prev_fetch = rc_state.last_successful_fetch_ms;
                        let stale = prev_fetch > 0
                            && now.saturating_sub(prev_fetch) > STALENESS_THRESHOLD_MS;
                        // Now update to current time.
                        rc_state.last_successful_fetch_ms = now;
                        if stale || rc_state.baseline.is_empty() {
                            // Reseed: adopt current as baseline without classification
                            let n = current.len();
                            rc_state.baseline = current;
                            info!(seeded = n, stale = stale,
                                "baseline reseeded (staleness or empty) / 基線重播種");
                            continue;
                        }

                        // -- Classify drifts --
                        let mut all_keys: std::collections::HashSet<&String> =
                            rc_state.baseline.keys().collect();
                        all_keys.extend(current.keys());

                        let mut drifts: Vec<(String, DriftVerdict)> = Vec::new();
                        for key in &all_keys {
                            let b = rc_state.baseline.get(*key);
                            let c = current.get(*key);
                            let verdict = classify(b, c, MINOR_DRIFT_THRESHOLD_PCT);
                            if verdict.is_drift() {
                                let (sym, side) = match (b, c) {
                                    (Some(v), _) | (_, Some(v)) => {
                                        (v.symbol.clone(), v.side.clone())
                                    }
                                    _ => continue,
                                };
                                let baseline_qty = b.map(|v| v.qty);
                                let current_qty = c.map(|v| v.qty);
                                info!(
                                    symbol = %sym, side = %side,
                                    kind = verdict.kind_str(),
                                    baseline_qty = ?baseline_qty,
                                    current_qty = ?current_qty,
                                    "reconcile drift detected / 對帳發現漂移"
                                );
                                spawn_reconcile_audit(
                                    &audit_pool, &verdict, &sym, &side,
                                    baseline_qty, current_qty, &engine_label,
                                );
                                drifts.push(((*key).clone(), verdict));
                            }
                        }

                        // -- Phase 6: evaluate and dispatch actions --
                        let actions = evaluate_actions(
                            &mut rc_state, current_level, &drifts, now,
                        );
                        for action in &actions {
                            let sent = dispatch_action(action, &cmd_tx, &audit_pool, &engine_label);
                            // Set pre_escalation_level only after successful channel send.
                            // This prevents recording a floor for commands that failed to dispatch.
                            // 只在成功送入通道後設置 pre_escalation_level，
                            // 避免為未成功分發的命令記錄恢復 floor。
                            if sent {
                                if let ReconcilerAction::Escalate { .. } = action {
                                    if rc_state.pre_escalation_level.is_none() {
                                        rc_state.pre_escalation_level = Some(current_level);
                                    }
                                }
                            }
                        }

                        // Update baseline
                        rc_state.baseline = current;
                    }
                }
            }
        }
    }
}

/// Dispatch a `ReconcilerAction` by sending the corresponding `PipelineCommand`.
/// Returns `true` if the command was successfully sent to the channel.
/// 分發 `ReconcilerAction`，發送對應的 `PipelineCommand`。成功送入通道返回 true。
fn dispatch_action(
    action: &ReconcilerAction,
    cmd_tx: &tokio::sync::mpsc::UnboundedSender<crate::tick_pipeline::PipelineCommand>,
    audit_pool: &Option<sqlx::PgPool>,
    engine_label: &str,
) -> bool {
    use crate::tick_pipeline::PipelineCommand;

    match action {
        ReconcilerAction::Escalate { target, reason } => {
            let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
            let event_type = "reconciler_auto_escalate";
            spawn_action_audit(audit_pool, event_type, &target.as_str(), reason, engine_label);
            if let Err(e) = cmd_tx.send(PipelineCommand::ReconcilerEscalate {
                target_tier: target.as_str().to_string(),
                reason: reason.clone(),
                response_tx: resp_tx,
            }) {
                warn!(error = %e, "failed to send ReconcilerEscalate command / 發送升級命令失敗");
                return false;
            }
            // QC audit fix: log handler response instead of silently dropping.
            // 審計修復：記錄 handler 回應而非靜默丟棄。
            tokio::spawn(async move {
                match resp_rx.await {
                    Ok(Ok(_)) => {}
                    Ok(Err(e)) => warn!(error = %e, "ReconcilerEscalate handler rejected / 升級被 handler 拒絕"),
                    Err(_) => warn!("ReconcilerEscalate response channel dropped / 升級回應通道丟失"),
                }
            });
            true
        }
        ReconcilerAction::DeEscalate { target, reason } => {
            let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
            let event_type = "reconciler_auto_recover";
            spawn_action_audit(audit_pool, event_type, &target.as_str(), reason, engine_label);
            if let Err(e) = cmd_tx.send(PipelineCommand::ReconcilerDeEscalate {
                target_tier: target.as_str().to_string(),
                reason: reason.clone(),
                response_tx: resp_tx,
            }) {
                warn!(error = %e, "failed to send ReconcilerDeEscalate command / 發送恢復命令失敗");
                return false;
            }
            // QC audit fix: log handler response instead of silently dropping.
            tokio::spawn(async move {
                match resp_rx.await {
                    Ok(Ok(_)) => {}
                    Ok(Err(e)) => warn!(error = %e, "ReconcilerDeEscalate handler rejected / 恢復被 handler 拒絕"),
                    Err(_) => warn!("ReconcilerDeEscalate response channel dropped / 恢復回應通道丟失"),
                }
            });
            true
        }
        ReconcilerAction::CloseAll { reason } => {
            let event_type = "reconciler_close_all";
            spawn_action_audit(audit_pool, event_type, "CIRCUIT_BREAKER", reason, engine_label);
            if let Err(e) = cmd_tx.send(PipelineCommand::CloseAll) {
                warn!(error = %e, "failed to send CloseAll command / 發送全平倉命令失敗");
                return false;
            }
            true
        }
    }
}

/// Fire-and-forget V014 audit for reconciler actions (escalation / recovery / close-all).
/// Separate event_type from observation audits (reconcile_major_drift etc.) per 6-RC-2.
/// 對帳器動作的 V014 審計（升級/恢復/全平倉）。事件類型與觀察審計區分（6-RC-2）。
fn spawn_action_audit(
    audit_pool: &Option<sqlx::PgPool>,
    event_type: &str,
    target_tier: &str,
    reason: &str,
    engine_label: &str,
) {
    let Some(pool) = audit_pool.clone() else { return };
    let payload = serde_json::json!({
        "target_tier": target_tier,
        "reason": reason,
        "engine": engine_label,
    });
    let et = event_type.to_string();
    let ts_ms = now_ms_util() as i64;
    tokio::spawn(async move {
        if let Err(e) = sqlx::query(
            "INSERT INTO observability.engine_events
             (ts_ms, event_type, source, config_name, old_version, new_version, payload)
             VALUES ($1, $2, $3, $4, NULL, NULL, $5)",
        )
        .bind(ts_ms)
        .bind(&et)
        .bind("position_reconciler")
        .bind("reconciler.auto_contraction")
        .bind(&payload)
        .execute(&pool)
        .await
        {
            warn!(error = %e, "V014 reconciler action audit insert failed / 對帳器動作審計寫入失敗");
        }
    });
}

// S-04: use shared now_ms() from openclaw_core instead of local copy.
// S-04：使用 openclaw_core 的共用 now_ms() 取代本地副本。
use openclaw_core::now_ms as now_ms_util;

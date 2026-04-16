//! Phase 6 auto-contraction: escalation logic, recovery, and state tracking.
//! Phase 6 自動降級：升級邏輯、恢復和狀態追蹤。
//!
//! Pure functions that evaluate drift results and determine actions
//! (escalation / recovery / close-all). No I/O — the caller dispatches.

use super::{DriftVerdict, PositionView};
use openclaw_core::sm::risk_gov::RiskLevel;
use std::collections::HashMap;

// ═══════════════════════════════════════════════════════════════════════════════
// Phase 6: Auto-contraction constants / 自動降級常量
// ═══════════════════════════════════════════════════════════════════════════════

/// Dust floor multiplier for minOrderQty (6-RC-5). Positions below this are ignored.
/// 灰塵閾值倍數（6-RC-5）。低於 minOrderQty × 此倍數的倉位被忽略。
pub const DUST_FLOOR_MULTIPLIER: f64 = 1.5;

/// Baseline staleness threshold (6-RC-9). If last successful REST > this, reseed.
/// 基線過期閾值（6-RC-9）。上次成功 REST 超過此時間則重播種。
pub const STALENESS_THRESHOLD_MS: u64 = 600_000; // 10 minutes

/// Consecutive REST failures before escalation tiers (6-RC-10 progressive).
/// 連續 REST 失敗漸進升級閾值。
pub const REST_FAILURE_TIER1_COUNT: u32 = 10;  // → Cautious  (5 min without verification)
pub const REST_FAILURE_TIER2_COUNT: u32 = 30;  // → Reduced   (15 min)
pub const REST_FAILURE_TIER3_COUNT: u32 = 60;  // → Defensive (30 min)

/// Persistent drift threshold — cycles of continuous drift before Defensive.
/// 持續漂移閾值 — 連續多少週期漂移後升至 Defensive。
pub const PERSISTENT_DRIFT_CYCLES: u32 = 3;

/// Multi-symbol burst threshold — simultaneous drifts before CircuitBreaker + CloseAll.
/// 多 symbol 爆發閾值 — 同時多少個漂移觸發 CB + 全平倉。
pub const BURST_DRIFT_COUNT: usize = 5;

/// Per-(symbol,side) escalation cooldown in ms (30 minutes).
/// 每 (symbol,side) 升級冷卻時間（30 分鐘）。
pub const PER_SYMBOL_COOLDOWN_MS: u64 = 30 * 60 * 1000;

/// Global escalation cooldown in ms (5 minutes, max 1 action).
/// 全局升級冷卻時間（5 分鐘，最多 1 次）。
pub const GLOBAL_COOLDOWN_MS: u64 = 5 * 60 * 1000;

/// Recovery: clean cycles required per tier transition.
/// 恢復：每級轉換需要的乾淨週期數。
pub const RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL: u32 = 30;   // 15 min
pub const RECOVERY_CYCLES_REDUCED_TO_CAUTIOUS: u32 = 20;  // 10 min
pub const RECOVERY_CYCLES_DEFENSIVE_TO_REDUCED: u32 = 20;  // 10 min

/// Recovery: minimum wall-clock time (ms) since last drift per tier transition.
/// 恢復：每級轉換自最後漂移起的最小牆鐘時間。
pub const RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS: u64 = 15 * 60 * 1000;  // 15 min
pub const RECOVERY_WALL_REDUCED_TO_CAUTIOUS_MS: u64 = 10 * 60 * 1000; // 10 min
pub const RECOVERY_WALL_DEFENSIVE_TO_REDUCED_MS: u64 = 10 * 60 * 1000; // 10 min

/// P0-0 RECONCILER-BURST-FIX: startup grace window during which reconciler
/// auto-escalation is suppressed. Baseline drifts observed during engine
/// warmup (legacy Bybit orphans, stale paper_state ghosts from snapshot
/// reload) are cleaned by `orphan_handler` / baseline reseeding, not treated
/// as live drift bursts. The window is long enough (~10 reconcile cycles at
/// 30s interval) for orphan adoption to run to completion and for paper_state
/// to converge to Bybit truth, but short enough not to overlap with the
/// `PER_SYMBOL_COOLDOWN_MS` (30min) or `RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS`
/// (15min) time scales.
/// P0-0：啟動寬限期，期間 reconciler 自動升級被抑制。Warmup 期間看到的
/// baseline drift（legacy Bybit orphan、snapshot 重載的 stale paper_state
/// ghost）由 orphan_handler / baseline 重播種處理，不視為 live drift burst。
/// 選 5min 因為 30s 輪詢 → 約 10 個完整週期，足夠 orphan adoption 跑完、
/// paper_state 收斂到 Bybit 真相，但小於 per-symbol cooldown（30min）與
/// Cautious→Normal recovery wall（15min）時間尺度。
pub const STARTUP_GRACE_MS: u64 = 5 * 60 * 1000; // 5 minutes

// ═══════════════════════════════════════════════════════════════════════════════
// Phase 6: ReconcilerState / 對帳器狀態
// ═══════════════════════════════════════════════════════════════════════════════

/// Action determined by `evaluate_actions()` for the reconciler task to execute.
/// `evaluate_actions()` 決定的動作，由對帳器任務執行。
#[derive(Debug, Clone, PartialEq)]
pub enum ReconcilerAction {
    /// Escalate risk governor (tighten constraints on drift detection).
    /// 升級風控（漂移偵測時收緊約束）。
    Escalate { target: RiskLevel, reason: String },
    /// De-escalate risk governor (auto-recovery after clean cycles).
    /// 降級風控（乾淨週期後自動恢復）。
    DeEscalate { target: RiskLevel, reason: String },
    /// Close all positions (CircuitBreaker level — systemic failure).
    /// 全平倉（CB 級別 — 系統性故障）。
    CloseAll { reason: String },
}

/// Mutable state for the reconciler's auto-contraction logic.
/// Tracks drift streaks, cooldowns, and recovery progress.
/// 對帳器自動降級的可變狀態。追蹤漂移連續計數、冷卻和恢復進度。
pub struct ReconcilerState {
    /// Current baseline (previous cycle's Bybit truth).
    /// 當前基線（上一輪 Bybit 真相）。
    pub baseline: HashMap<String, PositionView>,
    /// Timestamp of last successful REST fetch (ms since epoch). 0 = never.
    /// 上次成功 REST 抓取的時間戳。0 = 從未成功。
    pub last_successful_fetch_ms: u64,
    /// Consecutive REST poll failures (reset on success).
    /// 連續 REST 輪詢失敗次數（成功時重置）。
    pub consecutive_rest_failures: u32,
    /// Per-(symbol|side) consecutive drift cycle count. Key = "BTCUSDT|Buy".
    /// 每 (symbol|side) 連續漂移週期計數。
    pub drift_streak: HashMap<String, u32>,
    /// Consecutive clean cycles since last action-triggering drift.
    /// MinorDrift does NOT reset this counter (noise tolerance).
    /// 自上次 action-triggering 漂移以來的連續乾淨週期數。MinorDrift 不重設。
    pub clean_cycles_since_last_drift: u32,
    /// Timestamp (ms) of last action-triggering drift event.
    /// 上次 action-triggering 漂移事件的時間戳。
    pub last_drift_seen_ms: u64,
    /// Per-(symbol|side) last escalation timestamp (30min cooldown).
    /// 每 (symbol|side) 上次升級時間戳（30min 冷卻）。
    pub last_escalation_ms: HashMap<String, u64>,
    /// Global last escalation timestamp (5min cooldown).
    /// 全局上次升級時間戳（5min 冷卻）。
    pub global_last_escalation_ms: u64,
    /// Risk level before reconciler started escalating (recovery floor).
    /// None if reconciler has not escalated. Auto-recovery will not go below this.
    /// 對帳器開始升級前的風控級別（恢復 floor）。None = 對帳器未曾升級。
    pub pre_escalation_level: Option<RiskLevel>,
    /// FIX-B: Consecutive cycles where actionable_count >= BURST_DRIFT_COUNT.
    /// First burst cycle → Defensive (not CB). Second consecutive → CircuitBreaker.
    /// This prevents a single transient API-sync hiccup (e.g. IPC close_all followed by
    /// delayed Bybit REST, making 5 positions appear to vanish simultaneously) from
    /// immediately tripping CB across all three engines.
    /// FIX-B：連續 actionable_count >= BURST_DRIFT_COUNT 的週期數。
    /// 第一次 burst → Defensive（非 CB），連續第二次 → CircuitBreaker。
    /// 防止單次瞬態 API 同步抖動（如 IPC close_all 後 Bybit REST 延遲）誤觸 CB。
    pub burst_drift_streak: u32,
    /// ORPHAN-ADOPT-1 Phase 1: per-(symbol|side) last-dispatched orphan close
    /// timestamp. Used by `orphan_handler::check_and_stamp_dedup()` to suppress
    /// repeat reduce_only orders within `ORPHAN_CLOSE_DEDUP_MS`.
    /// ORPHAN-ADOPT-1 Phase 1：每 (symbol|side) 上次分發孤兒平倉的時間戳。
    pub pending_orphan_closes: HashMap<String, u64>,
    /// P0-0 RECONCILER-BURST-FIX: timestamp (ms) when the reconciler task
    /// started. 0 = not yet stamped (backward-compatible: `ReconcilerState::new()`
    /// leaves this at 0, so callers that have not opted in still see legacy
    /// behaviour). Used by `evaluate_actions()` and `check_rest_failure_escalation()`
    /// to suppress auto-escalation during the `STARTUP_GRACE_MS` window.
    /// P0-0：對帳器任務啟動時間戳。0 = 未標記（向後兼容）。
    /// 用於 evaluate_actions 與 check_rest_failure_escalation 在
    /// STARTUP_GRACE_MS 寬限期內抑制自動升級。
    pub startup_ms: u64,
}

impl ReconcilerState {
    pub fn new() -> Self {
        Self {
            baseline: HashMap::new(),
            last_successful_fetch_ms: 0,
            consecutive_rest_failures: 0,
            drift_streak: HashMap::new(),
            clean_cycles_since_last_drift: 0,
            last_drift_seen_ms: 0,
            last_escalation_ms: HashMap::new(),
            global_last_escalation_ms: 0,
            pre_escalation_level: None,
            burst_drift_streak: 0,
            pending_orphan_closes: HashMap::new(),
            startup_ms: 0,
        }
    }
}

/// Evaluate drift results and determine actions (escalation / recovery / close-all).
/// Pure function: takes state + current drifts + current risk level, returns actions.
/// 評估漂移結果並決定動作。純函數：接受狀態 + 當前漂移 + 當前風控級別，返回動作。
pub fn evaluate_actions(
    state: &mut ReconcilerState,
    current_level: RiskLevel,
    drifts: &[(String, DriftVerdict)],
    now_ms: u64,
) -> Vec<ReconcilerAction> {
    // -- P0-0 RECONCILER-BURST-FIX: startup grace window --
    // Within `STARTUP_GRACE_MS` of reconciler start, suppress all
    // auto-escalation (burst / persistent / single / recovery dispatch).
    // `orphan_handler` runs upstream of this function and is not affected.
    // Baseline update (mod.rs loop tail) also runs independently and converges
    // `rc_state.baseline` to Bybit truth during the grace period so the post-
    // grace first cycle starts from a clean slate.
    // State counters (drift_streak / burst_drift_streak / clean_cycles) are
    // NOT updated either — pent-up counters would otherwise trigger instantly
    // on grace expiry.
    // ---- 啟動寬限期：STARTUP_GRACE_MS 內抑制所有自動升級/降級，並且不累加
    // 計數器（避免寬限期結束瞬間集中觸發）。orphan_handler 與 baseline 更新
    // 在此函數之外正常運作。
    if state.startup_ms > 0
        && now_ms.saturating_sub(state.startup_ms) < STARTUP_GRACE_MS
    {
        let actionable_count = drifts
            .iter()
            .filter(|(_, v)| {
                matches!(
                    v,
                    DriftVerdict::MajorDrift
                        | DriftVerdict::SideFlip
                        | DriftVerdict::Orphan
                        | DriftVerdict::Ghost
                )
            })
            .count();
        if actionable_count > 0 {
            let grace_remaining_ms =
                STARTUP_GRACE_MS.saturating_sub(now_ms.saturating_sub(state.startup_ms));
            tracing::info!(
                count = actionable_count,
                grace_remaining_ms = grace_remaining_ms,
                "reconciler escalation suppressed during startup grace (P0-0) / 啟動寬限期抑制自動升級"
            );
        }
        return Vec::new();
    }

    let mut actions = Vec::new();

    // -- Collect action-triggering drifts (MinorDrift excluded) --
    // -- 收集觸發動作的漂移（排除 MinorDrift）--
    let actionable: Vec<&(String, DriftVerdict)> = drifts
        .iter()
        .filter(|(_, v)| matches!(v, DriftVerdict::MajorDrift | DriftVerdict::SideFlip | DriftVerdict::Orphan | DriftVerdict::Ghost))
        .collect();

    // -- Update drift streaks --
    // -- 更新漂移連續計數 --
    let drift_keys: std::collections::HashSet<&String> = actionable.iter().map(|(k, _)| k).collect();
    // Increment streaks for drifting slots
    for key in &drift_keys {
        *state.drift_streak.entry((*key).clone()).or_insert(0) += 1;
    }
    // Reset streaks for clean slots (only slots that were previously drifting)
    let stale_keys: Vec<String> = state
        .drift_streak
        .keys()
        .filter(|k| !drift_keys.contains(k))
        .cloned()
        .collect();
    for key in stale_keys {
        state.drift_streak.remove(&key);
    }

    // -- Update clean cycle counter --
    // -- 更新乾淨週期計數器 --
    if actionable.is_empty() {
        state.clean_cycles_since_last_drift += 1;
    } else {
        state.clean_cycles_since_last_drift = 0;
        state.last_drift_seen_ms = now_ms;
    }

    // -- Determine escalation target (severity-ordered) --
    // -- 決定升級目標（按嚴重度排序）--
    let actionable_count = actionable.len();
    let max_streak = state.drift_streak.values().copied().max().unwrap_or(0);

    // FIX-B: Track consecutive burst cycles. First burst → Defensive (warning shot);
    // second consecutive burst → CircuitBreaker. Resets on any non-burst cycle.
    // FIX-B：追蹤連續 burst 週期。第一次 burst → Defensive（預警）；
    // 第二次連續 burst → CircuitBreaker。任何非 burst 週期重置計數。
    if actionable_count >= BURST_DRIFT_COUNT {
        state.burst_drift_streak += 1;
    } else {
        state.burst_drift_streak = 0;
    }

    let escalation_target: Option<RiskLevel> = if actionable_count >= BURST_DRIFT_COUNT {
        if state.burst_drift_streak >= 2 {
            // Two consecutive cycles with 5+ drifts → CircuitBreaker + CloseAll
            // 連續兩個週期 5+ 漂移 → CircuitBreaker + 全平倉
            Some(RiskLevel::CircuitBreaker)
        } else {
            // First burst cycle → Defensive (not yet CB; may be transient API sync hiccup)
            // 第一次 burst 週期 → Defensive（尚未 CB；可能是瞬態 API 同步抖動）
            Some(RiskLevel::Defensive)
        }
    } else if max_streak >= PERSISTENT_DRIFT_CYCLES {
        // Persistent drift ≥3 cycles → Defensive
        // 持續漂移 ≥3 週期 → Defensive
        Some(RiskLevel::Defensive)
    } else if !actionable.is_empty() {
        // Single MajorDrift/Orphan/Ghost → Cautious
        // 單個漂移 → Cautious
        Some(RiskLevel::Cautious)
    } else {
        None
    };

    // -- Apply escalation with cooldown checks --
    // -- 套用升級（含冷卻檢查）--
    if let Some(target) = escalation_target {
        if target > current_level {
            // Cooldown checks:
            //  - CB (burst): bypasses ALL cooldowns (emergency)
            //  - Defensive (persistent drift): bypasses per-symbol cooldown
            //    (QC audit fix: 30min per-symbol cooldown was blocking confirmed
            //     persistent drift from reaching Defensive for 30 minutes)
            //  - Cautious (single drift): full cooldown applies
            // 冷卻檢查：CB 繞過全部 / Defensive 繞過 per-symbol / Cautious 全檢查
            let cooldown_ok = if target >= RiskLevel::CircuitBreaker {
                true // CB always fires / CB 永遠觸發
            } else if target >= RiskLevel::Defensive {
                // Persistent drift → only global cooldown, skip per-symbol
                // 持續漂移 → 只檢全局冷卻，跳過 per-symbol
                now_ms.saturating_sub(state.global_last_escalation_ms) >= GLOBAL_COOLDOWN_MS
            } else {
                let global_ok =
                    now_ms.saturating_sub(state.global_last_escalation_ms) >= GLOBAL_COOLDOWN_MS;
                let per_symbol_ok = actionable.iter().any(|(key, _)| {
                    match state.last_escalation_ms.get(key) {
                        None => true, // never escalated → no cooldown
                        Some(&last) => now_ms.saturating_sub(last) >= PER_SYMBOL_COOLDOWN_MS,
                    }
                });
                global_ok && per_symbol_ok
            };

            if cooldown_ok {
                // NOTE: pre_escalation_level is NOT set here — it is set by
                // the caller after the IPC command is confirmed. This prevents
                // recording a floor for a rejected escalation.
                // 注意：pre_escalation_level 不在此處設置，而是由調用方在
                // IPC 命令確認後設置，避免為被拒絕的升級記錄 floor。

                let reason = if actionable_count >= BURST_DRIFT_COUNT {
                    format!("{actionable_count} simultaneous drifts (burst, streak={})", state.burst_drift_streak)
                } else if max_streak >= PERSISTENT_DRIFT_CYCLES {
                    format!("persistent drift {max_streak} cycles")
                } else {
                    let (key, verdict) = &actionable[0];
                    format!("{}: {}", verdict.kind_str(), key)
                };

                actions.push(ReconcilerAction::Escalate {
                    target,
                    reason: reason.clone(),
                });

                // CloseAll on CircuitBreaker
                if target >= RiskLevel::CircuitBreaker {
                    actions.push(ReconcilerAction::CloseAll { reason });
                }

                // Update cooldowns
                state.global_last_escalation_ms = now_ms;
                for (key, _) in &actionable {
                    state.last_escalation_ms.insert(key.clone(), now_ms);
                }
            }
        }
    }

    // -- Recovery check --
    // -- 恢復檢查 --
    if actionable.is_empty() && state.pre_escalation_level.is_some() {
        let floor = state.pre_escalation_level.unwrap();
        if current_level > floor && current_level < RiskLevel::CircuitBreaker {
            let (required_cycles, required_wall_ms) = recovery_params(current_level);
            let wall_elapsed = now_ms.saturating_sub(state.last_drift_seen_ms);

            if state.clean_cycles_since_last_drift >= required_cycles
                && wall_elapsed >= required_wall_ms
            {
                // Step one level down toward floor
                let target = match current_level {
                    RiskLevel::Defensive => RiskLevel::Reduced,
                    RiskLevel::Reduced => RiskLevel::Cautious,
                    RiskLevel::Cautious => RiskLevel::Normal,
                    _ => return actions, // CB/MR — unreachable due to guard above
                };
                if target >= floor {
                    actions.push(ReconcilerAction::DeEscalate {
                        target,
                        reason: format!(
                            "auto-recovery: {} clean cycles, {}s elapsed",
                            state.clean_cycles_since_last_drift,
                            wall_elapsed / 1000
                        ),
                    });
                    // Reset clean cycle counter for next step
                    state.clean_cycles_since_last_drift = 0;
                    // Clear floor if we've reached it
                    if target == floor {
                        state.pre_escalation_level = None;
                    }
                }
            }
        }
    }

    actions
}

/// Check if consecutive REST failures warrant escalation (6-RC-10 progressive).
/// Tiered: ≥10 → Cautious, ≥30 → Reduced, ≥60 → Defensive.
/// Returns an escalation action if threshold met and current level < target.
/// 檢查連續 REST 失敗是否需要升級（6-RC-10 漸進式）。
/// 三階段：≥10 → Cautious, ≥30 → Reduced, ≥60 → Defensive。
pub fn check_rest_failure_escalation(
    state: &mut ReconcilerState,
    current_level: RiskLevel,
    now_ms: u64,
) -> Option<ReconcilerAction> {
    // P0-0 RECONCILER-BURST-FIX: honour startup grace window — do not
    // escalate on transient REST failures while the engine is still warming
    // up. `consecutive_rest_failures` continues to accumulate so that if the
    // condition persists past the grace window, the normal tiered escalation
    // fires immediately.
    // P0-0：啟動寬限期內不因 REST 失敗升級。consecutive_rest_failures 計數
    // 仍會累加，寬限期結束後若仍失敗立即觸發正常 tier 升級。
    if state.startup_ms > 0
        && now_ms.saturating_sub(state.startup_ms) < STARTUP_GRACE_MS
    {
        return None;
    }

    let failures = state.consecutive_rest_failures;
    // Determine target tier based on failure count (highest matching wins).
    // 根據失敗次數決定目標級別（取最高匹配）。
    let target = if failures >= REST_FAILURE_TIER3_COUNT {
        RiskLevel::Defensive
    } else if failures >= REST_FAILURE_TIER2_COUNT {
        RiskLevel::Reduced
    } else if failures >= REST_FAILURE_TIER1_COUNT {
        RiskLevel::Cautious
    } else {
        return None;
    };

    if current_level >= target {
        return None; // already at or above target / 已在目標級別或更高
    }

    let global_ok =
        now_ms.saturating_sub(state.global_last_escalation_ms) >= GLOBAL_COOLDOWN_MS;
    if global_ok {
        // pre_escalation_level set by caller after IPC confirmation.
        state.global_last_escalation_ms = now_ms;
        return Some(ReconcilerAction::Escalate {
            target,
            reason: format!(
                "{} consecutive REST failures ({}s without position verification)",
                failures,
                failures as u64 * super::RECONCILE_INTERVAL_SECS
            ),
        });
    }
    None
}

/// Return (required_clean_cycles, required_wall_clock_ms) for recovery from a given level.
/// 返回從指定級別恢復所需的（乾淨週期數, 牆鐘毫秒數）。
pub(crate) fn recovery_params(level: RiskLevel) -> (u32, u64) {
    match level {
        RiskLevel::Cautious => (RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL, RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS),
        RiskLevel::Reduced => (RECOVERY_CYCLES_REDUCED_TO_CAUTIOUS, RECOVERY_WALL_REDUCED_TO_CAUTIOUS_MS),
        RiskLevel::Defensive => (RECOVERY_CYCLES_DEFENSIVE_TO_REDUCED, RECOVERY_WALL_DEFENSIVE_TO_REDUCED_MS),
        _ => (u32::MAX, u64::MAX), // CB/MR — never auto-recover
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: build N actionable drifts with unique keys.
    /// 輔助：構建 N 個可觸發動作的漂移。
    fn make_drifts(n: usize, verdict: DriftVerdict) -> Vec<(String, DriftVerdict)> {
        (0..n)
            .map(|i| (format!("SYM{}USDT|Buy", i), verdict.clone()))
            .collect()
    }

    // ── Constants ──

    /// EN: Verify key constant values match design doc.
    /// 中文: 關鍵常量值與設計文檔一致。
    #[test]
    fn test_escalation_constants() {
        assert_eq!(PERSISTENT_DRIFT_CYCLES, 3);
        assert_eq!(BURST_DRIFT_COUNT, 5);
        assert_eq!(GLOBAL_COOLDOWN_MS, 5 * 60 * 1000);
        assert_eq!(PER_SYMBOL_COOLDOWN_MS, 30 * 60 * 1000);
        assert_eq!(REST_FAILURE_TIER1_COUNT, 10);
        assert_eq!(REST_FAILURE_TIER2_COUNT, 30);
        assert_eq!(REST_FAILURE_TIER3_COUNT, 60);
        assert_eq!(STARTUP_GRACE_MS, 5 * 60 * 1000);
    }

    // ── evaluate_actions: escalation ──

    /// EN: Single MajorDrift at Normal → Escalate to Cautious.
    /// 中文: 正常狀態下單個 MajorDrift → 升級到 Cautious。
    #[test]
    fn test_single_drift_escalates_to_cautious() {
        let mut state = ReconcilerState::new();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            ReconcilerAction::Escalate { target, .. } => assert_eq!(*target, RiskLevel::Cautious),
            other => panic!("expected Escalate, got {:?}", other),
        }
    }

    /// EN: Persistent drift (3 cycles) at Normal → Escalate to Defensive.
    /// 中文: 持續漂移 3 週期 → 升級到 Defensive。
    #[test]
    fn test_persistent_drift_escalates_to_defensive() {
        let mut state = ReconcilerState::new();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        // Run 2 cycles to build streak, then 3rd triggers Defensive
        let now = 1_000_000u64;
        let _ = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, now);
        // After first: streak=1, escalated to Cautious, global cooldown set
        let _ = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, now + GLOBAL_COOLDOWN_MS);
        // After second: streak=2, still Cautious (not yet 3)
        let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, now + 2 * GLOBAL_COOLDOWN_MS);
        // After third: streak=3 → Defensive
        assert!(actions.iter().any(|a| matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Defensive)));
    }

    /// EN: First burst (5+ drifts) → Defensive (not CircuitBreaker). FIX-B.
    /// 中文: 首次 burst（5+ 漂移）→ Defensive（非 CB）。FIX-B。
    #[test]
    fn test_burst_first_cycle_defensive_not_cb() {
        let mut state = ReconcilerState::new();
        let drifts = make_drifts(5, DriftVerdict::MajorDrift);
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert_eq!(state.burst_drift_streak, 1);
        // Should escalate to Defensive, not CB
        assert!(actions.iter().any(|a| matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Defensive)));
        assert!(!actions.iter().any(|a| matches!(a, ReconcilerAction::CloseAll { .. })));
    }

    /// EN: Second consecutive burst → CircuitBreaker + CloseAll.
    /// 中文: 第二次連續 burst → CircuitBreaker + 全平倉。
    #[test]
    fn test_burst_second_cycle_circuit_breaker() {
        let mut state = ReconcilerState::new();
        let drifts = make_drifts(5, DriftVerdict::Ghost);
        let now = 1_000_000u64;
        // First burst → Defensive
        let _ = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, now);
        assert_eq!(state.burst_drift_streak, 1);
        // Second burst → CB + CloseAll (CB bypasses all cooldowns)
        let actions = evaluate_actions(&mut state, RiskLevel::Defensive, &drifts, now + 1000);
        assert_eq!(state.burst_drift_streak, 2);
        assert!(actions.iter().any(|a| matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::CircuitBreaker)));
        assert!(actions.iter().any(|a| matches!(a, ReconcilerAction::CloseAll { .. })));
    }

    // ── evaluate_actions: recovery ──

    /// EN: After enough clean cycles + wall time → DeEscalate one level.
    /// 中文: 足夠乾淨週期 + 牆鐘時間後 → 降級一級。
    #[test]
    fn test_recovery_deescalates() {
        let mut state = ReconcilerState::new();
        state.pre_escalation_level = Some(RiskLevel::Normal);
        state.clean_cycles_since_last_drift = RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL;
        state.last_drift_seen_ms = 0; // long ago
        let now = RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS + 1;
        let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &[], now);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            ReconcilerAction::DeEscalate { target, .. } => assert_eq!(*target, RiskLevel::Normal),
            other => panic!("expected DeEscalate, got {:?}", other),
        }
        // Floor cleared since we reached it
        assert!(state.pre_escalation_level.is_none());
    }

    /// EN: MinorDrift does NOT reset clean cycle counter (noise tolerance).
    /// 中文: MinorDrift 不重設乾淨週期計數器（噪聲容忍）。
    #[test]
    fn test_minor_drift_does_not_reset_clean_cycles() {
        let mut state = ReconcilerState::new();
        state.clean_cycles_since_last_drift = 10;
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MinorDrift)];
        let _ = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, 1_000_000);
        // MinorDrift is filtered out of actionable → clean_cycles increments
        assert_eq!(state.clean_cycles_since_last_drift, 11);
    }

    // ── check_rest_failure_escalation ──

    /// EN: 10 consecutive REST failures → Cautious.
    /// 中文: 連續 10 次 REST 失敗 → Cautious。
    #[test]
    fn test_rest_failure_tier1_escalates() {
        let mut state = ReconcilerState::new();
        state.consecutive_rest_failures = REST_FAILURE_TIER1_COUNT;
        let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
        assert!(action.is_some());
        match action.unwrap() {
            ReconcilerAction::Escalate { target, .. } => assert_eq!(target, RiskLevel::Cautious),
            other => panic!("expected Escalate, got {:?}", other),
        }
    }

    /// EN: 9 REST failures (below tier 1) → no action.
    /// 中文: 9 次 REST 失敗（低於閾值）→ 無動作。
    #[test]
    fn test_rest_failure_below_threshold_no_action() {
        let mut state = ReconcilerState::new();
        state.consecutive_rest_failures = 9;
        let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
        assert!(action.is_none());
    }

    /// EN: 60 REST failures → Defensive (highest tier).
    /// 中文: 60 次 REST 失敗 → Defensive（最高級別）。
    #[test]
    fn test_rest_failure_tier3_defensive() {
        let mut state = ReconcilerState::new();
        state.consecutive_rest_failures = REST_FAILURE_TIER3_COUNT;
        let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
        match action.unwrap() {
            ReconcilerAction::Escalate { target, .. } => assert_eq!(target, RiskLevel::Defensive),
            other => panic!("expected Defensive, got {:?}", other),
        }
    }

    // ── recovery_params ──

    /// EN: recovery_params returns correct values per tier.
    /// 中文: recovery_params 每級返回正確值。
    #[test]
    fn test_recovery_params_per_tier() {
        assert_eq!(recovery_params(RiskLevel::Cautious), (30, 15 * 60 * 1000));
        assert_eq!(recovery_params(RiskLevel::Reduced), (20, 10 * 60 * 1000));
        assert_eq!(recovery_params(RiskLevel::Defensive), (20, 10 * 60 * 1000));
        // CB/MR never auto-recover
        assert_eq!(recovery_params(RiskLevel::CircuitBreaker), (u32::MAX, u64::MAX));
    }

    // ── ReconcilerState::new ──

    /// EN: Fresh state has all fields zeroed/empty.
    /// 中文: 新狀態所有字段為零/空。
    #[test]
    fn test_reconciler_state_new_defaults() {
        let state = ReconcilerState::new();
        assert!(state.baseline.is_empty());
        assert_eq!(state.last_successful_fetch_ms, 0);
        assert_eq!(state.consecutive_rest_failures, 0);
        assert!(state.drift_streak.is_empty());
        assert_eq!(state.clean_cycles_since_last_drift, 0);
        assert_eq!(state.last_drift_seen_ms, 0);
        assert!(state.last_escalation_ms.is_empty());
        assert_eq!(state.global_last_escalation_ms, 0);
        assert!(state.pre_escalation_level.is_none());
        assert_eq!(state.burst_drift_streak, 0);
        assert!(state.pending_orphan_closes.is_empty());
        assert_eq!(state.startup_ms, 0);
    }

    // ══════════════════════════════════════════════════════════════════════
    // P0-0 RECONCILER-BURST-FIX: startup grace window tests
    // P0-0：啟動寬限期測試
    // ══════════════════════════════════════════════════════════════════════

    /// EN: Within the startup grace window, a 5-drift burst does NOT escalate
    /// and does NOT update burst_drift_streak / drift_streak / clean_cycles.
    /// 中文: 啟動寬限期內 5-drift burst 不升級、也不累加任何計數器。
    #[test]
    fn test_startup_grace_suppresses_burst_escalation() {
        let mut state = ReconcilerState::new();
        state.startup_ms = 1_000_000;
        let drifts = make_drifts(5, DriftVerdict::Ghost);
        // 1 minute into grace window (grace is 5 min)
        let now = state.startup_ms + 60 * 1000;
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, now);
        assert!(actions.is_empty(), "no actions during grace window");
        assert_eq!(state.burst_drift_streak, 0, "burst streak not updated");
        assert!(state.drift_streak.is_empty(), "drift streak not updated");
        assert_eq!(state.clean_cycles_since_last_drift, 0);
    }

    /// EN: Within grace, persistent drift across multiple cycles does not
    /// accumulate streak (would otherwise trigger Defensive at streak >= 3).
    /// 中文: 寬限期內持續漂移不累加 streak（否則 streak≥3 會升到 Defensive）。
    #[test]
    fn test_startup_grace_suppresses_persistent_drift() {
        let mut state = ReconcilerState::new();
        state.startup_ms = 1_000_000;
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        // 3 cycles all inside grace (30s + 60s + 90s after startup)
        for offset in [30_000u64, 60_000, 90_000] {
            let now = state.startup_ms + offset;
            let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, now);
            assert!(actions.is_empty(), "no action at offset {}ms", offset);
        }
        assert!(state.drift_streak.is_empty(), "streak not accumulated");
    }

    /// EN: Within grace, a single drift does not escalate to Cautious.
    /// 中文: 寬限期內單個 drift 不升到 Cautious。
    #[test]
    fn test_startup_grace_suppresses_single_drift() {
        let mut state = ReconcilerState::new();
        state.startup_ms = 1_000_000;
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Orphan)];
        let now = state.startup_ms + 4 * 60 * 1000; // 4 min in
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, now);
        assert!(actions.is_empty());
    }

    /// EN: After the grace window expires, a fresh burst escalates normally.
    /// Counters start clean (no pent-up accumulation from grace period).
    /// 中文: 寬限期過後新的 burst 正常升級。計數器從零開始（寬限期不累積）。
    #[test]
    fn test_after_grace_burst_escalates_normally() {
        let mut state = ReconcilerState::new();
        state.startup_ms = 1_000_000;
        let startup_ms = state.startup_ms;
        let drifts = make_drifts(5, DriftVerdict::MajorDrift);
        // Cycle inside grace — suppressed
        let _ = evaluate_actions(
            &mut state,
            RiskLevel::Normal,
            &drifts,
            startup_ms + 60 * 1000,
        );
        assert_eq!(state.burst_drift_streak, 0);
        // Cycle just past grace expiry — should escalate to Defensive (first burst)
        let now = startup_ms + STARTUP_GRACE_MS + 1;
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, now);
        assert_eq!(state.burst_drift_streak, 1);
        assert!(actions.iter().any(|a| matches!(
            a,
            ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Defensive
        )));
        assert!(
            !actions.iter().any(|a| matches!(a, ReconcilerAction::CloseAll { .. })),
            "first post-grace burst should not trip CB"
        );
    }

    /// EN: Within grace, REST failure tiers do not escalate.
    /// 中文: 寬限期內 REST 失敗 tier 不升級。
    #[test]
    fn test_startup_grace_suppresses_rest_failures() {
        let mut state = ReconcilerState::new();
        state.startup_ms = 1_000_000;
        state.consecutive_rest_failures = REST_FAILURE_TIER3_COUNT;
        let now = state.startup_ms + 2 * 60 * 1000;
        let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, now);
        assert!(action.is_none(), "REST escalation suppressed during grace");
    }

    /// EN: Legacy callers that do not stamp startup_ms (leave it at 0) keep
    /// pre-P0-0 behaviour — grace is NOT active, burst escalates immediately.
    /// 中文: 舊調用方未標記 startup_ms (留 0) 保持 P0-0 前行為，寬限期不生效。
    #[test]
    fn test_startup_ms_zero_preserves_legacy_behaviour() {
        let mut state = ReconcilerState::new();
        assert_eq!(state.startup_ms, 0);
        let drifts = make_drifts(5, DriftVerdict::Ghost);
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert!(!actions.is_empty(), "legacy callers still get escalation");
        assert_eq!(state.burst_drift_streak, 1);
    }

    /// EN: Exactly at STARTUP_GRACE_MS boundary → grace EXPIRED (`<` not `<=`).
    /// 中文: now_ms - startup_ms == STARTUP_GRACE_MS 邊界時寬限期已結束。
    #[test]
    fn test_startup_grace_boundary_exclusive() {
        let mut state = ReconcilerState::new();
        state.startup_ms = 1_000_000;
        let drifts = make_drifts(5, DriftVerdict::Ghost);
        // Exactly at STARTUP_GRACE_MS → grace has ended → burst escalates
        let now = state.startup_ms + STARTUP_GRACE_MS;
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, now);
        assert!(!actions.is_empty());
        assert!(actions.iter().any(|a| matches!(
            a,
            ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Defensive
        )));
    }
}

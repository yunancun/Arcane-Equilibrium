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
fn recovery_params(level: RiskLevel) -> (u32, u64) {
    match level {
        RiskLevel::Cautious => (RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL, RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS),
        RiskLevel::Reduced => (RECOVERY_CYCLES_REDUCED_TO_CAUTIOUS, RECOVERY_WALL_REDUCED_TO_CAUTIOUS_MS),
        RiskLevel::Defensive => (RECOVERY_CYCLES_DEFENSIVE_TO_REDUCED, RECOVERY_WALL_DEFENSIVE_TO_REDUCED_MS),
        _ => (u32::MAX, u64::MAX), // CB/MR — never auto-recover
    }
}

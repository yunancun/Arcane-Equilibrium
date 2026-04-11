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

    let escalation_target: Option<RiskLevel> = if actionable_count >= BURST_DRIFT_COUNT {
        // 5+ simultaneous drifts → CircuitBreaker + CloseAll
        // 5+ 同時漂移 → CB + 全平倉
        Some(RiskLevel::CircuitBreaker)
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
                    format!("{actionable_count} simultaneous drifts (burst)")
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
                failures as u64 * RECONCILE_INTERVAL_SECS
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
    use crate::tick_pipeline::PipelineCommand;

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

/// Utility: current time in milliseconds since epoch.
/// 工具函數：當前時間（毫秒）。
fn now_ms_util() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
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
    fn side_flip_on_direction_change() {
        let a = pv("BTCUSDT", "Buy", 0.1);
        let b = pv("BTCUSDT", "Sell", 0.1);
        assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::SideFlip);
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
        assert!(!DriftVerdict::Match.is_drift());
        assert!(DriftVerdict::MinorDrift.is_drift());
        assert!(DriftVerdict::MajorDrift.is_drift());
        assert!(DriftVerdict::SideFlip.is_drift());
        assert!(DriftVerdict::Orphan.is_drift());
        assert!(DriftVerdict::Ghost.is_drift());
    }

    // ── Phase 6: evaluate_actions tests ──

    fn make_state() -> ReconcilerState {
        ReconcilerState::new()
    }

    #[test]
    fn phase6_single_major_drift_escalates_to_cautious() {
        let mut state = make_state();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert_eq!(actions.len(), 1);
        assert!(matches!(
            &actions[0],
            ReconcilerAction::Escalate { target: RiskLevel::Cautious, .. }
        ));
    }

    #[test]
    fn phase6_single_ghost_escalates_to_cautious() {
        let mut state = make_state();
        let drifts = vec![("ETHUSDT|Buy".into(), DriftVerdict::Ghost)];
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert_eq!(actions.len(), 1);
        assert!(matches!(
            &actions[0],
            ReconcilerAction::Escalate { target: RiskLevel::Cautious, .. }
        ));
    }

    #[test]
    fn phase6_single_orphan_escalates_to_cautious() {
        let mut state = make_state();
        let drifts = vec![("XRPUSDT|Sell".into(), DriftVerdict::Orphan)];
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert_eq!(actions.len(), 1);
        assert!(matches!(
            &actions[0],
            ReconcilerAction::Escalate { target: RiskLevel::Cautious, .. }
        ));
    }

    #[test]
    fn phase6_minor_drift_no_action() {
        let mut state = make_state();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MinorDrift)];
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert!(actions.is_empty());
    }

    #[test]
    fn phase6_minor_drift_does_not_reset_clean_counter() {
        let mut state = make_state();
        state.clean_cycles_since_last_drift = 10;
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MinorDrift)];
        evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        // MinorDrift should increment clean counter (it's not actionable)
        assert_eq!(state.clean_cycles_since_last_drift, 11);
    }

    #[test]
    fn phase6_persistent_drift_3_cycles_to_defensive() {
        let mut state = make_state();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        let t0 = 100_000_000u64; // large enough base to avoid cooldown from epoch
        // Cycle 1: escalate to Cautious
        let a1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
        assert!(matches!(&a1[0], ReconcilerAction::Escalate { target: RiskLevel::Cautious, .. }));
        // Cycle 2: streak=2 < 3, Cautious→Cautious is no-op
        let a2 = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, t0 + 30_000);
        assert!(a2.is_empty());
        // Cycle 3: streak=3 → Defensive. Persistent drift (≥3 cycles) bypasses
        // per-symbol cooldown (QC audit fix), only needs global 5min cooldown.
        // Use t0 + GLOBAL_COOLDOWN_MS + 1 (not the 30min per-symbol cooldown).
        let a3 = evaluate_actions(
            &mut state,
            RiskLevel::Cautious,
            &drifts,
            t0 + GLOBAL_COOLDOWN_MS + 1,
        );
        assert_eq!(a3.len(), 1);
        assert!(matches!(&a3[0], ReconcilerAction::Escalate { target: RiskLevel::Defensive, .. }));
    }

    #[test]
    fn phase6_burst_5_drifts_to_circuit_breaker_and_close_all() {
        let mut state = make_state();
        let drifts = vec![
            ("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift),
            ("ETHUSDT|Buy".into(), DriftVerdict::Orphan),
            ("XRPUSDT|Sell".into(), DriftVerdict::Ghost),
            ("SOLUSDT|Buy".into(), DriftVerdict::MajorDrift),
            ("DOGEUSDT|Buy".into(), DriftVerdict::Orphan),
        ];
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert_eq!(actions.len(), 2);
        assert!(matches!(
            &actions[0],
            ReconcilerAction::Escalate { target: RiskLevel::CircuitBreaker, .. }
        ));
        assert!(matches!(&actions[1], ReconcilerAction::CloseAll { .. }));
    }

    #[test]
    fn phase6_no_escalation_when_already_at_target() {
        let mut state = make_state();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        // Already at Cautious — single drift targets Cautious, so no escalation
        let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, 1_000_000);
        assert!(actions.is_empty());
    }

    #[test]
    fn phase6_per_symbol_cooldown_blocks_repeat() {
        let mut state = make_state();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        // First escalation
        let a1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert_eq!(a1.len(), 1);
        // Second attempt within 30min cooldown — blocked (target Cautious == current Cautious anyway)
        // But even if we reset to Normal, the per-symbol cooldown should block
        let a2 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000 + GLOBAL_COOLDOWN_MS + 1);
        // per-symbol cooldown of 30min not met
        assert!(a2.is_empty());
    }

    #[test]
    fn phase6_global_cooldown_blocks_rapid_fire() {
        let mut state = make_state();
        let drifts_a = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        let drifts_b = vec![("ETHUSDT|Buy".into(), DriftVerdict::Ghost)];
        // First escalation from drift A
        let a1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts_a, 1_000_000);
        assert_eq!(a1.len(), 1);
        // Different symbol but within global 5min cooldown
        let a2 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts_b, 1_000_000 + 1000);
        assert!(a2.is_empty());
    }

    #[test]
    fn phase6_recovery_cautious_to_normal() {
        let mut state = make_state();
        state.pre_escalation_level = Some(RiskLevel::Normal);
        state.clean_cycles_since_last_drift = RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL;
        // Set last_drift_seen_ms so wall-clock requirement is met
        let now = 1_000_000 + RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS + 1;
        state.last_drift_seen_ms = 1_000_000;
        let drifts: Vec<(String, DriftVerdict)> = vec![];
        let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, now);
        assert_eq!(actions.len(), 1);
        assert!(matches!(
            &actions[0],
            ReconcilerAction::DeEscalate { target: RiskLevel::Normal, .. }
        ));
        // Floor should be cleared since we reached it
        assert!(state.pre_escalation_level.is_none());
    }

    #[test]
    fn phase6_recovery_wall_clock_not_met() {
        let mut state = make_state();
        state.pre_escalation_level = Some(RiskLevel::Normal);
        state.clean_cycles_since_last_drift = RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL;
        state.last_drift_seen_ms = 1_000_000;
        // Wall clock not met (only 5 min elapsed, need 15 min)
        let now = 1_000_000 + 5 * 60 * 1000;
        let drifts: Vec<(String, DriftVerdict)> = vec![];
        let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, now);
        assert!(actions.is_empty());
    }

    #[test]
    fn phase6_recovery_floor_prevents_over_recovery() {
        let mut state = make_state();
        // Drawdown had already pushed to Cautious before reconciler escalated to Reduced
        state.pre_escalation_level = Some(RiskLevel::Cautious);
        state.clean_cycles_since_last_drift = RECOVERY_CYCLES_REDUCED_TO_CAUTIOUS;
        state.last_drift_seen_ms = 1_000_000;
        let now = 1_000_000 + RECOVERY_WALL_REDUCED_TO_CAUTIOUS_MS + 1;
        let drifts: Vec<(String, DriftVerdict)> = vec![];
        let actions = evaluate_actions(&mut state, RiskLevel::Reduced, &drifts, now);
        assert_eq!(actions.len(), 1);
        assert!(matches!(
            &actions[0],
            ReconcilerAction::DeEscalate { target: RiskLevel::Cautious, .. }
        ));
        // Floor cleared — we've reached it
        assert!(state.pre_escalation_level.is_none());
    }

    #[test]
    fn phase6_cb_no_auto_recovery() {
        let mut state = make_state();
        state.pre_escalation_level = Some(RiskLevel::Normal);
        state.clean_cycles_since_last_drift = 100;
        state.last_drift_seen_ms = 0;
        let drifts: Vec<(String, DriftVerdict)> = vec![];
        // CB should never auto-recover
        let actions = evaluate_actions(&mut state, RiskLevel::CircuitBreaker, &drifts, 999_999_999);
        assert!(actions.is_empty());
    }

    #[test]
    fn phase6_rest_failure_tier1_escalation() {
        let mut state = make_state();
        state.consecutive_rest_failures = REST_FAILURE_TIER1_COUNT;
        let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
        assert!(action.is_some());
        assert!(matches!(
            action.unwrap(),
            ReconcilerAction::Escalate { target: RiskLevel::Cautious, .. }
        ));
    }

    #[test]
    fn phase6_rest_failure_tier2_escalation() {
        let mut state = make_state();
        state.consecutive_rest_failures = REST_FAILURE_TIER2_COUNT;
        let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
        assert!(action.is_some());
        assert!(matches!(
            action.unwrap(),
            ReconcilerAction::Escalate { target: RiskLevel::Reduced, .. }
        ));
    }

    #[test]
    fn phase6_rest_failure_tier3_escalation() {
        let mut state = make_state();
        state.consecutive_rest_failures = REST_FAILURE_TIER3_COUNT;
        let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
        assert!(action.is_some());
        assert!(matches!(
            action.unwrap(),
            ReconcilerAction::Escalate { target: RiskLevel::Defensive, .. }
        ));
    }

    #[test]
    fn phase6_rest_failure_no_escalation_when_at_target() {
        let mut state = make_state();
        state.consecutive_rest_failures = REST_FAILURE_TIER1_COUNT;
        let action = check_rest_failure_escalation(&mut state, RiskLevel::Cautious, 1_000_000);
        assert!(action.is_none());
        // Tier2 but already at Reduced → no action
        state.consecutive_rest_failures = REST_FAILURE_TIER2_COUNT;
        let action2 = check_rest_failure_escalation(&mut state, RiskLevel::Reduced, 2_000_000);
        assert!(action2.is_none());
    }

    #[test]
    fn phase6_pre_escalation_level_not_set_by_evaluate_actions() {
        // After Finding 6 fix: evaluate_actions no longer sets pre_escalation_level.
        // The caller (main loop) sets it after successful dispatch.
        // Finding 6 修復：evaluate_actions 不再設置 pre_escalation_level，
        // 由調用方在成功分發後設置。
        let mut state = make_state();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        assert!(state.pre_escalation_level.is_none());
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert!(!actions.is_empty()); // escalation was produced
        assert!(state.pre_escalation_level.is_none()); // but floor NOT set yet
    }

    #[test]
    fn phase6_side_flip_escalates_to_cautious() {
        let mut state = make_state();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::SideFlip)];
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
        assert_eq!(actions.len(), 1);
        assert!(matches!(
            &actions[0],
            ReconcilerAction::Escalate { target: RiskLevel::Cautious, .. }
        ));
    }

    #[test]
    fn phase6_side_flip_kind_str() {
        assert_eq!(DriftVerdict::SideFlip.kind_str(), "side_flip");
    }

    // ── QC audit fix tests ─────────────────────────────────────

    #[test]
    fn phase6_staleness_reseed_triggers_after_long_rest_outage() {
        // 6-RC-9 fix: after a long REST outage (>10min), the first successful
        // fetch should reseed baseline, not classify against stale data.
        // QC 審計修復：長時間 REST 中斷後首次成功應重播種。
        let mut state = make_state();
        // Simulate previous success 15 minutes ago
        let t_prev = 100_000_000u64;
        state.last_successful_fetch_ms = t_prev;
        // Current time is 15 minutes later (> STALENESS_THRESHOLD_MS = 10min)
        let now = t_prev + 15 * 60 * 1000;
        let prev_fetch = state.last_successful_fetch_ms;
        let stale = prev_fetch > 0
            && now.saturating_sub(prev_fetch) > STALENESS_THRESHOLD_MS;
        assert!(stale, "baseline should be detected as stale after 15min gap");
        // After updating, the new value prevents future false staleness
        state.last_successful_fetch_ms = now;
        let stale2 = now.saturating_sub(state.last_successful_fetch_ms) > STALENESS_THRESHOLD_MS;
        assert!(!stale2, "should not be stale immediately after update");
    }

    #[test]
    fn phase6_persistent_drift_bypasses_per_symbol_cooldown() {
        // QC audit fix: persistent drift (streak ≥ 3) to Defensive should
        // bypass per-symbol 30min cooldown, only need global 5min cooldown.
        // QC 審計修復：持續漂移到 Defensive 繞過 per-symbol 冷卻。
        let mut state = make_state();
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
        let t0 = 100_000_000u64;
        // Cycle 1: escalate Normal → Cautious
        evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
        // Cycle 2: streak=2, no-op (target=Cautious = current)
        evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, t0 + 30_000);
        // Cycle 3: streak=3 → Defensive. Only 5min+1ms after cycle 1.
        // This is far less than PER_SYMBOL_COOLDOWN_MS (30min), proving bypass.
        let t3 = t0 + GLOBAL_COOLDOWN_MS + 1;
        assert!(t3 - t0 < PER_SYMBOL_COOLDOWN_MS, "must be within per-symbol cooldown window");
        let a3 = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, t3);
        assert_eq!(a3.len(), 1);
        assert!(matches!(&a3[0], ReconcilerAction::Escalate { target: RiskLevel::Defensive, .. }),
            "persistent drift should reach Defensive despite per-symbol cooldown");
    }
}

//! Supervised-live 5-SoT 對賬 reconciler（spec v2 §2）。
//!
//! MODULE_NOTE
//! 模塊用途：每 30s 對 5 個 Source-of-Truth 做投影對賬，偵測 split-brain。
//!   5 SoT = Rust SM(#1) / Python mirror(#2) / authorization.json(#3) /
//!   lease_transitions(#4) / supervised_live_audit(#5，真值權威)。其餘 4 個為
//!   derived view；任一與 #5 disagree → 升 reconcile_force_close（spec §2.3）。
//! 主要型別/函數：SotSnapshot / ReconcileVerdict / ReconcileDecision /
//!   reconcile_once / project_*。
//! 依賴：state.rs（SmState + audit_action_to_projected_state）。
//! 硬邊界：
//!   - SoT 真值權威固定為 #5 audit table；其餘為 derived（spec §2.2）。
//!   - No-false-positive：連續 2 cycle disagree 才升 force_close；1-cycle →
//!     WARN + pending flag（spec §2.5）。單次抖動不得誤殺 session。
//!   - reconciler **不直接寫 SM**；偵測到 disagree 後由上層透過正常
//!     `try_transition(ReconcileForceClose)` 走 SM path（spec §2.4），本模組只
//!     產生 `ReconcileDecision`，不持有 SM 的可變引用。
//!   - reconciler `should_force_close` 不參考 WS connection state（spec §7.6：
//!     WS reconnect 不觸 SM transition）。

use super::state::{audit_action_to_projected_state, SmState};
use tracing::{error, warn};

/// 5 SoT 在某一 cycle 的快照投影（spec v2 §2.2）。
///
/// 為什麼用 Option：authorization.json 可能不存在；lease/audit 查詢可能空集合
/// （新 session 尚無 audit row）。None 代表「該 SoT 對此 session 無觀測」，
/// 在對賬時與「明確的 state」區別處理（避免把 missing 誤判成 disagree）。
#[derive(Debug, Clone, PartialEq)]
pub struct SotSnapshot {
    /// SoT #1：Rust SM in-process 直讀 state。
    pub rust_sm: Option<SmState>,
    /// SoT #2：Python mirror in-memory/disk state。
    pub python_mirror: Option<SmState>,
    /// SoT #3：authorization.json → 投影（存在+valid+未過期 ⇒ AUTHED-or-later）。
    pub auth_file: Option<SmState>,
    /// SoT #4：lease_transitions → 投影（有 open lease ⇒ ACTIVE_TRADING）。
    pub lease_table: Option<SmState>,
    /// SoT #5（真值權威）：最後一筆 audit action 字串（用 inverse map 投影）。
    pub last_audit_action: Option<String>,
}

impl SotSnapshot {
    /// 把 SoT #5 的最後 audit action 投影成 state（spec §2.2A inverse map）。
    ///
    /// 回 None 代表：無 audit row、或 action=illegal_transition_attempted、
    /// 或 unknown action（後兩者走 fail-closed WARN）。
    pub fn authoritative_state(&self) -> Option<SmState> {
        self.last_audit_action
            .as_deref()
            .and_then(audit_action_to_projected_state)
    }
}

/// 單一 derived view 對賬結果。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ViewAgreement {
    /// 與權威一致，或該 view 無觀測（None）→ 不算 disagree。
    Agree,
    /// 與權威 #5 不一致。
    Disagree,
}

/// 一次 reconcile 的判決（spec §2.2 + §2.5）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ReconcileVerdict {
    /// 全 derived view 與 #5 一致。
    Consistent,
    /// 本 cycle 偵測到 disagree，但尚未達 2-cycle 門檻 → 僅 WARN + pending。
    PendingFirstDisagree { drift_reasons: Vec<String> },
    /// 連續 2 cycle disagree → 必升 reconcile_force_close。
    ForceClose { drift_reasons: Vec<String> },
    /// 無法判定（#5 無權威投影，例如全空或 unknown action）→ fail-closed WARN。
    Indeterminate,
}

/// reconcile 給上層的決策（上層據此決定是否驅動 ReconcileForceClose event）。
///
/// 為什麼回決策而非直接收 SM：spec §2.4 規定 reconciler read-only on derived
/// sources，且強推必須走正常 SM `try_transition` path（才會寫 audit + 維持不變量）。
/// 故本模組只回「該不該 force_close + 原因」，由 SM 持有者執行 transition。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReconcileDecision {
    pub verdict: ReconcileVerdict,
    /// 是否需要上層驅動 reconcile_force_close。
    pub should_force_close: bool,
}

/// reconciler 跨 cycle 的最小狀態（per session）。
///
/// 為什麼只存「上一輪是否 disagree」：No-false-positive 門檻是「連 2 cycle」，
/// 故僅需記 1 bit 歷史 + 上輪原因，避免 reconciler 持有冗餘狀態。
#[derive(Debug, Clone, Default)]
pub struct ReconcileMemory {
    prev_cycle_disagreed: bool,
}

/// 把單一 derived view 與權威 state 對賬。
///
/// 規則：view 為 None（無觀測）→ Agree（不誤判 missing 為 drift）；
/// 有觀測且 != 權威 → Disagree。
fn agree(view: Option<SmState>, authoritative: SmState) -> ViewAgreement {
    match view {
        None => ViewAgreement::Agree,
        Some(s) if s == authoritative => ViewAgreement::Agree,
        Some(_) => ViewAgreement::Disagree,
    }
}

/// 執行一次 reconcile cycle（spec §2.2 + §2.3 + §2.5）。
///
/// 為什麼把 memory 以 &mut 傳入：2-cycle 門檻需跨呼叫保留「上輪是否 disagree」；
/// 由上層（reconcile loop task）持有 per-session memory map，本函數純更新。
///
/// 不變量：
///   - 真值權威 = #5 audit 投影；無法投影（None）→ Indeterminate（fail-closed WARN）。
///   - 1-cycle disagree → PendingFirstDisagree（should_force_close=false）。
///   - 2-cycle 連續 disagree → ForceClose（should_force_close=true）。
pub fn reconcile_once(snapshot: &SotSnapshot, memory: &mut ReconcileMemory) -> ReconcileDecision {
    let authoritative = match snapshot.authoritative_state() {
        Some(s) => s,
        None => {
            // #5 無權威投影：可能全空（新 session）或 unknown/illegal action。
            // fail-closed：不貿然 force_close（避免誤殺），但記 WARN 供 [61] 觀測。
            warn!("supervised-live reconcile: no authoritative audit projection; indeterminate");
            // indeterminate 不累積 disagree 歷史（重置，避免 false 2-cycle）。
            memory.prev_cycle_disagreed = false;
            return ReconcileDecision {
                verdict: ReconcileVerdict::Indeterminate,
                should_force_close: false,
            };
        }
    };

    let mut drift_reasons: Vec<String> = Vec::new();
    if agree(snapshot.rust_sm, authoritative) == ViewAgreement::Disagree {
        drift_reasons.push("rust_sm_drift".to_string());
    }
    if agree(snapshot.python_mirror, authoritative) == ViewAgreement::Disagree {
        drift_reasons.push("python_sm_drift".to_string());
    }
    if agree(snapshot.auth_file, authoritative) == ViewAgreement::Disagree {
        drift_reasons.push("auth_file_drift".to_string());
    }
    if agree(snapshot.lease_table, authoritative) == ViewAgreement::Disagree {
        drift_reasons.push("lease_drift".to_string());
    }

    if drift_reasons.is_empty() {
        memory.prev_cycle_disagreed = false;
        return ReconcileDecision {
            verdict: ReconcileVerdict::Consistent,
            should_force_close: false,
        };
    }

    // 有 disagree：套 No-false-positive 2-cycle 門檻（spec §2.5）。
    if memory.prev_cycle_disagreed {
        // 連續第 2 cycle → 升 force_close。
        error!(
            reasons = ?drift_reasons,
            "supervised-live reconcile: 2-cycle disagree → reconcile_force_close"
        );
        // force_close 後重置歷史（session 即將 CLOSED）。
        memory.prev_cycle_disagreed = false;
        ReconcileDecision {
            verdict: ReconcileVerdict::ForceClose { drift_reasons },
            should_force_close: true,
        }
    } else {
        // 第 1 cycle disagree → WARN + pending，記歷史等下一輪確認。
        warn!(
            reasons = ?drift_reasons,
            "supervised-live reconcile: 1-cycle disagree → pending (no force_close yet)"
        );
        memory.prev_cycle_disagreed = true;
        ReconcileDecision {
            verdict: ReconcileVerdict::PendingFirstDisagree { drift_reasons },
            should_force_close: false,
        }
    }
}

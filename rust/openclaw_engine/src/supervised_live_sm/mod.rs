//! Supervised-live 狀態機核心模組（LG-3 T1）。
//!
//! MODULE_NOTE
//! 模塊用途：LG-3 supervised-live 7-state 狀態機的 Rust 權威實作（SoT #1）。
//!   集中表達 state / event / transition / fail-closed 語意 + 30s 對賬 reconciler，
//!   供 approve / kill / drawdown / lease 等控制面路徑驅動 supervised-live session。
//!   本模組是 control-plane meta state，**不**直接下單、不繞 5-gate live 邊界、
//!   不繞 GovernanceHub Decision Lease（spec v2 §0 + CLAUDE.md §四/§二 根原則 3/4）。
//! 主要型別/函數：
//!   - `SmState` / `SmEvent` / `SmAction` / `SmResult`（state.rs）；
//!   - `try_transition`（transition.rs，純函數查表）；
//!   - `SupervisedLiveSm`（本檔，持有 state + session context + audit sink）；
//!   - `AuditSink` trait（T4 audit writer 接入的 seam，T1 不寫 V104/writer 本體）；
//!   - `Reconciler` / SoT projection（reconciler.rs）。
//! 依賴：
//!   - state.rs / transition.rs / reconciler.rs（本 module 內）；
//!   - crate::common::time::now_ms（audit ts_ms）；
//!   - tracing（log）；serde（Python mirror 對齊）。
//!   - **不**依賴 V104 SQL / supervised_live_audit_writer.rs（那是 T4；本模組只
//!     透過 `AuditSink` trait seam 與其解耦）。
//! 硬邊界：
//!   - 任一非法 transition → fail-closed：留在當前 state + 寫
//!     `illegal_transition_attempted` forensic audit + log ERROR，不 panic、不前進。
//!   - audit emit 失敗（sink 回 Err）→ fail-closed：transition **不** advance，
//!     回 Err（spec v2 §4.4 buffer 滿 fail-closed），維持 audit-first 原子性。
//!   - CLOSED 為 TERMINAL；對 CLOSED 再施事件視為冪等 no-op（kill/reconcile 重入安全）。
//!   - 不觸碰 live_execution_allowed / max_retries / system_mode /
//!     OPENCLAW_ALLOW_MAINNET / authorization.json（0 變動）。

pub mod reconciler;
pub mod state;
pub mod transition;

#[cfg(test)]
mod tests;

pub use reconciler::{ReconcileDecision, ReconcileVerdict, SotSnapshot};
pub use state::{
    audit_action_to_projected_state, IllegalTransitionError, SmAction, SmEvent, SmResult, SmState,
};
pub use transition::{try_transition, TransitionOutcome};

use tracing::{error, info, warn};

/// 一筆待寫入的 audit row（spec v2 §4.1 欄位子集，T1 只填能在 SM 內決定的欄）。
///
/// 為什麼是 T1 定義的中立結構：T1 產生 transition 語意（action / src / dst /
/// result / reason_codes / session/request id / ts），T4 的 writer 負責把它對齊
/// V104 的 21 欄並 INSERT。T1 不知道 PG schema 細節 —— 兩端透過此結構 + `AuditSink`
/// trait seam 解耦（避免 T1 依賴 T4 的 SQL/writer 本體）。
#[derive(Debug, Clone, PartialEq)]
pub struct AuditRow {
    /// audit action（17 enum 之一；對齊 V104 CHECK）。
    pub action: SmAction,
    /// transition src state（首列為 None）。
    pub src_state: Option<SmState>,
    /// transition dst state。
    pub dst_state: SmState,
    /// result：ok / rejected / forced。
    pub result: SmResult,
    /// emit ms epoch（crate::common::time::now_ms）。
    pub ts_ms: i64,
    /// "sess:" + uuid；REGISTERED/REJECTED 前可能為 None。
    pub session_id: Option<String>,
    /// "req:" + uuid。
    pub request_id: Option<String>,
    /// 綁定的 decision lease id（ACTIVE_TRADING 後才有）。
    pub decision_lease_id: Option<String>,
    /// reason codes（rejected / forced 路徑填）。
    pub reason_codes: Vec<String>,
}

/// audit 寫入 seam —— T4 的 supervised_live_audit_writer 實作此 trait。
///
/// 為什麼用 trait 而非直接呼叫 writer：T1（SM core）與 T4（V104 + writer）並行
/// 開發且檔案零 overlap；T1 不可依賴尚未存在的 V104 writer 型別。此 trait 是兩者
/// 的契約 seam —— T1 在 transition 時呼叫 `emit`，T4 land 後提供實作（mpsc → PG）。
/// 測試以 `MockAuditSink` 注入（無 PG / 無 file）。
///
/// 不變量：`emit` 回 Err → SM 視為 audit-first 失敗 → transition fail-closed 不前進。
pub trait AuditSink: Send + Sync {
    /// 寫一筆 audit row。回 Err 代表寫入通道不可用（buffer 滿 / channel closed）。
    fn emit(&self, row: &AuditRow) -> Result<(), AuditEmitError>;
}

/// audit emit 失敗原因（fail-closed 觸發點）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AuditEmitError {
    /// 寫入通道已滿（spec v2 §4.4 try_send Err → fail-closed）。
    ChannelFull,
    /// 寫入通道已關閉（engine shutdown 中）。
    ChannelClosed,
}

impl std::fmt::Display for AuditEmitError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            AuditEmitError::ChannelFull => f.write_str("audit channel full"),
            AuditEmitError::ChannelClosed => f.write_str("audit channel closed"),
        }
    }
}

impl std::error::Error for AuditEmitError {}

/// SM transition 對外的失敗總類型。
#[derive(Debug)]
pub enum SmTransitionError {
    /// 非法 (src, event)（spec v2 §1.3）。
    Illegal(IllegalTransitionError),
    /// audit emit 失敗 → transition 不前進（spec v2 §4.4 fail-closed）。
    AuditFailed(AuditEmitError),
}

impl std::fmt::Display for SmTransitionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SmTransitionError::Illegal(e) => write!(f, "{e}"),
            SmTransitionError::AuditFailed(e) => write!(f, "audit-first failed: {e}"),
        }
    }
}

impl std::error::Error for SmTransitionError {}

/// 單一 supervised-live session 的狀態機持有者（SoT #1）。
///
/// 為什麼每 session 一個實例：state 與 session_id / request_id / lease 綁定；
/// 多 session 並行時各自獨立 transition，reconciler 逐 session 對賬。
/// 生命週期：approve 成功時建立（REGISTERED→PRE_AUTH 起點），CLOSED 後保留供
/// reconciler 最後一輪對賬與 GUI 顯示，之後由上層 registry 清理。
pub struct SupervisedLiveSm {
    state: SmState,
    session_id: Option<String>,
    request_id: Option<String>,
    decision_lease_id: Option<String>,
    /// audit seam（T4 注入；測試注入 mock）。
    audit_sink: std::sync::Arc<dyn AuditSink>,
}

impl SupervisedLiveSm {
    /// 建立新 SM，初始態 DRAFT（spec v2 §1：Python-only 起手態）。
    ///
    /// 為什麼從 DRAFT 起：DRAFT 是 0 DB / 0 audit 的 in-memory 起點；
    /// 真正寫 audit 的第一筆是 DRAFT→REGISTERED（request_registered）。
    pub fn new(audit_sink: std::sync::Arc<dyn AuditSink>) -> Self {
        Self {
            state: SmState::Draft,
            session_id: None,
            request_id: None,
            decision_lease_id: None,
            audit_sink,
        }
    }

    /// 當前 state（reconciler SoT #1 直讀）。
    pub fn state(&self) -> SmState {
        self.state
    }

    pub fn session_id(&self) -> Option<&str> {
        self.session_id.as_deref()
    }

    pub fn request_id(&self) -> Option<&str> {
        self.request_id.as_deref()
    }

    pub fn decision_lease_id(&self) -> Option<&str> {
        self.decision_lease_id.as_deref()
    }

    /// 設定 session/request 識別碼（approve 路徑在 ApprovalGranted 前注入）。
    ///
    /// 為什麼分開設：transition 表本身不攜帶載荷；識別碼由控制面路徑在驅動
    /// 對應 event 前先寫入，使 audit row 能填 session_id / request_id。
    pub fn bind_identity(&mut self, session_id: Option<String>, request_id: Option<String>) {
        if let Some(s) = session_id {
            self.session_id = Some(s);
        }
        if let Some(r) = request_id {
            self.request_id = Some(r);
        }
    }

    /// 綁定 decision lease（LeaseAcquired 前注入；用於 audit decision_lease_id）。
    pub fn bind_lease(&mut self, lease_id: String) {
        self.decision_lease_id = Some(lease_id);
    }

    /// 驅動一個事件：查表 → audit-first 寫入 → 成功才 mutate state。
    ///
    /// 為什麼 audit-first：spec v2 §4.3 outbox —— 先把 audit row 推進 sink，
    /// 成功才前進 state；sink 失敗則 transition 不 advance（fail-closed），
    /// 保證「state 變更必有對應 audit」「無 audit 必不變 state」的原子不變量。
    ///
    /// 非法 transition：寫 `illegal_transition_attempted` forensic（best-effort，
    /// 即使該 forensic 也寫失敗也不前進）+ log ERROR，留在 src，回
    /// `SmTransitionError::Illegal`。
    pub fn drive(
        &mut self,
        event: SmEvent,
        reason_codes: Vec<String>,
    ) -> Result<SmState, SmTransitionError> {
        // CLOSED 為 TERMINAL：對其再施 kill/reconcile 等視為冪等 no-op，避免重複副作用。
        // 為什麼 no-op 而非 Err：kill API 與 IPC 雙路徑、reconciler 重入都可能對已
        // CLOSED session 再次觸發（spec §6 dual-path idempotent）；回 Ok(Closed) 讓
        // 呼叫端冪等，但不寫重複 audit。
        if self.state.is_terminal() && is_closing_event(event) {
            info!(
                session = self.session_id.as_deref().unwrap_or("<none>"),
                event = event.as_str(),
                "supervised-live SM already CLOSED; closing event treated as idempotent no-op"
            );
            return Ok(self.state);
        }

        match try_transition(self.state, event, self.session_id.as_deref()) {
            Ok(outcome) => {
                let row = AuditRow {
                    action: outcome.action,
                    src_state: Some(self.state),
                    dst_state: outcome.dst,
                    result: outcome.result,
                    ts_ms: now_ms_i64(),
                    session_id: self.session_id.clone(),
                    request_id: self.request_id.clone(),
                    decision_lease_id: self.decision_lease_id.clone(),
                    reason_codes,
                };
                // audit-first：失敗則不前進（fail-closed）。
                if let Err(e) = self.audit_sink.emit(&row) {
                    error!(
                        session = self.session_id.as_deref().unwrap_or("<none>"),
                        event = event.as_str(),
                        error = %e,
                        "supervised-live audit emit failed; transition NOT advanced (fail-closed)"
                    );
                    return Err(SmTransitionError::AuditFailed(e));
                }
                let prev = self.state;
                self.state = outcome.dst;
                info!(
                    session = self.session_id.as_deref().unwrap_or("<none>"),
                    src = prev.as_str(),
                    dst = self.state.as_str(),
                    event = event.as_str(),
                    action = outcome.action.as_str(),
                    "supervised-live SM transition"
                );
                Ok(self.state)
            }
            Err(illegal) => {
                // 寫 forensic（best-effort；即使失敗也不前進）。
                let forensic = AuditRow {
                    action: SmAction::IllegalTransitionAttempted,
                    src_state: Some(self.state),
                    dst_state: self.state, // 不變
                    result: SmResult::Rejected,
                    ts_ms: now_ms_i64(),
                    session_id: self.session_id.clone(),
                    request_id: self.request_id.clone(),
                    decision_lease_id: self.decision_lease_id.clone(),
                    reason_codes: vec![format!(
                        "from_{}_event_{}",
                        self.state.as_str(),
                        event.as_str()
                    )],
                };
                if let Err(e) = self.audit_sink.emit(&forensic) {
                    warn!(
                        session = self.session_id.as_deref().unwrap_or("<none>"),
                        error = %e,
                        "forensic illegal_transition audit also failed to emit"
                    );
                }
                error!(
                    "illegal supervised-live transition rejected: {} (fail-closed, stayed at {})",
                    illegal,
                    self.state.as_str()
                );
                Err(SmTransitionError::Illegal(illegal))
            }
        }
    }
}

/// 取當前毫秒 epoch（i64，audit ts_ms 用）。
///
/// 為什麼自帶而不直接呼 `crate::common::time::now_ms`：該 helper 因 cfg 在
/// i64 / u64 兩種簽名間切換，直接相依會在某些 build profile 觸發型別不符或
/// clippy unnecessary_cast。本 helper 自 SystemTime 直算 i64，與 audit row 欄位
/// （BIGINT）對齊且 clippy-clean、無外部耦合。
fn now_ms_i64() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

/// 是否為「收斂到 CLOSED」的事件（kill/duration/reconcile/approval-reject 等）。
///
/// 為什麼需要：判斷對已 CLOSED session 的事件是否可冪等 no-op；只有這些
/// closing 事件對 TERMINAL 態安全（其餘事件對 CLOSED 仍應 fail-loud 為非法）。
fn is_closing_event(event: SmEvent) -> bool {
    matches!(
        event,
        SmEvent::KillApi
            | SmEvent::KillIpc
            | SmEvent::SessionMaxDuration
            | SmEvent::ReconcileForceClose
            | SmEvent::ApprovalRejected
            | SmEvent::RequestExpired
            | SmEvent::AuthFileInvalid
            | SmEvent::AuthRecheckFail
            | SmEvent::TransitionalClose
    )
}

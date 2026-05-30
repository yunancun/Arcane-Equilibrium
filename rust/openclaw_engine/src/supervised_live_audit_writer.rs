// MODULE_NOTE
// 模塊用途：P0-LG-3 supervised-live 不可變稽核軌跡的 Rust writer（append-only emitter）。
//           supervised SM 的每一筆狀態轉換 / approval 決策 / lease 生命週期 /
//           kill 路徑 / drawdown breach / reconcile 強平，都經此 sink 落一筆到
//           learning.supervised_live_audit（V104）。
// 主要類/函數：
//   - trait SupervisedLiveAuditWriter：寫一筆 audit 的抽象 seam（測試可注入 mock）。
//   - struct SupervisedLiveAuditEvent：對齊 V104 21-column 的可寫子集 + builder。
//   - enum AuditAction / AuditResult / AuditEngineMode：與 V104 CHECK 逐字對齊的枚舉。
//   - struct PgSupervisedLiveAuditWriter：sqlx PgPool 實作，參數化 INSERT。
//   - enum SupervisedAuditError：寫入錯誤型別。
// 依賴：sqlx(postgres)、serde_json::Value、async-trait。
// 硬邊界：
//   1) append-only：只 INSERT，無 UPDATE/DELETE（root principle §1 單一寫入口 / §8 可重建）。
//   2) fail-loud：emit 失敗回 Err，絕不 swallow。呼叫端依此 fail-closed
//      （audit 遺失 = 審計斷鏈，合規不可接受）。
//   3) engine_mode 限 Live / LiveDemo —— 拒 Paper（LiveDemo 不因 endpoint 降級）。
//      Rust 端先擋（無 Paper variant），DB CHECK 是最後防線。
//   4) 所有 INSERT 走參數化 bind，禁字串拼接（防 SQL injection）。
//   5) 不碰 supervised SM 核心 / reconciler / position_manager / live_execution_allowed /
//      max_retries / authorization.json（那些非 T4 範圍）。

use sqlx::postgres::PgPool;

/// audit action（對齊 V104 chk_supervised_live_audit_action 17-enum）。
///
/// 為什麼用 enum 而非裸字串：在 Rust 端把枚舉約束住，拼錯字串不會等到 runtime
/// DB check_violation 才爆（fail 點越早越好）。as_str 與 V104 CHECK 值嚴格逐字對齊。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuditAction {
    RequestRegistered,
    ApprovalGranted,
    ApprovalRejected,
    ExpiredPreAuth,
    AuthFileObserved,
    AuthFileInvalid,
    LeaseAcquired,
    LeaseReleased,
    AuthRecheckFail,
    DrawdownBreach,
    DrawdownCloseComplete,
    KillApi,
    KillIpc,
    SessionMaxDuration,
    ReconcileForceClose,
    IllegalTransitionAttempted,
    SessionClosed,
}

impl AuditAction {
    pub fn as_str(self) -> &'static str {
        match self {
            AuditAction::RequestRegistered => "request_registered",
            AuditAction::ApprovalGranted => "approval_granted",
            AuditAction::ApprovalRejected => "approval_rejected",
            AuditAction::ExpiredPreAuth => "expired_pre_auth",
            AuditAction::AuthFileObserved => "auth_file_observed",
            AuditAction::AuthFileInvalid => "auth_file_invalid",
            AuditAction::LeaseAcquired => "lease_acquired",
            AuditAction::LeaseReleased => "lease_released",
            AuditAction::AuthRecheckFail => "auth_recheck_fail",
            AuditAction::DrawdownBreach => "drawdown_breach",
            AuditAction::DrawdownCloseComplete => "drawdown_close_complete",
            AuditAction::KillApi => "kill_api",
            AuditAction::KillIpc => "kill_ipc",
            AuditAction::SessionMaxDuration => "session_max_duration",
            AuditAction::ReconcileForceClose => "reconcile_force_close",
            AuditAction::IllegalTransitionAttempted => "illegal_transition_attempted",
            AuditAction::SessionClosed => "session_closed",
        }
    }
}

/// audit result（對齊 V104 chk_supervised_live_audit_result 3-enum）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuditResult {
    Ok,
    Rejected,
    Forced,
}

impl AuditResult {
    pub fn as_str(self) -> &'static str {
        match self {
            AuditResult::Ok => "ok",
            AuditResult::Rejected => "rejected",
            AuditResult::Forced => "forced",
        }
    }
}

/// engine_mode（對齊 V104 chk_supervised_live_audit_engine_mode 2-enum）。
///
/// 為什麼無 Paper variant：supervised-live 是 Live 管線；LiveDemo 走 demo endpoint
/// 但授權 / TTL / 風控 / audit 按 Live 嚴格標準（feedback_live_no_degradation_by_endpoint）。
/// Paper 不得進此 audit；Rust 端用型別系統根除，DB CHECK 為最後防線。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuditEngineMode {
    Live,
    LiveDemo,
}

impl AuditEngineMode {
    pub fn as_str(self) -> &'static str {
        match self {
            AuditEngineMode::Live => "live",
            AuditEngineMode::LiveDemo => "live_demo",
        }
    }
}

/// 一筆待寫入的 supervised audit 事件（對齊 V104 21-column 可寫子集）。
///
/// 為什麼 builder：多數事件只填部分可空欄位（例 request_registered 無 session_id /
/// decision_lease_id）。必填項在 new() 強制，可空項用 with_* 鏈式填，未填落 NULL/DEFAULT。
#[derive(Debug, Clone)]
pub struct SupervisedLiveAuditEvent {
    // 必填（對齊 V104 NOT NULL，無 server-side default 的）
    pub event_id: String,
    pub ts_ms: i64,
    pub operator_id: String,
    pub request_id: String,
    pub engine_mode: AuditEngineMode,
    pub action: AuditAction,
    pub dst_state: String,
    pub result: AuditResult,
    // 可空 / 有 DEFAULT
    pub session_id: Option<String>,
    pub decision_lease_id: Option<String>,
    pub symbols: Vec<String>,
    pub strategies: Vec<String>,
    pub risk_limits: serde_json::Value,
    pub src_state: Option<String>,
    pub reason_codes: Vec<String>,
    pub alpha_source_id: Option<String>,
    pub cohort_ref: Option<String>,
    pub strategy_alpha_score: Option<f64>,
    pub regime_tag: Option<String>,
    pub payload: serde_json::Value,
}

impl SupervisedLiveAuditEvent {
    /// 建一筆事件，必填 8 項；其餘可空 / DEFAULT 預設。
    ///
    /// 不變量：ts_ms 必 > 0（V104 C4 CHECK），dst_state 不可空白；呼叫端應傳有效值。
    #[allow(clippy::too_many_arguments)]
    pub fn new(
        event_id: impl Into<String>,
        ts_ms: i64,
        operator_id: impl Into<String>,
        request_id: impl Into<String>,
        engine_mode: AuditEngineMode,
        action: AuditAction,
        dst_state: impl Into<String>,
        result: AuditResult,
    ) -> Self {
        Self {
            event_id: event_id.into(),
            ts_ms,
            operator_id: operator_id.into(),
            request_id: request_id.into(),
            engine_mode,
            action,
            dst_state: dst_state.into(),
            result,
            session_id: None,
            decision_lease_id: None,
            symbols: Vec::new(),
            strategies: Vec::new(),
            risk_limits: serde_json::json!({}),
            src_state: None,
            reason_codes: Vec::new(),
            alpha_source_id: None,
            cohort_ref: None,
            strategy_alpha_score: None,
            regime_tag: None,
            payload: serde_json::json!({}),
        }
    }

    pub fn with_session_id(mut self, s: impl Into<String>) -> Self {
        self.session_id = Some(s.into());
        self
    }
    pub fn with_decision_lease_id(mut self, s: impl Into<String>) -> Self {
        self.decision_lease_id = Some(s.into());
        self
    }
    pub fn with_symbols(mut self, v: Vec<String>) -> Self {
        self.symbols = v;
        self
    }
    pub fn with_strategies(mut self, v: Vec<String>) -> Self {
        self.strategies = v;
        self
    }
    pub fn with_risk_limits(mut self, v: serde_json::Value) -> Self {
        self.risk_limits = v;
        self
    }
    pub fn with_src_state(mut self, s: impl Into<String>) -> Self {
        self.src_state = Some(s.into());
        self
    }
    pub fn with_reason_codes(mut self, v: Vec<String>) -> Self {
        self.reason_codes = v;
        self
    }
    pub fn with_alpha_source_id(mut self, s: impl Into<String>) -> Self {
        self.alpha_source_id = Some(s.into());
        self
    }
    pub fn with_cohort_ref(mut self, s: impl Into<String>) -> Self {
        self.cohort_ref = Some(s.into());
        self
    }
    pub fn with_strategy_alpha_score(mut self, v: f64) -> Self {
        self.strategy_alpha_score = Some(v);
        self
    }
    pub fn with_regime_tag(mut self, s: impl Into<String>) -> Self {
        self.regime_tag = Some(s.into());
        self
    }
    pub fn with_payload(mut self, v: serde_json::Value) -> Self {
        self.payload = v;
        self
    }
}

/// audit 寫入錯誤。
///
/// 為什麼分 Validation 與 Db：呼叫端對「資料不合法」與「DB 不可用」可做不同處置，
/// 但兩者都必 fail-loud（不可降級為靜默丟棄；audit 遺失 = 合規斷鏈）。
#[derive(Debug)]
pub enum SupervisedAuditError {
    /// 寫入前本地校驗失敗（例 ts_ms <= 0 / dst_state 空白）。
    Validation(String),
    /// DB 層失敗（連線 / 約束違反 / 逾時）。
    Db(sqlx::Error),
}

impl std::fmt::Display for SupervisedAuditError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SupervisedAuditError::Validation(m) => write!(f, "supervised audit 校驗失敗: {m}"),
            SupervisedAuditError::Db(e) => write!(f, "supervised audit DB 寫入失敗: {e}"),
        }
    }
}

impl std::error::Error for SupervisedAuditError {}

impl From<sqlx::Error> for SupervisedAuditError {
    fn from(e: sqlx::Error) -> Self {
        SupervisedAuditError::Db(e)
    }
}

/// supervised audit 寫入抽象 seam。
///
/// 為什麼用 trait（對齊 notification_failsafe::FailsafeAuditEmitter 範式）：核心 SM /
/// 決策路徑只依賴此介面；測試注入記憶體 mock 不需真 PG，runtime 注入 Pg 實作。
/// 同時保留 fail-loud 契約（emit 回 Result）。
#[async_trait::async_trait]
pub trait SupervisedLiveAuditWriter: Send + Sync {
    /// 寫一筆 audit event（append-only INSERT）。
    ///
    /// 不變量：失敗必回 Err，呼叫端 fail-closed（不可忽略回傳）。
    async fn emit(&self, event: SupervisedLiveAuditEvent) -> Result<(), SupervisedAuditError>;
}

/// PgSupervisedLiveAuditWriter — sqlx 實作，INSERT into learning.supervised_live_audit。
pub struct PgSupervisedLiveAuditWriter {
    pool: PgPool,
}

impl PgSupervisedLiveAuditWriter {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    /// 寫入前本地校驗。
    ///
    /// 為什麼在 Rust 端先擋：DB CHECK 是最後防線，但提早擋住 ts_ms<=0 / 空白 dst_state
    /// 可給更清楚錯誤訊息且省一次 DB 往返。engine_mode / action / result 由型別系統保證合法，
    /// 無需在此再校驗。
    fn validate(event: &SupervisedLiveAuditEvent) -> Result<(), SupervisedAuditError> {
        if event.ts_ms <= 0 {
            return Err(SupervisedAuditError::Validation(format!(
                "ts_ms 必須 > 0（違反 chk_supervised_live_audit_ts_ms_positive），實得 {}",
                event.ts_ms
            )));
        }
        if event.dst_state.trim().is_empty() {
            return Err(SupervisedAuditError::Validation(
                "dst_state 不可空白（V104 NOT NULL）".to_string(),
            ));
        }
        if event.event_id.trim().is_empty() {
            return Err(SupervisedAuditError::Validation(
                "event_id 不可空白（V104 PK NOT NULL）".to_string(),
            ));
        }
        Ok(())
    }
}

#[async_trait::async_trait]
impl SupervisedLiveAuditWriter for PgSupervisedLiveAuditWriter {
    async fn emit(&self, event: SupervisedLiveAuditEvent) -> Result<(), SupervisedAuditError> {
        Self::validate(&event)?;

        // 參數化 INSERT（禁字串拼接）。created_at 由 DB DEFAULT NOW() 生成（hypertable partition）。
        // append-only：只 INSERT，不 ON CONFLICT UPDATE（audit 不可變）。
        // 欄位順序嚴格對齊 V104 column order（event_id..payload；created_at 省略走 DEFAULT）。
        sqlx::query(
            "INSERT INTO learning.supervised_live_audit \
             (event_id, ts_ms, operator_id, session_id, request_id, decision_lease_id, \
              engine_mode, symbols, strategies, risk_limits, action, src_state, dst_state, \
              result, reason_codes, alpha_source_id, cohort_ref, strategy_alpha_score, \
              regime_tag, payload) \
             VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20)",
        )
        .bind(&event.event_id)
        .bind(event.ts_ms)
        .bind(&event.operator_id)
        .bind(&event.session_id)
        .bind(&event.request_id)
        .bind(&event.decision_lease_id)
        .bind(event.engine_mode.as_str())
        .bind(&event.symbols)
        .bind(&event.strategies)
        .bind(&event.risk_limits)
        .bind(event.action.as_str())
        .bind(&event.src_state)
        .bind(&event.dst_state)
        .bind(event.result.as_str())
        .bind(&event.reason_codes)
        .bind(&event.alpha_source_id)
        .bind(&event.cohort_ref)
        .bind(event.strategy_alpha_score)
        .bind(&event.regime_tag)
        .bind(&event.payload)
        .execute(&self.pool)
        .await?;

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn action_str_matches_v104_check_17_enum() {
        // 不變量：as_str 必與 V104 chk_supervised_live_audit_action 17-enum 逐字對齊。
        assert_eq!(AuditAction::RequestRegistered.as_str(), "request_registered");
        assert_eq!(AuditAction::ApprovalGranted.as_str(), "approval_granted");
        assert_eq!(AuditAction::ApprovalRejected.as_str(), "approval_rejected");
        assert_eq!(AuditAction::ExpiredPreAuth.as_str(), "expired_pre_auth");
        assert_eq!(AuditAction::AuthFileObserved.as_str(), "auth_file_observed");
        assert_eq!(AuditAction::AuthFileInvalid.as_str(), "auth_file_invalid");
        assert_eq!(AuditAction::LeaseAcquired.as_str(), "lease_acquired");
        assert_eq!(AuditAction::LeaseReleased.as_str(), "lease_released");
        assert_eq!(AuditAction::AuthRecheckFail.as_str(), "auth_recheck_fail");
        assert_eq!(AuditAction::DrawdownBreach.as_str(), "drawdown_breach");
        assert_eq!(
            AuditAction::DrawdownCloseComplete.as_str(),
            "drawdown_close_complete"
        );
        assert_eq!(AuditAction::KillApi.as_str(), "kill_api");
        assert_eq!(AuditAction::KillIpc.as_str(), "kill_ipc");
        assert_eq!(
            AuditAction::SessionMaxDuration.as_str(),
            "session_max_duration"
        );
        assert_eq!(
            AuditAction::ReconcileForceClose.as_str(),
            "reconcile_force_close"
        );
        assert_eq!(
            AuditAction::IllegalTransitionAttempted.as_str(),
            "illegal_transition_attempted"
        );
        assert_eq!(AuditAction::SessionClosed.as_str(), "session_closed");
    }

    #[test]
    fn result_str_matches_v104_check() {
        assert_eq!(AuditResult::Ok.as_str(), "ok");
        assert_eq!(AuditResult::Rejected.as_str(), "rejected");
        assert_eq!(AuditResult::Forced.as_str(), "forced");
    }

    #[test]
    fn engine_mode_str_matches_v104_check_no_paper() {
        // engine_mode 限 live / live_demo —— 型別系統根除 paper（LiveDemo 不降級硬邊界）。
        assert_eq!(AuditEngineMode::Live.as_str(), "live");
        assert_eq!(AuditEngineMode::LiveDemo.as_str(), "live_demo");
    }

    #[test]
    fn builder_required_fields_and_defaults() {
        let ev = SupervisedLiveAuditEvent::new(
            "evt:abc123",
            1_730_000_000_000,
            "op-1",
            "req:uuid",
            AuditEngineMode::LiveDemo,
            AuditAction::RequestRegistered,
            "REGISTERED",
            AuditResult::Ok,
        );
        assert_eq!(ev.event_id, "evt:abc123");
        assert_eq!(ev.engine_mode, AuditEngineMode::LiveDemo);
        // session_id / decision_lease_id 預設 None（REGISTERED 階段 session 未建）。
        assert!(ev.session_id.is_none());
        assert!(ev.decision_lease_id.is_none());
        // array 預設空，JSONB 預設 {}。
        assert!(ev.symbols.is_empty());
        assert_eq!(ev.risk_limits, serde_json::json!({}));
    }

    #[test]
    fn builder_chains_optional_fields() {
        let ev = SupervisedLiveAuditEvent::new(
            "evt:x",
            1,
            "op",
            "req",
            AuditEngineMode::Live,
            AuditAction::LeaseAcquired,
            "ACTIVE_TRADING",
            AuditResult::Ok,
        )
        .with_session_id("sess-1")
        .with_decision_lease_id("lease-1")
        .with_symbols(vec!["BTCUSDT".to_string()])
        .with_src_state("AWAIT_AUTH");
        assert_eq!(ev.session_id.as_deref(), Some("sess-1"));
        assert_eq!(ev.decision_lease_id.as_deref(), Some("lease-1"));
        assert_eq!(ev.src_state.as_deref(), Some("AWAIT_AUTH"));
        assert_eq!(ev.symbols, vec!["BTCUSDT".to_string()]);
    }

    #[test]
    fn validate_rejects_nonpositive_ts_ms() {
        // fail-loud：ts_ms<=0 在 Rust 端就擋（對齊 V104 C4 CHECK ts_ms>0）。
        let ev = SupervisedLiveAuditEvent::new(
            "evt:x",
            0,
            "op",
            "req",
            AuditEngineMode::Live,
            AuditAction::RequestRegistered,
            "S",
            AuditResult::Ok,
        );
        let r = PgSupervisedLiveAuditWriter::validate(&ev);
        assert!(matches!(r, Err(SupervisedAuditError::Validation(_))));
    }

    #[test]
    fn validate_rejects_blank_dst_state() {
        let ev = SupervisedLiveAuditEvent::new(
            "evt:x",
            1,
            "op",
            "req",
            AuditEngineMode::Live,
            AuditAction::SessionClosed,
            "   ",
            AuditResult::Ok,
        );
        let r = PgSupervisedLiveAuditWriter::validate(&ev);
        assert!(matches!(r, Err(SupervisedAuditError::Validation(_))));
    }

    #[test]
    fn validate_accepts_valid_event() {
        let ev = SupervisedLiveAuditEvent::new(
            "evt:x",
            1_730_000_000_000,
            "op",
            "req",
            AuditEngineMode::LiveDemo,
            AuditAction::RequestRegistered,
            "REGISTERED",
            AuditResult::Ok,
        );
        assert!(PgSupervisedLiveAuditWriter::validate(&ev).is_ok());
    }
}

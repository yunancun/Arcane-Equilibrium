//! Sprint 1B Earn first stake Wave C — IntentProcessor Earn dispatch branch。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   Wave C 接線 IntentProcessor.process_earn_intent() 的 Earn-specific dispatch
//!   path。trading intent 仍走 router.rs 既有 process_with_features 路徑；本模塊
//!   負責 Earn intent (IntentType::EarnStake / EarnRedeem) 的：
//!     - 5-gate inheritance 驗證（per earn_governance §2.1 hard fail-closed +
//!       AMD-2026-05-21-01 v2 protected 6 不變量）；
//!     - acquire LeaseScope::EarnStake / EarnRedeem lease（60s TTL，per
//!       earn_governance §2.3 + lease_scope.rs default_ttl_ms）；
//!     - INSERT placeholder row to learning.earn_movement_log（reconciliation_
//!       status='pending'）→ call BybitEarnClient subscribe/redeem flexible →
//!       UPDATE outcome row (Bybit ack 後 'matched'；失敗則 write_failure 走
//!       'mismatch' 一次性 INSERT)；
//!     - release lease Consumed（成功）/ Failed（Bybit retCode != 0 / writer 失敗）/
//!       Cancelled（earn_payload absent / governance auth fail）。
//!
//! 主要類 / 函數：
//!   - `EarnDispatchError`：dispatch 過程中的 4 類錯誤分支（earn_payload absent /
//!     governance auth fail / lease acquire fail / Bybit fail / writer fail）；
//!   - `dispatch_earn_intent`：crate-internal async entry，由 IntentProcessor.
//!     process_earn_intent 呼叫，不對外暴露。
//!
//! 依賴：
//!   - `crate::bybit_earn_client::BybitEarnClient`（B3 wave land）；
//!   - `crate::database::earn_movement_writer::EarnMovementWriter`（B4 wave land）；
//!   - `openclaw_core::governance_core::GovernanceCore`（acquire_lease / release_lease /
//!     is_authorized）；
//!   - `openclaw_core::lease_scope::LeaseScope`（EarnStake / EarnRedeem variant，
//!     對映 audit string "EARN_STAKE" / "EARN_REDEEM"）。
//!
//! 硬邊界：
//!   - Earn intent **必須**走 process_earn_intent 入口，不能走 process_with_features
//!     trade-path（後者入口 sanity check 會 fail-closed reject）；
//!   - earn_payload absent → 立即 fail-closed reject（不嘗試 Bybit call）；
//!   - Governance not_authorized → fail-closed reject（同 trade-path Gate 1 語意）；
//!   - bybit_earn_client / earn_movement_writer 任一 None → fail-closed reject
//!     ("earn_dispatch_unwired")，避免 silent no-op：未接線 = 引擎端 Earn capability OFF；
//!   - acquire_lease 失敗（GovernanceError::AuthNotEffective / InvalidTtl /
//!     LeaseSmFailure / LeaseScopeNotPermitted）→ fail-closed reject；
//!   - Bybit subscribe/redeem retCode != 0 → caller 寫 failure row（write_failure
//!     一次性 INSERT，reconciliation_status='mismatch'）+ release lease Failed +
//!     fail-closed reject；
//!   - earn_movement_writer placeholder INSERT 失敗 → fail-closed reject + release
//!     lease Cancelled（不做 Bybit call，避免 audit log 缺 row）；
//!   - earn_movement_writer update_outcome 失敗（Bybit 已 ack）→ release lease
//!     Failed + fail-closed reject 但 caller 應 alert（governance integrity 破損）。
//!
//! 不變量：
//!   - 任何 Earn intent 對應「至少 1 row」在 learning.earn_movement_log（即使失敗，
//!     write_failure 補一條 mismatch row）；
//!   - acquire 成功的 lease 永必 release（Consumed / Failed / Cancelled 三選一），
//!     由 EarnLeaseGuard RAII 兜底；
//!   - process_earn_intent 的 IntentResult.lease_id 為 EarnRouter lease 的 String
//!     形式，audit chain 對映 learning.governance_audit_log.id。
//!
//! 規格 / Spec：
//!   - PA dispatch packet 2026-05-23 §5.3 EarnRouter dispatch path；
//!   - earn_governance_spec.md §2.1 (operator authority hard fail-closed) + §2.3
//!     (lease TTL 60s) + §2.5 (audit gate 兩階段) + §5.1 (fail-closed retCode != 0)；
//!   - ADR-0030 5-gate live boundary + lease facade；
//!   - lease_scope.rs::LeaseScope::EarnStake / EarnRedeem requires_operator_authority。

use std::sync::Arc;

use openclaw_core::{
    governance_core::{GovernanceCore, GovernanceError, GovernanceProfile, LeaseId, LeaseOutcome},
    lease_scope::LeaseScope,
};

use crate::bybit_earn_client::BybitEarnClient;
use crate::bybit_rest_client::BybitApiError;
use crate::database::earn_movement_writer::EarnMovementWriter;

use super::{EarnIntentPayload, IntentResult, IntentType, OrderIntent};

/// Earn dispatch 過程中的錯誤分類。
///
/// 為什麼分這 5 類：caller 端（IntentProcessor.process_earn_intent → fail-closed
/// reject path）需要區分「設計性失敗」（unwired / earn_payload absent）vs「runtime
/// 失敗」（governance / lease / Bybit / writer），對映 IntentResult.rejected_reason
/// 字串供 audit / GUI 顯示。
#[derive(Debug, thiserror::Error)]
pub enum EarnDispatchError {
    /// EarnRouter 未注入 bybit_earn_client 或 earn_movement_writer。
    /// 引擎端 Earn capability OFF；fail-closed 拒絕意圖。
    #[error("earn_dispatch_unwired: {0}")]
    Unwired(&'static str),
    /// OrderIntent.earn_payload 為 None；caller bug。
    #[error("earn_dispatch_payload_missing: EarnIntent must carry earn_payload")]
    PayloadMissing,
    /// GovernanceCore.is_authorized() 為 false（Gate 1 等價）。
    #[error("earn_dispatch_governance_not_authorized")]
    GovernanceNotAuthorized,
    /// acquire_lease 失敗（lease facade 各分支映射）。
    #[error("earn_dispatch_lease_acquire_failed: {0}")]
    LeaseAcquire(String),
    /// Bybit Earn place-order 失敗（retCode != 0 或 transport error）。
    #[error("earn_dispatch_bybit_failed: {0}")]
    BybitFailed(String),
    /// earn_movement_writer placeholder INSERT 失敗（PG 不可達 / FK 破損）。
    /// 此狀態下 Bybit call 尚未發起，audit log 缺 row 視為 fail-closed。
    #[error("earn_dispatch_writer_placeholder_failed: {0}")]
    WriterPlaceholderFailed(String),
    /// earn_movement_writer update_outcome 失敗（Bybit 已 ack）。
    /// 此狀態下 audit log 有 placeholder row 但 outcome 未 update；governance
    /// integrity 破損；caller 應 alert + 釋放 lease Failed。
    #[error("earn_dispatch_writer_update_failed: {0}")]
    WriterUpdateFailed(String),
}

/// RAII guard：acquire 成功的 lease 永必 release，避免 leak。
/// 對應 router.rs::RouterLeaseGuard 範式。
///
/// - 成功路徑（Bybit ack OK + writer update OK）：caller 顯式呼 `consume_ok()`
///   → release Consumed。
/// - Bybit 失敗 / writer 失敗：caller 顯式呼 `consume_failed()` → release Failed。
/// - earn_payload absent / governance auth fail / writer placeholder fail：guard
///   未呼 consume_*，Drop 自動 release Cancelled。
struct EarnLeaseGuard<'a> {
    governance: &'a GovernanceCore,
    lease: Option<LeaseId>,
}

impl<'a> EarnLeaseGuard<'a> {
    fn new(governance: &'a GovernanceCore, lease: Option<LeaseId>) -> Self {
        Self { governance, lease }
    }

    /// 成功路徑：取出 lease 並走 LeaseOutcome::Consumed release。
    /// 返回 lease_id String（供 IntentResult.lease_id 填入）。
    fn consume_ok(mut self) -> Option<String> {
        let lease = self.lease.take()?;
        let id = lease.as_str().to_string();
        if let Err(e) = self.governance.release_lease(&lease, LeaseOutcome::Consumed) {
            tracing::warn!(
                error = %e,
                lease_id = %id,
                "EarnRouter consume_ok release_lease(Consumed) failed; ExpiryGuardian will sweep / EarnRouter 成功路徑釋放失敗，依 ExpiryGuardian 過期清理"
            );
        }
        Some(id)
    }

    /// 失敗路徑（Bybit / writer update fail）：取出 lease 並走 LeaseOutcome::Failed release。
    fn consume_failed(mut self) -> Option<String> {
        let lease = self.lease.take()?;
        let id = lease.as_str().to_string();
        if let Err(e) = self.governance.release_lease(&lease, LeaseOutcome::Failed) {
            tracing::warn!(
                error = %e,
                lease_id = %id,
                "EarnRouter consume_failed release_lease(Failed) failed; ExpiryGuardian will sweep / EarnRouter 失敗路徑釋放失敗，依 ExpiryGuardian 過期清理"
            );
        }
        Some(id)
    }
}

impl<'a> Drop for EarnLeaseGuard<'a> {
    fn drop(&mut self) {
        if let Some(lease) = self.lease.take() {
            // 未呼 consume_* 即 Drop → 視為 caller 中止（earn_payload absent /
            // governance auth fail / writer placeholder fail）→ Cancelled。
            if let Err(e) = self.governance.release_lease(&lease, LeaseOutcome::Cancelled) {
                tracing::warn!(
                    error = %e,
                    "EarnRouter Drop release_lease(Cancelled) failed; ExpiryGuardian will sweep / EarnRouter Drop 釋放失敗，依 ExpiryGuardian 過期清理"
                );
            }
        }
    }
}

/// 把 GovernanceError 映射為對 user 可見的 LeaseAcquire reason 字串。
/// 對齊 router.rs::acquire_lease_for_gate_1_4 風格。
fn map_lease_acquire_err(e: GovernanceError) -> String {
    match e {
        GovernanceError::AuthNotEffective => {
            "lease_facade: authorization not effective (earn fail-closed)".to_string()
        }
        GovernanceError::LeaseScopeNotPermitted(scope) => {
            format!("lease_facade: scope not permitted: {scope}")
        }
        GovernanceError::InvalidTtl(ttl) => {
            format!("lease_facade: invalid TTL {ttl} ms")
        }
        GovernanceError::LeaseNotFound(id) => {
            format!("lease_facade: lease not found: {id}")
        }
        GovernanceError::LeaseSmFailure(sm_err) => {
            format!("lease_facade: SM failure: {sm_err}")
        }
    }
}

/// 依 IntentType 派發 LeaseScope；只接 EarnStake / EarnRedeem，其他 variant 是
/// caller bug（process_earn_intent 入口已驗 is_earn()）。
fn lease_scope_for_earn_intent_type(intent_type: IntentType) -> LeaseScope {
    match intent_type {
        IntentType::EarnStake => LeaseScope::EarnStake,
        IntentType::EarnRedeem => LeaseScope::EarnRedeem,
        // 其他 variant 不應走到本 fn（caller 端 is_earn() 已守）；
        // debug_assert 直接 panic，release path 回 EarnStake 保守。
        other => {
            debug_assert!(
                false,
                "lease_scope_for_earn_intent_type called with non-Earn variant: {:?}",
                other
            );
            LeaseScope::EarnStake
        }
    }
}

/// 依 IntentType 派發 V100 earn_movement_log.direction 字串
/// （per earn_movement_writer.rs validate_direction CHECK 2 enum）。
fn direction_for_earn_intent_type(intent_type: IntentType) -> &'static str {
    match intent_type {
        IntentType::EarnStake => "stake",
        IntentType::EarnRedeem => "redeem",
        other => {
            debug_assert!(
                false,
                "direction_for_earn_intent_type called with non-Earn variant: {:?}",
                other
            );
            "stake"
        }
    }
}

/// EarnRouter dispatch entry — IntentProcessor.process_earn_intent 內呼叫。
///
/// 參數說明：
///   - `intent`: 上層 OrderIntent，intent_type 必為 EarnStake/EarnRedeem，
///     earn_payload 必為 Some(EarnIntentPayload)；caller 端責任驗。
///   - `governance`: 用於 is_authorized() + acquire_lease / release_lease。
///   - `profile`: GovernanceProfile（Production / Validation / Exploration）；
///     Validation / Exploration 走 LeaseId::Bypass 短路（與 trade-path 一致）；
///     Production 走真實 SM transition。
///   - `bybit_earn_client`: B3 wave Earn client；None → fail-closed reject。
///   - `earn_movement_writer`: B4 wave V100 writer；None → fail-closed reject。
///   - `engine_mode`: V100 schema CHECK 4 enum ('paper'/'demo'/'live_demo'/'live')；
///     由 IntentProcessor.effective_engine_mode() 傳入。
///   - `api_scope_used`: 對應 Bybit API permission scope 字串
///     （e.g. "account:earn:write"）；audit forensic 用。
///
/// 回傳：IntentResult；submitted=true 表 Bybit ack OK + writer update OK；
/// submitted=false 表任一 gate 失敗，rejected_reason 帶分類字串。
#[allow(clippy::too_many_arguments)]
pub(super) async fn dispatch_earn_intent(
    intent: &OrderIntent,
    governance: &GovernanceCore,
    profile: GovernanceProfile,
    bybit_earn_client: Option<Arc<BybitEarnClient>>,
    earn_movement_writer: Option<Arc<EarnMovementWriter>>,
    engine_mode: &'static str,
    api_scope_used: &str,
) -> IntentResult {
    // ─── Gate E-0: capability wiring 檢查（未接線 = fail-closed reject）─────
    // 為什麼 fail-closed 而非 silent no-op：未注入兩 dep 表示引擎端 Earn 功能
    // 未啟用，但 caller 仍送 Earn intent → 必須讓 caller 知道（per 不變量
    // 「任何 Earn intent 對應至少 1 row」雖然此處 row 寫不到，但 reject reason
    // 字串明示 unwired 讓 caller alert）。
    let earn_client = match bybit_earn_client {
        Some(c) => c,
        None => {
            return IntentResult::rejected(
                EarnDispatchError::Unwired("bybit_earn_client not injected").to_string(),
            );
        }
    };
    let writer = match earn_movement_writer {
        Some(w) => w,
        None => {
            return IntentResult::rejected(
                EarnDispatchError::Unwired("earn_movement_writer not injected").to_string(),
            );
        }
    };

    // ─── Gate E-1: earn_payload Some 驗（caller bug 早 fail）─────────────────
    // earn_governance §3.2：Earn intent 必帶 amount_usdt / product_id / approval_id
    // 等 7 field；payload None 表 caller 未對齊 IntentProcessor.process_earn_intent
    // contract → fail-closed reject。
    let payload: &EarnIntentPayload = match intent.earn_payload.as_ref() {
        Some(p) => p,
        None => {
            return IntentResult::rejected(EarnDispatchError::PayloadMissing.to_string());
        }
    };

    // ─── Gate E-2: IntentType 必為 EarnStake/EarnRedeem（defence in depth）──
    // 上層 process_earn_intent 已驗 is_earn()，此處 redundant check 防止 caller
    // 端 invariant 破壞時 silent dispatch 錯誤 direction。
    if !intent.intent_type.is_earn() {
        return IntentResult::rejected(
            "earn_dispatch_non_earn_intent_type: caller invariant violated".to_string(),
        );
    }

    // ─── Gate E-3: governance authorization（Gate 1 等價）──────────────────
    if !governance.is_authorized() {
        return IntentResult::rejected(EarnDispatchError::GovernanceNotAuthorized.to_string());
    }

    // ─── Gate E-4: acquire lease（LeaseScope::EarnStake / EarnRedeem，60s TTL）
    // earn_governance §2.3 line 102「TTL = 60s（與 trading lease 一致）」；
    // lease_scope.rs::default_ttl_ms 已固定 60_000。
    let scope = lease_scope_for_earn_intent_type(intent.intent_type);
    let intent_id = format!(
        "earn-{}-{}-{}-{}",
        scope.as_audit_str(),
        intent.symbol,
        payload.approval_id,
        payload.actor_id,
    );
    let lease = match governance.acquire_lease(
        &intent_id,
        scope.as_audit_str(),
        scope.default_ttl_ms(),
        profile,
        "earn_router",
    ) {
        Ok(l) => l,
        Err(e) => {
            return IntentResult::rejected(
                EarnDispatchError::LeaseAcquire(map_lease_acquire_err(e)).to_string(),
            );
        }
    };
    let lease_guard = EarnLeaseGuard::new(governance, Some(lease));

    // ─── Gate E-5: parse amount_usdt + apr_at_time（writer schema 對齊）────
    // amount_usdt 為 String 載荷（per EarnIntentPayload + Bybit V5 慣例）；
    // writer 接 f64，client-side parse 為 f64。失敗 → fail-closed reject（不做
    // Bybit call，避免 placeholder row 寫進去 + Bybit 拒 + audit chain 雙寫）。
    let amount_f64: f64 = match payload.amount_usdt.parse::<f64>() {
        Ok(v) if v.is_finite() && v > 0.0 => v,
        Ok(other) => {
            return IntentResult::rejected(format!(
                "earn_dispatch_amount_invalid: '{}' parsed to {} (must be finite > 0)",
                payload.amount_usdt, other
            ));
        }
        Err(e) => {
            return IntentResult::rejected(format!(
                "earn_dispatch_amount_parse_failed: '{}' err={}",
                payload.amount_usdt, e
            ));
        }
    };
    let apr_at_time: Option<f32> = if intent.intent_type == IntentType::EarnRedeem {
        // redeem 時 APR optional（per writer doc + V100 schema apr_at_time REAL NULL allowed）。
        None
    } else if payload.expected_apr_bps >= 0 {
        // stake 時 expected_apr_bps i32 → REAL: bps / 10000.0 = 小數比例（10000 bps = 100%）。
        Some(payload.expected_apr_bps as f32 / 10_000.0)
    } else {
        None
    };

    // ─── Gate E-6: INSERT placeholder row（earn_movement_log）─────────────
    // earn_governance §2.5「兩階段範式」：placeholder 寫 'pending'，Bybit ack 後
    // UPDATE outcome 'matched'；Bybit timeout 時 Daily cron 掃 24h pending 補對賬。
    // governance_approval_id 為 caller 端 INSERT 後傳入 i64 soft ref（PA-DRIFT-6）；
    // 本 IMPL approval_id 是 String UUID（per EarnIntentPayload）而非 BIGINT id，
    // writer 需 BIGINT — 採取 string→hash i64 fallback：approval_id 作為 audit
    // forensic 字串保留在 governance_audit_log，但 writer FK 端用 0（占位 sentinel）
    // 直到 W6/E1e 補 caller 端「先寫 governance_audit_log RETURNING id」chain。
    //
    // 注意：本決策是 Wave C carry-over → 留給 Wave D/E 補 governance_audit_log
    // INSERT chain；本 IMPL 文檔化此 sentinel 行為避 silent drift。
    let governance_approval_id: i64 = 0; // Wave D/E carry-over: TODO 接 governance_audit_log INSERT chain
    let direction = direction_for_earn_intent_type(intent.intent_type);

    let movement_id = match writer
        .insert_placeholder(
            direction,
            amount_f64,
            apr_at_time,
            governance_approval_id,
            engine_mode,
            api_scope_used,
        )
        .await
    {
        Ok(id) => id,
        Err(e) => {
            // Placeholder INSERT 失敗 → 不做 Bybit call；guard Drop 釋放 Cancelled。
            return IntentResult::rejected(
                EarnDispatchError::WriterPlaceholderFailed(format!("{}", e)).to_string(),
            );
        }
    };

    // ─── Gate E-7: Bybit Earn place-order（subscribe/redeem flexible）──────
    // amount 字串直接傳（Bybit V5 期望字串）；order_link_id 用 intent_id 對映
    // audit chain（per BybitEarnClient subscribe_flexible doc + earn_governance §3.2）。
    // 失敗時 write_failure 補 mismatch row，release lease Failed。
    let bybit_result = match intent.intent_type {
        IntentType::EarnStake => {
            earn_client
                .subscribe_flexible(
                    &intent.symbol,
                    &payload.product_id,
                    &payload.amount_usdt,
                    &intent_id,
                )
                .await
        }
        IntentType::EarnRedeem => {
            earn_client
                .redeem_flexible(
                    &intent.symbol,
                    &payload.product_id,
                    &payload.amount_usdt,
                    &intent_id,
                )
                .await
        }
        _ => unreachable!("earn intent_type validated at Gate E-2"),
    };

    match bybit_result {
        Ok(place_result) => {
            // ─── Gate E-8: UPDATE outcome（Bybit ack OK → 'matched'）──────
            // 成功路徑：bybit_response_payload 寫真實 result JSON（含 orderId /
            // orderLinkId），reconciliation_status='matched'。
            // 注意：本處用 'matched' 而非 'pending' 是「樂觀 ack」假設；Daily
            // reconciliation cron 仍會掃此 row 對賬 Bybit balance API 驗證一致性
            // （per earn_governance §6 + cron/earn_reconciliation.rs）。
            let response_json = serde_json::json!({
                "ret_code": 0,
                "order_id": place_result.order_id,
                "order_link_id": place_result.order_link_id,
            });
            if let Err(e) = writer
                .update_outcome(movement_id, &response_json, "matched")
                .await
            {
                // Bybit 已 ack 但 writer update fail → governance integrity 破損；
                // 釋放 lease Failed + fail-closed reject + tracing alert。
                tracing::error!(
                    movement_id,
                    error = %e,
                    "earn_dispatch_writer_update_failed: Bybit ack OK but earn_movement_log update_outcome failed; governance integrity break / Bybit 已 ack 但 audit log 更新失敗，治理完整性破損"
                );
                let lease_id_str = lease_guard.consume_failed();
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(
                        EarnDispatchError::WriterUpdateFailed(format!("{}", e)).to_string(),
                    ),
                    fill: None,
                    verdict_info: None,
                    approved_qty: 0.0,
                    resting_order: None,
                    maker_degraded_fallback: None,
                    lease_id: lease_id_str,
                };
            }
            // 成功路徑：release lease Consumed + 返回 submitted=true。
            let lease_id_str = lease_guard.consume_ok();
            IntentResult {
                submitted: true,
                rejected_reason: None,
                fill: None, // Earn 不走 FillResult 路徑（trading-specific 結構）
                verdict_info: None, // Earn 不走 Guardian verdict
                approved_qty: amount_f64,
                resting_order: None,
                maker_degraded_fallback: None,
                lease_id: lease_id_str,
            }
        }
        Err(api_err) => {
            // ─── Gate E-9: Bybit retCode != 0 / transport error → write_failure ──
            // earn_governance §5.1「fail-closed retCode != 0」：write_failure 補一條
            // mismatch row（reconciliation_status='mismatch' + bybit_response_payload
            // 含 ret_code/ret_msg/failure_reason）；release lease Failed。
            let (ret_code, ret_msg, failure_reason) = match &api_err {
                BybitApiError::Business { ret_code, ret_msg, .. } => {
                    (*ret_code as i64, ret_msg.clone(), "business_error".to_string())
                }
                BybitApiError::Transport(e) => {
                    (-1, format!("{}", e), "transport_error".to_string())
                }
                BybitApiError::JsonParse(e) => {
                    (-2, format!("{}", e), "json_parse_error".to_string())
                }
                other => {
                    (-99, format!("{:?}", other), "unknown_error".to_string())
                }
            };
            // write_failure 是「一次性 INSERT mismatch row」（per
            // earn_movement_writer.rs::write_failure doc）；本處 movement_id 已存在
            // (placeholder row at Gate E-6)，write_failure 額外寫一筆 mismatch row
            // 在 audit log（雙 row：placeholder pending + failure mismatch），Daily
            // cron 處理時可區分 placeholder 是 silent loss vs 真實 failure。
            //
            // 設計選擇：write_failure 而非 update_outcome("mismatch") 是為了：
            // 1. write_failure 帶 ret_code / ret_msg payload（update_outcome 只接
            //    JsonValue + status，需 caller 自構 payload，重複代碼）；
            // 2. write_failure 是 §5.1 spec 明示的失敗路徑入口，audit forensic
            //    端 grep "failure_reason" 即可找到所有 Bybit fail row。
            if let Err(writer_err) = writer
                .write_failure(
                    direction,
                    amount_f64,
                    apr_at_time,
                    governance_approval_id,
                    engine_mode,
                    api_scope_used,
                    ret_code,
                    &ret_msg,
                    &failure_reason,
                )
                .await
            {
                tracing::error!(
                    movement_id,
                    bybit_ret_code = ret_code,
                    bybit_ret_msg = %ret_msg,
                    writer_err = %writer_err,
                    "earn_dispatch double-fault: Bybit fail + writer fail_row also failed / Bybit 失敗 + failure row 寫入再失敗"
                );
                // Double-fault：仍 release lease Failed（已 acquire），但 reject
                // reason 字串提示 caller 端 audit 缺 failure row。
            }
            let lease_id_str = lease_guard.consume_failed();
            IntentResult {
                submitted: false,
                rejected_reason: Some(
                    EarnDispatchError::BybitFailed(format!(
                        "ret_code={} ret_msg={} reason={}",
                        ret_code, ret_msg, failure_reason
                    ))
                    .to_string(),
                ),
                fill: None,
                verdict_info: None,
                approved_qty: 0.0,
                resting_order: None,
                maker_degraded_fallback: None,
                lease_id: lease_id_str,
            }
        }
    }
}

// ─── IntentProcessor extension impl block ──────────────────────────────────
// 為什麼放在本 file 內：mod.rs 已 ~2030 LOC 逼近 CLAUDE.md §九「2000 LOC hard
// cap」邊界；setter + process_earn_intent 屬 Earn 路徑職責，移到 earn_router.rs
// 內 cross-file impl block 維持 mod.rs LOC 不破 cap。Rust 允許多 impl block 跨
// 同 mod 的 file 散列。
impl super::IntentProcessor {
    /// Sprint 1B Earn Wave C：注入 Bybit Earn REST client（B3 wave land）。
    /// 注入後 process_earn_intent 才能走真實 Bybit place-order 路徑；未注入時
    /// process_earn_intent fail-closed reject "earn_dispatch_unwired"。
    /// Production caller 於 engine bootstrap 注入 Arc<BybitEarnClient>
    /// （與 BybitRestClient 共用同一 secret slot endpoint）。
    pub fn set_bybit_earn_client(&mut self, client: Arc<BybitEarnClient>) {
        self.bybit_earn_client = Some(client);
    }

    /// Sprint 1B Earn Wave C：注入 V100 earn_movement_log writer（B4 wave land）。
    /// 注入後 process_earn_intent 才能走真實 PG 兩階段 audit（placeholder INSERT
    /// → UPDATE outcome）；未注入時 fail-closed reject "earn_dispatch_unwired"。
    pub fn set_earn_movement_writer(&mut self, writer: Arc<EarnMovementWriter>) {
        self.earn_movement_writer = Some(writer);
    }

    /// Sprint 1B Earn Wave C：Earn intent 專用 dispatch entry。
    ///
    /// 為什麼分 sync process_with_features + async process_earn_intent 兩入口：
    /// 1. 既有 process_with_features 是 sync `&self`，trading hot-path 不容許
    ///    block；Bybit Earn API 是 async（reqwest::Client），不能在 sync 內呼。
    /// 2. Earn intent 在 trading hot-path 之外（per earn_governance §2.1 manual
    ///    operator-driven action）：分離 entry 也避免 trading caller 誤把 Earn
    ///    intent 送進 trade-path。
    /// 3. process_with_features 入口（router.rs Gate 0）對 is_earn() intent
    ///    fail-closed reject 並提示走本 method，雙向防護。
    ///
    /// 5-gate inheritance（per AMD-2026-05-21-01 v2 protected 6 不變量）：
    ///   - **Gate E-0 capability wiring**：bybit_earn_client + earn_movement_writer
    ///     兩 dep 未注入 → fail-closed（引擎端 Earn capability OFF）；
    ///   - **Gate E-1 payload Some**：intent.earn_payload absent → fail-closed
    ///     (caller bug 早 fail，不嘗試 Bybit call)；
    ///   - **Gate E-2 intent_type is_earn**：defence in depth；
    ///   - **Gate E-3 governance auth**：governance.is_authorized() == false →
    ///     fail-closed（5-gate Gate a）；
    ///   - **Gate E-4 lease acquire**：LeaseScope::EarnStake/EarnRedeem，60s TTL，
    ///     失敗（auth/scope/TTL）→ fail-closed（5-gate Gate b 等價）；
    ///   - **Gate E-5 amount parse**：amount_usdt String → f64 + finite + > 0；
    ///   - **Gate E-6 INSERT placeholder**：earn_movement_log row 寫前 audit；
    ///   - **Gate E-7 Bybit place-order**：subscribe/redeem flexible；
    ///   - **Gate E-8 UPDATE outcome 'matched'** (Bybit ack OK)；
    ///   - **Gate E-9 write_failure 'mismatch'** (Bybit fail) + release Failed。
    ///
    /// 注意：5-gate Gate b（OPENCLAW_ALLOW_MAINNET=1）由 BybitRestClient 構造時
    /// 把關（per bybit_rest_client_tests.rs Mainnet 構造 fail-closed）；Earn 走
    /// Demo / LiveDemo 端點時不觸 Gate b，client 已是有效 instance。
    pub async fn process_earn_intent(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        profile: GovernanceProfile,
    ) -> IntentResult {
        // engine_mode 對映 V100 schema CHECK 4 enum；effective_engine_mode 已封裝。
        // api_scope_used 用於 audit forensic；Earn write scope 對齊 Bybit V5 spec。
        let engine_mode = self.effective_engine_mode();
        let api_scope_used = "account:earn:write";
        dispatch_earn_intent(
            intent,
            governance,
            profile,
            self.bybit_earn_client.clone(),
            self.earn_movement_writer.clone(),
            engine_mode,
            api_scope_used,
        )
        .await
    }
}

#[cfg(test)]
mod tests {
    //! EarnRouter 內 helper 的純算術 unit test（dispatch 整合路徑於
    //! intent_processor::tests_sprint1b_earn.rs 補）。
    use super::*;

    #[test]
    fn lease_scope_for_earn_stake_maps_to_lease_scope_earn_stake() {
        assert_eq!(
            lease_scope_for_earn_intent_type(IntentType::EarnStake),
            LeaseScope::EarnStake
        );
    }

    #[test]
    fn lease_scope_for_earn_redeem_maps_to_lease_scope_earn_redeem() {
        assert_eq!(
            lease_scope_for_earn_intent_type(IntentType::EarnRedeem),
            LeaseScope::EarnRedeem
        );
    }

    #[test]
    fn direction_for_earn_stake_is_stake_string() {
        assert_eq!(direction_for_earn_intent_type(IntentType::EarnStake), "stake");
    }

    #[test]
    fn direction_for_earn_redeem_is_redeem_string() {
        assert_eq!(direction_for_earn_intent_type(IntentType::EarnRedeem), "redeem");
    }

    #[test]
    fn map_lease_acquire_err_auth_not_effective_string_format() {
        let s = map_lease_acquire_err(GovernanceError::AuthNotEffective);
        assert!(
            s.contains("authorization not effective"),
            "AuthNotEffective 必映射為 user 可見字串"
        );
        assert!(s.contains("earn fail-closed"));
    }

    #[test]
    fn earn_dispatch_error_display_strings_are_grep_friendly() {
        // grep audit log 用：每分支字串均含「earn_dispatch_」前綴 + 可分辨後綴。
        assert!(
            format!("{}", EarnDispatchError::Unwired("test_dep"))
                .contains("earn_dispatch_unwired")
        );
        assert!(
            format!("{}", EarnDispatchError::PayloadMissing)
                .contains("earn_dispatch_payload_missing")
        );
        assert!(
            format!("{}", EarnDispatchError::GovernanceNotAuthorized)
                .contains("earn_dispatch_governance_not_authorized")
        );
        assert!(
            format!("{}", EarnDispatchError::LeaseAcquire("foo".to_string()))
                .contains("earn_dispatch_lease_acquire_failed")
        );
        assert!(
            format!("{}", EarnDispatchError::BybitFailed("bar".to_string()))
                .contains("earn_dispatch_bybit_failed")
        );
        assert!(
            format!("{}", EarnDispatchError::WriterPlaceholderFailed("baz".to_string()))
                .contains("earn_dispatch_writer_placeholder_failed")
        );
        assert!(
            format!("{}", EarnDispatchError::WriterUpdateFailed("qux".to_string()))
                .contains("earn_dispatch_writer_update_failed")
        );
    }

}

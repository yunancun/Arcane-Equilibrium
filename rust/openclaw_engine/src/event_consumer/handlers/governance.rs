//! MODULE_NOTE
//! 模塊用途：SM Option-2 收斂 step (i) 的治理 lease + 唯讀投影 IPC handler。
//!   把 `PipelineCommand::{AcquireLease,ReleaseLease,GetLease,IsAuthorized,
//!   GetGovStatus,ListLeases,GetRiskState}` 變體應用到 tick actor 獨佔的
//!   per-pipeline `GovernanceCore`，並透過 oneshot 回 `Result<String, String>`。
//! 主要類/函數：handle_acquire_lease、handle_release_lease、handle_get_lease、
//!   handle_is_authorized、handle_get_gov_status、handle_list_leases、
//!   handle_get_risk_state；私有 parse_profile / parse_lease_outcome。
//! 依賴：openclaw_core::governance_core（GovernanceCore facade 既有方法，不重實作
//!   SM 邏輯）、openclaw_core::sm::{lease, risk_gov}、serde_json。
//! 硬邊界：
//!   - **ADDITIVE / dormant**：在 Python flag `OPENCLAW_LEASE_PYTHON_IPC_ENABLED`
//!     打開前不被路由；不改動任何既有 SM 邏輯或既有 handler。
//!   - **fail-CLOSED**：任何錯誤（profile/outcome 解析失敗、auth 未生效、
//!     lease not found、SM 內部拒）一律回 `Err(String)`；Rust 端絕不回
//!     permissive / empty-success（Python 端據此 fail-closed），鏡像
//!     governance_lease_bridge.py 既有契約。
//!   - 不碰 execution_authority / live_reserved / 5 道 live-auth gate；lease
//!     acquire 對 Production profile 仍受 `GovernanceCore::is_authorized()`
//!     硬 fail-closed gate 約束（不在此放鬆）。
//!
//! 與 governance_lease_bridge.py / lease_ipc_schema.py 的契約對齊（E1 親驗）：
//!   - acquire 請求 params：intent_id / scope / ttl_ms / profile / source_stage；
//!     回應 `{lease_id, outcome}`，outcome ∈ {"Active","Bypass"}。
//!   - release 請求 params：lease_id / outcome（"Consumed"/"Failed"/"Cancelled"）；
//!     回應 `{ok: true}`。
//!   - get 請求 params：lease_id；回應序列化 LeaseObject（含 lease_id 欄位）。
//!   dispatch.rs 負責 JSON-RPC 解包 → 構造 PipelineCommand → 等 oneshot →
//!   format JSON-RPC 回覆；本模塊只負責「拿到參數後對 GovernanceCore 做事」。

use crate::tick_pipeline::TickPipeline;
use openclaw_core::governance_core::{GovernanceProfile, LeaseId, LeaseOutcome};
use tracing::{info, warn};

/// 將 Python 送來的 profile 字串解析為 `GovernanceProfile`。
///
/// 為什麼 fail-closed：未知 profile 不可默認成 Production（會誤觸 lease 真實 SM
/// 路徑）也不可默認成 bypass（會偽造 Active）——直接回 `Err` 讓上層拒絕，鏡像
/// lease_ipc_schema.build_acquire_request_params 的 3-value 嚴格白名單。
fn parse_profile(s: &str) -> Result<GovernanceProfile, String> {
    match s {
        "Production" => Ok(GovernanceProfile::Production),
        "Validation" => Ok(GovernanceProfile::Validation),
        "Exploration" => Ok(GovernanceProfile::Exploration),
        other => Err(format!(
            "unknown governance profile: {other:?} (must be Production/Validation/Exploration)"
        )),
    }
}

/// 將 Python 送來的 release outcome 字串解析為 `LeaseOutcome`。
///
/// 為什麼 fail-closed：未知 outcome 不可默認成 Consumed（會把失敗執行記成成功
/// 消費，污染 V054 audit 與 SM 終態）——回 `Err` 讓 release 拒絕。
fn parse_lease_outcome(s: &str) -> Result<LeaseOutcome, String> {
    match s {
        "Consumed" => Ok(LeaseOutcome::Consumed),
        "Failed" => Ok(LeaseOutcome::Failed),
        "Cancelled" => Ok(LeaseOutcome::Cancelled),
        other => Err(format!(
            "unknown lease outcome: {other:?} (must be Consumed/Failed/Cancelled)"
        )),
    }
}

/// SM step (i) · acquire_lease handler。
///
/// 調 `core.acquire_lease` 並把 `LeaseId` 攤平成 `{lease_id, outcome}` JSON 字串。
/// Python `parse_acquire_response` 從中讀 `lease_id` + `outcome`（"Active"/"Bypass"）。
pub(super) fn handle_acquire_lease(
    intent_id: String,
    scope: String,
    ttl_ms: u32,
    profile: String,
    source_stage: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = (|| -> Result<String, String> {
        let profile = parse_profile(&profile)?;
        let lease_id = pipeline
            .governance
            .acquire_lease(&intent_id, &scope, ttl_ms, profile, &source_stage)
            .map_err(|e| format!("acquire_lease failed: {e}"))?;
        // LeaseId::Active(s) → {s, "Active"}；Bypass → {"bypass", "Bypass"}。
        // as_str() 對 Bypass 回 "bypass"（與 lease_ipc_schema 註釋一致）。
        let outcome = match &lease_id {
            LeaseId::Active(_) => "Active",
            LeaseId::Bypass => "Bypass",
        };
        Ok(serde_json::json!({
            "lease_id": lease_id.as_str(),
            "outcome": outcome,
        })
        .to_string())
    })();
    if let Err(ref e) = result {
        // intent_id 為 caller-supplied，記 debug 上下文便於追溯；不含敏感資料。
        info!(intent_id = %intent_id, error = %e,
            "governance.acquire_lease rejected (fail-closed) / lease 取得被拒（fail-closed）");
    }
    let _ = response_tx.send(result);
}

/// SM step (i) · release_lease handler。
///
/// 以 `LeaseId::Active(lease_id)` 重建後調 `core.release_lease`。成功回
/// `{"ok": true}`；失敗回 `Err`（Python `parse_release_response` → False）。
pub(super) fn handle_release_lease(
    lease_id: String,
    outcome: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = (|| -> Result<String, String> {
        let outcome = parse_lease_outcome(&outcome)?;
        // Python 端只會送真實 lease_id（SHADOW_BYPASS 在 caller 端已短路，
        // 不會到達 IPC）；故以 Active 重建。若 lease_id 在 SM 反查表不存在，
        // release_lease 回 LeaseNotFound → fail-closed Err。
        let lease = LeaseId::Active(lease_id.clone());
        pipeline
            .governance
            .release_lease(&lease, outcome)
            .map_err(|e| format!("release_lease failed: {e}"))?;
        Ok(serde_json::json!({ "ok": true }).to_string())
    })();
    if let Err(ref e) = result {
        info!(lease_id = %lease_id, error = %e,
            "governance.release_lease rejected (fail-closed) / lease 釋放被拒（fail-closed）");
    }
    let _ = response_tx.send(result);
}

/// SM step (i) · get_lease handler。
///
/// 調 `core.get_lease_by_id` 並 serde 序列化 LeaseObject 為 JSON 回傳。
/// not found 回 `Err`（Python `parse_get_response` → None）。
pub(super) fn handle_get_lease(
    lease_id: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = (|| -> Result<String, String> {
        let obj = pipeline
            .governance
            .get_lease_by_id(&lease_id)
            .map_err(|e| format!("get_lease failed: {e}"))?;
        serde_json::to_string(&obj).map_err(|e| format!("serialize LeaseObject failed: {e}"))
    })();
    let _ = response_tx.send(result);
}

/// SM step (i) · is_authorized 唯讀投影。
///
/// 回 `{"authorized": bool}`。fail-closed 語意由上層（dispatch + Python）負責：
/// 任何 IPC 失敗 Python 回 False；此處只誠實回 GovernanceCore 的當前授權狀態
/// （`is_authorized()` 本身已是 fail-closed：!enabled 或 Frozen 或無 effective auth
/// 皆回 false）。
pub(super) fn handle_is_authorized(
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let authorized = pipeline.governance.is_authorized();
    let payload = serde_json::json!({ "authorized": authorized }).to_string();
    let _ = response_tx.send(Ok(payload));
}

/// SM step (i) · get_status 唯讀投影。
///
/// `core.status()` + auth pending-approval 計數。Python `hub.get_status()` 與
/// `approve_authorization`（需 auth_pending_approval）消費。Rust 端誠實回當前
/// 快照；engine-down / IPC 失敗時的 stale + FROZEN 保守投影由 Python 端負責。
pub(super) fn handle_get_gov_status(
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = (|| -> Result<String, String> {
        let status = pipeline.governance.status();
        // auth pending-approval 計數：core.status() 不含，從 auth SM 快照推算
        // （PendingApproval 狀態），供 Python approve 佇列顯示。
        let auth_pending_approval = pipeline
            .governance
            .auth
            .snapshot_states()
            .iter()
            .filter(|(_, st)| {
                matches!(st, openclaw_core::sm::auth::AuthState::PendingApproval)
            })
            .count();
        // GovernanceStatus 已 derive Serialize；額外併入 pending 計數欄位。
        let mut v = serde_json::to_value(&status)
            .map_err(|e| format!("serialize GovernanceStatus failed: {e}"))?;
        if let serde_json::Value::Object(ref mut map) = v {
            map.insert(
                "auth_pending_approval".to_string(),
                serde_json::json!(auth_pending_approval),
            );
        }
        serde_json::to_string(&v).map_err(|e| format!("serialize status failed: {e}"))
    })();
    let _ = response_tx.send(result);
}

/// SM step (i) · list_leases 唯讀投影。
///
/// 列出本管線所有「live」lease 的 LeaseObject serde array。供 lease list GUI。
/// 空集合回 `[]`（誠實，非錯誤）。
pub(super) fn handle_list_leases(
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = (|| -> Result<String, String> {
        // lease SM 由 Mutex 包（facade 內部可變性）；持鎖蒐集 live LeaseObject clone
        // 後釋鎖再序列化，避免跨 await 持鎖（此 handler 為同步，但保持 clone 模式
        // 與 get_lease_by_id 一致）。
        let leases = {
            let sm = pipeline.governance.lease.lock();
            sm.get_live()
                .into_iter()
                .filter_map(|idx| sm.get(idx).cloned())
                .collect::<Vec<_>>()
        };
        serde_json::to_string(&leases).map_err(|e| format!("serialize lease list failed: {e}"))
    })();
    let _ = response_tx.send(result);
}

/// SM step (i) · get_risk_state 唯讀投影。
///
/// RiskGovernor 狀態（level / level_entered_at_ms / held_ms / constraints /
/// 最近 transition tail）。供 risk GUI 與 `hub.get_status()["risk"]`。
/// 注意：讀的是本管線（per-pipeline）的 governor，符合 3-config 獨立要求
/// （paper/demo/live 各自的 EscalationThresholds 在各自 GovernanceCore）。
pub(super) fn handle_get_risk_state(
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = (|| -> Result<String, String> {
        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        let risk = &pipeline.governance.risk;
        let level = risk.level;
        let held_ms = now_ms.saturating_sub(risk.level_entered_at_ms);
        // 最近 8 筆 transition tail（避免 payload 過大；GUI 只需近期歷史）。
        let tail_n = 8usize;
        let tail_start = risk.transitions.len().saturating_sub(tail_n);
        let transitions_tail = &risk.transitions[tail_start..];
        let constraints = risk.constraints();
        let v = serde_json::json!({
            "level": level.as_str(),
            "level_value": level.value(),
            "level_entered_at_ms": risk.level_entered_at_ms,
            "held_ms": held_ms,
            "consecutive_escalations": risk.consecutive_escalations,
            "version": risk.version,
            "constraints": constraints,
            "transitions_tail": transitions_tail,
        });
        serde_json::to_string(&v).map_err(|e| format!("serialize risk state failed: {e}"))
    })();
    if let Err(ref e) = result {
        warn!(error = %e, "governance.get_risk_state serialize failed (fail-closed)");
    }
    let _ = response_tx.send(result);
}

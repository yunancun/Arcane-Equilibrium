"""Connection-health status normalizer for the Stock/ETF display-only surface.

W4 lockstep（AMD-2026-07-08-01 §Runtime Boundary,與 Rust emitter 同 PR）。負空間三層
判定,依序執行、前層永不可被後層鬆動：

- 第 1 層（hard-safety,無條件）：contact/secret/socket/order/live/db_apply 若為 true →
  **恆 violation**,不受任何 lineage 影響（EA-gated,非 W4/W5 可解禁）。最先執行。
- 第 2 層（negative-space default,lineage 缺席）：`lineage_present == False` 時,每一個
  populated operational 值（session/pacing 活動/attestation/entitlement/report_status）→
  violation。與 W3 all-false 檢查逐位元同構。
- 第 3 層（lineage-bounded,W5+,W4 結構性不可達）：`lineage_present == True` 時 operational
  值可 populated,但仍**逐欄**受 lineage-bound 不變量約束（W5-S0 窮舉補齊：契約枚舉封閉
  值域/session 一致性/halt_reason/reconnect_attempt/pacing 活動/entitlement/report_status
  /attestation 縱深）。W4 下 gate 恆 BLOCKED → 此分支不可達。

`lineage_present`（唯一放行閘,全 Rust-emitter 所有）：`= (phase2_gate.status == "PASS") ∧
(attestation_status ∈ {PAPER_ATTESTED, READONLY_ATTESTED})`——production 未 seal 下結構性為
False。Python **只做一致性檢查,不計算 lineage、不接受 client state、不加 authority**。

**pacing `main_tokens_available` 是 telemetry 非 liveness 訊號**：inactive governor 為滿桶
（初始桶量,非零屬誠實基線）——**不列入負空間 violation**。負空間鎖定 pacing 活動計數。
"""

from __future__ import annotations

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _phase2_fail_closed,
)

# 第 1 層 hard-safety 欄（health 報告的負空間安全束 + db_apply;恆校驗,不受 lineage 影響）。
# 注：health 束用 `ibkr_contact_performed`（非 account 的 `ibkr_call_performed`）。
_HEALTH_HARD_SAFETY_FIELDS: tuple[str, ...] = (
    "ibkr_contact_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
    "ibkr_live_enabled",
    "gateway_socket_open",
    "db_apply_performed",
)

# pacing 活動計數（第 2 層負空間校驗;**不含** main_tokens_available——telemetry 非 liveness）。
_HEALTH_PACING_ACTIVITY_FIELDS: tuple[str, ...] = (
    "queue_depth",
    "lines_in_use",
    "ib_pacing_strikes",
    "admitted",
    "rejected_order_verb",
    "rejected_queue_full",
    "rejected_timeout",
    "rejected_historical",
    "rejected_lines",
)

_ATTESTED_STATES: tuple[str, ...] = ("PAPER_ATTESTED", "READONLY_ATTESTED")

# 第 3 層：session 活躍態（session_active ⟺ session_state ∈ 此集;Rust FSM 契約投影）。
_ACTIVE_SESSION_STATES: tuple[str, ...] = ("ready", "degraded")

# 第 3 層：reconnect 生命週期態——`reconnect_attempt` 非零僅在此集內合法
# （ready 後計數歸零;disconnected 終態殘留計數 fail-closed 視為 violation）。
_RECONNECT_LIFECYCLE_STATES: tuple[str, ...] = ("connecting", "handshaking", "backoff")

# 契約枚舉封閉值域（Rust serde snake_case 投影;與 Rust enum 的逐變體 lockstep 由
# cross-surface parity 測試鎖死,漂移即紅）。∉ 域＝契約外字串——Layer 3 直接 violation
# （fail-closed;Layer 2 由「≠默認值」檢查天然覆蓋契約外值,無需重複域檢查）。
# 出典:`rust/openclaw_types/src/ibkr_tws_session_state.rs` IbkrTwsSessionStateV1。
_SESSION_STATE_DOMAIN: tuple[str, ...] = (
    "disconnected",
    "connecting",
    "handshaking",
    "ready",
    "degraded",
    "backoff",
)
# 出典:`rust/openclaw_types/src/ibkr_tws_connection_health.rs` IbkrConnectionHealthHaltReasonV1。
_HALT_REASON_DOMAIN: tuple[str, ...] = (
    "not_halted",
    "initial",
    "envelope_required",
    "session_fatal",
    "weekly_reauth",
    "reconnect_budget_exhausted",
    "halted",
)
# 出典:同上 IbkrConnectionHealthEntitlementStateV1。
_ENTITLEMENT_STATE_DOMAIN: tuple[str, ...] = ("pending", "granted", "denied")

# 第 2/3 層讀取的 operational scalar 欄（非 hard-safety、非 pacing-activity）的契約共源
# 清單——cross-surface parity superset 測試自本模組匯入（同 hard-safety/pacing 兩集慣例,
# 避免測試側手抄漂移）。
_OPERATIONAL_SCALAR_FIELDS: tuple[str, ...] = (
    "session_state",
    "session_active",
    "reconnect_attempt",
    "halt_reason",
    "attestation_status",
    "account_fingerprint_is_live",
    "entitlement_state",
    "report_status",
)


def _connection_health_lineage_present(
    source: dict[str, Any],
    phase2_gate_status: str,
) -> bool:
    """唯一放行閘：phase2 gate PASS ∧ attestation 已 attested（全 Rust-emitter 所有）。
    W4 下 gate 恆 BLOCKED → 恆 False（第 3 層結構性不可達）。"""
    attestation_status = _as_str(source.get("attestation_status"), "BLOCKED")
    return phase2_gate_status == "PASS" and attestation_status in _ATTESTED_STATES


def _connection_health_negative_space_violations(
    source: dict[str, Any],
    violations: list[str],
) -> None:
    """第 2 層：lineage 缺席時,每一個 populated operational 值 → violation。"""
    # session 束（disconnected / envelope_required / 非 active / reconnect 0 才乾淨）。
    if _as_str(source.get("session_state"), "disconnected") != "disconnected":
        violations.append("session_state_populated")
    if _as_bool(source.get("session_active")):
        violations.append("session_active")
    if _as_int(source.get("reconnect_attempt")) != 0:
        violations.append("reconnect_attempt_present")
    if _as_str(source.get("halt_reason"), "envelope_required") != "envelope_required":
        violations.append("halt_reason_not_envelope_required")
    # pacing 活動計數（main_tokens_available 不校驗——telemetry）。
    for field in _HEALTH_PACING_ACTIVITY_FIELDS:
        if _as_int(source.get(field)) != 0:
            violations.append(f"pacing_{field}_present")
    # attestation / entitlement / report_status 束。
    if _as_str(source.get("attestation_status"), "BLOCKED") != "BLOCKED":
        violations.append("attestation_status_populated")
    if _as_bool(source.get("account_fingerprint_is_live")):
        violations.append("account_fingerprint_is_live")
    if _as_str(source.get("entitlement_state"), "pending") != "pending":
        violations.append("entitlement_state_populated")
    if (
        _as_str(source.get("report_status"), "external_verification_pending")
        != "external_verification_pending"
    ):
        violations.append("report_status_populated")


def _connection_health_lineage_bounded_violations(
    source: dict[str, Any],
    violations: list[str],
) -> None:
    """第 3 層（W5+,W4 結構性不可達）：lineage 具備下,operational 值可 populated,但仍**逐欄**
    受 lineage-bound 不變量約束（W5-S0 窮舉補齊;綁定不成立即 violation,fail-closed）。W4 下
    gate 恆 BLOCKED → 本函數永不被呼叫（覆蓋率/斷言雙鎖）。live 帳戶指紋為硬否決（即使
    lineage 具備仍拒）。"""
    attestation_status = _as_str(source.get("attestation_status"), "BLOCKED")
    session_active = _as_bool(source.get("session_active"))
    session_state = _as_str(source.get("session_state"), "disconnected")
    halt_reason = _as_str(source.get("halt_reason"), "envelope_required")
    entitlement_state = _as_str(source.get("entitlement_state"), "pending")
    # 契約枚舉域檢查（最先執行）：三字串欄僅接受 Rust 契約封閉值域的 snake_case 投影,
    # 契約外字串＝violation——lineage 具備也不接受自宣告的域外值（fail-closed;域外值
    # 若放行會被後續綁定檢查誤判且原樣投影到 GUI 輸出）。
    if session_state not in _SESSION_STATE_DOMAIN:
        violations.append("session_state_unknown")
    if halt_reason not in _HALT_REASON_DOMAIN:
        violations.append("halt_reason_unknown")
    if entitlement_state not in _ENTITLEMENT_STATE_DOMAIN:
        violations.append("entitlement_state_unknown")
    # 縱深防禦：本函數不假設 caller 的 lineage 閘——attestation 未 attested 即 violation
    # （caller 分流漂移時本層自足 fail-closed;正常路徑下 lineage_present 已保證 attested）。
    if attestation_status not in _ATTESTED_STATES:
        violations.append("attestation_status_not_attested_under_lineage")
    if session_active and attestation_status not in _ATTESTED_STATES:
        violations.append("session_active_without_attestation")
    if _as_bool(source.get("account_fingerprint_is_live")):
        violations.append("account_fingerprint_is_live")
    # session_state 與 session_active 一致性（active ⟺ ready/degraded）。
    if session_active != (session_state in _ACTIVE_SESSION_STATES):
        violations.append("session_state_activity_inconsistent")
    # halt_reason ⟺ session_state 綁定（Rust 契約：`not_halted` = 非 disconnected 態）。
    if session_state == "disconnected":
        if halt_reason == "not_halted":
            violations.append("halt_reason_missing_for_disconnected")
    elif halt_reason != "not_halted":
        violations.append("halt_reason_populated_without_disconnect")
    # reconnect_attempt 非零僅在 reconnect 生命週期態內合法。
    if (
        _as_int(source.get("reconnect_attempt")) != 0
        and session_state not in _RECONNECT_LIFECYCLE_STATES
    ):
        violations.append("reconnect_attempt_outside_reconnect_lifecycle")
    # pacing 活動計數：只可能源於活躍 attested session;無活躍 session 而有活動＝violation
    # （main_tokens_available 仍為 telemetry,不校驗）。
    if not session_active:
        for field in _HEALTH_PACING_ACTIVITY_FIELDS:
            if _as_int(source.get(field)) != 0:
                violations.append(f"pacing_{field}_without_active_session")
    # entitlement：非默認值（pending）需活躍 attested session 才可派生（W6 才真派生）。
    if entitlement_state != "pending" and not session_active:
        violations.append("entitlement_state_without_active_session")
    # report_status：emitter 唯一可產值＝external_verification_pending（degraded 僅
    # normalizer 側 IPC 降級路徑）——lineage 具備下自宣告其他值仍 fail-closed。
    if (
        _as_str(source.get("report_status"), "external_verification_pending")
        != "external_verification_pending"
    ):
        violations.append("report_status_not_emitter_produced")


def _connection_health_contract_violations(
    source: dict[str, Any],
    lineage_present: bool,
    reason: str | None,
) -> list[str]:
    """三層負空間判定（依序;前層不可被後層鬆動）。"""
    # 第 1 層：hard-safety,無條件,在任何 lineage 分支之前。
    violations = [
        field for field in _HEALTH_HARD_SAFETY_FIELDS if _as_bool(source.get(field))
    ]
    if reason is not None:
        return violations
    # 第 2/3 層依 lineage 分流。
    if not lineage_present:
        _connection_health_negative_space_violations(source, violations)
    else:
        _connection_health_lineage_bounded_violations(source, violations)
    return violations


def _normalize_connection_health(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    phase2_gate_status = _as_str(external_surface_gate.get("status"), "BLOCKED")
    # lineage_present：唯一放行閘（W4 恆 False）。Python 只讀 Rust-emitter payload,不計算。
    lineage_present = _connection_health_lineage_present(source, phase2_gate_status)

    contract_violations = _connection_health_contract_violations(
        source,
        lineage_present,
        reason,
    )
    blockers = [
        str(item) for item in _as_list(external_surface_gate.get("blockers"))
    ]
    if reason is not None and reason not in blockers:
        blockers.append(reason)

    status_state = "external_verification_pending"
    if contract_violations:
        status_state = "contract_violation_blocked"
    elif reason is not None:
        status_state = "degraded"

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper_readonly",
        "gui_authority": "display_only",
        "connection_health_state": status_state,
        "phase": _as_str(
            source.get("phase"), "phase2_connection_health_source_fixture"
        ),
        "report_status": _as_str(
            source.get("report_status"), "external_verification_pending"
        ),
        # session 束：資訊性 string/int display-only 投影(engine 為 SoT);但 `session_active`
        # 是 negative-space 布林「宣稱」——**輸出恆 clamp False**(thin relay NEVER echo 危險
        # true;GUI 以 contract_violations 為權威訊號)。
        "session_state": _as_str(source.get("session_state"), "disconnected"),
        "halt_reason": _as_str(source.get("halt_reason"), "envelope_required"),
        "session_active": False,
        "reconnect_attempt": _as_int(source.get("reconnect_attempt")),
        # pacing 束（main_tokens_available＝telemetry;活動計數 display-only）。
        "main_tokens_available": _as_int(source.get("main_tokens_available")),
        "queue_depth": _as_int(source.get("queue_depth")),
        "lines_in_use": _as_int(source.get("lines_in_use")),
        "ib_pacing_strikes": _as_int(source.get("ib_pacing_strikes")),
        "admitted": _as_int(source.get("admitted")),
        "rejected_order_verb": _as_int(source.get("rejected_order_verb")),
        "rejected_queue_full": _as_int(source.get("rejected_queue_full")),
        "rejected_timeout": _as_int(source.get("rejected_timeout")),
        "rejected_historical": _as_int(source.get("rejected_historical")),
        "rejected_lines": _as_int(source.get("rejected_lines")),
        # attestation / entitlement 束：資訊性 string 投影;但 `account_fingerprint_is_live`
        # 是 negative-space 布林「宣稱」(live 帳戶)——**輸出恆 clamp False**(NEVER echo 危險 true)。
        "attestation_status": _as_str(source.get("attestation_status"), "BLOCKED"),
        "account_fingerprint_is_live": False,
        "entitlement_state": _as_str(source.get("entitlement_state"), "pending"),
        "pending_reason": _as_str(source.get("pending_reason"), ""),
        # lineage 觀測（第 4 道機器證明：W4 恆 False → 第 3 層不可達）。
        "lineage_present": lineage_present,
        "phase2": phase2,
        "phase2_gate_status": phase2_gate_status,
        "phase2_gate_blockers": blockers,
        "allowed_gui_actions": ["refresh_connection_health"],
        "denied_operations": list(_DENIED_OPERATIONS),
        # 負空間安全束（輸出恆 false;NEVER echo true——contract_violations 才是權威訊號）。
        "ibkr_live_enabled": False,
        "ibkr_contact_performed": False,
        "secret_slot_touched": False,
        "gateway_socket_open": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "db_apply_performed": False,
        "stock_live_disabled": True,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }

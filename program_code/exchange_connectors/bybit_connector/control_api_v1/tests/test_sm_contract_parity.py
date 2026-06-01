"""
跨語言狀態機對等契約測試（Python 側 harness）— 4a 治理里程碑。

MODULE_NOTE
模塊用途：讀單一權威 fixture (rust/openclaw_core/tests/fixtures/sm_contract_vectors.json，
  與 Rust harness 共讀)，對每條向量驅動「真實」的 Python SM
  (AuthorizationStateMachine / DecisionLeaseStateMachine / RiskGovernorStateMachine) 的
  transition()/_validate_transition()，把結果分類成 {allowed / error_kind} 後與 fixture
  expect 比對。Rust harness (tests/sm_contract.rs) 讀同一 fixture 做同樣比對 → 兩側對等。
主要類/函數：_resolve_fixture / _classify_py / _run_auth / _run_lease / _run_risk /
  test_sm_contract_parity / test_inv_d_constraint_table_parity。
依賴：app.authorization_state_machine / decision_lease_state_machine /
  risk_governor_state_machine（均為被觀察對象，0 改動）。
硬邊界：
  - TEST-ONLY，0 行改動 *_state_machine.py / state_machine_base.py。
  - 不可繞過真實 transition()/_validate_transition()；對等必須是「真實驗證路徑」對等。
  - SM-04 min_hold 設 0（fixture harness_contract），使 de-escalation allowed 只反映
    rule+initiator+approval。
  - fixture 路徑必與 Rust 端 env!(CARGO_MANIFEST_DIR) 解析的「同一」絕對檔吻合
    （此處用 repo root = parents[5] 計算）。

為什麼預期首跑會把 drift 顯式列出：fixture 內 rust_only 向量（Reconciler initiator /
  NotificationFailsafeTimeout）在 Python 端「initiator 不存在 / event 不存在」→ harness
  將其 skip+count（不參與等值），並由 tagged-count guard 鎖死。任何「未登記的新分歧」
  （untagged）會讓等值斷言 fail。本里程碑主交付是把 silent drift 轉成顯式列舉。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# 與 repo 內其他 control_api_v1 測試一致：把 control_api_v1 根加入 sys.path 後 `from app...`。
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.authorization_state_machine import (  # noqa: E402
    AuthEvent,
    AuthInitiator,
    AuthState,
    AuthorizationStateMachine,
)
from app.decision_lease_state_machine import (  # noqa: E402
    DecisionLeaseStateMachine,
    LeaseEvent,
    LeaseInitiator,
    LeaseState,
)
from app.risk_governor_state_machine import (  # noqa: E402
    LEVEL_CONSTRAINTS,
    EscalationThresholds,
    RiskEvent,
    RiskGovernorStateMachine,
    RiskInitiator,
    RiskLevel,
)


# ═══════════════════════════════════════════════════════════════════════════════
# fixture 解析（必與 Rust env!(CARGO_MANIFEST_DIR) 解析同一檔）
# ═══════════════════════════════════════════════════════════════════════════════

def _resolve_fixture() -> Path:
    # repo root = srv = parents[5]（tests→control_api_v1→bybit_connector→exchange_connectors
    # →program_code→srv）。Rust 端 = CARGO_MANIFEST_DIR(rust/openclaw_core)/tests/fixtures/...
    primary = (
        Path(__file__).resolve().parents[5]
        / "rust" / "openclaw_core" / "tests" / "fixtures" / "sm_contract_vectors.json"
    )
    if primary.exists():
        return primary
    # 退化：向上尋找含 rust/openclaw_core 的祖先（防 odd cwd / 目錄重排）。
    cur = Path(__file__).resolve()
    for anc in cur.parents:
        cand = anc / "rust" / "openclaw_core" / "tests" / "fixtures" / "sm_contract_vectors.json"
        if cand.exists():
            return cand
    raise FileNotFoundError(f"找不到 SM 契約 fixture（primary={primary}）")


def _load_vectors() -> list[dict]:
    doc = json.loads(_resolve_fixture().read_text(encoding="utf-8"))
    return doc["vectors"]


# ═══════════════════════════════════════════════════════════════════════════════
# enum 解析（initiator 可能在 Python enum 不存在 → 回 None 供 harness 判 drift）
# ═══════════════════════════════════════════════════════════════════════════════

_AUTH_STATE = {s.value: s for s in AuthState}
_LEASE_STATE = {s.value: s for s in LeaseState}
_RISK_LEVEL = {lv.name: lv for lv in RiskLevel}

_AUTH_INIT = {i.value: i for i in AuthInitiator}
_LEASE_INIT = {i.value: i for i in LeaseInitiator}
_RISK_INIT = {i.value: i for i in RiskInitiator}


class _MissingInitiator(Exception):
    """fixture initiator 在 Python enum 不存在（drift 訊號）。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 結果分類：把 Python ERROR_CLS 訊息映成與 Rust SmError 同名的 error_kind
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼用訊息子串弱分類：Python SM 不像 Rust 有結構化 SmError enum；_validate_transition
# 對每種違規 raise ERROR_CLS（AuthorizationError/LeaseError/RiskGovernorError）帶固定訊息。
# state_machine_base._validate_transition 的訊息模板是穩定 source（已逐條核對）：
#   Guard1 terminal     -> "Cannot transition from terminal state"
#   Guard2 forbidden    -> "Forbidden transition:"
#   Guard3 not in table -> "not in transition table"
#   Guard4 initiator    -> "not allowed for"
#   Guard5 approval     -> "requires" + "explicit approval"
#   _extra_validate     -> "before de-escalation"（hold-time；本 fixture 已關閉）

def _classify_py(exc: Exception | None) -> dict:
    if exc is None:
        return {"allowed": True, "error_kind": None}
    msg = str(exc)
    if "terminal state" in msg:
        kind = "TerminalState"
    elif "Forbidden transition" in msg:
        kind = "Forbidden"
    elif "not in transition table" in msg:
        kind = "InvalidTransition"
    elif "not allowed for" in msg:
        kind = "InitiatorNotAllowed"
    elif "explicit approval" in msg or "must be provided" in msg:
        kind = "ApprovalRequired"
    elif "before de-escalation" in msg:
        kind = "HoldTimeNotMet"
    else:
        kind = "UNCLASSIFIED:" + msg[:60]
    return {"allowed": False, "error_kind": kind}


# ═══════════════════════════════════════════════════════════════════════════════
# SM-01 auth：預定位 + 驅動
# ═══════════════════════════════════════════════════════════════════════════════

def _auth_position(sm: AuthorizationStateMachine, frm: AuthState) -> str:
    """走真實 convenience 方法把 auth 物件驅動到 frm，回 authorization_id。"""
    obj = sm.create_draft(title="contract", scope={}, created_by="operator",
                          expires_at_ms=2**62)
    aid = obj.authorization_id
    if frm == AuthState.DRAFT:
        pass
    elif frm == AuthState.PENDING_APPROVAL:
        sm.submit_for_approval(aid)
    elif frm == AuthState.ACTIVE:
        sm.submit_for_approval(aid)
        sm.approve(aid, approved_by="op", reason="pos")
    elif frm == AuthState.RESTRICTED:
        sm.submit_for_approval(aid)
        sm.approve(aid, approved_by="op", reason="pos")
        sm.restrict(aid, reason="pos")
    elif frm == AuthState.FROZEN:
        sm.submit_for_approval(aid)
        sm.approve(aid, approved_by="op", reason="pos")
        sm.freeze(aid, reason="pos")
    elif frm == AuthState.REVOKED:
        sm.submit_for_approval(aid)
        sm.approve(aid, approved_by="op", reason="pos")
        sm.revoke(aid, approved_by="op", reason="pos")
    elif frm == AuthState.EXPIRED:
        sm.submit_for_approval(aid)
        sm.approve(aid, approved_by="op", reason="pos")
        # Active→Expired 必用 ExpiryGuardian（allow-list 不含 Operator）。
        sm.transition(aid, AuthState.EXPIRED, event=AuthEvent.EXPIRED,
                      initiator=AuthInitiator.EXPIRY_GUARDIAN,
                      reason_codes=["time_expiry"])
    elif frm == AuthState.REJECTED:
        sm.reject(aid, reason="pos")  # Draft→Rejected
    else:
        raise AssertionError(f"未處理 auth from {frm}")
    return aid


def _run_auth(v: dict) -> dict:
    frm = _AUTH_STATE[v["from_state"]]
    to = _AUTH_STATE[v["to_state"]]
    init = _AUTH_INIT.get(v["initiator"])
    if init is None:
        raise _MissingInitiator(v["initiator"])
    sm = AuthorizationStateMachine()
    aid = _auth_position(sm, frm)
    try:
        sm.transition(aid, to, event=AuthEvent.APPROVED, initiator=init,
                      reason_codes=["contract"],
                      approved_by=v.get("approved_by"), reason="contract")
        return _classify_py(None)
    except Exception as e:  # noqa: BLE001 — 分類用，下游不吞錯
        return _classify_py(e)


# ═══════════════════════════════════════════════════════════════════════════════
# SM-02 lease
# ═══════════════════════════════════════════════════════════════════════════════

def _lease_position(sm: DecisionLeaseStateMachine, frm: LeaseState) -> str:
    obj = sm.create_draft(intent={}, created_by="strategist", expires_at_ms=2**62)
    lid = obj.lease_id
    if frm == LeaseState.DRAFT:
        pass
    elif frm == LeaseState.REGISTERED:
        sm.register(lid)
    elif frm == LeaseState.ACTIVE:
        sm.register(lid)
        sm.activate(lid)
    elif frm == LeaseState.BRIDGED:
        sm.register(lid)
        sm.activate(lid)
        sm.bridge(lid)
    elif frm == LeaseState.FROZEN:
        sm.register(lid)
        sm.activate(lid)
        sm.freeze(lid, reason="pos")
    elif frm == LeaseState.REVOKED:
        sm.register(lid)
        sm.revoke(lid, approved_by="op", reason="pos")
    elif frm == LeaseState.EXPIRED:
        sm.register(lid)
        sm.transition(lid, LeaseState.EXPIRED, event=LeaseEvent.EXPIRED_BY_TIME,
                      initiator=LeaseInitiator.EXPIRY_GUARDIAN,
                      reason_codes=["time_expiry"])
    elif frm == LeaseState.REJECTED:
        sm.reject(lid, reason="pos")  # Draft→Rejected
    elif frm == LeaseState.CONSUMED:
        sm.register(lid)
        sm.activate(lid)
        sm.bridge(lid)
        sm.consume(lid)
    else:
        raise AssertionError(f"未處理 lease from {frm}")
    return lid


def _run_lease(v: dict) -> dict:
    frm = _LEASE_STATE[v["from_state"]]
    to = _LEASE_STATE[v["to_state"]]
    init = _LEASE_INIT.get(v["initiator"])
    if init is None:
        raise _MissingInitiator(v["initiator"])
    sm = DecisionLeaseStateMachine()
    lid = _lease_position(sm, frm)
    try:
        sm.transition(lid, to, event=LeaseEvent.RECOVERY_APPROVED, initiator=init,
                      reason_codes=["contract"],
                      approved_by=v.get("approved_by"), reason="contract")
        return _classify_py(None)
    except Exception as e:  # noqa: BLE001
        return _classify_py(e)


# ═══════════════════════════════════════════════════════════════════════════════
# SM-04 risk_gov
# ═══════════════════════════════════════════════════════════════════════════════

def _risk_sm() -> RiskGovernorStateMachine:
    # min_hold=0 關閉 hold-time（fixture harness_contract）。
    return RiskGovernorStateMachine(
        thresholds=EscalationThresholds(min_hold_time_seconds=0.0)
    )


def _risk_position(sm: RiskGovernorStateMachine, frm: RiskLevel) -> None:
    if frm == RiskLevel.NORMAL:
        return
    # Operator escalate（Operator ∈ _AUTO 與 _OPERATOR_GOV，對 Normal→任何 escalation 合法）。
    sm.transition(frm, event=RiskEvent.OPERATOR_ESCALATION,
                  initiator=RiskInitiator.OPERATOR, reason_codes=["position"])


def _run_risk(v: dict) -> dict:
    frm = _RISK_LEVEL[v["from_state"]]
    to = _RISK_LEVEL[v["to_state"]]
    init = _RISK_INIT.get(v["initiator"])
    if init is None:
        raise _MissingInitiator(v["initiator"])
    sm = _risk_sm()
    _risk_position(sm, frm)
    try:
        sm.transition(to, event=RiskEvent.RECOVERY_APPROVED, initiator=init,
                      reason_codes=["contract"], approved_by=v.get("approved_by"),
                      reason="contract")
        return _classify_py(None)
    except Exception as e:  # noqa: BLE001
        return _classify_py(e)


_RUNNERS = {"auth": _run_auth, "lease": _run_lease, "risk_gov": _run_risk}


# ═══════════════════════════════════════════════════════════════════════════════
# 主 test：逐向量比對 + tagged-count drift guard
# ═══════════════════════════════════════════════════════════════════════════════

# 與 Rust harness 同步：已登記 drift 計數。新增未登記分歧 → 等值斷言或本計數 fail。
_EXPECTED_RUST_ONLY = 4
_EXPECTED_PY_ONLY = 0


def test_sm_contract_parity():
    vectors = _load_vectors()
    assert vectors, "fixture 無向量"

    failures: list[str] = []
    equality_checked = 0
    rust_only = 0
    py_only = 0

    for v in vectors:
        sm = v["sm"]
        tag = v.get("tag")
        runner = _RUNNERS[sm]

        # rust_only：Python 端常因 initiator/event 不存在而無法表達 → skip+count。
        # 但若 Python 端「竟能表達」（initiator 存在），仍跑出結果以供報告（不參與等值）。
        if tag == "py_only":
            py_only += 1
            continue
        if tag == "rust_only":
            rust_only += 1
            try:
                runner(v)
            except _MissingInitiator:
                pass  # 預期：Reconciler 等在 Python 不存在
            except Exception:  # noqa: BLE001 — drift 向量在 Python 任何結果都不影響等值
                pass
            continue

        # 等值向量
        try:
            actual = runner(v)
        except _MissingInitiator as mi:
            # 未登記 drift：等值向量竟引用 Python 不存在的 initiator → 必須 surface。
            failures.append(
                f"{sm} {v['from_state']}->{v['to_state']} init={v['initiator']} "
                f"note={v.get('note','')}: Python 缺 initiator '{mi}'（未登記 drift）"
            )
            continue

        equality_checked += 1
        expected = v["expect"]
        mismatch = actual["allowed"] != expected["allowed"]
        if (not expected["allowed"]) and (not mismatch):
            if actual["error_kind"] != expected.get("error_kind"):
                mismatch = True
        if mismatch:
            failures.append(
                f"{sm} {v['from_state']}->{v['to_state']} init={v['initiator']} "
                f"appr={v.get('approved_by')} note={v.get('note','')}: "
                f"actual={actual} expected={{'allowed': {expected['allowed']}, "
                f"'error_kind': {expected.get('error_kind')!r}}}"
            )

    assert rust_only == _EXPECTED_RUST_ONLY, (
        f"rust_only drift 計數變動：實際 {rust_only} != 預期 {_EXPECTED_RUST_ONLY}。"
        "若有意新增/移除 drift，請同步本常數 + Rust harness 常數 + E1 report DRIFT LIST。"
    )
    assert py_only == _EXPECTED_PY_ONLY, (
        f"py_only drift 計數變動：實際 {py_only} != 預期 {_EXPECTED_PY_ONLY}。"
    )

    print(
        f"[sm_contract] 向量={len(vectors)} 等值核對={equality_checked} "
        f"rust_only={rust_only} py_only={py_only} 失敗={len(failures)}"
    )

    if failures:
        body = "\n  ".join(failures)
        pytest.fail(
            f"SM 契約對等失敗 {len(failures)} 條（Python 真實 transition 與 fixture expect 不符）:\n  {body}",
            pytrace=False,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# INV-D：constraint 表逐欄對等（Rust constraints_for vs Python LEVEL_CONSTRAINTS）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼獨立一個 test：constraint 表不是「遷移」，是每個 level 的行為約束（monotonic-protective）。
# Rust constraints_for() 與 Python LEVEL_CONSTRAINTS 必須逐欄一致，否則同一風控等級兩語言下
# 行為分歧（新倉允許 / reduce_only / 倉位係數 / requires_operator 不同）。
# 本 test 只驗 Python 側的值符合 4 欄硬契約（per CC INV-D + 與 risk_gov.rs constraints_for 對照）；
# Rust 側等值由 sm/risk_gov.rs 既有 unit test（test_circuit_breaker_constraints 等）守。

# 期望表 = risk_gov.rs constraints_for() 的逐 level 值（已逐欄核對轉錄）。
_EXPECTED_CONSTRAINTS = {
    "NORMAL":          dict(new_entries_allowed=True,  position_size_multiplier=1.0, reduce_only=False, active_de_risking=False, emergency_stops=False, requires_operator=False),
    "CAUTIOUS":        dict(new_entries_allowed=True,  position_size_multiplier=0.7, reduce_only=False, active_de_risking=False, emergency_stops=False, requires_operator=False),
    "REDUCED":         dict(new_entries_allowed=False, position_size_multiplier=0.5, reduce_only=True,  active_de_risking=False, emergency_stops=False, requires_operator=False),
    "DEFENSIVE":       dict(new_entries_allowed=False, position_size_multiplier=0.0, reduce_only=True,  active_de_risking=True,  emergency_stops=False, requires_operator=False),
    "CIRCUIT_BREAKER": dict(new_entries_allowed=False, position_size_multiplier=0.0, reduce_only=True,  active_de_risking=True,  emergency_stops=True,  requires_operator=True),
    "MANUAL_REVIEW":   dict(new_entries_allowed=False, position_size_multiplier=0.0, reduce_only=True,  active_de_risking=False, emergency_stops=True,  requires_operator=True),
}


def test_inv_d_constraint_table_parity():
    """INV-D：Python LEVEL_CONSTRAINTS 必逐欄等於 Rust constraints_for() 的轉錄期望表。"""
    mismatches: list[str] = []
    for lv in RiskLevel:
        exp = _EXPECTED_CONSTRAINTS[lv.name]
        got = LEVEL_CONSTRAINTS[lv]
        for field, want in exp.items():
            have = getattr(got, field)
            if have != want:
                mismatches.append(f"{lv.name}.{field}: Python={have} 期望(Rust)={want}")
    assert not mismatches, "INV-D constraint 表分歧:\n  " + "\n  ".join(mismatches)


# ═══════════════════════════════════════════════════════════════════════════════
# INV-B：de-escalation hold-time（Python 側非 fixture 等值範圍，獨立守）
# ═══════════════════════════════════════════════════════════════════════════════

def test_inv_b_deescalation_requires_hold_time():
    """
    INV-B：降級需 min-hold-time（300s）。本 fixture 等值向量把 min_hold 設 0 以隔離 rule 對等；
    此處用「預設 300s」單獨驗 hold-time gate 真的擋下即時降級（Python 側；Rust 由 risk_gov.rs
    test_de_escalation_hold_time 守）。
    """
    sm = RiskGovernorStateMachine()  # 預設 min_hold_time_seconds=300.0
    sm.escalate_to(RiskLevel.CAUTIOUS, reason="t")
    with pytest.raises(Exception) as ei:
        sm.de_escalate_to(RiskLevel.NORMAL, approved_by="op", reason="r")
    assert "before de-escalation" in str(ei.value)

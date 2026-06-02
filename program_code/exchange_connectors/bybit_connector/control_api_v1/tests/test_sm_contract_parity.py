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


# ═══════════════════════════════════════════════════════════════════════════════
# §3e：lease 審計列形狀對等（Rust LeaseTransitionMsg→V054 row keys
#       == Python _build_transition_record keys for a lease transition）
# ═══════════════════════════════════════════════════════════════════════════════
#
# 為什麼新增（P5 step-(i) / design §3e）：SM Option 2 cutover 後 Rust event_consumer +
# lease_transition_writer.rs 是 learning.lease_transitions 的唯一寫入者。刪 Python
# 寫入路徑前，必須鎖死「Rust 寫的列形狀 == Python 歷史寫的列形狀」，否則 cutover
# 靜默丟失 audit lineage（違反 root principle 8 / DOC-08 inv）。本 test 是該不變量的
# 回歸鎖（Mac 靜態鎖 key 映射；真正的 PG 值語意 dry-run 由 Linux soak 補，design §3e）。
#
# 範圍界定：本 test 鎖「鍵集合 / 語意映射」對等，不是「逐 row 值 byte-equal」（值
# 對等需 Linux PG empirical，見 design §3e 第一點）。auth/risk audit-row 對等是
# 另一個 gate（design §3e 末 R1），非本 task。

# Rust 端權威欄位集 = lease_transition_writer.rs 的 INSERT 欄位 +
# LeaseTransitionMsg struct 欄位（兩者必一致；Rust test_insert_sql_locked_columns 已守）。
# 此處轉錄為期望集，並由 _parse_rust_insert_columns() 從 Rust 源碼重抓做漂移哨兵。
_EXPECTED_RUST_LEASE_ROW_FIELDS = {
    "transition_id",
    "lease_id",
    "from_state",
    "to_state",
    "event",
    "initiator",
    "reason_codes",
    "requires_approval",
    "approved_by",
    "profile",
    "engine_mode",
    "context_id",
    "ts_ms",
}

# 語意映射：Rust/V054 欄位 → Python _build_transition_record 鍵。
# None = 該 Rust 欄位在 Python lease 審計記錄「不存在」（Rust-only，cutover 後由 Rust
# 於 emit 時填；Python 歷史列本就沒有 → 非 lineage 丟失）。
_RUST_TO_PY_LEASE_KEY_MAP: dict[str, str | None] = {
    "transition_id": "transition_id",
    "lease_id": "lease_id",                       # object_id_key="lease_id"
    "from_state": "previous_status",
    "to_state": "next_status",
    "event": "trigger_event_type",
    "initiator": "initiated_by",
    "reason_codes": "transition_reason_codes",
    "requires_approval": "approval_required",
    "approved_by": "approved_by",
    "profile": None,        # Rust-only：GovernanceProfile（Python 記錄無）
    "engine_mode": None,    # Rust-only：engine_mode tag（Python 記錄無）
    "context_id": None,     # Rust-only：context id（Python 記錄無）
    "ts_ms": "effective_at_ms",
}

# Python lease 記錄中、不對應任何 V054 欄位的鍵（Python-only 內部欄位；cutover 後
# Rust 不寫這些，但它們本就不是 V054 列的一部分 → 非 lineage 丟失）。
# 逐一登記，使「未登記的新 Python 鍵」會讓本 test fail（漂移哨兵）。
_PY_ONLY_LEASE_RECORD_KEYS = {
    "trigger_event_id",   # Python 內部事件 id（V054 無此欄）
    "audit_event_ref",    # Python 內部審計引用（V054 無此欄）
    "version_before",     # Python 物件版本（V054 無此欄）
    "version_after",      # Python 物件版本（V054 無此欄）
}


def _parse_rust_insert_columns() -> set[str]:
    """從 lease_transition_writer.rs 源碼抓 INSERT 欄位集（漂移哨兵）。

    對齊 Rust test_insert_sql_locked_columns：若 Rust 改了 INSERT 欄位但沒同步
    本 Python 期望集，本函式抓到的集合會 != _EXPECTED_RUST_LEASE_ROW_FIELDS → fail。
    """
    writer = (
        Path(__file__).resolve().parents[5]
        / "rust" / "openclaw_engine" / "src" / "database" / "lease_transition_writer.rs"
    )
    src = writer.read_text(encoding="utf-8")
    # 抓 "INSERT INTO learning.lease_transitions (col, col, ...) " 內的欄位列。
    import re  # noqa: PLC0415 — test-only local import

    m = re.search(
        r"INSERT INTO learning\.lease_transitions\s*\\?\s*\((.*?)\)\s*\\?\s*VALUES",
        src,
        re.DOTALL,
    )
    assert m, "找不到 Rust INSERT INTO learning.lease_transitions 欄位列"
    cols_blob = m.group(1)
    # 去掉行續接 "\"、換行、空白後 split。
    cols = [c.strip() for c in cols_blob.replace("\\", "").replace("\n", " ").split(",")]
    return {c for c in cols if c}


def _drive_real_python_lease_record() -> dict:
    """驅動一條「真實」的 Python lease transition，回傳 _build_transition_record 輸出。

    走真實 DecisionLeaseStateMachine.transition()（DRAFT→REGISTERED），記錄被 append
    到 lease.transitions[-1]。這就是 cutover 前 Python 寫進 audit pipeline 的列形狀。
    """
    sm = DecisionLeaseStateMachine()
    obj = sm.create_draft(intent={"intent_id": "i-3e", "scope": "TRADE_ENTRY"},
                          created_by="contract", expires_at_ms=2**62)
    lid = obj.lease_id
    lease = sm.register(lid)  # DRAFT→REGISTERED：一條 1:1 真實 transition
    # register() 回傳更新後的 lease 物件；最後一筆 transition 即該次 _build_transition_record。
    return lease.transitions[-1]


def test_lease_audit_row_shape_parity():
    """§3e：Rust LeaseTransitionMsg→V054 row keys 與 Python _build_transition_record
    鍵集合在語意映射下對等（cutover audit-lineage 回歸鎖）。"""
    # 1) Rust 欄位集從源碼重抓 == 期望集（Rust 端漂移哨兵）。
    rust_cols = _parse_rust_insert_columns()
    assert rust_cols == _EXPECTED_RUST_LEASE_ROW_FIELDS, (
        f"Rust INSERT 欄位集漂移：源碼={sorted(rust_cols)} "
        f"期望={sorted(_EXPECTED_RUST_LEASE_ROW_FIELDS)}。"
        "若 Rust 有意改 lease_transitions 欄位，請同步本期望集 + 語意映射 + V054。"
    )

    # 2) 映射表的鍵集合 == Rust 欄位集（映射完整，無遺漏 Rust 欄位）。
    assert set(_RUST_TO_PY_LEASE_KEY_MAP.keys()) == _EXPECTED_RUST_LEASE_ROW_FIELDS, (
        "Rust→Python 語意映射的鍵集合必等於 Rust 欄位集（每個 Rust 欄位都要有對應或標 None）"
    )

    # 3) 驅動真實 Python lease 記錄，取其鍵集合。
    py_record = _drive_real_python_lease_record()
    py_keys = set(py_record.keys())

    # 4) 每個「映射到 Python 的 Rust 欄位」其目標鍵必真實存在於 Python 記錄。
    missing_in_py = [
        (rust_f, py_k)
        for rust_f, py_k in _RUST_TO_PY_LEASE_KEY_MAP.items()
        if py_k is not None and py_k not in py_keys
    ]
    assert not missing_in_py, (
        "Rust 欄位映射到的 Python 鍵不存在於真實 _build_transition_record 輸出："
        + ", ".join(f"{r}→{k}" for r, k in missing_in_py)
        + f"。實際 Python 鍵={sorted(py_keys)}"
    )

    # 5) 反向：每個 Python 記錄鍵必為 (a) 某 Rust 欄位的映射目標，或 (b) 已登記的
    #    Python-only 鍵。未登記的新鍵 → fail（漂移哨兵，防 cutover 靜默丟 lineage）。
    mapped_py_targets = {
        v for v in _RUST_TO_PY_LEASE_KEY_MAP.values() if v is not None
    }
    unaccounted = py_keys - mapped_py_targets - _PY_ONLY_LEASE_RECORD_KEYS
    assert not unaccounted, (
        f"Python lease 記錄出現未登記鍵 {sorted(unaccounted)}；"
        "若有意新增，請更新 _RUST_TO_PY_LEASE_KEY_MAP（若 Rust 也寫）或 "
        "_PY_ONLY_LEASE_RECORD_KEYS（若僅 Python 內部）。"
    )

    print(
        f"[lease_audit_shape] rust_cols={len(rust_cols)} py_keys={len(py_keys)} "
        f"mapped={len(mapped_py_targets)} py_only={len(_PY_ONLY_LEASE_RECORD_KEYS)} "
        f"rust_only={sum(1 for v in _RUST_TO_PY_LEASE_KEY_MAP.values() if v is None)}"
    )

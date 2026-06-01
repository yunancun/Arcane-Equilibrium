#!/usr/bin/env python3
"""
SM 契約向量產生器 — 4a 治理里程碑（跨語言狀態機對等測試）。

MODULE_NOTE
模塊用途：把 Rust (sm/auth.rs, sm/lease.rs, sm/risk_gov.rs) 與 Python
  (authorization/decision_lease/risk_governor_state_machine.py) 的遷移規則表
  完整轉錄成 Python dict，計算「兩側對等矩陣」並輸出單一權威 fixture JSON
  (sm_contract_vectors.json)，供 Rust + Python 兩個 harness 共讀。
主要函數：build_auth / build_lease / build_risk_gov / main。
依賴：無（純標準庫）。
硬邊界：
  - 本檔是 dev 工具，不是被測代碼；它只「轉錄」規則，不改任何 SM。
  - 規則一旦在 SM 源碼變動，必須手動同步本檔並重生 fixture（fixture drift guard
    由 harness 的 tagged-count assert 把關）。
  - 不得在此「修正」drift：4a 階段只觀察、列舉 drift；修復是 4b。

為什麼要產生器而非手寫 fixture：~180 向量手寫易錯；以兩側規則表為 source 計算
  對等/分歧可保證 expect 欄位與規則一致，且 drift 分類可審計。

對等語義（與 harness 對齊）：
  - allowed：transition 成功（Rust Ok / Python 不 raise）。
  - requires_approval：規則的 approval flag（僅 allowed 向量有意義）。
  - error_kind：當 allowed=false 時，Rust SmError 變體名（Python 僅斷言有 raise +
    用訊息子串做弱分類）。
  - SM-04 hold-time gate 在 harness 端以 min_hold=0 關閉，故 de-escalation 的 allowed
    只反映 rule+initiator+approval（hold-time 不變量 INV-B 由 requires_approval=true 表達，
    另有 harness 內建 hold-time 專測，非本 fixture 等值範圍）。
  - tag=rust_only / py_only：該 (sm, from, to, initiator) 組合只有一側可表達（state /
    initiator / event 只存在於一側），排除等值斷言、但計入 tagged-count。
"""

from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "sm_contract_vectors.json"


# ═══════════════════════════════════════════════════════════════════════════════
# 工具：規則表 → 向量
# ═══════════════════════════════════════════════════════════════════════════════

def rule_vectors(sm, states, forbidden_pairs, rules, all_initiators,
                 terminal_states, error_for):
    """
    依「兩側規則表」對單一 SM 生成向量。

    參數：
      rules: dict[(from,to)] -> {"requires_approval": bool, "allowed": set[str]}
             （這是「共識」規則表，即兩側 allow-list 取交集後仍對等的部分；
              分歧部分由呼叫端另以 rust_only/py_only 補。）
      forbidden_pairs: set[(from,to)] 兩側一致的禁止對。
      error_for: callable(from,to,initiator,rule_or_None) -> error_kind str
    回傳：list[vector]
    """
    out = []
    # 1) 規則內向量：每條 rule 取一個 allowed initiator（成功）+ 一個 disallowed
    #    initiator（InitiatorNotAllowed）+ approval 探針。
    for (frm, to), rule in sorted(rules.items()):
        allowed_inits = rule["allowed"]
        req = rule["requires_approval"]
        # (a) allowed initiator + （若需審批則帶 approved_by）→ 成功
        a_init = sorted(allowed_inits)[0]
        out.append({
            "sm": sm, "from_state": frm, "to_state": to,
            "initiator": a_init,
            "approved_by": "operator_x" if req else None,
            "expect": {"allowed": True, "requires_approval": req},
            "note": "rule_allowed_with_approval" if req else "rule_allowed",
        })
        # (b) 若需審批，補一條「allowed initiator 但缺 approved_by」→ ApprovalRequired
        if req:
            out.append({
                "sm": sm, "from_state": frm, "to_state": to,
                "initiator": a_init, "approved_by": None,
                "expect": {"allowed": False, "requires_approval": True,
                           "error_kind": "ApprovalRequired"},
                "note": "approval_required_missing_approver",
            })
        # (c) disallowed initiator（在 all_initiators 但不在 allowed）→ InitiatorNotAllowed
        dis = sorted(set(all_initiators) - set(allowed_inits))
        if dis:
            d_init = dis[0]
            out.append({
                "sm": sm, "from_state": frm, "to_state": to,
                "initiator": d_init,
                "approved_by": "operator_x" if req else None,
                "expect": {"allowed": False, "requires_approval": req,
                           "error_kind": "InitiatorNotAllowed"},
                "note": "initiator_not_allowed",
            })
    # 2) 禁止對：每對一向量。發起者取 Operator（普遍存在）。
    #    關鍵：guard 順序 = 終態(Guard1) 先於 禁止(Guard2)（Rust transition() 與 Python
    #    _validate_transition 兩側一致）。故「from 為終態」的禁止對實際以 TerminalState 浮現，
    #    永遠到不了 forbidden 檢查 → error_kind 應為 TerminalState。只有「from 非終態」的禁止對
    #    才真的命中 Forbidden（auth: DRAFT→ACTIVE；lease: DRAFT→ACTIVE/BRIDGED/CONSUMED +
    #    REGISTERED→BRIDGED）。這本身是一條跨語言對等觀察（兩側 guard 順序相同）。
    for (frm, to) in sorted(forbidden_pairs):
        ek = "TerminalState" if frm in terminal_states else "Forbidden"
        out.append({
            "sm": sm, "from_state": frm, "to_state": to,
            "initiator": "Operator", "approved_by": "operator_x",
            "expect": {"allowed": False, "requires_approval": False,
                       "error_kind": ek},
            "note": "forbidden_pair" if ek == "Forbidden" else "forbidden_pair_shadowed_by_terminal",
        })
    # 3) terminal 來源：從每個 terminal state 出發到一個非自身的合法目標 → TerminalState
    #    （auth/lease 有 terminal；risk_gov 無）。
    for t in sorted(terminal_states):
        # 目標挑一個「若非 terminal 本會是某種結果」的狀態；用第一個非自身 state。
        tgt = next(s for s in states if s != t)
        out.append({
            "sm": sm, "from_state": t, "to_state": tgt,
            "initiator": "Operator", "approved_by": "operator_x",
            "expect": {"allowed": False, "requires_approval": False,
                       "error_kind": "TerminalState"},
            "note": "terminal_source",
        })
    # 4) 「不在表中且非禁止且非 terminal 來源」的代表性 invalid 對 → InvalidTransition
    #    全枚舉太多，取每個非 terminal from_state 的第一個此類 to。
    defined = set(rules.keys()) | set(forbidden_pairs)
    for frm in sorted(states):
        if frm in terminal_states:
            continue
        for to in sorted(states):
            if to == frm:
                continue
            if (frm, to) in defined:
                continue
            out.append({
                "sm": sm, "from_state": frm, "to_state": to,
                "initiator": "Operator", "approved_by": "operator_x",
                "expect": {"allowed": False, "requires_approval": False,
                           "error_kind": "InvalidTransition"},
                "note": "invalid_not_in_table",
            })
            break  # 每個 from 取一條代表即可，避免向量爆炸
    return out


# ═══════════════════════════════════════════════════════════════════════════════
# SM-01 Authorization
# ═══════════════════════════════════════════════════════════════════════════════

def build_auth():
    states = ["DRAFT", "PENDING_APPROVAL", "ACTIVE", "RESTRICTED", "FROZEN",
              "REVOKED", "EXPIRED", "REJECTED"]
    terminal = {"REVOKED", "EXPIRED", "REJECTED"}
    # initiator 命名用 enum.value（兩側一致）：
    GOV = "AuthorizationGovernance"; OP = "Operator"; INC = "IncidentPolicy"
    REC = "RecoveryApprovalFlow"; EXP = "ExpiryGuardian"
    all_inits = [GOV, OP, INC, REC, EXP]

    OP_GOV = {GOV, OP}
    INCIDENT = {INC, GOV, OP}
    RECOVERY = {REC, OP}
    EXPIRY = {EXP, GOV}

    # 兩側規則表完全一致（已逐條核對 auth.rs lookup_rule vs Python TRANSITION_RULES）。
    rules = {
        ("DRAFT", "PENDING_APPROVAL"): {"requires_approval": False, "allowed": OP_GOV},
        ("DRAFT", "REJECTED"): {"requires_approval": False, "allowed": OP_GOV},
        ("PENDING_APPROVAL", "ACTIVE"): {"requires_approval": True, "allowed": OP_GOV},
        ("PENDING_APPROVAL", "REJECTED"): {"requires_approval": False, "allowed": OP_GOV},
        ("ACTIVE", "RESTRICTED"): {"requires_approval": False, "allowed": INCIDENT},
        ("ACTIVE", "FROZEN"): {"requires_approval": False, "allowed": INCIDENT},
        ("ACTIVE", "REVOKED"): {"requires_approval": True, "allowed": OP_GOV},
        ("ACTIVE", "EXPIRED"): {"requires_approval": False, "allowed": EXPIRY},
        ("RESTRICTED", "ACTIVE"): {"requires_approval": True, "allowed": RECOVERY},
        ("RESTRICTED", "FROZEN"): {"requires_approval": False, "allowed": INCIDENT},
        ("RESTRICTED", "REVOKED"): {"requires_approval": True, "allowed": OP_GOV},
        ("RESTRICTED", "EXPIRED"): {"requires_approval": False, "allowed": EXPIRY},
        ("FROZEN", "RESTRICTED"): {"requires_approval": True, "allowed": RECOVERY},
        ("FROZEN", "ACTIVE"): {"requires_approval": True, "allowed": RECOVERY},
        ("FROZEN", "REVOKED"): {"requires_approval": True, "allowed": OP_GOV},
        ("FROZEN", "EXPIRED"): {"requires_approval": False, "allowed": EXPIRY},
    }
    forbidden = {
        ("REVOKED", "ACTIVE"), ("REVOKED", "RESTRICTED"),
        ("EXPIRED", "ACTIVE"), ("EXPIRED", "RESTRICTED"),
        ("REJECTED", "ACTIVE"), ("REJECTED", "PENDING_APPROVAL"),
        ("DRAFT", "ACTIVE"),
    }
    vecs = rule_vectors("auth", states, forbidden, rules, all_inits, terminal, None)
    # auth：無 rust_only/py_only 規則層分歧（events INCIDENT_FREEZE/OBSERVATION_RESTRICTION
    # 只在 Python 且不影響遷移有效性 → 不產生 tagged 向量，於報告文字記載）。
    return vecs


# ═══════════════════════════════════════════════════════════════════════════════
# SM-02 Decision Lease
# ═══════════════════════════════════════════════════════════════════════════════

def build_lease():
    states = ["DRAFT", "REGISTERED", "ACTIVE", "BRIDGED", "FROZEN",
              "REVOKED", "EXPIRED", "REJECTED", "CONSUMED"]
    terminal = {"REVOKED", "EXPIRED", "REJECTED", "CONSUMED"}
    I = "I"; OP = "Operator"; GOV = "AuthorizationGovernance"; INC = "IncidentPolicy"
    EXE = "ExecutionClosureFlow"; EXP = "ExpiryGuardian"; RG = "RiskGovernor"
    all_inits = [I, OP, GOV, INC, EXE, EXP, RG]

    I_OP = {I, OP}
    GOVS = {I, OP, GOV, INC}
    FREEZE = {OP, INC, GOV, I}
    REVOKE = {OP, GOV, INC, I}
    EXPIRY = {EXP, I}
    RECOVERY = {OP, I}
    EXECUTION = {EXE, I}
    RISK_GOV = {RG, I, OP}

    # 兩側規則表完全一致（已逐條核對 lease.rs lookup_rule vs Python LEASE_TRANSITION_RULES）。
    rules = {
        ("DRAFT", "REGISTERED"): {"requires_approval": False, "allowed": I_OP},
        ("DRAFT", "REJECTED"): {"requires_approval": False, "allowed": I_OP},
        ("REGISTERED", "ACTIVE"): {"requires_approval": False, "allowed": I_OP},
        ("REGISTERED", "FROZEN"): {"requires_approval": False, "allowed": FREEZE},
        ("REGISTERED", "REVOKED"): {"requires_approval": True, "allowed": REVOKE},
        ("REGISTERED", "EXPIRED"): {"requires_approval": False, "allowed": EXPIRY},
        ("REGISTERED", "REJECTED"): {"requires_approval": False, "allowed": GOVS},
        ("ACTIVE", "BRIDGED"): {"requires_approval": False, "allowed": RISK_GOV},
        ("ACTIVE", "FROZEN"): {"requires_approval": False, "allowed": FREEZE},
        ("ACTIVE", "REVOKED"): {"requires_approval": True, "allowed": REVOKE},
        ("ACTIVE", "EXPIRED"): {"requires_approval": False, "allowed": EXPIRY},
        ("ACTIVE", "REJECTED"): {"requires_approval": False, "allowed": GOVS},
        ("FROZEN", "REGISTERED"): {"requires_approval": True, "allowed": RECOVERY},
        ("FROZEN", "ACTIVE"): {"requires_approval": True, "allowed": RECOVERY},
        ("FROZEN", "REVOKED"): {"requires_approval": True, "allowed": REVOKE},
        ("FROZEN", "EXPIRED"): {"requires_approval": False, "allowed": EXPIRY},
        ("BRIDGED", "CONSUMED"): {"requires_approval": False, "allowed": EXECUTION},
        ("BRIDGED", "REVOKED"): {"requires_approval": True, "allowed": REVOKE},
    }
    forbidden = {
        ("REVOKED", "ACTIVE"), ("REVOKED", "BRIDGED"),
        ("EXPIRED", "ACTIVE"), ("EXPIRED", "BRIDGED"),
        ("REJECTED", "REGISTERED"), ("REJECTED", "ACTIVE"),
        ("CONSUMED", "ACTIVE"), ("CONSUMED", "BRIDGED"),
        ("DRAFT", "ACTIVE"), ("DRAFT", "BRIDGED"), ("DRAFT", "CONSUMED"),
        ("REGISTERED", "BRIDGED"),
    }
    vecs = rule_vectors("lease", states, forbidden, rules, all_inits, terminal, None)
    # lease：4 個 py_only events（BRIDGE_REJECTED / INVALIDATED / AUTHORIZATION_REVOKED /
    # INCIDENT_FREEZE）不影響遷移有效性 → 報告文字記載，不產生 tagged 向量。
    return vecs


# ═══════════════════════════════════════════════════════════════════════════════
# SM-04 Risk Governor
# ═══════════════════════════════════════════════════════════════════════════════

def build_risk_gov():
    levels = ["NORMAL", "CAUTIOUS", "REDUCED", "DEFENSIVE",
              "CIRCUIT_BREAKER", "MANUAL_REVIEW"]
    RG = "RiskGovernor"; OP = "Operator"; INC = "IncidentPolicy"
    HM = "HealthMonitor"; EXP = "ExpiryGuardian"; REC = "Reconciler"

    # ── 兩側 allow-list 集合（注意：此處是分歧重災區）──
    # Rust AUTO = {RiskGovernor, Operator, IncidentPolicy, HealthMonitor, Reconciler}
    # Py   _AUTO = {RiskGovernor, Operator, IncidentPolicy, HealthMonitor}
    #   → 共識（交集，用於等值向量的 allow-list）= {RG, OP, INC, HM}
    #   → Reconciler 是 rust_only initiator（Python enum 無此成員）。
    #   → ExpiryGuardian 兩側皆「不在」escalation AUTO（Python _ALL 有 EXP 但未用於任何 rule）。
    AUTO_SHARED = {RG, OP, INC, HM}
    OP_GOV_SHARED = {OP, RG}     # Rust OP_GOV 多 Reconciler；共識 = {OP, RG}
    OP_ONLY = {OP}
    # 全體「兩側都存在」的 initiator（Reconciler 不在內，因 Python 無）：
    all_shared_inits = [RG, OP, INC, HM, EXP]

    # 兩側「方向 + approval」一致；差異只在 allow-list 是否含 Reconciler。
    esc_auto = {"requires_approval": False, "allowed": AUTO_SHARED}
    esc_opgov = {"requires_approval": False, "allowed": OP_GOV_SHARED}
    deesc_opgov = {"requires_approval": True, "allowed": OP_GOV_SHARED}
    deesc_oponly = {"requires_approval": True, "allowed": OP_ONLY}
    lateral_opgov = {"requires_approval": False, "allowed": OP_GOV_SHARED}

    rules = {
        # Escalation（AUTO）
        ("NORMAL", "CAUTIOUS"): esc_auto,
        ("NORMAL", "REDUCED"): esc_auto,
        ("NORMAL", "DEFENSIVE"): esc_auto,
        ("NORMAL", "CIRCUIT_BREAKER"): esc_auto,
        ("CAUTIOUS", "REDUCED"): esc_auto,
        ("CAUTIOUS", "DEFENSIVE"): esc_auto,
        ("CAUTIOUS", "CIRCUIT_BREAKER"): esc_auto,
        ("REDUCED", "DEFENSIVE"): esc_auto,
        ("REDUCED", "CIRCUIT_BREAKER"): esc_auto,
        ("DEFENSIVE", "CIRCUIT_BREAKER"): esc_auto,
        # Escalation → ManualReview（OP_GOV）
        ("NORMAL", "MANUAL_REVIEW"): esc_opgov,
        ("CAUTIOUS", "MANUAL_REVIEW"): esc_opgov,
        ("REDUCED", "MANUAL_REVIEW"): esc_opgov,
        ("DEFENSIVE", "MANUAL_REVIEW"): esc_opgov,
        # CB → ManualReview（lateral, OP_GOV）
        ("CIRCUIT_BREAKER", "MANUAL_REVIEW"): lateral_opgov,
        # De-escalation
        ("CAUTIOUS", "NORMAL"): deesc_opgov,
        ("REDUCED", "CAUTIOUS"): deesc_opgov,
        ("REDUCED", "NORMAL"): deesc_oponly,
        ("DEFENSIVE", "REDUCED"): deesc_opgov,
        ("DEFENSIVE", "CAUTIOUS"): deesc_oponly,
        ("CIRCUIT_BREAKER", "DEFENSIVE"): deesc_oponly,
        ("MANUAL_REVIEW", "DEFENSIVE"): deesc_oponly,
        ("MANUAL_REVIEW", "REDUCED"): deesc_oponly,
        ("MANUAL_REVIEW", "CAUTIOUS"): deesc_oponly,
        ("MANUAL_REVIEW", "NORMAL"): deesc_oponly,
    }
    # risk_gov 無 terminal、無顯式 forbidden 表（Python FORBIDDEN_TRANSITIONS=空，
    # Rust 也只靠 lookup_rule None → InvalidTransition）。
    forbidden: set = set()
    terminal: set = set()

    vecs = rule_vectors("risk_gov", levels, forbidden, rules, all_shared_inits,
                        terminal, None)

    # ── INV-A 顯式覆蓋：escalation requires_approval=false（已含於 rule allowed 向量，
    #    這裡再加一條 HealthMonitor escalate 的顯式向量做語義鎖死）。
    vecs.append({
        "sm": "risk_gov", "from_state": "NORMAL", "to_state": "DEFENSIVE",
        "initiator": HM, "approved_by": None,
        "expect": {"allowed": True, "requires_approval": False},
        "note": "INV-A_escalation_auto_no_approval",
    })
    # ── INV-C 顯式覆蓋：CircuitBreaker→Defensive 與 ManualReview→Normal 是 Operator-ONLY，
    #    RiskGovernor / HealthMonitor 不可降級（兩側一致 → 等值向量）。
    for bad in [RG, HM, INC]:
        vecs.append({
            "sm": "risk_gov", "from_state": "CIRCUIT_BREAKER", "to_state": "DEFENSIVE",
            "initiator": bad, "approved_by": "operator_x",
            "expect": {"allowed": False, "requires_approval": True,
                       "error_kind": "InitiatorNotAllowed"},
            "note": "INV-C_cb_recover_operator_only",
        })
    for bad in [RG, HM]:
        vecs.append({
            "sm": "risk_gov", "from_state": "MANUAL_REVIEW", "to_state": "NORMAL",
            "initiator": bad, "approved_by": "operator_x",
            "expect": {"allowed": False, "requires_approval": True,
                       "error_kind": "InitiatorNotAllowed"},
            "note": "INV-C_manual_review_recover_operator_only",
        })

    # ── DRIFT（rust_only）：Reconciler initiator 在 Rust AUTO / OP_GOV，Python 無此 enum。
    #    對「同一 (from,to)」Rust 允許 Reconciler，Python 連 initiator 都不存在 → 必然分歧。
    #    這些向量只在 Rust harness 跑（allowed=true），Python harness 偵測 initiator 不存在 → skip+count。
    reconciler_drift = [
        ("NORMAL", "CAUTIOUS", True, None),        # Reconciler ∈ AUTO escalation
        ("CAUTIOUS", "CIRCUIT_BREAKER", True, None),
        ("CAUTIOUS", "NORMAL", True, "operator_x"),  # Reconciler ∈ OP_GOV de-escalation（需審批）
    ]
    for (frm, to, allowed, appr) in reconciler_drift:
        req = to_is_deescalation(frm, to, levels)
        vecs.append({
            "sm": "risk_gov", "from_state": frm, "to_state": to,
            "initiator": REC, "approved_by": appr,
            "expect": {"allowed": allowed, "requires_approval": req},
            "tag": "rust_only",
            "reason": "RiskInitiator::Reconciler 僅存在於 Rust risk_gov.rs（Phase-6 對帳器自動收縮）；"
                      "Python RiskInitiator enum 無此成員（genuine-gap，待 4b）。",
            "note": "drift_reconciler_initiator",
        })

    # ── DRIFT（rust_only）：NotificationFailsafeTimeout 是 Rust-only RiskEvent（hard-coded
    #    fail-safe, per AMD-2026-05-21-01）。event 不影響 lookup_rule 有效性，但作為治理對等
    #    清單的一員必須顯式登記。用一條 Normal→Defensive escalation 承載（event-only drift）。
    vecs.append({
        "sm": "risk_gov", "from_state": "NORMAL", "to_state": "DEFENSIVE",
        "initiator": RG, "approved_by": None,
        "expect": {"allowed": True, "requires_approval": False},
        "tag": "rust_only",
        "reason": "RiskEvent::NotificationFailsafeTimeout + FAILSAFE_DEFENSIVE_COOLING_MS(7d) + "
                  "active_lock_profit_per_position 為 engine-only failsafe（AMD-2026-05-21-01 §Decision），"
                  "Python SM 無對應 event/常數/hook（legit-engine-only）。",
        "note": "drift_notification_failsafe_event",
    })

    return vecs


def to_is_deescalation(frm, to, order):
    """方向判定：to 等級 < from 等級 = de-escalation（需審批）。"""
    return order.index(to) < order.index(frm)


# ═══════════════════════════════════════════════════════════════════════════════
# main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    vectors = []
    vectors += build_auth()
    vectors += build_lease()
    vectors += build_risk_gov()

    # 穩定排序：sm → from → to → initiator → note（讓 fixture diff 可讀、可重生對齊）。
    vectors.sort(key=lambda v: (v["sm"], v["from_state"], v["to_state"],
                                v["initiator"], v.get("note", "")))

    tagged = [v for v in vectors if v.get("tag")]
    by_sm = {}
    for v in vectors:
        by_sm[v["sm"]] = by_sm.get(v["sm"], 0) + 1

    doc = {
        "_schema": {
            "description": "SM-01/02/04 跨語言對等契約向量（4a 里程碑）。Rust + Python harness 共讀。",
            "fields": {
                "sm": "auth | lease | risk_gov",
                "from_state": "起始狀態 / 等級（enum .value 或 IntEnum .name）",
                "to_state": "目標狀態 / 等級",
                "initiator": "發起者 enum .value",
                "approved_by": "審批人（null = 未提供）",
                "expect.allowed": "transition 是否成功（Rust Ok / Python 不 raise）",
                "expect.requires_approval": "規則 approval flag（僅 allowed 向量有意義）",
                "expect.error_kind": "allowed=false 時的 Rust SmError 變體；Python 弱分類",
                "tag": "rust_only | py_only（排除等值斷言，計入 tagged-count）",
                "reason": "drift 分類與理由",
                "note": "向量用途標籤",
            },
            "harness_contract": {
                "risk_gov_min_hold_ms": 0,
                "note": "harness 必把 SM-04 min_hold 設 0，使 de-escalation allowed 只反映 rule+initiator+approval。",
            },
        },
        "_counts": {
            "total": len(vectors),
            "by_sm": by_sm,
            "tagged_total": len(tagged),
            "tagged_rust_only": sum(1 for v in tagged if v["tag"] == "rust_only"),
            "tagged_py_only": sum(1 for v in tagged if v["tag"] == "py_only"),
        },
        "vectors": vectors,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  total={len(vectors)} by_sm={by_sm} tagged={len(tagged)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

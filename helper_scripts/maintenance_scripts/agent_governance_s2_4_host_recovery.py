#!/usr/bin/env python3
"""S2E.2b-1:S2.4 §5.4 的**啟動逆序補償器**(重啟之後,對上一筆半途交易的 undo)。

``apply_s2_4_install_plan`` 在啟動 reconcile 收斂成 ``COMPENSATE_REVERSE_ORDER`` 時**刻意不自己
補償**:它回 typed 收斂結果並零變更,把 §5.4 的逆序鏈留給持有三段生命週期的 runner。本模組就是
那一段,而且只有那一段。

**它買到的是什麼,不是什麼。** 補償成功之後,同一份 plan 在結構上**永遠不能重跑**:兩張 operator
permit 已 durable 消費且永不因 rollback 釋放;重跑同 plan 會走到 ``IDEMPOTENT_REPLAY``,而
``_load_terminal_journal`` 明文拒絕把終端 ``COMPENSATED`` 讀成「已安裝」,於是收在
``RECOVERY_REQUIRED``。所以本模組買到的是**把「主機狀態不明」換成「主機已證回到前態」**,不是
把 lane 打開——下一步永遠是 operator 簽一份新 plan 配新 permit。

**本模組不簽發任何 receipt。** ``s2_4_install_effect_receipt_v1`` 的 status enum 是凍結的,裡面
沒有任何一個值的語義是「上一筆交易在啟動時被撤銷」;借用它等於對稽核說謊,而擴充它等於改凍結
schema。故本模組用自己的 informal verdict namespace
(:data:`STARTUP_COMPENSATION_SCHEMA_VERSION`),九 authority 恆 false,
``mutation_performed`` 誠實記錄。

**最重要的安全性質(§B.1 S2c)。** 補償是**破壞性**的主機動作。授權它的不是一張新 permit——§5.4
的逆序鏈是「一次已授權 apply 的 undo」,授權來自那兩張**已經燒掉**的 permit。所以本模組在碰主機
之前必須證明**那次授權真的發生過**:replay ledger 的 durable head 必須含這兩張 permit 的消費紀錄,
而那兩張 permit 的 ``authorization_id`` 必須由**綁定這一份 plan** 的 payload 重新導出得到。沒有這
一道,本模組就是一支「找到任何 journal 就對主機做破壞性動作」的免 permit 工具。
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_4_component as _component  # noqa: E402
import agent_governance_s2_4_install_driver as _install_driver  # noqa: E402
import agent_governance_s2_4_install_evidence as _evidence  # noqa: E402
import agent_governance_s2_4_journal as _journal  # noqa: E402
import agent_governance_s2_4_lock as _lock  # noqa: E402
import agent_governance_s2_4_reconcile as _reconcile  # noqa: E402


# ── informal verdict namespace(零 schema 註冊、零 receipt;§B.6)──────────────────
STARTUP_COMPENSATION_SCHEMA_VERSION = "s2_4_startup_compensation_verdict_v1_informal"
STARTUP_COMPENSATION_COMPLETED_EXACT = "STARTUP_COMPENSATION_COMPLETED_EXACT"
STARTUP_COMPENSATION_NOT_APPLICABLE = "STARTUP_COMPENSATION_NOT_APPLICABLE"
STARTUP_COMPENSATION_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
STARTUP_COMPENSATION_JOURNAL_CORRUPT = "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
STARTUP_COMPENSATION_LOCK_HELD = "INSTALL_LOCK_HELD"
STARTUP_COMPENSATION_PENDING = "EXTERNAL_VERIFICATION_PENDING"
STARTUP_COMPENSATION_LANE_UNSUPPORTED = "REVERSE_COMPENSATION_LANE_UNSUPPORTED"
STARTUP_COMPENSATION_TYPED_STATUSES = (
    STARTUP_COMPENSATION_COMPLETED_EXACT,
    STARTUP_COMPENSATION_JOURNAL_CORRUPT,
    STARTUP_COMPENSATION_LANE_UNSUPPORTED,
    STARTUP_COMPENSATION_LOCK_HELD,
    STARTUP_COMPENSATION_NOT_APPLICABLE,
    STARTUP_COMPENSATION_PENDING,
    STARTUP_COMPENSATION_RECOVERY_REQUIRED,
)
# §5.4 逆序鏈在**啟動**時的 rollback post-state digest domain。它與交易內版本刻意不同域:
# 那一份記的是「哪一 row 讓交易停下」,這一份記的是「重啟時在 journal 上讀到哪幾列有 delta」,
# 兩者不是同一件事,共用一個 digest 空間會讓兩種完全不同的結局長得一樣。
STARTUP_ROLLBACK_POST_STATE_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-startup-reverse-compensation-post-state-v1"
)

# ── 每一 row 的 journal 證據分類(§B.2;由 journal 導出,caller 永遠遞交不進來)──────
ROW_DELTA_PROVEN = "DELTA_PROVEN"
ROW_DELTA_POSSIBLE = "DELTA_POSSIBLE"
ROW_NO_DELTA = "NO_DELTA"
# APPLY 交易需要的兩張 permit(§9.1 atomically 消費;aggregate 永不代替 PG)。
REQUIRED_AUTHORIZATION_PROFILE_KEYS = ("apply_aggregate", "pg_migration")

# ── §C:新 probe / PREPARE intent 之前的 journal-routed 收斂閘(自有 informal namespace)──
INTENT_GATE_SCHEMA_VERSION = "s2_4_startup_intent_gate_verdict_v1_informal"
INTENT_GATE_ADMITTED = "STARTUP_INTENT_ADMITTED"
INTENT_GATE_SURFACE_ABSENT = _reconcile.RECONCILE_STATUS_SURFACE_ABSENT
INTENT_GATE_INSTALL_COMPENSATION_REQUIRED = "INSTALL_LANE_REVERSE_COMPENSATION_REQUIRED"
INTENT_GATE_RECOVERY_REQUIRED = STARTUP_COMPENSATION_RECOVERY_REQUIRED
INTENT_GATE_JOURNAL_CORRUPT = STARTUP_COMPENSATION_JOURNAL_CORRUPT
INTENT_GATE_LOCK_HELD = STARTUP_COMPENSATION_LOCK_HELD
INTENT_GATE_PENDING = STARTUP_COMPENSATION_PENDING
INTENT_GATE_LANE_UNSUPPORTED = STARTUP_COMPENSATION_LANE_UNSUPPORTED
INTENT_GATE_TYPED_STATUSES = (
    INTENT_GATE_ADMITTED,
    INTENT_GATE_INSTALL_COMPENSATION_REQUIRED,
    INTENT_GATE_JOURNAL_CORRUPT,
    INTENT_GATE_LANE_UNSUPPORTED,
    INTENT_GATE_LOCK_HELD,
    INTENT_GATE_PENDING,
    INTENT_GATE_RECOVERY_REQUIRED,
    INTENT_GATE_SURFACE_ABSENT,
)
# 本閘只對這兩條 lane 存在:APPLY lane 的啟動 reconcile 由 ``apply_s2_4_install_plan`` 在**同一把
# lock 下**自己做(它只需要四個 startup_* 參數),再包一層等於同一件事做兩次、兩把 lock。
INTENT_GATE_LANES = ("probe", "prepare")
# §C.2 的誠實缺口:``RESUME_VERIFICATION`` 的正解是「只重跑該步的驗證路徑」,而今日 probe 與
# PREPARE **沒有** verify-only 進入點。本波不臨時發明一條(那會變成一次沒有 WAL 前置的重放),
# 而是誠實回 typed RECOVERY_REQUIRED 並把缺口記成 obligation。
RESUME_VERIFICATION_OBLIGATION = (
    "S2E_2B_1_PROBE_PREPARE_VERIFY_ONLY_ENTRY_POINT_ABSENT"
)

# S2E.2b-1 P2-4:本模組對外部模組一律只用**公開名**。設計批准的唯一私有跨模組穿透是
# ``_install_driver._fold_lock_release``(lock 釋放政策的單一擁有者;見 :func:`_release_is_clean`
# 說明它為何不能被抄一份),其餘六處已由各 owner 模組逐名公開再匯出。
_ALL_FALSE_PRODUCTION_FLAGS = dict(_component.ALL_FALSE_PRODUCTION_FLAGS)


def _verdict(
    status: str,
    reasons: list[str],
    *,
    plan_id: str | None = None,
    mutation_performed: bool = False,
    driver_engaged: bool = False,
    reconcile: dict[str, Any] | None = None,
    row_classification: dict[str, Any] | None = None,
    reverse_ops: list[dict[str, Any]] | None = None,
    rollback: dict[str, Any] | None = None,
    journal: dict[str, Any] | None = None,
    residue: dict[str, Any] | None = None,
    lock_release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """單一出境面;九 authority 恆 false,且出境前過一次秘密掃描(§7)。"""

    verdict = {
        "schema_version": STARTUP_COMPENSATION_SCHEMA_VERSION,
        "status": status,
        "reasons": list(reasons),
        "plan_id": plan_id,
        "mutation_performed": bool(mutation_performed),
        "driver_engaged": bool(driver_engaged),
        "reconcile": reconcile,
        "row_classification": dict(row_classification or {}),
        "reverse_ops": list(reverse_ops or []),
        "rollback": rollback,
        "journal": journal,
        "residue": residue,
        "lock_release": lock_release,
        # 本模組**不簽發** receipt:那句話在出境物件上必須看得見,而不是只寫在 docstring。
        "emits_effect_receipt": False,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "secret_material_scanned": True,
    }
    leak = _component.scan_serializable_surface(verdict)
    if leak:
        return {
            "schema_version": STARTUP_COMPENSATION_SCHEMA_VERSION,
            "status": _component.COMPONENT_STATUS_SECRET_LEAK_BLOCKED,
            "reasons": leak + [
                "the constructed startup-compensation verdict carried secret material; every "
                "artifact, reason and observation was dropped rather than returned (§7)"
            ],
            "plan_id": plan_id,
            "mutation_performed": bool(mutation_performed),
            "driver_engaged": bool(driver_engaged),
            "reconcile": None, "row_classification": {}, "reverse_ops": [],
            "rollback": None, "journal": None, "residue": None, "lock_release": None,
            "emits_effect_receipt": False,
            "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
            "secret_material_scanned": True,
        }
    return verdict


# --------------------------------------------------------------------------- #
# §B.2 每一 row 的分類 —— 完全由 durable journal 導出
# --------------------------------------------------------------------------- #
def classify_journal_rows(journal: Any) -> dict[str, dict[str, Any]]:
    """逐 row 掃 APPLY WAL,回 ``{class: {classification, states, digests…}}``。

    ``applied_rows`` **絕不**由 caller 遞交:那會讓「哪幾列要被破壞性還原」變成一個未認證的
    caller view。判準只有 journal 上的 state 序列(§B.2):

    ==================================================  ==================  =============
    journal 證據                                         分類                動作
    ==================================================  ==================  =============
    有 ``COMPENSATING`` 但無該 row 的 ``COMPENSATED``    ``DELTA_POSSIBLE``  必再補償
    有 ``APPLIED`` / ``VERIFIED``                        ``DELTA_PROVEN``    必補償
    有 ``APPLYING`` 但其後無 ``APPLIED``/``VERIFIED``    ``DELTA_POSSIBLE``  必**冪等**補償
    該 class 完全無 entry                                ``NO_DELTA``        不呼叫 driver
    ==================================================  ==================  =============

    「上次補償被打斷」排在最前面:一次被中斷的補償留下的殘留與「從未補償過」在主機上不可分辨,
    跳過它就是把一台半拆的主機講成乾淨。

    ``component_effect_class == ENTRY_SCOPE_AGGREGATE_TRANSACTION`` 的 entry 是**交易級**的
    (``COMPENSATING`` 與終端態),它們的 pre/post 是 plan 級前態,不屬於任何一 row 的 digest
    空間,故不參與任何 row 的分類。

    ``row_applied_state_digest`` / ``row_pre_state_digest`` 只由 ``entry_source ==
    ENTRY_SOURCE_COMPONENT_ROW`` 的 entry 導出,而**本模組自己寫的**補償 entry 一律標
    ``ENTRY_SOURCE_AGGREGATE``(§B.4;判別欄的定義是「誰寫的」)——否則補償鏈中崩、第二次啟動
    時 ``row_driver_entries[-1]`` 取到的會是補償器自己那一筆,於是「這一列被施作成什麼樣」會被
    讀成「這一列已被還原成什麼樣」。
    """

    entries = (journal or {}).get("entries") or []
    classified: dict[str, dict[str, Any]] = {}
    for name in _install_driver.APPLY_ROW_ORDER:
        row_entries = [
            entry for entry in entries
            if isinstance(entry, dict) and entry.get("component_effect_class") == name
        ]
        states = [str(entry.get("state")) for entry in row_entries]
        # §5.2 的 digest 空間判別:只有該 row 的 driver 寫的那幾筆活在該 row 的 subject 空間。
        row_driver_entries = [
            entry for entry in row_entries
            if entry.get("entry_source") == _journal.ENTRY_SOURCE_COMPONENT_ROW
        ]
        if not states:
            classification = ROW_NO_DELTA
        elif "COMPENSATING" in states and "COMPENSATED" not in states:
            classification = ROW_DELTA_POSSIBLE
        elif "APPLIED" in states or "VERIFIED" in states:
            classification = ROW_DELTA_PROVEN
        else:
            # ``APPLYING`` 之後沒有任何 APPLIED/VERIFIED:崩在 effect 窗內,delta 可能存在。
            classification = ROW_DELTA_POSSIBLE
        classified[name] = {
            "classification": classification,
            "states": states,
            "entry_sources": sorted({str(entry.get("entry_source")) for entry in row_entries}),
            # 逆向 WAL 的方向是**反的**:pre = 已施作態,post = 原前態。
            "row_applied_state_digest": (
                row_driver_entries[-1].get("post_state_digest") if row_driver_entries else None
            ),
            "row_pre_state_digest": (
                row_driver_entries[0].get("pre_state_digest") if row_driver_entries else None
            ),
        }
    return classified


# --------------------------------------------------------------------------- #
# §B.1 S2b:journal 的 plan 身分必須逐欄等於由**手上這份 plan** 重算的值
# --------------------------------------------------------------------------- #
def journal_plan_identity_reasons(journal: Any, plan: dict[str, Any]) -> list[str]:
    """四欄逐一比對;任一不等即「這本 journal 不是這份 plan 的」⇒ 零變更。"""

    plan_id = plan.get("plan_id")
    expected = {
        "plan_id": plan_id,
        "plan_core_digest": plan.get("core_digest"),
        "expected_pre_state_digest": (plan.get("core") or {}).get("pre_state_digest"),
        "aggregate_rollback_digest": _install_driver.aggregate_rollback_digest(
            plan_id=str(plan_id)
        ),
    }
    reasons: list[str] = []
    for field, wanted in expected.items():
        if (journal or {}).get(field) != wanted:
            reasons.append(
                f"the durable APPLY journal field {field} does not equal the value re-derived "
                "from the plan in hand; this journal does not describe this plan, so nothing in "
                "it authorizes a destructive reverse compensation (§5.4)"
            )
    return reasons


# --------------------------------------------------------------------------- #
# §B.1 S2c:那兩張 permit 真的被燒掉過(本元件最重要的安全性質)
# --------------------------------------------------------------------------- #
def replay_consumption_reasons(
    ledger: Any, plan: dict[str, Any], authorization_set: Any
) -> list[str]:
    """證明 replay ledger 的 durable head 含**這一份 plan** 的兩筆 consume 紀錄。

    判準(全部與時鐘無關,見下方誠實界線):

      1. 兩張 permit 都在場,且各自通過中央 schema 驗證;
      2. 每張 permit 的 ``payload_binding`` 綁的是**這一份** plan(``plan_id`` +
         ``plan_core_digest`` 逐欄相等);
      3. 每張 permit 的 ``authorization_id`` 由該 plan-bound payload **重新導出**得到
         (``s2_4_authorization_identity_digest``)——id 是算出來的,不是它自報的。導出用的
         profile 身分 / 簽章 namespace / payload token 次序取自 **profile 表**,而不是 permit
         自報的那三欄。這一點正是本導出與中央 schema 閘**不重複**之處:
         ``derive_authorization_id`` 用 permit 自報的欄位,所以一張完全合法的 aggregate permit
         被填到 ``pg_migration`` 這個位置時它自己驗得過(而 registry invariant 明文
         「the aggregate permit never replaces the PG permit」);用 profile 表導出,位置與身分
         不符當場現形;
      4. ledger 的 hash chain 重新導出成立,且恰有**一筆** entry 的 ``authorization_id``
         等於它,且該 entry 的 ``authorization_digest`` == permit 的 ``self_digest``、
         ``profile_identity`` == permit 的 ``profile_identity``。

    **誠實界線:此處刻意不重驗 SSHSIG 新鮮度。** §9.1 的 TTL 與新鮮窗是「這張 permit 現在能不能
    授權一次**新**動作」的閘,而本模組要證的是一件**過去**的事實:那次 apply 的授權真的發生過。
    重啟後的 permit 幾乎必然已過期——把新鮮度當判準,等於讓補償器恰好在它唯一被需要的時刻不可達。
    真正的錨是 ledger:entry 綁 ``authorization_digest``(= permit 的整份 canonical self digest,
    含簽章位元組),而要造出同 id 又同 self_digest 的 permit 就得逐位元組等於那一張本尊。

    第 4 點的 ``AUTHORIZATION_CONSUMPTION`` 若不存在(id 從未出現在 ledger),結論是**沒有任何
    授權曾被燒掉** ⇒ 拒絕。這條路徑正是「找到一本 journal 就對主機做破壞性動作」與「undo 一次
    已授權的 apply」之間的分界。
    """

    reasons: list[str] = []
    if not isinstance(authorization_set, dict):
        return [
            "the startup compensator requires the two operator permits this plan's APPLY "
            "consumed; without them nothing proves that authorization ever happened (§9.1)"
        ]
    chain_errors = central_validator.s2_4_replay_ledger_errors(ledger)
    if chain_errors:
        return list(chain_errors) + [
            "the replay ledger head does not re-derive its hash chain, so it cannot prove any "
            "consumption; RECOVERY_REQUIRED with zero mutation"
        ]
    entries = (ledger or {}).get("entries") or []
    plan_id = plan.get("plan_id")
    plan_core_digest = plan.get("core_digest")
    for profile_key in REQUIRED_AUTHORIZATION_PROFILE_KEYS:
        permit = authorization_set.get(profile_key)
        if not isinstance(permit, dict):
            reasons.append(
                f"the {profile_key} permit was not supplied; the reverse compensation of an "
                "APPLY that consumed BOTH permits cannot be authorized by one of them"
            )
            continue
        schema_errors = central_validator.validate_aiml_artifact(permit)
        if schema_errors:
            reasons.extend(f"{profile_key}: {reason}" for reason in schema_errors)
            continue
        payload = permit.get("payload_binding")
        if not isinstance(payload, dict) or payload.get("plan_id") != plan_id or (
            payload.get("plan_core_digest") != plan_core_digest
        ):
            reasons.append(
                f"the {profile_key} permit payload is not bound to this plan "
                "(plan_id/plan_core_digest mismatch); a permit for another plan never "
                "authorized this host's delta"
            )
            continue
        profile = central_validator.S2_4_AUTHORIZATION_PROFILES.get(profile_key) or {}
        derived_id = central_validator.s2_4_authorization_identity_digest(
            profile_identity=profile.get("profile_identity"),
            signature_namespace=profile.get("signature_namespace"),
            payload_fields=list(profile.get("payload_fields") or ()),
            payload_binding=payload,
        )
        if permit.get("authorization_id") != derived_id:
            reasons.append(
                f"the {profile_key} permit's authorization_id is not the digest re-derived from "
                "its own plan-bound payload; a self-reported id binds nothing"
            )
            continue
        matches = [
            entry for entry in entries
            if isinstance(entry, dict) and entry.get("authorization_id") == derived_id
        ]
        if len(matches) != 1:
            reasons.append(
                f"the replay ledger holds {len(matches)} consumption records for the "
                f"{profile_key} permit of this plan; exactly one is required. Zero means this "
                "plan's APPLY never durably consumed its authorization, so there is no "
                "authorized delta to undo and this surface would be a permit-free destructive "
                "tool (§9.1)"
            )
            continue
        entry = matches[0]
        if entry.get("authorization_digest") != permit.get("self_digest") or (
            entry.get("profile_identity") != permit.get("profile_identity")
        ):
            reasons.append(
                f"the {profile_key} consumption record does not bind this exact permit "
                "(authorization_digest / profile_identity mismatch)"
            )
    return reasons


# --------------------------------------------------------------------------- #
# §B.3 ownership_verified —— 三個合取,全來自 durable state
# --------------------------------------------------------------------------- #
def _row_ownership_verified(
    *,
    journal: dict[str, Any],
    component_effect_class: str,
    component_intents: Any,
) -> bool:
    """(c):journal 內存在一筆該 row driver 寫的 entry,其 ``pre_state_digest`` 恰等於
    plan 綁定的 intent 前態 ——「是本任務把這一列從它記錄的前態移開的」。

    (a) 與 (b) 是全域前置(install lane 收斂為 COMPENSATE ⇒ ``reconcile_journal`` 已強制
    ownership binding 解參考到**這一本** journal;plan 身分四欄全等),由呼叫端在進到這裡之前
    就已成立;此函式只負責 per-row 的第三個合取。
    """

    intent = (component_intents or {}).get(component_effect_class)
    expected_pre = (intent or {}).get("pre_state_digest") if isinstance(intent, dict) else None
    if not isinstance(expected_pre, str):
        return False
    for entry in journal.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        if entry.get("entry_source") != _journal.ENTRY_SOURCE_COMPONENT_ROW:
            continue
        if entry.get("component_effect_class") != component_effect_class:
            continue
        if entry.get("pre_state_digest") == expected_pre:
            return True
    return False


def component_intent_binding_reasons(plan: dict[str, Any], component_intents: Any) -> list[str]:
    """五份 intent 必須逐一重算出 plan core 釘住的 ``component_intent_digest``。

    ``component_intents`` 是 caller 遞交的,而 §B.3 (c) 用它的 ``pre_state_digest`` 決定
    ``ownership_verified``。未綁定的 intent 等於讓 caller 自己填「我擁有這一列」,故此處先把它
    綁回**已簽的** plan core(``apply_rows[].component_intent_digest``)。
    """

    rows = {
        str(row.get("component_effect_class")): row.get("component_intent_digest")
        for row in ((plan.get("core") or {}).get("apply_rows") or [])
        if isinstance(row, dict)
    }
    reasons: list[str] = []
    for name in _install_driver.APPLY_ROW_ORDER:
        intent = (component_intents or {}).get(name)
        if not isinstance(intent, dict):
            reasons.append(
                f"no component intent was supplied for {name}; without it the §5.4 ownership "
                "condition for that row cannot be established from durable state"
            )
            continue
        derived = _install_driver.component_intent_plan_binding_digest(intent)
        if derived != rows.get(name):
            reasons.append(
                f"the supplied {name} component intent does not re-derive the "
                "component_intent_digest pinned in the signed plan core; an unbound intent is a "
                "caller view, not plan-bound evidence"
            )
    return reasons


# --------------------------------------------------------------------------- #
# §B 的頂層進入點
# --------------------------------------------------------------------------- #
def compensate_s2_4_startup_residue(
    plan: Any,
    authorization_set: Any = None,
    driver: Any = None,
    *,
    component_intents: Any = None,
    ownership_evidence: Any = None,
    startup_journal_paths: Any = None,
    startup_observed_state_digests: Any = None,
    startup_task_owned_partials: Any = None,
    probe_receipt_digests: Any = None,
    now: Any = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """§5.4:重啟之後,對**上一筆**半途 APPLY 交易執行逆序補償。

    公開簽名裡**沒有** ``ownership_verified``:那是由 durable state 導出的結論,不是 caller 可以
    遞交的輸入(鏡 S2.0 runner 的 production lane 不收任何 caller view)。``applied_rows`` 同理,
    由 :func:`classify_journal_rows` 從 journal 導出。

    固定閘序(任何一道不過即 typed 非成功且**零主機變更**):

      1. plan 結構;2. ``driver=None`` → ``EXTERNAL_VERIFICATION_PENDING``;
      3. aggregate driver 禁面硬檢;4. install lock;5. §5.2 啟動 reconcile,且必須**恰為**
      install lane 的 ``COMPENSATE_REVERSE_ORDER``;6. journal plan 身分四欄;
      7. replay ledger 的兩筆 consume 紀錄(§B.1 S2c);8. 五份 intent 綁回 plan core。

    ``now`` 只用於記錄;**plan 的到期不是本進入點的閘**——重啟時它幾乎必然已過期,而「上一筆
    交易在主機上留下了什麼」與「這份 plan 現在還能不能授權新工作」是兩件事。後者由
    ``apply_s2_4_install_plan`` 執法(且補償之後那條路必然收在 RECOVERY_REQUIRED)。
    """

    tick = clock or (lambda: datetime.now(timezone.utc))
    del now  # 只由 caller 記錄用;本進入點的判準全部與時鐘無關(見 docstring)。
    if not isinstance(plan, dict) or plan.get("schema_version") != "s2_4_install_plan_v1":
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED,
            ["the startup compensator accepts only an s2_4_install_plan_v1 artifact"],
        )
    plan_errors = central_validator.validate_aiml_artifact(plan)
    if plan_errors:
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED, plan_errors,
            plan_id=plan.get("plan_id"),
        )
    plan_id = str(plan["plan_id"])
    if driver is None:
        return _verdict(
            STARTUP_COMPENSATION_PENDING,
            [
                "the §5.4 startup reverse compensation is reachable but authority-locked: no "
                "production driver is present (Mac/source/test lane); "
                "EXTERNAL_VERIFICATION_PENDING with zero mutation"
            ],
            plan_id=plan_id,
        )
    forbidden = _install_driver.assert_no_aggregate_forbidden_surface(driver)
    if forbidden:
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED, forbidden, plan_id=plan_id,
        )
    try:
        lock_driver = driver.lock_driver()
        file_driver = driver.file_driver()
    except Exception as error:  # noqa: BLE001
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED,
            [
                "the aggregate driver could not supply its lock/file surfaces: "
                f"{_component.redact_driver_error(error)}"
            ],
            plan_id=plan_id, driver_engaged=True,
        )
    lock_verdict = _lock.acquire_s2_4_install_lock(lock_driver)
    if lock_verdict["status"] != _lock.LOCK_STATUS_ACQUIRED:
        mapped = {
            _lock.LOCK_STATUS_HELD: STARTUP_COMPENSATION_LOCK_HELD,
            _lock.LOCK_STATUS_PENDING: STARTUP_COMPENSATION_PENDING,
        }.get(lock_verdict["status"], STARTUP_COMPENSATION_RECOVERY_REQUIRED)
        return _verdict(
            mapped, lock_verdict["reasons"], plan_id=plan_id, driver_engaged=True,
        )
    try:
        outcome = _under_lock(
            plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
            lock_verdict=lock_verdict, authorization_set=authorization_set,
            component_intents=component_intents, ownership_evidence=ownership_evidence,
            startup_journal_paths=startup_journal_paths,
            startup_observed_state_digests=startup_observed_state_digests,
            startup_task_owned_partials=startup_task_owned_partials,
            probe_receipt_digests=probe_receipt_digests, tick=tick,
        )
    except BaseException:
        # 崩潰(JournalCrash)也必須把 FD 放掉;它沒有 typed verdict,故不再加工。
        _lock.release_s2_4_install_lock(lock_driver, lock_verdict)
        raise
    release = _lock.release_s2_4_install_lock(lock_driver, lock_verdict)
    return _fold_release_into_startup_verdict(outcome, release, plan_id=plan_id)


def _release_is_clean(
    outcome: dict[str, Any], release: dict[str, Any], *, plan_id: str
) -> dict[str, Any] | None:
    """lock 釋放的**政策**取自 ``install_driver``;乾淨即回折好的 outcome,否則回 ``None``。

    「未乾淨釋放 ⇒ 整份結果降為 ``RECOVERY_REQUIRED``」這條政策的擁有者是
    :func:`agent_governance_s2_4_install_driver._fold_lock_release`;抄一份等於製造第二份判準。
    但它的失敗分支回的是 **aggregate 交易的** verdict 形狀(``s2_4_install_transaction_verdict``
    + receipt enum 的 status),而本模組刻意不借用那個 namespace(§B.6),故呼叫端只取它的
    **決定**,再把結果投影回本模組自己的 informal verdict。
    """

    folded = _install_driver._fold_lock_release(outcome, release, plan_id=plan_id)
    if folded.get("schema_version") == outcome.get("schema_version"):
        return folded
    return None


def _fold_release_into_startup_verdict(
    outcome: dict[str, Any], release: dict[str, Any], *, plan_id: str
) -> dict[str, Any]:
    """把 lock 釋放結果折進**補償** verdict(未乾淨釋放 → 整份降為 RECOVERY_REQUIRED)。"""

    clean = _release_is_clean(outcome, release, plan_id=plan_id)
    if clean is not None:
        return clean
    folded = _install_driver._fold_lock_release(outcome, release, plan_id=plan_id)
    return _verdict(
        STARTUP_COMPENSATION_RECOVERY_REQUIRED,
        list(folded.get("reasons") or []),
        plan_id=plan_id,
        mutation_performed=bool(outcome.get("mutation_performed")),
        driver_engaged=True,
        reconcile=outcome.get("reconcile"),
        row_classification=outcome.get("row_classification"),
        reverse_ops=outcome.get("reverse_ops"),
        rollback=outcome.get("rollback"),
        journal=outcome.get("journal"),
        residue=outcome.get("residue"),
        lock_release=dict(release),
    )


def _under_lock(
    *,
    plan: dict[str, Any],
    plan_id: str,
    driver: Any,
    file_driver: Any,
    lock_verdict: dict[str, Any],
    authorization_set: Any,
    component_intents: Any,
    ownership_evidence: Any,
    startup_journal_paths: Any,
    startup_observed_state_digests: Any,
    startup_task_owned_partials: Any,
    probe_receipt_digests: Any,
    tick: Callable[[], datetime],
) -> dict[str, Any]:
    """握著 install lock 的那一段(S1-S2c + 逆序鏈);呼叫端負責釋放並折入釋放結果。"""

    # ── S1:§5.2 啟動 reconcile(零變更;只讀 journal 與 caller 的獨立觀測)──────────
    #
    # caller 遞交的 probe/prepare lane id 一律經 ``rederive_lane_path`` 重算,畸形值是 typed
    # 契約層硬錯。它必須在**這裡**被轉譯成本模組的 typed verdict:公開 docstring 承諾「任何一道
    # 不過即 typed 非成功」,而 ``reconcile_before_s2_4_intent`` 對同一類輸入早就是 typed 轉譯
    # ——兩個公開面對同一種畸形輸入給出不同判準,本身就是一道判準漂移。
    try:
        journal_paths = _reconcile.startup_journal_paths(plan_id, startup_journal_paths)
    except _reconcile.InstallDriverContractError as error:
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED,
            [
                "a supplied startup journal lane id could not be re-derived into its §5.2 path "
                f"({error.code}); a caller string is never joined into the state root. "
                "Zero mutation"
            ],
            plan_id=plan_id, driver_engaged=True,
        )
    reconcile = _reconcile.reconcile_startup_journals(
        file_driver,
        journal_paths=journal_paths,
        observed_state_digests=startup_observed_state_digests,
        task_owned_partials=startup_task_owned_partials,
        ownership_evidence=ownership_evidence,
        lock_verdict=lock_verdict,
    )
    gate = _reverse_compensation_gate(reconcile)
    if gate["status"] != STARTUP_COMPENSATION_COMPLETED_EXACT:
        return _verdict(
            gate["status"], gate["reasons"], plan_id=plan_id, driver_engaged=True,
            reconcile=reconcile,
        )
    # ── S2b:journal 讀回 + plan 身分四欄 ────────────────────────────────────────
    store = _journal.JournalStore(
        file_driver, journal_path=_journal.install_journal_path(plan_id)
    )
    read = store.load()
    if read["status"] != _journal.JOURNAL_STATUS_LOADED:
        return _verdict(
            STARTUP_COMPENSATION_JOURNAL_CORRUPT
            if read["status"] == _journal.JOURNAL_STATUS_CORRUPT
            else STARTUP_COMPENSATION_RECOVERY_REQUIRED,
            list(read["reasons"]) + [
                "the durable APPLY journal for this plan could not be read back under the "
                "install lock, so nothing describes what to undo; zero mutation"
            ],
            plan_id=plan_id, driver_engaged=True, reconcile=reconcile,
        )
    journal = read["journal"]
    identity_reasons = journal_plan_identity_reasons(journal, plan)
    if identity_reasons:
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED, identity_reasons,
            plan_id=plan_id, driver_engaged=True, reconcile=reconcile, journal=journal,
        )
    # ── S2c:那兩張 permit 真的被燒掉過(本元件最重要的安全性質)───────────────────
    ledger_store = _journal.JournalStore(
        file_driver, journal_path=_lock.REPLAY_LEDGER_PATH
    )
    ledger_read = _lock.read_durable_ledger(
        ledger_store, ledger_path=_lock.REPLAY_LEDGER_PATH
    )
    if ledger_read["status"] != "LEDGER_LOADED":
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED,
            list(ledger_read["reasons"]) + [
                f"the replay ledger could not be read as a durable head ({ledger_read['status']}); "
                "without it nothing proves this plan's APPLY ever consumed its two operator "
                "permits, and an unproven consumption makes this surface a permit-free "
                "destructive tool (§9.1). Zero mutation"
            ],
            plan_id=plan_id, driver_engaged=True, reconcile=reconcile, journal=journal,
        )
    permit_reasons = replay_consumption_reasons(
        ledger_read["ledger"], plan, authorization_set
    )
    if permit_reasons:
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED, permit_reasons,
            plan_id=plan_id, driver_engaged=True, reconcile=reconcile, journal=journal,
        )
    # ── §B.3 (c) 的輸入:五份 intent 必須綁回已簽的 plan core ────────────────────
    intent_reasons = component_intent_binding_reasons(plan, component_intents)
    if intent_reasons:
        return _verdict(
            STARTUP_COMPENSATION_RECOVERY_REQUIRED, intent_reasons,
            plan_id=plan_id, driver_engaged=True, reconcile=reconcile, journal=journal,
        )
    return _run_reverse_chain(
        plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
        journal=journal, store=store, component_intents=component_intents,
        probe_receipt_digests=probe_receipt_digests, reconcile=reconcile, tick=tick,
    )


def _reverse_compensation_gate(reconcile: dict[str, Any]) -> dict[str, Any]:
    """S2:收斂必須**恰為** install lane 的 ``COMPENSATE_REVERSE_ORDER``。

    §5.4 的五 row 逆序鏈只對 install lane 有定義(probe / PREPARE 各自有 cleanup 契約,不是這條
    鏈)。所以 probe/prepare lane 的 COMPENSATE 一律 typed
    :data:`STARTUP_COMPENSATION_LANE_UNSUPPORTED`,而不是被這條鏈「順便」處理掉。
    """

    status = reconcile.get("status")
    lanes = reconcile.get("lanes") or {}
    if status in _reconcile.RECONCILE_ADMITS_NEW_WORK:
        return {
            "status": STARTUP_COMPENSATION_NOT_APPLICABLE,
            "reasons": [
                "startup reconciliation found nothing to compensate on any §5.2 lane "
                f"({status}); zero mutation and no reverse compensation was attempted"
            ],
        }
    if status == _reconcile.RECONCILE_STATUS_CORRUPT:
        return {
            "status": STARTUP_COMPENSATION_JOURNAL_CORRUPT,
            "reasons": list(reconcile.get("reasons") or []),
        }
    if status != _reconcile.RECONCILE_STATUS_COMPENSATE:
        return {
            "status": (
                STARTUP_COMPENSATION_PENDING
                if status == _reconcile.RECONCILE_STATUS_PENDING
                else STARTUP_COMPENSATION_RECOVERY_REQUIRED
            ),
            "reasons": list(reconcile.get("reasons") or []) + [
                f"startup reconciliation converged to {status!r}, not to the task-owned partial "
                "state that §5.4 reverse compensation is defined for; zero mutation"
            ],
        }
    compensating_lanes = sorted(
        lane for lane, verdict in lanes.items()
        if (verdict or {}).get("status") == _reconcile.RECONCILE_STATUS_COMPENSATE
    )
    unsupported = [lane for lane in compensating_lanes if not lane.startswith("install")]
    if unsupported or "install" not in compensating_lanes:
        return {
            "status": STARTUP_COMPENSATION_LANE_UNSUPPORTED,
            "reasons": [
                f"lane(s) {compensating_lanes} reconcile to COMPENSATE_REVERSE_ORDER, but the "
                "§5.4 five-row reverse chain is defined only for the install lane (probe and "
                "PREPARE carry their own cleanup contracts). RECOVERY_REQUIRED with zero "
                "mutation; an operator resolves the other lane first"
            ],
        }
    return {"status": STARTUP_COMPENSATION_COMPLETED_EXACT, "reasons": []}


def _run_reverse_chain(
    *,
    plan: dict[str, Any],
    plan_id: str,
    driver: Any,
    file_driver: Any,
    journal: dict[str, Any],
    store: Any,
    component_intents: Any,
    probe_receipt_digests: Any,
    reconcile: dict[str, Any],
    tick: Callable[[], datetime],
) -> dict[str, Any]:
    """§B.4:逐 row 前後各寫 WAL 的逆序鏈(比交易內版本更強,而那是對的)。

    交易內版本只寫**一筆**交易級 ``COMPENSATING``,因為五 row 的補償在同一個行程內一氣呵成。
    啟動補償器不同:它本身就可能再崩一次,而「鏈中崩潰」若不可分辨,下一次重啟就會對一台
    被拆到一半的主機再猜一次。故每一 row 前後各一筆 durable 記錄。

    **撤回(E2 S2E.2b-1 P1-1)**:本函式先前宣稱「``pre_compensation_observed_digest`` 的
    durable 替身**只能是** WAL 上該 row driver 寫的 post_state_digest」,以及「收緊它需要 W4b
    的 ``OBSERVER_SPACE_PRE_STATE_DIGEST``」。兩句都不成立——
    :func:`agent_governance_s2_4_component.capture_pre_compensation_observation` 本來就存在、
    唯讀、零新主機能力,mid-effect row 的交易內補償路徑已經在用它,形狀與此處完全同構。舊寫法
    把 applier 空間的值餵進一個 verifier 空間的不等式,那道「排除常量 verifier」的判準因此恆真、
    形同不存在;現在改由同一支獨立 verifier 在補償前後各觀測一次。
    """

    del file_driver  # journal store 已綁住同一支;此處不再另取檔案面。
    classification = classify_journal_rows(journal)
    transaction = _journal.WriteAheadTransaction(
        store,
        build_journal=lambda entries, terminal: _journal.build_install_journal(
            plan_id=plan_id,
            plan_core_digest=plan["core_digest"],
            idempotency_key=plan_id,
            expected_pre_state_digest=plan["core"]["pre_state_digest"],
            aggregate_rollback_digest=_install_driver.aggregate_rollback_digest(
                plan_id=plan_id
            ),
            entries=entries, terminal=terminal,
        ),
        clock=tick,
    )
    # append-only 的 ``seq`` 必須從**磁碟上已有的**最後一筆續下去:從 0 重數會讓整本 WAL 的
    # 序列契約當場失效(``journal_entry_sequence_errors``),而那是 commit 前的硬檢。
    transaction.entries = [dict(entry) for entry in journal["entries"]]
    transaction.committed_entries = [dict(entry) for entry in journal["entries"]]

    reasons: list[str] = []
    reverse_ops: list[dict[str, Any]] = []
    compensated_rows: list[str] = []
    exact = True
    mutation_performed = False
    daemon_reload = False
    hba_reload = False
    for name in _install_driver.REVERSE_COMPENSATION_ORDER:
        digest = _install_driver.per_row_rollback_digest(
            plan_id=plan_id, component_effect_class=name
        )
        row = classification[name]
        if row["classification"] == ROW_NO_DELTA:
            # 從未施作 → 沒有 delta 需要還原(§5.4 只移除證明為 absent 的新增物)。
            reverse_ops.append({
                "component_effect_class": name, "per_row_rollback_digest": digest,
                "ownership_verified": True,
            })
            continue
        ownership_verified = _row_ownership_verified(
            journal=journal, component_effect_class=name, component_intents=component_intents
        )
        if not ownership_verified:
            reasons.append(
                f"{name}: no journal entry written by that row's own driver records a "
                "pre_state_digest equal to the plan-bound intent pre-state, so the §5.4 "
                "ownership-aware condition is NOT established for its reverse op"
            )
        # ── 前 WAL:方向是**反的**(pre = 已施作態,post = 原前態)──────────────
        before = transaction.record(
            state="COMPENSATING",
            pre_state_digest=row["row_applied_state_digest"] or plan["core"]["pre_state_digest"],
            post_state_digest=row["row_pre_state_digest"] or plan["core"]["pre_state_digest"],
            step_index=_install_driver.APPLY_ROW_STEP_INDEX[name],
            terminal=False,
            entry_source=_row_compensation_entry_source(),
            component_effect_class=name,
        )
        if before["status"] != _journal.JOURNAL_STATUS_COMMITTED:
            # 一步都不做,整鏈中止:un-journalled compensation 是所有結局裡最壞的一種——主機被
            # 拆了而磁碟上沒有任何證據,下一次重啟會對一台半拆主機收斂出 RESUME_VERIFICATION。
            residue = _install_driver.observe_residue(
                driver, dict(probe_receipt_digests or {})
            )
            return _verdict(
                STARTUP_COMPENSATION_RECOVERY_REQUIRED,
                reasons + list(before["reasons"]) + [
                    f"the per-row COMPENSATING write-ahead record for {name} could not be "
                    "durably committed, so NO reverse compensation was attempted from this row "
                    "onward; RECOVERY_REQUIRED with the exact residual recorded (§5.2)"
                ],
                plan_id=plan_id, mutation_performed=mutation_performed, driver_engaged=True,
                reconcile=reconcile, row_classification=classification,
                reverse_ops=reverse_ops, journal=journal, residue=residue,
            )
        # ── 補償**之前**先取 verifier 並唯讀觀測一次(§B.4;整條鏈的順序關鍵)────────
        #
        # ``COMPENSATED_EXACT`` 唯一能排除「對任何 subject 都回同一份乾淨觀測」的常量 verifier
        # 的手段,就是「補償後那次觀測 ≠ 補償前那次觀測」。而那個前值必須與後值落在**同一個
        # digest 空間**(同一支獨立 verifier 的投影)才比得起來:跨空間的兩個值恆不相等,這道
        # 判準就會恆真、形同不存在。故此處呼叫 ``capture_pre_compensation_observation``
        # ——它唯讀(只跑 ``independent_postcheck``)、零新主機能力,而 mid-effect row 的交易內
        # 補償路徑(``_component._compensating_failure``)用的就是同一支。
        #
        # 次序同時修掉一個實作風險:``row_driver()`` 若在補償**之後**才取而它拋了例外,主機
        # 已經被改而完全沒有 verifier 可用。先取,拿不到就誠實地在無 verifier 之下補償(delta
        # 一律不跳過),並停在 typed 未證。
        try:
            row_driver = driver.row_driver(component_effect_class=name)
        except Exception as error:  # noqa: BLE001
            # C2 的教訓:主機部分施作時,這是最不能讓 untyped 例外逸出的時刻。
            row_driver = None
            exact = False
            reasons.append(
                f"{name} row driver was unavailable before compensation: "
                f"{_component.redact_driver_error(error)}; the reverse op cannot be "
                "independently re-observed, so exact restoration is not claimed"
            )
        applier_node = f"s2-4-{name.lower()}-applier"
        pre_observed = (
            None if row_driver is None
            else _component.capture_pre_compensation_observation(
                row_driver, component_effect_class=name,
                install_plan_digest=plan["core_digest"], applier_node=applier_node,
            )
        )
        try:
            outcome = driver.compensate_component_row(
                component_effect_class=name, plan_id=plan_id,
                per_row_rollback_digest=digest, ownership_verified=ownership_verified,
            )
        except Exception as error:  # noqa: BLE001
            exact = False
            mutation_performed = True
            reasons.append(
                f"{name} reverse compensation failed: "
                f"{_component.redact_driver_error(error)}"
            )
            reverse_ops.append({
                "component_effect_class": name, "per_row_rollback_digest": digest,
                "ownership_verified": False,
            })
            _record_row_terminal(transaction, name, row, plan, compensated=False)
            continue
        mutation_performed = True
        normalized, independent = _component.compensation_with_independent_postcheck(
            outcome, driver=row_driver, component_effect_class=name,
            install_plan_digest=plan["core_digest"], applier_node=applier_node,
            pre_state_digest=plan["core"]["pre_state_digest"],
            # 拿不到補償前觀測(verifier 不在/逸出/形狀不符)時一律遞交 ``None`` ⇒ typed
            # ``POST_COMPENSATION_PRE_OBSERVATION_UNPROVEN`` ⇒ 不宣稱 exact。**絕不**在此
            # 塞一個 WAL 上的 applier 空間 digest 當替身:那與 verifier 空間的後值恆不相等,
            # 會讓這道檢查恆真,而「恆真的排除力」就是「沒有排除力」。
            pre_compensation_observed_digest=pre_observed,
        )
        status, row_exact = _component.derive_compensation_status(normalized)
        reasons.extend(independent["reasons"])
        if not row_exact:
            exact = False
            reasons.append(
                f"{name} reverse compensation did not prove exact pre-state restoration "
                f"({status})"
            )
        if name == "ENGINE_SCANNER":
            daemon_reload = bool((outcome or {}).get("daemon_reload_reasserted"))
            if not daemon_reload:
                exact = False
                reasons.append(
                    "a unit-byte rollback must re-run the typed daemon-reload and verify the "
                    "restored FragmentPath/digest/load state (§5.4)"
                )
        if name == "PG_ROLE_ACL_MIGRATION":
            hba_reload = bool((outcome or {}).get("hba_reload_reasserted"))
            if not hba_reload:
                exact = False
                reasons.append(
                    "an HBA rollback must use the topology-attested reload operation id and "
                    "then verify active HBA rules, cluster identity and connectivity (§5.4)"
                )
            if (outcome or {}).get("observer_role_preserved") is not True:
                exact = False
                reasons.append(
                    "the PG reverse op did not confirm aiml_observer_ro is preserved; S2.4 "
                    "never drops the observer role (§5.4)"
                )
        compensated_rows.append(name)
        reverse_ops.append({
            "component_effect_class": name, "per_row_rollback_digest": digest,
            "ownership_verified": bool(ownership_verified and row_exact),
        })
        after = _record_row_terminal(transaction, name, row, plan, compensated=row_exact)
        if after["status"] != _journal.JOURNAL_STATUS_COMMITTED:
            exact = False
            reasons.append(
                f"the per-row terminal record for {name} could not be fsynced; the reverse op "
                "happened but is not durably recorded"
            )
    return _finish_reverse_chain(
        plan=plan, plan_id=plan_id, driver=driver, transaction=transaction,
        classification=classification, reverse_ops=reverse_ops,
        compensated_rows=compensated_rows, reasons=reasons, exact=exact,
        mutation_performed=mutation_performed, daemon_reload=daemon_reload,
        hba_reload=hba_reload, probe_receipt_digests=probe_receipt_digests,
        reconcile=reconcile, tick=tick,
    )


def _row_compensation_entry_source() -> str:
    """本模組寫的每一筆 row 級補償 entry 的 ``entry_source``。

    ``agent_governance_s2_4_journal`` 對 :data:`ENTRY_SOURCE_COMPONENT_ROW` 的定義是「由**該
    row 的 driver** 寫入」。啟動補償器不是任何一 row 的 driver——它是 aggregate 級的 runner,
    只是把該 row 自己寫過的兩個 digest 逐位元組轉抄進逆向 entry。標成 COMPONENT_ROW 會在
    「補償鏈中崩 → 第二次啟動」時反噬::func:`classify_journal_rows` 的
    ``row_driver_entries[-1]`` 會取到補償器自己那一筆,把「這一列被施作成什麼樣」讀成「這一列
    已被還原成什麼樣」。故一律 AGGREGATE(digest 空間的事實記在轉抄處的註解,不靠判別欄說謊)。
    """

    return _journal.ENTRY_SOURCE_AGGREGATE


def _record_row_terminal(
    transaction: Any, name: str, row: dict[str, Any], plan: dict[str, Any], *, compensated: bool
) -> dict[str, Any]:
    """後 WAL(``COMPENSATED`` / ``FAILED``);``terminal`` 恆 ``False``。

    ``reconcile_journal`` 要求 ``state ∈ TERMINAL`` **且** ``journal["terminal"] is True`` 才算
    「無需收斂」,所以只要鏈中每一筆都 ``terminal=False``,鏈中崩潰重啟後仍然走四分收斂——
    一筆 row 級的 ``COMPENSATED`` 永遠不會被誤讀成整筆交易的終端。
    """

    return transaction.record(
        state="COMPENSATED" if compensated else "FAILED",
        pre_state_digest=row["row_applied_state_digest"] or plan["core"]["pre_state_digest"],
        post_state_digest=row["row_pre_state_digest"] or plan["core"]["pre_state_digest"],
        step_index=_install_driver.APPLY_ROW_STEP_INDEX[name],
        terminal=False,
        entry_source=_row_compensation_entry_source(),
        component_effect_class=name,
    )


def _finish_reverse_chain(
    *,
    plan: dict[str, Any],
    plan_id: str,
    driver: Any,
    transaction: Any,
    classification: dict[str, Any],
    reverse_ops: list[dict[str, Any]],
    compensated_rows: list[str],
    reasons: list[str],
    exact: bool,
    mutation_performed: bool,
    daemon_reload: bool,
    hba_reload: bool,
    probe_receipt_digests: Any,
    reconcile: dict[str, Any],
    tick: Callable[[], datetime],
) -> dict[str, Any]:
    """§B.5 終端:獨立殘留觀測 → rollback artifact → 終端 journal。"""

    residue = _install_driver.observe_residue(driver, dict(probe_receipt_digests or {}))
    if residue["installed_unit_inactive"] is not True:
        exact = False
        reasons.extend(residue["reasons"])
        if residue["observation_status"] == _evidence.RESIDUE_OBSERVATION_UNAVAILABLE:
            reasons.append(
                "the post-compensation unit observation was UNAVAILABLE, not negative; "
                "'could not observe' is NOT 'observed clean', so no result may claim an "
                "independently confirmed clean residue"
            )
    rollback = _install_driver.build_install_rollback(
        plan=plan, reverse_ops=reverse_ops, exact=exact,
        post_state_digest=central_validator.canonical_digest({
            "domain": STARTUP_ROLLBACK_POST_STATE_DOMAIN,
            "plan_id": plan_id,
            "compensated_rows": list(compensated_rows),
            "row_classification": {
                name: row["classification"] for name, row in sorted(classification.items())
            },
        }),
        daemon_reload_reasserted=daemon_reload, hba_reload_reasserted=hba_reload, clock=tick,
    )
    rollback_errors = central_validator.validate_aiml_artifact(rollback)
    if rollback_errors:
        exact = False
        reasons.extend(rollback_errors)
    journal = _install_driver.terminal_journal(
        transaction, None, plan, tick, compensated=exact
    )
    if journal is None:
        exact = False
        reasons.append(
            "the terminal compensation journal could not be fsynced; RECOVERY_REQUIRED"
        )
    status = (
        STARTUP_COMPENSATION_COMPLETED_EXACT if exact
        else STARTUP_COMPENSATION_RECOVERY_REQUIRED
    )
    return _verdict(
        status,
        reasons + [
            "the task-owned delta recorded in the durable APPLY journal was compensated in "
            "reverse §5.4 order and every reverse op was confirmed by an INDEPENDENT "
            "post-compensation re-observation. This does NOT reopen the lane: both operator "
            "permits are durably burnt and are never released by a rollback, and re-running "
            "this plan reads a terminal COMPENSATED journal and stops at RECOVERY_REQUIRED. "
            "The next step is an operator-signed NEW plan with fresh permits"
            if exact else
            "safe exact compensation could not be proved; the service stays disabled/inactive, "
            "RECOVERY_REQUIRED records the exact residual and blocks S2.5 (§5.4)"
        ],
        plan_id=plan_id, mutation_performed=mutation_performed, driver_engaged=True,
        reconcile=reconcile, row_classification=classification, reverse_ops=reverse_ops,
        rollback=rollback, journal=journal, residue=residue,
    )


# --------------------------------------------------------------------------- #
# §C:新 probe / PREPARE intent 之前的 journal-routed 收斂閘
# --------------------------------------------------------------------------- #
def _intent_verdict(
    status: str,
    reasons: list[str],
    *,
    lane: str | None = None,
    lane_path: str | None = None,
    admits_new_work: Any = False,
    driver_engaged: bool = False,
    reconcile: dict[str, Any] | None = None,
    intent_result: Any = None,
    intent_executed: bool = False,
    new_obligations: list[str] | None = None,
    lock_release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """§C 的單一出境面。

    ``admits_new_work`` 逐位元組轉述 :func:`reconcile_before_new_intent` 的三態:``True`` /
    ``False`` / ``None``。``None`` 是「**沒能建立**收斂」——它既不是「乾淨」也不是「不乾淨」,
    把它折成 ``False`` 會讓「沒有 durable journal 面」讀起來像「有殘留」,折成 ``True`` 則是
    直接放行。三態原樣保留是唯一誠實的形狀。
    """

    return {
        "schema_version": INTENT_GATE_SCHEMA_VERSION,
        "status": status,
        "reasons": list(reasons),
        "lane": lane,
        "lane_path": lane_path,
        "admits_new_work": admits_new_work,
        "intent_executed": bool(intent_executed),
        "intent_result": intent_result,
        "new_obligations": list(new_obligations or []),
        "driver_engaged": bool(driver_engaged),
        "reconcile": reconcile,
        "lock_release": lock_release,
        "mutation_performed": bool(intent_executed),
        "emits_effect_receipt": False,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
    }


def dispatch_startup_reconcile(outcome: Any, *, lane: str) -> dict[str, Any]:
    """§C.2 的分流矩陣。**一律 branch on ``admits_new_work``,絕不 branch 字串。**

    status 字串是給人讀的;``admits_new_work`` 才是那份 verdict 對「能不能開始新工作」的裁決。
    先看字串再決定,等於在收斂端重新實作一次收斂判準——兩份判準遲早分岔,而分岔的方向是放行。
    """

    admits = (outcome or {}).get("admits_new_work")
    status = (outcome or {}).get("status")
    lanes = (outcome or {}).get("lanes") or {}
    reasons = list((outcome or {}).get("reasons") or [])
    if admits is True:
        return {"status": INTENT_GATE_ADMITTED, "reasons": reasons, "obligations": []}
    if admits is None:
        # 「沒能建立」≠「乾淨」:``SURFACE_ABSENT`` 原樣轉述,絕不冒充成已收斂。
        return {
            "status": INTENT_GATE_SURFACE_ABSENT, "reasons": reasons, "obligations": [],
        }
    if status == _reconcile.RECONCILE_STATUS_CORRUPT:
        return {"status": INTENT_GATE_JOURNAL_CORRUPT, "reasons": reasons, "obligations": []}
    if status == _reconcile.RECONCILE_STATUS_LOCK_REQUIRED:
        return {"status": INTENT_GATE_LOCK_HELD, "reasons": reasons, "obligations": []}
    if status == _reconcile.RECONCILE_STATUS_PENDING:
        return {"status": INTENT_GATE_PENDING, "reasons": reasons, "obligations": []}
    if status == _reconcile.RECONCILE_STATUS_RESUME:
        return {
            "status": INTENT_GATE_RECOVERY_REQUIRED,
            "reasons": reasons + [
                "the interrupted step converged to RESUME_VERIFICATION, whose correct next "
                "action is to re-run ONLY that step's verification path — and neither the "
                "capability probe nor PREPARE exposes a verify-only entry point today. This "
                "surface refuses rather than inventing one: a blind re-run would repeat an "
                "external effect with no write-ahead record of the repeat. RECOVERY_REQUIRED "
                "with zero mutation; the gap is recorded as an obligation"
            ],
            "obligations": [RESUME_VERIFICATION_OBLIGATION],
        }
    if status == _reconcile.RECONCILE_STATUS_COMPENSATE:
        compensating = sorted(
            key for key, verdict in lanes.items()
            if (verdict or {}).get("status") == _reconcile.RECONCILE_STATUS_COMPENSATE
        )
        if any(key == "install" or key.startswith("install:") for key in compensating):
            return {
                "status": INTENT_GATE_INSTALL_COMPENSATION_REQUIRED,
                "reasons": reasons + [
                    "the install lane holds a task-owned partial state with a valid journal "
                    "ownership binding; §5.4 reverse compensation must run first via "
                    "compensate_s2_4_startup_residue (it needs the signed plan, the five "
                    "plan-bound component intents and the two burnt operator permits, none of "
                    f"which this {lane} intent gate has). Zero mutation"
                ],
                "obligations": [],
            }
        return {
            "status": INTENT_GATE_LANE_UNSUPPORTED,
            "reasons": reasons + [
                f"lane(s) {compensating} converged to COMPENSATE_REVERSE_ORDER, but the §5.4 "
                "five-row reverse chain is defined only for the install lane; probe and "
                "PREPARE carry their own cleanup contracts and an operator resolves them"
            ],
            "obligations": [],
        }
    return {
        "status": INTENT_GATE_RECOVERY_REQUIRED, "reasons": reasons, "obligations": [],
    }


def reconcile_before_s2_4_intent(
    driver: Any = None,
    *,
    lane: str,
    lane_id: Any,
    intent_driver: Any = None,
    build_journal: Callable[[list[dict[str, Any]], bool], dict[str, Any]] | None = None,
    run_intent: Callable[[Any], Any] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """§5.2 前置:接受一個新的 probe / PREPARE intent **之前**先收斂任何非終端 journal。

    固定閘序(§C.1,每一步都有既存錨點):

      1. **先** lock。``reconcile_startup_journals`` 先問 lock 再問 driver,所以倒過來會讓
         「driver=None ∧ 無 lock」回報 ``EXTERNAL_VERIFICATION_PENDING`` —— 那句話讀起來像
         「只差一個主機面就成」,實際上連 §5.2 的准入前提都不成立;
      2. 把該進入點的 host driver 包進
         :class:`agent_governance_s2_4_reconcile.JournalRoutedDriver`(綁該 lane 的
         :class:`JournalStore` 與**已取得**的 lock),於是它的每一次 ``journal_transition``
         都經 durable WAL 落盤;
      3. ``reconcile_before_new_intent`` 自 ``startup_reconcile_surface()`` 取回檔案面與 lock
         裁決並跑真正的收斂;
      4. §C.2 分流(一律 branch on ``admits_new_work``);
      5. ``finally`` 釋放 lock 並把釋放結果折入。

    ``run_intent`` 是「被閘保護的那件事」:它**只**在收斂放行時被呼叫,且在**同一把 lock 之下**
    收到已包好的 driver。這不是可有可無的便利參數——把閘與 intent 拆成兩次 lock 會留下一個
    TOCTOU 窗:閘說「乾淨」、鎖放掉、另一個 writer 動手、然後 intent 才開始。缺席時本函式是
    一個純粹的 dry-run 閘(零主機變更)。

    APPLY lane 不走這裡:``apply_s2_4_install_plan`` 已在它自己那把 lock 下做同一件事,只需要
    餵它四個 ``startup_*`` 參數(見 :data:`INTENT_GATE_LANES`)。
    """

    tick = clock or (lambda: datetime.now(timezone.utc))
    if lane not in INTENT_GATE_LANES:
        return _intent_verdict(
            INTENT_GATE_RECOVERY_REQUIRED,
            [
                f"the startup intent gate covers {list(INTENT_GATE_LANES)}; the APPLY lane "
                "reconciles inside apply_s2_4_install_plan under its own install lock, and "
                "wrapping it here would take a second lock for the same work"
            ],
            lane=lane,
        )
    try:
        lane_path = _reconcile.rederive_lane_path(lane, lane_id)
    except _reconcile.InstallDriverContractError as error:
        return _intent_verdict(
            INTENT_GATE_RECOVERY_REQUIRED,
            [
                f"the {lane} journal path could not be re-derived from the supplied id "
                f"({error.code}); a caller string is never joined into the §5.2 state root"
            ],
            lane=lane,
        )
    if driver is None:
        return _intent_verdict(
            INTENT_GATE_PENDING,
            [
                "the §5.2 startup reconciliation is reachable but authority-locked: no host "
                "lock/file surface is present (Mac/source/test lane); "
                "EXTERNAL_VERIFICATION_PENDING with zero mutation"
            ],
            lane=lane, lane_path=lane_path,
        )
    try:
        lock_driver = driver.lock_driver()
        file_driver = driver.file_driver()
    except Exception as error:  # noqa: BLE001
        return _intent_verdict(
            INTENT_GATE_RECOVERY_REQUIRED,
            [
                "the driver could not supply its lock/file surfaces: "
                f"{_component.redact_driver_error(error)}"
            ],
            lane=lane, lane_path=lane_path, driver_engaged=True,
        )
    # ── (1) lock-first ─────────────────────────────────────────────────────────
    lock_verdict = _lock.acquire_s2_4_install_lock(lock_driver)
    if lock_verdict["status"] != _lock.LOCK_STATUS_ACQUIRED:
        mapped = {
            _lock.LOCK_STATUS_HELD: INTENT_GATE_LOCK_HELD,
            _lock.LOCK_STATUS_PENDING: INTENT_GATE_PENDING,
        }.get(lock_verdict["status"], INTENT_GATE_RECOVERY_REQUIRED)
        return _intent_verdict(
            mapped, lock_verdict["reasons"], lane=lane, lane_path=lane_path,
            driver_engaged=True,
        )
    try:
        outcome = _gate_under_lock(
            lane=lane, lane_path=lane_path, intent_driver=intent_driver,
            file_driver=file_driver, lock_verdict=lock_verdict,
            build_journal=build_journal, run_intent=run_intent, tick=tick,
        )
    except BaseException:
        _lock.release_s2_4_install_lock(lock_driver, lock_verdict)
        raise
    release = _lock.release_s2_4_install_lock(lock_driver, lock_verdict)
    clean = _release_is_clean(outcome, release, plan_id=lane_path)
    if clean is not None:
        return clean
    folded = _install_driver._fold_lock_release(outcome, release, plan_id=lane_path)
    return _intent_verdict(
        INTENT_GATE_RECOVERY_REQUIRED, list(folded.get("reasons") or []),
        lane=lane, lane_path=lane_path,
        admits_new_work=outcome.get("admits_new_work"),
        driver_engaged=True, reconcile=outcome.get("reconcile"),
        intent_result=outcome.get("intent_result"),
        intent_executed=bool(outcome.get("intent_executed")),
        new_obligations=outcome.get("new_obligations"),
        lock_release=dict(release),
    )


def _gate_under_lock(
    *,
    lane: str,
    lane_path: str,
    intent_driver: Any,
    file_driver: Any,
    lock_verdict: dict[str, Any],
    build_journal: Callable[[list[dict[str, Any]], bool], dict[str, Any]] | None,
    run_intent: Callable[[Any], Any] | None,
    tick: Callable[[], datetime],
) -> dict[str, Any]:
    """握著 install lock 的那一段(wrap → reconcile → 分流 → 放行時跑 intent)。"""

    wrapped = _reconcile.JournalRoutedDriver(
        intent_driver,
        store=_journal.JournalStore(file_driver, journal_path=lane_path),
        # ``build_journal`` 只在該 intent 真的做出一次 state 轉移時才被呼叫;收斂本身零變更。
        # 缺席時給一個 typed raise 的替身,而不是一個「看起來能用」的空 journal builder。
        build_journal=build_journal or _refuse_journal_build,
        lock_verdict=lock_verdict, clock=tick, step_index=None, transaction=None,
    )
    reconcile = _reconcile.reconcile_before_new_intent(
        wrapped, lane=lane, lane_path=lane_path
    )
    decision = dispatch_startup_reconcile(reconcile, lane=lane)
    if decision["status"] != INTENT_GATE_ADMITTED:
        return _intent_verdict(
            decision["status"], decision["reasons"], lane=lane, lane_path=lane_path,
            admits_new_work=reconcile.get("admits_new_work"), driver_engaged=True,
            reconcile=reconcile, new_obligations=decision["obligations"],
        )
    if run_intent is None:
        return _intent_verdict(
            INTENT_GATE_ADMITTED,
            decision["reasons"] + [
                "startup reconciliation admits a new intent on this lane; no intent callable "
                "was supplied, so this call is a dry-run gate with zero mutation"
            ],
            lane=lane, lane_path=lane_path, admits_new_work=True, driver_engaged=True,
            reconcile=reconcile,
        )
    try:
        result = run_intent(wrapped)
    except Exception as error:  # noqa: BLE001
        return _intent_verdict(
            INTENT_GATE_RECOVERY_REQUIRED,
            decision["reasons"] + [
                "the admitted intent raised under the install lock: "
                f"{_component.redact_driver_error(error)}; whatever it durably wrote is on the "
                "WAL and the next startup reconciles from there"
            ],
            lane=lane, lane_path=lane_path, admits_new_work=True, driver_engaged=True,
            reconcile=reconcile, intent_executed=True,
        )
    return _intent_verdict(
        INTENT_GATE_ADMITTED, decision["reasons"], lane=lane, lane_path=lane_path,
        admits_new_work=True, driver_engaged=True, reconcile=reconcile,
        intent_result=result, intent_executed=True,
    )


def _refuse_journal_build(entries: Any, terminal: Any) -> dict[str, Any]:
    """沒有 journal builder 就不可能有 durable WAL —— typed raise,絕不落一本空 journal。"""

    del entries, terminal
    raise _reconcile.InstallDriverContractError(
        "startup_intent_gate_requires_a_lane_journal_builder"
    )

"""Intent-derived target-host effect APPLY orchestrator (AIML S1 formal-closure Wave B1).

把 S1.6B target-host 探針從「有 schema/adapter/closure 綁定」推進到「可被真正驅動」的一條
intent-derived APPLY 軌:一個 admitted-intent applier、可信 capture、獨立驗證者附掛,以及對應的
durable ``aiml_landing_session_attempt_v1`` attempt row。Wave A 已建 seams/schema/adapter/closure
binding;本模組是把它們接成 orchestrator 的最後一段(source;真正在 trade-core 上跑屬 Wave C)。

**Decision #4(intent-derived authorization,誠實界線)**:授權**由一張已驗證的 typed intent 派生**,
絕非裸的 user-set ``AIML_TARGET_HOST_PROBE=1``。低階 seam 仍以 ``target_host_available()`` 讀該 env(測試
需要),但一張 **closure-ADMISSIBLE** 的 ``target_host_effect_result_v1`` 只能經本模組的 intent-validated
applier 產生:唯有 ``apply_target_host_probe_effect`` 會(a)驗證 typed intent、(b)由 VALIDATED intent
派生探針參數、(c)作為 admitted-intent 執行路徑去 **設定** ``AIML_TARGET_HOST_PROBE=1`` 給它 spawn 的探針
子行程,再(d)把輸出綁成 dedicated result。裸 env + 直呼 ``run_target_host_probe`` 至多得到一個 probe-output
dict / choice receipt,永遠不是一張綁了 intent 的 dedicated effect result。governed ``capture-command`` 持續
env-strip ``AIML_TARGET_HOST_PROBE``,故此旗標不可能被 user 或 capture 走私進來——只由 applier 程式化設定。

**Decision #5(applier != independent verifier)**:applier 不得自驗。applier 自跑的 receipt
``independent_postcheck`` 恆 ``DEFERRED``(binding ``PROVISIONAL_PENDING_LINUX``);唯有 distinct
驗證者經 ``attach_distinct_verifier_postcheck`` 以它**自己**的 on-host residue capture 附掛,才升 PASSED/
BINDING。同節點驗證者(verifier==applier)或裸重用 applier capture digest 一律 fail-closed。

本模組 stdlib-first,唯讀 import Wave A 的探針/選擇/effect 模組;不 register 進中央 validator/registry
(schema/adapter/closure 綁定已於 Wave A 完成),``agent_governance_closure.py`` 核心零改動。
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable

import agent_governance_target_host_probe as th
import agent_governance_target_host_choice as thc
import agent_governance_target_host_effects as tfx
import agent_governance_target_host_child_apply as thchild


TARGET_HOST_ADAPTER_ID = tfx.TARGET_HOST_ADAPTER_ID
INTENT_SCHEMA_VERSION = tfx.INTENT_SCHEMA_VERSION
RESULT_SCHEMA_VERSION = tfx.RESULT_SCHEMA_VERSION
LANDING_SCHEMA_VERSION = "aiml_landing_session_attempt_v1"

# 授權閘 env(由 admitted-intent applier 程式化設定;governed capture-command 會 env-strip 之)。
AIML_TARGET_HOST_PROBE_ENV = "AIML_TARGET_HOST_PROBE"

# effect evidence 的 TTL:completed < evidence_expiry <= completed + 15 分(effect result validator 的上限)。
EVIDENCE_TTL_SECONDS = 600

# intent 依賴 receipt(S1.1/S1.4/S1.5)——build 選擇 receipt 真需要;由呼叫端(真 S1.6B session)供真 digest。
DEPENDENCY_RECEIPT_KEYS = (
    "runtime_candidate_receipt_a_digest",
    "runtime_candidate_receipt_b_digest",
    "runtime_candidate_comparison_digest",
    "effect_seams_ready_receipt_digest",
    "pg_readonly_identity_receipt_digest",
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")

DEFAULT_EFFECT_CLASS = th.PROBE_EFFECT_CLASS  # "TARGET_HOST_DISPOSABLE_RUNTIME_PROBE"
DEFAULT_ROLLBACK_CONTRACT = "atomic_pointer_swap+teardown_reset_failed+rmtree"
DEFAULT_REQUIRED_EFFECT_STATUS = "REQUIRED_PENDING"


class TargetHostApplyError(RuntimeError):
    """Raised when a would-be target-host effect apply cannot be safely produced (fail-closed)."""


# --------------------------------------------------------------------------- #
# time helpers (tz-aware; mirror the Wave A modules)
# --------------------------------------------------------------------------- #
def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def _plus_seconds(iso: str, seconds: int) -> str:
    return (_parse_time(iso) + timedelta(seconds=seconds)).isoformat()


# --------------------------------------------------------------------------- #
# (a) intent validation — authorization derives from THIS validated typed intent
# --------------------------------------------------------------------------- #
def validate_probe_intent(intent: Any, *, now: str) -> list[str]:
    """Return the fail-closed errors for a ``target_host_disposable_runtime_probe_intent_v1``.

    委派中央 validator(schema const/bounds/pattern:non_root_uid/user_scope_only const true、
    ttl<=3600、throwaway_root ``^/run/user/<uid>/.+``、risk∈{high,critical}、applier!=postcheck)並補上
    中央閘不查的 **時間** 不變量:``created_at <= now < expires_at``(intent 未過期),以及 throwaway_root
    不在任何生產前綴下(schema pattern 已保證 /run/user/... 與生產前綴不相交,此為 defense-in-depth)。
    """

    errors: list[str] = []
    if not isinstance(intent, dict):
        return ["target-host probe intent must be an object"]
    if intent.get("schema_version") != INTENT_SCHEMA_VERSION:
        errors.append("target-host probe intent schema_version is invalid")
        return errors
    # 中央 validator(SCHEMA_FILES 委派 + applier!=postcheck 分支)。延遲 import 免硬綁 ml_training 路徑。
    import aiml_gate_receipt_validator as _validator

    errors.extend(
        f"target-host probe intent: {error}"
        for error in _validator.validate_aiml_artifact(intent, now=now)
    )
    # 時間不變量:intent 必須尚未過期(中央閘不查 expiry-not-passed)。
    try:
        created = _parse_time(intent["created_at"])
        expires = _parse_time(intent["expires_at"])
        current = _parse_time(now)
        if not created <= expires:
            errors.append("target-host probe intent created_at must precede expires_at")
        if current >= expires:
            errors.append("target-host probe intent has already expired (expires_at <= now)")
        if current < created:
            errors.append("target-host probe intent is not yet valid (now < created_at)")
    except (KeyError, TypeError, ValueError):
        errors.append("target-host probe intent timestamps are invalid")
    # throwaway_root 不得落在任何生產前綴(schema 已保證 /run/user/<uid>/,此處再防禦一層)。
    throwaway_root = str(intent.get("throwaway_root", ""))
    for prefix in th.PRODUCTION_PATH_PREFIXES:
        if throwaway_root == prefix or throwaway_root.startswith(prefix + os.sep):
            errors.append("target-host probe intent throwaway_root is under a production path prefix")
            break
    return errors


def _require_valid_intent(intent: Any, *, now: str) -> None:
    errors = validate_probe_intent(intent, now=now)
    if errors:
        raise TargetHostApplyError(
            "target-host probe intent is not admissible: " + "; ".join(errors[:4])
        )


# --------------------------------------------------------------------------- #
# (b) probe-parameter derivation FROM the validated intent
# --------------------------------------------------------------------------- #
def _dep(dependency_receipts: Any, key: str) -> str:
    if not isinstance(dependency_receipts, dict):
        raise TargetHostApplyError("dependency_receipts must be a mapping of sha256 dependency digests")
    value = dependency_receipts.get(key)
    if not DIGEST_RE.fullmatch(str(value)):
        raise TargetHostApplyError(f"dependency_receipts.{key} must be a sha256 digest")
    return str(value)


def _derive_probe_params(
    intent: dict[str, Any], *, dependency_receipts: dict[str, Any], capture_digest: str | None
) -> dict[str, Any]:
    """Derive ``run_target_host_probe`` params from the VALIDATED intent (never from raw prompt)."""

    per_seam = intent.get("per_seam_argv") or {}
    return {
        "throwaway_root": intent["throwaway_root"],
        "pg_readonly_identity_receipt_digest": _dep(
            dependency_receipts, "pg_readonly_identity_receipt_digest"
        ),
        # start_stop seam 的 argv 即長駐 launcher;缺則交由 run_target_host_probe 用預設 sleeper。
        "launcher_argv": per_seam.get(th.SEAM_START_STOP),
        "target_host_capture_digest": capture_digest,
    }


# --------------------------------------------------------------------------- #
# (c) authorization is passed to a DEDICATED CHILD PROCESS — never process-global
# --------------------------------------------------------------------------- #
def _run_probe_under_intent_authorization(
    probe_runner: Callable[..., dict[str, Any]],
    params: dict[str, Any],
    *,
    intent: dict[str, Any],
    source_head: str,
    now: str,
    operator_authorization: dict[str, Any] | None,
    operator_signature: bytes | None,
) -> dict[str, Any]:
    """Drive the low-level probe WITHOUT ever opening a process-global authorization gate.

    P1(Codex)修復:舊實作在 **parent** 行程設 ``os.environ["AIML_TARGET_HOST_PROBE"]=1`` 跑 probe,期間
    整個 parent 行程的低階閘都開著——同行程另一 task / direct caller 可在該窗口未經自己的 validated intent
    就跑真基元。改為:

    * **真 runner(預設 ``th.run_target_host_probe``)**:由 VALIDATED intent 派生一張 canonical
      authorization capsule,經一次性 stdin pipe 傳入一個 ``python3 -I`` 子行程;子行程自行重驗 capsule、
      在**自己**的 env 設閘、跑真探針、回傳 JSON。parent 行程從不翻開該閘;子行程退出即失效。
    * **注入的 runner(結構測試)**:不需真閘、也不改任何 env,直接 in-process 呼叫以確定性行使綁定邏輯。

    ``target_host_available()`` 仍讀該 env,但只有子行程於驗過 capsule 後才設定它;governed
    ``capture-command`` 的 env-strip 不受削弱(child 授權來自 capsule 而非 env)。
    """

    if probe_runner is th.run_target_host_probe:
        if not isinstance(operator_authorization, dict) or not isinstance(
            operator_signature, bytes
        ):
            raise TargetHostApplyError(
                "real target-host probe requires an operator-signed exact intent"
            )
        capsule = thchild.build_authorization_capsule(
            intent=intent, source_head=source_head, probe_params=params,
            nonce=uuid.uuid4().hex[:16], now=now,
            operator_authorization=operator_authorization,
        )
        return thchild.run_probe_via_child(
            capsule,
            intent=intent,
            operator_authorization=operator_authorization,
            operator_signature=operator_signature,
        )
    # 注入 runner:確定性 in-process 輸出,無任何 process-global env 變更。
    return probe_runner(**params)


def _build_choice_from_probe_output(
    intent: dict[str, Any],
    probe_output: dict[str, Any],
    *,
    capture_digest: str | None,
    capture_artifact: dict[str, Any] | None,
    now: str,
    dependency_receipts: dict[str, Any],
) -> dict[str, Any]:
    """Turn one run_target_host_probe output + the intent-derived nodes into a choice receipt.

    applier 自跑:``independent_postcheck`` 由探針輸出恆帶 ``DEFERRED``(applier 無法自證獨立性),故此
    receipt 為 ``PROVISIONAL_PENDING_LINUX``,待 distinct 驗證者附掛才升 BINDING。``apply_actor_node`` /
    ``postcheck_verifier_node`` 皆由 VALIDATED intent 派生。
    """

    if not isinstance(probe_output, dict):
        raise TargetHostApplyError("probe output must be an object")
    host_identity = probe_output.get("host_identity")
    if not isinstance(host_identity, dict):
        raise TargetHostApplyError("probe output lacks a host_identity block")
    # host 綁定:探針真觀察的 expected_host 必須等於 admitted intent 的 expected_host(否則冒稱 target host)。
    if host_identity.get("expected_host") != intent["expected_host"]:
        raise TargetHostApplyError(
            "probe host_identity.expected_host does not match the admitted intent expected_host"
        )
    evidence_class = probe_output.get("evidence_class")
    # real primitives invoked / teardown 由 ATTESTED 派生:一份 ATTESTED 探針輸出即代表 run_target_host_probe
    # 真跑完(其 finally 恆 rmtree + reset-failed 完成 applier 自身 teardown)。非 ATTESTED → 誠實 status=FAIL。
    real_invoked = evidence_class == th.EVIDENCE_ATTESTED
    return thc.build_target_host_choice_receipt(
        caller=f"{th.HARNESS_ID}:intent-applier:{intent['intent_id']}",
        platform=th.detect_platform(),
        target_class=th.TARGET_CLASS,
        host_identity=host_identity,
        apply_actor_node=intent["applier_node_id"],
        postcheck_verifier_node=intent["postcheck_node_id"],
        fixed_path_seams=probe_output["fixed_path_seams"],
        pg_identity_mode=probe_output["pg_identity_mode"],
        evidence_class=evidence_class,
        real_target_host_primitives_invoked=real_invoked,
        complete_teardown_verified=real_invoked,
        runtime_candidate_receipt_a_digest=_dep(dependency_receipts, "runtime_candidate_receipt_a_digest"),
        runtime_candidate_receipt_b_digest=_dep(dependency_receipts, "runtime_candidate_receipt_b_digest"),
        runtime_candidate_comparison_digest=_dep(dependency_receipts, "runtime_candidate_comparison_digest"),
        effect_seams_ready_receipt_digest=_dep(dependency_receipts, "effect_seams_ready_receipt_digest"),
        pg_readonly_identity_receipt_digest=_dep(dependency_receipts, "pg_readonly_identity_receipt_digest"),
        observation_time=now,
        ttl_seconds=intent["ttl_seconds"],
        target_host_capture_digest=capture_digest,
        target_host_capture_artifact=capture_artifact,
    )


def apply_target_host_probe_effect(
    intent: Any,
    *,
    source_head: str,
    approved_by: str,
    approved_at: str,
    capture_digest: str | None,
    capture_artifact: dict[str, Any] | None,
    verifier_node_id: str,
    now: str,
    dependency_receipts: dict[str, Any],
    probe_runner: Callable[..., dict[str, Any]] = th.run_target_host_probe,
    operator_authorization: dict[str, Any] | None = None,
    operator_signature: bytes | None = None,
) -> dict[str, Any]:
    """Admitted-intent applier: derive → run → embed into a dedicated ``target_host_effect_result_v1``.

    Fail-closed by construction: 只回傳一份通過 ``require_success``+``require_target_host_attested`` 嚴格
    驗的 effect result。``independent_postcheck`` 於 applier 自跑必為 DEFERRED(binding PROVISIONAL);
    distinct 驗證者以 ``attach_distinct_verifier_postcheck`` 升 BINDING。

    ``dependency_receipts`` / ``probe_runner`` 為 core 之外的加簽關鍵字參數:前者是 build 選擇 receipt 真需要
    的 S1.1/S1.4/S1.5 依賴 digest(由真 session 供),後者預設 ``run_target_host_probe``(Mac 上 SKIP,結構
    測試以注入的 runner 餵入「as-if trade-core」probe 輸出以確定性地行使 orchestration/綁定邏輯)。
    """

    _require_valid_intent(intent, now=now)
    if not HEAD_RE.fullmatch(str(source_head)):
        raise TargetHostApplyError("source_head must be a 40-hex commit id")
    if not (isinstance(approved_by, str) and approved_by):
        raise TargetHostApplyError("approved_by is required")
    # decision #5:宣告的 verifier 必為 intent.postcheck_node_id,且 != applier(applier 不得自驗)。
    if verifier_node_id != intent["postcheck_node_id"]:
        raise TargetHostApplyError("verifier_node_id must equal the admitted intent postcheck_node_id")
    if verifier_node_id == intent["applier_node_id"]:
        raise TargetHostApplyError("applier_node_id must differ from the independent postcheck verifier")

    params = _derive_probe_params(
        intent, dependency_receipts=dependency_receipts, capture_digest=capture_digest
    )
    probe_output = _run_probe_under_intent_authorization(
        probe_runner,
        params,
        intent=intent,
        source_head=source_head,
        now=now,
        operator_authorization=operator_authorization,
        operator_signature=operator_signature,
    )
    choice = _build_choice_from_probe_output(
        intent, probe_output, capture_digest=capture_digest,
        capture_artifact=capture_artifact, now=now, dependency_receipts=dependency_receipts,
    )
    result = tfx.build_target_host_effect_result(
        choice_receipt=choice,
        intent_id=intent["intent_id"],
        intent_digest=intent["self_digest"],
        source_head=source_head,
        approved_by=approved_by,
        approved_at=approved_at,
        started_at=now,
        completed_at=now,
        intent_expires_at=intent["expires_at"],
        evidence_expires_at=_plus_seconds(now, EVIDENCE_TTL_SECONDS),
    )
    # fail-closed:applier 只回傳過得了嚴格 attestation lane 的 effect result(§13 C4 的真實執法)。
    errors = tfx.validate_target_host_effect_result(
        result, now=now, expected_source_head=source_head, require_success=True
    )
    if errors:
        raise TargetHostApplyError(
            "applier produced a non-admissible effect result: " + "; ".join(errors[:3])
        )
    return result


# --------------------------------------------------------------------------- #
# (3) independent verifier (distinct role + process + capture) — no self-verify
# --------------------------------------------------------------------------- #
def _embed_verifier_capture_binding(
    upgraded_choice: dict[str, Any], verifier_capture_digest: str
) -> None:
    """Durably record the distinct verifier capture digest into the upgraded choice receipt.

    B1 P2(E2):``attach_distinct_verifier_postcheck`` 過去只比對 verifier capture != applier capture
    後即丟棄。這裡把 verifier 的 capture digest 綁進升級後 receipt 的 ``independent_postcheck`` seam
    note(schema 合法的自由文字欄位),使「相異 capture」主張被持久記錄(而非僅一次性比對),再重簽
    ``self_digest`` 讓該綁定 tamper-evident。就地修改 ``upgraded_choice``。
    """

    probes = upgraded_choice.get("candidate_probes")
    fixed = next(
        (b for b in probes if isinstance(b, dict) and b.get("candidate_id") == th.CANDIDATE_FIXED_PATH),
        None,
    ) if isinstance(probes, list) else None
    seams = fixed.get("seams") if isinstance(fixed, dict) else None
    seam = next(
        (s for s in seams if isinstance(s, dict) and s.get("seam_id") == th.SEAM_INDEPENDENT_POSTCHECK),
        None,
    ) if isinstance(seams, list) else None
    if seam is None:
        raise TargetHostApplyError("upgraded choice receipt has no independent_postcheck seam to bind the verifier capture to")
    seam["note"] = f"{seam['note']} | distinct verifier capture digest: {verifier_capture_digest}"
    upgraded_choice.pop("self_digest", None)
    upgraded_choice["self_digest"] = th.receipt_digest(upgraded_choice)


def attach_distinct_verifier_postcheck(
    effect_result: Any,
    *,
    verifier_node_id: str,
    verifier_capture_digest: str,
    residue_observation: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    """Distinct OPS verifier attaches ITS OWN residue capture, upgrading the effect result to BINDING.

    decision #5/#7:verifier 必須(1)非 applier 節點、(2)是 effect result 宣告的 postcheck 節點、
    (3)帶一份與 applier capture **相異** 的 governed capture digest(role+process+CAPTURE 皆異)。residue
    觀察經 ``attach_independent_postcheck`` 升 ``independent_postcheck``→PASSED(同節點附掛或殘留未清即
    raise),再以升級後 choice 重建 effect result(re-derive choice_receipt_digest/receipt_digest)。
    B1 P2:verifier 的相異 capture digest 會被 **持久綁進** 升級後 receipt(independent_postcheck seam),
    使「相異 capture」主張被記錄而非比對後即丟棄。
    """

    if not isinstance(effect_result, dict):
        raise TargetHostApplyError("effect_result must be an object")
    applier_node = effect_result.get("applier_node_id")
    declared_verifier = effect_result.get("postcheck_verifier_node_id")
    choice = effect_result.get("choice_receipt")
    if not isinstance(choice, dict):
        raise TargetHostApplyError("effect_result lacks an embedded choice receipt to attach a postcheck to")
    if not (isinstance(verifier_node_id, str) and verifier_node_id):
        raise TargetHostApplyError("verifier_node_id is required")
    if verifier_node_id == applier_node:
        raise TargetHostApplyError("distinct verifier must differ from the applier node (no self-verify)")
    if verifier_node_id != declared_verifier:
        raise TargetHostApplyError("distinct verifier must be the effect result's declared postcheck node")
    applier_capture = choice.get("target_host_capture_digest")
    if not DIGEST_RE.fullmatch(str(verifier_capture_digest)):
        raise TargetHostApplyError("verifier_capture_digest must be a sha256 digest")
    if str(verifier_capture_digest) == str(applier_capture):
        raise TargetHostApplyError(
            "verifier capture must differ from the applier capture (distinct process + capture)"
        )
    # thread 驗證者自己的 on-host residue 觀察;attach_independent_postcheck 自行 fail-closed
    # (verifier==apply_actor 或 residue 未全清即 raise)。
    upgraded = thc.attach_independent_postcheck(
        choice, verifier_node=verifier_node_id, residue_observation=residue_observation, now=now
    )
    # B1 P2:把 verifier 的相異 capture digest 持久綁進升級後 receipt(而非比對後丟棄),再重簽。
    _embed_verifier_capture_binding(upgraded, str(verifier_capture_digest))
    # P1(Codex):同一 digest 亦以結構化 ``verifier_capture_digest`` 欄位帶進 effect result,供 closure
    # 對「effect receipt / ops_postcheck / verifier capture」三者交叉綁定(不只是 seam note 文字)。
    return tfx.build_target_host_effect_result(
        choice_receipt=upgraded,
        intent_id=effect_result["intent_id"],
        intent_digest=effect_result["intent_digest"],
        source_head=effect_result["source_head"],
        approved_by=effect_result["approved_by"],
        approved_at=effect_result["approved_at"],
        started_at=effect_result["started_at"],
        completed_at=effect_result["completed_at"],
        intent_expires_at=effect_result["intent_expires_at"],
        evidence_expires_at=effect_result["evidence_expires_at"],
        verifier_capture_digest=str(verifier_capture_digest),
    )


# --------------------------------------------------------------------------- #
# (4) emit the durable aiml_landing_session_attempt_v1 for this effect
# --------------------------------------------------------------------------- #
def build_target_host_landing_attempt(
    *,
    effect_result: dict[str, Any],
    session_id: str,
    cohort_epoch: str,
    owner: str,
    source: dict[str, Any],
    lease: dict[str, Any],
    landing_scope_id: str,
    work_package_id: str,
    direct_interfaces: list[str],
    owned_paths: list[str],
    dependency_generations: list[dict[str, Any]],
    bootstrap: dict[str, Any],
    ci_classifier_digest: str,
    effect_classification_digest: str,
    closure_packet_digest: str,
    created_at: str,
    attempt: int = 1,
    status: str = "IN_PROGRESS",
    semantic_rechecks: tuple[str, ...] = ("path_ownership",),
    selected_workflows: tuple[str, ...] = ("structure",),
    node_id: str = "implementation",
    role: str | None = None,
    native_agent: str | None = None,
    permission: str = "source_writer",
    effect_class: str = DEFAULT_EFFECT_CLASS,
    rollback_contract: str = DEFAULT_ROLLBACK_CONTRACT,
    required_effect_status: str = DEFAULT_REQUIRED_EFFECT_STATUS,
) -> dict[str, Any]:
    """Assemble the durable S1 landing attempt row bound to one produced target-host effect result.

    綁定:DAG 節點 + owned 路徑 + source head(= effect result ``source_head``)、author-declared
    ``required_effects``(``adapter_id`` == route-node adapter == effect result ``adapter_id``)、以及
    ``closure_binding``(綁 produced effect result 的 ``receipt_digest`` 與 closure packet)。``actor_node`` /
    ``independent_postcheck_node`` 由 effect result 派生(故天然 applier != verifier)。attempt_id/self_digest
    以中央 validator 的既有 helper 重算。回傳的 row 走中央 validator 的 landing-attempt 分支(非 S0.3 硬編路徑)。
    """

    if not isinstance(effect_result, dict):
        raise TargetHostApplyError("effect_result must be an object")
    adapter_id = effect_result.get("adapter_id")
    if adapter_id != TARGET_HOST_ADAPTER_ID:
        raise TargetHostApplyError("effect_result adapter_id is not the target-host route-node adapter")
    actor_node = effect_result.get("applier_node_id")
    independent_postcheck_node = effect_result.get("postcheck_verifier_node_id")
    effect_receipt_digest = effect_result.get("receipt_digest")
    baseline_head = effect_result.get("source_head")
    for field, value in (
        ("applier_node_id", actor_node),
        ("postcheck_verifier_node_id", independent_postcheck_node),
        ("source_head", baseline_head),
    ):
        if not (isinstance(value, str) and value):
            raise TargetHostApplyError(f"effect_result.{field} is required to bind a landing attempt")
    if not DIGEST_RE.fullmatch(str(effect_receipt_digest)):
        raise TargetHostApplyError("effect_result.receipt_digest must be a sha256 digest")
    if not DIGEST_RE.fullmatch(str(closure_packet_digest)):
        raise TargetHostApplyError("closure_packet_digest must be a sha256 digest")

    path_manifest = sorted(set(owned_paths))
    if not path_manifest:
        raise TargetHostApplyError("owned_paths must be a non-empty source manifest")
    scope_ref = {"kind": "LANDING_SCOPE", "landing_scope_id": landing_scope_id}
    attempt_key = {
        "session_id": session_id,
        "scope_ref": scope_ref,
        "cohort_epoch": cohort_epoch,
        "attempt": attempt,
    }
    resolved_source = {
        "branch": source["branch"],
        "worktree": source["worktree"],
        "baseline_head": baseline_head,
        "checkpoint_head": source["checkpoint_head"],
    }
    bootstrap_admission = {
        "task_id": bootstrap["task_id"],
        "task_contract_digest": bootstrap["task_contract_digest"],
        "dag_digest": bootstrap["dag_digest"],
        "context_artifact_digest": bootstrap["context_artifact_digest"],
        "baseline_head": baseline_head,
        "writer_lease_id": lease["lease_id"],
    }
    native_admission = {
        "node_id": node_id,
        "role": role or owner,
        "native_agent": native_agent or owner.lower(),
        "node_class": "work",
        "permission": permission,
    }
    dag_nodes = [{
        "node_id": node_id,
        "node_class": "work",
        "permission": permission,
        "requires": [],
        "writer_paths": path_manifest,
    }]
    required_effects = [{
        "effect_class": effect_class,
        "adapter_id": adapter_id,
        "actor_node_id": actor_node,
        "rollback_contract": rollback_contract,
        "independent_postcheck_node_id": independent_postcheck_node,
        "status": required_effect_status,
    }]
    artifact: dict[str, Any] = {
        "schema_version": LANDING_SCHEMA_VERSION,
        "attempt_id": "PLACEHOLDER",
        "session_id": session_id,
        "scope_ref": scope_ref,
        "cohort_epoch": cohort_epoch,
        "attempt": attempt,
        "attempt_key": attempt_key,
        "attempt_phase": "SOURCE_BUILD",
        "status": status,
        "owner": owner,
        "lease": dict(lease),
        "source": resolved_source,
        "path_manifest": path_manifest,
        "work_package": {
            "work_package_id": work_package_id,
            "phase": "SOURCE_BUILD",
            "side_effect_class": "target_host_probe",
            "runtime_claim": True,
            "owned_path_manifest": path_manifest,
            "direct_interfaces": list(direct_interfaces),
        },
        "dependency_generations": [dict(gen) for gen in dependency_generations],
        "bootstrap_admission": bootstrap_admission,
        "native_admission": native_admission,
        "dag_nodes": dag_nodes,
        "semantic_rechecks": list(semantic_rechecks),
        "ci_classifier": {
            "classifier_digest": ci_classifier_digest,
            "selected_workflows": list(selected_workflows),
            "invocation_history": [],
            "failure_fingerprints": [],
        },
        "effect_classification_digest": effect_classification_digest,
        "required_effects": required_effects,
        "adapter_id": adapter_id,
        "actor_node": actor_node,
        "rollback": rollback_contract,
        "independent_postcheck_node": independent_postcheck_node,
        "closure_binding": {
            "closure_packet_digest": closure_packet_digest,
            "effect_receipt_digest": effect_receipt_digest,
            "effect_adapter_id": adapter_id,
        },
        "created_at": created_at,
        "self_digest": "PLACEHOLDER",
    }
    import aiml_gate_receipt_validator as _validator

    artifact["attempt_id"] = _validator.session_attempt_identity_digest(artifact)
    artifact["self_digest"] = _validator.artifact_self_digest(artifact)
    return artifact

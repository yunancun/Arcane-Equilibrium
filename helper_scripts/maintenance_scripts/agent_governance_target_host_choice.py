"""Target-host choice-receipt builder + validators for AIML LR0C (S1.6B).

Split out of ``agent_governance_target_host_probe`` (which stayed under the
2000-line governance-interface cap): the probe module runs the real on-host
seams + driver; this module turns the per-seam verdicts into the canonical
self-hashed ``learning_runtime_choice_receipt_target_host_v1``, attaches the
distinct-verifier ``independent_postcheck``, validates the receipt, and holds the
fail-closed bypass-negative cases.  It imports the shared constants/errors/
helpers from the probe module (one-way; the probe module re-exports this
module's public builders/validators so ``th.build_target_host_choice_receipt`` etc.
keep working for callers importing the probe module).  Mac-testable pure logic —
no on-host effect here.

AIML S1 formal-closure Wave A: this module is now an ``implementation_path`` of the
registered ``target_host_disposable_runtime_probe_adapter_v1``, and its
``validate_target_host_choice_receipt`` is delegated from the central AIML closure-
validator for the registered ``learning_runtime_choice_receipt_target_host_v1`` schema
(structure-only, ``require_target_host_attested=False``, at the offline gate).  The
strict attested gate (``require_target_host_attested=True``) is invoked by the effect
lane in ``agent_governance_target_host_effects``.
"""

from __future__ import annotations

import copy
from datetime import datetime, timedelta
from typing import Any, Callable

import agent_governance_component_effects as ce
import agent_governance_command_capture_v2 as governed_capture
from agent_governance_schema import schema_subset_errors
from agent_governance_target_host_probe import (
    BINDING_BINDING,
    BINDING_PROVISIONAL,
    BYPASS_KINDS,
    BindingRuleError,
    CANDIDATE_FIXED_PATH,
    CANDIDATE_IDS,
    CANDIDATE_OCI,
    DEFERRED_ROOT_ONLY_CONTROLLERS,
    DIGEST_RE,
    EVIDENCE_ATTESTED,
    EVIDENCE_CLASSES,
    EVIDENCE_STRUCTURAL,
    EXPECTED_TARGET_HOST_DEFAULT,
    FINAL_CHOICE_FIXED_PATH,
    FINAL_CHOICE_OCI,
    FIXED_PATH_CAVEATS,
    FIXED_PATH_SEAM_VERDICTS,
    FailClosedStop,
    HARNESS_ID,
    NATIVE_FULL_CLOSURE,
    NATIVE_REPRESENTATIVE,
    OCI_CAVEATS,
    PG_MODES,
    PG_MODE_DEFERRED,
    PG_MODE_REAL,
    PLATFORM_OS,
    PROBE_ADAPTER_ID,
    PROBE_EFFECT_CLASS,
    RECEIPT_FIELDS,
    RECEIPT_SCHEMA_VERSION,
    REJECTED_TARGET_CLASSES,
    REQUIRED_DELEGATED_CONTROLLERS,
    SEAM_INDEPENDENT_POSTCHECK,
    SEAM_NATIVE_LIB,
    SEAM_PG_IDENTITY,
    SEAM_START_STOP,
    SEAM_VERDICT_DEFERRED,
    SEAM_VERDICT_NON_SATISFIABLE,
    SEAM_VERDICT_PASSED,
    SECRET_PATTERNS_CHECKED,
    SELECTION_RULE,
    TARGET_CLASS,
    TARGET_HOST_SEAMS,
    TARGET_HOST_SEAM_SET,
    TTL_CEILING_SECONDS,
    TargetClassRejectedError,
    TargetHostProbeError,
    _SEAM_NOTES,
    _canonical_digest,
    _contains_secret_like,
    _guard_no_secret,
    _parse_time,
    _receipt_schema,
    detect_platform,
    oci_non_satisfiable_seams,
    receipt_digest,
    receipt_schema_sha256,
    source_sha256,
    synthesize_fixed_path_seams,
)


# --------------------------------------------------------------------------- #
# governed on-host capture artifact (embedded command_capture_v2; verifier-bound)
# --------------------------------------------------------------------------- #
def _validate_capture_artifact(artifact: Any) -> dict[str, Any] | None:
    """Structurally validate an embedded governed ``command_capture_v2`` capture artifact (or None).

    要求:dict、``schema_version=="command_capture_v2"``、``record_digest`` 為 sha256、且帶非空 capturer
    身分(``node_id`` 且 ``native_agent``/``role_id`` 至少一)。這是把「target-host 真出口」的門檻由「任意
    64-hex 字串」抬到「一個可重放、綁到 capturer 身分的 capture 記錄」。離線僅做結構驗證(**非認證**,
    CLAUDE.md):真確性由受信主機重放此 artifact 確立;此處只確保 digest 與 artifact 不可解耦。掃過機密後
    回傳深拷貝以內嵌。``None`` → 回 ``None``(呼叫端可仍內嵌裸 digest,但過不了 require_target_host_attested)。
    """

    if artifact is None:
        return None
    if not isinstance(artifact, dict):
        raise TargetHostProbeError("target_host_capture_artifact must be a command_capture_v2 record dict or None")
    if artifact.get("schema_version") != "command_capture_v2":
        raise TargetHostProbeError("target_host_capture_artifact.schema_version must be command_capture_v2")
    if not DIGEST_RE.fullmatch(str(artifact.get("record_digest"))):
        raise TargetHostProbeError("target_host_capture_artifact.record_digest must be a sha256 digest")
    node_id = artifact.get("node_id")
    if not isinstance(node_id, str) or not node_id:
        raise TargetHostProbeError("target_host_capture_artifact must carry a non-empty capturer node_id")
    native_agent = artifact.get("native_agent")
    role_id = artifact.get("role_id")
    if not ((isinstance(native_agent, str) and native_agent) or (isinstance(role_id, str) and role_id)):
        raise TargetHostProbeError("target_host_capture_artifact must carry a non-empty native_agent/role_id capturer identity")
    _guard_no_secret(artifact)
    return copy.deepcopy(artifact)


# --------------------------------------------------------------------------- #
# choice receipt builder (honest-by-construction; unsafe states raise)
# --------------------------------------------------------------------------- #
def build_target_host_choice_receipt(
    *,
    caller: str,
    platform: dict[str, Any],
    target_class: str,
    host_identity: dict[str, Any],
    apply_actor_node: str,
    postcheck_verifier_node: str,
    fixed_path_seams: list[dict[str, Any]],
    pg_identity_mode: str,
    evidence_class: str,
    real_target_host_primitives_invoked: bool,
    complete_teardown_verified: bool,
    runtime_candidate_receipt_a_digest: str,
    runtime_candidate_receipt_b_digest: str,
    runtime_candidate_comparison_digest: str,
    effect_seams_ready_receipt_digest: str,
    pg_readonly_identity_receipt_digest: str,
    observation_time: str,
    ttl_seconds: int,
    target_host_capture_digest: str | None = None,
    target_host_capture_artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``learning_runtime_choice_receipt_target_host_v1``.

    Honest-by-construction: ``final_choice`` / ``oci_selectable`` / ``binding`` /
    ``pending_seams`` / ``status`` are all DERIVED, never free parameters.  Unsafe
    states RAISE (never emit): a non-``target_host`` class; passwordless sudo /
    missing delegated controllers in ``host_identity``; applier==verifier; a fixed-
    path seam set that is not exactly the 8 seams; a ``pg_identity_mode`` inconsistent
    with the PG seam verdict; or a secret in any serialized field.  ``status="PASS"``
    iff ``evidence_class==PLATFORM_OR_EXTERNAL_ATTESTED`` and the real primitives were
    invoked and teardown was verified (the target-host honesty gate); a Mac
    ``STRUCTURAL_ONLY`` synthesis is ``status="FAIL"``.  ``binding="BINDING"`` iff
    EVERY fixed-path seam is ``PASSED_TARGET_HOST``, else
    ``PROVISIONAL_PENDING_LINUX`` naming the unmet seams.
    """

    if not isinstance(caller, str) or not caller:
        raise TargetHostProbeError("caller is required")
    if target_class in REJECTED_TARGET_CLASSES:
        raise TargetClassRejectedError(
            "S1.6B is target_host only; production/disposable targets are rejected fail-closed"
        )
    if target_class != TARGET_CLASS:
        raise TargetHostProbeError(f"unrecognized target_class: {target_class!r}")
    if evidence_class not in EVIDENCE_CLASSES:
        raise TargetHostProbeError(f"unrecognized evidence_class: {evidence_class!r}")
    if pg_identity_mode not in PG_MODES:
        raise TargetHostProbeError(f"unrecognized pg_identity_mode: {pg_identity_mode!r}")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise TargetHostProbeError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise TargetHostProbeError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    # target_host_capture_digest 為 governed on-host capture(command_capture_v2)參照:None(未綁)或 sha256。
    if target_host_capture_digest is not None and not DIGEST_RE.fullmatch(str(target_host_capture_digest)):
        raise TargetHostProbeError("target_host_capture_digest must be a sha256 digest or None")
    # #T1:若提供 governed on-host capture ARTIFACT,驗其結構並「派生」digest = artifact.record_digest
    # (digest 與 artifact 不可解耦),再內嵌 receipt。裸 digest(無 artifact)仍內嵌但過不了 require_target_host_attested。
    capture_artifact = _validate_capture_artifact(target_host_capture_artifact)
    if capture_artifact is not None:
        derived = capture_artifact["record_digest"]
        if target_host_capture_digest is not None and str(target_host_capture_digest) != str(derived):
            raise TargetHostProbeError(
                "target_host_capture_digest must match the embedded command_capture_v2 record_digest "
                "(digest and artifact cannot be decoupled)"
            )
        target_host_capture_digest = derived
    if apply_actor_node == postcheck_verifier_node:
        raise ce.ApplierIsSoleVerifierError("target-host probe applier equals its verifier")

    host_block = _validate_host_identity(host_identity)
    platform_block = _validate_platform(platform)
    normalized_fixed = _normalize_fixed_path_seams(fixed_path_seams, pg_identity_mode)
    oci_seams = oci_non_satisfiable_seams()

    real_invoked = bool(real_target_host_primitives_invoked)
    teardown_ok = bool(complete_teardown_verified)
    target_host_probe_performed = real_invoked

    # --- machine-encoded 規則(真證據)---
    oci_all_passed = all(seam["verdict"] == SEAM_VERDICT_PASSED for seam in oci_seams)  # 恆 False
    oci_selectable = target_host_probe_performed and oci_all_passed
    final_choice = FINAL_CHOICE_OCI if oci_selectable else FINAL_CHOICE_FIXED_PATH
    if final_choice != FINAL_CHOICE_FIXED_PATH:
        raise BindingRuleError("OCI is NON_SATISFIABLE_NON_ROOT on target; final_choice must be content_addressed_fixed_path")

    verdict_by_id = {seam["seam_id"]: seam["verdict"] for seam in normalized_fixed}
    unmet = [seam_id for seam_id in TARGET_HOST_SEAMS if verdict_by_id.get(seam_id) != SEAM_VERDICT_PASSED]
    binding = BINDING_BINDING if not unmet else BINDING_PROVISIONAL
    pending_seams = list(unmet)

    reasons: list[str] = []
    if evidence_class != EVIDENCE_ATTESTED:
        reasons.append("structural-only synthesis: real target-host primitives were not invoked on this node")
    if not real_invoked:
        reasons.append("real target-host primitives were not invoked")
    if not teardown_ok:
        reasons.append("complete teardown was not independently verified")
    status = "PASS" if not reasons else "FAIL"
    failure_reason = None if status == "PASS" else "; ".join(reasons)

    for digest in (
        runtime_candidate_receipt_a_digest, runtime_candidate_receipt_b_digest,
        runtime_candidate_comparison_digest, effect_seams_ready_receipt_digest,
        pg_readonly_identity_receipt_digest,
    ):
        if not DIGEST_RE.fullmatch(str(digest)):
            raise TargetHostProbeError("dependency receipt digests must be sha256 digests")

    observed = _parse_time(observation_time)
    expires = observed + timedelta(seconds=ttl_seconds)

    if binding == BINDING_BINDING:
        reason = (
            "OCI is NON_SATISFIABLE_NON_ROOT on trade-core (rootful docker only; LR2 forbids the OCI socket "
            "surface); every fixed-path seam PASSED_TARGET_HOST, so content_addressed_fixed_path is BINDING on "
            "real target-host evidence."
        )
    else:
        reason = (
            "OCI is NON_SATISFIABLE_NON_ROOT on trade-core; fixed-path is the choice but PROVISIONAL_PENDING_LINUX "
            f"because these fixed-path seams are not PASSED_TARGET_HOST: {pending_seams}."
        )

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "harness_id": HARNESS_ID,
        "status": status,
        "caller": caller,
        "target_class": TARGET_CLASS,
        "evidence_class": evidence_class,
        "host_identity": host_block,
        "platform": platform_block,
        "probe_scope": {
            "effect_class": PROBE_EFFECT_CLASS,
            "target_host_probe_performed": target_host_probe_performed,
            "adapter_id": PROBE_ADAPTER_ID,
            "pg_identity_mode": pg_identity_mode,
        },
        "candidate_probes": [
            {
                "candidate_id": CANDIDATE_FIXED_PATH,
                "runtime_identity_kind": "content_addressed_path",
                "apply_actor_node": apply_actor_node,
                "postcheck_verifier_node": postcheck_verifier_node,
                "seams": normalized_fixed,
                "caveats": list(FIXED_PATH_CAVEATS),
            },
            {
                "candidate_id": CANDIDATE_OCI,
                "runtime_identity_kind": "exact_image_id",
                "apply_actor_node": apply_actor_node,
                "postcheck_verifier_node": postcheck_verifier_node,
                "seams": oci_seams,
                "caveats": list(OCI_CAVEATS),
            },
        ],
        "selection": {
            "final_choice": final_choice,
            "selection_rule": SELECTION_RULE,
            "oci_selectable": oci_selectable,
            "binding": binding,
            "pending_seams": pending_seams,
            "reason": reason,
        },
        "unselected_path_removal": {
            "unselected_candidate": FINAL_CHOICE_OCI,
            "unselected_production_artifact_present": False,
            "production_path_removed": True,
            "forecloses_downstream": True,
            "note": (
                "no non-root OCI runtime exists on trade-core to build/install; LR2/S2.3 seals ONLY the "
                "fixed-path runtime, so no downstream session may create an OCI build/install/socket path."
            ),
        },
        "production_running_attested": False,
        "target_host_capture_digest": target_host_capture_digest,
        "target_host_capture": capture_artifact,
        "dependency_receipts": {
            "runtime_candidate_receipt_a_digest": runtime_candidate_receipt_a_digest,
            "runtime_candidate_receipt_b_digest": runtime_candidate_receipt_b_digest,
            "runtime_candidate_comparison_digest": runtime_candidate_comparison_digest,
            "effect_seams_ready_receipt_digest": effect_seams_ready_receipt_digest,
            "component_effect_matrix_digest": ce.component_effect_matrix_digest(),
            "pg_readonly_identity_receipt_digest": pg_readonly_identity_receipt_digest,
        },
        "boundary": {
            "non_root": True,
            "user_scope_only": True,
            "no_docker_invoked": True,
            "no_system_scope": True,
            "no_production_path": True,
            "prod_pg_untouched": True,
            "applier_ne_verifier": True,
            "production_running_attested": False,
            "real_target_host_primitives_invoked": real_invoked,
            "complete_teardown_verified": teardown_ok,
        },
        "source_sha256": source_sha256(),
        "schema_sha256": receipt_schema_sha256(),
        "secret_scan": {
            "patterns_checked": list(SECRET_PATTERNS_CHECKED),
            "leaked": False,
        },
        "observation_time": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "ttl_seconds": ttl_seconds,
        "failure_reason": failure_reason,
    }
    # 計算 self_digest 前掃描整份 receipt(排除 secret_scan 自身)。
    _guard_no_secret({k: v for k, v in receipt.items() if k != "secret_scan"})
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


# distinct 驗證者附掛時要求的殘留觀察鍵:units/cgroup/netns/temp 皆已清(全 True 才可升 PASS)。
RESIDUE_OBSERVATION_KEYS = ("units_gone", "cgroup_gone", "netns_gone", "temp_gone")


def _require_clean_residue_observation(observation: Any) -> dict[str, bool]:
    # 驗證 distinct 驗證者交來的 on-host 掃描結果:四鍵皆 True(真的無殘留)才允許附掛 PASS,否則 raise。
    if not isinstance(observation, dict):
        raise TargetHostProbeError("independent_postcheck residue_observation must be an object")
    not_clean = [key for key in RESIDUE_OBSERVATION_KEYS if observation.get(key) is not True]
    if not_clean:
        raise TargetHostProbeError(
            f"independent_postcheck residue_observation must report all clean; not clean: {not_clean}"
        )
    return {key: True for key in RESIDUE_OBSERVATION_KEYS}


def attach_independent_postcheck(
    receipt: dict[str, Any],
    *,
    verifier_node: str,
    residue_observation: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    """DISTINCT OPS verifier attaches the real on-host residue observation, upgrading the choice.

    由與 applier 相異的 OPS 驗證者呼叫:斷言 ``verifier_node != apply_actor_node``、驗證真殘留觀察
    (units/cgroup/netns/temp 皆已清),才把 ``independent_postcheck`` seam 由 ``DEFERRED`` 升為
    ``PASSED``,並重新導出選擇(若所有 fixed-path seam 皆 PASSED → ``BINDING``,否則仍 ``PROVISIONAL``
    指名未達 seam),再重簽 ``self_digest``。applier 自跑(independent_postcheck 仍 DEFERRED)的 receipt
    永遠不會是 BINDING——真獨立確認是 BINDING 的必要條件。同一 actor 附掛(verifier==applier)一律拒。
    """

    if not isinstance(receipt, dict):
        raise TargetHostProbeError("receipt must be an object")
    if not isinstance(verifier_node, str) or not verifier_node:
        raise TargetHostProbeError("verifier_node is required")
    updated = copy.deepcopy(receipt)
    probes = updated.get("candidate_probes")
    fixed_block = None
    if isinstance(probes, list):
        fixed_block = next(
            (b for b in probes if isinstance(b, dict) and b.get("candidate_id") == CANDIDATE_FIXED_PATH), None
        )
    if fixed_block is None:
        raise TargetHostProbeError("receipt has no fixed-path candidate to attach an independent postcheck to")
    apply_actor = fixed_block.get("apply_actor_node")
    if verifier_node == apply_actor:
        raise ce.ApplierIsSoleVerifierError(
            "independent_postcheck verifier_node must differ from the apply_actor_node (applier != verifier)"
        )
    seams = fixed_block.get("seams")
    ip_seam = None
    if isinstance(seams, list):
        ip_seam = next(
            (s for s in seams if isinstance(s, dict) and s.get("seam_id") == SEAM_INDEPENDENT_POSTCHECK), None
        )
    if ip_seam is None:
        raise TargetHostProbeError("receipt has no independent_postcheck seam")
    if ip_seam.get("verdict") != SEAM_VERDICT_DEFERRED:
        raise TargetHostProbeError(
            "independent_postcheck seam is not DEFERRED (nothing to attach, or it was already attached)"
        )
    clean = _require_clean_residue_observation(residue_observation)
    # 升 PASSED,evidence_digest 綁真觀察 + 驗證者身分 + 附掛時間,note 換成「已附掛」誠實敘述。
    evidence = {
        "verifier_node": verifier_node,
        "apply_actor_node": apply_actor,
        "residue_observation": clean,
        "attested_at": now,
    }
    ip_seam["verdict"] = SEAM_VERDICT_PASSED
    ip_seam["evidence_digest"] = _canonical_digest(
        {"seam_id": SEAM_INDEPENDENT_POSTCHECK, "verdict": SEAM_VERDICT_PASSED, "evidence": evidence}
    )
    ip_seam["note"] = _SEAM_NOTES[SEAM_INDEPENDENT_POSTCHECK]
    # 重新導出 binding/pending_seams(其餘 seam 不動;pg 仍 DEFERRED 則續 PROVISIONAL 指名 pg)。
    verdict_by_id = {s.get("seam_id"): s.get("verdict") for s in seams if isinstance(s, dict)}
    unmet = [seam_id for seam_id in TARGET_HOST_SEAMS if verdict_by_id.get(seam_id) != SEAM_VERDICT_PASSED]
    selection = updated.get("selection")
    if not isinstance(selection, dict):
        raise TargetHostProbeError("receipt has no selection block to re-derive")
    selection["binding"] = BINDING_BINDING if not unmet else BINDING_PROVISIONAL
    selection["pending_seams"] = list(unmet)
    if not unmet:
        selection["reason"] = (
            "OCI is NON_SATISFIABLE_NON_ROOT on trade-core; a distinct OPS verifier attached a clean on-host "
            "residue sweep, so every fixed-path seam is PASSED_TARGET_HOST and content_addressed_fixed_path is BINDING."
        )
    else:
        selection["reason"] = (
            "OCI is NON_SATISFIABLE_NON_ROOT on trade-core; independent_postcheck attached but PROVISIONAL_PENDING_LINUX "
            f"because these fixed-path seams are not PASSED_TARGET_HOST: {unmet}."
        )
    _guard_no_secret({k: v for k, v in updated.items() if k != "secret_scan"})
    updated.pop("self_digest", None)
    updated["self_digest"] = receipt_digest(updated)
    return updated


def _validate_host_identity(host_identity: Any) -> dict[str, Any]:
    if not isinstance(host_identity, dict):
        raise FailClosedStop("host_identity must be an object")
    if host_identity.get("passwordless_sudo_present") is not False:
        raise FailClosedStop("host_identity.passwordless_sudo_present must be false (fail-closed STOP)")
    if host_identity.get("non_root_uid") is not True:
        raise FailClosedStop("host_identity.non_root_uid must be true (non-root only)")
    if host_identity.get("throwaway_root_under_runtime_dir") is not True:
        raise FailClosedStop("host_identity.throwaway_root_under_runtime_dir must be true")
    controllers = host_identity.get("delegated_controllers")
    if not isinstance(controllers, list) or not REQUIRED_DELEGATED_CONTROLLERS <= set(controllers):
        raise FailClosedStop(
            f"host_identity.delegated_controllers must include {sorted(REQUIRED_DELEGATED_CONTROLLERS)}"
        )
    expected_host = host_identity.get("expected_host")
    if not isinstance(expected_host, str) or not expected_host:
        raise FailClosedStop("host_identity.expected_host must be a non-empty string")
    # #T3:observed_host 是真觀察的 nodename(preflight 已與 expected 綁定);必須存在、非空、且 == expected。
    observed_host = host_identity.get("observed_host")
    if not isinstance(observed_host, str) or not observed_host:
        raise FailClosedStop("host_identity.observed_host must be a non-empty string (the real observed nodename)")
    if observed_host != expected_host:
        raise FailClosedStop(
            f"host_identity.observed_host {observed_host!r} != expected_host {expected_host!r} "
            "(host spoof) — fail-closed STOP"
        )
    return {
        "expected_host": expected_host,
        "observed_host": observed_host,
        "non_root_uid": True,
        "passwordless_sudo_present": False,
        "delegated_controllers": sorted(set(controllers)),
        "deferred_root_only_controllers": list(host_identity.get("deferred_root_only_controllers") or DEFERRED_ROOT_ONLY_CONTROLLERS),
        "throwaway_root_under_runtime_dir": True,
    }


def _validate_platform(platform: Any) -> dict[str, Any]:
    if (
        not isinstance(platform, dict)
        or platform.get("os") not in PLATFORM_OS
        or not isinstance(platform.get("arch"), str)
        or not platform.get("arch")
        or not isinstance(platform.get("python_version"), str)
        or not platform.get("python_version")
        or not isinstance(platform.get("systemd_run_available"), bool)
        or not isinstance(platform.get("bwrap_available"), bool)
    ):
        raise TargetHostProbeError("platform must bind os/arch/python_version/systemd_run/bwrap flags")
    if platform.get("non_root_oci_runtime_available") is not False:
        raise TargetHostProbeError("platform.non_root_oci_runtime_available must be false (no rootless OCI on target)")
    return {
        "os": platform["os"],
        "arch": platform["arch"],
        "python_version": platform["python_version"],
        "systemd_run_available": platform["systemd_run_available"],
        "bwrap_available": platform["bwrap_available"],
        "non_root_oci_runtime_available": False,
    }


def _normalize_fixed_path_seams(seams: Any, pg_identity_mode: str) -> list[dict[str, Any]]:
    if not isinstance(seams, list):
        raise TargetHostProbeError("fixed_path_seams must be a list")
    by_id: dict[str, dict[str, Any]] = {}
    for seam in seams:
        if not isinstance(seam, dict):
            raise TargetHostProbeError("fixed-path seam must be an object")
        seam_id = seam.get("seam_id")
        if seam_id not in TARGET_HOST_SEAM_SET:
            raise TargetHostProbeError(f"unrecognized fixed-path seam: {seam_id!r}")
        if seam_id in by_id:
            raise TargetHostProbeError(f"duplicate fixed-path seam: {seam_id!r}")
        verdict = seam.get("verdict")
        if verdict not in FIXED_PATH_SEAM_VERDICTS:
            # fixed-path seam 只能 PASSED / DEFERRED;NON_SATISFIABLE 是 OCI 專屬,禁走私。
            raise TargetHostProbeError(f"fixed-path seam {seam_id!r} verdict must be PASSED/DEFERRED, saw {verdict!r}")
        if not DIGEST_RE.fullmatch(str(seam.get("evidence_digest"))):
            raise TargetHostProbeError(f"fixed-path seam {seam_id!r} evidence_digest is invalid")
        if not isinstance(seam.get("note"), str) or not seam.get("note"):
            raise TargetHostProbeError(f"fixed-path seam {seam_id!r} note is required")
        record = {
            "seam_id": seam_id,
            "verdict": verdict,
            "evidence_digest": seam["evidence_digest"],
            "note": seam["note"],
        }
        if seam_id == SEAM_NATIVE_LIB:
            representativeness = seam.get("representativeness", NATIVE_REPRESENTATIVE)
            if representativeness not in {NATIVE_REPRESENTATIVE, NATIVE_FULL_CLOSURE}:
                raise TargetHostProbeError("native_lib_loading representativeness is invalid")
            record["representativeness"] = representativeness
        elif "representativeness" in seam:
            raise TargetHostProbeError(f"only native_lib_loading may carry representativeness (saw on {seam_id!r})")
        by_id[seam_id] = record
    if set(by_id) != TARGET_HOST_SEAM_SET:
        raise TargetHostProbeError(
            f"fixed_path_seams must be exactly {sorted(TARGET_HOST_SEAM_SET)} "
            f"(missing={sorted(TARGET_HOST_SEAM_SET - set(by_id))})"
        )
    # pg_identity_mode 與 PG seam verdict 一致性:REAL⟹PASSED、DEFERRED⟹DEFERRED,禁不一致走私。
    pg_verdict = by_id[SEAM_PG_IDENTITY]["verdict"]
    if pg_identity_mode == PG_MODE_REAL and pg_verdict != SEAM_VERDICT_PASSED:
        raise TargetHostProbeError("pg_identity_mode=real_initdb_cluster requires the pg_identity seam PASSED_TARGET_HOST")
    if pg_identity_mode == PG_MODE_DEFERRED and pg_verdict != SEAM_VERDICT_DEFERRED:
        raise TargetHostProbeError("pg_identity_mode=deferred_server_absent requires the pg_identity seam DEFERRED_TARGET_HOST")
    return [by_id[seam_id] for seam_id in TARGET_HOST_SEAMS]


# --------------------------------------------------------------------------- #
# choice receipt validator (structure/integrity + the machine-encoded rules)
# --------------------------------------------------------------------------- #
def validate_target_host_choice_receipt(
    receipt: Any,
    *,
    require_success: bool = False,
    require_target_host_attested: bool = False,
    now: str | None = None,
) -> list[str]:
    """Validate the target-host choice receipt structure/integrity + every crux.

    Schema subset、exact field-set、const identity、digest regexes、source/schema binding、
    host_identity fail-closed 常量、platform、OCI-non-satisfiable(每 OCI seam 必
    ``NON_SATISFIABLE_NON_ROOT``)、fixed-path seam 封閉集 + verdict 域(僅 PASSED/DEFERRED)+
    native representativeness、BINDING-requires-all-fixed-path-PASSED 閘(BINDING 卻夾 DEFERRED →
    拒;PROVISIONAL 卻無 unmet → 拒;pending_seams 必精確等於 unmet)、選擇規則
    (``oci_selectable == target_host_probe_performed AND all OCI seams passed``,恆 false → final
    須 fixed-path)、const boundary、``production_running_attested==false``、matrix-digest 綁定 live
    central、applier!=verifier、secret-free 序列化、TTL/time ordering、``self_digest`` 重算。

    ``require_target_host_attested=True`` 額外要求 ``evidence_class==PLATFORM_OR_EXTERNAL_ATTESTED``:
    Mac 的 STRUCTURAL_ONLY 合成無法自證 target-host 出口,消費者採信真出口時必開此旗標。

    ACCEPTANCE CONTRACT:``self_digest`` 只證完整性非真確性(CLAUDE.md)。把本 receipt 當 S1.6B
    真出口採信者 **必須** 於 trade-core 重跑探針或取得 governed on-host capture,並以 digest 重抓
    S1.1/S1.4/S1.5 依賴重驗——不得單憑 receipt bytes 認證 PASS。
    """

    if not isinstance(receipt, dict):
        return ["target-host choice receipt must be an object"]
    schema = _receipt_schema()
    errors = [
        f"target-host choice receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != RECEIPT_FIELDS:
        errors.append(
            "target-host choice receipt fields mismatch: "
            f"missing={sorted(RECEIPT_FIELDS - set(receipt))} extra={sorted(set(receipt) - RECEIPT_FIELDS)}"
        )
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        errors.append("target-host choice receipt schema_version is invalid")
    if receipt.get("harness_id") != HARNESS_ID:
        errors.append("target-host choice receipt harness_id is invalid")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        errors.append("target-host choice receipt status is invalid")
    if receipt.get("target_class") != TARGET_CLASS:
        errors.append("target-host choice receipt target_class must be target_host")
    if receipt.get("evidence_class") not in EVIDENCE_CLASSES:
        errors.append("target-host choice receipt evidence_class is invalid")
    if receipt.get("production_running_attested") is not False:
        errors.append("target-host choice receipt production_running_attested must be false")

    for field_name in ("source_sha256", "schema_sha256", "self_digest"):
        if not DIGEST_RE.fullmatch(str(receipt.get(field_name, ""))):
            errors.append(f"target-host choice receipt {field_name} is invalid")
    if receipt.get("source_sha256") != source_sha256():
        errors.append("target-host choice receipt source_sha256 does not bind this module")
    if receipt.get("schema_sha256") != receipt_schema_sha256():
        errors.append("target-host choice receipt schema_sha256 does not bind the schema")
    capture_digest = receipt.get("target_host_capture_digest")
    if capture_digest is not None and not DIGEST_RE.fullmatch(str(capture_digest)):
        errors.append("target-host choice receipt target_host_capture_digest must be a sha256 digest or null")

    errors.extend(_validate_host_identity_block(receipt))
    errors.extend(_validate_probe_scope(receipt))
    errors.extend(_validate_candidate_probes(receipt))
    errors.extend(_validate_selection(receipt))
    errors.extend(_validate_unselected_path(receipt))
    errors.extend(_validate_dependency_receipts(receipt))
    errors.extend(_validate_boundary(receipt))
    errors.extend(_validate_secret_scan(receipt))
    errors.extend(_validate_times(receipt, now=now))

    status = receipt.get("status")
    failure_reason = receipt.get("failure_reason")
    if status == "PASS":
        if failure_reason is not None:
            errors.append("PASS target-host choice receipt cannot carry a failure_reason")
        if receipt.get("evidence_class") != EVIDENCE_ATTESTED:
            errors.append("PASS target-host choice receipt requires evidence_class PLATFORM_OR_EXTERNAL_ATTESTED")
        boundary = receipt.get("boundary") or {}
        if boundary.get("real_target_host_primitives_invoked") is not True:
            errors.append("PASS target-host choice receipt requires real_target_host_primitives_invoked true")
        if boundary.get("complete_teardown_verified") is not True:
            errors.append("PASS target-host choice receipt requires complete_teardown_verified true")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAIL target-host choice receipt requires a non-empty failure_reason")

    if require_target_host_attested:
        if receipt.get("evidence_class") != EVIDENCE_ATTESTED:
            errors.append(
                "target-host choice receipt is not PLATFORM_OR_EXTERNAL_ATTESTED: a structural synthesis "
                "cannot certify the target-host exit (re-run on trade-core / obtain the on-host capture)"
            )
        capture_digest = receipt.get("target_host_capture_digest")
        # 真確性不可靠自報 label 或裸 digest 字串:必須內嵌一個 verifier-bound 的 governed command_capture_v2
        # ARTIFACT。離線僅結構接受(**非認證**,CLAUDE.md)——內嵌 artifact 才是受信主機重放認證的對象。
        if not DIGEST_RE.fullmatch(str(capture_digest or "")):
            errors.append(
                "target-host choice receipt lacks a bound governed on-host command_capture_v2 digest "
                "(target_host_capture_digest); a self-reported evidence_class cannot certify the target-host exit"
            )
        capture = receipt.get("target_host_capture")
        if not isinstance(capture, dict):
            errors.append(
                "target-host choice receipt lacks an embedded governed command_capture_v2 artifact under "
                "target_host_capture; a bare digest cannot certify the target-host exit (offline structural "
                "acceptance is not authentication — a trusted host replays the embedded artifact)"
            )
        else:
            if capture.get("schema_version") != "command_capture_v2":
                errors.append("target_host_capture must be a command_capture_v2 record (schema_version)")
            if str(capture.get("record_digest")) != str(capture_digest):
                errors.append(
                    "target_host_capture.record_digest must equal target_host_capture_digest "
                    "(the digest and the embedded artifact are decoupled)"
                )
            if not (isinstance(capture.get("node_id"), str) and capture.get("node_id")):
                errors.append("target_host_capture must carry a non-empty capturer node_id")
            if not (isinstance(capture.get("native_agent"), str) and capture.get("native_agent")):
                errors.append("target_host_capture must carry a non-empty capturer native_agent")
            errors.extend(
                "target_host_capture is not a complete governed command capture: "
                + error
                for error in governed_capture.validate_governed_command_capture(
                    capture
                )
            )
    if require_success:
        if now is None:
            errors.append("target-host choice receipt PASS acceptance requires a non-null now for freshness")
        if status != "PASS":
            errors.append("target-host choice receipt does not prove a passing target-host probe")
    if receipt.get("self_digest") != receipt_digest(receipt):
        errors.append("target-host choice receipt self_digest does not match canonical receipt")
    return errors


def _validate_host_identity_block(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    host = receipt.get("host_identity")
    if not isinstance(host, dict):
        return ["target-host choice receipt host_identity is missing"]
    if host.get("passwordless_sudo_present") is not False:
        errors.append("host_identity.passwordless_sudo_present must be false (fail-closed STOP)")
    if host.get("non_root_uid") is not True:
        errors.append("host_identity.non_root_uid must be true")
    if host.get("throwaway_root_under_runtime_dir") is not True:
        errors.append("host_identity.throwaway_root_under_runtime_dir must be true")
    controllers = host.get("delegated_controllers")
    if not isinstance(controllers, list) or not REQUIRED_DELEGATED_CONTROLLERS <= set(controllers):
        errors.append(f"host_identity.delegated_controllers must include {sorted(REQUIRED_DELEGATED_CONTROLLERS)}")
    # #T3:真觀察的 nodename 必存在、非空、且 == expected_host,否則任一非 target 盒可冒稱 target host。
    expected_host = host.get("expected_host")
    observed_host = host.get("observed_host")
    if not isinstance(observed_host, str) or not observed_host:
        errors.append("host_identity.observed_host must be a non-empty string (the real observed nodename)")
    elif observed_host != expected_host:
        errors.append(
            f"host_identity.observed_host must equal expected_host (host spoof: {observed_host!r} != {expected_host!r})"
        )
    return errors


def _validate_probe_scope(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    scope = receipt.get("probe_scope")
    if not isinstance(scope, dict):
        return ["target-host choice receipt probe_scope is missing"]
    if scope.get("effect_class") != PROBE_EFFECT_CLASS:
        errors.append("probe_scope.effect_class is invalid")
    if scope.get("adapter_id") != PROBE_ADAPTER_ID:
        errors.append("probe_scope.adapter_id must reuse learning_runtime_deploy_adapter_v1")
    if scope.get("pg_identity_mode") not in PG_MODES:
        errors.append("probe_scope.pg_identity_mode is invalid")
    if not isinstance(scope.get("target_host_probe_performed"), bool):
        errors.append("probe_scope.target_host_probe_performed must be boolean")
    return errors


def _validate_candidate_probes(receipt: dict[str, Any]) -> list[str]:
    probes = receipt.get("candidate_probes")
    if not isinstance(probes, list) or len(probes) != 2:
        return ["target-host choice receipt requires exactly both candidates probed"]
    scope = receipt.get("probe_scope") or {}
    pg_identity_mode = scope.get("pg_identity_mode")
    errors: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for block in probes:
        if not isinstance(block, dict):
            errors.append("target-host candidate probe is invalid")
            continue
        candidate_id = block.get("candidate_id")
        if candidate_id not in CANDIDATE_IDS:
            errors.append(f"target-host candidate probe id is not recognized: {candidate_id!r}")
            continue
        if candidate_id in by_id:
            errors.append(f"duplicate target-host candidate probe: {candidate_id!r}")
        by_id[candidate_id] = block
        if block.get("apply_actor_node") == block.get("postcheck_verifier_node"):
            errors.append(f"target-host candidate {candidate_id} applier equals its verifier")
        expected_kind = "exact_image_id" if candidate_id == CANDIDATE_OCI else "content_addressed_path"
        if block.get("runtime_identity_kind") != expected_kind:
            errors.append(f"target-host candidate {candidate_id} runtime_identity_kind is not {expected_kind}")
    if set(by_id) != CANDIDATE_IDS:
        errors.append(f"target-host candidates must be {sorted(CANDIDATE_IDS)} (saw {sorted(by_id)})")
        return errors
    errors.extend(_validate_oci_seams(by_id[CANDIDATE_OCI]))
    errors.extend(_validate_fixed_path_seams(by_id[CANDIDATE_FIXED_PATH], pg_identity_mode))
    return errors


def _validate_oci_seams(block: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seams = block.get("seams")
    if not isinstance(seams, list) or len(seams) < len(TARGET_HOST_SEAMS):
        return ["target-host OCI candidate seams are missing"]
    seen: set[str] = set()
    for seam in seams:
        if not isinstance(seam, dict):
            errors.append("target-host OCI seam is invalid")
            continue
        seen.add(seam.get("seam_id"))
        if seam.get("verdict") != SEAM_VERDICT_NON_SATISFIABLE:
            # PM Q1:每個 OCI target-host seam 必為 NON_SATISFIABLE_NON_ROOT(邊界驅動非選擇)。
            errors.append(f"target-host OCI seam {seam.get('seam_id')!r} must be NON_SATISFIABLE_NON_ROOT")
        if "representativeness" in seam:
            errors.append("target-host OCI seam must not carry representativeness")
    if seen != TARGET_HOST_SEAM_SET:
        errors.append(f"target-host OCI seams must be exactly {sorted(TARGET_HOST_SEAM_SET)}")
    return errors


def _validate_fixed_path_seams(block: dict[str, Any], pg_identity_mode: Any) -> list[str]:
    errors: list[str] = []
    seams = block.get("seams")
    if not isinstance(seams, list) or len(seams) < len(TARGET_HOST_SEAMS):
        return ["target-host fixed-path candidate seams are missing"]
    verdict_by_id: dict[str, str] = {}
    for seam in seams:
        if not isinstance(seam, dict):
            errors.append("target-host fixed-path seam is invalid")
            continue
        seam_id = seam.get("seam_id")
        verdict = seam.get("verdict")
        verdict_by_id[seam_id] = verdict
        if verdict not in FIXED_PATH_SEAM_VERDICTS:
            errors.append(f"target-host fixed-path seam {seam_id!r} verdict must be PASSED/DEFERRED (NON_SATISFIABLE is OCI-only)")
        if seam_id == SEAM_NATIVE_LIB:
            if seam.get("representativeness") not in {NATIVE_REPRESENTATIVE, NATIVE_FULL_CLOSURE}:
                errors.append("target-host native_lib_loading seam must carry a representativeness flag")
        elif "representativeness" in seam:
            errors.append(f"only native_lib_loading may carry representativeness (saw on {seam_id!r})")
    if set(verdict_by_id) != TARGET_HOST_SEAM_SET:
        errors.append(
            f"target-host fixed-path seams must be exactly {sorted(TARGET_HOST_SEAM_SET)} "
            f"(missing={sorted(TARGET_HOST_SEAM_SET - set(verdict_by_id))})"
        )
        return errors
    # pg_identity_mode ↔ pg seam verdict 一致性。
    pg_verdict = verdict_by_id.get(SEAM_PG_IDENTITY)
    if pg_identity_mode == PG_MODE_REAL and pg_verdict != SEAM_VERDICT_PASSED:
        errors.append("pg_identity_mode=real_initdb_cluster requires the pg_identity seam PASSED_TARGET_HOST")
    if pg_identity_mode == PG_MODE_DEFERRED and pg_verdict != SEAM_VERDICT_DEFERRED:
        errors.append("pg_identity_mode=deferred_server_absent requires the pg_identity seam DEFERRED_TARGET_HOST")
    return errors


def _validate_selection(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    selection = receipt.get("selection")
    if not isinstance(selection, dict):
        return ["target-host choice receipt selection is missing"]
    if selection.get("selection_rule") != SELECTION_RULE:
        errors.append("target-host choice receipt selection_rule is invalid")
    if selection.get("oci_selectable") is not False:
        errors.append("target-host choice receipt oci_selectable must be false (OCI is NON_SATISFIABLE_NON_ROOT)")
    if selection.get("binding") not in {BINDING_BINDING, BINDING_PROVISIONAL}:
        errors.append("target-host choice receipt binding is invalid")
    if not isinstance(selection.get("reason"), str) or not selection.get("reason"):
        errors.append("target-host choice receipt selection.reason is required")

    scope = receipt.get("probe_scope") or {}
    target_host_probe_performed = bool(scope.get("target_host_probe_performed"))
    probes = receipt.get("candidate_probes") if isinstance(receipt.get("candidate_probes"), list) else []
    oci_block = next((b for b in probes if isinstance(b, dict) and b.get("candidate_id") == CANDIDATE_OCI), None)
    fixed_block = next((b for b in probes if isinstance(b, dict) and b.get("candidate_id") == CANDIDATE_FIXED_PATH), None)

    oci_seams = (oci_block or {}).get("seams") or []
    oci_all_passed = bool(oci_seams) and all(
        isinstance(seam, dict) and seam.get("verdict") == SEAM_VERDICT_PASSED for seam in oci_seams
    )
    derived_oci_selectable = target_host_probe_performed and oci_all_passed
    if bool(selection.get("oci_selectable")) != derived_oci_selectable:
        errors.append(
            "target-host choice receipt oci_selectable must equal "
            "(target_host_probe_performed AND every OCI seam passed)"
        )
    final_choice = selection.get("final_choice")
    if final_choice == FINAL_CHOICE_OCI and not derived_oci_selectable:
        errors.append("target-host choice receipt cannot select OCI without a probe passing all OCI seams")
    if not derived_oci_selectable and final_choice != FINAL_CHOICE_FIXED_PATH:
        errors.append("target-host choice receipt must fall back to content_addressed_fixed_path")

    # --- crux:BINDING-requires-all-fixed-path-PASSED 閘 ---
    fixed_seams = (fixed_block or {}).get("seams") or []
    verdict_by_id = {
        seam.get("seam_id"): seam.get("verdict")
        for seam in fixed_seams if isinstance(seam, dict)
    }
    unmet = [seam_id for seam_id in TARGET_HOST_SEAMS if verdict_by_id.get(seam_id) != SEAM_VERDICT_PASSED]
    binding = selection.get("binding")
    pending = selection.get("pending_seams")
    if binding == BINDING_BINDING and unmet:
        errors.append(
            "target-host choice receipt claims BINDING but these fixed-path seams are not PASSED_TARGET_HOST: "
            f"{unmet} (must be PROVISIONAL_PENDING_LINUX)"
        )
    if binding == BINDING_PROVISIONAL and not unmet:
        errors.append("target-host choice receipt is PROVISIONAL_PENDING_LINUX but every fixed-path seam PASSED (must be BINDING)")
    if not isinstance(pending, list) or set(pending) != set(unmet):
        errors.append(f"target-host choice receipt pending_seams must exactly name the unmet fixed-path seams {sorted(unmet)}")
    return errors


def _validate_unselected_path(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    removal = receipt.get("unselected_path_removal")
    if not isinstance(removal, dict):
        return ["target-host choice receipt unselected_path_removal is missing"]
    if removal.get("unselected_candidate") != FINAL_CHOICE_OCI:
        errors.append("unselected_path_removal.unselected_candidate must be exact_image_id_oci")
    if removal.get("unselected_production_artifact_present") is not False:
        errors.append("unselected_path_removal.unselected_production_artifact_present must be false")
    if removal.get("production_path_removed") is not True:
        errors.append("unselected_path_removal.production_path_removed must be true")
    if removal.get("forecloses_downstream") is not True:
        errors.append("unselected_path_removal.forecloses_downstream must be true")
    if not isinstance(removal.get("note"), str) or not removal.get("note").strip():
        errors.append("unselected_path_removal.note must be a non-empty string")
    return errors


def _validate_dependency_receipts(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dependency = receipt.get("dependency_receipts")
    if not isinstance(dependency, dict):
        return ["target-host choice receipt dependency_receipts is missing"]
    required = (
        "runtime_candidate_receipt_a_digest",
        "runtime_candidate_receipt_b_digest",
        "runtime_candidate_comparison_digest",
        "effect_seams_ready_receipt_digest",
        "component_effect_matrix_digest",
        "pg_readonly_identity_receipt_digest",
    )
    for field_name in required:
        if not DIGEST_RE.fullmatch(str(dependency.get(field_name, ""))):
            errors.append(f"target-host choice dependency {field_name} is invalid")
    if dependency.get("component_effect_matrix_digest") != ce.component_effect_matrix_digest():
        errors.append("target-host choice dependency component_effect_matrix_digest is not the live central digest")
    return errors


def _validate_boundary(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    boundary = receipt.get("boundary")
    if not isinstance(boundary, dict):
        return ["target-host choice receipt boundary is missing"]
    const_true = (
        "non_root", "user_scope_only", "no_docker_invoked", "no_system_scope",
        "no_production_path", "prod_pg_untouched", "applier_ne_verifier",
    )
    for flag in const_true:
        if boundary.get(flag) is not True:
            errors.append(f"target-host choice receipt boundary.{flag} must be true")
    if boundary.get("production_running_attested") is not False:
        errors.append("target-host choice receipt boundary.production_running_attested must be false")
    for flag in ("real_target_host_primitives_invoked", "complete_teardown_verified"):
        if not isinstance(boundary.get(flag), bool):
            errors.append(f"target-host choice receipt boundary.{flag} must be boolean")
    return errors


def _validate_secret_scan(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    secret_scan = receipt.get("secret_scan")
    if not isinstance(secret_scan, dict):
        return ["target-host choice receipt secret_scan is missing"]
    if secret_scan.get("leaked") is not False:
        errors.append("target-host choice receipt secret_scan must report leaked=false")
    if list(secret_scan.get("patterns_checked", [])) != list(SECRET_PATTERNS_CHECKED):
        errors.append("target-host choice receipt secret_scan patterns are not the exact contract")
    if _contains_secret_like({k: v for k, v in receipt.items() if k != "secret_scan"}):
        errors.append("target-host choice receipt carries secret-like content")
    return errors


def _validate_times(receipt: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    ttl_seconds = receipt.get("ttl_seconds")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        return ["target-host choice receipt ttl_seconds is invalid"]
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        errors.append(f"target-host choice ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    try:
        observed = _parse_time(str(receipt.get("observation_time", "")))
        expires = _parse_time(str(receipt.get("expires_at", "")))
        if expires != observed + timedelta(seconds=ttl_seconds):
            errors.append("target-host choice expires_at does not equal observation_time + ttl")
        if not observed < expires:
            errors.append("target-host choice observation_time must precede expires_at")
        if now is not None:
            current = _parse_time(now)
            if not observed <= current < expires:
                errors.append("target-host choice receipt is not fresh")
    except (TypeError, ValueError):
        errors.append("target-host choice receipt timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# structural reference receipts (STRUCTURAL_ONLY; honest, never a real probe)
# --------------------------------------------------------------------------- #
def _structural_host_identity() -> dict[str, Any]:
    # observed_host == expected_host:結構參照代表「真跑於 trade-core、觀察 nodename==trade-core」的形。
    return {
        "expected_host": EXPECTED_TARGET_HOST_DEFAULT,
        "observed_host": EXPECTED_TARGET_HOST_DEFAULT,
        "non_root_uid": True,
        "passwordless_sudo_present": False,
        "delegated_controllers": sorted(REQUIRED_DELEGATED_CONTROLLERS),
        "deferred_root_only_controllers": list(DEFERRED_ROOT_ONLY_CONTROLLERS),
        "throwaway_root_under_runtime_dir": True,
    }


def _structural_capture_artifact() -> dict[str, Any]:
    """Minimal STRUCTURALLY-valid ``command_capture_v2`` artifact for Mac SHAPE references / structural tests.

    誠實界線:這是 governed on-host ``command_capture_v2`` 記錄的**結構外形**(offline-unauthenticated),
    **不是**真 governed capture。真 trade-core 出口綁的是 OPS ``capture-command`` 產出的真 record(其
    ``record_digest`` 由真執行位元組導出);此 helper 僅供離線結構閘測試「digest↔artifact 綁定」路徑,絕不
    宣稱真跑過 capture。離線結構接受並非認證(CLAUDE.md);受信主機重放此內嵌 artifact 才是認證。
    """

    artifact: dict[str, Any] = {
        "schema_version": "command_capture_v2",
        "node_id": "s16b_ops_capture_node",
        "native_agent": "e3-ops",
        "role_id": "E3",
        "structural_reference_only": True,
    }
    artifact["record_digest"] = _canonical_digest(
        {key: value for key, value in artifact.items() if key != "record_digest"}
    )
    return artifact


def build_structural_reference_receipt(*, now: str, pg_mode: str = PG_MODE_DEFERRED) -> dict[str, Any]:
    """Build a STRUCTURAL_ONLY (status=FAIL) reference receipt for the Mac logic tests.

    誠實標籤:``evidence_class=STRUCTURAL_ONLY``、``real_target_host_primitives_invoked=false`` →
    ``status=FAIL``。DERIVED 選擇欄位(oci_selectable / final_choice / binding / pending_seams)仍如實
    由合成 seam verdict 導出,可供邏輯測試;但此 receipt 過不了 ``require_target_host_attested``。
    """

    return build_target_host_choice_receipt(
        caller="target_host_probe_v1:structural-reference",
        platform=detect_platform(),
        target_class=TARGET_CLASS,
        host_identity=_structural_host_identity(),
        apply_actor_node="s16b_apply_actor",
        postcheck_verifier_node="s16b_independent_verifier",
        fixed_path_seams=synthesize_fixed_path_seams(pg_mode),
        pg_identity_mode=pg_mode,
        evidence_class=EVIDENCE_STRUCTURAL,
        real_target_host_primitives_invoked=False,
        complete_teardown_verified=False,
        runtime_candidate_receipt_a_digest=_canonical_digest({"s1_4": "a"}),
        runtime_candidate_receipt_b_digest=_canonical_digest({"s1_4": "b"}),
        runtime_candidate_comparison_digest=_canonical_digest({"s1_4": "cmp"}),
        effect_seams_ready_receipt_digest=_canonical_digest({"s1_5": "effect_seams_ready"}),
        pg_readonly_identity_receipt_digest=_canonical_digest({"s1_1": "pg_readonly_identity"}),
        observation_time=now, ttl_seconds=900,
    )


def build_attested_reference_receipt(
    *,
    now: str,
    pg_mode: str = PG_MODE_REAL,
    independent_postcheck_attached: bool = True,
    capture_digest: str | None = None,
    include_capture_artifact: bool = False,
    capture_artifact: dict[str, Any] | None = None,
    apply_actor_node: str = "s16b_apply_actor",
    postcheck_verifier_node: str = "s16b_independent_verifier",
) -> dict[str, Any]:
    """Build a PLATFORM_OR_EXTERNAL_ATTESTED (status=PASS) reference, as the REAL trade-core run would.

    表達「真出口長什麼樣」的 shape 參照:``evidence_class=ATTESTED`` + invoked + teardown → ``status=PASS``。
    ``pg_mode=real_initdb_cluster`` 且 ``independent_postcheck_attached`` ⇒ 全 seam PASSED ⇒ ``BINDING``。
    ``independent_postcheck_attached=False`` ⇒ independent_postcheck DEFERRED(applier 自跑形)⇒
    ``PROVISIONAL_PENDING_LINUX`` 指名 independent_postcheck。

    預設(``include_capture_artifact=False`` 且 ``capture_digest=None``)⇒ 無內嵌 governed capture artifact ⇒
    **過不了 ``require_target_host_attested``**(這是刻意的:Mac 參照無法自證真出口)。``include_capture_artifact=
    True`` ⇒ 合成一個結構有效的 ``command_capture_v2`` artifact(offline-unauthenticated 的**結構參照**,非真跑)
    以行使 attested-PASS 的結構路徑;``capture_digest`` 則只內嵌裸 digest(仍過不了 attested,示範裸 digest 不足)。
    """

    if capture_artifact is not None and include_capture_artifact:
        raise ValueError(
            "pass either capture_artifact or include_capture_artifact, not both"
        )
    capture_artifact = (
        copy.deepcopy(capture_artifact)
        if capture_artifact is not None
        else _structural_capture_artifact()
        if include_capture_artifact
        else None
    )
    return build_target_host_choice_receipt(
        caller="target_host_probe_v1:attested-reference",
        platform=detect_platform(),
        target_class=TARGET_CLASS,
        host_identity=_structural_host_identity(),
        apply_actor_node=apply_actor_node,
        postcheck_verifier_node=postcheck_verifier_node,
        fixed_path_seams=synthesize_fixed_path_seams(
            pg_mode, evidence_marker=EVIDENCE_ATTESTED,
            independent_postcheck_attached=independent_postcheck_attached,
        ),
        pg_identity_mode=pg_mode,
        evidence_class=EVIDENCE_ATTESTED,
        real_target_host_primitives_invoked=True,
        complete_teardown_verified=True,
        runtime_candidate_receipt_a_digest=_canonical_digest({"s1_4": "a"}),
        runtime_candidate_receipt_b_digest=_canonical_digest({"s1_4": "b"}),
        runtime_candidate_comparison_digest=_canonical_digest({"s1_4": "cmp"}),
        effect_seams_ready_receipt_digest=_canonical_digest({"s1_5": "effect_seams_ready"}),
        pg_readonly_identity_receipt_digest=_canonical_digest({"s1_1": "pg_readonly_identity"}),
        observation_time=now, ttl_seconds=900,
        target_host_capture_digest=capture_digest,
        target_host_capture_artifact=capture_artifact,
    )


# --------------------------------------------------------------------------- #
# bypass-negatives (fail-closed; each REALLY triggers the rejection, no rubber stamp)
# --------------------------------------------------------------------------- #
def _resign(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt = copy.deepcopy(receipt)
    receipt.pop("self_digest", None)
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


def _reject_or_vacuous(
    receipt: dict[str, Any], *, needle: str, now: str, require_target_host_attested: bool = False
) -> None:
    errors = validate_target_host_choice_receipt(
        receipt, now=now, require_target_host_attested=require_target_host_attested
    )
    matched = [error for error in errors if needle in error]
    if matched:
        raise TargetHostProbeError("rejected: " + "; ".join(matched[:2]))
    return None


def _bypass_oci_seam_claimed_satisfiable(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    oci_block = next(b for b in receipt["candidate_probes"] if b["candidate_id"] == CANDIDATE_OCI)
    oci_block["seams"][0]["verdict"] = SEAM_VERDICT_PASSED  # 謊稱某 OCI seam 可滿足 → 拒
    _reject_or_vacuous(_resign(receipt), needle="NON_SATISFIABLE_NON_ROOT", now=now)


def _bypass_oci_selected_without_all_seams_passing(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["selection"]["final_choice"] = FINAL_CHOICE_OCI  # OCI 不可選卻選 OCI → 拒
    _reject_or_vacuous(_resign(receipt), needle="select OCI", now=now)


def _bypass_binding_with_deferred_fixed_path_seam(now: str) -> None:
    # 真出口若 pg DEFERRED 必為 PROVISIONAL;硬標 BINDING(留 pg DEFERRED)→ BINDING 閘拒。
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_DEFERRED)
    receipt["selection"]["binding"] = BINDING_BINDING
    receipt["selection"]["pending_seams"] = []
    _reject_or_vacuous(_resign(receipt), needle="claims BINDING but these fixed-path seams", now=now)


def _bypass_provisional_without_unmet_seam(now: str) -> None:
    # 全 seam PASSED 卻標 PROVISIONAL → 拒(必為 BINDING)。
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["selection"]["binding"] = BINDING_PROVISIONAL
    receipt["selection"]["pending_seams"] = [SEAM_PG_IDENTITY]
    _reject_or_vacuous(_resign(receipt), needle="PROVISIONAL_PENDING_LINUX but every fixed-path seam PASSED", now=now)


def _bypass_pending_seams_mismatch(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_DEFERRED)
    receipt["selection"]["pending_seams"] = [SEAM_START_STOP]  # 未如實指名 unmet(pg_identity)→ 拒
    _reject_or_vacuous(_resign(receipt), needle="pending_seams must exactly name", now=now)


def _bypass_attested_without_primitives_invoked(now: str) -> None:
    # 謊稱 ATTESTED 卻 real_target_host_primitives_invoked=false → PASS 分支拒(假背書)。
    receipt = build_structural_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["evidence_class"] = EVIDENCE_ATTESTED
    receipt["status"] = "PASS"
    receipt["failure_reason"] = None
    receipt["probe_scope"]["target_host_probe_performed"] = True
    # 仍留 real_target_host_primitives_invoked=false → 觸 PASS 分支的 real_invoked 檢查。
    _reject_or_vacuous(_resign(receipt), needle="real_target_host_primitives_invoked true", now=now)


def _bypass_passwordless_sudo_present(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["host_identity"]["passwordless_sudo_present"] = True
    _reject_or_vacuous(_resign(receipt), needle="passwordless_sudo_present must be false", now=now)


def _bypass_missing_delegated_controller(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["host_identity"]["delegated_controllers"] = ["cpu", "pids"]  # 缺 memory → 拒
    _reject_or_vacuous(_resign(receipt), needle="delegated_controllers must include", now=now)


def _bypass_production_path_in_scope(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["boundary"]["no_production_path"] = False
    _reject_or_vacuous(_resign(receipt), needle="boundary.no_production_path must be true", now=now)


def _bypass_docker_invoked_in_scope(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["boundary"]["no_docker_invoked"] = False
    _reject_or_vacuous(_resign(receipt), needle="boundary.no_docker_invoked must be true", now=now)


def _bypass_system_scope_used(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["boundary"]["no_system_scope"] = False
    _reject_or_vacuous(_resign(receipt), needle="boundary.no_system_scope must be true", now=now)


def _bypass_prod_pg_contacted(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["boundary"]["prod_pg_untouched"] = False
    _reject_or_vacuous(_resign(receipt), needle="boundary.prod_pg_untouched must be true", now=now)


def _bypass_applier_is_sole_verifier(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    block = receipt["candidate_probes"][0]
    block["postcheck_verifier_node"] = block["apply_actor_node"]  # applier == verifier → 拒
    _reject_or_vacuous(_resign(receipt), needle="applier equals its verifier", now=now)


def _bypass_production_running_attested_claimed(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["production_running_attested"] = True
    receipt["boundary"]["production_running_attested"] = True
    _reject_or_vacuous(_resign(receipt), needle="production_running_attested", now=now)


def _bypass_matrix_digest_tamper(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    receipt["dependency_receipts"]["component_effect_matrix_digest"] = "sha256:" + "0" * 64
    _reject_or_vacuous(_resign(receipt), needle="matrix", now=now)


def _bypass_plaintext_secret_ingress(now: str) -> None:
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL)
    poisoned = copy.deepcopy(receipt)
    poisoned["selection"]["reason"] = "authorization=Bearer plaintexthunter2exampletoken"
    _guard_no_secret({k: v for k, v in poisoned.items() if k != "secret_scan"})  # 必 raise


def _bypass_host_identity_spoofed(now: str) -> None:
    # #T3:observed_host 與 expected_host 不符(冒稱 trade-core)→ host_identity 閘拒。
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL, include_capture_artifact=True)
    receipt["host_identity"]["observed_host"] = "attacker-box"  # != expected_host(trade-core)→ 拒
    _reject_or_vacuous(_resign(receipt), needle="observed_host", now=now)


def _bypass_attested_digest_without_capture_artifact(now: str) -> None:
    # #T1:ATTESTED + 裸 synthetic digest 但無內嵌 command_capture_v2 artifact → require_target_host_attested 拒。
    receipt = build_attested_reference_receipt(now=now, pg_mode=PG_MODE_REAL, capture_digest="sha256:" + "e" * 64)
    _reject_or_vacuous(
        receipt, needle="embedded governed command_capture_v2 artifact", now=now,
        require_target_host_attested=True,
    )


_BYPASS_RUNNERS: dict[str, Callable[[str], None]] = {
    "oci_seam_claimed_satisfiable": _bypass_oci_seam_claimed_satisfiable,
    "oci_selected_without_all_seams_passing": _bypass_oci_selected_without_all_seams_passing,
    "binding_with_deferred_fixed_path_seam": _bypass_binding_with_deferred_fixed_path_seam,
    "provisional_without_unmet_seam": _bypass_provisional_without_unmet_seam,
    "pending_seams_mismatch": _bypass_pending_seams_mismatch,
    "attested_without_primitives_invoked": _bypass_attested_without_primitives_invoked,
    "passwordless_sudo_present": _bypass_passwordless_sudo_present,
    "missing_delegated_controller": _bypass_missing_delegated_controller,
    "production_path_in_scope": _bypass_production_path_in_scope,
    "docker_invoked_in_scope": _bypass_docker_invoked_in_scope,
    "system_scope_used": _bypass_system_scope_used,
    "prod_pg_contacted": _bypass_prod_pg_contacted,
    "applier_is_sole_verifier": _bypass_applier_is_sole_verifier,
    "production_running_attested_claimed": _bypass_production_running_attested_claimed,
    "matrix_digest_tamper": _bypass_matrix_digest_tamper,
    "plaintext_secret_ingress": _bypass_plaintext_secret_ingress,
    "host_identity_spoofed": _bypass_host_identity_spoofed,
    "attested_digest_without_capture_artifact": _bypass_attested_digest_without_capture_artifact,
}


def run_bypass_negative(kind: str, *, now: str) -> dict[str, Any]:
    """Run one bypass-negative; confirm it REALLY fails closed (no rubber stamp).

    若 runner 未 raise,該例為 vacuous,重新 raise ``TargetHostProbeError`` —— receipt 絕不得在
    路徑未真拒時記錄該 bypass 為 REJECTED。
    """

    runner = _BYPASS_RUNNERS.get(kind)
    if runner is None:
        raise TargetHostProbeError(f"unknown bypass-negative kind: {kind!r}")
    try:
        runner(now)
    except (TargetHostProbeError, ce.ComponentEffectError, ValueError) as error:
        return {
            "case_id": f"neg-{BYPASS_KINDS.index(kind) + 1:02d}-{kind}",
            "bypass_kind": kind,
            "expected": "FAIL_CLOSED",
            "observed_verdict": "REJECTED",
            "evidence_class": EVIDENCE_STRUCTURAL,
            "reason": str(error)[:200],
        }
    raise TargetHostProbeError(f"bypass-negative {kind!r} did not fail closed (vacuous rejection)")


def build_bypass_negative_cases(*, now: str) -> list[dict[str, Any]]:
    """Run all eighteen bypass-negatives and return their REJECTED case records."""

    return [run_bypass_negative(kind, now=now) for kind in BYPASS_KINDS]

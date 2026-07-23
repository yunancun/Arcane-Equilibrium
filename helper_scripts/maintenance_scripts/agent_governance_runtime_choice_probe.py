"""Isolated disposable runtime probe + final single-runtime choice for AIML LR0C (S1.6).

This harness runs, for BOTH plan-§LR0C candidates, one ISOLATED **disposable-local**
runtime probe by REUSING S1.5's ``LEARNING_RUNTIME`` ``temp_dir_artifact``
apply/rollback/postcheck lifecycle as the probe effect actor, records the honest
disposable-proven vs target-host-deferred seam split, then makes the final
single-runtime choice under the plan's own asymmetric rule and forecloses the
unselected OCI production path.  It emits one canonical self-hashed
``learning_runtime_choice_receipt_v1``.

The two candidates are:

* ``exact_image_id_oci`` — OCI image pinned by exact image ID (``content_addressed_standin``
  on Mac: the same content-addressed lifecycle stands in, it is NOT an OCI runtime).
* ``content_addressed_fixed_path`` — a hash-named runtime bundle at a fixed path
  (``native_shape``: the ``temp_dir_artifact`` lifecycle IS this candidate's runtime shape).

S1.6 attests **nothing running**.  ``target_host_probe_performed`` is honestly
``false`` on this Mac, so the machine-encoded rule
``oci_selectable == (target_host_probe_performed AND every OCI target-host seam passed)``
forces ``oci_selectable=false`` ⇒ ``final_choice=content_addressed_fixed_path``
(BINDING).  ``production_running_attested`` and every ``boundary.*`` running flag
are const ``false``.  The decisive isolation seams (cgroup / kernel network denial /
native-lib LOADING on target / true target-host start / target-host PG identity /
networked ML-closure resolution) are ``DEFERRED_TARGET_HOST`` for BOTH candidates —
a receipt that marked any of them disposably-proven is **rejected**.

Like S1.3/S1.4 this harness SELF-VALIDATES its own receipt and is NOT registered
into the central AIML closure-validator, the governance registry, the
route-compiler, permissions or the vocabulary; S1.6 stays disjoint.  (By contrast
S1.1's pg-receipt and S1.5's effect-seam/component receipts WERE added to the
central ``SCHEMA_FILES`` for delegated recognition — the split is: closure-carried
seam/identity proof receipts get eager central recognition, while intermediate
self-contained contract receipts — S1.3, S1.4, S1.6 — self-validate.)  It REUSES
(read-only imports) S1.5 ``agent_governance_component_effects`` (the disposable
lifecycle + intent/result/attestation builders) and S1.4
``agent_governance_runtime_candidate_spike`` (the candidate ids, ``hash_bundle_tree``
and the const-null comparison).  The S1.1 disposable RO-PG identity probe is used by
the disposable TEST (not imported by this module); this module binds the S1.1 42501
evidence by digest/shape only.  It makes NO network / remote / process / native-load
contact and starts NO real service.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import agent_governance_component_effects as ce
import agent_governance_runtime_candidate_spike as spike
from agent_governance_schema import schema_subset_errors


HARNESS_ID = "runtime_choice_probe_v1"
RECEIPT_SCHEMA_VERSION = "learning_runtime_choice_receipt_v1"
PROBE_EFFECT_CLASS = "TARGET_HOST_DISPOSABLE_RUNTIME_PROBE"
PROBE_ADAPTER_ID = "learning_runtime_deploy_adapter_v1"  # S1.5 已註冊,S1.6 復用、不新增

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
SCHEMA_DIR = REPO_ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
RECEIPT_SCHEMA_PATH = SCHEMA_DIR / "learning_runtime_choice_receipt_v1.schema.json"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# 兩候選的合法 id(復用 S1.4);未知 id 一律 fail-closed。
CANDIDATE_OCI = spike.CANDIDATE_OCI  # "exact_image_id_oci"
CANDIDATE_FIXED_PATH = spike.CANDIDATE_FIXED_PATH  # "content_addressed_fixed_path"
CANDIDATE_IDS = frozenset({CANDIDATE_OCI, CANDIDATE_FIXED_PATH})

# Mac 交付面只接受 disposable_local;target_host 屬未來 Linux OPS 探針,production 更無論。
MAC_TARGET_CLASS = "disposable_local"
SCHEMA_TARGET_CLASSES = frozenset({"disposable_local", "target_host"})
REJECTED_MAC_TARGET_CLASSES = frozenset({"production", "target_host"})

EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"})
PLATFORM_OS = frozenset({"darwin", "linux"})
TTL_CEILING_SECONDS = 3600

# seam 裁決:disposable 可證 / target-host 延後。
VERDICT_DISPOSABLE = "DISPOSABLE_PROVEN"
VERDICT_DEFERRED = "DEFERRED_TARGET_HOST"
# 一個「未來 Linux 探針才可能」的通過裁決;v1(Mac)receipt 版刻意不可達:v1 schema 對 deferred
# seam 的 verdict const=DEFERRED_TARGET_HOST(無 PASSED_TARGET_HOST 常量),故 _oci_target_host_
# seams_all_passed() 於本版恆為 False、affirmative OCI-selectable 分支結構上打不到。此常量保留給
# 未來的 Linux target-host receipt 版(S2.5 真實探針)才會翻轉。
SEAM_VERDICT_PASSED = "PASSED_TARGET_HOST"

# 六個一律可在本機重現的 disposable lifecycle seam(純 stdlib 檔案系統轉換,到處可跑)。
CORE_DISPOSABLE_SEAMS = (
    "start_stop",
    "failure_recovery",
    "rollback",
    "complete_cleanup",
    "immutable_dependency_closure",
    "artifact_persistence",
)
CORE_DISPOSABLE_SEAM_SET = frozenset(CORE_DISPOSABLE_SEAMS)
# 第七個 disposable seam:disposable PG identity(initdb-gated;無 PG 二進位即誠實跳過,不列)。
PG_IDENTITY_SEAM = "disposable_pg_identity"
ALLOWED_DISPOSABLE_SEAMS = CORE_DISPOSABLE_SEAM_SET | {PG_IDENTITY_SEAM}

# 六個決定性 target-host seam:只有真實 Linux target-host 探針(S2.5)或網路封存建置(S2.3)
# 才可行使;本 receipt 內必為 DEFERRED_TARGET_HOST。標成 disposably-proven 的 receipt 被拒。
TARGET_HOST_DEFERRED_SEAMS = (
    "cgroup_isolation",
    "network_denial_kernel",
    "native_lib_loading_target",
    "true_target_host_start",
    "target_host_pg_identity",
    "networked_ml_closure_resolution",
)
TARGET_HOST_DEFERRED_SEAM_SET = frozenset(TARGET_HOST_DEFERRED_SEAMS)

REPRESENTATIVENESS_NATIVE = "native_shape"
REPRESENTATIVENESS_STANDIN = "content_addressed_standin"

# 選擇區塊常量(machine-encoded 規則,§5.1)。
FINAL_CHOICE_FIXED_PATH = "content_addressed_fixed_path"
FINAL_CHOICE_OCI = "exact_image_id_oci"
SELECTION_RULE = "oci_only_if_all_seams_pass_else_fixed_path"
SELECTION_BASIS = (
    "oci_all_seams_pass_precondition_unmet",
    "lr2_no_oci_socket_dbus_constraint",
    "fixed_path_offline_and_disposable_seams_proven",
)
SELECTION_REASON = (
    "OCI's decisive isolation seams are not satisfiable in the available "
    "disposable/target-host-deferred evidence; fixed-path satisfies the "
    "offline-provable seams and LR2's no-OCI-socket constraint."
)
BINDING_BINDING = "BINDING"
# PROVISIONAL 分支在本版未被行使:PM 已確認 BINDING(§6.3/§11-Q1),fixed-path 之選擇以「當下即可
# 裁定」的規則+LR2 規範為據,非待 Linux 探針。此常量保留供未來若有 ADR 放寬 LR2 時的降級路徑。
BINDING_PROVISIONAL = "PROVISIONAL_PENDING_LINUX"
TARGET_HOST_DEFERRED_TO = "S2.3_sealed_build_and_S2.5_running_attestation"

UNSELECTED_NOTE = (
    "S1.4 was design-only: no AIML OCI Dockerfile/build/install artifact exists to "
    "delete (the repo Dockerfile is the unrelated Bybit connector control API). "
    "LR2/S2.3 seals ONLY the fixed-path runtime; no downstream session may create an "
    "OCI build/install path."
)

# 每候選允許出現的 caveat(受 schema/validator 封閉集約束)。
OCI_CAVEATS = (
    "arch_limited_colima_arm64",
    "no_buildx",
    "no_target_host_container_runtime",
    "lr2_no_oci_socket_dbus",
)
FIXED_PATH_CAVEATS = ("target_host_isolation_evidence_deferred_s2_5",)
EXPECTED_CAVEATS = {
    CANDIDATE_OCI: list(OCI_CAVEATS),
    CANDIDATE_FIXED_PATH: list(FIXED_PATH_CAVEATS),
}

# initdb-gated disposable PG identity seam 觀察到的真實拒絕 SQLSTATE(S1.1 SET ROLE→42501)。
PG_IDENTITY_SQLSTATE = "42501"
# disposable_pg_identity seam 必須綁定的 42501 證據(規範二鍵形狀);validator 用其 canonical
# digest 核對 seam 非空宣稱(把 builder 的 _validate_pg_identity_evidence 檢查 port 進 validator)。
PG_IDENTITY_EVIDENCE = {"observed_sqlstate": PG_IDENTITY_SQLSTATE, "verdict": "DENIED"}

# 對序列化 receipt 的機密掃描,沿用 S1.1/S1.4/S1.5 風格。choice receipt 全為 digest/label。
SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"pgpassword|private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|postgres(?:ql)?://[^\s:/@]+:[^\s:/@]+@",
    re.IGNORECASE,
)
SECRET_PATTERNS_CHECKED = (
    "auth_scheme_token",
    "credential_assignment",
    "github_token",
    "postgres_dsn_credentials",
)

RECEIPT_FIELDS = frozenset({
    "schema_version",
    "harness_id",
    "status",
    "caller",
    "target_class",
    "platform",
    "probe_scope",
    "candidate_probes",
    "selection",
    "unselected_path_removal",
    "production_running_attested",
    "dependency_receipts",
    "boundary",
    "supersedes_comparison_null",
    "source_sha256",
    "schema_sha256",
    "secret_scan",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "failure_reason",
    "self_digest",
})

# §9 的 12 個 bypass-negative 種類;PASS 交付需十二者全部真觸拒。
BYPASS_KINDS = (
    "target_host_running_attestation_claimed",
    "oci_selected_without_target_host_probe",
    "oci_selected_without_all_seams_passing",
    "selection_without_both_candidates_probed",
    "deferred_seam_claimed_disposably_proven",
    "disposable_probe_not_exact_restoration",
    "applier_is_sole_verifier",
    "production_or_target_host_target_on_mac",
    "comparison_final_choice_mutated",
    "unselected_path_not_foreclosed",
    "matrix_digest_tamper",
    "plaintext_secret_ingress",
)
BYPASS_KIND_SET = frozenset(BYPASS_KINDS)

# 拋棄佈署根的內容定址 bundle 素材(每候選略異,證明兩候選非同一位元組)。
_UNIT_TEXT = b"[Unit]\nDescription=aiml learning runtime (disposable probe)\n[Service]\nExecStart=/opt/aiml/runtime/bin/python3 -I -m aiml_runtime\n"


class RuntimeChoiceProbeError(RuntimeError):
    """Base for a would-be choice receipt that cannot be safely emitted (fail-closed)."""


class SecretLeakageError(RuntimeChoiceProbeError):
    """Raised when a would-be receipt field carries secret-like content."""


class TargetHostRejectedError(RuntimeChoiceProbeError):
    """Raised when a production/target_host target reaches the Mac disposable gate."""


class DeferredSeamClaimError(RuntimeChoiceProbeError):
    """Raised when a target-host-deferred seam is claimed disposably-proven.

    離線/本機不可能證明任何 target-host seam(cgroup / kernel network-denial /
    native-lib loading / true start / target-host PG identity / networked ML closure)。
    若候選的 ``disposable_seams_proven`` 夾帶其中任一 → 結構完整性破壞,raise 不序列化。
    """


class RuntimeChoiceRuleError(RuntimeChoiceProbeError):
    """Raised when the machine-encoded selection rule would be violated at build time."""


# --------------------------------------------------------------------------- #
# canonical digest helpers (mirror S1.4/S1.5)
# --------------------------------------------------------------------------- #
def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _canonical_digest(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


@lru_cache(maxsize=1)
def _pg_identity_evidence_digest() -> str:
    """規範 42501 disposable PG-identity 證據的 canonical digest。

    此值為常量(規範證據形狀固定),故 standalone validator 可從 receipt bytes 重算並核對:
    任何宣稱 ``disposable_pg_identity`` 已 DISPOSABLE_PROVEN 的 seam,必攜帶 == 此 digest 的
    ``evidence_digest``,否則視為無 42501 背書而拒(port 自 builder ``_validate_pg_identity_evidence``)。
    """

    return _canonical_digest(PG_IDENTITY_EVIDENCE)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


@lru_cache(maxsize=1)
def _receipt_schema() -> dict[str, Any]:
    return json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this harness module source."""

    return _file_sha256(SOURCE_PATH)


@lru_cache(maxsize=1)
def receipt_schema_sha256() -> str:
    """Return the sha256 identity of the choice-receipt schema file."""

    return _file_sha256(RECEIPT_SCHEMA_PATH)


def receipt_digest(receipt: dict[str, Any]) -> str:
    """Hash every receipt field except the self-digest."""

    unsigned = {key: value for key, value in receipt.items() if key != "self_digest"}
    return _canonical_digest(unsigned)


# --------------------------------------------------------------------------- #
# secret scan (fail-closed, mirror S1.1/S1.4/S1.5)
# --------------------------------------------------------------------------- #
def _contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return SECRET_LIKE_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_secret_like(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_secret_like(key) or _contains_secret_like(item)
            for key, item in value.items()
        )
    return False


def _guard_no_secret(payload: Any) -> None:
    if _contains_secret_like(payload):
        raise SecretLeakageError("choice receipt payload carries secret-like content")


# --------------------------------------------------------------------------- #
# platform detection (reuse S1.4 shape + the target-host-runtime const-false flag)
# --------------------------------------------------------------------------- #
def detect_platform() -> dict[str, Any]:
    """Pin the Mac reality (reuse S1.4 ``detect_platform``) + target-host-runtime const false.

    ``target_host_container_runtime_available`` is const ``false``: Mac cannot reach a
    Linux target-host container runtime (no cross-arch load, no owned target slice).
    """

    base = spike.detect_platform()
    return {
        "os": base["os"],
        "arch": base["arch"],
        "python_version": base["python_version"],
        "container_runtime": base["container_runtime"],
        "container_runtime_available": base["container_runtime_available"],
        "buildx_available": base["buildx_available"],
        "target_host_container_runtime_available": False,
    }


# --------------------------------------------------------------------------- #
# per-candidate disposable bundle material (content-addressed; differs per candidate)
# --------------------------------------------------------------------------- #
def _prior_bundle(candidate_id: str) -> dict[str, bytes]:
    return {
        "bin/launch_contract.txt": (
            b"# absolute-pinned launch (no PATH lookup, no /usr/bin/python3 fallback)\n"
            b"exec ${BUNDLE}/bin/python3 -I -m aiml_runtime\n"
        ),
        "manifest.json": (
            b'{"candidate":"' + candidate_id.encode("ascii") + b'","generation":0}\n'
        ),
    }


def _new_bundle(candidate_id: str) -> dict[str, bytes]:
    return {
        "bin/launch_contract.txt": (
            b"# absolute-pinned launch (no PATH lookup, no /usr/bin/python3 fallback)\n"
            b"exec ${BUNDLE}/bin/python3 -I -m aiml_runtime\n"
        ),
        "manifest.json": (
            b'{"candidate":"' + candidate_id.encode("ascii") + b'","generation":1}\n'
        ),
    }


def _interrupted_bundle(candidate_id: str) -> dict[str, bytes]:
    return {
        "bin/launch_contract.txt": b"# interrupted staging; pointer must never swap\n",
        "manifest.json": (
            b'{"candidate":"' + candidate_id.encode("ascii") + b'","generation":"interrupted"}\n'
        ),
    }


def _candidate_intent_fields(candidate_id: str, dependency_manifest_digest: str) -> dict[str, Any]:
    """Bind the exact LEARNING_RUNTIME matrix key-set with candidate-representative values.

    這正是 §2 記錄 OCI-socket 疑慮之處:OCI 候選的 isolation-surface 為 LR2 禁止的
    OCI/DBus socket surface;fixed-path 候選無 socket surface(絕對釘住啟動)。key-set
    與矩陣 ``required_intent_fields`` 完全一致(S1.5 validator 逐鍵核對)。
    """

    if candidate_id == CANDIDATE_OCI:
        runtime_identity = "exact_image_id:content_addressed_standin_on_mac"
        surface = "oci_socket_dbus_surface_lr2_forbids"
    else:
        runtime_identity = "content_addressed_path:native_shape"
        surface = "no_socket_surface_absolute_pinned_launch"
    return {
        "runtime_identity": runtime_identity,
        "dependency_manifest_digest": dependency_manifest_digest,
        "mount_network_socket_secret_surface": surface,
        "exact_rollback": "atomic_pointer_swap_to_prior_content_hash",
    }


def _seam_record(seam_id: str, evidence_class: str, *, evidence_digest: str | None = None) -> dict[str, Any]:
    if evidence_class not in EVIDENCE_CLASSES:
        raise RuntimeChoiceProbeError(f"invalid seam evidence_class: {evidence_class!r}")
    record: dict[str, Any] = {"seam_id": seam_id, "verdict": VERDICT_DISPOSABLE, "evidence_class": evidence_class}
    if evidence_digest is not None:
        # 目前僅 disposable_pg_identity seam 攜帶:綁定其 42501 證據的 canonical digest。
        record["evidence_digest"] = evidence_digest
    return record


def _teardown_and_confirm(deploy_root: str, cleanup_verifier_node: str) -> bool:
    """真實拆除拋棄式佈署根,並由與 applier 相異的 cleanup verifier 確認 path 已不存在。

    在 postcheck 讀取 deploy root 之後才呼叫(complete_cleanup 的實證,而非空宣稱):先 ``rmtree``
    真正刪除,再確認 deploy root 已消失。未消失即結構完整性破壞 → raise(fail-closed);故只有
    確認拆除後,complete_cleanup seam 才會被標為 DISPOSABLE_PROVEN。
    """

    shutil.rmtree(deploy_root, ignore_errors=False)
    if Path(deploy_root).exists():
        raise RuntimeChoiceProbeError(
            f"complete_cleanup seam violated: deploy root still present after teardown by {cleanup_verifier_node}"
        )
    return True


def _deferred_seam_records() -> list[dict[str, Any]]:
    return [{"seam_id": seam_id, "verdict": VERDICT_DEFERRED} for seam_id in TARGET_HOST_DEFERRED_SEAMS]


# --------------------------------------------------------------------------- #
# the isolated disposable runtime probe (per candidate, reusing S1.5's lifecycle)
# --------------------------------------------------------------------------- #
def probe_candidate(
    candidate_id: str,
    deploy_root: str,
    *,
    started_at: str,
    completed_at: str,
    observed_at: str,
    pg_identity_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run ONE S1.5 ``LEARNING_RUNTIME`` disposable lifecycle as the probe for a candidate.

    Maps the plan's probe verbs onto the content-addressed generation transitions on a
    fresh throwaway ``0o700`` deploy root (caller owns teardown):

    * ``artifact_deploy_root_init`` → pre-state digest (the installed prior runtime);
    * FAILURE-RECOVERY = ``artifact_apply_interrupted`` → the pointer NEVER swaps, so the
      prior generation stays active (interrupted digest MUST equal pre);
    * START = ``artifact_apply`` → atomic pointer swap → applied digest (MUST differ from pre);
    * STOP/ROLLBACK = ``artifact_rollback`` → atomic swap back → post digest (MUST equal pre);
    * an INDEPENDENT distinct verifier re-derives the post digest.

    Hand-codes NO apply/rollback/postcheck — it delegates entirely to the S1.5 module.
    Returns the receipt's ``candidate_probes`` block.  ``pg_identity_evidence`` (from the
    ``initdb``-gated S1.1 probe) adds the ``disposable_pg_identity`` seam; when ``None`` the
    seam is honestly skipped (never a false PASS).  A target-host seam can never be claimed
    disposably-proven here.
    """

    if candidate_id not in CANDIDATE_IDS:
        raise RuntimeChoiceProbeError(f"candidate_id is not recognized: {candidate_id!r}")

    apply_actor = f"runtime_choice_{candidate_id}_apply_actor"
    verifier = f"runtime_choice_{candidate_id}_ops_verifier"
    cleanup_verifier = f"runtime_choice_{candidate_id}_cleanup_verifier"

    # --- 真實 S1.5 disposable lifecycle(全為 read-only 委派,無自寫 apply/rollback)---
    prior = ce.artifact_deploy_root_init(
        deploy_root, prior_bundle_files=_prior_bundle(candidate_id), unit_text=_UNIT_TEXT
    )
    pre = ce.artifact_state_digest(deploy_root)

    # FAILURE-RECOVERY:中斷式 apply 只 stage、絕不 swap 指標 → 先前世代仍 active。
    interrupted_digest = ce.artifact_apply_interrupted(
        deploy_root, new_bundle_files=_interrupted_bundle(candidate_id)
    )
    if interrupted_digest != pre:
        raise RuntimeChoiceProbeError(
            "failure-recovery seam violated: an interrupted apply changed the active generation"
        )

    # START:apply 新 bundle,原子 swap 指標 → active 世代改變(applied != pre)。
    _new_hash, applied = ce.artifact_apply(deploy_root, new_bundle_files=_new_bundle(candidate_id))
    if applied == pre:
        raise RuntimeChoiceProbeError(
            "start seam violated: the apply did not change the active generation"
        )

    # STOP/ROLLBACK:swap 回先前內容 hash → 精確還原(post == pre)。
    post = ce.artifact_rollback(deploy_root, prior_hash=prior)

    intent = ce.build_component_effect_intent(
        effect_class="LEARNING_RUNTIME",
        target_class="disposable_local",
        pre_state_digest=pre,
        apply_actor_node=apply_actor,
        independent_postcheck_node=verifier,
        approved_by="operator:s1.6",
        approved_at=started_at,
        ttl_seconds=600,
        intent_id=f"runtime-choice-probe-{candidate_id}",
        intent_fields=_candidate_intent_fields(candidate_id, ce.canonical_digest({"closure": pre})),
    )
    # exact restoration(pre==post)、applied!=pre 由 S1.5 result builder 機器強制(否則 raise)。
    result = ce.build_component_effect_result(
        intent=intent,
        apply_status="APPLIED_ROLLED_BACK_EXACT",
        pre_state_digest=pre,
        applied_digest=applied,
        post_rollback_digest=post,
        apply_actor_node=apply_actor,
        applied_observed=True,
        observation_window_stable=True,
        runtime_witness_kind="real_filesystem_atomic_swap",
        observed_sqlstate=None,
        evidence_class="LOCAL_REPRODUCIBLE",
        started_at=started_at,
        completed_at=completed_at,
    )
    # INDEPENDENT postcheck:distinct verifier 重算 post digest(applier!=verifier 由 S1.5 強制)。
    reobserved = ce.artifact_state_digest(deploy_root)
    attestation = ce.build_postcheck_attestation(
        result=result,
        verifier_node=verifier,
        reobserved_post_rollback_digest=reobserved,
        restoration_confirmed=(reobserved == post),
        evidence_class="LOCAL_REPRODUCIBLE",
        observed_at=observed_at,
    )

    # COMPLETE CLEANUP:postcheck(上面已讀過 deploy root)之後,才真實拆除拋棄式佈署根並確認消失。
    # complete_cleanup seam 因此有真實 teardown 背書;未確認消失即 raise,seam 永不空宣稱(E2 P2)。
    cleanup_confirmed = _teardown_and_confirm(deploy_root, cleanup_verifier)

    disposable_seams = [
        _seam_record(seam_id, "LOCAL_REPRODUCIBLE")
        for seam_id in CORE_DISPOSABLE_SEAMS
        if seam_id != "complete_cleanup" or cleanup_confirmed
    ]
    if pg_identity_evidence is not None:
        _validate_pg_identity_evidence(pg_identity_evidence)
        # 綁定 42501 證據 canonical digest,validator 據此核對 seam 有 42501 背書(非空宣稱)。
        disposable_seams.append(
            _seam_record(PG_IDENTITY_SEAM, "LOCAL_REPRODUCIBLE", evidence_digest=_pg_identity_evidence_digest())
        )

    block = {
        "candidate_id": candidate_id,
        "runtime_identity_kind": "exact_image_id" if candidate_id == CANDIDATE_OCI else "content_addressed_path",
        "lifecycle_result_digest": result["result_digest"],
        "postcheck_attestation_digest": attestation["attestation_digest"],
        "apply_actor_node": apply_actor,
        "postcheck_verifier_node": verifier,
        "pre_state_digest": pre,
        # applied_digest:真實 apply 後 active 世代 digest(!= pre);validator 用其擋掉空跑 lifecycle。
        "applied_digest": applied,
        "post_rollback_digest": post,
        "representativeness": REPRESENTATIVENESS_STANDIN if candidate_id == CANDIDATE_OCI else REPRESENTATIVENESS_NATIVE,
        "disposable_seams_proven": disposable_seams,
        "target_host_deferred_seams": _deferred_seam_records(),
        "caveats": list(EXPECTED_CAVEATS[candidate_id]),
        "evidence_class": "LOCAL_REPRODUCIBLE",
    }
    # 完整性守衛:disposable_seams_proven 絕不得夾帶任何 target-host-deferred seam。
    _assert_no_deferred_in_proven(block)
    return block


def _validate_pg_identity_evidence(evidence: dict[str, Any]) -> None:
    # initdb-gated disposable PG identity 證據:必為真實觀察到的 42501(SET ROLE 提權被拒)。
    if not isinstance(evidence, dict):
        raise RuntimeChoiceProbeError("pg_identity_evidence must be an object")
    if evidence.get("observed_sqlstate") != PG_IDENTITY_SQLSTATE:
        raise RuntimeChoiceProbeError(
            f"disposable PG-identity seam requires an observed {PG_IDENTITY_SQLSTATE} denial"
        )
    if evidence.get("verdict") != "DENIED":
        raise RuntimeChoiceProbeError("disposable PG-identity evidence must record a DENIED verdict")


def _assert_no_deferred_in_proven(candidate_block: dict[str, Any]) -> None:
    proven = candidate_block.get("disposable_seams_proven") or []
    for seam in proven:
        seam_id = seam.get("seam_id") if isinstance(seam, dict) else None
        if seam_id in TARGET_HOST_DEFERRED_SEAM_SET:
            raise DeferredSeamClaimError(
                f"target-host-deferred seam {seam_id!r} cannot be claimed DISPOSABLE_PROVEN"
            )


# --------------------------------------------------------------------------- #
# the machine-encoded selection rule (§5.1)
# --------------------------------------------------------------------------- #
def _oci_target_host_seams_all_passed(oci_block: dict[str, Any]) -> bool:
    """Whether EVERY OCI target-host seam passed (never true in v1: seams are const DEFERRED).

    這是 §5.1 規則的「all OCI seams pass」項。v1 schema 對 deferred seam 的 verdict 釘死
    ``DEFERRED_TARGET_HOST``(無 ``PASSED_TARGET_HOST`` 常量),故本函式恆為 ``False``——
    OCI 於本 receipt 版結構上不可選,只有未來真實 Linux target-host 探針(另一版)才可能翻轉。
    """

    seams = oci_block.get("target_host_deferred_seams") or []
    if not seams:
        return False
    return all(isinstance(seam, dict) and seam.get("verdict") == SEAM_VERDICT_PASSED for seam in seams)


def _derive_oci_selectable(target_host_probe_performed: bool, oci_block: dict[str, Any]) -> bool:
    # 規則:oci_selectable == (target_host_probe_performed AND 每個 OCI target-host seam 皆 passed)。
    return bool(target_host_probe_performed) and _oci_target_host_seams_all_passed(oci_block)


# --------------------------------------------------------------------------- #
# choice receipt builder (honest-by-construction; unsafe states raise)
# --------------------------------------------------------------------------- #
def build_learning_runtime_choice_receipt(
    *,
    caller: str,
    platform: dict[str, Any],
    target_class: str,
    candidate_probes: list[dict[str, Any]],
    runtime_candidate_receipt_a: dict[str, Any],
    runtime_candidate_receipt_b: dict[str, Any],
    runtime_candidate_comparison: dict[str, Any],
    effect_seams_ready_receipt_digest: str,
    pg_readonly_identity_receipt_digest: str,
    observation_time: str,
    ttl_seconds: int,
    binding: str = BINDING_BINDING,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``learning_runtime_choice_receipt_v1``.

    The choice is honest-by-construction: ``final_choice`` is derived from the
    machine-encoded rule, never a free parameter.  Unsafe states RAISE (never emit):
    a ``production``/``target_host`` target on Mac, fewer than both candidates probed,
    a target-host seam claimed disposably-proven, a non-exact candidate restoration, an
    applier==verifier candidate, a mutated (non-null) S1.4 comparison, a matrix-digest
    mismatch, or a secret in any serialized field.  ``status="PASS"`` iff both candidates
    are probed with exact restoration + distinct verifier and the rule + boundary consts hold.
    """

    if not isinstance(caller, str) or not caller:
        raise RuntimeChoiceProbeError("caller is required")
    if target_class in REJECTED_MAC_TARGET_CLASSES:
        # production/target_host 屬 S2.x;Mac disposable gate fail-closed raise。
        raise TargetHostRejectedError(
            "S1.6 Mac deliverable is disposable_local only; production/target_host is rejected fail-closed"
        )
    if target_class != MAC_TARGET_CLASS:
        raise RuntimeChoiceProbeError(f"unrecognized target_class: {target_class!r}")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise RuntimeChoiceProbeError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise RuntimeChoiceProbeError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    if binding not in {BINDING_BINDING, BINDING_PROVISIONAL}:
        raise RuntimeChoiceProbeError(f"unrecognized binding: {binding!r}")

    platform_block = _validate_platform(platform)

    # --- 綁定 S1.4 依賴 BY DIGEST 並保護 comparison 的 const-null(§7.1)---
    a_errors = spike.validate_runtime_candidate_receipt(runtime_candidate_receipt_a)
    b_errors = spike.validate_runtime_candidate_receipt(runtime_candidate_receipt_b)
    if a_errors:
        raise RuntimeChoiceProbeError(f"S1.4 candidate A receipt is invalid: {a_errors[:3]}")
    if b_errors:
        raise RuntimeChoiceProbeError(f"S1.4 candidate B receipt is invalid: {b_errors[:3]}")
    if runtime_candidate_receipt_a.get("candidate", {}).get("id") != CANDIDATE_OCI:
        raise RuntimeChoiceProbeError("runtime_candidate_receipt_a must be the exact_image_id_oci candidate")
    if runtime_candidate_receipt_b.get("candidate", {}).get("id") != CANDIDATE_FIXED_PATH:
        raise RuntimeChoiceProbeError("runtime_candidate_receipt_b must be the content_addressed_fixed_path candidate")
    comparison_errors = spike.validate_runtime_candidate_comparison(
        runtime_candidate_comparison,
        receipt_a=runtime_candidate_receipt_a,
        receipt_b=runtime_candidate_receipt_b,
    )
    if comparison_errors:
        raise RuntimeChoiceProbeError(f"S1.4 comparison is invalid: {comparison_errors[:3]}")
    if runtime_candidate_comparison.get("final_choice") is not None:
        # 保護 §7.1 邊界:被綁定的 comparison 其 final_choice 必為 null(S1.4 不做選擇)。
        raise RuntimeChoiceProbeError(
            "the bound S1.4 comparison.final_choice must be null (S1.6 supersedes by binding, never by editing)"
        )
    for digest in (effect_seams_ready_receipt_digest, pg_readonly_identity_receipt_digest):
        if not DIGEST_RE.fullmatch(str(digest)):
            raise RuntimeChoiceProbeError("dependency receipt digests must be sha256 digests")

    # --- 校驗兩候選探針區塊(封閉集 + 精確還原 + distinct verifier + 無 deferred 走私)---
    normalized_probes = _normalize_candidate_probes(candidate_probes)
    probe_by_id = {block["candidate_id"]: block for block in normalized_probes}
    oci_block = probe_by_id.get(CANDIDATE_OCI)

    target_host_probe_performed = False  # Mac 交付面:誠實 false(無真實 target-host 探針)。
    oci_selectable = _derive_oci_selectable(target_host_probe_performed, oci_block or {})
    # 規則後果:oci 不可選 → 只能回退 fixed-path。final_choice 由規則導出,非自由參數。
    final_choice = FINAL_CHOICE_OCI if oci_selectable else FINAL_CHOICE_FIXED_PATH
    if final_choice != FINAL_CHOICE_FIXED_PATH:
        # 防禦:Mac 面 oci_selectable 恆 false;若走到這裡代表規則被破壞,fail-closed。
        raise RuntimeChoiceRuleError("Mac deliverable must resolve to content_addressed_fixed_path")

    reasons: list[str] = []
    ids = set(probe_by_id)
    if ids != CANDIDATE_IDS or len(normalized_probes) != 2:
        reasons.append(f"both candidates must be probed exactly once (saw {sorted(ids)})")
    if any(block["evidence_class"] != "LOCAL_REPRODUCIBLE" for block in normalized_probes):
        reasons.append("each candidate probe must be LOCAL_REPRODUCIBLE (the disposable lifecycle really ran)")

    status = "PASS" if not reasons else "FAIL"
    failure_reason = None if status == "PASS" else "; ".join(reasons)

    observed = _parse_time(observation_time)
    expires = observed + timedelta(seconds=ttl_seconds)

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "harness_id": HARNESS_ID,
        "status": status,
        "caller": caller,
        "target_class": MAC_TARGET_CLASS,
        "platform": platform_block,
        "probe_scope": {
            "effect_class": PROBE_EFFECT_CLASS,
            "disposable_probe_performed": True,
            "target_host_probe_performed": target_host_probe_performed,
            "target_host_deferred_to": TARGET_HOST_DEFERRED_TO,
        },
        "candidate_probes": normalized_probes,
        "selection": {
            "final_choice": final_choice,
            "selection_rule": SELECTION_RULE,
            "selection_basis": list(SELECTION_BASIS),
            "reason": SELECTION_REASON,
            "binding": binding,
            "oci_selectable": oci_selectable,
        },
        "unselected_path_removal": {
            "unselected_candidate": FINAL_CHOICE_OCI,
            "unselected_production_artifact_present": False,
            "production_path_removed": True,
            "forecloses_downstream": True,
            "note": UNSELECTED_NOTE,
        },
        "production_running_attested": False,
        "dependency_receipts": {
            "runtime_candidate_receipt_a_digest": runtime_candidate_receipt_a["self_digest"],
            "runtime_candidate_receipt_b_digest": runtime_candidate_receipt_b["self_digest"],
            "runtime_candidate_comparison_digest": runtime_candidate_comparison["self_digest"],
            "effect_seams_ready_receipt_digest": effect_seams_ready_receipt_digest,
            "component_effect_matrix_digest": ce.component_effect_matrix_digest(),
            "pg_readonly_identity_receipt_digest": pg_readonly_identity_receipt_digest,
        },
        "boundary": {
            "production_running_attested": False,
            "real_target_host_probe_on_mac": False,
            "real_process_started": False,
            "native_lib_loaded_on_target": False,
            "kernel_isolation_exercised": False,
            "network_contact": False,
            "nine_authorities_false": True,
        },
        "supersedes_comparison_null": True,
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


def _validate_platform(platform: Any) -> dict[str, Any]:
    if (
        not isinstance(platform, dict)
        or platform.get("os") not in PLATFORM_OS
        or not isinstance(platform.get("arch"), str)
        or not platform.get("arch")
        or not isinstance(platform.get("python_version"), str)
        or not platform.get("python_version")
        or not isinstance(platform.get("container_runtime_available"), bool)
        or not isinstance(platform.get("buildx_available"), bool)
    ):
        raise RuntimeChoiceProbeError("platform must bind os/arch/python_version/container flags")
    runtime = platform.get("container_runtime")
    if runtime is not None and (not isinstance(runtime, str) or not runtime):
        raise RuntimeChoiceProbeError("platform.container_runtime must be a non-empty string or null")
    if platform.get("target_host_container_runtime_available") is not False:
        raise RuntimeChoiceProbeError("platform.target_host_container_runtime_available must be false on Mac")
    return {
        "os": platform["os"],
        "arch": platform["arch"],
        "python_version": platform["python_version"],
        "container_runtime": runtime,
        "container_runtime_available": platform["container_runtime_available"],
        "buildx_available": platform["buildx_available"],
        "target_host_container_runtime_available": False,
    }


def _normalize_candidate_probes(candidate_probes: Any) -> list[dict[str, Any]]:
    if not isinstance(candidate_probes, list) or len(candidate_probes) < 2:
        # 沒有兩候選就無從做出綁定選擇(§9-4)→ fail-closed raise。
        raise RuntimeChoiceProbeError("a binding choice requires both candidates probed")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for block in candidate_probes:
        if not isinstance(block, dict):
            raise RuntimeChoiceProbeError("candidate probe block must be an object")
        candidate_id = block.get("candidate_id")
        if candidate_id not in CANDIDATE_IDS:
            raise RuntimeChoiceProbeError(f"candidate probe id is not recognized: {candidate_id!r}")
        if candidate_id in seen:
            raise RuntimeChoiceProbeError(f"duplicate candidate probe: {candidate_id!r}")
        seen.add(candidate_id)
        if block.get("apply_actor_node") == block.get("postcheck_verifier_node"):
            raise ce.ApplierIsSoleVerifierError("a candidate probe applier equals its verifier")
        if block.get("pre_state_digest") != block.get("post_rollback_digest"):
            raise ce.NonExactRollbackError("a candidate probe is not exactly restored (pre != post)")
        if block.get("evidence_class") not in EVIDENCE_CLASSES:
            raise RuntimeChoiceProbeError("candidate probe evidence_class is invalid")
        _assert_no_deferred_in_proven(block)
        normalized.append(block)
    if seen != CANDIDATE_IDS:
        raise RuntimeChoiceProbeError(f"the two candidates must be {sorted(CANDIDATE_IDS)} (saw {sorted(seen)})")
    return normalized


# --------------------------------------------------------------------------- #
# choice receipt validator (structure/integrity + the machine-encoded rule)
# --------------------------------------------------------------------------- #
def validate_learning_runtime_choice_receipt(
    receipt: Any, *, require_success: bool = False, now: str | None = None
) -> list[str]:
    """Validate the choice receipt structure/integrity + every PASS-critical crux.

    Schema subset、exact field-set、const identity、digest regexes、source/schema binding、
    both-candidates-probed(distinct ids)、per-candidate exact restoration + distinct verifier +
    seam closed-set(六 core disposable + 選配 disposable_pg_identity;target-host-deferred 六者
    到齊且皆 DEFERRED_TARGET_HOST;任一 deferred seam 被標 disposably-proven → 拒)、the selection
    rule(``oci_selectable == target_host_probe_performed AND all OCI seams passed``;final_choice
    須為 fixed-path)、const-false boundary、``production_running_attested==false``、
    ``forecloses_downstream==true``、matrix-digest 綁定 live central、``supersedes_comparison_null``、
    secret-free 序列化、TTL/time ordering 與 ``self_digest`` 重算。

    此 validator 不再橡皮圖章 candidate_probes 的標籤,而是把 builder 的保證 port 進來重驗:PASS 探針
    的 ``applied_digest`` 必 != ``pre_state_digest``(擋空跑 lifecycle 認證)、其 ``evidence_class`` 與
    proven seams 必為 ``LOCAL_REPRODUCIBLE``(STRUCTURAL_ONLY 探針不得認證 PASS)、任何
    ``disposable_pg_identity`` proven seam 必攜帶綁定的 42501 ``evidence_digest``。

    ACCEPTANCE CONTRACT(證據誠實,沿 S1.3 消費者契約;CLAUDE.md「self-digest 只證完整性非真確性」):
    一張 ``LOCAL_REPRODUCIBLE`` PASS 的 per-candidate 探針證據(applied/lifecycle_result/postcheck_
    attestation digests + disposable_seams,含 pg 的 42501 evidence_digest)是 **自證摘要**。此 standalone
    validator 只做離線結構/完整性檢查,無法從 receipt bytes 重算 ``lifecycle_result_digest`` /
    ``postcheck_attestation_digest``(其來源 S1.5 result 物件不在 receipt 內),也無法抓取被綁定的 S1.4
    A/B/comparison(只格式檢查其 digest)。把本 receipt 當 S1-exit 探針採信的消費者 **必須** 重跑
    builder 或取得 trusted-host attestation,並以 digest 重抓 S1.4 comparison 重驗 ``final_choice is None``
    ——不得單憑 receipt bytes 認證 PASS(``require_success=True`` 亦然)。
    """

    if not isinstance(receipt, dict):
        return ["learning runtime choice receipt must be an object"]
    schema = _receipt_schema()
    errors = [
        f"learning runtime choice receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != RECEIPT_FIELDS:
        errors.append(
            "learning runtime choice receipt fields mismatch: "
            f"missing={sorted(RECEIPT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - RECEIPT_FIELDS)}"
        )
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        errors.append("learning runtime choice receipt schema_version is invalid")
    if receipt.get("harness_id") != HARNESS_ID:
        errors.append("learning runtime choice receipt harness_id is invalid")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        errors.append("learning runtime choice receipt status is invalid")
    if receipt.get("target_class") != MAC_TARGET_CLASS:
        errors.append("learning runtime choice receipt target_class must be disposable_local on Mac")
    if receipt.get("supersedes_comparison_null") is not True:
        errors.append("learning runtime choice receipt supersedes_comparison_null must be true")
    if receipt.get("production_running_attested") is not False:
        errors.append("learning runtime choice receipt production_running_attested must be false")

    for field_name in ("source_sha256", "schema_sha256", "self_digest"):
        if not DIGEST_RE.fullmatch(str(receipt.get(field_name, ""))):
            errors.append(f"learning runtime choice receipt {field_name} is invalid")
    if receipt.get("source_sha256") != source_sha256():
        errors.append("learning runtime choice receipt source_sha256 does not bind this module")
    if receipt.get("schema_sha256") != receipt_schema_sha256():
        errors.append("learning runtime choice receipt schema_sha256 does not bind the schema")

    errors.extend(_validate_boundary(receipt))
    errors.extend(_validate_candidate_probes(receipt))
    errors.extend(_validate_selection(receipt))
    errors.extend(_validate_unselected_path(receipt))
    errors.extend(_validate_dependency_receipts(receipt))
    errors.extend(_validate_secret_scan(receipt))
    errors.extend(_validate_times(receipt, now=now))

    status = receipt.get("status")
    failure_reason = receipt.get("failure_reason")
    if status == "PASS":
        if failure_reason is not None:
            errors.append("PASS choice receipt cannot carry a failure_reason")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAIL choice receipt requires a non-empty failure_reason")

    if require_success:
        # PASS 採信必須帶 now 才能實證新鮮度:缺 now 時 _validate_times 會跳過新鮮度,一張過期 receipt
        # 就能矇混過 require_success。故 require_success 下強制 now 非空(E3 P3-2 / rec 6)。
        if now is None:
            errors.append("learning runtime choice receipt PASS acceptance requires a non-null now for freshness")
        if status != "PASS":
            errors.append("learning runtime choice receipt does not prove a passing choice")
    if receipt.get("self_digest") != receipt_digest(receipt):
        errors.append("learning runtime choice receipt self_digest does not match canonical receipt")
    return errors


def _validate_boundary(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    boundary = receipt.get("boundary")
    if not isinstance(boundary, dict):
        return ["learning runtime choice receipt boundary is missing"]
    const_false = (
        "production_running_attested",
        "real_target_host_probe_on_mac",
        "real_process_started",
        "native_lib_loaded_on_target",
        "kernel_isolation_exercised",
        "network_contact",
    )
    for flag in const_false:
        if boundary.get(flag) is not False:
            errors.append(f"learning runtime choice receipt boundary.{flag} must be false")
    if boundary.get("nine_authorities_false") is not True:
        errors.append("learning runtime choice receipt boundary.nine_authorities_false must be true")
    scope = receipt.get("probe_scope")
    if not isinstance(scope, dict):
        errors.append("learning runtime choice receipt probe_scope is missing")
    else:
        if scope.get("effect_class") != PROBE_EFFECT_CLASS:
            errors.append("learning runtime choice receipt probe_scope.effect_class is invalid")
        if scope.get("disposable_probe_performed") is not True:
            errors.append("learning runtime choice receipt probe_scope.disposable_probe_performed must be true")
        if scope.get("target_host_deferred_to") != TARGET_HOST_DEFERRED_TO:
            errors.append("learning runtime choice receipt probe_scope.target_host_deferred_to is invalid")
        if not isinstance(scope.get("target_host_probe_performed"), bool):
            errors.append("learning runtime choice receipt probe_scope.target_host_probe_performed must be boolean")
    return errors


def _validate_candidate_probes(receipt: dict[str, Any]) -> list[str]:
    probes = receipt.get("candidate_probes")
    if not isinstance(probes, list) or len(probes) < 2:
        return ["learning runtime choice receipt requires both candidates probed"]
    # PASS 交付要求 candidate_probes 是被實證的探針(非 synthetic 標籤);FAIL 允許降級探針。
    is_pass = receipt.get("status") == "PASS"
    errors: list[str] = []
    seen: list[str] = []
    for block in probes:
        if not isinstance(block, dict):
            errors.append("learning runtime choice candidate probe is invalid")
            continue
        candidate_id = block.get("candidate_id")
        seen.append(candidate_id)
        # 精確還原 + distinct verifier(§5.1 crux)。
        if block.get("pre_state_digest") != block.get("post_rollback_digest"):
            errors.append(f"candidate {candidate_id} is not exactly restored (pre != post)")
        if block.get("apply_actor_node") == block.get("postcheck_verifier_node"):
            errors.append(f"candidate {candidate_id} applier equals its verifier")
        # applied_digest 必為合法 digest;PASS 時必 != pre(port S1.5 no-op 防禦:空跑 lifecycle 不得認證)。
        applied_digest = block.get("applied_digest")
        if not DIGEST_RE.fullmatch(str(applied_digest)):
            errors.append(f"candidate {candidate_id} applied_digest is not a sha256 digest")
        if is_pass and (applied_digest is None or applied_digest == block.get("pre_state_digest")):
            errors.append(
                f"candidate {candidate_id} applied_digest must differ from pre_state_digest for a PASS (no-op lifecycle)"
            )
        # PASS 探針必為 LOCAL_REPRODUCIBLE:STRUCTURAL_ONLY 探針(合約/設計、無 runtime bytes)不得認證 PASS。
        if is_pass and block.get("evidence_class") != "LOCAL_REPRODUCIBLE":
            errors.append(f"candidate {candidate_id} evidence_class must be LOCAL_REPRODUCIBLE for a PASS probe")
        # representativeness 與候選一致(fixed-path=native_shape;OCI=content_addressed_standin)。
        expected_repr = REPRESENTATIVENESS_STANDIN if candidate_id == CANDIDATE_OCI else REPRESENTATIVENESS_NATIVE
        if block.get("representativeness") != expected_repr:
            errors.append(f"candidate {candidate_id} representativeness is not {expected_repr}")
        expected_kind = "exact_image_id" if candidate_id == CANDIDATE_OCI else "content_addressed_path"
        if block.get("runtime_identity_kind") != expected_kind:
            errors.append(f"candidate {candidate_id} runtime_identity_kind is not {expected_kind}")
        errors.extend(_validate_candidate_seams(candidate_id, block, is_pass=is_pass))
        if list(block.get("caveats") or []) != EXPECTED_CAVEATS.get(candidate_id, []):
            errors.append(f"candidate {candidate_id} caveats are not the expected set")
    if set(seen) != CANDIDATE_IDS:
        errors.append(f"learning runtime choice receipt candidates must be {sorted(CANDIDATE_IDS)} (saw {sorted(set(seen))})")
    if len(seen) != len(set(seen)):
        errors.append("learning runtime choice receipt has duplicate candidate probes")
    return errors


def _validate_candidate_seams(candidate_id: Any, block: dict[str, Any], *, is_pass: bool = False) -> list[str]:
    errors: list[str] = []
    proven = block.get("disposable_seams_proven")
    if not isinstance(proven, list) or not proven:
        return [f"candidate {candidate_id} disposable_seams_proven is missing"]
    proven_ids: list[str] = []
    for seam in proven:
        if not isinstance(seam, dict):
            errors.append(f"candidate {candidate_id} disposable seam is invalid")
            continue
        seam_id = seam.get("seam_id")
        proven_ids.append(seam_id)
        if seam.get("verdict") != VERDICT_DISPOSABLE:
            errors.append(f"candidate {candidate_id} disposable seam {seam_id} verdict must be DISPOSABLE_PROVEN")
        if seam.get("evidence_class") not in EVIDENCE_CLASSES:
            errors.append(f"candidate {candidate_id} disposable seam {seam_id} evidence_class is invalid")
        # PASS proven seam 必為 LOCAL_REPRODUCIBLE(有 runtime bytes);STRUCTURAL_ONLY 不得認證 PASS。
        if is_pass and seam.get("evidence_class") != "LOCAL_REPRODUCIBLE":
            errors.append(
                f"candidate {candidate_id} disposable seam {seam_id} evidence_class must be LOCAL_REPRODUCIBLE for a PASS"
            )
        # crux:target-host-deferred seam 絕不得出現於 disposable_seams_proven(S1.4 守衛再施用)。
        if seam_id in TARGET_HOST_DEFERRED_SEAM_SET:
            errors.append(
                f"candidate {candidate_id} seam {seam_id} is a target-host seam claimed DISPOSABLE_PROVEN"
            )
        # crux:任何 disposable_pg_identity proven seam 必攜帶綁定的 42501 evidence_digest,否則視為
        # 無 42501 背書而拒(把 builder 的 _validate_pg_identity_evidence 檢查 port 進 validator)。
        if seam_id == PG_IDENTITY_SEAM and seam.get("evidence_digest") != _pg_identity_evidence_digest():
            errors.append(
                f"candidate {candidate_id} disposable_pg_identity seam must bind the 42501 denial evidence digest"
            )
    missing_core = CORE_DISPOSABLE_SEAM_SET - set(proven_ids)
    if missing_core:
        errors.append(f"candidate {candidate_id} is missing core disposable seams: {sorted(missing_core)}")
    extra = set(proven_ids) - ALLOWED_DISPOSABLE_SEAMS
    if extra:
        errors.append(f"candidate {candidate_id} disposable_seams_proven has unexpected seams: {sorted(extra)}")
    if len(proven_ids) != len(set(proven_ids)):
        errors.append(f"candidate {candidate_id} has duplicate disposable seams")

    deferred = block.get("target_host_deferred_seams")
    if not isinstance(deferred, list):
        errors.append(f"candidate {candidate_id} target_host_deferred_seams is missing")
        return errors
    deferred_ids = []
    for seam in deferred:
        if not isinstance(seam, dict):
            errors.append(f"candidate {candidate_id} deferred seam is invalid")
            continue
        deferred_ids.append(seam.get("seam_id"))
        if seam.get("verdict") != VERDICT_DEFERRED:
            errors.append(f"candidate {candidate_id} deferred seam {seam.get('seam_id')} verdict must be DEFERRED_TARGET_HOST")
    # 六個決定性 target-host seam 必到齊(不得偷偷丟掉一個好把它塞進 proven)。
    if set(deferred_ids) != TARGET_HOST_DEFERRED_SEAM_SET:
        errors.append(
            f"candidate {candidate_id} target_host_deferred_seams must be exactly "
            f"{sorted(TARGET_HOST_DEFERRED_SEAM_SET)}"
        )
    return errors


def _validate_selection(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    selection = receipt.get("selection")
    if not isinstance(selection, dict):
        return ["learning runtime choice receipt selection is missing"]
    if selection.get("selection_rule") != SELECTION_RULE:
        errors.append("learning runtime choice receipt selection_rule is invalid")
    if list(selection.get("selection_basis") or []) != list(SELECTION_BASIS):
        errors.append("learning runtime choice receipt selection_basis is not the exact const set")
    if selection.get("reason") != SELECTION_REASON:
        errors.append("learning runtime choice receipt selection reason is not the const reason")
    if selection.get("binding") not in {BINDING_BINDING, BINDING_PROVISIONAL}:
        errors.append("learning runtime choice receipt selection binding is invalid")
    if selection.get("oci_selectable") is not False:
        errors.append("learning runtime choice receipt oci_selectable must be false on the Mac deliverable")

    # --- 機器強制 §5.1 規則:oci_selectable == target_host_probe_performed AND all OCI seams passed ---
    scope = receipt.get("probe_scope") or {}
    target_host_probe_performed = bool(scope.get("target_host_probe_performed"))
    probes = receipt.get("candidate_probes") if isinstance(receipt.get("candidate_probes"), list) else []
    oci_block = next((b for b in probes if isinstance(b, dict) and b.get("candidate_id") == CANDIDATE_OCI), None)
    derived = _derive_oci_selectable(target_host_probe_performed, oci_block or {})
    if bool(selection.get("oci_selectable")) != derived:
        errors.append(
            "learning runtime choice receipt oci_selectable must equal "
            "(target_host_probe_performed AND every OCI target-host seam passed)"
        )
    final_choice = selection.get("final_choice")
    # OCI 只有在真正可選時才可被選;不可選卻選 OCI(或未回退 fixed-path)→ 拒(§9-2/§9-3)。
    if final_choice == FINAL_CHOICE_OCI and not derived:
        errors.append(
            "learning runtime choice receipt cannot select OCI without a target-host probe passing all seams"
        )
    if not derived and final_choice != FINAL_CHOICE_FIXED_PATH:
        errors.append("learning runtime choice receipt must fall back to content_addressed_fixed_path")
    if final_choice not in {FINAL_CHOICE_FIXED_PATH, FINAL_CHOICE_OCI}:
        errors.append("learning runtime choice receipt final_choice is invalid")
    return errors


def _validate_unselected_path(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    removal = receipt.get("unselected_path_removal")
    if not isinstance(removal, dict):
        return ["learning runtime choice receipt unselected_path_removal is missing"]
    if removal.get("unselected_candidate") != FINAL_CHOICE_OCI:
        errors.append("unselected_path_removal.unselected_candidate must be exact_image_id_oci")
    if removal.get("unselected_production_artifact_present") is not False:
        errors.append("unselected_path_removal.unselected_production_artifact_present must be false")
    if removal.get("production_path_removed") is not True:
        errors.append("unselected_path_removal.production_path_removed must be true")
    if removal.get("forecloses_downstream") is not True:
        # 必須 foreclose OCI 路徑(§9-10):LR2/S2.3 只封存 fixed-path。
        errors.append("unselected_path_removal.forecloses_downstream must be true")
    if not isinstance(removal.get("note"), str) or not removal.get("note").strip():
        errors.append("unselected_path_removal.note must be a non-empty string")
    return errors


def _validate_dependency_receipts(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dependency = receipt.get("dependency_receipts")
    if not isinstance(dependency, dict):
        return ["learning runtime choice receipt dependency_receipts is missing"]
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
            errors.append(f"learning runtime choice dependency {field_name} is invalid")
    # matrix digest 必等於 live central digest(§9-11 tamper 守衛)。
    if dependency.get("component_effect_matrix_digest") != ce.component_effect_matrix_digest():
        errors.append("learning runtime choice dependency component_effect_matrix_digest is not the live central digest")
    return errors


def _validate_secret_scan(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    secret_scan = receipt.get("secret_scan")
    if not isinstance(secret_scan, dict):
        return ["learning runtime choice receipt secret_scan is missing"]
    if secret_scan.get("leaked") is not False:
        errors.append("learning runtime choice receipt secret_scan must report leaked=false")
    if list(secret_scan.get("patterns_checked", [])) != list(SECRET_PATTERNS_CHECKED):
        errors.append("learning runtime choice receipt secret_scan patterns are not the exact contract")
    if _contains_secret_like({k: v for k, v in receipt.items() if k != "secret_scan"}):
        errors.append("learning runtime choice receipt carries secret-like content")
    return errors


def _validate_times(receipt: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    ttl_seconds = receipt.get("ttl_seconds")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        return ["learning runtime choice receipt ttl_seconds is invalid"]
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        errors.append(f"learning runtime choice ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    try:
        observed = _parse_time(str(receipt.get("observation_time", "")))
        expires = _parse_time(str(receipt.get("expires_at", "")))
        if expires != observed + timedelta(seconds=ttl_seconds):
            errors.append("learning runtime choice expires_at does not equal observation_time + ttl")
        if not observed < expires:
            errors.append("learning runtime choice observation_time must precede expires_at")
        if now is not None:
            current = _parse_time(now)
            if not observed <= current < expires:
                errors.append("learning runtime choice receipt is not fresh")
    except (TypeError, ValueError):
        errors.append("learning runtime choice receipt timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# bypass-negatives (fail-closed; each REALLY triggers the rejection, no rubber stamp)
# --------------------------------------------------------------------------- #
def _honest_reference_receipt(now: str, base_dir: str) -> dict[str, Any]:
    """Build a hermetic, structurally-complete honest PASS choice receipt for tampering.

    真跑兩候選 disposable lifecycle(檔案系統)+ 真建 S1.4 A/B receipt(python3 -I 子進程,
    到處可跑)+ comparison;S1.5/S1.1 依賴以 digest 綁定。供反例 deep-copy 竄改。
    """

    started = now
    completed = _plus_seconds(now, 30)
    observed = _plus_seconds(now, 40)
    probes = []
    for index, candidate_id in enumerate((CANDIDATE_OCI, CANDIDATE_FIXED_PATH)):
        root = str(Path(base_dir) / f"probe_{index}_{candidate_id}")
        probes.append(
            probe_candidate(
                candidate_id, root,
                started_at=started, completed_at=completed, observed_at=observed,
            )
        )
    receipt_a, receipt_b, comparison = _hermetic_s14_dependencies(now, base_dir)
    return build_learning_runtime_choice_receipt(
        caller="runtime_choice_probe_v1:reference",
        platform=detect_platform(),
        target_class="disposable_local",
        candidate_probes=probes,
        runtime_candidate_receipt_a=receipt_a,
        runtime_candidate_receipt_b=receipt_b,
        runtime_candidate_comparison=comparison,
        effect_seams_ready_receipt_digest=_canonical_digest({"s1_5": "effect_seams_ready"}),
        pg_readonly_identity_receipt_digest=_canonical_digest({"s1_1": "pg_readonly_identity"}),
        observation_time=now, ttl_seconds=900,
    )


def _hermetic_s14_dependencies(now: str, base_dir: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Build genuine S1.4 A/B candidate receipts + the const-null comparison (hermetic).

    A real ``python3 -I`` subprocess proves isolated mode (runs everywhere); a fixture
    tree gives a real closure hash.  Both are stdlib-only, no docker/network.
    """

    bundle_root = Path(base_dir) / "s14_fixture"
    spike.materialize_fixture_bundle(bundle_root)
    closure_hash, count = spike.hash_bundle_tree(bundle_root)
    inventory = spike.inventory_native_libraries(bundle_root)
    isolation = spike.probe_python_isolated_mode()  # 真跑子進程(非 initdb-gated)
    dependency_closure = {
        "lock_tool": "stdlib_sha256_closure",
        "lock_input_ref": "runtime_candidate_fixture_v1",
        "closure_hash": closure_hash,
        "hashed_input_count": count,
    }
    receipt_a = spike.build_runtime_candidate_receipt(
        caller="runtime_choice_probe_v1:s1.4-a", platform=spike.detect_platform(),
        candidate_id=CANDIDATE_OCI, target_class="disposable_offline",
        dependency_closure=dependency_closure, native_library_inventory=inventory,
        isolation_mode=isolation,
        sealed_input=spike.oci_sealed_input(
            "sha256:" + "b" * 64, spike.OCI_DOCKERFILE_SPEC,
            (bundle_root / "requirements.lock").read_bytes(),
        ),
        observation_time=now, ttl_seconds=3600,
    )
    receipt_b = spike.build_runtime_candidate_receipt(
        caller="runtime_choice_probe_v1:s1.4-b", platform=spike.detect_platform(),
        candidate_id=CANDIDATE_FIXED_PATH, target_class="disposable_offline",
        dependency_closure=dependency_closure, native_library_inventory=inventory,
        isolation_mode=isolation,
        sealed_input=spike.build_sealed_input({
            "closure_hash": closure_hash.encode("utf-8"),
            "requirements_lock": (bundle_root / "requirements.lock").read_bytes(),
            "manifest": (bundle_root / "manifest.json").read_bytes(),
        }),
        observation_time=now, ttl_seconds=3600,
    )
    comparison = spike.build_runtime_candidate_comparison(
        receipt_a, receipt_b, observation_time=now, ttl_seconds=3600
    )
    return receipt_a, receipt_b, comparison


def _plus_seconds(iso: str, seconds: int) -> str:
    return (_parse_time(iso) + timedelta(seconds=seconds)).isoformat()


def _resign(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt = copy.deepcopy(receipt)
    receipt.pop("self_digest", None)
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


def _reject_or_vacuous(receipt: dict[str, Any], *, needle: str, now: str) -> None:
    # 竄改後跑 validator;若被拒(含 needle 的錯誤)→ raise 記 REJECTED;若未被拒 → vacuous 返回。
    errors = validate_learning_runtime_choice_receipt(receipt, now=now)
    matched = [error for error in errors if needle in error]
    if matched:
        raise RuntimeChoiceProbeError("rejected: " + "; ".join(matched[:2]))
    return None


def _bypass_target_host_running_attestation_claimed(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    receipt["boundary"]["production_running_attested"] = True
    receipt["production_running_attested"] = True
    _reject_or_vacuous(_resign(receipt), needle="production_running_attested", now=now)


def _bypass_oci_selected_without_target_host_probe(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    # target_host_probe_performed 仍 false,卻硬選 OCI → 規則拒。
    receipt["selection"]["final_choice"] = FINAL_CHOICE_OCI
    _reject_or_vacuous(_resign(receipt), needle="select OCI", now=now)


def _bypass_oci_selected_without_all_seams_passing(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    # 即使謊稱有 target-host 探針且 oci_selectable=true,deferred seam 仍 DEFERRED(未 passed)→ 規則拒。
    receipt["probe_scope"]["target_host_probe_performed"] = True
    receipt["selection"]["oci_selectable"] = True
    receipt["selection"]["final_choice"] = FINAL_CHOICE_OCI
    _reject_or_vacuous(_resign(receipt), needle="oci_selectable", now=now)


def _bypass_selection_without_both_candidates_probed(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    receipt["candidate_probes"] = receipt["candidate_probes"][:1]  # 只剩一個候選
    _reject_or_vacuous(_resign(receipt), needle="candidate", now=now)


def _bypass_deferred_seam_claimed_disposably_proven(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    # 把一個 target-host-deferred seam 塞進 disposable_seams_proven → 拒。
    receipt["candidate_probes"][0]["disposable_seams_proven"].append(
        {"seam_id": "cgroup_isolation", "verdict": VERDICT_DISPOSABLE, "evidence_class": "LOCAL_REPRODUCIBLE"}
    )
    _reject_or_vacuous(_resign(receipt), needle="target-host seam", now=now)


def _bypass_disposable_probe_not_exact_restoration(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    # pre != post(回滾非精確)→ 拒。
    receipt["candidate_probes"][0]["post_rollback_digest"] = "sha256:" + "0" * 64
    _reject_or_vacuous(_resign(receipt), needle="not exactly restored", now=now)


def _bypass_applier_is_sole_verifier(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    block = receipt["candidate_probes"][0]
    block["postcheck_verifier_node"] = block["apply_actor_node"]  # applier == verifier → 拒
    _reject_or_vacuous(_resign(receipt), needle="applier equals its verifier", now=now)


def _bypass_production_or_target_host_target_on_mac(now: str, base_dir: str) -> None:
    # builder 層 fail-closed:target_host 直接 raise(不發 receipt)。
    receipt_a, receipt_b, comparison = _hermetic_s14_dependencies(now, base_dir)
    probes = _reference_probe_blocks(now, base_dir)
    build_learning_runtime_choice_receipt(
        caller="runtime_choice_probe_v1:neg", platform=detect_platform(),
        target_class="target_host", candidate_probes=probes,
        runtime_candidate_receipt_a=receipt_a, runtime_candidate_receipt_b=receipt_b,
        runtime_candidate_comparison=comparison,
        effect_seams_ready_receipt_digest=_canonical_digest({"s1_5": "x"}),
        pg_readonly_identity_receipt_digest=_canonical_digest({"s1_1": "x"}),
        observation_time=now, ttl_seconds=900,
    )


def _bypass_comparison_final_choice_mutated(now: str, base_dir: str) -> None:
    # 餵入一個被竄改成非 null final_choice 的 comparison → builder 經 spike validator 拒。
    receipt_a, receipt_b, comparison = _hermetic_s14_dependencies(now, base_dir)
    mutated = copy.deepcopy(comparison)
    mutated["final_choice"] = FINAL_CHOICE_FIXED_PATH  # 非 null → 破壞 S1.4 const-null 邊界
    mutated["self_digest"] = spike.comparison_digest(mutated)
    probes = _reference_probe_blocks(now, base_dir)
    build_learning_runtime_choice_receipt(
        caller="runtime_choice_probe_v1:neg", platform=detect_platform(),
        target_class="disposable_local", candidate_probes=probes,
        runtime_candidate_receipt_a=receipt_a, runtime_candidate_receipt_b=receipt_b,
        runtime_candidate_comparison=mutated,
        effect_seams_ready_receipt_digest=_canonical_digest({"s1_5": "x"}),
        pg_readonly_identity_receipt_digest=_canonical_digest({"s1_1": "x"}),
        observation_time=now, ttl_seconds=900,
    )


def _bypass_unselected_path_not_foreclosed(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    receipt["unselected_path_removal"]["forecloses_downstream"] = False  # 未 foreclose OCI 路徑 → 拒
    _reject_or_vacuous(_resign(receipt), needle="forecloses_downstream", now=now)


def _bypass_matrix_digest_tamper(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    receipt["dependency_receipts"]["component_effect_matrix_digest"] = "sha256:" + "0" * 64
    _reject_or_vacuous(_resign(receipt), needle="matrix", now=now)


def _bypass_plaintext_secret_ingress(now: str, base_dir: str) -> None:
    receipt = _honest_reference_receipt(now, base_dir)
    poisoned = copy.deepcopy(receipt)
    poisoned["unselected_path_removal"]["note"] = "authorization=Bearer plaintexthunter2exampletoken"
    _guard_no_secret({k: v for k, v in poisoned.items() if k != "secret_scan"})  # 必 raise


def _reference_probe_blocks(now: str, base_dir: str) -> list[dict[str, Any]]:
    started, completed, observed = now, _plus_seconds(now, 30), _plus_seconds(now, 40)
    blocks = []
    for index, candidate_id in enumerate((CANDIDATE_OCI, CANDIDATE_FIXED_PATH)):
        root = str(Path(base_dir) / f"negprobe_{index}_{candidate_id}")
        blocks.append(
            probe_candidate(
                candidate_id, root,
                started_at=started, completed_at=completed, observed_at=observed,
            )
        )
    return blocks


_BYPASS_RUNNERS: dict[str, Callable[[str, str], None]] = {
    "target_host_running_attestation_claimed": _bypass_target_host_running_attestation_claimed,
    "oci_selected_without_target_host_probe": _bypass_oci_selected_without_target_host_probe,
    "oci_selected_without_all_seams_passing": _bypass_oci_selected_without_all_seams_passing,
    "selection_without_both_candidates_probed": _bypass_selection_without_both_candidates_probed,
    "deferred_seam_claimed_disposably_proven": _bypass_deferred_seam_claimed_disposably_proven,
    "disposable_probe_not_exact_restoration": _bypass_disposable_probe_not_exact_restoration,
    "applier_is_sole_verifier": _bypass_applier_is_sole_verifier,
    "production_or_target_host_target_on_mac": _bypass_production_or_target_host_target_on_mac,
    "comparison_final_choice_mutated": _bypass_comparison_final_choice_mutated,
    "unselected_path_not_foreclosed": _bypass_unselected_path_not_foreclosed,
    "matrix_digest_tamper": _bypass_matrix_digest_tamper,
    "plaintext_secret_ingress": _bypass_plaintext_secret_ingress,
}


def run_bypass_negative(kind: str, *, now: str, base_dir: str) -> dict[str, Any]:
    """Run one §9 bypass-negative; confirm it REALLY fails closed (no rubber stamp).

    If a runner does NOT raise, the case is vacuous and this re-raises
    ``RuntimeChoiceProbeError`` — the receipt must never record a bypass as REJECTED
    when the path did not actually reject.
    """

    runner = _BYPASS_RUNNERS.get(kind)
    if runner is None:
        raise RuntimeChoiceProbeError(f"unknown bypass-negative kind: {kind!r}")
    try:
        runner(now, base_dir)
    except (RuntimeChoiceProbeError, ce.ComponentEffectError, ValueError) as error:
        return {
            "case_id": f"neg-{BYPASS_KINDS.index(kind) + 1:02d}-{kind}",
            "bypass_kind": kind,
            "expected": "FAIL_CLOSED",
            "observed_verdict": "REJECTED",
            "evidence_class": "STRUCTURAL_ONLY",
            "reason": str(error)[:200],
        }
    raise RuntimeChoiceProbeError(f"bypass-negative {kind!r} did not fail closed (vacuous rejection)")


def build_bypass_negative_cases(*, now: str, base_dir: str) -> list[dict[str, Any]]:
    """Run all twelve §9 bypass-negatives and return their REJECTED case records."""

    return [run_bypass_negative(kind, now=now, base_dir=base_dir) for kind in BYPASS_KINDS]

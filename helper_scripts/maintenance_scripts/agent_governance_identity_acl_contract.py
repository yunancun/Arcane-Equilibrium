"""Declarative least-privilege identity/ACL contract Adapter for AIML LR0B (S1.3).

This Adapter owns the *contract side* of the AIML runtime's identity/ACL slice:
the declarative least-privilege topology the runtime will require — per-component
non-root host UIDs, dedicated least-privilege PostgreSQL roles, local-only auth
mapping, private socket-dir ACLs, a credential-rotation lifecycle, and per-change
rollback — plus the crux **negative-ACL** proof that an *over-granting* contract
FAILS closed.  It emits one canonical, self-hashed
``identity_acl_contract_receipt_v1``.

S1.3 is ``DISPOSABLE_ONLY``.  It provisions nothing real: every
``production_*_provisioned`` flag is const ``false``, ``production`` target is
rejected fail-closed, and no real host UID / ``pg_hba`` / credential slot is
mutated (that is S2.0/S2.4).  The PG-role least-privilege / reader-write-denial
(``42501``), credential-rotation old-credential rejection (``28P01``) and
socket-dir mode facets are proven with a *real disposable* PostgreSQL cluster and
real ``chmod``/``stat`` in the companion ``_disposable`` test (LOCAL_REPRODUCIBLE);
the host-UID separation, trust/wide-CIDR rejection and rollback-presence facets
are STRUCTURAL_ONLY here, with the real host mutation honestly DEFERRED to S2.4.

**Evidence-authenticity honesty (CLAUDE §四).**  A ``LOCAL_REPRODUCIBLE`` label on the
receipt bytes alone is a *self-attested summary, not proof of execution*: a canonical
self-digest authenticates integrity only, never who ran what.  The receipt's
``observation_source`` / ``mode_source`` / ``new_credential_connected`` are **advisory
caller-supplied labels** — the builder/validator only refuse the laziest forgery (a bare
``evidence_class`` field flipped without them), but a hermetic caller could still set those
labels without ever running a cluster.  Their authenticity requires the out-of-band
``_disposable`` re-run (a real cluster / ``chmod``/``stat``) or platform attestation.
**Consumer contract:** any S1.5/S2.4 consumer that relies on a ``LOCAL_REPRODUCIBLE``
identity/ACL receipt MUST re-run the disposable proof (or obtain platform attestation); it
may not trust the ``evidence_class`` label alone.

Mirrors ``agent_governance_pg_readonly_identity`` (S1.1) for the
adapter-id / receipt-pair / ``self_digest`` / secret-scan / TTL / schema-binding
conventions and reuses the disposable-cluster *pattern* (not a shared helper).
Like S1.1/S1.4 it self-validates its own receipt and deliberately does NOT
register into the central AIML closure-validator, the S1.2 effect matrix, or the
governance registry/route-compiler; the field names of ``secret_lifecycle`` /
``pg_role_topology`` / ``host_uid_topology`` mirror the S1.2
``CREDENTIAL_ROTATION`` / ``PG_ROLE_ACL_MIGRATION`` / ``CONTROLLER_WORKERS``
intent vocabulary verbatim, so the contract binds to the matrix by construction
(the runtime binding is the S1.5/S2.4 consumer adapter's job).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

from agent_governance_schema import schema_subset_errors


ADAPTER_ID = "identity_acl_contract_adapter_v1"
RECEIPT_SCHEMA_VERSION = "identity_acl_contract_receipt_v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
SCHEMA_PATH = (
    REPO_ROOT
    / "program_code/ml_training/schemas/aiml_gate_receipts"
    / "identity_acl_contract_receipt_v1.schema.json"
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
SQLSTATE_RE = re.compile(r"^[0-9A-Z]{5}$")
_MODE_RE = re.compile(r"^0[0-7]{3}$")

TARGET_CLASSES = frozenset({"disposable_local", "production"})
# S1.3 只接受 disposable_local;production 一律 fail-closed 拒絕(真正 provisioning=S2.0/S2.4)。
S1_TARGET_CLASS = "disposable_local"
EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"})
# host_uid facet 永遠是結構性(真 useradd 需 root→DEFERRED_S2),故其 facet evidence
# 只允許 STRUCTURAL_ONLY / DEFERRED_S2,永不 LOCAL_REPRODUCIBLE。
HOST_UID_EVIDENCE_CLASSES = frozenset({"STRUCTURAL_ONLY", "DEFERRED_S2"})
PLATFORM_OS = frozenset({"darwin", "linux"})

# 元件集=plan §LR3-326 的分組(fit/evaluation 合為單一身分,較細的 fit-vs-evaluation
# 拆分是 Sprint-3 選項,此處對齊 plan 以免 contract-vs-plan 漂移)。
COMPONENTS = ("engine_scanner", "controller", "fit_evaluation", "serving", "deleter")
# controller/workers 依 plan §LR2-311 不得持有 OCI socket 或 DBus authority
# (schema 對所有元件皆 const false,以下集合僅供反例聚焦)。
WORKER_COMPONENTS = frozenset({"controller", "fit_evaluation"})
PRIVILEGE_CLASSES = frozenset({
    "observer_read_only", "scanner_capture_writer", "queue_writer",
    "fit_evaluation_writer", "serving_read_only", "retention_deleter",
})
# 讀者類 privilege_class:絕不可攜帶任何寫入權(no writer-for-reader 不變量)。
READER_PRIVILEGE_CLASSES = frozenset({"observer_read_only", "serving_read_only"})
AUTH_METHODS = frozenset({"pg_hba_ident_local", "pg_hba_scram_local", "authenticated_loopback"})
# S1.3 誠實 disposable 契約永不使用 ident map(有界 ident map 是 S2.4 範疇);ident_map 一律必為 null。
CHANGE_KINDS = frozenset({"host_uid", "pg_role", "auth_mapping", "socket_acl", "secret_slot"})
RECOVERY_KINDS = frozenset({"rollback", "approved_forward_only"})

# host UID least-privilege 能力 ALLOWLIST:僅這些良性能力 token 可出現;任何不在此集合者
# (含 sudo/root/oci-socket/spawn-container/read-all-secrets 等過度授權)一律 fail-closed 拒絕。
LEAST_PRIVILEGE_CAP_ALLOWLIST = frozenset({
    "read_config",
    "connect_pg_socket",
    "write_own_socket_dir",
    "read_own_dataset",
    "write_own_fit",
    "read_registry",
    "delete_own_tombstoned_rows",
})
# 安全輪換順序:先 stage 新密鑰 → alter/activate role 憑證 → 最後 revoke 舊密鑰。
_ROTATION_STAGE_TOKEN = "stage"
_ROTATION_ALTER_TOKENS = ("alter", "activate")
_ROTATION_REVOKE_TOKEN = "revoke"

# 元件→正規 privilege_class 的權威綁定(validator 用以擋偽造 receipt 對某元件 mislabel 權限類)。
CANONICAL_PRIVILEGE_CLASS = {
    "engine_scanner": "scanner_capture_writer",
    "controller": "queue_writer",
    "fit_evaluation": "fit_evaluation_writer",
    "serving": "serving_read_only",
    "deleter": "retention_deleter",
    "observation": "observer_read_only",
}
# pg_role_topology 的正規元件集=五元件 + 重用的 S1.1 觀察身分列(observation)。
PG_ROLE_COMPONENTS = COMPONENTS + ("observation",)
# 元件→正規 host UID label 的權威綁定(checker 與 validator 重建路徑兩路皆用):host uid_label 與
# socket_dir_acl 的 owner_uid_label/group_label 必等於該元件「自身」的正規 UID,擋兩類 free-form
# label 偽造——①單一 owner 橫跨所有元件(跨元件最小權限破壞)、②owner 綁到別元件的 UID。
CANONICAL_UID_LABEL = {
    "engine_scanner": "aiml-engine-scanner",
    "controller": "aiml-controller",
    "fit_evaluation": "aiml-fit-evaluation",
    "serving": "aiml-serving",
    "deleter": "aiml-deleter",
}
# uid_label / socket owner label 不得命名 root/superuser 等特權身分——即使同時宣稱 non_root=true 亦屬
# 自相矛盾,一律拒絕(不讓 free-form label 騎在 non_root 布林值上偷帶 root/特權)。
_PRIVILEGED_IDENTITY_TOKENS = ("root", "superuser", "sudo", "wheel", "admin")

# rotation 見證/socket 見證的 live vs structural 標記(evidence_class=LOCAL_REPRODUCIBLE 必須有 live 見證背書)。
ROTATION_OBSERVATION_SOURCES = frozenset({"live_disposable_pg", "structural_contract"})
SOCKET_MODE_SOURCES = frozenset({"live_chmod_stat", "structural_contract"})
# 唯一可認證輪換的憑證拒絕碼:28P01=invalid_password(missing-role/peer/ident 皆不得充當)。
ROTATION_INVALID_PASSWORD_SQLSTATE = "28P01"

# PG 角色禁用屬性(沿用 S1.1 常量;forbidden_attrs_all_false 即這些全為 false)。
FORBIDDEN_ROLE_ATTRS = (
    "rolsuper", "rolcreaterole", "rolcreatedb", "rolbypassrls", "rolreplication",
)
# 憑證拒絕類 SQLSTATE:28P01=invalid_password、28000=invalid_authorization_specification。
CREDENTIAL_DENIAL_SQLSTATES = frozenset({"28P01", "28000"})
# 讀者寫入拒絕類 SQLSTATE:42501=insufficient_privilege(disposable 真實觀察)。
READER_WRITE_DENIAL_SQLSTATES = frozenset({"42501"})

TTL_CEILING_SECONDS = 3600

# 九項 §8 crux 過度授權種類——其中第 6 列(trust / wide_cidr)是兩個 over_grant_kind,
# 故九個表列=十個 over_grant_kind,PASS receipt 必須十者全部存在且皆 REJECTED。
OVER_GRANT_KINDS = (
    "writer_role_for_reader",
    "shared_uid",
    "root_uid",
    "world_readable_socket",
    "superuser_role",
    "trust_auth_from_anywhere",
    "wide_cidr",
    "missing_rollback",
    "controller_oci_socket_or_dbus",
    "plaintext_secret_ingress",
)
CRUX_OVER_GRANT_KINDS = frozenset(OVER_GRANT_KINDS)
# 每種過度授權的正規拒絕理由(不回放注入的機密,plaintext 反例只記結構性理由)。
CRUX_CASE_REASONS = {
    "writer_role_for_reader": "a reader role carrying a write privilege is rejected",
    "shared_uid": "two components sharing one host UID label is rejected",
    "root_uid": "a component running as a root (uid 0) identity is rejected",
    "world_readable_socket": "a socket dir mode with group/world access (& 0o077 != 0) is rejected",
    "superuser_role": "a PG role with superuser or any forbidden attribute is rejected",
    "trust_auth_from_anywhere": "a non-local-only / trust auth method is rejected",
    "wide_cidr": "a wide / non-local CIDR auth mapping is rejected",
    "missing_rollback": "an identity/ACL change lacking a rollback entry is rejected",
    "controller_oci_socket_or_dbus": "a controller/worker with OCI socket or DBus authority is rejected",
    "plaintext_secret_ingress": "a plaintext secret-like value in the contract is rejected",
}

# 對序列化 receipt 做的機密掃描;沿用 S1.1 的 PG_SECRET_LIKE_RE 風格
# (GitHub token / credential 賦值 / auth header / postgres DSN 憑證形)。
PG_SECRET_LIKE_RE = re.compile(
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
    "adapter_id",
    "status",
    "caller",
    "platform",
    "target_class",
    "evidence_class",
    "host_uid_topology",
    "pg_role_topology",
    "auth_mapping",
    "socket_dir_acl",
    "secret_lifecycle",
    "rollback",
    "negative_acl_cases",
    "source_sha256",
    "schema_sha256",
    "secret_scan",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "failure_reason",
    "self_digest",
})

FACET_KEYS = (
    "host_uid_topology",
    "pg_role_topology",
    "auth_mapping",
    "socket_dir_acl",
    "secret_lifecycle",
    "rollback",
)


class IdentityAclContractError(RuntimeError):
    """Base for a would-be receipt that cannot be safely serialized.

    Fail-closed: the Adapter raises (rather than emit a receipt) whenever
    serializing would fake evidence — a real production-provision claim, a
    non-denial rotation code, or an over-grant that is not actually rejected.
    """


class SecretLeakageError(IdentityAclContractError):
    """Raised when a would-be receipt field carries secret-like content."""


class LeastPrivilegeError(IdentityAclContractError):
    """Raised when an over-grant is not rejected fail-closed.

    Either the honest contract itself over-grants, or a negative-ACL mutation was
    NOT flagged by the least-privilege checker (a vacuous refusal); certifying
    such a contract would be faking the crux deliverable.
    """


# --------------------------------------------------------------------------- #
# canonical digest helpers (mirror agent_governance_pg_readonly_identity.py)
# --------------------------------------------------------------------------- #
def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    """Return the canonical sha256 identity used for pre-state / fingerprints."""

    return _sha256_bytes(_canonical_bytes(value))


def credential_slot_fingerprint(slot_id: str, generation: str) -> str:
    """Return a non-secret rotation fingerprint bound to the slot IDENTITY, not the secret.

    The rotation fingerprints must differ old-vs-new and be safe to serialize, so we
    fingerprint the *non-secret* ``slot_id`` + ``generation`` label (never the raw
    password / secret material).  This is the exact pattern S2.4 must copy: a plain
    sha256 over the raw credential is a rainbow-table hazard, so it is deliberately
    not used here.
    """

    if not isinstance(slot_id, str) or not slot_id:
        raise ValueError("slot_id is required")
    if not isinstance(generation, str) or not generation:
        raise ValueError("generation is required")
    return canonical_digest({"secret_slot": slot_id, "generation": generation})


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


@lru_cache(maxsize=1)
def _receipt_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this Adapter module source."""

    return _file_sha256(SOURCE_PATH)


@lru_cache(maxsize=1)
def schema_sha256() -> str:
    """Return the sha256 identity of the receipt schema file."""

    return _file_sha256(SCHEMA_PATH)


def receipt_digest(receipt: dict[str, Any]) -> str:
    """Hash every receipt field except the self-digest."""

    unsigned = {key: value for key, value in receipt.items() if key != "self_digest"}
    return _sha256_bytes(_canonical_bytes(unsigned))


# --------------------------------------------------------------------------- #
# secret scan (mirror S1.1)
# --------------------------------------------------------------------------- #
def _contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return PG_SECRET_LIKE_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_secret_like(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_secret_like(key) or _contains_secret_like(item)
            for key, item in value.items()
        )
    return False


def _guard_no_secret(payload: Any) -> None:
    # fail-closed:任何機密樣態即拒絕序列化,絕不發出帶密的 receipt/contract。
    if _contains_secret_like(payload):
        raise SecretLeakageError("contract payload carries secret-like content")


def _mode_is_private(mode: Any) -> bool:
    """Return True iff ``mode`` is an octal string with no group/world bits."""

    if not isinstance(mode, str) or not _MODE_RE.fullmatch(mode):
        return False
    return (int(mode, 8) & 0o077) == 0


def _names_privileged_identity(label: Any) -> bool:
    """Return True iff a UID/owner label names a root/superuser/privileged identity.

    A label naming ``root``/``superuser``/``sudo``/``wheel``/``admin`` is refused even
    when the row also claims ``non_root=true`` — a free-form label must not ride on the
    boolean to smuggle a privileged identity past least-privilege.
    """

    if not isinstance(label, str):
        return False
    lowered = label.lower()
    return any(token in lowered for token in _PRIVILEGED_IDENTITY_TOKENS)


# --------------------------------------------------------------------------- #
# the declarative least-privilege topology (§3)
# --------------------------------------------------------------------------- #
# 正規生產安裝路徑僅作為 design data 記錄的 label,絕非 Mac spike 會寫入/建立的路徑
# (可攜性:不硬編 /Users/ncyu 或 /home/ncyu)。
_SOCKET_DIR_LABELS = {
    "engine_scanner": "/opt/aiml/run/engine_scanner",
    "controller": "/opt/aiml/run/controller",
    "fit_evaluation": "/opt/aiml/run/fit_evaluation",
    "serving": "/opt/aiml/run/serving",
    "deleter": "/opt/aiml/run/deleter",
}
# 建構器沿用同一份正規綁定(單一真相來源,避免 builder 與 checker/validator 漂移)。
_UID_LABELS = CANONICAL_UID_LABEL
_ROLE_NAMES = {
    "engine_scanner": "aiml_engine_scanner",
    "controller": "aiml_controller",
    "fit_evaluation": "aiml_fit_evaluation",
    "serving": "aiml_serving",
    "deleter": "aiml_deleter",
}
_PRIVILEGE_CLASS = {
    "engine_scanner": "scanner_capture_writer",
    "controller": "queue_writer",
    "fit_evaluation": "fit_evaluation_writer",
    "serving": "serving_read_only",
    "deleter": "retention_deleter",
}
_LEAST_PRIVILEGE_CAPS = {
    "engine_scanner": ["read_config", "connect_pg_socket"],
    "controller": ["read_config", "connect_pg_socket"],
    "fit_evaluation": ["read_config", "connect_pg_socket"],
    "serving": ["read_config", "connect_pg_socket"],
    "deleter": ["read_config", "connect_pg_socket"],
}


def _default_rejection_proof() -> dict[str, Any]:
    # 結構性(STRUCTURAL_ONLY)版本:記錄契約要求的憑證拒絕碼 28P01,並以 observation_source=
    # structural_contract / new_credential_connected=False 誠實表明此為契約期望而非 live 觀察。
    # disposable 版本經 observe_old_credential_rejection 改綁真實觀察(observation_source=live_disposable_pg)。
    return {
        "attempted": "reconnect_with_superseded_credential",
        "observed_sqlstate": "28P01",
        "verdict": "DENIED",
        "observation_source": "structural_contract",
        "new_credential_connected": False,
    }


def _facet_class(is_local_reproducible: bool) -> str:
    return "LOCAL_REPRODUCIBLE" if is_local_reproducible else "STRUCTURAL_ONLY"


def canonical_identity_acl_contract(
    *,
    old_credential_rejection_proof: dict[str, Any] | None = None,
    old_fingerprint: str | None = None,
    new_fingerprint: str | None = None,
    observed_socket_mode: str | None = None,
    pg_role_write_denial_observed: bool = False,
) -> dict[str, Any]:
    """Return the §3 declarative least-privilege identity/ACL topology (honest).

    The pg_role / socket / secret facet ``evidence_class`` is derived from the
    **more-specific advisory labels** ``observation_source`` / ``mode_source`` (a live
    rotation proof ``observation_source==live_disposable_pg`` from
    ``observe_old_credential_rejection``, a real ``chmod``/``stat`` socket mode via
    ``observed_socket_mode``, and an observed reader write-denial
    ``pg_role_write_denial_observed``) — **not** from a bare per-facet ``evidence_class``
    field.  That defeats the laziest forgery (flipping ``evidence_class`` alone), but those
    source labels are themselves **caller-supplied and NOT self-authenticating**: a hermetic
    caller could set ``observation_source==live_disposable_pg`` on receipt bytes it never
    actually observed.  Genuine ``LOCAL_REPRODUCIBLE`` authenticity comes only from the
    companion ``_disposable`` re-run (a real cluster / ``chmod``/``stat``) or platform
    attestation — a self-hashed receipt cannot prove its own execution (CLAUDE §四).  With no
    such label (the hermetic default) every derivable facet is ``STRUCTURAL_ONLY``.  host_uid
    and auth_mapping stay STRUCTURAL_ONLY by design (real ``useradd`` needs root =
    DEFERRED_S2; binding ``0.0.0.0`` live to "prove" the trust negative would be the insecure
    act we refuse).  The returned contract carries NO over-grant.
    """

    rejection = old_credential_rejection_proof or _default_rejection_proof()
    old_fp = old_fingerprint or credential_slot_fingerprint("aiml_pg_credential_slot", "old")
    new_fp = new_fingerprint or credential_slot_fingerprint("aiml_pg_credential_slot", "new")

    rotation_live = rejection.get("observation_source") == "live_disposable_pg"
    socket_live = observed_socket_mode is not None
    # 任一 backable facet 有 live 見證即代表這是一次真實 disposable run(pg_role 的 42501 亦來自同一 run)。
    live_witness_present = rotation_live or socket_live
    pg_role_lr = bool(pg_role_write_denial_observed) and live_witness_present
    socket_mode = observed_socket_mode if socket_live else "0700"
    socket_mode_source = "live_chmod_stat" if socket_live else "structural_contract"
    rotation_source = "live_disposable_pg" if rotation_live else "structural_contract"

    host_uid_topology = [
        {
            "component": component,
            "uid_label": _UID_LABELS[component],
            "non_root": True,
            "oci_socket_access": False,
            "dbus_authority": False,
            "least_privilege_caps": list(_LEAST_PRIVILEGE_CAPS[component]),
            "evidence_class": "STRUCTURAL_ONLY",
            "production_uid_provisioned": False,
        }
        for component in COMPONENTS
    ]

    pg_role_topology = [
        {
            "component": component,
            "role_name": _ROLE_NAMES[component],
            "privilege_class": _PRIVILEGE_CLASS[component],
            "is_superuser": False,
            "forbidden_attrs_all_false": True,
            "is_reader": _PRIVILEGE_CLASS[component] in READER_PRIVILEGE_CLASSES,
            "writer_for_reader": False,
            "evidence_class": _facet_class(pg_role_lr),
            "production_role_provisioned": False,
        }
        for component in COMPONENTS
    ]
    # S1.1 的唯讀觀察身分 aiml_observer_ro 作為本拓撲的一列(reader),原樣重用。
    pg_role_topology.append({
        "component": "observation",
        "role_name": "aiml_observer_ro",
        "privilege_class": "observer_read_only",
        "is_superuser": False,
        "forbidden_attrs_all_false": True,
        "is_reader": True,
        "writer_for_reader": False,
        "evidence_class": _facet_class(pg_role_lr),
        "production_role_provisioned": False,
    })

    auth_mapping = {
        "method": "pg_hba_scram_local",
        "local_only": True,
        "trust_from_anywhere": False,
        "wide_cidr": False,
        "ident_map": None,
        "evidence_class": "STRUCTURAL_ONLY",
        "production_hba_installed": False,
    }

    socket_dir_acl = [
        {
            "component": component,
            "socket_dir_label": _SOCKET_DIR_LABELS[component],
            "mode": socket_mode,
            "mode_source": socket_mode_source,
            "world_readable": False,
            "world_writable": False,
            "owner_uid_label": _UID_LABELS[component],
            "group_label": _UID_LABELS[component],
            "evidence_class": _facet_class(socket_live),
            "production_socket_provisioned": False,
        }
        for component in COMPONENTS
    ]

    secret_lifecycle = {
        "rotation": {
            "secret_slot_target": "aiml_pg_credential_slot",
            "role_target": _ROLE_NAMES["fit_evaluation"],
            "old_fingerprint": old_fp,
            "new_fingerprint": new_fp,
            "rotation_order": ["stage_new_secret", "alter_role_credential", "revoke_old_secret"],
            "old_credential_rejection_proof": {
                "attempted": str(rejection.get("attempted", "")),
                "observed_sqlstate": str(rejection.get("observed_sqlstate", "")),
                "verdict": "DENIED",
                "observation_source": rotation_source,
                "new_credential_connected": bool(rejection.get("new_credential_connected", False)),
            },
        },
        "protected_loading": {
            "no_plaintext_ingress": True,
            "loader_kind": "systemd_credential_load",
        },
        "plaintext_ingress": False,
        "evidence_class": _facet_class(rotation_live),
        "production_credential_rotated": False,
    }

    rollback = [
        {
            "change_id": f"chg-{kind}",
            "change_kind": kind,
            "pre_state_digest": canonical_digest({"change_kind": kind, "pre_state": "baseline"}),
            "rollback_action": action,
            "recovery": "rollback",
        }
        for kind, action in (
            ("host_uid", "delete provisioned component UIDs and restore prior identity generation"),
            ("pg_role", "DROP ROLE the provisioned component roles"),
            ("auth_mapping", "restore prior pg_hba.conf generation and reload"),
            ("socket_acl", "restore prior socket dir mode and owner"),
            ("secret_slot", "restore prior credential slot and revoke the new one"),
        )
    ]

    return {
        "host_uid_topology": host_uid_topology,
        "pg_role_topology": pg_role_topology,
        "auth_mapping": auth_mapping,
        "socket_dir_acl": socket_dir_acl,
        "secret_lifecycle": secret_lifecycle,
        "rollback": rollback,
    }


# --------------------------------------------------------------------------- #
# the crux: least-privilege checker + over-grant negative generator (§8)
# --------------------------------------------------------------------------- #
def _required_change_kinds(contract: dict[str, Any]) -> set[str]:
    # 拓撲各 facet 存在即隱含一項 identity/ACL 變更種類,rollback 必須逐一覆蓋。
    kinds: set[str] = set()
    if contract.get("host_uid_topology"):
        kinds.add("host_uid")
    if contract.get("pg_role_topology"):
        kinds.add("pg_role")
    if contract.get("auth_mapping"):
        kinds.add("auth_mapping")
    if contract.get("socket_dir_acl"):
        kinds.add("socket_acl")
    if contract.get("secret_lifecycle"):
        kinds.add("secret_slot")
    return kinds


def assert_least_privilege_topology(contract: dict[str, Any]) -> list[str]:
    """Return the over-grant errors in ``contract`` (empty iff least-privilege).

    Each error is prefixed with its ``over_grant_kind`` token so a negative case
    can confirm that its specific over-grant was the one rejected.  This is the
    load-bearing checker: the builder runs it on the honest contract (must be
    empty) and on each over-granting mutation (must be non-empty).
    """

    errors: list[str] = []
    host_uids = contract.get("host_uid_topology") or []
    roles = contract.get("pg_role_topology") or []
    auth = contract.get("auth_mapping") or {}
    sockets = contract.get("socket_dir_acl") or []
    secret = contract.get("secret_lifecycle") or {}
    rollback = contract.get("rollback") or []

    # 1. writer_role_for_reader:讀者角色不得攜帶任何寫入權。
    for role in roles:
        is_reader = role.get("is_reader") is True
        reader_class = role.get("privilege_class") in READER_PRIVILEGE_CLASSES
        if (is_reader or reader_class) and role.get("writer_for_reader") is True:
            errors.append(
                f"writer_role_for_reader: reader role {role.get('role_name')!r} carries a write privilege"
            )
        if reader_class and not is_reader:
            errors.append(
                f"writer_role_for_reader: reader-class role {role.get('role_name')!r} is not marked is_reader"
            )

    # 2. shared_uid:每元件 host UID label 必須互異。
    uid_labels = [host.get("uid_label") for host in host_uids]
    if len(set(uid_labels)) != len(uid_labels):
        errors.append("shared_uid: host UID labels are not distinct across components")
    role_names = [role.get("role_name") for role in roles]
    if len(set(role_names)) != len(role_names):
        errors.append("shared_role: PG role names are not distinct across components")

    # 3. root_uid:每元件必為 non-root。
    for host in host_uids:
        if host.get("non_root") is not True:
            errors.append(
                f"root_uid: component {host.get('component')!r} is not a non-root identity"
            )

    # 3b. over_broad_capability:least_privilege_caps 必須逐一屬良性 ALLOWLIST;任何過度授權/
    # 未知能力(sudo/root/oci-socket/spawn-container/read-all-secrets 等)一律 fail-closed 拒絕。
    for host in host_uids:
        caps = host.get("least_privilege_caps")
        if not isinstance(caps, list) or not caps:
            errors.append(
                f"over_broad_capability: component {host.get('component')!r} lacks a bounded capability list"
            )
            continue
        for cap in caps:
            if cap not in LEAST_PRIVILEGE_CAP_ALLOWLIST:
                errors.append(
                    f"over_broad_capability: component {host.get('component')!r} requests "
                    f"non-allowlisted capability {cap!r}"
                )

    # 3c. unsafe_uid_label:host uid_label 必等於該元件自身的正規 UID,且不得命名 root/特權身分——
    # 擋 free-form label 偽造(non_root=true 卻把 uid_label 命名為 root 屬自相矛盾,一律拒絕)。
    for host in host_uids:
        component = host.get("component")
        label = host.get("uid_label")
        if _names_privileged_identity(label):
            errors.append(
                f"unsafe_uid_label: component {component!r} uid_label {label!r} names a root/privileged identity"
            )
        expected_label = CANONICAL_UID_LABEL.get(component)
        if expected_label is not None and label != expected_label:
            errors.append(
                f"unsafe_uid_label: component {component!r} uid_label {label!r} is not its canonical "
                f"host UID {expected_label!r}"
            )

    # 4. world_readable_socket:socket dir 模式必須私有(& 0o077 == 0),不可 world r/w。
    for sock in sockets:
        if not _mode_is_private(sock.get("mode")):
            errors.append(
                f"world_readable_socket: {sock.get('socket_dir_label')!r} mode {sock.get('mode')!r} "
                "is group/world accessible"
            )
        if sock.get("world_readable") is True or sock.get("world_writable") is True:
            errors.append(
                f"world_readable_socket: {sock.get('socket_dir_label')!r} is world readable/writable"
            )

    # 4b. unsafe_socket_owner:每 socket dir 的 owner_uid_label/group_label 必等於其擁有元件的正規
    # host UID,且跨元件互異——擋「單一 owner 橫跨所有元件」(跨元件最小權限破壞)、owner 綁到別元件
    # 的 UID、以及 owner/group 命名 root/特權身分等 free-form owner-label 偽造。
    owner_labels: list[Any] = []
    for sock in sockets:
        component = sock.get("component")
        owner = sock.get("owner_uid_label")
        group = sock.get("group_label")
        owner_labels.append(owner)
        if _names_privileged_identity(owner) or _names_privileged_identity(group):
            errors.append(
                f"unsafe_socket_owner: socket {sock.get('socket_dir_label')!r} owner/group names a "
                "root/privileged identity"
            )
        expected_label = CANONICAL_UID_LABEL.get(component)
        if expected_label is not None:
            if owner != expected_label:
                errors.append(
                    f"unsafe_socket_owner: socket {sock.get('socket_dir_label')!r} owner_uid_label "
                    f"{owner!r} is not the owning component's host UID {expected_label!r}"
                )
            if group != expected_label:
                errors.append(
                    f"unsafe_socket_owner: socket {sock.get('socket_dir_label')!r} group_label "
                    f"{group!r} is not the owning component's host UID {expected_label!r}"
                )
    if len(set(owner_labels)) != len(owner_labels):
        errors.append("unsafe_socket_owner: socket owner labels are not distinct across components")

    # 5. superuser_role:任何角色不得 superuser,禁用屬性須全 false。
    for role in roles:
        if role.get("is_superuser") is True:
            errors.append(f"superuser_role: {role.get('role_name')!r} is a superuser role")
        if role.get("forbidden_attrs_all_false") is not True:
            errors.append(
                f"superuser_role: {role.get('role_name')!r} holds a forbidden role attribute"
            )

    # 6. trust_auth_from_anywhere:方法須為本地 only 的允許集,且非 trust-from-anywhere。
    if auth.get("method") not in AUTH_METHODS:
        errors.append(
            f"trust_auth_from_anywhere: auth method {auth.get('method')!r} is not a local-only method"
        )
    if auth.get("trust_from_anywhere") is True:
        errors.append("trust_auth_from_anywhere: trust auth from anywhere is enabled")

    # 7. wide_cidr:不得綁 wide/非本地 CIDR,必須 local_only。
    if auth.get("wide_cidr") is True:
        errors.append("wide_cidr: a wide / non-local CIDR is bound")
    if auth.get("local_only") is not True:
        errors.append("wide_cidr: auth mapping is not local-only")

    # 7b. unsafe_ident_map:S1.3 徹底移除 ident_map free-form 攻擊面——誠實 disposable 契約永不使用
    # ident map(有界 ident map 是 S2.4 範疇),故任何 non-null ident_map 一律拒絕(schema 亦 const null)。
    if auth.get("ident_map") is not None:
        errors.append(
            "unsafe_ident_map: ident_map must be null at S1.3 (a bounded ident map is S2.4 scope)"
        )

    # 8. missing_rollback:每項隱含變更種類都要有 rollback,且各 entry 具 pre_state+action。
    rollback_kinds = {entry.get("change_kind") for entry in rollback}
    for entry in rollback:
        if not entry.get("pre_state_digest") or not entry.get("rollback_action"):
            errors.append(
                f"missing_rollback: change {entry.get('change_id')!r} lacks a pre_state_digest/rollback_action"
            )
    for kind in sorted(_required_change_kinds(contract)):
        if kind not in rollback_kinds:
            errors.append(f"missing_rollback: change_kind {kind!r} has no rollback entry")

    # 9. controller_oci_socket_or_dbus:任何元件(尤其 controller/workers)不得持 OCI/DBus。
    for host in host_uids:
        if host.get("oci_socket_access") is True:
            errors.append(
                f"controller_oci_socket_or_dbus: component {host.get('component')!r} has OCI socket access"
            )
        if host.get("dbus_authority") is True:
            errors.append(
                f"controller_oci_socket_or_dbus: component {host.get('component')!r} has DBus authority"
            )

    # 10. plaintext_secret_ingress:契約不得含明文機密,protected loading 須 no_plaintext_ingress。
    if secret.get("plaintext_ingress") is True:
        errors.append("plaintext_secret_ingress: secret_lifecycle.plaintext_ingress is enabled")
    protected = secret.get("protected_loading") or {}
    if protected.get("no_plaintext_ingress") is not True:
        errors.append("plaintext_secret_ingress: protected_loading.no_plaintext_ingress is not set")
    if _contains_secret_like(contract):
        errors.append("plaintext_secret_ingress: a plaintext secret-like value is present in the contract")

    # 10b. unsafe_rotation_order:輪換順序必須 stage 新密鑰 → alter/activate → 最後 revoke 舊密鑰;
    # 任何在 stage 前就 revoke 舊密鑰的順序(舊憑證在新憑證生效前即被移除)一律拒絕。
    errors.extend(_rotation_order_errors((secret.get("rotation") or {}).get("rotation_order")))

    return errors


def _rotation_order_errors(order: Any) -> list[str]:
    if not isinstance(order, list) or not order:
        return ["unsafe_rotation_order: rotation_order is missing"]
    tokens = [str(step).lower() for step in order]
    stage_idx = next((i for i, tok in enumerate(tokens) if _ROTATION_STAGE_TOKEN in tok), None)
    revoke_idx = next((i for i, tok in enumerate(tokens) if _ROTATION_REVOKE_TOKEN in tok), None)
    alter_idx = next(
        (i for i, tok in enumerate(tokens) if any(a in tok for a in _ROTATION_ALTER_TOKENS)),
        None,
    )
    if stage_idx is None or revoke_idx is None:
        return ["unsafe_rotation_order: rotation_order must stage a new secret before revoking the old"]
    if revoke_idx < stage_idx:
        return [
            "unsafe_rotation_order: revoke-old precedes stage-new "
            "(the old credential is removed before the new one is active)"
        ]
    # alter/activate 是必需步驟:缺它代表新憑證從未被啟用(僅 stage→revoke 會留下無效憑證)。
    if alter_idx is None:
        return [
            "unsafe_rotation_order: rotation_order lacks an alter/activate step "
            "(the new credential is never activated)"
        ]
    if alter_idx < stage_idx or revoke_idx < alter_idx:
        return [
            "unsafe_rotation_order: alter/activate must occur after stage-new and before revoke-old"
        ]
    return []


def _over_grant_detected(errors: list[str], kind: str) -> bool:
    return any(error.split(":", 1)[0] == kind for error in errors)


def _mut_writer_role_for_reader(contract: dict[str, Any]) -> dict[str, Any]:
    for role in contract["pg_role_topology"]:
        if role["privilege_class"] == "serving_read_only":
            role["writer_for_reader"] = True
    return contract


def _mut_shared_uid(contract: dict[str, Any]) -> dict[str, Any]:
    contract["host_uid_topology"][1]["uid_label"] = contract["host_uid_topology"][0]["uid_label"]
    return contract


def _mut_root_uid(contract: dict[str, Any]) -> dict[str, Any]:
    contract["host_uid_topology"][0]["non_root"] = False
    return contract


def _mut_world_readable_socket(contract: dict[str, Any]) -> dict[str, Any]:
    contract["socket_dir_acl"][0]["mode"] = "0777"
    contract["socket_dir_acl"][0]["world_readable"] = True
    contract["socket_dir_acl"][0]["world_writable"] = True
    return contract


def _mut_superuser_role(contract: dict[str, Any]) -> dict[str, Any]:
    contract["pg_role_topology"][0]["is_superuser"] = True
    return contract


def _mut_trust_auth_from_anywhere(contract: dict[str, Any]) -> dict[str, Any]:
    contract["auth_mapping"]["method"] = "trust"
    contract["auth_mapping"]["trust_from_anywhere"] = True
    return contract


def _mut_wide_cidr(contract: dict[str, Any]) -> dict[str, Any]:
    contract["auth_mapping"]["wide_cidr"] = True
    contract["auth_mapping"]["local_only"] = False
    return contract


def _mut_missing_rollback(contract: dict[str, Any]) -> dict[str, Any]:
    contract["rollback"] = [
        entry for entry in contract["rollback"] if entry["change_kind"] != "pg_role"
    ]
    return contract


def _mut_controller_oci_socket_or_dbus(contract: dict[str, Any]) -> dict[str, Any]:
    for host in contract["host_uid_topology"]:
        if host["component"] == "controller":
            host["oci_socket_access"] = True
    return contract


def _mut_plaintext_secret_ingress(contract: dict[str, Any]) -> dict[str, Any]:
    # 注入明文機密樣態進被丟棄的 mutation(絕不序列化進 receipt),驗證掃描守衛會拒絕。
    contract["secret_lifecycle"]["rotation"]["old_fingerprint"] = "password=plaintexthunter2example"
    return contract


OVER_GRANT_MUTATORS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "writer_role_for_reader": _mut_writer_role_for_reader,
    "shared_uid": _mut_shared_uid,
    "root_uid": _mut_root_uid,
    "world_readable_socket": _mut_world_readable_socket,
    "superuser_role": _mut_superuser_role,
    "trust_auth_from_anywhere": _mut_trust_auth_from_anywhere,
    "wide_cidr": _mut_wide_cidr,
    "missing_rollback": _mut_missing_rollback,
    "controller_oci_socket_or_dbus": _mut_controller_oci_socket_or_dbus,
    "plaintext_secret_ingress": _mut_plaintext_secret_ingress,
}


def build_negative_acl_cases(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Prove each over-grant is rejected by mutating the honest contract.

    For every crux ``over_grant_kind`` this derives an over-granting variant,
    runs ``assert_least_privilege_topology`` and confirms that kind was flagged.
    If any mutation is NOT rejected (a vacuous checker) it RAISES — the receipt
    must never claim an over-grant was rejected when it was not.
    """

    cases: list[dict[str, Any]] = []
    for index, kind in enumerate(OVER_GRANT_KINDS):
        mutated = OVER_GRANT_MUTATORS[kind](copy.deepcopy(contract))
        errors = assert_least_privilege_topology(mutated)
        if not _over_grant_detected(errors, kind):
            raise LeastPrivilegeError(
                f"over-grant {kind!r} was not rejected by the least-privilege checker"
            )
        cases.append({
            "case_id": f"neg-{index + 1:02d}-{kind}",
            "over_grant_kind": kind,
            "expected": "FAIL_CLOSED",
            "observed_verdict": "REJECTED",
            "evidence_class": "STRUCTURAL_ONLY",
            "reason": CRUX_CASE_REASONS[kind],
        })
    return cases


# --------------------------------------------------------------------------- #
# disposable credential-rotation denial observation (live path; §4)
# --------------------------------------------------------------------------- #
def resolve_credential_denial_sqlstate(pgcode: Any, message: Any) -> str | None:
    """Resolve a credential-denial SQLSTATE from a connection failure.

    Prefers a real ``pgcode`` when the driver populates it.  For connection-time
    failures (where psycopg2 leaves ``pgcode`` empty) only the SPECIFIC
    invalid-password evidence — the canonical ``password authentication failed``
    message / an explicit ``28P01`` — maps to ``28P01``.  Generic / peer / ident
    "authentication failed" is deliberately NOT matched (it is not invalid-password
    and must not be misattributed as a rotated-out credential).  Pure/hermetically
    testable.
    """

    if isinstance(pgcode, str) and pgcode in CREDENTIAL_DENIAL_SQLSTATES:
        return pgcode
    text = str(message or "")
    if "28P01" in text or "password authentication failed" in text.lower():
        return "28P01"
    # 明確的 28000 代碼字串(非泛化 "authentication failed" 語句)才回 28000;peer/ident 不匹配。
    if "28000" in text:
        return "28000"
    return None


def observe_old_credential_rejection(
    connect_with_old_credential: Callable[[], Any],
    *,
    connect_with_new_credential: Callable[[], Any],
    attempted: str = "reconnect_with_superseded_credential",
) -> dict[str, Any]:
    """Certify an old-credential rejection ONLY when it is a genuine rotation.

    Soundness contract (moved INTO this reusable function so any S1.5/S2.4 reuse is
    safe by construction): a denial is certifiable as an old-credential rejection
    only if BOTH hold —

    1. the NEW credential connects successfully (same host/db/role), proving the
       infra is valid and the role EXISTS — otherwise the observed denial could be a
       MISSING/dropped role, which over a scram line returns the identical
       ``28P01`` "password authentication failed"; and
    2. the reconnect with the EXACT superseded (old) secret is denied with the
       SPECIFIC invalid-password evidence (``28P01``) — a generic / peer / ident
       "authentication failed" is refused.

    If the new-credential-connects proof is absent (it raises), this refuses to
    certify and RAISES (the denial cannot be attributed to rotation).  If the old
    credential is ACCEPTED, rotation is not fail-closed and this RAISES.
    """

    # (1) 新憑證必須可連——否則觀察到的拒絕可能是 role 缺失/被 drop,而非真正輪換掉的舊憑證。
    try:
        new_connection = connect_with_new_credential()
    except Exception as exc:  # noqa: BLE001 - infra invalid → cannot attribute the denial
        raise LeastPrivilegeError(
            "new credential did not connect; the observed denial cannot be attributed to "
            "rotation (it could be a missing/dropped role or invalid infra)"
        ) from exc
    try:
        new_connection.close()
    except Exception:  # pragma: no cover - best effort  # noqa: BLE001
        pass

    # (2) 舊憑證必須被拒,且是特定 invalid-password(28P01)證據。
    try:
        connection = connect_with_old_credential()
    except Exception as exc:  # noqa: BLE001 - any driver error is the denial
        sqlstate = resolve_credential_denial_sqlstate(getattr(exc, "pgcode", None), str(exc))
        if sqlstate != ROTATION_INVALID_PASSWORD_SQLSTATE:
            raise LeastPrivilegeError(
                "old-credential reconnect failed but not with invalid-password (28P01); a "
                "generic/peer/ident authentication failure does not prove a rotated-out credential"
            ) from exc
        return {
            "attempted": attempted,
            "observed_sqlstate": sqlstate,
            "verdict": "DENIED",
            "observation_source": "live_disposable_pg",
            "new_credential_connected": True,
        }
    try:
        connection.close()
    except Exception:  # pragma: no cover - best effort  # noqa: BLE001
        pass
    raise LeastPrivilegeError("superseded credential was accepted; rotation is not fail-closed")


# --------------------------------------------------------------------------- #
# contract normalization + evidence ceiling
# --------------------------------------------------------------------------- #
def _validate_platform(platform: Any) -> dict[str, Any]:
    if (
        not isinstance(platform, dict)
        or platform.get("os") not in PLATFORM_OS
        or not isinstance(platform.get("arch"), str)
        or not platform.get("arch")
        or not isinstance(platform.get("postgres_version"), str)
        or not platform.get("postgres_version")
    ):
        raise ValueError("platform must bind os(darwin|linux)/arch/postgres_version")
    return {
        "os": platform["os"],
        "arch": platform["arch"],
        "postgres_version": platform["postgres_version"],
    }


_PRODUCTION_FLAGS = {
    "host_uid_topology": "production_uid_provisioned",
    "pg_role_topology": "production_role_provisioned",
    "socket_dir_acl": "production_socket_provisioned",
}


def _normalize_contract(contract: Any) -> dict[str, Any]:
    """Re-project + structurally validate the contract; raise on unserializable state.

    RAISES (never emits) when a serialized receipt would fake evidence: any
    ``production_*_provisioned`` true, a rotation code that is not denial-class,
    or equal old/new fingerprints.  Shape errors raise ``ValueError``.
    """

    if not isinstance(contract, dict) or set(contract) != set(FACET_KEYS):
        raise ValueError(
            "contract must carry exactly the facet keys: " + ", ".join(FACET_KEYS)
        )
    normalized = copy.deepcopy(contract)

    for facet_key, flag in _PRODUCTION_FLAGS.items():
        rows = normalized.get(facet_key)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"{facet_key} must be a non-empty array")
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{facet_key} entries must be objects")
            if row.get(flag) is True:
                # 明確拒絕:S1.3 不做任何真實 provisioning,聲稱做了即造假。
                raise IdentityAclContractError(
                    f"{facet_key}.{flag} is true; S1.3 provisions nothing real (S2.0/S2.4)"
                )

    auth = normalized.get("auth_mapping")
    if not isinstance(auth, dict):
        raise ValueError("auth_mapping must be an object")
    if auth.get("production_hba_installed") is True:
        raise IdentityAclContractError(
            "auth_mapping.production_hba_installed is true; S1.3 installs no real pg_hba (S2.0/S2.4)"
        )

    secret = normalized.get("secret_lifecycle")
    if not isinstance(secret, dict):
        raise ValueError("secret_lifecycle must be an object")
    if secret.get("production_credential_rotated") is True:
        raise IdentityAclContractError(
            "secret_lifecycle.production_credential_rotated is true; S1.3 rotates no real slot (S2.4)"
        )
    rotation = secret.get("rotation")
    if not isinstance(rotation, dict):
        raise ValueError("secret_lifecycle.rotation must be an object")
    old_fp = rotation.get("old_fingerprint")
    new_fp = rotation.get("new_fingerprint")
    if not DIGEST_RE.fullmatch(str(old_fp)) or not DIGEST_RE.fullmatch(str(new_fp)):
        raise ValueError("secret_lifecycle.rotation fingerprints must be sha256 digests")
    if old_fp == new_fp:
        raise ValueError("secret_lifecycle.rotation old_fingerprint must differ from new_fingerprint")
    proof = rotation.get("old_credential_rejection_proof")
    if not isinstance(proof, dict):
        raise ValueError("secret_lifecycle.rotation.old_credential_rejection_proof is required")
    sqlstate = str(proof.get("observed_sqlstate", ""))
    if proof.get("verdict") != "DENIED" or sqlstate not in CREDENTIAL_DENIAL_SQLSTATES:
        # 非拒絕類的 rotation 碼無法作為 old-credential 拒絕證明 → 不可序列化 → raise。
        raise IdentityAclContractError(
            "old_credential_rejection_proof is not a credential-denial (28P01/28000, DENIED)"
        )
    observation_source = proof.get("observation_source")
    if observation_source not in ROTATION_OBSERVATION_SOURCES:
        raise ValueError("old_credential_rejection_proof.observation_source is invalid")
    if not isinstance(proof.get("new_credential_connected"), bool):
        raise ValueError("old_credential_rejection_proof.new_credential_connected must be boolean")
    if observation_source == "live_disposable_pg":
        # live 輪換證明必須是特定 invalid-password(28P01)且新憑證確實連上(否則可能是缺 role)。
        if sqlstate != ROTATION_INVALID_PASSWORD_SQLSTATE:
            raise IdentityAclContractError(
                "a live rotation proof must observe invalid-password 28P01 (not a generic/peer/ident denial)"
            )
        if proof.get("new_credential_connected") is not True:
            raise IdentityAclContractError(
                "a live rotation proof requires the new credential to have connected first"
            )

    for sock in normalized["socket_dir_acl"]:
        if not _MODE_RE.fullmatch(str(sock.get("mode", ""))):
            raise ValueError("socket_dir_acl mode must match ^0[0-7]{3}$")
        if sock.get("mode_source") not in SOCKET_MODE_SOURCES:
            raise ValueError("socket_dir_acl mode_source must be live_chmod_stat or structural_contract")

    for host in normalized["host_uid_topology"]:
        if host.get("evidence_class") not in HOST_UID_EVIDENCE_CLASSES:
            raise ValueError("host_uid_topology evidence_class must be STRUCTURAL_ONLY or DEFERRED_S2")

    return normalized


def _has_live_disposable_witness(contract: dict[str, Any]) -> bool:
    """Return True iff the contract's advisory labels CLAIM a live disposable observation.

    This keys off the **more-specific advisory labels** — a rotation proof
    ``observation_source==live_disposable_pg`` or a socket ``mode_source==live_chmod_stat``
    — rather than the bare per-facet ``evidence_class`` field, so the laziest forgery
    (flipping ``evidence_class`` alone) cannot lift the ceiling and a hermetic contract with
    the default 28P01/0700 stays ``STRUCTURAL_ONLY``.  **Honesty caveat:** these labels are
    themselves caller-supplied and NOT self-authenticating — a hermetic receipt can set them
    without ever running a cluster; a self-hashed receipt cannot authenticate its own
    execution (CLAUDE §四).  A ``True`` here is therefore a *claim* of a live observation,
    made genuine only by the companion ``_disposable`` re-run (a real cluster /
    ``chmod``/``stat``) or platform attestation — which any S1.5/S2.4 consumer of a
    ``LOCAL_REPRODUCIBLE`` receipt MUST perform before trusting it.
    """

    rotation = (contract.get("secret_lifecycle") or {}).get("rotation") or {}
    proof = rotation.get("old_credential_rejection_proof") or {}
    if proof.get("observation_source") == "live_disposable_pg":
        return True
    for row in contract.get("socket_dir_acl") or []:
        if isinstance(row, dict) and row.get("mode_source") == "live_chmod_stat":
            return True
    return False


def _evidence_ceiling(contract: dict[str, Any]) -> str:
    # ceiling 只認 observation_source/mode_source 這類「較具體的顧問標籤」,不認裸 evidence_class 欄位
    # (擋最懶的單欄升級);host_uid/auth 永不 LOCAL_REPRODUCIBLE。誠實界線:這些標籤仍是呼叫端可自設、
    # 非自我認證的——自雜湊 receipt 無法證明自身執行(CLAUDE §四),LOCAL_REPRODUCIBLE 的真確性需
    # _disposable 重跑或平台背書,消費端不得只信標籤。
    if _has_live_disposable_witness(contract):
        return "LOCAL_REPRODUCIBLE"
    return "STRUCTURAL_ONLY"


# --------------------------------------------------------------------------- #
# receipt builder
# --------------------------------------------------------------------------- #
def build_identity_acl_contract_receipt(
    *,
    caller: str,
    platform: dict[str, Any],
    target_class: str,
    contract: dict[str, Any],
    observation_time: str,
    ttl_seconds: int,
    evidence_class: str,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``identity_acl_contract_receipt_v1``.

    ``status="PASS"`` iff ALL hold: ``target_class==disposable_local``;
    ``evidence_class`` equals the strongest non-deferred facet exercised; the
    honest ``contract`` carries no over-grant; and all ten crux over-grants are
    proven REJECTED.  Integrity violations that cannot be safely serialized (a
    secret, a ``production_*_provisioned`` true, a non-denial rotation code, an
    over-grant not rejected, ttl out of ``[1, 3600]``) RAISE instead of emitting.
    Otherwise ``status="FAIL"`` with a non-empty ``failure_reason`` (e.g. a
    ``production`` target request, honestly recorded and refused).
    """

    if not isinstance(caller, str) or not caller:
        raise ValueError("caller is required")
    if target_class not in TARGET_CLASSES:
        raise ValueError(f"target_class is not recognized: {target_class!r}")
    if evidence_class not in EVIDENCE_CLASSES:
        raise ValueError(f"evidence_class is not recognized: {evidence_class!r}")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ValueError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise ValueError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")

    platform_block = _validate_platform(platform)
    normalized = _normalize_contract(contract)
    # 在生成 negative 前先掃描誠實契約本身(排除機密殘留)。
    _guard_no_secret(normalized)

    honest_errors = assert_least_privilege_topology(normalized)
    if honest_errors:
        raise LeastPrivilegeError(
            "contract is not least-privilege: " + "; ".join(honest_errors)
        )
    negative_cases = build_negative_acl_cases(normalized)

    ceiling = _evidence_ceiling(normalized)
    observed = _parse_time(observation_time)
    expires = observed + timedelta(seconds=ttl_seconds)

    reasons: list[str] = []
    if target_class != S1_TARGET_CLASS:
        reasons.append("target_class is not disposable_local (S1.3 is disposable-only)")
    if evidence_class != ceiling:
        reasons.append(
            f"evidence_class {evidence_class} is not the strongest non-deferred facet exercised ({ceiling})"
        )

    status = "PASS" if not reasons else "FAIL"
    failure_reason = None if status == "PASS" else "; ".join(reasons)

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "status": status,
        "caller": caller,
        "platform": platform_block,
        "target_class": target_class,
        "evidence_class": evidence_class,
        "host_uid_topology": normalized["host_uid_topology"],
        "pg_role_topology": normalized["pg_role_topology"],
        "auth_mapping": normalized["auth_mapping"],
        "socket_dir_acl": normalized["socket_dir_acl"],
        "secret_lifecycle": normalized["secret_lifecycle"],
        "rollback": normalized["rollback"],
        "negative_acl_cases": negative_cases,
        "source_sha256": source_sha256(),
        "schema_sha256": schema_sha256(),
        "secret_scan": {
            "patterns_checked": list(SECRET_PATTERNS_CHECKED),
            "leaked": False,
        },
        "observation_time": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "ttl_seconds": ttl_seconds,
        "failure_reason": failure_reason,
    }
    # 計算 self_digest 前對整份 receipt(排除 secret_scan)再掃一次機密。
    _guard_no_secret({k: v for k, v in receipt.items() if k != "secret_scan"})
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


# --------------------------------------------------------------------------- #
# receipt validator (structural + integrity; not execution authenticity)
# --------------------------------------------------------------------------- #
def validate_identity_acl_contract_receipt(
    receipt: Any,
    *,
    require_success: bool = False,
    now: str | None = None,
) -> list[str]:
    """Validate receipt structure/integrity and the S1.3 disposable-only gate.

    Mirrors ``validate_pg_readonly_identity_receipt``: schema subset, exact
    field-set, const identity, digest regexes, source/schema binding, per-facet
    least-privilege invariants (distinct UIDs/roles, no superuser/writer-for-
    reader, private socket mode ``& 0o077 == 0``, local-only auth, rollback
    coverage), the ten crux negative-ACL cases all REJECTED, secret-free
    serialization, evidence-ceiling consistency, TTL/time ordering and
    ``self_digest`` re-derivation.  ``target_class`` must be ``disposable_local``.
    """

    if not isinstance(receipt, dict):
        return ["identity acl contract receipt must be an object"]
    schema = _receipt_schema()
    errors = [
        f"identity acl contract receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != RECEIPT_FIELDS:
        errors.append(
            "identity acl contract receipt fields mismatch: "
            f"missing={sorted(RECEIPT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - RECEIPT_FIELDS)}"
        )
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        errors.append("identity acl contract receipt schema_version is invalid")
    if receipt.get("adapter_id") != ADAPTER_ID:
        errors.append("identity acl contract receipt adapter_id is invalid")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        errors.append("identity acl contract receipt status is invalid")
    if receipt.get("target_class") != S1_TARGET_CLASS:
        errors.append(
            "identity acl contract receipt target_class must be disposable_local "
            "(production is rejected at the S1.3 gate)"
        )
    for field_name in ("source_sha256", "schema_sha256", "self_digest"):
        if not DIGEST_RE.fullmatch(str(receipt.get(field_name, ""))):
            errors.append(f"identity acl contract receipt {field_name} is invalid")
    if receipt.get("source_sha256") != source_sha256():
        errors.append("identity acl contract receipt source_sha256 does not bind this module")
    if receipt.get("schema_sha256") != schema_sha256():
        errors.append("identity acl contract receipt schema_sha256 does not bind the schema")

    errors.extend(_validate_host_uid_topology(receipt.get("host_uid_topology")))
    errors.extend(_validate_pg_role_topology(receipt.get("pg_role_topology")))
    errors.extend(_validate_auth_mapping(receipt.get("auth_mapping")))
    errors.extend(_validate_socket_dir_acl(receipt.get("socket_dir_acl")))
    errors.extend(_validate_secret_lifecycle(receipt.get("secret_lifecycle")))
    errors.extend(_validate_rollback(receipt.get("rollback")))
    errors.extend(_validate_negative_cases(receipt.get("negative_acl_cases")))
    errors.extend(_validate_secret_scan(receipt))
    errors.extend(_validate_times(receipt, now=now))
    # 元件完整性:三個 facet 必須恰好覆蓋正規元件集(不得靜默 drop controller 列/單元件/重複)。
    errors.extend(_validate_component_completeness(receipt))
    # 消費者的 gate 必須獨立重驗:從 receipt 重建 6-facet 契約,重跑 least-privilege 檢查與
    # negative 生成器,而非僅信任 receipt 自報的 REJECTED verdict。
    errors.extend(_validate_reconstructed_contract(receipt))
    # pg_role facet 若標 LOCAL_REPRODUCIBLE,至少須帶 live 觀察標籤(observation_source=live_disposable_pg
    # 等),否則就是最懶的裸 evidence_class 升級 → 拒絕。註:此標籤仍是顧問性、非自我認證,真確性需消費端
    # _disposable 重跑或平台背書(見 _has_live_disposable_witness 的誠實界線)。
    if not _has_live_disposable_witness(receipt):
        for row in receipt.get("pg_role_topology") or []:
            if isinstance(row, dict) and row.get("evidence_class") == "LOCAL_REPRODUCIBLE":
                errors.append(
                    "identity acl contract pg_role claims LOCAL_REPRODUCIBLE without a live disposable observation"
                )
                break

    # evidence_class 必須等於實際行使的最強非 deferred facet(可獨立重算)。
    if isinstance(receipt.get("evidence_class"), str):
        try:
            ceiling = _evidence_ceiling(receipt)
        except (AttributeError, TypeError):
            ceiling = None
        if ceiling is not None and receipt.get("evidence_class") != ceiling:
            errors.append(
                "identity acl contract evidence_class is not the strongest facet exercised"
            )

    status = receipt.get("status")
    failure_reason = receipt.get("failure_reason")
    if status == "PASS":
        if failure_reason is not None:
            errors.append("PASS receipt cannot carry a failure_reason")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAIL receipt requires a non-empty failure_reason")

    if require_success and status != "PASS":
        errors.append("identity acl contract receipt does not prove a passing contract")
    if receipt.get("self_digest") != receipt_digest(receipt):
        errors.append("identity acl contract receipt self_digest does not match canonical receipt")
    return errors


def _reconstruct_contract(receipt: dict[str, Any]) -> dict[str, Any]:
    # 從 receipt 重建 6-facet 契約(validator 獨立重驗用,絕不信任自報 verdict)。
    return {key: receipt.get(key) for key in FACET_KEYS}


def _validate_component_completeness(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expectations = (
        ("host_uid_topology", set(COMPONENTS)),
        ("socket_dir_acl", set(COMPONENTS)),
        ("pg_role_topology", set(PG_ROLE_COMPONENTS)),
    )
    for facet, expected in expectations:
        rows = receipt.get(facet)
        if not isinstance(rows, list) or not rows:
            errors.append(f"identity acl contract {facet} is missing for component completeness")
            continue
        components = [row.get("component") for row in rows if isinstance(row, dict)]
        if len(components) != len(set(components)):
            errors.append(f"identity acl contract {facet} has a duplicate component row")
        if set(components) != expected:
            errors.append(
                f"identity acl contract {facet} components must be exactly {sorted(expected)} "
                f"(got {sorted(set(c for c in components if c is not None))})"
            )
    return errors


def _validate_reconstructed_contract(receipt: dict[str, Any]) -> list[str]:
    """Independently re-verify the reconstructed contract (item E3 P2-3).

    Re-runs ``assert_least_privilege_topology`` (must be EMPTY) and
    ``build_negative_acl_cases`` (must not raise; produced kinds must match the
    claimed ``negative_acl_cases`` kinds exactly) on the contract reconstructed
    from the receipt — so a forged receipt cannot rubber-stamp fabricated REJECTED
    negatives or hide an over-grant behind claimed verdicts.
    """

    errors: list[str] = []
    reconstructed = _reconstruct_contract(receipt)
    try:
        over_grants = assert_least_privilege_topology(reconstructed)
    except Exception as exc:  # noqa: BLE001 - malformed reconstruction cannot be certified
        errors.append(f"identity acl contract reconstructed topology could not be checked: {exc}")
        return errors
    if over_grants:
        errors.append(
            "identity acl contract reconstructed topology is not least-privilege: "
            + "; ".join(over_grants)
        )
    try:
        rebuilt = build_negative_acl_cases(reconstructed)
    except LeastPrivilegeError as exc:
        errors.append(
            f"identity acl contract negative_acl_cases could not be independently reproduced: {exc}"
        )
        return errors
    except Exception as exc:  # noqa: BLE001 - malformed reconstruction for the negative re-run
        errors.append(
            f"identity acl contract reconstructed contract is malformed for the negative re-run: {exc}"
        )
        return errors
    produced = sorted(case["over_grant_kind"] for case in rebuilt)
    claimed = sorted(
        case.get("over_grant_kind")
        for case in (receipt.get("negative_acl_cases") or [])
        if isinstance(case, dict)
    )
    if produced != claimed:
        errors.append(
            "identity acl contract negative_acl_cases do not match an independent re-derivation: "
            f"produced={produced} claimed={claimed}"
        )
    return errors


def _validate_host_uid_topology(rows: Any) -> list[str]:
    if not isinstance(rows, list) or not rows:
        return ["identity acl contract host_uid_topology is missing"]
    errors: list[str] = []
    labels = [row.get("uid_label") for row in rows if isinstance(row, dict)]
    if len(set(labels)) != len(labels):
        errors.append("identity acl contract host UID labels are not distinct")
    for row in rows:
        if not isinstance(row, dict):
            errors.append("identity acl contract host_uid_topology entry is invalid")
            continue
        if row.get("non_root") is not True:
            errors.append(f"identity acl contract component {row.get('component')} is not non-root")
        if row.get("oci_socket_access") is not False or row.get("dbus_authority") is not False:
            errors.append(
                f"identity acl contract component {row.get('component')} holds OCI socket or DBus authority"
            )
        if row.get("production_uid_provisioned") is not False:
            errors.append("identity acl contract host_uid production_uid_provisioned must be false")
    return errors


def _validate_pg_role_topology(rows: Any) -> list[str]:
    if not isinstance(rows, list) or not rows:
        return ["identity acl contract pg_role_topology is missing"]
    errors: list[str] = []
    names = [row.get("role_name") for row in rows if isinstance(row, dict)]
    if len(set(names)) != len(names):
        errors.append("identity acl contract PG role names are not distinct")
    for row in rows:
        if not isinstance(row, dict):
            errors.append("identity acl contract pg_role_topology entry is invalid")
            continue
        if row.get("is_superuser") is not False:
            errors.append(f"identity acl contract role {row.get('role_name')} is superuser")
        if row.get("forbidden_attrs_all_false") is not True:
            errors.append(f"identity acl contract role {row.get('role_name')} holds a forbidden attribute")
        if row.get("writer_for_reader") is not False:
            errors.append(f"identity acl contract role {row.get('role_name')} is a writer-for-reader")
        if row.get("privilege_class") in READER_PRIVILEGE_CLASSES and row.get("is_reader") is not True:
            errors.append(f"identity acl contract reader-class role {row.get('role_name')} is not a reader")
        # 元件→正規 privilege_class 綁定:偽造 receipt 不得把某元件 mislabel 成別的最小權限類。
        expected_class = CANONICAL_PRIVILEGE_CLASS.get(row.get("component"))
        if expected_class is not None and row.get("privilege_class") != expected_class:
            errors.append(
                f"identity acl contract component {row.get('component')} privilege_class must be "
                f"{expected_class} (got {row.get('privilege_class')})"
            )
        if row.get("production_role_provisioned") is not False:
            errors.append("identity acl contract pg_role production_role_provisioned must be false")
    return errors


def _validate_auth_mapping(auth: Any) -> list[str]:
    if not isinstance(auth, dict):
        return ["identity acl contract auth_mapping is missing"]
    errors: list[str] = []
    if auth.get("method") not in AUTH_METHODS:
        errors.append("identity acl contract auth method is not local-only")
    if auth.get("local_only") is not True:
        errors.append("identity acl contract auth mapping is not local-only")
    if auth.get("trust_from_anywhere") is not False:
        errors.append("identity acl contract auth allows trust from anywhere")
    if auth.get("wide_cidr") is not False:
        errors.append("identity acl contract auth binds a wide CIDR")
    if auth.get("production_hba_installed") is not False:
        errors.append("identity acl contract auth production_hba_installed must be false")
    return errors


def _validate_socket_dir_acl(rows: Any) -> list[str]:
    if not isinstance(rows, list) or not rows:
        return ["identity acl contract socket_dir_acl is missing"]
    errors: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            errors.append("identity acl contract socket_dir_acl entry is invalid")
            continue
        if not _mode_is_private(row.get("mode")):
            errors.append(
                f"identity acl contract socket {row.get('socket_dir_label')} mode is group/world accessible"
            )
        if row.get("world_readable") is not False or row.get("world_writable") is not False:
            errors.append(
                f"identity acl contract socket {row.get('socket_dir_label')} is world readable/writable"
            )
        if row.get("mode_source") not in SOCKET_MODE_SOURCES:
            errors.append(
                f"identity acl contract socket {row.get('socket_dir_label')} mode_source is invalid"
            )
        # socket facet 標 LOCAL_REPRODUCIBLE 必須來自真實 chmod/stat(mode_source=live_chmod_stat)。
        if row.get("evidence_class") == "LOCAL_REPRODUCIBLE" and row.get("mode_source") != "live_chmod_stat":
            errors.append(
                f"identity acl contract socket {row.get('socket_dir_label')} claims LOCAL_REPRODUCIBLE "
                "without a live chmod/stat observation"
            )
        if row.get("production_socket_provisioned") is not False:
            errors.append("identity acl contract socket production_socket_provisioned must be false")
    return errors


def _validate_secret_lifecycle(secret: Any) -> list[str]:
    if not isinstance(secret, dict):
        return ["identity acl contract secret_lifecycle is missing"]
    errors: list[str] = []
    if secret.get("plaintext_ingress") is not False:
        errors.append("identity acl contract secret_lifecycle plaintext_ingress must be false")
    if secret.get("production_credential_rotated") is not False:
        errors.append("identity acl contract secret_lifecycle production_credential_rotated must be false")
    protected = secret.get("protected_loading")
    if not isinstance(protected, dict) or protected.get("no_plaintext_ingress") is not True:
        errors.append("identity acl contract protected_loading.no_plaintext_ingress must be true")
    rotation = secret.get("rotation")
    if not isinstance(rotation, dict):
        return errors + ["identity acl contract secret_lifecycle rotation is missing"]
    if rotation.get("old_fingerprint") == rotation.get("new_fingerprint"):
        errors.append("identity acl contract rotation old_fingerprint must differ from new_fingerprint")
    # 輪換順序安全性(先 stage → alter → 最後 revoke;revoke-before-stage 一律拒絕)。
    errors.extend(_rotation_order_errors(rotation.get("rotation_order")))
    proof = rotation.get("old_credential_rejection_proof")
    if not isinstance(proof, dict):
        errors.append("identity acl contract old_credential_rejection_proof is missing")
    else:
        sqlstate = str(proof.get("observed_sqlstate", ""))
        observation_source = proof.get("observation_source")
        new_connected = proof.get("new_credential_connected")
        if proof.get("verdict") != "DENIED":
            errors.append("identity acl contract old-credential rejection verdict must be DENIED")
        if not SQLSTATE_RE.fullmatch(sqlstate) or sqlstate not in CREDENTIAL_DENIAL_SQLSTATES:
            errors.append("identity acl contract old-credential rejection SQLSTATE is not credential-denial class")
        if observation_source not in ROTATION_OBSERVATION_SOURCES:
            errors.append("identity acl contract old-credential rejection observation_source is invalid")
        if not isinstance(new_connected, bool):
            errors.append("identity acl contract old-credential rejection new_credential_connected must be boolean")
        if observation_source == "live_disposable_pg":
            # live 輪換證明:必須 28P01 invalid-password 且新憑證確實先連上(排除缺 role/peer/ident 誤判)。
            if sqlstate != ROTATION_INVALID_PASSWORD_SQLSTATE:
                errors.append(
                    "identity acl contract live rotation proof must observe invalid-password 28P01"
                )
            if new_connected is not True:
                errors.append(
                    "identity acl contract live rotation proof requires the new credential to have connected"
                )
        # secret facet 標 LOCAL_REPRODUCIBLE 至少須帶 live rotation 標籤(observation_source=live_disposable_pg)
        # ——擋裸 evidence_class 升級;該標籤仍是顧問性、非自我認證,真確性需消費端 _disposable 重跑或平台背書。
        if secret.get("evidence_class") == "LOCAL_REPRODUCIBLE" and observation_source != "live_disposable_pg":
            errors.append(
                "identity acl contract secret_lifecycle claims LOCAL_REPRODUCIBLE without a live "
                "disposable rotation observation"
            )
    return errors


def _validate_rollback(rows: Any) -> list[str]:
    if not isinstance(rows, list) or not rows:
        return ["identity acl contract rollback is missing"]
    errors: list[str] = []
    present_kinds: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            errors.append("identity acl contract rollback entry is invalid")
            continue
        present_kinds.add(row.get("change_kind"))
        if not DIGEST_RE.fullmatch(str(row.get("pre_state_digest", ""))):
            errors.append(f"identity acl contract rollback {row.get('change_id')} pre_state_digest is invalid")
        if not isinstance(row.get("rollback_action"), str) or not row.get("rollback_action"):
            errors.append(f"identity acl contract rollback {row.get('change_id')} lacks a rollback_action")
        if row.get("recovery") not in RECOVERY_KINDS:
            errors.append(f"identity acl contract rollback {row.get('change_id')} recovery is invalid")
    # 每項隱含變更種類都要有對應 rollback(host_uid/pg_role/auth_mapping/socket_acl/secret_slot)。
    for kind in sorted(CHANGE_KINDS):
        if kind not in present_kinds:
            errors.append(f"identity acl contract rollback is missing change_kind {kind}")
    return errors


def _validate_negative_cases(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return ["identity acl contract negative_acl_cases are missing"]
    errors: list[str] = []
    kinds: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            errors.append("identity acl contract negative_acl_case is invalid")
            continue
        kinds.add(row.get("over_grant_kind"))
        if row.get("expected") != "FAIL_CLOSED":
            errors.append(f"identity acl contract negative case {row.get('case_id')} expected must be FAIL_CLOSED")
        if row.get("observed_verdict") != "REJECTED":
            errors.append(f"identity acl contract negative case {row.get('case_id')} was not REJECTED")
    missing = CRUX_OVER_GRANT_KINDS - kinds
    if missing:
        errors.append(
            "identity acl contract negative_acl_cases miss crux over-grants: " + ",".join(sorted(missing))
        )
    return errors


def _validate_secret_scan(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    secret_scan = receipt.get("secret_scan")
    if not isinstance(secret_scan, dict):
        return ["identity acl contract receipt secret_scan is missing"]
    if secret_scan.get("leaked") is not False:
        errors.append("identity acl contract secret_scan must report leaked=false")
    if list(secret_scan.get("patterns_checked", [])) != list(SECRET_PATTERNS_CHECKED):
        errors.append("identity acl contract secret_scan patterns are not the exact contract")
    if _contains_secret_like({k: v for k, v in receipt.items() if k != "secret_scan"}):
        errors.append("identity acl contract receipt carries secret-like content")
    return errors


def _validate_times(receipt: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    ttl_seconds = receipt.get("ttl_seconds")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        return ["identity acl contract receipt ttl_seconds is invalid"]
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        errors.append(f"identity acl contract ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    try:
        observed = _parse_time(str(receipt.get("observation_time", "")))
        expires = _parse_time(str(receipt.get("expires_at", "")))
        if expires != observed + timedelta(seconds=ttl_seconds):
            errors.append("identity acl contract expires_at does not equal observation_time + ttl")
        if not observed < expires:
            errors.append("identity acl contract observation_time must precede expires_at")
        if now is not None:
            current = _parse_time(now)
            if not observed <= current < expires:
                errors.append("identity acl contract receipt is not fresh")
    except (TypeError, ValueError):
        errors.append("identity acl contract receipt timestamps are invalid")
    return errors

"""Offline learning-runtime candidate spike for AIML LR0C (S1.4).

This harness evaluates the two candidate runtime *shapes* from plan §LR0C on the
seams that are checkable **without a target-host runtime probe** and emits, per
candidate, one canonical self-hashed ``runtime_candidate_receipt_v1`` plus a
single preliminary ``runtime_candidate_comparison_v1``.

The two candidates are:

* ``exact_image_id_oci`` — an OCI image pinned by exact image ID / digest.
* ``content_addressed_fixed_path`` — a hash-named runtime bundle at a fixed path.

S1.4 is ``DISPOSABLE_ONLY`` and structurally cannot select a runtime:

* ``target_class`` accepts only ``disposable_offline``; ``target_host`` is
  rejected fail-closed (a target-host candidate is an S1.6 concern and cannot be
  evaluated offline at all).
* every runtime-only seam (kernel isolation / cgroup / network denial /
  start-stop / PG identity / native-lib *loading*) is recorded
  ``verdict=DEFERRED_S1_6``; a PASS receipt that marked any of them
  ``OFFLINE_PROVEN`` is rejected by the schema and the validator.
* the comparison's ``final_choice`` is schema-const ``null``; the real choice is
  S1.6's ``learning_runtime_choice_receipt_v1``.

Like S1.1, this harness self-validates its own receipts and deliberately does NOT
register into the central AIML closure-validator, the governance registry, the
route-compiler, permissions, or the vocabulary; S1.4 stays disjoint (protocol
line 159).  It is stdlib-first (``hashlib``/``json``/``subprocess``/
``shutil.which``/``tempfile``) and never pulls a base image, builds, or hits the
network — the OCI candidate is evaluated at the digest-pinning / sealed-input
*mechanism* level only.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform as platform_module
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent_governance_schema import schema_subset_errors


HARNESS_ID = "runtime_candidate_spike_v1"
RECEIPT_SCHEMA_VERSION = "runtime_candidate_receipt_v1"
COMPARISON_SCHEMA_VERSION = "runtime_candidate_comparison_v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
SCHEMA_DIR = REPO_ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
RECEIPT_SCHEMA_PATH = SCHEMA_DIR / "runtime_candidate_receipt_v1.schema.json"
COMPARISON_SCHEMA_PATH = SCHEMA_DIR / "runtime_candidate_comparison_v1.schema.json"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# 兩個候選的合法 id;未知 id 一律 fail-closed。
CANDIDATE_OCI = "exact_image_id_oci"
CANDIDATE_FIXED_PATH = "content_addressed_fixed_path"
CANDIDATE_IDS = frozenset({CANDIDATE_OCI, CANDIDATE_FIXED_PATH})

# S1.4 只接受 disposable_offline;target_host 屬 S1.6,離線根本無從評估,故 raise。
TARGET_CLASSES = frozenset({"disposable_offline", "target_host"})
S1_TARGET_CLASS = "disposable_offline"

EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY"})
SEAM_EVIDENCE_CLASSES = frozenset({"LOCAL_REPRODUCIBLE", "STRUCTURAL_ONLY", "DEFERRED"})
PLATFORM_OS = frozenset({"darwin", "linux"})

VERDICT_OFFLINE = "OFFLINE_PROVEN"
VERDICT_STRUCTURAL = "STRUCTURAL_DESIGN"
VERDICT_DEFERRED = "DEFERRED_S1_6"
SEAM_VERDICTS = frozenset({VERDICT_OFFLINE, VERDICT_STRUCTURAL, VERDICT_DEFERRED})

# verdict → 每 seam 的 evidence_class 映射(嚴格一對一,validator 據此檢查一致性)。
VERDICT_TO_EVIDENCE = {
    VERDICT_OFFLINE: "LOCAL_REPRODUCIBLE",
    VERDICT_STRUCTURAL: "STRUCTURAL_ONLY",
    VERDICT_DEFERRED: "DEFERRED",
}

TTL_CEILING_SECONDS = 3600

# 只有 target-host runtime probe(S1.6)才能行使的 seam;PASS receipt 內必為 DEFERRED_S1_6。
RUNTIME_ONLY_SEAMS = (
    "native_lib_loading_target",
    "cgroup_isolation",
    "network_denial",
    "start_stop_failure_cleanup",
    "pg_identity_runtime",
)

# 每個 seam 的裁決層級(comparison.seam_matrix 用):S1.4 離線可判 / LR2 網路封存建置 / S1.6 host probe。
SEAM_DECISIVE_AT = {
    "content_addressing_determinism": "S1.4",
    "sealed_build_input_digest": "S1.4",
    "python_isolated_mode": "S1.4",
    "no_system_python_fallback": "S1.4",
    "non_relocatable_no_mutable_alias": "S1.4",
    "exact_image_id_pin": "S1.4",
    "native_lib_inventory_origin": "S1.4",
    "rollback_bundle_shape": "S1.4",
    "artifact_persistence_model": "S1.4",
    "real_ml_dep_closure_resolution": "LR2",
    "reproducible_output_bit_identity": "LR2",
    "native_lib_loading_target": "S1.6",
    "cgroup_isolation": "S1.6",
    "network_denial": "S1.6",
    "start_stop_failure_cleanup": "S1.6",
    "pg_identity_runtime": "S1.6",
}

# OCI 專屬 seam:content-addressed fixed-path 不適用(comparison 內記 N_A,receipt 內不列)。
OCI_ONLY_SEAMS = frozenset({"exact_image_id_pin"})

# 每候選的封閉 seam-id 集合:由 SEAM_DECISIVE_AT(全 seam)扣除不適用的 OCI 專屬 seam
# 單一事實來源推導。validator 據此拒絕缺漏/多餘/重命名/同形異義(如尾隨空白)seam,
# 杜絕偽造 receipt 夾帶額外 seam 走私 runtime-only 能力的離線偽證。
EXPECTED_SEAMS = {
    CANDIDATE_OCI: frozenset(SEAM_DECISIVE_AT),
    CANDIDATE_FIXED_PATH: frozenset(SEAM_DECISIVE_AT) - OCI_ONLY_SEAMS,
}

# 對序列化 receipt 做的機密掃描,沿用 S1.1 風格(github token / auth header /
# credential assignment / provider secret)。S1.4 receipt 不嵌任何 host 路徑或憑證。
SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}",
    re.IGNORECASE,
)
SECRET_PATTERNS_CHECKED = (
    "auth_scheme_token",
    "credential_assignment",
    "github_token",
    "provider_secret",
)

RECEIPT_FIELDS = frozenset({
    "schema_version",
    "harness_id",
    "status",
    "caller",
    "platform",
    "candidate",
    "target_class",
    "evidence_class",
    "dependency_closure",
    "native_library_inventory",
    "isolation_mode",
    "sealed_input",
    "immutability",
    "artifact_persistence",
    "rollback",
    "oci_build",
    "seams",
    "source_sha256",
    "schema_sha256",
    "secret_scan",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "failure_reason",
    "self_digest",
})

COMPARISON_FIELDS = frozenset({
    "schema_version",
    "harness_id",
    "candidate_a_digest",
    "candidate_b_digest",
    "candidate_status",
    "seam_matrix",
    "deferred_to_s1_6",
    "preliminary_lean",
    "final_choice",
    "source_sha256",
    "schema_sha256",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "self_digest",
})

# 內容定址 fixture:固定位元組,同輸入必得同 closure hash(離線、無 daemon)。
FIXTURE_FILES = {
    "bin/launch_contract.txt": (
        b"# absolute-pinned launch contract (no PATH lookup, no /usr/bin/python3 fallback)\n"
        b"exec ${BUNDLE}/bin/python3 -I -m aiml_runtime\n"
    ),
    "lib/native/placeholder_lightgbm.marker": (
        b"native-lib-placeholder: lightgbm - structural inventory only; "
        b"real .so loading is DEFERRED_S1_6\n"
    ),
    "lib/native/placeholder_onnxruntime.marker": (
        b"native-lib-placeholder: onnxruntime - structural inventory only; "
        b"real .so loading is DEFERRED_S1_6\n"
    ),
    "requirements.lock": (
        b"# pinned dependency-closure placeholder; real LightGBM/sklearn/ONNX "
        b"resolution is a networked LR2 sealed-build step, not offline\n"
    ),
    "manifest.json": (
        b'{"runtime":"content_addressed_fixed_path","real_ml_closure_resolved":false}\n'
    ),
}

# OCI 候選的離線 sealed-input 素材(全為 design bytes,永不建置/不 pull/不觸網)。
# base 以 digest(而非 mutable tag)釘住;真實 base digest 需 registry pull(網路)=DEFERRED。
OCI_BASE_IMAGE_NAME = "python:3.10-slim"
OCI_DOCKERFILE_SPEC = (
    b"# base pinned by digest, never a mutable tag\n"
    b"FROM python:3.10-slim@sha256:<pinned-base-digest>\n"
    b"COPY runtime/ /opt/aiml/runtime/\n"
    b'ENTRYPOINT ["/opt/aiml/runtime/bin/python3", "-I", "-m", "aiml_runtime"]\n'
)


class SecretLeakageError(RuntimeError):
    """Raised when a would-be receipt field carries secret-like content.

    Fail-closed:拒絕序列化任何帶密的 receipt(即使是 FAIL receipt)。
    """


class RuntimeSeamClaimError(RuntimeError):
    """Raised when a runtime-only seam is not deferred.

    S1.4 離線不可能證明任何 runtime seam;若組裝時某 runtime seam 非 DEFERRED_S1_6,
    視為結構完整性破壞而 raise,絕不序列化。
    """


class TargetHostRejectedError(RuntimeError):
    """Raised when a target_host candidate reaches the S1.4 gate.

    target_host 屬 S1.6;離線根本無從評估,故直接 raise 而非發出 FAIL receipt。
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


def _canonical_digest(value: Any) -> str:
    return _sha256_bytes(_canonical_bytes(value))


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


@lru_cache(maxsize=1)
def _receipt_schema() -> dict[str, Any]:
    return json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _comparison_schema() -> dict[str, Any]:
    return json.loads(COMPARISON_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this harness module source."""

    return _file_sha256(SOURCE_PATH)


@lru_cache(maxsize=1)
def receipt_schema_sha256() -> str:
    """Return the sha256 identity of the per-candidate receipt schema file."""

    return _file_sha256(RECEIPT_SCHEMA_PATH)


@lru_cache(maxsize=1)
def comparison_schema_sha256() -> str:
    """Return the sha256 identity of the comparison schema file."""

    return _file_sha256(COMPARISON_SCHEMA_PATH)


def receipt_digest(receipt: dict[str, Any]) -> str:
    """Hash every receipt field except the self-digest."""

    unsigned = {key: value for key, value in receipt.items() if key != "self_digest"}
    return _canonical_digest(unsigned)


def comparison_digest(comparison: dict[str, Any]) -> str:
    """Hash every comparison field except the self-digest."""

    unsigned = {key: value for key, value in comparison.items() if key != "self_digest"}
    return _canonical_digest(unsigned)


# --------------------------------------------------------------------------- #
# secret scan (fail-closed, mirror S1.1)
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
        raise SecretLeakageError("receipt payload carries secret-like content")


# --------------------------------------------------------------------------- #
# platform detection (stdlib + PATH lookup only; never contacts a daemon)
# --------------------------------------------------------------------------- #
def detect_platform() -> dict[str, Any]:
    """Capture the Mac/Linux reality via stdlib + ``shutil.which`` — no daemon.

    ``container_runtime``/``container_runtime_available`` are pure PATH lookups
    (a ``which`` never contacts the Docker daemon or the network).
    ``buildx_available`` defaults to ``False`` because proving a linux/amd64
    cross-build capability requires invoking docker, which S1.4 must not do; the
    offline-honest default is ``False`` (dev-Mac ground truth: no buildx plugin).
    """

    runtime = None
    for candidate in ("docker", "podman", "nerdctl"):
        if shutil.which(candidate):
            runtime = candidate
            break
    return {
        "os": "darwin" if sys.platform == "darwin" else "linux",
        "arch": platform_module.machine() or "unknown",
        "python_version": platform_module.python_version(),
        "container_runtime": runtime,
        "container_runtime_available": runtime is not None,
        "buildx_available": False,
    }


# --------------------------------------------------------------------------- #
# candidate B — content-addressing (OFFLINE_PROVEN, real local bytes)
# --------------------------------------------------------------------------- #
def materialize_fixture_bundle(dest: str | os.PathLike[str]) -> Path:
    """Write the deterministic fixture runtime tree into ``dest`` (idempotent bytes).

    同輸入必得同 closure hash;呼叫端負責在 disposable temp dir 內建立與拆除。
    """

    root = Path(dest)
    for rel_path, data in FIXTURE_FILES.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return root


def hash_bundle_tree(root: str | os.PathLike[str]) -> tuple[str, int]:
    """Compute the deterministic dependency-closure hash of a runtime tree.

    以「排序後的相對路徑 + 各檔 sha256」的 canonical 投影雜湊之;同一棵樹的位元組
    必得同一 closure hash(離線、純 stdlib、無 daemon)。回傳 ``(closure_hash, file_count)``。
    """

    base = Path(root)
    entries = []
    for path in sorted(base.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_file():
            rel = path.relative_to(base).as_posix()
            entries.append({"path": rel, "sha256": _file_sha256(path)})
    return _canonical_digest(entries), len(entries)


def inventory_native_libraries(root: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Inventory + origin-hash the fixture's placeholder native libs (structural).

    這是機制證明:枚舉 + 雜湊 fixture 內的 ``.marker`` 佔位檔。真實
    LightGBM/sklearn/ONNX ``.so`` 的解析與載入不在此(載入=DEFERRED_S1_6,
    解析=LR2 網路封存建置)。
    """

    base = Path(root)
    inventory = []
    for path in sorted((base / "lib" / "native").glob("*.marker")):
        inventory.append({
            "name": path.stem,
            "origin": "fixture_vendored_placeholder",
            "sha256": _file_sha256(path),
        })
    return inventory


# --------------------------------------------------------------------------- #
# isolated-mode / no-system-python-fallback probe (OFFLINE_PROVEN, real subprocess)
# --------------------------------------------------------------------------- #
def probe_python_isolated_mode(interpreter: str | None = None) -> dict[str, Any]:
    """Run ``<interpreter> -I`` and prove it ignores an injected ``PYTHONPATH``.

    以絕對釘住的直譯器(預設 ``sys.executable``,不走 PATH 查找)實跑兩次:
    ``-I`` 隔離模式下注入的 ``PYTHONPATH`` 必被忽略(``sys.path`` 不含 marker,
    且 ``isolated==1``/``no_user_site==1``);對照組(無 ``-I``)同一 marker 必出現於
    ``sys.path``,證明 marker 為真且 ``-I`` 正是抹除它的機制。兩支子進程皆在
    disposable temp marker 目錄下執行,結束即拆除。
    """

    interpreter = interpreter or sys.executable
    if not interpreter:
        raise RuntimeError("no python interpreter available for the isolated-mode probe")

    marker_dir = tempfile.mkdtemp(prefix="aiml_s14_injected_")
    try:
        probe_src = (
            "import sys, json\n"
            "marker = sys.argv[1]\n"
            "print(json.dumps({\n"
            "    'isolated': int(sys.flags.isolated),\n"
            "    'no_user_site': int(sys.flags.no_user_site),\n"
            "    'injected_present': marker in sys.path,\n"
            "}))\n"
        )
        env = dict(os.environ)
        env["PYTHONPATH"] = marker_dir

        def _run(args: list[str]) -> dict[str, Any]:
            completed = subprocess.run(
                [interpreter, *args, "-c", probe_src, marker_dir],
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            return json.loads(completed.stdout.strip())

        isolated = _run(["-I"])
        # 對照組:不加 -I,PYTHONPATH 必被尊重(injected_present==True),排除偽陰性。
        control = _run([])
    finally:
        shutil.rmtree(marker_dir, ignore_errors=True)

    return {
        "isolated_flag": isolated["isolated"],
        "no_user_site_flag": isolated["no_user_site"],
        "injected_absent_under_isolated": isolated["injected_present"] is False,
        "injected_present_without_isolated": control["injected_present"] is True,
        "python_isolated_mode": isolated["isolated"] == 1 and isolated["no_user_site"] == 1,
        "ignores_ambient_env": isolated["injected_present"] is False,
        "system_python_fallback_possible": False,
        "launch_interpreter": "absolute_pinned",
        "evidence_class": "LOCAL_REPRODUCIBLE",
    }


def structural_isolation_contract() -> dict[str, Any]:
    """Return the STRUCTURAL isolation contract (no subprocess run).

    供 structural 測試與「離線不跑子進程」路徑使用;證據等級為 STRUCTURAL_ONLY,
    絕不冒充實跑的 LOCAL_REPRODUCIBLE。
    """

    return {
        "isolated_flag": 1,
        "no_user_site_flag": 1,
        "injected_absent_under_isolated": True,
        "injected_present_without_isolated": True,
        "python_isolated_mode": True,
        "ignores_ambient_env": True,
        "system_python_fallback_possible": False,
        "launch_interpreter": "absolute_pinned",
        "evidence_class": "STRUCTURAL_ONLY",
    }


# --------------------------------------------------------------------------- #
# sealed-input digest (OFFLINE_PROVEN, deterministic)
# --------------------------------------------------------------------------- #
def build_sealed_input(inputs_bytes: dict[str, bytes]) -> dict[str, Any]:
    """Build the sealed BUILD-INPUT block from a name→bytes map (deterministic).

    ``reproducible_output_verified`` 由 builder 補為 const false:封存的是「建置輸入」
    的 digest,產物位元一致性需 builder + CI,屬 DEFERRED。
    """

    if not inputs_bytes:
        raise ValueError("sealed_input requires at least one input")
    inputs = [
        {"ref": ref, "sha256": _sha256_bytes(data)}
        for ref, data in sorted(inputs_bytes.items())
    ]
    return {
        "sealed_input_digest": _canonical_digest(inputs),
        "inputs": inputs,
    }


def oci_sealed_input(base_digest: str, dockerfile_spec: bytes, lockfile: bytes) -> dict[str, Any]:
    """Sealed-input over the OCI *spec* bytes (digest-pinned FROM, lockfile, context).

    全為 design bytes:不 pull、不 build、不觸網;僅證明 digest-pinning + sealed-input
    的 digest 機制離線可重現。
    """

    return build_sealed_input({
        "dockerfile_spec": dockerfile_spec,
        "pinned_base_digest": base_digest.encode("utf-8"),
        "requirements_lock": lockfile,
        "build_context_manifest": b"runtime/ (COPY-only; no network RUN)",
    })


# --------------------------------------------------------------------------- #
# seam assembly
# --------------------------------------------------------------------------- #
def _seam(
    seam_id: str,
    verdict: str,
    note: str,
    detail: Any,
) -> dict[str, Any]:
    if verdict not in SEAM_VERDICTS:
        raise ValueError(f"unknown seam verdict: {verdict!r}")
    return {
        "seam_id": seam_id,
        "offline_evaluable": verdict != VERDICT_DEFERRED,
        "verdict": verdict,
        "evidence_class": VERDICT_TO_EVIDENCE[verdict],
        "detail_digest": _canonical_digest({"seam_id": seam_id, "verdict": verdict, "detail": detail}),
        "note": note,
    }


def _deferred_runtime_seams() -> list[dict[str, Any]]:
    notes = {
        "native_lib_loading_target": "loading Linux .so on the target arch/OS needs the host; Mac cannot",
        "cgroup_isolation": "cgroup / resource isolation only exists when the runtime runs on the host",
        "network_denial": "runtime network-denial can only be exercised on the target host",
        "start_stop_failure_cleanup": "start/stop/failure/cleanup lifecycle is a host-probe seam",
        "pg_identity_runtime": "PG identity at runtime is a host-probe seam (see S1.1 for the offline identity)",
    }
    return [
        _seam(seam_id, VERDICT_DEFERRED, notes[seam_id], {"deferred_to": "S1.6"})
        for seam_id in RUNTIME_ONLY_SEAMS
    ]


def build_candidate_seams(
    candidate_id: str,
    *,
    dependency_closure: dict[str, Any],
    isolation_mode: dict[str, Any],
    sealed_input: dict[str, Any],
    native_library_inventory: list[dict[str, Any]],
    oci_build: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Assemble the ordered, per-candidate seam list with honest verdicts.

    共通的離線機制(content-addressing 決定性、sealed-input digest、isolated-mode、
    native-lib inventory 雜湊)兩候選皆 OFFLINE_PROVEN;差別在:content-addressed
    fixed-path(B)以絕對路徑啟動 + 內容雜湊路徑,故 no-system-python-fallback 與
    non-relocatable 皆 OFFLINE_PROVEN;OCI(A)這兩者只能靠 image ENTRYPOINT / image-id
    不變性的 STRUCTURAL_DESIGN。exact_image_id_pin 為 OCI 專屬。五個 runtime seam 一律
    DEFERRED_S1_6。
    """

    is_oci = candidate_id == CANDIDATE_OCI
    seams: list[dict[str, Any]] = [
        _seam(
            "content_addressing_determinism", VERDICT_OFFLINE,
            "hashing the sealed inputs / bundle tree twice yields an identical digest (stdlib, offline)",
            {"closure_hash": dependency_closure["closure_hash"]},
        ),
        _seam(
            "sealed_build_input_digest", VERDICT_OFFLINE,
            "sealed BUILD-INPUT digest over pinned spec/lock bytes is deterministic and offline",
            {"sealed_input_digest": sealed_input["sealed_input_digest"]},
        ),
        _seam(
            "python_isolated_mode", VERDICT_OFFLINE,
            "python3 -I yields isolated=1/no_user_site=1 and ignores injected PYTHONPATH (host interp, run)",
            {
                "isolated_flag": isolation_mode.get("isolated_flag"),
                "no_user_site_flag": isolation_mode.get("no_user_site_flag"),
                "ignores_ambient_env": isolation_mode["ignores_ambient_env"],
            },
        ),
    ]

    if is_oci:
        seams.append(_seam(
            "no_system_python_fallback", VERDICT_STRUCTURAL,
            "image ENTRYPOINT pins an absolute interpreter; provable only when the image runs (design)",
            {"launch_interpreter": "absolute_pinned", "identity_kind": "exact_image_id"},
        ))
        seams.append(_seam(
            "non_relocatable_no_mutable_alias", VERDICT_STRUCTURAL,
            "an exact image ID is immutable by construction; pinned by digest, never a mutable tag (design)",
            {"identity_kind": "exact_image_id"},
        ))
    else:
        seams.append(_seam(
            "no_system_python_fallback", VERDICT_OFFLINE,
            "launch is <bundle>/bin/python3 -I by absolute pinned path (no PATH, no /usr/bin/python3)",
            {
                "launch_interpreter": isolation_mode["launch_interpreter"],
                "system_python_fallback_possible": isolation_mode["system_python_fallback_possible"],
            },
        ))
        seams.append(_seam(
            "non_relocatable_no_mutable_alias", VERDICT_OFFLINE,
            "the content-hash path is immutable by construction; no current/latest symlink alias",
            {"identity_kind": "content_addressed_path", "closure_hash": dependency_closure["closure_hash"]},
        ))

    # 空 inventory 無實際位元組可雜湊,不得謊稱 OFFLINE_PROVEN → 降為 STRUCTURAL_DESIGN。
    if native_library_inventory:
        seams.append(_seam(
            "native_lib_inventory_origin", VERDICT_OFFLINE,
            "native-lib inventory + origin hashing over the fixture is deterministic and offline",
            {"inventory": native_library_inventory},
        ))
    else:
        seams.append(_seam(
            "native_lib_inventory_origin", VERDICT_STRUCTURAL,
            "native-lib inventory is empty: no offline bytes to hash, structural-design only",
            {"inventory": native_library_inventory},
        ))

    if is_oci:
        seams.append(_seam(
            "exact_image_id_pin", VERDICT_STRUCTURAL,
            "an exact image ID is obtainable by build, but floor-only: no pull/build/network here "
            "(and colima is linux/arm64, no buildx, != target host)",
            {"oci_build": oci_build},
        ))

    seams.append(_seam(
        "rollback_bundle_shape", VERDICT_STRUCTURAL,
        "rollback re-pins a specific prior identity (image ID / content hash), never a mutable alias (design)",
        {"identity_kind": "exact_image_id" if is_oci else "content_addressed_path"},
    ))
    seams.append(_seam(
        "artifact_persistence_model", VERDICT_STRUCTURAL,
        "data persists outside the immutable image/bundle (external volume / fixed data path) (design)",
        {"model": "external_volume" if is_oci else "fixed_data_path"},
    ))
    seams.append(_seam(
        "real_ml_dep_closure_resolution", VERDICT_STRUCTURAL,
        "real LightGBM/sklearn/ONNX closure RESOLUTION needs a package index (network) — LR2 sealed-build",
        {"real_ml_closure_resolved": False},
    ))
    seams.append(_seam(
        "reproducible_output_bit_identity", VERDICT_STRUCTURAL,
        "reproducible OUTPUT bit-identity needs a builder + CI (nondeterministic layers/timestamps) — LR2/CI",
        {"reproducible_output_verified": False},
    ))

    seams.extend(_deferred_runtime_seams())

    # 完整性守衛:runtime-only seam 必為 DEFERRED_S1_6,否則視為結構破壞而 raise。
    verdict_by_id = {seam["seam_id"]: seam["verdict"] for seam in seams}
    for seam_id in RUNTIME_ONLY_SEAMS:
        if verdict_by_id.get(seam_id) != VERDICT_DEFERRED:
            raise RuntimeSeamClaimError(
                f"runtime-only seam {seam_id} must be DEFERRED_S1_6 at S1.4"
            )
    return seams


def _strongest_non_deferred_verdict(seams: list[dict[str, Any]]) -> str | None:
    non_deferred = [seam["verdict"] for seam in seams if seam["verdict"] != VERDICT_DEFERRED]
    if not non_deferred:
        return None
    if VERDICT_OFFLINE in non_deferred:
        return VERDICT_OFFLINE
    return VERDICT_STRUCTURAL


# --------------------------------------------------------------------------- #
# receipt builder
# --------------------------------------------------------------------------- #
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
        raise ValueError("platform must bind os/arch/python_version/container_runtime flags")
    runtime = platform.get("container_runtime")
    if runtime is not None and (not isinstance(runtime, str) or not runtime):
        raise ValueError("platform.container_runtime must be a non-empty string or null")
    return {
        "os": platform["os"],
        "arch": platform["arch"],
        "python_version": platform["python_version"],
        "container_runtime": runtime,
        "container_runtime_available": platform["container_runtime_available"],
        "buildx_available": platform["buildx_available"],
    }


def _isolation_block(isolation_mode: dict[str, Any]) -> dict[str, Any]:
    launch = isolation_mode.get("launch_interpreter")
    if launch not in {"absolute_pinned", "path_lookup"}:
        raise ValueError("isolation_mode.launch_interpreter is invalid")
    evidence = isolation_mode.get("evidence_class")
    if evidence not in EVIDENCE_CLASSES:
        raise ValueError("isolation_mode.evidence_class is invalid")
    return {
        "python_isolated_mode": bool(isolation_mode.get("python_isolated_mode")),
        "ignores_ambient_env": bool(isolation_mode.get("ignores_ambient_env")),
        "system_python_fallback_possible": bool(isolation_mode.get("system_python_fallback_possible")),
        "launch_interpreter": launch,
        "evidence_class": evidence,
    }


def build_runtime_candidate_receipt(
    *,
    caller: str,
    platform: dict[str, Any],
    candidate_id: str,
    target_class: str,
    dependency_closure: dict[str, Any],
    native_library_inventory: list[dict[str, Any]],
    isolation_mode: dict[str, Any],
    sealed_input: dict[str, Any],
    observation_time: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``runtime_candidate_receipt_v1``.

    ``status="PASS"`` iff ALL hold: ``target_class==disposable_offline``;
    the isolated-mode probe proved ``python_isolated_mode`` and
    ``ignores_ambient_env``; the strongest non-deferred seam is ``OFFLINE_PROVEN``
    (so at least one seam produced genuine local bytes) ⇒ receipt
    ``evidence_class==LOCAL_REPRODUCIBLE``; and every runtime-only seam is
    ``DEFERRED_S1_6``.  Integrity violations that cannot be safely serialized
    (secret detected, a runtime seam not deferred, ``target_host`` at the gate,
    ttl out of ``[1, 3600]``, unknown candidate) raise instead of emitting a
    receipt.  Otherwise ``status="FAIL"`` with a non-empty ``failure_reason``.
    """

    if not isinstance(caller, str) or not caller:
        raise ValueError("caller is required")
    if candidate_id not in CANDIDATE_IDS:
        raise ValueError(f"candidate_id is not recognized: {candidate_id!r}")
    if target_class not in TARGET_CLASSES:
        raise ValueError(f"target_class is not recognized: {target_class!r}")
    if target_class == "target_host":
        # target_host 屬 S1.6,離線無從評估 → fail-closed raise(不發 FAIL receipt)。
        raise TargetHostRejectedError(
            "S1.4 is disposable-offline; target_host is an S1.6 concern and is rejected fail-closed"
        )
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ValueError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise ValueError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")

    platform_block = _validate_platform(platform)
    isolation_block = _isolation_block(isolation_mode)
    observed = _parse_time(observation_time)
    expires = observed + timedelta(seconds=ttl_seconds)

    is_oci = candidate_id == CANDIDATE_OCI

    closure_hash = dependency_closure.get("closure_hash")
    if not DIGEST_RE.fullmatch(str(closure_hash)):
        raise ValueError("dependency_closure.closure_hash must be a sha256 digest")
    hashed_input_count = dependency_closure.get("hashed_input_count")
    if isinstance(hashed_input_count, bool) or not isinstance(hashed_input_count, int) or hashed_input_count < 0:
        raise ValueError("dependency_closure.hashed_input_count must be a non-negative integer")
    dependency_block = {
        "lock_tool": str(dependency_closure.get("lock_tool") or "stdlib_sha256_closure"),
        "lock_input_ref": str(dependency_closure.get("lock_input_ref") or "runtime_candidate_fixture_v1"),
        "closure_hash": closure_hash,
        "hashed_input_count": hashed_input_count,
        "real_ml_closure_resolved": False,
    }

    native_block = _normalize_native_inventory(native_library_inventory)

    sealed_digest = sealed_input.get("sealed_input_digest")
    if not DIGEST_RE.fullmatch(str(sealed_digest)):
        raise ValueError("sealed_input.sealed_input_digest must be a sha256 digest")
    sealed_block = {
        "sealed_input_digest": sealed_digest,
        "inputs": _normalize_sealed_inputs(sealed_input.get("inputs")),
        "reproducible_output_verified": False,
    }

    immutability_block = {
        "identity_kind": "exact_image_id" if is_oci else "content_addressed_path",
        "mutable_tag_or_alias": False,
        "relocatable_renamed_venv": False,
    }
    persistence_block = {
        "model": "external_volume" if is_oci else "fixed_data_path",
        "inside_immutable_image_or_bundle": False,
    }
    rollback_block = {
        "shape": "repin_prior_exact_image_id" if is_oci else "repin_prior_content_hash",
        "prior_identity_pinned": True,
        "mutable_current_symlink": False,
    }
    oci_build_block = _oci_build_block(platform_block) if is_oci else None

    seams = build_candidate_seams(
        candidate_id,
        dependency_closure=dependency_block,
        isolation_mode=isolation_mode,
        sealed_input=sealed_block,
        native_library_inventory=native_block,
        oci_build=oci_build_block,
    )

    strongest = _strongest_non_deferred_verdict(seams)
    evidence_class = "LOCAL_REPRODUCIBLE" if strongest == VERDICT_OFFLINE else "STRUCTURAL_ONLY"

    reasons: list[str] = []
    if not isolation_block["python_isolated_mode"]:
        reasons.append("python isolated-mode was not proven (isolated/no_user_site)")
    if not isolation_block["ignores_ambient_env"]:
        reasons.append("isolated mode did not ignore the injected ambient PYTHONPATH")
    if evidence_class != "LOCAL_REPRODUCIBLE":
        reasons.append("no seam produced genuine local bytes (evidence_class is not LOCAL_REPRODUCIBLE)")

    status = "PASS" if not reasons else "FAIL"
    failure_reason = None if status == "PASS" else "; ".join(reasons)

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "harness_id": HARNESS_ID,
        "status": status,
        "caller": caller,
        "platform": platform_block,
        "candidate": {"id": candidate_id, "kind": _candidate_kind(candidate_id)},
        "target_class": target_class,
        "evidence_class": evidence_class,
        "dependency_closure": dependency_block,
        "native_library_inventory": native_block,
        "isolation_mode": isolation_block,
        "sealed_input": sealed_block,
        "immutability": immutability_block,
        "artifact_persistence": persistence_block,
        "rollback": rollback_block,
        "oci_build": oci_build_block,
        "seams": seams,
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
    # 在計算 self_digest 前掃描整個 receipt(排除 secret_scan 自身)。
    _guard_no_secret({k: v for k, v in receipt.items() if k != "secret_scan"})
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


def _candidate_kind(candidate_id: str) -> str:
    if candidate_id == CANDIDATE_OCI:
        return "exact-image-ID-pinned OCI image (digest FROM, sealed build inputs)"
    return "content-addressed fixed-path runtime bundle (hash-named store path)"


def _oci_build_block(platform_block: dict[str, Any]) -> dict[str, Any]:
    # Floor-only:PM 裁定不 pull/不 build/不觸網,故 built=false、image_id=null。
    # buildx_multiarch / target_arch_match_verified 一律 const false(離線無從證明)。
    return {
        "builder": None,
        "built": False,
        "image_id": None,
        "image_platform": None,
        "buildx_multiarch": False,
        "target_arch_match_verified": False,
    }


def _normalize_native_inventory(inventory: Any) -> list[dict[str, Any]]:
    if inventory is None:
        return []
    if not isinstance(inventory, list):
        raise ValueError("native_library_inventory must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in inventory:
        if not isinstance(record, dict):
            raise ValueError("native library record must be an object")
        name = record.get("name")
        origin = record.get("origin")
        sha256 = record.get("sha256")
        if not isinstance(name, str) or not name:
            raise ValueError("native library record name is invalid")
        if name in seen:
            raise ValueError(f"duplicate native library record: {name!r}")
        seen.add(name)
        if not isinstance(origin, str) or not origin:
            raise ValueError("native library record origin is invalid")
        if not DIGEST_RE.fullmatch(str(sha256)):
            raise ValueError("native library record sha256 is invalid")
        normalized.append({
            "name": name,
            "origin": origin,
            "sha256": sha256,
            "load_verified_on_target": False,
        })
    return normalized


def _normalize_sealed_inputs(inputs: Any) -> list[dict[str, Any]]:
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("sealed_input.inputs must be a non-empty list")
    normalized: list[dict[str, Any]] = []
    for record in inputs:
        if not isinstance(record, dict):
            raise ValueError("sealed_input record must be an object")
        ref = record.get("ref")
        sha256 = record.get("sha256")
        if not isinstance(ref, str) or not ref:
            raise ValueError("sealed_input record ref is invalid")
        if not DIGEST_RE.fullmatch(str(sha256)):
            raise ValueError("sealed_input record sha256 is invalid")
        normalized.append({"ref": ref, "sha256": sha256})
    return normalized


# --------------------------------------------------------------------------- #
# receipt validator (structural + integrity; not execution authenticity)
# --------------------------------------------------------------------------- #
def validate_runtime_candidate_receipt(
    receipt: Any,
    *,
    require_success: bool = False,
    now: str | None = None,
) -> list[str]:
    """Validate receipt structure/integrity and the S1.4 disposable-offline gate.

    Schema subset、exact field-set、const identity、digest regexes、source/schema
    binding、per-seam verdict↔evidence 一致性、runtime-seam 全 DEFERRED_S1_6、const-false
    禁制(mutable tag/alias、relocatable venv、mutable current symlink、real ML closure、
    reproducible output、native-lib load)、secret-free 序列化、TTL/time ordering 與
    ``self_digest`` 重算。``target_class`` 必為 ``disposable_offline``;``target_host`` 拒。
    """

    if not isinstance(receipt, dict):
        return ["runtime candidate receipt must be an object"]
    schema = _receipt_schema()
    errors = [
        f"runtime candidate receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != RECEIPT_FIELDS:
        errors.append(
            "runtime candidate receipt fields mismatch: "
            f"missing={sorted(RECEIPT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - RECEIPT_FIELDS)}"
        )
    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        errors.append("runtime candidate receipt schema_version is invalid")
    if receipt.get("harness_id") != HARNESS_ID:
        errors.append("runtime candidate receipt harness_id is invalid")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        errors.append("runtime candidate receipt status is invalid")
    if receipt.get("target_class") != S1_TARGET_CLASS:
        errors.append(
            "runtime candidate receipt target_class must be disposable_offline "
            "(target_host is rejected at the S1.4 gate)"
        )
    candidate = receipt.get("candidate")
    if not isinstance(candidate, dict) or candidate.get("id") not in CANDIDATE_IDS:
        errors.append("runtime candidate receipt candidate.id is not recognized")

    for field_name in ("source_sha256", "schema_sha256", "self_digest"):
        if not DIGEST_RE.fullmatch(str(receipt.get(field_name, ""))):
            errors.append(f"runtime candidate receipt {field_name} is invalid")
    if receipt.get("source_sha256") != source_sha256():
        errors.append("runtime candidate receipt source_sha256 does not bind this module")
    if receipt.get("schema_sha256") != receipt_schema_sha256():
        errors.append("runtime candidate receipt schema_sha256 does not bind the schema")

    errors.extend(_validate_const_false_invariants(receipt))
    errors.extend(_validate_seams(receipt))
    errors.extend(_validate_oci_build(receipt))
    errors.extend(_validate_secret_scan(receipt))
    errors.extend(_validate_times(receipt, now=now))

    status = receipt.get("status")
    failure_reason = receipt.get("failure_reason")
    seams = receipt.get("seams") if isinstance(receipt.get("seams"), list) else []
    has_offline_seam = any(
        isinstance(seam, dict) and seam.get("verdict") == VERDICT_OFFLINE for seam in seams
    )
    evidence_class = receipt.get("evidence_class")
    # 一致性:LOCAL_REPRODUCIBLE ⟺ 至少一個 OFFLINE_PROVEN seam(真有本機位元組)。
    if evidence_class == "LOCAL_REPRODUCIBLE" and not has_offline_seam:
        errors.append("evidence_class LOCAL_REPRODUCIBLE requires at least one OFFLINE_PROVEN seam")
    if evidence_class == "STRUCTURAL_ONLY" and has_offline_seam:
        errors.append("evidence_class STRUCTURAL_ONLY contradicts an OFFLINE_PROVEN seam")

    if status == "PASS":
        if evidence_class != "LOCAL_REPRODUCIBLE":
            errors.append("PASS receipt requires evidence_class LOCAL_REPRODUCIBLE")
        if failure_reason is not None:
            errors.append("PASS receipt cannot carry a failure_reason")
        isolation = receipt.get("isolation_mode")
        if isinstance(isolation, dict):
            if isolation.get("python_isolated_mode") is not True:
                errors.append("PASS receipt requires python_isolated_mode true")
            if isolation.get("ignores_ambient_env") is not True:
                errors.append("PASS receipt requires ignores_ambient_env true")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAIL receipt requires a non-empty failure_reason")

    if require_success and status != "PASS":
        errors.append("runtime candidate receipt does not prove a passing candidate")
    if receipt.get("self_digest") != receipt_digest(receipt):
        errors.append("runtime candidate receipt self_digest does not match canonical receipt")
    return errors


def _validate_const_false_invariants(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dependency = receipt.get("dependency_closure")
    if isinstance(dependency, dict) and dependency.get("real_ml_closure_resolved") is not False:
        errors.append("dependency_closure.real_ml_closure_resolved must be false at S1.4")
    sealed = receipt.get("sealed_input")
    if isinstance(sealed, dict) and sealed.get("reproducible_output_verified") is not False:
        errors.append("sealed_input.reproducible_output_verified must be false at S1.4")
    immutability = receipt.get("immutability")
    if isinstance(immutability, dict):
        if immutability.get("mutable_tag_or_alias") is not False:
            errors.append("immutability.mutable_tag_or_alias must be false (plan §LR0C line 272)")
        if immutability.get("relocatable_renamed_venv") is not False:
            errors.append("immutability.relocatable_renamed_venv must be false (plan §LR0C line 272)")
    persistence = receipt.get("artifact_persistence")
    if isinstance(persistence, dict) and persistence.get("inside_immutable_image_or_bundle") is not False:
        errors.append("artifact_persistence.inside_immutable_image_or_bundle must be false")
    rollback = receipt.get("rollback")
    if isinstance(rollback, dict) and rollback.get("mutable_current_symlink") is not False:
        errors.append("rollback.mutable_current_symlink must be false (no mutable current/latest alias)")
    inventory = receipt.get("native_library_inventory")
    if isinstance(inventory, list):
        for record in inventory:
            if isinstance(record, dict) and record.get("load_verified_on_target") is not False:
                errors.append("native_library_inventory load_verified_on_target must be false (loading DEFERRED)")
                break
    return errors


def _validate_seams(receipt: dict[str, Any]) -> list[str]:
    seams = receipt.get("seams")
    if not isinstance(seams, list) or not seams:
        return ["runtime candidate receipt seams are missing"]
    errors: list[str] = []
    seen: set[str] = set()
    verdict_by_id: dict[str, str] = {}
    for seam in seams:
        if not isinstance(seam, dict):
            errors.append("runtime candidate seam record is invalid")
            continue
        seam_id = seam.get("seam_id")
        verdict = seam.get("verdict")
        evidence = seam.get("evidence_class")
        if not isinstance(seam_id, str) or not seam_id:
            errors.append("runtime candidate seam_id is invalid")
            continue
        if seam_id in seen:
            errors.append(f"runtime candidate duplicate seam: {seam_id}")
        seen.add(seam_id)
        verdict_by_id[seam_id] = verdict
        if verdict not in SEAM_VERDICTS:
            errors.append(f"runtime candidate seam verdict is invalid: {seam_id}")
            continue
        # verdict↔evidence_class 必嚴格對應,防止把 DEFERRED 偽裝成 LOCAL_REPRODUCIBLE。
        if evidence != VERDICT_TO_EVIDENCE[verdict]:
            errors.append(f"runtime candidate seam evidence_class inconsistent with verdict: {seam_id}")
        if seam.get("offline_evaluable") is not (verdict != VERDICT_DEFERRED):
            errors.append(f"runtime candidate seam offline_evaluable inconsistent with verdict: {seam_id}")
        if not DIGEST_RE.fullmatch(str(seam.get("detail_digest", ""))):
            errors.append(f"runtime candidate seam detail_digest is invalid: {seam_id}")
    # 五個 runtime-only seam 必到齊且皆 DEFERRED_S1_6(離線不可能證明 runtime seam)。
    for seam_id in RUNTIME_ONLY_SEAMS:
        if seam_id not in verdict_by_id:
            errors.append(f"runtime candidate receipt is missing runtime seam: {seam_id}")
        elif verdict_by_id[seam_id] != VERDICT_DEFERRED:
            errors.append(
                f"runtime seam {seam_id} must be DEFERRED_S1_6 (a runtime seam cannot be proven offline)"
            )
    # 封閉集守衛(鏡射 RECEIPT_FIELDS 檢查):seam-id 集合須與該候選的預期完全一致。
    # 否則偽造 receipt 可在未列 id(或尾隨空白等同形異義)下夾帶額外 OFFLINE_PROVEN seam,
    # 對 runtime-only 能力捏造離線偽證——正是 S1.4 禁止之事。
    candidate = receipt.get("candidate")
    candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
    expected = EXPECTED_SEAMS.get(candidate_id)
    if expected is not None and seen != expected:
        errors.append(
            "runtime candidate receipt seam-id set mismatch: "
            f"missing={sorted(expected - seen)} extra={sorted(seen - expected)}"
        )
    return errors


def _validate_oci_build(receipt: dict[str, Any]) -> list[str]:
    candidate = receipt.get("candidate")
    candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
    oci_build = receipt.get("oci_build")
    errors: list[str] = []
    if candidate_id == CANDIDATE_FIXED_PATH:
        if oci_build is not None:
            errors.append("content_addressed_fixed_path receipt must carry oci_build=null")
        return errors
    if candidate_id == CANDIDATE_OCI:
        if not isinstance(oci_build, dict):
            errors.append("exact_image_id_oci receipt requires an oci_build block")
            return errors
        if oci_build.get("buildx_multiarch") is not False:
            errors.append("oci_build.buildx_multiarch must be false (no buildx cross-build offline)")
        if oci_build.get("target_arch_match_verified") is not False:
            errors.append("oci_build.target_arch_match_verified must be false (target arch unknown at S1.4)")
        built = oci_build.get("built")
        image_id = oci_build.get("image_id")
        if built is True and not (isinstance(image_id, str) and image_id):
            errors.append("oci_build claims built=true but has no image_id")
        if built is False and image_id is not None:
            errors.append("oci_build built=false must not carry an image_id")
    return errors


def _validate_secret_scan(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    secret_scan = receipt.get("secret_scan")
    if not isinstance(secret_scan, dict):
        return ["runtime candidate receipt secret_scan is missing"]
    if secret_scan.get("leaked") is not False:
        errors.append("runtime candidate secret_scan must report leaked=false")
    if list(secret_scan.get("patterns_checked", [])) != list(SECRET_PATTERNS_CHECKED):
        errors.append("runtime candidate secret_scan patterns are not the exact contract")
    if _contains_secret_like({k: v for k, v in receipt.items() if k != "secret_scan"}):
        errors.append("runtime candidate receipt carries secret-like content")
    return errors


def _validate_times(receipt: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    ttl_seconds = receipt.get("ttl_seconds")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        return ["runtime candidate receipt ttl_seconds is invalid"]
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        errors.append(f"runtime candidate ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    try:
        observed = _parse_time(str(receipt.get("observation_time", "")))
        expires = _parse_time(str(receipt.get("expires_at", "")))
        if expires != observed + timedelta(seconds=ttl_seconds):
            errors.append("runtime candidate expires_at does not equal observation_time + ttl")
        if not observed < expires:
            errors.append("runtime candidate observation_time must precede expires_at")
        if now is not None:
            current = _parse_time(now)
            if not observed <= current < expires:
                errors.append("runtime candidate receipt is not fresh")
    except (TypeError, ValueError):
        errors.append("runtime candidate receipt timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# preliminary comparison (non-binding; final_choice const null)
# --------------------------------------------------------------------------- #
def build_runtime_candidate_comparison(
    receipt_a: dict[str, Any],
    receipt_b: dict[str, Any],
    *,
    observation_time: str,
    ttl_seconds: int,
    preliminary_lean: str | None = None,
) -> dict[str, Any]:
    """Build the preliminary ``runtime_candidate_comparison_v1`` (final_choice=null).

    綁定兩張 candidate receipt 的 ``self_digest``、逐 seam A/B verdict 矩陣、
    ``deferred_to_s1_6`` 與一段**明示非綁定**的 ``preliminary_lean``,並顯性記錄
    ``candidate_status``(各候選的 PASS/FAIL)——FAIL 候選不得被悄悄呈現為已評估;
    但這**不**硬性要求 PASS:合法失敗的候選應可見而非被拒。
    ``final_choice`` 為 const ``null``:S1.4 結構上不做選擇。若任一 receipt 無法通過
    自身 validator,或候選身分不符(A=OCI、B=fixed-path),即 raise。
    """

    a_errors = validate_runtime_candidate_receipt(receipt_a)
    b_errors = validate_runtime_candidate_receipt(receipt_b)
    if a_errors:
        raise ValueError(f"candidate A receipt is invalid: {a_errors[:3]}")
    if b_errors:
        raise ValueError(f"candidate B receipt is invalid: {b_errors[:3]}")
    if receipt_a["candidate"]["id"] != CANDIDATE_OCI:
        raise ValueError("receipt_a must be the exact_image_id_oci candidate")
    if receipt_b["candidate"]["id"] != CANDIDATE_FIXED_PATH:
        raise ValueError("receipt_b must be the content_addressed_fixed_path candidate")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ValueError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise ValueError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    if preliminary_lean is not None and (not isinstance(preliminary_lean, str) or not preliminary_lean):
        raise ValueError("preliminary_lean must be a non-empty string or null")

    observed = _parse_time(observation_time)
    expires = observed + timedelta(seconds=ttl_seconds)

    a_verdicts = {seam["seam_id"]: seam["verdict"] for seam in receipt_a["seams"]}
    b_verdicts = {seam["seam_id"]: seam["verdict"] for seam in receipt_b["seams"]}
    all_seam_ids = sorted(set(a_verdicts) | set(b_verdicts), key=_seam_matrix_sort_key)
    seam_matrix = [
        {
            "seam_id": seam_id,
            "a_verdict": a_verdicts.get(seam_id, "N_A"),
            "b_verdict": b_verdicts.get(seam_id, "N_A"),
            "decisive_at": SEAM_DECISIVE_AT.get(seam_id, "S1.6"),
        }
        for seam_id in all_seam_ids
    ]

    lean = preliminary_lean or (
        "offline evidence is thicker for content_addressed_fixed_path (no_system_python_fallback "
        "and non_relocatable are OFFLINE_PROVEN, vs STRUCTURAL_DESIGN for OCI), but candidate A's "
        "decisive strengths (kernel/cgroup isolation, single-digest identity) live in the "
        "DEFERRED_S1_6 seams; both remain viable-pending-S1.6. NON-BINDING — not a selection."
    )

    comparison: dict[str, Any] = {
        "schema_version": COMPARISON_SCHEMA_VERSION,
        "harness_id": HARNESS_ID,
        "candidate_a_digest": receipt_a["self_digest"],
        "candidate_b_digest": receipt_b["self_digest"],
        # 顯性記錄各候選 status:FAIL 候選不得被悄悄呈現為「兩者皆已評估」。
        "candidate_status": {"a": receipt_a["status"], "b": receipt_b["status"]},
        "seam_matrix": seam_matrix,
        "deferred_to_s1_6": list(RUNTIME_ONLY_SEAMS),
        "preliminary_lean": lean,
        "final_choice": None,
        "source_sha256": source_sha256(),
        "schema_sha256": comparison_schema_sha256(),
        "observation_time": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "ttl_seconds": ttl_seconds,
    }
    _guard_no_secret(comparison)
    comparison["self_digest"] = comparison_digest(comparison)
    return comparison


def _seam_matrix_sort_key(seam_id: str) -> tuple[int, str]:
    # 依裁決層級(S1.4 → LR2 → S1.6)再字典序排,矩陣可讀且可重現。
    order = {"S1.4": 0, "LR2": 1, "S1.6": 2}
    return (order.get(SEAM_DECISIVE_AT.get(seam_id, "S1.6"), 3), seam_id)


def validate_runtime_candidate_comparison(
    comparison: Any,
    *,
    now: str | None = None,
    receipt_a: dict[str, Any] | None = None,
    receipt_b: dict[str, Any] | None = None,
) -> list[str]:
    """Validate the comparison's structure/integrity and the const-null guarantee.

    ``candidate_status`` 必為 ``{a,b}→PASS/FAIL`` 之對映(FAIL 候選須顯性可見,不得被
    隱藏成「兩者皆已評估」)。若傳入對應 ``receipt_a``/``receipt_b``,額外交叉核對
    記錄的 digest 與 status 皆與真實 receipt 相符。
    """

    if not isinstance(comparison, dict):
        return ["runtime candidate comparison must be an object"]
    schema = _comparison_schema()
    errors = [
        f"runtime candidate comparison schema violation: {error}"
        for error in schema_subset_errors(comparison, schema, schema)
    ]
    if set(comparison) != COMPARISON_FIELDS:
        errors.append(
            "runtime candidate comparison fields mismatch: "
            f"missing={sorted(COMPARISON_FIELDS - set(comparison))} "
            f"extra={sorted(set(comparison) - COMPARISON_FIELDS)}"
        )
    if comparison.get("schema_version") != COMPARISON_SCHEMA_VERSION:
        errors.append("runtime candidate comparison schema_version is invalid")
    if comparison.get("harness_id") != HARNESS_ID:
        errors.append("runtime candidate comparison harness_id is invalid")
    # 核心保證:final_choice 必為 None——S1.4 結構上不做選擇。
    if comparison.get("final_choice") is not None:
        errors.append("runtime candidate comparison final_choice must be null (S1.4 cannot select)")
    for field_name in ("candidate_a_digest", "candidate_b_digest", "source_sha256", "schema_sha256", "self_digest"):
        if not DIGEST_RE.fullmatch(str(comparison.get(field_name, ""))):
            errors.append(f"runtime candidate comparison {field_name} is invalid")
    if comparison.get("source_sha256") != source_sha256():
        errors.append("runtime candidate comparison source_sha256 does not bind this module")
    if comparison.get("schema_sha256") != comparison_schema_sha256():
        errors.append("runtime candidate comparison schema_sha256 does not bind the schema")

    # candidate_status 必為 {a,b}→PASS/FAIL 之對映;FAIL 候選顯性可見而非隱形。
    status_map = comparison.get("candidate_status")
    if (
        not isinstance(status_map, dict)
        or set(status_map) != {"a", "b"}
        or status_map.get("a") not in {"PASS", "FAIL"}
        or status_map.get("b") not in {"PASS", "FAIL"}
    ):
        errors.append("runtime candidate comparison candidate_status must map a/b to PASS/FAIL")
    else:
        # 若提供對應 receipt,交叉核對:記錄的 digest 與 status 皆須與真實 receipt 相符。
        for role, receipt, digest_field in (
            ("a", receipt_a, "candidate_a_digest"),
            ("b", receipt_b, "candidate_b_digest"),
        ):
            if isinstance(receipt, dict):
                if comparison.get(digest_field) != receipt.get("self_digest"):
                    errors.append(
                        f"runtime candidate comparison {digest_field} does not bind the provided receipt"
                    )
                if status_map.get(role) != receipt.get("status"):
                    errors.append(
                        f"runtime candidate comparison candidate_status.{role} does not match the receipt status"
                    )

    deferred = comparison.get("deferred_to_s1_6")
    if list(deferred or []) != list(RUNTIME_ONLY_SEAMS):
        errors.append("runtime candidate comparison deferred_to_s1_6 must be the exact runtime-seam list")

    matrix = comparison.get("seam_matrix")
    if isinstance(matrix, list):
        for row in matrix:
            if not isinstance(row, dict):
                errors.append("runtime candidate comparison seam_matrix row is invalid")
                continue
            for key in ("a_verdict", "b_verdict"):
                if row.get(key) not in (SEAM_VERDICTS | {"N_A"}):
                    errors.append(f"runtime candidate comparison seam_matrix {key} is invalid")
            if row.get("decisive_at") not in {"S1.4", "LR2", "S1.6"}:
                errors.append("runtime candidate comparison seam_matrix decisive_at is invalid")
    else:
        errors.append("runtime candidate comparison seam_matrix is missing")

    errors.extend(_validate_comparison_times(comparison, now=now))
    if _contains_secret_like(comparison):
        errors.append("runtime candidate comparison carries secret-like content")
    if comparison.get("self_digest") != comparison_digest(comparison):
        errors.append("runtime candidate comparison self_digest does not match canonical comparison")
    return errors


def _validate_comparison_times(comparison: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    ttl_seconds = comparison.get("ttl_seconds")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        return ["runtime candidate comparison ttl_seconds is invalid"]
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        errors.append(f"runtime candidate comparison ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    try:
        observed = _parse_time(str(comparison.get("observation_time", "")))
        expires = _parse_time(str(comparison.get("expires_at", "")))
        if expires != observed + timedelta(seconds=ttl_seconds):
            errors.append("runtime candidate comparison expires_at does not equal observation_time + ttl")
        if not observed < expires:
            errors.append("runtime candidate comparison observation_time must precede expires_at")
        if now is not None:
            current = _parse_time(now)
            if not observed <= current < expires:
                errors.append("runtime candidate comparison is not fresh")
    except (TypeError, ValueError):
        errors.append("runtime candidate comparison timestamps are invalid")
    return errors

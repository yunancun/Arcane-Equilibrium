"""Sealed-build + expected-identity binder for AIML LR2 (S2.3).

This module is the thin *sealing + binding* layer over the landed S1 slices for
the runtime that S1.6 chose — ``content_addressed_fixed_path`` (NOT OCI).  It has
two jobs, both **source + build-verification only** (S2.3 is ``NONE``-effect):

1. Turn the fully-resolved, hash-pinned Linux dependency closure
   (``requirements-ml.lock``, produced once by ``uv pip compile --generate-hashes``)
   into one canonical self-hashed ``sealed_build_receipt_v1``.  It flips the three
   deferred S1.4 consts truthfully: ``dependency_closure.real_ml_closure_resolved``
   is now ``true`` (the real closure resolved), ``sealed_input.reproducible_output_verified``
   is ``true`` (deterministic closure digest), and the launch contract is proven at
   the ``absolute_pinned`` / ``python_isolated_mode`` level.  ``load_verified_on_target``
   stays const ``false`` — loading Linux ``.so`` on the target host is S2.5/LR6,
   and installing is S2.4.

2. Project (BIND) the S1.3 least-privilege identity/ACL matrix onto the sealed
   build as one canonical self-hashed ``expected_identity_receipt_v1``.  It does
   **not** re-derive the identity topology — it re-uses S1.3's
   ``canonical_identity_acl_contract`` and ``OVER_GRANT_KINDS`` verbatim, so the
   receipt binds to S1.3 by construction.  Every ``production_*`` and
   ``running_attested.*`` flag is const ``false``; provisioning is S2.4 and running
   attestation is S2.5/LR6 (``observation_owner`` const ``S2.5_LR6``).

Like S1.1/S1.3/S1.4/S1.6, this module self-validates its own receipts and
deliberately does NOT register into the central AIML closure-validator, the
governance registry, the route-compiler, permissions, or the vocabulary; S2.3
stays disjoint (central registration is a separate serialized PM follow-up).  It
reuses ``canonical_digest`` / ``artifact_self_digest`` from the central validator
(imported, never reimplemented) and ``schema_subset_errors`` from
``agent_governance_schema``.  The emit + validate path is pure stdlib: NO pip,
NO network, NO subprocess — the network happened exactly once, offline of this
module, to produce the committed ``requirements-ml.lock``.

Evidence-authenticity honesty (CLAUDE §四): a ``LOCAL_REPRODUCIBLE`` sealed-build
receipt's ``closure_hash`` / ``runtime_content_digest`` prove the *lock bytes* are a
deterministic, fully-hashed closure; they do NOT prove the wheels were installed,
imported, or that the ``.so`` loaded on the Linux target.  That is the CI
``learning-runtime-sealed-build`` job (real offline install + import) and S2.5's
running attestation.  A self-hashed receipt authenticates integrity only, never
execution.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
_HELPER_DIR = SOURCE_PATH.parent
_ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _dir in (str(_HELPER_DIR), str(_ML_TRAINING_DIR)):
    if _dir not in sys.path:
        sys.path.insert(0, _dir)

# 重用中央 validator 的 canonical digest / self-hash(禁重實作;不新增雜湊抽象)。
from aiml_gate_receipt_validator import artifact_self_digest, canonical_digest  # noqa: E402
from agent_governance_schema import schema_subset_errors  # noqa: E402
# S1.3 身分/ACL 契約:expected-identity receipt 以「投影(bind)」方式重用它,絕不 re-derive。
import agent_governance_identity_acl_contract as _s1_3  # noqa: E402


ADAPTER_ID = "sealed_build_adapter_v1"
SEALED_SCHEMA_VERSION = "sealed_build_receipt_v1"
EXPECTED_IDENTITY_SCHEMA_VERSION = "expected_identity_receipt_v1"

SCHEMA_DIR = REPO_ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
SEALED_SCHEMA_PATH = SCHEMA_DIR / "sealed_build_receipt_v1.schema.json"
EXPECTED_IDENTITY_SCHEMA_PATH = SCHEMA_DIR / "expected_identity_receipt_v1.schema.json"
# S1.6 runtime-choice receipt 為 disposable/uncommitted(未被任何 committed rollup 收錄),
# 故其 digest 綁定退回「committed schema 身分」層級(可離線重算、可審計)。
LEARNING_RUNTIME_CHOICE_SCHEMA_PATH = SCHEMA_DIR / "learning_runtime_choice_receipt_v1.schema.json"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
TTL_CEILING_SECONDS = 3600
PLATFORM_OS = frozenset({"darwin", "linux"})

# S1.6 選定的 runtime,以及本 receipt 面向的 Linux 目標平台(uv --python-platform 語彙)。
SELECTED_RUNTIME_KIND = "content_addressed_fixed_path"
TARGET_PLATFORM = "x86_64-unknown-linux-gnu"
TARGET_PYTHON_VERSION = "3.12"

# 產鎖工具身分(供 lock_tool 欄位;本機 uv 版本)。
LOCK_TOOL = "uv 0.11.26"
# 直接依賴檔(closure 的 top-level 種子);lock 的 real 產物由此解析。
SPEC_INPUT_REF = "requirements-ml.txt"
LOCK_INPUT_REF = "requirements-ml.lock"

# LR2 sealed-build 面向的 5 個學習元件(對齊 S1.3 §LR3 分組;fit/evaluation 合為單一身分)。
SEALED_COMPONENTS = _s1_3.COMPONENTS  # (engine_scanner, controller, fit_evaluation, serving, deleter)

# 具備原生 .so / 編譯產物的套件白名單:native_library_inventory 只投影 closure 中屬此集合者。
# 真實載入(dlopen)/目標架相符為 S2.5/LR6,故 load_verified_on_target 一律 const false。
NATIVE_PACKAGES = frozenset({
    "lightgbm", "scikit-learn", "scipy", "numpy", "onnx", "onnxruntime",
    "pyarrow", "duckdb", "llvmlite", "ml-dtypes", "numba", "psycopg-binary",
})

# --------------------------------------------------------------------------- #
# 真實 committed S1 lineage digest(綁定來源見各常量註解)。
# --------------------------------------------------------------------------- #
# S1.3 identity_acl_contract receipt 的真實 self_digest,取自 committed S1.5
# effect_seams_ready_receipt.json 的 dependency_receipts.identity_acl_contract_receipt_digest。
S1_3_IDENTITY_ACL_RECEIPT_DIGEST = (
    "sha256:fdb623c574c3e16232af51e534d2e4c17bb1d3abf748ae0ba5ff7f772f6fead3"
)
# S1.4 candidate B(content_addressed_fixed_path)receipt 的真實 self_digest,同一 committed
# S1.5 rollup 的 dependency_receipts.runtime_candidate_receipt_b_digest。
S1_4_RUNTIME_CANDIDATE_B_DIGEST = (
    "sha256:3e5562b5632d1795ce498b601a54c520ffaf59151268bab5b7d404a46deca140"
)

# 沿用 S1.1/S1.4 的機密掃描樣態(github token / auth header / credential 賦值 / provider secret)。
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

SEALED_RECEIPT_FIELDS = frozenset({
    "schema_version",
    "adapter_id",
    "status",
    "caller",
    "platform",
    "closure_hash",
    "runtime_content_digest",
    "lock_tool",
    "lock_input_ref",
    "dependency_closure",
    "sealed_input",
    "launch",
    "native_library_inventory",
    "boundary",
    "learning_runtime_choice_receipt_digest",
    "runtime_candidate_receipt_b_digest",
    "source_sha256",
    "schema_sha256",
    "secret_scan",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "failure_reason",
    "self_digest",
})

EXPECTED_IDENTITY_RECEIPT_FIELDS = frozenset({
    "schema_version",
    "adapter_id",
    "status",
    "caller",
    "platform",
    "sealed_build_digest",
    "runtime_content_digest",
    "identity_acl_contract_digest",
    "expected_component_identities",
    "least_privilege_assertions",
    "negative_acl_binding",
    "secret_loading_binding",
    "rollback_binding",
    "production_provisioned",
    "running_attested",
    "observation_owner",
    "source_sha256",
    "schema_sha256",
    "secret_scan",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "failure_reason",
    "self_digest",
})

# lock 內部依賴解析的固定投影欄位(closure_hash / 統計 的單一真相來源)。
_REQUIREMENT_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(==|>=|<=|~=|!=|>|<)\s*([^\s;\\]+)")
_HASH_RE = re.compile(r"--hash=sha256:([0-9a-f]{64})")
_VIA_INLINE_RE = re.compile(r"^\s+#\s*via\s+(\S.*)$")
_VIA_HEADER_RE = re.compile(r"^\s+#\s*via\s*$")
_VIA_CONT_RE = re.compile(r"^\s+#\s+(\S.*)$")


class SecretLeakageError(RuntimeError):
    """Raised when a would-be receipt field carries secret-like content (fail-closed)."""


class LockClosureError(RuntimeError):
    """Raised when the dependency lock is not a fully-resolved, hash-pinned closure.

    S2.3 refuses to seal (never emits a receipt claiming ``real_ml_closure_resolved``)
    for a lock with any unpinned / unhashed entry, a missing top-level requirement, or
    a broken transitive closure — that would forge the truthfulness of the flipped
    S1.4 consts.
    """


# --------------------------------------------------------------------------- #
# digest helpers — canonical_digest/artifact_self_digest are IMPORTED (not
# reimplemented).  Only the raw-file-bytes sha256 (for source/schema binding) is
# local, exactly as every sibling receipt module binds source_sha256/schema_sha256.
# --------------------------------------------------------------------------- #
def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this module source."""

    return _file_sha256(SOURCE_PATH)


@lru_cache(maxsize=1)
def sealed_schema_sha256() -> str:
    return _file_sha256(SEALED_SCHEMA_PATH)


@lru_cache(maxsize=1)
def expected_identity_schema_sha256() -> str:
    return _file_sha256(EXPECTED_IDENTITY_SCHEMA_PATH)


@lru_cache(maxsize=1)
def learning_runtime_choice_schema_sha256() -> str:
    """Schema-level binding for the disposable/uncommitted S1.6 runtime-choice receipt."""

    return _file_sha256(LEARNING_RUNTIME_CHOICE_SCHEMA_PATH)


@lru_cache(maxsize=1)
def _sealed_schema() -> dict[str, Any]:
    return json.loads(SEALED_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _expected_identity_schema() -> dict[str, Any]:
    return json.loads(EXPECTED_IDENTITY_SCHEMA_PATH.read_text(encoding="utf-8"))


def receipt_digest(receipt: dict[str, Any]) -> str:
    """Self-hash a receipt via the central validator's artifact_self_digest (excludes self_digest)."""

    return artifact_self_digest(receipt)


# --------------------------------------------------------------------------- #
# secret scan (fail-closed, mirror S1.1/S1.4)
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
# lock-closure verifier (the load-bearing S2.3 check)
# --------------------------------------------------------------------------- #
def _normalize_name(name: str) -> str:
    # PEP 503 正規化:大小寫、-_. 皆等價。
    return re.sub(r"[-_.]+", "-", name.strip().lower())


def _parse_spec_direct_names(spec_path: Path) -> list[str]:
    names: list[str] = []
    for raw in spec_path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?", line)
        if match:
            names.append(_normalize_name(match.group(1)))
    return names


def _parse_lock_entries(lock_path: Path) -> tuple[dict[str, dict[str, Any]], int]:
    """Parse a ``uv pip compile --generate-hashes`` lock into name -> {version, hashes, via}.

    回傳 ``(entries, unpinned_count)``。``unpinned_count`` = 任何 requirement 行使用非
    ``==`` specifier 的數量(uv 只出 ``==``,故正常為 0;非 0 即拒絕 seal)。
    """

    entries: dict[str, dict[str, Any]] = {}
    unpinned_count = 0
    current: str | None = None
    in_via = False
    for raw in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\n")
        if line.startswith("#"):
            # 檔頭 col-0 註解(含產鎖命令列)——跳過。
            continue
        req = _REQUIREMENT_RE.match(line)
        if req:
            operator = req.group(2)
            if operator != "==":
                unpinned_count += 1
            name = _normalize_name(req.group(1))
            entries[name] = {"version": req.group(3), "hashes": [], "via": [], "pinned": operator == "=="}
            current = name
            in_via = False
            continue
        hash_match = _HASH_RE.search(line)
        if hash_match and current is not None:
            entries[current]["hashes"].append(hash_match.group(1))
            in_via = False
            continue
        inline_via = _VIA_INLINE_RE.match(line)
        if inline_via and current is not None:
            entries[current]["via"].append(inline_via.group(1).strip())
            in_via = True
            continue
        if _VIA_HEADER_RE.match(line) and current is not None:
            in_via = True
            continue
        cont_via = _VIA_CONT_RE.match(line)
        if in_via and cont_via and current is not None:
            entries[current]["via"].append(cont_via.group(1).strip())
            continue
        in_via = False
    return entries, unpinned_count


def _via_parents(via_labels: list[str]) -> list[str]:
    # uv 的 ``# via X`` 記錄「誰把此套件拉進來」(parents);``-r <file>`` 視為 root 種子。
    parents: list[str] = []
    for label in via_labels:
        token = label.strip()
        if not token:
            continue
        if token.startswith("-r") or "requirements" in token.lower():
            parents.append("__root__")
            continue
        parents.append(_normalize_name(re.sub(r"\s+", "", token)))
    return parents


def verify_lock_closure(lock_path: str | Path, spec_path: str | Path) -> dict[str, Any]:
    """Verify + digest a hash-pinned dependency closure; RAISE fail-closed on any gap.

    Asserts: 0 unpinned/``>=`` entries, every entry carries ≥1 sha256, all top-level
    (direct) spec names present, and transitive completeness — every ``# via`` parent
    resolves to a present entry (closure closed) and no non-direct entry is orphaned
    (each was pulled in by something).  Returns a deterministic closure summary with
    ``closure_hash = canonical_digest(sorted (name, version, sorted(hashes)) tuples)``.
    """

    lock_path = Path(lock_path)
    spec_path = Path(spec_path)
    if not lock_path.is_file():
        raise LockClosureError(f"lock file is absent: {lock_path}")
    if not spec_path.is_file():
        raise LockClosureError(f"spec file is absent: {spec_path}")

    direct = _parse_spec_direct_names(spec_path)
    entries, unpinned_count = _parse_lock_entries(lock_path)

    errors: list[str] = []
    if not entries:
        raise LockClosureError("lock has no resolved entries")
    if unpinned_count != 0:
        errors.append(f"lock has {unpinned_count} unpinned (non ==) requirement(s)")
    for name, entry in sorted(entries.items()):
        if not entry["pinned"]:
            errors.append(f"entry {name!r} is not pinned to an exact version")
        if not entry["hashes"]:
            errors.append(f"entry {name!r} has no sha256 hash")
    missing_direct = [name for name in direct if name not in entries]
    if missing_direct:
        errors.append(f"top-level requirements missing from lock: {sorted(missing_direct)}")

    # transitive completeness:closure 須在「depends-on」關係下封閉,且無孤兒。
    missing_parents: set[str] = set()
    orphans: list[str] = []
    direct_set = set(direct)
    for name, entry in entries.items():
        parents = _via_parents(entry["via"])
        for parent in parents:
            if parent != "__root__" and parent not in entries:
                missing_parents.add(parent)
        if name not in direct_set and not parents:
            orphans.append(name)
    if missing_parents:
        errors.append(f"transitive closure not closed (missing via-parents): {sorted(missing_parents)}")
    if orphans:
        errors.append(f"orphan entries (non-direct, no via provenance): {sorted(orphans)}")

    if errors:
        raise LockClosureError("; ".join(errors))

    projected = [
        {"name": name, "version": entry["version"], "hashes": sorted(entry["hashes"])}
        for name, entry in sorted(entries.items())
    ]
    closure_tuples = [[item["name"], item["version"], item["hashes"]] for item in projected]
    return {
        "closure_hash": canonical_digest(closure_tuples),
        "entries_total": len(entries),
        "hashed_entries_total": sum(1 for entry in entries.values() if entry["hashes"]),
        "unpinned_count": 0,
        "direct_names": sorted(direct_set),
        "entries": projected,
    }


def project_native_inventory(
    closure: dict[str, Any], *, native_packages: frozenset[str] | set[str] = NATIVE_PACKAGES
) -> list[dict[str, Any]]:
    """Project the native-compiled subset of the closure into the receipt inventory.

    ``wheel_sha256`` is the canonical digest OVER the package's locked sha256 set (a
    deterministic per-package content identity that binds every acceptable wheel/sdist
    hash) — NOT a single downloaded wheel, because offline we cannot uniquely select
    the one target wheel; that selection + real ``.so`` load is the CI job / S2.5's job,
    hence ``load_verified_on_target`` stays const ``false``.
    """

    by_name = {entry["name"]: entry for entry in closure.get("entries", [])}
    inventory: list[dict[str, Any]] = []
    for name in sorted(native_packages):
        entry = by_name.get(name)
        if entry is None:
            continue
        hashes = sorted(entry["hashes"])
        inventory.append({
            "package": name,
            "version": entry["version"],
            "wheel_sha256": canonical_digest(hashes),
            "load_verified_on_target": False,
        })
    return inventory


def _native_inventory_digest(inventory: list[dict[str, Any]]) -> str:
    return canonical_digest(inventory)


def _launch_block() -> dict[str, Any]:
    # 絕對釘住的隔離啟動契約(mirror S1.4 isolation seams,now sealed for the target runtime)。
    return {
        "launch_interpreter": "absolute_pinned",
        "system_python_fallback_possible": False,
        "python_isolated_mode": True,
        "ignores_ambient_env": True,
    }


def runtime_content_digest(
    *,
    closure_hash: str,
    isolated_launch_config: dict[str, Any],
    native_lib_inventory_digest: str,
    python_version: str,
    target_platform: str,
) -> str:
    """The content-addressed identity of the sealed runtime (S1.6 fixed-path candidate)."""

    return canonical_digest({
        "closure_hash": closure_hash,
        "isolated_launch_config": isolated_launch_config,
        "native_lib_inventory_digest": native_lib_inventory_digest,
        "python_version": python_version,
        "target_platform": target_platform,
    })


# --------------------------------------------------------------------------- #
# platform helper
# --------------------------------------------------------------------------- #
def target_platform_block() -> dict[str, Any]:
    """The Linux target the closure was resolved for (NOT the Mac emit host).

    os/arch/python_version/target_platform describe the resolution TARGET; loading /
    running on that host is S2.5 (boundary.target_host_loaded const false).
    """

    return {
        "os": "linux",
        "arch": "x86_64",
        "python_version": TARGET_PYTHON_VERSION,
        "target_platform": TARGET_PLATFORM,
    }


def _validate_platform(platform: Any) -> dict[str, Any]:
    if (
        not isinstance(platform, dict)
        or platform.get("os") not in PLATFORM_OS
        or not isinstance(platform.get("arch"), str)
        or not platform.get("arch")
        or not isinstance(platform.get("python_version"), str)
        or not platform.get("python_version")
        or not isinstance(platform.get("target_platform"), str)
        or not platform.get("target_platform")
    ):
        raise ValueError("platform must bind os(darwin|linux)/arch/python_version/target_platform")
    return {
        "os": platform["os"],
        "arch": platform["arch"],
        "python_version": platform["python_version"],
        "target_platform": platform["target_platform"],
    }


# --------------------------------------------------------------------------- #
# sealed_build_receipt builder
# --------------------------------------------------------------------------- #
def build_sealed_build_receipt(
    *,
    caller: str,
    platform: dict[str, Any],
    lock_closure: dict[str, Any],
    native_library_inventory: list[dict[str, Any]],
    lock_tool: str,
    lock_input_ref: str,
    learning_runtime_choice_receipt_digest: str,
    runtime_candidate_receipt_b_digest: str,
    observation_time: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``sealed_build_receipt_v1``.

    Status is ``PASS`` when emitted: the sealing invariants (fully-resolved,
    fully-pinned, fully-hashed closure; absolute-pinned isolated launch) map to schema
    consts, so a would-be violation RAISES fail-closed rather than emitting a lying
    ``FAIL`` receipt.  Integrity violations that cannot be safely serialized (secret,
    ttl out of ``[1, 3600]``, non-digest binding, unpinned/unhashed closure) raise.
    """

    if not isinstance(caller, str) or not caller:
        raise ValueError("caller is required")
    if not isinstance(lock_tool, str) or not lock_tool:
        raise ValueError("lock_tool is required")
    if not isinstance(lock_input_ref, str) or not lock_input_ref:
        raise ValueError("lock_input_ref is required")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ValueError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise ValueError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    for label, digest in (
        ("learning_runtime_choice_receipt_digest", learning_runtime_choice_receipt_digest),
        ("runtime_candidate_receipt_b_digest", runtime_candidate_receipt_b_digest),
    ):
        if not DIGEST_RE.fullmatch(str(digest)):
            raise ValueError(f"{label} must be a sha256 digest")

    platform_block = _validate_platform(platform)
    closure_hash = lock_closure.get("closure_hash")
    if not DIGEST_RE.fullmatch(str(closure_hash)):
        raise ValueError("lock_closure.closure_hash must be a sha256 digest")
    entries_total = lock_closure.get("entries_total")
    hashed_total = lock_closure.get("hashed_entries_total")
    unpinned_count = lock_closure.get("unpinned_count")
    if (
        not isinstance(entries_total, int) or entries_total <= 0
        or not isinstance(hashed_total, int)
        or unpinned_count != 0
        or hashed_total != entries_total
    ):
        # fail-closed:未完全 pin/hash 的 closure 不可 seal(否則 real_ml_closure_resolved const=true 造假)。
        raise LockClosureError(
            "sealed build requires a fully-pinned, fully-hashed closure "
            f"(entries_total={entries_total}, hashed_entries_total={hashed_total}, unpinned_count={unpinned_count})"
        )

    native_block = _normalize_native_inventory(native_library_inventory)
    launch_block = _launch_block()
    content_digest = runtime_content_digest(
        closure_hash=closure_hash,
        isolated_launch_config=launch_block,
        native_lib_inventory_digest=_native_inventory_digest(native_block),
        python_version=platform_block["python_version"],
        target_platform=platform_block["target_platform"],
    )

    observed = _parse_time(observation_time)
    expires = observed + timedelta(seconds=ttl_seconds)

    receipt: dict[str, Any] = {
        "schema_version": SEALED_SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "status": "PASS",
        "caller": caller,
        "platform": platform_block,
        "closure_hash": closure_hash,
        "runtime_content_digest": content_digest,
        "lock_tool": lock_tool,
        "lock_input_ref": lock_input_ref,
        "dependency_closure": {
            "real_ml_closure_resolved": True,
            "unpinned_count": 0,
            "entries_total": entries_total,
            "hashed_entries_total": hashed_total,
        },
        "sealed_input": {
            "reproducible_output_verified": True,
            "mutable_tag_or_alias": False,
            "relocatable_renamed_venv": False,
        },
        "launch": launch_block,
        "native_library_inventory": native_block,
        "boundary": {
            "production_installed": False,
            "production_running_attested": False,
            "target_host_loaded": False,
            "nine_authorities_false": True,
        },
        "learning_runtime_choice_receipt_digest": learning_runtime_choice_receipt_digest,
        "runtime_candidate_receipt_b_digest": runtime_candidate_receipt_b_digest,
        "source_sha256": source_sha256(),
        "schema_sha256": sealed_schema_sha256(),
        "secret_scan": {
            "patterns_checked": list(SECRET_PATTERNS_CHECKED),
            "leaked": False,
        },
        "observation_time": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "ttl_seconds": ttl_seconds,
        "failure_reason": None,
    }
    _guard_no_secret({k: v for k, v in receipt.items() if k != "secret_scan"})
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


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
        package = record.get("package")
        version = record.get("version")
        wheel_sha256 = record.get("wheel_sha256")
        if not isinstance(package, str) or not package:
            raise ValueError("native library record package is invalid")
        if package in seen:
            raise ValueError(f"duplicate native library record: {package!r}")
        seen.add(package)
        if not isinstance(version, str) or not version:
            raise ValueError("native library record version is invalid")
        if not DIGEST_RE.fullmatch(str(wheel_sha256)):
            raise ValueError("native library record wheel_sha256 is invalid")
        normalized.append({
            "package": package,
            "version": version,
            "wheel_sha256": wheel_sha256,
            "load_verified_on_target": False,
        })
    return normalized


# --------------------------------------------------------------------------- #
# sealed_build_receipt validator (structural + integrity; not execution authenticity)
# --------------------------------------------------------------------------- #
def validate_sealed_build_receipt(
    receipt: Any,
    *,
    require_success: bool = False,
    now: str | None = None,
) -> list[str]:
    """Validate the sealed-build receipt structure/integrity and the flipped LR2 consts.

    Schema subset, exact field-set, const identity, digest regexes, source/schema
    binding, the flipped consts (``real_ml_closure_resolved`` true / ``unpinned_count`` 0
    / launch isolated), the const-false ``load_verified_on_target`` + boundary flags, an
    INDEPENDENT re-derivation of ``runtime_content_digest`` from the receipt's own fields,
    secret-free serialization, TTL/time ordering and ``self_digest`` re-hash.
    """

    if not isinstance(receipt, dict):
        return ["sealed build receipt must be an object"]
    schema = _sealed_schema()
    errors = [
        f"sealed build receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != SEALED_RECEIPT_FIELDS:
        errors.append(
            "sealed build receipt fields mismatch: "
            f"missing={sorted(SEALED_RECEIPT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - SEALED_RECEIPT_FIELDS)}"
        )
    if receipt.get("schema_version") != SEALED_SCHEMA_VERSION:
        errors.append("sealed build receipt schema_version is invalid")
    if receipt.get("adapter_id") != ADAPTER_ID:
        errors.append("sealed build receipt adapter_id is invalid")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        errors.append("sealed build receipt status is invalid")

    for field_name in (
        "closure_hash", "runtime_content_digest", "learning_runtime_choice_receipt_digest",
        "runtime_candidate_receipt_b_digest", "source_sha256", "schema_sha256", "self_digest",
    ):
        if not DIGEST_RE.fullmatch(str(receipt.get(field_name, ""))):
            errors.append(f"sealed build receipt {field_name} is invalid")
    if receipt.get("source_sha256") != source_sha256():
        errors.append("sealed build receipt source_sha256 does not bind this module")
    if receipt.get("schema_sha256") != sealed_schema_sha256():
        errors.append("sealed build receipt schema_sha256 does not bind the schema")

    errors.extend(_validate_sealed_consts(receipt))
    errors.extend(_validate_sealed_native_inventory(receipt))
    errors.extend(_validate_runtime_content_digest(receipt))
    errors.extend(_validate_secret_scan(receipt, kind="sealed build"))
    errors.extend(_validate_times(receipt, now=now, kind="sealed build"))

    status = receipt.get("status")
    failure_reason = receipt.get("failure_reason")
    if status == "PASS":
        if failure_reason is not None:
            errors.append("PASS sealed build receipt cannot carry a failure_reason")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAIL sealed build receipt requires a non-empty failure_reason")

    if require_success and status != "PASS":
        errors.append("sealed build receipt does not prove a passing sealed build")
    if receipt.get("self_digest") != receipt_digest(receipt):
        errors.append("sealed build receipt self_digest does not match canonical receipt")
    return errors


def _validate_sealed_consts(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    dependency = receipt.get("dependency_closure")
    if isinstance(dependency, dict):
        if dependency.get("real_ml_closure_resolved") is not True:
            errors.append("dependency_closure.real_ml_closure_resolved must be true at S2.3")
        if dependency.get("unpinned_count") != 0:
            errors.append("dependency_closure.unpinned_count must be 0 (fully pinned)")
        entries_total = dependency.get("entries_total")
        hashed_total = dependency.get("hashed_entries_total")
        if not isinstance(entries_total, int) or entries_total <= 0:
            errors.append("dependency_closure.entries_total must be a positive integer")
        elif hashed_total != entries_total:
            errors.append("dependency_closure.hashed_entries_total must equal entries_total")
    sealed = receipt.get("sealed_input")
    if isinstance(sealed, dict):
        if sealed.get("reproducible_output_verified") is not True:
            errors.append("sealed_input.reproducible_output_verified must be true at S2.3")
        if sealed.get("mutable_tag_or_alias") is not False:
            errors.append("sealed_input.mutable_tag_or_alias must be false")
        if sealed.get("relocatable_renamed_venv") is not False:
            errors.append("sealed_input.relocatable_renamed_venv must be false")
    launch = receipt.get("launch")
    if isinstance(launch, dict):
        if launch.get("launch_interpreter") != "absolute_pinned":
            errors.append("launch.launch_interpreter must be absolute_pinned")
        if launch.get("system_python_fallback_possible") is not False:
            errors.append("launch.system_python_fallback_possible must be false")
        if launch.get("python_isolated_mode") is not True:
            errors.append("launch.python_isolated_mode must be true")
        if launch.get("ignores_ambient_env") is not True:
            errors.append("launch.ignores_ambient_env must be true")
    boundary = receipt.get("boundary")
    if isinstance(boundary, dict):
        for flag in ("production_installed", "production_running_attested", "target_host_loaded"):
            if boundary.get(flag) is not False:
                errors.append(f"boundary.{flag} must be false (installing=S2.4, running=S2.5/LR6)")
        if boundary.get("nine_authorities_false") is not True:
            errors.append("boundary.nine_authorities_false must be true")
    return errors


def _validate_sealed_native_inventory(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    inventory = receipt.get("native_library_inventory")
    if not isinstance(inventory, list):
        return ["sealed build native_library_inventory must be a list"]
    seen: set[str] = set()
    for record in inventory:
        if not isinstance(record, dict):
            errors.append("sealed build native_library_inventory record is invalid")
            continue
        package = record.get("package")
        if isinstance(package, str) and package:
            if package in seen:
                errors.append(f"sealed build native_library_inventory duplicate package: {package}")
            seen.add(package)
        if not DIGEST_RE.fullmatch(str(record.get("wheel_sha256", ""))):
            errors.append("sealed build native_library_inventory wheel_sha256 is invalid")
        if record.get("load_verified_on_target") is not False:
            errors.append("native_library_inventory load_verified_on_target must be false (loading is S2.5/LR6)")
    return errors


def _validate_runtime_content_digest(receipt: dict[str, Any]) -> list[str]:
    # 獨立重算:偽造的 runtime_content_digest 必須被抓(不只信自報值)。
    platform = receipt.get("platform")
    launch = receipt.get("launch")
    inventory = receipt.get("native_library_inventory")
    closure_hash = receipt.get("closure_hash")
    if not (isinstance(platform, dict) and isinstance(launch, dict) and isinstance(inventory, list)):
        return ["sealed build runtime_content_digest inputs are malformed"]
    if not DIGEST_RE.fullmatch(str(closure_hash)):
        return []
    recomputed = runtime_content_digest(
        closure_hash=closure_hash,
        isolated_launch_config=launch,
        native_lib_inventory_digest=_native_inventory_digest(inventory),
        python_version=platform.get("python_version"),
        target_platform=platform.get("target_platform"),
    )
    if receipt.get("runtime_content_digest") != recomputed:
        return ["sealed build runtime_content_digest does not match an independent re-derivation"]
    return []


# --------------------------------------------------------------------------- #
# expected_identity_receipt builder (BINDS/projects S1.3; does not re-derive)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _s1_3_component_projection() -> dict[str, dict[str, Any]]:
    """Project the per-component identity from S1.3's canonical topology (single source)."""

    contract = _s1_3.canonical_identity_acl_contract()
    host_by_component = {row["component"]: row for row in contract["host_uid_topology"]}
    role_by_component = {row["component"]: row for row in contract["pg_role_topology"]}
    socket_by_component = {row["component"]: row for row in contract["socket_dir_acl"]}
    auth_method = contract["auth_mapping"]["method"]
    loader_kind = contract["secret_lifecycle"]["protected_loading"]["loader_kind"]
    projection: dict[str, dict[str, Any]] = {}
    for component in SEALED_COMPONENTS:
        host = host_by_component[component]
        role = role_by_component[component]
        socket = socket_by_component[component]
        projection[component] = {
            "component": component,
            "uid_label": host["uid_label"],
            "pg_role": role["role_name"],
            "privilege_class": role["privilege_class"],
            "auth_method": auth_method,
            "socket_dir_mode": socket["mode"],
            "protected_secret_loader": loader_kind,
            "oci_socket_access": False,
            "dbus_authority": False,
            "non_root": True,
        }
    return projection


def expected_component_identities() -> list[dict[str, Any]]:
    projection = _s1_3_component_projection()
    return [dict(projection[component]) for component in SEALED_COMPONENTS]


def s1_3_negatives_digest() -> str:
    # 投影 S1.3 的 negative-ACL 種類(over_grant_kinds)為單一 digest;綁 S1.3 by construction。
    return canonical_digest(list(_s1_3.OVER_GRANT_KINDS))


def _rollback_binding() -> dict[str, Any]:
    change_kinds = sorted(_s1_3.CHANGE_KINDS)
    return {
        "rollback_present": True,
        "change_kinds": change_kinds,
        "rollback_digest": canonical_digest(change_kinds),
    }


def build_expected_identity_receipt(
    *,
    caller: str,
    platform: dict[str, Any],
    sealed_build_digest: str,
    runtime_content_digest: str,
    identity_acl_contract_digest: str,
    observation_time: str,
    ttl_seconds: int,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``expected_identity_receipt_v1`` (binds S1.3 -> sealed build).

    Projects the S1.3 least-privilege matrix (host UID / PG role / auth / socket / secret
    loader) onto the sealed build.  Every ``production_provisioned.*`` and
    ``running_attested.*`` flag is const ``false`` (provisioning=S2.4, running=S2.5/LR6);
    ``observation_owner`` is const ``S2.5_LR6``.
    """

    if not isinstance(caller, str) or not caller:
        raise ValueError("caller is required")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        raise ValueError("ttl_seconds must be an integer")
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        raise ValueError(f"ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    for label, digest in (
        ("sealed_build_digest", sealed_build_digest),
        ("runtime_content_digest", runtime_content_digest),
        ("identity_acl_contract_digest", identity_acl_contract_digest),
    ):
        if not DIGEST_RE.fullmatch(str(digest)):
            raise ValueError(f"{label} must be a sha256 digest")

    platform_block = _validate_platform(platform)
    observed = _parse_time(observation_time)
    expires = observed + timedelta(seconds=ttl_seconds)
    components = expected_component_identities()

    receipt: dict[str, Any] = {
        "schema_version": EXPECTED_IDENTITY_SCHEMA_VERSION,
        "adapter_id": ADAPTER_ID,
        "status": "PASS",
        "caller": caller,
        "platform": platform_block,
        "sealed_build_digest": sealed_build_digest,
        "runtime_content_digest": runtime_content_digest,
        "identity_acl_contract_digest": identity_acl_contract_digest,
        "expected_component_identities": components,
        "least_privilege_assertions": {
            "no_oci_socket": True,
            "no_dbus_authority": True,
            "host_systemd_owns_lifecycle": True,
            "non_root_all": True,
        },
        "negative_acl_binding": {
            "s1_3_negatives_digest": s1_3_negatives_digest(),
            "count": len(_s1_3.OVER_GRANT_KINDS),
            "all_rejected": True,
        },
        "secret_loading_binding": {
            "no_plaintext_ingress": True,
            "plaintext_ingress": False,
        },
        "rollback_binding": _rollback_binding(),
        "production_provisioned": {
            "uid": False,
            "pg_role": False,
            "hba": False,
            "socket": False,
            "credential": False,
        },
        "running_attested": {
            "unit": False,
            "pid_cgroup": False,
            "mount": False,
            "network": False,
            "pg_identity": False,
        },
        "observation_owner": "S2.5_LR6",
        "source_sha256": source_sha256(),
        "schema_sha256": expected_identity_schema_sha256(),
        "secret_scan": {
            "patterns_checked": list(SECRET_PATTERNS_CHECKED),
            "leaked": False,
        },
        "observation_time": observed.isoformat(),
        "expires_at": expires.isoformat(),
        "ttl_seconds": ttl_seconds,
        "failure_reason": None,
    }
    _guard_no_secret({k: v for k, v in receipt.items() if k != "secret_scan"})
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


def validate_expected_identity_receipt(
    receipt: Any,
    *,
    require_success: bool = False,
    now: str | None = None,
) -> list[str]:
    """Validate the expected-identity receipt structure/integrity and the S1.3 projection.

    Beyond schema subset / field-set / const identity / digest regex / source-schema
    binding / secret / TTL / self_digest, this INDEPENDENTLY re-projects the S1.3
    per-component identity from ``canonical_identity_acl_contract`` and asserts every
    ``expected_component_identities`` row matches it exactly (component / uid_label /
    pg_role / privilege_class / auth_method / socket_dir_mode / protected_secret_loader),
    that each row is non-root with no OCI socket / DBus authority, that the negative-ACL
    binding re-derives the S1.3 ``OVER_GRANT_KINDS`` digest with ``count`` >= 10 and
    ``all_rejected``, and that every production / running-attested flag is false.
    """

    if not isinstance(receipt, dict):
        return ["expected identity receipt must be an object"]
    schema = _expected_identity_schema()
    errors = [
        f"expected identity receipt schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != EXPECTED_IDENTITY_RECEIPT_FIELDS:
        errors.append(
            "expected identity receipt fields mismatch: "
            f"missing={sorted(EXPECTED_IDENTITY_RECEIPT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - EXPECTED_IDENTITY_RECEIPT_FIELDS)}"
        )
    if receipt.get("schema_version") != EXPECTED_IDENTITY_SCHEMA_VERSION:
        errors.append("expected identity receipt schema_version is invalid")
    if receipt.get("adapter_id") != ADAPTER_ID:
        errors.append("expected identity receipt adapter_id is invalid")
    if receipt.get("status") not in {"PASS", "FAIL"}:
        errors.append("expected identity receipt status is invalid")
    if receipt.get("observation_owner") != "S2.5_LR6":
        errors.append("expected identity receipt observation_owner must be S2.5_LR6")

    for field_name in (
        "sealed_build_digest", "runtime_content_digest", "identity_acl_contract_digest",
        "source_sha256", "schema_sha256", "self_digest",
    ):
        if not DIGEST_RE.fullmatch(str(receipt.get(field_name, ""))):
            errors.append(f"expected identity receipt {field_name} is invalid")
    if receipt.get("source_sha256") != source_sha256():
        errors.append("expected identity receipt source_sha256 does not bind this module")
    if receipt.get("schema_sha256") != expected_identity_schema_sha256():
        errors.append("expected identity receipt schema_sha256 does not bind the schema")

    errors.extend(_validate_component_projection(receipt))
    errors.extend(_validate_least_privilege_assertions(receipt))
    errors.extend(_validate_negative_acl_binding(receipt))
    errors.extend(_validate_secret_loading_binding(receipt))
    errors.extend(_validate_rollback_binding(receipt))
    errors.extend(_validate_provisioned_and_running_flags(receipt))
    errors.extend(_validate_secret_scan(receipt, kind="expected identity"))
    errors.extend(_validate_times(receipt, now=now, kind="expected identity"))

    status = receipt.get("status")
    failure_reason = receipt.get("failure_reason")
    if status == "PASS":
        if failure_reason is not None:
            errors.append("PASS expected identity receipt cannot carry a failure_reason")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAIL expected identity receipt requires a non-empty failure_reason")

    if require_success and status != "PASS":
        errors.append("expected identity receipt does not prove a passing binding")
    if receipt.get("self_digest") != receipt_digest(receipt):
        errors.append("expected identity receipt self_digest does not match canonical receipt")
    return errors


def _validate_component_projection(receipt: dict[str, Any]) -> list[str]:
    rows = receipt.get("expected_component_identities")
    if not isinstance(rows, list) or not rows:
        return ["expected identity receipt expected_component_identities is missing"]
    errors: list[str] = []
    projection = _s1_3_component_projection()
    seen: list[Any] = []
    for row in rows:
        if not isinstance(row, dict):
            errors.append("expected identity component row is invalid")
            continue
        component = row.get("component")
        seen.append(component)
        expected = projection.get(component)
        if expected is None:
            errors.append(f"expected identity component {component!r} is not an S1.3 sealed component")
            continue
        # 逐欄核對 S1.3 投影;偽造 receipt 對某元件 mislabel 身分即被抓。
        for field in ("uid_label", "pg_role", "privilege_class", "auth_method",
                      "socket_dir_mode", "protected_secret_loader"):
            if row.get(field) != expected[field]:
                errors.append(
                    f"expected identity component {component!r} {field} does not match the bound "
                    f"S1.3 projection (got {row.get(field)!r}, expected {expected[field]!r})"
                )
        if row.get("oci_socket_access") is not False or row.get("dbus_authority") is not False:
            errors.append(f"expected identity component {component!r} holds OCI socket or DBus authority")
        if row.get("non_root") is not True:
            errors.append(f"expected identity component {component!r} is not non-root")
    if len(seen) != len(set(seen)):
        errors.append("expected identity receipt has a duplicate component row")
    if set(seen) != set(SEALED_COMPONENTS):
        errors.append(
            "expected identity components must be exactly the S1.3 sealed set "
            f"{sorted(SEALED_COMPONENTS)} (got {sorted(str(c) for c in seen)})"
        )
    return errors


def _validate_least_privilege_assertions(receipt: dict[str, Any]) -> list[str]:
    assertions = receipt.get("least_privilege_assertions")
    if not isinstance(assertions, dict):
        return ["expected identity least_privilege_assertions is missing"]
    errors: list[str] = []
    for flag in ("no_oci_socket", "no_dbus_authority", "host_systemd_owns_lifecycle", "non_root_all"):
        if assertions.get(flag) is not True:
            errors.append(f"expected identity least_privilege_assertions.{flag} must be true")
    return errors


def _validate_negative_acl_binding(receipt: dict[str, Any]) -> list[str]:
    binding = receipt.get("negative_acl_binding")
    if not isinstance(binding, dict):
        return ["expected identity negative_acl_binding is missing"]
    errors: list[str] = []
    count = binding.get("count")
    if isinstance(count, bool) or not isinstance(count, int) or count < 10:
        errors.append("expected identity negative_acl_binding.count must be an integer >= 10")
    if binding.get("all_rejected") is not True:
        errors.append("expected identity negative_acl_binding.all_rejected must be true")
    if binding.get("s1_3_negatives_digest") != s1_3_negatives_digest():
        errors.append("expected identity negative_acl_binding.s1_3_negatives_digest does not bind the S1.3 negatives")
    # count 必等於 S1.3 實際 over-grant 種類數(綁 S1.3 by construction)。
    if isinstance(count, int) and not isinstance(count, bool) and count != len(_s1_3.OVER_GRANT_KINDS):
        errors.append("expected identity negative_acl_binding.count does not match the S1.3 over-grant kind count")
    return errors


def _validate_secret_loading_binding(receipt: dict[str, Any]) -> list[str]:
    binding = receipt.get("secret_loading_binding")
    if not isinstance(binding, dict):
        return ["expected identity secret_loading_binding is missing"]
    errors: list[str] = []
    if binding.get("no_plaintext_ingress") is not True:
        errors.append("expected identity secret_loading_binding.no_plaintext_ingress must be true")
    if binding.get("plaintext_ingress") is not False:
        errors.append("expected identity secret_loading_binding.plaintext_ingress must be false")
    return errors


def _validate_rollback_binding(receipt: dict[str, Any]) -> list[str]:
    binding = receipt.get("rollback_binding")
    if not isinstance(binding, dict):
        return ["expected identity rollback_binding is missing"]
    errors: list[str] = []
    if binding.get("rollback_present") is not True:
        errors.append("expected identity rollback_binding.rollback_present must be true")
    change_kinds = binding.get("change_kinds")
    expected_kinds = sorted(_s1_3.CHANGE_KINDS)
    if change_kinds != expected_kinds:
        errors.append("expected identity rollback_binding.change_kinds must bind the S1.3 change kinds")
    elif binding.get("rollback_digest") != canonical_digest(expected_kinds):
        errors.append("expected identity rollback_binding.rollback_digest does not bind the change kinds")
    return errors


def _validate_provisioned_and_running_flags(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    provisioned = receipt.get("production_provisioned")
    if not isinstance(provisioned, dict):
        errors.append("expected identity production_provisioned is missing")
    else:
        for flag in ("uid", "pg_role", "hba", "socket", "credential"):
            if provisioned.get(flag) is not False:
                errors.append(f"expected identity production_provisioned.{flag} must be false (provisioning is S2.4)")
    running = receipt.get("running_attested")
    if not isinstance(running, dict):
        errors.append("expected identity running_attested is missing")
    else:
        for flag in ("unit", "pid_cgroup", "mount", "network", "pg_identity"):
            if running.get(flag) is not False:
                errors.append(f"expected identity running_attested.{flag} must be false (running attestation is S2.5/LR6)")
    return errors


# --------------------------------------------------------------------------- #
# shared secret-scan + time validators
# --------------------------------------------------------------------------- #
def _validate_secret_scan(receipt: dict[str, Any], *, kind: str) -> list[str]:
    errors: list[str] = []
    secret_scan = receipt.get("secret_scan")
    if not isinstance(secret_scan, dict):
        return [f"{kind} receipt secret_scan is missing"]
    if secret_scan.get("leaked") is not False:
        errors.append(f"{kind} secret_scan must report leaked=false")
    if list(secret_scan.get("patterns_checked", [])) != list(SECRET_PATTERNS_CHECKED):
        errors.append(f"{kind} secret_scan patterns are not the exact contract")
    if _contains_secret_like({k: v for k, v in receipt.items() if k != "secret_scan"}):
        errors.append(f"{kind} receipt carries secret-like content")
    return errors


def _validate_times(receipt: dict[str, Any], *, now: str | None, kind: str) -> list[str]:
    errors: list[str] = []
    ttl_seconds = receipt.get("ttl_seconds")
    if isinstance(ttl_seconds, bool) or not isinstance(ttl_seconds, int):
        return [f"{kind} receipt ttl_seconds is invalid"]
    if not (1 <= ttl_seconds <= TTL_CEILING_SECONDS):
        errors.append(f"{kind} ttl_seconds must be within [1, {TTL_CEILING_SECONDS}]")
    try:
        observed = _parse_time(str(receipt.get("observation_time", "")))
        expires = _parse_time(str(receipt.get("expires_at", "")))
        if expires != observed + timedelta(seconds=ttl_seconds):
            errors.append(f"{kind} expires_at does not equal observation_time + ttl")
        if not observed < expires:
            errors.append(f"{kind} observation_time must precede expires_at")
        if now is not None:
            current = _parse_time(now)
            if not observed <= current < expires:
                errors.append(f"{kind} receipt is not fresh")
    except (TypeError, ValueError):
        errors.append(f"{kind} receipt timestamps are invalid")
    return errors


# --------------------------------------------------------------------------- #
# real S2.3 emit (RUN the builders against the committed lock + real S1 digests)
# --------------------------------------------------------------------------- #
def emit_s23_receipts(
    *,
    observation_time: str,
    ttl_seconds: int = 1800,
    caller: str = "E1:S2.3:LR2-sealed-build",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build BOTH real S2.3 receipts from the committed lock + real committed S1 digests.

    Bindings (documented, real, reproducible):
      * ``runtime_candidate_receipt_b_digest`` — the real committed S1.4-B receipt digest
        recorded in the committed S1.5 ``effect_seams_ready_receipt.json`` rollup.
      * ``identity_acl_contract_digest`` — the real committed S1.3 receipt digest from the
        same committed S1.5 rollup.
      * ``learning_runtime_choice_receipt_digest`` — SCHEMA-LEVEL binding: the S1.6
        runtime-choice receipt instance is disposable/uncommitted (not captured into any
        committed rollup), so the committed schema identity is bound instead.
    """

    closure = verify_lock_closure(REPO_ROOT / LOCK_INPUT_REF, REPO_ROOT / SPEC_INPUT_REF)
    native_inventory = project_native_inventory(closure)
    sealed = build_sealed_build_receipt(
        caller=caller,
        platform=target_platform_block(),
        lock_closure=closure,
        native_library_inventory=native_inventory,
        lock_tool=LOCK_TOOL,
        lock_input_ref=LOCK_INPUT_REF,
        learning_runtime_choice_receipt_digest=learning_runtime_choice_schema_sha256(),
        runtime_candidate_receipt_b_digest=S1_4_RUNTIME_CANDIDATE_B_DIGEST,
        observation_time=observation_time,
        ttl_seconds=ttl_seconds,
    )
    expected_identity = build_expected_identity_receipt(
        caller=caller,
        platform=target_platform_block(),
        sealed_build_digest=sealed["self_digest"],
        runtime_content_digest=sealed["runtime_content_digest"],
        identity_acl_contract_digest=S1_3_IDENTITY_ACL_RECEIPT_DIGEST,
        observation_time=observation_time,
        ttl_seconds=ttl_seconds,
    )
    return sealed, expected_identity


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI: emit + self-validate both S2.3 receipts into the committed receipts dir."""

    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observation-time", default="2026-07-24T00:00:00+00:00")
    parser.add_argument("--ttl-seconds", type=int, default=1800)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "docs/execution_plan/ai_ml_landing/receipts",
    )
    parser.add_argument("--emit", action="store_true", help="write the receipts to --out-dir")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    sealed, expected_identity = emit_s23_receipts(
        observation_time=args.observation_time, ttl_seconds=args.ttl_seconds
    )
    sealed_errors = validate_sealed_build_receipt(sealed, require_success=True)
    identity_errors = validate_expected_identity_receipt(expected_identity, require_success=True)
    if sealed_errors or identity_errors:
        print("VALIDATION FAILED", {"sealed": sealed_errors, "expected_identity": identity_errors})
        return 1
    if args.emit:
        _write_json(args.out_dir / "S2.3-sealed-build-receipt-v1.json", sealed)
        _write_json(args.out_dir / "S2.3-expected-identity-receipt-v1.json", expected_identity)
    print(json.dumps({
        "sealed_build_self_digest": sealed["self_digest"],
        "runtime_content_digest": sealed["runtime_content_digest"],
        "closure_hash": sealed["closure_hash"],
        "expected_identity_self_digest": expected_identity["self_digest"],
        "entries_total": sealed["dependency_closure"]["entries_total"],
        "hashed_entries_total": sealed["dependency_closure"]["hashed_entries_total"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Real target-host disposable runtime probe + target-host choice for AIML LR0C (S1.6B).

This harness is the TARGET-HOST counterpart of the S1.6 Mac choice probe
(``agent_governance_runtime_choice_probe``).  Where S1.6 made a BINDING runtime
choice from a Mac-local disposable stand-in, S1.6B re-makes the choice on the
REAL non-root Linux target host (``trade-core``) using genuine user-scope kernel
primitives, and records HONEST evidence — never a fake.

Two halves, cleanly split so the logic tests pass on Mac and the real effect runs
on Linux:

* **On-host executor (skips on Mac, never fakes).**  For candidate B
  (``content_addressed_fixed_path``) each plan-§LR0C seam is exercised with a real
  non-root user-scope primitive: ``systemd-run --user --scope`` start/stop
  lifecycle; a scope carrying ``-p MemoryMax/MemoryHigh/CPUQuota/TasksMax`` that is
  ACTIVELY driven (OOM alloc, CPU spin, bounded fork) so ``memory.events:oom_kill``
  / ``cpu.stat`` throttling / ``pids.events:max`` are READ from the scope's cgroup
  dir (enforcement proven, not merely set); a seccomp ``SCMP_ACT_ERRNO(ENETUNREACH)``
  filter on ``connect``/``sendto``/``sendmsg`` (libseccomp via ctypes) whose egress
  attempt is kernel-denied while a no-filter baseline on the same host/port CONNECTs
  (differential proof; ``bwrap --unshare-net`` netns is unusable non-root on this
  host — it needs root-in-userns to bring up ``lo`` but the host denies unprivileged
  ``uid_map`` root-mapping and lacks ``newuidmap``, so bwrap dies on ``lo``); ``bwrap
  --ro-bind`` native-lib load whose ``/proc/self/maps`` resolves the lib only from
  the bundle; a content-addressed bundle at a fixed path with an atomic pointer
  swap (reusing S1.4 ``hash_bundle_tree`` + S1.5 ``artifact_*``); ``systemctl
  --user kill`` + restart-from-same-bundle + teardown + ``reset-failed`` + rmtree
  with an INDEPENDENT residue verifier.  Every on-host function gates on
  ``target_host_available()`` (linux + ``systemd-run`` on PATH + ``AIML_TARGET_HOST_
  PROBE=1``); on this Mac they raise ``TargetHostUnavailableError`` and SKIP — they
  are marked for the real ``trade-core`` run, they never simulate a kernel fact.
  cpuset (pinning) + io (bandwidth) are root-only and recorded as deferred
  refinements (PM Q4); the full LR2-sealed native closure is S2.3 (PM Q3, a
  representative ``.so`` + a ``representativeness`` flag).

* **Choice-receipt logic (Mac-testable).**  ``build_target_host_choice_receipt``
  turns the per-seam verdicts into a canonical self-hashed
  ``learning_runtime_choice_receipt_target_host_v1``.  Candidate A (OCI) is
  boundary-driven NON-selection: every OCI seam is ``NON_SATISFIABLE_NON_ROOT``
  (trade-core has only a rootful docker daemon; LR2 forbids the OCI socket surface;
  no rootless OCI runtime) — the machine rule ``oci_selectable ==
  (target_host_probe_performed AND every OCI seam PASSED_TARGET_HOST)`` is const
  false on real evidence, so ``final_choice = content_addressed_fixed_path``.  The
  binding is ``BINDING`` only when EVERY fixed-path seam is ``PASSED_TARGET_HOST``;
  if any is not — e.g. on a host lacking ``initdb`` the PLUGGABLE PG-identity seam
  stays ``DEFERRED_TARGET_HOST`` — the binding is ``PROVISIONAL_PENDING_LINUX`` and
  ``pending_seams`` names the exact unmet seam(s), NEVER a forced BINDING PASS.  On
  trade-core (postgresql-16 installed, 2026-07-23) all 7 fixed-path seams
  ``PASSED_TARGET_HOST`` — ``independent_postcheck`` is ``DEFERRED`` by design in
  the applier's own receipt and earns PASS only when a distinct verifier attaches a
  clean residue sweep, at which point the choice is ``BINDING``.

**Honesty gate.**  ``status=PASS`` REQUIRES ``evidence_class ==
PLATFORM_OR_EXTERNAL_ATTESTED`` and ``boundary.real_target_host_primitives_
invoked == true``.  A Mac author cannot self-produce trade-core kernel facts, so a
Mac structural synthesis is ``STRUCTURAL_ONLY`` and ``status=FAIL``: it exercises
the receipt/verdict LOGIC only and can never masquerade as the real target-host
exit (``require_target_host_attested=True`` rejects it).

**Boundary (airtight, fail-closed).**  Non-root; user-scope transient units only
(NO ``systemctl --system``); NO docker; NO production unit/socket/path; prod PG on
:5432 UNTOUCHED; everything under a fresh ``mktemp -d`` under ``$XDG_RUNTIME_DIR``
+ a user cgroup subtree + a private netns; complete teardown with an INDEPENDENT
residue check.  Fail-closed STOPS (no PASS): passwordless sudo present; missing
delegated ``cpu memory pids``; target under a production path; any docker /
system-scope; any prod-PG contact; applier==verifier; cleanup residue; a secret in
any serialized field; TTL exceeded.

Like S1.1/S1.4/S1.6 this harness SELF-VALIDATES its own receipt and is NOT
registered into the central AIML closure-validator, the governance registry, the
route-compiler, permissions, or the vocabulary; S1.6B stays disjoint.  It REUSES
(read-only imports) S1.5 ``agent_governance_component_effects`` (the atomic
artifact lifecycle + the live matrix digest; it reuses the already-registered
``learning_runtime_deploy_adapter_v1`` and adds NO registry adapter) and S1.4
``agent_governance_runtime_candidate_spike`` (the candidate ids, ``hash_bundle_tree``
and platform base).  It is stdlib-first.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import agent_governance_component_effects as ce
import agent_governance_runtime_candidate_spike as spike
from agent_governance_schema import schema_subset_errors


HARNESS_ID = "target_host_probe_v1"
RECEIPT_SCHEMA_VERSION = "learning_runtime_choice_receipt_target_host_v1"
PROBE_EFFECT_CLASS = "TARGET_HOST_DISPOSABLE_RUNTIME_PROBE"
# S1.5 已註冊;S1.6B 復用、不新增 registry adapter/matrix。
PROBE_ADAPTER_ID = "learning_runtime_deploy_adapter_v1"

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
SCHEMA_DIR = REPO_ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
RECEIPT_SCHEMA_PATH = SCHEMA_DIR / "learning_runtime_choice_receipt_target_host_v1.schema.json"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# 兩候選的合法 id(復用 S1.4);未知 id 一律 fail-closed。
CANDIDATE_OCI = spike.CANDIDATE_OCI  # "exact_image_id_oci"
CANDIDATE_FIXED_PATH = spike.CANDIDATE_FIXED_PATH  # "content_addressed_fixed_path"
CANDIDATE_IDS = frozenset({CANDIDATE_OCI, CANDIDATE_FIXED_PATH})

# 本 receipt 只接受 target_host;production/disposable_local 一律 fail-closed raise。
TARGET_CLASS = "target_host"
REJECTED_TARGET_CLASSES = frozenset({"production", "disposable_local", "disposable_offline"})

# 證據等級:真跑於 target host = 平台/外部背書;Mac 合成 = 純結構(status 必 FAIL,不得冒充真探針)。
EVIDENCE_ATTESTED = "PLATFORM_OR_EXTERNAL_ATTESTED"
EVIDENCE_STRUCTURAL = "STRUCTURAL_ONLY"
EVIDENCE_CLASSES = frozenset({EVIDENCE_ATTESTED, EVIDENCE_STRUCTURAL})

PLATFORM_OS = frozenset({"darwin", "linux"})
TTL_CEILING_SECONDS = 3600

# seam 裁決常量:target-host 通過 / target-host 延後 / 非 root 邊界內不可滿足(OCI)。
SEAM_VERDICT_PASSED = "PASSED_TARGET_HOST"
SEAM_VERDICT_DEFERRED = "DEFERRED_TARGET_HOST"
SEAM_VERDICT_NON_SATISFIABLE = "NON_SATISFIABLE_NON_ROOT"
SEAM_VERDICTS = frozenset({SEAM_VERDICT_PASSED, SEAM_VERDICT_DEFERRED, SEAM_VERDICT_NON_SATISFIABLE})
FIXED_PATH_SEAM_VERDICTS = frozenset({SEAM_VERDICT_PASSED, SEAM_VERDICT_DEFERRED})

# 八個 target-host seam(fixed-path 與 OCI 用同一集合,對照才是同基準)。
SEAM_START_STOP = "start_stop"
SEAM_CGROUP = "cgroup_resource_isolation"
SEAM_NETWORK_DENIAL = "network_denial"
SEAM_NATIVE_LIB = "native_lib_loading"
SEAM_IMMUTABLE_CLOSURE = "immutable_closure_persistence"
SEAM_FAILURE_ROLLBACK_CLEANUP = "failure_rollback_cleanup"
SEAM_PG_IDENTITY = "pg_identity"
SEAM_INDEPENDENT_POSTCHECK = "independent_postcheck"
TARGET_HOST_SEAMS = (
    SEAM_START_STOP,
    SEAM_CGROUP,
    SEAM_NETWORK_DENIAL,
    SEAM_NATIVE_LIB,
    SEAM_IMMUTABLE_CLOSURE,
    SEAM_FAILURE_ROLLBACK_CLEANUP,
    SEAM_PG_IDENTITY,
    SEAM_INDEPENDENT_POSTCHECK,
)
TARGET_HOST_SEAM_SET = frozenset(TARGET_HOST_SEAMS)

# 非 root 可委派控制器(user@<uid>.service 委派 cpu/mem/pids);缺一即 fail-closed。
REQUIRED_DELEGATED_CONTROLLERS = frozenset({"cpu", "memory", "pids"})
# cpuset(釘核)+ io(頻寬)是 root-only,記為延後精修(PM Q4),非 S1.6 seam 必要。
DEFERRED_ROOT_ONLY_CONTROLLERS = ("cpuset", "io")

# native-lib 代表性(PM Q3):代表性 .so 已可證載入 seam;完整 LR2-sealed 封存屬 S2.3。
NATIVE_REPRESENTATIVE = "representative_native_lib"
NATIVE_FULL_CLOSURE = "lr2_sealed_closure"

# PG-identity 可插拔模式:server 缺席即誠實延後;initdb 到位即翻成真 S1.1 42501 叢集,零代碼變更。
PG_MODE_DEFERRED = "deferred_server_absent"
PG_MODE_REAL = "real_initdb_cluster"
PG_MODES = frozenset({PG_MODE_DEFERRED, PG_MODE_REAL})
PG_IDENTITY_SQLSTATE = "42501"

# 選擇區塊常量(machine-encoded 規則)。
FINAL_CHOICE_FIXED_PATH = CANDIDATE_FIXED_PATH
FINAL_CHOICE_OCI = CANDIDATE_OCI
SELECTION_RULE = "oci_only_if_all_seams_pass_else_fixed_path"
BINDING_BINDING = "BINDING"
BINDING_PROVISIONAL = "PROVISIONAL_PENDING_LINUX"

# OCI 每 seam 的非選擇理由(PM Q1:邊界驅動的非選擇,LR2 已禁 OCI socket surface)。
OCI_NON_SATISFIABLE_REASON = (
    "no non-root OCI runtime on target (rootful docker only); LR2 forbids the OCI socket surface"
)
OCI_CAVEATS = (
    "no_non_root_oci_runtime_on_target",
    "rootful_docker_daemon_only",
    "lr2_no_oci_socket_dbus",
)
FIXED_PATH_CAVEATS = (
    "cpuset_io_isolation_root_only_deferred_pm_q4",
    "native_closure_representative_full_sealed_s2_3_pm_q3",
)

EXPECTED_TARGET_HOST_DEFAULT = "trade-core"

# 拋棄佈署根必須在此(target 上 $XDG_RUNTIME_DIR,通常 /run/user/<uid>);其餘為 fail-closed 生產前綴。
PRODUCTION_PATH_PREFIXES = (
    "/opt/aiml",
    "/opt/openclaw",
    "/var/lib/openclaw",
    "/var/lib/postgresql",
    "/etc",
    "/srv",
    "/usr",
    "/boot",
)

# 每個 fixed-path seam 的誠實描述(真跑於 target host 由 run_target_host_probe 以真觀察覆寫 note)。
_SEAM_NOTES = {
    SEAM_START_STOP: "systemd-run --user --scope lifecycle observed Active->dead, unit present->absent",
    SEAM_CGROUP: (
        "scope with MemoryMax/MemoryHigh/CPUQuota/TasksMax drove memory.events:oom_kill, "
        "cpu.stat throttling and pids.events:max (cpu/mem/pids; cpuset/io root-only deferred)"
    ),
    SEAM_NETWORK_DENIAL: "seccomp connect/sendto/sendmsg egress denial: baseline CONNECTED, filtered ENETUNREACH (non-root, kernel-enforced)",
    SEAM_NATIVE_LIB: "compiled unique-soname .so in the bundle; CDLL resolves it from the content-addressed bundle prefix (/proc/self/maps) with a callable symbol (=42)",
    SEAM_IMMUTABLE_CLOSURE: "content-addressed bundle at a fixed path; atomic pointer swap; digest re-derived across restart",
    SEAM_FAILURE_ROLLBACK_CLEANUP: "systemctl --user kill + restart-from-same-bundle; interrupted apply never swaps; teardown + reset-failed + rmtree",
    SEAM_PG_IDENTITY: "S1.1 disposable initdb cluster on-target: read-only role SET ROLE denied 42501",
    # 已附掛(distinct verifier 完成)後的 independent_postcheck note。
    SEAM_INDEPENDENT_POSTCHECK: "distinct OPS verifier (verifier != applier) attached a clean on-host residue sweep: units/cgroup/netns/temp all gone",
}
# independent_postcheck 尚未附掛(applier 自跑)時的誠實 note:applier 無法自證獨立性,延後至 distinct 驗證者附掛。
_INDEPENDENT_DEFERRED_NOTE = (
    "independent_postcheck DEFERRED: the applier alone cannot self-certify independence; pending the distinct "
    "OPS verifier's on-host residue sweep (units/cgroup/netns/temp) via attach_independent_postcheck"
)
# native-lib seam 無編譯器、無法真備 bundle .so 時的誠實 note(representativeness-flagged、不計為完整 PASS)。
_NATIVE_IMPORT_ONLY_NOTE = (
    "representative import succeeded but no bundle .so could be compiled/staged (no compiler) to assert the "
    "maps origin; representativeness-flagged, DEFERRED (does not count as a full PASSED for BINDING)"
)
_PG_DEFERRED_NOTE = (
    "postgresql-server not installed on target; PG-identity bound by digest to the S1.1 receipt, "
    "target-host-deferred (initdb on PATH flips this to the real 42501 cluster with no code change)"
)
_PG_RUN_FAILED_NOTE = (
    "initdb resolvable on target but the disposable non-root cluster did not observe the real 42501 "
    "SET ROLE denial; honestly target-host-deferred (bound by digest to the S1.1 receipt) rather than faked"
)

# 對序列化 receipt 的機密掃描(沿 S1.1/S1.4/S1.5/S1.6 風格);本 receipt 全為 digest/label。
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
    "evidence_class",
    "host_identity",
    "platform",
    "probe_scope",
    "candidate_probes",
    "selection",
    "unselected_path_removal",
    "production_running_attested",
    "target_host_capture_digest",
    "dependency_receipts",
    "boundary",
    "source_sha256",
    "schema_sha256",
    "secret_scan",
    "observation_time",
    "expires_at",
    "ttl_seconds",
    "failure_reason",
    "self_digest",
})

# 十六個 fail-closed bypass 種類;交付需全部真觸拒(非橡皮圖章)。
BYPASS_KINDS = (
    "oci_seam_claimed_satisfiable",
    "oci_selected_without_all_seams_passing",
    "binding_with_deferred_fixed_path_seam",
    "provisional_without_unmet_seam",
    "pending_seams_mismatch",
    "attested_without_primitives_invoked",
    "passwordless_sudo_present",
    "missing_delegated_controller",
    "production_path_in_scope",
    "docker_invoked_in_scope",
    "system_scope_used",
    "prod_pg_contacted",
    "applier_is_sole_verifier",
    "production_running_attested_claimed",
    "matrix_digest_tamper",
    "plaintext_secret_ingress",
)
BYPASS_KIND_SET = frozenset(BYPASS_KINDS)


class TargetHostProbeError(RuntimeError):
    """Base for a would-be target-host receipt that cannot be safely emitted (fail-closed)."""


class SecretLeakageError(TargetHostProbeError):
    """Raised when a would-be receipt field carries secret-like content."""


class TargetClassRejectedError(TargetHostProbeError):
    """Raised when a production/disposable target reaches the target-host gate."""


class TargetHostUnavailableError(TargetHostProbeError):
    """Raised when the REAL on-host primitives cannot run here (e.g. Mac).

    這是「乾淨跳過、絕不造假」的信號:任何 on-host executor 函式在非 target host(無
    systemd-run / 非 linux / 未設 AIML_TARGET_HOST_PROBE=1)被呼叫時 raise 此例外,呼叫端
    (在授權 target host 上直跑的 pytest)據此 SKIP,永不合成 kernel 事實冒充真跑。
    注意:governed ``capture-command`` 會 env-strip ``AIML_TARGET_HOST_PROBE``/``XDG_RUNTIME_DIR``,
    故真 seam 不經 capture-command 佐證(那屬 source/結構層,LOCAL_REPRODUCIBLE);真 seam 的
    PLATFORM 佐證來自在 trade-core 上直跑 + distinct OPS on-host 觀察(design §3)。
    """


class FailClosedStop(TargetHostProbeError):
    """Raised when a boundary preflight stop fires (no PASS may follow)."""


class BindingRuleError(TargetHostProbeError):
    """Raised when the BINDING-requires-all-fixed-path-PASSED rule would be violated at build time."""


# --------------------------------------------------------------------------- #
# canonical digest helpers (mirror S1.4/S1.5/S1.6)
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


def _plus_seconds(iso: str, seconds: int) -> str:
    return (_parse_time(iso) + timedelta(seconds=seconds)).isoformat()


@lru_cache(maxsize=1)
def _receipt_schema() -> dict[str, Any]:
    return json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this harness module source."""

    return _file_sha256(SOURCE_PATH)


@lru_cache(maxsize=1)
def receipt_schema_sha256() -> str:
    """Return the sha256 identity of the target-host choice-receipt schema file."""

    return _file_sha256(RECEIPT_SCHEMA_PATH)


def receipt_digest(receipt: dict[str, Any]) -> str:
    """Hash every receipt field except the self-digest."""

    unsigned = {key: value for key, value in receipt.items() if key != "self_digest"}
    return _canonical_digest(unsigned)


# --------------------------------------------------------------------------- #
# secret scan (fail-closed, mirror S1.1/S1.4/S1.5/S1.6)
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
        raise SecretLeakageError("target-host choice receipt payload carries secret-like content")


# --------------------------------------------------------------------------- #
# platform detection (target-host aware; never contacts a daemon)
# --------------------------------------------------------------------------- #
def detect_platform() -> dict[str, Any]:
    """Capture the Mac/Linux reality via stdlib + ``shutil.which`` — no daemon.

    ``non_root_oci_runtime_available`` is const ``false``: neither this Mac nor
    trade-core has a non-root OCI runtime (podman / newuidmap / newgidmap absent;
    docker is rootful).  ``systemd_run_available`` / ``bwrap_available`` are pure
    PATH lookups — on Mac both are false, so the honest platform block shows the
    on-host primitives are unavailable here.
    """

    base = spike.detect_platform()
    return {
        "os": base["os"],
        "arch": base["arch"],
        "python_version": base["python_version"],
        "systemd_run_available": shutil.which("systemd-run") is not None,
        "bwrap_available": shutil.which("bwrap") is not None,
        "non_root_oci_runtime_available": False,
    }


# --------------------------------------------------------------------------- #
# on-host availability gate (SKIP on Mac cleanly; never fake)
# --------------------------------------------------------------------------- #
def target_host_available() -> bool:
    """Whether the REAL non-root target-host probe primitives can run on this node.

    真值需三者齊備:(1) linux;(2) ``systemd-run`` 在 PATH;(3) 顯式旗標
    ``AIML_TARGET_HOST_PROBE=1``。三缺一即 ``False`` → on-host executor 乾淨跳過。這是把
    「真 kernel 效果」限制在被明確授權的 target-host 執行的閘門(旗標由授權的 on-target 執行環境
    設定;governed ``capture-command`` 會剝掉此旗標,故不經它跑真 seam)。
    """

    return (
        sys.platform.startswith("linux")
        and shutil.which("systemd-run") is not None
        and os.environ.get("AIML_TARGET_HOST_PROBE") == "1"
    )


def _require_target_host() -> None:
    if not target_host_available():
        raise TargetHostUnavailableError(
            "real target-host primitives require linux + systemd-run on PATH + AIML_TARGET_HOST_PROBE=1; "
            "this node skips (never fakes a kernel fact)"
        )


def _run(cmd: list[str], *, timeout: int, check: bool = False, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    # 統一的 user-scope 子行程執行:乾淨 env(避免 ambient 洩漏),永不觸 docker / system-scope。
    env = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        env["XDG_RUNTIME_DIR"] = xdg
    dbus = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if dbus:
        env["DBUS_SESSION_BUS_ADDRESS"] = dbus
    return subprocess.run(
        cmd, env=env, input=input_bytes, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, check=check,
    )


def _passwordless_sudo_present() -> bool:
    # sudo -n true:rc==0 代表無需密碼(passwordless)→ 邊界違反,STOP。rc!=0(需密碼)= 預期。
    if shutil.which("sudo") is None:
        return False
    try:
        result = _run(["sudo", "-n", "true"], timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _self_cgroup_dir() -> Path:
    # 由 /proc/self/cgroup(cgroup v2 單行 "0::<path>")推導本行程所在的 v2 cgroup 目錄。
    line = Path("/proc/self/cgroup").read_text(encoding="utf-8").strip()
    rel = line.split("::", 1)[-1] if "::" in line else "/"
    return Path("/sys/fs/cgroup") / rel.lstrip("/")


def _delegated_controllers() -> list[str]:
    # 讀 user@<uid>.service 委派子樹的 cgroup.controllers(cpu memory pids);讀不到即空(→ fail-closed)。
    uid = os.getuid()
    candidates = [
        Path(f"/sys/fs/cgroup/user.slice/user-{uid}.slice/user@{uid}.service/cgroup.controllers"),
        _self_cgroup_dir() / "cgroup.controllers",
    ]
    for path in candidates:
        try:
            return path.read_text(encoding="utf-8").split()
        except OSError:
            continue
    return []


def preflight_target_host(*, throwaway_root: str, expected_host: str = EXPECTED_TARGET_HOST_DEFAULT) -> dict[str, Any]:
    """Fail-closed OPS preflight, INDEPENDENT of the receipt builder (design §4.1).

    在任何真效果前執行:非 root、無 passwordless sudo、委派 cpu/mem/pids 到位、拋棄根在
    ``$XDG_RUNTIME_DIR`` 下且不在任何生產前綴、docker 未被觸及。任一違反 → ``FailClosedStop``。
    回傳可放進 receipt ``host_identity`` 的誠實 facts(全部通過才回傳)。
    """

    _require_target_host()
    if os.geteuid() == 0:
        raise FailClosedStop("target-host probe must be strictly non-root (euid==0 rejected)")
    if _passwordless_sudo_present():
        raise FailClosedStop("unexpected passwordless sudo present on target — fail-closed STOP")
    controllers = _delegated_controllers()
    if not REQUIRED_DELEGATED_CONTROLLERS <= set(controllers):
        raise FailClosedStop(
            f"missing delegated controllers; need {sorted(REQUIRED_DELEGATED_CONTROLLERS)}, saw {sorted(controllers)}"
        )
    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    real_root = os.path.realpath(throwaway_root)
    if not (real_root == os.path.realpath(xdg) or real_root.startswith(os.path.realpath(xdg) + os.sep)):
        raise FailClosedStop(f"throwaway root {real_root!r} is not under XDG_RUNTIME_DIR {xdg!r}")
    _assert_not_production_path(real_root)
    return {
        "expected_host": expected_host,
        "non_root_uid": True,
        "passwordless_sudo_present": False,
        "delegated_controllers": sorted(REQUIRED_DELEGATED_CONTROLLERS & set(controllers)),
        "deferred_root_only_controllers": list(DEFERRED_ROOT_ONLY_CONTROLLERS),
        "throwaway_root_under_runtime_dir": True,
    }


def _assert_not_production_path(path: str) -> None:
    real = os.path.realpath(path)
    for prefix in PRODUCTION_PATH_PREFIXES:
        if real == prefix or real.startswith(prefix + os.sep):
            raise FailClosedStop(f"target {real!r} is under a production path {prefix!r} — fail-closed STOP")


def _assert_non_root_boundary(*paths: str) -> None:
    """Per-primitive boundary re-assertion so it holds even on a DIRECT call (not just via preflight).

    每個會 spawn 子行程的 on-host primitive 起手都重申三條硬邊界:(1) 嚴格非 root(``euid!=0``);
    (2) 無 passwordless sudo(``sudo -n true`` rc!=0);(3) 每個被交付的路徑(realpath)都不在任何生產前綴下。
    任一違反 → ``FailClosedStop``。這樣即使有人繞過 ``preflight_target_host`` 直呼 primitive,root/生產路徑
    仍被 fail-closed 擋下。
    """

    if os.geteuid() == 0:
        raise FailClosedStop("target-host primitive must be strictly non-root (euid==0 rejected) — fail-closed STOP")
    if _passwordless_sudo_present():
        raise FailClosedStop("unexpected passwordless sudo present on target — fail-closed STOP")
    for path in paths:
        _assert_not_production_path(path)


# --------------------------------------------------------------------------- #
# on-host seam executors (REAL non-root primitives; each SKIPS on Mac)
# --------------------------------------------------------------------------- #
def _systemctl_user_show(unit: str, prop: str) -> str:
    result = _run(["systemctl", "--user", "show", unit, "-p", prop, "--value"], timeout=15)
    return result.stdout.decode("utf-8", "replace").strip()


def _scope_cgroup_dir(unit: str) -> Path | None:
    control_group = _systemctl_user_show(unit, "ControlGroup")
    if not control_group:
        return None
    return Path("/sys/fs/cgroup") / control_group.lstrip("/")


def _seam_record(seam_id: str, verdict: str, evidence: dict[str, Any], note: str, *, representativeness: str | None = None) -> dict[str, Any]:
    if verdict not in SEAM_VERDICTS:
        raise TargetHostProbeError(f"invalid seam verdict: {verdict!r}")
    record: dict[str, Any] = {
        "seam_id": seam_id,
        "verdict": verdict,
        "evidence_digest": _canonical_digest({"seam_id": seam_id, "verdict": verdict, "evidence": evidence}),
        "note": note,
    }
    if representativeness is not None:
        record["representativeness"] = representativeness
    return record


def probe_start_stop_on_host(*, launcher_argv: list[str], nonce: str) -> dict[str, Any]:
    """REAL start/stop: ``systemd-run --user --scope`` a long launcher, observe Active->dead."""

    _require_target_host()
    _assert_non_root_boundary()
    unit = f"aiml-probeB-{nonce}"
    proc = subprocess.Popen(  # noqa: S603 — abs-pinned argv, user-scope only
        ["systemd-run", "--user", "--scope", f"--unit={unit}.scope", "--", *launcher_argv],
        env={"PATH": os.environ.get("PATH", ""), "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "")},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    active_observed = False
    try:
        for _ in range(50):
            if _systemctl_user_show(f"{unit}.scope", "ActiveState") == "active":
                active_observed = True
                break
            time.sleep(0.1)
        _run(["systemctl", "--user", "stop", f"{unit}.scope"], timeout=15)
    finally:
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        # #5:即使 stop 逾時/失敗也清掉可能殘留的 failed 單元記錄(best-effort)。
        try:
            _run(["systemctl", "--user", "reset-failed", f"{unit}.scope"], timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    dead = _systemctl_user_show(f"{unit}.scope", "ActiveState") in {"inactive", "failed", "dead", ""}
    load = _systemctl_user_show(f"{unit}.scope", "LoadState")
    unit_absent = load in {"not-found", ""}
    verdict = SEAM_VERDICT_PASSED if (active_observed and dead and unit_absent) else SEAM_VERDICT_DEFERRED
    return _seam_record(
        SEAM_START_STOP, verdict,
        {"active_observed": active_observed, "dead_after_stop": dead, "unit_absent_after": unit_absent},
        _SEAM_NOTES[SEAM_START_STOP],
    )


def probe_cgroup_isolation_on_host(*, nonce: str, mem_max_bytes: int = 64 * 1024 * 1024, tasks_max: int = 16) -> dict[str, Any]:
    """REAL cgroup enforcement: drive OOM/CPU/fork under a limited scope, READ the cgroup files.

    設 ``MemoryMax/MemoryHigh/CPUQuota/TasksMax`` 於一個 transient scope,主動:配置超過
    MemoryMax(觀察 ``memory.events:oom_kill`` 遞增)、CPU busy-loop(觀察 ``cpu.stat`` 節流)、
    有界 fork(觀察 ``pids.events:max``)。三者皆自 scope 的 cgroup 目錄真讀,證明「enforcement」而
    非僅「set limits」。cpuset/io 為 root-only,記為延後精修(PM Q4)。
    """

    _require_target_host()
    _assert_non_root_boundary()
    unit = f"aiml-probeBcg-{nonce}.scope"
    # workload:main 全程存活以保住 scope(否則 scope 隨 main 死即被 systemd 拆除,計數讀不到)。
    #   1) pids:fork 至 TasksMax 觸 pids.events:max,隨後全數收屍釋放 slot 給 hog;
    #   2) cpu:busy-loop 觸 cpu.stat throttled_usec;
    #   3) mem:fork 一個 hog child 撐爆 MemoryMax → cgroup OOM 只殺 child(oom.group=0 + 下方 OOMPolicy=
    #      continue 使 systemd 不因成員被殺而拆 scope),main 收屍後短暫 linger 讓觀察者讀到 oom_kill。
    #      (舊版讓 main 自己被 OOM 殺 → scope 隨即拆除、oom_kill 恆讀成 0,即真 bug;此處修正。)
    workload = (
        "import os,sys,time\n"
        "kids=[]\n"
        "for _ in range(64):\n"
        "    try:\n"
        "        pid=os.fork()\n"
        "    except OSError:\n"
        "        break\n"
        "    if pid==0:\n"
        "        time.sleep(0.4); os._exit(0)\n"
        "    kids.append(pid)\n"
        "for k in kids:\n"
        "    try:\n"
        "        os.waitpid(k,0)\n"
        "    except OSError:\n"
        "        pass\n"
        "t=time.time()+1.0\n"
        "x=0\n"
        "while time.time()<t:\n"
        "    x+=1\n"
        "pid=os.fork()\n"
        "if pid==0:\n"
        "    buf=bytearray()\n"
        "    chunk=b'x'*(4*1024*1024)\n"
        "    while True:\n"
        "        buf+=chunk\n"
        "    os._exit(0)\n"
        "os.waitpid(pid,0)\n"
        "time.sleep(2.5)\n"
    )
    proc = subprocess.Popen(
        [
            "systemd-run", "--user", "--scope", f"--unit={unit}",
            "-p", f"MemoryMax={mem_max_bytes}", "-p", f"MemoryHigh={mem_max_bytes}",
            "-p", "CPUQuota=20%", "-p", f"TasksMax={tasks_max}", "-p", "OOMPolicy=continue",
            "--", sys.executable, "-I", "-c", workload,
        ],
        env={"PATH": os.environ.get("PATH", ""), "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "")},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    oom_kill = 0
    pids_max = 0
    throttled_usec = 0
    try:
        cgroup_dir = None
        for _ in range(50):
            cgroup_dir = _scope_cgroup_dir(unit)
            if cgroup_dir and cgroup_dir.exists():
                break
            time.sleep(0.1)
        deadline = time.time() + 8
        while time.time() < deadline and proc.poll() is None:
            if cgroup_dir and cgroup_dir.exists():
                oom_kill = max(oom_kill, _cgroup_keyed_value(cgroup_dir / "memory.events", "oom_kill"))
                pids_max = max(pids_max, _cgroup_keyed_value(cgroup_dir / "pids.events", "max"))
                throttled_usec = max(throttled_usec, _cgroup_keyed_value(cgroup_dir / "cpu.stat", "throttled_usec"))
            time.sleep(0.2)
        # #6:workload 退出後、stop/reset-failed 前再讀一次計數檔——若 OOM 落在兩次 poll 之間,
        # 這次補讀可避免偽 DEFERRED(cgroup 目錄尚未被 systemd 隨 scope 退出移除時仍讀得到)。
        if cgroup_dir and cgroup_dir.exists():
            oom_kill = max(oom_kill, _cgroup_keyed_value(cgroup_dir / "memory.events", "oom_kill"))
            pids_max = max(pids_max, _cgroup_keyed_value(cgroup_dir / "pids.events", "max"))
            throttled_usec = max(throttled_usec, _cgroup_keyed_value(cgroup_dir / "cpu.stat", "throttled_usec"))
    finally:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            _run(["systemctl", "--user", "stop", unit], timeout=10)
            _run(["systemctl", "--user", "reset-failed", unit], timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
    enforced = oom_kill > 0 and pids_max > 0 and throttled_usec > 0
    verdict = SEAM_VERDICT_PASSED if enforced else SEAM_VERDICT_DEFERRED
    note = _SEAM_NOTES[SEAM_CGROUP]
    if verdict == SEAM_VERDICT_DEFERRED:
        # DEFERRED 時掛精確的「哪個計數仍為 0」note,不掛成功感 note(誠實,勿誤讀為 PASS)。
        unmet = [name for name, val in (
            ("memory.events:oom_kill", oom_kill),
            ("pids.events:max", pids_max),
            ("cpu.stat:throttled_usec", throttled_usec),
        ) if val <= 0]
        note = f"cgroup enforcement not fully observed; counters still zero: {unmet} — DEFERRED"
    return _seam_record(
        SEAM_CGROUP, verdict,
        {
            "memory_events_oom_kill": oom_kill,
            "pids_events_max": pids_max,
            "cpu_stat_throttled_usec": throttled_usec,
            "controllers": sorted(REQUIRED_DELEGATED_CONTROLLERS),
            "root_only_deferred": list(DEFERRED_ROOT_ONLY_CONTROLLERS),
        },
        note,
    )


def _cgroup_keyed_value(path: Path, key: str) -> int:
    # 讀 cgroup 「key value」型檔案(memory.events / pids.events / cpu.stat)的某鍵值;缺檔即 0。
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] == key:
                return int(parts[1])
    except (OSError, ValueError):
        return 0
    return 0


# --------------------------------------------------------------------------- #
# network-denial child sources (differential seccomp egress proof).
# baseline(無過濾)與 seccomp(connect/sendto/sendmsg 拒絕)兩個子行程對同一 host/port 真跑;
# 唯一變數是 seccomp filter,把 CONNECTED 翻成 ENETUNREACH。HOST 以 !r 安全內插(repr→帶引號字面量),
# PORT 先 int() 再內插。兩者皆真讀核心回傳,絕不造假。
# --------------------------------------------------------------------------- #
_EGRESS_BASELINE_SRC = (
    "import socket,sys\n"
    "try:\n"
    "    socket.create_connection(({host!r},{port}),timeout=3)\n"
    "    print('CONNECTED')\n"
    "except OSError as e:\n"
    "    print('DENIED:%d' % (e.errno or 0))\n"
)
_EGRESS_SECCOMP_DENY_SRC = (
    "import ctypes,ctypes.util,socket,errno,sys\n"
    "libname = ctypes.util.find_library('seccomp') or 'libseccomp.so.2'\n"
    "try:\n"
    "    lib = ctypes.CDLL(libname, use_errno=True)\n"
    "except OSError:\n"
    "    print('NOLIB'); sys.exit(0)\n"
    "try:\n"
    "    lib.seccomp_init.restype = ctypes.c_void_p\n"
    "    lib.seccomp_init.argtypes = [ctypes.c_uint32]\n"
    "    lib.seccomp_syscall_resolve_name.restype = ctypes.c_int\n"
    "    lib.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]\n"
    "    lib.seccomp_rule_add.restype = ctypes.c_int\n"
    "    lib.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]\n"
    "    lib.seccomp_load.restype = ctypes.c_int\n"
    "    lib.seccomp_load.argtypes = [ctypes.c_void_p]\n"
    "except AttributeError:\n"
    "    print('NOSYM'); sys.exit(0)\n"
    "SCMP_ACT_ALLOW = 0x7fff0000\n"
    "ctx = lib.seccomp_init(SCMP_ACT_ALLOW)\n"
    "if not ctx:\n"
    "    print('INITNULL'); sys.exit(0)\n"
    "added = 0\n"
    "for nm in (b'connect', b'sendto', b'sendmsg'):\n"
    "    nr = lib.seccomp_syscall_resolve_name(nm)\n"
    "    if nr < 0:\n"
    "        continue\n"
    "    if lib.seccomp_rule_add(ctx, 0x00050000 | (errno.ENETUNREACH & 0xffff), nr, 0) == 0:\n"
    "        added += 1\n"
    "if added == 0:\n"
    "    print('NORULE'); sys.exit(0)\n"
    "if lib.seccomp_load(ctx) != 0:\n"
    "    print('LOADFAIL'); sys.exit(0)\n"
    "print('FILTER_LOADED:%d' % added)\n"
    "try:\n"
    "    socket.create_connection(({host!r},{port}),timeout=3)\n"
    "    print('CONNECTED')\n"
    "except OSError as e:\n"
    "    print('DENIED:%d' % (e.errno or 0))\n"
)
_SECCOMP_FILTER_FAULTS = frozenset({"NOLIB", "NOSYM", "INITNULL", "NORULE", "LOADFAIL"})


def probe_network_denial_on_host(*, egress_host: str = "1.1.1.1", egress_port: int = 443) -> dict[str, Any]:
    """REAL egress denial via seccomp (differential proof), fully non-root.

    A child installs a libseccomp ``SCMP_ACT_ERRNO(ENETUNREACH)`` filter on
    ``connect``/``sendto``/``sendmsg`` and THEN attempts egress → the kernel denies
    it (``ENETUNREACH``).  A second child on the SAME host/port with NO filter
    CONNECTs.  The only variable is the seccomp filter, so the CONNECTED→DENIED flip
    is the proof — no fake, real kernel enforcement, no root, no netns.

    Why not netns:``bwrap --unshare-net`` is unusable non-root on this host — it must
    be root inside its userns to bring up ``lo``, but the host denies unprivileged
    ``uid_map`` root-mapping and lacks ``newuidmap``/``newgidmap``, so bwrap treats the
    ``lo`` bring-up failure as fatal and never runs the child.  seccomp is the real,
    enforceable, observable, non-root egress-denial mechanism available here.

    PASS(``PASSED_TARGET_HOST``) requires: baseline CONNECTED (host truly has egress,
    so the denial is meaningful) AND the seccomp filter loaded AND the filtered child
    DENIED.  Any other outcome (libseccomp/symbol/init/rule/load fault, no baseline
    egress to differentiate, or a loaded filter that failed to deny) →
    ``DEFERRED_TARGET_HOST`` with the exact honest reason — never a forced PASS.
    """

    _require_target_host()
    _assert_non_root_boundary()
    # #6:egress_port 強制轉 int 再插值,杜絕字串注入類(host 以 !r repr 引號安全)。
    egress_port = int(egress_port)

    baseline = _run(
        [sys.executable, "-I", "-c", _EGRESS_BASELINE_SRC.format(host=egress_host, port=egress_port)],
        timeout=20,
    )
    baseline_out = baseline.stdout.decode("utf-8", "replace").strip()

    seccomp = _run(
        [sys.executable, "-I", "-c", _EGRESS_SECCOMP_DENY_SRC.format(host=egress_host, port=egress_port)],
        timeout=20,
    )
    seccomp_lines = [ln.strip() for ln in seccomp.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]
    seccomp_last = seccomp_lines[-1] if seccomp_lines else ""
    filter_fault = next((ln for ln in seccomp_lines if ln in _SECCOMP_FILTER_FAULTS), None)
    filter_loaded = any(ln.startswith("FILTER_LOADED") for ln in seccomp_lines)

    baseline_connected = baseline_out == "CONNECTED"
    seccomp_denied = seccomp_last.startswith("DENIED")
    # PASS 僅當:本機基線真有 egress(CONNECTED)、seccomp 過濾真裝上、且過濾把 egress 真拒(DENIED)。
    passed = baseline_connected and filter_loaded and filter_fault is None and seccomp_denied
    verdict = SEAM_VERDICT_PASSED if passed else SEAM_VERDICT_DEFERRED

    note = _SEAM_NOTES[SEAM_NETWORK_DENIAL]
    if verdict == SEAM_VERDICT_DEFERRED:
        if filter_fault:
            note = f"seccomp filter not installed ({filter_fault}); egress denial not enforced — DEFERRED"
        elif not baseline_connected:
            note = f"no baseline egress on host ({baseline_out!r}); cannot differentiate seccomp denial — DEFERRED"
        elif not seccomp_denied:
            note = f"seccomp filter loaded but egress not denied ({seccomp_last!r}) — DEFERRED"
        else:
            # 兜底:任何其他非 PASS 組合(如 FILTER_LOADED 行缺失)不得留成功感 note。
            note = f"seccomp egress denial not confirmed ({seccomp_lines}) — DEFERRED"

    return _seam_record(
        SEAM_NETWORK_DENIAL, verdict,
        {
            "mechanism": "seccomp SCMP_ACT_ERRNO(ENETUNREACH) on connect/sendto/sendmsg (libseccomp via ctypes)",
            "egress_target": f"{egress_host}:{egress_port}",
            "baseline_egress": baseline_out,
            "baseline_connected": baseline_connected,
            "seccomp_filter_loaded": filter_loaded,
            "seccomp_filter_fault": filter_fault,
            "seccomp_egress": seccomp_last,
            "seccomp_denied": seccomp_denied,
        },
        note,
    )


_NATIVE_PROBE_SONAME = "libaiml_probe_bundle.so"


def _stage_representative_so(bundle_dir: str) -> str | None:
    """COMPILE a tiny, unique-``soname`` ``.so`` INTO the content-addressed bundle; return its basename.

    關鍵:動態連結器以 ``DT_SONAME`` 去重——複製一份「系統既載入的 lib(如 ``libz``)」到 bundle,``CDLL`` 會
    回既有映射、``/proc/self/maps`` 只見系統路徑而非 bundle,無法證明「從 bundle 載入」(舊版真 bug)。改以
    ``cc``/``gcc`` 現編一個 **唯一 soname**(``libaiml_probe_bundle.so``)的小 ``.so`` 進 bundle:此 soname 從未被
    預載,``CDLL(bundle/該.so)`` 必真映射 bundle 內那份,``maps`` 前綴即證 bundle 來源。代表性(PM Q3):符號
    僅為一個 trivial ``aiml_probe_symbol``,完整 LR2-sealed 原生 closure 屬 S2.3。
    無編譯器 → 回 ``None``(呼叫端誠實走 import-only 的 representativeness-flagged DEFERRED,絕不造假)。
    """

    compiler = shutil.which("cc") or shutil.which("gcc")
    if compiler is None:
        return None
    try:
        os.makedirs(bundle_dir, exist_ok=True)
        src = os.path.join(bundle_dir, "_aiml_probe_src.c")
        dest = os.path.join(bundle_dir, _NATIVE_PROBE_SONAME)
        with open(src, "w", encoding="utf-8") as fh:
            fh.write("int aiml_probe_symbol(void){ return 42; }\n")
        result = _run(
            [compiler, "-shared", "-fPIC", f"-Wl,-soname,{_NATIVE_PROBE_SONAME}", "-o", dest, src],
            timeout=30,
        )
        try:
            os.remove(src)  # bundle 只留 .so(內容定址),不留 .c 原始檔。
        except OSError:
            pass
        if result.returncode != 0 or not os.path.exists(dest):
            return None
        return _NATIVE_PROBE_SONAME
    except (OSError, subprocess.SubprocessError):
        return None


def _parse_load_lines(res: subprocess.CompletedProcess) -> list[str]:
    return [ln.strip() for ln in res.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def _run_native_load(load_src: str, *, ro_bundle: str | None) -> tuple[list[str], str, str]:
    """Run a native-load probe child, PREFERRING a ``bwrap`` ro-bind mount sandbox; fall back to a
    direct (no-mount-sandbox) run when bwrap cannot set up an unprivileged userns on this host.

    本 host(Ubuntu, ``apparmor_restrict_unprivileged_userns=1``)禁非特權 userns → bwrap 無論 ro-bind 或
    ``--unshare-*`` 都在 uid_map/lo 階段 fatal,無法跑子行程。故:先試 bwrap(掛載隔離);若其輸出無有效
    ``LOADED``/``NOLOAD`` 行(= bwrap setup 失敗)→ 直接跑。maps-origin 對「從 bundle 載入」的證明在兩模式皆真
    (唯一 soname 保證非系統去重);掛載隔離為額外保證,在此 host 因 AppArmor 不可得,誠實記為 direct 模式。
    回傳 ``(out_lines, sandbox_mode, sandbox_note)``。
    """

    if shutil.which("bwrap") is not None:
        binds = ["--ro-bind", ro_bundle, ro_bundle] if ro_bundle else []
        cmd = [
            "bwrap", *binds, "--ro-bind", "/usr", "/usr", "--ro-bind", "/lib", "/lib",
            "--ro-bind-try", "/lib64", "/lib64", "--proc", "/proc", "--dev", "/dev",
            "--", sys.executable, "-I", "-c", load_src,
        ]
        try:
            lines = _parse_load_lines(_run(cmd, timeout=20))
            if any(ln in ("LOADED", "NOLOAD") for ln in lines):
                return lines, "bwrap_ro_bind", "mount-isolated (bwrap ro-bind) sandbox"
        except (OSError, subprocess.SubprocessError):
            pass
    lines = _parse_load_lines(_run([sys.executable, "-I", "-c", load_src], timeout=20))
    return lines, "direct_no_sandbox", (
        "bwrap mount-isolation unavailable non-root (AppArmor apparmor_restrict_unprivileged_userns=1); "
        "direct load — maps-origin proof still real, mount-isolated variant deferred"
    )


def probe_native_lib_loading_on_host(*, bundle_dir: str, representative_import: str = "ctypes") -> dict[str, Any]:
    """REAL native-lib load: compile a unique-``soname`` ``.so`` into the bundle, dlopen THAT, assert
    ``/proc/self/maps`` bundle origin AND that its symbol is callable.

    現編一個 **唯一 soname** 的代表性 ``.so`` 進內容定址 bundle(避開動態連結器 soname 去重),以
    ``ctypes.CDLL(bundle_path)`` 載入「bundle 內那份」,真斷言 ``/proc/self/maps`` 內該 ``.so`` 的解析來源前綴 ==
    bundle,並真呼叫其符號(``aiml_probe_symbol`` → 42)證明「確實載入且可執行」而非只是路徑字串比對。載入優先在
    bwrap ro-bind 掛載沙箱內;本 host AppArmor 禁非特權 userns 使 bwrap 不可用 → 誠實退化為直接載入(``sandbox_mode
    =direct_no_sandbox``),maps-origin 仍真證 bundle 來源。三者(loaded/origin_bundle/symbol=42)皆真 → ``PASSED``;
    任一未證 → ``DEFERRED``(不掛假 note)。若無法真備 ``.so``(缺編譯器)→ 只記代表性 import、``representativeness``-
    flagged 且 ``DEFERRED``。代表性(PM Q3):符號僅一個 trivial ``aiml_probe_symbol``,完整 LR2-sealed 原生 closure 屬 S2.3。
    """

    _require_target_host()
    _assert_non_root_boundary(bundle_dir)
    staged = _stage_representative_so(bundle_dir)
    if staged is None:
        # 無編譯器:只跑代表性 import(bwrap 優先、否則直接),不宣稱 bundle 來源;representativeness-flagged 且 DEFERRED。
        import_src = (
            "import importlib,sys\n"
            f"m=importlib.import_module({representative_import!r})\n"
            "print('LOADED' if m else 'NOLOAD')\n"
        )
        lines, mode, _snote = _run_native_load(import_src, ro_bundle=None)
        loaded = bool(lines) and lines[0] == "LOADED"
        return _seam_record(
            SEAM_NATIVE_LIB, SEAM_VERDICT_DEFERRED,
            {"loaded": loaded, "representative_import": representative_import, "bundle_so_staged": False, "sandbox_mode": mode},
            _NATIVE_IMPORT_ONLY_NOTE, representativeness=NATIVE_REPRESENTATIVE,
        )
    bundle_so = os.path.join(bundle_dir, staged)
    # 載入 bundle 內那份 .so,讀 /proc/self/maps 判斷解析來源是否為 bundle 路徑,並真呼叫其符號(回 42)。
    load_src = (
        "import ctypes,sys\n"
        f"p={bundle_so!r}\n"
        "ok=False; sym=None\n"
        "try:\n"
        "    h=ctypes.CDLL(p)\n"
        "    h.aiml_probe_symbol.restype=ctypes.c_int\n"
        "    sym=h.aiml_probe_symbol()\n"
        "    ok=True\n"
        "except OSError:\n"
        "    ok=False\n"
        "maps=open('/proc/self/maps').read()\n"
        "print('LOADED' if ok else 'NOLOAD')\n"
        "print('ORIGIN_BUNDLE' if (p in maps) else 'ORIGIN_OTHER')\n"
        "print('SYM=%s' % (sym,))\n"
    )
    lines, mode, snote = _run_native_load(load_src, ro_bundle=bundle_dir)
    loaded = bool(lines) and lines[0] == "LOADED"
    origin_bundle = len(lines) >= 2 and lines[1] == "ORIGIN_BUNDLE"
    sym_ok = any(ln == "SYM=42" for ln in lines)
    # 唯有真載入 + maps 證 bundle 來源 + 符號真回 42 才 PASS;否則誠實 DEFERRED(不掛假 note)。
    verdict = SEAM_VERDICT_PASSED if (loaded and origin_bundle and sym_ok) else SEAM_VERDICT_DEFERRED
    if verdict == SEAM_VERDICT_PASSED:
        note = f"unique-soname .so compiled into bundle; CDLL loaded from bundle path (maps-origin confirmed, symbol=42); {snote}"
    else:
        note = (
            f"native-lib bundle-origin not fully confirmed (loaded={loaded}, origin_bundle={origin_bundle}, "
            f"symbol_ok={sym_ok}); {snote} — DEFERRED"
        )
    return _seam_record(
        SEAM_NATIVE_LIB, verdict,
        {"loaded": loaded, "maps_origin_bundle": origin_bundle, "symbol_ok": sym_ok, "bundle_so": staged,
         "bundle_so_staged": True, "sandbox_mode": mode},
        note, representativeness=NATIVE_REPRESENTATIVE,
    )


def probe_immutable_closure_on_host(*, deploy_root: str) -> dict[str, Any]:
    """REAL immutable closure + persistence: content-addressed bundle, atomic swap, digest re-derived.

    復用 S1.5 ``artifact_*`` 原子 generation-pointer swap:init→pre digest→interrupted apply(指標不
    swap,digest==pre)→apply(digest!=pre)→rollback 回 prior(post==pre)。再重讀一次 state digest
    證明重啟後 digest 可重推導(內容定址不變性)。呼叫端負責 teardown(見 failure_rollback_cleanup)。
    """

    _require_target_host()
    prior_files = {
        "bin/launch_contract.txt": (
            b"# absolute-pinned launch (no PATH lookup, no /usr/bin/python3 fallback)\n"
            b"exec ${BUNDLE}/bin/python3 -I -m aiml_runtime\n"
        ),
        "manifest.json": b'{"candidate":"content_addressed_fixed_path","generation":0}\n',
    }
    new_files = {
        "bin/launch_contract.txt": prior_files["bin/launch_contract.txt"],
        "manifest.json": b'{"candidate":"content_addressed_fixed_path","generation":1}\n',
    }
    _assert_non_root_boundary(deploy_root)
    prior = ce.artifact_deploy_root_init(deploy_root, prior_bundle_files=prior_files)
    pre = ce.artifact_state_digest(deploy_root)
    interrupted = ce.artifact_apply_interrupted(deploy_root, new_bundle_files={"manifest.json": b'{"g":"x"}\n'})
    _new_hash, applied = ce.artifact_apply(deploy_root, new_bundle_files=new_files)
    post = ce.artifact_rollback(deploy_root, prior_hash=prior)
    re_derived = ce.artifact_state_digest(deploy_root)
    ok = interrupted == pre and applied != pre and post == pre and re_derived == post
    verdict = SEAM_VERDICT_PASSED if ok else SEAM_VERDICT_DEFERRED
    return _seam_record(
        SEAM_IMMUTABLE_CLOSURE, verdict,
        {"pre": pre, "interrupted_eq_pre": interrupted == pre, "applied_ne_pre": applied != pre,
         "post_eq_pre": post == pre, "re_derived_stable": re_derived == post},
        _SEAM_NOTES[SEAM_IMMUTABLE_CLOSURE],
    )


def probe_failure_rollback_cleanup_on_host(*, nonce: str, launcher_argv: list[str], teardown_root: str) -> dict[str, Any]:
    """REAL failure/rollback/cleanup: kill + restart from the same bundle; teardown + INDEPENDENT residue check."""

    _require_target_host()
    _assert_non_root_boundary(teardown_root)
    unit = f"aiml-probeBfrc-{nonce}.scope"

    def _start() -> subprocess.Popen:
        return subprocess.Popen(
            ["systemd-run", "--user", "--scope", f"--unit={unit}", "--", *launcher_argv],
            env={"PATH": os.environ.get("PATH", ""), "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "")},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    killed = restarted = False
    proc = _start()
    try:
        for _ in range(50):
            if _systemctl_user_show(unit, "ActiveState") == "active":
                break
            time.sleep(0.1)
        _run(["systemctl", "--user", "kill", unit], timeout=10)
        killed = True
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        # restart from the SAME immutable bundle (new scope, same launcher argv)。
        proc2 = _start()
        for _ in range(50):
            if _systemctl_user_show(unit, "ActiveState") == "active":
                restarted = True
                break
            time.sleep(0.1)
        _run(["systemctl", "--user", "stop", unit], timeout=10)
        try:
            proc2.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc2.kill()
    finally:
        try:
            _run(["systemctl", "--user", "reset-failed", unit], timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
        shutil.rmtree(teardown_root, ignore_errors=True)
    residue = independent_postcheck_on_host(unit=unit, teardown_root=teardown_root)
    ok = killed and restarted and residue["no_residue"]
    verdict = SEAM_VERDICT_PASSED if ok else SEAM_VERDICT_DEFERRED
    return _seam_record(
        SEAM_FAILURE_ROLLBACK_CLEANUP, verdict,
        {"killed": killed, "restarted_from_same_bundle": restarted, **residue},
        _SEAM_NOTES[SEAM_FAILURE_ROLLBACK_CLEANUP],
    )


def independent_postcheck_on_host(*, unit: str, teardown_root: str) -> dict[str, Any]:
    """INDEPENDENT residue check (distinct verifier): unit NoSuchUnit, cgroup gone, temp gone."""

    _require_target_host()
    load = _systemctl_user_show(unit, "LoadState")
    unit_absent = load in {"not-found", ""}
    cgroup_dir = _scope_cgroup_dir(unit)
    cgroup_gone = cgroup_dir is None or not cgroup_dir.exists()
    temp_gone = not os.path.exists(teardown_root)
    return {
        "unit_absent": unit_absent,
        "cgroup_gone": cgroup_gone,
        "temp_gone": temp_gone,
        "no_residue": unit_absent and cgroup_gone and temp_gone,
    }


def probe_pg_identity_on_host(*, pg_readonly_identity_receipt_digest: str) -> dict[str, Any]:
    """PLUGGABLE PG-identity seam: REAL non-root disposable initdb cluster -> 42501, else honestly DEFERRED.

    ``initdb``/``pg_ctl`` 可解析(``shutil.which`` 或 ``/usr/lib/postgresql/*/bin/``)→ 於
    ``$XDG_RUNTIME_DIR`` 下真建一個非 root、socket-only、拋棄式 initdb 叢集,唯讀角色 ``SET ROLE``
    被真實拒絕(SQLSTATE ``42501``),拆除叢集;唯有觀察到真 42501 才回 ``PASSED_TARGET_HOST``。
    ``initdb`` 缺席 → 綁 S1.1 receipt digest 並標 ``DEFERRED_TARGET_HOST``;initdb 在但真跑未觀察到
    42501(異常)→ 同樣誠實 ``DEFERRED_TARGET_HOST``。**永不造假**:server 缺席/真跑失敗就誠實延後,
    裝上並成功即零代碼變更自動翻真。prod PG(:5432)完全不觸——拋棄叢集是另建的一次性 socket。
    """

    _require_target_host()
    _assert_non_root_boundary()
    initdb = _resolve_pg_binary("initdb")
    pg_ctl = _resolve_pg_binary("pg_ctl")
    if not (initdb and pg_ctl):
        return _seam_record(
            SEAM_PG_IDENTITY, SEAM_VERDICT_DEFERRED,
            {"mode": PG_MODE_DEFERRED, "bound_s11_receipt_digest": pg_readonly_identity_receipt_digest},
            _PG_DEFERRED_NOTE,
        )
    # 真跑拋棄式叢集,觀察唯讀角色 SET ROLE 的真實 42501(非硬編);唯有真觀察到才 PASS。
    observed_sqlstate = _run_disposable_pg_identity_cluster(initdb, pg_ctl)
    if observed_sqlstate == PG_IDENTITY_SQLSTATE:
        return _seam_record(
            SEAM_PG_IDENTITY, SEAM_VERDICT_PASSED,
            {"mode": PG_MODE_REAL, "observed_sqlstate": observed_sqlstate,
             "bound_s11_receipt_digest": pg_readonly_identity_receipt_digest},
            _SEAM_NOTES[SEAM_PG_IDENTITY],
        )
    return _seam_record(
        SEAM_PG_IDENTITY, SEAM_VERDICT_DEFERRED,
        {"mode": PG_MODE_DEFERRED, "initdb_present": True, "observed_sqlstate": observed_sqlstate,
         "bound_s11_receipt_digest": pg_readonly_identity_receipt_digest},
        _PG_RUN_FAILED_NOTE,
    )


def _resolve_pg_binary(name: str) -> str | None:
    # 解析未必在 $PATH 上的版本化 PG 二進位(Debian/Ubuntu:/usr/lib/postgresql/<ver>/bin/)。
    found = shutil.which(name)
    if found:
        return found
    base = Path("/usr/lib/postgresql")
    matches = sorted(str(path) for path in base.glob(f"*/bin/{name}")) if base.exists() else []
    return matches[-1] if matches else None


def _initdb_available() -> bool:
    # 真跑需 initdb 與 pg_ctl 皆可解析。
    return bool(_resolve_pg_binary("initdb") and _resolve_pg_binary("pg_ctl"))


def _run_disposable_pg_identity_cluster(initdb: str, pg_ctl: str) -> str | None:
    """Run a REAL non-root socket-only disposable initdb cluster; return the RO ``SET ROLE`` SQLSTATE (else None).

    復用 S1.1 ``agent_governance_pg_readonly_identity`` 的連線/探針邏輯(``psycopg2`` over socket,絕不
    shell 出 ``psql``)。叢集建於 ``$XDG_RUNTIME_DIR`` 下、``listen_addresses=''`` 純 socket,與 prod PG
    (:5432)完全隔離。任何錯誤 → 回 ``None``(呼叫端誠實 DEFERRED,不造假)。``finally`` 強制停機 +
    rmtree(完整拆除,無殘留)。
    """

    import agent_governance_pg_readonly_identity as pg  # 延遲匯入,結構測試無需驅動即可載入本模組。
    try:
        import psycopg2
    except ImportError:
        return None

    _assert_non_root_boundary()
    uid = os.getuid()
    xdg = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
    # #4:initdb 前先確認 XDG 根與 mkdtemp 結果都不在任何生產前綴下(拋棄叢集絕不落地生產路徑)。
    _assert_not_production_path(xdg)
    tmp = tempfile.mkdtemp(prefix="aiml_s16b_pg_", dir=xdg)
    _assert_not_production_path(tmp)
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    clean_env = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}
    ro_role, writer_role, database = "aiml_s16b_ro", "aiml_s16b_writer", "postgres"
    started = False
    try:
        subprocess.run(
            [initdb, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
            env=clean_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90, check=True,
        )
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
        subprocess.run(
            [pg_ctl, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
            env=clean_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60, check=True,
        )
        started = True
        # superuser(socket trust)建唯讀角色 + 一個 writer 角色作 SET ROLE 提權目標。
        connection = psycopg2.connect(host=sock_dir, dbname=database, user="postgres", connect_timeout=10)
        try:
            connection.autocommit = True
            cursor = connection.cursor()
            cursor.execute(f"CREATE ROLE {writer_role} LOGIN")
            cursor.execute(f"CREATE ROLE {ro_role} LOGIN")
        finally:
            connection.close()
        params = pg.build_readonly_connection_params(
            endpoint_class="unix_socket_allowlisted", database=database, role=ro_role, socket_dir=sock_dir,
        )
        result = pg.run_readonly_probe(params, escalation_target_role=writer_role)
        return str(result.role_escalation_denied.get("observed_sqlstate"))
    except Exception:  # noqa: BLE001 — 真跑失敗(initdb/pg_ctl/psycopg2 任一)一律誠實 DEFERRED,絕不造假
        return None
    finally:
        # #5:無條件拆除——即使 start 在 spawn 後逾時(started 仍 False),只要有 postmaster.pid 就強停,
        # 杜絕孤兒 postmaster。先 pg_ctl immediate stop,失敗再直接 kill pid,最後 rmtree。
        _force_stop_pg_cluster(pg_ctl, data_dir, clean_env, started=started)
        shutil.rmtree(tmp, ignore_errors=True)


def _force_stop_pg_cluster(pg_ctl: str, data_dir: str, clean_env: dict[str, str], *, started: bool) -> None:
    """Unconditional disposable-cluster stop: kill any postmaster (via postmaster.pid) regardless of ``started``.

    只要 ``<data_dir>/postmaster.pid`` 存在,就先 ``pg_ctl -m immediate stop``;失敗再直接對 pidfile 首行 PID
    送 SIGKILL。這樣即使 ``pg_ctl start`` 在 spawn 出 postmaster 後才逾時(``started`` 仍 False),也不留孤兒。
    """

    pid_path = os.path.join(data_dir, "postmaster.pid")
    if not (started or os.path.exists(pid_path)):
        return
    try:
        subprocess.run(
            [pg_ctl, "-D", data_dir, "-m", "immediate", "stop"],
            env=clean_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass
    # pg_ctl 失敗仍殘留 pidfile → 直接對 postmaster PID 送 SIGKILL(pidfile 首行即 PID)。
    if os.path.exists(pid_path):
        try:
            pid = int(Path(pid_path).read_text(encoding="utf-8").splitlines()[0].strip())
            os.kill(pid, 9)
        except (OSError, ValueError, IndexError):
            pass


def pg_identity_mode_on_host() -> str:
    """Return the pluggable PG-identity mode for THIS node (real cluster vs server-absent-deferred)."""

    _require_target_host()
    return PG_MODE_REAL if _initdb_available() else PG_MODE_DEFERRED


# --------------------------------------------------------------------------- #
# pure seam-verdict helpers (Mac-testable; no host contact)
# --------------------------------------------------------------------------- #
def oci_non_satisfiable_seams() -> list[dict[str, Any]]:
    """Every OCI target-host seam is NON_SATISFIABLE_NON_ROOT (PM Q1 boundary-driven non-selection)."""

    return [
        _seam_record(seam_id, SEAM_VERDICT_NON_SATISFIABLE, {"boundary": "non_root_user_scope"}, OCI_NON_SATISFIABLE_REASON)
        for seam_id in TARGET_HOST_SEAMS
    ]


def synthesize_fixed_path_seams(
    pg_mode: str,
    *,
    evidence_marker: str = EVIDENCE_STRUCTURAL,
    independent_postcheck_attached: bool = False,
) -> list[dict[str, Any]]:
    """Build the 8 fixed-path seam records for the choice logic (STRUCTURAL synthesis for Mac tests).

    真跑於 trade-core 時,``run_target_host_probe`` 以每個 on-host executor 的真觀察組出這 8 個
    record;此函式供 Mac 結構測試/參照以誠實的 STRUCTURAL 佔位組出(不宣稱真跑)。``pg_mode`` 決定
    PG-identity seam 是 DEFERRED(server 缺席)或 PASSED(真叢集)。``independent_postcheck_attached``
    預設 False:applier 自跑時 ``independent_postcheck`` 為 DEFERRED(applier 無法自證獨立性);
    唯有 distinct 驗證者經 ``attach_independent_postcheck`` 附掛真殘留觀察後才 PASSED。
    """

    if pg_mode not in PG_MODES:
        raise TargetHostProbeError(f"unrecognized pg_identity_mode: {pg_mode!r}")
    records: list[dict[str, Any]] = []
    for seam_id in TARGET_HOST_SEAMS:
        if seam_id == SEAM_PG_IDENTITY and pg_mode == PG_MODE_DEFERRED:
            verdict, note = SEAM_VERDICT_DEFERRED, _PG_DEFERRED_NOTE
        elif seam_id == SEAM_INDEPENDENT_POSTCHECK and not independent_postcheck_attached:
            verdict, note = SEAM_VERDICT_DEFERRED, _INDEPENDENT_DEFERRED_NOTE
        else:
            verdict, note = SEAM_VERDICT_PASSED, _SEAM_NOTES[seam_id]
        representativeness = NATIVE_REPRESENTATIVE if seam_id == SEAM_NATIVE_LIB else None
        records.append(
            _seam_record(seam_id, verdict, {"synthesis": evidence_marker, "pg_mode": pg_mode}, note, representativeness=representativeness)
        )
    return records


def run_target_host_probe(
    *,
    throwaway_root: str,
    nonce: str | None = None,
    pg_readonly_identity_receipt_digest: str,
    launcher_argv: list[str] | None = None,
    target_host_capture_digest: str | None = None,
) -> dict[str, Any]:
    """Orchestrate the REAL candidate-B target-host probe on trade-core (SKIPS on Mac).

    在 target host 依序真跑八個 seam(preflight → start/stop → cgroup → network → native →
    immutable → failure/rollback/cleanup → pg-identity),回傳 ``{host_identity, pg_identity_mode,
    fixed_path_seams, target_host_capture_digest, evidence_class=ATTESTED}``,供
    ``build_target_host_choice_receipt`` 直接消費。Mac 上呼叫即 ``TargetHostUnavailableError`` → 乾淨跳過。

    ``independent_postcheck`` seam 在此(applier 自跑)恆為 ``DEFERRED_TARGET_HOST``——applier 無法自證
    獨立性,故自跑 receipt 為 ``PROVISIONAL_PENDING_LINUX``(指名 independent_postcheck),須由 distinct OPS
    驗證者事後以 ``attach_independent_postcheck`` 附掛真殘留觀察才升為 PASSED/BINDING。
    ``target_host_capture_digest`` 由 governed on-host capture(``command_capture_v2``)提供(參數或
    ``AIML_TARGET_HOST_CAPTURE_DIGEST`` env);缺席即 ``None``,receipt 過不了 ``require_target_host_attested``。
    頂層 ``try/finally`` 保證即使 raw caller 直呼,也 rmtree ``throwaway_root`` 並 best-effort 掃除殘留 scope。
    """

    _require_target_host()
    nonce = nonce or uuid.uuid4().hex[:12]
    launcher_argv = launcher_argv or [sys.executable, "-I", "-c", "import time; time.sleep(30)"]
    capture_digest = target_host_capture_digest or os.environ.get("AIML_TARGET_HOST_CAPTURE_DIGEST")
    try:
        host_identity = preflight_target_host(throwaway_root=throwaway_root)
        immut_root = os.path.join(throwaway_root, "bundle_store")
        bundle_dir = os.path.join(throwaway_root, "native_bundle")
        os.makedirs(bundle_dir, exist_ok=True)
        # PG seam 真跑一次;pg_identity_mode 由其真實 verdict 導出,確保 mode 與 seam 恆一致
        # (真 42501 → REAL/PASSED;缺 server 或真跑失敗 → DEFERRED),絕不出現 mode/seam 矛盾。
        pg_seam = probe_pg_identity_on_host(pg_readonly_identity_receipt_digest=pg_readonly_identity_receipt_digest)
        pg_identity_mode = PG_MODE_REAL if pg_seam["verdict"] == SEAM_VERDICT_PASSED else PG_MODE_DEFERRED
        seams = [
            probe_start_stop_on_host(launcher_argv=launcher_argv, nonce=nonce),
            probe_cgroup_isolation_on_host(nonce=nonce),
            probe_network_denial_on_host(),
            probe_native_lib_loading_on_host(bundle_dir=bundle_dir),
            probe_immutable_closure_on_host(deploy_root=immut_root),
            probe_failure_rollback_cleanup_on_host(nonce=nonce, launcher_argv=launcher_argv, teardown_root=os.path.join(throwaway_root, "frc")),
            pg_seam,
            # #1:applier 自跑無法自證獨立性 → independent_postcheck 恆 DEFERRED,待 distinct 驗證者附掛。
            _seam_record(
                SEAM_INDEPENDENT_POSTCHECK, SEAM_VERDICT_DEFERRED,
                {"applier_only": True, "pending_distinct_verifier": True}, _INDEPENDENT_DEFERRED_NOTE,
            ),
        ]
        return {
            "host_identity": host_identity,
            "pg_identity_mode": pg_identity_mode,
            "fixed_path_seams": seams,
            "target_host_capture_digest": capture_digest,
            "evidence_class": EVIDENCE_ATTESTED,
        }
    finally:
        # #5:頂層無條件收尾——rmtree throwaway_root 並 best-effort 掃除任何殘留 aiml-probe* scope。
        shutil.rmtree(throwaway_root, ignore_errors=True)
        for verb in ("stop", "reset-failed"):
            try:
                _run(["systemctl", "--user", verb, "aiml-probe*"], timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass


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
    return {
        "expected_host": expected_host,
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
        # 真確性不可靠自報 label:必須綁一個非空的 governed on-host command_capture_v2 digest。
        if not DIGEST_RE.fullmatch(str(receipt.get("target_host_capture_digest") or "")):
            errors.append(
                "target-host choice receipt lacks a bound governed on-host command_capture_v2 digest "
                "(target_host_capture_digest); a self-reported evidence_class cannot certify the target-host exit"
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
    return {
        "expected_host": EXPECTED_TARGET_HOST_DEFAULT,
        "non_root_uid": True,
        "passwordless_sudo_present": False,
        "delegated_controllers": sorted(REQUIRED_DELEGATED_CONTROLLERS),
        "deferred_root_only_controllers": list(DEFERRED_ROOT_ONLY_CONTROLLERS),
        "throwaway_root_under_runtime_dir": True,
    }


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
) -> dict[str, Any]:
    """Build a PLATFORM_OR_EXTERNAL_ATTESTED (status=PASS) reference, as the REAL trade-core run would.

    表達「真出口長什麼樣」的 shape 參照:``evidence_class=ATTESTED`` + invoked + teardown → ``status=PASS``。
    ``pg_mode=real_initdb_cluster`` 且 ``independent_postcheck_attached`` ⇒ 全 seam PASSED ⇒ ``BINDING``。
    ``independent_postcheck_attached=False`` ⇒ independent_postcheck DEFERRED(applier 自跑形)⇒
    ``PROVISIONAL_PENDING_LINUX`` 指名 independent_postcheck。``capture_digest=None``(預設)⇒ 無綁 governed
    on-host capture ⇒ **過不了 ``require_target_host_attested``**(這是刻意的:Mac 參照無法自證真出口,唯有真跑
    綁上 governed ``command_capture_v2`` digest 才可被採信)。
    """

    return build_target_host_choice_receipt(
        caller="target_host_probe_v1:attested-reference",
        platform=detect_platform(),
        target_class=TARGET_CLASS,
        host_identity=_structural_host_identity(),
        apply_actor_node="s16b_apply_actor",
        postcheck_verifier_node="s16b_independent_verifier",
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
    )


# --------------------------------------------------------------------------- #
# bypass-negatives (fail-closed; each REALLY triggers the rejection, no rubber stamp)
# --------------------------------------------------------------------------- #
def _resign(receipt: dict[str, Any]) -> dict[str, Any]:
    receipt = copy.deepcopy(receipt)
    receipt.pop("self_digest", None)
    receipt["self_digest"] = receipt_digest(receipt)
    return receipt


def _reject_or_vacuous(receipt: dict[str, Any], *, needle: str, now: str) -> None:
    errors = validate_target_host_choice_receipt(receipt, now=now)
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
    """Run all sixteen bypass-negatives and return their REJECTED case records."""

    return [run_bypass_negative(kind, now=now) for kind in BYPASS_KINDS]

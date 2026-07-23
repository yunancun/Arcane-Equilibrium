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
    SEAM_FAILURE_ROLLBACK_CLEANUP: "systemctl --user kill + restart the deployed content-addressed bundle; restarted process resolves (proc cwd) under the rolled-back bundle root; interrupted apply never swaps; teardown + reset-failed + rmtree",
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
    "target_host_capture",
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

# 十八個 fail-closed bypass 種類;交付需全部真觸拒(非橡皮圖章)。
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
    # #T3:觀察 host 與 expected 不符(冒稱 target host)。
    "host_identity_spoofed",
    # #T1:ATTESTED + 裸 digest 但無內嵌 command_capture_v2 artifact(冒充真出口)。
    "attested_digest_without_capture_artifact",
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
    # #T3:記錄前先真觀察本機 nodename;與 expected_host 不符即 fail-closed。否則任一非 root Linux 盒
    # 只要設 AIML_TARGET_HOST_PROBE=1 就能發出「聲稱是 trade-core」的 receipt——這裡把 expected 綁到真 observed。
    observed_host = os.uname().nodename
    if observed_host != expected_host:
        raise FailClosedStop(
            f"observed host {observed_host!r} != expected_host {expected_host!r}; refusing to record a "
            "target-host receipt on an unexpected node — fail-closed STOP"
        )
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
        "observed_host": observed_host,
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


def probe_failure_rollback_cleanup_on_host(
    *, nonce: str, launcher_argv: list[str], teardown_root: str, bundle_root: str | None = None
) -> dict[str, Any]:
    """REAL failure/rollback/cleanup: kill + RESTART THE DEPLOYED BUNDLE; teardown + INDEPENDENT residue check.

    ``launcher_argv`` 必須被 ``run_target_host_probe`` 綁到真內容定址 bundle(``bundle_root`` = 佈署後
    rolled-back 的 active bundle 目錄);restart 後不僅觀察 scope 復活,還讀 restart scope 的 cgroup.procs、
    解析各 pid 的 ``/proc/<pid>/cwd`` 真實路徑,斷言其位於 ``bundle_root`` 之下(證明「重啟的正是那個選定的
    固定路徑 bundle」而非任意 sleeper)。唯有 killed AND restarted AND 解析回 bundle AND 殘留全清才 PASS;
    否則誠實 DEFERRED,絕不以「隨便一個 sleeper 能殺能重跑」冒充。``bundle_root=None``(直呼/測試)時退回
    僅觀察 restart(不做 bundle 解析)——真跑一律由 driver 供 bundle_root。
    """

    _require_target_host()
    _assert_non_root_boundary(*([teardown_root, bundle_root] if bundle_root else [teardown_root]))
    unit = f"aiml-probeBfrc-{nonce}.scope"

    def _start() -> subprocess.Popen:
        return subprocess.Popen(
            ["systemd-run", "--user", "--scope", f"--unit={unit}", "--", *launcher_argv],
            env={"PATH": os.environ.get("PATH", ""), "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR", "")},
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    killed = restarted = resolves_to_bundle = False
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
        # restart the SAME deployed content-addressed bundle (new scope, same bundle-pinned launcher argv)。
        proc2 = _start()
        for _ in range(50):
            if _systemctl_user_show(unit, "ActiveState") == "active":
                restarted = True
                break
            time.sleep(0.1)
        # #T2:restart 存活後,在停機前解析 restart 行程真的落在 bundle_root 下(否則證不了「重啟的是 bundle」)。
        if restarted and bundle_root is not None:
            resolves_to_bundle = _restarted_process_resolves_to_bundle(unit, bundle_root)
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
    # bundle_root 有給(真跑)時,resolves_to_bundle 是 PASS 的必要條件;沒給(直呼)時不強制,退回舊行為。
    bundle_ok = resolves_to_bundle if bundle_root is not None else True
    ok = killed and restarted and bundle_ok and residue["no_residue"]
    verdict = SEAM_VERDICT_PASSED if ok else SEAM_VERDICT_DEFERRED
    note = _SEAM_NOTES[SEAM_FAILURE_ROLLBACK_CLEANUP]
    if verdict == SEAM_VERDICT_DEFERRED:
        note = (
            f"failure/rollback not fully proven (killed={killed}, restarted={restarted}, "
            f"restarted_resolves_to_bundle={resolves_to_bundle}, no_residue={residue['no_residue']}) — DEFERRED"
        )
    return _seam_record(
        SEAM_FAILURE_ROLLBACK_CLEANUP, verdict,
        {
            "killed": killed,
            "restarted_from_same_bundle": restarted,
            "restarted_resolves_to_bundle": resolves_to_bundle,
            "bundle_root": bundle_root,
            **residue,
        },
        note,
    )


def _scope_cgroup_pids(cgroup_dir: Path | None) -> list[int]:
    # 讀 scope cgroup 目錄的 cgroup.procs,回傳其中的行程 PID(缺檔/讀不到即空)。
    if cgroup_dir is None:
        return []
    try:
        text = (cgroup_dir / "cgroup.procs").read_text(encoding="utf-8")
    except OSError:
        return []
    pids: list[int] = []
    for token in text.split():
        try:
            pids.append(int(token))
        except ValueError:
            continue
    return pids


def _restarted_process_resolves_to_bundle(unit: str, bundle_root: str) -> bool:
    """Whether at least one live process in the restarted scope resolves (proc cwd) under ``bundle_root``.

    讀 restart scope 的 cgroup.procs,對每個 pid 解析 ``/proc/<pid>/cwd`` 的真實路徑,只要有一個落在
    已佈署 bundle root(或其子路徑)之下即回 True——這證明重啟的行程真的釘在那個內容定址 bundle,
    而非任意可殺可重跑的 sleeper。輪詢數次容忍行程剛啟動、chdir 尚未生效的短暫視窗。
    """

    real_root = os.path.realpath(bundle_root)
    for _ in range(30):
        for pid in _scope_cgroup_pids(_scope_cgroup_dir(unit)):
            try:
                cwd = os.path.realpath(f"/proc/{pid}/cwd")
            except OSError:
                continue
            if cwd == real_root or cwd.startswith(real_root + os.sep):
                return True
        time.sleep(0.1)
    return False


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


# bundle-pinned launcher:chdir 進內容定址 bundle 目錄後長眠;/proc/<pid>/cwd 即解析回 bundle,
# 供 rollback seam 斷言「重啟的正是那個選定 bundle」而非任意 sleeper。
_BUNDLE_PINNED_SLEEP_SRC = "import os,sys,time; os.chdir(sys.argv[1]); time.sleep(30)"


def _active_bundle_dir(deploy_root: str) -> str:
    """Resolve the CURRENTLY-active (rolled-back) content-addressed bundle directory under a deploy root.

    讀 S1.5 佈署根的 ``active_generation`` 指標(裸 sha256 hex),回傳
    ``<deploy_root>/bundles/<active>`` ——即 immutable-closure seam rollback 後真正 active 的那個 bundle 目錄。
    """

    active = Path(deploy_root, ce._ACTIVE_POINTER).read_text(encoding="utf-8").strip()
    return str(Path(deploy_root, ce._BUNDLES_DIR, active))


def _bundle_pinned_launcher(bundle_root: str) -> list[str]:
    # 產生一個釘在 bundle_root 的 launcher argv(chdir 進 bundle 後長眠),供 start/kill/restart 使用。
    return [sys.executable, "-I", "-c", _BUNDLE_PINNED_SLEEP_SRC, bundle_root]


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
        # #T2:先真備內容定址 bundle(immutable-closure seam),再把 rollback seam 的 launcher 綁到那個
        # rolled-back active bundle 目錄——rollback 必須重啟「選定的固定路徑 bundle」並解析回它,而非一個泛用 sleeper。
        immut_seam = probe_immutable_closure_on_host(deploy_root=immut_root)
        rollback_bundle_root = _active_bundle_dir(immut_root)
        rollback_launcher = _bundle_pinned_launcher(rollback_bundle_root)
        seams = [
            probe_start_stop_on_host(launcher_argv=launcher_argv, nonce=nonce),
            probe_cgroup_isolation_on_host(nonce=nonce),
            probe_network_denial_on_host(),
            probe_native_lib_loading_on_host(bundle_dir=bundle_dir),
            immut_seam,
            probe_failure_rollback_cleanup_on_host(
                nonce=nonce, launcher_argv=rollback_launcher,
                teardown_root=os.path.join(throwaway_root, "frc"), bundle_root=rollback_bundle_root,
            ),
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
# 選擇 receipt builder/validators 已拆至 agent_governance_target_host_choice(使本檔維持 2000
# 行治理介面上限)。以 PEP 562 module ``__getattr__`` **延遲** re-export:``th.build_target_host_
# choice_receipt`` 等(含測試用的私有 helper)對「匯入本模組」的呼叫者零改動可用,同時避免
# A<->choice 的 import-time 循環——choice 於載入時要 import 本模組的常數/helper(單向),本模組僅在
# 「某個本地找不到的名字被存取」時才延遲載入 choice,屆時兩邊皆已完成初始化。任一 import 順序皆安全。
# --------------------------------------------------------------------------- #
def __getattr__(name: str) -> Any:  # noqa: D401 — PEP 562 lazy re-export
    import agent_governance_target_host_choice as _choice

    try:
        return getattr(_choice, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None

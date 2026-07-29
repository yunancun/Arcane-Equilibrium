"""S2E.2a:S2 受信主機的**唯讀 observer**(read-only, process-separated)。

四個觀測面(設計 §B.1),全部唯讀、全部零 mutation:

===================  ============================================================
面                    機制與硬邊界
===================  ============================================================
``unit_state``       system-level ``systemctl show <unit> -p <封閉屬性集>``,經 kernel 的
                     唯讀 session(**絕不** ``--user``、絕不 D-Bus write、絕不生命週期動詞)。
                     誠實界線:``is-enabled`` 不在 owner 的 allowlist 內,本波**不加寬** owner
                     allowlist(那會使 kernel 的「導出 ≡ owner」變假),故 enabled-state 面
                     今日缺席並如實記錄。
``pg_acl``           以 S2.0 唯讀 observer 角色走 **local socket** 讀 ``pg_roles`` /
                     ``pg_namespace.nspacl`` / ``pg_class.relacl``。**DSN 字串永不進參數**
                     (只收 socket_dir/database/role 三個受驗識別碼);直接 ``psql`` 被治理
                     preflight 拒,故此面只用 library、不用 CLI。
``file_identity``    已驗 parent FD(``O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC``)→ ``fstat`` →
                     ``openat(O_PATH|O_NOFOLLOW)``;**絕不 join 未驗字串進 root path** ——
                     caller 只能遞 code-owned 表裡的 **key**,遞不進路徑。
``process_identity`` ``/proc/<pid>/{cmdline,cgroup,stat}`` + unit 的 MainPID/InvocationID,
                     交叉 ``compute_owner_fingerprint``。指紋演算法**只調用不重寫**
                     (``agent_governance_alr_quiesce_inventory`` 是 SSOT)。本面**必須**與
                     ``unit_state`` 同時請求:少了那些屬性,它只會發出由缺席值算出的預設紀錄
                     (P2-D),故 request 層與觀測層各拒一次。
===================  ============================================================

**applier ≠ verifier 的三層(§B.2,強度遞減,誠實標示)**

* **L1 object capability(最強、完全可機證)**:本模組的 observer 物件在結構上不持有任何寫能力
  ——沒有 driver、沒有 admin handle、沒有寫連線;:func:`agent_governance_s2_host_kernel
  .assert_read_only_surface` 在**呼叫任何方法之前**檢查,且本模組的 import closure 不含任何
  applier 模組(結構測試執法)。
* **L2 進程分離**:``main()`` 讓本模組能以 ``python3 -E`` 子行程獨立執行(由 kernel 的
  ``run_observer_child`` 以 sanitized env 啟動),輸出只經 stdout 的 canonical JSON,且該唯一出口
  在寫出之前必須通過 kernel 的 :func:`agent_governance_s2_host_kernel
  .scan_serializable_surface_for_secrets`(命中即零 stdout + typed 退出
  :data:`EXIT_OBSERVATION_SECRET_LEAK_BLOCKED`)。**通道分離**:stdout 是資料通道,stderr 只是
  診斷通道 —— 守衛命中時 stderr 只寫固定訊息 + 條目數,理由字串(鍵名 trail)一個 fd 都不出境。
* **L3 OS 身分分離:本波不提供**。真 uid 分離需主機側供裝(獨立 unix user),屬 operator/W6B。
  S2E.2a 提供「相異 process + 相異 object capability」,**不**提供相異 OS uid;W5 ledger 的
  ``ATTESTOR_KEY_IS_NOT_SEPARATE_FROM_THE_PERMIT_KEY`` 因此被**縮小**但未關閉。

**這不是 receipt。** ``s2_host_observation_v1`` 是 observer child 的 stdout 傳輸契約(鏡
``target_host_governed_observation_v1`` 的先例),**不是** adapter receipt、**不是** closure
evidence,也不註冊進中央 AIML 閘。任何 closure 綁定一律走既有的
``build_s2_effect_ops_postcheck_evidence`` 與各 adapter 自己的 receipt(設計 §H R4)。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
for _candidate in (_HERE, _REPO_ROOT / "program_code" / "ml_training"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_alr_quiesce_inventory as quiesce_inventory  # noqa: E402
import agent_governance_s2_host_kernel as host_kernel  # noqa: E402


OBSERVATION_SCHEMA_VERSION = "s2_host_observation_v1"
REQUEST_SCHEMA_VERSION = "s2_host_observation_request_v1"

# ``main()`` 的 L1 觀測閘退出碼(E2 RES-6):production/unknown 上沒有顯式承認 ⇒ 零觀測、零 exec。
EXIT_OBSERVATION_NOT_ADMITTED = 6
# ``main()`` 的出境秘密掃描退出碼:observation 命中中央 secret scanner ⇒ 整包丟棄、**零 stdout**,
# 且 stderr 只留固定診斷訊息(理由字串不進任何通道)。
EXIT_OBSERVATION_SECRET_LEAK_BLOCKED = 7

FACE_UNIT_STATE = "unit_state"
FACE_PG_ACL = "pg_acl"
FACE_FILE_IDENTITY = "file_identity"
FACE_PROCESS_IDENTITY = "process_identity"
OBSERVATION_FACES = (FACE_UNIT_STATE, FACE_PG_ACL, FACE_FILE_IDENTITY, FACE_PROCESS_IDENTITY)

# PG 識別碼的封閉 charset(鏡 component_effects 的 ``_pg_ident``);任何 DSN 形都過不了。
_PG_IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
# socket_dir 必為絕對路徑且不得夾帶 DSN/連線字串的任何標記。
_DSN_MARKERS = ("://", "@", "=", " ", "\t", "\n", "password", "pass=", "sslmode")

# code-owned 的可觀測檔案表:caller 遞 **key**,永遠遞不進路徑(§B.1 硬邊界)。
CANONICAL_OBSERVABLE_PATHS: dict[str, str] = {
    "unit_fragment": f"{host_kernel.SYSTEMD_SYSTEM_UNIT_DIR}/{quiesce_inventory.UNIT_NAME}",
    "install_root_runtimes": host_kernel.CANONICAL_INSTALL_ROOTS[0],
    "install_root_apps": host_kernel.CANONICAL_INSTALL_ROOTS[1],
    "install_root_launches": host_kernel.CANONICAL_INSTALL_ROOTS[2],
}

DEFAULT_PROC_ROOT = "/proc"


class S2HostObserverError(RuntimeError):
    """Raised when a read-only observation cannot be taken safely (fail-closed, never a guess)."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


# --------------------------------------------------------------------------- #
# face 1 — systemd unit state (through the kernel's read-only session)
# --------------------------------------------------------------------------- #
class UnitStateObserver:
    """Read the system-level unit's declared property set.  Never ``--user``, never a verb."""

    def __init__(self, executor: Any) -> None:
        self._executor = executor

    def observe(self) -> dict[str, Any]:
        argv = list(quiesce_inventory._show_command())
        # 獨立 re-assert:即使有人繞過 kernel 直呼本 observer,argv 仍必須通過 owner 的 allowlist。
        quiesce_inventory._assert_allowlisted_systemctl(argv)
        host_kernel.assert_session_argv(host_kernel.SESSION_S2_1_QUIESCE_READ, argv)
        raw = self._executor.run(argv)
        properties: dict[str, str] = {}
        for line in str(raw).splitlines():
            key, separator, value = line.partition("=")
            if separator == "=" and key in set(quiesce_inventory.QUIESCE_SHOW_PROPERTIES):
                properties[key] = value
        missing = sorted(set(quiesce_inventory.QUIESCE_SHOW_PROPERTIES) - set(properties))
        return {
            "unit": quiesce_inventory.UNIT_NAME,
            "manager_scope": "system",
            "properties": properties,
            "missing_properties": missing,
            # 誠實界線:owner allowlist 沒有 ``is-enabled``,本波不加寬它。
            "unit_file_state_observed": False,
            "unit_file_state_reason": (
                "the owner allowlist admits only `show -p <closed set>` and `list-units`; "
                "widening it to is-enabled would break the derived kernel allowlist"
            ),
        }


# --------------------------------------------------------------------------- #
# face 2 — PG role + ACL, AS the S2.0 read-only observer, over a local socket
# --------------------------------------------------------------------------- #
def _assert_local_socket_dir(value: Any) -> str:
    socket_dir = str(value or "")
    if not socket_dir.startswith("/"):
        raise S2HostObserverError("observer socket_dir must be an absolute local socket directory")
    lowered = socket_dir.lower()
    if any(marker in lowered for marker in _DSN_MARKERS):
        raise S2HostObserverError(
            "observer socket_dir carries DSN-like content; a DSN string never enters the observer"
        )
    return socket_dir


def _assert_pg_ident(value: Any, *, label: str) -> str:
    candidate = str(value or "")
    if not _PG_IDENT_RE.fullmatch(candidate):
        raise S2HostObserverError(f"observer {label} is not a safe PG identifier")
    return candidate


class PgAclObserver:
    """Read ``pg_roles`` + schema/relation ACLs AS the S2.0 read-only observer.

    ``connect`` 只接受 socket_dir/database/user 三個**受驗識別碼**(絕不接受 DSN 字串、絕不接受
    password);連線層釘死 ``default_transaction_read_only=on`` 與 ``search_path=pg_catalog``。
    """

    def __init__(self, *, connect: Any = None) -> None:
        self._connect = connect

    def _open(self, *, socket_dir: str, database: str, user: str) -> Any:
        if self._connect is not None:
            return self._connect(socket_dir=socket_dir, database=database, user=user)
        try:
            import psycopg2
        except ImportError as error:  # pragma: no cover - 依主機而定
            raise S2HostObserverError(
                "the PG ACL face needs the psycopg2 library (direct psql stays denied)"
            ) from error
        connection = psycopg2.connect(
            host=socket_dir, dbname=database, user=user, connect_timeout=10,
            options="-c default_transaction_read_only=on -c search_path=pg_catalog",
        )
        connection.autocommit = True
        return connection

    def observe(self, request: dict[str, Any]) -> dict[str, Any]:
        socket_dir = _assert_local_socket_dir(request.get("socket_dir"))
        database = _assert_pg_ident(request.get("database"), label="database")
        role = _assert_pg_ident(request.get("observer_role"), label="observer_role")
        schema = _assert_pg_ident(request.get("observed_schema"), label="observed_schema")
        relations = [
            _assert_pg_ident(item, label="observed_relation")
            for item in (request.get("observed_relations") or [])
        ]
        connect_as = _assert_pg_ident(request.get("connect_as") or role, label="connect_as")
        # P2-C:PG 不可用 / catalog query 失敗時,``psycopg2`` 拋的是它自己的例外型別,不在
        # ``main()`` 捕捉的兩個型別內 ⇒ 裸 traceback + exit 1,破壞已文件化的 typed exit 契約。
        # 這裡把整個連線+查詢邊界收成 :class:`S2HostObserverError`(exit 5)。**只帶例外型別名**,
        # 不帶 DB 訊息本身:那段字串是主機給的內容(可能含連線 locus / 角色名),而 stderr 是診斷
        # 通道不是資料通道(SEC-3 的同一條界線)。
        try:
            return self._observe_catalog(
                socket_dir=socket_dir, database=database, connect_as=connect_as,
                role=role, schema=schema, relations=relations,
            )
        except S2HostObserverError:
            raise
        except Exception as error:  # noqa: BLE001 - 任何 DB 側失敗一律 typed fail-closed
            raise S2HostObserverError(
                "the PG ACL face could not complete its read-only catalog observation "
                f"({type(error).__name__}); refusing to report a partial or guessed projection"
            ) from error

    def _observe_catalog(
        self, *, socket_dir: str, database: str, connect_as: str,
        role: str, schema: str, relations: list[str],
    ) -> dict[str, Any]:
        connection = self._open(socket_dir=socket_dir, database=database, user=connect_as)
        try:
            cursor = connection.cursor()
            cursor.execute(
                "SELECT rolname, rolcanlogin, rolsuper, rolcreaterole, rolcreatedb, "
                "rolreplication, rolbypassrls, rolconfig FROM pg_catalog.pg_roles "
                "WHERE rolname = %s",
                (role,),
            )
            row = cursor.fetchone()
            role_view: dict[str, Any] | None = None
            if row is not None:
                role_view = {
                    "rolname": row[0], "rolcanlogin": bool(row[1]), "rolsuper": bool(row[2]),
                    "rolcreaterole": bool(row[3]), "rolcreatedb": bool(row[4]),
                    "rolreplication": bool(row[5]), "rolbypassrls": bool(row[6]),
                    "rolconfig": sorted(row[7]) if row[7] else [],
                }
            cursor.execute(
                "SELECT nspacl::text FROM pg_catalog.pg_namespace WHERE nspname = %s",
                (schema,),
            )
            schema_row = cursor.fetchone()
            cursor.execute(
                "SELECT c.relname, c.relacl::text FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = %s AND c.relname = ANY(%s) ORDER BY c.relname",
                (schema, relations),
            )
            relation_acls = {name: acl for name, acl in cursor.fetchall()}
        finally:
            connection.close()
        projection = {
            "role": role_view,
            "schema": schema,
            "schema_acl": schema_row[0] if schema_row else None,
            "relation_acls": relation_acls,
        }
        return {
            "observer_role_present": role_view is not None,
            "projection": projection,
            "projection_digest": _digest(projection),
        }


# --------------------------------------------------------------------------- #
# face 3 — file identity via a verified parent FD (never a joined caller string)
# --------------------------------------------------------------------------- #
class FileIdentityObserver:
    """``O_DIRECTORY|O_NOFOLLOW`` parent → ``fstat`` → ``openat(O_PATH|O_NOFOLLOW)`` 的唯讀身分讀取。

    ``paths`` 是 code-owned 表(預設 :data:`CANONICAL_OBSERVABLE_PATHS`);request 只能遞表裡的
    **key**。任何未知 key 一律 typed 拒,絕不 join 未驗字串。
    """

    def __init__(self, paths: dict[str, str] | None = None) -> None:
        self._paths = dict(paths or CANONICAL_OBSERVABLE_PATHS)

    @property
    def known_keys(self) -> list[str]:
        return sorted(self._paths)

    def observe(self, keys: list[str]) -> dict[str, Any]:
        unknown = sorted(set(keys) - set(self._paths))
        if unknown:
            raise S2HostObserverError(
                f"unknown observable path keys {unknown}; the observer never joins a caller string "
                "into a root path"
            )
        observed: dict[str, Any] = {}
        for key in sorted(set(keys)):
            observed[key] = self._observe_one(self._paths[key])
        return observed

    def _leaf_stat(self, leaf: str, parent_fd: int) -> os.stat_result:
        """``openat(O_PATH|O_NOFOLLOW)`` → ``fstat``;無 ``O_PATH`` 的平台退回 ``fstatat``。

        兩條路徑都以**已驗的 parent FD** 為錨、都帶 ``O_NOFOLLOW`` / ``follow_symlinks=False``,
        故 leaf 名永遠不會被 join 進一個未驗字串路徑,symlink 也永遠不被跟隨。
        """

        if hasattr(os, "O_PATH"):
            leaf_fd = os.open(leaf, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
            try:
                return os.fstat(leaf_fd)
            finally:
                os.close(leaf_fd)
        return os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)

    def _observe_one(self, path: str) -> dict[str, Any]:
        parent = os.path.dirname(path) or "/"
        leaf = os.path.basename(path)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            parent_fd = os.open(parent, flags)
        except OSError as error:
            return {"path": path, "present": False, "reason": f"parent unavailable: {error.strerror}"}
        try:
            parent_stat = os.fstat(parent_fd)
            try:
                leaf_stat = self._leaf_stat(leaf, parent_fd)
            except OSError as error:
                return {
                    "path": path, "present": False,
                    "parent_inode": parent_stat.st_ino,
                    "reason": f"leaf unavailable: {error.strerror}",
                }
            return {
                "path": path,
                "present": True,
                "parent_inode": parent_stat.st_ino,
                "parent_device": parent_stat.st_dev,
                "inode": leaf_stat.st_ino,
                "device": leaf_stat.st_dev,
                "mode": format(stat.S_IMODE(leaf_stat.st_mode), "04o"),
                "uid": leaf_stat.st_uid,
                "gid": leaf_stat.st_gid,
                "is_symlink": stat.S_ISLNK(leaf_stat.st_mode),
                "is_dir": stat.S_ISDIR(leaf_stat.st_mode),
                "size": leaf_stat.st_size,
            }
        finally:
            os.close(parent_fd)


# --------------------------------------------------------------------------- #
# face 4 — process identity (only calls the inventory SSOT, never re-implements it)
# --------------------------------------------------------------------------- #
class ProcessIdentityObserver:
    """Read ``/proc/<pid>/{cmdline,cgroup,stat}`` and cross the unit's MainPID/InvocationID.

    指紋由 ``quiesce_inventory.compute_owner_fingerprint`` / ``compute_stable_identity_fingerprint``
    導出(C1 exact 9-token 指紋比對已在 owner 模組;observer 只調用不重寫)。

    **本面完全寄生在 unit 面的觀測結果上(P2-D)。** ``MainPID`` / ``InvocationID`` / ``ControlGroup``
    都只能從 ``systemctl show`` 來;缺了它們,``observe`` 產出的每一個欄位——``main_pid=0``、
    ``proc_present=false``、由**缺席**屬性算出的兩個指紋——都不是觀測結果,而是預設值。那份 payload
    仍能通過 ``validate_observation`` 並被 CLI 報成一次成功觀測,等於把「從未被觀測的 process」
    包裝成看似有效的 runtime 證據。故屬性缺席時一律 typed 拒,絕不發一份預設值紀錄。
    """

    #: 指紋所依賴、且必須真的被 ``systemctl show`` 觀測到的 unit 屬性(全部在 owner 的封閉屬性集內)。
    REQUIRED_UNIT_PROPERTIES = ("ControlGroup", "InvocationID", "MainPID")

    def __init__(self, proc_root: str = DEFAULT_PROC_ROOT) -> None:
        self._proc_root = Path(proc_root)

    def observe(self, unit_properties: dict[str, str], *, flock_path: str = "") -> dict[str, Any]:
        missing = [key for key in self.REQUIRED_UNIT_PROPERTIES if key not in unit_properties]
        if missing:
            raise S2HostObserverError(
                "the process_identity face needs the unit's observed "
                f"{sorted(missing)}; without them every field below would be derived from "
                "properties that were never observed, so no process record is emitted"
            )
        main_pid_raw = str(unit_properties.get("MainPID", "0"))
        main_pid = int(main_pid_raw) if main_pid_raw.isdigit() else 0
        present = main_pid > 0 and (self._proc_root / str(main_pid)).exists()
        cmdline = quiesce_inventory._read_proc_cmdline(self._proc_root, main_pid) if present else None
        environ = quiesce_inventory._read_proc_environ(self._proc_root, main_pid) if present else None
        cgroup = quiesce_inventory._read_proc_cgroup(self._proc_root, main_pid) if present else None
        start_ticks = (
            quiesce_inventory._read_proc_stat_start_ticks(self._proc_root, main_pid)
            if present else None
        )
        boot_id = quiesce_inventory._read_boot_id(self._proc_root)
        cmdline_digest = quiesce_inventory.canonical_digest(cmdline) if cmdline else None
        env_hash = None
        runtime_digest = None
        if environ is not None:
            env_hash = quiesce_inventory.canonical_digest({
                key: environ[key]
                for key in quiesce_inventory.ENV_DECLARED_KEYS if key in environ
            })
            runtime_digest = quiesce_inventory._default_runtime_digest_resolver(
                environ.get("ALR_SOURCE_HEAD"), environ
            )
        control_group = str(unit_properties.get("ControlGroup", ""))
        invocation_id = str(unit_properties.get("InvocationID", ""))
        return {
            "main_pid": main_pid,
            "proc_present": present,
            "boot_id": boot_id,
            "process_start_ticks": start_ticks,
            "cmdline_digest": cmdline_digest,
            "cgroup": cgroup,
            "cgroup_matches_unit": bool(cgroup) and quiesce_inventory.UNIT_NAME in str(cgroup),
            "env_hash": env_hash,
            "runtime_digest": runtime_digest,
            "owner_fingerprint": quiesce_inventory.compute_owner_fingerprint(
                main_pid=main_pid, process_start_ticks=start_ticks, boot_id=boot_id,
                control_group=control_group, env_hash=env_hash, invocation_id=invocation_id,
                cmdline_digest=cmdline_digest, runtime_digest=runtime_digest,
                flock_path=flock_path,
            ),
            "stable_identity_fingerprint": quiesce_inventory.compute_stable_identity_fingerprint(
                control_group=control_group, env_hash=env_hash,
                cmdline_digest=cmdline_digest, runtime_digest=runtime_digest,
            ),
        }


# --------------------------------------------------------------------------- #
# the aggregate observer — holds NO driver, NO admin handle, NO write connection
# --------------------------------------------------------------------------- #
class S2HostObserver:
    """The read-only aggregate.  Structurally incapable of mutating anything."""

    def __init__(
        self,
        *,
        executor: Any = None,
        pg_connect: Any = None,
        observable_paths: dict[str, str] | None = None,
        proc_root: str = DEFAULT_PROC_ROOT,
    ) -> None:
        self._unit = UnitStateObserver(executor) if executor is not None else None
        self._pg = PgAclObserver(connect=pg_connect)
        self._files = FileIdentityObserver(observable_paths)
        self._process = ProcessIdentityObserver(proc_root)

    def observe(self, request: dict[str, Any]) -> dict[str, Any]:
        errors = validate_observation_request(request)
        if errors:
            raise S2HostObserverError("observation request is inadmissible: " + "; ".join(errors[:3]))
        faces = list(request["faces"])
        observed: dict[str, Any] = {}
        unit_properties: dict[str, str] = {}
        if FACE_UNIT_STATE in faces:
            if self._unit is None:
                raise S2HostObserverError(
                    "the unit-state face needs a host executor; none was injected (zero contact)"
                )
            observed[FACE_UNIT_STATE] = self._unit.observe()
            unit_properties = observed[FACE_UNIT_STATE]["properties"]
        if FACE_PG_ACL in faces:
            observed[FACE_PG_ACL] = self._pg.observe(request.get("pg") or {})
        if FACE_FILE_IDENTITY in faces:
            observed[FACE_FILE_IDENTITY] = self._files.observe(list(request.get("path_keys") or []))
        if FACE_PROCESS_IDENTITY in faces:
            observed[FACE_PROCESS_IDENTITY] = self._process.observe(
                unit_properties, flock_path=str(request.get("flock_path") or "")
            )
        observation = {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            # 敘述性時戳:本機牆鐘讀值,不是 attestation、不帶 trust 語義(見 kernel docstring)。
            "observed_at": host_kernel.host_wall_clock_time(),
            "target_class_view": host_kernel.derive_host_target_class(),
            "request_digest": _digest(request),
            "faces": observed,
        }
        observation["self_digest"] = _digest(observation)
        return observation


def validate_observation_request(request: Any) -> list[str]:
    """Fail-closed shape check for the observer's transport request."""

    errors: list[str] = []
    if not isinstance(request, dict):
        return ["observation request must be an object"]
    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        errors.append("observation request schema_version is invalid")
    faces = request.get("faces")
    if not isinstance(faces, list) or not faces:
        errors.append("observation request must name at least one face")
    else:
        unknown = sorted(set(faces) - set(OBSERVATION_FACES))
        if unknown:
            errors.append(f"observation request names unknown faces {unknown}")
    if FACE_PG_ACL in (faces or []) and not isinstance(request.get("pg"), dict):
        errors.append("the pg_acl face requires a pg object")
    if FACE_FILE_IDENTITY in (faces or []) and not isinstance(request.get("path_keys"), list):
        errors.append("the file_identity face requires a path_keys list of code-owned keys")
    # P2-D:``process_identity`` 的每個欄位都衍生自 unit 面的 MainPID/InvocationID/ControlGroup,
    # 故單獨請求它只會產出一份「未被觀測卻看起來有效」的 process 紀錄 —— 在 request 層就拒。
    if FACE_PROCESS_IDENTITY in (faces or []) and FACE_UNIT_STATE not in (faces or []):
        errors.append(
            "the process_identity face requires the unit_state face; a process record derived "
            "from an unobserved unit is not evidence"
        )
    if "allow_production" in request and not isinstance(request["allow_production"], bool):
        errors.append("allow_production must be a bool acknowledgement (absent means false)")
    return errors


def validate_observation(observation: Any) -> list[str]:
    """Fail-closed shape + integrity check of one observer payload (self_digest recomputed)."""

    errors: list[str] = []
    if not isinstance(observation, dict):
        return ["observation must be an object"]
    if observation.get("schema_version") != OBSERVATION_SCHEMA_VERSION:
        errors.append("observation schema_version is invalid")
    if not isinstance(observation.get("faces"), dict) or not observation["faces"]:
        errors.append("observation carries no face")
    body = {key: value for key, value in observation.items() if key != "self_digest"}
    if observation.get("self_digest") != _digest(body):
        errors.append("observation self_digest does not match its bytes")
    return errors


# --------------------------------------------------------------------------- #
# process-separated entrypoint (spawned by HostExecutionKernel.run_observer_child)
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    """獨立進入點:``python3 -E <this file> --request-base64 <token>``。

    **L1 觀測閘就在這裡(E2 RES-6)。** 先前這道閘只存在於 CLI(``aiml_s2_effect_host_run``)的
    ``_observation()``,於是「直接跑這個檔」這條完全合法的進入點在生產主機上會**毫無承認地**發出
    ``systemctl show`` —— CLI docstring 那句「否則 observer 子行程根本不被 spawn」只對 CLI 路徑
    成立。現在閘下沉到本函式:target class 一律當場由 :func:`derive_host_target_class` 從**主機
    事實**導出(caller 遞不進 view),``production`` / ``unknown`` 需要 request 裡一次顯式的
    ``allow_production: true`` 承認,否則零觀測、零 exec、typed 退出 6。

    誠實界線:``allow_production`` 是一次**顯式承認**,不是授權 —— 它與 CLI 的
    ``--allow-production`` 旗標同性質(自我宣告),擋的是「不小心在生產主機上跑起來」而不是一個
    刻意的操作者。真正不可自我宣告的是 ``target_class`` 本身,那一項恆為導出值。
    """

    parser = argparse.ArgumentParser(description="S2 read-only host observer (process-separated)")
    parser.add_argument("--request-base64", required=True)
    args = parser.parse_args(argv)
    try:
        request = json.loads(base64.b64decode(args.request_base64, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        sys.stderr.write("observation request is not canonical base64 JSON\n")
        return 3
    if not isinstance(request, dict):
        sys.stderr.write("observation request must be an object\n")
        return 3
    admission_errors = host_kernel.host_observation_admission_errors(
        host_kernel.derive_host_target_class(),
        allow_production=request.get("allow_production") is True,
    )
    if admission_errors:
        sys.stderr.write(
            "read-only observation refused by the L1 host gate: "
            + "; ".join(admission_errors) + "\n"
        )
        return EXIT_OBSERVATION_NOT_ADMITTED
    executor = None
    if FACE_UNIT_STATE in (request.get("faces") or []):
        executor = host_kernel.HostExecutionKernel(
            session=host_kernel.SESSION_S2_1_QUIESCE_READ
        )
    # 子行程一律用 code-owned 的 ``/proc``:``proc_root`` **不是** request 欄位,rehearsal 的模擬
    # ``/proc`` 只能經 in-process 的建構子注入,故沒有任何 caller 路徑字串能經 child 面進來。
    observer = S2HostObserver(executor=executor, proc_root=DEFAULT_PROC_ROOT)
    # L1 能力分割硬檢:在呼叫任何觀測方法**之前**確認 observer 面上沒有任何寫能力。
    surface_errors = host_kernel.assert_read_only_surface(observer)
    if surface_errors:
        sys.stderr.write("; ".join(surface_errors) + "\n")
        return 4
    try:
        observation = observer.observe(request)
    except (S2HostObserverError, host_kernel.S2HostKernelError) as error:
        sys.stderr.write(f"read-only observation refused: {error}\n")
        return 5
    # 出境守衛:stdout 是本 child 唯一的資料出口,故 observation 在**寫出之前**必須過中央 secret
    # scanner。輸入側的硬邊界只保證「caller 遞不進秘密」(PG 面拒任何 DSN 形、檔案面只收 code-owned
    # key),它**不**保證「主機事實裡沒有秘密」—— unit 的 ``Environment=``、role 的 ``rolconfig``、
    # ACL 文字全是主機給的字串,今日對它們零機械保證。命中即整包丟棄:零 stdout、typed 退出,
    # 絕不寫出被判定含 secret 的內容;守衛的理由字串(只帶鍵名 trail、不帶值)也不出境,見下。
    leak_reasons = host_kernel.scan_serializable_surface_for_secrets(observation)
    if leak_reasons:
        # 通道分離(SEC-3):stderr 是本 child 的**診斷通道**,不是資料通道 —— 命中時它只寫人類可讀
        # 的固定訊息 + 守衛回報的條目數,**絕不**寫守衛的理由字串。理由字串雖然只帶鍵名 trail 不帶
        # 值(見 kernel 的 ``_secret_trails``),但它仍是由「已被判定含 secret 的那份 payload」導出
        # 的內容;把它寫進診斷通道,等於讓這道守衛自己成為第二條出境路徑。命中時**兩個 fd 都不帶
        # payload 導出物**才是這道閘的完整語義。誠實代價:鍵名 trail 從此不出現在 child 的任何通道,
        # 現場只知道「守衛開火了」,不知道命中在哪個鍵;而條目數今日恆為 1(掃描器結構上只回一條
        # 彙總理由),所以那個數字目前只證明「開火了」,不是命中點的計數。
        sys.stderr.write(
            "read-only observation withheld by the egress secret guard: "
            f"{len(leak_reasons)} finding(s); the key trails stay inside the guard and never "
            "reach this diagnostic channel\n"
        )
        return EXIT_OBSERVATION_SECRET_LEAK_BLOCKED
    sys.stdout.write(
        json.dumps(observation, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

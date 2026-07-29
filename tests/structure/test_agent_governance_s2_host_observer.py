"""S2E.2a:S2 受信主機唯讀 observer 的結構證明(applier ≠ verifier 的 L1 + L2)。

證明:

* **L1 object capability**:observer 的 import closure ∩ applier 模組集 == ∅(以獨立子行程實測,
  非靜態宣稱);``assert_read_only_surface`` 在**呼叫任何方法之前**拒絕寫能力面(反例的寫方法
  一旦被呼叫就會炸,故「未被呼叫」是可機證的)。
* **L2 進程分離**:observer 真的能以 ``python3 -E`` 子行程執行並回傳可重算 self_digest 的
  canonical JSON。
* 四個觀測面的硬邊界:unit 面的 argv 與 owner 的 ``_show_command()`` 逐位元組相同且再經 owner 的
  allowlist 自檢;PG 面拒絕任何 DSN 形、只走 local socket + 唯讀連線選項;檔案面**只**接受
  code-owned key(未知 key 一律拒,絕不 join 未驗字串)且不跟隨 symlink;process 面只調用
  inventory SSOT 的指紋函式而不重寫。
* **誠實邊界(本波未關閉)**:observer 的 governed ``command_capture_v2`` 綁定今日**不可得**——
  ``authorize_native_command`` 只承認 S1.6B 那一支 observation script,而
  ``agent_governance_permissions.py`` 不在本波 owned path 內。此事實以測試釘住,任何未來加寬都會
  讓這個測試變紅並被看見。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_alr_quiesce_inventory as qi  # noqa: E402
import agent_governance_s2_host_kernel as kernel  # noqa: E402
import agent_governance_s2_host_observer as observer_module  # noqa: E402

APPLIER_MODULES = frozenset({
    "agent_governance_pg_observer_bootstrap",
    "agent_governance_alr_quiesce_fence",
    "agent_governance_s2_4_apply",
    "agent_governance_s2_4_install",
    "agent_governance_s2_4_install_driver",
    "agent_governance_s2_4_prepare",
    "agent_governance_s2_4_probe",
    "agent_governance_s2_5_lifecycle",
    "agent_governance_s2_5_driver",
    "agent_governance_s2_0_host_runner",
    "agent_governance_s2_1_host_runner",
})

_FRAG = f"{kernel.SYSTEMD_SYSTEM_UNIT_DIR}/{qi.UNIT_NAME}"
_FLOCK = "/run/arcane-equilibrium/aiml-engine-scanner/consumer.lock"
_DSN_FILE = "/run/credentials/arcane-equilibrium-aiml-engine-scanner.service/pg-dsn"
_INTERP = "/opt/arcane-equilibrium/aiml/runtimes/" + "b" * 64 + "/bin/python3"
_CG = "/system.slice/" + qi.UNIT_NAME


class _ShowExecutor:
    """只認得 owner 的 show 指令;任何其它 argv 直接炸(證明 observer 不會亂送)。"""

    def __init__(self, properties: dict[str, str]) -> None:
        self.properties = properties
        self.argv: list[tuple[str, ...]] = []

    def run(self, argv):
        self.argv.append(tuple(argv))
        assert list(argv) == list(qi._show_command())
        return "\n".join(
            f"{key}={self.properties.get(key, '')}" for key in qi.QUIESCE_SHOW_PROPERTIES
        )


def _properties(main_pid: int) -> dict[str, str]:
    return {
        "LoadState": "loaded", "ActiveState": "active", "SubState": "running",
        "MainPID": str(main_pid), "InvocationID": "inv-1", "NRestarts": "0",
        "FragmentPath": _FRAG, "DropInPaths": "", "ControlGroup": _CG,
        "Environment": "", "NeedDaemonReload": "no", "Restart": "on-failure",
        "RestartUSec": "5s", "TimeoutStopUSec": "30s", "WatchdogUSec": "0",
        "NoNewPrivileges": "yes", "ProtectSystem": "full", "PrivateTmp": "yes",
        "RestrictAddressFamilies": "AF_UNIX",
    }


# --------------------------------------------------------------------------- #
# L1 — import closure and object capability
# --------------------------------------------------------------------------- #
def test_observer_import_closure_excludes_every_applier_module():
    argv = [
        sys.executable, "-E", "-c",
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
        "import agent_governance_s2_host_observer; "
        "print('\\n'.join(sorted(sys.modules)))" % (str(ML_ROOT), str(HELPERS)),
    ]
    loaded = set(
        subprocess.run(argv, capture_output=True, text=True, check=True).stdout.split()
    )
    assert not (loaded & APPLIER_MODULES), sorted(loaded & APPLIER_MODULES)


def test_aggregate_observer_carries_no_mutating_surface():
    observer = observer_module.S2HostObserver()
    assert kernel.assert_read_only_surface(observer) == []
    for component in (observer._pg, observer._files, observer._process):
        assert kernel.assert_read_only_surface(component) == []


class _ObserverWithWriteCapability:
    def observe(self, request):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("the capability check must refuse before any observation")

    def compensate(self):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("a read-only observer must never expose compensate()")


def test_capability_partition_refuses_before_calling_anything():
    errors = kernel.assert_read_only_surface(_ObserverWithWriteCapability())
    assert errors and "compensate" in errors[0]


# --------------------------------------------------------------------------- #
# L2 — real process separation through the kernel's observer child
# --------------------------------------------------------------------------- #
def test_observer_runs_in_an_isolated_child_and_returns_a_verifiable_payload():
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_HOST_OBSERVER_CHILD)
    request = {
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_FILE_IDENTITY, observer_module.FACE_PROCESS_IDENTITY],
        "path_keys": ["unit_fragment", "install_root_runtimes"],
    }
    raw = host.run_observer_child(request)
    observation = json.loads(raw)
    assert observer_module.validate_observation(observation) == []
    assert set(observation["faces"]) == {
        observer_module.FACE_FILE_IDENTITY, observer_module.FACE_PROCESS_IDENTITY
    }
    assert observation["request_digest"] == observer_module._digest(request)
    # 子行程真的是另一個 process:kernel 記了一次 exec,且 argv 是 code-owned 的構造結果。
    assert len(host.calls) == 1
    assert host.calls[0][:3] == (
        sys.executable, "-E", str(kernel.OBSERVER_CHILD_SCRIPT)
    )


def test_observer_child_argv_is_constructed_never_supplied():
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_HOST_OBSERVER_CHILD)
    # 該 session 的字面 allowlist 為空 ⇒ 任何 caller argv 一律拒。
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        host.run([sys.executable, "-E", str(kernel.OBSERVER_CHILD_SCRIPT)])
    # 非 base64 / 過長 payload 一律 typed 拒(後者同時是 E2BIG 護欄)。
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        kernel.observer_child_argv("not base64; rm -rf /")
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        kernel.observer_child_argv("A" * (kernel.OBSERVER_CHILD_MAX_REQUEST_BYTES + 4))


def test_only_the_observer_child_session_may_spawn_the_child():
    for session in (
        kernel.SESSION_S2_0_OBSERVER_BOOTSTRAP, kernel.SESSION_S2_1_QUIESCE_READ,
    ):
        host = kernel.HostExecutionKernel(session=session)
        with pytest.raises(kernel.S2HostSessionError):
            host.run_observer_child({"schema_version": observer_module.REQUEST_SCHEMA_VERSION,
                                     "faces": [observer_module.FACE_PROCESS_IDENTITY]})


def test_observer_child_exits_nonzero_on_an_inadmissible_request():
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_HOST_OBSERVER_CHILD)
    with pytest.raises(kernel.S2HostCommandFailed):
        host.run_observer_child({"schema_version": "wrong", "faces": ["nope"]})


# --------------------------------------------------------------------------- #
# RES-6:L1 觀測閘必須在 ``main()`` 裡,而不是只在 CLI 裡
# --------------------------------------------------------------------------- #
def _encoded(request: dict) -> str:
    import base64

    return base64.b64encode(
        json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


@pytest.mark.parametrize("target_class", [
    kernel.TARGET_CLASS_PRODUCTION,
    kernel.TARGET_CLASS_UNKNOWN,
])
def test_main_refuses_a_production_grade_host_without_an_acknowledgement(
    monkeypatch, capsys, target_class
):
    """直接跑這個腳本(不經 CLI)在生產級主機上必須零觀測、零 exec。"""

    monkeypatch.setattr(
        observer_module.host_kernel, "derive_host_target_class",
        lambda: {"target_class": target_class, "reason": "forced"},
    )

    def _never(*args, **kwargs):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("no host executor may be constructed before the L1 gate passes")

    monkeypatch.setattr(observer_module.host_kernel, "HostExecutionKernel", _never)
    request = {
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_UNIT_STATE],
    }
    code = observer_module.main(["--request-base64", _encoded(request)])
    assert code == observer_module.EXIT_OBSERVATION_NOT_ADMITTED
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refused by the L1 host gate" in captured.err


def test_main_admits_the_same_host_once_the_acknowledgement_is_present(monkeypatch):
    """同一份 production view 上,一次顯式承認就放行 —— 與 CLI 那道閘逐字同義。"""

    monkeypatch.setattr(
        observer_module.host_kernel, "derive_host_target_class",
        lambda: {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "forced"},
    )
    request = {
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_FILE_IDENTITY],
        "path_keys": ["unit_fragment"],
        "allow_production": True,
    }
    assert observer_module.main(["--request-base64", _encoded(request)]) == 0


# --------------------------------------------------------------------------- #
# 出境秘密掃描:stdout 是 child 唯一的資料出口,命中即整包丟棄(零 stdout)
# --------------------------------------------------------------------------- #
# 反例以片段拼接構造(repo 內不留看起來像真憑證的字面量);這是 S2.4 封閉 DSN 的 libpq 鍵值形。
_SECRET_SHAPED_PROPERTY = "PG" + "PASSWORD" + "=" + "s3cr3t-not-real"


def _observation_with(environment_value: str) -> dict:
    body = {
        "schema_version": observer_module.OBSERVATION_SCHEMA_VERSION,
        "observed_at": "2026-07-29T00:00:00Z",
        "target_class_view": {"target_class": kernel.TARGET_CLASS_NON_TARGET},
        "request_digest": "sha256:" + "0" * 64,
        "faces": {
            observer_module.FACE_UNIT_STATE: {
                "unit": qi.UNIT_NAME, "manager_scope": "system",
                "properties": {"ActiveState": "active", "Environment": environment_value},
            },
        },
    }
    body["self_digest"] = observer_module._digest(body)
    return body


def _install_observer_returning(monkeypatch, observation: dict) -> None:
    """把 ``main()`` 建構的 aggregate observer 換成一支回傳指定 payload 的唯讀替身。"""

    class _Stub:
        def __init__(self, **kwargs) -> None:
            del kwargs

        def observe(self, request):
            del request
            return observation

    # 替身仍必須通過 L1 能力分割硬檢(它結構上就沒有任何寫能力方法)。
    assert kernel.assert_read_only_surface(_Stub()) == []
    monkeypatch.setattr(observer_module, "S2HostObserver", _Stub)


def test_main_withholds_an_observation_carrying_secret_shaped_host_facts(monkeypatch, capsys):
    """主機事實(unit 的 ``Environment=``)帶 secret 形 ⇒ typed 拒 + **stdout 為空**。"""

    _install_observer_returning(monkeypatch, _observation_with(_SECRET_SHAPED_PROPERTY))
    code = observer_module.main(["--request-base64", _encoded({
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_FILE_IDENTITY], "path_keys": ["unit_fragment"],
    })])
    captured = capsys.readouterr()
    assert code == observer_module.EXIT_OBSERVATION_SECRET_LEAK_BLOCKED
    # 絕不寫出被判定含 secret 的內容:一個位元組都沒有。
    assert captured.out == ""
    assert "observation withheld" in captured.err
    # 理由只帶鍵名 trail,值本身絕不入 stderr(否則守衛自己就是第二條洩漏路徑)。
    assert "faces.unit_state.properties.Environment" in captured.err
    assert _SECRET_SHAPED_PROPERTY not in captured.err


def test_main_emits_a_clean_observation_unchanged(monkeypatch, capsys):
    """同一條路徑上,乾淨的觀測照常整份寫出(守衛不是把所有輸出都掐掉)。"""

    clean = _observation_with("ALR_SOURCE_HEAD=" + "0" * 40)
    _install_observer_returning(monkeypatch, clean)
    code = observer_module.main(["--request-base64", _encoded({
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_FILE_IDENTITY], "path_keys": ["unit_fragment"],
    })])
    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    assert json.loads(captured.out) == clean
    assert observer_module.validate_observation(json.loads(captured.out)) == []


def test_the_egress_guard_runs_before_the_stdout_write(monkeypatch):
    """結構釘:守衛必須在 ``sys.stdout.write`` **之前**,而不是寫出之後補一個檢查。"""

    import inspect

    source = inspect.getsource(observer_module.main)
    assert source.index("scan_serializable_surface_for_secrets") < source.index(
        "sys.stdout.write"
    )
    assert "EXIT_OBSERVATION_SECRET_LEAK_BLOCKED" in source


def test_a_non_bool_acknowledgement_is_inadmissible():
    errors = observer_module.validate_observation_request({
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_PROCESS_IDENTITY],
        "allow_production": "true",
    })
    assert any("allow_production must be a bool" in item for item in errors)


# --------------------------------------------------------------------------- #
# face 1 — unit state
# --------------------------------------------------------------------------- #
def test_unit_state_face_issues_exactly_the_owner_show_command():
    executor = _ShowExecutor(_properties(4242))
    observer = observer_module.S2HostObserver(executor=executor)
    observation = observer.observe({
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_UNIT_STATE],
    })
    face = observation["faces"][observer_module.FACE_UNIT_STATE]
    assert executor.argv == [tuple(qi._show_command())]
    assert face["manager_scope"] == "system"
    assert face["missing_properties"] == []
    assert face["properties"]["ActiveState"] == "active"
    # 誠實界線:owner allowlist 無 is-enabled,本波不加寬 ⇒ 該面明記未觀測。
    assert face["unit_file_state_observed"] is False


def test_unit_state_face_without_an_executor_is_typed_refusal():
    observer = observer_module.S2HostObserver()
    with pytest.raises(observer_module.S2HostObserverError):
        observer.observe({
            "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
            "faces": [observer_module.FACE_UNIT_STATE],
        })


def test_unit_state_argv_passes_both_the_owner_and_the_kernel_allowlist():
    argv = list(qi._show_command())
    qi._assert_allowlisted_systemctl(argv)
    assert kernel.assert_session_argv(kernel.SESSION_S2_1_QUIESCE_READ, argv) == tuple(argv)
    assert "--user" not in argv


# --------------------------------------------------------------------------- #
# face 2 — PG role + ACL (no DSN, ever)
# --------------------------------------------------------------------------- #
class _FakeCursor:
    def __init__(self) -> None:
        self._rows: list = []

    def execute(self, statement, parameters=None):
        text = " ".join(str(statement).split())
        if "pg_roles" in text:
            self._rows = [("aiml_observer", False, False, False, False, False, False,
                           ["default_transaction_read_only=on"])]
        elif "pg_class" in text:
            self._rows = [("alr_consumer_events", "{reader=r/postgres}")]
        else:
            self._rows = [("{reader=U/postgres}",)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.closed = False

    def cursor(self):
        return _FakeCursor()

    def close(self):
        self.closed = True


def test_pg_face_reads_role_and_acl_as_the_observer_role():
    seen: dict = {}

    def _connect(**kwargs):
        seen.update(kwargs)
        return _FakeConnection(**kwargs)

    observer = observer_module.S2HostObserver(pg_connect=_connect)
    observation = observer.observe({
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_PG_ACL],
        "pg": {
            "socket_dir": "/var/run/postgresql", "database": "trading_ai",
            "observer_role": "aiml_observer", "observed_schema": "learning",
            "observed_relations": ["alr_consumer_events"],
        },
    })
    face = observation["faces"][observer_module.FACE_PG_ACL]
    assert face["observer_role_present"] is True
    assert face["projection"]["role"]["rolcanlogin"] is False
    assert face["projection_digest"].startswith("sha256:")
    assert seen == {
        "socket_dir": "/var/run/postgresql", "database": "trading_ai", "user": "aiml_observer",
    }


# DSN 形的反例以片段拼接(不在 repo 內留下任何看起來像連線字串的字面量)。
_DSN_SHAPED_SOCKET_DIRS = (
    "post" + "gres" + "://" + "reader" + "@" + "trade-core:5432/db",
    "/var/run/postgresql" + " host=" + "trade-core",
    "var/run/postgresql",
)


@pytest.mark.parametrize("socket_dir", _DSN_SHAPED_SOCKET_DIRS)
def test_pg_face_refuses_any_dsn_shaped_socket_dir(socket_dir):
    observer = observer_module.PgAclObserver(connect=lambda **kwargs: _FakeConnection())
    request = {"socket_dir": socket_dir, "database": "trading_ai",
               "observer_role": "aiml_observer", "observed_schema": "learning",
               "observed_relations": []}
    with pytest.raises(observer_module.S2HostObserverError):
        observer.observe(request)


@pytest.mark.parametrize("field,value", [
    ("database", "trading_ai; DROP TABLE x"),
    ("observer_role", "Reader"),
    ("observed_schema", "1learning"),
])
def test_pg_face_refuses_unsafe_identifiers(field, value):
    observer = observer_module.PgAclObserver(connect=lambda **kwargs: _FakeConnection())
    request = {"socket_dir": "/var/run/postgresql", "database": "trading_ai",
               "observer_role": "aiml_observer", "observed_schema": "learning",
               "observed_relations": [], field: value}
    with pytest.raises(observer_module.S2HostObserverError):
        observer.observe(request)


def test_pg_face_pins_read_only_connection_options_and_never_takes_a_password():
    import inspect

    source = inspect.getsource(observer_module.PgAclObserver._open)
    # 連線層釘死唯讀交易 + pg_catalog search_path;且 ``psycopg2.connect`` 的關鍵字裡沒有 password。
    assert "default_transaction_read_only=on" in source
    assert "search_path=pg_catalog" in source
    assert "password" not in source
    assert "dsn" not in source.lower()
    # 只讀語句:PG 面只跑 SELECT。
    observe_source = inspect.getsource(observer_module.PgAclObserver.observe)
    for verb in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "GRANT", "REVOKE", "ALTER"):
        assert verb not in observe_source


# --------------------------------------------------------------------------- #
# face 3 — file identity (code-owned keys only; symlinks are never followed)
# --------------------------------------------------------------------------- #
def test_file_face_refuses_an_unknown_key_and_never_joins_a_caller_string():
    observer = observer_module.FileIdentityObserver()
    with pytest.raises(observer_module.S2HostObserverError):
        observer.observe(["../../etc/shadow"])
    with pytest.raises(observer_module.S2HostObserverError):
        observer.observe(["/etc/shadow"])
    assert observer.known_keys == [
        "install_root_apps", "install_root_launches", "install_root_runtimes", "unit_fragment",
    ]


def test_file_face_reports_inode_mode_and_never_follows_a_symlink(tmp_path):
    real = tmp_path / "real"
    real.write_text("x", encoding="utf-8")
    os.chmod(real, 0o640)
    link = tmp_path / "link"
    link.symlink_to(real)
    observer = observer_module.FileIdentityObserver({
        "real": str(real), "link": str(link), "absent": str(tmp_path / "absent"),
    })
    observed = observer.observe(["real", "link", "absent"])
    assert observed["real"]["present"] is True
    assert observed["real"]["mode"] == "0640"
    assert observed["real"]["is_symlink"] is False
    assert observed["link"]["is_symlink"] is True
    assert observed["link"]["inode"] != observed["real"]["inode"]
    assert observed["absent"]["present"] is False


def test_canonical_observable_paths_are_derived_from_the_pinned_constants():
    assert observer_module.CANONICAL_OBSERVABLE_PATHS["unit_fragment"] == (
        f"{kernel.SYSTEMD_SYSTEM_UNIT_DIR}/{qi.UNIT_NAME}"
    )
    assert sorted(
        value for key, value in observer_module.CANONICAL_OBSERVABLE_PATHS.items()
        if key.startswith("install_root_")
    ) == sorted(kernel.CANONICAL_INSTALL_ROOTS)


# --------------------------------------------------------------------------- #
# face 4 — process identity calls the inventory SSOT, never re-implements it
# --------------------------------------------------------------------------- #
def _materialize_proc(proc_root: Path, pid: int) -> None:
    (proc_root / "sys" / "kernel" / "random").mkdir(parents=True, exist_ok=True)
    (proc_root / "sys" / "kernel" / "random" / "boot_id").write_text(
        "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
    )
    directory = proc_root / str(pid)
    directory.mkdir(parents=True, exist_ok=True)
    rest = ["S"] + ["0"] * 30
    rest[19] = "998877"
    (directory / "stat").write_text(f"{pid} (python3) " + " ".join(rest) + "\n", encoding="utf-8")
    cmdline = [
        _INTERP, "-I", "-m", "ml_training.alr_event_consumer",
        "--dsn-file", _DSN_FILE, "--lock-file", _FLOCK, "--max-batch", "32",
    ]
    (directory / "cmdline").write_bytes(b"\x00".join(a.encode() for a in cmdline) + b"\x00")
    environ = {
        "ALR_SOURCE_HEAD": "0123456789abcdef0123456789abcdef01234567",
        "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST": "sha256:" + "9" * 64,
        "ALR_EXPECTED_COMPATIBILITY_RECEIPT": "sha256:" + "c" * 64,
    }
    (directory / "environ").write_bytes(
        b"\x00".join(f"{k}={v}".encode() for k, v in environ.items()) + b"\x00"
    )
    (directory / "cgroup").write_text(f"0::{_CG}\n", encoding="utf-8")


def test_process_face_fingerprint_equals_the_inventory_ssot(tmp_path):
    proc_root = tmp_path / "proc"
    _materialize_proc(proc_root, 4242)
    executor = _ShowExecutor(_properties(4242))
    observer = observer_module.S2HostObserver(executor=executor, proc_root=str(proc_root))
    observation = observer.observe({
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_UNIT_STATE, observer_module.FACE_PROCESS_IDENTITY],
        "flock_path": _FLOCK,
    })
    face = observation["faces"][observer_module.FACE_PROCESS_IDENTITY]
    assert face["proc_present"] is True
    assert face["cgroup_matches_unit"] is True
    assert face["runtime_digest"] == "sha256:" + "9" * 64
    # 指紋由 owner SSOT 導出:獨立以 owner 函式重算必逐位元組相同。
    expected = qi.compute_owner_fingerprint(
        main_pid=4242,
        process_start_ticks=qi._read_proc_stat_start_ticks(proc_root, 4242),
        boot_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", control_group=_CG,
        env_hash=face["env_hash"], invocation_id="inv-1",
        cmdline_digest=face["cmdline_digest"], runtime_digest=face["runtime_digest"],
        flock_path=_FLOCK,
    )
    assert face["owner_fingerprint"] == expected


def test_process_face_is_honest_when_the_owner_is_gone(tmp_path):
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    executor = _ShowExecutor({**_properties(0), "ActiveState": "inactive", "SubState": "dead"})
    observer = observer_module.S2HostObserver(executor=executor, proc_root=str(proc_root))
    observation = observer.observe({
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_UNIT_STATE, observer_module.FACE_PROCESS_IDENTITY],
    })
    face = observation["faces"][observer_module.FACE_PROCESS_IDENTITY]
    assert face["proc_present"] is False
    assert face["cmdline_digest"] is None


# --------------------------------------------------------------------------- #
# request / observation contracts
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("request_payload", [
    {"schema_version": "nope", "faces": ["unit_state"]},
    {"schema_version": observer_module.REQUEST_SCHEMA_VERSION, "faces": []},
    {"schema_version": observer_module.REQUEST_SCHEMA_VERSION, "faces": ["make_me_root"]},
    {"schema_version": observer_module.REQUEST_SCHEMA_VERSION, "faces": ["pg_acl"]},
    {"schema_version": observer_module.REQUEST_SCHEMA_VERSION, "faces": ["file_identity"]},
])
def test_inadmissible_requests_fail_closed(request_payload):
    assert observer_module.validate_observation_request(request_payload)


def test_observation_self_digest_is_tamper_evident():
    observer = observer_module.S2HostObserver()
    observation = observer.observe({
        "schema_version": observer_module.REQUEST_SCHEMA_VERSION,
        "faces": [observer_module.FACE_FILE_IDENTITY], "path_keys": ["unit_fragment"],
    })
    assert observer_module.validate_observation(observation) == []
    forged = json.loads(json.dumps(observation))
    forged["faces"][observer_module.FACE_FILE_IDENTITY]["unit_fragment"]["present"] = True
    assert observer_module.validate_observation(forged)


def test_observation_is_not_a_receipt_and_is_not_registered_centrally():
    import aiml_gate_receipt_validator as validator

    # R4:runner 不得產出自己的新 receipt schema。observer 的傳輸 payload 因此**不**在中央閘註冊。
    assert observer_module.OBSERVATION_SCHEMA_VERSION not in validator.SCHEMA_FILES


# --------------------------------------------------------------------------- #
# honest boundary — the governed command_capture_v2 binding is NOT provided here
# --------------------------------------------------------------------------- #
def test_governed_capture_of_the_observer_is_not_available_in_this_wave():
    """釘住本波的誠實邊界(§B.2 L2 的 capture 綁定部分未交付)。

    ``authorize_native_command`` 今日只承認 S1.6B 那一支 target-host observation script;要讓
    observer 的輸出成為一份 governed ``command_capture_v2``(closure 硬門要求的第三份 evidence)
    必須加寬 ``agent_governance_permissions.py`` 的 allowlist,而該檔不在 S2E.2a 的 owned path 內
    (加寬一個安全 allowlist 屬 scope 擴張,需自己的審查)。此測試釘住現況:未來一旦加寬,
    本測試變紅,沒有人能在無聲中越過這個邊界。
    """

    from agent_governance_permissions import authorize_native_command

    argv = kernel.observer_child_argv("QQ==")
    decision = authorize_native_command("OPS", " ".join(argv))
    assert decision["allowed"] is False

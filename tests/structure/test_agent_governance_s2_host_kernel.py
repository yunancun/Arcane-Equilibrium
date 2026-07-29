"""S2E.2a:S2 受信主機 runner 家族 kernel 的結構證明。

四道 §E.3「禁止 raw command 繞過 Adapter」全部在此執法,其中第四道(AST 掃描)是本波**驗收的
機器判準**:

1. 唯一 exec 點 —— kernel 之外的 runner 家族檔案不得出現 ``subprocess`` / ``os.system`` /
   ``os.popen`` / ``shell=True`` / ``eval`` / ``exec`` / ``__import__``;
2. kernel 側獨立 re-assert —— 非 allowlist argv 一律 raise 且**絕不執行**;
3. 能力分割硬檢 —— ``assert_read_only_surface`` 在呼叫任何方法之前拒絕寫能力面;
4. allowlist ≡ 原 owner 集合 —— 以「錄音式 host_probe 驅動 ``build_owner_inventory``」比對實際
   送出的 argv,證明 kernel 的表是**導出**而非手抄。

另證 target class 由主機事實導出(caller 字串永遠進不來)、``unknown`` 與 ``production`` 同等
對待、``--allow-production`` 單獨不足,以及 ``PR_SET_DUMPABLE`` 真的被執法。
"""

from __future__ import annotations

import ast
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


# ── runner 家族(§G owned paths;AST 掃描的對象) ──
KERNEL_PATH = HELPERS / "agent_governance_s2_host_kernel.py"
RUNNER_FAMILY = (
    KERNEL_PATH,
    HELPERS / "agent_governance_s2_host_observer.py",
    HELPERS / "agent_governance_s2_0_host_runner.py",
    HELPERS / "agent_governance_s2_1_host_runner.py",
    HELPERS / "aiml_s2_effect_host_run.py",
)
# 四個 S2 effect adapter 的 apply 進入點 + 其驅動葉:observer/kernel 的 import closure 不得含它們。
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
})

FORBIDDEN_RAW_COMMAND_NAMES = ("system", "popen", "spawnl", "spawnv", "execv", "execve")
FORBIDDEN_BUILTINS = ("eval", "exec", "compile", "__import__")


def _present_family() -> list[Path]:
    return [path for path in RUNNER_FAMILY if path.is_file()]


# --------------------------------------------------------------------------- #
# (4) ★驗收判準★ — AST no-raw-command scan over the runner family
# --------------------------------------------------------------------------- #
def _raw_command_findings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"subprocess", "pty", "commands"}:
                    findings.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] in {"subprocess", "pty", "commands"}:
                findings.append(f"line {node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_RAW_COMMAND_NAMES and isinstance(node.value, ast.Name):
                if node.value.id in {"os", "subprocess"}:
                    findings.append(f"line {node.lineno}: {node.value.id}.{node.attr}")
        elif isinstance(node, ast.Name):
            if node.id in FORBIDDEN_BUILTINS and isinstance(node.ctx, ast.Load):
                findings.append(f"line {node.lineno}: builtin {node.id}")
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "shell" and not (
                    isinstance(keyword.value, ast.Constant) and keyword.value.value is False
                ):
                    findings.append(f"line {node.lineno}: shell= is not the constant False")
    return findings


def test_no_raw_command_outside_the_kernel():
    present = _present_family()
    assert KERNEL_PATH in present
    for path in present:
        findings = _raw_command_findings(path)
        if path == KERNEL_PATH:
            # kernel 是唯一 exec 點:它**必須**帶 subprocess,但也只准帶 subprocess。
            assert any("import subprocess" in item for item in findings), findings
            residue = [item for item in findings if "import subprocess" not in item]
            assert residue == [], residue
        else:
            assert findings == [], f"{path.name} carries a raw-command surface: {findings}"


def test_the_ast_scanner_actually_catches_a_violation(tmp_path):
    # 反例:掃描器若抓不到違規就是空轉。逐一注入四類違規,必須全部被抓到。
    samples = {
        "import subprocess\n": "import subprocess",
        "import os\nos.system('x')\n": "os.system",
        "import subprocess\nsubprocess.run(['x'], shell=True)\n": "shell=",
        "eval('1')\n": "builtin eval",
    }
    for index, (source, expected) in enumerate(samples.items()):
        path = tmp_path / f"violation_{index}.py"
        path.write_text(source, encoding="utf-8")
        findings = _raw_command_findings(path)
        assert any(expected in item for item in findings), (source, findings)


def test_kernel_is_the_only_family_member_importing_subprocess():
    for path in _present_family():
        source = path.read_text(encoding="utf-8")
        if path == KERNEL_PATH:
            assert "import subprocess" in source
        else:
            assert "subprocess" not in source, path.name


# --------------------------------------------------------------------------- #
# (1)+(4) allowlist ≡ owner — derived, not hand-copied
# --------------------------------------------------------------------------- #
_FRAG = "/etc/systemd/system/arcane-equilibrium-aiml-engine-scanner.service"
_FLOCK = "/run/arcane-equilibrium/aiml-engine-scanner/consumer.lock"
_DSN = "/run/credentials/arcane-equilibrium-aiml-engine-scanner.service/pg-dsn"


class _RecordingProbe:
    """錄音式 host_probe:記下 owner 模組**實際**送出的每一條 argv。"""

    def __init__(self, proc_root: Path) -> None:
        self.proc_root = proc_root
        self.argv: list[tuple[str, ...]] = []

    def run(self, argv):
        self.argv.append(tuple(argv))
        if list(argv[:3]) == [qi.SYSTEMD, "show", qi.UNIT_NAME]:
            props = {
                "LoadState": "loaded", "ActiveState": "active", "SubState": "running",
                "MainPID": "0", "InvocationID": "inv", "NRestarts": "0", "ControlGroup": "",
                "FragmentPath": _FRAG, "DropInPaths": "", "NeedDaemonReload": "no",
                "Environment": "", "Restart": "on-failure", "RestartUSec": "5s",
                "TimeoutStopUSec": "30s", "WatchdogUSec": "0", "NoNewPrivileges": "yes",
                "ProtectSystem": "full", "PrivateTmp": "yes",
                "RestrictAddressFamilies": "AF_UNIX",
            }
            return "\n".join(f"{key}={props[key]}" for key in qi.QUIESCE_SHOW_PROPERTIES)
        if list(argv[:2]) == [qi.SYSTEMD, "list-units"]:
            return ""
        raise AssertionError(f"unexpected argv: {argv}")

    def dsn_stat(self):
        return {"dsn_file_path": _DSN, "dsn_mode": "0600", "dsn_owner_uid": 4001,
                "world_readable": False}

    def flock_held(self):
        return True


class _ScriptedCursor:
    """read_db_quiesce 的最小回應腳本(hashtext → holders → session*3 → queue usage)。"""

    def __init__(self) -> None:
        self._rows: list = []

    def execute(self, statement, parameters=None):
        text = " ".join(str(statement).split())
        if text.startswith("SELECT hashtext"):
            self._rows = [(1234,)]
        elif "pg_locks" in text:
            self._rows = []
        elif "pg_notification_queue_usage" in text:
            self._rows = [(0.0,)]
        else:
            self._rows = [(0,)]

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


def test_kernel_read_allowlist_equals_the_argv_the_owner_actually_issues(tmp_path):
    proc_root = tmp_path / "proc"
    (proc_root / "sys" / "kernel" / "random").mkdir(parents=True)
    (proc_root / "sys" / "kernel" / "random" / "boot_id").write_text("b\n", encoding="utf-8")
    probe = _RecordingProbe(proc_root)
    intent = {
        "flock_path": _FLOCK,
        "unit_fragment_path": _FRAG,
        "advisory_lock_name": qi.ADVISORY_LOCK_NAME,
        "consumer_session_relation": qi.DEFAULT_CONSUMER_SESSION_RELATION,
    }
    qi.build_owner_inventory(probe, _ScriptedCursor(), intent=intent)
    issued = set(probe.argv)
    assert issued, "the owner module issued no host command"
    # 導出比對(非手抄):owner 實際送出的每一條 argv 都在 kernel 的唯讀 allowlist 內,且兩者相等。
    assert issued == set(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])


def test_kernel_read_allowlist_is_accepted_by_the_owner_assert():
    for argv in kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ]:
        qi._assert_allowlisted_systemctl(list(argv))


def test_fence_allowlist_is_exactly_the_units_own_stop_start():
    fence = kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_FENCE]
    assert fence == frozenset({
        (qi.SYSTEMD, "stop", qi.UNIT_NAME),
        (qi.SYSTEMD, "start", qi.UNIT_NAME),
    })
    # fence argv 絕不是 pkill / kill-by-name / kill-by-pattern / kill-by-pid,也永遠不是 --user。
    for argv in fence:
        assert argv[0] == qi.SYSTEMD
        assert argv[2] == qi.UNIT_NAME
        assert "--user" not in argv


def test_s2_0_session_has_no_argv_surface_at_all():
    assert kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_0_OBSERVER_BOOTSTRAP] == frozenset()
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        kernel.assert_session_argv(kernel.SESSION_S2_0_OBSERVER_BOOTSTRAP, ["/usr/bin/psql", "-c", "select 1"])


# --------------------------------------------------------------------------- #
# (2) kernel-side independent re-assert — a non-allowlisted argv NEVER executes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("argv", [
    [qi.SYSTEMD, "stop", qi.UNIT_NAME],                                   # 唯讀 session 不得 stop
    [qi.SYSTEMD, "show", qi.UNIT_NAME],                                   # 屬性集不完整
    [qi.SYSTEMD, "--user", "show", qi.UNIT_NAME],                         # --user 形
    ["systemctl", "list-units", "--type=scope", "--state=active",
     "--no-legend", "--no-pager"],                                        # 非絕對路徑
    [qi.SYSTEMD, "list-units", "--type=scope", "--state=active", "--no-legend"],
])
def test_non_allowlisted_argv_raises_and_never_executes(argv, monkeypatch):
    def _boom(*args, **kwargs):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("subprocess.run must never be reached for a non-allowlisted argv")

    monkeypatch.setattr(subprocess, "run", _boom)
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        host.run(argv)
    assert host.calls == []


def test_shell_string_argv_is_refused(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    with pytest.raises(kernel.S2HostArgvNotAllowlisted):
        host.run(f"{qi.SYSTEMD} show {qi.UNIT_NAME}")


def test_there_is_no_generic_session():
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(session="generic")
    with pytest.raises(kernel.S2HostSessionError):
        kernel.session_argv_allowlist("anything_else")


def test_mutating_session_requires_explicit_acknowledgement():
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_FENCE)
    with pytest.raises(kernel.S2HostSessionError):
        kernel.HostExecutionKernel(
            session=kernel.SESSION_S2_1_QUIESCE_READ, allow_mutation=True
        )
    fence = kernel.HostExecutionKernel(
        session=kernel.SESSION_S2_1_QUIESCE_FENCE, allow_mutation=True
    )
    assert fence.allow_mutation is True


def test_kernel_execution_is_shell_false_absolute_and_sanitized(monkeypatch):
    captured: dict = {}

    class _Completed:
        returncode = 0
        stdout = b"LoadState=loaded\n"
        stderr = b""

    def _fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return _Completed()

    monkeypatch.setattr(subprocess, "run", _fake_run)
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    output = host.run(list(allowed))
    assert output == "LoadState=loaded\n"
    assert captured["argv"] == list(allowed)
    assert captured["argv"][0].startswith("/")
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["timeout"] == kernel.SESSION_TIMEOUT_SECONDS[
        kernel.SESSION_S2_1_QUIESCE_READ
    ]
    environment = captured["kwargs"]["env"]
    assert environment["LC_ALL"] == "C"
    assert not {"HOME", "PGPASSWORD", "PYTHONPATH"} & set(environment)


def test_nonzero_exit_and_timeout_fail_closed(monkeypatch):
    class _Failed:
        returncode = 3
        stdout = b""
        stderr = b"boom"

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Failed())
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    with pytest.raises(kernel.S2HostCommandFailed):
        host.run(list(allowed))

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    with pytest.raises(kernel.S2HostCommandFailed):
        host.run(list(allowed))


def test_stdout_is_redacted_with_the_existing_capture_v2_patterns(monkeypatch):
    class _Completed:
        returncode = 0
        stdout = b"Environment=PGPASSWORD=hunter2\n"
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed())
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    output = host.run(list(allowed))
    assert "hunter2" not in output
    assert "<redacted>" in output


# --------------------------------------------------------------------------- #
# (3) capability partition
# --------------------------------------------------------------------------- #
class _WriterSurface:
    def stop(self):  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("assert_read_only_surface must refuse BEFORE calling anything")

    def read(self):
        return "ok"


class _ReaderSurface:
    def read(self):
        return "ok"


def test_assert_read_only_surface_refuses_before_calling_anything():
    errors = kernel.assert_read_only_surface(_WriterSurface())
    assert errors and "stop" in errors[0]
    assert kernel.assert_read_only_surface(_ReaderSurface()) == []


def test_forbidden_read_only_surface_covers_the_four_adapter_mutators():
    for name in ("stop", "start", "create_read_only_observer", "compensate",
                 "signed_apply_attestation", "enable_now"):
        assert name in kernel.FORBIDDEN_READ_ONLY_SURFACE


# --------------------------------------------------------------------------- #
# target class is derived from HOST FACTS (a caller string can never reach it)
# --------------------------------------------------------------------------- #
def _force_host(monkeypatch, *, platform, hostname, writable, roots):
    monkeypatch.setattr(kernel.sys, "platform", platform)
    monkeypatch.setattr(kernel.socket, "gethostname", lambda: hostname)
    monkeypatch.setattr(kernel, "_writable", lambda path: writable)
    monkeypatch.setattr(kernel, "_present", lambda path: roots)


@pytest.mark.parametrize("platform,hostname,writable,roots,expected", [
    ("darwin", "trade-core", True, True, kernel.TARGET_CLASS_NON_TARGET),
    ("linux", "some-laptop", True, True, kernel.TARGET_CLASS_NON_TARGET),
    ("linux", "trade-core", False, False, kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE),
    ("linux", "trade-core", True, True, kernel.TARGET_CLASS_PRODUCTION),
    ("linux", "trade-core", None, True, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", True, None, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", True, False, kernel.TARGET_CLASS_UNKNOWN),
    ("linux", "trade-core", False, True, kernel.TARGET_CLASS_UNKNOWN),
])
def test_derive_host_target_class_matrix(monkeypatch, platform, hostname, writable, roots, expected):
    _force_host(monkeypatch, platform=platform, hostname=hostname, writable=writable, roots=roots)
    view = kernel.derive_host_target_class()
    assert view["target_class"] == expected
    assert view["facts"]["hostname"] == hostname


def test_derive_host_target_class_takes_no_caller_argument():
    import inspect

    assert list(inspect.signature(kernel.derive_host_target_class).parameters) == []


def test_this_development_machine_is_never_a_production_target():
    # Mac 開發機:不論本地檔案系統長什麼樣,必為 non_target(絕不可能誤判成 production)。
    view = kernel.derive_host_target_class()
    if sys.platform != "linux":
        assert view["target_class"] == kernel.TARGET_CLASS_NON_TARGET


# --------------------------------------------------------------------------- #
# production / unknown admission matrix — --allow-production alone is NOT enough
# --------------------------------------------------------------------------- #
DIGEST = "sha256:" + "a" * 64


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
def test_allow_production_alone_is_insufficient(target_class):
    view = {"target_class": target_class, "reason": "x", "facts": {}}
    errors = kernel.host_target_admission_errors(
        view, allow_production=True, production_confirm=None,
        intent_digest=DIGEST, operator_authorization_verified=False,
    )
    assert errors
    assert any("operator SSHSIG" in error for error in errors)
    assert any("--production-confirm" in error for error in errors)


@pytest.mark.parametrize("target_class", sorted(kernel.PRODUCTION_GRADE_TARGET_CLASSES))
def test_all_three_conditions_admit_and_any_missing_one_refuses(target_class):
    view = {"target_class": target_class, "reason": "x", "facts": {}}
    assert kernel.host_target_admission_errors(
        view, allow_production=True, production_confirm=DIGEST,
        intent_digest=DIGEST, operator_authorization_verified=True,
    ) == []
    for override in (
        {"allow_production": False},
        {"operator_authorization_verified": False},
        {"production_confirm": "sha256:" + "b" * 64},
        {"production_confirm": None},
    ):
        kwargs = {
            "allow_production": True, "production_confirm": DIGEST,
            "intent_digest": DIGEST, "operator_authorization_verified": True,
            **override,
        }
        assert kernel.host_target_admission_errors(view, **kwargs)


def test_non_target_is_refused_and_disposable_candidate_is_admitted():
    assert kernel.host_target_admission_errors(
        {"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"},
        allow_production=True, production_confirm=DIGEST, intent_digest=DIGEST,
        operator_authorization_verified=True,
    )
    assert kernel.host_target_admission_errors(
        {"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, "reason": "throwaway"},
        allow_production=False, production_confirm=None, intent_digest=None,
        operator_authorization_verified=False,
    ) == []


def test_unknown_is_treated_exactly_like_production():
    unknown = {"target_class": kernel.TARGET_CLASS_UNKNOWN, "reason": "x"}
    production = {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x"}
    for kwargs in (
        {"allow_production": False, "production_confirm": DIGEST, "intent_digest": DIGEST,
         "operator_authorization_verified": True},
        {"allow_production": True, "production_confirm": None, "intent_digest": DIGEST,
         "operator_authorization_verified": True},
    ):
        assert bool(kernel.host_target_admission_errors(unknown, **kwargs)) == bool(
            kernel.host_target_admission_errors(production, **kwargs)
        )


# --------------------------------------------------------------------------- #
# rehearsal lane — an injected view may only TIGHTEN, never loosen (RUN-1)
# --------------------------------------------------------------------------- #
DISPOSABLE = {"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE, "reason": "throwaway"}
NON_TARGET = {"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"}


@pytest.mark.parametrize("derived,injected,refused", [
    (DISPOSABLE, None, False),
    (NON_TARGET, None, False),
    # derived 落在 production-grade ⇒ 拒,任何注入都救不回來(注入不能放寬)。
    ({"target_class": kernel.TARGET_CLASS_PRODUCTION}, None, True),
    ({"target_class": kernel.TARGET_CLASS_UNKNOWN}, None, True),
    ({"target_class": kernel.TARGET_CLASS_PRODUCTION}, DISPOSABLE, True),
    ({"target_class": kernel.TARGET_CLASS_UNKNOWN}, DISPOSABLE, True),
    # injected 落在 production-grade ⇒ 也拒(注入只能加嚴)。
    (NON_TARGET, {"target_class": kernel.TARGET_CLASS_PRODUCTION}, True),
    (NON_TARGET, {"target_class": kernel.TARGET_CLASS_UNKNOWN}, True),
    (DISPOSABLE, {"target_class": kernel.TARGET_CLASS_PRODUCTION}, True),
])
def test_rehearsal_refusal_is_the_stricter_of_derived_and_injected(derived, injected, refused):
    assert bool(kernel.rehearsal_target_refusals(derived, injected)) is refused


def test_rehearsal_unknown_is_treated_exactly_like_production():
    assert kernel.REHEARSAL_REFUSED_TARGET_CLASSES == frozenset(
        {kernel.TARGET_CLASS_PRODUCTION, kernel.TARGET_CLASS_UNKNOWN}
    )


def test_the_recorded_target_class_is_always_the_derived_one():
    record = kernel.rehearsal_target_view_record(
        DISPOSABLE, {"target_class": kernel.TARGET_CLASS_NON_TARGET}
    )
    assert record["target_class"] == kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE
    assert record["derived"] is DISPOSABLE
    assert record["injected"] == {"target_class": kernel.TARGET_CLASS_NON_TARGET}
    assert record["injected_is_authoritative"] is False


# --------------------------------------------------------------------------- #
# W5 #21 — PR_SET_DUMPABLE is actually enforced (not a declared constant)
# --------------------------------------------------------------------------- #
def test_process_hardening_is_observed_and_load_bearing():
    observation = kernel.enforce_process_hardening(force=True)
    if sys.platform == "linux":
        assert observation == {"enforced": True, "observed_dumpable": 0, "reason": None}
    else:
        assert observation["enforced"] is False
        assert observation["observed_dumpable"] is None
        assert "not a target host" in observation["reason"]


def test_process_hardening_refusal_blocks_execution(monkeypatch):
    def _refuse(*args, **kwargs):
        raise kernel.S2HostKernelError("PR_GET_DUMPABLE observed 1")

    monkeypatch.setattr(kernel, "enforce_process_hardening", _refuse)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("must not execute"))
    host = kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ)
    allowed = sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ])[0]
    with pytest.raises(kernel.S2HostKernelError):
        host.run(list(allowed))


# --------------------------------------------------------------------------- #
# derived constants are pinned against their owners (no re-invented host facts)
# --------------------------------------------------------------------------- #
def test_target_hostnames_are_pinned_to_the_s1_target_host():
    import agent_governance_target_host_probe as th

    assert kernel.TARGET_HOSTNAMES == frozenset({th.EXPECTED_TARGET_HOST_DEFAULT})


def test_canonical_roots_and_unit_dir_match_the_s2_4_constants():
    import agent_governance_s2_4_apply as s2_4_apply

    assert set(kernel.CANONICAL_INSTALL_ROOTS) == set(s2_4_apply.INSTALL_ROOTS.values())
    assert kernel.SYSTEMD_SYSTEM_UNIT_DIR == str(
        Path(s2_4_apply.UNIT_FRAGMENT_PATH).parent
    )


def test_kernel_import_closure_excludes_every_applier_module():
    argv = [
        sys.executable, "-c",
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
        "import agent_governance_s2_host_kernel; "
        "print('\\n'.join(sorted(sys.modules)))" % (str(ML_ROOT), str(HELPERS)),
    ]
    loaded = set(
        subprocess.run(argv, capture_output=True, text=True, check=True).stdout.split()
    )
    assert not (loaded & APPLIER_MODULES), sorted(loaded & APPLIER_MODULES)


def test_kernel_abi_projection_is_code_owned():
    projection = kernel.kernel_abi_projection()
    assert projection["sessions"] == sorted(kernel.SESSION_ARGV_ALLOWLISTS)
    assert projection["mutating_sessions"] == [kernel.SESSION_S2_1_QUIESCE_FENCE]
    assert projection["production_grade_target_classes"] == sorted(
        {kernel.TARGET_CLASS_PRODUCTION, kernel.TARGET_CLASS_UNKNOWN}
    )

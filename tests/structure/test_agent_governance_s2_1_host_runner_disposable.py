"""S2E.2a:S2.1 受信主機 runner 的**拋棄式 rehearsal**(T1)+ 獨立 re-assert 證明(T0)。

T0(恆跑,含 Mac):

* ``QuiesceHostProbe.run`` 的**獨立 re-assert** —— 繞過 owner 模組直接把任意 argv 遞進 probe
  一律 raise 且 executor **從未**被呼叫(這是 §E.3 #2 今日真正的洞:S2.1 的 allowlist 只在
  caller 側,``host_probe.run(argv)`` 本身收任意 argv);
* ``QuiesceFenceOps`` 的 argv 由 code 構造成該 unit 自身的 stop/start,永遠不是 pkill /
  kill-by-name / kill-by-pattern / kill-by-pid,也永遠不帶 ``--user``;
* 能力分割:probe / db_observer 面上沒有任何寫能力方法,裸連線(帶 commit/rollback)則被拒;
* production 拒絕矩陣:被拒時 ``capability_factory`` **從未**被呼叫(主機零接觸)。

T1(需 ``initdb``/``pg_ctl``/``psycopg2``,缺任一則相關測試誠實 SKIP):五個 operator 場景 +
「窗內拋錯證 ``finally`` 真的 un-fence」,全部**經 runner 自己的類別**(非測試內 fake)驅動,
DB 端是真 ``pg_try_advisory_lock`` 的 held → free → re-held,``dsn_stat()`` / ``flock_held()``
對真的臨時檔與真的 ``/proc/locks`` 格式解析執行。host 端 systemd 是注入的模擬器,誠實標示。

**誠實界線**:``QUIESCED_STATIC_GUARDS_HELD`` 被 schema 釘成 disposable_local +
LOCAL_REPRODUCIBLE + ``production_fence_performed=false``,S2E.1 另已把 S2.1 標成
closure-PASS-blocked ⇒ rehearsal 綠不是 closure PASS,也不是 EFFECT 進展。真 live ALR owner
從未被 signal,生產 systemd 從未被接觸。
"""

from __future__ import annotations

import copy
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_alr_quiesce_fence as q  # noqa: E402
import agent_governance_alr_quiesce_inventory as qi  # noqa: E402
import agent_governance_pg_observer_bootstrap as observer  # noqa: E402
import agent_governance_s2_1_host_runner as runner  # noqa: E402
import agent_governance_s2_host_kernel as kernel  # noqa: E402
import aiml_gate_receipt_validator as validator  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")

DB = "postgres"
OBSERVER_ROLE = "aiml_s2e2_q_observer"
ASSUME_ROLE = "aiml_s2e2_q_assume"
SESSION_SCHEMA = "learning"
SESSION_TABLE = "alr_consumer_events"
SESSION_RELATION = f"{SESSION_SCHEMA}.{SESSION_TABLE}"

HEAD = "0123456789abcdef0123456789abcdef01234567"
CREATED = "2026-07-28T12:00:00+00:00"
NOW = "2026-07-28T12:01:00+00:00"
LATER = "2026-07-28T12:02:00+00:00"
CAP = "sha256:" + "e" * 64

FRAG = f"{kernel.SYSTEMD_SYSTEM_UNIT_DIR}/{qi.UNIT_NAME}"
INTERP = "/opt/arcane-equilibrium/aiml/runtimes/" + "b" * 64 + "/bin/python3"
CG = "/system.slice/" + qi.UNIT_NAME
ENVIRON = {
    "ALR_SOURCE_HEAD": HEAD,
    "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST": "sha256:" + "9" * 64,
    "ALR_EXPECTED_COMPATIBILITY_RECEIPT": "sha256:" + "c" * 64,
}
CLEAN_SUBPROCESS_ENV = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}


# --------------------------------------------------------------------------- #
# T0 — independent re-assert / capability partition / production refusal
# --------------------------------------------------------------------------- #
class _RecordingExecutor:
    def __init__(self) -> None:
        self.argv: list[tuple[str, ...]] = []

    def run(self, argv):
        self.argv.append(tuple(argv))
        return ""


@pytest.mark.parametrize("argv", [
    [qi.SYSTEMD, "stop", qi.UNIT_NAME],
    [qi.SYSTEMD, "--user", "show", qi.UNIT_NAME],
    ["/usr/bin/pkill", "-f", "alr_event_consumer"],
    [qi.SYSTEMD, "kill", qi.UNIT_NAME],
    ["/bin/sh", "-c", "systemctl stop x"],
])
def test_probe_run_independently_re_asserts_and_never_reaches_the_executor(argv):
    executor = _RecordingExecutor()
    probe = runner.QuiesceHostProbe(executor=executor, proc_root="/proc")
    with pytest.raises((qi.QuiesceHostReadError, kernel.S2HostArgvNotAllowlisted)):
        probe.run(argv)
    assert executor.argv == []
    assert probe.argv == []


def test_probe_run_admits_exactly_the_two_owner_read_commands():
    executor = _RecordingExecutor()
    probe = runner.QuiesceHostProbe(executor=executor, proc_root="/proc")
    for argv in sorted(kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ]):
        probe.run(list(argv))
    assert set(executor.argv) == kernel.SESSION_ARGV_ALLOWLISTS[
        kernel.SESSION_S2_1_QUIESCE_READ
    ]


def test_fence_ops_argv_is_the_units_own_lifecycle_only():
    executor = _RecordingExecutor()
    fence_ops = runner.QuiesceFenceOps(executor=executor)
    fence_ops.stop()
    fence_ops.start()
    assert executor.argv == [
        (qi.SYSTEMD, "stop", qi.UNIT_NAME),
        (qi.SYSTEMD, "start", qi.UNIT_NAME),
    ]
    for argv in executor.argv:
        assert "--user" not in argv
        assert "pkill" not in argv[0]
        assert argv[2] == qi.UNIT_NAME
    # fence argv 也必須落在 kernel 的 fence allowlist 內(而不在唯讀 allowlist 內)。
    for argv in executor.argv:
        kernel.assert_session_argv(kernel.SESSION_S2_1_QUIESCE_FENCE, list(argv))
        with pytest.raises(kernel.S2HostArgvNotAllowlisted):
            kernel.assert_session_argv(kernel.SESSION_S2_1_QUIESCE_READ, list(argv))


def test_read_only_surfaces_carry_no_mutating_capability():
    probe = runner.QuiesceHostProbe(executor=_RecordingExecutor(), proc_root="/proc")
    assert kernel.assert_read_only_surface(probe) == []
    fence_ops = runner.QuiesceFenceOps(executor=_RecordingExecutor())
    assert kernel.assert_read_only_surface(fence_ops)     # fence 面**必須**被認出是寫能力面

    class _BareConnection:
        def cursor(self):
            return None

        def commit(self):  # pragma: no cover - 只是用來被拒
            raise AssertionError

        def rollback(self):  # pragma: no cover - 只是用來被拒
            raise AssertionError

    bare = _BareConnection()
    assert kernel.assert_read_only_surface(bare)          # 裸連線帶 commit/rollback → 拒
    assert kernel.assert_read_only_surface(runner.QuiesceDbObserver(bare)) == []


def _intent(expected_fingerprint, *, target_class="disposable_local", window=None,
            flock_path="/run/arcane-equilibrium/aiml-engine-scanner/consumer.lock"):
    return q.build_quiesce_intent(
        target_class=target_class, target_host="trade-core", unit_fragment_path=FRAG,
        expected_owner_fingerprint=expected_fingerprint, flock_path=flock_path,
        observed_relations=[SESSION_RELATION], consumer_session_relation=SESSION_RELATION,
        observation_window=window or {"duration_seconds": 5, "min_samples": 2,
                                      "sample_interval_seconds": 5},
        applier_node_id="s2_1_apply_actor", postcheck_node_id="s2_1_ops_postcheck",
        created_at=CREATED, ttl_seconds=900, source_head=HEAD,
    )


PRODUCTION_VIEWS = [
    {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x", "facts": {}},
    {"target_class": kernel.TARGET_CLASS_UNKNOWN, "reason": "x", "facts": {}},
]


def _force_derived(monkeypatch, view):
    """target class 只能被主機事實決定 ⇒ 測試也只能從 ``derive_host_target_class`` 這一點造假。"""

    monkeypatch.setattr(kernel, "derive_host_target_class", lambda: view)


# --------------------------------------------------------------------------- #
# RUN-1:production lane 完全不收 caller view
# --------------------------------------------------------------------------- #
def test_production_lane_takes_no_caller_target_view():
    import inspect

    assert "target_view" not in inspect.signature(runner.run_quiesce_fence_on_host).parameters


def test_a_forged_target_view_cannot_reach_the_production_lane(monkeypatch):
    _force_derived(monkeypatch, PRODUCTION_VIEWS[0])
    intent = _intent("sha256:" + "0" * 64, target_class="production")

    def _factory():  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("no fence capability may be built when admission refuses")

    with pytest.raises(TypeError):
        runner.run_quiesce_fence_on_host(
            intent, None, None, now=NOW, source_head=HEAD, capability_factory=_factory,
            target_view={"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE},
            allow_production=True, production_confirm=intent["self_digest"],
            operator_authorization_verified=True,
        )


@pytest.mark.parametrize("view", PRODUCTION_VIEWS)
@pytest.mark.parametrize("kwargs", [
    {},
    {"allow_production": True},
    {"allow_production": True, "operator_authorization_verified": True},
    {"allow_production": True, "production_confirm": "sha256:" + "9" * 64},
])
def test_production_refusal_never_builds_a_fence_capability(monkeypatch, view, kwargs):
    _force_derived(monkeypatch, view)
    intent = _intent("sha256:" + "0" * 64, target_class="production")

    def _factory():  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("no fence capability may be built when admission refuses")

    with pytest.raises(runner.S2_1HostRunnerError):
        runner.run_quiesce_fence_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            capability_factory=_factory, **kwargs,
        )


# --------------------------------------------------------------------------- #
# RUN-3:production lane 拒絕非 runner 自有的 capability 物件
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("view", PRODUCTION_VIEWS)
def test_a_disposable_local_intent_never_builds_a_fence_capability(monkeypatch, view):
    """P1-B:``disposable_local`` intent 在生產級主機上必須在 ``capability_factory`` **之前**被拒。

    這是最嚴重的一形:``apply_quiesce_fence`` 的 disposable 分支會對**真的** kernel capability 發
    system-level ``stop``/``start``,再把那次真實 effect 標成 rehearsal 級的 local 證據。
    """

    _force_derived(monkeypatch, view)
    intent = _intent("sha256:" + "0" * 64, target_class="disposable_local")

    def _factory():  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("no fence capability may be built for a mismatched intent class")

    with pytest.raises(runner.S2_1HostRunnerError) as error:
        runner.run_quiesce_fence_on_host(
            intent, None, None, now=NOW, source_head=HEAD, capability_factory=_factory,
            allow_production=True, production_confirm=intent["self_digest"],
            operator_authorization_verified=True,
        )
    assert "disposable_local" in str(error.value)


def test_the_runner_binds_the_intent_class_before_building_anything():
    """結構釘:admission 必須在 ``capability_factory()`` 之前,且真的把 intent 的 class 遞進去。"""

    import inspect

    source = inspect.getsource(runner.run_quiesce_fence_on_host)
    assert 'intent_target_class=intent.get("target_class")' in source
    assert source.index("_require_host_admission") < source.index("capability_factory()")


def test_production_lane_refuses_foreign_capability_objects(monkeypatch):
    _force_derived(monkeypatch, PRODUCTION_VIEWS[0])
    intent = _intent("sha256:" + "0" * 64, target_class="production")

    class _ForeignFenceOps:
        """一個**真的會 stop** 主機、但 runner 報不出 stop_calls 的注入物件。"""

        def stop(self):  # pragma: no cover - 必須永不被呼叫
            raise AssertionError("a foreign fence capability must be refused before any call")

        def start(self):  # pragma: no cover - 必須永不被呼叫
            raise AssertionError("a foreign fence capability must be refused before any call")

    def _factory():
        return {
            "host_probe": runner.QuiesceHostProbe(
                executor=_RecordingExecutor(), proc_root="/proc"
            ),
            "fence_ops": _ForeignFenceOps(),
            "db_observer": runner.QuiesceDbObserver(None),
        }

    with pytest.raises(runner.S2_1HostRunnerError) as error:
        runner.run_quiesce_fence_on_host(
            intent, None, None, now=NOW, source_head=HEAD, capability_factory=_factory,
            allow_production=True, production_confirm=intent["self_digest"],
            operator_authorization_verified=True,
        )
    assert "unobservable capabilities" in str(error.value)
    assert "fence_ops=" in str(error.value)


def test_production_lane_refuses_a_subclass_that_drops_the_counters(monkeypatch):
    """RES-4:``isinstance`` 收子類別 ⇒ 覆寫 ``stop()`` 不加計數器仍過閘,零值又被當成事實。"""

    _force_derived(monkeypatch, PRODUCTION_VIEWS[0])
    intent = _intent("sha256:" + "0" * 64, target_class="production")

    class _SilentFenceOps(runner.QuiesceFenceOps):
        def stop(self):  # pragma: no cover - 必須永不被呼叫
            raise AssertionError("a counter-dropping subclass must be refused before any call")

    def _factory():
        return {
            "host_probe": runner.QuiesceHostProbe(
                executor=kernel.HostExecutionKernel(session=kernel.SESSION_S2_1_QUIESCE_READ),
                proc_root="/proc",
            ),
            "fence_ops": _SilentFenceOps(
                executor=kernel.HostExecutionKernel(
                    session=kernel.SESSION_S2_1_QUIESCE_FENCE, allow_mutation=True
                )
            ),
            "db_observer": runner.QuiesceDbObserver(None),
        }

    with pytest.raises(runner.S2_1HostRunnerError) as error:
        runner.run_quiesce_fence_on_host(
            intent, None, None, now=NOW, source_head=HEAD, capability_factory=_factory,
            allow_production=True, production_confirm=intent["self_digest"],
            operator_authorization_verified=True,
        )
    assert "expected exactly QuiesceFenceOps" in str(error.value)


def test_production_lane_refuses_an_executor_that_is_not_the_host_kernel(monkeypatch):
    """RES-4:``QuiesceFenceOps._run`` 只斷言 argv,真 exec 交給 executor ⇒ 它必須是 kernel 本尊。

    注入一個裸執行器就把 ``shell=False`` / sanitized env / timeout / 每次 exec 前的 prctl 執法
    全部丟掉,而 argv 斷言照樣綠 —— 生產 lane 因此把 executor 釘死。
    """

    _force_derived(monkeypatch, PRODUCTION_VIEWS[0])
    intent = _intent("sha256:" + "0" * 64, target_class="production")

    def _factory():
        return {
            "host_probe": runner.QuiesceHostProbe(
                executor=_RecordingExecutor(), proc_root="/proc"
            ),
            "fence_ops": runner.QuiesceFenceOps(executor=_RecordingExecutor()),
            "db_observer": runner.QuiesceDbObserver(None),
        }

    with pytest.raises(runner.S2_1HostRunnerError) as error:
        runner.run_quiesce_fence_on_host(
            intent, None, None, now=NOW, source_head=HEAD, capability_factory=_factory,
            allow_production=True, production_confirm=intent["self_digest"],
            operator_authorization_verified=True,
        )
    message = str(error.value)
    assert "only executes through the HostExecutionKernel" in message
    assert "host_probe executor=" in message and "fence_ops executor=" in message


def test_the_rehearsal_lane_still_accepts_the_injected_simulator():
    """誠實界線:RES-4 的 executor 釘只套在生產 lane;排練面的模擬器仍必須進得來。"""

    probe = runner.QuiesceHostProbe(executor=_RecordingExecutor(), proc_root="/proc")
    fence_ops = runner.QuiesceFenceOps(executor=_RecordingExecutor())
    runner._require_runner_capabilities(probe, fence_ops, runner.QuiesceDbObserver(None))
    with pytest.raises(runner.S2_1HostRunnerError):
        runner._require_kernel_executors(probe, fence_ops)


def test_unobservable_fence_is_reported_as_null_never_as_zero():
    """RUN-3 的核心:``0`` / ``[]`` 只能出現在**真的觀測過**的情形,否則必須是 ``null``。"""

    result = runner._run_result(
        lane="production", target_view={"target_class": kernel.TARGET_CLASS_PRODUCTION},
        receipt={"status": "EXTERNAL_VERIFICATION_PENDING"}, probe=None, fence_ops=None,
        verifier_node="s2_1_ops_postcheck",
    )
    assert result["stop_calls"] is None
    assert result["start_calls"] is None
    assert result["fence_argv"] is None
    assert result["read_argv"] is None
    assert result["fence_observable"] is False


@pytest.mark.parametrize("injected", [
    kernel.TARGET_CLASS_PRODUCTION,
    kernel.TARGET_CLASS_UNKNOWN,     # unknown 與 production 在 rehearsal lane 同等對待
])
def test_rehearsal_refuses_on_an_injected_production_grade_class(injected):
    intent = _intent("sha256:" + "0" * 64)
    probe = runner.QuiesceHostProbe(executor=_RecordingExecutor(), proc_root="/proc")
    with pytest.raises(runner.S2_1HostRunnerError):
        runner.rehearse_quiesce_fence(
            intent, None, None, now=NOW, source_head=HEAD, host_probe=probe,
            fence_ops=runner.QuiesceFenceOps(executor=_RecordingExecutor()),
            db_observer=runner.QuiesceDbObserver(None), clock=lambda: 0.0,
            target_view={"target_class": injected, "reason": "x"},
        )


@pytest.mark.parametrize("derived", PRODUCTION_VIEWS)
def test_a_forged_disposable_view_cannot_loosen_the_rehearsal_refusal(monkeypatch, derived):
    _force_derived(monkeypatch, derived)
    intent = _intent("sha256:" + "0" * 64)
    probe = runner.QuiesceHostProbe(executor=_RecordingExecutor(), proc_root="/proc")
    with pytest.raises(runner.S2_1HostRunnerError):
        runner.rehearse_quiesce_fence(
            intent, None, None, now=NOW, source_head=HEAD, host_probe=probe,
            fence_ops=runner.QuiesceFenceOps(executor=_RecordingExecutor()),
            db_observer=runner.QuiesceDbObserver(None), clock=lambda: 0.0,
            target_view={"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE},
        )


def test_dsn_stat_reads_identity_only_and_never_opens_the_credential(tmp_path):
    dsn = tmp_path / "pg-dsn"
    dsn.write_text("never-read-by-the-probe", encoding="utf-8")
    os.chmod(dsn, 0o600)
    probe = runner.QuiesceHostProbe(
        executor=_RecordingExecutor(), proc_root=str(tmp_path), dsn_path=str(dsn)
    )
    observed = probe.dsn_stat()
    assert observed["dsn_mode"] == "0600"
    assert observed["world_readable"] is False
    assert observed["dsn_owner_uid"] == os.getuid()
    assert "never-read-by-the-probe" not in repr(observed)
    # 憑證檔不可觀測時 typed 拒(絕不猜一個 exposure)。
    missing = runner.QuiesceHostProbe(
        executor=_RecordingExecutor(), proc_root=str(tmp_path),
        dsn_path=str(tmp_path / "absent" / "pg-dsn"),
    )
    with pytest.raises(runner.S2_1HostRunnerError):
        missing.dsn_stat()


def _locus(path) -> str:
    """真實 ``/proc/locks`` 第 6 欄的形:``<major hex>:<minor hex>:<inode dec>``。"""

    info = os.stat(path)
    return f"{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino}"


def test_flock_held_is_read_only_and_parses_proc_locks(tmp_path):
    lock = tmp_path / "consumer.lock"
    lock.write_text("", encoding="utf-8")
    locks = tmp_path / "locks"
    locks.write_text(
        f"1: FLOCK  ADVISORY  WRITE 4242 {_locus(lock)} 0 EOF\n", encoding="utf-8"
    )
    probe = runner.QuiesceHostProbe(
        executor=_RecordingExecutor(), proc_root=str(tmp_path),
        flock_path=str(lock), locks_path=str(locks),
    )
    assert probe.flock_held() is True
    locks.write_text("1: POSIX  ADVISORY  WRITE 1 fd:01:999 0 EOF\n", encoding="utf-8")
    assert probe.flock_held() is False
    # 不可判定時回 None(而不是把 None 當成 False 亂報)。
    unreadable = runner.QuiesceHostProbe(
        executor=_RecordingExecutor(), proc_root=str(tmp_path),
        flock_path=str(lock), locks_path=str(tmp_path / "absent-locks"),
    )
    assert unreadable.flock_held() is None
    assert runner.QuiesceHostProbe(
        executor=_RecordingExecutor(), proc_root=str(tmp_path)
    ).flock_held() is None


def test_flock_held_requires_the_device_to_match_not_just_the_inode(tmp_path):
    """E2 P2 #11 前半:跨檔案系統的 inode 碰撞不得被誤判成 held。"""

    lock = tmp_path / "consumer.lock"
    lock.write_text("", encoding="utf-8")
    info = os.stat(lock)
    locks = tmp_path / "locks"
    # 同 inode、**不同 device**(major+1)⇒ 那不是我們的檔案。
    locks.write_text(
        f"1: FLOCK  ADVISORY  WRITE 4242 {os.major(info.st_dev) + 1:02x}:"
        f"{os.minor(info.st_dev):02x}:{info.st_ino} 0 EOF\n",
        encoding="utf-8",
    )
    probe = runner.QuiesceHostProbe(
        executor=_RecordingExecutor(), proc_root=str(tmp_path),
        flock_path=str(lock), locks_path=str(locks),
    )
    assert probe.flock_held() is False


def test_flock_held_survives_the_waiter_arrow_prefix(tmp_path):
    """E2 P2 #11 後半:``->`` 前綴的 waiter 行會把欄位推移一格,解析必須先正規化。"""

    lock = tmp_path / "consumer.lock"
    lock.write_text("", encoding="utf-8")
    locus = _locus(lock)
    locks = tmp_path / "locks"
    # 第一行是等待者(``->``),第二行才是真正持有者;若不剝 ``->``,第一行會被讀成
    # ``fields[5] == "WRITE"`` 之類的錯欄位。
    locks.write_text(
        f"1: -> FLOCK  ADVISORY  WRITE 9999 {locus} 0 EOF\n"
        f"1: FLOCK  ADVISORY  WRITE 4242 {locus} 0 EOF\n",
        encoding="utf-8",
    )
    probe = runner.QuiesceHostProbe(
        executor=_RecordingExecutor(), proc_root=str(tmp_path),
        flock_path=str(lock), locks_path=str(locks),
    )
    assert probe.flock_held() is True
    # 只有 waiter 而沒有 holder 時,欄位仍必須被正確對齊(而不是解析到別的欄位後誤判)。
    locks.write_text(f"1: -> FLOCK  ADVISORY  WRITE 9999 fd:01:999 0 EOF\n", encoding="utf-8")
    assert probe.flock_held() is False


def test_ops_postcheck_uses_the_s2e1_builder_and_records_its_typed_refusal():
    receipt = q.apply_quiesce_fence(
        _intent("sha256:" + "0" * 64), None, None, now=NOW, source_head=HEAD,
    )
    projection = runner._ops_postcheck_projection(
        receipt, verifier_node="s2_1_ops_postcheck", observed_at=NOW
    )
    assert projection["evidence"] is None
    assert "not representable today" in projection["refusal"]


# --------------------------------------------------------------------------- #
# T1 — real disposable cluster + simulated systemd host
# --------------------------------------------------------------------------- #
# E2 P2 #5:``pytest.importorskip`` 原本在**模組層** ⇒ psycopg2 缺席時連 T0 的 production 拒絕
# 矩陣(恆該跑、且完全不需要 PG 的那 33+ 個)都會整批消失。改成模組層只做「可選 import」,
# 缺席的代價僅落在 T1 的 skipif 上,T0 於是真的恆跑。
try:  # pragma: no cover - 依主機而定
    import psycopg2
except ImportError:  # pragma: no cover - 依主機而定
    psycopg2 = None

disposable = pytest.mark.skipif(
    not (INITDB and PG_CTL and psycopg2 is not None),
    reason="initdb/pg_ctl/psycopg2 are absent; the S2.1 host runner rehearsal cannot run",
)


def _run(cmd, *, logfile, timeout):
    result = subprocess.run(
        cmd, env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=timeout,
    )
    if result.returncode != 0:
        detail = ""
        try:
            detail = Path(logfile).read_text(encoding="utf-8")[-800:]
        except OSError:
            pass
        raise RuntimeError(f"command failed rc={result.returncode}: {cmd[0]}\n{detail}")


@pytest.fixture(scope="module")
def cluster():
    if not (INITDB and PG_CTL and psycopg2 is not None):
        pytest.skip("initdb/pg_ctl/psycopg2 are absent")
    tmp = tempfile.mkdtemp(prefix="aiml_s2e2_s21_")
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    started = False
    try:
        _run([INITDB, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
             logfile=logfile, timeout=90)
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
            handle.write("lc_messages = 'C'\n")
            handle.write("log_statement = 'none'\n")
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   all   trust\n")
        _run([PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
             logfile=logfile, timeout=60)
        started = True
        _bootstrap(sock_dir)
        yield {"socket_dir": sock_dir}
    finally:
        if started or os.path.exists(os.path.join(data_dir, "postmaster.pid")):
            try:
                subprocess.run([PG_CTL, "-D", data_dir, "-m", "immediate", "stop"],
                               env=CLEAN_SUBPROCESS_ENV, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _connect(sock, user="postgres"):
    connection = psycopg2.connect(host=sock, dbname=DB, user=user, connect_timeout=10)
    connection.autocommit = True
    return connection


def _bootstrap(sock):
    connection = _connect(sock)
    try:
        cursor = connection.cursor()
        cursor.execute(f"CREATE SCHEMA {SESSION_SCHEMA}")
        cursor.execute(
            f"CREATE TABLE {SESSION_RELATION} ("
            "event_id uuid PRIMARY KEY, session_id uuid, event_kind text, "
            "recorded_at timestamptz NOT NULL DEFAULT clock_timestamp())"
        )
        cursor.execute(f"CREATE ROLE {q.ALR_CONNECTION_ROLE} LOGIN")
        grant_set = observer.generate_observer_grant_sql({
            "grant_set_selector": "observer_read_only_v1", "observer_role": OBSERVER_ROLE,
            "observed_schema": SESSION_SCHEMA, "observed_relations": [SESSION_TABLE],
            "auth_mapping": "pg_hba_ident_local",
        })
        observer.observer_bootstrap_apply(cursor, grant_set=grant_set)
        cursor.execute(f"CREATE ROLE {ASSUME_ROLE} LOGIN")
        cursor.execute(f'GRANT "{OBSERVER_ROLE}" TO "{ASSUME_ROLE}"')
    finally:
        connection.close()


def _observer_connection(sock):
    connection = psycopg2.connect(host=sock, dbname=DB, user=ASSUME_ROLE, connect_timeout=10)
    connection.autocommit = True
    cursor = connection.cursor()
    cursor.execute(f'SET ROLE "{OBSERVER_ROLE}"')
    cursor.execute("SET default_transaction_read_only = on")
    return connection


class _SimulatedSystemdHost:
    """注入的 systemd 執行器 + 模擬 /proc + 真的 advisory lock;**只**當作 executor 用。

    runner 自己的 ``QuiesceHostProbe`` / ``QuiesceFenceOps`` 包在它外面,故被驗的是 runner 的
    類別(allowlist re-assert / argv 構造 / dsn_stat / flock_held),不是測試內的 fake。
    """

    def __init__(self, root: Path, sock: str, *, main_pid: int = 4242) -> None:
        self.root = root
        self.proc_root = root / "proc"
        self.proc_root.mkdir(parents=True, exist_ok=True)
        self.dsn_path = root / "pg-dsn"
        self.dsn_path.write_text("credential-bytes-never-read", encoding="utf-8")
        os.chmod(self.dsn_path, 0o600)
        self.lock_path = root / "consumer.lock"
        self.lock_path.write_text("", encoding="utf-8")
        self.locks_path = root / "locks"
        self.sock = sock
        self.pid = main_pid
        self.invocation = "inv-1"
        self.n_restarts = 0
        self.state = "running"
        self.max_batch = "32"
        self.start_should_fail = False
        self.stop_causes_restart = False
        self.raise_during_window = False
        self._window_read_should_raise = False
        self.session_id = None
        self._admin = _connect(sock)
        self._owner = _connect(sock, user=q.ALR_CONNECTION_ROLE)
        self._admin.cursor().execute(f"TRUNCATE {SESSION_RELATION}")
        (self.proc_root / "sys" / "kernel" / "random").mkdir(parents=True, exist_ok=True)
        (self.proc_root / "sys" / "kernel" / "random" / "boot_id").write_text(
            "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee\n", encoding="utf-8"
        )
        self._materialize(self.pid)
        self._acquire_lock()
        self._write_locks(held=True)
        self._record_session("SESSION_STARTED", new=True)

    # -- the injected executor face ---------------------------------------- #
    def run(self, argv):
        argv = list(argv)
        if argv[:2] == [qi.SYSTEMD, "stop"]:
            return self._stop()
        if argv[:2] == [qi.SYSTEMD, "start"]:
            return self._start()
        if self._window_read_should_raise:
            raise RuntimeError("injected mid-window host read failure")
        if argv[:3] == [qi.SYSTEMD, "show", qi.UNIT_NAME]:
            return self._show_dump()
        if argv[:2] == [qi.SYSTEMD, "list-units"]:
            return ""
        raise AssertionError(f"unexpected argv reached the simulated host: {argv}")

    # -- lifecycle --------------------------------------------------------- #
    def _stop(self) -> str:
        if self.raise_during_window:
            self._window_read_should_raise = True
        if self.stop_causes_restart:
            self.n_restarts += 1
            self.invocation = "inv-restarted"
            self.state = "restarted"
            return ""
        self._release_lock()
        self._write_locks(held=False)
        shutil.rmtree(self.proc_root / str(self.pid), ignore_errors=True)
        self._record_session("SESSION_STOPPED")
        self.state = "fenced"
        return ""

    def _start(self) -> str:
        if self.start_should_fail:
            raise RuntimeError("injected system-level systemctl start failure")
        self.pid += 1313
        self.invocation = "inv-2"
        self.state = "running"
        self._materialize(self.pid)
        self._acquire_lock()
        self._write_locks(held=True)
        self._record_session("SESSION_STARTED", new=True)
        return ""

    # -- internals --------------------------------------------------------- #
    def _show_dump(self) -> str:
        if self.state == "fenced":
            props = {"LoadState": "loaded", "ActiveState": "inactive", "SubState": "dead",
                     "MainPID": "0", "InvocationID": "", "NRestarts": str(self.n_restarts),
                     "ControlGroup": ""}
        else:
            props = {"LoadState": "loaded", "ActiveState": "active", "SubState": "running",
                     "MainPID": str(self.pid), "InvocationID": self.invocation,
                     "NRestarts": str(self.n_restarts), "ControlGroup": CG}
        props.update({
            "FragmentPath": FRAG, "DropInPaths": "", "NeedDaemonReload": "no",
            "Environment": " ".join(f"{k}={v}" for k, v in ENVIRON.items()),
            "Restart": "on-failure", "RestartUSec": "5s", "TimeoutStopUSec": "30s",
            "WatchdogUSec": "0", "NoNewPrivileges": "yes", "ProtectSystem": "full",
            "PrivateTmp": "yes", "RestrictAddressFamilies": "AF_UNIX AF_INET",
        })
        return "\n".join(f"{key}={props[key]}" for key in qi.QUIESCE_SHOW_PROPERTIES)

    def _materialize(self, pid: int) -> None:
        directory = self.proc_root / str(pid)
        directory.mkdir(parents=True, exist_ok=True)
        rest = ["S"] + ["0"] * 30
        rest[19] = "998877"
        (directory / "stat").write_text(f"{pid} (python3) " + " ".join(rest) + "\n", encoding="utf-8")
        cmdline = [
            INTERP, "-I", "-m", "ml_training.alr_event_consumer",
            "--dsn-file", str(self.dsn_path), "--lock-file", str(self.lock_path),
            "--max-batch", self.max_batch,
        ]
        (directory / "cmdline").write_bytes(b"\x00".join(a.encode() for a in cmdline) + b"\x00")
        (directory / "environ").write_bytes(
            b"\x00".join(f"{k}={v}".encode() for k, v in ENVIRON.items()) + b"\x00"
        )
        (directory / "cgroup").write_text(f"0::{CG}\n", encoding="utf-8")

    def add_second_candidate(self, pid: int) -> None:
        self._materialize(pid)

    def _write_locks(self, *, held: bool) -> None:
        # 真實 ``/proc/locks`` 的 locus 欄:``<major hex>:<minor hex>:<inode dec>``
        # (device 也必須對得上,見 QuiesceHostProbe.flock_held)。
        info = os.stat(self.lock_path)
        locus = f"{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}:{info.st_ino}"
        self.locks_path.write_text(
            f"1: FLOCK  ADVISORY  WRITE {self.pid} {locus} 0 EOF\n" if held else "",
            encoding="utf-8",
        )

    def _acquire_lock(self) -> None:
        cursor = self._owner.cursor()
        cursor.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (q.ADVISORY_LOCK_NAME,))
        assert cursor.fetchone()[0] is True

    def _release_lock(self) -> None:
        self._owner.cursor().execute(
            "SELECT pg_advisory_unlock(hashtext(%s))", (q.ADVISORY_LOCK_NAME,)
        )

    def free_lock_and_gone(self) -> None:
        self._release_lock()
        self._write_locks(held=False)
        shutil.rmtree(self.proc_root / str(self.pid), ignore_errors=True)
        self._record_session("SESSION_STOPPED")
        self.state = "fenced"

    def _record_session(self, kind: str, *, new: bool = False) -> None:
        if new:
            self.session_id = str(uuid.uuid4())
        self._admin.cursor().execute(
            f"INSERT INTO {SESSION_RELATION}(event_id, session_id, event_kind) "
            "VALUES (%s::uuid, %s::uuid, %s)",
            (str(uuid.uuid4()), self.session_id, kind),
        )

    def close(self) -> None:
        for connection in (self._owner, self._admin):
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - best effort
                pass


def _capabilities(host: _SimulatedSystemdHost, connection):
    probe = runner.QuiesceHostProbe(
        executor=host, proc_root=str(host.proc_root), dsn_path=str(host.dsn_path),
        flock_path=str(host.lock_path), locks_path=str(host.locks_path),
    )
    return probe, runner.QuiesceFenceOps(executor=host), runner.QuiesceDbObserver(connection)


def _stepping_clock(step: float = 5.0):
    state = {"t": -step}

    def _clock():
        state["t"] += step
        return state["t"]

    return _clock


def _install_operator_profile(tmp_path, monkeypatch):
    private_key = tmp_path / "operator"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True)
    public_key = " ".join(private_key.with_suffix(".pub").read_text(encoding="ascii").split()[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(q, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(q, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


_SIGN_SEQ = [0]


def _sign(private_key, intent, source_head):
    authorization = q.build_operator_authorization(intent=intent, source_head=source_head)
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"s2e2-quiesce-permit-{_SIGN_SEQ[0]}.json"
    message.write_bytes(q.canonical_bytes(authorization))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n",
         q.OPERATOR_SIGNATURE_NAMESPACE, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return authorization, message.with_suffix(".json.sig").read_bytes()


@pytest.fixture
def host(cluster, tmp_path):
    simulated = _SimulatedSystemdHost(tmp_path / "host", cluster["socket_dir"])
    try:
        yield simulated
    finally:
        simulated.close()


def _expected_fingerprint(host, probe, connection):
    probe_intent = _intent("sha256:" + "0" * 64, flock_path=str(host.lock_path))
    inventory = qi.build_owner_inventory(probe, connection.cursor(), intent=probe_intent)
    return inventory["owner_fingerprint"]


def _drive(host, connection, intent, authorization, signature):
    probe, fence_ops, db_observer = _capabilities(host, connection)
    return runner.rehearse_quiesce_fence(
        intent, authorization, signature, now=NOW, source_head=HEAD,
        host_probe=probe, fence_ops=fence_ops, db_observer=db_observer,
        clock=_stepping_clock(), verifier_capture_digest=CAP,
    )


@disposable
def test_rehearsal_happy_path_through_the_runner_classes(host, cluster, tmp_path, monkeypatch):
    connection = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    probe, _fence, _db = _capabilities(host, connection)
    expected = _expected_fingerprint(host, probe, connection)
    intent = _intent(expected, flock_path=str(host.lock_path))
    authorization, signature = _sign(private_key, intent, HEAD)

    result = _drive(host, connection, intent, authorization, signature)
    receipt = result["receipt"]
    assert result["status"] == "QUIESCED_STATIC_GUARDS_HELD"
    assert result["stop_calls"] == 1 and result["start_calls"] == 1
    assert result["fence_argv"] == [
        [qi.SYSTEMD, "stop", qi.UNIT_NAME], [qi.SYSTEMD, "start", qi.UNIT_NAME],
    ]
    # 每一條讀取 argv 都在唯讀 allowlist 內(runner 的獨立 re-assert 全程生效)。
    for argv in result["read_argv"]:
        assert tuple(argv) in kernel.SESSION_ARGV_ALLOWLISTS[kernel.SESSION_S2_1_QUIESCE_READ]
    # 真 advisory lock 的 HELD → FREE → RE-HELD(以 S2.0 唯讀 observer 身分讀)。
    assert receipt["pre_fence_observation"]["db_quiesce"]["advisory_lock_held"] is True
    assert all(s["db_quiesce"]["advisory_lock_held"] is False for s in receipt["window_samples"])
    assert receipt["post_unfence_observation"]["db_quiesce"]["advisory_lock_held"] is True
    assert result["rollback_status"] == "RESTORED"
    assert q.validate_quiesce_fence_result(receipt, now=LATER) == []
    assert validator.validate_aiml_artifact(receipt, now=LATER) == []
    # 誠實界線
    assert result["production_fence_performed"] is False
    assert result["live_alr_owner_fenced"] is False
    assert result["closure_pass_blocked"] is True
    assert result["ops_postcheck_evidence"] is None
    connection.close()

    # 三方 closure binding(source-only):receipt + ops_postcheck 的 verifier command_capture_v2。
    capture = {"schema_version": "command_capture_v2", "node_id": "s2_1_ops_postcheck",
               "record_digest": CAP}
    evidence_by_id = {
        "ev-receipt": None,
        "ev-cap": {"id": "ev-cap", "scope": "runtime", "source": "ops_postcheck",
                   "kind": "command_capture_v2", "digest": CAP, "artifact": capture},
    }
    route = {"nodes": [{"id": q.ADAPTER_ID, "kind": "effect_adapter", "mandatory": True}]}
    fragments = {"ops_preflight": {"evidence_refs": []},
                 "ops_postcheck": {"evidence_refs": ["ev-cap"]}}
    packet = {
        "authority_refs": [{"class": "claim_evidence",
                            "source": f"{q.INTENT_SCHEMA_VERSION}:{intent['intent_id']}",
                            "digest": intent["self_digest"]}],
        "acceptance": [{"status": "PASS", "evidence_refs": ["ev-receipt", "ev-cap"]}],
    }
    assert q.validate_quiesce_fence_binding(
        packet, route, fragments, evidence_by_id, {"ev-receipt": receipt}
    ) == []
    forged = copy.deepcopy(evidence_by_id)
    forged["ev-cap"]["digest"] = "sha256:" + "1" * 64
    assert q.validate_quiesce_fence_binding(
        packet, route, fragments, forged, {"ev-receipt": receipt}
    )


@disposable
def test_rehearsal_stale_owner_never_fences(host, cluster, tmp_path, monkeypatch):
    connection = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    probe, _f, _d = _capabilities(host, connection)
    expected = _expected_fingerprint(host, probe, connection)
    intent = _intent(expected, flock_path=str(host.lock_path))
    authorization, signature = _sign(private_key, intent, HEAD)
    host.free_lock_and_gone()

    result = _drive(host, connection, intent, authorization, signature)
    assert result["status"] == "STALE_OWNER_FAIL_CLOSED"
    assert result["stop_calls"] == 0 and result["fence_argv"] == []
    assert q.validate_quiesce_fence_result(result["receipt"], now=LATER) == []
    connection.close()


@disposable
def test_rehearsal_double_owner_is_refused(host, cluster, tmp_path, monkeypatch):
    connection = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    probe, _f, _d = _capabilities(host, connection)
    expected = _expected_fingerprint(host, probe, connection)
    intent = _intent(expected, flock_path=str(host.lock_path))
    authorization, signature = _sign(private_key, intent, HEAD)
    host.add_second_candidate(host.pid + 7)

    result = _drive(host, connection, intent, authorization, signature)
    assert result["status"] == "AMBIGUOUS_OWNER_REFUSED"
    assert result["stop_calls"] == 0
    connection.close()


@disposable
def test_rehearsal_unfence_failure_is_not_restored(host, cluster, tmp_path, monkeypatch):
    connection = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    probe, _f, _d = _capabilities(host, connection)
    expected = _expected_fingerprint(host, probe, connection)
    intent = _intent(expected, flock_path=str(host.lock_path))
    authorization, signature = _sign(private_key, intent, HEAD)
    host.start_should_fail = True

    result = _drive(host, connection, intent, authorization, signature)
    assert result["status"] == "NOT_RESTORED"
    assert result["rollback_status"] == "NOT_RESTORED"
    assert result["stop_calls"] == 1 and result["start_calls"] == 1   # 仍嘗試 un-fence
    connection.close()


@disposable
def test_rehearsal_observation_window_violated(host, cluster, tmp_path, monkeypatch):
    connection = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    probe, _f, _d = _capabilities(host, connection)
    expected = _expected_fingerprint(host, probe, connection)
    intent = _intent(expected, flock_path=str(host.lock_path))
    authorization, signature = _sign(private_key, intent, HEAD)
    host.stop_causes_restart = True

    result = _drive(host, connection, intent, authorization, signature)
    assert result["status"] == "OBSERVATION_WINDOW_VIOLATED"
    assert any(s["verdict"] == "RESTART_DETECTED" for s in result["receipt"]["window_samples"])
    assert result["start_calls"] == 1
    connection.close()


@disposable
def test_rehearsal_window_raise_after_fence_still_unfences(host, cluster, tmp_path, monkeypatch):
    """強制窗內拋錯:證明 ``finally`` 的 un-fence 真的跑了(runner 的 fence_ops 記到 start)。"""

    connection = _observer_connection(cluster["socket_dir"])
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    probe, _f, _d = _capabilities(host, connection)
    expected = _expected_fingerprint(host, probe, connection)
    intent = _intent(expected, flock_path=str(host.lock_path))
    authorization, signature = _sign(private_key, intent, HEAD)
    host.raise_during_window = True

    result = _drive(host, connection, intent, authorization, signature)
    assert result["status"] == "FAILED"
    assert "un-fence attempted" in result["receipt"]["failure_reason"]
    assert result["stop_calls"] == 1 and result["start_calls"] == 1
    assert result["fence_argv"][-1] == [qi.SYSTEMD, "start", qi.UNIT_NAME]
    connection.close()


@disposable
def test_rehearsal_without_an_operator_signature_never_fences(host, cluster):
    connection = _observer_connection(cluster["socket_dir"])
    probe, _f, _d = _capabilities(host, connection)
    expected = _expected_fingerprint(host, probe, connection)
    intent = _intent(expected, flock_path=str(host.lock_path))

    result = _drive(host, connection, intent, None, None)
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["stop_calls"] == 0 and result["fence_argv"] == []
    connection.close()

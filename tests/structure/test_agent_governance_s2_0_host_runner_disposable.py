"""S2E.2a:S2.0 受信主機 runner 的**拋棄式 rehearsal**(T1)+ production 拒絕矩陣(T0)。

T0(恆跑,含 Mac):production/unknown 全路徑 typed 拒且 **driver 未被構造**(以
``ObserverBootstrapHostDriver.constructions`` 計數器斷言);``--allow-production`` 單獨不足;
rehearsal 恆拒在 production target class 上執行;rehearsal driver 永不宣稱 PLATFORM_ATTESTED。

T1(需 ``initdb``/``pg_ctl``/``psycopg2``,缺任一則**只有 T1 那幾支**誠實 SKIP、T0 恆跑):對一個真的
``initdb`` 拋棄式叢集,以 runner 的 ``ObserverBootstrapHostDriver`` 走 **S2.0 adapter 的 production
gate**(§6 step 2→9),證明三段:

  apply(真 CREATE ROLE + GRANT)→ 獨立 verifier 的 postcheck **FAIL** → 補償
  → catalog digest **逐位元組**回前態、observer 角色真的消失。

另證:evidence_class 第一道 filter(LOCAL_REPRODUCIBLE 一律補償後 PENDING)、
``signed_apply_attestation`` 永遠 raise(絕不偽造 platform 背書)、補償失敗 → RECOVERY_REQUIRED、
以及 receipt 的 ``production_apply_performed`` 恆 false。

**誠實界線**:所有 rehearsal 頂點都是 ``EXTERNAL_VERIFICATION_PENDING`` / ``RECOVERY_REQUIRED``
——那是**預期**行為。rehearsal 綠不是 closure PASS,也不是 EFFECT 進展;九 authority 恆 false,
runtime 恆 inactive,生產 PG 從未被接觸。
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[2]
HELPERS = ROOT / "helper_scripts/maintenance_scripts"
ML_ROOT = ROOT / "program_code/ml_training"
for candidate in (HELPERS, ML_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import agent_governance_pg_observer_bootstrap as obs  # noqa: E402
import agent_governance_pg_observer_bootstrap_attestation as obs_att  # noqa: E402
import agent_governance_s2_0_host_runner as runner  # noqa: E402
import agent_governance_s2_host_kernel as kernel  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")

DB = "postgres"
SCHEMA = "learning"
TABLE = "alr_consumer_events"
OBSERVER = "aiml_s2e2_observer"
WRITER = "aiml_s2e2_writer"
ASSUME = "aiml_s2e2_assume"
ASSUME_PW = "aiml-s2e2-assume-cred-v0"
WRONG_PW = "aiml-s2e2-assume-cred-WRONG"

HEAD = "0123456789abcdef0123456789abcdef01234567"
CREATED = "2026-07-28T12:00:00+00:00"
NOW = "2026-07-28T12:01:00+00:00"
CAP = "sha256:" + "e" * 64

CLEAN_SUBPROCESS_ENV = {"PATH": os.environ.get("PATH", ""), "LANG": "C", "LC_ALL": "C"}


# --------------------------------------------------------------------------- #
# T0 — production refusal matrix (always runs, including on Mac)
# --------------------------------------------------------------------------- #
def _intent(target_class="production", sock="/var/run/postgresql"):
    return obs.build_pg_observer_bootstrap_intent(
        target_class=target_class, target_host="trade-core", database=DB,
        observer_role=OBSERVER, observed_schema=SCHEMA, observed_relations=[TABLE],
        socket_dir=sock, auth_mapping="pg_hba_ident_local",
        applier_node_id="s2_0_apply_actor", postcheck_node_id="s2_0_ops_postcheck",
        created_at=CREATED, ttl_seconds=900, source_head=HEAD,
    )


def _exploding_factory():
    def _factory():  # pragma: no cover - 必須永不被呼叫
        raise AssertionError("the driver factory must never be reached when admission refuses")

    return _factory


def _never_connect():  # pragma: no cover - 必須永不被呼叫
    raise AssertionError("no PG connection may be opened on a refused / L2-gated path")


PRODUCTION_VIEWS = [
    {"target_class": kernel.TARGET_CLASS_PRODUCTION, "reason": "x", "facts": {}},
    {"target_class": kernel.TARGET_CLASS_UNKNOWN, "reason": "x", "facts": {}},
]


def _force_derived(monkeypatch, view):
    """target class 只能被**主機事實**決定 ⇒ 測試也只能從 ``derive_host_target_class`` 這一點造假。"""

    monkeypatch.setattr(kernel, "derive_host_target_class", lambda: view)


# --------------------------------------------------------------------------- #
# RUN-1:production lane 完全不收 caller view(一個 caller 字串繞不過 L1)
# --------------------------------------------------------------------------- #
def test_production_lane_takes_no_caller_target_view():
    import inspect

    for entry in (runner.run_observer_bootstrap_on_host,):
        assert "target_view" not in inspect.signature(entry).parameters


def test_a_forged_target_view_cannot_reach_the_production_lane(monkeypatch):
    # 偽造一份 disposable_candidate view 遞進 production lane:今日連參數都不存在 ⇒ TypeError,
    # 且 driver_factory 從未被呼叫(主機零接觸)。
    _force_derived(monkeypatch, PRODUCTION_VIEWS[0])
    intent = _intent()
    before = runner.ObserverBootstrapHostDriver.constructions
    with pytest.raises(TypeError):
        runner.run_observer_bootstrap_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            driver_factory=_exploding_factory(),
            target_view={"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE},
            allow_production=True, production_confirm=intent["self_digest"],
            operator_authorization_verified=True,
        )
    assert runner.ObserverBootstrapHostDriver.constructions == before


@pytest.mark.parametrize("view", PRODUCTION_VIEWS)
@pytest.mark.parametrize("kwargs", [
    {},
    {"allow_production": True},
    {"allow_production": True, "operator_authorization_verified": True},
    {"allow_production": True, "production_confirm": "sha256:" + "9" * 64},
    {"operator_authorization_verified": True, "production_confirm": "match"},
])
def test_production_refusal_never_constructs_a_driver(monkeypatch, view, kwargs):
    _force_derived(monkeypatch, view)
    intent = _intent()
    if kwargs.get("production_confirm") == "match":
        kwargs["production_confirm"] = intent["self_digest"]
    before = runner.ObserverBootstrapHostDriver.constructions
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.run_observer_bootstrap_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            driver_factory=_exploding_factory(), **kwargs,
        )
    assert runner.ObserverBootstrapHostDriver.constructions == before


@pytest.mark.parametrize("view", PRODUCTION_VIEWS)
def test_all_three_conditions_reach_the_driver_factory(monkeypatch, view):
    _force_derived(monkeypatch, view)
    intent = _intent()
    reached = {"count": 0}

    def _factory():
        reached["count"] += 1
        # runner 自有 driver;連線 callable 會炸 —— adapter 因缺 SSHSIG 根本不會呼叫它。
        return runner.ObserverBootstrapHostDriver(
            applier_connect=_never_connect, verifier_connect=_never_connect,
        )

    # driver 被構造了,但 adapter 的 L2 閘(缺 operator SSHSIG)仍讓它停在 PENDING —— L1 只決定
    # 「今天要不要碰這台主機」,證據完整性仍由 L2 把關。
    result = runner.run_observer_bootstrap_on_host(
        intent, None, None, now=NOW, source_head=HEAD, driver_factory=_factory,
        allow_production=True, production_confirm=intent["self_digest"],
        operator_authorization_verified=True,
    )
    assert reached["count"] == 1
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert result["production_apply_performed"] is False
    assert result["closure_pass_blocked"] is True
    # 落盤的 target_class_view 是**導出值**,不是任何注入值。
    assert result["target_class_view"] is view
    # driver 是 runner 自有類別 ⇒ 呼叫序真的可觀測(而不是一個不可信的空序列)。
    assert result["driver_calls_observable"] is True
    assert result["driver_calls"] == []


# --------------------------------------------------------------------------- #
# RUN-3:production lane 拒絕不可觀測的 capability 類別
# --------------------------------------------------------------------------- #
def test_production_lane_refuses_a_foreign_capability_object(monkeypatch):
    _force_derived(monkeypatch, PRODUCTION_VIEWS[0])
    intent = _intent()

    class _ForeignDriver:
        """一個「看起來像」driver 的注入物件:沒有 ``calls``,呼叫序永遠報不出來。"""

        evidence_class = runner.LOCAL_REPRODUCIBLE_EVIDENCE_CLASS

        def observer_role_present(self, *, role):  # pragma: no cover - 必須永不被呼叫
            raise AssertionError("a foreign capability must be refused before any call")

    with pytest.raises(runner.S2_0HostRunnerError) as error:
        runner.run_observer_bootstrap_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            driver_factory=_ForeignDriver, allow_production=True,
            production_confirm=intent["self_digest"], operator_authorization_verified=True,
        )
    assert "unobservable" in str(error.value)


def test_non_target_host_is_refused_outright(monkeypatch):
    _force_derived(monkeypatch, {"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"})
    intent = _intent()
    before = runner.ObserverBootstrapHostDriver.constructions
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.run_observer_bootstrap_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            driver_factory=_exploding_factory(),
            allow_production=True, production_confirm=intent["self_digest"],
            operator_authorization_verified=True,
        )
    assert runner.ObserverBootstrapHostDriver.constructions == before


def test_this_machine_refuses_the_production_lane_with_no_forcing_at_all():
    intent = _intent()
    if sys.platform == "linux":  # pragma: no cover - 開發機為 Mac
        pytest.skip("only asserts the non-target refusal on a non-target host")
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.run_observer_bootstrap_on_host(
            intent, None, None, now=NOW, source_head=HEAD,
            driver_factory=_exploding_factory(), allow_production=True,
            production_confirm=intent["self_digest"], operator_authorization_verified=True,
        )


@pytest.mark.parametrize("injected", [
    kernel.TARGET_CLASS_PRODUCTION,
    kernel.TARGET_CLASS_UNKNOWN,     # unknown 與 production 在 rehearsal lane 同等對待
])
def test_rehearsal_refuses_on_an_injected_production_grade_class(injected):
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=_never_connect, verifier_connect=_never_connect,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.rehearse_observer_bootstrap(
            _intent(), None, None, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=lambda: "sha256:" + "0" * 64, role_probe=lambda: False,
            target_view={"target_class": injected, "reason": "x"},
        )


@pytest.mark.parametrize("derived", PRODUCTION_VIEWS)
def test_a_forged_disposable_view_cannot_loosen_the_rehearsal_refusal(monkeypatch, derived):
    # 注入**只能加嚴**:即使遞一份偽造的 disposable_candidate view,derived 仍讓排練被拒。
    _force_derived(monkeypatch, derived)
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=_never_connect, verifier_connect=_never_connect,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.rehearse_observer_bootstrap(
            _intent(), None, None, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=lambda: "sha256:" + "0" * 64, role_probe=lambda: False,
            target_view={"target_class": kernel.TARGET_CLASS_DISPOSABLE_CANDIDATE},
        )


def test_rehearsal_driver_may_never_claim_platform_attested():
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=_never_connect, verifier_connect=_never_connect,
        evidence_class=obs.PRODUCTION_APPLIED_EVIDENCE_CLASS,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        runner.rehearse_observer_bootstrap(
            _intent(), None, None, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=lambda: "sha256:" + "0" * 64, role_probe=lambda: False,
            target_view={"target_class": kernel.TARGET_CLASS_NON_TARGET, "reason": "mac"},
        )


# --------------------------------------------------------------------------- #
# RUN-2:零 role membership DDL、識別碼一律過 _safe_ident
# --------------------------------------------------------------------------- #
# E2 RES-3:原掃描器只比對 ``.execute``、且只看直接的 attribute call ⇒ 兩條逃逸形全綠:
#   ``cur.executemany("GRANT %s TO %s", rows)``   (方法名不同)
#   ``run = cur.execute; run(f'GRANT ...')``      (先綁成別名再呼叫)
# 前者以方法名集合收口;後者以「任何把 execute 家族綁成名字的動作即記一筆違規證據」收口 —— 別名
# 一旦存在,這支掃描器就再也證不出「只發過一條 SET」,故它必須紅而不是靜默漏掉。
_EXECUTE_METHOD_NAMES = frozenset({"execute", "executemany", "executescript"})


def _source_of(module) -> str:
    return Path(module.__file__).read_text(encoding="utf-8")


def _executed_statement_literals(module) -> list[str]:
    """AST 掃出 runner 模組**實際送進 cursor.execute()/executemany() 的字面 SQL**(不看註解)。"""

    tree = ast.parse(_source_of(module))
    literals: list[str] = []
    for node in ast.walk(tree):
        # ①別名綁定:``run = cur.execute`` / ``run := cur.execute`` 一律當違規證據。
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
            bound = node.value
            if (
                isinstance(bound, ast.Attribute) and bound.attr in _EXECUTE_METHOD_NAMES
            ):  # pragma: no cover - 現況零命中;命中即紅
                literals.append(f"<execute alias bound at line {node.lineno}>")
            continue
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in _EXECUTE_METHOD_NAMES):
            continue
        if not node.args:  # pragma: no cover - 無參數的 execute 也不該存在
            literals.append(f"<{func.attr}() with no statement at line {node.lineno}>")
            continue
        statement = node.args[0]
        if isinstance(statement, ast.Constant) and isinstance(statement.value, str):
            literals.append(statement.value)
        elif isinstance(statement, ast.JoinedStr):
            literals.append("".join(
                part.value for part in statement.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            ))
        else:  # pragma: no cover - 非字面 SQL 一律視為違規證據
            literals.append(f"<non-literal statement at line {node.lineno}>")
    return literals


def test_the_runner_never_issues_role_membership_ddl():
    """RUN-2(b):registry invariant 的 ``no role membership`` 對本 implementation path 逐字成立。"""

    statements = _executed_statement_literals(runner)
    # runner 只發一條語句:session 局部、非 DDL、不持久的 SET ROLE。
    assert [item.split()[0] for item in statements] == ["SET"], statements
    for statement in statements:
        upper = statement.upper()
        assert "GRANT" not in upper and "REVOKE" not in upper, statement
    # 撤權路徑不存在 ⇒ 不可能有「撤權失敗被 except: pass 吞掉」這回事(fail loud)。
    source = _source_of(runner)
    assert "except Exception" not in source
    assert "pass\n" not in source


# RES-3 的反例:掃描器抓不到的逃逸形 = 上面那支測試在空轉。兩條 E2 指名的形逐一釘死。
SQL_SCANNER_ESCAPES = {
    "executemany_grant": 'def f(cur):\n    cur.executemany("GRANT %s TO %s", [])\n',
    "aliased_execute": (
        "def f(cur):\n    run = cur.execute\n    run(f'GRANT \"a\" TO \"b\"')\n"
    ),
    "walrus_aliased_execute": (
        "def f(cur):\n    (run := cur.execute)\n    run('GRANT a TO b')\n"
    ),
}


@pytest.mark.parametrize("escape", sorted(SQL_SCANNER_ESCAPES))
def test_the_sql_scanner_catches_the_known_escapes(tmp_path, escape):
    sample = tmp_path / f"{escape}.py"
    sample.write_text(SQL_SCANNER_ESCAPES[escape], encoding="utf-8")
    statements = _executed_statement_literals(SimpleNamespace(__file__=str(sample)))
    assert statements, escape
    # 逐字重跑上面那支測試的判準:它必須**紅**,不能靜默漏掉。
    assert [item.split()[0] for item in statements] != ["SET"], statements


def test_the_driver_holds_no_admin_write_connection_for_the_proof(monkeypatch):
    """verifier 連線只被用來做**唯讀** catalog 投影 —— 它從不執行任何語句字面。"""

    executed: list[str] = []

    class _RecordingCursor:
        def execute(self, statement, parameters=None):
            executed.append(str(statement))

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class _Connection:
        def cursor(self):
            return _RecordingCursor()

        def close(self):
            return None

    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=_never_connect, verifier_connect=_Connection,
        observer_session_connect=_Connection, credential_escalation_connect=_never_connect,
        set_role_target=WRITER,
    )
    with pytest.raises(obs.PgObserverReadOnlyError):
        # 錄音 cursor 不會拒絕 DELETE ⇒ adapter 的拒絕證明 fail-closed 地炸掉(絕不偽造 42501)。
        driver.independent_read_only_proof(grant_set={
            "role": OBSERVER, "schema": SCHEMA, "relations": [TABLE],
        })
    assert [item.split()[0] for item in executed][:1] == ["SET"]
    for statement in executed:
        assert "GRANT" not in statement.upper() and "REVOKE" not in statement.upper()


def test_the_driver_constructor_no_longer_takes_a_session_role():
    import inspect

    parameters = inspect.signature(runner.ObserverBootstrapHostDriver.__init__).parameters
    assert "observer_session_role" not in parameters


@pytest.mark.parametrize("hostile_role", [
    'aiml_s2e2_assume", "e2_probe_victim',      # E2 在真 PG 16.14 上逃出裸雙引號的 payload
    "postgres; DROP ROLE x",
    "Observer",                                  # 大寫不在 ^[a-z_][a-z0-9_]*$ 白名單內
])
def test_a_hostile_role_identifier_is_refused_by_the_safe_ident_allowlist(hostile_role):
    session = {"opened": 0}

    def _session_connect():  # pragma: no cover - 必須永不被呼叫
        session["opened"] += 1
        raise AssertionError("no connection may be opened for an unsafe identifier")

    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=_never_connect, verifier_connect=_never_connect,
        observer_session_connect=_session_connect,
        credential_escalation_connect=_never_connect, set_role_target="aiml_writer",
    )
    with pytest.raises(obs.PgObserverBootstrapError):
        driver.independent_read_only_proof(grant_set={
            "role": hostile_role, "schema": SCHEMA, "relations": [TABLE],
        })
    assert session["opened"] == 0


def test_signed_apply_attestation_always_raises():
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=lambda: None, verifier_connect=lambda: None,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        driver.signed_apply_attestation(
            intent={}, applied_grant_set_digest="sha256:" + "0" * 64,
            reobserved_digest="sha256:" + "0" * 64,
        )


def test_independent_proof_refuses_to_fabricate_without_the_capability():
    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=lambda: None, verifier_connect=lambda: None,
    )
    with pytest.raises(runner.S2_0HostRunnerError):
        driver.independent_read_only_proof(grant_set={
            "role": OBSERVER, "schema": SCHEMA, "relations": [TABLE],
        })


def test_ops_postcheck_uses_the_s2e1_builder_and_records_its_typed_refusal():
    # §H R4:runner 不得產出自己的 receipt schema。S2E.1 的建構子對 S2.0 typed 拒絕,
    # runner 忠實記錄該理由而非另造一份。
    receipt = obs.apply_observer_bootstrap(
        _intent(), None, None, now=NOW, source_head=HEAD,
    )
    projection = runner._ops_postcheck_projection(
        receipt, verifier_node="s2_0_ops_postcheck", observed_at=NOW
    )
    assert projection["evidence"] is None
    assert "not representable today" in projection["refusal"]


# --------------------------------------------------------------------------- #
# T1 — real disposable cluster rehearsal
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
    reason="initdb/pg_ctl/psycopg2 are absent; the S2.0 host runner rehearsal cannot run",
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
    tmp = tempfile.mkdtemp(prefix="aiml_s2e2_s20_")
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
            handle.write("password_encryption = 'scram-sha-256'\n")
            handle.write("lc_messages = 'C'\n")
            handle.write("log_statement = 'none'\n")
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   postgres   trust\n")
            handle.write("local   all   all        scram-sha-256\n")
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


def _admin(sock):
    connection = psycopg2.connect(host=sock, dbname=DB, user="postgres", connect_timeout=10)
    connection.autocommit = True
    return connection


def _bootstrap(sock):
    connection = _admin(sock)
    try:
        cursor = connection.cursor()
        cursor.execute(f"CREATE SCHEMA {SCHEMA}")
        cursor.execute(f"CREATE TABLE {SCHEMA}.{TABLE}(event_id integer PRIMARY KEY, note text)")
        cursor.execute(f"INSERT INTO {SCHEMA}.{TABLE} VALUES (1, 'seed')")
        cursor.execute(f"CREATE ROLE {WRITER} NOLOGIN")
        cursor.execute(f"CREATE ROLE {ASSUME} LOGIN NOSUPERUSER PASSWORD %s", (ASSUME_PW,))
        cursor.execute(f"GRANT USAGE ON SCHEMA {SCHEMA} TO {ASSUME}")
    finally:
        connection.close()


def _install_operator_profile(tmp_path, monkeypatch):
    private_key = tmp_path / "operator"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)], check=True)
    public_key = " ".join(private_key.with_suffix(".pub").read_text(encoding="ascii").split()[:2])
    fingerprint = subprocess.run(
        ["ssh-keygen", "-lf", str(private_key.with_suffix(".pub")), "-E", "sha256"],
        check=True, capture_output=True, text=True,
    ).stdout.split()[1]
    monkeypatch.setattr(obs_att, "OPERATOR_PUBLIC_KEY", public_key)
    monkeypatch.setattr(obs_att, "OPERATOR_FINGERPRINT", fingerprint)
    return private_key


_SIGN_SEQ = [0]


def _sign(private_key, intent, source_head):
    authorization = obs.build_operator_authorization(intent=intent, source_head=source_head)
    _SIGN_SEQ[0] += 1
    message = private_key.parent / f"s2e2-observer-permit-{_SIGN_SEQ[0]}.json"
    message.write_bytes(obs.canonical_bytes(authorization))
    subprocess.run(
        ["ssh-keygen", "-Y", "sign", "-f", str(private_key), "-n",
         obs.OPERATOR_SIGNATURE_NAMESPACE, str(message)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return authorization, message.with_suffix(".json.sig").read_bytes()


def _catalog_probe(sock):
    def _probe():
        connection = _admin(sock)
        try:
            return obs.observer_role_acl_state_digest(
                connection.cursor(), role=OBSERVER, schema=SCHEMA, relations=[TABLE]
            )
        finally:
            connection.close()

    return _probe


def _role_probe(sock):
    def _probe():
        connection = _admin(sock)
        try:
            cursor = connection.cursor()
            cursor.execute("SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = %s", (OBSERVER,))
            return cursor.fetchone() is not None
        finally:
            connection.close()

    return _probe


def _provisioned_observer_session(sock):
    """**供裝者**(而非 runner)交出一條「已經可以扮演 observer 角色」的 session。

    RUN-2(b) 的處置:role membership DDL 屬於「誰供裝這台主機」的職責 —— T1 由本拋棄式叢集
    harness 供裝(鏡既有先例 ``test_agent_governance_pg_observer_bootstrap_disposable.py``),
    生產面由 operator 供裝。runner 自己**一行 membership DDL 都不發**,也因此不需要持有 admin
    寫連線 ⇒ ``pg_observer_bootstrap_adapter_v1.invariant`` 的 ``no role membership`` 對 runner
    這條 implementation path 逐字成立。

    **時序是 lazy,不是「預先建立」(E2 在真 PG 16.14 上證偽了前一版敘述)。** 本函式是在
    adapter 的 **step 8**(``independent_read_only_proof``)才被呼叫的,那條 ``GRANT`` 也才在
    那一刻發出 —— 因為 observer 角色要到 **step 7** 才存在(step 6 又硬拒既存的 observer 角色),
    所以它**不可能**在 apply 之前就建好。生產面同理:peer/ident 只解決認證,不解決 membership,
    operator 必須在 step 7 之後、step 8 之前補這一條 GRANT。

    ``ASSUME`` 刻意是**非 superuser** 登入角色:superuser 的 session 可以 ``SET ROLE`` 任何角色,
    於是 ``probe_observer_set_role_denied`` 根本得不到真的 42501 —— 那會把拒絕證明變成假的。
    """

    connection = _admin(sock)
    try:
        connection.cursor().execute(f'GRANT "{OBSERVER}" TO "{ASSUME}"')
    finally:
        connection.close()
    session = psycopg2.connect(
        host=sock, dbname=DB, user=ASSUME, password=ASSUME_PW, connect_timeout=10
    )
    session.autocommit = True
    return session


def _driver(sock, **overrides):
    applier = _admin(sock)
    # verifier 只做**唯讀** catalog 投影,故用一條 read-only 連線(絕不是 admin 寫連線)。
    verifier = psycopg2.connect(
        host=sock, dbname=DB, user="postgres", connect_timeout=10,
        options="-c default_transaction_read_only=on",
    )
    verifier.autocommit = True
    opened = [applier, verifier]

    def _observer_session():
        return _provisioned_observer_session(sock)

    def _wrong_credential():
        return psycopg2.connect(
            host=sock, dbname=DB, user=ASSUME, password=WRONG_PW, connect_timeout=10
        )

    driver = runner.ObserverBootstrapHostDriver(
        applier_connect=lambda: applier,
        verifier_connect=lambda: verifier,
        observer_session_connect=_observer_session,
        credential_escalation_connect=_wrong_credential,
        set_role_target=WRITER,
        verifier_capture_digest=CAP,
        **overrides,
    )
    return driver, opened


@disposable
def test_rehearsal_apply_then_failing_postcheck_then_compensation_restores_exactly(
    cluster, tmp_path, monkeypatch
):
    """三段:apply → 獨立 postcheck FAIL(T2)→ 補償 → catalog digest 逐位元組回前態。"""

    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)

    def _disagree(proof):
        # 獨立 verifier 不同意 applier 的觀測(T2 gate 的真實失敗形)。
        return {**proof, "reobserved_digest": "sha256:" + "1" * 64}

    driver, opened = _driver(sock, proof_fault=_disagree)
    try:
        result = runner.rehearse_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=_catalog_probe(sock), role_probe=_role_probe(sock),
        )
    finally:
        for connection in opened:
            connection.close()

    assert result["rehearsal"] is True
    assert result["lane"] == "disposable_rehearsal"
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "reobserved digest != applied (T2)" in result["receipt"]["failure_reason"]
    # 真的走完 apply → proof → compensate 三段(不是在前檢就退場)。
    assert driver.calls.count("create_read_only_observer") == 1
    assert driver.calls.count("independent_read_only_proof") == 1
    assert driver.calls.count("compensate") == 1
    # 逐位元組還原 + observer 角色真的消失。
    assert result["catalog_restored_exact"] is True
    assert result["pre_state_digest"] == result["post_state_digest"]
    assert result["observer_present_after"] is False
    # 誠實邊界:absolutely never a closure PASS / EFFECT 進展。
    assert result["production_apply_performed"] is False
    assert result["closure_pass_blocked"] is True
    assert result["ops_postcheck_evidence"] is None
    assert "not representable today" in result["ops_postcheck_refusal"]
    assert result["receipt"]["boundary"]["nine_authorities_false"] is True


@disposable
def test_rehearsal_real_denial_proofs_then_evidence_class_filter_compensates(
    cluster, tmp_path, monkeypatch
):
    """不注入任何 fault:真 42501 / 28P01 被觀測到,但 evidence_class 第一道 filter 仍補償。"""

    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)
    observed: dict = {}

    def _record(proof):
        observed.update(proof["read_only_proof"])
        return proof

    driver, opened = _driver(sock, proof_fault=_record)
    try:
        result = runner.rehearse_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=_catalog_probe(sock), role_probe=_role_probe(sock),
        )
    finally:
        for connection in opened:
            connection.close()

    # 真 SQLSTATE(nothing mocked):真 postgres 行程發出的拒絕碼。
    assert observed["write_denied"]["observed_sqlstate"] == "42501"
    assert observed["set_role_denied"]["observed_sqlstate"] == "42501"
    assert observed["credential_escalation_denied"]["observed_sqlstate"] in (
        obs.CREDENTIAL_DENIAL_SQLSTATES
    )
    assert observed["search_path_reset_harmless"]["harmless"] is True
    # T2 通過(verifier 的 reobserved == applied),但 evidence_class 不是 PLATFORM_ATTESTED。
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "not PLATFORM_ATTESTED" in result["receipt"]["failure_reason"]
    assert "signed_apply_attestation" not in driver.calls   # 連 attestation 都沒被請求
    assert result["catalog_restored_exact"] is True
    assert result["observer_present_after"] is False
    assert result["production_apply_performed"] is False


@disposable
def test_rehearsal_unconfirmed_compensation_is_recovery_required(cluster, tmp_path, monkeypatch):
    sock = cluster["socket_dir"]
    private_key = _install_operator_profile(tmp_path, monkeypatch)
    intent = _intent(sock=sock)
    authorization, signature = _sign(private_key, intent, HEAD)

    def _explode():
        raise RuntimeError("injected compensation failure")

    driver, opened = _driver(sock, compensate_fault=_explode)
    try:
        result = runner.rehearse_observer_bootstrap(
            intent, authorization, signature, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=_catalog_probe(sock), role_probe=_role_probe(sock),
        )
        assert result["status"] == "RECOVERY_REQUIRED"
        # 誠實回報:角色其實還在(絕不冒充「已補償」)。
        assert result["observer_present_after"] is True
        assert result["catalog_restored_exact"] is False
    finally:
        cleanup = _admin(sock)
        try:
            cleanup.cursor().execute(
                f"REVOKE ALL ON {SCHEMA}.{TABLE} FROM {OBSERVER}"
            )
            cleanup.cursor().execute(f"REVOKE ALL ON SCHEMA {SCHEMA} FROM {OBSERVER}")
            cleanup.cursor().execute(f'DROP ROLE IF EXISTS "{OBSERVER}"')
        finally:
            cleanup.close()
        for connection in opened:
            connection.close()


@disposable
def test_rehearsal_without_an_operator_signature_never_touches_the_cluster(cluster):
    sock = cluster["socket_dir"]
    intent = _intent(sock=sock)
    driver, opened = _driver(sock)
    try:
        result = runner.rehearse_observer_bootstrap(
            intent, None, None, now=NOW, source_head=HEAD, driver=driver,
            catalog_probe=_catalog_probe(sock), role_probe=_role_probe(sock),
        )
    finally:
        for connection in opened:
            connection.close()
    assert result["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert "AUTHORIZATION_REJECTED" in result["receipt"]["failure_reason"]
    assert driver.calls == []               # driver 一次都沒被呼叫
    assert result["observer_present_after"] is False
    assert result["catalog_restored_exact"] is True

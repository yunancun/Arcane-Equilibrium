"""Disposable-cluster proof for the §8.3 consumer failure classification (W2 F1/F2).

Gated on ``shutil.which("initdb")`` + ``psycopg2``.  When PG binaries are present this
``initdb``-creates a throwaway, socket-only, ``scram-sha-256`` cluster (reusing the S1.1
*pattern*, not a shared helper) and drives **real** ``psycopg2.connect`` failures through
the production classifier.  Nothing is mocked: a real ``postgres`` process emits the FATAL
and the real driver decides what the exception carries.

Why this lane exists (the OPS finding it closes): the hermetic suite asserted
``pgcode="28P01"`` on a *connect-time* error, which the driver never produces.  libpq
returns no ``PGresult`` when the connection itself fails, so psycopg2 leaves
``pgcode`` / ``diag.sqlstate`` / ``pgerror`` at ``None`` and only the server's FATAL text
survives.  A SQLSTATE-only classifier therefore treated a wrong credential as a transient
outage and retried forever — the exact §8.3 failure the fix claimed to close, hidden by a
fixture that encoded a false driver shape.  These assertions are backed by a real driver
and a real server, so a psycopg2/PG behaviour change breaks them.

Proven here on a real cluster:

* connect-time ``28P01`` / ``3D000`` / pg_hba denial all arrive with ``pgcode is None``
  and are still classified ``permanent_config`` (→ typed → production exit 78);
* a genuine connectivity failure (no server on the socket) stays ``transient``;
* the resident loop takes ZERO backoff on the real auth failure;
* a real in-session ``42P01`` on a NON-identity relation becomes a typed permanent error
  carrying its SQLSTATE and relation name (F2), instead of escaping as exit 1.

The cluster lives in a temp dir and is torn down in a finally.  Absent binaries SKIP with
a clear reason — never a false pass.  No production socket, no repository mutation.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "program_code") not in sys.path:
    sys.path.insert(0, str(ROOT / "program_code"))

from ml_training import alr_application_identity as app_identity  # noqa: E402
from ml_training import alr_consumer_resilience as resilience  # noqa: E402

INITDB = shutil.which("initdb")
PG_CTL = shutil.which("pg_ctl")
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 driver is required")

pytestmark = pytest.mark.skipif(
    not (INITDB and PG_CTL),
    reason="initdb/pg_ctl are absent; the disposable connect-failure proof cannot run",
)

DATABASE = "postgres"
SCANNER_ROLE = "aiml_engine_scanner"
SCANNER_PW = "aiml-scanner-cred-v0"
WRONG_PW = "aiml-scanner-cred-WRONG"
REJECTED_ROLE = "aiml_hba_rejected"
# 乾淨環境:子進程一律不繼承 ambient PG* 路由;lc_messages=C 讓 server 訊息穩定英文。
CLEAN_SUBPROCESS_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "LANG": "C",
    "LC_ALL": "C",
}


def _run(cmd, *, logfile, timeout):
    result = subprocess.run(
        cmd,
        env=CLEAN_SUBPROCESS_ENV,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = ""
        try:
            detail = Path(logfile).read_text(encoding="utf-8")[-800:]
        except OSError:
            pass
        raise RuntimeError(f"command failed rc={result.returncode}: {cmd[0]}\n{detail}")


@pytest.fixture(scope="module")
def disposable_cluster():
    tmp = tempfile.mkdtemp(prefix="aiml_resilience_")
    data_dir = os.path.join(tmp, "data")
    sock_dir = os.path.join(tmp, "sock")
    empty_dir = os.path.join(tmp, "no-server")  # 沒有 server 的 socket 目錄
    logfile = os.path.join(tmp, "server.log")
    os.makedirs(sock_dir)
    os.makedirs(empty_dir)
    started = False
    try:
        # --auth=trust 供 superuser bootstrap;其餘角色走自寫 pg_hba 的 scram/reject。
        _run(
            [INITDB, "-D", data_dir, "-U", "postgres", "--auth=trust", "-E", "UTF8", "-N"],
            logfile=logfile,
            timeout=120,
        )
        with open(os.path.join(data_dir, "postgresql.auto.conf"), "a", encoding="utf-8") as handle:
            handle.write("\nlisten_addresses = ''\n")
            handle.write(f"unix_socket_directories = '{sock_dir}'\n")
            handle.write("fsync = off\n")
            handle.write("password_encryption = 'scram-sha-256'\n")
            handle.write("lc_messages = 'C'\n")
        with open(os.path.join(data_dir, "pg_hba.conf"), "w", encoding="utf-8") as handle:
            handle.write("local   all   postgres          trust\n")
            handle.write(f"local   all   {REJECTED_ROLE}   reject\n")
            handle.write(f"local   all   {SCANNER_ROLE}    scram-sha-256\n")
        _run(
            [PG_CTL, "-D", data_dir, "-l", logfile, "-w", "-t", "40", "start"],
            logfile=logfile,
            timeout=90,
        )
        started = True
        admin = psycopg2.connect(
            host=sock_dir, dbname=DATABASE, user="postgres", connect_timeout=10
        )
        try:
            admin.autocommit = True
            cursor = admin.cursor()
            cursor.execute(f"CREATE ROLE {SCANNER_ROLE} LOGIN PASSWORD %s", (SCANNER_PW,))
            cursor.execute(f"CREATE ROLE {REJECTED_ROLE} LOGIN PASSWORD %s", (SCANNER_PW,))
            cursor.execute("CREATE SCHEMA learning")
            cursor.execute(f"GRANT USAGE ON SCHEMA learning TO {SCANNER_ROLE}")
        finally:
            admin.close()
        yield {"socket_dir": sock_dir, "empty_socket_dir": empty_dir}
    finally:
        pid_file = os.path.join(data_dir, "postmaster.pid")
        if started or os.path.exists(pid_file):
            try:
                subprocess.run(
                    [PG_CTL, "-D", data_dir, "-m", "immediate", "stop"],
                    env=CLEAN_SUBPROCESS_ENV,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=30,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        shutil.rmtree(tmp, ignore_errors=True)


def _connect_failure(**kwargs) -> BaseException:
    """真的去連,回傳驅動拋出的那個例外(連上了就是測試前提失效)。"""
    try:
        connection = psycopg2.connect(connect_timeout=10, **kwargs)
    except Exception as exc:  # noqa: BLE001 - 這就是待分類的真實失敗
        return exc
    connection.close()
    raise AssertionError(f"connection unexpectedly succeeded: {kwargs.get('user')!r}")


def test_scanner_credential_actually_works_on_this_cluster(disposable_cluster) -> None:
    """前提見證:正確憑證連得上——否則下面的拒絕可能只是叢集壞了。"""
    connection = psycopg2.connect(
        host=disposable_cluster["socket_dir"],
        dbname=DATABASE,
        user=SCANNER_ROLE,
        password=SCANNER_PW,
        connect_timeout=10,
    )
    connection.close()


@pytest.mark.parametrize(
    "case,expected_sqlstate",
    [
        ("wrong_password", "28P01"),
        ("missing_database", "3D000"),
        ("hba_rejected", "28000"),
        ("missing_role", "28000"),
    ],
)
def test_real_connect_time_failures_carry_no_sqlstate_yet_are_permanent(
    disposable_cluster, case: str, expected_sqlstate: str
) -> None:
    sock = disposable_cluster["socket_dir"]
    kwargs = {
        "wrong_password": dict(
            host=sock, dbname=DATABASE, user=SCANNER_ROLE, password=WRONG_PW
        ),
        "missing_database": dict(
            host=sock, dbname="trading_ai_absent", user=SCANNER_ROLE, password=SCANNER_PW
        ),
        "hba_rejected": dict(
            host=sock, dbname=DATABASE, user=REJECTED_ROLE, password=SCANNER_PW
        ),
        "missing_role": dict(
            host=sock, dbname=DATABASE, user="aiml_ghost_role", password=SCANNER_PW
        ),
    }[case]
    error = _connect_failure(**kwargs)

    # (1) 真驅動事實:連線期例外根本沒有 SQLSTATE(這是 OPS 的 F1 根因)。
    assert isinstance(error, psycopg2.OperationalError)
    assert error.pgcode is None, f"driver unexpectedly populated pgcode: {error.pgcode!r}"
    assert getattr(error.diag, "sqlstate", None) is None
    assert error.pgerror is None

    # (2) 分流仍必須是 permanent——修前這裡是 transient,單元每 300 秒重試到永遠。
    assert resilience.resolve_db_error_sqlstate(error) == expected_sqlstate, str(error)
    assert resilience.classify_db_error(error) == "permanent_config", str(error)
    assert not resilience.is_transient_db_availability_error(error)

    # (3) 且真的落在 production 的 exit-78 面。
    typed = resilience.permanent_db_config_error(error)
    assert typed is not None
    assert str(typed).startswith(
        f"{resilience.PERMANENT_DB_CONFIG_CODE_PREFIX}{expected_sqlstate}"
    )
    assert app_identity.is_permanent_pre_db_error(typed)


def test_real_connectivity_failure_stays_transient(disposable_cluster) -> None:
    """沒有 server 的 socket 目錄 = 真停機:必須維持 transient(§8.3 不得退出)。"""
    error = _connect_failure(
        host=disposable_cluster["empty_socket_dir"], dbname=DATABASE, user=SCANNER_ROLE
    )
    assert isinstance(error, psycopg2.OperationalError)
    assert error.pgcode is None
    assert resilience.resolve_db_error_sqlstate(error) is None, str(error)
    assert resilience.classify_db_error(error) == "transient", str(error)
    assert resilience.permanent_db_config_error(error) is None


def test_resident_loop_never_retries_a_real_authentication_failure(
    disposable_cluster,
) -> None:
    """端到端真驅動:常駐迴圈拿到真 28P01 → 零退避、typed permanent(→ 78)。"""
    sock = disposable_cluster["socket_dir"]
    slept: list[float] = []
    attempts = {"count": 0}

    def open_connection():
        attempts["count"] += 1
        return psycopg2.connect(
            host=sock,
            dbname=DATABASE,
            user=SCANNER_ROLE,
            password=WRONG_PW,
            connect_timeout=10,
        )

    with pytest.raises(resilience.AlrPermanentDbConfigError) as failure:
        resilience.run_resident_db_sessions(
            open_connection=open_connection,
            run_session=lambda connection: {"drains": 0},
            close_connection=lambda connection: connection.close(),
            should_stop=lambda: False,
            sleep=slept.append,
            jitter=lambda: 0.0,
        )
    assert str(failure.value) == "db_config_permanent_sqlstate_28P01"
    assert slept == []  # 修前:5s,10s,20s,… 300s 無限重試
    assert attempts["count"] == 1
    assert app_identity.is_permanent_pre_db_error(failure.value)


def test_resident_loop_still_retries_a_real_outage(disposable_cluster) -> None:
    """反向:真停機(無 server)仍走有界退避、不退出——F1 沒有收緊過頭。"""
    empty = disposable_cluster["empty_socket_dir"]
    sock = disposable_cluster["socket_dir"]
    slept: list[float] = []
    attempts = {"count": 0}

    def open_connection():
        attempts["count"] += 1
        host = empty if attempts["count"] <= 2 else sock
        return psycopg2.connect(
            host=host,
            dbname=DATABASE,
            user=SCANNER_ROLE,
            password=SCANNER_PW,
            connect_timeout=10,
        )

    outcome = resilience.run_resident_db_sessions(
        open_connection=open_connection,
        run_session=lambda connection: {"drains": 1},
        close_connection=lambda connection: connection.close(),
        should_stop=lambda: False,
        sleep=slept.append,
        jitter=lambda: 1.0,
    )
    assert outcome["status"] == "SESSION_COMPLETED"
    assert slept == [5.0, 10.0]
    assert all(5.0 <= value <= 300.0 for value in slept)


def test_real_in_session_undefined_table_is_typed_permanent_with_its_relation(
    disposable_cluster,
) -> None:
    """F2 真驅動:非身分關聯的 42P01 → typed permanent,帶 SQLSTATE 與關聯名。

    修前:裸 ``psycopg2.errors.UndefinedTable`` 逸出 main 的 except → exit 1 →
    ``Restart=on-failure`` 三次燒光 ``StartLimitBurst`` → 單元永久 failed。
    """
    connection = psycopg2.connect(
        host=disposable_cluster["socket_dir"],
        dbname=DATABASE,
        user=SCANNER_ROLE,
        password=SCANNER_PW,
        connect_timeout=10,
    )
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT * FROM learning.alr_consumer_events")
            raise AssertionError("relation unexpectedly exists")
        except psycopg2.Error as exc:
            error = exc
    finally:
        connection.close()

    # session 內 server 有回 error response,所以這裡 pgcode 是有值的(與連線期相反)。
    assert error.pgcode == "42P01"
    assert resilience.classify_db_error(error) == "permanent_config"
    typed = resilience.permanent_db_config_error(error)
    assert typed is not None
    assert str(typed) == (
        "db_config_permanent_sqlstate_42P01"
        f"{resilience.DB_ERROR_SUBJECT_INFIX}learning.alr_consumer_events"
    )
    assert app_identity.is_permanent_pre_db_error(typed)


def test_real_insufficient_privilege_is_typed_permanent(disposable_cluster) -> None:
    """真 42501(scanner 對未授權的表)同樣是 typed permanent,而非崩潰迴圈。"""
    sock = disposable_cluster["socket_dir"]
    admin = psycopg2.connect(host=sock, dbname=DATABASE, user="postgres", connect_timeout=10)
    try:
        admin.autocommit = True
        admin.cursor().execute(
            "CREATE TABLE IF NOT EXISTS learning.alr_health_events(id integer PRIMARY KEY)"
        )
    finally:
        admin.close()
    connection = psycopg2.connect(
        host=sock, dbname=DATABASE, user=SCANNER_ROLE, password=SCANNER_PW, connect_timeout=10
    )
    try:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT * FROM learning.alr_health_events")
            raise AssertionError("SELECT unexpectedly permitted")
        except psycopg2.Error as exc:
            error = exc
    finally:
        connection.close()

    assert error.pgcode == "42501"
    typed = resilience.permanent_db_config_error(error)
    assert typed is not None
    assert str(typed).startswith("db_config_permanent_sqlstate_42501")
    assert resilience.db_error_subject(error) == "alr_health_events"
    assert app_identity.is_permanent_pre_db_error(typed)

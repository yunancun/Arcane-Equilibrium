"""S2.4 §8.3 / §10.5 #35(W2 P1-A)常駐 consumer 重連語義的確定性回歸測試。

覆蓋(全部零真實 sleep、零真實 DB):

* 長時間 DB 停機 → 常駐 consumer **不退出**:逐次關閉失敗連線、退避序列有界且含 jitter、
  值域嚴格落在 [5,300],恢復後回到正常 session;
* durable cursor 語義:重連後由 DB 側 cursor 續讀(行程內零跨 session 進度狀態),
  且每次重連都重新 start_consumer_session;
* 無界累積防呆:200 次 transient 失敗後,常駐狀態只有固定純量欄位(零 list/dict 成長);
* 重連時 topology guard / 叢集身分列不符 → typed permanent 失敗 → main 以 exit 78 收場;
* 非 transient 失敗(typed consumer 錯誤)一律上拋,不進入無限重試。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "program_code") not in sys.path:
    sys.path.insert(0, str(ROOT / "program_code"))

from ml_training import alr_application_identity as app_identity  # noqa: E402
from ml_training import alr_consumer_resilience as resilience  # noqa: E402
from ml_training import alr_event_consumer as consumer  # noqa: E402
from ml_training.alr_candidate_board_events import AlrEventConsumerError  # noqa: E402
from ml_training.aiml_gate_receipt_schema_core import resolve_facade  # noqa: E402


class _FakeOperationalError(Exception):
    """模擬 psycopg2.OperationalError(以型別全名比對,不需安裝 psycopg2)。"""

    __module__ = "psycopg2"
    __qualname__ = "OperationalError"


_FakeOperationalError.__name__ = "OperationalError"


# --------------------------------------------------------------------------- #
# 退避序列:有界指數 + jitter,值域恆在 [5,300]
# --------------------------------------------------------------------------- #
def test_backoff_is_bounded_exponential_with_jitter_inside_five_to_three_hundred() -> None:
    # jitter=1.0 → 取上界:5,10,20,...,300 後夾住
    ceilings = [resilience.next_backoff_seconds(n, jitter=1.0) for n in range(1, 12)]
    assert ceilings[:6] == [5.0, 10.0, 20.0, 40.0, 80.0, 160.0]
    assert all(value == 300.0 for value in ceilings[6:])
    # jitter=0.0 → 恆為下界 5;任何 jitter 都不得越界
    for attempt in (1, 2, 8, 64, 4096, 10**6):
        for jitter in (0.0, 0.13, 0.5, 0.99, 1.0):
            delay = resilience.next_backoff_seconds(attempt, jitter=jitter)
            assert 5.0 <= delay <= 300.0, (attempt, jitter, delay)
    assert resilience.next_backoff_seconds(9, jitter=0.0) == 5.0
    # jitter 真的改變值(非常數退避)
    assert resilience.next_backoff_seconds(5, jitter=0.25) != resilience.next_backoff_seconds(
        5, jitter=0.75
    )


def test_backoff_rejects_invalid_attempt_or_jitter() -> None:
    for bad_attempt in (0, -1, True, 1.5):
        with pytest.raises(AlrEventConsumerError, match="reconnect_backoff_attempt_invalid"):
            resilience.next_backoff_seconds(bad_attempt, jitter=0.5)
    for bad_jitter in (-0.01, 1.01, True, "x"):
        with pytest.raises(AlrEventConsumerError, match="reconnect_backoff_jitter_invalid"):
            resilience.next_backoff_seconds(3, jitter=bad_jitter)


def test_only_connection_availability_errors_are_transient() -> None:
    assert resilience.is_transient_db_availability_error(_FakeOperationalError("down"))
    assert not resilience.is_transient_db_availability_error(ValueError("boom"))
    assert not resilience.is_transient_db_availability_error(
        AlrEventConsumerError("single_instance_lock_busy")
    )
    assert not resilience.is_transient_db_availability_error(
        resilience.AlrRuntimeIdentityError("cluster_identity_row_digest_mismatch")
    )


# --------------------------------------------------------------------------- #
# 常駐迴圈:停機不退出、關閉失敗連線、退避後恢復
# --------------------------------------------------------------------------- #
def test_prolonged_outage_keeps_one_resident_consumer_alive_and_resumes() -> None:
    opened: list[str] = []
    closed: list[str] = []
    slept: list[float] = []
    outage = {"remaining": 5}

    def open_connection() -> str:
        name = f"conn-{len(opened)}"
        opened.append(name)
        if outage["remaining"] > 0:
            outage["remaining"] -= 1
            raise _FakeOperationalError("could not connect to server")
        return name

    def run_session(connection: str) -> dict[str, int]:
        return {"drains": 1, "rows_seen": 3, "connection": connection}

    state = resilience.ResidentConsumerState()
    outcome = resilience.run_resident_db_sessions(
        open_connection=open_connection,
        run_session=run_session,
        close_connection=closed.append,
        should_stop=lambda: False,
        sleep=slept.append,
        jitter=lambda: 1.0,
        state=state,
    )

    assert outcome["status"] == "SESSION_COMPLETED"
    assert outcome["result"]["rows_seen"] == 3
    # 五次停機 → 五次退避,序列為有界指數上界
    assert slept == [5.0, 10.0, 20.0, 40.0, 80.0]
    assert all(5.0 <= value <= 300.0 for value in slept)
    assert len(opened) == 6  # 五次失敗 + 一次成功
    # 失敗連線從未成功建立 → 無可關閉物件;成功那次由常駐迴圈關閉
    assert closed == ["conn-5"]
    assert state.transient_failures == 5
    assert state.consecutive_failures == 0
    assert state.sessions_completed == 1


def test_failed_connection_is_closed_before_each_retry() -> None:
    closed: list[str] = []
    attempts = {"count": 0}

    def open_connection() -> str:
        attempts["count"] += 1
        return f"conn-{attempts['count']}"

    def run_session(connection: str) -> dict[str, int]:
        if attempts["count"] < 3:
            raise _FakeOperationalError("server closed the connection unexpectedly")
        return {"drains": 1}

    resilience.run_resident_db_sessions(
        open_connection=open_connection,
        run_session=run_session,
        close_connection=closed.append,
        should_stop=lambda: False,
        sleep=lambda seconds: None,
        jitter=lambda: 0.0,
    )
    # 每一次(含失敗)都關閉,零連線洩漏
    assert closed == ["conn-1", "conn-2", "conn-3"]


def test_close_failure_never_masks_the_transient_cause_or_blocks_retry() -> None:
    attempts = {"count": 0}

    def open_connection() -> str:
        attempts["count"] += 1
        return "conn"

    def run_session(connection: str) -> dict[str, int]:
        if attempts["count"] < 2:
            raise _FakeOperationalError("outage")
        return {"drains": 0}

    def hostile_close(connection: str) -> None:
        raise OSError("socket already dead")

    outcome = resilience.run_resident_db_sessions(
        open_connection=open_connection,
        run_session=run_session,
        close_connection=hostile_close,
        should_stop=lambda: False,
        sleep=lambda seconds: None,
        jitter=lambda: 0.0,
    )
    assert outcome["status"] == "SESSION_COMPLETED"


def test_two_hundred_outages_accumulate_no_tasks_rows_or_memory() -> None:
    slept: list[float] = []
    outage = {"remaining": 200}
    state = resilience.ResidentConsumerState()

    def open_connection() -> str:
        if outage["remaining"] > 0:
            outage["remaining"] -= 1
            raise _FakeOperationalError("down")
        return "conn"

    resilience.run_resident_db_sessions(
        open_connection=open_connection,
        run_session=lambda connection: {"drains": 0},
        close_connection=lambda connection: None,
        should_stop=lambda: False,
        sleep=slept.append,
        jitter=lambda: 0.5,
        state=state,
    )
    assert len(slept) == 200
    assert all(5.0 <= value <= 300.0 for value in slept)
    # 常駐狀態是固定形狀的純量集合:零容器欄位 → 不可能隨停機時長成長
    assert set(resilience.ResidentConsumerState.__slots__) == {
        "sessions_completed",
        "transient_failures",
        "consecutive_failures",
        "last_backoff_seconds",
        "total_backoff_seconds",
    }
    assert not hasattr(state, "__dict__")
    assert all(
        isinstance(getattr(state, name), (int, float))
        for name in resilience.ResidentConsumerState.__slots__
    )
    assert state.transient_failures == 200


def test_stop_signal_during_outage_returns_cleanly_without_result() -> None:
    stop = {"set": False}

    def open_connection() -> str:
        raise _FakeOperationalError("down")

    def sleep(seconds: float) -> None:
        stop["set"] = True  # 模擬退避等待期間收到 SIGTERM

    outcome = resilience.run_resident_db_sessions(
        open_connection=open_connection,
        run_session=lambda connection: {"drains": 0},
        close_connection=lambda connection: None,
        should_stop=lambda: stop["set"],
        sleep=sleep,
        jitter=lambda: 0.0,
    )
    assert outcome["status"] == "STOPPED_DURING_DB_OUTAGE"
    assert outcome["result"] is None
    assert outcome["telemetry"]["transient_failures"] == 2


def test_non_transient_failure_is_raised_not_retried() -> None:
    slept: list[float] = []

    def run_session(connection: str) -> dict[str, int]:
        raise AlrEventConsumerError("single_instance_lock_busy")

    with pytest.raises(AlrEventConsumerError, match="single_instance_lock_busy"):
        resilience.run_resident_db_sessions(
            open_connection=lambda: "conn",
            run_session=run_session,
            close_connection=lambda connection: None,
            should_stop=lambda: False,
            sleep=slept.append,
            jitter=lambda: 0.0,
        )
    assert slept == []


# --------------------------------------------------------------------------- #
# 重連身分閘:topology guard + 叢集身分列
# --------------------------------------------------------------------------- #
_ENDPOINT = {"host": "127.0.0.1", "port": 5432, "dbname": "trading_ai"}
_DSN_IDENTITY = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "trading_ai",
    "user": "aiml_engine_scanner",
}
_ROW = {
    "system_identifier": "7412345678901234567",
    "database_oid": 16401,
    "server_major_version": 16,
    "runtime_host": "127.0.0.1",
    "runtime_port": 5432,
    "runtime_dbname": "trading_ai",
    "binding_nonce": "b3f1c0d9a7e24f10",
}


def _write_guard(tmp_path: Path, *, row: dict | None = None, **overrides) -> Path:
    facade = resolve_facade()
    guard = {
        "schema_version": "pg_topology_runtime_guard_v1",
        "guard_path": "/etc/arcane-equilibrium/aiml/engine-scanner/topology-runtime-guard.json",
        "cluster_identity_row_digest": resilience.cluster_identity_row_digest(
            row if row is not None else _ROW
        ),
        "plan_topology_digest": "sha256:" + "1" * 64,
        "runtime_endpoint": dict(_ENDPOINT),
        "system_identifier": _ROW["system_identifier"],
        "database_oid": _ROW["database_oid"],
        "server_major_version": _ROW["server_major_version"],
        "binding_nonce": _ROW["binding_nonce"],
        "expected_topology_values_digest": "sha256:" + "2" * 64,
    }
    guard.update(overrides)
    guard["self_digest"] = facade.artifact_self_digest(guard)
    path = tmp_path / "topology-runtime-guard.json"
    path.write_text(json.dumps(guard, sort_keys=True), encoding="utf-8")
    return path


class _IdentityConnection:
    """只回應兩條身分 SELECT 的最小連線替身(逐條記錄真實執行的 SQL)。"""

    def __init__(self, *, connected: dict | None = None, rows: list | None = None) -> None:
        self.connected = connected if connected is not None else {
            "connected_user": "aiml_engine_scanner",
            "connected_database": "trading_ai",
            "server_version_num": "160004",
        }
        self.rows = rows if rows is not None else [dict(_ROW)]
        self.executed: list[str] = []
        self.rollbacks = 0

    def cursor(self):
        connection = self

        class _Cursor:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                connection.executed.append(sql)
                self._sql = sql

            def fetchall(self):
                if "alr_runtime_cluster_identity_v1" in self._sql:
                    return list(connection.rows)
                return [dict(connection.connected)]

        return _Cursor()

    def rollback(self) -> None:
        self.rollbacks += 1


def test_matching_guard_and_cluster_identity_row_admits_consumption(tmp_path: Path) -> None:
    guard_path = _write_guard(tmp_path)
    connection = _IdentityConnection()
    check = resilience.verify_connected_cluster_identity(
        connection, topology_guard_file=guard_path, dsn_identity=_DSN_IDENTITY
    )
    assert check["status"] == "MATCH"
    assert check["connected_user"] == "aiml_engine_scanner"
    assert connection.rollbacks == 1  # 身分讀取不留交易
    assert any("alr_runtime_cluster_identity_v1" in sql for sql in connection.executed)


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ({"system_identifier": "9999999999999999999"}, "cluster_identity_system_identifier_mismatch"),
        ({"database_oid": 99999}, "cluster_identity_database_oid_mismatch"),
        ({"runtime_port": 5433}, "cluster_identity_endpoint_mismatch"),
        ({"binding_nonce": "deadbeefdeadbeef"}, "cluster_identity_row_digest_mismatch"),
    ],
)
def test_cluster_identity_row_drift_is_permanent_typed_failure(
    tmp_path: Path, mutation: dict, expected: str
) -> None:
    # guard 綁定的是「正確」那一列;連上的叢集回傳漂移列。
    guard_path = _write_guard(tmp_path)
    drifted = dict(_ROW)
    drifted.update(mutation)
    connection = _IdentityConnection(rows=[drifted])
    with pytest.raises(resilience.AlrRuntimeIdentityError, match=expected):
        resilience.verify_connected_cluster_identity(
            connection, topology_guard_file=guard_path, dsn_identity=_DSN_IDENTITY
        )


def test_absent_or_duplicated_identity_row_is_refused(tmp_path: Path) -> None:
    guard_path = _write_guard(tmp_path)
    with pytest.raises(resilience.AlrRuntimeIdentityError, match="cluster_identity_row_absent"):
        resilience.verify_connected_cluster_identity(
            _IdentityConnection(rows=[]), topology_guard_file=guard_path
        )
    with pytest.raises(
        resilience.AlrRuntimeIdentityError, match="cluster_identity_row_not_unique"
    ):
        resilience.verify_connected_cluster_identity(
            _IdentityConnection(rows=[dict(_ROW), dict(_ROW)]),
            topology_guard_file=guard_path,
        )


def test_connected_user_database_and_version_are_compared(tmp_path: Path) -> None:
    guard_path = _write_guard(tmp_path)
    cases = {
        "cluster_identity_user_mismatch": {
            "connected_user": "alr_shadow",
            "connected_database": "trading_ai",
            "server_version_num": "160004",
        },
        "cluster_identity_database_mismatch": {
            "connected_user": "aiml_engine_scanner",
            "connected_database": "postgres",
            "server_version_num": "160004",
        },
        "cluster_identity_server_version_mismatch": {
            "connected_user": "aiml_engine_scanner",
            "connected_database": "trading_ai",
            "server_version_num": "150009",
        },
    }
    for expected, connected in cases.items():
        with pytest.raises(resilience.AlrRuntimeIdentityError, match=expected):
            resilience.verify_connected_cluster_identity(
                _IdentityConnection(connected=connected),
                topology_guard_file=guard_path,
                dsn_identity=_DSN_IDENTITY,
            )


def test_tampered_guard_file_is_refused_on_every_reconnect(tmp_path: Path) -> None:
    guard_path = _write_guard(tmp_path)
    guard = json.loads(guard_path.read_text(encoding="utf-8"))
    guard["database_oid"] = 12345  # 未重簽 self_digest
    guard_path.write_text(json.dumps(guard, sort_keys=True), encoding="utf-8")
    with pytest.raises(resilience.AlrRuntimeIdentityError, match="topology_guard_"):
        resilience.verify_connected_cluster_identity(
            _IdentityConnection(), topology_guard_file=guard_path
        )
    guard_path.unlink()
    with pytest.raises(resilience.AlrRuntimeIdentityError, match="topology_guard_"):
        resilience.verify_connected_cluster_identity(
            _IdentityConnection(), topology_guard_file=guard_path
        )


def test_identity_mismatch_codes_are_permanent_pre_db_and_exit_78() -> None:
    for code in (
        "cluster_identity_row_digest_mismatch",
        "cluster_identity_user_mismatch",
        "topology_guard_topology_guard_self_digest_mismatch",
        "psycopg2_unavailable",
        "runtime_file_lock_unsupported",
        "candidate_board_inotify_unsupported",
    ):
        assert app_identity.is_permanent_pre_db_error(AlrEventConsumerError(code)), code
    # 可自癒/host 競用類刻意不在列(否則會把可恢復狀況鎖成永久 78)
    for code in (
        "single_instance_lock_busy",
        "runtime_file_lock_busy",
        "candidate_board_directory_unavailable",
    ):
        assert not app_identity.is_permanent_pre_db_error(AlrEventConsumerError(code)), code
    assert app_identity.EX_CONFIG_EXIT_CODE == 78


# --------------------------------------------------------------------------- #
# consumer 佈線:重連時重跑身分閘、durable cursor 由 DB 側續讀
# --------------------------------------------------------------------------- #
def test_run_event_consumer_reconnects_and_reverifies_identity_each_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    guard_path = _write_guard(tmp_path)
    connections: list[_IdentityConnection] = []
    sessions: list[str] = []
    slept: list[float] = []
    outage = {"remaining": 3}
    # durable cursor 只存在於 DB 側:每個 session 都自同一 cursor 續讀
    durable_cursor = {"value": 41}

    class _Lock:
        def __enter__(self):
            return None

        def __exit__(self, *args):
            return False

    def connect(dsn: str) -> _IdentityConnection:
        if outage["remaining"] > 0:
            outage["remaining"] -= 1
            raise _FakeOperationalError("the database system is shutting down")
        connection = _IdentityConnection()
        connections.append(connection)
        return connection

    def loop(connection, **kwargs):
        sessions.append(kwargs["session_id"])
        durable_cursor["value"] += 1  # DB 側 cursor 前進(行程內零進度狀態)
        return {"drains": 1, "cursor": durable_cursor["value"]}

    monkeypatch.setattr(
        consumer,
        "_preflight_source_compatibility",
        lambda **kwargs: {"fit_quarantined": False, "repo_source_head": "a" * 40},
    )
    monkeypatch.setattr(
        consumer, "read_local_dsn_file", lambda path, **kwargs: "host=127.0.0.1"
    )
    monkeypatch.setattr(consumer, "_install_shutdown_handlers", lambda event: {})
    monkeypatch.setattr(consumer, "_restore_shutdown_handlers", lambda previous: None)
    monkeypatch.setattr(consumer, "runtime_file_lock", lambda path: _Lock())
    monkeypatch.setattr(consumer, "_connect_listener", connect)
    monkeypatch.setattr(consumer, "acquire_single_instance", lambda connection: True)
    monkeypatch.setattr(consumer, "release_single_instance", lambda connection: None)
    monkeypatch.setattr(consumer, "new_session_id", lambda: f"session-{len(sessions)}")
    monkeypatch.setattr(
        consumer, "start_consumer_session", lambda connection, session_id: None
    )
    monkeypatch.setattr(
        consumer, "stop_consumer_session", lambda connection, session_id: None
    )
    monkeypatch.setattr(consumer, "event_consumer_loop", loop)

    result = consumer.run_event_consumer(
        dsn_path=tmp_path / "dsn",
        lock_path=tmp_path / "lock",
        max_batch=8,
        source_head="a" * 40,
        topology_guard_file=guard_path,
        dsn_required_identity=_DSN_IDENTITY,
        reconnect_sleep=slept.append,
        reconnect_jitter=lambda: 1.0,
    )

    # 三次停機不退出;第四次連上後照常回傳 session 結果
    assert slept == [5.0, 10.0, 20.0]
    assert result["drains"] == 1
    # durable cursor 自 DB 側續讀(41 → 42),行程未重置或重放進度
    assert result["cursor"] == 42
    assert sessions == ["session-0"]
    # 每次成功連線都跑過在帶身分閘(guard 重讀 + 身分列比對)
    assert len(connections) == 1
    assert any(
        "alr_runtime_cluster_identity_v1" in sql for sql in connections[0].executed
    )


def test_identity_mismatch_on_reconnect_exits_78(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """§8.3:重連身分不符 → typed permanent → production main 以 exit 78 收場。"""
    guard_path = _write_guard(tmp_path)
    drifted = dict(_ROW)
    drifted["system_identifier"] = "1111111111111111111"

    class _Lock:
        def __enter__(self):
            return None

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        consumer,
        "_preflight_source_compatibility",
        lambda **kwargs: {"fit_quarantined": False, "repo_source_head": "a" * 40},
    )
    monkeypatch.setattr(
        consumer, "read_local_dsn_file", lambda path, **kwargs: "host=127.0.0.1"
    )
    monkeypatch.setattr(consumer, "_install_shutdown_handlers", lambda event: {})
    monkeypatch.setattr(consumer, "_restore_shutdown_handlers", lambda previous: None)
    monkeypatch.setattr(consumer, "runtime_file_lock", lambda path: _Lock())
    monkeypatch.setattr(
        consumer, "_connect_listener", lambda dsn: _IdentityConnection(rows=[drifted])
    )
    monkeypatch.setattr(
        consumer,
        "acquire_single_instance",
        lambda connection: pytest.fail("identity gate must precede any consumption"),
    )

    real_run_event_consumer = consumer.run_event_consumer

    def run_consumer() -> None:
        real_run_event_consumer(
            dsn_path=tmp_path / "dsn",
            lock_path=tmp_path / "lock",
            max_batch=8,
            source_head="a" * 40,
            topology_guard_file=guard_path,
            dsn_required_identity=_DSN_IDENTITY,
            reconnect_sleep=lambda seconds: pytest.fail("mismatch must not be retried"),
        )

    with pytest.raises(resilience.AlrRuntimeIdentityError):
        run_consumer()

    # production main 把該 typed 失敗映射為 exit 78(RestartPreventExitStatus=78)
    monkeypatch.setattr(consumer, "run_event_consumer", lambda **kwargs: run_consumer())
    monkeypatch.setattr(
        consumer,
        "run_production_preflight_from_args",
        lambda arguments: {
            "summary": {"status": "PASS"},
            "source_value_guard": {
                "schema_version": "source_value_guard_v1",
                "status": "PASS",
                "learning_runtime_digest_v2": "sha256:" + "0" * 64,
            },
            "run_kwargs": {},
        },
    )
    exit_code = consumer.main(
        [
            "--dsn-file",
            str(tmp_path / "dsn"),
            "--lock-file",
            str(tmp_path / "lock"),
            "--application-root",
            str(tmp_path),
            "--source-head",
            "a" * 40,
        ]
    )
    assert exit_code == 78

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

import errno
import inspect
import json
import os
import re
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


class _FakeDiagnostics:
    """psycopg2 的 ``error.diag``(只帶本模組會讀到的欄位)。"""

    def __init__(self, sqlstate: str | None) -> None:
        self.sqlstate = sqlstate


class _FakeOperationalError(Exception):
    """模擬 psycopg2.OperationalError(以型別全名比對,不需安裝 psycopg2)。

    這個類只用於「**session 內**」拋出的 OperationalError——server 真的回過 error
    response,psycopg2 因而填得出 ``pgcode``(例:57P01 admin shutdown、53300 too many
    clients)。**連線期**的失敗形狀完全不同,見 :class:`_FakeConnectError`。
    """

    __module__ = "psycopg2"
    __qualname__ = "OperationalError"

    def __init__(self, message: str, pgcode: str | None = None) -> None:
        super().__init__(message)
        self.pgcode = pgcode
        self.diag = _FakeDiagnostics(pgcode)


_FakeOperationalError.__name__ = "OperationalError"


# 連線期 FATAL 的真實外形(psycopg2 2.9.12 + PostgreSQL 16 逐一觀察;真叢集見
# tests/structure/test_agent_governance_s2_4_consumer_resilience_disposable.py):
# libpq 在「連線建立」失敗時不回 PGresult,所以 pgcode / diag.sqlstate / pgerror 全 None,
# 只剩 server 的 FATAL 文本被包進這一行前綴裡。
_CONNECT_FAILURE_PREFIX = (
    'connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed: '
)


class _FakeConnectError(_FakeOperationalError):
    """連線期 psycopg2.OperationalError:``pgcode`` 恆為 None(不可注入)。

    舊 fixture 允許 ``pgcode="28P01"``,把一個**驅動不會發生**的形狀寫成 fixture 真理,
    於是 SQLSTATE 分流測試恆綠而 production 的 connect path 其實整條沒被修。此類刻意
    不接受 pgcode 參數,任何連線期分流只能靠訊息文本——與真驅動一致。
    """

    def __init__(self, fatal_message: str, *, with_prefix: bool = True) -> None:
        text = f"{_CONNECT_FAILURE_PREFIX}{fatal_message}\n" if with_prefix else fatal_message
        super().__init__(text, pgcode=None)


class _FakeProgrammingError(Exception):
    """模擬 psycopg2.ProgrammingError(42P01/42703/42501 家族的載體)。"""

    __module__ = "psycopg2"
    __qualname__ = "ProgrammingError"

    def __init__(self, message: str, pgcode: str | None = None) -> None:
        super().__init__(message)
        self.pgcode = pgcode


_FakeProgrammingError.__name__ = "ProgrammingError"


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
# F1(OPS):連線期失敗**沒有 SQLSTATE**——分流只能靠 libpq/PG 的逐字 FATAL 文本
# --------------------------------------------------------------------------- #
# 每一條都是 PG server 真的會送出的 FATAL(格式取自 auth.c / hba.c / postinit.c);
# 真叢集重放見 tests/structure/test_agent_governance_s2_4_consumer_resilience_disposable.py。
_PERMANENT_CONNECT_FATALS = (
    ("28P01", 'FATAL:  password authentication failed for user "aiml_engine_scanner"'),
    (
        "28000",
        'FATAL:  no pg_hba.conf entry for host "10.0.0.7", user "aiml_engine_scanner", '
        'database "trading_ai", no encryption',
    ),
    (
        "28000",
        'FATAL:  pg_hba.conf rejects connection for host "[local]", '
        'user "aiml_engine_scanner", database "trading_ai", no encryption',
    ),
    ("28000", 'FATAL:  Peer authentication failed for user "aiml_engine_scanner"'),
    ("28000", 'FATAL:  Ident authentication failed for user "aiml_engine_scanner"'),
    ("28000", 'FATAL:  "trust" authentication failed for user "aiml_engine_scanner"'),
    ("28000", 'FATAL:  role "aiml_engine_scanner" does not exist'),
    ("28000", 'FATAL:  role "aiml_engine_scanner" is not permitted to log in'),
    ("3D000", 'FATAL:  database "trading_ai" does not exist'),
)
# 真連線/可用性失敗(同樣 pgcode=None)——一條都不得被訊息指紋誤判為 permanent。
_TRANSIENT_CONNECT_FATALS = (
    "No such file or directory\n\tIs the server running locally and accepting "
    "connections on that socket?",
    "Connection refused\n\tIs the server running on that host and accepting "
    "TCP/IP connections?",
    "timeout expired",
    "server closed the connection unexpectedly\n\tThis probably means the server "
    "terminated abnormally before or while processing the request.",
    'could not translate host name "trade-core" to address: nodename nor servname provided',
    "FATAL:  the database system is starting up",
    "FATAL:  the database system is in recovery mode",
    "FATAL:  sorry, too many clients already",
    "FATAL:  terminating connection due to administrator command",
    'FATAL:  database "trading_ai" is not currently accepting connections',
)
# session 內拋出的 OperationalError:server 回過 error response,pgcode 才有值。
_TRANSIENT_SESSION_SQLSTATES = ("08006", "08001", "57P01", "57P03", "53300")


def test_connect_time_driver_shape_carries_no_sqlstate_at_all() -> None:
    """F1 的根事實:連線期 psycopg2 例外的 pgcode / diag.sqlstate 皆為 None。

    舊 fixture 直接注入 ``pgcode="28P01"``,把一個驅動不會產生的形狀寫成真理,測試因此
    全綠而 connect path 未被修。這條把「真驅動外形」釘進單元測試,disposable lane 再以
    真叢集複現同一形狀。
    """
    error = _FakeConnectError('FATAL:  password authentication failed for user "x"')
    assert error.pgcode is None
    assert error.diag.sqlstate is None
    assert resilience._db_error_sqlstate(error) is None  # 舊權威來源在此路徑上是空的
    # 但權威解析仍必須得到 SQLSTATE——否則就會落回 transient 無限重試。
    assert resilience.resolve_db_error_sqlstate(error) == "28P01"


@pytest.mark.parametrize("sqlstate,fatal", _PERMANENT_CONNECT_FATALS)
def test_auth_hba_and_missing_database_are_permanent_without_any_pgcode(
    sqlstate: str, fatal: str
) -> None:
    error = _FakeConnectError(fatal)
    assert error.pgcode is None  # 修前的 SQLSTATE 分流在此完全失效
    assert resilience.resolve_db_error_sqlstate(error) == sqlstate
    assert resilience.classify_db_error(error) == "permanent_config"
    # 修前:pgcode 缺席 → 落回型別分支 → transient → 每 300 秒重試到天荒地老。
    assert not resilience.is_transient_db_availability_error(error)
    typed = resilience.permanent_db_config_error(error)
    assert typed is not None and str(typed) == (
        f"{resilience.PERMANENT_DB_CONFIG_CODE_PREFIX}{sqlstate}"
    )
    # 該 typed code 必須真的落在 production 的 exit-78 面(否則等於沒修)。
    assert app_identity.is_permanent_pre_db_error(typed)


@pytest.mark.parametrize("fatal", _TRANSIENT_CONNECT_FATALS)
def test_genuine_connectivity_failures_stay_transient_without_pgcode(fatal: str) -> None:
    error = _FakeConnectError(fatal)
    assert error.pgcode is None
    assert resilience.resolve_db_error_sqlstate(error) is None
    assert resilience.classify_db_error(error) == "transient"
    assert resilience.is_transient_db_availability_error(error)
    assert resilience.permanent_db_config_error(error) is None


@pytest.mark.parametrize("sqlstate", _TRANSIENT_SESSION_SQLSTATES)
def test_self_healing_session_sqlstates_stay_transient(sqlstate: str) -> None:
    error = _FakeOperationalError("connection failure", pgcode=sqlstate)
    assert resilience.classify_db_error(error) == "transient"
    assert resilience.permanent_db_config_error(error) is None


@pytest.mark.parametrize(
    "sqlstate", ("0P000", "3F000", "42704", "28000", "28P01", "42501")
)
def test_permanent_sqlstates_are_still_honoured_when_the_driver_supplies_them(
    sqlstate: str,
) -> None:
    """session 內(pgcode 有值)的 permanent 分流不得因 F1 的訊息回填而退化。"""
    error = _FakeOperationalError("driver-supplied", pgcode=sqlstate)
    assert resilience.resolve_db_error_sqlstate(error) == sqlstate
    assert resilience.classify_db_error(error) == "permanent_config"


def test_message_fingerprint_never_fires_on_a_non_driver_exception() -> None:
    """訊息回填只對連線型驅動例外生效;任意例外不得因文字巧合被判 permanent。"""
    impostor = ValueError('password authentication failed for user "aiml_engine_scanner"')
    assert resilience.resolve_db_error_sqlstate(impostor) is None
    assert resilience.classify_db_error(impostor) == "unclassified"
    assert resilience.permanent_db_config_error(impostor) is None


def test_permanent_sqlstate_stops_the_resident_loop_with_a_typed_78_error() -> None:
    """方向一:認證失敗 → 迴圈不重試,轉 typed permanent(production main → 78)。"""
    slept: list[float] = []

    def open_connection() -> str:
        raise _FakeConnectError(
            'FATAL:  password authentication failed for user "aiml_engine_scanner"'
        )

    with pytest.raises(resilience.AlrPermanentDbConfigError) as failure:
        resilience.run_resident_db_sessions(
            open_connection=open_connection,
            run_session=lambda connection: {"drains": 0},
            close_connection=lambda connection: None,
            should_stop=lambda: False,
            sleep=slept.append,
            jitter=lambda: 0.0,
        )
    assert str(failure.value) == "db_config_permanent_sqlstate_28P01"
    assert slept == []  # 零退避、零重試:operator 立刻拿到 exit 78
    assert app_identity.is_permanent_pre_db_error(failure.value)
    assert isinstance(failure.value, AlrEventConsumerError)  # main 捕捉得到


def test_transient_outage_still_never_exits_the_resident_loop() -> None:
    """方向二:無 SQLSTATE 的真停機仍是 §8.3 的「不得退出」——有界重試後恢復。"""
    slept: list[float] = []
    outage = {"remaining": 3}

    def open_connection() -> str:
        if outage["remaining"] > 0:
            outage["remaining"] -= 1
            raise _FakeConnectError("Connection refused")
        return "conn"

    outcome = resilience.run_resident_db_sessions(
        open_connection=open_connection,
        run_session=lambda connection: {"drains": 1},
        close_connection=lambda connection: None,
        should_stop=lambda: False,
        sleep=slept.append,
        jitter=lambda: 1.0,
    )
    assert outcome["status"] == "SESSION_COMPLETED"
    assert slept == [5.0, 10.0, 20.0]


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
        "connections_opened",
        "lock_busy_reconnect_retries",
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
    """E2 P3-a:退避等待返回後必須**先**檢查停機訊號,不得多做一次連線嘗試。

    修前:sleep 內設下的 SIGTERM 要等到下一輪 ``open_connection()`` 失敗後才被看到
    (transient_failures==2);DB 若剛好在此刻恢復,還會跑完一整個 session,直接威脅
    ``TimeoutStopSec=30s``。修後:恰好一次嘗試即乾淨停機。
    """
    stop = {"set": False}
    attempts = {"count": 0}
    recovered_sessions: list[str] = []

    def open_connection() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise _FakeOperationalError("down")
        return "conn"  # 模擬退避期間 DB 已恢復:多一次嘗試就會跑完整個 session

    def sleep(seconds: float) -> None:
        stop["set"] = True  # 模擬退避等待期間收到 SIGTERM

    outcome = resilience.run_resident_db_sessions(
        open_connection=open_connection,
        run_session=lambda connection: recovered_sessions.append(connection) or {},
        close_connection=lambda connection: None,
        should_stop=lambda: stop["set"],
        sleep=sleep,
        jitter=lambda: 0.0,
    )
    assert outcome["status"] == "STOPPED_DURING_DB_OUTAGE"
    assert outcome["result"] is None
    assert outcome["telemetry"]["transient_failures"] == 1
    assert attempts["count"] == 1  # 停機訊號後零額外連線嘗試
    assert recovered_sessions == []  # 且絕不在停機路徑上再跑一個 session


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
# E2 P2-C:首連 lock-busy = 真第二實例(上拋);重連 lock-busy = 自己殘留 backend
# (有界退避)。分割變體不得把單元燒成 §8.3 禁止的永久 failed。
# --------------------------------------------------------------------------- #
def test_lock_busy_on_first_connect_is_still_raised_not_retried() -> None:
    """首連即佔用 = 另一個實例真的在跑;維持原行為(上拋、零退避)。"""
    slept: list[float] = []
    state = resilience.ResidentConsumerState()

    with pytest.raises(AlrEventConsumerError, match="single_instance_lock_busy"):
        resilience.run_resident_db_sessions(
            open_connection=lambda: "conn",
            run_session=lambda connection: (_ for _ in ()).throw(
                AlrEventConsumerError("single_instance_lock_busy")
            ),
            close_connection=lambda connection: None,
            should_stop=lambda: False,
            sleep=slept.append,
            jitter=lambda: 0.0,
            state=state,
        )
    assert slept == []
    assert state.lock_busy_reconnect_retries == 0


def test_lock_busy_after_a_reconnect_goes_through_bounded_backoff() -> None:
    """分割後重連撞到自己 server 側殘留的 advisory lock → 有界退避,不得崩潰。

    修前:第二次連線的 lock-busy 直接上拋 → 行程崩潰 → 300s 內三次即
    ``StartLimitBurst`` 耗盡 → 單元永久 failed(§8.3 禁止的結果之分割變體)。
    """
    slept: list[float] = []
    attempts = {"count": 0}
    state = resilience.ResidentConsumerState()

    def run_session(connection: str) -> dict[str, int]:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise _FakeOperationalError("server closed the connection unexpectedly")
        if attempts["count"] <= 3:
            # 我們自己上一條 backend 尚未被 server 回收,advisory lock 還在它手上
            raise AlrEventConsumerError("single_instance_lock_busy")
        return {"drains": 1}

    outcome = resilience.run_resident_db_sessions(
        open_connection=lambda: "conn",
        run_session=run_session,
        close_connection=lambda connection: None,
        should_stop=lambda: False,
        sleep=slept.append,
        jitter=lambda: 1.0,
        state=state,
    )
    assert outcome["status"] == "SESSION_COMPLETED"
    # 一次 transient + 兩次 lock-busy 重連 → 三段有界退避,全落在 [5,300]
    assert slept == [5.0, 10.0, 20.0]
    assert all(5.0 <= value <= 300.0 for value in slept)
    assert state.transient_failures == 1
    assert state.lock_busy_reconnect_retries == 2
    assert outcome["telemetry"]["lock_busy_reconnect_retries"] == 2


def test_lock_busy_predicate_matches_the_code_the_consumer_actually_raises() -> None:
    """防漂移:謂詞比對的字串必須就是 consumer 那一行 raise 的 typed code。"""
    source = (
        ROOT / "program_code/ml_training/alr_event_consumer.py"
    ).read_text(encoding="utf-8")
    assert (
        f'raise AlrEventConsumerError("{resilience.SINGLE_INSTANCE_LOCK_BUSY_CODE}")'
        in source
    )
    assert resilience.is_single_instance_lock_busy(
        AlrEventConsumerError(resilience.SINGLE_INSTANCE_LOCK_BUSY_CODE)
    )
    assert not resilience.is_single_instance_lock_busy(
        AlrEventConsumerError("runtime_file_lock_busy")
    )


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


# --------------------------------------------------------------------------- #
# E2 P2-B:身分關聯缺席/欄位不符 → 與「零列」同一條 permanent 路徑(78),不得崩潰迴圈
# --------------------------------------------------------------------------- #
class _RaisingIdentityConnection(_IdentityConnection):
    """對指定 SQL 拋出真實形狀的 psycopg2 錯誤(其餘照常回應)。"""

    def __init__(self, *, needle: str, error: BaseException) -> None:
        super().__init__()
        self._needle = needle
        self._error = error

    def cursor(self):
        connection = self
        base = super().cursor()

        class _Cursor:
            def __enter__(self):
                base.__enter__()
                return self

            def __exit__(self, *args):
                return False

            def execute(self, sql, params=None):
                if connection._needle in sql:
                    raise connection._error
                base.execute(sql, params)

            def fetchall(self):
                return base.fetchall()

        return _Cursor()


@pytest.mark.parametrize(
    "sqlstate,message",
    [
        ("42P01", 'relation "learning.alr_runtime_cluster_identity_v1" does not exist'),
        ("42703", 'column "binding_nonce" does not exist'),
        ("42501", "permission denied for table alr_runtime_cluster_identity_v1"),
    ],
)
def test_absent_or_misshapen_identity_relation_is_permanent_not_a_crash_loop(
    tmp_path: Path, sqlstate: str, message: str
) -> None:
    """修前:ProgrammingError 逸出 consumer 的 AlrEventConsumerError 捕捉面 → exit 1
    → ``Restart=on-failure`` 把 start limit 燒成永久 failed 單元。修後:typed → 78。
    """
    guard_path = _write_guard(tmp_path)
    connection = _RaisingIdentityConnection(
        needle="alr_runtime_cluster_identity_v1",
        error=_FakeProgrammingError(message, pgcode=sqlstate),
    )
    with pytest.raises(
        resilience.AlrRuntimeIdentityError,
        match="cluster_identity_relation_unavailable",
    ) as failure:
        resilience.verify_connected_cluster_identity(
            connection, topology_guard_file=guard_path, dsn_identity=_DSN_IDENTITY
        )
    # 與零列同一條 permanent 出口,且讀交易不被留下
    assert app_identity.is_permanent_pre_db_error(failure.value)
    assert isinstance(failure.value, AlrEventConsumerError)
    assert connection.rollbacks == 1


def test_identity_read_transient_failure_is_not_masked_as_permanent(
    tmp_path: Path,
) -> None:
    """反向防呆:身分讀取途中的真連線中斷仍是 transient(否則永不重連)。"""
    guard_path = _write_guard(tmp_path)
    connection = _RaisingIdentityConnection(
        needle="alr_runtime_cluster_identity_v1",
        error=_FakeOperationalError("server closed the connection unexpectedly"),
    )
    with pytest.raises(_FakeOperationalError):
        resilience.verify_connected_cluster_identity(
            connection, topology_guard_file=guard_path, dsn_identity=_DSN_IDENTITY
        )


def test_connected_identity_relation_failure_is_also_permanent(tmp_path: Path) -> None:
    """connected-identity 那條 SELECT 同樣不得逸出成未捕捉例外。"""
    guard_path = _write_guard(tmp_path)
    connection = _RaisingIdentityConnection(
        needle="current_database",
        error=_FakeProgrammingError("function does not exist", pgcode="42883"),
    )
    with pytest.raises(
        resilience.AlrRuntimeIdentityError,
        match="cluster_identity_relation_unavailable",
    ):
        resilience.verify_connected_cluster_identity(
            connection, topology_guard_file=guard_path, dsn_identity=_DSN_IDENTITY
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
        "runtime_file_lock_unavailable_ENOSPC",
        "candidate_board_directory_unavailable",
    ):
        assert not app_identity.is_permanent_pre_db_error(AlrEventConsumerError(code)), code
    assert app_identity.EX_CONFIG_EXIT_CODE == 78
    # E2 P2-A/P2-B + F1/F2/F5:所有 permanent 出口(含帶 SQLSTATE/關聯後綴者)落在 78 面。
    for code in (
        "db_config_permanent_sqlstate_28P01",
        "db_config_permanent_sqlstate_3D000",
        "db_config_permanent_sqlstate_42P01_relation_learning.alr_consumer_events",
        "db_config_permanent_sqlstate_42703_relation_binding_nonce",
        "db_config_permanent_sqlstate_42501_relation_alr_health_events",
        "cluster_identity_relation_unavailable",
        "cluster_identity_relation_unavailable_42P01_relation_learning.alr_x",
        "runtime_file_lock_denied_EACCES",
    ):
        assert app_identity.is_permanent_pre_db_error(AlrEventConsumerError(code)), code


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


class _WiringLock:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


def _wire_production_consumer(monkeypatch: pytest.MonkeyPatch, *, connect) -> None:
    """把 run_event_consumer 的 host 面全部替身化,只留下要驗的重連分流。"""
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
    monkeypatch.setattr(consumer, "runtime_file_lock", lambda path: _WiringLock())
    monkeypatch.setattr(consumer, "_connect_listener", connect)
    monkeypatch.setattr(consumer, "release_single_instance", lambda connection: None)
    monkeypatch.setattr(consumer, "new_session_id", lambda: "session-0")
    monkeypatch.setattr(
        consumer, "start_consumer_session", lambda connection, session_id: None
    )
    monkeypatch.setattr(
        consumer, "stop_consumer_session", lambda connection, session_id: None
    )


def _production_main_exit_code(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, run_consumer
) -> int:
    """以 production ABI(--application-root)跑 main,回傳其 exit code。"""
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
    return consumer.main(
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


def test_wired_auth_failure_exits_78_instead_of_retrying_every_300s(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """F1 端到端:psycopg2.connect 的認證失敗(**pgcode=None**)→ main exit 78。

    修前:連線期沒有 pgcode → 分流落回型別 → transient → 每 300 秒重試,單元恆 active、
    永遠不蒐集、operator 永遠等不到 78。
    """
    guard_path = _write_guard(tmp_path)
    attempts = {"count": 0}

    def connect(dsn: str):
        attempts["count"] += 1
        raise _FakeConnectError(
            'FATAL:  password authentication failed for user "aiml_engine_scanner"'
        )

    _wire_production_consumer(monkeypatch, connect=connect)
    real_run_event_consumer = consumer.run_event_consumer

    def run_consumer() -> None:
        real_run_event_consumer(
            dsn_path=tmp_path / "dsn",
            lock_path=tmp_path / "lock",
            max_batch=8,
            source_head="a" * 40,
            topology_guard_file=guard_path,
            dsn_required_identity=_DSN_IDENTITY,
            reconnect_sleep=lambda seconds: pytest.fail(
                "auth failure must never enter the 300s retry loop"
            ),
        )

    with pytest.raises(resilience.AlrPermanentDbConfigError):
        run_consumer()
    assert attempts["count"] == 1

    attempts["count"] = 0
    assert _production_main_exit_code(monkeypatch, tmp_path, run_consumer) == 78


def test_wired_missing_identity_relation_exits_78_instead_of_crash_looping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E2 P2-B 端到端:身分關聯不存在(42P01)→ main exit 78(不是未捕捉 → exit 1)。"""
    guard_path = _write_guard(tmp_path)

    def connect(dsn: str):
        return _RaisingIdentityConnection(
            needle="alr_runtime_cluster_identity_v1",
            error=_FakeProgrammingError(
                'relation "learning.alr_runtime_cluster_identity_v1" does not exist',
                pgcode="42P01",
            ),
        )

    _wire_production_consumer(monkeypatch, connect=connect)
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
            reconnect_sleep=lambda seconds: pytest.fail("permanent must not be retried"),
        )

    with pytest.raises(
        resilience.AlrRuntimeIdentityError, match="cluster_identity_relation_unavailable"
    ):
        run_consumer()
    assert _production_main_exit_code(monkeypatch, tmp_path, run_consumer) == 78


def test_wired_reconnect_lock_busy_backs_off_instead_of_burning_the_start_limit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E2 P2-C 端到端:分割後重連撞到自己的 advisory lock → 有界退避 → 恢復收集。"""
    guard_path = _write_guard(tmp_path)
    slept: list[float] = []
    opens = {"count": 0}
    acquisitions = {"count": 0}

    def connect(dsn: str):
        opens["count"] += 1
        return _IdentityConnection()

    def acquire(connection) -> bool:
        acquisitions["count"] += 1
        # 第 2 次:我們自己上一條 backend 還握著 server 側的 advisory lock
        return acquisitions["count"] != 2

    def loop(connection, **kwargs):
        if acquisitions["count"] == 1:
            raise _FakeOperationalError("server closed the connection unexpectedly")
        return {"drains": 1, "rows_seen": 7}

    _wire_production_consumer(monkeypatch, connect=connect)
    monkeypatch.setattr(consumer, "acquire_single_instance", acquire)
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
    # 修前:第 2 次連線的 lock-busy 直接崩潰(300s 內三次 → 單元永久 failed)
    assert result["rows_seen"] == 7
    assert slept == [5.0, 10.0]
    assert opens["count"] == 3


# --------------------------------------------------------------------------- #
# F2:crash-loop 類必須對「整個 session」關閉,不只兩條身分讀取
# --------------------------------------------------------------------------- #
# 這三碼在 ACL manifest 的其餘 12 個關聯上一樣會發生(migration 落後、GRANT 漏一張表、
# 欄位改名)。修前它們是裸 psycopg2 例外 → 逸出 main 的 except → exit 1 →
# Restart=on-failure 在 300 秒內燒掉 StartLimitBurst=3 → 單元永久 failed。
_SESSION_SCHEMA_FAILURES = (
    (
        "42P01",
        'relation "learning.alr_consumer_events" does not exist',
        "learning.alr_consumer_events",
    ),
    ("42703", 'column "binding_nonce" does not exist', "binding_nonce"),
    (
        "42501",
        "permission denied for table alr_health_events",
        "alr_health_events",
    ),
)


@pytest.mark.parametrize("sqlstate,message,subject", _SESSION_SCHEMA_FAILURES)
def test_schema_contract_failure_anywhere_in_the_session_is_typed_permanent(
    sqlstate: str, message: str, subject: str
) -> None:
    error = _FakeProgrammingError(message, pgcode=sqlstate)
    assert resilience.classify_db_error(error) == "permanent_config"
    typed = resilience.permanent_db_config_error(error)
    assert typed is not None
    # 診斷面:SQLSTATE 與關聯名都在 code 裡(舊版三碼全壓成同一個無資訊字串)。
    assert str(typed) == (
        f"{resilience.PERMANENT_DB_CONFIG_CODE_PREFIX}{sqlstate}"
        f"{resilience.DB_ERROR_SUBJECT_INFIX}{subject}"
    )
    assert isinstance(typed, AlrEventConsumerError)  # main 捕捉得到
    assert app_identity.is_permanent_pre_db_error(typed)


@pytest.mark.parametrize("sqlstate,message,subject", _SESSION_SCHEMA_FAILURES)
def test_non_identity_relation_failure_does_not_escape_the_resident_loop(
    sqlstate: str, message: str, subject: str
) -> None:
    """修前:run_session 內的 42P01/42703 原樣上拋 → 未捕捉 → exit 1 → 崩潰迴圈。"""
    slept: list[float] = []

    def run_session(connection: str) -> dict[str, int]:
        raise _FakeProgrammingError(message, pgcode=sqlstate)

    with pytest.raises(resilience.AlrPermanentDbConfigError) as failure:
        resilience.run_resident_db_sessions(
            open_connection=lambda: "conn",
            run_session=run_session,
            close_connection=lambda connection: None,
            should_stop=lambda: False,
            sleep=slept.append,
            jitter=lambda: 0.0,
        )
    assert sqlstate in str(failure.value) and subject in str(failure.value)
    assert slept == []  # permanent:零退避、零重試
    assert app_identity.is_permanent_pre_db_error(failure.value)


def test_identity_relation_failure_codes_distinguish_the_three_sqlstates(
    tmp_path: Path,
) -> None:
    """F2 診斷回歸:身分路徑不得再把 42P01/42703/42501 壓成同一個碼。"""
    guard_path = _write_guard(tmp_path)
    seen: set[str] = set()
    for sqlstate, message, subject in (
        (
            "42P01",
            'relation "learning.alr_runtime_cluster_identity_v1" does not exist',
            "learning.alr_runtime_cluster_identity_v1",
        ),
        ("42703", 'column "binding_nonce" does not exist', "binding_nonce"),
        (
            "42501",
            "permission denied for table alr_runtime_cluster_identity_v1",
            "alr_runtime_cluster_identity_v1",
        ),
    ):
        connection = _RaisingIdentityConnection(
            needle="alr_runtime_cluster_identity_v1",
            error=_FakeProgrammingError(message, pgcode=sqlstate),
        )
        with pytest.raises(resilience.AlrRuntimeIdentityError) as failure:
            resilience.verify_connected_cluster_identity(
                connection, topology_guard_file=guard_path, dsn_identity=_DSN_IDENTITY
            )
        code = str(failure.value)
        assert code == (
            f"{resilience.CLUSTER_IDENTITY_RELATION_UNAVAILABLE_CODE}_{sqlstate}"
            f"{resilience.DB_ERROR_SUBJECT_INFIX}{subject}"
        )
        assert app_identity.is_permanent_pre_db_error(failure.value)
        seen.add(code)
    assert len(seen) == 3  # 三碼互異(修前:三者相同)


def test_db_error_subject_is_sanitised_and_bounded() -> None:
    """關聯名進 typed code 前必須消毒:只留識別字字元、長度有界。"""
    hostile = _FakeProgrammingError(
        'relation "learning.evil\nname; DROP" does not exist', pgcode="42P01"
    )
    subject = resilience.db_error_subject(hostile)
    assert subject is not None
    assert re.fullmatch(r"[A-Za-z0-9_.$]+", subject)
    assert len(subject) <= 64
    long_name = _FakeProgrammingError(
        'relation "' + "a" * 100 + '" does not exist', pgcode="42P01"
    )
    assert len(resilience.db_error_subject(long_name)) == 64
    assert resilience.db_error_subject(_FakeConnectError("Connection refused")) is None


# --------------------------------------------------------------------------- #
# F6:失敗路徑的 rollback 不得把 permanent 身分失敗降級成 transient
# --------------------------------------------------------------------------- #
class _FakeInterfaceError(Exception):
    """psycopg2.InterfaceError(連線已死):classify 為 transient。"""

    __module__ = "psycopg2"
    __qualname__ = "InterfaceError"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.pgcode = None
        self.diag = _FakeDiagnostics(None)


_FakeInterfaceError.__name__ = "InterfaceError"


class _DeadRollbackConnection(_IdentityConnection):
    """身分讀完後連線已死:rollback 自己會拋 InterfaceError。"""

    def rollback(self) -> None:
        self.rollbacks += 1
        raise _FakeInterfaceError("connection already closed")


def test_failing_rollback_never_downgrades_a_permanent_identity_mismatch(
    tmp_path: Path,
) -> None:
    """修前:``finally: rollback()`` 的 InterfaceError 取代了 in-flight 的身分不符。

    後果最嚴重:permanent(→78)被讀成 transient(→ 無限重連),連上的是**錯誤叢集**
    卻永遠不停下。此處驗 in-flight 原因原樣保留、且 rollback 真的被嘗試過。
    """
    guard_path = _write_guard(tmp_path)
    connection = _DeadRollbackConnection(
        connected={
            "connected_user": "aiml_engine_scanner",
            "connected_database": "postgres",  # 身分不符 → permanent
            "server_version_num": "160004",
        }
    )
    with pytest.raises(
        resilience.AlrRuntimeIdentityError, match="cluster_identity_database_mismatch"
    ) as failure:
        resilience.verify_connected_cluster_identity(
            connection, topology_guard_file=guard_path, dsn_identity=_DSN_IDENTITY
        )
    assert connection.rollbacks == 1  # 仍盡力 rollback
    assert app_identity.is_permanent_pre_db_error(failure.value)
    assert not resilience.is_transient_db_availability_error(failure.value)


def test_rollback_failure_on_the_success_path_still_surfaces_as_transient(
    tmp_path: Path,
) -> None:
    """成功路徑上的 rollback 失敗刻意保持上拋:連線已壞,transient 重連才是對的。"""
    guard_path = _write_guard(tmp_path)
    connection = _DeadRollbackConnection()
    with pytest.raises(_FakeInterfaceError):
        resilience.verify_connected_cluster_identity(
            connection, topology_guard_file=guard_path, dsn_identity=_DSN_IDENTITY
        )
    assert resilience.is_transient_db_availability_error(_FakeInterfaceError("x"))


# --------------------------------------------------------------------------- #
# F5:runtime_file_lock 的 os.open 失敗必須 typed,不得以 exit 1 裸奔
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "error_number,expected_code,permanent",
    [
        (errno.EACCES, "runtime_file_lock_denied_EACCES", True),
        (errno.EPERM, "runtime_file_lock_denied_EPERM", True),
        (errno.EROFS, "runtime_file_lock_denied_EROFS", True),
        (errno.ELOOP, "runtime_file_lock_denied_ELOOP", True),
        (errno.ENOSPC, "runtime_file_lock_unavailable_ENOSPC", False),
        (errno.EMFILE, "runtime_file_lock_unavailable_EMFILE", False),
    ],
)
def test_lock_open_oserrors_become_typed_codes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_number: int,
    expected_code: str,
    permanent: bool,
) -> None:
    """修前:只有 BlockingIOError 被轉 typed;其餘 OSError 直接逸出 → exit 1 + traceback。"""

    def hostile_open(path, flags, mode=0o777):
        raise OSError(error_number, os.strerror(error_number))

    monkeypatch.setattr(consumer.os, "open", hostile_open)
    with pytest.raises(AlrEventConsumerError) as failure:
        with consumer.runtime_file_lock(tmp_path / "sub" / "consumer.lock"):
            pytest.fail("lock must not be acquired")
    assert str(failure.value) == expected_code
    # permanent 類(部署/組態錯)→ 78 停下等 operator;資源耗盡類刻意留在列外(可自癒)。
    assert app_identity.is_permanent_pre_db_error(failure.value) is permanent


def test_lock_busy_and_unsupported_paths_are_unchanged(tmp_path: Path) -> None:
    """既有兩條 typed 出口不得被 F5 改動(lock-busy 仍非 permanent)。"""
    lock_path = tmp_path / "consumer.lock"
    with consumer.runtime_file_lock(lock_path):
        with pytest.raises(AlrEventConsumerError, match="runtime_file_lock_busy"):
            with consumer.runtime_file_lock(lock_path):
                pytest.fail("second holder must be refused")
    assert not app_identity.is_permanent_pre_db_error(
        AlrEventConsumerError("runtime_file_lock_busy")
    )


# --------------------------------------------------------------------------- #
# D2:liveness/staleness 契約(source-only 宣告;零 runtime 接觸)
# --------------------------------------------------------------------------- #
def test_consumer_liveness_contract_is_bound_to_the_real_heartbeat_default() -> None:
    """契約的 heartbeat 週期必須就是 persist_health_snapshot 的預設值(漂移即紅)。"""
    from ml_training.alr_health_repository import persist_health_snapshot

    default = inspect.signature(persist_health_snapshot).parameters[
        "heartbeat_seconds"
    ].default
    assert default == resilience.CONSUMER_HEARTBEAT_INTERVAL_SECONDS

    contract = resilience.derive_consumer_liveness_contract()
    assert contract["schema_version"] == "alr_consumer_liveness_contract_v1"
    assert contract["health_relation"] == "learning.alr_health_events"
    assert contract["heartbeat_interval_seconds"] == default
    assert contract["staleness_threshold_seconds"] == (
        default * contract["missed_heartbeats_before_stale"]
    )
    # 契約必須明講「active 不是活著」——否則 postcheck 又會退回 ActiveState。
    assert "systemd ActiveState=active" in contract["insufficient_signals"]
    assert contract["runtime_contact"] is False
    # 該關聯真的是 consumer 寫 heartbeat 的那一張表(防止契約指向不存在的 lane)。
    repository_source = (
        ROOT / "program_code/ml_training/alr_health_repository.py"
    ).read_text(encoding="utf-8")
    assert f"INSERT INTO {contract['health_relation']} " in repository_source


def test_consumer_liveness_verdicts_fail_closed_on_missing_evidence() -> None:
    threshold = resilience.CONSUMER_LIVENESS_STALENESS_SECONDS
    assert resilience.classify_consumer_liveness(0) == "LIVE"
    assert resilience.classify_consumer_liveness(threshold) == "LIVE"
    assert resilience.classify_consumer_liveness(threshold + 0.001) == "STALE"
    # 查不到 heartbeat 年齡 ≠ 活著:postcheck 必須拿到 UNKNOWN 而非 LIVE。
    for missing in (None, "", -1, float("nan"), True):
        assert resilience.classify_consumer_liveness(missing) == "UNKNOWN", missing


def test_wired_non_identity_relation_failure_exits_78_instead_of_crash_looping(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """F2 端到端:身分閘通過後,drain 打到缺席的 alr_consumer_events(42P01)。

    修前:裸 psycopg2.ProgrammingError 逸出 main 的 ``except AlrEventConsumerError``
    → exit 1 → ``Restart=on-failure`` 三次燒光 ``StartLimitBurst`` → 單元永久 failed。
    """
    guard_path = _write_guard(tmp_path)

    def connect(dsn: str):
        return _IdentityConnection()

    def loop(connection, **kwargs):
        raise _FakeProgrammingError(
            'relation "learning.alr_consumer_events" does not exist', pgcode="42P01"
        )

    _wire_production_consumer(monkeypatch, connect=connect)
    monkeypatch.setattr(consumer, "acquire_single_instance", lambda connection: True)
    monkeypatch.setattr(consumer, "event_consumer_loop", loop)

    real_run_event_consumer = consumer.run_event_consumer

    def run_consumer() -> None:
        real_run_event_consumer(
            dsn_path=tmp_path / "dsn",
            lock_path=tmp_path / "lock",
            max_batch=8,
            source_head="a" * 40,
            topology_guard_file=guard_path,
            dsn_required_identity=_DSN_IDENTITY,
            reconnect_sleep=lambda seconds: pytest.fail("permanent must not be retried"),
        )

    with pytest.raises(resilience.AlrPermanentDbConfigError) as failure:
        run_consumer()
    assert str(failure.value) == (
        "db_config_permanent_sqlstate_42P01_relation_learning.alr_consumer_events"
    )
    assert _production_main_exit_code(monkeypatch, tmp_path, run_consumer) == 78

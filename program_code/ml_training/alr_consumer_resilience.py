"""S2.4 §8.3 常駐 consumer 的「不退出重連」韌性與在帶(in-band)叢集身分驗證葉模組。

§8.3 規範(normative):permanent 的 pre-DB 組態/身分/憑證格式失敗 exit 78;但**transient
的 attested-DB 可用性失敗不得退出**——常駐 consumer 必須關閉失敗連線、保留 durable cursor
語義,並以「有界指數退避 + jitter」(最小 5 秒、最大 300 秒)無限重試,且不累積 task/row/
記憶體。如此 systemd 的 ``StartLimitIntervalSec=300s`` / ``StartLimitBurst=3`` 只保護真正的
行程崩潰迴圈,長時間 DB 停機不會耗盡 start limit、也不會永久停止自主蒐集。

重連時必須:載入並自我 digest 不可變 topology guard → 比對連上的 user/database/endpoint
→ 比對 ``learning.alr_runtime_cluster_identity_v1`` 的**那一列**;任何不符即 typed 失敗
(consumer 於 production 模式以 exit 78 收場)。這是可執行的**在帶**叢集身分檢查,並不宣稱
無特權 consumer 能檢視 host 的 listener/proxy 行程。

硬邊界:本模組零 effect、零 authority、零重試「寫入」——它只重試「建立 session」;
durable cursor 一律留在 DB 側(``learning.alr_consumer_events`` lane cursor),重連後由
既有 drain 路徑自該 cursor 續讀,故不需要、也不會在行程內保留任何跨 session 進度狀態。
facade 依 2000 行治理拆分規約「只」經 schema_core.resolve_facade() 取得。
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Callable, Mapping

from ml_training.aiml_gate_receipt_schema_core import resolve_facade
from ml_training.alr_candidate_board_events import AlrEventConsumerError
from ml_training.alr_application_identity import (
    AlrApplicationIdentityError,
    verify_topology_guard,
)

# §8.3:退避值域硬邊界(jitter 後仍必須落在 [5,300])。
RECONNECT_MIN_BACKOFF_SECONDS = 5.0
RECONNECT_MAX_BACKOFF_SECONDS = 300.0
_BACKOFF_BASE = 2.0
# 2**32 已遠超 300s 天花板;夾住指數避免 float overflow(長時間停機下 n 可以很大)。
_BACKOFF_MAX_EXPONENT = 32

# §8.2/§8.3:admin-owned、scanner-read-only 的叢集身分列(唯一在帶身分來源)。
# 註:此關聯由 W6B 的 PG migration 建立/驗證;source 面只綁其名稱與封閉欄位契約。
CLUSTER_IDENTITY_RELATION = "learning.alr_runtime_cluster_identity_v1"
CLUSTER_IDENTITY_COLUMNS = (
    "system_identifier",
    "database_oid",
    "server_major_version",
    "runtime_host",
    "runtime_port",
    "runtime_dbname",
    "binding_nonce",
)
# 靜態 SQL(module 常量:engine-scanner SQL inventory 可靜態解析並導出 SELECT 權限)。
_CLUSTER_IDENTITY_SQL = (
    "SELECT system_identifier, database_oid, server_major_version, runtime_host, "
    "runtime_port, runtime_dbname, binding_nonce "
    "FROM learning.alr_runtime_cluster_identity_v1"
)
_CONNECTED_IDENTITY_SQL = (
    "SELECT current_user AS connected_user, current_database() AS connected_database, "
    "current_setting('server_version_num') AS server_version_num"
)
# transient = 連線/可用性類(psycopg2 的 OperationalError/InterfaceError 及其子類);
# 其餘一律非 transient(真崩潰迴圈交給 systemd start limit)。以型別全名比對,避免在
# 無 psycopg2 的開發環境 import 失敗。
_TRANSIENT_DB_ERROR_TYPES = frozenset({
    "psycopg2.OperationalError",
    "psycopg2.InterfaceError",
})


class AlrRuntimeIdentityError(AlrEventConsumerError):
    """§8.3 重連身分不符:permanent、不可重試(production → exit 78)。"""


class ResidentConsumerState:
    """常駐重連的**有界**狀態:只有固定數量的純量計數,永不累積 task/row/物件。"""

    __slots__ = (
        "sessions_completed",
        "transient_failures",
        "consecutive_failures",
        "last_backoff_seconds",
        "total_backoff_seconds",
    )

    def __init__(self) -> None:
        self.sessions_completed = 0
        self.transient_failures = 0
        self.consecutive_failures = 0
        self.last_backoff_seconds = 0.0
        self.total_backoff_seconds = 0.0

    def record_transient_failure(self) -> None:
        self.transient_failures += 1
        self.consecutive_failures += 1

    def record_backoff(self, delay_seconds: float) -> None:
        self.last_backoff_seconds = float(delay_seconds)
        self.total_backoff_seconds += float(delay_seconds)

    def record_session_completed(self) -> None:
        self.sessions_completed += 1
        self.consecutive_failures = 0

    def telemetry(self) -> dict[str, float]:
        return {
            "schema_version": "alr_resident_reconnect_telemetry_v1",
            "sessions_completed": self.sessions_completed,
            "transient_failures": self.transient_failures,
            "consecutive_failures": self.consecutive_failures,
            "last_backoff_seconds": self.last_backoff_seconds,
            "total_backoff_seconds": self.total_backoff_seconds,
        }


def default_jitter() -> float:
    """預設 jitter 來源:[0,1) 均勻分數(測試以確定性注入取代)。"""
    return random.random()


def next_backoff_seconds(consecutive_failures: int, *, jitter: float) -> float:
    """§8.3 有界指數退避 + jitter;回傳值恆落在 [5.0, 300.0]。

    ceiling = min(300, 5 * 2**(n-1));delay = 5 + jitter*(ceiling-5)。jitter 由外部注入
    (production 用 :func:`default_jitter`,測試注入確定值),使序列可完全重放。
    """
    if (
        isinstance(consecutive_failures, bool)
        or not isinstance(consecutive_failures, int)
        or consecutive_failures < 1
    ):
        raise AlrEventConsumerError("reconnect_backoff_attempt_invalid")
    if (
        isinstance(jitter, bool)
        or not isinstance(jitter, (int, float))
        or not 0.0 <= float(jitter) <= 1.0
    ):
        raise AlrEventConsumerError("reconnect_backoff_jitter_invalid")
    exponent = min(consecutive_failures - 1, _BACKOFF_MAX_EXPONENT)
    ceiling = min(
        RECONNECT_MAX_BACKOFF_SECONDS,
        RECONNECT_MIN_BACKOFF_SECONDS * (_BACKOFF_BASE ** exponent),
    )
    delay = RECONNECT_MIN_BACKOFF_SECONDS + float(jitter) * (
        ceiling - RECONNECT_MIN_BACKOFF_SECONDS
    )
    return min(RECONNECT_MAX_BACKOFF_SECONDS, max(RECONNECT_MIN_BACKOFF_SECONDS, delay))


def is_transient_db_availability_error(error: BaseException) -> bool:
    """是否為 §8.3 的 transient DB 可用性失敗(唯一可重試類)。"""
    if isinstance(error, AlrEventConsumerError):
        return False  # typed consumer 失敗一律非 transient(含身分不符與單例佔用)
    for klass in type(error).__mro__:
        if f"{klass.__module__}.{klass.__qualname__}" in _TRANSIENT_DB_ERROR_TYPES:
            return True
    return False


def _row_value(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row[key]
    return row[index]


def _single_identity_row(rows: Any, columns: tuple[str, ...]) -> dict[str, Any]:
    """取唯一一條身分列;缺列/多列/欄位形狀不符一律 typed fail-closed(絕不猜)。"""
    if not rows:
        raise AlrRuntimeIdentityError("cluster_identity_row_absent")
    if len(rows) != 1:
        raise AlrRuntimeIdentityError("cluster_identity_row_not_unique")
    row = rows[0]
    try:
        return {name: _row_value(row, index, name) for index, name in enumerate(columns)}
    except (IndexError, KeyError) as exc:
        raise AlrRuntimeIdentityError("cluster_identity_row_shape_invalid") from exc


# 兩個取列函數刻意各自以「module 常量」直接呼叫 execute:engine-scanner 的靜態 SQL
# inventory 必須能解析出確切語句與其權限(把 SQL 當參數傳會 fail-closed 進 unresolved)。
def _fetch_connected_identity(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(_CONNECTED_IDENTITY_SQL)
        rows = cursor.fetchall()
    return _single_identity_row(
        rows, ("connected_user", "connected_database", "server_version_num")
    )


def _fetch_cluster_identity_row(connection: Any) -> dict[str, Any]:
    with connection.cursor() as cursor:
        cursor.execute(_CLUSTER_IDENTITY_SQL)
        rows = cursor.fetchall()
    return _single_identity_row(rows, CLUSTER_IDENTITY_COLUMNS)


def load_runtime_topology_guard(topology_guard_file: Path) -> dict[str, Any]:
    """每次重連都重讀 + 自我 digest 不可變 topology guard(§8.3;不快取)。"""
    try:
        return verify_topology_guard(Path(topology_guard_file))
    except AlrApplicationIdentityError as exc:
        raise AlrRuntimeIdentityError(f"topology_guard_{exc.code}") from exc


def cluster_identity_row_digest(projection: Mapping[str, Any]) -> str:
    """封閉欄位投影的 canonical digest(guard 的 cluster_identity_row_digest 對照面)。"""
    return resolve_facade().canonical_digest(
        {name: projection[name] for name in CLUSTER_IDENTITY_COLUMNS}
    )


def verify_connected_cluster_identity(
    connection: Any,
    *,
    topology_guard_file: Path,
    dsn_identity: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """§8.3 重連身分閘:guard 自我 digest → 連上的 user/database/endpoint → 身分列。

    任何一項不符即 :class:`AlrRuntimeIdentityError`(permanent;production → exit 78)。
    本函數只讀,不寫、不建、不改任何 DB 狀態;結束前 rollback 以不持有讀交易。
    """
    guard = load_runtime_topology_guard(topology_guard_file)
    endpoint = guard["runtime_endpoint"]
    if dsn_identity is not None:
        expected = {
            "host": str(endpoint["host"]),
            "port": str(endpoint["port"]),
            "dbname": str(endpoint["dbname"]),
        }
        if any(str(dsn_identity.get(key)) != value for key, value in expected.items()):
            raise AlrRuntimeIdentityError("cluster_identity_dsn_endpoint_mismatch")
    try:
        connected = _fetch_connected_identity(connection)
        if str(connected["connected_database"]) != str(endpoint["dbname"]):
            raise AlrRuntimeIdentityError("cluster_identity_database_mismatch")
        if dsn_identity is not None and "user" in dsn_identity:
            if str(connected["connected_user"]) != str(dsn_identity["user"]):
                raise AlrRuntimeIdentityError("cluster_identity_user_mismatch")
        try:
            server_major = int(connected["server_version_num"]) // 10_000
        except (TypeError, ValueError) as exc:
            raise AlrRuntimeIdentityError("cluster_identity_server_version_invalid") from exc
        if server_major != int(guard["server_major_version"]):
            raise AlrRuntimeIdentityError("cluster_identity_server_version_mismatch")
        row = _fetch_cluster_identity_row(connection)
    finally:
        connection.rollback()
    projection = {
        "system_identifier": str(row["system_identifier"]),
        "database_oid": int(row["database_oid"]),
        "server_major_version": int(row["server_major_version"]),
        "runtime_host": str(row["runtime_host"]),
        "runtime_port": int(row["runtime_port"]),
        "runtime_dbname": str(row["runtime_dbname"]),
        "binding_nonce": str(row["binding_nonce"]),
    }
    if projection["system_identifier"] != str(guard["system_identifier"]):
        raise AlrRuntimeIdentityError("cluster_identity_system_identifier_mismatch")
    if projection["database_oid"] != int(guard["database_oid"]):
        raise AlrRuntimeIdentityError("cluster_identity_database_oid_mismatch")
    if projection["server_major_version"] != int(guard["server_major_version"]):
        raise AlrRuntimeIdentityError("cluster_identity_row_server_version_mismatch")
    if (
        projection["runtime_host"] != str(endpoint["host"])
        or projection["runtime_port"] != int(endpoint["port"])
        or projection["runtime_dbname"] != str(endpoint["dbname"])
    ):
        raise AlrRuntimeIdentityError("cluster_identity_endpoint_mismatch")
    row_digest = cluster_identity_row_digest(projection)
    if row_digest != guard["cluster_identity_row_digest"]:
        raise AlrRuntimeIdentityError("cluster_identity_row_digest_mismatch")
    return {
        "schema_version": "alr_runtime_cluster_identity_check_v1",
        "status": "MATCH",
        "topology_guard_digest": guard["self_digest"],
        "cluster_identity_row_digest": row_digest,
        "connected_user": str(connected["connected_user"]),
        "connected_database": str(connected["connected_database"]),
    }


def run_resident_db_sessions(
    *,
    open_connection: Callable[[], Any],
    run_session: Callable[[Any], dict[str, int]],
    close_connection: Callable[[Any], None],
    should_stop: Callable[[], bool],
    sleep: Callable[[float], Any],
    jitter: Callable[[], float] = default_jitter,
    is_transient: Callable[[BaseException], bool] = is_transient_db_availability_error,
    state: ResidentConsumerState | None = None,
) -> dict[str, Any]:
    """§8.3 常駐迴圈:transient DB 失敗絕不退出,關閉連線後有界退避無限重試。

    - ``run_session`` 正常回傳(收到停機訊號)→ 回傳該結果並結束;
    - transient 失敗 → 關閉失敗連線、遞增有界計數、退避後重連(不重放、不累積);
    - 非 transient(含身分不符/typed consumer 失敗)→ 原樣上拋(production → 78);
    - 退避期間收到停機訊號(``sleep`` 應為可中斷等待)→ 乾淨回傳、result 為 None。

    durable cursor 語義:進度全在 DB 側,行程內不保留跨 session 狀態,故重連後續讀
    自同一 durable cursor;本函數刻意不持有任何 per-attempt 佇列/緩衝。
    """
    tracker = state if state is not None else ResidentConsumerState()
    while True:
        connection: Any | None = None
        try:
            connection = open_connection()
            result = run_session(connection)
        except Exception as error:  # noqa: BLE001 — 由 is_transient 精確分流
            if not is_transient(error):
                raise
            tracker.record_transient_failure()
        else:
            tracker.record_session_completed()
            return {
                "status": "SESSION_COMPLETED",
                "result": result,
                "telemetry": tracker.telemetry(),
            }
        finally:
            if connection is not None:
                try:
                    close_connection(connection)
                except Exception:  # noqa: BLE001 — 關閉失敗不得掩蓋原因或阻斷重試
                    pass
        if should_stop():
            return {
                "status": "STOPPED_DURING_DB_OUTAGE",
                "result": None,
                "telemetry": tracker.telemetry(),
            }
        delay = next_backoff_seconds(tracker.consecutive_failures, jitter=jitter())
        tracker.record_backoff(delay)
        sleep(delay)


__all__ = [
    "AlrRuntimeIdentityError",
    "CLUSTER_IDENTITY_COLUMNS",
    "CLUSTER_IDENTITY_RELATION",
    "RECONNECT_MAX_BACKOFF_SECONDS",
    "RECONNECT_MIN_BACKOFF_SECONDS",
    "ResidentConsumerState",
    "cluster_identity_row_digest",
    "default_jitter",
    "is_transient_db_availability_error",
    "load_runtime_topology_guard",
    "next_backoff_seconds",
    "run_resident_db_sessions",
    "verify_connected_cluster_identity",
]

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
# 連線/可用性類的 psycopg2 型別(OperationalError/InterfaceError 及其子類)。以型別
# 全名比對,避免在無 psycopg2 的開發環境 import 失敗。
_CONNECTION_DB_ERROR_TYPES = frozenset({
    "psycopg2.OperationalError",
    "psycopg2.InterfaceError",
})
# W2 P2-A(真 fail-open):**只以型別分類會把 permanent 判成 transient**——psycopg2 對
# 「password authentication failed」(28P01)、「no pg_hba.conf entry」(28000)、
# 「database ... does not exist」(3D000)、「role ... does not exist」(42704)一律拋
# ``OperationalError``。型別分類下這些會被無限重試:單元恆 active、每 300 秒敲一次、
# 永遠不蒐集,operator 也永遠拿不到那個 exit 78。故以 SQLSTATE(psycopg2 的 ``pgcode``)
# 為權威分流。
#
# permanent(無 operator 介入永不自癒 → typed → production exit 78):
#   class 28 = invalid_authorization_specification(28000 pg_hba 無條目 / 28P01 密碼錯);
#   0P000 invalid_role_specification;42704 undefined_object(role 不存在);
#   3D000 invalid_catalog_name(database 不存在);3F000 invalid_schema_name;
#   42501 insufficient_privilege(ACL 與 pg_acl_manifest 錯配)。
_PERMANENT_DB_SQLSTATE_CLASSES = frozenset({"28"})
_PERMANENT_DB_SQLSTATES = frozenset({"0P000", "3D000", "3F000", "42501", "42704"})
# transient 保持「連線型別 ∧ 非 permanent SQLSTATE」:真連線失敗(connection refused /
# timeout / server closed)沒有 SQLSTATE,而 class 08(connection_exception)、
# 53(insufficient_resources)、57(operator_intervention:admin_shutdown/
# crash_shutdown/cannot_connect_now)都會自癒。未知 SQLSTATE 的連線型錯誤刻意留在
# transient:§8.3 規範「DB 可用性失敗不得退出」,寧可有界重試也不得把可恢復停機
# 鎖成永久 78。permanent 名單則必須把已知的認證/組態碼收全(本輪 P2-A 的修補面)。
PERMANENT_DB_CONFIG_CODE_PREFIX = "db_config_permanent_sqlstate_"
# §8.3 單例 advisory lock 佔用碼(consumer 於身分閘後、消費前 raise 的 typed 值)。
SINGLE_INSTANCE_LOCK_BUSY_CODE = "single_instance_lock_busy"


class AlrRuntimeIdentityError(AlrEventConsumerError):
    """§8.3 重連身分不符:permanent、不可重試(production → exit 78)。"""


class AlrPermanentDbConfigError(AlrEventConsumerError):
    """§8.3 permanent 的 DB 認證/組態失敗(SQLSTATE 判定;production → exit 78)。"""


class ResidentConsumerState:
    """常駐重連的**有界**狀態:只有固定數量的純量計數,永不累積 task/row/物件。"""

    __slots__ = (
        "sessions_completed",
        "transient_failures",
        "consecutive_failures",
        "connections_opened",
        "lock_busy_reconnect_retries",
        "last_backoff_seconds",
        "total_backoff_seconds",
    )

    def __init__(self) -> None:
        self.sessions_completed = 0
        self.transient_failures = 0
        self.consecutive_failures = 0
        self.connections_opened = 0
        self.lock_busy_reconnect_retries = 0
        self.last_backoff_seconds = 0.0
        self.total_backoff_seconds = 0.0

    def record_transient_failure(self) -> None:
        self.transient_failures += 1
        self.consecutive_failures += 1

    def record_connection_opened(self) -> None:
        """成功建立過連線才算「已連上」;P2-C 以此區分首連與重連。"""
        self.connections_opened += 1

    def record_lock_busy_reconnect_retry(self) -> None:
        """重連時撞到自己殘留 backend 的 advisory lock:與 transient 同走有界退避。"""
        self.lock_busy_reconnect_retries += 1
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
            "connections_opened": self.connections_opened,
            "lock_busy_reconnect_retries": self.lock_busy_reconnect_retries,
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


def _db_error_sqlstate(error: BaseException) -> str | None:
    """取 psycopg2 風格錯誤的 SQLSTATE(``pgcode``);缺失/非字串即 None。"""
    code = getattr(error, "pgcode", None)
    if not isinstance(code, str) or not code.strip():
        return None
    return code.strip().upper()


def _is_connection_db_error_type(error: BaseException) -> bool:
    """型別面:是否屬 psycopg2 的連線/可用性錯誤家族(以全名比對,不 import)。"""
    for klass in type(error).__mro__:
        if f"{klass.__module__}.{klass.__qualname__}" in _CONNECTION_DB_ERROR_TYPES:
            return True
    return False


def classify_db_error(error: BaseException) -> str:
    """§8.3 的 DB 失敗三分類:``transient`` / ``permanent_config`` / ``unclassified``。

    P2-A:SQLSTATE 優先於型別——permanent 的認證/組態碼即使包在 ``OperationalError``
    裡也絕不重試(否則單元永遠 active 卻永遠不蒐集);其餘連線型錯誤(含無 SQLSTATE
    的 connection refused / timeout / server closed)維持 transient。
    """
    if isinstance(error, AlrEventConsumerError):
        return "unclassified"  # typed consumer 失敗自有分流(身分不符/單例佔用)
    sqlstate = _db_error_sqlstate(error)
    if sqlstate is not None and (
        sqlstate[:2] in _PERMANENT_DB_SQLSTATE_CLASSES
        or sqlstate in _PERMANENT_DB_SQLSTATES
    ):
        return "permanent_config"
    if _is_connection_db_error_type(error):
        return "transient"
    return "unclassified"


def is_transient_db_availability_error(error: BaseException) -> bool:
    """是否為 §8.3 的 transient DB 可用性失敗(唯一可重試類)。"""
    return classify_db_error(error) == "transient"


def permanent_db_config_error(error: BaseException) -> AlrPermanentDbConfigError | None:
    """permanent 的 DB 認證/組態失敗 → typed 錯誤(production main 映射為 exit 78)。"""
    if classify_db_error(error) != "permanent_config":
        return None
    return AlrPermanentDbConfigError(
        f"{PERMANENT_DB_CONFIG_CODE_PREFIX}{_db_error_sqlstate(error)}"
    )


def is_single_instance_lock_busy(error: BaseException) -> bool:
    """是否為單例 advisory lock 佔用(P2-C 的重連重試判定面)。"""
    return (
        isinstance(error, AlrEventConsumerError)
        and str(error) == SINGLE_INSTANCE_LOCK_BUSY_CODE
    )


def _identity_relation_failure(error: BaseException) -> AlrRuntimeIdentityError | None:
    """P2-B:身分讀取的非 transient 失敗 → permanent typed(否則 None = 原樣上拋)。

    身分關聯缺席/欄位不符(psycopg2 ``ProgrammingError``:42P01 UndefinedTable、
    42703 UndefinedColumn、42501 InsufficientPrivilege)舊路徑會整個逸出 consumer 的
    ``AlrEventConsumerError`` 捕捉面 → exit 1 → ``Restart=on-failure`` 把 start limit
    燒成永久 failed 單元。此處一律收斂成與「零列」同一條 permanent 路徑(→ 78);
    transient 與既有 typed 失敗維持原分流,不被掩蓋。
    """
    if isinstance(error, AlrEventConsumerError) or is_transient_db_availability_error(
        error
    ):
        return None
    return AlrRuntimeIdentityError("cluster_identity_relation_unavailable")


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
    try:
        with connection.cursor() as cursor:
            cursor.execute(_CONNECTED_IDENTITY_SQL)
            rows = cursor.fetchall()
    except Exception as exc:  # noqa: BLE001 — 由 _identity_relation_failure 精確分流
        failure = _identity_relation_failure(exc)
        if failure is None:
            raise
        raise failure from exc
    return _single_identity_row(
        rows, ("connected_user", "connected_database", "server_version_num")
    )


def _fetch_cluster_identity_row(connection: Any) -> dict[str, Any]:
    try:
        with connection.cursor() as cursor:
            cursor.execute(_CLUSTER_IDENTITY_SQL)
            rows = cursor.fetchall()
    except Exception as exc:  # noqa: BLE001 — 由 _identity_relation_failure 精確分流
        failure = _identity_relation_failure(exc)
        if failure is None:
            raise
        raise failure from exc
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
    - **重連**時的單例 advisory lock 佔用(P2-C)→ 同走有界退避;首連的佔用維持上拋;
    - permanent 的 DB 認證/組態 SQLSTATE(P2-A)→ 轉 typed(production → exit 78);
    - 其餘非 transient(含身分不符/typed consumer 失敗)→ 原樣上拋(production → 78);
    - 退避前/後收到停機訊號(``sleep`` 應為可中斷等待)→ 乾淨回傳、result 為 None。

    durable cursor 語義:進度全在 DB 側,行程內不保留跨 session 狀態,故重連後續讀
    自同一 durable cursor;本函數刻意不持有任何 per-attempt 佇列/緩衝。
    """
    tracker = state if state is not None else ResidentConsumerState()
    while True:
        connection: Any | None = None
        # P2-C:「重連」= 本常駐迴圈已成功建立過連線。網路分割後我們自己上一條 backend
        # 可能還握著 server 側 advisory lock,新連線於是看到 lock-busy——那不是第二個
        # 實例,而是同一實例的殘留,崩潰三次就會把單元燒成 §8.3 禁止的永久 failed。
        # 首連的 lock-busy(真的有第二個實例)行為刻意不變。
        reconnect = tracker.connections_opened > 0
        try:
            connection = open_connection()
            tracker.record_connection_opened()
            result = run_session(connection)
        except Exception as error:  # noqa: BLE001 — 由下列謂詞精確分流
            if is_transient(error):
                tracker.record_transient_failure()
            elif reconnect and is_single_instance_lock_busy(error):
                tracker.record_lock_busy_reconnect_retry()
            else:
                permanent = permanent_db_config_error(error)
                if permanent is not None:
                    raise permanent from error
                raise
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
        # P3-a:等待返回後**先**看停機訊號再開下一條連線。少了這一步,SIGTERM 會多換
        # 到一次連線嘗試——DB 此時若剛好恢復,還會跑完一整個 session,直接威脅
        # ``TimeoutStopSec=30s``。
        if should_stop():
            return {
                "status": "STOPPED_DURING_DB_OUTAGE",
                "result": None,
                "telemetry": tracker.telemetry(),
            }


__all__ = [
    "AlrPermanentDbConfigError",
    "AlrRuntimeIdentityError",
    "CLUSTER_IDENTITY_COLUMNS",
    "CLUSTER_IDENTITY_RELATION",
    "PERMANENT_DB_CONFIG_CODE_PREFIX",
    "RECONNECT_MAX_BACKOFF_SECONDS",
    "RECONNECT_MIN_BACKOFF_SECONDS",
    "SINGLE_INSTANCE_LOCK_BUSY_CODE",
    "ResidentConsumerState",
    "classify_db_error",
    "cluster_identity_row_digest",
    "default_jitter",
    "is_single_instance_lock_busy",
    "is_transient_db_availability_error",
    "load_runtime_topology_guard",
    "next_backoff_seconds",
    "permanent_db_config_error",
    "run_resident_db_sessions",
    "verify_connected_cluster_identity",
]

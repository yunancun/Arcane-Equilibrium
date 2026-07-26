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

import math
import random
import re
import time
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
# P2-3(W2 review):一條**已證穩定**的 session(自連線建立起活過至少一個 heartbeat 週期,
# 即 300 秒)結束於斷線時,那是「復原後的新一次停機」,不是同一條失敗串的延續。舊碼只在
# run_session 正常回傳(收到停機訊號)時重設 consecutive_failures,而 production 常駐
# session 一路跑到下一次斷線才拋——於是相隔數小時的孤立停機被累加成同一串,每一次孤立
# 停機最終都吃滿 300 秒。此門檻之上即重設「連續」計數,累計計數(transient_failures)保留。
RECONNECT_HEALTHY_SESSION_SECONDS = 300.0
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
    "current_setting('server_version_num') AS server_version_num, "
    "current_setting('lc_messages') AS lc_messages"
)
# P1-4(W2 review):連線期失敗**沒有 SQLSTATE**(見下方 F1),唯一可判的是 server 的
# FATAL 文本;而該文本是被 ``lc_messages`` 在地化的。若 server 的 lc_messages 不是 C/英文,
# 認證/pg_hba/缺 role/缺 DB 這些 permanent 失敗一條都不匹配 → 被判成 transient → 常駐行程
# 永遠重試、operator 永遠等不到 exit 78。故把該設定綁進**可執行的** topology 契約:每一次
# (重)連線的在帶身分閘都讀 ``current_setting('lc_messages')`` 並硬比對;不符即 permanent
# typed 失敗(``cluster_identity_`` 前綴 → production exit 78),逼 operator 修正組態。
# 訊息指紋比對維持為次要訊號(見 _CONNECT_PERMANENT_MESSAGE_SQLSTATES)。
REQUIRED_LC_MESSAGES = "C"
# 誠實的殘留(source-only 不可導出):**首次**連線就失敗、且該 cluster 的 lc_messages 從未
# 被本閘證實過時,client 端拿不到 SQLSTATE 也拿不到可信任的語言——那一則失敗無法分類。
# 它刻意留在 transient(§8.3:可用性失敗不得退出),並由本契約顯式宣告為 typed 未證面,
# 而不是假裝已分類。見 :func:`derive_connect_error_locale_contract`。
CONNECT_ERROR_LOCALE_UNVERIFIED_CODE = "connect_error_locale_unverified_before_first_gate"
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
# 永遠不蒐集,operator 也永遠拿不到那個 exit 78。故以 SQLSTATE 為權威分流。
#
# permanent(無 operator 介入永不自癒 → typed → production exit 78):
#   class 28 = invalid_authorization_specification(28000 pg_hba 無條目 / 28P01 密碼錯);
#   0P000 invalid_role_specification;42704 undefined_object(role 不存在);
#   3D000 invalid_catalog_name(database 不存在);3F000 invalid_schema_name;
#   42501 insufficient_privilege / 42P01 undefined_table / 42703 undefined_column
#   (F2:schema/ACL 契約與 pg_acl_manifest 錯配——見下方 _SCHEMA_CONTRACT_SQLSTATES)。
_PERMANENT_DB_SQLSTATE_CLASSES = frozenset({"28"})
# F2:ACL manifest 涵蓋的 14 個關聯上任何 undefined-table / undefined-column /
# insufficient-privilege 都與身分列同一個 crash-loop 類——psycopg2 的 ``ProgrammingError``
# 逸出 consumer 的 ``AlrEventConsumerError`` 捕捉面 → exit 1 → ``Restart=on-failure``
# 在 300 秒內燒掉 ``StartLimitBurst=3`` → 單元永久 failed(§8.3 明文禁止的結果)。
# 這三碼在「session 內任何位置」都是 permanent,不限身分讀取。
_SCHEMA_CONTRACT_SQLSTATES = frozenset({"42501", "42703", "42P01"})
_PERMANENT_DB_SQLSTATES = frozenset({"0P000", "3D000", "3F000", "42704"}) | (
    _SCHEMA_CONTRACT_SQLSTATES
)
# F1(真驅動實證:psycopg2 2.9.12 + PostgreSQL 16,連線期逐一觀察):**連線期失敗沒有
# SQLSTATE**。libpq 在「連線建立」失敗時不回 PGresult,psycopg2 因而讓 ``pgcode`` /
# ``diag.sqlstate`` / ``pgerror`` **全為 None**,只留 server 的 FATAL 文本。所以單靠
# ``pgcode`` 分流在 connect path 上等於沒修:密碼錯、pg_hba 無條目、DB 不存在、role
# 不存在照樣落回 transient 分支被無限重試——正是 §8.3 要關掉的失敗。SQLSTATE 缺席時,
# 以 PG 的**逐字** errmsg 指紋回填 SQLSTATE;每條都對應一個固定的 PG 原始碼格式:
#   src/backend/libpq/auth.c  auth_failed()  → 密碼類 ERRCODE_INVALID_PASSWORD(28P01);
#                                              其餘方法 INVALID_AUTHORIZATION_SPEC(28000);
#   src/backend/libpq/hba.c(經 auth.c)      → 無條目 / 顯式 reject → 28000;
#   src/backend/utils/init/postinit.c        → role 不存在/不可登入 28000、DB 不存在 3D000。
# 反向硬邊界:真連線/可用性失敗(Connection refused、No such file or directory、timeout
# expired、server closed the connection unexpectedly、could not translate host name、
# the database system is starting up、sorry too many clients already)一條都不匹配 →
# 維持 transient。名單只收「已知 permanent」,未知文本永遠留在 transient(§8.3)。
_CONNECT_PERMANENT_MESSAGE_SQLSTATES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r'password authentication failed for user "[^"]*"'), "28P01"),
    (re.compile(r'no pg_hba\.conf entry for host "[^"]*"'), "28000"),
    (re.compile(r'pg_hba\.conf rejects connection for host "[^"]*"'), "28000"),
    (
        re.compile(
            r'(?:"trust"|Ident|Peer|GSSAPI|SSPI|PAM|LDAP|RADIUS|Certificate|BSD)'
            r' authentication failed for user "[^"]*"'
        ),
        "28000",
    ),
    (re.compile(r'authentication failed for user "[^"]*": host rejected'), "28000"),
    (re.compile(r'role "[^"]*" does not exist'), "28000"),
    (re.compile(r'role "[^"]*" is not permitted to log in'), "28000"),
    (re.compile(r'database "[^"]*" does not exist'), "3D000"),
)
# 診斷面:psycopg2 對 42P01/42703/42501 的 ``diag.table_name`` / ``diag.column_name``
# 實測恆為 None(server 不在 errdata 附關聯),故關聯/欄位名只能自 message_primary 解析。
_RELATION_SUBJECT_PATTERNS = (
    re.compile(r'relation "([^"]{1,120})" does not exist'),
    re.compile(r'column "([^"]{1,120})" does not exist'),
    re.compile(r'permission denied for \w+ ([A-Za-z0-9_.$"]{1,120})'),
)
# typed code 是要被 operator 讀、被 journal 記的:只讓識別字字元進去(其餘一律折成 _)。
_SUBJECT_UNSAFE_RE = re.compile(r'[^A-Za-z0-9_.$]')
# transient 保持「連線型別 ∧ 非 permanent SQLSTATE」:真連線失敗(connection refused /
# timeout / server closed)沒有 SQLSTATE,而 class 08(connection_exception)、
# 53(insufficient_resources)、57(operator_intervention:admin_shutdown/
# crash_shutdown/cannot_connect_now)都會自癒。未知 SQLSTATE 的連線型錯誤刻意留在
# transient:§8.3 規範「DB 可用性失敗不得退出」,寧可有界重試也不得把可恢復停機
# 鎖成永久 78。permanent 名單則必須把已知的認證/組態碼收全(本輪 P2-A 的修補面)。
PERMANENT_DB_CONFIG_CODE_PREFIX = "db_config_permanent_sqlstate_"
# 診斷用後綴:typed code 帶上關聯/欄位名,operator 不必翻 traceback 就知道是哪一張表。
DB_ERROR_SUBJECT_INFIX = "_relation_"
# §8.3 單例 advisory lock 佔用碼(consumer 於身分閘後、消費前 raise 的 typed 值)。
SINGLE_INSTANCE_LOCK_BUSY_CODE = "single_instance_lock_busy"
# 身分關聯讀取失敗的 typed 前綴(F2:其後接 SQLSTATE 與關聯名,不再把 42P01/42703/42501
# 壓成同一個無資訊碼——那相對於原 traceback 是診斷性退步)。
CLUSTER_IDENTITY_RELATION_UNAVAILABLE_CODE = "cluster_identity_relation_unavailable"

# D2 §8.3 可觀測性契約(source-only 宣告,零 runtime 接觸):**沉默重試的 consumer 在
# journal 與 ``systemctl status`` 上與健康者不可區分**——單元 active、行程存在、零日誌,
# 但每 300 秒只是敲一次連不上的 DB。唯一真信號是 ``learning.alr_health_events`` 的
# heartbeat 是否變舊。S2.5A 的「initial running evidence」postcheck 必須消費本契約,
# **不得**以 ``ActiveState=active`` 結案。
CONSUMER_HEALTH_RELATION = "learning.alr_health_events"
# 與 alr_health_repository.persist_health_snapshot 的 heartbeat_seconds 預設同值
# (focused 測試以 inspect.signature 釘死,漂移即紅)。
CONSUMER_HEARTBEAT_INTERVAL_SECONDS = 300
# 容忍兩次遺失後才判 STALE(退避上限恰為一個 heartbeat 週期,單次錯過可能只是重連)。
CONSUMER_MISSED_HEARTBEATS_BEFORE_STALE = 3
CONSUMER_LIVENESS_STALENESS_SECONDS = (
    CONSUMER_HEARTBEAT_INTERVAL_SECONDS * CONSUMER_MISSED_HEARTBEATS_BEFORE_STALE
)


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
        "healthy_recoveries",
        "last_session_seconds",
        "last_backoff_seconds",
        "total_backoff_seconds",
    )

    def __init__(self) -> None:
        self.sessions_completed = 0
        self.transient_failures = 0
        self.consecutive_failures = 0
        self.connections_opened = 0
        self.lock_busy_reconnect_retries = 0
        self.healthy_recoveries = 0
        self.last_session_seconds = 0.0
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

    def record_healthy_recovery(self, session_seconds: float) -> None:
        """P2-3:一條**已證穩定**的 session 之後,連續失敗串歸零(累計計數保留)。

        「已證穩定」= 自連線建立起活過 :data:`RECONNECT_HEALTHY_SESSION_SECONDS`
        (一個 heartbeat 週期,期間必然已寫過 durable 證據)。相隔數小時的孤立停機因此
        各自從 5 秒重新退避,而不是被累加成一條永遠吃滿 300 秒的失敗串。
        """
        self.healthy_recoveries += 1
        self.last_session_seconds = float(session_seconds)
        self.consecutive_failures = 0

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
            "healthy_recoveries": self.healthy_recoveries,
            "last_session_seconds": self.last_session_seconds,
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


def _connect_message_sqlstate(message: str) -> str | None:
    """F1:自 libpq/PG 的逐字 FATAL 文本回填 permanent SQLSTATE(不匹配即 None)。"""
    for pattern, sqlstate in _CONNECT_PERMANENT_MESSAGE_SQLSTATES:
        if pattern.search(message):
            return sqlstate
    return None


def resolve_db_error_sqlstate(error: BaseException) -> str | None:
    """權威 SQLSTATE:先取 driver 的 ``pgcode``;連線期缺席時退回訊息指紋。

    F1:``pgcode`` 只在 server 真的回過 error response(session 內)時才有值;連線期
    失敗(認證/pg_hba/缺 DB/缺 role)一律 ``pgcode is None``,只有訊息可判。訊息回填
    **僅限**連線/可用性錯誤型別,避免任意例外因文字巧合被判成 permanent。
    """
    sqlstate = _db_error_sqlstate(error)
    if sqlstate is not None:
        return sqlstate
    if not _is_connection_db_error_type(error):
        return None
    return _connect_message_sqlstate(str(error))


def db_error_subject(error: BaseException) -> str | None:
    """自訊息解析關聯/欄位名(diag.table_name 對這三碼實測恆為 None);消毒後回傳。"""
    text = str(error)
    for pattern in _RELATION_SUBJECT_PATTERNS:
        found = pattern.search(text)
        if found:
            subject = _SUBJECT_UNSAFE_RE.sub("_", found.group(1)).strip("_")[:64]
            if subject:
                return subject
    return None


def _is_permanent_db_sqlstate(sqlstate: str) -> bool:
    return (
        sqlstate[:2] in _PERMANENT_DB_SQLSTATE_CLASSES
        or sqlstate in _PERMANENT_DB_SQLSTATES
    )


def classify_db_error(error: BaseException) -> str:
    """§8.3 的 DB 失敗三分類:``transient`` / ``permanent_config`` / ``unclassified``。

    P2-A:SQLSTATE 優先於型別——permanent 的認證/組態碼即使包在 ``OperationalError``
    裡也絕不重試(否則單元永遠 active 卻永遠不蒐集);其餘連線型錯誤(含無 SQLSTATE
    的 connection refused / timeout / server closed)維持 transient。
    F1:SQLSTATE 由 :func:`resolve_db_error_sqlstate` 解析,故連線期(``pgcode is None``)
    的認證/pg_hba/缺 DB 失敗一樣走 permanent,不再被無限重試。
    """
    if isinstance(error, AlrEventConsumerError):
        return "unclassified"  # typed consumer 失敗自有分流(身分不符/單例佔用)
    sqlstate = resolve_db_error_sqlstate(error)
    if sqlstate is not None and _is_permanent_db_sqlstate(sqlstate):
        return "permanent_config"
    if _is_connection_db_error_type(error):
        return "transient"
    return "unclassified"


def is_transient_db_availability_error(error: BaseException) -> bool:
    """是否為 §8.3 的 transient DB 可用性失敗(唯一可重試類)。"""
    return classify_db_error(error) == "transient"


def _typed_failure_code(prefix: str, error: BaseException) -> str:
    """typed code = 前綴 + SQLSTATE(+ 關聯名)。F2:42P01/42703/42501 必須可區分。"""
    code = prefix
    sqlstate = resolve_db_error_sqlstate(error)
    if sqlstate is not None:
        code = f"{code}{'' if prefix.endswith('_') else '_'}{sqlstate}"
    subject = db_error_subject(error)
    if subject is not None:
        code = f"{code}{DB_ERROR_SUBJECT_INFIX}{subject}"
    return code


def permanent_db_config_error(error: BaseException) -> AlrPermanentDbConfigError | None:
    """permanent 的 DB 認證/組態失敗 → typed 錯誤(production main 映射為 exit 78)。

    F2:涵蓋面不再只有身分讀取——session 內任何位置的 42P01/42703/42501 都在此收斂成
    typed permanent(否則裸 psycopg2 錯誤逸出 → exit 1 → start limit 燒成永久 failed)。
    """
    if classify_db_error(error) != "permanent_config":
        return None
    return AlrPermanentDbConfigError(
        _typed_failure_code(PERMANENT_DB_CONFIG_CODE_PREFIX, error)
    )


def is_single_instance_lock_busy(error: BaseException) -> bool:
    """是否為單例 advisory lock 佔用(P2-C 的重連重試判定面)。"""
    return (
        isinstance(error, AlrEventConsumerError)
        and str(error) == SINGLE_INSTANCE_LOCK_BUSY_CODE
    )


def derive_consumer_liveness_contract() -> dict[str, Any]:
    """D2:常駐 consumer 的 liveness/staleness 契約(code-owned;source-only,零 runtime)。

    §8.3 允許 consumer 在 DB 停機時無限重試而**不退出**——正確,但代價是「單元 active」
    從此不再是「在蒐集」的證據:沉默重連的 consumer 與健康的 consumer 在 systemd 與
    journal 上完全一樣。本契約把唯一的真信號寫成可執行常量:``learning.alr_health_events``
    的 heartbeat 年齡。折入 W2 exported ABI 後,S2.5A 的「initial running evidence」
    postcheck 有一個明確輸入,不能以 ``ActiveState=active`` 結案。

    ⚠ 本函數不連 DB、不讀 host、不宣稱任何 runtime 事實;它只宣告「要看什麼、多舊算死」。
    """
    return {
        "schema_version": "alr_consumer_liveness_contract_v1",
        "health_relation": CONSUMER_HEALTH_RELATION,
        "heartbeat_interval_seconds": CONSUMER_HEARTBEAT_INTERVAL_SECONDS,
        "missed_heartbeats_before_stale": CONSUMER_MISSED_HEARTBEATS_BEFORE_STALE,
        "staleness_threshold_seconds": CONSUMER_LIVENESS_STALENESS_SECONDS,
        "liveness_signal": (
            "max(observed_at) of learning.alr_health_events written by the unit's "
            "consumer session lane"
        ),
        "insufficient_signals": [
            "systemd ActiveState=active",
            "systemd SubState=running",
            "process exists / journal is silent",
        ],
        "verdicts": ["LIVE", "STALE", "UNKNOWN"],
        "runtime_contact": False,
    }


def derive_connect_error_locale_contract() -> dict[str, Any]:
    """P1-4:連線期錯誤分類的 locale 契約(code-owned;source-only,零 runtime 接觸)。

    可執行面(primary):在帶身分閘每次(重)連線都比對 ``current_setting('lc_messages')``
    == :data:`REQUIRED_LC_MESSAGES`,不符即 permanent typed 失敗 → production exit 78。
    次要訊號(secondary):PG 逐字 FATAL 文本指紋(``_CONNECT_PERMANENT_MESSAGE_SQLSTATES``)
    ——連線期 libpq 不回 SQLSTATE,故它是唯一可用的判別材料,而其可用性正由上一條保證。

    ⚠ typed 未證面(source-only 不可導出):在**第一次成功連線之前**,client 端既無
    SQLSTATE 也無經證實的 server 語言,那一則連線失敗無法被誠實分類——它留在 transient
    (§8.3 禁止把可恢復停機鎖成永久 78),並在此顯式具名為
    :data:`CONNECT_ERROR_LOCALE_UNVERIFIED_CODE`,而不是假裝已分類。折入 W2 exported ABI
    後,該設定或該名單漂移必然破壞 W2 導出。
    """
    return {
        "schema_version": "alr_connect_error_locale_contract_v1",
        "required_lc_messages": REQUIRED_LC_MESSAGES,
        "verified_by": (
            "in-band identity gate on every (re)connect: "
            "SELECT current_setting('lc_messages')"
        ),
        "mismatch_verdict": "cluster_identity_lc_messages_mismatch",
        "mismatch_disposition": "permanent_config_exit_78",
        "secondary_signal": "verbatim PG FATAL message fingerprints",
        "message_fingerprint_count": len(_CONNECT_PERMANENT_MESSAGE_SQLSTATES),
        "unverifiable_before_first_gate": CONNECT_ERROR_LOCALE_UNVERIFIED_CODE,
        "unverifiable_disposition": "transient_bounded_retry",
        "runtime_contact": False,
    }


def classify_consumer_liveness(heartbeat_age_seconds: Any) -> str:
    """依契約把 heartbeat 年齡判為 ``LIVE`` / ``STALE`` / ``UNKNOWN``(純函數)。

    年齡不可得(從未寫過 heartbeat / 查不到)= ``UNKNOWN``,**不是** LIVE:postcheck
    在沒有證據時必須 fail-closed,不得把「查不到」讀成「活著」。
    """
    if (
        isinstance(heartbeat_age_seconds, bool)
        or not isinstance(heartbeat_age_seconds, (int, float))
        # NaN 的所有比較皆為 False,漏掉這一條會讓 NaN 直接落進 LIVE(fail-open)。
        or not math.isfinite(heartbeat_age_seconds)
        or heartbeat_age_seconds < 0
    ):
        return "UNKNOWN"
    return (
        "STALE"
        if float(heartbeat_age_seconds) > CONSUMER_LIVENESS_STALENESS_SECONDS
        else "LIVE"
    )


def _identity_relation_failure(error: BaseException) -> AlrRuntimeIdentityError | None:
    """P2-B:身分讀取的非 transient 失敗 → permanent typed(否則 None = 原樣上拋)。

    身分關聯缺席/欄位不符(psycopg2 ``ProgrammingError``:42P01 UndefinedTable、
    42703 UndefinedColumn、42501 InsufficientPrivilege)舊路徑會整個逸出 consumer 的
    ``AlrEventConsumerError`` 捕捉面 → exit 1 → ``Restart=on-failure`` 把 start limit
    燒成永久 failed 單元。此處一律收斂成與「零列」同一條 permanent 路徑(→ 78);
    transient 與既有 typed 失敗維持原分流,不被掩蓋。

    F2:typed code 帶上 SQLSTATE 與關聯/欄位名——舊版把三碼壓成同一個無資訊字串,
    operator 分不出「表不存在 / 欄位不符 / 權限不足」,相對原 traceback 是診斷性退步。
    """
    if isinstance(error, AlrEventConsumerError) or is_transient_db_availability_error(
        error
    ):
        return None
    return AlrRuntimeIdentityError(
        _typed_failure_code(CLUSTER_IDENTITY_RELATION_UNAVAILABLE_CODE, error)
    )


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
        rows,
        ("connected_user", "connected_database", "server_version_num", "lc_messages"),
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

    F6:失敗路徑上的 rollback 只做**盡力而為**。舊的 ``finally: connection.rollback()``
    會在連線半死時以 ``InterfaceError`` 取代 in-flight 的 ``AlrRuntimeIdentityError``,
    把 permanent 身分不符降級成 transient → 無限重連,永遠不會有那個 78。成功路徑上的
    rollback 失敗則刻意保持上拋(連線已壞,transient 重連正是對的處置)。
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
        # P1-4:連線期失敗的唯一判別材料是 server 文本,而文本語言由 lc_messages 決定。
        # 這條在帶檢查把「permanent 認證/組態失敗可被分類」變成可執行的 topology 契約:
        # 不是 C 即 permanent typed 失敗(→ 78),而非讓分類器在未來某次連線期靜默失效。
        if str(connected["lc_messages"]) != REQUIRED_LC_MESSAGES:
            raise AlrRuntimeIdentityError("cluster_identity_lc_messages_mismatch")
        try:
            server_major = int(connected["server_version_num"]) // 10_000
        except (TypeError, ValueError) as exc:
            raise AlrRuntimeIdentityError("cluster_identity_server_version_invalid") from exc
        if server_major != int(guard["server_major_version"]):
            raise AlrRuntimeIdentityError("cluster_identity_server_version_mismatch")
        row = _fetch_cluster_identity_row(connection)
    except BaseException:
        # in-flight 失敗優先:rollback 自己的錯誤絕不得取代它(見 docstring F6)。
        try:
            connection.rollback()
        except Exception:  # noqa: BLE001 — 盡力而為;原因必須原樣上拋
            pass
        raise
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
        "lc_messages": str(connected["lc_messages"]),
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
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """§8.3 常駐迴圈:transient DB 失敗絕不退出,關閉連線後有界退避無限重試。

    - ``run_session`` 正常回傳(收到停機訊號)→ 回傳該結果並結束;
    - transient 失敗 → 關閉失敗連線、遞增有界計數、退避後重連(不重放、不累積);
    - **重連**時的單例 advisory lock 佔用(P2-C)→ 同走有界退避;首連的佔用維持上拋;
    - permanent 的 DB 認證/組態 SQLSTATE(P2-A)→ 轉 typed(production → exit 78);
    - 其餘非 transient(含身分不符/typed consumer 失敗)→ 原樣上拋(production → 78);
    - 退避前/後收到停機訊號(``sleep`` 應為可中斷等待)→ 乾淨回傳、result 為 None。

    P2-3(W2 review):失敗發生前若該連線已活過 :data:`RECONNECT_HEALTHY_SESSION_SECONDS`,
    先記一次 healthy recovery 再記這次失敗——連續失敗串因此從 1 重新起算(累計失敗計數
    不動)。``monotonic`` 可注入以令序列在測試中完全可重放。

    durable cursor 語義:進度全在 DB 側,行程內不保留跨 session 狀態,故重連後續讀
    自同一 durable cursor;本函數刻意不持有任何 per-attempt 佇列/緩衝。
    """
    tracker = state if state is not None else ResidentConsumerState()
    while True:
        connection: Any | None = None
        connected_at: float | None = None
        # P2-C:「重連」= 本常駐迴圈已成功建立過連線。網路分割後我們自己上一條 backend
        # 可能還握著 server 側 advisory lock,新連線於是看到 lock-busy——那不是第二個
        # 實例,而是同一實例的殘留,崩潰三次就會把單元燒成 §8.3 禁止的永久 failed。
        # 首連的 lock-busy(真的有第二個實例)行為刻意不變。
        reconnect = tracker.connections_opened > 0
        try:
            connection = open_connection()
            tracker.record_connection_opened()
            connected_at = monotonic()
            result = run_session(connection)
        except Exception as error:  # noqa: BLE001 — 由下列謂詞精確分流
            # P2-3:先判「這條連線是否已證穩定」;是 → 這是復原之後的**新**一次停機。
            if connected_at is not None:
                session_seconds = float(monotonic()) - float(connected_at)
                if session_seconds >= RECONNECT_HEALTHY_SESSION_SECONDS:
                    tracker.record_healthy_recovery(session_seconds)
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
    "CLUSTER_IDENTITY_RELATION_UNAVAILABLE_CODE",
    "CONNECT_ERROR_LOCALE_UNVERIFIED_CODE",
    "CONSUMER_HEALTH_RELATION",
    "CONSUMER_HEARTBEAT_INTERVAL_SECONDS",
    "CONSUMER_LIVENESS_STALENESS_SECONDS",
    "CONSUMER_MISSED_HEARTBEATS_BEFORE_STALE",
    "DB_ERROR_SUBJECT_INFIX",
    "PERMANENT_DB_CONFIG_CODE_PREFIX",
    "RECONNECT_HEALTHY_SESSION_SECONDS",
    "RECONNECT_MAX_BACKOFF_SECONDS",
    "RECONNECT_MIN_BACKOFF_SECONDS",
    "REQUIRED_LC_MESSAGES",
    "SINGLE_INSTANCE_LOCK_BUSY_CODE",
    "ResidentConsumerState",
    "classify_consumer_liveness",
    "classify_db_error",
    "cluster_identity_row_digest",
    "db_error_subject",
    "default_jitter",
    "derive_connect_error_locale_contract",
    "derive_consumer_liveness_contract",
    "is_single_instance_lock_busy",
    "is_transient_db_availability_error",
    "load_runtime_topology_guard",
    "next_backoff_seconds",
    "permanent_db_config_error",
    "resolve_db_error_sqlstate",
    "run_resident_db_sessions",
    "verify_connected_cluster_identity",
]

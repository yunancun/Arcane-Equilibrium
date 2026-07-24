"""S2.1 ALR quiesce ownership / inventory / static-guard SAMPLER 下層(AIML WP3;由 fence SSOT 拆出)。

這是 ``agent_governance_alr_quiesce_fence`` 的**下層**:host 端 allowlisted system-level ``systemctl show`` +
模擬 ``/proc`` 讀取、以重用的 S2.0 唯讀 observer 讀 DB 端 quiesce 證據、把多訊號組裝成一份 raw inventory、
以此判 ``CONFIRMED / STALE / AMBIGUOUS`` ownership verdict,以及 bounded observation-window 靜態守恆取樣。
上層(fence 模組)保留 schema 註冊委派、operator SSHSIG 授權、四個 typed artifact 的 builder/validator、
可逆 fence ops、``apply_quiesce_fence`` 編排與 secret-armor。

**為何拆分。** fence 模組已抵達 2000 行硬上限;把「純讀取 + inventory + predicate + sampler」下沉到本模組,
讓 Codex P1 修正(C1 exact-invocation 收斂 / C2 owner↔MainPID 綁定 / C4 取樣節奏截止)得以落地而不破 2000 行。

**誠實界線不變。** 本層絕不 signal 任何真 process、絕不 stop/start;host 端跑在**模擬 /proc + 注入
system-level systemctl callable** 上,DB 端只經 S2.0 唯讀 observer 讀。真 live ``/proc`` / ``systemctl`` 一律
DEFERRED 給 S2.1 EFFECT session。

**循環相依處理。** ``confirm_alr_owner`` / ``collect_static_guard_window`` 需要上層的 observation builder
(``build_quiesce_observation``)與時間投影(``_plus_seconds``);為免 import 期循環,這兩處在**函式內**延遲
匯入 fence 模組(本模組 top-level 完全不匯入 fence 模組,先被完整載入)。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

# 唯讀消費:component_effects 的 PG 識別碼引號;中央 validator 的 canonical_digest。
import agent_governance_component_effects as ce  # noqa: E402
import aiml_gate_receipt_validator as central_validator  # noqa: E402


canonical_digest = central_validator.canonical_digest

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

EVIDENCE_TTL_SECONDS = 900
# 靜態守恆窗取樣的硬上限:防止注入 clock 永不前進導致無限取樣(spin → fail-closed)。
MAX_WINDOW_SAMPLES = 512
# collect_static_guard_window 三值窗判定(FIX-W3-1c):HELD=達標;VIOLATED=帶真 non-held 樣本;UNDERSPECIFIED=全 held 但窗不足→typed FAILED。
WINDOW_STATUS_HELD = "HELD"
WINDOW_STATUS_VIOLATED = "VIOLATED"
WINDOW_STATUS_UNDERSPECIFIED = "UNDERSPECIFIED"

# ── 被 fence 的唯一具體 owner(S2.1 §1;不發明 owner model,只確認這一個)。S2.4 §8 對齊:system-level unit,
# 專屬 aiml-engine-scanner UID + content-addressed 解譯器 + protected-credential DSN + PG role aiml_engine_scanner。──
UNIT_NAME = "arcane-equilibrium-aiml-engine-scanner.service"
ADVISORY_LOCK_NAME = "alr_event_consumer_v1"
LISTEN_CHANNEL = "alr_scanner_snapshot_v1"
DEFAULT_CONSUMER_SESSION_RELATION = "learning.alr_consumer_events"
# ALR consumer 的最小權限 PG 身分(§8 的 PG role=aiml_engine_scanner,本地 Unix-socket 對映)。§3 訊號 #7 以此把
# advisory lock 的**持有 backend** 綁回 ALR 連線身分——注意 pg_locks.pid 是**伺服器端 backend pid**,與 systemd
# MainPID(client OS pid)本質不同、永不相等,故正確的綁定是 holder backend 的 role(usename),非 pid 比對。
ALR_CONNECTION_ROLE = "aiml_engine_scanner"
# host 端唯讀 allowlist 的固定路徑(system-level manager;prior art:p0b_alr_current_head_two_cycle_observer_v2,narrowly 重寫,不匯入)。
SYSTEMD = "/usr/bin/systemctl"
# 唯一被允許的 system-level ``systemctl show`` 屬性集(超出即 fail-closed);對齊 p0b 並補 restart-policy/hardening。
QUIESCE_SHOW_PROPERTIES = (
    "LoadState", "ActiveState", "SubState", "MainPID", "InvocationID", "NRestarts",
    "FragmentPath", "DropInPaths", "ControlGroup", "Environment", "NeedDaemonReload",
    "Restart", "RestartUSec", "TimeoutStopUSec", "WatchdogUSec",
    "NoNewPrivileges", "ProtectSystem", "PrivateTmp", "RestrictAddressFamilies",
)
_SHOW_PROPERTY_SET = frozenset(QUIESCE_SHOW_PROPERTIES)
# env-hash 只涵蓋 unit 宣告的鍵(§3 訊號 #5);runtime-digest 由 ALR_EXPECTED_LEARNING_RUNTIME_DIGEST 導出。
# §8 unit 恰宣告三條 ``Environment=`` 行(無 PYTHONPATH——content-addressed runtime 已內含模組樹;無 ALR_CANDIDATE_*)。
ENV_DECLARED_KEYS = (
    "ALR_SOURCE_HEAD", "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST", "ALR_EXPECTED_COMPATIBILITY_RECEIPT",
)
_RUNTIME_DIGEST_ENV_KEY = "ALR_EXPECTED_LEARNING_RUNTIME_DIGEST"
CONSUMER_SESSION_TERMINALS = ("SESSION_STOPPED", "SESSION_FAILED", "UNCLEAN_RECOVERY")

# ── FIX-C1(Codex :414;S2.4 §8 對齊):exact approved-flag 形。長壽命 ALR invocation 的解譯器必為 §8 的
# content-addressed 路徑(封存 runtimes root 下的 python3;拒 /usr/bin/python3 系統 Python 與任何 home/PYTHONPATH
# 相對 Python)、``-I`` 隔離模式固定、模組固定、三旗標值逐一綁定、max-batch 為 bounded 整數;任何多餘/未知參數一律拒。──
_ALR_CONSUMER_MODULE = "ml_training.alr_event_consumer"
_ALR_APPROVED_FLAGS = frozenset({"--dsn-file", "--lock-file", "--max-batch"})
_ALR_MAX_BATCH_CEILING = 4096
# §8 的 content-addressed 解譯器:封存 runtimes root 下的絕對路徑 + basename python3。``[^/]+`` digest 段刻意不釘
# 精確 hex 長度/編碼(§8 只寫 <runtime-content-digest>,其 wire 形歸 S2.3 content_addressed_fixed_path 約定);regex
# 仍強制兩個 §8 決定性事實——絕對路徑落在封存 runtimes root 下(故 /usr/bin/python3 與 home 相對 Python 皆拒)+ basename python3。
_ALR_RUNTIME_INTERPRETER_RE = re.compile(r"^/opt/arcane-equilibrium/aiml/runtimes/[^/]+/bin/python3$")
# 部署形固定 10 個 token(§8 resolved argv):``<runtime python3> -I -m <module> --dsn-file <v> --lock-file <v> --max-batch <int>``。
# systemd 在 exec 前解析 specifier,故 kernel 儲存的 argv 帶**已解析的絕對路徑**(``%d``/``%t`` 永不現身於 /proc)。
_ALR_CMDLINE_TOKEN_COUNT = 10


class QuiesceFenceError(RuntimeError):
    """Base for a would-be quiesce artifact that cannot be safely emitted (fail-closed)."""


class QuiesceHostReadError(QuiesceFenceError):
    """Raised when a host-side read violates the allowlist / cannot be trusted."""


def _safe_ident(name: Any) -> str:
    # 重用 component_effects ``_pg_ident`` 白名單(^[a-z_][a-z0-9_]*$),把 ComponentEffectError 轉為本模組錯誤。
    try:
        return ce._pg_ident(name)
    except ce.ComponentEffectError as exc:  # noqa: PERF203
        raise QuiesceFenceError(f"unsafe SQL identifier: {name!r}") from exc


# --------------------------------------------------------------------------- #
# host-side allowlisted systemd/proc reader (SOURCE lane = injected/simulated)
# --------------------------------------------------------------------------- #
def _assert_allowlisted_systemctl(argv: list[str]) -> None:
    """只允許固定的唯讀 system-level ``systemctl show/list-units`` 形;任何其它指令一律拒(絕不 stop/start/kill from a reader)。

    §8 的 unit 為 system-level(host system manager 擁有生命週期,非 ``--user``);故此處以 system-level
    ``systemctl``(``SYSTEMD`` 同一 binary,去掉 ``--user`` 即選 system manager)唯讀 show/list-units。
    prior art:``p0b_alr_current_head_two_cycle_observer_v2.build_readonly_runtime_module`` 的 narrow
    allowlist(此處 narrowly 重寫,不匯入 p0b——其硬編 fixed-path/uid1000/target-head drift-fail)。
    """

    show_prefix = [SYSTEMD, "show", UNIT_NAME]
    if argv[: len(show_prefix)] == show_prefix:
        tail = argv[len(show_prefix):]
        if len(tail) % 2 == 0 and all(
            tail[i] == "-p" and tail[i + 1] in _SHOW_PROPERTY_SET
            for i in range(0, len(tail), 2)
        ):
            return
    if argv == [SYSTEMD, "list-units", "--type=scope", "--state=active",
                "--no-legend", "--no-pager"]:
        return
    raise QuiesceHostReadError("readonly systemctl command is not allowlisted")


def _show_command() -> list[str]:
    command = [SYSTEMD, "show", UNIT_NAME]
    for prop in QUIESCE_SHOW_PROPERTIES:
        command.extend(("-p", prop))
    return command


def _parse_show(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in raw.splitlines():
        key, separator, value = line.partition("=")
        if separator != "=" or key not in _SHOW_PROPERTY_SET:
            raise QuiesceHostReadError("readonly service property line is invalid")
        result[key] = value
    if set(result) != _SHOW_PROPERTY_SET:
        raise QuiesceHostReadError("readonly service properties are incomplete")
    return result


def _run_show(host_probe: Any) -> dict[str, str]:
    command = _show_command()
    _assert_allowlisted_systemctl(command)
    return _parse_show(host_probe.run(command))


def _scope_conflict(host_probe: Any) -> bool:
    command = [SYSTEMD, "list-units", "--type=scope", "--state=active",
               "--no-legend", "--no-pager"]
    _assert_allowlisted_systemctl(command)
    raw = host_probe.run(command)
    for line in raw.splitlines():
        if not line.strip():
            continue
        name = line.split()[0]
        # ALR 的 owner 是 service(非 scope);任何攜 alr_event_consumer 的 active scope = 替身/包裝競爭者。
        if "alr" in name and name.endswith(".scope"):
            return True
    return False


def _read_proc_cmdline(proc_root: Path, pid: int) -> list[str] | None:
    try:
        raw = (proc_root / str(pid) / "cmdline").read_bytes()
    except OSError:
        return None
    return [part.decode("utf-8", "replace") for part in raw.split(b"\x00") if part]


def _is_alr_longlived_cmdline(
    args: list[str], *, expected_dsn_file: str, expected_lock_file: str,
) -> bool:
    # FIX-C1(Codex :414;S2.4 §8 對齊):精確辨識**部署中**的長壽命 ALR invocation(§4 反替身守恆)。§8 兩個
    # 決定性事實迫使收斂——解譯器必為 content-addressed 路徑(拒 /usr/bin/python3 系統 Python),且 ``-I`` 插在
    # 解譯器與 ``-m`` 之間使 token 數為 10。此處收斂為 exact approved-flag 形:
    #   ① token 數固定 10;② 解譯器 fullmatch content-addressed regex(封存 runtimes root 下的 python3);
    #   ③ args[1] == ``-I``;④ ``-m <module>`` 於 args[2:4] 固定;⑤ 尾端(args[4:])三旗標為恰好
    #   {--dsn-file,--lock-file,--max-batch}、無重複、無未知/多餘旗標;⑥ dsn/lock 值逐一等於 intent/probe 的**已解析**
    #   路徑(``%d``/``%t`` 已被 systemd 解析);⑦ max-batch 為 bounded 正整數。任一不符即非 candidate。
    if len(args) != _ALR_CMDLINE_TOKEN_COUNT:
        return False
    if not _ALR_RUNTIME_INTERPRETER_RE.fullmatch(args[0]):
        return False
    if args[1] != "-I":
        return False
    if args[2] != "-m" or args[3] != _ALR_CONSUMER_MODULE:
        return False
    tail = args[4:]
    flags: dict[str, str] = {}
    for i in range(0, len(tail), 2):
        key = tail[i]
        value = tail[i + 1]
        if key in flags:  # 重複旗標 → 拒
            return False
        flags[key] = value
    if set(flags) != set(_ALR_APPROVED_FLAGS):  # 未知/多餘/缺旗標 → 拒
        return False
    if flags["--dsn-file"] != expected_dsn_file or flags["--lock-file"] != expected_lock_file:
        return False
    max_batch = flags["--max-batch"]
    return bool(max_batch.isdigit() and 1 <= int(max_batch) <= _ALR_MAX_BATCH_CEILING)


def _read_proc_stat_start_ticks(proc_root: Path, pid: int) -> str | None:
    try:
        raw = (proc_root / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return None
    close = raw.rfind(")")
    fields = raw[close + 2:].split() if close >= 0 else []
    if len(fields) < 20 or not fields[19].isdigit():
        raise QuiesceHostReadError("readonly process start-ticks are invalid")
    return fields[19]


def _read_proc_environ(proc_root: Path, pid: int) -> dict[str, str] | None:
    try:
        raw = (proc_root / str(pid) / "environ").read_bytes()
    except OSError:
        return None
    environ: dict[str, str] = {}
    for item in raw.split(b"\x00"):
        if not item:
            continue
        key, separator, value = item.decode("utf-8", "replace").partition("=")
        if separator == "=":
            environ[key] = value
    return environ


def _read_proc_cgroup(proc_root: Path, pid: int) -> str | None:
    try:
        raw = (proc_root / str(pid) / "cgroup").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            return parts[2]
    return raw.strip()


def _read_boot_id(proc_root: Path) -> str | None:
    try:
        return (proc_root / "sys" / "kernel" / "random" / "boot_id").read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _scan_candidate_pids(
    proc_root: Path, *, expected_dsn_file: str, expected_lock_file: str,
) -> list[int]:
    pids: list[int] = []
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return pids
    for entry in entries:
        if not entry.name.isdigit():
            continue
        args = _read_proc_cmdline(proc_root, int(entry.name))
        if args and _is_alr_longlived_cmdline(
            args, expected_dsn_file=expected_dsn_file, expected_lock_file=expected_lock_file
        ):
            pids.append(int(entry.name))
    return sorted(pids)


def _default_runtime_digest_resolver(source_head: Any, environ: dict[str, str]) -> str | None:
    # SOURCE lane:runtime-digest 由 unit(S2.4 §8)stamp 的 ALR_EXPECTED_LEARNING_RUNTIME_DIGEST 導出。
    # EFFECT lane 的嚴格 recompute(``resolve_pinned_learning_runtime_digest`` 由 checkout 重算)DEFERRED——
    # 由 EFFECT session 注入更嚴格的 resolver;此處只證「已釘的 runtime-digest 存在且形態合法」。
    candidate = environ.get(_RUNTIME_DIGEST_ENV_KEY)
    return candidate if isinstance(candidate, str) and DIGEST_RE.fullmatch(candidate) else None


# --------------------------------------------------------------------------- #
# DB-side quiesce evidence — read ONLY through the S2.0 read-only observer role
# --------------------------------------------------------------------------- #
def _advisory_lock_split(cursor: Any, name: str) -> tuple[int, int]:
    # ``pg_try_advisory_lock(hashtext(name))`` 使用單一 bigint 形 → pg_locks 以 (classid, objid, objsubid=1)
    # 儲存 key 的高/低 32 位。hashtext 回 int4(可負),故先取 two's-complement 的 unsigned 64-bit 再切高低位,
    # 避免以 bigint 位移/或運算對負值溢位。此為唯讀 SELECT(observer 角色可執行)。
    cursor.execute("SELECT hashtext(%s)", (name,))
    signed = int(cursor.fetchone()[0])
    key = signed & 0xFFFFFFFFFFFFFFFF
    classid = (key >> 32) & 0xFFFFFFFF
    objid = key & 0xFFFFFFFF
    return classid, objid


def _consumer_session_status(cursor: Any, *, schema: str, relation: str) -> str:
    rel = f"{_safe_ident(schema)}.{_safe_ident(relation)}"
    cursor.execute(
        f"SELECT count(*) FROM {rel} AS started "
        f"WHERE started.event_kind = 'SESSION_STARTED' AND NOT EXISTS ("
        f"SELECT 1 FROM {rel} AS terminal WHERE terminal.session_id = started.session_id "
        f"AND terminal.event_kind IN ('SESSION_STOPPED', 'SESSION_FAILED', 'UNCLEAN_RECOVERY'))"
    )
    if int(cursor.fetchone()[0]) > 0:
        return "OPEN"
    cursor.execute(f"SELECT count(*) FROM {rel}")
    if int(cursor.fetchone()[0]) == 0:
        return "ABSENT"
    cursor.execute(
        f"SELECT event_kind FROM {rel} WHERE event_kind IN "
        f"('SESSION_STOPPED', 'SESSION_FAILED', 'UNCLEAN_RECOVERY') "
        f"ORDER BY recorded_at DESC, event_id DESC LIMIT 1"
    )
    row = cursor.fetchone()
    latest = str(row[0]) if row else ""
    if latest == "SESSION_STOPPED":
        return "STOPPED"
    if latest == "SESSION_FAILED":
        return "FAILED"
    # FIX-W3-2:UNCLEAN_RECOVERY(或任何非乾淨/未知終端)映射為 distinct 非 STOPPED 狀態——unclean 終端絕不可被 §5
    # queue-drained 守恆讀成「乾淨排空的 STOPPED」;只有顯式 SESSION_STOPPED 才算乾淨停止。
    return "UNCLEAN_RECOVERY"


def read_db_quiesce(
    cursor: Any, *, advisory_lock_name: str, consumer_session_relation: str
) -> dict[str, Any]:
    """Read the DB-side quiesce evidence AS the S2.0 read-only observer (§6).

    All reads are schema-qualified system-catalog / consumer-session SELECTs — reachable under the
    observer's pinned ``search_path=pg_catalog`` + ``default_transaction_read_only=on`` and the S2.0
    grant set (``GRANT SELECT`` on the declared relations).  No new privileged DB path.
    """

    classid, objid = _advisory_lock_split(cursor, advisory_lock_name)
    # holder 的 usename 由 pg_stat_activity join 取得:advisory lock 為 exclusive,理應至多一位 holder;把它
    # 綁回 ALR 連線身分(usename=aiml_engine_scanner)是 §3 訊號 #7 的可行做法(pg_locks.pid 是 server backend pid,
    # 無法和 client 的 systemd MainPID 比對)。
    cursor.execute(
        "SELECT l.pid, a.usename FROM pg_locks l "
        "LEFT JOIN pg_stat_activity a ON a.pid = l.pid "
        "WHERE l.locktype = 'advisory' AND l.classid = %s AND l.objid = %s "
        "AND l.objsubid = 1 AND l.granted",
        (classid, objid),
    )
    holder_rows = cursor.fetchall()
    holder_pids = [int(row[0]) for row in holder_rows]
    holder_usenames = [row[1] for row in holder_rows if row[1] is not None]
    holder_count = len(holder_pids)
    advisory_lock_held = holder_count > 0
    # backend_present:持有 advisory lock 的 backend 於 pg_stat_activity 現身(即 lock 綁在一個 live backend 上)。
    backend_present = bool(holder_usenames)
    advisory_holder_usename = holder_usenames[0] if holder_usenames else None
    if "." not in consumer_session_relation:
        raise QuiesceFenceError("consumer_session_relation must be schema-qualified")
    schema, _, relation = consumer_session_relation.partition(".")
    session_status = _consumer_session_status(cursor, schema=schema, relation=relation)
    # F3(EFFECT 契約備註):``pg_notification_queue_usage()`` 是**叢集層** coarse LISTEN backlog 訊號,非本 channel
    # 的 per-channel backlog,且 consumer 被 fence 後近乎 vacuous;drained 權威證據=lock 釋放+backend 消失+session STOPPED。
    cursor.execute("SELECT pg_notification_queue_usage()")
    usage = float(cursor.fetchone()[0])
    return {
        "advisory_lock_held": advisory_lock_held,
        "advisory_lock_holder_count": holder_count,
        "advisory_holder_pid": holder_pids[0] if holder_pids else None,
        "advisory_holder_usename": advisory_holder_usename,
        "backend_present": backend_present,
        "consumer_session_status": session_status,
        "listen_backlog_drained": usage < 0.5,
    }


# --------------------------------------------------------------------------- #
# owner fingerprints (§3 composite + the restart-surviving stable-identity subset)
# --------------------------------------------------------------------------- #
def compute_owner_fingerprint(
    *, main_pid: int, process_start_ticks: Any, boot_id: Any, control_group: str,
    env_hash: Any, invocation_id: str, cmdline_digest: Any, runtime_digest: Any, flock_path: str,
) -> str:
    return canonical_digest({
        "unit": UNIT_NAME,
        "main_pid": main_pid,
        "process_start_ticks": process_start_ticks,
        "boot_id": boot_id,
        "control_group": control_group,
        "env_hash": env_hash,
        "invocation_id": invocation_id,
        "cmdline_digest": cmdline_digest,
        "runtime_digest": runtime_digest,
        "advisory_lock_name": ADVISORY_LOCK_NAME,
        "flock_path": flock_path,
    })


def compute_stable_identity_fingerprint(
    *, control_group: str, env_hash: Any, cmdline_digest: Any, runtime_digest: Any,
) -> str:
    # restart 會鑄新 PID/InvocationID/start_ticks/boot_id,故 stable-identity 只取這些跨窗不變的訊號。
    return canonical_digest({
        "unit": UNIT_NAME,
        "control_group": control_group,
        "env_hash": env_hash,
        "cmdline_digest": cmdline_digest,
        "runtime_digest": runtime_digest,
        "advisory_lock_name": ADVISORY_LOCK_NAME,
    })


# --------------------------------------------------------------------------- #
# assemble the raw inventory (host_probe + observer cursor) — §3 signals #1-#8
# --------------------------------------------------------------------------- #
def build_owner_inventory(
    host_probe: Any,
    db_cursor: Any,
    *,
    intent: dict[str, Any],
    runtime_digest_resolver: Callable[[Any, dict[str, str]], str | None] | None = None,
) -> dict[str, Any]:
    """Assemble the multi-signal inventory the ownership predicate classifies (§3).

    host_probe drives the allowlisted system-level ``systemctl show`` + a SIMULATED ``/proc`` (SOURCE lane);
    db_cursor is a connection AS the S2.0 read-only observer.  Returns a raw dict (host_inventory /
    db_quiesce / credential_exposure + the scalar signals confirm_alr_owner needs).  It NEVER mutates
    anything and NEVER signals a process.
    """

    resolver = runtime_digest_resolver or _default_runtime_digest_resolver
    proc_root = Path(host_probe.proc_root)
    show = _run_show(host_probe)
    main_pid_raw = show.get("MainPID", "0")
    main_pid = int(main_pid_raw) if main_pid_raw.isdigit() else 0
    invocation_id = show.get("InvocationID", "")
    n_restarts = int(show["NRestarts"]) if show.get("NRestarts", "").isdigit() else 0
    control_group = show.get("ControlGroup", "")
    flock_path = str(intent.get("flock_path", ""))

    proc_present = main_pid > 0 and (proc_root / str(main_pid)).exists()
    start_ticks = _read_proc_stat_start_ticks(proc_root, main_pid) if proc_present else None
    cmdline = _read_proc_cmdline(proc_root, main_pid) if proc_present else None
    environ = _read_proc_environ(proc_root, main_pid) if proc_present else None
    proc_cgroup = _read_proc_cgroup(proc_root, main_pid) if proc_present else None
    boot_id = _read_boot_id(proc_root)

    cmdline_digest = canonical_digest(cmdline) if cmdline else None
    env_hash = None
    runtime_digest = None
    if environ is not None:
        # F5(EFFECT 契約備註):env-hash(§3 訊號 #5)此處僅由 live ``/proc/<pid>/environ`` 宣告鍵導出;把它與 unit 宣告的
        # ``Environment=``(system-level ``systemctl show``)交叉核對以偵測 drift/注入,DEFERRED 給 EFFECT session。
        env_hash = canonical_digest({k: environ[k] for k in ENV_DECLARED_KEYS if k in environ})
        runtime_digest = resolver(environ.get("ALR_SOURCE_HEAD"), environ)
    # §4 訊號 #4:P ∈ unit 的 cgroup(proc cgroup 含 unit 名),排除 cgroup 外的散兵 cmdline 命中。
    cgroup_match = bool(proc_cgroup) and UNIT_NAME in str(proc_cgroup)

    dsn = host_probe.dsn_stat()
    # FIX-C1/C2:approved invocation 形 = intent 宣告的 lock-file(flock_path)+ 部署 DSN 路徑(dsn_stat)。
    # 先於候選掃描算出,供 exact-invocation 收斂與 MainPID cmdline 綁定共用。
    expected_dsn_file = str(dsn["dsn_file_path"])
    expected_lock_file = flock_path
    candidate_pids = _scan_candidate_pids(
        proc_root, expected_dsn_file=expected_dsn_file, expected_lock_file=expected_lock_file
    )
    candidate_count = len(candidate_pids)
    # FIX-C2(Codex :779):MainPID 自身 cmdline 必為 exact ALR invocation;否則 wrapper MainPID 會被誤放行。
    main_pid_invocation_ok = bool(
        proc_present and cmdline and _is_alr_longlived_cmdline(
            cmdline, expected_dsn_file=expected_dsn_file, expected_lock_file=expected_lock_file
        )
    )
    scope_conflict = _scope_conflict(host_probe)

    db_quiesce_raw = read_db_quiesce(
        db_cursor,
        advisory_lock_name=intent.get("advisory_lock_name", ADVISORY_LOCK_NAME),
        consumer_session_relation=intent.get("consumer_session_relation", DEFAULT_CONSUMER_SESSION_RELATION),
    )
    # advisory_holder_pid / advisory_holder_usename 為 predicate 用的純量訊號,不進入 observation 的 db_quiesce
    # schema(schema 只認五個唯讀證據欄位)。
    advisory_holder_pid = db_quiesce_raw.pop("advisory_holder_pid")
    advisory_holder_usename = db_quiesce_raw.pop("advisory_holder_usename")
    db_quiesce = db_quiesce_raw

    credential_exposure = {
        "dsn_file_path": str(dsn["dsn_file_path"]),
        "dsn_mode": str(dsn["dsn_mode"]),
        "dsn_owner_uid": int(dsn["dsn_owner_uid"]),
        "world_readable": bool(dsn["world_readable"]),
        "plaintext_ingress": False,
        "unit_hardening": {
            "no_new_privileges": show.get("NoNewPrivileges", ""),
            "protect_system": show.get("ProtectSystem", ""),
            "private_tmp": show.get("PrivateTmp", ""),
            "restrict_address_families": show.get("RestrictAddressFamilies", ""),
        },
    }

    owner_fingerprint = compute_owner_fingerprint(
        main_pid=main_pid, process_start_ticks=start_ticks, boot_id=boot_id,
        control_group=control_group, env_hash=env_hash, invocation_id=invocation_id,
        cmdline_digest=cmdline_digest, runtime_digest=runtime_digest, flock_path=flock_path,
    )
    stable_fingerprint = compute_stable_identity_fingerprint(
        control_group=control_group, env_hash=env_hash,
        cmdline_digest=cmdline_digest, runtime_digest=runtime_digest,
    )

    host_inventory = {
        "owner": {"uid": int(dsn["dsn_owner_uid"]), "unit": UNIT_NAME},
        "process": {
            "main_pid": main_pid,
            "process_start_ticks": start_ticks,
            "boot_id": boot_id,
            "cmdline_digest": cmdline_digest,
        },
        "unit": {
            "load_state": show.get("LoadState", ""),
            "active_state": show.get("ActiveState", ""),
            "sub_state": show.get("SubState", ""),
            "fragment_path": show.get("FragmentPath", ""),
            "drop_in_paths": show.get("DropInPaths", ""),
            "need_daemon_reload": show.get("NeedDaemonReload", ""),
        },
        "cgroup": {"control_group": control_group},
        "env_hash": env_hash,
        "runtime_digest": runtime_digest,
        "restart_policy": {
            "restart": show.get("Restart", ""),
            "restart_usec": show.get("RestartUSec", ""),
            "timeout_stop_usec": show.get("TimeoutStopUSec", ""),
        },
        "watchdog": {
            "watchdog_usec": show.get("WatchdogUSec", ""),
            "n_restarts": n_restarts,
            "invocation_id": invocation_id,
        },
        "queue": {
            "listen_channel": LISTEN_CHANNEL,
            "advisory_lock_name": ADVISORY_LOCK_NAME,
            "flock_path": flock_path or "/nonexistent",
            "flock_held": bool(host_probe.flock_held()) if hasattr(host_probe, "flock_held") else None,
        },
    }

    return {
        "host_inventory": host_inventory,
        "db_quiesce": db_quiesce,
        "credential_exposure": credential_exposure,
        "candidate_count": candidate_count,
        # FIX-C2:保留候選 PID 清單與 MainPID invocation 綁定,供 _confirm_grade_signals_ok 把 owner 綁回 MainPID。
        "candidate_pids": candidate_pids,
        "main_pid_invocation_ok": main_pid_invocation_ok,
        "advisory_holder_pid": advisory_holder_pid,
        "advisory_holder_usename": advisory_holder_usename,
        "main_pid": main_pid,
        "proc_present": proc_present,
        "unit_active": (
            show.get("LoadState") == "loaded"
            and show.get("ActiveState") == "active"
            and show.get("SubState") == "running"
        ),
        "cgroup_match": cgroup_match,
        "fragment_path_match": show.get("FragmentPath", "") == str(intent.get("unit_fragment_path", "")),
        "scope_conflict": scope_conflict,
        "owner_fingerprint": owner_fingerprint,
        "stable_identity_fingerprint": stable_fingerprint,
    }


# --------------------------------------------------------------------------- #
# ownership-confirmation predicate (§3 — the safety crux)
# --------------------------------------------------------------------------- #
def _confirm_grade_signals_ok(inventory: dict[str, Any]) -> bool:
    """多訊號 confirm-grade 不變量(去掉 owner_fingerprint 綁定;供 pre-fence 判定與 FIX-C3 post-unfence 復核共用)。

    §3 全部訊號(unit-active / cgroup / env-hash / runtime-digest / advisory-lock 由 aiml_engine_scanner 單一
    backend 持有 / consumer-session OPEN / fragment-path / drop-in 空 / 無需 daemon-reload),外加 FIX-C2:唯一 ALR
    候選的 PID 必等於 unit 的 MainPID(candidate_pids == [main_pid]),且 MainPID 自身 cmdline 為 exact ALR
    invocation(main_pid_invocation_ok)——杜絕「wrapper MainPID + 脫離的 consumer 持鎖」被誤判為 confirmed。
    """

    host = inventory["host_inventory"]
    db = inventory["db_quiesce"]
    candidate_count = int(inventory["candidate_count"])
    main_pid = int(inventory["main_pid"])
    holder_count = int(db["advisory_lock_holder_count"])
    return bool(
        candidate_count == 1
        and holder_count == 1
        and not bool(inventory["scope_conflict"])
        and main_pid > 0
        # FIX-C2:唯一候選 PID == MainPID,且 MainPID cmdline 為 exact ALR invocation。
        and list(inventory.get("candidate_pids") or []) == [main_pid]
        and bool(inventory.get("main_pid_invocation_ok"))
        and bool(inventory["proc_present"])
        and bool(inventory["unit_active"])
        and bool(inventory["fragment_path_match"])
        and host["unit"]["drop_in_paths"] == ""
        and host["unit"]["need_daemon_reload"] == "no"
        and bool(inventory["cgroup_match"])
        and isinstance(host["env_hash"], str) and DIGEST_RE.fullmatch(host["env_hash"] or "")
        and isinstance(host["runtime_digest"], str) and DIGEST_RE.fullmatch(host["runtime_digest"] or "")
        and db["advisory_lock_held"] is True
        and db["backend_present"] is True
        # §3 訊號 #7:advisory lock 的 holder backend 必屬 ALR 連線身分(usename=aiml_engine_scanner),把 PG 的
        # at-most-one-owner 保證綁回這個具體 owner(而非 pid 比對——server backend pid != client MainPID)。
        and inventory["advisory_holder_usename"] == ALR_CONNECTION_ROLE
        and db["consumer_session_status"] == "OPEN"
    )


def _owner_verdict(inventory: dict[str, Any], *, expected_fingerprint: str) -> str:
    candidate_count = int(inventory["candidate_count"])
    holder_count = int(inventory["db_quiesce"]["advisory_lock_holder_count"])

    ambiguous = (
        candidate_count >= 2
        or holder_count >= 2
        or bool(inventory["scope_conflict"])
    )
    if ambiguous:
        return "AMBIGUOUS_MULTIPLE_OWNERS"

    if _confirm_grade_signals_ok(inventory) and inventory["owner_fingerprint"] == expected_fingerprint:
        return "CONFIRMED_SINGLE_OWNER"
    # 非 confirmed 且非 ambiguous → 期望的 owner 未乾淨在場(gone / drift / wrapper MainPID)→ fail-closed STALE
    # (不 fence 一個不確定的 owner,以免遮蔽另一個 live owner)。
    return "STALE_OWNER"


def confirm_alr_owner(
    inventory: dict[str, Any],
    *,
    expected_fingerprint: str,
    applier_node: str,
    verifier_node: str,
    verifier_capture_digest: str,
    observed_at: str,
    ttl_seconds: int = EVIDENCE_TTL_SECONDS,
) -> dict[str, Any]:
    """Return the phase PRE_FENCE_INVENTORY ``quiesce_observation_v1`` with exactly one verdict (§3)."""

    # 延遲匯入上層 observation builder(免 import 期循環;fence 模組載入後始被呼叫)。
    from agent_governance_alr_quiesce_fence import build_quiesce_observation

    verdict = _owner_verdict(inventory, expected_fingerprint=expected_fingerprint)
    return build_quiesce_observation(
        phase="PRE_FENCE_INVENTORY", verdict=verdict,
        candidate_count=int(inventory["candidate_count"]),
        owner_fingerprint=inventory["owner_fingerprint"],
        host_inventory=inventory["host_inventory"], db_quiesce=inventory["db_quiesce"],
        credential_exposure=inventory["credential_exposure"],
        applier_node=applier_node, verifier_node=verifier_node,
        verifier_capture_digest=verifier_capture_digest, observed_at=observed_at, ttl_seconds=ttl_seconds,
    )


# --------------------------------------------------------------------------- #
# bounded observation-window static guards (§5 — injected monotonic clock)
# --------------------------------------------------------------------------- #
def _classify_static_guard(inventory: dict[str, Any], baseline: dict[str, Any]) -> str:
    host = inventory["host_inventory"]
    db = inventory["db_quiesce"]
    no_restart = (
        host["unit"]["active_state"] == "inactive"
        and int(host["watchdog"]["n_restarts"]) <= int(baseline["n_restarts"])
        and host["watchdog"]["invocation_id"] == ""
    )
    queue_drained = (
        db["advisory_lock_held"] is False
        and db["backend_present"] is False
        and db["consumer_session_status"] == "STOPPED"
        and db["listen_backlog_drained"] is True
    )
    if not no_restart:
        return "RESTART_DETECTED"
    if not queue_drained:
        return "QUEUE_NOT_DRAINED"
    return "STATIC_GUARDS_HELD"


def collect_static_guard_window(
    host_probe: Any,
    db_cursor: Any,
    *,
    intent: dict[str, Any],
    baseline: dict[str, Any],
    applier_node: str,
    verifier_node: str,
    verifier_capture_digest: str,
    clock: Callable[[], float],
    observed_at_base: str,
    sleep: Callable[[float], None] | None = None,
    runtime_digest_resolver: Callable[[Any, dict[str, str]], str | None] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Collect IN_WINDOW static-guard samples at the declared cadence (INJECTED monotonic clock).  Returns
    ``(samples, window_status)`` ∈ {HELD, VIOLATED, UNDERSPECIFIED}: HELD = ``>= min_samples`` all-held samples
    spanning ``>= duration_seconds``; VIOLATED = a GENUINE non-held sample (restart / queue-not-drained) → applier
    maps to ``OBSERVATION_WINDOW_VIOLATED``; UNDERSPECIFIED = all-held but inadequate (too few samples / span <
    duration / hit ``MAX_WINDOW_SAMPLES`` / elapsed beyond the declared-window deadline) → applier maps to a typed
    ``FAILED``, DISTINCT from VIOLATED (FIX-W3-1c).  FIX-W3-1(b):the sampler CONSUMES ``sample_interval_seconds``
    via the injected ``sleep`` between samples (SOURCE lane never real-sleeps; EFFECT injects real ``time.sleep`` +
    monotonic clock); with the ``MAX_WINDOW_SAMPLES`` ceiling it can never spin (a non-advancing clock ends as
    ``UNDERSPECIFIED``).

    FIX-C4(Codex :1177):a HARD total-elapsed deadline (``duration_seconds`` + one cadence step) caps the window
    so the fence can NEVER be held beyond the declared window even under a lying/jumping injected clock; the
    pathological ``(min_samples-1)*interval > duration`` config is already rejected at intent build/validate.
    """

    # 延遲匯入上層 observation builder + 時間投影(免 import 期循環)。
    from agent_governance_alr_quiesce_fence import build_quiesce_observation, _plus_seconds

    window = intent["observation_window"]
    min_samples = int(window["min_samples"])
    duration = int(window["duration_seconds"])
    interval = int(window["sample_interval_seconds"])
    # FIX-C4 硬截止:總經過時間(注入單調時鐘)不得超過宣告窗一個節奏步(duration + interval)。intent build/
    # validate 已擋 (min_samples-1)*interval > duration 的病態設定;此處為執行期防禦——注入時鐘暴走(如一步跨數百
    # 小時)絕不再取樣、絕不 HELD,回 UNDERSPECIFIED(applier 映射 typed FAILED 並嘗試 un-fence)。
    hard_deadline_seconds = duration + interval
    pace = sleep if sleep is not None else (lambda _seconds: None)
    samples: list[dict[str, Any]] = []
    first_t: float | None = None
    while True:
        current = float(clock())
        if first_t is None:
            first_t = current
        elapsed = current - first_t
        if elapsed > hard_deadline_seconds:
            # 已跨過宣告窗上限仍未完成 held 窗 → 硬截止,絕不再取樣(fence 不被持有超出宣告窗)。
            return samples, WINDOW_STATUS_UNDERSPECIFIED
        inventory = build_owner_inventory(
            host_probe, db_cursor, intent=intent, runtime_digest_resolver=runtime_digest_resolver,
        )
        verdict = _classify_static_guard(inventory, baseline)
        samples.append(build_quiesce_observation(
            phase="IN_WINDOW_STATIC_GUARD", verdict=verdict,
            candidate_count=int(inventory["candidate_count"]),
            owner_fingerprint=inventory["owner_fingerprint"],
            host_inventory=inventory["host_inventory"], db_quiesce=inventory["db_quiesce"],
            credential_exposure=inventory["credential_exposure"],
            applier_node=applier_node, verifier_node=verifier_node,
            verifier_capture_digest=verifier_capture_digest,
            # observed_at 反映**真實**經過的注入時鐘時間(非樣本序號),讓 FIX-W3-1d 的跨度再驗(span>=duration)自洽。
            observed_at=_plus_seconds(observed_at_base, max(0, int(round(elapsed)))),
        ))
        if verdict != "STATIC_GUARDS_HELD":
            return samples, WINDOW_STATUS_VIOLATED  # 帶真 non-held 樣本 → 真 window violation
        if len(samples) >= min_samples and elapsed >= duration:
            # 樣本數 >= min_samples 且真實跨度 >= duration_seconds(且仍在硬截止內)→ HELD。
            return samples, WINDOW_STATUS_HELD
        if len(samples) >= MAX_WINDOW_SAMPLES:
            return samples, WINDOW_STATUS_UNDERSPECIFIED  # 注入 clock 未前進到滿足 duration 的取樣上限 → underspecified
        pace(interval)  # 以宣告節奏在下一取樣前等待 sample_interval_seconds(注入式;SOURCE lane 絕不真 sleep)

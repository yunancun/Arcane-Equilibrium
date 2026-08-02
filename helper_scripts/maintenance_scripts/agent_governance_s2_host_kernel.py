"""S2E.2a:S2 受信主機 runner 家族的**唯一執行核心**(kernel)。

本模組是「S2 host runner 家族」裡**唯一**被允許呼叫 ``subprocess`` 的檔案(結構測試
``test_agent_governance_s2_host_kernel.py`` 以 AST 掃描執法:``subprocess`` / ``os.system`` /
``os.popen`` / ``shell=True`` / ``eval`` / ``exec`` / ``__import__`` 只准出現在此檔)。它提供五件、
且**只有**五件,四個 S2 effect adapter 的主機面共通需要的東西:

1. :data:`SESSION_ARGV_ALLOWLISTS` —— per-session 的**封閉** argv allowlist,由既有 owner 模組
   **導出**(非手抄):S2.1 段直接呼叫 ``agent_governance_alr_quiesce_inventory._show_command()``
   並逐條經該模組自己的 ``_assert_allowlisted_systemctl`` 自檢。任一漂移在 import 期即炸。
2. :class:`HostExecutionKernel` —— ``shell=False`` / argv[0] 絕對路徑 / sanitized env allowlist /
   固定 timeout / 輸出 redact 的單一 exec 點,且 ``session`` 為**必填**建構參數並綁一個封閉
   allowlist(沒有 "generic" session,故本 kernel 不會退化成通用 exec service)。
3. :func:`derive_host_target_class` —— target class 由**主機事實**導出,**絕不**收 caller 字串;
   命中釘死的 target hostname 即支配一切供裝訊號(導出面只回 ``non_target`` / ``production`` /
   ``unknown``,``unknown`` 與 ``production`` 同等對待,rehearsal-only 的 ``disposable_candidate``
   永不被導出)。搭配 :func:`host_target_admission_errors`(對同一份導出視圖的薄准入謂詞,另把
   intent 自宣告的 ``target_class`` 綁到導出的主機 class),讓 runner 在**構造任何 driver 之前**
   就能 typed 拒絕。
4. :func:`host_wall_clock_time` —— 本機牆鐘的 UTC 讀值(純敘述性,不帶 trust 語義;
   與 adapter driver Protocol 的 ``trusted_host_time`` 是兩件事,故刻意不同名)。
5. :func:`assert_read_only_surface` —— 鏡 ``agent_governance_s2_4_install_driver
   .assert_no_aggregate_forbidden_surface``:物件上出現任一寫能力方法即 typed 拒,且**絕不呼叫**。

S2E-LW1 的 recovery host-capture 另共用同一 exec point：root-owned attestor 的固定
path/protocol 由本 kernel 封閉；attestor 只能走零輸入、bounded output 的專用方法，不能經
generic :meth:`HostExecutionKernel.run` 呼叫。source head、host facts、process identity、clock
與 SSHSIG 全由該 capability 自主採集，producer 不再把 mutable-checkout claims 送去代簽。

外加兩件與 exec / 出境不可分割的執法:

* :func:`enforce_process_hardening` 在**每一次**主機指令執行之前真的跑 ``prctl(PR_SET_DUMPABLE, 0)``
  並回讀 ``PR_GET_DUMPABLE`` 確認為 0,不為 0 即拒絕執行。
* :func:`scan_serializable_surface_for_secrets` 是家族共用的**出境守衛**:任何 payload 進 sink
  (observer child 的 stdout、CLI 的 ``observation.json``)之前必須先過它,判準直接取自
  ``agent_governance_command_capture_v2.SECRET_VALUE_PATTERNS``(與 :func:`_redact` 同一套規則,
  不另造第二套),命中即整包丟棄。

**W5 obligation #21 的誠實措辭(必讀)。** ``PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED`` 的原文要求
是「observing prctl(PR_GET_DUMPABLE) on the applier and refusing when it is not 0 —— a
driver-protocol and host-observation change」,而它指的 applier 是 **S2.4/S2.5 的 driver
protocol**,那條路徑**完全不經本 kernel**。因此:本 kernel 只是**提供可翻 #21 的證據**(repo 內
第一處真的觀測並拒絕的實作),**obligation 本身仍 OPEN**,批次裁決留給 S2E.5。本波對 W5 ledger
零編輯。

**誠實界線(必讀)。**

* 本模組是 **L1 主機安全層**,不是證據完整性層。它只決定「今天要不要碰這台主機」;
  「即使 driver 在手也不可能 emit APPLIED」是 adapter 的 L2 閘(permit 驗簽 / trusted-host
  attestation),「封包不可 PASS」是 closure 的 L3 閘。本波對 L2/L3 **一行不動**。
* :func:`host_wall_clock_time` 回的是**這台主機自己的**牆鐘讀值,**不是** attestation,不承載
  任何 trust 語義。真正解鎖 APPLIED 的 signed ``trusted_host_time`` 仍只能來自 driver 的簽章
  attestation(S2.0 §9b/§9c);那個 ``trusted_host_time`` 是 driver Protocol 方法名兼**已簽**
  payload 欄位名(frozen),與本 kernel 的匯出面同名只會誤導,故本 kernel 用不同名字。
* 本模組對四個 S2 adapter 模組**零行修改**:刪掉整個 runner 家族,四個 adapter 的行為與今日
  逐位元組相同(全部 ``EXTERNAL_VERIFICATION_PENDING``)。
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import re
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

# 唯讀消費:S2.1 的 inventory 下層(它 top-level 不匯入 fence 上層,且明文「絕不 signal 真 process、
# 絕不 stop/start」),用來**導出** S2.1 的唯讀 argv allowlist。本 kernel **不**匯入任何 S2 apply
# 進入點模組(pg_observer_bootstrap / alr_quiesce_fence / s2_4_* / s2_5_*),故 observer 的
# import-closure ∩ applier == ∅ 可以成立。
import agent_governance_alr_quiesce_inventory as quiesce_inventory  # noqa: E402
from aiml_gate_receipt_s2_5_host_capture import (  # noqa: E402
    HOST_CAPTURE_ATTESTOR_CAPABILITY_PATH,
    HOST_CAPTURE_ATTESTOR_CAPABILITY_PROTOCOL,
)


class S2HostKernelError(RuntimeError):
    """Base for any refusal raised by the S2 host kernel (fail-closed, never a silent fallback)."""


class S2HostArgvNotAllowlisted(S2HostKernelError):
    """Raised when an argv is not literally in the session's closed allowlist."""


class S2HostSessionError(S2HostKernelError):
    """Raised when the requested session / mutation posture is not a declared one."""


class S2HostTargetRefused(S2HostKernelError):
    """Raised when the derived host target class refuses the requested run."""


class S2HostCommandFailed(S2HostKernelError):
    """Raised when an allowlisted host command exits non-zero / times out."""


# --------------------------------------------------------------------------- #
# (1) sessions + derived closed argv allowlists
# --------------------------------------------------------------------------- #
# session 是**必填**且封閉的:沒有 "generic" session,故 kernel 不能被當成通用 exec service(R5)。
SESSION_S2_0_OBSERVER_BOOTSTRAP = "s2_0_pg_observer_bootstrap"
SESSION_S2_1_QUIESCE_READ = "s2_1_quiesce_read"
SESSION_S2_1_QUIESCE_FENCE = "s2_1_quiesce_fence"
SESSION_S2_5_RECOVERY_HOST_CAPTURE = "s2_5_recovery_host_capture"
# 唯讀 observer 的**進程分離**子行程(§B.2 L2)。它沒有字面 allowlist:argv 由
# :meth:`HostExecutionKernel.run_observer_child` 於 kernel 內部**構造**(解譯器 + ``-E`` + 絕對
# 腳本路徑 + 一段經 charset/大小驗證的 base64 request),caller 永遠遞不進 argv。
SESSION_S2_HOST_OBSERVER_CHILD = "s2_host_observer_child"

RECOVERY_HOST_CAPTURE_ATTESTOR_ARGV = (
    HOST_CAPTURE_ATTESTOR_CAPABILITY_PATH,
    "--protocol",
    HOST_CAPTURE_ATTESTOR_CAPABILITY_PROTOCOL,
)
MAX_RECOVERY_HOST_CAPTURE_ARTIFACT_BYTES = 64 * 1024

# 只有 fence session 允許變更主機狀態,且必須由 caller 顯式 ``allow_mutation=True`` 承認。
MUTATING_SESSIONS = frozenset({SESSION_S2_1_QUIESCE_FENCE})

# 任一 allowlisted argv 都不得帶這些 token(縱深防禦;列名是為了 typed 錯誤訊息)。``--user`` 在此
# 特別重要:S2.4 §8 的 unit 是 system-level,任何 ``--user`` 形都會觀測到**錯誤的** manager。
FORBIDDEN_ARGV_TOKENS = frozenset({
    "--user", "--global", "--host", "-H", "-M", "--machine",
    "kill", "restart", "try-restart", "reload", "daemon-reload", "daemon-reexec",
    "mask", "unmask", "edit", "set-property", "link", "revert", "isolate",
    "poweroff", "reboot", "halt", "kexec", "switch-root",
})
# 唯讀 session 另外禁止的生命週期動詞(fence session 才可用 stop/start,且只有那兩個)。
READ_ONLY_FORBIDDEN_VERBS = frozenset({"stop", "start", "enable", "disable", "reset-failed"})


def _derive_quiesce_read_argv() -> tuple[tuple[str, ...], ...]:
    """由 S2.1 的 owner 模組**導出**唯讀 argv 集合(不是手抄一份平行 allowlist)。

    ``_show_command()`` 是 ``_run_show`` 實際送出的那一條;list-units 一條在 owner 的
    ``_scope_conflict`` 內以字面量構造,故此處以同一組字面量重建後,**逐條**丟回 owner 自己的
    ``_assert_allowlisted_systemctl`` 求證——owner 若收窄 allowlist,本模組 import 期即炸。結構測試
    另以「錄音式 host_probe 驅動 ``build_owner_inventory``」比對實際送出的 argv 集合 ≡ 本表,
    使「導出」不只是聲稱。
    """

    show = tuple(quiesce_inventory._show_command())
    scope = (
        quiesce_inventory.SYSTEMD, "list-units", "--type=scope", "--state=active",
        "--no-legend", "--no-pager",
    )
    derived = (show, scope)
    for argv in derived:
        quiesce_inventory._assert_allowlisted_systemctl(list(argv))
    return derived


def _derive_quiesce_fence_argv() -> tuple[tuple[str, ...], ...]:
    """S2.1 的 fence/un-fence = 該 unit **自身**的 system-level stop/start(§4)。

    unit 名與 systemctl 路徑同樣由 owner 模組導出;此處**不**新增任何 caller unit-name/pattern/pid
    參數面(那正是 registry invariant「owner-scoped stop only ... NEVER pkill/kill-by-name/
    kill-by-pattern/kill-by-pid」所禁止的縫)。
    """

    return (
        (quiesce_inventory.SYSTEMD, "stop", quiesce_inventory.UNIT_NAME),
        (quiesce_inventory.SYSTEMD, "start", quiesce_inventory.UNIT_NAME),
    )


SESSION_ARGV_ALLOWLISTS: dict[str, frozenset[tuple[str, ...]]] = {
    # S2.0 的主機面**沒有任何 argv**:observer 走 local socket 的 PG library(直接 ``psql`` 被治理
    # preflight 明文拒絕,見 agent_governance_permissions 的 psql 分支),故其 allowlist 恆為空集
    # ——任何試圖從 S2.0 session 執行外部指令的呼叫一律 typed 拒。
    SESSION_S2_0_OBSERVER_BOOTSTRAP: frozenset(),
    SESSION_S2_1_QUIESCE_READ: frozenset(_derive_quiesce_read_argv()),
    SESSION_S2_1_QUIESCE_FENCE: frozenset(_derive_quiesce_fence_argv()),
    SESSION_S2_5_RECOVERY_HOST_CAPTURE: frozenset({
        RECOVERY_HOST_CAPTURE_ATTESTOR_ARGV,
    }),
    # observer child 的 argv 由 kernel 構造,故字面 allowlist 為空 ⇒ ``run()`` 對此 session 恆拒。
    SESSION_S2_HOST_OBSERVER_CHILD: frozenset(),
}

# per-session 固定 timeout(code-owned,caller 不可放大)。fence 需容納 unit 的 TimeoutStopUSec。
SESSION_TIMEOUT_SECONDS: dict[str, int] = {
    SESSION_S2_0_OBSERVER_BOOTSTRAP: 30,
    SESSION_S2_1_QUIESCE_READ: 30,
    SESSION_S2_1_QUIESCE_FENCE: 120,
    SESSION_S2_5_RECOVERY_HOST_CAPTURE: 30,
    SESSION_S2_HOST_OBSERVER_CHILD: 120,
}

# observer child 的 code-owned 進入點與 request 上限(防 execve 的 MAX_ARG_STRLEN / E2BIG)。
OBSERVER_CHILD_SCRIPT = HELPER_DIR / "agent_governance_s2_host_observer.py"
OBSERVER_CHILD_FLAG = "--request-base64"
OBSERVER_CHILD_MAX_REQUEST_BYTES = 8192
_BASE64_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/]+={0,2}$")


def _assert_allowlist_shape() -> None:
    """import 期自檢:allowlist 不得含禁用 token,唯讀 session 不得含生命週期動詞。"""

    for session, allowlist in SESSION_ARGV_ALLOWLISTS.items():
        for argv in allowlist:
            if not argv or not str(argv[0]).startswith("/"):
                raise S2HostKernelError(f"session {session} allowlists a non-absolute argv[0]: {argv!r}")
            tokens = set(argv[1:])
            forbidden = tokens & FORBIDDEN_ARGV_TOKENS
            if forbidden:
                raise S2HostKernelError(
                    f"session {session} allowlists forbidden tokens {sorted(forbidden)}"
                )
            if session not in MUTATING_SESSIONS:
                verbs = tokens & READ_ONLY_FORBIDDEN_VERBS
                if verbs:
                    raise S2HostKernelError(
                        f"read-only session {session} allowlists lifecycle verbs {sorted(verbs)}"
                    )


_assert_allowlist_shape()


def session_argv_allowlist(session: str) -> frozenset[tuple[str, ...]]:
    """Return the closed argv allowlist of one declared session (unknown session -> typed refusal)."""

    if session not in SESSION_ARGV_ALLOWLISTS:
        raise S2HostSessionError(
            f"unknown S2 host session {session!r}; the kernel has no generic session"
        )
    return SESSION_ARGV_ALLOWLISTS[session]


def assert_session_argv(session: str, argv: Iterable[str]) -> tuple[str, ...]:
    """Independent re-assert of the session allowlist (the *only* admission for a host command).

    ``QuiesceHostProbe.run`` 亦呼叫本函式,故「繞過 owner 模組直呼 probe」也擋得住(S2.1 今日的
    ``_assert_allowlisted_systemctl`` 只在 caller 側,``host_probe.run(argv)`` 本身收任意 argv)。
    """

    allowlist = session_argv_allowlist(session)
    if isinstance(argv, (str, bytes)):
        raise S2HostArgvNotAllowlisted("argv must be a sequence of strings, never a shell string")
    candidate = tuple(argv)
    if not candidate or not all(isinstance(token, str) for token in candidate):
        raise S2HostArgvNotAllowlisted("argv must be a non-empty sequence of strings")
    if candidate not in allowlist:
        raise S2HostArgvNotAllowlisted(
            f"argv is not in the closed allowlist of session {session!r}"
        )
    return candidate


def observer_child_argv(request_base64: str) -> list[str]:
    """唯一的 read-only observer child argv 構造點(鏡 S2.5 ``allowlisted_systemctl_argv`` 的形制)。

    caller 永遠遞不進 argv:解譯器、``-E``(忽略 ``PYTHON*`` env ⇒ 防 ``PYTHONPATH`` 注入)、絕對
    腳本路徑與旗標名全是 code-owned 常量,唯一變動處是一段必須通過 charset + 大小檢查的 base64
    request。任何非 base64 charset / 超長 payload 一律 typed 拒(後者同時是 ``E2BIG`` 護欄)。
    """

    if not isinstance(request_base64, str) or not _BASE64_TOKEN_RE.fullmatch(request_base64):
        raise S2HostArgvNotAllowlisted(
            "observer child request must be a strict base64 token (no shell metacharacters)"
        )
    if len(request_base64) > OBSERVER_CHILD_MAX_REQUEST_BYTES:
        raise S2HostArgvNotAllowlisted(
            f"observer child request exceeds {OBSERVER_CHILD_MAX_REQUEST_BYTES} bytes"
        )
    return [sys.executable, "-E", str(OBSERVER_CHILD_SCRIPT), OBSERVER_CHILD_FLAG, request_base64]


# --------------------------------------------------------------------------- #
# process hardening (W5 #21: PR_SET_DUMPABLE must be LOAD-BEARING, not declared)
# --------------------------------------------------------------------------- #
_PR_GET_DUMPABLE = 3
_PR_SET_DUMPABLE = 4
_HARDENING_CACHE: dict[str, Any] | None = None


def enforce_process_hardening(*, force: bool = False) -> dict[str, Any]:
    """真的執法 ``PR_SET_DUMPABLE=0``:設定 → 回讀 → 不為 0 即拒絕跑任何主機指令。

    本函式是那個「觀測 + 拒絕」,且被 :meth:`HostExecutionKernel.run` /
    :meth:`HostExecutionKernel.run_observer_child` 在**每一次** exec 之前以 ``force=True`` 呼叫
    ——E2 P2 #10:快取會使觀測只發生一次,那樣的話「執法」在第二條指令起就只是一份舊紀錄。
    ``force=False`` 只保留給純查詢用途。

    誠實界線(E2 P2 #7:原本的理由字串是**假的**):非 Linux 主機沒有 prctl,回
    ``enforced=False``;但本行程**仍然會**在此 session 執行 allowlisted 指令(例如唯讀 observer
    child),所以絕不可把這份觀測讀成「這裡沒有 exec,所以不必執法」。真正把生產主機擋在外面的
    是 :func:`derive_host_target_class`(非 Linux 恆為 ``non_target``)與 L1 准入謂詞,不是這一行
    理由字串。
    """

    global _HARDENING_CACHE
    if _HARDENING_CACHE is not None and not force:
        return dict(_HARDENING_CACHE)
    if sys.platform != "linux":
        observation = {
            "enforced": False,
            "observed_dumpable": None,
            "reason": (
                "prctl(PR_SET_DUMPABLE) is a Linux facility and cannot be observed on this "
                "platform; allowlisted commands may still execute here, so this is an honest "
                "NOT-ENFORCED observation, not a claim that nothing executes"
            ),
        }
        _HARDENING_CACHE = observation
        return dict(observation)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(_PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), "prctl(PR_SET_DUMPABLE, 0) failed")
        observed = int(libc.prctl(_PR_GET_DUMPABLE, 0, 0, 0, 0))
    except (OSError, AttributeError, ValueError) as error:  # noqa: PERF203
        raise S2HostKernelError(
            f"cannot enforce PR_SET_DUMPABLE=0 on the applier process; refusing to run: {error}"
        ) from error
    if observed != 0:
        raise S2HostKernelError(
            f"PR_GET_DUMPABLE observed {observed!r} after PR_SET_DUMPABLE=0; refusing to run"
        )
    observation = {"enforced": True, "observed_dumpable": 0, "reason": None}
    _HARDENING_CACHE = observation
    return dict(observation)


# --------------------------------------------------------------------------- #
# (3) host target class — derived from HOST FACTS, never from a caller string
# --------------------------------------------------------------------------- #
# 釘死的 target 主機集合(與 S1.6B 的 ``EXPECTED_TARGET_HOST_DEFAULT`` 同一台;結構測試以導出比對
# 釘住,不在本檔重新發明主機名)。
TARGET_HOSTNAMES = frozenset({"trade-core"})
# S2.4 §8.3 / §8.1 的固定安裝面(結構測試以 ``agent_governance_s2_4_apply`` 的常量比對釘住;本檔
# **不**匯入該 applier 模組,以維持 observer 的 import-closure ∩ applier == ∅)。
SYSTEMD_SYSTEM_UNIT_DIR = "/etc/systemd/system"
CANONICAL_INSTALL_ROOTS = (
    "/opt/arcane-equilibrium/aiml/runtimes",
    "/opt/arcane-equilibrium/aiml/apps",
    "/opt/arcane-equilibrium/aiml/launches",
)

TARGET_CLASS_NON_TARGET = "non_target"
TARGET_CLASS_DISPOSABLE_CANDIDATE = "disposable_candidate"
TARGET_CLASS_PRODUCTION = "production"
TARGET_CLASS_UNKNOWN = "unknown"
# ``unknown`` 與 ``production`` **同等對待**:兩者都必須滿足 :func:`host_target_admission_errors`
# 的四條件才可執行。
PRODUCTION_GRADE_TARGET_CLASSES = frozenset({TARGET_CLASS_PRODUCTION, TARGET_CLASS_UNKNOWN})
# **rehearsal-only class(P1-A 的處置)**:``disposable_candidate`` 不是一件可從主機事實導出的事實,
# 只在 rehearsal 的**注入面**上成立(:func:`rehearsal_target_refusals`,且注入只能加嚴)。
# :func:`derive_host_target_class` 因此永遠不回它,兩支由主機事實驅動的准入謂詞則一律拒它。
REHEARSAL_ONLY_TARGET_CLASSES = frozenset({TARGET_CLASS_DISPOSABLE_CANDIDATE})
# 可由主機事實導出的完整值域(結構測試以此釘住「導不出 rehearsal-only class」)。
DERIVABLE_TARGET_CLASSES = frozenset({
    TARGET_CLASS_NON_TARGET, TARGET_CLASS_PRODUCTION, TARGET_CLASS_UNKNOWN,
})

# intent 側的 ``target_class`` 是**另一個**命名空間(S2.0/S2.1 adapter 的 schema:
# ``production`` / ``disposable_local``),與上面那組由主機事實導出的 host class 不是同一件事。
# kernel 不匯入任何 applier 模組(observer 的 import-closure 硬邊界),故在此以字面量宣告,
# 由結構測試對兩個 adapter 的常量逐字比對釘死。
INTENT_TARGET_CLASS_PRODUCTION = "production"
INTENT_TARGET_CLASS_DISPOSABLE_LOCAL = "disposable_local"
INTENT_TARGET_CLASSES = frozenset({
    INTENT_TARGET_CLASS_PRODUCTION, INTENT_TARGET_CLASS_DISPOSABLE_LOCAL,
})


def _writable(path: str) -> bool | None:
    """True/False;不可判定(例如 stat 失敗)回 None → target class 落 ``unknown``。"""

    try:
        if not os.path.isdir(path):
            return False
        return os.access(path, os.W_OK)
    except OSError:
        return None


def _present(path: str) -> bool | None:
    try:
        return os.path.exists(path)
    except OSError:
        return None


def _observed_nodename() -> str:
    """與 S1.6B **同一個來源**取主機名(E2 P2 #12)。

    ``agent_governance_target_host_probe.preflight_target_host`` 用的是 ``os.uname().nodename``;
    本 kernel 原本用 ``socket.gethostname()``,兩者在部分設定下會不一致 ⇒ 同一台主機可能被兩個
    S2/S1 元件判成不同身分。統一成 ``os.uname().nodename``(缺該 API 的平台退回
    ``socket.gethostname()``)。
    """

    uname = getattr(os, "uname", None)
    if uname is not None:
        try:
            return str(uname().nodename)
        except OSError:  # pragma: no cover - 依平台而定
            pass
    return socket.gethostname()


def _hostname_labels(hostname: str) -> tuple[str, ...]:
    """``trade-core`` 與 ``trade-core.internal`` 都視為同一台 target(FQDN nodename 護欄)。

    誠實界線:這**只**會把一台原本落 ``non_target``(=無條件拒絕)的主機移進三條件 production
    閘,絕不會放寬任何既有的 production 准入 —— production 仍需 ``--allow-production`` + 已驗證
    operator SSHSIG + ``--production-confirm`` 三者並存。
    """

    return tuple({hostname, hostname.split(".")[0]})


def derive_host_target_class() -> dict[str, Any]:
    """由**主機事實**導出 target class;**絕不**接受 caller 傳入的 target_class 字串。

    這是 L1 不可被 L2 取代的原因:``target_class`` 今日在 S2.5 是 caller 參數
    (``apply_s2_5_start(target_class=...)``)、在 S2.4 的 plan/probe schema 根本不存在——
    「我在拋棄式主機上」目前完全是呼叫端自我宣告。runner 是唯一能把它變成主機導出事實的地方。

    **分類優先序(P1-A 的處置;順序本身就是安全性質)。**

    1. ``platform != linux`` → ``non_target``。非 Linux 主機沒有 systemd,結構上不可能是 S2 目標。
    2. hostname 不在 :data:`TARGET_HOSTNAMES` → ``non_target``。
    3. hostname **在** :data:`TARGET_HOSTNAMES` → 這台就是被釘死的生產目標主機,**該事實支配**
       其餘所有訊號:``production``(可寫 unit dir + canonical roots 齊備)或 ``unknown``(其餘一切)。

    先前的版本在第 3 步之下多一條「unit dir 不可寫 **且** canonical roots 全缺 → ``disposable_candidate``」
    的分支,而 ``disposable_candidate`` 在准入謂詞裡是**無條件放行**的。那兩個訊號都是**易變的**:
    unit dir 的可寫性只反映本行程的 euid(非 root 執行即為不可寫),canonical roots 的存在與否只反映
    供裝進度(初始供裝 / 恢復期恆為全缺)。於是一台**貨真價實的 trade-core**,只要在初始供裝期以
    非 root 身分跑一次,就會被分類成 ``disposable_candidate`` 而跳過三條 production 承認。

    hostname 相反地是**穩定且被釘死**的身分宣告。因此優先序是「hostname 支配供裝訊號」:命中 target
    hostname 之後,供裝訊號只能在 ``production`` 與 ``unknown`` 之間做選擇,而 ``unknown`` 與
    ``production`` 同等對待 ⇒ 任何一種供裝狀態都落在三條件閘之內(fail-closed 方向)。代價是「一台
    真的叫 trade-core 的拋棄式 VM」會被當成生產主機看待 —— 那正是正確的保守方向:一台拋棄式主機
    **不可能**被主機事實證明成拋棄式(那正是 L1 要收掉的自我宣告洞),所以 ``disposable_candidate``
    從此只是 rehearsal 注入面的 class(:data:`REHEARSAL_ONLY_TARGET_CLASSES`),導出面永不回它。
    """

    facts: dict[str, Any] = {
        "platform": sys.platform,
        # 主機名與 S1.6B 同源(``os.uname().nodename``);兩者一併落盤以便任何漂移可被看見。
        "hostname": _observed_nodename(),
        "hostname_via_socket": socket.gethostname(),
        "systemd_system_unit_dir": SYSTEMD_SYSTEM_UNIT_DIR,
        "systemd_system_unit_dir_writable": None,
        "canonical_install_roots": list(CANONICAL_INSTALL_ROOTS),
        "canonical_install_roots_present": None,
        "euid": os.geteuid() if hasattr(os, "geteuid") else None,
    }
    if sys.platform != "linux":
        return {
            "target_class": TARGET_CLASS_NON_TARGET,
            "reason": "platform is not linux; this is not an S2 target host",
            "facts": facts,
        }
    if not set(_hostname_labels(str(facts["hostname"]))) & TARGET_HOSTNAMES:
        return {
            "target_class": TARGET_CLASS_NON_TARGET,
            "reason": (
                f"hostname {facts['hostname']!r} is not in the pinned S2 target host set "
                f"{sorted(TARGET_HOSTNAMES)}"
            ),
            "facts": facts,
        }
    writable = _writable(SYSTEMD_SYSTEM_UNIT_DIR)
    roots = [_present(root) for root in CANONICAL_INSTALL_ROOTS]
    facts["systemd_system_unit_dir_writable"] = writable
    facts["canonical_install_roots_present"] = roots
    if writable is None or any(value is None for value in roots):
        return {
            "target_class": TARGET_CLASS_UNKNOWN,
            "reason": (
                "the systemd unit directory or the canonical install roots are not decidable on "
                "this host; unknown is treated exactly like production"
            ),
            "facts": facts,
        }
    if writable and all(roots):
        return {
            "target_class": TARGET_CLASS_PRODUCTION,
            "reason": (
                "linux target hostname with a writable system unit directory and all canonical "
                "install roots present"
            ),
            "facts": facts,
        }
    if not writable and not any(roots):
        # P1-A:這**曾經**是 ``disposable_candidate`` 分支。一個未供裝 / 非 root 的視圖是供裝階段的
        # 訊號,不是「這台是拋棄式主機」的證明 —— 命中 target hostname 的主機一律留在 production 閘內。
        return {
            "target_class": TARGET_CLASS_UNKNOWN,
            "reason": (
                "the pinned target hostname is present but the host is unprovisioned from this "
                "process's view (no writable system unit directory, no canonical install root); "
                "that is a provisioning-stage signal, never a proof of a disposable host, so "
                "unknown is treated exactly like production"
            ),
            "facts": facts,
        }
    return {
        "target_class": TARGET_CLASS_UNKNOWN,
        "reason": (
            "the host is partially provisioned (unit directory writability and canonical install "
            "roots disagree); unknown is treated exactly like production"
        ),
        "facts": facts,
    }


def host_target_admission_errors(
    target_view: dict[str, Any],
    *,
    allow_production: bool,
    production_confirm: Any,
    intent_digest: Any,
    operator_authorization_verified: bool,
    intent_target_class: Any,
) -> list[str]:
    """L1 准入謂詞:``production`` / ``unknown`` 必須**四**條件並存,否則 typed 拒(driver 永不構造)。

    (a) CLI 顯式 ``--allow-production``;
    (b) 已驗證的 operator SSHSIG(綁 exact intent digest + source_head + target_host——驗簽本身屬
        adapter 的 L2 閘,呼叫端把「已驗證」這個布林事實遞進來);
    (c) ``--production-confirm <intent_digest>`` 逐字回填(防手滑 / 防貼上);
    (d) **intent 自己宣告的 ``target_class`` 必須與導出的主機 class 同一級**(P1-B)。

    (d) 是 P1-B 的處置。少了它,呼叫端可以在導出為 ``production`` / ``unknown`` 的主機上遞一份
    **合法簽章的 ``disposable_local`` intent**:adapter 於是走它的 disposable 分支(``apply_quiesce_fence``
    會真的對 system-level unit 發 ``stop``/``start``),卻回報 rehearsal 級的 local 證據 —— 一次真實的
    runtime effect 被記成演練。故生產進入點只收 ``production`` intent;``disposable_local`` intent 只能
    走 rehearsal lane(那條 lane 的 derived class 若是 production-grade 本來就恆拒)。

    ``non_target`` 一律拒(那台主機根本不是 S2 目標)。``disposable_candidate`` **也一律拒**(P1-A):
    它是 :data:`REHEARSAL_ONLY_TARGET_CLASSES`,不可由主機事實導出,故生產進入點見到它只可能是一份
    偽造 / 過期的視圖。四條件**任一**缺席即回非空 errors —— 特別是 ``--allow-production`` 單獨絕不足夠。
    """

    target_class = target_view.get("target_class")
    if target_class in REHEARSAL_ONLY_TARGET_CLASSES:
        return [
            f"target_class={target_class} is a rehearsal-only class that host facts can never "
            "derive; a production entry point never admits it (use the rehearsal lane instead)"
        ]
    if target_class == TARGET_CLASS_NON_TARGET:
        return [
            "S2 host runner refuses to construct a driver on a non-target host "
            f"({target_view.get('reason')})"
        ]
    if target_class not in PRODUCTION_GRADE_TARGET_CLASSES:
        return [f"S2 host runner cannot classify this host (target_class={target_class!r})"]
    errors: list[str] = []
    # intent/主機 class 綁定:訊息只複述**封閉枚舉**(兩個宣告值或 ``unrecognized``),絕不把呼叫端
    # 遞進來的原字串回寫進任何理由 —— 這些理由會落進 artifact 與 stdout summary。
    if intent_target_class != INTENT_TARGET_CLASS_PRODUCTION:
        # ``isinstance`` 先行:一份壞 intent 可能遞來 list/dict,而 ``x in frozenset`` 對不可雜湊值
        # 會拋 TypeError —— 一道准入謂詞絕不可以自己炸成未分類例外。
        declared = (
            intent_target_class
            if isinstance(intent_target_class, str) and intent_target_class in INTENT_TARGET_CLASSES
            else "unrecognized"
        )
        errors.append(
            f"target_class={target_class} only admits an intent whose own target_class is "
            f"{INTENT_TARGET_CLASS_PRODUCTION}; this intent declares {declared} (a "
            f"{INTENT_TARGET_CLASS_DISPOSABLE_LOCAL} intent would drive the adapter's rehearsal "
            "branch with real host capabilities and report a real effect as a drill)"
        )
    if not allow_production:
        errors.append(
            f"target_class={target_class} requires an explicit --allow-production; refusing "
            "(unknown is treated exactly like production)"
        )
    if not operator_authorization_verified:
        errors.append(
            f"target_class={target_class} requires a verified operator SSHSIG bound to the exact "
            "intent digest, source head and target host"
        )
    if not isinstance(intent_digest, str) or not intent_digest:
        errors.append("production admission requires the exact intent digest to confirm against")
    elif production_confirm != intent_digest:
        errors.append(
            "production admission requires --production-confirm to repeat the exact intent digest "
            "verbatim (paste/typo guard)"
        )
    return errors


def host_observation_admission_errors(
    target_view: dict[str, Any], *, allow_production: bool
) -> list[str]:
    """**唯讀觀測**面的 L1 准入謂詞(E2 P2 #7:observer 面原本完全不過 L1)。

    原本 ``probe --observe`` 直接對真主機發 ``systemctl show``,連一道 L1 都沒過。現在它也過 L1,
    但**刻意**比 :func:`host_target_admission_errors` 弱一級,而且理由必須寫清楚:

    * 觀測面的每一條 argv 都在**唯讀** session 的封閉 allowlist 內(``show -p <封閉屬性集>`` 與
      ``list-units``),結構上不可能變更主機狀態,故它不需要、也不該需要一份綁 intent digest 的
      operator SSHSIG —— 觀測正是「拿到 permit 之前」要做的事。
    * 但它仍然是**真的主機接觸**,所以在 ``production`` / ``unknown`` 上必須有一次顯式的
      ``--allow-production`` 承認;``unknown`` 一如既往與 ``production`` 同等對待。
    * ``non_target`` **放行**:那台主機上的觀測只會打到不存在的 ``systemctl``(typed 失敗),
      擋它沒有安全收益,反而會讓 Mac 上的結構測試失去唯一一條真子行程路徑。
    * ``disposable_candidate`` **拒**(P1-A):本謂詞的輸入恆為導出視圖,而導出面永不回 rehearsal-only
      class,故見到它只可能是一份偽造 / 過期的視圖 —— 落在「無法分類」那一支才是誠實的收場。
    """

    target_class = target_view.get("target_class")
    if target_class == TARGET_CLASS_NON_TARGET:
        return []
    if target_class not in PRODUCTION_GRADE_TARGET_CLASSES:
        return [
            f"S2 host observer cannot classify this host (target_class={target_class!r})"
        ]
    if not allow_production:
        return [
            f"a read-only observation on target_class={target_class} requires an explicit "
            "--allow-production acknowledgement (unknown is treated exactly like production)"
        ]
    return []


# rehearsal lane 的拒絕集合:``unknown`` 與 ``production`` **同等對待**(排練絕不在可能是生產的
# 主機上跑)。
REHEARSAL_REFUSED_TARGET_CLASSES = frozenset({TARGET_CLASS_PRODUCTION, TARGET_CLASS_UNKNOWN})


def rehearsal_target_refusals(
    derived_view: dict[str, Any], injected_view: dict[str, Any] | None = None
) -> list[str]:
    """rehearsal lane 的 target 拒絕謂詞:derived 與 injected **取更嚴**(嚴格性單調遞增)。

    production lane **不收**任何 caller view —— 那個洞正是 L1 的存在理由。rehearsal lane 需要能在
    非目標主機上證明「production 會被拒」,故允許注入一份 view,但注入**只能加嚴、不能放寬**:
    derived 或 injected 任一落在 :data:`REHEARSAL_REFUSED_TARGET_CLASSES` 即拒。因此一份偽造的
    ``disposable_candidate`` view 在真 production 主機上仍然拒絕,而測試注入的 ``production``
    view 在 Mac(derived=``non_target``)上也仍然拒絕。

    落盤 artifact 必須分別記錄 derived 與 injected(:func:`rehearsal_target_view_record`),
    ``target_class_view`` 永遠是**導出值**,絕不是注入值。
    """

    refusals: list[str] = []
    derived_class = (derived_view or {}).get("target_class")
    if derived_class in REHEARSAL_REFUSED_TARGET_CLASSES:
        refusals.append(
            f"the derived host target_class is {derived_class!r} (unknown is treated exactly like "
            "production); a rehearsal never runs here"
        )
    if injected_view is not None:
        injected_class = injected_view.get("target_class")
        if injected_class in REHEARSAL_REFUSED_TARGET_CLASSES:
            refusals.append(
                f"the injected rehearsal target_class is {injected_class!r}; an injected view may "
                "only make the refusal stricter, never weaker"
            )
    return refusals


def rehearsal_target_view_record(
    derived_view: dict[str, Any], injected_view: dict[str, Any] | None = None
) -> dict[str, Any]:
    """artifact 用的誠實投影:``target_class`` 恆為**導出值**,注入值只作旁註。"""

    return {
        "target_class": (derived_view or {}).get("target_class"),
        "derived": derived_view,
        "injected": injected_view,
        "injected_is_authoritative": False,
    }


# --------------------------------------------------------------------------- #
# (4) host wall clock
# --------------------------------------------------------------------------- #
def host_wall_clock_time() -> str:
    """本行程所在主機**牆鐘**的 UTC ISO8601 讀值。

    **誠實界線(名字即語義)**:這只是一次 ``datetime.now`` 的讀值,**不是** attestation,
    **不承載任何 trust 語義** —— 它沒有被任何金鑰簽章、沒有被任何獨立方背書、沒有防重放,
    任何人只要能改這台主機的時鐘就能改它。合法用途只有兩種,兩種都不需要 trust:
    (a)**敘述性**時戳欄位(``observed_at`` / postcheck 的 ``observed_at``——「這份 artifact
    何時被寫出」);(b)當作 caller 的 ``now`` 遞給既有的 permit 驗證器,而 caller 的 ``now``
    在該設計裡**只能收緊**(讓過期的 permit 被拒)、**永遠不能放寬**任何閘。它絕不可以被寫進
    任何簽章 payload,也絕不可以單獨解鎖任何狀態。

    與 adapter 面的 ``trusted_host_time`` **是兩件不同的事,故刻意不同名**:後者是
    ``AggregateInstallDriver`` 等 driver Protocol 的方法名、以及簽章 attestation payload
    (``s2_4_install_apply_attestation_v1`` / ``pg_observer_bootstrap_apply_attestation_v1``
    / ``s2_5_*_attestation_v1``)內的**已簽欄位名**;那個值才是 S2.0/S2.4/S2.5 解鎖
    ``APPLIED`` 的新鮮度錨(caller 的 now 永不參與)。本函式**絕不**被用來冒充那個值,
    兩者共用同一個識別碼只會讓讀者誤以為本函式也帶 trust。
    """

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------- #
# (5) capability partition — refuse a mutating surface before calling anything
# --------------------------------------------------------------------------- #
# observer / read-only probe 上**絕不**可以出現的寫能力方法名(鏡 FORBIDDEN_AGGREGATE_METHODS 的形制)。
FORBIDDEN_READ_ONLY_SURFACE = frozenset({
    "stop", "start", "restart", "enable", "disable", "enable_now", "reset_failed",
    "kill", "mask", "unmask", "daemon_reload",
    "apply", "rollback", "compensate", "commit", "write", "install", "prepare",
    "create_read_only_observer", "observer_bootstrap_apply", "signed_apply_attestation",
    "execute", "remove", "unlink", "rmtree", "drop", "grant", "revoke",
})


def assert_read_only_surface(obj: Any, forbidden: Iterable[str] = FORBIDDEN_READ_ONLY_SURFACE) -> list[str]:
    """物件上出現任一寫能力方法即 typed 拒(**絕不呼叫**);鏡 ``assert_no_aggregate_forbidden_surface``。

    這是 §B.2 的 L1 object-capability 檢查:observer 在結構上不持有任何寫能力,而且檢查發生在
    **呼叫任何方法之前**。
    """

    present = sorted(name for name in set(forbidden) if callable(getattr(obj, name, None)))
    if not present:
        return []
    return [
        f"the read-only S2 host surface exposes forbidden mutating operations {present}; an "
        "observer never stops, starts, applies, compensates or writes anything"
    ]


# --------------------------------------------------------------------------- #
# (2) the single exec point
# --------------------------------------------------------------------------- #
def _safe_environment() -> dict[str, str]:
    """Sanitized env allowlist,由 ``agent_governance_command_capture_v2`` 的既有集合**導出**。"""

    from agent_governance_command_capture_v2 import SAFE_INHERITED_ENVIRONMENT

    environment = {
        key: value for key, value in os.environ.items()
        if key in SAFE_INHERITED_ENVIRONMENT
    }
    # 決定性輸出:systemctl 的訊息語系必須固定,否則 parse 會隨 locale 漂移。
    environment.update({"LANG": "C", "LC_ALL": "C"})
    return environment


def _redact(data: bytes) -> str:
    """輸出去敏:重用 capture_v2 的既有 secret 正則(不另造第二套規則)。"""

    from agent_governance_command_capture_v2 import _redact_preview

    redacted, _changed = _redact_preview(data)
    return redacted.decode("utf-8", "replace")


# --------------------------------------------------------------------------- #
# (6) 出境秘密掃描 —— runner 家族任何 payload 進 sink 之前的共用守衛
# --------------------------------------------------------------------------- #
def _egress_bytes(payload: Any) -> bytes:
    """把任一 payload 折成掃描用 bytes;不可 canonical 序列化時退回 ``repr``(絕不因此放過)。"""

    try:
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            allow_nan=False, default=repr,
        ).encode("utf-8")
    except (TypeError, ValueError):
        return repr(payload).encode("utf-8", "replace")


def _carries_secret_shaped_value(payload: Any) -> bool:
    """判定一份 payload 是否帶 secret 形的值(判準 = capture_v2 的 ``SECRET_VALUE_PATTERNS``)。

    掃的是**canonical JSON bytes**而不是逐個葉節點:``{"password":"x"}`` 這種「鍵值相鄰」形只有在
    序列化後才看得見,逐葉掃描會漏掉它。
    """

    from agent_governance_command_capture_v2 import _redact_preview

    return _redact_preview(_egress_bytes(payload))[1]


def _secret_trails(node: Any, trail: str) -> list[str]:
    """定位命中點的 JSON trail;**只回鍵名路徑,絕不回內容**(理由字串本身不得成為第二條洩漏路徑)。"""

    if isinstance(node, dict):
        found: list[str] = []
        for key, value in node.items():
            here = f"{trail}{key}"
            if _carries_secret_shaped_value({key: value}):
                found.extend(_secret_trails(value, here + ".") or [here])
        return found
    if isinstance(node, (list, tuple)):
        found = []
        for index, item in enumerate(node):
            here = f"{trail}{index}"
            if _carries_secret_shaped_value(item):
                found.extend(_secret_trails(item, here + ".") or [here])
        return found
    return []


def scan_serializable_surface_for_secrets(payload: Any) -> list[str]:
    """對一份**即將出境**的 payload 做秘密掃描;命中回 typed 理由(絕不逸出例外、絕不回內容)。

    形制鏡 ``agent_governance_s2_4_install_driver`` 的 ``scan_serializable_surface(verdict)`` 用法:
    命中即整包丟棄、只回理由,而不是把「疑似含秘密」的內容照樣送出去再標一個旗標。

    **判準來源(不自造)**:``agent_governance_command_capture_v2.SECRET_VALUE_PATTERNS`` ——
    也就是每一份 governed capture 的 preview 去敏、以及本 kernel :func:`_redact` 對主機 stdout/stderr
    去敏所用的**同一套**正則(``*TOKEN/SECRET/PASSWORD/PASSWD/API_KEY/ACCESS_KEY/PRIVATE_KEY/
    CREDENTIAL* = <值>``、``Authorization: Bearer <值>``、``scheme://user:pass@host``)。

    **誠實界線(必讀)**

    * 這是**形狀**掃描,不是「不含秘密」的證明:它擋得住密碼賦值 / bearer token / URL 內嵌密碼這
      三類已知形,擋不住一段沒有任何鍵名線索的高熵字串。它的價值在於「本來零機械保證」→「已知形
      一律 fail-closed」,不在於完備。
    * **已知殘餘缺口(不在本波收口)**:``SECRET_VALUE_PATTERNS`` 的 URL 形只涵蓋 ``http(s)``
      scheme,故 ``<db-scheme>``-URI 形(授權段內嵌密碼)今日**擋不住**。repo 內確實另有一支涵蓋
      該形的中央規則 —— ``public_repo_security_gate.EMBEDDED_CREDENTIAL_DSN`` —— 但那個模組
      ``import subprocess``,把它拉進 runner 家族等於重新開一條完整 exec 路徑(正是 E2 RES-5 對
      ``agent_governance_command_capture_v2`` 收掉的那條縫),故本波**不**匯入它。正確修法是把該形
      併進中央的 ``SECRET_VALUE_PATTERNS``(全 repo 的 governed capture preview 一起受惠),而不是
      在 runner 家族自造第二套判準。S2.4 實際使用的封閉 DSN 是 libpq 鍵值形(密碼以 ``pass``+
      ``word=`` 鍵出現),那一形**有**被擋;此缺口以結構測試釘住,中央一旦加寬即被看見。
    * **為何不用** ``agent_governance_s2_4_credential.scan_serializable_surface``:那一支是
      **哨兵**掃描——它比對的是本行程內活著的 :class:`SealedSecretHandle` 明文,沒有 handle 時
      恆回 ``[]``。observer child 從不鑄造 handle,故那支在此路徑上結構性地是 no-op(等於沒有
      守衛);且 ``s2_4_*`` 是 applier 側模組,匯入它會同時破壞「observer 的 import closure ∩
      applier == ∅」與 runner 家族的正面 import 白名單。兩支掃描器是互補的兩層,不是替代品。
    """

    if not _carries_secret_shaped_value(payload):
        return []
    trails = sorted(set(_secret_trails(payload, ""))) or ["<root>"]
    return [
        f"a secret-shaped value reached a serializable surface at {trails}; the whole payload is "
        "dropped rather than emitted (the reason carries key trails only, never the value)"
    ]


class HostExecutionKernel:
    """The one and only place the S2 host runner family calls ``subprocess``.

    ``session`` 必填且必須是宣告過的 session;變更型 session 另需 ``allow_mutation=True``。
    每次 :meth:`run` 都會:①先執法 ``PR_SET_DUMPABLE=0``;②以 :func:`assert_session_argv` 對封閉
    allowlist 做**字面**比對;③``shell=False`` + argv[0] 絕對路徑 + sanitized env + 固定 timeout;
    ④非零退出 / timeout 一律 typed raise(絕不把失敗吞成空字串)。
    """

    def __init__(self, *, session: str, allow_mutation: bool = False) -> None:
        allowlist = session_argv_allowlist(session)
        mutating = session in MUTATING_SESSIONS
        if mutating and not allow_mutation:
            raise S2HostSessionError(
                f"session {session!r} mutates host state and requires an explicit allow_mutation=True"
            )
        if allow_mutation and not mutating:
            raise S2HostSessionError(
                f"session {session!r} is read-only; allow_mutation=True is refused"
            )
        self.session = session
        self.allow_mutation = bool(allow_mutation)
        self._allowlist = allowlist
        self._timeout_seconds = SESSION_TIMEOUT_SECONDS[session]
        self.calls: list[tuple[str, ...]] = []

    # -- introspection ------------------------------------------------------ #
    @property
    def allowlist(self) -> frozenset[tuple[str, ...]]:
        return self._allowlist

    @property
    def timeout_seconds(self) -> int:
        return self._timeout_seconds

    # -- the exec point ----------------------------------------------------- #
    def run_observer_child(self, request: dict[str, Any]) -> str:
        """Spawn the read-only observer in an isolated ``python3 -E`` child and return its stdout.

        §B.2 L2 的進程分離:子行程以 sanitized allowlist env 啟動、不繼承任何治理閘 env、不持有
        本行程的任何 driver 或連線物件,產出只經 stdout 的 canonical JSON 回來。argv 由
        :func:`observer_child_argv` 於 kernel 內部構造,caller 只遞一份 dict request。
        """

        if self.session != SESSION_S2_HOST_OBSERVER_CHILD:
            raise S2HostSessionError(
                f"session {self.session!r} may not spawn the read-only observer child"
            )
        payload = json.dumps(
            request, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
        argv = observer_child_argv(base64.b64encode(payload).decode("ascii"))
        enforce_process_hardening(force=True)
        self.calls.append(tuple(argv))
        return _redact(self._execute(argv).stdout or b"")

    def run(self, argv: Iterable[str]) -> str:
        """Execute exactly one allowlisted argv and return its redacted stdout."""

        candidate = assert_session_argv(self.session, argv)
        if candidate == RECOVERY_HOST_CAPTURE_ATTESTOR_ARGV:
            raise S2HostSessionError(
                "the recovery attestor requires the zero-input dedicated method"
            )
        enforce_process_hardening(force=True)
        self.calls.append(candidate)
        return _redact(self._execute(list(candidate)).stdout or b"")

    def capture_recovery_host(self) -> bytes:
        """Invoke the fixed attestor with no caller payload and return bounded JSON bytes."""

        if self.session != SESSION_S2_5_RECOVERY_HOST_CAPTURE:
            raise S2HostSessionError(
                f"session {self.session!r} may not invoke the recovery attestor"
            )
        candidate = assert_session_argv(
            self.session, RECOVERY_HOST_CAPTURE_ATTESTOR_ARGV
        )
        enforce_process_hardening(force=True)
        self.calls.append(candidate)
        completed = self._execute(list(candidate))
        if completed.stderr or not (
            1 <= len(completed.stdout) <= MAX_RECOVERY_HOST_CAPTURE_ARTIFACT_BYTES
        ):
            raise S2HostCommandFailed(
                "fixed recovery host-capture attestor response is invalid"
            )
        return bytes(completed.stdout)

    def _execute(
        self,
        candidate: list[str],
        *,
        stdin_bytes: bytes = b"",
    ) -> Any:
        try:
            completed = subprocess.run(  # noqa: S603 - fixed absolute argv, shell=False, no caller string
                list(candidate),
                shell=False,
                input=stdin_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_safe_environment(),
                timeout=self._timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise S2HostCommandFailed(
                f"S2 host command timed out after {self._timeout_seconds}s in session {self.session}"
            ) from error
        except OSError as error:
            raise S2HostCommandFailed(
                f"S2 host command could not be executed in session {self.session}: {error}"
            ) from error
        if completed.returncode != 0:
            raise S2HostCommandFailed(
                f"S2 host command exited {completed.returncode} in session {self.session}: "
                + _redact(completed.stderr or b"")[:400]
            )
        return completed


def kernel_abi_projection() -> dict[str, Any]:
    """Code-owned projection of the kernel's closed surface (tests/registry reconciliation)."""

    return {
        "sessions": sorted(SESSION_ARGV_ALLOWLISTS),
        "mutating_sessions": sorted(MUTATING_SESSIONS),
        "argv_allowlists": {
            session: sorted(list(argv) for argv in allowlist)
            for session, allowlist in SESSION_ARGV_ALLOWLISTS.items()
        },
        "timeout_seconds": dict(SESSION_TIMEOUT_SECONDS),
        "target_classes": sorted({
            TARGET_CLASS_NON_TARGET, TARGET_CLASS_DISPOSABLE_CANDIDATE,
            TARGET_CLASS_PRODUCTION, TARGET_CLASS_UNKNOWN,
        }),
        "production_grade_target_classes": sorted(PRODUCTION_GRADE_TARGET_CLASSES),
        # P1-A / P1-B 的兩條硬邊界在 artifact 上的可稽核投影。
        "derivable_target_classes": sorted(DERIVABLE_TARGET_CLASSES),
        "rehearsal_only_target_classes": sorted(REHEARSAL_ONLY_TARGET_CLASSES),
        "production_entry_intent_target_class": INTENT_TARGET_CLASS_PRODUCTION,
        "forbidden_read_only_surface": sorted(FORBIDDEN_READ_ONLY_SURFACE),
        "forbidden_argv_tokens": sorted(FORBIDDEN_ARGV_TOKENS),
        # 出境秘密掃描在 artifact 上的活再導出面(鏡 s2_4 credential ABI 的同名欄位形制)。
        "egress_secret_scanner": (
            "agent_governance_s2_host_kernel.scan_serializable_surface_for_secrets"
        ),
        "egress_secret_scanner_rules": (
            "agent_governance_command_capture_v2.SECRET_VALUE_PATTERNS"
        ),
    }

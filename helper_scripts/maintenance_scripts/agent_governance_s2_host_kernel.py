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
   ``unknown`` 與 ``production`` 同等對待。搭配 :func:`host_target_admission_errors`(對同一份
   導出視圖的薄准入謂詞),讓 runner 在**構造任何 driver 之前**就能 typed 拒絕。
4. :func:`trusted_host_time` —— 施作端主機時鐘的 UTC 投影。
5. :func:`assert_read_only_surface` —— 鏡 ``agent_governance_s2_4_install_driver
   .assert_no_aggregate_forbidden_surface``:物件上出現任一寫能力方法即 typed 拒,且**絕不呼叫**。

外加一件與 exec 不可分割的執法::func:`enforce_process_hardening` 在**任何**主機指令執行之前真的
跑 ``prctl(PR_SET_DUMPABLE, 0)`` 並回讀 ``PR_GET_DUMPABLE`` 確認為 0,不為 0 即拒絕執行(W5
obligation ``PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED`` 指出該常量今日只出現在兩個投影 dict、
無任何 driver 觀測它;本 kernel 是第一處真的觀測並執法它的地方)。

**誠實界線(必讀)。**

* 本模組是 **L1 主機安全層**,不是證據完整性層。它只決定「今天要不要碰這台主機」;
  「即使 driver 在手也不可能 emit APPLIED」是 adapter 的 L2 閘(permit 驗簽 / trusted-host
  attestation),「封包不可 PASS」是 closure 的 L3 閘。本波對 L2/L3 **一行不動**。
* :func:`trusted_host_time` 回的是**施作端自己的**牆鐘,**不是** attestation。真正解鎖 APPLIED 的
  signed ``trusted_host_time`` 仍只能來自 driver 的簽章 attestation(S2.0 §9b/§9c)。
* 本模組對四個 S2 adapter 模組**零行修改**:刪掉整個 runner 家族,四個 adapter 的行為與今日
  逐位元組相同(全部 ``EXTERNAL_VERIFICATION_PENDING``)。
"""

from __future__ import annotations

import ctypes
import os
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
}

# per-session 固定 timeout(code-owned,caller 不可放大)。fence 需容納 unit 的 TimeoutStopUSec。
SESSION_TIMEOUT_SECONDS: dict[str, int] = {
    SESSION_S2_0_OBSERVER_BOOTSTRAP: 30,
    SESSION_S2_1_QUIESCE_READ: 30,
    SESSION_S2_1_QUIESCE_FENCE: 120,
}


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


# --------------------------------------------------------------------------- #
# process hardening (W5 #21: PR_SET_DUMPABLE must be LOAD-BEARING, not declared)
# --------------------------------------------------------------------------- #
_PR_GET_DUMPABLE = 3
_PR_SET_DUMPABLE = 4
_HARDENING_CACHE: dict[str, Any] | None = None


def enforce_process_hardening(*, force: bool = False) -> dict[str, Any]:
    """真的執法 ``PR_SET_DUMPABLE=0``:設定 → 回讀 → 不為 0 即拒絕跑任何主機指令。

    W5 obligation ``PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED`` 的原文要求是「observing
    prctl(PR_GET_DUMPABLE) on the applier and refusing when it is not 0」。本函式即是那個觀測 +
    拒絕,且被 :meth:`HostExecutionKernel.run` 在**第一次** exec 之前無條件呼叫。

    誠實界線:非 Linux 主機沒有 prctl,回 ``enforced=False`` 並註明理由;但非 Linux 主機的
    ``derive_host_target_class`` 恆為 ``non_target``,runner 在那裡就已經拒絕跑真主機指令,
    故此處不構成一個「在 Mac 上被靜默略過的閘」。
    """

    global _HARDENING_CACHE
    if _HARDENING_CACHE is not None and not force:
        return dict(_HARDENING_CACHE)
    if sys.platform != "linux":
        observation = {
            "enforced": False,
            "observed_dumpable": None,
            "reason": (
                "prctl(PR_SET_DUMPABLE) is a Linux facility; this host is not a target host and "
                "the kernel executes no host command here"
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
# ``unknown`` 與 ``production`` **同等對待**:兩者都必須滿足三條件才可執行。
PRODUCTION_GRADE_TARGET_CLASSES = frozenset({TARGET_CLASS_PRODUCTION, TARGET_CLASS_UNKNOWN})


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


def derive_host_target_class() -> dict[str, Any]:
    """由**主機事實**導出 target class;**絕不**接受 caller 傳入的 target_class 字串。

    這是 L1 不可被 L2 取代的原因:``target_class`` 今日在 S2.5 是 caller 參數
    (``apply_s2_5_start(target_class=...)``)、在 S2.4 的 plan/probe schema 根本不存在——
    「我在拋棄式主機上」目前完全是呼叫端自我宣告。runner 是唯一能把它變成主機導出事實的地方。

    判定(§E.2):

    * ``platform != linux`` → ``non_target``
    * hostname 不在 :data:`TARGET_HOSTNAMES` → ``non_target``
    * ``/etc/systemd/system`` 不可寫 **且** canonical roots 皆不存在 → ``disposable_candidate``
    * 三項全命中(linux + target hostname + 可寫 unit dir + canonical roots 齊備)→ ``production``
    * 任何一項不可判定 → ``unknown``(與 ``production`` 同等對待)
    """

    facts: dict[str, Any] = {
        "platform": sys.platform,
        "hostname": socket.gethostname(),
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
    if facts["hostname"] not in TARGET_HOSTNAMES:
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
        return {
            "target_class": TARGET_CLASS_DISPOSABLE_CANDIDATE,
            "reason": (
                "linux target hostname without a writable system unit directory and without any "
                "canonical install root; only a disposable rehearsal may run here"
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
) -> list[str]:
    """L1 准入謂詞:``production`` / ``unknown`` 必須三條件並存,否則 typed 拒(driver 永不構造)。

    (a) CLI 顯式 ``--allow-production``;
    (b) 已驗證的 operator SSHSIG(綁 exact intent digest + source_head + target_host——驗簽本身屬
        adapter 的 L2 閘,呼叫端把「已驗證」這個布林事實遞進來);
    (c) ``--production-confirm <intent_digest>`` 逐字回填(防手滑 / 防貼上)。

    ``non_target`` 一律拒(那台主機根本不是 S2 目標);``disposable_candidate`` 放行 rehearsal。
    三條件**任一**缺席即回非空 errors —— 特別是 ``--allow-production`` 單獨絕不足夠。
    """

    target_class = target_view.get("target_class")
    if target_class == TARGET_CLASS_DISPOSABLE_CANDIDATE:
        return []
    if target_class == TARGET_CLASS_NON_TARGET:
        return [
            "S2 host runner refuses to construct a driver on a non-target host "
            f"({target_view.get('reason')})"
        ]
    if target_class not in PRODUCTION_GRADE_TARGET_CLASSES:
        return [f"S2 host runner cannot classify this host (target_class={target_class!r})"]
    errors: list[str] = []
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


# --------------------------------------------------------------------------- #
# (4) trusted host time
# --------------------------------------------------------------------------- #
def trusted_host_time() -> str:
    """施作端主機時鐘的 UTC ISO8601 投影。

    **誠實界線**:這是**這台主機自己的**牆鐘,不是 attestation。S2.0 的 ``APPLIED`` 仍然只由
    driver 簽章 attestation 內的 ``trusted_host_time`` 錨定新鮮度(caller 的 now 永不參與),
    本函式**絕不**被用來冒充那個值。
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
    def run(self, argv: Iterable[str]) -> str:
        """Execute exactly one allowlisted argv and return its redacted stdout."""

        candidate = assert_session_argv(self.session, argv)
        enforce_process_hardening()
        self.calls.append(candidate)
        try:
            completed = subprocess.run(  # noqa: S603 - fixed absolute argv, shell=False, no caller string
                list(candidate),
                shell=False,
                stdin=subprocess.DEVNULL,
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
        return _redact(completed.stdout or b"")


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
        "forbidden_read_only_surface": sorted(FORBIDDEN_READ_ONLY_SURFACE),
        "forbidden_argv_tokens": sorted(FORBIDDEN_ARGV_TOKENS),
    }

"""S2E.2a:S2.1(ALR quiesce fence)的**受信主機 runner**。

S2.1 的注入面沒有 Protocol class(``host_probe`` / ``fence_ops`` / ``db_observer`` 全是 ``Any``),
契約由 consumer 反推。本模組把那三個面實作成三個**能力分割**的類別:

* :class:`QuiesceHostProbe` —— 唯讀面(``run(argv)`` / ``proc_root`` / ``dsn_stat()`` /
  ``flock_held()``)。**沒有** ``stop`` / ``start``,故 ``assert_read_only_surface`` 對它恆乾淨。
* :class:`QuiesceFenceOps` —— 可逆生命週期面(``stop()`` / ``start()``),argv 由 code 構造成
  **該 unit 自身**的 system-level stop/start;沒有任何 caller unit-name/pattern/pid 參數面。
* :class:`QuiesceDbObserver` —— DB 唯讀面,只暴露 ``cursor()``。裸 psycopg2 連線帶 ``commit`` /
  ``rollback`` 這類寫能力方法,直接交給 adapter 會讓能力分割硬檢失效;本包裝把它收窄成一個
  結構上只能讀的物件。

**§E.3 #2(kernel 側獨立 re-assert)的落點在這裡。** 今日 S2.1 的 allowlist 只在 caller 側
(``agent_governance_alr_quiesce_inventory._assert_allowlisted_systemctl`` 於 ``_run_show`` /
``_scope_conflict`` 內呼叫),``host_probe.run(argv)`` 本身收**任意** argv —— 任何繞過 owner 模組
直呼 probe 的路徑今天都是開的。:meth:`QuiesceHostProbe.run` 因此**自己再 assert 一次**(owner 側 +
kernel 側兩道),照抄 S2.5 ``allowlisted_systemctl_argv`` 「唯一 argv 構造點」的形制。

**誠實界線。**

1. 本模組對 ``agent_governance_alr_quiesce_fence`` / ``..._inventory`` **零行修改**。
2. rehearsal 的 host 面是「模擬 ``/proc`` + 注入的 systemctl executor + 注入的 fence executor」,
   DB 面是**真** PG advisory lock;這正是 S2.1 既有 disposable 證明的形制,誠實標示為 T1,
   **不證明**任何真 systemd 事實。
3. ``QUIESCED_STATIC_GUARDS_HELD`` 被 S2.1 的 result schema 釘成 ``disposable_local`` +
   ``LOCAL_REPRODUCIBLE`` + ``production_fence_performed=false``,且 S2E.1 已把 S2.1 標成
   closure-PASS-blocked ⇒ **rehearsal 綠絕不是 closure PASS,也絕不是 EFFECT 進展。**
4. 獨立 ops_postcheck 一律走 S2E.1 既有的 ``build_s2_effect_ops_postcheck_evidence``;它對 S2.1
   typed 拒絕,本 runner 忠實記錄該理由,絕不另造第二種 receipt schema(§H R4)。
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any, Callable

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
for _candidate in (_HERE, _REPO_ROOT / "program_code" / "ml_training"):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_alr_quiesce_fence as quiesce_fence  # noqa: E402
import agent_governance_alr_quiesce_inventory as quiesce_inventory  # noqa: E402
import agent_governance_s2_effect_binding as s2_effect_binding  # noqa: E402
import agent_governance_s2_host_kernel as host_kernel  # noqa: E402


S2_1_STEP = "S2_1_DRILL"
# S2.4 §8 的固定憑證面:DSN 落在 systemd 的 credential 目錄(code-owned,caller 永不遞路徑)。
DSN_CREDENTIAL_PATH = f"/run/credentials/{quiesce_inventory.UNIT_NAME}/pg-dsn"
PROC_LOCKS_PATH = "/proc/locks"


class S2_1HostRunnerError(RuntimeError):
    """Raised when the S2.1 host runner refuses to act (fail-closed; nothing is fenced)."""


# --------------------------------------------------------------------------- #
# read-only host probe (independent re-assert; NO stop/start on this surface)
# --------------------------------------------------------------------------- #
class QuiesceHostProbe:
    """The read-only ``host_probe`` face consumed by ``build_owner_inventory`` / the sampler."""

    def __init__(
        self,
        *,
        executor: Any,
        proc_root: str = "/proc",
        dsn_path: str = DSN_CREDENTIAL_PATH,
        flock_path: str | None = None,
        locks_path: str = PROC_LOCKS_PATH,
    ) -> None:
        self._executor = executor
        self.proc_root = str(proc_root)
        self._dsn_path = str(dsn_path)
        self._flock_path = flock_path
        self._locks_path = str(locks_path)
        self.argv: list[tuple[str, ...]] = []

    # -- the independently re-asserted read command ------------------------- #
    def run(self, argv) -> str:
        """Execute one read-only systemctl command after **two independent** allowlist asserts.

        ①owner 側 ``_assert_allowlisted_systemctl``(S2.1 今日唯一的一道,且只在 caller 側);
        ②kernel 側 :func:`agent_governance_s2_host_kernel.assert_session_argv` 的封閉字面比對。
        兩道都過才會遞給 executor —— 於是「繞過 owner 模組直呼 probe」也擋得住。
        """

        candidate = list(argv)
        quiesce_inventory._assert_allowlisted_systemctl(candidate)
        host_kernel.assert_session_argv(host_kernel.SESSION_S2_1_QUIESCE_READ, candidate)
        self.argv.append(tuple(candidate))
        return self._executor.run(candidate)

    # -- read-only credential-file identity (never reads the DSN content) --- #
    def dsn_stat(self) -> dict[str, Any]:
        """``fstatat`` 出憑證檔的模式/擁有者;**絕不**開啟或讀取其內容。"""

        parent = os.path.dirname(self._dsn_path) or "/"
        leaf = os.path.basename(self._dsn_path)
        try:
            parent_fd = os.open(
                parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
            )
        except OSError as error:
            raise S2_1HostRunnerError(
                f"the ALR credential directory is not observable ({error.strerror}); refusing to "
                "guess the credential exposure"
            ) from error
        try:
            info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        except OSError as error:
            raise S2_1HostRunnerError(
                f"the ALR credential file is not observable ({error.strerror}); refusing to guess"
            ) from error
        finally:
            os.close(parent_fd)
        mode = stat.S_IMODE(info.st_mode)
        return {
            "dsn_file_path": self._dsn_path,
            "dsn_mode": format(mode, "04o"),
            "dsn_owner_uid": int(info.st_uid),
            "world_readable": bool(mode & stat.S_IROTH),
        }

    # -- read-only flock corroboration via /proc/locks ---------------------- #
    @staticmethod
    def _locks_row(line: str) -> list[str] | None:
        """把一行 ``/proc/locks`` 正規化成 ``[type, kind, mode, pid, locus, start, end]``。

        E2 P2 #11 的第二半:等待者(waiter)行的形是 ``N: -> FLOCK ...``,那個 ``->`` 前綴會把
        所有欄位往後推一格,使「固定看 ``fields[5]``」讀到錯的東西。此處先剝掉序號欄,再剝掉可選
        的 ``->``,欄位位置才是穩定的。
        """

        fields = line.split()
        if not fields or not fields[0].endswith(":"):
            return None
        rest = fields[1:]
        if rest and rest[0] == "->":
            rest = rest[1:]
        return rest if len(rest) >= 5 else None

    def flock_held(self) -> bool | None:
        """由 ``/proc/locks`` 的 FLOCK 條目比對 lock 檔 **device + inode** 判定;**絕不**自己去取鎖。

        取鎖(即使 ``LOCK_NB`` 後立刻釋放)會擾動真 owner 的重取,故此面只用純唯讀來源。
        無法判定時回 ``None``(``build_owner_inventory`` 把 flock 當佐證訊號,權威證據是 PG
        advisory lock)。

        E2 P2 #11:第 6 欄是 ``<major>:<minor>:<inode>``(major/minor 為 **16 進位**),原本只比
        inode ⇒ 跨檔案系統的 inode 碰撞會誤判成 ``True``。現在 device 與 inode 必須同時相符。
        """

        if not self._flock_path:
            return None
        try:
            info = os.stat(self._flock_path, follow_symlinks=False)
        except OSError:
            return False
        try:
            raw = Path(self._locks_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        expected = (os.major(info.st_dev), os.minor(info.st_dev), int(info.st_ino))
        for line in raw.splitlines():
            row = self._locks_row(line)
            if row is None or row[0] != "FLOCK":
                continue
            locus = row[4].split(":")
            if len(locus) != 3:
                continue
            try:
                observed = (int(locus[0], 16), int(locus[1], 16), int(locus[2]))
            except ValueError:
                continue
            if observed == expected:
                return True
        return False


# --------------------------------------------------------------------------- #
# reversible owner-scoped fence ops (the ONLY mutating surface in this module)
# --------------------------------------------------------------------------- #
class QuiesceFenceOps:
    """``fence_ops`` 面:該 unit **自身**的 system-level ``systemctl stop`` / ``start``。

    argv 由 code 構造(``[SYSTEMD, verb, UNIT_NAME]``),沒有任何 caller unit-name / pattern /
    pid 參數面 —— 這正是 registry invariant「owner-scoped stop only ... NEVER pkill /
    kill-by-name / kill-by-pattern / kill-by-pid」在 runner 面的實作。
    """

    def __init__(self, *, executor: Any) -> None:
        self._executor = executor
        self.stop_calls = 0
        self.start_calls = 0
        self.argv: list[tuple[str, ...]] = []

    def _run(self, verb: str) -> str:
        argv = [quiesce_inventory.SYSTEMD, verb, quiesce_inventory.UNIT_NAME]
        host_kernel.assert_session_argv(host_kernel.SESSION_S2_1_QUIESCE_FENCE, argv)
        self.argv.append(tuple(argv))
        return self._executor.run(argv)

    def stop(self) -> None:
        self.stop_calls += 1
        self._run("stop")

    def start(self) -> None:
        self.start_calls += 1
        self._run("start")


# --------------------------------------------------------------------------- #
# DB read-only observer capability (a bare connection carries commit/rollback)
# --------------------------------------------------------------------------- #
class QuiesceDbObserver:
    """Expose exactly ``cursor()`` over the reused S2.0 read-only observer connection."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def cursor(self) -> Any:
        return self._connection.cursor()


# --------------------------------------------------------------------------- #
# host admission (L1) — refuse BEFORE constructing any fence capability
# --------------------------------------------------------------------------- #
def _require_host_admission(
    target_view: dict[str, Any],
    *,
    allow_production: bool,
    production_confirm: Any,
    intent_digest: Any,
    operator_authorization_verified: bool,
) -> None:
    errors = host_kernel.host_target_admission_errors(
        target_view,
        allow_production=allow_production,
        production_confirm=production_confirm,
        intent_digest=intent_digest,
        operator_authorization_verified=operator_authorization_verified,
    )
    if errors:
        raise S2_1HostRunnerError(
            "S2.1 host runner refuses to build a fence capability: " + "; ".join(errors)
        )


def _ops_postcheck_projection(
    receipt: dict[str, Any], *, verifier_node: str, observed_at: str
) -> dict[str, Any]:
    try:
        evidence = s2_effect_binding.build_s2_effect_ops_postcheck_evidence(
            receipt, verifier_node=verifier_node, observed_at=observed_at
        )
    except ValueError as error:
        return {"evidence": None, "refusal": str(error)}
    return {"evidence": evidence, "refusal": None}


def _require_runner_capabilities(probe: Any, fence_ops: Any, db_observer: Any) -> None:
    """能力物件必須是 runner 自有類別,否則 typed 拒(E2 RUN-3)。

    收下任意物件會讓 ``stop_calls`` / ``fence_argv`` 這些欄位在物件**確實**動過主機時仍被寫成
    ``0`` / ``[]`` —— 零值被當成事實發出。runner 存在的理由正是提供可觀測的主機面,故非自有類別
    一律拒絕,而不是靜默降級成不可觀測。

    E2 RES-4:比對用 ``type(x) is klass`` 而**不是** ``isinstance``。一個覆寫 ``stop()`` 但不加
    計數器的子類別能通過 ``isinstance``,於是 ``stop_calls`` 又回到「零值被當成事實」——那正是
    RUN-3 要收的洞,不能從子類別這條路重新打開。
    """

    expected = (
        ("host_probe", probe, QuiesceHostProbe),
        ("fence_ops", fence_ops, QuiesceFenceOps),
        ("db_observer", db_observer, QuiesceDbObserver),
    )
    wrong = [
        f"{name}={type(value).__name__!r} (expected exactly {klass.__name__})"
        for name, value, klass in expected
        if type(value) is not klass
    ]
    if wrong:
        raise S2_1HostRunnerError(
            "the S2.1 host runner only drives its own capability classes; refusing unobservable "
            "capabilities " + "; ".join(wrong)
        )


def _require_kernel_executors(probe: QuiesceHostProbe, fence_ops: QuiesceFenceOps) -> None:
    """**生產 lane 專用**:兩個 exec 面背後必須是真的 :class:`HostExecutionKernel`(E2 RES-4)。

    ``QuiesceFenceOps._run`` 自己只做 ``assert_session_argv``(argv 是不是那條),真正的 exec 交給
    注入的 ``executor``。於是 ``shell=False`` / sanitized env / 固定 timeout / 每次 exec 前的
    ``prctl(PR_SET_DUMPABLE)`` 執法**全部**是 kernel 的性質,而不是 runner 的性質 —— 注入一個裸
    的執行器包裝就把那四項一起丟了,而 argv 斷言照樣綠。生產 lane 因此把 executor 釘死成 kernel
    本尊(``type(x) is``,子類別可覆寫 ``_execute``,同樣不收)。

    rehearsal lane **刻意不套這道**:那條 lane 的 host 面本來就是注入的模擬器,誠實界線已寫明
    「不證明任何真 systemd 事實」。把模擬器擋掉不會增加安全,只會讓非 Linux 主機上再也證不出
    拒絕矩陣。
    """

    wrong = [
        f"{name} executor={type(executor).__name__!r}"
        for name, executor in (
            ("host_probe", probe._executor), ("fence_ops", fence_ops._executor),
        )
        if type(executor) is not host_kernel.HostExecutionKernel
    ]
    if wrong:
        raise S2_1HostRunnerError(
            "the S2.1 production lane only executes through the HostExecutionKernel (shell=False, "
            "sanitized env, fixed timeout, per-exec prctl enforcement); refusing " + "; ".join(wrong)
        )


def _run_result(
    *,
    lane: str,
    target_view: dict[str, Any],
    receipt: dict[str, Any],
    probe: QuiesceHostProbe | None,
    fence_ops: QuiesceFenceOps | None,
    verifier_node: str,
) -> dict[str, Any]:
    postcheck = _ops_postcheck_projection(
        receipt, verifier_node=verifier_node, observed_at=host_kernel.host_wall_clock_time()
    )
    rollback = receipt.get("rollback_record") or {}
    return {
        "lane": lane,
        "step": S2_1_STEP,
        "target_class_view": target_view,
        "status": receipt.get("status"),
        "receipt": receipt,
        # 無法觀測時發 ``null``,**絕不**發 ``0`` / ``[]``(那是把零值當成事實)。
        "read_argv": None if probe is None else [list(item) for item in probe.argv],
        "fence_argv": None if fence_ops is None else [list(item) for item in fence_ops.argv],
        "fence_observable": fence_ops is not None,
        "stop_calls": fence_ops.stop_calls if fence_ops is not None else None,
        "start_calls": fence_ops.start_calls if fence_ops is not None else None,
        "rollback_status": rollback.get("status"),
        "ops_postcheck_evidence": postcheck["evidence"],
        "ops_postcheck_refusal": postcheck["refusal"],
        "closure_pass_blocked": True,
        "closure_pass_blocked_reason": s2_effect_binding.S2_STEP_RECEIPT_CONTRACTS[S2_1_STEP][
            "closure_pass_blocked_reason"
        ],
        "production_fence_performed": bool(
            (receipt.get("boundary") or {}).get("production_fence_performed")
        ),
        "live_alr_owner_fenced": bool(
            (receipt.get("boundary") or {}).get("live_alr_owner_fenced")
        ),
    }


# --------------------------------------------------------------------------- #
# lane 1 — production quiesce fence on a real trusted host
# --------------------------------------------------------------------------- #
def run_quiesce_fence_on_host(
    intent: dict[str, Any],
    operator_authorization: Any,
    signature: Any,
    *,
    now: str,
    source_head: str,
    capability_factory: Callable[[], dict[str, Any]],
    verifier_capture_digest: str | None = None,
    clock: Callable[[], float] | None = None,
    sleep: Callable[[float], None] | None = None,
    allow_production: bool = False,
    production_confirm: Any = None,
    operator_authorization_verified: bool = False,
) -> dict[str, Any]:
    """Drive one S2.1 production quiesce fence (L1 admission strictly first).

    **production lane 不收任何 caller target view**(E2 RUN-1):target class 一律當場由
    ``derive_host_target_class()`` 從主機事實導出,落盤 artifact 記的也是導出值。

    ``capability_factory`` 回一個 ``{"host_probe", "fence_ops", "db_observer"}`` 字典,且**只有在
    host admission 通過之後**才被呼叫 —— 被拒時 fence 能力根本不存在,主機零接觸;三個能力都必須
    是 runner 自有類別(RUN-3,且比對 exact type),兩個 exec 面背後的 ``executor`` 還必須是真的
    :class:`agent_governance_s2_host_kernel.HostExecutionKernel`(RES-4:否則 ``shell=False`` /
    sanitized env / timeout / prctl 執法在真 fence 路徑上一項都不成立)。
    """

    view = host_kernel.derive_host_target_class()
    _require_host_admission(
        view,
        allow_production=allow_production,
        production_confirm=production_confirm,
        intent_digest=intent.get("self_digest"),
        operator_authorization_verified=operator_authorization_verified,
    )
    capabilities = capability_factory()
    probe = capabilities["host_probe"]
    fence_ops = capabilities["fence_ops"]
    db_observer = capabilities["db_observer"]
    _require_runner_capabilities(probe, fence_ops, db_observer)
    _require_kernel_executors(probe, fence_ops)
    surface_errors = host_kernel.assert_read_only_surface(probe)
    surface_errors.extend(host_kernel.assert_read_only_surface(db_observer))
    if surface_errors:
        raise S2_1HostRunnerError("; ".join(surface_errors))
    receipt = quiesce_fence.apply_quiesce_fence(
        intent, operator_authorization, signature,
        now=now, source_head=source_head, host_probe=probe, fence_ops=fence_ops,
        db_observer=db_observer, clock=clock, sleep=sleep,
        verifier_capture_digest=verifier_capture_digest,
    )
    return _run_result(
        lane="production", target_view=view, receipt=receipt,
        probe=probe, fence_ops=fence_ops,
        verifier_node=str(intent.get("postcheck_node_id")),
    )


# --------------------------------------------------------------------------- #
# lane 2 — disposable rehearsal (simulated /proc + injected executors + real PG)
# --------------------------------------------------------------------------- #
def rehearse_quiesce_fence(
    intent: dict[str, Any],
    operator_authorization: Any,
    signature: Any,
    *,
    now: str,
    source_head: str,
    host_probe: QuiesceHostProbe,
    fence_ops: QuiesceFenceOps,
    db_observer: QuiesceDbObserver,
    clock: Callable[[], float],
    sleep: Callable[[float], None] | None = None,
    verifier_capture_digest: str | None = None,
    target_view: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Rehearse the S2.1 fence cycle through the runner's own classes (never on production).

    ``target_view`` 只在排練面存在且**只能加嚴**:derived 或 injected 任一為 ``production`` /
    ``unknown`` 即拒。落盤的 ``target_class_view.target_class`` 永遠是導出值。
    """

    derived = host_kernel.derive_host_target_class()
    refusals = host_kernel.rehearsal_target_refusals(derived, target_view)
    if refusals:
        raise S2_1HostRunnerError(
            "refusing to rehearse the S2.1 quiesce fence: " + "; ".join(refusals)
        )
    view = host_kernel.rehearsal_target_view_record(derived, target_view)
    _require_runner_capabilities(host_probe, fence_ops, db_observer)
    surface_errors = host_kernel.assert_read_only_surface(host_probe)
    surface_errors.extend(host_kernel.assert_read_only_surface(db_observer))
    if surface_errors:
        raise S2_1HostRunnerError("; ".join(surface_errors))
    receipt = quiesce_fence.apply_quiesce_fence(
        intent, operator_authorization, signature,
        now=now, source_head=source_head, host_probe=host_probe, fence_ops=fence_ops,
        db_observer=db_observer, clock=clock, sleep=sleep,
        verifier_capture_digest=verifier_capture_digest,
    )
    result = _run_result(
        lane="disposable_rehearsal", target_view=view, receipt=receipt,
        probe=host_probe, fence_ops=fence_ops,
        verifier_node=str(intent.get("postcheck_node_id")),
    )
    result["rehearsal"] = True
    return result

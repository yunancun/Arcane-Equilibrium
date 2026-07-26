#!/usr/bin/env python3
"""S2.4(WP4·W4a)§5.2 install lock + §9.1 replay-ledger **append** 葉。

兩件 W3 明載為 W4 義務的事在此落地:

1. **exact install-lock 取得契約**(§5.2)。runner 以 ``O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC``
   開啟已驗的 root-owned ``/run/lock`` parent、綁其 device/inode/mode,再以
   ``openat(O_NOFOLLOW|O_CREAT|O_CLOEXEC, 0600)`` 開固定 basename;``fstat`` 必須證明
   root-owned 一般檔、mode ``0600``、link count 為一、且 device 等於 parent,**才**做
   non-blocking exclusive ``flock``。lock **永不** unlink。競爭回
   :data:`LOCK_STATUS_HELD` 且零變更;symlink、hardlink、被置換的 parent、寬鬆
   ownership/mode 一律回 :data:`LOCK_STATUS_PRECHECK_FAILED`。

2. **replay-ledger 的 append 側**(§9.1 / W3 obligation ``REPLAY_LEDGER_APPEND``)。W3 只
   讀 ledger head 證明「未消費」,從不 append,故一張 permit 在 TTL 內可驅動無上限次操作。
   此處提供 atomic、hash-chained、fsynced、consume-once 的 append:必須**持有 install
   lock**、必須以 lock 下讀到的 **durable ledger head**(而非 caller 傳入的快照)裁決、
   相同 key 的 idempotent replay 成功且**不**重複 append、相同 key 綁不同 plan 一律
   ``AUTHORIZATION_REJECTED``(§10.5 #8)。

所有主機動作經注入 protocol(``driver=None`` 一律 typed ``EXTERNAL_VERIFICATION_PENDING``
且零變更);durable 落盤沿用 :mod:`agent_governance_s2_4_journal` 的同一條
temp→fsync→rename→parent-fsync 紀律。九 authority 恆 false。
"""
from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_4_journal as _journal  # noqa: E402

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest

# ── §5.2 的 exact lock 面(worker 不得選 lock 位置,§10.4)───────────────────────
INSTALL_LOCK_PATH = "/run/lock/arcane-equilibrium-aiml-s2-4-install.lock"
INSTALL_LOCK_PARENT = "/run/lock"
INSTALL_LOCK_BASENAME = "arcane-equilibrium-aiml-s2-4-install.lock"
LOCK_PARENT_OPEN_FLAGS = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
LOCK_FILE_OPEN_FLAGS = ("O_NOFOLLOW", "O_CREAT", "O_CLOEXEC")
LOCK_FILE_MODE = "0600"
LOCK_FILE_MODE_BITS = 0o600
# /run/lock 在 systemd 主機上是 root-owned;world-writable(1777)等寬鬆位一律不接受。
LOCK_PARENT_ACCEPTED_MODES = ("0700", "0750", "0755")

LOCK_STATUS_ACQUIRED = "INSTALL_LOCK_ACQUIRED"
LOCK_STATUS_HELD = "INSTALL_LOCK_HELD"
LOCK_STATUS_RELEASED = "INSTALL_LOCK_RELEASED"
LOCK_STATUS_PRECHECK_FAILED = "PRECHECK_FAILED"
LOCK_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
LOCK_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
LOCK_TYPED_STATUSES = (
    LOCK_STATUS_ACQUIRED,
    LOCK_STATUS_HELD,
    LOCK_STATUS_PENDING,
    LOCK_STATUS_PRECHECK_FAILED,
    LOCK_STATUS_RECOVERY_REQUIRED,
    LOCK_STATUS_RELEASED,
)
# §5.2:lock 永不被 unlink——driver 上出現這些面即 typed 拒。
FORBIDDEN_LOCK_METHODS = (
    "chmod",
    "chown",
    "remove",
    "rename",
    "rmdir",
    "truncate",
    "unlink",
    "unlink_lock",
)

# ── §9.1 replay ledger ─────────────────────────────────────────────────────────
REPLAY_LEDGER_PATH = (
    "/var/lib/arcane-equilibrium/aiml/install/s2_4/authorization-replay-ledger.json"
)
REPLAY_LEDGER_SCHEMA_VERSION = "s2_4_authorization_replay_ledger_v1"
REPLAY_STATUS_CONSUME_ADMITTED = "CONSUME_ADMITTED"
REPLAY_STATUS_IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY_ADMITTED"
REPLAY_STATUS_APPENDED = "AUTHORIZATION_CONSUMPTION_APPENDED"
REPLAY_STATUS_REJECTED = "AUTHORIZATION_REJECTED"
REPLAY_STATUS_LOCK_REQUIRED = "INSTALL_LOCK_REQUIRED"
REPLAY_STATUS_PENDING = LOCK_STATUS_PENDING
REPLAY_STATUS_CORRUPT = "LEDGER_CORRUPT_RECOVERY_REQUIRED"
REPLAY_TYPED_STATUSES = (
    REPLAY_STATUS_APPENDED,
    REPLAY_STATUS_CONSUME_ADMITTED,
    REPLAY_STATUS_CORRUPT,
    REPLAY_STATUS_IDEMPOTENT_REPLAY,
    REPLAY_STATUS_LOCK_REQUIRED,
    REPLAY_STATUS_PENDING,
    REPLAY_STATUS_REJECTED,
)
_ALL_FALSE_PRODUCTION_FLAGS = {
    "nine_authorities_false": True,
    "production_apply_performed": False,
    "running_attested": False,
}


class LockContractError(ValueError):
    """lock/ledger 契約層硬錯誤(帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _InstallLockToken:
    """module-private 的持有憑證(不可由呼叫端偽造:類別本身不對外 re-export)。

    ``nonce`` 是這張憑證的身分。過去 live-set 記的是 ``id(token)``——CPython 的位址在物件被
    回收後會被**重用**,所以一個「acquire 之後把 verdict 丟掉而沒有 release」的呼叫端會在
    set 裡留下一個永久 live 的 id,而之後任何一個恰好配置到同一位址的新 token(包括從未經
    ``acquire_s2_4_install_lock`` 發出的)都會通過 ``install_lock_is_held``,卻沒有持有任何
    ``flock``。128-bit 隨機 nonce 沒有這個性質。
    """

    __slots__ = ("lock_fd", "nonce")

    def __init__(self, lock_fd: Any) -> None:
        self.lock_fd = lock_fd
        self.nonce = secrets.token_bytes(16)


# 目前**真的**持有中的 token nonce。release 之後移出,於是一份已釋放的 verdict 立刻失效。
_LIVE_LOCK_TOKENS: set[bytes] = set()


def install_lock_is_held(lock_verdict: Any) -> bool:
    """「這個呼叫端此刻真的持有 install lock」的唯一判準(§5.2)。

    舊判準 ``lock_verdict.get("status") == "INSTALL_LOCK_ACQUIRED"`` 是**未認證的 caller
    字典**:任何人手寫一個同形 dict 就能通過每一道「必須持有 lock」的閘,而這些閘是
    W6 runner 的匯出接縫(SCRIPT_INDEX 明載),所以那是現在就可利用的洞,不是潛在風險。
    此處改為 type + membership:token 只由 :func:`acquire_s2_4_install_lock` 產生,且必須
    仍在 :data:`_LIVE_LOCK_TOKENS` 內(釋放後即失效)。
    """

    if not isinstance(lock_verdict, dict):
        return False
    if lock_verdict.get("status") != LOCK_STATUS_ACQUIRED:
        return False
    token = lock_verdict.get("lock_token")
    return isinstance(token, _InstallLockToken) and token.nonce in _LIVE_LOCK_TOKENS


def _lock_not_held_reasons(lock_verdict: Any, *, action: str) -> list[str]:
    """未持有 lock 的 typed reason(區分「沒 token」與「token 已釋放/偽造」)。"""

    if isinstance(lock_verdict, dict) and lock_verdict.get("status") == (
        LOCK_STATUS_ACQUIRED
    ) and not isinstance(lock_verdict.get("lock_token"), _InstallLockToken):
        return [
            f"{action} refused: the supplied lock proof carries no install-lock token. A "
            "verdict-shaped dict is not the lock; only acquire_s2_4_install_lock issues a "
            "token and only while it is still held (§5.2)"
        ]
    if isinstance(lock_verdict, dict) and isinstance(
        lock_verdict.get("lock_token"), _InstallLockToken
    ):
        return [
            f"{action} refused: this install-lock token has already been released; a released "
            "proof never re-authorizes anything (§5.2)"
        ]
    return [
        f"{action} refused: no acquired install lock was supplied; the exclusive S2.4 install "
        "lock is the only writer admission (§5.2)"
    ]


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _resolve_now(now: Any) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return central_validator._parse_timestamp(now)


# --------------------------------------------------------------------------- #
# 1) install lock(§5.2 exact 取得契約)
# --------------------------------------------------------------------------- #
class InstallLockDriver(Protocol):
    """§5.2 的 lock 面。**沒有** unlink/chmod 入口;flock 為 non-blocking exclusive。

    ``open_parent_directory`` / ``fstat_parent`` 回
    ``{"fd", "device", "inode", "nlink", "mode", "uid", "is_dir", "is_symlink"}``;
    ``openat_lock_file`` 回 ``{"fd"}``;``fstat_lock_file`` 回
    ``{"uid", "gid", "mode", "nlink", "device", "inode", "is_regular_file"}``;
    ``flock_exclusive_nonblocking`` 在被別人持有時回 ``False``(``EWOULDBLOCK``),
    絕不阻塞。
    """

    def open_parent_directory(
        self, *, path: str, flags: tuple[str, ...]
    ) -> dict[str, Any]: ...

    def fstat_parent(self, *, fd: Any) -> dict[str, Any]: ...

    def openat_lock_file(
        self, *, parent_fd: Any, basename: str, flags: tuple[str, ...], mode: int
    ) -> dict[str, Any]: ...

    def fstat_lock_file(self, *, fd: Any) -> dict[str, Any]: ...

    def flock_exclusive_nonblocking(self, *, fd: Any) -> bool: ...

    def close(self, *, fd: Any) -> None: ...


def assert_no_lock_unlink_surface(driver: Any) -> list[str]:
    """§5.2:driver 上出現任何 unlink/rename/chmod 面即 typed 拒(lock 永不被 unlink)。"""

    return [
        f"the injected install-lock driver exposes {name!r}; the S2.4 install lock is never "
        "unlinked, renamed or re-moded (§5.2)"
        for name in FORBIDDEN_LOCK_METHODS
        if callable(getattr(driver, name, None))
    ]


def _lock_verdict(
    status: str,
    reasons: list[str],
    *,
    lock_fd: Any = None,
    bound_parent: dict[str, Any] | None = None,
    lock_file_created: bool = False,
    driver_engaged: bool = False,
    lock_token: Any = None,
) -> dict[str, Any]:
    return {
        "schema_version": "s2_4_install_lock_verdict_v1_informal",
        "status": status,
        "reasons": list(reasons),
        "lock_path": INSTALL_LOCK_PATH,
        "lock_fd": lock_fd,
        "lock_token": lock_token,
        "bound_parent": bound_parent,
        # lock 檔的建立不是 install 狀態的變更(§5.2 明載 O_CREAT 且永不 unlink);
        # 競爭/precheck 失敗時 install 狀態一律零變更。
        "mutation_performed": False,
        "lock_file_created": bool(lock_file_created),
        "lock_unlinked": False,
        "driver_engaged": bool(driver_engaged),
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
    }


def _lock_parent_reasons(observed: Any) -> list[str]:
    if not isinstance(observed, dict):
        return [f"install-lock parent {INSTALL_LOCK_PARENT} observation is not an object"]
    reasons: list[str] = []
    if observed.get("is_dir") is not True:
        reasons.append(f"install-lock parent {INSTALL_LOCK_PARENT} is not a directory")
    if observed.get("is_symlink") is True:
        reasons.append(
            f"install-lock parent {INSTALL_LOCK_PARENT} is a symlink; O_DIRECTORY|O_NOFOLLOW "
            "refuses it"
        )
    if observed.get("uid") != 0:
        reasons.append(
            f"install-lock parent {INSTALL_LOCK_PARENT} is not root-owned (permissive "
            "ownership is PRECHECK_FAILED)"
        )
    if str(observed.get("mode")) not in LOCK_PARENT_ACCEPTED_MODES:
        reasons.append(
            f"install-lock parent {INSTALL_LOCK_PARENT} mode {observed.get('mode')!r} is "
            f"permissive; only {list(LOCK_PARENT_ACCEPTED_MODES)} are accepted"
        )
    for field in ("device", "inode"):
        if not isinstance(observed.get(field), int):
            reasons.append(f"install-lock parent {field} is not bound")
    return reasons


def _lock_file_reasons(observed: Any, *, expected_device: Any) -> list[str]:
    """``fstat`` 必須證明 root-owned 一般檔 / mode 0600 / link count 一 / 期望 device。"""

    if not isinstance(observed, dict):
        return ["install-lock fstat did not return an observation object"]
    reasons: list[str] = []
    if observed.get("is_regular_file") is not True:
        reasons.append(
            "the install lock is not a regular file (a symlink or special file is "
            "PRECHECK_FAILED)"
        )
    if observed.get("uid") != 0:
        reasons.append("the install lock is not root-owned")
    if str(observed.get("mode")) != LOCK_FILE_MODE:
        reasons.append(
            f"the install lock mode is {observed.get('mode')!r}, not the required "
            f"{LOCK_FILE_MODE}"
        )
    if observed.get("nlink") != 1:
        reasons.append(
            "the install lock link count is not one (a hardlinked lock is PRECHECK_FAILED)"
        )
    if observed.get("device") != expected_device:
        reasons.append(
            "the install lock is not on the bound parent device (replaced parent or "
            "cross-device lock is PRECHECK_FAILED)"
        )
    return reasons


def acquire_s2_4_install_lock(driver: Any = None) -> dict[str, Any]:
    """§5.2:取得(或 typed 拒絕)唯一的 install-transaction writer 權。

    固定順序:parent 目錄 FD(``O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC``)→ 綁 device/inode/mode
    → ``openat`` 固定 basename(``O_NOFOLLOW|O_CREAT|O_CLOEXEC``, ``0600``)→ ``fstat``
    四項證明 → parent 置換重驗 → non-blocking exclusive ``flock``。

    回 typed verdict:``INSTALL_LOCK_ACQUIRED`` / ``INSTALL_LOCK_HELD``(競爭,零變更)/
    ``PRECHECK_FAILED``(symlink、hardlink、被置換的 parent、寬鬆 ownership/mode)/
    ``EXTERNAL_VERIFICATION_PENDING``(無 driver,零變更)/ ``RECOVERY_REQUIRED``(driver 逸出)。
    """

    if driver is None:
        return _lock_verdict(
            LOCK_STATUS_PENDING,
            [
                "the install lock is reachable but authority-locked: no host lock driver is "
                "present (Mac/source/test lane); EXTERNAL_VERIFICATION_PENDING with zero "
                "mutation"
            ],
        )
    unlink_surface = assert_no_lock_unlink_surface(driver)
    if unlink_surface:
        return _lock_verdict(LOCK_STATUS_PRECHECK_FAILED, unlink_surface, driver_engaged=True)
    parent_fd = None
    lock_fd = None
    created = False
    acquired = False
    try:
        parent = driver.open_parent_directory(
            path=INSTALL_LOCK_PARENT, flags=LOCK_PARENT_OPEN_FLAGS
        )
        parent_reasons = _lock_parent_reasons(parent)
        if parent_reasons:
            if isinstance(parent, dict):
                parent_fd = parent.get("fd")
            return _lock_verdict(
                LOCK_STATUS_PRECHECK_FAILED, parent_reasons, driver_engaged=True
            )
        parent_fd = parent["fd"]
        bound_parent = {
            "device": parent["device"], "inode": parent["inode"], "mode": str(parent["mode"])
        }
        opened = driver.openat_lock_file(
            parent_fd=parent_fd,
            basename=INSTALL_LOCK_BASENAME,
            flags=LOCK_FILE_OPEN_FLAGS,
            mode=LOCK_FILE_MODE_BITS,
        )
        if not isinstance(opened, dict) or "fd" not in opened:
            return _lock_verdict(
                LOCK_STATUS_PRECHECK_FAILED,
                ["openat of the install lock did not return a file descriptor"],
                bound_parent=bound_parent, driver_engaged=True,
            )
        lock_fd = opened["fd"]
        created = bool(opened.get("created", False))
        stat = driver.fstat_lock_file(fd=lock_fd)
        file_reasons = _lock_file_reasons(stat, expected_device=bound_parent["device"])
        if file_reasons:
            return _lock_verdict(
                LOCK_STATUS_PRECHECK_FAILED, file_reasons, bound_parent=bound_parent,
                lock_file_created=created, driver_engaged=True,
            )
        recheck_reasons = _reresolve_lock_parent_reasons(driver, bound_parent)
        if recheck_reasons:
            return _lock_verdict(
                LOCK_STATUS_PRECHECK_FAILED, recheck_reasons,
                bound_parent=bound_parent, lock_file_created=created, driver_engaged=True,
            )
        if driver.flock_exclusive_nonblocking(fd=lock_fd) is not True:
            return _lock_verdict(
                LOCK_STATUS_HELD,
                [
                    "another writer already owns this S2.4 install transaction "
                    "(non-blocking exclusive flock would block); INSTALL_LOCK_HELD with zero "
                    "mutation"
                ],
                bound_parent=bound_parent, lock_file_created=created, driver_engaged=True,
            )
    except Exception as error:  # noqa: BLE001 - 任何 driver 逸出都 fail-closed
        return _lock_verdict(
            LOCK_STATUS_RECOVERY_REQUIRED,
            [f"install-lock acquisition failed: {_journal.redact_driver_error(error)}"],
            lock_file_created=created, driver_engaged=True,
        )
    else:
        acquired = True
    finally:
        # lock FD 只有在**真的取得**時才交給呼叫端;競爭、precheck 失敗與例外路徑都必須把它
        # 關掉,否則一個重試迴圈會把 RLIMIT_NOFILE 用盡(每次競爭洩一個 fd)。
        if not acquired and lock_fd is not None:
            try:
                driver.close(fd=lock_fd)
            except Exception:  # noqa: BLE001
                pass
        if parent_fd is not None:
            try:
                driver.close(fd=parent_fd)
            except Exception:  # noqa: BLE001
                pass
    token = _InstallLockToken(lock_fd)
    _LIVE_LOCK_TOKENS.add(token.nonce)
    return _lock_verdict(
        LOCK_STATUS_ACQUIRED, [], lock_fd=lock_fd, bound_parent=bound_parent,
        lock_file_created=created, driver_engaged=True, lock_token=token,
    )


def _reresolve_lock_parent_reasons(driver: Any, bound_parent: dict[str, Any]) -> list[str]:
    """flock 之前**重新解析** ``/run/lock`` 並與綁定值比對(有牙齒的置換偵測)。

    以同一個 dirfd 再 ``fstat`` 一次不可能失敗——fd 釘住 inode。真正要排除的情境是:綁定
    之後 ``/run/lock`` 這個**路徑**被換成別的目錄,於是我們鎖住的是一個孤兒 inode 上的檔,
    而其他 runner 會去鎖新路徑下的另一個檔——互斥就此消失。重新解析才看得見這件事。
    """

    observed = driver.open_parent_directory(
        path=INSTALL_LOCK_PARENT, flags=LOCK_PARENT_OPEN_FLAGS
    )
    try:
        reasons = _lock_parent_reasons(observed)
        if not reasons and (
            observed["device"] != bound_parent["device"]
            or observed["inode"] != bound_parent["inode"]
        ):
            reasons.append(
                f"install-lock parent {INSTALL_LOCK_PARENT} was replaced between the "
                "directory-FD binding and the flock (the path now resolves to a different "
                "directory); PRECHECK_FAILED with zero mutation"
            )
        return reasons
    finally:
        if isinstance(observed, dict) and observed.get("fd") is not None:
            try:
                driver.close(fd=observed["fd"])
            except Exception:  # noqa: BLE001
                pass


def release_s2_4_install_lock(driver: Any, lock_verdict: Any) -> dict[str, Any]:
    """關閉 lock FD 釋放 ``flock``,並**作廢 token**;永不 unlink(§5.2)。

    舊行為只關 fd 而不動 verdict,於是一份已釋放的 verdict 永遠通得過每一道「必須持有
    lock」的閘。釋放之後 token 立刻移出 :data:`_LIVE_LOCK_TOKENS`,verdict 自身也改記
    ``INSTALL_LOCK_RELEASED``。
    """

    if not install_lock_is_held(lock_verdict):
        return {
            "status": "NOT_HELD",
            "reasons": _lock_not_held_reasons(lock_verdict, action="install-lock release"),
            "lock_unlinked": False,
        }
    _LIVE_LOCK_TOKENS.discard(lock_verdict["lock_token"].nonce)
    lock_verdict["status"] = LOCK_STATUS_RELEASED
    try:
        driver.close(fd=lock_verdict.get("lock_fd"))
    except Exception as error:  # noqa: BLE001
        return {
            "status": LOCK_STATUS_RECOVERY_REQUIRED,
            "reasons": [f"install-lock release failed: {_journal.redact_driver_error(error)}"],
            "lock_unlinked": False,
        }
    return {"status": LOCK_STATUS_RELEASED, "reasons": [], "lock_unlinked": False}


# --------------------------------------------------------------------------- #
# 2) replay ledger 的 append 側(§9.1 / W3 obligation REPLAY_LEDGER_APPEND)
# --------------------------------------------------------------------------- #
def empty_replay_ledger(*, ledger_path: str = REPLAY_LEDGER_PATH) -> dict[str, Any]:
    """尚未有任何消費紀錄時的 genesis 形(schema 要求 entries 非空,故以 ``None`` 表示無檔)。"""

    return {
        "schema_version": REPLAY_LEDGER_SCHEMA_VERSION,
        "ledger_path": ledger_path,
        "entries": [],
        "append_only": True,
    }


def build_replay_ledger_entry(
    *,
    seq: int,
    prev_entry_digest: str | None,
    authorization: dict[str, Any],
    consumed_at: str,
) -> dict[str, Any]:
    """一筆 hash-chained 消費紀錄(``entry_digest`` 由除自身以外的 canonical bytes 導出)。"""

    entry: dict[str, Any] = {
        "seq": int(seq),
        "prev_entry_digest": prev_entry_digest,
        "authorization_id": authorization["authorization_id"],
        "authorization_digest": authorization["self_digest"],
        "profile_identity": authorization["profile_identity"],
        "consumed_at": consumed_at,
        "fsynced": True,
    }
    entry["entry_digest"] = canonical_digest(entry)
    return entry


def seal_replay_ledger(ledger: dict[str, Any]) -> dict[str, Any]:
    sealed = {key: value for key, value in ledger.items() if key != "self_digest"}
    sealed["self_digest"] = artifact_self_digest(sealed)
    return sealed


def append_replay_entries(
    ledger: Any,
    authorizations: list[dict[str, Any]],
    *,
    consumed_at: str,
    ledger_path: str = REPLAY_LEDGER_PATH,
) -> dict[str, Any]:
    """純函式 append:回**新的**已封 ledger(hash chain 續接;不改動輸入物件)。

    ``ledger_path`` 一律取**呼叫端實際要寫進去的那個路徑**,絕不沿用被讀回物件自報的值:
    後者是被讀取的位元組的一部分,一份宣稱自己住在別處的 ledger 若被原樣沿用,封好的
    artifact 就會記著一個它從未被寫入過的位置。
    """

    if not isinstance(ledger, dict):
        raise LockContractError("replay_ledger_not_an_object")
    entries = [dict(item) for item in (ledger.get("entries") or [])]
    previous = entries[-1]["entry_digest"] if entries else None
    for authorization in authorizations:
        entry = build_replay_ledger_entry(
            seq=len(entries), prev_entry_digest=previous, authorization=authorization,
            consumed_at=consumed_at,
        )
        previous = entry["entry_digest"]
        entries.append(entry)
    return seal_replay_ledger({
        "schema_version": REPLAY_LEDGER_SCHEMA_VERSION,
        "ledger_path": str(ledger_path),
        "entries": entries,
        "append_only": True,
    })


def derive_replay_consumption_decision(
    authorization: Any,
    ledger: Any,
    *,
    expected_payload_binding: Any,
    profile_key: Any = None,
    now: Any = None,
) -> dict[str, Any]:
    """一張 permit 對「lock 下讀到的 durable ledger head」的 consume-once 裁決(§9.1/§10.5 #8)。

    三分 typed 結果:

      * :data:`REPLAY_STATUS_CONSUME_ADMITTED` —— ledger 內無此 ``authorization_id``,
        且 permit 的 plan binding 與消費端獨立再導出的期望值逐欄相符 → 可 append 後執行;
      * :data:`REPLAY_STATUS_IDEMPOTENT_REPLAY` —— 恰一筆同 ``authorization_id`` 的紀錄,
        其 ``authorization_digest`` 與 ``profile_identity`` 皆等於本 permit → 同 key、同
        plan 的 replay:**成功**、不重複 append、不重跑 effect(§10.5 #8 前半);
      * :data:`REPLAY_STATUS_REJECTED` —— 同 key 綁到**不同** authorization/plan、重複紀錄、
        鏈斷/亂序/竄改、permit 自身無效/過期、或 plan binding 不符(§10.5 #8 後半)。

    誠實界線:此裁決必須餵入 install lock 下讀到的 exact durable head;caller 傳入的快照
    無從偵測 stale-prefix/fork(見 :func:`consume_authorizations_under_lock`)。
    """

    verdict: dict[str, Any] = {
        "schema_version": "s2_4_replay_consumption_decision_v1_informal",
        "status": REPLAY_STATUS_REJECTED,
        "reasons": [],
        "authorization_id": None,
        "production_effect": LOCK_STATUS_PENDING,
    }
    if not isinstance(authorization, dict):
        verdict["reasons"] = ["authorization must be an object"]
        return verdict
    verdict["authorization_id"] = authorization.get("authorization_id")
    # §9.1 新鮮窗:``_s2_4_operator_authorization_errors`` 在 ``now is None`` 時**整段跳過**
    # 新鮮度檢查,而本函式過去把 ``now`` 原樣轉發。於是「空 ledger + now=None」——也就是系統
    # 一生中燒掉的第一張 permit——會把一張 2030 年才生效的 permit 判成 CONSUME_ADMITTED。
    # 姊妹函式 derive_authorization_replay_binding 早就預設牆鐘,這裡對齊它。
    resolved_now = _resolve_now(now)
    binding = central_validator.derive_permit_plan_binding_status(
        authorization,
        expected_payload_binding=expected_payload_binding,
        profile_key=profile_key,
    )
    if binding["status"] != central_validator.PERMIT_PLAN_BINDING_STATUS_VERIFIED:
        verdict["reasons"] = list(binding["reasons"])
        return verdict
    entries = (ledger or {}).get("entries") if isinstance(ledger, dict) else None
    if isinstance(entries, list) and not entries:
        # 空 ledger:schema 的 minItems:1 不適用於「還沒有任何消費」的 genesis 狀態,
        # 故此處只驗 permit 本身(下方 read-binding 需要非空 entries)。
        permit_reasons = central_validator._s2_4_operator_authorization_errors(
            authorization, now=resolved_now
        )
        if permit_reasons:
            verdict["reasons"] = permit_reasons
            return verdict
        verdict["status"] = REPLAY_STATUS_CONSUME_ADMITTED
        return verdict
    read_binding = central_validator.derive_authorization_replay_binding(
        authorization, ledger, now=resolved_now
    )
    if read_binding["status"] == "UNCONSUMED_AUTHORIZATION_VALID":
        verdict["status"] = REPLAY_STATUS_CONSUME_ADMITTED
        return verdict
    matches = [
        entry
        for entry in (entries or [])
        if isinstance(entry, dict)
        and entry.get("authorization_id") == authorization.get("authorization_id")
    ]
    if (
        len(matches) == 1
        and matches[0].get("authorization_digest") == authorization.get("self_digest")
        and matches[0].get("profile_identity") == authorization.get("profile_identity")
        and not central_validator._s2_4_replay_ledger_errors(ledger)
        and not central_validator._s2_4_operator_authorization_errors(
            authorization, now=resolved_now
        )
    ):
        verdict["status"] = REPLAY_STATUS_IDEMPOTENT_REPLAY
        verdict["reasons"] = [
            "this exact permit (same idempotency key, same plan binding, same permit digest) "
            "is already recorded as consumed; the replay is idempotent — no second entry is "
            "appended and the effect is not re-executed (§10.5 #8)"
        ]
        return verdict
    verdict["reasons"] = list(read_binding["reasons"])
    return verdict


def consume_authorizations_under_lock(
    driver: Any = None,
    *,
    authorizations: Any = None,
    expected_payload_bindings: Any = None,
    lock_verdict: Any = None,
    now: Any = None,
    ledger_path: str = REPLAY_LEDGER_PATH,
) -> dict[str, Any]:
    """atomically 消費一組 permit:lock 下讀 durable head → 裁決 → hash-chained append → fsync。

    ``authorizations`` 是 ``{profile_key: authorization}``,``expected_payload_bindings`` 是
    ``{profile_key: 消費端獨立再導出的期望 payload 子集}``(兩者鍵集必須相同)。

    §9.1:APPLY 於第一次變更之前 **atomically** 消費 aggregate 與 PG 兩個 id/digest——本函式
    因此是全有全無:任一 permit 非 ADMITTED/IDEMPOTENT 即回 ``AUTHORIZATION_REJECTED`` 且零
    append;全部 IDEMPOTENT 則回 ``IDEMPOTENT_REPLAY_ADMITTED``(不 append);否則把所有需要
    新紀錄的 permit 以一次 atomic durable write 一併 append。
    """

    outcome: dict[str, Any] = {
        "schema_version": "s2_4_replay_append_verdict_v1_informal",
        "status": REPLAY_STATUS_REJECTED,
        "reasons": [],
        "ledger_path": ledger_path,
        "ledger": None,
        "appended_authorization_ids": [],
        "decisions": {},
        "mutation_performed": False,
        "driver_engaged": False,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
    }
    if not isinstance(authorizations, dict) or not authorizations:
        outcome["reasons"] = ["authorizations must be a non-empty {profile_key: permit} map"]
        return outcome
    if not isinstance(expected_payload_bindings, dict) or sorted(
        expected_payload_bindings
    ) != sorted(authorizations):
        outcome["reasons"] = [
            "every consumed permit needs its own independently re-derived expected payload "
            "binding (an unbound permit authorizes any intent of its class inside its TTL)"
        ]
        return outcome
    if not install_lock_is_held(lock_verdict):
        outcome["status"] = REPLAY_STATUS_LOCK_REQUIRED
        outcome["reasons"] = _lock_not_held_reasons(
            lock_verdict, action="authorization consumption"
        ) + [
            "authorization consumption is appended and fsynced only under the exclusive "
            "S2.4 install lock (§9.1); no lock, no append"
        ]
        return outcome
    if driver is None:
        outcome["status"] = REPLAY_STATUS_PENDING
        outcome["reasons"] = [
            "the replay-ledger append is reachable but authority-locked: no host file driver "
            "is present (Mac/source/test lane); EXTERNAL_VERIFICATION_PENDING with zero "
            "mutation"
        ]
        return outcome
    outcome["driver_engaged"] = True
    store = _journal.JournalStore(
        driver, journal_path=ledger_path, parent_mode=_journal.JOURNAL_PARENT_MODE
    )
    read = _read_durable_ledger(store, ledger_path=ledger_path)
    if read["status"] not in {"LEDGER_LOADED", "LEDGER_ABSENT"}:
        outcome["status"] = read["status"]
        outcome["reasons"] = read["reasons"]
        return outcome
    ledger = read["ledger"]
    now_text = _iso(_resolve_now(now))
    pending: list[tuple[str, dict[str, Any]]] = []
    for profile_key in sorted(authorizations):
        decision = derive_replay_consumption_decision(
            authorizations[profile_key],
            ledger,
            expected_payload_binding=expected_payload_bindings[profile_key],
            profile_key=profile_key,
            now=now,
        )
        outcome["decisions"][profile_key] = decision
        if decision["status"] == REPLAY_STATUS_CONSUME_ADMITTED:
            pending.append((profile_key, authorizations[profile_key]))
        elif decision["status"] != REPLAY_STATUS_IDEMPOTENT_REPLAY:
            outcome["reasons"] = [
                f"{profile_key}: {reason}" for reason in decision["reasons"]
            ] + [
                "atomic consumption is all-or-nothing; nothing was appended (§9.1)"
            ]
            return outcome
    if not pending:
        outcome["status"] = REPLAY_STATUS_IDEMPOTENT_REPLAY
        outcome["ledger"] = ledger
        outcome["reasons"] = [
            "every supplied permit is already recorded as consumed for this exact plan "
            "binding; the replay is idempotent and no entry was appended"
        ]
        return outcome
    appended = append_replay_entries(
        ledger, [authorization for _, authorization in pending], consumed_at=now_text,
        ledger_path=ledger_path,
    )
    central_errors = central_validator.validate_aiml_artifact(appended)
    chain_errors = central_validator._s2_4_replay_ledger_errors(appended)
    if central_errors or chain_errors:
        outcome["reasons"] = central_errors + chain_errors + [
            "refusing to persist a replay ledger that does not re-derive its hash chain"
        ]
        return outcome
    commit = _commit_durable_ledger(store, appended)
    if commit["status"] != _journal.JOURNAL_STATUS_COMMITTED:
        outcome["status"] = (
            REPLAY_STATUS_CORRUPT
            if commit["status"] == _journal.JOURNAL_STATUS_CORRUPT
            else commit["status"]
        )
        outcome["reasons"] = commit["reasons"]
        return outcome
    outcome["status"] = REPLAY_STATUS_APPENDED
    outcome["ledger"] = appended
    outcome["mutation_performed"] = True
    outcome["appended_authorization_ids"] = [
        authorization["authorization_id"] for _, authorization in pending
    ]
    return outcome


def _read_durable_ledger(store: Any, *, ledger_path: str) -> dict[str, Any]:
    """以 journal 的 durable 讀路徑讀 ledger;畸形/截斷/chain 不符即 typed CORRUPT。"""

    if store.driver is None:
        return {"status": REPLAY_STATUS_PENDING, "reasons": [], "ledger": None}
    parent_fd = None
    try:
        parent_fd, reasons = store._open_parent()
        if reasons:
            return {
                "status": LOCK_STATUS_PRECHECK_FAILED, "reasons": reasons, "ledger": None
            }
        payload = store.driver.read_journal_bytes(
            parent_fd=parent_fd, basename=store.basename
        )
    except Exception as error:  # noqa: BLE001
        return {
            "status": REPLAY_STATUS_CORRUPT,
            "reasons": [
                f"replay-ledger bytes are unreadable: "
                f"{_journal.redact_driver_error(error)}"
            ],
            "ledger": None,
        }
    finally:
        if parent_fd is not None:
            try:
                store.driver.close(fd=parent_fd)
            except Exception:  # noqa: BLE001
                pass
    if payload is None:
        return {
            "status": "LEDGER_ABSENT",
            "reasons": [],
            "ledger": empty_replay_ledger(ledger_path=ledger_path),
        }
    try:
        ledger = json.loads(bytes(payload).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return {
            "status": REPLAY_STATUS_CORRUPT,
            "reasons": [
                f"replay ledger is malformed or truncated ({type(error).__name__}); it is "
                "never renamed away or overwritten automatically"
            ],
            "ledger": None,
        }
    errors = central_validator.validate_aiml_artifact(
        ledger
    ) + central_validator._s2_4_replay_ledger_errors(ledger)
    # 讀回來的 ledger 必須自報它就住在我們剛剛讀的那個路徑;不符即 typed CORRUPT
    # (一份被搬過來的 ledger 不是這條 lane 的 durable head)。
    if isinstance(ledger, dict) and ledger.get("ledger_path") != ledger_path:
        errors.append(
            f"replay ledger self-reports ledger_path {ledger.get('ledger_path')!r} but was "
            f"read from {ledger_path}; a ledger that records a location it was not written "
            "to is not this lane's durable head"
        )
    if errors:
        return {"status": REPLAY_STATUS_CORRUPT, "reasons": errors, "ledger": None}
    return {"status": "LEDGER_LOADED", "reasons": [], "ledger": ledger}


def _commit_durable_ledger(store: Any, ledger: dict[str, Any]) -> dict[str, Any]:
    """ledger 的 durable 落盤(同 journal 的 temp→fsync→rename→parent-fsync 紀律)。"""

    destructive = _journal.assert_no_journal_destructive_surface(store.driver)
    if destructive:
        return {"status": _journal.JOURNAL_STATUS_PRECHECK_FAILED, "reasons": destructive}
    parent_fd = None
    temp_fd = None
    # 同 JournalStore.commit:暫存名的唯一性來自 ``<pid>-<隨機>``(見 journal_temp_basename
    # 的說明);``attempts`` 只數同一行程內的重試。
    temp_basename = _journal.journal_temp_basename(store.basename, attempt=store.attempts)
    store.attempts += 1
    try:
        parent_fd, reasons = store._open_parent()
        if reasons:
            return {"status": _journal.JOURNAL_STATUS_PRECHECK_FAILED, "reasons": reasons}
        try:
            temp = store.driver.create_temp_file(
                parent_fd=parent_fd, basename=temp_basename,
                flags=_journal.JOURNAL_TEMP_OPEN_FLAGS, mode=_journal.JOURNAL_FILE_MODE_BITS,
            )
        except FileExistsError:
            return {
                "status": _journal.JOURNAL_STATUS_TEMP_COLLISION,
                "reasons": [
                    _journal._temp_residue_reason(store.parent_path, temp_basename)
                ],
            }
        temp_reasons = _journal._temp_file_precheck_reasons(
            temp, expected_device=store.bound_parent["device"]
        )
        if temp_reasons:
            return {"status": _journal.JOURNAL_STATUS_PRECHECK_FAILED, "reasons": temp_reasons}
        temp_fd = temp["fd"]
        payload = central_validator._canonical_bytes(ledger)
        written = store.driver.write_bytes(fd=temp_fd, payload=payload)
        if int(written) != len(payload):
            return {
                "status": _journal.JOURNAL_STATUS_PRECHECK_FAILED,
                "reasons": ["replay-ledger temp write was short; refusing to rename it"],
            }
        store.driver.fsync_file(fd=temp_fd)
        recheck_reasons = store._reresolve_parent_reasons()
        if recheck_reasons:
            return {
                "status": _journal.JOURNAL_STATUS_PRECHECK_FAILED,
                "reasons": recheck_reasons,
            }
        store.driver.atomic_rename(
            parent_fd=parent_fd, from_basename=temp_basename, to_basename=store.basename
        )
        store.driver.fsync_parent_dir(fd=parent_fd)
    except _journal.JournalCrash:
        raise
    except Exception as error:  # noqa: BLE001
        return {
            "status": _journal.JOURNAL_STATUS_RECOVERY_REQUIRED,
            "reasons": [
                f"durable replay-ledger append failed: "
                f"{_journal.redact_driver_error(error)}"
            ],
        }
    finally:
        for fd in (temp_fd, parent_fd):
            if fd is None:
                continue
            try:
                store.driver.close(fd=fd)
            except Exception:  # noqa: BLE001
                pass
    store.commits += 1
    return {"status": _journal.JOURNAL_STATUS_COMMITTED, "reasons": []}


def lock_abi_projection() -> dict[str, Any]:
    """W4 exported-ABI 折入的 lock / replay-append 面。"""

    return {
        "install_lock_path": INSTALL_LOCK_PATH,
        "lock_parent_open_flags": list(LOCK_PARENT_OPEN_FLAGS),
        "lock_file_open_flags": list(LOCK_FILE_OPEN_FLAGS),
        "lock_file_mode": LOCK_FILE_MODE,
        "lock_parent_accepted_modes": list(LOCK_PARENT_ACCEPTED_MODES),
        "forbidden_lock_methods": list(FORBIDDEN_LOCK_METHODS),
        "lock_typed_statuses": list(LOCK_TYPED_STATUSES),
        "replay_ledger_path": REPLAY_LEDGER_PATH,
        "replay_typed_statuses": list(REPLAY_TYPED_STATUSES),
        # A2:每一道「必須持有 lock」的閘用的是 token(type + membership),不是 caller 字典。
        "lock_proof_is_a_module_private_token": True,
        "lock_release_invalidates_the_proof": True,
    }

#!/usr/bin/env python3
"""S2.4(WP4·W4a)§5.2 durable WAL journal 葉——三本 journal、write-ahead 次序與確定性 reconcile。

W3 的 driver 只把每一次 state 轉移**遞交給注入的 driver**(``journal_transition``);真正的
「WAL 落盤」——same-filesystem 暫存 → file ``fsync`` → atomic ``rename`` → parent-dir
``fsync``、canonical self-digest 加獨立 outer checksum、以及 malformed/truncated/checksum
不符時的 typed ``JOURNAL_CORRUPT_RECOVERY_REQUIRED``——是 W4 的義務。本葉提供它:

- :func:`probe_journal_path` / :func:`prepare_journal_path` / :func:`install_journal_path`
  ——§5.2 的三條 exact 路徑,id 由各自 core digest 導出(``s2-4-probe-`` / ``s2-4-prepare-`` /
  ``s2-4-`` 加 64 個小寫 hex);caller 的字串**永不**被 join 進 root 路徑;
- :class:`JournalStore` ——所有主機檔案動作都經注入的 :class:`DurableFileDriver`
  (``driver=None`` 一律 typed ``EXTERNAL_VERIFICATION_PENDING`` 且零變更)。parent 以
  ``O_DIRECTORY|O_NOFOLLOW`` 開啟並綁 device/inode/link count/mode/owner,暫存檔以
  ``openat(O_NOFOLLOW|O_CREAT|O_EXCL, 0600)`` 建立;parent 置換、symlink、hardlink 或跨裝置
  暫存一律 typed ``PRECHECK_FAILED``;
- :class:`WriteAheadTransaction` ——一步一步強制 §5.2 的四段次序:**先** fsync ``APPLYING``
  (帶 exact operation id 與期望 pre/post state)→ 執行一個 typed effect → **獨立**再觀測
  → fsync ``APPLIED``(帶觀測到的 digest)→ 進 ``VERIFYING``。三個 fault 窗
  (``pre_effect`` / ``post_effect_pre_observation`` / ``post_observation_pre_applied_fsync``)
  是 §10.5 #7 crash matrix 的注入點;
- :func:`reconcile_journal` ——§5.2 的四分確定性收斂(等於 post-state → 續驗;等於 pre-state
  → 該步未施作;task-owned 部分態 → 逆序補償;擁有權/狀態不明 → ``RECOVERY_REQUIRED`` 且零變更)。

誠實界線:本葉「不」認證任何 runtime——九 authority / production_apply_performed /
running_attested 恆 false;真 fd/fsync/rename 由 W6 的注入 driver 提供。
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest

# ── §5.2 的固定路徑面(worker 不得選 journal 位置,§10.4)────────────────────────
INSTALL_STATE_ROOT = "/var/lib/arcane-equilibrium/aiml/install/s2_4"
PROBE_JOURNAL_PARENT = INSTALL_STATE_ROOT + "/probes"
PREPARE_JOURNAL_PARENT = INSTALL_STATE_ROOT + "/prepared"
INSTALL_JOURNAL_PARENT = INSTALL_STATE_ROOT
PROBE_ID_PREFIX = "s2-4-probe-"
PREPARE_ID_PREFIX = "s2-4-prepare-"
PLAN_ID_PREFIX = "s2-4-"
_PROBE_ID_RE = re.compile(r"^s2-4-probe-[0-9a-f]{64}$")
_PREPARE_ID_RE = re.compile(r"^s2-4-prepare-[0-9a-f]{64}$")
_PLAN_ID_RE = re.compile(r"^s2-4-[0-9a-f]{64}$")
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
# §5.2:parent 為 root-owned mode 0700;journal 本身 root-owned mode 0600。
JOURNAL_PARENT_MODE = "0700"
JOURNAL_FILE_MODE = "0600"
JOURNAL_FILE_MODE_BITS = 0o600
JOURNAL_PARENT_OPEN_FLAGS = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
JOURNAL_TEMP_OPEN_FLAGS = ("O_NOFOLLOW", "O_CREAT", "O_EXCL", "O_CLOEXEC")
# §5.2 的八個 step state(install/probe);PREPARE 另有 PREPARING(建 staging 之前先 fsync)。
JOURNAL_STATES = (
    "NOT_STARTED",
    "APPLYING",
    "APPLIED",
    "VERIFYING",
    "VERIFIED",
    "COMPENSATING",
    "COMPENSATED",
    "FAILED",
)
PREPARE_JOURNAL_STATES = ("NOT_STARTED", "PREPARING") + JOURNAL_STATES[1:]
NON_TERMINAL_JOURNAL_STATES = (
    "NOT_STARTED",
    "PREPARING",
    "APPLYING",
    "APPLIED",
    "VERIFYING",
    "COMPENSATING",
)
TERMINAL_JOURNAL_STATES = ("VERIFIED", "COMPENSATED", "FAILED")

# ── typed 狀態(§10.2;無別名把其一變成 success)────────────────────────────────
JOURNAL_STATUS_COMMITTED = "JOURNAL_COMMITTED"
JOURNAL_STATUS_LOADED = "JOURNAL_LOADED"
JOURNAL_STATUS_ABSENT = "JOURNAL_ABSENT"
JOURNAL_STATUS_CORRUPT = "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
JOURNAL_STATUS_PRECHECK_FAILED = "PRECHECK_FAILED"
JOURNAL_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
JOURNAL_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
# 崩潰殘留的暫存檔讓 ``openat(O_EXCL)`` 回 EEXIST:那是**主機殘留**,不是 journal 內容壞掉,
# 也不是「別人拿著 lock」——給它自己的 typed 狀態,reason 帶絕對路徑與 operator 的補救動作。
JOURNAL_STATUS_TEMP_COLLISION = "JOURNAL_TEMP_RESIDUE_RECOVERY_REQUIRED"
JOURNAL_TYPED_STATUSES = (
    JOURNAL_STATUS_ABSENT,
    JOURNAL_STATUS_COMMITTED,
    JOURNAL_STATUS_CORRUPT,
    JOURNAL_STATUS_LOADED,
    JOURNAL_STATUS_PENDING,
    JOURNAL_STATUS_PRECHECK_FAILED,
    JOURNAL_STATUS_RECOVERY_REQUIRED,
    JOURNAL_STATUS_TEMP_COLLISION,
)
# §5.2 reconcile 的四分收斂。
RECONCILE_RESUME_VERIFICATION = "RESUME_VERIFICATION"
RECONCILE_STEP_NOT_APPLIED = "STEP_NOT_APPLIED_RESUME"
RECONCILE_COMPENSATE_REVERSE = "COMPENSATE_REVERSE_ORDER"
RECONCILE_RECOVERY_REQUIRED = JOURNAL_STATUS_RECOVERY_REQUIRED
RECONCILE_TERMINAL_NOTHING_TO_DO = "TERMINAL_NOTHING_TO_RECONCILE"
# write-ahead transaction 的三個 crash 注入窗(§5.2 最後一段 / §10.5 #7)。
WAL_FAULT_WINDOWS = (
    "pre_effect",
    "post_effect_pre_observation",
    "post_observation_pre_applied_fsync",
)
# ── entry 的 producer 判別欄(重啟的 runner 必須分得出某筆 entry 的 digest 空間)────
# APPLY 的共用 WAL 上,每個 row 六筆 entry 中有三筆由**該 row 的 driver** 以自己的 subject
# digest 空間寫入,另三筆由 aggregate 以 row-observation digest 空間寫入。少了判別欄,
# reconcile 只能拿 caller 的一個 digest 去比 ``entries[-1]["post_state_digest"]``,卻不知道
# 那是哪個空間——同一個字串在兩個空間裡意義完全不同。
ENTRY_SOURCE_AGGREGATE = "aggregate_transaction"
ENTRY_SOURCE_COMPONENT_ROW = "component_row_driver"
ENTRY_SOURCE_PROBE = "capability_probe"
ENTRY_SOURCE_PREPARE = "prepare_bundle"
ENTRY_SOURCES = (
    ENTRY_SOURCE_AGGREGATE,
    ENTRY_SOURCE_COMPONENT_ROW,
    ENTRY_SOURCE_PREPARE,
    ENTRY_SOURCE_PROBE,
)
# 交易級(而非某一 row 級)的 entry 的判別值。APPLY WAL 上有三種 entry 的 subject **不是**
# 任何一 row:``COMPENSATING`` 與終端的 ``VERIFIED``/``COMPENSATED``/``FAILED``——它們的
# pre/post digest 是 plan 級的 ``pre_state_digest``,涵蓋整筆交易。過去它們只帶一個
# ``step_index``,而 :data:`APPLY_STEP_INDEX_COMPONENT_CLASS` 會把 ``step_index=0`` 推成
# ``HOST_IDENTITY_INSTALL``——於是「五列全數拆除」在 WAL 上被記成「第 0 列」。判別欄是必填的,
# 但滿足它的值必須是**真的**;此常量讓交易級 entry 說出自己的 scope,而不是冒名一列。
ENTRY_SCOPE_AGGREGATE_TRANSACTION = "AGGREGATE_TRANSACTION"
# §5.1 的六個 typed step ↔ 五個 v2 class(step 4 由 LEARNING_RUNTIME 原子併發佈,故不獨立
# 存在)。class 次序取中央 SSOT,index 元組在此釘住(定義見 JournalContractError 之後)。
APPLY_ROW_STEP_INDICES = (0, 1, 2, 3, 5)
_ALL_FALSE_PRODUCTION_FLAGS = {
    "nine_authorities_false": True,
    "production_apply_performed": False,
    "running_attested": False,
}


class JournalContractError(ValueError):
    """journal 契約層硬錯誤(帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


if len(APPLY_ROW_STEP_INDICES) != len(central_validator.S2_4_APPLY_ROW_CLASS_ORDER):
    raise JournalContractError("apply_row_step_index_table_drifted")
APPLY_STEP_INDEX_COMPONENT_CLASS = dict(
    zip(APPLY_ROW_STEP_INDICES, central_validator.S2_4_APPLY_ROW_CLASS_ORDER)
)


class JournalCrash(RuntimeError):
    """注入的 crash(§10.5 #7 fault injection);行程在該窗口「消失」。"""

    def __init__(self, window: str) -> None:
        super().__init__(window)
        self.window = window


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def redact_driver_error(error: BaseException) -> str:
    """只回例外類名(driver 例外文字可能夾帶主機路徑/秘密片段)。"""

    return type(error).__name__


# --------------------------------------------------------------------------- #
# §5.2 路徑導出:id 由各自 core digest 導出,caller 字串永不 join 進 root。
# --------------------------------------------------------------------------- #
def probe_journal_path(probe_id: Any) -> str:
    """``…/probes/<probe_id>.probe.journal.json``(``s2-4-probe-`` + 64 小寫 hex)。"""

    if not isinstance(probe_id, str) or _PROBE_ID_RE.fullmatch(probe_id) is None:
        raise JournalContractError("probe_id_invalid")
    return f"{PROBE_JOURNAL_PARENT}/{probe_id}.probe.journal.json"


def prepare_journal_path(prepare_id: Any) -> str:
    """``…/prepared/<prepare_id>.prepare.journal.json``(``s2-4-prepare-`` + 64 小寫 hex)。"""

    if not isinstance(prepare_id, str) or _PREPARE_ID_RE.fullmatch(prepare_id) is None:
        raise JournalContractError("prepare_id_invalid")
    return f"{PREPARE_JOURNAL_PARENT}/{prepare_id}.prepare.journal.json"


def install_journal_path(plan_id: Any) -> str:
    """``…/s2_4/<plan_id>.journal.json``(``s2-4-`` + 64 小寫 hex)。"""

    if not isinstance(plan_id, str) or _PLAN_ID_RE.fullmatch(plan_id) is None:
        raise JournalContractError("plan_id_invalid")
    return f"{INSTALL_JOURNAL_PARENT}/{plan_id}.journal.json"


_TEMP_TOKEN_RE = re.compile(r"^[0-9a-f]{1,32}-[0-9a-f]{16}$")
# E16:擱淺 WAL 暫存檔的 basename 形狀(``.<basename>.tmp.<pid hex>-<128 bit hex>.<attempt>``)。
# 跨行程唯一的名字讓 ``O_EXCL`` 再也撞不到上一次崩潰的殘留,所以**列舉**是唯一還看得見它的面。
JOURNAL_TEMP_RESIDUE_RE = re.compile(
    r"^\..+\.tmp\.[0-9a-f]{1,32}-[0-9a-f]{16}\.[0-9]+$"
)
_PROCESS_TEMP_TOKEN: str | None = None


def process_temp_token() -> str:
    """本行程的暫存檔前綴(``<pid hex>-<128 bit 隨機>``);同一行程內恆定,跨行程必不同。"""

    global _PROCESS_TEMP_TOKEN
    if _PROCESS_TEMP_TOKEN is None:
        _PROCESS_TEMP_TOKEN = f"{os.getpid():x}-{os.urandom(8).hex()}"
    return _PROCESS_TEMP_TOKEN


def journal_temp_basename(
    basename: str, *, attempt: int = 0, unique_token: str | None = None
) -> str:
    """同檔案系統的暫存名(與正本同 parent,故 rename 恆為 same-filesystem atomic)。

    名字必須**跨行程唯一**。舊形 ``.<basename>.tmp.<attempt>`` 把 ``attempt`` 綁在
    :class:`JournalStore` 實例上,於是每個新行程的第一次落盤永遠瞄準 ``.tmp.0``:一次
    「``create_temp_file`` 之後、``atomic_rename`` 之前」的崩潰——正是 WAL 存在的理由——
    留下的殘留檔,會讓其後**每一個** runner 在已經 durable 消費掉 permit 之後才撞上
    ``openat(O_EXCL)`` 的 EEXIST。``O_EXCL`` 是防競態的原子性手段,不是正確性的錨點;
    唯一性由 ``<pid>-<隨機>`` 提供,``attempt`` 只負責同一行程內的重試。
    """

    if "/" in basename or basename in {"", ".", ".."}:
        raise JournalContractError("journal_basename_invalid")
    token = process_temp_token() if unique_token is None else str(unique_token)
    if _TEMP_TOKEN_RE.fullmatch(token) is None:
        raise JournalContractError("journal_temp_token_invalid")
    return f".{basename}.tmp.{token}.{int(attempt)}"


# --------------------------------------------------------------------------- #
# journal 完整性:canonical inner self-digest + 獨立 outer checksum(§5.2)。
# 次序與 W3 的 probe journal 逐字一致:先 outer(不含 self_digest),再 self(含 outer)。
# --------------------------------------------------------------------------- #
def seal_journal(journal: dict[str, Any]) -> dict[str, Any]:
    """填入 ``outer_checksum`` 與 ``self_digest``(兩道可分辨的完整性面)。"""

    body = {
        key: value
        for key, value in journal.items()
        if key not in {"outer_checksum", "self_digest"}
    }
    sealed = dict(body)
    sealed["outer_checksum"] = canonical_digest(body)
    sealed["self_digest"] = artifact_self_digest(sealed)
    return sealed


def journal_integrity_errors(journal: Any) -> list[str]:
    """重算兩道 digest;任一不符即 malformed(呼叫端轉 typed CORRUPT)。"""

    if not isinstance(journal, dict):
        return ["journal must be an object"]
    errors: list[str] = []
    body = {
        key: value
        for key, value in journal.items()
        if key not in {"outer_checksum", "self_digest"}
    }
    if journal.get("outer_checksum") != canonical_digest(body):
        errors.append("journal outer_checksum does not re-derive the canonical journal body")
    if journal.get("self_digest") != artifact_self_digest(journal):
        errors.append("journal self_digest does not bind the canonical journal")
    return errors


def journal_state_vocabulary(schema_version: Any) -> tuple[str, ...]:
    """該 journal schema 的 exact state 詞彙(PREPARE 多一個 ``PREPARING``)。"""

    if schema_version == "s2_4_prepare_journal_v1":
        return PREPARE_JOURNAL_STATES
    if schema_version in {"s2_4_capability_probe_journal_v1", "s2_4_install_journal_v1"}:
        return JOURNAL_STATES
    raise JournalContractError("journal_schema_version_unknown")


def journal_entry_sequence_errors(journal: Any) -> list[str]:
    """entries 必為 monotonic ``seq`` 自 0 起、state 落在該 schema 的封閉詞彙內、且**每一筆**
    都帶完整的 producer 判別欄(``entry_source`` + ``component_effect_class``)。

    判別欄是**必要**的,不是選配:選配的判別欄等於沒有判別欄——任何一個 producer 只要省略它,
    重啟的 runner 讀到 ``entries[-1]`` 時就又回到猜 digest 空間的狀態,而「猜對」與「猜錯」在
    §5.2 的四分收斂上分別是「續驗」與「對一台部分施作的主機宣稱沒事」。
    """

    if not isinstance(journal, dict):
        return ["journal must be an object"]
    try:
        vocabulary = journal_state_vocabulary(journal.get("schema_version"))
    except JournalContractError as error:
        return [f"journal schema_version is not one of the three §5.2 WALs ({error.code})"]
    entries = journal.get("entries")
    if not isinstance(entries, list) or not entries:
        return ["journal entries must be a non-empty list"]
    errors: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"journal entry[{index}] must be an object")
            continue
        if entry.get("seq") != index:
            errors.append(f"journal entry[{index}] seq is out of order (append-only WAL)")
        if entry.get("state") not in vocabulary:
            errors.append(
                f"journal entry[{index}] state {entry.get('state')!r} is outside the §5.2 "
                "step vocabulary"
            )
        if entry.get("fsynced") is not True:
            errors.append(
                f"journal entry[{index}] is not recorded as fsynced (a WAL entry that was not "
                "fsynced cannot be write-ahead evidence)"
            )
        if entry.get("entry_source") not in ENTRY_SOURCES:
            errors.append(
                f"journal entry[{index}] entry_source {entry.get('entry_source')!r} is not one "
                "of the §5.2 producers; a WAL entry that does not say WHO wrote it cannot be "
                "reconciled against any observed digest"
            )
        effect_class = entry.get("component_effect_class")
        if not isinstance(effect_class, str) or not effect_class:
            errors.append(
                f"journal entry[{index}] carries no component_effect_class; without it a "
                "restarting runner cannot tell WHICH subject digest space entries[-1] lives in "
                "(§5.2)"
            )
    return errors


def journal_terminal_state(journal: Any) -> str | None:
    """最後一筆 entry 的 state(空/畸形回 ``None``)。"""

    if not isinstance(journal, dict):
        return None
    entries = journal.get("entries")
    if not isinstance(entries, list) or not entries or not isinstance(entries[-1], dict):
        return None
    state = entries[-1].get("state")
    return state if isinstance(state, str) else None


# --------------------------------------------------------------------------- #
# 三本 journal 的 builder(schema 為 W1 owned;此處只組出 exact 形狀並封 digest)。
# --------------------------------------------------------------------------- #
def build_probe_journal(
    *,
    probe_id: str,
    derived_unit_name: str,
    scope: str,
    transient_unit_property_digest: str,
    expected_invocation_id_pattern: str,
    cleanup_rollback_digest: str,
    entries: list[dict[str, Any]],
    terminal: bool,
) -> dict[str, Any]:
    """``s2_4_capability_probe_journal_v1``(第一次 D-Bus 呼叫之前先 fsync ``APPLYING``)。"""

    probe_journal_path(probe_id)  # 路徑導出即身分驗證(畸形 id 於此 typed 拒)
    return seal_journal({
        "schema_version": "s2_4_capability_probe_journal_v1",
        "probe_id": probe_id,
        "derived_unit_name": derived_unit_name,
        "scope": scope,
        "transient_unit_property_digest": transient_unit_property_digest,
        "expected_invocation_id_pattern": expected_invocation_id_pattern,
        "cleanup_rollback_digest": cleanup_rollback_digest,
        "entries": [dict(entry) for entry in entries],
        "terminal": bool(terminal),
        "journal_integrity": {
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
    })


def build_prepare_journal(
    *, prepare_id: str, staging_root: str, entries: list[dict[str, Any]], terminal: bool
) -> dict[str, Any]:
    """``s2_4_prepare_journal_v1``(``PREPARING`` 在建立 staging 目錄**之前**即 fsync)。"""

    prepare_journal_path(prepare_id)
    return seal_journal({
        "schema_version": "s2_4_prepare_journal_v1",
        "prepare_id": prepare_id,
        "staging_root": staging_root,
        "entries": [dict(entry) for entry in entries],
        "terminal": bool(terminal),
        "journal_integrity": {
            "preparing_fsynced_before_staging_create": True,
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
    })


def build_install_journal(
    *,
    plan_id: str,
    plan_core_digest: str,
    idempotency_key: str,
    expected_pre_state_digest: str,
    aggregate_rollback_digest: str,
    entries: list[dict[str, Any]],
    terminal: bool,
) -> dict[str, Any]:
    """``s2_4_install_journal_v1``(APPLY 交易;``APPLYING`` 於外部 effect 之前 fsync)。"""

    install_journal_path(plan_id)
    if idempotency_key != plan_id:
        raise JournalContractError("install_journal_idempotency_key_is_not_plan_id")
    return seal_journal({
        "schema_version": "s2_4_install_journal_v1",
        "plan_id": plan_id,
        "plan_core_digest": plan_core_digest,
        "idempotency_key": idempotency_key,
        "expected_pre_state_digest": expected_pre_state_digest,
        "aggregate_rollback_digest": aggregate_rollback_digest,
        "entries": [dict(entry) for entry in entries],
        "terminal": bool(terminal),
        "journal_integrity": {
            "applying_fsynced_before_effect": True,
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
    })


# --------------------------------------------------------------------------- #
# 注入的檔案系統面(真 openat/fsync/rename 屬 W6;source lane 恆 driver=None)。
# --------------------------------------------------------------------------- #
class DurableFileDriver(Protocol):
    """§5.2 的 durable-write 面。**沒有** unlink/truncate/chmod 入口。

    ``open_parent_directory`` 必回 ``{"fd", "device", "inode", "nlink", "mode", "uid",
    "is_dir", "is_symlink"}``;``fstat_parent`` 以同一形狀重讀**同一個 fd**;
    ``create_temp_file`` 回 ``{"fd", "device", "inode", "nlink", "mode", "uid",
    "is_regular_file"}``;``list_journal_basenames`` 是**唯讀**列舉(只回 basename 字串,
    絕不回路徑,更沒有任何刪改面)。任何逸出的例外都會被上層轉成 typed 非成功(絕不半通過)。

    誠實界線:一個已開啟的 dirfd 會釘住 inode,所以「拿同一個 fd 再 ``fstat`` 一次」在真
    POSIX driver 上**永遠**不會偵測到 parent 被置換——那只是重讀同一個 inode。真正的置換
    偵測有兩處:(a) ``openat``/``renameat`` 全部相對於已綁定的 dirfd,所以即使路徑被換掉,
    寫入也仍然落在當初驗過的那個目錄;(b) :meth:`JournalStore._open_parent` 每次呼叫都
    **重新解析路徑**並與首次綁定的 device/inode 比對,以及 rename 之前的一次獨立
    :func:`JournalStore._reresolve_parent_reasons`——那才是有牙齒的檢查。
    """

    def open_parent_directory(
        self, *, path: str, flags: tuple[str, ...]
    ) -> dict[str, Any]: ...

    def fstat_parent(self, *, fd: Any) -> dict[str, Any]: ...

    def list_journal_basenames(self, *, parent_fd: Any) -> list[str]: ...

    def create_temp_file(
        self, *, parent_fd: Any, basename: str, flags: tuple[str, ...], mode: int
    ) -> dict[str, Any]: ...

    def write_bytes(self, *, fd: Any, payload: bytes) -> int: ...

    def fsync_file(self, *, fd: Any) -> None: ...

    def atomic_rename(
        self, *, parent_fd: Any, from_basename: str, to_basename: str
    ) -> None: ...

    def fsync_parent_dir(self, *, fd: Any) -> None: ...

    def read_journal_bytes(self, *, parent_fd: Any, basename: str) -> bytes | None: ...

    def close(self, *, fd: Any) -> None: ...


# journal 面上絕不允許出現的破壞性方法(§5.2:journal 從不被自動改名或覆寫掉)。
FORBIDDEN_JOURNAL_METHODS = (
    "chmod",
    "chown",
    "overwrite_journal",
    "remove",
    "rename_away",
    "rmdir",
    "rotate",
    "truncate",
    "unlink",
)


def assert_no_journal_destructive_surface(driver: Any) -> list[str]:
    """§5.2:driver 上出現任何 unlink/truncate/rotate 面即 typed 拒(絕不自動搬走 journal)。"""

    return [
        f"the injected journal driver exposes {name!r}; a malformed or checksum-invalid "
        "journal is never renamed away or overwritten automatically (§5.2)"
        for name in FORBIDDEN_JOURNAL_METHODS
        if callable(getattr(driver, name, None))
    ]


def _verdict(
    status: str,
    reasons: list[str],
    *,
    journal_path: str,
    journal: dict[str, Any] | None = None,
    mutation_performed: bool = False,
    driver_engaged: bool = False,
    durability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "s2_4_journal_store_verdict_v1_informal",
        "status": status,
        "reasons": list(reasons),
        "journal_path": journal_path,
        "journal": journal,
        "mutation_performed": bool(mutation_performed),
        "driver_engaged": bool(driver_engaged),
        "durability": durability,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
    }


def _parent_precheck_reasons(observed: Any, *, path: str, expected_mode: str) -> list[str]:
    """parent 必為 root-owned、非 symlink 的目錄且 mode 恰為 §5.2 值。"""

    if not isinstance(observed, dict):
        return [f"journal parent {path} directory-FD observation is not an object"]
    reasons: list[str] = []
    if observed.get("is_dir") is not True:
        reasons.append(f"journal parent {path} is not a directory")
    if observed.get("is_symlink") is True:
        reasons.append(f"journal parent {path} is a symlink (O_NOFOLLOW/O_DIRECTORY refuse it)")
    if observed.get("uid") != 0:
        reasons.append(f"journal parent {path} is not root-owned")
    if str(observed.get("mode")) != expected_mode:
        reasons.append(
            f"journal parent {path} mode is {observed.get('mode')!r}, not the required "
            f"{expected_mode}"
        )
    for field in ("device", "inode"):
        if not isinstance(observed.get(field), int):
            reasons.append(f"journal parent {path} {field} is not bound")
    return reasons


class PurePosixLike:
    """極小的 POSIX 路徑拆分(不引 pathlib 語義,避免平台差異)。"""

    def __init__(self, path: str) -> None:
        if not isinstance(path, str) or not path.startswith("/") or path.endswith("/"):
            raise JournalContractError("journal_path_invalid")
        head, _, tail = path.rpartition("/")
        if not tail or tail in {".", ".."} or ".." in path.split("/"):
            raise JournalContractError("journal_path_invalid")
        self.parent = head or "/"
        self.name = tail


class JournalStore:
    """一本 journal 的 durable 落盤/讀回面(§5.2);所有主機動作經注入 driver。"""

    def __init__(
        self,
        driver: Any,
        *,
        journal_path: str,
        parent_mode: str = JOURNAL_PARENT_MODE,
    ) -> None:
        self.driver = driver
        self.journal_path = journal_path
        self.parent_mode = parent_mode
        posix = PurePosixLike(journal_path)
        self.parent_path = posix.parent
        self.basename = posix.name
        # parent 的 device/inode 在第一次開啟時綁定,其後每次落盤都重驗(置換偵測)。
        self.bound_parent: dict[str, Any] | None = None
        self.commits = 0
        # 暫存檔名的計數器必須數**嘗試**次數而非成功次數:``openat(O_EXCL)`` 在前一次失敗留下的
        # 同名暫存檔上會回 EEXIST,於是「失敗一次之後就再也寫不進 journal」——連終端態都落不了盤。
        self.attempts = 0

    # ── 內部:parent FD 開啟 + 綁定/重驗 ────────────────────────────────────────
    def _open_parent(self) -> tuple[Any, list[str]]:
        observed = self.driver.open_parent_directory(
            path=self.parent_path, flags=JOURNAL_PARENT_OPEN_FLAGS
        )
        reasons = _parent_precheck_reasons(
            observed, path=self.parent_path, expected_mode=self.parent_mode
        )
        if reasons:
            return (observed.get("fd") if isinstance(observed, dict) else None, reasons)
        if self.bound_parent is None:
            self.bound_parent = {
                "device": observed["device"],
                "inode": observed["inode"],
                "mode": str(observed["mode"]),
            }
        elif (
            observed["device"] != self.bound_parent["device"]
            or observed["inode"] != self.bound_parent["inode"]
        ):
            reasons.append(
                f"journal parent {self.parent_path} device/inode changed between transitions "
                "(parent replacement); PRECHECK_FAILED with zero mutation"
            )
        return (observed["fd"], reasons)

    def _reresolve_parent_reasons(self) -> list[str]:
        """rename 之前**重新解析** parent 路徑並與綁定值比對(有牙齒的置換偵測)。

        以同一個 dirfd 再 ``fstat`` 一次是套套邏輯:fd 釘住 inode,值必然相同。真正能發現
        「``/var/lib/…/s2_4`` 現在指向別的目錄」的,只有重新走一次路徑解析。此檢查失敗
        並不代表寫入會落錯地方(``renameat`` 仍相對於已驗的 dirfd),而是代表這本 journal
        的**絕對路徑語義**已經不成立——那足以 typed 拒且零變更。
        """

        observed = self.driver.open_parent_directory(
            path=self.parent_path, flags=JOURNAL_PARENT_OPEN_FLAGS
        )
        try:
            reasons = _parent_precheck_reasons(
                observed, path=self.parent_path, expected_mode=self.parent_mode
            )
            if not reasons and (
                observed["device"] != self.bound_parent["device"]
                or observed["inode"] != self.bound_parent["inode"]
            ):
                reasons.append(
                    f"journal parent {self.parent_path} was replaced before the atomic "
                    "rename (the path now resolves to a different directory); PRECHECK_FAILED"
                )
            return reasons
        finally:
            if isinstance(observed, dict) and observed.get("fd") is not None:
                try:
                    self.driver.close(fd=observed["fd"])
                except Exception:  # noqa: BLE001
                    pass

    def list_basenames(self) -> dict[str, Any]:
        """**唯讀**列出 parent 目錄內的 basename(§5.2 啟動巡查用;絕無刪改面)。

        沒有列舉面的 driver 一律 typed 非成功:「我沒辦法知道這個目錄裡還躺著什麼」與
        「這個目錄是乾淨的」是兩件事,後者不得由前者推得。
        """

        if self.driver is None:
            return {
                "status": JOURNAL_STATUS_PENDING,
                "reasons": [
                    "the durable journal enumeration is reachable but authority-locked: no "
                    "host file driver is present; EXTERNAL_VERIFICATION_PENDING"
                ],
                "basenames": [],
            }
        lister = getattr(self.driver, "list_journal_basenames", None)
        if not callable(lister):
            return {
                "status": JOURNAL_STATUS_RECOVERY_REQUIRED,
                "reasons": [
                    f"the injected journal driver cannot enumerate {self.parent_path}; a "
                    "previous plan's stranded transaction would be invisible, so no new work "
                    "is admitted (§5.2)"
                ],
                "basenames": [],
            }
        parent_fd = None
        try:
            parent_fd, reasons = self._open_parent()
            if reasons:
                return {
                    "status": JOURNAL_STATUS_PRECHECK_FAILED,
                    "reasons": reasons,
                    "basenames": [],
                }
            listed = lister(parent_fd=parent_fd)
        except Exception as error:  # noqa: BLE001
            return {
                "status": JOURNAL_STATUS_RECOVERY_REQUIRED,
                "reasons": [
                    f"journal parent {self.parent_path} could not be enumerated: "
                    f"{redact_driver_error(error)}"
                ],
                "basenames": [],
            }
        finally:
            if parent_fd is not None:
                try:
                    self.driver.close(fd=parent_fd)
                except Exception:  # noqa: BLE001
                    pass
        if not isinstance(listed, (list, tuple)) or any(
            not isinstance(name, str) or "/" in name for name in listed
        ):
            return {
                "status": JOURNAL_STATUS_RECOVERY_REQUIRED,
                "reasons": [
                    f"journal parent {self.parent_path} enumeration did not return plain "
                    "basenames"
                ],
                "basenames": [],
            }
        return {
            "status": JOURNAL_STATUS_LOADED, "reasons": [], "basenames": sorted(listed)
        }

    def commit(self, journal: dict[str, Any]) -> dict[str, Any]:
        """把一份已封 digest 的 journal durable 落盤(temp → fsync → rename → parent fsync)。"""

        if self.driver is None:
            return _verdict(
                JOURNAL_STATUS_PENDING,
                [
                    "the durable journal write is reachable but authority-locked: no host "
                    "file driver is present (Mac/source/test lane); "
                    "EXTERNAL_VERIFICATION_PENDING with zero mutation"
                ],
                journal_path=self.journal_path,
            )
        destructive = assert_no_journal_destructive_surface(self.driver)
        if destructive:
            return _verdict(
                JOURNAL_STATUS_PRECHECK_FAILED, destructive, journal_path=self.journal_path
            )
        integrity = journal_integrity_errors(journal) + journal_entry_sequence_errors(journal)
        if integrity:
            return _verdict(
                JOURNAL_STATUS_PRECHECK_FAILED,
                integrity + ["refusing to persist a journal that does not re-derive its digests"],
                journal_path=self.journal_path,
            )
        central_errors = central_validator.validate_aiml_artifact(journal)
        if central_errors:
            return _verdict(
                JOURNAL_STATUS_PRECHECK_FAILED,
                central_errors,
                journal_path=self.journal_path,
            )
        parent_fd = None
        temp_fd = None
        temp_basename = journal_temp_basename(self.basename, attempt=self.attempts)
        self.attempts += 1
        durability = {
            "same_filesystem_atomic_rename": False,
            "file_fsynced": False,
            "parent_dir_fsynced": False,
            "temp_basename": temp_basename,
        }
        try:
            parent_fd, reasons = self._open_parent()
            if reasons:
                return _verdict(
                    JOURNAL_STATUS_PRECHECK_FAILED, reasons, journal_path=self.journal_path,
                    driver_engaged=True, durability=durability,
                )
            try:
                temp = self.driver.create_temp_file(
                    parent_fd=parent_fd,
                    basename=temp_basename,
                    flags=JOURNAL_TEMP_OPEN_FLAGS,
                    mode=JOURNAL_FILE_MODE_BITS,
                )
            except FileExistsError:
                return _verdict(
                    JOURNAL_STATUS_TEMP_COLLISION,
                    [_temp_residue_reason(self.parent_path, temp_basename)],
                    journal_path=self.journal_path, driver_engaged=True, durability=durability,
                )
            temp_reasons = _temp_file_precheck_reasons(
                temp, expected_device=self.bound_parent["device"]
            )
            if temp_reasons:
                return _verdict(
                    JOURNAL_STATUS_PRECHECK_FAILED, temp_reasons,
                    journal_path=self.journal_path, driver_engaged=True, durability=durability,
                )
            temp_fd = temp["fd"]
            durability["same_filesystem_atomic_rename"] = True
            payload = central_validator._canonical_bytes(journal)
            written = self.driver.write_bytes(fd=temp_fd, payload=payload)
            if int(written) != len(payload):
                return _verdict(
                    JOURNAL_STATUS_PRECHECK_FAILED,
                    ["journal temp write was short; refusing to rename a truncated WAL"],
                    journal_path=self.journal_path, driver_engaged=True, durability=durability,
                )
            self.driver.fsync_file(fd=temp_fd)
            durability["file_fsynced"] = True
            # rename 之前重新解析 parent 路徑(見 _reresolve_parent_reasons 的誠實界線)。
            recheck_reasons = self._reresolve_parent_reasons()
            if recheck_reasons:
                return _verdict(
                    JOURNAL_STATUS_PRECHECK_FAILED, recheck_reasons,
                    journal_path=self.journal_path, driver_engaged=True, durability=durability,
                )
            self.driver.atomic_rename(
                parent_fd=parent_fd, from_basename=temp_basename, to_basename=self.basename
            )
            self.driver.fsync_parent_dir(fd=parent_fd)
            durability["parent_dir_fsynced"] = True
        except JournalCrash:
            raise
        except Exception as error:  # noqa: BLE001 - 任何 driver 逸出都 fail-closed
            return _verdict(
                JOURNAL_STATUS_RECOVERY_REQUIRED,
                [f"durable journal write failed: {redact_driver_error(error)}"],
                journal_path=self.journal_path, driver_engaged=True, durability=durability,
            )
        finally:
            for fd in (temp_fd, parent_fd):
                if fd is None:
                    continue
                try:
                    self.driver.close(fd=fd)
                except Exception:  # noqa: BLE001 - close 失敗不改變已 fsync 的事實
                    pass
        self.commits += 1
        return _verdict(
            JOURNAL_STATUS_COMMITTED, [], journal_path=self.journal_path, journal=journal,
            mutation_performed=True, driver_engaged=True, durability=durability,
        )

    def load(self) -> dict[str, Any]:
        """讀回 journal;malformed/truncated/checksum 不符一律 typed CORRUPT(絕不覆寫)。"""

        if self.driver is None:
            return _verdict(
                JOURNAL_STATUS_PENDING,
                [
                    "the durable journal read is reachable but authority-locked: no host file "
                    "driver is present; EXTERNAL_VERIFICATION_PENDING with zero mutation"
                ],
                journal_path=self.journal_path,
            )
        destructive = assert_no_journal_destructive_surface(self.driver)
        if destructive:
            return _verdict(
                JOURNAL_STATUS_PRECHECK_FAILED, destructive, journal_path=self.journal_path
            )
        parent_fd = None
        try:
            parent_fd, reasons = self._open_parent()
            if reasons:
                return _verdict(
                    JOURNAL_STATUS_PRECHECK_FAILED, reasons, journal_path=self.journal_path,
                    driver_engaged=True,
                )
            payload = self.driver.read_journal_bytes(
                parent_fd=parent_fd, basename=self.basename
            )
        except Exception as error:  # noqa: BLE001
            return _verdict(
                JOURNAL_STATUS_CORRUPT,
                [f"journal bytes are unreadable: {redact_driver_error(error)}"],
                journal_path=self.journal_path, driver_engaged=True,
            )
        finally:
            if parent_fd is not None:
                try:
                    self.driver.close(fd=parent_fd)
                except Exception:  # noqa: BLE001
                    pass
        if payload is None:
            return _verdict(
                JOURNAL_STATUS_ABSENT, [], journal_path=self.journal_path, driver_engaged=True
            )
        verdict = verify_journal_bytes(payload, journal_path=self.journal_path)
        verdict["driver_engaged"] = True
        return verdict


def _temp_residue_reason(parent_path: str, temp_basename: str) -> str:
    """EEXIST 的 reason:帶**絕對路徑**與 operator 的補救動作(§5.2 不給任何 unlink 面)。"""

    return (
        f"the write-ahead temp file {parent_path}/{temp_basename} already exists "
        "(openat O_EXCL returned EEXIST). The journal surface deliberately exposes no "
        "unlink/truncate entry point (§5.2), so this residue of an interrupted write is "
        "never removed automatically: an operator must inspect and remove exactly "
        f"{parent_path}/{temp_basename} as root before this transaction can proceed. "
        "The journal itself was neither renamed away nor overwritten."
    )


def _temp_file_precheck_reasons(observed: Any, *, expected_device: Any) -> list[str]:
    """暫存檔必為同裝置、root-owned、mode 0600、link count 1 的一般檔。"""

    if not isinstance(observed, dict):
        return ["journal temp-file creation did not return an observation object"]
    reasons: list[str] = []
    if observed.get("is_regular_file") is not True:
        reasons.append("journal temp file is not a regular file")
    if observed.get("uid") != 0:
        reasons.append("journal temp file is not root-owned")
    if str(observed.get("mode")) != JOURNAL_FILE_MODE:
        reasons.append(
            f"journal temp file mode is {observed.get('mode')!r}, not the required "
            f"{JOURNAL_FILE_MODE}"
        )
    if observed.get("nlink") != 1:
        reasons.append(
            "journal temp file link count is not one (a hardlinked WAL is PRECHECK_FAILED)"
        )
    if observed.get("device") != expected_device:
        reasons.append(
            "journal temp file is on a different device than its parent directory "
            "(cross-device staging can never be an atomic rename); PRECHECK_FAILED"
        )
    return reasons


def verify_journal_bytes(payload: Any, *, journal_path: str) -> dict[str, Any]:
    """把持久化的 bytes 驗回一份 journal;任何畸形/截斷/checksum 不符即 typed CORRUPT。"""

    import json

    if not isinstance(payload, (bytes, bytearray)):
        return _verdict(
            JOURNAL_STATUS_CORRUPT,
            ["journal payload is not bytes"],
            journal_path=journal_path,
        )
    try:
        journal = json.loads(bytes(payload).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return _verdict(
            JOURNAL_STATUS_CORRUPT,
            [
                "journal bytes are malformed or truncated "
                f"({type(error).__name__}); JOURNAL_CORRUPT_RECOVERY_REQUIRED — the file is "
                "never renamed away or overwritten automatically (§5.2)"
            ],
            journal_path=journal_path,
        )
    reasons = journal_integrity_errors(journal) + journal_entry_sequence_errors(journal)
    if isinstance(journal, dict):
        reasons.extend(central_validator.validate_aiml_artifact(journal))
    if reasons:
        return _verdict(
            JOURNAL_STATUS_CORRUPT,
            reasons + [
                "JOURNAL_CORRUPT_RECOVERY_REQUIRED — no automatic rename, overwrite or "
                "repair is performed"
            ],
            journal_path=journal_path,
            journal=None,
        )
    return _verdict(
        JOURNAL_STATUS_LOADED, [], journal_path=journal_path, journal=journal
    )


# --------------------------------------------------------------------------- #
# §5.2 write-ahead transaction:APPLYING(fsync)→ effect → 獨立再觀測 → APPLIED(fsync)。
# --------------------------------------------------------------------------- #
class WriteAheadTransaction:
    """一本 journal 上的 write-ahead 步驟執行器(WAL,不是事後日誌)。

    每一步固定次序,且**每一次** state 轉移都先 durable 落盤才進下一段:

      1. append ``APPLYING``(exact operation id + 期望 pre/post state)並 fsync;
      2. 執行一個 typed effect;
      3. **獨立**再觀測 subject(observe 回 digest);
      4. append ``APPLIED``(觀測到的 digest)並 fsync,然後進 ``VERIFYING``。

    ``fault`` 於三個窗被呼叫(:data:`WAL_FAULT_WINDOWS`);它若 raise
    :class:`JournalCrash`,本步即在該窗「消失」——已 fsync 的 journal 保留,未 fsync 的
    不存在,正是 §10.5 #7 要證的東西。
    """

    def __init__(
        self,
        store: JournalStore,
        *,
        build_journal: Callable[[list[dict[str, Any]], bool], dict[str, Any]],
        clock: Callable[[], datetime],
    ) -> None:
        self.store = store
        self.build_journal = build_journal
        self.clock = clock
        self.entries: list[dict[str, Any]] = []
        self.committed_entries: list[dict[str, Any]] = []
        self.operations: list[dict[str, Any]] = []

    def _append_and_commit(
        self,
        *,
        state: str,
        pre: str,
        post: str,
        step_index: int | None,
        terminal: bool = False,
        entry_source: str = ENTRY_SOURCE_AGGREGATE,
        component_effect_class: Any = None,
    ) -> dict[str, Any]:
        if entry_source not in ENTRY_SOURCES:
            raise JournalContractError("journal_entry_source_unknown")
        entry: dict[str, Any] = {
            "seq": len(self.entries),
            "state": state,
            "pre_state_digest": pre,
            "post_state_digest": post,
            "fsynced": True,
            "recorded_at": _iso(self.clock()),
            # §5.2 的 digest 空間判別:這一筆是誰寫的、寫的是哪一 row 的 subject。
            "entry_source": entry_source,
        }
        if step_index is not None:
            entry["step_index"] = int(step_index)
        mapped_class = (
            APPLY_STEP_INDEX_COMPONENT_CLASS.get(int(step_index))
            if step_index is not None
            else None
        )
        resolved_class = component_effect_class
        if resolved_class is None:
            resolved_class = mapped_class
        elif str(resolved_class) == ENTRY_SCOPE_AGGREGATE_TRANSACTION:
            # 交易級 scope:subject 是整筆交易的 plan 級前態,不屬於任何一 row 的 digest 空間,
            # 所以不與 step_index 推出的 class 比對(它本來就不冒充那一列)。只有 aggregate
            # producer 能宣告它——row driver 借用這個 scope 會把自己的 subject 講成交易級。
            if entry_source != ENTRY_SOURCE_AGGREGATE:
                raise JournalContractError(
                    "journal_entry_aggregate_scope_requires_the_aggregate_producer"
                )
        elif mapped_class is not None and str(resolved_class) != mapped_class:
            # producer 自報的 row 與 step_index 表推出的 row 不一致 = digest 空間衝突。兩個
            # 都寫下去只會讓收斂端二選一,故此處 typed 硬拒(絕不落盤一筆自相矛盾的判別)。
            raise JournalContractError("journal_entry_component_effect_class_conflicts_step")
        if resolved_class is None:
            # 判別欄是必填的:寫不出「哪一 row 的 subject 空間」就不該有這筆 WAL entry。
            raise JournalContractError("journal_entry_component_effect_class_required")
        entry["component_effect_class"] = str(resolved_class)
        candidate = self.entries + [entry]
        journal = self.build_journal(candidate, terminal)
        verdict = self.store.commit(journal)
        if verdict["status"] != JOURNAL_STATUS_COMMITTED:
            return verdict
        self.entries = candidate
        self.committed_entries = [dict(item) for item in candidate]
        return verdict

    def record(
        self,
        *,
        state: str,
        pre_state_digest: str,
        post_state_digest: str,
        step_index: int | None = None,
        terminal: bool = False,
        entry_source: str = ENTRY_SOURCE_AGGREGATE,
        component_effect_class: Any = None,
    ) -> dict[str, Any]:
        """durable 記一次 state 轉移(補償/終端態走此路;失敗即 typed 非成功)。"""

        return self._append_and_commit(
            state=state, pre=pre_state_digest, post=post_state_digest,
            step_index=step_index, terminal=terminal, entry_source=entry_source,
            component_effect_class=component_effect_class,
        )

    def step(
        self,
        *,
        operation_id: str,
        pre_state_digest: str,
        expected_post_state_digest: str,
        effect: Callable[[], Any],
        observe: Callable[[], str],
        step_index: int | None = None,
        fault: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """跑一個 write-ahead 步驟;回 ``{"status", "reasons", "observed_post_state_digest", …}``。"""

        outcome: dict[str, Any] = {
            "schema_version": "s2_4_wal_step_outcome_v1_informal",
            "status": JOURNAL_STATUS_RECOVERY_REQUIRED,
            "reasons": [],
            "operation_id": operation_id,
            "step_index": step_index,
            "expected_post_state_digest": expected_post_state_digest,
            "observed_post_state_digest": None,
            "effect_executed": False,
            "observed": False,
            "applied_fsynced": False,
            "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        }
        self.operations.append({
            "operation_id": operation_id,
            "step_index": step_index,
            "pre_state_digest": pre_state_digest,
            "expected_post_state_digest": expected_post_state_digest,
        })
        # (1) APPLYING 先落盤(外部 effect 之前)。
        applying = self._append_and_commit(
            state="APPLYING", pre=pre_state_digest, post=expected_post_state_digest,
            step_index=step_index,
        )
        if applying["status"] != JOURNAL_STATUS_COMMITTED:
            outcome["reasons"] = applying["reasons"] + [
                "the APPLYING record could not be fsynced, so the external effect was never "
                "attempted (write-ahead ordering, §5.2)"
            ]
            outcome["status"] = applying["status"]
            return outcome
        # crash 窗 1:APPLYING 已 fsync,effect 尚未發生。
        if fault is not None:
            fault("pre_effect")
        # (2) 一個 typed effect。
        try:
            effect()
        except JournalCrash:
            raise
        except Exception as error:  # noqa: BLE001
            outcome["reasons"] = [
                f"typed effect {operation_id} failed: {redact_driver_error(error)}"
            ]
            return outcome
        outcome["effect_executed"] = True
        # crash 窗 2:effect 已發生,尚未再觀測。
        if fault is not None:
            fault("post_effect_pre_observation")
        # (3) 獨立再觀測。
        try:
            observed = observe()
        except JournalCrash:
            raise
        except Exception as error:  # noqa: BLE001
            outcome["reasons"] = [
                f"independent re-observation of {operation_id} failed: "
                f"{redact_driver_error(error)}"
            ]
            return outcome
        if not isinstance(observed, str) or _DIGEST_RE.fullmatch(observed) is None:
            outcome["reasons"] = [
                f"independent re-observation of {operation_id} did not return a sha256 digest"
            ]
            return outcome
        outcome["observed"] = True
        outcome["observed_post_state_digest"] = observed
        # crash 窗 3:已再觀測,APPLIED 尚未 fsync。
        if fault is not None:
            fault("post_observation_pre_applied_fsync")
        # (4) APPLIED 帶「觀測到的」digest 落盤,再進 VERIFYING。
        applied = self._append_and_commit(
            state="APPLIED", pre=pre_state_digest, post=observed, step_index=step_index
        )
        if applied["status"] != JOURNAL_STATUS_COMMITTED:
            outcome["reasons"] = applied["reasons"] + [
                "the effect executed and was observed, but APPLIED could not be fsynced; "
                "reconcile from observed state (never blind replay)"
            ]
            outcome["status"] = applied["status"]
            return outcome
        outcome["applied_fsynced"] = True
        if observed != expected_post_state_digest:
            outcome["reasons"] = [
                f"observed post-state for {operation_id} does not equal the planned post-state; "
                "the journal records the OBSERVED digest and the step is not verified"
            ]
            return outcome
        verifying = self._append_and_commit(
            state="VERIFYING", pre=observed, post=observed, step_index=step_index
        )
        if verifying["status"] != JOURNAL_STATUS_COMMITTED:
            outcome["reasons"] = verifying["reasons"]
            outcome["status"] = verifying["status"]
            return outcome
        outcome["status"] = JOURNAL_STATUS_COMMITTED
        return outcome


def reconcile_journal(
    journal: Any,
    *,
    observed_state_digest: Any,
    task_owned_partial: bool = False,
    ownership_evidence: Any = None,
) -> dict[str, Any]:
    """§5.2 啟動時的確定性收斂;``RECOVERY_REQUIRED`` 一律零變更。

    收斂規則(逐條對應 §5.2 的四項):

      * 觀測 == 該步計畫的 post-state → :data:`RECONCILE_RESUME_VERIFICATION`;
      * 觀測 == pre-state → :data:`RECONCILE_STEP_NOT_APPLIED`(標記未施作並安全續行);
      * task-owned 部分態(caller 以 ``task_owned_partial=True`` + ownership 證據宣告)→
        :data:`RECONCILE_COMPENSATE_REVERSE`;
      * 擁有權或狀態不明 → :data:`RECONCILE_RECOVERY_REQUIRED`,零變更。

    另有兩個先決:journal 本身必須完整(digest/序列)——畸形即
    ``JOURNAL_CORRUPT_RECOVERY_REQUIRED``;已終端的 journal 無需收斂。
    """

    verdict: dict[str, Any] = {
        "schema_version": "s2_4_journal_reconcile_verdict_v1_informal",
        "status": RECONCILE_RECOVERY_REQUIRED,
        "reasons": [],
        "terminal_state": None,
        "terminal_entry_source": None,
        "terminal_component_effect_class": None,
        "mutation_performed": False,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
    }
    integrity = journal_integrity_errors(journal) + journal_entry_sequence_errors(journal)
    if integrity:
        verdict["status"] = JOURNAL_STATUS_CORRUPT
        verdict["reasons"] = integrity + [
            "a malformed journal returns JOURNAL_CORRUPT_RECOVERY_REQUIRED without starting "
            "any new work (§5.2)"
        ]
        return verdict
    state = journal_terminal_state(journal)
    verdict["terminal_state"] = state
    entries = journal["entries"]
    last = entries[-1]
    # §5.2 的 digest 空間判別(A9):最後一筆是誰寫的、寫的是哪一 row 的 subject。呼叫端拿
    # 來比對的 observed digest 必須屬於同一個空間,否則「相等」只是巧合。
    verdict["terminal_entry_source"] = last.get("entry_source")
    verdict["terminal_component_effect_class"] = last.get("component_effect_class")
    # 「無需收斂」必須**兩者**成立:journal 自己宣告 terminal,且最後一筆 state 亦為終端態。
    # 只看最後一筆 state 會 fail-open:APPLY 的共用 WAL 上,某個 row 內部的 ``VERIFIED``
    # (那是**該 row** 的終端,不是**交易**的終端)恰好落在最後一筆時,一筆未完成的交易會被
    # 誤判為「沒事」,於是一個新 plan 被放行,而主機上還躺著部分施作的狀態。
    if state in TERMINAL_JOURNAL_STATES and journal.get("terminal") is True:
        # ``FAILED`` 與 ``COMPENSATED`` 都是終端,但只有後者代表殘留已消失。§5.4 的
        # ``FAILED`` 恰好寫在「補償無法被證明為 exact」時——它記的是**確切殘留**並封鎖
        # S2.5。把它讀成「沒事要收斂」正是 row-level VERIFIED 那個 fail-open 的同一族。
        if state == "FAILED":
            verdict["status"] = RECONCILE_RECOVERY_REQUIRED
            verdict["reasons"] = [
                "the journal is terminal in state FAILED: compensation could not be proved "
                "exact, so the exact residual it records is still on the host (§5.4). "
                "RECOVERY_REQUIRED with zero mutation; no new probe, prepare intent or plan "
                "is admitted until an independent residue postcheck clears it"
            ]
            return verdict
        verdict["status"] = RECONCILE_TERMINAL_NOTHING_TO_DO
        return verdict
    if not isinstance(observed_state_digest, str) or (
        _DIGEST_RE.fullmatch(observed_state_digest) is None
    ):
        verdict["reasons"] = [
            "reconcile requires an independently observed state digest; ownership/state is "
            "ambiguous without it and no new mutation is performed"
        ]
        return verdict
    if observed_state_digest == last.get("post_state_digest"):
        verdict["status"] = RECONCILE_RESUME_VERIFICATION
        verdict["reasons"] = [
            "observed state equals the planned post-state of the interrupted step; resume "
            "verification (never blind replay)"
        ]
        return verdict
    if observed_state_digest == last.get("pre_state_digest"):
        verdict["status"] = RECONCILE_STEP_NOT_APPLIED
        verdict["reasons"] = [
            "observed state equals the pre-state; the interrupted step is marked not applied "
            "and execution resumes safely"
        ]
        return verdict
    if task_owned_partial:
        import agent_governance_s2_4_component as _component

        ownership_reasons = _component.ownership_evidence_reasons(ownership_evidence)
        # §5.3/§5.4:授權「破壞性的逆序補償」不能只看兩個字串長得像 digest。``journal_digest``
        # 必須**就是**剛剛讀回並完整性驗過的那本 journal 的 ``self_digest``——它就在手上,
        # 沒有任何理由不比對。不比對的話,兩個 ``sha256:000…0`` 就能把零變更的
        # RECOVERY_REQUIRED 換成一次被授權的破壞性補償。
        binding_reasons = _component.ownership_binding_reasons(
            (ownership_evidence or {}).get("journal_subject"),
            subject="journal_subject",
            expected_journal_digest=journal.get("self_digest"),
        )
        if ownership_reasons or binding_reasons:
            verdict["reasons"] = (ownership_reasons or []) + binding_reasons + [
                "a partial state was declared task-owned but no valid task-owned journal "
                "ownership binding was supplied; RECOVERY_REQUIRED with no mutation (§5.3)"
            ]
            return verdict
        verdict["status"] = RECONCILE_COMPENSATE_REVERSE
        verdict["reasons"] = [
            "observed state is a task-owned partial state with a valid journal; compensate in "
            "reverse order"
        ]
        return verdict
    verdict["reasons"] = [
        "observed state matches neither the pre-state nor the planned post-state and is not a "
        "proven task-owned partial state; RECOVERY_REQUIRED and no new mutation (§5.2)"
    ]
    return verdict


def journal_abi_projection() -> dict[str, Any]:
    """W4 exported-ABI 折入的 journal 面(路徑導出/state 詞彙/durability 契約)。"""

    sample = "0" * 64
    return {
        "install_state_root": INSTALL_STATE_ROOT,
        "probe_journal_path": probe_journal_path(PROBE_ID_PREFIX + sample),
        "prepare_journal_path": prepare_journal_path(PREPARE_ID_PREFIX + sample),
        "install_journal_path": install_journal_path(PLAN_ID_PREFIX + sample),
        "journal_states": list(JOURNAL_STATES),
        "prepare_journal_states": list(PREPARE_JOURNAL_STATES),
        "terminal_journal_states": list(TERMINAL_JOURNAL_STATES),
        "terminal_states_admitting_new_work": [
            state for state in TERMINAL_JOURNAL_STATES if state != "FAILED"
        ],
        "entry_sources": list(ENTRY_SOURCES),
        "apply_step_index_component_class": {
            str(index): name
            for index, name in sorted(APPLY_STEP_INDEX_COMPONENT_CLASS.items())
        },
        "wal_fault_windows": list(WAL_FAULT_WINDOWS),
        "parent_open_flags": list(JOURNAL_PARENT_OPEN_FLAGS),
        "temp_open_flags": list(JOURNAL_TEMP_OPEN_FLAGS),
        "journal_parent_mode": JOURNAL_PARENT_MODE,
        "journal_file_mode": JOURNAL_FILE_MODE,
        "forbidden_journal_methods": list(FORBIDDEN_JOURNAL_METHODS),
        "typed_statuses": list(JOURNAL_TYPED_STATUSES),
        "reconcile_outcomes": [
            RECONCILE_RESUME_VERIFICATION,
            RECONCILE_STEP_NOT_APPLIED,
            RECONCILE_COMPENSATE_REVERSE,
            RECONCILE_RECOVERY_REQUIRED,
            RECONCILE_TERMINAL_NOTHING_TO_DO,
        ],
    }

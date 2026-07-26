#!/usr/bin/env python3
"""S2.4(WP4·W4b)§5.2 啟動 reconcile + runner 的 WAL/lock 接線葉。

依 §10.1.1(2026-07-26 PM path-scope amendment)的 standing rule 自
:mod:`agent_governance_s2_4_install_driver` 拆出(該檔為 §10.1 明列 owned path,拆分只為把它
維持在 repo 的 2000 行門檻內);每一個名字都由父模組**逐名 re-export**,消費者的匯入面不變,
且不新增任何 capability——本葉沒有任何新的 effect / authority / network / credential 面。

兩件事在此:

1. :func:`reconcile_startup_journals` ——§5.2 的「接受新 probe / prepare intent / plan **之前**
   先收斂任何非終端 journal」。四個收斂逐條對應設計:觀測 == 該步計畫的 post-state → 續驗;
   觀測 == pre-state → 標記未施作並安全續行;task-owned 部分態(帶合法 journal ownership 綁定)
   → 逆序補償;擁有權/狀態不明 → ``RECOVERY_REQUIRED`` 且**零新變更**。畸形/截斷/checksum
   不符一律 ``JOURNAL_CORRUPT_RECOVERY_REQUIRED``,且絕不被自動改名或覆寫。
2. :class:`JournalRoutedDriver` ——W4a 記錄的 ``RUNNER_WAL_LOCK_WIRING``:把既有 probe /
   PREPARE / APPLY driver 的 ``journal_transition`` 呼叫**路由**進 W4a 的
   :class:`agent_governance_s2_4_journal.JournalStore`,並要求同一把已取得的 install lock。
   它**只**改 journalling 與 locking 走哪裡,不改那些 driver 對主機做什麼。

九 authority / production_apply_performed / running_attested 恆 false;``driver=None`` 一律
typed ``EXTERNAL_VERIFICATION_PENDING`` 且零變更。
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import agent_governance_s2_4_component as _component  # noqa: E402
import agent_governance_s2_4_journal as _journal  # noqa: E402
import agent_governance_s2_4_lock as _lock  # noqa: E402

_ALL_FALSE_PRODUCTION_FLAGS = dict(_component._ALL_FALSE_PRODUCTION_FLAGS)

# ── typed 狀態(§10.2;無別名把其一變成 success)────────────────────────────────
RECONCILE_STATUS_CLEAN = "STARTUP_RECONCILE_CLEAN"
RECONCILE_STATUS_RESUME = "STARTUP_RECONCILE_RESUME_VERIFICATION"
RECONCILE_STATUS_NOT_APPLIED = "STARTUP_RECONCILE_STEP_NOT_APPLIED"
RECONCILE_STATUS_COMPENSATE = "STARTUP_RECONCILE_COMPENSATE_REVERSE_ORDER"
RECONCILE_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
RECONCILE_STATUS_CORRUPT = _journal.JOURNAL_STATUS_CORRUPT
RECONCILE_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
RECONCILE_STATUS_LOCK_REQUIRED = _lock.REPLAY_STATUS_LOCK_REQUIRED
RECONCILE_TYPED_STATUSES = (
    RECONCILE_STATUS_CLEAN,
    RECONCILE_STATUS_COMPENSATE,
    RECONCILE_STATUS_CORRUPT,
    RECONCILE_STATUS_LOCK_REQUIRED,
    RECONCILE_STATUS_NOT_APPLIED,
    RECONCILE_STATUS_PENDING,
    RECONCILE_STATUS_RECOVERY_REQUIRED,
    RECONCILE_STATUS_RESUME,
)
# §5.2 的四個收斂 → 啟動 reconcile 的 typed 投影。
_RECONCILE_PROJECTION = {
    _journal.RECONCILE_RESUME_VERIFICATION: RECONCILE_STATUS_RESUME,
    _journal.RECONCILE_STEP_NOT_APPLIED: RECONCILE_STATUS_NOT_APPLIED,
    _journal.RECONCILE_COMPENSATE_REVERSE: RECONCILE_STATUS_COMPENSATE,
    _journal.RECONCILE_RECOVERY_REQUIRED: RECONCILE_STATUS_RECOVERY_REQUIRED,
    _journal.RECONCILE_TERMINAL_NOTHING_TO_DO: RECONCILE_STATUS_CLEAN,
    _journal.JOURNAL_STATUS_CORRUPT: RECONCILE_STATUS_CORRUPT,
}
# 「接受新工作」只有兩種收斂:沒有需要收斂的東西,或該步被標記為未施作而可安全續行。
RECONCILE_ADMITS_NEW_WORK = (RECONCILE_STATUS_CLEAN, RECONCILE_STATUS_NOT_APPLIED)
# reconcile 一律不允許新工作的收斂(次序 = 回報時的嚴格度優先序)。
_RECONCILE_BLOCKING_ORDER = (
    RECONCILE_STATUS_CORRUPT,
    RECONCILE_STATUS_RECOVERY_REQUIRED,
    RECONCILE_STATUS_COMPENSATE,
    RECONCILE_STATUS_RESUME,
)
# §5.2 巡查的三個 lane(APPLY 恆在;probe/PREPARE 由 caller 顯式遞交導出過的路徑)。
RECONCILE_LANES = ("install", "prepare", "probe")


class InstallDriverContractError(ValueError):
    """aggregate 交易家族的 typed 契約層硬錯誤(父模組 re-export 同一個類別物件)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def startup_journal_paths(plan_id: str, extra: Any = None) -> dict[str, str]:
    """§5.2 啟動 reconcile 要巡的 lane:APPLY 恆在;probe/PREPARE lane 由 caller 顯式給路徑。

    probe/prepare 的 journal 路徑由各自的 ``probe_id`` / ``prepare_id`` 導出,而那兩個 id 不在
    install plan 內(plan 只綁 receipt digest),故 aggregate 無法憑 plan 猜出它們;W6 runner
    以 ``startup_journal_paths={"probe": …, "prepare": …}`` 顯式遞交(路徑仍由
    :mod:`agent_governance_s2_4_journal` 的導出函式產生,caller 字串永不 join 進 root)。
    """

    paths = {"install": _journal.install_journal_path(plan_id)}
    if isinstance(extra, dict):
        for lane in RECONCILE_LANES:
            value = extra.get(lane)
            if lane != "install" and isinstance(value, str) and value:
                paths[lane] = value
    return paths


def reconcile_startup_journals(
    driver: Any = None,
    *,
    journal_paths: Any = None,
    observed_state_digests: Any = None,
    task_owned_partials: Any = None,
    ownership_evidence: Any = None,
    lock_verdict: Any = None,
) -> dict[str, Any]:
    """§5.2:收斂**任何**非終端的 probe / PREPARE / APPLY journal,然後才接受新工作。

    ``journal_paths`` 是 ``{"probe"|"prepare"|"install": path}``(缺席的 lane 不檢查);
    ``observed_state_digests`` 是各 lane **獨立觀測**到的當下狀態 digest。任一 lane 不允許新
    工作,整體即不允許(``admits_new_work=False``)。收斂本身**零變更**:它只讀 journal 與
    caller 遞交的獨立觀測,補償/續驗由呼叫端在收到 typed 收斂後自行執行。
    """

    outcome: dict[str, Any] = {
        "schema_version": "s2_4_startup_reconcile_verdict_v1_informal",
        "status": RECONCILE_STATUS_RECOVERY_REQUIRED,
        "reasons": [],
        "lanes": {},
        "admits_new_work": False,
        "mutation_performed": False,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
    }
    paths = journal_paths if isinstance(journal_paths, dict) else {}
    if not paths:
        outcome["reasons"] = [
            "startup reconciliation requires the exact §5.2 journal paths it must inspect "
            "(fail-closed: an unchecked lane could strand a non-terminal journal)"
        ]
        return outcome
    if not isinstance(lock_verdict, dict) or lock_verdict.get("status") != (
        _lock.LOCK_STATUS_ACQUIRED
    ):
        outcome["status"] = RECONCILE_STATUS_LOCK_REQUIRED
        outcome["reasons"] = [
            "a restarted runner inspects and reconciles journals only while HOLDING the "
            "exclusive install lock (§5.2)"
        ]
        return outcome
    if driver is None:
        outcome["status"] = RECONCILE_STATUS_PENDING
        outcome["reasons"] = [
            "startup reconciliation is reachable but authority-locked: no host file driver is "
            "present (Mac/source/test lane); EXTERNAL_VERIFICATION_PENDING with zero mutation"
        ]
        return outcome
    observed = observed_state_digests if isinstance(observed_state_digests, dict) else {}
    partials = task_owned_partials if isinstance(task_owned_partials, dict) else {}
    statuses: list[str] = []
    for lane in sorted(paths):
        lane_verdict = _reconcile_lane(
            driver, lane=lane, journal_path=paths[lane],
            observed_state_digest=observed.get(lane),
            task_owned_partial=bool(partials.get(lane)),
            ownership_evidence=ownership_evidence,
        )
        outcome["lanes"][lane] = lane_verdict
        statuses.append(lane_verdict["status"])
    for blocking in _RECONCILE_BLOCKING_ORDER:
        if blocking in statuses:
            blocked = sorted(
                lane for lane, value in outcome["lanes"].items()
                if value["status"] == blocking
            )
            outcome["status"] = blocking
            outcome["reasons"] = [
                f"lane(s) {blocked} reconcile to {blocking}; no new probe, prepare intent or "
                "plan is accepted until that is resolved (§5.2)"
            ]
            return outcome
    outcome["status"] = (
        RECONCILE_STATUS_NOT_APPLIED
        if RECONCILE_STATUS_NOT_APPLIED in statuses
        else RECONCILE_STATUS_CLEAN
    )
    outcome["admits_new_work"] = True
    return outcome


def _reconcile_lane(
    driver: Any,
    *,
    lane: str,
    journal_path: str,
    observed_state_digest: Any,
    task_owned_partial: bool,
    ownership_evidence: Any,
) -> dict[str, Any]:
    """單一 lane 的收斂(讀回 journal → §5.2 四分);讀不回即 typed CORRUPT/RECOVERY。"""

    store = _journal.JournalStore(driver, journal_path=journal_path)
    read = store.load()
    if read["status"] == _journal.JOURNAL_STATUS_ABSENT:
        return {
            "status": RECONCILE_STATUS_CLEAN,
            "reasons": ["no journal exists for this lane; nothing to reconcile"],
            "terminal_state": None,
            "journal_path": journal_path,
        }
    if read["status"] != _journal.JOURNAL_STATUS_LOADED:
        return {
            "status": (
                RECONCILE_STATUS_CORRUPT
                if read["status"] == _journal.JOURNAL_STATUS_CORRUPT
                else RECONCILE_STATUS_RECOVERY_REQUIRED
            ),
            "reasons": list(read["reasons"]),
            "terminal_state": None,
            "journal_path": journal_path,
        }
    reconcile = _journal.reconcile_journal(
        read["journal"], observed_state_digest=observed_state_digest,
        task_owned_partial=task_owned_partial, ownership_evidence=ownership_evidence,
    )
    return {
        "status": _RECONCILE_PROJECTION.get(
            reconcile["status"], RECONCILE_STATUS_RECOVERY_REQUIRED
        ),
        "reasons": list(reconcile["reasons"]),
        "terminal_state": reconcile["terminal_state"],
        "journal_path": journal_path,
    }


class JournalRoutedDriver:
    """把一支 W3/W3b host driver 的 ``journal_transition`` 路由進 durable ``JournalStore``。

    **只**改「journalling 與 locking 走哪裡」,不改該 driver 對主機做什麼:除
    ``journal_transition`` 之外的每一個屬性都原樣委派給被包裹的 driver(``hasattr`` 語義因此
    完整保留,``assert_no_unit_lifecycle_surface`` 之類的硬檢行為不變)。

    契約(W4a 記錄的 ``RUNNER_WAL_LOCK_WIRING``):

      * 沒有**已取得**的 install lock 即拒絕落盤(:class:`InstallDriverContractError`);
      * 每一筆 state 轉移都經 ``JournalStore.commit``(temp → fsync → rename → parent fsync),
        append-only 且 ``seq`` 單調;
      * 落盤失敗即 raise,由呼叫端(row / probe / prepare 進入點的 fail-closed 例外處理)轉成
        typed 非成功——絕不「沒落盤卻繼續」。

    ``transaction`` 在場時(APPLY 的五 row),轉移改由該
    :class:`agent_governance_s2_4_journal.WriteAheadTransaction` 落盤,因此 row 內部的轉移與
    aggregate 的每步轉移共用**同一本** journal 的單調 ``seq``——一筆交易一本 WAL。缺席時
    (probe / PREPARE 有各自的 journal)使用自帶的 store 與 entry 序列。
    """

    def __init__(
        self,
        driver: Any,
        *,
        store: _journal.JournalStore,
        build_journal: Callable[[list[dict[str, Any]], bool], dict[str, Any]],
        lock_verdict: Any,
        clock: Callable[[], datetime],
        step_index: int | None = None,
        transaction: Any = None,
    ) -> None:
        self._driver = driver
        self._store = store
        self._build_journal = build_journal
        self._lock_verdict = lock_verdict
        self._clock = clock
        self._step_index = step_index
        self._transaction = transaction
        self.entries: list[dict[str, Any]] = []
        self.commits: list[dict[str, Any]] = []

    # 被包裹 driver 的一切(包含 evidence_class 自報欄位)原樣可見。
    def __getattr__(self, name: str) -> Any:
        return getattr(self._driver, name)

    @property
    def wrapped_driver(self) -> Any:
        return self._driver

    def journal_transition(self, *, entry: dict[str, Any]) -> None:
        if not isinstance(self._lock_verdict, dict) or self._lock_verdict.get("status") != (
            _lock.LOCK_STATUS_ACQUIRED
        ):
            raise InstallDriverContractError("journal_transition_requires_the_install_lock")
        if self._transaction is not None:
            verdict = self._transaction.record(
                state=entry["state"],
                pre_state_digest=entry["pre_state_digest"],
                post_state_digest=entry["post_state_digest"],
                step_index=self._step_index,
            )
            self.commits.append(verdict)
            if verdict["status"] != _journal.JOURNAL_STATUS_COMMITTED:
                raise InstallDriverContractError(
                    "journal_transition_was_not_durably_committed"
                )
            self.entries = [dict(item) for item in self._transaction.entries]
            return
        routed = dict(entry)
        routed["seq"] = len(self.entries)
        routed["fsynced"] = True
        if self._step_index is not None:
            routed["step_index"] = int(self._step_index)
        routed.setdefault("recorded_at", _iso(self._clock()))
        candidate = self.entries + [routed]
        verdict = self._store.commit(self._build_journal(candidate, False))
        self.commits.append(verdict)
        if verdict["status"] != _journal.JOURNAL_STATUS_COMMITTED:
            raise InstallDriverContractError("journal_transition_was_not_durably_committed")
        self.entries = candidate


def reconcile_abi_projection() -> dict[str, Any]:
    """W4 exported-ABI 折入的 §5.2 啟動 reconcile / WAL 接線面。"""

    return {
        "reconcile_entrypoint": (
            "agent_governance_s2_4_reconcile.reconcile_startup_journals"
        ),
        "journal_routed_driver": "agent_governance_s2_4_reconcile.JournalRoutedDriver",
        "reconcile_lanes": list(RECONCILE_LANES),
        "reconcile_typed_statuses": list(RECONCILE_TYPED_STATUSES),
        "reconcile_admits_new_work": list(RECONCILE_ADMITS_NEW_WORK),
        "reconcile_blocking_order": list(_RECONCILE_BLOCKING_ORDER),
        "reconcile_projection": dict(_RECONCILE_PROJECTION),
    }

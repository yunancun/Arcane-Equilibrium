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

import re
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
# 三個 lane 的 parent 與其 basename 形狀。啟動時**列舉**這三個 parent,因此
# 「caller 沒有指名某條 lane」不再等於「那條 lane 是乾淨的」(A5),而別的 plan 留下的
# 半途交易也一定會被看見(A4)。basename → id → 由 journal 葉的導出函式重算路徑,
# caller 字串永不 join 進 root。
_LANE_PARENTS = {
    "install": (
        _journal.INSTALL_JOURNAL_PARENT,
        re.compile(r"^(s2-4-[0-9a-f]{64})\.journal\.json$"),
        _journal.install_journal_path,
    ),
    "prepare": (
        _journal.PREPARE_JOURNAL_PARENT,
        re.compile(r"^(s2-4-prepare-[0-9a-f]{64})\.prepare\.journal\.json$"),
        _journal.prepare_journal_path,
    ),
    "probe": (
        _journal.PROBE_JOURNAL_PARENT,
        re.compile(r"^(s2-4-probe-[0-9a-f]{64})\.probe\.journal\.json$"),
        _journal.probe_journal_path,
    ),
}


class InstallDriverContractError(ValueError):
    """aggregate 交易家族的 typed 契約層硬錯誤(父模組 re-export 同一個類別物件)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def rederive_lane_path(lane: str, value: Any) -> str:
    """把 caller 給的 lane 值(id 或完整路徑)**重新**經 journal 葉的導出函式算出來。

    舊行為只檢查「是非空字串」,於是 ``/etc/shadow``、``//etc//passwd``、``/\\n/x`` 都會被
    當成合法 lane 路徑收下(讀取仍會卡在 root-owned-0700 前置檢查,所以沒有洩漏,但
    docstring 宣稱的「路徑仍由導出函式產生」在結構上並不成立)。此處讓它成立:抽出
    basename、比對該 lane 的 exact id 形狀、再由導出函式重算;結果必須與 caller 給的值
    逐位元相同(caller 也可以直接給 id)。
    """

    if lane not in _LANE_PARENTS:
        raise InstallDriverContractError("startup_journal_lane_unknown")
    parent, pattern, derive = _LANE_PARENTS[lane]
    if not isinstance(value, str) or not value:
        raise InstallDriverContractError("startup_journal_path_invalid")
    basename = value.rsplit("/", 1)[-1]
    match = pattern.fullmatch(basename)
    if match is None:
        # caller 也可能直接給 id(``s2-4-probe-<64hex>`` 之類)。
        try:
            return derive(value)
        except _journal.JournalContractError as error:
            raise InstallDriverContractError(
                f"startup_journal_path_not_derivable:{error.code}"
            ) from error
    derived = derive(match.group(1))
    if value not in {derived, match.group(1)}:
        raise InstallDriverContractError("startup_journal_path_not_derivable")
    del parent
    return derived


def startup_journal_paths(plan_id: str, extra: Any = None) -> dict[str, str]:
    """§5.2 啟動 reconcile 要巡的 lane:APPLY 恆在;probe/PREPARE lane 由 caller 顯式給。

    probe/prepare 的 journal 路徑由各自的 ``probe_id`` / ``prepare_id`` 導出,而那兩個 id 不在
    install plan 內(plan 只綁 receipt digest),故 aggregate 無法憑 plan 猜出它們;W6 runner
    以 ``startup_journal_paths={"probe": …, "prepare": …}`` 顯式遞交。caller 的值一律經
    :func:`rederive_lane_path` 重算,畸形值即 typed 契約層硬錯(絕不 join 進 root)。

    誠實界線:這裡「指名」的 lane 只決定哪些 journal 會拿到 caller 的獨立觀測 digest;
    **是否巡查**不由指名決定——:func:`reconcile_startup_journals` 會列舉三個 parent。
    """

    paths = {"install": _journal.install_journal_path(plan_id)}
    if isinstance(extra, dict):
        for lane in RECONCILE_LANES:
            # 「缺席」才跳過;**給了**一個空/畸形的值一律 typed 拒(靜默丟掉一條 caller
            # 明確指名的 lane,正是 §5.2 前置被 omission 滿足的那條路)。
            if lane != "install" and lane in extra and extra[lane] is not None:
                paths[lane] = rederive_lane_path(lane, extra[lane])
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

    ``journal_paths`` 是 ``{"probe"|"prepare"|"install": path}``;它只決定哪條 lane 拿得到
    caller 的獨立觀測 digest,**不**決定巡查範圍——三個 §5.2 parent 一律被列舉,任何一本
    沒被指名的非終端 journal(例如**上一個 plan** 半途崩掉留下的那本)都會被看見並讓整體
    ``admits_new_work=False``。``observed_state_digests`` 是各 lane **獨立觀測**到的當下狀態
    digest。收斂本身**零變更**:它只讀 journal 與 caller 遞交的獨立觀測,補償/續驗由呼叫端
    在收到 typed 收斂後自行執行。
    """

    outcome: dict[str, Any] = {
        "schema_version": "s2_4_startup_reconcile_verdict_v1_informal",
        "status": RECONCILE_STATUS_RECOVERY_REQUIRED,
        "reasons": [],
        "lanes": {},
        "enumerated_parents": {},
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
    # §5.2 的閘序:**先** lock,再 driver。重啟的 runner「只在**持有**互斥 install lock 時」
    # 巡查並收斂 journal,所以「有沒有那把 lock」是這個進入點的第一個問題;有沒有 host file
    # driver 是「拿到 lock 之後能不能真的讀到磁碟」的下一個問題。倒過來問會讓
    # ``driver=None ∧ 無 lock`` 回報 EXTERNAL_VERIFICATION_PENDING——那句話讀起來像「只差一個
    # 主機面就成」,實際上連 §5.2 的准入前提都不成立。兩者都 admits_new_work=False 且零變更,
    # 但 typed 非成功要說出**最先**擋住的那一道。
    if not _lock.install_lock_is_held(lock_verdict):
        outcome["status"] = RECONCILE_STATUS_LOCK_REQUIRED
        outcome["reasons"] = _lock._lock_not_held_reasons(
            lock_verdict, action="startup reconciliation"
        ) + [
            "a restarted runner inspects and reconciles journals only while HOLDING the "
            "exclusive install lock (§5.2)"
        ]
        return outcome
    if driver is None:
        # 持有 lock 但沒有 host file driver:連主機都碰不到,零變更是結構性的。
        outcome["status"] = RECONCILE_STATUS_PENDING
        outcome["reasons"] = [
            "startup reconciliation is reachable but authority-locked: no host file driver is "
            "present (Mac/source/test lane); EXTERNAL_VERIFICATION_PENDING with zero mutation"
        ]
        return outcome
    observed = observed_state_digests if isinstance(observed_state_digests, dict) else {}
    partials = task_owned_partials if isinstance(task_owned_partials, dict) else {}
    lane_evidence = _lane_ownership_evidence(ownership_evidence)
    statuses: list[str] = []
    for lane in sorted(paths):
        lane_verdict = _reconcile_lane(
            driver, lane=lane, journal_path=paths[lane],
            observed_state_digest=observed.get(lane),
            task_owned_partial=bool(partials.get(lane)),
            ownership_evidence=lane_evidence.get(lane),
        )
        outcome["lanes"][lane] = lane_verdict
        statuses.append(lane_verdict["status"])
    # ── §5.2 的「**任何**非終端 journal」:列舉三個 parent,不靠 caller 指名 ─────────
    discovered = _enumerate_startup_journals(driver, known=set(paths.values()))
    outcome["enumerated_parents"] = discovered["parents"]
    if discovered["reasons"]:
        outcome["status"] = RECONCILE_STATUS_RECOVERY_REQUIRED
        outcome["reasons"] = discovered["reasons"]
        return outcome
    for lane_key, journal_path in sorted(discovered["paths"].items()):
        lane_verdict = _reconcile_lane(
            driver, lane=lane_key, journal_path=journal_path,
            # 未被指名的 journal 沒有 caller 的獨立觀測,也沒有 per-lane ownership key:
            # 非終端即 RECOVERY_REQUIRED,終端(且非 FAILED)即 CLEAN。
            observed_state_digest=None, task_owned_partial=False, ownership_evidence=None,
        )
        outcome["lanes"][lane_key] = lane_verdict
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


RECONCILE_STATUS_SURFACE_ABSENT = "STARTUP_RECONCILE_SURFACE_ABSENT"


def reconcile_before_new_intent(driver: Any, *, lane: str, lane_path: str) -> dict[str, Any]:
    """§5.2 前置:接受新的 probe / prepare intent **之前**先收斂任何非終端 journal。

    ``driver`` 是該進入點的 host driver。W4/W6 的接線把它包在
    :class:`JournalRoutedDriver` 裡,於是 durable journal 面與已取得的 install lock 都能
    由 :meth:`JournalRoutedDriver.startup_reconcile_surface` 取得,此處即跑真正的收斂。

    誠實界線:沒有該面的 driver(source lane 的 in-memory fake、或任何未經 W4 接線的
    host driver)**根本沒有 durable journal**,所以這裡回
    :data:`RECONCILE_STATUS_SURFACE_ABSENT` 並把 ``admits_new_work`` 記成 ``None`` ——
    「沒能建立」與「乾淨」是兩件事,呼叫端把這個 typed 結果原樣記進 verdict,絕不冒充成
    已收斂。§10.5 #39 的跨崩潰保證由 :func:`reconcile_startup_journals` 對 probe parent
    的列舉提供:一次未解的 recovery 會留下**非終端的 probe journal**,下一次啟動即
    RECOVERY_REQUIRED。
    """

    surface = getattr(driver, "startup_reconcile_surface", None)
    if not callable(surface):
        return {
            "status": RECONCILE_STATUS_SURFACE_ABSENT,
            "admits_new_work": None,
            "reasons": [
                "this driver exposes no durable §5.2 journal surface, so startup "
                "reconciliation could not be established before accepting the new intent; "
                "the W4/W6 runner must inject a journal-routed driver"
            ],
            "lanes": {},
            "mutation_performed": False,
        }
    bound = surface()
    outcome = reconcile_startup_journals(
        (bound or {}).get("file_driver"),
        journal_paths={lane: lane_path},
        lock_verdict=(bound or {}).get("lock_verdict"),
    )
    return outcome


def _lane_ownership_evidence(ownership_evidence: Any) -> dict[str, Any]:
    """把 ``ownership_evidence`` 拆成 **per-lane** 的鑰匙(一把鑰匙不得開三扇門)。

    舊行為把同一個物件同時餵給 install / prepare / probe 三條 lane,於是一組
    ``journal_subject`` 綁定就同時授權了三條 lane 上的破壞性補償。此處要求
    ``{"install": {...}, "prepare": {...}, "probe": {...}}`` 這種 per-lane 形狀;
    沒有該 lane 的鍵就是**沒有**該 lane 的授權(fail-closed)。
    """

    if not isinstance(ownership_evidence, dict):
        return {}
    if any(lane in ownership_evidence for lane in RECONCILE_LANES):
        return {
            lane: ownership_evidence.get(lane)
            for lane in RECONCILE_LANES
            if isinstance(ownership_evidence.get(lane), dict)
        }
    # 舊形(單一 subject map)只被視為 install lane 的鑰匙——它是 aggregate 交易遞交的那個。
    return {"install": ownership_evidence}


def _enumerate_startup_journals(driver: Any, *, known: set[str]) -> dict[str, Any]:
    """列舉三個 §5.2 parent,回**未被指名**的 journal 路徑(路徑一律由 journal 葉重算)。

    E16:同一趟列舉也把**擱淺的 WAL 暫存檔**看出來。跨行程唯一的
    ``.<basename>.tmp.<pid>-<128 bit 隨機>.<attempt>`` 名字修掉了「每個新行程都撞上前一次崩潰
    留下的 ``.tmp.0``」那個 EEXIST 陷阱,但它同時讓 ``JOURNAL_TEMP_RESIDUE_RECOVERY_REQUIRED``
    只在**同一個行程內**可達:一次「create_temp_file 之後、atomic_rename 之前」的崩潰留下的檔
    自此永遠不會再被任何 ``O_EXCL`` 撞到,於是它在一個 root-owned 0700 目錄裡無聲地累積,沒有
    任何東西看得見它。列舉是唯一還看得見它的地方,所以它在此被報出來。
    """

    found: dict[str, str] = {}
    parents: dict[str, Any] = {}
    reasons: list[str] = []
    for lane, (parent, pattern, derive) in sorted(_LANE_PARENTS.items()):
        # JournalStore 只用它來開/驗這個 parent 目錄本身;basename 是不會存在的哨兵。
        store = _journal.JournalStore(
            driver, journal_path=f"{parent}/.s2-4-enumeration-probe"
        )
        listing = store.list_basenames()
        parents[lane] = {"parent": parent, "status": listing["status"], "temp_residue": []}
        if listing["status"] != _journal.JOURNAL_STATUS_LOADED:
            reasons.extend(listing["reasons"])
            reasons.append(
                f"the {lane} journal parent {parent} could not be enumerated, so §5.2's "
                "'reconcile ANY non-terminal journal before accepting new work' cannot be "
                "established; RECOVERY_REQUIRED with zero mutation"
            )
            continue
        residue = sorted(
            basename for basename in listing["basenames"]
            if _journal.JOURNAL_TEMP_RESIDUE_RE.fullmatch(basename) is not None
        )
        parents[lane]["temp_residue"] = residue
        if residue:
            reasons.append(
                f"the {lane} journal parent {parent} holds stranded write-ahead temp files "
                f"{residue}: a previous runner crashed between create_temp_file(O_EXCL) and "
                "the atomic rename, so a partially written journal body is sitting in a "
                "root-owned 0700 directory that nothing else will ever look at "
                f"({_journal.JOURNAL_STATUS_TEMP_COLLISION}). §5.2 forbids this surface from "
                "renaming or removing it, so an operator must inspect and clear it; "
                "RECOVERY_REQUIRED with zero mutation"
            )
        for basename in listing["basenames"]:
            match = pattern.fullmatch(basename)
            if match is None:
                continue
            path = derive(match.group(1))
            if path in known:
                continue
            found[f"{lane}:{match.group(1)}"] = path
    return {"paths": found, "parents": parents, "reasons": reasons}


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

    def startup_reconcile_surface(self) -> dict[str, Any]:
        """把本 driver 背後的 durable journal 面**唯讀**暴露給 probe / PREPARE 進入點。

        §5.2 要求「接受新的 probe 或 prepare intent 之前先收斂任何非終端 journal」。那兩個
        進入點只認得自己的 host driver,而真正握著 journal 檔案系統與 install lock 的是
        本包裹層——所以由本層把它交出去(只交面,不交任何新 capability)。
        """

        return {"file_driver": self._store.driver, "lock_verdict": self._lock_verdict}

    def journal_transition(self, *, entry: dict[str, Any]) -> None:
        if not _lock.install_lock_is_held(self._lock_verdict):
            raise InstallDriverContractError("journal_transition_requires_the_install_lock")
        if self._transaction is not None:
            verdict = self._transaction.record(
                state=entry["state"],
                pre_state_digest=entry["pre_state_digest"],
                post_state_digest=entry["post_state_digest"],
                step_index=self._step_index,
                # A9:被包裹的 row driver 以**自己的** subject digest 空間寫這幾筆。
                entry_source=(
                    entry.get("entry_source") or _journal.ENTRY_SOURCE_COMPONENT_ROW
                ),
                component_effect_class=entry.get("component_effect_class"),
            )
            self.commits.append(verdict)
            if verdict["status"] != _journal.JOURNAL_STATUS_COMMITTED:
                raise InstallDriverContractError(
                    "journal_transition_was_not_durably_committed"
                )
            self.entries = [dict(item) for item in self._transaction.entries]
            return
        routed = dict(entry)
        # ``terminal`` 是 journal 級的欄位而非 entry 欄位:呼叫端用它宣告「這一筆就是本本
        # journal 的終端」。過去這裡恆傳 False,於是**成功結束**的 probe / PREPARE 也在磁碟
        # 上留下一本永遠非終端的 journal——下一次啟動的 reconcile 會永遠把它讀成未解殘留。
        terminal = bool(routed.pop("terminal", False))
        routed["seq"] = len(self.entries)
        routed["fsynced"] = True
        routed.setdefault("entry_source", _journal.ENTRY_SOURCE_COMPONENT_ROW)
        if self._step_index is not None:
            routed["step_index"] = int(self._step_index)
        routed.setdefault("recorded_at", _iso(self._clock()))
        candidate = self.entries + [routed]
        verdict = self._store.commit(self._build_journal(candidate, terminal))
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
        "reconcile_enumerated_parents": [
            parent for parent, _pattern, _derive in
            (_LANE_PARENTS[lane] for lane in sorted(_LANE_PARENTS))
        ],
        "reconcile_lane_paths_are_rederived": True,
        "reconcile_ownership_evidence_is_per_lane": True,
        "reconcile_typed_statuses": list(RECONCILE_TYPED_STATUSES),
        "reconcile_admits_new_work": list(RECONCILE_ADMITS_NEW_WORK),
        "reconcile_blocking_order": list(_RECONCILE_BLOCKING_ORDER),
        "reconcile_projection": dict(_RECONCILE_PROJECTION),
    }

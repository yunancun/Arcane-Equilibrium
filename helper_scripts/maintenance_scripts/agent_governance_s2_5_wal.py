#!/usr/bin/env python3
"""S2.5(WP5)§5.7 durability substrate —— WAL journal / replay-ledger 持久化 / 兩把鎖。

自 ``agent_governance_s2_5_lifecycle`` 拆出(S2E.3 C7:該葉在 durability 修法後越過 repo
的 2000 行硬上限)。**零語義變更**:此處是 lifecycle 葉逐位元組搬入的同一批函式;applier
仍以 ``from agent_governance_s2_5_wal import ...`` 逐名再匯入,故既有匯入面與 monkeypatch
面(``lifecycle.<name>``)一律照舊可解析/可覆寫。

三個關注點:

* **路徑導出**:journal 檔名唯一由 ``start_id`` regex 派生,ledger 是 state_root 下的固定
  basename —— worker 不得選位置;
* **durable WAL**:``_durable_write_json``(O_NOFOLLOW|O_EXCL 唯一暫存名 → fsync →
  os.replace → parent-dir fsync)、journal v2 的 hash chain + self_digest、
  ``reconcile_s2_5_journal`` 的 tamper 偵測、replay ledger 的鎖下持久化與 head-anchor;
* **兩把鎖**:S2.4 install 鎖的 probe-only 面與 S2.5 lifecycle 鎖的 hold 面是**兩個資源**
  (S2E.3 F3),外加 typed release 與 ``lock_window`` 證據(F4)。

⚠ 誠實邊界:此處全部是本行程的結構/完整性證據。self_digest 只證 integrity 不證作者;
``lock_window`` 只證本行程 acquire/release 對稱;本模組永不接觸真實 systemd/PG。
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_5_attestation as attestation  # noqa: E402
from agent_governance_s2_4_credential import redact_driver_error  # noqa: E402
from agent_governance_s2_4_lock import (  # noqa: E402
    INSTALL_LOCK_PATH as S2_4_INSTALL_LOCK_PATH,
)

# 斷鏈 journal 被強制記成的狀態;lifecycle 於 import 期 assert 它等於自己的 typed
# recovery status,分歧即 import 期炸——不留第二套自由字面量。
JOURNAL_RECOVERY_REQUIRED_STATE = "RECOVERY_REQUIRED"


# §5.7 journal 狀態(WAL:先寫 APPLYING 再動 effect;terminal 之外的殘留擋新 effect)。
_JOURNAL_TERMINAL_STATES = frozenset({
    "TERMINAL_SUCCESS", "TERMINAL_ROLLED_BACK", "TERMINAL_FAILED",
})
JOURNAL_CORRUPT = "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
# note-1:journal payload v2 —— per-entry hash chain + top-level self_digest。v1 形狀
# (無 digest 無鏈)刻意**不**再被讀取:留一條 v1 相容路徑等同留一個降級縫。
S2_5_JOURNAL_SCHEMA_VERSION = "s2_5_start_journal_v2_informal"
# ── §5.7 的固定路徑面(worker 不得選 journal/ledger 位置;source lane 只以注入的
# tmp state_root 觸碰)。journal 檔名唯一由 start_id regex 派生(鏡 probe_journal_path)。
S2_5_STATE_ROOT = "/var/lib/arcane-equilibrium/aiml/install/s2_5"
S2_5_LOCK_PATH = "/run/lock/arcane-equilibrium-aiml-s2-5-lifecycle.lock"
S2_5_REPLAY_LEDGER_BASENAME = "authorization-replay-ledger.json"
_S2_5_START_ID_RE = re.compile(r"^s2-5-[0-9a-f]{64}$")
_S2_5_JOURNAL_NAME_RE = re.compile(r"^s2-5-[0-9a-f]{64}\.journal\.json$")


# ── §5.7 路徑導出(caller 的字串永不成為 journal 檔名;source lane 只注入 state_root)──
def s2_5_journal_path(state_root: Path | str, start_id: Any) -> Path:
    """``<state_root>/<start_id>.journal.json``——檔名唯一由 start_id regex 派生
    (鏡 ``probe_journal_path``:畸形 id 於此 typed 拒,caller 不得指定任意 journal 路徑)。"""

    if not isinstance(start_id, str) or _S2_5_START_ID_RE.fullmatch(start_id) is None:
        raise ValueError("s2_5 start_id is malformed; the journal path derives from it")
    return Path(state_root) / f"{start_id}.journal.json"


def s2_5_replay_ledger_path(state_root: Path | str) -> Path:
    """§5.7 replay ledger 的唯一位置(state_root 下的固定 basename)。"""

    return Path(state_root) / S2_5_REPLAY_LEDGER_BASENAME


# ── §5.7 WAL journal(durable 落盤紀律鏡 s2_4 journal 葉:O_NOFOLLOW|O_EXCL 唯一暫存名
# → file fsync → os.replace → parent-dir fsync;目錄 0700、檔案 0600)────────────────
def _durable_write_json(target: Path, payload: dict[str, Any]) -> None:
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    os.chmod(parent, 0o700)
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    # 暫存名跨行程唯一(<pid hex>-<64 bit 隨機>):O_EXCL 是防競態的原子性手段,唯一性
    # 使上一次崩潰的殘留不再撞名(s2_4 journal 葉 E16 的同一教訓)。
    temp_path = parent / f".{target.name}.tmp.{os.getpid():x}-{os.urandom(8).hex()}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open(temp_path, flags, 0o600)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(temp_path, target)
    dir_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


def _journal_payload_errors(payload: Any, *, start_id: str | None = None) -> list[str]:
    """note-1:一份 journal payload 的完整性重驗(self_digest + hash chain + 尾錨一致)。

    **刻意沒有 v1 讀取相容分支**:v1 形狀既無 per-entry digest 也無 self_digest,保留
    「讀得懂 v1」正是一個可被利用的降級縫(把 v2 換成 v1 形狀即繞過全部鏈驗)。
    repo 內無任何 ``*.journal.json``、production state_root 亦不存在 ⇒ 零遷移代價。
    """

    if not isinstance(payload, dict):
        return ["s2_5 journal payload must be an object"]
    if payload.get("schema_version") != S2_5_JOURNAL_SCHEMA_VERSION:
        return [
            f"s2_5 journal declares schema_version {payload.get('schema_version')!r}; "
            f"only {S2_5_JOURNAL_SCHEMA_VERSION} is read (there is no v1 downgrade branch)"
        ]
    if payload.get("append_only") is not True:
        return ["s2_5 journal must declare append_only"]
    if payload.get("self_digest") != central_validator.artifact_self_digest(payload):
        return [
            "s2_5 journal self_digest does not re-derive; the payload was rewritten "
            "without resealing (fail-closed)"
        ]
    if start_id is not None and payload.get("start_id") != start_id:
        return ["s2_5 journal start_id does not bind this apply"]
    history = payload.get("history")
    chain_errors = attestation.s2_5_journal_entry_errors(history)
    if chain_errors:
        return chain_errors
    if not history:
        return ["s2_5 journal history is empty; every transition appends one entry"]
    tail = history[-1]
    if (
        tail.get("state") != payload.get("state")
        or tail.get("updated_at") != payload.get("updated_at")
    ):
        return [
            "s2_5 journal top-level state/updated_at do not equal the tail entry; a "
            "header rewritten over an intact chain is rejected (fail-closed)"
        ]
    return []


def _journal_transition(
    journal_path: Path,
    *,
    start_id: str,
    state: str,
    updated_at: str,
    replay_ledger_head: dict[str, Any] | None = None,
    lock_release_status: str | None = None,
) -> dict[str, Any]:
    """note-1:**驗證後追加,永不靜默重置**;斷鏈留痕 **sticky**。

    修前:讀不懂的 journal 讓 ``history`` 直接歸零(281-282),歷史消失不留痕。現在壞
    payload 會開新鏈但打上 ``integrity_broken``/``prior_payload_digest``,且 state 強制
    ``RECOVERY_REQUIRED`` —— 一次無聲的歷史清洗因此不再可能。

    E2 P1-1:留痕必須**跨越後續每一次 append**。斷鏈後寫出的那一份自己是一份合法 v2
    payload,若旗標只在「本次讀到壞 bytes」時成立,連續兩次 transition 就足以把
    ``RECOVERY_REQUIRED`` 洗成 ``TERMINAL_SUCCESS`` 並讓 ``prior_payload_digest`` 歸 None
    —— 那正是本函式宣稱要擋的事。旗標因此只由 operator 面的重建結束,絕不由再一次
    transition 自癒。
    """

    history: list[dict[str, Any]] = []
    carried_head: dict[str, Any] | None = None
    chain_broken_now = False
    integrity_broken = False
    prior_payload_digest: str | None = None
    if journal_path.is_file():
        try:
            raw = journal_path.read_text(encoding="utf-8")
        except OSError:
            raw = None
            chain_broken_now = True
        else:
            try:
                existing = json.loads(raw)
            except ValueError:
                existing = None
            if _journal_payload_errors(existing, start_id=start_id):
                chain_broken_now = True
                prior_payload_digest = central_validator.canonical_digest(
                    {"prior_journal_bytes": raw}
                )
            else:
                history = list(existing["history"])
                head = existing.get("replay_ledger_head")
                carried_head = dict(head) if isinstance(head, dict) else None
                if existing.get("integrity_broken") is True:
                    # sticky:合法但已留痕的 payload,旗標與舊 bytes 的 digest 一律續帶。
                    integrity_broken = True
                    carried_digest = existing.get("prior_payload_digest")
                    prior_payload_digest = (
                        carried_digest if isinstance(carried_digest, str) else None
                    )
    integrity_broken = integrity_broken or chain_broken_now
    if integrity_broken:
        # 本次才讀到壞 bytes ⇒ 開新鏈(舊 bytes 已不可信),但把「發生過一次斷鏈」與舊
        # bytes 的 digest 留在檔上;sticky 續帶時 history 本身仍是合法鏈,續 append 保住
        # 可稽核軌跡。兩條路徑的 state 都強制 RECOVERY_REQUIRED —— 斷鏈的主機狀態不明,
        # 絕不由本次 transition 洗白。
        if chain_broken_now:
            history = []
        state = JOURNAL_RECOVERY_REQUIRED_STATE
    entry: dict[str, Any] = {
        "seq": len(history),
        "state": state,
        "updated_at": updated_at,
        "lock_release_status": lock_release_status,
        "prev_entry_digest": history[-1]["entry_digest"] if history else None,
        "fsynced": True,
    }
    entry["entry_digest"] = central_validator.canonical_digest(entry)
    payload = {
        "schema_version": S2_5_JOURNAL_SCHEMA_VERSION,
        "start_id": start_id,
        "append_only": True,
        "integrity_broken": integrity_broken,
        "prior_payload_digest": prior_payload_digest,
        "state": state,
        "updated_at": updated_at,
        # P1-3 head-anchor:journal 釘住消費當下的 ledger head(entry 總數+尾 digest+
        # ledger self_digest),使尾部截斷與整本清空在同 start_id 重放時可測。
        "replay_ledger_head": (
            dict(replay_ledger_head) if replay_ledger_head is not None else carried_head
        ),
        "history": history + [entry],
    }
    payload["self_digest"] = central_validator.artifact_self_digest(payload)
    _durable_write_json(journal_path, payload)
    return payload


def _terminal_journal_ledger_anchor_reasons(
    root: Path, payload: dict[str, Any], journal_name: str
) -> list[str]:
    """note-1:終端 journal 宣稱的 ledger head 必須真的存在於 durable ledger。

    自洽的 journal 仍可能與 ledger 不相容(整本 ledger 被清空/截尾而 journal 未動)。
    複用既有的 :func:`_ledger_behind_head_reasons`——不為此另造第二把尺。
    """

    head = payload.get("replay_ledger_head")
    if not isinstance(head, dict):
        return []
    ledger_path = s2_5_replay_ledger_path(root)
    entries: Any = None
    if ledger_path.is_file():
        try:
            persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            persisted = None
        if isinstance(persisted, dict):
            entries = persisted.get("entries")
    return [
        f"s2_5 journal {journal_name} is terminal but its pinned replay-ledger head is "
        f"not covered by the durable ledger: {reason}"
        for reason in _ledger_behind_head_reasons(entries, head, anchor="terminal-journal")
    ]


def reconcile_s2_5_journal(state_root: Path | str | None) -> dict[str, Any]:
    """§5.2 語義:state_root 下**任一** journal 的非終端殘留/corrupt 一律擋新 effect。

    掃描整個 state_root(而非只看本 start_id 的 journal):別的 start 留下的 APPLYING
    殘留同樣代表一台狀態不明的主機,fail-closed。

    note-1 之後這裡是**主要的 tamper 偵測器**:每份 journal 過 self_digest + hash chain +
    尾錨一致性,`integrity_broken` 留痕一律擋,終端 journal 釘的 ledger head 必須被
    durable ledger 涵蓋。

    ⚠ 誠實偵測邊界:關得掉=單 entry 改而不重算全鏈 / 截尾而不重封 self_digest / 自洽但與
    ledger head 不相容 / 壞 journal 靜默歸零 / 一份終端 journal 被複製成另一個 start_id 的
    檔名(P2-3:start_id 由檔名導出並驗);**關不掉**兩項——(1)具 state_root write 權限者
    同時且一致地重寫 journal + ledger(self-digest 只證 integrity,不證作者);(2)**把
    journal 檔整個 ``unlink``**:state_root 目錄層沒有 anchor/manifest,「少一個檔」與「從未
    存在」無法區分,單一次刪除即讓本函式放行且不留痕。故此修的定位只到「把無聲**改寫**降級
    為必須做一次一致的多檔改寫」——**刪除**仍只需一次 unlink,真解(目錄層 anchor/manifest
    + startup recovery)屬 host-runner 波,不在本 tranche。
    """

    if state_root is None:
        return {
            "admits_new_work": False,
            "reasons": [
                "s2_5 journal surface is absent; a driver-present apply requires a durable "
                "WAL state root (fail-closed)"
            ],
        }
    root = Path(state_root)
    if not root.is_dir():
        return {"admits_new_work": True, "reasons": []}
    for journal_path in sorted(root.glob("s2-5-*.journal.json")):
        if _S2_5_JOURNAL_NAME_RE.fullmatch(journal_path.name) is None:
            continue
        try:
            payload = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = None
        # E2 P2-3:start_id 必須由**檔名**導出並一併驗。不帶 start_id 時,把 A 的
        # TERMINAL_SUCCESS journal 原樣複製成 B 的合法檔名即可通過(內容完全自洽),
        # 一份終端 journal 因此能被複製成任意 start_id 的「已完成」證據。
        payload_errors = _journal_payload_errors(
            payload, start_id=journal_path.name[: -len(".journal.json")]
        )
        if payload_errors:
            return {
                "admits_new_work": False,
                "reasons": [
                    f"{JOURNAL_CORRUPT}: the s2_5 journal {journal_path.name} does not "
                    "re-derive; operator investigation is required before any new effect "
                    "(" + "; ".join(payload_errors) + ")"
                ],
            }
        if payload.get("integrity_broken") is True:
            return {
                "admits_new_work": False,
                "reasons": [
                    f"{JOURNAL_CORRUPT}: the s2_5 journal {journal_path.name} records a "
                    "broken integrity chain (prior_payload_digest="
                    f"{payload.get('prior_payload_digest')}); the history was reset once "
                    "and the host state is unproven"
                ],
            }
        state = payload["state"]
        if state not in _JOURNAL_TERMINAL_STATES:
            return {
                "admits_new_work": False,
                "reasons": [
                    f"s2_5 journal {journal_path.name} holds a non-terminal state "
                    f"{state!r}; §5.2 reconciles any non-terminal journal before a new "
                    "effect is accepted"
                ],
            }
        anchor_reasons = _terminal_journal_ledger_anchor_reasons(
            root, payload, journal_path.name
        )
        if anchor_reasons:
            return {"admits_new_work": False, "reasons": anchor_reasons}
    return {"admits_new_work": True, "reasons": []}


# ── P1-3 replay ledger 的鎖下持久化 + head-anchor 驗證面 ───────────────────────────
def _persist_s2_5_replay_ledger(ledger_path: Path, replay_ledger: dict[str, Any]) -> dict[str, Any]:
    """把 in-memory chain 封成 closed artifact 並以 journal 同紀律 durable 落盤。"""

    sealed = attestation.seal_s2_5_replay_ledger(
        replay_ledger, ledger_path=str(ledger_path)
    )
    _durable_write_json(ledger_path, sealed)
    return sealed


def _replay_ledger_head(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "entry_count": len(entries),
        "tail_entry_digest": entries[-1]["entry_digest"] if entries else None,
    }


def _ledger_behind_head_reasons(
    entries: Any, head: dict[str, Any], *, anchor: str
) -> list[str]:
    count = head.get("entry_count")
    tail = head.get("tail_entry_digest")
    if not isinstance(count, int) or count <= 0 or not tail:
        return []
    if (
        not isinstance(entries, list)
        or len(entries) < count
        or not isinstance(entries[count - 1], dict)
        or entries[count - 1].get("entry_digest") != tail
    ):
        return [
            f"s2_5 replay ledger does not contain the {anchor}-pinned head "
            f"(entry_count={count}); a truncated or wiped ledger never re-admits a "
            "consumed authorization (fail-closed)"
        ]
    return []


def _replay_ledger_anchor_reasons(
    journal_path: Path, ledger_path: Path, replay_ledger: Any
) -> list[str]:
    """head-anchor(P1-3):journal 釘的 head 與 durable ledger head 都必須被涵蓋。

    截斷尾 entry/整本清空的 in-memory ledger 在此被抓——沒有 anchor 時,截斷後的 prefix
    仍是一條合法 hash chain,consume-once 無從執法。
    """

    reasons: list[str] = []
    entries = replay_ledger.get("entries") if isinstance(replay_ledger, dict) else None
    # 1. 本 start_id 的 journal 釘過的 head(同 intent 重放時的錨)。
    if journal_path.is_file():
        try:
            journal = json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            journal = None
        head = (journal or {}).get("replay_ledger_head")
        if isinstance(head, dict):
            reasons.extend(_ledger_behind_head_reasons(entries, head, anchor="journal"))
    # 2. durable ledger 檔自身(state_root 的 exact durable head)。
    if ledger_path.is_file():
        try:
            persisted = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return reasons + [
                "s2_5 durable replay ledger cannot be parsed; a malformed ledger blocks "
                "any new authorization consumption (fail-closed)"
            ]
        if not isinstance(persisted, dict) or persisted.get(
            "self_digest"
        ) != central_validator.artifact_self_digest(persisted):
            return reasons + [
                "s2_5 durable replay ledger self_digest does not re-derive; a tampered "
                "ledger blocks any new authorization consumption (fail-closed)"
            ]
        persisted_entries = persisted.get("entries") or []
        chain_errors = attestation.s2_5_replay_ledger_entry_errors(persisted_entries)
        if chain_errors:
            return reasons + chain_errors
        reasons.extend(
            _ledger_behind_head_reasons(
                entries, _replay_ledger_head(persisted_entries), anchor="durable-ledger"
            )
        )
    return reasons


# ── P1-5 §5.7 lock:install_lock_free 唯一由真 flock 探測導出(caller 自報不採信)────
# P2-2(tranche 2)typed lock statuses:hold-style 面鏡 s2_4 lock 葉的公開形制
# (ACQUIRED/HELD/RELEASED/NOT_HELD/PRECHECK_FAILED),但鎖的是 S2.5 自己的 lifecycle 鎖。
S2_5_LOCK_ACQUIRED = "S2_5_LIFECYCLE_LOCK_ACQUIRED"
S2_5_LOCK_HELD = "S2_5_LIFECYCLE_LOCK_HELD"
S2_5_LOCK_RELEASED = "S2_5_LIFECYCLE_LOCK_RELEASED"
S2_5_LOCK_NOT_HELD = "S2_5_LIFECYCLE_LOCK_NOT_HELD"
S2_5_LOCK_PRECHECK_FAILED = "S2_5_LIFECYCLE_LOCK_PRECHECK_FAILED"
# F4:release 也是 typed outcome(修前它回 None、無 release 面靜默忽略、例外 `pass`,
# 於是「鎖窗有沒有被正常關閉」在 verdict/receipt 上完全不可見)。
S2_5_LOCK_RELEASE_FAILED = "S2_5_LIFECYCLE_LOCK_RELEASE_FAILED"
S2_5_LOCK_RELEASE_UNTYPED = "S2_5_LIFECYCLE_LOCK_RELEASE_UNTYPED"
# receipt/verdict 上 lock_window.release_status 的封閉集:兩個 s2_5 attestation schema 的
# enum、中央閘成功臂採用的字面量與此三方逐字同源,由
# ``test_the_release_status_enum_is_pinned_three_ways`` 執法(E2 P2-4:此常量原本零引用,
# 註解宣稱的同源性沒有任何執法點),並在 :func:`_lock_window_evidence` 就地當白名單用。
S2_5_LOCK_RELEASE_STATUSES = (
    S2_5_LOCK_RELEASED,
    S2_5_LOCK_NOT_HELD,
    S2_5_LOCK_RELEASE_FAILED,
    S2_5_LOCK_RELEASE_UNTYPED,
)


def _flock_free_observation(lock_path: Path | str) -> dict[str, Any]:
    """probe-only 的 non-blocking exclusive ``flock`` 探測(探測即釋放)。

    只證「當下自由」,**不護任何窗**;lock 檔不存在=無人持有;O_NOFOLLOW 拒 symlink 替身
    (逸出交由 caller 當 unproven-free 處理);lock 檔永不 unlink/chmod(§5.2 紀律)。
    """

    path = Path(lock_path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return {"held": False, "exists": False, "lock_path": str(path)}
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"held": True, "exists": True, "lock_path": str(path)}
        fcntl.flock(fd, fcntl.LOCK_UN)
        return {"held": False, "exists": True, "lock_path": str(path)}
    finally:
        os.close(fd)


class S2_4InstallLockFreeProbe:
    """**S2.4 install 鎖**的 probe-only 面(F3:與 S2.5 lifecycle 鎖是兩個資源)。

    §3.1c 的 ``install_lock_free`` 問的是「S2.4 的 install 交易是否正在進行」,故此探針
    的預設路徑是 :data:`S2_4_INSTALL_LOCK_PATH`(來自 s2_4 lock 葉的 SSOT,不重宣告)。
    刻意**沒有** acquire/release:S2.5 永不去持有 S2.4 的鎖(那會與合法 install 交易競爭)。
    """

    def __init__(self, lock_path: Path | str = S2_4_INSTALL_LOCK_PATH) -> None:
        self.lock_path = Path(lock_path)

    def flock_probe(self) -> dict[str, Any]:
        return _flock_free_observation(self.lock_path)


class S2_5LifecycleLockHold:
    """**S2.5 lifecycle 鎖**的 hold-style 面(P2-2;鏡 ``agent_governance_s2_4_lock`` 的公開形制)。

    取得後 fd 一直持有到 :meth:`release`,reconcile→anchor-check→前態→consume→persist→
    journal 整段在鎖下,關閉「探測即釋放」與消費之間的競態窗。刻意**沒有** ``flock_probe``:
    probe-only 面不護窗,把兩者放在同一個 class 上正是 F3 要拆掉的混淆。

    production 面預設 :data:`S2_5_LOCK_PATH`;source lane/測試注入 tmp 路徑。lock 檔不存在
    =無人持有(由取鎖者以 O_CREAT 建立);O_NOFOLLOW 拒 symlink 替身;永不 unlink/chmod。
    """

    def __init__(self, lock_path: Path | str = S2_5_LOCK_PATH) -> None:
        self.lock_path = Path(lock_path)
        self._held_fd: int | None = None

    def acquire(self) -> dict[str, Any]:
        """hold-style 取鎖:non-blocking exclusive flock,取得後持有到 :meth:`release`。"""

        if self._held_fd is not None:
            return {
                "status": S2_5_LOCK_HELD,
                "lock_path": str(self.lock_path),
                "reasons": [
                    "this hold already owns the s2_5 lifecycle lock (a hold is "
                    "never re-entrant)"
                ],
            }
        try:
            fd = os.open(
                self.lock_path,
                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
        except OSError as error:
            # symlink 替身(O_NOFOLLOW)/權限問題:unproven fail-closed,零變更。
            return {
                "status": S2_5_LOCK_PRECHECK_FAILED,
                "lock_path": str(self.lock_path),
                "reasons": [
                    "s2_5 lifecycle lock open failed: " + redact_driver_error(error)
                ],
            }
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            return {
                "status": S2_5_LOCK_HELD,
                "lock_path": str(self.lock_path),
                "reasons": [
                    "another S2.5 applier holds the lifecycle lock (a live consume→"
                    "persist transaction is in flight); typed rejection with zero "
                    "consumption"
                ],
            }
        self._held_fd = fd
        return {
            "status": S2_5_LOCK_ACQUIRED,
            "lock_path": str(self.lock_path),
            "reasons": [],
        }

    def release(self) -> dict[str, Any]:
        """釋放 hold(flock UN + close fd);永不 unlink。未持有=typed NOT_HELD。"""

        if self._held_fd is None:
            return {
                "status": S2_5_LOCK_NOT_HELD,
                "lock_path": str(self.lock_path),
                "reasons": ["no s2_5 lifecycle hold is held by this object"],
            }
        fd, self._held_fd = self._held_fd, None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
        return {
            "status": S2_5_LOCK_RELEASED,
            "lock_path": str(self.lock_path),
            "reasons": [],
        }


def derive_s2_4_install_lock_free(install_lock_probe: Any) -> tuple[bool, list[str]]:
    """``install_lock_free`` 的唯一導出點:注入 **S2.4 install** 鎖介面的真 flock 探測。

    F3:改名前這個函式收的是 S2.5 自己的 lifecycle 鎖探針(``S2_5FlockProbe`` 預設
    ``S2_5_LOCK_PATH``),於是 receipt 上的 ``install_lock_free`` **從未探測過 S2.4 install
    lock**,而另一個 S2.5 applier 持 hold 時得到的 reason 竟寫「S2.4 install lock is held」
    ——歸因錯誤。型別互斥守衛在此執法:帶 hold 面(acquire)的物件是 lifecycle 鎖,不是
    install 探針,一律 typed 拒。

    無介面/探測逸出/held/形狀不明 一律 ``(False, typed reasons)``——自報 boolean 永不採信。
    """

    if install_lock_probe is None:
        return False, [
            "no S2.4 install-lock probe interface was injected; lock freedom cannot be "
            "proved (a caller-asserted boolean is never accepted)"
        ]
    if isinstance(install_lock_probe, bool):
        return False, [
            "a bare boolean is not a lock probe; install_lock_free derives only from a "
            "real non-blocking flock probe of the S2.4 install lock (§5.7)"
        ]
    if callable(getattr(install_lock_probe, "acquire", None)):
        return False, [
            "the injected S2.4 install-lock probe exposes a hold-style acquire; that is "
            "the S2.5 lifecycle lock, not the S2.4 install lock (S2.5 never holds the "
            "install lock — it would race a legitimate install transaction)"
        ]
    try:
        observation = install_lock_probe.flock_probe()
    except Exception as error:  # noqa: BLE001 —— 探測逸出=unproven-free,fail-closed。
        return False, [
            f"S2.4 install-lock probe raised: {redact_driver_error(error)} "
            "(unproven-free fails closed)"
        ]
    if not isinstance(observation, dict) or observation.get("held") is not False:
        return False, [
            "the S2.4 install lock is held (or the probe observation is malformed); a "
            "live install transaction blocks any S2.5 lifecycle effect"
        ]
    return True, []


def _resolved_lock_path(lock_face: Any) -> str | None:
    """取注入物件宣告的 lock 位置並正規化(不可導出 ⇒ ``None`` ⇒ 分離不可證)。"""

    declared = getattr(lock_face, "lock_path", None)
    if declared is None:
        return None
    try:
        return os.path.normpath(os.path.abspath(str(declared)))
    except (TypeError, ValueError):
        return None


def _lock_resource_separation_reasons(
    install_lock_probe: Any, lifecycle_lock: Any
) -> list[str]:
    """F3 的 load-bearing 守衛:兩個 lock 面必須是**兩個資源**(在取 hold 之前執法)。

    同一物件、或解析後指向同一個 lock 檔,都代表「S2.4 install 自由」與「S2.5 lifecycle
    窗互斥」兩件事被同一把鎖同時充當——那正是改名前 receipt 上 ``install_lock_free``
    無意義的根因。不可導出位置=分離不可證,同樣 fail-closed。
    """

    if install_lock_probe is not None and install_lock_probe is lifecycle_lock:
        return [
            "the S2.4 install-lock probe and the S2.5 lifecycle hold are the same "
            "object; one lock can never stand for both resources (fail-closed)"
        ]
    install_path = _resolved_lock_path(install_lock_probe)
    lifecycle_path = _resolved_lock_path(lifecycle_lock)
    if install_path is None or lifecycle_path is None:
        return [
            "the injected lock faces do not declare resolvable lock_path values; the "
            "S2.4 install lock and the S2.5 lifecycle lock cannot be proved distinct "
            "(fail-closed)"
        ]
    if install_path == lifecycle_path:
        return [
            "the S2.4 install lock and the S2.5 lifecycle lock resolve to the same file; "
            "S2.5 must never contend for the install lock (fail-closed)"
        ]
    return []


def acquire_s2_5_lifecycle_hold(lifecycle_lock: Any) -> tuple[bool, list[str]]:
    """P2-2:consume→persist→journal 交易窗的 hold-style 取鎖(唯一導出點)。

    probe-only 面(只有 ``flock_probe``)不足以護窗——探測即釋放,兩個 applier 可在
    「探測自由」與「消費 permit」之間交錯而雙消費。無 hold 面/取鎖逸出/被持有/形狀
    不明一律 ``(False, typed reasons)`` fail-closed。
    """

    acquire = getattr(lifecycle_lock, "acquire", None)
    if not callable(acquire):
        return False, [
            "the injected lock interface has no hold-style acquire; a probe-only "
            "interface cannot guard the consume→persist window (fail-closed)"
        ]
    try:
        verdict = acquire()
    except Exception as error:  # noqa: BLE001 —— 取鎖逸出=unproven,fail-closed。
        return False, [
            f"s2_5 lifecycle lock acquire raised: {redact_driver_error(error)} "
            "(an unproven hold fails closed)"
        ]
    if not isinstance(verdict, dict) or verdict.get("status") != S2_5_LOCK_ACQUIRED:
        reasons = (
            [str(r) for r in verdict.get("reasons") or []]
            if isinstance(verdict, dict)
            else []
        )
        return False, reasons or [
            "the s2_5 lifecycle lock was not acquired (held or malformed verdict); "
            "the consume→persist window never opens without the hold"
        ]
    return True, []


def _release_s2_5_lifecycle_hold(lifecycle_lock: Any) -> dict[str, Any]:
    """finally 臂的釋放,回 **typed outcome**(F4)。

    修前此函式回 ``None``:無 release 面靜默忽略、``except Exception: pass``,且呼叫點在
    ``finally`` 又不接回傳值 ⇒ release 失敗完全不可見,而效果窗照常開始。現在三種失敗
    形狀各有 typed status,由呼叫端收斂成 ``RECOVERY_REQUIRED``(不新增 verdict status)。

    仍不以第二個例外遮蔽窗內的真實 verdict/例外——釋放失敗時 fd 仍被持有=fail-closed
    方向(擋人而非放行)。
    """

    release = getattr(lifecycle_lock, "release", None)
    if not callable(release):
        return {
            "status": S2_5_LOCK_RELEASE_UNTYPED,
            "reasons": [
                "the injected lifecycle lock has no release face; the hold window cannot "
                "be proved closed (fail-closed)"
            ],
        }
    try:
        verdict = release()
    except Exception as error:  # noqa: BLE001 —— 釋放逸出=鎖窗未證關閉。
        return {
            "status": S2_5_LOCK_RELEASE_FAILED,
            "reasons": [
                "s2_5 lifecycle lock release raised: " + redact_driver_error(error)
            ],
        }
    status = verdict.get("status") if isinstance(verdict, dict) else None
    if status not in {S2_5_LOCK_RELEASED, S2_5_LOCK_NOT_HELD}:
        return {
            "status": S2_5_LOCK_RELEASE_UNTYPED,
            "reasons": [
                "s2_5 lifecycle lock release returned a malformed or unknown verdict; "
                "the hold window cannot be proved closed (fail-closed)"
            ],
        }
    if status == S2_5_LOCK_NOT_HELD:
        return {
            "status": S2_5_LOCK_NOT_HELD,
            "reasons": [
                "s2_5 lifecycle lock release reports no hold was held; the window this "
                "applier believed it owned is unaccounted for (fail-closed)"
            ],
        }
    return {"status": S2_5_LOCK_RELEASED, "reasons": []}


def _lock_window_evidence(
    *, hold_acquired: bool, release: dict[str, Any] | None
) -> dict[str, Any]:
    """F4 的最小可驗證形狀:「本行程的鎖窗被 typed 關閉」的三欄證據。

    ⚠ honesty:這證明的是**本行程**的 acquire/release 對稱地走完,**不**證明 lock 檔沒被
    root 竄改、也不證明別的主機上沒有第二個 applier。
    """

    status = (
        release["status"] if isinstance(release, dict) else S2_5_LOCK_NOT_HELD
    )
    if status not in S2_5_LOCK_RELEASE_STATUSES:
        # 封閉集之外的狀態一律收斂成 UNTYPED:receipt 的 enum 只認這四個,任何未來新增
        # 的 release status 若沒同步進 schema,寧可 fail-closed 也不寫出過不了閘的欄位。
        status = S2_5_LOCK_RELEASE_UNTYPED
    return {
        "hold_acquired": bool(hold_acquired),
        "hold_released": status == S2_5_LOCK_RELEASED,
        "release_status": status,
    }

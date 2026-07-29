#!/usr/bin/env python3
"""S2.5(WP5)lifecycle 葉——start/final 兩 phase 的 builders、prechecks、appliers 與 WAL。

design §3/§5/§7 的 SSOT:``apply_s2_5_start``(S2.5A:precheck → authorization → WAL →
``enable --now`` → 五維觀測 → receipt/rollback)與 ``apply_s2_5_final``(S2.5B:S2.1 drill
綁定 → 五維再證 → **watchdog reset last** → receipt)。

固定順序,driver 呼叫之前零變更(形制鏡 ``agent_governance_s2_4_probe.run_s2_4_capability_probe``):

0. 未解 recovery → ``RECOVERY_REQUIRED``;
1. intent 過中央閘 closed schema + §5.1 core/start_id 再導出;
2. phase/route-surface 再導出(phase↔effect-class 綁定;builder/install 面夾帶即拒);
3. 靜態 precheck(§3.1):S2.4 APPLIED_INACTIVE receipt digest 綁定、native-loader closure
   重驗、S2.4 recovery clear、install lock free;S2.5B 另加 S2.1 drill receipt 與 S2.5A
   attestation 的 digest 綁定;
4. 授權:§5.6 permit 驗簽(payload 綁定 + TTL/skew + 域分離)+ replay ledger 消費綁定;
5. intent 自身新鮮窗;
6. ``driver is None`` → ``EXTERNAL_VERIFICATION_PENDING``(零變更、零 driver 呼叫;
   Mac/source/test lane 的誠實終點);
7. driver 在場 → §5.7 journal reconcile → 前態讀取 → WAL(APPLYING)→ effect → 觀測 →
   receipt;任一維 fail → rollback-to-disabled(S2.5A)/ typed 失敗(S2.5B),rollback 自身
   失敗 → ``NOT_RESTORED`` + ``RECOVERY_REQUIRED``,絕不把部分態轉成功。

⚠ 誠實邊界:simulated/disposable lane 的成功頂點是 ``SOURCE_SIMULATION_PASS``
(``LOCAL_REPRODUCIBLE``);``RUNNING_ATTESTED``/``FINAL_ATTESTED`` 唯一由驗簽通過的
trusted-host attestor 簽章解鎖(key custody 鎖產線)。本模組永不接觸真實 systemd/PG;
production driver 只在 S2.5 EFFECT session 由 OPS 注入。九項 authority 恆 false。
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_5_attestation as attestation  # noqa: E402
from agent_governance_alr_quiesce_inventory import (  # noqa: E402
    UNIT_NAME,
    compute_owner_fingerprint,
)
from agent_governance_s2_4_credential import redact_driver_error  # noqa: E402
from agent_governance_s2_4_lock import (  # noqa: E402
    INSTALL_LOCK_PATH as S2_4_INSTALL_LOCK_PATH,
)
from agent_governance_s2_5_driver import S2_5_UNIT_NAME  # noqa: E402
from aiml_gate_receipt_s2_5 import (  # noqa: E402
    S2_5_PHASE_EFFECT_CLASS,
    S2_5_START_ID_PREFIX,
    s2_5_running_dimension_verdicts,
)

# WP3 的 owner 確認尺與 driver 常量必須是同一個 unit——分歧即 import 期炸(縱深防禦)。
assert UNIT_NAME == S2_5_UNIT_NAME, "S2.5 unit constant drifted from the WP3 inventory"

# ── typed statuses ───────────────────────────────────────────────────────────
S2_5_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
S2_5_STATUS_REQUEST_REJECTED = "REQUEST_REJECTED"
S2_5_STATUS_AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
S2_5_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
S2_5_STATUS_SIMULATION_PASS = "SOURCE_SIMULATION_PASS"
S2_5_STATUS_RUNNING_ATTESTED = "RUNNING_ATTESTED"
S2_5_STATUS_FINAL_ATTESTED = "FINAL_ATTESTED"
S2_5_STATUS_ATTESTATION_FAILED = "ATTESTATION_FAILED"
S2_5_TARGET_CLASSES = ("simulated_harness", "disposable_local", "production")
# §5.7 journal 狀態(WAL:先寫 APPLYING 再動 effect;terminal 之外的殘留擋新 effect)。
_JOURNAL_TERMINAL_STATES = frozenset({
    "TERMINAL_SUCCESS", "TERMINAL_ROLLED_BACK", "TERMINAL_FAILED",
})
JOURNAL_CORRUPT = "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
# ── §5.7 的固定路徑面(worker 不得選 journal/ledger 位置;source lane 只以注入的
# tmp state_root 觸碰)。journal 檔名唯一由 start_id regex 派生(鏡 probe_journal_path)。
S2_5_STATE_ROOT = "/var/lib/arcane-equilibrium/aiml/install/s2_5"
S2_5_LOCK_PATH = "/run/lock/arcane-equilibrium-aiml-s2-5-lifecycle.lock"
S2_5_REPLAY_LEDGER_BASENAME = "authorization-replay-ledger.json"
_S2_5_START_ID_RE = re.compile(r"^s2-5-[0-9a-f]{64}$")
_S2_5_JOURNAL_NAME_RE = re.compile(r"^s2-5-[0-9a-f]{64}\.journal\.json$")
# §11.21 secret-like 掃描(鏡 identity_acl_contract.PG_SECRET_LIKE_RE 形制):任何要被
# 回傳/落盤的 reason/evidence 字串命中即整段改寫,絕不讓秘密樣態進 verdict/receipt。
_S2_5_SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"pgpassword|private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}"
    r"|postgres(?:ql)?://[^\s:/@]+:[^\s:/@]+@",
    re.IGNORECASE,
)
_S2_5_SECRET_REDACTED = "<redacted: secret-like content was scrubbed from this reason>"


class S2_5RecoveryState:
    """跨 apply 的 in-process recovery 閂(未解 recovery 擋一切新 effect;§3.1c)。"""

    def __init__(self) -> None:
        self.unresolved: dict[str, Any] | None = None

    def record(self, *, start_id: str | None, reasons: list[str]) -> None:
        self.unresolved = {"start_id": start_id, "reasons": list(reasons)}

    def resolve(self, *, resolution_note: str) -> dict[str, Any] | None:
        resolved, self.unresolved = self.unresolved, None
        if resolved is not None:
            resolved["resolution_note"] = resolution_note
        return resolved


class S2_5RunningObserver(Protocol):
    """獨立 verifier node 的觀測面(五維 + persistence + owner 訊號 + post-reset)。"""

    verifier_node_id: str

    def observe_running_dimensions(self) -> dict[str, Any]: ...

    def observe_enabled_persistence(self) -> dict[str, Any]: ...

    def observe_owner_signals(self) -> dict[str, Any]: ...

    def oldest_evidence_at(self) -> str: ...

    def observe_post_reset(self) -> dict[str, Any]: ...


# ── builders(§5.1)───────────────────────────────────────────────────────────
def build_s2_5_start_core(
    *,
    phase: str,
    target_host: str,
    expected_unit_fragment_digest: str,
    s2_4_install_effect_receipt_digest: str,
    expected_launch_bundle_digest: str,
    expected_application_bundle_digest: str,
    expected_base_runtime_tree_digest: str,
    native_loader_closure_digest: str,
    source_head: str,
    issued_at: str,
    expires_at: str,
    s2_1_drill_receipt_digest: str | None = None,
    pre_drill_attestation_digest: str | None = None,
    attestation_window: dict[str, int] | None = None,
    start_budget_seconds: int = 120,
    rollback_budget_seconds: int = 120,
    safety_margin_seconds: int = 30,
    max_ttl_seconds: int = attestation.MAX_S2_5_PERMIT_TTL_SECONDS,
) -> dict[str, Any]:
    """unsigned start core(排除導出 id/授權/self_digest;§5.6 profile 由 phase 決定)。"""

    profile = attestation.S2_5_PERMIT_PROFILES[phase]
    return {
        "schema_version": "s2_5_start_core_v1",
        "phase": phase,
        "target_host": target_host,
        "unit_name": S2_5_UNIT_NAME,
        "expected_unit_fragment_digest": expected_unit_fragment_digest,
        "s2_4_install_effect_receipt_digest": s2_4_install_effect_receipt_digest,
        "expected_launch_bundle_digest": expected_launch_bundle_digest,
        "expected_application_bundle_digest": expected_application_bundle_digest,
        "expected_base_runtime_tree_digest": expected_base_runtime_tree_digest,
        "native_loader_closure_digest": native_loader_closure_digest,
        "s2_1_drill_receipt_digest": s2_1_drill_receipt_digest,
        "pre_drill_attestation_digest": pre_drill_attestation_digest,
        "attestation_window": dict(attestation_window or {
            "max_evidence_age_seconds": 120,
            "min_samples": 3,
            "sample_interval_seconds": 5,
        }),
        "start_budget_seconds": int(start_budget_seconds),
        "rollback_budget_seconds": int(rollback_budget_seconds),
        "safety_margin_seconds": int(safety_margin_seconds),
        "authorization_profile": {
            "profile_identity": profile["profile_identity"],
            "signature_namespace": profile["signature_namespace"],
            "attestor_identity": attestation.S2_5_ATTESTOR_IDENTITY,
            "attestor_namespace": attestation.S2_5_ATTESTOR_NAMESPACE,
            "max_ttl_seconds": int(max_ttl_seconds),
        },
        "source_head": source_head,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def build_s2_5_start_intent(
    core: dict[str, Any], *, expires_at: str, risk: str = "critical"
) -> dict[str, Any]:
    """closed route-class intent:phase↔effect-class 綁定 + 九個 forbidden surface 全 false。"""

    core_digest = central_validator.canonical_digest(core)
    intent: dict[str, Any] = {
        "schema_version": "s2_5_start_intent_v1",
        "route_class": "s2_5_start_intent",
        "core": core,
        "core_digest": core_digest,
        "start_id": S2_5_START_ID_PREFIX + core_digest.split(":", 1)[1],
        "route_surface": {
            "required_effect_class": S2_5_PHASE_EFFECT_CLASS[core["phase"]],
            "effect_lineage": "WATCHDOG_ROLLBACK_TEST",
            "runtime_effect": True,
            "service": "installed_unit_lifecycle_only",
            "risk": risk,
            "runtime_claim": True,
        },
        "forbidden_surfaces": {
            name: False
            for name in (
                "pg_write", "migration", "secret", "credential_install", "host_identity",
                "prepare_fetch_build", "unit_render_install", "daemon_reload",
                "broker_or_order",
            )
        },
        "expires_at": expires_at,
    }
    intent["self_digest"] = central_validator.artifact_self_digest(intent)
    return intent


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


def _journal_transition(
    journal_path: Path,
    *,
    start_id: str,
    state: str,
    updated_at: str,
    replay_ledger_head: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    carried_head: dict[str, Any] | None = None
    if journal_path.is_file():
        try:
            existing = json.loads(journal_path.read_text(encoding="utf-8"))
            history = list(existing.get("history") or [])
            head = existing.get("replay_ledger_head")
            carried_head = dict(head) if isinstance(head, dict) else None
        except (OSError, ValueError):
            history = []
    entry = {"state": state, "updated_at": updated_at}
    payload = {
        "schema_version": "s2_5_start_journal_v1_informal",
        "start_id": start_id,
        "state": state,
        "updated_at": updated_at,
        # P1-3 head-anchor:journal 釘住消費當下的 ledger head(entry 總數+尾 digest+
        # ledger self_digest),使尾部截斷與整本清空在同 start_id 重放時可測。
        "replay_ledger_head": (
            dict(replay_ledger_head) if replay_ledger_head is not None else carried_head
        ),
        "history": history + [entry],
    }
    _durable_write_json(journal_path, payload)
    return payload


def reconcile_s2_5_journal(state_root: Path | str | None) -> dict[str, Any]:
    """§5.2 語義:state_root 下**任一** journal 的非終端殘留/corrupt 一律擋新 effect。

    掃描整個 state_root(而非只看本 start_id 的 journal):別的 start 留下的 APPLYING
    殘留同樣代表一台狀態不明的主機,fail-closed。
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
            state = payload["state"]
        except (OSError, ValueError, KeyError, TypeError):
            return {
                "admits_new_work": False,
                "reasons": [
                    f"{JOURNAL_CORRUPT}: the s2_5 journal {journal_path.name} cannot be "
                    "parsed; operator investigation is required before any new effect"
                ],
            }
        if state not in _JOURNAL_TERMINAL_STATES:
            return {
                "admits_new_work": False,
                "reasons": [
                    f"s2_5 journal {journal_path.name} holds a non-terminal state "
                    f"{state!r}; §5.2 reconciles any non-terminal journal before a new "
                    "effect is accepted"
                ],
            }
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


def _release_s2_5_lifecycle_hold(lifecycle_lock: Any) -> None:
    """finally 臂的釋放。釋放失敗時 fd 仍被持有=fail-closed 方向(擋人而非放行),
    不以第二個例外遮蔽窗內的真實 verdict/例外。"""

    release = getattr(lifecycle_lock, "release", None)
    if callable(release):
        try:
            release()
        except Exception:  # noqa: BLE001
            pass


def derive_ttl_budget_status(core: Any, *, now: Any) -> dict[str, Any]:
    """TTL 預算不等式(E1#2):``start+rollback+safety ≤ permit 剩餘 TTL`` 才可開始。

    不夠時間完成 start+rollback(含 safety margin)的 effect 一開始就不該開始——
    否則 rollback 會落在 permit 過期之後,變成無授權的 lifecycle 操作。
    """

    verdict: dict[str, Any] = {
        "status": "TTL_BUDGET_EXCEEDED",
        "reasons": [],
        "required_seconds": None,
        "remaining_seconds": None,
    }
    if not isinstance(core, dict):
        verdict["reasons"] = ["s2_5 ttl budget requires the core object"]
        return verdict
    try:
        required = (
            int(core["start_budget_seconds"])
            + int(core["rollback_budget_seconds"])
            + int(core["safety_margin_seconds"])
        )
        expires = central_validator._parse_timestamp(str(core["expires_at"]))
        remaining = (expires - _resolve_now(now)).total_seconds()
    except (KeyError, TypeError, ValueError) as error:
        verdict["reasons"] = [f"s2_5 ttl budget cannot be derived: {error} (fail-closed)"]
        return verdict
    verdict["required_seconds"] = required
    verdict["remaining_seconds"] = remaining
    if required <= remaining:
        verdict["status"] = "TTL_BUDGET_OK"
        return verdict
    verdict["reasons"] = [
        f"s2_5 ttl budget exceeded: start+rollback+safety requires {required}s but the "
        f"permit window has only {remaining:.0f}s left; a start whose rollback would "
        "outlive the permit never begins (E1#2)"
    ]
    return verdict


# ── 內部小工具 ───────────────────────────────────────────────────────────────
def _scrub_secret_text(text: Any) -> Any:
    """reason/evidence 字串的 secret-like 掃描(§11.21/E2 F4):命中即整段改寫。"""

    if isinstance(text, str) and _S2_5_SECRET_LIKE_RE.search(text) is not None:
        return _S2_5_SECRET_REDACTED
    return text


def _secret_scan_errors(artifact: Any, path: str = "$") -> list[str]:
    """遞迴掃描即將落盤/回傳的 artifact(命中回 typed error,不逸出例外)。"""

    if isinstance(artifact, str):
        if _S2_5_SECRET_LIKE_RE.search(artifact) is not None:
            return [f"s2_5 artifact carries secret-like content at {path} (fail-closed)"]
        return []
    if isinstance(artifact, dict):
        hits: list[str] = []
        for key, value in artifact.items():
            hits.extend(_secret_scan_errors(key, f"{path}.{key}"))
            hits.extend(_secret_scan_errors(value, f"{path}.{key}"))
        return hits
    if isinstance(artifact, list):
        hits = []
        for index, value in enumerate(artifact):
            hits.extend(_secret_scan_errors(value, f"{path}[{index}]"))
        return hits
    return []


def _verdict(status: str, reasons: list[str], **extra: Any) -> dict[str, Any]:
    verdict = {"status": status, "reasons": [_scrub_secret_text(r) for r in reasons]}
    verdict.update(extra)
    return verdict


def _resolve_now(now: Any) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return central_validator._parse_timestamp(str(now))


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _bound_artifact_digest_ok(artifact: Any, bound_digest: Any) -> bool:
    """P1-2/E2 F1:上游 artifact 的 digest 綁定不採信自報值——就地以
    ``artifact_self_digest`` 重算,三值鏈相等才算在手(鏡 s2_4_install 的 W0 lineage 形制):
    ``recompute(artifact) == artifact["self_digest"] == core 綁定值``。"""

    return (
        isinstance(artifact, dict)
        and bool(artifact.get("self_digest"))
        and central_validator.artifact_self_digest(artifact) == artifact["self_digest"]
        and artifact["self_digest"] == bound_digest
    )


def _upstream_receipt_gate_reasons(
    artifact: dict[str, Any],
    *,
    now_dt: datetime,
    schema_version: str,
    label: str,
    expiry_field: str | None,
) -> list[str]:
    """PR#153 Codex-4:上游 receipt 的 **digest 綁定只證 bytes**,不證那份 receipt 站得住。

    ``_bound_artifact_digest_ok`` 對「任何 canonical 自洽的物件」都會通過——一份缺 closed
    schema 必填欄、缺五 APPLY row lineage、或已過期的 receipt 照樣能綁進 operator-signed
    intent。此處補上 §3.1a 原文要求的另一半(「digest 在手**且未過期**」):

    1. exact ``schema_version``(名字對不上就不必談內容);
    2. 中央閘全套(closed schema CP2b + 該 schema 的 lineage/委派驗;s2_4 走
       ``derive_install_lineage_status``,quiesce 走 S2.1 葉的逐 observation 再驗);
    3. wall-clock 窗:``expiry_field`` 已過 ⇒ typed 拒。quiesce result 的新鮮窗由中央閘
       自己判(``started_at <= now < evidence_expires_at``),故該分支傳 ``None`` 不重複判;
       s2_4 install receipt 在中央閘**沒有**窗判,由此處補。

    ⚠ honesty:通過此閘只證「這份 receipt 結構上站得住且未過期」,**不**證明它描述的安裝/
    drill 真的發生過(那需要 platform-attested 證據,非 source lane 可得)。
    """

    if artifact.get("schema_version") != schema_version:
        return [
            f"{label} does not declare schema_version {schema_version!r}; a differently "
            "shaped artifact never satisfies the binding (fail-closed)"
        ]
    reasons: list[str] = []
    central_errors = central_validator.validate_aiml_artifact(
        artifact, now=_iso(now_dt)
    )
    if central_errors:
        reasons.append(
            f"{label} fails the central closed-schema/lineage gate: "
            + "; ".join(central_errors)
        )
    if expiry_field is not None:
        try:
            expires_dt = central_validator._parse_timestamp(str(artifact[expiry_field]))
        except (KeyError, TypeError, ValueError):
            reasons.append(
                f"{label} carries no parseable {expiry_field}; an upstream receipt whose "
                "validity window cannot be derived is never in hand (fail-closed)"
            )
        else:
            if expires_dt <= now_dt:
                reasons.append(
                    f"{label} expired at {artifact[expiry_field]} (now {_iso(now_dt)}); "
                    "§3.1a requires the bound receipt to be in hand AND unexpired"
                )
    return reasons


def _static_precheck_reasons(
    core: dict[str, Any],
    *,
    phase: str,
    target_class: str,
    now_dt: datetime,
    s2_4_install_effect_receipt: Any,
    loader_closure_observation: Any,
    s2_4_recovery_clear: Any,
    install_lock_free: Any,
    s2_1_drill_receipt: Any,
    pre_drill_attestation: Any,
) -> list[str]:
    """§3.1 靜態 precheck(零 driver 接觸)。任一缺席/不符即 typed reason。"""

    reasons: list[str] = []
    # a. S2.4 APPLIED_INACTIVE receipt digest 綁定(#36 精神:綁 exact artifact 非名字;
    #    P1-2:self_digest 就地重算,自報 digest 的替身 stub 一律拒)。
    if not (
        isinstance(s2_4_install_effect_receipt, dict)
        and s2_4_install_effect_receipt.get("status") == "APPLIED_INACTIVE"
        and _bound_artifact_digest_ok(
            s2_4_install_effect_receipt, core.get("s2_4_install_effect_receipt_digest")
        )
    ):
        reasons.append(
            "S2.5 precheck: the exact s2_4_install_effect_receipt_v1(status="
            "APPLIED_INACTIVE) bound by the core digest is not in hand or its "
            "self_digest does not re-derive (a self-reported digest is never trusted; "
            "fail-closed)"
        )
    else:
        # Codex-4:digest 綁定之後,那份 receipt 本身也必須過中央閘且未過期。
        reasons.extend(
            _upstream_receipt_gate_reasons(
                s2_4_install_effect_receipt,
                now_dt=now_dt,
                schema_version="s2_4_install_effect_receipt_v1",
                label="S2.5 precheck: the bound s2_4_install_effect_receipt_v1",
                expiry_field="expires_at",
            )
        )
    # b. native-loader closure 重驗(§8.1:S2.5A 於 start 前重跑)。
    observed_closure = (
        loader_closure_observation.get("native_loader_closure_digest")
        if isinstance(loader_closure_observation, dict)
        else None
    )
    if observed_closure != core.get("native_loader_closure_digest"):
        reasons.append(
            "S2.5 precheck: the re-derived native-loader closure digest does not equal "
            "the base manifest closure (any new path or changed byte fails closed)"
        )
    # c. S2.4 recovery clear + install lock free(#39/#7;lock 由真 flock 探測導出)。
    if s2_4_recovery_clear is not True:
        reasons.append(
            "S2_4_RECOVERY_UNRESOLVED: the S2.4 probe/PREPARE/APPLY journals hold "
            "non-terminal residue or an unresolved recovery; S2.5 must not start"
        )
    if install_lock_free is not True:
        reasons.append(
            "S2.5 precheck: the S2.4 install lock is held (or unproven-free); S2.5 must "
            "not start under a live install transaction"
        )
    if phase == "S2_5B_FINAL":
        if not (
            isinstance(s2_1_drill_receipt, dict)
            and str(s2_1_drill_receipt.get("status", "")).startswith("QUIESCED")
            and _bound_artifact_digest_ok(
                s2_1_drill_receipt, core.get("s2_1_drill_receipt_digest")
            )
        ):
            reasons.append(
                "S2.5B precheck: the exact quiesce_result_v1(status=QUIESCED_...) bound "
                "by s2_1_drill_receipt_digest is not in hand or its self_digest does not "
                "re-derive (the drill must have actually happened and restored)"
            )
        else:
            # Codex-4 的同形第二洞:drill receipt 也只被檢查過 status 前綴 + digest 三值鏈。
            reasons.extend(
                _upstream_receipt_gate_reasons(
                    s2_1_drill_receipt,
                    now_dt=now_dt,
                    schema_version="quiesce_result_v1",
                    label="S2.5B precheck: the bound quiesce_result_v1 drill receipt",
                    expiry_field=None,
                )
            )
        pre_drill_ok = (
            isinstance(pre_drill_attestation, dict)
            and pre_drill_attestation.get("schema_version")
            == "s2_5_running_attestation_v1"
            and _bound_artifact_digest_ok(
                pre_drill_attestation, core.get("pre_drill_attestation_digest")
            )
        )
        if pre_drill_ok:
            # P1-2:pre-drill 錨要過**全套**中央閘驗(含 RUNNING_ATTESTED 的 attestor
            # 驗簽路徑與新鮮窗)——digest 綁定只證 bytes,不證這份 attestation 站得住。
            central_errors = central_validator.validate_aiml_artifact(
                pre_drill_attestation, now=_iso(now_dt)
            )
            if central_errors:
                pre_drill_ok = False
        if pre_drill_ok:
            status = pre_drill_attestation.get("status")
            if target_class == "production":
                # production lane 的 S2.5B 只可錨在真 attested 的 production S2.5A 上;
                # simulated 的 SOURCE_SIMULATION_PASS 錨永不解鎖 production final。
                if not (
                    status == S2_5_STATUS_RUNNING_ATTESTED
                    and pre_drill_attestation.get("target_class") == "production"
                ):
                    pre_drill_ok = False
            elif status not in {
                S2_5_STATUS_RUNNING_ATTESTED, S2_5_STATUS_SIMULATION_PASS
            }:
                pre_drill_ok = False
        if not pre_drill_ok:
            reasons.append(
                "S2.5B precheck: the exact S2.5A s2_5_running_attestation_v1 bound by "
                "pre_drill_attestation_digest is not in hand, fails the central gate, "
                "or is not an admissible anchor for this lane (production requires "
                "RUNNING_ATTESTED on a production target; a simulated anchor never "
                "unlocks a production final)"
            )
    return reasons


def _authorization_reasons(
    intent: dict[str, Any], authorization: Any, replay_ledger: Any, *, now_dt: datetime
) -> list[str]:
    reasons = attestation.verify_s2_5_operator_permit(
        authorization, intent, now=now_dt
    )
    replay = attestation.derive_s2_5_replay_binding(
        authorization, replay_ledger, start_id=intent.get("start_id")
    )
    if replay["status"] != attestation.REPLAY_STATUS_VALID:
        reasons = reasons + replay["reasons"]
    return reasons


def _observe_and_build(
    *,
    core: dict[str, Any],
    observers: Any,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    """讀五維 + persistence + owner 訊號 + observer gate(全由獨立 verifier 面採集)。

    ``owner_fingerprint`` 在此**模組內**經 WP3 ``compute_owner_fingerprint`` 重算
    (E1#4):caller 供值只作交叉檢查,receipt 一律載模組導出值。
    """

    dimensions = observers.observe_running_dimensions()
    persistence = dict(observers.observe_enabled_persistence())
    persistence.setdefault("reboot_survival_observed", None)
    gate = attestation.build_observer_gate(
        verifier_node_id=observers.verifier_node_id,
        max_evidence_age_seconds=core["attestation_window"]["max_evidence_age_seconds"],
        oldest_evidence_at=observers.oldest_evidence_at(),
        evaluated_at=_iso(clock()),
    )
    return {
        "dimensions": dimensions,
        "persistence": persistence,
        "observer_gate": gate,
        "verdicts": s2_5_running_dimension_verdicts(dimensions),
        "owner_fingerprint": compute_owner_fingerprint(
            **dict(observers.observe_owner_signals())
        ),
    }


def _base_receipt(
    *,
    schema_version: str,
    adapter_id: str,
    status: str,
    intent: dict[str, Any],
    core: dict[str, Any],
    target_class: str,
    owner_fingerprint: str,
    observation: dict[str, Any],
    precheck: dict[str, bool],
    rollback_record: Any,
    applier_node: str,
    verifier_node: str,
    trusted_host_attestation: Any,
    evidence_class: str,
    started_at: str,
    completed_at: str,
    failure_reason: str | None,
) -> dict[str, Any]:
    max_age = core["attestation_window"]["max_evidence_age_seconds"]
    receipt: dict[str, Any] = {
        "schema_version": schema_version,
        "adapter_id": adapter_id,
        "status": status,
        "intent_id": intent["start_id"],
        "intent_digest": intent["self_digest"],
        "target_class": target_class,
        "target_host": core["target_host"],
        "unit_name": S2_5_UNIT_NAME,
        "owner_fingerprint": owner_fingerprint,
        "running_dimensions": observation["dimensions"],
        "enabled_persistence": observation["persistence"],
        "observer_gate": observation["observer_gate"],
        "precheck": dict(precheck),
        "rollback_record": rollback_record,
        "apply_actor_node": applier_node,
        "independent_verifier_node": verifier_node,
        "verifier_capture_digest": None,
        "trusted_host_attestation": trusted_host_attestation,
        "evidence_class": evidence_class,
        "boundary": {
            "production_started_by_source_lane": False,
            "production_running_attested_without_attestor": False,
            "fixture_impersonates_platform_attested": False,
            "nine_authorities_false": True,
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "evidence_expires_at": _iso(
            central_validator._parse_timestamp(completed_at)
            + timedelta(seconds=int(max_age))
        ),
        "failure_reason": _scrub_secret_text(failure_reason),
        "source_head": core["source_head"],
    }
    return receipt


def _seal(receipt: dict[str, Any], *, now_dt: datetime) -> tuple[dict[str, Any], list[str]]:
    receipt["self_digest"] = central_validator.artifact_self_digest(receipt)
    errors = central_validator.validate_aiml_artifact(receipt, now=_iso(now_dt))
    # §11.21/E2 F4:receipt 落盤/回傳前過 secret-like 掃描(簽章 armor 不在掃描形狀內)。
    errors = errors + _secret_scan_errors(receipt)
    return receipt, errors


def _build_rollback_receipt(
    *,
    kind: str,
    status: str,
    intent: dict[str, Any],
    core: dict[str, Any],
    pre_state: dict[str, Any],
    post_state: dict[str, Any],
    s2_4_inactive_prestate_digest: str | None,
    watchdog_last: Any,
    observed_at: str,
) -> dict[str, Any]:
    receipt = {
        "schema_version": "s2_5_rollback_drill_receipt_v1",
        "kind": kind,
        "status": status,
        "intent_id": intent["start_id"],
        "unit_name": S2_5_UNIT_NAME,
        "pre_state": dict(pre_state),
        "post_state": dict(post_state),
        "operation": {
            "kind": "systemd_stop_disable"
            if kind == "ROLLBACK_TO_DISABLED"
            else "systemd_reset_failed"
        },
        "s2_4_inactive_prestate_digest": s2_4_inactive_prestate_digest,
        "watchdog_last": watchdog_last,
        "observed_at": observed_at,
        "expires_at": _iso(
            central_validator._parse_timestamp(observed_at)
            + timedelta(seconds=int(core["attestation_window"]["max_evidence_age_seconds"]))
        ),
        "source_head": core["source_head"],
    }
    receipt["self_digest"] = central_validator.artifact_self_digest(receipt)
    return receipt


def _unit_state_from_show(properties: dict[str, str]) -> dict[str, Any]:
    return {
        "active_state": str(properties.get("ActiveState", "")),
        "unit_file_state": str(properties.get("UnitFileState", "")),
        "n_restarts": int(properties.get("NRestarts", "0") or 0),
        "invocation_id": str(properties.get("InvocationID", "")) or "none",
    }


def _common_gate(
    intent: Any,
    authorization: Any,
    driver: Any,
    *,
    phase: str,
    now: Any,
    replay_ledger: Any,
    target_class: str,
    recovery_state: S2_5RecoveryState | None,
    install_lock_probe: Any,
    precheck_inputs: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any], datetime]:
    """step 0-6 的共用閘。回 (提前終止的 verdict | None, 導出的 precheck 旗標, now)。"""

    now_dt = _resolve_now(now)
    precheck_flags = {
        "inactive_prestate_verified": False,
        "loader_closure_reverified": False,
        "s2_4_recovery_clear": False,
        "install_lock_free": False,
    }
    # step 0 —— recovery 閂。
    if recovery_state is not None and recovery_state.unresolved is not None:
        return (
            _verdict(
                S2_5_STATUS_RECOVERY_REQUIRED,
                [
                    "a prior S2.5 recovery is unresolved; no new lifecycle effect may "
                    f"start (blocked by {recovery_state.unresolved.get('start_id')})"
                ],
            ),
            precheck_flags,
            now_dt,
        )
    # step 1 —— intent 結構/身分(中央閘負責 core_digest/start_id/self_digest/新鮮窗)。
    if not isinstance(intent, dict):
        return (
            _verdict(S2_5_STATUS_REQUEST_REJECTED, ["s2_5 intent must be an object"]),
            precheck_flags,
            now_dt,
        )
    schema_errors = central_validator.validate_aiml_artifact(intent, now=_iso(now_dt))
    if schema_errors:
        return (
            _verdict(S2_5_STATUS_REQUEST_REJECTED, schema_errors),
            precheck_flags,
            now_dt,
        )
    core = intent["core"]
    # step 2 —— phase 綁定(apply_s2_5_start 只收 S2_5A_START;final 只收 S2_5B_FINAL)。
    if core["phase"] != phase:
        return (
            _verdict(
                S2_5_STATUS_REQUEST_REJECTED,
                [
                    f"this applier owns phase {phase} only; the intent declares "
                    f"{core['phase']!r} (phase substitution is rejected)"
                ],
            ),
            precheck_flags,
            now_dt,
        )
    if target_class not in S2_5_TARGET_CLASSES:
        return (
            _verdict(
                S2_5_STATUS_REQUEST_REJECTED,
                [f"unknown target_class {target_class!r} (closed enum)"],
            ),
            precheck_flags,
            now_dt,
        )
    # step 3 —— 靜態 precheck(零 driver 接觸)。install_lock_free 唯一由 **S2.4 install 鎖**
    # 的真 flock 探測導出(P1-5:caller 自報 boolean 不採信)。此處是 fail-fast:探測即釋放,
    # 護窗的是窗內(F2b)的重探 + lifecycle hold。
    install_lock_free, lock_reasons = derive_s2_4_install_lock_free(install_lock_probe)
    static_reasons = _static_precheck_reasons(
        core,
        phase=phase,
        target_class=target_class,
        now_dt=now_dt,
        install_lock_free=install_lock_free,
        **precheck_inputs,
    )
    if not install_lock_free:
        static_reasons = static_reasons + lock_reasons
    precheck_flags["loader_closure_reverified"] = not any(
        "native-loader" in reason for reason in static_reasons
    )
    precheck_flags["s2_4_recovery_clear"] = not any(
        "S2_4_RECOVERY_UNRESOLVED" in reason for reason in static_reasons
    )
    precheck_flags["install_lock_free"] = bool(install_lock_free)
    if static_reasons:
        status = (
            S2_5_STATUS_RECOVERY_REQUIRED
            if any("S2_4_RECOVERY_UNRESOLVED" in reason for reason in static_reasons)
            else S2_5_STATUS_REQUEST_REJECTED
        )
        return _verdict(status, static_reasons), precheck_flags, now_dt
    # step 4 —— 授權 + replay 消費綁定。
    authorization_reasons = _authorization_reasons(
        intent, authorization, replay_ledger, now_dt=now_dt
    )
    if authorization_reasons:
        return (
            _verdict(S2_5_STATUS_AUTHORIZATION_REJECTED, authorization_reasons),
            precheck_flags,
            now_dt,
        )
    # step 4b —— TTL 預算不等式(E1#2):不夠時間完成 start+rollback+safety 就不開始。
    budget = derive_ttl_budget_status(core, now=now_dt)
    if budget["status"] != "TTL_BUDGET_OK":
        return (
            _verdict(S2_5_STATUS_AUTHORIZATION_REJECTED, budget["reasons"]),
            precheck_flags,
            now_dt,
        )
    # step 5 —— intent 新鮮窗已由中央閘擋(step 1 傳了 now);此處不重複。
    # step 6 —— driver 缺席:reachable 但 authority-locked(零變更、零 driver 呼叫)。
    if driver is None:
        return (
            _verdict(
                S2_5_STATUS_PENDING,
                [
                    "S2.5 lifecycle is reachable but authority-locked: no host service "
                    "driver is present (Mac/source/test lane); "
                    "EXTERNAL_VERIFICATION_PENDING with zero mutation"
                ],
            ),
            precheck_flags,
            now_dt,
        )
    return None, precheck_flags, now_dt


def apply_s2_5_start(
    intent: Any,
    authorization: Any = None,
    driver: Any = None,
    *,
    now: Any = None,
    replay_ledger: Any = None,
    target_class: str = "simulated_harness",
    s2_4_install_effect_receipt: Any = None,
    s2_4_inactive_prestate: Any = None,
    loader_closure_observation: Any = None,
    s2_4_recovery_clear: Any = None,
    install_lock_probe: Any = None,
    lifecycle_lock: Any = None,
    recovery_state: S2_5RecoveryState | None = None,
    state_root: Path | None = None,
    observers: Any = None,
    owner_fingerprint: str | None = None,
    applier_node: str = "s2-5-start-applier",
    trusted_host_attestation: Any = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """S2.5A:initial ``enable --now`` + 五維 running attestation(§3;固定順序見模組 docstring)。"""

    outcome, precheck_flags, now_dt = _common_gate(
        intent, authorization, driver,
        phase="S2_5A_START",
        now=now,
        replay_ledger=replay_ledger,
        target_class=target_class,
        recovery_state=recovery_state,
        install_lock_probe=install_lock_probe,
        precheck_inputs={
            "s2_4_install_effect_receipt": s2_4_install_effect_receipt,
            "loader_closure_observation": loader_closure_observation,
            "s2_4_recovery_clear": s2_4_recovery_clear,
            "s2_1_drill_receipt": None,
            "pre_drill_attestation": None,
        },
    )
    if outcome is not None:
        return outcome
    core = intent["core"]
    clock = clock or (lambda: now_dt)
    # step 7 前置:driver 在場必須有 journal 面與獨立 observer/verifier。
    reconcile = reconcile_s2_5_journal(state_root)
    if reconcile["admits_new_work"] is not True:
        return _verdict(S2_5_STATUS_RECOVERY_REQUIRED, reconcile["reasons"])
    journal_path = s2_5_journal_path(state_root, intent["start_id"])
    ledger_path = s2_5_replay_ledger_path(state_root)
    if observers is None or not str(getattr(observers, "verifier_node_id", "")):
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            ["S2.5 requires an independent verifier observation surface (fail-closed)"],
        )
    if observers.verifier_node_id == applier_node:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            ["S2.5 verifier node must differ from the applier node"],
        )
    if not owner_fingerprint:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            [
                "S2.5 requires the WP3 owner fingerprint (compute_owner_fingerprint) "
                "before any lifecycle effect (fail-closed)"
            ],
        )
    # F3:取 hold 之前先證「兩個 lock 面是兩個資源」——同物件/同路徑代表 S2.4 install
    # 自由與 S2.5 窗互斥被同一把鎖充當,那正是 install_lock_free 曾經無意義的根因。
    separation_reasons = _lock_resource_separation_reasons(
        install_lock_probe, lifecycle_lock
    )
    if separation_reasons:
        return _verdict(S2_5_STATUS_REQUEST_REJECTED, separation_reasons)
    # P2-2:anchor-check→前態讀取→consume→persist→journal(APPLYING)整段持 hold-style
    # flock,release 在 finally——「探測即釋放」的 probe 只是 §3.1 的 fail-fast,護窗的是
    # 這裡的 hold(第二個 applier 在窗內一律 typed 拒,永不雙消費)。
    hold_ok, hold_reasons = acquire_s2_5_lifecycle_hold(lifecycle_lock)
    if not hold_ok:
        return _verdict(S2_5_STATUS_REQUEST_REJECTED, hold_reasons)
    try:
        # P1-3 head-anchor:journal/durable ledger 釘過的 head 必須被涵蓋(截斷/清空即拒)。
        anchor_reasons = _replay_ledger_anchor_reasons(
            journal_path, ledger_path, replay_ledger
        )
        if anchor_reasons:
            return _verdict(S2_5_STATUS_AUTHORIZATION_REJECTED, anchor_reasons)
        # 前態讀取(read-only):必須等於 S2.4 receipt 所證的 loaded/disabled/inactive。
        pre_properties = driver.show()
        pre_state = _unit_state_from_show(pre_properties)
        prestate_expected = (
            isinstance(s2_4_inactive_prestate, dict)
            and _unit_state_from_show({
                "ActiveState": s2_4_inactive_prestate.get("active_state", ""),
                "UnitFileState": s2_4_inactive_prestate.get("unit_file_state", ""),
                "NRestarts": str(s2_4_inactive_prestate.get("n_restarts", 0)),
                "InvocationID": s2_4_inactive_prestate.get("invocation_id", "none"),
            })
            == pre_state
            and pre_state["active_state"] == "inactive"
            and pre_state["unit_file_state"] == "disabled"
            and str(pre_properties.get("FragmentDigest", ""))
            == core["expected_unit_fragment_digest"]
            and str(pre_properties.get("DropInPaths", "")) == ""
            and str(pre_properties.get("NeedDaemonReload", "no")) == "no"
        )
        precheck_flags["inactive_prestate_verified"] = bool(prestate_expected)
        if not prestate_expected:
            return _verdict(
                S2_5_STATUS_REQUEST_REJECTED,
                [
                    "S2.5 precheck: the live unit pre-state does not equal the S2.4 "
                    "APPLIED_INACTIVE pre-state (loaded/disabled/inactive, exact fragment "
                    "digest, no drop-ins, no pending daemon-reload); refusing to start a "
                    "look-alike unit"
                ],
            )
        prestate_digest = central_validator.canonical_digest(dict(s2_4_inactive_prestate))
        started_at = _iso(clock())
        # §9.1:先 durable 消費 permit 並持久化 ledger,再寫 APPLYING(journal 同時釘
        # ledger head),之後才動 effect(§5.2 WAL 語義)。consume 在鎖下重導出 replay
        # binding——鎖窗外先驗過的裁決在此再驗一次,競態下的第二個消費是 typed 拒。
        consumed_at = started_at
        try:
            attestation.consume_s2_5_authorization(
                replay_ledger, authorization,
                start_id=intent["start_id"], consumed_at=consumed_at,
            )
        except ValueError as error:
            return _verdict(
                S2_5_STATUS_AUTHORIZATION_REJECTED,
                [
                    "s2_5 authorization consumption was refused under the lifecycle "
                    f"lock: {error}"
                ],
            )
        _persist_s2_5_replay_ledger(ledger_path, replay_ledger)
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="APPLYING",
            updated_at=started_at,
            replay_ledger_head=_replay_ledger_head(replay_ledger["entries"]),
        )
    finally:
        _release_s2_5_lifecycle_hold(lifecycle_lock)
    try:
        driver.enable_now()
    except Exception as error:  # noqa: BLE001 —— effect 失敗必走 rollback,絕不轉成功。
        rollback = _rollback_to_disabled(
            intent=intent, core=core, driver=driver, pre_state=pre_state,
            prestate_digest=prestate_digest, clock=clock,
        )
        _journal_transition(
            journal_path, start_id=intent["start_id"],
            state="TERMINAL_ROLLED_BACK"
            if rollback["status"] == "RESTORED_INACTIVE"
            else "RECOVERY_REQUIRED",
            updated_at=_iso(clock()),
        )
        if rollback["status"] != "RESTORED_INACTIVE" and recovery_state is not None:
            recovery_state.record(
                start_id=intent["start_id"],
                reasons=[
                    "start failed and rollback did not restore: "
                    + redact_driver_error(error)
                ],
            )
        return _verdict(
            S2_5_STATUS_ATTESTATION_FAILED
            if rollback["status"] == "RESTORED_INACTIVE"
            else S2_5_STATUS_RECOVERY_REQUIRED,
            [f"enable --now failed: {redact_driver_error(error)}"],
            rollback_receipt=rollback["receipt"],
        )
    # P1-1:effect 之後的**全部**觀測(五維/persistence/owner 訊號/observer-gate 時間解析)
    # 都在 try 內——任何例外都不得裸逸,例外臂走 rollback + journal terminal + recovery 閂。
    try:
        observation = _observe_and_build(core=core, observers=observers, clock=clock)
    except Exception as error:  # noqa: BLE001 —— 觀測炸掉=真實狀態不明,fail-closed。
        reasons = [
            "post-start observation raised and the runtime state is unproven: "
            + redact_driver_error(error)
        ]
        rollback = _rollback_to_disabled(
            intent=intent, core=core, driver=driver, pre_state=pre_state,
            prestate_digest=prestate_digest, clock=clock,
        )
        restored = rollback["status"] == "RESTORED_INACTIVE"
        _journal_transition(
            journal_path, start_id=intent["start_id"],
            state="TERMINAL_ROLLED_BACK" if restored else "RECOVERY_REQUIRED",
            updated_at=_iso(clock()),
        )
        if recovery_state is not None:
            recovery_state.record(start_id=intent["start_id"], reasons=reasons)
        return _verdict(
            S2_5_STATUS_ATTESTATION_FAILED if restored else S2_5_STATUS_RECOVERY_REQUIRED,
            reasons
            + ([] if restored else ["rollback-to-disabled did not restore the S2.4 pre-state"]),
            rollback_receipt=rollback["receipt"],
        )
    failing = sorted(
        name for name, ok in observation["verdicts"].items() if not ok
    )
    stale = observation["observer_gate"]["stale"] is not False
    # E1#4:owner_fingerprint 由模組重算(_observe_and_build);caller 供值僅交叉檢查。
    owner_mismatch = observation["owner_fingerprint"] != owner_fingerprint
    if failing or stale or owner_mismatch:
        rollback = _rollback_to_disabled(
            intent=intent, core=core, driver=driver, pre_state=pre_state,
            prestate_digest=prestate_digest, clock=clock,
        )
        terminal = (
            "TERMINAL_ROLLED_BACK"
            if rollback["status"] == "RESTORED_INACTIVE"
            else "RECOVERY_REQUIRED"
        )
        _journal_transition(
            journal_path, start_id=intent["start_id"], state=terminal,
            updated_at=_iso(clock()),
        )
        if failing:
            reasons = [f"running attestation failed on dimension(s): {failing}"]
        elif stale:
            reasons = ["observer/dead-man gate is stale; a PASS cannot be derived"]
        else:
            reasons = [
                "owner fingerprint cross-check failed: the module-recomputed WP3 "
                "compute_owner_fingerprint value differs from the caller-supplied claim"
            ]
        if rollback["status"] != "RESTORED_INACTIVE":
            if recovery_state is not None:
                recovery_state.record(start_id=intent["start_id"], reasons=reasons)
            return _verdict(
                S2_5_STATUS_RECOVERY_REQUIRED,
                reasons + ["rollback-to-disabled did not restore the S2.4 pre-state"],
                rollback_receipt=rollback["receipt"],
            )
        receipt = _base_receipt(
            schema_version="s2_5_running_attestation_v1",
            adapter_id="s2_5_runtime_start_adapter_v1",
            status=S2_5_STATUS_ATTESTATION_FAILED,
            intent=intent, core=core, target_class=target_class,
            owner_fingerprint=observation["owner_fingerprint"], observation=observation,
            precheck=precheck_flags, rollback_record=rollback["receipt"],
            applier_node=applier_node, verifier_node=observers.verifier_node_id,
            trusted_host_attestation=None,
            evidence_class="STRUCTURAL_ONLY",
            started_at=started_at, completed_at=_iso(clock()),
            failure_reason="; ".join(reasons),
        )
        receipt, errors = _seal(receipt, now_dt=now_dt)
        return _verdict(
            S2_5_STATUS_ATTESTATION_FAILED, reasons + errors, receipt=receipt,
            rollback_receipt=rollback["receipt"],
        )
    # 全維通過:成功語義按 lane 收斂(simulated/disposable 頂點是 SOURCE_SIMULATION_PASS)。
    completed_at = _iso(clock())
    if target_class == "production":
        attestation_errors = attestation.verify_s2_5_trusted_host_attestation(
            trusted_host_attestation,
            intent_digest=intent["self_digest"],
            running_dimensions=observation["dimensions"],
            observer_gate=observation["observer_gate"],
            now=now_dt,
            expected_kind="A",
        )
        status = (
            S2_5_STATUS_RUNNING_ATTESTED if not attestation_errors else S2_5_STATUS_PENDING
        )
        evidence_class = (
            "PLATFORM_OR_EXTERNAL_ATTESTED" if not attestation_errors else "STRUCTURAL_ONLY"
        )
        failure_reason = (
            None
            if not attestation_errors
            else "production running attestation is pending the trusted-host attestor: "
            + "; ".join(attestation_errors)
        )
        bound_attestation = trusted_host_attestation if not attestation_errors else None
    else:
        status = S2_5_STATUS_SIMULATION_PASS
        evidence_class = "LOCAL_REPRODUCIBLE"
        failure_reason = None
        bound_attestation = None
    receipt = _base_receipt(
        schema_version="s2_5_running_attestation_v1",
        adapter_id="s2_5_runtime_start_adapter_v1",
        status=status,
        intent=intent, core=core, target_class=target_class,
        owner_fingerprint=observation["owner_fingerprint"], observation=observation,
        precheck=precheck_flags, rollback_record=None,
        applier_node=applier_node, verifier_node=observers.verifier_node_id,
        trusted_host_attestation=bound_attestation,
        evidence_class=evidence_class,
        started_at=started_at, completed_at=completed_at,
        failure_reason=failure_reason,
    )
    receipt, errors = _seal(receipt, now_dt=now_dt)
    if errors:
        # 自產 receipt 過不了中央閘 = 實作缺陷,fail-closed 絕不回成功。
        return _verdict(S2_5_STATUS_ATTESTATION_FAILED, errors, receipt=receipt)
    _journal_transition(
        journal_path, start_id=intent["start_id"], state="TERMINAL_SUCCESS",
        updated_at=completed_at,
    )
    return _verdict(status, [], receipt=receipt)


def _rollback_to_disabled(
    *,
    intent: dict[str, Any],
    core: dict[str, Any],
    driver: Any,
    pre_state: dict[str, Any],
    prestate_digest: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    """失敗即 rollback-to-disabled(§8.3 末段):stop + disable + 驗證回 S2.4 前態。

    §5.3(PM 詮釋,2026-07-28):identity tuple(active_state/unit_file_state/
    stable_identity_match)不等 ⇒ ``NOT_RESTORED`` 誠實失敗;``n_restarts`` 漂移**記錄**
    於 receipt 的 ``watchdog_last``(``unexplained_restart_detected`` 反映),不阻
    ``RESTORED_INACTIVE``。
    """

    failure: str | None = None
    try:
        driver.stop()
        driver.disable()
    except Exception as error:  # noqa: BLE001
        failure = redact_driver_error(error)
    stable_identity_match = False
    try:
        post_properties = driver.show()
        post_state = _unit_state_from_show(post_properties)
        # stable identity:rollback 之後的 unit 仍是 exact fragment(無替身/無 drop-in)。
        stable_identity_match = (
            str(post_properties.get("FragmentDigest", ""))
            == core["expected_unit_fragment_digest"]
            and str(post_properties.get("DropInPaths", "")) == ""
        )
    except Exception as error:  # noqa: BLE001
        failure = failure or redact_driver_error(error)
        post_state = {
            "active_state": "unknown", "unit_file_state": "unknown",
            "n_restarts": 0, "invocation_id": "none",
        }
    restored = (
        failure is None
        and post_state["active_state"] == "inactive"
        and post_state["unit_file_state"] == "disabled"
        and post_state["active_state"] == pre_state["active_state"]
        and post_state["unit_file_state"] == pre_state["unit_file_state"]
        and stable_identity_match is True
    )
    # n_restarts 漂移(supervening restart during rollback)只記錄不阻 RESTORED_INACTIVE。
    watchdog_last = attestation.build_watchdog_last(
        n_restarts_before=int(pre_state.get("n_restarts", 0)),
        n_restarts_after=int(post_state.get("n_restarts", 0)),
        invocation_id_before=str(pre_state.get("invocation_id", "none")),
        invocation_id_after=str(post_state.get("invocation_id", "none")),
        last_lifecycle_operation_kind="systemd_stop_disable",
        authorized_operation_kind="systemd_stop_disable",
        watchdog_usec="none",
    )
    status = "RESTORED_INACTIVE" if restored else "NOT_RESTORED"
    receipt = _build_rollback_receipt(
        kind="ROLLBACK_TO_DISABLED",
        status=status,
        intent=intent,
        core=core,
        pre_state=pre_state,
        post_state=post_state,
        s2_4_inactive_prestate_digest=prestate_digest,
        watchdog_last=watchdog_last,
        observed_at=_iso(clock()),
    )
    return {"status": status, "receipt": receipt}


def apply_s2_5_final(
    intent: Any,
    authorization: Any = None,
    driver: Any = None,
    *,
    now: Any = None,
    replay_ledger: Any = None,
    target_class: str = "simulated_harness",
    s2_4_install_effect_receipt: Any = None,
    loader_closure_observation: Any = None,
    s2_4_recovery_clear: Any = None,
    install_lock_probe: Any = None,
    lifecycle_lock: Any = None,
    s2_1_drill_receipt: Any = None,
    pre_drill_attestation: Any = None,
    recovery_state: S2_5RecoveryState | None = None,
    state_root: Path | None = None,
    observers: Any = None,
    owner_fingerprint: str | None = None,
    applier_node: str = "s2-5-final-applier",
    trusted_host_attestation: Any = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """S2.5B:post-drill 五維再證 + **watchdog reset last**(§3;RESET 是最後一個 lifecycle 操作)。"""

    outcome, precheck_flags, now_dt = _common_gate(
        intent, authorization, driver,
        phase="S2_5B_FINAL",
        now=now,
        replay_ledger=replay_ledger,
        target_class=target_class,
        recovery_state=recovery_state,
        install_lock_probe=install_lock_probe,
        precheck_inputs={
            "s2_4_install_effect_receipt": s2_4_install_effect_receipt,
            "loader_closure_observation": loader_closure_observation,
            "s2_4_recovery_clear": s2_4_recovery_clear,
            "s2_1_drill_receipt": s2_1_drill_receipt,
            "pre_drill_attestation": pre_drill_attestation,
        },
    )
    if outcome is not None:
        return outcome
    core = intent["core"]
    clock = clock or (lambda: now_dt)
    reconcile = reconcile_s2_5_journal(state_root)
    if reconcile["admits_new_work"] is not True:
        return _verdict(S2_5_STATUS_RECOVERY_REQUIRED, reconcile["reasons"])
    journal_path = s2_5_journal_path(state_root, intent["start_id"])
    ledger_path = s2_5_replay_ledger_path(state_root)
    if observers is None or not str(getattr(observers, "verifier_node_id", "")):
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            ["S2.5 requires an independent verifier observation surface (fail-closed)"],
        )
    if observers.verifier_node_id == applier_node:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            ["S2.5 verifier node must differ from the applier node"],
        )
    if not owner_fingerprint:
        return _verdict(
            S2_5_STATUS_REQUEST_REJECTED,
            [
                "S2.5 requires the WP3 owner fingerprint (compute_owner_fingerprint) "
                "before any lifecycle effect (fail-closed)"
            ],
        )
    # F3:同 start——兩個 lock 面必須是兩個資源(守衛在取 hold 之前)。
    separation_reasons = _lock_resource_separation_reasons(
        install_lock_probe, lifecycle_lock
    )
    if separation_reasons:
        return _verdict(S2_5_STATUS_REQUEST_REJECTED, separation_reasons)
    # P2-2:與 apply_s2_5_start 同一條 hold-style 交易窗(anchor→前態→consume→persist→
    # journal),release 在 finally。
    hold_ok, hold_reasons = acquire_s2_5_lifecycle_hold(lifecycle_lock)
    if not hold_ok:
        return _verdict(S2_5_STATUS_REQUEST_REJECTED, hold_reasons)
    try:
        anchor_reasons = _replay_ledger_anchor_reasons(
            journal_path, ledger_path, replay_ledger
        )
        if anchor_reasons:
            return _verdict(S2_5_STATUS_AUTHORIZATION_REJECTED, anchor_reasons)
        # S2.5B 的 drill 之後前態:unit 必須 enabled/active(drill restore 成功的活實例)。
        pre_properties = driver.show()
        pre_state = _unit_state_from_show(pre_properties)
        precheck_flags["inactive_prestate_verified"] = True  # S2.5B 消費 restore 後的活前態。
        if not (
            pre_state["active_state"] == "active"
            and pre_state["unit_file_state"] == "enabled"
            and str(pre_properties.get("FragmentDigest", ""))
            == core["expected_unit_fragment_digest"]
        ):
            return _verdict(
                S2_5_STATUS_REQUEST_REJECTED,
                [
                    "S2.5B precheck: the post-drill unit is not the restored active/enabled "
                    "instance bound to the exact fragment digest (fail-closed)"
                ],
            )
        started_at = _iso(clock())
        try:
            attestation.consume_s2_5_authorization(
                replay_ledger, authorization,
                start_id=intent["start_id"], consumed_at=started_at,
            )
        except ValueError as error:
            return _verdict(
                S2_5_STATUS_AUTHORIZATION_REJECTED,
                [
                    "s2_5 authorization consumption was refused under the lifecycle "
                    f"lock: {error}"
                ],
            )
        _persist_s2_5_replay_ledger(ledger_path, replay_ledger)
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="APPLYING",
            updated_at=started_at,
            replay_ledger_head=_replay_ledger_head(replay_ledger["entries"]),
        )
    finally:
        _release_s2_5_lifecycle_hold(lifecycle_lock)
    # 五維再證(drill 之後的新 PID/InvocationID;stable identity 的比對折在觀測面)。
    # P1-1:觀測例外不得裸逸——journal terminal + typed 失敗(S2.5B 無 rollback 語義)。
    try:
        observation = _observe_and_build(core=core, observers=observers, clock=clock)
    except Exception as error:  # noqa: BLE001
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="TERMINAL_FAILED",
            updated_at=_iso(clock()),
        )
        return _verdict(
            S2_5_STATUS_ATTESTATION_FAILED,
            [
                "post-drill observation raised and the runtime state is unproven: "
                + redact_driver_error(error)
            ],
        )
    failing = sorted(name for name, ok in observation["verdicts"].items() if not ok)
    stale = observation["observer_gate"]["stale"] is not False
    owner_mismatch = observation["owner_fingerprint"] != owner_fingerprint
    if failing or stale or owner_mismatch:
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="TERMINAL_FAILED",
            updated_at=_iso(clock()),
        )
        if failing:
            reasons = [f"final attestation failed on dimension(s): {failing}"]
        elif stale:
            reasons = ["observer/dead-man gate is stale; a PASS cannot be derived"]
        else:
            reasons = [
                "owner fingerprint cross-check failed: the module-recomputed WP3 "
                "compute_owner_fingerprint value differs from the caller-supplied claim"
            ]
        return _verdict(S2_5_STATUS_ATTESTATION_FAILED, reasons)
    # watchdog reset **last**:最後一個 lifecycle 操作是本 phase 的 reset 本身(§3/O-2)。
    try:
        driver.reset_failed()
    except Exception as error:  # noqa: BLE001
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="RECOVERY_REQUIRED",
            updated_at=_iso(clock()),
        )
        if recovery_state is not None:
            recovery_state.record(
                start_id=intent["start_id"],
                reasons=[f"reset-failed failed: {redact_driver_error(error)}"],
            )
        return _verdict(
            S2_5_STATUS_RECOVERY_REQUIRED,
            [f"watchdog reset failed: {redact_driver_error(error)}"],
        )
    # P1-1:reset 之後的觀測/導出也不得裸逸——reset 已發生,乾淨與否未證 ⇒ RECOVERY。
    try:
        post_reset = observers.observe_post_reset()
        watchdog_last = attestation.build_watchdog_last(
            n_restarts_before=observation["dimensions"]["unit"]["n_restarts_baseline"],
            n_restarts_after=int(post_reset.get("n_restarts", 0)),
            invocation_id_before=observation["dimensions"]["pid_cgroup"]["invocation_id"],
            invocation_id_after=str(post_reset.get("invocation_id", "none")),
            last_lifecycle_operation_kind=str(
                post_reset.get("last_lifecycle_operation_kind", "")
            ),
            authorized_operation_kind="systemd_reset_failed",
            watchdog_usec="none",
        )
    except Exception as error:  # noqa: BLE001
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="RECOVERY_REQUIRED",
            updated_at=_iso(clock()),
        )
        if recovery_state is not None:
            recovery_state.record(
                start_id=intent["start_id"],
                reasons=[
                    "post-reset observation raised; the reset outcome is unproven: "
                    + redact_driver_error(error)
                ],
            )
        return _verdict(
            S2_5_STATUS_RECOVERY_REQUIRED,
            [
                "post-reset observation raised; the reset outcome is unproven: "
                + redact_driver_error(error)
            ],
        )
    reset_clean = (
        watchdog_last["unexplained_restart_detected"] is False
        and watchdog_last["last_transition_matches_authorized_op"] is True
        and watchdog_last["n_restarts_after"] == 0
    )
    reset_receipt = _build_rollback_receipt(
        kind="WATCHDOG_RESET_LAST",
        status="RESET_CLEAN" if reset_clean else "FAILED",
        intent=intent,
        core=core,
        pre_state=pre_state,
        post_state={
            "active_state": str(post_reset.get("active_state", "active")),
            "unit_file_state": str(post_reset.get("unit_file_state", "enabled")),
            "n_restarts": int(post_reset.get("n_restarts", 0)),
            "invocation_id": str(post_reset.get("invocation_id", "none")),
        },
        s2_4_inactive_prestate_digest=None,
        watchdog_last=watchdog_last,
        observed_at=_iso(clock()),
    )
    stable_identity_match = bool(post_reset.get("stable_identity_match", False))
    completed_at = _iso(clock())
    if not reset_clean or not stable_identity_match:
        _journal_transition(
            journal_path, start_id=intent["start_id"], state="TERMINAL_FAILED",
            updated_at=completed_at,
        )
        return _verdict(
            S2_5_STATUS_ATTESTATION_FAILED,
            [
                "watchdog reset last is not clean or the stable identity drifted "
                "(supervening restart / unauthorized transition makes RESET_CLEAN "
                "unreachable)"
            ],
            rollback_receipt=reset_receipt,
        )
    if target_class == "production":
        attestation_errors = attestation.verify_s2_5_trusted_host_attestation(
            trusted_host_attestation,
            intent_digest=intent["self_digest"],
            running_dimensions=observation["dimensions"],
            observer_gate=observation["observer_gate"],
            now=now_dt,
            expected_kind="B",
        )
        status = (
            S2_5_STATUS_FINAL_ATTESTED if not attestation_errors else S2_5_STATUS_PENDING
        )
        evidence_class = (
            "PLATFORM_OR_EXTERNAL_ATTESTED" if not attestation_errors else "STRUCTURAL_ONLY"
        )
        failure_reason = (
            None
            if not attestation_errors
            else "production final attestation is pending the trusted-host attestor: "
            + "; ".join(attestation_errors)
        )
        bound_attestation = trusted_host_attestation if not attestation_errors else None
    else:
        status = S2_5_STATUS_SIMULATION_PASS
        evidence_class = "LOCAL_REPRODUCIBLE"
        failure_reason = None
        bound_attestation = None
    receipt = _base_receipt(
        schema_version="s2_5_final_attestation_v1",
        adapter_id="s2_5_final_attestation_adapter_v1",
        status=status,
        intent=intent, core=core, target_class=target_class,
        owner_fingerprint=observation["owner_fingerprint"], observation=observation,
        precheck=precheck_flags, rollback_record=None,
        applier_node=applier_node, verifier_node=observers.verifier_node_id,
        trusted_host_attestation=bound_attestation,
        evidence_class=evidence_class,
        started_at=started_at, completed_at=completed_at,
        failure_reason=failure_reason,
    )
    receipt["s2_1_drill_receipt_digest"] = core["s2_1_drill_receipt_digest"]
    receipt["pre_drill_attestation_digest"] = core["pre_drill_attestation_digest"]
    receipt["watchdog_last"] = watchdog_last
    receipt["watchdog_reset_receipt_digest"] = reset_receipt["self_digest"]
    receipt["stable_identity_match"] = stable_identity_match
    receipt, errors = _seal(receipt, now_dt=now_dt)
    if errors:
        return _verdict(S2_5_STATUS_ATTESTATION_FAILED, errors, receipt=receipt)
    _journal_transition(
        journal_path, start_id=intent["start_id"], state="TERMINAL_SUCCESS",
        updated_at=completed_at,
    )
    return _verdict(status, [], receipt=receipt, reset_receipt=reset_receipt)

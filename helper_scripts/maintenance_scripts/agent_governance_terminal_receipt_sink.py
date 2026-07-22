"""Disposable WORM terminal-receipt append Adapter for AIML LR0B (S1.2).

This Adapter is the one concrete component-effect Adapter delivered by S1.2: it
proves the ``terminal_receipt_sink_v1`` WORM append mechanism against a **local
content-addressed, immutable-after-commit store** in a throwaway directory, with
real OS semantics (``os.link`` atomic commit + idempotency dedup, ``chmod 0o444``
immutable-after-write) and an **independent** readback ACK by a distinct actor.

S1.2 is ``DISPOSABLE_ONLY``: ``target_class`` must be
``disposable_local_worm_emulation`` (``external_worm`` is rejected fail-closed),
no real external WORM destination is contacted, no network I/O happens, and the
real S3-Object-Lock / append-only bucket binding is deferred to S8.6, which
consumes this contract.

Stdlib only at import (``os``/``hashlib``/``json``/``uuid``/``tempfile``/
``pathlib``/``datetime``/``re``/``functools``) so the central AIML validator can
import it for delegated validation without any third-party dependency.  The
Adapter deliberately injects NO routable ``route_task`` node and NO
``closure_packet_v1`` effect binding (both are live-consumption seams for S8.6);
it self-validates via its own tests and the central validator's ``SCHEMA_FILES``
dispatch, exactly as the S1.1 ``pg_readonly`` Adapter self-validates.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any


ADAPTER_ID = "terminal_receipt_sink_adapter_v1"
SINK_ID = "terminal_receipt_sink_v1"
INTENT_SCHEMA_VERSION = "terminal_receipt_append_intent_v1"
RESULT_SCHEMA_VERSION = "terminal_receipt_append_result_v1"
READBACK_SCHEMA_VERSION = "terminal_receipt_readback_ack_v1"

DESTINATION_CLASS = "EXTERNAL_IMMUTABLE_WORM"
# S1.2 只接受 disposable 本地 WORM 模擬;external_worm 一律 fail-closed 拒絕。
DISPOSABLE_TARGET_CLASS = "disposable_local_worm_emulation"
TARGET_CLASSES = frozenset({"disposable_local_worm_emulation", "external_worm"})

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = Path(__file__).resolve()
SCHEMA_DIR = REPO_ROOT / "program_code/ml_training/schemas/aiml_gate_receipts"
INTENT_SCHEMA_PATH = SCHEMA_DIR / "terminal_receipt_append_intent_v1.schema.json"
RESULT_SCHEMA_PATH = SCHEMA_DIR / "terminal_receipt_append_result_v1.schema.json"
READBACK_SCHEMA_PATH = SCHEMA_DIR / "terminal_receipt_readback_ack_v1.schema.json"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
# committed record 的合法相對 locator 形狀:records/<64hex>.record(與
# _record_relative_locator 同構)。readback 與 result 驗證皆以此形狀拒絕越界 locator
# (絕對路徑、.. 逃逸、非 digest 檔名),防 store-escape 任意讀檔。
RECORD_LOCATOR_RE = re.compile(r"^records/[0-9a-f]{64}\.record$")

# payload_binding / idempotency 欄位逐字複製自凍結的 S0.3 sink 契約
# (terminal_receipt_sink_v1.schema.json 的 payload_binding_fields /
# idempotency_key_fields),使 Adapter 與凍結契約無法漂移;drift 由測試強制核對。
PAYLOAD_BINDING_FIELDS = (
    "final_source_head",
    "landing_scope_id",
    "learning_runtime_digest",
    "terminal_payload_digest",
    "terminal_state",
)
IDEMPOTENCY_KEY_FIELDS = ("landing_scope_id", "terminal_state", "terminal_payload_digest")

# terminal_receipt_type 與 terminal_state 的一一對應;S1.2 的 disposable 證明使用
# disposable_proof_payload_v1 / DISPOSABLE_PROOF 這對 stand-in。
TERMINAL_TYPE_TO_STATE = {
    "aiml_module_landed_for_trading_receipt_v1": "MODULE_LANDED_FOR_TRADING",
    "aiml_platform_no_candidate_receipt_v1": "PLATFORM_NO_CANDIDATE",
    "disposable_proof_payload_v1": "DISPOSABLE_PROOF",
}
TERMINAL_STATES = frozenset(TERMINAL_TYPE_TO_STATE.values())

APPEND_STATUSES = frozenset(
    {"APPENDED", "IDEMPOTENT_DEDUP", "ROLLED_BACK_INTERRUPTED", "FAILED"}
)
# 已 commit(唯一不可變 record)的兩種狀態;其餘兩種不得 commit 任何 record。
COMMITTED_STATUSES = frozenset({"APPENDED", "IDEMPOTENT_DEDUP"})

# 一次性 record 的 immutable 權限位:committed 後 chmod 0o444。
IMMUTABLE_RECORD_MODE = 0o444
# intent 授權窗上限(4 小時)與證據新鮮度窗上限(1 小時,對齊 disposable 證明)。
INTENT_TTL_CEILING_SECONDS = 4 * 3600
EVIDENCE_TTL_SECONDS = 3600

REQUIRED_HARD_STOPS = frozenset({
    "disposable local WORM emulation only; no real external WORM destination contact",
    "no production terminal receipt append; no network I/O",
    "no live/mainnet authority expansion; no order/broker/decision-lease effect",
})

# 對序列化 intent/result/ack 做的機密掃描;沿用
# aiml_gate_receipt_validator.GITHUB_SECRET_LIKE_RE 風格(WORM payload 僅攜帶
# 非機密 digest/fingerprint,此掃描為 fail-closed 防禦)。
WORM_SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})"
    r"|(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"private[_-]?key)\s*[:=]"
    r"|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}",
    re.IGNORECASE,
)
SECRET_PATTERNS_CHECKED = (
    "auth_scheme_token",
    "credential_assignment",
    "github_token",
)

INTENT_FIELDS = frozenset({
    "schema_version", "intent_id", "sink_id", "destination_class", "target_class",
    "terminal_receipt_type", "payload_binding", "idempotency_key", "append_actor_id",
    "approved_by", "approved_at", "expires_at", "hard_stops", "typed_confirm",
    "intent_digest",
})
RESULT_FIELDS = frozenset({
    "schema_version", "sink_id", "intent_id", "intent_digest", "append_status",
    "record_locator", "persisted_payload_digest", "idempotency_key", "append_actor_id",
    "immutable_after_write", "started_at", "completed_at", "evidence_expires_at",
    "failure_reason", "result_digest",
})
READBACK_FIELDS = frozenset({
    "schema_version", "sink_id", "intent_id", "result_digest", "readback_verifier_id",
    "read_record_locator", "readback_payload_digest", "ack", "same_actor_violation",
    "observed_at", "expires_at", "ack_digest",
})


class SecretLeakageError(RuntimeError):
    """Raised when a would-be intent/result/ack carries secret-like content.

    Fail-closed: the Adapter refuses to serialize any artifact that would leak a
    credential rather than emit it with the secret bound.
    """


class WormStoreError(RuntimeError):
    """Raised when the disposable WORM store cannot be used safely."""


# 延遲匯入的 agent_governance_schema.schema_subset_errors;central validator 已把
# helper_scripts/maintenance_scripts 放進 sys.path,測試亦然。
from agent_governance_schema import schema_subset_errors  # noqa: E402


# --------------------------------------------------------------------------- #
# canonical digest / time helpers (mirror agent_governance_pg_readonly_identity)
# --------------------------------------------------------------------------- #
def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _plus_seconds(iso: str, seconds: int) -> str:
    return (_parse_time(iso) + timedelta(seconds=seconds)).isoformat()


@lru_cache(maxsize=1)
def _intent_schema() -> dict[str, Any]:
    return json.loads(INTENT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _result_schema() -> dict[str, Any]:
    return json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _readback_schema() -> dict[str, Any]:
    return json.loads(READBACK_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def source_sha256() -> str:
    """Return the sha256 identity of this Adapter module source."""

    return _file_sha256(SOURCE_PATH)


def terminal_payload_digest(payload: Any) -> str:
    """Return the canonical sha256 of a terminal payload object."""

    return _sha256_bytes(_canonical_bytes(payload))


def terminal_receipt_idempotency_key(payload_binding: dict[str, Any]) -> str:
    """Derive the idempotency key from the frozen-contract idempotency fields."""

    projection = {field: payload_binding.get(field) for field in IDEMPOTENCY_KEY_FIELDS}
    return _sha256_bytes(_canonical_bytes(projection))


def terminal_receipt_intent_digest(intent: dict[str, Any]) -> str:
    """Hash every intent field except the self-referential ``intent_digest``."""

    unsigned = {key: value for key, value in intent.items() if key != "intent_digest"}
    return _sha256_bytes(_canonical_bytes(unsigned))


def terminal_receipt_result_digest(result: dict[str, Any]) -> str:
    """Hash every result field except the self-referential ``result_digest``."""

    unsigned = {key: value for key, value in result.items() if key != "result_digest"}
    return _sha256_bytes(_canonical_bytes(unsigned))


def terminal_receipt_ack_digest(ack: dict[str, Any]) -> str:
    """Hash every readback-ack field except the self-referential ``ack_digest``."""

    unsigned = {key: value for key, value in ack.items() if key != "ack_digest"}
    return _sha256_bytes(_canonical_bytes(unsigned))


def _typed_confirm(landing_scope_id: Any, terminal_state: Any, intent_id: Any) -> str:
    return f"terminal-append:{landing_scope_id}:{terminal_state}:{intent_id}"


# --------------------------------------------------------------------------- #
# secret scan
# --------------------------------------------------------------------------- #
def _contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return WORM_SECRET_LIKE_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_secret_like(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_secret_like(key) or _contains_secret_like(item)
            for key, item in value.items()
        )
    return False


def _guard_no_secret(payload: Any) -> None:
    # fail-closed:任何機密樣態即拒絕序列化,絕不發出帶密的 intent/result/ack。
    if _contains_secret_like(payload):
        raise SecretLeakageError("terminal receipt payload carries secret-like content")


# --------------------------------------------------------------------------- #
# intent builder
# --------------------------------------------------------------------------- #
def build_terminal_receipt_append_intent(
    *,
    intent_id: str,
    terminal_receipt_type: str,
    final_source_head: str,
    landing_scope_id: str,
    learning_runtime_digest: str,
    terminal_payload_digest: str,
    append_actor_id: str,
    approved_by: str,
    approved_at: str,
    expires_at: str,
    target_class: str = DISPOSABLE_TARGET_CLASS,
    hard_stops: list[str] | None = None,
) -> dict[str, Any]:
    """Build the canonical, self-hashed ``terminal_receipt_append_intent_v1``.

    ``idempotency_key`` and ``typed_confirm`` are DERIVED (never caller-supplied):
    the key from the frozen idempotency fields, the confirm string from
    scope/state/intent.  ``terminal_state`` is derived from
    ``terminal_receipt_type``.  Fail-closed on an unknown type, a non-digest
    binding, ``external_worm`` target, or any secret-like content.
    """

    if terminal_receipt_type not in TERMINAL_TYPE_TO_STATE:
        raise ValueError(f"terminal_receipt_type is not recognized: {terminal_receipt_type!r}")
    if target_class not in TARGET_CLASSES:
        raise ValueError(f"target_class is not recognized: {target_class!r}")
    if not isinstance(intent_id, str) or len(intent_id) < 8:
        raise ValueError("intent_id must be a string of at least 8 characters")
    if not HEAD_RE.fullmatch(str(final_source_head)):
        raise ValueError("final_source_head must be a 40-hex git head")
    for name, digest in (
        ("landing_scope_id", landing_scope_id),
        ("learning_runtime_digest", learning_runtime_digest),
        ("terminal_payload_digest", terminal_payload_digest),
    ):
        if not DIGEST_RE.fullmatch(str(digest)):
            raise ValueError(f"{name} must be a sha256 digest")

    terminal_state = TERMINAL_TYPE_TO_STATE[terminal_receipt_type]
    payload_binding = {
        "final_source_head": final_source_head,
        "landing_scope_id": landing_scope_id,
        "learning_runtime_digest": learning_runtime_digest,
        "terminal_payload_digest": terminal_payload_digest,
        "terminal_state": terminal_state,
    }
    intent: dict[str, Any] = {
        "schema_version": INTENT_SCHEMA_VERSION,
        "intent_id": intent_id,
        "sink_id": SINK_ID,
        "destination_class": DESTINATION_CLASS,
        "target_class": target_class,
        "terminal_receipt_type": terminal_receipt_type,
        "payload_binding": payload_binding,
        "idempotency_key": terminal_receipt_idempotency_key(payload_binding),
        "append_actor_id": append_actor_id,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "expires_at": expires_at,
        "hard_stops": sorted(REQUIRED_HARD_STOPS) if hard_stops is None else list(hard_stops),
        "typed_confirm": _typed_confirm(landing_scope_id, terminal_state, intent_id),
        "intent_digest": "sha256:" + "0" * 64,
    }
    _guard_no_secret(intent)
    intent["intent_digest"] = terminal_receipt_intent_digest(intent)
    return intent


# --------------------------------------------------------------------------- #
# disposable WORM-emulation store (real OS semantics; no external service)
# --------------------------------------------------------------------------- #
def _record_relative_locator(idempotency_key: str) -> str:
    # content-address key:以 idempotency_key 的 hex 段為檔名,records/<hex>.record。
    if not DIGEST_RE.fullmatch(str(idempotency_key)):
        raise WormStoreError("idempotency_key must be a sha256 digest")
    return f"records/{idempotency_key.split(':', 1)[1]}.record"


def _quiet_unlink(path: Path) -> None:
    try:
        path.unlink()
    except OSError:  # pragma: no cover - best-effort tmp cleanup
        pass


def _read_record_bytes_no_symlink(path: Path) -> bytes:
    # 以 O_NOFOLLOW 開檔:record 若為 symlink 則拒絕跟隨,避免被導向 store 外的檔案。
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def new_disposable_store_dir(*, prefix: str = "aiml_worm_store_") -> str:
    """Create a private (``0o700``) disposable WORM store dir owned by the Adapter.

    Centralizes the "store must not be group/world-readable" property so a caller
    never hands the Adapter a world-readable directory (defense-in-depth); the
    committed records inside are immutable-after-write ``0o444``.
    """

    # mkdtemp 本身即以 0o700 建立;顯式 chmod 為多一層保險(不信任 umask)。
    path = tempfile.mkdtemp(prefix=prefix)
    os.chmod(path, 0o700)
    return path


def apply_terminal_receipt_append(
    intent: dict[str, Any],
    *,
    store_dir: str,
    append_actor_id: str,
    terminal_payload: Any,
    simulate_interruption: bool = False,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    """Apply one WORM append against the disposable content-addressed store.

    Record-level transactional: serialize the payload, write to
    ``tmp/<uuid>`` (uncommitted), then atomically commit via
    ``os.link`` to ``records/<idempotency_key>.record``.  ``os.link`` raising
    ``FileExistsError`` on an existing key IS the idempotency dedup
    (``IDEMPOTENT_DEDUP``; no duplicate record).  On a fresh commit the record is
    ``chmod 0o444`` (immutable-after-write) and the tmp is unlinked.  An
    interrupted apply (``simulate_interruption``) leaves only an orphan tmp and
    commits no record, so the same key stays free and a retry re-appends cleanly.
    Nothing is mocked; no external WORM service is contacted.
    """

    if not isinstance(intent, dict):
        raise ValueError("intent must be an object")
    # 防禦(depth):disposable adapter 於 apply 時亦拒絕 external_worm,而非僅在 validate。
    if intent.get("target_class") != DISPOSABLE_TARGET_CLASS:
        raise WormStoreError(
            "apply refuses a non-disposable target_class (external_worm is rejected at apply)"
        )
    store = Path(store_dir)
    # 防禦(depth):disposable WORM store 必須是私有 0o700 目錄(group/other 不可存取),
    # 否則 committed 的 0o444 record 會因目錄可 traverse 而被 group/other 讀取。
    # 自建路徑:makedirs 後顯式 chmod 0o700(umask-proof,不信任 umask 給的 0o755);
    # 既有目錄:不替呼叫端「修正」,保留其模式交由下方 UNCONDITIONAL 斷言把關。
    store_preexisting = store.exists()
    os.makedirs(store, exist_ok=True)
    if not store_preexisting:
        os.chmod(store, 0o700)
    # UNCONDITIONAL 私有性斷言:確保目錄存在「之後」一律檢查,不再只在預先存在時檢查。
    # 任何 group/other 位即 fail-closed(既有 0o755 store 於此被拒;自建 store 已為 0o700)。
    store_mode = os.stat(store).st_mode
    if store_mode & 0o077:
        raise WormStoreError(
            "disposable WORM store dir must be private 0o700; got "
            f"{store_mode & 0o777:#o}"
        )
    tmp_dir = store / "tmp"
    records_dir = store / "records"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    records_dir.mkdir(parents=True, exist_ok=True)

    started = started_at or _utcnow_iso()
    idempotency_key = intent.get("idempotency_key")
    record_rel = _record_relative_locator(str(idempotency_key))
    record_path = store / record_rel

    payload_bytes = _canonical_bytes(terminal_payload)
    persisted_digest = _sha256_bytes(payload_bytes)
    payload_binding = intent.get("payload_binding") or {}
    completed = completed_at or _utcnow_iso()

    def _result(
        status: str, *, record_locator: str | None, persisted: str | None,
        immutable: bool, failure: str | None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "sink_id": SINK_ID,
            "intent_id": intent.get("intent_id"),
            "intent_digest": intent.get("intent_digest"),
            "append_status": status,
            "record_locator": record_locator,
            "persisted_payload_digest": persisted,
            "idempotency_key": idempotency_key,
            "append_actor_id": append_actor_id,
            "immutable_after_write": immutable,
            "started_at": started,
            "completed_at": completed,
            "evidence_expires_at": _plus_seconds(completed, EVIDENCE_TTL_SECONDS),
            "failure_reason": failure,
            "result_digest": "sha256:" + "0" * 64,
        }
        _guard_no_secret(result)
        result["result_digest"] = terminal_receipt_result_digest(result)
        return result

    # WORM record 不可變:序列化前先掃描 payload,任何機密樣態一律 fail-closed,絕不寫入
    # 任何 record(避免明文機密落入不可變 WORM record;與 receipts 的機密掃描對稱)。
    if _contains_secret_like(terminal_payload):
        return _result(
            "FAILED", record_locator=None, persisted=None, immutable=False,
            failure="terminal payload carries secret-like content; nothing committed",
        )
    # payload-hash binding:序列化 payload 的 digest 必須等於 intent 綁定的 digest。
    if persisted_digest != payload_binding.get("terminal_payload_digest"):
        return _result(
            "FAILED", record_locator=None, persisted=None, immutable=False,
            failure="terminal payload digest does not match intent payload_binding",
        )
    # append actor 必須等於已核准 intent 的 append_actor_id。
    if append_actor_id != intent.get("append_actor_id"):
        return _result(
            "FAILED", record_locator=None, persisted=None, immutable=False,
            failure="append actor differs from approved intent append_actor_id",
        )

    # 寫入未 commit 的 tmp/<uuid>。
    tmp_path = tmp_dir / uuid.uuid4().hex
    tmp_path.write_bytes(payload_bytes)

    if simulate_interruption:
        # 中斷發生在 atomic link 之前:留下 orphan tmp,絕不 commit 任何 record,
        # 同一 idempotency_key 保持空缺 ⇒ 可重試。WORM 從不「改寫」已 commit 的 record。
        return _result(
            "ROLLED_BACK_INTERRUPTED", record_locator=None, persisted=None,
            immutable=False,
            failure="apply interrupted before atomic commit; no record committed",
        )

    try:
        os.link(tmp_path, record_path)
    except FileExistsError:
        # idempotent dedup:key 已存在 ⇒ 不產生重複 record;回讀既有 record 的 digest。
        _quiet_unlink(tmp_path)
        try:
            existing_bytes = _read_record_bytes_no_symlink(record_path)
        except OSError:
            # 既有 record 為 symlink(O_NOFOLLOW→ELOOP)或不可讀:不佯稱去重,回結構化 FAILED
            # (與 readback 讀檔失敗的處理對稱;仍 fail-closed,絕不 commit 任何 record)。
            return _result(
                "FAILED", record_locator=None, persisted=None, immutable=False,
                failure=(
                    "existing idempotency-key record is not a regular readable file "
                    "(symlink / unreadable pre-seed detected); nothing committed"
                ),
            )
        existing_digest = _sha256_bytes(existing_bytes)
        # idempotency key 由 terminal_payload_digest 派生,故既有 record 的內容 digest 必須
        # 等於本次核准的 digest;不符即為內容替換/預植入 ⇒ fail-closed FAILED,不佯稱去重成功。
        if existing_digest != payload_binding.get("terminal_payload_digest"):
            return _result(
                "FAILED", record_locator=None, persisted=None, immutable=False,
                failure=(
                    "idempotency-key record content does not match the approved payload "
                    "digest (content substitution / pre-seed detected)"
                ),
            )
        return _result(
            "IDEMPOTENT_DEDUP", record_locator=record_rel, persisted=existing_digest,
            immutable=True, failure=None,
        )
    # commit 成功:chmod 0o444(immutable-after-write),移除 tmp。
    os.chmod(record_path, IMMUTABLE_RECORD_MODE)
    _quiet_unlink(tmp_path)
    return _result(
        "APPENDED", record_locator=record_rel, persisted=persisted_digest,
        immutable=True, failure=None,
    )


def readback_terminal_receipt(
    result: dict[str, Any],
    *,
    store_dir: str,
    readback_verifier_id: str,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Independently read back one committed record and ACK it.

    The ``readback_verifier_id`` MUST differ from the result's
    ``append_actor_id`` (the frozen contract's ``same_actor_allowed=false``): a
    same-actor readback sets ``same_actor_violation=true`` and refuses to ACK.
    A positive ACK requires the recomputed record-byte digest to equal the
    result's ``persisted_payload_digest``.
    """

    store = Path(store_dir)
    observed = observed_at or _utcnow_iso()
    append_actor = result.get("append_actor_id")
    same_actor_violation = readback_verifier_id == append_actor
    record_locator = result.get("record_locator")

    readback_digest: str | None = None
    ack = False
    read_locator: str | None = None
    # store-escape 防禦:record_locator 必須是 records/<64hex>.record 形狀(拒絕絕對路徑、
    # .. 逃逸、非 digest 檔名),再以 O_NOFOLLOW 開檔避免跟隨 symlink 讀到 store 外檔案。
    # 形狀不合即不讀任何檔:read_locator 留 None、ack 留 False(fail-closed)。
    if (
        not same_actor_violation
        and isinstance(record_locator, str)
        and RECORD_LOCATOR_RE.fullmatch(record_locator)
    ):
        record_path = store / record_locator
        read_locator = record_locator
        try:
            record_bytes: bytes | None = _read_record_bytes_no_symlink(record_path)
        except OSError:
            record_bytes = None
        if record_bytes is not None:
            readback_digest = _sha256_bytes(record_bytes)
            ack = readback_digest == result.get("persisted_payload_digest")

    ack_obj: dict[str, Any] = {
        "schema_version": READBACK_SCHEMA_VERSION,
        "sink_id": SINK_ID,
        "intent_id": result.get("intent_id"),
        "result_digest": result.get("result_digest"),
        "readback_verifier_id": readback_verifier_id,
        "read_record_locator": read_locator,
        "readback_payload_digest": readback_digest,
        "ack": ack,
        "same_actor_violation": same_actor_violation,
        "observed_at": observed,
        "expires_at": _plus_seconds(observed, EVIDENCE_TTL_SECONDS),
        "ack_digest": "sha256:" + "0" * 64,
    }
    _guard_no_secret(ack_obj)
    ack_obj["ack_digest"] = terminal_receipt_ack_digest(ack_obj)
    return ack_obj


def attempt_record_rewrite(record_path: str) -> dict[str, Any]:
    """Prove-negative helper: try to rewrite a committed 0o444 record.

    Returns a structured observation ``{attempted, immutable, observed_error}``.
    A committed record is expected to raise ``PermissionError`` (immutable), so
    ``immutable`` is ``True`` iff the write was refused.  Used by the disposable
    proof to record the immutability negative case; never mutates a committed
    record on success.
    """

    path = Path(record_path)
    try:
        with open(path, "ab") as handle:
            handle.write(b"tamper")
    except PermissionError as error:
        return {
            "attempted": "append bytes to a committed 0o444 record",
            "immutable": True,
            "observed_error": type(error).__name__,
        }
    # 若竟然寫入成功(非預期,例如以 root 執行),回報 immutable=False 供測試 fail-closed。
    return {
        "attempted": "append bytes to a committed 0o444 record",
        "immutable": False,
        "observed_error": None,
    }


# --------------------------------------------------------------------------- #
# validators (structural + integrity + freshness; not execution authenticity)
# --------------------------------------------------------------------------- #
def _fieldset_error(kind: str, value: dict[str, Any], expected: frozenset[str]) -> list[str]:
    if set(value) != expected:
        return [
            f"terminal receipt {kind} fields mismatch: "
            f"missing={sorted(expected - set(value))} extra={sorted(set(value) - expected)}"
        ]
    return []


def validate_terminal_receipt_append_intent(
    intent: Any, *, now: str | None = None
) -> list[str]:
    """Validate a WORM append intent: structure, target gate, derived bindings.

    ``target_class`` must be ``disposable_local_worm_emulation`` at the S1.2 gate
    (``external_worm`` rejected fail-closed).  ``idempotency_key`` and
    ``typed_confirm`` must equal their independently derived values;
    ``intent_digest`` must re-derive.  Freshness is checked only when ``now`` is
    supplied.
    """

    if not isinstance(intent, dict):
        return ["terminal receipt append intent must be an object"]
    schema = _intent_schema()
    errors = [
        f"terminal receipt append intent schema violation: {error}"
        for error in schema_subset_errors(intent, schema, schema)
    ]
    errors.extend(_fieldset_error("append intent", intent, INTENT_FIELDS))
    if intent.get("schema_version") != INTENT_SCHEMA_VERSION:
        errors.append("terminal receipt append intent schema_version is invalid")
    if intent.get("sink_id") != SINK_ID:
        errors.append("terminal receipt append intent sink_id is invalid")
    if intent.get("destination_class") != DESTINATION_CLASS:
        errors.append("terminal receipt append intent destination_class is invalid")
    if intent.get("target_class") != DISPOSABLE_TARGET_CLASS:
        errors.append(
            "terminal receipt append intent target_class must be "
            "disposable_local_worm_emulation (external_worm is rejected fail-closed "
            "at the S1.2 gate)"
        )
    receipt_type = intent.get("terminal_receipt_type")
    payload_binding = intent.get("payload_binding")
    if not isinstance(payload_binding, dict):
        errors.append("terminal receipt append intent payload_binding is invalid")
    else:
        state = payload_binding.get("terminal_state")
        if receipt_type in TERMINAL_TYPE_TO_STATE and (
            TERMINAL_TYPE_TO_STATE[receipt_type] != state
        ):
            errors.append(
                "terminal receipt type and payload_binding.terminal_state are inconsistent"
            )
        if intent.get("idempotency_key") != terminal_receipt_idempotency_key(payload_binding):
            errors.append(
                "terminal receipt idempotency_key is not derived from the payload_binding"
            )
        expected_confirm = _typed_confirm(
            payload_binding.get("landing_scope_id"), state, intent.get("intent_id")
        )
        if intent.get("typed_confirm") != expected_confirm:
            errors.append(
                "terminal receipt typed_confirm is not bound to scope/state/intent"
            )
    hard_stops = intent.get("hard_stops")
    if (
        not isinstance(hard_stops, list)
        or any(not isinstance(item, str) or not item for item in hard_stops)
        or not REQUIRED_HARD_STOPS.issubset(set(hard_stops))
    ):
        errors.append("terminal receipt append intent required hard stops are missing")
    if _contains_secret_like(intent):
        errors.append("terminal receipt append intent carries secret-like content")
    errors.extend(_validate_intent_times(intent, now=now))
    if intent.get("intent_digest") != terminal_receipt_intent_digest(intent):
        errors.append("terminal receipt intent_digest does not match the canonical intent")
    return errors


def _validate_intent_times(intent: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    try:
        approved = _parse_time(str(intent.get("approved_at", "")))
        expires = _parse_time(str(intent.get("expires_at", "")))
        if not approved < expires:
            errors.append("terminal receipt intent approved_at must precede expires_at")
        if expires - approved > timedelta(seconds=INTENT_TTL_CEILING_SECONDS):
            errors.append("terminal receipt intent TTL exceeds its ceiling")
        if now is not None:
            current = _parse_time(now)
            if not approved <= current < expires:
                errors.append("terminal receipt intent is not fresh")
    except (TypeError, ValueError):
        errors.append("terminal receipt intent timestamps are invalid")
    return errors


def validate_terminal_receipt_append_result(
    result: Any, *, intent: dict[str, Any] | None = None, now: str | None = None
) -> list[str]:
    """Validate a WORM append result: committed-vs-uncommitted invariants + binding.

    ``APPENDED``/``IDEMPOTENT_DEDUP`` must bind exactly one immutable
    content-addressed record; ``ROLLED_BACK_INTERRUPTED``/``FAILED`` must claim no
    record, no persisted digest, ``immutable_after_write=false`` and a
    ``failure_reason``.  When ``intent`` is supplied it is cross-bound.
    """

    if not isinstance(result, dict):
        return ["terminal receipt append result must be an object"]
    schema = _result_schema()
    errors = [
        f"terminal receipt append result schema violation: {error}"
        for error in schema_subset_errors(result, schema, schema)
    ]
    errors.extend(_fieldset_error("append result", result, RESULT_FIELDS))
    if result.get("schema_version") != RESULT_SCHEMA_VERSION:
        errors.append("terminal receipt append result schema_version is invalid")
    if result.get("sink_id") != SINK_ID:
        errors.append("terminal receipt append result sink_id is invalid")
    status = result.get("append_status")
    if status not in APPEND_STATUSES:
        errors.append("terminal receipt append result append_status is invalid")
    record_locator = result.get("record_locator")
    persisted = result.get("persisted_payload_digest")
    immutable = result.get("immutable_after_write")
    failure = result.get("failure_reason")
    if status in COMMITTED_STATUSES:
        if not isinstance(record_locator, str) or not RECORD_LOCATOR_RE.fullmatch(
            record_locator or ""
        ):
            errors.append(
                "committed terminal receipt result requires a records/<64hex>.record locator"
            )
        if not DIGEST_RE.fullmatch(str(persisted or "")):
            errors.append(
                "committed terminal receipt result requires a persisted_payload_digest"
            )
        if immutable is not True:
            errors.append(
                "committed terminal receipt result must be immutable_after_write=true"
            )
        if failure is not None:
            errors.append("committed terminal receipt result cannot carry a failure_reason")
    else:
        if record_locator is not None:
            errors.append(
                f"{status} terminal receipt result cannot claim a committed record_locator"
            )
        if persisted is not None:
            errors.append(
                f"{status} terminal receipt result cannot claim a persisted payload digest"
            )
        if immutable is not False:
            errors.append(
                f"{status} terminal receipt result must be immutable_after_write=false"
            )
        if not isinstance(failure, str) or not failure.strip():
            errors.append(f"{status} terminal receipt result requires a failure_reason")
    if isinstance(intent, dict):
        for field in ("intent_id", "intent_digest", "idempotency_key"):
            if result.get(field) != intent.get(field):
                errors.append(
                    f"terminal receipt result {field} is not bound to the intent"
                )
        if result.get("append_actor_id") != intent.get("append_actor_id"):
            errors.append("terminal receipt result append actor differs from the intent")
        # committed record 的 persisted digest 必須等於 intent 核准的 terminal_payload_digest
        # (idempotency key 由該 digest 派生,持久內容不得與核准 payload 脫鉤 → 防替換)。
        if status in COMMITTED_STATUSES:
            approved_digest = (intent.get("payload_binding") or {}).get(
                "terminal_payload_digest"
            )
            if result.get("persisted_payload_digest") != approved_digest:
                errors.append(
                    "terminal receipt result persisted digest is not bound to the "
                    "approved intent payload digest"
                )
    errors.extend(_validate_result_times(result, now=now))
    if _contains_secret_like(result):
        errors.append("terminal receipt append result carries secret-like content")
    if result.get("result_digest") != terminal_receipt_result_digest(result):
        errors.append("terminal receipt result_digest does not match the canonical result")
    return errors


def _validate_result_times(result: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    try:
        started = _parse_time(str(result.get("started_at", "")))
        completed = _parse_time(str(result.get("completed_at", "")))
        evidence = _parse_time(str(result.get("evidence_expires_at", "")))
        if not started <= completed:
            errors.append("terminal receipt result started_at must not follow completed_at")
        if not completed < evidence:
            errors.append(
                "terminal receipt result completed_at must precede evidence_expires_at"
            )
        if evidence - completed > timedelta(seconds=EVIDENCE_TTL_SECONDS):
            errors.append("terminal receipt result evidence TTL exceeds its ceiling")
        if now is not None:
            current = _parse_time(now)
            if not completed <= current < evidence:
                errors.append("terminal receipt result evidence is not fresh")
    except (TypeError, ValueError):
        errors.append("terminal receipt result timestamps are invalid")
    return errors


def validate_terminal_receipt_readback_ack(
    ack: Any, *, result: dict[str, Any] | None = None, now: str | None = None
) -> list[str]:
    """Validate an independent readback ACK: distinctness + payload-digest match.

    A positive ACK (``ack=true``) requires ``same_actor_violation=false``, a
    verifier distinct from the append actor, and a ``readback_payload_digest``
    equal to the result's ``persisted_payload_digest``.  A same-actor readback
    must set ``same_actor_violation=true`` and refuse to ACK.
    """

    if not isinstance(ack, dict):
        return ["terminal receipt readback ack must be an object"]
    schema = _readback_schema()
    errors = [
        f"terminal receipt readback ack schema violation: {error}"
        for error in schema_subset_errors(ack, schema, schema)
    ]
    errors.extend(_fieldset_error("readback ack", ack, READBACK_FIELDS))
    if ack.get("schema_version") != READBACK_SCHEMA_VERSION:
        errors.append("terminal receipt readback ack schema_version is invalid")
    if ack.get("sink_id") != SINK_ID:
        errors.append("terminal receipt readback ack sink_id is invalid")
    verifier = ack.get("readback_verifier_id")
    same_actor_violation = ack.get("same_actor_violation")
    acked = ack.get("ack")
    if isinstance(result, dict):
        for field in ("intent_id", "result_digest"):
            if ack.get(field) != result.get(field):
                errors.append(
                    f"terminal receipt readback {field} is not bound to the result"
                )
        # read_record_locator 若有值必須綁定 result 的 record_locator(不得聲稱讀了別的 record)。
        read_locator = ack.get("read_record_locator")
        if read_locator is not None and read_locator != result.get("record_locator"):
            errors.append(
                "terminal receipt readback read_record_locator is not bound to the "
                "result record"
            )
        append_actor = result.get("append_actor_id")
        # 獨立性由「綁定身分」推導,而非信任 caller 設定的 same_actor_violation 布林與裸字串
        # 比較:verifier 等於被綁定的 append actor 即為 same-actor。
        bound_same_actor = verifier == append_actor
        if bound_same_actor and same_actor_violation is not True:
            errors.append(
                "terminal receipt readback by the append actor must set "
                "same_actor_violation=true"
            )
        if not bound_same_actor and same_actor_violation is not False:
            errors.append(
                "terminal receipt readback same_actor_violation is inconsistent with "
                "the verifier identity"
            )
        if acked is True:
            # positive ACK:綁定 append actor 不得等於 verifier(不論 caller 布林),且必須讀到該 record。
            if bound_same_actor:
                errors.append(
                    "a positive terminal receipt readback ACK cannot be issued by the "
                    "bound append actor"
                )
            if read_locator != result.get("record_locator"):
                errors.append(
                    "a positive terminal receipt readback ACK must read the result record"
                )
    if acked is True:
        if same_actor_violation is not False:
            errors.append(
                "a positive terminal receipt readback ACK cannot be a same-actor violation"
            )
        if not DIGEST_RE.fullmatch(str(ack.get("readback_payload_digest") or "")):
            errors.append(
                "a positive terminal receipt readback ACK requires a readback_payload_digest"
            )
        if isinstance(result, dict) and ack.get("readback_payload_digest") != result.get(
            "persisted_payload_digest"
        ):
            errors.append(
                "terminal receipt readback payload digest does not match the persisted record"
            )
    if same_actor_violation is True and acked is not False:
        errors.append("a same-actor terminal receipt readback must refuse to ACK")
    errors.extend(_validate_ack_times(ack, now=now))
    if _contains_secret_like(ack):
        errors.append("terminal receipt readback ack carries secret-like content")
    if ack.get("ack_digest") != terminal_receipt_ack_digest(ack):
        errors.append("terminal receipt ack_digest does not match the canonical ack")
    return errors


def _validate_ack_times(ack: dict[str, Any], *, now: str | None) -> list[str]:
    errors: list[str] = []
    try:
        observed = _parse_time(str(ack.get("observed_at", "")))
        expires = _parse_time(str(ack.get("expires_at", "")))
        if not observed < expires:
            errors.append("terminal receipt readback observed_at must precede expires_at")
        if expires - observed > timedelta(seconds=EVIDENCE_TTL_SECONDS):
            errors.append("terminal receipt readback TTL exceeds its ceiling")
        if now is not None:
            current = _parse_time(now)
            if not observed <= current < expires:
                errors.append("terminal receipt readback ack is not fresh")
    except (TypeError, ValueError):
        errors.append("terminal receipt readback ack timestamps are invalid")
    return errors

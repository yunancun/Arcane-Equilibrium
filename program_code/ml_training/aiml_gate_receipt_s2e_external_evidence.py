"""Independent external evidence gates for formal S2E launch receipts."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import agent_governance_aiml_trusted_host as trusted_host
from agent_governance_schema import schema_subset_errors
from aiml_gate_receipt_schema_core import (
    _contains_github_secret_like_content,
    _load_schema,
    canonical_digest,
)


LAUNCH_ID = "S2E-LW1-LW5"
DURABILITY_ANCHOR_SCHEMA = "s2e_durability_anchor_attestation_v1"
PREDECESSOR_REGISTRY_SCHEMA = "s2e_predecessor_registry_attestation_v1"
DURABILITY_ANCHOR_IDENTITY = (
    "aiml-s2e-durability-anchor-attestor-v1"
)
DURABILITY_ANCHOR_NAMESPACE = (
    "arcane-equilibrium-aiml-s2e-durability-anchor"
)
PREDECESSOR_REGISTRY_IDENTITY = (
    "aiml-s2e-predecessor-registry-attestor-v1"
)
PREDECESSOR_REGISTRY_NAMESPACE = (
    "arcane-equilibrium-aiml-s2e-predecessor-registry"
)
# 這組 scheme 擋的是 fixture／stub 證據冒充真實 attestation,與「證據在不在本機」
# 無關;Tier 1 的 anchor 本來就是 host-local capability,仍必須擋掉測試替身。
LOCAL_EVIDENCE_LOCATOR_SCHEMES = frozenset({
    "fixture", "memory", "local", "test",
})
OFFHOST_REPLICA_READBACK_SCHEMA = "s2e_offhost_replica_readback_v1"
OFFHOST_REPLICA_IDENTITY = "aiml-s2e-offhost-replica-attestor-v1"
OFFHOST_REPLICA_NAMESPACE = "arcane-equilibrium-aiml-s2e-offhost-replica"
DURABILITY_ANCHOR_LOCATOR_PREFIX = "host:append-only-durability-anchor:"
OFFHOST_REPLICA_LOCATOR_PREFIX = "replica:offhost-append-only:"
PREDECESSOR_REGISTRY_LOCATOR_PREFIX = "registry:host-append-only:"
DURABILITY_ANCHOR_TRUST_ROOT_PATH = Path(
    "/etc/arcane-equilibrium/aiml/"
    "s2e-durability-anchor-trust-root-v1.json"
)
# 第二把 key 的公開信任根。私鑰與簽章動作歸屬第二台實體機器(operator 2026-08-03
# 裁決),trade-core 只讀公鑰形式;`host_fingerprint` 是那台機器的 SSH host key 指紋。
OFFHOST_REPLICA_TRUST_ROOT_PATH = Path(
    "/etc/arcane-equilibrium/aiml/"
    "s2e-offhost-replica-trust-root-v1.json"
)
PREDECESSOR_REGISTRY_TRUST_ROOT_PATH = Path(
    "/etc/arcane-equilibrium/aiml/"
    "s2e-predecessor-registry-trust-root-v1.json"
)
TRUST_ROOT_OWNER_UID = 0
TRUST_ROOT_MODE = 0o644
MAX_TRUST_ROOT_BYTES = 16 * 1024
MAX_ATTESTATION_TTL = timedelta(minutes=10)
_TRUST_ROOT_FIELDS = {
    "schema_version",
    "signer_identity",
    "signature_namespace",
    "algorithm",
    "key_generation",
    "anchor",
    "public_key",
    "key_fingerprint",
    "attestor_class",
}
_HOST_FINGERPRINT_FIELDS = frozenset({"host_fingerprint"})
_SSH_FINGERPRINT_PATTERN = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
# anchor 側簽章覆蓋除三個自指欄位外的全部欄位(含整份 replica readback);
# replica 側只排除自己的兩個自指欄位,因此兩把簽章對同一個 head 各自負責。
_ANCHOR_SIGNED_EXCLUSIONS = frozenset({
    "signed_core_digest", "signature", "attestation_digest",
})
_REPLICA_SIGNED_EXCLUSIONS = frozenset({"signed_core_digest", "signature"})
# 驗證器自己跑在 anchor host 上,因此它可以直接讀本機的 SSH host key 並算指紋。
LOCAL_SSH_HOST_KEY_DIR = Path("/etc/ssh")
LOCAL_SSH_HOST_KEY_GLOB = "ssh_host_*.pub"
LOCAL_HOST_KEYS_OBSERVED = "LOCAL_HOST_KEYS_OBSERVED"
LOCAL_HOST_KEYS_UNREADABLE = "LOCAL_HOST_KEYS_UNREADABLE"
# 一把 SSH host public key 遠小於此;上界只是為了讓「超大檔」不進記憶體。
MAX_LOCAL_HOST_KEY_BYTES = 64 * 1024


def _read_local_host_key_bytes(candidate: Path) -> bytes | None:
    """讀一個 host key 檔;不是**普通檔案**或讀不完整一律回 `None`。

    E3-E 指出兩個新增的讀取面:
    - `/etc/ssh` 下一個名為 `ssh_host_*.pub` 的 **FIFO** 會讓 `read_text` 永久阻塞
      (E3 實測 15s 未止)。因此改用 `os.open(..., O_NONBLOCK)` + `fstat`:FIFO 在
      O_NONBLOCK 下立刻回 fd,再由 `S_ISREG` 擋掉,且沒有 lstat→open 的 TOCTOU 縫。
    - 超大檔會讓 `MemoryError` 從 `validate_s2e_durability_anchor_attestation` 裸逸出
      (它不在舊的 except tuple 內)。因此設位元組上界,並顯式捕捉 `MemoryError`。
    """

    fd = None
    try:
        fd = os.open(candidate, os.O_RDONLY | os.O_NONBLOCK)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        raw = os.read(fd, MAX_LOCAL_HOST_KEY_BYTES + 1)
        return None if len(raw) > MAX_LOCAL_HOST_KEY_BYTES else raw
    except (OSError, ValueError, MemoryError):
        return None
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def local_ssh_host_key_fingerprints() -> tuple[frozenset[str], str]:
    """本機 SSH host key 指紋集合 + typed 觀察狀態。

    E3(2026-08-03 複核 §六「應該」第 9 項)指出:副本是否在**別台機器**這件事,有一段
    是代碼本來就能執法卻被推給 provisioning 的——驗證器跑在 trade-core 上,讀
    `/etc/ssh/ssh_host_*.pub` 就能算出本機指紋,要求 `replica_host_fingerprint`
    不等於其中任何一個。這**不是**設計 §5.2 拒絕過的 loopback 自由文字黑名單
    (對自由文字做否定列舉無法判定 host identity),而是與**真實本機 key** 的逐字
    比對:同一台機器就是同一把 host key,改不掉也繞不開。

    讀不到時(例如 Mac 開發機沒有 sshd host key)**不得 fail-open**:回空集合 +
    `LOCAL_HOST_KEYS_UNREADABLE`,由驗證器把該 typed skip 顯式帶到 errors 之外的
    observation 通道,而不是在驗證器裡靜默當成「已檢查且通過」。

    E3-E／E2 F-06(2026-08-04):舊版**逐檔失敗靜默 `continue`**,卻仍然回報
    `LOCAL_HOST_KEYS_OBSERVED`。E2 實測用 `ssh-keygen -C` 把 rsa 那把的 comment 改成
    合法 UTF-8(非 ASCII)⇒ `read_text(encoding="ascii")` 拋 `UnicodeDecodeError`,
    那把指紋被靜默排除、狀態仍說「已觀察」,攻擊者拿它當 `replica_host_fingerprint`
    就不會被抓;E3 另測出 mode 000 同效果。修法兩層:
    (1) 解碼改成**只取 wire 欄位的位元組**,不再對整行做 ASCII 解碼——comment 是自由
        文字,本來就不該影響指紋計算;
    (2) 任何一個 candidate 失敗都**降級狀態**為 `LOCAL_HOST_KEYS_UNREADABLE`。
        已算出的指紋仍然回傳(它們仍能抓到冒充),但狀態不再宣稱「全部已觀察」。
    """

    fingerprints: set[str] = set()
    degraded = False
    try:
        candidates = sorted(LOCAL_SSH_HOST_KEY_DIR.glob(LOCAL_SSH_HOST_KEY_GLOB))
    except OSError:
        return frozenset(), LOCAL_HOST_KEYS_UNREADABLE
    for candidate in candidates:
        raw = _read_local_host_key_bytes(candidate)
        if raw is None:
            degraded = True
            continue
        try:
            wire = base64.b64decode(raw.split()[1], validate=True)
        except (IndexError, ValueError, TypeError):
            degraded = True
            continue
        digest = base64.b64encode(hashlib.sha256(wire).digest()).decode("ascii")
        fingerprints.add("SHA256:" + digest.rstrip("="))
    if degraded or not fingerprints:
        return frozenset(fingerprints), LOCAL_HOST_KEYS_UNREADABLE
    return frozenset(fingerprints), LOCAL_HOST_KEYS_OBSERVED


def _raw_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _strict_json_object(raw: bytes) -> Any:
    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    return json.loads(raw.decode("utf-8"), object_pairs_hook=object_pairs)


def _timestamp(value: str | datetime) -> datetime:
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _read_trust_root(
    path: Path,
    *,
    schema_version: str,
    signer_identity: str,
    signature_namespace: str,
    attestor_class: str,
    label: str,
    extra_fields: frozenset[str] = frozenset(),
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    repo_root = Path(__file__).resolve().parents[2]
    if not path.is_absolute() or path.is_relative_to(repo_root):
        return None, [f"{label} trust-root path is not fixed off-repository"]
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(
        os, "O_NOFOLLOW", 0
    )
    try:
        before = os.lstat(path)
        if stat.S_ISLNK(before.st_mode):
            raise ValueError("trust-root path is a symlink")
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode):
                errors.append(f"{label} trust root is not a regular file")
            if opened.st_nlink != 1:
                errors.append(f"{label} trust root link count is not one")
            if opened.st_uid != TRUST_ROOT_OWNER_UID:
                errors.append(f"{label} trust root owner is not trusted")
            if stat.S_IMODE(opened.st_mode) != TRUST_ROOT_MODE:
                errors.append(f"{label} trust root mode is not exact")
            raw = bytearray()
            while len(raw) <= MAX_TRUST_ROOT_BYTES:
                chunk = os.read(
                    descriptor,
                    min(4096, MAX_TRUST_ROOT_BYTES + 1 - len(raw)),
                )
                if not chunk:
                    break
                raw.extend(chunk)
        finally:
            os.close(descriptor)
        after = os.lstat(path)
        identity = (opened.st_dev, opened.st_ino, opened.st_mode, opened.st_uid)
        if identity != (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_uid,
        ) or identity != (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_uid,
        ):
            errors.append(f"{label} trust root changed while being read")
    except (OSError, ValueError) as error:
        return None, [f"{label} trust root is unavailable or untrusted: {error}"]
    if len(raw) > MAX_TRUST_ROOT_BYTES:
        return None, errors + [f"{label} trust root exceeds size limit"]
    try:
        profile = _strict_json_object(bytes(raw))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        return None, errors + [f"{label} trust root JSON is invalid: {error}"]
    if not isinstance(profile, dict) or set(profile) != (
        _TRUST_ROOT_FIELDS | set(extra_fields)
    ):
        return None, errors + [f"{label} trust root fields are not exact"]
    expected = {
        "schema_version": schema_version,
        "signer_identity": signer_identity,
        "signature_namespace": signature_namespace,
        "algorithm": "SSH-ED25519",
        "key_generation": "independent_off_repo_ed25519_v1",
        "anchor": "fixed_off_repo_public_trust_root_v1",
        "attestor_class": attestor_class,
    }
    for field, value in expected.items():
        if profile.get(field) != value:
            errors.append(f"{label} trust root {field} is invalid")
    # extra field 目前只有 host_fingerprint;它是公開值,必須是逐字可外部核對的
    # SSH host key 指紋形制,不得是佔位字串。
    for field in sorted(extra_fields):
        if not _SSH_FINGERPRINT_PATTERN.match(str(profile.get(field, ""))):
            errors.append(f"{label} trust root {field} is not an SSH fingerprint")
    try:
        fingerprint = trusted_host.ssh_public_key_fingerprint(
            str(profile.get("public_key"))
        )
    except ValueError as error:
        errors.append(f"{label} trust root public key is invalid: {error}")
    else:
        if profile.get("key_fingerprint") != fingerprint:
            errors.append(f"{label} trust root fingerprint does not match public key")
    if _contains_github_secret_like_content(profile):
        errors.append(f"{label} trust root contains secret-like content")
    return (profile if not errors else None), errors


def _load_durability_anchor_trust_root(
) -> tuple[dict[str, Any] | None, list[str]]:
    return _read_trust_root(
        DURABILITY_ANCHOR_TRUST_ROOT_PATH,
        schema_version="s2e_durability_anchor_trust_root_v1",
        signer_identity=DURABILITY_ANCHOR_IDENTITY,
        signature_namespace=DURABILITY_ANCHOR_NAMESPACE,
        attestor_class="HOST_APPEND_ONLY_DURABILITY_ANCHOR_V1",
        label="S2E durability anchor",
        extra_fields=_HOST_FINGERPRINT_FIELDS,
    )


def _load_offhost_replica_trust_root(
) -> tuple[dict[str, Any] | None, list[str]]:
    return _read_trust_root(
        OFFHOST_REPLICA_TRUST_ROOT_PATH,
        schema_version="s2e_offhost_replica_trust_root_v1",
        signer_identity=OFFHOST_REPLICA_IDENTITY,
        signature_namespace=OFFHOST_REPLICA_NAMESPACE,
        attestor_class="OFFHOST_APPEND_ONLY_REPLICA_READBACK_V1",
        label="S2E off-host replica readback",
        extra_fields=_HOST_FINGERPRINT_FIELDS,
    )


def _load_predecessor_registry_trust_root(
) -> tuple[dict[str, Any] | None, list[str]]:
    return _read_trust_root(
        PREDECESSOR_REGISTRY_TRUST_ROOT_PATH,
        schema_version="s2e_predecessor_registry_trust_root_v1",
        signer_identity=PREDECESSOR_REGISTRY_IDENTITY,
        signature_namespace=PREDECESSOR_REGISTRY_NAMESPACE,
        attestor_class="HOST_APPEND_ONLY_PREDECESSOR_REGISTRY_V1",
        label="S2E predecessor registry",
    )


def _load_s2e_receipt_signer_profile(
) -> tuple[dict[str, Any] | None, list[str]]:
    from aiml_gate_receipt_s2e_launch import load_s2e_receipt_signer_trust_root

    return load_s2e_receipt_signer_trust_root()


def _signed_bytes(
    attestation: dict[str, Any],
    *,
    excluded: frozenset[str] = _ANCHOR_SIGNED_EXCLUSIONS,
) -> bytes:
    return json.dumps(
        {
            key: value
            for key, value in attestation.items()
            if key not in excluded
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def durability_anchor_signed_bytes(attestation: dict[str, Any]) -> bytes:
    return _signed_bytes(attestation)


def offhost_replica_readback_signed_bytes(readback: dict[str, Any]) -> bytes:
    """replica 先簽自己的 readback core,anchor 再把整份 readback 納入自己的簽章。

    因此 anchor 簽章證明「我引用的就是這份 replica 證言」,replica 簽章證明
    「我在我自己的時間窗看到這個 head」:兩把簽章對同一個 head 各自負責。
    """

    return _signed_bytes(readback, excluded=_REPLICA_SIGNED_EXCLUSIONS)


def predecessor_registry_signed_bytes(attestation: dict[str, Any]) -> bytes:
    return _signed_bytes(attestation)


def durability_anchor_attestation_digest(
    attestation: dict[str, Any],
) -> str:
    return canonical_digest({
        key: value for key, value in attestation.items()
        if key != "attestation_digest"
    })


def durability_anchor_digest_or_none(value: Any) -> str | None:
    return value.get("attestation_digest") if isinstance(value, dict) else None


def durability_anchor_entry_digest(attestation: dict[str, Any]) -> str:
    """單筆 append-only 條目的規範摘要,與 registry 條目採同一形制。"""

    fields = (
        "anchor_class",
        "anchor_locator",
        "launch_id",
        "terminal_payload_digest",
        "anchor_generation",
        "previous_anchor_head_digest",
    )
    return canonical_digest({
        "schema_version": "s2e_durability_anchor_entry_v1",
        **{field: attestation.get(field) for field in fields},
    })


def durability_anchor_head_digest(attestation: dict[str, Any]) -> str:
    """append-only head 的規範摘要;off-host 副本必須回讀到同一個值。"""

    return canonical_digest({
        "schema_version": "s2e_durability_anchor_head_v1",
        "anchor_class": attestation.get("anchor_class"),
        "anchor_locator": attestation.get("anchor_locator"),
        "anchor_generation": attestation.get("anchor_generation"),
        "previous_anchor_head_digest": attestation.get(
            "previous_anchor_head_digest"
        ),
        "anchor_entry_digest": attestation.get("anchor_entry_digest"),
    })


def predecessor_registry_attestation_digest(
    attestation: dict[str, Any],
) -> str:
    return canonical_digest({
        key: value for key, value in attestation.items()
        if key != "attestation_digest"
    })


def s2e_predecessor_registry_slot_id(predecessor_payload_digest: str) -> str:
    return canonical_digest({
        "schema_version": "s2e_launch_predecessor_single_use_slot_v1",
        "launch_id": LAUNCH_ID,
        "predecessor_payload_digest": predecessor_payload_digest,
    })


def predecessor_registry_entry_digest(attestation: dict[str, Any]) -> str:
    fields = (
        "registry_class",
        "registry_locator",
        "launch_id",
        "slot_id",
        "predecessor_payload_digest",
        "successor_candidate_payload_digest",
        "successor_wave",
        "successor_source_head",
        "acceptance_review_bundle_digest",
        "prior_consumption_ledger_digest",
        "expected_consumption_entry_digest",
        "expected_result_ledger_digest",
        "decision",
        "conflicting_grant_absent",
        "registry_generation",
        "previous_registry_head_digest",
    )
    return canonical_digest({
        "schema_version": "s2e_predecessor_registry_entry_v1",
        **{field: attestation.get(field) for field in fields},
    })


def predecessor_registry_head_digest(attestation: dict[str, Any]) -> str:
    return canonical_digest({
        "schema_version": "s2e_predecessor_registry_head_v1",
        "registry_class": attestation.get("registry_class"),
        "registry_locator": attestation.get("registry_locator"),
        "registry_generation": attestation.get("registry_generation"),
        "previous_registry_head_digest": attestation.get(
            "previous_registry_head_digest"
        ),
        "registry_entry_digest": attestation.get("registry_entry_digest"),
    })


def _freshness_errors(
    attestation: dict[str, Any],
    *,
    now: str | datetime,
    label: str,
    require_current_freshness: bool = True,
) -> list[str]:
    """時間無關的窗長上界恆檢查;只有「now 落在窗內」這個謂詞受參數控制。

    被某份已發行 receipt 的 digest 釘死的歷史件物理上不可重鑄,對它做 wall-clock
    檢查必然在時間推移後變成死鎖。窗長上界(≤10 分鐘)**不因此放寬**——本參數
    不加長任何窗,也絕不得與 `require_current_generation` 合併成一個 flag。
    """

    errors: list[str] = []
    try:
        observed = _timestamp(attestation.get("observed_at"))
        expires = _timestamp(attestation.get("expires_at"))
        if not observed < expires:
            errors.append(f"{label} freshness window is invalid")
        if expires - observed > MAX_ATTESTATION_TTL:
            errors.append(f"{label} freshness window exceeds ten minutes")
        if require_current_freshness and not observed <= _timestamp(now) < expires:
            errors.append(f"{label} is stale or not yet valid")
    except (TypeError, ValueError) as error:
        errors.append(f"{label} timestamp is invalid: {error}")
    return errors


def _signature_errors(
    attestation: dict[str, Any],
    *,
    profile_loader: Callable[[], tuple[dict[str, Any] | None, list[str]]],
    identity: str,
    namespace: str,
    label: str,
    excluded: frozenset[str] = _ANCHOR_SIGNED_EXCLUSIONS,
) -> tuple[list[str], dict[str, Any] | None]:
    profile, errors = profile_loader()
    if profile is None:
        return list(errors), None
    signer = attestation.get("signer", {})
    for field, profile_field in (
        ("identity", "signer_identity"),
        ("namespace", "signature_namespace"),
        ("key_generation", "key_generation"),
        ("anchor", "anchor"),
        ("key_fingerprint", "key_fingerprint"),
    ):
        if signer.get(field) != profile.get(profile_field):
            errors.append(f"{label} signer {field} differs from fixed trust root")
    signed = _signed_bytes(attestation, excluded=excluded)
    signed_digest = _raw_digest(signed)
    if attestation.get("signed_core_digest") != signed_digest:
        errors.append(f"{label} signed core digest is invalid")
    signature = attestation.get("signature", {})
    if signature.get("signed_digest") != signed_digest:
        errors.append(f"{label} signature binding differs")
    if not trusted_host._verify_ssh_signature(
        signed,
        str(signature.get("signature", "")).encode("ascii", errors="ignore"),
        public_key=str(profile["public_key"]),
        identity=identity,
        namespace=namespace,
    ):
        errors.append(f"{label} SSHSIG verification failed")
    return errors, profile


def _distinct_fingerprint_errors(
    *,
    subject: dict[str, Any] | None,
    peers: list[tuple[str, dict[str, Any] | None]],
    label: str,
) -> list[str]:
    if subject is None:
        return []
    fingerprint = subject.get("key_fingerprint")
    errors: list[str] = []
    for peer_label, peer in peers:
        if peer is None:
            errors.append(f"{label} cannot prove key separation from {peer_label}")
        elif fingerprint == peer.get("key_fingerprint"):
            errors.append(f"{label} key is not independent from {peer_label}")
    return errors


def _external_locator_errors(
    value: Any,
    *,
    label: str,
    required_prefix: str | None = None,
    admitted_class: str = "external registry class",
) -> list[str]:
    if not isinstance(value, str):
        return [f"{label} locator is not a string"]
    canonical = value.strip()
    if canonical != value:
        return [f"{label} locator is not canonical"]
    scheme, separator, _remainder = canonical.partition(":")
    if not separator or scheme.lower() in LOCAL_EVIDENCE_LOCATOR_SCHEMES:
        return [f"{label} locator is fixture or local evidence"]
    if required_prefix is not None and not canonical.startswith(required_prefix):
        return [f"{label} locator is outside the admitted {admitted_class}"]
    return []


def _replica_readback_errors(
    attestation: dict[str, Any],
    *,
    now: str | datetime,
    require_current_freshness: bool,
) -> tuple[list[str], dict[str, Any] | None, str]:
    """第二把 key 在第二個 host identity 上對同一個 head 的獨立回讀證言。

    副本是同一條 ledger 的忠實鏡像,不是獨立計數器:獨立性來自「第二把 key +
    第二個 host」,不是來自第二個計數器。
    """

    readback = attestation.get("offhost_replica_readback")
    if not isinstance(readback, dict):
        return (
            ["durability anchor off-host replica readback is absent"],
            None,
            local_ssh_host_key_fingerprints()[1],
        )
    errors: list[str] = []
    if readback.get("replica_locator") != attestation.get("offhost_replica_locator"):
        errors.append("durability anchor replica locator differs from the attestation")
    if readback.get("observed_anchor_locator") != attestation.get("anchor_locator"):
        errors.append("durability anchor replica observed a different anchor locator")
    for replica_field, anchor_field in (
        ("replica_generation", "anchor_generation"),
        ("replica_previous_head_digest", "previous_anchor_head_digest"),
        ("replica_entry_digest", "anchor_entry_digest"),
        ("replica_head_digest", "anchor_head_digest"),
    ):
        if readback.get(replica_field) != attestation.get(anchor_field):
            errors.append(
                f"durability anchor replica {replica_field} does not mirror the anchor"
            )
    errors.extend(_freshness_errors(
        readback,
        now=now,
        label="durability anchor replica readback",
        require_current_freshness=require_current_freshness,
    ))
    signature_errors, replica_profile = _signature_errors(
        readback,
        profile_loader=_load_offhost_replica_trust_root,
        identity=OFFHOST_REPLICA_IDENTITY,
        namespace=OFFHOST_REPLICA_NAMESPACE,
        label="durability anchor replica readback",
        excluded=_REPLICA_SIGNED_EXCLUSIONS,
    )
    errors.extend(signature_errors)
    # §5.1:副本身分的獨立性綁 host fingerprint,不用 loopback 黑名單——對自由文字
    # 做否定列舉無法判定 host identity,而指紋是可由第三方視角 keyscan 逐字核對的公開值。
    if replica_profile is not None and readback.get("replica_host_fingerprint") != (
        replica_profile.get("host_fingerprint")
    ):
        errors.append(
            "durability anchor replica host fingerprint differs from its fixed "
            "trust root"
        )
    # 與**本機真實 host key** 的逐字比對(見 `local_ssh_host_key_fingerprints`)。
    # 讀不到時集合為空 ⇒ 這裡不產生錯誤,狀態改由 observation 通道帶出。
    local_fingerprints, local_status = local_ssh_host_key_fingerprints()
    if readback.get("replica_host_fingerprint") in local_fingerprints:
        errors.append(
            "durability anchor replica host fingerprint is this verifying host's "
            "own SSH host key"
        )
    return errors, replica_profile, local_status


def validate_s2e_durability_anchor_attestation(
    attestation: Any,
    *,
    terminal_payload_digest: str,
    now: str | datetime,
    require_current_freshness: bool = True,
    observations: list[str] | None = None,
) -> list[str]:
    """Require two independent SSHSIG keys on two host identities over one head.

    這是 §LW1 spec anchor 選言的第二支。anchor 側簽章綁 append-only monotonic
    head 與 trusted freshness window;replica 側由**第二把 key、第二個 host
    fingerprint**對同一個 head 再簽一次,並帶自己的時間窗。因此 spec 的兩條否定
    條款(單一簽章不能防 rollback、同一 writer coherent rewrite 只能得
    `UNVERIFIED`)在結構上成立:只取得 anchor host 的 root 拿不到第二台機器對改寫
    後 head 的簽章。caller 不能自選 anchor 或 replica 後端。

    **代碼不宣稱、也不可能宣稱**:replica 私鑰實際存放在哪台機器。驗證端跑在受檢
    主機上,這是任何在受檢主機執行的驗證器的資訊論上界;該邊界由 provisioning 的
    三個可核對物承擔(keypair 產生地、第三方視角 keyscan、blocking 前置)。

    `observations` 是**errors 以外**的 typed 通道:本機 host key 讀不到時,
    「這一條沒被執法」必須顯式出現在這裡,不能靜默當成已檢查(複核 §六-9)。

    **這條通道的消費者(E3-E／E2 F-07,2026-08-04 明確化)**:

    - `aiml_gate_receipt_s2e_launch.verify_receipt_carrier_attestation` 把它投影成
      result dict 的 `host_identity_observations`。該欄位在 repo 內**沒有程式消費者**,
      它是 result artifact 上供人工/receipt 審閱的 typed 欄位(被
      `verification_result_digest` 涵蓋)。此處刻意寫明,免得它被誤讀成一個已被執法的
      檢查——**不得**因為「有欄位」就推論「已檢查」。
    - acceptance-review 那條路徑(gate issuance 與 predecessor authority 走的就是它)
      舊版**根本沒傳** `observations`,於是同一條觀察只接了一半。現在由
      `AnchorGateObservations` 一路帶到 `agent_governance_s2e_launch_receipts` CLI 的
      `anchor_gate_observations` 輸出,那是本通道真正的程式消費者。
    """

    schema = _load_schema(DURABILITY_ANCHOR_SCHEMA)
    errors = schema_subset_errors(attestation, schema, root_schema=schema)
    if not isinstance(attestation, dict):
        return errors
    errors.extend(_external_locator_errors(
        attestation.get("anchor_locator"),
        label="durability anchor",
        required_prefix=DURABILITY_ANCHOR_LOCATOR_PREFIX,
        admitted_class="host append-only durability anchor class",
    ))
    errors.extend(_external_locator_errors(
        attestation.get("offhost_replica_locator"),
        label="durability anchor replica",
        required_prefix=OFFHOST_REPLICA_LOCATOR_PREFIX,
        admitted_class="off-host append-only replica class",
    ))
    if errors:
        return sorted(set(errors))
    if attestation.get("launch_id") != LAUNCH_ID:
        errors.append("durability anchor launch_id binding differs")
    if attestation.get("terminal_payload_digest") != terminal_payload_digest:
        errors.append("durability anchor terminal_payload_digest binding differs")
    # generation 與 previous head 必須連續:第一代不得帶前手,後續代不得缺前手。
    generation = attestation.get("anchor_generation")
    previous = attestation.get("previous_anchor_head_digest")
    if (generation == 1 and previous is not None) or (
        isinstance(generation, int) and generation > 1 and previous is None
    ):
        errors.append("durability anchor generation/head continuity is invalid")
    if attestation.get("anchor_entry_digest") != (
        durability_anchor_entry_digest(attestation)
    ):
        errors.append("durability anchor entry digest is invalid")
    if attestation.get("anchor_head_digest") != (
        durability_anchor_head_digest(attestation)
    ):
        errors.append("durability anchor head digest is invalid")
    readback = attestation.get("offhost_replica_readback")
    readback = readback if isinstance(readback, dict) else {}
    replica_errors, replica_profile, local_status = _replica_readback_errors(
        attestation,
        now=now,
        require_current_freshness=require_current_freshness,
    )
    errors.extend(replica_errors)
    if observations is not None:
        observations.append(f"durability anchor replica host identity: {local_status}")
    errors.extend(_freshness_errors(
        attestation,
        now=now,
        label="durability anchor",
        require_current_freshness=require_current_freshness,
    ))
    try:
        if _timestamp(attestation["observed_at"]) < _timestamp(
            readback["observed_at"]
        ):
            errors.append("durability anchor predates off-host readback")
    except (KeyError, TypeError, ValueError) as error:
        errors.append(f"durability anchor binding timestamp is invalid: {error}")
    signature_errors, anchor_profile = _signature_errors(
        attestation,
        profile_loader=_load_durability_anchor_trust_root,
        identity=DURABILITY_ANCHOR_IDENTITY,
        namespace=DURABILITY_ANCHOR_NAMESPACE,
        label="durability anchor",
    )
    errors.extend(signature_errors)
    if anchor_profile is not None and attestation.get("anchor_host_fingerprint") != (
        anchor_profile.get("host_fingerprint")
    ):
        errors.append(
            "durability anchor host fingerprint differs from its fixed trust root"
        )
    if attestation.get("anchor_host_fingerprint") == readback.get(
        "replica_host_fingerprint"
    ):
        errors.append(
            "durability anchor replica host identity is not independent from the "
            "anchor host"
        )
    receipt_profile, receipt_errors = _load_s2e_receipt_signer_profile()
    errors.extend(receipt_errors)
    errors.extend(_distinct_fingerprint_errors(
        subject=anchor_profile,
        peers=[
            ("S2E receipt signer", receipt_profile),
            ("off-host replica readback attestor", replica_profile),
        ],
        label="durability anchor",
    ))
    errors.extend(_distinct_fingerprint_errors(
        subject=replica_profile,
        peers=[
            ("S2E receipt signer", receipt_profile),
            ("durability anchor", anchor_profile),
        ],
        label="durability anchor replica readback",
    ))
    if attestation.get("attestation_digest") != (
        durability_anchor_attestation_digest(attestation)
    ):
        errors.append("durability anchor attestation digest is invalid")
    if _contains_github_secret_like_content(attestation):
        errors.append("durability anchor attestation contains secret-like content")
    return sorted(set(errors))


def validate_s2e_predecessor_registry_attestation(
    attestation: Any,
    *,
    candidate: dict[str, Any],
    predecessor_receipt: dict[str, Any],
    acceptance_review_bundle_digest: str,
    prior_consumption_ledger_digest: str,
    expected_consumption_entry: dict[str, Any],
    expected_result_ledger_digest: str,
    now: str | datetime,
) -> list[str]:
    """Validate one independent, append-only predecessor single-use grant."""

    schema = _load_schema(PREDECESSOR_REGISTRY_SCHEMA)
    errors = schema_subset_errors(attestation, schema, root_schema=schema)
    if errors or not isinstance(attestation, dict):
        return errors
    predecessor_digest = str(predecessor_receipt.get("payload_digest", ""))
    expected = {
        "launch_id": LAUNCH_ID,
        "slot_id": s2e_predecessor_registry_slot_id(predecessor_digest),
        "predecessor_payload_digest": predecessor_digest,
        "successor_candidate_payload_digest": candidate.get("payload_digest"),
        "successor_wave": candidate.get("wave"),
        "successor_source_head": candidate.get("source_head"),
        "acceptance_review_bundle_digest": acceptance_review_bundle_digest,
        "prior_consumption_ledger_digest": prior_consumption_ledger_digest,
        "expected_consumption_entry_digest": expected_consumption_entry.get(
            "entry_digest"
        ),
        "expected_result_ledger_digest": expected_result_ledger_digest,
        "decision": "GRANTED_ONCE",
        "conflicting_grant_absent": True,
    }
    for field, value in expected.items():
        if attestation.get(field) != value:
            errors.append(f"predecessor registry {field} binding differs")
    errors.extend(_external_locator_errors(
        attestation.get("registry_locator"),
        label="predecessor registry",
        required_prefix=PREDECESSOR_REGISTRY_LOCATOR_PREFIX,
    ))
    generation = attestation.get("registry_generation")
    previous = attestation.get("previous_registry_head_digest")
    if (generation == 1 and previous is not None) or (
        isinstance(generation, int) and generation > 1 and previous is None
    ):
        errors.append("predecessor registry generation/head continuity is invalid")
    if attestation.get("registry_entry_digest") != (
        predecessor_registry_entry_digest(attestation)
    ):
        errors.append("predecessor registry entry digest is invalid")
    if attestation.get("registry_head_digest") != (
        predecessor_registry_head_digest(attestation)
    ):
        errors.append("predecessor registry head digest is invalid")
    errors.extend(_freshness_errors(attestation, now=now, label="predecessor registry"))
    signature_errors, registry_profile = _signature_errors(
        attestation,
        profile_loader=_load_predecessor_registry_trust_root,
        identity=PREDECESSOR_REGISTRY_IDENTITY,
        namespace=PREDECESSOR_REGISTRY_NAMESPACE,
        label="predecessor registry",
    )
    errors.extend(signature_errors)
    receipt_profile, receipt_errors = _load_s2e_receipt_signer_profile()
    anchor_profile, anchor_errors = _load_durability_anchor_trust_root()
    errors.extend(receipt_errors)
    errors.extend(anchor_errors)
    errors.extend(_distinct_fingerprint_errors(
        subject=registry_profile,
        peers=[
            ("S2E receipt signer", receipt_profile),
            ("durability anchor", anchor_profile),
        ],
        label="predecessor registry",
    ))
    if attestation.get("attestation_digest") != (
        predecessor_registry_attestation_digest(attestation)
    ):
        errors.append("predecessor registry attestation digest is invalid")
    if _contains_github_secret_like_content(attestation):
        errors.append("predecessor registry attestation contains secret-like content")
    return sorted(set(errors))

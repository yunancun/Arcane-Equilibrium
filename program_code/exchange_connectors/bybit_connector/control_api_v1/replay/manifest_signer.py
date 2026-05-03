"""REF-20 P2a-S2 Manifest Signer — Python mirror of Rust ManifestSigner.
REF-20 P2a-S2 Manifest 簽名器 — Python 鏡像 Rust ManifestSigner.

MODULE_NOTE (EN):
    Python mirror of the canonical Rust implementation at
    `rust/openclaw_engine/src/replay/manifest_signer.rs`. For the same
    (canonical_bytes, key) pair, this module's `sign()` MUST produce a
    byte-equal HMAC-SHA256 hex tag to the Rust side. This is the
    cross-language consistency invariant enforced by the integration test
    `tests/replay/test_manifest_signer_xlang_consistency.py` + the Rust
    sibling test `tests/replay_manifest_signer_xlang_consistency.rs`. Both
    consume the same in-tree fixture
    (`rust/openclaw_engine/tests/fixtures/replay_manifest_signer/`).

    Wave 2 P2a-S2 scope (this commit):
      - 256-bit key load from
        `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`.
      - `sign(canonical_bytes) -> hex_signature` synchronous helper.
      - `verify(canonical, declared_hash, sig_hex, fingerprint) -> None`
        (raises ValueError(SignatureFailMode.X.value) on fail).
      - 4 fail-mode enum mirroring Rust enum.
      - `KeyArchive` ABC + `InMemoryKeyArchive` for unit testing without
        V042 `replay_signing_keys` table dependency.

    NOT in this scope:
      - DB INSERT into `replay.replay_signing_keys` (V042 reserved, P2a-S4
        lands archive writer).
      - Cron rotation / retention cleanup (R20-P2a-S1 sub-agent owns).
      - FastAPI route wiring (R20-P2a-S3 sub-agent owns).
      - GovernanceHub / Decision Lease integration (red-line; replay
        subsystem MUST NOT couple to Live hot path).

MODULE_NOTE (中):
    Rust 正規實作（`rust/openclaw_engine/src/replay/manifest_signer.rs`）的
    Python 鏡像。對相同 (canonical_bytes, key) 配對，本模組 `sign()` 必對
    Rust 側產出 byte-equal HMAC-SHA256 hex tag。此跨語言一致性不變量由
    `tests/replay/test_manifest_signer_xlang_consistency.py` 與 Rust sibling
    test 共同強制。兩者消費同一 in-tree fixture。

    Wave 2 P2a-S2 範圍：
      - 從 `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` 讀 256-bit key。
      - `sign(canonical_bytes) -> hex_signature` 同步 helper。
      - `verify(...)` raises ValueError on fail。
      - 4 fail-mode enum 鏡像 Rust enum。
      - `KeyArchive` ABC + `InMemoryKeyArchive` 為 unit test 可行。

    不在本範圍：
      - DB INSERT `replay.replay_signing_keys`（V042 reserved；P2a-S4 起
        archive writer）。
      - Cron rotation（R20-P2a-S1 sub-agent）。
      - FastAPI route wiring（R20-P2a-S3 sub-agent）。
      - GovernanceHub / Decision Lease 整合（紅線；replay subsystem 嚴禁
        耦合 Live hot path）。

SPEC: REF-20 V3 §3 G2 + §5
Runbook: docs/runbooks/replay_signing_key_rotation.md §6
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P2a-S2
V3 §12 acceptance #2: signature_verify 4 fail-mode unit test PASS
"""

from __future__ import annotations

import hashlib
import hmac
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Optional


# V3 §5: HMAC-SHA256 256-bit key 寫成 64 hex char (32 bytes raw)。
# V3 §5: HMAC-SHA256 256-bit key written as 64 hex chars (32 bytes raw).
EXPECTED_KEY_HEX_LEN = 64


class SignatureFailMode(Enum):
    """V3 §5 4 fail-mode 枚舉，鏡像 Rust `SignatureFailMode`。

    V3 §5 four fail-mode enum, mirrors Rust `SignatureFailMode`.

    每個 value 對應 audit row 寫入時的 `replay_fail_mode` 字串 label，
    供 `learning.governance_audit_log` dashboard 區分四種失敗根因。
    Each value maps to the `replay_fail_mode` string label written to
    `learning.governance_audit_log` so the dashboard can disambiguate
    the four failure root-causes.

    Verify path order:
      1. archive lookup → KEY_MISSING if absent.
      2. archive status → KEY_EXPIRED if status ∈ {expired, compromised}.
      3. signature byte-equal → SIGNATURE_MISMATCH else.
      4. body hash equal → MANIFEST_HASH_MISMATCH else.

    順序：(1) archive lookup → KEY_MISSING，(2) status → KEY_EXPIRED，
    (3) signature byte-equal → SIGNATURE_MISMATCH，
    (4) body hash → MANIFEST_HASH_MISMATCH。
    """

    MANIFEST_HASH_MISMATCH = "manifest_hash_mismatch"
    SIGNATURE_MISMATCH = "signature_mismatch"
    KEY_MISSING = "key_missing"
    KEY_EXPIRED = "key_expired"


class KeyStatus(Enum):
    """archive 中 key 的狀態，鏡像 Rust `KeyStatus` + V042 status column。

    Status of a key in the archive, mirrors Rust `KeyStatus` + V042 status
    column.

    - `ACTIVE`: 唯一 active per env，新 manifest 必用此 key 簽。
    - `RETIRED`: 90d rotation 後的舊 key，仍可驗最多 180d 內舊 manifest。
    - `EXPIRED`: 過 180d retention 的舊 key，verify 一律拒（KeyExpired）。
    - `COMPROMISED`: emergency rotation 後的洩漏 key，verify 一律拒。
    """

    ACTIVE = "active"
    RETIRED = "retired"
    EXPIRED = "expired"
    COMPROMISED = "compromised"

    def permits_verify(self) -> bool:
        """此 status 是否仍允許 verify-pass。

        Whether this status still permits verify-pass.

        `ACTIVE` / `RETIRED` → True（runbook §4.3 dual key 支援 180d 內舊 manifest）。
        `EXPIRED` / `COMPROMISED` → False（KeyExpired fail-mode）。
        """
        return self in (KeyStatus.ACTIVE, KeyStatus.RETIRED)


class KeyArchive(ABC):
    """V042 `replay_signing_keys` archive 查詢的抽象 ABC，鏡像 Rust trait。

    Abstract base class for V042 `replay_signing_keys` archive lookup,
    mirrors Rust `KeyArchive` trait.

    Wave 2 P2a-S2 僅出貨 `InMemoryKeyArchive` 供 unit test。Wave 3
    R20-P2a-S4 會落地 SQL 版本（讀 `replay.replay_signing_keys`）。
    Wave 2 ships only `InMemoryKeyArchive` for unit tests; Wave 3
    R20-P2a-S4 lands the SQL-backed implementation.
    """

    @abstractmethod
    def lookup_status(self, fingerprint: str) -> Optional[KeyStatus]:
        """查 fingerprint 對應的 status；不存在回 None → caller 視為 KEY_MISSING。

        Look up status for fingerprint; absent returns None → caller treats
        as KEY_MISSING.
        """
        raise NotImplementedError


class InMemoryKeyArchive(KeyArchive):
    """不依賴 DB 的記憶體版 KeyArchive 實作。

    In-memory KeyArchive impl for unit testing without DB dependency.
    """

    def __init__(self) -> None:
        self._entries: list[tuple[str, KeyStatus]] = []

    def insert(self, fingerprint: str, status: KeyStatus) -> None:
        """加入 fingerprint → status 對映。

        Insert a fingerprint → status mapping.
        """
        self._entries.append((fingerprint, status))

    def lookup_status(self, fingerprint: str) -> Optional[KeyStatus]:
        for fp, status in self._entries:
            if fp == fingerprint:
                return status
        return None


def compute_key_fingerprint(key_file_content: bytes) -> str:
    """計算 **key 檔案內容 bytes**（含 `printf '%s\\n'` 寫入的 trailing newline）
    的 first-16-hex-chars SHA-256 fingerprint。

    Compute first-16-hex-chars SHA-256 fingerprint over **key file content
    bytes** (including trailing newline written by `printf '%s\\n'`).

    鏡像 helper script `generate_replay_signing_key.sh` line 91/93/111 算法：

        openssl dgst -sha256 -hex < $KEY_FILE | awk '{print $NF}' | cut -c1-16

    Script 的 `< $KEY_FILE` 重定向把整個檔案內容（含 `printf '%s\\n'` 寫入的
    `\\n`）餵給 `openssl dgst -sha256 -hex`。本函式必對相同 byte sequence 做
    sha256（檔案內容 as-is，**不 trim、不 hex decode**），以便 operator 寫
    1Password vault 的 fingerprint 與 runtime 查 V042 `replay_signing_keys`
    archive 用的 fingerprint 對得上。

    Mirrors helper script `generate_replay_signing_key.sh` line 91/93/111
    algorithm. The script's `< $KEY_FILE` redirect feeds the entire file
    content (including the `\\n` appended by `printf '%s\\n'`) to
    `openssl dgst -sha256 -hex`. This function MUST sha256 the same byte
    sequence (file content as-is, no trim, no hex decode) so the
    operator-facing fingerprint logged in 1Password vault matches the
    runtime-computed fingerprint used to look up V042 `replay_signing_keys`
    archive.

    不變量 / Invariant: caller MUST 傳檔案 content bytes（typically
    `key_path.read_bytes()` 或測試時 `(key_hex + "\\n").encode("ascii")`）；
    切勿傳 `bytes.fromhex(...)` 後的 raw 32 bytes — 那會與 script-computed
    fingerprint 不符 → 100% `KEY_MISSING` fail-mode（archive lookup miss）。
    """
    full = hashlib.sha256(key_file_content).hexdigest()
    return full[:16]


def compute_body_hash(manifest_canonical: bytes) -> str:
    """計算 canonical manifest bytes 的 SHA-256 hex digest。

    Compute SHA-256 hex digest over canonical manifest bytes.
    """
    return hashlib.sha256(manifest_canonical).hexdigest()


def _constant_time_eq(a: bytes, b: bytes) -> bool:
    """常數時間 byte 比對，防 HMAC tag 的 timing oracle 攻擊。

    Constant-time byte comparison to defeat timing-oracle attacks on HMAC tag.
    Mirrors Rust `constant_time_eq` and uses Python stdlib `hmac.compare_digest`.
    """
    return hmac.compare_digest(a, b)


class ManifestSigner:
    """簽名器主類，鏡像 Rust `ManifestSigner`。

    Manifest signer, mirrors Rust `ManifestSigner`.

    Holds raw 32-byte key + own fingerprint. The same `(key_bytes,
    canonical_bytes)` pair MUST produce the same HMAC-SHA256 tag as Rust
    `ManifestSigner::sign()` (cross-language byte-equal invariant).
    """

    def __init__(self, key_path: Path, fingerprint: str):
        """從 disk 讀 key 構造 signer。Path 必為
        `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key`（V3 §5 hardcode）。

        Construct signer by reading key from disk. Path must be
        `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` (V3 §5 hardcode).

        `fingerprint` 是 caller-provided 預期 fingerprint（first 16 hex char
        of SHA-256 over **key file content bytes**，含 trailing `\\n`，鏡像
        helper script `generate_replay_signing_key.sh` line 91/93/111 的算法）；
        caller 從 V042 archive / 1Password vault 取得，本 ctor 驗證磁碟 key
        的 fingerprint == caller 預期值，不一致則 raise ValueError。

        `fingerprint` is the caller-provided expected fingerprint (first 16
        hex chars of SHA-256 over **key file content bytes**, including
        trailing `\\n`, mirroring helper script
        `generate_replay_signing_key.sh` line 91/93/111 algorithm). This
        constructor verifies disk-key fingerprint == caller expected;
        mismatch → raise ValueError (path correct but content drift, e.g.
        cron failure / rotation forgot to update archive).

        不變量 / Invariant: HMAC key = decoded 32 raw bytes（去除 newline 後
        hex decode）；fingerprint = sha256(file content bytes 含 newline)[:16]。
        兩條 derivation 路徑分離以對齊 helper script 的 operator-facing
        fingerprint（operator 用 openssl 算後寫入 1Password vault，runtime
        必與此一致才能查 V042 archive）。

        Raises:
            FileNotFoundError: key file missing.
            ValueError: key length != 64 hex chars, key not valid hex,
                or fingerprint mismatch.
        """
        if not key_path.is_file():
            # NOTE: 此 raise 非 4 fail-mode 的 KEY_MISSING；那是 verify-time
            # archive lookup 的概念。此處是 sign-time disk read 失敗。
            # NOTE: this is NOT the KEY_MISSING fail-mode (which is verify-time
            # archive lookup); this is sign-time disk read failure.
            raise FileNotFoundError(
                f"replay_signing_key missing at {key_path} / replay_signing_key 檔案不存在"
            )

        # 讀 raw bytes 而非 text — fingerprint 必對 file content bytes（含
        # trailing newline）算 sha256，鏡像 `openssl dgst < KEY_FILE`。
        # Read raw bytes (not text) — fingerprint must sha256 file content
        # bytes (including trailing newline), mirroring `openssl dgst < KEY_FILE`.
        file_content_bytes = key_path.read_bytes()
        raw = file_content_bytes.decode("utf-8").strip()

        # 不變量 / Invariant: V3 §5 demands 256-bit key = 64 hex chars.
        if len(raw) != EXPECTED_KEY_HEX_LEN:
            raise ValueError(
                f"replay_signing_key length {len(raw)} != expected "
                f"{EXPECTED_KEY_HEX_LEN} hex chars (256-bit) / "
                f"replay_signing_key 長度錯誤"
            )

        try:
            key_bytes = bytes.fromhex(raw)
        except ValueError as e:
            raise ValueError(
                f"replay_signing_key hex decode failed: {e} / "
                f"replay_signing_key hex 解碼失敗"
            ) from e

        # 驗 caller 預期 fingerprint == disk key 真實 fingerprint。
        # 注意：fingerprint 算法用 file content bytes（含 newline）以對齊 helper
        # script line 91/93/111；HMAC key 用 decoded raw 32 bytes（去除 newline）。
        # Verify caller-expected fingerprint == disk-key real fingerprint.
        # Note: fingerprint computed over file content bytes (including newline)
        # to align with helper script line 91/93/111; HMAC key uses decoded raw
        # 32 bytes (newline stripped).
        actual_fp = compute_key_fingerprint(file_content_bytes)
        if actual_fp != fingerprint:
            raise ValueError(
                f"replay_signing_key fingerprint mismatch: expected "
                f"{fingerprint}, got {actual_fp} / fingerprint 不符"
            )

        self._key_bytes = key_bytes
        self._fingerprint = fingerprint

    @classmethod
    def from_bytes_for_test(
        cls, key_bytes: bytes, fingerprint: str
    ) -> "ManifestSigner":
        """純測試 constructor — 直接接 raw key bytes + fingerprint。

        Test-only constructor — accepts raw key bytes + fingerprint without
        disk I/O. Used by cross-lang consistency tests where the fixture
        key is loaded from an in-tree fixture file.

        注意 / Note：`key_bytes` 必為 decoded raw 32 bytes（HMAC key 用），
        與 `fingerprint`（caller 預先用 file content bytes 算的 sha256[:16]）
        是兩條獨立 derivation；本 constructor 不重算 fingerprint，直接信任
        caller — 整合測試在 fixture loader 中以 file content bytes 算
        fingerprint 並對齊 `fingerprint.txt`。
        `key_bytes` MUST be decoded raw 32 bytes (HMAC key); `fingerprint` is
        caller-precomputed sha256[:16] over file content bytes. The two
        derivations are independent; this constructor does NOT recompute
        fingerprint and trusts the caller — integration tests compute
        fingerprint over file content bytes in the fixture loader and assert
        against `fingerprint.txt`.

        生產 caller 嚴禁使用（請用 `__init__` 從磁碟讀）。
        Production callers MUST NOT use this (use `__init__` to load from
        disk).
        """
        instance = cls.__new__(cls)
        instance._key_bytes = key_bytes
        instance._fingerprint = fingerprint
        return instance

    @property
    def fingerprint(self) -> str:
        """此 signer 的 fingerprint。

        Fingerprint of this signer.
        """
        return self._fingerprint

    def sign(self, manifest_canonical: bytes) -> str:
        """HMAC-SHA256 sign canonical manifest bytes → hex (lowercase) signature.

        對 canonical manifest bytes 做 HMAC-SHA256 簽名 → hex（小寫）signature。

        `manifest_canonical` MUST be caller-canonicalized bytes (typically
        `json.dumps(..., sort_keys=True, ensure_ascii=False).encode('utf-8')`).
        This function does NOT re-canonicalize; that prevents
        canonicalization-drift between Rust and Python sides.

        `manifest_canonical` 必為 caller 預先 canonicalize 過的 bytes；本
        函式不重做 canonicalization，避免雙端 normalization drift。
        """
        # SAFETY / 不變量: HMAC-SHA256 accepts arbitrary key length. The 32-byte
        # constraint is verified at __init__; here we trust the constructor invariant.
        # 不變量：HMAC-SHA256 接受任意長度 key。32-byte 限制在 __init__ 強制；
        # 此處信任 constructor invariant。
        mac = hmac.new(self._key_bytes, manifest_canonical, hashlib.sha256)
        return mac.hexdigest()

    def verify(
        self,
        manifest_canonical: bytes,
        manifest_declared_hash: str,
        signature_hex: str,
        fingerprint: str,
        archive: KeyArchive,
    ) -> None:
        """V3 §5 verify-order invariant: 先 signature 後 manifest hash。

        V3 §5 verify-order invariant: signature first, manifest hash second.

        Order of checks:
          1. archive lookup → KEY_MISSING if fingerprint absent.
          2. archive status → KEY_EXPIRED if status ∈ {expired, compromised}.
          3. signature byte-equal → SIGNATURE_MISMATCH else.
          4. body hash equal → MANIFEST_HASH_MISMATCH else.

        順序：(1) archive lookup → KEY_MISSING，(2) status → KEY_EXPIRED，
        (3) signature byte-equal → SIGNATURE_MISMATCH，(4) body hash → MANIFEST_HASH_MISMATCH。

        Raises:
            ValueError: with `.args[0]` set to one of the
                `SignatureFailMode.X.value` strings (`signature_mismatch` /
                `manifest_hash_mismatch` / `key_missing` / `key_expired`).
                Caller 必 catch ValueError 後對 `e.args[0]` 做 str 比對 → 寫
                audit row 的 `replay_fail_mode` 欄位（V3 §5 4 fail-mode 區分
                需求）。
        """
        # Step 1: archive lookup gate / archive 查詢 gate。
        status = archive.lookup_status(fingerprint)
        if status is None:
            raise ValueError(SignatureFailMode.KEY_MISSING.value)

        # Step 2: archive status gate / archive 狀態 gate。
        if not status.permits_verify():
            raise ValueError(SignatureFailMode.KEY_EXPIRED.value)

        # Step 3: signature first / 先驗 signature（V3 §5 順序不變量）。
        #
        # 若 verify 用的 fingerprint 對應 key != 本 signer 的 key（caller 用
        # 錯 signer instance 驗別人簽的 manifest），signature 計算結果一定
        # mismatch → SIGNATURE_MISMATCH（這是設計的 fail-closed 行為，prod
        # caller 必先按 fingerprint 路由到正確 signer instance）。
        #
        # If the key behind `fingerprint` differs from this signer's key
        # (caller used the wrong signer instance), the recomputed signature
        # mismatches → SIGNATURE_MISMATCH (intentional fail-closed; production
        # caller must route by fingerprint to the correct signer).
        expected_sig = self.sign(manifest_canonical)
        if not _constant_time_eq(
            expected_sig.encode("ascii"), signature_hex.encode("ascii")
        ):
            raise ValueError(SignatureFailMode.SIGNATURE_MISMATCH.value)

        # Step 4: manifest hash second / 後驗 manifest body hash。
        actual_body_hash = compute_body_hash(manifest_canonical)
        if not _constant_time_eq(
            actual_body_hash.encode("ascii"),
            manifest_declared_hash.encode("ascii"),
        ):
            raise ValueError(SignatureFailMode.MANIFEST_HASH_MISMATCH.value)

        # All four gates passed; verify is OK. Returns implicitly None.
        # 4 個 gate 都通過；verify 成功，隱式 return None。

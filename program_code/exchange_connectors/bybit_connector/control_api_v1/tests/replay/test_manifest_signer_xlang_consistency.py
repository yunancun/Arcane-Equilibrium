"""REF-20 P2a-S2 cross-language consistency test (Python side).
REF-20 P2a-S2 跨語言一致性測試（Python 側）。

MODULE_NOTE (EN):
    Python sibling of
    `rust/openclaw_engine/tests/replay_manifest_signer_xlang_consistency.rs`.
    Both consume the same in-tree fixture
    (`rust/openclaw_engine/tests/fixtures/replay_manifest_signer/`) and
    assert the V3 §12 acceptance #2 binding from the Python implementation:

      1. Python `ManifestSigner.sign()` reproduces the golden signature
         byte-equal for all 3 fixture manifests (cross-language HMAC-SHA256
         byte-equal invariant; tolerance = 0 bytes, NOT 1e-4 since that
         applies to floating-point IPC).
      2. Python `ManifestSigner.verify()` accepts the happy path.
      3. Each of the 4 fail-modes (`SIGNATURE_MISMATCH`,
         `MANIFEST_HASH_MISMATCH`, `KEY_MISSING`, `KEY_EXPIRED`) fires under
         the spec'd condition.

MODULE_NOTE (中):
    Rust sibling test 的 Python 鏡像。兩者消費同一 in-tree fixture，從
    Python 側斷言 V3 §12 acceptance #2 binding：

      1. Python `ManifestSigner.sign()` 對 3 個 fixture manifest 重現 golden
         signature byte-equal（跨語言 HMAC-SHA256 byte-equal 不變量；容差
         0 byte，非 1e-4 — 1e-4 是浮點 IPC 容差）。
      2. Python `ManifestSigner.verify()` 接受 happy path。
      3. 4 種 fail-mode（`SIGNATURE_MISMATCH`、`MANIFEST_HASH_MISMATCH`、
         `KEY_MISSING`、`KEY_EXPIRED`）各在規格條件下觸發。

Fixture 路徑 / Fixture path:
    `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/`

Run / 執行:
    `pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_manifest_signer_xlang_consistency.py -v`

SPEC: REF-20 V3 §3 G2 + §5
V3 §12 acceptance #2: signature_verify 4 fail-mode unit test PASS
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


# ─────────────────────────────────────────────────────────────────────
# Path setup / 路径配置
# ─────────────────────────────────────────────────────────────────────
#
# 推導 control_api_v1 package root，加進 sys.path 以便 `from replay import ...`
# 可直接匯入。鏡像 sibling test 的 conftest.py PROJECT_ROOT pattern。
#
# Resolve control_api_v1 package root and add to sys.path so `from replay
# import ...` works. Mirrors sibling test conftest.py PROJECT_ROOT pattern.

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # control_api_v1/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from replay.manifest_signer import (  # noqa: E402
    InMemoryKeyArchive,
    KeyStatus,
    ManifestSigner,
    SignatureFailMode,
    compute_body_hash,
    compute_key_fingerprint,
)


# ─────────────────────────────────────────────────────────────────────
# Fixture loader / Fixture 載入
# ─────────────────────────────────────────────────────────────────────
#
# Fixture 共用 Rust + Python 兩端。路徑跨平台導出：optionally allow override
# via `OPENCLAW_REPLAY_FIXTURE_DIR` env var；fallback 到 git 根 + 相對路徑。
# 不硬編碼 `/Users/ncyu/...` 或 `/home/ncyu/...`（CLAUDE.md §七 跨平台守則）。
#
# Fixtures are shared with Rust tests. Path is cross-platform-derived: respect
# `OPENCLAW_REPLAY_FIXTURE_DIR` override, fallback to git root + relative path.
# No hardcoded user-home absolute paths (CLAUDE.md §七 cross-platform rule).


def _fixture_dir() -> Path:
    """取得 fixture 目錄（跨平台）。

    Resolve fixture directory cross-platform.

    解析優先序：
    Resolution order:
      1. `OPENCLAW_REPLAY_FIXTURE_DIR` env var (整合測試或 CI override)。
      2. `OPENCLAW_BASE_DIR/rust/openclaw_engine/tests/fixtures/replay_manifest_signer`。
      3. 從本檔反推 4 層到 srv root，再走相對路徑（dev fallback）。
    """
    override = os.environ.get("OPENCLAW_REPLAY_FIXTURE_DIR")
    if override:
        return Path(override)

    base = os.environ.get("OPENCLAW_BASE_DIR")
    if base:
        return (
            Path(base)
            / "rust"
            / "openclaw_engine"
            / "tests"
            / "fixtures"
            / "replay_manifest_signer"
        )

    # Dev fallback: 本檔在 srv/program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/
    # parents[6] = srv root（驗算：parents[0]=replay, [1]=tests, [2]=control_api_v1,
    # [3]=bybit_connector, [4]=exchange_connectors, [5]=program_code, [6]=srv）。
    srv_root = Path(__file__).resolve().parents[6]
    return (
        srv_root
        / "rust"
        / "openclaw_engine"
        / "tests"
        / "fixtures"
        / "replay_manifest_signer"
    )


@pytest.fixture(scope="module")
def fixture_dir() -> Path:
    d = _fixture_dir()
    if not d.is_dir():
        pytest.skip(f"fixture dir missing: {d}")
    return d


@pytest.fixture(scope="module")
def fixture_signer(fixture_dir: Path) -> ManifestSigner:
    """載入 fixture key + 產生 signer。

    Load fixture key + produce signer.

    fingerprint 算法對齊 helper script `generate_replay_signing_key.sh` line
    91/93/111：對 **file content bytes**（含 trailing `\\n`）做 sha256，取
    first 16 hex chars。HMAC key 仍用 decoded raw 32 bytes（key_hex.strip()
    後 bytes.fromhex）。

    fingerprint algorithm aligns with helper script line 91/93/111: sha256
    over **file content bytes** (including trailing `\\n`), first 16 hex
    chars. HMAC key still uses decoded raw 32 bytes (key_hex.strip() then
    bytes.fromhex).
    """
    # 讀 file content as bytes — fingerprint 必對含 trailing newline 的整個
    # 檔案內容做 sha256（鏡像 `openssl dgst -sha256 -hex < key.hex`）。
    # Read file content as bytes — fingerprint must sha256 entire file content
    # including trailing newline (mirrors `openssl dgst -sha256 -hex < key.hex`).
    file_content = (fixture_dir / "key.hex").read_bytes()
    key_hex = file_content.decode("utf-8").strip()
    key_bytes = bytes.fromhex(key_hex)

    # 不變量 / Invariant: V3 §5 demands 32-byte (256-bit) key.
    assert len(key_bytes) == 32, "fixture key must be 32 bytes (V3 §5 256-bit invariant)"

    # fingerprint 對 file content bytes 算（含 trailing `\n`）。
    # fingerprint computed over file content bytes (including trailing `\n`).
    fp = compute_key_fingerprint(file_content)
    expected_fp = (
        (fixture_dir / "fingerprint.txt").read_text(encoding="utf-8").strip()
    )
    assert fp == expected_fp, "fingerprint drift in fixture"

    return ManifestSigner.from_bytes_for_test(key_bytes, fp)


def _load_manifest(fixture_dir: Path, n: int) -> tuple[bytes, str, str]:
    """載入 fixture manifest #N: (body, golden_sig_hex, golden_hash_hex)。

    Load fixture manifest #N: (body_bytes, golden_sig_hex, golden_hash_hex).
    """
    body = (fixture_dir / f"manifest_{n}.json").read_bytes()
    sig = (fixture_dir / f"manifest_{n}.sig").read_text(encoding="utf-8").strip()
    body_hash = (
        (fixture_dir / f"manifest_{n}.hash").read_text(encoding="utf-8").strip()
    )
    return body, sig, body_hash


# ─────────────────────────────────────────────────────────────────────
# Cross-language byte-equal invariant
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("n", [1, 2, 3])
def test_xlang_signature_byte_equal_for_fixture(
    fixture_dir: Path, fixture_signer: ManifestSigner, n: int
):
    """對 3 個 fixture manifest，Python sign 結果必 == golden sig（即 Rust 端
    產生的 sig）→ 雙端 HMAC-SHA256 byte-equal 不變量。

    For 3 fixture manifests, Python sign() result MUST == golden sig
    (Rust-side computed sig) → cross-language HMAC-SHA256 byte-equal
    invariant.
    """
    body, golden_sig, golden_hash = _load_manifest(fixture_dir, n)

    computed_sig = fixture_signer.sign(body)
    assert computed_sig == golden_sig, (
        f"manifest_{n} signature drift: Python computed {computed_sig} "
        f"!= golden {golden_sig} (cross-lang byte-equal invariant violated)"
    )

    computed_hash = compute_body_hash(body)
    assert computed_hash == golden_hash, (
        f"manifest_{n} body hash drift: Python computed {computed_hash} "
        f"!= golden {golden_hash}"
    )


def test_happy_path_verify_passes_with_fixture(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """Happy path: archive 有 active key + signature 對 + body hash 對 → verify 通過。

    Happy path: archive contains active key + signature matches + body hash
    matches → verify passes.
    """
    archive = InMemoryKeyArchive()
    archive.insert(fixture_signer.fingerprint, KeyStatus.ACTIVE)

    for n in (1, 2, 3):
        body, golden_sig, golden_hash = _load_manifest(fixture_dir, n)
        # raises ValueError on fail; nothing on pass.
        fixture_signer.verify(
            body, golden_hash, golden_sig, fixture_signer.fingerprint, archive
        )


# ─────────────────────────────────────────────────────────────────────
# 4 fail-mode tests / 4 fail-mode 測試
# V3 §12 acceptance #2 binding
# ─────────────────────────────────────────────────────────────────────


def test_fail_mode_signature_mismatch_with_fixture(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """V3 §12 acceptance #2 mode 1/4: tamper signature 1 byte → SIGNATURE_MISMATCH."""
    archive = InMemoryKeyArchive()
    archive.insert(fixture_signer.fingerprint, KeyStatus.ACTIVE)

    body, golden_sig, golden_hash = _load_manifest(fixture_dir, 1)
    # Tamper signature first byte / 改 signature 第 1 byte。
    tampered_sig = (
        ("b" if golden_sig[0] == "a" else "a") + golden_sig[1:]
    )

    with pytest.raises(ValueError) as exc:
        fixture_signer.verify(
            body, golden_hash, tampered_sig, fixture_signer.fingerprint, archive
        )
    assert exc.value.args[0] == SignatureFailMode.SIGNATURE_MISMATCH.value
    assert exc.value.args[0] == "signature_mismatch"


def test_fail_mode_manifest_hash_mismatch_with_fixture(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """V3 §12 acceptance #2 mode 2/4: tamper declared hash 1 char → MANIFEST_HASH_MISMATCH.

    純粹的 ManifestHashMismatch 路徑：keep body 不變 + signature 不變
    （所以 step 3 通過）+ tamper declared_hash 1 char（step 4 fail）。

    Pure ManifestHashMismatch path: keep body unchanged + signature unchanged
    (step 3 passes) + tamper declared_hash 1 char (step 4 fails).
    """
    archive = InMemoryKeyArchive()
    archive.insert(fixture_signer.fingerprint, KeyStatus.ACTIVE)

    body, golden_sig, golden_hash = _load_manifest(fixture_dir, 1)
    tampered_hash = ("b" if golden_hash[0] == "a" else "a") + golden_hash[1:]

    with pytest.raises(ValueError) as exc:
        fixture_signer.verify(
            body, tampered_hash, golden_sig, fixture_signer.fingerprint, archive
        )
    assert exc.value.args[0] == SignatureFailMode.MANIFEST_HASH_MISMATCH.value
    assert exc.value.args[0] == "manifest_hash_mismatch"


def test_fail_mode_key_missing_with_fixture(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """V3 §12 acceptance #2 mode 3/4: fingerprint not in archive → KEY_MISSING."""
    empty_archive = InMemoryKeyArchive()  # 空 archive。

    body, golden_sig, golden_hash = _load_manifest(fixture_dir, 1)

    with pytest.raises(ValueError) as exc:
        fixture_signer.verify(
            body, golden_hash, golden_sig, fixture_signer.fingerprint, empty_archive
        )
    assert exc.value.args[0] == SignatureFailMode.KEY_MISSING.value
    assert exc.value.args[0] == "key_missing"


def test_fail_mode_key_expired_with_fixture(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """V3 §12 acceptance #2 mode 4/4: fingerprint in archive with expired status → KEY_EXPIRED."""
    archive = InMemoryKeyArchive()
    archive.insert(fixture_signer.fingerprint, KeyStatus.EXPIRED)

    body, golden_sig, golden_hash = _load_manifest(fixture_dir, 1)

    with pytest.raises(ValueError) as exc:
        fixture_signer.verify(
            body, golden_hash, golden_sig, fixture_signer.fingerprint, archive
        )
    assert exc.value.args[0] == SignatureFailMode.KEY_EXPIRED.value
    assert exc.value.args[0] == "key_expired"


def test_compromised_status_also_fires_key_expired(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """Runbook §6 + V3 §5: COMPROMISED status 必走 KEY_EXPIRED fail-mode。

    Runbook §6 + V3 §5: COMPROMISED status MUST map to KEY_EXPIRED fail-mode
    (emergency-rotated compromised key MUST reject).
    """
    archive = InMemoryKeyArchive()
    archive.insert(fixture_signer.fingerprint, KeyStatus.COMPROMISED)

    body, golden_sig, golden_hash = _load_manifest(fixture_dir, 1)

    with pytest.raises(ValueError) as exc:
        fixture_signer.verify(
            body, golden_hash, golden_sig, fixture_signer.fingerprint, archive
        )
    assert exc.value.args[0] == SignatureFailMode.KEY_EXPIRED.value


def test_retired_status_still_verifies(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """Runbook §4.3 dual key support: RETIRED key 仍可驗 180d 內舊 manifest。

    Runbook §4.3 dual key support: RETIRED key still verifies historical
    manifests within 180d retention.
    """
    archive = InMemoryKeyArchive()
    archive.insert(fixture_signer.fingerprint, KeyStatus.RETIRED)

    body, golden_sig, golden_hash = _load_manifest(fixture_dir, 1)
    # 不 raise；通過代表 retired key 仍可驗。
    # Should not raise; passing means retired key still verifies.
    fixture_signer.verify(
        body, golden_hash, golden_sig, fixture_signer.fingerprint, archive
    )


# ─────────────────────────────────────────────────────────────────────
# Verify-order invariant tests / 驗證順序不變量測試
# ─────────────────────────────────────────────────────────────────────


def test_verify_order_signature_before_hash(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """V3 §5 verify-order invariant: 同時 tamper signature 與 declared hash 時
    必先報 SIGNATURE_MISMATCH（不是 MANIFEST_HASH_MISMATCH）。

    V3 §5 verify-order invariant: when both signature AND declared hash are
    tampered, the error MUST be SIGNATURE_MISMATCH (sig is checked first).
    """
    archive = InMemoryKeyArchive()
    archive.insert(fixture_signer.fingerprint, KeyStatus.ACTIVE)

    body, golden_sig, golden_hash = _load_manifest(fixture_dir, 1)
    tampered_sig = ("b" if golden_sig[0] == "a" else "a") + golden_sig[1:]
    tampered_hash = ("b" if golden_hash[0] == "a" else "a") + golden_hash[1:]

    with pytest.raises(ValueError) as exc:
        fixture_signer.verify(
            body, tampered_hash, tampered_sig, fixture_signer.fingerprint, archive
        )
    assert exc.value.args[0] == SignatureFailMode.SIGNATURE_MISMATCH.value, (
        "V3 §5 verify-order: signature MUST be checked before declared hash"
    )


def test_verify_order_archive_gates_before_signature(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """archive gate (KEY_MISSING / KEY_EXPIRED) 必在 signature gate 之前 —
    即使 signature/hash 都對，archive 沒命中或 expired 仍應拒。

    archive gates (KEY_MISSING / KEY_EXPIRED) MUST precede signature gate —
    even with valid signature/hash, an absent or expired key must reject.
    """
    body, golden_sig, golden_hash = _load_manifest(fixture_dir, 1)

    # KEY_MISSING wins over correct signature.
    with pytest.raises(ValueError) as exc:
        fixture_signer.verify(
            body,
            golden_hash,
            golden_sig,
            fixture_signer.fingerprint,
            InMemoryKeyArchive(),
        )
    assert exc.value.args[0] == SignatureFailMode.KEY_MISSING.value

    # KEY_EXPIRED wins over correct signature.
    expired_archive = InMemoryKeyArchive()
    expired_archive.insert(fixture_signer.fingerprint, KeyStatus.EXPIRED)
    with pytest.raises(ValueError) as exc:
        fixture_signer.verify(
            body, golden_hash, golden_sig, fixture_signer.fingerprint, expired_archive
        )
    assert exc.value.args[0] == SignatureFailMode.KEY_EXPIRED.value


def test_fingerprint_helper_matches_fixture(
    fixture_dir: Path, fixture_signer: ManifestSigner
):
    """驗證 fingerprint helper 與 fixture 中存的 expected fingerprint 一致。

    Sanity-check fingerprint helper against fixture-stored expected fingerprint.
    """
    expected_fp = (
        (fixture_dir / "fingerprint.txt").read_text(encoding="utf-8").strip()
    )
    assert fixture_signer.fingerprint == expected_fp
    assert len(fixture_signer.fingerprint) == 16

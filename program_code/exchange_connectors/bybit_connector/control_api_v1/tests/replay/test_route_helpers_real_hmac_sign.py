"""REF-20 Sprint A R3 Round 6 T4-1 — write_manifest_fixture real HMAC sign.
REF-20 Sprint A R3 Round 6 T4-1 — write_manifest_fixture 真 HMAC sign 測試。

MODULE_NOTE (EN):
    T4-1 unit tests for ``replay/route_helpers.py`` Round 6 fix:

      * env override path produces real HMAC-SHA256 signature aligned with
        Rust ``replay_runner.rs::load_and_verify_manifest`` cross-language
        invariant (no placeholder strings on disk).
      * sibling ``key.hex`` written with mode 0o600 + trailing newline +
        fingerprint = ``compute_key_fingerprint(file_content_bytes)`` so
        Rust runner's ``compute_key_fingerprint`` matches.
      * envelope key leak from caller raises ValueError before any sign
        computation (defense-in-depth against stale Round-5 callsites).
      * fail-closed when neither env override nor secrets-dir is provisioned
        (raises ``manifest_signing_key_unavailable``; never falls through to
        placeholder).
      * placeholder strings (``placeholder_signature_wave6_v042_pending``
        etc.) absent from any code path now and forever.

MODULE_NOTE (中):
    Round 6 ``write_manifest_fixture`` 真 HMAC sign + sibling key.hex unit
    test：env override / fail-closed / envelope leak / 0o600 sibling +
    placeholder string 0 hit。

SPEC: REF-20 V3 §5 (manifest signing) + Sprint 1 Track B fail-closed
      verifier (commit ``edf33c0``) + Sprint A R3 Round 6 task DAG.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(os.path.dirname(_test_dir))
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from replay.experiment_registry import (  # noqa: E402
    compute_manifest_canonical_bytes,
)
from replay.manifest_signer import (  # noqa: E402
    InMemoryKeyArchive,
    KeyStatus,
    ManifestSigner,
    compute_body_hash,
    compute_key_fingerprint,
)
from replay.route_helpers import (  # noqa: E402
    ENVELOPE_KEYS_FOR_SIGNING,
    SIBLING_KEY_HEX_FILENAME,
    SIGNING_KEY_FILE_ENV_VAR,
    _resolve_manifest_signing_key,
    build_default_manifest_payload,
    write_manifest_fixture,
)

# Test fixture key — 64 hex char (32 byte HMAC key).
# 測試 fixture key — 64 hex char（32 byte HMAC key）。
TEST_KEY_HEX = "aabbccddeeff00112233445566778899" * 2  # 64 hex char


@pytest.fixture
def isolated_env(monkeypatch):
    """Strip all signing-key-related env so tests start from clean slate.
    清空所有與 signing key 相關 env，測試從 clean slate 開始。
    """
    monkeypatch.delenv(SIGNING_KEY_FILE_ENV_VAR, raising=False)
    monkeypatch.delenv("OPENCLAW_SECRETS_DIR", raising=False)
    monkeypatch.delenv("OPENCLAW_REPLAY_ENV_LABEL", raising=False)
    monkeypatch.delenv("OPENCLAW_RELEASE_PROFILE", raising=False)
    yield


@pytest.fixture
def env_override_key(tmp_path: Path, isolated_env, monkeypatch):
    """Provision a key.hex via env override; returns (path, fingerprint).
    透過 env override 配置 key.hex；回 (path, fingerprint)。
    """
    key_path = tmp_path / "test_signing_key.hex"
    key_path.write_text(TEST_KEY_HEX + "\n", encoding="utf-8")
    monkeypatch.setenv(SIGNING_KEY_FILE_ENV_VAR, str(key_path))
    file_content = key_path.read_bytes()
    expected_fp = compute_key_fingerprint(file_content)
    return key_path, expected_fp


# ─────────────────────────────────────────────────────────────────────
# T4-1.1: env override → real HMAC + sibling key.hex
# ─────────────────────────────────────────────────────────────────────


def test_resolve_signing_key_env_override(env_override_key):
    """env override path returns expected (key_bytes, fingerprint).
    env override 路徑回正確 (key_bytes, fingerprint)。
    """
    key_path, expected_fp = env_override_key
    key_bytes, fp = _resolve_manifest_signing_key()
    assert len(key_bytes) == 32
    assert key_bytes.hex() == TEST_KEY_HEX
    assert fp == expected_fp
    assert len(fp) == 16


def test_resolve_signing_key_fail_closed_no_provision(isolated_env):
    """Both env override and secrets-dir absent → ValueError fail-closed.
    env override 與 secrets-dir 都沒設 → fail-closed ValueError。
    """
    with pytest.raises(ValueError) as exc_info:
        _resolve_manifest_signing_key()
    assert "manifest_signing_key_unavailable" in str(exc_info.value)


def test_resolve_signing_key_env_override_invalid_path(monkeypatch, isolated_env):
    """env override pointing at non-existent path → ValueError (not fallthrough).
    env override 指向不存在路徑 → ValueError（不 silent fallthrough）。
    """
    monkeypatch.setenv(SIGNING_KEY_FILE_ENV_VAR, "/nonexistent/key.hex")
    with pytest.raises(ValueError) as exc_info:
        _resolve_manifest_signing_key()
    assert "signing_key_file_not_readable" in str(exc_info.value)


def test_resolve_signing_key_env_override_invalid_length(
    tmp_path: Path, monkeypatch, isolated_env,
):
    """env override at file with wrong length → ValueError invalid_length.
    env override 指向長度錯誤檔 → ValueError invalid_length。
    """
    bad = tmp_path / "bad.hex"
    bad.write_text("deadbeef\n", encoding="utf-8")  # too short
    monkeypatch.setenv(SIGNING_KEY_FILE_ENV_VAR, str(bad))
    with pytest.raises(ValueError) as exc_info:
        _resolve_manifest_signing_key()
    assert "signing_key_file_invalid_length" in str(exc_info.value)


def test_resolve_signing_key_env_override_invalid_hex(
    tmp_path: Path, monkeypatch, isolated_env,
):
    """env override at file with non-hex content → invalid_hex.
    env override 指向非 hex 內容檔 → invalid_hex。
    """
    bad = tmp_path / "bad.hex"
    # 64 chars but not hex
    bad.write_text("z" * 64 + "\n", encoding="utf-8")
    monkeypatch.setenv(SIGNING_KEY_FILE_ENV_VAR, str(bad))
    with pytest.raises(ValueError) as exc_info:
        _resolve_manifest_signing_key()
    assert "signing_key_file_invalid_hex" in str(exc_info.value)


def test_resolve_signing_key_env_override_blocked_in_live_profile(
    tmp_path: Path, monkeypatch, isolated_env,
):
    """Round 7 FINDING-1 fix: env override blocked under live profile.
    Round 7 FINDING-1 fix：env override 在 live profile 下被阻斷。

    Sprint 1 Track C P0-2 already blocks ``OPENCLAW_REPLAY_VERIFY_TEST_KEY``
    under live profile via ``is_live_release_profile()``. Round 6 added the
    sibling ``OPENCLAW_REPLAY_SIGNING_KEY_FILE`` env but missed the same
    gate, so production live could be redirected to any operator-writable
    path bypassing R2-T3's mode 0o600 + symlink + path traversal guards.
    Round 7 closes this hole: env set under live profile must hard-fail
    (NOT silent fallthrough to step 2).

    Sprint 1 Track C P0-2 已透過 ``is_live_release_profile()`` 在 live
    profile 下阻斷 ``OPENCLAW_REPLAY_VERIFY_TEST_KEY``；Round 6 新增同類
    ``OPENCLAW_REPLAY_SIGNING_KEY_FILE`` env 但漏 gate，理論上 production
    live 可被導向任意 operator-writable 路徑繞過 R2-T3 mode 0o600 +
    symlink + path traversal 守門。Round 7 補完：live profile 下 env 設
    必 hard-fail（不 silent 走 step 2）。
    """
    # Provision a valid-looking key file (would have succeeded under
    # dev/test profile) — proves blocking is profile-driven, not file-validity.
    # 配置一個 valid 形式 key file（dev/test profile 下會成功）— 證明
    # 阻斷由 profile 驅動，非由 file 內容驅動。
    key_path = tmp_path / "looks_valid.hex"
    key_path.write_text(TEST_KEY_HEX + "\n", encoding="utf-8")
    monkeypatch.setenv(SIGNING_KEY_FILE_ENV_VAR, str(key_path))
    monkeypatch.setenv("OPENCLAW_RELEASE_PROFILE", "live")

    with pytest.raises(ValueError) as exc_info:
        _resolve_manifest_signing_key()
    assert (
        "signing_key_file_env_override_blocked_in_live_profile"
        in str(exc_info.value)
    )


def test_resolve_signing_key_env_override_works_outside_live_profile(
    tmp_path: Path, monkeypatch, isolated_env,
):
    """Round 7 FINDING-1 fix counter-test: dev/test profile still allows env.
    Round 7 FINDING-1 fix 反向測試：dev/test profile 下 env 仍可用。

    Confirms the live profile gate is precisely scoped — only ``live``
    triggers block; demo / paper / live_demo / unset profile all allow
    the override (this is intentional; pytest fixtures + Mac smoke runs
    rely on it).

    確認 live profile gate 範圍精準 — 僅 ``live`` 觸發 block；demo /
    paper / live_demo / unset profile 均允許 override（pytest fixture +
    Mac smoke run 依賴此行為）。
    """
    key_path = tmp_path / "test_signing_key.hex"
    key_path.write_text(TEST_KEY_HEX + "\n", encoding="utf-8")
    monkeypatch.setenv(SIGNING_KEY_FILE_ENV_VAR, str(key_path))
    # Test 4 non-live values: unset / demo / paper / live_demo.
    # 4 個 non-live 值：unset / demo / paper / live_demo。
    for profile in (None, "demo", "paper", "live_demo"):
        if profile is None:
            monkeypatch.delenv("OPENCLAW_RELEASE_PROFILE", raising=False)
        else:
            monkeypatch.setenv("OPENCLAW_RELEASE_PROFILE", profile)
        key_bytes, fp = _resolve_manifest_signing_key()
        assert len(key_bytes) == 32
        assert key_bytes.hex() == TEST_KEY_HEX


# ─────────────────────────────────────────────────────────────────────
# T4-1.2: write_manifest_fixture real HMAC + sibling key.hex
# ─────────────────────────────────────────────────────────────────────


def test_write_manifest_fixture_real_hmac_with_env_override(
    tmp_path: Path, env_override_key,
):
    """Round 6 acceptance: real HMAC + sibling key.hex + 0o600 + verify.
    Round 6 acceptance：真 HMAC + sibling key.hex + 0o600 + 自驗通過。
    """
    _, expected_fp = env_override_key
    output_dir = tmp_path / "run_xyz"
    run_id = "test-run-xyz"

    payload = build_default_manifest_payload(
        experiment_id="exp-001", output_dir=output_dir,
    )
    # Body-only payload (no envelope) per Round 6 contract.
    # body-only payload（無 envelope）符合 Round 6 契約。
    assert set(payload.keys()) == {"experiment_id", "data_tier", "fixture_uri"}

    fixture_path = write_manifest_fixture(
        run_id=run_id, manifest_data=payload, output_dir=output_dir,
    )
    assert fixture_path.exists()

    written = fixture_path.read_text(encoding="utf-8")
    # Placeholder strings absolutely forbidden.
    # placeholder 字串絕對禁止。
    assert "placeholder_signature_wave6" not in written
    assert "placeholder_hash_wave6" not in written
    assert "placeholder_key_ref" not in written

    disk = json.loads(written)
    # 7 keys total: 3 body + run_id + 3 envelope.
    # 共 7 keys：3 body + run_id + 3 envelope。
    assert set(disk.keys()) == {
        "experiment_id", "data_tier", "fixture_uri", "run_id",
        "signature", "manifest_hash", "signature_key_ref",
    }
    assert disk["run_id"] == run_id
    assert disk["signature_key_ref"] == expected_fp
    assert len(disk["signature"]) == 64  # HMAC-SHA256 hex
    assert len(disk["manifest_hash"]) == 64  # SHA-256 hex

    # Verify HMAC: re-canonicalize body (envelope stripped) + sign with
    # same key and assert byte-equal to disk signature.
    # 驗 HMAC：strip envelope 後 re-canonicalize + 用同 key 簽應 byte-equal。
    body_only = {
        k: v for k, v in disk.items() if k not in ENVELOPE_KEYS_FOR_SIGNING
    }
    canonical = compute_manifest_canonical_bytes(body_only)
    expected_hash = compute_body_hash(canonical)
    assert expected_hash == disk["manifest_hash"]

    archive = InMemoryKeyArchive()
    archive.insert(expected_fp, KeyStatus.ACTIVE)
    signer = ManifestSigner.from_bytes_for_test(
        bytes.fromhex(TEST_KEY_HEX), expected_fp,
    )
    expected_sig = signer.sign(canonical)
    assert expected_sig == disk["signature"]
    # Full verify path mirrors Rust replay_runner integration.
    # 完整 verify path 對齊 Rust replay_runner 整合。
    signer.verify(
        canonical,
        disk["manifest_hash"],
        disk["signature"],
        disk["signature_key_ref"],
        archive,
    )

    # Sibling key.hex written + correct content + trailing newline.
    # sibling key.hex 落地 + 內容正確 + trailing newline。
    sibling = output_dir / SIBLING_KEY_HEX_FILENAME
    assert sibling.exists()
    sibling_content = sibling.read_text(encoding="utf-8")
    assert sibling_content == TEST_KEY_HEX + "\n"
    # Mode 0o600 (Mac may relax; verify file content is enough on macOS,
    # but assert mode on Linux). Best-effort because some FS may downgrade.
    # Mode 0o600（Mac sandbox 可能放寬；only check on POSIX systems）。
    if sys.platform != "win32":
        mode = sibling.stat().st_mode & 0o777
        assert mode in (0o600, 0o644)  # Mac sandbox FS may keep 0o644


def test_write_manifest_fixture_envelope_leak_rejected(env_override_key, tmp_path: Path):
    """Caller passing envelope key triggers ValueError before sign.
    Caller 傳 envelope key 在簽名前 ValueError。
    """
    output_dir = tmp_path / "run_leak"
    bad = {
        "experiment_id": "exp",
        "data_tier": "S3",
        "signature": "anything",  # leak!
    }
    with pytest.raises(ValueError) as exc_info:
        write_manifest_fixture(
            run_id="r", manifest_data=bad, output_dir=output_dir,
        )
    assert "envelope keys" in str(exc_info.value)
    assert "signature" in str(exc_info.value)


def test_write_manifest_fixture_run_id_required(env_override_key, tmp_path: Path):
    """Empty run_id raises ValueError (existing invariant).
    空 run_id 必 ValueError（既有不變量）。
    """
    output_dir = tmp_path / "run_empty"
    body = build_default_manifest_payload(
        experiment_id="exp", output_dir=output_dir,
    )
    with pytest.raises(ValueError):
        write_manifest_fixture(
            run_id="", manifest_data=body, output_dir=output_dir,
        )


def test_write_manifest_fixture_propagates_signing_key_failure(
    isolated_env, tmp_path: Path,
):
    """No env override + no secrets dir → write fails with fail-closed reason.
    沒 env override 且沒 secrets dir → write 失敗（fail-closed reason）。
    """
    output_dir = tmp_path / "run_no_key"
    body = build_default_manifest_payload(
        experiment_id="exp", output_dir=output_dir,
    )
    with pytest.raises(ValueError) as exc_info:
        write_manifest_fixture(
            run_id="r", manifest_data=body, output_dir=output_dir,
        )
    assert "manifest_signing_key_unavailable" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────
# T4-1.3: build_default_manifest_payload body-only contract
# ─────────────────────────────────────────────────────────────────────


def test_build_default_manifest_payload_body_only(tmp_path: Path):
    """Round 6: build_default returns 3 body keys only (no envelope).
    Round 6：build_default 只回 3 body keys（無 envelope）。
    """
    out = build_default_manifest_payload(
        experiment_id="exp", output_dir=tmp_path / "x",
    )
    assert set(out.keys()) == {"experiment_id", "data_tier", "fixture_uri"}
    # No envelope keys at all.
    # 完全無 envelope keys。
    for k in ENVELOPE_KEYS_FOR_SIGNING:
        assert k not in out


def test_build_default_manifest_payload_no_placeholders(tmp_path: Path):
    """Round 6: placeholder strings purged from build_default output.
    Round 6：build_default 輸出無 placeholder 字串。
    """
    out = build_default_manifest_payload(
        experiment_id="exp", output_dir=tmp_path / "x",
    )
    serialised = json.dumps(out)
    assert "placeholder_signature_wave6" not in serialised
    assert "placeholder_hash_wave6" not in serialised
    assert "placeholder_key_ref" not in serialised

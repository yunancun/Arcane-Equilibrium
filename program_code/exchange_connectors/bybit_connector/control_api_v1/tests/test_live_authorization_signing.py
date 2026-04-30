"""
Tests for LIVE-GATE-BINDING-1 signed authorization helpers in live_trust_routes.

Exercises the pure signing primitives + file IO in isolation without standing
up the FastAPI stack. End-to-end flow through /api/v1/live/auth/renew is
covered by existing trust-engine integration tests.

測試 live_trust_routes 內 LIVE-GATE-BINDING-1 簽名輔助函數。
"""

from __future__ import annotations

import hmac
import hashlib
import json
import os
from pathlib import Path

import pytest

from app.earned_trust_engine import TrustTier
from app import live_trust_routes as ltr


TEST_SECRET = "test-ipc-secret-do-not-use-in-prod"


@pytest.fixture
def secrets_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """
    Redirect both secret dir + IPC secret to test-local values.
    Returns the live-slot dir.
    """
    monkeypatch.setenv("OPENCLAW_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCLAW_IPC_SECRET", TEST_SECRET)
    live_dir = tmp_path / "live"
    live_dir.mkdir(parents=True, exist_ok=True)
    return live_dir


def _canonical_reference(
    version: int,
    tier: str,
    issued: int,
    expires: int,
    op: str,
    approved_system_mode: str,
    envs: list[str],
) -> str:
    """Independent re-implementation to guard against drift."""
    envs_sorted = sorted(set(envs))
    return f"{version}|{tier}|{issued}|{expires}|{op}|{approved_system_mode}|{','.join(envs_sorted)}"


def test_canonical_payload_matches_spec():
    """Python canonical format must stay byte-for-byte compatible with Rust."""
    payload = ltr._canonical_authorization_payload(
        version=2,
        tier="T0_ENTRY",
        issued_at_ms=1_700_000_000_000,
        expires_at_ms=1_700_000_000_000 + 24 * 3600 * 1000,
        operator_id="ncyu",
        approved_system_mode="live_reserved",
        env_allowed=["live_demo"],
    )
    assert payload == "2|T0_ENTRY|1700000000000|1700086400000|ncyu|live_reserved|live_demo"


def test_canonical_payload_sorts_and_dedups_envs():
    """Rust sorts+dedups env_allowed before signing — Python must do the same."""
    payload = ltr._canonical_authorization_payload(
        version=2,
        tier="T2_ESTABLISHED",
        issued_at_ms=1,
        expires_at_ms=2,
        operator_id="op",
        approved_system_mode="live_reserved",
        env_allowed=["mainnet", "live_demo", "live_demo"],
    )
    assert payload.endswith("|live_demo,mainnet")
    assert "live_demo,live_demo" not in payload


def test_signature_matches_manual_hmac():
    """Reference-check the HMAC output."""
    payload = "2|T0_ENTRY|1|2|op|live_reserved|live_demo"
    expected = hmac.new(
        TEST_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    assert ltr._sign_authorization_payload(payload, TEST_SECRET) == expected


def test_write_signed_live_authorization_creates_file(secrets_tmp: Path):
    """End-to-end: write → file exists with chmod 600 → content verifies."""
    # bybit_endpoint must exist for env derivation
    (secrets_tmp / "bybit_endpoint").write_text("demo")

    expires = int(1_800_000_000_000)  # far-future
    record = ltr._write_signed_live_authorization(
        operator_id="ncyu",
        tier=TrustTier.T0_ENTRY.value,
        expires_at_ms=expires,
    )

    path = secrets_tmp / "authorization.json"
    assert path.exists(), "authorization.json not created"

    # File permissions: owner r/w only (600) — check stat mode low 9 bits
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600, f"expected 600, got {oct(mode)}"

    # File contents round-trip + signature verifies
    loaded = json.loads(path.read_text())
    assert loaded["version"] == 2
    assert loaded["tier"] == "T0_ENTRY"
    assert loaded["expires_at_ms"] == expires
    assert loaded["operator_id"] == "ncyu"
    assert loaded["approved_system_mode"] == "live_reserved"
    assert loaded["env_allowed"] == ["live_demo"]
    # Returned record matches on-disk
    assert loaded == record

    payload = ltr._canonical_authorization_payload(
        version=loaded["version"],
        tier=loaded["tier"],
        issued_at_ms=loaded["issued_at_ms"],
        expires_at_ms=loaded["expires_at_ms"],
        operator_id=loaded["operator_id"],
        approved_system_mode=loaded["approved_system_mode"],
        env_allowed=loaded["env_allowed"],
    )
    expected_sig = hmac.new(
        TEST_SECRET.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()
    assert loaded["sig"] == expected_sig


def test_write_fails_without_ipc_secret(secrets_tmp: Path, monkeypatch):
    """No IPC_SECRET → raise, don't silently write an unsigned file."""
    monkeypatch.delenv("OPENCLAW_IPC_SECRET", raising=False)
    (secrets_tmp / "bybit_endpoint").write_text("demo")

    with pytest.raises(RuntimeError, match="OPENCLAW_IPC_SECRET"):
        ltr._write_signed_live_authorization(
            operator_id="ncyu",
            tier=TrustTier.T0_ENTRY.value,
            expires_at_ms=1_800_000_000_000,
        )
    assert not (secrets_tmp / "authorization.json").exists()


def test_mainnet_endpoint_produces_mainnet_env_allowed(secrets_tmp: Path):
    """env_allowed follows current bybit_endpoint file content."""
    (secrets_tmp / "bybit_endpoint").write_text("mainnet")
    record = ltr._write_signed_live_authorization(
        operator_id="ncyu",
        tier=TrustTier.T2_ESTABLISHED.value,
        expires_at_ms=1_800_000_000_000,
    )
    assert record["env_allowed"] == ["mainnet"]


def test_missing_endpoint_file_defaults_to_mainnet(secrets_tmp: Path):
    """Fail-safe: missing bybit_endpoint → mainnet (not silent demo)."""
    # Do NOT create bybit_endpoint
    record = ltr._write_signed_live_authorization(
        operator_id="ncyu",
        tier=TrustTier.T0_ENTRY.value,
        expires_at_ms=1_800_000_000_000,
    )
    assert record["env_allowed"] == ["mainnet"]


def test_delete_removes_authorization_file(secrets_tmp: Path):
    """Revoke flow must actually delete the file so Rust stops trusting it."""
    (secrets_tmp / "bybit_endpoint").write_text("demo")
    ltr._write_signed_live_authorization(
        operator_id="ncyu",
        tier=TrustTier.T0_ENTRY.value,
        expires_at_ms=1_800_000_000_000,
    )
    path = secrets_tmp / "authorization.json"
    assert path.exists()

    assert ltr._delete_live_authorization_file() is True
    assert not path.exists()

    # Second delete is a no-op (returns False, does not raise)
    assert ltr._delete_live_authorization_file() is False


def test_read_signed_authorization_status_reports_missing(secrets_tmp: Path):
    """GUI status must distinguish trust TTL from missing Rust signed auth."""
    status = ltr._read_signed_live_authorization_status(now_ms=1_700_000_000_000)

    assert status["status"] == "missing"
    assert status["present"] is False
    assert status["valid_for_engine"] is False
    assert status["reason"] == "authorization_json_missing"


def test_read_signed_authorization_status_validates_written_record(secrets_tmp: Path):
    """Status helper mirrors the Rust live gate for a valid authorization.json."""
    (secrets_tmp / "bybit_endpoint").write_text("demo")
    expires = 1_800_000_000_000
    ltr._write_signed_live_authorization(
        operator_id="ncyu",
        tier=TrustTier.T0_ENTRY.value,
        expires_at_ms=expires,
    )

    status = ltr._read_signed_live_authorization_status(now_ms=1_700_000_000_000)

    assert status["status"] == "valid"
    assert status["valid_for_engine"] is True
    assert status["expires_at_ms"] == expires
    assert status["tier"] == "T0_ENTRY"
    assert status["endpoint"] == "live_demo"
    assert status["env_allowed"] == ["live_demo"]


def test_read_signed_authorization_status_reports_expired(secrets_tmp: Path):
    """Expired signed auth is invalid even if earned-trust state still has TTL."""
    (secrets_tmp / "bybit_endpoint").write_text("demo")
    expires = 1_700_000_000_000
    ltr._write_signed_live_authorization(
        operator_id="ncyu",
        tier=TrustTier.T0_ENTRY.value,
        expires_at_ms=expires,
    )

    status = ltr._read_signed_live_authorization_status(now_ms=expires + 1)

    assert status["status"] == "expired"
    assert status["valid_for_engine"] is False
    assert status["reason"] == "authorization_json_expired"


def test_atomic_write_uses_rename(secrets_tmp: Path, monkeypatch):
    """
    Simulate crash between write + rename: no partial authorization.json visible.
    We monkeypatch os.replace to raise AFTER tmpfile is written, then confirm
    the final authorization.json was never created (prevents Rust from parsing
    a half-written record).
    """
    (secrets_tmp / "bybit_endpoint").write_text("demo")
    original_replace = os.replace

    def boom(src, dst):
        raise RuntimeError("simulated crash mid-rename")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(RuntimeError, match="simulated crash"):
        ltr._write_signed_live_authorization(
            operator_id="ncyu",
            tier=TrustTier.T0_ENTRY.value,
            expires_at_ms=1_800_000_000_000,
        )
    assert not (secrets_tmp / "authorization.json").exists()

    # Tmpfile also cleaned up
    leftovers = [p for p in secrets_tmp.glob(".authorization.*.tmp")]
    assert leftovers == [], f"tmpfile leaked: {leftovers}"

    # Restore and prove normal write still works
    monkeypatch.setattr(os, "replace", original_replace)
    ltr._write_signed_live_authorization(
        operator_id="ncyu",
        tier=TrustTier.T0_ENTRY.value,
        expires_at_ms=1_800_000_000_000,
    )
    assert (secrets_tmp / "authorization.json").exists()


def test_tier_wire_names_cover_all_tiers():
    """Every TrustTier must have a wire name — else write() KeyErrors in prod."""
    for t in TrustTier:
        assert t in ltr._TIER_WIRE_NAME, f"TrustTier {t} missing wire name"
        assert ltr._TIER_WIRE_NAME[t] == t.name

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app import autonomy_totp


RFC6238_SHA1_SEED_B32 = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"


def _write_secret(path: Path, *, seed: str = RFC6238_SHA1_SEED_B32, digits: int = 6) -> None:
    path.write_text(
        json.dumps(
            {
                "totp_seed_b32": seed,
                "totp_digits": digits,
                "totp_interval_sec": 30,
                "totp_algorithm": "SHA1",
                "fingerprint": hashlib.sha256(seed.encode("utf-8")).hexdigest(),
            }
        ),
        encoding="utf-8",
    )


def test_totp_backend_missing_fails_closed(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENCLAW_AUTONOMY_TOTP_SECRET_FILE", str(tmp_path / "missing.json"))

    assert autonomy_totp.autonomy_totp_backend_configured() is False
    assert autonomy_totp.verify_autonomy_totp("123456") == (
        False,
        "backend_unreachable",
        "twofa_backend_down",
    )


def test_totp_verify_accepts_rfc6238_code(monkeypatch, tmp_path) -> None:
    secret = tmp_path / "autonomy_totp.json"
    _write_secret(secret)
    monkeypatch.setenv("OPENCLAW_AUTONOMY_TOTP_SECRET_FILE", str(secret))

    assert autonomy_totp.autonomy_totp_backend_configured() is True
    assert autonomy_totp.verify_autonomy_totp("287082", now=59) == (
        True,
        "TOTP",
        "success",
    )


def test_totp_verify_rejects_bad_code(monkeypatch, tmp_path) -> None:
    secret = tmp_path / "autonomy_totp.json"
    _write_secret(secret)
    monkeypatch.setenv("OPENCLAW_AUTONOMY_TOTP_SECRET_FILE", str(secret))

    assert autonomy_totp.verify_autonomy_totp("000000", now=59) == (
        False,
        "TOTP",
        "twofa_fail",
    )
    assert autonomy_totp.verify_autonomy_totp("not-six", now=59) == (
        False,
        "TOTP",
        "twofa_fail",
    )


def test_totp_fingerprint_mismatch_fails_closed(monkeypatch, tmp_path) -> None:
    secret = tmp_path / "autonomy_totp.json"
    secret.write_text(
        json.dumps(
            {
                "totp_seed_b32": RFC6238_SHA1_SEED_B32,
                "totp_digits": 6,
                "totp_interval_sec": 30,
                "totp_algorithm": "SHA1",
                "fingerprint": "0" * 64,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENCLAW_AUTONOMY_TOTP_SECRET_FILE", str(secret))

    assert autonomy_totp.autonomy_totp_backend_configured() is False
    assert autonomy_totp.verify_autonomy_totp("287082", now=59) == (
        False,
        "backend_unreachable",
        "twofa_backend_down",
    )

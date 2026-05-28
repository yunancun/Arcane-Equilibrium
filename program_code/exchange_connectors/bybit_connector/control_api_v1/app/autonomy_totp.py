"""Autonomy Level TOTP verifier.

The verifier is intentionally file-backed and fail-closed. It never generates
or prints a production secret; operator enrollment owns the secret file.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from pathlib import Path
import struct
import time
from typing import Any


@dataclass(frozen=True)
class AutonomyTotpConfig:
    seed_b32: str
    digits: int = 6
    interval_sec: int = 30
    algorithm: str = "SHA1"
    window_steps: int = 1


def _default_totp_secret_file() -> Path:
    explicit = os.environ.get("OPENCLAW_AUTONOMY_TOTP_SECRET_FILE")
    if explicit:
        return Path(explicit).expanduser()
    home = Path(os.environ.get("HOME", "~")).expanduser()
    return home / "BybitOpenClaw" / "secrets" / "vault" / "autonomy_totp.json"


def _normalize_seed(seed: str) -> str:
    return "".join(seed.split()).upper()


def _decode_base32(seed_b32: str) -> bytes:
    padded = seed_b32 + ("=" * ((8 - len(seed_b32) % 8) % 8))
    return base64.b32decode(padded, casefold=True)


def _load_totp_config() -> tuple[AutonomyTotpConfig | None, str | None]:
    path = _default_totp_secret_file()
    try:
        if not path.is_file():
            return None, "secret_file_missing"
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None, "secret_file_unreadable"
    if not isinstance(raw, dict):
        return None, "secret_file_invalid"

    seed = _normalize_seed(str(raw.get("totp_seed_b32") or raw.get("secret_b32") or ""))
    if not seed:
        return None, "secret_missing"
    try:
        _decode_base32(seed)
    except Exception:
        return None, "secret_invalid_base32"

    expected_fingerprint = str(raw.get("fingerprint") or "").strip().lower()
    if expected_fingerprint:
        actual = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(actual, expected_fingerprint):
            return None, "fingerprint_mismatch"

    algorithm = str(raw.get("totp_algorithm") or "SHA1").upper()
    if algorithm != "SHA1":
        return None, "unsupported_algorithm"
    try:
        digits = int(raw.get("totp_digits") or 6)
        interval = int(raw.get("totp_interval_sec") or 30)
        window = int(os.environ.get("OPENCLAW_AUTONOMY_TOTP_WINDOW_STEPS", "1"))
    except ValueError:
        return None, "secret_file_invalid"
    if digits not in (6, 8) or interval <= 0 or window < 0 or window > 2:
        return None, "secret_file_invalid"

    return AutonomyTotpConfig(
        seed_b32=seed,
        digits=digits,
        interval_sec=interval,
        algorithm=algorithm,
        window_steps=window,
    ), None


def autonomy_totp_backend_configured() -> bool:
    config, _ = _load_totp_config()
    return config is not None


def _totp_at(config: AutonomyTotpConfig, for_time: float) -> str:
    key = _decode_base32(config.seed_b32)
    counter = int(for_time // config.interval_sec)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    dbc = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(dbc % (10 ** config.digits)).zfill(config.digits)


def verify_autonomy_totp(code: str, *, now: float | None = None) -> tuple[bool, str, str]:
    config, err = _load_totp_config()
    if config is None:
        return False, "backend_unreachable", "twofa_backend_down"

    token = str(code or "").strip()
    if not token.isdigit() or len(token) != config.digits:
        return False, "TOTP", "twofa_fail"

    current_time = time.time() if now is None else now
    for step in range(-config.window_steps, config.window_steps + 1):
        candidate_time = current_time + (step * config.interval_sec)
        if hmac.compare_digest(_totp_at(config, candidate_time), token):
            return True, "TOTP", "success"
    return False, "TOTP", "twofa_fail"


__all__ = [
    "AutonomyTotpConfig",
    "autonomy_totp_backend_configured",
    "verify_autonomy_totp",
]

#!/usr/bin/python3
"""Sealed authorization-parameterized current-head generation pin."""

from __future__ import annotations

import hashlib
import base64
import os
import re
import stat
import sys
import types
from pathlib import Path
from typing import Callable


BASE_WRAPPER = Path(__file__).with_name("p0a_generation_pin_apply_v1.py")
BASE_WRAPPER_SHA256 = (
    "4ced9de5f688c2db0a12c1f11058001e069fc8e6f6e72dff299178136cd5e9b7"
)


def load_transaction_engine(*, after_open: Callable[[], None] | None = None):
    path_stat = BASE_WRAPPER.lstat()
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise RuntimeError("base_wrapper_not_regular")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(BASE_WRAPPER, flags)
    try:
        opened = os.fstat(fd)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (path_stat.st_dev, path_stat.st_ino)
        ):
            raise RuntimeError("base_wrapper_identity_mismatch")
        if after_open is not None:
            after_open()
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final = os.fstat(fd)
        if final.st_size != opened.st_size or final.st_mtime_ns != opened.st_mtime_ns:
            raise RuntimeError("base_wrapper_changed_during_read")
    finally:
        os.close(fd)
    raw = b"".join(chunks)
    if len(raw) != opened.st_size:
        raise RuntimeError("base_wrapper_short_read")
    if hashlib.sha256(raw).hexdigest() != BASE_WRAPPER_SHA256:
        raise RuntimeError("base_wrapper_sha256_mismatch")
    sys.dont_write_bytecode = True
    module = types.ModuleType("p0b_generation_pin_authorized_engine")
    module.__file__ = str(BASE_WRAPPER)
    module.__package__ = ""
    exec(compile(raw, str(BASE_WRAPPER), "exec", dont_inherit=True), module.__dict__)
    return module


def configure(
    engine,
    *,
    expected_head: str,
    old_head: str,
    old_pin_sha256: str,
    old_pin_base64: str,
    expected_old_pin_ino: int,
):
    try:
        decoded_old_pin = base64.b64decode(old_pin_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("old_pin_base64_invalid") from exc
    if (
        re.fullmatch(r"[0-9a-f]{40}", expected_head) is None
        or re.fullmatch(r"[0-9a-f]{40}", old_head) is None
        or re.fullmatch(r"[0-9a-f]{64}", old_pin_sha256) is None
        or hashlib.sha256(decoded_old_pin).hexdigest() != old_pin_sha256
        or not isinstance(expected_old_pin_ino, int)
        or expected_old_pin_ino <= 0
    ):
        raise RuntimeError("runtime_generation_binding_invalid")
    engine.SYSTEM_ENV = {
        "HOME": "/home/ncyu",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "USER": "ncyu",
        "LOGNAME": "ncyu",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "XDG_RUNTIME_DIR": "/run/user/1000",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "core.fsmonitor",
        "GIT_CONFIG_VALUE_0": "false",
        "GIT_CONFIG_KEY_1": "core.hooksPath",
        "GIT_CONFIG_VALUE_1": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    engine.DERIVE_ENV = {
        **engine.SYSTEM_ENV,
        "OPENCLAW_BASE_DIR": "/home/ncyu/BybitOpenClaw/srv",
        "OPENCLAW_DATA_DIR": "/home/ncyu/BybitOpenClaw/var/openclaw",
    }
    engine.SCHEMA = "p0b_generation_pin_apply_authorized_v1"
    engine.EXPECTED_HEAD = expected_head
    engine.OLD_HEAD = old_head
    engine.OLD_PIN_SHA256 = old_pin_sha256
    engine.OLD_PIN_BASE64 = old_pin_base64
    engine.EXPECTED_OLD_PIN_INO = expected_old_pin_ino
    return engine


def main(argv: list[str] | None = None) -> int:
    raise RuntimeError("explicit_runtime_generation_binding_required")


if __name__ == "__main__":
    raise SystemExit(main())

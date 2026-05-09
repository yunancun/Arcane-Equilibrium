"""Live / LiveDemo pipeline liveness healthcheck.
Live / LiveDemo 管線活性健康檢查。

This module is intentionally filesystem-only. It verifies whether the live
secret slot is configured, whether the signed live authorization file is
present, and whether the Rust live pipeline snapshot is fresh. It does not
read API key contents beyond non-empty existence checks, and it never writes
or renews ``authorization.json``.

本模組刻意保持純檔案系統檢查：只確認 live secret slot 是否配置、
簽名授權檔是否存在、Rust live 管線 snapshot 是否新鮮。不讀出 API key
內容（只判非空），也絕不寫入或續簽 ``authorization.json``。
"""

from __future__ import annotations

import os
import time
from pathlib import Path


_FALSE_VALUES = {"0", "false", "no", "off", "disabled"}
_TRUE_VALUES = {"1", "true", "yes", "on", "required"}
_DEFAULT_STALE_SECONDS = 180.0


def _flag_value(name: str) -> str:
    return os.environ.get(name, "").strip().lower()


def _resolve_secrets_base() -> Path:
    env_dir = os.environ.get("OPENCLAW_SECRETS_DIR")
    if env_dir:
        return Path(env_dir)
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE")
    if home:
        return Path(home) / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"
    return Path.cwd() / "BybitOpenClaw" / "secrets" / "secret_files" / "bybit"


def _resolve_data_dir() -> Path:
    return Path(os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"))


def _nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and bool(path.read_text(encoding="utf-8").strip())
    except OSError:
        return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _live_endpoint_label(live_dir: Path) -> str:
    endpoint = _read_text(live_dir / "bybit_endpoint").lower()
    return "live_demo" if endpoint == "demo" else "mainnet"


def _stale_seconds() -> float:
    raw = os.environ.get("OPENCLAW_LIVE_PIPELINE_STALE_SECONDS", "").strip()
    if not raw:
        return _DEFAULT_STALE_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return _DEFAULT_STALE_SECONDS
    return max(15.0, value)


def _age_seconds(path: Path, now: float) -> float | None:
    try:
        return max(0.0, now - path.stat().st_mtime)
    except OSError:
        return None


def check_56_live_pipeline_active(now: float | None = None) -> tuple[str, str]:
    """[56] Live / LiveDemo pipeline liveness.

    Default behavior is auto-detected:
    - live slot configured (non-empty ``api_key`` + ``api_secret``) => pipeline
      is expected and missing auth/stale snapshot is FAIL.
    - live slot not configured => PASS-skip unless
      ``OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED=1`` is set.

    ``OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED=0`` disables the check explicitly
    for local/dev environments that intentionally carry live-slot files but do
    not want LiveDemo spawned.

    [56] Live / LiveDemo 管線活性。默認 auto-detect：live slot 有非空
    ``api_key`` + ``api_secret`` 時即視為應啟動；此時 auth 缺失或 live
    snapshot stale 都是 FAIL。slot 未配置則 PASS-skip，除非設
    ``OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED=1``。
    """
    required_flag = _flag_value("OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED")
    if required_flag in _FALSE_VALUES:
        return (
            "PASS",
            "live pipeline health disabled by OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED=0",
        )

    now_ts = time.time() if now is None else now
    secrets_base = _resolve_secrets_base()
    live_dir = secrets_base / "live"
    has_key = _nonempty_file(live_dir / "api_key")
    has_secret = _nonempty_file(live_dir / "api_secret")
    configured = has_key and has_secret
    required = required_flag in _TRUE_VALUES

    if not configured:
        base = (
            f"live secret slot incomplete at {live_dir}: "
            f"api_key={has_key} api_secret={has_secret}"
        )
        if required:
            return ("FAIL", base + " — health required")
        return ("PASS", base + " — not configured; live pipeline liveness skipped")

    endpoint = _live_endpoint_label(live_dir)
    auth_path = live_dir / "authorization.json"
    if not _nonempty_file(auth_path):
        return (
            "FAIL",
            f"live pipeline expected endpoint={endpoint} but "
            f"auth=authorization_json_missing path={auth_path}; "
            "operator must renew via signed live-auth route, not manual file write",
        )

    data_dir = _resolve_data_dir()
    snapshot_path = data_dir / "pipeline_snapshot_live.json"
    age = _age_seconds(snapshot_path, now_ts)
    if age is None:
        return (
            "FAIL",
            f"live pipeline expected endpoint={endpoint} auth=present but "
            f"snapshot missing at {snapshot_path}",
        )

    threshold = _stale_seconds()
    if age > threshold:
        return (
            "FAIL",
            f"live pipeline expected endpoint={endpoint} auth=present but "
            f"snapshot stale age={age:.1f}s threshold={threshold:.0f}s "
            f"path={snapshot_path}",
        )

    return (
        "PASS",
        f"live pipeline active endpoint={endpoint} auth=present "
        f"snapshot_age={age:.1f}s threshold={threshold:.0f}s",
    )


"""replay_key_rotation_check.sh — pytest fixtures + scenarios.
replay_key_rotation_check.sh — pytest 場景測試。

MODULE_NOTE (EN): REF-20 R20-P2a-S1 (Wave 2 Batch 1). Pins three load-bearing
  behaviours of the rotation check cron so future edits cannot silently
  regress:
    1. V042 absent → fall back to filesystem mtime + 90d rule.
    2. Filesystem mtime > 90d (or within 7d alert window) → ALERT (exit 1).
    3. Filesystem mtime ≤ 83d (older than 7d window) → silent OK (exit 0).
  Mirrors the style of `test_edge_label_backfill_cron_env.py` (sealed env,
  subprocess.run, log file inspection).

MODULE_NOTE (中): REF-20 R20-P2a-S1（Wave 2 Batch 1）。將 rotation check
  cron 三條 load-bearing 行為釘死，未來編輯不能靜默回退：
    1. V042 缺 → fallback 到 filesystem mtime + 90d 規則。
    2. mtime > 90d（或進入 7d alert 視窗）→ ALERT（exit 1）。
    3. mtime ≤ 83d（早於 7d 視窗）→ 靜默 OK（exit 0）。
  風格對齊 `test_edge_label_backfill_cron_env.py`（密封 env、
  subprocess.run、log file 驗）。

Tests / 測試覆蓋:
  1. wrapper exists and bash -n passes
  2. V042 absent + mtime ≤ 83d → exit 0 silent (OK silent)
  3. V042 absent + mtime > 90d → exit 1 ALERT
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest


WRAPPER = (
    Path(__file__).resolve().parents[2]
    / "helper_scripts"
    / "cron"
    / "replay_key_rotation_check.sh"
)


def _run_wrapper(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run the cron wrapper with a sealed env (no inheritance from operator).
    用密封 env 跑 cron wrapper（不繼承 operator 的 shell env）。
    """
    return subprocess.run(
        ["bash", str(WRAPPER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _base_env(
    tmp_path: Path,
    secrets_dir: Path,
    secrets_root: Path | None = None,
) -> dict[str, str]:
    """Build hermetic env mirroring cron's barebones environment.
    建立密封 env 模擬 cron 的 barebones 環境。

    Defaults SECRETS_ROOT to a non-existent path so `psql` cannot be wired
    up by accident (forces the V042-absent fallback path; matters for these
    tests, which assert filesystem mtime behaviour).

    SECRETS_ROOT 預設不存在路徑，避免誤連 psql（強制走 V042-absent fallback
    路徑；本測試組驗的就是 filesystem mtime 行為）。
    """
    if secrets_root is None:
        secrets_root = tmp_path / "no_such_secrets_root"
    return {
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "OPENCLAW_BASE_DIR": str(WRAPPER.resolve().parents[2]),
        "OPENCLAW_DATA_DIR": str(tmp_path / "data"),
        "OPENCLAW_SECRETS_DIR": str(secrets_dir),
        "OPENCLAW_SECRETS_ROOT": str(secrets_root),
    }


def _seed_secrets_dir(secrets_dir: Path, envs: list[str]) -> None:
    """Create per-env subdirs under SECRETS_DIR (mirror runbook §3 layout).
    在 SECRETS_DIR 下建每 env 子目錄（鏡像 runbook §3 layout）。
    """
    for env_name in envs:
        (secrets_dir / env_name).mkdir(parents=True, exist_ok=True)


def _write_key_with_mtime(
    secrets_dir: Path, env_name: str, mtime_age_days: int
) -> Path:
    """Write a fake key file with mtime backdated by N days.
    寫一個 mtime 倒推 N 天的假 key 檔。
    """
    key_path = secrets_dir / env_name / "replay_signing_key"
    # Content does not matter for this script (it only reads mtime).
    # 本腳本只讀 mtime；內容不重要。
    key_path.write_text("0" * 64 + "\n", encoding="utf-8")
    key_path.chmod(0o600)
    backdated = time.time() - mtime_age_days * 86400
    os.utime(key_path, (backdated, backdated))
    return key_path


# ─── Tests / 測試 ────────────────────────────────────────────────────


def test_wrapper_exists_and_syntax_clean() -> None:
    """Wrapper script exists and passes ``bash -n`` static syntax check.
    Wrapper 檔案存在且 ``bash -n`` 靜態語法檢查通過。"""
    assert WRAPPER.exists(), f"missing wrapper: {WRAPPER}"
    rc = subprocess.run(
        ["bash", "-n", str(WRAPPER)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert rc.returncode == 0, f"bash -n failed: {rc.stderr}"


def test_v042_absent_mtime_within_grace_exits_0_silent(tmp_path: Path) -> None:
    """V042 absent + mtime ≤ 83d → exit 0 (rotation_due_at >7d in future).
    V042 缺 + mtime ≤ 83d → exit 0（rotation_due_at 未來 >7d）。

    With mtime backdated 30 days, due_at = mtime + 90d = +60d future, which
    is comfortably outside the 7d alert window. Expected: exit 0, no ALERT
    line in stderr, log file contains OK rows for all 3 envs.

    mtime 倒推 30 天，due_at = mtime + 90d = 未來 +60d，舒適在 7d 視窗外。
    期望：exit 0、stderr 無 ALERT、log 三 env 都 OK。
    """
    secrets_dir = tmp_path / "secrets" / "secret_files" / "bybit"
    _seed_secrets_dir(secrets_dir, ["paper", "demo", "live"])
    for env_name in ("paper", "demo", "live"):
        _write_key_with_mtime(secrets_dir, env_name, mtime_age_days=30)

    env = _base_env(tmp_path, secrets_dir)
    proc = _run_wrapper(env)

    assert proc.returncode == 0, (
        f"expected exit=0 (mtime within 90-7=83d window), "
        f"got {proc.returncode}; stderr={proc.stderr!r}; stdout={proc.stdout!r}"
    )
    # Silent: no ALERT line in stderr.
    # silent：stderr 無 ALERT 字串。
    assert "ALERT" not in proc.stderr, (
        f"stderr contained ALERT but mtime is within grace period: {proc.stderr!r}"
    )

    log_path = tmp_path / "data" / "logs" / "replay_key_rotation_check.log"
    assert log_path.exists(), f"missing log {log_path}"
    log_text = log_path.read_text(encoding="utf-8")
    # Each env should have OK row.
    # 每 env 應有 OK row。
    for env_name in ("paper", "demo", "live"):
        assert f"OK env={env_name}" in log_text, (
            f"OK row missing for env={env_name}; log:\n{log_text}"
        )


def test_v042_absent_mtime_past_due_exits_1_alert(tmp_path: Path) -> None:
    """V042 absent + mtime > 90d → exit 1 (rotation_due_at past).
    V042 缺 + mtime > 90d → exit 1（rotation_due_at 已過期）。

    With mtime backdated 95 days, due_at = mtime + 90d = -5d past, which is
    well inside the alert window (≤7d days_remaining, in fact negative).
    Expected: exit 1, stderr contains ALERT line for each affected env, log
    contains ALERT rows.

    mtime 倒推 95 天，due_at = mtime + 90d = 過去 -5d，遠在 alert 視窗內
    （days_remaining ≤7，實際負值）。期望：exit 1、stderr 每 env 一條
    ALERT、log 含 ALERT row。
    """
    secrets_dir = tmp_path / "secrets" / "secret_files" / "bybit"
    _seed_secrets_dir(secrets_dir, ["paper", "demo", "live"])
    for env_name in ("paper", "demo", "live"):
        _write_key_with_mtime(secrets_dir, env_name, mtime_age_days=95)

    env = _base_env(tmp_path, secrets_dir)
    proc = _run_wrapper(env)

    assert proc.returncode == 1, (
        f"expected exit=1 (3 envs past due), "
        f"got {proc.returncode}; stderr={proc.stderr!r}; stdout={proc.stdout!r}"
    )
    # Each env should appear in an ALERT line on stderr.
    # 每 env 應在 stderr 有 ALERT 行。
    for env_name in ("paper", "demo", "live"):
        assert f"ALERT env={env_name}" in proc.stderr, (
            f"ALERT line missing for env={env_name}; stderr:\n{proc.stderr}"
        )

    log_path = tmp_path / "data" / "logs" / "replay_key_rotation_check.log"
    assert log_path.exists(), f"missing log {log_path}"
    log_text = log_path.read_text(encoding="utf-8")
    for env_name in ("paper", "demo", "live"):
        assert f"ALERT env={env_name}" in log_text, (
            f"ALERT row missing in log for env={env_name}; log:\n{log_text}"
        )


def test_secrets_dir_missing_exits_2(tmp_path: Path) -> None:
    """SECRETS_DIR not exist → exit 2 (FATAL configuration).
    SECRETS_DIR 不存在 → exit 2（FATAL configuration）。
    """
    secrets_dir = tmp_path / "no_such_secrets_dir"  # intentionally not created
    env = _base_env(tmp_path, secrets_dir)
    proc = _run_wrapper(env)
    assert proc.returncode == 2, (
        f"expected exit=2 (SECRETS_DIR missing), "
        f"got {proc.returncode}; stderr={proc.stderr!r}"
    )
    assert "OPENCLAW_SECRETS_DIR does not exist" in proc.stderr, proc.stderr


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

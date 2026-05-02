"""Edge label backfill cron wrapper PG-creds sourcing tests.
邊緣標籤回填 cron wrapper PG 認證注入測試。

MODULE_NOTE (EN): LG5-W3-FUP-3-CRON-ENV (2026-05-02). E4 Linux regression
  for LG5-W3-FUP-2 Fix 1+2 reported real cron run failure with
  ``psycopg2.OperationalError: fe_sendauth: no password supplied`` —
  ``edge_label_backfill_cron.sh`` ran in cron's barebones env without
  inheriting OPENCLAW_DATABASE_URL / POSTGRES_* from the operator's
  interactive shell. Fix sources PG creds from
  ``$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env``
  per ``helper_scripts/linux_bootstrap_db.sh:41-45`` sibling pattern.
  These tests pin that behaviour so a future edit cannot silently
  reintroduce the regression.

MODULE_NOTE (中): LG5-W3-FUP-3-CRON-ENV（2026-05-02）。E4 Linux 回歸測試
  顯示真實 cron 跑失敗 ``psycopg2.OperationalError: fe_sendauth: no
  password supplied`` — ``edge_label_backfill_cron.sh`` 在 cron 極簡 env
  下沒繼承 OPENCLAW_DATABASE_URL / POSTGRES_*。修法為從
  ``$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env``
  抓 PG creds，對齊 ``linux_bootstrap_db.sh:41-45`` sibling pattern。
  這些測試把行為釘死，未來編輯不能靜默回退。

Tests / 測試覆蓋:
  1. env file missing -> exit 2 + FATAL stderr/log
  2. env file present but creds incomplete -> exit 2 + FATAL stderr/log
  3. env file complete -> wrapper proceeds; OPENCLAW_DATABASE_URL exported
     downstream (verified via mocked ``python3`` in PATH that echoes the
     env var into the wrapper log).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest


WRAPPER = (
    Path(__file__).resolve().parents[2]
    / "helper_scripts"
    / "cron"
    / "edge_label_backfill_cron.sh"
)


def _run_wrapper(env: dict[str, str]) -> subprocess.CompletedProcess:
    """Run the cron wrapper with a sealed env (no inheritance from operator).
    用密封 env 跑 cron wrapper（不繼承 operator 的 shell env）。
    """
    # Use ``env=...`` directly (we want a hermetic env mirroring cron's).
    # 直接用 env=...（要密封 env 模擬 cron 的執行環境）。
    return subprocess.run(
        ["bash", str(WRAPPER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _base_env(tmp_path: Path, secrets_root: Path) -> dict[str, str]:
    """Build a hermetic env mirroring cron's barebones environment.
    建立密封 env 模擬 cron 的 barebones 環境。

    Excludes anything from the operator's interactive shell — only the env
    vars cron itself would supply (HOME / PATH) plus the four wrapper
    inputs (OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR / OPENCLAW_SECRETS_ROOT).

    完全排除 operator 互動 shell 的變量 — 只給 cron 本身會供應的（HOME /
    PATH）加上 4 個 wrapper 輸入（OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR /
    OPENCLAW_SECRETS_ROOT）。
    """
    return {
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
        "OPENCLAW_BASE_DIR": str(WRAPPER.resolve().parents[2]),
        "OPENCLAW_DATA_DIR": str(tmp_path / "data"),
        "OPENCLAW_SECRETS_ROOT": str(secrets_root),
    }


def test_wrapper_exists_and_syntax_clean(tmp_path: Path) -> None:
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


def test_env_file_missing_exits_2_with_fatal(tmp_path: Path) -> None:
    """ENV file missing -> exit code 2 and FATAL message in stderr + log.
    env 檔缺 -> exit 2 且 stderr/log 含 FATAL 訊息。"""
    secrets_root = tmp_path / "no_such_secrets"  # intentionally not created
    env = _base_env(tmp_path, secrets_root)
    proc = _run_wrapper(env)

    assert proc.returncode == 2, (
        f"expected exit=2 (env file missing FATAL), "
        f"got {proc.returncode}; stderr={proc.stderr!r}"
    )
    assert "FATAL: env file missing" in proc.stderr, proc.stderr

    # Also verify the wrapper writes FATAL to its log (operator triage path).
    # 同時確認 wrapper 把 FATAL 寫進 log（operator 排查路徑）。
    log_path = tmp_path / "data" / "logs" / "edge_label_backfill_cron.log"
    assert log_path.exists(), f"wrapper did not create log at {log_path}"
    assert "FATAL: env file missing" in log_path.read_text(encoding="utf-8")


def test_env_file_creds_incomplete_exits_2_with_fatal(tmp_path: Path) -> None:
    """ENV file present but missing PASSWORD/USER/DB -> exit 2 + FATAL.
    env 檔存在但缺 PASSWORD/USER/DB -> exit 2 + FATAL。"""
    secrets_root = tmp_path / "secrets"
    env_file_dir = secrets_root / "environment_files"
    env_file_dir.mkdir(parents=True)
    # Only POSTGRES_DB present; PASSWORD + USER missing.
    # 只給 POSTGRES_DB；PASSWORD + USER 缺。
    (env_file_dir / "basic_system_services.env").write_text(
        "POSTGRES_DB=trading_ai\n", encoding="utf-8"
    )

    env = _base_env(tmp_path, secrets_root)
    proc = _run_wrapper(env)

    assert proc.returncode == 2, (
        f"expected exit=2 (creds incomplete FATAL), "
        f"got {proc.returncode}; stderr={proc.stderr!r}"
    )
    assert "FATAL: PG creds incomplete" in proc.stderr, proc.stderr
    log_path = tmp_path / "data" / "logs" / "edge_label_backfill_cron.log"
    assert log_path.exists()
    assert "FATAL: PG creds incomplete" in log_path.read_text(encoding="utf-8")


def test_env_file_complete_exports_database_url(tmp_path: Path) -> None:
    """Complete creds -> wrapper proceeds; mocked python3 sees DSN exported.
    完整 creds -> wrapper 繼續；mocked python3 看到 DSN 已 export。

    Strategy: shadow ``python3`` in PATH with a fake that echoes the env
    var the wrapper exported, so we can confirm the export reached the
    downstream subprocess (the actual python module would need a live PG).

    策略：用 fake python3 shadow 真 python3，讓它 echo wrapper export 的 env
    var；確認 export 真到下游 subprocess（真 python module 需要 live PG）。
    """
    secrets_root = tmp_path / "secrets"
    env_file_dir = secrets_root / "environment_files"
    env_file_dir.mkdir(parents=True)
    (env_file_dir / "basic_system_services.env").write_text(
        textwrap.dedent(
            """\
            POSTGRES_PASSWORD=secret_pw
            POSTGRES_USER=tradebot
            POSTGRES_DB=trading_ai
            POSTGRES_PORT=15432
            """
        ),
        encoding="utf-8",
    )

    # Shadow python3 with a script that echoes the env then exits 0.
    # 用一個 echo env 然後 exit 0 的 script shadow python3。
    mock_bin = tmp_path / "mock_bin"
    mock_bin.mkdir()
    mock_python3 = mock_bin / "python3"
    mock_python3.write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            echo "MOCK_PY3_DSN=${OPENCLAW_DATABASE_URL:-UNSET}"
            exit 0
            """
        ),
        encoding="utf-8",
    )
    mock_python3.chmod(0o755)

    env = _base_env(tmp_path, secrets_root)
    # Prepend mock_bin so wrapper picks our fake python3 (cron-style PATH).
    # Prepend mock_bin 讓 wrapper 抓 fake python3（cron 風格 PATH）。
    env["PATH"] = f"{mock_bin}:{env['PATH']}"

    proc = _run_wrapper(env)

    assert proc.returncode == 0, (
        f"expected exit=0 with complete creds + mock python3, "
        f"got {proc.returncode}; stderr={proc.stderr!r}; stdout={proc.stdout!r}"
    )

    log_path = tmp_path / "data" / "logs" / "edge_label_backfill_cron.log"
    assert log_path.exists(), f"missing log {log_path}"
    log_text = log_path.read_text(encoding="utf-8")
    expected_dsn = (
        "MOCK_PY3_DSN=postgresql://redacted@127.0.0.1:15432/trading_ai"
    )
    assert expected_dsn in log_text, (
        f"DSN not exported as expected. log_text:\n{log_text}"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

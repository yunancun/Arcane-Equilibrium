"""polymarket_axis cron wrapper / installer 靜態測試。

證硬約束（不執行 wrapper 主體，純文本 + bash -n）：
  - daily 04:41 UTC 排程；hourly 行默認以「註釋停用」形組裝（活化 = operator）。
  - installer：Linux-only 守門 + APPLY env gate + idempotent guard + --remove。
  - wrapper：lock + heartbeat + fail-soft exit 0 + 零 secrets sourcing（R-0：
    本軸零 auth / 零 PG，wrapper 不得 source 任何 secrets env file）。
  - 跨平台紅線：零硬編碼 user path。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_CRON_DIR = Path(__file__).resolve().parents[1]
WRAPPER = _CRON_DIR / "polymarket_axis_cron.sh"
INSTALLER = _CRON_DIR / "install_polymarket_axis_cron.sh"


def _src(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_bash_syntax_ok(script):
    if shutil.which("bash") is None:
        pytest.skip("bash not available")
    proc = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_scripts_executable_and_strict_mode(script):
    assert script.stat().st_mode & 0o111, f"{script.name} not executable"
    assert "set -euo pipefail" in _src(script)


def test_installer_daily_schedule_0441_utc():
    src = _src(INSTALLER)
    assert 'ENTRY_DAILY="41 4 * * *' in src  # QC memo：daily 固定 UTC 時刻錯峰。


def test_installer_hourly_default_commented_operator_gated():
    src = _src(INSTALLER)
    # hourly 默認以註釋行安裝（QC memo §3：cron 活化 = operator 決策）。
    assert 'ENTRY_HOURLY="#${ENTRY_HOURLY_ACTIVE}"' in src
    assert 'OPENCLAW_POLYMARKET_CRON_HOURLY' in src
    assert 'OPENCLAW_POLYMARKET_CRON_TOPN_MINUTES="${OPENCLAW_POLYMARKET_CRON_TOPN_MINUTES:-7}"' in src
    assert 'ENTRY_HOURLY_ACTIVE="${OPENCLAW_POLYMARKET_CRON_TOPN_MINUTES} * * * *' in src
    assert '_validate_cron_minute_list "OPENCLAW_POLYMARKET_CRON_TOPN_MINUTES"' in src
    assert "7,22,37,52" in src


def test_installer_can_persist_query_set_env():
    src = _src(INSTALLER)
    assert "OPENCLAW_POLYMARKET_QUERY_SET" in src
    assert 'ENV_PREFIX="${ENV_PREFIX} OPENCLAW_POLYMARKET_QUERY_SET=${OPENCLAW_POLYMARKET_QUERY_SET}"' in src
    assert "must be v1 or v2" in src


def test_installer_linux_guard_apply_gate_idempotent_remove():
    src = _src(INSTALLER)
    assert 'uname -s' in src and '!= "Linux"' in src.replace("'", '"')
    assert "OPENCLAW_POLYMARKET_CRON_APPLY" in src
    assert "--remove" in src
    # idempotent guard：偵測既有條目即拒裝。
    assert 'grep -q "$MARKER"' in src
    assert 'MARKER="polymarket_axis_cron.sh"' in src


def test_wrapper_lock_heartbeat_failsoft():
    src = _src(WRAPPER)
    assert "polymarket_axis_cron.lock.d" in src
    assert "cron_heartbeat" in src
    assert src.rstrip().endswith("exit 0")  # fail-soft 收尾。
    assert 'case "$MODE"' in src and "hourly-topn" in src


def test_wrapper_query_set_env_pass_through():
    src = _src(WRAPPER)
    assert "OPENCLAW_POLYMARKET_QUERY_SET" in src
    assert 'QUERY_SET_ARGS=(--query-set "$QUERY_SET")' in src
    assert '"$PYBIN" "$CLI" --mode "$MODE" "${QUERY_SET_ARGS[@]}" --created-by-role cron' in src


def test_wrapper_zero_secrets_zero_pg():
    # R-0 紅線：本軸零 auth / 零 PG —— wrapper 不得 source secrets env、
    # 不得 export POSTGRES_*（對照 incident_sentinel_cron.sh 是「有 DB 軸」才有）。
    src = _src(WRAPPER)
    assert "OPENCLAW_SECRETS_ROOT" not in src
    assert "POSTGRES_" not in src
    assert "basic_system_services.env" not in src


@pytest.mark.parametrize("script", [WRAPPER, INSTALLER], ids=["wrapper", "installer"])
def test_no_hardcoded_user_paths(script):
    src = _src(script)
    assert "/home/ncyu" not in src
    assert "/Users/" not in src

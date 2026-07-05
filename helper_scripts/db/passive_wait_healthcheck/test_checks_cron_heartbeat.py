"""checks_cron_heartbeat [94] focused tests（冷審計 R2 F-1b）。

MODULE_NOTE:
  以 tmp_path + OPENCLAW_CRON_HEARTBEAT_DIR 隔離 sentinel 目錄,驗
  check_94_bybit_announcement_sentinel_cron_fires 三態:缺檔=WARN(missing)、
  過時 > 2h=WARN(stale)、新鮮=PASS;並驗 REQUIRED=1 升 FAIL。純函數不觸 runtime。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import helper_scripts.db.passive_wait_healthcheck.checks_cron_heartbeat as ch

_SENTINEL = "bybit_announcement_sentinel.last_fire"


def _set_dir(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENCLAW_CRON_HEARTBEAT_DIR", str(tmp_path))
    monkeypatch.delenv("OPENCLAW_CRON_HEARTBEAT_REQUIRED", raising=False)
    return tmp_path


def _touch(tmp_path: Path, age_seconds: float) -> None:
    p = tmp_path / _SENTINEL
    p.write_text("", encoding="utf-8")
    when = time.time() - age_seconds
    os.utime(p, (when, when))


def test_94_missing_is_warn(monkeypatch, tmp_path):
    _set_dir(monkeypatch, tmp_path)
    sev, msg = ch.check_94_bybit_announcement_sentinel_cron_fires()
    assert sev == "WARN", msg
    assert "heartbeat file missing" in msg
    assert "[94]" in msg


def test_94_fresh_is_pass(monkeypatch, tmp_path):
    _set_dir(monkeypatch, tmp_path)
    _touch(tmp_path, age_seconds=60)  # 1min < 2h threshold
    sev, msg = ch.check_94_bybit_announcement_sentinel_cron_fires()
    assert sev == "PASS", msg
    assert "heartbeat fresh" in msg


def test_94_stale_is_warn(monkeypatch, tmp_path):
    _set_dir(monkeypatch, tmp_path)
    _touch(tmp_path, age_seconds=3 * 3600)  # 3h > 2h threshold
    sev, msg = ch.check_94_bybit_announcement_sentinel_cron_fires()
    assert sev == "WARN", msg
    assert "heartbeat stale" in msg


def test_94_required_mode_upgrades_missing_to_fail(monkeypatch, tmp_path):
    _set_dir(monkeypatch, tmp_path)
    monkeypatch.setenv("OPENCLAW_CRON_HEARTBEAT_REQUIRED", "1")
    sev, msg = ch.check_94_bybit_announcement_sentinel_cron_fires()
    assert sev == "FAIL", msg
    assert "heartbeat file missing" in msg

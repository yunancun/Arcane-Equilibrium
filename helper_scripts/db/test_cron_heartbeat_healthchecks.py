#!/usr/bin/env python3
"""Unit tests for cron heartbeat healthchecks [75]-[79].

MODULE_NOTE:
  P1-CRON-INSTALL-WAVE-1（2026-05-18）— 驗 5 個 cron heartbeat sentinel：
    - 新鮮 sentinel → PASS
    - 缺失 sentinel → WARN（或 FAIL when OPENCLAW_CRON_HEARTBEAT_REQUIRED=1）
    - 過時 sentinel → WARN with age detail
    - threshold 邊界（剛好 == threshold / 剛超過）→ PASS / WARN

  pytest tmp_path fixture 隔離真實 /tmp/openclaw/cron_heartbeat（operator
  指示 do NOT touch real /tmp/openclaw）；OPENCLAW_CRON_HEARTBEAT_DIR env
  覆蓋路徑解析，所有測試走 tmp_path。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_cron_heartbeat import (  # noqa: E402
    check_75_panel_aggregator_health_cron_fires,
    check_76_wave9_replay_no_live_mutation_watch_cron_fires,
    check_77_replay_key_rotation_check_cron_fires,
    check_78_feature_baseline_writer_cron_fires,
    check_79_blocked_symbols_30d_unblock_check_cron_fires,
)

# 五 checks 對齊：函數 -> (sentinel 檔名, threshold 秒數, 人類可讀 cadence)。
# 與 checks_cron_heartbeat.py 內部 _classify() 參數同步；任一邊改 threshold
# 即觸發測試 mismatch（防 silent drift）。
_CHECK_MATRIX = [
    (
        check_75_panel_aggregator_health_cron_fires,
        "panel_aggregator_health.last_fire",
        7 * 60,
    ),
    (
        check_76_wave9_replay_no_live_mutation_watch_cron_fires,
        "wave9_replay_no_live_mutation_watch.last_fire",
        75 * 60,
    ),
    (
        check_77_replay_key_rotation_check_cron_fires,
        "replay_key_rotation_check.last_fire",
        25 * 3600,
    ),
    (
        check_78_feature_baseline_writer_cron_fires,
        "feature_baseline_writer.last_fire",
        25 * 3600,
    ),
    (
        check_79_blocked_symbols_30d_unblock_check_cron_fires,
        "blocked_symbols_30d_unblock_check.last_fire",
        8 * 86400,
    ),
]


@pytest.fixture
def heartbeat_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """隔離 sentinel 目錄到 tmp_path；清除 REQUIRED env 確保 WARN-default。"""
    target = tmp_path / "cron_heartbeat"
    target.mkdir()
    monkeypatch.setenv("OPENCLAW_CRON_HEARTBEAT_DIR", str(target))
    monkeypatch.delenv("OPENCLAW_CRON_HEARTBEAT_REQUIRED", raising=False)
    return target


def _write_sentinel(heartbeat_dir: Path, sentinel_name: str, mtime: float) -> Path:
    """建 sentinel 檔並指定 mtime，回傳路徑。"""
    path = heartbeat_dir / sentinel_name
    path.touch()
    os.utime(path, (mtime, mtime))
    return path


# ---------------------------------------------------------------------------
# 基礎 PASS / WARN（missing） / WARN（stale）三狀態
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("check_fn,sentinel_name,threshold_s", _CHECK_MATRIX)
def test_fresh_sentinel_returns_pass(
    heartbeat_dir: Path,
    check_fn,
    sentinel_name: str,
    threshold_s: int,
) -> None:
    """sentinel 存在且 age << threshold → PASS。"""
    now = 1_700_000_000.0
    # mtime = now - 1s → age 1s（極新鮮）
    _write_sentinel(heartbeat_dir, sentinel_name, now - 1.0)
    status, msg = check_fn(now=now)
    assert status == "PASS", f"{check_fn.__name__}: msg={msg}"
    assert "heartbeat fresh" in msg
    assert sentinel_name in msg


@pytest.mark.parametrize("check_fn,sentinel_name,threshold_s", _CHECK_MATRIX)
def test_missing_sentinel_returns_warn(
    heartbeat_dir: Path,
    check_fn,
    sentinel_name: str,
    threshold_s: int,
) -> None:
    """sentinel 不存在 → WARN，並提示 cron not installed。"""
    now = 1_700_000_000.0
    # heartbeat_dir 為空 — 故意不建檔
    status, msg = check_fn(now=now)
    assert status == "WARN", f"{check_fn.__name__}: msg={msg}"
    assert "heartbeat file missing" in msg
    assert "cron not installed or has never fired" in msg


@pytest.mark.parametrize("check_fn,sentinel_name,threshold_s", _CHECK_MATRIX)
def test_stale_sentinel_returns_warn_with_age(
    heartbeat_dir: Path,
    check_fn,
    sentinel_name: str,
    threshold_s: int,
) -> None:
    """sentinel 存在但 age > threshold → WARN，msg 含 age detail。"""
    now = 1_700_000_000.0
    # age = threshold + 1h，確保「明顯過時」
    stale_mtime = now - (threshold_s + 3600)
    _write_sentinel(heartbeat_dir, sentinel_name, stale_mtime)
    status, msg = check_fn(now=now)
    assert status == "WARN", f"{check_fn.__name__}: msg={msg}"
    assert "heartbeat stale" in msg
    assert "cron likely stopped firing" in msg


# ---------------------------------------------------------------------------
# Threshold 邊界（剛好 / 剛超過）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("check_fn,sentinel_name,threshold_s", _CHECK_MATRIX)
def test_threshold_exact_boundary_passes(
    heartbeat_dir: Path,
    check_fn,
    sentinel_name: str,
    threshold_s: int,
) -> None:
    """age == threshold 邊界 → PASS（內部用 `age > threshold` 判斷 stale）。

    為什麼用 strictly-greater：cron 觸發抖動是常態，邊界 inclusive WARN
    會把「剛好 5min 後跑一輪」誤判為 stale。
    """
    now = 1_700_000_000.0
    # age = threshold（精準等於）
    exact_mtime = now - threshold_s
    _write_sentinel(heartbeat_dir, sentinel_name, exact_mtime)
    status, msg = check_fn(now=now)
    assert status == "PASS", f"{check_fn.__name__}: msg={msg}"


@pytest.mark.parametrize("check_fn,sentinel_name,threshold_s", _CHECK_MATRIX)
def test_threshold_just_over_warns(
    heartbeat_dir: Path,
    check_fn,
    sentinel_name: str,
    threshold_s: int,
) -> None:
    """age = threshold + 1s → WARN。"""
    now = 1_700_000_000.0
    over_mtime = now - (threshold_s + 1)
    _write_sentinel(heartbeat_dir, sentinel_name, over_mtime)
    status, msg = check_fn(now=now)
    assert status == "WARN", f"{check_fn.__name__}: msg={msg}"
    assert "heartbeat stale" in msg


# ---------------------------------------------------------------------------
# OPENCLAW_CRON_HEARTBEAT_REQUIRED=1 升 WARN → FAIL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("check_fn,sentinel_name,threshold_s", _CHECK_MATRIX)
def test_required_mode_escalates_missing_to_fail(
    heartbeat_dir: Path,
    check_fn,
    sentinel_name: str,
    threshold_s: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQUIRED=1 時 sentinel 缺失應升 FAIL（fail-closed mode）。"""
    monkeypatch.setenv("OPENCLAW_CRON_HEARTBEAT_REQUIRED", "1")
    now = 1_700_000_000.0
    status, msg = check_fn(now=now)
    assert status == "FAIL", f"{check_fn.__name__}: msg={msg}"
    assert "heartbeat file missing" in msg


@pytest.mark.parametrize("check_fn,sentinel_name,threshold_s", _CHECK_MATRIX)
def test_required_mode_escalates_stale_to_fail(
    heartbeat_dir: Path,
    check_fn,
    sentinel_name: str,
    threshold_s: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQUIRED=1 時 sentinel 過時應升 FAIL。"""
    monkeypatch.setenv("OPENCLAW_CRON_HEARTBEAT_REQUIRED", "1")
    now = 1_700_000_000.0
    stale_mtime = now - (threshold_s + 3600)
    _write_sentinel(heartbeat_dir, sentinel_name, stale_mtime)
    status, msg = check_fn(now=now)
    assert status == "FAIL", f"{check_fn.__name__}: msg={msg}"


@pytest.mark.parametrize("check_fn,sentinel_name,threshold_s", _CHECK_MATRIX)
def test_required_mode_fresh_still_passes(
    heartbeat_dir: Path,
    check_fn,
    sentinel_name: str,
    threshold_s: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REQUIRED=1 時新鮮 sentinel 仍 PASS — required mode 不影響 happy path。"""
    monkeypatch.setenv("OPENCLAW_CRON_HEARTBEAT_REQUIRED", "1")
    now = 1_700_000_000.0
    _write_sentinel(heartbeat_dir, sentinel_name, now - 1.0)
    status, _msg = check_fn(now=now)
    assert status == "PASS", f"{check_fn.__name__} required+fresh should PASS"


# ---------------------------------------------------------------------------
# Path 解析：OPENCLAW_CRON_HEARTBEAT_DIR 高於 OPENCLAW_DATA_DIR
# ---------------------------------------------------------------------------


def test_heartbeat_dir_env_overrides_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPENCLAW_CRON_HEARTBEAT_DIR 指定時應覆蓋 OPENCLAW_DATA_DIR 推導。

    為什麼分兩個 env：DATA_DIR 是 cron 共用根目錄，HEARTBEAT_DIR 提供
    測試 / 隔離環境直接指 sentinel 根目錄；priority HEARTBEAT_DIR > DATA_DIR。
    """
    override_dir = tmp_path / "explicit_heartbeat"
    override_dir.mkdir()
    monkeypatch.setenv("OPENCLAW_CRON_HEARTBEAT_DIR", str(override_dir))
    # 故意設一個不存在的 DATA_DIR；override 該勝出
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(tmp_path / "nonexistent"))
    monkeypatch.delenv("OPENCLAW_CRON_HEARTBEAT_REQUIRED", raising=False)

    now = 1_700_000_000.0
    sentinel = override_dir / "panel_aggregator_health.last_fire"
    sentinel.touch()
    os.utime(sentinel, (now - 1.0, now - 1.0))

    status, msg = check_75_panel_aggregator_health_cron_fires(now=now)
    assert status == "PASS"
    assert str(override_dir) in msg


def test_data_dir_default_path_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """無 HEARTBEAT_DIR 時，sentinel 路徑 = OPENCLAW_DATA_DIR/cron_heartbeat。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.delenv("OPENCLAW_CRON_HEARTBEAT_DIR", raising=False)
    monkeypatch.setenv("OPENCLAW_DATA_DIR", str(data_dir))
    monkeypatch.delenv("OPENCLAW_CRON_HEARTBEAT_REQUIRED", raising=False)

    # 缺 sentinel → WARN，msg 路徑應反映 DATA_DIR/cron_heartbeat
    status, msg = check_75_panel_aggregator_health_cron_fires(
        now=1_700_000_000.0
    )
    assert status == "WARN"
    expected_path = str(data_dir / "cron_heartbeat" / "panel_aggregator_health.last_fire")
    assert expected_path in msg


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

"""pytest fixtures for Phase 1b healthcheck tests.

MODULE_NOTE:
  腳本檔名以 digit 開頭（62_*.py 等），Python module import 文法不可直接
  ``from 62_close_maker_fill_rate import run``。本 conftest 用
  ``importlib.util.spec_from_file_location`` 動態載入，避同時改 production
  腳本檔名。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

# 添加 healthchecks 目錄到 sys.path 讓 _common import 工作
HEALTHCHECKS_DIR = Path(__file__).resolve().parent.parent
if str(HEALTHCHECKS_DIR) not in sys.path:
    sys.path.insert(0, str(HEALTHCHECKS_DIR))


def _load_script(filename: str, module_name: str) -> ModuleType:
    """以 importlib 從 digit-prefixed file 載入 module。"""
    spec = importlib.util.spec_from_file_location(
        module_name, HEALTHCHECKS_DIR / filename
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def hc62():
    return _load_script("62_close_maker_fill_rate.py", "hc62_close_maker_fill_rate")


@pytest.fixture(scope="session")
def hc63():
    return _load_script("63_close_maker_fallback_audit.py", "hc63_fallback_audit")


@pytest.fixture(scope="session")
def hc64():
    return _load_script(
        "64_close_maker_rate_limit_pause_duration.py", "hc64_rate_limit"
    )


@pytest.fixture(scope="session")
def hc65():
    return _load_script("65_reject_sample_healthcheck.py", "hc65_reject_sample")


@pytest.fixture(scope="session")
def hc66():
    # P1-OBS-PRE-STOPOUT-RATE（2026-05-21）新增 [66] standalone healthcheck
    # 對應 FA round 1 #5 close maker 來得及量度（R2 從 [71] 改 [66]
    # 避與 passive_wait_healthcheck [71] close_maker_zero_spine_lineage
    # 字面碰撞 — 兩 namespace 物理分離但 PM/operator mixed report 易混淆）
    return _load_script(
        "66_close_maker_pre_stopout_rate.py", "hc66_pre_stopout_rate"
    )


class FakeCursor:
    """Minimal psycopg2-cursor stub for SQL/result unit tests."""

    def __init__(self, results_queue: list):
        # ``results_queue`` 是按 cur.execute 順序回傳的 fetchall/fetchone payload
        # 每 element = list of tuple（fetchall）或單 tuple（fetchone）
        self._queue = list(results_queue)
        self._last = None
        self.executed_sqls: list[tuple[str, tuple]] = []

    def execute(self, sql, params=None):
        self.executed_sqls.append((sql, params))
        if self._queue:
            self._last = self._queue.pop(0)
        else:
            self._last = []

    def fetchall(self):
        if isinstance(self._last, list):
            return list(self._last)
        return [self._last] if self._last is not None else []

    def fetchone(self):
        if isinstance(self._last, list):
            return self._last[0] if self._last else None
        return self._last


@pytest.fixture
def fake_cursor_factory():
    """Factory: tests pass list of fetchall/fetchone payloads."""
    def _make(queue):
        return FakeCursor(queue)
    return _make

#!/usr/bin/env python3
"""Tests for [16] strategist_cycle_fresh log-tail parsing.

MODULE_NOTE (EN): Standalone unittest for the scheduler liveness sentinel.
It uses a temporary OPENCLAW_DATA_DIR and synthetic engine.log lines so it
does not require Postgres, IPC, or a running engine.

MODULE_NOTE (中): [16] strategist_cycle_fresh 單元測試。使用臨時
OPENCLAW_DATA_DIR 與合成 engine.log，不依賴 Postgres / IPC / runtime。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_HELPER_SCRIPTS_DIR = os.path.dirname(_THIS_DIR)
_SRV_ROOT = os.path.dirname(_HELPER_SCRIPTS_DIR)
sys.path.insert(0, _SRV_ROOT)

from helper_scripts.db.passive_wait_healthcheck.checks_strategy import (  # noqa: E402
    check_strategist_cycle_fresh,
)


def _utc_ts() -> str:
    """Return a tracing-compatible UTC timestamp.
    回傳與 tracing log 相容的 UTC timestamp。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class TestStrategistCycleFresh(unittest.TestCase):
    """[16] log parser coverage for live scheduler activity shapes."""

    def _run_with_log(self, log_text: str) -> tuple[str, str]:
        """Run the check against a temporary engine.log.
        對臨時 engine.log 跑 check。"""
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "engine.log").write_text(log_text, encoding="utf-8")
            with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": tmp}, clear=False):
                return check_strategist_cycle_fresh()

    def test_delta_cap_reject_counts_as_cycle_activity(self) -> None:
        """Reject-only cycle activity should PASS, not look wedged.
        只有 reject 的 cycle 仍是活動，不應判成 wedge。"""
        ts = _utc_ts()
        log = (
            f"{ts} INFO openclaw_engine::strategist_scheduler: "
            "StrategistScheduler started (5-min cycle)\n"
            f"{ts} WARN openclaw_engine::strategist_scheduler: "
            "delta exceeds configured cap "
            "(RiskConfig.strategist.max_param_delta_pct) / delta 超過配置上限\n"
        )

        status, msg = self._run_with_log(log)

        self.assertEqual(status, "PASS")
        self.assertIn("last cycle", msg)

    def test_ansi_colored_timestamp_is_parsed(self) -> None:
        """Runtime logs may contain tracing ANSI color escapes before ts.
        runtime engine.log 可能在 timestamp 前帶 tracing ANSI 色碼。"""
        ts = _utc_ts()
        log = (
            f"\x1b[2m{ts}\x1b[0m \x1b[32m INFO\x1b[0m "
            "openclaw_engine::strategist_scheduler: "
            "StrategistScheduler cycle complete / 評估週期完成\n"
        )

        status, msg = self._run_with_log(log)

        self.assertEqual(status, "PASS")
        self.assertIn("last cycle", msg)


if __name__ == "__main__":
    unittest.main()

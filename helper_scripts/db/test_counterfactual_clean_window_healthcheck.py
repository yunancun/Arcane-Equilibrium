#!/usr/bin/env python3
"""Tests for passive_wait_healthcheck [11] counterfactual clean window.
[11] counterfactual clean window 健檢單元測試。

MODULE_NOTE (EN): Covers the JSON-only [11] check without a Postgres
dependency. The production writer uses a rolling ``--days`` replay, so row
counts may shrink when old exits age out; that must stay WARN, not FAIL.

MODULE_NOTE (中): 覆蓋不依賴 Postgres 的 [11] JSON 健檢。production writer 使用
rolling ``--days`` replay，舊 exits 滾出時 row count 可下降；此情況應為 WARN，
不是 FAIL。
"""

from __future__ import annotations

import json
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

from helper_scripts.db.passive_wait_healthcheck.checks_strategy_counterfactual import (  # noqa: E402
    check_counterfactual_clean_window_growth,
)


class TestCounterfactualCleanWindowGrowth(unittest.TestCase):
    """Regression semantics for rolling vs cumulative replay windows.
    rolling 與 cumulative replay 視窗的倒退語義。"""

    def _write_latest(
        self,
        data_dir: Path,
        *,
        days: int | None,
        grid_rows: int = 218,
        ma_rows: int = 178,
        orphan_rows: int = 2,
    ) -> None:
        """Write a minimal counterfactual replay JSON.
        寫入最小可用 counterfactual replay JSON。"""
        audit_dir = data_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "by_window": {
                "post-P013-clean": [
                    {
                        "strategy_name": "grid_trading",
                        "n_exits": grid_rows,
                        "per_model": {"fee_only": {"cf_fired_count": 16}},
                    },
                    {
                        "strategy_name": "ma_crossover",
                        "n_exits": ma_rows,
                        "per_model": {"fee_only": {"cf_fired_count": 22}},
                    },
                    {
                        "strategy_name": "orphan_frozen",
                        "n_exits": orphan_rows,
                        "per_model": {"fee_only": {"cf_fired_count": 0}},
                    },
                ]
            },
        }
        if days is not None:
            payload["days"] = days
        (audit_dir / "counterfactual_exit_replay_latest.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def _write_prior_snapshot(self, data_dir: Path, n_rows: int) -> None:
        """Write a historical daily snapshot before today's key.
        寫入早於今日 key 的歷史 daily snapshot。"""
        daily_dir = data_dir / "audit" / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        (daily_dir / "20000101.json").write_text(
            json.dumps({"n_rows": n_rows}),
            encoding="utf-8",
        )

    def test_rolling_window_shrink_is_warn_not_fail(self) -> None:
        """A rolling --days replay may shrink as old rows age out.
        rolling --days replay 會因舊 rows 滾出而下降。"""
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            self._write_latest(data_dir, days=2)
            self._write_prior_snapshot(data_dir, n_rows=864)

            with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": str(data_dir)}):
                status, msg = check_counterfactual_clean_window_growth()

        self.assertEqual(status, "WARN")
        self.assertIn("rolling 2d window shrank from 864", msg)

    def test_non_rolling_regression_remains_fail(self) -> None:
        """A cumulative/non-rolling replay shrink remains a red data signal.
        cumulative / non-rolling replay 下降仍是紅燈資料訊號。"""
        with tempfile.TemporaryDirectory() as td:
            data_dir = Path(td)
            self._write_latest(data_dir, days=None)
            self._write_prior_snapshot(data_dir, n_rows=864)

            with patch.dict(os.environ, {"OPENCLAW_DATA_DIR": str(data_dir)}):
                status, msg = check_counterfactual_clean_window_growth()

        self.assertEqual(status, "FAIL")
        self.assertIn("n_rows regressed from 864", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)

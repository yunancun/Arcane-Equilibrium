#!/usr/bin/env python3
"""Unit tests — funding_arb 14d audit script 的 ``_load_sl_hard_cap_pct``.

P3-AUDIT-SCRIPT-STALE-CONST · 2026-05-21
========================================
驗證 ``_load_sl_hard_cap_pct`` 動態讀 ``risk_config_demo.toml`` 的三條路徑：
  1. 只有 global ``limits.stop_loss_max_pct`` → 回 0.25
  2. per_strategy.funding_arb override 存在 → override 路徑優先
  3. 即 fallback 路徑：缺 per_strategy section 或 funding_arb key → global

audit 模組檔名為 ``2026-05-16_funding_arb_14d_audit.py``，以數字 / 連字符
開頭，不符合 Python 標準 import；以 ``importlib.util.spec_from_file_location``
動態載入。
"""

from __future__ import annotations

import importlib.util
import io
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_HERE = Path(__file__).resolve().parent
_AUDIT_SCRIPT = _HERE / "2026-05-16_funding_arb_14d_audit.py"


def _load_audit_module() -> types.ModuleType:
    """以絕對路徑載入有日期前綴的 audit script 為 module。"""
    spec = importlib.util.spec_from_file_location(
        "funding_arb_14d_audit_under_test", _AUDIT_SCRIPT
    )
    assert spec is not None and spec.loader is not None, (
        f"無法載入 audit script: {_AUDIT_SCRIPT}"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Module-level 載入一次，後續測試重用。注意：載入時會跑 module-level
# ``SL_HARD_CAP_PCT = _load_sl_hard_cap_pct()`` 讀真實 TOML — 那一次成功是
# 預設 fixture 的副作用，不在本測試斷言範圍。
_AUDIT_MODULE = _load_audit_module()


class TestLoadSlHardCapPct(unittest.TestCase):
    """``_load_sl_hard_cap_pct`` 三條路徑覆蓋。"""

    def _patch_tomllib_load(self, fake_cfg: dict):
        """以 fake TOML dict 取代 ``tomllib.load``；Path.open 仍真實開啟
        （任何存在的檔即可，內容無關，因 tomllib.load 已被 mock）。"""
        # Path.open 返回真實 binary handle，但內容無關（tomllib.load 被 mock）
        fake_handle = io.BytesIO(b"")
        return (
            patch.object(_AUDIT_MODULE.tomllib, "load", return_value=fake_cfg),
            patch("pathlib.Path.open", return_value=fake_handle),
        )

    def test_global_fallback_returns_25_pct(self) -> None:
        """無 per_strategy.funding_arb override → 回退 limits.stop_loss_max_pct。"""
        fake_cfg = {
            "limits": {"stop_loss_max_pct": 25.0},
            "per_strategy": {"ma_crossover": {"stop_loss_max_pct_override": 2.5}},
        }
        tomllib_patch, path_patch = self._patch_tomllib_load(fake_cfg)
        with tomllib_patch, path_patch:
            result = _AUDIT_MODULE._load_sl_hard_cap_pct()
        self.assertAlmostEqual(result, 0.25, places=6)

    def test_funding_arb_override_takes_priority(self) -> None:
        """per_strategy.funding_arb.stop_loss_max_pct_override 存在 → 優先。"""
        fake_cfg = {
            "limits": {"stop_loss_max_pct": 25.0},
            "per_strategy": {
                "funding_arb": {"stop_loss_max_pct_override": 3.0},
            },
        }
        tomllib_patch, path_patch = self._patch_tomllib_load(fake_cfg)
        with tomllib_patch, path_patch:
            result = _AUDIT_MODULE._load_sl_hard_cap_pct()
        self.assertAlmostEqual(result, 0.03, places=6)

    def test_missing_per_strategy_section_falls_back_to_global(self) -> None:
        """完全缺 per_strategy section → 回退 global limits。"""
        fake_cfg = {"limits": {"stop_loss_max_pct": 10.0}}
        tomllib_patch, path_patch = self._patch_tomllib_load(fake_cfg)
        with tomllib_patch, path_patch:
            result = _AUDIT_MODULE._load_sl_hard_cap_pct()
        self.assertAlmostEqual(result, 0.10, places=6)

    def test_per_strategy_funding_arb_missing_override_key_falls_back(self) -> None:
        """per_strategy.funding_arb section 存在但無 stop_loss_max_pct_override
        key → 回退 global limits。"""
        fake_cfg = {
            "limits": {"stop_loss_max_pct": 25.0},
            "per_strategy": {
                "funding_arb": {"active": True},  # 無 override key
            },
        }
        tomllib_patch, path_patch = self._patch_tomllib_load(fake_cfg)
        with tomllib_patch, path_patch:
            result = _AUDIT_MODULE._load_sl_hard_cap_pct()
        self.assertAlmostEqual(result, 0.25, places=6)


class TestRealTomlLoad(unittest.TestCase):
    """真實 TOML smoke test — 確認當前 demo TOML 與 W-AUDIT-6 一致。"""

    def test_current_demo_toml_returns_25_pct(self) -> None:
        """W-AUDIT-6 後 funding_arb override 應已移除；當前 effective SL gate = 25%。

        若此 test 失敗 = 有人重啟 funding_arb override 或改 global
        stop_loss_max_pct，請走 PA / QC 流程 sign-off。
        """
        result = _AUDIT_MODULE._load_sl_hard_cap_pct()
        self.assertAlmostEqual(
            result, 0.25, places=6,
            msg=(
                "Expected effective SL gate = 25% (W-AUDIT-6 後 funding_arb "
                "override 已移除)。若意外為 0.03，代表 funding_arb override "
                "被重新加回 demo TOML — 請先查 git log 並走 PA / QC 流程。"
            ),
        )


if __name__ == "__main__":
    unittest.main()
